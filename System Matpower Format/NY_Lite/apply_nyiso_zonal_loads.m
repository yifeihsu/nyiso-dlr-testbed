function [mpc, report] = apply_nyiso_zonal_loads(mpc, zonal_loads, eta, options)
%APPLY_NYISO_ZONAL_LOADS Redistribute retained NY load by NYISO zone.
%   zonal_loads may be an 11-element MW vector, A-K struct, two-column cell,
%   table, CSV path, or scenario_id in ny_zonal_load_targets.csv.
%
%   options.preserve_total_ny_load (default true) rescales supplied targets
%   to options.ny_total_load_mw or the pre-allocation NY total.

if nargin < 2, zonal_loads = []; end
if nargin < 3 || isempty(eta), eta = 1.0; end
if nargin < 4, options = struct(); end
if ~isfield(options, 'default_power_factor'), options.default_power_factor = 0.97; end
if ~isfield(options, 'preserve_total_ny_load'), options.preserve_total_ny_load = true; end
if ~isfield(options, 'ny_total_load_mw'), options.ny_total_load_mw = []; end
if ~isfield(options, 'target_file')
    options.target_file = fullfile(fileparts(mfilename('fullpath')), 'ny_zonal_load_targets.csv');
end
if ~isfield(options, 'tolerance_mw'), options.tolerance_mw = 1e-8; end

if ~isscalar(eta) || ~isfinite(eta) || eta < 0 || eta > 1
    error('apply_nyiso_zonal_loads:BadEta', 'eta must be a finite scalar in [0, 1].');
end
if options.default_power_factor <= 0 || options.default_power_factor > 1
    error('apply_nyiso_zonal_loads:BadPowerFactor', ...
        'default_power_factor must be in (0, 1].');
end

PD = 3; QD = 4;
mpc = attach_nyiso_zone_metadata(mpc);
[map, zones] = nyiso_bus_zone_map;
letters = {zones.letter};
n_zone = numel(zones);

original_pd = mpc.bus(:, PD);
original_qd = mpc.bus(:, QD);
original_zone_mw = zone_totals(mpc, map, zones, original_pd);
original_total_mw = sum(original_zone_mw);

[target_mw, target_type, scenario_id] = normalize_zonal_load_targets( ...
    zonal_loads, original_zone_mw, map, zones, options);

if options.preserve_total_ny_load
    if isempty(options.ny_total_load_mw)
        desired_total = original_total_mw;
    else
        desired_total = options.ny_total_load_mw;
    end
    if ~isfinite(desired_total) || desired_total < 0
        error('apply_nyiso_zonal_loads:BadTotal', ...
            'ny_total_load_mw must be finite and nonnegative.');
    end
    if sum(target_mw) <= 0 && desired_total > 0
        error('apply_nyiso_zonal_loads:ZeroTargetTotal', ...
            'Zonal targets must have positive total when the desired NY load is positive.');
    elseif sum(target_mw) > 0
        target_mw = target_mw * desired_total / sum(target_mw);
    end
end

if any(~isfinite(target_mw)) || any(target_mw < -options.tolerance_mw)
    error('apply_nyiso_zonal_loads:BadTargets', ...
        'All zonal load targets must be finite and nonnegative.');
end
target_mw(abs(target_mw) < options.tolerance_mw) = 0;

applied_zone_mw = zeros(n_zone, 1);
applied_zone_mvar = zeros(n_zone, 1);
for z = 1:n_zone
    zone_bus_ids = [map(strcmp({map.load_allocation_group}, letters{z})).bus_id];
    bus_idx = find(ismember(mpc.bus(:, 1), zone_bus_ids));
    if isempty(bus_idx)
        error('apply_nyiso_zonal_loads:NoAllocationBus', ...
            'No retained bus is assigned to load-allocation group %s.', letters{z});
    end

    blended_mw = (1 - eta) * original_zone_mw(z) + eta * target_mw(z);
    weights = load_allocation_weights(map, mpc.bus(bus_idx, 1), original_pd(bus_idx));
    new_pd = blended_mw * weights(:);
    [~, correction_idx] = max(weights);
    new_pd(correction_idx) = new_pd(correction_idx) + blended_mw - sum(new_pd);

    for k = 1:numel(bus_idx)
        idx = bus_idx(k);
        mpc.bus(idx, PD) = new_pd(k);
        mpc.bus(idx, QD) = reactive_load_mvar(new_pd(k), original_pd(idx), ...
            original_qd(idx), options.default_power_factor, options.tolerance_mw);
    end

    applied_zone_mw(z) = sum(mpc.bus(bus_idx, PD));
    applied_zone_mvar(z) = sum(mpc.bus(bus_idx, QD));
end

report = struct();
report.scenario_id = scenario_id;
report.target_type = target_type;
report.zone_letter = letters(:);
report.zone_name = {zones.name}';
report.original_mw = original_zone_mw;
report.target_mw = target_mw(:);
report.applied_mw = applied_zone_mw;
report.applied_mvar = applied_zone_mvar;
report.original_total_mw = original_total_mw;
report.applied_total_mw = sum(applied_zone_mw);
report.eta = eta;

mpc.userdata.ny_lite.zonal_load_report = report;
mpc.userdata.ny_lite.zonal_load_target_mw = target_mw(:);
mpc.userdata.ny_lite.zonal_load_eta = eta;
end

function totals = zone_totals(mpc, map, zones, pd)
totals = zeros(numel(zones), 1);
for z = 1:numel(zones)
    ids = [map(strcmp({map.load_allocation_group}, zones(z).letter)).bus_id];
    totals(z) = sum(pd(ismember(mpc.bus(:, 1), ids)));
end
end

function [target_mw, target_type, scenario_id] = normalize_zonal_load_targets(input, original_zone_mw, map, zones, options)
n_zone = numel(zones);
target_mw = NaN(n_zone, 1);
target_type = 'mw';
scenario_id = '';

if isempty(input)
    target_mw = original_zone_mw(:);
    target_type = 'original_mw';
    return;
end

if ischar(input) || (exist('isstring', 'builtin') && isstring(input))
    token = char(input);
    if exist(token, 'file') == 2
        tbl = readtable(token);
    else
        scenario_id = token;
        if exist(options.target_file, 'file') ~= 2
            error('apply_nyiso_zonal_loads:TargetFileMissing', ...
                'Cannot find zonal target file: %s', options.target_file);
        end
        tbl = readtable(options.target_file);
        names = cellfun(@lower, tbl.Properties.VariableNames, 'UniformOutput', false);
        scenario_col = find(strcmp(names, 'scenario_id'), 1);
        if isempty(scenario_col)
            error('apply_nyiso_zonal_loads:NoScenarioColumn', ...
                'Target file must contain scenario_id.');
        end
        values = tbl{:, scenario_col};
        if iscell(values), mask = strcmp(values, scenario_id); else, mask = strcmp(cellstr(values), scenario_id); end
        tbl = tbl(mask, :);
        if height(tbl) == 0
            error('apply_nyiso_zonal_loads:UnknownScenario', ...
                'No load targets found for scenario %s.', scenario_id);
        end
    end
    [target_mw, target_type] = targets_from_table(tbl, zones, original_zone_mw);
    return;
end

if isnumeric(input)
    if numel(input) ~= n_zone
        error('apply_nyiso_zonal_loads:BadNumericTargets', ...
            'Numeric zonal_loads must have 11 values in A-K order.');
    end
    target_mw = input(:);
    return;
end

if isstruct(input)
    if numel(input) == 1
        for z = 1:n_zone
            if isfield(input, zones(z).letter), target_mw(z) = input.(zones(z).letter); end
        end
    elseif isfield(input, 'zone_letter') && isfield(input, 'load_mw')
        for k = 1:numel(input)
            z = nyiso_zone_index(input(k).zone_letter);
            if ~isnan(z), target_mw(z) = input(k).load_mw; end
        end
    end
elseif iscell(input)
    for k = 1:size(input, 1)
        z = nyiso_zone_index(input{k, 1});
        if ~isnan(z), target_mw(z) = input{k, 2}; end
    end
elseif (exist('istable', 'builtin') || exist('istable', 'file')) && istable(input)
    [target_mw, target_type] = targets_from_table(input, zones, original_zone_mw);
    return;
else
    error('apply_nyiso_zonal_loads:UnsupportedTargets', 'Unsupported zonal-load input type.');
end

if any(isnan(target_mw))
    missing = {zones(isnan(target_mw)).letter};
    error('apply_nyiso_zonal_loads:IncompleteTargets', ...
        'Missing zonal load targets for zone(s): %s', strjoin(missing, ', '));
end
end

function [target_mw, target_type] = targets_from_table(tbl, zones, original_zone_mw)
names = cellfun(@lower, tbl.Properties.VariableNames, 'UniformOutput', false);
zone_col = find(strcmp(names, 'zone') | strcmp(names, 'nyiso_zone_letter'), 1);
mw_col = find(strcmp(names, 'load_mw') | strcmp(names, 'target_mw') | strcmp(names, 'target_load_mw'), 1);
share_col = find(strcmp(names, 'load_share') | strcmp(names, 'target_load_share'), 1);
if isempty(zone_col) || (isempty(mw_col) && isempty(share_col))
    error('apply_nyiso_zonal_loads:BadTableTargets', ...
        'Table must contain a zone column and either MW or share targets.');
end

mw_present = false(height(tbl), 1);
share_present = false(height(tbl), 1);
if ~isempty(mw_col)
    mw_vals = numeric_column(tbl, mw_col);
    mw_present = isfinite(mw_vals);
else
    mw_vals = NaN(height(tbl), 1);
end
if ~isempty(share_col)
    share_vals = numeric_column(tbl, share_col);
    share_present = isfinite(share_vals);
else
    share_vals = NaN(height(tbl), 1);
end
if any(mw_present & share_present) || (any(mw_present) && any(share_present))
    error('apply_nyiso_zonal_loads:MixedLoadTargets', ...
        'A scenario must use only MW targets or only share targets, not both.');
end
if ~any(mw_present) && ~any(share_present)
    error('apply_nyiso_zonal_loads:EmptyTargets', 'No numeric MW or share targets were supplied.');
end

raw = NaN(numel(zones), 1);
for k = 1:height(tbl)
    zone_value = tbl{k, zone_col};
    if iscell(zone_value), zone_value = zone_value{1}; end
    z = nyiso_zone_index(char(zone_value));
    if isnan(z), continue; end
    if any(mw_present), raw(z) = mw_vals(k); else, raw(z) = share_vals(k); end
end
if any(isnan(raw))
    missing = {zones(isnan(raw)).letter};
    error('apply_nyiso_zonal_loads:IncompleteTargets', ...
        'Missing zonal load targets for zone(s): %s', strjoin(missing, ', '));
end
if any(mw_present)
    target_mw = raw;
    target_type = 'mw';
else
    if any(raw < 0) || sum(raw) <= 0
        error('apply_nyiso_zonal_loads:BadShares', ...
            'Load shares must be nonnegative and have positive total.');
    end
    target_mw = raw / sum(raw) * sum(original_zone_mw);
    target_type = 'share';
end
end

function values = numeric_column(tbl, col)
values = tbl{:, col};
if iscell(values)
    out = NaN(numel(values), 1);
    for k = 1:numel(values)
        if isempty(values{k}), continue; end
        if isnumeric(values{k}), out(k) = values{k}; else, out(k) = str2double(values{k}); end
    end
    values = out;
end
values = double(values(:));
end

function weights = load_allocation_weights(map, bus_ids, original_pd)
weights = zeros(numel(bus_ids), 1);
positive = original_pd > 1e-6;
if any(positive)
    weights(positive) = original_pd(positive) / sum(original_pd(positive));
    return;
end
proxy = zeros(numel(bus_ids), 1);
for k = 1:numel(bus_ids)
    idx = find([map.bus_id] == bus_ids(k), 1);
    proxy(k) = map(idx).load_proxy_weight;
end
if sum(proxy) > 0
    weights = proxy / sum(proxy);
else
    weights(:) = 1 / numel(bus_ids);
end
end

function qd = reactive_load_mvar(new_pd, original_pd, original_qd, default_pf, tol)
if abs(new_pd - original_pd) <= tol
    qd = original_qd;                   % exact baseline invariance
elseif abs(original_pd) > tol
    qd = new_pd * original_qd / original_pd;  % preserve signed Q/P
else
    qd = new_pd * tan(acos(default_pf));       % new proxy load
end
end
