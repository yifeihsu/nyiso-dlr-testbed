function outputs = run_ny_only_eta_continuation(options)
%RUN_NY_ONLY_ETA_CONTINUATION Sweep from S1 to public NY load/interchange.
%
%   For each public scenario, this script solves OPF for
%       Pd(eta) = (1 - eta) Pd_S1 + eta Pd_public
%       Pe(eta) = (1 - eta) Pe_S1 + eta Pe_public
%   where external schedules are represented by boundary equivalent
%   generators grouped at retained NY boundary buses.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'ny_external_interface_targets.csv');
end
if ~isfield(options, 'output_file')
    options.output_file = fullfile(helper_dir, 'ny_only_eta_continuation.csv');
end
if ~isfield(options, 'eta_grid')
    options.eta_grid = 0:0.1:1;
end
if exist(options.target_file, 'file') ~= 2
    build_ny_external_interface_targets([], struct('target_file', options.target_file));
end

public_scenarios = readtable(fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
mpopt = mpoption( ...
    'verbose', 0, ...
    'out.all', 0, ...
    'opf.ac.solver', 'IPOPT', ...
    'opf.flow_lim', 'S', ...
    'opf.violation', 1e-6, ...
    'opf.use_vg', 0, ...
    'opf.ignore_angle_lim', 0);

base = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
[base_ny, ~] = build_ny_only_equivalent_case(base);

rows = table();
for s = 1:height(public_scenarios)
    scenario_id = string(public_scenarios.scenario_id(s));
    for k = 1:numel(options.eta_grid)
        eta = options.eta_grid(k);
        rows = [rows; run_one(base_ny, scenario_id, eta, mpopt, options)]; %#ok<AGROW>
    end
end

writetable(rows, options.output_file);
outputs = struct('output_file', options.output_file, 'row_count', height(rows));
end

function row = run_one(base_ny, public_scenario_id, eta, mpopt, options)
define_constants;
status = "ok";
note = "";
try
    mpc = base_ny;
    [mpc, ~] = apply_nyiso_zonal_loads(mpc, public_scenario_id, eta, ...
        struct('preserve_total_ny_load', true));
    eta_targets = make_eta_external_targets(public_scenario_id, eta, options.target_file);
    tmp_file = [tempname, '.csv'];
    cleanup = onCleanup(@() cleanup_temp_file(tmp_file)); %#ok<NASGU>
    writetable(eta_targets, tmp_file);
    target_id = string(eta_targets.scenario_id(1));
    [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
        target_id, struct('target_file', tmp_file));
    results = runopf(mpc, mpopt);
catch ME
    results = struct();
    ext_report = table();
    status = "error";
    note = string(regexprep(ME.message, '\s+', ' '));
end
row = summarize(public_scenario_id, eta, results, ext_report, status, note);
end

function targets = make_eta_external_targets(public_scenario_id, eta, target_file)
all_targets = readtable(target_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
s1 = all_targets(strcmp(string(all_targets.scenario_id), "S1_MEASURED_BOUNDARY"), :);
pub = all_targets(strcmp(string(all_targets.scenario_id), string(public_scenario_id)), :);
if height(s1) == 0
    error('run_ny_only_eta_continuation:MissingS1Targets', ...
        'Missing S1_MEASURED_BOUNDARY rows in %s.', target_file);
end
if height(pub) == 0
    error('run_ny_only_eta_continuation:MissingPublicTargets', ...
        'Missing public external target rows for %s.', string(public_scenario_id));
end

s1_agg = aggregate_by_boundary_bus(s1);
pub_agg = aggregate_by_boundary_bus(pub);
buses = unique([[s1_agg.bus], [pub_agg.bus]]);
buses = buses(:);
n = numel(buses);

sid = "ETA_" + string(public_scenario_id) + "_" + ...
    replace(string(sprintf('%.2f', eta)), ".", "p");
scenario_id = repmat(sid, n, 1);
timestamp = repmat(string(pub.timestamp(1)), n, 1);
external_interface_name = "ETA_BOUNDARY_BUS_" + string(buses(:));
p32_interface_name = repmat("eta_blend_s1_to_public", n, 1);
ny_boundary_bus = buses(:);
direction_positive = repmat("import_into_ny", n, 1);
nyiso_flow_mw = NaN(n, 1);
nyiso_limit_mw = NaN(n, 1);
scale_factor_gamma = repmat(first_finite(pub, 'scale_factor_gamma', NaN), n, 1);
target_flow_mw = zeros(n, 1);
target_limit_mw = zeros(n, 1);
target_q_mvar = zeros(n, 1);
v_setpoint = zeros(n, 1);
qmin_mvar = zeros(n, 1);
qmax_mvar = zeros(n, 1);

for k = 1:n
    bus = buses(k);
    a = row_for_bus(s1_agg, bus);
    b = row_for_bus(pub_agg, bus);
    target_flow_mw(k) = blend(a.p, b.p, eta);
    target_limit_mw(k) = blend(a.limit, b.limit, eta);
    target_q_mvar(k) = blend(a.q, b.q, eta);
    v_setpoint(k) = blend(a.vg, b.vg, eta);
    qmin_mvar(k) = blend(a.qmin, b.qmin, eta);
    qmax_mvar(k) = blend(a.qmax, b.qmax, eta);
    if qmin_mvar(k) > target_q_mvar(k)
        qmin_mvar(k) = target_q_mvar(k);
    end
    if qmax_mvar(k) < target_q_mvar(k)
        qmax_mvar(k) = target_q_mvar(k);
    end
end

equivalent_type = repmat("boundary_generator", n, 1);
q_mode = repmat("limited_q_support", n, 1);
note = repmat("Eta blend of S1 measured boundary injections and scaled public P-32 external schedules.", n, 1);

targets = table(scenario_id, timestamp, external_interface_name, p32_interface_name, ...
    ny_boundary_bus, direction_positive, nyiso_flow_mw, nyiso_limit_mw, ...
    scale_factor_gamma, target_flow_mw, target_limit_mw, target_q_mvar, ...
    equivalent_type, q_mode, v_setpoint, qmin_mvar, qmax_mvar, note);
end

function agg = aggregate_by_boundary_bus(tbl)
buses = unique(numeric_column(tbl, 'ny_boundary_bus'));
agg = struct('bus', num2cell(buses), 'p', [], 'q', [], 'limit', [], ...
    'qmin', [], 'qmax', [], 'vg', []);
for k = 1:numel(buses)
    mask = numeric_column(tbl, 'ny_boundary_bus') == buses(k);
    agg(k).p = sum(numeric_column(tbl(mask, :), 'target_flow_mw'));
    agg(k).q = sum(numeric_column(tbl(mask, :), 'target_q_mvar'));
    agg(k).limit = sum(numeric_column(tbl(mask, :), 'target_limit_mw'), 'omitnan');
    agg(k).qmin = sum(numeric_column(tbl(mask, :), 'qmin_mvar'));
    agg(k).qmax = sum(numeric_column(tbl(mask, :), 'qmax_mvar'));
    vg = numeric_column(tbl(mask, :), 'v_setpoint');
    agg(k).vg = vg(find(isfinite(vg), 1));
    if isempty(agg(k).vg), agg(k).vg = 1.03; end
end
end

function entry = row_for_bus(agg, bus)
idx = find([agg.bus] == bus, 1);
if isempty(idx)
    entry = struct('bus', bus, 'p', 0, 'q', 0, 'limit', 0, ...
        'qmin', 0, 'qmax', 0, 'vg', 1.03);
else
    entry = agg(idx);
end
end

function value = blend(a, b, eta)
value = (1 - eta) * a + eta * b;
end

function row = summarize(public_scenario_id, eta, results, ext_report, status, note)
define_constants;
if strcmp(status, "error")
    values = num2cell(NaN(1, 16));
    row = table(string(public_scenario_id), eta, string(status), ...
        values{:}, string(note), 'VariableNames', result_columns());
    return;
end

online = results.gen(:, GEN_STATUS) > 0;
sf = sqrt(results.branch(:, PF).^2 + results.branch(:, QF).^2);
st = sqrt(results.branch(:, PT).^2 + results.branch(:, QT).^2);
smax = max(sf, st);
rate = results.branch(:, RATE_A);
rated = rate > 0;
flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
row = table(string(public_scenario_id), eta, string(status), ...
    double(results.success), raw_info(results), results.f, sum(results.bus(:, PD)), ...
    sum(results.gen(online, PG)), sum(results.gen(online, PG)) - sum(results.bus(:, PD)), ...
    sum(ext_report.target_flow_mw), min(results.bus(:, VM)), max(results.bus(:, VM)), ...
    sum(results.bus(:, VM) >= results.bus(:, VMAX) - 1e-5), ...
    sum(results.bus(:, VM) <= results.bus(:, VMIN) + 1e-5), ...
    sum(rated & smax > rate + 1e-6), max([0; smax(rated) - rate(rated)]), ...
    interface_flow(flows, 'Total_East_proxy'), interface_flow(flows, 'UPNY_ConEd'), ...
    interface_flow(flows, 'Dunwoodie_South'), string(note), ...
    'VariableNames', result_columns());
end

function names = result_columns()
names = {'public_scenario_id','eta','status','opf_success','opf_raw_info', ...
    'objective','total_load_mw','total_generation_mw','losses_mw', ...
    'boundary_equiv_pg_mw','min_voltage','max_voltage', ...
    'voltage_upper_bound_count','voltage_lower_bound_count', ...
    'rate_a_overload_count','max_rate_a_overload_mva', ...
    'total_east_proxy_flow_mw','upny_coned_flow_mw', ...
    'dunwoodie_south_flow_mw','note'};
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

function value = first_finite(tbl, name, default_value)
if ~ismember(name, tbl.Properties.VariableNames)
    value = default_value;
    return;
end
values = numeric_column(tbl, name);
idx = find(isfinite(values), 1);
if isempty(idx), value = default_value; else, value = values(idx); end
end

function values = numeric_column(tbl, name)
if ~ismember(name, tbl.Properties.VariableNames)
    values = NaN(height(tbl), 1);
    return;
end
values = tbl.(name);
if iscell(values)
    out = NaN(numel(values), 1);
    for k = 1:numel(values)
        out(k) = numeric_value(values{k});
    end
    values = out;
elseif isstring(values)
    values = str2double(values);
end
values = double(values(:));
end

function value = numeric_value(value)
if isempty(value)
    value = NaN;
elseif isnumeric(value)
    value = double(value);
elseif isstring(value) || ischar(value)
    value = str2double(value);
else
    value = NaN;
end
end

function cleanup_temp_file(filename)
if exist(filename, 'file') == 2
    delete(filename);
end
end
