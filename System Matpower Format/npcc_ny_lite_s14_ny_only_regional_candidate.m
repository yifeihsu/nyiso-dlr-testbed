function mpc=npcc_ny_lite_s14_ny_only_regional_candidate
%NPCC_NY_LITE_S14_NY_ONLY_REGIONAL_CANDIDATE Frozen historical Package B case.
% Hash-checked load, not a fresh PF or contemporary/DLR qualification.
% Use replay_ny_only_regional_candidate for independent physical validation.
root=fileparts(fileparts(mfilename('fullpath')));addpath(fullfile(root,'System Matpower Format','NY_Lite'));
folder=fullfile(root,'output','ny_only_package_b');file=fullfile(folder,'ny_regional_candidate.mat');
manifest=readtable(fullfile(folder,'candidate_input_manifest.csv'),'TextType','string');
assert(height(manifest)==1&&manifest.artifact=="ny_regional_candidate.mat"&& ...
    manifest.sha256==ny_reference_file_sha256(file),'ny_region:InputFingerprint','Frozen candidate differs from manifest.');
d=load(file,'mpc','expected_qualified');assert(isequal(d.expected_qualified,true),'ny_region:Unqualified','Saved candidate is not qualified.');
mpc=d.mpc;
end
