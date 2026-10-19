function validate_matlab_inputs(artifact_folder)
% Check MATLAB interoperability and the inputs-only contract, not a PF solve.
root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
if nargin < 1
    artifact_folder = fullfile(root, 'output', 'nygrid_2025_inputs', 'model');
end
addpath(fullfile(root, 'System Matpower Format'));
d = load(fullfile(artifact_folder, 'operating_inputs.mat'), ...
    'timestamp_utc', 'zonal_load_model_mw', 'boundary_hour_qualified');
t = datetime(string(d.timestamp_utc), 'InputFormat', "yyyy-MM-dd'T'HH:mm:ss'Z'", 'TimeZone', 'UTC');
assert(numel(t) == 8760 && all(diff(t) == hours(1)), 'UTC coverage failed.');
local = t;
local.TimeZone = 'America/New_York';
assert(all(year(local) == 2025), 'Civil year differs from UTC input axis.');
fall = find(month(local) == 11 & day(local) == 2 & hour(local) == 1);
assert(numel(fall) == 2 && diff(t(fall)) == hours(1), 'Fall fold was lost.');
[peak, peak_index] = max(sum(d.zonal_load_model_mw, 2));
gap = find(~d.boundary_hour_qualified, 1);
indices = unique([1; 8760; peak_index; fall; gap]);
for h = indices'
    s = npcc_nygrid_2025_operating_inputs(h, artifact_folder);
    assert(numel(s.gross_pd_mw) == 140 && numel(s.gross_qd_mvar) == 140);
    assert(numel(s.external_generator_input_mw) == 271);
    assert(all(size(s.zonal_generation_prior_model_mw) == [11, 5]));
    assert(abs(sum(s.gross_pd_mw(37:82)) - sum(s.zonal_load_model_mw)) < 1e-8);
    assert(~s.ready_for_dc_power_flow && ~s.ny_generation_dispatch_available);
    assert(~isfield(s, 'bus') && ~isfield(s, 'gen') && ~isfield(s, 'branch'));
    assert(all(isnan(s.external_generator_input_mw(1:243))), 'Native dispatch must remain unset.');
end
assert(abs(peak - 9561) < 1e-8, 'Wrong source-matched benchmark anchor.');
result = struct('passed', true, 'matlab_version', version, 'physical_hours', numel(t), ...
    'accessor_hours_checked', indices, 'fall_fold_preserved', true, 'benchmark_peak_mw', peak, ...
    'input_accessor_only', true, 'power_flow_tested', false);
fid = fopen(fullfile(artifact_folder, 'matlab_accessor_validation.json'), 'w');
assert(fid >= 0);
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(result, 'PrettyPrint', true));
disp(result);
end
