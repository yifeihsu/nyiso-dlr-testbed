% s12_build_priors: season-specific unit/zonal dispatch priors for the six
% 2019 scenario hours from NYISO real-time fuel mix + PERFORM unit data,
% with NYGenUCV4 winter capacities applied where plant names match.
root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
nylite = fullfile(root, 'System Matpower Format', 'NY_Lite');
addpath(root, fullfile(root, 'System Matpower Format'), nylite);
define_constants;

ws = load(fullfile(nylite, 's12_case.mat'));
s12 = ws.s12;
ng = size(s12.gen, 1);
areas = s12.userdata.s12_zone_area_codes(:);
letters = string(s12.userdata.s12_zone_letters(:));
gen_area = s12.bus(s12.gen(:, GEN_BUS), BUS_AREA);
[~, gen_zone_idx] = ismember(gen_area, areas);

% fuel pools: PERFORM labels cannot separate NYISO "Dual Fuel" from
% "Natural Gas" units, so both fuel-mix categories feed one Gas pool.
fuel = string(s12.genfuel);
class = strings(ng, 1);
class(ismember(fuel, ["ng", "dfo", "rfo"])) = "Gas";
class(fuel == "nuclear") = "Nuclear";
class(fuel == "hydro") = "Hydro";
class(fuel == "wind") = "Wind";
class(ismember(fuel, ["coal", "other"])) = "Other Fossil Fuels";
class(ismember(fuel, ["solar", "wood"])) = "Other Renewables";
is_boundary = false(ng, 1);
is_boundary(s12.userdata.s12_external_groups.gen_index) = true;
is_ref = fuel == "reference";
eligible = ~is_boundary & ~is_ref & class ~= "" & s12.gen(:, PMAX) > 0;
fprintf('eligible prior units: %d of %d (boundary %d, reference %d, unclassified %d)\n', ...
    sum(eligible), ng, sum(is_boundary), sum(is_ref), ...
    sum(class == "" & ~is_boundary & ~is_ref));

% NYGenUCV4 winter capacities by plant-name match
uc = load(fullfile(root, 'PERFORM', 'Auxilliary_Perform_NY', 'NYGenUCV4.mat'));
uct = uc.NYGenUC;
plant_wcap = groupsummary(uct, 'PlantName', 'sum', 'WinterCapacityMW');
ctrl = readtable(fullfile(nylite, 'perform_source_to_reduced_control_mapping.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
gen_plant = strings(ng, 1);
ok = isfinite(ctrl.converted_gen_index) & ctrl.converted_gen_index > 0;
gen_plant(ctrl.converted_gen_index(ok)) = erase(ctrl.source_plant_name(ok), '"');
wcap = nan(ng, 1);
uc_names = lower(strtrim(string(plant_wcap.PlantName)));
for g = 1:ng
    if gen_plant(g) == "", continue; end
    m = find(uc_names == lower(strtrim(gen_plant(g))), 1);
    if ~isempty(m)
        % plant-level winter capacity shared among co-located units by PMAX
        sameplant = gen_plant == gen_plant(g);
        wcap(g) = plant_wcap.sum_WinterCapacityMW(m) * ...
            s12.gen(g, PMAX) / sum(s12.gen(sameplant, PMAX));
    end
end
matched = isfinite(wcap) & eligible;
fprintf('winter-capacity name match: %d units, %.0f of %.0f MW eligible PMAX\n', ...
    sum(matched), sum(s12.gen(matched, PMAX)), sum(s12.gen(eligible, PMAX)));

scen = readtable(fullfile(nylite, 'nyiso_public_scenarios.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
cache = fullfile(nylite, 'nyiso_public_cache');
classes = ["Gas", "Nuclear", "Other Fossil Fuels", ...
    "Other Renewables", "Wind", "Hydro"];
fuelmix_members = containers.Map( ...
    {'Gas', 'Nuclear', 'Other Fossil Fuels', 'Other Renewables', 'Wind', 'Hydro'}, ...
    {["Dual Fuel", "Natural Gas"], "Nuclear", "Other Fossil Fuels", ...
     "Other Renewables", "Wind", "Hydro"});

unit_rows = table(); zonal_rows = table(); class_rows = table();
for s = 1:height(scen)
    ts = datetime(scen.timestamp(s), 'InputFormat', 'yyyy-MM-dd HH:mm');
    day_token = datestr(ts, 'yyyymmdd');
    month_token = datestr(ts, 'yyyymm');
    f = fullfile(cache, [month_token '_rtfuelmix'], [day_token 'rtfuelmix.csv']);
    tbl = readtable(f, 'TextType', 'string', 'VariableNamingRule', 'preserve');
    fts = datetime(tbl.("Time Stamp"), 'InputFormat', 'MM/dd/yyyy HH:mm:ss');
    in_hour = fts > ts & fts <= ts + hours(1);   % hour-ending window
    winter = month(ts) <= 3 | month(ts) >= 11;

    cap = s12.gen(:, PMAX);
    if winter
        cap(matched) = min(cap(matched), wcap(matched));
    end

    pg_prior = zeros(ng, 1);
    for c = 1:numel(classes)
        members = fuelmix_members(char(classes(c)));
        target = 0;
        for mname = members
            v = mean(tbl.("Gen MW")(in_hour & tbl.("Fuel Category") == mname));
            if isfinite(v), target = target + v; end
        end
        umask = eligible & class == classes(c);
        K = sum(cap(umask));
        alloc = min(target, K);
        if K > 0
            pg_prior(umask) = cap(umask) * (alloc / K);
        end
        class_rows = [class_rows; table(scen.scenario_id(s), classes(c), target, ...
            K, alloc, target - alloc, 'VariableNames', {'scenario_id', 'fuel_class', ...
            'nyiso_fuelmix_mw', 'model_class_capacity_mw', 'allocated_mw', ...
            'unallocated_mw'})]; %#ok<AGROW>
    end

    gamma = scen.scale_factor_gamma(s);
    for z = 1:numel(areas)
        zsum = sum(pg_prior(gen_zone_idx == z));
        zonal_rows = [zonal_rows; table(scen.scenario_id(s), letters(z), zsum, ...
            gamma * zsum, gamma, 'VariableNames', {'scenario_id', 'zone', ...
            'prior_mw_raw', 'prior_mw_scaled', 'gamma'})]; %#ok<AGROW>
    end
    gsel = find(pg_prior > 0);
    unit_rows = [unit_rows; table(repmat(scen.scenario_id(s), numel(gsel), 1), ...
        gsel, s12.gen(gsel, GEN_BUS), letters(gen_zone_idx(gsel)), class(gsel), ...
        pg_prior(gsel), gamma * pg_prior(gsel), ...
        'VariableNames', {'scenario_id', 'gen_index', 'reduced_bus', 'zone', ...
        'fuel_class', 'prior_mw_raw', 'prior_mw_scaled'})]; %#ok<AGROW>
    fprintf('%s: fuelmix total %.0f MW, allocated %.0f MW raw\n', ...
        scen.scenario_id(s), sum(class_rows.nyiso_fuelmix_mw( ...
        class_rows.scenario_id == scen.scenario_id(s))), sum(pg_prior));
end

writetable(unit_rows, fullfile(nylite, 's12_unit_dispatch_priors.csv'));
writetable(zonal_rows, fullfile(nylite, 's12_zonal_generation_priors.csv'));
writetable(class_rows, fullfile(nylite, 's12_fuel_class_allocation.csv'));
fprintf('wrote s12 prior CSVs\n');

% compare with single-snapshot prior (source PG by zone)
snapshot_z = zeros(numel(areas), 1);
on = s12.gen(:, GEN_STATUS) > 0 & ~is_boundary & ~is_ref;
for z = 1:numel(areas)
    snapshot_z(z) = sum(s12.gen(on & gen_zone_idx == z, PG));
end
fprintf('\nzonal priors, raw MW (snapshot vs winter-hour fuelmix prior):\n');
w = zonal_rows(zonal_rows.scenario_id == "S2_2019_WINTER_PEAK_PUBLIC", :);
for z = 1:numel(areas)
    fprintf('  %s: snapshot %8.1f  winter prior %8.1f\n', letters(z), ...
        snapshot_z(z), w.prior_mw_raw(w.zone == letters(z)));
end
