function tests=test_restored_fleet_ac_checkpoint
%TEST_RESTORED_FLEET_AC_CHECKPOINT Adversarial persisted-evidence guards.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(root,'System Matpower Format','NY_Lite'));
file=fullfile(root,'output','nygrid_compact_2019','ac_checkpoint','restored_fleet_ac_checkpoint.mat');
d=load(file,'out');original=d.out;
parent=fullfile(root,'tmp');folder=tempname(parent);mkdir(folder);clean=onCleanup(@()remove_fixture(folder,parent)); %#ok<NASGU>
names=strings(0,1);
out=original;out.policy.fit_interfaces=true;persist(folder,out,false);
reject(@()replay_restored_fleet_ac_checkpoint(folder),'compact_2019_ac:InputFingerprint');
names(end+1)="unrefreshed_artifact_tamper_rejected";
out=original;out.cases{1}.snapshot.Pg_prior_mw(1)=out.cases{1}.snapshot.Pg_prior_mw(1)+1;persist(folder,out,true);
reject(@()replay_restored_fleet_ac_checkpoint(folder),'compact_2019_ac:SourceInputs');
names(end+1)="refreshed_manifest_cannot_hide_changed_source_prior";
out=original;f=out.cases{1}.fit;f.bounded_result.gen(1,9)=f.bounded_result.gen(1,9)+1;
out.cases{1}.fit=f;out.cases{1}.attempts{1}=f;persist(folder,out,true);
reject(@()replay_restored_fleet_ac_checkpoint(folder),'compact_2019_ac:FrozenHardware');
names(end+1)="refreshed_manifest_cannot_hide_relaxed_generator_capacity";
out=original;f=out.cases{1}.fit;f.internal_interface_fit_used=true;
out.cases{1}.fit=f;out.cases{1}.attempts{1}=f;persist(folder,out,true);
reject(@()replay_restored_fleet_ac_checkpoint(folder),'compact_2019_ac:InterfaceLeakage');
names(end+1)="interface_objective_claim_rejected";
out=original;f=out.cases{1}.fit;f.input.gencost(1,5)=f.input.gencost(1,5)*2;
out.cases{1}.fit=f;out.cases{1}.attempts{1}=f;persist(folder,out,true);
reject(@()replay_restored_fleet_ac_checkpoint(folder),'compact_2019_ac:Objective');
names(end+1)="changed_prior_objective_rejected";
out=original;out.Marcy_DC_topology_AC_qualified=true;persist(folder,out,true);
reject(@()replay_restored_fleet_ac_checkpoint(folder),'compact_2019_ac:Scope');
names(end+1)="unearned_Marcy_AC_qualification_rejected";
tests=table(names(:),true(numel(names),1),'VariableNames',{'test','passed'});
end
function persist(folder,out,valid)
file=fullfile(folder,'restored_fleet_ac_checkpoint.mat');save(file,'out','-v7');
hash=ny_reference_file_sha256(file);if ~valid,hash=repmat("0",1,64);hash=join(hash,"");end
ny_lite_writetable_lf(table("restored_fleet_ac_checkpoint.mat",hash,'VariableNames',{'relative_path','sha256'}), ...
    fullfile(folder,'output_manifest.csv'));
end
function reject(fn,id)
try,fn();catch err,assert(string(err.identifier)==id,'compact_2019_ac:TestUnexpected','Unexpected rejection: %s',err.identifier);return;end
error('compact_2019_ac:TestNoRejection','Expected %s',id);
end
function remove_fixture(folder,parent)
path=char(java.io.File(folder).getCanonicalPath());base=char(java.io.File(parent).getCanonicalPath());
assert(startsWith(path,[base filesep])&&~strcmp(path,base));
if isfolder(path),rmdir(path,'s');end
end
