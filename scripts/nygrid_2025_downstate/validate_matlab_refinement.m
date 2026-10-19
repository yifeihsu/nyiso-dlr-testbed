function validate_matlab_refinement(artifact_folder)
% Independent MATPOWER checks across each topology state and seasonal hours.
root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
if nargin < 1, artifact_folder = fullfile(root, 'output', 'nygrid_2025_downstate'); end
addpath(fullfile(root, 'System Matpower Format'));
clear npcc_nygrid_2025_downstate_dc npcc_nygrid_2025_full_dc
baseline_folder = fullfile(root, 'output', 'nygrid_2025_dispatch', 'dispatch');
d = load(fullfile(baseline_folder, 'dispatch.mat'), 'timestamp_utc', 'dispatch_qualified', ...
    'gen_pg', 'dc_pf', 'bus_pd', 'bus_qd', 'reference_bus');
variants = {'expanded_identity', 'source_detail_2019', 'upgrades_year_end', ...
    'upgrades_dated', 'assets_year_end', 'assets_dated', 'nyes_assumption_year_end'};
qualified = logical(d.dispatch_qualified(:));
t = datetime(string(d.timestamp_utc), 'InputFormat', "yyyy-MM-dd'T'HH:mm:ss'Z'", 'TimeZone', 'UTC');
t.TimeZone = 'America/New_York';
calendar = [];
for mo = 1:12, calendar = [calendar; find(month(t) == mo & qualified, 1)]; end %#ok<AGROW>
good = find(qualified);
[~, peak] = max(sum(d.bus_pd(good, :), 2));
[~, valley] = min(sum(d.bus_pd(good, :), 2));
calendar = unique([calendar; good(peak); good(valley); find(month(t) == 11 & day(t) == 2 & hour(t) == 1 & qualified)]);
checks = table();
options = mpoption('model', 'DC', 'verbose', 0, 'out.all', 0);
receipts = struct('path', {}, 'sha256', {});
for v = 1:numel(variants)
    variant = variants{v};
    path = fullfile(artifact_folder, 'replay', [variant, '.mat']);
    p = load(path, 'qualified', 'network_state_ids', 'branch_pf', 'bus_va', 'interface_pf');
    states = unique(string(p.network_state_ids));
    selected = calendar;
    for s = states'
        ids = find(string(p.network_state_ids) == s & qualified);
        selected = [selected; ids(1); ids(end)]; %#ok<AGROW>
    end
    selected = unique(selected);
    for h = selected'
        m = npcc_nygrid_2025_downstate_dc(h, variant, artifact_folder);
        [r, ok] = rundcpf(m, options);
        assert(ok, 'Refined DC solve failed.');
        flow_error = max(abs(r.branch(:, 14) - p.branch_pf(h, :)'));
        angle_error = max(abs(r.bus(:, 9) - p.bus_va(h, :)'));
        pg_error = max(abs(r.gen(:, 2) - d.gen_pg(h, :)'));
        bound_error = max([0; r.gen(:, 10)-r.gen(:, 2); r.gen(:, 2)-r.gen(:, 9)]);
        interface = zeros(1, 7); keys = [1, 2, 3, 4, 5, 8, 10];
        for j = 1:7
            members = m.if.map(m.if.map(:, 1) == keys(j), 2);
            interface(j) = sum(sign(members) .* r.branch(abs(members), 14));
        end
        interface_error = max(abs(interface - p.interface_pf(h, :)));
        assert(max([flow_error, angle_error, pg_error, bound_error, interface_error]) < 1e-7, ...
            'Independent replay mismatch.');
        checks = [checks; table(string(variant), h, flow_error, angle_error, pg_error, bound_error, interface_error)]; %#ok<AGROW>
    end
    receipts(end+1) = struct('path', path, 'sha256', file_sha256(path)); %#ok<AGROW>
end
bad = find(~qualified, 1); rejected = false;
try
    npcc_nygrid_2025_downstate_dc(bad, 'assets_dated', artifact_folder);
catch err
    rejected = strcmp(err.identifier, 'nygrid2025:UnqualifiedHour');
end
assert(rejected, 'Missing-source hour was not rejected.');
checks.Properties.VariableNames = {'variant', 'hour_index', 'branch_error_model_mw', 'angle_error_deg', ...
    'generation_change_model_mw', 'bound_violation_model_mw', 'interface_error_model_mw'};
writetable(checks, fullfile(artifact_folder, 'validation', 'matlab_checks.csv'));
extra = {fullfile(artifact_folder, 'network', 'network_cases.mat'), ...
    fullfile(baseline_folder, 'dispatch.mat'), fullfile(baseline_folder, 'dispatch_bounds.mat'), ...
    which('npcc_nygrid_2025_downstate_dc'), [mfilename('fullpath'), '.m']};
for j = 1:numel(extra)
    receipts(end+1) = struct('path', extra{j}, 'sha256', file_sha256(extra{j})); %#ok<AGROW>
end
summary = struct('passed', true, 'fresh_MATPOWER_snapshots', height(checks), 'variants', {variants}, ...
    'maximum_branch_error_model_mw', max(checks.branch_error_model_mw), ...
    'maximum_generation_change_model_mw', max(checks.generation_change_model_mw), ...
    'maximum_bound_violation_model_mw', max(checks.bound_violation_model_mw), ...
    'maximum_interface_error_model_mw', max(checks.interface_error_model_mw), ...
    'missing_source_hour_rejected', rejected, 'matlab_version', version, 'dependencies', receipts);
fid = fopen(fullfile(artifact_folder, 'validation', 'matlab_validation.json'), 'w');
assert(fid >= 0); cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(summary, 'PrettyPrint', true));
disp(summary);
end

function digest = file_sha256(path)
engine = java.security.MessageDigest.getInstance('SHA-256');
fid = fopen(path, 'rb'); assert(fid >= 0); cleanup = onCleanup(@() fclose(fid));
while ~feof(fid)
    bytes = fread(fid, 1048576, '*uint8');
    if ~isempty(bytes), engine.update(typecast(bytes, 'int8')); end
end
raw = typecast(engine.digest(), 'uint8');
digest = lower(reshape(dec2hex(raw, 2)', 1, []));
end
