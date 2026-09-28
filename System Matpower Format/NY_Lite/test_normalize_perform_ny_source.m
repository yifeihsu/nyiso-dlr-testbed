function out=test_normalize_perform_ny_source
%TEST_NORMALIZE_PERFORM_NY_SOURCE Real pinned source and role-accounting guards.
n=normalize_perform_ny_source;
g=n.generator_inventory;b=n.boundary_reconciliation;l=n.branch_inventory;
assert(n.validation.pass && height(n.validation.gates)==32 && width(n.validation.gates)==2);
assert(isequal(n.source,nyiso_On_Peak_v23_shunts_as_z_load), ...
    'The normalized source must retain every original MATPOWER field and column.');
assert(height(n.bus_inventory)==1576 && height(l)==2371 && height(g)==615);
assert(nnz(g.native_generation_member)==594 && nnz(b.boundary_member)==20);
assert(nnz(b.boundary_member & b.canonical_status>0)==14 && ...
    nnz(b.boundary_member & b.canonical_status==0)==6 && nnz(b.legacy_schedule_member)==19);
assert(nnz(g.source_device_role=="reference_placeholder")==1 && ...
    g.device_key(g.source_device_role=="reference_placeholder")=="PERFORM2019:GEN:1263:RF");
assert(nnz(~l.individual_circuit_identity_resolved)==287 && ...
    all(contains(l.raw_identity_candidates(~l.individual_circuit_identity_resolved),";")));
d=l(~l.raw_canonical_parameters_match,:);
assert(height(d)==1 && d.source_branch_row==2013 && d.source_from_bus==1137 && d.source_to_bus==1169 && ...
    abs(d.raw_parameter_max_abs_difference-0.00107)<1e-10);
assert(height(n.shunt_inventory)==34 && nnz(n.shunt_inventory.canonical_bs_mvar)==20 && ...
    abs(sum(n.shunt_inventory.canonical_bs_mvar)-1035.9)<1e-8 && height(n.control_inventory)==793);
assert(nnz(g.raw_canonical_status_mismatch)==6 && ...
    all(g.source_device_role(g.raw_canonical_status_mismatch)=="external_boundary_proxy"));
remote=g(g.raw_remote_control_omitted,:);
assert(height(remote)==1 && remote.device_key=="PERFORM2019:GEN:138:1" && ...
    remote.canonical_regulated_bus==138 && remote.regulated_bus==1296);

% Negative cases are changes that could silently add native P/Q capability,
% reactivate an external proxy, double-count a shunt, or claim false provenance.
bad=n;bad.generator_inventory.native_generation_member(537)=true;
reject(bad,"native_membership_excludes_all_proxies");
bad=n;bad.generator_inventory.source_pmax_mw(1)=bad.generator_inventory.source_pmax_mw(1)+1;
reject(bad,"source_generator_bounds_preserved");
bad=n;bad.shunt_inventory.add_as_generator(1)=true;
reject(bad,"34_shunts_counted_once");
bad=n;bad.boundary_reconciliation.effective_pg_mw(b.source_bus==69)=8;
reject(bad,"offline_boundary_effective_PQ_zero");
bad=n;bad.boundary_reconciliation.source_gen_row(1)=bad.boundary_reconciliation.source_gen_row(1)+1;
reject(bad,"boundary_identity_matches_generator_inventory");
bad=n;bad.generator_inventory.canonical_status(74)=1;
reject(bad,"canonical_status_preserved");
bad=n;bad.branch_inventory.device_key(2)=bad.branch_inventory.device_key(1);
reject(bad,"branch_keys_unique");
bad=n;bad.branch_inventory.overhead_thermal_eligible(1)=true;
reject(bad,"no_implicit_overhead_classification");
bad=n;bad.branch_inventory.raw_identity_candidates(~l.individual_circuit_identity_resolved)="one_ID";
reject(bad,"ambiguous_parallel_circuit_identity_disclosed");
bad=n;bad.electrical_baseline_qualified=true;
reject(bad,"no_qualification_from_inventory");
bad=n;bad.power_scale="contemporary_actual_mw";
reject(bad,"no_qualification_from_inventory");
bad=n;bad.generator_inventory.raw_remote_control_omitted(:)=false;
reject(bad,"RAW_remote_control_conversion_explicit");
out=struct('pass',true,'assertion_groups',23,'inventory_gates',height(n.validation.gates), ...
    'case_counts',[height(n.bus_inventory),height(l),height(g)], ...
    'source_hash',n.canonical_sha256);
end

function reject(n,gate)
v=validate_perform_ny_inventory(n);
assert(~v.pass && ~v.gates.passed(v.gates.gate==gate), ...
    'test_normalize_perform_ny_source:MissedGuard','Expected failed inventory gate: %s',gate);
end
