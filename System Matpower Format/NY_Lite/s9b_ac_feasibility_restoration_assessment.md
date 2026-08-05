# S9b Voltage-Reference and AC Restoration Assessment

## Corrected Interpretation

The original S9b continuation did not enforce independently sourced physical
generator-voltage schedules. Its internal reference was inherited from S1,
which saved an ACOPF solution obtained with `opf.use_vg = 0`.

All 48 S1 generator `VG` entries differ from original NPCC. CE UG changed from
1.020000 pu in original NPCC to 0.974721 pu in S1. CE UG is classified in the
reduced model as a Zone-I interface/voltage-support proxy, not a conventional
native generator with a validated local voltage schedule.

The defensible S9b statement is therefore:

> S9b measures compatibility with a selected numerical or source-case voltage
> reference. Results using S1 describe an S1 OPF-solved voltage-reference
> trajectory, not enforcement of real generator setpoints.

## Source-Controlled Reference Sets

`ny_voltage_reference_sets.csv` separates:

| Reference set | Meaning | Requested rows | Applied non-PQ buses | Skipped PQ buses |
|---|---|---:|---:|---:|
| `S1_OPF_SOLVED_REFERENCE` | Numerical continuation reference saved from S1 ACOPF | 20 | 20 | 0 |
| `ORIGINAL_NPCC_VG_REFERENCE` | Original NPCC generator-matrix `VG` fields | 20 | 20 | 0 |
| `PERFORM_ZONE_AGGREGATE_REFERENCE` | Provisional PMAX-weighted 2019 PERFORM zonal VG envelope | 30 | 20 | 10 |
| `CURRENT_S7_MODEL_REFERENCE` | Current model values with mixed provenance | 30 | 20 | 10 |
| `SHOULDER_BOUNDARY_EQUIVALENT_REFERENCE` | Separate scenario boundary-voltage priors | reported separately | reported separately | reported separately |

The PERFORM set is not yet a circuit-level control schedule. Direct parsing of
the PSS/E RAW file preserves all 649 generator-section `VS`/`IREG` records: 417
online records map to NYISO A-K at 179 source buses, one has a remote
regulated-bus assignment, and no online regulated bus is missing from the source
bus table. Preliminary classification identifies 34 reactive-only `QS` records,
381 positive-active-capability records, and two fixed-negative active-power
boundary/import equivalents. These are online RAW generator-section control
records, not 417 ordinary generators.

For the two 30-row reference sets, buses
`37|38|39|41|43|44|73|76|81|9003` are PQ buses and are skipped by the current
reference-bound application. The requested, applied, and skipped counts and IDs
are now explicit in every S9b summary row. The reduced reference remains a
low-confidence zonal aggregate because individual controls, deadbands, scenario
statuses, retained control groups, and pilot buses have not yet been mapped.

## Revised Numerical Procedure

For every reference weight and boundary-Q mode, S9b now:

1. applies the selected source-controlled voltage-reference envelope;
2. uses `opf.start = 2`, so warm runs use the preceding case state;
3. attempts a hard ACOPF with no restoration slack;
4. invokes MATPOWER AC soft limits only after the hard solve is unsuccessful;
5. distinguishes hard feasibility, nonzero restoration, nonconvergence, and
   solver exceptions;
6. records IPOPT status, iterations, the maximum P- or Q-balance component
   residual, and the maximum complex-power mismatch magnitude.

The installed IPOPT/MATPOWER wrapper does not expose complete dual,
complementarity, and KKT residuals. Those fields are saved as `NaN` with an
explicit availability note rather than being inferred.

## Restoration Objective

When restoration is invoked, the local AC NLP minimizes:

```text
1000 * sum(internal Q-limit slack in MVAr)
+ 1e7 * sum(voltage/reference-bound slack in pu)
+ 1e4 * sum(branch-flow slack in MVA)
+ 1e-4 * sum((Pg - Pg_S8)^2)
```

AC nodal balance, active-generator limits, angle limits, and the selected
external-boundary-Q mode remain hard. This hierarchy intentionally favors large
active redispatch over small voltage slack, so the Q/V/P decomposition is
metric-dependent and is not a unique physical deficiency estimate.

## Refined S1 Numerical-Reference Onset

The interval 0.8000-0.8250 was rerun at 0.0025 increments with:

```text
increasing and decreasing warm continuations
cold starts
two deterministic perturbed starts
all three boundary-Q modes for warm/cold paths
```

All paths agree:

```text
highest weight with a hard-feasible solution       0.8075
lowest weight with nonzero local restoration       0.8100
first slack element                                 CE UG VMAX
first slack at 0.8100                               0.00002727 pu
```

Thus the saved S1 numerical-reference onset is bracketed as:

```text
0.8075 < u_onset <= 0.8100
```

This is a local model/reference result, not a real-system voltage-control limit.
At the last hard-feasible point, absolute active redispatch is already about
763 MW and the worst interface residual is about 458 MW.

## Reference-Set Dependence

The compact comparison gives coarse hard-feasibility brackets:

| Reference set | Highest tested hard-feasible weight | First tested nonzero-restoration weight |
|---|---:|---:|
| Original NPCC VG | 0.75 | 0.80 |
| S1 OPF-solved | 0.80 | 0.825 |
| Current S7 model | 0.80 | 0.825 |
| Provisional PERFORM zonal aggregate | 0.90 | 1.00 |

At full reference weight under present limited boundary Q:

| Reference set | Q slack | Voltage slack | Absolute P redispatch | Worst interface residual |
|---|---:|---:|---:|---:|
| Original NPCC VG | 0 MVAr | 0.06874 pu | 1,917 MW | 651 MW |
| S1 OPF-solved | 170.41 MVAr | 0.07692 pu | 10,489 MW | 5,247 MW |
| Current S7 model | 170.41 MVAr | 0.07692 pu | 10,489 MW | 5,247 MW |
| Provisional PERFORM aggregate | 20.66 MVAr | 0.01859 pu | 4,350 MW | 2,071 MW |

The large variation confirms that the apparent threshold and slack allocation
are controlled strongly by voltage-reference provenance.

## Solver Integrity

The refined/reference audit contains 182 successful final solves:

```text
IPOPT final status                         0 for 182/182
solver exceptions                         0
maximum P/Q component residual             0.001067 MW or MVAr
maximum complex-power mismatch             0.001069 MVA
```

This establishes numerical consistency for the saved local solutions. It does
not supply a global infeasibility proof.

## Remaining Work

Before physical interpretation or S9c promotion:

1. validate a control-preserving reduction against the matching 2019 PERFORM
   snapshot before mixing source controls with 2025 public scenarios;
2. map classified source devices and regulated buses electrically to retained
   control groups and pilot buses;
3. import deadbands, taps, phase shifts, switched shunts/reactors, SVCs, and
   scenario status;
4. replace zonal PERFORM voltage aggregates with mapped source controls;
5. add scenario-specific active availability and redispatch trust regions;
6. include engineering interface-residual bands in a lexicographic restoration;
7. audit West-Central and Niagara West-Huntley measurement/network mappings;
8. perform interface and temporal holdout validation.

## Outputs

```text
ny_voltage_reference_sets.csv
ny_voltage_reference_coverage.csv
s1_opf_voltage_reference_provenance.csv
perform_zonal_voltage_reference_summary.csv
perform_generator_voltage_controls.csv
perform_voltage_control_coverage.csv
perform_voltage_control_classification_summary.csv
s9b_feasibility_restoration_summary.csv
s9b_feasibility_restoration_slacks.csv
s9b_external_boundary_q.csv
s9b_interface_residuals.csv
s9b_reference_continuation_summary.csv
s9b_reference_continuation_slacks.csv
s9b_reference_continuation_external_q.csv
s9b_reference_continuation_interfaces.csv
s9b_reference_onset_brackets.csv
```
