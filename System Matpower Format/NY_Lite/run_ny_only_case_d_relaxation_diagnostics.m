function outputs = run_ny_only_case_d_relaxation_diagnostics(options)
%RUN_NY_ONLY_CASE_D_RELAXATION_DIAGNOSTICS Diagnose reduced Case D failures.
%
%   Runs public-load/public-external NY-only Case D for each public scenario:
%     1. DCOPF with MIPS
%     2. DCOPF with IPOPT
%     3. DCOPF with IPOPT and branch ratings removed
%     4. ACOPF with normal constraints
%     5. ACOPF with branch ratings removed
%     6. ACOPF with relaxed voltage bounds
%     7. ACOPF with branch ratings removed and relaxed voltage bounds

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

if ~isfield(options, 'output_file')
    options.output_file = fullfile(helper_dir, ...
        'ny_only_case_d_relaxation_diagnostics.csv');
end
if ~isfield(options, 'relaxed_vmin'), options.relaxed_vmin = 0.50; end
if ~isfield(options, 'relaxed_vmax'), options.relaxed_vmax = 1.50; end

public_scenarios = readtable(fullfile(helper_dir, 'nyiso_public_scenarios.csv'), ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');

ac_mpopt = mpoption( ...
    'verbose', 0, ...
    'out.all', 0, ...
    'opf.ac.solver', 'IPOPT', ...
    'opf.flow_lim', 'S', ...
    'opf.violation', 1e-6, ...
    'opf.use_vg', 0, ...
    'opf.ignore_angle_lim', 0);
dc_mips_mpopt = mpoption( ...
    'verbose', 0, ...
    'out.all', 0, ...
    'model', 'DC', ...
    'opf.dc.solver', 'MIPS', ...
    'opf.violation', 1e-6, ...
    'opf.ignore_angle_lim', 0);
dc_ipopt_mpopt = mpoption( ...
    'verbose', 0, ...
    'out.all', 0, ...
    'model', 'DC', ...
    'opf.dc.solver', 'IPOPT', ...
    'opf.violation', 1e-6, ...
    'opf.ignore_angle_lim', 0);

rows = table();
for s = 1:height(public_scenarios)
    scenario_id = string(public_scenarios.scenario_id(s));
    base = make_case_d(scenario_id);
    rows = [rows; run_variant(base, scenario_id, "DCOPF_MIPS", ...
        false, false, dc_mips_mpopt, options)]; %#ok<AGROW>
    rows = [rows; run_variant(base, scenario_id, "DCOPF_IPOPT", ...
        false, false, dc_ipopt_mpopt, options)]; %#ok<AGROW>
    rows = [rows; run_variant(base, scenario_id, "DCOPF_IPOPT_NO_RATINGS", ...
        true, false, dc_ipopt_mpopt, options)]; %#ok<AGROW>
    rows = [rows; run_variant(base, scenario_id, "ACOPF_NORMAL", ...
        false, false, ac_mpopt, options)]; %#ok<AGROW>
    rows = [rows; run_variant(base, scenario_id, "ACOPF_NO_RATINGS", ...
        true, false, ac_mpopt, options)]; %#ok<AGROW>
    rows = [rows; run_variant(base, scenario_id, "ACOPF_RELAXED_V", ...
        false, true, ac_mpopt, options)]; %#ok<AGROW>
    rows = [rows; run_variant(base, scenario_id, "ACOPF_RELAXED_V_NO_RATINGS", ...
        true, true, ac_mpopt, options)]; %#ok<AGROW>
end

writetable(rows, options.output_file);
outputs = struct('output_file', options.output_file, 'row_count', height(rows));
end

function mpc = make_case_d(scenario_id)
base = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
[mpc, ~] = build_ny_only_equivalent_case(base);
[mpc, ~] = apply_nyiso_zonal_loads(mpc, scenario_id, 1.0, ...
    struct('preserve_total_ny_load', true));
[mpc, ~] = apply_nyiso_external_interface_injections(mpc, scenario_id);
end

function row = run_variant(base, scenario_id, variant, relax_ratings, relax_voltage, mpopt, options)
define_constants;
mpc = base;
original_rate_a = mpc.branch(:, RATE_A);
original_vmin = mpc.bus(:, VMIN);
original_vmax = mpc.bus(:, VMAX);
note = "";
status = "ok";

if relax_ratings
    mpc.branch(:, RATE_A) = 0;
    if size(mpc.branch, 2) >= RATE_B, mpc.branch(:, RATE_B) = 0; end
    if size(mpc.branch, 2) >= RATE_C, mpc.branch(:, RATE_C) = 0; end
end
if relax_voltage
    mpc.bus(:, VMIN) = options.relaxed_vmin;
    mpc.bus(:, VMAX) = options.relaxed_vmax;
end

try
    if startsWith(variant, "DCOPF")
        results = rundcopf(mpc, mpopt);
    else
        results = runopf(mpc, mpopt);
    end
catch ME
    status = "error";
    note = string(regexprep(ME.message, '\s+', ' '));
    results = struct();
end

row = summarize(results, scenario_id, variant, relax_ratings, relax_voltage, ...
    original_rate_a, original_vmin, original_vmax, status, note);
end

function row = summarize(results, scenario_id, variant, relax_ratings, relax_voltage, ...
    original_rate_a, original_vmin, original_vmax, status, note)
define_constants;
if strcmp(status, "error")
    values = num2cell(NaN(1, 20));
    row = table(string(scenario_id), string(variant), logical(relax_ratings), ...
        logical(relax_voltage), string(status), values{:}, string(note), ...
        'VariableNames', result_columns());
    return;
end

online = results.gen(:, GEN_STATUS) > 0;
model = "AC";
if startsWith(string(variant), "DCOPF"), model = "DC"; end

flow = branch_loading(results, model);
rated_original = original_rate_a > 0;
rated_solver = results.branch(:, RATE_A) > 0;

flows = safe_interface_flows(results);
row = table(string(scenario_id), string(variant), logical(relax_ratings), ...
    logical(relax_voltage), string(status), model, double(results.success), ...
    raw_info(results), results.f, sum(results.bus(:, PD)), ...
    sum(results.gen(online, PG)), sum(results.gen(online, PG)) - sum(results.bus(:, PD)), ...
    boundary_equiv_pg(results), min(results.bus(:, VM)), max(results.bus(:, VM)), ...
    sum(results.bus(:, VM) > original_vmax + 1e-5), ...
    sum(results.bus(:, VM) < original_vmin - 1e-5), ...
    sum(results.bus(:, VM) >= results.bus(:, VMAX) - 1e-5), ...
    sum(results.bus(:, VM) <= results.bus(:, VMIN) + 1e-5), ...
    sum(rated_original & flow > original_rate_a + 1e-6), ...
    max([0; flow(rated_original) - original_rate_a(rated_original)]), ...
    sum(rated_solver & flow > results.branch(:, RATE_A) + 1e-6), ...
    max([0; flow(rated_solver) - results.branch(rated_solver, RATE_A)]), ...
    interface_flow(flows, 'Total_East_proxy'), ...
    interface_flow(flows, 'UPNY_ConEd'), ...
    interface_flow(flows, 'Dunwoodie_South'), string(note), ...
    'VariableNames', result_columns());
end

function names = result_columns()
names = {'scenario_id','variant','ratings_relaxed','voltage_relaxed','status', ...
    'model','opf_success','opf_raw_info','objective','total_load_mw', ...
    'total_generation_mw','generation_minus_load_mw','boundary_equiv_pg_mw', ...
    'min_voltage','max_voltage','above_original_vmax_count', ...
    'below_original_vmin_count','at_solver_vmax_count','at_solver_vmin_count', ...
    'original_rate_overload_count','max_original_rate_overload_mva', ...
    'solver_rate_overload_count','max_solver_rate_overload_mva', ...
    'total_east_proxy_flow_mw','upny_coned_flow_mw', ...
    'dunwoodie_south_flow_mw','note'};
end

function loading = branch_loading(results, model)
define_constants;
if strcmp(model, "DC") || size(results.branch, 2) < QT
    loading = max(abs(results.branch(:, PF)), abs(results.branch(:, PT)));
else
    sf = sqrt(results.branch(:, PF).^2 + results.branch(:, QF).^2);
    st = sqrt(results.branch(:, PT).^2 + results.branch(:, QT).^2);
    loading = max(sf, st);
end
end

function value = boundary_equiv_pg(results)
define_constants;
value = NaN;
if isfield(results, 'userdata') && isfield(results.userdata, 'ny_only_equivalent') && ...
        isfield(results.userdata.ny_only_equivalent, 'external_equivalent_generators')
    tbl = results.userdata.ny_only_equivalent.external_equivalent_generators;
    if ismember('added_gen_index', tbl.Properties.VariableNames)
        idx = tbl.added_gen_index;
        value = sum(results.gen(idx, PG));
    end
end
end

function info = raw_info(results)
if isfield(results, 'raw') && isfield(results.raw, 'info')
    info = results.raw.info;
else
    info = NaN;
end
end

function flows = safe_interface_flows(results)
try
    flows = ny_lite_interface_flows(results, ny_lite_interface_definitions(results));
catch
    flows = struct([]);
end
end

function value = interface_flow(flows, name)
if isempty(flows)
    value = NaN;
    return;
end
idx = find(strcmp({flows.interface_name}, name), 1);
if isempty(idx), value = NaN; else, value = flows(idx).flow_mw; end
end
