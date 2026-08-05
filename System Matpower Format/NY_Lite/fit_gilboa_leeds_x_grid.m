function outputs = fit_gilboa_leeds_x_grid(options)
%FIT_GILBOA_LEEDS_X_GRID One-dimensional public-target X search.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
if ~isfield(options, 'scenario_file')
    options.scenario_file = fullfile(helper_dir, 'nyiso_public_scenarios.csv');
end
if ~isfield(options, 'output_file')
    options.output_file = fullfile(helper_dir, 'gilboa_leeds_x_grid_search.csv');
end
if ~isfield(options, 'best_file')
    options.best_file = fullfile(helper_dir, 'gilboa_leeds_x_grid_best.csv');
end
if ~isfield(options, 'x_grid')
    x0 = 0.01997;
    options.x_grid = x0 * linspace(0.70, 1.30, 25);
end
if ~isfield(options, 'lambda'), options.lambda = 0.01; end

if exist(options.scenario_file, 'file') ~= 2
    build_nyiso_public_targets();
end
scenarios = readtable(options.scenario_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
mpopt = mpoption( ...
    'verbose', 0, ...
    'out.all', 0, ...
    'opf.ac.solver', 'IPOPT', ...
    'opf.flow_lim', 'S', ...
    'opf.violation', 1e-6, ...
    'opf.use_vg', 0, ...
    'opf.ignore_angle_lim', 0);

x0 = 0.01997;
rows = table();
best_J = Inf;
best_x = NaN;
for k = 1:numel(options.x_grid)
    x_value = options.x_grid(k);
    J_total = options.lambda * log(x_value / x0)^2;
    success_count = 0;
    scenario_count = height(scenarios);
    max_overload = 0;
    for s = 1:height(scenarios)
        scenario_id = string(scenarios.scenario_id(s));
        try
            [J, ok, overload] = scenario_objective(scenario_id, x_value, mpopt);
            if ok, success_count = success_count + 1; end
            J_total = J_total + J;
            max_overload = max(max_overload, overload);
        catch
            J_total = J_total + 1e6;
        end
    end
    all_success = success_count == scenario_count;
    row = table(x_value, J_total, success_count, scenario_count, double(all_success), max_overload, ...
        'VariableNames', {'gilboa_leeds_x','objective','success_count', ...
            'scenario_count','all_success','max_rate_a_overload_mva'});
    rows = [rows; row]; %#ok<AGROW>
    if all_success && J_total < best_J
        best_J = J_total;
        best_x = x_value;
    end
end

writetable(rows, options.output_file);
best = table(best_x, best_J, best_x / x0, ...
    'VariableNames', {'best_gilboa_leeds_x','best_objective','x_over_seed'});
writetable(best, options.best_file);
outputs = struct('output_file', options.output_file, 'best_file', options.best_file, ...
    'best_x', best_x, 'best_objective', best_J);
end

function [J, ok, max_overload] = scenario_objective(scenario_id, x_value, mpopt)
define_constants;
mpc = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
[mpc, ~] = apply_nyiso_zonal_loads(mpc, scenario_id, 1.0, ...
    struct('preserve_total_ny_load', true));
candidates = ny_lite_tieline_candidates();
candidates = override_tieline_x(candidates, 'GILBOA_LEEDS', x_value);
[mpc, ~] = add_ny_lite_tielines(mpc, 'core', ...
    struct('candidate_override', candidates));
results = runopf(mpc, mpopt);
ok = results.success == 1;
sf = sqrt(results.branch(:, PF).^2 + results.branch(:, QF).^2);
st = sqrt(results.branch(:, PT).^2 + results.branch(:, QT).^2);
smax = max(sf, st);
rate = results.branch(:, RATE_A);
rated = rate > 0;
max_overload = max([0; smax(rated) - rate(rated)]);
if ~ok
    J = 1e6 + max_overload^2;
    return;
end
flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
targets = read_public_interface_targets(scenario_id);
[J, ~] = interface_target_objective(flows, targets);
end
