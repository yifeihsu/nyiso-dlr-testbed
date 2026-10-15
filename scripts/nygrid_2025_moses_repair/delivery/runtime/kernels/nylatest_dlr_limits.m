function out=nylatest_dlr_limits(mpc,segments,conductors,weather)
%AC_DLR_LIMITS Whole-system OH segment ampacity and series-branch limits.
% One weather row may define a declared uniform scenario. Otherwise provide
% one row per segment. Heterogeneous series sections share phase current;
% per-subconductor currents and limiting weather/conductors remain separate.
assert(istable(segments)&&istable(conductors)&&istable(weather) ...
    &&height(segments)>0&&(height(weather)==1||height(weather)==height(segments)), ...
    'acDLR:Schema','Supply segment and conductor tables with one or per-segment weather rows.');
assert(all(segments.circuits>=1&segments.circuits==fix(segments.circuits)) ...
    &&all(segments.bundle_count>=1&segments.bundle_count==fix(segments.bundle_count)), ...
    'acDLR:Multiplicity','Circuits and bundle counts must be positive integers.');
[ok,ci]=ismember(string(segments.catalog_id),string(conductors.catalog_id));assert(all(ok),'acDLR:Catalog','Unknown conductor.');
rows=segments.branch_row;n=height(segments);
assert(all(rows>=1&rows<=size(mpc.branch,1)),'acDLR:BranchRows','Segment branch row is outside this topology.');
[okf,f]=ismember(mpc.branch(rows,1),mpc.bus(:,1));[okt,t]=ismember(mpc.branch(rows,2),mpc.bus(:,1));
assert(all(okf&okt)&&all(abs(mpc.bus(f,10)-segments.base_kv)<1e-9) ...
    &&all(abs(mpc.bus(t,10)-segments.base_kv)<1e-9) ...
    &&all(mpc.branch(rows,9)==0|mpc.branch(rows,9)==1)&&all(mpc.branch(rows,10)==0), ...
    'acDLR:PhysicalClass','Overhead thermal records must be same-voltage unity-tap lines.');
amps=zeros(n,1);r=zeros(n,1);margin=zeros(n,1);
for j=1:n
    c=conductors(ci(j),:);w=weather(min(j,height(weather)),:);temp=segments.temperature_max_c(j);
    assert(temp>=segments.temperature_min_c(j)&&w.ambient_c<temp, ...
        'acDLR:Temperature','Ambient must be below the stated thermal cap.');
    h=nylatest_conductor_heat(temp,0,c,w);margin(j)=h.convection_w_m+h.radiation_w_m-h.solar_w_m;
    assert(margin(j)>0,'acDLR:NoAmpacity','Weather alone violates the selected conductor temperature cap.');
    r(j)=h.resistance_ohm_m;amps(j)=sqrt(margin(j)/r(j));
end
phase=amps.*segments.circuits.*segments.bundle_count;
unique_rows=unique(rows);branch_phase=zeros(numel(unique_rows),1);kv=branch_phase;
for k=1:numel(unique_rows)
    use=rows==unique_rows(k);branch_phase(k)=min(phase(use));kv(k)=segments.base_kv(find(use,1));
end
out.segment=segments;out.segment.ampacity_subconductor_a=amps;
out.segment.phase_ampacity_a=phase;out.segment.resistance_at_cap_ohm_per_m=r;
out.segment.available_joule_at_cap_w_m=margin;
out.branch=table(unique_rows,kv,branch_phase,ones(numel(unique_rows),1),ones(numel(unique_rows),1), ...
    'VariableNames',{'branch_row','base_kv','series_phase_limit_a','circuits','bundle_count'});
out.weather=weather;out.weather_is_observed=false;
out.definition='steady_state_weather_ampacity_at_declared_temperature_cap';
out.current_uses_synthetic_AC_system_scale=true;
end
