function tests=test_replay_compact_partial_spc_dlr(folder)
%TEST_REPLAY_COMPACT_PARTIAL_SPC_DLR Fresh replay plus adversarial saved inputs.
% Uses a private temporary MAT/manifest only. Original campaign bytes remain
% untouched; neither nominal replay nor tampered replay calls an optimizer.
root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
if nargin<1,folder=fullfile(root,'output','compact_ny_2025','partial_spc_thermal');end
nominal=replay_compact_partial_spc_dlr(folder);assert(nominal.passed&&~nominal.optimizer_called);
tests=add(table(),"independent_four_weather_frozen_dispatch_AC_and_heat_replay",0);
d=load(fullfile(folder,'campaign.mat'),'out');original=d.out;
scratch=fullfile(root,'tmp','partial_spc_thermal');if ~isfolder(scratch),mkdir(scratch);end
tmp=tempname(scratch);mkdir(tmp);cleanup=onCleanup(@()remove_private_files(tmp)); %#ok<NASGU>
out=original;out.weather.observed_weather(1)=true;
persist(tmp,out,true);reject(@()replay_compact_partial_spc_dlr(tmp),'partial_spc_dlr_replay:Scope');
tests=add(tests,"weather_observation_claim_cannot_be_enabled_by_saved_flag",0);
out=original;out.code_manifest.sha256_lf_normalized(1)=join(repmat("0",64,1),"");
persist(tmp,out,true);reject(@()replay_compact_partial_spc_dlr(tmp),'partial_spc_dlr_replay:Code');
tests=add(tests,"specific_thermal_code_fingerprint_is_mandatory",0);
out=original;out.electrical_source_fingerprints.sha256(1)=join(repmat("0",64,1),"");
persist(tmp,out,true);reject(@()replay_compact_partial_spc_dlr(tmp),'partial_spc_dlr_replay:Source');
tests=add(tests,"electrical_source_bytes_must_match_even_with_refreshed_thermal_manifest",0);
out=original;out.realizations.bundle_count(1)=out.realizations.bundle_count(1)+1;
persist(tmp,out,true);reject(@()replay_compact_partial_spc_dlr(tmp),'partial_spc_dlr_replay:Realization');
tests=add(tests,"multiplicity_cannot_be_changed_after_electrical_source_freeze",0);
out=original;out.cases{1}.bounded_result.gen(1,9)=out.cases{1}.bounded_result.gen(1,9)+1;
persist(tmp,out,true);reject(@()replay_compact_partial_spc_dlr(tmp),'partial_spc_dlr_replay:Hardware');
tests=add(tests,"bounded_generator_capacity_cannot_be_relaxed_after_freeze",0);
out=original;out.cases{1}.temperature_c(1)=out.cases{1}.temperature_c(1)+2;
persist(tmp,out,true);reject(@()replay_compact_partial_spc_dlr(tmp),'partial_spc_dlr_replay:Hardware');
tests=add(tests,"temperature_must_match_actual_R_T_not_saved_thermal_pass_flags",0);
% Refresh neither manifest nor its checksum for this final changed MAT.
out=original;out.weather.wind_m_s(1)=out.weather.wind_m_s(1)+.01;
persist(tmp,out,false);reject(@()replay_compact_partial_spc_dlr(tmp),'partial_spc_dlr_replay:Artifact');
tests=add(tests,"changed_MAT_bytes_rejected_before_loading_or_physics",0);
assert(all(tests.passed));
end
function persist(folder,out,refresh)
save(fullfile(folder,'campaign.mat'),'out','-v7');
if refresh
    ny_lite_writetable_lf(table("campaign.mat",ny_reference_file_sha256(fullfile(folder,'campaign.mat')), ...
        'VariableNames',{'artifact','sha256'}),fullfile(folder,'campaign_manifest.csv'));
end
end
function remove_private_files(folder)
for file=["campaign.mat";"campaign_manifest.csv"]
    p=fullfile(folder,file);if isfile(p),delete(p);end
end
if isfolder(folder),rmdir(folder);end
end
function reject(fn,id)
try,fn();catch err,assert(strcmp(err.identifier,id),'Expected %s, received %s.',id,err.identifier);return;end
error('partial_spc_dlr_replay_test:MissingGuard','Expected rejection %s.',id);
end
function t=add(t,name,error_value)
t=[t;table(string(name),true,error_value,'VariableNames',{'test','passed','max_error'})];
end
