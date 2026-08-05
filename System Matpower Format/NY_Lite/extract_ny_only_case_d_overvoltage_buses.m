function outputs = extract_ny_only_case_d_overvoltage_buses(options)
%EXTRACT_NY_ONLY_CASE_D_OVERVOLTAGE_BUSES Write bus-level overvoltage table.
%
%   Reconstructs the NY-only Case D public-load/public-external scenarios,
%   removes branch ratings, relaxes voltage bounds to the requested window,
%   runs ACOPF with IPOPT, and records buses above their original VMAX.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

if ~isfield(options, 'relaxed_vmin'), options.relaxed_vmin = 0.10; end
if ~isfield(options, 'relaxed_vmax'), options.relaxed_vmax = 2.00; end
if ~isfield(options, 'output_file')
    options.output_file = fullfile(helper_dir, ...
        'ny_only_case_d_vmax2_overvoltage_buses.csv');
end

define_constants;
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
for s = 1:height(public_scenarios)
    scenario_id = string(public_scenarios.scenario_id(s));
    timestamp = string(public_scenarios.timestamp(s));
    base = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
    [mpc, ~] = build_ny_only_equivalent_case(base);
    [mpc, ~] = apply_nyiso_zonal_loads(mpc, scenario_id, 1.0, ...
        struct('preserve_total_ny_load', true));
    [mpc, ~] = apply_nyiso_external_interface_injections(mpc, scenario_id);
    mpc = attach_nyiso_zone_metadata(mpc);

    original_vmin = mpc.bus(:, VMIN);
    original_vmax = mpc.bus(:, VMAX);
    mpc.branch(:, RATE_A) = 0;
    if size(mpc.branch, 2) >= RATE_B, mpc.branch(:, RATE_B) = 0; end
    if size(mpc.branch, 2) >= RATE_C, mpc.branch(:, RATE_C) = 0; end
    mpc.bus(:, VMIN) = options.relaxed_vmin;
    mpc.bus(:, VMAX) = options.relaxed_vmax;

    results = runopf(mpc, mpopt);
    bus_mask = results.bus(:, VM) > original_vmax + 1e-5;
    rows = [rows; scenario_bus_rows(scenario_id, timestamp, results, mpc, ...
        original_vmin, original_vmax, bus_mask, options.relaxed_vmax)]; %#ok<AGROW>
end

rows = sortrows(rows, {'scenario_id', 'voltage_pu'});
writetable(rows, options.output_file);
outputs = struct('output_file', options.output_file, 'row_count', height(rows));
end

function rows = scenario_bus_rows(scenario_id, timestamp, results, mpc, ...
    original_vmin, original_vmax, bus_mask, relaxed_vmax)
define_constants;
idx = find(bus_mask);
n = numel(idx);
if n == 0
    rows = table();
    return;
end
scenario_col = repmat(string(scenario_id), n, 1);
timestamp_col = repmat(string(timestamp), n, 1);
opf_success = repmat(double(results.success), n, 1);
bus_id = results.bus(idx, BUS_I);
bus_name = strings(n, 1);
if isfield(mpc, 'bus_name')
    for k = 1:n
        bus_name(k) = string(strtrim(mpc.bus_name{idx(k)}));
    end
end
zone = string(mpc.userdata.nyiso_physical_zone(idx));
zone_name = string(mpc.userdata.nyiso_zone_name(idx));
base_kv = results.bus(idx, BASE_KV);
pd_mw = results.bus(idx, PD);
qd_mvar = results.bus(idx, QD);
voltage_pu = results.bus(idx, VM);
original_vmin_pu = original_vmin(idx);
original_vmax_pu = original_vmax(idx);
excess_over_original_vmax_pu = voltage_pu - original_vmax_pu;
at_relaxed_vmax = voltage_pu >= relaxed_vmax - 1e-5;

rows = table(scenario_col, timestamp_col, opf_success, bus_id, bus_name, ...
    zone, zone_name, base_kv, pd_mw, qd_mvar, voltage_pu, ...
    original_vmin_pu, original_vmax_pu, excess_over_original_vmax_pu, ...
    at_relaxed_vmax, ...
    'VariableNames', {'scenario_id', 'timestamp', 'opf_success', 'bus_id', ...
    'bus_name', 'zone', 'zone_name', 'base_kv', 'pd_mw', 'qd_mvar', ...
    'voltage_pu', 'original_vmin_pu', 'original_vmax_pu', ...
    'excess_over_original_vmax_pu', 'at_relaxed_vmax'});
end
