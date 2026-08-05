function [mpc, report] = apply_perform_controls_to_operating_case(mpc, options)
%APPLY_PERFORM_CONTROLS_TO_OPERATING_CASE Apply source-backed S10a controls.
%   [MPC, REPORT] = APPLY_PERFORM_CONTROLS_TO_OPERATING_CASE(MPC, OPTIONS)
%   replaces only the legacy internal generator rows in an already prepared
%   NY operating case. Loads, shunts, branches, and public external active-
%   power schedules are preserved. PERFORM capabilities are not similarity
%   scaled.
%
%   Public external generators added by APPLY_NYISO_EXTERNAL_INTERFACE_INJECTIONS
%   remain authoritative for interchange P. Map-derived import records are
%   retained as provenance only, except for the Marcy RF source-reference
%   record, which is represented as a zero-P, fixed/tightly-bounded-Q record.

if nargin < 1 || isempty(mpc)
    error('apply_perform_controls_to_operating_case:MissingCase', ...
        'An already-loaded operating case is required.');
end
if nargin < 2, options = struct(); end

helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
options = defaults(options, helper_dir);
define_constants;

mpc = attach_nyiso_zone_metadata(mpc);
control_map = read_control_map(options);
validate_control_map(control_map, options);
control_map = apply_source_operating_priors(control_map, options);

input_state = struct();
input_state.pd = mpc.bus(:, PD);
input_state.qd = mpc.bus(:, QD);
input_state.gs = mpc.bus(:, GS);
input_state.bs = mpc.bus(:, BS);
input_state.branch = mpc.branch;
input_state.bus_type = mpc.bus(:, BUS_TYPE);
input_state.bus_vm = mpc.bus(:, VM);
input_state.gen = mpc.gen;
input_state.gencost = field_or_empty(mpc, 'gencost');
input_state.genfuel = field_or_empty(mpc, 'genfuel');
input_state.gentype = field_or_empty(mpc, 'gentype');

[external_input_idx, external_metadata] = external_generator_indices(mpc, options);
fixed_source_boundary = options.boundary_p_policy == ...
    "fixed_source_when_no_public_external";
if fixed_source_boundary && ~isempty(external_input_idx)
    error('apply_perform_controls_to_operating_case:BoundaryScheduleConflict', ...
        ['Benchmark fixed-source boundary mode cannot be used when public ' ...
        'external generator rows are present.']);
end
internal_input_idx = setdiff((1:size(mpc.gen, 1))', external_input_idx, 'stable');
external_gen = mpc.gen(external_input_idx, :);
external_cost = aligned_cost_rows(input_state.gencost, size(input_state.gen, 1), ...
    external_input_idx);
external_fuel = aligned_text_rows(input_state.genfuel, size(input_state.gen, 1), ...
    external_input_idx, 'public_external_boundary');
external_type = aligned_text_rows(input_state.gentype, size(input_state.gen, 1), ...
    external_input_idx, 'EX');

[zone_ids, zone_names] = bus_zone_lookup(mpc);
old_zone_pg = zonal_internal_pg(input_state.gen, internal_input_idx, ...
    zone_ids, zone_names);

[groups, map_diagnostics] = aggregate_control_groups(control_map, mpc, options);
[groups, zone_dispatch] = allocate_zonal_active_power(groups, old_zone_pg, options);

ncol = max(21, size(mpc.gen, 2));
internal_gen = zeros(0, ncol);
internal_fuel = cell(0, 1);
internal_type = cell(0, 1);
report_rows = repmat(generator_report_template(), 0, 1);

for k = 1:numel(groups)
    group = groups(k);
    if group.is_boundary && fixed_source_boundary
        qtarget = group.source_qg;
        qtol = options.reference_boundary_q_tolerance_mvar;
        role = "benchmark_boundary_fixed_pq";
        action = "Benchmark-only fixed source P/Q boundary; enabled only " + ...
            "because no public external schedules are present.";
        if group.is_source_reference
            role = "benchmark_reference_boundary_fixed_pq";
        end
        [internal_gen, internal_fuel, internal_type, report_rows] = ...
            append_internal_generator(internal_gen, internal_fuel, internal_type, ...
            report_rows, ncol, mpc.baseMVA, group, group.device_bus, ...
            group.source_pg, qtarget, group.source_pg, group.source_pg, ...
            qtarget-qtol, qtarget+qtol, group.vg, role, ...
            group.reduced_type, true, false, false, action);
        continue;
    elseif group.is_boundary && ~group.is_source_reference
        row = group_report_row(group, NaN, "boundary_provenance_only", ...
            0, 0, 0, 0, 0, 0, group.vg, false, false, false, ...
            "Map-derived boundary P omitted; public scenario schedule is authoritative.");
        report_rows(end+1, 1) = row; %#ok<AGROW>
        continue;
    end

    if group.is_source_reference
        qtarget = group.source_qg;
        qtol = options.reference_boundary_q_tolerance_mvar;
        [internal_gen, internal_fuel, internal_type, report_rows] = ...
            append_internal_generator(internal_gen, internal_fuel, internal_type, ...
            report_rows, ncol, mpc.baseMVA, group, group.device_bus, ...
            0, qtarget, 0, 0, qtarget-qtol, qtarget+qtol, group.vg, ...
            "reference_boundary_fixed_q_provenance", ...
            "reference_boundary_equivalent", true, false, false, ...
            "Marcy RF retained with zero P and narrow/fixed Q; not an interchange schedule.");
        continue;
    end

    qmin = group.qmin;
    qmax = group.qmax;
    qg = min(max(group.source_qg, qmin), qmax);
    q_projected = abs(qg - group.source_qg) > options.numeric_tolerance;
    fixed_q = ismember(group.pilot_bus, options.provisional_fixed_q_bus_ids);
    if fixed_q
        qmin = qg;
        qmax = qg;
    end

    if group.is_native_active && group.remote_regulation
        [internal_gen, internal_fuel, internal_type, report_rows] = ...
            append_internal_generator(internal_gen, internal_fuel, internal_type, ...
            report_rows, ncol, mpc.baseMVA, group, group.device_bus, ...
            group.pg, 0, group.pmin, group.pmax, 0, 0, group.vg, ...
            "remote_p_injection", group.reduced_type + "_p_injection", ...
            false, group.p_projected, false, ...
            "Active injection retained at mapped device bus.");
        [internal_gen, internal_fuel, internal_type, report_rows] = ...
            append_internal_generator(internal_gen, internal_fuel, internal_type, ...
            report_rows, ncol, mpc.baseMVA, group, group.pilot_bus, ...
            0, qg, 0, 0, qmin, qmax, group.vg, ...
            "remote_q_control", group.reduced_type + "_remote_q_control", ...
            fixed_q, false, q_projected, ...
            "Reactive control retained at mapped pilot bus.");
    elseif group.is_native_active
        [internal_gen, internal_fuel, internal_type, report_rows] = ...
            append_internal_generator(internal_gen, internal_fuel, internal_type, ...
            report_rows, ncol, mpc.baseMVA, group, group.device_bus, ...
            group.pg, qg, group.pmin, group.pmax, qmin, qmax, group.vg, ...
            "combined_pq_control", group.reduced_type, fixed_q, ...
            group.p_projected, q_projected, ...
            "Scenario zonal P preserved within source-backed group bounds.");
    elseif group.is_q_only
        [internal_gen, internal_fuel, internal_type, report_rows] = ...
            append_internal_generator(internal_gen, internal_fuel, internal_type, ...
            report_rows, ncol, mpc.baseMVA, group, group.pilot_bus, ...
            0, qg, 0, 0, qmin, qmax, group.vg, ...
            "reactive_only_q_control", group.reduced_type, fixed_q, ...
            false, q_projected, ...
            "Reactive-only source record retained separately from native generation.");
    end
end

% The S11 operating policy deliberately enables only the seven audited
% source-backed candidates. Inherited S7 PV labels are provenance, not an
% authorization to create additional regulating locations. One enabled
% candidate is selected as the operational MATPOWER reference.
inherited_pv = mpc.bus(input_state.bus_type == PV, BUS_I);
inherited_ref = mpc.bus(input_state.bus_type == REF, BUS_I);
if any(ismember(inherited_ref, options.provisional_fixed_q_bus_ids))
    error('apply_perform_controls_to_operating_case:ProvisionalReference', ...
        'An inherited reference bus is in the provisional fixed-Q list.');
end
if numel(inherited_ref) ~= 1
    error('apply_perform_controls_to_operating_case:ReferenceCount', ...
        'Expected exactly one inherited operating reference bus, found %d.', ...
        numel(inherited_ref));
end
regulating_buses = unique(internal_gen( ...
    internal_gen(:, GEN_STATUS)>0 & ...
    internal_gen(:, QMAX)-internal_gen(:, QMIN)>options.numeric_tolerance, ...
    GEN_BUS), 'stable');
promoted_pv = intersect(options.pv_candidate_bus_ids(:), ...
    regulating_buses, 'stable');
enabled_pv = promoted_pv(:);
enabled_pv = setdiff(enabled_pv, options.provisional_fixed_q_bus_ids(:), 'stable');
operational_ref = select_operational_reference( ...
    internal_gen, inherited_ref, enabled_pv, ...
    options.numeric_tolerance);
mpc.bus(:, BUS_TYPE) = PQ;
mpc = set_bus_types(mpc, enabled_pv, PV);
mpc = set_bus_types(mpc, options.provisional_fixed_q_bus_ids, PQ);
mpc = set_bus_types(mpc, operational_ref, REF);

% A regulating public external row is immutable. Where it shares a bus with
% internal controls, use its VG as the common setpoint and change only the
% internal rows. Otherwise use physical internal Q range as the weight.
[internal_gen, report_rows, common_vg_report, mpc] = harmonize_internal_vg( ...
    internal_gen, external_gen, external_input_idx, report_rows, mpc, options);

% Mark the actual inherited MATPOWER reference control separately from the
% source-reference provenance row.
for r = 1:numel(report_rows)
    gi = report_rows(r).reduced_gen_index;
    if isfinite(gi) && gi <= size(internal_gen, 1) && ...
            ismember(internal_gen(gi, GEN_BUS), operational_ref)
        report_rows(r).is_operational_reference = true;
        report_rows(r).is_reference_balance = true;
    end
end

% Rebuild aligned generator-side arrays. Public external numeric rows and
% their costs are copied without modification and in their original order.
external_gen = pad_matrix(external_gen, ncol);
mpc.gen = [internal_gen; external_gen];
new_external_idx = (size(internal_gen, 1) + (1:size(external_gen, 1)))';

cost_width = max(7, size(input_state.gencost, 2));
internal_cost = default_cost_rows(size(internal_gen, 1), cost_width);
if isempty(external_cost)
    external_cost = default_cost_rows(size(external_gen, 1), cost_width);
else
    external_cost = pad_matrix(external_cost, cost_width);
end
mpc.gencost = [internal_cost; external_cost];
mpc.genfuel = [internal_fuel; external_fuel];
mpc.gentype = [internal_type; external_type];

% Add public external rows to the generator report after final indices are known.
for k = 1:numel(new_external_idx)
    gi = new_external_idx(k);
    old_gi = external_input_idx(k);
    bus_id = mpc.gen(gi, GEN_BUS);
    group = external_report_group(bus_id, old_gi, external_metadata, k, ...
        zone_for_bus(bus_id, zone_ids, zone_names));
    qfixed = abs(mpc.gen(gi, QMAX) - mpc.gen(gi, QMIN)) <= ...
        options.numeric_tolerance;
    row = group_report_row(group, gi, "public_external_schedule_preserved", ...
        mpc.gen(gi, PG), mpc.gen(gi, QG), mpc.gen(gi, PMIN), ...
        mpc.gen(gi, PMAX), mpc.gen(gi, QMIN), mpc.gen(gi, QMAX), ...
        mpc.gen(gi, VG), qfixed, false, false, ...
        "Public external generator copied exactly from input operating case.");
    row.input_gen_index = old_gi;
    row.is_external_boundary_equivalent = true;
    report_rows(end+1, 1) = row; %#ok<AGROW>
end

generator_report = struct2table(report_rows);
active_dispatch_gen_idx = generator_report.reduced_gen_index( ...
    isfinite(generator_report.reduced_gen_index) & ...
    generator_report.is_native_active_control & ...
    ismember(generator_report.injection_role, ...
    ["combined_pq_control", "remote_p_injection"]));

% Refresh public external metadata after internal row replacement.
if ~isempty(external_metadata)
    if istable(external_metadata)
        external_metadata.added_gen_index = new_external_idx;
    elseif isstruct(external_metadata) && isfield(external_metadata, 'added_gen_index')
        external_metadata.added_gen_index = new_external_idx;
    end
    if ~isfield(mpc, 'userdata'), mpc.userdata = struct(); end
    if ~isfield(mpc.userdata, 'ny_only_equivalent')
        mpc.userdata.ny_only_equivalent = struct();
    end
    mpc.userdata.ny_only_equivalent.external_equivalent_generators = ...
        external_metadata;
end

alignment = struct( ...
    'gencost_aligned', size(mpc.gencost, 1) == size(mpc.gen, 1), ...
    'genfuel_aligned', numel(mpc.genfuel) == size(mpc.gen, 1), ...
    'gentype_aligned', numel(mpc.gentype) == size(mpc.gen, 1));
invariance = struct( ...
    'pd_unchanged', isequaln(mpc.bus(:, PD), input_state.pd), ...
    'qd_unchanged', isequaln(mpc.bus(:, QD), input_state.qd), ...
    'gs_unchanged', isequaln(mpc.bus(:, GS), input_state.gs), ...
    'bs_unchanged', isequaln(mpc.bus(:, BS), input_state.bs), ...
    'branch_unchanged', isequaln(mpc.branch, input_state.branch), ...
    'external_gen_rows_unchanged', ...
        isequaln(mpc.gen(new_external_idx, :), pad_matrix(external_gen, ncol)), ...
    'external_pg_unchanged', ...
        isequaln(mpc.gen(new_external_idx, PG), input_state.gen(external_input_idx, PG)), ...
    'external_p_bounds_unchanged', ...
        isequaln(mpc.gen(new_external_idx, [PMIN PMAX]), ...
        input_state.gen(external_input_idx, [PMIN PMAX])));
invariance.all_pass = all(structfun(@(x) logical(x), invariance));
alignment.all_pass = all(structfun(@(x) logical(x), alignment));

placeholder_counts = struct( ...
    'legacy_internal_placeholder_row_count', ...
        nnz(generic_placeholder_pair(input_state.gen(internal_input_idx, QMIN), ...
        input_state.gen(internal_input_idx, QMAX), options)), ...
    'map_internal_placeholder_row_count', map_diagnostics.internal_placeholder_count, ...
    'map_boundary_placeholder_row_count', map_diagnostics.boundary_placeholder_count, ...
    'map_qs_broad_range_preserved_count', map_diagnostics.qs_broad_preserved_count, ...
    'provisional_fixed_q_group_count', nnz(generator_report.q_limits_fixed & ...
        ismember(generator_report.retained_pilot_bus, ...
        options.provisional_fixed_q_bus_ids)));

controls = struct();
controls.status = 'source_backed_operating_controls_applied';
controls.control_map_file = options.control_map_file;
controls.control_map_row_count = height(control_map);
controls.effective_online_source_record_count = ...
    nnz(control_map.snapshot_effective_status > 0);
controls.reduced_control_group_count = numel(groups);
controls.generator_report = generator_report;
controls.external_gen_idx = new_external_idx;
controls.active_dispatch_gen_idx = active_dispatch_gen_idx;
controls.inherited_pv_bus_ids = inherited_pv;
controls.retained_source_backed_inherited_pv_bus_ids = zeros(0, 1);
controls.inherited_ref_bus_ids = inherited_ref;
controls.selected_operational_ref_bus_id = operational_ref;
controls.pv_candidate_bus_ids = options.pv_candidate_bus_ids(:);
controls.provisional_fixed_q_bus_ids = options.provisional_fixed_q_bus_ids(:);
controls.enabled_pv_bus_ids = mpc.bus(mpc.bus(:, BUS_TYPE) == PV, BUS_I);
controls.operational_ref_bus_ids = mpc.bus(mpc.bus(:, BUS_TYPE) == REF, BUS_I);
controls.zone_dispatch = zone_dispatch;
controls.excluded_placeholder_counts = placeholder_counts;
controls.common_vg_report = common_vg_report;
controls.invariance = invariance;
controls.alignment = alignment;
controls.boundary_policy = ['Public scenario external P schedules are authoritative; ' ...
    'PERFORM import rows are provenance-only; Marcy RF is zero-P fixed/tight-Q provenance.'];
controls.boundary_p_policy = options.boundary_p_policy;
controls.internal_pg_policy = options.internal_pg_policy;
if isempty(options.source_operating_case)
    controls.source_prior_mode = 'control_map_snapshot_fields';
else
    controls.source_prior_mode = 'supplied_source_operating_case';
end

if ~isfield(mpc, 'userdata'), mpc.userdata = struct(); end
if ~isfield(mpc.userdata, 's11'), mpc.userdata.s11 = struct(); end
mpc.userdata.s11.controls = controls;

report = struct();
report.generator_report = generator_report;
report.zone_dispatch = zone_dispatch;
report.external_gen_idx = new_external_idx;
report.active_dispatch_gen_idx = active_dispatch_gen_idx;
report.input_internal_gen_count = numel(internal_input_idx);
report.output_internal_gen_count = size(internal_gen, 1);
report.external_gen_count = numel(new_external_idx);
report.control_group_count = numel(groups);
report.map_diagnostics = map_diagnostics;
report.excluded_placeholder_counts = placeholder_counts;
report.common_vg_report = common_vg_report;
report.invariance = invariance;
report.alignment = alignment;

if options.strict_invariance && (~invariance.all_pass || ~alignment.all_pass)
    error('apply_perform_controls_to_operating_case:InvariantFailure', ...
        'A protected operating-case field changed or generator metadata is misaligned.');
end
end

function bus_id = select_operational_reference(gen, inherited_ref, candidates, tol)
define_constants;
online = gen(:, GEN_STATUS)>0;
active = online & gen(:, PMAX)-gen(:, PMIN)>tol;
variable_q = gen(:, QMAX)-gen(:, QMIN)>tol;
eligible = active & variable_q & ismember(gen(:, GEN_BUS), candidates(:));
if any(eligible & ismember(gen(:, GEN_BUS), inherited_ref(:)))
    bus_id = inherited_ref(find(ismember(inherited_ref, ...
        gen(eligible, GEN_BUS)), 1));
    return;
end
ids = unique(gen(eligible, GEN_BUS), 'stable');
if isempty(ids)
    error('apply_perform_controls_to_operating_case:OperationalReference', ...
        'No source-backed PV candidate has both active and reactive range.');
end
score = zeros(numel(ids), 1);
for k = 1:numel(ids)
    rows = eligible & gen(:, GEN_BUS)==ids(k);
    score(k) = sum(gen(rows, PMAX)-gen(rows, PMIN));
end
[~, pick] = max(score);
bus_id = ids(pick);
end

function mpc = set_bus_types(mpc, bus_ids, bus_type)
define_constants;
for k = 1:numel(bus_ids)
    bi = find(mpc.bus(:, BUS_I) == bus_ids(k), 1);
    if isempty(bi)
        error('apply_perform_controls_to_operating_case:MissingControlBus', ...
            'Required control bus %.0f is absent from the operating case.', ...
            bus_ids(k));
    end
    mpc.bus(bi, BUS_TYPE) = bus_type;
end
end

function options = defaults(options, helper_dir)
items = { ...
    'control_map_file', fullfile(helper_dir, 'perform_source_to_reduced_control_mapping.csv'); ...
    'expected_control_map_rows', 649; ...
    'strict_map_size', true; ...
    'strict_invariance', true; ...
    'pv_candidate_bus_ids', [37 38 39 41 73 76 81]; ...
    'provisional_fixed_q_bus_ids', [43 44 9003]; ...
    'reference_boundary_q_tolerance_mvar', 0; ...
    'boundary_p_policy', "public_schedules_authoritative"; ...
    'internal_pg_policy', "preserve_input_zonal"; ...
    'source_operating_case', []; ...
    'boundary_placeholder_threshold_mvar', 5000; ...
    'qs_broad_range_threshold_mvar', 750; ...
    'numeric_tolerance', 1e-8};
for k = 1:size(items, 1)
    if ~isfield(options, items{k, 1}), options.(items{k, 1}) = items{k, 2}; end
end
options.boundary_p_policy = string(options.boundary_p_policy);
allowed = ["public_schedules_authoritative", ...
    "fixed_source_when_no_public_external"];
if ~ismember(options.boundary_p_policy, allowed)
    error('apply_perform_controls_to_operating_case:BoundaryPolicy', ...
        'Unknown boundary_p_policy: %s', options.boundary_p_policy);
end
options.internal_pg_policy = string(options.internal_pg_policy);
allowed_pg = ["preserve_input_zonal", "source_group_priors"];
if ~ismember(options.internal_pg_policy, allowed_pg)
    error('apply_perform_controls_to_operating_case:InternalPGPolicy', ...
        'Unknown internal_pg_policy: %s', options.internal_pg_policy);
end
end

function value = field_or_empty(s, name)
if isfield(s, name), value = s.(name); else, value = []; end
end

function map = read_control_map(options)
if isfield(options, 'control_map') && istable(options.control_map)
    map = options.control_map;
else
    if exist(options.control_map_file, 'file') ~= 2
        error('apply_perform_controls_to_operating_case:MissingControlMap', ...
            'Control map not found: %s', options.control_map_file);
    end
    import = detectImportOptions(options.control_map_file, ...
        'VariableNamingRule', 'preserve');
    text_names = intersect(import.VariableNames, { ...
        'source_generator_id','source_bus_name','source_zone','source_plant_name', ...
        'source_fuel','device_class','source_regulated_bus_name','regulated_zone', ...
        'reduced_device_type','reduced_control_group_id','mapping_confidence', ...
        'classification_confidence'}, 'stable');
    import = setvartype(import, text_names, 'string');
    map = readtable(options.control_map_file, import);
end

text_names = {'source_generator_id','source_bus_name','source_zone', ...
    'source_plant_name','source_fuel','device_class','source_regulated_bus_name', ...
    'regulated_zone','reduced_device_type','reduced_control_group_id', ...
    'mapping_confidence','classification_confidence'};
for k = 1:numel(text_names)
    if ismember(text_names{k}, map.Properties.VariableNames)
        map.(text_names{k}) = string(map.(text_names{k}));
    end
end
numeric_names = {'source_bus','source_regulated_bus','source_VS','source_QMIN', ...
    'source_QMAX','source_PG','source_QG','source_PMIN','source_PMAX', ...
    'retained_device_bus','retained_pilot_bus','status','converted_status', ...
    'snapshot_effective_status','raw_converted_status_mismatch', ...
    'remote_regulation','converted_gen_index'};
for k = 1:numel(numeric_names)
    if ismember(numeric_names{k}, map.Properties.VariableNames) && ...
            ~isnumeric(map.(numeric_names{k}))
        map.(numeric_names{k}) = str2double(string(map.(numeric_names{k})));
    end
end
end

function validate_control_map(map, options)
required = {'source_bus','source_generator_id','source_fuel','device_class', ...
    'source_VS','source_QMIN','source_QMAX','source_PG','source_QG', ...
    'source_PMIN','source_PMAX','retained_device_bus','retained_pilot_bus', ...
    'snapshot_effective_status','remote_regulation','mapping_confidence'};
missing = setdiff(required, map.Properties.VariableNames, 'stable');
if ~isempty(missing)
    error('apply_perform_controls_to_operating_case:ControlMapSchema', ...
        'Control map is missing: %s', strjoin(missing, ', '));
end

if options.strict_map_size && height(map) ~= options.expected_control_map_rows
    error('apply_perform_controls_to_operating_case:ControlMapSize', ...
        'Expected %d control-map rows, found %d.', ...
        options.expected_control_map_rows, height(map));
end
keys = string(map.source_bus) + "|" + upper(strtrim(map.source_generator_id));
if numel(unique(keys)) ~= height(map)
    error('apply_perform_controls_to_operating_case:DuplicateSourceKey', ...
        'Control-map source bus + generator-ID keys are not unique.');
end
end

function map = apply_source_operating_priors(map, options)
if isempty(options.source_operating_case), return; end
define_constants;
source = options.source_operating_case;
if ischar(source) || isstring(source), source = loadcase(char(source)); end
if ~isstruct(source) || ~isfield(source, 'bus') || ~isfield(source, 'gen')
    error('apply_perform_controls_to_operating_case:SourceOperatingCase', ...
        'source_operating_case must be a MATPOWER case/result struct or case name.');
end
if ~ismember('converted_gen_index', map.Properties.VariableNames)
    error('apply_perform_controls_to_operating_case:SourceOperatingMap', ...
        'converted_gen_index is required when source_operating_case is supplied.');
end
ci = map.converted_gen_index;
converted = isfinite(ci);
if any(ci(converted) < 1 | ci(converted) > size(source.gen, 1) | ...
        ci(converted) ~= round(ci(converted)))
    error('apply_perform_controls_to_operating_case:SourceOperatingIndex', ...
        'A converted_gen_index is invalid for the supplied source case.');
end
map.source_PG(converted) = source.gen(ci(converted), PG);
map.source_QG(converted) = source.gen(ci(converted), QG);

qs = upper(strtrim(map.source_generator_id)) == "QS";
[found, bi] = ismember(map.source_bus(qs), source.bus(:, BUS_I));
if any(~found)
    error('apply_perform_controls_to_operating_case:SourceOperatingQSBus', ...
        'A QS source bus is absent from the supplied source operating case.');
end
qs_q = source.bus(bi, BS) .* source.bus(bi, VM).^2;
map.source_QG(qs) = qs_q;
end

function [idx, metadata] = external_generator_indices(mpc, options)
idx = zeros(0, 1);
metadata = [];
if isfield(mpc, 'userdata') && isfield(mpc.userdata, 'ny_only_equivalent') && ...
        isfield(mpc.userdata.ny_only_equivalent, 'external_equivalent_generators')
    metadata = mpc.userdata.ny_only_equivalent.external_equivalent_generators;
    if istable(metadata) && ismember('added_gen_index', metadata.Properties.VariableNames)
        idx = double(metadata.added_gen_index(:));
    elseif isstruct(metadata) && isfield(metadata, 'added_gen_index')
        idx = double([metadata.added_gen_index]');
    end
end
if isfield(options, 'external_gen_idx') && ~isempty(options.external_gen_idx)
    idx = double(options.external_gen_idx(:));
end
if any(~isfinite(idx) | idx < 1 | idx > size(mpc.gen, 1) | idx ~= round(idx)) || ...
        numel(unique(idx)) ~= numel(idx)
    error('apply_perform_controls_to_operating_case:ExternalGeneratorIndex', ...
        'Public external generator indices are invalid.');
end
end

function rows = aligned_cost_rows(cost, gen_count, idx)
if isempty(idx), rows = zeros(0, max(7, size(cost, 2))); return; end
if ~isempty(cost) && size(cost, 1) == gen_count
    rows = cost(idx, :);
else
    rows = [];
end
end

function rows = aligned_text_rows(values, gen_count, idx, fallback)
if isempty(idx), rows = cell(0, 1); return; end
if ~isempty(values) && numel(values) == gen_count
    if isstring(values), values = cellstr(values); end
    rows = values(idx);
    rows = rows(:);
else
    rows = repmat({fallback}, numel(idx), 1);
end
end

function [bus_ids, zones] = bus_zone_lookup(mpc)
define_constants;
bus_ids = mpc.bus(:, BUS_I);
zones = strings(size(bus_ids));
if isfield(mpc, 'userdata') && isfield(mpc.userdata, 'nyiso_physical_zone')
    zones = upper(strtrim(string(mpc.userdata.nyiso_physical_zone(:))));
end
end

function zone = zone_for_bus(bus_id, bus_ids, zones)
idx = find(bus_ids == bus_id, 1);
if isempty(idx), zone = ""; else, zone = zones(idx); end
end

function rows = zonal_internal_pg(gen, internal_idx, bus_ids, zones)
define_constants;
letters = string(('A':'K')');
target = zeros(numel(letters), 1);
for k = 1:numel(internal_idx)
    gi = internal_idx(k);
    if gen(gi, GEN_STATUS) <= 0, continue; end
    zone = zone_for_bus(gen(gi, GEN_BUS), bus_ids, zones);
    zi = find(letters == zone, 1);
    if ~isempty(zi), target(zi) = target(zi) + gen(gi, PG); end
end
rows = table(letters, target, 'VariableNames', {'zone','scenario_internal_pg_mw'});
end

function [groups, diagnostics] = aggregate_control_groups(map, mpc, options)
define_constants;
online = map.snapshot_effective_status > 0;
fuel = lower(strtrim(map.source_fuel));
id = upper(strtrim(map.source_generator_id));
class = lower(strtrim(map.device_class));

is_reference = online & (fuel == "reference" | id == "RF");
is_boundary = online & (is_reference | fuel == "import" | ...
    class == "fixed_import_or_boundary_equivalent");
is_qs = online & ~is_boundary & (id == "QS" | class == "reactive_only_qs");
is_sync = online & ~is_boundary & ~is_qs & class == "synchronous_condenser";
is_storage = online & ~is_boundary & ~is_qs & class == "storage_or_pumping";
is_native = online & ~is_boundary & ~is_qs & ~is_sync & ...
    (class == "native_generator" | is_storage);

types = repmat("unclassified_control_record", height(map), 1);
types(is_native & ~is_storage) = "aggregate_pv_generator";
types(is_storage) = "storage_or_pumping";
types(is_qs) = "controllable_q_device";
types(is_sync) = "synchronous_condenser";
types(is_boundary & ~is_reference) = "boundary_import_equivalent";
types(is_reference) = "reference_boundary_equivalent";

valid_bus = isfinite(map.retained_device_bus) & isfinite(map.retained_pilot_bus) & ...
    ismember(map.retained_device_bus, mpc.bus(:, BUS_I)) & ...
    ismember(map.retained_pilot_bus, mpc.bus(:, BUS_I));
eligible = online & valid_bus & types ~= "unclassified_control_record";
group_id = "BUS_" + string(map.retained_device_bus) + "__PILOT_" + ...
    string(map.retained_pilot_bus) + "__" + upper(types);
ids = unique(group_id(eligible), 'stable');

internal_placeholder = ~is_boundary & ~is_qs & ...
    generic_placeholder_pair(map.source_QMIN, map.source_QMAX, options);
boundary_placeholder = is_boundary & (abs(map.source_QMIN) >= ...
    options.boundary_placeholder_threshold_mvar | abs(map.source_QMAX) >= ...
    options.boundary_placeholder_threshold_mvar);
qs_broad = is_qs & (abs(map.source_QMIN) > 5000 | ...
    abs(map.source_QMAX) > 5000 | ...
    map.source_QMAX-map.source_QMIN > 4*max(map.source_PMAX, 100));

groups = repmat(group_template(), 0, 1);
for k = 1:numel(ids)
    idx = eligible & group_id == ids(k);
    rows = find(idx);
    group = group_template();
    group.id = ids(k);
    group.device_bus = map.retained_device_bus(rows(1));
    group.pilot_bus = map.retained_pilot_bus(rows(1));
    group.reduced_type = types(rows(1));
    group.source_device_class = join(unique(map.device_class(rows), 'stable')', '|');
    group.source_record_count = numel(rows);
    group.source_bus_ids = join(string(unique(map.source_bus(rows), 'stable'))', '|');
    keys = string(map.source_bus(rows)) + ":" + map.source_generator_id(rows);
    group.source_generator_ids = join(keys', '|');
    group.is_source_reference = any(is_reference(rows));
    group.is_boundary = any(is_boundary(rows));
    group.is_native_active = any(is_native(rows));
    group.is_q_only = any(is_qs(rows) | is_sync(rows));
    group.remote_regulation = any(map.remote_regulation(rows) > 0) || ...
        group.device_bus ~= group.pilot_bus;
    group.source_pg = sum(map.source_PG(rows));
    group.source_qg = sum(map.source_QG(rows));
    group.zone = zone_for_bus(group.device_bus, mpc.bus(:, BUS_I), ...
        upper(strtrim(string(mpc.userdata.nyiso_physical_zone(:)))));

    if group.is_native_active
        group.pmin = sum(map.source_PMIN(rows));
        group.pmax = sum(map.source_PMAX(rows));
        if group.pmin > group.pmax + options.numeric_tolerance
            error('apply_perform_controls_to_operating_case:InvalidPRange', ...
                'Group %s has PMIN > PMAX.', group.id);
        end
    else
        group.pmin = 0;
        group.pmax = 0;
    end

    qmin = map.source_QMIN(rows);
    qmax = map.source_QMAX(rows);
    qg = map.source_QG(rows);
    local_placeholder = internal_placeholder(rows);
    qmin(local_placeholder) = qg(local_placeholder);
    qmax(local_placeholder) = qg(local_placeholder);
    if group.is_source_reference
        qmin(:) = qg;
        qmax(:) = qg;
    end
    group.qmin = sum(qmin);
    group.qmax = sum(qmax);

    physical = ~boundary_placeholder(rows) & ~local_placeholder;
    weights = zeros(numel(rows), 1);
    weights(physical) = max(map.source_QMAX(rows(physical)) - ...
        map.source_QMIN(rows(physical)), 0);
    if sum(weights) <= options.numeric_tolerance && group.is_native_active
        weights(physical) = max(map.source_PMAX(rows(physical)), 0);
    end
    if sum(weights) <= options.numeric_tolerance
        weights(physical) = 1;
    end
    if sum(weights) <= options.numeric_tolerance
        group.vg = mean(map.source_VS(rows), 'omitnan');
    else
        group.vg = sum(weights .* map.source_VS(rows), 'omitnan') / sum(weights);
    end
    if ~isfinite(group.vg)
        bi = find(mpc.bus(:, BUS_I) == group.pilot_bus, 1);
        group.vg = mpc.bus(bi, VM);
    end
    group.mapping_confidence = aggregate_confidence(map.mapping_confidence(rows));
    groups(end+1, 1) = group; %#ok<AGROW>
end

diagnostics = struct();
diagnostics.input_row_count = height(map);
diagnostics.effective_online_row_count = nnz(online);
diagnostics.eligible_online_row_count = nnz(eligible);
diagnostics.unclassified_online_row_count = nnz(online & ...
    types == "unclassified_control_record");
diagnostics.invalid_bus_online_row_count = nnz(online & ~valid_bus);
diagnostics.internal_placeholder_count = nnz(internal_placeholder & online);
diagnostics.boundary_placeholder_count = nnz(boundary_placeholder & online);
diagnostics.qs_broad_preserved_count = nnz(qs_broad & online);
diagnostics.source_reference_key = join(string(map.source_bus(is_reference)) + ":" + ...
    map.source_generator_id(is_reference), '|');
end

function group = group_template()
group = struct( ...
    'id', "", 'device_bus', NaN, 'pilot_bus', NaN, 'reduced_type', "", ...
    'source_device_class', "", 'source_record_count', 0, ...
    'source_bus_ids', "", 'source_generator_ids', "", ...
    'is_source_reference', false, 'is_boundary', false, ...
    'is_native_active', false, 'is_q_only', false, ...
    'remote_regulation', false, 'source_pg', 0, 'source_qg', 0, ...
    'pmin', 0, 'pmax', 0, 'qmin', 0, 'qmax', 0, 'vg', 1, ...
    'zone', "", 'scenario_pg_before', 0, 'pg', 0, ...
    'p_projected', false, 'mapping_confidence', "");
end

function confidence = aggregate_confidence(values)
values = lower(strtrim(string(values)));
if any(values == "low"), confidence = "low";
elseif any(values == "medium"), confidence = "medium";
else, confidence = "high";
end
end

function [groups, rows] = allocate_zonal_active_power(groups, old_zone_pg, options)
letters = string(('A':'K')');
zone_rows = repmat(zone_dispatch_template(), numel(letters), 1);
for k = 1:numel(letters)
    zone = letters(k);
    idx = find([groups.is_native_active] & string({groups.zone}) == zone);
    if options.internal_pg_policy == "source_group_priors"
        target = sum([groups(idx).source_pg]);
    else
        target = old_zone_pg.scenario_internal_pg_mw(old_zone_pg.zone == zone);
    end
    if isempty(target), target = 0; end
    zone_rows(k).zone = zone;
    zone_rows(k).target_policy = options.internal_pg_policy;
    zone_rows(k).scenario_internal_pg_mw = target;
    zone_rows(k).active_group_count = numel(idx);
    if isempty(idx)
        zone_rows(k).aggregate_pmin_mw = 0;
        zone_rows(k).aggregate_pmax_mw = 0;
        zone_rows(k).allocated_pg_mw = 0;
        zone_rows(k).residual_mw = -target;
        zone_rows(k).feasible = abs(target) <= options.numeric_tolerance;
        zone_rows(k).projection_required = ~zone_rows(k).feasible;
        continue;
    end
    pmin = [groups(idx).pmin]';
    pmax = [groups(idx).pmax]';
    prior = [groups(idx).source_pg]';
    [allocation, feasible] = bounded_allocation(target, pmin, pmax, prior, ...
        options.numeric_tolerance);
    for j = 1:numel(idx)
        groups(idx(j)).scenario_pg_before = target;
        groups(idx(j)).pg = allocation(j);
        groups(idx(j)).p_projected = ...
            abs(allocation(j) - prior(j)) > options.numeric_tolerance;
    end
    zone_rows(k).source_prior_pg_mw = sum(prior);
    zone_rows(k).aggregate_pmin_mw = sum(pmin);
    zone_rows(k).aggregate_pmax_mw = sum(pmax);
    zone_rows(k).allocated_pg_mw = sum(allocation);
    zone_rows(k).residual_mw = sum(allocation) - target;
    zone_rows(k).feasible = feasible;
    zone_rows(k).projection_required = ~feasible;
end
rows = struct2table(zone_rows);
end

function [allocation, feasible] = bounded_allocation(target, pmin, pmax, prior, tol)
lower = sum(pmin);
upper = sum(pmax);
feasible = target >= lower - tol && target <= upper + tol;
projected_target = min(max(target, lower), upper);
allocation = min(max(prior, pmin), pmax);
delta = projected_target - sum(allocation);
if delta > tol
    headroom = max(pmax - allocation, 0);
    if sum(headroom) > tol
        allocation = allocation + delta * headroom / sum(headroom);
    end
elseif delta < -tol
    footroom = max(allocation - pmin, 0);
    if sum(footroom) > tol
        allocation = allocation + delta * footroom / sum(footroom);
    end
end
allocation = min(max(allocation, pmin), pmax);
end

function row = zone_dispatch_template()
row = struct('zone', "", 'target_policy', "", ...
    'scenario_internal_pg_mw', 0, ...
    'active_group_count', 0, 'source_prior_pg_mw', 0, ...
    'aggregate_pmin_mw', 0, 'aggregate_pmax_mw', 0, ...
    'allocated_pg_mw', 0, 'residual_mw', 0, ...
    'feasible', false, 'projection_required', false);
end

function [gen, fuels, types, report_rows] = append_internal_generator( ...
        gen, fuels, types, report_rows, ncol, baseMVA, group, bus_id, ...
        pg, qg, pmin, pmax, qmin, qmax, vg, role, fuel, qfixed, ...
        p_projected, q_projected, action)
define_constants;
if pmin > pmax || qmin > qmax
    error('apply_perform_controls_to_operating_case:InvalidGeneratorRange', ...
        'Invalid generator limits for group %s.', group.id);
end
if pg < pmin-1e-7 || pg > pmax+1e-7
    error('apply_perform_controls_to_operating_case:PGOutsideRange', ...
        'PG %.6g is outside [%.6g, %.6g] for group %s.', ...
        pg, pmin, pmax, group.id);
end
if qg < qmin-1e-7 || qg > qmax+1e-7
    error('apply_perform_controls_to_operating_case:QGOutsideRange', ...
        'QG %.6g is outside [%.6g, %.6g] for group %s.', ...
        qg, qmin, qmax, group.id);
end
new = zeros(1, ncol);
new(GEN_BUS) = bus_id;
new(PG) = pg;
new(QG) = qg;
new(QMAX) = qmax;
new(QMIN) = qmin;
new(VG) = vg;
new(MBASE) = baseMVA;
new(GEN_STATUS) = 1;
new(PMAX) = pmax;
new(PMIN) = pmin;
gen = [gen; new];
fuels{end+1, 1} = char(fuel);
types{end+1, 1} = 'AG';
row = group_report_row(group, size(gen, 1), role, pg, qg, pmin, pmax, ...
    qmin, qmax, vg, qfixed, p_projected, q_projected, action);
report_rows(end+1, 1) = row;
end

function row = group_report_row(group, gen_index, role, pg, qg, pmin, pmax, ...
        qmin, qmax, vg, qfixed, p_projected, q_projected, action)
row = generator_report_template();
row.reduced_control_group_id = group.id;
row.reduced_gen_index = gen_index;
row.retained_device_bus = group.device_bus;
row.retained_pilot_bus = group.pilot_bus;
row.zone = group.zone;
row.reduced_device_type = group.reduced_type;
row.source_device_class = group.source_device_class;
row.injection_role = string(role);
row.source_record_count = group.source_record_count;
row.source_bus_ids = group.source_bus_ids;
row.source_generator_ids = group.source_generator_ids;
row.source_reference = group.is_source_reference;
row.remote_regulation = group.remote_regulation;
row.snapshot_effective_status = 1;
row.is_external_boundary_equivalent = group.is_boundary;
row.is_native_active_control = group.is_native_active;
row.is_q_only_control = group.is_q_only;
row.is_reference_balance = group.is_source_reference;
row.is_operational_reference = false;
row.scenario_pg_before_mw = group.scenario_pg_before;
row.source_pg_mw = group.source_pg;
row.source_qg_mvar = group.source_qg;
row.initial_pg_mw = pg;
row.initial_qg_mvar = qg;
row.pmin_mw = pmin;
row.pmax_mw = pmax;
row.qmin_mvar = qmin;
row.qmax_mvar = qmax;
row.vg_pu = vg;
row.q_limits_fixed = qfixed;
row.p_projected = p_projected;
row.q_projected = q_projected;
row.mapping_confidence = group.mapping_confidence;
row.provenance_action = string(action);
end

function row = generator_report_template()
row = struct( ...
    'reduced_control_group_id', "", 'reduced_gen_index', NaN, ...
    'input_gen_index', NaN, 'retained_device_bus', NaN, ...
    'retained_pilot_bus', NaN, 'zone', "", 'reduced_device_type', "", ...
    'source_device_class', "", 'injection_role', "", ...
    'source_record_count', 0, 'source_bus_ids', "", ...
    'source_generator_ids', "", 'source_reference', false, ...
    'remote_regulation', false, 'snapshot_effective_status', 0, ...
    'is_external_boundary_equivalent', false, ...
    'is_native_active_control', false, 'is_q_only_control', false, ...
    'is_reference_balance', false, 'is_operational_reference', false, ...
    'scenario_pg_before_mw', 0, 'source_pg_mw', 0, 'source_qg_mvar', 0, ...
    'initial_pg_mw', 0, 'initial_qg_mvar', 0, ...
    'pmin_mw', 0, 'pmax_mw', 0, 'qmin_mvar', 0, 'qmax_mvar', 0, ...
    'vg_pu', 1, 'q_limits_fixed', false, 'p_projected', false, ...
    'q_projected', false, 'mapping_confidence', "", ...
    'provenance_action', "");
end

function [gen, report_rows, rows, mpc] = harmonize_internal_vg( ...
        gen, external_gen, external_input_idx, report_rows, mpc, options)
define_constants;
bus_ids = unique(gen(gen(:, GEN_STATUS) > 0 & ...
    gen(:, QMAX)-gen(:, QMIN) > options.numeric_tolerance, GEN_BUS), 'stable');
records = repmat(common_vg_template(), 0, 1);
for bus_id = bus_ids(:)'
    internal_idx = find(gen(:, GEN_STATUS) > 0 & gen(:, GEN_BUS) == bus_id);
    internal_reg = internal_idx(gen(internal_idx, QMAX)-gen(internal_idx, QMIN) > ...
        options.numeric_tolerance);
    external_reg = find(external_gen(:, GEN_STATUS) > 0 & ...
        external_gen(:, GEN_BUS) == bus_id & ...
        external_gen(:, QMAX)-external_gen(:, QMIN) > options.numeric_tolerance);
    record = common_vg_template();
    record.bus_id = bus_id;
    record.internal_regulating_count = numel(internal_reg);
    record.external_regulating_count = numel(external_reg);
    record.external_input_gen_indices = join(string(external_input_idx(external_reg))', '|');
    if ~isempty(external_reg)
        values = external_gen(external_reg, VG);
        common = values(1);
        record.source = "immutable_public_external_vg";
        record.immutable_external_vg_conflict = ...
            any(abs(values-common) > options.numeric_tolerance);
    else
        ranges = gen(internal_reg, QMAX)-gen(internal_reg, QMIN);
        common = sum(ranges .* gen(internal_reg, VG)) / sum(ranges);
        record.source = "physical_internal_q_range_weighted";
    end
    gen(internal_idx, VG) = common;
    record.common_vg_pu = common;
    records(end+1, 1) = record; %#ok<AGROW>
    for r = 1:numel(report_rows)
        gi = report_rows(r).reduced_gen_index;
        if isfinite(gi) && gi <= size(gen, 1) && gen(gi, GEN_BUS) == bus_id
            report_rows(r).vg_pu = common;
        end
    end
    bi = find(mpc.bus(:, BUS_I) == bus_id, 1);
    if ~isempty(bi) && ismember(mpc.bus(bi, BUS_TYPE), [PV REF])
        mpc.bus(bi, VM) = common;
    end
end
rows = struct2table(records);
end

function row = common_vg_template()
row = struct('bus_id', NaN, 'internal_regulating_count', 0, ...
    'external_regulating_count', 0, 'common_vg_pu', NaN, 'source', "", ...
    'immutable_external_vg_conflict', false, ...
    'external_input_gen_indices', "");
end

function group = external_report_group(bus_id, old_gi, metadata, metadata_row, zone)
group = group_template();
name = "PUBLIC_EXTERNAL_GEN_" + string(old_gi);
if istable(metadata) && height(metadata) >= metadata_row && ...
        ismember('external_interface_name', metadata.Properties.VariableNames)
    name = string(metadata.external_interface_name(metadata_row));
end
group.id = "PUBLIC_EXTERNAL__" + upper(regexprep(name, '[^A-Za-z0-9]+', '_'));
group.device_bus = bus_id;
group.pilot_bus = bus_id;
group.zone = zone;
group.reduced_type = "public_external_boundary_equivalent";
group.source_device_class = "public_external_boundary_equivalent";
group.source_record_count = 1;
group.source_bus_ids = string(bus_id);
group.source_generator_ids = name;
group.is_boundary = true;
group.mapping_confidence = "scenario_source";
end

function output = pad_matrix(input, width)
if isempty(input), output = zeros(0, width); return; end
if size(input, 2) < width
    output = [input zeros(size(input, 1), width-size(input, 2))];
elseif size(input, 2) > width
    output = input(:, 1:width);
else
    output = input;
end
end

function rows = default_cost_rows(count, width)
rows = zeros(count, width);
if count == 0, return; end
template = zeros(1, width);
template(1:min(width, 7)) = [2 0 0 2 0 0 0];
rows(:,:) = repmat(template, count, 1);
end

function flag = generic_placeholder_pair(qmin, qmax, options)
qmin = double(qmin);
qmax = double(qmax);
symmetry = abs(qmin + qmax) <= max(options.numeric_tolerance, ...
    1e-8 * max([abs(qmin), abs(qmax), ones(size(qmin))], [], 2));
values = [999 9999 9900];
match = false(size(qmin));
for k = 1:numel(values)
    match = match | (abs(abs(qmin)-values(k)) <= 1e-6 & ...
        abs(abs(qmax)-values(k)) <= 1e-6);
end
flag = symmetry & match;
end
