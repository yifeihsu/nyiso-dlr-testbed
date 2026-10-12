function [mpc,limits,segments,conductors]=ac_dlr_prepare_case(mpc,weather,temperature_policy)
%AC_DLR_PREPARE_CASE Attach all active OH current constraints to the AC case.
% Source-derived prior cases are never rewritten. All original boundary
% controls, generator constraints and objective terms survive this adapter.
% Reference mode evaluates the declared hot-conductor reference resistance;
% supplied temperatures must have one entry per active segment.
if nargin<3,temperature_policy='reference';end
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format','NY_Lite'));
folder=fullfile(root,'output','nygrid_2025_ac_system');
if isfield(mpc,'userdata')&&isfield(mpc.userdata,'ac_system')&&isfield(mpc.userdata.ac_system,'thermal_segments')
    segments=mpc.userdata.ac_system.thermal_segments;
else
    segments=readtable(fullfile(folder,'branches','thermal_segments.csv'),'TextType','string');
end
if iscell(segments),segments=struct2table([segments{:}]);elseif isstruct(segments),segments=struct2table(segments);end
segments.branch_key=string(segments.branch_key);segments.segment_id=string(segments.segment_id);
segments.catalog_id=string(segments.catalog_id);
for name={'branch_row','circuits','bundle_count'}
    segments.(name{1})=double(segments.(name{1}));
end
conductors=readtable(fullfile(folder,'engineering','thermal_conductors.csv'),'TextType','string');
assert(isfield(mpc,'userdata')&&isfield(mpc.userdata,'ac_system') ...
    &&isfield(mpc.userdata.ac_system,'branch_keys')&&~mpc.userdata.ac_system.current_gamma_lift, ...
    'acDLR:CaseIdentity','Use the explicitly identified synthetic AC study case.');
assert(isfield(mpc.userdata.ac_system,'terminal_current_constraints_applied') ...
    &&mpc.userdata.ac_system.terminal_current_constraints_applied, ...
    'acDLR:HardwareLimits','Attach the actual-voltage terminal current limits before conductor DLR.');
within=segments.branch_row<=size(mpc.branch,1);segments=segments(within,:);
active=mpc.branch(segments.branch_row,11)>0;segments=segments(active,:);
assert(height(segments)>0,'acDLR:NoLines','No active overhead thermal segments are available.');
keys=string(mpc.userdata.ac_system.branch_keys(:));
assert(all(keys(segments.branch_row)==segments.branch_key),'acDLR:Identity','Branch identities changed.');
if ischar(temperature_policy)||isstring(temperature_policy)
    assert(strcmp(temperature_policy,'reference'),'acDLR:TemperaturePolicy','Choose reference or explicit per-segment temperatures.');
    temperature=segments.reference_temperature_c;
else
    temperature=temperature_policy(:);
    assert(numel(temperature)==height(segments),'acDLR:TemperatureAxes','Temperature axes differ from active segment axes.');
end
before=mpc;
mpc=ac_dlr_apply_resistance(mpc,segments,conductors,temperature);
limits=ac_dlr_limits(mpc,segments,conductors,weather);
% The existing validated series-current callback uses multiplicity=1 here
% because heterogeneous segment limits have already become total phase amps.
mpc=add_dlr_series_current_constraints(mpc,limits.branch,limits.branch.series_phase_limit_a);
envelope=table(limits.branch.branch_row,limits.branch.series_phase_limit_a,limits.branch.series_phase_limit_a, ...
    'VariableNames',{'branch_row','total_terminal_current_limit_from_a','total_terminal_current_limit_to_a'});
mpc=add_ac_terminal_current_limits(mpc,envelope,'conductor_section_end_ampacity');
mpc.userdata.ac_system.thermal_constraints_applied=true;
assert(isequal(mpc.gen,before.gen)&&isequal(mpc.dcline,before.dcline)&&isequal(mpc.gencost,before.gencost) ...
    &&isequal(mpc.bus,before.bus),'acDLR:Preservation','Thermal adapter changed electrical inputs or controls.');
mpc.userdata.ac_dlr=struct('temperature_c',temperature,'segment_keys',segments.branch_key+"::"+segments.segment_id, ...
    'branch_rows',limits.branch.branch_row,'series_phase_limit_a',limits.branch.series_phase_limit_a, ...
    'reference_temperature_is_not_solved_equilibrium',ischar(temperature_policy)||isstring(temperature_policy), ...
    'uniform_weather_scenario',height(weather)==1,'weather_is_observed',false, ...
    'all_active_overhead_segments_constrained',true,'no_gamma_current_rescaling',true, ...
    'conductor_section_ends_also_current_limited',true,'exact_continuous_along_route_maximum_certified',false, ...
    'equipment_terminal_MVA_limits_retained',true);
end
