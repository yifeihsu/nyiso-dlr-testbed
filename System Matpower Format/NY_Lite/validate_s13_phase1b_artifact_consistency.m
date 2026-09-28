function out = validate_s13_phase1b_artifact_consistency(options)
%VALIDATE_S13_PHASE1B_ARTIFACT_CONSISTENCY Verify committed Phase 1B evidence.
%   Rebuilds or loads the cumulative S13-FULL Phase 1B candidate, reruns the
%   no-fit local-identity and UPNY proxy validators without failing early,
%   and compares seven committed CSVs against the fresh in-memory tables.
%   Schema, column order, expected data type, row order, values, and LF
%   serialization must match exactly. Existing cumulative S13 and immutable
%   Phase 1A evidence are independently revalidated in the same transaction.
%
%   WRITE_OUTPUTS defaults to false. When true, the seven Phase 1B evidence
%   CSVs are regenerated before comparison and an eighth, non-self-compared
%   consistency ledger is written.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
options = defaults(options, helper_dir);
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

if options.write_outputs && ~isfolder(options.artifact_dir)
    error('validate_s13_phase1b_artifact_consistency:OutputDirectory', ...
        'Artifact output directory does not exist: %s', options.artifact_dir);
end

[candidate, candidate_name] = load_candidate(options.candidate_case);
[phase1a_report, phase1b_report] = phase_reports(candidate);

local = run_s13_phase1b_local_identity(struct( ...
    's13_case', candidate, 'output_dir', options.artifact_dir, ...
    'write_outputs', options.write_outputs, 'verbose', false, ...
    'fail_on_gate', false));
operator = validate_s13_phase1b_upny_operator(struct( ...
    'candidate_case', candidate, 'output_dir', options.artifact_dir, ...
    'write_outputs', options.write_outputs, 'verbose', false, ...
    'fail_on_gate', false));

required_phase1b = {'generation_audit', 'terminal_reuse_audit'};
for k = 1:numel(required_phase1b)
    field = required_phase1b{k};
    if ~isfield(phase1b_report, field) || ...
            ~istable(phase1b_report.(field))
        error('validate_s13_phase1b_artifact_consistency:Phase1BReport', ...
            'Phase 1B report table %s is missing.', field);
    end
end

files = [ ...
    "s13_phase1b_local_identity.csv"; ...
    "s13_phase1b_local_omitted_injections.csv"; ...
    "s13_phase1b_terminal_voltage_comparison.csv"; ...
    "s13_phase1b_gate_ledger.csv"; ...
    "s13_phase1b_operator_validation.csv"; ...
    "s13_phase1b_generation_audit.csv"; ...
    "s13_phase1b_terminal_reuse_audit.csv"];
report_field = [ ...
    "local_identity.local_identity"; ...
    "local_identity.omitted_injections"; ...
    "local_identity.terminal_voltages"; ...
    "local_identity.gate_ledger"; ...
    "operator_validation.gate_ledger"; ...
    "phase1b_report.generation_audit"; ...
    "phase1b_report.terminal_reuse_audit"];
expected = { ...
    local.local_identity; ...
    local.omitted_injections; ...
    local.terminal_voltages; ...
    local.gate_ledger; ...
    operator.gate_ledger; ...
    phase1b_report.generation_audit; ...
    phase1b_report.terminal_reuse_audit};

if options.write_outputs
    ny_lite_writetable_lf(phase1b_report.generation_audit, ...
        fullfile(options.artifact_dir, files(6)));
    ny_lite_writetable_lf(phase1b_report.terminal_reuse_audit, ...
        fullfile(options.artifact_dir, files(7)));
end

temp_dir = tempname;
mkdir(temp_dir);
cleanup_guard = onCleanup(@() remove_temp_dir(temp_dir));

n = numel(files);
file_present = false(n, 1);
read_success = false(n, 1);
expected_rows = zeros(n, 1);
actual_rows = nan(n, 1);
expected_schema = strings(n, 1);
actual_schema = strings(n, 1);
expected_types = strings(n, 1);
actual_types = strings(n, 1);
schema_order_match = false(n, 1);
type_match = false(n, 1);
row_order_value_match = false(n, 1);
canonical_content_match = false(n, 1);
canonical_lf_match = false(n, 1);
pass = false(n, 1);
detail = strings(n, 1);

for k = 1:n
    artifact_path = fullfile(options.artifact_dir, files(k));
    canonical_path = fullfile(temp_dir, files(k));
    table_value = expected{k};
    if ~istable(table_value)
        error('validate_s13_phase1b_artifact_consistency:ExpectedTable', ...
            'Expected Phase 1B value for %s is not a table.', files(k));
    end
    ny_lite_writetable_lf(table_value, canonical_path);
    expected_rows(k) = height(table_value);
    expected_schema(k) = schema_signature(table_value);
    expected_types(k) = type_signature(table_value);
    file_present(k) = isfile(artifact_path);
    if ~file_present(k)
        detail(k) = "committed CSV is missing";
        continue;
    end
    try
        [actual, imported_names, lexical_types_ok] = ...
            read_csv_with_expected_types(artifact_path, table_value);
        read_success(k) = true;
        actual_rows(k) = height(actual);
        actual_schema(k) = strjoin(string(imported_names), "|");
        actual_types(k) = type_signature(actual);
    catch ex
        detail(k) = "CSV import failed: " + string(ex.identifier) + ...
            " - " + string(ex.message);
        continue;
    end
    schema_order_match(k) = isequal(imported_names, ...
        table_value.Properties.VariableNames);
    type_match(k) = schema_order_match(k) && lexical_types_ok && ...
        table_types_match(table_value, actual);
    expected_text = fileread(canonical_path);
    actual_text = fileread(artifact_path);
    expected_normalized = normalize_newlines(expected_text);
    actual_normalized = normalize_newlines(actual_text);
    canonical_content_match(k) = strcmp(expected_normalized, ...
        actual_normalized);
    canonical_lf_match(k) = strcmp(expected_text, actual_text) && ...
        ~contains(actual_text, sprintf('\r'));
    % The canonical writer deliberately rounds floating-point text. Exact
    % value/order equality therefore means identical canonical serialization,
    % while the typed import separately proves the expected type contract.
    row_order_value_match(k) = type_match(k) && ...
        actual_rows(k) == expected_rows(k) && canonical_content_match(k);
    pass(k) = schema_order_match(k) && type_match(k) && ...
        row_order_value_match(k) && canonical_lf_match(k);
    if pass(k)
        detail(k) = "exact schema/type/order/value and canonical LF match";
    elseif ~schema_order_match(k)
        detail(k) = "schema or column-order mismatch";
    elseif ~type_match(k)
        detail(k) = "expected variable-type contract mismatch";
    elseif actual_rows(k) ~= expected_rows(k)
        detail(k) = sprintf('row-count mismatch: expected %d, found %d', ...
            expected_rows(k), actual_rows(k));
    elseif ~row_order_value_match(k)
        detail(k) = first_value_mismatch(table_value, actual);
    elseif ~canonical_lf_match(k)
        detail(k) = "content or canonical LF serialization mismatch";
    end
end

checks = table(files, report_field, file_present, read_success, ...
    expected_rows, actual_rows, expected_schema, actual_schema, ...
    expected_types, actual_types, schema_order_match, type_match, ...
    row_order_value_match, canonical_content_match, canonical_lf_match, ...
    pass, detail, ...
    'VariableNames', {'artifact_file','report_field','file_present', ...
    'read_success','expected_rows','actual_rows','expected_schema', ...
    'actual_schema','expected_types','actual_types','schema_order_match', ...
    'type_match','row_order_value_match','canonical_content_match', ...
    'canonical_lf_match','pass','detail'});

% Revalidate the cumulative register/structural ledger without trusting the
% Phase 1B sidecars that were just compared.
cumulative = validate_s13_artifact_consistency(struct( ...
    'candidate_case', candidate, 'artifact_dir', options.artifact_dir, ...
    'fail_on_mismatch', false));

% Rebuild the Phase 1A oracle preflight once and pass that fresh result into
% its canonical artifact validator, avoiding a second oracle execution.
oracle = run_s13_phase1a_oracle_comparison(struct( ...
    'write_outputs', false, 'verbose', false, ...
    'fail_on_incomplete', false));
phase1a_oracle = validate_s13_phase1a_oracle_artifact_consistency(struct( ...
    'artifact_dir', options.artifact_dir, 'oracle_result', oracle, ...
    'fail_on_mismatch', false, 'verbose', false));

fresh_phase1a = build_s13_phase1a_candidate(struct( ...
    'write_outputs', false, 'verbose', false));
phase1a_report_exact = isequaln(phase1a_report, ...
    fresh_phase1a.phase1a_report);
phase1a_rows_exact = logical(local.phase1a_physical_rows_bit_identical);

dependency_id = [ ...
    "phase1b_local_identity_mandatory_gates"; ...
    "phase1b_operator_mandatory_proxy_gates"; ...
    "cumulative_s13_artifacts_exact"; ...
    "phase1a_oracle_artifacts_exact"; ...
    "phase1a_report_exact_rebuild"; ...
    "phase1a_physical_rows_bit_identical"];
dependency_class = ["phase1b_validation"; "phase1b_validation"; ...
    "cumulative_evidence"; "immutable_phase1a_evidence"; ...
    "immutable_phase1a_evidence"; "immutable_phase1a_evidence"];
dependency_pass = [logical(local.pass); logical(operator.pass); ...
    logical(cumulative.all_artifacts_match); ...
    logical(phase1a_oracle.all_artifacts_match); ...
    phase1a_report_exact; phase1a_rows_exact];
dependency_detail = [ ...
    sprintf('%d/%d mandatory local-identity gates pass', ...
        nnz(local.gate_ledger.pass & local.gate_ledger.mandatory), ...
        nnz(local.gate_ledger.mandatory)); ...
    sprintf('%d/%d mandatory proxy gates pass', ...
        operator.mandatory_proxy_pass_count, ...
        operator.mandatory_proxy_gate_count); ...
    sprintf('%d/%d cumulative register/ledger artifacts match', ...
        cumulative.matched_artifact_count, cumulative.artifact_count); ...
    sprintf('%d/%d immutable Phase 1A oracle artifacts match', ...
        phase1a_oracle.matching_artifact_count, ...
        phase1a_oracle.artifact_count); ...
    string(ternary_detail(phase1a_report_exact, ...
        'candidate Phase 1A report equals a fresh rebuild', ...
        'candidate Phase 1A report differs from a fresh rebuild')); ...
    string(ternary_detail(phase1a_rows_exact, ...
        'candidate Phase 1A physical rows are bit-identical', ...
        'candidate Phase 1A physical rows changed'))];
dependency_checks = table(dependency_id, dependency_class, ...
    dependency_pass, dependency_detail, ...
    'VariableNames', {'check_id','check_class','pass','detail'});

all_artifacts_match = height(checks) == 7 && all(checks.pass) && ...
    all(dependency_checks.pass);
ledger_file = fullfile(options.artifact_dir, ...
    's13_phase1b_artifact_consistency.csv');
ledger = build_ledger(checks, dependency_checks);
if options.write_outputs
    ny_lite_writetable_lf(ledger, ledger_file);
end

out = struct( ...
    'candidate_name', candidate_name, ...
    'artifact_dir', string(options.artifact_dir), ...
    'checks', checks, ...
    'dependency_checks', dependency_checks, ...
    'ledger', ledger, ...
    'artifact_count', height(checks), ...
    'matched_artifact_count', nnz(checks.pass), ...
    'dependency_count', height(dependency_checks), ...
    'passed_dependency_count', nnz(dependency_checks.pass), ...
    'all_artifacts_match', all_artifacts_match, ...
    'phase1b_local_identity', local, ...
    'phase1b_operator_validation', operator, ...
    'cumulative_artifact_consistency', cumulative, ...
    'phase1a_oracle_artifact_consistency', phase1a_oracle, ...
    'phase1a_report_exact_rebuild', phase1a_report_exact, ...
    'phase1a_physical_rows_bit_identical', phase1a_rows_exact, ...
    'ledger_file', string(ledger_file), ...
    'promotion_eligible', false);

if options.verbose
    fprintf(['S13 Phase 1B artifact consistency: %d/%d artifacts and ' ...
        '%d/%d dependencies pass.\n'], nnz(checks.pass), height(checks), ...
        nnz(dependency_checks.pass), height(dependency_checks));
end
if options.fail_on_mismatch && ~all_artifacts_match
    failed_files = checks.artifact_file(~checks.pass);
    failed_dependencies = dependency_checks.check_id(~dependency_checks.pass);
    failed = [failed_files; failed_dependencies];
    error('validate_s13_phase1b_artifact_consistency:ArtifactMismatch', ...
        'S13 Phase 1B artifact consistency failed: %s', ...
        strjoin(cellstr(failed), ', '));
end
clear cleanup_guard;
end

function options = defaults(options, helper_dir)
if ~isfield(options, 'candidate_case')
    options.candidate_case = 'npcc_ny_lite_s13_npcc_augmented_2019';
end
if ~isfield(options, 'artifact_dir'), options.artifact_dir = helper_dir; end
if ~isfield(options, 'write_outputs'), options.write_outputs = false; end
if ~isfield(options, 'fail_on_mismatch'), options.fail_on_mismatch = true; end
if ~isfield(options, 'verbose'), options.verbose = true; end
end

function [candidate, name] = load_candidate(value)
if isstruct(value)
    candidate = value;
    name = "provided_s13_phase1b_candidate";
else
    candidate = loadcase(value);
    name = string(value);
end
end

function [phase1a, phase1b] = phase_reports(candidate)
if ~isfield(candidate, 'userdata') || ...
        ~isfield(candidate.userdata, 's13') || ...
        ~isstruct(candidate.userdata.s13) || ...
        ~isscalar(candidate.userdata.s13) || ...
        ~isfield(candidate.userdata.s13, 'phase_reports') || ...
        ~isstruct(candidate.userdata.s13.phase_reports) || ...
        ~all(isfield(candidate.userdata.s13.phase_reports, ...
        {'phase1a', 'phase1b'}))
    error('validate_s13_phase1b_artifact_consistency:PhaseReports', ...
        'The cumulative candidate must contain Phase 1A and Phase 1B reports.');
end
phase1a = candidate.userdata.s13.phase_reports.phase1a;
phase1b = candidate.userdata.s13.phase_reports.phase1b;
end

function [actual, imported_names, lexical_types_ok] = ...
        read_csv_with_expected_types(path, expected)
opts = detectImportOptions(path, 'VariableNamingRule', 'preserve');
imported_names = opts.VariableNames;
lexical_types_ok = false;
if ~isequal(imported_names, expected.Properties.VariableNames)
    actual = readtable(path, 'VariableNamingRule', 'preserve', ...
        'TextType', 'string');
    return;
end

raw_opts = opts;
raw_opts = setvartype(raw_opts, raw_opts.VariableNames, 'string');
raw = readtable(path, raw_opts);
lexical_types_ok = lexical_values_match_types(raw, expected);

for k = 1:width(expected)
    name = expected.Properties.VariableNames{k};
    expected_class = class(expected.(name));
    if ~ismember(expected_class, {'double','single','logical','string', ...
            'datetime','duration'})
        error('validate_s13_phase1b_artifact_consistency:UnsupportedType', ...
            'Unsupported expected table type %s for %s.', ...
            expected_class, name);
    end
    opts = setvartype(opts, name, expected_class);
end
actual = readtable(path, opts);
end

function tf = lexical_values_match_types(raw, expected)
tf = height(raw) == height(expected);
if ~tf, return; end
for k = 1:width(expected)
    name = expected.Properties.VariableNames{k};
    text_values = raw.(name);
    expected_values = expected.(name);
    switch class(expected_values)
        case 'string'
            valid = isequaln(text_values, expected_values);
        case {'double','single'}
            parsed = str2double(text_values);
            valid_nan = isnan(expected_values) & isnan(parsed);
            valid_pos_inf = isinf(expected_values) & expected_values > 0 & ...
                isinf(parsed) & parsed > 0;
            valid_neg_inf = isinf(expected_values) & expected_values < 0 & ...
                isinf(parsed) & parsed < 0;
            valid_finite = isfinite(expected_values) & isfinite(parsed);
            valid = all(valid_nan | valid_pos_inf | valid_neg_inf | ...
                valid_finite, 'all');
        case 'logical'
            lower_text = lower(text_values);
            recognized = ismember(lower_text, ["0", "1", "false", "true"]);
            parsed = lower_text == "1" | lower_text == "true";
            valid = all(recognized & parsed == expected_values, 'all');
        otherwise
            valid = false;
    end
    if ~valid
        tf = false;
        return;
    end
end
end

function signature = schema_signature(value)
signature = strjoin(string(value.Properties.VariableNames), "|");
end

function signature = type_signature(value)
parts = strings(1, width(value));
for k = 1:width(value)
    name = value.Properties.VariableNames{k};
    parts(k) = string(name) + ":" + string(class(value.(name)));
end
signature = strjoin(parts, "|");
end

function tf = table_types_match(expected, actual)
tf = width(expected) == width(actual);
if ~tf, return; end
for k = 1:width(expected)
    name = expected.Properties.VariableNames{k};
    if ~strcmp(class(expected.(name)), class(actual.(name)))
        tf = false;
        return;
    end
end
end

function message = first_value_mismatch(expected, actual)
message = "value or row-order mismatch";
for k = 1:width(expected)
    name = expected.Properties.VariableNames{k};
    if ~isequaln(expected.(name), actual.(name))
        message = "value or row-order mismatch in column " + string(name);
        return;
    end
end
end

function value = normalize_newlines(value)
lf = newline;
cr = char(13);
value = strrep(value, [cr lf], lf);
value = strrep(value, cr, lf);
end

function ledger = build_ledger(checks, dependencies)
check_id = ["artifact:" + checks.artifact_file; ...
    "dependency:" + dependencies.check_id];
check_class = [repmat("phase1b_committed_artifact", height(checks), 1); ...
    dependencies.check_class];
pass = [checks.pass; dependencies.pass];
detail = [checks.detail; dependencies.detail];
ledger = table(check_id, check_class, pass, detail);
end

function value = ternary_detail(condition, true_value, false_value)
if condition, value = true_value; else, value = false_value; end
end

function remove_temp_dir(path)
if isfolder(path), rmdir(path, 's'); end
end
