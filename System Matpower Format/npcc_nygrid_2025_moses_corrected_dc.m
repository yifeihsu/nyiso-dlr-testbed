function mpc = npcc_nygrid_2025_moses_corrected_dc(hour_index, control, topology)
%NPCC_NYGRID_2025_MOSES_CORRECTED_DC Versioned source-backed allocation repair.
% The frozen148bus topology, generator outputs/bounds, loads and regional
% exchanges remain. Plant-specific Gold Book evidence corrects generator bus
% assignments. Any enabled PAR target must come from an independently verified
% source, never from a scored Moses South observation.
if nargin<1, hour_index=1; end
if nargin<2 || isempty(control), control='hydro_zone_corrected'; end
if nargin<3 || isempty(topology), topology='dated'; end
assert(any(strcmp(topology,{'dated','year_end'})), ...
    'mosesCorrection:Topology','Choose dated or year_end.');
assert(strcmp(control,'hydro_zone_corrected'), ...
    'mosesCorrection:Control','Only the confirmed hydro-zone repair is promoted. PAR orientation diagnostics are not operational cases.');
mpc=npcc_nygrid_2025_slim_dc(hour_index,['topology_',char(topology)]);
root=fileparts(fileparts(mfilename('fullpath')));
file=fullfile(root,'output','nygrid_2025_moses_audit','replay', ...
    [char(topology),'_',char(control),'.mat']);
assert(isfile(file),'mosesCorrection:MissingReplay','Build and validate this corrected variant first.');
persistent cached_file cached_signature r
info=dir(file);signature=[info.bytes,info.datenum];
if isempty(r)||~strcmp(cached_file,file)||~isequal(cached_signature,signature)
    r=load(file,'hour_index','qualified','corrected_generator_buses', ...
        'equivalent_shift_deg','source_control_branch_row');
    assert(isequal(r.hour_index(:),(1:8760)'),'mosesCorrection:HourAxis','Unexpected hour axis.');
    cached_file=file;cached_signature=signature;
end
assert(logical(r.qualified(hour_index)), ...
    'mosesCorrection:UnqualifiedHour','Required source data are incomplete for this hour.');
assert(numel(r.corrected_generator_buses)==size(mpc.gen,1), ...
    'mosesCorrection:GeneratorAxis','Corrected generator axis differs from the frozen dispatch.');
reference=mpc.bus(mpc.bus(:,2)==3,1);
mpc.gen(:,1)=r.corrected_generator_buses(:);
mpc.bus(:,2)=1;
mpc.bus(ismember(mpc.bus(:,1),mpc.gen(mpc.gen(:,8)==1,1)),2)=2;
assert(isscalar(reference)&&any(mpc.gen(:,1)==reference&mpc.gen(:,8)==1), ...
    'mosesCorrection:Reference','Corrected reference lacks an active generator.');
mpc.bus(mpc.bus(:,1)==reference,2)=3;
row=r.source_control_branch_row;
assert(row==211&&isequal(mpc.branch(row,1:2),[48 100]), ...
    'mosesCorrection:ControlIdentity','Original Moses-to-Ontario branch identity changed.');
mpc.branch(row,10)=r.equivalent_shift_deg(hour_index);
mpc.userdata.moses_correction=struct('control',control,'topology',topology, ...
    'source_generation_bus_correction',true,'frozen_unit_PG_and_bounds_preserved',true, ...
    'internal_interface_observations_used_for_fit',false, ...
    'equivalent_shift_is_measured_physical_PAR_tap',false,'DC_only',true);
end
