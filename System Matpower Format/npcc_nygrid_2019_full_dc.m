function mpc=npcc_nygrid_2019_full_dc(hour_index,artifact_folder)
%NPCC_NYGRID_2019_FULL_DC Full140-bus paper-derived2019 DC research case.
% hour_index1 is the authors' prepared2019-01-01 00:00 local label.
% This loader preserves full-system topology and paper DC-device semantics.
% It does not qualify AC capability, installed conductors, or hourly economics.
% Optional artifact_folder selects an alternate full_year.mat reproduction.
if nargin<1,hour_index=1;end
assert(isnumeric(hour_index)&&isscalar(hour_index)&&isfinite(hour_index) ...
    &&hour_index==fix(hour_index)&&hour_index>=1&&hour_index<=8760, ...
    'nygrid:HourIndex','Use an integer prepared2019 hour index from1 through8760.');
root=fileparts(fileparts(mfilename('fullpath')));
if nargin<2||isempty(artifact_folder),artifact_folder=fullfile(root,'output','nygrid_2019_full_stage1');end
folder=artifact_folder;
file=fullfile(folder,'full_year.mat');
assert(isfile(file),'nygrid:MissingBaseline','Run scripts/nygrid_2019_full reproduction first.');
d=load(file,'base_case','hour_index','bus_pd','bus_qd','input_pg','gen_pmax','dc_pf');
assert(isequal(d.hour_index(:),(1:8760)')&&size(d.bus_pd,1)==8760, ...
    'nygrid:Coverage','Saved full-year baseline is incomplete.');
mpc=d.base_case;
mpc.baseMVA=double(mpc.baseMVA);
if isfield(mpc,'genfuel'),mpc.genfuel=mpc.genfuel(:);end
assert(size(mpc.bus,1)==140&&size(mpc.branch,1)==225&&size(mpc.gen,1)==271 ...
    &&size(mpc.dcline,1)==4,'nygrid:Inventory','Unexpected full2019 inventory.');
mpc.bus(:,3)=d.bus_pd(hour_index,:)';mpc.bus(:,4)=d.bus_qd(hour_index,:)';
mpc.gen(:,2)=d.input_pg(hour_index,:)';mpc.gen(:,9)=d.gen_pmax(hour_index,:)';
mpc.dcline(:,4)=d.dc_pf(hour_index,:)';
% Static cost metadata from a captured hour is not a full-year bidding model.
if isfield(mpc,'gencost'),mpc=rmfield(mpc,'gencost');end
if isfield(mpc,'if')&&isfield(mpc.if,'lims'),mpc.if=rmfield(mpc.if,'lims');end
mpc=toggle_dcline(mpc,'on');
mpc.userdata.nygrid2019=struct('hour_index',hour_index,'model_year',2019, ...
    'prepared_local_label',char(string(datetime(2019,1,1)+hours(hour_index-1),'yyyy-MM-dd HH:mm:ss')), ...
    'source_commit','47698b6c7823ae7b1bc6935e5601d5b64b8f918e', ...
    'dc_only',true,'ac_feasibility_validated',false,'generation_bounds_enforced',false, ...
    'installed_conductors_verified',false,'hourly_economic_costs_available',false, ...
    'hourly_ramp_metadata_available',false, ...
    'hourly_interface_constraints_available',false, ...
    'time_policy','authors naive local labels; spring interpolation and repeated-fall-hour averaging retained');
end
