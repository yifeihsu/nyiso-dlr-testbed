function out=build_dlr_corridor_realizations(mpc,selection)
%BUILD_DLR_CORRIDOR_REALIZATIONS Explicit synthetic overhead realizations.
% selection columns: branch_row,branch_key,conductor_code,circuits,bundle_count,
% equipment_limit_mva. Circuit/bundle counts are discrete declared choices;
% length is derived to reproduce frozen R at75C, not claimed geographic length.
need={'branch_row','branch_key','conductor_code','circuits','bundle_count','equipment_limit_mva','declared_asset_kind'};
assert(istable(selection)&&all(ismember(need,selection.Properties.VariableNames)), ...
    'dlr:Selection','An explicit keyed corridor selection is required.');
rows=selection.branch_row;n=height(selection);lib=dlr_conductor_library;
assert(n>0&&all(isfinite(rows)&rows==fix(rows)&rows>=1&rows<=size(mpc.branch,1)) ...
    &&numel(unique(rows))==n&&numel(unique(string(selection.branch_key)))==n, ...
    'dlr:Identity','DLR branches and keys must be unique valid records.');
[ok,li]=ismember(string(selection.conductor_code),lib.conductor_code);assert(all(ok),'dlr:Conductor','Unknown conductor template.');
[~,f]=ismember(mpc.branch(rows,1),mpc.bus(:,1));[~,t]=ismember(mpc.branch(rows,2),mpc.bus(:,1));
assert(all(f>0&t>0)&&all(ismember(string(selection.declared_asset_kind), ...
    ["assumed_overhead_AC";"documented_overhead_AC"])), ...
    'dlr:AssetKind','Declare overhead AC eligibility explicitly; known cables and DC devices are excluded.');
nc=selection.circuits;nb=selection.bundle_count;kv=mpc.bus(f,10);
assert(all(isfinite([nc;nb;selection.equipment_limit_mva]))&&all(nc>=1&nc==fix(nc)) ...
    &&all(nb>=1&nb<=8&nb==fix(nb))&&all(selection.equipment_limit_mva>0) ...
    &&all(mpc.branch(rows,11)>0)&&all(mpc.branch(rows,3)>0)&&all(mpc.branch(rows,4)>0) ...
    &&all(abs(kv-mpc.bus(t,10))<1e-9)&&all(mpc.branch(rows,9)==0|mpc.branch(rows,9)==1) ...
    &&all(mpc.branch(rows,10)==0)&&all(kv>=69), ...
    'dlr:NonthermalElement','Selection needs active positive-R/X equal-voltage AC corridors, not transformer/DC/zero-R links.');
r=mpc.branch(rows,3).*kv.^2/mpc.baseMVA;
length_m=r.*nc.*nb./lib.r_ref_ohm_m(li);
assert(all(isfinite(length_m)&length_m>0),'dlr:Length','Invalid effective realization length.');
out=selection;out.base_kv=kv;out.base_mva=repmat(mpc.baseMVA,n,1);
out.from_bus=mpc.branch(rows,1);out.to_bus=mpc.branch(rows,2);
out.frozen_r_pu=mpc.branch(rows,3);out.frozen_x_pu=mpc.branch(rows,4);out.frozen_b_pu=mpc.branch(rows,5);
out.resistance_reference_c=lib.r_reference_c(li);out.resistance_eq_ohm=r;
out.effective_length_km=length_m/1000;out.inherited_rating_a_mva=mpc.branch(rows,6);
out.reconstructed_r_ohm=lib.r_ref_ohm_m(li).*length_m./(nc.*nb);
out.resistance_identity_error_ohm=abs(out.reconstructed_r_ohm-r);
out.length_requires_review=length_m<1000|length_m>300000;
out.realization_class=repmat("synthetic_overhead_corridor",n,1);
out.length_policy=repmat("Rmatched_effective_length_not_surveyed_route",n,1);
out.physical_conductor_verified=false(n,1);out.thermal_parameters_assumed=true(n,1);
out.research_thermal_eligible=~out.length_requires_review;
out.qualification_scope=repmat("synthetic_electrothermal_consistency_requires_operating_and_weather_validation",n,1);
end
