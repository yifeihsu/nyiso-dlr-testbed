function [m,change]=nyrepair_apply_case(m)
% Apply the source-conditioned line repair and fixed-rating reactor relocation.
% Authoring/annual-analysis helper; the final runtime uses compiled templates.
assert(~isfield(m.userdata,'physical_repair'),'nyrepair:AlreadyApplied','The physical repair is already applied.');
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'scripts','nygrid_2025_physical_repair','physics'));
before=m;[m,p41]=nyrepair_apply_parent41(m);[m,comp]=nyrepair_apply_185195(m);
assert(isequal(m.bus(:,[1:5 7:end]),before.bus(:,[1:5 7:end])));
assert(isequal(m.gen,before.gen)&&isequal(m.dcline,before.dcline));
assert(isequal(m.userdata.latest_runtime,before.userdata.latest_runtime));
assert(isequal(m.userdata.ac_system.branch_keys,before.userdata.ac_system.branch_keys));
assert(isequal(m.userdata.ac_system.branch_parent_row,before.userdata.ac_system.branch_parent_row));
assert(isequaln(m.userdata.ac_system.terminal_current_limits,before.userdata.ac_system.terminal_current_limits));
change=struct('schema_version',1,'model_revision','physical_repair_41_185_195_20261015', ...
    'parent41',p41,'compensation',comp,'source_profiles_and_controls_unchanged',true, ...
    'bus_branch_generator_axes_unchanged',true,'voltage_limits_and_PV_setpoints_unchanged',true, ...
    'physical_installed_asset_claimed',false,'observed_interface_data_used_for_parameter_selection',false);
m.userdata.physical_repair=change;
end
