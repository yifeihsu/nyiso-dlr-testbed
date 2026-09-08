function mpc=npcc_ny_compact_dlr_testbed
%NPCC_NY_COMPACT_DLR_TESTBED Frozen 51-bus NY-only NPCC electrical benchmark.
% Intended for preliminary research; thermal/DLR realization is unqualified.
% Loading verifies the input hash. Use replay_compact_npcc_ny_testbed for a
% fresh physical audit and fixed-input power flow without optimization.
root=fileparts(fileparts(mfilename('fullpath')));addpath(fullfile(root,'System Matpower Format','NY_Lite'));
folder=fullfile(root,'output','compact_npcc_ny');file=fullfile(folder,'compact_npcc_ny_reference.mat');
manifest=readtable(fullfile(folder,'compact_input_manifest.csv'),'TextType','string');
assert(height(manifest)==1&&manifest.artifact=="compact_npcc_ny_reference.mat"&& ...
    manifest.sha256==ny_reference_file_sha256(file),'compact_npcc:InputFingerprint','Frozen compact input differs from its manifest.');
d=load(file,'mpc','expected_qualified');
assert(isequal(d.expected_qualified,true),'compact_npcc:Unqualified','Saved compact candidate is not qualified.');
mpc=d.mpc;compact_npcc_model_contract(mpc);
end
