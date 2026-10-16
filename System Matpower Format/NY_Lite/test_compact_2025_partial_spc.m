function out=test_compact_2025_partial_spc(base)
%TEST_COMPACT_2025_PARTIAL_SPC Accounting, physical units and topology guards.
% Does not solve or inspect any public interface-flow observation.
if nargin<1||isempty(base),base=apply_compact_2025_generation(apply_compact_2025_infrastructure());end
before=base;o=apply_compact_2025_partial_spc(base);p=base.candidate;m=o.candidate;s=o.partial_spc_branch_register;
names=strings(0,1);passed=false(0,1);
assert(isequaln(base,before)&&o.partial_spc_validation.pass&&sum(o.ny_bus_mask)==71 ...
    &&size(m.bus,1)==165&&size(m.branch,1)==300&&nnz(o.ny_branch_mask)==135 ...
    &&nnz(o.ny_branch_mask&m.branch(:,11)>0)==117);
record("parent_is_immutable_and_71_bus_connected_construction");
assert(isequal(m.gen,p.gen)&&isequal(m.gencost,p.gencost) ...
    &&isequal(m.bus(1:160,3:6),p.bus(:,3:6))&&isequal(o.generator_keys,base.generator_keys));
original=ismember(p.bus(:,1),(37:82)');assert(isequal(m.bus(original,:),p.bus(original,:)));
record("all_original46_NPCC_bus_hardware_and_injection_gen_bounds_preserved");
d=o.partial_spc_branch_dispositions;assert(all(m.branch(d.parent_branch_row,11)==0));
assert(isequal(o.partial_spc_predecessor_branch_matrix,p.branch(d.parent_branch_row,:)) ...
    &&isequal(d.historical_from_base_kv,[230;230;230;230;115]) ...
    &&isequal(d.historical_to_base_kv,[230;230;230;230;230]) ...
    &&all(ismember(m.branch(:,1:2),m.bus(:,1)),'all'));
assert(isequal(o.partial_spc_predecessor_infrastructure_register.status,ones(4,1)));
record("retired_overlapping_paths_archived_with_historical_voltage_no_dangling_endpoints");
bc=o.partial_spc_bus_role_change;j=find(m.bus(:,1)==1220);
assert(bc.before_bus_row(10)==230&&bc.after_bus_row(10)==345&&isequal(m.bus(j,:),bc.after_bus_row) ...
    &&all(bc.after_bus_row(3:6)==0)&&~any(m.gen(:,1)==1220)&&~bc.original_NPCC_bus ...
    &&isnan(o.bus_map_2025.source_bus_name_voltage_identity(o.bus_map_2025.model_bus==1220)));
record("reused_proxy_ID_explicitly_changes_role_without_claiming_source_device_identity");

% Independent numeric expectations in ohms/siemens (100MVA voltage bases).
ha=find(s.branch_key=="NY2025_SPC:HA2");row=s.model_branch_row(ha);z345=345^2/100;z230=230^2/100;
expected_x=.10931*z230*83.7/105.5;expected_b=.41705/z230*83.7/105.5;
expected_r=(.026/304.8)*(83.7*1609.344)/2;
assert(abs(m.branch(row,3)*z345-expected_r)<1e-12 ...
    &&abs(m.branch(row,4)*z345-expected_x)<1e-11 ...
    &&abs(m.branch(row,5)/z345-expected_b)<1e-15);
assert(abs(s.rate_a_mva(ha)-sqrt(3)*345*2177/1000)<1e-10);
record("HA2_physical_ohm_siemens_and_amp_to_MVA_conversion_independently_checked");
vkv=[340*exp(1j*4*pi/180);334*exp(1j*pi/180)];vpu=vkv/345;
r=m.branch(row,:);ipu=(vpu(1)-vpu(2))/(r(3)+1j*r(4))+1j*r(5)/2*vpu(1);
amp_pu=ipu*100*1000/(sqrt(3)*345);
amp_physical=((vkv(1)-vkv(2))*1000/sqrt(3))/(expected_r+1j*expected_x) ...
    +1j*expected_b/2*vkv(1)*1000/sqrt(3);
assert(abs(amp_pu-amp_physical)<1e-9);
record("terminal_current_agrees_in_physical_units_after_voltage_rebase");

tr=ismember(s.branch_key,["NY2025_SPC:AT2";"NY2025_SPC:AT3";"NY2025_SPC:TR2"]);
assert(all(abs(s.r_pu(tr).*s.rate_a_mva(tr)/100-.005)<1e-15) ...
    &&all(abs(s.x_pu(tr).*s.rate_a_mva(tr)/100-.12)<1e-15) ...
    &&all(s.tap(tr)==1)&&all(s.b_pu(tr)==0)&&~any(s.thermal_surrogate_eligible(tr)));
reg=find(s.branch_key=="NY2025_SPC:PLATTS_REGIONAL_EQ");
assert(isequal([s.from_bus(reg),s.to_bus(reg),s.from_base_kv(reg),s.to_base_kv(reg)],[49 9124 115 230]) ...
    &&isequal([s.r_pu(reg),s.x_pu(reg),s.b_pu(reg),s.tap(reg)],[.0156 .1536 0 1]) ...
    &&~s.thermal_surrogate_eligible(reg));
record("transformer_own_base_conversion_and_Platts115_landing_are_explicit");

% Build the NY-only topology for operators without loading targets or a PF.
ny=m;ny.bus=m.bus(o.ny_bus_mask,:);ny.branch=m.branch(o.ny_branch_mask,:);
ny.gen=m.gen(o.ny_generator_mask,:);ny.userdata.nyiso_physical_zone=m.userdata.nyiso_physical_zone(o.ny_bus_mask);
op=compact_nyiso_interface_operator_variant(ny,o.branch_keys(o.ny_branch_mask));
members=op.members;ms=members(members.interface_name=="Moses_South",:);
assert(any(ms.branch_key=="NY2025_SPC:HA2") ...
    &&~any(ismember(ms.branch_key,d.parent_branch_key)) ...
    &&ms.metered_bus(ms.branch_key=="NY2025_SPC:HA2")==9121);
assert(any(ms.branch_key=="NPCC_S7:BRANCH_ROW:48")); % retained Porter-Colton115 support
record("Moses_South_recomputes_from_active_cut_and_keeps_distinct_lower_voltage_support");

sel=table(s.model_branch_row(1:6),s.branch_key(1:6),s.conductor_code(1:6), ...
    s.circuits(1:6),s.bundle_count(1:6),s.equipment_limit_mva(1:6),s.electrical_role(1:6), ...
    'VariableNames',{'branch_row','branch_key','conductor_code','circuits','bundle_count','equipment_limit_mva','declared_asset_kind'});
realization=build_dlr_corridor_realizations(m,sel);
assert(all(abs(realization.effective_length_km-s.length_miles(1:6)*1.609344)<1e-10) ...
    &&all(realization.resistance_identity_error_ohm<1e-12) ...
    &&all(~s.physical_conductor_verified)&&nnz(s.thermal_surrogate_eligible)==6);
record("six_OH_thermal_surrogates_reproduce_declared_AC75_physical_length_and_R");

low=apply_compact_2025_partial_spc(base,struct('impedance_scale',.75,'charging_scale',0,'rating_scale',.8));
high=apply_compact_2025_partial_spc(base,struct('impedance_scale',1.25,'charging_scale',1.5,'rating_scale',1.2));
a=low.partial_spc_branch_register;b=high.partial_spc_branch_register;ix=1:9;
assert(max(abs(a.r_pu(ix)-.75*s.r_pu(ix)))<1e-15&&max(abs(b.x_pu(ix)-1.25*s.x_pu(ix)))<1e-15 ...
    &&all(a.b_pu(ix)==0)&&max(abs(b.b_pu(ix)-1.5*s.b_pu(ix)))<1e-15 ...
    &&max(abs(a.rate_a_mva(ix)-.8*s.rate_a_mva(ix)))<1e-10 ...
    &&max(abs(b.rate_a_mva(ix)-1.2*s.rate_a_mva(ix)))<1e-10 ...
    &&isequal(a(reg,{'r_pu','x_pu','b_pu','rate_a_mva'}),s(reg,{'r_pu','x_pu','b_pu','rate_a_mva'})));
assert(isequal(low.candidate.branch(1:290,:),m.branch(1:290,:)) ...
    &&isequal(high.candidate.bus,m.bus)&&isequal(high.candidate.gen,m.gen));
record("bounded_sensitivities_change_only_new_assumptions_not_parent_or_regional_budget");

pr=o.project_register;old=o.partial_spc_parent_project_register;ix=pr.project_id=="SMART_PATH_CONNECT";
assert(pr.included(ix)&&~old.included(ix)&&pr.status_basis(ix)=="selected_partial2025_with2026_exclusions" ...
    &&contains(o.assumption_register.declaration(o.assumption_register.assumption=="excluded_future"),"selected_partial_SPC2025_included"));
ev=o.partial_spc_commissioning_register;
assert(isstring(ev.documented_event_date)&&ev.documented_event_date(ev.asset_key=="SPC_HA2")=="2025-10-13" ...
    &&ev.nominal_voltage_kv(ev.asset_key=="SPC_XFMR_2025")=="345/230");
assert(all(strlength(o.partial_spc_source_manifest.sha256_lf_normalized)==64) ...
    &&all(contains(o.partial_spc_source_manifest.hash_policy,"CRLF_normalized_to_LF")));
record("live_project_status_and_mixed_precision_evidence_are_not_stale_or_coerced");

reject(@()apply_compact_2025_partial_spc(o),'AlreadyApplied');record("double_application_rejected");
bad=base;bad.candidate.branch(d.parent_branch_row(1),2)=47;bad.full_candidate=bad.candidate;
reject(@()apply_compact_2025_partial_spc(bad),'RetirementIdentity');
bad=base;bad.candidate.branch(d.parent_branch_row(5),4)=.12;bad.full_candidate=bad.candidate;
reject(@()apply_compact_2025_partial_spc(bad),'RetirementHardware');record("wrong_predecessor_identity_and_regional_budget_rejected");
bad=base;bad.candidate.bus(j,3)=1;bad.full_candidate=bad.candidate;
reject(@()apply_compact_2025_partial_spc(bad),'AdirondackRole');
bad=base;bad.candidate.bus(bad.candidate.bus(:,1)==49,10)=230;bad.full_candidate=bad.candidate;
reject(@()apply_compact_2025_partial_spc(bad),'LandingVoltage');record("nonzero_proxy_injection_and_false_Platts_voltage_rejected");
bad=base;bad.candidate.baseMVA=200;bad.full_candidate=bad.candidate;
reject(@()apply_compact_2025_partial_spc(bad),'Parent');
bad=base;bad.historical_template_register.b_pu(bad.historical_template_register.source_key=="1220_1230_1")=.2;
reject(@()apply_compact_2025_partial_spc(bad),'TemplateIdentity');record("wrong_MVA_base_and_stale_physical_template_rejected");
reject(@()apply_compact_2025_partial_spc(base,struct('impedance_scale',1.3)),'SensitivityBounds');
reject(@()apply_compact_2025_partial_spc(base,struct('charging_scale',-1)),'SensitivityBounds');
reject(@()apply_compact_2025_partial_spc(base,struct('rating_scale',nan)),'Options');
reject(@()apply_compact_2025_partial_spc(base,struct('new_reactive_support',true)),'Options');
record("unregistered_or_unbounded_parameter_changes_rejected");
out=struct('pass',all(passed),'assertion_groups',numel(passed), ...
    'gates',table(names,passed,'VariableNames',{'test','passed'}));disp(out.gates);
    function record(name)
        names(end+1,1)=name;passed(end+1,1)=true;
    end
end

function reject(fn,suffix)
id=['partial_spc:' suffix];
try,fn();catch err,assert(strcmp(err.identifier,id),'Unexpected error %s',err.identifier);return;end
error('partial_spc_test:MissingGuard','Expected %s.',id);
end
