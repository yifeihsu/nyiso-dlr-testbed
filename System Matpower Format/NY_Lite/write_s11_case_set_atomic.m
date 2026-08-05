function report = write_s11_case_set_atomic(final_paths, cases, solved_flags)
%WRITE_S11_CASE_SET_ATOMIC Stage, verify, and publish S11 MATPOWER cases.
%   REPORT = WRITE_S11_CASE_SET_ATOMIC(PATHS, CASES, SOLVED) writes every
%   case into a temporary sibling directory, reloads it, verifies numerical
%   round-trip fidelity and Q-limit PF convergence, and only then moves the
%   complete staged set to the requested final filenames.

if nargin < 3
    error('write_s11_case_set_atomic:MissingInput', ...
        'final_paths, cases, and solved_flags are required.');
end
final_paths = string(final_paths(:));
solved_flags = logical(solved_flags(:));
if ~iscell(cases), cases = {cases}; end
cases = cases(:);
n = numel(final_paths);
if n == 0 || numel(cases) ~= n || numel(solved_flags) ~= n || ...
        any(strlength(final_paths) == 0)
    error('write_s11_case_set_atomic:InputShape', ...
        'Inputs must contain the same nonzero number of case entries.');
end

parents = strings(n, 1);
for k = 1:n
    parents(k) = string(fileparts(char(final_paths(k))));
    if strlength(parents(k)) == 0 || ~isfolder(parents(k))
        error('write_s11_case_set_atomic:OutputDirectory', ...
            'Output directory does not exist for %s.', final_paths(k));
    end
end
if any(~strcmpi(parents, parents(1)))
    error('write_s11_case_set_atomic:OutputDirectory', ...
        'All files in one atomic case set must share an output directory.');
end

stage_dir = string(tempname(char(parents(1))));
[made, message] = mkdir(stage_dir);
if ~made
    error('write_s11_case_set_atomic:StageDirectory', ...
        'Could not create staging directory: %s', message);
end
cleanup = onCleanup(@() cleanup_stage(stage_dir));
stage_paths = strings(n, 1);
max_difference = nan(n, 1);
q_limit_pf_success = false(n, 1);

for k = 1:n
    [~, name, ext] = fileparts(char(final_paths(k)));
    stage_paths(k) = fullfile(stage_dir, string(name) + string(ext));
    savecase(char(stage_paths(k)), cases{k});
    loaded = loadcase(char(stage_paths(k)));
    [max_difference(k), q_limit_pf_success(k)] = ...
        verify_round_trip(cases{k}, loaded, solved_flags(k), final_paths(k));
end

% All cases have passed reload and PF verification before any final file is
% replaced. The same-volume move from a sibling staging directory minimizes
% the window in which a managed case set could be partially published.
for k = 1:n
    [moved, message, message_id] = movefile( ...
        char(stage_paths(k)), char(final_paths(k)), 'f');
    if ~moved
        error('write_s11_case_set_atomic:PublishFailure', ...
            'Could not publish %s (%s): %s', ...
            final_paths(k), message_id, message);
    end
end

report = table(final_paths, solved_flags, max_difference, ...
    q_limit_pf_success, ...
    'VariableNames', {'case_file','solved_result','max_roundtrip_difference', ...
    'q_limit_pf_success'});
end

function [max_difference, success] = verify_round_trip( ...
        expected, loaded, solved, final_path)
define_constants;
if size(loaded.bus, 1) ~= size(expected.bus, 1) || ...
        size(loaded.gen, 1) ~= size(expected.gen, 1) || ...
        size(loaded.branch, 1) ~= size(expected.branch, 1) || ...
        size(loaded.bus, 1) ~= 49 || size(loaded.branch, 1) ~= 83
    error('write_s11_case_set_atomic:RoundTripShape', ...
        'Reloaded S11 case has an unexpected matrix shape: %s', final_path);
end
branch_columns = 13;
if solved, branch_columns = QT; end
required = [13 21 branch_columns];
available = [size(expected.bus, 2) size(expected.gen, 2) ...
    size(expected.branch, 2); size(loaded.bus, 2) size(loaded.gen, 2) ...
    size(loaded.branch, 2)];
if any(available < required)
    error('write_s11_case_set_atomic:RoundTripColumns', ...
        'Reloaded S11 case lost required MATPOWER columns: %s', final_path);
end

differences = [abs(double(expected.baseMVA)-double(loaded.baseMVA)); ...
    matrix_difference(expected.bus(:, 1:13), loaded.bus(:, 1:13)); ...
    matrix_difference(expected.gen(:, 1:21), loaded.gen(:, 1:21)); ...
    matrix_difference(expected.branch(:, 1:branch_columns), ...
        loaded.branch(:, 1:branch_columns))];
if isfield(expected, 'gencost') && isfield(loaded, 'gencost')
    differences(end+1, 1) = matrix_difference_zero_padded( ...
        expected.gencost, loaded.gencost);
end
max_difference = max(differences);
if ~isfinite(max_difference) || max_difference > 1e-4
    error('write_s11_case_set_atomic:RoundTripDifference', ...
        'Saved case %s changed by %.9g, above the 1e-4 tolerance.', ...
        final_path, max_difference);
end

try
    [~, success] = runpf(loaded, mpoption('verbose', 0, 'out.all', 0, ...
        'pf.enforce_q_lims', 1));
catch err
    error('write_s11_case_set_atomic:RoundTripPF', ...
        'Reloaded case %s raised during Q-limit PF: %s', ...
        final_path, err.message);
end
if ~success
    error('write_s11_case_set_atomic:RoundTripPF', ...
        'Reloaded case failed Q-limit PF: %s', final_path);
end
end

function value = matrix_difference(a, b)
if ~isequal(size(a), size(b))
    value = Inf;
    return;
end
delta = abs(double(a)-double(b));
same_nan = isnan(a) & isnan(b);
delta(same_nan) = 0;
value = max([0; delta(:)]);
end

function value = matrix_difference_zero_padded(a, b)
% SAVECASE omits polynomial-cost trailing zeros beyond each row's NCOST.
% Compare the serialized and in-memory forms after restoring those zeros.
if size(a, 1) ~= size(b, 1)
    value = Inf;
    return;
end
columns = max(size(a, 2), size(b, 2));
aa = zeros(size(a, 1), columns);
bb = zeros(size(b, 1), columns);
aa(:, 1:size(a, 2)) = a;
bb(:, 1:size(b, 2)) = b;
value = matrix_difference(aa, bb);
end

function cleanup_stage(stage_dir)
if isfolder(stage_dir)
    rmdir(char(stage_dir), 's');
end
end
