function [mpc, added] = add_ny_downstate_delivery_spine(mpc, profile, options)
%ADD_NY_DOWNSTATE_DELIVERY_SPINE Add staged zero-load downstate delivery paths.
%   Profiles:
%     none          no topology changes
%     lower_hudson  Gilboa-Leeds plus Pleasant Valley/Wood/Millwood/CE UG
%     nyc_mesh      lower_hudson plus CE UG to NYC proxy mesh
%     li            nyc_mesh plus East Garden City/Northport delivery
%     segment_b     li plus Leeds/Knickerbocker/Pleasant Valley
%     full          alias for segment_b

if nargin < 2 || isempty(profile), profile = 'full'; end
if nargin < 3, options = struct(); end
if ~isfield(options, 'on_existing'), options.on_existing = 'skip'; end

helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

mpc = attach_nyiso_zone_metadata(mpc);
if ~isfield(mpc, 'userdata'), mpc.userdata = struct(); end
if ~isfield(mpc.userdata, 'ny_lite'), mpc.userdata.ny_lite = struct(); end
if ~isfield(mpc.userdata.ny_lite, 'original_branch_count')
    mpc.userdata.ny_lite.original_branch_count = size(mpc.branch, 1);
end
if ~isfield(mpc.userdata.ny_lite, 'added_tielines')
    mpc.userdata.ny_lite.added_tielines = struct([]);
end

[bus_specs, branch_specs] = spine_specs();
selected_names = selected_branch_names(profile);
if isempty(selected_names)
    added = struct('profile', string(profile), 'buses', struct([]), ...
        'branches', struct([]));
    mpc.userdata.ny_lite.downstate_delivery_profile = profile;
    return;
end

needed_buses = required_transit_buses(branch_specs, selected_names);
added_buses = struct([]);
for k = 1:numel(bus_specs)
    if any(strcmp(bus_specs(k).name, needed_buses))
        [mpc, bus_added] = add_transit_bus(mpc, bus_specs(k));
        if bus_added
            added_buses = append_struct(added_buses, bus_specs(k));
        end
    end
end
mpc = install_transit_metadata(mpc, bus_specs);
mpc = attach_nyiso_zone_metadata(mpc);

existing_names = existing_added_names(mpc);
added_branches = struct([]);
for k = 1:numel(branch_specs)
    b = branch_specs(k);
    if ~any(strcmp(b.name, selected_names)), continue; end
    if any(strcmp(b.name, existing_names))
        if strcmpi(options.on_existing, 'error')
            error('add_ny_downstate_delivery_spine:AlreadyAdded', ...
                'Delivery-spine branch %s has already been added.', b.name);
        end
        continue;
    end
    assert_bus_present(mpc, b.from_bus);
    assert_bus_present(mpc, b.to_bus);

    ncol = max(13, size(mpc.branch, 2));
    new_branch = zeros(1, ncol);
    new_branch(1:13) = [b.from_bus, b.to_bus, b.br_r_initial, b.br_x_initial, ...
        b.br_b_initial, b.rate_a_initial, b.rate_b_initial, b.rate_c_initial, ...
        0, 0, 1, -360, 360];
    mpc.branch = [mpc.branch; new_branch];

    tagged = b;
    tagged.branch_index = size(mpc.branch, 1);
    added_branches = append_struct(added_branches, tagged);
    existing_names{end + 1} = b.name; %#ok<AGROW>
end

if ~isempty(added_branches)
    if isempty(mpc.userdata.ny_lite.added_tielines)
        mpc.userdata.ny_lite.added_tielines = added_branches;
    else
        mpc.userdata.ny_lite.added_tielines = ...
            [mpc.userdata.ny_lite.added_tielines, added_branches];
    end
end

mpc.userdata.ny_lite.downstate_delivery_profile = profile;
mpc.userdata.ny_lite.downstate_delivery_added_buses = added_buses;
mpc.userdata.ny_lite.downstate_delivery_added_branches = added_branches;
added = struct('profile', string(profile), 'buses', added_buses, ...
    'branches', added_branches);
end

function [bus_specs, branch_specs] = spine_specs()
bus_specs = struct( ...
    'name', {'KNICKERBOCKER', 'WOOD_STREET', 'EAST_GARDEN_CITY'}, ...
    'bus_id', {9001, 9002, 9003}, ...
    'bus_name', {'KNICKERBOCKER', 'WOOD STREET', 'EAST GARDEN CITY'}, ...
    'template_bus', {73, 74, 80}, ...
    'base_kv', {345, 345, 345}, ...
    'physical_zone', {'G', 'G', 'K'}, ...
    'load_allocation_group', {'G', 'G', 'K'}, ...
    'nyiso_zone_name', {'HUD VL', 'HUD VL', 'LONGIL'}, ...
    'nyiso_zone_id', {7, 7, 11}, ...
    'perform_zone_code', {71, 71, 75});

branch_specs = struct( ...
    'name', {}, 'from_bus', {}, 'to_bus', {}, 'interface', {}, ...
    'br_r_initial', {}, 'br_x_initial', {}, 'br_b_initial', {}, ...
    'rate_a_initial', {}, 'rate_b_initial', {}, 'rate_c_initial', {}, ...
    'include_default', {}, 'stage', {});
branch_specs(end + 1) = branch('GILBOA_LEEDS', 38, 39, 'Total East seed', ...
    0.00131, 0.01997, 0.51614, 1216, 2454, 1804, 'lower_hudson');
branch_specs(end + 1) = branch('PLEASANT_VLY_WOOD_STREET', 73, 9002, ...
    'UPNY-ConEd delivery', 0.00150, 0.02500, 0, 5000, 5000, 5000, 'lower_hudson');
branch_specs(end + 1) = branch('WOOD_STREET_MILLWOOD', 9002, 74, ...
    'UPNY-ConEd delivery', 0.00120, 0.02000, 0, 5000, 5000, 5000, 'lower_hudson');
branch_specs(end + 1) = branch('MILLWOOD_CE_UG_DELIVERY', 74, 78, ...
    'Millwood/Dunwoodie entry', 0.00090, 0.01500, 0, 5000, 5000, 5000, 'lower_hudson');
branch_specs(end + 1) = branch('BUCHANAN_CE_UG_DELIVERY', 77, 78, ...
    'Millwood/Dunwoodie entry', 0.00120, 0.02000, 0, 5000, 5000, 5000, 'lower_hudson');
branch_specs(end + 1) = branch('CE_UG_GOETHALS_DELIVERY', 78, 81, ...
    'NYC proxy mesh', 0.00072, 0.01200, 0, 5000, 5000, 5000, 'nyc_mesh');
branch_specs(end + 1) = branch('CE_UG_RAV_A3_DELIVERY', 78, 79, ...
    'NYC proxy mesh', 0.00060, 0.01000, 0, 5000, 5000, 5000, 'nyc_mesh');
branch_specs(end + 1) = branch('CE_UG_AK3_DELIVERY', 78, 82, ...
    'NYC proxy mesh', 0.00060, 0.01000, 0, 5000, 5000, 5000, 'nyc_mesh');
branch_specs(end + 1) = branch('CE_UG_EAST_GARDEN_CITY', 78, 9003, ...
    'ConEd-LIPA delivery', 0.00120, 0.02000, 0, 5000, 5000, 5000, 'li');
branch_specs(end + 1) = branch('EAST_GARDEN_CITY_NORTHPORT', 9003, 80, ...
    'ConEd-LIPA delivery', 0.00120, 0.02000, 0, 5000, 5000, 5000, 'li');
branch_specs(end + 1) = branch('GOETHALS_NORTHPORT_DELIVERY', 81, 80, ...
    'ConEd-LIPA delivery', 0.00180, 0.03000, 0, 5000, 5000, 5000, 'li');
branch_specs(end + 1) = branch('LEEDS_KNICKERBOCKER', 39, 9001, ...
    'Segment B / UPNY-SENY', 0.00210, 0.03500, 0, 5000, 5000, 5000, 'segment_b');
branch_specs(end + 1) = branch('KNICKERBOCKER_PLEASANT_VLY', 9001, 73, ...
    'Segment B / UPNY-SENY', 0.00150, 0.02500, 0, 5000, 5000, 5000, 'segment_b');
end

function b = branch(name, fbus, tbus, interface, r, x, bc, rate_a, rate_b, rate_c, stage)
b = struct('name', name, 'from_bus', fbus, 'to_bus', tbus, ...
    'interface', interface, 'br_r_initial', r, 'br_x_initial', x, ...
    'br_b_initial', bc, 'rate_a_initial', rate_a, ...
    'rate_b_initial', rate_b, 'rate_c_initial', rate_c, ...
    'include_default', true, 'stage', stage);
end

function names = selected_branch_names(profile)
profile = lower(string(profile));
stage_order = ["lower_hudson", "nyc_mesh", "li", "segment_b"];
if profile == "full", profile = "segment_b"; end
if profile == "none"
    names = {};
    return;
end
[~, branch_specs] = spine_specs();
stages = string({branch_specs.stage});
idx = find(stage_order == profile, 1);
if isempty(idx)
    known = ["none", stage_order, "full"];
    error('add_ny_downstate_delivery_spine:UnknownProfile', ...
        'Unknown delivery-spine profile %s. Known profiles: %s.', ...
        profile, strjoin(known, ', '));
end
selected_stages = stage_order(1:idx);
names = {branch_specs(ismember(stages, selected_stages)).name};
end

function needed = required_transit_buses(branch_specs, selected_names)
needed = {};
for k = 1:numel(branch_specs)
    if ~any(strcmp(branch_specs(k).name, selected_names)), continue; end
    for bus_id = [branch_specs(k).from_bus, branch_specs(k).to_bus]
        switch bus_id
            case 9001
                needed{end + 1} = 'KNICKERBOCKER'; %#ok<AGROW>
            case 9002
                needed{end + 1} = 'WOOD_STREET'; %#ok<AGROW>
            case 9003
                needed{end + 1} = 'EAST_GARDEN_CITY'; %#ok<AGROW>
        end
    end
end
needed = unique(needed, 'stable');
end

function [mpc, was_added] = add_transit_bus(mpc, spec)
define_constants;
was_added = false;
if any(mpc.bus(:, BUS_I) == spec.bus_id)
    return;
end
template_idx = find(mpc.bus(:, BUS_I) == spec.template_bus, 1);
if isempty(template_idx)
    error('add_ny_downstate_delivery_spine:MissingTemplateBus', ...
        'Template bus %.0f is not present.', spec.template_bus);
end
ncol = size(mpc.bus, 2);
new_bus = mpc.bus(template_idx, 1:ncol);
new_bus(BUS_I) = spec.bus_id;
new_bus(BUS_TYPE) = PQ;
new_bus(PD) = 0;
new_bus(QD) = 0;
new_bus(GS) = 0;
new_bus(BS) = 0;
new_bus(BASE_KV) = spec.base_kv;
new_bus(ZONE) = spec.perform_zone_code;
mpc.bus = [mpc.bus; new_bus];
mpc = append_bus_name(mpc, spec.bus_name);
was_added = true;
end

function mpc = append_bus_name(mpc, name)
if ~isfield(mpc, 'bus_name'), return; end
if iscell(mpc.bus_name)
    mpc.bus_name{end + 1, 1} = name;
elseif isstring(mpc.bus_name)
    mpc.bus_name(end + 1, 1) = string(name);
else
    mpc.bus_name = [cellstr(mpc.bus_name); {name}];
end
end

function mpc = install_transit_metadata(mpc, bus_specs)
if ~isfield(mpc, 'userdata'), mpc.userdata = struct(); end
if ~isfield(mpc.userdata, 'ny_lite'), mpc.userdata.ny_lite = struct(); end
metadata = struct([]);
for k = 1:numel(bus_specs)
    if any(mpc.bus(:, 1) == bus_specs(k).bus_id)
        entry = rmfield(bus_specs(k), {'name', 'bus_name', 'template_bus', 'base_kv'});
        metadata = append_struct(metadata, entry);
    end
end
mpc.userdata.ny_lite.transit_zone_metadata = metadata;
end

function names = existing_added_names(mpc)
names = {};
if isfield(mpc.userdata.ny_lite, 'added_tielines') && ...
        ~isempty(mpc.userdata.ny_lite.added_tielines) && ...
        isfield(mpc.userdata.ny_lite.added_tielines, 'name')
    names = {mpc.userdata.ny_lite.added_tielines.name};
end
end

function assert_bus_present(mpc, bus_id)
if ~any(mpc.bus(:, 1) == bus_id)
    error('add_ny_downstate_delivery_spine:MissingBus', ...
        'Bus %.0f is not present in the case.', bus_id);
end
end

function out = append_struct(out, entry)
if isempty(out)
    out = entry;
else
    out(end + 1) = entry;
end
end
