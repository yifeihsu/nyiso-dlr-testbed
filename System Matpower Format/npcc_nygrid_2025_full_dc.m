function mpc = npcc_nygrid_2025_full_dc(hour_index, artifact_folder)
%NPCC_NYGRID_2025_FULL_DC Capacity-bounded 2025 DC snapshot on full2019 NPCC.
% The 140 buses, 225 AC branches and four DC endpoints retain the modified
% 2019 topology. Native generators use the2025 EIA fleet and source priors.
% Missing-source or infeasible hours are rejected, never silently substituted.
% Pmin=0 is an hourly-average/off-on relaxation. AC, minimum-stable loading,
% commitment, ramping, branch thermal limits and storage energy are unverified.
if nargin < 1, hour_index = 1; end
assert(isnumeric(hour_index) && isscalar(hour_index) && isfinite(hour_index) ...
    && hour_index == fix(hour_index) && hour_index >= 1 && hour_index <= 8760, ...
    'nygrid2025:HourIndex', 'Use an integer physical-hour index from 1 through 8760.');
root = fileparts(fileparts(mfilename('fullpath')));
if nargin < 2 || isempty(artifact_folder)
    artifact_folder = fullfile(root, 'output', 'nygrid_2025_dispatch', 'dispatch');
end
main_file = fullfile(artifact_folder, 'dispatch.mat');
bounds_file = fullfile(artifact_folder, 'dispatch_bounds.mat');
assert(isfile(main_file) && isfile(bounds_file), 'nygrid2025:MissingDispatch', ...
    'Build the2025 fleet, priors and bounded dispatch first.');
persistent cached_folder cached_signature d bounds
files = [dir(main_file); dir(bounds_file)];
signature = [[files.bytes], [files.datenum]];
if isempty(d) || ~strcmp(cached_folder, artifact_folder) || ~isequal(cached_signature, signature)
    d = load(main_file, 'hour_index', 'timestamp_utc', 'base_case', 'bus_pd', 'bus_qd', ...
        'gen_pg', 'dc_pf', 'dispatch_qualified', 'status_code', 'reference_bus', 'gamma', 'native_fleet_ids');
    bounds = load(bounds_file, 'hour_index', 'native_fleet_ids', 'gen_pmin', 'gen_pmax');
    assert(isequal(d.hour_index(:), (1:8760)') && isequal(bounds.hour_index(:), d.hour_index(:)) ...
        && isequal(bounds.native_fleet_ids(:), d.native_fleet_ids(:)), ...
        'nygrid2025:Coverage', 'Saved time/fleet axes disagree.');
    cached_folder = artifact_folder;
    cached_signature = signature;
end
assert(logical(d.dispatch_qualified(hour_index)), 'nygrid2025:UnqualifiedHour', ...
    'Hour %d has status_code %d; inspect hour_status.csv. No replacement hour was selected.', ...
    hour_index, d.status_code(hour_index));
mpc = d.base_case;
mpc.baseMVA = double(mpc.baseMVA);
mpc.genfuel = mpc.genfuel(:);
mpc.bus(:, 3) = d.bus_pd(hour_index, :)';
mpc.bus(:, 4) = d.bus_qd(hour_index, :)';
mpc.bus(:, 9) = 0; % Independent DC solve; saved bus angles are not inputs.
mpc.gen(:, 2) = d.gen_pg(hour_index, :)';
mpc.gen(:, 3:5) = 0; % No physical reactive capability is asserted by this DC case.
mpc.gen(:, 9) = bounds.gen_pmax(hour_index, :)';
mpc.gen(:, 10) = bounds.gen_pmin(hour_index, :)';
mpc.gen(:, 8) = (mpc.gen(:, 9) > 0) | (mpc.gen(:, 10) < 0);
mpc.bus(:, 2) = 1;
mpc.bus(ismember(mpc.bus(:, 1), mpc.gen(mpc.gen(:, 8) == 1, 1)), 2) = 2;
ref = double(d.reference_bus(hour_index));
assert(any(mpc.gen(:, 1) == ref & mpc.gen(:, 8) == 1), ...
    'nygrid2025:Reference', 'The angle-reference bus has no admitted generator.');
mpc.bus(mpc.bus(:, 1) == ref, 2) = 3;
mpc.dcline(:, 4) = d.dc_pf(hour_index, :)';
mpc.dcline(:, 5) = mpc.dcline(:, 4); % PT has the same orientation as PF.
mpc.dcline(:, 6:7) = 0;
mpc.dcline(:, 10:11) = repmat(mpc.dcline(:, 4), 1, 2);
mpc.dcline(:, 12:15) = 0;
assert(all(isfinite(mpc.gen), 'all') && all(isfinite(mpc.bus), 'all'), ...
    'nygrid2025:Finite', 'Unqualified values reached the case loader.');
mpc = toggle_dcline(mpc, 'on');
mpc.userdata.nygrid2025 = struct('model_year', 2025, 'hour_index', hour_index, ...
    'timestamp_utc', string(d.timestamp_utc{hour_index}), 'scale_factor_gamma', d.gamma, ...
    'parent', 'modified2019_full_NPCC', 'topology_modified', false, 'dc_only', true, ...
    'active_power_bounds_enforced', true, 'fixed_external_schedule_equivalents', true, ...
    'free_slack_generation_allowed', false, 'hourly_pmin_zero_relaxation', true, ...
    'ac_feasibility_validated', false, 'reactive_capabilities_available', false, ...
    'unit_commitment_validated', false, 'ramping_validated', false, ...
    'physical_branch_thermal_feasibility_validated', false, ...
    'storage_energy_feasibility_validated', false, 'economic_costs_available', false, ...
    'internal_interface_observations_used_in_dispatch', false);
end
