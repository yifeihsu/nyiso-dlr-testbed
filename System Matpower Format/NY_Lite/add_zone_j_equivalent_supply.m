function [mpc, report] = add_zone_j_equivalent_supply(mpc, options)
%ADD_ZONE_J_EQUIVALENT_SUPPLY Add scaled aggregate Zone-J active supply.
%
%   This is an equivalent representation of missing NYC local generation
%   and controllable imports. It is not a unit-level generator model.
%
%   Default split:
%     40% RAV A-3   Queens/Ravenswood/Astoria aggregate
%     30% AK-3      Staten Island/Arthur Kill aggregate
%     30% GOETHALS  NYC import/Gowanus-adjacent aggregate

if nargin < 2, options = struct(); end
if ~isfield(options, 'total_pmax_mw'), options.total_pmax_mw = 3500; end
if ~isfield(options, 'split'), options.split = [0.40 0.30 0.30]; end
if ~isfield(options, 'q_abs_ratio'), options.q_abs_ratio = 0; end
if ~isfield(options, 'cost_c2'), options.cost_c2 = 0.02; end
if ~isfield(options, 'cost_c1'), options.cost_c1 = 250; end
if ~isfield(options, 'on_existing'), options.on_existing = 'skip'; end

if ~isscalar(options.total_pmax_mw) || ~isfinite(options.total_pmax_mw) || ...
        options.total_pmax_mw < 0
    error('add_zone_j_equivalent_supply:BadPmax', ...
        'total_pmax_mw must be finite and nonnegative.');
end
if numel(options.split) ~= 3 || any(options.split < 0) || sum(options.split) <= 0
    error('add_zone_j_equivalent_supply:BadSplit', ...
        'split must contain three nonnegative entries with positive sum.');
end
if ~isscalar(options.q_abs_ratio) || ~isfinite(options.q_abs_ratio) || options.q_abs_ratio < 0
    error('add_zone_j_equivalent_supply:BadQRatio', ...
        'q_abs_ratio must be finite and nonnegative.');
end

define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
if ~isfield(mpc, 'gencost') || isempty(mpc.gencost)
    mpc.gencost = zeros(size(mpc.gen, 1), 7);
    mpc.gencost(:, 1) = 2;
    mpc.gencost(:, 4) = 3;
end
if ~isfield(mpc, 'userdata'), mpc.userdata = struct(); end
if ~isfield(mpc.userdata, 'ny_lite'), mpc.userdata.ny_lite = struct(); end
if ~isfield(mpc.userdata.ny_lite, 'zone_j_equivalent_supply')
    mpc.userdata.ny_lite.zone_j_equivalent_supply = struct([]);
end

specs = zone_j_specs();
split = options.split(:) / sum(options.split);
pmax = options.total_pmax_mw * split;

existing = mpc.userdata.ny_lite.zone_j_equivalent_supply;
existing_names = {};
if ~isempty(existing) && isfield(existing, 'name')
    existing_names = {existing.name};
end

report = table();
for k = 1:numel(specs)
    s = specs(k);
    old = find(strcmp(existing_names, s.name), 1);
    if ~isempty(old)
        if strcmpi(options.on_existing, 'error')
            error('add_zone_j_equivalent_supply:AlreadyExists', ...
                'Zone-J equivalent %s already exists.', s.name);
        elseif strcmpi(options.on_existing, 'update')
            gi = existing(old).gen_index;
        else
            continue;
        end
    else
        gi = size(mpc.gen, 1) + 1;
        mpc.gen(gi, 1:max(21, size(mpc.gen, 2))) = 0;
        mpc.gencost(gi, 1:size(mpc.gencost, 2)) = 0;
    end

    bus_idx = find(mpc.bus(:, BUS_I) == s.bus_id, 1);
    if isempty(bus_idx)
        error('add_zone_j_equivalent_supply:MissingBus', ...
            'Zone-J equivalent bus %.0f is missing.', s.bus_id);
    end

    qmax = options.q_abs_ratio * pmax(k);
    qmin = -qmax;
    vg = mpc.bus(bus_idx, VM);
    mpc.gen(gi, [GEN_BUS PG QG QMAX QMIN VG MBASE GEN_STATUS PMAX PMIN]) = ...
        [s.bus_id 0 0 qmax qmin vg mpc.baseMVA 1 pmax(k) 0];
    cost = [2 0 0 3 options.cost_c2 options.cost_c1 0];
    mpc.gencost(gi, 1:numel(cost)) = cost;

    rec = struct('name', s.name, 'bus_id', s.bus_id, ...
        'bus_name', s.bus_name, 'zone', 'J', ...
        'proxy_interpretation', s.proxy_interpretation, ...
        'gen_index', gi, 'pmax_mw', pmax(k), ...
        'qmin_mvar', qmin, 'qmax_mvar', qmax, ...
        'cost_c2', options.cost_c2, 'cost_c1', options.cost_c1);
    if isempty(old)
        existing = append_struct(existing, rec);
        existing_names{end + 1} = s.name; %#ok<AGROW>
    else
        existing(old) = rec;
    end
    report = [report; struct2table(rec, 'AsArray', true)]; %#ok<AGROW>
end

mpc.userdata.ny_lite.zone_j_equivalent_supply = existing;
mpc.userdata.ny_lite.zone_j_equivalent_total_pmax_mw = options.total_pmax_mw;
mpc.userdata.ny_lite.zone_j_equivalent_split = split(:)';
mpc.userdata.ny_lite.zone_j_equivalent_q_abs_ratio = options.q_abs_ratio;
mpc.userdata.ny_lite.zone_j_equivalent_note = ...
    'Scaled aggregate Zone-J local generation/import equivalent, not unit-level plant model.';
end

function specs = zone_j_specs()
specs = struct( ...
    'name', {'RAV_A3_J_EQ_SUPPLY', 'AK3_J_EQ_SUPPLY', 'GOETHALS_J_EQ_SUPPLY'}, ...
    'bus_id', {79, 82, 81}, ...
    'bus_name', {'RAV A-3', 'AK-3', 'GOETHALS'}, ...
    'proxy_interpretation', { ...
        'Queens / Ravenswood / Astoria / East River aggregate', ...
        'Staten Island / Arthur Kill aggregate', ...
        'NYC import / Goethals / Gowanus-adjacent aggregate'});
end

function out = append_struct(out, entry)
if isempty(out)
    out = entry;
else
    out(end + 1) = entry;
end
end
