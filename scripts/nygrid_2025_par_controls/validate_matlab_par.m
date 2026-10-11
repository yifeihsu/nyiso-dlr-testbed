function validate_matlab_par(artifact_folder)
%VALIDATE_MATLAB_PAR Fresh MATLAB checks for ideal external PAR-flow controls.
% Uses actual annual extrema/reversals, commissioning states, DST folds and
% separately generated zero/counterflow fixtures. No physical tap is inferred.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
if nargin<1,artifact_folder=fullfile(root,'output','nygrid_2025_par_controls');end
addpath(fullfile(root,'System Matpower Format'));
clear npcc_nygrid_2025_par_controlled_dc npcc_nygrid_2025_moses_corrected_dc npcc_nygrid_2025_slim_dc npcc_nygrid_2025_full_dc
assert(~isempty(which('rundcpf')),'parValidation:MATPOWER','Configured MATPOWER is required.');
baseline=fullfile(root,'output','nygrid_2025_dispatch','dispatch');
d=load(fullfile(baseline,'dispatch.mat'),'timestamp_utc','dispatch_qualified','gen_pg','bus_pd','bus_qd','dc_pf','hour_index','gamma');
inputs=load(fullfile(artifact_folder,'controls','inputs.mat'));
q=logical(inputs.observed_replay_qualified(:));
assert(isequal(string(inputs.timestamp_utc(:)),string(d.timestamp_utc(:))));
assert(isequal(inputs.ptids(:),[25118;25119])&&inputs.gamma==d.gamma);
assert(inputs.observed_direction_verified&&~inputs.hardware_phase_applies_to_equivalent&&~inputs.full_P_Q_rating_feasible);
assert(~inputs.schedule_sign_verified&&inputs.schedule_mode_diagnostic);
assert(isequal(inputs.p_only_limit_public_mw(:),[300;300]));
assert(max(abs(inputs.observed_model_mw(q,:)-inputs.observed_public_mw(q,:)*d.gamma),[],'all')<1e-12);
t=datetime(string(d.timestamp_utc),'InputFormat',"yyyy-MM-dd'T'HH:mm:ss'Z'",'TimeZone','UTC');
t.TimeZone='America/New_York';good=find(q);selected=[];
for mo=[1 4 7 10],selected=[selected;find(month(t)==mo&q,1)];end %#ok<AGROW>
selected=[selected;find(month(t)==11&day(t)==2&hour(t)==1&q)]; %#ok<AGROW>
[~,peak]=max(sum(d.bus_pd(good,:),2));[~,valley]=min(sum(d.bus_pd(good,:),2));
selected=[selected;good(peak);good(valley)]; %#ok<AGROW>
for device=1:2
    [~,mi]=min(inputs.observed_model_mw(good,device));[~,ma]=max(inputs.observed_model_mw(good,device));
    selected=[selected;good(mi);good(ma)]; %#ok<AGROW>
end
[~,nearzero]=min(abs(sum(inputs.observed_model_mw(good,:),2)));
selected=[selected;good(nearzero)];
options=mpoption('model','DC','verbose',0,'out.all',0);checks=table();
check_names={'topology','hour_index','case_kind','branch_error_model_mw','angle_error_degree', ...
    'generation_change_model_mw','bound_violation_model_mw','interface_error_model_mw', ...
    'per_device_PAR_target_error_model_mw','original_four_DC_error_model_mw','logical_branch211_error_model_mw'};
files={fullfile(baseline,'dispatch.mat'),fullfile(baseline,'dispatch_bounds.mat'), ...
    fullfile(artifact_folder,'controls','inputs.mat'),fullfile(artifact_folder,'controls','input_receipt.json'), ...
    fullfile(artifact_folder,'validation','matlab_fixture_expected.mat'), ...
    which('npcc_nygrid_2025_par_controlled_dc'),which('npcc_nygrid_2025_moses_corrected_dc'), ...
    which('npcc_nygrid_2025_slim_dc'),which('npcc_nygrid_2025_full_dc'), ...
    which('npcc_nygrid_2025_slim_interfaces'),[mfilename('fullpath'),'.m']};
for topology={'dated','year_end'}
    topology=topology{1};path=fullfile(artifact_folder,'replay',[topology,'_verified_PAR_flows.mat']);
    p=load(path);assert(isequal(logical(p.qualified(:)),q));
    candidates=selected;
    if strcmp(topology,'dated')
        for key=unique(string(p.network_state_ids))'
            h=find(string(p.network_state_ids)==key&q,1);
            candidates=[candidates;h]; %#ok<AGROW>
        end
    end
    for h=unique(candidates)'
        m=npcc_nygrid_2025_par_controlled_dc(h,topology);
        before=npcc_nygrid_2025_moses_corrected_dc(h,'hydro_zone_corrected',topology);
        validate_contract(m,before,d,inputs,p,h);
        [r,ok]=rundcpf(m,options);assert(ok,'parValidation:Solve','DC solve failed.');
        measured=npcc_nygrid_2025_slim_interfaces(r);
        branch_error=max(abs(r.branch(:,14)-p.branch_pf(h,:)'));
        angle_error=max(abs(r.bus(:,9)-p.bus_va(h,:)'));
        generation_error=max(abs(r.gen(:,2)-d.gen_pg(h,:)'));
        bounds_error=max([0;r.gen(:,10)-r.gen(:,2);r.gen(:,2)-r.gen(:,9)]);
        interface_error=max(abs(measured.model_mw-p.interface_pf(h,:)'));
        target_error=max(abs(r.dcline(5:6,4)-inputs.observed_model_mw(h,:)'));
        original_dc_error=max(abs(r.dcline(1:4,4)-d.dc_pf(h,:)'));
        logical_error=abs(-sum(r.dcline(5:6,4))-p.logical_original_branch211_pf(h));
        assert(max([branch_error,angle_error,generation_error,bounds_error,interface_error,target_error,original_dc_error,logical_error])<1e-7, ...
            'parValidation:Mismatch','MATPOWER differs from final controlled replay.');
        checks=[checks;table(string(topology),h,"source_observed",branch_error,angle_error,generation_error, ...
            bounds_error,interface_error,target_error,original_dc_error,logical_error,'VariableNames',check_names)]; %#ok<AGROW>
    end
    files{end+1}=path; %#ok<AGROW>
end
fixture=load(fullfile(artifact_folder,'validation','matlab_fixture_expected.mat'));
if iscell(fixture.fixtures),fixture.fixtures=[fixture.fixtures{:}];end
for f=fixture.fixtures(:)'
    m=npcc_nygrid_2025_par_controlled_dc(double(f.hour_index),char(f.topology));
    target=f.target_model_mw(:);
    m.dcline(5:6,4:5)=repmat(target,1,2);m.dcline(5:6,10:11)=repmat(target,1,2);
    m.userdata.par_controls.logical_original_branch211_flow_model_mw=-sum(target);
    [r,ok]=rundcpf(m,options);assert(ok,'parValidation:FixtureSolve','Synthetic zero/counterflow solve failed.');
    measured=npcc_nygrid_2025_slim_interfaces(r);
    branch_error=max(abs(r.branch(:,14)-f.branch_pf(:)));
    angle_error=max(abs(r.bus(:,9)-f.bus_va(:)));
    generation_error=max(abs(r.gen(:,2)-d.gen_pg(double(f.hour_index),:)'));
    bounds_error=max([0;r.gen(:,10)-r.gen(:,2);r.gen(:,2)-r.gen(:,9)]);
    interface_error=max(abs(measured.model_mw-f.interface_pf(:)));
    target_error=max(abs(r.dcline(5:6,4)-target));
    original_dc_error=max(abs(r.dcline(1:4,4)-d.dc_pf(double(f.hour_index),:)'));
    logical_error=abs(-sum(r.dcline(5:6,4))+sum(target));
    assert(max([branch_error,angle_error,generation_error,bounds_error,interface_error,target_error,original_dc_error,logical_error])<1e-7);
    checks=[checks;table(string(f.topology),double(f.hour_index),string(f.label),branch_error,angle_error, ...
        generation_error,bounds_error,interface_error,target_error,original_dc_error,logical_error,'VariableNames',check_names)]; %#ok<AGROW>
end
gap_rejected=false;
try,npcc_nygrid_2025_par_controlled_dc(find(~q,1));
catch err,gap_rejected=ismember(err.identifier,{'nygrid2025:UnqualifiedHour','nygridPAR:UnqualifiedHour','mosesCorrection:UnqualifiedHour'});end
assert(gap_rejected,'parValidation:MissingSource','Missing-source hour was accepted.');
bad_topology_rejected=false;
try,npcc_nygrid_2025_par_controlled_dc(good(1),'invalid');
catch err,bad_topology_rejected=strcmp(err.identifier,'nygridPAR:Topology');end
assert(bad_topology_rejected);
checks.Properties.VariableNames={'topology','hour_index','case_kind','branch_error_model_mw','angle_error_degree', ...
    'generation_change_model_mw','bound_violation_model_mw','interface_error_model_mw', ...
    'per_device_PAR_target_error_model_mw','original_four_DC_error_model_mw','logical_branch211_error_model_mw'};
output=fullfile(artifact_folder,'validation');if ~isfolder(output),mkdir(output);end
writetable(checks,fullfile(output,'matlab_checks.csv'));
dependencies=struct('path',{},'sha256',{});
for j=1:numel(files),dependencies(end+1)=struct('path',files{j},'sha256',file_sha256(files{j}));end %#ok<AGROW>
summary=struct('passed',true,'fresh_MATPOWER_snapshots',height(checks), ...
    'observed_source_snapshots',nnz(checks.case_kind=="source_observed"), ...
    'synthetic_zero_counterflow_snapshots',nnz(checks.case_kind~="source_observed"), ...
    'maximum_branch_error_model_mw',max(checks.branch_error_model_mw), ...
    'maximum_angle_error_degree',max(checks.angle_error_degree), ...
    'maximum_generation_change_model_mw',max(checks.generation_change_model_mw), ...
    'maximum_bound_violation_model_mw',max(checks.bound_violation_model_mw), ...
    'maximum_interface_error_model_mw',max(checks.interface_error_model_mw), ...
    'maximum_per_device_PAR_target_error_model_mw',max(checks.per_device_PAR_target_error_model_mw), ...
    'maximum_original_four_DC_error_model_mw',max(checks.original_four_DC_error_model_mw), ...
    'maximum_logical_branch211_error_model_mw',max(checks.logical_branch211_error_model_mw), ...
    'missing_source_hour_rejected',gap_rejected,'invalid_topology_rejected',bad_topology_rejected, ...
    'physical_tap_reconstruction_available',false,'physical_HVDC_devices_added',0, ...
    'full_P_Q_thermal_or_tap_feasibility_certified',false, ...
    'MATPOWER_solver',which('rundcpf'),'MATLAB_version',version,'dependencies',dependencies);
fid=fopen(fullfile(output,'matlab_validation.json'),'w');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(summary,'PrettyPrint',true));disp(summary);
end

function validate_contract(m,before,d,inputs,p,h)
assert(size(m.bus,1)==148&&size(m.gen,1)==size(d.gen_pg,2)&&size(m.dcline,1)==6);
assert(isequal(m.bus,before.bus),'parValidation:BusChange','PAR control changed bus records.');
assert(isequal(m.gen,before.gen),'parValidation:GenChange','PAR control changed generation/bounds.');
expected=before.branch;expected(211,11)=0;
assert(isequal(m.branch,expected),'parValidation:BranchChange','Unexpected change beyond passive representation status.');
assert(m.branch(211,10)==0,'parValidation:FakeTap','An aggregate equivalent SHIFT was exported.');
assert(isequal(m.dcline(1:4,:),before.dcline),'parValidation:OriginalDC','Original four DC records changed.');
assert(isequal(m.dcline(5:6,1:3),[100 48 1;100 48 1])&&all(m.dcline(5:6,16:17)==0,'all'));
assert(isequal(m.gen(:,1),p.corrected_generator_buses(:)));
assert(isequal(m.gen(:,2),d.gen_pg(h,:)')&&isequal(m.bus(1:140,3),d.bus_pd(h,:)')&&isequal(m.bus(1:140,4),d.bus_qd(h,:)'));
assert(all(m.bus(141:end,3:6)==0,'all'));
assert(isequal(m.dcline(5:6,4),inputs.observed_model_mw(h,:)'));
meta=m.userdata.par_controls;
assert(isequal(meta.ptids,[25118;25119])&&contains(meta.kind,'ideal_PAR_controlled_transfer'));
assert(meta.passive_status_change_is_representation_substitution&&~meta.passive_status_change_is_physical_outage);
assert(~meta.physical_tap_reconstruction_available&&~meta.physical_operating_envelope_complete);
assert(meta.new_physical_HVDC_count==0&&meta.existing_source_DC_records_preserved==4);
assert(meta.external_flow_conditioned_reconstruction&&~meta.internal_interface_observations_used);
assert(isequal(meta.nominal_device_mva,[300;300])&&isequal(meta.hardware_no_load_phase_design_range_deg,[-60 60]));
assert(max(abs(meta.necessary_p_only_limit_model_mw-inputs.p_only_limit_model_mw(:)))<1e-12);
assert(abs(meta.logical_original_branch211_flow_model_mw+sum(m.dcline(5:6,4)))<1e-12);
end

function digest=file_sha256(path)
engine=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
while ~feof(fid),bytes=fread(fid,1048576,'*uint8');if ~isempty(bytes),engine.update(typecast(bytes,'int8'));end,end
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
