# 2019 Public-Target Retarget (Scaled Convention)

**Date:** 2026-07-20
**Change:** The six public calibration scenarios were moved from 2025 NYISO
hours to 2019 NYISO hours, and the model remains on the **scaled** convention
(total mapped NPCC-NY load fixed at 10,902.2197987 MW, per-hour
`gamma(t) = 10902.2197987 / NYISO_total_load(t)`). The raw-NYISO-scale S11
configuration is superseded for calibration purposes (see "Not rerun" below).

## Why

The structural network derives from the PERFORM 2019 On-Peak snapshot. Using
2025 public loads/flows asked a 2019 network to reproduce flows that ride on
post-2019 transmission upgrades (AC Transmission projects, Empire State Line,
Moses-Adirondack rebuild). Retargeting to 2019 hours makes target data and
network vintage contemporaneous and removes that confound.

## New scenarios (selected from 2019 P-58C / P-32 by the same criteria as the 2025 set)

| ID | Timestamp | Criterion | NYISO total (MW) | gamma |
|---|---|---|---:|---:|
| S1_2019_SUMMER_PEAK_PUBLIC | 2019-07-20 16:00 | July max total load | 30,396.9 | 0.358662 |
| S2_2019_WINTER_PEAK_PUBLIC | 2019-01-21 18:00 | January max total load | 24,727.6 | 0.440893 |
| S3_2019_SHOULDER_LIGHT_LOAD_PUBLIC | 2019-04-21 04:00 | April min total load | 11,951.1 | 0.912236 |
| S4_2019_HIGH_NYC_LI_LOAD_PUBLIC | 2019-07-17 16:00 | July max NYC+LI load (15,816.5 MW) | 29,319.7 | 0.371839 |
| S5_2019_HIGH_TOTAL_EAST_PUBLIC | 2019-07-17 08:00 | July max on-the-hour Total East (5,781.1 MW) | 24,338.6 | 0.447939 |
| S6_2019_LOW_TOTAL_EAST_PUBLIC | 2019-07-27 02:00 | July min on-the-hour Total East (2,206.4 MW) | 16,935.2 | 0.643761 |

S1 falls on NYISO's known 2019 annual peak day (2019-07-20), which is an
independent sanity check on the selection scan.

Note the S3 role changed in character: the 2019 minimum-load hour is an
overnight hour (04:00), while the 2025 minimum was a solar-suppressed Sunday
afternoon. Both are "shoulder light load," but their zonal share patterns
differ.

## What was changed and rerun

1. `nyiso_public_default_scenarios.m` - new 2019 IDs/timestamps/notes.
2. Scenario-ID references `S*_2025_*` renamed to `S*_2019_*` in:
   `run_s7_seven_interface_perform_tieline_calibration.m`,
   `run_s8_1_capability_feasibility_certificate.m`,
   `run_s9a_minimum_q_support_diagnostic.m`,
   `run_s9b_ac_feasibility_restoration.m`,
   `build_ny_voltage_reference_sets.m`,
   `diagnose_nyiso_public_voltage_locations.m`,
   `export_s8_winter_peak_handoff.m`, and the `'_2025_'` masks in
   `analyze_perform_reference.m`.
3. January/April/July 2019 P-58C and P-32 monthly archives downloaded from
   `https://mis.nyiso.com/public/csv/...` into `nyiso_public_cache/`.
4. Regenerated with the 2019 hours (scaled convention unchanged):
   `nyiso_public_scenarios.csv`, `ny_zonal_load_targets.csv`,
   `nyiso_public_interface_targets.csv`, `ny_external_interface_targets.csv`
   (58 rows), `nyiso_interface_objective_scales.csv`.
5. Reran the default handoff path (`run_handoff_reproduction`): S6 net-injection
   estimation + PFs and the S7 current-vs-direct-PERFORM tie validation. All
   built-in asserts passed (42 target rows, S6 6/6 standard PF, S7 12/12 PF,
   143/246/62 case dimensions).

The prior 2025-target CSVs are archived in
`archives/targets_2025_scaled_backup/`.

## Results with 2019 scaled targets (direct-PERFORM S7, frozen S6 dispatch)

| Metric | 2019 targets | Prior 2025 targets |
|---|---:|---:|
| Standard PF convergence | 6/6 | 6/6 |
| Q-limit-enforced PF convergence | **6/6** | 5/6 (shoulder failed) |
| Train objective (direct / current ties) | 0.29578 / 0.30034 | 0.12945 / 0.13566 |
| Holdout objective (direct / current ties) | 0.19383 / 0.19879 | 0.10385 / 0.14992 |
| All-hour objective (direct / current ties) | 0.48961 / 0.49914 | 0.23330 / 0.28558 |
| Worst interface residual | 888.6 MW (Total East proxy, shoulder) | 424.9 MW (Dunwoodie South) |
| Min voltage (standard PF) | 0.95272 pu | 0.90217 pu |
| Max voltage (standard PF) | 1.11002 pu | 1.11280 pu |
| Max branch overload | 341.0 MVA (Niagara W-Huntley, shoulder) | 168.1 MVA (same branch) |

Objectives are **not comparable across the two target sets**: the hours differ
and the fixed per-interface normalization scales were rebuilt from 2019 P-32
limits. Within the 2019 set, direct PERFORM ties remain better than the
current ties on train, holdout, and all-hour objectives, so the S7
direct-PERFORM recommendation stands.

Per-interface mean absolute residuals (direct PERFORM, six 2019 scenarios):

| Interface | MAE (MW) |
|---|---:|
| Dysinger East | 133.5 |
| West Central | 215.6 |
| Moses South | 53.7 |
| Central East | 110.1 |
| Total East proxy | 361.9 |
| UPNY-ConEd | 105.5 |
| Dunwoodie South | 276.6 |

Notable observations:

- The chronic 2025 shoulder Q-limit PF failure is gone: all six 2019 scenarios
  converge with Q limits enforced. The 2019 shoulder standard PF still shows
  one 253.5-MVAr generator Q violation, but enforcement now resolves it. This
  supports the vintage-mismatch hypothesis for part of the earlier
  voltage-control infeasibility.
- Residuals are almost uniformly negative (model underflows targets) with the
  frozen S6 dispatch; the dominant misses are winter Dysinger East/West Central
  (about -500 MW each) and shoulder Total East proxy (-888.6 MW). S8-style AC
  dispatch closure has not yet been rerun on these targets.
- Branch 29 Niagara West-Huntley overloads in all six scenarios (max 341 MVA,
  shoulder). The western-representation audit item from the handoff remains
  open under 2019 targets.

## Not rerun / now stale

- **S8, S8.1, S9a, and S9b result CSVs and assessments** still reflect the
  2025-target configuration. Their runner scripts have been re-pointed to the
  2019 IDs and can be refreshed via the corresponding
  `run_handoff_reproduction` options. S10a is a separate 2019 same-snapshot
  diagnostic and is not part of this stale group.
- **S11 DLR layer** (raw-NYISO-scale, 2025 summer peak) was deliberately left
  untouched: its scripts still reference `S*_2025_*` IDs and raw public
  targets, so it will not run against the regenerated target CSVs. Rebuilding
  the DLR operating layer on the scaled 2019 configuration is a separate step
  and should reuse the source-backed 2019 PG priors, which are now
  contemporaneous with the targets.
- `PROJECT_HANDOFF.md` retains its original 2026-07-12 handoff date but was
  updated on 2026-08-05 with the governing hierarchy, current 2019 results,
  the S13-FULL Phase 1A construction status, and the pending S14-NYISO role.
