function out = test_row235_replacement
%TEST_ROW235_REPLACEMENT Exact circuit accounting and fail-closed regressions.
b=build_s13_phase1b_candidate(struct('write_outputs',false,'verbose',false));
p=b.candidate;r=build_row235_replacement(p);m=r.candidate;
names=strings(0,1);passed=false(0,1);
assert(r.validation.pass && height(r.validation.gates)==11);
names(end+1)="nominal_local_gates";passed(end+1)=true;
assert(nnz(m.branch~=p.branch)==1 && m.branch(235,11)==0 ...
    && isequal(m.branch([256 257],:),p.branch([256 257],:)) ...
    && isequal(m.bus,p.bus) && isequal(m.gen,p.gen) && isequal(m.gencost,p.gencost));
names(end+1)="single_status_change_no_injection_or_rating_edits";passed(end+1)=true;
assert(isequal(r.bus_map.parent_bus,[73;9002]) && isequal(r.bus_map.source_bus,[651;902]) ...
    && all(r.bus_map.physical_zone=="G") && all(r.bus_map.parent_base_kv==345));
names(end+1)="original_bus_identity_and_alias";passed(end+1)=true;
assert(isequal(r.source_branch_register.source_branch_row,[1391;1392]) ...
    && isequal(r.source_branch_register.raw_circuit_id,["1";"2"]) ...
    && all(r.source_branch_register.individual_circuit_identity_resolved) ...
    && all(r.source_branch_register.parent_branch_row==[256;257]));
names(end+1)="unique_RAW_circuit_provenance";passed(end+1)=true;
assert(all(r.source_branch_register.source_angmin_deg==0) ...
    && all(r.source_branch_register.source_angmax_deg==0) ...
    && all(r.source_branch_register.parent_angmin_deg==-360) ...
    && all(r.source_branch_register.parent_angmax_deg==360));
names(end+1)="unrestricted_angle_semantics_preserved";passed(end+1)=true;
% Independent pi-circuit formula verifies the stamp and B/2 terminal split.
y=1/(.000405+1i*.006185);analytic=[y+1i*.63943/2 -y;-y y+1i*.63943/2];
assert(max(abs(r.local_admittance.candidate_pair-analytic),[],'all')<1e-11 ...
    && max(abs(r.local_admittance.parent_duplicate_pair-2*analytic),[],'all')<1e-11 ...
    && isequal(r.local_admittance.residual,complex(zeros(2))) ...
    && ~r.residual_fit_performed && r.disposition_register.residual_admittance_norm_pu==0);
names(end+1)="independent_pi_formula_and_zero_residual";passed(end+1)=true;
t=r.matched_terminal_tests;f=find(t.sample=="forward_transfer");q=find(t.sample=="reverse_transfer");
assert(t.physical_from_p_mw(f)>0 && t.physical_to_p_mw(f)<0 ...
    && t.physical_from_p_mw(q)<0 && t.physical_to_p_mw(q)>0 ...
    && all(t.physical_p_loss_mw>=-1e-9) ...
    && all(t.max_terminal_complex_power_error_mva<1e-8));
names(end+1)="matched_forward_reverse_and_losses";passed(end+1)=true;
f=find(t.sample=="equal_voltage_charging");
assert(abs(t.physical_from_q_mvar(f)+100*.63943/2)<1e-9 ...
    && abs(t.physical_to_q_mvar(f)+100*.63943/2)<1e-9);
names(end+1)="charging_not_lost_or_duplicated";passed(end+1)=true;
assert(~r.electrical_baseline_qualified && ~r.dlr_ready ...
    && ~m.userdata.row235_replacement.electrical_baseline_qualified ...
    && ~m.userdata.row235_replacement.dlr_ready);
names(end+1)="local_proof_not_global_or_thermal_qualification";passed(end+1)=true;
% Every electrical field of the retired aggregate is part of the contract.
for col=1:13
    bad=p;bad.branch(235,col)=bad.branch(235,col)+.001;
    expect_failure(bad,'row235:AggregateParameters');
    names(end+1)="reject_aggregate_column_"+string(col);passed(end+1)=true;
end
for col=[3 4 5 6 7 8 9 10 11 12 13]
    bad=p;bad.branch(256,col)=bad.branch(256,col)+.001;
    expect_failure(bad,'row235:PhysicalParameters');
    names(end+1)="reject_physical_column_"+string(col);passed(end+1)=true;
end
bad=p;bad.baseMVA=200;expect_failure(bad,'row235:BaseMVA');
names(end+1)="reject_wrong_MVA_base";passed(end+1)=true;
bad=p;bad.branch(end+1,:)=bad.branch(256,:);expect_failure(bad,'row235:DirectCircuitSet');
names(end+1)="reject_additional_duplicate_circuit";passed(end+1)=true;
bad=p;bad.bus_name{find(bad.bus(:,1)==73)}='UNVERIFIED';expect_failure(bad,'row235:BusIdentity');
names(end+1)="reject_terminal_identity_change";passed(end+1)=true;
bad=p;map=bad.userdata.s13.overlay_report.bus_map;
map.source_bus(map.model_bus==73)=652;bad.userdata.s13.overlay_report.bus_map=map;
expect_failure(bad,'row235:BusLineage');
names(end+1)="reject_registered_terminal_mapping_change";passed(end+1)=true;
bad=p;bad.branch([256 257],:)=bad.branch([257 256],:);
expect_failure(bad,'row235:PhysicalParameters');
names(end+1)="reject_swapped_distinct_circuits";passed(end+1)=true;
bad=p;bad.userdata.ny_lite.perform_tieline_calibration_report.impedance_scale(2)=.99;
expect_failure(bad,'row235:Lineage');
names(end+1)="reject_unproven_aggregate_lineage";passed(end+1)=true;
bad=p;map=bad.userdata.s13.overlay_report.branch_map;
map.source_circuit_id(map.model_branch_row==256)="2";
bad.userdata.s13.overlay_report.branch_map=map;expect_failure(bad,'row235:Lineage');
names(end+1)="reject_fabricated_source_circuit_identity";passed(end+1)=true;
expect_failure(m,'row235:AlreadyApplied');
names(end+1)="reject_double_application";passed(end+1)=true;
bad=p;bad.success=true;expect_failure(bad,'row235:SolvedParent');
names(end+1)="reject_stale_solved_parent";passed(end+1)=true;
c=build_s13_phase1c_candidate(struct('write_outputs',false,'verbose',false));
q=build_row235_replacement(c.candidate);
assert(q.validation.pass && nnz(q.candidate.branch~=c.candidate.branch)==1 ...
    && isequal(q.candidate.branch(263:end,:),c.candidate.branch(263:end,:)));
names(end+1)="Phase1C_append_only_extensions_preserved";passed(end+1)=true;
names=names(:);passed=passed(:);
out=struct('pass',all(passed),'assertion_groups',numel(passed), ...
    'gates',table(names,passed),'max_admittance_error_pu',r.validation.max_admittance_error_pu, ...
    'max_matched_flow_error_mva',r.validation.max_matched_flow_error_mva);
disp(out.gates);
end

function expect_failure(parent,id)
try
    build_row235_replacement(parent);
catch err
    assert(strcmp(err.identifier,id),'test_row235:WrongFailure', ...
        'Expected %s, received %s: %s',id,err.identifier,err.message);
    return
end
error('test_row235:MissingFailure','Invalid parent was accepted; expected %s.',id);
end
