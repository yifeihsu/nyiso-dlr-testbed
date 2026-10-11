function validate_matlab_slim(artifact_folder)
% Fresh seasonal, stress, DST and state-transition snapshots for the slim case.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
if nargin<1,artifact_folder=fullfile(root,'output','nygrid_2025_slim');end
addpath(fullfile(root,'System Matpower Format'));
clear npcc_nygrid_2025_slim_dc npcc_nygrid_2025_full_dc
baseline=fullfile(root,'output','nygrid_2025_dispatch','dispatch');
d=load(fullfile(baseline,'dispatch.mat'),'timestamp_utc','dispatch_qualified','gen_pg','bus_pd');
q=logical(d.dispatch_qualified(:));
t=datetime(string(d.timestamp_utc),'InputFormat',"yyyy-MM-dd'T'HH:mm:ss'Z'",'TimeZone','UTC');t.TimeZone='America/New_York';
calendar=[];
for m=1:12,calendar=[calendar;find(month(t)==m&q,1)];end %#ok<AGROW>
good=find(q);[~,peak]=max(sum(d.bus_pd(good,:),2));[~,valley]=min(sum(d.bus_pd(good,:),2));
calendar=unique([calendar;good(peak);good(valley);find(month(t)==11&day(t)==2&hour(t)==1&q)]);
options=mpoption('model','DC','verbose',0,'out.all',0);checks=table();
files={fullfile(baseline,'dispatch.mat'),fullfile(baseline,'dispatch_bounds.mat'), ...
    fullfile(artifact_folder,'network','network_cases.mat'),which('npcc_nygrid_2025_slim_dc'), ...
    which('npcc_nygrid_2025_slim_interfaces'),[mfilename('fullpath'),'.m']};
for variant={'topology_dated','topology_year_end'}
    name=variant{1};path=fullfile(artifact_folder,'replay',[name,'.mat']);
    p=load(path,'qualified','network_state_ids','branch_pf','bus_va','interface_pf');
    assert(isequal(logical(p.qualified(:)),q));selected=calendar;
    for state=unique(string(p.network_state_ids))'
        ix=find(string(p.network_state_ids)==state&q);selected=[selected;ix(1);ix(end)]; %#ok<AGROW>
    end
    for h=unique(selected)'
        c=npcc_nygrid_2025_slim_dc(h,name,artifact_folder);[r,ok]=rundcpf(c,options);assert(ok);
        recovered=npcc_nygrid_2025_slim_interfaces(r);
        flow=max(abs(r.branch(:,14)-p.branch_pf(h,:)'));
        angle=max(abs(r.bus(:,9)-p.bus_va(h,:)'));
        generation=max(abs(r.gen(:,2)-d.gen_pg(h,:)'));
        bounds=max([0;r.gen(:,10)-r.gen(:,2);r.gen(:,2)-r.gen(:,9)]);
        interface=max(abs(recovered.model_mw-p.interface_pf(h,:)'));
        assert(max([flow,angle,generation,bounds,interface])<1e-7,'Slim MATPOWER mismatch.');
        checks=[checks;table(string(name),h,flow,angle,generation,bounds,interface)]; %#ok<AGROW>
    end
    files{end+1}=path; %#ok<AGROW>
end
rejected=false;
try,npcc_nygrid_2025_slim_dc(find(~q,1),'topology_dated',artifact_folder);
catch err,rejected=strcmp(err.identifier,'nygrid2025:UnqualifiedHour');end
assert(rejected);
unsolved_rejected=false;
try,npcc_nygrid_2025_slim_interfaces(npcc_nygrid_2025_slim_dc(good(1),'topology_dated',artifact_folder));
catch err,unsolved_rejected=strcmp(err.identifier,'nygridSlim:UnsolvedCase');end
assert(unsolved_rejected);
checks.Properties.VariableNames={'variant','hour_index','branch_error_mw','angle_error_deg','generation_change_mw','bound_violation_mw','interface_error_mw'};
folder=fullfile(artifact_folder,'validation');if ~isfolder(folder),mkdir(folder);end
writetable(checks,fullfile(folder,'matlab_checks.csv'));
dependencies=struct('path',{},'sha256',{});
for j=1:numel(files),dependencies(end+1)=struct('path',files{j},'sha256',file_sha256(files{j}));end %#ok<AGROW>
summary=struct('passed',true,'fresh_MATPOWER_snapshots',height(checks), ...
    'maximum_branch_error_mw',max(checks.branch_error_mw),'maximum_generation_change_mw',max(checks.generation_change_mw), ...
    'maximum_bound_violation_mw',max(checks.bound_violation_mw),'maximum_interface_error_mw',max(checks.interface_error_mw), ...
    'missing_source_hour_rejected',rejected,'unsolved_interface_request_rejected',unsolved_rejected, ...
    'dependencies',dependencies,'matlab_version',version);
fid=fopen(fullfile(folder,'matlab_validation.json'),'w');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(summary,'PrettyPrint',true));disp(summary);
end

function digest=file_sha256(path)
engine=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
while ~feof(fid),bytes=fread(fid,1048576,'*uint8');if ~isempty(bytes),engine.update(typecast(bytes,'int8'));end,end
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
