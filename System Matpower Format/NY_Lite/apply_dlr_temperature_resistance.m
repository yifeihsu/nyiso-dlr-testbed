function out=apply_dlr_temperature_resistance(mpc,realizations,temperature_c)
%APPLY_DLR_TEMPERATURE_RESISTANCE Update only the explicitly realized R(T).
% Starting cases may already have R(T); every update derives from frozen R75,
% never compounds temperature multipliers. X, B, tap, endpoints and base are
% immutable. Caller must solve and audit AC power flow after an update.
n=height(realizations);r=realizations.branch_row;
assert(n>0&&all(r>=1&r<=size(mpc.branch,1)&r==fix(r))&&numel(unique(r))==n);
if isscalar(temperature_c),temperature_c=repmat(temperature_c,n,1);end
temperature_c=temperature_c(:);
assert(numel(temperature_c)==n&&all(isfinite(temperature_c)&temperature_c>-150&temperature_c<400), ...
    'dlr:Temperature','Supply valid conductor temperatures in Celsius.');
[ok,f]=ismember(mpc.branch(r,1),mpc.bus(:,1));[okt,t]=ismember(mpc.branch(r,2),mpc.bus(:,1));
assert(all(ok&okt)&&all(mpc.branch(r,1)==realizations.from_bus&mpc.branch(r,2)==realizations.to_bus) ...
    &&all(mpc.branch(r,4)==realizations.frozen_x_pu&mpc.branch(r,5)==realizations.frozen_b_pu) ...
    &&all(mpc.branch(r,11)>0)&&all(mpc.branch(r,9)==0|mpc.branch(r,9)==1) ...
    &&all(mpc.branch(r,10)==0)&&all(mpc.bus(f,10)==realizations.base_kv) ...
    &&all(mpc.bus(f,10)==mpc.bus(t,10))&&all(mpc.baseMVA==realizations.base_mva), ...
    'dlr:StaleRealization','Thermal realization no longer matches branch identity or electrical base.');
lib=dlr_conductor_library;[ok,c]=ismember(string(realizations.conductor_code),lib.conductor_code);assert(all(ok));
a=lib.assumed_alpha20_per_c(c);
factor=(1+a.*(temperature_c-20))./(1+a.*(lib.r_reference_c(c)-20));
assert(all(factor>0));out=mpc;out.branch(r,3)=realizations.frozen_r_pu.*factor;
end
