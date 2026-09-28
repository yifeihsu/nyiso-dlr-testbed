function tests=test_export_compact_network(out)
%TEST_EXPORT_COMPACT_NETWORK Conservation and identity checks, no solves.
if nargin<1,out=export_compact_network(struct('write_outputs',false));end
define_constants;m=out.parent.candidate;a=out.variants.paper74;b=out.variants.physical77;
names=strings(0,1);
assert(size(m.bus,1)==51&&size(m.branch,1)==92&&nnz(m.branch(:,BR_STATUS))==87&&size(m.gen,1)==35);
assert(all(ismember((37:82)',m.bus(:,BUS_I)))&&numel(unique(m.bus(:,BUS_I)))==51);
names(end+1)="pre2025_51_bus_inventory_and_all_original_46_IDs";
assert(out.gamma2019==0.358662225381536&&m.baseMVA==100);
assert(max(abs(a.candidate.gen(end-1:end,PMAX)-out.gamma2019*[1025.9;1039.9]))<1e-10);
names(end+1)="one_fixed_gamma_scales_public_nuclear_capacities_once";
for v={a,b}
    v=v{1};g=v.candidate.gen;
    assert(size(g,1)==37&&isequal(g(1:35,:),m.gen)&&isequal(v.candidate.branch,m.branch));
    assert(isequal(v.candidate.bus(:,[BUS_I PD QD GS BS BASE_KV VMIN VMAX]),m.bus(:,[BUS_I PD QD GS BS BASE_KV VMIN VMAX])));
    assert(all(g(end-1:end,PG)==0)&&all(g(end-1:end,PMIN)==0)&&all(g(end-1:end,GEN_STATUS)==1));
    assert(all(g(end-1:end,QMAX)<200&g(end-1:end,QMAX)>0)&&all(g(end-1:end,QMIN)==-g(end-1:end,QMAX)));
    assert(numel(unique(v.generator_keys))==37&&v.candidate.bus(v.candidate.bus(:,BUS_TYPE)==REF,BUS_I)==42);
end
names(end+1)="only_two_explicit_nuclear_devices_no_existing_hardware_or_gross_load_change";
names(end+1)="finite_assumed_reactive_envelopes_and_native_reference_42";
assert(all(a.candidate.gen(end-1:end,GEN_BUS)==74)&&all(b.candidate.gen(end-1:end,GEN_BUS)==77));
assert(isequal(a.candidate.gen(:,2:end),b.candidate.gen(:,2:end)));
names(end+1)="spatial_sensitivity_changes_only_nuclear_landing_and_PV_bus_type";
meta=out.bus_metadata;dif=meta.bus_id(meta.zone_roles_differ);
assert(all(ismember([38;46;47;62;69;77;79],dif))&&height(meta)==51);
names(end+1)="paper_allocation_and_compact_physical_zone_disagreements_visible";
op=out.parent.operators;order=size(m.branch,1):-1:1;mp=m;mp.branch=m.branch(order,:);
permuted=compact_nyiso_interface_operator_variant(mp,out.parent.branch_keys(order));
assert(isequal(op.from_coefficients(:,order),permuted.from_coefficients)&&isequal(op.to_coefficients(:,order),permuted.to_coefficients));
assert(~any(op.from_coefficients(:,m.branch(:,BR_STATUS)==0),'all')&&~any(op.to_coefficients(:,m.branch(:,BR_STATUS)==0),'all'));
names(end+1)="current_operator_identity_survives_permutation_and_excludes_retired_paths";
assert(numel(out.selected_inputs)==5&&height(out.input_bus_rows)==255&&height(out.input_generator_rows)==370);
outside=false;
for k=1:5
    s=out.selected_inputs{k};ledger=s.bus_rows;
    assert(abs(s.remaining_unallocated_source_mw)<1e-7);
    for name=["paper74","physical77"]
        q=s.(name);g=q.candidate.gen;target=sum(s.source_prior_zone_mw);
        assert(abs(sum(g(:,PG))-target)<1e-7&&isequal(g(:,PG),q.Pg_prior_mw));
        assert(max(abs(q.candidate.bus(:,PD)-(ledger.pd_gross_mw-ledger.p_boundary_mw)))<1e-9);
        assert(max(abs(q.candidate.bus(:,QD)-(ledger.qd_gross_mvar-ledger.q_boundary_mvar)))<1e-9);
        assert(all(isnan(q.interface_targets.target_flow_mw))&&~q.snapshot.default_campaign_interface_fit_allowed);
        assert(~q.source_dispatch_clipped&&~q.electrical_baseline_qualified);
        outside=outside||any(g(:,PG)>g(:,PMAX)+1e-8|g(:,PG)<g(:,PMIN)-1e-8);
    end
    assert(isequal(s.paper74.Pg_prior_mw,s.physical77.Pg_prior_mw));
end
names(end+1)="five_source_snapshots_restore_all_unallocated_H_generation_without_clipping";
names(end+1)="gross_load_minus_boundary_once_and_fixed_Q_accounting";
names(end+1)="identical_total_and_unit_priors_across_landing_sensitivity";
names(end+1)="interface_targets_NaN_and_no_new_electrical_qualification_claim";
assert(outside&&any(out.input_generator_rows.raw_prior_outside_bounds)&&~any(out.input_generator_rows.dispatch_clipped));
names(end+1)="raw_out_of_bounds_source_assignment_preserved_as_visible_diagnostic";
tests=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});
end
