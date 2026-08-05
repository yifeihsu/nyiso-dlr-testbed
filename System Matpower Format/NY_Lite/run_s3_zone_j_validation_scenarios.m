function outputs = run_s3_zone_j_validation_scenarios(options)
%RUN_S3_ZONE_J_VALIDATION_SCENARIOS Validate S3 under public P/Q scenarios.
%
%   Runs the full S2 spine plus Zone-J active-supply equivalent for:
%     PUBLIC_P_ONLY_S1_BOUNDARY
%     PUBLIC_Q_ONLY_S1_BOUNDARY
%     PUBLIC_PQ_S1_BOUNDARY
%     PUBLIC_PQ_PUBLIC_EXTERNAL
%
%   Outputs scenario summary, per-device Zone-J usage, and public P-32
%   interface residual tables.

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
if ~isfield(options, 'summary_file')
    options.summary_file = fullfile(helper_dir, 's3_zone_j_validation_summary.csv');
end
if ~isfield(options, 'usage_file')
    options.usage_file = fullfile(helper_dir, 's3_zone_j_equivalent_usage.csv');
end
if ~isfield(options, 'interface_file')
    options.interface_file = fullfile(helper_dir, 's3_public_interface_residuals.csv');
end
if ~isfield(options, 'archive_dir')
    options.archive_dir = fullfile(helper_dir, 'archives');
end
if ~isfield(options, 'zone_j_pmax_values_mw'), options.zone_j_pmax_values_mw = [3000 3500]; end
if ~isfield(options, 'x_multiplier'), options.x_multiplier = 1.0; end
if ~isfield(options, 'q_abs_ratio'), options.q_abs_ratio = 0; end
if ~isfield(options, 'make_archive'), options.make_archive = true; end

public_scenarios = readtable(fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
load_modes = ["PUBLIC_P_ONLY_S1_BOUNDARY", "PUBLIC_Q_ONLY_S1_BOUNDARY", ...
    "PUBLIC_PQ_S1_BOUNDARY", "PUBLIC_PQ_PUBLIC_EXTERNAL"];
mpopt = mpoption( ...
    'verbose', 0, ...
    'out.all', 0, ...
    'opf.ac.solver', 'IPOPT', ...
    'opf.flow_lim', 'S', ...
    'opf.violation', 1e-6, ...
    'opf.use_vg', 0, ...
    'opf.ignore_angle_lim', 0);

summary_rows = table();
usage_rows = table();
interface_rows = table();
for p = 1:numel(options.zone_j_pmax_values_mw)
    pmax_mw = options.zone_j_pmax_values_mw(p);
    for m = 1:numel(load_modes)
        load_mode = load_modes(m);
        for s = 1:height(public_scenarios)
            scenario_id = string(public_scenarios.scenario_id(s));
            [summary_row, usage, residuals] = run_one( ...
                scenario_id, load_mode, pmax_mw, mpopt, options);
            summary_rows = [summary_rows; summary_row]; %#ok<AGROW>
            usage_rows = [usage_rows; usage]; %#ok<AGROW>
            interface_rows = [interface_rows; residuals]; %#ok<AGROW>
        end
    end
end

writetable(summary_rows, options.summary_file);
writetable(usage_rows, options.usage_file);
writetable(interface_rows, options.interface_file);

archive_file = "";
if options.make_archive
    if exist(options.archive_dir, 'dir') ~= 7, mkdir(options.archive_dir); end
    stamp = string(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
    archive_file = fullfile(options.archive_dir, ...
        "s3_zone_j_validation_results_" + stamp + ".zip");
    files = {options.summary_file, options.usage_file, options.interface_file, ...
        fullfile(case_dir, 'npcc_ny_lite_s3_zone_j_supply_equivalent_uncalibrated.m'), ...
        fullfile(helper_dir, 'run_s3_zone_j_validation_scenarios.m'), ...
        fullfile(helper_dir, 'add_zone_j_equivalent_supply.m'), ...
        fullfile(helper_dir, 'add_ny_downstate_delivery_spine.m'), ...
        fullfile(helper_dir, 'scale_ny_downstate_delivery_spine_impedance.m'), ...
        fullfile(helper_dir, 'read_public_interface_targets.m'), ...
        fullfile(helper_dir, 'interface_target_objective.m'), ...
        fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
        fullfile(helper_dir, 'ny_zonal_load_targets.csv'), ...
        fullfile(helper_dir, 'ny_external_interface_targets.csv'), ...
        fullfile(helper_dir, 'nyiso_public_interface_targets.csv')};
    zip(archive_file, files);
end

outputs = struct('summary_file', options.summary_file, ...
    'usage_file', options.usage_file, ...
    'interface_file', options.interface_file, ...
    'archive_file', archive_file, ...
    'summary_row_count', height(summary_rows), ...
    'usage_row_count', height(usage_rows), ...
    'interface_row_count', height(interface_rows));
end

function [summary_row, usage_rows, residual_rows] = run_one(scenario_id, load_mode, ...
    pmax_mw, mpopt, options)
define_constants;
status = "ok";
note = "";
ext_report = table();
try
    base = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
    [mpc, ~] = build_ny_only_equivalent_case(base);
    [mpc, ~] = add_ny_downstate_delivery_spine(mpc, 'full');
    [mpc, scale_report] = scale_ny_downstate_delivery_spine_impedance(mpc, ...
        options.x_multiplier, struct('include_gilboa_leeds', false));
    mpc = apply_load_mode(mpc, scenario_id, load_mode);
    if endsWith(load_mode, "PUBLIC_EXTERNAL")
        ext_scenario = scenario_id;
    else
        ext_scenario = "S1_MEASURED_BOUNDARY";
    end
    [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
        ext_scenario, struct('target_file', options.target_file));
    [mpc, zone_j_report] = add_zone_j_equivalent_supply(mpc, ...
        struct('total_pmax_mw', pmax_mw, 'q_abs_ratio', options.q_abs_ratio));
    results = runopf(mpc, mpopt);
catch ME
    results = struct();
    scale_report = table();
    zone_j_report = table();
    status = "error";
    note = string(regexprep(ME.message, '\s+', ' '));
end

summary_row = summarize_result(scenario_id, load_mode, pmax_mw, status, note, ...
    results, ext_report, scale_report, options);
usage_rows = summarize_zone_j_usage(scenario_id, load_mode, pmax_mw, status, ...
    results, zone_j_report);
residual_rows = summarize_interface_residuals(scenario_id, load_mode, pmax_mw, ...
    status, results, options);
end

function mpc = apply_load_mode(mpc, scenario_id, load_mode)
define_constants;
s1_pd = mpc.bus(:, PD);
s1_qd = mpc.bus(:, QD);
[public_mpc, ~] = apply_nyiso_zonal_loads(mpc, scenario_id, 1.0, ...
    struct('preserve_total_ny_load', true));
switch string(load_mode)
    case "PUBLIC_P_ONLY_S1_BOUNDARY"
        mpc.bus(:, PD) = public_mpc.bus(:, PD);
        mpc.bus(:, QD) = s1_qd;
    case "PUBLIC_Q_ONLY_S1_BOUNDARY"
        mpc.bus(:, PD) = s1_pd;
        mpc.bus(:, QD) = public_mpc.bus(:, QD);
    case {"PUBLIC_PQ_S1_BOUNDARY", "PUBLIC_PQ_PUBLIC_EXTERNAL"}
        mpc.bus(:, PD) = public_mpc.bus(:, PD);
        mpc.bus(:, QD) = public_mpc.bus(:, QD);
    otherwise
        error('run_s3_zone_j_validation_scenarios:BadLoadMode', ...
            'Unknown load mode %s.', load_mode);
end
mpc = attach_nyiso_zone_metadata(mpc);
end

function row = summarize_result(scenario_id, load_mode, pmax_mw, status, note, ...
    results, ext_report, scale_report, options)
define_constants;
names = summary_columns();
if strcmp(status, "error") || ~isfield(results, 'bus')
    values = num2cell(NaN(1, numel(names) - 8));
    row = table(string(scenario_id), string(load_mode), pmax_mw, ...
        options.x_multiplier, options.q_abs_ratio, string(status), string(note), ...
        height(scale_report), values{:}, 'VariableNames', names);
    return;
end

online = results.gen(:, GEN_STATUS) > 0;
sf = sqrt(results.branch(:, PF).^2 + results.branch(:, QF).^2);
st = sqrt(results.branch(:, PT).^2 + results.branch(:, QT).^2);
smax = max(sf, st);
rate = results.branch(:, RATE_A);
rated = rate > 0;
flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
[j_pg, j_qg, j_pmax, j_count, rav_pg, ak_pg, goethals_pg] = zone_j_sums(results);
[J, max_abs_residual, mean_abs_residual] = interface_metrics(scenario_id, results);

row = table(string(scenario_id), string(load_mode), pmax_mw, ...
    options.x_multiplier, options.q_abs_ratio, string(status), string(note), ...
    height(scale_report), double(results.success), raw_info(results), results.f, ...
    interface_metrics_value(J), max_abs_residual, mean_abs_residual, ...
    size(results.bus, 1), size(results.branch, 1), size(results.gen, 1), ...
    sum(results.bus(:, PD)), sum(results.bus(:, QD)), ...
    sum(results.gen(online, PG)), sum(results.gen(online, QG)), ...
    ext_sum(ext_report, 'target_flow_mw'), ext_sum(ext_report, 'target_q_mvar'), ...
    j_count, j_pg, j_qg, j_pmax, safe_div(j_pg, j_pmax), ...
    rav_pg, ak_pg, goethals_pg, ...
    min(results.bus(:, VM)), max(results.bus(:, VM)), ...
    sum(results.bus(:, VM) >= results.bus(:, VMAX) - 1e-5), ...
    sum(results.bus(:, VM) <= results.bus(:, VMIN) + 1e-5), ...
    sum(rated & smax > rate + 1e-6), max([0; smax(rated) - rate(rated)]), ...
    interface_flow(flows, 'Total_East_proxy'), ...
    interface_flow(flows, 'UPNY_ConEd'), ...
    interface_flow(flows, 'Millwood_South'), ...
    interface_flow(flows, 'Dunwoodie_South'), ...
    interface_flow(flows, 'ConEd_LIPA_IK') + interface_flow(flows, 'ConEd_LIPA_JK'), ...
    'VariableNames', names);
end

function names = summary_columns()
names = {'scenario_id','load_mode','zone_j_total_pmax_mw','x_multiplier', ...
    'zone_j_q_abs_ratio','status','note','scaled_branch_count', ...
    'opf_success','opf_raw_info','objective','interface_objective', ...
    'max_abs_interface_residual_mw','mean_abs_interface_residual_mw', ...
    'bus_count','branch_count','gen_count','total_pd_mw','total_qd_mvar', ...
    'total_pg_mw','total_qg_mvar','boundary_target_p_mw', ...
    'boundary_target_q_mvar','zone_j_equiv_count','zone_j_equiv_pg_mw', ...
    'zone_j_equiv_qg_mvar','zone_j_equiv_pmax_mw','zone_j_fraction_pmax_used', ...
    'rav_a3_j_eq_pg_mw','ak3_j_eq_pg_mw','goethals_j_eq_pg_mw', ...
    'min_voltage','max_voltage','at_vmax_count','at_vmin_count', ...
    'rate_a_overload_count','max_rate_a_overload_mva', ...
    'total_east_proxy_flow_mw','upny_coned_flow_mw', ...
    'millwood_south_flow_mw','dunwoodie_south_flow_mw', ...
    'coned_lipa_total_flow_mw'};
end

function rows = summarize_zone_j_usage(scenario_id, load_mode, pmax_mw, status, ...
    results, zone_j_report)
define_constants;
rows = table();
if strcmp(status, "error") || ~isfield(results, 'gen') || height(zone_j_report) == 0
    return;
end
for k = 1:height(zone_j_report)
    gi = zone_j_report.gen_index(k);
    pg = results.gen(gi, PG);
    qg = results.gen(gi, QG);
    pmax = results.gen(gi, PMAX);
    row = table(string(scenario_id), string(load_mode), pmax_mw, ...
        string(zone_j_report.name(k)), zone_j_report.bus_id(k), ...
        string(zone_j_report.bus_name(k)), ...
        string(zone_j_report.proxy_interpretation(k)), gi, ...
        pg, qg, pmax, safe_div(pg, pmax), ...
        'VariableNames', {'scenario_id','load_mode','zone_j_total_pmax_mw', ...
        'device_name','bus_id','bus_name','proxy_interpretation', ...
        'gen_index','pg_mw','qg_mvar','pmax_mw','fraction_pmax_used'});
    rows = [rows; row]; %#ok<AGROW>
end
end

function rows = summarize_interface_residuals(scenario_id, load_mode, pmax_mw, ...
    status, results, options)
rows = table();
if strcmp(status, "error") || ~isfield(results, 'branch')
    return;
end
targets = read_public_interface_targets(scenario_id, options.interface_target_file);
flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
[J, detail] = interface_target_objective(flows, targets);
for k = 1:height(detail)
    target_idx = find(strcmp(string(targets.interface_name), detail.interface_name(k)), 1);
    if isempty(target_idx)
        target_limit = NaN;
        util = NaN;
    else
        target_limit = targets.target_limit_mw(target_idx);
        util = targets.nyiso_utilization(target_idx);
    end
    row = table(string(scenario_id), string(load_mode), pmax_mw, ...
        detail.interface_name(k), detail.lite_flow_mw(k), ...
        detail.target_flow_mw(k), detail.residual_mw(k), ...
        detail.scale_mw(k), detail.objective_term(k), J, ...
        target_limit, util, ...
        'VariableNames', {'scenario_id','load_mode','zone_j_total_pmax_mw', ...
        'interface_name','lite_flow_mw','target_flow_mw','residual_mw', ...
        'scale_mw','objective_term','interface_objective_total', ...
        'target_limit_mw','nyiso_utilization'});
    rows = [rows; row]; %#ok<AGROW>
end
end

function [J, max_abs_residual, mean_abs_residual] = interface_metrics(scenario_id, results)
try
    targets = read_public_interface_targets(scenario_id);
    flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
    [J, detail] = interface_target_objective(flows, targets);
    max_abs_residual = max(abs(detail.residual_mw), [], 'omitnan');
    mean_abs_residual = mean(abs(detail.residual_mw), 'omitnan');
catch
    J = NaN;
    max_abs_residual = NaN;
    mean_abs_residual = NaN;
end
end

function value = interface_metrics_value(value)
if isempty(value), value = NaN; end
end

function [pg, qg, pmax, count, rav_pg, ak_pg, goethals_pg] = zone_j_sums(results)
define_constants;
pg = 0; qg = 0; pmax = 0; count = 0;
rav_pg = NaN; ak_pg = NaN; goethals_pg = NaN;
if ~isfield(results, 'userdata') || ~isfield(results.userdata, 'ny_lite') || ...
        ~isfield(results.userdata.ny_lite, 'zone_j_equivalent_supply')
    return;
end
devices = results.userdata.ny_lite.zone_j_equivalent_supply;
if isempty(devices), return; end
idx = [devices.gen_index];
idx = idx(idx >= 1 & idx <= size(results.gen, 1));
count = numel(idx);
if count == 0, return; end
pg = sum(results.gen(idx, PG));
qg = sum(results.gen(idx, QG));
pmax = sum(results.gen(idx, PMAX));
rav_pg = device_pg(results, devices, 'RAV_A3_J_EQ_SUPPLY');
ak_pg = device_pg(results, devices, 'AK3_J_EQ_SUPPLY');
goethals_pg = device_pg(results, devices, 'GOETHALS_J_EQ_SUPPLY');
end

function pg = device_pg(results, devices, name)
define_constants;
pg = NaN;
idx = find(strcmp({devices.name}, name), 1);
if isempty(idx), return; end
gi = devices(idx).gen_index;
if gi >= 1 && gi <= size(results.gen, 1)
    pg = results.gen(gi, PG);
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
