function outputs = run_s4_cost_penalty_calibration_sweep(options)
%RUN_S4_COST_PENALTY_CALIBRATION_SWEEP Sweep S4 equivalent costs and caps.
%
%   This is a behavior-calibration sweep. Interface targets are scored after
%   each ACOPF using both the original target-flow scale and the balanced
%   target-limit scale. The interface objective is not yet embedded as an
%   ACOPF nonlinear cost.

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
if ~isfield(options, 'result_file')
    options.result_file = fullfile(helper_dir, 's4_cost_penalty_calibration_results.csv');
end
if ~isfield(options, 'residual_file')
    options.residual_file = fullfile(helper_dir, 's4_cost_penalty_calibration_residuals.csv');
end
if ~isfield(options, 'device_file')
    options.device_file = fullfile(helper_dir, 's4_cost_penalty_device_dispatch.csv');
end
if ~isfield(options, 'summary_file')
    options.summary_file = fullfile(helper_dir, 's4_cost_penalty_calibration_summary.csv');
end
if ~isfield(options, 'candidate_case_file')
    options.candidate_case_file = fullfile(case_dir, ...
        'npcc_ny_lite_s4_generation_aligned_candidate_v1.m');
end
if ~isfield(options, 'archive_dir')
    options.archive_dir = fullfile(helper_dir, 'archives');
end
if ~isfield(options, 'zone_j_c1_grid'), options.zone_j_c1_grid = [120 150 180 220 250]; end
if ~isfield(options, 's4_c1_grid'), options.s4_c1_grid = [160 180 220 260]; end
if ~isfield(options, 'abc_cap_factor_grid'), options.abc_cap_factor_grid = [0.80 0.90 1.00 1.10]; end
if ~isfield(options, 'x_spine_grid'), options.x_spine_grid = [1.00 0.75]; end
if ~isfield(options, 'zone_j_c2'), options.zone_j_c2 = 0.02; end
if ~isfield(options, 's4_c2'), options.s4_c2 = 0.02; end
if ~isfield(options, 'include_zone_split_sensitivity'), options.include_zone_split_sensitivity = true; end
if ~isfield(options, 'voltage_penalty_rho'), options.voltage_penalty_rho = 0; end
if ~isfield(options, 'balanced_min_scale_mw'), options.balanced_min_scale_mw = 500; end
if ~isfield(options, 'interface_scale_file')
    options.interface_scale_file = fullfile(helper_dir, 'nyiso_interface_objective_scales.csv');
end
if ~isfield(options, 'make_archive'), options.make_archive = true; end

build_s4_generation_alignment_targets();
build_s4_interface_objective_scales(struct('scale_file', options.interface_scale_file, ...
    'min_scale_mw', options.balanced_min_scale_mw));
scenarios = readtable(fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
cases = calibration_cases(options);

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
for c = 1:numel(cases)
    spec = cases(c);
    for s = 1:height(scenarios)
        scenario_id = string(scenarios.scenario_id(s));
        [row, residuals, devices] = run_one(scenario_id, spec, mpopt, options);
        result_rows = append_table(result_rows, row);
        residual_rows = append_table(residual_rows, residuals);
        device_rows = append_table(device_rows, devices);
    end
end

summary_rows = summarize_cases(result_rows, device_rows);
writetable(result_rows, options.result_file);
writetable(residual_rows, options.residual_file);
writetable(device_rows, options.device_file);
writetable(summary_rows, options.summary_file);

best = select_candidate(summary_rows);
if ~isempty(best)
    save_candidate_case(best, options.candidate_case_file, options);
end

archive_file = "";
if options.make_archive
    if exist(options.archive_dir, 'dir') ~= 7, mkdir(options.archive_dir); end
    stamp = string(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
    archive_file = fullfile(options.archive_dir, ...
        "s4_cost_penalty_calibration_results_" + stamp + ".zip");
    files = {options.result_file, options.residual_file, options.device_file, ...
        options.summary_file, options.candidate_case_file, ...
        fullfile(helper_dir, 'run_s4_cost_penalty_calibration_sweep.m'), ...
        fullfile(helper_dir, 'interface_target_objective_balanced.m'), ...
        fullfile(helper_dir, 'build_s4_interface_objective_scales.m'), ...
        fullfile(helper_dir, 's4_interface_objective_opf_note.md'), ...
        fullfile(helper_dir, 'add_s4_zonal_capability_equivalents.m'), ...
        fullfile(helper_dir, 'build_s4_generation_alignment_targets.m'), ...
        fullfile(helper_dir, 'add_zone_j_equivalent_supply.m'), ...
        fullfile(helper_dir, 'add_ny_downstate_delivery_spine.m'), ...
        fullfile(helper_dir, 'scale_ny_downstate_delivery_spine_impedance.m'), ...
        fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
        fullfile(helper_dir, 'ny_zonal_load_targets.csv'), ...
        fullfile(helper_dir, 'ny_external_interface_targets.csv'), ...
        fullfile(helper_dir, 'nyiso_public_interface_targets.csv'), ...
        fullfile(helper_dir, 'nyiso_generator_capability_targets.csv'), ...
        fullfile(helper_dir, 'nyiso_interface_objective_scales.csv'), ...
        fullfile(helper_dir, 'nyiso_zonal_generation_targets.csv')};
    files = files(cellfun(@(f) exist(f, 'file') == 2, files));
    zip(archive_file, files);
end

outputs = struct('result_file', options.result_file, ...
    'residual_file', options.residual_file, ...
    'device_file', options.device_file, ...
    'summary_file', options.summary_file, ...
    'candidate_case_file', options.candidate_case_file, ...
    'archive_file', archive_file, ...
    'case_count', numel(cases), ...
    'result_row_count', height(result_rows), ...
    'residual_row_count', height(residual_rows), ...
    'device_row_count', height(device_rows), ...
    'summary_row_count', height(summary_rows));
end

function cases = calibration_cases(options)
cases = struct('case_id', {}, 'case_group', {}, 'zone_j_c1', {}, ...
    'zone_j_c2', {}, 's4_e_c1', {}, 's4_f_c1', {}, 's4_g_c1', {}, ...
    's4_k_c1', {}, 's4_c2', {}, 'abc_cap_factor', {}, ...
    'x_spine_multiplier', {});
for j = options.zone_j_c1_grid
    for s4 = options.s4_c1_grid
        for cap = options.abc_cap_factor_grid
            for x = options.x_spine_grid
                cases(end + 1) = make_case("main_grid", j, s4, s4, s4, s4, ...
                    cap, x, options); %#ok<AGROW>
            end
        end
    end
end
if options.include_zone_split_sensitivity
    for j = [120 150 180]
        for g = [180 220]
            for k = [180 220 260]
                cases(end + 1) = make_case("gk_split", j, 180, 180, g, k, ...
                    1.0, 1.0, options); %#ok<AGROW>
            end
        end
    end
end
end

function spec = make_case(group, j, e, f, g, k, cap, x, options)
case_id = sprintf('S4_COST_%s_J%s_E%s_F%s_G%s_K%s_CAP%s_X%s', ...
    char(group), tok(j), tok(e), tok(f), tok(g), tok(k), tok(cap), tok(x));
spec = struct('case_id', string(case_id), 'case_group', string(group), ...
    'zone_j_c1', j, 'zone_j_c2', options.zone_j_c2, ...
    's4_e_c1', e, 's4_f_c1', f, 's4_g_c1', g, 's4_k_c1', k, ...
    's4_c2', options.s4_c2, 'abc_cap_factor', cap, ...
    'x_spine_multiplier', x);
end

function token = tok(v)
token = strrep(sprintf('%.4g', v), '.', 'p');
end

function [row, residual_rows, device_rows] = run_one(scenario_id, spec, mpopt, options)
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
        'zone_j_total_pmax_mw', 3000, ...
        'zone_j_cost_c1', spec.zone_j_c1, ...
        'zone_j_cost_c2', spec.zone_j_c2, ...
        'equiv_cost_c1', spec.s4_f_c1, ...
        'equiv_cost_c2', spec.s4_c2, ...
        'q_abs_ratio', 0, ...
        'apply_upstate_participation_caps', true, ...
        'abc_cap_factor', spec.abc_cap_factor, ...
        'reclassify_ce_ug', true));
    mpc = set_s4_zone_costs(mpc, spec);
    if options.voltage_penalty_rho > 0
        mpc = add_voltage_deviation_cost(mpc, options.voltage_penalty_rho, 1.0);
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
row = summarize_result(scenario_id, spec, status, note, results, scale_report, ...
    ext_report, add_report, options);
residual_rows = summarize_residuals(scenario_id, spec, status, results, options);
device_rows = summarize_device_dispatch(scenario_id, spec, status, results);
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
            c1 = spec.s4_e_c1;
        case "F"
            c1 = spec.s4_f_c1;
        case "G"
            c1 = spec.s4_g_c1;
        case "K"
            c1 = spec.s4_k_c1;
        otherwise
            c1 = spec.s4_f_c1;
    end
    mpc.gencost(gi, 5) = spec.s4_c2;
    mpc.gencost(gi, 6) = c1;
end
end

function row = summarize_result(scenario_id, spec, status, note, results, scale_report, ext_report, add_report, options)
define_constants;
names = result_columns();
if strcmp(status, "error") || ~isfield(results, 'bus')
    values = num2cell(NaN(1, numel(names) - 19));
    row = table(spec.case_id, spec.case_group, string(scenario_id), ...
        spec.zone_j_c1, spec.s4_e_c1, spec.s4_f_c1, spec.s4_g_c1, ...
        spec.s4_k_c1, spec.abc_cap_factor, spec.x_spine_multiplier, ...
        string(status), string(note), height(scale_report), height(add_report), ...
        ext_sum(ext_report, 'target_flow_mw'), ext_sum(ext_report, 'target_q_mvar'), ...
        values{:}, 'VariableNames', names);
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
[zj_pg, zj_pmax] = device_group_sum(results, "zone_j_equivalent");
[s4_pg, s4_pmax] = device_group_sum(results, "s4_zonal_capability_equivalent");
[s4_e_pg, ~] = device_zone_sum(results, "E");
[s4_f_pg, ~] = device_zone_sum(results, "F");
[s4_g_pg, ~] = device_zone_sum(results, "G");
[s4_k_pg, ~] = device_zone_sum(results, "K");
res = residual_map(balanced_detail);
row = table(spec.case_id, spec.case_group, string(scenario_id), ...
    spec.zone_j_c1, spec.s4_e_c1, spec.s4_f_c1, spec.s4_g_c1, ...
    spec.s4_k_c1, spec.abc_cap_factor, spec.x_spine_multiplier, ...
    string(status), string(note), height(scale_report), height(add_report), ...
    ext_sum(ext_report, 'target_flow_mw'), ext_sum(ext_report, 'target_q_mvar'), ...
    double(results.success), raw_info(results), results.f, classic_J, balanced_J, ...
    max(abs(balanced_detail.residual_mw), [], 'omitnan'), ...
    mean(abs(balanced_detail.residual_mw), 'omitnan'), ...
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
names = {'case_id','case_group','scenario_id','zone_j_cost_c1', ...
    's4_e_cost_c1','s4_f_cost_c1','s4_g_cost_c1','s4_k_cost_c1', ...
    'abc_cap_factor','x_spine_multiplier','status','note', ...
    'scaled_branch_count','added_device_count','boundary_target_p_mw', ...
    'boundary_target_q_mvar','opf_success','opf_raw_info','objective', ...
    'classic_interface_objective','balanced_interface_objective', ...
    'max_abs_interface_residual_mw','mean_abs_interface_residual_mw', ...
    'bus_count','branch_count','gen_count','total_pd_mw','total_qd_mvar', ...
    'total_pg_mw','total_qg_mvar','zone_j_equiv_pg_mw', ...
    'zone_j_equiv_pmax_mw','zone_j_fraction_pmax_used', ...
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
    if isempty(cidx)
        classic_term = NaN; classic_scale = NaN;
    else
        classic_term = classic_detail.objective_term(cidx);
        classic_scale = classic_detail.scale_mw(cidx);
    end
    row = table(spec.case_id, spec.case_group, string(scenario_id), ...
        spec.zone_j_c1, spec.s4_e_c1, spec.s4_f_c1, spec.s4_g_c1, ...
        spec.s4_k_c1, spec.abc_cap_factor, spec.x_spine_multiplier, ...
        cname, balanced_detail.lite_flow_mw(k), balanced_detail.target_flow_mw(k), ...
        balanced_detail.target_limit_mw(k), balanced_detail.residual_mw(k), ...
        classic_scale, classic_term, classic_J, balanced_detail.scale_mw(k), ...
        balanced_detail.objective_term(k), balanced_J, ...
        'VariableNames', {'case_id','case_group','scenario_id','zone_j_cost_c1', ...
        's4_e_cost_c1','s4_f_cost_c1','s4_g_cost_c1','s4_k_cost_c1', ...
        'abc_cap_factor','x_spine_multiplier','interface_name','lite_flow_mw', ...
        'target_flow_mw','target_limit_mw','residual_mw','classic_scale_mw', ...
        'classic_objective_term','classic_objective_total','balanced_scale_mw', ...
        'balanced_objective_term','balanced_objective_total'});
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
    row = table(spec.case_id, spec.case_group, string(scenario_id), ...
        spec.zone_j_c1, spec.s4_e_c1, spec.s4_f_c1, spec.s4_g_c1, ...
        spec.s4_k_c1, spec.abc_cap_factor, spec.x_spine_multiplier, ...
        string(devices(k).device_group), string(devices(k).name), ...
        string(devices(k).zone), devices(k).bus_id, string(devices(k).bus_name), ...
        gi, results.gen(gi, PG), results.gen(gi, QG), results.gen(gi, PMAX), ...
        results.gen(gi, PMIN), results.gen(gi, QMAX), results.gen(gi, QMIN), ...
        safe_div(results.gen(gi, PG), results.gen(gi, PMAX)), ...
        'VariableNames', {'case_id','case_group','scenario_id','zone_j_cost_c1', ...
        's4_e_cost_c1','s4_f_cost_c1','s4_g_cost_c1','s4_k_cost_c1', ...
        'abc_cap_factor','x_spine_multiplier','device_group','device_name', ...
        'zone','bus_id','bus_name','gen_index','pg_mw','qg_mvar','pmax_mw', ...
        'pmin_mw','qmax_mvar','qmin_mvar','fraction_pmax_used'});
    device_rows = append_table(device_rows, row);
end
end

function summary = summarize_cases(rows, device_rows)
keys = unique(rows(:, {'case_id','case_group','zone_j_cost_c1', ...
    's4_e_cost_c1','s4_f_cost_c1','s4_g_cost_c1','s4_k_cost_c1', ...
    'abc_cap_factor','x_spine_multiplier'}), 'rows');
summary = table();
for k = 1:height(keys)
    mask = rows.case_id == keys.case_id(k);
    subset = rows(mask, :);
    dmask = device_rows.case_id == keys.case_id(k);
    dsub = device_rows(dmask, :);
    zj = dsub.device_group == "zone_j_equivalent";
    s4 = dsub.device_group == "s4_zonal_capability_equivalent";
    score = sum(subset.balanced_interface_objective, 'omitnan');
    mean_zj = mean(subset.zone_j_equiv_pg_mw, 'omitnan');
    if mean_zj < 250
        dispatch_penalty = (250 - mean_zj) / 250;
    else
        dispatch_penalty = 0;
    end
    selection_score = score + dispatch_penalty;
    row = table(keys.case_id(k), keys.case_group(k), ...
        keys.zone_j_cost_c1(k), keys.s4_e_cost_c1(k), keys.s4_f_cost_c1(k), ...
        keys.s4_g_cost_c1(k), keys.s4_k_cost_c1(k), ...
        keys.abc_cap_factor(k), keys.x_spine_multiplier(k), ...
        height(subset), sum(subset.opf_success == 1), ...
        sum(subset.classic_interface_objective, 'omitnan'), ...
        sum(subset.balanced_interface_objective, 'omitnan'), ...
        mean(subset.balanced_interface_objective, 'omitnan'), ...
        max(subset.max_abs_interface_residual_mw, [], 'omitnan'), ...
        mean(subset.zone_j_equiv_pg_mw, 'omitnan'), ...
        max(subset.zone_j_equiv_pg_mw, [], 'omitnan'), ...
        mean(subset.s4_equiv_pg_mw, 'omitnan'), ...
        max(subset.s4_equiv_pg_mw, [], 'omitnan'), ...
        mean(subset.s4_g_equiv_pg_mw, 'omitnan'), ...
        mean(subset.s4_k_equiv_pg_mw, 'omitnan'), ...
        mean(dsub.pg_mw(zj), 'omitnan'), mean(dsub.pg_mw(s4), 'omitnan'), ...
        max(subset.branch_overload_count, [], 'omitnan'), ...
        max(subset.voltage_bound_count_high + subset.voltage_bound_count_low, [], 'omitnan'), ...
        dispatch_penalty, selection_score, ...
        'VariableNames', {'case_id','case_group','zone_j_cost_c1', ...
        's4_e_cost_c1','s4_f_cost_c1','s4_g_cost_c1','s4_k_cost_c1', ...
        'abc_cap_factor','x_spine_multiplier','scenario_count','success_count', ...
        'sum_classic_interface_objective','sum_balanced_interface_objective', ...
        'mean_balanced_interface_objective','max_abs_interface_residual_mw', ...
        'mean_zone_j_equiv_pg_mw','max_zone_j_equiv_pg_mw', ...
        'mean_s4_equiv_pg_mw','max_s4_equiv_pg_mw', ...
        'mean_s4_g_equiv_pg_mw','mean_s4_k_equiv_pg_mw', ...
        'mean_zone_j_device_pg_mw','mean_s4_device_pg_mw', ...
        'max_branch_overload_count','max_voltage_bound_count', ...
        'zone_j_zero_dispatch_penalty','selection_score'});
    summary = append_table(summary, row);
end
end

function best = select_candidate(summary)
mask = summary.success_count == summary.scenario_count & ...
    summary.mean_zone_j_equiv_pg_mw >= 250;
subset = summary(mask, :);
if height(subset) == 0
    subset = summary(summary.success_count == summary.scenario_count, :);
end
if height(subset) == 0
    best = [];
    return;
end
[~, idx] = min(subset.selection_score);
best = subset(idx, :);
end

function save_candidate_case(best, case_file, options)
case_dir = fileparts(case_file);
if exist(case_dir, 'dir') ~= 7, mkdir(case_dir); end
fid = fopen(case_file, 'w');
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
if fid < 0
    error('run_s4_cost_penalty_calibration_sweep:CandidateWriteFailed', ...
        'Could not open %s for writing.', case_file);
end
[~, fname] = fileparts(case_file);
fprintf(fid, 'function mpc = %s\n', fname);
fprintf(fid, '%%NPCC_NY_LITE_S4_GENERATION_ALIGNED_CANDIDATE_V1\n');
fprintf(fid, '%% Auto-generated by run_s4_cost_penalty_calibration_sweep.\n');
fprintf(fid, 'case_dir = fileparts(mfilename(''fullpath''));\n');
fprintf(fid, 'helper_dir = fullfile(case_dir, ''NY_Lite'');\n');
fprintf(fid, 'addpath(case_dir); addpath(helper_dir);\n');
fprintf(fid, 'mpc = loadcase(''npcc_ny_lite_s1_acopf_feasible_uncalibrated'');\n');
fprintf(fid, '[mpc, ~] = add_ny_downstate_delivery_spine(mpc, ''full'');\n');
fprintf(fid, '[mpc, ~] = scale_ny_downstate_delivery_spine_impedance(mpc, %.15g, struct(''include_gilboa_leeds'', false));\n', best.x_spine_multiplier);
fprintf(fid, '[mpc, ~] = add_s4_zonal_capability_equivalents(mpc, struct( ...\n');
fprintf(fid, '    ''include_zone_j'', true, ...\n');
fprintf(fid, '    ''zone_j_total_pmax_mw'', 3000, ...\n');
fprintf(fid, '    ''zone_j_cost_c1'', %.15g, ...\n', best.zone_j_cost_c1);
fprintf(fid, '    ''zone_j_cost_c2'', %.15g, ...\n', options.zone_j_c2);
fprintf(fid, '    ''equiv_cost_c1'', %.15g, ...\n', best.s4_f_cost_c1);
fprintf(fid, '    ''equiv_cost_c2'', %.15g, ...\n', options.s4_c2);
fprintf(fid, '    ''q_abs_ratio'', 0, ...\n');
fprintf(fid, '    ''apply_upstate_participation_caps'', true, ...\n');
fprintf(fid, '    ''abc_cap_factor'', %.15g, ...\n', best.abc_cap_factor);
fprintf(fid, '    ''reclassify_ce_ug'', true));\n');
fprintf(fid, 'mpc = local_set_s4_zone_costs(mpc, %.15g, %.15g, %.15g, %.15g, %.15g);\n', ...
    best.s4_e_cost_c1, best.s4_f_cost_c1, best.s4_g_cost_c1, best.s4_k_cost_c1, options.s4_c2);
fprintf(fid, 'mpc.userdata.ny_lite.s4_cost_penalty_candidate = struct( ...\n');
fprintf(fid, '    ''case_id'', ''%s'', ...\n', char(best.case_id));
fprintf(fid, '    ''sum_balanced_interface_objective'', %.15g, ...\n', best.sum_balanced_interface_objective);
fprintf(fid, '    ''mean_zone_j_equiv_pg_mw'', %.15g, ...\n', best.mean_zone_j_equiv_pg_mw);
fprintf(fid, '    ''mean_s4_equiv_pg_mw'', %.15g);\n', best.mean_s4_equiv_pg_mw);
fprintf(fid, 'mpc.userdata.ny_lite.s4_status = ''Generation-aligned cost/participation candidate; interface penalty still post-OPF scored, not embedded nonlinear OPF objective.'';\n');
fprintf(fid, 'end\n\n');
fprintf(fid, 'function mpc = local_set_s4_zone_costs(mpc, e, f, g, kcost, c2)\n');
fprintf(fid, 'devices = mpc.userdata.ny_lite.s4_zonal_capability_equivalents;\n');
fprintf(fid, 'for n = 1:numel(devices)\n');
fprintf(fid, '    gi = devices(n).gen_index;\n');
fprintf(fid, '    switch string(devices(n).zone)\n');
fprintf(fid, '        case \"E\", c1 = e;\n');
fprintf(fid, '        case \"F\", c1 = f;\n');
fprintf(fid, '        case \"G\", c1 = g;\n');
fprintf(fid, '        case \"K\", c1 = kcost;\n');
fprintf(fid, '        otherwise, c1 = f;\n');
fprintf(fid, '    end\n');
fprintf(fid, '    mpc.gencost(gi, 5) = c2;\n');
fprintf(fid, '    mpc.gencost(gi, 6) = c1;\n');
fprintf(fid, 'end\n');
fprintf(fid, 'end\n');
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
devices = all_devices(results);
idx = [];
for k = 1:numel(devices)
    if string(devices(k).device_group) == group
        idx(end + 1) = devices(k).gen_index; %#ok<AGROW>
    end
end
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
