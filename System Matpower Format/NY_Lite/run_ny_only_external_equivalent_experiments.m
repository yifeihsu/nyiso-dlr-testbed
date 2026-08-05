function outputs = run_ny_only_external_equivalent_experiments(options)
%RUN_NY_ONLY_EXTERNAL_EQUIVALENT_EXPERIMENTS Run Case B/C/D NY-only OPFs.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'ny_external_interface_targets.csv');
end
if ~isfield(options, 'output_file')
    options.output_file = fullfile(helper_dir, 'ny_only_external_equivalent_experiments.csv');
end
if exist(options.target_file, 'file') ~= 2
    build_ny_external_interface_targets([], struct('target_file', options.target_file));
end

define_constants;
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

rows = table();
rows = [rows; run_one("B_S1_LOAD_S1_BOUNDARY", "", "S1_MEASURED_BOUNDARY", mpopt, options)]; %#ok<AGROW>
for s = 1:height(public_scenarios)
    scenario_id = string(public_scenarios.scenario_id(s));
    rows = [rows; run_one("C_S1_LOAD_PUBLIC_EXTERNAL", "", scenario_id, mpopt, options)]; %#ok<AGROW>
    rows = [rows; run_one("D_PUBLIC_LOAD_PUBLIC_EXTERNAL", scenario_id, scenario_id, mpopt, options)]; %#ok<AGROW>
end

writetable(rows, options.output_file);
outputs = struct('output_file', options.output_file, 'row_count', height(rows));
end

function row = run_one(experiment, load_scenario_id, external_scenario_id, mpopt, options)
define_constants;
status = "ok";
note = "";
try
    base = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
    [mpc, ~] = build_ny_only_equivalent_case(base);
    if strlength(load_scenario_id) > 0
        [mpc, ~] = apply_nyiso_zonal_loads(mpc, load_scenario_id, 1.0, ...
            struct('preserve_total_ny_load', true));
    end
    [mpc, ext_report] = apply_nyiso_external_interface_injections(mpc, ...
        external_scenario_id, struct('target_file', options.target_file));
    results = runopf(mpc, mpopt);
catch ME
    results = struct();
    ext_report = table();
    status = "error";
    note = string(regexprep(ME.message, '\s+', ' '));
end
row = summarize(experiment, load_scenario_id, external_scenario_id, ...
    results, ext_report, status, note);
end

function row = summarize(experiment, load_scenario_id, external_scenario_id, results, ext_report, status, note)
define_constants;
if strcmp(status, "error")
    values = num2cell(NaN(1, 17));
    row = table(string(experiment), string(load_scenario_id), ...
        string(external_scenario_id), string(status), values{:}, string(note), ...
        'VariableNames', result_columns());
    return;
end
online = results.gen(:, GEN_STATUS) > 0;
sf = sqrt(results.branch(:, PF).^2 + results.branch(:, QF).^2);
st = sqrt(results.branch(:, PT).^2 + results.branch(:, QT).^2);
smax = max(sf, st);
rate = results.branch(:, RATE_A);
rated = rate > 0;
flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
row = table(string(experiment), string(load_scenario_id), ...
    string(external_scenario_id), string(status), double(results.success), ...
    raw_info(results), results.f, sum(results.bus(:, PD)), ...
    sum(results.gen(online, PG)), sum(results.gen(online, PG)) - sum(results.bus(:, PD)), ...
    sum(ext_report.target_flow_mw), sum(ext_report.target_q_mvar), ...
    min(results.bus(:, VM)), max(results.bus(:, VM)), ...
    sum(results.bus(:, VM) >= results.bus(:, VMAX) - 1e-5), ...
    sum(results.bus(:, VM) <= results.bus(:, VMIN) + 1e-5), ...
    sum(rated & smax > rate + 1e-6), max([0; smax(rated) - rate(rated)]), ...
    interface_flow(flows, 'Total_East_proxy'), interface_flow(flows, 'UPNY_ConEd'), ...
    interface_flow(flows, 'Dunwoodie_South'), string(note), ...
    'VariableNames', result_columns());
end

function names = result_columns()
names = {'experiment','load_scenario_id','external_scenario_id','status', ...
    'opf_success','opf_raw_info','objective','total_load_mw', ...
    'total_generation_mw','losses_mw','boundary_equiv_pg_mw', ...
    'boundary_equiv_qg_mvar','min_voltage','max_voltage', ...
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
