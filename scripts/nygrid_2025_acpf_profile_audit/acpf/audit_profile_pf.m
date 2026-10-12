function [audit,detail]=audit_profile_pf(m,r)
% Audit a profile-driven PF; convergence, V/Q assumptions and overloads differ.
root=fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(fullfile(root,'scripts','nygrid_2025_ac_system','ac_validation'));
[legacy,detail]=audit_ac_solution(m,r);
ref=m.bus(m.bus(:,2)==3,1);assert(isscalar(ref));
slack=find(m.gen(:,1)==ref&m.gen(:,8)>0,1,'first');assert(isscalar(slack));
other=true(size(m.gen,1),1);other(slack)=false;
delta=r.gen(:,2)-m.gen(:,2);
load_equal=isequal(m.bus(:,[1 3 4]),r.bus(:,[1 3 4]));
non_slack=max(abs(delta(other)));dcP=max(abs(r.dcline(:,4)-m.dcline(:,4)));
ac_loss=sum(r.branch(:,14)+r.branch(:,16));dc_loss=sum(r.dcline(:,4)-r.dcline(:,5));
expected_loss_adjustment=ac_loss+dc_loss+sum(m.bus(:,5).*r.bus(:,8).^2)+sum(m.bus(:,3))-sum(m.gen(:,2));
audit=legacy;
audit.hour_index=m.userdata.ac_system.hour_index;
audit.timestamp_utc=char(m.userdata.ac_system.timestamp_utc);
audit.PF_converged=logical(r.success);
audit.PF_iterations=r.iterations;
audit.PF_backend='MATPOWER_legacy_NR';audit.pf_enforce_q_lims=0;
audit.OPF_used=false;audit.operating_profiles_modified_before_PF=false;
audit.load_PQ_exactly_preserved=load_equal;
audit.reference_bus_id=ref;audit.reference_generator_row=slack;
audit.reference_PG_input_MW=m.gen(slack,2);audit.reference_PG_solved_MW=r.gen(slack,2);
audit.reference_PG_change_MW=delta(slack);
audit.reference_Pmin_MW=m.gen(slack,10);audit.reference_Pmax_MW=m.gen(slack,9);
audit.maximum_non_slack_PG_change_MW=non_slack;
audit.number_of_real_generators_with_PG_change_above1e_7=nnz(abs(delta)>1e-7);
audit.maximum_six_transfer_P_change_MW=dcP;
audit.slack_change_minus_required_loss_balance_MW=delta(slack)-expected_loss_adjustment;
audit.total_PD_MW=sum(m.bus(:,3));audit.total_QD_MVAr=sum(m.bus(:,4));
audit.number_of_buses_outside_0p95_to_1p05=nnz(r.bus(:,8)<.95-1e-7|r.bus(:,8)>1.05+1e-7);
audit.number_of_buses_outside_0p90_to_1p10=nnz(r.bus(:,8)<.9-1e-7|r.bus(:,8)>1.1+1e-7);
audit.AC_equation_gate=logical(r.success)&&legacy.finite ...
    &&legacy.max_nodal_P_residual_mw<1e-5&&legacy.max_nodal_Q_residual_mvar<1e-5;
audit.P_profile_preservation_gate=load_equal&&non_slack<1e-7&&dcP<1e-7 ...
    &&abs(audit.slack_change_minus_required_loss_balance_MW)<1e-5;
audit.normal_voltage_gate=legacy.max_voltage_bound_violation_pu<1e-7;
audit.generator_active_bound_gate=legacy.max_P_bound_violation_mw<1e-5;
audit.generator_reactive_bound_gate=legacy.max_Q_bound_violation_mvar<1e-5;
audit.generator_S_proxy_gate=legacy.max_assumed_generator_S_bound_violation_mva<1e-5;
audit.six_transfer_reactive_contract_gate=legacy.max_transfer_Q_bound_violation_mvar<1e-5;
audit.VQ_and_generator_assumption_gate=audit.AC_equation_gate&&audit.P_profile_preservation_gate ...
    &&audit.normal_voltage_gate&&audit.generator_active_bound_gate&&audit.generator_reactive_bound_gate ...
    &&audit.generator_S_proxy_gate&&audit.six_transfer_reactive_contract_gate;
audit.computed_current_available=audit.AC_equation_gate&&audit.P_profile_preservation_gate;
audit.overload_is_not_a_convergence_rejection=true;
audit.generator_Q_capabilities_are_engineering_assumptions_not_observed=true;
audit.slack_policy='Only the first online real generator at the existing reference bus balances AC losses; no redispatch elsewhere.';
audit.DC_Q_zero_contract_is_audited_not_enforced_by_standard_PV_converter_PF=true;
audit.branch_parameter_overlay_sha256=m.userdata.ac_system.branch_parameter_overlay_sha256;
audit.sectioned_design_plan_sha256=m.userdata.ac_system.sectioned_design_plan_sha256;
audit.generator_capability_policy_sha256=m.userdata.ac_system.generator_capability_policy_sha256;
end
