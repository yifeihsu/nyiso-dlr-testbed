# S11 49-bus hourly load profiles - handoff

This package contains hourly active-load profiles and modeled reactive-load
profiles for every bus in the retained S11 reduced diagnostic model.

## Start here

Extract the ZIP and open its `S11_49bus_hourly_load_profiles` folder. The ready-to-use
data are in `output/s11_hourly_load_profiles/`:

| File | Contents |
|---|---|
| `pd_mw.csv` | 4,416 hourly rows; UTC/local timestamps, source timezone, then 49 `bus_ID` columns of MW |
| `qd_mvar.csv` | Same layout; modeled signed constant-power reactive component in MVAr |
| `s11_hourly_load_profiles.mat` | MATLAB `profile` struct; `pd_mw` and `qd_mvar` are **49 buses x 4,416 hours** |
| `bus_allocation.csv` | Bus names, zones, allocation weights, baseline P/Q, and fixed GS/BS |
| `coverage.csv` | Coverage and statewide demand range for each month |
| `zonal_pd_mw.csv` | The 11 original zonal hourly input series |
| `README.md` | Detailed allocation methodology and usage |
| `validation.json`, `independent_validation.json` | Allocation and source reconciliation results |
| `peak_pf_validation.json` | Single retained-peak AC power-flow integration result |
| `source_manifest.csv` | Paths and record counts for all 184 included source files |

CSV files can be read without MATLAB or this repository. Use the actual bus IDs;
they are **37-82, 9001, 9002, and 9003**, not consecutive IDs 1-49. MATLAB arrays
use the order in `profile.bus_id`. Both UTC and local timestamps are included.

## Coverage and assumptions

- January, April, and July of **2019 and 2025**: 4,416 hours and 216,384 bus-hour pairs.
  Each of the six monthly segments is complete. This is not two complete years;
  missing months and the intervening years have not been interpolated.
- Source data: 184 cached NYISO `palIntegrated` daily files, included under
  `System Matpower Format/NY_Lite/nyiso_public_cache/`.
- Each zonal hourly MW total is distributed using fixed saved-S11 load shares.
  These are synthetic bus allocations of observed zonal demand. All 49 buses
  are present; 28 carry active demand and 21 remain zero.
- Qd follows the saved case's signed constant-power Q/P ratios. Only bus 80 has
  nonzero Qd, with a negative ratio. It is not measured hourly reactive demand.
  Network GS/BS shunts remain unchanged and are excluded from the load arrays.
- Source EST/EDT labels are retained, with explicit local UTC offsets. The
  provider's labels have not been reinterpreted as interval beginning or ending.
- All source and allocation checks passed. The retained **2025-07-29 18:00 EDT**
  peak reproduces the saved case and passes standard and Q-limit-enforced AC PF.
  AC feasibility for the other hours has not been established. Set consistent
  generation dispatch, external schedules, and controls before running them.

## MATLAB quick start

From the extracted package root:

```matlab
addpath('System Matpower Format', 'System Matpower Format/NY_Lite');
data = load('output/s11_hourly_load_profiles/s11_hourly_load_profiles.mat');
k = 1;  % column index; select using data.profile.timestamp_utc
mpc = npcc_ny_lite_s11_dlr_pf_base;
[mpc, hour] = apply_s11_hourly_load_profile(mpc, data.profile, k);
disp(hour);
```

Loading and applying the data do not require MATPOWER. The helper changes only
Pd/Qd and matches buses by ID, so reordered case rows are supported. Reading,
applying, and rebuilding were tested with MATLAB R2026a. Other versions were
not tested. AC PF validation additionally requires MATPOWER on the MATLAB path;
MATLAB and MATPOWER themselves are not bundled.

## Verify or reproduce

The original relative folder layout is retained so these commands work from
the extracted package root, independently of the original checkout.

Independent source-to-output check (Python with NumPy and SciPy):

```text
python scripts/s11_hourly_load_profiles/verify_s11_hourly_load_profiles.py
```

Rebuild and check bus-ID application in MATLAB:

```matlab
addpath('scripts/s11_hourly_load_profiles');
build_s11_hourly_load_profiles;
test_apply_s11_hourly_load_profile;
```

Optional retained-peak AC replay with MATPOWER installed:

```matlab
validate_s11_hourly_load_profile_integration;
```

The saved validation JSON files describe the delivered dataset. If you rebuild,
rerun the independent Python check and any required AC replay. The Python check
prints its new results to the terminal; it does not overwrite the saved JSON.

`PACKAGE_MANIFEST.json` identifies the source dataset commit and inventory.
`PACKAGE_CONTENTS.csv` lists the included payload files. All data needed to read,
apply, regenerate, and independently reconcile these profiles are included.
No repository clone or source download is required for those operations.
