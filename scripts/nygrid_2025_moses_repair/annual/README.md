# Moses South generation and boundary repair: annual replay

The completed `moses_repair_v1` replay retains all 8,760 clock rows and the
previous source mask. All 8,651 source-qualified hours converge and pass the AC
equation, loss-allocation, and voltage/current recovery gates. The 109 excluded
hours remain excluded. There are no newly qualified or lost baseline hours and
no solver exceptions. MATLAB replay time was 328.715 s.

This is an equation-qualified model, with **zero hours passing all operating
limits**. Do not interpret successful numerical validation as system-wide
voltage, generator capability, or thermal feasibility.

## Frozen inputs and baseline

The baseline is the previous **physical-repair** delivery and its completed
`physical_repair_v1` annual results. Its 8,651 candidate-qualified hours become
the baseline cohort here. The older 8,170-hour pre-repair baseline is not the
comparison cohort for this repair.

`prepare_annual_contract.py` makes hash-checked executable snapshots of the
baseline and compiled candidate. It freezes the clock, source mask, gamma,
interface definitions, comparison arrays, and model/runtime files in
`output/nygrid_2025_moses_repair/annual/`. Existing different snapshots cannot be
overwritten. The annual producer loads the compiled candidate directly; it does
not reapply earlier branch or reactor changes.

The candidate has 1,466 generator rows: the original 1,464 row identities,
appended native St. Lawrence unit 21 at row 1,465, and a fixed-P/fixed-Q external
PV20 boundary injection at row 1,466. There are still six existing fixed-transfer
records. The PV20 record is not an additional DC line and does not create PV-bus
voltage control, native generation, a reserve resource, or an external loss
balancer. It has fixed Q = 0, Pmin = Pmax = its source-defined P, zero loss share,
and assumed S capability = abs(P). Its external region is ISONE (12).

The generation candidate enforces St. Lawrence monthly EIA energy on the full
calendar, with 15 operating units each month drawn from 16 source unit records.
The 57 MW per operating unit bound is an engineering nameplate assumption, not
measured hourly availability. Qualified-hour total native PG, reconciled NY HY
generation, other native fuels, HQ, load profiles, existing DC targets, and
regional net-import targets are preserved. Other ISONE generation is adjusted
oppositely to the explicit PV20 injection, preventing double counting of the
same regional interchange.

The full-calendar energy calculation uses explicitly documented latent values
for excluded hours; it does not promote them to source-qualified PF hours. The
independent generation review reports the excluded-hour energy sensitivity.
The preserved HY series is the **existing reconciled** series, which is not
identical to the raw P63 Hydro observations.

PV20 uses Sand Bar P34 as the boundary proxy with positive injection into NY.
The source review establishes the current diagram's direction but does not
establish the historical 2025 effective date of that diagram. South Hero load
and intervening losses also prevent treating the Sand Bar meter as a certified
physical PV20 terminal meter. These remain declared source/model assumptions.
The physical membership of the P32 interface meters and the interpretation of
their numeric header as MW remain uncertified.

## Independent validation

`check_candidate_readiness.m` passed 31 source-selected hours covering all four
topology states, including monthly St. Lawrence input peaks and PV20 source
extremes. No P32 errors were used to select these hours. On hour 90, compact and
detailed solves agreed within 4.42e-14 pu in complex voltage and 7.67e-11 MVA in
branch complex power. MATLAB Code Analyzer found no producer issues.

After the annual producer finished and verified its source hashes, two Python
readers independently checked every saved qualified hour without running PF:

- `validate_annual.py` reconstructs source/profile preservation, finite P/Q/S
  metadata, fixed boundary P/Q, loss ownership, external balancing increments,
  regional imports, zonal load accounting, equipment limits, and current units.
  Maximum compiled-input change from the preserved baseline constraints was
  3.01e-11 MW; maximum regional target change was 2.73e-12 MW. The boundary P/Q
  deviation was exactly zero.
- `../validation/review_annual_physics.py` reconstructs both-terminal complex
  branch power and currents from saved voltage, branch parameters, taps and
  shifts; checks nodal complex-power balance including boundary and DC records;
  rebuilds the passive-node voltage lift; and checks material I-squared-R loss.
  Maximum branch power difference was 2.79e-10 MVA, terminal current difference
  1.45e-9 A, nodal P/Q residual 6.74e-9 MW / 1.01e-8 MVAr, and full-voltage lift
  difference 7.03e-14 pu.

The readers verify preservation of parent 41 R/X/B and its thermal realization,
parent 185/195 branch parameters, and the existing full-bus-axis fixed-reactor
placement. No prior physical repair is undone or added a second time. Parents
185 and 195 remain within their voltage limits in all 8,651 qualified hours:

| Target | Minimum voltage (pu) | Maximum voltage (pu) | Violation hours |
| --- | ---: | ---: | ---: |
| 185 | 1.020000 | 1.039389 | 0 |
| 195 | 1.006566 | 1.046987 | 0 |

Remaining global limits are reported explicitly: overvoltage in 8,651 hours,
undervoltage in 599, generator Q and assumed-S violations in 8,651, and branch
MVA violations in 4,793. Global voltage range is 0.841226–1.076098 pu. Parent 41
still exceeds its declared hardware-current limit in 2,712 hours. Its mean
model MW loss changes from 2.364978 to 2.356207 because the dispatch changes;
the physical parameters remain fixed.

## Public-interface comparison

The primary comparison uses the same 8,651 paired hours, unchanged observed
values, frozen gamma, and the predeclared `legacy_signed_literal_from`
convention. Public predictions are aggregated model MW divided by gamma once.
Saved physical amperes are never divided by gamma. The scorer also preserves
the other two declared terminal conventions and annual/monthly/state cohorts;
it does not choose a convention by fit. `crosscheck_scoring.py` independently
matched 28 metric rows against the raw-physics reader, with zero MAE/RMSE/bias
and WAPE discrepancy.

| Interface | Previous MAE (public MW) | Candidate MAE (public MW) | Previous WAPE (%) | Candidate WAPE (%) | Previous bias (MW) | Candidate bias (MW) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DYSINGER EAST | 259.494 | 249.433 | 30.941 | 29.742 | -5.681 | -68.489 |
| WEST CENTRAL | 256.548 | 247.053 | 46.067 | 44.362 | -8.859 | -71.926 |
| TOTAL EAST | 471.551 | 499.304 | 15.063 | 15.949 | -285.786 | -340.157 |
| MOSES SOUTH | 118.821 | 108.945 | 22.008 | 20.178 | 12.624 | 24.320 |
| CENTRAL EAST - VC | 230.424 | 208.719 | 13.849 | 12.545 | 158.034 | 112.615 |
| UPNY CONED | 235.207 | 235.207 | 7.844 | 7.844 | -35.765 | -35.743 |
| SPR/DUN-SOUTH | 177.242 | 177.242 | 9.592 | 9.592 | -75.480 | -75.480 |

Moses South MAE improves about 8.31%, while positive bias increases. Total East
MAE worsens about 5.89%. The result is therefore not an across-interface
improvement. UPNY MAE differs by only +0.000278 MW, and SPR MAE is unchanged to
the displayed precision.

## Reproduction

Run from this repository root in PowerShell. The Python environment needs
NumPy, SciPy and pandas. The recorded run used MATLAB R2026a Update 3 and
MATPOWER 8.1. The candidate model and its passing receipt must already exist.

```powershell
cd 'C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems'
$mosesPython = '.\tmp\nygrid_2025_inputs_runtime_20261010\Scripts\python.exe'
& $mosesPython scripts/nygrid_2025_moses_repair/annual/prepare_annual_contract.py --candidate-model-dir output/nygrid_2025_moses_repair/model --candidate-runtime-dir scripts/nygrid_2025_moses_repair/delivery/runtime --candidate-receipt output/nygrid_2025_moses_repair/candidate_receipt.json
& 'C:\Program Files\MATLAB\R2026a\bin\matlab.exe' -batch "addpath('scripts/nygrid_2025_moses_repair/annual'); check_candidate_readiness();"
& 'C:\Program Files\MATLAB\R2026a\bin\matlab.exe' -batch "addpath('scripts/nygrid_2025_moses_repair/annual'); issues=checkcode('scripts/nygrid_2025_moses_repair/annual/run_moses_annual.m','-id'); assert(isempty(issues)); run_moses_annual('moses_repair_reproduction',false);"
$mosesRun = 'output/nygrid_2025_moses_repair/annual/moses_repair_reproduction'
& $mosesPython scripts/nygrid_2025_moses_repair/annual/validate_annual.py --run-dir $mosesRun
& $mosesPython scripts/nygrid_2025_moses_repair/validation/review_annual_physics.py --run-dir $mosesRun
& $mosesPython scripts/nygrid_2025_moses_repair/annual/score_annual.py --run-dir $mosesRun
& $mosesPython scripts/nygrid_2025_moses_repair/annual/crosscheck_scoring.py --run-dir $mosesRun
```

Use a new run label for a fresh solve. `resume=true` authenticates and reuses
only completed monthly checkpoints from an identical frozen run. It refuses
changed sources and preserves incomplete monthly artifacts for inspection.
To inspect the completed run without new PF, set `$mosesRun` to the existing
`output/nygrid_2025_moses_repair/annual/moses_repair_v1` and run the two readers,
scorer, and crosscheck only.

The primary completed evidence is under that run directory:
`annual_receipt.json`, `annual_hour_quality.csv`, `annual_axes.mat`,
`annual_network.mat`, the 12 `monthly/profile_PF_2025_MM.mat` files,
`validation/annual_input_accounting_review.json`,
`validation/annual_physics_review.json`,
`comparison/public_interface_metrics.csv`,
`comparison/comparison_arrays.npz`, `comparison/scoring_receipt.json`, and
`comparison/independent_scoring_crosscheck.json`. Earlier partial-reader outputs
remain explicitly prefixed `partial_` and are not the completion evidence.

Generation evidence is in
`output/nygrid_2025_moses_repair/generation/independent_generation_review.json`
and `excluded_hour_energy_sensitivity.csv`. The separate delivery documentation
contains the current source qualifications and runnable user-facing model API.
