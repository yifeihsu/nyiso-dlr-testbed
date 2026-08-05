function [mpc, report] = build_s10a_perform_control_mapped_case(options)
%BUILD_S10A_PERFORM_CONTROL_MAPPED_CASE Build 2019 same-snapshot diagnostic.
%   The detailed PERFORM operating point is similarity-scaled to the S7
%   NY-load magnitude. This preserves source per-unit voltages while active
%   and reactive quantities are scaled consistently for the NY-only S7
%   structural network.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
options = defaults(options);
addpath(case_dir); addpath(helper_dir);
define_constants;

mapping_outputs = build_perform_control_preserving_mapping;
control_map = mapping_outputs.control_mapping;
source = mapping_outputs.source_pf;
s7 = attach_nyiso_zone_metadata(loadcase(options.structural_case));
[mpc, reduction_report] = build_ny_only_equivalent_case(s7);

source_zone = perform_bus_zones(source, helper_dir);
s7_ny = s7.userdata.nyiso_zone_id > 0;
target_ny_load_mw = sum(s7.bus(s7_ny, PD));
source_ny_load_mw = sum(source.bus(source_zone ~= "", PD));
gamma = target_ny_load_mw / source_ny_load_mw;

[zone_pd, zone_qd] = source_zonal_loads(source, source_zone, gamma);
[mpc, load_report] = apply_nyiso_zonal_loads(mpc, zone_pd, 1.0, ...
    struct('preserve_total_ny_load', false, 'default_power_factor', 1.0));
mpc.bus(:, QD) = 0;
for z = 1:11
    zone = string(char('A' + z - 1));
    idx = string(mpc.userdata.nyiso_physical_zone) == zone;
    if ~any(idx), continue; end
    weights = mpc.bus(idx, PD);
    if sum(weights) <= 0, weights = ones(sum(idx), 1); end
    weights = weights / sum(weights);
    mpc.bus(idx, QD) = zone_qd(z) * weights;
end
mpc.bus(:, [GS BS]) = 0;

mpc.gen = zeros(0, max(21, size(s7.gen, 2)));
mpc.gencost = zeros(0, 7);
mpc.genfuel = cell(0, 1);
mpc.gentype = cell(0, 1);
mpc.bus(:, BUS_TYPE) = PQ;

online = control_map.snapshot_effective_status > 0 & ...
    control_map.reduced_control_group_id ~= "UNMAPPED";
group_ids = unique(control_map.reduced_control_group_id(online), 'stable');
generator_report = table();
reference_bus = NaN;
for k = 1:numel(group_ids)
    idx = online & control_map.reduced_control_group_id == group_ids(k);
    [pg, qg, pmin, pmax, qmin, qmax, vg] = ...
        source_group_values(control_map, source, idx, gamma);
    device_bus = control_map.retained_device_bus(find(idx, 1));
    pilot_bus = control_map.retained_pilot_bus(find(idx, 1));
    device_type = control_map.reduced_device_type(find(idx, 1));
    is_reference = any(control_map.source_fuel(idx) == "reference");

    if device_type == "boundary_import_equivalent" && ~is_reference
        pmin = pg; pmax = pg;
    elseif is_reference
        pmin = pg - options.reference_balance_range_mw;
        pmax = pg + options.reference_balance_range_mw;
        reference_bus = device_bus;
    end
    if device_type == "boundary_import_equivalent"
        if options.boundary_q_mode == "fixed_source_q"
            qmin = qg; qmax = qg;
        elseif options.boundary_q_mode == "no_discretionary_q"
            qg = 0; qmin = 0; qmax = 0;
        end
    end

    if device_bus == pilot_bus
        [mpc, gi] = add_generator(mpc, device_bus, pg, qg, pmin, pmax, ...
            qmin, qmax, vg, device_type);
        generator_report = append_table(generator_report, generator_row( ...
            group_ids(k), gi, device_bus, pilot_bus, device_type, ...
            "combined_pq_control", pg, qg, pmin, pmax, qmin, qmax, vg, ...
            sum(idx), is_reference));
    else
        [mpc, pgi] = add_generator(mpc, device_bus, pg, 0, pmin, pmax, ...
            0, 0, vg, device_type + "_p_injection");
        generator_report = append_table(generator_report, generator_row( ...
            group_ids(k), pgi, device_bus, pilot_bus, device_type, ...
            "remote_p_injection", pg, 0, pmin, pmax, 0, 0, vg, ...
            sum(idx), is_reference));
        [mpc, qgi] = add_generator(mpc, pilot_bus, 0, qg, 0, 0, ...
            qmin, qmax, vg, device_type + "_remote_q_control");
        generator_report = append_table(generator_report, generator_row( ...
            group_ids(k), qgi, device_bus, pilot_bus, device_type, ...
            "remote_q_control", 0, qg, 0, 0, qmin, qmax, vg, ...
            sum(idx), false));
    end
end

% All source-backed regulating groups are enabled only for this diagnostic.
regulating = mpc.gen(:, GEN_STATUS) > 0 & ...
    mpc.gen(:, QMAX) - mpc.gen(:, QMIN) > options.min_q_range_mvar;
for bus_id = unique(mpc.gen(regulating, GEN_BUS))'
    bi = find(mpc.bus(:, BUS_I) == bus_id, 1);
    mpc.bus(bi, BUS_TYPE) = PV;
    gi = find(regulating & mpc.gen(:, GEN_BUS) == bus_id);
    qrange = mpc.gen(gi, QMAX) - mpc.gen(gi, QMIN);
    if sum(qrange) <= 0, qrange = ones(numel(gi), 1); end
    common_vg = sum(qrange .* mpc.gen(gi, VG)) / sum(qrange);
    mpc.gen(mpc.gen(:, GEN_BUS) == bus_id, VG) = common_vg;
    mpc.bus(bi, VM) = common_vg;
end
if ~isfinite(reference_bus)
    [~, gi] = max(mpc.gen(:, PMAX) - mpc.gen(:, PMIN));
    reference_bus = mpc.gen(gi, GEN_BUS);
end
ref_bi = find(mpc.bus(:, BUS_I) == reference_bus, 1);
mpc.bus(ref_bi, BUS_TYPE) = REF;

mpc.userdata.s10a = struct( ...
    'status', 'diagnostic_not_promoted', ...
    'source_case', 'PERFORM NYISO On Peak 2019 v23', ...
    'structural_case', options.structural_case, ...
    'similarity_scale_gamma', gamma, ...
    'source_ny_load_mw', source_ny_load_mw, ...
    'reduced_ny_load_mw', target_ny_load_mw, ...
    'reference_bus', reference_bus, ...
    'boundary_q_mode', options.boundary_q_mode, ...
    'generator_report', generator_report, ...
    'pq_audit', mapping_outputs.pq_audit, ...
    'discrete_control_summary', mapping_outputs.discrete_summary, ...
    'unmodeled_controls', ['Transformer control modes and switching blocks ' ...
        'remain inventoried but are not optimized; exact public interface ' ...
        'branch/sign operators remain pending.']);

report = struct('gamma', gamma, 'source_ny_load_mw', source_ny_load_mw, ...
    'target_ny_load_mw', target_ny_load_mw, ...
    'reduction_report', reduction_report, 'load_report', load_report, ...
    'generator_report', generator_report, 'reference_bus', reference_bus, ...
    'boundary_q_mode', options.boundary_q_mode, ...
    'mapping_outputs', mapping_outputs);
end

function options = defaults(options)
if ~isfield(options, 'structural_case')
    options.structural_case = 'npcc_ny_lite_s7_seven_interface_perform_direct_candidate';
end
if ~isfield(options, 'reference_balance_range_mw')
    options.reference_balance_range_mw = 1000;
end
if ~isfield(options, 'min_q_range_mvar'), options.min_q_range_mvar = 1e-6; end
if ~isfield(options, 'boundary_q_mode'), options.boundary_q_mode = "fixed_source_q"; end
end

function zones = perform_bus_zones(source, helper_dir)
% HELPER_DIR is retained for backward-compatible function shape.
if isempty(helper_dir), error('build_s10a_perform_control_mapped_case:HelperDir', ...
        'The helper directory cannot be empty.'); end
zones = perform_nyiso_zone_letters(source, source.bus(:, 1));
end

function [pd, qd] = source_zonal_loads(source, zones, gamma)
define_constants;
pd = zeros(11, 1); qd = zeros(11, 1);
for k = 1:11
    zone = string(char('A' + k - 1));
    idx = zones == zone;
    pd(k) = gamma * sum(source.bus(idx, PD));
    qd(k) = gamma * sum(source.bus(idx, QD));
end
end

function [pg, qg, pmin, pmax, qmin, qmax, vg] = ...
        source_group_values(control_map, source, idx, gamma)
define_constants;
rows = find(idx);
pg_values = control_map.source_PG(rows);
qg_values = control_map.source_QG(rows);
ci = control_map.converted_gen_index(rows);
converted = isfinite(ci);
pg_values(converted) = source.gen(ci(converted), PG);
qg_values(converted) = source.gen(ci(converted), QG);
qs = control_map.device_class(rows) == "reactive_only_QS";
[found, bi] = ismember(control_map.source_bus(rows(qs)), source.bus(:, BUS_I));
qs_q = zeros(sum(qs), 1);
qs_q(found) = source.bus(bi(found), BS) .* source.bus(bi(found), VM).^2;
qg_values(qs) = qs_q;

pg = gamma * sum(pg_values); qg = gamma * sum(qg_values);
pmin = gamma * sum(control_map.source_PMIN(rows));
pmax = gamma * sum(control_map.source_PMAX(rows));
qmin_values = control_map.source_QMIN(rows);
qmax_values = control_map.source_QMAX(rows);
boundary = ismember(lower(string(control_map.source_fuel(rows))), ...
    ["import","reference"]) | ...
    string(control_map.reduced_device_type(rows)) == "boundary_import_equivalent";
placeholder = generic_q_placeholder(qmin_values, qmax_values);
physical_q = ~boundary & ~placeholder;
qmin_values(~physical_q) = qg_values(~physical_q);
qmax_values(~physical_q) = qg_values(~physical_q);
qmin = gamma * sum(qmin_values);
qmax = gamma * sum(qmax_values);
weights = zeros(numel(rows), 1);
weights(physical_q) = max(qmax_values(physical_q)-qmin_values(physical_q), 0);
if sum(weights) <= 0
    weights(physical_q) = max(control_map.source_PMAX(rows(physical_q)), 0);
end
if sum(weights) > 0
    vg = sum(weights .* control_map.source_VS(rows)) / sum(weights);
else
    values = control_map.source_VS(rows);
    values = values(isfinite(values));
    if isempty(values), vg = 1; else, vg = median(values); end
end
end

function flag = generic_q_placeholder(qmin, qmax)
flag = false(size(qmin));
for value = [999 9999 9900]
    flag = flag | (abs(qmin+value)<=1e-6 & abs(qmax-value)<=1e-6);
end
end

function [mpc, gi] = add_generator(mpc, bus_id, pg, qg, pmin, pmax, ...
        qmin, qmax, vg, fuel)
define_constants;
new = zeros(1, size(mpc.gen, 2));
new(GEN_BUS) = bus_id; new(PG) = pg; new(QG) = qg;
new(QMAX) = qmax; new(QMIN) = qmin; new(VG) = vg;
new(MBASE) = mpc.baseMVA; new(GEN_STATUS) = 1;
new(PMAX) = max(pmax, pg); new(PMIN) = min(pmin, pg);
mpc.gen = [mpc.gen; new];
mpc.gencost = [mpc.gencost; 2 0 0 2 0 0 0];
mpc.genfuel{end+1,1} = char(fuel);
mpc.gentype{end+1,1} = 'AG';
gi = size(mpc.gen, 1);
end

function row = generator_row(group_id, gen_index, device_bus, pilot_bus, ...
        device_type, role, pg, qg, pmin, pmax, qmin, qmax, vg, count, is_reference)
row = table(string(group_id), gen_index, device_bus, pilot_bus, ...
    string(device_type), string(role), pg, qg, pmin, pmax, qmin, qmax, vg, ...
    count, logical(is_reference), ...
    'VariableNames', {'reduced_control_group_id','reduced_gen_index', ...
    'retained_device_bus','retained_pilot_bus','reduced_device_type', ...
    'injection_role','initial_pg_mw','initial_qg_mvar','pmin_mw','pmax_mw', ...
    'qmin_mvar','qmax_mvar','vg_pu','source_record_count','source_reference'});
end

function out = append_table(out, row)
if isempty(row), return; end
if isempty(out), out = row; else, out = [out; row]; end
end
