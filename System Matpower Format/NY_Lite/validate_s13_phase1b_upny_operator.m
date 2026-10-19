function out = validate_s13_phase1b_upny_operator(options)
%VALIDATE_S13_PHASE1B_UPNY_OPERATOR Validate the local UPNY-ConEd proxy.
%   The Phase 1B overlay intentionally implements only the six source-backed
%   345-kV public-interface circuits.  The declared nine-edge local graph
%   also contains two downstream E. Fishkill-Wood Street circuits and the
%   upstream Ramapo-Ladentown circuit as explicit nonmembers.  This function
%   proves that the six selected edges form the complete U-D boundary of that
%   declared graph and that stored branch orientation cannot change the
%   calculated operator.
%
%   This validator does not claim an exact public UPNY-ConEd operator.
%   RFK305 is absent from the PERFORM source and the public BK1/BK2 banks are
%   not represented as two independently identifiable source branches.  The
%   corresponding public-completeness gates therefore remain failed and
%   non-promotional by construction.

if nargin < 1, options = struct(); end

helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
root = fileparts(case_dir);
perform_dir = fullfile(root, 'PERFORM', ...
    'On Peak 2019 v23_Perform_NY', 'On Peak 2019 v23');
options = apply_defaults(options, helper_dir);
addpath(case_dir); addpath(helper_dir); addpath(perform_dir);
define_constants;

candidate = load_candidate(options.candidate_case);
[s13, phase1b, detail] = phase1b_detail(candidate);

model_rows = numeric_column(detail, {'model_branch_row'});
source_rows = numeric_column(detail, {'source_branch_row'});
source_circuit = string_column(detail, ...
    {'source_circuit_id', 'raw_circuit_id'});
physical_key = string_column(detail, ...
    {'physical_circuit_key', 'source_physical_circuit_key', 'circuit_key'});
membership = logical_column(detail, ...
    {'operator_membership', 'is_operator_member'});
from_side = normalize_side(string_column(detail, ...
    {'cutset_from_side', 'from_side'}));
to_side = normalize_side(string_column(detail, ...
    {'cutset_to_side', 'to_side'}));
metered_end = lower(strtrim(string_column(detail, ...
    {'metered_end', 'source_metered_end', 'meter_end'})));
operator_sign = numeric_column(detail, {'operator_sign', 'sign'});

expected_rows = [1389; 1390; 1391; 1392; 1576; 1738; 1689; 1690; 1577];
member_rows = [1389; 1390; 1391; 1392; 1576; 1738];
support_rows = [1689; 1690; 1577];
expected_from_bus = [651; 651; 651; 651; 774; 1519; 858; 858; 1519];
expected_to_bus = [858; 858; 902; 902; 900; 900; 902; 902; 774];
expected_circuit = ["1"; "2"; "1"; "2"; "1"; "1"; "1"; "2"; "1"];
expected_from_side = ["U"; "U"; "U"; "U"; "U"; "U"; "D"; "D"; "U"];
expected_to_side = ["D"; "D"; "D"; "D"; "D"; "D"; "D"; "D"; "U"];

[expected_found, detail_index] = ismember(expected_rows, source_rows);
row_count_ok = height(detail) == 9;
source_set_ok = row_count_ok && all(expected_found) && ...
    numel(unique(source_rows)) == numel(expected_rows);
if source_set_ok
    ordered_member = membership(detail_index);
    ordered_from_side = from_side(detail_index);
    ordered_to_side = to_side(detail_index);
    ordered_circuit = source_circuit(detail_index);
    ordered_metered_end = metered_end(detail_index);
    ordered_sign = operator_sign(detail_index);
else
    ordered_member = false(size(expected_rows));
    ordered_from_side = repmat("", size(expected_rows));
    ordered_to_side = repmat("", size(expected_rows));
    ordered_circuit = repmat("", size(expected_rows));
    ordered_metered_end = repmat("", size(expected_rows));
    ordered_sign = nan(size(expected_rows));
end

selected_set_ok = isequal(sort(source_rows(membership)), sort(member_rows)) && ...
    source_set_ok && isequal(ordered_member, ismember(expected_rows, member_rows));
support_set_ok = isequal(sort(source_rows(~membership)), sort(support_rows));
source_unique = numel(unique(source_rows)) == height(detail);
model_unique = numel(unique(model_rows)) == height(detail);
model_range = all(isfinite(model_rows) & model_rows == fix(model_rows) & ...
    model_rows >= 1 & model_rows <= size(candidate.branch, 1));
physical_key_ok = all(~ismissing(physical_key) & strlength(strtrim(physical_key)) > 0) && ...
    numel(unique(physical_key)) == height(detail);
circuit_identity_ok = source_set_ok && isequal(ordered_circuit, expected_circuit);

source_case = loadcase(options.source_case);
source_results = runpf(source_case, mpoption( ...
    'verbose', 0, 'out.all', 0, 'pf.enforce_q_lims', 1));
source_pf_ok = logical(source_results.success);
source_range = all(expected_rows >= 1 & ...
    expected_rows <= size(source_results.branch, 1));
source_endpoint_ok = false;
if source_range
    source_endpoint_ok = isequal( ...
        source_results.branch(expected_rows, [F_BUS T_BUS]), ...
        [expected_from_bus expected_to_bus]);
end

side_identity_ok = source_set_ok && ...
    isequal(ordered_from_side, expected_from_side) && ...
    isequal(ordered_to_side, expected_to_side);
crosses = from_side ~= to_side & ismember(from_side, ["U", "D"]) & ...
    ismember(to_side, ["U", "D"]);
selected_cross_once = all(crosses(membership));
same_side_excluded = all(~membership(~crosses));
boundary_membership_exact = all(membership == crosses);
prohibited_absent = ~any(ismember(source_rows, [1734; 1735]));
no_duplicate_series_path = selected_set_ok && support_set_ok && ...
    source_unique && physical_key_ok && prohibited_absent;

official_meter_ok = source_set_ok && ...
    all(ordered_metered_end(ismember(expected_rows, member_rows)) == "from");
official_sign_ok = source_set_ok && ...
    all(ordered_sign(ismember(expected_rows, member_rows)) == 1);
[orientation, orientation_ok] = orientation_invariance( ...
    source_results, source_rows, source_circuit, membership, ...
    metered_end, operator_sign, source_pf_ok);

[exact_flag_declared, exact_public_false] = exact_public_flag(phase1b, detail);
[status_declared, proxy_status_ok, status_text] = proxy_status(phase1b, detail);
phase_flags_false = safe_false(phase1b, 'promotion_eligible') && ...
    safe_false(phase1b, 'construction_source_qualified');
candidate_flags_false = safe_false(s13, 'promotion_eligible') && ...
    safe_false(s13, 'dlr_delivery_eligible');

rows = { ...
    "phase1b_operator_detail_row_count", "phase1b_proxy", height(detail), 9, "==", true, row_count_ok, "pass_or_fail", "Exactly nine declared local-graph edges"; ...
    "source_row_set_exact", "phase1b_proxy", double(source_set_ok), 1, "==", true, source_set_ok, "pass_or_fail", "Expected six members and three support exclusions only"; ...
    "six_operator_members_exact", "phase1b_proxy", nnz(membership), 6, "==", true, selected_set_ok && nnz(membership) == 6, "pass_or_fail", "1389/1390/1391/1392/1576/1738"; ...
    "three_support_exclusions_exact", "phase1b_proxy", nnz(~membership), 3, "==", true, support_set_ok && nnz(~membership) == 3, "pass_or_fail", "1689/1690 downstream; 1577 upstream"; ...
    "source_rows_unique", "phase1b_proxy", numel(unique(source_rows)), height(detail), "==", true, source_unique, "pass_or_fail", "No source edge can be counted twice"; ...
    "model_rows_unique", "phase1b_proxy", numel(unique(model_rows)), height(detail), "==", true, model_unique, "pass_or_fail", "No model edge can be counted twice"; ...
    "model_rows_in_range", "phase1b_proxy", double(model_range), 1, "==", true, model_range, "pass_or_fail", "Every declared model row exists"; ...
    "physical_circuit_keys_unique", "phase1b_proxy", numel(unique(physical_key)), height(detail), "==", true, physical_key_ok, "pass_or_fail", "Nonempty unique physical circuit keys"; ...
    "raw_circuit_identity_exact", "phase1b_proxy", double(circuit_identity_ok), 1, "==", true, circuit_identity_ok, "pass_or_fail", "Expected RAW CKT 1/2 identities"; ...
    "source_endpoint_identity_exact", "phase1b_proxy", double(source_endpoint_ok), 1, "==", true, source_endpoint_ok, "pass_or_fail", "Full PERFORM oriented endpoints"; ...
    "cutset_endpoint_sides_exact", "phase1b_proxy", double(side_identity_ok), 1, "==", true, side_identity_ok, "pass_or_fail", "Declared U/D partition matches the source rows"; ...
    "selected_edges_cross_once", "phase1b_proxy", nnz(crosses(membership)), nnz(membership), "==", true, selected_cross_once, "pass_or_fail", "Every member has exactly one U and one D endpoint"; ...
    "same_side_edges_excluded", "phase1b_proxy", nnz(membership(~crosses)), 0, "==", true, same_side_excluded, "pass_or_fail", "No U-U or D-D edge is selected"; ...
    "local_boundary_membership_exact", "phase1b_proxy", nnz(membership ~= crosses), 0, "==", true, boundary_membership_exact, "pass_or_fail", "Membership equals the edge boundary of the declared graph"; ...
    "wood_street_millwood_series_rows_absent", "phase1b_proxy", nnz(ismember(source_rows, [1734; 1735])), 0, "==", true, prohibited_absent, "pass_or_fail", "Rows 1734/1735 are downstream continuations, not cut terms"; ...
    "no_duplicate_series_path", "phase1b_proxy", double(no_duplicate_series_path), 1, "==", true, no_duplicate_series_path, "pass_or_fail", "Exact member/support sets exclude consecutive downstream segments"; ...
    "official_metered_ends_exact", "phase1b_proxy", double(official_meter_ok), 1, "==", true, official_meter_ok, "pass_or_fail", "All six source-backed 345-kV terms meter the source from end"; ...
    "operator_signs_exact", "phase1b_proxy", double(official_sign_ok), 1, "==", true, official_sign_ok, "pass_or_fail", "Positive U-to-D contribution uses +PF for all six terms"; ...
    "perform_q_limit_source_converged", "phase1b_proxy", double(source_pf_ok), 1, "==", true, source_pf_ok, "pass_or_fail", "Orientation test uses a solved full-PERFORM source"; ...
    "orientation_invariant_operator", "phase1b_proxy", max_error(orientation), 1e-12, "<=", true, orientation_ok, "pass_or_fail", "Swap endpoints and PF/PT while preserving the physical meter bus"; ...
    "proxy_status_declared", "phase1b_proxy", double(status_declared && proxy_status_ok), 1, "==", true, status_declared && proxy_status_ok, "pass_or_fail", "Status must explicitly identify a proxy: " + status_text; ...
    "exact_public_operator_false", "phase1b_proxy", double(exact_public_false), 1, "==", true, exact_flag_declared && exact_public_false, "pass_or_fail", "Exact-public claim is forbidden for this source-realizable proxy"; ...
    "phase1b_status_flags_false", "phase1b_proxy", double(phase_flags_false), 1, "==", true, phase_flags_false, "pass_or_fail", "Phase report remains unqualified and unpromoted"; ...
    "candidate_delivery_flags_false", "phase1b_proxy", double(candidate_flags_false), 1, "==", true, candidate_flags_false, "pass_or_fail", "S13-FULL remains ineligible for DLR delivery"; ...
    "public_gap_rfk305_resolved", "public_exactness", 0, 1, "==", false, false, "blocked", "RFK305 is absent from the full PERFORM source"; ...
    "public_gap_bk1_resolved", "public_exactness", 0, 1, "==", false, false, "blocked", "BK1 is not independently identifiable in the source"; ...
    "public_gap_bk2_resolved", "public_exactness", 0, 1, "==", false, false, "blocked", "BK2 is not independently identifiable in the source"};

gates = cell2table(rows, 'VariableNames', { ...
    'gate_id', 'gate_class', 'metric_value', 'limit', 'comparator', ...
    'mandatory_for_phase1b_proxy', 'pass', 'status', 'notes'});
gates.gate_id = string(gates.gate_id);
gates.gate_class = string(gates.gate_class);
gates.comparator = string(gates.comparator);
gates.status = string(gates.status);
gates.notes = string(gates.notes);

mandatory = gates.mandatory_for_phase1b_proxy;
mandatory_proxy_pass = all(gates.pass(mandatory));
output_file = fullfile(options.output_dir, ...
    's13_phase1b_operator_validation.csv');
if options.write_outputs
    if ~isfolder(options.output_dir)
        error('validate_s13_phase1b_upny_operator:OutputDirectory', ...
            'Output directory does not exist: %s', options.output_dir);
    end
    ny_lite_writetable_lf(gates, output_file);
end

out = struct( ...
    'pass', mandatory_proxy_pass, ...
    'mandatory_proxy_pass', mandatory_proxy_pass, ...
    'mandatory_proxy_gate_count', nnz(mandatory), ...
    'mandatory_proxy_pass_count', nnz(gates.pass & mandatory), ...
    'public_gap_gate_count', nnz(gates.gate_class == "public_exactness"), ...
    'public_gap_pass_count', nnz(gates.pass & ...
        gates.gate_class == "public_exactness"), ...
    'exact_public_operator', false, ...
    'promotion_eligible', false, ...
    'operator_status', status_text, ...
    'operator_detail', detail, ...
    'orientation_check', orientation, ...
    'gate_ledger', gates, ...
    'file', string(output_file));

if options.verbose
    fprintf(['S13 Phase-1B UPNY proxy: %d/%d mandatory gates pass; ' ...
        'three public gaps remain failed closed; exact public=false.\n'], ...
        out.mandatory_proxy_pass_count, out.mandatory_proxy_gate_count);
end
if options.fail_on_gate && ~mandatory_proxy_pass
    failed = gates.gate_id(mandatory & ~gates.pass);
    error('validate_s13_phase1b_upny_operator:GateFailure', ...
        'Mandatory Phase-1B operator gates failed: %s', ...
        strjoin(cellstr(failed), ', '));
end
end

function options = apply_defaults(options, helper_dir)
if ~isfield(options, 'candidate_case')
    options.candidate_case = 'npcc_ny_lite_s13_npcc_augmented_2019';
end
if ~isfield(options, 'source_case')
    options.source_case = 'nyiso_On_Peak_v23_shunts_as_z_load';
end
if ~isfield(options, 'write_outputs'), options.write_outputs = true; end
if ~isfield(options, 'fail_on_gate'), options.fail_on_gate = true; end
if ~isfield(options, 'verbose'), options.verbose = true; end
if ~isfield(options, 'output_dir'), options.output_dir = helper_dir; end
end

function candidate = load_candidate(value)
if isstruct(value)
    candidate = value;
else
    candidate = loadcase(value);
end
end

function [s13, phase1b, detail] = phase1b_detail(candidate)
if ~isfield(candidate, 'userdata') || ...
        ~isfield(candidate.userdata, 's13') || ...
        ~isstruct(candidate.userdata.s13)
    error('validate_s13_phase1b_upny_operator:MissingS13Metadata', ...
        'The candidate does not contain scalar S13 metadata.');
end
s13 = candidate.userdata.s13;
if ~isfield(s13, 'phase_reports') || ~isstruct(s13.phase_reports) || ...
        ~isfield(s13.phase_reports, 'phase1b') || ...
        ~isstruct(s13.phase_reports.phase1b)
    error('validate_s13_phase1b_upny_operator:MissingPhase1BReport', ...
        'candidate.userdata.s13.phase_reports.phase1b is required.');
end
phase1b = s13.phase_reports.phase1b;
if ~isfield(phase1b, 'operator_detail') || ...
        ~istable(phase1b.operator_detail)
    error('validate_s13_phase1b_upny_operator:MissingOperatorDetail', ...
        'The Phase 1B report must contain an operator_detail table.');
end
detail = phase1b.operator_detail;
end

function value = numeric_column(tbl, alternatives)
name = find_column(tbl, alternatives);
value = double(tbl.(name));
if size(value, 2) ~= 1 || any(~isfinite(value))
    error('validate_s13_phase1b_upny_operator:NumericColumn', ...
        'Operator-detail column %s must contain finite numeric scalars.', name);
end
end

function value = string_column(tbl, alternatives)
name = find_column(tbl, alternatives);
value = string(tbl.(name));
if size(value, 2) ~= 1 || any(ismissing(value))
    error('validate_s13_phase1b_upny_operator:StringColumn', ...
        'Operator-detail column %s must contain nonmissing strings.', name);
end
value = strtrim(value);
end

function value = logical_column(tbl, alternatives)
name = find_column(tbl, alternatives);
raw = tbl.(name);
if ~(islogical(raw) || isnumeric(raw)) || size(raw, 2) ~= 1 || ...
        any(~isfinite(double(raw))) || any(~ismember(double(raw), [0 1]))
    error('validate_s13_phase1b_upny_operator:LogicalColumn', ...
        'Operator-detail column %s must contain scalar logical values.', name);
end
value = logical(raw);
end

function name = find_column(tbl, alternatives)
names = string(tbl.Properties.VariableNames);
match = find(ismember(names, string(alternatives)), 1);
if isempty(match)
    error('validate_s13_phase1b_upny_operator:MissingColumn', ...
        'operator_detail is missing required column %s.', ...
        strjoin(alternatives, ' or '));
end
name = char(names(match));
end

function side = normalize_side(side)
side = upper(strtrim(side));
side(ismember(side, ["UPSTREAM", "SOURCE", "NORTH"])) = "U";
side(ismember(side, ["DOWNSTREAM", "SINK", "SOUTH"])) = "D";
end

function [checks, pass] = orientation_invariance(results, source_rows, ...
        source_circuit, membership, metered_end, operator_sign, source_ok)
define_constants;
idx = find(membership);
n = numel(idx);
row = source_rows(idx);
circuit = source_circuit(idx);
source_meter_bus = nan(n, 1);
original_end = metered_end(idx);
mutated_end = strings(n, 1);
sign_value = operator_sign(idx);
original_value = nan(n, 1);
mutated_value = nan(n, 1);
error_mw = inf(n, 1);
row_pass = false(n, 1);

if source_ok && all(row >= 1 & row <= size(results.branch, 1))
    for k = 1:n
        r = row(k);
        fbus = results.branch(r, F_BUS);
        tbus = results.branch(r, T_BUS);
        pf = results.branch(r, PF);
        pt = results.branch(r, PT);
        if original_end(k) == "from"
            source_meter_bus(k) = fbus;
            meter_p = pf;
        elseif original_end(k) == "to"
            source_meter_bus(k) = tbus;
            meter_p = pt;
        else
            continue;
        end
        original_value(k) = sign_value(k) * meter_p;

        % In-memory orientation mutation: the physical terminal values move
        % with their buses.  The original meter bus therefore changes ends.
        mutated_fbus = tbus;
        mutated_tbus = fbus;
        mutated_pf = pt;
        mutated_pt = pf;
        if source_meter_bus(k) == mutated_fbus
            mutated_end(k) = "from";
            mutated_meter_p = mutated_pf;
        elseif source_meter_bus(k) == mutated_tbus
            mutated_end(k) = "to";
            mutated_meter_p = mutated_pt;
        else
            continue;
        end
        mutated_value(k) = sign_value(k) * mutated_meter_p;
        error_mw(k) = abs(original_value(k) - mutated_value(k));
        row_pass(k) = error_mw(k) <= 1e-12;
    end
end

checks = table(row, circuit, source_meter_bus, original_end, mutated_end, ...
    sign_value, original_value, mutated_value, error_mw, row_pass, ...
    'VariableNames', {'source_branch_row', 'source_circuit_id', ...
    'source_meter_bus', 'original_metered_end', 'mutated_metered_end', ...
    'operator_sign', 'original_contribution_mw', ...
    'mutated_contribution_mw', 'absolute_error_mw', 'pass'});
pass = n == 6 && all(row_pass);
end

function value = max_error(checks)
if isempty(checks) || any(~isfinite(checks.absolute_error_mw))
    value = Inf;
else
    value = max(checks.absolute_error_mw);
end
end

function [declared, is_false] = exact_public_flag(phase1b, detail)
declared = false;
values = false(0, 1);
if isfield(phase1b, 'is_exact_public_operator')
    declared = true;
    values(end + 1, 1) = strict_logical_scalar( ...
        phase1b.is_exact_public_operator, 'is_exact_public_operator');
end
if ismember('is_exact_public_operator', detail.Properties.VariableNames)
    declared = true;
    raw = detail.is_exact_public_operator;
    if ~(islogical(raw) || isnumeric(raw)) || any(~isfinite(double(raw))) || ...
            any(~ismember(double(raw), [0 1]))
        error('validate_s13_phase1b_upny_operator:ExactPublicFlag', ...
            'operator_detail.is_exact_public_operator must be logical.');
    end
    values = [values; logical(raw(:))];
end
is_false = declared && ~any(values);
end

function [declared, pass, text_value] = proxy_status(phase1b, detail)
declared = false;
values = strings(0, 1);
fields = {'operator_status', 'public_operator_status', 'operator_scope'};
for k = 1:numel(fields)
    if isfield(phase1b, fields{k})
        declared = true;
        values(end + 1, 1) = string(phase1b.(fields{k})); %#ok<AGROW>
    end
end
for k = 1:numel(fields)
    if ismember(fields{k}, detail.Properties.VariableNames)
        declared = true;
        values = [values; string(detail.(fields{k})(:))]; %#ok<AGROW>
    end
end
values = lower(strtrim(values));
pass = declared && ~isempty(values) && all(~ismissing(values)) && ...
    all(contains(values, "proxy")) && ...
    ~any(contains(values, "exact_public"));
if isempty(values)
    text_value = "<missing>";
else
    text_value = strjoin(unique(values, 'stable'), ';');
end
end

function tf = safe_false(value, field)
tf = isfield(value, field) && isscalar(value.(field)) && ...
    (islogical(value.(field)) || isnumeric(value.(field))) && ...
    isfinite(double(value.(field))) && ~logical(value.(field));
end

function value = strict_logical_scalar(value, name)
if ~isscalar(value) || ~(islogical(value) || isnumeric(value)) || ...
        ~isfinite(double(value)) || ~ismember(double(value), [0 1])
    error('validate_s13_phase1b_upny_operator:LogicalFlag', ...
        'Phase 1B field %s must be a scalar logical value.', name);
end
value = logical(value);
end
