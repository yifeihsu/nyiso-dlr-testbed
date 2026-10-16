function out=run_compact_ny_dlr_baseline(options)
%RUN_COMPACT_NY_DLR_BASELINE Assumed-conductor research baseline and stresses.
% Reuses the saved matched electrical campaign; rebuild that first if absent.
% Outputs do not overwrite the electrical snapshots or historical packages.
if nargin<1,options=struct();end
root=fileparts(mfilename('fullpath'));addpath(fullfile(root,'System Matpower Format','NY_Lite'));
if ~isfield(options,'electrical_path'),options.electrical_path=fullfile(root,'output','compact_ny_2025','electrical_fixed_peak','compact_ny_2025_electrical_campaign.mat');end
if ~isfield(options,'output_dir'),options.output_dir=fullfile(root,'output','compact_ny_2025','thermal');end
if ~isfield(options,'run_tests'),options.run_tests=true;end
assert(isfile(options.electrical_path),'dlr:ElectricalInput','Run the matched electrical campaign first.');
d=load(options.electrical_path,'out');electrical=d.out;
assert(electrical.electrical_baseline_qualified,'dlr:ElectricalInput','Electrical campaign has not passed its bounded audits.');
j=find(electrical.inputs.snapshots.scenario_id=="S1_2025_SUMMER_PEAK_PUBLIC");fit=electrical.cases{j};
selection=compact_dlr_selection(electrical.modern_build,fit.snapshot);
realizations=build_dlr_corridor_realizations(fit.result,selection);lib=dlr_conductor_library;
tests=table();
if options.run_tests
    tests=[test_dlr_thermal_model;test_dlr_electrical_consistency;test_dlr_series_constraint;test_dlr_operating_guards];
    assert(all(tests.passed));
end
folder=options.output_dir;assert_safe_folder(folder,root);
if ~isfolder(folder),mkdir(folder);end
weather=table(["static_reference";"windy_mild";"hot_low_wind";"cool_windy"], ...
    [40;25;40;5],[.61;2;.2;1],[90;90;0;90],[1000;800;1000;100],repmat(101325,4,1), ...
    false(4,1),'VariableNames',{'scenario_id','ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa','observed_weather'});
% Limits are recalculated from physics, never fitted to RATE_A or dispatch.
ratings=table();cases=cell(height(weather),1);summary=table();
for k=1:height(weather)
    amps=zeros(height(realizations),1);[~,li]=ismember(realizations.conductor_code,lib.conductor_code);
    for n=1:numel(amps),a=dlr_steady_ampacity(lib(li(n),:),weather(k,:));amps(n)=a.ampacity_amp;end
    eq_mva=amps.*realizations.circuits.*realizations.bundle_count.*sqrt(3).*realizations.base_kv/1000;
    t=table(repmat(weather.scenario_id(k),numel(amps),1),realizations.branch_key,amps,eq_mva, ...
        realizations.equipment_limit_mva,min(eq_mva,realizations.equipment_limit_mva), ...
        'VariableNames',{'weather_scenario','branch_key','subconductor_ampacity_amp','series_ampacity_at_nominal_kv_mva', ...
        'assumed_equipment_limit_mva','nominal_display_limit_mva'});
    t.nominal_MVA_is_not_the_enforced_series_constraint=true(height(t),1);ratings=[ratings;t]; %#ok<AGROW>
    v=solve_dlr_steady_operating_point(fit.result,realizations,weather(k,:));cases{k}=v;
    maxheat=nan;identity=nan;fraction=nan;maxtemp=nan;
    if ~isempty(v.thermal_audit),maxheat=max(abs(v.thermal_audit.heat_residual_w_m));maxtemp=max(v.temperature_c);end
    if ~isempty(v.current_audit)
        identity=max(v.current_audit.heating_identity_error_mw);fraction=max(v.current_audit.subconductor_current_amp./amps);
    end
    summary=[summary;table(weather.scenario_id(k),v.synthetic_electrothermal_qualified, ...
        v.independent_PF_pass,height(v.iterations),maxtemp,maxheat,identity,fraction,v.dispatch_L1_change_mw,v.solver_error, ...
        'VariableNames',{'weather_scenario','synthetic_electrothermal_qualified','independent_PF_pass','iterations', ...
        'max_conductor_temperature_c','max_heat_residual_w_m','max_Joule_identity_error_mw','max_ampacity_fraction', ...
        'dispatch_L1_change_from_electrical_fit_mw','solver_error'})]; %#ok<AGROW>
    sf=fullfile(folder,char(weather.scenario_id(k)));if ~isfolder(sf),mkdir(sf);end
    save(fullfile(sf,'electrothermal_evidence.mat'),'v','-v7');write(sf,'iterations',v.iterations);
    write(sf,'series_current_audit',v.current_audit);write(sf,'steady_heat_audit',v.thermal_audit);
    if ~isempty(v.replay_audit),write(sf,'electrical_audit',v.replay_audit.summary);end
    fprintf('%s synthetic_qualified=%d maxT=%.3fC\n',weather.scenario_id(k),v.synthetic_electrothermal_qualified,maxtemp);
end
if options.run_tests
    for k=1:numel(cases)
        if cases{k}.synthetic_electrothermal_qualified
            checked=test_dlr_operating_guards(cases{k},realizations);
            checked.test=weather.scenario_id(k)+":"+checked.test;tests=[tests;checked]; %#ok<AGROW>
        end
    end
end
% Prescribed-current mismatch experiment isolates weather forecast error.
% It is not a coupled network time simulation or an observed NY weather day.
c=lib(lib.conductor_code=="CARDINAL_954_ACSR",:);a=dlr_steady_ampacity(c,weather(2,:));
times=(0:60:3600)';currents=repmat(.9*a.ampacity_amp,numel(times),1);
forecast=repmat(weather(2,:),numel(times),1);actual=forecast;
actual(times>=1200,:)=repmat(weather(3,:),nnz(times>=1200),1);
tf=dlr_temperature_trace(times,currents,forecast,c,25);ta=dlr_temperature_trace(times,currents,actual,c,25);
transient=table(times,currents,tf.temperature_c,ta.temperature_c, ...
    actual.ambient_c,actual.wind_m_s,actual.wind_angle_deg,actual.solar_w_m2,ta.temperature_c>75, ...
    'VariableNames',{'time_s','prescribed_subconductor_current_amp','forecast_temperature_c','actual_scenario_temperature_c', ...
    'actual_ambient_c','actual_wind_m_s','actual_wind_angle_deg','actual_solar_w_m2','above_assumed_limit'});
out=struct('realizations',realizations,'selection',selection,'conductors',lib,'weather',weather, ...
    'ratings',ratings,'cases',{cases},'summary',summary,'tests',tests,'transient',transient, ...
    'electrical_scenario_id',fit.snapshot.scenario_id,'electrical_input_sha256',ny_reference_file_sha256(options.electrical_path), ...
    'research_thermal_baseline_qualified',options.run_tests&&all(tests.passed)&&all(summary.synthetic_electrothermal_qualified), ...
    'physical_conductor_verified',false,'weather_observed',false,'observed_generator_dispatch_validated',false, ...
    'scope',"23_explicit_synthetic_overhead_realizations_on66bus_NPCC_derived2025_snapshot",'options',options, ...
    'code_manifest',compact_dlr_code_manifest,'reference_electrical_case',fit.result, ...
    'electrical_input_relative_path',"output/compact_ny_2025/electrical_fixed_peak/compact_ny_2025_electrical_campaign.mat");
% Save a portable project-relative pointer when it identifies the actual input.
if ~strcmp(ny_reference_file_sha256(fullfile(root,out.electrical_input_relative_path)),out.electrical_input_sha256)
    out.electrical_input_relative_path="";
end
save(fullfile(folder,'compact_ny_dlr_campaign.mat'),'out','-v7');
manifest=table("compact_ny_dlr_campaign.mat",string(ny_reference_file_sha256(fullfile(folder,'compact_ny_dlr_campaign.mat'))), ...
    'VariableNames',{'artifact','sha256'});write(folder,'thermal_campaign_manifest',manifest);
write(folder,'thermal_code_manifest',out.code_manifest);
write(folder,'conductor_library',lib);write(folder,'corridor_realizations',realizations);write(folder,'weather_scenarios',weather);
write(folder,'rating_comparison',ratings);write(folder,'operating_summary',summary);write(folder,'implementation_tests',tests);
write(folder,'weather_mismatch_transient',transient);
end
function write(folder,name,t)
if istable(t),ny_lite_writetable_lf(t,fullfile(folder,string(name)+".csv"));end
end
function assert_safe_folder(folder,root)
p=lower(string(java.io.File(folder).getCanonicalPath()));
for name=["ny_only_package_a","ny_only_package_b","compact_npcc_ny","compact_ny_2025/electrical","compact_ny_2025/electrical_fixed_peak","compact_ny_2025/electrical_constant_total_diagnostic"]
    r=lower(string(java.io.File(fullfile(root,'output',name)).getCanonicalPath()));
    assert(p~=r&&~startsWith(p,r+filesep)&&~startsWith(r,p+filesep),'dlr:ProtectedOutput','Electrical and historical outputs are protected.');
end
end
