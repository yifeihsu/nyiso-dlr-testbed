function outputs = run_nyiso_public_acopf_scenarios(options)
%RUN_NYISO_PUBLIC_ACOPF_SCENARIOS Run IPOPT ACOPF for public target scenarios.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
if ~isfield(options, 'scenario_file')
    options.scenario_file = fullfile(helper_dir, 'nyiso_public_scenarios.csv');
end
if ~isfield(options, 'output_file')
    options.output_file = fullfile(helper_dir, 'nyiso_public_acopf_results.csv');
end
if ~isfield(options, 'residual_file')
    options.residual_file = fullfile(helper_dir, 'nyiso_public_interface_residuals.csv');
end
if ~isfield(options, 'variants')
    options.variants = {'original_topology','gilboa_leeds'};
end

if exist(options.scenario_file, 'file') ~= 2
    build_nyiso_public_targets();
end

scenarios = readtable(options.scenario_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
mpopt = mpoption( ...
    'verbose', 0, ...
    'out.all', 0, ...
    'opf.ac.solver', 'IPOPT', ...
    'opf.flow_lim', 'S', ...
    'opf.violation', 1e-6, ...
    'opf.use_vg', 0, ...
    'opf.ignore_angle_lim', 0);

rows = table();
residual_rows = table();
for s = 1:height(scenarios)
    scenario_id = string(scenarios.scenario_id(s));
    for v = 1:numel(options.variants)
        variant = string(options.variants{v});
        [results, added, status, note] = solve_variant(scenario_id, variant, mpopt);
        [row, detail] = summarize_variant(scenario_id, scenarios.timestamp(s), ...
            variant, results, added, status, note);
        rows = [rows; row]; %#ok<AGROW>
        residual_rows = [residual_rows; detail]; %#ok<AGROW>
    end
end

writetable(rows, options.output_file);
writetable(residual_rows, options.residual_file);
outputs = struct('output_file', options.output_file, ...
    'residual_file', options.residual_file, 'row_count', height(rows), ...
    'residual_row_count', height(residual_rows));
end

function [results, added, status, note] = solve_variant(scenario_id, variant, mpopt)
added = [];
status = "ok";
note = "";
try
    mpc = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
    [mpc, ~] = apply_nyiso_zonal_loads(mpc, scenario_id, 1.0, ...
        struct('preserve_total_ny_load', true));
    if strcmpi(variant, 'gilboa_leeds')
        [mpc, added] = add_ny_lite_tielines(mpc, 'core');
    elseif ~strcmpi(variant, 'original_topology')
        error('run_nyiso_public_acopf_scenarios:UnknownVariant', ...
            'Unknown variant %s.', variant);
    end
    results = runopf(mpc, mpopt);
catch ME
    results = struct();
    status = "error";
    note = string(regexprep(ME.message, '\s+', ' '));
end
end

function [row, residual_rows] = summarize_variant(scenario_id, timestamp, variant, results, added, status, note)
define_constants;
if strcmp(status, "error")
    nan_values = num2cell(NaN(1, 26));
    row = table(scenario_id, string(timestamp), variant, status, nan_values{:}, note, ...
        'VariableNames', result_columns());
    residual_rows = empty_residual_rows();
    return;
end

tol = 1e-6;
online = results.gen(:, GEN_STATUS) > 0;
sf = sqrt(results.branch(:, PF).^2 + results.branch(:, QF).^2);
st = sqrt(results.branch(:, PT).^2 + results.branch(:, QT).^2);
smax = max(sf, st);
rate = results.branch(:, RATE_A);
rated = rate > 0;
binding = rated & abs(smax - rate) <= 1e-4;
voltage_bound = abs(results.bus(:, VM) - results.bus(:, VMIN)) <= 1e-5 | ...
    abs(results.bus(:, VM) - results.bus(:, VMAX)) <= 1e-5;

flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
targets = read_public_interface_targets(scenario_id);
[J, ~] = interface_target_objective(flows, targets);
residual_rows = residual_rows_for_targets(scenario_id, timestamp, variant, ...
    status, double(results.success), flows, targets);

gl_smax = NaN;
gl_pf = NaN;
gl_qf = NaN;
gl_pt = NaN;
gl_qt = NaN;
if ~isempty(added)
    gl_idx = added(1).branch_index;
    gl_smax = smax(gl_idx);
    gl_pf = results.branch(gl_idx, PF);
    gl_qf = results.branch(gl_idx, QF);
    gl_pt = results.branch(gl_idx, PT);
    gl_qt = results.branch(gl_idx, QT);
end

row = table(scenario_id, string(timestamp), variant, status, double(results.success), ...
    raw_info(results), results.f, J, sum(results.bus(:, PD)), ...
    sum(results.gen(online, PG)), sum(results.gen(online, PG)) - sum(results.bus(:, PD)), ...
    min(results.bus(:, VM)), max(results.bus(:, VM)), ...
    sum(voltage_bound), sum(binding), ...
    sum(rated & smax > rate + 1e-6), max([0; smax(rated) - rate(rated)]), ...
    smax(80) / rate(80) * 100, smax(190) / rate(190) * 100, ...
    interface_flow(flows, 'Moses_South'), interface_flow(flows, 'Central_East'), ...
    interface_flow(flows, 'Total_East_proxy'), interface_flow(flows, 'UPNY_ConEd'), ...
    interface_flow(flows, 'Dunwoodie_South'), interface_flow(flows, 'ConEd_LIPA_total'), ...
    gl_pf, gl_qf, gl_pt, gl_qt, gl_smax, note, ...
    'VariableNames', result_columns());
end

function names = result_columns()
names = {'scenario_id','timestamp','variant','status','opf_success', ...
    'opf_raw_info','objective','interface_objective','total_load_mw', ...
    'total_generation_mw','losses_mw','min_voltage','max_voltage', ...
    'voltage_bound_count','binding_branch_count', ...
    'rate_a_overload_count','max_rate_a_overload_mva', ...
    'branch80_loading_pct','branch190_loading_pct', ...
    'moses_south_flow_mw','central_east_flow_mw', ...
    'total_east_proxy_flow_mw','upny_coned_flow_mw', ...
    'dunwoodie_south_flow_mw','coned_lipa_total_flow_mw', ...
    'gilboa_leeds_pf_mw','gilboa_leeds_qf_mvar', ...
    'gilboa_leeds_pt_mw','gilboa_leeds_qt_mvar', ...
    'gilboa_leeds_smax_mva','note'};
end

function info = raw_info(results)
if isfield(results, 'raw') && isfield(results.raw, 'info')
    info = results.raw.info;
else
    info = NaN;
end
end

function value = interface_flow(flows, name)
idx = find(strcmp({flows.interface_name}, name), 1);
if isempty(idx), value = NaN; else, value = flows(idx).flow_mw; end
end

function rows = residual_rows_for_targets(scenario_id, timestamp, variant, status, opf_success, flows, targets)
rows = empty_residual_rows();
for k = 1:height(targets)
    interface_name = string(targets.interface_name(k));
    lite_flow = interface_flow(flows, char(interface_name));
    target_flow = targets.target_flow_mw(k);
    residual = lite_flow - target_flow;
    scale = max(100, abs(target_flow));
    objective_term = (residual / scale)^2;
    interface_timestamp = "";
    if ismember('interface_timestamp', targets.Properties.VariableNames)
        interface_timestamp = string(targets.interface_timestamp(k));
    end
    row = table(string(scenario_id), string(timestamp), string(variant), ...
        string(status), opf_success, interface_name, string(targets.zone_boundary(k)), ...
        interface_timestamp, targets.nyiso_flow_mw(k), targets.nyiso_limit_mw(k), ...
        targets.nyiso_utilization(k), targets.scale_factor_gamma(k), ...
        target_flow, targets.target_limit_mw(k), lite_flow, residual, ...
        abs(residual), scale, objective_term, ...
        'VariableNames', residual_columns());
    rows = [rows; row]; %#ok<AGROW>
end
end

function rows = empty_residual_rows()
rows = table(strings(0,1), strings(0,1), strings(0,1), strings(0,1), ...
    zeros(0,1), strings(0,1), strings(0,1), strings(0,1), ...
    zeros(0,1), zeros(0,1), zeros(0,1), zeros(0,1), ...
    zeros(0,1), zeros(0,1), zeros(0,1), zeros(0,1), ...
    zeros(0,1), zeros(0,1), zeros(0,1), ...
    'VariableNames', residual_columns());
end

function names = residual_columns()
names = {'scenario_id','timestamp','variant','status','opf_success', ...
    'interface_name','zone_boundary','interface_timestamp', ...
    'nyiso_flow_mw','nyiso_limit_mw','nyiso_utilization', ...
    'scale_factor_gamma','target_flow_mw','target_limit_mw', ...
    'lite_flow_mw','residual_mw','abs_residual_mw','scale_mw', ...
    'objective_term'};
end
