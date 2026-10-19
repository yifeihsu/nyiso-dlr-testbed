function validate_matlab_counterfactuals()
%VALIDATE_MATLAB_COUNTERFACTUALS Fresh solves for predetermined experiment hours.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(root,'System Matpower Format'));
folder=fullfile(root,'output','nygrid_2025_western_counterfactuals');
path=fullfile(folder,'replay','matlab_fixtures.mat');d=load(path);
if iscell(d.fixtures),fixtures=[d.fixtures{:}];else,fixtures=d.fixtures;end
options=mpoption('model','DC','verbose',0,'out.all',0);checks=table();
for f=fixtures(:)'
    h=double(f.hour_index);
    m=npcc_nygrid_2025_western_corrected_dc(h,'dated','combined');
    original=m;
    m.gen(:,2)=f.gen_pg(:);m.bus(:,3)=f.bus_pd(:);m.bus(:,4)=f.bus_qd(:);
    assert(isequal(m.gen(1437:end,:),original.gen(1437:end,:)));
    assert(isequal(m.gen(:,[1 3:21]),original.gen(:,[1 3:21])));
    assert(isequal(m.branch,original.branch)&&isequal(m.dcline,original.dcline));
    assert(abs(sum(m.gen(:,2))-sum(m.bus(:,3))-sum(m.bus(:,5)))<1e-7);
    assert(max([0;m.gen(:,10)-m.gen(:,2);m.gen(:,2)-m.gen(:,9)])<1e-7);
    [r,ok]=rundcpf(m,options);assert(ok,'westernExperiment:Solve','Counterfactual snapshot failed.');
    result=npcc_nygrid_2025_slim_interfaces(r);
    be=max(abs(r.branch(:,14)-f.branch_pf(:)));
    ae=max(abs(r.bus(:,9)-f.bus_va(:)));
    ie=max(abs(result.model_mw-f.interface_pf(:)));
    ge=max(abs(r.gen(:,2)-f.gen_pg(:)));
    de=max(abs(r.dcline(:,4)-original.dcline(:,4)));
    assert(max([be ae ie ge de])<1e-7,'westernExperiment:Mismatch','MATPOWER disagrees with experiment fixture.');
    checks=[checks;table(string(f.name),h,be,ae,ie,ge,de,'VariableNames', ...
        {'scenario','hour_index','branch_error_model_mw','angle_error_degree', ...
        'interface_error_model_mw','generation_error_model_mw','six_transfer_error_model_mw'})]; %#ok<AGROW>
end
out=fullfile(folder,'validation');if ~isfolder(out),mkdir(out);end
writetable(checks,fullfile(out,'matlab_checks.csv'));
files={path,fullfile(folder,'replay','replay_receipt.json'), ...
    which('npcc_nygrid_2025_western_corrected_dc'),which('npcc_nygrid_2025_slim_interfaces'), ...
    [mfilename('fullpath'),'.m']};
dependencies=struct('path',{},'sha256',{});
for i=1:numel(files),dependencies(end+1)=struct('path',files{i},'sha256',file_sha256(files{i}));end %#ok<AGROW>
summary=struct('passed',true,'fresh_MATPOWER_snapshots',height(checks),'scenarios',numel(unique(checks.scenario)), ...
    'predetermined_state_and_season_hours',true,'internal_observation_selected_hours',false, ...
    'maximum_branch_error_model_mw',max(checks.branch_error_model_mw), ...
    'maximum_interface_error_model_mw',max(checks.interface_error_model_mw), ...
    'maximum_generation_error_model_mw',max(checks.generation_error_model_mw), ...
    'maximum_six_transfer_error_model_mw',max(checks.six_transfer_error_model_mw), ...
    'MATLAB_version',version,'MATPOWER_solver',which('rundcpf'),'dependencies',dependencies);
fid=fopen(fullfile(out,'matlab_validation.json'),'w');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
fprintf(fid,'%s\n',jsonencode(summary,'PrettyPrint',true));disp(summary);
end

function digest=file_sha256(path)
engine=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);cleanup=onCleanup(@()fclose(fid));
while ~feof(fid),bytes=fread(fid,1048576,'*uint8');if ~isempty(bytes),engine.update(typecast(bytes,'int8'));end,end
raw=typecast(engine.digest(),'uint8');digest=lower(reshape(dec2hex(raw,2)',1,[]));
end
