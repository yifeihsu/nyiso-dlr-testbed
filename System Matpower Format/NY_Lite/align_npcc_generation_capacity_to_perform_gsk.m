function [mpc, report] = align_npcc_generation_capacity_to_perform_gsk(mpc, gsk)
%ALIGN_NPCC_GENERATION_CAPACITY_TO_PERFORM_GSK Repartition zonal PMAX.
%   Preserves each zone's aggregate online PMAX while reallocating effective
%   bus participation capability according to PERFORM bus weights.

if nargin < 2 || isempty(gsk)
    gsk = build_perform_npcc_generation_shift_keys(mpc);
end
define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
[mapped, bi] = ismember(mpc.gen(:, GEN_BUS), mpc.bus(:, BUS_I));
gen_zone = strings(size(mpc.gen, 1), 1);
gen_zone(mapped) = string(mpc.userdata.nyiso_physical_zone(bi(mapped)));
online = mpc.gen(:, GEN_STATUS) > 0;
report = table();

zones = unique(gsk.zone, 'stable');
for z = 1:numel(zones)
    zone = zones(z);
    rows = gsk(gsk.zone == zone, :);
    zone_gen = find(online & gen_zone == zone);
    if isempty(zone_gen), continue; end
    old_zone_pmax = sum(mpc.gen(zone_gen, PMAX));
    for k = 1:height(rows)
        bus_id = rows.npcc_bus_id(k);
        gi = zone_gen(mpc.gen(zone_gen, GEN_BUS) == bus_id);
        if isempty(gi)
            error('Mapped bus %.0f in zone %s has no online generator.', bus_id, zone);
        end
        old_bus_pmax = sum(mpc.gen(gi, PMAX));
        new_bus_pmax = old_zone_pmax * rows.perform_bus_weight(k);
        if old_bus_pmax > 0
            shares = mpc.gen(gi, PMAX) / old_bus_pmax;
        else
            shares = ones(numel(gi), 1) / numel(gi);
        end
        mpc.gen(gi, PMAX) = new_bus_pmax * shares;
        mpc.gen(gi, PMIN) = min(mpc.gen(gi, PMIN), mpc.gen(gi, PMAX));
        mpc.gen(gi, PG) = min(max(mpc.gen(gi, PG), mpc.gen(gi, PMIN)), ...
            mpc.gen(gi, PMAX));
        row = table(zone, bus_id, rows.npcc_bus_name(k), ...
            rows.perform_bus_weight(k), old_zone_pmax, old_bus_pmax, ...
            new_bus_pmax, new_bus_pmax - old_bus_pmax, ...
            rows.source_rule(k), rows.confidence(k), ...
            'VariableNames', {'zone','npcc_bus_id','npcc_bus_name', ...
            'perform_bus_weight','preserved_zone_pmax_mw','old_bus_pmax_mw', ...
            'new_bus_pmax_mw','bus_pmax_change_mw','source_rule','confidence'});
        if isempty(report), report = row; else, report = [report; row]; end %#ok<AGROW>
    end
    new_total = sum(mpc.gen(zone_gen, PMAX));
    if abs(new_total - old_zone_pmax) > 1e-6
        error('Zone %s PMAX was not preserved.', zone);
    end
end
mpc.userdata.ny_lite.perform_capacity_alignment_report = report;
mpc.userdata.ny_lite.perform_capacity_alignment_note = ...
    'Effective bus PMAX repartitioned by PERFORM GSK; zonal PMAX preserved.';
end
