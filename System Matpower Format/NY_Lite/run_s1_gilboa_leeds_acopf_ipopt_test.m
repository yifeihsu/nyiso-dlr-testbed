function outputs = run_s1_gilboa_leeds_acopf_ipopt_test()
%RUN_S1_GILBOA_LEEDS_ACOPF_IPOPT_TEST Compare S1 ACOPF with IPOPT.

helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir);
addpath(helper_dir);

if ~have_feature('ipopt')
    error('run_s1_gilboa_leeds_acopf_ipopt_test:IpoptMissing', ...
        'MATPOWER does not report IPOPT as available.');
end

define_constants;

comparison_file = fullfile(helper_dir, 's1_gilboa_leeds_acopf_ipopt_comparison.csv');

mpopt = mpoption( ...
    'verbose', 0, ...
    'out.all', 0, ...
    'opf.ac.solver', 'IPOPT', ...
    'opf.flow_lim', 'S', ...
    'opf.violation', 1e-6, ...
    'opf.use_vg', 0, ...
    'opf.ignore_angle_lim', 0);

mpc_s1 = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
[mpc_s1_gl, added] = add_ny_lite_tielines(mpc_s1, 'core');

res_s1 = runopf(mpc_s1, mpopt);
res_s1_gl = runopf(mpc_s1_gl, mpopt);

write_comparison(comparison_file, res_s1, res_s1_gl, added, mpopt);

outputs = struct('comparison_file', comparison_file);
end

function write_comparison(path, res_s1, res_s1_gl, added, mpopt)
define_constants;
tol = mpopt.opf.violation;
s1 = collect_metrics(res_s1, tol, []);
gl = collect_metrics(res_s1_gl, tol, added);
dpg = res_s1_gl.gen(:, PG) - res_s1.gen(:, PG);
[max_abs_dpg, max_abs_dpg_idx] = max(abs(dpg));

rows = {
    'solver', 'IPOPT', 'IPOPT', '', '', ''
    'opf_success', double(res_s1.success), double(res_s1_gl.success), double(res_s1_gl.success) - double(res_s1.success), 'flag', ''
    'opf_raw_info', raw_info(res_s1), raw_info(res_s1_gl), raw_info(res_s1_gl) - raw_info(res_s1), 'code', ''
    'objective', res_s1.f, res_s1_gl.f, res_s1_gl.f - res_s1.f, '$/h', 'GL value is a failed-solver candidate if opf_success=0'
    'total_absolute_redispatch', 0, sum(abs(dpg)), sum(abs(dpg)), 'MW', 'sum(abs(PG_GL - PG_S1))'
    'max_single_generator_redispatch', 0, max_abs_dpg, max_abs_dpg, 'MW', sprintf('gen_idx=%d bus=%.0f', max_abs_dpg_idx, res_s1.gen(max_abs_dpg_idx, GEN_BUS))
    'branch_80_flow_mva', s1.branch80_flow_mva, gl.branch80_flow_mva, gl.branch80_flow_mva - s1.branch80_flow_mva, 'MVA', ''
    'branch_80_rate_a_mva', s1.branch80_rate_a_mva, gl.branch80_rate_a_mva, gl.branch80_rate_a_mva - s1.branch80_rate_a_mva, 'MVA', ''
    'branch_80_loading_pct', s1.branch80_loading_pct, gl.branch80_loading_pct, gl.branch80_loading_pct - s1.branch80_loading_pct, 'pct', ''
    'branch_80_overload_mva', s1.branch80_overload_mva, gl.branch80_overload_mva, gl.branch80_overload_mva - s1.branch80_overload_mva, 'MVA', ''
    'branch_190_flow_mva', s1.branch190_flow_mva, gl.branch190_flow_mva, gl.branch190_flow_mva - s1.branch190_flow_mva, 'MVA', ''
    'branch_190_rate_a_mva', s1.branch190_rate_a_mva, gl.branch190_rate_a_mva, gl.branch190_rate_a_mva - s1.branch190_rate_a_mva, 'MVA', ''
    'branch_190_loading_pct', s1.branch190_loading_pct, gl.branch190_loading_pct, gl.branch190_loading_pct - s1.branch190_loading_pct, 'pct', ''
    'gilboa_leeds_pf_mw', NaN, gl.gilboa_leeds_pf_mw, NaN, 'MW', ''
    'gilboa_leeds_qf_mvar', NaN, gl.gilboa_leeds_qf_mvar, NaN, 'MVAr', ''
    'gilboa_leeds_pt_mw', NaN, gl.gilboa_leeds_pt_mw, NaN, 'MW', ''
    'gilboa_leeds_qt_mvar', NaN, gl.gilboa_leeds_qt_mvar, NaN, 'MVAr', ''
    'gilboa_leeds_smax_mva', NaN, gl.gilboa_leeds_smax_mva, NaN, 'MVA', ''
    'total_east_proxy_flow_mw', s1.total_east_proxy_flow_mw, gl.total_east_proxy_flow_mw, gl.total_east_proxy_flow_mw - s1.total_east_proxy_flow_mw, 'MW', ''
    'upny_coned_flow_mw', s1.upny_coned_flow_mw, gl.upny_coned_flow_mw, gl.upny_coned_flow_mw - s1.upny_coned_flow_mw, 'MW', ''
    'voltage_bound_count', s1.voltage_bound_count, gl.voltage_bound_count, gl.voltage_bound_count - s1.voltage_bound_count, 'count', ''
    'binding_branch_count', s1.binding_branch_count, gl.binding_branch_count, gl.binding_branch_count - s1.binding_branch_count, 'count', ''
    'rate_a_overload_count', s1.rate_a_overload_count, gl.rate_a_overload_count, gl.rate_a_overload_count - s1.rate_a_overload_count, 'count', ''
    'max_rate_a_overload_mva', s1.max_rate_a_overload_mva, gl.max_rate_a_overload_mva, gl.max_rate_a_overload_mva - s1.max_rate_a_overload_mva, 'MVA', ''
    };

fid = fopen(path, 'w');
if fid < 0, error('Cannot open %s.', path); end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, 'metric,s1_original_opf,s1_gilboa_leeds_opf,delta_gl_minus_s1,unit,note\n');
for k = 1:size(rows, 1)
    fprintf(fid, '%s,%s,%s,%s,%s,%s\n', ...
        esc(rows{k, 1}), esc(fmt(rows{k, 2})), esc(fmt(rows{k, 3})), ...
        esc(fmt(rows{k, 4})), esc(rows{k, 5}), esc(rows{k, 6}));
end
end

function metrics = collect_metrics(results, tol, added)
define_constants;
sf = sqrt(results.branch(:, PF).^2 + results.branch(:, QF).^2);
st = sqrt(results.branch(:, PT).^2 + results.branch(:, QT).^2);
smax = max(sf, st);
rate = results.branch(:, RATE_A);
rated = rate > 0;
overload = zeros(size(rate));
overload(rated) = smax(rated) - rate(rated);

vm = results.bus(:, VM);
vmax = results.bus(:, VMAX);
vmin = results.bus(:, VMIN);
bound_tol = max(tol, 1e-5);
branch_tol = max(tol, 1e-6);

results = attach_nyiso_zone_metadata(results);
defs = ny_lite_interface_definitions(results);
flows = ny_lite_interface_flows(results, defs);

metrics.branch80_flow_mva = smax(80);
metrics.branch80_rate_a_mva = rate(80);
metrics.branch80_loading_pct = 100 * smax(80) / rate(80);
metrics.branch80_overload_mva = max(0, smax(80) - rate(80));
metrics.branch190_flow_mva = smax(190);
metrics.branch190_rate_a_mva = rate(190);
metrics.branch190_loading_pct = 100 * smax(190) / rate(190);
metrics.total_east_proxy_flow_mw = interface_flow(flows, 'Total_East_proxy');
metrics.upny_coned_flow_mw = interface_flow(flows, 'UPNY_ConEd');
metrics.voltage_bound_count = sum(abs(vm - vmax) <= bound_tol | abs(vm - vmin) <= bound_tol);
metrics.binding_branch_count = sum(rated & abs(smax - rate) <= branch_tol);
metrics.rate_a_overload_count = sum(rated & smax > rate + tol);
metrics.max_rate_a_overload_mva = max([0; overload]);

metrics.gilboa_leeds_pf_mw = NaN;
metrics.gilboa_leeds_qf_mvar = NaN;
metrics.gilboa_leeds_pt_mw = NaN;
metrics.gilboa_leeds_qt_mvar = NaN;
metrics.gilboa_leeds_smax_mva = NaN;
if ~isempty(added)
    b = added(1).branch_index;
    metrics.gilboa_leeds_pf_mw = results.branch(b, PF);
    metrics.gilboa_leeds_qf_mvar = results.branch(b, QF);
    metrics.gilboa_leeds_pt_mw = results.branch(b, PT);
    metrics.gilboa_leeds_qt_mvar = results.branch(b, QT);
    metrics.gilboa_leeds_smax_mva = smax(b);
end
end

function value = interface_flow(flows, name)
idx = find(strcmp({flows.interface_name}, name), 1);
if isempty(idx)
    value = NaN;
else
    value = flows(idx).flow_mw;
end
end

function info = raw_info(results)
if isfield(results, 'raw') && isfield(results.raw, 'info')
    info = results.raw.info;
else
    info = NaN;
end
end

function s = fmt(v)
if isnumeric(v)
    if isempty(v) || (isscalar(v) && isnan(v))
        s = '';
    elseif isscalar(v)
        s = sprintf('%.12g', v);
    else
        s = mat2str(v, 12);
    end
else
    s = char(v);
end
end

function out = esc(v)
out = char(v);
if any(out == ',') || any(out == '"') || any(out == newline)
    out = ['"' strrep(out, '"', '""') '"'];
end
end
