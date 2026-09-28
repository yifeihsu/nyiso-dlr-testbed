function run_upstream_smoke(toolbox_variant)
% Run the released, unmodified paper model before any performance adaptation.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
upstream=fullfile(root,'tmp','nygrid_2019_reproduction','upstream');
if nargin<1,toolbox_variant='mirror';end
toolbox=fullfile(root,'tmp','nygrid_2019_reproduction','reduction_toolbox',toolbox_variant);
if strcmp(toolbox_variant,'official'),toolbox=fullfile(toolbox,'NetworkReduction2');end
outdir=fullfile(root,'output','nygrid_2019');
old=pwd;cleanup=onCleanup(@()cd(old));cd(upstream);
addpath(upstream,fullfile(upstream,'Utility'),toolbox);
if ~isfolder('Result'),mkdir('Result');end
set(groot,'defaultFigureVisible','off');
fprintf('MATLAB %s; MATPOWER %s; reduction %s\n',version,mpver,which('MPReduction'));
base=modifyMPC();
times=[datetime(2019,1,1,0,0,0);datetime(2019,7,20,17,0,0)];
rows=cell(numel(times),1);cases=cell(numel(times),1);logs=cell(numel(times),1);
for k=1:numel(times)
    timer=tic;
    try
        logs{k}=evalc('m=updateOpCond(base,times(k),false,false,true);');
        [r,success]=rundcpf(m,mpoption('verbose',0,'out.all',0,'exp.use_legacy_core',1));
        [~,obs,lims]=readOpCond(times(k));
        [sim,actual,err,names]=flow4Plot(r,obs,lims);
        cases{k}=struct('input',m,'result',r);
        rows{k}=table(repmat(times(k),7,1),names(:),sim,actual,100*err, ...
            repmat(success,7,1),'VariableNames',{'timestamp','interface','simulated_mw','observed_mw','paper_error_pct','pf_success'});
        fprintf('%s buses=%d branches=%d gens=%d success=%d finite=%d seconds=%.2f\n',string(times(k)),size(m.bus,1),size(m.branch,1),size(m.gen,1),success,all(isfinite(sim)),toc(timer));
        disp(rows{k});
    catch e
        logs{k}=getReport(e,'extended','hyperlinks','off');
        fprintf('%s\n',logs{k});
    end
end
save(fullfile(outdir,['unmodified_smoke_' toolbox_variant '_legacy.mat']),'base','cases','logs','times','rows');
if any(~cellfun(@isempty,rows)),writetable(vertcat(rows{:}),fullfile(outdir,['unmodified_smoke_' toolbox_variant '_legacy.csv']));end
end
