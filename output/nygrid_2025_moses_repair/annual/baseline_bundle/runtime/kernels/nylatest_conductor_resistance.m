function r=nylatest_conductor_resistance(c,temperature_c)
%AC_CONDUCTOR_RESISTANCE Manufacturer AC R(T), per metre/subconductor.
% No gamma conversion, DC-resistance substitution, or cold extrapolation.
if istable(c),assert(height(c)==1);c=table2struct(c);end
t=[25 75 200];v=[c.r_ac25_ohm_per_m c.r_ac75_ohm_per_m c.r_ac200_ohm_per_m];
valid=isfinite(v);t=t(valid);v=v(valid);
assert(numel(t)>=2&&all(v>0)&&all(diff(v)>=0)&&isscalar(temperature_c) ...
    &&isfinite(temperature_c)&&temperature_c>=t(1)&&temperature_c<=t(end), ...
    'acDLR:ResistanceRange','Temperature must remain within the declared manufacturer AC table.');
r=interp1(t,v,temperature_c,'linear');
end
