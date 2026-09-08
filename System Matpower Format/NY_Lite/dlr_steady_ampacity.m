function out=dlr_steady_ampacity(conductor,weather,temperature_limit_c)
%DLR_STEADY_AMPACITY Per-subconductor current at thermal equilibrium.
if istable(conductor),assert(height(conductor)==1);conductor=table2struct(conductor);end
if nargin<3,temperature_limit_c=conductor.temperature_limit_c;end
h=dlr_heat_balance(temperature_limit_c,0,conductor,weather);
available=h.convection_w_m+h.radiation_w_m-h.solar_w_m;
out=struct('ampacity_amp',sqrt(max(available,0)/h.resistance_ohm_m), ...
    'temperature_limit_c',temperature_limit_c,'zero_current_thermally_feasible',available>=0, ...
    'available_joule_w_m',available,'heat_balance_at_zero_current',h);
end
