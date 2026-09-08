function tests=test_npcc_ny_2025_partial_spc_dlr
%TEST_NPCC_NY_2025_PARTIAL_SPC_DLR Saved-case identity and weather/scope guards.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));addpath(fullfile(root,'System Matpower Format'));
names=strings(0,1);[m,t]=npcc_ny_2025_partial_spc_dlr;
assert(size(m.bus,1)==71&&size(m.gen,1)==37&&height(t.realizations)==25 ...
    &&t.weather.scenario_id=="static_reference"&&all(ismember((37:82)',m.bus(:,1))));
names(end+1)="default_saved_71_bus_case_has_25_explicit_thermal_realizations";
assert(isequal(t.contract,compact_partial_spc_dlr_contract)&&t.fresh_replay.passed ...
    &&t.research_thermal_baseline_qualified&&t.synthetic_electrothermal_qualified);
names(end+1)="successful_load_preserves_contract_and_verifies_full_fresh_source_AC_heat_chain";
u=m.userdata.ny2025_partial_spc_dlr;
assert(u.year_end_topology_counterfactual&&u.approximate_infrastructure&&~u.weather_observed ...
    &&~u.physical_conductor_verified&&~u.as_built_network_validated&&~u.historical_as_operated_reconstruction ...
    &&~u.fresh_holdout_validation&&~u.exact_public_interface_operators&&~u.dlr_ready);
names(end+1)="synthetic_qualification_does_not_claim_observed_or_as_built_operation";
current=dlr_series_current_audit(m,t.realizations,t.temperature_c);
assert(max(current.heating_identity_error_mw)<1e-8&&all(t.thermal_audit.passed) ...
    &&max(abs(current.subconductor_current_amp-t.current_audit.subconductor_current_amp))<1e-8);
names(end+1)="returned_R_temperature_and_current_ledger_are_physically_consistent";
reject(@()npcc_ny_2025_partial_spc_dlr("unknown_weather"));
names(end+1)="unknown_weather_rejected";
reject(@()npcc_ny_2025_partial_spc_dlr(""));
reject(@()npcc_ny_2025_partial_spc_dlr(["static_reference";"hot_low_wind"]));
names(end+1)="empty_or_multiple_weather_selection_rejected";
[n,v]=npcc_ny_2025_partial_spc_dlr("hot_low_wind");
assert(v.weather.scenario_id=="hot_low_wind"&&n.userdata.ny2025_partial_spc_dlr.weather_scenario=="hot_low_wind" ...
    &&~isequaln(v.temperature_c,t.temperature_c)&&v.fresh_replay.passed);
names(end+1)="explicit_weather_returns_its_own_saved_dispatch_and_temperature";
tests=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});disp(tests);
end
function reject(fn)
id="npcc_partial_spc_dlr:WeatherScenario";
try,fn();catch e,assert(string(e.identifier)==id,'Unexpected error %s instead of %s.',e.identifier,id);return;end
error('npcc_partial_spc_dlr_test:MissingGuard','Expected %s.',id);
end
