function summary = analyze_winter_mitigations()
root = fileparts(fileparts(mfilename('fullpath')));
case_file = fullfile(root, 'output', 's8_winter_peak_handoff', 'cases', ...
    'npcc_ny_lite_s8_winter_peak_operating_case.mat');
map_file = fullfile(root, 'output', 's8_winter_peak_handoff', 'data', ...
    'winter_peak_interface_branch_map.csv');
target_file = fullfile(root, 'output', 's8_winter_peak_handoff', 'results', ...
    'winter_peak_interface_comparison.csv');
loaded = load(case_file, 'mpc');
base = loaded.mpc;
map = readtable(map_file, 'TextType', 'string');
targets = readtable(target_file, 'TextType', 'string');
define_constants;

external_idx = base.userdata.ny_only_equivalent. ...
    external_equivalent_generators.added_gen_index;
variants = { ...
    'BASELINE', @(m) m; ...
    'BOUNDARY_PV_1P03', @(m) boundary_pv(m, external_idx); ...
    'BOUNDARY_FIXED_Q_ZERO', @(m) boundary_fixed_q_zero(m, external_idx); ...
    'HUNTLEY_VG_1P03', @(m) set_bus_vg(m, 56, 1.03); ...
    'INTERNAL_VG_CAP_1P05', @(m) cap_internal_vg(m, external_idx, 1.05); ...
    'BOUNDARY_PV_AND_INTERNAL_CAP', @(m) cap_internal_vg( ...
        boundary_pv(m, external_idx), external_idx, 1.05); ...
    'SHIFT_100MW_NIAGARA_TO_RAMAPO', @(m) shift_external_p(m, ...
        external_idx, 54, 75, 100)};

summary = table();
for k = 1:size(variants, 1)
    name = string(variants{k, 1});
    mpc = variants{k, 2}(base);
    try
        opt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1);
        r = runpf(mpc, opt);
        success = logical(r.success);
        metrics = case_metrics(r, map, targets);
        note = "";
    catch err
        success = false;
        metrics = empty_metrics();
        note = string(err.identifier) + ": " + string(err.message);
    end
    row = struct2table(metrics);
    row.variant = name;
    row.success = success;
    row.note = note;
    row = movevars(row, {'variant','success'}, 'Before', 1);
    summary = [summary; row]; %#ok<AGROW>
end
disp(summary(:, {'variant','success','wape_pct','max_voltage_pu', ...
    'voltage_violation_count','branch29_loading_pct', ...
    'branch29_overload_mva','branch63_loading_pct', ...
    'branch63_overload_mva','max_branch_overload_mva'}));
end

function mpc = boundary_pv(mpc, external_idx)
define_constants;
for g = external_idx(:)'
    bi = find(mpc.bus(:, BUS_I) == mpc.gen(g, GEN_BUS), 1);
    if mpc.bus(bi, BUS_TYPE) ~= REF, mpc.bus(bi, BUS_TYPE) = PV; end
    mpc.gen(g, VG) = 1.03;
    mpc.bus(bi, VM) = 1.03;
end
end

function mpc = boundary_fixed_q_zero(mpc, external_idx)
define_constants;
mpc.gen(external_idx, QG) = 0;
mpc.gen(external_idx, QMIN) = 0;
mpc.gen(external_idx, QMAX) = 0;
end

function mpc = set_bus_vg(mpc, bus_id, target)
define_constants;
gi = find(mpc.gen(:, GEN_BUS) == bus_id & mpc.gen(:, GEN_STATUS) > 0);
bi = find(mpc.bus(:, BUS_I) == bus_id, 1);
mpc.gen(gi, VG) = target;
mpc.bus(bi, VM) = target;
end

function mpc = cap_internal_vg(mpc, external_idx, cap)
define_constants;
internal = setdiff(find(mpc.gen(:, GEN_STATUS) > 0), external_idx);
gi = internal(mpc.gen(internal, VG) > cap);
mpc.gen(gi, VG) = cap;
for bus_id = unique(mpc.gen(gi, GEN_BUS))'
    bi = find(mpc.bus(:, BUS_I) == bus_id, 1);
    if mpc.bus(bi, BUS_TYPE) == PV, mpc.bus(bi, VM) = cap; end
end
end

function mpc = shift_external_p(mpc, external_idx, from_bus, to_bus, amount)
define_constants;
from = external_idx(mpc.gen(external_idx, GEN_BUS) == from_bus);
to = external_idx(mpc.gen(external_idx, GEN_BUS) == to_bus);
if numel(from) ~= 1 || numel(to) ~= 1
    error('Expected one external generator at each transfer bus.');
end
for pair = [from, -amount; to, amount]'
    g = pair(1);
    delta = pair(2);
    mpc.gen(g, PG) = mpc.gen(g, PG) + delta;
    mpc.gen(g, PMIN) = mpc.gen(g, PMIN) + delta;
    mpc.gen(g, PMAX) = mpc.gen(g, PMAX) + delta;
end
end

function metrics = case_metrics(r, map, targets)
define_constants;
flow = zeros(height(targets), 1);
for k = 1:height(targets)
    rows = map(map.interface_name == targets.interface_name(k), :);
    for j = 1:height(rows)
        if rows.flow_column(j) == "PF"
            value = r.branch(rows.branch_index(j), PF);
        else
            value = r.branch(rows.branch_index(j), PT);
        end
        flow(k) = flow(k) + rows.sign(j) * value;
    end
end
residual = flow - targets.target_flow_mw;
sf = hypot(r.branch(:, PF), r.branch(:, QF));
st = hypot(r.branch(:, PT), r.branch(:, QT));
loading = max(sf, st);
rate = r.branch(:, RATE_A);
overload = loading - rate;
rated = rate > 0;
metrics = struct( ...
    'wape_pct', 100 * sum(abs(residual)) / sum(abs(targets.target_flow_mw)), ...
    'max_interface_error_mw', max(abs(residual)), ...
    'max_voltage_pu', max(r.bus(:, VM)), ...
    'voltage_violation_count', sum(r.bus(:, VM) > r.bus(:, VMAX) + 1e-6 | ...
        r.bus(:, VM) < r.bus(:, VMIN) - 1e-6), ...
    'branch29_loading_pct', 100 * loading(29) / rate(29), ...
    'branch29_overload_mva', max(0, overload(29)), ...
    'branch63_loading_pct', 100 * loading(63) / rate(63), ...
    'branch63_overload_mva', max(0, overload(63)), ...
    'branch_overload_count', sum(rated & overload > 1e-6), ...
    'max_branch_overload_mva', max([0; overload(rated)]));
end

function metrics = empty_metrics()
metrics = struct('wape_pct', NaN, 'max_interface_error_mw', NaN, ...
    'max_voltage_pu', NaN, 'voltage_violation_count', NaN, ...
    'branch29_loading_pct', NaN, 'branch29_overload_mva', NaN, ...
    'branch63_loading_pct', NaN, 'branch63_overload_mva', NaN, ...
    'branch_overload_count', NaN, 'max_branch_overload_mva', NaN);
end
