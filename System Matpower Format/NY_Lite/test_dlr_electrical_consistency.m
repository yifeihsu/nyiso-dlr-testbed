function tests=test_dlr_electrical_consistency
%TEST_DLR_ELECTRICAL_CONSISTENCY Charging, multiplicity and stale-case guards.
m=loadcase('case9');m.branch(2,3)=.017;m.branch(2,4)=.092;m.branch(2,5)=.35;
s=table(2,"test_branch", "CARDINAL_954_ACSR",2,2,1000,"assumed_overhead_AC", ...
    'VariableNames',{'branch_row','branch_key','conductor_code','circuits','bundle_count','equipment_limit_mva','declared_asset_kind'});
r=build_dlr_corridor_realizations(m,s);tests=table();
err=max(r.resistance_identity_error_ohm);tests=add(tests,"R75_realization_identity",err<1e-12,err);
m.bus(:,8)=linspace(.97,1.04,size(m.bus,1));m.bus(:,9)=linspace(-4,6,size(m.bus,1));
a=dlr_series_current_audit(m,r,75);
tests=add(tests,"parallel_bundle_Joule_identity",max(a.heating_identity_error_mw)<1e-10,max(a.heating_identity_error_mw));
tests=add(tests,"charging_terminal_current_differs_from_series",abs(a.from_terminal_current_amp-a.series_phase_current_amp)>1,0);
mi=ext2int(m);[~,yf,yt]=makeYbus(mi.baseMVA,mi.bus,mi.branch);v=mi.bus(:,8).*exp(1i*mi.bus(:,9)*pi/180);
sf=v(mi.branch(:,1)).*conj(yf*v)*mi.baseMVA;st=v(mi.branch(:,2)).*conj(yt*v)*mi.baseMVA;
err=abs(real(sf(2)+st(2))-a.total_conductor_joule_mw);
tests=add(tests,"independent_MATPOWER_terminal_real_loss",err<1e-10,err);
hot=apply_dlr_temperature_resistance(m,r,95);a2=dlr_series_current_audit(hot,r,95);
tests=add(tests,"temperature_changes_only_R",isequal(m.branch(:,[1:2 4:end]),hot.branch(:,[1:2 4:end]))&&hot.branch(2,3)>m.branch(2,3)&&a2.heating_identity_error_mw<1e-10,0);
back=apply_dlr_temperature_resistance(hot,r,75);tests=add(tests,"R_updates_do_not_compound",abs(back.branch(2,3)-m.branch(2,3))<1e-15,0);
tests=add(tests,"reject_temperature_network_mismatch",reject(@()dlr_series_current_audit(m,r,95)),0);
wrong=m;wrong.branch(2,5)=wrong.branch(2,5)*2;
tests=add(tests,"reject_stale_shunt_or_identity",reject(@()dlr_series_current_audit(wrong,r,75)),0);
bad=s;bad.declared_asset_kind="underground_cable";
tests=add(tests,"reject_cable_thermal_selection",reject(@()build_dlr_corridor_realizations(m,bad)),0);
wrong=m;wrong.branch(2,9)=1.05;
tests=add(tests,"reject_transformer",reject(@()build_dlr_corridor_realizations(wrong,s)),0);
bad=s;bad.circuits=1.5;tests=add(tests,"reject_fractional_parallel_circuits",reject(@()build_dlr_corridor_realizations(m,bad)),0);
assert(all(tests.passed),'dlr:ElectricalTest','Electrical thermal consistency tests failed.');disp(tests);
end
function y=reject(f),y=false;try,f();catch,y=true;end,end
function t=add(t,name,pass,error_value)
t=[t;table(string(name),logical(pass),error_value,'VariableNames',{'test','passed','max_error'})];
end
