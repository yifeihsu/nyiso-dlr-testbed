function mpc = npcc_ny_lite_v0_baseline
%NPCC_NY_LITE_V0_BASELINE Frozen NPCC baseline with NYISO zone metadata.

case_dir = fileparts(mfilename('fullpath'));
helper_dir = fullfile(case_dir, 'NY_Lite');
if exist(helper_dir, 'dir')
    addpath(helper_dir);
end

mpc = npcc_original;
mpc = attach_nyiso_zone_metadata(mpc);

mpc.userdata.ny_lite.case_version = 'v0_baseline';
mpc.userdata.ny_lite.description = ...
    'Frozen original NPCC case with explicit retained-bus NYISO zone metadata.';
mpc.userdata.ny_lite.original_branch_count = size(mpc.branch, 1);
end
