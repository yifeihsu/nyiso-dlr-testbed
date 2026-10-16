function check_unmodified_release()
% Fresh monthly checks using original author code and original2019 inputs.
% No reconstructed full-NPCC or current2025 model is loaded by this check.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
out=fullfile(root,'output','nygrid_released_2019_comparison');if ~isfolder(out),mkdir(out);end
up=fullfile(root,'tmp','nygrid_2019_reproduction','upstream');
toolbox=fullfile(root,'tmp','nygrid_2019_reproduction','reduction_toolbox','mirror');
mp='C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower';
for d={'lib','mips/lib','mp-opt-model/lib','mptest/lib'},addpath(fullfile(mp,d{1}),'-begin');end
addpath(toolbox,'-begin');addpath(genpath(up),'-begin');
old=pwd;cleanup=onCleanup(@()cd(old));cd(up);
assert(strcmp(mpver,'8.1'));assert(strcmp(which('updateOpCond'),fullfile(up,'updateOpCond.m')));
assert(strcmp(which('modifyMPC'),fullfile(up,'modifyMPC.m')));
assert(strcmp(which('flow4Plot'),fullfile(up,'Utility','flow4Plot.m')));
manifest=jsondecode(fileread(fullfile(root,'output','nygrid_2019','upstream_manifest.json')));
for k=1:numel(manifest.files),f=manifest.files(k);assert(strcmp(file_sha(fullfile(up,f.path)),f.sha256));end
opts=mpoption('verbose',0,'out.all',0,'exp.use_legacy_core',1);
parts=cell(4,1);for k=1:4,parts{k}=load(fullfile(root,'output','nygrid_2019',sprintf('annual_%d.mat',k)));end
evalc('base=modifyMPC();');times=datetime(2019,(1:12)',1);records=struct([]);cases=cell(12,1);
for k=1:12
    h=hours(times(k)-datetime(2019,1,1))+1;part=ceil(h/2190);local=h-(part-1)*2190;saved=parts{part};
    assert(saved.status(local));evalc('m=updateOpCond(base,times(k),false,false,true);');[r,success]=rundcpf(m,opts);
    assert(success&&size(m.bus,1)==57&&size(m.branch,1)==94&&size(m.gen,1)==271&&size(m.dcline,1)==4);
    original=saved.selected_cases{local};assert(~isempty(original));
    errors=zeros(1,6);fields={'bus','gen','branch','dcline','gencost'};
    for j=1:5,errors(j)=max(abs(m.(fields{j})-original.input.(fields{j})),[],'all');end
    errors(6)=max(abs(r.branch(:,14)-saved.branch_pf(local,:)'));
    assert(max(errors)<1e-8&&isequal(m.if.map,original.input.if.map));
    [~,observed,limits]=readOpCond(times(k));[sim,obs,err]=flow4Plot(r,observed,limits);
    literal_error=max(abs(sim(:)'-saved.sim(local,:)));observation_error=max(abs(obs(:)'-saved.actual(local,:)));
    paper_error=max(abs(100*err(:)'-saved.paper(local,:)));
    ids=[1 2 3 4 5 8 10];from_author_map=zeros(1,7);
    for j=1:7,members=m.if.map(m.if.map(:,1)==ids(j),2);from_author_map(j)=sum(sign(members).*r.branch(abs(members),14));end
    mapped_error=max(abs(from_author_map-saved.corrected_sim(local,:)));
    assert(max([literal_error observation_error paper_error mapped_error])<1e-8);
    records=[records;struct('hour_index',h,'timestamp',char(times(k),'yyyy-MM-dd HH:mm:ss'), ...
        'buses',57,'branches',94,'generators',271,'DC_records',4,'PF_success',success, ...
        'bus_difference',errors(1),'generator_difference',errors(2),'branch_difference',errors(3), ...
        'DC_difference',errors(4),'cost_difference',errors(5),'solved_branch_flow_difference_MW',errors(6), ...
        'literal_plot_difference_MW',literal_error,'observation_difference_MW',observation_error, ...
        'paper_metric_difference_percent',paper_error,'author_if_map_difference_MW',mapped_error)]; %#ok<AGROW>
    cases{k}=struct('input',m,'result',r,'literal_plot_MW',sim,'author_if_map_MW',from_author_map,'observed_MW',obs);
    fprintf('AUTHOR_RELEASE_CHECK month%d buses57 branches94 max_difference%.3g\n',k,max([errors literal_error observation_error mapped_error]));
end
for k=1:numel(manifest.files),f=manifest.files(k);assert(strcmp(file_sha(fullfile(up,f.path)),f.sha256));end
writetable(struct2table(records),fullfile(out,'fresh_author_release_checks.csv'));
save(fullfile(out,'fresh_author_release_cases.mat'),'cases','times','records','-v7');
receipt=struct('passed',true,'upstream_commit',manifest.commit,'original_author_files_unchanged',true, ...
    'original_author_files_hash_checked',numel(manifest.files),'fresh_unmodified_source_PF_hours',12, ...
    'saved_annual_comparison_hours',8760,'derived_full_NPCC_loaded',false,'current2025_case_loaded',false, ...
    'network_or2019_input_modification',false,'MATLAB_version',version,'MATPOWER_version',mpver, ...
    'model_builder',which('updateOpCond'),'plot_helper',which('flow4Plot'),'reduction_toolbox',which('MPReduction'), ...
    'compatibility_note','MATPOWER8.1legacycore and pinnedJune2019reductiontoolbox; the exact environment used for the paper figure is not known.', ...
    'checks',records);
fid=fopen(fullfile(out,'fresh_author_release_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(receipt,'PrettyPrint',true));fclose(fid);
end
function s=file_sha(path)
md=java.security.MessageDigest.getInstance('SHA-256');fid=fopen(path,'rb');assert(fid>=0);c=onCleanup(@()fclose(fid));
while ~feof(fid),b=fread(fid,1048576,'*uint8');if ~isempty(b),md.update(typecast(b,'int8'));end,end
s=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2)',1,[]));
end
