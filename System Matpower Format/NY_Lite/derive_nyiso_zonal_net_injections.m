function [targets, diagnostics] = derive_nyiso_zonal_net_injections( ...
        mpc, scenario_id, gsk, external_gen_idx, options)
%DERIVE_NYISO_ZONAL_NET_INJECTIONS Infer zonal PG from public flow targets.
%   Public zonal loads and external boundary injections must already be
%   applied to MPC. A constrained DC inverse problem estimates nonnegative
%   zonal generation totals that match the scaled P-32 interface targets.
%   PERFORM zonal generation supplies only the regularization prior and its
%   bus shift keys define how each zonal total is injected.

if nargin < 5, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
if ~isfield(options, 'interface_target_file')
    options.interface_target_file = fullfile(helper_dir, ...
        'nyiso_public_interface_targets.csv');
end
if ~isfield(options, 'interface_scale_file')
    options.interface_scale_file = fullfile(helper_dir, ...
        'nyiso_interface_objective_scales.csv');
end
if ~isfield(options, 'prior_weight'), options.prior_weight = 0.05; end
if ~isfield(options, 'min_scale_mw'), options.min_scale_mw = 500; end
if ~isfield(options, 'balance_zone'), options.balance_zone = "J"; end
if ~isfield(options, 'sensitivity_step_mw'), options.sensitivity_step_mw = 1; end

define_constants;
zones = string(('A':'K')');
mpc = attach_nyiso_zone_metadata(mpc);
external_gen_idx = unique(external_gen_idx(:));
external_gen_idx = external_gen_idx(external_gen_idx >= 1 & ...
    external_gen_idx <= size(mpc.gen, 1));

[gen_mapped, gen_bus_idx] = ismember(mpc.gen(:, GEN_BUS), mpc.bus(:, BUS_I));
gen_zone = strings(size(mpc.gen, 1), 1);
gen_zone(gen_mapped) = string(mpc.userdata.nyiso_physical_zone(gen_bus_idx(gen_mapped)));
internal = mpc.gen(:, GEN_STATUS) > 0 & gen_zone ~= "";
internal(external_gen_idx) = false;

load_mw = zeros(numel(zones), 1);
external_import_mw = zeros(numel(zones), 1);
pmin = zeros(numel(zones), 1);
pmax = zeros(numel(zones), 1);
perform_pg = zeros(numel(zones), 1);
for z = 1:numel(zones)
    bus_mask = string(mpc.userdata.nyiso_physical_zone) == zones(z);
    load_mw(z) = sum(mpc.bus(bus_mask, PD));
    gi = find(internal & gen_zone == zones(z));
    pmin(z) = sum(mpc.gen(gi, PMIN));
    pmax(z) = sum(mpc.gen(gi, PMAX));
    egi = external_gen_idx(gen_zone(external_gen_idx) == zones(z));
    external_import_mw(z) = sum(mpc.gen(egi, PG));
    grow = gsk(gsk.zone == zones(z), :);
    if ~isempty(grow)
        perform_pg(z) = grow.perform_zone_pg_mw(1);
    end
end

required_generation_mw = sum(load_mw) - sum(external_import_mw);
if required_generation_mw < sum(pmin) - 1e-6 || ...
        required_generation_mw > sum(pmax) + 1e-6
    error('derive_nyiso_zonal_net_injections:GenerationBounds', ...
        ['Required internal generation %.3f MW is outside aggregate zonal ' ...
         'limits [%.3f, %.3f] MW.'], required_generation_mw, ...
        sum(pmin), sum(pmax));
end

if sum(perform_pg) <= 0
    raw_prior = pmax / max(sum(pmax), eps) * required_generation_mw;
    prior_source = "model_capability_share";
else
    raw_prior = perform_pg / sum(perform_pg) * required_generation_mw;
    prior_source = "scaled_PERFORM_2019_on_peak_zonal_PG";
end
prior = project_total(raw_prior, pmin, pmax, required_generation_mw);

balance_zone = upper(string(options.balance_zone));
balance_idx = find(zones == balance_zone, 1);
if isempty(balance_idx) || pmax(balance_idx) <= pmin(balance_idx)
    error('derive_nyiso_zonal_net_injections:BalanceZone', ...
        'Balance zone %s has no adjustable generation.', string(options.balance_zone));
end
adjustable = pmax - pmin > 1e-9;
variable_idx = find(adjustable & (1:numel(zones))' ~= balance_idx);
fixed_idx = setdiff((1:numel(zones))', [variable_idx; balance_idx], 'stable');
fixed_generation_mw = sum(prior(fixed_idx));
remaining_generation_mw = required_generation_mw - fixed_generation_mw;

mpc0 = set_internal_zonal_generation(mpc, zones, prior, gsk, internal, gen_zone);
ref_gen = choose_reference_generator(mpc0, internal & gen_zone == balance_zone);
mpc0 = set_scenario_reference_bus(mpc0, ref_gen, ...
    struct('require_external', false));
dcopt = mpoption('verbose', 0, 'out.all', 0, 'model', 'DC');
base_result = rundcpf(mpc0, dcopt);
if ~base_result.success
    error('derive_nyiso_zonal_net_injections:BaseDCPF', ...
        'The prior dispatch did not converge in DC PF.');
end

public_targets = read_public_interface_targets(scenario_id, ...
    options.interface_target_file);
[base_flow, names] = target_flow_vector(base_result, public_targets);
target_flow = public_targets.target_flow_mw;
scales = objective_scales(public_targets, options);

step = options.sensitivity_step_mw;
response = zeros(height(public_targets), numel(variable_idx));
for k = 1:numel(variable_idx)
    trial = prior;
    trial(variable_idx(k)) = trial(variable_idx(k)) + step;
    trial(balance_idx) = trial(balance_idx) - step;
    trial_mpc = set_internal_zonal_generation(mpc0, zones, trial, ...
        gsk, internal, gen_zone);
    trial_result = rundcpf(trial_mpc, dcopt);
    if ~trial_result.success
        error('derive_nyiso_zonal_net_injections:SensitivityDCPF', ...
            'DC sensitivity run failed for zone %s.', zones(variable_idx(k)));
    end
    trial_flow = target_flow_vector(trial_result, public_targets);
    response(:, k) = (trial_flow - base_flow) / step;
end

x0 = prior(variable_idx);
W = diag(1 ./ scales);
C_interface = W * response;
d_interface = W * (target_flow - base_flow + response * x0);

prior_scale = max(500, pmax);
root_lambda = sqrt(max(0, options.prior_weight));
C_prior = zeros(numel(zones), numel(variable_idx));
d_prior = zeros(numel(zones), 1);
for k = 1:numel(variable_idx)
    z = variable_idx(k);
    C_prior(z, k) = root_lambda / prior_scale(z);
    d_prior(z) = root_lambda * prior(z) / prior_scale(z);
end
C_prior(balance_idx, :) = -root_lambda / prior_scale(balance_idx);
d_prior(balance_idx) = root_lambda * ...
    (prior(balance_idx) - remaining_generation_mw) / prior_scale(balance_idx);

C = [C_interface; C_prior];
d = [d_interface; d_prior];
A = [ones(1, numel(variable_idx)); -ones(1, numel(variable_idx))];
b = [remaining_generation_mw - pmin(balance_idx); ...
    pmax(balance_idx) - remaining_generation_mw];
lb = pmin(variable_idx);
ub = pmax(variable_idx);
solver_options = optimoptions('lsqlin', 'Display', 'off', ...
    'Algorithm', 'interior-point');
[x, resnorm, ~, exitflag, output] = lsqlin(C, d, A, b, [], [], ...
    lb, ub, x0, solver_options);
if exitflag <= 0
    error('derive_nyiso_zonal_net_injections:LeastSquares', ...
        'Constrained zonal estimator failed: %s', output.message);
end

generation = zeros(numel(zones), 1);
generation(fixed_idx) = prior(fixed_idx);
generation(variable_idx) = x;
generation(balance_idx) = remaining_generation_mw - sum(x);
predicted_flow = base_flow + response * (x - x0);
prior_residual = base_flow - target_flow;
predicted_residual = predicted_flow - target_flow;
prior_objective = sum((prior_residual ./ scales).^2);
predicted_objective = sum((predicted_residual ./ scales).^2);

native_net_injection = generation - load_mw;
effective_net_injection = native_net_injection + external_import_mw;
at_pmin = abs(generation - pmin) <= 1e-4;
at_pmax = abs(generation - pmax) <= 1e-4;
targets = table(zones, load_mw, external_import_mw, prior, generation, ...
    native_net_injection, effective_net_injection, pmin, pmax, ...
    at_pmin, at_pmax, repmat(prior_source, numel(zones), 1), ...
    'VariableNames', {'zone','target_load_mw','external_import_mw', ...
    'generation_prior_mw','target_generation_mw', ...
    'target_native_net_injection_mw','target_effective_net_injection_mw', ...
    'pmin_mw','pmax_mw','at_pmin','at_pmax','prior_source'});

interface_table = table(names, target_flow, base_flow, prior_residual, ...
    predicted_flow, predicted_residual, scales, ...
    (prior_residual ./ scales).^2, (predicted_residual ./ scales).^2, ...
    'VariableNames', {'interface_name','target_flow_mw','prior_dc_flow_mw', ...
    'prior_dc_residual_mw','predicted_dc_flow_mw', ...
    'predicted_dc_residual_mw','scale_mw','prior_objective_term', ...
    'predicted_objective_term'});
diagnostics = struct('scenario_id', string(scenario_id), ...
    'required_generation_mw', required_generation_mw, ...
    'total_load_mw', sum(load_mw), ...
    'total_external_import_mw', sum(external_import_mw), ...
    'prior_weight', options.prior_weight, ...
    'prior_objective', prior_objective, ...
    'predicted_objective', predicted_objective, ...
    'resnorm', resnorm, 'exitflag', exitflag, ...
    'balance_zone', balance_zone, 'reference_gen_index', ref_gen, ...
    'interface_table', interface_table, 'response_matrix', response);
end

function projected = project_total(seed, lower, upper, total)
scale = max(500, upper);
C = diag(1 ./ scale);
d = C * seed;
opts = optimoptions('lsqlin', 'Display', 'off', 'Algorithm', 'interior-point');
[projected, ~, ~, exitflag, output] = lsqlin(C, d, [], [], ...
    ones(1, numel(seed)), total, lower, upper, seed, opts);
if exitflag <= 0
    error('derive_nyiso_zonal_net_injections:PriorProjection', ...
        'Could not project the generation prior: %s', output.message);
end
end

function mpc = set_internal_zonal_generation(mpc, zones, generation, ...
        gsk, internal, gen_zone)
define_constants;
mpc.gen(internal, PG) = 0;
for z = 1:numel(zones)
    target = generation(z);
    gi_zone = find(internal & gen_zone == zones(z));
    rows = gsk(gsk.zone == zones(z), :);
    if isempty(gi_zone)
        if abs(target) > 1e-6
            error('No internal generator is available in zone %s.', zones(z));
        end
        continue;
    end
    if isempty(rows)
        error('No PERFORM bus shift key is available for zone %s.', zones(z));
    end
    for r = 1:height(rows)
        gi = gi_zone(mpc.gen(gi_zone, GEN_BUS) == rows.npcc_bus_id(r));
        bus_target = target * rows.perform_bus_weight(r);
        if isempty(gi)
            error('No online generator is available at mapped bus %.0f.', ...
                rows.npcc_bus_id(r));
        end
        pmax = mpc.gen(gi, PMAX);
        if sum(pmax) <= 0 && bus_target > 1e-6
            error('Mapped bus %.0f has no positive generation capability.', ...
                rows.npcc_bus_id(r));
        end
        mpc.gen(gi, PG) = bus_target * pmax / max(sum(pmax), eps);
    end
end
end

function gi = choose_reference_generator(mpc, mask)
define_constants;
idx = find(mask);
if isempty(idx), error('No internal reference generator candidate exists.'); end
[~, k] = max(mpc.gen(idx, PMAX) - mpc.gen(idx, PG));
gi = idx(k);
end

function [vector, names] = target_flow_vector(results, targets)
flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
names = string(targets.interface_name);
vector = nan(height(targets), 1);
for k = 1:height(targets)
    idx = find(strcmp({flows.interface_name}, char(names(k))), 1);
    if isempty(idx)
        error('Interface %s is not defined in the reduced case.', names(k));
    end
    vector(k) = flows(idx).flow_mw;
end
end

function scales = objective_scales(targets, options)
fixed = table();
if exist(options.interface_scale_file, 'file') == 2
    fixed = readtable(options.interface_scale_file, 'TextType', 'string', ...
        'VariableNamingRule', 'preserve');
end
scales = zeros(height(targets), 1);
for k = 1:height(targets)
    name = string(targets.interface_name(k));
    idx = [];
    if ~isempty(fixed) && ismember('interface_name', fixed.Properties.VariableNames)
        idx = find(string(fixed.interface_name) == name, 1);
    end
    if ~isempty(idx)
        scales(k) = max(options.min_scale_mw, fixed.fixed_scale_mw(idx));
    elseif ismember('target_limit_mw', targets.Properties.VariableNames) && ...
            isfinite(targets.target_limit_mw(k))
        scales(k) = max(options.min_scale_mw, abs(targets.target_limit_mw(k)));
    else
        scales(k) = max(options.min_scale_mw, abs(targets.target_flow_mw(k)));
    end
end
end
