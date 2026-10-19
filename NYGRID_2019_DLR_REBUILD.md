# Full 2019 NYgrid/NPCC reconstruction and first DC DLR scenarios

**Verified 2026-10-07.** The new `npcc_nygrid_2019_full_dc` loader provides an
unreduced, paper-derived 2019 research network with **140 buses, 225 AC branch
records, 271 generator records, and four controllable DC-link records**. A
complete **8,760-hour** baseline and a first synthetic thermal exposure screen
are saved under [output/nygrid_2019_full_stage1](output/nygrid_2019_full_stage1).
The model is usable for the requested **DC research scenarios with explicit
conductor/weather assumptions**. AC feasibility, installed-line thermal ratings,
and economic redispatch benefits are not established.

The paper is Liu et al., *An Open Source Representation for the NYS Electric
Grid to Support Power Grid and Market Transition Studies*, IEEE TPWRS 38(4),
2023, [DOI 10.1109/TPWRS.2022.3200887](https://doi.org/10.1109/TPWRS.2022.3200887).
The model/data year is 2019. The attached PDF was reviewed, including Sections
III-V and the network-modeling figures. Its author release is
[NYgrid commit 47698b6c7823ae7b1bc6935e5601d5b64b8f918e](https://github.com/AndersonEnergyLab-Cornell/NYgrid/tree/47698b6c7823ae7b1bc6935e5601d5b64b8f918e).

## What the paper and actual download contain

| Construction stage | Buses | AC branches | Generators | DC records |
|---|---:|---:|---:|---:|
| Downloaded `Data/npcc.mat` | 140 | 227 | 48 | 0 |
| Released `modifyMPC()` base | 140 | 226 | 48 | 0 |
| Released full hourly case immediately before reduction | 140 | 226 | 271 | 0 |
| Released reduced case before DC-device changes | 57 | 95 | 271 | 0 |
| Released final model validated in the earlier annual reproduction | 57 | 94 | 271 | 4 |
| New derived full model with the same final-device changes | 140 | 225 | 271 | 4 |

The paper describes an original **233-branch** NPCC network, while its pinned
download contains **227**. This source-version discrepancy remains unresolved.
No missing branches were invented or substituted from the separate ENLITEN
case. The released builder removes three remote ties and adds the 38-77 and
43-38 aggregate paths: `227 - 3 + 2 = 226`. The later device changes delete the
81-125 AC row and add four DC-link records: `226 - 1 = 225`, plus four DC records.
One of those records represents the VFT through the authors' controllable-link
abstraction; four DC records do not imply four separately identified HVDC assets.
See the [source discrepancy](output/nygrid_2019_full_stage1/paper_source_discrepancy.json)
and [complete branch lineage](output/nygrid_2019_full_stage1/source_branch_lineage.csv).

The source constructor also changes load signs and voltage-control bus types,
moves the reference bus to 74, updates external tie limits, allocates 2019 NY
generation/demand, scales external demand/generation, and adds an HQ injection
at bus 48. It then performs a DC-oriented external reduction. The paper
explicitly limits its validation to DC studies because reactive data are
insufficient; the reduction toolbox likewise declares a DC scope.

## Reproduction and validation evidence

The downloaded source is unchanged. A separate instrumented execution copy
adds two outputs around `MPReduction`; reversing those additions reproduces
the original cached source byte-for-byte. Preparation verifies 73 upstream
files, 73 cached files, and 20 pinned reduction-toolbox files.

Fresh MATLAB execution captured the first hour of all 12 months plus July 20
at 17:00. All 13 released final states exactly matched the saved annual demand,
input generation, DC schedules, branch flows, solved generation, and angles.
The annual reconstruction independently allocates load from the released CSVs
and replays all hours with a separate NumPy/SciPy nodal solver. It reuses the
previously verified annual generation-allocation evidence; it is not a fresh
annual extraction from RGGI or independently observed generator telemetry.

The reduction code overwrites generation with the full-system solved output.
The reconstruction therefore restores the original first bus-74 generator
input from the daily Indian Point 2 series before solving the full case.
Leaving the already-balanced value as the original prior would misstate the
source operation.

| Fresh check | Result |
|---|---:|
| Annual prepared hourly states | 8,760 / 8,760 |
| Reconstructed NY active demand versus saved release | maximum 7.00e-11 MW |
| Full solved generation versus release's preserved full-PF output | maximum 1.08e-10 MW |
| Full annual final-device nodal residual | maximum 2.24e-11 MW |
| Fresh MATLAB loader flow versus independent full solver, 13 hours | maximum 4.14e-11 MW |
| MATLAB loader invalid-hour guards | 8 passed |
| Thermal physics/integration checks | 12 passed, including a 21-case independent fixture |

Evidence: [annual summary](output/nygrid_2019_full_stage1/full_year_summary.json),
[source capture checks](output/nygrid_2019_full_stage1/full_year_capture_checks.csv),
[fresh loader verification](output/nygrid_2019_full_stage1/full_loader_validation.json),
and [thermal checks](output/nygrid_2019_full_stage1/synthetic_thermal_tests.csv).
The documented separate-folder rebuild also completed successfully: all 14
compared annual numerical arrays were exactly equal to the delivered baseline,
and four thermal evidence CSVs were byte-identical. The
[rebuild receipt](output/nygrid_2019_full_stage1/clean_rebuild_verification.json)
records that check without replacing the delivered numerical artifacts.

### A measured difference from the reduced model

The derived full model is **not exactly equivalent** to the released final
57-bus model. Across the year, the maximum retained-branch difference is
**3.69482 MW**, the maximum seven-interface difference is **1.74792 MW**, and
the RMS interface difference is **0.23792 MW**. These differences remain in
the saved results; no tolerance was widened or network parameter fitted to
hide them.

The reason is traceable to the reduction implementation. It includes bus and
line-charging susceptance in its elimination matrix, although MATPOWER DC
power flow ignores those terms. Load redistribution restores the original
operating point, but the subsequent DC-device changes excite slightly
different network responses. The reduced off-diagonal matrix matches the
shunt-augmented elimination to 2.73e-12 MW/rad. Before the device changes,
the 13 captured full/reduced operating points agree to numerical tolerance.

Against the same seven NYISO interface series, full-network pooled WAPE is
**11.21722%**, versus **11.21808%** for the corrected reduced release. This
negligible difference is not evidence of improved predictive accuracy. Pooled
WAPE combines overlapping interfaces and is not a statewide power-balance
error. The inherited paper-metric caveats and five stale plotting indices are
documented in [the original interface verification](NYGRID_2019_INTERFACE_VERIFICATION.md).
The new model uses keyed interface mappings, not the stale plotting formulas.

The source's 8,760 naive local-hour labels are retained, including its spring
interpolation and repeated-fall-hour averaging. External loads are scaled
from NY demand rather than independently observed external demand. NY QD
uses the source's assumed 0.98 power factor; external QD stays inherited.
Many generator reactive bounds are +/-9999 MVAr placeholders. Neither those
fields nor a successful DC solve establishes bounded AC operation.

## First DLR research scenarios

The [branch register](output/nygrid_2019_full_stage1/branch_register.csv) covers
all 225 AC and four DC records. It identifies **39 structural candidates**:
15 at 115 kV, ten at 230 kV, and fourteen at 345 kV. They are active internal
NY branches with equal endpoint voltage, positive R/X, and no nontrivial tap
or phase shift. Transformers, DC links, external branches, and the two added
aggregate paths are excluded. This classification does not verify overhead
construction: every physical/conductor/route-verification flag remains false.

All 39 candidates have source `RATE_A=0`, meaning no supplied MATPOWER limit.
Zero is not a measured zero capacity or a thermal rating. The separate
[synthetic selection](output/nygrid_2019_full_stage1/synthetic_dlr_selection.csv)
declares the following assumptions:

- One equivalent circuit per selected branch; Drake 795 ACSR surrogates.
- One subconductor at 115/230 kV and two at 345 kV.
- 75 C conductor limit; emissivity/absorptivity 0.8; catalog resistance and
  geometry with the existing thermal library's heat-capacity/resistance-slope
  approximations. The 2026 catalog is a surrogate, not a 2019 installed-asset record.
- Effective length matched to electrical R at an assumed 75 C. All 39 lengths
  lie within the declared 1-300 km screening interval; these are not surveyed routes.
- Each weather condition below is applied independently to the same full year
  of fixed dispatch. Weather is synthetic, spatially uniform, and constant
  within each scenario. The angles are relative to the assumed conductor axis.

The reused thermal core computes convection, radiation, simplified solar
heating, and Joule heating. Ampacity is converted to a DC research limit using
`P_limit = sqrt(3) * nominal_kV * circuits * bundle_count * ampacity_A / 1000`.
This assumes nominal voltage and unity power factor. It is not an AC series
current measurement. Source R is not refitted, and no conductor count is
chosen to make the historical flows pass.

| Scenario | Air C | Wind m/s | Relative angle | Solar W/m2 | Per-subconductor A | Exceeded branch-hours | Share of 341,640 branch-hours |
|---|---:|---:|---:|---:|---:|---:|---:|
| Static reference | 40 | 0.61 | 90 deg | 1,000 | 732.37 | 144,541 | 42.31% |
| Windy/mild | 25 | 2.0 | 90 deg | 800 | 1,288.16 | 89,931 | 26.32% |
| Hot/low wind | 40 | 0.2 | 0 deg | 1,000 | 482.62 | 209,811 | 61.41% |
| Cool/windy | 5 | 1.0 | 90 deg | 100 | 1,353.42 | 84,304 | 24.68% |

A branch-hour is one branch at one hourly state. Every scenario has at least
one exceeded candidate in all 8,760 hours. Static-reference worst loading is
17.00 times the assumed limit; hot/low-wind worst loading is 25.80 times.
These severe exceedances show that the simple assumed circuit configuration
is not an adequate physical realization for some aggregate network flows.
They are **not observations of real 2019 line overloads**, and the lower
windy-case count is not a demonstrated congestion-cost or transfer-capacity
benefit. The preserved DC dispatch is unconstrained by these new capacities.

The heat-balance residual at the computed ampacities is at most 3.56e-14 W/m.
[Capacities](output/nygrid_2019_full_stage1/synthetic_dlr_capacities.csv),
[scenario summary](output/nygrid_2019_full_stage1/synthetic_dlr_summary.csv),
[hourly exposure](output/nygrid_2019_full_stage1/synthetic_dlr_hourly.csv), and
[explicit scope flags](output/nygrid_2019_full_stage1/synthetic_dlr_scope.json)
are inspectable independently.

## Use and next modeling work

See [reproduction instructions](scripts/nygrid_2019_full/README.md). For a saved
case in MATLAB from the repository root:

```matlab
addpath('System Matpower Format');
mpc = npcc_nygrid_2019_full_dc(4818); % prepared 2019-07-20 17:00 label
[result, success] = rundcpf(mpc, mpoption('verbose',0,'out.all',0,'exp.use_legacy_core',1));
```

The loader activates the four DC-link callbacks and restores hourly P/Q load,
input PG and external PMAX. Costs and interface-limit snapshot metadata are
removed because complete hourly economics and all interface constraint fields
were not reconstructed. Ramp metadata remains a first-hour snapshot and is
explicitly marked unavailable as an hourly series. This loader is for DC
power flow, not a ready-to-run economic dispatch or commitment model.

The next substantive DLR step is to assign defensible physical circuits or
explicit aggregate corridor realizations, then compare matched static and
DLR **constrained DC redispatch** cases using declared generation envelopes
and costs. A historical weather study additionally needs route/direction and
weather provenance with consistent timestamps. Dynamic conductor temperature,
AC/reactive feasibility, contingencies, and sag/clearance remain separate
unverified extensions. The present deliverable completes the selected full
2019 reconstruction and the first fixed-dispatch DC thermal scenarios.
