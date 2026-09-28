# NPCC NY-Lite Adaptation

The latest preliminary extension is the [66-bus 2025 NY research baseline](../../COMPACT_NY_2025_DLR_METHODOLOGY.md), with matched NYISO demand, bounded interface-proxy calibration and 23 assumed overhead thermal realizations. Earlier cases below retain their historical scope.

This package is a **calibration scaffold**, not a validated NYISO planning case.
It retains the small NPCC network, maps retained New York buses to NYISO A-K
zones, supports zonal load/generation scenarios, and adds only selected
interface-oriented equivalents.

## Case entry points

- `npcc_original.m`: frozen source case.
- `npcc_ny_lite_v0_baseline.m`: source case plus zone metadata.
- `npcc_ny_lite_v1_zonal_load.m`: v0 plus explicit zonal-load allocation.
- `npcc_ny_lite_v2_topology.m`: v0 plus topology-only patch.
- `npcc_ny_lite_v3_composed_initial.m`: uncalibrated load + topology composition.
- `npcc_ny_lite_v3_calibrated.m`: guard that errors until calibration exists.

## Safe scenario sequence

```matlab
mpc = npcc_ny_lite_v0_baseline;

% Optional E/G/H equivalents at existing buses. Choose the control mode.
opts = struct('control_mode', 'fixed_pq', 'on_existing', 'skip');
[mpc, eq_report] = add_ny_equivalent_generators(mpc, [], opts);

% Apply one explicit A-K load scenario.
load_opts = struct('preserve_total_ny_load', true);
[mpc, load_report] = apply_nyiso_zonal_loads( ...
    mpc, 'S1_PERFORM_COMPATIBLE_PEAK', 1.0, load_opts);

% Apply matched zonal generation targets.
[mpc, gen_report] = apply_ny_zonal_generation( ...
    mpc, 'S1_PERFORM_COMPATIBLE_PEAK');

% Apply interchange through generator redispatch; method is explicit.
int_opts = struct('method', 'generator_redispatch');
[mpc, interchange_report] = apply_external_interchange( ...
    mpc, 'S1_PERFORM_COMPATIBLE_PEAK', int_opts);

% Put the real-power slack on an external balancing unit.
[mpc, ref_report] = set_scenario_reference_bus( ...
    mpc, EXTERNAL_GEN_INDEX, struct('selector_type', 'gen_idx'));

% Repair any remaining generator-limit violations, then balance losses.
[mpc, repair_report] = repair_generator_limit_violations(mpc, ...
    struct('protected_gen_idx', NY_FIXED_GEN_INDICES));
[mpc, balance_report] = balance_scenario_dispatch(mpc, ...
    struct('balance_gen_idx', EXTERNAL_BALANCE_GEN_INDICES, ...
           'expected_losses_mw', EXPECTED_LOSSES_MW));

% Add the one-line default topology seed.
[mpc, added] = add_ny_lite_tielines(mpc, 'core');

% Record identity before runpf.
structural_id = ny_lite_case_fingerprint(mpc);
operating_id = ny_lite_operating_point_fingerprint(mpc);
```

`balanced_injection_test` in `apply_external_interchange` is intended only for
PTDF/transfer screening because it changes `PD/QD`. Use `generator_redispatch`
for matched operating scenarios so native zonal loads remain unchanged.

## Equivalent-generator control modes

- `fixed_pq`: retains the bus as PQ; `PG/QG` are fixed injections in power flow.
- `voltage_regulating_pv`: changes the bus to PV unless it is the reference bus.

The included equivalent-generator costs and capabilities are placeholders and
must be replaced before OPF or economic conclusions.

## Interface flow convention

`ny_lite_interface_definitions.m` identifies every in-service branch crossing
a reduced zone boundary and records the source-side metered end. The flow
calculator uses `PF` or `PT` explicitly. `ConEd_LIPA_total` aggregates the
I-K and J-K subpaths.


## Scaffold self-test

Run `run_ny_lite_scaffold_selftest` before calibration. It checks S0 Pd/Qd
invariance, H/I codes, equivalent-generator idempotence, the one-line core
profile, Gilboa-Leeds parameters, RATE_A/B/C, and both fingerprints.

## Audit files

- `baseline_npcc_snapshot_summary.csv` is a static source-case snapshot.
- `baseline_npcc_summary.csv` is created only by `run_npcc_baseline_audit.m`.

See `FIXES_APPLIED.md` for the hardening changes in this rebuild.
