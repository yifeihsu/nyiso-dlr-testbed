function out = assess_s13_phase1a_common_input_readiness(options)
%ASSESS_S13_PHASE1A_COMMON_INPUT_READINESS Audit no-fit S12/S13 inputs.
%   This audit defines the common-input contract needed by the Phase 1A
%   paired oracle comparison. It deliberately does not apply boundary
%   injections to S13, close public interface flows, fit branch parameters,
%   or claim that a full-NPCC tie-flow controller exists.
%
%   The default behavior is fail-closed without throwing: the durable input
%   and control registers are written, READY is false, and the missing
%   controls are returned as failed readiness gates. Set
%   OPTIONS.fail_on_not_ready=true only for callers that require readiness.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
workspace_dir = fileparts(case_dir);
options = defaults(options, helper_dir);
addpath(case_dir); addpath(helper_dir);
addpath(fullfile(workspace_dir, 'PERFORM', ...
    'On Peak 2019 v23_Perform_NY', 'On Peak 2019 v23'));
define_constants;

scenario = readtable(fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
load_target = readtable(fullfile(helper_dir, 'ny_zonal_load_targets.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
generation_prior = readtable(fullfile(helper_dir, ...
    's12_zonal_generation_priors.csv'), 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');

source = loadcase('nyiso_On_Peak_v23_shunts_as_z_load');
s13 = loadcase('npcc_ny_lite_s13_npcc_augmented_2019');
s13 = attach_nyiso_zone_metadata(s13);
s7 = loadcase('npcc_ny_lite_s7_seven_interface_perform_direct_candidate');
s12_data = load(fullfile(helper_dir, 's12_case.mat'), 's12');
s12 = s12_data.s12;

letters = string(('A':'K')');
[reference_pd, reference_qd, reference_q_over_p] = ...
    oracle_zonal_load_reference(s12, letters);
[s12_capacity, s12_generator_count, s12_zone_present] = ...
    s12_zonal_capacity(s12, letters);
[s13_capacity, s13_generator_count, s13_zone_present] = ...
    s13_zonal_capacity(s13, letters);

tie_audit = audit_s13_regional_ties(s13);
external_map = build_external_schedule_map(scenario, s12, tie_audit, ...
    helper_dir, options.tolerance_mw);
common_input = build_common_input_spec(scenario, load_target, ...
    generation_prior, external_map, letters, reference_pd, reference_qd, ...
    reference_q_over_p, s12_capacity, s12_generator_count, ...
    s12_zone_present, s13_capacity, s13_generator_count, ...
    s13_zone_present, options.tolerance_mw);

parent_rxb_frozen = size(s13.branch, 1) >= size(s7.branch, 1) && ...
    isequaln(s13.branch(1:size(s7.branch, 1), [BR_R BR_X BR_B]), ...
    s7.branch(:, [BR_R BR_X BR_B]));
no_s12_boundary_injections = size(s13.gen, 1) == size(s7.gen, 1) && ...
    isequaln(s13.gen, s7.gen);
added_rxb_exact = added_physical_rxb_exact(s13, source, options.tolerance_pu);

all_scenarios = numel(unique(scenario.scenario_id)) == 6 && ...
    height(scenario) == 6;
complete_zonal_rows = height(common_input) == 66 && ...
    all(isfinite(common_input.target_load_mw)) && ...
    all(isfinite(common_input.target_reactive_load_mvar)) && ...
    all(isfinite(common_input.target_generation_mw));
s12_representable = all(common_input.s12_load_representable) && ...
    all(common_input.s12_generation_representable);
s13_load_representable = all(common_input.s13_load_representable);
s13_generation_representable = ...
    all(common_input.s13_generation_representable);
nine_groups_mapped = numel(unique(external_map.s12_p32_group)) == 9 && ...
    all(external_map.s12_group_row_count > 0) && ...
    all(external_map.regional_map_defined);
regional_targets_complete = all(isfinite(external_map.group_target_mw)) && ...
    all(isfinite(external_map.regional_target_mw));

% No validated full-NPCC controller or common loss/voltage-control policy is
% present in Phase 1A. These are scientific prerequisites, not options that
% a caller may override with a flag.
validated_tie_controller = false;
common_loss_balance_policy = false;
common_voltage_control_policy = false;
no_interface_closure = true;
no_residual_fit = parent_rxb_frozen && added_rxb_exact;

gates = table();
gates = append_gate(gates, "scale_convention_explicit", true, ...
    "Six public 2019 patterns are similarity-scaled to the fixed NPCC-NY load magnitude.");
gates = append_gate(gates, "six_public_scenarios_complete", all_scenarios, ...
    "Expected six scenario rows and scenario-specific gamma values.");
gates = append_gate(gates, "common_zonal_p_q_generation_defined", ...
    complete_zonal_rows, ...
    "A-K active load, PERFORM Q/P reactive load, and fuel-mix generation priors are explicit.");
gates = append_gate(gates, "s12_zonal_inputs_representable", ...
    s12_representable, "S12 has the required zone load components and generation capacity.");
gates = append_gate(gates, "s13_zonal_loads_representable", ...
    s13_load_representable, "Every A-K zone has an S13 load-allocation location.");
gates = append_gate(gates, "s13_zonal_generation_representable", ...
    s13_generation_representable, ...
    "Nonzero source-backed zonal priors require S13 generation and sufficient PMAX.");
gates = append_gate(gates, "s12_nine_groups_to_four_regions_mapped", ...
    nine_groups_mapped, ...
    "Nine S12 P-32 groups are aggregated to HQ, ONTARIO, ISONE, and PJM.");
gates = append_gate(gates, "regional_public_targets_complete", ...
    regional_targets_complete, ...
    "Every group and regional aggregate has a finite scaled P-32 target.");
gates = append_gate(gates, "s13_regional_tie_rows_and_signs_verified", ...
    tie_audit.all_verified, ...
    "All ten full-NPCC NY boundary rows are assigned once with NY-import metering signs.");
gates = append_gate(gates, "unrepresentable_individual_controls_flagged", ...
    all(external_map.individual_control_status ~= "unreviewed"), ...
    "NPX/HTP/Neptune/VFT path controls are explicitly regional-only in S13.");
gates = append_gate(gates, "validated_full_npcc_tie_controller", ...
    validated_tie_controller, ...
    "Pending bounded AC tie-flow control with corresponding external-area redispatch.");
gates = append_gate(gates, "common_ac_loss_balance_policy", ...
    common_loss_balance_policy, ...
    "Pending a common bounded loss-balancing participation rule.");
gates = append_gate(gates, "common_voltage_control_policy", ...
    common_voltage_control_policy, ...
    "S12 source controls and S13 inherited controls are not yet a common representable set.");
gates = append_gate(gates, "no_s12_boundary_injections_added_to_s13", ...
    no_s12_boundary_injections, ...
    "S13 retains exactly the S7 generator rows; S12 boundary records remain oracle-only.");
gates = append_gate(gates, "no_interface_flow_closure", ...
    no_interface_closure, ...
    "This audit reads public interfaces only for schedules, never for internal-flow fitting.");
gates = append_gate(gates, "parent_branch_rxb_frozen", ...
    parent_rxb_frozen, "Every inherited S7 branch retains identical R/X/B.");
gates = append_gate(gates, "added_physical_branch_rxb_source_exact", ...
    added_rxb_exact, "Every Phase 1A physical branch retains source PERFORM R/X/B.");
gates = append_gate(gates, "no_residual_rxb_fit", no_residual_fit, ...
    "No inherited or added physical branch admittance is fitted by this audit.");

controls = build_control_assumption_register(validated_tie_controller, ...
    common_loss_balance_policy, common_voltage_control_policy, ...
    parent_rxb_frozen, added_rxb_exact);

ready = all(gates.actual(gates.required));
if ready
    readiness_status = "ready_for_no_fit_paired_pf";
else
    readiness_status = "not_ready_fail_closed";
end
blockers = gates.gate_id(gates.required & ~gates.actual);

common_path = fullfile(options.output_dir, ...
    's13_phase1a_common_input_spec.csv');
external_path = fullfile(options.output_dir, ...
    's13_phase1a_external_schedule_map.csv');
control_path = fullfile(options.output_dir, ...
    's13_phase1a_control_assumption_register.csv');
if options.write_outputs
    if ~isfolder(options.output_dir)
        error('assess_s13_phase1a_common_input_readiness:OutputDirectory', ...
            'Output directory does not exist: %s', options.output_dir);
    end
    ny_lite_writetable_lf(common_input, common_path);
    ny_lite_writetable_lf(external_map, external_path);
    ny_lite_writetable_lf(controls, control_path);
end

if options.verbose
    fprintf('S13.1 common-input readiness: %s (%d/%d gates pass)\n', ...
        readiness_status, sum(gates.actual), height(gates));
    for k = find(gates.required & ~gates.actual)'
        fprintf('  fail-closed: %s -- %s\n', gates.gate_id(k), gates.evidence(k));
    end
end

out = struct('ready', logical(ready), ...
    'readiness_status', readiness_status, ...
    'promotion_eligible', false, ...
    'same_snapshot_status', "pending_common_input_controls", ...
    'validated_full_npcc_tie_controller', validated_tie_controller, ...
    'gates', gates, 'blockers', blockers, ...
    'common_input_spec', common_input, ...
    'external_schedule_map', external_map, ...
    'control_assumption_register', controls, ...
    'tie_audit', tie_audit, ...
    'outputs_written', logical(options.write_outputs), ...
    'common_input_file', string(common_path), ...
    'external_schedule_file', string(external_path), ...
    'control_assumption_file', string(control_path));

if options.fail_on_not_ready && ~ready
    error('assess_s13_phase1a_common_input_readiness:NotReady', ...
        'S13.1 common input is not ready: %s.', strjoin(blockers, ', '));
end
end

function options = defaults(options, helper_dir)
if ~isfield(options, 'write_outputs'), options.write_outputs = true; end
if ~isfield(options, 'output_dir'), options.output_dir = helper_dir; end
if ~isfield(options, 'verbose'), options.verbose = true; end
if ~isfield(options, 'fail_on_not_ready'), options.fail_on_not_ready = false; end
if ~isfield(options, 'tolerance_mw'), options.tolerance_mw = 1e-6; end
if ~isfield(options, 'tolerance_pu'), options.tolerance_pu = 1e-12; end
options.write_outputs = logical(options.write_outputs);
options.verbose = logical(options.verbose);
options.fail_on_not_ready = logical(options.fail_on_not_ready);
end

function [pd, qd, ratio] = oracle_zonal_load_reference(s12, letters)
areas = s12.userdata.s12_zone_area_codes(:);
area_letters = string(s12.userdata.s12_zone_letters(:));
PB = s12.userdata.s12_zone_base_load_p;
QB = s12.userdata.s12_zone_base_load_q;
pd = zeros(numel(letters), 1);
qd = zeros(numel(letters), 1);
ratio = zeros(numel(letters), 1);
for z = 1:numel(letters)
    ai = find(area_letters == letters(z), 1);
    if isempty(ai), continue; end
    assert(ai <= numel(areas), 'S12 zone-load metadata is inconsistent.');
    pd(z) = sum(PB(:, ai));
    qd(z) = sum(QB(:, ai));
    if pd(z) > 0, ratio(z) = qd(z) / pd(z); end
end
end

function [capacity, count, present] = s12_zonal_capacity(s12, letters)
define_constants;
areas = s12.userdata.s12_zone_area_codes(:);
area_letters = string(s12.userdata.s12_zone_letters(:));
gen_area = s12.bus(s12.gen(:, GEN_BUS), BUS_AREA);
is_boundary = false(size(s12.gen, 1), 1);
is_boundary(s12.userdata.s12_external_groups.gen_index) = true;
is_reference = string(s12.genfuel(:)) == "reference";
eligible = ~is_boundary & ~is_reference & s12.gen(:, PMAX) > 0;
capacity = zeros(numel(letters), 1);
count = zeros(numel(letters), 1);
present = false(numel(letters), 1);
for z = 1:numel(letters)
    ai = find(area_letters == letters(z), 1);
    if isempty(ai), continue; end
    present(z) = any(s12.bus(:, BUS_AREA) == areas(ai));
    idx = eligible & gen_area == areas(ai);
    capacity(z) = sum(s12.gen(idx, PMAX));
    count(z) = sum(idx);
end
end

function [capacity, count, present] = s13_zonal_capacity(s13, letters)
define_constants;
[found, bi] = ismember(s13.gen(:, GEN_BUS), s13.bus(:, BUS_I));
gen_zone = strings(size(s13.gen, 1), 1);
gen_zone(found) = string(s13.userdata.nyiso_physical_zone(bi(found)));
bus_zone = string(s13.userdata.nyiso_physical_zone(:));
capacity = zeros(numel(letters), 1);
count = zeros(numel(letters), 1);
present = false(numel(letters), 1);
for z = 1:numel(letters)
    present(z) = any(bus_zone == letters(z));
    idx = s13.gen(:, GEN_STATUS) > 0 & gen_zone == letters(z);
    capacity(z) = sum(s13.gen(idx, PMAX));
    count(z) = sum(idx);
end
end

function spec = build_common_input_spec(scenario, load_target, gen_prior, ...
        external_map, letters, reference_pd, reference_qd, ratio, s12_capacity, ...
        s12_count, s12_present, s13_capacity, s13_count, s13_present, tol)
n = height(scenario) * numel(letters);
scenario_id = strings(n, 1); timestamp = strings(n, 1);
zone = strings(n, 1); scale_convention = strings(n, 1);
scale_factor_gamma = zeros(n, 1); target_ny_load_mw = zeros(n, 1);
target_load_mw = zeros(n, 1); reference_snapshot_pd_mw = zeros(n, 1);
reference_snapshot_qd_mvar = zeros(n, 1); reference_q_over_p = zeros(n, 1);
reactive_ratio_source = repmat("S12_PERFORM_retention_zone_base_P_Q", n, 1);
target_reactive_load_mvar = zeros(n, 1);
target_generation_mw = zeros(n, 1);
target_generation_q_mvar = nan(n, 1);
generation_prior_source = repmat("NYISO_fuel_mix_allocated_by_source_capability", n, 1);
reactive_generation_policy = repmat("voltage_controlled_not_observed_dispatch", n, 1);
s12_load_representable = false(n, 1);
s13_load_representable = false(n, 1);
s12_generation_representable = false(n, 1);
s13_generation_representable = false(n, 1);
s12_generation_capacity_mw = zeros(n, 1);
s13_generation_capacity_mw = zeros(n, 1);
s12_generator_count = zeros(n, 1); s13_generator_count = zeros(n, 1);
scenario_total_internal_generation_mw = zeros(n, 1);
scenario_total_external_import_mw = zeros(n, 1);
pre_loss_balance_surplus_mw = zeros(n, 1);
aggregate_requirement_status = strings(n, 1); blocker = strings(n, 1);

r = 0;
for s = 1:height(scenario)
    sid = scenario.scenario_id(s);
    lrows = load_target(load_target.scenario_id == sid, :);
    grows = gen_prior(gen_prior.scenario_id == sid, :);
    erows = external_map(external_map.scenario_id == sid, :);
    total_generation = sum(grows.prior_mw_scaled);
    total_external = sum(erows.group_target_mw);
    total_load = sum(lrows.target_load_mw);
    for z = 1:numel(letters)
        r = r + 1;
        li = find(upper(lrows.nyiso_zone_letter) == letters(z), 1);
        gi = find(upper(grows.zone) == letters(z), 1);
        scenario_id(r) = sid;
        timestamp(r) = scenario.timestamp(s);
        zone(r) = letters(z);
        scale_convention(r) = "similarity_scaled_2019_pattern_not_raw_MW";
        scale_factor_gamma(r) = scenario.scale_factor_gamma(s);
        target_ny_load_mw(r) = scenario.npcc_ny_total_load_mw(s);
        reference_snapshot_pd_mw(r) = reference_pd(z);
        reference_snapshot_qd_mvar(r) = reference_qd(z);
        reference_q_over_p(r) = ratio(z);
        if isempty(li)
            target_load_mw(r) = NaN;
            target_reactive_load_mvar(r) = NaN;
        else
            target_load_mw(r) = lrows.target_load_mw(li);
            target_reactive_load_mvar(r) = target_load_mw(r) * ratio(z);
        end
        if isempty(gi), target_generation_mw(r) = NaN;
        else, target_generation_mw(r) = grows.prior_mw_scaled(gi); end
        s12_load_representable(r) = s12_present(z);
        s13_load_representable(r) = s13_present(z);
        s12_generation_capacity_mw(r) = s12_capacity(z);
        s13_generation_capacity_mw(r) = s13_capacity(z);
        s12_generator_count(r) = s12_count(z);
        s13_generator_count(r) = s13_count(z);
        s12_generation_representable(r) = isfinite(target_generation_mw(r)) && ...
            target_generation_mw(r) <= s12_capacity(z) + tol && ...
            (target_generation_mw(r) <= tol || s12_count(z) > 0);
        s13_generation_representable(r) = isfinite(target_generation_mw(r)) && ...
            target_generation_mw(r) <= s13_capacity(z) + tol && ...
            (target_generation_mw(r) <= tol || s13_count(z) > 0);
        scenario_total_internal_generation_mw(r) = total_generation;
        scenario_total_external_import_mw(r) = total_external;
        pre_loss_balance_surplus_mw(r) = total_generation + total_external - total_load;
        ok = s12_load_representable(r) && s13_load_representable(r) && ...
            s12_generation_representable(r) && s13_generation_representable(r);
        if ok
            aggregate_requirement_status(r) = "representable_before_controls";
            blocker(r) = "";
        elseif ~s13_generation_representable(r) && letters(z) == "H"
            aggregate_requirement_status(r) = "not_common_fail_closed";
            blocker(r) = "nonzero_Zone_H_prior_has_no_S13_generator";
        elseif ~s13_generation_representable(r)
            aggregate_requirement_status(r) = "not_common_fail_closed";
            blocker(r) = "S13_zonal_generation_capacity_or_mapping_missing";
        elseif ~s12_generation_representable(r)
            aggregate_requirement_status(r) = "not_common_fail_closed";
            blocker(r) = "S12_zonal_generation_capacity_or_mapping_missing";
        else
            aggregate_requirement_status(r) = "not_common_fail_closed";
            blocker(r) = "zonal_load_location_missing";
        end
    end
end

spec = table(scenario_id, timestamp, scale_convention, scale_factor_gamma, ...
    target_ny_load_mw, zone, target_load_mw, reference_snapshot_pd_mw, ...
    reference_snapshot_qd_mvar, reference_q_over_p, reactive_ratio_source, ...
    target_reactive_load_mvar, target_generation_mw, ...
    target_generation_q_mvar, generation_prior_source, ...
    reactive_generation_policy, s12_load_representable, ...
    s13_load_representable, s12_generation_representable, ...
    s13_generation_representable, s12_generation_capacity_mw, ...
    s13_generation_capacity_mw, s12_generator_count, s13_generator_count, ...
    scenario_total_internal_generation_mw, ...
    scenario_total_external_import_mw, pre_loss_balance_surplus_mw, ...
    aggregate_requirement_status, blocker);
end

function audit = audit_s13_regional_ties(s13)
define_constants;
regions = ["HQ"; "ONTARIO"; "ISONE"; "PJM"];
rows = {221, [63 64], [25 32], [72 80 83 93 99]};
expected_area = [4; 4; 1; 6];
ny = s13.userdata.nyiso_zone_id(:) > 0;
all_rows = [];
row_text = strings(numel(regions), 1);
operator_text = strings(numel(regions), 1);
endpoint_text = strings(numel(regions), 1);
area_text = strings(numel(regions), 1);
region_verified = false(numel(regions), 1);
for k = 1:numel(regions)
    br = rows{k}(:)';
    all_rows = [all_rows br]; %#ok<AGROW>
    expr = strings(numel(br), 1); endpoints = strings(numel(br), 1);
    areas = zeros(numel(br), 1); ok = true;
    for j = 1:numel(br)
        b = br(j);
        if b < 1 || b > size(s13.branch, 1)
            ok = false; continue;
        end
        fi = find(s13.bus(:, BUS_I) == s13.branch(b, F_BUS), 1);
        ti = find(s13.bus(:, BUS_I) == s13.branch(b, T_BUS), 1);
        if isempty(fi) || isempty(ti) || ~xor(ny(fi), ny(ti))
            ok = false; continue;
        end
        if ny(fi)
            expr(j) = sprintf('row%d:-PF', b);
            ext = ti;
        else
            expr(j) = sprintf('row%d:-PT', b);
            ext = fi;
        end
        areas(j) = s13.bus(ext, BUS_AREA);
        endpoints(j) = sprintf('row%d:%d-%d', b, ...
            s13.branch(b, F_BUS), s13.branch(b, T_BUS));
        ok = ok && areas(j) == expected_area(k) && ...
            s13.branch(b, BR_STATUS) > 0;
    end
    row_text(k) = strjoin(string(br), ';');
    operator_text(k) = strjoin(expr, ';');
    endpoint_text(k) = strjoin(endpoints, ';');
    area_text(k) = strjoin(string(unique(areas)), ';');
    region_verified(k) = ok;
end

boundary = [];
for b = 1:size(s13.branch, 1)
    if s13.branch(b, BR_STATUS) <= 0, continue; end
    fi = find(s13.bus(:, BUS_I) == s13.branch(b, F_BUS), 1);
    ti = find(s13.bus(:, BUS_I) == s13.branch(b, T_BUS), 1);
    if ~isempty(fi) && ~isempty(ti) && xor(ny(fi), ny(ti))
        boundary(end+1) = b; %#ok<AGROW>
    end
end
no_duplicate_assignments = numel(all_rows) == numel(unique(all_rows));
complete = no_duplicate_assignments && ...
    isequal(sort(unique(all_rows)), sort(unique(boundary)));
table_data = table(regions, row_text, operator_text, endpoint_text, ...
    area_text, expected_area, region_verified, ...
    'VariableNames', {'region','tie_branch_rows','import_operator', ...
    'branch_endpoints','external_area_codes','expected_external_area', ...
    'verified'});
audit = struct('regions', table_data, ...
    'all_boundary_branch_rows', boundary(:), ...
    'no_duplicate_regional_assignments', no_duplicate_assignments, ...
    'all_expected_rows_present_once', complete, ...
    'all_verified', complete && all(region_verified));
end

function out = build_external_schedule_map(scenario, s12, tie_audit, ...
        helper_dir, tol)
groups = ["SCH - HQ - NY"; "SCH - OH - NY"; "SCH - NE - NY"; ...
    "SCH - NPX_1385"; "SCH - NPX_CSC"; "SCH - PJ - NY"; ...
    "SCH - PJM_HTP"; "SCH - PJM_NEPTUNE"; "SCH - PJM_VFT"];
regions = ["HQ"; "ONTARIO"; "ISONE"; "ISONE"; "ISONE"; ...
    "PJM"; "PJM"; "PJM"; "PJM"];
components = groups;
components(1) = "SCH - HQ - NY;SCH - HQ_CEDARS";
direct = ismember(groups, ["SCH - NPX_1385", "SCH - NPX_CSC", ...
    "SCH - PJM_HTP", "SCH - PJM_NEPTUNE", "SCH - PJM_VFT"]);

ext = s12.userdata.s12_external_groups;
out = table();
for s = 1:height(scenario)
    sid = scenario.scenario_id(s);
    gamma = scenario.scale_factor_gamma(s);
    ts = datetime(scenario.timestamp(s), 'InputFormat', 'yyyy-MM-dd HH:mm');
    p32 = load_p32_hour(helper_dir, ts);
    group_target = nan(numel(groups), 1);
    group_found = false(numel(groups), 1);
    for g = 1:numel(groups)
        names = split(components(g), ';');
        value = 0; found = true;
        for n = 1:numel(names)
            idx = find(p32.name == names(n), 1);
            if isempty(idx)
                found = false;
            else
                value = value + p32.flow_mw(idx);
            end
        end
        group_found(g) = found;
        if found, group_target(g) = gamma * value; end
    end
    regional_target = nan(numel(groups), 1);
    for g = 1:numel(groups)
        mask = regions == regions(g);
        if all(group_found(mask)), regional_target(g) = sum(group_target(mask)); end
    end
    for g = 1:numel(groups)
        sr = ext(ext.p32_interface_name == groups(g), :);
        tr = tie_audit.regions(tie_audit.regions.region == regions(g), :);
        if direct(g)
            individual_status = "absorbed_into_regional_cut_no_individual_S13_path";
        else
            individual_status = "regional_AC_cut_only_controller_pending";
        end
        mapping_status = "regional_map_defined_controller_pending";
        if isempty(tr) || ~group_found(g) || height(sr) == 0
            mapping_status = "incomplete_fail_closed";
        end
        row = table(sid, scenario.timestamp(s), gamma, groups(g), ...
            components(g), regions(g), group_target(g), regional_target(g), ...
            height(sr), index_list(sr.gen_index), index_list(sr.source_bus), ...
            tr.tie_branch_rows, tr.import_operator, tr.branch_endpoints, ...
            tr.external_area_codes, logical(~isempty(tr)), false, ...
            individual_status, mapping_status, ...
            "S12 boundary generators remain oracle-only; S13 must use tie-flow control and external-area redispatch.", ...
            'VariableNames', {'scenario_id','timestamp','scale_factor_gamma', ...
            's12_p32_group','public_schedule_components','s13_region', ...
            'group_target_mw','regional_target_mw','s12_group_row_count', ...
            's12_gen_indices','s12_source_buses','s13_tie_branch_rows', ...
            's13_import_operator','s13_branch_endpoints', ...
            's13_external_area_codes','regional_map_defined', ...
            'validated_s13_tie_controller','individual_control_status', ...
            'mapping_status','policy_note'});
        out = append_table(out, row);
    end
end
assert(all(abs(out.group_target_mw(isfinite(out.group_target_mw))) < 1e7 + tol), ...
    'External target magnitude is implausible.');
end

function hour = load_p32_hour(helper_dir, ts)
cache = fullfile(helper_dir, 'nyiso_public_cache');
month_token = char(string(ts, 'yyyyMM'));
day_token = char(string(ts, 'yyyyMMdd'));
path = fullfile(cache, [month_token '_ExternalLimitsFlows'], ...
    [day_token 'ExternalLimitsFlows.csv']);
tbl = readtable(path, 'TextType', 'string', 'VariableNamingRule', 'preserve');
row_ts = datetime(tbl.Timestamp, 'InputFormat', 'MM/dd/yyyy HH:mm');
unique_ts = unique(row_ts);
[~, k] = min(abs(unique_ts - ts));
selected = row_ts == unique_ts(k);
hour = table(tbl.('Interface Name')(selected), tbl.('Flow (MWH)')(selected), ...
    'VariableNames', {'name','flow_mw'});
end

function text = index_list(value)
if isempty(value), text = ""; else, text = strjoin(string(value(:)'), ';'); end
end

function exact = added_physical_rxb_exact(s13, source, tol)
define_constants;
exact = false;
if ~isfield(s13, 'userdata') || ~isfield(s13.userdata, 's13'), return; end
report = s13.userdata.s13.overlay_report;
if ~isfield(report, 'branch_map'), return; end
map = report.branch_map;
if isempty(map), return; end
model_rows = double(map.model_branch_row);
source_rows = double(map.source_branch_row);
if any(model_rows < 1 | model_rows > size(s13.branch, 1)) || ...
        any(source_rows < 1 | source_rows > size(source.branch, 1))
    return;
end
delta = s13.branch(model_rows, [BR_R BR_X BR_B]) - ...
    source.branch(source_rows, [BR_R BR_X BR_B]);
exact = all(abs(delta(:)) <= tol);
end

function rows = build_control_assumption_register(tie_ready, loss_ready, ...
        voltage_ready, parent_rxb_frozen, added_rxb_exact)
rows = table();
rows = add_control(rows, "scale_convention", "operating_scale", ...
    "Scenario gamma times public 2019 patterns; fixed NPCC-NY total 10902.2197987 MW", ...
    "Same aggregate targets", "Same aggregate targets", "defined", ...
    "Similarity-scaled reconstruction, not raw 2019 MW.");
rows = add_control(rows, "active_load", "load", ...
    "Exact scaled P-58C A-K totals", "Zone-labeled retained components", ...
    "NPCC load-allocation buses", "defined", ...
    "Model-specific bus allocation is allowed only after exact zonal totals match.");
rows = add_control(rows, "reactive_load", "load", ...
    "Scaled active load times the S12/PERFORM retention-load zonal Q/P", ...
    "Ward-retained zone load components", "NPCC allocation buses", ...
    "defined", "A common aggregate Q target is required in every zone.");
rows = add_control(rows, "active_generation_prior", "generation", ...
    "Fuel-mix-derived zonal totals without interface closure", ...
    "S12 unit prior within zone", "PERFORM-derived NPCC GSK within zone", ...
    "blocked", "Fifteen scenario-zone rows are not representable: Zone H " + ...
    "has no S13 generator and selected A/B/C/E priors exceed current mapped capability.");
rows = add_control(rows, "reactive_generation", "generation", ...
    "Voltage-controlled Q within source-backed limits; not historical dispatch", ...
    "Source-retained controls", "Inherited S7 controls", "blocked", ...
    "A common representable voltage-control subset is not yet defined.");
rows = add_control(rows, "external_schedule_aggregation", "interchange", ...
    "Nine P-32 groups aggregated to HQ, ONTARIO, ISONE, and PJM", ...
    "Nine boundary-generator groups", "Ten physical NPCC tie rows", ...
    "defined", "Individual NPX/HTP/Neptune/VFT paths are regional-only in S13.");
rows = add_control(rows, "full_npcc_tie_control", "interchange", ...
    "Bounded AC tie-flow targets with external-area redispatch", ...
    "Not applicable to the boundary oracle", "Controller not implemented", ...
    pass_pending(tie_ready), "S12 boundary injections must never be copied into S13.");
rows = add_control(rows, "loss_balance", "active_balance", ...
    "Identical documented distributed participation rule", ...
    "Pending", "Pending", pass_pending(loss_ready), ...
    "Reference-generator pickup is not a common dispatch prior.");
rows = add_control(rows, "transformer_par_controls", "voltage_control", ...
    "Fixed snapshot values unless a bounded uncertainty variable is documented", ...
    "Source snapshot", "Inherited NPCC snapshot", "diagnostic_only", ...
    "PERFORM provides no usable historical automatic tap/PAR schedule.");
rows = add_control(rows, "common_voltage_control", "voltage_control", ...
    "Same source-backed assumptions where representable", ...
    "Source-retained controls", "Inherited S7 controls", ...
    pass_pending(voltage_ready), "Exact device equality is not currently available.");
rows = add_control(rows, "interface_flow_closure", "prohibited_action", ...
    "Prohibited", "Disabled", "Disabled", "pass", ...
    "Public internal-interface targets cannot inform this forward comparison.");
rows = add_control(rows, "s12_boundary_injections_on_s13", ...
    "prohibited_action", "Prohibited", "Oracle-only", "Not added", ...
    "pass", "The retained external NPCC network would otherwise be double counted.");
rows = add_control(rows, "inherited_branch_rxb", "frozen_admittance", ...
    "No residual or calibration fit", "Not applicable", "Frozen to S7", ...
    pass_pending(parent_rxb_frozen), "All inherited R/X/B must remain exact.");
rows = add_control(rows, "added_physical_branch_rxb", "frozen_admittance", ...
    "Exact source PERFORM values", "Exact retained circuits", ...
    "Exact appended circuits", pass_pending(added_rxb_exact), ...
    "No residual fitting is permitted in S13.1.");
end

function value = pass_pending(flag)
if flag, value = "pass"; else, value = "pending_fail_closed"; end
end

function out = add_control(out, id, category, common, s12, s13, status, evidence)
row = table(string(id), string(category), string(common), string(s12), ...
    string(s13), string(status), string(evidence), ...
    'VariableNames', {'assumption_id','category','required_common_policy', ...
    's12_implementation','s13_implementation','status','evidence'});
out = append_table(out, row);
end

function out = append_gate(out, id, actual, evidence)
if actual, status = "pass"; else, status = "fail_closed"; end
row = table(string(id), true, logical(actual), status, string(evidence), ...
    'VariableNames', {'gate_id','required','actual','status','evidence'});
out = append_table(out, row);
end

function out = append_table(out, row)
if isempty(out), out = row; else, out = [out; row]; end
end
