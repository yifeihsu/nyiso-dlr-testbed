function out=test_ny_foundation_reference
%TEST_NY_FOUNDATION_REFERENCE Actual original-source, bounded reference gates.
% This test solves the real 2019 source and a bounded prior-only reference;
% it does not use a toy fixture, inherited reduction or stored success flag.
define_constants;
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));addpath(root);
folder=tempname;mkdir(folder);
cleanup=onCleanup(@()remove_fixture(folder)); %#ok<NASGU>
package=run_ny_only_foundation(struct('write_outputs',true,'run_tests',false,'output_dir',folder));
n=package.inventory;original=n.source;p=package.source_snapshot.result;
b=package.boundary;r=package.reference;
assert(isequal([size(original.bus,1),size(original.branch,1),size(original.gen,1)], ...
    [1576,2371,615])&&n.validation.pass);
assert(p.success,'test_ny_foundation_reference:SourcePF','Source PF did not converge.');
assert(height(b.boundary_register)==20&&height(b.reference_register)==1&& ...
    b.summary.classified_candidate_count==21&&b.summary.legacy_schedule_record_count==19&& ...
    b.summary.online_boundary_count==14&&b.summary.inactive_boundary_count==6);
falconer=b.boundary_register.device_key=="PERFORM2019:GEN:69:X";
assert(sum(falconer)==1&&b.boundary_register.raw_status(falconer)==1&& ...
    b.boundary_register.canonical_status(falconer)==0&& ...
    b.boundary_register.p_injection_mw(falconer)==0&&b.boundary_register.q_injection_mvar(falconer)==0);
assert(r.electrical_baseline_qualified&&r.bounded_audit.passed&&r.replay_audit.passed);
assert(isequal(n.source,original),'Construction changed the immutable source.');
c=r.candidate;native=r.application.native_generator_map;ng=height(native);
assert(ng==594&&size(c.gen,1)==595&&size(c.bus,1)==1576&&size(c.branch,1)==2371);
assert(all(startsWith(string(native.source_device_role),"native_")));
assert(~any(ismember(r.generator_keys,string(b.all_records.device_key))));
assert(sum(c.gen(:,GEN_BUS)==69)==3,'Colocated native Falconer generators disappeared.');
assert(isequal(c.gen(1:ng,GEN_BUS),original.gen(native.source_gen_row,GEN_BUS)));
cols=[PMIN PMAX QMIN QMAX GEN_STATUS];
assert(isequal(c.gen(1:ng,cols),original.gen(native.source_gen_row,cols))&& ...
    isequal(r.result.gen(:,cols),c.gen(:,cols))&& ...
    all(isfinite(c.gen(:,cols)),'all'));
assert(isequal(c.branch(:,1:13),original.branch(:,1:13))&& ...
    isequal(r.result.branch(:,1:13),original.branch(:,1:13)));
assert(isequal(c.bus(:,[GS BS BASE_KV VMIN VMAX]),original.bus(:,[GS BS BASE_KV VMIN VMAX])));

support=find(r.generator_keys=="RESEARCH2019:Q_SUPPORT:1263:MARCY");
assert(isscalar(support)&&c.gen(support,GEN_BUS)==1263&& ...
    all(c.gen(support,[PG PMIN PMAX])==0)&& ...
    isequal(c.gen(support,[QMIN QMAX]),[-900,900])&& ...
    abs(r.result.gen(support,PG))<1e-6&&r.support_register.provenance=="assumed");
ref_bus=c.bus(c.bus(:,BUS_TYPE)==REF,BUS_I);
assert(isscalar(ref_bus)&&ref_bus==847);
refs=find(c.gen(:,GEN_BUS)==ref_bus&c.gen(:,GEN_STATUS)>0);
assert(all(refs<=ng)&&all(startsWith(string(native.source_device_role(refs)),"native_"))&& ...
    all(ismember(r.generator_keys(refs),native.device_key)));

l=r.application.bus_injection_ledger;
assert(isequal(l.source_bus,original.bus(:,BUS_I))&& ...
    isequal(l.pd_gross_mw,original.bus(:,PD))&&isequal(l.qd_gross_mvar,original.bus(:,QD)));
assert(max(abs(c.bus(:,PD)+l.p_boundary_mw-l.pd_gross_mw))<1e-9&& ...
    max(abs(c.bus(:,QD)+l.q_boundary_mvar-l.qd_gross_mvar))<1e-9);
assert(abs(sum(l.p_boundary_mw)-sum(b.boundary_register.p_injection_mw))<1e-9&& ...
    abs(sum(l.q_boundary_mvar)-sum(b.boundary_register.q_injection_mvar))<1e-9&& ...
    r.accounting.boundary_schedule_movement_mw==0);
assert(abs(r.accounting.balance_error_mw)<1e-3&& ...
    abs(r.accounting.native_generation_mw+r.accounting.fixed_boundary_p_mw- ...
    r.accounting.gross_load_mw-r.accounting.total_loss_mw)<1e-3);

% Fresh third PF from frozen bounded dispatch; neither reconstruct again
% nor trust the stored fixed_input_pf/result flows or qualification status.
fixed=r.reconstruction.result;
fresh=runpf(fixed,mpoption('verbose',0,'out.all',0,'pf.enforce_q_lims',1,'pf.tol',1e-10));
audit=audit_ny_ac_reference(fresh,struct('generator_keys',r.generator_keys, ...
    'branch_keys',n.branch_inventory.device_key));
assert(fresh.success&&audit.passed);
on=fixed.gen(:,GEN_STATUS)>0;
dp=max(abs(fresh.gen(on,PG)-fixed.gen(on,PG)));
dv=max(abs(fresh.bus(:,VM)-fixed.bus(:,VM)));
assert(dp<1e-3&&dv<1e-4&&abs(fresh.gen(support,PG))<1e-6);
assert(isequal(fresh.gen(:,cols),c.gen(:,cols))&& ...
    isequal(fresh.bus(:,[PD QD GS BS VMIN VMAX]),c.bus(:,[PD QD GS BS VMIN VMAX]))&& ...
    isequal(fresh.branch(:,1:13),c.branch(:,1:13)));
assert(~r.minimum_relaxation_used&&r.fictitious_active_injection_mw==0&& ...
    ~r.internal_interface_fit_used&&~r.dlr_ready&& ...
    string(r.contemporary_validation_coverage)=="not_evaluated");

% Exercise the file-based replay contract separately from the in-memory PF.
replayed=replay_ny_only_foundation(folder);assert(replayed.passed);
file=fullfile(folder,'ny_foundation_reference.mat');saved=load(file);changed=saved;
changed.mpc.branch(1,RATE_A)=changed.mpc.branch(1,RATE_A)+100000;
save(file,'-struct','changed');
expect_replay_failure(folder,'replay_ny_only_foundation:InputFingerprint');
refresh_fixture_manifest(folder,file);
expect_replay_failure(folder,'replay_ny_only_foundation:FrozenHardware');
changed=saved;changed.mpc.gen(1,QMAX)=changed.mpc.gen(1,QMAX)+100000;
save(file,'-struct','changed');refresh_fixture_manifest(folder,file);
expect_replay_failure(folder,'replay_ny_only_foundation:FrozenHardware');
changed=saved;changed.boundary_register.device_key(1)="PERFORM2019:GEN:1263:RF";
save(file,'-struct','changed');refresh_fixture_manifest(folder,file);
expect_replay_failure(folder,'replay_ny_only_foundation:BoundaryIdentity');

out=struct('pass',true,'test_count',25,'external_proxy_count',height(b.boundary_register), ...
    'native_generator_count',ng,'independent_fresh_pf_pass',audit.passed, ...
    'max_fresh_P_adjustment_mw',dp,'max_fresh_voltage_adjustment_pu',dv, ...
    'gross_load_mw',sum(l.pd_gross_mw),'fixed_boundary_p_mw',sum(l.p_boundary_mw), ...
    'reference_balance_error_mw',r.accounting.balance_error_mw, ...
    'saved_input_tamper_rejected',true,'widened_source_limits_rejected',true, ...
    'changed_boundary_identity_rejected',true, ...
    'qualification_scope','one_assumed_2019_source_reference_only');
disp(out);
end

function expect_replay_failure(folder,id)
failed=false;
try,replay_ny_only_foundation(folder);catch e,failed=strcmp(e.identifier,id);end
assert(failed,'test_ny_foundation_reference:ReplayGuard','Expected %s.',id);
end
function refresh_fixture_manifest(folder,file)
manifest=table("ny_foundation_reference.mat",ny_reference_file_sha256(file), ...
    'VariableNames',{'artifact','sha256'});
ny_lite_writetable_lf(manifest,fullfile(folder,'reference_input_manifest.csv'));
end
function remove_fixture(folder)
% Verify the only recursively removed path is the test's temp directory.
base=char(java.io.File(tempdir).getCanonicalPath());
resolved=char(java.io.File(folder).getCanonicalPath());
assert(startsWith(resolved,[base filesep])&&~strcmp(resolved,base), ...
    'test_ny_foundation_reference:Cleanup','Refusing cleanup outside tempdir.');
if isfolder(resolved),rmdir(resolved,'s');end
end
