function outputs = run_nyiso_public_acopf_relaxed_gen_limits(options)
%RUN_NYISO_PUBLIC_ACOPF_RELAXED_GEN_LIMITS Diagnose OPF with relaxed gen limits.
%   Modes:
%     q_limits_relaxed  - widen only QMIN/QMAX
%     pq_limits_relaxed - widen QMIN/QMAX and relax active PMIN/PMAX

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
if ~isfield(options, 'scenario_file')
    options.scenario_file = fullfile(helper_dir, 'nyiso_public_scenarios.csv');
end
if ~isfield(options, 'output_file')
    options.output_file = fullfile(helper_dir, 'nyiso_public_acopf_relaxed_gen_limits.csv');
end
if ~isfield(options, 'variants')
    options.variants = {'original_topology', 'gilboa_leeds'};
end
if ~isfield(options, 'limit_modes')
    options.limit_modes = {'q_limits_relaxed', 'pq_limits_relaxed'};
end
if ~isfield(options, 'q_abs_limit_mvar'), options.q_abs_limit_mvar = 1e5; end
if ~isfield(options, 'pmax_limit_mw'), options.pmax_limit_mw = 1e5; end
if ~isfield(options, 'pmin_limit_mw'), options.pmin_limit_mw = 0; end

define_constants;
scenarios = readtable(options.scenario_file, ...
    'TextType', 'string', 'VariableNamingRule', 'preserve');
mpopt = mpoption( ...
    'verbose', 0, ...
    'out.all', 0, ...
    'opf.ac.solver', 'IPOPT', ...
    'opf.flow_lim', 'S', ...
    'opf.violation', 1e-6, ...
    'opf.use_vg', 0, ...
    'opf.ignore_angle_lim', 0, ...
    'ipopt.opts.max_iter', 1000);

rows = table();
for s = 1:height(scenarios)
    scenario_id = string(scenarios.scenario_id(s));
    for v = 1:numel(options.variants)
        variant = string(options.variants{v});
        for m = 1:numel(options.limit_modes)
            limit_mode = string(options.limit_modes{m});
            [results, status, note] = solve_case(scenario_id, variant, ...
                limit_mode, mpopt, options);
            row = summarize_result(scenario_id, string(scenarios.timestamp(s)), ...
                variant, limit_mode, results, status, note, options);
            rows = [rows; row]; %#ok<AGROW>
        end
    end
end

writetable(rows, options.output_file);
outputs = struct('output_file', options.output_file, 'row_count', height(rows));
end

function [results, status, note] = solve_case(scenario_id, variant, limit_mode, mpopt, options)
define_constants;
status = "ok";
note = "";
try
    mpc = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
    [mpc, ~] = apply_nyiso_zonal_loads(mpc, scenario_id, 1.0, ...
        struct('preserve_total_ny_load', true));
    if strcmpi(variant, 'gilboa_leeds')
        [mpc, ~] = add_ny_lite_tielines(mpc, 'core');
    elseif ~strcmpi(variant, 'original_topology')
        error('run_nyiso_public_acopf_relaxed_gen_limits:BadVariant', ...
            'Unknown variant %s.', variant);
    end
    if strcmpi(limit_mode, 'q_limits_relaxed')
        mpc.gen(:, QMIN) = -options.q_abs_limit_mvar;
        mpc.gen(:, QMAX) = options.q_abs_limit_mvar;
    elseif strcmpi(limit_mode, 'pq_limits_relaxed')
        mpc.gen(:, QMIN) = -options.q_abs_limit_mvar;
        mpc.gen(:, QMAX) = options.q_abs_limit_mvar;
        mpc.gen(:, PMIN) = options.pmin_limit_mw;
        mpc.gen(:, PMAX) = options.pmax_limit_mw;
    else
        error('run_nyiso_public_acopf_relaxed_gen_limits:BadLimitMode', ...
            'Unknown limit mode %s.', limit_mode);
    end
    results = runopf(mpc, mpopt);
catch ME
    results = struct();
    status = "error";
    note = string(regexprep(ME.message, '\s+', ' '));
end
end

function row = summarize_result(scenario_id, timestamp, variant, limit_mode, results, status, note, options)
define_constants;
if strcmp(status, "error")
    values = num2cell(NaN(1, 24));
    row = table(string(scenario_id), string(timestamp), string(variant), ...
        string(limit_mode), string(status), values{:}, string(note), ...
        'VariableNames', result_columns());
    return;
end

online = results.gen(:, GEN_STATUS) > 0;
sf = sqrt(results.branch(:, PF).^2 + results.branch(:, QF).^2);
st = sqrt(results.branch(:, PT).^2 + results.branch(:, QT).^2);
smax = max(sf, st);
rate = results.branch(:, RATE_A);
rated = rate > 0;
tol = 1e-5;

voltage_upper_count = sum(results.bus(:, VM) >= results.bus(:, VMAX) - tol);
voltage_lower_count = sum(results.bus(:, VM) <= results.bus(:, VMIN) + tol);
q_at_max = sum(online & results.gen(:, QG) >= results.gen(:, QMAX) - 1e-4);
q_at_min = sum(online & results.gen(:, QG) <= results.gen(:, QMIN) + 1e-4);
p_at_max = sum(online & results.gen(:, PG) >= results.gen(:, PMAX) - 1e-4);
p_at_min = sum(online & results.gen(:, PG) <= results.gen(:, PMIN) + 1e-4);

row = table(string(scenario_id), string(timestamp), string(variant), ...
    string(limit_mode), string(status), double(results.success), raw_info(results), ...
    results.f, sum(results.bus(:, PD)), sum(results.gen(online, PG)), ...
    sum(results.gen(online, PG)) - sum(results.bus(:, PD)), ...
    sum(results.bus(:, QD)), sum(results.gen(online, QG)), ...
    min(results.bus(:, VM)), max(results.bus(:, VM)), ...
    voltage_upper_count, voltage_lower_count, ...
    min(results.gen(online, QG)), max(results.gen(online, QG)), ...
    sum(abs(results.gen(online, QG))), q_at_max, q_at_min, ...
    p_at_max, p_at_min, ...
    sum(rated & smax > rate + 1e-6), max([0; smax(rated) - rate(rated)]), ...
    smax(80) / rate(80) * 100, smax(190) / rate(190) * 100, ...
    options.q_abs_limit_mvar, string(note), ...
    'VariableNames', result_columns());
end

function names = result_columns()
names = {'scenario_id','timestamp','variant','limit_mode','status', ...
    'opf_success','opf_raw_info','objective','total_load_mw', ...
    'total_generation_mw','losses_mw','total_qd_mvar','total_qg_mvar', ...
    'min_voltage','max_voltage','voltage_upper_bound_count', ...
    'voltage_lower_bound_count','min_qg_mvar','max_qg_mvar', ...
    'sum_abs_qg_mvar','number_of_generators_at_qmax', ...
    'number_of_generators_at_qmin','number_of_generators_at_pmax', ...
    'number_of_generators_at_pmin','rate_a_overload_count', ...
    'max_rate_a_overload_mva','branch80_loading_pct', ...
    'branch190_loading_pct','q_abs_limit_mvar','note'};
end

function info = raw_info(results)
if isfield(results, 'raw') && isfield(results.raw, 'info')
    info = results.raw.info;
else
    info = NaN;
end
end
