function outputs = analyze_perform_reference(output_dir)
%ANALYZE_PERFORM_REFERENCE Extract auditable PERFORM-to-NYISO comparisons.

define_constants;

helper_dir = fileparts(mfilename('fullpath'));
workspace_dir = fileparts(fileparts(helper_dir));
if nargin < 1 || isempty(output_dir)
    output_dir = fullfile(workspace_dir, 'output', 'perform_comparison');
end
if ~exist(output_dir, 'dir')
    mkdir(output_dir);
end

perform_dir = fullfile(workspace_dir, 'PERFORM', ...
    'On Peak 2019 v23_Perform_NY', 'On Peak 2019 v23');
target_dir = helper_dir;

addpath(perform_dir);
mpc = nyiso_On_Peak_v23_shunts_as_z_load;

bus_zone = perform_nyiso_zone_letters(mpc, mpc.bus(:, BUS_I));
bus_names = string(mpc.bus_name(:));

[gen_mapped, gen_bus_idx] = ismember(mpc.gen(:, GEN_BUS), mpc.bus(:, BUS_I));
gen_zone = strings(size(mpc.gen, 1), 1);
gen_zone(gen_mapped) = bus_zone(gen_bus_idx(gen_mapped));
gen_fuel = lower(strtrim(string(mpc.genfuel(:))));
gen_type = string(mpc.gentype(:));
is_import = ismember(gen_fuel, ["import", "reference"]);
is_online = mpc.gen(:, GEN_STATUS) > 0;

zones = string(('A':'K')');
zone_names = ["WEST"; "GENESE"; "CENTRL"; "NORTH"; "MHK VL"; ...
    "CAPITL"; "HUD VL"; "MILLWD"; "DUNWOD"; "N.Y.C."; "LONGIL"];

zonal = table(zones, zone_names, 'VariableNames', {'zone','zone_name'});
zonal.perform_bus_count = zeros(height(zonal), 1);
zonal.perform_load_mw = zeros(height(zonal), 1);
zonal.perform_load_mvar = zeros(height(zonal), 1);
zonal.online_gen_count = zeros(height(zonal), 1);
zonal.native_online_gen_count = zeros(height(zonal), 1);
zonal.import_online_gen_count = zeros(height(zonal), 1);
zonal.native_dispatch_mw = zeros(height(zonal), 1);
zonal.import_dispatch_mw = zeros(height(zonal), 1);
zonal.total_dispatch_mw = zeros(height(zonal), 1);
zonal.native_online_pmax_mw = zeros(height(zonal), 1);
zonal.native_all_pmax_mw = zeros(height(zonal), 1);
zonal.total_online_pmax_mw = zeros(height(zonal), 1);
zonal.total_all_pmax_mw = zeros(height(zonal), 1);
zonal.native_q_dispatch_mvar = zeros(height(zonal), 1);

for z = 1:height(zonal)
    bi = bus_zone == zones(z);
    gi = gen_zone == zones(z);
    native = gi & ~is_import;
    imports = gi & is_import;
    zonal.perform_bus_count(z) = nnz(bi);
    zonal.perform_load_mw(z) = sum(mpc.bus(bi, PD));
    zonal.perform_load_mvar(z) = sum(mpc.bus(bi, QD));
    zonal.online_gen_count(z) = nnz(gi & is_online);
    zonal.native_online_gen_count(z) = nnz(native & is_online);
    zonal.import_online_gen_count(z) = nnz(imports & is_online);
    zonal.native_dispatch_mw(z) = sum(mpc.gen(native & is_online, PG));
    zonal.import_dispatch_mw(z) = sum(mpc.gen(imports & is_online, PG));
    zonal.total_dispatch_mw(z) = sum(mpc.gen(gi & is_online, PG));
    zonal.native_online_pmax_mw(z) = sum(mpc.gen(native & is_online, PMAX));
    zonal.native_all_pmax_mw(z) = sum(mpc.gen(native, PMAX));
    zonal.total_online_pmax_mw(z) = sum(mpc.gen(gi & is_online, PMAX));
    zonal.total_all_pmax_mw(z) = sum(mpc.gen(gi, PMAX));
    zonal.native_q_dispatch_mvar(z) = sum(mpc.gen(native & is_online, QG));
end

total_load = sum(zonal.perform_load_mw);
total_native_dispatch = sum(zonal.native_dispatch_mw);
total_import_dispatch = sum(zonal.import_dispatch_mw);
total_dispatch = sum(zonal.total_dispatch_mw);
zonal.perform_load_share = zonal.perform_load_mw / total_load;
zonal.native_dispatch_share = zonal.native_dispatch_mw / total_native_dispatch;
zonal.native_all_pmax_share = zonal.native_all_pmax_mw / ...
    sum(zonal.native_all_pmax_mw);

fuel = build_fuel_table(mpc, gen_zone, gen_fuel, gen_type, is_online, zones);

mpopt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1);
[pf, pf_success] = runpf(mpc, mpopt);
pf_online = pf.gen(:, GEN_STATUS) > 0;
pf_losses = sum(pf.gen(pf_online, PG)) - sum(pf.bus(:, PD));
pf_pmax_violation = max([0; pf.gen(pf_online, PG) - pf.gen(pf_online, PMAX)]);
pf_pmin_violation = max([0; pf.gen(pf_online, PMIN) - pf.gen(pf_online, PG)]);
pf_qmax_violation = max([0; pf.gen(pf_online, QG) - pf.gen(pf_online, QMAX)]);
pf_qmin_violation = max([0; pf.gen(pf_online, QMIN) - pf.gen(pf_online, QG)]);
ref_bus_idx = find(pf.bus(:, BUS_TYPE) == REF, 1);
ref_bus_id = pf.bus(ref_bus_idx, BUS_I);
ref_gen_idx = find(pf.gen(:, GEN_BUS) == ref_bus_id & pf_online, 1);
ref_bus_name = bus_names(ref_bus_idx);
ref_gen_pg = pf.gen(ref_gen_idx, PG);
ref_gen_pmax = pf.gen(ref_gen_idx, PMAX);

pf_summary = table("PERFORM_2019_ON_PEAK_V23", logical(pf_success), ...
    size(mpc.bus, 1), size(mpc.gen, 1), size(mpc.branch, 1), ...
    total_load, sum(mpc.bus(:, QD)), total_native_dispatch, ...
    total_import_dispatch, total_dispatch, sum(pf.gen(pf_online, PG)), ...
    pf_losses, min(pf.bus(:, VM)), max(pf.bus(:, VM)), ...
    pf_pmax_violation, pf_pmin_violation, pf_qmax_violation, ...
    pf_qmin_violation, true, ref_bus_id, ref_bus_name, ref_gen_pg, ...
    ref_gen_pmax, nnz(~mapped), nnz(~gen_mapped), ...
    'VariableNames', {'case_name','pf_success','bus_count','gen_count', ...
    'branch_count','embedded_load_mw','embedded_load_mvar', ...
    'embedded_native_dispatch_mw','embedded_import_dispatch_mw', ...
    'embedded_total_dispatch_mw','pf_total_generation_mw','pf_losses_mw', ...
    'pf_min_voltage_pu','pf_max_voltage_pu','pf_max_pmax_violation_mw', ...
    'pf_max_pmin_violation_mw','pf_max_qmax_violation_mvar', ...
    'pf_max_qmin_violation_mvar','pf_q_limits_enforced','reference_bus_id', ...
    'reference_bus_name','reference_gen_pg_mw','reference_gen_pmax_mw', ...
    'unmapped_bus_count','unmapped_gen_count'});

cross_zone = build_cross_zone_table(pf, bus_zone, bus_names);
zone_pairs = build_zone_pair_summary(cross_zone);
corridors = build_corridor_table(pf, bus_zone, bus_names);
corridor_equivalents = build_corridor_equivalents(corridors);
load_comparison = build_load_comparison(zonal, target_dir);
generation_comparison = build_generation_comparison(zonal, target_dir);
retarget_pf = build_retarget_pf_results(mpc, bus_zone, gen_zone, gen_fuel, ...
    target_dir, pf_losses, total_load);

writetable(pf_summary, fullfile(output_dir, 'perform_pf_summary.csv'));
writetable(zonal, fullfile(output_dir, 'perform_zonal_snapshot.csv'));
writetable(fuel, fullfile(output_dir, 'perform_zonal_generation_by_fuel.csv'));
writetable(cross_zone, fullfile(output_dir, 'perform_cross_zone_branches.csv'));
writetable(zone_pairs, fullfile(output_dir, 'perform_zone_pair_summary.csv'));
writetable(corridors, fullfile(output_dir, 'perform_candidate_corridor_branches.csv'));
writetable(corridor_equivalents, ...
    fullfile(output_dir, 'perform_candidate_corridor_equivalents.csv'));
writetable(load_comparison, fullfile(output_dir, 'perform_vs_nyiso_load.csv'));
writetable(generation_comparison, ...
    fullfile(output_dir, 'perform_vs_goldbook_generation.csv'));
writetable(retarget_pf, ...
    fullfile(output_dir, 'perform_retarget_pf_scenarios.csv'));

outputs = struct('pf_summary', pf_summary, 'zonal', zonal, 'fuel', fuel, ...
    'cross_zone', cross_zone, 'zone_pairs', zone_pairs, ...
    'corridors', corridors, 'corridor_equivalents', corridor_equivalents, ...
    'load_comparison', load_comparison, ...
    'generation_comparison', generation_comparison, ...
    'retarget_pf', retarget_pf, ...
    'output_dir', output_dir);
end

function tbl = build_zone_pair_summary(branches)
from_code = double(char(branches.from_zone));
to_code = double(char(branches.to_zone));
pair_a = string(char(min(from_code, to_code)));
pair_b = string(char(max(from_code, to_code)));
pair = pair_a + "-" + pair_b;
pairs = unique(pair, 'stable');
tbl = table();
for k = 1:numel(pairs)
    idx = pair == pairs(k) & branches.status > 0;
    rows = branches(idx, :);
    sign_from_a = ones(height(rows), 1);
    sign_from_a(rows.from_zone ~= pair_a(find(idx, 1))) = -1;
    net_flow = sum(sign_from_a .* rows.pf_mw);
    row = table(pairs(k), pair_a(find(idx, 1)), pair_b(find(idx, 1)), ...
        height(rows), sum(rows.rate_a_mva), sum(abs(rows.pf_mw)), net_flow, ...
        max(rows.rate_a_loading_pct, [], 'omitnan'), ...
        'VariableNames', {'zone_pair','zone_a','zone_b','online_branch_count', ...
        'sum_rate_a_mva','sum_abs_pf_mw','net_flow_a_to_b_mw', ...
        'max_individual_loading_pct'});
    tbl = [tbl; row]; %#ok<AGROW>
end
end

function tbl = build_fuel_table(mpc, gen_zone, gen_fuel, gen_type, is_online, zones)
GEN_STATUS = 8; PG = 2; PMAX = 9;
tbl = table();
for z = 1:numel(zones)
    fuels = unique(gen_fuel(gen_zone == zones(z)), 'stable');
    for f = 1:numel(fuels)
        idx = gen_zone == zones(z) & gen_fuel == fuels(f);
        online = idx & is_online & mpc.gen(:, GEN_STATUS) > 0;
        row = table(zones(z), fuels(f), strjoin(unique(gen_type(idx)), '; '), ...
            nnz(idx), nnz(online), sum(mpc.gen(online, PG)), ...
            sum(mpc.gen(online, PMAX)), sum(mpc.gen(idx, PMAX)), ...
            'VariableNames', {'zone','fuel','generator_types','all_gen_count', ...
            'online_gen_count','online_dispatch_mw','online_pmax_mw','all_pmax_mw'});
        tbl = [tbl; row]; %#ok<AGROW>
    end
end
end

function tbl = build_cross_zone_table(pf, bus_zone, bus_names)
F_BUS = 1; T_BUS = 2; BR_R = 3; BR_X = 4; BR_B = 5;
RATE_A = 6; RATE_B = 7; RATE_C = 8; TAP = 9; SHIFT = 10;
BR_STATUS = 11; PF = 14; QF = 15; PT = 16; QT = 17; BASE_KV = 10;
[~, fi] = ismember(pf.branch(:, F_BUS), pf.bus(:, 1));
[~, ti] = ismember(pf.branch(:, T_BUS), pf.bus(:, 1));
valid = fi > 0 & ti > 0 & bus_zone(fi) ~= "" & bus_zone(ti) ~= "" & ...
    bus_zone(fi) ~= bus_zone(ti);
idx = find(valid);
from_zone = bus_zone(fi(idx));
to_zone = bus_zone(ti(idx));
from_bus = pf.branch(idx, F_BUS);
to_bus = pf.branch(idx, T_BUS);
from_name = bus_names(fi(idx));
to_name = bus_names(ti(idx));
from_kv = pf.bus(fi(idx), BASE_KV);
to_kv = pf.bus(ti(idx), BASE_KV);
br_r = pf.branch(idx, BR_R);
br_x = pf.branch(idx, BR_X);
br_b = pf.branch(idx, BR_B);
rate_a = pf.branch(idx, RATE_A);
rate_b = pf.branch(idx, RATE_B);
rate_c = pf.branch(idx, RATE_C);
tap = pf.branch(idx, TAP);
tap(tap == 0) = 1;
shift_deg = pf.branch(idx, SHIFT);
status = pf.branch(idx, BR_STATUS);
pf_mw = pf.branch(idx, PF);
qf_mvar = pf.branch(idx, QF);
pt_mw = pf.branch(idx, PT);
qt_mvar = pf.branch(idx, QT);
from_mva = hypot(pf_mw, qf_mvar);
to_mva = hypot(pt_mw, qt_mvar);
loading_pct = nan(size(rate_a));
rated = rate_a > 0;
loading_pct(rated) = 100 * max(from_mva(rated), to_mva(rated)) ./ rate_a(rated);
tbl = table(idx, from_zone, to_zone, from_bus, from_name, from_kv, ...
    to_bus, to_name, to_kv, br_r, br_x, br_b, rate_a, rate_b, rate_c, ...
    tap, shift_deg, status, pf_mw, qf_mvar, pt_mw, qt_mvar, from_mva, ...
    to_mva, loading_pct, 'VariableNames', {'branch_index','from_zone', ...
    'to_zone','from_bus','from_name','from_kv','to_bus','to_name','to_kv', ...
    'r_pu','x_pu','b_pu','rate_a_mva','rate_b_mva','rate_c_mva', ...
    'tap_ratio','shift_deg','status','pf_mw','qf_mvar','pt_mw','qt_mvar', ...
    'from_mva','to_mva','rate_a_loading_pct'});
end

function tbl = build_corridor_table(pf, bus_zone, bus_names)
corridor_name = ["EDIC_GILBOA"; "GILBOA_LEEDS"; ...
    "PLEASANT_VALLEY_WOOD_STREET"; "WOOD_STREET_MILLWOOD"; ...
    "MILLWOOD_DUNWOODIE"; "BUCHANAN_DUNWOODIE"; ...
    "RAMAPO_PLEASANT_VALLEY"; "EAST_GARDEN_CITY_NORTHPORT"];
from_pattern = ["EDIC"; "GILBOA"; "PLEASANT VALLEY"; "WOOD STREET"; ...
    "MILLWOOD"; "BUCHANAN"; "RAMAPO"; "EAST GARDEN CITY"];
to_pattern = ["GILBOA"; "LEEDS"; "WOOD STREET"; "MILLWOOD"; ...
    "DUNWOODIE"; "DUNWOODIE"; "PLEASANT VALLEY"; "NORTHPORT"];
cross = build_all_branch_table(pf, bus_zone, bus_names);
tbl = table();
for k = 1:numel(corridor_name)
    direct = (contains(upper(cross.from_name), from_pattern(k)) & ...
        contains(upper(cross.to_name), to_pattern(k))) | ...
        (contains(upper(cross.from_name), to_pattern(k)) & ...
        contains(upper(cross.to_name), from_pattern(k)));
    rows = cross(direct, :);
    if isempty(rows)
        row = cross(1, :);
        row.branch_index = NaN;
        row.from_zone = "";
        row.to_zone = "";
        row.from_bus = NaN;
        row.from_name = "";
        row.to_bus = NaN;
        row.to_name = "";
        numeric_names = {'r_pu','x_pu','b_pu','rate_a_mva','rate_b_mva', ...
            'rate_c_mva','tap_ratio','shift_deg','status','pf_mw','qf_mvar', ...
            'pt_mw','qt_mvar'};
        for n = 1:numel(numeric_names)
            row.(numeric_names{n}) = NaN;
        end
        row = addvars(row, corridor_name(k), false, 'Before', 1, ...
            'NewVariableNames', {'corridor_name','direct_match'});
        tbl = [tbl; row]; %#ok<AGROW>
    else
        rows = addvars(rows, repmat(corridor_name(k), height(rows), 1), ...
            true(height(rows), 1), 'Before', 1, ...
            'NewVariableNames', {'corridor_name','direct_match'});
        tbl = [tbl; rows]; %#ok<AGROW>
    end
end
end


function tbl = build_corridor_equivalents(corridors)
names = unique(corridors.corridor_name, 'stable');
tbl = table();
for k = 1:numel(names)
    rows = corridors(corridors.corridor_name == names(k) & ...
        corridors.direct_match & corridors.status > 0, :);
    if isempty(rows)
        row = table(names(k), false, 0, NaN, NaN, NaN, NaN, NaN, NaN, ...
            'VariableNames', {'corridor_name','direct_match','circuit_count', ...
            'parallel_r_eq_pu','parallel_x_eq_pu','sum_b_pu', ...
            'sum_rate_a_mva','sum_rate_b_mva','sum_rate_c_mva'});
    else
        y = sum(1 ./ complex(rows.r_pu, rows.x_pu));
        z = 1 / y;
        row = table(names(k), true, height(rows), real(z), imag(z), ...
            sum(rows.b_pu), sum(rows.rate_a_mva), sum(rows.rate_b_mva), ...
            sum(rows.rate_c_mva), 'VariableNames', ...
            {'corridor_name','direct_match','circuit_count', ...
            'parallel_r_eq_pu','parallel_x_eq_pu','sum_b_pu', ...
            'sum_rate_a_mva','sum_rate_b_mva','sum_rate_c_mva'});
    end
    tbl = [tbl; row]; %#ok<AGROW>
end
end

function tbl = build_all_branch_table(pf, bus_zone, bus_names)
F_BUS = 1; T_BUS = 2; BR_R = 3; BR_X = 4; BR_B = 5;
RATE_A = 6; RATE_B = 7; RATE_C = 8; TAP = 9; SHIFT = 10;
BR_STATUS = 11; PF = 14; QF = 15; PT = 16; QT = 17;
[~, fi] = ismember(pf.branch(:, F_BUS), pf.bus(:, 1));
[~, ti] = ismember(pf.branch(:, T_BUS), pf.bus(:, 1));
valid = fi > 0 & ti > 0;
idx = find(valid);
tap = pf.branch(idx, TAP); tap(tap == 0) = 1;
tbl = table(idx, bus_zone(fi(idx)), bus_zone(ti(idx)), ...
    pf.branch(idx, F_BUS), bus_names(fi(idx)), pf.branch(idx, T_BUS), ...
    bus_names(ti(idx)), pf.branch(idx, BR_R), pf.branch(idx, BR_X), ...
    pf.branch(idx, BR_B), pf.branch(idx, RATE_A), pf.branch(idx, RATE_B), ...
    pf.branch(idx, RATE_C), tap, pf.branch(idx, SHIFT), ...
    pf.branch(idx, BR_STATUS), pf.branch(idx, PF), pf.branch(idx, QF), ...
    pf.branch(idx, PT), pf.branch(idx, QT), 'VariableNames', ...
    {'branch_index','from_zone','to_zone','from_bus','from_name','to_bus', ...
    'to_name','r_pu','x_pu','b_pu','rate_a_mva','rate_b_mva','rate_c_mva', ...
    'tap_ratio','shift_deg','status','pf_mw','qf_mvar','pt_mw','qt_mvar'});
end

function tbl = build_load_comparison(zonal, target_dir)
targets = readtable(fullfile(target_dir, 'ny_zonal_load_targets.csv'), ...
    'TextType', 'string');
mask = contains(targets.scenario_id, '_2019_') & isfinite(targets.nyiso_load_mw);
targets = targets(mask, :);
scenario_ids = unique(targets.scenario_id, 'stable');
tbl = table();
for s = 1:numel(scenario_ids)
    rows = targets(targets.scenario_id == scenario_ids(s), :);
    ny_total = sum(rows.nyiso_load_mw);
    for z = 1:height(zonal)
        tr = rows(rows.nyiso_zone_letter == zonal.zone(z), :);
        if isempty(tr), continue; end
        ny_load = tr.nyiso_load_mw(1);
        ny_share = ny_load / ny_total;
        matched_nyiso_mw = sum(zonal.perform_load_mw) * ny_share;
        row = table(scenario_ids(s), tr.timestamp(1), zonal.zone(z), ...
            zonal.zone_name(z), zonal.perform_load_mw(z), ...
            zonal.perform_load_share(z), ny_load, ny_share, ...
            zonal.perform_load_share(z) - ny_share, ...
            matched_nyiso_mw, zonal.perform_load_mw(z) - matched_nyiso_mw, ...
            'VariableNames', {'scenario_id','timestamp','zone','zone_name', ...
            'perform_load_mw','perform_load_share','nyiso_actual_load_mw', ...
            'nyiso_actual_load_share','share_difference','nyiso_scaled_to_perform_mw', ...
            'perform_minus_scaled_nyiso_mw'});
        tbl = [tbl; row]; %#ok<AGROW>
    end
end
end

function tbl = build_generation_comparison(zonal, target_dir)
gold = readtable(fullfile(target_dir, 'nyiso_generator_capability_targets.csv'), ...
    'TextType', 'string');
[found, loc] = ismember(zonal.zone, gold.zone);
if ~all(found)
    error('Gold Book target table does not cover all A-K zones.');
end
gold = gold(loc, :);
capability_ratio = zonal.native_all_pmax_mw ./ gold.nyiso_summer_capability_mw;
capability_ratio(gold.nyiso_summer_capability_mw <= 0) = NaN;
tbl = table(zonal.zone, zonal.zone_name, zonal.native_dispatch_mw, ...
    zonal.import_dispatch_mw, zonal.native_online_pmax_mw, ...
    zonal.native_all_pmax_mw, gold.nyiso_summer_capability_mw, ...
    zonal.native_all_pmax_mw - gold.nyiso_summer_capability_mw, ...
    capability_ratio, ...
    zonal.native_dispatch_share, zonal.native_all_pmax_share, gold.nyiso_share, ...
    'VariableNames', {'zone','zone_name','perform_native_dispatch_mw', ...
    'perform_import_dispatch_mw','perform_native_online_pmax_mw', ...
    'perform_native_all_pmax_mw','goldbook_2025_summer_capability_mw', ...
    'perform_minus_goldbook_capability_mw','perform_to_goldbook_capability_ratio', ...
    'perform_native_dispatch_share','perform_native_pmax_share', ...
    'goldbook_capability_share'});
end

function tbl = build_retarget_pf_results(mpc, bus_zone, ~, gen_fuel, ...
        target_dir, baseline_losses, baseline_load)
PD = 3; BUS_I = 1; VM = 8; VMAX = 12; VMIN = 13;
PG = 2; PMAX = 9; PMIN = 10; GEN_STATUS = 8; GEN_BUS = 1;
PF = 14; QF = 15; PT = 16; QT = 17; RATE_A = 6; REF = 3; BUS_TYPE = 2;

targets = readtable(fullfile(target_dir, 'ny_zonal_load_targets.csv'), ...
    'TextType', 'string');
mask = contains(targets.scenario_id, '_2019_') & isfinite(targets.nyiso_load_mw);
targets = targets(mask, :);
scenario_ids = unique(targets.scenario_id, 'stable');

online = mpc.gen(:, GEN_STATUS) > 0;
native = ~ismember(gen_fuel, ["import", "reference"]);
native_online = native & online;
fixed_import_pg = sum(mpc.gen(~native & online, PG));
native_min = sum(mpc.gen(native_online, PMIN));
native_max = sum(mpc.gen(native_online, PMAX));
ref_bus = mpc.bus(mpc.bus(:, BUS_TYPE) == REF, BUS_I);
ref_gen = find(mpc.gen(:, GEN_BUS) == ref_bus & online, 1);
mpopt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1);
tbl = table();

for s = 1:numel(scenario_ids)
    rows = targets(targets.scenario_id == scenario_ids(s), :);
    trial = mpc;
    for k = 1:height(rows)
        zone = rows.nyiso_zone_letter(k);
        bi = bus_zone == zone;
        old_total = sum(mpc.bus(bi, PD));
        if old_total <= 0
            error('PERFORM zone %s has no positive active load for redistribution.', zone);
        end
        trial.bus(bi, PD) = mpc.bus(bi, PD) * rows.nyiso_load_mw(k) / old_total;
    end

    target_load = sum(trial.bus(:, PD));
    loss_estimate = baseline_losses * target_load / baseline_load;
    target_native = target_load + loss_estimate - fixed_import_pg;
    allocatable = target_native >= native_min - 1e-7 && ...
        target_native <= native_max + 1e-7;
    success = false;
    min_v = NaN; max_v = NaN; losses = NaN; slack_pg = NaN;
    max_nonref_p_violation = NaN; branch_overload_count = NaN;
    max_branch_overload_mva = NaN; voltage_bound_count = NaN;
    status = "not_run_dispatch_outside_online_limits";

    if allocatable
        trial.gen(native_online, PG) = project_total(target_native, ...
            trial.gen(native_online, PMIN), trial.gen(native_online, PMAX), ...
            trial.gen(native_online, PG));
        trial.gen(ref_gen, PG) = mpc.gen(ref_gen, PG);
        try
            [result, success] = runpf(trial, mpopt);
            status = "pf_failed";
            if success
                status = "ok";
                on = result.gen(:, GEN_STATUS) > 0;
                min_v = min(result.bus(:, VM));
                max_v = max(result.bus(:, VM));
                losses = sum(result.gen(on, PG)) - sum(result.bus(:, PD));
                slack_pg = result.gen(ref_gen, PG);
                nonref = on;
                nonref(ref_gen) = false;
                max_nonref_p_violation = max([0; ...
                    result.gen(nonref, PG) - result.gen(nonref, PMAX); ...
                    result.gen(nonref, PMIN) - result.gen(nonref, PG)]);
                rated = result.branch(:, RATE_A) > 0 & result.branch(:, 11) > 0;
                mva = max(hypot(result.branch(:, PF), result.branch(:, QF)), ...
                    hypot(result.branch(:, PT), result.branch(:, QT)));
                overload = zeros(size(mva));
                overload(rated) = mva(rated) - result.branch(rated, RATE_A);
                branch_overload_count = nnz(overload > 1e-6);
                max_branch_overload_mva = max([0; overload]);
                voltage_bound_count = nnz(result.bus(:, VM) >= ...
                    result.bus(:, VMAX) - 1e-5 | result.bus(:, VM) <= ...
                    result.bus(:, VMIN) + 1e-5);
            end
        catch ME
            status = "error:" + string(ME.identifier);
        end
    end

    row = table(scenario_ids(s), rows.timestamp(1), target_load, ...
        loss_estimate, fixed_import_pg, target_native, native_min, native_max, ...
        allocatable, logical(success), status, min_v, max_v, losses, slack_pg, ...
        max_nonref_p_violation, branch_overload_count, max_branch_overload_mva, ...
        voltage_bound_count, ...
        'VariableNames', {'scenario_id','timestamp','target_load_mw', ...
        'estimated_losses_mw','fixed_import_reference_pg_mw', ...
        'target_native_generation_mw','online_native_pmin_mw', ...
        'online_native_pmax_mw','dispatch_allocatable','pf_success','status', ...
        'min_voltage_pu','max_voltage_pu','pf_losses_mw','reference_gen_pg_mw', ...
        'max_nonreference_p_limit_violation_mw','branch_overload_count', ...
        'max_branch_overload_mva','voltage_bound_count'});
    tbl = [tbl; row]; %#ok<AGROW>
end
end

function pg = project_total(target, pmin, pmax, seed)
pmin = pmin(:); pmax = pmax(:); seed = seed(:);
if target < sum(pmin) - 1e-7 || target > sum(pmax) + 1e-7
    error('Target generation is outside aggregate online limits.');
end
pg = min(max(seed, pmin), pmax);
for iter = 1:200
    delta = target - sum(pg);
    if abs(delta) < 1e-7, break; end
    if delta > 0
        room = pmax - pg;
    else
        room = pg - pmin;
    end
    active = room > 1e-10;
    if ~any(active), break; end
    weights = room;
    weights(~active) = 0;
    weights = weights / sum(weights);
    step = delta * weights;
    if delta > 0
        step = min(step, room);
    else
        step = max(step, -room);
    end
    pg = pg + step;
end
if abs(target - sum(pg)) > 1e-5
    error('Could not allocate aggregate generation target.');
end
end
