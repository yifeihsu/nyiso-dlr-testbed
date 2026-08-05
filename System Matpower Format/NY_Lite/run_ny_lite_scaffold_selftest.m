function report = run_ny_lite_scaffold_selftest
%RUN_NY_LITE_SCAFFOLD_SELFTEST Validate non-power-flow NY-lite safeguards.

case_dir = fileparts(fileparts(mfilename('fullpath')));
addpath(case_dir);
addpath(fileparts(mfilename('fullpath')));

mpc0 = npcc_ny_lite_v0_baseline;
[~, zones] = nyiso_bus_zone_map;
assert(zones(nyiso_zone_index('H')).perform_zone_code == 73, 'H code must be 73.');
assert(zones(nyiso_zone_index('I')).perform_zone_code == 72, 'I code must be 72.');

% S0 must preserve exact Pd and Qd.
[mpc1, load_report] = apply_nyiso_zonal_loads(mpc0, 'S0_NPCC_BASE', 1.0);
assert(max(abs(mpc1.bus(:, 3) - mpc0.bus(:, 3))) < 1e-8, ...
    'S0 load scenario changed baseline Pd.');
assert(max(abs(mpc1.bus(:, 4) - mpc0.bus(:, 4))) < 1e-8, ...
    'S0 load scenario changed baseline Qd.');

% Equivalent-generator helper must be idempotent.
[mpc2, eq_first] = add_ny_equivalent_generators(mpc0, [], ...
    struct('control_mode', 'fixed_pq', 'on_existing', 'skip'));
ngen = size(mpc2.gen, 1);
[mpc2b, eq_second] = add_ny_equivalent_generators(mpc2, [], ...
    struct('control_mode', 'fixed_pq', 'on_existing', 'skip'));
assert(size(mpc2b.gen, 1) == ngen, 'Equivalent generators were duplicated.');
assert(isempty(eq_second), 'Second equivalent-generator call should add nothing.');

% Core topology must add only Gilboa-Leeds and be idempotent.
[mpc3, tie_first] = add_ny_lite_tielines(mpc0, 'core');
assert(numel(tie_first) == 1 && strcmp(tie_first.name, 'GILBOA_LEEDS'), ...
    'Core profile must add only GILBOA_LEEDS.');
assert(abs(mpc3.branch(end, 3) - 0.00131) < 1e-12, 'Gilboa-Leeds R mismatch.');
assert(abs(mpc3.branch(end, 4) - 0.01997) < 1e-12, 'Gilboa-Leeds X mismatch.');
assert(abs(mpc3.branch(end, 5) - 0.51614) < 1e-12, 'Gilboa-Leeds B mismatch.');
assert(all(abs(mpc3.branch(end, 6:8) - [1216 2454 1804]) < 1e-12), ...
    'Gilboa-Leeds RATE_A/B/C mismatch.');
nb = size(mpc3.branch, 1);
[mpc3b, tie_second] = add_ny_lite_tielines(mpc3, 'core');
assert(size(mpc3b.branch, 1) == nb, 'Core tie was duplicated.');
assert(isempty(tie_second), 'Second core-tie call should add nothing.');

report = struct();
report.pass = true;
report.s0_total_mw = load_report.applied_total_mw;
report.equivalent_generators_added = numel(eq_first);
report.core_ties_added = numel(tie_first);
report.structural_fingerprint = ny_lite_case_fingerprint(mpc3);
report.operating_point_fingerprint = ny_lite_operating_point_fingerprint(mpc3);
end
