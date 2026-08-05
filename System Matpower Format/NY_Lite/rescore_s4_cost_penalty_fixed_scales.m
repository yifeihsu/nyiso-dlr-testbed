function outputs = rescore_s4_cost_penalty_fixed_scales(options)
%RESCORE_S4_COST_PENALTY_FIXED_SCALES Re-score S4 sweep with fixed scales.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
if ~isfield(options, 'residual_file')
    options.residual_file = fullfile(helper_dir, 's4_cost_penalty_calibration_residuals.csv');
end
if ~isfield(options, 'result_file')
    options.result_file = fullfile(helper_dir, 's4_cost_penalty_calibration_results.csv');
end
if ~isfield(options, 'scale_file')
    options.scale_file = fullfile(helper_dir, 'nyiso_interface_objective_scales.csv');
end
if ~isfield(options, 'summary_file')
    options.summary_file = fullfile(helper_dir, 's4_cost_penalty_fixed_scale_rescore_summary.csv');
end
if ~isfield(options, 'min_scale_mw'), options.min_scale_mw = 500; end

if exist(options.scale_file, 'file') ~= 2
    build_s4_interface_objective_scales(struct('scale_file', options.scale_file, ...
        'min_scale_mw', options.min_scale_mw));
end
res = readtable(options.residual_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
results = readtable(options.result_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
scales = readtable(options.scale_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');

fixed_scale = zeros(height(res), 1);
fixed_term = zeros(height(res), 1);
for k = 1:height(res)
    fixed_scale(k) = scale_for_interface(scales, res.interface_name(k), options.min_scale_mw);
    fixed_term(k) = (res.residual_mw(k) / fixed_scale(k))^2;
end
res.fixed_scale_mw = fixed_scale;
res.fixed_scale_objective_term = fixed_term;

case_ids = unique(res.case_id, 'stable');
summary = table();
for c = 1:numel(case_ids)
    cid = case_ids(c);
    rmask = res.case_id == cid;
    omask = results.case_id == cid;
    subset = results(omask, :);
    first = subset(1, :);
    row = table(cid, first.case_group, first.zone_j_cost_c1, ...
        first.s4_e_cost_c1, first.s4_f_cost_c1, first.s4_g_cost_c1, ...
        first.s4_k_cost_c1, first.abc_cap_factor, first.x_spine_multiplier, ...
        height(subset), sum(subset.opf_success == 1), ...
        sum(subset.classic_interface_objective, 'omitnan'), ...
        sum(res.fixed_scale_objective_term(rmask), 'omitnan'), ...
        mean(subset.zone_j_equiv_pg_mw, 'omitnan'), ...
        max(subset.zone_j_equiv_pg_mw, [], 'omitnan'), ...
        mean(subset.s4_equiv_pg_mw, 'omitnan'), ...
        max(subset.s4_equiv_pg_mw, [], 'omitnan'), ...
        max(subset.max_abs_interface_residual_mw, [], 'omitnan'), ...
        max(subset.branch_overload_count, [], 'omitnan'), ...
        max(subset.voltage_bound_count_high + subset.voltage_bound_count_low, [], 'omitnan'), ...
        'VariableNames', {'case_id','case_group','zone_j_cost_c1', ...
        's4_e_cost_c1','s4_f_cost_c1','s4_g_cost_c1','s4_k_cost_c1', ...
        'abc_cap_factor','x_spine_multiplier','scenario_count','success_count', ...
        'sum_classic_interface_objective','sum_fixed_scale_interface_objective', ...
        'mean_zone_j_equiv_pg_mw','max_zone_j_equiv_pg_mw', ...
        'mean_s4_equiv_pg_mw','max_s4_equiv_pg_mw', ...
        'max_abs_interface_residual_mw','max_branch_overload_count', ...
        'max_voltage_bound_count'});
    summary = append_table(summary, row);
end
writetable(summary, options.summary_file);
outputs = struct('summary_file', options.summary_file, 'row_count', height(summary));
end

function scale = scale_for_interface(scales, name, min_scale)
idx = find(scales.interface_name == name, 1);
if isempty(idx) || ~isfinite(scales.fixed_scale_mw(idx)) || scales.fixed_scale_mw(idx) <= 0
    scale = min_scale;
else
    scale = max(min_scale, scales.fixed_scale_mw(idx));
end
end

function out = append_table(out, row)
if isempty(out)
    out = row;
else
    out = [out; row]; %#ok<AGROW>
end
end
