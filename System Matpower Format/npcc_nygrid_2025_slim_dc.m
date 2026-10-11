function mpc = npcc_nygrid_2025_slim_dc(hour_index, variant, artifact_folder)
%NPCC_NYGRID_2025_SLIM_DC Full NPCC plus eight critical345kV transmission buses.
% All140 original buses remain. Only43 zero-injection added buses from the
% detailed reference are eliminated. Equivalent branches are DC response
% representations and have no certified conductor, thermal rating or AC model.
% Use npcc_nygrid_2025_slim_interfaces(result) after a successful rundcpf to
% recover the same seven interface functionals as the191bus reference.
if nargin<1, hour_index=1; end
if nargin<2 || isempty(variant), variant='topology_dated'; end
root=fileparts(fileparts(mfilename('fullpath')));
if nargin<3 || isempty(artifact_folder)
    artifact_folder=fullfile(root,'output','nygrid_2025_slim');
end
assert(any(strcmp(variant,{'topology_dated','topology_year_end'})), ...
    'nygridSlim:Variant','Choose topology_dated or topology_year_end. Asset-remapping diagnostics are not supported.');
% Reuse frozen source qualification, per-generatorPG/bounds, signedDC schedules.
mpc=npcc_nygrid_2025_full_dc(hour_index);
reference=mpc.bus(mpc.bus(:,2)==3,1);
file=fullfile(artifact_folder,'network','network_cases.mat');
replay_file=fullfile(artifact_folder,'replay',[char(variant),'.mat']);
assert(isfile(file)&&isfile(replay_file),'nygridSlim:MissingArtifact','Build and replay the slim case first.');
persistent cached_folder cached_signature n cached_variant r r_signature
info=dir(file);signature=[info.bytes,info.datenum];
if isempty(n)||~strcmp(cached_folder,artifact_folder)||~isequal(cached_signature,signature)
    n=load(file);cached_folder=artifact_folder;cached_signature=signature;cached_variant='';
end
info=dir(replay_file);signature=[info.bytes,info.datenum];
if isempty(r)||~strcmp(cached_variant,variant)||~isequal(r_signature,signature)
    r=load(replay_file,'hour_index','qualified','network_state_ids','gamma');
    assert(isequal(r.hour_index(:),(1:8760)'),'nygridSlim:HourAxis','Unexpected saved hour axis.');
    cached_variant=variant;r_signature=signature;
end
assert(logical(r.qualified(hour_index)),'nygridSlim:UnqualifiedHour','Source-gap hour is unavailable.');
key=char(r.network_state_ids{hour_index});
state=strrep(key,'_case','');c=n.(key);recovery=n.recovery.(state);
assert(isequal(c.bus(1:140,1),mpc.bus(:,1))&&size(c.bus,1)==148,'nygridSlim:OriginalBuses','Original NPCC bus axis changed.');
loads=[mpc.bus(:,3:4);zeros(8,2)];
mpc.bus=c.bus;mpc.branch=c.branch;mpc.bus_name=c.bus_name(:);
mpc.bus(:,3:4)=loads;mpc.bus(:,9)=0;
mpc.bus(:,2)=1;
mpc.bus(ismember(mpc.bus(:,1),mpc.gen(mpc.gen(:,8)==1,1)),2)=2;
assert(isscalar(reference)&&any(mpc.gen(:,1)==reference&mpc.gen(:,8)==1), ...
    'nygridSlim:Reference','The frozen angle reference has no admitted generator.');
mpc.bus(mpc.bus(:,1)==reference,2)=3;
% An arbitrary new zone cut is not necessarily the original measurement.
% Expose all seven through the exact recovery operator, not stale if.map rows.
if isfield(mpc,'if'),mpc=rmfield(mpc,'if');end
mpc.userdata.nygrid2025.topology_modified=true;
mpc.userdata.slim=struct('variant',variant,'network_state',key,'bus_ids',c.bus(:,1), ...
    'interface_angle_matrix',recovery.interface_angle_matrix, ...
    'interface_flow_offset',recovery.interface_flow_offset(:),'gamma',r.gamma, ...
    'all_original_buses_retained',true,'added_buses',8,'DC_only',true, ...
    'equivalent_branch_thermal_qualification',false,'asset_remapping_supported',false, ...
    'interface_names',{{'DYSINGER EAST','WEST CENTRAL','TOTAL EAST','MOSES SOUTH', ...
                        'CENTRAL EAST - VC','UPNY CONED','SPR/DUN-SOUTH'}});
end
