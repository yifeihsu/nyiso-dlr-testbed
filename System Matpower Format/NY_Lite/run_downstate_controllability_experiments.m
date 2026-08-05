function outputs = run_downstate_controllability_experiments(options)
%RUN_DOWNSTATE_CONTROLLABILITY_EXPERIMENTS Test stiffness, supply, Q, Vm cost.
%
%   Case: full S2 spine, public P-only load at eta = 1.0, S1 boundary
%   equivalent fixed, normal branch ratings and voltage bounds, IPOPT ACOPF.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'ny_external_interface_targets.csv');
end
if ~isfield(options, 'summary_file')
    options.summary_file = fullfile(helper_dir, 'downstate_controllability_experiments.csv');
end
if ~isfield(options, 'aggregate_file')
    options.aggregate_file = fullfile(helper_dir, 'downstate_controllability_summary.csv');
end
if ~isfield(options, 'archive_dir')
    options.archive_dir = fullfile(helper_dir, 'archives');
end
if ~isfield(options, 'x_multipliers'), options.x_multipliers = [1.0 0.75 0.50 0.25]; end
if ~isfield(options, 'device_profiles')
    options.device_profiles = ["none", "p_supply", "q_support", "pq_supply", "pq_supply_vpenalty"];
end
if ~isfield(options, 'eta'), options.eta = 1.0; end
if ~isfield(options, 'voltage_penalty_rho'), options.voltage_penalty_rho = 1e4; end
if ~isfield(options, 'voltage_penalty_vref'), options.voltage_penalty_vref = 1.0; end
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

rows = table();
for xk = 1:numel(options.x_multipliers)
    x_multiplier = options.x_multipliers(xk);
    for pk = 1:numel(options.device_profiles)
        device_profile = string(options.device_profiles(pk));
        for s = 1:height(public_scenarios)
            scenario_id = string(public_scenarios.scenario_id(s));
            row = run_one(scenario_id, x_multiplier, device_profile, mpopt, options);
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
        "downstate_controllability_results_" + stamp + ".zip");
    files = {options.summary_file, options.aggregate_file, ...
        fullfile(helper_dir, 'run_downstate_controllability_experiments.m'), ...
        fullfile(helper_dir, 'scale_ny_downstate_delivery_spine_impedance.m'), ...
        fullfile(helper_dir, 'add_ny_downstate_equivalent_devices.m'), ...
        fullfile(helper_dir, 'add_voltage_deviation_cost.m'), ...
        fullfile(helper_dir, 'add_ny_downstate_delivery_spine.m'), ...
        fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
        fullfile(helper_dir, 'ny_zonal_load_targets.csv'), ...
        fullfile(helper_dir, 'ny_external_interface_targets.csv')};
    zip(archive_file, files);
end

outputs = struct('summary_file', options.summary_file, ...
    'aggregate_file', options.aggregate_file, ...
    'archive_file', archive_file, ...
    'row_count', height(rows), ...
    'aggregate_row_count', height(agg));
end

function row = run_one(scenario_id, x_multiplier, device_profile, mpopt, options)
define_constants;
status = "ok";
note = "";
ext_report = table();
device_report = table();
try
    base = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
    [mpc, ~] = build_ny_only_equivalent_case(base);
    [mpc, ~] = add_ny_downstate_delivery_spine(mpc, 'full');
    [mpc, scale_report] = scale_ny_downstate_delivery_spine_impedance(mpc, ...
        x_multiplier, struct('include_gilboa_leeds', false));
    mpc = apply_public_active_load_eta(mpc, scenario_id, options.eta);
    [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
        "S1_MEASURED_BOUNDARY", struct('target_file', options.target_file));
    [base_device_profile, use_vpenalty] = parse_device_profile(device_profile);
    [mpc, device_report] = add_ny_downstate_equivalent_devices(mpc, base_device_profile);
    if use_vpenalty
        mpc = add_voltage_deviation_cost(mpc, options.voltage_penalty_rho, ...
            options.voltage_penalty_vref);
    end
    results = runopf(mpc, mpopt);
catch ME
    results = struct();
    mpc = struct();
    scale_report = table();
    status = "error";
    note = string(regexprep(ME.message, '\s+', ' '));
end
row = summarize(scenario_id, x_multiplier, device_profile, status, note, ...
    mpc, results, ext_report, device_report, scale_report, options);
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

function [base_profile, use_vpenalty] = parse_device_profile(device_profile)
use_vpenalty = endsWith(device_profile, "_vpenalty");
base_profile = erase(device_profile, "_vpenalty");
if strlength(base_profile) == 0
    base_profile = "none";
end
end

function row = summarize(scenario_id, x_multiplier, device_profile, status, note, ...
    mpc, results, ext_report, device_report, scale_report, options)
define_constants;
names = result_columns();
if strcmp(status, "error") || ~isfield(results, 'bus')
    values = num2cell(NaN(1, numel(names) - 8));
    row = table(string(scenario_id), x_multiplier, string(device_profile), ...
        options.eta, string(status), string(note), ...
        options.voltage_penalty_rho * double(endsWith(string(device_profile), "_vpenalty")), ...
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
[dev_pg, dev_qg, dev_pmax, dev_qabs, dev_count] = device_sums(results);
added_branch_mask = added_branch_mask_for(results);
added_loading_pct = NaN;
if any(added_branch_mask & rated)
    added_loading_pct = max(100 * smax(added_branch_mask & rated) ./ ...
        rate(added_branch_mask & rated));
end

row = table(string(scenario_id), x_multiplier, string(device_profile), ...
    options.eta, string(status), string(note), ...
    options.voltage_penalty_rho * double(endsWith(string(device_profile), "_vpenalty")), ...
    height(scale_report), double(results.success), raw_info(results), results.f, ...
    size(results.bus, 1), size(results.branch, 1), size(results.gen, 1), ...
    height(device_report), dev_count, sum(results.bus(:, PD)), sum(results.bus(:, QD)), ...
    sum(results.gen(online, PG)), sum(results.gen(online, QG)), ...
    ext_sum(ext_report, 'target_flow_mw'), ext_sum(ext_report, 'target_q_mvar'), ...
    dev_pg, dev_qg, dev_pmax, dev_qabs, ...
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
names = {'scenario_id','x_multiplier','device_profile','eta','status','note', ...
    'voltage_penalty_rho','scaled_branch_count','opf_success','opf_raw_info', ...
    'objective','bus_count','branch_count','gen_count','added_device_report_count', ...
    'added_device_result_count','total_pd_mw','total_qd_mvar','total_pg_mw', ...
    'total_qg_mvar','boundary_target_p_mw','boundary_target_q_mvar', ...
    'added_device_pg_mw','added_device_qg_mvar','added_device_pmax_mw', ...
    'added_device_qabs_limit_mvar','min_voltage','max_voltage','at_vmax_count', ...
    'at_vmin_count','rate_a_overload_count','max_rate_a_overload_mva', ...
    'max_added_branch_loading_pct','total_east_proxy_flow_mw', ...
    'upny_coned_flow_mw','millwood_south_flow_mw','dunwoodie_south_flow_mw', ...
    'coned_lipa_total_flow_mw'};
end

function agg = aggregate_rows(rows)
profiles = unique(string(rows.device_profile), 'stable');
xvals = unique(rows.x_multiplier, 'stable');
agg = table();
for xi = 1:numel(xvals)
    for pi = 1:numel(profiles)
        mask = rows.x_multiplier == xvals(xi) & string(rows.device_profile) == profiles(pi);
        subset = rows(mask, :);
        row = table(xvals(xi), profiles(pi), sum(mask), ...
            sum(subset.opf_success == 1), ...
            min(subset.min_voltage, [], 'omitnan'), ...
            max(subset.max_voltage, [], 'omitnan'), ...
            max(subset.max_rate_a_overload_mva, [], 'omitnan'), ...
            max(subset.added_device_pg_mw, [], 'omitnan'), ...
            max(abs(subset.added_device_qg_mvar), [], 'omitnan'), ...
            'VariableNames', {'x_multiplier','device_profile','case_count', ...
            'success_count','min_voltage_seen','max_voltage_seen', ...
            'max_rate_a_overload_mva_seen','max_added_device_pg_mw_seen', ...
            'max_abs_added_device_qg_mvar_seen'});
        agg = [agg; row]; %#ok<AGROW>
    end
end
end

function mask = added_branch_mask_for(results)
mask = false(size(results.branch, 1), 1);
if isfield(results.userdata, 'ny_lite') && ...
        isfield(results.userdata.ny_lite, 'original_branch_count')
    mask((results.userdata.ny_lite.original_branch_count + 1):end) = true;
end
end

function [pg, qg, pmax, qabs, count] = device_sums(results)
define_constants;
pg = 0; qg = 0; pmax = 0; qabs = 0; count = 0;
if ~isfield(results, 'userdata') || ~isfield(results.userdata, 'ny_lite') || ...
        ~isfield(results.userdata.ny_lite, 'downstate_equivalent_devices')
    return;
end
devices = results.userdata.ny_lite.downstate_equivalent_devices;
if isempty(devices), return; end
idx = [devices.gen_index];
idx = idx(idx >= 1 & idx <= size(results.gen, 1));
count = numel(idx);
if count == 0, return; end
pg = sum(results.gen(idx, PG));
qg = sum(results.gen(idx, QG));
pmax = sum(results.gen(idx, PMAX));
qabs = sum(max(abs(results.gen(idx, QMAX)), abs(results.gen(idx, QMIN))));
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
