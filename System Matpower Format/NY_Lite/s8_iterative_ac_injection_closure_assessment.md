# S8 Iterative AC Injection-Closure Assessment

## Status

S8 is an operational diagnostic on the direct-PERFORM S7 network. It is not a
new structural case and it is not a final calibrated model.

The experiment confirms that most of the S7 interface-flow error came from the
open loop between the lossless DC injection estimate and the AC PF. Re-estimating
zonal generation against AC flows nearly eliminates the dominant UPNY-ConEd and
Dunwoodie residuals. However, the resulting shoulder dispatch is not Q/voltage
feasible, and the West-Central shoulder target remains outside the capability of
the present A/B representation.

## Method

`derive_nyiso_zonal_net_injections_ac_iterative.m` performs the following steps:

1. Initialize from the constrained seven-interface DC estimate.
2. Run AC PF on the selected direct-PERFORM S7 topology.
3. Measure AC losses and distribute the required generation increment by zonal
   upward headroom.
4. Form finite-difference AC interface sensitivities using transfer directions
   `e_z - alpha`, where `alpha` is a distributed participation vector.
5. Solve a bounded zonal redispatch with exact zero-sum redispatch after the
   loss allocation.
6. Apply a 0.4 damped update and repeat for at most six iterations.
7. Close the remaining loss mismatch until reference pickup is below 0.1 MW.

The historical limit-normalized objective remains the reporting score.
Redispatch uses separate 100-150 MW engineering accuracy scales and Huber-style
iterative weights. External interchange remains fixed at the scaled P-32 values.

## Aggregate Result

| Score | Reporting objective | Mean absolute residual | Worst residual | Mean signed residual |
|---|---:|---:|---:|---:|
| Initial DC estimate | 0.015599 | 36.41 MW | 354.89 MW | -21.08 MW |
| Frozen-S6 dispatch on direct S7 | 0.233303 | 138.35 MW | 424.91 MW | -137.98 MW |
| Iterative AC reoptimized dispatch | 0.015310 | 19.49 MW | 416.00 MW | -18.11 MW |

Relative to frozen S7 scoring, iterative closure reduces the reporting objective
by 93.44% and mean absolute residual by 85.91%. Maximum residual improves only
slightly because the shoulder West-Central target remains infeasible under the
current A/B generation bounds.

## Interface Result

| Interface | Frozen S7 MAE | Reoptimized AC MAE |
|---|---:|---:|
| Dysinger East | 57.00 MW | 23.27 MW |
| West Central | 138.87 MW | 82.48 MW |
| Moses South | 26.85 MW | 3.05 MW |
| Central East | 104.38 MW | 6.19 MW |
| Total East | 142.07 MW | 7.87 MW |
| UPNY-ConEd | 259.81 MW | 11.40 MW |
| Dunwoodie South | 239.47 MW | 2.20 MW |

The two previously dominant downstream interfaces are therefore controlled far
more strongly by dispatch/loss closure than by the three PERFORM-supported line
multipliers.

## Loss Closure

The largest final absolute reference-generation adjustment is 0.0983 MW. This
replaces the archived 146-589 MW single-bus Zone-J loss pickup with scheduled,
headroom-weighted zonal loss allocation. Zone J remains the numerical reference
for PF robustness, but it no longer supplies the system loss requirement by
itself. Finite-difference transfers are explicitly balanced by the distributed
participation vector.

## Shoulder Limitation

The shoulder result does not satisfy the active-flow calibration stopping
criteria:

```text
West-Central residual                 -416.00 MW
Minimum voltage                          0.85457 pu
Low-voltage buses                               3
Maximum Q-limit violation              1189.18 MVAr
Q-limit-enforced PF success                    false
Niagara West-Huntley overload           170.24 MVA
```

Zones A and B finish at approximately 1292.65/1292.80 MW and
288.77/288.80 MW, respectively. The West-Central residual is therefore not
correctable through another unconstrained AC sensitivity iteration without
changing capability, GSK, external schedules, or the interface measurement.

The shoulder Q violations occur at CE UG, Huntley, and AK-3. Iterative active
redispatch increases the maximum Q violation relative to frozen S7, confirming
that active-flow agreement must not be accepted without Q/voltage constraints.

## Physical Feasibility Across Six Scenarios

```text
Standard PF success                    6/6
Q-limit-enforced PF success            5/6
Minimum voltage                        0.85457 pu
Maximum voltage                        1.10846 pu
Largest branch overload                170.24 MVA
Largest generator Q violation         1189.18 MVAr
Largest generator P violation            0.00 MW
```

Niagara West-Huntley remains overloaded in every scenario; the winter scenario
also overloads Niagara West-Rochester. These violations were not included as
hard constraints in the active-flow estimator.

## Interpretation Boundary

The reoptimized operational score uses all seven interface targets to infer the
same scenario's zonal dispatch. It demonstrates achievable in-sample AC flow
consistency; it is not independent validation of the proxy interface maps or
transmission parameters.

Direct-PERFORM S7 remains the structural baseline. S8 shows that dispatch/loss
closure is the dominant numerical correction for most interfaces, while also
making the remaining physical and measurement problems easier to isolate.

## Next Work

1. Replace zone-pair proxy cuts with audited branch/sign maps.
2. Add PERFORM-derived aggregate Q capability, shunts, tap ratios, and phase
   shifts before accepting any reoptimized dispatch.
3. Audit Niagara West-Huntley and Niagara West-Rochester ratings, circuits,
   impedances, and western GSK allocation.
4. Diagnose whether the shoulder West-Central target is incompatible with the
   scaled A/B capability or with the proxy interface definition.
5. Add leave-one-interface-out and temporal holdout tests before using the
   operational score as calibration evidence.

## Output Files

```text
s8_ac_iterative_pf_results.csv
s8_structural_vs_operational_interface_residuals.csv
s8_structural_vs_operational_summary.csv
s8_interface_summary.csv
s8_ac_iteration_history.csv
s8_ac_sensitivity_history.csv
s8_distributed_participation_history.csv
s8_final_zonal_generation.csv
s8_final_perform_bus_allocation.csv
s8_final_pf_violations.csv
s8_q_enforced_pf_diagnostics.csv
```
