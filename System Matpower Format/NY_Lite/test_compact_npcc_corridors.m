function out=test_compact_npcc_corridors
%TEST_COMPACT_NPCC_CORRIDORS Independent electrical/device preservation checks.
b=build_compact_npcc_corridors;c=b.candidate;p=b.parent;s=b.source_inventory.source;
sr=[1389;1390;1391;1392;1689;1690;1734;1735;1577;1576;1738];mr=(247:257)';
names=strings(0,1);passed=false(0,1);
assert(b.validation.pass&&height(b.validation.gates)==13);
names(end+1)="constructor_preservation_gates";passed(end+1)=true;
assert(isequal([size(c.bus,1) size(c.branch,1) size(c.gen,1)],[145 257 62]) ...
    && sum(c.branch(:,11)>0)==252&&sum(b.ny_bus_mask)==51 ...
    && sum(b.ny_branch_mask)==92&&sum(b.ny_branch_mask&c.branch(:,11)>0)==87 ...
    && sum(b.ny_generator_mask)==35);
names(end+1)="full_and_NY_counts_under_hard_cap";passed(end+1)=true;
assert(isequal(c.bus(1:143,:),p.bus)&&isequal(c.gen,p.gen)&&isequal(c.gencost,p.gencost));
names(end+1)="all_benchmark_loads_shunts_capability_and_controls_unchanged";passed(end+1)=true;
pn=ismember(p.bus(:,1),b.ny_bus_ids);
assert(sum(c.bus(b.ny_bus_mask,3))==sum(p.bus(pn,3)) ...
    && sum(c.bus(b.ny_bus_mask,4))==sum(p.bus(pn,4)) ...
    && isequal(c.bus(144:145,1),[858;774])&&all(c.bus(144:145,3:6)==0,'all'));
names(end+1)="benchmark_MW_scale_and_zero_injection_expansion";passed(end+1)=true;
retired=[88;89;94;235;236];want=p.branch;want(retired,11)=0;
assert(isequal(c.branch(1:246,:),want)&&nnz(c.branch(1:246,:)~=p.branch)==5 ...
    && isequal(b.retired_parent_rows,retired));
names(end+1)="exactly_five_old_contributions_retired_once";passed(end+1)=true;
assert(isequal(b.physical_branch_register.source_branch_row,sr) ...
    && isequal(b.physical_branch_register.model_branch_row,mr) ...
    && numel(unique(b.physical_branch_register.device_key))==11 ...
    && all(b.physical_branch_register.individual_circuit_identity_resolved));
names(end+1)="all_eleven_source_circuit_identities_are_unique";passed(end+1)=true;
for k=3:11
    assert(isequal(c.branch(mr,k),s.branch(sr,k)));
    names(end+1)="source_branch_column_"+string(k)+"_unchanged";passed(end+1)=true;
end
assert(all(s.branch(sr,12:13)==0,'all')&&all(c.branch(mr,12)==-360)&&all(c.branch(mr,13)==360));
names(end+1)="unrestricted_source_angle_semantics_preserved";passed(end+1)=true;
map=b.bus_map;[ff,fi]=ismember(s.branch(sr,1),map.source_bus);[tf,ti]=ismember(s.branch(sr,2),map.source_bus);
assert(all(ff&tf)&&isequal(c.branch(mr,1:2),[map.model_bus(fi) map.model_bus(ti)]));
names(end+1)="explicit_original_source_endpoint_mapping";passed(end+1)=true;
% Independent closed-form series admittance and shunt sum for each exact
% S7 equivalent; both physical B values are retained rather than averaged.
for k=1:2
    pair={[249;250],[253;254]};old=[235 236];rows=pair{k};
    physical_series=sum(1./complex(c.branch(rows,3),c.branch(rows,4)));
    original_series=1/complex(p.branch(old(k),3),p.branch(old(k),4));
    assert(abs(physical_series-original_series)<1e-11 ...
        && abs(sum(c.branch(rows,5))-p.branch(old(k),5))<1e-12 ...
        && isequal(sum(c.branch(rows,6:8),1),p.branch(old(k),6:8)));
end
assert(all(b.local_identity_tests.max_admittance_error_pu<1e-11) ...
    && all(b.local_identity_tests.max_matched_flow_error_mva<1e-8));
names(end+1)="235_and_236_exact_parallel_R_X_B_ratings_and_flow";passed(end+1)=true;
f=b.functional_replacement_comparison;
assert(all(f.port_admittance_difference_pu>1e-3)&&~any(f.response_preserved) ...
    && ~any(f.residual_fit_performed)&&~any(b.parent_branch_disposition.residual_added));
names(end+1)="original_NPCC_response_change_is_explicit_no_residual_fit";passed(end+1)=true;
g=b.source_inventory.generator_inventory;
g=g(ismember(g.source_bus,map.source_bus),:);e=b.source_device_exclusion_register;
assert(sum(isnan(e.source_gen_row))==7&&sum(isfinite(e.source_gen_row))==height(g) ...
    && isequal(sort(e.source_gen_row(isfinite(e.source_gen_row))),sort(g.source_gen_row)) ...
    && ~any(e.added_to_benchmark));
names(end+1)="all_selected_terminal_source_devices_excluded_explicitly";passed(end+1)=true;
incident=find(ismember(s.branch(:,1),map.source_bus)|ismember(s.branch(:,2),map.source_bus));
assert(isequal(b.source_connection_omission_register.source_branch_row,setdiff(incident,sr)));
names(end+1)="omitted_incident_source_connections_are_explicit";passed(end+1)=true;
assert(~any(ismember([1228;1222;1567;772],c.bus(:,1))) ...
    && ~any(ismember((263:315)',b.physical_branch_register.model_branch_row)));
names(end+1)="uncertain_Phase1A_and_Phase1C_mesh_not_superimposed";passed(end+1)=true;
assert(numel(b.branch_keys)==257&&numel(unique(b.branch_keys))==257 ...
    && numel(b.generator_keys)==62&&numel(unique(b.generator_keys))==62);
names(end+1)="every_model_record_has_a_stable_key";passed(end+1)=true;
assert(~b.electrical_baseline_qualified&&~b.dlr_ready ...
    && ~any(b.physical_branch_register.dlr_eligible) ...
    && ~c.userdata.compact_npcc.source_devices_imported);
names(end+1)="construction_and_thermal_claim_boundaries";passed(end+1)=true;
rejected=false;
try,build_compact_npcc_corridors(struct('parent',p));
catch err,rejected=strcmp(err.identifier,'compact_npcc:ParentOverride');end
assert(rejected);
names(end+1)="custom_parent_cannot_bypass_reproducible_benchmark";passed(end+1)=true;
out=struct('pass',all(passed),'assertion_groups',numel(passed), ...
    'gates',table(names(:),passed(:),'VariableNames',{'test','passed'}), ...
    'ny_bus_count',sum(b.ny_bus_mask),'ny_active_branch_count',sum(b.ny_branch_mask&c.branch(:,11)>0), ...
    'benchmark_NY_load_mw',sum(c.bus(b.ny_bus_mask,3)));
disp(out.gates);
end
