function outputs = run_downstate_spine_p_only_benchmark(options)
%RUN_DOWNSTATE_SPINE_P_ONLY_BENCHMARK Test staged spine against P-only load shift.
%
%   The benchmark holds the S1 measured boundary equivalent fixed, keeps S1
%   reactive load, blends only active load toward public NYISO targets, and
%   enforces normal voltage/rating constraints with IPOPT ACOPF.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'ny_external_interface_targets.csv');
end
if ~isfield(options, 'summary_file')
    options.summary_file = fullfile(helper_dir, 'downstate_spine_p_only_benchmark.csv');
end
if ~isfield(options, 'stage_file')
    options.stage_file = fullfile(helper_dir, 'downstate_spine_stage_summary.csv');
end
if ~isfield(options, 'case_file')
    options.case_file = fullfile(case_dir, ...
        'npcc_ny_lite_s2_downstate_delivery_uncalibrated.m');
end
if ~isfield(options, 'archive_dir')
    options.archive_dir = fullfile(helper_dir, 'archives');
end
if ~isfield(options, 'profiles')
    options.profiles = ["none", "lower_hudson", "nyc_mesh", "li", "full"];
end
if ~isfield(options, 'eta_grid'), options.eta_grid = 0:0.1:1; end
if ~isfield(options, 'make_archive'), options.make_archive = true; end

if exist(options.target_file, 'file') ~= 2
    build_ny_external_interface_targets([], struct('target_file', options.target_file));
end

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

save_s2_case(options.case_file);

base = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
[base_ny, ~] = build_ny_only_equivalent_case(base);
base_ny = attach_nyiso_zone_metadata(base_ny);

summary_rows = table();
for p = 1:numel(options.profiles)
    profile = string(options.profiles(p));
    profile_case = base_ny;
    if profile ~= "none"
        [profile_case, ~] = add_ny_downstate_delivery_spine(profile_case, profile);
    end
    for s = 1:height(public_scenarios)
        scenario_id = string(public_scenarios.scenario_id(s));
        for e = 1:numel(options.eta_grid)
            eta = options.eta_grid(e);
            row = run_one(profile_case, profile, scenario_id, eta, mpopt, options);
            summary_rows = [summary_rows; row]; %#ok<AGROW>
        end
    end
end

stage_rows = summarize_stages(summary_rows, options.profiles);
writetable(summary_rows, options.summary_file);
writetable(stage_rows, options.stage_file);

archive_file = "";
if options.make_archive
    if exist(options.archive_dir, 'dir') ~= 7, mkdir(options.archive_dir); end
    stamp = string(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
    archive_file = fullfile(options.archive_dir, ...
        "downstate_spine_results_" + stamp + ".zip");
    files = {options.summary_file, options.stage_file, options.case_file, ...
        fullfile(helper_dir, 'add_ny_downstate_delivery_spine.m'), ...
        fullfile(helper_dir, 'run_downstate_spine_p_only_benchmark.m')};
    zip(archive_file, files);
end

outputs = struct('summary_file', options.summary_file, ...
    'stage_file', options.stage_file, ...
    'case_file', options.case_file, ...
    'archive_file', archive_file, ...
    'summary_row_count', height(summary_rows), ...
    'stage_row_count', height(stage_rows));
end

function save_s2_case(case_file)
case_dir = fileparts(case_file);
if exist(case_dir, 'dir') ~= 7, mkdir(case_dir); end
mpc = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
[mpc, ~] = add_ny_downstate_delivery_spine(mpc, 'full');
savecase(case_file, mpc);
end

function row = run_one(base_case, profile, scenario_id, eta, mpopt, options)
define_constants;
status = "ok";
note = "";
mpc = base_case;
ext_report = table();
try
    mpc = apply_public_active_load_eta(mpc, scenario_id, eta);
    [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
        "S1_MEASURED_BOUNDARY", struct('target_file', options.target_file));
    results = runopf(mpc, mpopt);
catch ME
    results = struct();
    status = "error";
    note = string(regexprep(ME.message, '\s+', ' '));
end
row = summarize_result(profile, scenario_id, eta, status, note, mpc, results, ext_report);
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

function row = summarize_result(profile, scenario_id, eta, status, note, mpc, results, ext_report)
define_constants;
names = result_columns();
if strcmp(status, "error") || ~isfield(results, 'bus')
    values = num2cell(NaN(1, numel(names) - 5));
    row = table(string(profile), string(scenario_id), eta, string(status), ...
        string(note), values{:}, 'VariableNames', names);
    return;
end

online = results.gen(:, GEN_STATUS) > 0;
sf = sqrt(results.branch(:, PF).^2 + results.branch(:, QF).^2);
st = sqrt(results.branch(:, PT).^2 + results.branch(:, QT).^2);
smax = max(sf, st);
rate = results.branch(:, RATE_A);
rated = rate > 0;
flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
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

row = table(string(profile), string(scenario_id), eta, string(status), string(note), ...
    double(results.success), raw_info(results), results.f, ...
    size(results.bus, 1), size(results.branch, 1), ...
    added_bus_count(results), sum(added_branch_mask), ...
    sum(results.bus(:, PD)), sum(results.bus(:, QD)), ...
    sum(results.gen(online, PG)), sum(results.gen(online, QG)), ...
    ext_sum(ext_report, 'target_flow_mw'), ext_sum(ext_report, 'target_q_mvar'), ...
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
names = {'profile','scenario_id','eta','status','note','opf_success', ...
    'opf_raw_info','objective','bus_count','branch_count', ...
    'added_transit_bus_count','added_branch_count','total_pd_mw', ...
    'total_qd_mvar','total_pg_mw','total_qg_mvar','boundary_target_p_mw', ...
    'boundary_target_q_mvar','min_voltage','max_voltage','at_vmax_count', ...
    'at_vmin_count','rate_a_overload_count','max_rate_a_overload_mva', ...
    'max_added_branch_loading_pct','total_east_proxy_flow_mw', ...
    'upny_coned_flow_mw','millwood_south_flow_mw', ...
    'dunwoodie_south_flow_mw','coned_lipa_total_flow_mw'};
end

function rows = summarize_stages(summary_rows, profiles)
rows = table();
for p = 1:numel(profiles)
    profile = string(profiles(p));
    mask = string(summary_rows.profile) == profile;
    etas = unique(summary_rows.eta(mask), 'stable');
    success = summary_rows.opf_success(mask) == 1;
    prof_rows = summary_rows(mask, :);
    successful_etas = prof_rows.eta(success);
    if isempty(successful_etas)
        max_success_eta = NaN;
    else
        max_success_eta = max(successful_etas);
    end
    eta1_mask = mask & summary_rows.eta == 1;
    eta1_success_count = sum(summary_rows.opf_success(eta1_mask) == 1);
    eta1_case_count = sum(eta1_mask);
    all_success_eta = NaN;
    for k = 1:numel(etas)
        eta_mask = mask & summary_rows.eta == etas(k);
        if all(summary_rows.opf_success(eta_mask) == 1)
            all_success_eta = etas(k);
        end
    end
    row = table(profile, sum(mask), eta1_success_count, eta1_case_count, ...
        max_success_eta, all_success_eta, ...
        min(prof_rows.min_voltage, [], 'omitnan'), ...
        max(prof_rows.max_voltage, [], 'omitnan'), ...
        max(prof_rows.max_rate_a_overload_mva, [], 'omitnan'), ...
        'VariableNames', {'profile','case_count','eta1_success_count', ...
        'eta1_case_count','max_success_eta_any_scenario', ...
        'max_eta_with_all_scenarios_success','min_voltage_seen', ...
        'max_voltage_seen','max_rate_a_overload_mva_seen'});
    rows = [rows; row]; %#ok<AGROW>
end
end

function n = added_bus_count(results)
n = 0;
if isfield(results.userdata, 'ny_lite') && ...
        isfield(results.userdata.ny_lite, 'transit_zone_metadata')
    buses = [results.userdata.ny_lite.transit_zone_metadata.bus_id];
    n = sum(ismember(buses, results.bus(:, 1)));
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
