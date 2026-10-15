function out=nylatest_conductor_heat(temperature_c,current_amp,conductor,weather)
%AC_CONDUCTOR_HEAT Reuse validated heat-transfer equations with catalog R(T).
% Heat balance is per individual subconductor. Gamma is not a current factor
% in the user-selected synthetic AC study system. Solar is the existing
% alpha*diameter*irradiance approximation, not a full sag/clearance model.
if istable(conductor),assert(height(conductor)==1);conductor=table2struct(conductor);end
c=conductor;
c.r_ref_ohm_m=nylatest_conductor_resistance(c,temperature_c);
c.r_reference_c=temperature_c;c.assumed_alpha20_per_c=0;
out=nylatest_dlr_heat_balance(temperature_c,current_amp,c,weather);
out.resistance_source='manufacturer_AC_piecewise_linear';
out.synthetic_system_current_without_gamma_lift=true;
end
