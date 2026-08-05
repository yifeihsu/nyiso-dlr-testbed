function [interface_rows, scenario_rows] = import_p32_interface_targets(scenario_rows, options)
%IMPORT_P32_INTERFACE_TARGETS Import NYISO P-32 scaled interface targets.

if nargin < 1 || isempty(scenario_rows)
    [~, scenario_rows] = import_p58c_zonal_loads(nyiso_public_default_scenarios());
end
if nargin < 2, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'nyiso_public_interface_targets.csv');
end
if ~isfield(options, 'write_targets'), options.write_targets = false; end
if ~isfield(options, 'max_time_delta_minutes'), options.max_time_delta_minutes = 5; end

interfaces = nyiso_public_interface_map();
interface_rows = table();
for s = 1:height(scenario_rows)
    scenario_id = string(scenario_rows.scenario_id(s));
    ts = nyiso_public_timestamp(scenario_rows.timestamp(s));
    gamma = scenario_rows.scale_factor_gamma(s);
    [csv_file, source_name] = nyiso_public_monthly_csv('p32', ts, options);
    scenario_rows.source_interface_file(s) = string(source_name);

    tbl = readtable(csv_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
    row_ts = datetime(tbl.Timestamp, 'InputFormat', 'MM/dd/yyyy HH:mm');
    [selected_ts, delta_minutes] = nearest_timestamp(row_ts, ts);
    if ~isfinite(delta_minutes) || delta_minutes > options.max_time_delta_minutes
        error('import_p32_interface_targets:TimestampMissing', ...
            'Timestamp %s not found within %.3g minutes in %s.', ...
            datestr(ts), options.max_time_delta_minutes, csv_file);
    end
    mask = row_ts == selected_ts;
    hour_rows = tbl(mask, :);
    timestamp_string = string(datestr(ts, 'yyyy-mm-dd HH:MM'));
    interface_timestamp_string = string(datestr(selected_ts, 'yyyy-mm-dd HH:MM'));

    for k = 1:numel(interfaces)
        idx = strcmp(hour_rows.("Interface Name"), interfaces(k).p32_name);
        if ~any(idx)
            continue;
        end
        rec = hour_rows(find(idx, 1), :);
        flow = rec.("Flow (MWH)");
        pos_limit = rec.("Positive Limit (MWH)");
        neg_limit = rec.("Negative Limit (MWH)");
        limit = directional_limit(flow, pos_limit, neg_limit);
        if isfinite(limit) && abs(limit) > 0
            utilization = flow / limit;
            target_limit = gamma * limit;
        else
            utilization = NaN;
            target_limit = NaN;
        end
        target_flow = gamma * flow;
        note = string(interfaces(k).note);
        if delta_minutes > 0
            note = note + string(sprintf("; P-32 nearest timestamp offset %.3g minutes", delta_minutes));
        end
        new_row = table( ...
            scenario_id, timestamp_string, interface_timestamp_string, ...
            string(interfaces(k).interface_name), string(interfaces(k).aggregate_name), ...
            string(interfaces(k).zone_boundary), string(interfaces(k).p32_name), ...
            flow, limit, utilization, gamma, target_flow, target_limit, ...
            "P32_scaled", note, ...
            'VariableNames', {'scenario_id','timestamp','interface_timestamp', ...
                'interface_name','aggregate_name','zone_boundary','nyiso_interface_name', ...
                'nyiso_flow_mw','nyiso_limit_mw','nyiso_utilization', ...
                'scale_factor_gamma','target_flow_mw','target_limit_mw', ...
                'source','note'});
        interface_rows = [interface_rows; new_row]; %#ok<AGROW>
    end
end

if options.write_targets
    writetable(interface_rows, options.target_file);
end
end

function [selected_ts, delta_minutes] = nearest_timestamp(row_ts, ts)
unique_ts = unique(row_ts);
if isempty(unique_ts)
    selected_ts = NaT;
    delta_minutes = Inf;
    return;
end
[delta_duration, idx] = min(abs(unique_ts - ts));
selected_ts = unique_ts(idx);
delta_minutes = minutes(delta_duration);
end

function limit = directional_limit(flow, pos_limit, neg_limit)
if flow >= 0
    limit = pos_limit;
elseif isfinite(neg_limit) && neg_limit > -9000
    limit = abs(neg_limit);
else
    limit = NaN;
end
end
