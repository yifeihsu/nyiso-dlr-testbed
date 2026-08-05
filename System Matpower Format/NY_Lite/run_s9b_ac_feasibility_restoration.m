function outputs = run_s9b_ac_feasibility_restoration(options)
%RUN_S9B_AC_FEASIBILITY_RESTORATION Quantify shoulder AC constraint slack.
%   Uses MATPOWER AC soft limits to distinguish a zero-slack feasible point,
%   a locally restored point with quantified violations, solver nonconvergence,
%   and solver exceptions. Active-power bounds and AC balance remain hard.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
options = defaults(options, helper_dir);
define_constants;

if exist(options.voltage_reference_file, 'file') ~= 2
    build_ny_voltage_reference_sets;
end
all_references = readtable(options.voltage_reference_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');

scenario_id = string(options.scenario_id);
base = loadcase(options.structural_case);
[gsk, ~] = build_perform_npcc_generation_shift_keys(base);
[core, ~] = build_ny_only_equivalent_case(base);
[core, ~] = align_npcc_generation_capacity_to_perform_gsk(core, gsk);
[core, ~] = apply_nyiso_zonal_loads(core, scenario_id, 1.0, ...
    struct('preserve_total_ny_load', true));
zonal = readtable(options.zonal_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
zonal = zonal(string(zonal.scenario_id) == scenario_id, :);
zones = string(('A':'K')');
generation = vector_by_zone(zonal, zones, 'target_generation_mw');
[core, ~] = apply_perform_generation_allocation(core, ...
    table(zones, generation, ...
    'VariableNames', {'zone','target_generation_mw'}), gsk);
[base_case, ext] = apply_nyiso_external_interface_injections(core, ...
    scenario_id, struct('target_file', options.external_target_file));
base_case = set_zone_reference(base_case, ext.added_gen_index, "J");
q_targets = build_perform_zonal_q_capability_targets(core);
base_case = apply_zonal_q_limits(base_case, q_targets, ext.added_gen_index);
scheduled_pg = base_case.gen(:, PG);
physical_vmin = base_case.bus(:, VMIN);
physical_vmax = base_case.bus(:, VMAX);

summary_rows = table();
slack_rows = table();
external_q_rows = table();
interface_rows = table();

boundary_modes = string(options.boundary_q_modes);
reference_sets = string(options.voltage_reference_sets);
directions = string(options.sweep_directions);
start_modes = string(options.start_modes);
for reference_set = reference_sets(:)'
    voltage_reference = all_references( ...
        string(all_references.reference_set) == reference_set, :);
    [present, ~] = ismember(voltage_reference.model_bus, base_case.bus(:, BUS_I));
    voltage_reference = voltage_reference(present, :);
    if isempty(voltage_reference)
        error('Voltage reference set %s has no buses in the S9b model.', ...
            reference_set);
    end
    for direction = directions(:)'
        weights = options.reference_weights(:)';
        if direction == "decreasing"
            weights = sort(weights, 'descend');
        else
            weights = sort(weights, 'ascend');
        end
        for start_mode = start_modes(:)'
            perturbation_ids = 0;
            if startsWith(start_mode, "perturbed")
                perturbation_ids = options.perturbation_ids(:)';
            end
            for perturbation_id = perturbation_ids
                run_options = options;
                run_options.voltage_reference_set = reference_set;
                run_options.sweep_direction = direction;
                run_options.start_mode = start_mode;
                run_options.perturbation_id = perturbation_id;
                for mode = boundary_modes(:)'
                    seed = struct();
                    for reference_weight = weights
                        [summary, slacks, external_q, interface_detail, seed] = ...
                            run_point(base_case, ext, mode, reference_weight, ...
                            voltage_reference, seed, scheduled_pg, physical_vmin, ...
                            physical_vmax, scenario_id, run_options);
                        summary_rows = append_table(summary_rows, summary);
                        slack_rows = append_table(slack_rows, slacks);
                        external_q_rows = append_table(external_q_rows, external_q);
                        interface_rows = append_table(interface_rows, interface_detail);
                    end
                end
            end
        end
    end
end

if options.write_outputs
    writetable(summary_rows, options.summary_file);
    writetable(slack_rows, options.slack_file);
    writetable(external_q_rows, options.external_q_file);
    writetable(interface_rows, options.interface_file);
end
outputs = struct('scenario_id', scenario_id, 'summary', summary_rows, ...
    'slacks', slack_rows, 'external_q', external_q_rows, ...
    'interface_residuals', interface_rows, ...
    'summary_file', options.summary_file, 'slack_file', options.slack_file, ...
    'external_q_file', options.external_q_file, ...
    'interface_file', options.interface_file);
end

function options = defaults(options, helper_dir)
if isfield(options, 'use_vg_values') && ~isfield(options, 'reference_weights')
    options.reference_weights = options.use_vg_values;
end
if isfield(options, 'voltage_reference_set') && ...
        ~isfield(options, 'voltage_reference_sets')
    options.voltage_reference_sets = options.voltage_reference_set;
end
if isfield(options, 'sweep_direction') && ~isfield(options, 'sweep_directions')
    options.sweep_directions = options.sweep_direction;
end
if isfield(options, 'start_mode') && ~isfield(options, 'start_modes')
    options.start_modes = options.start_mode;
end
items = { ...
    'scenario_id', "S3_2019_SHOULDER_LIGHT_LOAD_PUBLIC"; ...
    'structural_case', 'npcc_ny_lite_s7_seven_interface_perform_direct_candidate'; ...
    'zonal_file', fullfile(helper_dir, 's8_final_zonal_generation.csv'); ...
    'external_target_file', fullfile(helper_dir, 'ny_external_interface_targets.csv'); ...
    'interface_target_file', fullfile(helper_dir, 'nyiso_public_interface_targets.csv'); ...
    'interface_scale_file', fullfile(helper_dir, 'nyiso_interface_objective_scales.csv'); ...
    'voltage_reference_file', fullfile(helper_dir, 'ny_voltage_reference_sets.csv'); ...
    'voltage_reference_sets', "S1_OPF_SOLVED_REFERENCE"; ...
    'boundary_q_modes', ["present_limited_q"; "fixed_scenario_q"; "no_discretionary_q"]; ...
    'reference_weights', (0.80:0.025:1.00)'; ...
    'sweep_directions', "increasing"; ...
    'start_modes', "warm"; ...
    'perturbation_ids', [1; 2]; ...
    'start_voltage_perturbation_pu', 0.005; ...
    'boundary_q_tolerance_mvar', 1e-4; ...
    'q_slack_cost_per_mvar', 1e3; ...
    'v_slack_cost_per_pu', 1e7; ...
    'branch_slack_cost_per_mva', 1e4; ...
    'p_deviation_cost_per_mw2', 1e-4; ...
    'outer_vmin_pu', 0.5; ...
    'outer_vmax_pu', 1.5; ...
    'slack_tolerance', 1e-5; ...
    'opf_solver', 'IPOPT'; ...
    'write_outputs', true; ...
    'summary_file', fullfile(helper_dir, 's9b_feasibility_restoration_summary.csv'); ...
    'slack_file', fullfile(helper_dir, 's9b_feasibility_restoration_slacks.csv'); ...
    'external_q_file', fullfile(helper_dir, 's9b_external_boundary_q.csv'); ...
    'interface_file', fullfile(helper_dir, 's9b_interface_residuals.csv')};
for k = 1:size(items, 1)
    if ~isfield(options, items{k, 1}), options.(items{k, 1}) = items{k, 2}; end
end
end

function vector = vector_by_zone(tbl, zones, variable)
vector = zeros(numel(zones), 1);
for z = 1:numel(zones)
    idx = find(string(tbl.zone) == zones(z), 1);
    if isempty(idx), error('Missing S8 generation row for zone %s.', zones(z)); end
    vector(z) = tbl.(variable)(idx);
end
end

function [summary, slacks, external_q, interface_detail, seed] = run_point( ...
        base_case, ext, mode, reference_weight, voltage_reference, seed, ...
        scheduled_pg, physical_vmin, physical_vmax, scenario_id, options)
define_constants;
mpc = apply_boundary_q_mode(base_case, ext, mode, ...
    options.boundary_q_tolerance_mvar);
if string(options.start_mode) == "warm" && ~isempty(fieldnames(seed))
    mpc.bus(:, [VM VA]) = seed.bus(:, [VM VA]);
    mpc.gen(:, [PG QG]) = seed.gen(:, [PG QG]);
elseif startsWith(string(options.start_mode), "perturbed")
    mpc = perturb_start(mpc, options.perturbation_id, ...
        options.start_voltage_perturbation_pu);
end
[mpc, reference_application] = apply_weighted_reference_bounds( ...
    mpc, reference_weight, voltage_reference);
mpc = set_restoration_costs(mpc, scheduled_pg, ...
    options.p_deviation_cost_per_mw2);
[hard_result, hard_success, hard_class, hard_note, hard_diag] = ...
    solve_opf_case(mpc, options, "hard");
restoration_invoked = ~hard_success;
if hard_success
    result = hard_result;
    success = true;
    termination_class = "hard_feasible_zero_slack";
    note = hard_note;
    final_diag = hard_diag;
else
    soft_mpc = add_restoration_soft_limits(mpc, ext.added_gen_index, options);
    [result, success, termination_class, note, final_diag] = ...
        solve_opf_case(soft_mpc, options, "restoration");
end
[summary, slacks, external_q, interface_detail] = summarize_run( ...
    result, success, termination_class, note, scenario_id, mode, ...
    reference_weight, scheduled_pg, ext, physical_vmin, physical_vmax, ...
    voltage_reference, restoration_invoked, hard_success, hard_class, ...
    hard_note, hard_diag, final_diag, reference_application, options);
if success
    seed = result;
end
end

function mpc = apply_boundary_q_mode(mpc, ext, mode, tolerance)
define_constants;
idx = ext.added_gen_index;
switch mode
    case "present_limited_q"
        return;
    case "fixed_scenario_q"
        target = ext.target_q_mvar;
    case "no_discretionary_q"
        target = zeros(height(ext), 1);
    otherwise
        error('Unknown external boundary-Q mode %s.', mode);
end
mpc.gen(idx, QG) = target;
mpc.gen(idx, QMIN) = target - tolerance;
mpc.gen(idx, QMAX) = target + tolerance;
end

function [mpc, application] = apply_weighted_reference_bounds( ...
        mpc, weight, reference)
define_constants;
if weight < 0 || weight > 1
    error('Voltage-reference weight must be between zero and one.');
end
applied_ids = zeros(0, 1);
skipped_pq_ids = zeros(0, 1);
for k = 1:height(reference)
    bi = find(mpc.bus(:, BUS_I) == reference.model_bus(k), 1);
    if isempty(bi), continue; end
    if mpc.bus(bi, BUS_TYPE) == PQ
        skipped_pq_ids(end + 1, 1) = reference.model_bus(k); %#ok<AGROW>
        continue;
    end
    applied_ids(end + 1, 1) = reference.model_bus(k); %#ok<AGROW>
    vmin_ref = reference.voltage_reference_min_pu(k);
    vmax_ref = reference.voltage_reference_max_pu(k);
    mpc.bus(bi, VMIN) = (1 - weight) * mpc.bus(bi, VMIN) + weight * vmin_ref;
    mpc.bus(bi, VMAX) = (1 - weight) * mpc.bus(bi, VMAX) + weight * vmax_ref;
    mpc.bus(bi, VM) = min(max(mpc.bus(bi, VM), mpc.bus(bi, VMIN)), ...
        mpc.bus(bi, VMAX));
end
applied_ids = unique(applied_ids, 'stable');
skipped_pq_ids = unique(skipped_pq_ids, 'stable');
if isempty(skipped_pq_ids)
    skipped_pq_reference_bus_ids = "";
else
    skipped_pq_reference_bus_ids = join(string(skipped_pq_ids(:)'), '|');
end
application = struct( ...
    'requested_reference_bus_count', height(reference), ...
    'applied_reference_bus_count', numel(applied_ids), ...
    'skipped_pq_reference_bus_count', numel(skipped_pq_ids), ...
    'skipped_pq_reference_bus_ids', skipped_pq_reference_bus_ids);
end

function mpc = perturb_start(mpc, perturbation_id, amplitude)
define_constants;
nb = size(mpc.bus, 1);
phase = (1:nb)' * (0.71 + 0.13 * double(perturbation_id));
mpc.bus(:, VM) = mpc.bus(:, VM) + amplitude * sin(phase);
mpc.bus(:, VA) = mpc.bus(:, VA) + 0.25 * double(perturbation_id) * cos(phase);
mpc.bus(:, VM) = min(max(mpc.bus(:, VM), 0.8), 1.2);
end

function mpc = set_restoration_costs(mpc, scheduled_pg, rho)
define_constants;
ng = size(mpc.gen, 1);
gencost = zeros(ng, 7);
for g = 1:ng
    coefficient = rho * double(mpc.gen(g, PMAX) - mpc.gen(g, PMIN) > 1e-6);
    p0 = scheduled_pg(g);
    gencost(g, :) = [2 0 0 3 coefficient -2 * coefficient * p0 ...
        coefficient * p0^2];
end
mpc.gencost = gencost;
end

function mpc = add_restoration_soft_limits(mpc, external_idx, options)
define_constants;
nb = size(mpc.bus, 1);
online_internal = mpc.gen(:, GEN_STATUS) > 0 & ~isload(mpc.gen);
online_internal(external_idx) = false;
rated = mpc.branch(:, BR_STATUS) > 0 & mpc.branch(:, RATE_A) > 0;
mpc.softlims = struct();
mpc.softlims.VMIN = struct('idx', (1:nb)', ...
    'cost', options.v_slack_cost_per_pu * ones(nb, 1), ...
    'hl_mod', 'replace', 'hl_val', options.outer_vmin_pu);
mpc.softlims.VMAX = struct('idx', (1:nb)', ...
    'cost', options.v_slack_cost_per_pu * ones(nb, 1), ...
    'hl_mod', 'replace', 'hl_val', options.outer_vmax_pu);
qidx = find(online_internal);
mpc.softlims.QMIN = struct('idx', qidx, ...
    'cost', options.q_slack_cost_per_mvar * ones(numel(qidx), 1), ...
    'hl_mod', 'remove');
mpc.softlims.QMAX = struct('idx', qidx, ...
    'cost', options.q_slack_cost_per_mvar * ones(numel(qidx), 1), ...
    'hl_mod', 'remove');
bidx = find(rated);
mpc.softlims.RATE_A = struct('idx', bidx, ...
    'cost', options.branch_slack_cost_per_mva * ones(numel(bidx), 1), ...
    'hl_mod', 'remove');
mpc = toggle_softlims(mpc, 'on');
end

function [result, success, termination_class, note, diagnostic] = ...
        solve_opf_case(mpc, options, solve_type)
result = struct();
success = false;
note = "";
diagnostic = empty_solver_diagnostic();
mpopt = mpoption('verbose', 0, 'out.all', 0, ...
    'opf.ac.solver', options.opf_solver, 'opf.flow_lim', 'S', ...
    'opf.violation', 1e-7, 'opf.use_vg', 0, 'opf.ignore_angle_lim', 0, ...
    'opf.softlims.default', 0, 'opf.start', 2);
try
    result = runopf(mpc, mpopt);
    success = isfield(result, 'success') && logical(result.success);
    if success
        termination_class = string(solve_type) + "_success";
    else
        termination_class = "solver_nonconvergence";
        note = solver_message(result, string(solve_type) + ...
            " ACOPF returned success = 0");
    end
    diagnostic = solver_diagnostic(result, success);
catch ME
    termination_class = "solver_exception";
    note = string(regexprep(ME.message, '\s+', ' '));
    if ~isempty(ME.stack)
        note = note + " @ " + string(ME.stack(1).name) + ":" + ...
            string(ME.stack(1).line);
    end
end
end

function diagnostic = empty_solver_diagnostic()
diagnostic = struct('status', NaN, 'iterations', NaN, ...
    'max_ac_balance_component_residual_mw_or_mvar', NaN, ...
    'max_complex_power_mismatch_mva', NaN, 'dual_residual', NaN, ...
    'complementarity_residual', NaN, 'kkt_residual', NaN, ...
    'metric_note', "AC balance fields report the maximum P/Q component " + ...
    "residual and maximum complex-power mismatch. Full IPOPT dual/" + ...
    "complementarity/KKT residuals are not exposed by the installed " + ...
    "MATPOWER wrapper.");
end

function diagnostic = solver_diagnostic(result, success)
diagnostic = empty_solver_diagnostic();
if isfield(result, 'raw') && isfield(result.raw, 'output') && ...
        isstruct(result.raw.output)
    output = result.raw.output;
    if isfield(output, 'status'), diagnostic.status = output.status; end
    if isfield(output, 'iterations'), diagnostic.iterations = output.iterations; end
end
if success
    [diagnostic.max_ac_balance_component_residual_mw_or_mvar, ...
        diagnostic.max_complex_power_mismatch_mva] = ...
        ac_balance_residuals(result);
end
end

function [component_residual, complex_residual] = ...
        ac_balance_residuals(result)
define_constants;
mpc = result;
original_bus_ids = mpc.bus(:, BUS_I);
mpc.bus(:, BUS_I) = (1:size(mpc.bus, 1))';
[found_f, f] = ismember(mpc.branch(:, F_BUS), original_bus_ids);
[found_t, t] = ismember(mpc.branch(:, T_BUS), original_bus_ids);
[found_g, g] = ismember(mpc.gen(:, GEN_BUS), original_bus_ids);
if ~all(found_f & found_t) || ~all(found_g)
    component_residual = NaN;
    complex_residual = NaN;
    return;
end
mpc.branch(:, F_BUS) = f;
mpc.branch(:, T_BUS) = t;
mpc.gen(:, GEN_BUS) = g;
[Ybus, ~, ~] = makeYbus(mpc.baseMVA, mpc.bus, mpc.branch);
Sbus = makeSbus(mpc.baseMVA, mpc.bus, mpc.gen);
V = mpc.bus(:, VM) .* exp(1j * deg2rad(mpc.bus(:, VA)));
mismatch = V .* conj(Ybus * V) - Sbus;
component_residual = max(abs([real(mismatch); imag(mismatch)])) * mpc.baseMVA;
complex_residual = max(abs(mismatch)) * mpc.baseMVA;
end

function note = solver_message(result, fallback)
note = string(fallback);
if isfield(result, 'raw') && isfield(result.raw, 'output')
    output = result.raw.output;
    if isstruct(output) && isfield(output, 'message')
        note = string(output.message);
    elseif ischar(output) || isstring(output)
        note = string(output);
    end
end
end

function [summary, slacks, external_q, detail] = summarize_run(result, ...
        success, termination_class, note, scenario_id, mode, reference_weight, ...
        scheduled_pg, ext, physical_vmin, physical_vmax, voltage_reference, ...
        restoration_invoked, hard_success, hard_class, hard_note, hard_diag, ...
        final_diag, reference_application, options)
if ~success
    summary = failed_summary(scenario_id, mode, reference_weight, ...
        termination_class, note, hard_success, hard_class, hard_note, ...
        hard_diag, final_diag, restoration_invoked, reference_application, ...
        options);
    slacks = table(); external_q = table(); detail = table();
    return;
end
define_constants;
qmin_slack = overload(result, 'QMIN');
qmax_slack = overload(result, 'QMAX');
vmin_slack = overload(result, 'VMIN');
vmax_slack = overload(result, 'VMAX');
branch_slack = overload(result, 'RATE_A');
weighted_cost = sum(overload_cost(result, 'QMIN')) + ...
    sum(overload_cost(result, 'QMAX')) + sum(overload_cost(result, 'VMIN')) + ...
    sum(overload_cost(result, 'VMAX')) + sum(overload_cost(result, 'RATE_A'));
total_slack = sum(qmin_slack) + sum(qmax_slack) + ...
    sum(vmin_slack) + sum(vmax_slack) + sum(branch_slack);
if restoration_invoked && total_slack <= options.slack_tolerance
    termination_class = "restored_zero_slack_after_hard_failure";
elseif restoration_invoked
    termination_class = "restored_nonzero_slack";
else
    termination_class = "hard_feasible_zero_slack";
end
internal_idx = setdiff((1:size(result.gen, 1))', ext.added_gen_index(:));
delta_pg = result.gen(internal_idx, PG) - scheduled_pg(internal_idx);
[vg_total, vg_max] = raw_reference_deviation(result, voltage_reference);
original_v = max(max(0, physical_vmin - result.bus(:, VM)), ...
    max(0, result.bus(:, VM) - physical_vmax));
targets = read_public_interface_targets(scenario_id, ...
    options.interface_target_file);
flows = ny_lite_interface_flows(result, ny_lite_interface_definitions(result));
[interface_objective, detail] = interface_target_objective_balanced( ...
    flows, targets, struct('scale_file', options.interface_scale_file, ...
    'min_scale_mw', 500));
detail = addvars(detail, repmat(scenario_id, height(detail), 1), ...
    repmat(string(options.voltage_reference_set), height(detail), 1), ...
    repmat(string(options.sweep_direction), height(detail), 1), ...
    repmat(string(options.start_mode), height(detail), 1), ...
    repmat(options.perturbation_id, height(detail), 1), ...
    repmat(mode, height(detail), 1), ...
    repmat(reference_weight, height(detail), 1), ...
    'Before', 1, 'NewVariableNames', ...
    {'scenario_id','voltage_reference_set','sweep_direction','start_mode', ...
    'perturbation_id','boundary_q_mode','reference_weight'});
external_q = boundary_q_report(result, ext, scenario_id, mode, ...
    reference_weight, options);
external_q_abs = sum(abs(external_q.qg_mvar));
external_q_deviation = sum(abs(external_q.q_deviation_mvar));
summary = table(scenario_id, string(options.voltage_reference_set), ...
    reference_application.requested_reference_bus_count, ...
    reference_application.applied_reference_bus_count, ...
    reference_application.skipped_pq_reference_bus_count, ...
    reference_application.skipped_pq_reference_bus_ids, ...
    string(options.sweep_direction), ...
    string(options.start_mode), options.perturbation_id, mode, ...
    reference_weight, string(options.opf_solver), true, termination_class, ...
    hard_success, hard_class, restoration_invoked, hard_diag.status, ...
    hard_diag.iterations, hard_note, final_diag.status, final_diag.iterations, ...
    final_diag.max_ac_balance_component_residual_mw_or_mvar, ...
    final_diag.max_complex_power_mismatch_mva, final_diag.dual_residual, ...
    final_diag.complementarity_residual, final_diag.kkt_residual, ...
    final_diag.metric_note, result.f, weighted_cost, sum(qmin_slack), ...
    sum(qmax_slack), sum(vmin_slack), sum(vmax_slack), sum(branch_slack), ...
    total_slack, max([0; qmin_slack; qmax_slack]), ...
    max([0; vmin_slack; vmax_slack]), max([0; branch_slack]), ...
    sum(qmin_slack > options.slack_tolerance) + ...
    sum(qmax_slack > options.slack_tolerance), ...
    sum(vmin_slack > options.slack_tolerance) + ...
    sum(vmax_slack > options.slack_tolerance), ...
    sum(branch_slack > options.slack_tolerance), vg_total, vg_max, ...
    sum(original_v), max([0; original_v]), min(result.bus(:, VM)), ...
    max(result.bus(:, VM)), sum(abs(delta_pg)), max([0; abs(delta_pg)]), ...
    external_q_abs, external_q_deviation, interface_objective, ...
    max(abs(detail.residual_mw)), note, ...
    "tap and shunt controls not modeled because defensible ranges are absent", ...
    'VariableNames', summary_names());
slacks = element_slack_report(result, scenario_id, mode, reference_weight, ...
    options.slack_tolerance, options);
end

function values = overload(result, name)
values = zeros(0, 1);
if isfield(result, 'softlims') && isfield(result.softlims, name) && ...
        isfield(result.softlims.(name), 'overload')
    values = result.softlims.(name).overload;
end
end

function values = overload_cost(result, name)
values = zeros(0, 1);
if isfield(result, 'softlims') && isfield(result.softlims, name) && ...
        isfield(result.softlims.(name), 'ovl_cost')
    values = result.softlims.(name).ovl_cost;
end
end

function [total, maximum] = raw_reference_deviation(result, reference)
define_constants;
deviation = zeros(height(reference), 1);
for k = 1:height(reference)
    bi = find(result.bus(:, BUS_I) == reference.model_bus(k), 1);
    if isempty(bi), continue; end
    deviation(k) = max(0, reference.voltage_reference_min_pu(k) - ...
        result.bus(bi, VM)) + max(0, result.bus(bi, VM) - ...
        reference.voltage_reference_max_pu(k));
end
total = sum(deviation);
maximum = max([0; deviation]);
end

function rows = element_slack_report(result, scenario_id, mode, ...
        reference_weight, tol, options)
rows = table();
for name = ["QMIN", "QMAX", "VMIN", "VMAX", "RATE_A"]
    values = overload(result, char(name));
    costs = overload_cost(result, char(name));
    for idx = find(values > tol)'
        [element_type, element_id, element_name, value, limit, unit] = ...
            describe_element(result, name, idx);
        row = table(scenario_id, string(options.voltage_reference_set), ...
            string(options.sweep_direction), string(options.start_mode), ...
            options.perturbation_id, mode, reference_weight, name, ...
            element_type, idx, ...
            element_id, element_name, value, limit, values(idx), unit, ...
            costs(idx), 'VariableNames', {'scenario_id','voltage_reference_set', ...
            'sweep_direction','start_mode','perturbation_id','boundary_q_mode', ...
            'reference_weight','slack_type','element_type','element_index', ...
            'element_id','element_name','value','original_limit','slack', ...
            'unit','weighted_cost'});
        rows = append_table(rows, row);
    end
end
end

function [type, id, name, value, limit, unit] = describe_element(result, ...
        slack_name, idx)
define_constants;
switch slack_name
    case {"QMIN", "QMAX"}
        type = "GENERATOR";
        id = result.gen(idx, GEN_BUS);
        bi = find(result.bus(:, BUS_I) == id, 1);
        name = string(strtrim(result.bus_name{bi}));
        value = result.gen(idx, QG);
        if slack_name == "QMIN", limit = result.gen(idx, QMIN); ...
        else, limit = result.gen(idx, QMAX); end
        unit = "MVAr";
    case {"VMIN", "VMAX"}
        type = "BUS";
        id = result.bus(idx, BUS_I);
        name = string(strtrim(result.bus_name{idx}));
        value = result.bus(idx, VM);
        if slack_name == "VMIN", limit = result.bus(idx, VMIN); ...
        else, limit = result.bus(idx, VMAX); end
        unit = "pu";
    otherwise
        type = "BRANCH";
        id = idx;
        fi = find(result.bus(:, BUS_I) == result.branch(idx, F_BUS), 1);
        ti = find(result.bus(:, BUS_I) == result.branch(idx, T_BUS), 1);
        name = string(strtrim(result.bus_name{fi})) + " - " + ...
            string(strtrim(result.bus_name{ti}));
        value = max(hypot(result.branch(idx, PF), result.branch(idx, QF)), ...
            hypot(result.branch(idx, PT), result.branch(idx, QT)));
        limit = result.branch(idx, RATE_A);
        unit = "MVA";
end
end

function rows = boundary_q_report(result, ext, scenario_id, mode, ...
        reference_weight, options)
define_constants;
rows = table();
for k = 1:height(ext)
    g = ext.added_gen_index(k);
    qg = result.gen(g, QG);
    target = ext.target_q_mvar(k);
    row = table(scenario_id, string(options.voltage_reference_set), ...
        string(options.sweep_direction), string(options.start_mode), ...
        options.perturbation_id, mode, reference_weight, ...
        string(ext.external_interface_name(k)), g, result.gen(g, GEN_BUS), ...
        result.gen(g, PG), qg, target, qg - target, result.gen(g, QMIN), ...
        result.gen(g, QMAX), ...
        'VariableNames', {'scenario_id','voltage_reference_set', ...
        'sweep_direction','start_mode','perturbation_id','boundary_q_mode', ...
        'reference_weight', ...
        'external_interface_name','gen_index','bus_id','pg_mw','qg_mvar', ...
        'target_q_mvar','q_deviation_mvar','qmin_mvar','qmax_mvar'});
    rows = append_table(rows, row);
end
end

function summary = failed_summary(scenario_id, mode, reference_weight, ...
        termination_class, note, hard_success, hard_class, hard_note, ...
        hard_diag, final_diag, restoration_invoked, reference_application, options)
names = summary_names();
values = repmat({NaN}, 1, numel(names));
values = set_named_value(values, names, 'scenario_id', scenario_id);
values = set_named_value(values, names, 'voltage_reference_set', ...
    string(options.voltage_reference_set));
fields = {'requested_reference_bus_count','applied_reference_bus_count', ...
    'skipped_pq_reference_bus_count','skipped_pq_reference_bus_ids'};
for k = 1:numel(fields)
    values = set_named_value(values, names, fields{k}, ...
        reference_application.(fields{k}));
end
values = set_named_value(values, names, 'sweep_direction', ...
    string(options.sweep_direction));
values = set_named_value(values, names, 'start_mode', ...
    string(options.start_mode));
values = set_named_value(values, names, 'perturbation_id', ...
    options.perturbation_id);
values = set_named_value(values, names, 'boundary_q_mode', mode);
values = set_named_value(values, names, 'reference_weight', reference_weight);
values = set_named_value(values, names, 'solver', string(options.opf_solver));
values = set_named_value(values, names, 'opf_success', false);
values = set_named_value(values, names, 'termination_class', termination_class);
values = set_named_value(values, names, 'hard_attempt_success', hard_success);
values = set_named_value(values, names, 'hard_termination_class', hard_class);
values = set_named_value(values, names, 'restoration_invoked', restoration_invoked);
values = set_named_value(values, names, 'hard_solver_status', hard_diag.status);
values = set_named_value(values, names, 'hard_iterations', hard_diag.iterations);
values = set_named_value(values, names, 'hard_solver_note', hard_note);
values = set_named_value(values, names, 'final_solver_status', final_diag.status);
values = set_named_value(values, names, 'final_iterations', final_diag.iterations);
values = set_named_value(values, names, ...
    'max_ac_balance_component_residual_mw_or_mvar', ...
    final_diag.max_ac_balance_component_residual_mw_or_mvar);
values = set_named_value(values, names, 'max_complex_power_mismatch_mva', ...
    final_diag.max_complex_power_mismatch_mva);
values = set_named_value(values, names, 'dual_residual', final_diag.dual_residual);
values = set_named_value(values, names, 'complementarity_residual', ...
    final_diag.complementarity_residual);
values = set_named_value(values, names, 'kkt_residual', final_diag.kkt_residual);
values = set_named_value(values, names, 'solver_metric_note', ...
    final_diag.metric_note);
values = set_named_value(values, names, 'solver_note', note);
values = set_named_value(values, names, 'unmodeled_controls', ...
    "tap and shunt controls not modeled because defensible ranges are absent");
summary = cell2table(values, 'VariableNames', names);
end

function names = summary_names()
names = {'scenario_id','voltage_reference_set', ...
    'requested_reference_bus_count','applied_reference_bus_count', ...
    'skipped_pq_reference_bus_count','skipped_pq_reference_bus_ids', ...
    'sweep_direction','start_mode','perturbation_id','boundary_q_mode', ...
    'reference_weight','solver','opf_success','termination_class', ...
    'hard_attempt_success','hard_termination_class','restoration_invoked', ...
    'hard_solver_status','hard_iterations','hard_solver_note', ...
    'final_solver_status','final_iterations', ...
    'max_ac_balance_component_residual_mw_or_mvar', ...
    'max_complex_power_mismatch_mva', ...
    'dual_residual','complementarity_residual','kkt_residual', ...
    'solver_metric_note','objective','weighted_restoration_cost', ...
    'qmin_slack_mvar','qmax_slack_mvar','vmin_slack_pu','vmax_slack_pu', ...
    'branch_slack_mva','unweighted_mixed_unit_slack_total', ...
    'max_q_slack_mvar','max_v_slack_pu','max_branch_slack_mva', ...
    'q_slack_element_count','v_slack_element_count', ...
    'branch_slack_element_count','raw_vg_deviation_total_pu', ...
    'raw_vg_deviation_max_pu','original_voltage_violation_total_pu', ...
    'original_voltage_violation_max_pu','min_voltage_pu','max_voltage_pu', ...
    'total_absolute_p_redispatch_mw','max_single_p_redispatch_mw', ...
    'external_q_absolute_mvar','external_q_deviation_from_prior_mvar', ...
    'interface_objective','max_abs_interface_residual_mw','solver_note', ...
    'unmodeled_controls'};
end

function values = set_named_value(values, names, name, value)
idx = find(strcmp(names, name), 1);
if isempty(idx), error('Unknown summary field %s.', name); end
values{idx} = value;
end

function mpc = apply_zonal_q_limits(mpc, targets, external_idx)
define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
[mapped, bi] = ismember(mpc.gen(:, GEN_BUS), mpc.bus(:, BUS_I));
gen_zone = strings(size(mpc.gen, 1), 1);
gen_zone(mapped) = string(mpc.userdata.nyiso_physical_zone(bi(mapped)));
internal = mpc.gen(:, GEN_STATUS) > 0 & gen_zone ~= "";
internal(external_idx) = false;
for z = 1:height(targets)
    idx = find(internal & gen_zone == string(targets.zone(z)));
    if isempty(idx), continue; end
    weights = max(0, mpc.gen(idx, PMAX));
    if sum(weights) <= 0, weights = ones(numel(idx), 1); end
    weights = weights / sum(weights);
    mpc.gen(idx, QMIN) = targets.target_qmin_mvar(z) * weights;
    mpc.gen(idx, QMAX) = targets.target_qmax_mvar(z) * weights;
    mpc.gen(idx, QG) = min(max(mpc.gen(idx, QG), mpc.gen(idx, QMIN)), ...
        mpc.gen(idx, QMAX));
end
end

function mpc = set_zone_reference(mpc, external_idx, zone_name)
define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
[mapped, bi] = ismember(mpc.gen(:, GEN_BUS), mpc.bus(:, BUS_I));
zone = strings(size(mpc.gen, 1), 1);
zone(mapped) = string(mpc.userdata.nyiso_physical_zone(bi(mapped)));
mask = mpc.gen(:, GEN_STATUS) > 0 & zone == zone_name;
mask(external_idx) = false;
idx = find(mask);
qrange = mpc.gen(idx, QMAX) - mpc.gen(idx, QMIN);
if any(qrange > 1e-6), idx = idx(qrange > 1e-6); end
[~, k] = max(mpc.gen(idx, PMAX) - mpc.gen(idx, PG));
mpc = set_scenario_reference_bus(mpc, idx(k), ...
    struct('require_external', false));
end

function out = append_table(out, row)
if isempty(row), return; end
if isempty(out), out = row; else, out = [out; row]; end
end
