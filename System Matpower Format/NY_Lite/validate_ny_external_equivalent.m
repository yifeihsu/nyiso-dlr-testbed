function outputs = validate_ny_external_equivalent(options)
%VALIDATE_NY_EXTERNAL_EQUIVALENT Build and validate S1 NY-only equivalent.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
if ~isfield(options, 'target_file')
    options.target_file = fullfile(helper_dir, 'ny_external_interface_targets.csv');
end
if ~isfield(options, 'case_file')
    options.case_file = fullfile(case_dir, 'npcc_ny_lite_s1_ny_only_equiv.m');
end
if ~isfield(options, 'boundary_file')
    options.boundary_file = fullfile(helper_dir, 'ny_boundary_s1_measured_flows.csv');
end
if ~isfield(options, 'validation_file')
    options.validation_file = fullfile(helper_dir, 'ny_external_equivalent_validation_report.csv');
end
if exist(options.target_file, 'file') ~= 2
    build_ny_external_interface_targets([], struct('target_file', options.target_file));
end

define_constants;
full = loadcase('npcc_ny_lite_s1_acopf_feasible_uncalibrated');
mpopt = mpoption('verbose', 0, 'out.all', 0);
full_pf = runpf(full, mpopt);
boundary = measure_ny_boundary_flows(full_pf, "S1_MEASURED_BOUNDARY", ...
    struct('run_pf_if_needed', false));
writetable(boundary, options.boundary_file);

[ny_case, build_report] = build_ny_only_equivalent_case(full);
[ny_case, add_report] = apply_nyiso_external_interface_injections( ...
    ny_case, "S1_MEASURED_BOUNDARY", struct('target_file', options.target_file));
savecase(options.case_file, ny_case);
ny_pf = runpf(ny_case, mpopt);

rows = validation_rows(full_pf, ny_pf, build_report, add_report);
writetable(rows, options.validation_file);

outputs = struct('case_file', options.case_file, ...
    'target_file', options.target_file, ...
    'boundary_file', options.boundary_file, ...
    'validation_file', options.validation_file, ...
    'ny_pf_success', ny_pf.success, ...
    'ny_bus_count', size(ny_case.bus, 1), ...
    'ny_branch_count', size(ny_case.branch, 1), ...
    'ny_gen_count', size(ny_case.gen, 1));
end

function rows = validation_rows(full_pf, ny_pf, build_report, add_report)
define_constants;
full_pf = attach_nyiso_zone_metadata(full_pf);
ny_pf = attach_nyiso_zone_metadata(ny_pf);
ny_ids = ny_pf.bus(:, BUS_I);
[~, full_idx] = ismember(ny_ids, full_pf.bus(:, BUS_I));
vm_delta = ny_pf.bus(:, VM) - full_pf.bus(full_idx, VM);
va_delta = ny_pf.bus(:, VA) - full_pf.bus(full_idx, VA);

rows = table();
rows = add_metric(rows, 'full_pf_success', full_pf.success, 'flag', '');
rows = add_metric(rows, 'ny_equiv_pf_success', ny_pf.success, 'flag', '');
rows = add_metric(rows, 'kept_bus_count', build_report.kept_bus_count, 'count', '');
rows = add_metric(rows, 'kept_branch_count', build_report.kept_branch_count, 'count', '');
rows = add_metric(rows, 'kept_original_gen_count', build_report.kept_gen_count, 'count', '');
rows = add_metric(rows, 'added_boundary_equiv_gen_count', height(add_report), 'count', '');
rows = add_metric(rows, 'max_abs_ny_vm_delta', max(abs(vm_delta)), 'p.u.', '');
rows = add_metric(rows, 'mean_abs_ny_vm_delta', mean(abs(vm_delta)), 'p.u.', '');
rows = add_metric(rows, 'max_abs_ny_va_delta', max(abs(va_delta)), 'deg', 'angle reference differs after reduction');
rows = add_metric(rows, 'full_ny_load_mw', sum(full_pf.bus(full_idx, PD)), 'MW', '');
rows = add_metric(rows, 'ny_equiv_load_mw', sum(ny_pf.bus(:, PD)), 'MW', '');
rows = add_metric(rows, 'full_ny_generation_mw', sum(full_pf.gen(ismember(full_pf.gen(:, GEN_BUS), ny_ids), PG)), 'MW', 'NY generators only');
rows = add_metric(rows, 'ny_equiv_total_generation_mw', sum(ny_pf.gen(:, PG)), 'MW', 'includes boundary equivalents');
rows = add_metric(rows, 'boundary_equiv_pg_mw', sum(add_report.target_flow_mw), 'MW', 'positive is import into NY');
rows = add_metric(rows, 'boundary_equiv_qg_mvar', sum(add_report.target_q_mvar), 'MVAr', 'positive is injection into NY');

full_flows = ny_lite_interface_flows(full_pf, ny_lite_interface_definitions(full_pf));
ny_flows = ny_lite_interface_flows(ny_pf, ny_lite_interface_definitions(ny_pf));
for k = 1:numel(full_flows)
    name = full_flows(k).interface_name;
    idx = find(strcmp({ny_flows.interface_name}, name), 1);
    if isempty(idx), continue; end
    rows = add_metric(rows, ['interface_delta_' name], ...
        ny_flows(idx).flow_mw - full_flows(k).flow_mw, 'MW', ...
        'NY-only equivalent minus full S1 PF');
end
end

function rows = add_metric(rows, metric, value, unit, note)
row = table(string(metric), value, string(unit), string(note), ...
    'VariableNames', {'metric','value','unit','note'});
rows = [rows; row];
end
