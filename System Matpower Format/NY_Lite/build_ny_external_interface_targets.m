function outputs = build_ny_external_interface_targets(scenarios, options)
%BUILD_NY_EXTERNAL_INTERFACE_TARGETS Build S1 and public boundary target rows.

if nargin < 1 || isempty(scenarios)
    scenarios = nyiso_public_default_scenarios();
end
if nargin < 2, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'ny_external_interface_targets.csv');
end
if ~isfield(options, 'power_factor'), options.power_factor = 0.97; end
if ~isfield(options, 'include_public'), options.include_public = true; end

rows = s1_measured_rows(options);
if options.include_public
    rows = [rows; public_p32_rows(scenarios, options)]; %#ok<AGROW>
end
writetable(rows, options.target_file);
outputs = struct('target_file', options.target_file, 'row_count', height(rows));
end

function rows = s1_measured_rows(options)
define_constants;
mpc = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
mpopt = mpoption('verbose', 0, 'out.all', 0);
res = runpf(mpc, mpopt);
boundary = measure_ny_boundary_flows(res, "S1_MEASURED_BOUNDARY", ...
    struct('run_pf_if_needed', false));
rows = empty_rows();
for k = 1:height(boundary)
    name = sprintf('S1_BRANCH_%03d_%s_%s', boundary.source_branch(k), ...
        clean_token(boundary.ny_boundary_bus_name(k)), ...
        clean_token(boundary.external_bus_name(k)));
    row = make_row("S1_MEASURED_BOUNDARY", "", string(name), "", ...
        boundary.ny_boundary_bus(k), "import_into_ny", ...
        NaN, boundary.source_branch_rate_a_mva(k), 1.0, ...
        boundary.p_import_mw(k), boundary.source_branch_rate_a_mva(k), ...
        boundary.q_import_mvar(k), "boundary_generator", "fixed_q", ...
        boundary.ny_vm_pu(k), boundary.q_import_mvar(k), ...
        boundary.q_import_mvar(k), ...
        "S1 full-NPCC PF measured boundary flow");
    rows = [rows; row]; %#ok<AGROW>
end
end

function rows = public_p32_rows(scenarios, options)
if isstruct(scenarios), scenarios = struct2table(scenarios); end
map = nyiso_public_external_interface_map();
rows = empty_rows();
for s = 1:height(scenarios)
    scenario_id = string(scenarios.scenario_id(s));
    ts = nyiso_public_timestamp(scenarios.timestamp(s));
    [~, scenario_rows] = import_p58c_zonal_loads(scenarios(s, :), ...
        struct('write_targets', false));
    gamma = scenario_rows.scale_factor_gamma(1);
    [csv_file, source_name] = nyiso_public_monthly_csv('p32', ts, options);
    tbl = readtable(csv_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
    row_ts = datetime(tbl.Timestamp, 'InputFormat', 'MM/dd/yyyy HH:mm');
    selected_ts = nearest_timestamp(row_ts, ts);
    hour_rows = tbl(row_ts == selected_ts, :);
    for k = 1:numel(map)
        idx = find(strcmp(hour_rows.("Interface Name"), map(k).p32_interface_name), 1);
        if isempty(idx), continue; end
        flow = hour_rows.("Flow (MWH)")(idx);
        pos_limit = hour_rows.("Positive Limit (MWH)")(idx);
        neg_limit = hour_rows.("Negative Limit (MWH)")(idx);
        limit = directional_limit(flow, pos_limit, neg_limit);
        p_target = gamma * flow * map(k).allocation_weight;
        if isfinite(limit)
            target_limit = gamma * limit * abs(map(k).allocation_weight);
        else
            target_limit = NaN;
        end
        q_target = p_target * tan(acos(options.power_factor));
        row = make_row(scenario_id, string(datestr(ts, 'yyyy-mm-dd HH:MM')), ...
            string(map(k).external_interface_name), string(map(k).p32_interface_name), ...
            map(k).ny_boundary_bus, string(map(k).direction_positive), ...
            flow, limit, gamma, p_target, target_limit, q_target, ...
            "boundary_generator", string(map(k).q_mode), map(k).v_setpoint, ...
            map(k).qmin_mvar, map(k).qmax_mvar, ...
            string(map(k).note) + "; source=" + string(source_name));
        rows = [rows; row]; %#ok<AGROW>
    end
end
end

function row = make_row(scenario_id, timestamp, external_name, p32_name, ...
    bus, direction, nyiso_flow, nyiso_limit, gamma, target_flow, target_limit, ...
    target_q, equivalent_type, q_mode, v_setpoint, qmin, qmax, note)
row = table(string(scenario_id), string(timestamp), string(external_name), ...
    string(p32_name), bus, string(direction), nyiso_flow, nyiso_limit, gamma, ...
    target_flow, target_limit, target_q, string(equivalent_type), ...
    string(q_mode), v_setpoint, qmin, qmax, string(note), ...
    'VariableNames', target_columns());
end

function rows = empty_rows()
rows = table(strings(0,1), strings(0,1), strings(0,1), strings(0,1), ...
    zeros(0,1), strings(0,1), zeros(0,1), zeros(0,1), zeros(0,1), ...
    zeros(0,1), zeros(0,1), zeros(0,1), strings(0,1), strings(0,1), ...
    zeros(0,1), zeros(0,1), zeros(0,1), strings(0,1), ...
    'VariableNames', target_columns());
end

function names = target_columns()
names = {'scenario_id','timestamp','external_interface_name', ...
    'p32_interface_name','ny_boundary_bus','direction_positive', ...
    'nyiso_flow_mw','nyiso_limit_mw','scale_factor_gamma', ...
    'target_flow_mw','target_limit_mw','target_q_mvar', ...
    'equivalent_type','q_mode','v_setpoint','qmin_mvar','qmax_mvar','note'};
end

function token = clean_token(value)
token = char(regexprep(upper(string(value)), '[^A-Z0-9]+', '_'));
token = regexprep(token, '^_|_$', '');
end

function selected_ts = nearest_timestamp(row_ts, ts)
unique_ts = unique(row_ts);
[~, idx] = min(abs(unique_ts - ts));
selected_ts = unique_ts(idx);
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
