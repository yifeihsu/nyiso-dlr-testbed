function out = s12_generate_interface_snapshot_sums(options)
%S12_GENERATE_INTERFACE_SNAPSHOT_SUMS Build the authoritative S12 sidecar.
%   The caller must first run s12_update_te_operator so the rich S12 MAT
%   case and operator CSV contain the complete eight-circuit Total East
%   operator. Set write_output=false for a read-only recomputation.

if nargin < 1, options = struct(); end
if ~isfield(options, 'write_output'), options.write_output = true; end
if ~isfield(options, 'verbose'), options.verbose = true; end

helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
root = fileparts(case_dir);
perform_dir = fullfile(root, 'PERFORM', ...
    'On Peak 2019 v23_Perform_NY', 'On Peak 2019 v23');
addpath(root, case_dir, helper_dir, perform_dir);
define_constants;

case_data = load(fullfile(helper_dir, 's12_case.mat'), 's12');
s12 = case_data.s12;
assert(isfield(s12, 'userdata') && ...
    isfield(s12.userdata, 's12_interface_operators'), ...
    'S12 rich case is missing interface operators.');
op = s12.userdata.s12_interface_operators;
assert(istable(op) && ~isempty(op), ...
    'S12 interface operators must be a nonempty table.');

te = op(op.interface_name == "Total_East_proxy", :);
expected_te_source_rows = sort([935; 1345; 1346; 1567; 1568; 1609; 1612; 2136]);
assert(height(te) == 8 && ...
    numel(unique(te.source_branch)) == 8 && ...
    isequal(sort(te.source_branch), expected_te_source_rows), ...
    ['Run s12_update_te_operator before snapshot-sum generation: ' ...
    'Total_East_proxy must contain exactly eight source circuits.']);

source_case = loadcase('nyiso_On_Peak_v23_shunts_as_z_load');
source_results = runpf(source_case, mpoption( ...
    'verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1));
assert(source_results.success == 1, ...
    'Source PERFORM Q-limit power flow did not converge.');

reduction = load(fullfile(helper_dir, 's12_reduction_workspace.mat'), 'red');
reduced_case = reduction.red;
assert(size(reduced_case.gen, 1) == size(source_results.gen, 1), ...
    'Source and reduced generator rows are not aligned.');
for g = 1:size(reduced_case.gen, 1)
    if reduced_case.gen(g, GEN_STATUS) > 0
        reduced_case.gen(g, PG) = source_results.gen(g, PG);
        reduced_case.gen(g, QG) = source_results.gen(g, QG);
        reduced_case.gen(g, VG) = ...
            reduced_case.bus(reduced_case.gen(g, GEN_BUS), VM);
    end
end
reduced_results = runpf(reduced_case, mpoption('verbose', 0, 'out.all', 0));
assert(reduced_results.success == 1, ...
    'S12 reduced snapshot power flow did not converge.');

if options.verbose
    fprintf('\nSnapshot interface sums (MW):\n');
end
interface_names = sort(unique(op.interface_name));
summary = table();
for k = 1:numel(interface_names)
    rows = op(op.interface_name == interface_names(k), :);
    source_mw = sum(rows.sign .* ...
        source_results.branch(rows.source_branch, PF));
    reduced_mw = sum(rows.sign .* ...
        reduced_results.branch(rows.reduced_branch, PF));
    if options.verbose
        fprintf('  %-18s source %9.2f  reduced %9.2f  circuits %d\n', ...
            interface_names(k), source_mw, reduced_mw, height(rows));
    end
    summary = [summary; table(interface_names(k), height(rows), ...
        source_mw, reduced_mw, 'VariableNames', {'interface_name', ...
        'circuit_count', 'source_snapshot_mw', ...
        'reduced_snapshot_mw'})]; %#ok<AGROW>
end

output_file = fullfile(helper_dir, 's12_interface_snapshot_sums.csv');
if options.write_output
    ny_lite_writetable_lf(summary, output_file);
end
out = struct('summary', summary, 'operator', op, ...
    'source_results', source_results, 'reduced_results', reduced_results, ...
    'output_file', string(output_file));
end
