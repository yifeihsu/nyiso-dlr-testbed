function [mpc_ny, report] = build_ny_only_equivalent_case(mpc, options)
%BUILD_NY_ONLY_EQUIVALENT_CASE Remove non-NY network from an NPCC case.

if nargin < 1 || isempty(mpc)
    mpc = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
elseif ischar(mpc) || isstring(mpc)
    mpc = loadcase(char(mpc));
end
if nargin < 2, options = struct(); end
if ~isfield(options, 'keep_all_ny_mapped_buses'), options.keep_all_ny_mapped_buses = true; end
if ~options.keep_all_ny_mapped_buses
    error('build_ny_only_equivalent_case:UnsupportedBusPolicy', ...
        'The current reduction requires all NY-mapped buses to be retained.');
end

helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
ny_mask = mpc.userdata.nyiso_zone_id > 0;
ny_bus_ids = mpc.bus(ny_mask, BUS_I);

keep_bus = ismember(mpc.bus(:, BUS_I), ny_bus_ids);
keep_branch = ismember(mpc.branch(:, F_BUS), ny_bus_ids) & ...
    ismember(mpc.branch(:, T_BUS), ny_bus_ids);
keep_gen = ismember(mpc.gen(:, GEN_BUS), ny_bus_ids);

mpc_ny = mpc;
mpc_ny.bus = mpc.bus(keep_bus, :);
mpc_ny.branch = mpc.branch(keep_branch, :);
mpc_ny.gen = mpc.gen(keep_gen, :);
if isfield(mpc, 'gencost') && size(mpc.gencost, 1) == size(mpc.gen, 1)
    mpc_ny.gencost = mpc.gencost(keep_gen, :);
end
% Keep row-aligned generator metadata aligned with the filtered matrix.
generator_fields = {'genfuel','gentype','gen_name'};
for k = 1:numel(generator_fields)
    name = generator_fields{k};
    if isfield(mpc, name) && numel(mpc.(name)) == size(mpc.gen, 1)
        values = mpc.(name);
        mpc_ny.(name) = values(keep_gen, :);
    end
end
if isfield(mpc, 'bus_name')
    mpc_ny.bus_name = mpc.bus_name(keep_bus);
end

mpc_ny = attach_nyiso_zone_metadata(mpc_ny);
mpc_ny.userdata.ny_only_equivalent = struct( ...
    'source_bus_count', size(mpc.bus, 1), ...
    'source_branch_count', size(mpc.branch, 1), ...
    'source_gen_count', size(mpc.gen, 1), ...
    'kept_bus_count', size(mpc_ny.bus, 1), ...
    'kept_branch_count', size(mpc_ny.branch, 1), ...
    'kept_gen_count', size(mpc_ny.gen, 1));

report = struct();
report.source_bus_count = size(mpc.bus, 1);
report.source_branch_count = size(mpc.branch, 1);
report.source_gen_count = size(mpc.gen, 1);
report.kept_bus_count = size(mpc_ny.bus, 1);
report.kept_branch_count = size(mpc_ny.branch, 1);
report.kept_gen_count = size(mpc_ny.gen, 1);
report.removed_bus_count = report.source_bus_count - report.kept_bus_count;
report.removed_branch_count = report.source_branch_count - report.kept_branch_count;
report.removed_gen_count = report.source_gen_count - report.kept_gen_count;
end
