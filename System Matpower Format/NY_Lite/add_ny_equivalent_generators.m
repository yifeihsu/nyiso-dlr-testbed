function [mpc, report] = add_ny_equivalent_generators(mpc, specs, options)
%ADD_NY_EQUIVALENT_GENERATORS Add idempotent E/G/H generator equivalents.
%   control_mode is 'fixed_pq' or 'voltage_regulating_pv'. In fixed_pq
%   mode the existing bus type is retained. In voltage_regulating_pv mode
%   the bus is changed to PV unless it is already REF.

if nargin < 2 || isempty(specs), specs = ny_equivalent_generator_specs; end
if nargin < 3, options = struct(); end
if ~isfield(options, 'on_existing'), options.on_existing = 'skip'; end
if ~isfield(options, 'control_mode'), options.control_mode = ''; end

GEN_BUS=1; PG=2; QG=3; QMAX=4; QMIN=5; VG=6; MBASE=7; GEN_STATUS=8; PMAX=9; PMIN=10;
BUS_I=1; BUS_TYPE=2; PV=2; REF=3;

mpc = attach_nyiso_zone_metadata(mpc);
if ~isfield(mpc, 'gencost') || isempty(mpc.gencost)
    mpc.gencost = zeros(size(mpc.gen, 1), 7);
    mpc.gencost(:, 1) = 2; mpc.gencost(:, 4) = 3;
end
if ~isfield(mpc.userdata, 'ny_lite'), mpc.userdata.ny_lite = struct(); end
if ~isfield(mpc.userdata.ny_lite, 'equivalent_generators')
    mpc.userdata.ny_lite.equivalent_generators = struct([]);
end
existing = mpc.userdata.ny_lite.equivalent_generators;
existing_names = {};
if ~isempty(existing) && isfield(existing, 'name'), existing_names = {existing.name}; end

report = struct([]);
for k = 1:numel(specs)
    s = specs(k);
    mode = s.control_mode;
    if ~isempty(options.control_mode), mode = options.control_mode; end
    mode = char(mode);
    if ~any(strcmpi(mode, {'fixed_pq', 'voltage_regulating_pv'}))
        error('add_ny_equivalent_generators:BadControlMode', ...
            'control_mode must be fixed_pq or voltage_regulating_pv.');
    end

    old = find(strcmp(existing_names, s.name), 1);
    if ~isempty(old)
        if strcmpi(options.on_existing, 'error')
            error('add_ny_equivalent_generators:AlreadyExists', ...
                'Equivalent generator %s already exists.', s.name);
        elseif strcmpi(options.on_existing, 'update')
            gi = existing(old).gen_index;
        else
            continue;
        end
    else
        % Fallback idempotence if userdata was stripped but the exact
        % equivalent-generator seed is already present at the proxy bus.
        match = find(mpc.gen(:, GEN_BUS) == s.bus_id & ...
            abs(mpc.gen(:, PMAX) - s.pmax_mw) < 1e-9 & ...
            abs(mpc.gen(:, PMIN) - s.pmin_mw) < 1e-9 & ...
            abs(mpc.gen(:, QMAX) - s.qmax_mvar) < 1e-9 & ...
            abs(mpc.gen(:, QMIN) - s.qmin_mvar) < 1e-9, 1);
        if ~isempty(match)
            gi = match;
        else
            gi = size(mpc.gen, 1) + 1;
            mpc.gen(gi, 1:max(21, size(mpc.gen, 2))) = 0;
            mpc.gencost(gi, 1:size(mpc.gencost, 2)) = 0;
        end
    end

    mpc.gen(gi, [GEN_BUS PG QG QMAX QMIN VG MBASE GEN_STATUS PMAX PMIN]) = ...
        [s.bus_id s.pg_mw s.qg_mvar s.qmax_mvar s.qmin_mvar s.vg_pu ...
         mpc.baseMVA s.status s.pmax_mw s.pmin_mw];
    cost = [2 0 0 3 s.cost_c2 s.cost_c1 s.cost_c0];
    mpc.gencost(gi, 1:numel(cost)) = cost;

    bi = find(mpc.bus(:, BUS_I) == s.bus_id, 1);
    if isempty(bi), error('add_ny_equivalent_generators:MissingBus', 'Bus %d is missing.', s.bus_id); end
    if strcmpi(mode, 'voltage_regulating_pv') && mpc.bus(bi, BUS_TYPE) ~= REF
        mpc.bus(bi, BUS_TYPE) = PV;
    end

    rec = struct('name', s.name, 'zone', s.zone, 'bus_id', s.bus_id, ...
        'gen_index', gi, 'control_mode', mode, ...
        'cost_status', 'placeholder-not-calibrated');
    if isempty(old)
        if isempty(existing), existing = rec; else, existing(end + 1) = rec; end %#ok<AGROW>
        existing_names{end + 1} = s.name; %#ok<AGROW>
    else
        existing(old) = rec;
    end
    if isempty(report), report = rec; else, report(end + 1) = rec; end %#ok<AGROW>
end
mpc.userdata.ny_lite.equivalent_generators = existing;
end
