function out=test_compact_npcc_ny_replay(input_folder)
%TEST_COMPACT_NPCC_NY_REPLAY Actual frozen-case replay and mutation guards.
% Hash-refresh fixtures must still fail independent construction/accounting.
% Requires a qualified artifact, and never invokes an optimizer.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));addpath(root);
if nargin<1,input_folder=fullfile(root,'output','compact_npcc_ny');end
folder=tempname;mkdir(folder);cleanup=onCleanup(@()remove_fixture(folder)); %#ok<NASGU>
copyfile(fullfile(input_folder,'compact_npcc_ny_reference.mat'),folder);
copyfile(fullfile(input_folder,'compact_input_manifest.csv'),folder);
file=fullfile(folder,'compact_npcc_ny_reference.mat');saved=load(file);
nominal=replay_compact_npcc_ny_testbed(folder);
assert(nominal.passed&&nominal.full_reference_replay_passed&&nominal.source_accounting_verified ...
    && nominal.frozen_hardware_verified&&nominal.fresh_pf_hardware_verified ...
    && nominal.boundary_accounting_verified&&nominal.model_contract.structure_checked ...
    && ~nominal.optimizer_called&&~nominal.package_a_dependency&&~nominal.dlr_ready);
names="nominal_source_rebuild_full_PF_and_NY_PF";
changed=saved;changed.mpc.bus(1,3)=changed.mpc.bus(1,3)+1;
save(file,'-struct','changed');expect_failure(folder,'InputFingerprint');
names(end+1)="unrefreshed_frozen_input_hash";
fixtures=["qualification_flag";"source_manifest";"source_branch_identity"; ...
    "saved_build_hardware";"full_reference_capability";"full_reference_false_flow"; ...
    "boundary_ledger";"NY_hardware";"NY_dispatch_drift";"unregistered_electrical_extension"];
expected=["Unqualified";"SourceManifest";"SourceAccounting";"FrozenBuild"; ...
    "FullHardware";"FullReference";"BoundaryAccounting";"NYHardware"; ...
    "NYOperatingState";"NYHardware"];
for k=1:numel(fixtures)
    changed=saved;
    switch fixtures(k)
        case "qualification_flag",changed.expected_qualified=false;
        case "source_manifest",changed.source_manifest.sha256_lf_normalized(1)="tampered";
        case "source_branch_identity"
            changed.build.source_branch_map.device_key(1)="UNREGISTERED_CIRCUIT";
            changed.build.physical_branch_register=changed.build.source_branch_map;
        case "saved_build_hardware"
            changed.build.candidate.branch(end,4)=changed.build.candidate.branch(end,4)+.001;
            changed.build.full_candidate=changed.build.candidate;
        case "full_reference_capability",changed.full_reference.gen(1,4)=changed.full_reference.gen(1,4)+1;
        case "full_reference_false_flow"
            at=find(changed.full_reference.branch(:,11)>0,1);
            changed.full_reference.branch(at,14)=changed.full_reference.branch(at,14)+1;
        case "boundary_ledger"
            changed.assembly.boundary_register.p_injection_mw(1)= ...
                changed.assembly.boundary_register.p_injection_mw(1)+1;
        case "NY_hardware",changed.mpc.bus(1,3)=changed.mpc.bus(1,3)+1;
        case "NY_dispatch_drift"
            ref=changed.mpc.bus(changed.mpc.bus(:,2)==3,1);
            at=find(changed.mpc.gen(:,1)==ref&changed.mpc.gen(:,8)>0,1);
            changed.mpc.gen(at,2)=changed.mpc.gen(at,2)+.1;
        case "unregistered_electrical_extension",changed.mpc.dcline=zeros(0,23);
    end
    save(file,'-struct','changed');refresh_manifest(folder,file);
    expect_failure(folder,expected(k));names(end+1)=fixtures(k); %#ok<AGROW>
end
out=struct('pass',true,'assertion_groups',numel(names), ...
    'gates',table(names(:),true(numel(names),1),'VariableNames',{'test','passed'}), ...
    'independent_fresh_pf_pass',nominal.passed, ...
    'full_reference_replay_passed',nominal.full_reference_replay_passed, ...
    'max_fresh_P_adjustment_mw',nominal.max_dispatch_adjustment_mw, ...
    'max_fresh_voltage_adjustment_pu',nominal.max_voltage_adjustment_pu, ...
    'full_max_fresh_P_adjustment_mw',nominal.full_max_dispatch_adjustment_mw, ...
    'full_max_fresh_voltage_adjustment_pu',nominal.full_max_voltage_adjustment_pu, ...
    'reconstruction_performed',false,'optimizer_called',false);
disp(out.gates);
end

function expect_failure(folder,id)
expected=['replay_compact_npcc_ny_testbed:' char(id)];
try,replay_compact_npcc_ny_testbed(folder);
catch err
    assert(strcmp(err.identifier,expected),'test_compact_npcc_ny_replay:WrongFailure', ...
        'Expected %s, received %s: %s',expected,err.identifier,err.message);return
end
error('test_compact_npcc_ny_replay:MissingFailure','Expected %s.',expected);
end

function refresh_manifest(folder,file)
manifest=table("compact_npcc_ny_reference.mat",ny_reference_file_sha256(file), ...
    'VariableNames',{'artifact','sha256'});
ny_lite_writetable_lf(manifest,fullfile(folder,'compact_input_manifest.csv'));
end

function remove_fixture(folder)
base=char(java.io.File(tempdir).getCanonicalPath());
resolved=char(java.io.File(folder).getCanonicalPath());
assert(startsWith(resolved,[base filesep])&&~strcmp(resolved,base), ...
    'test_compact_npcc_ny_replay:Cleanup','Refusing cleanup outside tempdir.');
if isfolder(resolved),rmdir(resolved,'s');end
end
