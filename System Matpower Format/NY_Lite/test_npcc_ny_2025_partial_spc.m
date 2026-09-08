function tests=test_npcc_ny_2025_partial_spc
%TEST_NPCC_NY_2025_PARTIAL_SPC Saved nominal variant and scope guards.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));addpath(fullfile(root,'System Matpower Format'));
names=strings(0,1);m=npcc_ny_2025_partial_spc;
u=m.userdata.ny2025_partial_spc;
assert(size(m.bus,1)==71&&size(m.gen,1)==37&&all(ismember((37:82)',m.bus(:,1))) ...
    &&u.variant_id=="nominal"&&u.scenario_id=="S1_2025_SUMMER_PEAK_PUBLIC");
names(end+1)="default_load_returns_registered_nominal_71_bus_37_generator_case";
assert(u.electrical_baseline_qualified&&u.parent_code_source_and_topology_verified&&u.fresh_ac_replay_passed);
names(end+1)="saved_campaign_and_new_topology_receive_independent_fresh_verification";
assert(u.approximate_infrastructure&&u.year_end_topology_counterfactual&&u.topology_as_of=="2025-12-31" ...
    &&~u.historical_as_operated_reconstruction&&~u.fresh_holdout_validation&&~u.dlr_ready ...
    &&~u.exact_public_interface_operators&&~u.internal_interface_targets_used&&u.source_prior_vectors_unchanged);
names(end+1)="approximation_counterfactual_and_unqualified_DLR_scope_preserved";
reject(@()npcc_ny_2025_partial_spc("S1_2019_SUMMER_PEAK_PUBLIC"),'Scenario');
reject(@()npcc_ny_2025_partial_spc("S5_2025_HIGH_TOTAL_EAST_PUBLIC"),'Scenario');
names(end+1)="historical_and_skipped_operating_hours_are_not_exposed";
reject(@()npcc_ny_2025_partial_spc("impedance_075"),'Scenario');
reject(@()npcc_ny_2025_partial_spc("missing_scenario"),'Scenario');
names(end+1)="sensitivity_or_unknown_selection_cannot_replace_nominal_topology";
reject(@()npcc_ny_2025_partial_spc(""),'Scenario');
reject(@()npcc_ny_2025_partial_spc(["S1_2025_SUMMER_PEAK_PUBLIC";"V4_2025_JUL25_NIGHT"]),'Scenario');
names(end+1)="empty_or_multiple_scenario_requests_rejected";
tests=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});disp(tests);
end
function reject(fn,suffix)
id="npcc_partial_spc:"+suffix;
try,fn();catch e,assert(string(e.identifier)==id,'Unexpected error %s instead of %s.',e.identifier,id);return;end
error('npcc_partial_spc_test:MissingGuard','Expected %s.',id);
end
