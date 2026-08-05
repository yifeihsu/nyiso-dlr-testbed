# S8.1 Local Linear Capability-Envelope Assessment

## Purpose

S8.1 tests whether the shoulder West-Central conflict is caused by the inherited
S4 A/B/C cap factor before changing interface definitions or transmission
parameters. It uses the final S8 AC sensitivity matrix and then applies each
linear proposal to a nonlinear AC PF with distributed loss closure.

## Linear Certificate

| A/B/C cap factor | Minimum eta | Linear worst residual | Minimum A/B/C relaxation for eta <= 1 |
|---:|---:|---:|---:|
| 0.80 | 2.7013 | 405.20 MW | 272.58 MW |
| 0.90 | 1.5742 | 236.12 MW | 91.79 MW |
| 1.00 | 0.9937 | 149.06 MW | 0 MW |

At the inherited 0.8 envelope, the minimum-relaxation solution assigns:

```text
Zone A       5.41 MW
Zone B     267.17 MW
Zone C       0.00 MW
Total      272.58 MW
```

The strict 0.8 solution binds A, B, C, and D PMAX. The first-stage minimax-LP
PMAX dual values for
A and B are approximately 0.00554 and 0.00626 eta per additional MW,
respectively.

The minimum-relaxation output reports both the first-stage LP capability dual
and the second-stage minimum-norm QP dual. They are not interchangeable.

## West-Central Local Test

Under the current 0.8 bounds:

```text
Base West-Central residual                       -416.00 MW
Maximum correction when other interfaces ignored 113.39 MW
Remaining residual                               -302.61 MW
Correction while other six remain in bands          3.88 MW
Remaining residual                               -412.12 MW
```

This confirms a local incompatibility under the inherited envelope. It is not
an optimizer convergence or Huber-weighting artifact.

## Nonlinear AC Recheck

The linear certificate is necessary but not sufficient. After applying the
strict proposals and reclosing AC losses:

| Cap factor | Nonlinear worst residual | Minimum V | Maximum Q violation | Q-limit PF |
|---:|---:|---:|---:|---:|
| 0.80 | 500.54 MW | 0.92856 pu | 134.64 MVAr | succeeds |
| 0.90 | 286.60 MW | 0.89784 pu | 572.86 MVAr | fails |
| 1.00 | 164.70 MW | 0.86538 pu | 998.76 MVAr | fails |

The redispatch is large relative to a single Jacobian evaluation, so this is a
**local linear certificate with nonlinear recheck**, not a global nonlinear
infeasibility certificate. Restoring 1.0 makes the seven active targets locally compatible in
the saved linearization but does not create an acceptable nonlinear AC operating
point. The extra western capability worsens the reactive/voltage condition.

Total absolute strict-solution redispatch is 1024.72 MW at cap 0.8, 1578.65 MW
at cap 0.9, and 2138.60 MW at cap 1.0. These movements explain why one fixed
Jacobian should not be treated as a nonlinear trajectory.

## Scenario Availability

No independent 2025 hour-specific unit availability or commitment table exists
in the project. Static Gold Book capability is not relabeled as scenario
availability. `nyiso_scenario_available_capability_TEMPLATE.csv` defines the
required input schema and the scenario-specific envelope remains unrun.

## Decision

Describe the shoulder result as:

> Infeasible under the inherited S4 0.8 A/B/C participation envelope and the
> current West-Central proxy measurement. Restoring the 1.0 envelope removes
> the local linear active-power conflict but fails nonlinear Q/voltage checks.

Do not promote cap factor 1.0 and do not retune R/X/B from this result.

## Outputs

```text
s8_1_capability_envelope_summary.csv
s8_1_capability_interface_residuals.csv
s8_1_capability_bound_duals.csv
s8_1_capability_relaxation.csv
s8_1_capability_redispatch_proposals.csv
s8_1_capability_nonlinear_recheck.csv
s8_1_west_central_local_diagnostics.csv
s8_1_scenario_availability_status.csv
```
