function [load_rows, scenario_rows] = import_p58c_zonal_loads(scenarios, options)
%IMPORT_P58C_ZONAL_LOADS Import NYISO P-58C loads as scaled NY-lite targets.

if nargin < 1 || isempty(scenarios)
    scenarios = nyiso_public_default_scenarios();
end
if nargin < 2, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'ny_zonal_load_targets.csv');
end
if ~isfield(options, 'write_targets'), options.write_targets = false; end
if ~isfield(options, 'solver'), options.solver = 'IPOPT'; end

scenarios = normalize_scenarios(scenarios);
zones = nyiso_public_zone_map();
npcc_ny_total_load_mw = npcc_ny_total_load();

load_rows = table();
scenario_rows = table();
for s = 1:height(scenarios)
    scenario_id = string(scenarios.scenario_id(s));
    ts = nyiso_public_timestamp(scenarios.timestamp(s));
    [csv_file, source_name] = nyiso_public_monthly_csv('p58c', ts, options);
    tbl = readtable(csv_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
    time_col = tbl.("Time Stamp");
    row_ts = datetime(time_col, 'InputFormat', 'MM/dd/yyyy HH:mm:ss');
    mask = row_ts == ts;
    if ~any(mask)
        error('import_p58c_zonal_loads:TimestampMissing', ...
            'Timestamp %s not found in %s.', datestr(ts), csv_file);
    end
    hour_rows = tbl(mask, :);

    zone_loads = zeros(numel(zones), 1);
    for z = 1:numel(zones)
        idx = strcmp(hour_rows.Name, zones(z).name);
        if ~any(idx)
            error('import_p58c_zonal_loads:ZoneMissing', ...
                'Zone %s missing for %s.', zones(z).name, scenario_id);
        end
        zone_loads(z) = hour_rows.("Integrated Load")(find(idx, 1));
    end
    nyiso_total = sum(zone_loads);
    gamma = npcc_ny_total_load_mw / nyiso_total;
    shares = zone_loads / nyiso_total;
    targets = npcc_ny_total_load_mw * shares;
    timestamp_string = string(datestr(ts, 'yyyy-mm-dd HH:MM'));

    for z = 1:numel(zones)
        new_row = table( ...
            scenario_id, timestamp_string, string(zones(z).letter), ...
            string(zones(z).name), zone_loads(z), targets(z), NaN, ...
            "P58C_scaled", "ready", ...
            sprintf("NYISO load %.6g MW scaled by gamma %.8g", zone_loads(z), gamma), ...
            'VariableNames', {'scenario_id','timestamp','nyiso_zone_letter', ...
                'nyiso_zone_name','nyiso_load_mw','target_load_mw', ...
                'target_load_share','source','status','note'});
        load_rows = [load_rows; new_row]; %#ok<AGROW>
    end

    note = "";
    if ismember('notes', scenarios.Properties.VariableNames)
        note = string(scenarios.notes(s));
    end
    scenario_row = table( ...
        scenario_id, timestamp_string, string(source_name), strings(1,1), ...
        nyiso_total, npcc_ny_total_load_mw, gamma, string(options.solver), note, ...
        'VariableNames', {'scenario_id','timestamp','source_load_file', ...
            'source_interface_file','nyiso_total_load_mw', ...
            'npcc_ny_total_load_mw','scale_factor_gamma','solver','notes'});
    scenario_rows = [scenario_rows; scenario_row]; %#ok<AGROW>
end

if options.write_targets
    write_replace_scenarios(options.target_file, load_rows, 'scenario_id', load_rows.scenario_id);
end
end

function scenarios = normalize_scenarios(scenarios)
if istable(scenarios)
    return;
end
if isstruct(scenarios)
    scenarios = struct2table(scenarios);
else
    error('import_p58c_zonal_loads:BadScenarios', ...
        'Scenarios must be a table or struct array.');
end
end

function total = npcc_ny_total_load()
define_constants;
mpc = npcc_ny_lite_v0_baseline;
mpc = attach_nyiso_zone_metadata(mpc);
ny_mask = mpc.userdata.nyiso_zone_id > 0;
total = sum(mpc.bus(ny_mask, PD));
end

function write_replace_scenarios(path, new_rows, key_name, scenario_ids)
if exist(path, 'file') == 2
    old = readtable(path, 'TextType', 'string', 'VariableNamingRule', 'preserve');
else
    old = table();
end
if height(old) > 0 && ismember(key_name, old.Properties.VariableNames)
    old_ids = string(old.(key_name));
    keep = ~ismember(old_ids, string(scenario_ids));
    old = old(keep, :);
end
all_names = union(old.Properties.VariableNames, new_rows.Properties.VariableNames, 'stable');
old = normalize_output_table(old, all_names);
new_rows = normalize_output_table(new_rows, all_names);
writetable([old; new_rows], path);
end

function tbl = normalize_output_table(tbl, names)
numeric_names = {'target_load_mw','target_load_share','nyiso_load_mw'};
for k = 1:numel(names)
    if ~ismember(names{k}, tbl.Properties.VariableNames)
        if ismember(names{k}, numeric_names)
            tbl.(names{k}) = NaN(height(tbl), 1);
        else
            tbl.(names{k}) = strings(height(tbl), 1);
        end
    elseif ismember(names{k}, numeric_names)
        tbl.(names{k}) = double(tbl.(names{k}));
    else
        tbl.(names{k}) = string_column(tbl.(names{k}));
    end
end
tbl = tbl(:, names);
end

function values = string_column(values)
if isdatetime(values)
    out = strings(size(values));
    valid = ~isnat(values);
    out(valid) = string(datestr(values(valid), 'yyyy-mm-dd HH:MM'));
    values = out;
else
    values = string(values);
end
values = values(:);
end
