function outputs = run_s9a_minimum_q_support_diagnostic(options)
%RUN_S9A_MINIMUM_Q_SUPPORT_DIAGNOSTIC Locate temporary reactive support.
%   Adds split positive/negative Q-only diagnostic generators at defensible
%   retained buses. Reactive linear costs minimize absolute temporary MVAr,
%   while quadratic P costs penalize movement from the S8 shoulder dispatch.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
options = defaults(options, helper_dir);
define_constants;

scenario_id = string(options.scenario_id);
base = loadcase(options.structural_case);
[gsk, ~] = build_perform_npcc_generation_shift_keys(base);
[core, ~] = build_ny_only_equivalent_case(base);
[core, ~] = align_npcc_generation_capacity_to_perform_gsk(core, gsk);
[core, ~] = apply_nyiso_zonal_loads(core, scenario_id, 1.0, ...
    struct('preserve_total_ny_load', true));
zonal = readtable(options.zonal_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
zonal = zonal(string(zonal.scenario_id) == scenario_id, :);
zones = string(('A':'K')');
generation = vector_by_zone(zonal, zones, 'target_generation_mw');
[core, ~] = apply_perform_generation_allocation(core, ...
    table(zones, generation, ...
    'VariableNames', {'zone','target_generation_mw'}), gsk);
[base_case, ext] = apply_nyiso_external_interface_injections(core, ...
    scenario_id, struct('target_file', options.external_target_file));
base_case = set_zone_reference(base_case, ext.added_gen_index, "J");
q_targets = build_perform_zonal_q_capability_targets(core);
writetable(q_targets, options.q_target_file);
voltage_audit = voltage_setpoint_audit(base_case, ext.added_gen_index);
writetable(voltage_audit, options.voltage_setpoint_file);

case_specs = { ...
    "CURRENT_Q_BASE_FREE_VM", false, false, 0, "current", 0, options.opf_solver; ...
    "PERFORM_Q_BASE_FREE_VM", false, false, 0, "perform_scaled", 0, options.opf_solver; ...
    "PERFORM_Q_TEMP_SUPPORT_FREE_VM", true, false, 0, "perform_scaled", 0, options.opf_solver; ...
    "PERFORM_Q_TEMP_SUPPORT_VG0p25", true, false, 0, "perform_scaled", 0.25, "IPOPT"; ...
    "PERFORM_Q_TEMP_SUPPORT_VG0p50", true, false, 0, "perform_scaled", 0.50, "IPOPT"; ...
    "PERFORM_Q_TEMP_SUPPORT_VG0p75", true, false, 0, "perform_scaled", 0.75, "IPOPT"; ...
    "PERFORM_Q_TEMP_SUPPORT_VG0p80", true, false, 0, "perform_scaled", 0.80, "IPOPT"; ...
    "PERFORM_Q_TEMP_SUPPORT_VG0p85", true, false, 0, "perform_scaled", 0.85, "IPOPT"; ...
    "PERFORM_Q_TEMP_SUPPORT_VG0p90", true, false, 0, "perform_scaled", 0.90, "IPOPT"; ...
    "PERFORM_Q_BASE_FIXED_VG_IPOPT", false, false, 0, "perform_scaled", 1, "IPOPT"; ...
    "PERFORM_Q_TEMP_SUPPORT_FIXED_VG_IPOPT", true, false, 0, "perform_scaled", 1, "IPOPT"; ...
    "PERFORM_Q_BASE_FIXED_VG_MIPS", false, false, 0, "perform_scaled", 1, "MIPS"; ...
    "PERFORM_Q_TEMP_SUPPORT_FIXED_VG_MIPS", true, false, 0, "perform_scaled", 1, "MIPS"; ...
    "PERFORM_Q_TEMP_SUPPORT_FIXED_VG_NO_RATINGS", true, true, 0, "perform_scaled", 1, "MIPS"; ...
    "PERFORM_Q_TEMP_SUPPORT_VPENALTY", true, false, options.voltage_penalty_rho, "perform_scaled", 0, options.opf_solver; ...
    "PERFORM_Q_TEMP_SUPPORT_NO_RATINGS", true, true, 0, "perform_scaled", 0, options.opf_solver};
summary_rows = table();
support_rows = table();
redispatch_rows = table();
interface_rows = table();
binding_rows = table();
q_dispatch_rows = table();
external_q_rows = table();

for c = 1:size(case_specs, 1)
    case_id = string(case_specs{c, 1});
    add_support = logical(case_specs{c, 2});
    remove_ratings = logical(case_specs{c, 3});
    voltage_penalty = double(case_specs{c, 4});
    q_limit_mode = string(case_specs{c, 5});
    use_vg = double(case_specs{c, 6});
    solver = string(case_specs{c, 7});
    mpc = base_case;
    original_ng = size(mpc.gen, 1);
    if q_limit_mode == "perform_scaled"
        mpc = apply_zonal_q_limits(mpc, q_targets, ext.added_gen_index);
    end
    support_map = table();
    if add_support
        [mpc, support_map] = add_temporary_q_support(mpc, ...
            options.candidate_bus_ids, options.q_support_limit_mvar);
    end
    if remove_ratings
        mpc.branch(:, RATE_A:RATE_C) = 0;
    end
    scheduled_pg = mpc.gen(:, PG);
    mpc = set_diagnostic_costs(mpc, scheduled_pg, original_ng, ...
        support_map, options);
    if voltage_penalty > 0
        mpc = add_voltage_deviation_cost(mpc, voltage_penalty, 1.0);
    end
    [result, success, termination_class, note] = solve_opf(mpc, use_vg, solver);
    [summary, support, redispatch, interface_detail, bindings, q_dispatch, ...
        external_q] = summarize_case(result, success, termination_class, note, ...
        case_id, scenario_id, ...
        scheduled_pg, original_ng, support_map, ext, voltage_penalty, ...
        q_limit_mode, use_vg, solver, options);
    summary_rows = append_table(summary_rows, summary);
    support_rows = append_table(support_rows, support);
    redispatch_rows = append_table(redispatch_rows, redispatch);
    interface_rows = append_table(interface_rows, interface_detail);
    binding_rows = append_table(binding_rows, bindings);
    q_dispatch_rows = append_table(q_dispatch_rows, q_dispatch);
    external_q_rows = append_table(external_q_rows, external_q);
end

writetable(summary_rows, options.summary_file);
writetable(support_rows, options.support_file);
writetable(redispatch_rows, options.redispatch_file);
writetable(interface_rows, options.interface_file);
writetable(binding_rows, options.binding_file);
writetable(q_dispatch_rows, options.q_dispatch_file);
writetable(external_q_rows, options.external_q_file);
outputs = struct('summary_file', options.summary_file, ...
    'support_file', options.support_file, ...
    'redispatch_file', options.redispatch_file, ...
    'interface_file', options.interface_file, ...
    'binding_file', options.binding_file, ...
    'q_dispatch_file', options.q_dispatch_file, ...
    'external_q_file', options.external_q_file, ...
    'q_target_file', options.q_target_file, ...
    'voltage_setpoint_file', options.voltage_setpoint_file, ...
    'summary', summary_rows, 'scenario_id', scenario_id);
end

function options = defaults(options, helper_dir)
items = { ...
    'scenario_id', "S3_2019_SHOULDER_LIGHT_LOAD_PUBLIC"; ...
    'structural_case', 'npcc_ny_lite_s7_seven_interface_perform_direct_candidate'; ...
    'zonal_file', fullfile(helper_dir, 's8_final_zonal_generation.csv'); ...
    'external_target_file', fullfile(helper_dir, 'ny_external_interface_targets.csv'); ...
    'interface_target_file', fullfile(helper_dir, 'nyiso_public_interface_targets.csv'); ...
    'interface_scale_file', fullfile(helper_dir, 'nyiso_interface_objective_scales.csv'); ...
    'candidate_bus_ids', [39; 73; 74; 9001; 9002; 56; 57; 71; 78; 79; 81; 82]; ...
    'q_support_limit_mvar', 2500; ...
    'q_support_cost_per_mvar', 1; ...
    'p_deviation_cost_per_mw2', 1; ...
    'voltage_penalty_rho', 1e4; ...
    'opf_solver', 'IPOPT'; ...
    'summary_file', fullfile(helper_dir, 's9a_q_support_case_summary.csv'); ...
    'support_file', fullfile(helper_dir, 's9a_q_support_by_bus.csv'); ...
    'redispatch_file', fullfile(helper_dir, 's9a_p_redispatch.csv'); ...
    'interface_file', fullfile(helper_dir, 's9a_interface_residuals.csv'); ...
    'binding_file', fullfile(helper_dir, 's9a_binding_constraints.csv'); ...
    'q_dispatch_file', fullfile(helper_dir, 's9a_existing_generator_q_dispatch.csv'); ...
    'external_q_file', fullfile(helper_dir, 's9a_external_boundary_q_dispatch.csv'); ...
    'q_target_file', fullfile(helper_dir, 's9a_perform_zonal_q_capability.csv'); ...
    'voltage_setpoint_file', fullfile(helper_dir, 's9a_voltage_setpoint_audit.csv')};
for k = 1:size(items, 1)
    if ~isfield(options, items{k, 1}), options.(items{k, 1}) = items{k, 2}; end
end
end

function vector = vector_by_zone(tbl, zones, variable)
vector = zeros(numel(zones), 1);
for z = 1:numel(zones)
    idx = find(string(tbl.zone) == zones(z), 1);
    if isempty(idx), error('Missing S8 generation row for zone %s.', zones(z)); end
    vector(z) = tbl.(variable)(idx);
end
end

function [mpc, map] = add_temporary_q_support(mpc, bus_ids, qlimit)
define_constants;
map = table();
for k = 1:numel(bus_ids)
    bus_id = bus_ids(k);
    bi = find(mpc.bus(:, BUS_I) == bus_id, 1);
    if isempty(bi), error('Temporary Q-support bus %.0f is missing.', bus_id); end
    if mpc.bus(bi, BUS_TYPE) == PQ, mpc.bus(bi, BUS_TYPE) = PV; end
    for polarity = [1 -1]
        row = zeros(1, size(mpc.gen, 2));
        row(GEN_BUS) = bus_id;
        row(PG) = 0;
        row(QG) = 0;
        if polarity > 0
            row(QMIN) = 0;
            row(QMAX) = qlimit;
            kind = "positive";
        else
            row(QMIN) = -qlimit;
            row(QMAX) = 0;
            kind = "negative";
        end
        existing = find(mpc.gen(:, GEN_BUS) == bus_id & ...
            mpc.gen(:, GEN_STATUS) > 0, 1);
        if isempty(existing)
            row(VG) = mpc.bus(bi, VM);
        else
            row(VG) = mpc.gen(existing, VG);
        end
        row(MBASE) = mpc.baseMVA;
        row(GEN_STATUS) = 1;
        row(PMAX) = 0;
        row(PMIN) = 0;
        mpc.gen(end + 1, :) = row;
        gi = size(mpc.gen, 1);
        bus_name = string(strtrim(mpc.bus_name{bi}));
        mrow = table(gi, bus_id, bus_name, kind, qlimit, ...
            'VariableNames', {'gen_index','bus_id','bus_name','polarity', ...
            'q_limit_mvar'});
        map = append_table(map, mrow);
    end
end
end

function mpc = set_diagnostic_costs(mpc, scheduled_pg, original_ng, map, options)
define_constants;
ng = size(mpc.gen, 1);
gencost = zeros(2 * ng, 7);
for g = 1:ng
    rho = 0;
    if g <= original_ng && mpc.gen(g, PMAX) - mpc.gen(g, PMIN) > 1e-6
        rho = options.p_deviation_cost_per_mw2;
    end
    p0 = scheduled_pg(g);
    gencost(g, :) = [2 0 0 3 rho -2 * rho * p0 rho * p0^2];
    gencost(ng + g, 1:6) = [2 0 0 2 0 0];
end
for k = 1:height(map)
    g = map.gen_index(k);
    coefficient = options.q_support_cost_per_mvar;
    if map.polarity(k) == "negative", coefficient = -coefficient; end
    gencost(ng + g, 1:6) = [2 0 0 2 coefficient 0];
end
mpc.gencost = gencost;
end

function [result, success, termination_class, note] = solve_opf(mpc, use_vg, solver)
success = false;
note = "";
result = struct();
mpopt = mpoption('verbose', 0, 'out.all', 0, ...
    'opf.ac.solver', char(solver), 'opf.flow_lim', 'S', ...
    'opf.violation', 1e-6, 'opf.use_vg', use_vg, ...
    'opf.ignore_angle_lim', 0);
try
    result = runopf(mpc, mpopt);
    success = isfield(result, 'success') && logical(result.success);
    if success
        termination_class = "feasible_success";
    else
        termination_class = "solver_nonconvergence";
        note = "ACOPF returned success = 0";
    end
catch ME
    termination_class = "solver_exception";
    note = string(regexprep(ME.message, '\s+', ' '));
    if ~isempty(ME.stack)
        note = note + " @ " + string(ME.stack(1).name) + ":" + ...
            string(ME.stack(1).line);
    end
end
end

function [summary, support, redispatch, detail, bindings, q_dispatch, ...
        external_q] = summarize_case(result, success, termination_class, note, ...
        case_id, scenario_id, scheduled_pg, ...
        original_ng, support_map, ext, voltage_penalty, q_limit_mode, use_vg, ...
        solver, options)
if ~success
    summary = failed_summary(case_id, scenario_id, q_limit_mode, use_vg, ...
        solver, termination_class, note);
    support = table(); redispatch = table(); detail = table(); bindings = table();
    q_dispatch = table(); external_q = table();
    return;
end
define_constants;
targets = read_public_interface_targets(scenario_id, ...
    options.interface_target_file);
flows = ny_lite_interface_flows(result, ny_lite_interface_definitions(result));
[J, detail] = interface_target_objective_balanced(flows, targets, ...
    struct('scale_file', options.interface_scale_file, 'min_scale_mw', 500));
detail = addvars(detail, repmat(case_id, height(detail), 1), ...
    repmat(scenario_id, height(detail), 1), 'Before', 1, ...
    'NewVariableNames', {'case_id','scenario_id'});

support = support_report(result, support_map, case_id, scenario_id);
internal_idx = setdiff((1:original_ng)', ext.added_gen_index(:));
delta_pg = result.gen(internal_idx, PG) - scheduled_pg(internal_idx);
redispatch = redispatch_report(result, internal_idx, scheduled_pg, ...
    case_id, scenario_id);
q_dispatch = existing_q_report(result, internal_idx, case_id, scenario_id);
external_q = boundary_q_report(result, ext, case_id, scenario_id);
sf = hypot(result.branch(:, PF), result.branch(:, QF));
st = hypot(result.branch(:, PT), result.branch(:, QT));
smax = max(sf, st);
rated = result.branch(:, RATE_A) > 0 & result.branch(:, BR_STATUS) > 0;
binding_branch = rated & smax >= result.branch(:, RATE_A) - 1e-3;
vbound = result.bus(:, VM) <= result.bus(:, VMIN) + 1e-5 | ...
    result.bus(:, VM) >= result.bus(:, VMAX) - 1e-5;
bindings = binding_report(result, binding_branch, vbound, case_id, scenario_id);
external_error = max(abs(result.gen(ext.added_gen_index, PG) - ...
    ext.target_flow_mw));
if isempty(support)
    qpositive = 0; qnegative = 0; qabs = 0; active_support_buses = 0;
else
    qpositive = sum(support.positive_q_mvar);
    qnegative = sum(support.negative_q_mvar);
    qabs = sum(support.absolute_q_mvar);
    active_support_buses = sum(support.absolute_q_mvar > 1e-3);
end
summary = table(case_id, scenario_id, q_limit_mode, use_vg, solver, true, ...
    termination_class, result.f, ...
    voltage_penalty, ...
    qpositive, qnegative, ...
    qabs, active_support_buses, sum(abs(delta_pg)), max(abs(delta_pg)), ...
    min(result.bus(:, VM)), max(result.bus(:, VM)), ...
    sum((result.bus(:, VM) - 1).^2), sum(vbound), ...
    sum(binding_branch), max([0; smax(rated) ./ result.branch(rated, RATE_A)]), ...
    external_error, J, max(abs(detail.residual_mw)), note, ...
    'VariableNames', summary_names());
end

function rows = existing_q_report(result, idx, case_id, scenario_id)
define_constants;
result = attach_nyiso_zone_metadata(result);
rows = table();
for k = 1:numel(idx)
    g = idx(k);
    bi = find(result.bus(:, BUS_I) == result.gen(g, GEN_BUS), 1);
    qrange = result.gen(g, QMAX) - result.gen(g, QMIN);
    if qrange > 1e-9
        utilization = (result.gen(g, QG) - result.gen(g, QMIN)) / qrange;
    else
        utilization = NaN;
    end
    row = table(case_id, scenario_id, g, result.gen(g, GEN_BUS), ...
        string(strtrim(result.bus_name{bi})), ...
        string(result.userdata.nyiso_physical_zone{bi}), result.gen(g, QG), ...
        result.gen(g, QMIN), result.gen(g, QMAX), utilization, ...
        abs(result.gen(g, QG) - result.gen(g, QMIN)) <= 1e-4, ...
        abs(result.gen(g, QG) - result.gen(g, QMAX)) <= 1e-4, ...
        'VariableNames', {'case_id','scenario_id','gen_index','bus_id', ...
        'bus_name','zone','qg_mvar','qmin_mvar','qmax_mvar', ...
        'q_range_position','at_qmin','at_qmax'});
    rows = append_table(rows, row);
end
end

function rows = boundary_q_report(result, ext, case_id, scenario_id)
define_constants;
rows = table();
for k = 1:height(ext)
    g = ext.added_gen_index(k);
    target_q = ext.target_q_mvar(k);
    qg = result.gen(g, QG);
    qmin = result.gen(g, QMIN);
    qmax = result.gen(g, QMAX);
    row = table(case_id, scenario_id, ...
        string(ext.external_interface_name(k)), g, result.gen(g, GEN_BUS), ...
        result.gen(g, PG), qg, target_q, qg - target_q, qmin, qmax, ...
        abs(qg - qmin) <= 1e-4, abs(qg - qmax) <= 1e-4, ...
        'VariableNames', {'case_id','scenario_id','external_interface_name', ...
        'gen_index','bus_id','pg_mw','qg_mvar','target_q_mvar', ...
        'q_deviation_mvar','qmin_mvar','qmax_mvar','at_qmin','at_qmax'});
    rows = append_table(rows, row);
end
end

function support = support_report(result, map, case_id, scenario_id)
support = table();
if isempty(map), return; end
bus_ids = unique(map.bus_id, 'stable');
for k = 1:numel(bus_ids)
    bus_id = bus_ids(k);
    rows = map(map.bus_id == bus_id, :);
    pos = rows.gen_index(rows.polarity == "positive");
    neg = rows.gen_index(rows.polarity == "negative");
    qpos = sum(result.gen(pos, 3));
    qneg = sum(result.gen(neg, 3));
    qabs = qpos - qneg;
    row = table(case_id, scenario_id, bus_id, rows.bus_name(1), ...
        qpos, qneg, qpos + qneg, qabs, ...
        any(result.gen(pos, 3) >= result.gen(pos, 4) - 1e-4), ...
        any(result.gen(neg, 3) <= result.gen(neg, 5) + 1e-4), ...
        'VariableNames', {'case_id','scenario_id','bus_id','bus_name', ...
        'positive_q_mvar','negative_q_mvar','net_q_mvar', ...
        'absolute_q_mvar','positive_at_limit','negative_at_limit'});
    support = append_table(support, row);
end
end

function rows = redispatch_report(result, idx, scheduled, case_id, scenario_id)
define_constants;
result = attach_nyiso_zone_metadata(result);
rows = table();
for k = 1:numel(idx)
    g = idx(k);
    bi = find(result.bus(:, BUS_I) == result.gen(g, GEN_BUS), 1);
    delta = result.gen(g, PG) - scheduled(g);
    if abs(delta) <= 1e-5, continue; end
    row = table(case_id, scenario_id, g, result.gen(g, GEN_BUS), ...
        string(strtrim(result.bus_name{bi})), ...
        string(result.userdata.nyiso_physical_zone{bi}), scheduled(g), ...
        result.gen(g, PG), delta, ...
        'VariableNames', {'case_id','scenario_id','gen_index','bus_id', ...
        'bus_name','zone','scheduled_pg_mw','opf_pg_mw','redispatch_mw'});
    rows = append_table(rows, row);
end
end

function rows = binding_report(result, branch_mask, voltage_mask, case_id, scenario_id)
define_constants;
rows = table();
for b = find(branch_mask)'
    fi = find(result.bus(:, BUS_I) == result.branch(b, F_BUS), 1);
    ti = find(result.bus(:, BUS_I) == result.branch(b, T_BUS), 1);
    sf = hypot(result.branch(b, PF), result.branch(b, QF));
    st = hypot(result.branch(b, PT), result.branch(b, QT));
    row = table(case_id, scenario_id, "BRANCH", b, ...
        string(strtrim(result.bus_name{fi})) + " - " + ...
        string(strtrim(result.bus_name{ti})), max(sf, st), ...
        result.branch(b, RATE_A), ...
        'VariableNames', {'case_id','scenario_id','constraint_type', ...
        'element_index','element_name','value','limit'});
    rows = append_table(rows, row);
end
for b = find(voltage_mask)'
    limit = result.bus(b, VMAX);
    if result.bus(b, VM) <= result.bus(b, VMIN) + 1e-5
        limit = result.bus(b, VMIN);
    end
    row = table(case_id, scenario_id, "VOLTAGE", b, ...
        string(strtrim(result.bus_name{b})), result.bus(b, VM), limit, ...
        'VariableNames', {'case_id','scenario_id','constraint_type', ...
        'element_index','element_name','value','limit'});
    rows = append_table(rows, row);
end
end

function summary = failed_summary(case_id, scenario_id, q_limit_mode, use_vg, ...
        solver, termination_class, note)
values = {case_id, scenario_id, q_limit_mode, use_vg, solver, false, ...
    termination_class, NaN, ...
    NaN, NaN, NaN, NaN, ...
    NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, note};
summary = cell2table(values, 'VariableNames', summary_names());
end

function names = summary_names()
names = {'case_id','scenario_id','q_limit_mode','opf_use_vg', ...
    'opf_solver','opf_success','termination_class','objective', ...
    'voltage_penalty_rho', ...
    'positive_q_support_mvar','negative_q_support_mvar', ...
    'absolute_q_support_mvar','active_q_support_bus_count', ...
    'total_absolute_p_redispatch_mw','max_single_generator_redispatch_mw', ...
    'min_voltage_pu','max_voltage_pu','sum_squared_voltage_deviation', ...
    'voltage_bound_count', ...
    'binding_branch_count','max_branch_loading_ratio', ...
    'max_external_schedule_error_mw','interface_objective', ...
    'max_abs_interface_residual_mw','diagnostic'};
end

function mpc = apply_zonal_q_limits(mpc, targets, external_idx)
define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
[mapped, bi] = ismember(mpc.gen(:, GEN_BUS), mpc.bus(:, BUS_I));
gen_zone = strings(size(mpc.gen, 1), 1);
gen_zone(mapped) = string(mpc.userdata.nyiso_physical_zone(bi(mapped)));
internal = mpc.gen(:, GEN_STATUS) > 0 & gen_zone ~= "";
internal(external_idx) = false;
for z = 1:height(targets)
    zone = string(targets.zone(z));
    idx = find(internal & gen_zone == zone);
    if isempty(idx), continue; end
    weights = max(0, mpc.gen(idx, PMAX));
    if sum(weights) <= 0, weights = ones(numel(idx), 1); end
    weights = weights / sum(weights);
    mpc.gen(idx, QMIN) = targets.target_qmin_mvar(z) * weights;
    mpc.gen(idx, QMAX) = targets.target_qmax_mvar(z) * weights;
    mpc.gen(idx, QG) = min(max(mpc.gen(idx, QG), mpc.gen(idx, QMIN)), ...
        mpc.gen(idx, QMAX));
end
end

function audit = voltage_setpoint_audit(mpc, external_idx)
define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
online = mpc.gen(:, GEN_STATUS) > 0;
online(external_idx) = false;
bus_ids = unique(mpc.gen(online, GEN_BUS), 'stable');
audit = table();
for k = 1:numel(bus_ids)
    bus_id = bus_ids(k);
    bi = find(mpc.bus(:, BUS_I) == bus_id, 1);
    gi = find(online & mpc.gen(:, GEN_BUS) == bus_id);
    vg = mpc.gen(gi, VG);
    row = table(bus_id, string(strtrim(mpc.bus_name{bi})), ...
        string(mpc.userdata.nyiso_physical_zone{bi}), numel(gi), ...
        min(vg), max(vg), max(vg) - min(vg), mpc.bus(bi, VMIN), ...
        mpc.bus(bi, VMAX), any(vg < mpc.bus(bi, VMIN) - 1e-9 | ...
        vg > mpc.bus(bi, VMAX) + 1e-9), sum(mpc.gen(gi, QMIN)), ...
        sum(mpc.gen(gi, QMAX)), ...
        'VariableNames', {'bus_id','bus_name','zone','online_gen_count', ...
        'min_vg_pu','max_vg_pu','vg_spread_pu','bus_vmin_pu','bus_vmax_pu', ...
        'vg_outside_bus_bounds','aggregate_qmin_mvar','aggregate_qmax_mvar'});
    audit = append_table(audit, row);
end
audit = sortrows(audit, {'vg_outside_bus_bounds','vg_spread_pu'}, ...
    {'descend','descend'});
end

function mpc = set_zone_reference(mpc, external_idx, zone_name)
define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
[mapped, bi] = ismember(mpc.gen(:, GEN_BUS), mpc.bus(:, BUS_I));
zone = strings(size(mpc.gen, 1), 1);
zone(mapped) = string(mpc.userdata.nyiso_physical_zone(bi(mapped)));
mask = mpc.gen(:, GEN_STATUS) > 0 & zone == zone_name;
mask(external_idx) = false;
idx = find(mask);
qrange = mpc.gen(idx, QMAX) - mpc.gen(idx, QMIN);
if any(qrange > 1e-6), idx = idx(qrange > 1e-6); end
[~, k] = max(mpc.gen(idx, PMAX) - mpc.gen(idx, PG));
mpc = set_scenario_reference_bus(mpc, idx(k), ...
    struct('require_external', false));
end

function out = append_table(out, row)
if isempty(row), return; end
if isempty(out), out = row; else, out = [out; row]; end
end
