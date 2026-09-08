function mpc=npcc_ny_2025_dlr_research(scenario_id)
%NPCC_NY_2025_DLR_RESEARCH Frozen66-bus approximate2025 electrical research case.
% Default is calibrated2025summerpeak; optional ID selects another2025 hour.
% Loading checks frozen artifact/code fingerprints and selected physical AC
% state. Full source rebuild and fresh replay: replay_compact_ny_2025_electrical.
% Electrical calibration is separate from thermal/DLR qualification.
if nargin<1,scenario_id="S1_2025_SUMMER_PEAK_PUBLIC";end
root=fileparts(fileparts(mfilename('fullpath')));addpath(fullfile(root,'System Matpower Format','NY_Lite'));
folder=fullfile(root,'output','compact_ny_2025','electrical_fixed_peak');
file=fullfile(folder,'compact_ny_2025_electrical_campaign.mat');
manifest=readtable(fullfile(folder,'electrical_campaign_manifest.csv'),'TextType','string');
assert(height(manifest)==1&&manifest.artifact=="compact_ny_2025_electrical_campaign.mat"&& ...
    manifest.sha256==ny_reference_file_sha256(file),'npcc_ny_2025:Fingerprint','Frozen campaign fingerprint changed.');
d=load(file,'out');o=d.out;
assert(o.electrical_baseline_qualified&&isequal(o.code_manifest,compact_ny_2025_code_manifest), ...
    'npcc_ny_2025:Qualification','Saved electrical case or executable provenance is unqualified.');
k=find(o.inputs.snapshots.scenario_id==string(scenario_id)&o.inputs.snapshots.vintage==2025);
assert(isscalar(k),'npcc_ny_2025:Scenario','Select one registered2025 scenario.');
c=o.cases{k};assert(c.electrical_baseline_qualified,'npcc_ny_2025:Qualification','Selected case is unqualified.');
mpc=c.result;a=audit_ny_ac_reference(mpc,struct('generator_keys',c.snapshot.generator_keys,'branch_keys',c.snapshot.branch_keys));
assert(a.passed&&size(mpc.bus,1)<=200&&all(ismember((37:82)',mpc.bus(:,1))),'npcc_ny_2025:Physics','Physical limits or compact identity failed.');
mpc.userdata.ny2025_research=struct('scenario_id',string(scenario_id),'electrical_baseline_qualified',true, ...
    'interface_calibrated',c.internal_interface_fit_used,'heldout_prediction',~c.internal_interface_fit_used, ...
    'observed_generator_dispatch_validated',false,'exact_public_interface_operators',false, ...
    'thermal_validation_separate',true,'dlr_ready',false);
end
