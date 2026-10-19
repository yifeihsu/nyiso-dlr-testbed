function out=test_ny_regional_candidate_replay(input_folder)
%TEST_NY_REGIONAL_CANDIDATE_REPLAY Saved-input and independent-source guards.
% Uses an already qualified real Package B artifact; never runs an optimizer.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));addpath(root);
if nargin<1,input_folder=fullfile(root,'output','ny_only_package_b');end
folder=tempname;mkdir(folder);cleanup=onCleanup(@()remove_fixture(folder)); %#ok<NASGU>
copyfile(fullfile(input_folder,'ny_regional_candidate.mat'),folder);
copyfile(fullfile(input_folder,'candidate_input_manifest.csv'),folder);
file=fullfile(folder,'ny_regional_candidate.mat');saved=load(file);
nominal=replay_ny_only_regional_candidate(folder);
assert(nominal.passed&&nominal.foundation_replay_passed&&nominal.source_accounting_verified ...
    && nominal.frozen_hardware_verified&&nominal.fresh_pf_hardware_verified ...
    && ~nominal.reconstruction_performed&&~nominal.dlr_ready);
names="nominal_independent_fresh_PF_and_source_accounting";passed=true;

% A hash is the first frozen-input guard; refreshing it must not bypass the
% independent source, foundation, device identity and physical checks below.
changed=saved;changed.mpc.branch(1,6)=changed.mpc.branch(1,6)+100000;
save(file,'-struct','changed');expect_failure(folder,'InputFingerprint');
names(end+1)="unrefreshed_artifact_hash";passed(end+1)=true;
fixtures=["qualified_flag";"source_manifest";"replacement_zones"; ...
    "self_consistent_embedded_foundation";"generator_key";"branch_key"; ...
    "source_allocation";"boundary_identity";"gross_load_ledger"; ...
    "native_device_ledger";"candidate_presolution";"aggregate_disposition"; ...
    "branch_rating";"native_Q_limit";"load";"shunt";"voltage_limit"; ...
    "reference_type";"prior_objective";"nonfinite_state";"fictitious_support_P"; ...
    "frozen_dispatch_mismatch"];
expected=["Unqualified";"SourceManifest";"Policy";"FoundationMismatch"; ...
    "KeyMapping";"KeyMapping";"SourceAccounting";"SourceAccounting"; ...
    "SourceAccounting";"SourceAccounting";"FrozenBuild";"FrozenBuild"; ...
    "FrozenHardware";"FrozenHardware";"FrozenHardware";"FrozenHardware"; ...
    "FrozenHardware";"FrozenHardware";"FrozenHardware";"FrozenState";"Support";"Failed"];
for k=1:numel(fixtures)
    changed=saved;
    switch fixtures(k)
        case "qualified_flag",changed.expected_qualified=false;
        case "source_manifest",changed.source_manifest.sha256_lf_normalized(1)="tampered";
        case "replacement_zones",changed.replacement_zones="G";
        case "self_consistent_embedded_foundation"
            changed.build.foundation.mpc.bus(1,3)=changed.build.foundation.mpc.bus(1,3)+1;
            changed.build.foundation.gross_boundary_ledger.pd_gross_mw(1)= ...
                changed.build.foundation.gross_boundary_ledger.pd_gross_mw(1)+1;
        case "generator_key",changed.generator_keys(1)="PERFORM2019:GEN:1263:RF";
        case "branch_key",changed.branch_keys(1)="UNREGISTERED_PHYSICAL_BRANCH";
        case "source_allocation",changed.build.source_bus_map.model_bus(1)=changed.build.source_bus_map.model_bus(1)+1000000;
        case "boundary_identity",changed.build.allocation.boundary_register.device_key(1)="PERFORM2019:GEN:1263:RF";
        case "gross_load_ledger",changed.build.allocation.model_bus_ledger.pd_gross_mw(1)= ...
                changed.build.allocation.model_bus_ledger.pd_gross_mw(1)+1;
        case "native_device_ledger",changed.build.allocation.generator_map.qmax_mvar(1)= ...
                changed.build.allocation.generator_map.qmax_mvar(1)+1;
        case "candidate_presolution",changed.build.candidate.bus(1,3)=changed.build.candidate.bus(1,3)+1;
        case "aggregate_disposition",changed.build.row235.disposition_register.new_status(1)=1;
        case "branch_rating",changed.mpc.branch(1,6)=changed.mpc.branch(1,6)+100000;
        case "native_Q_limit",changed.mpc.gen(1,4)=changed.mpc.gen(1,4)+100000;
        case "load",changed.mpc.bus(1,3)=changed.mpc.bus(1,3)+1;
        case "shunt",changed.mpc.bus(1,6)=changed.mpc.bus(1,6)+1;
        case "voltage_limit",changed.mpc.bus(1,12)=changed.mpc.bus(1,12)+.1;
        case "reference_type",i=find(changed.mpc.bus(:,2)==3);changed.mpc.bus(i,2)=2;
        case "prior_objective",changed.mpc.gencost(1,5)=changed.mpc.gencost(1,5)+1;
        case "nonfinite_state",changed.mpc.bus(1,8)=NaN;
        case "fictitious_support_P"
            i=find(string(changed.generator_keys)=="RESEARCH2019:Q_SUPPORT:1263:MARCY");changed.mpc.gen(i,2)=1;
        case "frozen_dispatch_mismatch"
            ref=changed.mpc.bus(changed.mpc.bus(:,2)==3,1);
            i=find(changed.mpc.gen(:,1)==ref&changed.mpc.gen(:,8)>0,1);
            changed.mpc.gen(i,2)=changed.mpc.gen(i,2)+.1;
    end
    save(file,'-struct','changed');refresh_manifest(folder,file);
    expect_failure(folder,expected(k));
    names(end+1)=fixtures(k);passed(end+1)=true; %#ok<AGROW>
end
out=struct('pass',all(passed),'assertion_groups',numel(passed), ...
    'gates',table(names(:),passed(:),'VariableNames',{'test','passed'}), ...
    'independent_fresh_pf_pass',nominal.passed, ...
    'max_fresh_P_adjustment_mw',nominal.max_dispatch_adjustment_mw, ...
    'max_fresh_voltage_adjustment_pu',nominal.max_voltage_adjustment_pu, ...
    'reconstruction_performed',false);
disp(out.gates);
end

function expect_failure(folder,id)
expected=['replay_ny_only_regional_candidate:' char(id)];
try,replay_ny_only_regional_candidate(folder);
catch err
    assert(strcmp(err.identifier,expected),'test_ny_regional_candidate_replay:WrongFailure', ...
        'Expected %s, received %s: %s',expected,err.identifier,err.message);
    return
end
error('test_ny_regional_candidate_replay:MissingFailure','Expected %s.',expected);
end

function refresh_manifest(folder,file)
manifest=table("ny_regional_candidate.mat",ny_reference_file_sha256(file), ...
    'VariableNames',{'artifact','sha256'});
ny_lite_writetable_lf(manifest,fullfile(folder,'candidate_input_manifest.csv'));
end

function remove_fixture(folder)
base=char(java.io.File(tempdir).getCanonicalPath());
resolved=char(java.io.File(folder).getCanonicalPath());
assert(startsWith(resolved,[base filesep])&&~strcmp(resolved,base), ...
    'test_ny_regional_candidate_replay:Cleanup','Refusing cleanup outside tempdir.');
if isfolder(resolved),rmdir(resolved,'s');end
end
