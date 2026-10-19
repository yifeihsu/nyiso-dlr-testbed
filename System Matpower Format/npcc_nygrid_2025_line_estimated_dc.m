function mpc = npcc_nygrid_2025_line_estimated_dc(hour_index, topology, scenario)
%NPCC_NYGRID_2025_LINE_ESTIMATED_DC Source-informed project parameter scenario.
% F84 uses a project-design Mallard ACSS/geometry estimate; Staten uses its
% documented9.4mi route with the qualified historical cable impedance analog.
% Dover line-only estimates are not substituted for missing PAR impedances.
% The148bus case remains DC-only; Schur edges are not physical conductors.
if nargin<1, hour_index=1; end
if nargin<2 || isempty(topology), topology='dated'; end
if nargin<3 || isempty(scenario), scenario='engineering_nominal'; end
assert(any(strcmp(scenario,{'identity_reference','engineering_nominal', ...
    'geometry_spacing_80pct','geometry_spacing_120pct','ground_image_30ft'})), ...
    'lineEstimate:Scenario','Unknown engineering scenario.');
mpc=npcc_nygrid_2025_western_corrected_dc(hour_index,topology,'combined');
root=fileparts(fileparts(mfilename('fullpath')));
folder=fullfile(root,'output','nygrid_2025_line_parameters','overlays',char(scenario));
file=fullfile(folder,'network_cases.mat');proof_file=fullfile(folder,'overlay_receipt.json');
assert(isfile(file)&&isfile(proof_file),'lineEstimate:MissingArtifact','Build and validate the parameter overlay first.');
persistent cached_file cached_signature n
info=dir(file);pinfo=dir(proof_file);signature=[info.bytes info.datenum pinfo.bytes pinfo.datenum];
if isempty(n)||~strcmp(cached_file,file)||~isequal(cached_signature,signature)
    proof=jsondecode(fileread(proof_file));
    assert(proof.passed&&~proof.observed_interface_flows_used ...
        &&strcmp(proof.scenario_name,scenario), 'lineEstimate:Proof','Unqualified parameter overlay.');
    assert(strcmp(file_sha256(file),proof.outputs.network_cases_mat), ...
        'lineEstimate:ChangedArtifact','Saved case differs from its validated overlay receipt.');
    n=load(file);cached_file=file;cached_signature=signature;
end
key=mpc.userdata.slim.network_state;state=strrep(key,'_case','');
c=n.(key);rec=n.recovery.(state);
assert(isequal(c.bus(:,1),mpc.bus(:,1))&&size(c.bus,1)==148 ...
    &&isequal(c.branch(:,1:2),mpc.branch(:,1:2))&&size(c.branch,1)==274, ...
    'lineEstimate:Axes','The retained bus/branch identity axes changed.');
assert(size(mpc.dcline,1)==6&&mpc.branch(211,11)==0&&c.branch(211,11)==1, ...
    'lineEstimate:ControlIdentity','Expected original four DC transfers and two external PAR equivalents.');
active=c.branch(:,11);active(211)=0;
assert(isequal(active,mpc.branch(:,11)), ...
    'lineEstimate:Topology','Parameter overlay changed the dated topology.');
mpc.branch=c.branch;mpc.branch(211,11)=0;
mpc.userdata.slim.interface_angle_matrix=rec.interface_angle_matrix;
mpc.userdata.slim.interface_flow_offset=rec.interface_flow_offset(:);
mpc.userdata.line_estimation=struct('scenario',char(scenario), ...
    'source_parameter_file_sha256',file_sha256(file), ...
    'engineering_estimates_not_asbuilt_measurements',true, ...
    'physical_flowgates_certified',false,'AC_equivalent',false, ...
    'F84_rating_scope','conductor_summer_design_not_verified_terminal_limited_facility', ...
    'RCC_conductor_sizes_and_charging_unresolved',true, ...
    'Dover_PAR_impedance_unresolved_line_only_estimates_not_applied',true, ...
    'original_generation_bounds_load_and_six_transfers_preserved',true);
end

function digest=file_sha256(path)
engine=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
while ~feof(fid),bytes=fread(fid,1048576,'*uint8');if ~isempty(bytes),engine.update(typecast(bytes,'int8'));end,end
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
