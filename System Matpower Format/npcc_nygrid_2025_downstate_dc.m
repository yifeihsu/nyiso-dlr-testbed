function mpc = npcc_nygrid_2025_downstate_dc(hour_index, variant, artifact_folder)
%NPCC_NYGRID_2025_DOWNSTATE_DC Expanded full-NPCC fixed-dispatch DC research case.
% Default: dated2025 topology with the frozen baseline injection landings.
% Asset mapping variants are diagnostic, pending load/flowgate qualification.
% Public station/project facts and assumed impedances are in the registers.
% Neither AC feasibility nor physical2025 flowgate membership is certified.
if nargin < 1, hour_index = 1; end
if nargin < 2 || isempty(variant), variant = 'upgrades_dated'; end
root = fileparts(fileparts(mfilename('fullpath')));
if nargin < 3 || isempty(artifact_folder)
    artifact_folder = fullfile(root, 'output', 'nygrid_2025_downstate');
end
allowed = {'expanded_identity', 'source_detail_2019', 'upgrades_year_end', ...
    'upgrades_dated', 'assets_year_end', 'assets_dated', 'nyes_assumption_year_end'};
assert(any(strcmp(variant, allowed)), 'nygridDownstate:Variant', 'Unknown refinement variant.');
% This loader enforces the source cohort and restores the frozen hourly PG,
% PMIN/PMAX, DC schedules and reference policy before applying network changes.
mpc = npcc_nygrid_2025_full_dc(hour_index);
ref = mpc.bus(mpc.bus(:, 2) == 3, 1);
network_file = fullfile(artifact_folder, 'network', 'network_cases.mat');
replay_file = fullfile(artifact_folder, 'replay', [char(variant), '.mat']);
assert(isfile(network_file) && isfile(replay_file), 'nygridDownstate:MissingArtifact', ...
    'Build and replay the refinement first.');
persistent cached_folder cached_signature n cached_variant replay_signature r
file = dir(network_file);
signature = [file.bytes, file.datenum];
if isempty(n) || ~strcmp(cached_folder, artifact_folder) || ~isequal(cached_signature, signature)
    n = load(network_file);
    cached_folder = artifact_folder;
    cached_signature = signature;
    cached_variant = '';
end
file = dir(replay_file);
signature = [file.bytes, file.datenum];
if isempty(r) || ~strcmp(cached_variant, variant) || ~isequal(replay_signature, signature)
    r = load(replay_file, 'hour_index', 'qualified', 'network_state_ids', ...
        'load_allocation_name', 'generator_mapping_name', 'gamma');
    assert(isequal(r.hour_index(:), (1:8760)'), 'nygridDownstate:HourAxis', 'Replay hour axis changed.');
    cached_variant = variant;
    replay_signature = signature;
end
assert(logical(r.qualified(hour_index)), 'nygridDownstate:UnqualifiedHour', 'Unqualified refinement hour.');
key = char(r.network_state_ids{hour_index});
network_case = n.(key);
W = n.(['load_allocation_', char(r.load_allocation_name)]);
pd = W * mpc.bus(:, 3);
qd = W * mpc.bus(:, 4);
mpc.bus = network_case.bus;
mpc.branch = network_case.branch;
mpc.bus_name = network_case.bus_name(:);
mpc.gen(:, 1) = n.(['generator_bus_', char(r.generator_mapping_name)]);
mpc.bus(:, 3:4) = [pd, qd];
mpc.bus(:, 9) = 0;
mpc.bus(:, 2) = 1;
mpc.bus(ismember(mpc.bus(:, 1), mpc.gen(mpc.gen(:, 8) == 1, 1)), 2) = 2;
assert(isscalar(ref) && any(mpc.gen(:, 1) == ref & mpc.gen(:, 8) == 1), 'nygridDownstate:Reference', ...
    'Frozen reference bus has no online generator.');
mpc.bus(mpc.bus(:, 1) == ref, 2) = 3;
% Rebuild the same accounting-zone functionals on active refined branches.
from_groups = {'A', 'B', 'ABCDE', 'D', 'E', 'ABCDEFG', 'I'};
to_groups = {'B', 'C', 'FGHIJK', 'E', 'F', 'HIJK', 'J'};
ids = [1, 2, 3, 4, 5, 8, 10];
[~, from] = ismember(mpc.branch(:, 1), mpc.bus(:, 1));
[~, to] = ismember(mpc.branch(:, 2), mpc.bus(:, 1));
zones = string(n.bus_zones(:));
map = zeros(0, 2);
for j = 1:numel(ids)
    a = cellstr(from_groups{j}'); b = cellstr(to_groups{j}');
    signs = double(ismember(zones(from), a) & ismember(zones(to), b)) ...
        - double(ismember(zones(to), a) & ismember(zones(from), b));
    selected = find(signs ~= 0 & mpc.branch(:, 11) == 1);
    map = [map; repmat(ids(j), numel(selected), 1), selected .* signs(selected)]; %#ok<AGROW>
end
mpc.if = struct('map', map);
mpc.userdata.nygrid2025.topology_modified = true;
mpc.userdata.downstate_refinement = struct('variant', variant, 'network_state', key, ...
    'injection_mapping', char(r.load_allocation_name), 'all_original_NPCC_buses_retained', true, ...
    'same_per_device_PG_and_bounds', true, 'legacy_accounting_zone_interfaces', true, ...
    'physical_2025_flowgate_membership_verified', false, 'as_built_parameters_verified', false, ...
    'internal_interface_observations_used', false, 'gamma', r.gamma);
end
