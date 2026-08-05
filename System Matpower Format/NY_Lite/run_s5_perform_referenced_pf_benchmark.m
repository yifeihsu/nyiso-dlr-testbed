function outputs = run_s5_perform_referenced_pf_benchmark(options)
%RUN_S5_PERFORM_REFERENCED_PF_BENCHMARK Test PERFORM allocation/tie priors.
%   For every public scenario, an S4 NY-only ACOPF provides fixed zonal
%   generation totals. Full-NPCC AC PF then compares S4 versus PERFORM
%   within-zone bus allocation under three tie parameter treatments.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

if ~isfield(options, 'scenario_file')
    options.scenario_file = fullfile(helper_dir, 'nyiso_public_scenarios.csv');
end
if ~isfield(options, 'external_target_file')
    options.external_target_file = fullfile(helper_dir, 'ny_external_interface_targets.csv');
end
if ~isfield(options, 'interface_target_file')
    options.interface_target_file = fullfile(helper_dir, 'nyiso_public_interface_targets.csv');
end
if ~isfield(options, 'interface_scale_file')
    options.interface_scale_file = fullfile(helper_dir, 'nyiso_interface_objective_scales.csv');
end
if ~isfield(options, 'result_file')
    options.result_file = fullfile(helper_dir, 's5_perform_pf_results.csv');
end
if ~isfield(options, 'residual_file')
    options.residual_file = fullfile(helper_dir, 's5_perform_pf_interface_residuals.csv');
end
if ~isfield(options, 'summary_file')
    options.summary_file = fullfile(helper_dir, 's5_perform_pf_summary.csv');
end
if ~isfield(options, 'gsk_file')
    options.gsk_file = fullfile(helper_dir, 's5_perform_generation_shift_keys.csv');
end
if ~isfield(options, 'plant_file')
    options.plant_file = fullfile(helper_dir, 's5_perform_generation_by_plant.csv');
end
if ~isfield(options, 'tie_file')
    options.tie_file = fullfile(helper_dir, 's5_perform_tieline_alignment.csv');
end
if ~isfield(options, 'zonal_target_file')
    options.zonal_target_file = fullfile(helper_dir, 's5_s4_reference_zonal_generation.csv');
end
if ~isfield(options, 'bus_target_file')
    options.bus_target_file = fullfile(helper_dir, 's5_s4_reference_bus_generation.csv');
end
if ~isfield(options, 'allocation_file')
    options.allocation_file = fullfile(helper_dir, 's5_perform_applied_bus_generation.csv');
end
if ~isfield(options, 'capacity_file')
    options.capacity_file = fullfile(helper_dir, 's5_perform_capacity_alignment.csv');
end
if ~isfield(options, 'violation_file')
    options.violation_file = fullfile(helper_dir, 's5_perform_pf_violations.csv');
end

scenarios = readtable(options.scenario_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
base_full = loadcase('npcc_ny_lite_s4_cost_calibration_candidate_v2');
[gsk, plant_summary] = build_perform_npcc_generation_shift_keys(base_full);
[~, capacity_rows] = align_npcc_generation_capacity_to_perform_gsk(base_full, gsk);

tie_modes = ["current", "perform_rx", "perform_rxb"];
allocation_modes = ["s4", "perform", "perform_cap"];
tie_rows = table();
for t = 1:numel(tie_modes)
    [~, row] = apply_perform_tieline_alignment(base_full, tie_modes(t));
    tie_rows = append_table(tie_rows, row);
end

opf_opt = mpoption('verbose', 0, 'out.all', 0, ...
    'opf.ac.solver', 'IPOPT', 'opf.flow_lim', 'S', ...
    'opf.violation', 1e-6, 'opf.use_vg', 0, 'opf.ignore_angle_lim', 0);
pf_opt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1);

result_rows = table();
residual_rows = table();
zonal_rows = table();
bus_rows = table();
allocation_rows = table();
violation_rows = table();

for s = 1:height(scenarios)
    scenario_id = string(scenarios.scenario_id(s));
    [reference, bus_targets, zonal_targets, ref_note] = ...
        build_s4_reference_dispatch(scenario_id, opf_opt, options);
    if ~isempty(zonal_targets)
        zonal_targets = addvars(zonal_targets, ...
            repmat(scenario_id, height(zonal_targets), 1), 'Before', 1, ...
            'NewVariableNames', 'scenario_id');
        zonal_rows = append_table(zonal_rows, zonal_targets);
    end
    if ~isempty(bus_targets)
        bus_targets = addvars(bus_targets, ...
            repmat(scenario_id, height(bus_targets), 1), 'Before', 1, ...
            'NewVariableNames', 'scenario_id');
        bus_rows = append_table(bus_rows, bus_targets);
    end

    for a = 1:numel(allocation_modes)
        for t = 1:numel(tie_modes)
            allocation_mode = allocation_modes(a);
            tie_mode = tie_modes(t);
            variant_id = upper(allocation_mode) + "_GSK__" + tie_mode;
            [row, detail, allocation, violations] = run_full_pf_variant(scenario_id, ...
                allocation_mode, tie_mode, variant_id, reference, ...
                bus_targets, zonal_targets, gsk, pf_opt, options, ref_note);
            result_rows = append_table(result_rows, row);
            residual_rows = append_table(residual_rows, detail);
            violation_rows = append_table(violation_rows, violations);
            if ~isempty(allocation)
                allocation = addvars(allocation, ...
                    repmat(scenario_id, height(allocation), 1), ...
                    repmat(variant_id, height(allocation), 1), ...
                    'Before', 1, 'NewVariableNames', {'scenario_id','variant_id'});
                allocation_rows = append_table(allocation_rows, allocation);
            end
        end
    end
end

summary_rows = summarize_variants(result_rows);
writetable(result_rows, options.result_file);
writetable(residual_rows, options.residual_file);
writetable(summary_rows, options.summary_file);
writetable(gsk, options.gsk_file);
writetable(plant_summary, options.plant_file);
writetable(tie_rows, options.tie_file);
writetable(zonal_rows, options.zonal_target_file);
writetable(bus_rows, options.bus_target_file);
writetable(allocation_rows, options.allocation_file);
writetable(capacity_rows, options.capacity_file);
writetable(violation_rows, options.violation_file);

outputs = struct('result_file', options.result_file, ...
    'residual_file', options.residual_file, 'summary_file', options.summary_file, ...
    'gsk_file', options.gsk_file, 'plant_file', options.plant_file, ...
    'tie_file', options.tie_file, 'zonal_target_file', options.zonal_target_file, ...
    'bus_target_file', options.bus_target_file, ...
    'allocation_file', options.allocation_file, ...
    'capacity_file', options.capacity_file, ...
    'violation_file', options.violation_file, ...
    'result_row_count', height(result_rows), ...
    'residual_row_count', height(residual_rows), ...
    'summary_row_count', height(summary_rows));
end

function [results, bus_targets, zonal_targets, note] = ...
        build_s4_reference_dispatch(scenario_id, mpopt, options)
define_constants;
note = "";
try
    base = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
    [mpc, ~] = build_ny_only_equivalent_case(base);
    [mpc, ~] = add_ny_downstate_delivery_spine(mpc, 'full');
    [mpc, ~] = scale_ny_downstate_delivery_spine_impedance(mpc, 1.0, ...
        struct('include_gilboa_leeds', false));
    [mpc, ~] = apply_nyiso_zonal_loads(mpc, scenario_id, 1.0, ...
        struct('preserve_total_ny_load', true));
    [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
        scenario_id, struct('target_file', options.external_target_file));
    [mpc, ~] = add_s4_zonal_capability_equivalents(mpc, ...
        struct('include_zone_j', true, 'zone_j_total_pmax_mw', 3000, ...
        'zone_j_cost_c1', 180, 'zone_j_cost_c2', 0.02, ...
        'equiv_cost_c1', 180, 'equiv_cost_c2', 0.02, ...
        'q_abs_ratio', 0, 'apply_upstate_participation_caps', true, ...
        'abc_cap_factor', 0.8, 'reclassify_ce_ug', true));
    results = runopf(mpc, mpopt);
    if ~results.success
        note = "S4 reference ACOPF did not converge";
        bus_targets = table(); zonal_targets = table();
        return;
    end
    results = attach_nyiso_zone_metadata(results);
    external_idx = ext_report.added_gen_index(:);
    internal = results.gen(:, GEN_STATUS) > 0;
    internal(external_idx) = false;
    [gen_mapped, gen_bus_idx] = ismember(results.gen(:, GEN_BUS), results.bus(:, BUS_I));
    gen_zone = strings(size(results.gen, 1), 1);
    gen_zone(gen_mapped) = string(results.userdata.nyiso_physical_zone(gen_bus_idx(gen_mapped)));
    internal = internal & gen_zone ~= "";

    buses = unique(results.gen(internal, GEN_BUS), 'stable');
    bus_targets = table();
    for k = 1:numel(buses)
        gi = internal & results.gen(:, GEN_BUS) == buses(k);
        bi = find(results.bus(:, BUS_I) == buses(k), 1);
        row = table(gen_zone(find(gi, 1)), buses(k), ...
            string(strtrim(results.bus_name{bi})), sum(results.gen(gi, PG)), ...
            'VariableNames', {'zone','npcc_bus_id','npcc_bus_name','target_bus_pg_mw'});
        bus_targets = append_table(bus_targets, row);
    end
    zones = unique(gen_zone(internal), 'stable');
    zonal_targets = table();
    for k = 1:numel(zones)
        target = sum(results.gen(internal & gen_zone == zones(k), PG));
        row = table(zones(k), target, ...
            'VariableNames', {'zone','target_generation_mw'});
        zonal_targets = append_table(zonal_targets, row);
    end
catch ME
    results = struct('success', false);
    bus_targets = table(); zonal_targets = table();
    note = "S4 reference error: " + string(regexprep(ME.message, '\s+', ' '));
end
end

function [row, detail, allocation_report, violations] = run_full_pf_variant(scenario_id, ...
        allocation_mode, tie_mode, variant_id, reference, bus_targets, ...
        zonal_targets, gsk, mpopt, options, ref_note)
define_constants;
status = "ok";
note = ref_note;
allocation_report = table();
result = struct();
ref_opf_success = isfield(reference, 'success') && logical(reference.success);
opf_classic = NaN; opf_fixed = NaN;
try
    if ~ref_opf_success || isempty(zonal_targets)
        error('S4 reference dispatch unavailable for scenario %s.', scenario_id);
    end
    [opf_classic, opf_fixed] = score_interfaces(reference, scenario_id, options);
    mpc = loadcase('npcc_ny_lite_s4_cost_calibration_candidate_v2');
    [mpc, ~] = apply_nyiso_zonal_loads(mpc, scenario_id, 1.0, ...
        struct('preserve_total_ny_load', true));
    [mpc, ~] = apply_perform_tieline_alignment(mpc, tie_mode);
    if allocation_mode == "perform_cap"
        [mpc, ~] = align_npcc_generation_capacity_to_perform_gsk(mpc, gsk);
        [mpc, allocation_report] = apply_perform_generation_allocation( ...
            mpc, zonal_targets, gsk);
    elseif allocation_mode == "perform"
        [mpc, allocation_report] = apply_perform_generation_allocation( ...
            mpc, zonal_targets, gsk);
    else
        [mpc, allocation_report] = apply_s4_bus_targets(mpc, bus_targets);
    end
    ref_gen = choose_external_reference(mpc);
    [mpc, ref_report] = set_scenario_reference_bus(mpc, ref_gen);
    result = runpf(mpc, mpopt);
    if ~result.success
        status = "pf_failed";
    end
catch ME
    status = "error";
    note = string(regexprep(ME.message, '\s+', ' '));
    ref_gen = NaN;
    ref_report = struct('reference_bus_id', NaN);
end

[row, detail] = summarize_pf(scenario_id, allocation_mode, tie_mode, ...
    variant_id, status, note, result, ref_opf_success, opf_classic, ...
    opf_fixed, ref_gen, ref_report, allocation_report, bus_targets, options);
violations = collect_violations(result, scenario_id, variant_id, ...
    allocation_mode, tie_mode);
end

function rows = collect_violations(results, scenario_id, variant_id, allocation_mode, tie_mode)
define_constants;
rows = table();
if ~isfield(results, 'bus'), return; end
results = attach_nyiso_zone_metadata(results);
names = string(results.bus_name(:));
zones = string(results.userdata.nyiso_physical_zone(:));

low = find(results.bus(:, VM) < results.bus(:, VMIN) - 1e-6);
high = find(results.bus(:, VM) > results.bus(:, VMAX) + 1e-6);
for bi = low(:)'
    rows = append_table(rows, violation_row(scenario_id, variant_id, ...
        allocation_mode, tie_mode, "LOW_VOLTAGE", bi, ...
        results.bus(bi, BUS_I), names(bi), zones(bi), NaN, "", "", ...
        results.bus(bi, VM), results.bus(bi, VMIN), ...
        results.bus(bi, VMIN) - results.bus(bi, VM), "pu"));
end
for bi = high(:)'
    rows = append_table(rows, violation_row(scenario_id, variant_id, ...
        allocation_mode, tie_mode, "HIGH_VOLTAGE", bi, ...
        results.bus(bi, BUS_I), names(bi), zones(bi), NaN, "", "", ...
        results.bus(bi, VM), results.bus(bi, VMAX), ...
        results.bus(bi, VM) - results.bus(bi, VMAX), "pu"));
end

sf = hypot(results.branch(:, PF), results.branch(:, QF));
st = hypot(results.branch(:, PT), results.branch(:, QT));
smax = max(sf, st);
over = find(results.branch(:, BR_STATUS) > 0 & results.branch(:, RATE_A) > 0 & ...
    smax > results.branch(:, RATE_A) + 1e-6);
for br = over(:)'
    fi = find(results.bus(:, BUS_I) == results.branch(br, F_BUS), 1);
    ti = find(results.bus(:, BUS_I) == results.branch(br, T_BUS), 1);
    rows = append_table(rows, violation_row(scenario_id, variant_id, ...
        allocation_mode, tie_mode, "BRANCH_OVERLOAD", br, ...
        results.branch(br, F_BUS), names(fi), zones(fi), ...
        results.branch(br, T_BUS), names(ti), zones(ti), ...
        smax(br), results.branch(br, RATE_A), ...
        smax(br) - results.branch(br, RATE_A), "MVA"));
end

online = find(results.gen(:, GEN_STATUS) > 0);
pviol = max(results.gen(online, PG) - results.gen(online, PMAX), ...
    results.gen(online, PMIN) - results.gen(online, PG));
bad = online(pviol > 1e-6);
for gi = bad(:)'
    bi = find(results.bus(:, BUS_I) == results.gen(gi, GEN_BUS), 1);
    limit = results.gen(gi, PMAX);
    if results.gen(gi, PG) < results.gen(gi, PMIN), limit = results.gen(gi, PMIN); end
    rows = append_table(rows, violation_row(scenario_id, variant_id, ...
        allocation_mode, tie_mode, "GEN_P_LIMIT", gi, ...
        results.gen(gi, GEN_BUS), names(bi), zones(bi), NaN, "", "", ...
        results.gen(gi, PG), limit, ...
        max(results.gen(gi, PG) - results.gen(gi, PMAX), ...
        results.gen(gi, PMIN) - results.gen(gi, PG)), "MW"));
end
end

function row = violation_row(scenario_id, variant_id, allocation_mode, tie_mode, ...
        kind, element_index, from_bus, from_name, from_zone, to_bus, to_name, ...
        to_zone, value, limit, amount, units)
row = table(string(scenario_id), string(variant_id), string(allocation_mode), ...
    string(tie_mode), string(kind), element_index, from_bus, ...
    strtrim(string(from_name)), string(from_zone), to_bus, ...
    strtrim(string(to_name)), string(to_zone), value, limit, amount, string(units), ...
    'VariableNames', {'scenario_id','variant_id','allocation_mode','tie_mode', ...
    'violation_type','element_index','from_or_bus_id','from_or_bus_name', ...
    'from_or_bus_zone','to_bus_id','to_bus_name','to_bus_zone','value', ...
    'limit','violation_amount','units'});
end

function [mpc, report] = apply_s4_bus_targets(mpc, targets)
define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
[mapped, bi] = ismember(mpc.gen(:, GEN_BUS), mpc.bus(:, BUS_I));
zone = strings(size(mpc.gen, 1), 1);
zone(mapped) = string(mpc.userdata.nyiso_physical_zone(bi(mapped)));
ny_online = mpc.gen(:, GEN_STATUS) > 0 & zone ~= "";
mpc.gen(ny_online, PG) = 0;
report = table();
for k = 1:height(targets)
    bus_id = targets.npcc_bus_id(k);
    gi = find(ny_online & mpc.gen(:, GEN_BUS) == bus_id);
    if isempty(gi)
        error('S4 target bus %.0f has no online full-NPCC generator.', bus_id);
    end
    pg = project_unit_total(targets.target_bus_pg_mw(k), ...
        mpc.gen(gi, PMIN), mpc.gen(gi, PMAX), mpc.gen(gi, PMAX));
    mpc.gen(gi, PG) = pg;
    zone_total = sum(targets.target_bus_pg_mw(targets.zone == targets.zone(k)));
    row = table(targets.zone(k), bus_id, targets.npcc_bus_name(k), ...
        zone_total, NaN, targets.target_bus_pg_mw(k), ...
        targets.target_bus_pg_mw(k), 0, ...
        sum(mpc.gen(gi, PMIN)), sum(mpc.gen(gi, PMAX)), ...
        "S4 ACOPF bus dispatch", "reference", ...
        'VariableNames', {'zone','npcc_bus_id','npcc_bus_name', ...
        'zone_target_generation_mw','perform_bus_weight','ideal_bus_pg_mw', ...
        'applied_bus_pg_mw','capacity_redispatch_mw', ...
        'bus_pmin_mw','bus_pmax_mw','source_rule','confidence'});
    report = append_table(report, row);
end
end

function gi = choose_external_reference(mpc)
define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
[mapped, bi] = ismember(mpc.gen(:, GEN_BUS), mpc.bus(:, BUS_I));
external = mapped & mpc.gen(:, GEN_STATUS) > 0 & ...
    mpc.userdata.nyiso_zone_id(bi) == 0;
idx = find(external);
if isempty(idx), error('No external online generator is available for PF reference.'); end
[~, k] = max(mpc.gen(idx, PMAX) - mpc.gen(idx, PG));
gi = idx(k);
end

function [classic, fixed] = score_interfaces(results, scenario_id, options)
targets = readtable(options.interface_target_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
targets = targets(targets.scenario_id == string(scenario_id), :);
flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
[classic, ~] = interface_target_objective(flows, targets);
[fixed, ~] = interface_target_objective_balanced(flows, targets, ...
    struct('min_scale_mw', 500, 'scale_file', options.interface_scale_file));
end

function [row, details] = summarize_pf(scenario_id, allocation_mode, tie_mode, ...
        variant_id, status, note, results, ref_opf_success, opf_classic, ...
        opf_fixed, ref_gen, ref_report, allocation_report, bus_targets, options)
define_constants;
targets = readtable(options.interface_target_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
targets = targets(targets.scenario_id == string(scenario_id), :);

if ~isfield(results, 'bus')
    row = failed_result_row(scenario_id, allocation_mode, tie_mode, variant_id, ...
        status, note, ref_opf_success, opf_classic, opf_fixed);
    details = failed_residual_rows(scenario_id, variant_id, allocation_mode, ...
        tie_mode, targets);
    return;
end

online = results.gen(:, GEN_STATUS) > 0;
sf = hypot(results.branch(:, PF), results.branch(:, QF));
st = hypot(results.branch(:, PT), results.branch(:, QT));
smax = max(sf, st);
rated = results.branch(:, RATE_A) > 0 & results.branch(:, BR_STATUS) > 0;
overload = zeros(size(smax));
overload(rated) = smax(rated) - results.branch(rated, RATE_A);

flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
[classic, classic_detail] = interface_target_objective(flows, targets);
[fixed, fixed_detail] = interface_target_objective_balanced(flows, targets, ...
    struct('min_scale_mw', 500, 'scale_file', options.interface_scale_file));

results = attach_nyiso_zone_metadata(results);
[mapped, bi] = ismember(results.gen(:, GEN_BUS), results.bus(:, BUS_I));
ny_gen = mapped & online & results.userdata.nyiso_zone_id(bi) > 0;
reference_pg = NaN; reference_pmax = NaN; reference_violation = NaN;
if isfinite(ref_gen) && ref_gen <= size(results.gen, 1)
    reference_pg = results.gen(ref_gen, PG);
    reference_pmax = results.gen(ref_gen, PMAX);
    reference_violation = max([0, reference_pg - reference_pmax, ...
        results.gen(ref_gen, PMIN) - reference_pg]);
end
p_violation = max([0; results.gen(online, PG) - results.gen(online, PMAX); ...
    results.gen(online, PMIN) - results.gen(online, PG)]);
q_violation = max([0; results.gen(online, QG) - results.gen(online, QMAX); ...
    results.gen(online, QMIN) - results.gen(online, QG)]);
allocation_shift = allocation_shift_metric(allocation_report, bus_targets);

row = table(string(scenario_id), string(variant_id), string(allocation_mode), ...
    string(tie_mode), logical(ref_opf_success), double(results.success), ...
    string(status), string(note), opf_classic, opf_fixed, classic, fixed, ...
    max(abs(fixed_detail.residual_mw), [], 'omitnan'), ref_gen, ...
    ref_report.reference_bus_id, reference_pg, reference_pmax, ...
    reference_violation, sum(results.bus(:, PD)), sum(results.gen(online, PG)), ...
    sum(results.gen(online, PG)) - sum(results.bus(:, PD)), ...
    sum(results.gen(ny_gen, PG)), min(results.bus(:, VM)), max(results.bus(:, VM)), ...
    nnz(results.bus(:, VM) < results.bus(:, VMIN) - 1e-6), ...
    nnz(results.bus(:, VM) > results.bus(:, VMAX) + 1e-6), ...
    nnz(overload > 1e-6), max([0; overload]), p_violation, q_violation, ...
    allocation_shift, ...
    'VariableNames', result_columns());

details = fixed_detail;
details = addvars(details, repmat(string(scenario_id), height(details), 1), ...
    repmat(string(variant_id), height(details), 1), ...
    repmat(string(allocation_mode), height(details), 1), ...
    repmat(string(tie_mode), height(details), 1), ...
    classic_detail.objective_term, 'Before', 1, ...
    'NewVariableNames', {'scenario_id','variant_id','allocation_mode', ...
    'tie_mode','classic_objective_term'});
end

function value = allocation_shift_metric(report, bus_targets)
if isempty(report) || isempty(bus_targets), value = NaN; return; end
value = 0;
buses = unique([report.npcc_bus_id; bus_targets.npcc_bus_id]);
for k = 1:numel(buses)
    a = sum(report.applied_bus_pg_mw(report.npcc_bus_id == buses(k)));
    b = sum(bus_targets.target_bus_pg_mw(bus_targets.npcc_bus_id == buses(k)));
    value = value + abs(a - b);
end
end

function row = failed_result_row(scenario_id, allocation_mode, tie_mode, ...
        variant_id, status, note, ref_success, opf_classic, opf_fixed)
values = num2cell(NaN(1, 21));
row = table(string(scenario_id), string(variant_id), string(allocation_mode), ...
    string(tie_mode), logical(ref_success), 0, string(status), string(note), ...
    opf_classic, opf_fixed, values{:}, 'VariableNames', result_columns());
end

function names = result_columns()
names = {'scenario_id','variant_id','allocation_mode','tie_mode', ...
    's4_reference_opf_success','pf_success','status','note', ...
    's4_reference_classic_objective','s4_reference_fixed_objective', ...
    'classic_interface_objective','fixed_scale_interface_objective', ...
    'max_abs_interface_residual_mw','reference_gen_index','reference_bus_id', ...
    'reference_pg_mw','reference_pmax_mw','reference_p_violation_mw', ...
    'total_load_mw','total_generation_mw','losses_mw','ny_generation_mw', ...
    'min_voltage_pu','max_voltage_pu','low_voltage_violation_count', ...
    'high_voltage_violation_count','branch_overload_count', ...
    'max_branch_overload_mva','max_p_limit_violation_mw', ...
    'max_q_limit_violation_mvar','total_abs_bus_redispatch_vs_s4_mw'};
end

function rows = failed_residual_rows(scenario_id, variant_id, allocation_mode, tie_mode, targets)
rows = table();
for k = 1:height(targets)
    row = table(string(scenario_id), string(variant_id), string(allocation_mode), ...
        string(tie_mode), NaN, string(targets.interface_name(k)), NaN, ...
        targets.target_flow_mw(k), targets.target_limit_mw(k), NaN, NaN, ...
        "not_scored", NaN, 'VariableNames', {'scenario_id','variant_id', ...
        'allocation_mode','tie_mode','classic_objective_term','interface_name', ...
        'lite_flow_mw','target_flow_mw','target_limit_mw','residual_mw', ...
        'scale_mw','scale_source','objective_term'});
    rows = append_table(rows, row);
end
end

function summary = summarize_variants(results)
variants = unique(results.variant_id, 'stable');
summary = table();
baseline = results(results.variant_id == "S4_GSK__current", :);
baseline_fixed = sum(baseline.fixed_scale_interface_objective, 'omitnan');
for k = 1:numel(variants)
    rows = results(results.variant_id == variants(k), :);
    fixed = sum(rows.fixed_scale_interface_objective, 'omitnan');
    row = table(variants(k), rows.allocation_mode(1), rows.tie_mode(1), ...
        height(rows), sum(rows.pf_success == 1), ...
        sum(rows.classic_interface_objective, 'omitnan'), fixed, ...
        100 * (baseline_fixed - fixed) / baseline_fixed, ...
        mean(rows.max_abs_interface_residual_mw, 'omitnan'), ...
        max(rows.max_abs_interface_residual_mw, [], 'omitnan'), ...
        max(rows.low_voltage_violation_count + rows.high_voltage_violation_count, [], 'omitnan'), ...
        max(rows.branch_overload_count, [], 'omitnan'), ...
        max(rows.max_branch_overload_mva, [], 'omitnan'), ...
        max(rows.reference_p_violation_mw, [], 'omitnan'), ...
        mean(rows.total_abs_bus_redispatch_vs_s4_mw, 'omitnan'), ...
        'VariableNames', {'variant_id','allocation_mode','tie_mode', ...
        'scenario_count','pf_success_count','sum_classic_interface_objective', ...
        'sum_fixed_scale_interface_objective','fixed_objective_improvement_pct', ...
        'mean_max_abs_interface_residual_mw','max_abs_interface_residual_mw', ...
        'max_voltage_violation_count','max_branch_overload_count', ...
        'max_branch_overload_mva','max_reference_p_violation_mw', ...
        'mean_total_abs_bus_redispatch_vs_s4_mw'});
    summary = append_table(summary, row);
end
summary = sortrows(summary, {'pf_success_count','sum_fixed_scale_interface_objective'}, ...
    {'descend','ascend'});
end

function pg = project_unit_total(target, pmin, pmax, seed)
pmin = pmin(:); pmax = pmax(:); seed = seed(:);
if target < sum(pmin) - 1e-6 || target > sum(pmax) + 1e-6
    error('Bus target %.3f MW is outside generator limits [%.3f, %.3f].', ...
        target, sum(pmin), sum(pmax));
end
if sum(seed) <= 0, seed = pmax; end
pg = min(max(seed * target / max(sum(seed), eps), pmin), pmax);
for iter = 1:100
    delta = target - sum(pg);
    if abs(delta) < 1e-8, break; end
    if delta > 0, room = pmax - pg; else, room = pg - pmin; end
    active = room > 1e-10;
    if ~any(active), break; end
    weights = room; weights(~active) = 0; weights = weights / sum(weights);
    step = delta * weights;
    if delta > 0, step = min(step, room); else, step = max(step, -room); end
    pg = pg + step;
end
if abs(target - sum(pg)) > 1e-5, error('Could not allocate bus generation target.'); end
end

function out = append_table(out, row)
if isempty(row), return; end
if isempty(out), out = row; else, out = [out; row]; end %#ok<AGROW>
end
