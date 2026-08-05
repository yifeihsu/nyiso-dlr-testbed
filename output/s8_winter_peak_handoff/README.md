# NPCC-NY-Lite S8 Winter-Peak Handoff

## Purpose

This package contains the exact model layers used for the reported winter-peak
interface-flow result:

```text
S7 direct-PERFORM structural network
    -> NY-only boundary-equivalent reduction
    -> scaled NYISO winter zonal loads and external interchange
    -> S8 iterative AC zonal-injection closure
    -> standard AC power flow
```

The package is intentionally compact. The final cases are flattened, so the
full PERFORM and original project datasets are not required to rerun this PF.

## Requirements

- MATLAB
- MATPOWER 8.1 recommended
- MATPOWER available on the MATLAB path

## Reproduce

From MATLAB:

```matlab
cd '<extracted package directory>'
report = run_winter_peak_pf;
```

The script loads the authoritative full-metadata operating case, runs standard
PF and Q-limit-enforced PF, reconstructs all seven interfaces from the packaged
branch map, checks the flows against the archived solution, and writes results
to `rerun_results/`.

## Authoritative Cases

| Case | Size | Purpose |
|---|---:|---|
| `cases/npcc_ny_lite_s7_perform_direct_flat.mat` | 143 buses, 246 branches, 62 generators | Flattened S7 structural source |
| `cases/npcc_ny_lite_s8_winter_peak_operating_case.mat` | 49 buses, 81 branches, 43 generators | Authoritative unsolved S8 winter PF input |
| `cases/npcc_ny_lite_s8_winter_peak_pf_solution.mat` | 49 buses, 81 branches, 43 generators | Archived solved PF result |

Equivalent `.m` MATPOWER case files are included for inspection and use with
`loadcase`. The `.mat` operating case is authoritative because it retains the
complete metadata and full numerical precision.

## Expected Winter Result

```text
Scenario                         S2_2025_WINTER_PEAK_PUBLIC
Standard PF                      success
Q-limit-enforced PF              success
Seven-interface WAPE             0.458011%
Seven-interface MAPE             0.985081%
Maximum interface mismatch       25.109784 MW
All interfaces within 50 MW      yes
Interfaces within 25 MW          6 of 7
Minimum voltage                  0.952721 pu
Maximum voltage                  1.108457 pu
Voltage-bound violations         3
Branch overloads                 2
Maximum branch overload          94.216026 MVA
```

West Central is the limiting flow comparison: the scaled target is
559.985984 MW and the calculated PF flow is 534.876200 MW, a -25.109784 MW
or -4.484002% residual.

## Interpretation Boundary

The seven interface targets are used by the S8 estimator to infer zonal
generation. The close match is therefore an in-sample operating-point
consistency result, not independent validation of the transmission parameters.

The winter case is also not a certified secure operating point. Q-limit PF
converges, but the standard solution has three voltage-bound violations and two
branch overloads. Further tests should preserve this distinction:

```text
interface-flow consistency != complete AC operating feasibility
```

## Package Contents

- `cases/`: flattened S7 model, S8 operating input, and archived PF solution
- `data/`: scaled NYISO load/interface/interchange targets, branch measurement
  map, PERFORM GSK, and supported tie parameters
- `results/`: expected flows, dispatch, zonal generation, external interchange,
  and feasibility diagnostics
- `CASE_INVENTORY.csv`: model roles, dimensions, and authoritative input
- `SOURCE_PROVENANCE.csv`: origin and caveat for each modeling input
- `FULL_PROJECT_HANDOFF.md` and `FULL_PROJECT_LATEST_MODEL_CONFIGURATION.csv`:
  broader construction history and current project status
- `source_reference/`: exporter and S8 estimator source for audit; these source
  files require the full project dependency tree and are not needed by the
  standalone PF runner
- `PACKAGE_MANIFEST.csv`: file sizes and SHA-256 hashes
- `PACKAGE_CONTENT_ROOT.sha256`: canonical package payload checksum

## Recommended Colleague Tests

1. Rerun `run_winter_peak_pf.m` unchanged and confirm the archived flows.
2. Identify the three voltage violations and two overloaded branches.
3. Test Q limits, taps, shunts, and boundary-Q assumptions independently.
4. Perturb zonal generation without reusing all seven targets and evaluate
   out-of-sample interface behavior.
5. Do not recalibrate tie impedances until measurement operators and control
   assumptions are audited.
