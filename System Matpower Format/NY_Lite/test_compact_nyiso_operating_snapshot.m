function tests=test_compact_nyiso_operating_snapshot(build,inputs)
%TEST_COMPACT_NYISO_OPERATING_SNAPSHOT Real accounting and leakage guards.
if nargin<1,build=apply_compact_2025_infrastructure(build_compact_npcc_corridors);end
if nargin<2,inputs=build_compact_nyiso_snapshot_inputs(struct('scenario_ids','S1_2025_SUMMER_PEAK_PUBLIC'));end
id="S1_2025_SUMMER_PEAK_PUBLIC";s=build_compact_nyiso_operating_snapshot(build,inputs,id);define_constants;
names=strings(0,1);
assert(s.accounting_error_mw<1e-7&&sum(s.bus_injection_ledger.pd_gross_mw)>10000);
for z=string(('A':'K')')'
    target=s.loads.target_load_mw(string(s.loads.zone)==z);
    assert(abs(sum(s.bus_injection_ledger.pd_gross_mw(s.bus_injection_ledger.zone==z))-target)<1e-7);
end
assert(sum(s.bus_injection_ledger.pd_gross_mw(s.bus_injection_ledger.zone=="J"))>3000);
names(end+1)="all_zones_match_observed_shape_including_NYC";
assert(height(s.boundary_inputs)==10&&all(s.boundary_register.q_injection_mvar==0)&&height(s.omitted_boundary_records)==1);
assert(abs(sum(s.boundary_register.p_injection_mw)-sum(s.boundary_inputs.target_import_mw))<1e-9);
names(end+1)="ten_distinct_boundary_channels_counted_once_Q_assumed";
alt=build_compact_nyiso_operating_snapshot(build,inputs,id,struct('hq_boundary_policy','net_market_proxy_with_separate_Cedars'));
assert(~any(alt.boundary_inputs.public_interface_name=="SCH - HQ - NY")&& ...
    nnz(alt.boundary_inputs.public_interface_name=="SCH - HQ_IMPORT_EXPORT")==1&& ...
    nnz(alt.boundary_inputs.public_interface_name=="SCH - HQ_CEDARS")==1);
names(end+1)="HQ_sensitivity_replaces_overlapping_record_without_addition";
assert(size(s.candidate.bus,1)<=200&&all(ismember((37:82)',s.candidate.bus(:,BUS_I))));
assert(all(isfinite(s.candidate.gen(:,[PMIN PMAX QMIN QMAX])),'all'));
names(end+1)="bus_budget_original_identity_and_finite_bounds";
changed=inputs;changed.interfaces.target_flow_mw=changed.interfaces.target_flow_mw+10000;
other=build_compact_nyiso_operating_snapshot(build,changed,id);
assert(isequal(s.candidate,other.candidate)&&isequal(s.Pg_prior_mw,other.Pg_prior_mw));
names(end+1)="assembly_and_generation_prior_independent_of_interface_targets";
changed=inputs;selected=changed.external_records.scenario_id==id;
row=find(selected&changed.external_records.default_primary_scope,1);
changed.external_records=[changed.external_records;changed.external_records(row,:)];
expect(@()build_compact_nyiso_operating_snapshot(build,changed,id),'compact_snapshot:DuplicateBoundary');
names(end+1)="duplicate_boundary_observation_rejected";
held=s;held.snapshot.dataset_split(:)="heldout";
held.snapshot.default_campaign_interface_fit_allowed(:)=false;
expect(@()fit_compact_nyiso_operating_snapshot(held,struct('fit_interfaces',true)),'compact_fit:HeldoutLeakage');
names(end+1)="heldout_interface_objective_rejected_before_solve";
old=s.operators;order=(size(s.candidate.branch,1):-1:1)';m=s.candidate;m.branch=m.branch(order,:);
perm=compact_nyiso_interface_operators(m,s.branch_keys(order));
assert(isequal(old.from_coefficients(:,order),perm.from_coefficients)&&isequal(old.to_coefficients(:,order),perm.to_coefficients));
names(end+1)="operator_mapping_survives_branch_row_permutation";
at=find(s.branch_keys=="PERFORM2019:AC:651:858:1");m=s.candidate;m.branch(at,BR_STATUS)=0;
expect(@()compact_nyiso_interface_operators(m,s.branch_keys),'compact_interfaces:InactiveMember');
names(end+1)="inactive_source_operator_member_rejected";
at=old.members.interface_name=="UPNY_ConEd";
assert(nnz(at)==6&&numel(unique(old.members.branch_key(at)))==6&&~any(contains(old.members.branch_key(at),"897:902")));
names(end+1)="six_UPNY_members_without_downstream_series_doublecount";
assert(~s.operators.public_operator_complete&&~s.electrical_baseline_qualified&&~s.dlr_ready);
names(end+1)="assembly_never_self_qualifies_or_claims_public_operator_identity";
tests=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});disp(tests);
end
function expect(f,id)
caught="";try,f();catch err,caught=string(err.identifier);end
assert(caught==string(id),'compact_snapshot_test:Guard','Expected %s, received %s.',id,caught);
end
