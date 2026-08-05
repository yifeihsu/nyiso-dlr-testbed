function [mpc, report] = apply_perform_generation_allocation( ...
        mpc, zonal_totals, gsk, options)
%APPLY_PERFORM_GENERATION_ALLOCATION Apply PERFORM bus weights to zonal PG.

if nargin < 3 || isempty(gsk)
    gsk = build_perform_npcc_generation_shift_keys(mpc);
end
if nargin < 4, options = struct(); end
if ~isfield(options, 'exclude_gen_idx'), options.exclude_gen_idx = []; end
define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
zonal_totals = normalize_zonal_totals(zonal_totals);
report = table();

[gen_mapped, gen_bus_idx] = ismember(mpc.gen(:, GEN_BUS), mpc.bus(:, BUS_I));
gen_zone = strings(size(mpc.gen, 1), 1);
gen_zone(gen_mapped) = string(mpc.userdata.nyiso_physical_zone(gen_bus_idx(gen_mapped)));
ny_online = mpc.gen(:, GEN_STATUS) > 0 & gen_zone ~= "";
exclude = unique(options.exclude_gen_idx(:));
exclude = exclude(exclude >= 1 & exclude <= size(mpc.gen, 1));
ny_online(exclude) = false;
mpc.gen(ny_online, PG) = 0;

for z = 1:height(zonal_totals)
    zone = zonal_totals.zone(z);
    target = zonal_totals.target_generation_mw(z);
    rows = gsk(gsk.zone == zone, :);
    zone_gen = find(ny_online & gen_zone == zone);
    if isempty(rows)
        if target > 1e-7
            error('No PERFORM shift-key mapping for non-zero zone %s target %.3f MW.', ...
                zone, target);
        end
        continue;
    end
    bus_ids = rows.npcc_bus_id;
    ideal = target * rows.perform_bus_weight;
    bus_pmin = zeros(height(rows), 1);
    bus_pmax = zeros(height(rows), 1);
    for k = 1:height(rows)
        gi = zone_gen(mpc.gen(zone_gen, GEN_BUS) == bus_ids(k));
        if isempty(gi)
            error('Mapped bus %.0f in zone %s has no online generator.', bus_ids(k), zone);
        end
        bus_pmin(k) = sum(mpc.gen(gi, PMIN));
        bus_pmax(k) = sum(mpc.gen(gi, PMAX));
    end
    applied = project_vector_total(target, bus_pmin, bus_pmax, ideal);
    for k = 1:height(rows)
        gi = zone_gen(mpc.gen(zone_gen, GEN_BUS) == bus_ids(k));
        pg = project_unit_total(applied(k), mpc.gen(gi, PMIN), ...
            mpc.gen(gi, PMAX), mpc.gen(gi, PMAX));
        mpc.gen(gi, PG) = pg;
        row = table(zone, bus_ids(k), rows.npcc_bus_name(k), target, ...
            rows.perform_bus_weight(k), ideal(k), applied(k), ...
            applied(k) - ideal(k), bus_pmin(k), bus_pmax(k), ...
            rows.source_rule(k), rows.confidence(k), ...
            'VariableNames', {'zone','npcc_bus_id','npcc_bus_name', ...
            'zone_target_generation_mw','perform_bus_weight','ideal_bus_pg_mw', ...
            'applied_bus_pg_mw','capacity_redispatch_mw','bus_pmin_mw', ...
            'bus_pmax_mw','source_rule','confidence'});
        if isempty(report), report = row; else, report = [report; row]; end %#ok<AGROW>
    end
end
mpc.userdata.ny_lite.perform_generation_allocation_report = report;
end

function tbl = normalize_zonal_totals(input)
if ~istable(input)
    error('zonal_totals must be a table.');
end
names = input.Properties.VariableNames;
zc = find(strcmpi(names, 'zone'), 1);
gc = find(strcmpi(names, 'target_generation_mw') | ...
    strcmpi(names, 'generation_mw') | strcmpi(names, 'pg_mw'), 1);
if isempty(zc) || isempty(gc)
    error('zonal_totals requires zone and target_generation_mw columns.');
end
tbl = table(upper(string(input{:, zc})), double(input{:, gc}), ...
    'VariableNames', {'zone','target_generation_mw'});
if any(~isfinite(tbl.target_generation_mw)) || any(tbl.target_generation_mw < -1e-7)
    error('Zonal generation targets must be finite and nonnegative.');
end
end

function x = project_vector_total(target, lower, upper, seed)
lower = lower(:); upper = upper(:); seed = seed(:);
if target < sum(lower) - 1e-6 || target > sum(upper) + 1e-6
    error('Zone target %.3f MW is outside aggregate bus limits [%.3f, %.3f].', ...
        target, sum(lower), sum(upper));
end
x = min(max(seed, lower), upper);
for iter = 1:200
    delta = target - sum(x);
    if abs(delta) < 1e-8, break; end
    if delta > 0, room = upper - x; else, room = x - lower; end
    active = room > 1e-10;
    if ~any(active), break; end
    weights = room;
    weights(~active) = 0;
    weights = weights / sum(weights);
    step = delta * weights;
    if delta > 0, step = min(step, room); else, step = max(step, -room); end
    x = x + step;
end
if abs(target - sum(x)) > 1e-5
    error('Could not project zonal target onto mapped NPCC buses.');
end
end

function pg = project_unit_total(target, pmin, pmax, seed)
pmin = pmin(:); pmax = pmax(:); seed = seed(:);
pg = project_vector_total(target, pmin, pmax, seed * target / max(sum(seed), eps));
end
