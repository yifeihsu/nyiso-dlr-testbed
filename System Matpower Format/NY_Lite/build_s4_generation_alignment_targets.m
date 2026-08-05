function outputs = build_s4_generation_alignment_targets(options)
%BUILD_S4_GENERATION_ALIGNMENT_TARGETS Build S4 capability/net-injection CSVs.
%
%   The NYISO capability numbers are seeded from the user-provided 2025
%   Gold Book summary values in the calibration notes. They are used as
%   aggregate zonal priors, not as unit-level dispatch targets.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

if ~isfield(options, 'capability_file')
    options.capability_file = fullfile(helper_dir, 'nyiso_generator_capability_targets.csv');
end
if ~isfield(options, 'generation_target_file')
    options.generation_target_file = fullfile(helper_dir, 'nyiso_zonal_generation_targets.csv');
end
if ~isfield(options, 'zone_j_total_pmax_mw'), options.zone_j_total_pmax_mw = 3000; end

mpc = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
[mpc, ~] = add_ny_downstate_delivery_spine(mpc, 'full');
[mpc, ~] = add_zone_j_equivalent_supply(mpc, ...
    struct('total_pmax_mw', options.zone_j_total_pmax_mw, ...
    'q_abs_ratio', 0, 'cost_c1', 250, 'cost_c2', 0.02));
current = zonal_pmax(mpc);

capability_targets = build_capability_table(current);
writetable(capability_targets, options.capability_file);

generation_targets = build_generation_target_table(capability_targets);
writetable(generation_targets, options.generation_target_file);

outputs = struct('capability_file', options.capability_file, ...
    'generation_target_file', options.generation_target_file, ...
    'capability_row_count', height(capability_targets), ...
    'generation_target_row_count', height(generation_targets));
end

function tbl = build_capability_table(current)
zones = ["A"; "B"; "C"; "D"; "E"; "F"; "G"; "H"; "I"; "J"; "K"];
names = ["WEST"; "GENESE"; "CENTRL"; "NORTH"; "MHK VL"; "CAPITL"; ...
    "HUD VL"; "MILLWD"; "DUNWOD"; "N.Y.C."; "LONGIL"];

nyiso_summer_capability_mw = [3492.4; 780.5; 6781.1; 1918.5; 1293.1; 4775.6; ...
    4704.0; 53.5; 0.0; 8704.7; 5195.5];
nyiso_total = 37698.9;
model_total = sum(struct2array(current));
model_scaled_capability_mw = nyiso_summer_capability_mw / nyiso_total * model_total;
recommended_equivalent_pmax_mw = [0; 0; 0; 0; 600; 1600; 2200; 0; 0; 0; 1800];
action = ["reduce_participation"; "reduce_participation"; ...
    "reduce_participation"; "keep"; "add_equivalent"; "add_equivalent"; ...
    "add_equivalent"; "keep_minor"; "reclassify_as_import"; ...
    "keep_zone_j_equivalent"; "add_equivalent"];
notes = [ ...
    "Current reduced model is western-capability heavy."; ...
    "Current reduced model is Genesee-capability heavy."; ...
    "Current reduced model is somewhat high in Central capability."; ...
    "Close to scaled NYISO capability target."; ...
    "Add small Mohawk Valley equivalent capability if residuals require."; ...
    "Add Capital-region aggregate capability around Gilboa/Albany/Rotterdam/New Scotland."; ...
    "Add Hudson Valley aggregate capability around Pleasant Valley/Ramapo/Leeds."; ...
    "Small scaled NYISO capability; no first-pass equivalent added."; ...
    "Treat CE UG generator as an interface/import or voltage-support proxy, not native Zone I."; ...
    "Keep bounded 3.0 GW Zone-J equivalent as S3 feasibility repair."; ...
    "Add Long Island aggregate capability at Northport/East Garden City."];

current_model_pmax_mw = zeros(numel(zones), 1);
for k = 1:numel(zones)
    if isfield(current, char(zones(k)))
        current_model_pmax_mw(k) = current.(char(zones(k)));
    else
        current_model_pmax_mw(k) = 0;
    end
end
nyiso_share = nyiso_summer_capability_mw / nyiso_total;
model_minus_scaled_target_mw = current_model_pmax_mw - model_scaled_capability_mw;

tbl = table(zones, names, nyiso_summer_capability_mw, nyiso_share, ...
    model_scaled_capability_mw, current_model_pmax_mw, ...
    model_minus_scaled_target_mw, recommended_equivalent_pmax_mw, action, notes, ...
    repmat("user_provided_2025_gold_book_summary", numel(zones), 1), ...
    'VariableNames', {'zone','nyiso_zone_name','nyiso_summer_capability_mw', ...
    'nyiso_share','model_scaled_capability_mw','current_model_pmax_mw', ...
    'model_minus_scaled_target_mw','recommended_equivalent_pmax_mw', ...
    'action','notes','source'});
end

function targets = build_generation_target_table(capability_targets)
helper_dir = fileparts(mfilename('fullpath'));
load_targets = readtable(fullfile(helper_dir, 'ny_zonal_load_targets.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
interface_targets = readtable(fullfile(helper_dir, 'nyiso_public_interface_targets.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
scenarios = readtable(fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
zones = capability_targets.zone;
targets = table();
for s = 1:height(scenarios)
    scenario_id = string(scenarios.scenario_id(s));
    lmask = string(load_targets.scenario_id) == scenario_id;
    imask = string(interface_targets.scenario_id) == scenario_id;
    load_subset = load_targets(lmask, :);
    iface_subset = interface_targets(imask, :);
    net_export = net_export_from_interfaces(iface_subset, zones);
    for z = 1:numel(zones)
        zone = zones(z);
        load_row = load_subset(string(load_subset.nyiso_zone_letter) == zone, :);
        if height(load_row) == 0
            target_load = NaN;
        else
            target_load = load_row.target_load_mw(1);
        end
        cap_row = capability_targets(capability_targets.zone == zone, :);
        target_net_export = net_export.(char(zone));
        target_generation = target_load + target_net_export;
        row = table(scenario_id, string(scenarios.timestamp(s)), zone, ...
            string(cap_row.nyiso_zone_name(1)), target_load, target_net_export, ...
            target_generation, cap_row.model_scaled_capability_mw(1), ...
            "low_internal_interface_incidence_only", ...
            "P58C_load_P32_internal_interface_scaled", ...
            "Approximate zonal generation target from signed public interface incidence; not a hard OPF target.", ...
            'VariableNames', {'scenario_id','timestamp','zone','nyiso_zone_name', ...
            'target_load_mw','target_net_export_mw','target_generation_mw', ...
            'generation_prior_mw','target_confidence','source','note'});
        targets = [targets; row]; %#ok<AGROW>
    end
end
end

function net = net_export_from_interfaces(tbl, zones)
for z = 1:numel(zones)
    net.(char(zones(z))) = 0;
end
for k = 1:height(tbl)
    name = string(tbl.interface_name(k));
    f = tbl.target_flow_mw(k);
    switch name
        case "Moses_South"
            net.D = net.D + f; net.E = net.E - f;
        case "Central_East"
            net.E = net.E + f; net.F = net.F - f;
        case "Total_East_proxy"
            net.F = net.F + f; net.G = net.G - f;
        case "UPNY_ConEd"
            net.G = net.G + f; net.H = net.H - f;
        case "Millwood_South"
            net.H = net.H + f; net.I = net.I - f;
        case "Dunwoodie_South"
            net.I = net.I + f; net.J = net.J - f;
        case {"ConEd_LIPA_IK", "ConEd_LIPA_total"}
            net.I = net.I + f; net.K = net.K - f;
        case "ConEd_LIPA_JK"
            net.J = net.J + f; net.K = net.K - f;
    end
end
end

function current = zonal_pmax(mpc)
define_constants;
mpc = attach_nyiso_zone_metadata(mpc);
zones = unique(string(mpc.userdata.nyiso_physical_zone), 'stable');
current = struct();
for k = 1:numel(zones)
    zone = char(zones(k));
    if zone == ""
        continue;
    end
    bus_ids = mpc.bus(strcmp(string(mpc.userdata.nyiso_physical_zone), zones(k)), 1);
    idx = ismember(mpc.gen(:, GEN_BUS), bus_ids) & mpc.gen(:, GEN_STATUS) > 0;
    current.(zone) = sum(mpc.gen(idx, PMAX));
end
end
