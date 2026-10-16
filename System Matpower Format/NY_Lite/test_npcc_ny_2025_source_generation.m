function tests=test_npcc_ny_2025_source_generation
%TEST_NPCC_NY_2025_SOURCE_GENERATION Optional-loader guards and saved identity.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));addpath(fullfile(root,'System Matpower Format'));
names=strings(0,1);m=npcc_ny_2025_source_generation;
assert(isequal([size(m.bus,1),size(m.branch,1),size(m.gen,1)],[66,125,37]) ...
    &&nnz(m.branch(:,11)>0)==112&&all(ismember((37:82)',m.bus(:,1))));
names(end+1)="default_saved_case_has_exact_compact_inventory_and_original_NY_ids";
u=m.userdata.ny2025_source_generation;
assert(u.scenario_id=="S1_2025_SUMMER_PEAK_PUBLIC"&&u.electrical_baseline_qualified ...
    &&u.source_and_code_fingerprints_verified&&u.fresh_ac_replay_passed);
names(end+1)="successful_load_verifies_campaign_code_sources_and_fresh_AC_replay";
assert(u.generation_prior_source_estimated&&~u.observed_generator_dispatch_validated ...
    &&~u.observed_zonal_generation_validated&&~u.interface_calibrated&&~u.internal_interface_targets_used ...
    &&~u.exact_public_interface_operators&&~u.dlr_ready&&~u.all_registered_snapshots_electrically_qualified);
names(end+1)="estimated_generation_and_missing_campaign_coverage_are_not_overclaimed";
reject(@()npcc_ny_2025_source_generation("S1_2019_SUMMER_PEAK_PUBLIC"),'Scenario');
names(end+1)="historical_2019_scenario_rejected";
reject(@()npcc_ny_2025_source_generation("S5_2025_HIGH_TOTAL_EAST_PUBLIC"),'Qualification');
names(end+1)="boundary_incomplete_registered_S5_rejected";
reject(@()npcc_ny_2025_source_generation("missing_2025_scenario"),'Scenario');
names(end+1)="unknown_scenario_rejected";
reject(@()npcc_ny_2025_source_generation(""),'Scenario');
reject(@()npcc_ny_2025_source_generation(["S1_2025_SUMMER_PEAK_PUBLIC";"V4_2025_JUL25_NIGHT"]),'Scenario');
names(end+1)="empty_or_multiple_scenario_selection_rejected";
n=npcc_ny_2025_source_generation("V4_2025_JUL25_NIGHT");
assert(n.userdata.ny2025_source_generation.scenario_id=="V4_2025_JUL25_NIGHT" ...
    &&n.userdata.ny2025_source_generation.electrical_baseline_qualified ...
    &&~isequaln(n.gen(:,2),m.gen(:,2)));
names(end+1)="explicit_eligible_2025_selection_returns_its_own_saved_dispatch";
tests=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});disp(tests);
end
function reject(fn,suffix)
id="npcc_source_generation:"+suffix;
try,fn();catch e,assert(string(e.identifier)==id,'Unexpected error %s instead of %s.',e.identifier,id);return;end
error('npcc_source_generation_test:MissingGuard','Expected %s.',id);
end
