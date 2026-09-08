function tests=test_compact_ny_2025_replay(folder)
%TEST_COMPACT_NY_2025_REPLAY Source, physics and leakage mutation regressions.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));addpath(root);
if nargin<1,folder=fullfile(root,'output','compact_ny_2025','electrical_fixed_peak');end
temp=tempname;mkdir(temp);cleanup=onCleanup(@()remove_fixture(temp)); %#ok<NASGU>
file=fullfile(temp,'compact_ny_2025_electrical_campaign.mat');
copyfile(fullfile(folder,'compact_ny_2025_electrical_campaign.mat'),file);
copyfile(fullfile(folder,'electrical_campaign_manifest.csv'),temp);
d=load(file,'out');saved=d.out;
nominal=replay_compact_ny_2025_electrical(temp);
assert(nominal.passed&&all(nominal.records.passed)&&~nominal.optimizer_called&&~nominal.heldout_targets_used&&~nominal.dlr_ready);
names="nominal_source_rebuild_and_13_fixed_input_PFs";
out=saved;out.cases{1}.result.bus(1,3)=out.cases{1}.result.bus(1,3)+1;save(file,'out','-v7');
expect(temp,'compact_replay:Fingerprint');names(end+1)="stale_artifact_fingerprint";
fixtures=["qualification","code_manifest","solver_protocol","public_load","build_branch", ...
    "training_participation","heldout_accounting","heldout_fit_flag","false_stored_flow", ...
    "capability","unregistered_extension","HQ_overlap"];
ids=["Unqualified","CodeManifest","SolverProtocol","PublicInputs","Build", ...
    "TrainingRule","SnapshotAccounting","TargetLeakage","SavedPhysics", ...
    "Hardware","CustomInputs","HQSensitivity"];
held=find(saved.inputs.snapshots.vintage==2025&saved.inputs.snapshots.dataset_split=="heldout",1);
for k=1:numel(fixtures)
    out=saved;
    switch fixtures(k)
        case "qualification",out.electrical_baseline_qualified=false;
        case "code_manifest",out.code_manifest.sha256_lf_normalized(1)="tampered";
        case "solver_protocol",out.solver_protocol.opf_violation=1;
        case "public_load",out.inputs.loads.target_load_mw(1)=out.inputs.loads.target_load_mw(1)+1;
        case "build_branch",out.modern_build.candidate.branch(1,4)=out.modern_build.candidate.branch(1,4)+.001;
        case "training_participation",out.training_generation_participation(1)=out.training_generation_participation(1)+.01;
        case "heldout_accounting",out.cases{held}.snapshot.Pg_prior_mw(1)=out.cases{held}.snapshot.Pg_prior_mw(1)+10;
        case "heldout_fit_flag",out.cases{held}.internal_interface_fit_used=true;
        case "false_stored_flow",out.cases{1}.result.branch(1,14)=out.cases{1}.result.branch(1,14)+1;
        case "capability",out.cases{1}.result.gen(1,9)=out.cases{1}.result.gen(1,9)+1;
        case "unregistered_extension",out.cases{1}.result.A=sparse(1,1);
        case "HQ_overlap",out.hq_sensitivity.snapshot.boundary_register.p_injection_mw(1)= ...
                out.hq_sensitivity.snapshot.boundary_register.p_injection_mw(1)+100;
    end
    save(file,'out','-v7');refresh(file,temp);expect(temp,"compact_replay:"+ids(k));names(end+1)=fixtures(k); %#ok<AGROW>
end
tests=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});disp(tests);
end
function expect(folder,id)
caught="";try,replay_compact_ny_2025_electrical(folder);catch err,caught=string(err.identifier);end
assert(caught==string(id),'compact_replay_test:ExpectedGuard','Expected %s, received %s.',id,caught);
end
function refresh(file,folder)
t=table("compact_ny_2025_electrical_campaign.mat",ny_reference_file_sha256(file),'VariableNames',{'artifact','sha256'});
ny_lite_writetable_lf(t,fullfile(folder,'electrical_campaign_manifest.csv'));
end
function remove_fixture(folder)
p=char(java.io.File(folder).getCanonicalPath());r=char(java.io.File(tempdir).getCanonicalPath());
assert(startsWith(lower(p),[lower(r) filesep]));if isfolder(p),rmdir(p,'s');end
end
