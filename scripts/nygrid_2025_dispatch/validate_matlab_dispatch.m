function validate_matlab_dispatch(artifact_folder)
% Independent MATPOWER replay of calendar and stress snapshots, no OPF.
root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
if nargin < 1
    artifact_folder = fullfile(root, 'output', 'nygrid_2025_dispatch', 'dispatch');
end
addpath(fullfile(root, 'System Matpower Format'));
clear npcc_nygrid_2025_full_dc
d = load(fullfile(artifact_folder, 'dispatch.mat'), 'hour_index', 'timestamp_utc', ...
    'gen_pg', 'dispatch_qualified', 'native_required_pg', 'reference_bus');
network = load(fullfile(artifact_folder, 'dispatch_network.mat'), 'hour_index', 'branch_pf', 'bus_va');
assert(isequal(d.hour_index, network.hour_index));
qualified = logical(d.dispatch_qualified(:));
t = datetime(string(d.timestamp_utc), 'InputFormat', "yyyy-MM-dd'T'HH:mm:ss'Z'", 'TimeZone', 'UTC');
local = t; local.TimeZone = 'America/New_York';
selected = [];
for mo = 1:12
    selected = [selected; find(month(local) == mo & qualified, 1)]; %#ok<AGROW>
end
ix = find(qualified);
[~, peak] = max(d.native_required_pg(ix));
[~, valley] = min(d.native_required_pg(ix));
fold = find(month(local) == 11 & day(local) == 2 & hour(local) == 1 & qualified);
selected = unique([selected; ix(peak); ix(valley); fold]);
options = mpoption('model', 'DC', 'verbose', 0, 'out.all', 0);
checks = [];
for h = selected'
    m = npcc_nygrid_2025_full_dc(h, artifact_folder);
    [r, ok] = rundcpf(m, options);
    assert(ok, 'DC solve failed at hour%d.', h);
    flow_error = max(abs(r.branch(:, 14) - network.branch_pf(h, :)'));
    generation_error = max(abs(r.gen(:, 2) - d.gen_pg(h, :)'));
    angle_error = max(abs(r.bus(:, 9) - network.bus_va(h, :)'));
    bound_error = max([0; r.gen(:, 10)-r.gen(:, 2); r.gen(:, 2)-r.gen(:, 9)]);
    assert(flow_error < 1e-7 && generation_error < 1e-7 && angle_error < 1e-7 && bound_error < 1e-7);
    assert(abs(r.bus(r.bus(:, 1) == double(d.reference_bus(h)), 9)) < 1e-9);
    checks = [checks; h, flow_error, generation_error, angle_error, bound_error]; %#ok<AGROW>
end
bad = find(~qualified, 1);
rejected = false;
if ~isempty(bad)
    try
        npcc_nygrid_2025_full_dc(bad, artifact_folder);
    catch err
        rejected = strcmp(err.identifier, 'nygrid2025:UnqualifiedHour');
    end
    assert(rejected, 'Loader did not reject the missing-source/failed hour.');
end
result = struct('passed', true, 'matlab_version', version, 'fresh_matpower_hours', numel(selected), ...
    'selected_hours', selected, 'maximum_branch_error_mw', max(checks(:, 2)), ...
    'maximum_generation_change_mw', max(checks(:, 3)), 'maximum_angle_error_deg', max(checks(:, 4)), ...
    'maximum_generator_bound_violation_mw', max(checks(:, 5)), 'unqualified_hour_rejected', rejected, ...
    'DC_only', true, 'AC_feasibility_validated', false);
mat_files = {'dispatch.mat', 'dispatch_bounds.mat', 'dispatch_priors.mat', 'dispatch_network.mat'};
input_files = struct('name', {}, 'sha256', {});
for k = 1:numel(mat_files)
    input_files(k) = struct('name', mat_files{k}, 'sha256', file_sha256(fullfile(artifact_folder, mat_files{k}))); %#ok<AGROW>
end
result.input_files = input_files;
result.loader_sha256 = file_sha256(which('npcc_nygrid_2025_full_dc'));
result.validation_code_sha256 = file_sha256([mfilename('fullpath'), '.m']);
writetable(array2table(checks, 'VariableNames', {'hour_index', 'branch_error_mw', ...
    'generation_change_mw', 'angle_error_deg', 'bound_violation_mw'}), fullfile(artifact_folder, 'matlab_checks.csv'));
fid = fopen(fullfile(artifact_folder, 'matlab_validation.json'), 'w');
assert(fid >= 0); cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(result, 'PrettyPrint', true));
disp(result);
end

function digest = file_sha256(path)
engine = java.security.MessageDigest.getInstance('SHA-256');
fid = fopen(path, 'rb');
assert(fid >= 0);
cleanup = onCleanup(@() fclose(fid));
while ~feof(fid)
    bytes = fread(fid, 1048576, '*uint8');
    if ~isempty(bytes), engine.update(typecast(bytes, 'int8')); end
end
raw = typecast(engine.digest(), 'uint8');
digest = lower(reshape(dec2hex(raw, 2)', 1, []));
end
