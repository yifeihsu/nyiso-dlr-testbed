function report = test_apply_s11_hourly_load_profile
%TEST_APPLY_S11_HOURLY_LOAD_PROFILE Identity and preservation checks on S11.
repo_dir = fileparts(fileparts(fileparts(mfilename('fullpath'))));
case_dir = fullfile(repo_dir, 'System Matpower Format');
old_path = path;
restore_path = onCleanup(@() path(old_path)); %#ok<NASGU>
addpath(case_dir, fullfile(case_dir, 'NY_Lite'));
base = npcc_ny_lite_s11_dlr_pf_base;
n = size(base.bus, 1);
assert(n == 49, 'Expected the saved 49-bus S11 case.');
profile = struct('bus_id', base.bus(:, 1), ...
    'pd_mw', base.bus(:, 3) * [0.5, 0.75, 1.0], ...
    'qd_mvar', base.bus(:, 4) * [0.5, 0.75, 1.0], ...
    'timestamp_utc', {{'2025-07-01T04:00:00Z'; '2025-07-01T05:00:00Z'; ...
        '2025-07-01T06:00:00Z'}}, ...
    'timestamp_local', {{'2025-07-01T00:00:00-04:00'; ...
        '2025-07-01T01:00:00-04:00'; '2025-07-01T02:00:00-04:00'}}, ...
    'source_time_zone', {{'EDT'; 'EDT'; 'EDT'}});

% Independently reorder case and profile to detect positional application.
case_order = [n:-1:1];
profile_order = [2:n, 1];
reordered = base;
reordered.bus = base.bus(case_order, :);
reordered.userdata = struct('preserve_this_field', 'unchanged');
permuted = profile;
permuted.bus_id = profile.bus_id(profile_order);
permuted.pd_mw = profile.pd_mw(profile_order, :);
permuted.qd_mvar = profile.qd_mvar(profile_order, :);
[actual, applied] = apply_s11_hourly_load_profile(reordered, permuted, 2);
expected = reordered;
expected.bus(:, 3:4) = 0.75 * reordered.bus(:, 3:4);
assert(isequaln(actual, expected), ...
    'Loads must map by ID while GS/BS, generators, branches and metadata stay identical.');
assert(strcmp(applied.timestamp_utc, '2025-07-01T05:00:00Z'));
assert(abs(applied.total_pd_mw - sum(expected.bus(:, 3))) < 1e-9);
assert(abs(applied.total_qd_mvar - sum(expected.bus(:, 4))) < 1e-9);
assert(~applied.power_flow_verified);
baseline = apply_s11_hourly_load_profile(base, profile, 3);
assert(isequaln(baseline, base), 'Baseline profile must reproduce the saved case.');

% MAT-file and direct-struct interfaces must produce the same result.
mat_path = [tempname, '.mat'];
remove_mat = onCleanup(@() delete_if_present(mat_path)); %#ok<NASGU>
save(mat_path, 'profile');
from_file = apply_s11_hourly_load_profile(base, mat_path, 1);
from_struct = apply_s11_hourly_load_profile(base, profile, 1);
assert(isequaln(from_file, from_struct));
save(mat_path, '-struct', 'profile');
from_fields = apply_s11_hourly_load_profile(base, mat_path, 1);
assert(isequaln(from_fields, from_struct));

rejected = 0;
for bad_hour = {0, -1, 4, 1.5, NaN, Inf, [1 2], '1'}
    expect_error(@() apply_s11_hourly_load_profile(base, profile, bad_hour{1}), 'HourIndex');
    rejected = rejected + 1;
end
bad = profile; bad.bus_id(1) = bad.bus_id(2);
expect_error(@() apply_s11_hourly_load_profile(base, bad, 1), 'BusIds');
bad = profile; bad.bus_id(1) = 123456;
expect_error(@() apply_s11_hourly_load_profile(base, bad, 1), 'BusIds');
bad = profile; bad.bus_id = bad.bus_id(2:end);
expect_error(@() apply_s11_hourly_load_profile(base, bad, 1), 'BusIds');
bad = profile; bad.bus_id(1) = NaN;
expect_error(@() apply_s11_hourly_load_profile(base, bad, 1), 'BusIds');
bad_case = base; bad_case.bus(1, 1) = bad_case.bus(2, 1);
expect_error(@() apply_s11_hourly_load_profile(bad_case, profile, 1), 'BusIds');
rejected = rejected + 5;

bad = profile; bad.pd_mw = bad.pd_mw';
expect_error(@() apply_s11_hourly_load_profile(base, bad, 1), 'ProfileShape');
bad = profile; bad.qd_mvar = bad.qd_mvar(:, 1:2);
expect_error(@() apply_s11_hourly_load_profile(base, bad, 1), 'ProfileShape');
bad = profile; bad.pd_mw(1, 2) = NaN;
expect_error(@() apply_s11_hourly_load_profile(base, bad, 1), 'LoadValues');
bad = profile; bad.qd_mvar(1, 2) = Inf;
expect_error(@() apply_s11_hourly_load_profile(base, bad, 1), 'LoadValues');
bad = profile; bad.pd_mw(1, 2) = -1;
expect_error(@() apply_s11_hourly_load_profile(base, bad, 1), 'LoadValues');
bad = profile; bad.timestamp_utc = bad.timestamp_utc(1:2);
expect_error(@() apply_s11_hourly_load_profile(base, bad, 1), 'Timestamps');
rejected = rejected + 6;

report = struct('passed', true, 'bus_count', n, 'invalid_inputs_rejected', rejected, ...
    'row_reordering_verified', true, 'case_fields_preserved', true, ...
    'mat_file_load_verified', true);
disp(report);
end

function expect_error(action, suffix)
expected = ['apply_s11_hourly_load_profile:', suffix];
try
    action();
catch exception
    assert(strcmp(exception.identifier, expected), ...
        'Expected %s but received %s.', expected, exception.identifier);
    return;
end
error('test_apply_s11_hourly_load_profile:MissingError', 'Expected %s.', expected);
end

function delete_if_present(pathname)
if isfile(pathname), delete(pathname); end
end
