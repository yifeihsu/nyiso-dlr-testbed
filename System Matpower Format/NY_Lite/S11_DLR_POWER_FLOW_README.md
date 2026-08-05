# S11-DLR diagnostic/reduced-model AC benchmark

## Current status

The central-Q `S1_2025_SUMMER_PEAK_PUBLIC` case passed the implemented hard
validation gates on 2026-07-14 and is retained as the accepted nominal S11
diagnostic benchmark. It is not the promoted NPCC DLR testbed. The retained
unsolved input and solved result are:

- `npcc_ny_lite_s11_dlr_pf_base.m`
- `npcc_ny_lite_s11_dlr_pf_solution.m`

The S1 0.90/1.10-Q sensitivities also passed and are retained as validation
cases. All S2 winter and S5 high-Total-East variants were excluded. S2 exceeds
both dispatch-movement gates; S5 exceeds the dispatch and interface gates.
Their managed case files were deliberately invalidated rather than left looking
current. This follows the plan's rule to exclude a scenario rather than soften
limits or save a misleading case.

The CSV gate ledger is authoritative for acceptance within the S11 diagnostic
set. A filename alone is not proof that a case is accepted.

## Latest validation result

The full S1/S2/S5 by central/0.90/1.10-Q matrix and the shared 2019 PERFORM
benchmark were rebuilt on 2026-07-14.

The 2026-08-05 hierarchy update changed only S11 role/status labels in the
historical ledgers. The electrical values below were not rerun: the current
public target tables have been retargeted to 2019 IDs, while this S11 matrix
still names the retired 2025 scenario IDs. A future S11 refresh must first map
that diagnostic matrix onto the current target set; it cannot silently treat
missing 2025 rows as failed electrical cases.

| Central-Q scenario | Result | Interface MAE / max / bias (MW) | Reference pickup (MW) | Zonal redispatch |
|---|---:|---:|---:|---:|
| S1 summer peak | diagnostic pass | 71.662 / 98.191 / 28.793 | 0.000001 | 1,971.297 MW (6.433%) |
| S2 winter peak | excluded | 41.441 / 80.915 / -20.690 | 0.020 | 3,199.397 MW (13.602%) |
| S5 high Total East | excluded | 156.800 / 318.407 / -86.401 | -0.000009 | 3,410.424 MW (12.037%) |

Every accepted S1 variant passed standard AC PF, Q-limit-enforced PF, voltage,
generator P/Q, trusted static branch, reference-pickup, interface, placeholder-Q,
control-provenance, physical-circuit, and dispatch-movement gates with zero
restoration slack. S1 used the no-slack hard ACOPF feasibility projection. Its
operational reference is the mapped source-backed control at bus 73, and no
regulating bus lies outside candidates 37, 38, 39, 41, 73, 76, and 81.

S2 is electrically and interface feasible, but its 3,199.397 MW source-balanced
zonal movement is 13.602% of NY load, exceeding the 3,000 MW and 10% gates. S5
is electrically hard-feasible but fails both dispatch gates and its calibrated
interface closure; its largest central-Q residual is 318.407 MW. No limit,
external-Q range, or dispatch justification was introduced.

The corrected 2019 same-snapshot benchmark passed:

- five direct physical-circuit current errors: 5.051%, 7.555%, 7.555%,
  11.302%, and 11.302%;
- active network loss error: 0.000096%;
- corrected net-network-Q error: 2.470%; and
- Q-limit-enforced PF.

## Model composition and provenance

S11 is a 49-bus NYISO A-K core with external NPCC boundary equivalents and is
used only for fast algorithm tests and reduced-model diagnostics. The
143-bus `npcc_ny_lite_s7_seven_interface_perform_direct_candidate` case is the
full structural parent and remains in the package for topology tracing and
future S13 external-NPCC work.

The builder performs this sequence:

1. Load the S7 direct-PERFORM structural case and create the 49-bus NY-only
   boundary-equivalent core.
2. Split Pleasant Valley-Wood Street and Wood Street-Millwood into two physical
   circuits each; retain Gilboa-Leeds as one circuit. The result has 49 buses,
   83 branches, and five explicitly mapped physical circuits.
3. Apply the persisted sparse non-DLR equivalent correction while verifying
   that all five physical DLR branch R/X/B rows remain exactly frozen.
4. Apply public zonal P load and source-backed 2019 PERFORM zonal Q/P ratios,
   including the 0.90 and 1.10 Q sensitivities.
5. Apply fixed public external P schedules and fixed-zero external Q by default.
6. Apply the 649-row source-bus-plus-generator-ID control map without replacing
   the scenario loads or external schedules.
7. Infer zonal active dispatch with AC loss and mapped-interface closure using
   a constrained-DC seed, source-backed PMIN/PMAX, headroom loss participation,
   50-100 MW trust regions, and a recomputed AC sensitivity matrix after each
   accepted step.
8. Require standard and Q-limit-enforced AC PF; if needed, run a no-slack hard
   ACOPF feasibility projection.
9. Recompute final interfaces, dispatch movement, losses, limits, and branch
   currents from the accepted final solution.

The enabled source-backed PV candidates are buses 37, 38, 39, 41, 73, 76, and
81. EDIC, Porter, and East Garden City at buses 43, 44, and 9003 remain
provisional PQ/fixed-Q locations. Generic internal `+/-999` and `+/-9999` MVAr
ranges are prohibited. Boundary/reference classification takes precedence over
storage or pumping heuristics, including the Marcy `RF` record.

The old S7 `abc_cap_factor=0.8` operational restriction is not used. Mandatory
dispatch movement is measured from the 2019 source-PG zonal prior after a
headroom-weighted PMIN/PMAX-constrained adjustment to the public scenario's
required total generation. This excludes the unavoidable non-zero total change
between the 2019 and public snapshots, but includes the entire constrained-DC
interface inference and final AC closure. It is subject to both the 10% of NY
load gate and an unconditional 3000 MW ceiling. The raw source-prior, legacy
scenario, scenario-balanced-prior, and post-DC-seed movements are all retained
as diagnostics so the baseline boundary is explicit.

## Interface operators and known limitation

`nyiso_interface_branch_map.csv` replaces dynamic zone cuts with explicit
branch/cutset operators, monitored-circuit provenance, metered ends, signs,
effective dates, and confidence labels.

The calibrated operators are Dysinger East, West Central, Moses South, and
Central East. Moses South uses the explicit conserved retained-enclave cut
`PT8 + PT11 + PF14 + PT19 + PT62` for the retained set `{44,47,48}`. Against
the 2019 source snapshot, this cut is within 0.77% of the seven listed source
monitored-circuit terminal-flow sum.

Total East remains diagnostic. The official composite contains Central East,
GF5-35, external ties, Rockland elements, and other monitored paths that are not
all represented in the 49-bus reduction. The available partial proxy cannot be
made source-complete or sign-consistent within the 200 MW gate, so it was not
calibrated by cherry-picking omitted terms. See the
[NYISO Total East stability report](https://www.nyiso.com/documents/20142/3692388/TE-22-StabReport-OC-4-20-2022-Approved.pdf/e20daf31-0dda-1365-271a-abd36350ad8a).

UPNY-ConEd and Dunwoodie South likewise remain diagnostic because their full
public monitored-circuit definitions are not conserved in the reduced model.
This four-operator calibration set is a documented limitation relative to the
original five-interface goal, not an unreported tolerance change.

## Non-DLR equivalent correction

The persisted correction is a sparse empirical complex-admittance fit over
non-DLR equivalent branches and retained-bus shunts. It includes a hard-AC-
feasibility-verified retained-bus shunt refit at buses 9002 and 73. The five
direct physical DLR branches are never optimization variables.

The local five-anchor Ward/Kron diagnostic worsens from approximately 0.317 to
0.889 complex relative Frobenius error. This is reported, not concealed. It is
diagnostic rather than a repository promotion gate; the mandatory S11
acceptance checks are the
five selected-circuit currents, active loss, and corrected net network Q, all of
which pass. The correction is therefore an empirical reduced equivalent, not an
exact Ward reduction or a utility planning equivalent.

The benchmark reactive identity is:

```text
net network Q = series reactive loss - line charging injection - bus shunt injection
```

MATPOWER `get_losses` charging terms are treated as real-valued MVAr injections,
not passed through `imag(...)`.

## Build and validation

Run from the package root in MATLAB:

```matlab
addpath('System Matpower Format')
addpath('System Matpower Format/NY_Lite')
out = run_s11_dlr_validation();
```

For a diagnostic run that retains evidence even if the nominal case fails:

```matlab
out = run_s11_dlr_validation(struct('fail_on_nominal', false));
```

For a no-write diagnostic:

```matlab
out = run_s11_dlr_validation(struct( ...
    'write_outputs', false, ...
    'write_case_files', false, ...
    'fail_on_nominal', false));
```

The current managed case outputs are:

- `npcc_ny_lite_s11_dlr_pf_base.m` - retained unsolved nominal input;
- `npcc_ny_lite_s11_dlr_pf_solution.m` - solved nominal Q-limit PF result;
- `npcc_ny_lite_s11_dlr_summer_peak_q090_sensitivity.m`;
- `npcc_ny_lite_s11_dlr_summer_peak_q110_sensitivity.m`.

`npcc_ny_lite_s11_dlr_winter_validation.m` and
`npcc_ny_lite_s11_dlr_high_total_east_validation.m` are intentionally absent
because S2 and S5 fail mandatory gates. Their Q-sensitivity files are absent for
the same reason.

The direct builder defaults to `write_cases=false` and can write only explicitly
named `candidate_unvalidated` files when requested. Managed benchmark filenames
are owned by the full validator, which stages, reloads, numerically compares, and
Q-limit-PF tests each case before publication. Plain MATPOWER case functions do
not retain arbitrary `userdata`; the CSV ledger and this README carry scenario
status and provenance. S3 shoulder light load remains excluded and is not built.

## Mandatory gates

The gate ledger records:

- standard and Q-limit-enforced AC PF success;
- zero P/Q restoration slack;
- no BUS VMIN/VMAX or online generator P/Q violations;
- no overload on a trusted static-limit branch;
- final reference pickup strictly below 1 MW;
- calibrated-interface MAE at most 100 MW, maximum residual at most 200 MW,
  and absolute signed bias at most 50 MW;
- no generic placeholder internal Q limits and no unrestricted external Q;
- no regulating bus outside the seven source-backed candidates and an exact
  match between the PF reference and mapped operational reference;
- 49 buses, 83 branches, and one model branch for each of five physical
  circuits;
- absolute zonal redispatch at most 10% of NY load and at most 3000 MW; and
- 2019 selected-circuit current, active-loss, and corrected net-network-Q
  errors each at most 15%.

The preferred but non-blocking targets are predominantly 0.95-1.05 pu internal
voltages, interface MAE below 75 MW, direct current errors below 10%, and fewer
than 20% of regulating groups at Q limits. Q-saturation and PV-to-PQ conversion
counts are always reported.

## Branch-current and DLR scope

`s11_branch_current_report.csv` contains PF, QF, PT, QT, from-end current,
to-end current, series current, terminal voltage, branch classification, and
physical-circuit identity. Terminal current uses three-phase apparent power and
line-line RMS voltage.

Only rows explicitly classified as `physical_circuit` and carrying a physical
circuit ID have line currents suitable for later conductor mapping. Currents on
`aggregate_equivalent` and `transformer_or_boundary_equivalent` rows are
electrical diagnostics only.

Conductor types, conductor ampacities, thermal parameters, weather, route
segmentation, sag/clearance, terminal-equipment ratings, and dynamic ampacity
are not included. A branch `RATE_A` value is not automatically a DLR limit or a
conductor ampacity.

S11 is suitable for fast algorithm tests and reduced-model diagnostics only.
It is not the promoted NPCC DLR testbed, a utility operating model, or support
for utility operating, facility-rating, reliability, or real-time dispatch
claims.

## Validation outputs

- `s11_interface_validation.csv` - targets, final flows, residuals, eligibility,
  and aggregate interface gates;
- `s11_voltage_q_branch_validation.csv` - mandatory and preferred gate ledger;
- `s11_branch_current_report.csv` - branch powers, currents, classification,
  and interpretation flags;
- `s11_physical_circuit_map.csv` - one-row-per-branch circuit provenance;
- `s11_dispatch_and_loss_summary.csv` - status, dispatch, losses, Q status, and
  inclusion decision;
- `s11_2019_same_snapshot_benchmark.csv` - source/reduced structural benchmark;
- `nyiso_interface_branch_map.csv` - explicit interface operators and mapping
  confidence.
