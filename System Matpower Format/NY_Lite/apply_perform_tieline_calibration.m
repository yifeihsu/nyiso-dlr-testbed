function [mpc, report] = apply_perform_tieline_calibration(mpc, params)
%APPLY_PERFORM_TIELINE_CALIBRATION Scale direct PERFORM corridor equivalents.
%   PARAMS fields are impedance multipliers around the direct PERFORM values:
%       gilboa_leeds_scale
%       pleasant_wood_scale
%       wood_millwood_scale
%       lower_hudson_b_fraction
%   R and X are scaled together to preserve each PERFORM R/X ratio. The B
%   fraction applies only to the two lower-Hudson parallel equivalents.

if nargin < 2, params = struct(); end
if ~isfield(params, 'mode'), params.mode = "perform_scaled"; end
if ~isfield(params, 'gilboa_leeds_scale'), params.gilboa_leeds_scale = 1; end
if ~isfield(params, 'pleasant_wood_scale'), params.pleasant_wood_scale = 1; end
if ~isfield(params, 'wood_millwood_scale'), params.wood_millwood_scale = 1; end
if ~isfield(params, 'lower_hudson_b_fraction'), params.lower_hudson_b_fraction = 0; end

mode = lower(string(params.mode));
if mode == "current"
    [mpc, report] = apply_perform_tieline_alignment(mpc, 'current');
    report.impedance_scale = ones(height(report), 1);
    report.b_fraction = ones(height(report), 1);
    report.calibration_source = repmat("S4 current parameters", height(report), 1);
    return;
end

validateattributes(params.gilboa_leeds_scale, {'numeric'}, {'scalar','positive'});
validateattributes(params.pleasant_wood_scale, {'numeric'}, {'scalar','positive'});
validateattributes(params.wood_millwood_scale, {'numeric'}, {'scalar','positive'});
validateattributes(params.lower_hudson_b_fraction, {'numeric'}, ...
    {'scalar','>=',0,'<=',1});

define_constants;
[mpc, base_report] = apply_perform_tieline_alignment(mpc, 'perform_rxb');
names = string(base_report.branch_name);
scales = [params.gilboa_leeds_scale; params.pleasant_wood_scale; ...
    params.wood_millwood_scale];
if height(base_report) ~= numel(scales) || ...
        ~all(names == ["GILBOA_LEEDS"; "PLEASANT_VLY_WOOD_STREET"; ...
        "WOOD_STREET_MILLWOOD"])
    error('Unexpected PERFORM tie-line alignment report ordering.');
end

report = base_report;
report.mode(:) = mode;
report.impedance_scale = scales;
report.b_fraction = [1; params.lower_hudson_b_fraction; ...
    params.lower_hudson_b_fraction];
report.perform_r_pu = report.new_r_pu;
report.perform_x_pu = report.new_x_pu;
report.perform_b_pu = report.new_b_pu;
for k = 1:height(report)
    idx = report.branch_index(k);
    mpc.branch(idx, BR_R) = report.perform_r_pu(k) * scales(k);
    mpc.branch(idx, BR_X) = report.perform_x_pu(k) * scales(k);
    if k == 1
        mpc.branch(idx, BR_B) = report.perform_b_pu(k);
    else
        mpc.branch(idx, BR_B) = report.perform_b_pu(k) * ...
            params.lower_hudson_b_fraction;
    end
    report.new_r_pu(k) = mpc.branch(idx, BR_R);
    report.new_x_pu(k) = mpc.branch(idx, BR_X);
    report.new_b_pu(k) = mpc.branch(idx, BR_B);
end
report.calibration_source = repmat( ...
    "PERFORM direct parameter prior with fitted impedance multiplier", ...
    height(report), 1);
mpc.userdata.ny_lite.perform_tieline_calibration = params;
mpc.userdata.ny_lite.perform_tieline_calibration_report = report;
end
