# S7 seven-interface alignment and PERFORM tie calibration

## Scope

The public target set was expanded from five to all seven internal interfaces
present in the downloaded P-32 files:

```text
Dysinger East      A-B
West Central       B-C
Moses South        D-E
Central East       E-F
Total East         F-G
UPNY-ConEd         G-H
Dunwoodie South    I-J
```

The S6 constrained estimator was rerun with all seven measurements. Its zonal
generation targets were then frozen. Loads, zonal generation, PERFORM GSK bus
allocation, and scaled external schedules remained identical during every tie
candidate PF.

## Calibration design

Only three added corridors have direct parameter evidence in PERFORM:

```text
Gilboa-Leeds
Pleasant Valley-Wood Street, two-circuit equivalent
Wood Street-Millwood, two-circuit equivalent
```

The calibration varied impedance multipliers around the PERFORM R/X values and
the fraction of PERFORM lower-Hudson line charging. Four public hours were used
for training. The shoulder-light-load and low-Total-East hours were held out.
A small log-parameter regularization penalized movement away from PERFORM.

The broad, refined, edge, and final sweeps executed 2,112 standard AC PFs. All
converged. Q-limit enforcement was rerun separately on the selected cases.

## Recommended parameters

The training-optimal fitted sensitivity was:

```text
Gilboa-Leeds multiplier                 2.00
Pleasant Valley-Wood Street multiplier 0.85
Wood Street-Millwood multiplier        1.00
Lower-Hudson PERFORM B fraction        1.00
```

It was not promoted because exact PERFORM had slightly better holdout, minimum
voltage, and maximum-residual diagnostics. The recommended S7 candidate uses
the direct PERFORM values:

| Corridor | R pu | X pu | B pu | RATE_A MVA |
|---|---:|---:|---:|---:|
| Gilboa-Leeds | 0.001310 | 0.019970 | 0.51614 | 1216 |
| Pleasant Valley-Wood Street | 0.000405 | 0.006185 | 0.63943 | 2432 |
| Wood Street-Millwood | 0.000185 | 0.002815 | 0.29107 | 2432 |

## PF consistency

| Case | Training objective | Holdout objective | All-hour objective | Worst residual |
|---|---:|---:|---:|---:|
| Current S4 ties | 0.13566 | 0.14992 | 0.28558 | 572.6 MW |
| Direct PERFORM | 0.12945 | 0.10385 | 0.23330 | 424.9 MW |
| Fitted sensitivity | 0.12435 | 0.10407 | 0.22842 | 435.5 MW |

Direct PERFORM reduces the all-hour objective by 18.3% and the held-out
objective by 30.7% relative to the current ties.

| Interface | Current MAE | Direct-PERFORM MAE | Change |
|---|---:|---:|---:|
| Dysinger East | 57.3 MW | 57.0 MW | -0.3 MW |
| West Central | 139.1 MW | 138.9 MW | -0.3 MW |
| Moses South | 26.84 MW | 26.85 MW | effectively unchanged |
| Central East | 106.4 MW | 104.4 MW | -2.0 MW |
| Total East | 144.6 MW | 142.1 MW | -2.6 MW |
| UPNY-ConEd | 268.2 MW | 259.8 MW | -8.3 MW |
| Dunwoodie South | 272.6 MW | 239.5 MW | -33.2 MW |

## Feasibility status

Direct PERFORM improves the standard-PF minimum voltage from 0.8037 to 0.9022
pu and reduces the maximum branch overload from 169.0 to 168.1 MVA. It does not
fully certify AC feasibility:

- maximum voltage remains 1.1128 pu;
- up to three voltage-bound violations remain;
- one branch overload remains;
- standard PF reports up to three generator Q-limit violations;
- Q-limit-enforced PF succeeds for five of six hours;
- the shoulder-light-load Q-limit PF still returns success = 0.

## Decision

Use `npcc_ny_lite_s7_seven_interface_perform_direct_candidate` as the
recommended structural S7 case. Keep the fitted multiplier case as a sensitivity
only. The seven-interface active-flow consistency is improved on both training
and held-out hours, but reactive/voltage repair is still required before calling
the operating points fully feasible.
