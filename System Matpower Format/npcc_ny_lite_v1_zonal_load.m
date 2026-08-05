function [mpc, load_report] = npcc_ny_lite_v1_zonal_load(zonal_loads, eta, options)
%NPCC_NY_LITE_V1_ZONAL_LOAD Apply NYISO zonal load targets to NPCC buses.
%   zonal_loads may also be a scenario_id from ny_zonal_load_targets.csv.

if nargin < 1, zonal_loads = []; end
if nargin < 2 || isempty(eta), eta = 1.0; end
if nargin < 3, options = struct(); end

case_dir = fileparts(mfilename('fullpath'));
helper_dir = fullfile(case_dir, 'NY_Lite');
if exist(helper_dir, 'dir'), addpath(helper_dir); end

mpc = npcc_ny_lite_v0_baseline;
[mpc, load_report] = apply_nyiso_zonal_loads(mpc, zonal_loads, eta, options);
mpc.userdata.ny_lite.case_version = 'v1_zonal_load';
mpc.userdata.ny_lite.description = ...
    'NPCC baseline with redistributed NY load by NYISO zones; topology unchanged.';
end
