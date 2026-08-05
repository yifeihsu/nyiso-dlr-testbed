function outputs = build_s4_interface_objective_scales(options)
%BUILD_S4_INTERFACE_OBJECTIVE_SCALES Build fixed public-interface scales.
%
%   Uses the median available scaled P-32 target_limit_mw by interface.
%   Missing scenario limits then use this fixed scale instead of falling
%   back to the minimum-scale floor.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'nyiso_public_interface_targets.csv');
end
if ~isfield(options, 'scale_file')
    options.scale_file = fullfile(helper_dir, 'nyiso_interface_objective_scales.csv');
end
if ~isfield(options, 'min_scale_mw'), options.min_scale_mw = 500; end

targets = readtable(options.target_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
interfaces = unique(targets.interface_name, 'stable');
rows = table();
for k = 1:numel(interfaces)
    name = interfaces(k);
    mask = targets.interface_name == name;
    limits = targets.target_limit_mw(mask);
    limits = limits(isfinite(limits) & limits > 0);
    if isempty(limits)
        fixed_scale = options.min_scale_mw;
        source = "floor_only_no_available_limit";
        available_count = 0;
    else
        fixed_scale = max(options.min_scale_mw, median(limits));
        source = "median_available_scaled_p32_target_limit";
        available_count = numel(limits);
    end
    missing_count = sum(mask) - available_count;
    row = table(name, fixed_scale, options.min_scale_mw, available_count, ...
        missing_count, source, ...
        "Fixed scale for objective normalization; not a branch rating.", ...
        'VariableNames', {'interface_name','fixed_scale_mw','min_scale_mw', ...
        'available_limit_count','missing_limit_count','source','note'});
    rows = [rows; row]; %#ok<AGROW>
end
writetable(rows, options.scale_file);
outputs = struct('scale_file', options.scale_file, 'row_count', height(rows));
end
