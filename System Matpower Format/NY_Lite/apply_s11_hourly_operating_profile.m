function [mpc, report] = apply_s11_hourly_operating_profile(mpc, load_profile, operating, hour_index)
%APPLY_S11_HOURLY_OPERATING_PROFILE Apply an aligned, validated S11 hour.
%   Each profile may be a scalar struct or a MAT-file containing PROFILE
%   (loads) / OPERATING (generation and controls). Matrices are device-by-hour.
%   Buses map by bus ID. Generator/control rows map by the unique combination
%   of bus ID, genfuel and gentype, including repeated generator buses.
%
%   Applies load, PG/QG/VG/status, bus VM/VA/type, and the exact hourly P bounds
%   of external schedules. Internal capability limits, GS/BS, branch data,
%   gencost and other metadata are preserved. Invalid or unaligned hours fail.
%   The validity flag belongs to the supplied package; this helper does not
%   run a new power flow or certify a modified network.

if nargin ~= 4
    fail('Arguments', 'Supply a case, load profile, operating profile, and hour index.');
end
load_profile = read_profile(load_profile, 'profile');
operating = read_profile(operating, 'operating');
required = {'bus_id','gen_id','gen_bus_id','genfuel','gentype','base_gen', ...
    'timestamp_utc','timestamp_local','source_time_zone','pg_mw','qg_mvar', ...
    'vg_pu','gen_status','bus_vm_pu','bus_va_deg','bus_type', ...
    'external_gen_indices','valid'};
if ~isstruct(operating) || ~isscalar(operating) || ~all(isfield(operating, required))
    fail('ProfileFields', 'Operating profile is missing required identity, time, control or validity fields.');
end
if ~isstruct(load_profile) || ~isscalar(load_profile) || ...
        ~all(isfield(load_profile, {'bus_id','pd_mw','qd_mvar'}))
    fail('ProfileFields', 'Load profile must contain bus_id, pd_mw and qd_mvar.');
end
if ~isstruct(mpc) || ~isscalar(mpc) || ...
        ~all(isfield(mpc, {'bus','gen','genfuel','gentype'})) || ...
        ~real_matrix(mpc.bus) || size(mpc.bus, 2) < 13 || ...
        ~real_matrix(mpc.gen) || size(mpc.gen, 2) < 21
    fail('Case', 'Case requires bus/gen matrices and aligned genfuel/gentype metadata.');
end
nb = size(mpc.bus, 1);
ng = size(mpc.gen, 1);
if nb ~= 49 || ng ~= 49 || ~valid_ids(operating.bus_id) || ...
        ~valid_ids(mpc.bus(:, 1)) || numel(operating.bus_id) ~= nb
    fail('BusIds', 'The case and operating profile must contain 49 unique S11 bus IDs.');
end
[found, bus_rows] = ismember(mpc.bus(:, 1), operating.bus_id(:));
if ~all(found)
    fail('BusIds', 'Case and operating profile bus-ID sets must match.');
end
if ~real_matrix(operating.pg_mw) || size(operating.pg_mw, 1) ~= ng || ...
        isempty(operating.pg_mw)
    fail('ProfileShape', 'Operating matrices must be nonempty device-by-hour numeric matrices.');
end
nh = size(operating.pg_mw, 2);
if ~isnumeric(hour_index) || ~isreal(hour_index) || ~isscalar(hour_index) || ...
        ~isfinite(hour_index) || hour_index ~= fix(hour_index) || ...
        hour_index < 1 || hour_index > nh
    fail('HourIndex', 'hour_index must be an integer in the operating profile column range.');
end
if ~islogical(operating.valid) || ~isvector(operating.valid) || numel(operating.valid) ~= nh
    fail('Validity', 'valid must contain one logical validity flag per profile hour.');
end
if ~operating.valid(hour_index)
    fail('InvalidHour', 'The selected hour is not validated for operating-profile application.');
end
gen_fields = {'pg_mw','qg_mvar','vg_pu','gen_status'};
bus_fields = {'bus_vm_pu','bus_va_deg','bus_type'};
check_hour_matrices(operating, gen_fields, ng, nh, hour_index);
check_hour_matrices(operating, bus_fields, nb, nh, hour_index);
if ~real_matrix(load_profile.pd_mw) || ~real_matrix(load_profile.qd_mvar) || ...
        size(load_profile.pd_mw, 2) ~= nh || size(load_profile.qd_mvar, 2) ~= nh
    fail('ProfileShape', 'Load and operating profiles must have the same hour count.');
end
time_fields = {'timestamp_utc','timestamp_local','source_time_zone'};
for k = 1:numel(time_fields)
    field = time_fields{k};
    if ~isfield(load_profile, field)
        fail('Timestamps', 'Both profiles require UTC/local timestamps and source_time_zone.');
    end
    operating_time = text_vector(operating.(field), nh, 'Timestamps');
    load_time = text_vector(load_profile.(field), nh, 'Timestamps');
    if ~isequal(operating_time, load_time)
        fail('Timestamps', 'Load and operating timestamps/time zones must match at every index.');
    end
end

ids = text_vector(operating.gen_id, ng, 'GeneratorIdentity');
if numel(unique(ids)) ~= ng || ~valid_repeated_ids(operating.gen_bus_id, ng)
    fail('GeneratorIdentity', 'Generator IDs must be unique and generator bus IDs must be valid.');
end
op_fuel = text_vector(operating.genfuel, ng, 'GeneratorIdentity');
op_type = text_vector(operating.gentype, ng, 'GeneratorIdentity');
case_fuel = text_vector(mpc.genfuel, ng, 'GeneratorIdentity');
case_type = text_vector(mpc.gentype, ng, 'GeneratorIdentity');
op_keys = identity_keys(operating.gen_bus_id(:), op_fuel, op_type);
case_keys = identity_keys(mpc.gen(:, 1), case_fuel, case_type);
if numel(unique(op_keys)) ~= ng || numel(unique(case_keys)) ~= ng
    fail('GeneratorIdentity', 'Bus, genfuel and gentype must identify each row uniquely.');
end
[found, gen_rows] = ismember(case_keys, op_keys);
if ~all(found)
    fail('GeneratorIdentity', 'Case and profile generator/control identity sets must match.');
end
base_gen = operating.base_gen;
if ~real_matrix(base_gen) || size(base_gen, 1) ~= ng || size(base_gen, 2) < 21 || ...
        any(~isfinite(base_gen(:, 1:21)), 'all') || ...
        ~isequal(base_gen(:, 1), double(operating.gen_bus_id(:)))
    fail('BaseGenerator', 'base_gen must align with the profile generator identities.');
end
external = op_fuel == "external_schedule";
external_rows = operating.external_gen_indices;
if nnz(external) ~= 8 || ~valid_ids(external_rows) || ...
        ~isequal(sort(double(external_rows(:))), find(external))
    fail('ExternalIdentity', 'external_gen_indices must identify exactly the eight external_schedule rows.');
end
case_external = external(gen_rows);
% Require the saved capabilities; an unrelated case with matching IDs must
% not silently inherit a validity label derived from another fleet.
fixed_cols = [4 5 7 11:21];
if ~isequal(mpc.gen(:, fixed_cols), base_gen(gen_rows, fixed_cols)) || ...
        ~isequal(mpc.gen(~case_external, 9:10), base_gen(gen_rows(~case_external), 9:10))
    fail('Capabilities', 'Case generator capabilities do not match the operating profile baseline.');
end
p = operating.pg_mw(:, hour_index);
q = operating.qg_mvar(:, hour_index);
vg = operating.vg_pu(:, hour_index);
status = operating.gen_status(:, hour_index);
if any(status ~= 0 & status ~= 1) || any(status(external) ~= 1)
    fail('Status', 'Generator status must be zero or one; external schedules must be online.');
end
if any(abs(p(status == 0)) > 1e-6) || any(abs(q(status == 0)) > 1e-6)
    fail('OfflineInjection', 'Offline generator/control rows must have zero PG and QG.');
end
if any(vg <= 0) || any(operating.bus_vm_pu(:, hour_index) <= 0)
    fail('ControlValues', 'Generator setpoints and bus voltage magnitudes must be positive.');
end
fixed_q = abs(base_gen(:, 4) - base_gen(:, 5)) <= 1e-10 & status == 1;
zero_p = base_gen(:, 9) == 0 & base_gen(:, 10) == 0;
if any(abs(q(fixed_q) - base_gen(fixed_q, 5)) > 1e-3) || ...
        any(abs(p(zero_p)) > 1e-6) || any(abs(q(external)) > 1e-6) || ...
        any(base_gen(external, 4:5) ~= 0, 'all')
    fail('FixedControls', 'Fixed-Q, zero-P and external zero-Q control identities must be preserved.');
end
types = operating.bus_type(:, hour_index);
profile_bus_ids = operating.bus_id(:);
if any(~ismember(types, [1 2 3])) || nnz(types == 3) ~= 1 || ...
        profile_bus_ids(types == 3) ~= 73 || ...
        any(~ismember(profile_bus_ids(types == 2 | types == 3), [37 38 39 41 73 76 81]))
    fail('BusControls', 'S11 requires REF bus 73 and only its seven allowed regulating candidates.');
end

[mpc, load_report] = apply_s11_hourly_load_profile(mpc, load_profile, hour_index);
mpc.gen(:, 2) = p(gen_rows);
mpc.gen(:, 3) = q(gen_rows);
mpc.gen(:, 6) = vg(gen_rows);
mpc.gen(:, 8) = status(gen_rows);
mpc.gen(case_external, 9:10) = repmat(p(gen_rows(case_external)), 1, 2);
mpc.bus(:, 8) = operating.bus_vm_pu(bus_rows, hour_index);
mpc.bus(:, 9) = operating.bus_va_deg(bus_rows, hour_index);
mpc.bus(:, 2) = types(bus_rows);
report = struct('hour_index', double(hour_index), 'hour_count', nh, ...
    'timestamp_utc', char(string(operating.timestamp_utc(hour_index))), ...
    'timestamp_local', char(string(operating.timestamp_local(hour_index))), ...
    'source_time_zone', char(string(operating.source_time_zone(hour_index))), ...
    'profile_hour_valid', true, 'power_flow_rerun', false, ...
    'case_gen_to_profile_row', gen_rows, 'case_bus_to_profile_row', bus_rows, ...
    'total_pd_mw', load_report.total_pd_mw, 'total_qd_mvar', load_report.total_qd_mvar, ...
    'internal_generation_mw', sum(p(~external)), 'net_import_mw', sum(p(external)), ...
    'online_internal_control_rows', nnz(status(~external)));
end

function value = read_profile(value, field)
if ischar(value) || (isstring(value) && isscalar(value))
    saved = load(char(value), '-mat');
    if ~isfield(saved, field)
        fail('ProfileFields', 'MAT-file must contain the named profile variable.');
    end
    value = saved.(field);
end
end

function check_hour_matrices(profile, fields, rows, columns, hour)
for k = 1:numel(fields)
    values = profile.(fields{k});
    if ~real_matrix(values) || ~isequal(size(values), [rows columns])
        fail('ProfileShape', 'Operating matrix dimensions must match device and hour counts.');
    end
    if any(~isfinite(values(:, hour)))
        fail('ControlValues', 'Selected operating-hour values must be finite.');
    end
end
end

function values = text_vector(values, count, identifier)
if ~(iscellstr(values) || isstring(values)) || ~isvector(values) || numel(values) ~= count
    fail(identifier, 'Expected a text vector with one entry per identity or timestamp.');
end
values = string(values(:));
if any(ismissing(values)) || any(strlength(values) == 0)
    fail(identifier, 'Identity and timestamp text must not be missing or empty.');
end
end

function keys = identity_keys(bus, fuel, type)
if ~valid_repeated_ids(bus, numel(fuel)) || any(contains(fuel, '|')) || any(contains(type, '|'))
    fail('GeneratorIdentity', 'Invalid generator bus or ambiguous role/type text.');
end
keys = string(bus(:)) + "|" + fuel + "|" + type;
end

function ok = real_matrix(values)
ok = isnumeric(values) && isreal(values) && ismatrix(values);
end

function ok = valid_ids(values)
ok = valid_repeated_ids(values, numel(values)) && numel(unique(values(:))) == numel(values);
end

function ok = valid_repeated_ids(values, count)
ok = isnumeric(values) && isreal(values) && isvector(values) && ~isempty(values) && ...
    numel(values) == count && all(isfinite(values(:))) && ...
    all(values(:) > 0) && all(values(:) == fix(values(:)));
end

function fail(identifier, message)
error(['apply_s11_hourly_operating_profile:' identifier], '%s', message);
end
