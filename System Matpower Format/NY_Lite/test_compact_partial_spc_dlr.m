function tests=test_compact_partial_spc_dlr(build,snapshot)
%TEST_COMPACT_PARTIAL_SPC_DLR Adversarial selection and dimensional identities.
% Synthetic preflight requires no source archives, optimizer or saved result.
% Optional real build/snapshot additionally checks the actual selected assets.
[b,s]=fixture;tests=table();t=compact_partial_spc_dlr_selection(b,s);
assert(height(t)==25&&numel(unique(t.branch_key))==25);
tests=add(tests,"exact_11_source_8_CEEC_NYES_6_partial_SPC_whitelist",0);
assert(~any(contains(t.branch_key,"SMART_PATH"))&&~any(contains(t.branch_key,"REGIONAL")) ...
    &&~any(ismember(t.branch_key,["NY2025_SPC:AT2";"NY2025_SPC:AT3";"NY2025_SPC:TR2"])));
tests=add(tests,"retired_lines_transformers_and_regional_equivalent_excluded",0);
assert(all(t.circuits==1)&&all(t.bundle_count(20:21)==1)&&all(t.bundle_count(22:25)==2) ...
    &&all(t.conductor_code(20:25)=="DRAKE_795_ACSR"));
tests=add(tests,"registered_SPC_one_circuit_Drake_multiplicity_not_voltage_default",0);
r=build_dlr_corridor_realizations(s.candidate,t);
err=max(abs(r.effective_length_km(20:25)-t.declared_planning_length_miles(20:25)*1.609344));assert(err<1e-10);
tests=add(tests,"catalog_AC75_R_and_voltage_base_recover_declared_planning_length",err);
bad=b;bad.partial_spc_branch_register.thermal_surrogate_eligible(7)=true;
reject(@()compact_partial_spc_dlr_selection(bad,s),'partial_spc_dlr:Whitelist');
tests=add(tests,"stale_true_eligibility_cannot_enable_transformer",0);
bad=b;bad.partial_spc_branch_register.bundle_count(1)=2;
reject(@()compact_partial_spc_dlr_selection(bad,s),'partial_spc_dlr:Multiplicity');
tests=add(tests,"two_subconductors_at230_cannot_silently_change_current_divisor",0);
bad=b;bad.partial_spc_branch_register.from_base_kv(1)=345;
reject(@()compact_partial_spc_dlr_selection(bad,s),'partial_spc_dlr:StaleRegister');
tests=add(tests,"registered_voltage_base_is_checked_against_both_terminals",0);
bad=s;bad.candidate.branch(20,4)=bad.candidate.branch(20,4)*1.1;
reject(@()compact_partial_spc_dlr_selection(b,bad),'partial_spc_dlr:StaleBranch');
tests=add(tests,"snapshot_reactance_drift_rejected",0);
bad=b;bad.physical_branch_register.model_branch_row([1 2])=[2;1];
reject(@()compact_partial_spc_dlr_selection(bad,s),'partial_spc_dlr:Identity');
tests=add(tests,"source_row_pointer_cannot_replace_device_identity",0);
bad=s;bad.branch_keys(1)=bad.branch_keys(2);
reject(@()compact_partial_spc_dlr_selection(b,bad),'partial_spc_dlr:Identity');
tests=add(tests,"duplicate_snapshot_key_rejected",0);
bad=b;bs=s;bad.candidate.branch(20,11)=0;bs.candidate.branch(20,11)=0;
reject(@()compact_partial_spc_dlr_selection(bad,bs),'partial_spc_dlr:Inactive');
tests=add(tests,"offline_new_corridor_cannot_keep_thermal_eligibility",0);
bad=s;bad.candidate.branch(26,11)=1;
reject(@()compact_partial_spc_dlr_selection(b,bad),'partial_spc_dlr:Retirement');
tests=add(tests,"retired_Smart_Path_reactivation_rejected",0);
bad=b;bs=s;bad.candidate.bus(40,10)=345;bs.candidate.bus(40,10)=345;
reject(@()compact_partial_spc_dlr_selection(bad,bs),'partial_spc_dlr:NonOverhead');
tests=add(tests,"mixed_terminal_voltage_bases_never_assumed_overhead",0);
bad=b;bs=s;bad.candidate.branch(20,9)=1.5;bs.candidate.branch(20,9)=1.5;
reject(@()compact_partial_spc_dlr_selection(bad,bs),'partial_spc_dlr:NonOverhead');
tests=add(tests,"nominal_voltage_ratio_is_not_an_allowed_line_tap",0);
% A row permutation changes pointers, not which physical devices are selected.
bs=s;order=(33:-1:1)';bs.candidate.branch=bs.candidate.branch(order,:);bs.branch_keys=bs.branch_keys(order);
rt=compact_partial_spc_dlr_selection(b,bs);assert(isequal(t.branch_key,rt.branch_key) ...
    &&isequal(bs.candidate.branch(rt.branch_row,1:13),s.candidate.branch(t.branch_row,1:13)));
tests=add(tests,"NY_row_permutation_preserves_exact_source_key_selection",0);
c=compact_partial_spc_dlr_contract;
assert(height(c.weather)==4&&~any(c.weather.observed_weather)&&~c.fresh_holdout_validation ...
    &&~c.physical_conductor_verified&&~c.historical_as_operated_validation);
tests=add(tests,"four_synthetic_weather_conditions_and_year_end_counterfactual_scope",0);
if nargin>0
    assert(nargin==2);t=compact_partial_spc_dlr_selection(build,snapshot);
    r=build_dlr_corridor_realizations(snapshot.candidate,t);
    assert(height(r)==25&&all(r.research_thermal_eligible)&&~any(r.length_requires_review));
    tests=add(tests,"actual_partial_SPC_snapshot_has_25_qualified_surrogates",0);
    selected=startsWith(t.branch_key,"NY2025_SPC:");
    err=max(abs(r.effective_length_km(selected)-t.declared_planning_length_miles(selected)*1.609344));
    assert(err<1e-8,'partial_spc_dlr_test:Nominal','Real-case test requires the nominal impedance variant.');
    tests=add(tests,"actual_nominal_new_corridor_R_matches_declared_length",err);
end
assert(all(tests.passed));
end
function [b,s]=fixture
keys=["PERFORM2019:BRANCH:"+string((1:11)');"NY2025:CEEC:"+string((1:6)'); ...
    "NY2025:NYES:"+string((1:2)');"NY2025_SPC:"+["MH2";"MH3";"HA2";"HW2";"LINE11";"LINE13"]; ...
    "NY2025:SMART_PATH:"+string((1:4)');"NY2025_SPC:"+["AT2";"AT3";"TR2";"PLATTS_REGIONAL_EQ"]];
m=struct('version','2','baseMVA',100,'bus',zeros(66,13),'branch',zeros(33,13),'gen',zeros(1,21));
m.bus(:,1)=(1:66)';m.bus(:,2)=1;m.bus(:,8)=1;m.bus(:,10)=345;m.bus(:,12:13)=repmat([1.1 .9],66,1);
m.branch(:,1)=(1:2:65)';m.branch(:,2)=(2:2:66)';m.branch(:,3:5)=repmat([.001 .02 .01],33,1);
m.branch(:,6:8)=1000;m.branch(:,11)=1;m.branch(:,12:13)=repmat([-360 360],33,1);m.branch(26:29,11)=0;
m.bus(39:42,10)=230;
sp_rows=[(20:25)';(30:33)'];pkeys=keys(sp_rows);f=m.branch(sp_rows,1);to=m.branch(sp_rows,2);
kv=m.bus(f,10);lengths=[10;12;50;27;41;24;NaN;NaN;NaN;NaN];bundle=1+(kv==345);
lib=dlr_conductor_library;drake=lib(lib.conductor_code=="DRAKE_795_ACSR",:);
m.branch(20:25,3)=drake.r_ref_ohm_m*lengths(1:6)*1609.344./bundle(1:6)./(kv(1:6).^2/100);
sp=table(pkeys,sp_rows,f,to,kv,kv,m.branch(sp_rows,3),m.branch(sp_rows,4),m.branch(sp_rows,5), ...
    m.branch(sp_rows,6),m.branch(sp_rows,11),[true(6,1);false(4,1)],repmat("DRAKE_795_ACSR",10,1),bundle,lengths, ...
    'VariableNames',{'branch_key','model_branch_row','from_bus','to_bus','from_base_kv','to_base_kv', ...
    'r_pu','x_pu','b_pu','rate_a_mva','status','thermal_surrogate_eligible','conductor_code','bundle_count','length_miles'});
sp.circuits=ones(10,1);sp.equipment_limit_mva=sp.rate_a_mva;
ir=table(keys(12:19),[repmat("CEEC",6,1);repmat("NYES",2,1)], ...
    repmat("assumed_345kV_overhead_circuit",8,1),(12:19)', ...
    'VariableNames',{'branch_key','project_id','electrical_role','model_branch_row'});
b=struct('candidate',m,'branch_keys',keys,'physical_branch_register', ...
    table(keys(1:11),(1:11)','VariableNames',{'device_key','model_branch_row'}), ...
    'infrastructure_branch_register',ir,'partial_spc_branch_register',sp);
s=struct('candidate',m,'branch_keys',keys);
end
function reject(fn,id)
try,fn();catch err,assert(strcmp(err.identifier,id),'Expected %s, received %s.',id,err.identifier);return;end
error('partial_spc_dlr_test:MissingGuard','Expected rejection %s.',id);
end
function t=add(t,name,error_value)
t=[t;table(string(name),true,error_value,'VariableNames',{'test','passed','max_error'})];
end
