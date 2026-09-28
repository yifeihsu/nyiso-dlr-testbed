function tests=test_dlr_operating_guards(evidence,realizations)
%TEST_DLR_OPERATING_GUARDS Fail-closed operating inputs and saved-state physics.
% No arguments: preflight adversarial cases, without an optimizer call.
% (evidence,realizations): also validate a qualified saved solve using fresh
% current/heat calculations, not its stored passed flags. No optimizer replay.
m=loadcase('case9');m.branch(2,3:5)=[.001 .02 .01];
selection=table(2,"GUARD:CASE9:2","CARDINAL_954_ACSR",1,2,200,"assumed_overhead_AC", ...
    'VariableNames',{'branch_row','branch_key','conductor_code','circuits','bundle_count','equipment_limit_mva','declared_asset_kind'});
r=build_dlr_corridor_realizations(m,selection);
assert(r.research_thermal_eligible&&~r.length_requires_review);
w=table(40,.61,90,1000,101325,'VariableNames', ...
    {'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'});
tests=table();
reject(@()solve_dlr_steady_operating_point(m,r,w,struct('temperature_tolerance_c',1e6)),'dlr:Options');
tests=add(tests,"reject_tolerance_that_would_accept_unequilibrated_first_iterate",true,0);
for v=[0 -.001 NaN Inf]
    reject(@()solve_dlr_steady_operating_point(m,r,w,struct('temperature_tolerance_c',v)),'dlr:Options');
end
tests=add(tests,"reject_nonpositive_or_nonfinite_thermal_tolerance",true,0);
for v=[0 1.5 201 NaN Inf]
    reject(@()solve_dlr_steady_operating_point(m,r,w,struct('max_iterations',v)),'dlr:Options');
end
tests=add(tests,"reject_invalid_iteration_count_before_optimizer",true,0);
bad=r;bad.research_thermal_eligible=false;
reject(@()solve_dlr_steady_operating_point(m,bad,w),'dlr:UnqualifiedRealization');
tests=add(tests,"reject_unqualified_realization_even_with_valid_electrical_R",true,0);
bad=r;bad.length_requires_review=true;bad.research_thermal_eligible=true;
reject(@()solve_dlr_steady_operating_point(m,bad,w),'dlr:UnqualifiedRealization');
tests=add(tests,"reject_conflicting_eligibility_and_length_review_flags",true,0);
long=m;long.branch(2,3)=.1;longr=build_dlr_corridor_realizations(long,selection);
assert(longr.length_requires_review&&~longr.research_thermal_eligible);
reject(@()solve_dlr_steady_operating_point(long,longr,w),'dlr:UnqualifiedRealization');
tests=add(tests,"reject_Rmatched_but_unreviewed_long_corridor_realization",true,0);
badw=w;badw.ambient_c=80;
reject(@()solve_dlr_steady_operating_point(m,r,badw),'dlr:WeatherInfeasible');
tests=add(tests,"reject_weather_overtemperature_without_current",true,0);
bad=m;bad.branch(2,4)=bad.branch(2,4)*2;
reject(@()solve_dlr_steady_operating_point(bad,r,w),'dlr:StaleRealization');
tests=add(tests,"reject_stale_reactance_before_thermal_dispatch",true,0);
bad=m;bad.branch(2,1)=1;
reject(@()solve_dlr_steady_operating_point(bad,r,w),'dlr:StaleRealization');
tests=add(tests,"reject_stale_endpoint_before_thermal_dispatch",true,0);
bad=m;[~,j]=ismember(bad.branch(2,1:2),bad.bus(:,1));bad.bus(j,10)=230;
reject(@()solve_dlr_steady_operating_point(bad,r,w),'dlr:StaleRealization');
tests=add(tests,"reject_stale_voltage_base_before_thermal_dispatch",true,0);
if nargin>0
    assert(nargin==2,'dlr_operating_test:Schema','Supply the saved operating evidence and its frozen realization table.');
    v=evidence;r=realizations;
    assert(v.synthetic_electrothermal_qualified&&v.independent_PF_pass&&v.converged ...
        && v.replay_audit.passed&&height(v.thermal_audit)==height(r), ...
        'dlr_operating_test:Evidence','Expected a qualified nominal result with a full independent thermal audit.');
    a=dlr_series_current_audit(v.result,r,v.temperature_c);
    [ok,j]=ismember(string(r.branch_key),string(v.thermal_audit.branch_key));
    assert(all(ok)&&numel(unique(j))==height(r));ta=v.thermal_audit(j,:);
    assert(all(ta.passed)&&all(abs(ta.heat_residual_w_m)<=.025) ...
        && all(abs(ta.independent_PF_equilibrium_c-ta.temperature_c)<=.01) ...
        && all(ta.temperature_c<=ta.temperature_limit_c+.01));
    tests=add(tests,"saved_qualification_has_complete_thermal_acceptance_evidence",true,0);
    err=max(abs(a.total_conductor_joule_mw-a.series_loss_mw));
    assert(err<1e-8);tests=add(tests,"replayed_currents_obey_three_phase_Joule_identity",true,err);
    [ok,j]=ismember(string(r.branch_key),string(v.current_audit.branch_key));assert(all(ok));
    err=max(abs(a.subconductor_current_amp-v.current_audit.subconductor_current_amp(j)));
    assert(err<1e-7);tests=add(tests,"saved_current_audit_matches_fresh_electrical_recomputation",true,err);
    lib=dlr_conductor_library;[ok,ci]=ismember(r.conductor_code,lib.conductor_code);assert(all(ok));
    residual=zeros(height(r),1);limit=zeros(height(r),1);
    for k=1:height(r)
        weather=v.weather(min(k,height(v.weather)),:);
        heat=dlr_heat_balance(v.temperature_c(k),a.subconductor_current_amp(k),lib(ci(k),:),weather);
        residual(k)=heat.net_w_m;amp=dlr_steady_ampacity(lib(ci(k),:),weather);limit(k)=amp.ampacity_amp;
    end
    err=max(abs(residual-ta.heat_residual_w_m));
    assert(err<1e-9&&max(abs(residual))<=.025);
    tests=add(tests,"thermal_residual_recomputed_from_fresh_PF_current_and_weather",true,err);
    ratio=max(a.subconductor_current_amp./limit);assert(ratio<=1+1e-6);
    tests=add(tests,"qualified_PF_obeys_recomputed_series_ampacity",true,ratio);
    reject(@()dlr_series_current_audit(v.result,r,v.temperature_c+5),'dlr:ResistanceMismatch');
    tests=add(tests,"tampered_temperature_rejected_by_electrical_resistance_identity",true,0);
    bad=v.result;bad.branch(r.branch_row(1),5)=bad.branch(r.branch_row(1),5)+.1;
    reject(@()dlr_series_current_audit(bad,r,v.temperature_c),'dlr:StaleRealization');
    tests=add(tests,"tampered_charging_rejected_by_frozen_realization",true,0);
end
assert(all(tests.passed));disp(tests);
end

function reject(fn,id)
try,fn();catch e,assert(strcmp(e.identifier,id),'Unexpected error %s, expected %s.',e.identifier,id);return;end
error('dlr_operating_test:MissingGuard','Expected %s.',id);
end
function t=add(t,name,passed,error_value)
t=[t;table(string(name),logical(passed),error_value,'VariableNames',{'test','passed','max_error'})];
end
