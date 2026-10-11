function validate_matlab_western()
%VALIDATE_MATLAB_WESTERN Independent fresh MATPOWER solves of exported cases.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(root,'System Matpower Format'));
clear npcc_nygrid_2025_western_corrected_dc
assert(~isempty(which('rundcpf')),'westernValidation:MATPOWER','Configured MATPOWER is required.');
folder=fullfile(root,'output','nygrid_2025_western_audit');
baseline=fullfile(root,'output','nygrid_2025_dispatch','dispatch');
d=load(fullfile(baseline,'dispatch.mat'),'timestamp_utc','gen_pg','bus_pd','bus_qd','dc_pf','hour_index','gamma');
b=load(fullfile(baseline,'dispatch_bounds.mat'),'gen_pmin','gen_pmax');
on=load(fullfile(folder,'dispatch','actual_Ontario_dispatch.mat'));
all_regions=load(fullfile(folder,'dispatch','all_boundary_actual_dispatch.mat'));
modes={'mapping_only','Ontario_actual_only','Ontario_actual_and_mapping','all_boundary_actual_only','combined'};
options=mpoption('model','DC','verbose',0,'out.all',0);checks=table();
names={'topology','mode','hour_index','branch_error_model_mw','angle_error_degree', ...
    'generation_change_model_mw','bound_violation_model_mw','interface_error_model_mw', ...
    'six_transfer_error_model_mw'};
t=datetime(string(d.timestamp_utc),'InputFormat',"yyyy-MM-dd'T'HH:mm:ss'Z'",'TimeZone','UTC');
t.TimeZone='America/New_York';
files={fullfile(baseline,'dispatch.mat'),fullfile(baseline,'dispatch_bounds.mat'), ...
    fullfile(folder,'dispatch','actual_Ontario_dispatch.mat'), ...
    fullfile(folder,'dispatch','all_boundary_actual_dispatch.mat'), ...
    which('npcc_nygrid_2025_western_corrected_dc'),which('npcc_nygrid_2025_par_controlled_dc'), ...
    which('npcc_nygrid_2025_slim_interfaces'),[mfilename('fullpath'),'.m']};
for topology={'dated','year_end'}
    topology=topology{1};
    for mode=modes
        mode=mode{1};path=fullfile(folder,'replay',[topology,'_',mode,'.mat']);r=load(path);
        q=logical(r.qualified(:));good=find(q);selected=[];
        for mo=[1 4 7 10],selected=[selected;find(month(t)==mo&q,1)];end %#ok<AGROW>
        selected=[selected;find(month(t)==11&day(t)==2&hour(t)==1&q)]; %#ok<AGROW>
        for key=unique(string(r.network_state_ids))'
            selected=[selected;find(string(r.network_state_ids)==key&q,1)]; %#ok<AGROW>
        end
        if strcmp(r.boundary_basis,'Ontario'),pg=on.gen_pg;
        elseif strcmp(r.boundary_basis,'all'),pg=all_regions.gen_pg;
        else,pg=d.gen_pg;end
        [~,hi]=max(sum(pg(good,1:1436),2));[~,lo]=min(sum(pg(good,1:1436),2));
        selected=[selected;good(hi);good(lo)]; %#ok<AGROW>
        for h=unique(selected)'
            m=npcc_nygrid_2025_western_corrected_dc(h,topology,mode);
            before=npcc_nygrid_2025_par_controlled_dc(h,topology);
            assert(size(m.bus,1)==148&&size(m.gen,1)==1464&&size(m.dcline,1)==6);
            assert(isequal(m.branch,before.branch)&&isequal(m.dcline,before.dcline));
            assert(isequal(m.bus(:,[1 3:13]),before.bus(:,[1 3:13])));
            assert(isequal(m.gen(:,1),r.corrected_generator_buses(:)));
            assert(isequal(m.gen(:,2),pg(h,:)'));
            assert(isequal(m.gen(1:1436,9),b.gen_pmax(h,1:1436)') ...
                &&isequal(m.gen(1:1436,10),b.gen_pmin(h,1:1436)'));
            assert(isequal(m.gen(:,3:7),before.gen(:,3:7)));
            if ~strcmp(r.boundary_basis,'scheduled')
                assert(isequal(m.gen(1437:end,9:10),repmat(pg(h,1437:end)',1,2)));
            else,assert(isequal(m.gen(:,2:end),before.gen(:,2:end)));end
            assert(~m.userdata.western_correction.internal_interface_observations_used_for_fit ...
                &&~m.userdata.western_correction.Dysinger_East_Stolle_PAR_added);
            [solved,ok]=rundcpf(m,options);assert(ok,'westernValidation:Solve','Fresh DC solve failed.');
            measured=npcc_nygrid_2025_slim_interfaces(solved);
            branch_error=max(abs(solved.branch(:,14)-r.branch_pf(h,:)'));
            angle_error=max(abs(solved.bus(:,9)-r.bus_va(h,:)'));
            generation_error=max(abs(solved.gen(:,2)-pg(h,:)'));
            bound_error=max([0;solved.gen(:,10)-solved.gen(:,2);solved.gen(:,2)-solved.gen(:,9)]);
            interface_error=max(abs(measured.model_mw-r.interface_pf(h,:)'));
            dc_error=max(abs(solved.dcline(:,4)-[d.dc_pf(h,:) r.par_transfer_model_mw(h,:)]'));
            assert(max([branch_error,angle_error,generation_error,bound_error,interface_error,dc_error])<1e-7);
            checks=[checks;table(string(topology),string(mode),h,branch_error,angle_error,generation_error, ...
                bound_error,interface_error,dc_error,'VariableNames',names)]; %#ok<AGROW>
        end
        files{end+1}=path; %#ok<AGROW>
    end
end
gap_rejected=false;h=find(~logical(on.qualified(:)),1);
try,npcc_nygrid_2025_western_corrected_dc(h,'dated','Ontario_actual_only');
catch err,gap_rejected=contains(err.identifier,'UnqualifiedHour');end
assert(gap_rejected);
invalid_mode=false;try,npcc_nygrid_2025_western_corrected_dc(1,'dated','bad');
catch err,invalid_mode=strcmp(err.identifier,'westernCorrection:Mode');end
invalid_topology=false;try,npcc_nygrid_2025_western_corrected_dc(1,'bad');
catch err,invalid_topology=strcmp(err.identifier,'westernCorrection:Topology');end
assert(invalid_mode&&invalid_topology);
% The six IESO all-intertie zero records are rejected even when the old model
% and all-boundary reconstruction have a valid hour at the same timestamp.
quality=readtable(fullfile(folder,'ontario','hourly_exchange_quality.csv'));
suspect=find(ismember(lower(string(quality.all_intertie_actual_zero)),["true","1"]) ...
    &ismember(lower(string(quality.schedules_nonzero)),["true","1"]));
for h=suspect'
    rejected=false;try,npcc_nygrid_2025_western_corrected_dc(h,'dated','Ontario_actual_only');
    catch err,rejected=strcmp(err.identifier,'westernCorrection:UnqualifiedHour');end
    assert(rejected);
end
files{end+1}=fullfile(folder,'ontario','hourly_exchange_quality.csv');
out=fullfile(folder,'validation');if ~isfolder(out),mkdir(out);end
writetable(checks,fullfile(out,'matlab_checks.csv'));
dependencies=struct('path',{},'sha256',{});
for j=1:numel(files),dependencies(end+1)=struct('path',files{j},'sha256',file_sha256(files{j}));end %#ok<AGROW>
summary=struct('passed',true,'fresh_MATPOWER_snapshots',height(checks), ...
    'modes',string(modes),'maximum_branch_error_model_mw',max(checks.branch_error_model_mw), ...
    'maximum_angle_error_degree',max(checks.angle_error_degree), ...
    'maximum_generation_change_model_mw',max(checks.generation_change_model_mw), ...
    'maximum_bound_violation_model_mw',max(checks.bound_violation_model_mw), ...
    'maximum_interface_error_model_mw',max(checks.interface_error_model_mw), ...
    'maximum_six_transfer_error_model_mw',max(checks.six_transfer_error_model_mw), ...
    'missing_hour_rejected',gap_rejected,'invalid_mode_rejected',invalid_mode, ...
    'invalid_topology_rejected',invalid_topology,'IESO_suspect_hours_rejected',numel(suspect), ...
    'AC_or_physical_PAR_tap_feasibility_verified',false, ...
    'MATPOWER_solver',which('rundcpf'),'MATLAB_version',version,'dependencies',dependencies);
fid=fopen(fullfile(out,'matlab_validation.json'),'w');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(summary,'PrettyPrint',true));disp(summary);
end

function digest=file_sha256(path)
engine=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
while ~feof(fid),bytes=fread(fid,1048576,'*uint8');if ~isempty(bytes),engine.update(typecast(bytes,'int8'));end,end
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
