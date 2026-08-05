function outputs = run_s3_interface_calibration_sweep(options)
%RUN_S3_INTERFACE_CALIBRATION_SWEEP First S3 interface-behavior calibration.
%
%   Uses PUBLIC_PQ_PUBLIC_EXTERNAL as the calibration target mode:
%   public NYISO P/Q zonal load plus public external schedule. The sweep is
%   diagnostic/calibration-prep, not a final optimizer.

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
    options.result_file = fullfile(helper_dir, 's3_interface_calibration_results.csv');
end
if ~isfield(options, 'residual_file')
    options.residual_file = fullfile(helper_dir, 's3_interface_calibration_residuals.csv');
end
if ~isfield(options, 'summary_file')
    options.summary_file = fullfile(helper_dir, 's3_interface_calibration_case_summary.csv');
end
if ~isfield(options, 'candidate_case_file')
    options.candidate_case_file = fullfile(case_dir, ...
        'npcc_ny_lite_s3_interface_calibration_candidate.m');
end
if ~isfield(options, 'archive_dir')
    options.archive_dir = fullfile(helper_dir, 'archives');
end
if ~isfield(options, 'zone_j_pmax_default_mw'), options.zone_j_pmax_default_mw = 3000; end
if ~isfield(options, 'zone_j_pmax_sensitivity_mw'), options.zone_j_pmax_sensitivity_mw = 3500; end
if ~isfield(options, 'zone_j_cost_c1'), options.zone_j_cost_c1 = 250; end
if ~isfield(options, 'zone_j_rho_default'), options.zone_j_rho_default = 0.02; end
if ~isfield(options, 'rho_sweep'), options.rho_sweep = [0 0.005 0.02 0.08 0.2 0.5]; end
if ~isfield(options, 'x_sweep'), options.x_sweep = [1.0 0.75 0.50 0.25]; end
if ~isfield(options, 'combined_rho_grid'), options.combined_rho_grid = [0.005 0.02 0.08 0.2 0.5]; end
if ~isfield(options, 'combined_x_grid'), options.combined_x_grid = [1.0 0.75 0.50 0.25]; end
if ~isfield(options, 'q_abs_ratio'), options.q_abs_ratio = 0; end
if ~isfield(options, 'load_mode'), options.load_mode = "PUBLIC_PQ_PUBLIC_EXTERNAL"; end
if ~isfield(options, 'make_archive'), options.make_archive = true; end

public_scenarios = readtable(fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
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
for c = 1:numel(cases)
    spec = cases(c);
    for s = 1:height(public_scenarios)
        scenario_id = string(public_scenarios.scenario_id(s));
        [row, residuals] = run_one(scenario_id, spec, mpopt, options);
        result_rows = [result_rows; row]; %#ok<AGROW>
        residual_rows = [residual_rows; residuals]; %#ok<AGROW>
    end
end

summary_rows = summarize_cases(result_rows);
writetable(result_rows, options.result_file);
writetable(residual_rows, options.residual_file);
writetable(summary_rows, options.summary_file);

best = select_best_combined(summary_rows);
if ~isempty(best)
    save_candidate_case(best, options.candidate_case_file, options);
end

archive_file = "";
if options.make_archive
    if exist(options.archive_dir, 'dir') ~= 7, mkdir(options.archive_dir); end
    stamp = string(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
    archive_file = fullfile(options.archive_dir, ...
        "s3_interface_calibration_results_" + stamp + ".zip");
    files = {options.result_file, options.residual_file, options.summary_file, ...
        options.candidate_case_file, ...
        fullfile(helper_dir, 'run_s3_interface_calibration_sweep.m'), ...
        fullfile(helper_dir, 'add_zone_j_equivalent_supply.m'), ...
        fullfile(helper_dir, 'add_ny_downstate_delivery_spine.m'), ...
        fullfile(helper_dir, 'scale_ny_downstate_delivery_spine_impedance.m'), ...
        fullfile(helper_dir, 'read_public_interface_targets.m'), ...
        fullfile(helper_dir, 'interface_target_objective.m'), ...
        fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
        fullfile(helper_dir, 'ny_zonal_load_targets.csv'), ...
        fullfile(helper_dir, 'ny_external_interface_targets.csv'), ...
        fullfile(helper_dir, 'nyiso_public_interface_targets.csv'), ...
        fullfile(case_dir, 'npcc_ny_lite_s3_zone_j_supply_equivalent_uncalibrated.m')};
    files = files(cellfun(@(f) exist(f, 'file') == 2, files));
    zip(archive_file, files);
end

outputs = struct('result_file', options.result_file, ...
    'residual_file', options.residual_file, ...
    'summary_file', options.summary_file, ...
    'candidate_case_file', options.candidate_case_file, ...
    'archive_file', archive_file, ...
    'result_row_count', height(result_rows), ...
    'residual_row_count', height(residual_rows), ...
    'summary_row_count', height(summary_rows));
end

function cases = calibration_cases(options)
cases = struct('case_id', {}, 'case_group', {}, 'zone_j_pmax_mw', {}, ...
    'zone_j_cost_c1', {}, 'rho_j_cost_c2', {}, 'x_spine_multiplier', {}, ...
    'x_gl_multiplier', {});
cases(end + 1) = make_case("BASE_3GW_NO_INTERFACE_OBJECTIVE", "baseline", ...
    options.zone_j_pmax_default_mw, options.zone_j_cost_c1, ...
    options.zone_j_rho_default, 1.0, 1.0);
for k = 1:numel(options.rho_sweep)
    rho = options.rho_sweep(k);
    cases(end + 1) = make_case("RHO_SWEEP_3GW_RHO_" + rho_token(rho), ...
        "rho_sweep", options.zone_j_pmax_default_mw, options.zone_j_cost_c1, ...
        rho, 1.0, 1.0); %#ok<AGROW>
end
for k = 1:numel(options.x_sweep)
    x = options.x_sweep(k);
    cases(end + 1) = make_case("SPINE_X_SWEEP_3GW_X_" + rho_token(x), ...
        "spine_x_sweep", options.zone_j_pmax_default_mw, options.zone_j_cost_c1, ...
        options.zone_j_rho_default, x, 1.0); %#ok<AGROW>
end
for r = 1:numel(options.combined_rho_grid)
    for xk = 1:numel(options.combined_x_grid)
        rho = options.combined_rho_grid(r);
        x = options.combined_x_grid(xk);
        cases(end + 1) = make_case("COMBINED_RHO_X_3GW_RHO_" + ...
            rho_token(rho) + "_X_" + rho_token(x), ...
            "combined_rho_x", options.zone_j_pmax_default_mw, ...
            options.zone_j_cost_c1, rho, x, 1.0); %#ok<AGROW>
    end
end
cases(end + 1) = make_case("SENSITIVITY_3P5GW_DEFAULT", "pmax_sensitivity", ...
    options.zone_j_pmax_sensitivity_mw, options.zone_j_cost_c1, ...
    options.zone_j_rho_default, 1.0, 1.0);
end

function spec = make_case(case_id, case_group, pmax, c1, rho, x_spine, x_gl)
spec = struct('case_id', string(case_id), 'case_group', string(case_group), ...
    'zone_j_pmax_mw', pmax, 'zone_j_cost_c1', c1, ...
    'rho_j_cost_c2', rho, 'x_spine_multiplier', x_spine, ...
    'x_gl_multiplier', x_gl);
end

function token = rho_token(value)
token = replace(string(sprintf('%.5g', value)), ".", "p");
end

function [row, residual_rows] = run_one(scenario_id, spec, mpopt, options)
define_constants;
status = "ok";
note = "";
ext_report = table();
scale_report = table();
try
    base = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
    [mpc, ~] = build_ny_only_equivalent_case(base);
    [mpc, ~] = add_ny_downstate_delivery_spine(mpc, 'full');
    [mpc, scale_report] = scale_ny_downstate_delivery_spine_impedance(mpc, ...
        spec.x_spine_multiplier, struct('include_gilboa_leeds', false));
    mpc = apply_public_pq_load(mpc, scenario_id);
    [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
        scenario_id, struct('target_file', options.target_file));
    [mpc, ~] = add_zone_j_equivalent_supply(mpc, ...
        struct('total_pmax_mw', spec.zone_j_pmax_mw, ...
        'q_abs_ratio', options.q_abs_ratio, ...
        'cost_c1', spec.zone_j_cost_c1, ...
        'cost_c2', spec.rho_j_cost_c2));
    results = runopf(mpc, mpopt);
catch ME
    results = struct();
    status = "error";
    note = string(regexprep(ME.message, '\s+', ' '));
end
row = summarize_result(scenario_id, spec, status, note, results, ext_report, ...
    scale_report, options);
residual_rows = summarize_residuals(scenario_id, spec, status, results, options);
end

function mpc = apply_public_pq_load(mpc, scenario_id)
[mpc, ~] = apply_nyiso_zonal_loads(mpc, scenario_id, 1.0, ...
    struct('preserve_total_ny_load', true));
mpc = attach_nyiso_zone_metadata(mpc);
end

function row = summarize_result(scenario_id, spec, status, note, results, ext_report, ...
    scale_report, options)
define_constants;
names = result_columns();
if strcmp(status, "error") || ~isfield(results, 'bus')
    values = num2cell(NaN(1, numel(names) - 13));
    row = table(spec.case_id, spec.case_group, string(scenario_id), ...
        string(options.load_mode), spec.zone_j_pmax_mw, spec.zone_j_cost_c1, ...
        spec.rho_j_cost_c2, spec.x_spine_multiplier, spec.x_gl_multiplier, ...
        options.q_abs_ratio, string(status), string(note), height(scale_report), ...
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
[J, detail] = interface_objective_detail(scenario_id, results, options);
[j_pg, j_pmax, j_count] = zone_j_sums(results);
res = residual_map(detail);
row = table(spec.case_id, spec.case_group, string(scenario_id), ...
    string(options.load_mode), spec.zone_j_pmax_mw, spec.zone_j_cost_c1, ...
    spec.rho_j_cost_c2, spec.x_spine_multiplier, spec.x_gl_multiplier, ...
    options.q_abs_ratio, string(status), string(note), height(scale_report), ...
    double(results.success), raw_info(results), results.f, J, ...
    max(abs(detail.residual_mw), [], 'omitnan'), ...
    mean(abs(detail.residual_mw), 'omitnan'), ...
    size(results.bus, 1), size(results.branch, 1), size(results.gen, 1), ...
    sum(results.bus(:, PD)), sum(results.bus(:, QD)), ...
    sum(results.gen(online, PG)), sum(results.gen(online, QG)), ...
    ext_sum(ext_report, 'target_flow_mw'), ext_sum(ext_report, 'target_q_mvar'), ...
    j_count, j_pg, j_pmax, safe_div(j_pg, j_pmax), ...
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
names = {'case_id','case_group','scenario_id','load_mode','zone_j_total_pmax_mw', ...
    'zone_j_cost_c1','rho_j_cost_c2','x_spine_multiplier','x_gl_multiplier', ...
    'zone_j_q_abs_ratio','status','note','scaled_branch_count','opf_success', ...
    'opf_raw_info','objective','interface_objective','max_abs_interface_residual_mw', ...
    'mean_abs_interface_residual_mw','bus_count','branch_count','gen_count', ...
    'total_pd_mw','total_qd_mvar','total_pg_mw','total_qg_mvar', ...
    'boundary_target_p_mw','boundary_target_q_mvar','zone_j_equiv_count', ...
    'zone_j_equiv_pg_mw','zone_j_equiv_pmax_mw','zone_j_fraction_pmax_used', ...
    'min_voltage','max_voltage','voltage_bound_count_high','voltage_bound_count_low', ...
    'branch_overload_count','max_branch_overload_mva','central_east_residual_mw', ...
    'total_east_residual_mw','upny_coned_residual_mw','dunwoodie_south_residual_mw', ...
    'moses_south_residual_mw','total_east_proxy_flow_mw','upny_coned_flow_mw', ...
    'dunwoodie_south_flow_mw'};
end

function residual_rows = summarize_residuals(scenario_id, spec, status, results, options)
residual_rows = table();
if strcmp(status, "error") || ~isfield(results, 'branch')
    return;
end
[J, detail] = interface_objective_detail(scenario_id, results, options);
for k = 1:height(detail)
    row = table(spec.case_id, spec.case_group, string(scenario_id), ...
        string(options.load_mode), spec.zone_j_pmax_mw, spec.rho_j_cost_c2, ...
        spec.x_spine_multiplier, detail.interface_name(k), ...
        detail.lite_flow_mw(k), detail.target_flow_mw(k), ...
        detail.residual_mw(k), detail.scale_mw(k), detail.objective_term(k), J, ...
        'VariableNames', {'case_id','case_group','scenario_id','load_mode', ...
        'zone_j_total_pmax_mw','rho_j_cost_c2','x_spine_multiplier', ...
        'interface_name','lite_flow_mw','target_flow_mw','residual_mw', ...
        'scale_mw','objective_term','interface_objective_total'});
    residual_rows = [residual_rows; row]; %#ok<AGROW>
end
end

function [J, detail] = interface_objective_detail(scenario_id, results, options)
targets = read_public_interface_targets(scenario_id, options.interface_target_file);
flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
[J, detail] = interface_target_objective(flows, targets);
end

function summary = summarize_cases(rows)
keys = unique(rows(:, {'case_id','case_group','zone_j_total_pmax_mw', ...
    'zone_j_cost_c1','rho_j_cost_c2','x_spine_multiplier','x_gl_multiplier'}), 'rows');
summary = table();
for k = 1:height(keys)
    mask = rows.case_id == keys.case_id(k);
    subset = rows(mask, :);
    row = table(keys.case_id(k), keys.case_group(k), keys.zone_j_total_pmax_mw(k), ...
        keys.zone_j_cost_c1(k), keys.rho_j_cost_c2(k), ...
        keys.x_spine_multiplier(k), keys.x_gl_multiplier(k), ...
        height(subset), sum(subset.opf_success == 1), ...
        sum(subset.interface_objective, 'omitnan'), ...
        mean(subset.interface_objective, 'omitnan'), ...
        max(subset.max_abs_interface_residual_mw, [], 'omitnan'), ...
        mean(subset.zone_j_equiv_pg_mw, 'omitnan'), ...
        max(subset.zone_j_equiv_pg_mw, [], 'omitnan'), ...
        max(subset.zone_j_fraction_pmax_used, [], 'omitnan'), ...
        max(subset.branch_overload_count, [], 'omitnan'), ...
        max(subset.voltage_bound_count_high + subset.voltage_bound_count_low, [], 'omitnan'), ...
        'VariableNames', {'case_id','case_group','zone_j_total_pmax_mw', ...
        'zone_j_cost_c1','rho_j_cost_c2','x_spine_multiplier','x_gl_multiplier', ...
        'scenario_count','success_count','sum_interface_objective', ...
        'mean_interface_objective','max_abs_interface_residual_mw', ...
        'mean_zone_j_equiv_pg_mw','max_zone_j_equiv_pg_mw', ...
        'max_zone_j_fraction_pmax_used','max_branch_overload_count', ...
        'max_voltage_bound_count'});
    summary = [summary; row]; %#ok<AGROW>
end
end

function best = select_best_combined(summary)
mask = summary.case_group == "combined_rho_x" & ...
    summary.success_count == summary.scenario_count;
subset = summary(mask, :);
if height(subset) == 0
    best = [];
    return;
end
[~, idx] = min(subset.sum_interface_objective);
best = subset(idx, :);
end

function save_candidate_case(best, case_file, options)
case_dir = fileparts(case_file);
if exist(case_dir, 'dir') ~= 7, mkdir(case_dir); end
fid = fopen(case_file, 'w');
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
if fid < 0
    error('run_s3_interface_calibration_sweep:CandidateWriteFailed', ...
        'Could not open %s for writing.', case_file);
end
[~, fname] = fileparts(case_file);
fprintf(fid, 'function mpc = %s\n', fname);
fprintf(fid, '%%NPCC_NY_LITE_S3_INTERFACE_CALIBRATION_CANDIDATE\n');
fprintf(fid, '%% Auto-generated by run_s3_interface_calibration_sweep.\n');
fprintf(fid, 'case_dir = fileparts(mfilename(''fullpath''));\n');
fprintf(fid, 'helper_dir = fullfile(case_dir, ''NY_Lite'');\n');
fprintf(fid, 'addpath(case_dir); addpath(helper_dir);\n');
fprintf(fid, 'mpc = loadcase(''npcc_ny_lite_s1_acopf_feasible_uncalibrated'');\n');
fprintf(fid, '[mpc, ~] = add_ny_downstate_delivery_spine(mpc, ''full'');\n');
fprintf(fid, '[mpc, ~] = scale_ny_downstate_delivery_spine_impedance(mpc, %.15g, struct(''include_gilboa_leeds'', false));\n', best.x_spine_multiplier);
fprintf(fid, '[mpc, ~] = add_zone_j_equivalent_supply(mpc, struct(''total_pmax_mw'', %.15g, ''q_abs_ratio'', %.15g, ''cost_c1'', %.15g, ''cost_c2'', %.15g));\n', ...
    best.zone_j_total_pmax_mw, options.q_abs_ratio, best.zone_j_cost_c1, best.rho_j_cost_c2);
fprintf(fid, 'mpc.userdata.ny_lite.interface_calibration_candidate = struct( ...\n');
fprintf(fid, '    ''case_id'', ''%s'', ...\n', char(best.case_id));
fprintf(fid, '    ''case_group'', ''%s'', ...\n', char(best.case_group));
fprintf(fid, '    ''zone_j_total_pmax_mw'', %.15g, ...\n', best.zone_j_total_pmax_mw);
fprintf(fid, '    ''zone_j_cost_c1'', %.15g, ...\n', best.zone_j_cost_c1);
fprintf(fid, '    ''rho_j_cost_c2'', %.15g, ...\n', best.rho_j_cost_c2);
fprintf(fid, '    ''x_spine_multiplier'', %.15g, ...\n', best.x_spine_multiplier);
fprintf(fid, '    ''sum_interface_objective'', %.15g, ...\n', best.sum_interface_objective);
fprintf(fid, '    ''success_count'', %.15g, ...\n', best.success_count);
fprintf(fid, '    ''scenario_count'', %.15g);\n', best.scenario_count);
fprintf(fid, 'mpc.userdata.ny_lite.interface_calibration_note = ''First behavior-calibration candidate selected by minimum public interface residual objective.'';\n');
fprintf(fid, 'end\n');
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

function [pg, pmax, count] = zone_j_sums(results)
define_constants;
pg = 0; pmax = 0; count = 0;
if ~isfield(results, 'userdata') || ~isfield(results.userdata, 'ny_lite') || ...
        ~isfield(results.userdata.ny_lite, 'zone_j_equivalent_supply')
    return;
end
devices = results.userdata.ny_lite.zone_j_equivalent_supply;
idx = [devices.gen_index];
idx = idx(idx >= 1 & idx <= size(results.gen, 1));
count = numel(idx);
if count == 0, return; end
pg = sum(results.gen(idx, PG));
pmax = sum(results.gen(idx, PMAX));
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
