function report = test_apply_s11_hourly_operating_profile
%TEST_APPLY_S11_HOURLY_OPERATING_PROFILE Test routing and control preservation.
%   Fixtures exercise application semantics, not power-flow feasibility.
root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
case_dir = fullfile(root, 'System Matpower Format');
old_path = path;
restore_path = onCleanup(@() path(old_path));
addpath(case_dir, fullfile(case_dir, 'NY_Lite'));
base = npcc_ny_lite_s11_dlr_pf_base;
[profile, operating] = fixture(base);

% Identity baseline with only external equality bounds tightened as promised.
[baseline, baseline_report] = apply_s11_hourly_operating_profile(base, profile, operating, 1);
expected = base;
expected.gen(42:49, 9:10) = repmat(base.gen(42:49, 2), 1, 2);
assert(isequaln(baseline, expected));
assert(baseline_report.profile_hour_valid && ~baseline_report.power_flow_rerun);

% Independently permute buses, generator/control rows and both profile axes.
nb = size(base.bus, 1);
ng = size(base.gen, 1);
case_buses = nb:-1:1;
case_gens = [2:2:ng 1:2:ng];
op_buses = [3:nb 1 2];
op_gens = ng:-1:1;
load_buses = [2:nb 1];
reordered = base;
reordered.bus = base.bus(case_buses, :);
reordered.bus_name = base.bus_name(case_buses);
reordered.gen = base.gen(case_gens, :);
reordered.gencost = base.gencost(case_gens, :);
reordered.genfuel = base.genfuel(case_gens);
reordered.gentype = base.gentype(case_gens);
reordered.userdata = struct('must_be_preserved', 'user annotation');
permuted_load = profile;
for field = {'bus_id','pd_mw','qd_mvar'}
    permuted_load.(field{1}) = profile.(field{1})(load_buses, :);
end
permuted_op = operating;
for field = {'bus_id','bus_vm_pu','bus_va_deg','bus_type'}
    permuted_op.(field{1}) = operating.(field{1})(op_buses, :);
end
for field = {'gen_id','gen_bus_id','genfuel','gentype','base_gen', ...
        'pg_mw','qg_mvar','vg_pu','gen_status'}
    permuted_op.(field{1}) = operating.(field{1})(op_gens, :);
end
permuted_op.external_gen_indices = find(strcmp(permuted_op.genfuel, 'external_schedule'));
[actual, applied] = apply_s11_hourly_operating_profile(reordered, permuted_load, permuted_op, 2);
expected = reordered;
expected.bus(:, 3) = profile.pd_mw(case_buses, 2);
expected.bus(:, 4) = profile.qd_mvar(case_buses, 2);
expected.bus(:, 8) = operating.bus_vm_pu(case_buses, 2);
expected.bus(:, 9) = operating.bus_va_deg(case_buses, 2);
expected.bus(:, 2) = operating.bus_type(case_buses, 2);
expected.gen(:, 2) = operating.pg_mw(case_gens, 2);
expected.gen(:, 3) = operating.qg_mvar(case_gens, 2);
expected.gen(:, 6) = operating.vg_pu(case_gens, 2);
expected.gen(:, 8) = operating.gen_status(case_gens, 2);
external = case_gens >= 42;
expected.gen(external, 9:10) = repmat(operating.pg_mw(case_gens(external), 2), 1, 2);
assert(isequaln(actual, expected), ...
    'Only documented operating/load fields may change, independently of row order.');
assert(strcmp(applied.timestamp_utc, '2025-07-01T05:00:00Z'));
assert(abs(applied.net_import_mw - sum(operating.pg_mw(42:49, 2))) < 1e-9);
assert(isequal(actual.gen(~external, 9:10), reordered.gen(~external, 9:10)));
assert(isequal(actual.gen(:, 4:5), reordered.gen(:, 4:5)));
assert(isequal(actual.bus(:, 5:6), reordered.bus(:, 5:6)));
assert(isequal(actual.branch, reordered.branch));
assert(isequal(actual.gencost, reordered.gencost));

% Application can be repeated to select another hour with different schedules.
reapplied = apply_s11_hourly_operating_profile(actual, permuted_load, permuted_op, 1);
direct = apply_s11_hourly_operating_profile(reordered, permuted_load, permuted_op, 1);
assert(isequaln(reapplied, direct));

% Both named MAT-file interfaces must reproduce direct struct application.
mat_path = [tempname, '.mat'];
remove_mat = onCleanup(@() delete_if_present(mat_path));
save(mat_path, 'profile', 'operating');
from_file = apply_s11_hourly_operating_profile(base, mat_path, mat_path, 2);
from_struct = apply_s11_hourly_operating_profile(base, profile, operating, 2);
assert(isequaln(from_file, from_struct));

rejected = 0;
for bad_hour = {0, -1, 4, 1.5, NaN, Inf, [1 2], '1'}
    expect_error(@() apply_s11_hourly_operating_profile(base, profile, operating, bad_hour{1}), 'HourIndex');
    rejected = rejected + 1;
end
bad = operating; bad.valid(1) = false;
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'InvalidHour');
bad = operating; bad.valid = double(bad.valid);
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'Validity');
for field = {'timestamp_utc','timestamp_local','source_time_zone'}
    bad = operating; bad.(field{1}){3} = 'mismatch in an unselected hour';
    expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'Timestamps');
end
bad = profile; bad = rmfield(bad, 'timestamp_utc');
expect_error(@() apply_s11_hourly_operating_profile(base, bad, operating, 1), 'Timestamps');
rejected = rejected + 6;

bad = operating; bad.gen_status(1, 1) = 2;
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'Status');
bad = operating; bad.gen_status(42, 1) = 0;
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'Status');
bad = operating; bad.gen_status(1, 1) = 0;
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'OfflineInjection');
bad = operating; bad.pg_mw(1, 1) = NaN;
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'ControlValues');
bad = operating; bad.vg_pu(1, 1) = -1;
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'ControlValues');
bad = operating; bad.qg_mvar(2, 1) = bad.qg_mvar(2, 1) + 1;
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'FixedControls');
bad = operating; bad.pg_mw(39, 1) = 1;
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'FixedControls');
bad = operating; bad.qg_mvar(42, 1) = 1;
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'FixedControls');
bad = operating; bad.bus_type(bad.bus_id == 43, 1) = 2;
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'BusControls');
bad = operating; bad.bus_type(bad.bus_id == 73, 1) = 2;
bad.bus_type(bad.bus_id == 37, 1) = 3;
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'BusControls');
rejected = rejected + 10;

bad = operating; bad.gen_id{2} = bad.gen_id{1};
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'GeneratorIdentity');
bad = operating; bad.genfuel{1} = 'unknown role';
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'GeneratorIdentity');
bad_case = base; bad_case.gen(2, :) = bad_case.gen(1, :);
bad_case.genfuel{2} = bad_case.genfuel{1}; bad_case.gentype{2} = bad_case.gentype{1};
expect_error(@() apply_s11_hourly_operating_profile(bad_case, profile, operating, 1), 'GeneratorIdentity');
bad = operating; bad.external_gen_indices(1) = 41;
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'ExternalIdentity');
bad = operating; bad.bus_id(1) = bad.bus_id(2);
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'BusIds');
bad_case = base; bad_case.gen(1, 9) = bad_case.gen(1, 9) + 1;
expect_error(@() apply_s11_hourly_operating_profile(bad_case, profile, operating, 1), 'Capabilities');
bad = operating; bad.pg_mw = bad.pg_mw(:, 1:2);
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'Validity');
bad = operating; bad.qg_mvar = bad.qg_mvar(:, 1:2);
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'ProfileShape');
bad = operating; bad.base_gen(1, 1) = 123456;
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 1), 'BaseGenerator');
rejected = rejected + 9;

% Invalid columns may retain NaNs for honest failed-hour reporting. They may
% not prevent an independently valid column from being applied.
bad = operating; bad.valid(3) = false;
for field = {'pg_mw','qg_mvar','vg_pu','gen_status','bus_vm_pu','bus_va_deg','bus_type'}
    bad.(field{1})(:, 3) = NaN;
end
with_invalid_other_hour = apply_s11_hourly_operating_profile(base, profile, bad, 1);
assert(isequaln(with_invalid_other_hour, baseline));
expect_error(@() apply_s11_hourly_operating_profile(base, profile, bad, 3), 'InvalidHour');
rejected = rejected + 1;

report = struct('passed', true, 'bus_count', nb, 'generator_control_row_count', ng, ...
    'invalid_inputs_rejected', rejected, 'independent_row_permutations_verified', true, ...
    'internal_capabilities_and_network_preserved', true, ...
    'exact_hourly_external_bounds_verified', true, 'offline_injections_verified', true, ...
    'mat_file_interfaces_verified', true, 'all_timestamp_alignment_checked', true, ...
    'invalid_hours_rejected', true, 'power_flow_run_by_this_test', false);
disp(jsonencode(report));
end

function [profile, operating] = fixture(base)
time_utc = {'2025-07-01T04:00:00Z'; '2025-07-01T05:00:00Z'; '2025-07-01T06:00:00Z'};
time_local = {'2025-07-01T00:00:00-04:00'; '2025-07-01T01:00:00-04:00'; '2025-07-01T02:00:00-04:00'};
zone = {'EDT'; 'EDT'; 'EDT'};
profile = struct('bus_id', base.bus(:, 1), ...
    'pd_mw', base.bus(:, 3) * [1 0.75 0.5], 'qd_mvar', base.bus(:, 4) * [1 0.75 0.5], ...
    'timestamp_utc', {time_utc}, 'timestamp_local', {time_local}, 'source_time_zone', {zone});
ng = size(base.gen, 1);
operating = struct('bus_id', base.bus(:, 1), 'gen_id', {cellstr("S11:G" + string((1:ng)'))}, ...
    'gen_bus_id', base.gen(:, 1), 'genfuel', {base.genfuel}, 'gentype', {base.gentype}, ...
    'base_gen', base.gen, 'timestamp_utc', {time_utc}, 'timestamp_local', {time_local}, ...
    'source_time_zone', {zone}, 'pg_mw', repmat(base.gen(:, 2), 1, 3), ...
    'qg_mvar', repmat(base.gen(:, 3), 1, 3), 'vg_pu', repmat(base.gen(:, 6), 1, 3), ...
    'gen_status', repmat(base.gen(:, 8), 1, 3), 'bus_vm_pu', repmat(base.bus(:, 8), 1, 3), ...
    'bus_va_deg', repmat(base.bus(:, 9), 1, 3), 'bus_type', repmat(base.bus(:, 2), 1, 3), ...
    'external_gen_indices', (42:49)', 'valid', true(3, 1));
operating.pg_mw(42:49, 2) = operating.pg_mw(42:49, 2) + (1:8)';
operating.gen_status(11, 2) = 0;
operating.pg_mw(11, 2) = 0;
operating.qg_mvar(11, 2) = 0;
operating.vg_pu(:, 2) = operating.vg_pu(:, 2) + 0.002;
operating.bus_vm_pu(:, 2) = operating.bus_vm_pu(:, 2) + 0.002;
operating.bus_va_deg(:, 2) = operating.bus_va_deg(:, 2) + 0.1;
operating.bus_type(operating.bus_id == 41, 2) = 1;
end

function expect_error(action, suffix)
expected = ['apply_s11_hourly_operating_profile:' suffix];
try
    action();
catch exception
    assert(strcmp(exception.identifier, expected), ...
        'Expected %s but received %s.', expected, exception.identifier);
    return;
end
error('test_apply_s11_hourly_operating_profile:MissingError', 'Expected %s.', expected);
end

function delete_if_present(pathname)
if isfile(pathname), delete(pathname); end
end
