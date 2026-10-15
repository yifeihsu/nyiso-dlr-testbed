function out=nylatest_dlr_current_audit(result,segments,conductors,temperature_c,limits)
%AC_DLR_CURRENT_AUDIT Exact AC series current and total conductor Joule loss.
% Charging is excluded from heating. No gamma is applied to solved current.
assert(isfield(result,'success')&&result.success&&size(result.branch,2)>=17, ...
    'acDLR:Unsolved','A converged AC result with terminal powers is required.');
n=height(segments);if isscalar(temperature_c),temperature_c=repmat(temperature_c,n,1);end
expected=nylatest_dlr_apply_resistance(result,segments,conductors,temperature_c);
rows=segments.branch_row;unique_rows=unique(rows);
assert(all(abs(result.branch(unique_rows,3)-expected.branch(unique_rows,3))<1e-11), ...
    'acDLR:ResistanceMismatch','Solved electrical R differs from the thermal state.');
[~,f]=ismember(result.branch(rows,1),result.bus(:,1));[~,t]=ismember(result.branch(rows,2),result.bus(:,1));
assert(all(result.branch(rows,11)>0)&&all(result.branch(rows,9)==0|result.branch(rows,9)==1) ...
    &&all(result.branch(rows,10)==0)&&all(abs(result.bus(f,10)-result.bus(t,10))<1e-9), ...
    'acDLR:PhysicalClass','Thermal audit must contain only active unity-tap overhead lines.');
v=result.bus(:,8).*exp(1i*deg2rad(result.bus(:,9)));
ipu=(v(f)-v(t))./(result.branch(rows,3)+1i*result.branch(rows,4));
phase=abs(ipu)*result.baseMVA*1000./(sqrt(3)*segments.base_kv);
sub=phase./(segments.circuits.*segments.bundle_count);
[ok,ci]=ismember(string(segments.catalog_id),string(conductors.catalog_id));assert(all(ok));
heating=zeros(n,1);
for j=1:n
    rr=nylatest_conductor_resistance(conductors(ci(j),:),temperature_c(j));
    heating(j)=3*segments.circuits(j)*segments.bundle_count(j)*sub(j)^2*rr*segments.segment_length_m(j)/1e6;
end
segment=segments;segment.temperature_c=temperature_c(:);segment.series_phase_current_a=phase;
segment.subconductor_current_a=sub;segment.joule_loss_mw=heating;
segment.ampacity_fraction=sub./limits.segment.ampacity_subconductor_a;
branch_heating=zeros(numel(unique_rows),1);loss=branch_heating;ratio=branch_heating;
for k=1:numel(unique_rows)
    use=rows==unique_rows(k);branch_heating(k)=sum(heating(use));
    loss(k)=result.branch(unique_rows(k),14)+result.branch(unique_rows(k),16);
    ratio(k)=max(segment.ampacity_fraction(use));
end
out.segment=segment;
out.branch=table(unique_rows,branch_heating,loss,abs(branch_heating-loss),ratio, ...
    'VariableNames',{'branch_row','conductor_joule_loss_mw','AC_terminal_real_loss_mw','loss_identity_error_mw','max_ampacity_fraction'});
out.maximum_loss_identity_error_mw=max(out.branch.loss_identity_error_mw);
out.maximum_ampacity_fraction=max(ratio);
out.passed=out.maximum_loss_identity_error_mw<=1e-7&&out.maximum_ampacity_fraction<=1+1e-6;
out.no_gamma_current_rescaling=true;
end
