# S9a Reactive-Control Diagnostic Assessment

## Purpose

S9a tests the shoulder case with temporary positive/negative Q-only devices,
normal voltage and branch constraints, fixed external schedules, and quadratic
penalties around the S8 active dispatch. The devices are diagnostic slacks, not
proposed equipment.

## Reactive Capability Prior

The inherited reduced case contains broad placeholder-like Q limits, including
many +/-999 MVAr records. S9a therefore also aggregates native online PERFORM
generators by zone, excludes import/reference records, and scales each zonal
QMIN/QMAX envelope by retained-model zonal PMAX.

The resulting Q ranges are approximately 1.25-1.37 times zonal PMAX. They are
used as a first aggregate prior, not validated unit-level capability.

## Free-Voltage OPF Result

With `opf.use_vg = 0`, both the inherited and PERFORM-scaled Q envelopes solve
the full ACOPF with normal branch and voltage limits and essentially unchanged
active dispatch. The temporary Q devices remain at zero.

This means only that no **additional temporary internal Q device** is required
when generator voltages, active dispatch, broad internal Q envelopes, and the
present boundary-equivalent Q injections can all adjust. It does not establish
that the reduced model contains the correct physical reactive resources. The
1189-MVAr violation from the standard S8 PF is not, by itself, an established
system-wide Q deficiency.

## Voltage-Setpoint Continuation

Temporary Q devices inherit the existing current-model `VG` field at generator
buses, so they do not artificially widen the tested bounds. These fields are
primarily S1 OPF-solved voltage references, not independently sourced physical
setpoints.

| S1/current reference weight (`opf.use_vg`) | OPF success | Minimum temporary support | Active locations |
|---:|---:|---:|---|
| 0.00 | yes | 0 MVAr | none |
| 0.25 | yes | approximately 0 MVAr | none |
| 0.50 | yes | 0 MVAr | none |
| 0.75 | yes | 0 MVAr | none |
| 0.80 | yes | 36.07 MVAr | AK-3 |
| 0.85 | yes | 227.84 MVAr | AK-3, Huntley |
| 0.90 | yes | 833.27 MVAr | Huntley, AK-3, Binghamton |
| 1.00 | no saved success | not established | IPOPT exception; MIPS nonconvergence; also unsuccessful without ratings |

At S1/current reference weight `0.90`, the diagnostic support is:

```text
Huntley       443.33 MVAr
AK-3          326.24 MVAr
Binghamton     63.70 MVAr
Total         833.27 MVAr
```

No negative-Q device is selected in these minimum-support cases.

## Interpretation

The continuation shows rapidly increasing support between reference weights
0.85 and 0.90. Full-reference enforcement has not produced a successful saved solution
even after branch ratings are removed, so Niagara congestion is not the sole
cause. This is not yet proof of infeasibility: IPOPT encountered an
implementation exception and MIPS nonconvergence alone is not a certificate.

The current evidence points to missing or inconsistent voltage-control detail:

```text
generator voltage schedules
transformer tap positions
fixed/switched shunts and reactors
scenario-dependent control status
reactive capability placement
```

Temporary support should not be converted directly into capacitor or generator
ratings. First import or derive PERFORM voltage schedules, regulated buses, transformer taps,
phase shifts, and shunt status for a comparable operating regime.

## Interface Result

S9a does not include interface-flow penalties. Its feasible cases still have a
roughly 398-451 MW worst interface residual, dominated by West-Central. This is
expected and preserves the separation between reactive feasibility and active
interface calibration.

## Outputs

```text
s9a_q_support_case_summary.csv
s9a_q_support_by_bus.csv
s9a_p_redispatch.csv
s9a_interface_residuals.csv
s9a_binding_constraints.csv
s9a_existing_generator_q_dispatch.csv
s9a_external_boundary_q_dispatch.csv
s9a_perform_zonal_q_capability.csv
s9a_voltage_setpoint_audit.csv
```
