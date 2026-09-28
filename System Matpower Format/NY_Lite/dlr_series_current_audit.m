function out=dlr_series_current_audit(result,realizations,temperature_c)
%DLR_SERIES_CURRENT_AUDIT Series current and exact three-phase Joule identity.
% Pi-model charging current is excluded from series-conductor heating.
% The supplied result must use R at the supplied temperature; disagreement
% is rejected rather than scaling heating independently of the PF network.
n=height(realizations);lib=dlr_conductor_library;
if isscalar(temperature_c),temperature_c=repmat(temperature_c,n,1);end
assert(numel(temperature_c)==n&&all(isfinite(temperature_c)),'dlr:Temperature','Supply one temperature per realization.');
rows=realizations.branch_row;[ok,ci]=ismember(string(realizations.conductor_code),lib.conductor_code);assert(all(ok));
expected=apply_dlr_temperature_resistance(result,realizations,temperature_c);
assert(all(abs(result.branch(rows,3)-expected.branch(rows,3))<1e-12), ...
    'dlr:ResistanceMismatch','Solve with temperature-matched electrical resistance before auditing heating.');
[~,f]=ismember(result.branch(rows,1),result.bus(:,1));[~,t]=ismember(result.branch(rows,2),result.bus(:,1));
v=result.bus(:,8).*exp(1i*result.bus(:,9)*pi/180);
ncnb=realizations.circuits.*realizations.bundle_count;
alpha=lib.assumed_alpha20_per_c(ci);
rsub=lib.r_ref_ohm_m(ci).*(1+alpha.*(temperature_c(:)-20))./(1+alpha.*(lib.r_reference_c(ci)-20));
req=rsub.*realizations.effective_length_km*1000./ncnb;
basekv=result.bus(f,10);actual_r=result.branch(rows,3).*basekv.^2/result.baseMVA;
assert(all(result.branch(rows,11)>0)&&all(result.branch(rows,9)==0|result.branch(rows,9)==1) ...
    &&all(result.branch(rows,10)==0)&&all(abs(basekv-result.bus(t,10))<1e-9) ...
    &&result.baseMVA==realizations.base_mva(1)&&all(abs(actual_r-req)<1e-9.*max(1,req)), ...
    'dlr:ResistanceMismatch','PF resistance/voltage base does not match the thermal realization and temperature.');
ipu=(v(f)-v(t))./(result.branch(rows,3)+1i*result.branch(rows,4));
current=abs(ipu).*result.baseMVA*1000./(sqrt(3)*basekv);
sub=current./ncnb;
loss=3*current.^2.*actual_r/1e6;
heating=3*ncnb.*sub.^2.*rsub.*realizations.effective_length_km*1000/1e6;
from_amps=abs(ipu+1i*result.branch(rows,5)/2.*v(f)).*result.baseMVA*1000./(sqrt(3)*basekv);
to_amps=abs(-ipu+1i*result.branch(rows,5)/2.*v(t)).*result.baseMVA*1000./(sqrt(3)*basekv);
out=table(rows,string(realizations.branch_key),temperature_c(:),current,sub,from_amps,to_amps,loss,heating,abs(loss-heating), ...
    'VariableNames',{'branch_row','branch_key','temperature_c','series_phase_current_amp', ...
    'subconductor_current_amp','from_terminal_current_amp','to_terminal_current_amp', ...
    'series_loss_mw','total_conductor_joule_mw','heating_identity_error_mw'});
end
