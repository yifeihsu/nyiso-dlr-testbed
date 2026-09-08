function validate_cached_reproduction
% Compare the cache adapter against unmodified released source across seasons.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
up=fullfile(root,'tmp','nygrid_2019_reproduction','upstream');
cache=fullfile(root,'tmp','nygrid_2019_reproduction','cached_upstream');
toolbox=fullfile(root,'tmp','nygrid_2019_reproduction','reduction_toolbox','mirror');
old=pwd;cleanup=onCleanup(@()cd(old));
addpath(toolbox);opts=mpoption('verbose',0,'out.all',0,'exp.use_legacy_core',1);
times=datetime(2019,(1:12)',15,mod((0:11)'*7,24),0,0);
original=cell(12,1);adapted=cell(12,1);elapsed=zeros(12,2);
for variant=1:2
    if variant==1,folder=up;else,folder=cache;end
    cd(folder);addpath(folder,fullfile(folder,'Utility'),'-begin');
    if ~isfolder('Result'),mkdir('Result');end
    assert(startsWith(which('updateOpCond'),folder),'nygrid:ValidationPath','Wrong implementation loaded');
    evalc('base=modifyMPC();');
    for k=1:12
        t=tic;evalc('m=updateOpCond(base,times(k),false,false,true);');
        r=rundcpf(m,opts);assert(r.success&&all(isfinite(r.branch(:,14))));
        record=struct('input',m,'result',r);elapsed(k,variant)=toc(t);
        if variant==1,original{k}=record;else,adapted{k}=record;end
    end
end
bus_error=zeros(12,1);gen_error=bus_error;branch_error=bus_error;dc_error=bus_error;flow_error=bus_error;cost_error=bus_error;
for k=1:12
    a=original{k};b=adapted{k};
    bus_error(k)=max(abs(a.input.bus-b.input.bus),[],'all');
    gen_error(k)=max(abs(a.input.gen-b.input.gen),[],'all');
    branch_error(k)=max(abs(a.input.branch-b.input.branch),[],'all');
    dc_error(k)=max(abs(a.input.dcline-b.input.dcline),[],'all');
    cost_error(k)=max(abs(a.input.gencost-b.input.gencost),[],'all');
    flow_error(k)=max(abs(a.result.branch-b.result.branch),[],'all');
end
passed=max([bus_error gen_error branch_error dc_error cost_error flow_error],[],2)<1e-9;
summary=table(times,elapsed(:,1),elapsed(:,2),bus_error,gen_error,branch_error,dc_error,cost_error,flow_error,passed, ...
    'VariableNames',{'timestamp','unmodified_seconds','cached_seconds','bus_max_diff','gen_max_diff','branch_max_diff','dcline_max_diff','cost_max_diff','flow_max_diff','passed'});
out=fullfile(root,'output','nygrid_2019');
writetable(summary,fullfile(out,'cache_equivalence.csv'));
save(fullfile(out,'cache_equivalence.mat'),'summary','original','adapted');disp(summary);
assert(all(passed),'nygrid:CacheMismatch','Read caching changed the released model.');
end
