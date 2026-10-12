function report=run_annual_profiles()
% All8651 qualified profiles, independently initialized, no OPF or fitting.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
out=fullfile(root,'output','nygrid_2025_acpf_profile_audit','acpf');monthly=fullfile(out,'monthly');
if ~isfolder(monthly),mkdir(monthly);end
proof=jsondecode(fileread(fullfile(out,'cache_parity_and_benchmark.json')));assert(proof.passed);
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
all_audits=cell(8760,1);files=struct([]);attempted=0;converged_count=0;exception_count=0;
ib=cell(4,1);il=cell(4,1);ig=cell(4,1);
for s=1:4
    [ok,ib{s}]=ismember(cache.templates{s}.bus(:,1),bus_id);assert(all(ok));
    [ok,il{s}]=ismember(string(cache.templates{s}.userdata.ac_system.branch_keys),string(branch_keys));assert(all(ok));
    [ok,ig{s}]=ismember(cache.templates{s}.gen(:,1),bus_id);assert(all(ok));
end
for mon=1:12
    month_start=tic;hh=find(model_month==mon);nh=numel(hh);nb=numel(bus_id);nl=numel(branch_keys);
    chunk=struct('hour_index',hh,'timestamp_utc',{timestamp_utc(hh)},'gamma',gamma, ...
        'source_qualified',cache.qualified(hh),'bus_id',bus_id,'base_kv',base_kv,'branch_keys',{branch_keys}, ...
        'branch_parent_row',branch_parent_row,'branch_from_bus',branch_from_bus,'branch_to_bus',branch_to_bus, ...
        'DC_from_bus',DC_from_bus,'DC_to_bus',DC_to_bus,'topology_state_index',cache.state_index(hh));
    for name={'VM','VA','PD','QD','bus_PG','bus_QG'},chunk.(name{1})=nan(nh,nb);end
    for name={'PF','QF','PT','QT','Iseries','Ifrom','Ito'},chunk.(name{1})=nan(nh,nl);end
    for name={'DC_PF','DC_PT','DC_QF','DC_QT'},chunk.(name{1})=nan(nh,6);end
    chunk.Dover_model_SHIFT_deg=nan(nh,2);
    chunk.bus_present=false(nh,nb);chunk.branch_present=false(nh,nl);chunk.branch_active=false(nh,nl);
    for name={'PF_attempted','PF_converged','AC_equation_gate','P_profile_preservation_gate','VQ_and_generator_assumption_gate','computed_current_available','solver_exception'}
        chunk.(name{1})=false(nh,1);
    end
    for j=1:nh
        h=hh(j);if ~cache.qualified(h),continue;end
        m=profile_case_from_cache(cache,h);s=cache.state_index(h);attempted=attempted+1;chunk.PF_attempted(j)=true;
        try
            t=tic;[r,~]=runpf(m,opt);pf_seconds=toc(t);[audit,detail]=audit_profile_pf(m,r);audit.PF_seconds=pf_seconds;
        catch err
            exception_count=exception_count+1;chunk.solver_exception(j)=true;
            error_text=getReport(err,'extended');save(fullfile(out,sprintf('solver_exception_h%04d.mat',h)),'m','opt','error_text');
            fprintf('PROFILE_YEAR exception hour%d %s\n',h,err.identifier);continue;
        end
        all_audits{h}=audit;converged_count=converged_count+audit.PF_converged;
        for name={'PF_converged','AC_equation_gate','P_profile_preservation_gate','VQ_and_generator_assumption_gate','computed_current_available'}
            chunk.(name{1})(j)=audit.(name{1});
        end
        chunk.VM(j,ib{s})=r.bus(:,8);chunk.VA(j,ib{s})=r.bus(:,9);
        chunk.PD(j,ib{s})=m.bus(:,3);chunk.QD(j,ib{s})=m.bus(:,4);chunk.bus_present(j,ib{s})=true;
        chunk.bus_PG(j,:)=accumarray(ig{s},r.gen(:,2),[nb 1])';chunk.bus_QG(j,:)=accumarray(ig{s},r.gen(:,3),[nb 1])';
        chunk.PF(j,il{s})=r.branch(:,14);chunk.QF(j,il{s})=r.branch(:,15);chunk.PT(j,il{s})=r.branch(:,16);chunk.QT(j,il{s})=r.branch(:,17);
        chunk.Iseries(j,il{s})=detail.series_current_amp;chunk.Ifrom(j,il{s})=detail.from_terminal_current_amp;chunk.Ito(j,il{s})=detail.to_terminal_current_amp;
        chunk.branch_present(j,il{s})=true;chunk.branch_active(j,il{s})=m.branch(:,11)>0;
        chunk.DC_PF(j,:)=r.dcline(:,4);chunk.DC_PT(j,:)=r.dcline(:,5);chunk.DC_QF(j,:)=r.dcline(:,6);chunk.DC_QT(j,:)=r.dcline(:,7);
        if cache.dover.post_full_service(h),chunk.Dover_model_SHIFT_deg(j,:)=m.branch(411:412,10);end
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
    fprintf('PROFILE_YEAR month%02d q%d PF%d eq%d Pprofile%d VQ%d %.1fs file%.1fMB total%.1fs\n',mon,f.source_qualified,f.converged,f.equation_gate,f.profile_gate,f.VQ_assumption_gate,f.seconds,info.bytes/1e6,toc(all_start));
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
    'pf_enforce_q_lims',0,'backend','MATPOWER_legacy_NR','overload_not_used_as_convergence_gate',true, ...
    'global_infeasibility_from_failed_NR_claimed',false,'failed_outputs_retained_with_flags',true, ...
    'normal_voltage_range_pu',[.95 1.05],'broad_voltage_diagnostic_range_pu',[.9 1.1]);
fid=fopen(fullfile(out,'annual_profile_PF_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
progress.completed=true;progress.months_complete=12;progress.elapsed_seconds=report.elapsed_seconds;
progress.final_receipt='annual_profile_PF_receipt.json';
fid=fopen(fullfile(out,'annual_progress.json'),'w');fprintf(fid,'%s\n',jsonencode(progress,'PrettyPrint',true));fclose(fid);
fprintf('PROFILE_YEAR_COMPLETE attempted%d converged%d equations%d profiles%d VQ%d seconds%.1f\n',attempted,report.PF_converged_hours,report.AC_equation_qualified_hours,report.P_profile_preserved_hours,report.VQ_and_generator_assumption_qualified_hours,report.elapsed_seconds);
end
