function report=test_ny_region_replacement
%TEST_NY_REGION_REPLACEMENT Independent provenance and accounting guards.
define_constants;
[s,p,b]=fixture();o=struct('fail_on_error',false);
v=validate_ny_region_replacement(s,p,b,o);assert(v.passed);
assert(~v.operating_point_qualified&&~v.upstate_aggregation_identity_established&&~v.dlr_ready);
tests="valid_region_mapping_does_not_claim_operating_qualification";
x=b;x.candidate.branch(3,3)=x.candidate.branch(3,3)*2;
fails(s,p,x,o,"copied_source_electrical_parameters_and_status");
tests(end+1)="unregistered_branch_parameter_change_rejected";
x=b;x.source_branch_map=x.source_branch_map(1:2,:);
fails(s,p,x,o,"all_source_internal_and_crossing_records_mapped");
tests(end+1)="missing_source_crossing_rejected";
x=b;x.candidate.branch(end+1,:)=p.branch(2,:);
fails(s,p,x,o,"candidate_branch_provenance_is_total_and_disjoint");
tests(end+1)="old_inherited_parallel_path_cannot_be_superimposed";
x=b;x.retired_branch_register=x.retired_branch_register(1,:);
fails(s,p,x,o,"every_inherited_replacement_incident_row_retired");
tests(end+1)="inherited_downstate_row_cannot_escape_retirement";
x=b;x.candidate.branch(1,4)=.2;
fails(s,p,x,o,"retained_parent_rows_preserved");
tests(end+1)="upstate_parameter_change_requires_new_assumption";
x=b;x.candidate.bus(2,10)=69;
fails(s,p,x,o,"crossing_endpoint_voltage_classes");
tests(end+1)="crossing_port_base_kV_mismatch_rejected";
x=b;x.candidate.bus(3,12)=1.2;
fails(s,p,x,o,"exact_region_voltage_classes");
tests(end+1)="source_region_voltage_limit_widening_rejected";
x=b;x.candidate.bus(1,12)=1.2;
fails(s,p,x,o,"retained_parent_voltage_classes_and_limits_preserved");
tests(end+1)="retained_upstate_voltage_limit_widening_rejected";
x=b;x.candidate.bus(3,3)=x.candidate.bus(3,3)+1;
x.allocation.model_bus_ledger.pd_effective_mw(3)=x.candidate.bus(3,3);
fails(s,p,x,o,"candidate_load_boundary_shunt_conservation");
tests(end+1)="self_consistent_candidate_ledger_cannot_hide_extra_load";
x=b;x.allocation.source_load_ledger.gs_mw(1)=1;
fails(s,p,x,o,"source_gross_load_and_shunt_ledger_matches_original");
tests(end+1)="canonical_shunt_ledger_checked_against_source";
x=b;x.allocation.boundary_register.p_injection_mw=9;
x.allocation.model_bus_ledger.p_boundary_mw(4)=9;
x.allocation.model_bus_ledger.pd_effective_mw(4)=21;x.candidate.bus(4,3)=21;
fails(s,p,x,o,"fixed_boundary_PQ_matches_frozen_foundation");
tests(end+1)="changed_boundary_schedule_cannot_self_certify";
x=b;x.candidate.gen(2,9)=999;x.allocation.generator_map.pmax_mw(2)=999;
fails(s,p,x,o,"native_device_status_and_capability_unchanged");
tests(end+1)="native_capability_widening_rejected";
x=b;x.candidate.gen(end,2)=1;x.allocation.generator_map.prior_pg_mw(end)=1;
fails(s,p,x,o,"only_declared_bounded_Q_support_added");
tests(end+1)="reactive_support_cannot_supply_active_power";
x=b;x.candidate.gen(2,2)=x.candidate.gen(2,2)+1;
x.allocation.generator_map.prior_pg_mw(2)=x.candidate.gen(2,2);
fails(s,p,x,o,"candidate_dispatch_priors_match_frozen_foundation");
tests(end+1)="dispatch_prior_change_requires_separate_reconstruction";
x=b;x.candidate.gen(4,6)=1.01;x.allocation.control_map.mapped_vg_pu(4)=1.01;
fails(s,p,x,o,"declared_local_voltage_control_and_native_reference");
tests(end+1)="co_located_control_cannot_self_certify";
x=b;x.candidate.bus(1,2)=PQ;
fails(s,p,x,o,"declared_local_voltage_control_and_native_reference");
tests(end+1)="online_local_PV_control_cannot_silently_disappear";
x=b;x.allocation.control_map.policy(1)="unregistered_remote_control";
fails(s,p,x,o,"declared_local_voltage_control_and_native_reference");
tests(end+1)="unregistered_control_policy_rejected";
x=b;x.source_bus_map.model_bus(1)=101;
fails(s,p,x,o,"source_injections_remain_in_source_zone");
tests(end+1)="source_zone_aggregation_mismatch_rejected";
x=b;x.parent_branch_disposition=x.parent_branch_disposition(1:3,:);
fails(s,p,x,o,"parent_branch_disposition_is_total_and_disjoint");
tests(end+1)="external_retirement_requires_explicit_disposition";
[ds,dp,db]=fixture(["D";string(('G':'K')')]);
dv=validate_ny_region_replacement(ds,dp,db,o);
assert(dv.passed&&dv.retained_parent_bus_count==1&&dv.region_source_bus_count==3);
tests(end+1)="additional_D_replacement_preserves_remaining_parent_zone";
x=b;x.replacement_zones=["D";string(('G':'K')')];
fails(s,p,x,o,"all_declared_replacement_source_buses_in_region");
tests(end+1)="declared_extra_zone_requires_complete_source_region";
x=db;x.retired_branch_register=x.retired_branch_register(x.retired_branch_register.parent_branch_row~=1,:);
fails(ds,dp,x,o,"every_inherited_replacement_incident_row_retired");
tests(end+1)="additional_zone_inherited_branch_must_be_retired";
[fs,fp,fb]=fixture(string(('A':'K')'));
fv=validate_ny_region_replacement(fs,fp,fb,o);
assert(fv.passed&&fv.retained_parent_bus_count==0&&fv.region_source_bus_count==size(fs.bus,1));
assert(~fv.operating_point_qualified&&~fv.dlr_ready);
tests(end+1)="all_source_fallback_with_no_retained_parent_buses_is_auditable";
x=b;x.replacement_zones=["G";"H"];
try
    validate_ny_region_replacement(s,p,x,o);error('ny_region_test:UnexpectedPass','Missing mandatory zones were accepted.');
catch e
    assert(strcmp(e.identifier,'ny_region:ReplacementZones'));
end
tests(end+1)="mandatory_G_to_K_replacement_cannot_be_narrowed";
x=b;x.source_branch_map.device_key(1)="fabricated_source_identity";
fails(s,p,x,o,"branch_provenance_keys_match_source_and_parent");
tests(end+1)="source_branch_identity_cannot_be_fabricated";
x=b;x.branch_keys(2)=x.branch_keys(3);
fails(s,p,x,o,"branch_provenance_keys_match_source_and_parent");
tests(end+1)="exported_branch_keys_cannot_duplicate_another_record";
x=b;x.retired_branch_register.x_pu(1)=.9;
fails(s,p,x,o,"retired_branch_values_and_zero_contribution_preserved");
tests(end+1)="retired_branch_original_values_cannot_be_rewritten";
x=b;x.retired_branch_register.new_active_contribution(1)=1;
fails(s,p,x,o,"retired_branch_values_and_zero_contribution_preserved");
tests(end+1)="retired_branch_cannot_claim_an_active_contribution";
x=b;x.retired_legacy_bus_injections.retired_pd_mw(1)=999;
fails(s,p,x,o,"legacy_NY_injection_retirement_is_complete_and_original");
tests(end+1)="legacy_bus_archive_must_preserve_original_values";
x=b;x.retired_legacy_generators=x.retired_legacy_generators(1:end-1,:);
fails(s,p,x,o,"legacy_NY_injection_retirement_is_complete_and_original");
tests(end+1)="legacy_generator_retirement_cannot_omit_a_record";
x=b;isolated=x.candidate.bus(4,BUS_I);
incident=x.candidate.branch(:,F_BUS)==isolated|x.candidate.branch(:,T_BUS)==isolated;
x.candidate.branch(incident,BR_STATUS)=0;
fails(s,p,x,o,"active_network_is_connected");
tests(end+1)="disconnected_candidate_bus_rejected_by_explicit_connectivity_gate";
report=table(tests(:),true(numel(tests),1),'VariableNames',{'test','passed'});disp(report);
end

function fails(s,p,b,o,name)
v=validate_ny_region_replacement(s,p,b,o);
row=v.gates.metric==name;assert(any(row)&&~v.gates.passed(row)&&~v.passed, ...
    'ny_region_test:UnexpectedPass','Expected failed gate %s.',name);
end

function [s,p,b]=fixture(replacement_zones)
define_constants;
explicit_zones=nargin>0;
if ~explicit_zones,replacement_zones=string(('G':'K')');end
s=struct('version','2','baseMVA',100);
ids=[10;20;30;40;1263];zones=["D";"G";"H";"F";"F"];
s.bus=zeros(5,13);s.bus(:,BUS_I)=ids;s.bus(:,BUS_TYPE)=PQ;
s.bus(:,PD)=[10;20;30;40;0];s.bus(:,QD)=[2;3;4;5;0];
s.bus(:,BS)=[0;1;2;0;0];s.bus(:,VM)=[1.01;1.02;1;1.03;1.04];
s.bus(:,VA)=[-3;0;-1;2;4];s.bus(:,BASE_KV)=[345;345;115;115;115];
s.bus(:,ZONE)=[68;71;73;70;70];s.bus(:,VMAX)=1.1;s.bus(:,VMIN)=.9;
s.branch=zeros(4,13);s.branch(:,1:2)=[10 20;20 30;30 40;40 1263];
s.branch(:,BR_R)=.001;s.branch(:,BR_X)=.02;s.branch(:,BR_B)=.01;
s.branch(:,RATE_A)=1000;s.branch(:,BR_STATUS)=1;
s.branch(:,ANGMIN)=-360;s.branch(:,ANGMAX)=360;s.branch(2,TAP)=1.04;s.branch(2,SHIFT)=2;
s.gen=zeros(4,21);s.gen(:,GEN_BUS)=ids(1:4);s.gen(:,PG)=[10;30;20;35];
s.gen(:,QG)=[1;2;3;4];s.gen(:,QMAX)=100;s.gen(:,QMIN)=-100;
s.gen(:,VG)=[1.01;1.02;1;1.03];s.gen(:,MBASE)=100;s.gen(:,GEN_STATUS)=1;
s.gen(:,PMAX)=200;s.gen(:,PMIN)=0;
keys="NATIVE:"+string((1:4)');
n=struct();n.generator_inventory=table((1:4)',keys,true(4,1), ...
    'VariableNames',{'source_gen_row','device_key','native_generation_member'});
n.branch_inventory=table("SOURCE:BRANCH:"+string((1:size(s.branch,1))'), 'VariableNames',{'device_key'});
n.boundary_reconciliation=table(30,true,1, ...
    'VariableNames',{'source_bus','boundary_member','canonical_status'});
p=s;p.bus=zeros(5,13);p.bus(:,BUS_I)=[100;101;700;800;900];p.bus(:,BUS_TYPE)=PQ;
p.bus(:,VM)=1;p.bus(:,BASE_KV)=[345;115;345;115;345];p.bus(:,VMAX)=1.1;p.bus(:,VMIN)=.9;
p.userdata.nyiso_physical_zone={'D';'F';'G';'H';''};
p.gen(:,GEN_BUS)=[100;700;800;101];
p.branch=repmat(s.branch(1,:),4,1);p.branch(:,1:2)=[100 101;101 700;700 800;100 900];
model=[100;20020;20030;101;101];kind=repmat("assumed_same_zone_source_distance_aggregation",5,1);
exact=ismember(zones,replacement_zones);model(exact)=20000+ids(exact);kind(exact)="exact_source_region";
bm=table(ids,model,zones,kind,'VariableNames',{'source_bus','model_bus','zone','mapping_kind'});
pzones=string(p.userdata.nyiso_physical_zone);
retain=ismember(pzones,setdiff(string(('A':'K')'),replacement_zones));
replace=ismember(pzones,replacement_zones);
kept_rows=find(ismember(p.branch(:,F_BUS),p.bus(retain,BUS_I))&ismember(p.branch(:,T_BUS),p.bus(retain,BUS_I)));
retired_rows=find(ismember(p.branch(:,F_BUS),p.bus(replace,BUS_I))|ismember(p.branch(:,T_BUS),p.bus(replace,BUS_I)));
c=s;c.bus=[p.bus(retain,:);s.bus(exact,:)];c.bus(:,BUS_I)=[p.bus(retain,BUS_I);model(exact)];
c.userdata.nyiso_physical_zone=cellstr([pzones(retain);zones(exact)]);
source_rows=find(ismember(s.branch(:,F_BUS),ids(exact))|ismember(s.branch(:,T_BUS),ids(exact)));
physical=s.branch(source_rows,:);[~,sf]=ismember(physical(:,F_BUS),ids);[~,st]=ismember(physical(:,T_BUS),ids);
physical(:,F_BUS)=model(sf);physical(:,T_BUS)=model(st);
c.branch=[p.branch(kept_rows,:);physical];
fl=table(ids,s.bus(:,PD),s.bus(:,QD),[0;0;5;0;0],[0;0;1;0;0], ...
    'VariableNames',{'source_bus','pd_gross_mw','qd_gross_mvar','p_boundary_mw','q_boundary_mvar'});
fg=[s.gen;zeros(1,21)];fg(end,[GEN_BUS PG QG QMAX QMIN VG MBASE GEN_STATUS PMAX PMIN])= ...
    [1263 0 -5 900 -900 1.04 100 1 0 0];
f=struct('mpc',s,'generator_keys',[keys;"RESEARCH2019:Q_SUPPORT:1263:MARCY"], ...
    'gross_boundary_ledger',fl);f.mpc.gen=fg;
[~,mr]=ismember(model,c.bus(:,BUS_I));A=sparse(mr,(1:5)',1,size(c.bus,1),5);
gross=A*s.bus(:,[PD QD]);boundary=A*[fl.p_boundary_mw fl.q_boundary_mvar];
c.bus(:,[PD QD GS BS])=[gross-boundary A*s.bus(:,[GS BS])];
c.gen=fg;c.gen(:,GEN_BUS)=model;
for bus=unique(model)'
    rows=find(model==bus);w=fg(rows,QMAX)-fg(rows,QMIN);c.gen(rows,VG)=sum(w.*fg(rows,VG))/sum(w);
end
c.bus(:,BUS_TYPE)=PV;c.bus(c.bus(:,BUS_I)==20020,BUS_TYPE)=REF;
g=c.gen;
a=struct();a.reference_bus=20020;
a.source_load_ledger=table(ids,model,s.bus(:,PD),s.bus(:,QD),s.bus(:,GS),s.bus(:,BS), ...
    'VariableNames',{'source_bus','model_bus','pd_gross_mw','qd_gross_mvar','gs_mw','bs_mvar'});
a.model_bus_ledger=table(c.bus(:,BUS_I),gross(:,1),gross(:,2),boundary(:,1),boundary(:,2), ...
    c.bus(:,PD),c.bus(:,QD),c.bus(:,GS),c.bus(:,BS), ...
    'VariableNames',{'model_bus','pd_gross_mw','qd_gross_mvar','p_boundary_mw','q_boundary_mvar', ...
    'pd_effective_mw','qd_effective_mvar','gs_mw','bs_mvar'});
a.boundary_register=table(30,20030,5,1,'VariableNames',{'source_bus','model_bus','p_injection_mw','q_injection_mvar'});
a.generator_map=table((1:5)',f.generator_keys,[(1:4)';NaN],ids,model,zones,kind, ...
    g(:,GEN_STATUS),g(:,PG),g(:,QG),g(:,PMIN),g(:,PMAX),g(:,QMIN),g(:,QMAX), ...
    'VariableNames',{'model_gen_row','device_key','source_gen_row','source_bus','model_bus','zone','mapping_kind', ...
    'status','prior_pg_mw','prior_qg_mvar','pmin_mw','pmax_mw','qmin_mvar','qmax_mvar'});
a.control_map=table(f.generator_keys,ids,model,g(:,GEN_STATUS),fg(:,VG),g(:,VG), ...
    repmat("local_PV_common_terminal_Q_span_weighted_reference_prior",5,1), ...
    'VariableNames',{'device_key','source_bus','model_bus','status','source_reference_vg_pu','mapped_vg_pu','policy'});
b=struct('candidate',c,'source_bus_map',bm,'region_source_buses',ids(exact), ...
    'source_inventory',n,'allocation',a,'foundation',f);
if explicit_zones,b.replacement_zones=replacement_zones;end
b.source_branch_map=table(source_rows,numel(kept_rows)+(1:numel(source_rows))',n.branch_inventory.device_key(source_rows), ...
    'VariableNames',{'source_branch_row','model_branch_row','device_key'});
b.retained_parent_branch_map=table(kept_rows,(1:numel(kept_rows))',"NPCC_PARENT:BRANCH:"+string(kept_rows), ...
    'VariableNames',{'parent_branch_row','model_branch_row','device_key'});
b.retired_branch_register=table(retired_rows,repmat("fully_replaced_regional_function_assumed_correspondence",numel(retired_rows),1), ...
    'VariableNames',{'parent_branch_row','disposition'});
names={'parent_from_bus','parent_to_bus','r_pu','x_pu','b_pu','rate_a_mva','rate_b_mva','rate_c_mva', ...
    'tap','shift_deg','original_status','angle_min_deg','angle_max_deg'};
for k=1:13,b.retired_branch_register.(names{k})=p.branch(retired_rows,k);end
b.retired_branch_register.new_active_contribution=zeros(numel(retired_rows),1);
b.retired_branch_register.alternative_policy=repmat("historical_parent_kept_as_explicit_alternative_not_superimposed",numel(retired_rows),1);
disposition=repmat("external_network_removed",4,1);
disposition(kept_rows)="retained_upstate_NPCC_parameters";disposition(retired_rows)="replaced_downstate_regional_function";
b.parent_branch_disposition=table((1:4)',disposition,p.branch(:,F_BUS),p.branch(:,T_BUS),p.branch(:,BR_STATUS), ...
    'VariableNames',{'parent_branch_row','disposition','parent_from_bus','parent_to_bus','parent_status'});
b.branch_keys=[b.retained_parent_branch_map.device_key;b.source_branch_map.device_key];
ny=retain|replace;
b.retired_legacy_bus_injections=array2table(p.bus(ny,[BUS_I PD QD GS BS]), ...
    'VariableNames',{'parent_bus','retired_pd_mw','retired_qd_mvar','retired_gs_mw','retired_bs_mvar'});
gn=find(ismember(p.gen(:,GEN_BUS),p.bus(ny,BUS_I)));
b.retired_legacy_generators=array2table([gn p.gen(gn,[GEN_BUS PG QG PMIN PMAX QMIN QMAX])], ...
    'VariableNames',{'parent_gen_row','parent_bus','old_pg_mw','old_qg_mvar','old_pmin_mw','old_pmax_mw','old_qmin_mvar','old_qmax_mvar'});
b.retired_legacy_generators.disposition=repmat("retired_once_replaced_by_source_keyed_native_records",numel(gn),1);
end
