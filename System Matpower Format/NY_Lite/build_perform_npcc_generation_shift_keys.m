function [gsk, plant_summary] = build_perform_npcc_generation_shift_keys(mpc, options)
%BUILD_PERFORM_NPCC_GENERATION_SHIFT_KEYS Map PERFORM dispatch to NPCC buses.
%   The output weights allocate a zonal generation total among retained
%   NPCC/NY-lite generator buses. Exact plant clusters are mapped directly;
%   the remaining PERFORM dispatch is assigned to documented zonal proxies.

if nargin < 1 || isempty(mpc)
    mpc = loadcase('npcc_ny_lite_s4_cost_calibration_candidate_v2');
elseif ischar(mpc) || isstring(mpc)
    mpc = loadcase(char(mpc));
end
if nargin < 2, options = struct(); end

helper_dir = fileparts(mfilename('fullpath'));
workspace_dir = fileparts(fileparts(helper_dir));
if ~isfield(options, 'perform_case_dir')
    options.perform_case_dir = fullfile(workspace_dir, 'PERFORM', ...
        'On Peak 2019 v23_Perform_NY', 'On Peak 2019 v23');
end
if ~isfield(options, 'perform_aux_dir')
    options.perform_aux_dir = fullfile(workspace_dir, 'PERFORM', ...
        'Auxilliary_Perform_NY');
end

define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
addpath(options.perform_case_dir);
perform = nyiso_On_Peak_v23_shunts_as_z_load;

cost_meta = readtable(fullfile(options.perform_case_dir, ...
    'GenCostTable4MATPOWERv23_ShuntsNotShown.csv'), ...
    'VariableNamingRule', 'preserve');
unit_meta = readtable(fullfile(options.perform_aux_dir, 'NYGenUCV4.xlsx'), ...
    'VariableNamingRule', 'preserve');
if height(cost_meta) ~= size(perform.gen, 1)
    error('PERFORM generator metadata row count does not match the MATPOWER case.');
end

perform_zone = perform_nyiso_zone_letters(perform, perform.bus(:, BUS_I));
[gen_mapped, gen_bus_idx] = ismember(perform.gen(:, GEN_BUS), perform.bus(:, BUS_I));
gen_zone = strings(size(perform.gen, 1), 1);
gen_zone(gen_mapped) = perform_zone(gen_bus_idx(gen_mapped));
gen_fuel = lower(strtrim(string(perform.genfuel(:))));
native_online = perform.gen(:, GEN_STATUS) > 0 & ...
    ~ismember(gen_fuel, ["import", "reference"]);

plant_name = map_plant_names(cost_meta, unit_meta);
[group_id, group_zone, group_plant] = findgroups(gen_zone(native_online), ...
    plant_name(native_online));
plant_pg = splitapply(@sum, perform.gen(native_online, PG), group_id);
plant_pmax = splitapply(@sum, perform.gen(native_online, PMAX), group_id);
plant_summary = table(group_zone, group_plant, plant_pg, plant_pmax, ...
    'VariableNames', {'zone','plant_name','perform_pg_mw','perform_pmax_mw'});
plant_summary = sortrows(plant_summary, {'zone','perform_pg_mw'}, {'ascend','descend'});

gsk = table();

% Zone A: preserve the Niagara hydro concentration; distribute remaining
% western generation over the retained Huntley/Dunkirk proxy buses.
a = zone_plants(plant_summary, "A");
niagara = select_pg(a, ["Robert Moses Niagara", "Lewiston Niagara"]);
gsk = append_split(gsk, mpc, "A", [54 55], niagara, ...
    "PERFORM Niagara hydro plants", "high");
gsk = append_split(gsk, mpc, "A", [56 57 60 61], sum(a.perform_pg_mw) - niagara, ...
    "Residual Zone-A plants allocated to Huntley/Dunkirk proxies", "medium");

% Zone B has one retained NPCC generator location.
b = zone_plants(plant_summary, "B");
gsk = append_split(gsk, mpc, "B", 53, sum(b.perform_pg_mw), ...
    "All PERFORM Zone-B generation at retained Rochester proxy", "medium");

% Zone C: retain the Oswego nuclear/thermal cluster at Clay and direct
% Greenidge/Binghamton matches; allocate the remainder to Hillside/Lapeer.
c = zone_plants(plant_summary, "C");
clay = select_pg(c, ["Nine Mile", "Fitzpatrick", "Independence", "Oswego"]);
greenidge = select_pg(c, "Greenidge");
binghamton = select_pg(c, "Binghamton");
residual_c = sum(c.perform_pg_mw) - clay - greenidge - binghamton;
gsk = append_split(gsk, mpc, "C", [50 51], clay, ...
    "PERFORM Nine Mile/Fitzpatrick/Independence/Oswego cluster", "high");
gsk = append_split(gsk, mpc, "C", 65, greenidge, ...
    "PERFORM Greenidge plant", "high");
gsk = append_split(gsk, mpc, "C", 71, binghamton, ...
    "PERFORM Binghamton plant", "high");
gsk = append_split(gsk, mpc, "C", [68 72], residual_c, ...
    "Residual Zone-C plants allocated to Hillside/Lapeer proxies", "medium");

% Zones D/E are retained as zonal proxies because the two models use
% different station/zone abstractions around Moses and Mohawk Valley.
d = zone_plants(plant_summary, "D");
gsk = append_split(gsk, mpc, "D", [47 48], sum(d.perform_pg_mw), ...
    "PERFORM Zone-D total allocated to Moses W/E proxies", "low");
e = zone_plants(plant_summary, "E");
gsk = append_split(gsk, mpc, "E", [43 44], sum(e.perform_pg_mw), ...
    "PERFORM Zone-E total allocated to Edic/Porter equivalents", "low");

% Zone F: direct Gilboa match, major Capital-region thermal cluster at
% Albany, Selkirk at Rotterdam, and remaining resources at New Scotland.
f = zone_plants(plant_summary, "F");
gilboa = select_pg(f, "Blenheim Gilboa");
albany = select_pg(f, ["Bethlehem Energy", "Empire Generating"]);
rotterdam = select_pg(f, "Selkirk");
residual_f = sum(f.perform_pg_mw) - gilboa - albany - rotterdam;
gsk = append_split(gsk, mpc, "F", 38, gilboa, ...
    "PERFORM Blenheim-Gilboa plant", "high");
gsk = append_split(gsk, mpc, "F", 42, albany, ...
    "PERFORM Bethlehem/Empire Capital-region cluster", "medium");
gsk = append_split(gsk, mpc, "F", 41, rotterdam, ...
    "PERFORM Selkirk cluster at Rotterdam proxy", "medium");
gsk = append_split(gsk, mpc, "F", 37, residual_f, ...
    "Residual Zone-F plants at New Scotland proxy", "medium");

% Zone G: group the detailed lower-Hudson fleet into the three retained
% Leeds, Pleasant Valley and Ramapo supply proxies.
g = zone_plants(plant_summary, "G");
leeds = select_pg(g, ["Athens", "South Cairo", "West Coxsackie"]);
pleasant = select_pg(g, ["Roseton", "CPV Valley"]);
ramapo = sum(g.perform_pg_mw) - leeds - pleasant;
gsk = append_split(gsk, mpc, "G", 39, leeds, ...
    "PERFORM Athens/South-Cairo/West-Coxsackie cluster", "medium");
gsk = append_split(gsk, mpc, "G", 73, pleasant, ...
    "PERFORM Roseton/CPV-Valley cluster", "medium");
gsk = append_split(gsk, mpc, "G", 76, ramapo, ...
    "Residual Zone-G plants at Ramapo proxy", "medium");

% Zone I has only the legacy CE UG proxy in NPCC; keep any non-zero S4
% zonal target there, while retaining its interface-equivalent label.
i = zone_plants(plant_summary, "I");
gsk = append_split(gsk, mpc, "I", 78, sum(i.perform_pg_mw), ...
    "PERFORM Zone-I residual at CE UG interface proxy", "low");

% Zone J: explicit Queens/Astoria, Arthur-Kill/Narrows and residual NYC
% groupings replace the previous generic 40/30/30 dispatch split.
j = zone_plants(plant_summary, "J");
rav = select_pg(j, ["Ravenswood", "Astoria", "500MW CC"]);
ak = select_pg(j, ["Arthur Kill", "Narrows"]);
goethals = sum(j.perform_pg_mw) - rav - ak;
gsk = append_split(gsk, mpc, "J", 79, rav, ...
    "PERFORM Ravenswood/Astoria generation cluster", "high");
gsk = append_split(gsk, mpc, "J", 82, ak, ...
    "PERFORM Arthur-Kill/Narrows generation cluster", "high");
gsk = append_split(gsk, mpc, "J", 81, goethals, ...
    "Residual Zone-J generation at Goethals/Gowanus proxy", "medium");

% Zone K: preserve the Northport share and place the remainder at the
% East-Garden-City aggregate Long-Island proxy.
k = zone_plants(plant_summary, "K");
northport = select_pg(k, "Northport");
gsk = append_split(gsk, mpc, "K", 80, northport, ...
    "PERFORM Northport plant", "high");
gsk = append_split(gsk, mpc, "K", 9003, sum(k.perform_pg_mw) - northport, ...
    "Residual Zone-K plants at East Garden City proxy", "medium");

gsk = finalize_weights(gsk);
end

function names = map_plant_names(cost_meta, unit_meta)
codes = double(cost_meta.EIAPlantCode);
names = strings(size(codes));
unit_codes = double(unit_meta.PlantCode);
unit_names = string(unit_meta.PlantName);
for k = 1:numel(codes)
    idx = find(unit_codes == codes(k), 1);
    if isempty(idx)
        names(k) = "UNMAPPED_" + string(codes(k));
    else
        names(k) = strtrim(unit_names(idx));
    end
end
end

function rows = zone_plants(tbl, zone)
rows = tbl(tbl.zone == string(zone), :);
end

function value = select_pg(tbl, patterns)
patterns = string(patterns);
mask = false(height(tbl), 1);
for k = 1:numel(patterns)
    mask = mask | contains(lower(tbl.plant_name), lower(patterns(k)));
end
value = sum(tbl.perform_pg_mw(mask));
end

function out = append_split(out, mpc, zone, bus_ids, total_pg, rule, confidence)
define_constants;
bus_ids = bus_ids(:);
if total_pg < -1e-6
    error('Negative PERFORM reference allocation for zone %s.', zone);
end
capacity = zeros(numel(bus_ids), 1);
names = strings(numel(bus_ids), 1);
for k = 1:numel(bus_ids)
    bi = find(mpc.bus(:, BUS_I) == bus_ids(k), 1);
    if isempty(bi)
        error('Required NPCC proxy bus %.0f is missing.', bus_ids(k));
    end
    gi = mpc.gen(:, GEN_STATUS) > 0 & mpc.gen(:, GEN_BUS) == bus_ids(k);
    capacity(k) = sum(mpc.gen(gi, PMAX));
    if isfield(mpc, 'bus_name')
        names(k) = strtrim(string(mpc.bus_name{bi}));
    else
        names(k) = "BUS_" + string(bus_ids(k));
    end
end
if sum(capacity) <= 0
    error('NPCC proxy buses for zone %s have no online generation capacity.', zone);
end
allocation = total_pg * capacity / sum(capacity);
for k = 1:numel(bus_ids)
    row = table(string(zone), bus_ids(k), names(k), allocation(k), ...
        capacity(k), string(rule), string(confidence), ...
        'VariableNames', {'zone','npcc_bus_id','npcc_bus_name', ...
        'perform_reference_pg_mw','npcc_bus_pmax_mw','source_rule','confidence'});
    if isempty(out), out = row; else, out = [out; row]; end %#ok<AGROW>
end
end

function tbl = finalize_weights(tbl)
tbl.perform_zone_pg_mw = zeros(height(tbl), 1);
tbl.perform_bus_weight = zeros(height(tbl), 1);
zones = unique(tbl.zone, 'stable');
for k = 1:numel(zones)
    idx = tbl.zone == zones(k);
    total = sum(tbl.perform_reference_pg_mw(idx));
    tbl.perform_zone_pg_mw(idx) = total;
    if total > 0
        tbl.perform_bus_weight(idx) = tbl.perform_reference_pg_mw(idx) / total;
    else
        cap = tbl.npcc_bus_pmax_mw(idx);
        tbl.perform_bus_weight(idx) = cap / sum(cap);
    end
end
tbl = sortrows(tbl, {'zone','npcc_bus_id'});
end
