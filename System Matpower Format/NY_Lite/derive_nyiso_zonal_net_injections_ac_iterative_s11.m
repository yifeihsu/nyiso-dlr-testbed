function [targets, diagnostics] = derive_nyiso_zonal_net_injections_ac_iterative_s11( ...
        mpc, scenario_id, options)
%DERIVE_NYISO_ZONAL_NET_INJECTIONS_AC_ITERATIVE_S11 S11 AC injection closure.
%   [TARGETS, DIAGNOSTICS] = ... (MPC, SCENARIO_ID, OPTIONS) infers zonal
%   active-generation totals while preserving the S11 control-mapped
%   generator rows. Public external equivalents, reference-balance records,
%   and reactive-only controls do not participate in redispatch.
%
%   By default, active controls are read from
%   MPC.userdata.s11.controls.generator_report. OPTIONS.active_gen_idx may be
%   used when constructing or testing a case before that report is attached.
%   Public NYISO interface flows use the raw nyiso_flow_mw column when it is
%   available; set OPTIONS.use_raw_public_targets = false to use the scaled
%   target_flow_mw column instead.
%
%   This function performs standard AC power flows. Hard Q-limit PF and any
%   feasibility projection remain separate S11 diagnostic acceptance checks.

if nargin < 1 || isempty(mpc)
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:MissingCase', ...
        'An already composed S11 operating case is required.');
end
if nargin < 2 || isempty(scenario_id)
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:MissingScenario', ...
        'A public scenario ID is required.');
end
if nargin < 3, options = struct(); end

helper_dir = fileparts(mfilename('fullpath'));
options = defaults(options, helper_dir);
validate_options(options);
define_constants;

scenario_id = string(scenario_id);
mpc = attach_nyiso_zone_metadata(mpc);
[mpc, active_idx, selection_report] = resolve_active_generators(mpc, options);
if isempty(active_idx)
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:NoActiveControls', ...
        'No eligible native active-control generator rows were found.');
end

zones = string(('A':'K')');
model = build_active_model(mpc, active_idx, zones);
if sum(model.adjustable_zone) < 2
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:Participation', ...
        'At least two NYISO zones must have adjustable source-backed controls.');
end

reference_gen = choose_reference_generator(mpc, model, options);
definitions = resolve_interface_definitions(mpc, options);
public_targets = prepare_public_targets(scenario_id, definitions, options);
calibration_mask = logical(public_targets.calibration_eligible);
if ~any(calibration_mask)
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:NoCalibrationInterfaces', ...
        'No interface rows are eligible for S11 calibration.');
end
accuracy_scale = interface_accuracy_scales( ...
    public_targets.interface_name, options);

load_mw = zonal_load(mpc, zones);
original_generation = zonal_generation_from_case(mpc, model, zones);
[source_pg_prior, source_pg_prior_source] = zonal_source_pg_prior(mpc, model, zones, ...
    original_generation);
% The control mapper deliberately preserves the scenario's zonal dispatch.
% Source-snapshot PG is retained as provenance and, after total-generation
% balancing, as the mandatory dispatch-movement baseline. It is not the
% operating seed for a different public scenario. Generalize the S8
% constrained-DC inference to the mapped controls, then let the AC loop
% perform only the loss/interface correction around that inferred dispatch.
fixed_seed_generation = fixed_generation_total(mpc, model);
initial_total = sum(load_mw) * (1 + options.initial_loss_fraction) - ...
    fixed_seed_generation;
initial_total = min(max(initial_total, sum(model.zone_pmin)), ...
    sum(model.zone_pmax));
scenario_balance_prior = project_generation_total(original_generation, ...
    model.zone_pmin, model.zone_pmax, initial_total);
source_balance_prior = project_generation_total(source_pg_prior, ...
    model.zone_pmin, model.zone_pmax, initial_total);
switch options.initial_dispatch_method
    case "constrained_dc_interface"
        [generation, initial_dispatch] = constrained_dc_interface_seed( ...
            mpc, model, zones, scenario_balance_prior, initial_total, ...
            reference_gen, definitions, public_targets, calibration_mask, ...
            accuracy_scale, options);
        initial_dispatch_source = "constrained_dc_interface_from_scenario_dispatch";
    case "scenario_balance_projection"
        generation = scenario_balance_prior;
        initial_dispatch = struct('method', "scenario_balance_projection", ...
            'generation_mw', generation);
        initial_dispatch_source = "scenario_balance_projection";
    case "source_pg_prior"
        generation = source_balance_prior;
        initial_dispatch = struct('method', "source_pg_prior", ...
            'generation_mw', generation);
        initial_dispatch_source = source_pg_prior_source;
    otherwise
        error('derive_nyiso_zonal_net_injections_ac_iterative_s11:InitialDispatch', ...
            'Unknown initial_dispatch_method: %s', options.initial_dispatch_method);
end

pfopt = options.pf_options;
if isempty(pfopt)
    pfopt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 0);
end
inferred_initial_generation = generation;
[generation, initial_warm_result, continuation_history] = ...
    establish_initial_ac_seed(mpc, model, zones, generation, ...
    reference_gen, pfopt, scenario_id, options);
ac_seed_generation = generation;
initial_generation = inferred_initial_generation;
prior = inferred_initial_generation;

history = table();
sensitivity_history = table();
participation_history = table();
last_exitflag = NaN;
last_step_norm = NaN;
accepted_steps = 0;
stop_reason = "maximum_iterations";
last_feasible_result = initial_warm_result;

for iteration = 1:options.max_iterations
    if iteration == 1 && ~isempty(initial_warm_result)
        pre_result = initial_warm_result;
    else
        [pre_result, ~, ~] = run_generation(mpc, model, zones, generation, ...
            reference_gen, pfopt, last_feasible_result);
    end
    require_success(pre_result, scenario_id, iteration, 'pre-loss AC PF');
    pre_metrics = physical_metrics(pre_result, model, generation);

    required_active = pre_metrics.required_active_generation_mw;
    loss_adjustment = required_active - sum(generation);
    alpha_loss = loss_participation(generation, model.zone_pmin, ...
        model.zone_pmax, loss_adjustment, model.adjustable_zone);
    proposed_balanced_generation = project_generation_total(generation + ...
        alpha_loss * loss_adjustment, model.zone_pmin, model.zone_pmax, ...
        required_active);

    [base_result, balanced_generation] = accept_loss_balance_step( ...
        mpc, model, zones, generation, proposed_balanced_generation, ...
        reference_gen, pfopt, pre_result, options);
    require_success(base_result, scenario_id, iteration, 'loss-balanced AC PF');
    last_feasible_result = base_result;
    base_metrics = physical_metrics(base_result, model, balanced_generation);
    base_flow = interface_vector(base_result, definitions, public_targets);
    residual = base_flow - public_targets.selected_target_flow_mw;
    objective = huber_objective(residual(calibration_mask), ...
        accuracy_scale(calibration_mask), options.huber_delta);
    if interface_tolerance_pass(residual(calibration_mask), options) && ...
            abs(base_metrics.reference_pickup_mw) < ...
            options.reference_pickup_tolerance_mw
        generation = balanced_generation;
        stop_reason = "interface_and_reference_tolerance";
        history = append_table(history, history_row(scenario_id, iteration, ...
            "converged", base_metrics, objective, residual(calibration_mask), ...
            required_active, loss_adjustment, 0, 0, NaN, true, NaN));
        break;
    end

    alpha_sensitivity = sensitivity_participation(balanced_generation, ...
        model.zone_pmin, model.zone_pmax, model.adjustable_zone);
    [response, finite_steps, sensitivity_rows] = ac_response_matrix( ...
        mpc, model, zones, balanced_generation, reference_gen, pfopt, ...
        base_result, base_flow, definitions, public_targets, ...
        alpha_sensitivity, options, scenario_id, iteration);
    sensitivity_history = append_table(sensitivity_history, sensitivity_rows);
    participation_history = append_table(participation_history, ...
        participation_table(scenario_id, iteration, zones, ...
        balanced_generation, model.zone_pmin, model.zone_pmax, alpha_loss, ...
        alpha_sensitivity, finite_steps));

    [delta_generation, exitflag] = solve_ac_redispatch( ...
        response(calibration_mask, :), residual(calibration_mask), ...
        balanced_generation, prior, model.zone_pmin, model.zone_pmax, ...
        accuracy_scale(calibration_mask), model.adjustable_zone, options);
    last_exitflag = exitflag;
    proposed_norm = norm(delta_generation, inf);

    [accepted, next_generation, acceptance_factor, accepted_norm, ...
        accepted_result] = ...
        accept_redispatch_step(mpc, model, zones, balanced_generation, ...
        delta_generation, reference_gen, pfopt, base_result, definitions, ...
        public_targets, calibration_mask, accuracy_scale, objective, options);
    last_step_norm = accepted_norm;
    if accepted
        accepted_steps = accepted_steps + 1;
        last_feasible_result = accepted_result;
    end

    history = append_table(history, history_row(scenario_id, iteration, ...
        "iterate", base_metrics, objective, residual(calibration_mask), ...
        required_active, loss_adjustment, proposed_norm, accepted_norm, ...
        acceptance_factor, accepted, exitflag));

    if ~accepted
        generation = balanced_generation;
        stop_reason = "no_improving_redispatch_step";
        break;
    end
    generation = next_generation;
    if accepted_norm <= options.generation_step_tolerance_mw
        stop_reason = "generation_step_tolerance";
        break;
    end
end

% Close the remaining active-power mismatch so final reference pickup is
% below one MW without changing external schedules.
for k = 1:options.final_loss_iterations
    [probe, ~, ~] = run_generation(mpc, model, zones, generation, ...
        reference_gen, pfopt, last_feasible_result);
    require_success(probe, scenario_id, options.max_iterations + k, ...
        'final loss-closure PF');
    last_feasible_result = probe;
    metrics = physical_metrics(probe, model, generation);
    if abs(metrics.reference_pickup_mw) < ...
            options.reference_pickup_tolerance_mw
        break;
    end
    required_active = metrics.required_active_generation_mw;
    delta_total = required_active - sum(generation);
    alpha_loss = loss_participation(generation, model.zone_pmin, ...
        model.zone_pmax, delta_total, model.adjustable_zone);
    proposed_generation = project_generation_total(generation + ...
        alpha_loss * delta_total, ...
        model.zone_pmin, model.zone_pmax, required_active);
    [loss_result, accepted_generation] = accept_loss_balance_step( ...
        mpc, model, zones, generation, proposed_generation, reference_gen, ...
        pfopt, probe, options);
    if ~isfield(loss_result, 'success') || ~logical(loss_result.success)
        stop_reason = "final_loss_step_infeasible";
        break;
    end
    generation = accepted_generation;
    last_feasible_result = loss_result;
end

[final_result, final_allocation, final_case] = run_generation( ...
    mpc, model, zones, generation, reference_gen, pfopt, last_feasible_result);
require_success(final_result, scenario_id, options.max_iterations + ...
    options.final_loss_iterations + 1, 'final AC PF');
hard_q_refinement = struct('attempted', false, 'success', false, ...
    'converged', false, 'stop_reason', "not_enabled", ...
    'accepted_step_count', 0);
if logical(options.enable_hard_q_refinement) && ...
        options.hard_q_refinement_iterations > 0
    [q_generation, q_result, q_allocation, q_case, q_history, ...
        q_sensitivity, q_participation, hard_q_refinement] = ...
        hard_q_interface_refinement(final_case, model, zones, generation, prior, ...
        reference_gen, definitions, public_targets, calibration_mask, ...
        accuracy_scale, scenario_id, options);
    history = append_table(history, q_history);
    sensitivity_history = append_table(sensitivity_history, q_sensitivity);
    participation_history = append_table(participation_history, q_participation);
    accepted_steps = accepted_steps + hard_q_refinement.accepted_step_count;
    if hard_q_refinement.success
        generation = q_generation;
        final_result = q_result;
        final_allocation = q_allocation;
        final_case = q_case;
        stop_reason = hard_q_refinement.stop_reason;
    end
end
final_metrics = physical_metrics(final_result, model, generation);
final_flow = interface_vector(final_result, definitions, public_targets);
final_residual = final_flow - public_targets.selected_target_flow_mw;
final_objective = huber_objective(final_residual(calibration_mask), ...
    accuracy_scale(calibration_mask), options.huber_delta);
converged = interface_tolerance_pass(final_residual(calibration_mask), options) && ...
    abs(final_metrics.reference_pickup_mw) < ...
    options.reference_pickup_tolerance_mw;
if converged && stop_reason ~= "interface_and_reference_tolerance"
    stop_reason = "final_loss_closure_tolerance";
end

history = append_table(history, history_row(scenario_id, height(history) + 1, ...
    "final", final_metrics, final_objective, ...
    final_residual(calibration_mask), ...
    final_metrics.required_active_generation_mw, ...
    final_metrics.required_active_generation_mw - sum(generation), ...
    0, 0, NaN, converged, last_exitflag));

actual_generation = zonal_actual_generation(final_result, model, zones);
final_loss_alpha = loss_participation(generation, model.zone_pmin, ...
    model.zone_pmax, 1, model.adjustable_zone);
fixed_by_zone = zonal_fixed_generation(final_case, model, zones);
targets = table(zones, load_mw, fixed_by_zone, original_generation, ...
    initial_generation, repmat(initial_dispatch_source, numel(zones), 1), generation, ...
    actual_generation, generation - original_generation, ...
    generation - initial_generation, ...
    actual_generation - generation, model.zone_pmin, model.zone_pmax, ...
    abs(generation - model.zone_pmin) <= options.bound_tolerance_mw, ...
    abs(generation - model.zone_pmax) <= options.bound_tolerance_mw, ...
    final_loss_alpha, 'VariableNames', {'zone','target_load_mw', ...
    'fixed_nonparticipating_generation_mw', ...
    'original_scenario_generation_mw','seeded_initial_generation_mw', ...
    'seed_prior_source','target_generation_mw','final_actual_generation_mw', ...
    'original_to_final_redispatch_mw','seed_to_final_redispatch_mw', ...
    'final_generation_error_mw', ...
    'pmin_mw','pmax_mw','at_pmin','at_pmax', ...
    'loss_participation_factor'});

interface_table = table(public_targets.interface_name, ...
    public_targets.calibration_eligible, public_targets.target_source, ...
    public_targets.selected_target_flow_mw, final_flow, final_residual, ...
    accuracy_scale, final_residual ./ accuracy_scale, ...
    'VariableNames', {'interface_name','calibration_eligible','target_source', ...
    'target_flow_mw','final_ac_flow_mw','final_ac_residual_mw', ...
    'accuracy_scale_mw','normalized_residual'});
if ismember('nyiso_flow_mw', public_targets.Properties.VariableNames)
    interface_table.raw_public_flow_mw = public_targets.nyiso_flow_mw;
end
if ismember('target_flow_mw', public_targets.Properties.VariableNames)
    interface_table.scaled_public_flow_mw = public_targets.target_flow_mw;
end

diagnostics = struct( ...
    'scenario_id', scenario_id, ...
    'converged', converged, ...
    'stop_reason', stop_reason, ...
    'iteration_count', sum(history.row_type == "iterate"), ...
    'accepted_step_count', accepted_steps, ...
    'use_raw_public_targets', logical(options.use_raw_public_targets), ...
    'flow_tolerance_mw', options.flow_tolerance_mw, ...
    'reference_pickup_tolerance_mw', ...
        options.reference_pickup_tolerance_mw, ...
    'max_zonal_redispatch_step_mw', ...
        options.max_zonal_redispatch_step_mw, ...
    'active_gen_idx', active_idx, ...
    'active_generator_selection', selection_report, ...
    'original_zonal_generation_mw', original_generation, ...
    'source_pg_prior_zonal_generation_mw', source_pg_prior, ...
    'source_pg_prior_source', source_pg_prior_source, ...
    'source_balance_prior_zonal_generation_mw', source_balance_prior, ...
    'scenario_balance_prior_zonal_generation_mw', scenario_balance_prior, ...
    'seeded_zonal_generation_mw', initial_generation, ...
    'ac_feasible_seed_zonal_generation_mw', ac_seed_generation, ...
    'seed_prior_source', initial_dispatch_source, ...
    'initial_dispatch', initial_dispatch, ...
    'initial_continuation_history', continuation_history, ...
    'hard_q_refinement', hard_q_refinement, ...
    'reference_gen_index', reference_gen, ...
    'interface_definitions', definitions, ...
    'public_targets', public_targets, ...
    'history', history, ...
    'sensitivity_history', sensitivity_history, ...
    'participation_history', participation_history, ...
    'interface_table', interface_table, ...
    'final_metrics', final_metrics, ...
    'final_result', final_result, ...
    'final_case', final_case, ...
    'final_allocation', final_allocation, ...
    'last_step_norm_mw', last_step_norm, ...
    'last_solver_exitflag', last_exitflag);
end

function options = defaults(options, helper_dir)
items = { ...
    'interface_target_file', fullfile(helper_dir, 'nyiso_public_interface_targets.csv'); ...
    'accuracy_scale_file', fullfile(helper_dir, 'nyiso_interface_accuracy_scales.csv'); ...
    'interface_map_file', ""; ...
    'interface_definitions', []; ...
    'active_gen_idx', []; ...
    'exclude_gen_idx', []; ...
    'reference_gen_idx', []; ...
    'reference_zone', "J"; ...
    'use_raw_public_targets', true; ...
    'initial_loss_fraction', 0.02; ...
    'initial_dispatch_method', "constrained_dc_interface"; ...
    'dc_sensitivity_step_mw', 25; ...
    'dc_prior_weight', 0.002; ...
    'enable_initial_continuation', true; ...
    'initial_continuation_steps', 8; ...
    'enable_initial_acopf_seed', true; ...
    'initial_acopf_solver', "IPOPT"; ...
    'max_iterations', 20; ...
    'final_loss_iterations', 10; ...
    'max_zonal_redispatch_step_mw', 100; ...
    'ac_sensitivity_step_mw', 25; ...
    'min_sensitivity_step_mw', 0.25; ...
    'prior_weight', 0.002; ...
    'update_weight', 0.0005; ...
    'default_accuracy_mw', 100; ...
    'huber_delta', 1.5; ...
    'flow_tolerance_mw', 100; ...
    'interface_mae_tolerance_mw', 100; ...
    'interface_bias_tolerance_mw', 50; ...
    'reference_pickup_tolerance_mw', 0.5; ...
    'generation_step_tolerance_mw', 0.25; ...
    'enable_hard_q_refinement', true; ...
    'hard_q_refinement_iterations', 20; ...
    'bound_tolerance_mw', 1e-6; ...
    'minimum_objective_improvement', 1e-8; ...
    'line_search_factors', [1 0.5 0.25 0.125]; ...
    'pf_options', []};
for k = 1:size(items, 1)
    if ~isfield(options, items{k, 1})
        options.(items{k, 1}) = items{k, 2};
    end
end
end

function validate_options(options)
options.initial_dispatch_method = string(options.initial_dispatch_method);
if ~ismember(options.initial_dispatch_method, ["constrained_dc_interface", ...
        "scenario_balance_projection", "source_pg_prior"])
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:InitialDispatch', ...
        'Unsupported initial_dispatch_method: %s', options.initial_dispatch_method);
end
validateattributes(options.max_zonal_redispatch_step_mw, {'numeric'}, ...
    {'scalar','finite','>=',50,'<=',100});
validateattributes(options.reference_pickup_tolerance_mw, {'numeric'}, ...
    {'scalar','finite','positive','<',1});
validateattributes(options.flow_tolerance_mw, {'numeric'}, ...
    {'scalar','finite','positive'});
validateattributes(options.interface_mae_tolerance_mw, {'numeric'}, ...
    {'scalar','finite','positive'});
validateattributes(options.interface_bias_tolerance_mw, {'numeric'}, ...
    {'scalar','finite','positive'});
validateattributes(options.initial_loss_fraction, {'numeric'}, ...
    {'scalar','finite','>=',0,'<=',0.2});
validateattributes(options.dc_sensitivity_step_mw, {'numeric'}, ...
    {'scalar','finite','positive'});
validateattributes(options.dc_prior_weight, {'numeric'}, ...
    {'scalar','finite','nonnegative'});
validateattributes(options.initial_continuation_steps, {'numeric'}, ...
    {'scalar','integer','>=',2});
validateattributes(options.enable_initial_acopf_seed, {'logical','numeric'}, ...
    {'scalar'});
validateattributes(options.max_iterations, {'numeric'}, ...
    {'scalar','integer','positive'});
validateattributes(options.hard_q_refinement_iterations, {'numeric'}, ...
    {'scalar','integer','nonnegative'});
validateattributes(options.final_loss_iterations, {'numeric'}, ...
    {'scalar','integer','nonnegative'});
validateattributes(options.line_search_factors, {'numeric'}, ...
    {'vector','finite','positive','<=',1});
end

function [mpc, active_idx, selection] = resolve_active_generators(mpc, options)
define_constants;
report = table();
metadata_active_idx = [];
if isfield(mpc, 'userdata') && isfield(mpc.userdata, 's11') && ...
        isfield(mpc.userdata.s11, 'controls') && ...
        isfield(mpc.userdata.s11.controls, 'generator_report')
    report = mpc.userdata.s11.controls.generator_report;
    if isstruct(report), report = struct2table(report); end
end
if isfield(mpc, 'userdata') && isfield(mpc.userdata, 's11') && ...
        isfield(mpc.userdata.s11, 'controls') && ...
        isfield(mpc.userdata.s11.controls, 'active_dispatch_gen_idx')
    metadata_active_idx = numeric_column( ...
        mpc.userdata.s11.controls.active_dispatch_gen_idx);
end

source = "options.active_gen_idx";
report_gen_idx = [];
report_keep = [];
if ~isempty(report)
    idx_name = find_variable(report, {'reduced_gen_index','gen_index', ...
        'generator_index','model_gen_index','s11_gen_index'});
    if strlength(idx_name) == 0
        error('derive_nyiso_zonal_net_injections_ac_iterative_s11:GeneratorReport', ...
            'The S11 generator report has no reduced generator index column.');
    end
    report_gen_idx = numeric_column(report.(idx_name));
    report_keep = isfinite(report_gen_idx);

    native_name = find_variable(report, {'is_native_active_control', ...
        'active_dispatch_eligible','p_dispatch_eligible'});
    if strlength(native_name) > 0
        report_keep = report_keep & logical_column(report.(native_name));
    else
        role_name = find_variable(report, {'injection_role','reduced_device_type', ...
            'device_class','control_class'});
        if strlength(role_name) > 0
            role = lower(strtrim(string(report.(role_name))));
            report_keep = report_keep & (ismember(role, ["combined_pq_control", ...
                "remote_p_injection","native_active_control", ...
                "active_generation_control"]) | contains(role, "active"));
        end
    end

    status_name = find_variable(report, {'snapshot_effective_status', ...
        'effective_status','online_status','gen_status'});
    if strlength(status_name) > 0
        report_keep = report_keep & logical_column(report.(status_name));
    end
    report_keep = exclude_report_class(report, report_keep, ...
        {'is_external_boundary_equivalent','external_boundary','is_boundary'}, true);
    % Exclude fixed/source boundary-balance equivalents, but retain the one
    % source-backed native generator selected as the operational MATPOWER REF.
    % The control mapper marks that row as both reference-balance and
    % operational-reference; dropping it silently removes its PMAX headroom.
    reference_name = find_variable(report, ...
        {'is_reference_balance','reference_balance','is_reference'});
    operational_name = find_variable(report, ...
        {'is_operational_reference','operational_reference'});
    if strlength(reference_name) > 0
        reference_balance = logical_column(report.(reference_name));
        operational_reference = false(height(report), 1);
        if strlength(operational_name) > 0
            operational_reference = logical_column(report.(operational_name));
        end
        report_keep = report_keep & ...
            ~(reference_balance & ~operational_reference);
    end
    report_keep = exclude_report_class(report, report_keep, ...
        {'is_q_only_control','reactive_only_qs','q_only','reactive_only'}, true);
end

if ~isempty(options.active_gen_idx)
    active_idx = unique(round(double(options.active_gen_idx(:))), 'stable');
elseif ~isempty(metadata_active_idx)
    source = "mpc.userdata.s11.controls.active_dispatch_gen_idx";
    active_idx = unique(round(metadata_active_idx), 'stable');
elseif ~isempty(report)
    source = "mpc.userdata.s11.controls.generator_report";
    active_idx = unique(round(report_gen_idx(report_keep)), 'stable');
else
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:GeneratorReport', ...
        ['Attach mpc.userdata.s11.controls.generator_report or provide ' ...
         'options.active_gen_idx.']);
end

if ~isempty(report)
    allowed = unique(round(report_gen_idx(report_keep)), 'stable');
    active_idx = intersect(active_idx, allowed, 'stable');
    report_rows = find(report_keep & ismember(round(report_gen_idx), active_idx));
    % The report owns the source-backed active capability used by S11.
    pmin_name = find_variable(report, {'pmin_mw','source_pmin_mw','pmin'});
    pmax_name = find_variable(report, {'pmax_mw','source_pmax_mw','pmax'});
    if strlength(pmin_name) > 0 && strlength(pmax_name) > 0
        pmin = numeric_column(report.(pmin_name));
        pmax = numeric_column(report.(pmax_name));
        for r = report_rows(:)'
            gi = round(report_gen_idx(r));
            if gi >= 1 && gi <= size(mpc.gen, 1) && ...
                    isfinite(pmin(r)) && isfinite(pmax(r))
                if pmin(r) > pmax(r) + options.bound_tolerance_mw
                    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:Capability', ...
                        'Source-backed PMIN exceeds PMAX for generator row %d.', gi);
                end
                mpc.gen(gi, PMIN) = pmin(r);
                mpc.gen(gi, PMAX) = pmax(r);
            end
        end
    end
end

active_idx = active_idx(active_idx >= 1 & active_idx <= size(mpc.gen, 1));
active_idx = setdiff(active_idx, external_generator_indices(mpc), 'stable');
active_idx = setdiff(active_idx, round(double(options.exclude_gen_idx(:))), 'stable');
active_idx = active_idx(mpc.gen(active_idx, GEN_STATUS) > 0);
if isempty(active_idx)
    selection = table();
    return;
end

% A positive active-power range or nonzero fixed active injection is required.
has_active_p = mpc.gen(active_idx, PMAX) > mpc.gen(active_idx, PMIN) + ...
    options.bound_tolerance_mw | abs(mpc.gen(active_idx, PG)) > ...
    options.bound_tolerance_mw | abs(mpc.gen(active_idx, PMAX)) > ...
    options.bound_tolerance_mw;
active_idx = active_idx(has_active_p);
selection = table(active_idx, mpc.gen(active_idx, GEN_BUS), ...
    mpc.gen(active_idx, PG), mpc.gen(active_idx, PMIN), ...
    mpc.gen(active_idx, PMAX), repmat(source, numel(active_idx), 1), ...
    'VariableNames', {'gen_index','bus_id','initial_pg_mw','pmin_mw', ...
    'pmax_mw','selection_source'});
end

function keep = exclude_report_class(report, keep, candidates, value)
name = find_variable(report, candidates);
if strlength(name) > 0
    flag = logical_column(report.(name));
    if value, keep = keep & ~flag; else, keep = keep & flag; end
end
end

function idx = external_generator_indices(mpc)
idx = [];
if ~isfield(mpc, 'userdata') || ...
        ~isfield(mpc.userdata, 'ny_only_equivalent') || ...
        ~isfield(mpc.userdata.ny_only_equivalent, ...
        'external_equivalent_generators')
    return;
end
external = mpc.userdata.ny_only_equivalent.external_equivalent_generators;
if istable(external) && ismember('added_gen_index', ...
        external.Properties.VariableNames)
    idx = numeric_column(external.added_gen_index);
elseif isstruct(external) && isfield(external, 'added_gen_index')
    idx = numeric_column({external.added_gen_index}');
end
idx = unique(round(idx(isfinite(idx))));
end

function model = build_active_model(mpc, active_idx, zones)
define_constants;
[mapped, bi] = ismember(mpc.gen(active_idx, GEN_BUS), mpc.bus(:, BUS_I));
if ~all(mapped)
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:GeneratorBus', ...
        'Every active control must be connected to a retained bus.');
end
gen_zone = string(mpc.userdata.nyiso_physical_zone(bi));
if any(gen_zone == "")
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:GeneratorZone', ...
        'Every active control must map to a NYISO zone.');
end
zone_pmin = zeros(numel(zones), 1);
zone_pmax = zeros(numel(zones), 1);
for z = 1:numel(zones)
    local = gen_zone == zones(z);
    zone_pmin(z) = sum(mpc.gen(active_idx(local), PMIN));
    zone_pmax(z) = sum(mpc.gen(active_idx(local), PMAX));
end
model = struct('active_idx', active_idx(:), 'gen_zone', gen_zone(:), ...
    'zone_pmin', zone_pmin, 'zone_pmax', zone_pmax, ...
    'adjustable_zone', zone_pmax - zone_pmin > 1e-6);
end

function gi = choose_reference_generator(mpc, model, options)
define_constants;
if ~isempty(options.reference_gen_idx)
    gi = round(double(options.reference_gen_idx));
    if ~ismember(gi, model.active_idx)
        error('derive_nyiso_zonal_net_injections_ac_iterative_s11:Reference', ...
            'The requested reference generator is not an eligible active control.');
    end
    return;
end
mask = true(numel(model.active_idx), 1);
preferred = model.gen_zone == upper(string(options.reference_zone));
if any(preferred), mask = preferred; end
idx = model.active_idx(mask);
qrange = max(0, mpc.gen(idx, QMAX) - mpc.gen(idx, QMIN));
prange = max(0, mpc.gen(idx, PMAX) - mpc.gen(idx, PMIN));
score = prange + 0.1 * qrange;
score(qrange <= 1e-6) = -Inf;
[best, k] = max(score);
if isempty(k) || ~isfinite(best)
    [best, k] = max(prange);
end
if isempty(k) || ~isfinite(best) || best <= 0
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:Reference', ...
        'No adjustable native active control is suitable as the PF reference.');
end
gi = idx(k);
end

function definitions = resolve_interface_definitions(mpc, options)
definitions = options.interface_definitions;
if isempty(definitions)
    map_file = string(options.interface_map_file);
    if strlength(map_file) > 0 && exist(map_file, 'file') == 2
        map = readtable(map_file, 'TextType', 'string', ...
            'VariableNamingRule', 'preserve');
        definitions = definitions_from_s11_map(mpc, map);
    else
        definitions = ny_lite_interface_definitions(mpc);
    end
elseif ischar(definitions) || isstring(definitions)
    map = readtable(char(definitions), 'TextType', 'string', ...
        'VariableNamingRule', 'preserve');
    if ismember('reduced_branch_index', map.Properties.VariableNames)
        definitions = definitions_from_s11_map(mpc, map);
    else
        definitions = map;
    end
end
if istable(definitions) && ...
        ismember('reduced_branch_index', definitions.Properties.VariableNames)
    definitions = definitions_from_s11_map(mpc, definitions);
end
if istable(definitions), definitions = table2struct(definitions); end
if isempty(definitions) || ~isstruct(definitions) || ...
        ~isfield(definitions, 'interface_name')
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:Interfaces', ...
        'Explicit NY-lite interface definitions are empty or invalid.');
end

function definitions = definitions_from_s11_map(mpc, map)
required = {'interface_name','aggregate_name','zone_boundary', ...
    'positive_direction','reduced_branch_index','reduced_from_bus', ...
    'reduced_to_bus','metered_end','sign','calibration_eligible'};
if ~all(ismember(required, map.Properties.VariableNames))
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:InterfaceMap', ...
        'The explicit S11 interface map is missing required columns.');
end
rows = repmat(struct('interface_name','', 'aggregate_name','', ...
    'zone_boundary','', 'positive_direction','', 'branch_index',NaN, ...
    'branch_from',NaN, 'branch_to',NaN, 'branch_from_name','', ...
    'branch_to_name','', 'metered_bus',NaN, 'metered_end','', ...
    'flow_column','', 'sign',1, 'original_or_added','explicit_s11_map', ...
    'candidate_name','', 'target_source','', ...
    'calibration_eligible',true), height(map), 1);
for k = 1:height(map)
    branch_index = double(map.reduced_branch_index(k));
    if ~isfinite(branch_index) || branch_index < 1 || ...
            branch_index > size(mpc.branch, 1)
        error('derive_nyiso_zonal_net_injections_ac_iterative_s11:InterfaceMap', ...
            'Explicit interface row %d has invalid branch index.', k);
    end
    from_bus = double(map.reduced_from_bus(k));
    to_bus = double(map.reduced_to_bus(k));
    metered_end = lower(string(map.metered_end(k)));
    if metered_end == "from"
        metered_bus = from_bus;
        flow_column = 'PF';
    elseif metered_end == "to"
        metered_bus = to_bus;
        flow_column = 'PT';
    else
        error('derive_nyiso_zonal_net_injections_ac_iterative_s11:InterfaceMap', ...
            'Explicit interface row %d has unknown metered end %s.', ...
            k, metered_end);
    end
    rows(k).interface_name = char(string(map.interface_name(k)));
    rows(k).aggregate_name = char(string(map.aggregate_name(k)));
    rows(k).zone_boundary = char(string(map.zone_boundary(k)));
    rows(k).positive_direction = char(string(map.positive_direction(k)));
    rows(k).branch_index = branch_index;
    rows(k).branch_from = from_bus;
    rows(k).branch_to = to_bus;
    rows(k).branch_from_name = bus_name_for_id(mpc, from_bus);
    rows(k).branch_to_name = bus_name_for_id(mpc, to_bus);
    rows(k).metered_bus = metered_bus;
    rows(k).metered_end = char(metered_end);
    rows(k).flow_column = flow_column;
    rows(k).sign = double(map.sign(k));
    if ismember('circuit_id', map.Properties.VariableNames)
        rows(k).candidate_name = char(string(map.circuit_id(k)));
    end
    if ismember('target_source', map.Properties.VariableNames)
        rows(k).target_source = char(string(map.target_source(k)));
    end
    rows(k).calibration_eligible = logical_column( ...
        map.calibration_eligible(k));
end
definitions = rows;
end

function name = bus_name_for_id(mpc, bus_id)
idx = find(mpc.bus(:, 1) == bus_id, 1);
if isempty(idx)
    name = sprintf('BUS_%g', bus_id);
elseif isfield(mpc, 'bus_name') && numel(mpc.bus_name) >= idx
    name = char(strtrim(string(mpc.bus_name{idx})));
else
    name = sprintf('BUS_%g', bus_id);
end
end
end

function targets = prepare_public_targets(scenario_id, definitions, options)
targets = read_public_interface_targets(scenario_id, ...
    options.interface_target_file);
if options.use_raw_public_targets && ...
        ismember('nyiso_flow_mw', targets.Properties.VariableNames)
    selected = numeric_column(targets.nyiso_flow_mw);
    fallback = numeric_column(targets.target_flow_mw);
    missing = ~isfinite(selected);
    selected(missing) = fallback(missing);
    source = repmat("raw_nyiso_flow_mw", height(targets), 1);
    source(missing) = "scaled_target_flow_mw_fallback";
else
    selected = numeric_column(targets.target_flow_mw);
    source = repmat("scaled_target_flow_mw", height(targets), 1);
end
if any(~isfinite(selected))
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:Targets', ...
        'Every selected public interface target must be finite.');
end
eligible = true(height(targets), 1);
if ismember('calibration_eligible', targets.Properties.VariableNames)
    eligible = logical_column(targets.calibration_eligible);
elseif isfield(definitions, 'calibration_eligible')
    for k = 1:height(targets)
        idx = strcmp(string({definitions.interface_name}), ...
            string(targets.interface_name(k)));
        if any(idx)
            eligible(k) = all(logical_column( ...
                {definitions(idx).calibration_eligible}'));
        end
    end
end
targets.selected_target_flow_mw = selected;
targets.target_source = source;
targets.calibration_eligible = eligible;
end

function [generation, diagnostics] = constrained_dc_interface_seed( ...
        template, model, zones, prior, total_generation, reference_gen, ...
        definitions, targets, calibration_mask, accuracy_scale, options)
% Infer the pre-AC zonal dispatch with the S8 constrained-DC method, using
% the already mapped S11 control groups and the explicit interface operators.

prior = project_generation_total(prior, model.zone_pmin, ...
    model.zone_pmax, total_generation);
adjustable = model.adjustable_zone(:);
balance_idx = find(zones == upper(string(options.reference_zone)) & ...
    adjustable, 1);
if isempty(balance_idx)
    [~, balance_idx] = max((model.zone_pmax-model.zone_pmin) .* adjustable);
end
variable_idx = find(adjustable & (1:numel(zones))' ~= balance_idx);
fixed_idx = setdiff((1:numel(zones))', [variable_idx; balance_idx], 'stable');
fixed_generation = sum(prior(fixed_idx));
remaining_generation = total_generation - fixed_generation;

[base_result, base_case] = run_generation_dc(template, model, zones, prior, ...
    reference_gen);
if ~isfield(base_result, 'success') || ~logical(base_result.success)
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:InitialDCPF', ...
        'The scenario-balanced prior did not converge in DC power flow.');
end
base_flow = interface_vector(base_result, definitions, targets);

response = zeros(height(targets), numel(variable_idx));
steps = zeros(numel(variable_idx), 1);
for k = 1:numel(variable_idx)
    z = variable_idx(k);
    positive_margin = min(model.zone_pmax(z)-prior(z), ...
        prior(balance_idx)-model.zone_pmin(balance_idx));
    negative_margin = min(prior(z)-model.zone_pmin(z), ...
        model.zone_pmax(balance_idx)-prior(balance_idx));
    if positive_margin >= negative_margin
        direction = 1;
        margin = positive_margin;
    else
        direction = -1;
        margin = negative_margin;
    end
    magnitude = min(options.dc_sensitivity_step_mw, 0.8*max(0, margin));
    if magnitude <= 1e-6
        continue;
    end
    h = direction*magnitude;
    trial = prior;
    trial(z) = trial(z) + h;
    trial(balance_idx) = trial(balance_idx) - h;
    [trial_result, ~] = run_generation_dc(template, model, zones, trial, ...
        reference_gen);
    if ~isfield(trial_result, 'success') || ~logical(trial_result.success)
        error('derive_nyiso_zonal_net_injections_ac_iterative_s11:DCSensitivity', ...
            'DC sensitivity run failed for zone %s.', zones(z));
    end
    trial_flow = interface_vector(trial_result, definitions, targets);
    response(:, k) = (trial_flow-base_flow)/h;
    steps(k) = h;
end

x0 = prior(variable_idx);
eligible_response = response(calibration_mask, :);
eligible_target = targets.selected_target_flow_mw(calibration_mask);
eligible_base = base_flow(calibration_mask);
eligible_scale = accuracy_scale(calibration_mask);
W = diag(1 ./ eligible_scale);
C_interface = W * eligible_response;
d_interface = W * (eligible_target-eligible_base + eligible_response*x0);

prior_scale = max(500, model.zone_pmax(variable_idx));
root_lambda = sqrt(options.dc_prior_weight);
C_prior = diag(root_lambda ./ prior_scale);
d_prior = C_prior*x0;
C = [C_interface; C_prior];
d = [d_interface; d_prior];

% The balance-zone value is implied by the total-generation equality.
A = [ones(1, numel(variable_idx)); -ones(1, numel(variable_idx))];
b = [remaining_generation-model.zone_pmin(balance_idx); ...
    model.zone_pmax(balance_idx)-remaining_generation];
lb = model.zone_pmin(variable_idx);
ub = model.zone_pmax(variable_idx);
solver_options = optimoptions('lsqlin', 'Display', 'off', ...
    'Algorithm', 'interior-point');
[x, resnorm, ~, exitflag, output] = lsqlin(C, d, A, b, [], [], ...
    lb, ub, x0, solver_options);
if exitflag <= 0
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:InitialDCDispatch', ...
        'Constrained DC interface inference failed: %s', output.message);
end

generation = prior;
generation(variable_idx) = x;
generation(balance_idx) = remaining_generation-sum(x);
generation = project_generation_total(generation, model.zone_pmin, ...
    model.zone_pmax, total_generation);
predicted_flow = base_flow + response*(x-x0);
predicted_residual = predicted_flow-targets.selected_target_flow_mw;
diagnostics = struct('method', "constrained_dc_interface", ...
    'balance_zone', zones(balance_idx), 'balance_zone_index', balance_idx, ...
    'scenario_balance_prior_mw', prior, 'generation_mw', generation, ...
    'total_generation_mw', total_generation, 'base_result', base_result, ...
    'base_case', base_case, 'base_flow_mw', base_flow, ...
    'predicted_flow_mw', predicted_flow, ...
    'predicted_residual_mw', predicted_residual, ...
    'response_matrix', response, 'sensitivity_steps_mw', steps, ...
    'resnorm', resnorm, 'exitflag', exitflag);
end

function [result, case_mpc] = run_generation_dc(template, model, zones, ...
        generation, reference_gen)
[case_mpc, ~] = apply_zonal_generation(template, model, zones, generation);
case_mpc = set_scenario_reference_bus(case_mpc, reference_gen, ...
    struct('require_external', false));
result = rundcpf(case_mpc, mpoption('verbose', 0, 'out.all', 0, ...
    'model', 'DC'));
end

function [result, allocation, case_mpc] = run_generation(template, model, ...
        zones, generation, reference_gen, pfopt, warm_result)
define_constants;
[case_mpc, allocation] = apply_zonal_generation( ...
    template, model, zones, generation);
if nargin >= 7 && ~isempty(warm_result) && ...
        size(warm_result.bus, 1) == size(case_mpc.bus, 1)
    case_mpc.bus(:, [VM VA]) = warm_result.bus(:, [VM VA]);
    if size(warm_result.gen, 1) == size(case_mpc.gen, 1)
        case_mpc.gen(:, QG) = min(max(warm_result.gen(:, QG), ...
            case_mpc.gen(:, QMIN)), case_mpc.gen(:, QMAX));
        case_mpc.gen(:, VG) = warm_result.gen(:, VG);
    end
end
case_mpc = set_scenario_reference_bus(case_mpc, reference_gen, ...
    struct('require_external', false));
result = runpf(case_mpc, pfopt);
end

function [result, allocation, case_mpc] = try_run_generation(template, ...
        model, zones, generation, reference_gen, pfopt, warm_result)
allocation = table();
case_mpc = template;
try
    [result, allocation, case_mpc] = run_generation(template, model, ...
        zones, generation, reference_gen, pfopt, warm_result);
catch ex
    result = struct('success', false, 'error_identifier', ex.identifier, ...
        'error_message', ex.message);
end
end

function [result, accepted_generation] = accept_loss_balance_step( ...
        template, model, zones, current_generation, proposed_generation, ...
        reference_gen, pfopt, warm_result, options)
result = struct('success', false);
accepted_generation = current_generation;
factors = unique([1, options.line_search_factors(:)', ...
    0.0625, 0.03125], 'stable');
for factor = factors
    candidate = current_generation + ...
        factor*(proposed_generation-current_generation);
    [trial, ~, ~] = try_run_generation(template, model, zones, candidate, ...
        reference_gen, pfopt, warm_result);
    if isfield(trial, 'success') && logical(trial.success)
        result = trial;
        accepted_generation = candidate;
        return;
    end
end
end

function [generation, result, rows] = establish_initial_ac_seed(template, ...
        model, zones, generation, reference_gen, pfopt, scenario_id, options)
[result, ~, ~] = run_generation(template, model, zones, generation, ...
    reference_gen, pfopt, []);
rows = continuation_row(scenario_id, 1, "direct_seed", result, ...
    template, generation, model);
if isfield(result, 'success') && logical(result.success), return; end
if ~options.enable_initial_continuation
    require_success(result, scenario_id, 0, 'initial seeded AC PF');
end

define_constants;
fixed_generation = fixed_generation_total(template, model);
full_load = sum(template.bus(:, PD));
minimum_fraction = (sum(model.zone_pmin)+fixed_generation) / ...
    max(full_load*(1+options.initial_loss_fraction), eps);
start_fraction = min(0.9, max(0.4, minimum_fraction + 0.02));
fractions = linspace(start_fraction, 1, ...
    options.initial_continuation_steps);
warm = [];
started = false;
last_success_fraction = NaN;
for k = 1:numel(fractions)
    fraction = fractions(k);
    stage = template;
    stage.bus(:, PD) = template.bus(:, PD) * fraction;
    stage.bus(:, QD) = template.bus(:, QD) * fraction;
    % Public external schedules and every other nonparticipating P record
    % remain fixed during continuation. Only the mapped native controls are
    % projected to the staged load balance.
    stage_total = sum(stage.bus(:, PD))*(1+options.initial_loss_fraction) - ...
        fixed_generation;
    stage_total = min(max(stage_total, sum(model.zone_pmin)), ...
        sum(model.zone_pmax));
    stage_generation = project_generation_total(generation, ...
        model.zone_pmin, model.zone_pmax, stage_total);
    [stage_result, ~, ~] = run_generation(stage, model, zones, ...
        stage_generation, reference_gen, pfopt, warm);
    rows = append_table(rows, continuation_row(scenario_id, fraction, ...
        "continuation", stage_result, stage, stage_generation, model));
    if ~isfield(stage_result, 'success') || ~logical(stage_result.success)
        if ~started
            % A lightly loaded fixed-schedule case can be less solvable than
            % a later stage (for example because an import schedule cannot be
            % scaled). Search for the first hard-limit-preserving AC seed.
            continue;
        end
        break;
    end
    started = true;
    last_success_fraction = fraction;
    warm = stage_result;
    result = stage_result;
    generation = stage_generation;
end
if ~started || last_success_fraction < 1-1e-12
    if logical(options.enable_initial_acopf_seed)
        [opf_generation, opf_pf, opf_case, opf_diagnostics] = ...
            hard_acopf_initial_seed(template, model, zones, generation, ...
            reference_gen, pfopt, options);
        rows = append_table(rows, continuation_row(scenario_id, 1, ...
            "hard_acopf_seed", opf_pf, opf_case, opf_generation, model));
        if opf_diagnostics.success && isfield(opf_pf, 'success') && ...
                logical(opf_pf.success)
            generation = opf_generation;
            result = opf_pf;
            return;
        end
    end
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:InitialContinuation', ...
        ['Initial AC continuation could not establish the full-load seed for %s. ' ...
         'Hard generator limits and fixed external schedules were not relaxed; ' ...
         'the hard ACOPF seed also failed.'], ...
        scenario_id);
end
end

function [generation, pf_result, seed_case, diagnostics] = ...
        hard_acopf_initial_seed(template, model, zones, generation, ...
        reference_gen, pfopt, options)
% Find a hard-feasible AC seed without any P/Q/V/branch restoration slack.
% The objective is a literal squared-MW deviation from the constrained-DC
% inferred dispatch. Only explicitly mapped physical-circuit ratings are
% enforced; aggregate/equivalent RATE_A values remain diagnostics.
define_constants;
[opf_case, ~] = apply_zonal_generation(template, model, zones, generation);
opf_case = set_scenario_reference_bus(opf_case, reference_gen, ...
    struct('require_external', false));
trusted = false(size(opf_case.branch, 1), 1);
if isfield(opf_case, 'userdata') && isfield(opf_case.userdata, 's11_dlr') && ...
        isfield(opf_case.userdata.s11_dlr, 'branch_classification')
    trusted = string(opf_case.userdata.s11_dlr.branch_classification(:)) == ...
        "physical_circuit";
end
opf_case.branch(~trusted, [RATE_A RATE_B RATE_C]) = 0;

target_pg = opf_case.gen(:, PG);
width = 7;
opf_case.gencost = zeros(size(opf_case.gen, 1), width);
objective_scale = 1e-6;
for g = 1:size(opf_case.gen, 1)
    opf_case.gencost(g, :) = [2 0 0 3 objective_scale, ...
        -2*objective_scale*target_pg(g), ...
        objective_scale*target_pg(g)^2];
end
diagnostics = struct('attempted', true, 'success', false, ...
    'message', "Hard ACOPF did not run", 'result', struct());
try
    opfopt = mpoption('verbose', 0, 'out.all', 0, 'opf.ac.solver', ...
        char(options.initial_acopf_solver), 'opf.flow_lim', 'S', ...
        'opf.violation', 1e-6, 'opf.use_vg', 0, ...
        'opf.ignore_angle_lim', 0, 'opf.start', 2);
    opf_result = runopf(opf_case, opfopt);
catch ex
    diagnostics.message = "Hard ACOPF exception: " + string(ex.message);
    pf_result = struct('success', false);
    seed_case = opf_case;
    return;
end
diagnostics.result = opf_result;
diagnostics.success = isfield(opf_result, 'success') && ...
    logical(opf_result.success);
if ~diagnostics.success
    diagnostics.message = "Hard ACOPF returned success=0";
    pf_result = struct('success', false);
    seed_case = opf_case;
    return;
end

generation = zonal_actual_generation(opf_result, model, zones);
[seed_case, ~] = apply_zonal_generation(template, model, zones, generation);
seed_case = set_scenario_reference_bus(seed_case, reference_gen, ...
    struct('require_external', false));
seed_case.bus(:, [VM VA]) = opf_result.bus(:, [VM VA]);
seed_case.gen(:, QG) = min(max(opf_result.gen(:, QG), ...
    seed_case.gen(:, QMIN)), seed_case.gen(:, QMAX));
seed_case.gen(:, VG) = opf_result.gen(:, VG);
pf_result = runpf(seed_case, pfopt);
diagnostics.success = isfield(pf_result, 'success') && logical(pf_result.success);
diagnostics.message = "Hard ACOPF feasible without restoration slacks";
end

function row = continuation_row(scenario_id, fraction, stage_name, result, ...
        case_mpc, generation, model)
success = isfield(result, 'success') && logical(result.success);
reference_pickup = NaN;
min_voltage = NaN;
max_voltage = NaN;
if success
    metrics = physical_metrics(result, model, generation);
    reference_pickup = metrics.reference_pickup_mw;
    min_voltage = metrics.min_voltage_pu;
    max_voltage = metrics.max_voltage_pu;
end
row = table(scenario_id, fraction, string(stage_name), success, ...
    sum(case_mpc.bus(:, 3)), sum(generation), reference_pickup, ...
    min_voltage, max_voltage, 'VariableNames', {'scenario_id', ...
    'load_fraction','stage','pf_success','stage_load_mw', ...
    'scheduled_active_generation_mw','reference_pickup_mw', ...
    'min_voltage_pu','max_voltage_pu'});
end

function [mpc, report] = apply_zonal_generation(mpc, model, zones, generation)
define_constants;
report = table();
for z = 1:numel(zones)
    local = find(model.gen_zone == zones(z));
    if isempty(local)
        if abs(generation(z)) > 1e-7
            error('derive_nyiso_zonal_net_injections_ac_iterative_s11:ZoneControls', ...
                'Zone %s has no active controls for target %.3f MW.', ...
                zones(z), generation(z));
        end
        continue;
    end
    gi = model.active_idx(local);
    lower = mpc.gen(gi, PMIN);
    upper = mpc.gen(gi, PMAX);
    seed = mpc.gen(gi, PG);
    applied = project_vector_total(seed, lower, upper, generation(z));
    mpc.gen(gi, PG) = applied;
    row = table(repmat(zones(z), numel(gi), 1), gi, ...
        mpc.gen(gi, GEN_BUS), repmat(generation(z), numel(gi), 1), ...
        seed, applied, lower, upper, ...
        'VariableNames', {'zone','gen_index','bus_id', ...
        'zone_target_generation_mw','seed_pg_mw','applied_pg_mw', ...
        'pmin_mw','pmax_mw'});
    report = append_table(report, row);
end
end

function require_success(result, scenario_id, iteration, label)
if ~isfield(result, 'success') || ~logical(result.success)
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:PowerFlow', ...
        '%s failed for %s at iteration %d.', label, scenario_id, iteration);
end
end

function generation = zonal_generation_from_case(mpc, model, zones)
define_constants;
generation = zeros(numel(zones), 1);
for z = 1:numel(zones)
    local = model.gen_zone == zones(z);
    generation(z) = sum(mpc.gen(model.active_idx(local), PG));
end
end

function [prior, source] = zonal_source_pg_prior(mpc, model, zones, fallback)
prior = fallback;
source = "current_scenario_pg";
if ~isfield(mpc, 'userdata') || ~isfield(mpc.userdata, 's11') || ...
        ~isfield(mpc.userdata.s11, 'controls') || ...
        ~isfield(mpc.userdata.s11.controls, 'generator_report')
    return;
end
report = mpc.userdata.s11.controls.generator_report;
if isstruct(report), report = struct2table(report); end
if ~istable(report) || isempty(report), return; end
idx_name = find_variable(report, {'reduced_gen_index','gen_index', ...
    'generator_index','model_gen_index','s11_gen_index'});
pg_name = find_variable(report, {'source_pg_mw','source_active_pg_mw', ...
    'perform_source_pg_mw'});
if strlength(idx_name) == 0 || strlength(pg_name) == 0, return; end
idx = round(numeric_column(report.(idx_name)));
source_pg = numeric_column(report.(pg_name));
candidate = zeros(numel(zones), 1);
found = false(numel(model.active_idx), 1);
for k = 1:numel(model.active_idx)
    row = find(idx == model.active_idx(k) & isfinite(source_pg), 1);
    if isempty(row), continue; end
    z = find(zones == model.gen_zone(k), 1);
    candidate(z) = candidate(z) + source_pg(row);
    found(k) = true;
end
if all(found) && all(isfinite(candidate)) && sum(candidate) > 0
    prior = candidate;
    source = "generator_report_source_pg_mw";
end
end

function load_mw = zonal_load(mpc, zones)
define_constants;
load_mw = zeros(numel(zones), 1);
physical_zone = string(mpc.userdata.nyiso_physical_zone);
for z = 1:numel(zones)
    load_mw(z) = sum(mpc.bus(physical_zone == zones(z), PD));
end
end

function generation = zonal_actual_generation(results, model, zones)
define_constants;
generation = zeros(numel(zones), 1);
for z = 1:numel(zones)
    local = model.gen_zone == zones(z);
    generation(z) = sum(results.gen(model.active_idx(local), PG));
end
end

function generation = zonal_fixed_generation(mpc, model, zones)
define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
[mapped, bi] = ismember(mpc.gen(:, GEN_BUS), mpc.bus(:, BUS_I));
gen_zone = strings(size(mpc.gen, 1), 1);
gen_zone(mapped) = string(mpc.userdata.nyiso_physical_zone(bi(mapped)));
fixed = mpc.gen(:, GEN_STATUS) > 0;
fixed(model.active_idx) = false;
generation = zeros(numel(zones), 1);
for z = 1:numel(zones)
    generation(z) = sum(mpc.gen(fixed & gen_zone == zones(z), PG));
end
end

function generation = fixed_generation_total(mpc, model)
define_constants;
online = mpc.gen(:, GEN_STATUS) > 0;
online(model.active_idx) = false;
generation = sum(mpc.gen(online, PG));
end

function alpha = loss_participation(generation, pmin, pmax, delta, adjustable)
if delta >= 0
    reserve = max(0, pmax - generation);
else
    reserve = max(0, generation - pmin);
end
reserve(~adjustable) = 0;
if sum(reserve) <= 1e-9
    reserve = max(0, pmax - pmin);
    reserve(~adjustable) = 0;
end
if sum(reserve) <= 1e-9
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:Headroom', ...
        'No source-backed active headroom is available for loss closure.');
end
alpha = reserve / sum(reserve);
end

function alpha = sensitivity_participation(generation, pmin, pmax, adjustable)
reserve = min(max(0, pmax - generation), max(0, generation - pmin));
reserve(~adjustable) = 0;
if sum(reserve) <= 1e-9
    reserve = max(0, pmax - generation);
    reserve(~adjustable) = 0;
end
if sum(reserve) <= 1e-9
    reserve = max(0, generation - pmin);
    reserve(~adjustable) = 0;
end
if sum(reserve) <= 1e-9
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:SensitivityHeadroom', ...
        'No distributed participation vector can be formed.');
end
alpha = reserve / sum(reserve);
end

function projected = project_generation_total(seed, lower, upper, total)
projected = project_vector_total(seed, lower, upper, total);
end

function projected = project_vector_total(seed, lower, upper, total)
seed = seed(:); lower = lower(:); upper = upper(:);
if total < sum(lower) - 1e-6 || total > sum(upper) + 1e-6
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:GenerationBounds', ...
        'Required generation %.3f MW is outside [%.3f, %.3f] MW.', ...
        total, sum(lower), sum(upper));
end
projected = min(max(seed, lower), upper);
for iteration = 1:500
    delta = total - sum(projected);
    if abs(delta) <= 1e-9, break; end
    if delta > 0
        room = upper - projected;
    else
        room = projected - lower;
    end
    active = room > 1e-10;
    if ~any(active), break; end
    weight = room;
    weight(~active) = 0;
    weight = weight / sum(weight);
    step = delta * weight;
    if delta > 0
        step = min(step, room);
    else
        step = max(step, -room);
    end
    projected = projected + step;
end
if abs(total - sum(projected)) > 1e-6
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:Projection', ...
        'Could not project generation onto source-backed limits.');
end
end

function [response, steps, rows] = ac_response_matrix(template, model, zones, ...
        generation, reference_gen, pfopt, base_result, base_flow, definitions, ...
        targets, alpha, options, scenario_id, iteration)
nz = numel(zones);
nm = height(targets);
response = nan(nm, nz);
steps = zeros(nz, 1);
rows = table();
for z = find(model.adjustable_zone(:))'
    direction = -alpha;
    direction(z) = direction(z) + 1;
    if norm(direction, inf) <= 1e-12, continue; end
    positive_margin = feasible_margin(generation, direction, ...
        model.zone_pmin, model.zone_pmax);
    negative_margin = feasible_margin(generation, -direction, ...
        model.zone_pmin, model.zone_pmax);
    if positive_margin >= negative_margin
        direction_signs = [1 -1];
    else
        direction_signs = [-1 1];
    end
    accepted = false;
    for direction_sign = direction_signs
        if direction_sign > 0
            signed_margin = positive_margin;
        else
            signed_margin = negative_margin;
        end
        magnitude = min(options.ac_sensitivity_step_mw, 0.8*signed_margin);
        if ~isfinite(magnitude), magnitude = options.ac_sensitivity_step_mw; end
        while magnitude >= options.min_sensitivity_step_mw
            h = direction_sign*magnitude;
            trial_generation = generation + h*direction;
            [trial_result, ~, ~] = try_run_generation(template, model, zones, ...
                trial_generation, reference_gen, pfopt, base_result);
            if isfield(trial_result, 'success') && logical(trial_result.success)
                trial_flow = interface_vector(trial_result, definitions, targets);
                response(:, z) = (trial_flow-base_flow)/h;
                steps(z) = h;
                accepted = true;
                break;
            end
            magnitude = magnitude/2;
        end
        if accepted, break; end
    end
    if ~accepted, continue; end
    for m = 1:nm
        row = table(scenario_id, iteration, targets.interface_name(m), ...
            targets.calibration_eligible(m), zones(z), response(m, z), h, ...
            direction(z), alpha(z), 'VariableNames', {'scenario_id', ...
            'iteration','interface_name','calibration_eligible', ...
            'perturbed_zone','sensitivity_mw_per_mw', ...
            'finite_difference_step_mw','direction_zone_component', ...
            'distributed_participation_factor'});
        rows = append_table(rows, row);
    end
end
response(~isfinite(response)) = 0;
end

function margin = feasible_margin(generation, direction, lower, upper)
limits = [];
positive = direction > 1e-12;
negative = direction < -1e-12;
if any(positive)
    limits = [limits; (upper(positive) - generation(positive)) ./ ...
        direction(positive)];
end
if any(negative)
    limits = [limits; (generation(negative) - lower(negative)) ./ ...
        (-direction(negative))];
end
if isempty(limits), margin = Inf; else, margin = max(0, min(limits)); end
end

function [delta, exitflag] = solve_ac_redispatch(response, residual, ...
        generation, prior, pmin, pmax, accuracy, adjustable, options)
nz = numel(generation);
normalized = residual ./ accuracy;
irls = ones(size(normalized));
large = abs(normalized) > options.huber_delta;
irls(large) = options.huber_delta ./ abs(normalized(large));
W = diag(sqrt(irls) ./ accuracy);
C_flow = W * response;
d_flow = W * (-residual);

prior_scale = max(500, max(abs([pmin pmax]), [], 2));
C_prior = diag(sqrt(options.prior_weight) ./ prior_scale);
d_prior = C_prior * (prior - generation);
C_update = diag(repmat(sqrt(options.update_weight) / 500, nz, 1));
C = [C_flow; C_prior; C_update];
d = [d_flow; d_prior; zeros(nz, 1)];

trust = options.max_zonal_redispatch_step_mw;
lower = max(pmin - generation, -trust);
upper = min(pmax - generation, trust);
lower(~adjustable) = 0;
upper(~adjustable) = 0;
solver_options = optimoptions('lsqlin', 'Display', 'off', ...
    'Algorithm', 'interior-point');
[delta, ~, ~, exitflag, output] = lsqlin(C, d, [], [], ...
    ones(1, nz), 0, lower, upper, zeros(nz, 1), solver_options);
if exitflag <= 0
    error('derive_nyiso_zonal_net_injections_ac_iterative_s11:Redispatch', ...
        'AC redispatch solve failed: %s', output.message);
end
end

function [accepted, next_generation, factor, accepted_norm, accepted_result] = ...
        accept_redispatch_step(template, model, zones, generation, delta, ...
        reference_gen, pfopt, base_result, definitions, targets, ...
        calibration_mask, accuracy_scale, base_objective, options)
accepted = false;
next_generation = generation;
factor = NaN;
accepted_norm = 0;
accepted_result = base_result;
for f = options.line_search_factors(:)'
    candidate = generation + f * delta;
    candidate = project_generation_total(candidate, model.zone_pmin, ...
        model.zone_pmax, sum(generation));
    [trial, ~, ~] = try_run_generation(template, model, zones, candidate, ...
        reference_gen, pfopt, base_result);
    if ~isfield(trial, 'success') || ~logical(trial.success), continue; end
    trial_flow = interface_vector(trial, definitions, targets);
    trial_residual = trial_flow - targets.selected_target_flow_mw;
    objective = huber_objective(trial_residual(calibration_mask), ...
        accuracy_scale(calibration_mask), options.huber_delta);
    required_improvement = options.minimum_objective_improvement * ...
        max(1, abs(base_objective));
    if objective <= base_objective - required_improvement
        accepted = true;
        next_generation = candidate;
        factor = f;
        accepted_norm = norm(candidate - generation, inf);
        accepted_result = trial;
        return;
    end
end
end

function [generation, result, allocation, case_mpc, history, ...
        sensitivity_history, participation_history, diagnostics] = ...
        hard_q_interface_refinement(template, model, zones, generation, prior, ...
        reference_gen, definitions, targets, calibration_mask, accuracy_scale, ...
        scenario_id, options)
% Refine interface closure on the actual Q-limit-enforced AC manifold. This
% second phase prevents standard-PF Q violations from defining an accepted
% diagnostic result while retaining the same 50-100 MW zonal trust region.
qpfopt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1);
history = table();
sensitivity_history = table();
participation_history = table();
allocation = table();
case_mpc = template;
diagnostics = struct('attempted', true, 'success', false, ...
    'converged', false, 'stop_reason', "initial_q_limit_pf_failed", ...
    'accepted_step_count', 0);
try
    case_mpc = template;
    result = runpf(case_mpc, qpfopt);
catch ex
    result = struct('success', false, 'error_identifier', ex.identifier, ...
        'error_message', ex.message);
end
if ~isfield(result, 'success') || ~logical(result.success)
    standard_pfopt = mpoption('verbose', 0, 'out.all', 0, ...
        'pf.enforce_q_lims', 0);
    [opf_generation, ~, opf_case, opf_diagnostics] = ...
        hard_acopf_initial_seed(template, model, zones, generation, ...
        reference_gen, standard_pfopt, options);
    if ~opf_diagnostics.success, return; end
    try
        opf_qpf = runpf(opf_case, qpfopt);
    catch
        opf_qpf = struct('success', false);
    end
    if ~isfield(opf_qpf, 'success') || ~logical(opf_qpf.success), return; end
    generation = opf_generation;
    case_mpc = opf_case;
    result = opf_qpf;
end
diagnostics.success = true;
last_exitflag = NaN;
stop_reason = "hard_q_maximum_iterations";

for iteration = 1:options.hard_q_refinement_iterations
    metrics = physical_metrics(result, model, generation);
    required_active = metrics.required_active_generation_mw;
    loss_adjustment = required_active-sum(generation);
    if abs(loss_adjustment) >= options.reference_pickup_tolerance_mw
        alpha_loss = loss_participation(generation, model.zone_pmin, ...
            model.zone_pmax, loss_adjustment, model.adjustable_zone);
        proposed = project_generation_total(generation + ...
            alpha_loss*loss_adjustment, model.zone_pmin, model.zone_pmax, ...
            required_active);
        [loss_result, loss_generation] = accept_loss_balance_step( ...
            template, model, zones, generation, proposed, reference_gen, ...
            qpfopt, result, options);
        if isfield(loss_result, 'success') && logical(loss_result.success)
            generation = loss_generation;
            result = loss_result;
            metrics = physical_metrics(result, model, generation);
        end
    end

    base_flow = interface_vector(result, definitions, targets);
    residual = base_flow-targets.selected_target_flow_mw;
    objective = huber_objective(residual(calibration_mask), ...
        accuracy_scale(calibration_mask), options.huber_delta);
    if interface_tolerance_pass(residual(calibration_mask), options) && ...
            abs(metrics.reference_pickup_mw) < ...
            options.reference_pickup_tolerance_mw
        stop_reason = "hard_q_interface_and_reference_tolerance";
        diagnostics.converged = true;
        history = append_table(history, history_row(scenario_id, iteration, ...
            "hard_q_converged", metrics, objective, ...
            residual(calibration_mask), required_active, loss_adjustment, ...
            0, 0, NaN, true, last_exitflag));
        break;
    end

    alpha_sensitivity = sensitivity_participation(generation, ...
        model.zone_pmin, model.zone_pmax, model.adjustable_zone);
    alpha_loss = loss_participation(generation, model.zone_pmin, ...
        model.zone_pmax, 1, model.adjustable_zone);
    [response, finite_steps, sensitivity_rows] = ac_response_matrix( ...
        template, model, zones, generation, reference_gen, qpfopt, result, ...
        base_flow, definitions, targets, alpha_sensitivity, options, ...
        scenario_id, iteration);
    sensitivity_history = append_table(sensitivity_history, sensitivity_rows);
    participation_history = append_table(participation_history, ...
        participation_table(scenario_id, iteration, zones, generation, ...
        model.zone_pmin, model.zone_pmax, alpha_loss, alpha_sensitivity, ...
        finite_steps));
    [delta_generation, exitflag] = solve_ac_redispatch( ...
        response(calibration_mask, :), residual(calibration_mask), ...
        generation, prior, model.zone_pmin, model.zone_pmax, ...
        accuracy_scale(calibration_mask), model.adjustable_zone, options);
    last_exitflag = exitflag;
    [accepted, next_generation, factor, accepted_norm] = ...
        accept_redispatch_step(template, model, zones, generation, ...
        delta_generation, reference_gen, qpfopt, result, definitions, ...
        targets, calibration_mask, accuracy_scale, objective, options);
    history = append_table(history, history_row(scenario_id, iteration, ...
        "hard_q_iterate", metrics, objective, residual(calibration_mask), ...
        required_active, loss_adjustment, norm(delta_generation, inf), ...
        accepted_norm, factor, accepted, exitflag));
    if ~accepted
        stop_reason = "hard_q_no_improving_redispatch_step";
        break;
    end
    diagnostics.accepted_step_count = diagnostics.accepted_step_count+1;
    generation = next_generation;
    [next_result, next_allocation, next_case] = try_run_generation( ...
        template, model, zones, generation, reference_gen, qpfopt, result);
    if ~isfield(next_result, 'success') || ~logical(next_result.success)
        stop_reason = "hard_q_accepted_step_recheck_failed";
        break;
    end
    result = next_result;
    allocation = next_allocation;
    case_mpc = next_case;
end

[final_result, final_allocation, final_case] = try_run_generation( ...
    template, model, zones, generation, reference_gen, qpfopt, result);
if isfield(final_result, 'success') && logical(final_result.success)
    result = final_result;
    allocation = final_allocation;
    case_mpc = final_case;
    final_metrics = physical_metrics(result, model, generation);
    final_flow = interface_vector(result, definitions, targets);
    final_residual = final_flow-targets.selected_target_flow_mw;
    diagnostics.converged = interface_tolerance_pass( ...
        final_residual(calibration_mask), options) && ...
        abs(final_metrics.reference_pickup_mw) < ...
        options.reference_pickup_tolerance_mw;
end
if diagnostics.converged && stop_reason == "hard_q_maximum_iterations"
    stop_reason = "hard_q_final_tolerance";
end
diagnostics.stop_reason = stop_reason;
end

function vector = interface_vector(results, definitions, targets)
flows = ny_lite_interface_flows(results, definitions);
vector = nan(height(targets), 1);
for k = 1:height(targets)
    idx = find(strcmp({flows.interface_name}, ...
        char(targets.interface_name(k))), 1);
    if isempty(idx)
        if targets.calibration_eligible(k)
            error('derive_nyiso_zonal_net_injections_ac_iterative_s11:Interface', ...
                'Calibration interface %s is not defined.', ...
                targets.interface_name(k));
        end
    else
        vector(k) = flows(idx).flow_mw;
    end
end
end

function scales = interface_accuracy_scales(names, options)
scales = repmat(options.default_accuracy_mw, numel(names), 1);
if exist(options.accuracy_scale_file, 'file') ~= 2, return; end
tbl = readtable(options.accuracy_scale_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
if ~all(ismember({'interface_name','accuracy_scale_mw'}, ...
        tbl.Properties.VariableNames))
    return;
end
for k = 1:numel(names)
    idx = find(string(tbl.interface_name) == string(names(k)), 1);
    if ~isempty(idx) && isfinite(tbl.accuracy_scale_mw(idx)) && ...
            tbl.accuracy_scale_mw(idx) > 0
        scales(k) = tbl.accuracy_scale_mw(idx);
    end
end
end

function value = huber_objective(residual, scale, delta)
u = abs(residual ./ scale);
term = 0.5 * u.^2;
large = u > delta;
term(large) = delta * (u(large) - 0.5 * delta);
value = sum(term);
end

function passed = interface_tolerance_pass(residual, options)
residual = residual(isfinite(residual));
passed = ~isempty(residual) && ...
    max(abs(residual)) <= options.flow_tolerance_mw && ...
    mean(abs(residual)) <= options.interface_mae_tolerance_mw && ...
    abs(mean(residual)) <= options.interface_bias_tolerance_mw;
end

function metrics = physical_metrics(results, model, scheduled_generation)
define_constants;
online = results.gen(:, GEN_STATUS) > 0;
active_online = false(size(online));
active_online(model.active_idx) = online(model.active_idx);
fixed_online = online & ~active_online;
total_generation = sum(results.gen(online, PG));
total_load = sum(results.bus(:, PD));
losses = total_generation - total_load;
actual_active = sum(results.gen(active_online, PG));
fixed_generation = sum(results.gen(fixed_online, PG));
required_active = total_load + losses - fixed_generation;

sf = hypot(results.branch(:, PF), results.branch(:, QF));
st = hypot(results.branch(:, PT), results.branch(:, QT));
smax = max(sf, st);
rated = results.branch(:, RATE_A) > 0 & results.branch(:, BR_STATUS) > 0;
over = max(0, smax - results.branch(:, RATE_A));
vviol = results.bus(:, VM) < results.bus(:, VMIN) - 1e-6 | ...
    results.bus(:, VM) > results.bus(:, VMAX) + 1e-6;
pviol = max(max(0, results.gen(:, PMIN) - results.gen(:, PG)), ...
    max(0, results.gen(:, PG) - results.gen(:, PMAX)));
qviol = max(max(0, results.gen(:, QMIN) - results.gen(:, QG)), ...
    max(0, results.gen(:, QG) - results.gen(:, QMAX)));
metrics = struct( ...
    'total_load_mw', total_load, ...
    'total_generation_mw', total_generation, ...
    'losses_mw', losses, ...
    'fixed_nonparticipating_generation_mw', fixed_generation, ...
    'required_active_generation_mw', required_active, ...
    'scheduled_active_generation_mw', sum(scheduled_generation), ...
    'actual_active_generation_mw', actual_active, ...
    'reference_pickup_mw', actual_active - sum(scheduled_generation), ...
    'min_voltage_pu', min(results.bus(:, VM)), ...
    'max_voltage_pu', max(results.bus(:, VM)), ...
    'voltage_violation_count', sum(vviol), ...
    'branch_overload_count', sum(rated & over > 1e-6), ...
    'max_branch_overload_mva', max([0; over(rated)]), ...
    'generator_p_violation_count', sum(pviol > 1e-6), ...
    'max_generator_p_violation_mw', max([0; pviol]), ...
    'generator_q_violation_count', sum(qviol > 1e-6), ...
    'max_generator_q_violation_mvar', max([0; qviol]));
end

function row = history_row(scenario_id, iteration, row_type, metrics, ...
        objective, residual, required_active, loss_adjustment, proposed_step, ...
        accepted_step, acceptance_factor, accepted, exitflag)
row = table(scenario_id, iteration, row_type, true, objective, ...
    max(abs(residual)), mean(abs(residual)), mean(residual), ...
    metrics.total_load_mw, metrics.total_generation_mw, metrics.losses_mw, ...
    required_active, metrics.scheduled_active_generation_mw, ...
    metrics.actual_active_generation_mw, metrics.reference_pickup_mw, ...
    loss_adjustment, proposed_step, accepted_step, acceptance_factor, ...
    accepted, exitflag, metrics.min_voltage_pu, metrics.max_voltage_pu, ...
    metrics.voltage_violation_count, metrics.branch_overload_count, ...
    metrics.max_branch_overload_mva, metrics.generator_p_violation_count, ...
    metrics.max_generator_p_violation_mw, ...
    metrics.generator_q_violation_count, ...
    metrics.max_generator_q_violation_mvar, ...
    'VariableNames', {'scenario_id','iteration','row_type','pf_success', ...
    'calibration_huber_objective','max_calibrated_residual_mw', ...
    'mean_abs_calibrated_residual_mw','mean_signed_calibrated_residual_mw', ...
    'total_load_mw','total_generation_mw','losses_mw', ...
    'required_active_generation_mw','scheduled_active_generation_mw', ...
    'actual_active_generation_mw','reference_pickup_mw', ...
    'loss_total_adjustment_mw','proposed_step_inf_norm_mw', ...
    'accepted_step_inf_norm_mw','acceptance_factor','step_accepted', ...
    'redispatch_solver_exitflag','min_voltage_pu','max_voltage_pu', ...
    'voltage_violation_count','branch_overload_count', ...
    'max_branch_overload_mva','generator_p_violation_count', ...
    'max_generator_p_violation_mw','generator_q_violation_count', ...
    'max_generator_q_violation_mvar'});
end

function rows = participation_table(scenario_id, iteration, zones, ...
        generation, pmin, pmax, alpha_loss, alpha_sensitivity, steps)
rows = table(repmat(scenario_id, numel(zones), 1), ...
    repmat(iteration, numel(zones), 1), zones, generation, pmin, pmax, ...
    pmax - generation, generation - pmin, alpha_loss, alpha_sensitivity, ...
    steps, 'VariableNames', {'scenario_id','iteration','zone', ...
    'scheduled_generation_mw','pmin_mw','pmax_mw','upward_headroom_mw', ...
    'downward_headroom_mw','loss_participation_factor', ...
    'sensitivity_participation_factor','finite_difference_step_mw'});
end

function name = find_variable(tbl, candidates)
name = "";
names = string(tbl.Properties.VariableNames);
for k = 1:numel(candidates)
    idx = find(strcmpi(names, candidates{k}), 1);
    if ~isempty(idx), name = names(idx); return; end
end
end

function value = numeric_column(value)
if isnumeric(value) || islogical(value)
    value = double(value(:));
else
    value = str2double(string(value(:)));
end
end

function value = logical_column(value)
if islogical(value)
    value = value(:);
elseif isnumeric(value)
    value = isfinite(value(:)) & value(:) ~= 0;
else
    token = lower(strtrim(string(value(:))));
    value = ismember(token, ["1","true","yes","y","on","online", ...
        "enabled","eligible"]);
end
end

function out = append_table(out, row)
if isempty(row), return; end
if isempty(out), out = row; else, out = [out; row]; end
end
