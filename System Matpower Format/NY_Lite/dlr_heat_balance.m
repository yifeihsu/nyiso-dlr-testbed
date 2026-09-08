function out=dlr_heat_balance(temperature_c,current_amp,conductor,weather)
%DLR_HEAT_BALANCE Per-subconductor lumped heat balance in W/m and degrees C.
% Implements IEEE738 convection/radiation and the simplified alpha*D*GHI
% solar approximation described by NREL/PR-6A40-91599 slide5. Dry ideal-gas
% density at film temperature. This is not the complete IEEE738-2023 solar,
% radial-gradient, sag/clearance or bundle-shielding calculation.
% Weather: ambient_c, wind_m_s, wind_angle_deg (to line axis), solar_w_m2,
% pressure_pa. Weather must be a declared scenario or independently sourced.
if istable(conductor),assert(height(conductor)==1);conductor=table2struct(conductor);end
if istable(weather),assert(height(weather)==1);weather=table2struct(weather);end
cf={'diameter_m','r_ref_ohm_m','r_reference_c','assumed_alpha20_per_c', ...
    'heat_capacity_j_m_k','emissivity','absorptivity'};
wf={'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'};
assert(isstruct(conductor)&&all(isfield(conductor,cf))&&isstruct(weather)&&all(isfield(weather,wf)), ...
    'dlr:Schema','Conductor and weather fields are incomplete.');
cv=cellfun(@(f)conductor.(f),cf);wv=cellfun(@(f)weather.(f),wf);
assert(all(isfinite([temperature_c current_amp cv wv]))&&isscalar(temperature_c)&&isscalar(current_amp) ...
    && temperature_c>-150&&temperature_c<400&&weather.ambient_c>-100&&weather.ambient_c<100 ...
    && conductor.diameter_m>0&&conductor.r_ref_ohm_m>0&&conductor.heat_capacity_j_m_k>0 ...
    && conductor.assumed_alpha20_per_c>=0&&conductor.emissivity>=0&&conductor.emissivity<=1 ...
    && conductor.absorptivity>=0&&conductor.absorptivity<=1 ...
    && weather.wind_m_s>=0&&weather.solar_w_m2>=0&&weather.pressure_pa>=40000&&weather.pressure_pa<=120000, ...
    'dlr:Inputs','Invalid heat-balance values or units.');
c=conductor;w=weather;film_c=(temperature_c+w.ambient_c)/2;film_k=film_c+273.15;
rho=w.pressure_pa/(287.058*film_k);
mu=1.458e-6*film_k^1.5/(film_c+383.4);
kair=.02424+7.477e-5*film_c-4.407e-9*film_c^2;
re=c.diameter_m*rho*w.wind_m_s/mu;
phi=90-abs(mod(abs(w.wind_angle_deg),180)-90);
direction=1.194-cosd(phi)+.194*cosd(2*phi)+.368*sind(2*phi);
delta=temperature_c-w.ambient_c;d=abs(delta);
natural=3.645*sqrt(rho)*c.diameter_m^.75*d^1.25;
forced_low=direction*(1.01+1.35*re^.52)*kair*d;
forced_high=direction*.754*re^.6*kair*d;
qc=sign(delta)*max([natural forced_low forced_high]);
qr=pi*c.diameter_m*c.emissivity*5.67e-8*((temperature_c+273.15)^4-(w.ambient_c+273.15)^4);
qs=c.absorptivity*c.diameter_m*w.solar_w_m2;
r=c.r_ref_ohm_m*(1+c.assumed_alpha20_per_c*(temperature_c-20))/ ...
    (1+c.assumed_alpha20_per_c*(c.r_reference_c-20));
assert(r>0&&kair>0&&mu>0,'dlr:TemperatureRange','Thermal approximations left their valid numeric range.');
qj=current_amp^2*r;net=qj+qs-qc-qr;
out=struct('temperature_c',temperature_c,'current_amp',abs(current_amp),'resistance_ohm_m',r, ...
    'joule_w_m',qj,'solar_w_m',qs,'convection_w_m',qc,'radiation_w_m',qr,'net_w_m',net, ...
    'temperature_rate_c_s',net/c.heat_capacity_j_m_k,'film_temperature_c',film_c, ...
    'air_density_kg_m3',rho,'reynolds_number',re,'wind_direction_factor',direction);
end
