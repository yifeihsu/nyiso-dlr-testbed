function outputs = run_s4_candidate_validation_checks(options)
%RUN_S4_CANDIDATE_VALIDATION_CHECKS Validate selected S4 candidate.
%
%   Checks:
%     1. Zone-J PMAX sensitivity: 3.0, 3.5, 4.0 GW.
%     2. Voltage-deviation penalty sensitivity.
%     3. Per-scenario dispatch plausibility by zone and equivalent device.
%     4. Leave-one-out holdout scoring from the prior S4 sweep table.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'ny_external_interface_targets.csv');
end
if ~isfield(options, 'interface_target_file')
    options.interface_target_file = fullfile(helper_dir, 'nyiso_public_interface_targets.csv');
end
if ~isfield(options, 'interface_scale_file')
    options.interface_scale_file = fullfile(helper_dir, 'nyiso_interface_objective_scales.csv');
end
if ~isfield(options, 'result_file')
    options.result_file = fullfile(helper_dir, 's4_candidate_validation_results.csv');
end
if ~isfield(options, 'residual_file')
    options.residual_file = fullfile(helper_dir, 's4_candidate_validation_residuals.csv');
end
if ~isfield(options, 'device_file')
    options.device_file = fullfile(helper_dir, 's4_candidate_device_dispatch.csv');
end
if ~isfield(options, 'zonal_file')
    options.zonal_file = fullfile(helper_dir, 's4_candidate_zonal_dispatch.csv');
end
if ~isfield(options, 'summary_file')
    options.summary_file = fullfile(helper_dir, 's4_candidate_validation_summary.csv');
end
if ~isfield(options, 'holdout_file')
    options.holdout_file = fullfile(helper_dir, 's4_cost_penalty_leave_one_out_holdout.csv');
end
if ~isfield(options, 'archive_dir')
    options.archive_dir = fullfile(helper_dir, 'archives');
end
if ~isfield(options, 'zone_j_pmax_grid'), options.zone_j_pmax_grid = [3000 3500 4000]; end
if ~isfield(options, 'voltage_penalty_grid'), options.voltage_penalty_grid = [0 1e2 1e3 1e4]; end
if ~isfield(options, 'balanced_min_scale_mw'), options.balanced_min_scale_mw = 500; end
if ~isfield(options, 'make_archive'), options.make_archive = true; end

selected = selected_candidate();
build_s4_generation_alignment_targets();
build_s4_interface_objective_scales(struct('scale_file', options.interface_scale_file, ...
    'min_scale_mw', options.balanced_min_scale_mw));

scenarios = readtable(fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
cases = validation_cases(options, selected);
mpopt = mpoption( ...
    'verbose', 0, ...
    'out.all', 0, ...
    'opf.ac.solver', 'IPOPT', ...
    'opf.flow_lim', 'S', ...
    'opf.violation', 1e-6, ...
    'opf.use_vg', 0, ...
    'opf.ignore_angle_lim', 0);

result_rows = table();
residual_rows = table();
device_rows = table();
zonal_rows = table();
for c = 1:numel(cases)
    spec = cases(c);
    for s = 1:height(scenarios)
        scenario_id = string(scenarios.scenario_id(s));
        [row, residuals, devices, zonal] = run_one(scenario_id, spec, mpopt, options);
        result_rows = append_table(result_rows, row);
        residual_rows = append_table(residual_rows, residuals);
        device_rows = append_table(device_rows, devices);
        zonal_rows = append_table(zonal_rows, zonal);
    end
end

summary_rows = summarize_cases(result_rows);
holdout_rows = leave_one_out_holdout(options);
writetable(result_rows, options.result_file);
writetable(residual_rows, options.residual_file);
writetable(device_rows, options.device_file);
writetable(zonal_rows, options.zonal_file);
writetable(summary_rows, options.summary_file);
writetable(holdout_rows, options.holdout_file);

archive_file = "";
if options.make_archive
    if exist(options.archive_dir, 'dir') ~= 7, mkdir(options.archive_dir); end
    stamp = string(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
    archive_file = fullfile(options.archive_dir, ...
        "s4_candidate_validation_results_" + stamp + ".zip");
    files = {options.result_file, options.residual_file, options.device_file, ...
        options.zonal_file, options.summary_file, options.holdout_file, ...
        options.interface_scale_file, ...
        fullfile(helper_dir, 'run_s4_candidate_validation_checks.m'), ...
        fullfile(helper_dir, 'build_s4_interface_objective_scales.m'), ...
        fullfile(helper_dir, 'interface_target_objective_balanced.m'), ...
        fullfile(helper_dir, 's4_interface_objective_opf_note.md'), ...
        fullfile(helper_dir, 'add_voltage_deviation_cost.m'), ...
        fullfile(helper_dir, 'add_s4_zonal_capability_equivalents.m'), ...
        fullfile(helper_dir, 'add_zone_j_equivalent_supply.m'), ...
        fullfile(helper_dir, 'add_ny_downstate_delivery_spine.m'), ...
        fullfile(helper_dir, 'scale_ny_downstate_delivery_spine_impedance.m'), ...
        fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
        fullfile(helper_dir, 'ny_zonal_load_targets.csv'), ...
        fullfile(helper_dir, 'ny_external_interface_targets.csv'), ...
        fullfile(helper_dir, 'nyiso_public_interface_targets.csv'), ...
        fullfile(case_dir, 'npcc_ny_lite_s4_generation_aligned_candidate_v1.m')};
    files = files(cellfun(@(f) exist(f, 'file') == 2, files));
    zip(archive_file, files);
end

outputs = struct('result_file', options.result_file, ...
    'residual_file', options.residual_file, ...
    'device_file', options.device_file, ...
    'zonal_file', options.zonal_file, ...
    'summary_file', options.summary_file, ...
    'holdout_file', options.holdout_file, ...
    'interface_scale_file', options.interface_scale_file, ...
    'archive_file', archive_file, ...
    'case_count', numel(cases), ...
    'result_row_count', height(result_rows), ...
    'residual_row_count', height(residual_rows), ...
    'device_row_count', height(device_rows), ...
    'zonal_row_count', height(zonal_rows), ...
    'holdout_row_count', height(holdout_rows));
end

function selected = selected_candidate()
selected = struct('case_id', "S4_COST_main_grid_J220_E260_F260_G260_K260_CAP0p8_X1", ...
    'zone_j_cost_c1', 220, 'zone_j_cost_c2', 0.02, ...
    's4_e_cost_c1', 260, 's4_f_cost_c1', 260, ...
    's4_g_cost_c1', 260, 's4_k_cost_c1', 260, ...
    's4_cost_c2', 0.02, 'abc_cap_factor', 0.8, ...
    'x_spine_multiplier', 1.0);
end

function cases = validation_cases(options, selected)
cases = struct('case_id', {}, 'check_group', {}, 'zone_j_pmax_mw', {}, ...
    'voltage_penalty_rho', {}, 'zone_j_cost_c1', {}, 's4_e_cost_c1', {}, ...
    's4_f_cost_c1', {}, 's4_g_cost_c1', {}, 's4_k_cost_c1', {}, ...
    'zone_j_cost_c2', {}, 's4_cost_c2', {}, ...
    'abc_cap_factor', {}, 'x_spine_multiplier', {});
for pmax = options.zone_j_pmax_grid
    cases(end + 1) = make_case("zone_j_cap_sensitivity", pmax, 0, selected); %#ok<AGROW>
end
for rho = options.voltage_penalty_grid
    if rho == 0, continue; end
    cases(end + 1) = make_case("voltage_penalty", 3000, rho, selected); %#ok<AGROW>
end
end

function spec = make_case(group, pmax, rho, selected)
case_id = sprintf('S4_CAND_%s_JPMAX%s_VRHO%s', char(group), tok(pmax), tok(rho));
spec = struct('case_id', string(case_id), 'check_group', string(group), ...
    'zone_j_pmax_mw', pmax, 'voltage_penalty_rho', rho, ...
    'zone_j_cost_c1', selected.zone_j_cost_c1, ...
    'zone_j_cost_c2', selected.zone_j_cost_c2, ...
    's4_e_cost_c1', selected.s4_e_cost_c1, ...
    's4_f_cost_c1', selected.s4_f_cost_c1, ...
    's4_g_cost_c1', selected.s4_g_cost_c1, ...
    's4_k_cost_c1', selected.s4_k_cost_c1, ...
    's4_cost_c2', selected.s4_cost_c2, ...
    'abc_cap_factor', selected.abc_cap_factor, ...
    'x_spine_multiplier', selected.x_spine_multiplier);
end

function token = tok(v)
token = strrep(sprintf('%.4g', v), '.', 'p');
end

function [row, residual_rows, device_rows, zonal_rows] = run_one(scenario_id, spec, mpopt, options)
define_constants;
status = "ok";
note = "";
try
    base = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
    [mpc, ~] = build_ny_only_equivalent_case(base);
    [mpc, ~] = add_ny_downstate_delivery_spine(mpc, 'full');
    [mpc, scale_report] = scale_ny_downstate_delivery_spine_impedance(mpc, ...
        spec.x_spine_multiplier, struct('include_gilboa_leeds', false));
    [mpc, ~] = apply_nyiso_zonal_loads(mpc, scenario_id, 1.0, ...
        struct('preserve_total_ny_load', true));
    [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
        scenario_id, struct('target_file', options.target_file));
    [mpc, add_report] = add_s4_zonal_capability_equivalents(mpc, ...
        struct('include_zone_j', true, ...
        'zone_j_total_pmax_mw', spec.zone_j_pmax_mw, ...
        'zone_j_cost_c1', spec.zone_j_cost_c1, ...
        'zone_j_cost_c2', spec.zone_j_cost_c2, ...
        'equiv_cost_c1', spec.s4_f_cost_c1, ...
        'equiv_cost_c2', spec.s4_cost_c2, ...
        'q_abs_ratio', 0, ...
        'apply_upstate_participation_caps', true, ...
        'abc_cap_factor', spec.abc_cap_factor, ...
        'reclassify_ce_ug', true));
    mpc = set_s4_zone_costs(mpc, spec);
    if spec.voltage_penalty_rho > 0
        mpc = add_voltage_deviation_cost(mpc, spec.voltage_penalty_rho, 1.0);
    end
    results = runopf(mpc, mpopt);
catch ME
    results = struct();
    scale_report = table();
    ext_report = table();
    add_report = table();
    status = "error";
    note = string(regexprep(ME.message, '\s+', ' '));
end
row = summarize_result(scenario_id, spec, status, note, results, scale_report, ext_report, add_report, options);
residual_rows = summarize_residuals(scenario_id, spec, status, results, options);
device_rows = summarize_device_dispatch(scenario_id, spec, status, results);
zonal_rows = summarize_zonal_dispatch(scenario_id, spec, status, results);
end

function mpc = set_s4_zone_costs(mpc, spec)
if ~isfield(mpc, 'userdata') || ~isfield(mpc.userdata, 'ny_lite') || ...
        ~isfield(mpc.userdata.ny_lite, 's4_zonal_capability_equivalents')
    return;
end
devices = mpc.userdata.ny_lite.s4_zonal_capability_equivalents;
for k = 1:numel(devices)
    gi = devices(k).gen_index;
    if gi < 1 || gi > size(mpc.gencost, 1), continue; end
    switch string(devices(k).zone)
        case "E"
            c1 = spec.s4_e_cost_c1;
        case "F"
            c1 = spec.s4_f_cost_c1;
        case "G"
            c1 = spec.s4_g_cost_c1;
        case "K"
            c1 = spec.s4_k_cost_c1;
        otherwise
            c1 = spec.s4_f_cost_c1;
    end
    mpc.gencost(gi, 5) = spec.s4_cost_c2;
    mpc.gencost(gi, 6) = c1;
end
end

function row = summarize_result(scenario_id, spec, status, note, results, scale_report, ext_report, add_report, options)
define_constants;
names = result_columns();
if strcmp(status, "error") || ~isfield(results, 'bus')
    values = num2cell(NaN(1, numel(names) - 17));
    row = table(spec.case_id, spec.check_group, string(scenario_id), ...
        spec.zone_j_pmax_mw, spec.voltage_penalty_rho, ...
        spec.zone_j_cost_c1, spec.s4_e_cost_c1, spec.s4_f_cost_c1, ...
        spec.s4_g_cost_c1, spec.s4_k_cost_c1, spec.abc_cap_factor, ...
        spec.x_spine_multiplier, string(status), string(note), ...
        height(scale_report), height(add_report), values{:}, ...
        'VariableNames', names);
    return;
end
online = results.gen(:, GEN_STATUS) > 0;
sf = sqrt(results.branch(:, PF).^2 + results.branch(:, QF).^2);
st = sqrt(results.branch(:, PT).^2 + results.branch(:, QT).^2);
smax = max(sf, st);
rate = results.branch(:, RATE_A);
rated = rate > 0;
flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
[classic_J, classic_detail, balanced_J, balanced_detail] = interface_scores(scenario_id, results, options);
res = residual_map(balanced_detail);
[zj_pg, zj_pmax] = device_group_sum(results, "zone_j_equivalent");
[s4_pg, s4_pmax] = device_group_sum(results, "s4_zonal_capability_equivalent");
[s4_e_pg, ~] = device_zone_sum(results, "E");
[s4_f_pg, ~] = device_zone_sum(results, "F");
[s4_g_pg, ~] = device_zone_sum(results, "G");
[s4_k_pg, ~] = device_zone_sum(results, "K");
row = table(spec.case_id, spec.check_group, string(scenario_id), ...
    spec.zone_j_pmax_mw, spec.voltage_penalty_rho, ...
    spec.zone_j_cost_c1, spec.s4_e_cost_c1, spec.s4_f_cost_c1, ...
    spec.s4_g_cost_c1, spec.s4_k_cost_c1, spec.abc_cap_factor, ...
    spec.x_spine_multiplier, string(status), string(note), ...
    height(scale_report), height(add_report), double(results.success), ...
    raw_info(results), results.f, classic_J, balanced_J, ...
    max(abs(balanced_detail.residual_mw), [], 'omitnan'), ...
    mean(abs(balanced_detail.residual_mw), 'omitnan'), ...
    ext_sum(ext_report, 'target_flow_mw'), ext_sum(ext_report, 'target_q_mvar'), ...
    size(results.bus, 1), size(results.branch, 1), size(results.gen, 1), ...
    sum(results.bus(:, PD)), sum(results.bus(:, QD)), ...
    sum(results.gen(online, PG)), sum(results.gen(online, QG)), ...
    zj_pg, zj_pmax, safe_div(zj_pg, zj_pmax), ...
    s4_pg, s4_pmax, safe_div(s4_pg, s4_pmax), ...
    s4_e_pg, s4_f_pg, s4_g_pg, s4_k_pg, ...
    min(results.bus(:, VM)), max(results.bus(:, VM)), ...
    sum(results.bus(:, VM) >= results.bus(:, VMAX) - 1e-5), ...
    sum(results.bus(:, VM) <= results.bus(:, VMIN) + 1e-5), ...
    sum(rated & smax > rate + 1e-6), max([0; smax(rated) - rate(rated)]), ...
    res.central_east, res.total_east, res.upny_coned, res.dunwoodie_south, ...
    res.moses_south, interface_flow(flows, 'Total_East_proxy'), ...
    interface_flow(flows, 'UPNY_ConEd'), interface_flow(flows, 'Dunwoodie_South'), ...
    'VariableNames', names);
end

function names = result_columns()
names = {'case_id','check_group','scenario_id','zone_j_pmax_mw', ...
    'voltage_penalty_rho','zone_j_cost_c1','s4_e_cost_c1','s4_f_cost_c1', ...
    's4_g_cost_c1','s4_k_cost_c1','abc_cap_factor','x_spine_multiplier', ...
    'status','note','scaled_branch_count','added_device_count','opf_success', ...
    'opf_raw_info','objective','classic_interface_objective', ...
    'balanced_interface_objective','max_abs_interface_residual_mw', ...
    'mean_abs_interface_residual_mw','boundary_target_p_mw', ...
    'boundary_target_q_mvar','bus_count','branch_count','gen_count', ...
    'total_pd_mw','total_qd_mvar','total_pg_mw','total_qg_mvar', ...
    'zone_j_equiv_pg_mw','zone_j_equiv_pmax_mw','zone_j_fraction_pmax_used', ...
    's4_equiv_pg_mw','s4_equiv_pmax_mw','s4_fraction_pmax_used', ...
    's4_e_equiv_pg_mw','s4_f_equiv_pg_mw','s4_g_equiv_pg_mw', ...
    's4_k_equiv_pg_mw','min_voltage','max_voltage', ...
    'voltage_bound_count_high','voltage_bound_count_low', ...
    'branch_overload_count','max_branch_overload_mva', ...
    'central_east_residual_mw','total_east_residual_mw', ...
    'upny_coned_residual_mw','dunwoodie_south_residual_mw', ...
    'moses_south_residual_mw','total_east_proxy_flow_mw', ...
    'upny_coned_flow_mw','dunwoodie_south_flow_mw'};
end

function residual_rows = summarize_residuals(scenario_id, spec, status, results, options)
residual_rows = table();
if strcmp(status, "error") || ~isfield(results, 'branch'), return; end
[classic_J, classic_detail, balanced_J, balanced_detail] = interface_scores(scenario_id, results, options);
for k = 1:height(balanced_detail)
    cname = balanced_detail.interface_name(k);
    cidx = find(classic_detail.interface_name == cname, 1);
    row = table(spec.case_id, spec.check_group, string(scenario_id), ...
        spec.zone_j_pmax_mw, spec.voltage_penalty_rho, cname, ...
        balanced_detail.lite_flow_mw(k), balanced_detail.target_flow_mw(k), ...
        balanced_detail.target_limit_mw(k), balanced_detail.residual_mw(k), ...
        classic_detail.scale_mw(cidx), classic_detail.objective_term(cidx), classic_J, ...
        balanced_detail.scale_mw(k), balanced_detail.scale_source(k), ...
        balanced_detail.objective_term(k), balanced_J, ...
        'VariableNames', {'case_id','check_group','scenario_id','zone_j_pmax_mw', ...
        'voltage_penalty_rho','interface_name','lite_flow_mw','target_flow_mw', ...
        'target_limit_mw','residual_mw','classic_scale_mw', ...
        'classic_objective_term','classic_objective_total','balanced_scale_mw', ...
        'balanced_scale_source','balanced_objective_term','balanced_objective_total'});
    residual_rows = append_table(residual_rows, row);
end
end

function device_rows = summarize_device_dispatch(scenario_id, spec, status, results)
device_rows = table();
if strcmp(status, "error") || ~isfield(results, 'gen'), return; end
define_constants;
devices = all_devices(results);
for k = 1:numel(devices)
    gi = devices(k).gen_index;
    if gi < 1 || gi > size(results.gen, 1), continue; end
    row = table(spec.case_id, spec.check_group, string(scenario_id), ...
        spec.zone_j_pmax_mw, spec.voltage_penalty_rho, ...
        string(devices(k).device_group), string(devices(k).name), ...
        string(devices(k).zone), devices(k).bus_id, string(devices(k).bus_name), ...
        gi, results.gen(gi, PG), results.gen(gi, QG), results.gen(gi, PMAX), ...
        results.gen(gi, PMIN), results.gen(gi, QMAX), results.gen(gi, QMIN), ...
        safe_div(results.gen(gi, PG), results.gen(gi, PMAX)), ...
        'VariableNames', {'case_id','check_group','scenario_id','zone_j_pmax_mw', ...
        'voltage_penalty_rho','device_group','device_name','zone','bus_id', ...
        'bus_name','gen_index','pg_mw','qg_mvar','pmax_mw','pmin_mw', ...
        'qmax_mvar','qmin_mvar','fraction_pmax_used'});
    device_rows = append_table(device_rows, row);
end
end

function zonal_rows = summarize_zonal_dispatch(scenario_id, spec, status, results)
zonal_rows = table();
if strcmp(status, "error") || ~isfield(results, 'bus'), return; end
define_constants;
results = attach_nyiso_zone_metadata(results);
zones = ["A","B","C","D","E","F","G","H","I","J","K"];
boundary_idx = boundary_generator_indices(results);
s4_idx = device_indices(results, "s4_zonal_capability_equivalent");
zj_idx = device_indices(results, "zone_j_equivalent");
for z = zones
    bus_ids = zone_bus_ids(results, z);
    gen_idx = find(ismember(results.gen(:, GEN_BUS), bus_ids) & results.gen(:, GEN_STATUS) > 0);
    local_idx = setdiff(gen_idx, boundary_idx);
    load_mw = sum(results.bus(ismember(results.bus(:, BUS_I), bus_ids), PD));
    local_pg = sum(results.gen(local_idx, PG));
    boundary_pg = sum(results.gen(intersect(gen_idx, boundary_idx), PG));
    s4_pg = sum(results.gen(intersect(gen_idx, s4_idx), PG));
    zj_pg = sum(results.gen(intersect(gen_idx, zj_idx), PG));
    pmax = sum(results.gen(local_idx, PMAX));
    row = table(spec.case_id, spec.check_group, string(scenario_id), ...
        spec.zone_j_pmax_mw, spec.voltage_penalty_rho, z, load_mw, ...
        local_pg, boundary_pg, s4_pg, zj_pg, pmax, local_pg - load_mw, ...
        'VariableNames', {'case_id','check_group','scenario_id','zone_j_pmax_mw', ...
        'voltage_penalty_rho','zone','load_mw','local_pg_excluding_boundary_mw', ...
        'boundary_equiv_pg_mw','s4_equiv_pg_mw','zone_j_equiv_pg_mw', ...
        'local_pmax_excluding_boundary_mw','local_net_injection_mw'});
    zonal_rows = append_table(zonal_rows, row);
end
end

function summary = summarize_cases(rows)
keys = unique(rows(:, {'case_id','check_group','zone_j_pmax_mw', ...
    'voltage_penalty_rho'}), 'rows');
summary = table();
for k = 1:height(keys)
    mask = rows.case_id == keys.case_id(k);
    subset = rows(mask, :);
    row = table(keys.case_id(k), keys.check_group(k), keys.zone_j_pmax_mw(k), ...
        keys.voltage_penalty_rho(k), height(subset), ...
        sum(subset.opf_success == 1), ...
        sum(subset.classic_interface_objective, 'omitnan'), ...
        sum(subset.balanced_interface_objective, 'omitnan'), ...
        mean(subset.zone_j_equiv_pg_mw, 'omitnan'), ...
        max(subset.zone_j_equiv_pg_mw, [], 'omitnan'), ...
        mean(subset.s4_equiv_pg_mw, 'omitnan'), ...
        max(subset.s4_equiv_pg_mw, [], 'omitnan'), ...
        max(subset.voltage_bound_count_high + subset.voltage_bound_count_low, [], 'omitnan'), ...
        max(subset.branch_overload_count, [], 'omitnan'), ...
        min(subset.min_voltage, [], 'omitnan'), ...
        max(subset.max_voltage, [], 'omitnan'), ...
        'VariableNames', {'case_id','check_group','zone_j_pmax_mw', ...
        'voltage_penalty_rho','scenario_count','success_count', ...
        'sum_classic_interface_objective','sum_balanced_interface_objective', ...
        'mean_zone_j_equiv_pg_mw','max_zone_j_equiv_pg_mw', ...
        'mean_s4_equiv_pg_mw','max_s4_equiv_pg_mw', ...
        'max_voltage_bound_count','max_branch_overload_count', ...
        'min_voltage_observed','max_voltage_observed'});
    summary = append_table(summary, row);
end
end

function holdout_rows = leave_one_out_holdout(options)
helper_dir = fileparts(mfilename('fullpath'));
res_file = fullfile(helper_dir, 's4_cost_penalty_calibration_residuals.csv');
result_file = fullfile(helper_dir, 's4_cost_penalty_calibration_results.csv');
if exist(res_file, 'file') ~= 2 || exist(result_file, 'file') ~= 2
    holdout_rows = table();
    return;
end
res = readtable(res_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
results = readtable(result_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
scales = readtable(options.interface_scale_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');

fixed_term = zeros(height(res), 1);
for k = 1:height(res)
    scale = scale_for_interface(scales, res.interface_name(k), options.balanced_min_scale_mw);
    fixed_term(k) = (res.residual_mw(k) / scale)^2;
end
res.fixed_scale_objective_term = fixed_term;
scenario_ids = unique(res.scenario_id, 'stable');
case_ids = unique(res.case_id, 'stable');
holdout_rows = table();
for h = 1:numel(scenario_ids)
    holdout = scenario_ids(h);
    train_scores = table();
    for c = 1:numel(case_ids)
        cid = case_ids(c);
        train_mask = res.case_id == cid & res.scenario_id ~= holdout;
        hold_mask = res.case_id == cid & res.scenario_id == holdout;
        rmask = results.case_id == cid;
        success_count = sum(results.opf_success(rmask) == 1);
        if success_count < numel(scenario_ids)
            continue;
        end
        train_score = sum(res.fixed_scale_objective_term(train_mask), 'omitnan');
        hold_score = sum(res.fixed_scale_objective_term(hold_mask), 'omitnan');
        r_hold = results(results.case_id == cid & results.scenario_id == holdout, :);
        row = table(cid, holdout, train_score, hold_score, ...
            r_hold.classic_interface_objective(1), r_hold.zone_j_equiv_pg_mw(1), ...
            r_hold.s4_equiv_pg_mw(1), r_hold.max_abs_interface_residual_mw(1), ...
            'VariableNames', {'case_id','holdout_scenario_id', ...
            'train_fixed_scale_objective','holdout_fixed_scale_objective', ...
            'holdout_classic_interface_objective','holdout_zone_j_equiv_pg_mw', ...
            'holdout_s4_equiv_pg_mw','holdout_max_abs_interface_residual_mw'});
        train_scores = append_table(train_scores, row);
    end
    if height(train_scores) > 0
        [~, idx] = min(train_scores.train_fixed_scale_objective);
        holdout_rows = append_table(holdout_rows, train_scores(idx, :));
    end
end
end

function scale = scale_for_interface(scales, name, min_scale)
idx = find(scales.interface_name == name, 1);
if isempty(idx) || ~isfinite(scales.fixed_scale_mw(idx)) || scales.fixed_scale_mw(idx) <= 0
    scale = min_scale;
else
    scale = max(min_scale, scales.fixed_scale_mw(idx));
end
end

function [classic_J, classic_detail, balanced_J, balanced_detail] = interface_scores(scenario_id, results, options)
targets = read_public_interface_targets(scenario_id, options.interface_target_file);
flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
[classic_J, classic_detail] = interface_target_objective(flows, targets);
[balanced_J, balanced_detail] = interface_target_objective_balanced(flows, targets, ...
    struct('min_scale_mw', options.balanced_min_scale_mw, ...
    'scale_file', options.interface_scale_file));
end

function devices = all_devices(results)
zone_j_devices = device_structs(results, 'zone_j');
s4_devices = device_structs(results, 's4');
devices = [zone_j_devices(:); s4_devices(:)];
end

function devices = device_structs(results, group)
devices = struct('device_group', {}, 'name', {}, 'zone', {}, 'bus_id', {}, ...
    'bus_name', {}, 'gen_index', {});
if ~isfield(results, 'userdata') || ~isfield(results.userdata, 'ny_lite'), return; end
if strcmp(group, 'zone_j')
    field = 'zone_j_equivalent_supply';
    device_group = 'zone_j_equivalent';
else
    field = 's4_zonal_capability_equivalents';
    device_group = 's4_zonal_capability_equivalent';
end
if ~isfield(results.userdata.ny_lite, field), return; end
src = results.userdata.ny_lite.(field);
for k = 1:numel(src)
    devices(end + 1) = struct('device_group', device_group, ...
        'name', src(k).name, 'zone', src(k).zone, 'bus_id', src(k).bus_id, ...
        'bus_name', src(k).bus_name, 'gen_index', src(k).gen_index); %#ok<AGROW>
end
end

function [pg, pmax] = device_group_sum(results, group)
define_constants;
idx = device_indices(results, group);
idx = idx(idx >= 1 & idx <= size(results.gen, 1));
pg = sum(results.gen(idx, PG));
pmax = sum(results.gen(idx, PMAX));
end

function [pg, pmax] = device_zone_sum(results, zone)
define_constants;
devices = all_devices(results);
idx = [];
for k = 1:numel(devices)
    if string(devices(k).device_group) == "s4_zonal_capability_equivalent" && ...
            string(devices(k).zone) == zone
        idx(end + 1) = devices(k).gen_index; %#ok<AGROW>
    end
end
idx = idx(idx >= 1 & idx <= size(results.gen, 1));
pg = sum(results.gen(idx, PG));
pmax = sum(results.gen(idx, PMAX));
end

function idx = device_indices(results, group)
devices = all_devices(results);
idx = [];
for k = 1:numel(devices)
    if string(devices(k).device_group) == group
        idx(end + 1) = devices(k).gen_index; %#ok<AGROW>
    end
end
idx = idx(:);
end

function idx = boundary_generator_indices(results)
idx = [];
if isfield(results, 'userdata') && isfield(results.userdata, 'ny_only_equivalent') && ...
        isfield(results.userdata.ny_only_equivalent, 'external_equivalent_generators')
    tbl = results.userdata.ny_only_equivalent.external_equivalent_generators;
    if istable(tbl) && ismember('added_gen_index', tbl.Properties.VariableNames)
        idx = tbl.added_gen_index(:);
    end
end
end

function bus_ids = zone_bus_ids(results, zone)
bus_ids = [];
for i = 1:size(results.bus, 1)
    if isfield(results.userdata, 'nyiso_physical_zone') && ...
            numel(results.userdata.nyiso_physical_zone) >= i && ...
            strcmp(string(results.userdata.nyiso_physical_zone{i}), string(zone))
        bus_ids(end + 1) = results.bus(i, 1); %#ok<AGROW>
    end
end
end

function out = residual_map(detail)
out = struct('central_east', NaN, 'total_east', NaN, 'upny_coned', NaN, ...
    'dunwoodie_south', NaN, 'moses_south', NaN);
for k = 1:height(detail)
    name = string(detail.interface_name(k));
    switch name
        case "Central_East"
            out.central_east = detail.residual_mw(k);
        case "Total_East_proxy"
            out.total_east = detail.residual_mw(k);
        case "UPNY_ConEd"
            out.upny_coned = detail.residual_mw(k);
        case "Dunwoodie_South"
            out.dunwoodie_south = detail.residual_mw(k);
        case "Moses_South"
            out.moses_south = detail.residual_mw(k);
    end
end
end

function value = ext_sum(tbl, name)
if istable(tbl) && ismember(name, tbl.Properties.VariableNames)
    value = sum(tbl.(name));
else
    value = NaN;
end
end

function info = raw_info(results)
if isfield(results, 'raw') && isfield(results.raw, 'info')
    info = results.raw.info;
else
    info = NaN;
end
end

function value = interface_flow(flows, name)
idx = find(strcmp({flows.interface_name}, name), 1);
if isempty(idx), value = NaN; else, value = flows(idx).flow_mw; end
end

function value = safe_div(num, den)
if den == 0
    value = NaN;
else
    value = num / den;
end
end

function out = append_table(out, row)
if isempty(row), return; end
if isempty(out)
    out = row;
else
    out = [out; row]; %#ok<AGROW>
end
end
