function [mpc, report] = scale_ny_downstate_delivery_spine_impedance(mpc, x_multiplier, options)
%SCALE_NY_DOWNSTATE_DELIVERY_SPINE_IMPEDANCE Scale added delivery-path R/X.
%   By default this scales the added S2 delivery paths except the older
%   Gilboa-Leeds seed. Branch charging and ratings are left unchanged.

if nargin < 2 || isempty(x_multiplier), x_multiplier = 1.0; end
if nargin < 3, options = struct(); end
if ~isfield(options, 'include_gilboa_leeds'), options.include_gilboa_leeds = false; end
if ~isfield(options, 'scale_r'), options.scale_r = true; end

if ~isscalar(x_multiplier) || ~isfinite(x_multiplier) || x_multiplier <= 0
    error('scale_ny_downstate_delivery_spine_impedance:BadMultiplier', ...
        'x_multiplier must be a positive finite scalar.');
end

define_constants;
report = table();
if ~isfield(mpc, 'userdata') || ~isfield(mpc.userdata, 'ny_lite') || ...
        ~isfield(mpc.userdata.ny_lite, 'downstate_delivery_added_branches')
    return;
end

branches = mpc.userdata.ny_lite.downstate_delivery_added_branches;
for k = 1:numel(branches)
    b = branches(k);
    if strcmp(b.name, 'GILBOA_LEEDS') && ~options.include_gilboa_leeds
        continue;
    end
    if ~isfield(b, 'branch_index') || b.branch_index > size(mpc.branch, 1)
        continue;
    end
    idx = b.branch_index;
    old_r = mpc.branch(idx, BR_R);
    old_x = mpc.branch(idx, BR_X);
    new_x = b.br_x_initial * x_multiplier;
    if options.scale_r
        new_r = b.br_r_initial * x_multiplier;
    else
        new_r = old_r;
    end
    mpc.branch(idx, BR_R) = new_r;
    mpc.branch(idx, BR_X) = new_x;

    row = table(string(b.name), idx, b.from_bus, b.to_bus, ...
        old_r, old_x, new_r, new_x, x_multiplier, ...
        'VariableNames', {'branch_name','branch_index','from_bus','to_bus', ...
        'old_r','old_x','new_r','new_x','x_multiplier'});
    report = [report; row]; %#ok<AGROW>
end

mpc.userdata.ny_lite.downstate_delivery_x_multiplier = x_multiplier;
mpc.userdata.ny_lite.downstate_delivery_scaled_branch_count = height(report);
end
