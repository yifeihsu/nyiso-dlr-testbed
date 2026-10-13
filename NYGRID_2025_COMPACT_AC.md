# Compact 148-bus AC model and recovered-current validation

The delivered model solves AC power flow on **148 retained buses** and recovers all detailed bus voltages and original branch currents algebraically. It eliminates all 118 pre-Dover or 119 post-Dover passive interior nodes. No additional node is necessary for the current fixed-control model. No AC OPF, parameter fitting or profile correction was performed.

The compact model is numerically equivalent to the detailed AC model on the validated paired solutions. It inherits that model's limitations: its source profiles do not yet produce operating-limit-qualified states, its bus load distribution is assumed within each NYISO zone, and several interface-flow errors remain substantial. Reduction accuracy and physical calibration are separate conclusions.

## Model and retained-node boundary

The original 148 IDs are retained in their registered order. All original loads, generators, converter terminals and controlled voltages are already on these buses. The removed states comprise 43 restored station/terminal nodes, 75 numerical section nodes, and the later fixed-tap Dover auxiliary node. They carry no prescribed P/Q injection or independent voltage control in this model. Fixed shunts remain in the admittance equations and do not require a separate retained voltage state. The [bus retention ledger](output/nygrid_2025_compact_ac/independent/bus_retention_ledger.json) records every bus name, source lineage and retention reason in all four dated states.

| Dated topology | Example hour | Detailed buses | Retained buses | Eliminated buses | Additional required buses |
| --- | --- | --- | --- | --- | --- |
| refined_2025_pre_may_case | 1 | 266 | 148 | 118 | 0 |
| refined_2025_may21_case | 3360 | 266 | 148 | 118 | 0 |
| refined_2025_may30_case | 3576 | 266 | 148 | 118 | 0 |
| refined_2025_case | 8472 | 267 | 148 | 119 | 0 |

If a future case puts a load, generator, DC terminal or PV/reference control on an interior node, the builder retains that node automatically. The 148 buses are the requested external interface, not a proof of a globally minimum possible network.

For retained voltages `Vk` and passive interior voltages `Ve`, the implemented identity is:

```text
0 = Yek Vk + Yee Ve
Ve = -(Yee \ Yek) Vk = K Vk
Yred = Ykk + Yke K
Vfull = L Vk
If = Yf L Vk;  It = Yt L Vk
```

The complex network includes resistance, charging, shunts, off-nominal taps and phase shifts before elimination. Complex, non-symmetric terms are retained without magnitude pruning. The block equations above establish the reduction and voltage recovery for this passive interior. Checks cover interior connectivity, conditioning, elimination identities and the Hermitian real-power dissipation screen. The nonlinear solve uses [MATPOWER's Newton power-flow kernel](https://matpower.org/doc/ref-manual/legacy/functions/newtonpf.html), with its DC-line conversion and legacy generator/Q-limit policy.

This is a **complex-admittance matrix model**, not a fabricated physical branch case. Use its dedicated wrapper. Reduced matrix couplings must not be assigned conductor ratings or summed as physical NYISO flowgates. The model stores full branch metadata for reconstruction while solving only retained bus states. [Model contract](output/nygrid_2025_compact_ac/MODEL_CONTRACT.json), [fixed-hour matrix models](output/nygrid_2025_compact_ac/models/model_exports.json), and [independent mathematical review](output/nygrid_2025_compact_ac/independent/kron_feasibility_review.json) document the boundary.

## Fresh paired ACPF and recovery evidence

Eight fresh detailed/compact pairs cover the original seven diagnostic hours and the May 21 topology transition. All eight converge and pass full-network KCL, input-profile preservation and recovery checks. The maximum paired complex-voltage difference is 1.274e-12 pu and the maximum paired physical-branch current difference is 2.805e-09 A. A separate primitive-branch calculation validates current reconstruction without using the production reduction operators.

The annual run attempts all 8,651 source-qualified hours on the original 8,760-hour axis. Compact ACPF qualifies 8,494 hours under the equation/profile gates; 157 attempted hours do not qualify. The primary comparison retains 8,494 paired hours from the frozen detailed baseline. Additional compact successes: 0; lost detailed successes: 0. The 109 source-excluded hours remain marked and are not silently simulated or filled. Numerical failure does not prove that a physical solution is impossible.

Across that complete paired cohort, the maximum complex-voltage difference is 6.69681e-12 pu and the maximum original-branch current difference is 1.47927e-08 A. The runner's acceptance thresholds are 1e-7 pu for voltage, 1e-4 MW/MVAr for power components and 1e-3 A for current; these thresholds are independent of public-interface fitting errors.

Maximum compact-versus-frozen-detailed discrepancies on the paired cohort:

| Quantity | Maximum absolute difference | Units | Compared values |
| --- | --- | --- | --- |
| VM | 3.13682e-12 | pu | 2,259,691 |
| VA_phase_gauge_aligned | 3.45704e-10 | degree | 2,259,691 |
| PF | 5.10909e-09 | model_MW | 4,120,451 |
| QF | 1.06775e-08 | model_MVAr | 4,120,451 |
| PT | 4.72926e-09 | model_MW | 4,120,451 |
| QT | 1.06945e-08 | model_MVAr | 4,120,451 |
| Ifrom | 1.41108e-08 | A | 4,120,451 |
| Ito | 1.47927e-08 | A | 4,120,451 |
| Iseries | 1.45067e-08 | A | 4,120,451 |
| bus_PG | 3.65139e-09 | model_MW | 2,259,691 |
| bus_QG | 1.06947e-08 | model_MVAr | 2,259,691 |

Angle differences use an explicitly common reference gauge. Currents are compared on original branch keys and active masks, including the appropriate dated topology. Terminal-current bases use the corresponding endpoint kV; series current excludes charging and uses the receiving-side winding base on transformer rows. On equal-voltage overhead conductor sections it is the current used for Joule heating. Currents are amperes on the original 100-MVA-base synthetic model and are **never divided by gamma**.

The default paired policy has reactive-limit enforcement disabled, matching the frozen detailed run. In the separate seven-hour mode-1 comparison, both models converge on 5 hours and fail on the same 2 hours. Every converged pair matches; failed iterates are not treated as equivalent solutions. Q/converter-reactive bounds pass at those converged points, while voltage and slack active-power bounds still fail. This is a control-response validation, not a refit of the default annual results. Mode 2 also matched at hour 8508 before the performance-only edits; that explicitly retained earlier test required 769 control iterations.

Source and operator fingerprints reject stale cached reductions after input, tap, shunt, resistance, status, mapping or recovery-operator edits. Rebuild after each physical `R(T)` update in an electrothermal iteration. The compact implementation does not run a full-network Newton solver internally.

Evidence: [fresh paired cases](output/nygrid_2025_compact_ac/validation/representative_pairs/representative_pair_receipt.json), [independent saved-point recovery](output/nygrid_2025_compact_ac/validation/independent_reference_recovery.json), [annual replay](output/nygrid_2025_compact_ac/validation/annual_compact_PF_receipt.json), [independent annual current/KCL review](output/nygrid_2025_compact_ac/independent/annual_arrays_independent_review.json), [reactive-limit pairs](output/nygrid_2025_compact_ac/validation/Q_limit_pairs/Q_limit_pair_receipt.json), [all paired error statistics](output/nygrid_2025_compact_ac/alignment/paired_recovery_errors.csv), and [core/control/guard review](output/nygrid_2025_compact_ac/independent/compact_core_review.json).

## NYISO load and interface alignment

All 96,360 hour-zone load values in the existing 11-zone, 8,760-hour source mapping reaggregate to public NYISO measured load after the original aggregate scale conversion; the previous audit's maximum difference is 9.095e-13 MW. Compact recovery preserves input PD and QD exactly on the evaluated hours, with maximum source differences 0 MW and 0 MVAr. This is a construction identity, not an independent forecast or validation of within-zone bus allocation.

The within-zone shares remain static, including the equal split between buses 81 and 82 in Zone J. External-area demand still uses historical bus allocation and the NY statewide time shape. Native generator profiles are bounded source-prior reconstructions rather than observed unit dispatch. NYISO measured grid load is net of behind-the-meter solar and demand response; it is not gross end-use demand. These inherited source assumptions are documented in the [profile source audit](output/nygrid_2025_acpf_profile_audit/alignment/profile_alignment_summary.json).

The interface comparison uses recovered original branch terminals with the previously sealed membership, signs, UTC hours, scale and dated masks. No reduced matrix edge flows are used. The seven internal-interface comparison series are not used to initialize, tune or fit the compact solver; the prescribed boundary schedules retain their documented public-data sources. WAPE is `100 * sum(abs(model-public)) / sum(abs(public))`. On the **same 8,494-hour paired cohort**, using the inherited signed literal-from convention:

| Interface | Detailed WAPE | Compact WAPE | Compact MAE, public MW |
| --- | --- | --- | --- |
| DYSINGER EAST | 38.8581% | 38.8581% | 328.951 |
| WEST CENTRAL | 59.8587% | 59.8587% | 330.462 |
| TOTAL EAST | 15.6919% | 15.6919% | 496.302 |
| MOSES SOUTH | 22.5858% | 22.5858% | 120.701 |
| CENTRAL EAST - VC | 45.0359% | 45.0359% | 754.962 |
| UPNY CONED | 7.6535% | 7.6535% | 228.524 |
| SPR/DUN-SOUTH | 9.0635% | 9.0635% | 167.237 |

The compact model preserves the detailed model's alignment; it does not improve those public errors. The source-side and target-side terminal conventions are also exported as separate diagnostics. They are different metering definitions, not a confidence interval. Physical P32 meter membership and the original `Flow(MWH)` field's interpretation as hourly average MW remain uncertified. Only aggregate MW is divided by the frozen gamma=0.30012075175285535; currents are not rescaled.

Evidence: [comparison contract sealed before results](output/nygrid_2025_compact_ac/alignment/comparison_contract.json), [scoring receipt](output/nygrid_2025_compact_ac/alignment/scoring_receipt.json), [annual/monthly metrics and terminal conventions](output/nygrid_2025_compact_ac/alignment/public_interface_metrics.csv), and [explicit hour cohorts](output/nygrid_2025_compact_ac/alignment/comparison_cohort.csv).

## Remaining physical qualification

**0 of the 8,494 compact equation/profile-qualified hours pass the inherited joint voltage/generator/converter assumption gate.** In the default solved cohort, voltage ranges from 0.854424 to 1.120060 pu. The original slack's active-power adjustment ranges from 143.984 to 869.314 MW to balance the AC losses omitted from the supplied lossless dispatch balance. Demand, other generators' active powers and the six transfer active-power targets remain fixed under the default policy.

These numerical currents are suitable for comparing the compact model with the detailed synthetic model. They are not measured NYISO line currents or proof that the supplied operating state satisfies real equipment capabilities. Generator Q/S capabilities are engineering assumptions, and the standard PV-converter behavior can violate the declared zero-Q transfer contract. Thermal overload is reported separately from PF convergence.

The inherited cable classification issues also remain: current overhead-labelled rows 300, 309, 310 and 386 conflict with source-documented underground/submarine corridors or proxy attachments. The 65 unresolved mixed-device equivalent rows have no verified internal conductor inventory. Compact recovery does not establish overhead DLR eligibility for them. Refer to the [asset/structure audit](output/nygrid_2025_acpf_profile_audit/structure/structure_audit.json) before assigning thermal physics.

## Use and reproduce

MATLAB and MATPOWER 8.1 must already be installed and on the path.

```matlab
cd('C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems');
addpath('System Matpower Format');
[r, audit, recovered] = run_nygrid_2025_compact_acpf(8508);
assert(r.success && audit.reduction_and_equation_gate ...
    && audit.P_profile_preservation_gate);
assert(size(r.bus,1) == 148);
Iseries_A = r.recovered_line_current_A(:,3);
% Iseries_A(j) corresponds to recovered.branch(j,:), not a Yred coupling.
```

Check `audit.VQ_and_generator_assumption_gate` separately; it is false for this unchanged operating case. `audit.passed` additionally contains inherited equipment checks and is not a reduction-equivalence verdict. A saved example can be loaded with `load('output/nygrid_2025_compact_ac/models/compact_ac_h8508.mat','model')` and passed as the wrapper's first argument.

The [implementation README](scripts/nygrid_2025_compact_ac/README.md) explains input changes, current bases and solver scope. [Public constructor](System%20Matpower%20Format/npcc_nygrid_2025_compact_ac.m) and [PF wrapper](System%20Matpower%20Format/run_nygrid_2025_compact_acpf.m) are the supported entry points. Validation scripts are under `scripts/nygrid_2025_compact_ac/validation`; source alignment scripts are under `scripts/nygrid_2025_compact_ac/alignment`.

Verify the delivered bytes without rerunning the simulations:

```powershell
python scripts/nygrid_2025_compact_ac/finalize_delivery.py --verify
```

Rerunning numerical scripts changes timestamped receipts and MAT-file bytes; rebuild the report, repeat the final review and reseal the manifest for a new run. The [delivery manifest](output/nygrid_2025_compact_ac/DELIVERY_MANIFEST.json) binds the implementation and evidence. It also verifies that all detailed model and prior audit files are byte-identical to baseline commit `3d2d3104879815180b82804861788dd132aed729`. Unrelated working-tree changes are outside this delivery.
