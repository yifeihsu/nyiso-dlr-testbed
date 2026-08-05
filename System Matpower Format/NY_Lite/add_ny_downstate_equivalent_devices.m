function [mpc, report] = add_ny_downstate_equivalent_devices(mpc, profile, options)
%ADD_NY_DOWNSTATE_EQUIVALENT_DEVICES Add aggregate downstate supply/Q support.
%
%   profile:
%     none       no devices
%     p_supply   dispatchable active-power equivalents, fixed Q = 0
%     q_support  zero-P bounded-Q support devices
%     pq_supply  dispatchable P plus bounded Q support

if nargin < 2 || isempty(profile), profile = 'pq_supply'; end
if nargin < 3, options = struct(); end
if ~isfield(options, 'on_existing'), options.on_existing = 'skip'; end
if ~isfield(options, 'p_scale'), options.p_scale = 1.0; end
if ~isfield(options, 'q_scale'), options.q_scale = 1.0; end
if ~isfield(options, 'cost_c2'), options.cost_c2 = 0.02; end
if ~isfield(options, 'cost_c1'), options.cost_c1 = 250; end

profile = lower(string(profile));
if profile == "none"
    report = table();
    return;
end
if ~any(profile == ["p_supply", "q_support", "pq_supply"])
    error('add_ny_downstate_equivalent_devices:BadProfile', ...
        'Unknown downstate device profile: %s.', profile);
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
if ~isfield(mpc.userdata.ny_lite, 'downstate_equivalent_devices')
    mpc.userdata.ny_lite.downstate_equivalent_devices = struct([]);
end

specs = default_specs();
existing = mpc.userdata.ny_lite.downstate_equivalent_devices;
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
            error('add_ny_downstate_equivalent_devices:AlreadyExists', ...
                'Device %s already exists.', s.name);
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

    if profile == "q_support"
        pmax = 0; pmin = 0; pg = 0;
    else
        pmax = s.pmax_mw * options.p_scale;
        pmin = 0;
        pg = 0;
    end
    if profile == "p_supply"
        qmax = 0; qmin = 0; qg = 0;
    else
        qmax = s.qmax_mvar * options.q_scale;
        qmin = s.qmin_mvar * options.q_scale;
        qg = 0;
    end

    bus_idx = find(mpc.bus(:, BUS_I) == s.bus_id, 1);
    if isempty(bus_idx)
        error('add_ny_downstate_equivalent_devices:MissingBus', ...
            'Device bus %.0f is missing.', s.bus_id);
    end
    mpc.gen(gi, [GEN_BUS PG QG QMAX QMIN VG MBASE GEN_STATUS PMAX PMIN]) = ...
        [s.bus_id pg qg qmax qmin s.vg_pu mpc.baseMVA 1 pmax pmin];

    cost = [2 0 0 3 options.cost_c2 options.cost_c1 0];
    mpc.gencost(gi, 1:numel(cost)) = cost;

    rec = struct('name', s.name, 'profile', char(profile), 'bus_id', s.bus_id, ...
        'bus_name', s.bus_name, 'zone', s.zone, 'gen_index', gi, ...
        'pmax_mw', pmax, 'qmin_mvar', qmin, 'qmax_mvar', qmax, ...
        'cost_c2', options.cost_c2, 'cost_c1', options.cost_c1);
    if isempty(old)
        existing = append_struct(existing, rec);
        existing_names{end + 1} = s.name; %#ok<AGROW>
    else
        existing(old) = rec;
    end
    report = [report; struct2table(rec, 'AsArray', true)]; %#ok<AGROW>
end

mpc.userdata.ny_lite.downstate_equivalent_devices = existing;
mpc.userdata.ny_lite.downstate_equivalent_device_profile = char(profile);
end

function specs = default_specs()
specs = struct( ...
    'name', {'PV_HUDSON_SUPPORT', 'CE_UG_EQ_SUPPLY', 'GOETHALS_EQ_SUPPLY', ...
             'RAV_A3_EQ_SUPPLY', 'AK3_EQ_SUPPLY', 'NORTHPORT_EQ_SUPPLY'}, ...
    'bus_id', {73, 78, 81, 79, 82, 80}, ...
    'bus_name', {'PLEASANT VLY', 'CE UG', 'GOETHALS', 'RAV A-3', 'AK-3', 'NORTHPORT'}, ...
    'zone', {'G', 'I', 'J', 'J', 'J', 'K'}, ...
    'pmax_mw', {750, 1200, 1600, 1200, 1200, 1500}, ...
    'qmin_mvar', {-350, -600, -700, -500, -500, -700}, ...
    'qmax_mvar', {350, 600, 700, 500, 500, 700}, ...
    'vg_pu', {1.00, 1.00, 1.00, 1.00, 1.00, 1.00});
end

function out = append_struct(out, entry)
if isempty(out)
    out = entry;
else
    out(end + 1) = entry;
end
end
