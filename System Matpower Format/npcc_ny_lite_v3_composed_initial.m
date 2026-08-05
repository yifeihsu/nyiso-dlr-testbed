function [mpc, load_report, added_tielines] = npcc_ny_lite_v3_composed_initial(zonal_loads, eta, profile, load_options)
%NPCC_NY_LITE_V3_COMPOSED_INITIAL Compose loads and initial topology.
%   This is an explicitly UNCALIBRATED case for screening and calibration.

if nargin < 1, zonal_loads = []; end
if nargin < 2 || isempty(eta), eta = 1.0; end
if nargin < 3 || isempty(profile), profile = 'core'; end
if nargin < 4, load_options = struct(); end

case_dir = fileparts(mfilename('fullpath'));
helper_dir = fullfile(case_dir, 'NY_Lite');
if exist(helper_dir, 'dir'), addpath(helper_dir); end

mpc = npcc_ny_lite_v0_baseline;
[mpc, load_report] = apply_nyiso_zonal_loads(mpc, zonal_loads, eta, load_options);
[mpc, added_tielines] = add_ny_lite_tielines(mpc, profile);
mpc.userdata.ny_lite.case_version = 'v3_composed_initial';
mpc.userdata.ny_lite.description = ...
    'Uncalibrated NY-lite composition: zonal load allocation plus selected initial ties.';
mpc.userdata.ny_lite.calibration_status = 'NOT CALIBRATED';
end
