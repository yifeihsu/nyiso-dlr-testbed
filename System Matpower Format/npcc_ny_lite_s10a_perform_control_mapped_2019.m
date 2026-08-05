function mpc = npcc_ny_lite_s10a_perform_control_mapped_2019
%NPCC_NY_LITE_S10A_PERFORM_CONTROL_MAPPED_2019 Diagnostic 2019 benchmark case.
%   This case is not promoted over S7. It is a NY-only, similarity-scaled
%   same-snapshot experiment for validating PERFORM-derived control mapping.

case_dir = fileparts(mfilename('fullpath'));
helper_dir = fullfile(case_dir, 'NY_Lite');
addpath(case_dir); addpath(helper_dir);
[mpc, ~] = build_s10a_perform_control_mapped_case;
end
