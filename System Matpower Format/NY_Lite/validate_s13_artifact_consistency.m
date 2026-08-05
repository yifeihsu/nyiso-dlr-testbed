function out = validate_s13_artifact_consistency(options)
%VALIDATE_S13_ARTIFACT_CONSISTENCY Verify committed S13-FULL evidence.
%   Rebuilds/loads the S13-FULL construction parent and compares all seven
%   canonical register CSVs plus the structural-gate ledger against freshly
%   rebuilt in-memory tables. Schema, column order, variable types, row order,
%   and values must all match. The default behavior is fail-closed.

if nargin < 1, options = struct(); end
if ~isfield(options, 'candidate_case')
    options.candidate_case = 'npcc_ny_lite_s13_npcc_augmented_2019';
end
if ~isfield(options, 'artifact_dir')
    options.artifact_dir = fileparts(mfilename('fullpath'));
end
if ~isfield(options, 'fail_on_mismatch'), options.fail_on_mismatch = true; end

helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);

if isstruct(options.candidate_case)
    candidate = options.candidate_case;
    candidate_name = "provided_s13_candidate";
else
    candidate = loadcase(options.candidate_case);
    candidate_name = string(options.candidate_case);
end

report = struct();
report_present = isfield(candidate, 'userdata') && ...
    isfield(candidate.userdata, 's13') && ...
    isfield(candidate.userdata.s13, 'overlay_report') && ...
    isstruct(candidate.userdata.s13.overlay_report);
if report_present
    report = candidate.userdata.s13.overlay_report;
end
structural = validate_s13_structural_preservation(struct( ...
    'candidate_case', candidate, 'candidate_name', ...
    'npcc_ny_lite_s13_npcc_augmented_2019', ...
    'write_outputs', false, 'fail_on_structural', false));
report.structural_gate_ledger = structural.gates;

spec = table([ ...
    "npcc_perform_overlay_bus_map.csv"; ...
    "npcc_perform_overlay_branch_map.csv"; ...
    "npcc_residual_equivalent_register.csv"; ...
    "npcc_residual_shunt_register.csv"; ...
    "npcc_overlay_path_register.csv"; ...
    "npcc_added_physical_circuit_register.csv"; ...
    "npcc_2019_interface_operator_map.csv"; ...
    "s13_structural_preservation.csv"], ...
    ["bus_map"; "branch_map"; "residual_register"; ...
    "residual_shunt_register"; "path_register"; ...
    "physical_register"; "operator_map"; "structural_gate_ledger"], ...
    'VariableNames', {'artifact_file','report_field'});

n = height(spec);
file_present = false(n, 1);
report_table_present = false(n, 1);
read_success = false(n, 1);
expected_rows = nan(n, 1);
actual_rows = nan(n, 1);
schema_order_match = false(n, 1);
type_match = false(n, 1);
value_match = false(n, 1);
pass = false(n, 1);
expected_schema = strings(n, 1);
actual_schema = strings(n, 1);
expected_types = strings(n, 1);
actual_types = strings(n, 1);
detail = strings(n, 1);

for k = 1:n
    field = char(spec.report_field(k));
    artifact_path = fullfile(options.artifact_dir, spec.artifact_file(k));
    file_present(k) = isfile(artifact_path);
    report_table_present(k) = report_present && isfield(report, field) && ...
        istable(report.(field));

    if ~report_table_present(k)
        detail(k) = "missing or non-table candidate report field " + ...
            spec.report_field(k);
        continue;
    end

    expected = report.(field);
    expected_rows(k) = height(expected);
    expected_schema(k) = schema_signature(expected);
    expected_types(k) = type_signature(expected);

    if ~file_present(k)
        detail(k) = "committed CSV is missing";
        continue;
    end

    try
        [actual, imported_names, lexical_types_ok] = read_csv_with_expected_types( ...
            artifact_path, expected);
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
        expected.Properties.VariableNames);
    if ~schema_order_match(k)
        detail(k) = "schema/order mismatch";
        continue;
    end

    type_match(k) = lexical_types_ok && table_types_match(expected, actual);
    if ~type_match(k)
        detail(k) = "variable type mismatch";
        continue;
    end

    if actual_rows(k) ~= expected_rows(k)
        detail(k) = sprintf('row-count mismatch: expected %d, found %d', ...
            expected_rows(k), actual_rows(k));
        continue;
    end

    value_match(k) = table_values_match(expected, actual);
    if ~value_match(k)
        detail(k) = first_value_mismatch(expected, actual);
        continue;
    end

    pass(k) = true;
    detail(k) = "exact schema/type/order/value match";
end

checks = table(spec.artifact_file, spec.report_field, file_present, ...
    report_table_present, read_success, expected_rows, actual_rows, ...
    expected_schema, actual_schema, expected_types, actual_types, ...
    schema_order_match, type_match, value_match, pass, detail, ...
    'VariableNames', {'artifact_file','report_field','file_present', ...
    'report_table_present','read_success','expected_rows','actual_rows', ...
    'expected_schema','actual_schema','expected_types','actual_types', ...
    'schema_order_match','type_match','value_match','pass','detail'});

register_mask = spec.report_field ~= "structural_gate_ledger";
ledger_mask = ~register_mask;
all_artifacts_match = height(checks) == 8 && all(checks.pass);
out = struct('candidate_name', candidate_name, ...
    'artifact_dir', string(options.artifact_dir), 'checks', checks, ...
    'artifact_count', height(checks), ...
    'matched_artifact_count', nnz(checks.pass), ...
    'register_artifact_count', nnz(register_mask), ...
    'matched_register_artifact_count', nnz(checks.pass & register_mask), ...
    'structural_ledger_count', nnz(ledger_mask), ...
    'matched_structural_ledger_count', nnz(checks.pass & ledger_mask), ...
    'all_artifacts_match', all_artifacts_match);

if options.fail_on_mismatch && ~all_artifacts_match
    failed = checks.artifact_file(~checks.pass);
    error('validate_s13_artifact_consistency:ArtifactMismatch', ...
        'S13 committed artifact consistency failed: %s', ...
        strjoin(cellstr(failed), ', '));
end
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
        error('validate_s13_artifact_consistency:UnsupportedType', ...
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
            valid_nan = isnan(expected_values) & strcmpi(text_values, "NaN");
            valid_pos_inf = isinf(expected_values) & expected_values > 0 & ...
                strcmpi(text_values, "Inf");
            valid_neg_inf = isinf(expected_values) & expected_values < 0 & ...
                strcmpi(text_values, "-Inf");
            valid_finite = isfinite(expected_values) & isfinite(parsed) & ...
                parsed == double(expected_values);
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

function tf = table_values_match(expected, actual)
tf = height(expected) == height(actual) && width(expected) == width(actual);
if ~tf, return; end
for k = 1:width(expected)
    name = expected.Properties.VariableNames{k};
    if ~isequaln(expected.(name), actual.(name))
        tf = false;
        return;
    end
end
end

function message = first_value_mismatch(expected, actual)
message = "value mismatch";
for k = 1:width(expected)
    name = expected.Properties.VariableNames{k};
    if ~isequaln(expected.(name), actual.(name))
        message = "value mismatch in column " + string(name);
        return;
    end
end
end
