function out = test_s13_structural_validator_adversarial(options)
%TEST_S13_STRUCTURAL_VALIDATOR_ADVERSARIAL Challenge S13 structural gates.
%   OUT = TEST_S13_STRUCTURAL_VALIDATOR_ADVERSARIAL() applies nine isolated
%   mutations to a fresh S13 Phase-1A candidate. The first eight exercise the
%   in-memory structural validator. The ninth truncates a copied CSV register
%   and uses VALIDATE_S13_ARTIFACT_CONSISTENCY when that validator is present.
%   Source cases and repository registers are never modified.

if nargin < 1, options = struct(); end
helper_dir = fileparts(mfilename('fullpath'));
case_dir = fileparts(helper_dir);
addpath(case_dir); addpath(helper_dir);
if ~isfield(options, 'output_file')
    options.output_file = fullfile(helper_dir, ...
        's13_structural_adversarial_results.csv');
end

base = loadcase('npcc_ny_lite_s13_npcc_augmented_2019');
baseline = validate_s13_structural_preservation(struct( ...
    'candidate_case', base, 'candidate_name', 's13_adversarial_baseline', ...
    'write_outputs', false, 'fail_on_structural', false));
baseline_failed = string(baseline.gates.metric( ...
    baseline.gates.mandatory_for_structure & ~baseline.gates.pass));
if ~isempty(baseline_failed)
    error('test_s13_structural_validator_adversarial:BaselineFailed', ...
        'Unmutated S13 baseline failed structural gates: %s', ...
        strjoin(cellstr(baseline_failed), ', '));
end

mutation_id = [ ...
    "original_bus_id_changed"; ...
    "original_branch_endpoint_changed"; ...
    "original_bus_name_changed"; ...
    "generator_cost_changed"; ...
    "added_branch_r_x_b_changed"; ...
    "source_branch_row_changed"; ...
    "s12_source_label_injected"; ...
    "unregistered_parent_r_x_b_changed"; ...
    "csv_physical_register_truncated"];
expected_failed_gate = [ ...
    "original_bus_row_identity"; ...
    "original_branch_row_identity"; ...
    "parent_bus_names_stable"; ...
    "generator_capability_and_identity"; ...
    "added_physical_r_x_b_and_ratings"; ...
    "added_physical_r_x_b_and_ratings"; ...
    "no_s12_kron_admittance"; ...
    "changed_parent_r_x_b_registered"; ...
    "all_artifacts_match"];

n = numel(mutation_id);
actual_failed_gate = strings(n, 1);
exception_identifier = strings(n, 1);
pass = false(n, 1);
for k = 1:n-1
    candidate = apply_structural_mutation(base, mutation_id(k));
    [actual_failed_gate(k), exception_identifier(k)] = ...
        observe_structural_failure(candidate, mutation_id(k));
    pass(k) = expected_gate_observed(expected_failed_gate(k), ...
        actual_failed_gate(k), exception_identifier(k));
end

[actual_failed_gate(n), exception_identifier(n), pass(n)] = ...
    observe_truncated_csv_failure(base, expected_failed_gate(n), helper_dir);

results = table(mutation_id, expected_failed_gate, actual_failed_gate, ...
    exception_identifier, pass);
ny_lite_writetable_lf(results, options.output_file);

out = struct('results', results, 'all_expected_gates_observed', all(pass), ...
    'missing_gate_mutations', mutation_id(~pass), ...
    'output_file', string(options.output_file));
fprintf('S13 adversarial validation: %d/%d expected failures observed.\n', ...
    sum(pass), height(results));
if any(~pass)
    fprintf('Missing or unresolved gates: %s\n', ...
        strjoin(cellstr(mutation_id(~pass)), ', '));
end
end

function candidate = apply_structural_mutation(base, mutation_id)
define_constants;
candidate = base;
switch mutation_id
    case "original_bus_id_changed"
        candidate.bus(1, BUS_I) = max(candidate.bus(:, BUS_I)) + 1000;
    case "original_branch_endpoint_changed"
        endpoints = candidate.branch(1, [F_BUS T_BUS]);
        replacement = candidate.bus(find( ...
            ~ismember(candidate.bus(:, BUS_I), endpoints), 1, 'last'), BUS_I);
        candidate.branch(1, F_BUS) = replacement;
    case "original_bus_name_changed"
        if iscell(candidate.bus_name)
            candidate.bus_name{1} = [char(candidate.bus_name{1}) ' MUTATED'];
        else
            candidate.bus_name(1) = string(candidate.bus_name(1)) + " MUTATED";
        end
    case "generator_cost_changed"
        candidate.gencost(1, end) = candidate.gencost(1, end) + 1;
    case "added_branch_r_x_b_changed"
        row = candidate.userdata.npcc_perform_overlay.physical_branch_rows(1);
        candidate.branch(row, [BR_R BR_X BR_B]) = ...
            candidate.branch(row, [BR_R BR_X BR_B]) + [1e-5 1e-5 1e-5];
    case "source_branch_row_changed"
        map = candidate.userdata.s13.phase1a_report.branch_map;
        map.source_branch_row(1) = map.source_branch_row(1) + 1;
        candidate.userdata.s13.phase1a_report.branch_map = map;
    case "s12_source_label_injected"
        map = candidate.userdata.s13.phase1a_report.branch_map;
        map.source_model(1) = "npcc_ny_lite_s12_perform_retention_core";
        candidate.userdata.s13.phase1a_report.branch_map = map;
    case "unregistered_parent_r_x_b_changed"
        candidate.branch(1, BR_X) = candidate.branch(1, BR_X) + 1e-4;
    otherwise
        error('test_s13_structural_validator_adversarial:UnknownMutation', ...
            'Unknown structural mutation: %s', mutation_id);
end
end

function [actual, exception_id] = observe_structural_failure(candidate, mutation_id)
actual = "<none>";
exception_id = "";
try
    validation = validate_s13_structural_preservation(struct( ...
        'candidate_case', candidate, ...
        'candidate_name', "adversarial_" + mutation_id, ...
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

function tf = expected_gate_observed(expected, actual, exception_id)
tf = exception_id == "" && any(split(actual, "|") == expected);
end

function [actual, exception_id, passed] = ...
        observe_truncated_csv_failure(base, expected, helper_dir)
% This hook is intentionally isolated so the artifact validator can evolve
% independently from the structural validator. When the validator is absent,
% the durable result stays fail-closed and identifies the missing coverage.
actual = "artifact_validator_unavailable";
exception_id = "";
passed = false;
if exist('validate_s13_artifact_consistency', 'file') ~= 2
    return;
end

try
    [actual, exception_id] = run_artifact_truncation_hook(base, helper_dir);
    passed = expected_gate_observed(expected, actual, exception_id);
catch ME
    actual = "exception_before_artifact_gate_table";
    exception_id = string(ME.identifier);
    if exception_id == "", exception_id = "unidentified_exception"; end
end
end

function [actual, exception_id] = run_artifact_truncation_hook(base, helper_dir)
artifact_files = [ ...
    "npcc_perform_overlay_bus_map.csv"; ...
    "npcc_perform_overlay_branch_map.csv"; ...
    "npcc_residual_equivalent_register.csv"; ...
    "npcc_residual_shunt_register.csv"; ...
    "npcc_overlay_path_register.csv"; ...
    "npcc_added_physical_circuit_register.csv"; ...
    "npcc_2019_interface_operator_map.csv"];
temp_dir = tempname;
mkdir(temp_dir);
cleanup_guard = onCleanup(@() rmdir(temp_dir, 's'));
for k = 1:numel(artifact_files)
    source_path = fullfile(helper_dir, artifact_files(k));
    destination_path = fullfile(temp_dir, artifact_files(k));
    if ~isfile(source_path)
        error('test_s13_structural_validator_adversarial:MissingArtifact', ...
            'Required artifact is missing: %s', source_path);
    end
    copyfile(source_path, destination_path);
end

baseline = validate_s13_artifact_consistency(struct( ...
    'candidate_case', base, 'artifact_dir', temp_dir, ...
    'fail_on_mismatch', false));
if ~baseline.all_artifacts_match
    failed = baseline.checks.artifact_file(~baseline.checks.pass);
    error('test_s13_structural_validator_adversarial:ArtifactBaselineFailed', ...
        'Unmodified artifact copies failed consistency: %s', ...
        strjoin(cellstr(failed), ', '));
end

target_file = "npcc_added_physical_circuit_register.csv";
truncated = base.userdata.s13.phase1a_report.physical_register;
if height(truncated) < 1
    error('test_s13_structural_validator_adversarial:EmptyPhysicalRegister', ...
        'The physical-circuit register cannot be truncated because it is empty.');
end
truncated(end, :) = [];
ny_lite_writetable_lf(truncated, fullfile(temp_dir, target_file));

validation = validate_s13_artifact_consistency(struct( ...
    'candidate_case', base, 'artifact_dir', temp_dir, ...
    'fail_on_mismatch', false));
target_failed = validation.checks.artifact_file == target_file & ...
    ~validation.checks.pass;
if ~validation.all_artifacts_match && any(target_failed)
    actual = "all_artifacts_match";
else
    actual = "<none>";
end
exception_id = "";
clear cleanup_guard;
end
