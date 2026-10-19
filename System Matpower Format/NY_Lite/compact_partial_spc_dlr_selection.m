function out=compact_partial_spc_dlr_selection(build,snapshot)
%COMPACT_PARTIAL_SPC_DLR_SELECTION Explicit late-2025 overhead surrogates.
% Source circuits remain assumed overhead realizations. New SPC conductors,
% lengths and station ceilings are research assumptions, not installed-asset
% evidence. Retired Smart Path rows and regional/transformer links are excluded.
required={'physical_branch_register','infrastructure_branch_register','partial_spc_branch_register','branch_keys','candidate'};
assert(all(isfield(build,required)),'partial_spc_dlr:Schema','Missing construction registers.');
m=snapshot.candidate;p=build.physical_branch_register;ir=build.infrastructure_branch_register;
sp=build.partial_spc_branch_register;bk=string(build.branch_keys(:));sk=string(snapshot.branch_keys(:));
assert(numel(bk)==size(build.candidate.branch,1)&&numel(unique(bk))==numel(bk) ...
    &&numel(sk)==size(m.branch,1)&&numel(unique(sk))==numel(sk), ...
    'partial_spc_dlr:Identity','Branch keys must be unique and row aligned.');
assert(height(p)==11&&numel(unique(string(p.device_key)))==11, ...
    'partial_spc_dlr:Whitelist','Expected the eleven frozen PERFORM source circuits.');
take=ismember(string(ir.project_id),["CEEC";"NYES"]) ...
    &string(ir.electrical_role)=="assumed_345kV_overhead_circuit";
assert(nnz(take)==8,'partial_spc_dlr:Whitelist','Expected eight explicit CEEC/NYES overhead records.');
allowed="NY2025_SPC:"+["MH2";"MH3";"HA2";"HW2";"LINE11";"LINE13"];
eligible=logical(sp.thermal_surrogate_eligible);
assert(nnz(eligible)==6&&isequal(sort(string(sp.branch_key(eligible))),sort(allowed)), ...
    'partial_spc_dlr:Whitelist','Only the six declared SPC overhead records may be eligible.');
keys=[string(p.device_key);string(ir.branch_key(take));string(sp.branch_key(eligible))];
fullrows=[p.model_branch_row;ir.model_branch_row(take);sp.model_branch_row(eligible)];
assert(all(fullrows>=1&fullrows<=numel(bk)&fullrows==fix(fullrows)) ...
    &&isequal(bk(fullrows),keys)&&numel(unique(keys))==25, ...
    'partial_spc_dlr:Identity','Source/register pointers do not identify the exact branch keys.');
[ok,rows]=ismember(keys,sk);
assert(all(ok),'partial_spc_dlr:Identity','A whitelisted source branch is absent from the NY snapshot.');
assert(isequal(m.branch(rows,1:13),build.candidate.branch(fullrows,1:13)) ...
    &&m.baseMVA==build.candidate.baseMVA,'partial_spc_dlr:StaleBranch','Snapshot hardware differs from construction.');
assert(all(m.branch(rows,11)>0),'partial_spc_dlr:Inactive','A declared eligible overhead branch is offline.');
[ok,f]=ismember(m.branch(rows,1),m.bus(:,1));[ok2,t]=ismember(m.branch(rows,2),m.bus(:,1));
assert(all(ok&ok2),'partial_spc_dlr:Identity','Branch endpoints are absent.');
kv=m.bus(f,10);
assert(all(kv==m.bus(t,10))&&all(ismember(kv,[230;345])) ...
    &&all(ismember(m.branch(rows,9),[0;1]))&&all(m.branch(rows,10)==0), ...
    'partial_spc_dlr:NonOverhead','Unequal voltage bases, transformers or phase shifters are not eligible.');
code=repmat("DRAKE_795_ACSR",25,1);code(kv>=345)="CARDINAL_954_ACSR";
bundle=ones(25,1);bundle(kv>=345)=2;
last=(20:25)';code(last)=string(sp.conductor_code(eligible));bundle(last)=sp.bundle_count(eligible);
expected=sp(eligible,:);
assert(isequal(expected.from_bus,m.branch(rows(last),1))&&isequal(expected.to_bus,m.branch(rows(last),2)) ...
    &&isequal(expected.from_base_kv,kv(last))&&isequal(expected.to_base_kv,kv(last)) ...
    &&isequal([expected.r_pu expected.x_pu expected.b_pu expected.rate_a_mva expected.status], ...
    m.branch(rows(last),[3:6 11])),'partial_spc_dlr:StaleRegister','SPC electrical register differs from the case.');
assert(all(code(last)=="DRAKE_795_ACSR")&&all(bundle(last)==1+(kv(last)==345)), ...
    'partial_spc_dlr:Multiplicity','SPC surrogate conductor and multiplicity must match the declared one-circuit policy.');
assert(all(expected.circuits==1)&&isequal(expected.equipment_limit_mva,expected.rate_a_mva), ...
    'partial_spc_dlr:Multiplicity','Circuit count and finite station ceilings must remain explicitly registered.');
out=table(rows,keys,code,ones(25,1),bundle,m.branch(rows,6),repmat("assumed_overhead_AC",25,1), ...
    'VariableNames',{'branch_row','branch_key','conductor_code','circuits','bundle_count','equipment_limit_mva','declared_asset_kind'});
out.full_branch_row=fullrows;
out.source_class=[repmat("PERFORM_source_AC_assumed_overhead",11,1);repmat("CEEC_NYES_assumed_explicit_overhead",8,1);repmat("partial_SPC_assumed_explicit_overhead",6,1)];
out.equipment_limit_policy=repmat("finite_electrical_RATE_A_as_assumed_station_ceiling_not_verified_equipment",25,1);
out.reference_resistance_policy=[repmat("electrical_R_assumed_AC75_not_source_verified_temperature",19,1); ...
    repmat("declared_Drake_catalog_AC75_and_planning_length_not_installed_conductor",6,1)];
out.multiplicity_policy=repmat("one_circuit_per_row_two_subconductors_at345_one_at230_assumed",25,1);
out.declared_planning_length_miles=[NaN(19,1);expected.length_miles];
out.conductor_choice_basis=repmat("catalog_ACSR_surrogate_not_verified_installed_conductor",25,1);
if ismember('conductor_choice_basis',expected.Properties.VariableNames)
    out.conductor_choice_basis(last)=string(expected.conductor_choice_basis);
end
out.physical_conductor_verified=false(25,1);out.observed_weather=false(25,1);
% Guard against a stale true eligibility flag on the four replaced records.
old=startsWith(sk,"NY2025:SMART_PATH:");
assert(nnz(old)==4&&all(m.branch(old,11)==0),'partial_spc_dlr:Retirement','All four old Smart Path records must remain offline.');
end
