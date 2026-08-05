function [mpc, added_tielines] = npcc_ny_lite_v2_topology(profile)
%NPCC_NY_LITE_V2_TOPOLOGY Add the initial NY-lite equivalent tie-line patch.
%   The default 'core' profile adds only the direct Perform Gilboa-Leeds analog
%   while preserving the original NPCC loads.

if nargin < 1 || isempty(profile)
    profile = 'core';
end

case_dir = fileparts(mfilename('fullpath'));
helper_dir = fullfile(case_dir, 'NY_Lite');
if exist(helper_dir, 'dir')
    addpath(helper_dir);
end

mpc = npcc_ny_lite_v0_baseline;
[mpc, added_tielines] = add_ny_lite_tielines(mpc, profile);

mpc.userdata.ny_lite.case_version = 'v2_topology';
mpc.userdata.ny_lite.description = ...
    'NPCC baseline loads with selected NY-lite equivalent tie-line topology patch.';
end
