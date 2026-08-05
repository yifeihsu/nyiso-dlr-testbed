function out = test_s13_phase1b_validator_adversarial(options)
%TEST_S13_PHASE1B_VALIDATOR_ADVERSARIAL Challenge cumulative Phase 1B gates.
%   OUT = TEST_S13_PHASE1B_VALIDATOR_ADVERSARIAL() rebuilds the cumulative
%   S13-FULL Phase 1B candidate and applies nine isolated in-memory
%   mutations. Structural mutations are evaluated by
%   VALIDATE_S13_STRUCTURAL_PRESERVATION; UPNY operator mutations are
%   evaluated by VALIDATE_S13_PHASE1B_UPNY_OPERATOR. Source cases,
%   production case files, and canonical registers are never modified.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
if ~isfield(options, 'output_file')
    options.output_file = fullfile(helper_dir, ...
        's13_phase1b_adversarial_results.csv');
end
if ~isfield(options, 'write_outputs'), options.write_outputs = true; end
if ~isfield(options, 'fail_on_unrejected')
    options.fail_on_unrejected = true;
end
if ~isfield(options, 'verbose'), options.verbose = true; end

built = build_s13_phase1b_candidate(struct( ...
    'write_outputs', false, 'verbose', false));
base = built.candidate;
validate_baseline(base);

mutation_id = [ ...
    "phase1a_report_changed_after_phase1b"; ...
    "duplicate_bus_map_key_cross_phase"; ...
    "cumulative_bus_row_without_phase_owner"; ...
    "phase1b_branch_omitted_from_cumulative"; ...
    "phase1b_attachment_mapping_changed"; ...
    "unregistered_parent_branch_r_x_b_changed"; ...
    "upny_wood_millwood_series_member_added"; ...
    "upny_orientation_metadata_mismatch"; ...
    "upny_exact_public_flag_promoted"];
expected_failed_gate = [ ...
    "phase1a_report_rebuild_identity"; ...
    "s13_metadata_coherence"; ...
    "s13_metadata_coherence"; ...
    "s13_metadata_coherence"; ...
    "added_physical_r_x_b_and_ratings"; ...
    "changed_parent_r_x_b_registered"; ...
    "wood_street_millwood_series_rows_absent"; ...
    "official_metered_ends_exact"; ...
    "exact_public_operator_false"];
validator_kind = [ ...
    repmat("structural", 6, 1); repmat("operator", 3, 1)];

n = numel(mutation_id);
actual_failed_gate = strings(n, 1);
exception_identifier = strings(n, 1);
pass = false(n, 1);
for k = 1:n
    candidate = apply_mutation(base, mutation_id(k));
    if validator_kind(k) == "structural"
        [actual_failed_gate(k), exception_identifier(k)] = ...
            observe_structural_failure(candidate, mutation_id(k));
    else
        [actual_failed_gate(k), exception_identifier(k)] = ...
            observe_operator_failure(candidate);
    end
    pass(k) = expected_gate_observed(expected_failed_gate(k), ...
        actual_failed_gate(k), exception_identifier(k));
end

results = table(mutation_id, expected_failed_gate, actual_failed_gate, ...
    exception_identifier, pass);
if options.write_outputs
    ny_lite_writetable_lf(results, options.output_file);
end

all_observed = all(pass);
out = struct( ...
    'results', results, ...
    'all_expected_gates_observed', all_observed, ...
    'missing_gate_mutations', mutation_id(~pass), ...
    'output_file', string(options.output_file));
if options.verbose
    fprintf(['S13 Phase-1B adversarial validation: %d/%d expected ' ...
        'failures observed.\n'], sum(pass), height(results));
    if any(~pass)
        fprintf('Missing or unresolved gates: %s\n', ...
            strjoin(cellstr(mutation_id(~pass)), ', '));
    end
end
if options.fail_on_unrejected && ~all_observed
    error('test_s13_phase1b_validator_adversarial:MutationNotRejected', ...
        'Expected rejection gates were not observed for: %s', ...
        strjoin(cellstr(mutation_id(~pass)), ', '));
end
end

function validate_baseline(base)
structural = validate_s13_structural_preservation(struct( ...
    'candidate_case', base, ...
    'candidate_name', 's13_phase1b_adversarial_baseline', ...
    'write_outputs', false, 'fail_on_structural', false));
failed = string(structural.gates.metric( ...
    structural.gates.mandatory_for_structure & ~structural.gates.pass));
if ~isempty(failed)
    error('test_s13_phase1b_validator_adversarial:StructuralBaseline', ...
        'Unmutated Phase 1B candidate failed structural gates: %s', ...
        strjoin(cellstr(failed), ', '));
end

operator = validate_s13_phase1b_upny_operator(struct( ...
    'candidate_case', base, 'write_outputs', false, ...
    'fail_on_gate', false, 'verbose', false));
mandatory = operator.gate_ledger.mandatory_for_phase1b_proxy;
failed = operator.gate_ledger.gate_id(mandatory & ...
    ~operator.gate_ledger.pass);
if ~isempty(failed)
    error('test_s13_phase1b_validator_adversarial:OperatorBaseline', ...
        'Unmutated Phase 1B candidate failed operator gates: %s', ...
        strjoin(cellstr(failed), ', '));
end
end

function candidate = apply_mutation(base, mutation_id)
define_constants;
candidate = base;
switch mutation_id
    case "phase1a_report_changed_after_phase1b"
        phase = candidate.userdata.s13.phase_reports.phase1a;
        phase.branch_map.source_branch_row(1) = ...
            phase.branch_map.source_branch_row(1) + 1;
        candidate.userdata.s13.phase_reports.phase1a = phase;
        candidate.userdata.s13.phase1a_report = phase;

    case "duplicate_bus_map_key_cross_phase"
        phase1a = candidate.userdata.s13.phase_reports.phase1a;
        phase1b = candidate.userdata.s13.phase_reports.phase1b;
        old_key = phase1b.bus_map.model_bus(1);
        duplicate_key = phase1a.bus_map.model_bus(1);
        phase1b.bus_map.model_bus(1) = duplicate_key;
        candidate = set_phase1b_report(candidate, phase1b);
        cumulative = candidate.userdata.s13.overlay_report.bus_map;
        row = require_one(cumulative.model_bus == old_key, ...
            'duplicate bus-map mutation target');
        cumulative.model_bus(row) = duplicate_key;
        candidate.userdata.s13.overlay_report.bus_map = cumulative;

    case "cumulative_bus_row_without_phase_owner"
        cumulative = candidate.userdata.s13.overlay_report.bus_map;
        extra = cumulative(end, :);
        extra.model_bus(1) = max(cumulative.model_bus) + 100000;
        extra.model_bus_name(1) = "UNOWNED MUTATION";
        cumulative = [cumulative; extra];
        candidate.userdata.s13.overlay_report.bus_map = cumulative;

    case "phase1b_branch_omitted_from_cumulative"
        phase1b = candidate.userdata.s13.phase_reports.phase1b;
        source_row = 1689;
        phase_row = require_one( ...
            phase1b.branch_map.source_branch_row == source_row, ...
            'Phase 1B branch omission source row');
        model_row = phase1b.branch_map.model_branch_row(phase_row);
        branch_map = candidate.userdata.s13.overlay_report.branch_map;
        remove = require_one(branch_map.model_branch_row == model_row, ...
            'cumulative branch-map omission target');
        branch_map(remove, :) = [];
        candidate.userdata.s13.overlay_report.branch_map = branch_map;
        physical = candidate.userdata.s13.overlay_report.physical_register;
        remove = require_one(physical.model_branch_row == model_row, ...
            'cumulative physical-register omission target');
        physical(remove, :) = [];
        candidate.userdata.s13.overlay_report.physical_register = physical;

    case "phase1b_attachment_mapping_changed"
        phase1b = candidate.userdata.s13.phase_reports.phase1b;
        path_id = "phase1b_pv_wood_mesh";
        row = require_one(phase1b.path_register.overlay_path_id == path_id, ...
            'Phase 1B path attachment mutation target');
        phase1b.path_register.npcc_attachment_from_bus(row) = 76;
        candidate = set_phase1b_report(candidate, phase1b);
        cumulative = candidate.userdata.s13.overlay_report.path_register;
        row = require_one(cumulative.overlay_path_id == path_id, ...
            'cumulative path attachment mutation target');
        cumulative.npcc_attachment_from_bus(row) = 76;
        candidate.userdata.s13.overlay_report.path_register = cumulative;

    case "unregistered_parent_branch_r_x_b_changed"
        candidate.branch(1, [BR_R BR_X BR_B]) = ...
            candidate.branch(1, [BR_R BR_X BR_B]) + [0 1e-4 0];

    case "upny_wood_millwood_series_member_added"
        phase1b = candidate.userdata.s13.phase_reports.phase1b;
        detail = phase1b.operator_detail;
        row = require_one(detail.source_branch_row == 1689, ...
            'UPNY support-row substitution target');
        detail.source_branch_row(row) = 1734;
        detail.source_from_bus(row) = 902;
        detail.source_to_bus(row) = 897;
        detail.source_circuit_id(row) = "1";
        detail.physical_circuit_key(row) = "PERFORM_902_897_CKT_1";
        detail.operator_membership(row) = true;
        detail.cutset_from_side(row) = "D";
        detail.cutset_to_side(row) = "D";
        detail.meter_end(row) = "from";
        detail.operator_sign(row) = 1;
        detail.public_circuit_label(row) = "WOOD_MILLWOOD_SERIES";
        phase1b.operator_detail = detail;
        candidate = set_phase1b_report(candidate, phase1b);

    case "upny_orientation_metadata_mismatch"
        phase1b = candidate.userdata.s13.phase_reports.phase1b;
        detail = phase1b.operator_detail;
        row = require_one(detail.source_branch_row == 1389, ...
            'UPNY orientation mutation target');
        detail.meter_end(row) = "to";
        phase1b.operator_detail = detail;
        candidate = set_phase1b_report(candidate, phase1b);

    case "upny_exact_public_flag_promoted"
        phase1b = candidate.userdata.s13.phase_reports.phase1b;
        phase1b.is_exact_public_operator = true;
        phase1b.operator_detail.is_exact_public_operator(:) = true;
        candidate = set_phase1b_report(candidate, phase1b);

    otherwise
        error('test_s13_phase1b_validator_adversarial:UnknownMutation', ...
            'Unknown Phase 1B mutation: %s', mutation_id);
end
end

function candidate = set_phase1b_report(candidate, report)
candidate.userdata.s13.phase_reports.phase1b = report;
if isfield(candidate.userdata.s13, 'phase1b_report')
    candidate.userdata.s13.phase1b_report = report;
end
end

function row = require_one(mask, description)
row = find(mask);
if numel(row) ~= 1
    error('test_s13_phase1b_validator_adversarial:MutationTarget', ...
        'Expected one %s, found %d.', description, numel(row));
end
end

function [actual, exception_id] = observe_structural_failure(candidate, id)
actual = "<none>";
exception_id = "";
try
    validation = validate_s13_structural_preservation(struct( ...
        'candidate_case', candidate, ...
        'candidate_name', "phase1b_adversarial_" + id, ...
        'write_outputs', false, 'fail_on_structural', false));
    failed = string(validation.gates.metric( ...
        validation.gates.mandatory_for_structure & ~validation.gates.pass));
    if ~isempty(failed)
        actual = strjoin(failed, "|");
    end
catch ME
    actual = "exception_before_gate_table";
    exception_id = string(ME.identifier);
    if exception_id == "", exception_id = "unidentified_exception"; end
end
end

function [actual, exception_id] = observe_operator_failure(candidate)
actual = "<none>";
exception_id = "";
try
    validation = validate_s13_phase1b_upny_operator(struct( ...
        'candidate_case', candidate, 'write_outputs', false, ...
        'fail_on_gate', false, 'verbose', false));
    mandatory = validation.gate_ledger.mandatory_for_phase1b_proxy;
    failed = validation.gate_ledger.gate_id(mandatory & ...
        ~validation.gate_ledger.pass);
    if ~isempty(failed)
        actual = strjoin(failed, "|");
    end
catch ME
    actual = "exception_before_gate_table";
    exception_id = string(ME.identifier);
    if exception_id == "", exception_id = "unidentified_exception"; end
end
end

function tf = expected_gate_observed(expected, actual, exception_id)
tf = exception_id == "" && any(split(actual, "|") == expected);
end
