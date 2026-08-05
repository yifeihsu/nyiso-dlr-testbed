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

% Correct a stale transit-bus classification embedded in older S7 cases.
% PERFORM bus 902 WOOD STREET is zone G; only MILLWOOD (bus 897) is zone H.
wood = find(mpc.bus(:, 1) == 9002, 1);
if ~isempty(wood)
    physical_zone{wood} = 'G';
    load_group{wood} = 'G';
    zone_name{wood} = 'HUD VL';
    zone_id(wood) = 7;
    perform_zone_code(wood) = 71;
    mpc.bus(wood, ZONE) = 71;
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
