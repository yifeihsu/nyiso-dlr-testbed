function [mpc, report] = apply_s11_hourly_load_profile(mpc, profile, hour_index)
%APPLY_S11_HOURLY_LOAD_PROFILE Apply one generated bus-load snapshot by bus ID.
%   [MPC, REPORT] = APPLY_S11_HOURLY_LOAD_PROFILE(MPC, PROFILE, HOUR_INDEX)
%   accepts a profile struct or a MAT-file containing a variable named profile
%   (or the profile fields at the file's top level). Required fields are
%   bus_id, pd_mw and qd_mvar; load matrices are bus-by-hour. HOUR_INDEX is a
%   one-based column index, not an hour of day. The profile and case must have
%   identical bus-ID sets, but either may use any bus-row order.
%
%   Only bus PD/QD columns change. Network GS/BS shunts, generation, branch
%   data and all metadata are preserved. Generated QD is a model assumption,
%   not an observed hourly reactive-demand series. Applying a profile does
%   not redispatch generation or establish power-flow feasibility.

if nargin ~= 3
    error('apply_s11_hourly_load_profile:Arguments', ...
        'Supply a case, a profile struct or MAT-file, and an hour index.');
end
if ischar(profile) || (isstring(profile) && isscalar(profile))
    saved = load(char(profile), '-mat');
    if isfield(saved, 'profile')
        profile = saved.profile;
    else
        profile = saved;
    end
end
if ~isstruct(profile) || ~isscalar(profile) || ...
        ~all(isfield(profile, {'bus_id', 'pd_mw', 'qd_mvar'}))
    error('apply_s11_hourly_load_profile:ProfileFields', ...
        'Profile must be a scalar struct with bus_id, pd_mw and qd_mvar.');
end
if ~isstruct(mpc) || ~isscalar(mpc) || ~isfield(mpc, 'bus') || ...
        ~isnumeric(mpc.bus) || ~isreal(mpc.bus) || ...
        ~ismatrix(mpc.bus) || isempty(mpc.bus) || size(mpc.bus, 2) < 4
    error('apply_s11_hourly_load_profile:Case', ...
        'Case must contain a real numeric bus matrix with at least four columns.');
end
ids = profile.bus_id;
case_ids = mpc.bus(:, 1);
if ~valid_ids(ids) || ~valid_ids(case_ids)
    error('apply_s11_hourly_load_profile:BusIds', ...
        'Case and profile bus IDs must be unique finite positive integers.');
end
ids = double(ids(:));
[found, rows] = ismember(double(case_ids), ids);
if numel(ids) ~= numel(case_ids) || ~all(found)
    error('apply_s11_hourly_load_profile:BusIds', ...
        'Profile and case must contain exactly the same bus-ID set.');
end
p = profile.pd_mw;
q = profile.qd_mvar;
if ~isnumeric(p) || ~isnumeric(q) || ~isreal(p) || ~isreal(q) || ...
        ~ismatrix(p) || ~ismatrix(q) || isempty(p) || ...
        ~isequal(size(p), size(q)) || size(p, 1) ~= numel(ids)
    error('apply_s11_hourly_load_profile:ProfileShape', ...
        'pd_mw and qd_mvar must be matching nonempty bus-by-hour numeric matrices.');
end
if any(~isfinite(p(:))) || any(~isfinite(q(:))) || any(p(:) < 0)
    error('apply_s11_hourly_load_profile:LoadValues', ...
        'All loads must be finite; active loads must be nonnegative. Signed Q is allowed.');
end
hour_count = size(p, 2);
if ~isnumeric(hour_index) || ~isreal(hour_index) || ~isscalar(hour_index) || ...
        ~isfinite(hour_index) || hour_index ~= fix(hour_index) || ...
        hour_index < 1 || hour_index > hour_count
    error('apply_s11_hourly_load_profile:HourIndex', ...
        'hour_index must be a one-based integer from 1 to %d.', hour_count);
end

report = struct('hour_index', double(hour_index), 'hour_count', hour_count, ...
    'bus_id', case_ids, 'total_pd_mw', sum(p(:, hour_index)), ...
    'total_qd_mvar', sum(q(:, hour_index)), 'power_flow_verified', false);
time_fields = {'timestamp_utc', 'timestamp_local', 'source_time_zone'};
for k = 1:numel(time_fields)
    field = time_fields{k};
    if isfield(profile, field)
        values = profile.(field);
        if ~(iscellstr(values) || isstring(values)) || ...
                ~isvector(values) || numel(values) ~= hour_count
            error('apply_s11_hourly_load_profile:Timestamps', ...
                'Optional field %s must contain one text value per profile hour.', field);
        end
        report.(field) = char(string(values(hour_index)));
    end
end

% Resolve identity before assignment; never interpret a bus ID as a row number.
mpc.bus(:, 3) = p(rows, hour_index);
mpc.bus(:, 4) = q(rows, hour_index);
end

function ok = valid_ids(ids)
ok = isnumeric(ids) && isreal(ids) && isvector(ids) && ~isempty(ids) && ...
    all(isfinite(ids(:))) && all(ids(:) > 0) && ...
    all(ids(:) == fix(ids(:))) && numel(unique(ids(:))) == numel(ids);
end
