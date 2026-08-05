function outputs = run_s1_acopf_feasible_uncalibrated_build()
%RUN_S1_ACOPF_FEASIBLE_UNCALIBRATED_BUILD Create ACOPF-feasible S1 artifacts.
%   Builds npcc_ny_lite_s1_acopf_feasible_uncalibrated.m from the AC OPF
%   result of S0, records OPF settings, validates that S0 metadata does not
%   change the original network equations, and runs topology-only PF checks.

helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir);
addpath(helper_dir);

if exist('runopf', 'file') ~= 2 || exist('savecase', 'file') ~= 2
    error('run_s1_acopf_feasible_uncalibrated_build:MatpowerMissing', ...
        'MATPOWER runopf/savecase are required.');
end

define_constants;

case_file = fullfile(case_dir, 'npcc_ny_lite_s1_acopf_feasible_uncalibrated.m');
feasibility_file = fullfile(helper_dir, 's1_acopf_feasibility_report.csv');
settings_file = fullfile(helper_dir, 's1_acopf_opf_settings.csv');
metadata_file = fullfile(helper_dir, 's1_acopf_metadata_validation.csv');
topology_file = fullfile(helper_dir, 's1_acopf_topology_comparison.csv');

mpopt = s1_acopf_options();
original_case = loadcase('npcc_original');
s0_case = npcc_ny_lite_v0_baseline;

original_opf = runopf(original_case, mpopt);
s0_opf = runopf(s0_case, mpopt);
if ~original_opf.success || ~s0_opf.success
    error('run_s1_acopf_feasible_uncalibrated_build:OpfFailed', ...
        'AC OPF failed for original or S0 case.');
end

s1_case = solved_case_from_opf(s0_opf);
s1_case = attach_nyiso_zone_metadata(s1_case);
s1_case.userdata.ny_lite.case_version = 's1_acopf_feasible_uncalibrated';
s1_case.userdata.ny_lite.description = ...
    'ACOPF feasible uncalibrated scenario generated from S0, not embedded S0 PG.';
s1_case.userdata.ny_lite.source_case = 'npcc_ny_lite_v0_baseline';
s1_case.userdata.ny_lite.opf_settings_file = settings_file;
savecase(case_file, s1_case);

write_feasibility_report(feasibility_file, s0_opf, mpopt);
write_opf_settings(settings_file, mpopt);
write_metadata_validation(metadata_file, original_opf, s0_opf);
write_topology_comparison(topology_file, case_file);

outputs = struct( ...
    'case_file', case_file, ...
    'feasibility_report', feasibility_file, ...
    'opf_settings', settings_file, ...
    'metadata_validation', metadata_file, ...
    'topology_comparison', topology_file);
end

function mpopt = s1_acopf_options()
mpopt = mpoption( ...
    'verbose', 0, ...
    'out.all', 0, ...
    'opf.ac.solver', 'MIPS', ...
    'opf.flow_lim', 'S', ...
    'opf.violation', 1e-6, ...
    'opf.use_vg', 0, ...
    'opf.ignore_angle_lim', 0, ...
    'mips.max_it', 500);
end

function mpc = solved_case_from_opf(results)
mpc = struct();
mpc.version = results.version;
mpc.baseMVA = results.baseMVA;
mpc.bus = results.bus(:, 1:13);
mpc.gen = results.gen(:, 1:min(21, size(results.gen, 2)));
mpc.branch = results.branch(:, 1:13);
if isfield(results, 'gencost')
    mpc.gencost = results.gencost;
end
if isfield(results, 'bus_name')
    mpc.bus_name = results.bus_name;
end
end

function write_feasibility_report(path, results, mpopt)
define_constants;
metrics = opf_metrics(results, mpopt);
rows = {
    'objective', metrics.objective, '$/h', 'runopf', ''
    'total_load_mw', metrics.total_load_mw, 'MW', 'runopf', ''
    'total_generation_mw', metrics.total_generation_mw, 'MW', 'runopf', ''
    'losses_mw', metrics.losses_mw, 'MW', 'runopf', ''
    'min_voltage', metrics.min_voltage, 'p.u.', 'runopf', ''
    'max_voltage', metrics.max_voltage, 'p.u.', 'runopf', ''
    'number_of_generators_at_pmax', metrics.number_of_generators_at_pmax, 'count', 'audit', ''
    'number_of_generators_at_pmin', metrics.number_of_generators_at_pmin, 'count', 'audit', ''
    'number_of_voltage_bounds', metrics.number_of_voltage_bounds, 'count', 'audit', ''
    'number_of_binding_branches', metrics.number_of_binding_branches, 'count', 'audit', ''
    'number_of_rate_a_overloads', metrics.number_of_rate_a_overloads, 'count', 'audit', ''
    'max_rate_a_overload_mva', metrics.max_rate_a_overload_mva, 'MVA', 'audit', ''
    'branch_190_flow_mva', metrics.branch_190_flow_mva, 'MVA', 'audit', 'max of from/to apparent flow'
    'branch_190_rate_a_mva', metrics.branch_190_rate_a_mva, 'MVA', 'case', ''
    };
write_metric_csv(path, rows);
end

function write_opf_settings(path, mpopt)
rows = {
    'mpopt.opf.ac.solver', mpopt.opf.ac.solver, '', 'mpoption', ''
    'mpopt.opf.flow_lim', mpopt.opf.flow_lim, '', 'mpoption', 'S means apparent-power MVA branch limits'
    'mpopt.opf.violation', mpopt.opf.violation, '', 'mpoption', ''
    'mpopt.opf.use_vg', mpopt.opf.use_vg, '', 'mpoption', ''
    'mpopt.opf.ignore_angle_lim', mpopt.opf.ignore_angle_lim, '', 'mpoption', ''
    };
write_metric_csv(path, rows);
end

function write_metadata_validation(path, original_opf, s0_opf)
define_constants;
eps_threshold = 1e-8;
sf_original = original_opf.branch(:, PF) + 1j * original_opf.branch(:, QF);
st_original = original_opf.branch(:, PT) + 1j * original_opf.branch(:, QT);
sf_s0 = s0_opf.branch(:, PF) + 1j * s0_opf.branch(:, QF);
st_s0 = s0_opf.branch(:, PT) + 1j * s0_opf.branch(:, QT);
max_pg = max(abs(original_opf.gen(:, PG) - s0_opf.gen(:, PG)));
max_v = max(abs(original_opf.bus(:, VM) - s0_opf.bus(:, VM)));
max_s = max(abs([sf_original - sf_s0; st_original - st_s0]));
pass = max_pg < eps_threshold && max_v < eps_threshold && max_s < eps_threshold;
rows = {
    'epsilon_threshold', eps_threshold, '', 'audit', ''
    'max_abs_pg_orig_minus_s0', max_pg, 'MW', 'runopf', ''
    'max_abs_vm_orig_minus_s0', max_v, 'p.u.', 'runopf', ''
    'max_abs_sbranch_orig_minus_s0', max_s, 'MVA', 'runopf', 'max of complex from/to branch flow differences'
    'metadata_validation_pass', double(pass), 'flag', 'audit', '1 means S0 metadata did not alter network equations'
    };
write_metric_csv(path, rows);
end

function write_topology_comparison(path, case_file)
define_constants;
mpopt = mpoption('verbose', 0, 'out.all', 0);
rows = {};

s1_base = loadcase(case_file);
s1_base = attach_nyiso_zone_metadata(s1_base);
rows = append_variant_rows(rows, 'S1 original topology', s1_base, [], mpopt, '');

[s1_core, added] = add_ny_lite_tielines(s1_base, 'core');
rows = append_variant_rows(rows, 'S1 plus Gilboa-Leeds', s1_core, added, mpopt, '');

try
    load_opts = struct('preserve_total_ny_load', true);
    [s1_core_load, load_report] = apply_nyiso_zonal_loads( ...
        s1_core, 'S1_PERFORM_COMPATIBLE_PEAK', 1.0, load_opts); %#ok<ASGLU>
    rows = append_variant_rows(rows, ...
        'S1 plus Gilboa-Leeds plus zonal load adjustment', ...
        s1_core_load, added, mpopt, 'S1_PERFORM_COMPATIBLE_PEAK');
catch ME
    rows(end+1,:) = { ...
        'S1 plus Gilboa-Leeds plus zonal load adjustment', ...
        'status', 'not_run', '', 'apply_nyiso_zonal_loads', ...
        [ME.identifier ': ' compact_message(ME.message)]}; %#ok<AGROW>
end

write_variant_metric_csv(path, rows);
end

function rows = append_variant_rows(rows, variant, mpc, added, mpopt, note)
define_constants;
try
    results = runpf(mpc, mpopt);
catch ME
    rows(end+1,:) = {variant, 'status', 'error', '', 'runpf', ...
        [ME.identifier ': ' compact_message(ME.message)]}; %#ok<AGROW>
    return;
end

if results.success
    results = attach_nyiso_zone_metadata(results);
end

metrics = pf_metrics(results);
rows(end+1,:) = {variant, 'status', 'ok', '', 'runpf', note}; %#ok<AGROW>
rows(end+1,:) = {variant, 'power_flow_success', double(results.success), 'flag', 'runpf', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'objective', metrics.objective, '$/h', 'dispatch_cost', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'total_load_mw', metrics.total_load_mw, 'MW', 'runpf', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'total_generation_mw', metrics.total_generation_mw, 'MW', 'runpf', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'losses_mw', metrics.losses_mw, 'MW', 'runpf', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'min_voltage', metrics.min_voltage, 'p.u.', 'runpf', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'max_voltage', metrics.max_voltage, 'p.u.', 'runpf', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'number_of_voltage_bounds', metrics.number_of_voltage_bounds, 'count', 'audit', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'number_of_voltage_violations', metrics.number_of_voltage_violations, 'count', 'audit', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'number_of_binding_branches', metrics.number_of_binding_branches, 'count', 'audit', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'number_of_rate_a_overloads', metrics.number_of_rate_a_overloads, 'count', 'audit', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'max_rate_a_overload_mva', metrics.max_rate_a_overload_mva, 'MVA', 'audit', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'worst_rate_a_branch_index', metrics.worst_rate_a_branch_index, 'index', 'audit', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'worst_rate_a_branch_from_to', metrics.worst_rate_a_branch_from_to, 'bus_pair', 'audit', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'worst_rate_a_branch_flow_mva', metrics.worst_rate_a_branch_flow_mva, 'MVA', 'audit', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'worst_rate_a_branch_rate_a_mva', metrics.worst_rate_a_branch_rate_a_mva, 'MVA', 'case', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'branch_190_flow_mva', metrics.branch_190_flow_mva, 'MVA', 'audit', 'max of from/to apparent flow'}; %#ok<AGROW>
rows(end+1,:) = {variant, 'branch_190_rate_a_mva', metrics.branch_190_rate_a_mva, 'MVA', 'case', ''}; %#ok<AGROW>
rows(end+1,:) = {variant, 'branch_190_loading_pct', metrics.branch_190_loading_pct, 'pct', 'audit', ''}; %#ok<AGROW>

if results.success
    defs = ny_lite_interface_definitions(results);
    flows = ny_lite_interface_flows(results, defs);
    for k = 1:numel(flows)
        rows(end+1,:) = {variant, ['interface_' flows(k).interface_name], ...
            flows(k).flow_mw, 'MW', 'runpf', flows(k).zone_boundary}; %#ok<AGROW>
    end
end

if ~isempty(added)
    b = added(1).branch_index;
    rows(end+1,:) = {variant, 'gilboa_leeds_branch_index', b, 'index', 'case', added(1).name}; %#ok<AGROW>
    if results.success && b <= size(results.branch, 1)
        pf = results.branch(b, PF);
        qf = results.branch(b, QF);
        pt = results.branch(b, PT);
        qt = results.branch(b, QT);
        rows(end+1,:) = {variant, 'gilboa_leeds_pf_mw', pf, 'MW', 'runpf', ''}; %#ok<AGROW>
        rows(end+1,:) = {variant, 'gilboa_leeds_qf_mvar', qf, 'MVAr', 'runpf', ''}; %#ok<AGROW>
        rows(end+1,:) = {variant, 'gilboa_leeds_pt_mw', pt, 'MW', 'runpf', ''}; %#ok<AGROW>
        rows(end+1,:) = {variant, 'gilboa_leeds_qt_mvar', qt, 'MVAr', 'runpf', ''}; %#ok<AGROW>
        rows(end+1,:) = {variant, 'gilboa_leeds_reactive_injection_mvar', ...
            -(qf + qt), 'MVAr', 'audit', '-(QF + QT), positive means branch injects MVAr into buses'}; %#ok<AGROW>
    end
end
end

function metrics = opf_metrics(results, mpopt)
define_constants;
metrics = common_solution_metrics(results, mpopt.opf.violation);
metrics.objective = results.f;
end

function metrics = pf_metrics(results)
metrics = common_solution_metrics(results, 1e-5);
metrics.objective = dispatch_objective(results);
end

function metrics = common_solution_metrics(results, tol)
define_constants;
online = results.gen(:, GEN_STATUS) > 0;
sf = sqrt(results.branch(:, PF).^2 + results.branch(:, QF).^2);
st = sqrt(results.branch(:, PT).^2 + results.branch(:, QT).^2);
smax = max(sf, st);
rate = results.branch(:, RATE_A);
rated = rate > 0;
vm = results.bus(:, VM);
vmax = results.bus(:, VMAX);
vmin = results.bus(:, VMIN);

binding_branch = false(size(rate));
binding_branch(rated) = abs(smax(rated) - rate(rated)) <= max(tol, 1e-6);
overload = zeros(size(rate));
overload(rated) = smax(rated) - rate(rated);
[max_overload, worst_rate_idx] = max(overload);

metrics.total_load_mw = sum(results.bus(:, PD));
metrics.total_generation_mw = sum(results.gen(online, PG));
metrics.losses_mw = metrics.total_generation_mw - metrics.total_load_mw;
metrics.min_voltage = min(vm);
metrics.max_voltage = max(vm);
metrics.number_of_generators_at_pmax = sum(online & abs(results.gen(:, PG) - results.gen(:, PMAX)) <= max(tol, 1e-5));
metrics.number_of_generators_at_pmin = sum(online & abs(results.gen(:, PG) - results.gen(:, PMIN)) <= max(tol, 1e-5));
metrics.number_of_voltage_bounds = sum(abs(vm - vmax) <= max(tol, 1e-5) | abs(vm - vmin) <= max(tol, 1e-5));
metrics.number_of_voltage_violations = sum(vm > vmax + tol | vm < vmin - tol);
metrics.number_of_binding_branches = sum(binding_branch);
metrics.number_of_rate_a_overloads = sum(rated & smax > rate + tol);
if max_overload > tol
    metrics.max_rate_a_overload_mva = max_overload;
else
    metrics.max_rate_a_overload_mva = 0;
end
metrics.worst_rate_a_branch_index = worst_rate_idx;
metrics.worst_rate_a_branch_from_to = sprintf('%.0f-%.0f', ...
    results.branch(worst_rate_idx, F_BUS), results.branch(worst_rate_idx, T_BUS));
metrics.worst_rate_a_branch_flow_mva = smax(worst_rate_idx);
metrics.worst_rate_a_branch_rate_a_mva = rate(worst_rate_idx);
metrics.branch_190_flow_mva = smax(190);
metrics.branch_190_rate_a_mva = rate(190);
metrics.branch_190_loading_pct = 100 * smax(190) / rate(190);
end

function value = dispatch_objective(mpc)
define_constants;
if ~isfield(mpc, 'gencost') || isempty(mpc.gencost)
    value = NaN;
else
    value = sum(totcost(mpc.gencost, mpc.gen(:, PG)));
end
end

function write_metric_csv(path, rows)
fid = fopen(path, 'w');
if fid < 0
    error('run_s1_acopf_feasible_uncalibrated_build:CannotOpenFile', ...
        'Cannot open %s.', path);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, 'metric,value,unit,source,note\n');
for k = 1:size(rows, 1)
    fprintf(fid, '%s,%s,%s,%s,%s\n', ...
        csv_escape(rows{k, 1}), csv_escape(format_value(rows{k, 2})), ...
        csv_escape(rows{k, 3}), csv_escape(rows{k, 4}), csv_escape(rows{k, 5}));
end
end

function write_variant_metric_csv(path, rows)
fid = fopen(path, 'w');
if fid < 0
    error('run_s1_acopf_feasible_uncalibrated_build:CannotOpenFile', ...
        'Cannot open %s.', path);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, 'variant,metric,value,unit,source,note\n');
for k = 1:size(rows, 1)
    fprintf(fid, '%s,%s,%s,%s,%s,%s\n', ...
        csv_escape(rows{k, 1}), csv_escape(rows{k, 2}), ...
        csv_escape(format_value(rows{k, 3})), csv_escape(rows{k, 4}), ...
        csv_escape(rows{k, 5}), csv_escape(rows{k, 6}));
end
end

function s = format_value(v)
if isnumeric(v)
    if isempty(v) || (isscalar(v) && isnan(v))
        s = '';
    elseif isscalar(v)
        s = sprintf('%.12g', v);
    else
        s = mat2str(v, 12);
    end
elseif islogical(v)
    s = sprintf('%d', v);
else
    s = char(v);
end
end

function out = csv_escape(v)
out = char(v);
if any(out == ',') || any(out == '"') || any(out == newline)
    out = ['"' strrep(out, '"', '""') '"'];
end
end

function msg = compact_message(msg)
msg = regexprep(char(msg), '\s+', ' ');
end
