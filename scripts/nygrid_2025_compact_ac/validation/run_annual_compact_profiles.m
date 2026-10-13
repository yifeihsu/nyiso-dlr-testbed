function report=run_annual_compact_profiles()
% Native148 retained-voltage PF on all8651 unchanged source profiles.
% Frozen detailed8494 success cohort is compared without rerunning the year.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'scripts','nygrid_2025_acpf_profile_audit','acpf'));
addpath(fullfile(root,'scripts','nygrid_2025_compact_ac','core'));
out=fullfile(root,'output','nygrid_2025_compact_ac','validation');monthly=fullfile(out,'monthly');
baseline=fullfile(root,'output','nygrid_2025_acpf_profile_audit','acpf');
if ~isfolder(monthly),mkdir(monthly);end
proof=jsondecode(fileread(fullfile(out,'representative_pairs','representative_pair_receipt.json')));assert(proof.passed);
registry=readtable(fullfile(root,'output','nygrid_2025_slim','network','bus_register.csv'));anchors=double(registry.model_bus(:));assert(numel(anchors)==148);
all_start=tic;cache=load_profile_cache();canonical=cache.canonical;
hour_index=(1:8760)';timestamp_utc=cache.dispatch.timestamp_utc(:);source_qualified=cache.qualified;
bus_id=canonical.bus(:,1);base_kv=canonical.bus(:,10);branch_keys=canonical.userdata.ac_system.branch_keys(:);
branch_parent_row=canonical.userdata.ac_system.branch_parent_row;branch_from_bus=canonical.branch(:,1);branch_to_bus=canonical.branch(:,2);
gamma=cache.dispatch.gamma;topology_state_index=cache.state_index;topology_state_names=cache.state_names;
DC_from_bus=canonical.dcline(:,1);DC_to_bus=canonical.dcline(:,2);
clock=datetime(string(timestamp_utc),'InputFormat','yyyy-MM-dd''T''HH:mm:ss''Z''','TimeZone','UTC');clock.TimeZone='America/New_York';
model_month=month(clock);assert(all(year(clock)==2025));
save(fullfile(out,'annual_axes.mat'),'hour_index','timestamp_utc','source_qualified','bus_id','base_kv','branch_keys', ...
    'branch_parent_row','branch_from_bus','branch_to_bus','gamma','topology_state_index','topology_state_names','model_month','DC_from_bus','DC_to_bus');
opt=mpoption('model','AC','verbose',0,'out.all',0,'pf.alg','NR','pf.nr.max_it',50, ...
    'pf.tol',1e-10,'pf.enforce_q_lims',0,'exp.use_legacy_core',1);
warning_state=warning;cleanup=onCleanup(@()warning(warning_state));
warning('off','MATLAB:nearlySingularMatrix');warning('off','MATLAB:singularMatrix');
all_audits=cell(8760,1);all_pairs=cell(8760,1);files=struct([]);attempted=0;converged_count=0;exception_count=0;
ib=cell(4,1);il=cell(4,1);ig=cell(4,1);
for s=1:4
    [ok,ib{s}]=ismember(cache.templates{s}.bus(:,1),bus_id);assert(all(ok));
    [ok,il{s}]=ismember(string(cache.templates{s}.userdata.ac_system.branch_keys),string(branch_keys));assert(all(ok));
    [ok,ig{s}]=ismember(cache.templates{s}.gen(:,1),bus_id);assert(all(ok));
end
for mon=1:12
    month_start=tic;hh=find(model_month==mon);nh=numel(hh);nb=numel(bus_id);nl=numel(branch_keys);
    old=load(fullfile(baseline,'monthly',sprintf('profile_PF_2025_%02d.mat',mon)));
    assert(isequal(old.hour_index,hh)&&isequal(old.bus_id,bus_id)&&isequal(string(old.branch_keys),string(branch_keys)));
    chunk=struct('hour_index',hh,'timestamp_utc',{timestamp_utc(hh)},'gamma',gamma, ...
        'source_qualified',cache.qualified(hh),'bus_id',bus_id,'base_kv',base_kv,'branch_keys',{branch_keys}, ...
        'branch_parent_row',branch_parent_row,'branch_from_bus',branch_from_bus,'branch_to_bus',branch_to_bus, ...
        'DC_from_bus',DC_from_bus,'DC_to_bus',DC_to_bus,'topology_state_index',cache.state_index(hh));
    for name={'VM','VA','PD','QD','bus_PG','bus_QG'},chunk.(name{1})=nan(nh,nb);end
    for name={'PF','QF','PT','QT','Iseries','Ifrom','Ito'},chunk.(name{1})=nan(nh,nl);end
    for name={'DC_PF','DC_PT','DC_QF','DC_QT'},chunk.(name{1})=nan(nh,6);end
    chunk.Dover_model_SHIFT_deg=nan(nh,2);
    chunk.retained_bus_ids=anchors;chunk.retained_VM=nan(nh,148);chunk.retained_VA=nan(nh,148);
    chunk.reduction_and_equation_gate=false(nh,1);chunk.native_retained_bus_count=nan(nh,1);
    chunk.detailed_baseline_qualified=old.AC_equation_gate&old.P_profile_preservation_gate;
    chunk.paired_detailed_solution_equivalent=false(nh,1);
    chunk.bus_present=false(nh,nb);chunk.branch_present=false(nh,nl);chunk.branch_active=false(nh,nl);
    for name={'PF_attempted','PF_converged','AC_equation_gate','P_profile_preservation_gate','VQ_and_generator_assumption_gate','computed_current_available','solver_exception'}
        chunk.(name{1})=false(nh,1);
    end
    for j=1:nh
        h=hh(j);if ~cache.qualified(h),continue;end
        m=profile_case_from_cache(cache,h);s=cache.state_index(h);attempted=attempted+1;chunk.PF_attempted(j)=true;
        try
            t=tic;c=compact_ac_build(m,anchors);build_seconds=toc(t);
            assert(numel(c.retained_bus_ids)==148&&isempty(c.promoted_bus_ids));
            t=tic;[compact,audit,r]=compact_ac_solve(c,opt);pf_seconds=toc(t);
            audit.PF_seconds=pf_seconds;audit.compact_build_seconds=build_seconds;audit.native_NR_seconds=compact.et;
            chunk.retained_VM(j,:)=compact.bus(:,8);chunk.retained_VA(j,:)=compact.bus(:,9);
            chunk.reduction_and_equation_gate(j)=audit.reduction_and_equation_gate;
            chunk.native_retained_bus_count(j)=numel(c.retained_bus_ids);
        catch err
            exception_count=exception_count+1;chunk.solver_exception(j)=true;
            error_text=getReport(err,'extended');save(fullfile(out,sprintf('solver_exception_h%04d.mat',h)),'m','opt','error_text');
            fprintf('COMPACT_YEAR exception hour%d %s\n',h,err.identifier);continue;
        end
        all_audits{h}=audit;converged_count=converged_count+audit.PF_converged;
        for name={'PF_converged','AC_equation_gate','P_profile_preservation_gate','VQ_and_generator_assumption_gate','computed_current_available'}
            chunk.(name{1})(j)=audit.(name{1});
        end
        chunk.VM(j,ib{s})=r.bus(:,8);chunk.VA(j,ib{s})=r.bus(:,9);
        chunk.PD(j,ib{s})=m.bus(:,3);chunk.QD(j,ib{s})=m.bus(:,4);chunk.bus_present(j,ib{s})=true;
        chunk.bus_PG(j,:)=accumarray(ig{s},r.gen(:,2),[nb 1])';chunk.bus_QG(j,:)=accumarray(ig{s},r.gen(:,3),[nb 1])';
        chunk.PF(j,il{s})=r.branch(:,14);chunk.QF(j,il{s})=r.branch(:,15);chunk.PT(j,il{s})=r.branch(:,16);chunk.QT(j,il{s})=r.branch(:,17);
        chunk.Iseries(j,il{s})=compact.recovered_line_current_A(:,3);chunk.Ifrom(j,il{s})=compact.recovered_line_current_A(:,1);chunk.Ito(j,il{s})=compact.recovered_line_current_A(:,2);
        chunk.branch_present(j,il{s})=true;chunk.branch_active(j,il{s})=m.branch(:,11)>0;
        chunk.DC_PF(j,:)=r.dcline(:,4);chunk.DC_PT(j,:)=r.dcline(:,5);chunk.DC_QF(j,:)=r.dcline(:,6);chunk.DC_QT(j,:)=r.dcline(:,7);
        if cache.dover.post_full_service(h),chunk.Dover_model_SHIFT_deg(j,:)=m.branch(411:412,10);end
        paired=compare_saved_pair(old,chunk,j,h,ib{s},il{s});all_pairs{h}=paired;
        chunk.paired_detailed_solution_equivalent(j)=paired.solution_equivalent;
    end
    path=fullfile(monthly,sprintf('profile_PF_2025_%02d.mat',mon));save(path,'-struct','chunk','-v7');
    month_audits=all_audits(hh);use=~cellfun(@isempty,month_audits);a=[month_audits{use}];
    writetable(struct2table(a),fullfile(monthly,sprintf('profile_PF_2025_%02d_quality.csv',mon)));
    info=dir(path);assert(info.bytes<100e6,'profilePF:FileSize','Monthly file exceeds Git size limit.');
    f=struct('month',mon,'path',path,'bytes',info.bytes,'hours',nh,'source_qualified',nnz(cache.qualified(hh)), ...
        'converged',sum(chunk.PF_converged),'equation_gate',sum(chunk.AC_equation_gate),'profile_gate',sum(chunk.P_profile_preservation_gate), ...
        'VQ_assumption_gate',sum(chunk.VQ_and_generator_assumption_gate),'seconds',toc(month_start));files=[files f]; %#ok<AGROW>
    progress=struct('completed',false,'months_complete',mon,'attempted',attempted,'converged',converged_count,'solver_exceptions',exception_count,'elapsed_seconds',toc(all_start),'files',files);
    fid=fopen(fullfile(out,'annual_progress.json'),'w');fprintf(fid,'%s\n',jsonencode(progress,'PrettyPrint',true));fclose(fid);
    fprintf('COMPACT_YEAR month%02d q%d PF%d eq%d Pprofile%d VQ%d %.1fs file%.1fMB total%.1fs\n',mon,f.source_qualified,f.converged,f.equation_gate,f.profile_gate,f.VQ_assumption_gate,f.seconds,info.bytes/1e6,toc(all_start));
end
use=~cellfun(@isempty,all_audits);audits=[all_audits{use}];writetable(struct2table(audits),fullfile(out,'annual_hour_quality.csv'));
failed_hours=[audits(~[audits.PF_converged]).hour_index]';
report=struct('completed',true,'source_qualified_hours',nnz(cache.qualified),'attempted_hours',attempted,'solver_exceptions',exception_count, ...
    'PF_converged_hours',sum([audits.PF_converged]),'AC_equation_qualified_hours',sum([audits.AC_equation_gate]), ...
    'P_profile_preserved_hours',sum([audits.P_profile_preservation_gate]), ...
    'VQ_and_generator_assumption_qualified_hours',sum([audits.VQ_and_generator_assumption_gate]), ...
    'failed_NR_hours',failed_hours,'elapsed_seconds',toc(all_start),'files',files, ...
    'OPF_used',false,'generation_profiles_redispatched',false,'only_original_reference_generator_P_balances_losses',true, ...
    'all_8760_clock_hours_exported_in_monthly_files',true,'canonical_bus_count',numel(bus_id),'canonical_branch_count',numel(branch_keys), ...
    'previous_solution_or_internal_interface_values_used_as_initial_state',false, ...
    'pf_enforce_q_lims',0,'backend','MATPOWER_newtonpf_native148_complex_Kron','overload_not_used_as_convergence_gate',true, ...
    'all_Newton_solves_use_148_retained_buses',true,'full_network_Newton_solve_used',false, ...
    'internal_interface_measurements_used_as_solver_input',false, ...
    'reduction_and_equation_qualified_hours',sum([audits.reduction_and_equation_gate]), ...
    'maximum_recovered_current_operator_crosscheck_A',max([audits([audits.AC_equation_gate]).recovered_current_operator_crosscheck_A]), ...
    'maximum_eliminated_current_residual_pu',max([audits([audits.AC_equation_gate]).eliminated_current_residual_pu]), ...
    'global_infeasibility_from_failed_NR_claimed',false,'failed_outputs_retained_with_flags',true, ...
    'normal_voltage_range_pu',[.95 1.05],'broad_voltage_diagnostic_range_pu',[.9 1.1]);
pairs=[all_pairs{~cellfun(@isempty,all_pairs)}];
writetable(struct2table(pairs),fullfile(out,'paired_detailed_error.csv'));
qualified=[pairs.detailed_baseline_qualified];both=qualified&[pairs.compact_equation_qualified];new=[pairs.compact_equation_qualified]&~qualified;
report.fixed_detailed_paired_cohort_hours=sum(qualified);assert(sum(qualified)==8494);
report.fixed_detailed_cohort_native_qualified_hours=sum(both);
report.fixed_detailed_cohort_equivalent_hours=sum([pairs.solution_equivalent]);
report.compact_failed_on_detailed_qualified_hours=[pairs(qualified&~[pairs.compact_equation_qualified]).hour_index];
report.new_compact_qualified_on_prior_failed_hours=[pairs(new).hour_index];
report.maximum_paired_complex_voltage_difference_pu=max([pairs(both).maximum_voltage_difference_pu]);
report.maximum_paired_branch_PQ_difference_MVA=max([pairs(both).maximum_branch_PQ_difference_MVA]);
report.maximum_paired_original_branch_current_difference_A=max([pairs(both).maximum_current_difference_A]);
report.maximum_paired_bus_generator_PQ_difference_MVA=max([pairs(both).maximum_bus_generation_PQ_difference_MVA]);
report.maximum_paired_DC_PQ_difference_MVA=max([pairs(both).maximum_DC_PQ_difference_MVA]);
report.paired_detailed_cohort_is_frozen_and_not_selected_by_compact_success=true;
report.passed=attempted==8651&&exception_count==0&&all([pairs(qualified).solution_equivalent]);
fid=fopen(fullfile(out,'annual_compact_PF_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
progress.completed=true;progress.months_complete=12;progress.elapsed_seconds=report.elapsed_seconds;
progress.final_receipt='annual_compact_PF_receipt.json';
fid=fopen(fullfile(out,'annual_progress.json'),'w');fprintf(fid,'%s\n',jsonencode(progress,'PrettyPrint',true));fclose(fid);
fprintf('COMPACT_YEAR_COMPLETE attempted%d converged%d equations%d profiles%d VQ%d seconds%.1f\n',attempted,report.PF_converged_hours,report.AC_equation_qualified_hours,report.P_profile_preserved_hours,report.VQ_and_generator_assumption_qualified_hours,report.elapsed_seconds);
end

function a=compare_saved_pair(old,chunk,j,h,ib,il)
detailed=old.AC_equation_gate(j)&&old.P_profile_preservation_gate(j);
compact=chunk.AC_equation_gate(j)&&chunk.P_profile_preservation_gate(j)&&chunk.reduction_and_equation_gate(j);
a=struct('hour_index',h,'detailed_baseline_qualified',detailed,'compact_equation_qualified',compact, ...
    'maximum_voltage_difference_pu',NaN,'maximum_branch_PQ_difference_MVA',NaN, ...
    'maximum_current_difference_A',NaN,'maximum_bus_generation_PQ_difference_MVA',NaN, ...
    'maximum_DC_PQ_difference_MVA',NaN,'input_load_PQ_exact',false,'same_presence_and_activity',false,'solution_equivalent',false);
if ~(detailed&&compact),return;end
vo=old.VM(j,ib).*exp(1j*deg2rad(old.VA(j,ib)));vn=chunk.VM(j,ib).*exp(1j*deg2rad(chunk.VA(j,ib)));
a.maximum_voltage_difference_pu=max(abs(vo-vn));
a.maximum_branch_PQ_difference_MVA=max(abs([old.PF(j,il)-chunk.PF(j,il),old.QF(j,il)-chunk.QF(j,il),old.PT(j,il)-chunk.PT(j,il),old.QT(j,il)-chunk.QT(j,il)]));
a.maximum_current_difference_A=max(abs([old.Iseries(j,il)-chunk.Iseries(j,il),old.Ifrom(j,il)-chunk.Ifrom(j,il),old.Ito(j,il)-chunk.Ito(j,il)]));
a.maximum_bus_generation_PQ_difference_MVA=max(abs([old.bus_PG(j,ib)-chunk.bus_PG(j,ib),old.bus_QG(j,ib)-chunk.bus_QG(j,ib)]));
a.maximum_DC_PQ_difference_MVA=max(abs([old.DC_PF(j,:)-chunk.DC_PF(j,:),old.DC_PT(j,:)-chunk.DC_PT(j,:),old.DC_QF(j,:)-chunk.DC_QF(j,:),old.DC_QT(j,:)-chunk.DC_QT(j,:)]));
a.input_load_PQ_exact=isequal(old.PD(j,ib),chunk.PD(j,ib))&&isequal(old.QD(j,ib),chunk.QD(j,ib));
a.same_presence_and_activity=isequal(old.bus_present(j,:),chunk.bus_present(j,:))&&isequal(old.branch_present(j,:),chunk.branch_present(j,:))&&isequal(old.branch_active(j,:),chunk.branch_active(j,:));
a.solution_equivalent=a.input_load_PQ_exact&&a.same_presence_and_activity&&a.maximum_voltage_difference_pu<1e-7 ...
    &&a.maximum_branch_PQ_difference_MVA<1e-4&&a.maximum_current_difference_A<1e-3 ...
    &&a.maximum_bus_generation_PQ_difference_MVA<1e-4&&a.maximum_DC_PQ_difference_MVA<1e-4;
end
