function report=run_annual_loss_policy(impedance_mode,loss_mode,run_label)
% Complete8651-source-hour replay. Call only after explicit kernel/policy freeze.
% Original8494 success cohort remains fixed for downstream paired reporting.
if nargin<1,impedance_mode='released_equivalent';end
if nargin<2,loss_mode='boundary_consistent';end
if nargin<3,run_label=[impedance_mode,'_',loss_mode];end
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
addpath(fullfile(root,'scripts','nygrid_2025_acpf_profile_audit','acpf'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_loss_revision','core'));
out=fullfile(root,'output','nygrid_2025_ac_loss_revision','validation','annual',run_label);
assert(~isfile(fullfile(out,'annual_axes.mat')),'acLossReplay:PreservePrior','Choose a new run_label to preserve an existing annual attempt.');
monthly=fullfile(out,'monthly');if ~isfolder(monthly),mkdir(monthly);end
source_records=loss_validation_source_records(root);started=tic;cache=load_profile_cache();canonical=cache.canonical;
options=struct('impedance_mode',impedance_mode,'loss_mode',loss_mode,'backend','compact');
hour_index=(1:8760)';timestamp_utc=cache.dispatch.timestamp_utc(:);source_qualified=cache.qualified;
bus_id=canonical.bus(:,1);base_kv=canonical.bus(:,10);branch_keys=canonical.userdata.ac_system.branch_keys(:);
branch_parent_row=canonical.userdata.ac_system.branch_parent_row;branch_from_bus=canonical.branch(:,1);branch_to_bus=canonical.branch(:,2);
gamma=cache.dispatch.gamma;topology_state_index=cache.state_index;topology_state_names=cache.state_names;
DC_from_bus=canonical.dcline(:,1);DC_to_bus=canonical.dcline(:,2);
external_generator_rows_1based=find(canonical.userdata.ac_system.external_generator_mask);
generator_bus_id=canonical.gen(:,1);
HQ=find(canonical.userdata.ac_system.external_generator_mask&canonical.gen(:,1)==48);assert(isscalar(HQ));
clock=datetime(string(timestamp_utc),'InputFormat','yyyy-MM-dd''T''HH:mm:ss''Z''','TimeZone','UTC');clock.TimeZone='America/New_York';model_month=month(clock);
oldroot=fullfile(root,'output','nygrid_2025_acpf_profile_audit','acpf');old_cohort=false(8760,1);
for mon=1:12
    d=load(fullfile(oldroot,'monthly',sprintf('profile_PF_2025_%02d.mat',mon)),'hour_index','source_qualified','AC_equation_gate','P_profile_preservation_gate');
    old_cohort(d.hour_index)=d.source_qualified&d.AC_equation_gate&d.P_profile_preservation_gate;
end
assert(nnz(old_cohort)==8494&&nnz(source_qualified)==8651);
save(fullfile(out,'annual_axes.mat'),'hour_index','timestamp_utc','source_qualified','old_cohort','bus_id','base_kv','branch_keys', ...
    'branch_parent_row','branch_from_bus','branch_to_bus','gamma','topology_state_index','topology_state_names','model_month', ...
    'DC_from_bus','DC_to_bus','external_generator_rows_1based','generator_bus_id','options','source_records');
ib=cell(4,1);il=cell(4,1);ig=cell(4,1);
for s=1:4
    [ok,ib{s}]=ismember(cache.templates{s}.bus(:,1),bus_id);assert(all(ok));
    [ok,il{s}]=ismember(string(cache.templates{s}.userdata.ac_system.branch_keys),string(branch_keys));assert(all(ok));
    [ok,ig{s}]=ismember(cache.templates{s}.gen(:,1),bus_id);assert(all(ok));
end
ws=warning;cleanup=onCleanup(@()warning(ws));warning('off','MATLAB:nearlySingularMatrix');warning('off','MATLAB:singularMatrix');
audits=cell(8760,1);files=struct([]);attempted=0;exception_count=0;converged_count=0;qualified_count=0;
qualified=false(8760,1);annual_exceptions=struct([]);nb=numel(bus_id);nl=numel(branch_keys);
flag_names={'PF_converged','AC_equation_gate','loss_allocation_gate','reduction_and_equation_gate','VQ_and_generator_assumption_gate'};
scalar_names={'native_PG_change_from_original_MW','HQ_PG_change_from_original_MW','NY_gross_load_accounting_residual_MW', ...
    'regional_NY_import_residual_MW','max_P_bound_violation_mw','max_fixed_transfer_P_change_mw','loss_budget_residual_MW', ...
    'reference_PG_change_from_original_MW','maximum_NY_zonal_loss_fraction','minimum_NY_served_PD_MW','loss_iterations','total_NR_iterations'};
for mon=1:12
    month_start=tic;hh=find(model_month==mon);nh=numel(hh);
    chunk=struct('hour_index',hh,'timestamp_utc',{timestamp_utc(hh)},'gamma',gamma,'source_qualified',source_qualified(hh), ...
        'frozen_old_qualified',old_cohort(hh),'bus_id',bus_id,'base_kv',base_kv,'branch_keys',{branch_keys}, ...
        'branch_parent_row',branch_parent_row,'branch_from_bus',branch_from_bus,'branch_to_bus',branch_to_bus, ...
        'DC_from_bus',DC_from_bus,'DC_to_bus',DC_to_bus,'topology_state_index',cache.state_index(hh), ...
        'external_generator_rows_1based',external_generator_rows_1based,'generator_bus_id',generator_bus_id, ...
        'impedance_mode',impedance_mode,'loss_mode',loss_mode);
    for name={'VM','VA','PD','QD','bus_PG','bus_QG'},chunk.(name{1})=nan(nh,nb);end
    for name={'PF','QF','PT','QT','Iseries','Ifrom','Ito'},chunk.(name{1})=nan(nh,nl);end
    for name={'DC_PF','DC_PT','DC_QF','DC_QT'},chunk.(name{1})=nan(nh,6);end
    chunk.external_gen_PG=nan(nh,28);chunk.NY_gross_target_MW=nan(nh,11);chunk.NY_served_PD_MW=nan(nh,11);
    chunk.NY_served_QD_MVAr=nan(nh,11);chunk.actual_budget_MW=nan(nh,14);
    chunk.regional_import_target_MW=nan(nh,3);chunk.regional_import_solved_MW=nan(nh,3);chunk.external_PG_increment_MW=nan(nh,3);
    chunk.Dover_model_SHIFT_deg=nan(nh,2);chunk.retained_bus_ids=[];
    chunk.retained_VM=nan(nh,148);chunk.retained_VA=nan(nh,148);
    chunk.bus_present=false(nh,nb);chunk.branch_present=false(nh,nl);chunk.branch_active=false(nh,nl);
    chunk.PF_attempted=false(nh,1);chunk.solver_exception=false(nh,1);chunk.computed_current_available=false(nh,1);
    chunk.loss_status=repmat({''},nh,1);chunk.total_call_seconds=nan(nh,1);
    for name=flag_names,chunk.(name{1})=false(nh,1);end
    for name=scalar_names,chunk.(name{1})=nan(nh,1);end
    month_trace=cell(nh,1);
    for j=1:nh
        h=hh(j);if ~source_qualified(h),continue;end
        baseline=profile_case_from_cache(cache,h);s=cache.state_index(h);attempted=attempted+1;chunk.PF_attempted(j)=true;
        try
            t=tic;[compact,audit,r,allocation]=run_nygrid_2025_loss_consistent_acpf(baseline,options);call_seconds=toc(t);
        catch err
            exception_count=exception_count+1;chunk.solver_exception(j)=true;
            item=struct('hour_index',h,'identifier',err.identifier,'message',err.message,'report',getReport(err,'extended'));
            annual_exceptions=[annual_exceptions item]; %#ok<AGROW>
            save(fullfile(out,sprintf('solver_exception_h%04d.mat',h)),'baseline','options','item');
            fprintf('LOSS_YEAR exception h%d %s\n',h,err.identifier);continue;
        end
        audit.HQ_PG_change_from_original_MW=r.gen(HQ,2)-baseline.gen(HQ,2);audit.total_call_seconds=call_seconds;
        audits{h}=audit;month_trace{j}=allocation.trace;chunk.total_call_seconds(j)=call_seconds;
        chunk.loss_status{j}=audit.loss_status;
        for name=flag_names,chunk.(name{1})(j)=audit.(name{1});end
        for name=scalar_names,chunk.(name{1})(j)=audit.(name{1});end
        converged_count=converged_count+audit.PF_converged;
        good=audit.PF_converged&&audit.AC_equation_gate&&audit.reduction_and_equation_gate;
        if strcmp(loss_mode,'boundary_consistent'),good=good&&audit.loss_allocation_gate;end
        qualified(h)=good;qualified_count=qualified_count+good;chunk.computed_current_available(j)=good;
        m=allocation.final_input;assert(numel(compact.retained_bus_ids)==148);
        if isempty(chunk.retained_bus_ids),chunk.retained_bus_ids=compact.retained_bus_ids;else,assert(isequal(chunk.retained_bus_ids,compact.retained_bus_ids));end
        chunk.retained_VM(j,:)=compact.bus(:,8);chunk.retained_VA(j,:)=compact.bus(:,9);
        chunk.VM(j,ib{s})=r.bus(:,8);chunk.VA(j,ib{s})=r.bus(:,9);chunk.PD(j,ib{s})=m.bus(:,3);chunk.QD(j,ib{s})=m.bus(:,4);
        chunk.bus_present(j,ib{s})=true;chunk.branch_present(j,il{s})=true;chunk.branch_active(j,il{s})=m.branch(:,11)>0;
        chunk.bus_PG(j,:)=accumarray(ig{s},r.gen(:,2),[nb 1])';chunk.bus_QG(j,:)=accumarray(ig{s},r.gen(:,3),[nb 1])';
        chunk.PF(j,il{s})=r.branch(:,14);chunk.QF(j,il{s})=r.branch(:,15);chunk.PT(j,il{s})=r.branch(:,16);chunk.QT(j,il{s})=r.branch(:,17);
        chunk.Ifrom(j,il{s})=compact.recovered_line_current_A(:,1);chunk.Ito(j,il{s})=compact.recovered_line_current_A(:,2);chunk.Iseries(j,il{s})=compact.recovered_line_current_A(:,3);
        chunk.DC_PF(j,:)=r.dcline(:,4);chunk.DC_PT(j,:)=r.dcline(:,5);chunk.DC_QF(j,:)=r.dcline(:,6);chunk.DC_QT(j,:)=r.dcline(:,7);
        chunk.external_gen_PG(j,:)=r.gen(external_generator_rows_1based,2);
        chunk.NY_gross_target_MW(j,:)=allocation.NY_gross_target_MW;chunk.NY_served_PD_MW(j,:)=allocation.NY_served_PD_MW;
        chunk.NY_served_QD_MVAr(j,:)=allocation.NY_served_QD_MVAr;chunk.actual_budget_MW(j,:)=allocation.actual_budget_MW;
        chunk.regional_import_target_MW(j,:)=allocation.regional_import_target_MW;chunk.regional_import_solved_MW(j,:)=allocation.regional_import_solved_MW;
        chunk.external_PG_increment_MW(j,:)=allocation.external_PG_increment_MW;
        if cache.dover.post_full_service(h),chunk.Dover_model_SHIFT_deg(j,:)=m.branch(411:412,10);end
    end
    path=fullfile(monthly,sprintf('profile_PF_2025_%02d.mat',mon));save(path,'-struct','chunk','-v7');
    save(fullfile(monthly,sprintf('loss_iteration_traces_2025_%02d.mat',mon)),'hh','month_trace','-v7');
    values=audits(hh);values=[values{~cellfun(@isempty,values)}];writetable(struct2table(values),fullfile(monthly,sprintf('profile_PF_2025_%02d_quality.csv',mon)));
    info=dir(path);assert(info.bytes<100e6);
    f=struct('month',mon,'path',path,'bytes',info.bytes,'source_qualified',nnz(source_qualified(hh)),'PF_converged',sum(chunk.PF_converged), ...
        'policy_equation_qualified',sum(qualified(hh)),'VQ_qualified',sum(chunk.VQ_and_generator_assumption_gate),'elapsed_seconds',toc(month_start));files=[files f]; %#ok<AGROW>
    progress=struct('completed',false,'run_label',run_label,'months_complete',mon,'attempted',attempted,'converged',converged_count, ...
        'qualified',qualified_count,'solver_exceptions',exception_count,'elapsed_seconds',toc(started),'files',files);
    fid=fopen(fullfile(out,'annual_progress.json'),'w');fprintf(fid,'%s\n',jsonencode(progress,'PrettyPrint',true));fclose(fid);
    fprintf('LOSS_YEAR month%02d source%d PF%d policyEq%d VQ%d %.1fs total%.1fs\n',mon,f.source_qualified,f.PF_converged,f.policy_equation_qualified,f.VQ_qualified,f.elapsed_seconds,toc(started));
end
current_records=loss_validation_source_records(root);assert(isequal(source_records,current_records),'acLossReplay:SourceChanged','Source files changed during annual replay; preserve this attempt and repeat after freeze.');
values=[audits{~cellfun(@isempty,audits)}];writetable(struct2table(values),fullfile(out,'annual_hour_quality.csv'));
report=struct('completed',true,'replay_integrity_passed',attempted==8651&&exception_count==0,'run_label',run_label,'options',options, ...
    'source_qualified_hours',8651,'attempted_hours',attempted,'PF_converged_hours',converged_count,'policy_equation_qualified_hours',qualified_count, ...
    'AC_equation_qualified_hours',sum([values.AC_equation_gate]),'loss_allocation_qualified_hours',sum([values.loss_allocation_gate]), ...
    'VQ_and_generator_assumption_qualified_hours',sum([values.VQ_and_generator_assumption_gate]),'solver_exceptions',exception_count, ...
    'source_qualified_but_not_policy_equation_qualified_hours',find(source_qualified&~qualified), ...
    'frozen_old_qualified_hours',8494,'paired_old_new_qualified_hours',nnz(old_cohort&qualified), ...
    'old_qualified_now_lost_hours',find(old_cohort&~qualified),'new_qualified_from_old_failed_hours',find(source_qualified&~old_cohort&qualified), ...
    'elapsed_seconds',toc(started),'files',files,'exceptions',annual_exceptions,'source_records',source_records, ...
    'source_files_unchanged_during_replay',true,'all_8760_clock_rows_exported',true,'canonical_bus_count',nb,'canonical_branch_count',nl, ...
    'native_voltage_solver_unknowns_retained_bus_count',148,'no_full_network_Newton_used',true,'OPF_or_observation_fitting_used',false, ...
    'failed_or_partial_iterates_retained_and_flagged',true,'full_physical_qualification_separate_from_accounting',true, ...
    'global_infeasibility_not_inferred_from_failed_iterations',true);
fid=fopen(fullfile(out,'annual_loss_policy_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
progress.completed=true;progress.elapsed_seconds=report.elapsed_seconds;progress.final_receipt='annual_loss_policy_receipt.json';
fid=fopen(fullfile(out,'annual_progress.json'),'w');fprintf(fid,'%s\n',jsonencode(progress,'PrettyPrint',true));fclose(fid);
fprintf('LOSS_YEAR_COMPLETE attempted%d PF%d qualified%d exceptions%d elapsed%.1fs\n',attempted,converged_count,qualified_count,exception_count,report.elapsed_seconds);
end
