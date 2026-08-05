function [J, detail] = interface_target_objective(flows, targets, options)
%INTERFACE_TARGET_OBJECTIVE Weighted public-interface target objective.

if nargin < 3, options = struct(); end
if ~isfield(options, 'w_F'), options.w_F = 1; end
if ~isfield(options, 'w_U'), options.w_U = 0; end
if ~isfield(options, 'use_scaled_limit_for_scale'), options.use_scaled_limit_for_scale = false; end

rows = table();
J = 0;
for k = 1:height(targets)
    name = string(targets.interface_name(k));
    idx = find(strcmp({flows.interface_name}, char(name)), 1);
    if isempty(idx)
        lite_flow = NaN;
        residual = NaN;
        term = 1e5;
        scale = NaN;
    else
        lite_flow = flows(idx).flow_mw;
        target_flow = targets.target_flow_mw(k);
        if options.use_scaled_limit_for_scale && isfinite(targets.target_limit_mw(k))
            scale = max(100, abs(targets.target_limit_mw(k)));
        else
            scale = max(100, abs(target_flow));
        end
        residual = lite_flow - target_flow;
        term = options.w_F * (residual / scale)^2;
    end
    J = J + term;
    new_row = table(name, lite_flow, targets.target_flow_mw(k), residual, scale, term, ...
        'VariableNames', {'interface_name','lite_flow_mw','target_flow_mw', ...
            'residual_mw','scale_mw','objective_term'});
    rows = [rows; new_row]; %#ok<AGROW>
end
detail = rows;
end
