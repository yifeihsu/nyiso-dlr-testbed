function mpc = attach_nyiso_zone_metadata(mpc)
%ATTACH_NYISO_ZONE_METADATA Store physical and allocation-zone metadata.

[map, zones] = nyiso_bus_zone_map;
ZONE = 11;
n_bus = size(mpc.bus, 1);
physical_zone = repmat({''}, n_bus, 1);
load_group = repmat({''}, n_bus, 1);
zone_name = repmat({''}, n_bus, 1);
zone_id = zeros(n_bus, 1);
perform_zone_code = zeros(n_bus, 1);

for k = 1:numel(map)
    idx = find(mpc.bus(:, 1) == map(k).bus_id, 1);
    if isempty(idx)
        error('attach_nyiso_zone_metadata:MissingBus', ...
            'Bus %d from the NYISO map is missing from the case.', map(k).bus_id);
    end
    physical_zone{idx} = map(k).physical_zone;
    load_group{idx} = map(k).load_allocation_group;
    zone_name{idx} = map(k).nyiso_zone_name;
    zone_id(idx) = map(k).nyiso_zone_id;
    perform_zone_code(idx) = map(k).perform_zone_code;
    mpc.bus(idx, ZONE) = map(k).perform_zone_code;
end

if isfield(mpc, 'userdata') && isfield(mpc.userdata, 'ny_lite') && ...
        isfield(mpc.userdata.ny_lite, 'transit_zone_metadata')
    custom = mpc.userdata.ny_lite.transit_zone_metadata;
    for k = 1:numel(custom)
        idx = find(mpc.bus(:, 1) == custom(k).bus_id, 1);
        if isempty(idx), continue; end
        physical_zone{idx} = custom(k).physical_zone;
        load_group{idx} = custom(k).load_allocation_group;
        zone_name{idx} = custom(k).nyiso_zone_name;
        zone_id(idx) = custom(k).nyiso_zone_id;
        perform_zone_code(idx) = custom(k).perform_zone_code;
        mpc.bus(idx, ZONE) = custom(k).perform_zone_code;
    end
end

% Transit-bus zone defaults.
%
% Buses 9001/9002/9003 are the three zero-load transit buses added by
% add_ny_downstate_delivery_spine. They are deliberately absent from
% nyiso_bus_zone_map (which errors on any mapped bus the case does not
% contain, and must stay loadable against the 140-bus baseline), so cases
% normally carry them in userdata.ny_lite.transit_zone_metadata.
%
% The 49-bus S11/DLR case does not carry that userdata, which left 9001 and
% 9003 with an empty physical_zone. Any zone-cut interface operator - such as
% legacy_definitions in ny_lite_interface_definitions - matches on zone pairs,
% so every branch touching an unzoned bus was silently dropped from its
% interface. For 9003 that removed the CE UG -> East Garden City I-K crossing
% (Con Ed-LIPA) from the cutset entirely.
%
% Zones are the PERFORM area field for the corresponding substation:
% WOOD STREET and EAST GARDEN CITY are areas 71 (G) and 75 (K). KNICKERBOCKER
% has no PERFORM counterpart; it is a synthetic transit node inserted on the
% Leeds-Pleasant Valley path, and both of its neighbours are zone G, so G
% keeps that path intra-zone. Labelling it F would manufacture two spurious
% F-G crossings and corrupt the Total East cut.
%
% Defaults fill only where a zone is still unset, so an explicit
% transit_zone_metadata entry always wins. The 9002 assignment is applied
% unconditionally because it also corrects a stale zone-H classification
% embedded in older S7 cases.
transit_defaults = struct( ...
    'bus_id',      {9001,     9002,     9003}, ...
    'zone',        {'G',      'G',      'K'}, ...
    'zone_name',   {'HUD VL', 'HUD VL', 'LONGIL'}, ...
    'zone_id',     {7,        7,        11}, ...
    'perform_code',{71,       71,       75}, ...
    'force',       {false,    true,     false});
for k = 1:numel(transit_defaults)
    idx = find(mpc.bus(:, 1) == transit_defaults(k).bus_id, 1);
    if isempty(idx), continue; end
    if ~transit_defaults(k).force && ~isempty(physical_zone{idx}), continue; end
    physical_zone{idx} = transit_defaults(k).zone;
    load_group{idx} = transit_defaults(k).zone;
    zone_name{idx} = transit_defaults(k).zone_name;
    zone_id(idx) = transit_defaults(k).zone_id;
    perform_zone_code(idx) = transit_defaults(k).perform_code;
    mpc.bus(idx, ZONE) = transit_defaults(k).perform_code;
end

mpc.userdata.nyiso_zone = physical_zone;              % backward-compatible alias
mpc.userdata.nyiso_physical_zone = physical_zone;
mpc.userdata.nyiso_load_allocation_group = load_group;
mpc.userdata.nyiso_zone_name = zone_name;
mpc.userdata.nyiso_zone_id = zone_id;
mpc.userdata.perform_zone_code = perform_zone_code;
mpc.userdata.nyiso_zones = zones;
mpc.userdata.ny_bus_zone_map = map;
end
