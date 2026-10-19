function capture_full_stages(outdir)
% Capture the full released 2019 constructor before its DC Ward reduction.
% Run prepare_capture.py first. Original source/data/results stay untouched.
% Optional outdir selects a separately prepared build without replacing the default.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
cached=fullfile(root,'tmp','nygrid_2019_reproduction','cached_upstream');
toolbox=fullfile(root,'tmp','nygrid_2019_reproduction','reduction_toolbox','mirror');
if nargin<1||isempty(outdir),outdir=fullfile(root,'output','nygrid_2019_full_stage1');end
[found,location]=fileattrib(outdir);assert(found&&isscalar(location)&&location.directory, ...
    'nygrid:OutputFolder','Prepare the selected output folder first.');
outdir=location.Name;
runtime=fullfile(outdir,'capture_runtime');
assert(isfile(fullfile(runtime,'nygrid_full_updateOpCond.m')),'Run prepare_capture.py first.');
old=pwd;oldpath=path;cleanup=onCleanup(@()restore_environment(old,oldpath));cd(runtime);
if ~isfolder('Result'),mkdir('Result');end
addpath(toolbox);addpath(genpath(cached),'-begin');addpath(runtime,'-begin');
assert(contains(which('nygrid_full_updateOpCond'),runtime));
clear nygrid_cached_table;
set(groot,'defaultFigureVisible','off');
opts=mpoption('verbose',0,'out.all',0,'exp.use_legacy_core',1);
fprintf('MATLAB %s; MATPOWER %s; reduction %s\n',version,mpver,which('MPReduction'));
evalc('base=modifyMPC();');
times=[datetime(2019,(1:12)',1);datetime(2019,7,20,17,0,0)];
timestamps=cellstr(string(times,'yyyy-MM-dd HH:mm:ss'));
hour_indices=round(hours(times-datetime(2019,1,1)))+1;
captures=cell(numel(times),1);rows=cell(numel(times),1);logs=cell(numel(times),1);
annual=cell(4,1);
for q=1:4
    annual{q}=load(fullfile(root,'output','nygrid_2019',sprintf('annual_%d.mat',q)), ...
        'first_hour','last_hour','bus_pd','input_pg','result_pg','dc_pf','branch_pf','bus_va','base_case');
end
for k=1:numel(times)
    started=tic;
    logs{k}=evalc('[final_input,full_input,reduced_pre_hvdc]=nygrid_full_updateOpCond(base,times(k),false,false,true);');
    [full_result,full_ok]=rundcpf(full_input,opts);
    [reduced_pre_hvdc_result,pre_ok]=rundcpf(reduced_pre_hvdc,opts);
    [final_result,final_ok]=rundcpf(final_input,opts);
    assert(full_ok && pre_ok && final_ok,'DC solve failed at %s',timestamps{k});
    q=find(cellfun(@(a)hour_indices(k)>=a.first_hour && hour_indices(k)<=a.last_hour,annual));
    assert(isscalar(q));a=annual{q};j=hour_indices(k)-a.first_hour+1;
    checks=[max(abs(final_input.bus(:,3)'-a.bus_pd(j,:))), ...
        max(abs(final_input.gen(:,2)'-a.input_pg(j,:))), ...
        max(abs(final_input.dcline(:,4)'-a.dc_pf(j,:))), ...
        max(abs(final_result.branch(:,14)'-a.branch_pf(j,:))), ...
        max(abs(final_result.gen(:,2)'-a.result_pg(j,:))), ...
        max(abs(final_result.bus(:,9)'-a.bus_va(j,:)))];
    assert(max(checks)<1e-7,'Captured final case differs from annual evidence.');
    assert(isequal(final_input.bus(:,1),a.base_case.bus(:,1)) && ...
        isequal(final_input.gen(:,1),a.base_case.gen(:,1)) && ...
        max(abs(final_input.branch(:,1:13)-a.base_case.branch(:,1:13)),[],'all')<1e-10);
    captures{k}=struct('full_input',full_input,'full_result',full_result, ...
        'reduced_pre_hvdc',reduced_pre_hvdc,'reduced_pre_hvdc_result',reduced_pre_hvdc_result, ...
        'final_input',final_input,'final_result',final_result);
    rows{k}=table(string(timestamps{k}),hour_indices(k),size(full_input.bus,1),size(full_input.branch,1), ...
        size(full_input.gen,1),size(reduced_pre_hvdc.bus,1),size(reduced_pre_hvdc.branch,1), ...
        size(final_input.branch,1),size(final_input.dcline,1),full_ok,pre_ok,final_ok,checks(1),checks(2), ...
        checks(3),checks(4),checks(5),checks(6),toc(started),'VariableNames', ...
        {'timestamp','hour_index','full_buses','full_branches','full_generators','reduced_buses', ...
        'reduced_pre_hvdc_branches','final_branches','final_dclines','full_pf_success','pre_pf_success', ...
        'final_pf_success','annual_pd_max_error_mw','annual_input_pg_max_error_mw','annual_dc_max_error_mw', ...
        'annual_branch_pf_max_error_mw','annual_result_pg_max_error_mw','annual_angle_max_error_deg','elapsed_seconds'});
    fprintf('Captured %s: full %d/%d/%d, final branch replay max %.3g MW (%.2f s)\n', ...
        timestamps{k},size(full_input.bus,1),size(full_input.branch,1),size(full_input.gen,1),checks(4),toc(started));
end
inventory=vertcat(rows{:});
save(fullfile(outdir,'captured_stages.mat'),'base','times','timestamps','hour_indices','captures','logs','inventory','-v7');
writetable(inventory,fullfile(outdir,'capture_inventory.csv'));
manifest=struct('complete',true,'captured_hours',numel(times),'all_dc_solves_passed',true, ...
    'maximum_saved_annual_error_mw',max(inventory.annual_branch_pf_max_error_mw), ...
    'matlab_version',version,'matpower_version',mpver,'source_stage', ...
    'full_input is literal upstream before MPReduction; final_input retains released post-reduction DC links');
fid=fopen(fullfile(outdir,'capture_run_summary.json'),'w');assert(fid>=0);
fprintf(fid,'%s\n',jsonencode(manifest,PrettyPrint=true));fclose(fid);
fprintf('Completed %d source-stage captures; saved under %s\n',numel(times),outdir);
end
function restore_environment(oldfolder,oldpath)
cd(oldfolder);path(oldpath);
end
