function outputs = fit_s11_non_dlr_equivalent_admittance(options)
%FIT_S11_NON_DLR_EQUIVALENT_ADMITTANCE Fit the non-DLR S11 equivalent.
%   OUTPUTS = FIT_S11_NON_DLR_EQUIVALENT_ADMITTANCE(OPTIONS) fits a sparse,
%   topology-preserving correction against the 2019 same-snapshot current,
%   active-loss, corrected-network-Q, and local complex Ward targets.
%
%   The fit ranks non-DLR rows by solved complex series burden, changes only
%   the selected rows, adds retained-bus shunt terms at Wood Street (9002)
%   and Pleasant Valley (73), and permits one non-DLR path-specific X
%   override for Gilboa--Leeds. The five direct physical DLR branches are
%   frozen and verified exactly. Candidate verification may use the same
%   no-slack hard AC-feasibility projection as the public S11 builder.
%
%   The local source target is formed explicitly as
%       Yeq = Yrr - Yre * (Yee \ Yer)
%   at Gilboa, Leeds, Pleasant Valley, Wood Street, and Millwood. Both real
%   and imaginary Ward residuals enter the constrained least-squares fit.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
options = defaults(options, helper_dir);
addpath(fileparts(helper_dir));
addpath(helper_dir);
define_constants;

if isempty(options.baseline_outputs)
    baseline = run_s11_2019_same_snapshot_benchmark( ...
        struct('write_output', false));
else
    baseline = options.baseline_outputs;
end
validate_baseline(baseline);

physical = baseline.physical_map.branch_classification == "physical_circuit";
[ranking, selected_idx] = rank_non_dlr_branches( ...
    baseline, physical, options.selected_branch_count);
anchor_map = ward_anchor_map();
source_ward = local_ward_equivalent( ...
    baseline.source_case, anchor_map.source_bus);
baseline_ward = local_ward_equivalent( ...
    baseline.reduced_input, anchor_map.reduced_bus);
baseline_ward_error = ward_error(source_ward, baseline_ward);
wood_transfer_target_mw = source_wood_transfer_target(baseline);

context = struct();
context.base_case = baseline.reduced_input;
context.branch_map = baseline.physical_map;
context.selected_idx = selected_idx;
context.source_current_kA = baseline.circuit_comparison.source_series_current_kA;
context.source_active_loss_mw = baseline.source_metrics.active_network_loss_mw;
context.source_net_q_mvar = baseline.source_metrics.net_network_q_mvar;
context.source_ward = source_ward;
context.reduced_anchor_bus = anchor_map.reduced_bus;
context.wood_transfer_target_mw = wood_transfer_target_mw;
context.ward_weight = options.ward_weight;
context.wood_closure_weight = options.wood_closure_weight;
context.regularization_weight = options.regularization_weight;
context.gate_percent = options.gate_percent;
context.zero_tolerance = options.zero_tolerance;
context.opf_solver = options.opf_solver;
context.opf_max_iterations = options.opf_max_iterations;
context.pf_options = mpoption('verbose', 0, 'out.all', 0, ...
    'pf.enforce_q_lims', 1);

x0 = options.initial_parameters(:);
initial = evaluate_parameters(x0, context);
x = x0;
solver_output = struct('algorithm', 'not_run', 'iterations', 0, ...
    'funcCount', 1, 'message', 'Optimization disabled.');
exitflag = NaN;
resnorm = sum(initial.residual.^2);
if options.run_optimization
    solver_options = optimoptions('lsqnonlin', ...
        'Display', char(options.solver_display), ...
        'MaxFunctionEvaluations', options.max_function_evaluations, ...
        'MaxIterations', options.max_iterations, ...
        'FiniteDifferenceType', 'forward', ...
        'TypicalX', x0, ...
        'FunctionTolerance', 1e-9, ...
        'StepTolerance', 1e-7, ...
        'OptimalityTolerance', 1e-7);
    objective = @(candidate) objective_residual(candidate, context);
    [candidate, candidate_resnorm, ~, candidate_exitflag, candidate_output] = ...
        lsqnonlin(objective, x0, options.lower_bounds(:), ...
        options.upper_bounds(:), solver_options);
    candidate_evaluation = evaluate_parameters(candidate, context);
    if choose_candidate(initial, candidate_evaluation, ...
            resnorm, candidate_resnorm, options.gate_percent)
        x = candidate;
        resnorm = candidate_resnorm;
        final_evaluation = candidate_evaluation;
    else
        final_evaluation = initial;
    end
    exitflag = candidate_exitflag;
    solver_output = candidate_output;
else
    final_evaluation = initial;
end

if ~exist('final_evaluation', 'var')
    final_evaluation = evaluate_parameters(x, context);
end
correction = correction_from_parameters(x, selected_idx, anchor_map, ...
    wood_transfer_target_mw, ranking, options);

% Verify through the public benchmark integration hook, not only the
% objective's local evaluator.
verified = run_s11_2019_same_snapshot_benchmark(struct( ...
    'write_output', false, 'gate_percent', options.gate_percent, ...
    'non_dlr_correction', correction));
fitted_ward = local_ward_equivalent( ...
    verified.reduced_input, anchor_map.reduced_bus);
fitted_ward_error = ward_error(source_ward, fitted_ward);
ward_summary = build_ward_summary( ...
    baseline_ward_error, fitted_ward_error);
parameter_summary = build_parameter_summary(x, options);

mandatory_pass = verified.all_mandatory_gates_pass && ...
    verified.reduced_pf_success && ...
    verified.correction_application.dlr_frozen_exact;
ward_nonworsening = fitted_ward_error.complex_relative_frobenius <= ...
    baseline_ward_error.complex_relative_frobenius;
correction.fitted_parameter_summary = parameter_summary;
correction.ward_summary = ward_summary;
correction.ward_nonworsening = ward_nonworsening;
correction.validation_summary = verified.summary;
correction.physical_circuit_validation = verified.circuit_comparison;
correction.source_q_status = verified.source_q_status;
correction.reduced_q_status = verified.reduced_q_status;
correction.all_mandatory_gates_pass = mandatory_pass;
if options.require_all_gates && ~mandatory_pass
    warning('fit_s11_non_dlr_equivalent_admittance:GatesNotMet', ...
        ['The best physically constrained correction did not pass every ' ...
        '15%% same-snapshot gate. Inspect outputs; no result was concealed.']);
end

if options.write_outputs
    output_paths = {options.correction_file, options.summary_file, ...
        options.change_file, options.ranking_file, options.ward_file, ...
        options.parameter_file};
    for k = 1:numel(output_paths)
        folder = fileparts(char(output_paths{k}));
        if ~isempty(folder) && ~isfolder(folder)
            error('fit_s11_non_dlr_equivalent_admittance:OutputDirectory', ...
                'Output directory does not exist: %s', folder);
        end
    end
    save(char(options.correction_file), 'correction');
    writetable(verified.summary, char(options.summary_file));
    writetable(verified.correction_application.branch_changes, ...
        char(options.change_file));
    writetable(ranking, char(options.ranking_file));
    writetable(ward_summary, char(options.ward_file));
    writetable(parameter_summary, char(options.parameter_file));
end

outputs = struct();
outputs.correction = correction;
outputs.parameter_summary = parameter_summary;
outputs.branch_ranking = ranking;
outputs.selected_branch_indices = selected_idx;
outputs.anchor_map = anchor_map;
outputs.source_ward_admittance = source_ward;
outputs.baseline_ward_admittance = baseline_ward;
outputs.fitted_ward_admittance = fitted_ward;
outputs.ward_summary = ward_summary;
outputs.ward_nonworsening = ward_nonworsening;
outputs.wood_transfer_target_mw = wood_transfer_target_mw;
outputs.initial_evaluation = initial;
outputs.final_evaluation = final_evaluation;
outputs.verified_benchmark = verified;
outputs.solver_exitflag = exitflag;
outputs.solver_resnorm = resnorm;
outputs.solver_output = solver_output;
outputs.all_mandatory_gates_pass = mandatory_pass;
outputs.output_written = options.write_outputs;
outputs.correction_file = options.correction_file;
outputs.summary_file = options.summary_file;
outputs.change_file = options.change_file;
outputs.ranking_file = options.ranking_file;
outputs.ward_file = options.ward_file;
outputs.parameter_file = options.parameter_file;
end

function options = defaults(options, helper_dir)
items = { ...
    'baseline_outputs', []; ...
    'selected_branch_count', 20; ...
    'initial_parameters', [0.1 0.21504694904556 1.5 ...
        3.02860543051724 441.236870704074 -13.068841922981 1200]; ...
    'lower_bounds', [0.1 0.1 0.5 0.5 300 -500 0]; ...
    'upper_bounds', [0.8 0.8 1.5 4.0 500 1000 1600]; ...
    'run_optimization', true; ...
    'max_function_evaluations', 180; ...
    'max_iterations', 35; ...
    'solver_display', "off"; ...
    'gate_percent', 15; ...
    'ward_weight', 2e-1; ...
    'wood_closure_weight', 5e-2; ...
    'regularization_weight', 1e-4; ...
    'zero_tolerance', 1e-9; ...
    'opf_solver', "IPOPT"; ...
    'opf_max_iterations', 1000; ...
    'require_all_gates', true; ...
    'write_outputs', false; ...
    'correction_file', string(fullfile(helper_dir, ...
        's11_non_dlr_admittance_correction.mat')); ...
    'summary_file', string(fullfile(helper_dir, ...
        's11_non_dlr_admittance_fit_summary.csv')); ...
    'change_file', string(fullfile(helper_dir, ...
        's11_non_dlr_admittance_changes.csv')); ...
    'ranking_file', string(fullfile(helper_dir, ...
        's11_non_dlr_admittance_branch_ranking.csv')); ...
    'ward_file', string(fullfile(helper_dir, ...
        's11_non_dlr_admittance_ward_summary.csv')); ...
    'parameter_file', string(fullfile(helper_dir, ...
        's11_non_dlr_admittance_parameters.csv'))};
for k = 1:size(items, 1)
    if ~isfield(options, items{k, 1})
        options.(items{k, 1}) = items{k, 2};
    end
end
validateattributes(options.selected_branch_count, {'numeric'}, ...
    {'scalar','integer','>=',1,'<=',70});
validateattributes(options.initial_parameters, {'numeric'}, ...
    {'vector','numel',7,'finite'});
validateattributes(options.lower_bounds, {'numeric'}, ...
    {'vector','numel',7,'finite'});
validateattributes(options.upper_bounds, {'numeric'}, ...
    {'vector','numel',7,'finite'});
if any(options.initial_parameters < options.lower_bounds) || ...
        any(options.initial_parameters > options.upper_bounds) || ...
        any(options.lower_bounds >= options.upper_bounds)
    error('fit_s11_non_dlr_equivalent_admittance:ParameterBounds', ...
        'Initial parameters and bounds are inconsistent.');
end
numeric_positive = {'max_function_evaluations','max_iterations', ...
    'gate_percent','zero_tolerance','opf_max_iterations'};
for k = 1:numel(numeric_positive)
    validateattributes(options.(numeric_positive{k}), {'numeric'}, ...
        {'scalar','positive','finite'});
end
weights = {'ward_weight','wood_closure_weight','regularization_weight'};
for k = 1:numel(weights)
    validateattributes(options.(weights{k}), {'numeric'}, ...
        {'scalar','nonnegative','finite'});
end
options.run_optimization = logical(options.run_optimization);
options.require_all_gates = logical(options.require_all_gates);
options.write_outputs = logical(options.write_outputs);
options.solver_display = string(options.solver_display);
options.opf_solver = string(options.opf_solver);
path_fields = {'correction_file','summary_file','change_file','ranking_file', ...
    'ward_file','parameter_file'};
for k = 1:numel(path_fields)
    options.(path_fields{k}) = string(options.(path_fields{k}));
end
end

function validate_baseline(baseline)
required = {'reduced_input','reduced_pf','source_case','source_pf', ...
    'physical_map','circuit_comparison','source_metrics'};
if ~isstruct(baseline) || ~all(isfield(baseline, required))
    error('fit_s11_non_dlr_equivalent_admittance:Baseline', ...
        'baseline_outputs is not an S11 same-snapshot benchmark result.');
end
if ~baseline.source_pf_success || ~baseline.reduced_pf_success
    error('fit_s11_non_dlr_equivalent_admittance:BaselinePF', ...
        'Both baseline Q-limit power flows must converge before fitting.');
end
end

function [ranking, selected] = rank_non_dlr_branches(baseline, physical, count)
define_constants;
[loss, fchg, tchg] = get_losses(baseline.reduced_pf);
p = real(loss);
q = imag(loss);
charging = real(fchg + tchg);
p_score = abs(p) / max(abs(baseline.source_metrics.active_network_loss_mw), 1);
q_score = abs(q) / max(abs(baseline.source_metrics.net_network_q_mvar), 1);
score = p_score + q_score;
score(physical) = -Inf;
[~, order] = sort(score, 'descend');
order = order(isfinite(score(order)));
if count > numel(order)
    error('fit_s11_non_dlr_equivalent_admittance:SelectionCount', ...
        'Requested more correction rows than available non-DLR branches.');
end
selected = order(1:count);
rank = nan(size(score));
rank(order) = (1:numel(order))';
is_selected = false(size(score));
is_selected(selected) = true;
ranking = table((1:numel(score))', rank, ...
    baseline.physical_map.reduced_from_bus, ...
    baseline.physical_map.reduced_to_bus, ...
    baseline.physical_map.branch_classification, p, q, charging, ...
    score, is_selected, ...
    'VariableNames', {'branch_index','burden_rank','from_bus','to_bus', ...
    'branch_classification','baseline_active_loss_mw', ...
    'baseline_series_q_mvar','baseline_charging_mvar', ...
    'normalized_complex_burden_score','selected_for_sparse_fit'});
ranking = sortrows(ranking, 'burden_rank');
end

function anchors = ward_anchor_map()
anchors = table([38;39;73;9002;74], [1227;818;651;902;897], ...
    ["GILBOA";"LEEDS";"PLEASANT_VALLEY";"WOOD_STREET";"MILLWOOD"], ...
    'VariableNames', {'reduced_bus','source_bus','anchor_name'});
end

function yeq = local_ward_equivalent(mpc, external_bus_ids)
internal = ext2int(mpc);
[found, retained] = ismember(double(external_bus_ids), ...
    double(internal.order.bus.i2e));
if any(~found)
    error('fit_s11_non_dlr_equivalent_admittance:WardAnchor', ...
        'A Ward anchor bus is missing from the supplied case.');
end
[ybus, ~, ~] = makeYbus(internal);
eliminated = setdiff((1:size(ybus, 1))', retained, 'stable');
yee = ybus(eliminated, eliminated);
yer = ybus(eliminated, retained);
yre = ybus(retained, eliminated);
yeq = ybus(retained, retained) - yre * (yee \ yer);
end

function errors = ward_error(target, actual)
errors = struct();
errors.real_relative_frobenius = norm(real(actual-target), 'fro') / ...
    max(norm(real(target), 'fro'), eps);
errors.imag_relative_frobenius = norm(imag(actual-target), 'fro') / ...
    max(norm(imag(target), 'fro'), eps);
errors.complex_relative_frobenius = norm(actual-target, 'fro') / ...
    max(norm(target, 'fro'), eps);
end

function target = source_wood_transfer_target(baseline)
define_constants;
map = baseline.physical_map;
physical = map.branch_classification == "physical_circuit";
pv = physical & contains(map.physical_circuit_id, "651_902");
wm = physical & contains(map.physical_circuit_id, "902_897");
pv_idx = map.source_branch_index(pv);
wm_idx = map.source_branch_index(wm);
target = sum(-baseline.source_pf.branch(pv_idx, PT)) - ...
    sum(baseline.source_pf.branch(wm_idx, PF));
if ~isfinite(target) || target <= 0
    error('fit_s11_non_dlr_equivalent_admittance:WoodTransfer', ...
        'The source Wood Street eliminated-network transfer is invalid.');
end
end

function correction = correction_from_parameters(x, selected, anchors, ...
        wood_target, ranking, options)
correction = struct();
correction.schema_version = 'S11_NON_DLR_EQUIVALENT_V2';
correction.method = ['Sparse topology-preserving complex-admittance fit; ' ...
    'local Ward/Kron target plus 2019 current/loss/net-Q gates and a ' ...
    'hard-AC-feasibility verified retained-bus shunt refit'];
correction.scaled_branch_indices = selected(:);
correction.selected_r_scale = x(1);
correction.selected_x_scale = x(2);
correction.selected_b_scale = x(3);
correction.branch_overrides = table(1, NaN, x(4), NaN, NaN, NaN, ...
    "Gilboa path non-DLR X override; physical branch 69 remains frozen", ...
    'VariableNames', {'branch_index','r_scale','x_scale','b_scale', ...
    'tap_ratio','shift_deg','reason'});
correction.bus_shunt_corrections = table([9002;73], [x(5);0], [x(6);x(7)], ...
    ["Wood Street Ward diagonal for eliminated transfer/network Q"; ...
     "Retained Pleasant Valley shunt refit for source net-Q/current closure"], ...
    'VariableNames', {'bus_id','delta_gs_mw','delta_bs_mvar','reason'});
correction.ward_anchor_map = anchors;
correction.source_wood_eliminated_transfer_mw = wood_target;
correction.selected_branch_count = numel(selected);
correction.selection_rule = ['Top non-DLR solved complex series-burden rows; ' ...
    'local real/imag Ward residual retained in objective'];
correction.gate_percent = options.gate_percent;
correction.parameter_bounds = table(options.lower_bounds(:), ...
    options.upper_bounds(:), 'VariableNames', {'lower','upper'}, ...
    'RowNames', parameter_names());
if isempty(ranking)
    correction.selected_branch_ranking = table();
else
    correction.selected_branch_ranking = ranking( ...
        ranking.selected_for_sparse_fit, :);
end
correction.dlr_policy = 'Five direct physical circuit R/X/B rows frozen exactly.';
end

function residual = objective_residual(x, context)
evaluation = evaluate_parameters(x, context);
residual = evaluation.residual;
end

function evaluation = evaluate_parameters(x, context)
correction = correction_from_parameters(x, context.selected_idx, ...
    ward_anchor_map(), context.wood_transfer_target_mw, table(), ...
    struct('gate_percent', context.gate_percent, ...
    'lower_bounds', nan(1,7), 'upper_bounds', nan(1,7)));
try
    [candidate, application] = apply_s11_non_dlr_equivalent_correction( ...
        context.base_case, context.branch_map, correction);
catch err
    evaluation = failed_evaluation(x, err.message);
    return;
end
try
    [result, success] = runpf(candidate, context.pf_options);
catch
    result = candidate;
    success = false;
end
if ~success
    physical = context.branch_map.branch_classification == "physical_circuit";
    trusted = false(size(candidate.branch, 1), 1);
    trusted(double(context.branch_map.branch_index(physical))) = true;
    projection = project_s11_hard_ac_feasibility(candidate, struct( ...
        'opf_solver', context.opf_solver, ...
        'max_iterations', context.opf_max_iterations), trusted);
    if projection.success
        candidate = projection.input_case;
        try
            [result, success] = runpf(candidate, context.pf_options);
        catch
            result = candidate;
            success = false;
        end
    end
end
if ~success
    evaluation = failed_evaluation(x, ...
        'Q-limit power flow and hard AC feasibility projection failed.');
    return;
end

physical = context.branch_map.branch_classification == "physical_circuit";
map = sortrows(context.branch_map(physical, :), ...
    {'corridor_name','source_circuit_id'});
currents = compute_branch_currents_kA(result, context.branch_map);
actual_current = currents.series_current_kA(map.branch_index);
[metrics, q_status] = network_and_q_metrics(candidate, result);
ward = local_ward_equivalent(candidate, context.reduced_anchor_bus);
ward_errors = ward_error(context.source_ward, ward);
wood_bi = find(result.bus(:, 1) == 9002, 1);
wood_consumption = result.bus(wood_bi, 5) * result.bus(wood_bi, 8)^2;

relative_current = (actual_current-context.source_current_kA) ./ ...
    max(abs(context.source_current_kA), context.zero_tolerance);
relative_loss = (metrics.active_network_loss_mw- ...
    context.source_active_loss_mw) / abs(context.source_active_loss_mw);
relative_q = (metrics.net_network_q_mvar-context.source_net_q_mvar) / ...
    abs(context.source_net_q_mvar);
wood_residual = (wood_consumption-context.wood_transfer_target_mw) / ...
    context.wood_transfer_target_mw;
regularization = [x(1)-1; x(2)-1; x(3)-1; (x(4)-1)/3; ...
    x(6)/1000; x(7)/1600];
residual = [relative_current; relative_loss; relative_q; ...
    sqrt(context.ward_weight) * ward_errors.real_relative_frobenius; ...
    sqrt(context.ward_weight) * ward_errors.imag_relative_frobenius; ...
    sqrt(context.wood_closure_weight) * wood_residual; ...
    sqrt(context.regularization_weight) * regularization];

percent = 100 * abs([relative_current; relative_loss; relative_q]);
evaluation = struct();
evaluation.parameters = x(:);
evaluation.success = true;
evaluation.message = 'Hard-feasible Q-limit PF converged.';
evaluation.corrected_input = candidate;
evaluation.result = result;
evaluation.application = application;
evaluation.current_kA = actual_current;
evaluation.current_percent_error = 100 * abs(relative_current);
evaluation.active_loss_mw = metrics.active_network_loss_mw;
evaluation.active_loss_percent_error = 100 * abs(relative_loss);
evaluation.net_network_q_mvar = metrics.net_network_q_mvar;
evaluation.net_network_q_percent_error = 100 * abs(relative_q);
evaluation.maximum_mandatory_percent_error = max(percent);
evaluation.all_mandatory_gates_pass = ...
    all(percent <= context.gate_percent) && application.dlr_frozen_exact;
evaluation.ward_error = ward_errors;
evaluation.wood_shunt_consumption_mw = wood_consumption;
evaluation.q_status = q_status;
evaluation.metrics = metrics;
evaluation.residual = residual;
end

function evaluation = failed_evaluation(x, message)
evaluation = struct();
evaluation.parameters = x(:);
evaluation.success = false;
evaluation.message = message;
evaluation.maximum_mandatory_percent_error = Inf;
evaluation.all_mandatory_gates_pass = false;
evaluation.residual = 50 * ones(16, 1);
end

function [metrics, status] = network_and_q_metrics(input_case, result)
define_constants;
[loss, fchg, tchg] = get_losses(result);
online = result.gen(:, GEN_STATUS) > 0;
metrics = struct();
metrics.active_network_loss_mw = sum(real(loss)) + ...
    sum(result.bus(:, GS) .* result.bus(:, VM).^2);
metrics.net_network_q_mvar = sum(imag(loss)) - sum(real(fchg+tchg)) - ...
    sum(result.bus(:, BS) .* result.bus(:, VM).^2);
metrics.active_identity_residual_mw = ...
    sum(result.gen(online, PG))-sum(result.bus(:, PD))- ...
    metrics.active_network_loss_mw;
metrics.reactive_identity_residual_mvar = ...
    sum(result.gen(online, QG))-sum(result.bus(:, QD))- ...
    metrics.net_network_q_mvar;
variable_q = online & result.gen(:, QMAX)-result.gen(:, QMIN) > 1e-3;
at_limit = abs(result.gen(:, QG)-result.gen(:, QMIN)) <= 1e-3 | ...
    abs(result.gen(:, QG)-result.gen(:, QMAX)) <= 1e-3;
status = struct('variable_q_generator_count', nnz(variable_q), ...
    'q_saturation_count', nnz(variable_q & at_limit));
initial_ids = input_case.bus(ismember(input_case.bus(:, BUS_TYPE), ...
    [PV REF]), BUS_I);
[found, bi] = ismember(initial_ids, result.bus(:, BUS_I));
became_pq = false(size(found));
became_pq(found) = result.bus(bi(found), BUS_TYPE) == PQ;
status.pv_to_pq_conversion_count = nnz(became_pq);
end

function choose = choose_candidate(initial, candidate, initial_resnorm, ...
        candidate_resnorm, gate_percent)
if ~candidate.success
    choose = false;
elseif candidate.maximum_mandatory_percent_error <= gate_percent && ...
        initial.maximum_mandatory_percent_error > gate_percent
    choose = true;
elseif initial.maximum_mandatory_percent_error <= gate_percent && ...
        candidate.maximum_mandatory_percent_error > gate_percent
    choose = false;
else
    choose = candidate_resnorm < initial_resnorm;
end
end

function rows = build_ward_summary(before, after)
quantity = ["real_relative_frobenius";"imag_relative_frobenius"; ...
    "complex_relative_frobenius"];
baseline_value = [before.real_relative_frobenius; ...
    before.imag_relative_frobenius; before.complex_relative_frobenius];
fitted_value = [after.real_relative_frobenius; ...
    after.imag_relative_frobenius; after.complex_relative_frobenius];
rows = table(quantity, baseline_value, fitted_value, ...
    fitted_value-baseline_value, ...
    'VariableNames', {'quantity','baseline_value','fitted_value','change'});
end

function rows = build_parameter_summary(x, options)
rows = table(string(parameter_names())', x(:), options.lower_bounds(:), ...
    options.upper_bounds(:), ...
    'VariableNames', {'parameter','fitted_value','lower_bound','upper_bound'});
end

function names = parameter_names()
names = {'selected_r_scale','selected_x_scale','selected_b_scale', ...
    'gilboa_path_branch_1_x_scale','wood_street_delta_gs_mw', ...
    'wood_street_delta_bs_mvar','pleasant_valley_delta_bs_mvar'};
end
