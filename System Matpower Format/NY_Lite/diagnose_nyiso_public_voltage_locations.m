function outputs = diagnose_nyiso_public_voltage_locations(options)
%DIAGNOSE_NYISO_PUBLIC_VOLTAGE_LOCATIONS Write voltage-bound location tables.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
if ~isfield(options, 'bound_file')
    options.bound_file = fullfile(helper_dir, 'nyiso_public_voltage_bound_locations.csv');
end
if ~isfield(options, 'relaxed_file')
    options.relaxed_file = fullfile(helper_dir, 'nyiso_public_relaxed_voltage_locations.csv');
end
if ~isfield(options, 'tol'), options.tol = 1e-5; end

define_constants;
scenarios = readtable(fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
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
variants = {'original_topology', 'gilboa_leeds'};
for s = 1:height(scenarios)
    scenario_id = string(scenarios.scenario_id(s));
    for v = 1:numel(variants)
        [results, status] = solve_public_case(scenario_id, variants{v}, mpopt);
        if strcmp(status, "ok")
            rows = [rows; voltage_bound_rows(results, scenario_id, variants{v}, options.tol)]; %#ok<AGROW>
        end
    end
end
writetable(rows, options.bound_file);

relaxed = relaxed_voltage_rows(mpopt);
writetable(relaxed, options.relaxed_file);

outputs = struct('bound_file', options.bound_file, ...
    'relaxed_file', options.relaxed_file, ...
    'bound_row_count', height(rows), ...
    'relaxed_row_count', height(relaxed));
end

function [results, status] = solve_public_case(scenario_id, variant, mpopt)
status = "ok";
try
    mpc = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
    [mpc, ~] = apply_nyiso_zonal_loads(mpc, scenario_id, 1.0, ...
        struct('preserve_total_ny_load', true));
    if strcmpi(variant, 'gilboa_leeds')
        [mpc, ~] = add_ny_lite_tielines(mpc, 'core');
    end
    results = runopf(mpc, mpopt);
catch
    results = struct();
    status = "error";
end
end

function rows = voltage_bound_rows(results, scenario_id, variant, tol)
define_constants;
upper = find(results.bus(:, VM) >= results.bus(:, VMAX) - tol);
lower = find(results.bus(:, VM) <= results.bus(:, VMIN) + tol);
rows = table();
for idx = [upper(:); lower(:)]'
    if any(idx == upper)
        bound_type = "upper";
    else
        bound_type = "lower";
    end
    row = voltage_row(results, scenario_id, variant, bound_type, idx, "");
    rows = [rows; row]; %#ok<AGROW>
end
end

function rows = relaxed_voltage_rows(mpopt)
define_constants;
mpopt = mpoption(mpopt, 'ipopt.opts.max_iter', 1000);
mpc = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
[mpc, ~] = apply_nyiso_zonal_loads(mpc, 'S1_2019_SUMMER_PEAK_PUBLIC', ...
    1.0, struct('preserve_total_ny_load', true));
mpc.branch(:, RATE_A) = 0;
mpc.bus(:, VMIN) = 0.5;
mpc.bus(:, VMAX) = 1.5;
results = runopf(mpc, mpopt);
idx = find(results.bus(:, VM) > 1.10);
rows = table();
for k = idx(:)'
    row = voltage_row(results, 'S1_2019_SUMMER_PEAK_PUBLIC', ...
        'diagnostic_no_rate_relaxed_voltage', "above_1p10", k, ...
        "RATE_A removed and V bounds relaxed to 0.5-1.5 pu");
    rows = [rows; row]; %#ok<AGROW>
end
end

function row = voltage_row(results, scenario_id, variant, bound_type, idx, note)
define_constants;
[zone_letter, zone_name] = mapped_zone(results.bus(idx, BUS_I));
row = table(string(scenario_id), string(variant), double(results.success), ...
    raw_info(results), string(bound_type), results.bus(idx, BUS_I), ...
    string(bus_name(results, idx)), zone_letter, zone_name, ...
    results.bus(idx, VM), results.bus(idx, VMIN), results.bus(idx, VMAX), ...
    results.bus(idx, PD), results.bus(idx, QD), string(note), ...
    'VariableNames', {'scenario_id','variant','opf_success','opf_raw_info', ...
        'bound_type','bus_number','bus_name','nyiso_zone_letter', ...
        'nyiso_zone_name','vm_pu','vmin_pu','vmax_pu','pd_mw','qd_mvar','note'});
end

function [letter, name] = mapped_zone(bus_id)
[map, ~] = nyiso_bus_zone_map();
idx = find([map.bus_id] == bus_id, 1);
if isempty(idx)
    letter = "NON_NY";
    name = "NON_NY";
else
    letter = string(map(idx).nyiso_zone_letter);
    name = string(map(idx).nyiso_zone_name);
end
end

function name = bus_name(results, idx)
if isfield(results, 'bus_name') && numel(results.bus_name) >= idx
    name = strtrim(results.bus_name{idx});
else
    name = sprintf('BUS_%d', results.bus(idx, 1));
end
end

function info = raw_info(results)
if isfield(results, 'raw') && isfield(results.raw, 'info')
    info = results.raw.info;
else
    info = NaN;
end
end
