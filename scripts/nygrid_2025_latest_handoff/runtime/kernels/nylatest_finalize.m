function [result,audit,r,allocation]=nylatest_finalize(base,m,r,p,c,options,complete,status,trace,actual_budget,budget_detail,applied,NR_iterations,elapsed)
%AC_LOSS_FINALIZE Independent final electrical, accounting and recovery checks.
[a,detail]=nylatest_audit_ac_solution(m,r);
V=r.bus(:,8).*exp(1j*deg2rad(r.bus(:,9)));Vk=V(c.retained_full_rows);
currents=[abs(c.YfL*Vk).*c.from_current_base_A,abs(c.YtL*Vk).*c.to_current_base_A,abs(c.YseriesL*Vk).*c.to_current_base_A];
current_error=max(abs(currents-[detail.from_terminal_current_amp detail.to_terminal_current_amp detail.series_current_amp]),[],'all');
imports=zeros(3,1);
for k=1:numel(p.parent_from)
    gf=p.parent_from(k);gt=p.parent_to(k);
    if gf<=11&&gt>11,imports(gt-11)=imports(gt-11)-r.branch(p.from_runtime(k),14);
    elseif gt<=11&&gf>11,imports(gf-11)=imports(gf-11)-r.branch(p.to_runtime(k),16);end
end
for k=1:size(r.dcline,1),imports(p.DC_external_group(k)-11)=imports(p.DC_external_group(k)-11)+r.dcline(k,5);end
native_change=max(abs(r.gen(p.native,2)-p.baseline_PG(p.native)));
NY_served=zeros(11,1);NY_Q=zeros(11,1);
for g=1:11,use=p.bus_group==g;NY_served(g)=sum(m.bus(use,3));NY_Q(g)=sum(m.bus(use,4));end
budget_residual=max(abs(actual_budget-applied.applied_budget_MW));
load_closure=max(abs(NY_served+actual_budget(1:11)-p.group_gross_PD(1:11)));
external_delta=zeros(3,1);
for g=12:14,use=p.external_gen_group==g;external_delta(g-11)=sum(r.gen(use,2)-p.baseline_PG(use));end
equations=logical(r.success)&&a.finite&&a.max_nodal_P_residual_mw<1e-5&&a.max_nodal_Q_residual_mvar<1e-5;
policy_gate=complete&&strcmp(options.loss_mode,'boundary_consistent')&&equations ...
    &&budget_residual<1e-6&&native_change<1e-7&&abs(r.gen(p.HQ,2)-p.baseline_PG(p.HQ))<1e-8 ...
    &&max(abs(imports-p.target_NY_import))<1e-5&&load_closure<1e-5 ...
    &&max(abs(external_delta-actual_budget(12:14)))<1e-5&&all(NY_served>=0) ...
    &&a.max_P_bound_violation_mw<1e-5&&a.max_fixed_transfer_P_change_mw<1e-8;
audit=a;audit.hour_index=base.userdata.ac_system.hour_index;audit.timestamp_utc=char(base.userdata.ac_system.timestamp_utc);
audit.PF_converged=logical(r.success);audit.AC_equation_gate=equations;audit.loss_allocation_gate=policy_gate;
audit.loss_iteration_converged=complete;audit.loss_status=status;audit.loss_iterations=numel(trace);
audit.total_NR_iterations=NR_iterations;audit.elapsed_seconds=elapsed;audit.backend=options.backend;
audit.no_full_network_Newton_used=strcmp(options.backend,'compact');audit.compact_retained_bus_count=148;
audit.recovery_voltage_error_pu=max(abs(V-c.voltage_lift*Vk));audit.recovered_current_error_A=current_error;
audit.reduction_and_equation_gate=equations&&audit.recovery_voltage_error_pu<1e-8&&current_error<1e-5;
audit.native_PG_change_from_original_MW=native_change;
audit.reference_PG_change_from_original_MW=r.gen(p.reference,2)-p.baseline_PG(p.reference);
audit.regional_NY_import_residual_MW=max(abs(imports-p.target_NY_import));
audit.NY_gross_load_accounting_residual_MW=load_closure;audit.loss_budget_residual_MW=budget_residual;
audit.maximum_NY_zonal_loss_fraction=max(actual_budget(1:11)./p.group_gross_PD(1:11));
audit.minimum_NY_served_PD_MW=min(NY_served);
audit.VQ_and_generator_assumption_gate=policy_gate&&a.max_voltage_bound_violation_pu<1e-7 ...
    &&a.max_Q_bound_violation_mvar<1e-5&&a.max_assumed_generator_S_bound_violation_mva<1e-5&&a.max_transfer_Q_bound_violation_mvar<1e-5;
audit.passed=policy_gate&&audit.reduction_and_equation_gate&&audit.VQ_and_generator_assumption_gate&&a.passed;
audit.impedance_mode=base.userdata.ac_loss_revision.impedance_mode;
audit.parent224_physical_impedance_validated=false;audit.OPF_used=false;
audit.P58_boundary_demand_equals_delivered_PD_plus_allocated_losses=true;
audit.loss_ownership_is_declared_not_observed_NYISO_meter_assignment=true;
audit.source_internal_interface_observations_used=false;
allocation=struct('policy',p.policy,'options',options,'status',status,'trace',trace,'group_labels',{p.labels}, ...
    'baseline_PG',p.baseline_PG,'baseline_gross_PD',p.gross_PD,'baseline_QD',p.gross_QD, ...
    'final_input',m,'policy_contract',p,'applied',applied,'actual_budget_MW',actual_budget, ...
    'budget_detail',budget_detail,'NY_gross_target_MW',p.group_gross_PD(1:11),'NY_served_PD_MW',NY_served,'NY_served_QD_MVAr',NY_Q, ...
    'regional_import_target_MW',p.target_NY_import,'regional_import_solved_MW',imports,'external_PG_increment_MW',external_delta);
result=struct('model_kind','compact_AC_with_boundary_loss_accounting','bus',r.bus(c.retained_full_rows,:), ...
    'gen',r.gen,'dcline',r.dcline,'success',policy_gate, ...
    'PF_success',logical(r.success),'retained_bus_ids',c.retained_bus_ids,'baseMVA',m.baseMVA, ...
    'recovered_full_voltage',V,'recovered_line_current_A',currents, ...
    'line_current_columns',{{'from_terminal_A','to_terminal_A','series_A'}},'audit',audit);
r.userdata.ac_loss_allocation=struct('policy',p.policy,'loss_mode',options.loss_mode,'status',status,'audit',audit);
end
