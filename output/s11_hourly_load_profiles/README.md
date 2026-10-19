# S11 hourly bus load profiles

49 buses x 4,416 source hours (216,384 bus-hour pairs). Coverage is January, April, and July of 2019 and 2025. The six monthly segments are complete individually; intervening months and years are not filled or interpolated.

## Files

- `pd_mw.csv`: hourly constant-power active demand, MW; one column per bus.
- `qd_mvar.csv`: modeled signed constant-power reactive component, MVAr; one column per bus.
- `s11_hourly_load_profiles.mat`: `profile` struct; `pd_mw` and `qd_mvar` are 49 x 4416, with rows keyed by `bus_id`.
- `bus_allocation.csv`: bus names, zones, fixed allocation weights, baseline P/Q, and unchanged GS/BS.
- `zonal_pd_mw.csv`: the 11 raw NYISO zonal hourly inputs.
- `coverage.csv`: dates, counts, and statewide load range for each month.
- `source_manifest.csv`: the 184 local source CSVs and their record counts.
- `validation.json`: source, allocation, baseline-replay, and round-trip checks.
- `independent_validation.json`: saved results of the independent Python source-to-output check.
- `peak_pf_validation.json`: produced by the separate retained-peak AC integration check.

## Allocation and interpretation

For bus i in load-allocation zone z, w_i = saved_S11_Pd_i / sum(saved_S11_Pd in z), and Pd_i(t) = w_i * NYISO_zonal_load_z(t). Weights are frozen before processing any hour. Raw zonal MW are used, with no gamma scaling or normalization to a constant statewide total. All 49 buses are present; the 21 zero-Pd buses retain zero Pd/Qd, including transit buses 9001, 9002, and 9003.

Qd_i(t) = Pd_i(t) * saved_S11_Qd_i / saved_S11_Pd_i for positive-Pd buses. This preserves the saved case's signed constant-Q component. In this case only bus 80 has nonzero Qd, and its ratio is negative. This is not a measured hourly reactive-demand profile or an assumed 0.95/0.97 power factor. The case's GS/BS network-equivalent shunts are unchanged and excluded from the load arrays; their power depends on voltage.

Bus-level profiles are synthetic allocations of observed zonal demand, not independently measured substation loads. Every bus in a zone therefore has the same normalized active-load shape. The nominal case remains the retained 2025 S11 diagnostic benchmark. These data use the saved case directly and do not depend on the stale 2025 versus 2019 scenario IDs in the snapshot target tables.

Timestamps preserve the published NYISO hourly labels. UTC is derived using each source EST/EDT tag; local labels carry explicit -05:00/-04:00 offsets. No claim is made here about whether the provider's label denotes interval beginning or ending. These timestamps should not be silently relabeled when aligning weather, generation, or boundary schedules.

## Validation and operating scope

Source checks cover all 184 files, 48,576 zone-hour rows, and 4,416 unique hours. Maximum zonal P error is 1.82e-12 MW; maximum statewide P error is 7.28e-12 MW.

The source hour 2025-07-29T22:00:00Z reproduces saved S11 active loads within 3.19e-06 MW per bus (case serialization precision). CSV and MAT files were reloaded and compared.

This delivery validates the demand allocation. It does not establish AC feasibility for all 4,416 hours. Generation dispatch, external interchange schedules, voltage controls, and any shunt operating policy must be chosen consistently before chronological power-flow/OPF studies. The saved summer-peak dispatch must not be assumed suitable for every hour. S11 retains its reduced-model diagnostic role.

## MATLAB use

Run from the repository root:

```matlab
addpath('System Matpower Format', 'System Matpower Format/NY_Lite');
data = load('output/s11_hourly_load_profiles/s11_hourly_load_profiles.mat');
k = 1; % choose an entry in data.profile.timestamp_utc
mpc = npcc_ny_lite_s11_dlr_pf_base;
mpc = apply_s11_hourly_load_profile(mpc, data.profile, k);
% Set consistent hourly generation/boundary conditions before runpf/runopf.
```

Regenerate from the existing local source cache:

```matlab
addpath('scripts/s11_hourly_load_profiles');
build_s11_hourly_load_profiles;
test_apply_s11_hourly_load_profile;
validate_s11_hourly_load_profile_integration;
```

Independent source-to-output verification: `python scripts/s11_hourly_load_profiles/verify_s11_hourly_load_profiles.py` (NumPy and SciPy required).
