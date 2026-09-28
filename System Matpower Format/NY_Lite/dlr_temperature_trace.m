function out=dlr_temperature_trace(time_s,current_amp,weather,conductor,initial_c,options)
%DLR_TEMPERATURE_TRACE Piecewise-constant current/weather with RK4 substeps.
% Input row k applies on [time(k),time(k+1)); temperatures are continuous.
% Final input row is retained in the ledger but defines no following step.
if nargin<6,options=struct();end
if ~isfield(options,'max_step_s'),options.max_step_s=2;end
time_s=time_s(:);current_amp=current_amp(:);n=numel(time_s);
assert(n>=2&&all(isfinite(time_s))&&all(diff(time_s)>0)&&numel(current_amp)==n ...
    &&all(isfinite(current_amp))&&isscalar(initial_c)&&isfinite(initial_c) ...
    &&isscalar(options.max_step_s)&&isfinite(options.max_step_s)&&options.max_step_s>0&&options.max_step_s<=30, ...
    'dlr:TimeSeries','Times must be ordered and current samples finite with a positive substep.');
assert(istable(weather)&&(height(weather)==1||height(weather)==n),'dlr:WeatherSeries','Use one weather row or one row per timestamp.');
temp=zeros(n,1);temp(1)=initial_c;energy=zeros(n,1);steps=zeros(n,1);
if istable(conductor),assert(height(conductor)==1);conductor=table2struct(conductor);end
for k=1:n-1
    w=table2struct(weather(min(k,height(weather)),:));
    duration=time_s(k+1)-time_s(k);count=ceil(duration/options.max_step_s);dt=duration/count;x=temp(k);
    for j=1:count
        a=dlr_heat_balance(x,current_amp(k),conductor,w);
        b=dlr_heat_balance(x+dt*a.temperature_rate_c_s/2,current_amp(k),conductor,w);
        c=dlr_heat_balance(x+dt*b.temperature_rate_c_s/2,current_amp(k),conductor,w);
        d=dlr_heat_balance(x+dt*c.temperature_rate_c_s,current_amp(k),conductor,w);
        x=x+dt*(a.temperature_rate_c_s+2*b.temperature_rate_c_s+2*c.temperature_rate_c_s+d.temperature_rate_c_s)/6;
    end
    temp(k+1)=x;energy(k+1)=energy(k)+conductor.heat_capacity_j_m_k*(temp(k+1)-temp(k));steps(k+1)=count;
end
out=table(time_s,current_amp,temp,energy,steps,'VariableNames', ...
    {'time_s','subconductor_current_amp','temperature_c','stored_energy_change_j_m','integration_substeps'});
end
