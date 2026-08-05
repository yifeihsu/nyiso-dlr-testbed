function [J, detail] = interface_target_objective_balanced(flows, targets, options)
%INTERFACE_TARGET_OBJECTIVE_BALANCED Public-interface objective with limit scale.
%
%   Uses S_m = max(min_scale_mw, abs(target_limit_mw)) when a scaled P-32
%   interface limit is available, otherwise max(min_scale_mw, abs(target_flow)).

if nargin < 3, options = struct(); end
if ~isfield(options, 'min_scale_mw'), options.min_scale_mw = 500; end
if ~isfield(options, 'w_F'), options.w_F = 1; end
if ~isfield(options, 'scale_file'), options.scale_file = ""; end

fixed_scales = table();
if strlength(string(options.scale_file)) > 0 && exist(options.scale_file, 'file') == 2
    fixed_scales = readtable(options.scale_file, 'TextType', 'string', ...
        'VariableNamingRule', 'preserve');
end

rows = table();
J = 0;
for k = 1:height(targets)
    name = string(targets.interface_name(k));
    idx = find(strcmp({flows.interface_name}, char(name)), 1);
    if ismember('target_limit_mw', targets.Properties.VariableNames)
        limit_value = targets.target_limit_mw(k);
    else
        limit_value = NaN;
    end
    if isempty(idx)
        lite_flow = NaN;
        residual = NaN;
        [scale, scale_source] = fixed_or_limit_scale(name, limit_value, ...
            targets.target_flow_mw(k), fixed_scales, options.min_scale_mw);
        term = 1e5;
    else
        lite_flow = flows(idx).flow_mw;
        target_flow = targets.target_flow_mw(k);
        [scale, scale_source] = fixed_or_limit_scale(name, limit_value, ...
            target_flow, fixed_scales, options.min_scale_mw);
        residual = lite_flow - target_flow;
        term = options.w_F * (residual / scale)^2;
    end
    J = J + term;
    rows = [rows; table(name, lite_flow, targets.target_flow_mw(k), ... %#ok<AGROW>
        limit_value, residual, scale, string(scale_source), term, ...
        'VariableNames', {'interface_name','lite_flow_mw','target_flow_mw', ...
        'target_limit_mw','residual_mw','scale_mw','scale_source', ...
        'objective_term'})];
end
detail = rows;
end

function [scale, source] = fixed_or_limit_scale(name, limit_value, target_flow, fixed_scales, min_scale)
if istable(fixed_scales) && height(fixed_scales) > 0 && ...
        ismember('interface_name', fixed_scales.Properties.VariableNames) && ...
        ismember('fixed_scale_mw', fixed_scales.Properties.VariableNames)
    idx = find(fixed_scales.interface_name == name, 1);
    if ~isempty(idx) && isfinite(fixed_scales.fixed_scale_mw(idx)) && ...
            fixed_scales.fixed_scale_mw(idx) > 0
        scale = max(min_scale, abs(fixed_scales.fixed_scale_mw(idx)));
        source = "fixed_interface_scale";
        return;
    end
end
if isfinite(limit_value) && limit_value > 0
    scale = max(min_scale, abs(limit_value));
    source = "row_target_limit";
else
    scale = max(min_scale, abs(target_flow));
    source = "target_flow_or_floor";
end
end
