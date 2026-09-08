function [mpc,thermal]=npcc_ny_2025_synthetic_dlr(weather_scenario)
%NPCC_NY_2025_SYNTHETIC_DLR Saved consistent R(T), dispatch and thermal ledger.
% This is the66-bus selected-summer-snapshot experiment. It is not an as-built
% NYISO case; only23 explicit overhead realizations carry thermal meaning.
if nargin<1,weather_scenario="static_reference";end
root=fileparts(fileparts(mfilename('fullpath')));addpath(fullfile(root,'System Matpower Format','NY_Lite'));
file=fullfile(root,'output','compact_ny_2025','thermal','compact_ny_dlr_campaign.mat');
assert(isfile(file),'dlr:MissingArtifact','Run run_compact_ny_dlr_baseline first.');
manifest=readtable(fullfile(fileparts(file),'thermal_campaign_manifest.csv'),'TextType','string');
assert(height(manifest)==1&&manifest.sha256==string(ny_reference_file_sha256(file)), ...
    'dlr:Fingerprint','Saved thermal artifact fingerprint changed.');
d=load(file,'out');o=d.out;k=find(o.weather.scenario_id==string(weather_scenario));
assert(numel(k)==1,'dlr:WeatherScenario','Unknown saved weather experiment.');v=o.cases{k};
assert(o.research_thermal_baseline_qualified&&v.synthetic_electrothermal_qualified, ...
    'dlr:UnqualifiedArtifact','Saved synthetic thermal baseline failed qualification.');
assert(isequal(o.code_manifest,compact_dlr_code_manifest),'dlr:CodeChanged','Thermal code or reference fixtures changed; rebuild evidence.');
electrical_path=o.options.electrical_path;
if strlength(o.electrical_input_relative_path)>0,electrical_path=fullfile(root,o.electrical_input_relative_path);end
assert(strcmp(ny_reference_file_sha256(electrical_path),o.electrical_input_sha256), ...
    'dlr:StaleElectricalInput','Electrical reference changed; rebuild thermal evidence.');
electrical=audit_ny_ac_reference(v.result);assert(electrical.passed,'dlr:ElectricalAudit','Saved electrical state fails fresh physical audit.');
tests=test_dlr_operating_guards(v,o.realizations);assert(all(tests.passed));
mpc=v.result;thermal=struct('realizations',o.realizations,'weather',o.weather(k,:), ...
    'temperature_c',v.temperature_c,'ampacity_subconductor_amp',v.ampacity_subconductor_amp, ...
    'current_audit',v.current_audit,'thermal_audit',v.thermal_audit,'contract',compact_ny_dlr_research_contract);
end
