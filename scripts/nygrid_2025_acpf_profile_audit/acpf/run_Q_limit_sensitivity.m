function report=run_Q_limit_sensitivity()
% Standard PV-to-PQ switching diagnostic on the same seven supplied profiles.
% No OPF, dispatch optimization, model-parameter or capability change.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'System Matpower Format'));
out=fullfile(root,'output','nygrid_2025_acpf_profile_audit','acpf','Q_limit_sensitivity');if ~isfolder(out),mkdir(out);end
hours=[2630 4194 523 4000 8508 8471 8472];checks=struct([]);
for h=hours
    m=npcc_nygrid_2025_ac(h);errors=struct([]);solved=false;
    a=struct('hour_index',h,'diagnostic_variant','standard_PV_to_PQ_with_Q_limits', ...
        'completed_without_solver_exception',false,'PF_converged',false,'iterations',NaN, ...
        'Q_limit_mode',1,'fallback_mode2_due_implementation_error',false,'seconds',NaN, ...
        'AC_equation_gate',false,'load_PQ_preserved',false,'original_one_slack_P_profile_gate',false, ...
        'normal_voltage_gate',false,'generator_P_bound_gate',false,'generator_Q_bound_gate',false, ...
        'generator_S_proxy_gate',false,'six_DC_P_preserved',false,'six_DC_Q_contract_gate',false, ...
        'reference_bus_changed',false,'initial_reference_bus',m.bus(m.bus(:,2)==3,1), ...
        'final_reference_bus',NaN,'PV_to_PQ_bus_count',NaN,'PG_changed_generator_count',NaN, ...
        'VM_min',NaN,'VM_max',NaN,'buses_outside_0p90_to_1p10',NaN,'max_PG_bound_violation_MW',NaN, ...
        'max_QG_bound_violation_MVAr',NaN,'max_DC_Q_bound_violation_MVAr',NaN, ...
        'max_non_original_slack_PG_change_MW',NaN,'total_PG_change_MW',NaN,'AC_losses_MW',NaN, ...
        'OPF_used',false,'profiles_or_limits_modified_before_run',false,'physical_infeasibility_proved',false, ...
        'failure_explanation','');
    t=tic;
    for mode=[1 2]
        opt=mpoption('model','AC','verbose',0,'out.all',0,'pf.alg','NR','pf.nr.max_it',50, ...
            'pf.tol',1e-10,'pf.enforce_q_lims',mode,'exp.use_legacy_core',1);
        try
            [r,ok]=runpf(m,opt);solved=true;a.Q_limit_mode=mode;a.completed_without_solver_exception=true;
            a.fallback_mode2_due_implementation_error=mode==2;break;
        catch err
            errors=[errors struct('Q_limit_mode',mode,'identifier',err.identifier,'message',err.message,'report',getReport(err,'extended'))]; %#ok<AGROW>
        end
    end
    a.seconds=toc(t);
    if solved
        [audit,detail]=audit_profile_pf(m,r);
        a.PF_converged=logical(ok);a.iterations=r.iterations;a.AC_equation_gate=audit.AC_equation_gate;
        a.load_PQ_preserved=audit.load_PQ_exactly_preserved;a.original_one_slack_P_profile_gate=audit.P_profile_preservation_gate;
        a.normal_voltage_gate=audit.normal_voltage_gate;a.generator_P_bound_gate=audit.generator_active_bound_gate;
        a.generator_Q_bound_gate=audit.generator_reactive_bound_gate;a.generator_S_proxy_gate=audit.generator_S_proxy_gate;
        a.six_DC_P_preserved=audit.maximum_six_transfer_P_change_MW<1e-7;a.six_DC_Q_contract_gate=audit.six_transfer_reactive_contract_gate;
        ref=r.bus(r.bus(:,2)==3,1);if isscalar(ref),a.final_reference_bus=ref;end
        a.reference_bus_changed=~isequal(ref,a.initial_reference_bus);
        a.PV_to_PQ_bus_count=nnz(m.bus(:,2)~=1&r.bus(:,2)==1);
        changed=find(abs(r.gen(:,2)-m.gen(:,2))>1e-7);
        a.PG_changed_generator_count=numel(changed);a.total_PG_change_MW=sum(r.gen(:,2)-m.gen(:,2));
        a.max_non_original_slack_PG_change_MW=audit.maximum_non_slack_PG_change_MW;
        a.VM_min=audit.min_voltage_pu;a.VM_max=audit.max_voltage_pu;a.buses_outside_0p90_to_1p10=audit.number_of_buses_outside_0p90_to_1p10;
        a.max_PG_bound_violation_MW=audit.max_P_bound_violation_mw;a.max_QG_bound_violation_MVAr=audit.max_Q_bound_violation_mvar;
        a.max_DC_Q_bound_violation_MVAr=audit.max_transfer_Q_bound_violation_mvar;a.AC_losses_MW=audit.AC_real_losses_mw;
        PG_changes=table(changed,m.gen(changed,1),m.gen(changed,2),r.gen(changed,2),r.gen(changed,2)-m.gen(changed,2), ...
            'VariableNames',{'generator_row','bus_id','profile_PG_MW','solved_PG_MW','change_MW'});
        writetable(PG_changes,fullfile(out,sprintf('h%04d_PG_changes.csv',h)));
        if ~ok
            a.failure_explanation='Standard Q-limit PF did not converge or exhausted reactive-control feasibility; this is not a global infeasibility proof.';
        elseif a.reference_bus_changed
            a.failure_explanation='The standard Q-limit algorithm reassigned the reference bus; PG changes at former/new slack generators are reported separately from the original single-slack profile contract.';
        end
        save(fullfile(out,sprintf('h%04d.mat',h)),'m','r','opt','a','audit','detail','PG_changes','errors');
    else
        a.failure_explanation='Both simultaneous and one-at-a-time Q-limit modes raised implementation exceptions. No numerical or physical feasibility conclusion is drawn.';
        save(fullfile(out,sprintf('h%04d_solver_exception.mat',h)),'m','errors','a');
    end
    a.errors=errors;checks=[checks a]; %#ok<AGROW>
    fid=fopen(fullfile(out,sprintf('h%04d.json',h)),'w');fprintf(fid,'%s\n',jsonencode(a,'PrettyPrint',true));fclose(fid);
    fprintf('Q_LIMIT_PROFILE h%d mode%d returned%d PF%d eq%d refchange%d PGchanged%.0f VM[%.4g,%.4g] Qviol%.4g DCQviol%.4g %s\n', ...
        h,a.Q_limit_mode,a.completed_without_solver_exception,a.PF_converged,a.AC_equation_gate,a.reference_bus_changed, ...
        a.PG_changed_generator_count,a.VM_min,a.VM_max,a.max_QG_bound_violation_MVAr,a.max_DC_Q_bound_violation_MVAr,a.failure_explanation);
end
report=struct('completed',true,'diagnostic_only',true,'same_seven_profiles',hours,'OPF_used',false, ...
    'generation_profiles_or_capability_parameters_modified_before_solve',false, ...
    'reference_reassignment_is_standard_solver_behavior_not_manual_redispatch',true, ...
    'primary_annual_unlimited_PV_results_replaced',false,'checks',checks);
fid=fopen(fullfile(out,'Q_limit_sensitivity_receipt.json'),'w');fprintf(fid,'%s\n',jsonencode(report,'PrettyPrint',true));fclose(fid);
end
