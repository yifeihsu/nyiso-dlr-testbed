function inspect_runtime_cases(matpower_root)
% Fresh loader/policy checks only. This does not run a power flow.
if nargin<1,matpower_root='C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower';end
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
runtime=fullfile(root,'scripts','nygrid_2025_moses_repair','delivery','runtime');
out=fullfile(root,'output','nygrid_2025_moses_repair','delivery');
addpath(runtime);setup=setup_nygrid_latest(root,matpower_root);[model,receipt]=nylatest_data();
prior=load(fullfile(root,'output','nygrid_2025_physical_repair','model','latest_model.mat'),'model');
assert(isequaln(model.thermal,prior.model.thermal)&&isequaln(model.physical_repair,prior.model.physical_repair));
q=logical(model.axis.source_qualified(:));times=datetime(string(model.axis.timestamp_utc(:)),'InputFormat','yyyy-MM-dd''T''HH:mm:ss''Z''','TimeZone','UTC');
times.TimeZone='America/New_York';pv=model.profiles.generator_PG_MW(:,1466);
hours=[];
for month_number=1:12
    hours(end+1)=find(q&month(times)==month_number,1); %#ok<AGROW>
end
available=find(q);[~,idx]=min(pv(available));hours(end+1)=available(idx);
hours(end+1)=find(q&pv==0,1);hours=unique(hours);
rows=cell(numel(hours),1);
for j=1:numel(hours)
    h=hours(j);m=load_nygrid_latest(h);p=nylatest_prepare_policy(m);
    assert(size(m.gen,1)==1466&&m.gen(1466,1)==49);
    assert(all(m.gen(1466,[3 4 5])==0)&&all(m.gen(1466,[9 10])==m.gen(1466,2)));
    assert(m.userdata.ac_system.generator_capability_reference(1466)==abs(m.gen(1466,2)));
    assert(m.userdata.ac_system.generator_assumed_s_cap(1466)==abs(m.gen(1466,2)));
    assert(~p.native(1466)&&p.native(1465)&&p.external_gen_group(1466)==12&&p.generator_share(1466)==0);
    expected=ones(size(m.bus,1),1);active=m.gen(:,8)>0;active(1466)=false;
    expected(ismember(m.bus(:,1),m.gen(active,1)))=2;expected(m.bus(:,1)==p.reference_bus)=3;
    assert(isequal(m.bus(:,2),expected));
    if month(times(h))<=2,assert(m.gen(317,8)==0&&m.gen(1465,8)==1);
    else,assert(m.gen(317,8)==1&&m.gen(1465,8)==0);end
    budget=zeros(14,1);
    for group=12:14
        eligible=p.external_gen_group==group&p.generator_share>0;
        room=sum(p.Pmax(eligible)-p.baseline_PG(eligible));
        budget(group)=min(1,max(0,room*.1));
    end
    [adjusted,a]=nylatest_apply_budget(m,p,budget);
    assert(adjusted.gen(1466,2)==m.gen(1466,2)&&all(adjusted.gen(1466,3:5)==0));
    rows{j}=struct('hour_index',h,'month_local',month(times(h)), ...
        'PV20_PG_model_MW',m.gen(1466,2),'PV20_PG_public_MW',m.gen(1466,2)/model.scale_factor_gamma, ...
        'PV20_active_status',m.gen(1466,8),'PV20_Qcap_MVAr',m.gen(1466,4), ...
        'PV20_assumed_Scap_MVA',m.userdata.ac_system.generator_assumed_s_cap(1466), ...
        'unit26_active_status',m.gen(317,8),'unit21_active_status',m.gen(1465,8), ...
        'external_loss_budget_MW',sum(budget(12:14)), ...
        'fixed_boundary_unchanged_under_loss_allocation',a.fixed_boundary_P_unchanged);
end
proof=struct('passed',true,'review_kind','fresh_runtime_loader_and_policy_without_PF', ...
    'model_sha256',receipt.model_file.sha256,'setup',setup,'cases',[rows{:}], ...
    'source_extreme_and_monthly_first_qualified_selection',true, ...
    'all_thermal_tables_and_prior_physical_repair_metadata_unchanged',true,'new_AC_solves',0);
if ~isfolder(out),mkdir(out);end
fid=fopen(fullfile(out,'independent_runtime_loader_review.json'),'w');
assert(fid>=0);fprintf(fid,'%s\n',jsonencode(proof,'PrettyPrint',true));fclose(fid);
fprintf('INDEPENDENT_RUNTIME_LOADER_PASS %d cases, noPF\n',numel(hours));
end
