function out=compact_dlr_selection(build,snapshot)
%COMPACT_DLR_SELECTION Whitelist synthetic overhead research realizations.
% The 11 PERFORM source AC circuits have unverified overhead equipment type;
% their overhead reinterpretation is declared. The 12 infrastructure records
% are only the explicit CEEC/NYES/SmartPath overhead assumptions. NYC cables,
% transformers, boundary injections and other equivalents are excluded.
p=build.physical_branch_register;keys=string(p.device_key);
ir=build.infrastructure_branch_register;
eligible=ismember(string(ir.electrical_role),["assumed_345kV_overhead_circuit";"230kV_historical_template_rebuild_equivalent"]);
keys=[keys;string(ir.branch_key(eligible))];
[ok,rows]=ismember(keys,string(snapshot.branch_keys));assert(all(ok));
m=snapshot.candidate;[ok,f]=ismember(m.branch(rows,1),m.bus(:,1));assert(all(ok));kv=m.bus(f,10);
code=repmat("DRAKE_795_ACSR",numel(rows),1);code(kv>=345)="CARDINAL_954_ACSR";
bundle=ones(numel(rows),1);bundle(kv>=345)=2;
out=table(rows,keys,code,ones(numel(rows),1),bundle,m.branch(rows,6), ...
    repmat("assumed_overhead_AC",numel(rows),1),'VariableNames', ...
    {'branch_row','branch_key','conductor_code','circuits','bundle_count','equipment_limit_mva','declared_asset_kind'});
out.equipment_limit_policy=repmat("inherited_finite_RATE_A_treated_as_assumed_substation_equipment_ceiling",height(out),1);
out.reference_resistance_policy=repmat("electrical_R_assumed_AC75_not_source_verified_temperature",height(out),1);
out.multiplicity_policy=repmat("one_circuit_per_explicit_row_two_subconductors_at345_one_at230_assumed",height(out),1);
end
