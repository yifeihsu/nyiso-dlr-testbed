function tests=test_dlr_thermal_model
%TEST_DLR_THERMAL_MODEL Independent numeric fixtures, integration and units.
folder=fileparts(mfilename('fullpath'));lib=dlr_conductor_library;
ref=readtable(fullfile(folder,'fixtures','dlr_nrel_reference.csv'),'TextType','string');
tests=table();err=0;
for k=1:height(ref)
    c=lib(lib.conductor_code==ref.conductor_code(k),:);w=ref(k,:);
    h=dlr_heat_balance(ref.temperature_c(k),0,c,w);a=dlr_steady_ampacity(c,w);
    err=max([err abs(h.convection_w_m-ref.convection_w_m(k)) abs(h.radiation_w_m-ref.radiation_w_m(k)) ...
        abs(h.solar_w_m-ref.solar_w_m(k)) abs(a.ampacity_amp-ref.ampacity_amp(k))]);
end
tests=add(tests,"independent_NREL_21_case_fixture",err<1e-9,err);
c=lib(2,:);w=table(40,.61,90,1000,101325,'VariableNames', ...
    {'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'});
a=dlr_steady_ampacity(c,w);h=dlr_heat_balance(75,a.ampacity_amp,c,w);
tests=add(tests,"steady_ampacity_zero_net_heat",abs(h.net_w_m)<1e-10,abs(h.net_w_m));
w2=w;w2.wind_m_s=2;a2=dlr_steady_ampacity(c,w2);
w3=w;w3.ambient_c=45;a3=dlr_steady_ampacity(c,w3);
w4=w;w4.solar_w_m2=1200;a4=dlr_steady_ampacity(c,w4);
tests=add(tests,"wind_ambient_solar_monotonicity",a2.ampacity_amp>a.ampacity_amp&&a3.ampacity_amp<a.ampacity_amp&&a4.ampacity_amp<a.ampacity_amp,0);
hneg=dlr_heat_balance(75,-a.ampacity_amp,c,w);tests=add(tests,"current_direction_does_not_change_heating",hneg.joule_w_m==h.joule_w_m,0);
w2=w;w2.wind_angle_deg=270;a2=dlr_steady_ampacity(c,w2);
tests=add(tests,"axis_180_degree_symmetry",abs(a2.ampacity_amp-a.ampacity_amp)<1e-10,0);
w2=w;w2.ambient_c=80;a2=dlr_steady_ampacity(c,w2);
tests=add(tests,"zero_current_overtemperature_is_infeasible",~a2.zero_current_thermally_feasible&&a2.ampacity_amp==0,0);
h2=dlr_heat_balance(20,0,c,w);tests=add(tests,"cold_wire_receives_ambient_heat",h2.convection_w_m<0&&h2.radiation_w_m<0&&h2.net_w_m>0,0);
w2=w;w2.pressure_pa=101.325;
tests=add(tests,"reject_kPa_used_as_Pa",reject(@()dlr_heat_balance(75,100,c,w2)),0);
tests=add(tests,"reject_temperature_kelvin_used_as_ambient_C",reject(@()badambient(c,w)),0);
times=[0;600;1800];currents=[600;1000;1000];ws=repmat(w,3,1);ws.wind_m_s(2)=2;
t1=dlr_temperature_trace(times,currents,ws,c,40,struct('max_step_s',2));
t2=dlr_temperature_trace(times,currents,ws,c,40,struct('max_step_s',1));
truth=40;
for k=1:2
    [~,sol]=ode45(@(~,temp)rate(temp,currents(k),c,ws(k,:)),[times(k) times(k+1)],truth(end),odeset('RelTol',1e-10,'AbsTol',1e-10));
    truth(k+1,1)=sol(end);
end
err=max(abs(t1.temperature_c-truth));
tests=add(tests,"RK4_vs_adaptive_ode45",err<1e-6,err);
err=max(abs(t1.temperature_c-t2.temperature_c));tests=add(tests,"RK4_step_refinement",err<1e-6,err);
eq=dlr_temperature_trace([0;3600],[a.ampacity_amp;a.ampacity_amp],w,c,75);
err=max(abs(eq.temperature_c-75));tests=add(tests,"equilibrium_remains_stationary",err<1e-9,err);
assert(all(tests.passed),'dlr:ThermalTest','Thermal tests failed.');disp(tests);
end
function y=rate(t,i,c,w),h=dlr_heat_balance(t,i,c,w);y=h.temperature_rate_c_s;end
function badambient(c,w),w.ambient_c=313.15;dlr_heat_balance(75,100,c,w);end
function y=reject(f),y=false;try,f();catch,y=true;end,end
function t=add(t,name,pass,error_value)
t=[t;table(string(name),logical(pass),error_value,'VariableNames',{'test','passed','max_error'})];
end
