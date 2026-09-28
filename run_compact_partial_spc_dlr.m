function out=run_compact_partial_spc_dlr(options)
%RUN_COMPACT_PARTIAL_SPC_DLR Separate synthetic thermal campaign on source priors.
% Never changes or re-solves the frozen source electrical campaign. Earlier
% 2025 operating inputs stress a fixed year-end topology counterfactually.
if nargin<1,options=struct();end
root=fileparts(mfilename('fullpath'));addpath(fullfile(root,'System Matpower Format','NY_Lite'));
defaults=struct('electrical_path',fullfile(root,'output','compact_ny_2025','partial_spc','campaign.mat'), ...
    'output_dir',fullfile(root,'output','compact_ny_2025','partial_spc_thermal'),'run_tests',true);
assert(all(ismember(fieldnames(options),fieldnames(defaults))),'partial_spc_dlr:Options','Unknown option.');
for name=string(fieldnames(defaults))',if ~isfield(options,name),options.(name)=defaults.(name);end,end
assert(isscalar(options.run_tests)&&islogical(options.run_tests),'partial_spc_dlr:Options','run_tests must be logical.');
folder=char(options.output_dir);protect(folder,root);
assert(~isfile(fullfile(folder,'campaign.mat')),'partial_spc_dlr:FrozenOutput','Saved campaigns are not overwritten.');
electrical_path=char(options.electrical_path);ef=fileparts(electrical_path);
input_sha256=ny_reference_file_sha256(electrical_path);
input_manifest_sha256=ny_reference_file_sha256(fullfile(ef,'campaign_manifest.csv'));
em=readtable(fullfile(ef,'campaign_manifest.csv'),'TextType','string');
assert(height(em)==1&&em.artifact=="campaign.mat" ...
    &&input_sha256==em.sha256,'partial_spc_dlr:ElectricalInput','Electrical manifest failed.');
d=load(electrical_path,'out');e=d.out;c=compact_partial_spc_dlr_contract;
assert(e.electrical_baseline_qualified&&all(e.case_summary.electrically_qualified) ...
    &&~e.internal_interface_targets_used&&~e.interface_parameters_fitted, ...
    'partial_spc_dlr:ElectricalInput','All registered electrical cases must qualify with target-free controls.');
electrical_replay=replay_compact_2025_partial_spc(ef);
assert(electrical_replay.passed,'partial_spc_dlr:ElectricalInput','Independent electrical reconstruction failed.');
j=find(e.case_summary.variant_id==c.electrical_variant_id&e.case_summary.scenario_id==c.electrical_scenario_id);
assert(isscalar(j),'partial_spc_dlr:ElectricalInput','Expected exactly one nominal S1 electrical case.');
fit=e.cases{j};assert(fit.electrical_baseline_qualified);
pd=load(fullfile(root,e.parent_relative_path),'out');vi=find(e.variants.variant_id==c.electrical_variant_id);assert(isscalar(vi));
fresh_build=apply_compact_2025_partial_spc(pd.out.modern_build,table2struct(e.variants(vi,2:end)));
selection=compact_partial_spc_dlr_selection(fresh_build,fit.snapshot);
realizations=build_dlr_corridor_realizations(fit.result,selection);
assert(all(realizations.research_thermal_eligible)&~any(realizations.length_requires_review), ...
    'partial_spc_dlr:Realization','An overhead surrogate requires unresolved length review.');
lib=dlr_conductor_library;weather=c.weather;tests=table();
if options.run_tests
    tests=[test_compact_partial_spc_dlr(fresh_build,fit.snapshot);test_dlr_thermal_model; ...
        test_dlr_electrical_consistency;test_dlr_series_constraint;test_dlr_operating_guards];
    assert(all(tests.passed),'partial_spc_dlr:Tests','Preflight physics tests failed.');
end
[code,runtime]=compact_partial_spc_dlr_code_manifest;
if ~isfolder(folder),mkdir(folder);end
ratings=table();cases=cell(height(weather),1);summary=table();
for k=1:height(weather)
    amps=zeros(height(realizations),1);[ok,li]=ismember(realizations.conductor_code,lib.conductor_code);assert(all(ok));
    for n=1:numel(amps),a=dlr_steady_ampacity(lib(li(n),:),weather(k,:));amps(n)=a.ampacity_amp;end
    eq_mva=amps.*realizations.circuits.*realizations.bundle_count.*sqrt(3).*realizations.base_kv/1000;
    t=table(repmat(weather.scenario_id(k),numel(amps),1),realizations.branch_key,amps,eq_mva, ...
        realizations.equipment_limit_mva,min(eq_mva,realizations.equipment_limit_mva), ...
        'VariableNames',{'weather_scenario','branch_key','subconductor_ampacity_amp','series_ampacity_at_nominal_kv_mva', ...
        'assumed_equipment_limit_mva','nominal_display_limit_mva'});
    t.nominal_MVA_is_not_the_enforced_series_constraint=true(height(t),1);ratings=[ratings;t]; %#ok<AGROW>
    v=solve_dlr_steady_operating_point(fit.result,realizations,weather(k,:));cases{k}=v;
    maxheat=NaN;identity=NaN;fraction=NaN;maxtemp=NaN;
    if ~isempty(v.thermal_audit),maxheat=max(abs(v.thermal_audit.heat_residual_w_m));maxtemp=max(v.temperature_c);end
    if ~isempty(v.current_audit)
        identity=max(v.current_audit.heating_identity_error_mw);fraction=max(v.current_audit.subconductor_current_amp./amps);
    end
    summary=[summary;table(weather.scenario_id(k),v.synthetic_electrothermal_qualified, ...
        v.independent_PF_pass,height(v.iterations),maxtemp,maxheat,identity,fraction,v.dispatch_L1_change_mw,v.solver_error, ...
        'VariableNames',{'weather_scenario','synthetic_electrothermal_qualified','independent_PF_pass','iterations', ...
        'max_conductor_temperature_c','max_heat_residual_w_m','max_Joule_identity_error_mw','max_ampacity_fraction', ...
        'dispatch_L1_change_from_source_electrical_reference_mw','solver_error'})]; %#ok<AGROW>
    sf=fullfile(folder,char(weather.scenario_id(k)));if ~isfolder(sf),mkdir(sf);end
    save(fullfile(sf,'electrothermal_evidence.mat'),'v','-v7');write(sf,'iterations',v.iterations);
    write(sf,'series_current_audit',v.current_audit);write(sf,'steady_heat_audit',v.thermal_audit);
    if ~isempty(v.replay_audit),write(sf,'electrical_audit',v.replay_audit.summary);end
    if options.run_tests&&v.synthetic_electrothermal_qualified
        checked=test_dlr_operating_guards(v,realizations);
        checked.test=weather.scenario_id(k)+":"+checked.test;tests=[tests;checked]; %#ok<AGROW>
    end
    fprintf('%s partial-SPC synthetic_qualified=%d maxT=%.3fC\n',weather.scenario_id(k),v.synthetic_electrothermal_qualified,maxtemp);
end
[final_code,final_runtime]=compact_partial_spc_dlr_code_manifest;
assert(isequal(code,final_code)&&isequal(runtime,final_runtime),'partial_spc_dlr:Code','Code changed while solving.');
assert(ny_reference_file_sha256(electrical_path)==input_sha256 ...
    &&ny_reference_file_sha256(fullfile(ef,'campaign_manifest.csv'))==input_manifest_sha256, ...
    'partial_spc_dlr:ElectricalInput','Electrical source bytes changed while solving.');
final_electrical_replay=replay_compact_2025_partial_spc(ef);
final_build=apply_compact_2025_partial_spc(pd.out.modern_build,table2struct(e.variants(vi,2:end)));
assert(final_electrical_replay.passed&&isequaln(final_build.partial_spc_source_manifest,fresh_build.partial_spc_source_manifest), ...
    'partial_spc_dlr:ElectricalInput','Electrical code, source tables or infrastructure provenance changed while solving.');
relative=relative_input(electrical_path,root);
source_fingerprints=table([relative;replace(string(fullfile(fileparts(relative),'campaign_manifest.csv')),"\","/")], ...
    [input_sha256;input_manifest_sha256], ...
    'VariableNames',{'relative_path','sha256'});
out=struct('realizations',realizations,'selection',selection,'conductors',lib,'weather',weather, ...
    'ratings',ratings,'cases',{cases},'summary',summary,'tests',tests,'contract',c, ...
    'electrical_scenario_id',c.electrical_scenario_id,'electrical_variant_id',c.electrical_variant_id, ...
    'electrical_input_relative_path',relative,'electrical_input_sha256',input_sha256, ...
    'electrical_source_fingerprints',source_fingerprints,'electrical_replay',electrical_replay, ...
    'electrical_source_manifest',e.source_manifest,'electrical_code_manifest',e.code_manifest, ...
    'infrastructure_source_manifest',fresh_build.partial_spc_source_manifest, ...
    'electrical_all_registered_cases_qualified',all(e.case_summary.electrically_qualified), ...
    'research_thermal_baseline_qualified',options.run_tests&&all(tests.passed)&&all(summary.synthetic_electrothermal_qualified), ...
    'physical_conductor_verified',false,'weather_observed',false,'observed_generator_dispatch_validated',false, ...
    'thermal_dispatch_policy',"finite_P_Q_movement_penalties_centered_on_source_prior_electrical_solution_no_interface_fit", ...
    'interface_targets_used',false,'fresh_holdout_validation',false,'historical_as_operated_reconstruction',false, ...
    'scope',c.scope,'options',options,'code_manifest',code,'runtime_manifest',runtime, ...
    'reference_electrical_case',fit.result,'reference_branch_keys',fit.snapshot.branch_keys, ...
    'reference_generator_keys',fit.snapshot.generator_keys);
save(fullfile(folder,'campaign.mat'),'out','-v7');
write(folder,'campaign_manifest',table("campaign.mat",ny_reference_file_sha256(fullfile(folder,'campaign.mat')), ...
    'VariableNames',{'artifact','sha256'}));
for name=["code_manifest","runtime_manifest","electrical_source_fingerprints","electrical_source_manifest", ...
        "electrical_code_manifest","infrastructure_source_manifest","selection","realizations","conductors", ...
        "weather","ratings","summary","tests"]
    write(folder,name,out.(name));
end
end
function p=relative_input(file,root)
f=string(char(java.io.File(file).getCanonicalPath()));r=string(char(java.io.File(root).getCanonicalPath()));
assert(startsWith(lower(f),lower(r+filesep)),'partial_spc_dlr:ElectricalInput','Portable input must reside inside this repository.');
p=replace(extractAfter(f,strlength(r)+1),"\","/");
end
function protect(folder,root)
p=lower(string(char(java.io.File(folder).getCanonicalPath())));
a=lower(string(char(java.io.File(fullfile(root,'output','compact_ny_2025','partial_spc_thermal')).getCanonicalPath())));
s=lower(string(char(java.io.File(fullfile(root,'tmp','partial_spc_thermal')).getCanonicalPath())));
assert(p==a||startsWith(p,a+filesep)||p==s||startsWith(p,s+filesep), ...
    'partial_spc_dlr:ProtectedOutput','Output must stay in the dedicated partial-SPC thermal output or scratch folder.');
end
function write(folder,name,t)
if istable(t)&&~isempty(t.Properties.VariableNames),ny_lite_writetable_lf(t,fullfile(folder,string(name)+".csv"));end
end
