function report=test_ny_ac_reference_audit
%TEST_NY_AC_REFERENCE_AUDIT Limits and replay cannot be bypassed by artifacts.
define_constants;
m=runpf(loadcase('case9'),mpoption('verbose',0,'out.all',0));
a=audit_ny_ac_reference(m);assert(a.passed);
tests="bounded_case9_replay_accepted";
bad=m;bad.gen(1,QMAX)=Inf;
a=audit_ny_ac_reference(bad);
assert(~a.passed&&~a.summary.finite_ordered_generator_bounds&&a.generator.invalid_capability_bounds(1));
tests(end+1)="infinite_online_Q_bound_rejected";
bad=m;bad.gen(1,PMAX)=NaN;
a=audit_ny_ac_reference(bad);assert(~a.passed&&~a.summary.finite_ordered_generator_bounds);
tests(end+1)="NaN_online_P_bound_rejected";
bad=m;bad.bus(1,VMAX)=Inf;
a=audit_ny_ac_reference(bad);assert(~a.passed&&~a.summary.finite_ordered_voltage_bounds);
tests(end+1)="infinite_voltage_bound_rejected";
bad=m;bad.gen(1,PMIN)=bad.gen(1,PMAX)+1;
a=audit_ny_ac_reference(bad);assert(~a.passed&&a.generator.invalid_capability_bounds(1));
tests(end+1)="reversed_generator_bounds_rejected";
% Fabricated terminal powers cannot hide a real thermal overload. Keep the
% physical V/G state unchanged and corrupt only the saved branch evidence.
bad=m;bad.branch(1,RATE_A)=1;bad.branch(1,[PF QF PT QT])=0;
a=audit_ny_ac_reference(bad);
assert(~a.passed&&a.branch.from_overload_mva(1)>1&& ...
    a.branch.stored_terminal_flow_inconsistent(1)&&~a.summary.stored_terminal_flows_consistent);
tests(end+1)="saved_zero_flow_cannot_hide_overload";
bad=m;bad.branch(1,PF)=bad.branch(1,PF)+0.5;
a=audit_ny_ac_reference(bad);
assert(~a.passed&&a.summary.max_stored_terminal_flow_error_mva>=0.49);
tests(end+1)="stale_saved_terminal_power_rejected";
bad=m;bad.branch(1,RATE_A)=NaN;
a=audit_ny_ac_reference(bad);assert(~a.passed&&~a.summary.valid_branch_limit_bounds);
tests(end+1)="NaN_branch_rating_rejected";
% A zero-injection out-of-service record is not an operating voltage gate.
bad=m;extra=m.bus(1,:);extra(BUS_I)=9999;extra(BUS_TYPE)=NONE;
extra([PD QD GS BS VM VA])=0;bad.bus=[bad.bus;extra];
a=audit_ny_ac_reference(bad);assert(a.passed);
tests(end+1)="empty_out_of_service_bus_not_voltage_violation";
bad.bus(end,QD)=1;a=audit_ny_ac_reference(bad);
assert(~a.passed&&a.summary.excluded_injection_present);
tests(end+1)="out_of_service_bus_injection_rejected";
bad.bus(end,QD)=0;g=m.gen(1,:);g(GEN_BUS)=9999;g(PG)=0;g(QG)=1;
bad.gen=[bad.gen;g];bad=rmfield(bad,'gencost');
a=audit_ny_ac_reference(bad);
assert(~a.passed&&a.summary.excluded_online_generator_present);
tests(end+1)="online_reactive_source_at_excluded_bus_rejected";
report=table(tests(:),true(numel(tests),1),'VariableNames',{'test','passed'});disp(report);
end
