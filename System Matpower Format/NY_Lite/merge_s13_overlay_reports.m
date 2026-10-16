function cumulative = merge_s13_overlay_reports(phase1a, phase1b)
%MERGE_S13_OVERLAY_REPORTS Merge immutable Phase 1A/1B overlay evidence.
%   CUMULATIVE = MERGE_S13_OVERLAY_REPORTS(PHASE1A, PHASE1B) concatenates
%   the seven canonical register tables in phase order. Schemas (including
%   variable classes and widths) must match, and each table's ownership key
%   must be unique within and disjoint across phases. No table is sorted, so
%   Phase 1A row order remains unchanged and Phase 1B rows are appended.

validate_report_header(phase1a, "phase1a");
validate_report_header(phase1b, "phase1b");

table_names = { ...
    'bus_map', 'branch_map', 'residual_register', ...
    'residual_shunt_register', 'path_register', ...
    'physical_register', 'operator_map'};
key_columns = { ...
    {'model_bus'}, ...
    {'model_branch_row'}, ...
    {'model_branch_row'}, ...
    {'model_bus'}, ...
    {'overlay_path_id'}, ...
    {'model_branch_row'}, ...
    {'interface_name', 'component_name', 'model_branch_row', ...
     'source_branch_row', 'source_circuit_id'}};

merged = struct();
for k = 1:numel(table_names)
    name = table_names{k};
    first = require_table(phase1a, name, "phase1a");
    second = require_table(phase1b, name, "phase1b");
    validate_identical_schema(first, second, name);

    keys_first = table_keys(first, key_columns{k}, name, "phase1a");
    keys_second = table_keys(second, key_columns{k}, name, "phase1b");
    assert_unique_keys(keys_first, name, "phase1a");
    assert_unique_keys(keys_second, name, "phase1b");
    overlap = intersect(keys_first, keys_second, 'stable');
    if ~isempty(overlap)
        error('merge_s13_overlay_reports:CrossPhaseKeyOverlap', ...
            ['Register %s has %d key(s) owned by both phases; first ' ...
             'overlap is %s.'], name, numel(overlap), overlap(1));
    end

    merged.(name) = [first; second];
end

phase1a_bus_count = require_nonnegative_integer( ...
    phase1a, 'buses_added', "phase1a");
phase1b_bus_count = require_nonnegative_integer( ...
    phase1b, 'buses_added', "phase1b");
phase1a_branch_count = require_nonnegative_integer( ...
    phase1a, 'branches_added', "phase1a");
phase1b_branch_count = require_nonnegative_integer( ...
    phase1b, 'branches_added', "phase1b");
phase1a_size = require_case_size(phase1a, "phase1a");
phase1b_size = require_case_size(phase1b, "phase1b");

expected_phase1b_size = phase1a_size + ...
    [phase1b_bus_count, phase1b_branch_count, 0];
if ~isequal(phase1b_size, expected_phase1b_size)
    error('merge_s13_overlay_reports:CaseSizeProgression', ...
        ['Phase 1B case_size must equal Phase 1A case_size plus its ' ...
         'reported bus/branch additions, with no generator additions.']);
end

if height(merged.branch_map) ~= ...
        phase1a_branch_count + phase1b_branch_count
    error('merge_s13_overlay_reports:BranchCountMismatch', ...
        'Merged branch_map height does not equal summed branches_added.');
end
if ~all(ismember({'model_branch_row', 'source_branch_row'}, ...
        merged.branch_map.Properties.VariableNames))
    error('merge_s13_overlay_reports:BranchRowSchema', ...
        'branch_map must contain model_branch_row and source_branch_row.');
end
if ~isequal(merged.physical_register.model_branch_row, ...
        merged.branch_map.model_branch_row)
    error('merge_s13_overlay_reports:PhysicalRegisterAlignment', ...
        ['physical_register and branch_map must retain identical ' ...
         'model_branch_row order.']);
end

if isfield(phase1a, 'register_files') && isfield(phase1b, 'register_files') && ...
        ~isequaln(phase1a.register_files, phase1b.register_files)
    error('merge_s13_overlay_reports:RegisterFileMismatch', ...
        'Phase reports declare different canonical register files.');
end

% Carry forward the latest phase's non-table status fields, then replace all
% cumulative fields explicitly so no Phase 1B-only table leaks through.
cumulative = phase1b;
for k = 1:numel(table_names)
    cumulative.(table_names{k}) = merged.(table_names{k});
end
cumulative.phase_id = 'cumulative_through_phase1b';
cumulative.report_role = 'cumulative_overlay_evidence';
cumulative.current_phase = 'phase1b';
cumulative.included_phases = ["phase1a"; "phase1b"];
cumulative.phase_count = 2;
cumulative.buses_added = phase1a_bus_count + phase1b_bus_count;
cumulative.branches_added = phase1a_branch_count + phase1b_branch_count;
cumulative.case_size = phase1b_size;
cumulative.physical_branch_rows = ...
    cumulative.branch_map.model_branch_row(:);
cumulative.source_branch_rows = ...
    cumulative.branch_map.source_branch_row(:);
cumulative.construction_source_qualified = false;
cumulative.promotion_eligible = false;
end

function validate_report_header(report, expected_phase)
if ~isstruct(report) || ~isscalar(report)
    error('merge_s13_overlay_reports:ReportType', ...
        '%s report must be a scalar struct.', expected_phase);
end
if ~isfield(report, 'phase_id')
    error('merge_s13_overlay_reports:MissingPhaseId', ...
        '%s report is missing phase_id.', expected_phase);
end
phase = string(report.phase_id);
if ~isscalar(phase) || ismissing(phase) || phase ~= expected_phase
    error('merge_s13_overlay_reports:PhaseIdMismatch', ...
        'Expected %s report, found phase_id %s.', ...
        expected_phase, display_value(phase));
end
require_false_flag(report, 'construction_source_qualified', expected_phase);
require_false_flag(report, 'promotion_eligible', expected_phase);
end

function value = require_table(report, field, phase)
if ~isfield(report, field) || ~istable(report.(field))
    error('merge_s13_overlay_reports:MissingTable', ...
        '%s report field %s must be a table.', phase, field);
end
value = report.(field);
end

function validate_identical_schema(first, second, table_name)
first_names = first.Properties.VariableNames;
second_names = second.Properties.VariableNames;
if ~isequal(first_names, second_names)
    error('merge_s13_overlay_reports:SchemaMismatch', ...
        'Register %s has different variable names or column order.', ...
        table_name);
end
for k = 1:numel(first_names)
    name = first_names{k};
    if ~strcmp(class(first.(name)), class(second.(name))) || ...
            size(first.(name), 2) ~= size(second.(name), 2)
        error('merge_s13_overlay_reports:SchemaMismatch', ...
            'Register %s variable %s has a different class or width.', ...
            table_name, name);
    end
end
end

function keys = table_keys(value, columns, table_name, phase)
if ~all(ismember(columns, value.Properties.VariableNames))
    error('merge_s13_overlay_reports:MissingKeyColumn', ...
        '%s register %s is missing one or more ownership-key columns.', ...
        phase, table_name);
end
keys = strings(height(value), 1);
for k = 1:numel(columns)
    part = string(value.(columns{k}));
    if size(part, 2) ~= 1
        error('merge_s13_overlay_reports:KeyColumnWidth', ...
            '%s register %s key column %s must be scalar-valued.', ...
            phase, table_name, columns{k});
    end
    missing_part = ismissing(part);
    part(missing_part) = "";
    encoded = "V" + strlength(part) + ":" + part;
    encoded(missing_part) = "M";
    keys = keys + "|" + encoded;
end
end

function assert_unique_keys(keys, table_name, phase)
if numel(unique(keys)) ~= numel(keys)
    error('merge_s13_overlay_reports:DuplicatePhaseKey', ...
        '%s register %s contains a duplicate ownership key.', ...
        phase, table_name);
end
end

function value = require_nonnegative_integer(report, field, phase)
if ~isfield(report, field) || ~isnumeric(report.(field)) || ...
        ~isscalar(report.(field)) || ~isfinite(report.(field)) || ...
        report.(field) < 0 || report.(field) ~= fix(report.(field))
    error('merge_s13_overlay_reports:InvalidCount', ...
        '%s report field %s must be a nonnegative integer scalar.', ...
        phase, field);
end
value = double(report.(field));
end

function value = require_case_size(report, phase)
if ~isfield(report, 'case_size') || ~isnumeric(report.case_size) || ...
        numel(report.case_size) ~= 3 || any(~isfinite(report.case_size)) || ...
        any(report.case_size < 0) || ...
        any(report.case_size ~= fix(report.case_size))
    error('merge_s13_overlay_reports:InvalidCaseSize', ...
        '%s report case_size must contain three nonnegative integers.', phase);
end
value = reshape(double(report.case_size), 1, 3);
end

function require_false_flag(report, field, phase)
if ~isfield(report, field) || ~isscalar(report.(field)) || ...
        ~(islogical(report.(field)) || isnumeric(report.(field))) || ...
        ~isfinite(double(report.(field))) || logical(report.(field))
    error('merge_s13_overlay_reports:UnsafeStatusFlag', ...
        '%s report field %s must be scalar false.', phase, field);
end
end

function value = display_value(value)
if isempty(value)
    value = "<empty>";
elseif ~isscalar(value)
    value = "<nonscalar>";
elseif ismissing(value)
    value = "<missing>";
end
end
