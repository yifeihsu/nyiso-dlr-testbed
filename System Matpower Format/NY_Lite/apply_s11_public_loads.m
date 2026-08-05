function [mpc, report] = apply_s11_public_loads(mpc, scenario_id, options)
%APPLY_S11_PUBLIC_LOADS Apply raw public P and PERFORM-backed zonal Q/P.

if nargin < 2 || isempty(scenario_id)
    scenario_id = "S1_2025_SUMMER_PEAK_PUBLIC";
end
if nargin < 3, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
workspace_dir = fileparts(case_dir);
if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'ny_zonal_load_targets.csv');
end
if ~isfield(options, 'q_multiplier'), options.q_multiplier = 1.0; end
if ~isfield(options, 'use_raw_public_scale'), options.use_raw_public_scale = true; end
if ~isfield(options, 'perform_case_dir')
    options.perform_case_dir = fullfile(workspace_dir, 'PERFORM', ...
        'On Peak 2019 v23_Perform_NY', 'On Peak 2019 v23');
end
if ~isfield(options, 'perform_bus_map_file')
    options.perform_bus_map_file = fullfile(workspace_dir, 'PERFORM', ...
        'Auxilliary_Perform_NY', 'internal_NYISO_MOD2MAP.xlsx');
end
if ~isscalar(options.q_multiplier) || ~isfinite(options.q_multiplier) || ...
        options.q_multiplier <= 0
    error('apply_s11_public_loads:QMultiplier', ...
        'q_multiplier must be a finite positive scalar.');
end
define_constants;

targets = readtable(options.target_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
targets = targets(string(targets.scenario_id) == string(scenario_id), :);
if height(targets) ~= 11
    error('apply_s11_public_loads:ScenarioRows', ...
        'Expected 11 public zonal load rows for %s; found %d.', ...
        string(scenario_id), height(targets));
end
zones = string(('A':'K')');
target_p = nan(11, 1);
for z = 1:11
    idx = find(upper(string(targets.nyiso_zone_letter)) == zones(z), 1);
    if isempty(idx)
        error('apply_s11_public_loads:MissingZone', ...
            'Scenario %s is missing zone %s.', string(scenario_id), zones(z));
    end
    if options.use_raw_public_scale
        target_p(z) = double(targets.nyiso_load_mw(idx));
    else
        target_p(z) = double(targets.target_load_mw(idx));
    end
end

[mpc, allocation] = apply_nyiso_zonal_loads(mpc, target_p, 1.0, ...
    struct('preserve_total_ny_load', false, 'default_power_factor', 1.0));
[ratio, source_p, source_q] = perform_zonal_qp(options);
mpc = attach_nyiso_zone_metadata(mpc);
applied_q = zeros(11, 1);
bus_rows = table();
for z = 1:11
    idx = string(mpc.userdata.nyiso_physical_zone) == zones(z);
    zone_q = ratio(z) * target_p(z) * options.q_multiplier;
    weights = mpc.bus(idx, PD);
    if sum(weights) <= 0, weights = ones(sum(idx), 1); end
    weights = weights / sum(weights);
    mpc.bus(idx, QD) = zone_q * weights;
    applied_q(z) = sum(mpc.bus(idx, QD));
    ids = mpc.bus(idx, BUS_I);
    pd = mpc.bus(idx, PD);
    qd = mpc.bus(idx, QD);
    row = table(repmat(string(scenario_id), numel(ids), 1), ...
        repmat(zones(z), numel(ids), 1), ids, pd, qd, weights, ...
        'VariableNames', {'scenario_id','zone','bus_id','pd_mw','qd_mvar', ...
        'zonal_allocation_weight'});
    bus_rows = append_table(bus_rows, row);
end
zone_rows = table(repmat(string(scenario_id),11,1), zones, target_p, ...
    source_p, source_q, ratio, repmat(options.q_multiplier,11,1), applied_q, ...
    'VariableNames', {'scenario_id','zone','public_active_load_mw', ...
    'perform_2019_active_load_mw','perform_2019_reactive_load_mvar', ...
    'perform_2019_q_over_p','q_multiplier','applied_reactive_load_mvar'});
report = struct('scenario_id', string(scenario_id), ...
    'use_raw_public_scale', logical(options.use_raw_public_scale), ...
    'q_multiplier', options.q_multiplier, 'zone_table', zone_rows, ...
    'bus_allocation_table', bus_rows, 'allocation_report', allocation, ...
    'total_active_load_mw', sum(target_p), ...
    'total_reactive_load_mvar', sum(applied_q), ...
    'source_snapshot', 'PERFORM NYISO On Peak 2019 v23');
if ~isfield(mpc, 'userdata'), mpc.userdata = struct(); end
if ~isfield(mpc.userdata, 's11'), mpc.userdata.s11 = struct(); end
mpc.userdata.s11.load_model = report;
end

function [ratio, pd, qd] = perform_zonal_qp(options)
define_constants;
addpath(options.perform_case_dir);
source = nyiso_On_Peak_v23_shunts_as_z_load;
source_zone = perform_nyiso_zone_letters(source, source.bus(:, BUS_I));
zones = string(('A':'K')');
pd = zeros(11,1); qd = zeros(11,1); ratio = zeros(11,1);
for z = 1:11
    idx = source_zone == zones(z);
    pd(z) = sum(source.bus(idx, PD));
    qd(z) = sum(source.bus(idx, QD));
    if pd(z) <= 0
        error('apply_s11_public_loads:SourceLoad', ...
            'PERFORM source zone %s has no positive active load.', zones(z));
    end
    ratio(z) = qd(z) / pd(z);
end
end

function out = append_table(out, row)
if isempty(out), out = row; else, out = [out; row]; end
end
