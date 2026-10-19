function out=nylatest_terminal_current_audit(result,limits)
%AC_TERMINAL_CURRENT_AUDIT Recompute actual terminal amps from AC S and V.
% Saved complex powers are independently verified by nylatest_audit_ac_solution.
rows=limits.branch_row;
[ok,f]=ismember(result.branch(rows,1),result.bus(:,1));assert(all(ok));
[ok,t]=ismember(result.branch(rows,2),result.bus(:,1));assert(all(ok));
ifrom=1000*abs(complex(result.branch(rows,14),result.branch(rows,15)))./(sqrt(3)*result.bus(f,10).*result.bus(f,8));
ito=1000*abs(complex(result.branch(rows,16),result.branch(rows,17)))./(sqrt(3)*result.bus(t,10).*result.bus(t,8));
fraction=max([ifrom./limits.total_terminal_current_limit_from_a,ito./limits.total_terminal_current_limit_to_a],[],2,'omitnan');
out.table=limits;out.table.actual_from_current_a=ifrom;out.table.actual_to_current_a=ito;
out.table.maximum_fraction=fraction;out.maximum_fraction=max([fraction;0]);
out.passed=all(isfinite([ifrom;ito]))&&out.maximum_fraction<=1+1e-6;
out.actual_voltage_used=true;out.charging_included=true;out.current_gamma_lift=false;
end
