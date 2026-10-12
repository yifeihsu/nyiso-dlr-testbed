function [a,detail] = audit_ac_solution(m,r)
% Independent complex branch-law/KCL audit, without makeYbus or solver Jacobian.
assert(isequal(m.bus(:,1),r.bus(:,1))&&isequal(m.gen(:,1),r.gen(:,1)));
assert(isequal(m.branch(:,1:13),r.branch(:,1:13)));
nb=size(m.bus,1);nl=size(m.branch,1);ng=size(m.gen,1);base=m.baseMVA;
V=r.bus(:,8).*exp(1j*deg2rad(r.bus(:,9)));
[ok,f]=ismember(m.branch(:,1),m.bus(:,1));assert(all(ok));
[ok,t]=ismember(m.branch(:,2),m.bus(:,1));assert(all(ok));
[ok,gb]=ismember(m.gen(:,1),m.bus(:,1));assert(all(ok));
active=m.branch(:,11)>0;tap=m.branch(:,9);tap(tap==0)=1;
tap=tap.*exp(1j*deg2rad(m.branch(:,10)));
Y=zeros(nl,1);Y(active)=1./complex(m.branch(active,3),m.branch(active,4));
bc=1j*m.branch(:,5)/2;bc(~active)=0;
Is=Y.*(V(f)./tap-V(t));
If=Is./conj(tap)+bc.*V(f)./abs(tap).^2;
It=-Is+bc.*V(t);
Sf=base*V(f).*conj(If);St=base*V(t).*conj(It);
Cf=sparse((1:nl)',f,1,nl,nb);Ct=sparse((1:nl)',t,1,nl,nb);
Cg=sparse(gb,(1:ng)',double(m.gen(:,8)>0),nb,ng);
Sgen=Cg*complex(r.gen(:,2),r.gen(:,3));
Sload=complex(m.bus(:,3),m.bus(:,4));
Sshunt=abs(V).^2.*complex(m.bus(:,5),-m.bus(:,6));
Sdc=zeros(nb,1);dc=r.dcline;on=dc(:,3)>0;
for k=find(on)'
    fi=find(m.bus(:,1)==dc(k,1));ti=find(m.bus(:,1)==dc(k,2));
    % MATPOWER dcline QF/QT are positive VAR injections at both terminals.
    Sdc(fi)=Sdc(fi)+complex(-dc(k,4),dc(k,6));
    Sdc(ti)=Sdc(ti)+complex(dc(k,5),dc(k,7));
end
kcl=Sgen+Sdc-Sload-Sshunt-Cf'*Sf-Ct'*St;
br_saved=complex(r.branch(:,14),r.branch(:,15));
bt_saved=complex(r.branch(:,16),r.branch(:,17));
external=m.userdata.ac_system.external_generator_mask;native=~external;
pcap=m.userdata.ac_system.generator_assumed_s_cap;
rate=m.branch(:,6);rated=active&rate>0;
rate_violation=max([0;abs(Sf(rated))-rate(rated);abs(St(rated))-rate(rated)]);
dc_loss=dc(:,4)-dc(:,5);dc_expected=dc(:,16)+dc(:,17).*dc(:,4);
a=struct('solver_success',logical(r.success),'finite',all(isfinite([r.bus(:,8:9);r.gen(:,2:3)]),'all'), ...
    'max_branch_complex_flow_error_mva',max([abs(Sf-br_saved);abs(St-bt_saved)]), ...
    'max_nodal_P_residual_mw',max(abs(real(kcl))), ...
    'max_nodal_Q_residual_mvar',max(abs(imag(kcl))), ...
    'max_P_bound_violation_mw',max([0;m.gen(:,10)-r.gen(:,2);r.gen(:,2)-m.gen(:,9)]), ...
    'max_Q_bound_violation_mvar',max([0;m.gen(:,5)-r.gen(:,3);r.gen(:,3)-m.gen(:,4)]), ...
    'max_assumed_generator_S_bound_violation_mva',max([0;abs(complex(r.gen(:,2),r.gen(:,3)))-pcap]), ...
    'max_voltage_bound_violation_pu',max([0;m.bus(:,13)-r.bus(:,8);r.bus(:,8)-m.bus(:,12)]), ...
    'min_voltage_pu',min(abs(V)),'max_voltage_pu',max(abs(V)), ...
    'max_equipment_MVA_violation',rate_violation, ...
    'max_external_P_schedule_change_mw',max(abs(r.gen(external,2)-m.userdata.ac_system.generator_p_reference(external))), ...
    'max_fixed_transfer_P_change_mw',max(abs(dc(:,4)-m.dcline(:,4))), ...
    'max_transfer_loss_equation_residual_mw',max(abs(dc_loss-dc_expected)), ...
    'max_transfer_Q_bound_violation_mvar',max([0;dc(:,12)-dc(:,6);dc(:,6)-dc(:,13);dc(:,14)-dc(:,7);dc(:,7)-dc(:,15)]), ...
    'native_generation_increase_mw',sum(r.gen(native,2)-m.userdata.ac_system.generator_p_reference(native)), ...
    'native_generation_change_from_supplied_point_mw',sum(r.gen(native,2)-m.gen(native,2)), ...
    'AC_real_losses_mw',sum(real(Sf+St)), ...
    'DC_real_losses_mw',sum(dc_loss(on)), ...
    'max_series_loss_identity_error_mw',max(abs(real(Sf+St)-base*m.branch(:,3).*abs(Is).^2)), ...
    'global_P_balance_residual_mw',real(sum(kcl)), ...
    'gamma_division_applied_to_current',false,'thermal_conductor_limits_audited',false);
pass_fields={'max_branch_complex_flow_error_mva','max_nodal_P_residual_mw','max_nodal_Q_residual_mvar', ...
    'max_P_bound_violation_mw','max_Q_bound_violation_mvar','max_assumed_generator_S_bound_violation_mva', ...
    'max_equipment_MVA_violation','max_external_P_schedule_change_mw','max_fixed_transfer_P_change_mw', ...
    'max_transfer_loss_equation_residual_mw','max_transfer_Q_bound_violation_mvar','max_series_loss_identity_error_mw'};
a.passed=a.solver_success&&a.finite&&a.max_voltage_bound_violation_pu<1e-6;
for k=1:numel(pass_fields),a.passed=a.passed&&a.(pass_fields{k})<1e-4;end
from_amps=abs(If)*base*1000./(sqrt(3)*m.bus(f,10));
to_amps=abs(It)*base*1000./(sqrt(3)*m.bus(t,10));
series_amps=abs(Is)*base*1000./(sqrt(3)*m.bus(t,10));
a.OH_series_current_limits_audited=false;a.maximum_OH_series_current_fraction=0;
if isfield(m.userdata,'ac_dlr')
    thermal=m.userdata.ac_dlr;rr=thermal.branch_rows;
    assert(all(isfinite(thermal.series_phase_limit_a)&thermal.series_phase_limit_a>0));
    a.OH_series_current_limits_audited=true;
    a.maximum_OH_series_current_fraction=max([0;series_amps(rr)./thermal.series_phase_limit_a]);
    a.passed=a.passed&&a.maximum_OH_series_current_fraction<=1+1e-6;
end
a.hardware_terminal_current_limits_audited=false;
a.hardware_terminal_current_limit_count=0;a.maximum_hardware_terminal_current_fraction=0;
a.max_terminal_current_crosscheck_error_amp=0;
if isfield(m.userdata.ac_system,'terminal_current_limits')
    lim=m.userdata.ac_system.terminal_current_limits;rr=lim.branch_row;
    frac=known_end_fractions(from_amps(rr),to_amps(rr),lim);
    alternate=ac_terminal_current_audit(r,lim);
    discrepancy=max([0;abs(from_amps(rr)-alternate.table.actual_from_current_a);abs(to_amps(rr)-alternate.table.actual_to_current_a)]);
    a.hardware_terminal_current_limits_audited=true;
    a.hardware_terminal_current_limit_count=height(lim);
    a.maximum_hardware_terminal_current_fraction=max([0;frac]);
    a.max_terminal_current_crosscheck_error_amp=discrepancy;
    a.passed=a.passed&&a.maximum_hardware_terminal_current_fraction<=1+1e-6&&discrepancy<1e-5;
end
a.conductor_section_end_current_limits_audited=false;
a.maximum_conductor_section_end_current_fraction=0;
a.max_conductor_end_current_crosscheck_error_amp=0;
if isfield(m.userdata.ac_system,'conductor_section_end_current_limits')
    lim=m.userdata.ac_system.conductor_section_end_current_limits;rr=lim.branch_row;
    frac=known_end_fractions(from_amps(rr),to_amps(rr),lim);
    alternate=ac_terminal_current_audit(r,lim);
    discrepancy=max([0;abs(from_amps(rr)-alternate.table.actual_from_current_a);abs(to_amps(rr)-alternate.table.actual_to_current_a)]);
    a.conductor_section_end_current_limits_audited=true;
    a.maximum_conductor_section_end_current_fraction=max([0;frac]);
    a.max_conductor_end_current_crosscheck_error_amp=discrepancy;
    a.passed=a.passed&&a.maximum_conductor_section_end_current_fraction<=1+1e-6&&discrepancy<1e-5;
end
a.cable_section_static_current_limits_audited=false;
a.maximum_cable_section_static_current_fraction=0;
a.max_cable_section_current_crosscheck_error_amp=0;
if isfield(m.userdata.ac_system,'cable_section_static_current_limits')
    lim=m.userdata.ac_system.cable_section_static_current_limits;rr=lim.branch_row;
    frac=known_end_fractions(from_amps(rr),to_amps(rr),lim);
    alternate=ac_terminal_current_audit(r,lim);
    discrepancy=max([0;abs(from_amps(rr)-alternate.table.actual_from_current_a);abs(to_amps(rr)-alternate.table.actual_to_current_a)]);
    a.cable_section_static_current_limits_audited=true;
    a.maximum_cable_section_static_current_fraction=max([0;frac]);
    a.max_cable_section_current_crosscheck_error_amp=discrepancy;
    a.passed=a.passed&&a.maximum_cable_section_static_current_fraction<=1+1e-6&&discrepancy<1e-5;
end
detail=struct('bus_id',m.bus(:,1),'P_residual_mw',real(kcl),'Q_residual_mvar',imag(kcl), ...
    'branch_index',(1:nl)','from_power_mva',Sf,'to_power_mva',St, ...
    'series_current_pu',Is,'from_terminal_current_pu',If,'to_terminal_current_pu',It, ...
    'series_current_amp',series_amps, ...
    'from_terminal_current_amp',from_amps,'to_terminal_current_amp',to_amps);
end

function frac=known_end_fractions(from_amps,to_amps,lim)
ff=zeros(height(lim),1);tt=ff;
use=isfinite(lim.total_terminal_current_limit_from_a);
ff(use)=from_amps(use)./lim.total_terminal_current_limit_from_a(use);
use=isfinite(lim.total_terminal_current_limit_to_a);
tt(use)=to_amps(use)./lim.total_terminal_current_limit_to_a(use);
frac=max(ff,tt);
end
