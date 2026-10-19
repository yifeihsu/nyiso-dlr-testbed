function report=test_compact_npcc_model_contract
%TEST_COMPACT_NPCC_MODEL_CONTRACT Enforce budget and preserve claim boundaries.
c=compact_npcc_model_contract;
assert(c.max_operating_bus_count==200 && c.original_NPCC_NY_bus_count==46 && ...
    c.planned_operating_bus_count==51 && c.planned_operating_branch_records==92 && ...
    c.planned_operating_active_branches==87 && c.planned_operating_generator_records==35);
names="compact_plan_and_hard_ceiling_are_distinct";
assert(c.power_scale=="NPCC_benchmark_MW"&&abs(c.gross_ny_benchmark_load_mw-10902.2198)<1e-8 && ...
    c.load_evidence_class=="assumed_inherited_NPCC_benchmark");
names(end+1)="benchmark_scale_is_not_contemporary_or_PERFORM_full_load";
assert(c.boundary_source=="matched_NPCC_benchmark_reference" && ...
    ~c.use_PERFORM_20_exchange_schedule_for_this_case && ~c.allow_boundary_slack_or_voltage_control);
names(end+1)="boundary_schedule_comes_from_matched_NPCC_reference";
assert(~c.allow_automatic_PERFORM_regional_expansion && ~c.allow_wholesale_PERFORM_operating_network_substitution && ...
    ~c.allow_dense_Kron_network_as_operating_backbone && c.preserve_historical_cases);
names(end+1)="source_expansion_is_focused_and_large_reference_remains_separate";
assert(isequal(c.parent_branch_rows_deactivated,[88;89;94;235;236]) && ...
    numel(unique(c.selected_source_branch_rows))==11 && ...
    numel(c.retained_parent_branch_rows)+numel(c.selected_source_branch_rows)==257);
names(end+1)="selected_corridors_and_five_retired_paths_are_explicit";
assert(isequal(c.generator_classes.record_count,[21;14]) && ...
    sum(c.generator_classes.record_count)==35 && ~any(c.generator_classes.physical_machine_capability_verified) && ...
    c.generator_capability_source=="inherited_S7_benchmark_including_existing_S4_changes" && ...
    isequal(c.generator_classes.inherited_S7_pmax_total_mw,[7992.895;9200]));
names(end+1)="35_generator_records_do_not_claim35_physical_machines";
assert(~any(c.asset_classes.thermal_eligible)&&~c.thermal_model_implemented&&~c.dlr_ready && ...
    ~c.electrical_baseline_qualified&&~c.allow_synthetic_observations&&~c.release_ready);
names(end+1)="electrical_declaration_never_grants_thermal_or_observation_status";

% Structural policy is independent of a model's supplied success flag.
m=struct('bus',[(37:82)';9001;9002;9003;858;774], ...
    'success',true,'electrical_baseline_qualified',true,'dlr_ready',true);
v=compact_npcc_model_contract(m);
assert(v.structure_checked&&v.checked_operating_bus_count==51&&~v.electrical_baseline_qualified&&~v.dlr_ready);
names(end+1)="candidate_success_flags_cannot_qualify_the_contract";
limit=m;limit.bus=[(37:82)';(1001:1154)'];v=compact_npcc_model_contract(limit);
assert(v.structure_checked&&v.checked_operating_bus_count==200);
names(end+1)="hard_ceiling_accepts200_without_forcing_exact51";
over=limit;over.bus(end+1)=1155;
reject(@()compact_npcc_model_contract(over),'compact_npcc_model_contract:BusLimit');
names(end+1)="201_bus_case_is_rejected";
missing=m;missing.bus(1)=9876;
reject(@()compact_npcc_model_contract(missing),'compact_npcc_model_contract:OriginalNYBuses');
names(end+1)="missing_original_NPCC_NY_bus_is_rejected";
duplicate=m;duplicate.bus(end)=duplicate.bus(end-1);
reject(@()compact_npcc_model_contract(duplicate),'compact_npcc_model_contract:BusIdentity');
names(end+1)="duplicate_candidate_bus_ID_is_rejected";
invalid=m;invalid.bus(end)=NaN;
reject(@()compact_npcc_model_contract(invalid),'compact_npcc_model_contract:BusIdentity');
names(end+1)="nonfinite_candidate_bus_ID_is_rejected";

% The standalone compact contract must not rewrite the older model semantics.
historical=research_model_contract('historical_actual_mw');
assert(historical.power_scale=="actual_mw" && ~historical.fixed_bus_count_required && ...
    historical.operating_network=="ny_only_explicit_boundary_injections");
names(end+1)="historical_research_contract_semantics_preserved";
report=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});
end

function reject(f,id)
try,f();catch e,assert(strcmp(e.identifier,id),'Unexpected rejection %s',e.identifier);return;end
error('test_compact_npcc_model_contract:MissedGuard','Expected rejection %s',id);
end
