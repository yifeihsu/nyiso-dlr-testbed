function out = validate_s13_phase1a_oracle_artifact_consistency(options)
%VALIDATE_S13_PHASE1A_ORACLE_ARTIFACT_CONSISTENCY Verify S13.1 evidence CSVs.
%   Rebuilds the no-fit local identity, common-input readiness audit, and
%   fail-closed oracle orchestration once. Each expected table is serialized
%   with the repository LF writer and compared byte-for-byte with its
%   committed CSV. This checks schema/column order, row order, rendered data
%   types and values, and canonical LF line endings without lossy CSV import.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
if ~isfield(options, 'artifact_dir'), options.artifact_dir = helper_dir; end
if ~isfield(options, 'fail_on_mismatch'), options.fail_on_mismatch = true; end
if ~isfield(options, 'verbose'), options.verbose = true; end

addpath(fileparts(helper_dir)); addpath(helper_dir);
if isfield(options, 'oracle_result') && ~isempty(options.oracle_result)
    oracle = options.oracle_result;
else
    oracle = run_s13_phase1a_oracle_comparison(struct( ...
        'write_outputs', false, 'verbose', false, ...
        'fail_on_incomplete', false));
end

files = [ ...
    "s13_phase1a_local_identity.csv"; ...
    "s13_phase1a_local_omitted_injections.csv"; ...
    "s13_phase1a_terminal_voltage_comparison.csv"; ...
    "s13_phase1a_common_input_spec.csv"; ...
    "s13_phase1a_external_schedule_map.csv"; ...
    "s13_phase1a_control_assumption_register.csv"; ...
    "s13_phase1a_same_snapshot_comparison.csv"; ...
    "s13_phase1a_cut_flow_comparison.csv"; ...
    "s13_phase1a_physical_circuit_comparison.csv"; ...
    "s13_phase1a_heldout_response.csv"; ...
    "s13_phase1a_heldout_metric_manifest.csv"; ...
    "s13_phase1a_oracle_gate_ledger.csv"];
expected = { ...
    oracle.local_identity.local_identity; ...
    oracle.local_identity.omitted_injections; ...
    oracle.local_identity.terminal_voltages; ...
    oracle.common_input_readiness.common_input_spec; ...
    oracle.common_input_readiness.external_schedule_map; ...
    oracle.common_input_readiness.control_assumption_register; ...
    oracle.same_snapshot_comparison; ...
    oracle.cut_flow_comparison; ...
    oracle.physical_circuit_comparison; ...
    oracle.heldout_response; ...
    oracle.heldout_metric_manifest; ...
    oracle.gate_ledger};

temp_dir = tempname;
mkdir(temp_dir);
cleanup_guard = onCleanup(@() rmdir(temp_dir, 's'));

n = numel(files);
file_present = false(n, 1);
expected_rows = zeros(n, 1);
actual_rows = nan(n, 1);
schema_order_match = false(n, 1);
content_match = false(n, 1);
canonical_lf_match = false(n, 1);
pass = false(n, 1);
expected_schema = strings(n, 1);
actual_schema = strings(n, 1);
expected_types = strings(n, 1);
detail = strings(n, 1);

for k = 1:n
    artifact_path = fullfile(options.artifact_dir, files(k));
    canonical_path = fullfile(temp_dir, files(k));
    table_value = expected{k};
    if ~istable(table_value)
        error('validate_s13_phase1a_oracle_artifact_consistency:BadExpected', ...
            'Expected value for %s is not a table.', files(k));
    end
    ny_lite_writetable_lf(table_value, canonical_path);
    expected_rows(k) = height(table_value);
    expected_schema(k) = strjoin(string( ...
        table_value.Properties.VariableNames), "|");
    expected_types(k) = table_type_signature(table_value);
    file_present(k) = isfile(artifact_path);
    if ~file_present(k)
        detail(k) = "committed CSV is missing";
        continue;
    end

    expected_text = fileread(canonical_path);
    actual_text = fileread(artifact_path);
    expected_normalized = normalize_newlines(expected_text);
    actual_normalized = normalize_newlines(actual_text);
    content_match(k) = strcmp(expected_normalized, actual_normalized);
    canonical_lf_match(k) = strcmp(expected_text, actual_text) && ...
        ~contains(actual_text, sprintf('\r'));

    expected_lines = splitlines(string(expected_normalized));
    actual_lines = splitlines(string(actual_normalized));
    expected_lines = drop_final_empty(expected_lines);
    actual_lines = drop_final_empty(actual_lines);
    if ~isempty(actual_lines)
        actual_schema(k) = actual_lines(1);
        actual_rows(k) = max(numel(actual_lines) - 1, 0);
    else
        actual_schema(k) = "";
        actual_rows(k) = 0;
    end
    schema_order_match(k) = ~isempty(expected_lines) && ...
        ~isempty(actual_lines) && expected_lines(1) == actual_lines(1);
    pass(k) = content_match(k) && canonical_lf_match(k) && ...
        schema_order_match(k) && actual_rows(k) == expected_rows(k);
    if pass(k)
        detail(k) = "exact canonical LF serialization match";
    elseif content_match(k) && ~canonical_lf_match(k)
        detail(k) = "content matches but line endings are not canonical LF";
    else
        detail(k) = first_line_difference(expected_lines, actual_lines);
    end
end

checks = table(files, file_present, expected_rows, actual_rows, ...
    expected_schema, actual_schema, expected_types, schema_order_match, ...
    content_match, canonical_lf_match, pass, detail, ...
    'VariableNames', {'artifact_file','file_present','expected_rows', ...
    'actual_rows','expected_schema','actual_schema','expected_types', ...
    'schema_order_match','content_match','canonical_lf_match','pass','detail'});
all_match = all(pass);
out = struct('checks', checks, 'all_artifacts_match', all_match, ...
    'matching_artifact_count', nnz(pass), 'artifact_count', n, ...
    'oracle_status', oracle.status, 'promotion_eligible', false);

if options.verbose
    fprintf('S13.1 oracle artifact consistency: %d/%d exact matches.\n', ...
        nnz(pass), n);
end
if options.fail_on_mismatch && ~all_match
    failed = files(~pass);
    error('validate_s13_phase1a_oracle_artifact_consistency:Mismatch', ...
        'S13.1 oracle artifacts differ from rebuilt evidence: %s', ...
        strjoin(cellstr(failed), ', '));
end
clear cleanup_guard;
end

function value = normalize_newlines(value)
lf = newline;
cr = char(13);
value = strrep(value, [cr lf], lf);
value = strrep(value, cr, lf);
end

function lines = drop_final_empty(lines)
if ~isempty(lines) && lines(end) == ""
    lines(end) = [];
end
end

function detail = first_line_difference(expected, actual)
n = min(numel(expected), numel(actual));
idx = find(expected(1:n) ~= actual(1:n), 1);
if isempty(idx)
    if numel(expected) ~= numel(actual)
        detail = sprintf('line-count mismatch: expected %d, found %d', ...
            numel(expected), numel(actual));
    else
        detail = "serialized content mismatch";
    end
else
    detail = sprintf('first serialized mismatch at line %d', idx);
end
end

function signature = table_type_signature(value)
names = string(value.Properties.VariableNames);
types = strings(size(names));
for k = 1:numel(names)
    types(k) = string(class(value.(char(names(k)))));
end
signature = strjoin(names + ":" + types, "|");
end
