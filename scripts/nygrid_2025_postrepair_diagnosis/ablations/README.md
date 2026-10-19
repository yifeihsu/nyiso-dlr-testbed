# Controlled source-input ablations after the Moses repair

The fresh annual G and P runs both passed equation, loss-accounting and recovery
qualification on all **8,651** previously source-qualified hours, with zero
exceptions. Their completed independent checks pass direct branch laws, nodal
KCL, native/HQ/fixed-boundary PG, fixed DC inputs, regional targets, zonal load
accounting and loss ownership. All 8,760 clock rows remain, including the same
109 excluded hours. Neither run has a whole-network operating-qualified hour.

The experiment answers which *modeled input change* causes the observed error
movement. It does not establish real-system causality, physical P32 meter
equivalence, or observed hourly generator availability.

## Predeclared interventions

`scenario_recipe.json` was frozen before new annual solves or ablation scoring.
Its SHA-256 is
`5cd5db970ce86413532613d40ca7ebaed136335b59f264a2f00282d0f26760f8`.
The recipe reads source profiles and metadata, not P32 observations. Existing
model files, runtime code, source policies, source mask and prior annual results
remain unchanged.

| Scenario | Hydro input and native bounds | PV20 / ISO-NE routing |
| --- | --- | --- |
| B | Previous physical-repair hydro; unit 21 inactive | Previous ISO-NE pool; PV20 inactive |
| G | Corrected hydro plus monthly unit availability and bounds | Previous ISO-NE pool; PV20 inactive |
| P | Previous physical-repair hydro; unit 21 inactive | Current PV20 proxy plus offsetting ISO-NE pool change |
| GP | Corrected hydro plus monthly unit availability and bounds | Current PV20 proxy plus offsetting ISO-NE pool change |

G is one joint factor containing the hydro dispatch reconstruction, monthly
unit admission, and associated native bounds. These results do not separately
identify the effect of hourly shape, dispatch location, or bounds within G.
The 855 MW St. Lawrence bound is still an engineering nameplate assumption, not
an observed hourly available-capacity series.

All cases use the common 1,466-row generator axis and frozen current runtime.
Inactive extra rows 1465/1466 are retained explicitly at zero. `ablation_load.m`
reconstructs status, PV/ref bus types, Q limits, S capability, MBASE/VG, active
and reactive generator costs, capability references, and objective weights after
choosing PG and Pmin/Pmax. The fixed boundary row never provides voltage control
or external loss balancing. Source provenance remains attached to the diagnostic
cases, while `only_current_model=false` and the explicit scenario identify the
intervention.

B and GP were each solved at 12 monthly hours selected from maximum current
St. Lawrence source-input PG. All 24 comparisons reproduce their saved annual
complex voltages, branch P/Q, generator P/Q, capabilities and regional targets
**exactly**. The sample file also contains G/P inputs at those hours. A separate
Python reconstruction verifies all 48 sample input metadata/cost arrays with
maximum discrepancy **zero**. The fresh G and P annual runs cover all four
topology states.

## Results on the identical 8,651-hour cohort

The primary operator is the frozen `legacy_signed_literal_from` convention.
All seven interfaces and all three predeclared terminal conventions are
retained in the machine-readable metrics. Public MW uses one division by the
unchanged gamma.

| Interface | B MAE MW | G MAE MW | P MAE MW | GP MAE MW |
| --- | ---: | ---: | ---: | ---: |
| DYSINGER EAST | 259.493530 | 249.432036 | 259.494120 | 249.433183 |
| WEST CENTRAL | 256.547589 | 247.054750 | 256.541310 | 247.052572 |
| TOTAL EAST | 471.551177 | 465.320064 | 507.402104 | 499.304073 |
| MOSES SOUTH | 118.820924 | 141.586389 | 123.014514 | 108.944975 |
| CENTRAL EAST - VC | 230.424188 | 239.102675 | 202.844824 | 208.719124 |
| UPNY CONED | 235.206790 | 235.207528 | 235.206329 | 235.207068 |
| SPR/DUN-SOUTH | 177.241927 | 177.241927 | 177.241927 | 177.241927 |

For a metric `f`, the average marginal effects and interaction are:

```text
G Shapley effect = 0.5 * [(f(G) - f(B)) + (f(GP) - f(P))]
P Shapley effect = 0.5 * [(f(P) - f(B)) + (f(GP) - f(G))]
interaction     = f(GP) - f(G) - f(P) + f(B)
```

The two Shapley effects sum exactly to the combined change. Negative MAE effects
improve error; bias and prediction effects retain their signed meaning.

| Interface / metric | G Shapley effect | P Shapley effect | Interaction | Combined change |
| --- | ---: | ---: | ---: | ---: |
| Total East MAE, MW | -7.164572 | +34.917468 | -1.866918 | +27.752896 |
| Total East bias, MW | +17.420963 | -71.792482 | +0.005985 | -54.371520 |
| Moses South MAE, MW | +4.347963 | -14.223912 | -36.835004 | -9.875949 |
| Moses South bias, MW | +89.138072 | -77.442958 | +0.197917 | +11.695114 |

PV20 routing therefore drives the Total East MAE regression within this model;
the hydro change partially offsets it. The baseline Total East bias is already
negative, so the approximately -71.79 MW P contribution to mean prediction
deepens the underprediction. The same routing lowers Central East mean
prediction by about 61.29 MW, where the baseline bias is positive, improving that
interface's MAE.

Moses South requires both factors to describe the result. G alone raises MAE
from 118.82 to 141.59 MW; P alone raises it to 123.01 MW; GP lowers it to
108.94 MW. Its bias is +12.624497 MW in B, +101.663610 in G, -64.917420 in P,
and +24.319610 in GP. The large negative MAE interaction reflects cancellation
and the nonlinear absolute-error transformation. It is not comparably large
electrical nonlinearity: mean prediction interaction is only +0.197917 MW.
The hourly table preserves both prediction interaction and absolute-error
interaction so they cannot be conflated.

On the qualified cohort, G increases St. Lawrence input by an average
**89.24910 public MW**, offset by the same reduction in other HY generation.
Total native PG remains unchanged. P inserts mean **-75.988526 public MW** at
PV20 and offsets it by **+75.988526 MW** in the remaining ISO-NE pool. Every
regional net-import target remains unchanged. These are routing/dispatch
interventions, not changes to aggregate NY native generation or regional net
interchange.

## Validation and retained evidence

G completed in 356.990 s; P completed in 355.417 s, running concurrently. Each
producer authenticated its inputs and numerical code before/after the run.
Maximum independent branch-power discrepancy was below 4e-10 MVA and nodal
P/Q residual below 7e-9 MW / 1e-8 MVAr. Fixed boundary Q and six prescribed DC
P discrepancies were exactly zero. Regional target differences from B were
0 MW for G and below 2.8e-12 MW for P.

The output root is `output/nygrid_2025_postrepair_diagnosis/ablations/`:

- `scenario_recipe.json`, `source_axes.mat`: source-only intervention contract
  and fixed clock/cohort.
- `bridge_receipt.json`, `bridge_comparison.csv`, `bridge_samples.mat`: exact
  B/GP equivalence and independently checked input metadata for all scenarios.
- `G_v1/` and `P_v1/`: annual receipts, hour qualification tables, compact
  monthly numeric arrays, 12 detailed solved sample cases, full independent
  validation receipts, and hourly scenario PG-change ledgers.
- `factorial_metrics.csv`: B/G/P/GP annual, monthly and state metrics for all
  seven interfaces and three terminal conventions.
- `factorial_attribution.csv`: ordered marginal effects, average marginal
  effects, and interaction for MAE, signed bias, RMSE, WAPE and mean prediction.
- `factorial_arrays.npz`: all 8,760 rows, actual masks, observations and four
  scenario predictions; invalid rows are not promoted to predictions.
- `hourly_Moses_TotalEast_attribution.csv`: paired hour-level prediction and
  absolute-error effects for the two interfaces under investigation.
- `factorial_scoring_receipt.json`: hashes, qualification counts, cohort and
  decomposition checks.

Monthly numeric arrays retain both-terminal branch P/Q, full bus voltages and
net injections, generator PG, boundary Q, DC endpoints, shifts and accounting
budgets. They omit repeated full generator-Q/capability matrices; 12 detailed
samples plus independent source reconstruction check that metadata. The two
monthly-array sets together occupy about 470 MB rather than duplicating the
larger production annual export twice. All-hour nodal KCL and input PG/regional
constraints are independently checked from the retained arrays.

## Commands

Original commands, from the repository root:

```powershell
cd 'C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems'
$ablationPython = '.\tmp\nygrid_2025_inputs_runtime_20261010\Scripts\python.exe'
& $ablationPython scripts/nygrid_2025_postrepair_diagnosis/ablations/prepare_recipe.py
& 'C:\Program Files\MATLAB\R2026a\bin\matlab.exe' -batch "addpath('scripts/nygrid_2025_postrepair_diagnosis/ablations'); check_bridges();"
& 'C:\Program Files\MATLAB\R2026a\bin\matlab.exe' -batch "addpath('scripts/nygrid_2025_postrepair_diagnosis/ablations'); run_ablation('G');"
& 'C:\Program Files\MATLAB\R2026a\bin\matlab.exe' -batch "addpath('scripts/nygrid_2025_postrepair_diagnosis/ablations'); run_ablation('P');"
& $ablationPython scripts/nygrid_2025_postrepair_diagnosis/ablations/validate_ablation.py G
& $ablationPython scripts/nygrid_2025_postrepair_diagnosis/ablations/validate_ablation.py P
& $ablationPython scripts/nygrid_2025_postrepair_diagnosis/ablations/score_factorial.py
```

The annual producer refuses to overwrite an existing G/P run directory. Keep
this completed diagnostic version intact; a new solve version requires a new
output destination and its own frozen recipe. The final three Python commands
revalidate and rescore existing results without new PF. `--partial` validation
is explicitly intermediate and cannot satisfy the final scorer's completion
gate. MATLAB Code Analyzer reported one array-growth advisory in source-record
collection; the solves and final source-integrity checks completed successfully.
