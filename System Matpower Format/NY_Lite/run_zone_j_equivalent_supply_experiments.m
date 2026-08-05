function outputs = run_zone_j_equivalent_supply_experiments(options)
%RUN_ZONE_J_EQUIVALENT_SUPPLY_EXPERIMENTS Test bounded Zone-J supply model.
%
%   Case: full S2 spine, public P-only load at eta = 1.0, S1 boundary
%   equivalent fixed, normal voltage/rating constraints, IPOPT ACOPF.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'ny_external_interface_targets.csv');
end
if ~isfield(options, 'summary_file')
    options.summary_file = fullfile(helper_dir, 'zone_j_equivalent_supply_experiments.csv');
end
if ~isfield(options, 'aggregate_file')
    options.aggregate_file = fullfile(helper_dir, 'zone_j_equivalent_supply_summary.csv');
end
if ~isfield(options, 'case_file')
    options.case_file = fullfile(case_dir, ...
        'npcc_ny_lite_s3_zone_j_supply_equivalent_uncalibrated.m');
end
if ~isfield(options, 'archive_dir')
    options.archive_dir = fullfile(helper_dir, 'archives');
end
if ~isfield(options, 'zone_j_pmax_grid_mw'), options.zone_j_pmax_grid_mw = [0 3000 3500 4000]; end
if ~isfield(options, 'x_multipliers'), options.x_multipliers = [1.0 0.75 0.50 0.25]; end
if ~isfield(options, 'eta'), options.eta = 1.0; end
if ~isfield(options, 'q_abs_ratio'), options.q_abs_ratio = 0; end
if ~isfield(options, 'make_archive'), options.make_archive = true; end

public_scenarios = readtable(fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
mpopt = mpoption( ...
    'verbose', 0, ...
    'out.all', 0, ...
    'opf.ac.solver', 'IPOPT', ...
    'opf.flow_lim', 'S', ...
    'opf.violation', 1e-6, ...
    'opf.use_vg', 0, ...
    'opf.ignore_angle_lim', 0);

save_s3_case(options.case_file, options);

rows = table();
for xk = 1:numel(options.x_multipliers)
    x_multiplier = options.x_multipliers(xk);
    for pk = 1:numel(options.zone_j_pmax_grid_mw)
        total_pmax_mw = options.zone_j_pmax_grid_mw(pk);
        for s = 1:height(public_scenarios)
            scenario_id = string(public_scenarios.scenario_id(s));
            row = run_one(scenario_id, x_multiplier, total_pmax_mw, mpopt, options);
            rows = [rows; row]; %#ok<AGROW>
        end
    end
end

agg = aggregate_rows(rows);
writetable(rows, options.summary_file);
writetable(agg, options.aggregate_file);

archive_file = "";
if options.make_archive
    if exist(options.archive_dir, 'dir') ~= 7, mkdir(options.archive_dir); end
    stamp = string(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
    archive_file = fullfile(options.archive_dir, ...
        "zone_j_equivalent_supply_results_" + stamp + ".zip");
    files = {options.summary_file, options.aggregate_file, options.case_file, ...
        fullfile(helper_dir, 'run_zone_j_equivalent_supply_experiments.m'), ...
        fullfile(helper_dir, 'add_zone_j_equivalent_supply.m'), ...
        fullfile(helper_dir, 'add_ny_downstate_delivery_spine.m'), ...
        fullfile(helper_dir, 'scale_ny_downstate_delivery_spine_impedance.m'), ...
        fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
        fullfile(helper_dir, 'ny_zonal_load_targets.csv'), ...
        fullfile(helper_dir, 'ny_external_interface_targets.csv')};
    zip(archive_file, files);
end

outputs = struct('summary_file', options.summary_file, ...
    'aggregate_file', options.aggregate_file, ...
    'case_file', options.case_file, ...
    'archive_file', archive_file, ...
    'row_count', height(rows), ...
    'aggregate_row_count', height(agg));
end

function save_s3_case(case_file, options)
case_dir = fileparts(case_file);
if exist(case_dir, 'dir') ~= 7, mkdir(case_dir); end
mpc = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
[mpc, ~] = add_ny_downstate_delivery_spine(mpc, 'full');
[mpc, ~] = add_zone_j_equivalent_supply(mpc, ...
    struct('total_pmax_mw', 3500, 'q_abs_ratio', options.q_abs_ratio));
savecase(case_file, mpc);
end

function row = run_one(scenario_id, x_multiplier, total_pmax_mw, mpopt, options)
define_constants;
status = "ok";
note = "";
ext_report = table();
zone_j_report = table();
scale_report = table();
try
    base = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
    [mpc, ~] = build_ny_only_equivalent_case(base);
    [mpc, ~] = add_ny_downstate_delivery_spine(mpc, 'full');
    [mpc, scale_report] = scale_ny_downstate_delivery_spine_impedance(mpc, ...
        x_multiplier, struct('include_gilboa_leeds', false));
    mpc = apply_public_active_load_eta(mpc, scenario_id, options.eta);
    [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
        "S1_MEASURED_BOUNDARY", struct('target_file', options.target_file));
    if total_pmax_mw > 0
        [mpc, zone_j_report] = add_zone_j_equivalent_supply(mpc, ...
            struct('total_pmax_mw', total_pmax_mw, ...
            'q_abs_ratio', options.q_abs_ratio));
    end
    results = runopf(mpc, mpopt);
catch ME
    results = struct();
    mpc = struct();
    status = "error";
    note = string(regexprep(ME.message, '\s+', ' '));
end
row = summarize(scenario_id, x_multiplier, total_pmax_mw, status, note, ...
    mpc, results, ext_report, zone_j_report, scale_report, options);
end

function mpc = apply_public_active_load_eta(mpc, scenario_id, eta)
define_constants;
s1_pd = mpc.bus(:, PD);
s1_qd = mpc.bus(:, QD);
[public_mpc, ~] = apply_nyiso_zonal_loads(mpc, scenario_id, 1.0, ...
    struct('preserve_total_ny_load', true));
mpc.bus(:, PD) = (1 - eta) * s1_pd + eta * public_mpc.bus(:, PD);
mpc.bus(:, QD) = s1_qd;
mpc = attach_nyiso_zone_metadata(mpc);
end

function row = summarize(scenario_id, x_multiplier, total_pmax_mw, status, note, ...
    mpc, results, ext_report, zone_j_report, scale_report, options)
define_constants;
names = result_columns();
if strcmp(status, "error") || ~isfield(results, 'bus')
    values = num2cell(NaN(1, numel(names) - 8));
    row = table(string(scenario_id), x_multiplier, total_pmax_mw, ...
        options.q_abs_ratio, options.eta, string(status), string(note), ...
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
[j_pg, j_qg, j_pmax, j_count] = zone_j_sums(results);
added_branch_mask = false(size(results.branch, 1), 1);
if isfield(results.userdata, 'ny_lite') && ...
        isfield(results.userdata.ny_lite, 'original_branch_count')
    added_branch_mask((results.userdata.ny_lite.original_branch_count + 1):end) = true;
end
added_loading_pct = NaN;
if any(added_branch_mask & rated)
    added_loading_pct = max(100 * smax(added_branch_mask & rated) ./ ...
        rate(added_branch_mask & rated));
end

row = table(string(scenario_id), x_multiplier, total_pmax_mw, ...
    options.q_abs_ratio, options.eta, string(status), string(note), ...
    height(scale_report), double(results.success), raw_info(results), results.f, ...
    size(results.bus, 1), size(results.branch, 1), size(results.gen, 1), ...
    height(zone_j_report), j_count, sum(results.bus(:, PD)), sum(results.bus(:, QD)), ...
    sum(results.gen(online, PG)), sum(results.gen(online, QG)), ...
    ext_sum(ext_report, 'target_flow_mw'), ext_sum(ext_report, 'target_q_mvar'), ...
    j_pg, j_qg, j_pmax, ...
    min(results.bus(:, VM)), max(results.bus(:, VM)), ...
    sum(results.bus(:, VM) >= results.bus(:, VMAX) - 1e-5), ...
    sum(results.bus(:, VM) <= results.bus(:, VMIN) + 1e-5), ...
    sum(rated & smax > rate + 1e-6), max([0; smax(rated) - rate(rated)]), ...
    added_loading_pct, ...
    interface_flow(flows, 'Total_East_proxy'), ...
    interface_flow(flows, 'UPNY_ConEd'), ...
    interface_flow(flows, 'Millwood_South'), ...
    interface_flow(flows, 'Dunwoodie_South'), ...
    interface_flow(flows, 'ConEd_LIPA_IK') + interface_flow(flows, 'ConEd_LIPA_JK'), ...
    'VariableNames', names);
end

function names = result_columns()
names = {'scenario_id','x_multiplier','zone_j_total_pmax_mw','zone_j_q_abs_ratio', ...
    'eta','status','note','scaled_branch_count','opf_success','opf_raw_info', ...
    'objective','bus_count','branch_count','gen_count','zone_j_report_count', ...
    'zone_j_result_count','total_pd_mw','total_qd_mvar','total_pg_mw', ...
    'total_qg_mvar','boundary_target_p_mw','boundary_target_q_mvar', ...
    'zone_j_equiv_pg_mw','zone_j_equiv_qg_mvar','zone_j_equiv_pmax_mw', ...
    'min_voltage','max_voltage','at_vmax_count','at_vmin_count', ...
    'rate_a_overload_count','max_rate_a_overload_mva', ...
    'max_added_branch_loading_pct','total_east_proxy_flow_mw', ...
    'upny_coned_flow_mw','millwood_south_flow_mw','dunwoodie_south_flow_mw', ...
    'coned_lipa_total_flow_mw'};
end

function agg = aggregate_rows(rows)
xvals = unique(rows.x_multiplier, 'stable');
pvals = unique(rows.zone_j_total_pmax_mw, 'stable');
agg = table();
for xi = 1:numel(xvals)
    for pi = 1:numel(pvals)
        mask = rows.x_multiplier == xvals(xi) & rows.zone_j_total_pmax_mw == pvals(pi);
        subset = rows(mask, :);
        row = table(xvals(xi), pvals(pi), sum(mask), ...
            sum(subset.opf_success == 1), ...
            min(subset.min_voltage, [], 'omitnan'), ...
            max(subset.max_voltage, [], 'omitnan'), ...
            max(subset.max_rate_a_overload_mva, [], 'omitnan'), ...
            max(subset.zone_j_equiv_pg_mw, [], 'omitnan'), ...
            mean(subset.zone_j_equiv_pg_mw(subset.opf_success == 1), 'omitnan'), ...
            'VariableNames', {'x_multiplier','zone_j_total_pmax_mw', ...
            'case_count','success_count','min_voltage_seen','max_voltage_seen', ...
            'max_rate_a_overload_mva_seen','max_zone_j_equiv_pg_mw_seen', ...
            'mean_success_zone_j_equiv_pg_mw'});
        agg = [agg; row]; %#ok<AGROW>
    end
end
end

function [pg, qg, pmax, count] = zone_j_sums(results)
define_constants;
pg = 0; qg = 0; pmax = 0; count = 0;
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
