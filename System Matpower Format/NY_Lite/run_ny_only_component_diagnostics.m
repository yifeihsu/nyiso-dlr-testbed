function outputs = run_ny_only_component_diagnostics(options)
%RUN_NY_ONLY_COMPONENT_DIAGNOSTICS Isolate load, external, P, and Q effects.
%
%   Produces two CSVs:
%     1. NY-only ACOPF feasibility for load-only/external-only continuations
%        and P-only/Q-only public-load component tests.
%     2. Zone-level reactive and voltage component diagnostics.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'ny_external_interface_targets.csv');
end
if ~isfield(options, 'eta_grid'), options.eta_grid = 0:0.1:1; end
if ~isfield(options, 'summary_file')
    options.summary_file = fullfile(helper_dir, ...
        'ny_only_component_diagnostics_summary.csv');
end
if ~isfield(options, 'zone_file')
    options.zone_file = fullfile(helper_dir, ...
        'ny_only_component_diagnostics_zone_q.csv');
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
base_ny = attach_nyiso_zone_metadata(base_ny);

summary_rows = table();
zone_rows = table();
for s = 1:height(public_scenarios)
    scenario_id = string(public_scenarios.scenario_id(s));
    for k = 1:numel(options.eta_grid)
        eta = options.eta_grid(k);
        [row, zrows] = run_case(base_ny, scenario_id, ...
            "LOAD_ONLY_S1_BOUNDARY", eta, "load_only", mpopt, options);
        summary_rows = [summary_rows; row]; %#ok<AGROW>
        zone_rows = [zone_rows; zrows]; %#ok<AGROW>

        [row, zrows] = run_case(base_ny, scenario_id, ...
            "EXTERNAL_ONLY_S1_LOAD", eta, "external_only", mpopt, options);
        summary_rows = [summary_rows; row]; %#ok<AGROW>
        zone_rows = [zone_rows; zrows]; %#ok<AGROW>
    end

    component_modes = ["P_ONLY_S1_BOUNDARY", "Q_ONLY_S1_BOUNDARY", ...
        "P_ONLY_PUBLIC_EXTERNAL", "Q_ONLY_PUBLIC_EXTERNAL"];
    for k = 1:numel(component_modes)
        [row, zrows] = run_case(base_ny, scenario_id, component_modes(k), ...
            NaN, lower(component_modes(k)), mpopt, options);
        summary_rows = [summary_rows; row]; %#ok<AGROW>
        zone_rows = [zone_rows; zrows]; %#ok<AGROW>
    end
end

writetable(summary_rows, options.summary_file);
writetable(zone_rows, options.zone_file);
outputs = struct('summary_file', options.summary_file, ...
    'zone_file', options.zone_file, ...
    'summary_row_count', height(summary_rows), ...
    'zone_row_count', height(zone_rows));
end

function [row, zrows] = run_case(base_ny, public_scenario_id, experiment, eta, mode, mpopt, options)
define_constants;
status = "ok";
note = "";
mpc = base_ny;
ext_report = table();
try
    switch string(mode)
        case "load_only"
            [mpc, ~] = apply_nyiso_zonal_loads(mpc, public_scenario_id, eta, ...
                struct('preserve_total_ny_load', true));
            [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
                "S1_MEASURED_BOUNDARY", struct('target_file', options.target_file));

        case "external_only"
            eta_targets = make_eta_external_targets(public_scenario_id, eta, options.target_file);
            [mpc, ext_report] = apply_temp_external_targets(mpc, eta_targets);

        case "p_only_s1_boundary"
            mpc = apply_public_p_or_q_component(mpc, public_scenario_id, true, false);
            [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
                "S1_MEASURED_BOUNDARY", struct('target_file', options.target_file));

        case "q_only_s1_boundary"
            mpc = apply_public_p_or_q_component(mpc, public_scenario_id, false, true);
            [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
                "S1_MEASURED_BOUNDARY", struct('target_file', options.target_file));

        case "p_only_public_external"
            mpc = apply_public_p_or_q_component(mpc, public_scenario_id, true, false);
            [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
                public_scenario_id, struct('target_file', options.target_file));

        case "q_only_public_external"
            mpc = apply_public_p_or_q_component(mpc, public_scenario_id, false, true);
            [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
                public_scenario_id, struct('target_file', options.target_file));

        otherwise
            error('run_ny_only_component_diagnostics:UnknownMode', ...
                'Unknown diagnostic mode %s.', string(mode));
    end
    original_vmin = mpc.bus(:, VMIN);
    original_vmax = mpc.bus(:, VMAX);
    results = runopf(mpc, mpopt);
catch ME
    results = struct();
    original_vmin = NaN(size(mpc.bus, 1), 1);
    original_vmax = NaN(size(mpc.bus, 1), 1);
    status = "error";
    note = string(regexprep(ME.message, '\s+', ' '));
end

row = summarize(public_scenario_id, experiment, eta, results, ext_report, status, note);
zrows = zone_summary(public_scenario_id, experiment, eta, results, mpc, ...
    ext_report, original_vmin, original_vmax, status);
end

function mpc = apply_public_p_or_q_component(mpc, public_scenario_id, use_public_p, use_public_q)
define_constants;
s1_pd = mpc.bus(:, PD);
s1_qd = mpc.bus(:, QD);
[public_mpc, ~] = apply_nyiso_zonal_loads(mpc, public_scenario_id, 1.0, ...
    struct('preserve_total_ny_load', true));
if use_public_p
    mpc.bus(:, PD) = public_mpc.bus(:, PD);
else
    mpc.bus(:, PD) = s1_pd;
end
if use_public_q
    mpc.bus(:, QD) = public_mpc.bus(:, QD);
else
    mpc.bus(:, QD) = s1_qd;
end
end

function [mpc, ext_report] = apply_temp_external_targets(mpc, eta_targets)
tmp_file = [tempname, '.csv'];
cleanup = onCleanup(@() cleanup_temp_file(tmp_file)); %#ok<NASGU>
writetable(eta_targets, tmp_file);
target_id = string(eta_targets.scenario_id(1));
[mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
    target_id, struct('target_file', tmp_file));
end

function row = summarize(public_scenario_id, experiment, eta, results, ext_report, status, note)
define_constants;
if strcmp(status, "error")
    values = num2cell(NaN(1, 17));
    row = table(string(public_scenario_id), string(experiment), eta, ...
        string(status), values{:}, string(note), 'VariableNames', summary_columns());
    return;
end

online = results.gen(:, GEN_STATUS) > 0;
sf = sqrt(results.branch(:, PF).^2 + results.branch(:, QF).^2);
st = sqrt(results.branch(:, PT).^2 + results.branch(:, QT).^2);
smax = max(sf, st);
rate = results.branch(:, RATE_A);
rated = rate > 0;
flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
row = table(string(public_scenario_id), string(experiment), eta, string(status), ...
    double(results.success), raw_info(results), results.f, sum(results.bus(:, PD)), ...
    sum(results.bus(:, QD)), sum(results.gen(online, PG)), ...
    sum(results.gen(online, QG)), ext_sum(ext_report, 'target_flow_mw'), ...
    ext_sum(ext_report, 'target_q_mvar'), min(results.bus(:, VM)), ...
    max(results.bus(:, VM)), sum(results.bus(:, VM) >= results.bus(:, VMAX) - 1e-5), ...
    sum(results.bus(:, VM) <= results.bus(:, VMIN) + 1e-5), ...
    sum(rated & smax > rate + 1e-6), max([0; smax(rated) - rate(rated)]), ...
    interface_flow(flows, 'Total_East_proxy'), interface_flow(flows, 'UPNY_ConEd'), ...
    string(note), 'VariableNames', summary_columns());
end

function names = summary_columns()
names = {'scenario_id','experiment','eta','status','opf_success','opf_raw_info', ...
    'objective','total_pd_mw','total_qd_mvar','total_pg_mw','total_qg_mvar', ...
    'boundary_target_p_mw','boundary_target_q_mvar','min_voltage','max_voltage', ...
    'at_vmax_count','at_vmin_count','rate_a_overload_count', ...
    'max_rate_a_overload_mva','total_east_proxy_flow_mw', ...
    'upny_coned_flow_mw','note'};
end

function rows = zone_summary(public_scenario_id, experiment, eta, results, mpc, ...
    ext_report, original_vmin, original_vmax, status)
define_constants;
if strcmp(status, "error") || ~isfield(results, 'bus')
    rows = table();
    return;
end

mpc = attach_nyiso_zone_metadata(mpc);
zones = unique(string(mpc.userdata.nyiso_physical_zone), 'stable');
zones(strlength(zones) == 0) = [];
ext_idx = [];
    if istable(ext_report) && ismember('added_gen_index', ext_report.Properties.VariableNames)
        ext_idx = ext_report.added_gen_index;
    end
rows = table();
for z = 1:numel(zones)
    zone = zones(z);
    bmask = strcmp(string(mpc.userdata.nyiso_physical_zone), zone);
    bus_ids = mpc.bus(bmask, BUS_I);
    gmask = ismember(results.gen(:, GEN_BUS), bus_ids) & results.gen(:, GEN_STATUS) > 0;
    gen_index = (1:size(results.gen, 1))';
    boundary_gmask = gmask & ismember(gen_index, ext_idx);
    original_gmask = gmask & ~boundary_gmask;
    branch_q_out = zone_branch_q_out(results, bus_ids);
    charging_scale = zone_branch_charging_scale(results, mpc, bus_ids);
    row = table(string(public_scenario_id), string(experiment), eta, ...
        double(results.success), zone, first_zone_name(mpc, bmask), ...
        sum(bmask), sum(results.bus(bmask, PD)), sum(results.bus(bmask, QD)), ...
        sum(results.gen(original_gmask, QG)), sum(results.gen(boundary_gmask, QG)), ...
        sum(results.gen(gmask, QG)), charging_scale, branch_q_out, ...
        min(results.bus(bmask, VM)), max(results.bus(bmask, VM)), ...
        sum(results.bus(bmask, VM) > original_vmax(bmask) + 1e-5), ...
        sum(results.bus(bmask, VM) < original_vmin(bmask) - 1e-5), ...
        'VariableNames', zone_columns());
    rows = [rows; row]; %#ok<AGROW>
end
end

function names = zone_columns()
names = {'scenario_id','experiment','eta','opf_success','zone','zone_name', ...
    'bus_count','pd_mw','qd_mvar','original_gen_q_mvar', ...
    'boundary_gen_q_mvar','total_gen_q_mvar','incident_charging_scale_mvar', ...
    'branch_terminal_q_out_mvar','min_voltage','max_voltage', ...
    'above_original_vmax_count','below_original_vmin_count'};
end

function qout = zone_branch_q_out(results, bus_ids)
define_constants;
qout = 0;
for k = 1:size(results.branch, 1)
    if ismember(results.branch(k, F_BUS), bus_ids)
        qout = qout + results.branch(k, QF);
    end
    if ismember(results.branch(k, T_BUS), bus_ids)
        qout = qout + results.branch(k, QT);
    end
end
end

function qchg = zone_branch_charging_scale(results, mpc, bus_ids)
define_constants;
qchg = 0;
for k = 1:size(results.branch, 1)
    br_b = results.branch(k, BR_B);
    if br_b == 0, continue; end
    fbus = results.branch(k, F_BUS);
    tbus = results.branch(k, T_BUS);
    if ismember(fbus, bus_ids)
        fidx = find(mpc.bus(:, BUS_I) == fbus, 1);
        qchg = qchg + 0.5 * br_b * mpc.baseMVA * results.bus(fidx, VM)^2;
    end
    if ismember(tbus, bus_ids)
        tidx = find(mpc.bus(:, BUS_I) == tbus, 1);
        qchg = qchg + 0.5 * br_b * mpc.baseMVA * results.bus(tidx, VM)^2;
    end
end
end

function value = first_zone_name(mpc, bmask)
names = string(mpc.userdata.nyiso_zone_name(bmask));
if isempty(names), value = ""; else, value = names(1); end
end

function targets = make_eta_external_targets(public_scenario_id, eta, target_file)
all_targets = readtable(target_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
s1 = all_targets(strcmp(string(all_targets.scenario_id), "S1_MEASURED_BOUNDARY"), :);
pub = all_targets(strcmp(string(all_targets.scenario_id), string(public_scenario_id)), :);
if height(s1) == 0 || height(pub) == 0
    error('run_ny_only_component_diagnostics:MissingTargets', ...
        'Missing S1 or public external target rows for %s.', string(public_scenario_id));
end

s1_agg = aggregate_by_boundary_bus(s1);
pub_agg = aggregate_by_boundary_bus(pub);
buses = unique([[s1_agg.bus], [pub_agg.bus]]);
buses = buses(:);
n = numel(buses);

sid = "EXTETA_" + string(public_scenario_id) + "_" + ...
    replace(string(sprintf('%.2f', eta)), ".", "p");
scenario_id = repmat(sid, n, 1);
timestamp = repmat(string(pub.timestamp(1)), n, 1);
external_interface_name = "EXTETA_BOUNDARY_BUS_" + string(buses(:));
p32_interface_name = repmat("external_eta_blend_s1_to_public", n, 1);
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
    qmin_mvar(k) = min(qmin_mvar(k), target_q_mvar(k));
    qmax_mvar(k) = max(qmax_mvar(k), target_q_mvar(k));
end

equivalent_type = repmat("boundary_generator", n, 1);
q_mode = repmat("limited_q_support", n, 1);
note = repmat("External-only eta blend of S1 measured and public P-32 boundary schedules.", n, 1);
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
    idx = find(isfinite(vg), 1);
    if isempty(idx), agg(k).vg = 1.03; else, agg(k).vg = vg(idx); end
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

function value = ext_sum(tbl, name)
if istable(tbl) && ismember(name, tbl.Properties.VariableNames)
    value = sum(tbl.(name));
else
    value = NaN;
end
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
