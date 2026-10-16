# Applying NYgrid methods to the compact New York model

**The matched-2019 experiment succeeds as a DC diagnostic.** A separate 51-bus historical compact variant, using the paper's reconstructed bus injections, explicit NY-side boundary conditions, paper-role interface definitions, and its two Marcy South reactances, has a best balanced snapshot with **3.28% pooled error and every interface within 4.86%**. It retains the NPCC benchmark power scale and every original NY bus. No new branch or injection parameter was fitted to an interface target in this experiment; the compact model retains its previously documented S4/S7 construction history.

This is a **pre-2025 historical comparison variant of our revised model**: 51 buses, 94 branch records, 89 active branches. It precedes the selected 2025 additions in the existing 71-bus model. The 71-bus preferred AC/DLR baseline and its frozen results remain unchanged. The new best cases are **DC-only, retrospectively selected examples**, not a calibrated 2025 model or untouched predictive validation.

## Review assessment and what was implemented

The review's main direction is supported. We implemented the bus-role/operator crosswalk, complete January 8 export, annual NY-only reference control, network/input comparison, fixed source-policy ablations, selected compact snapshots, and a separate bounded AC checkpoint. Shared-parameter fitting and fresh held-out validation are deferred until the representation questions below are resolved; no new fitted baseline is claimed.

The audit confirms all seven role differences: 38, 46, 47, 62, 69, 77 and 79. It also identifies source generator landings at 45, 49, 62, 74 and 77 that lack compact generator records, although the buses themselves are retained. Fixed-DC transfer preserves the source bus injections exactly instead of redistributing them among existing generators. [Crosswalk](output/nygrid_compact_2019/crosswalk_review.md).

One additional confound matters: the paper's original NPCC file has 227 branch records, versus 233 in our original parent. Parallel 43–50 and 74–78 multiplicities differ, and our S4 paths add further parallel transfer capability. Common NPCC ancestry alone therefore does not establish identical backbone response. These paths remain in the comparison; none was deleted to improve a score.

The NY-only reference uses 46 buses and 67 internal AC branch records. All 8,760 hours reproduce the source's branch and corrected interface flows to about 1e-11 actual MW. External auxiliary buses 21 and 132 disappear only after their NY-side effects enter the boundary ledger. HQ is separated from native generation and added once. Native input generation, solved generation, and the bus-74 slack adjustment are separate. [Complete reference export](output/nygrid_compact_2019/reference/REFERENCE_EXPORT.md).

## Strong compact snapshots

For a useful example across **every** interface, rank hours by the smallest worst individual percentage error. These three hours have no wrong-direction interface:

| New York local hour | Pooled error % | Worst interface % | Wrong directions |
| --- | --- | --- | --- |
| 2019-07-03 04:00:00 | 3.2787 | 4.8518 | 0 |
| 2019-07-22 04:00:00 | 2.6326 | 5.3109 | 0 |
| 2019-09-08 05:00:00 | 1.9516 | 5.5857 | 0 |

Per-interface absolute error divided by absolute observed flow, in percent:

| Interface | 2019-07-03 04:00:00 | 2019-07-22 04:00:00 | 2019-09-08 05:00:00 |
| --- | --- | --- | --- |
| Dysinger East | 1.46 | 0.44 | 2.57 |
| West Central | 1.48 | 5.31 | 3.14 |
| Moses South | 4.85 | 2.26 | 0.96 |
| Central East | 4.22 | 3.39 | 4.32 |
| Total East | 3.02 | 1.42 | 0.40 |
| UpNY-Coned | 3.75 | 1.62 | 5.59 |
| Dun/SPR-South | 2.45 | 5.09 | 0.01 |

The July 3 04:00 case in actual-scale MW is:

| Interface | Observed actual MW | Model actual-scale MW | Absolute error MW | Error % |
| --- | --- | --- | --- | --- |
| Dysinger East | 857.38 | 844.83 | 12.55 | 1.46 |
| West Central | 497.04 | 504.41 | 7.37 | 1.48 |
| Total East | 4110.18 | 4234.16 | 123.98 | 3.02 |
| Moses South | 1935.28 | 2029.18 | 93.90 | 4.85 |
| Central East | 2132.80 | 2042.70 | 90.11 | 4.22 |
| UpNY-Coned | 2833.57 | 2939.88 | 106.30 | 3.75 |
| Dun/SPR-South | 3468.36 | 3553.32 | 84.96 | 2.45 |

Internally, all loads, native generation, boundary P, interface targets and limits are multiplied once by **gamma = 0.358662225381536**. The actual-scale values above divide the benchmark results by that same factor; percentages do not change. For example, July 3 Total East has a 44.47 benchmark-MW mismatch, corresponding to 123.98 actual-scale MW. Reactances are not scaled.

The primary pooled ranking is also retained: September 6 02:00 has the lowest pooled error, **1.7732%**, but its worst individual error is **16.1524%**. September 8 05:00 has **1.9516% pooled** and **5.5857% worst-interface** error. No ranking criterion was silently replaced. All 8,760 rankings and both top-three selections are saved, with imputation/DST flags and minimum sample counts. The six unique selected/development states include January 8 and both ranking lists. [All errors](output/nygrid_compact_2019/best_snapshot_interface_errors.csv), [selected numerical inputs](output/nygrid_compact_2019/selected_dc_candidates.mat).

## Annual behavior and the Marcy experiment

WAPE below is `100 * sum(abs(model-observed)) / sum(abs(observed))`, calculated separately for each interface across all 8,760 hours. The pooled row sums across the seven overlapping interfaces; it is not a statewide energy-balance metric. No observation was excluded to improve these results.

| Interface | Paper reference WAPE % | Compact before Marcy % | Compact + Marcy % |
| --- | --- | --- | --- |
| ALL_SEVEN_POOLED | 11.22 | 17.38 | 12.32 |
| Central East | 9.63 | 49.23 | 7.09 |
| Dun/SPR-South | 10.89 | 11.02 | 11.02 |
| Dysinger East | 22.49 | 22.49 | 22.49 |
| Moses South | 8.99 | 8.99 | 8.99 |
| Total East | 7.24 | 7.24 | 7.24 |
| UpNY-Coned | 9.91 | 10.55 | 18.59 |
| West Central | 46.81 | 46.81 | 46.81 |

The Marcy experiment reduces pooled WAPE from **17.3825% to 12.3172%**, versus **11.2181%** for the paper reference. Pooled error improves in every month, by 4.06–5.87 percentage points. This is broader evidence than the selected good hours, but it remains retrospective.

The improvement comes principally from **Central East: 49.23% to 7.09%**. It also worsens **UPNY–ConEd: 10.55% to 18.59%**. West Central remains 46.81% annually. The variant therefore does not meet a 10–15% target on every interface.

Total East remains **7.235%** under the common paper inputs/roles, before and after Marcy. The complete western export is fixed by regional net injections. Marcy changes internal sharing and Central East flow; it cannot repair an arbitrary regional net-export error at fixed injections. The matched-hour [regional ledger](output/nygrid_compact_2019/total_east_regional_ledger.csv) reconciles generation, net load, boundaries and balancing with the full modeled cut to numerical precision.

The two added DC links are 43–38 with X=0.0427 and 38–77 with X=0.0147 pu on 100 MVA. Neither active endpoint pair existed in the compact parent. Original 38–69 and the different S4 38–39 path remain. This rules out identical-edge duplication, not every possible functional overlap between equivalents. The numerical additions use R=B=0 and RATE_A=0 solely because these quantities are not qualified by the DC experiment: zero rating means **unrated**, not safe at arbitrary loading. No installed conductor, resistance, thermal capacity or AC capability is inferred.

Changing only the metering/allocation roles also changes the score. With the paper inputs on the same compact electrical states, the current-role conventions give **19.07%** before Marcy and **19.67%** after its addition. For the Marcy variant, current-role cuts are extended to include any new crossing. These are separately reported measurement conventions, not improvements to physical geography or proof of exact NYISO flowgate membership.

## Network/input matrix and policy diagnostics

All arms use the paper-role metering convention and a bus-74 balance. A is the NYgrid NY-only network with paper inputs; B uses current reconstructed inputs on that reference; C uses paper inputs on compact51; D uses current inputs on compact51. C_marcy/D_marcy add the two declared paths. Values are pooled proportional error in percent:

| timestamp | A | B | C | D | C_marcy | D_marcy |
| --- | --- | --- | --- | --- | --- | --- |
| 2019-01-21 18:00:00 | 9.40 | 16.96 | 19.52 | 19.73 | 14.43 | 16.97 |
| 2019-04-21 04:00:00 | 22.62 | 36.66 | 27.91 | 39.50 | 19.08 | 29.85 |
| 2019-07-17 16:00:00 | 20.72 | 26.23 | 30.83 | 25.40 | 26.10 | 27.53 |
| 2019-07-20 16:00:00 | 12.34 | 16.13 | 23.05 | 19.42 | 16.84 | 17.43 |
| 2019-07-27 02:00:00 | 18.86 | 26.87 | 22.84 | 22.94 | 23.20 | 27.95 |

The five current-source hours were already qualified in the earlier campaign. The sixth July 17 08:00 hour remains excluded from this current-input matrix because of its previously documented boundary-data gap; it is still included in the complete paper-input annual study. Existing current inputs use P32 forward-hold hourly means; paper inputs use the released raw-sample arithmetic means. This timing-policy difference is part of the input-method comparison, not a topology effect.

The current inputs include generation at added bus9003. B uses a frozen, exact compact-network Schur injection map to the 46 common ports: its equal-X paths split that injection 50/50 to 78 and 80. This is a **model-derived port equivalent**, not observed geographic placement. The mapping preserves total injection, and reconstructs every original compact branch flow within 1e-7 MW before transfer to the different reference topology. C/D retain all 51 buses. [Mapping and checks](output/nygrid_compact_2019/common_port_equivalence_checks.csv).

The old missing H prior is explicitly restored at the literal paper terminal74. It is the available **combined zonal source estimate**, apportioned to two Indian Point proxies, not unit-level nuclear telemetry. January/April exceed the release-derived combined proxy capacity by 6.43/5.05 benchmark MW; raw values stay visible and are not silently clipped. Nuclear placement at77 is exported separately as a spatial sensitivity, not used to select the best reported DC states.

On compact+Marcy, the following one-rule changes retain all other paper inputs. Each cell is pooled error percent:

| Local hour | Current boundary | Current hydro spatial rule | Current load spatial rule | Paper policies | Statewide thermal residual |
| --- | --- | --- | --- | --- | --- |
| 2019-01-21 18:00:00 | 12.73 | 16.13 | 32.61 | 14.43 | 11.46 |
| 2019-04-21 04:00:00 | 19.60 | 23.10 | 27.93 | 19.08 | 22.40 |
| 2019-07-17 16:00:00 | 25.71 | 29.59 | 57.73 | 26.10 | 19.86 |
| 2019-07-20 16:00:00 | 16.80 | 14.88 | 38.33 | 16.84 | 13.33 |
| 2019-07-27 02:00:00 | 17.98 | 22.92 | 44.39 | 23.20 | 20.08 |

These are diagnostic comparisons, not a fitted parameter search. Statewide thermal residual normalization improves four of the five hours versus the literal J-only policy, so the review does **not** justify adopting J-only allocation as universally better for our network. The current hydro spatial rule is worse in three hours and better in two. The load spatial diagnostic changes **both allocation-role membership and within-zone weights** while preserving paper zonal totals; it is not an isolated weight-only test on identical partitions. Its deterioration exposes the importance of matching generation and load roles, not proof that the paper's labels are physically correct.

The six exported component hours expose missing raw thermal values, source residuals and source capability violations. For example, the released July St. Lawrence assumption produces 921.12 MW against its 856-MW capacity parameter. Copying the complete source reconstruction faithfully is distinct from qualifying all of its assumptions. A source-informed, capacity-bounded uncovered-unit policy and temporal hydro-energy calibration remain future work.

## Separate AC checkpoint

Three seasonal **current-source** inputs with the restored 2019 fleet pass bounded AC optimization and a fresh power-flow audit on the unchanged compact51 network:

| Local hour | Solver | Bounded AC pass | Dispatch L1 MW | Largest unit P move MW |
| --- | --- | --- | --- | --- |
| 2019-01-21 18:00 | MIPS | 1 | 162.46 | 25.63 |
| 2019-04-21 04:00 | IPOPT | 1 | 5.05 | 2.54 |
| 2019-07-20 16:00 | MIPS | 1 | 168.31 | 20.53 |

All values above are benchmark MW. No interface objective, changed load, changed boundary schedule, or relaxed equipment bound was used. The April first MIPS attempt failed its physical audit and remains recorded; strict IPOPT fallback passed. The initial raw-prior fixed-control PF converged in all three cases but failed operating-limit checks.

Control movement is material: maximum voltage changes from the inherited benchmark initializer are 0.145–0.183 pu and aggregate reactive dispatch changes are 3,518–8,096 MVAr. These are **reoptimized feasible operating points**, not fixed-control historical reconstructions. This checkpoint does **not** qualify the best DC Marcy snapshots. Their R/B, finite ratings, missing generator-landings/capability mapping and reactive controls still need a separate defensible AC implementation. No new DLR/thermal claim is made. [AC evidence](output/nygrid_compact_2019/ac_checkpoint/summary.csv).

The separate common-target [AC scoring](output/nygrid_compact_2019/ac_scoring/) compares the three raw-prior DC cases at **reference42**, matching the existing AC reference, with their bounded AC results. Across those 21 comparisons, current-role WAPE changes from **19.06% to 17.54%**; paper-role WAPE changes from **23.43% to 22.47%**. Individual hours can worsen. These increments include AC physics, loss balancing, redispatch and control changes together; they are not pure loss corrections and are distinct from the matrix's reference74 policy. Reverse AC members use their upstream **PT** value, not minus PF.

In the April checkpoint, losses rise from about **98.99 MW** in the raw-prior reference-balancing PF to **206.54 MW** after bounded optimization. The P-prior objective can preserve almost all specified generation by using the permitted voltage/reactive controls to change losses. This is a material limitation for historical operating reconstruction and requires a control-reference policy before transferring the result into a calibrated AC/DLR study.

## Reproduction and next decision

The scripts and numerical exports are under `scripts/nygrid_compact_2019/` and `output/nygrid_compact_2019/`. The workflow is described in the [reproduction guide](scripts/nygrid_compact_2019/README.md). The independent comparison audit passes **188 checks**, including all annual predictions, all 30 matrix rows, all 25 allocation ablations, and six selected MATPOWER DC replays. The separate source export, common-port checks, ten analytic solver/guard tests, twelve compact-export test groups, three AC disk replays and six AC adversarial guards are retained with fingerprints. The [independent verification](output/nygrid_compact_2019/verification/independent_validation.md) distinguishes numerical reproduction from operating or predictive validation.

The next useful calibration targets are representation consistency, UPNY transfer sharing, West Central injection uncertainty, and the uncovered-unit/hydro rules. Shared parameters should then be frozen before a genuinely unexamined evaluation period. The selected 2019 hours are suitable **development examples** for preliminary active-flow research; the preferred 2025 AC/DLR model should not be relabelled calibrated from them.

Sources: the [pinned NYgrid release](https://github.com/AndersonEnergyLab-Cornell/NYgrid/tree/47698b6c7823ae7b1bc6935e5601d5b64b8f918e), its [network additions](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/modifyMPC.m), and [operating reconstruction](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/updateOpCond.m). The paper's rating-normalized metric is distinct from the observed-flow percentages reported here. MATPOWER documents the separate [DC slack calculation](https://matpower.app/manual/matpower/DCPowerFlow.html) and [bounded AC formulation](https://matpower.app/manual/matpower/StandardACOPF.html).
