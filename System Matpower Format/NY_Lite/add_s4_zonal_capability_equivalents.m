function [mpc, report] = add_s4_zonal_capability_equivalents(mpc, options)
%ADD_S4_ZONAL_CAPABILITY_EQUIVALENTS Add S4 zonal capability equivalents.
%
%   S4 keeps the S3 Zone-J active-supply equivalent and adds bounded
%   aggregate active-power equivalents in zones E/F/G/K. These devices are
%   capability-alignment proxies, not unit-level generator models.

if nargin < 2, options = struct(); end
if ~isfield(options, 'include_zone_j'), options.include_zone_j = true; end
if ~isfield(options, 'zone_j_total_pmax_mw'), options.zone_j_total_pmax_mw = 3000; end
if ~isfield(options, 'zone_j_cost_c1'), options.zone_j_cost_c1 = 250; end
if ~isfield(options, 'zone_j_cost_c2'), options.zone_j_cost_c2 = 0.02; end
if ~isfield(options, 'equiv_cost_c1'), options.equiv_cost_c1 = 180; end
if ~isfield(options, 'equiv_cost_c2'), options.equiv_cost_c2 = 0.02; end
if ~isfield(options, 'q_abs_ratio'), options.q_abs_ratio = 0; end
if ~isfield(options, 'on_existing'), options.on_existing = 'skip'; end
if ~isfield(options, 'apply_upstate_participation_caps'), options.apply_upstate_participation_caps = false; end
if ~isfield(options, 'abc_cap_factor'), options.abc_cap_factor = 1.0; end
if ~isfield(options, 'reclassify_ce_ug'), options.reclassify_ce_ug = true; end
if ~isfield(options, 'ce_ug_cost_c1'), options.ce_ug_cost_c1 = 500; end
if ~isfield(options, 'ce_ug_cost_c2'), options.ce_ug_cost_c2 = 0.5; end

define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
mpc = ensure_gencost(mpc);
if ~isfield(mpc, 'userdata'), mpc.userdata = struct(); end
if ~isfield(mpc.userdata, 'ny_lite'), mpc.userdata.ny_lite = struct(); end
if ~isfield(mpc.userdata.ny_lite, 's4_zonal_capability_equivalents')
    mpc.userdata.ny_lite.s4_zonal_capability_equivalents = struct([]);
end

report = table();
if options.include_zone_j
    [mpc, zone_j_report] = add_zone_j_equivalent_supply(mpc, ...
        struct('total_pmax_mw', options.zone_j_total_pmax_mw, ...
        'q_abs_ratio', options.q_abs_ratio, ...
        'cost_c1', options.zone_j_cost_c1, ...
        'cost_c2', options.zone_j_cost_c2, ...
        'on_existing', options.on_existing));
    if ~isempty(zone_j_report)
        zone_j_report.model_stage = repmat("S3_ZONE_J_RETAINED", height(zone_j_report), 1);
        zone_j_report.action = repmat("keep_zone_j_equivalent", height(zone_j_report), 1);
        report = append_report(report, normalize_zone_j_report(zone_j_report));
    end
end

specs = default_specs();
existing = mpc.userdata.ny_lite.s4_zonal_capability_equivalents;
existing_names = {};
if ~isempty(existing) && isfield(existing, 'name')
    existing_names = {existing.name};
end

for k = 1:numel(specs)
    s = specs(k);
    old = find(strcmp(existing_names, s.name), 1);
    if ~isempty(old)
        if strcmpi(options.on_existing, 'error')
            error('add_s4_zonal_capability_equivalents:AlreadyExists', ...
                'S4 equivalent %s already exists.', s.name);
        elseif strcmpi(options.on_existing, 'update')
            gi = existing(old).gen_index;
        else
            continue;
        end
    else
        gi = size(mpc.gen, 1) + 1;
        mpc.gen(gi, 1:max(21, size(mpc.gen, 2))) = 0;
        mpc.gencost(gi, 1:size(mpc.gencost, 2)) = 0;
    end

    bus_idx = find(mpc.bus(:, BUS_I) == s.bus_id, 1);
    if isempty(bus_idx)
        error('add_s4_zonal_capability_equivalents:MissingBus', ...
            'S4 equivalent bus %.0f (%s) is missing.', s.bus_id, s.bus_name);
    end

    qmax = options.q_abs_ratio * s.pmax_mw;
    qmin = -qmax;
    vg = mpc.bus(bus_idx, VM);
    mpc.gen(gi, [GEN_BUS PG QG QMAX QMIN VG MBASE GEN_STATUS PMAX PMIN]) = ...
        [s.bus_id 0 0 qmax qmin vg mpc.baseMVA 1 s.pmax_mw 0];
    mpc.gencost(gi, 1:7) = [2 0 0 3 options.equiv_cost_c2 options.equiv_cost_c1 0];

    rec = struct('name', s.name, 'model_stage', 'S4_GENERATION_ALIGNMENT', ...
        'action', 'add_equivalent', 'bus_id', s.bus_id, ...
        'bus_name', s.bus_name, 'zone', s.zone, ...
        'proxy_interpretation', s.proxy_interpretation, ...
        'gen_index', gi, 'pmax_mw', s.pmax_mw, ...
        'qmin_mvar', qmin, 'qmax_mvar', qmax, ...
        'cost_c2', options.equiv_cost_c2, 'cost_c1', options.equiv_cost_c1);
    if isempty(old)
        existing = append_struct(existing, rec);
        existing_names{end + 1} = s.name; %#ok<AGROW>
    else
        existing(old) = rec;
    end
    report = append_report(report, struct2table(rec, 'AsArray', true));
end

mpc.userdata.ny_lite.s4_zonal_capability_equivalents = existing;
mpc.userdata.ny_lite.s4_generation_alignment_note = ...
    'S4 adds bounded zonal active-power capability equivalents; not unit-level generation.';

if options.reclassify_ce_ug
    [mpc, ce_report] = reclassify_ce_ug(mpc, options);
    mpc.userdata.ny_lite.s4_ce_ug_reclassification = ce_report;
end
if options.apply_upstate_participation_caps
    [mpc, cap_report] = apply_upstate_caps(mpc, options.abc_cap_factor);
    mpc.userdata.ny_lite.s4_upstate_participation_caps = cap_report;
end
end

function specs = default_specs()
specs = struct( ...
    'name', { ...
        'EDIC_E_EQ_SUPPLY', 'PORTER_E_EQ_SUPPLY', ...
        'GILBOA_F_EQ_SUPPLY', 'ALBANY_F_EQ_SUPPLY', ...
        'ROTTERDAM_F_EQ_SUPPLY', 'NEW_SCOTLAND_F_EQ_SUPPLY', ...
        'PLEASANT_VLY_G_EQ_SUPPLY', 'RAMAPO_G_EQ_SUPPLY', ...
        'LEEDS_G_EQ_SUPPLY', ...
        'NORTHPORT_K_EQ_SUPPLY', 'EAST_GARDEN_CITY_K_EQ_SUPPLY'}, ...
    'bus_id', {43, 44, 38, 42, 41, 37, 73, 76, 39, 80, 9003}, ...
    'bus_name', {'EDIC', 'PORTER', 'GILBOA', 'ALBANY', ...
        'ROTTERDAM', 'NEW SEATHED', 'PLEASANT VLY', 'RAMAPO', ...
        'LEEDS', 'NORTHPORT', 'EAST GARDEN CITY'}, ...
    'zone', {'E', 'E', 'F', 'F', 'F', 'F', 'G', 'G', 'G', 'K', 'K'}, ...
    'pmax_mw', {400, 200, 500, 500, 300, 300, 900, 700, 600, 1200, 600}, ...
    'proxy_interpretation', { ...
        'Mohawk Valley / Edic aggregate capability', ...
        'Mohawk Valley / Porter aggregate capability', ...
        'Capital-region / Gilboa aggregate capability', ...
        'Capital-region / Albany aggregate capability', ...
        'Capital-region / Rotterdam aggregate capability', ...
        'Capital-region / New Scotland aggregate capability', ...
        'Hudson Valley / Pleasant Valley aggregate capability', ...
        'Hudson Valley / Ramapo aggregate capability', ...
        'Hudson Valley / Leeds aggregate capability', ...
        'Long Island / Northport aggregate capability', ...
        'Long Island / East Garden City import-equivalent capability'});
end

function [mpc, report] = reclassify_ce_ug(mpc, options)
define_constants;
report = table();
idx = find(mpc.gen(:, GEN_BUS) == 78 & mpc.gen(:, PMAX) > 100);
for k = 1:numel(idx)
    gi = idx(k);
    old_c1 = NaN; old_c2 = NaN;
    if size(mpc.gencost, 1) >= gi && size(mpc.gencost, 2) >= 6
        old_c2 = mpc.gencost(gi, 5);
        old_c1 = mpc.gencost(gi, 6);
    end
    mpc.gencost(gi, 1:7) = [2 0 0 3 options.ce_ug_cost_c2 options.ce_ug_cost_c1 0];
    row = table(gi, mpc.gen(gi, PMAX), old_c2, old_c1, ...
        options.ce_ug_cost_c2, options.ce_ug_cost_c1, ...
        "reclassify_as_interface_import_or_voltage_support", ...
        'VariableNames', {'gen_index','pmax_mw','old_cost_c2','old_cost_c1', ...
        'new_cost_c2','new_cost_c1','action'});
    report = append_report(report, row);
end
end

function [mpc, report] = apply_upstate_caps(mpc, cap_factor)
define_constants;
if nargin < 2 || isempty(cap_factor), cap_factor = 1.0; end
targets = struct('zone', {'A', 'B', 'C'}, ...
    'target_pmax_mw', {1616, 361, 3139});
exclude = excluded_generator_indices(mpc);
report = table();
for k = 1:numel(targets)
    zone = targets(k).zone;
    bus_ids = buses_in_zone(mpc, zone);
    idx = find(ismember(mpc.gen(:, GEN_BUS), bus_ids) & ...
        mpc.gen(:, GEN_STATUS) > 0 & ~ismember((1:size(mpc.gen, 1))', exclude));
    old_total = sum(mpc.gen(idx, PMAX));
    target = targets(k).target_pmax_mw * cap_factor;
    if old_total > target && old_total > 0
        scale = target / old_total;
        mpc.gen(idx, PMAX) = mpc.gen(idx, PMAX) * scale;
        mpc.gen(idx, PG) = min(mpc.gen(idx, PG), mpc.gen(idx, PMAX));
    else
        scale = 1;
    end
    new_total = sum(mpc.gen(idx, PMAX));
    row = table(string(zone), numel(idx), old_total, targets(k).target_pmax_mw, ...
        cap_factor, target, scale, new_total, ...
        'VariableNames', {'zone','generator_count','old_pmax_mw', ...
        'base_target_pmax_mw','cap_factor','target_pmax_mw', ...
        'scale_factor','new_pmax_mw'});
    report = append_report(report, row);
end
end

function bus_ids = buses_in_zone(mpc, zone)
zone = char(zone);
bus_ids = [];
for i = 1:size(mpc.bus, 1)
    if isfield(mpc.userdata, 'nyiso_physical_zone') && ...
            numel(mpc.userdata.nyiso_physical_zone) >= i && ...
            strcmp(mpc.userdata.nyiso_physical_zone{i}, zone)
        bus_ids(end + 1) = mpc.bus(i, 1); %#ok<AGROW>
    end
end
end

function exclude = excluded_generator_indices(mpc)
exclude = [];
if isfield(mpc, 'userdata') && isfield(mpc.userdata, 'ny_only_equivalent') && ...
        isfield(mpc.userdata.ny_only_equivalent, 'external_equivalent_generators')
    tbl = mpc.userdata.ny_only_equivalent.external_equivalent_generators;
    if istable(tbl) && ismember('added_gen_index', tbl.Properties.VariableNames)
        exclude = [exclude; tbl.added_gen_index(:)];
    end
end
if isfield(mpc, 'userdata') && isfield(mpc.userdata, 'ny_lite')
    if isfield(mpc.userdata.ny_lite, 'zone_j_equivalent_supply')
        d = mpc.userdata.ny_lite.zone_j_equivalent_supply;
        if ~isempty(d) && isfield(d, 'gen_index'), exclude = [exclude; [d.gen_index]']; end
    end
    if isfield(mpc.userdata.ny_lite, 's4_zonal_capability_equivalents')
        d = mpc.userdata.ny_lite.s4_zonal_capability_equivalents;
        if ~isempty(d) && isfield(d, 'gen_index'), exclude = [exclude; [d.gen_index]']; end
    end
end
exclude = unique(exclude(isfinite(exclude)));
end

function mpc = ensure_gencost(mpc)
if ~isfield(mpc, 'gencost') || isempty(mpc.gencost)
    mpc.gencost = zeros(size(mpc.gen, 1), 7);
    mpc.gencost(:, 1) = 2;
    mpc.gencost(:, 4) = 3;
elseif size(mpc.gencost, 2) < 7
    mpc.gencost(:, end + 1:7) = 0;
end
end

function tbl = normalize_zone_j_report(tbl)
tbl.proxy_interpretation = string(tbl.proxy_interpretation);
tbl.model_stage = string(tbl.model_stage);
tbl.action = string(tbl.action);
tbl = tbl(:, {'name','model_stage','action','bus_id','bus_name','zone', ...
    'proxy_interpretation','gen_index','pmax_mw','qmin_mvar','qmax_mvar', ...
    'cost_c2','cost_c1'});
end

function out = append_struct(out, entry)
if isempty(out)
    out = entry;
else
    out(end + 1) = entry;
end
end

function out = append_report(out, row)
if isempty(out)
    out = row;
else
    out = [out; row]; %#ok<AGROW>
end
end
