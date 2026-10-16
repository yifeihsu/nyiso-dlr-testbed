function mpc = npcc_ny_lite_s13_npcc_augmented_2019
%NPCC_NY_LITE_S13_NPCC_AUGMENTED_2019 Cumulative S13-FULL construction parent.
%   Full 143-bus S7 NPCC structural provenance
%     + ratings-only Phase 0 corrections
%     + Phase 1A source-backed E-G detail
%     + Phase 1B source-backed UPNY-ConEd 345-kV detail.
%
%   This 149-bus/262-branch/62-generator case is an unpromoted construction
%   checkpoint. It is not the future NYISO DLR delivery model and it does not
%   contain an S14 external multi-port equivalent.

case_dir = fileparts(mfilename('fullpath'));
helper_dir = fullfile(case_dir, 'NY_Lite');
addpath(case_dir); addpath(helper_dir);

build = build_s13_phase1b_candidate(struct( ...
    'write_outputs', false, 'verbose', false));
mpc = build.candidate;
end
