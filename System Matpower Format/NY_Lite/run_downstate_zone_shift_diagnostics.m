function outputs = run_downstate_zone_shift_diagnostics(options)
%RUN_DOWNSTATE_ZONE_SHIFT_DIAGNOSTICS Isolate G/J/K active-load relocation.
%
%   For each selected sink-zone set, move only that zone-set toward the
%   public target and offset the added MW by reducing the zones that lose
%   load in the full public scenario, preserving total NY active load.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'ny_external_interface_targets.csv');
end
if ~isfield(options, 'output_file')
    options.output_file = fullfile(helper_dir, 'downstate_zone_shift_diagnostics.csv');
end
if ~isfield(options, 'archive_dir')
    options.archive_dir = fullfile(helper_dir, 'archives');
end
if ~isfield(options, 'make_archive'), options.make_archive = true; end

public_scenarios = readtable(fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
zone_sets = { ...
    'G_ONLY', {'G'}; ...
    'J_ONLY', {'J'}; ...
    'K_ONLY', {'K'}; ...
    'G_J', {'G','J'}; ...
    'J_K', {'J','K'}; ...
    'G_J_K', {'G','J','K'}; ...
    'FULL_PUBLIC_P', {'A','B','C','D','E','F','G','H','I','J','K'}};

mpopt = mpoption( ...
    'verbose', 0, ...
    'out.all', 0, ...
    'opf.ac.solver', 'IPOPT', ...
    'opf.flow_lim', 'S', ...
    'opf.violation', 1e-6, ...
    'opf.use_vg', 0, ...
    'opf.ignore_angle_lim', 0);

rows = table();
for s = 1:height(public_scenarios)
    scenario_id = string(public_scenarios.scenario_id(s));
    for z = 1:size(zone_sets, 1)
        row = run_one(scenario_id, string(zone_sets{z, 1}), zone_sets{z, 2}, mpopt, options);
        rows = [rows; row]; %#ok<AGROW>
    end
end

writetable(rows, options.output_file);
archive_file = "";
if options.make_archive
    if exist(options.archive_dir, 'dir') ~= 7, mkdir(options.archive_dir); end
    stamp = string(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
    archive_file = fullfile(options.archive_dir, ...
        "downstate_zone_shift_results_" + stamp + ".zip");
    files = {options.output_file, fullfile(helper_dir, ...
        'run_downstate_zone_shift_diagnostics.m'), ...
        fullfile(helper_dir, 'add_ny_downstate_delivery_spine.m'), ...
        fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
        fullfile(helper_dir, 'ny_zonal_load_targets.csv'), ...
        fullfile(helper_dir, 'ny_external_interface_targets.csv')};
    zip(archive_file, files);
end

outputs = struct('output_file', options.output_file, ...
    'archive_file', archive_file, ...
    'row_count', height(rows));
end

function row = run_one(scenario_id, zone_mode, selected_zones, mpopt, options)
define_constants;
status = "ok";
note = "";
ext_report = table();
try
    base = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
    [mpc, ~] = build_ny_only_equivalent_case(base);
    [mpc, ~] = add_ny_downstate_delivery_spine(mpc, 'full');
    [mpc, relocation_report] = apply_selected_zone_p_shift(mpc, scenario_id, selected_zones);
    [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
        "S1_MEASURED_BOUNDARY", struct('target_file', options.target_file));
    results = runopf(mpc, mpopt);
catch ME
    results = struct();
    relocation_report = struct('added_selected_mw', NaN, 'donor_reduction_mw', NaN);
    status = "error";
    note = string(regexprep(ME.message, '\s+', ' '));
end
row = summarize(scenario_id, zone_mode, selected_zones, status, note, ...
    results, ext_report, relocation_report);
end

function [mpc, report] = apply_selected_zone_p_shift(mpc, scenario_id, selected_zones)
define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
s1_pd = mpc.bus(:, PD);
s1_qd = mpc.bus(:, QD);
[public_mpc, ~] = apply_nyiso_zonal_loads(mpc, scenario_id, 1.0, ...
    struct('preserve_total_ny_load', true));
public_pd = public_mpc.bus(:, PD);
delta = public_pd - s1_pd;
zone = string(mpc.userdata.nyiso_load_allocation_group);
selected = ismember(zone, string(selected_zones));

new_pd = s1_pd;
selected_delta = max(delta(selected), 0);
new_pd(selected) = s1_pd(selected) + selected_delta;
added = sum(selected_delta);

donor = delta < 0 & ~selected;
available = -sum(delta(donor));
if added > 0 && available > 0
    scale = min(1, added / available);
    new_pd(donor) = s1_pd(donor) + scale * delta(donor);
else
    scale = 0;
end
if strcmp(strjoin(sort(string(selected_zones)), ''), 'ABCDEFGHIJK')
    new_pd = public_pd;
    added = sum(max(delta, 0));
    scale = 1;
end

mpc.bus(:, PD) = new_pd;
mpc.bus(:, QD) = s1_qd;
report = struct('added_selected_mw', added, ...
    'donor_reduction_mw', sum(s1_pd(donor) - new_pd(donor)), ...
    'donor_scale', scale, ...
    'total_pd_mw', sum(new_pd));
end

function row = summarize(scenario_id, zone_mode, selected_zones, status, note, ...
    results, ext_report, relocation_report)
define_constants;
names = result_columns();
if strcmp(status, "error") || ~isfield(results, 'bus')
    values = num2cell(NaN(1, numel(names) - 7));
    row = table(string(scenario_id), string(zone_mode), ...
        strjoin(string(selected_zones), '+'), string(status), string(note), ...
        relocation_report.added_selected_mw, relocation_report.donor_reduction_mw, ...
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

row = table(string(scenario_id), string(zone_mode), ...
    strjoin(string(selected_zones), '+'), string(status), string(note), ...
    relocation_report.added_selected_mw, relocation_report.donor_reduction_mw, ...
    double(results.success), raw_info(results), results.f, ...
    sum(results.bus(:, PD)), sum(results.bus(:, QD)), ...
    sum(results.gen(online, PG)), sum(results.gen(online, QG)), ...
    ext_sum(ext_report, 'target_flow_mw'), ext_sum(ext_report, 'target_q_mvar'), ...
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

function names = result_columns()
names = {'scenario_id','zone_mode','selected_zones','status','note', ...
    'added_selected_mw','donor_reduction_mw','opf_success','opf_raw_info', ...
    'objective','total_pd_mw','total_qd_mvar','total_pg_mw','total_qg_mvar', ...
    'boundary_target_p_mw','boundary_target_q_mvar','min_voltage','max_voltage', ...
    'at_vmax_count','at_vmin_count','rate_a_overload_count', ...
    'max_rate_a_overload_mva','total_east_proxy_flow_mw', ...
    'upny_coned_flow_mw','millwood_south_flow_mw','dunwoodie_south_flow_mw', ...
    'coned_lipa_total_flow_mw'};
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
