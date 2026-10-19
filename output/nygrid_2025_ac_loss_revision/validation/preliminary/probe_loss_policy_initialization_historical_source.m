function report=probe_loss_policy_initialization()
% Limited source-only starting-state diagnostics for the failed4860 stress case.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
addpath(fullfile(root,'scripts','nygrid_2025_ac_loss_revision','core'));
addpath(fullfile(root,'scripts','nygrid_2025_compact_ac','core'));
addpath(fullfile(root,'scripts','nygrid_2025_centraleast_diagnosis','experiments'));
out=fullfile(root,'output','nygrid_2025_ac_loss_revision','validation','initialization_probes');if ~isfolder(out),mkdir(out);end
b=load(fullfile(fileparts(out),'pairs','initial_stress','h4860.mat'));
rows=struct([]);ws=warning;cleanup=onCleanup(@()warning(ws));warning('off','MATLAB:nearlySingularMatrix');warning('off','MATLAB:singularMatrix');
for damping=[1 .5]
    options=struct('impedance_mode','released_equivalent','loss_mode','boundary_consistent','backend','compact', ...
        'initialization','original_case','damping',damping);
    t=tic;[result,audit,full,allocation]=run_nygrid_2025_loss_consistent_acpf(b.base,options);seconds=toc(t);
    row=struct('strategy',sprintf('zero_budget_original_case_damping_%g',damping),'full_policy_run',true, ...
        'PF_success',audit.PF_converged,'policy_success',audit.loss_allocation_gate,'iterations',audit.loss_iterations, ...
        'status',audit.loss_status,'seconds',seconds,'P_KCL_MW',audit.max_nodal_P_residual_mw,'Q_KCL_MVAr',audit.max_nodal_Q_residual_mvar);
    rows=[rows row]; %#ok<AGROW>
    save(fullfile(out,sprintf('zero_budget_damping_%g_h4860.mat',damping)),'options','result','audit','full','allocation','row');
    fprintf('LOSS_INIT %s PF%d policy%d iterations%d %s\n',row.strategy,row.PF_success,row.policy_success,row.iterations,row.status);
end
% Compare only the first seeded-budget innerPF, changing its voltage guess.
% The applied loss budget and all physical input/control values are identical.
m=b.cl.final_input;c=compact_ac_build(m);opt=mpoption('model','AC','pf.alg','NR','pf.tol',1e-10,'pf.nr.max_it',50,'pf.enforce_q_lims',0,'exp.use_legacy_core',1,'verbose',0,'out.all',0);
adjusted_DC=rundcpf(m,mpoption(opt,'model','DC'));assert(adjusted_DC.success);
for strategy={'case_voltage_on_seed_budget','adjusted_DCPF_voltage_on_seed_budget'}
    if strcmp(strategy{1},'case_voltage_on_seed_budget'),V0=[];else,V0=adjusted_DC.bus(:,8).*exp(1j*deg2rad(adjusted_DC.bus(:,9)));end
    t=tic;[full,V,inner]=ac_loss_inner_pf(m,c,V0,opt);seconds=toc(t);a=audit_bridge_AC_solution(m,full);
    row=struct('strategy',strategy{1},'full_policy_run',false,'PF_success',inner.success,'policy_success',false, ...
        'iterations',inner.iterations,'status','inner_initialization_diagnostic_only','seconds',seconds,'P_KCL_MW',a.max_P_residual_MW,'Q_KCL_MVAr',a.max_Q_residual_MVAr);
    rows=[rows row]; %#ok<AGROW>
    save(fullfile(out,[strategy{1},'_h4860.mat']),'m','c','V0','full','V','inner','a','row');
    fprintf('LOSS_INIT %s PF%d NR%d PKCL%.3g QKCL%.3g\n',row.strategy,row.PF_success,row.iterations,row.P_KCL_MW,row.Q_KCL_MVAr);
end
report=struct('completed',true,'hour_index',4860,'rows',rows,'source_only_initializations',true, ...
    'model_parameters_bounds_profiles_and_loss_equations_unchanged',true,'OPF_or_internal_interface_observations_used',false, ...
    'inner_only_success_is_not_final_policy_success',true);
writetable(struct2table(rows),fullfile(out,'initialization_checks.csv'));
fid=fopen(fullfile(out,'initialization_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
end
