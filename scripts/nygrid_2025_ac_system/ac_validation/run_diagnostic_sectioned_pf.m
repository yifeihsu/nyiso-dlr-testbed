function report=run_diagnostic_sectioned_pf()
% Computational ACPF diagnostic on the unchanged sectioned synthetic model.
% The NR solve does not enforce generator limits; audit every limit afterward.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
out=fullfile(root,'output','nygrid_2025_ac_system','ac_validation','diagnostic_unbounded_slack_PF');
if ~isfolder(out),mkdir(out);end
checks=struct([]);plan_sha='';overlay_sha='';
opt=mpoption('model','AC','verbose',1,'out.all',0,'pf.alg','NR', ...
    'pf.nr.max_it',50,'pf.tol',1e-10,'pf.enforce_q_lims',0);
for h=[2630 4000 8508]
    m=npcc_nygrid_2025_ac(h);
    u=m.userdata.ac_system;
    if isempty(plan_sha),plan_sha=u.sectioned_design_plan_sha256;overlay_sha=u.branch_parameter_overlay_sha256;end
    assert(strcmp(plan_sha,u.sectioned_design_plan_sha256)&&strcmp(overlay_sha,u.branch_parameter_overlay_sha256));
    t=tic;[r,success]=runpf(m,opt);elapsed=toc(t);
    [a,detail]=audit_ac_solution(m,r);
    a.hour_index=h;a.timestamp_utc=char(u.timestamp_utc);a.seconds=elapsed;
    a.case_label='diagnostic_unbounded_slack_PF';a.PF_Q_limit_enforcement=0;
    a.buses=size(m.bus,1);a.branches=size(m.branch,1);
    a.bound_constrained_dispatch_claimed=false;a.original_input_dispatch_changed_before_solve=false;
    a.sectioned_design_plan_sha256=plan_sha;a.branch_parameter_overlay_sha256=overlay_sha;
    save(fullfile(out,sprintf('hour_%04d.mat',h)),'m','r','opt','a','detail');
    fid=fopen(fullfile(out,sprintf('hour_%04d.json',h)),'w');fprintf(fid,'%s\n',jsonencode(a,'PrettyPrint',true));fclose(fid);
    checks=[checks a]; %#ok<AGROW>
    fprintf('DIAGNOSTIC_SECTIONED_PF h%d success%d audit%d VM[%.5f,%.5f] Pviol%.4g Qviol%.4g DCQviol%.4g hardwareI%.4g cableI%.4g\n', ...
        h,success,a.passed,a.min_voltage_pu,a.max_voltage_pu,a.max_P_bound_violation_mw, ...
        a.max_Q_bound_violation_mvar,a.max_transfer_Q_bound_violation_mvar, ...
        a.maximum_hardware_terminal_current_fraction,a.maximum_cable_section_static_current_fraction);
end
report=struct('complete',true,'diagnostic_only',true,'all_PF_solves_converged',all([checks.solver_success]), ...
    'all_limits_respected',all([checks.passed]),'bound_constrained_dispatch_claimed',false, ...
    'pf_enforce_q_lims',0,'all_generator_and_six_transfer_Q_limits_audited_after_solve',true, ...
    'lossless_DC_dispatch_is_used_as_initial_P_input',true,'free_reference_slack_adjustment_allowed_in_diagnostic',true, ...
    'sectioned_design_plan_sha256',plan_sha,'branch_parameter_overlay_sha256',overlay_sha,'checks',checks);
fid=fopen(fullfile(out,'diagnostic_PF_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
end
