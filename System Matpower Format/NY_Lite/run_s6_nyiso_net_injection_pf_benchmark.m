function outputs = run_s6_nyiso_net_injection_pf_benchmark(options)
%RUN_S6_NYISO_NET_INJECTION_PF_BENCHMARK Apply public interchange and injections.
%   Builds the S4 NY boundary-equivalent network, fixes scaled P-32 external
%   schedules, estimates zonal generation/net injections from public P-58C
%   loads and P-32 internal flows, allocates generation using PERFORM GSKs,
%   and validates the resulting operating point with an AC power flow.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
options = defaults(options, helper_dir);

scenarios = readtable(options.scenario_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
base_full = loadcase('npcc_ny_lite_s4_cost_calibration_candidate_v2');
[gsk, ~] = build_perform_npcc_generation_shift_keys(base_full);
% Standard PF is used for the flow-consistency test. Q-limit enforcement is
% diagnosed separately because the P-only reduced equivalents can otherwise
% eliminate every PV/REF control bus during MATPOWER's conversion loop.
pfopt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 0);
qpfopt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1);

result_rows = table();
zonal_rows = table();
interface_rows = table();
estimator_rows = table();
external_rows = table();
allocation_rows = table();
violation_rows = table();
q_diagnostic_rows = table();

for s = 1:height(scenarios)
    scenario_id = string(scenarios.scenario_id(s));
    [core, ~] = build_ny_only_equivalent_case(base_full);
    [core, ~] = align_npcc_generation_capacity_to_perform_gsk(core, gsk);
    [core, ~] = apply_nyiso_zonal_loads(core, scenario_id, 1.0, ...
        struct('preserve_total_ny_load', true));

    estimator_case = core;
    [estimator_case, ext_est] = apply_nyiso_external_interface_injections( ...
        estimator_case, scenario_id, struct('target_file', options.external_target_file));
    estimator_options = struct('interface_target_file', options.interface_target_file, ...
        'interface_scale_file', options.interface_scale_file, ...
        'prior_weight', options.prior_weight, ...
        'balance_zone', options.balance_zone);
    [zonal_targets, estimator] = derive_nyiso_zonal_net_injections( ...
        estimator_case, scenario_id, gsk, ext_est.added_gen_index, estimator_options);

    [core, allocation] = apply_perform_generation_allocation( ...
        core, zonal_targets(:, {'zone','target_generation_mw'}), gsk);
    [mpc, ext_report] = apply_nyiso_external_interface_injections( ...
        core, scenario_id, struct('target_file', options.external_target_file));
    [mpc, ref_gen, ref_bus, scheduled_ref_pg] = set_internal_reference(mpc, ...
        ext_report.added_gen_index, options.balance_zone);
    results = runpf(mpc, pfopt);
    [q_success, q_note, q_result] = run_q_enforced_diagnostic(mpc, qpfopt);
    q_metrics = q_enforced_metrics(q_result, scenario_id, ext_report, options);
    qrow = table(scenario_id, q_success, q_metrics.interface_objective, ...
        q_metrics.max_abs_interface_residual_mw, q_metrics.min_voltage_pu, ...
        q_metrics.max_voltage_pu, q_metrics.voltage_violation_count, ...
        q_metrics.branch_overload_count, q_metrics.max_external_schedule_error_mw, ...
        q_note, 'VariableNames', {'scenario_id','q_enforced_pf_success', ...
        'interface_objective','max_abs_interface_residual_mw','min_voltage_pu', ...
        'max_voltage_pu','voltage_violation_count','branch_overload_count', ...
        'max_external_schedule_error_mw','diagnostic'});
    q_diagnostic_rows = append_table(q_diagnostic_rows, qrow);

    [result_row, residuals, actual_zones, interchange, violations] = ...
        summarize_result(results, scenario_id, zonal_targets, estimator, ...
        ext_report, ref_gen, ref_bus, scheduled_ref_pg, options);
    result_rows = append_table(result_rows, result_row);
    zonal_rows = append_table(zonal_rows, actual_zones);
    interface_rows = append_table(interface_rows, residuals);
    external_rows = append_table(external_rows, interchange);
    violation_rows = append_table(violation_rows, violations);
    allocation_rows = append_table(allocation_rows, add_scenario(allocation, scenario_id));

    erow = table(scenario_id, estimator.total_load_mw, ...
        estimator.total_external_import_mw, estimator.required_generation_mw, ...
        estimator.prior_weight, estimator.prior_objective, ...
        estimator.predicted_objective, estimator.exitflag, ...
        string(estimator.balance_zone), ...
        'VariableNames', {'scenario_id','total_load_mw', ...
        'total_external_import_mw','required_generation_mw','prior_weight', ...
        'prior_dc_interface_objective','inferred_dc_interface_objective', ...
        'estimator_exitflag','balance_zone'});
    estimator_rows = append_table(estimator_rows, erow);
end

writetable(result_rows, options.result_file);
writetable(zonal_rows, options.zonal_file);
writetable(interface_rows, options.interface_file);
writetable(estimator_rows, options.estimator_file);
writetable(external_rows, options.external_file);
writetable(allocation_rows, options.allocation_file);
writetable(violation_rows, options.violation_file);
writetable(q_diagnostic_rows, options.q_diagnostic_file);

outputs = struct('result_file', options.result_file, ...
    'zonal_file', options.zonal_file, 'interface_file', options.interface_file, ...
    'estimator_file', options.estimator_file, 'external_file', options.external_file, ...
    'allocation_file', options.allocation_file, ...
    'violation_file', options.violation_file, ...
    'q_diagnostic_file', options.q_diagnostic_file, ...
    'scenario_count', height(result_rows), ...
    'pf_success_count', sum(result_rows.pf_success));
end

function options = defaults(options, helper_dir)
values = { ...
    'scenario_file', fullfile(helper_dir, 'nyiso_public_scenarios.csv'); ...
    'external_target_file', fullfile(helper_dir, 'ny_external_interface_targets.csv'); ...
    'interface_target_file', fullfile(helper_dir, 'nyiso_public_interface_targets.csv'); ...
    'interface_scale_file', fullfile(helper_dir, 'nyiso_interface_objective_scales.csv'); ...
    'result_file', fullfile(helper_dir, 's6_nyiso_net_injection_pf_results.csv'); ...
    'zonal_file', fullfile(helper_dir, 's6_nyiso_zonal_net_injection_targets.csv'); ...
    'interface_file', fullfile(helper_dir, 's6_nyiso_net_injection_interface_residuals.csv'); ...
    'estimator_file', fullfile(helper_dir, 's6_nyiso_net_injection_estimator.csv'); ...
    'external_file', fullfile(helper_dir, 's6_nyiso_external_interchange_validation.csv'); ...
    'allocation_file', fullfile(helper_dir, 's6_nyiso_perform_bus_allocation.csv'); ...
    'violation_file', fullfile(helper_dir, 's6_nyiso_net_injection_pf_violations.csv'); ...
    'q_diagnostic_file', fullfile(helper_dir, 's6_nyiso_q_enforced_pf_diagnostics.csv'); ...
    'prior_weight', 0.05; ...
    'balance_zone', "J"};
for k = 1:size(values, 1)
    if ~isfield(options, values{k, 1})
        options.(values{k, 1}) = values{k, 2};
    end
end
end

function [success, note, result] = run_q_enforced_diagnostic(mpc, mpopt)
success = false;
note = "";
result = struct();
try
    result = runpf(mpc, mpopt);
    success = isfield(result, 'success') && logical(result.success);
    if ~success, note = "Q-limit-enforced PF returned success = 0"; end
catch ME
    note = string(regexprep(ME.message, '\s+', ' '));
end
end

function metrics = q_enforced_metrics(results, scenario_id, ext_report, options)
metrics = struct('interface_objective', NaN, ...
    'max_abs_interface_residual_mw', NaN, 'min_voltage_pu', NaN, ...
    'max_voltage_pu', NaN, 'voltage_violation_count', NaN, ...
    'branch_overload_count', NaN, 'max_external_schedule_error_mw', NaN);
if ~isfield(results, 'success') || ~logical(results.success), return; end
define_constants;
targets = read_public_interface_targets(scenario_id, options.interface_target_file);
flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
[metrics.interface_objective, detail] = interface_target_objective_balanced( ...
    flows, targets, struct('scale_file', options.interface_scale_file, ...
    'min_scale_mw', 500));
metrics.max_abs_interface_residual_mw = max(abs(detail.residual_mw));
metrics.min_voltage_pu = min(results.bus(:, VM));
metrics.max_voltage_pu = max(results.bus(:, VM));
metrics.voltage_violation_count = sum(results.bus(:, VM) < ...
    results.bus(:, VMIN) - 1e-6 | results.bus(:, VM) > results.bus(:, VMAX) + 1e-6);
sf = hypot(results.branch(:, PF), results.branch(:, QF));
st = hypot(results.branch(:, PT), results.branch(:, QT));
smax = max(sf, st);
metrics.branch_overload_count = sum(results.branch(:, RATE_A) > 0 & ...
    smax > results.branch(:, RATE_A) + 1e-6);
idx = ext_report.added_gen_index(:);
metrics.max_external_schedule_error_mw = max(abs( ...
    results.gen(idx, PG) - ext_report.target_flow_mw));
end

function [mpc, ref_gen, ref_bus, scheduled_pg] = set_internal_reference( ...
        mpc, external_idx, balance_zone)
define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
[mapped, bi] = ismember(mpc.gen(:, GEN_BUS), mpc.bus(:, BUS_I));
zone = strings(size(mpc.gen, 1), 1);
zone(mapped) = string(mpc.userdata.nyiso_physical_zone(bi(mapped)));
mask = mpc.gen(:, GEN_STATUS) > 0 & zone == upper(string(balance_zone));
mask(external_idx) = false;
idx = find(mask);
if isempty(idx), error('No internal reference generator exists in zone %s.', balance_zone); end
q_range = mpc.gen(idx, QMAX) - mpc.gen(idx, QMIN);
q_capable = idx(q_range > 1e-6);
if ~isempty(q_capable)
    idx = q_capable;
end
[~, k] = max(mpc.gen(idx, PMAX) - mpc.gen(idx, PG));
ref_gen = idx(k);
ref_bus = mpc.gen(ref_gen, GEN_BUS);
scheduled_pg = mpc.gen(ref_gen, PG);
mpc = set_scenario_reference_bus(mpc, ref_gen, struct('require_external', false));
end

function [row, residuals, zonal, interchange, violations] = summarize_result( ...
        results, scenario_id, targets, estimator, ext_report, ...
        ref_gen, ref_bus, scheduled_ref_pg, options)
define_constants;
success = isfield(results, 'success') && logical(results.success);
residuals = table(); zonal = table(); interchange = table(); violations = table();
if ~success
    names = result_names();
    values = num2cell(nan(1, numel(names)));
    values{1} = scenario_id;
    values{2} = false;
    row = cell2table(values, 'VariableNames', names);
    return;
end

results = attach_nyiso_zone_metadata(results);
public_targets = read_public_interface_targets(scenario_id, options.interface_target_file);
flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
[J, residuals] = interface_target_objective_balanced(flows, public_targets, ...
    struct('scale_file', options.interface_scale_file, 'min_scale_mw', 500));
residuals = add_scenario(residuals, scenario_id);
dc = estimator.interface_table;
residuals.prior_dc_flow_mw = nan(height(residuals), 1);
residuals.inferred_dc_flow_mw = nan(height(residuals), 1);
residuals.inferred_dc_residual_mw = nan(height(residuals), 1);
for k = 1:height(residuals)
    di = find(dc.interface_name == residuals.interface_name(k), 1);
    if ~isempty(di)
        residuals.prior_dc_flow_mw(k) = dc.prior_dc_flow_mw(di);
        residuals.inferred_dc_flow_mw(k) = dc.predicted_dc_flow_mw(di);
        residuals.inferred_dc_residual_mw(k) = dc.predicted_dc_residual_mw(di);
    end
end

external_idx = ext_report.added_gen_index(:);
target_external = ext_report.target_flow_mw;
actual_external = results.gen(external_idx, PG);
external_error = actual_external - target_external;
interchange = ext_report(:, {'external_interface_name','p32_interface_name', ...
    'ny_boundary_bus','target_flow_mw'});
interchange.actual_flow_mw = actual_external;
interchange.error_mw = external_error;
interchange = add_scenario(interchange, scenario_id);

[mapped, gen_bus_idx] = ismember(results.gen(:, GEN_BUS), results.bus(:, BUS_I));
gen_zone = strings(size(results.gen, 1), 1);
gen_zone(mapped) = string(results.userdata.nyiso_physical_zone(gen_bus_idx(mapped)));
internal = results.gen(:, GEN_STATUS) > 0 & gen_zone ~= "";
internal(external_idx) = false;
zones = string(('A':'K')');
zonal = table();
for z = 1:numel(zones)
    gi = internal & gen_zone == zones(z);
    target_row = targets(targets.zone == zones(z), :);
    actual_generation = sum(results.gen(gi, PG));
    actual_load = target_row.target_load_mw(1);
    actual_native = actual_generation - actual_load;
    actual_effective = actual_native + target_row.external_import_mw(1);
    zrow = table(scenario_id, "actual_pf", zones(z), actual_load, ...
        target_row.external_import_mw(1), target_row.generation_prior_mw(1), ...
        target_row.pmin_mw(1), target_row.pmax_mw(1), ...
        target_row.at_pmin(1), target_row.at_pmax(1), ...
        target_row.target_generation_mw(1), ...
        actual_generation, actual_generation - target_row.target_generation_mw(1), ...
        target_row.target_native_net_injection_mw(1), actual_native, ...
        target_row.target_effective_net_injection_mw(1), actual_effective, ...
        'VariableNames', {'scenario_id','row_type','zone','target_load_mw', ...
        'external_import_mw','generation_prior_mw','pmin_mw','pmax_mw', ...
        'target_at_pmin','target_at_pmax','target_generation_mw', ...
        'actual_generation_mw', ...
        'generation_error_mw','target_native_net_injection_mw', ...
        'actual_native_net_injection_mw','target_effective_net_injection_mw', ...
        'actual_effective_net_injection_mw'});
    zonal = append_table(zonal, zrow);
end

sf = hypot(results.branch(:, PF), results.branch(:, QF));
st = hypot(results.branch(:, PT), results.branch(:, QT));
smax = max(sf, st);
rated = results.branch(:, RATE_A) > 0 & results.branch(:, BR_STATUS) > 0;
overload = max(0, smax - results.branch(:, RATE_A));
voltage_low = max(0, results.bus(:, VMIN) - results.bus(:, VM));
voltage_high = max(0, results.bus(:, VM) - results.bus(:, VMAX));
p_under = max(0, results.gen(:, PMIN) - results.gen(:, PG));
p_over = max(0, results.gen(:, PG) - results.gen(:, PMAX));
p_violation = max(p_under, p_over);
q_under = max(0, results.gen(:, QMIN) - results.gen(:, QG));
q_over = max(0, results.gen(:, QG) - results.gen(:, QMAX));
q_violation = max(q_under, q_over);

total_load = sum(results.bus(:, PD));
total_generation = sum(results.gen(results.gen(:, GEN_STATUS) > 0, PG));
losses = total_generation - total_load;
max_residual = max(abs(residuals.residual_mw));
reference_adjustment = results.gen(ref_gen, PG) - scheduled_ref_pg;
row = table(scenario_id, true, J, estimator.prior_objective, ...
    estimator.predicted_objective, total_load, total_generation, losses, ...
    sum(target_external), sum(actual_external), max(abs(external_error)), ...
    ref_gen, ref_bus, reference_adjustment, min(results.bus(:, VM)), ...
    max(results.bus(:, VM)), sum(voltage_low > 1e-6 | voltage_high > 1e-6), ...
    sum(rated & overload > 1e-6), max([0; overload(rated)]), ...
    sum(p_violation > 1e-6), max([0; p_violation]), ...
    sum(q_violation > 1e-6), max([0; q_violation]), max_residual, ...
    'VariableNames', result_names());

violations = collect_violations(results, scenario_id, external_idx);
end

function names = result_names()
names = {'scenario_id','pf_success','ac_interface_objective', ...
    'prior_dc_interface_objective','inferred_dc_interface_objective', ...
    'total_load_mw','total_generation_mw','losses_mw', ...
    'target_external_interchange_mw','actual_external_interchange_mw', ...
    'max_external_schedule_error_mw','reference_gen_index','reference_bus_id', ...
    'reference_generation_adjustment_mw','min_voltage_pu','max_voltage_pu', ...
    'voltage_violation_count','branch_overload_count','max_branch_overload_mva', ...
    'generator_p_violation_count','max_generator_p_violation_mw', ...
    'generator_q_violation_count','max_generator_q_violation_mvar', ...
    'max_abs_interface_residual_mw'};
end

function rows = collect_violations(results, scenario_id, external_idx)
define_constants;
rows = table();
names = string(results.bus_name(:));
sf = hypot(results.branch(:, PF), results.branch(:, QF));
st = hypot(results.branch(:, PT), results.branch(:, QT));
smax = max(sf, st);
for b = find(results.branch(:, RATE_A) > 0 & ...
        smax > results.branch(:, RATE_A) + 1e-6)'
    fi = find(results.bus(:, BUS_I) == results.branch(b, F_BUS), 1);
    ti = find(results.bus(:, BUS_I) == results.branch(b, T_BUS), 1);
    row = table(scenario_id, "BRANCH_OVERLOAD", b, ...
        results.branch(b, F_BUS), names(fi), results.branch(b, T_BUS), names(ti), ...
        smax(b), results.branch(b, RATE_A), ...
        smax(b) - results.branch(b, RATE_A), "MVA", ...
        'VariableNames', violation_names());
    rows = append_table(rows, row);
end
for b = find(results.bus(:, VM) < results.bus(:, VMIN) - 1e-6)'
    row = table(scenario_id, "LOW_VOLTAGE", b, results.bus(b, BUS_I), ...
        names(b), NaN, "", results.bus(b, VM), results.bus(b, VMIN), ...
        results.bus(b, VMIN) - results.bus(b, VM), "pu", ...
        'VariableNames', violation_names());
    rows = append_table(rows, row);
end
for b = find(results.bus(:, VM) > results.bus(:, VMAX) + 1e-6)'
    row = table(scenario_id, "HIGH_VOLTAGE", b, results.bus(b, BUS_I), ...
        names(b), NaN, "", results.bus(b, VM), results.bus(b, VMAX), ...
        results.bus(b, VM) - results.bus(b, VMAX), "pu", ...
        'VariableNames', violation_names());
    rows = append_table(rows, row);
end
pviol = max(max(0, results.gen(:, PMIN) - results.gen(:, PG)), ...
    max(0, results.gen(:, PG) - results.gen(:, PMAX)));
for g = find(pviol > 1e-6)'
    bi = find(results.bus(:, BUS_I) == results.gen(g, GEN_BUS), 1);
    kind = "GEN_P_LIMIT";
    if ismember(g, external_idx), kind = "EXTERNAL_GEN_P_LIMIT"; end
    row = table(scenario_id, kind, g, results.gen(g, GEN_BUS), names(bi), ...
        NaN, "", results.gen(g, PG), ...
        max(results.gen(g, PMIN), min(results.gen(g, PG), results.gen(g, PMAX))), ...
        pviol(g), "MW", 'VariableNames', violation_names());
    rows = append_table(rows, row);
end
qviol = max(max(0, results.gen(:, QMIN) - results.gen(:, QG)), ...
    max(0, results.gen(:, QG) - results.gen(:, QMAX)));
for g = find(qviol > 1e-6)'
    bi = find(results.bus(:, BUS_I) == results.gen(g, GEN_BUS), 1);
    kind = "GEN_Q_LIMIT";
    if ismember(g, external_idx), kind = "EXTERNAL_GEN_Q_LIMIT"; end
    row = table(scenario_id, kind, g, results.gen(g, GEN_BUS), names(bi), ...
        NaN, "", results.gen(g, QG), ...
        max(results.gen(g, QMIN), min(results.gen(g, QG), results.gen(g, QMAX))), ...
        qviol(g), "MVAr", 'VariableNames', violation_names());
    rows = append_table(rows, row);
end
end

function names = violation_names()
names = {'scenario_id','violation_type','element_index','from_or_bus_id', ...
    'from_or_bus_name','to_bus_id','to_bus_name','value','limit', ...
    'violation_amount','units'};
end

function tbl = add_scenario(tbl, scenario_id)
if isempty(tbl), return; end
if ismember('scenario_id', tbl.Properties.VariableNames)
    return;
end
tbl = addvars(tbl, repmat(string(scenario_id), height(tbl), 1), ...
    'Before', 1, 'NewVariableNames', 'scenario_id');
if ~ismember('row_type', tbl.Properties.VariableNames) && ...
        ismember('target_generation_mw', tbl.Properties.VariableNames)
    tbl = addvars(tbl, repmat("target", height(tbl), 1), ...
        'After', 1, 'NewVariableNames', 'row_type');
end
end

function out = append_table(out, row)
if isempty(row), return; end
if isempty(out), out = row; else, out = [out; row]; end
end
