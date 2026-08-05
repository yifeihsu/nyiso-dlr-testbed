function report = run_winter_peak_pf()
%RUN_WINTER_PEAK_PF Reproduce the packaged S8 winter-peak AC power flow.
%   Requires MATPOWER on the MATLAB path. The authoritative input is the
%   full-metadata MAT file in cases/. No original project helpers are used.

root = fileparts(mfilename('fullpath'));
case_file = fullfile(root, 'cases', ...
    'npcc_ny_lite_s8_winter_peak_operating_case.mat');
map_file = fullfile(root, 'data', 'winter_peak_interface_branch_map.csv');
archive_file = fullfile(root, 'results', ...
    'winter_peak_interface_comparison.csv');
rerun_dir = fullfile(root, 'rerun_results');
if exist(rerun_dir, 'dir') ~= 7, mkdir(rerun_dir); end

loaded = load(case_file, 'mpc');
if ~isfield(loaded, 'mpc')
    error('The packaged operating-case MAT file does not contain mpc.');
end
mpc = loaded.mpc;

mpopt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 0);
results = runpf(mpc, mpopt);
if ~isfield(results, 'success') || ~logical(results.success)
    error('Standard AC PF did not converge.');
end

archived = readtable(archive_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
branch_map = readtable(map_file, 'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
comparison = calculate_interfaces(results, archived, branch_map);
max_reproduction_delta_mw = max(abs(comparison.calculated_pf_flow_mw - ...
    archived.calculated_pf_flow_mw));
if max_reproduction_delta_mw > 1e-5
    error('Packaged PF differs from archived flows by %.9g MW.', ...
        max_reproduction_delta_mw);
end

wape_pct = 100 * sum(abs(comparison.residual_mw)) / ...
    sum(abs(comparison.target_flow_mw));
mape_pct = mean(comparison.absolute_percentage_error_pct);
metrics = physical_metrics(results);

q_success = false;
q_note = "";
try
    qopt = mpoption('verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1);
    qresults = runpf(mpc, qopt);
    q_success = isfield(qresults, 'success') && logical(qresults.success);
    if ~q_success, q_note = "Q-limit PF returned success = 0"; end
catch err
    q_note = string(err.identifier) + ": " + string(err.message);
end

scenario_id = "S2_2025_WINTER_PEAK_PUBLIC";
report = table(scenario_id, logical(results.success), q_success, wape_pct, ...
    mape_pct, max(abs(comparison.residual_mw)), ...
    max_reproduction_delta_mw, metrics.losses_mw, metrics.min_voltage_pu, ...
    metrics.max_voltage_pu, metrics.voltage_violation_count, ...
    metrics.branch_overload_count, metrics.max_branch_overload_mva, q_note, ...
    'VariableNames', {'scenario_id','standard_pf_success', ...
    'q_limit_pf_success','wape_pct','mape_pct', ...
    'max_abs_interface_residual_mw','max_reproduction_delta_mw', ...
    'losses_mw','min_voltage_pu','max_voltage_pu', ...
    'voltage_violation_count','branch_overload_count', ...
    'max_branch_overload_mva','q_limit_note'});

writetable(comparison, fullfile(rerun_dir, ...
    'winter_peak_interface_comparison_rerun.csv'));
writetable(report, fullfile(rerun_dir, 'winter_peak_pf_summary_rerun.csv'));

fprintf(['Winter PF reproduced: WAPE %.6f%%, MAPE %.6f%%, ' ...
    'max interface error %.6f MW.\n'], wape_pct, mape_pct, ...
    max(abs(comparison.residual_mw)));
fprintf(['Physical diagnostics: V = %.6f to %.6f pu, ' ...
    '%d voltage violations, %d branch overloads, max %.6f MVA.\n'], ...
    metrics.min_voltage_pu, metrics.max_voltage_pu, ...
    metrics.voltage_violation_count, metrics.branch_overload_count, ...
    metrics.max_branch_overload_mva);
end

function comparison = calculate_interfaces(results, archived, branch_map)
PF = 14;
PT = 16;
n = height(archived);
flow = zeros(n, 1);
for k = 1:n
    name = archived.interface_name(k);
    rows = branch_map(branch_map.interface_name == name, :);
    if isempty(rows), error('No branch map found for %s.', name); end
    for j = 1:height(rows)
        branch_idx = rows.branch_index(j);
        if rows.flow_column(j) == "PF"
            value = results.branch(branch_idx, PF);
        elseif rows.flow_column(j) == "PT"
            value = results.branch(branch_idx, PT);
        else
            error('Unknown flow column %s.', rows.flow_column(j));
        end
        flow(k) = flow(k) + rows.sign(j) * value;
    end
end
comparison = archived(:, {'interface_name','target_flow_mw'});
comparison.calculated_pf_flow_mw = flow;
comparison.residual_mw = flow - comparison.target_flow_mw;
comparison.absolute_error_mw = abs(comparison.residual_mw);
comparison.signed_percentage_error_pct = 100 * comparison.residual_mw ./ ...
    abs(comparison.target_flow_mw);
comparison.absolute_percentage_error_pct = ...
    abs(comparison.signed_percentage_error_pct);
end

function metrics = physical_metrics(results)
RATE_A = 6;
VM = 8;
VMAX = 12;
VMIN = 13;
PF = 14;
QF = 15;
PT = 16;
QT = 17;
rate = results.branch(:, RATE_A);
sf = hypot(results.branch(:, PF), results.branch(:, QF));
st = hypot(results.branch(:, PT), results.branch(:, QT));
overload = max(sf, st) - rate;
rated = rate > 0;
metrics = struct( ...
    'losses_mw', sum(results.branch(:, PF) + results.branch(:, PT)), ...
    'min_voltage_pu', min(results.bus(:, VM)), ...
    'max_voltage_pu', max(results.bus(:, VM)), ...
    'voltage_violation_count', sum(results.bus(:, VM) < ...
        results.bus(:, VMIN) - 1e-6 | results.bus(:, VM) > ...
        results.bus(:, VMAX) + 1e-6), ...
    'branch_overload_count', sum(rated & overload > 1e-6), ...
    'max_branch_overload_mva', max([0; overload(rated)]));
end
