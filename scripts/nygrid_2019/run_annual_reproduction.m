function run_annual_reproduction(first_hour,last_hour,run_id)
% Reproduce the released 2019 DC model with separately validated read caching.
if nargin<1,first_hour=1;end
if nargin<2,last_hour=8760;end
if nargin<3,run_id='annual';end
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
upstream=fullfile(root,'tmp','nygrid_2019_reproduction','upstream');
cached=fullfile(root,'tmp','nygrid_2019_reproduction','cached_upstream');
toolbox=fullfile(root,'tmp','nygrid_2019_reproduction','reduction_toolbox','mirror');
outdir=fullfile(root,'output','nygrid_2019');
old=pwd;cleanup=onCleanup(@()cd(old));cd(cached);
addpath(upstream,fullfile(upstream,'Utility'),toolbox);
assert(isfolder(cached),'nygrid:MissingCache','First prepare and validate the read-cache adaptation.');
addpath(genpath(cached),'-begin');
assert(contains(which('updateOpCond'),cached),'nygrid:CachePath','Expected the isolated cached implementation.');
opts=mpoption('verbose',0,'out.all',0,'exp.use_legacy_core',1);
evalc('base=modifyMPC();');
times=datetime(2019,1,1)+hours((first_hour:last_hour)'-1);
n=numel(times);sim=nan(n,7);actual=nan(n,7);paper=nan(n,7);limit=nan(n,7);corrected_sim=nan(n,7);
status=false(n,1);errors=strings(n,1);seconds=nan(n,1);
branch_pf=nan(n,94);bus_pd=nan(n,57);bus_va=nan(n,57);input_pg=nan(n,271);result_pg=nan(n,271);
dc_pf=nan(n,4);balance_residual=nan(n,1);base_case=[];
selected_cases=cell(n,1);
timer=tic;
for k=1:n
    t=tic;
    try
        evalc('m=updateOpCond(base,times(k),false,false,true);');
        [r,success]=rundcpf(m,opts);
        assert(success&&all(isfinite(r.branch(:,14))),'nygrid:Nonfinite','DC result failed or contains nonfinite branch flows.');
        assert(size(m.bus,1)==57&&size(m.branch,1)==94&&size(m.gen,1)==271,'nygrid:Inventory','Unexpected paper model inventory.');
        [~,obs,lims]=readOpCond(times(k));
        [f,a,e,names]=flow4Plot(r,obs,lims);
        sim(k,:)=f';actual(k,:)=a';paper(k,:)=100*e';
        % Released if.map matches geographic crossings; flow4Plot is stale
        % for five interfaces. Score both on precisely the same solution.
        interface_ids=[1,2,3,4,5,8,10];
        for j=1:7
            members=m.if.map(m.if.map(:,1)==interface_ids(j),2);
            corrected_sim(k,j)=sum(sign(members).*r.branch(abs(members),14));
        end
        % The helper returns observed minus simulated divided by positive limit.
        channels=["DYSINGER EAST","WEST CENTRAL","TOTAL EAST","MOSES SOUTH","CENTRAL EAST - VC","UPNY CONED","SPR/DUN-SOUTH"];
        for j=1:7,limit(k,j)=lims.PositiveLimitMWH(lims.InterfaceName==channels(j));end
        if isempty(base_case),base_case=m;end
        assert(isequal(m.bus(:,1),base_case.bus(:,1))&&isequal(m.gen(:,1),base_case.gen(:,1)) ...
            &&max(abs(m.branch(:,1:13)-base_case.branch(:,1:13)),[],'all')<1e-10,'nygrid:ChangedTopology','Unexpected hourly topology or generator-location variation.');
        branch_pf(k,:)=r.branch(:,14)';bus_pd(k,:)=m.bus(:,3)';bus_va(k,:)=r.bus(:,9)';
        input_pg(k,:)=m.gen(:,2)';result_pg(k,:)=r.gen(:,2)';dc_pf(k,:)=m.dcline(:,4)';
        % Independent nodal accounting, including the four lossless DC links.
        [~,gf]=ismember(r.gen(:,1),r.bus(:,1));[~,bf]=ismember(r.branch(:,1),r.bus(:,1));[~,bt]=ismember(r.branch(:,2),r.bus(:,1));
        [~,df]=ismember(r.dcline(:,1),r.bus(:,1));[~,dt]=ismember(r.dcline(:,2),r.bus(:,1));
        inj=accumarray(gf,r.gen(:,2),[57,1])-r.bus(:,3)-r.bus(:,5);
        exits=accumarray(bf,r.branch(:,14),[57,1])+accumarray(bt,r.branch(:,16),[57,1]) ...
            +accumarray(df,r.dcline(:,4),[57,1])-accumarray(dt,r.dcline(:,5),[57,1]);
        balance_residual(k)=max(abs(inj-exits));
        assert(balance_residual(k)<1e-6,'nygrid:NodalBalance','DC nodal accounting failed.');
        status(k)=true;
        if n<=48||day(times(k))==1&&hour(times(k))==0,selected_cases{k}=struct('input',m,'result',r);end
    catch e
        errors(k)=string(e.identifier)+": "+string(e.message);
        fprintf('FAIL %s %s\n',string(times(k)),errors(k));
    end
    seconds(k)=toc(t);
    if mod(k,24)==0||k==1||k==n
        fprintf('%s %d/%d successful=%d elapsed=%.1fs mean=%.3fs/hour\n',run_id,k,n,nnz(status),toc(timer),toc(timer)/k);
    end
    if mod(k,168)==0||k==n
        save(fullfile(outdir,[run_id '.mat']),'times','sim','corrected_sim','actual','paper','limit','status','errors','seconds', ...
            'branch_pf','bus_pd','bus_va','input_pg','result_pg','dc_pf','balance_residual','base_case','selected_cases','first_hour','last_hour');
    end
end
case_summary=table(times,status,seconds,balance_residual,errors);
writetable(case_summary,fullfile(outdir,[run_id '_cases.csv']));
rows=table(repelem(times,7),repmat(names(:),n,1),reshape(sim',[],1),reshape(corrected_sim',[],1),reshape(actual',[],1),reshape(limit',[],1),reshape(paper',[],1),repelem(status,7), ...
    'VariableNames',{'timestamp','interface','released_plot_mw','corrected_operator_mw','observed_mw','positive_limit_mw','released_paper_error_pct','pf_success'});
writetable(rows,fullfile(outdir,[run_id '_interfaces.csv']));
end
