function report=run_representative_profiles()
% Fresh PF from the current generation/load profiles, never an OPF replay.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
out=fullfile(root,'output','nygrid_2025_acpf_profile_audit','acpf');if ~isfolder(out),mkdir(out);end
hours=[2630 4194 523 4000 8508 8471 8472];checks=struct([]);
opt=mpoption('model','AC','verbose',0,'out.all',0,'pf.alg','NR','pf.nr.max_it',50, ...
    'pf.tol',1e-10,'pf.enforce_q_lims',0,'exp.use_legacy_core',1);
t=tic;canonical=npcc_nygrid_2025_ac(8508);canonical_time=toc(t);
bus_id=canonical.bus(:,1);branch_keys=canonical.userdata.ac_system.branch_keys(:);
branch_parent_row=canonical.userdata.ac_system.branch_parent_row;
branch_from_bus=canonical.branch(:,1);branch_to_bus=canonical.branch(:,2);base_kv=canonical.bus(:,10);
nh=numel(hours);nb=numel(bus_id);nl=numel(branch_keys);
VM=nan(nh,nb);VA=VM;PD=VM;QD=VM;bus_PG=VM;bus_QG=VM;
PF=nan(nh,nl);QF=PF;PT=PF;QT=PF;Iseries=PF;Ifrom=PF;Ito=PF;
branch_present=false(nh,nl);branch_active=branch_present;bus_present=false(nh,nb);
timestamp_utc=cell(nh,1);gamma=canonical.userdata.ac_system.gamma;
for k=1:nh
    h=hours(k);t=tic;
    if h==8508,m=canonical;build_seconds=canonical_time;else,m=npcc_nygrid_2025_ac(h);build_seconds=toc(t);end
    assert(m.userdata.ac_system.gamma==gamma);
    t=tic;[r,success]=runpf(m,opt);pf_seconds=toc(t);
    [audit,detail]=audit_profile_pf(m,r);audit.build_seconds=build_seconds;audit.PF_seconds=pf_seconds;
    timestamp_utc{k}=audit.timestamp_utc;
    [ok,ib]=ismember(m.bus(:,1),bus_id);assert(all(ok));
    [ok,il]=ismember(string(m.userdata.ac_system.branch_keys),string(branch_keys));assert(all(ok));
    VM(k,ib)=r.bus(:,8);VA(k,ib)=r.bus(:,9);PD(k,ib)=m.bus(:,3);QD(k,ib)=m.bus(:,4);bus_present(k,ib)=true;
    [ok,gb]=ismember(r.gen(:,1),bus_id);assert(all(ok));
    bus_PG(k,:)=accumarray(gb,r.gen(:,2),[nb 1])';bus_QG(k,:)=accumarray(gb,r.gen(:,3),[nb 1])';
    PF(k,il)=r.branch(:,14);QF(k,il)=r.branch(:,15);PT(k,il)=r.branch(:,16);QT(k,il)=r.branch(:,17);
    Iseries(k,il)=detail.series_current_amp;Ifrom(k,il)=detail.from_terminal_current_amp;Ito(k,il)=detail.to_terminal_current_amp;
    branch_present(k,il)=true;branch_active(k,il)=m.branch(:,11)>0;
    save(fullfile(out,sprintf('representative_h%04d.mat',h)),'m','r','opt','audit','detail');
    fid=fopen(fullfile(out,sprintf('representative_h%04d.json',h)),'w');fprintf(fid,'%s\n',jsonencode(audit,'PrettyPrint',true));fclose(fid);
    checks=[checks audit]; %#ok<AGROW>
    fprintf('PROFILE_PF h%d converged%d eq%d Ppreserve%d VQ%d it%d build%.3fs PF%.3fs slack%.3fMW VM[%.4f,%.4f] DCQviol%.3fMVAr\n', ...
        h,success,audit.AC_equation_gate,audit.P_profile_preservation_gate,audit.VQ_and_generator_assumption_gate, ...
        r.iterations,build_seconds,pf_seconds,audit.reference_PG_change_MW,audit.min_voltage_pu,audit.max_voltage_pu,audit.max_transfer_Q_bound_violation_mvar);
end
hour_index=hours(:);source_qualified=true(nh,1);PF_converged=[checks.PF_converged]';
AC_equation_gate=[checks.AC_equation_gate]';P_profile_preservation_gate=[checks.P_profile_preservation_gate]';
VQ_and_generator_assumption_gate=[checks.VQ_and_generator_assumption_gate]';
save(fullfile(out,'representative_state_arrays.mat'),'hour_index','timestamp_utc','gamma','source_qualified', ...
    'PF_converged','AC_equation_gate','P_profile_preservation_gate','VQ_and_generator_assumption_gate', ...
    'bus_id','branch_keys','branch_parent_row','branch_from_bus','branch_to_bus','base_kv','VM','VA','PD','QD','bus_PG','bus_QG', ...
    'PF','QF','PT','QT','Iseries','Ifrom','Ito','branch_present','branch_active','bus_present');
report=struct('completed',true,'generation_load_profiles_used_directly',true,'OPF_used',false, ...
    'selected_hour_count',nh,'selected_hours',hours,'converged_hours',sum(PF_converged), ...
    'AC_equation_qualified_hours',sum(AC_equation_gate),'P_profile_preserved_hours',sum(P_profile_preservation_gate), ...
    'VQ_and_generator_assumption_qualified_hours',sum(VQ_and_generator_assumption_gate), ...
    'current_computability_distinct_from_operating_constraints',true,'overload_not_used_as_convergence_gate',true, ...
    'median_loader_seconds',median([checks.build_seconds]),'median_PF_seconds',median([checks.PF_seconds]), ...
    'annual_projection_naive_seconds',8651*median([checks.build_seconds]+[checks.PF_seconds]),'checks',checks);
writetable(struct2table(checks),fullfile(out,'representative_hour_quality.csv'));
fid=fopen(fullfile(out,'representative_profile_PF_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
end
