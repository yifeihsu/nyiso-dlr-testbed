# Whole-system synthetic AC model and conductor-based DLR

**ACPF can run, and a separate whole-system AC engineering case is now implemented.** The earlier DC case already converged under Newton ACPF, but its missing cost data, zero reactive-limit placeholders and lossless dispatch prevented treating that result as bounded AC operation. The new case supplies explicit AC parameters, capability assumptions, equipment limits and conductor-current constraints. It retains the existing power scale, as requested, and interprets currents directly in this synthetic system without dividing by gamma.

The numerical qualification has a precise boundary: **four of seven preselected electrical snapshots pass bounded ACOPF and fresh ACPF replay. Four of eight whole-network weather/current-constrained snapshots pass.** The other attempted operating points remain failed qualifications; they are retained in the results. This is a usable synthetic AC/DLR research case with identified feasible operating points, not a demonstrated full-year historical AC replay or an as-built NYISO asset model.

## Direct answer about the earlier case

Fresh unchanged-input tests used hours 4000 and 8508 on both the 148-bus DC reduction and the unreduced 191/192-bus references. Newton ACPF converged in four iterations. It supplied approximately 232–239 MW of missing losses through the slack and violated real-generator reactive bounds by up to about 614 MVAr. The fixed-transfer terminal reactive bounds were also violated. All four direct ACOPF attempts stopped because the DC loader had no `gencost` field.

Thus, numerical ACPF convergence was already possible. It did not establish an operating point satisfying P/Q, voltage, equipment and conductor limits. The [initial diagnostic](output/nygrid_2025_ac_system/ac_validation/initial_diagnostic/current_ac_diagnostic.json) and [transfer-Q check](output/nygrid_2025_ac_system/ac_validation/initial_diagnostic/transfer_Q_limit_check.json) preserve that distinction.

The new AC constructor is [npcc_nygrid_2025_ac.m](System%20Matpower%20Format/npcc_nygrid_2025_ac.m). It uses the unreduced network. The 148-bus Schur representation remains a DC artifact and is not reused as a physical AC conductor network.

## Branch parameters and their physical interpretation

The [complete branch assignment ledger](output/nygrid_2025_ac_system/branches/branch_assignments.csv) covers all 413 reference records, including 339 records active in the source topology variants and 74 inactive provenance records. Runtime status also preserves the existing branch-211 controlled-transfer substitution. Every active electrical branch has finite positive R and X, a declared class and finite equipment assumptions. Source values and changes remain inspectable.

| Reference-model class | Records | Treatment in the AC study |
|---|---:|---|
| Overhead corridors | 186 | 187 conductor sections before numerical subdivision; explicit catalog, length, integer circuits, bundle count, geometry, R(T), X and B |
| Cable/urban cable equivalents | 40 | Explicit synthetic copper/XLPE equivalents and static current limits; excluded from the overhead heat balance |
| Transformer-compatible station paths | 38 | Same-station labels and zero line charging; finite engineering transformer assumptions, not verified nameplates |
| Composite voltage-changing equivalents | 65 | Regional or mixed line/transformer equivalents; finite voltage-class terminal envelopes, with unresolved physical interiors |
| PAR, station-reactance and accounting links | 10 | Separate equipment models and limits |
| Inactive provenance | 74 | Retained; not silently promoted to active physical assets |

For the 186 overhead corridors, **128 retain their inherited R/X exactly** and **58 receive explicit engineering replacements** where the inherited values cannot support a plausible conductor/geometry realization. All overhead B values come from the selected geometry. For cables, 37 retain inherited R/X and three use route-anchored replacements. These are versioned model changes; the earlier cases and source records are unchanged.

The [overhead segment ledger](output/nygrid_2025_ac_system/branches/thermal_segments.csv), [cable segment ledger](output/nygrid_2025_ac_system/branches/cable_segments.csv), and [R/X replacement ledger](output/nygrid_2025_ac_system/branches/explicit_R_X_replacements.csv) provide the actual values. The [14-conductor thermal catalog](output/nygrid_2025_ac_system/engineering/thermal_conductors.csv) uses manufacturer AC resistance points, dimensions and GMR, with declared heat-capacity and surface assumptions. An inferred equivalent length or conductor match does not identify installed equipment uniquely.

Circuit multiplicity and bundle multiplicity are separate integers. In an identical parallel-circuit model, length and circuit count cancel from X/R; adding circuits cannot repair an impossible X/R ratio. The builder therefore checks conductor, bundle geometry and phase spacing before selecting circuit count and length. It does not read dispatch results or internal interface errors. The basic identities are:

`R_eq(T) = R_sub(T) * length / (parallel_circuits * bundle_count)`

`X_eq = omega * L_per_length * length / parallel_circuits`

`B_eq = parallel_circuits * omega * C_per_length * length`

The 65 composite equivalents deserve particular caution. A voltage change excludes a branch from direct overhead-conductor heating; it does not establish that its entire X is transformer leakage. Using that total X to infer a transformer nameplate produced misleadingly small capacities. Their revised limits use the declared voltage-class terminal-current policy independently of solved flows. Their internal physical lines remain undecomposed and are not covered by the overhead DLR equations. Whole-system operation here means the complete synthetic network and all its explicitly modeled overhead corridors, not every physical line hidden inside regional equivalents.

## AC line sections and reactive equipment

The final case has **266 buses and 485 branch records before Dover's full-service boundary**, and **267 buses and 488 records afterward**. All original buses remain. The additional 75 buses are zero-injection numerical points along 44 overhead corridors and two cable corridors; they are not claimed to be new substations.

Overhead sections are at most 100 km. Two 40-km 345-kV cable equivalents are split because their single-pi approximation exceeded the declared accuracy screen. Independent comparison against exact distributed-line ABCD constants reduces the worst overhead error from 12.742% to **0.2713%**, with maximum no-load voltage error **0.000797 pu**. See the [sectioning accuracy assessment](output/nygrid_2025_ac_system/engineering/line_segmentation_accuracy.json).

The [section and reactor plan](output/nygrid_2025_ac_system/branches/section_and_reactor_plan.csv) preserves total corridor R/X/B and adds separate fixed shunt reactors at original terminal buses. The selected fraction is 75% of nominal charging, split equally between the two ends. The [Oncor/SEL reference](output/nygrid_2025_ac_system/engineering/sources/SEL_Oncor_2013_shunt_reactors.pdf), page 4, describes a common 70–80% planning range. The chosen midpoint and selectors are study assumptions: overhead length above 120 miles, or cable nominal charging of at least 10 MVAr. Applying this rule to the cable equivalents is an explicit planning extension, not a claim about installed reactors.

The design selects 16 overhead and 19 cable corridors. Actual reactor participation follows each dated corridor status; pre-May has 34 active selected corridors and about 3,837.29 MVAr at 1 pu, while the later topology has 35 and about 3,862.11 MVAr. Absorption varies with voltage squared. Original bus shunts are preserved and reactor additions are separately recorded. No generator-Q residual was used to size these reactors, and branch charging was not erased to make a solver converge.

The MATLAB runtime and independent Python construction agree exactly across four topology states. An outage fixture removes the affected line sections and its associated reactor rather than leaving disconnected artificial buses or energized compensation behind. [Sectioned construction receipt](output/nygrid_2025_ac_system/branches/sectioned_design_receipt.json), [MATLAB runtime validation](output/nygrid_2025_ac_system/branches/sectioned_matlab_runtime_validation.json), and [independent review](output/nygrid_2025_ac_system/engineering/sectioned_design_independent_review.json).

## Operating assumptions required for AC

The [generator capability policy](output/nygrid_2025_ac_system/ac_validation/generator_capability_policy.json) completes the numerical AC data without claiming measured machine capability curves:

- Original hourly active-power bounds, statuses, P/Q loads, external generator P settings and all six prescribed transfers are preserved. Bounded native redispatch supplies AC losses.
- Admitted native generators use finite Q boxes derived from their hourly admitted capability at a declared 0.95 power factor. A status-zero row supplies no Q. Admission status is not verified unit commitment.
- The 28 external import rows are regional boundary equivalents. Their unchanged finite apparent-power proxies derive from the parent model's finite active-capacity bounds. At fixed P, Q is bounded by the corresponding apparent-power-circle slice. They are not treated as individual synchronous machines with an invented fixed power-factor restriction.
- Bus voltage bounds are 0.95–1.05 pu. Transformer/PAR and other equipment limits remain finite. Genuine installed nameplates are not inferred merely from an aggregate branch X.
- The objective penalizes deviation from the DC generation prior and reactive use. It is a declared research objective, not production cost or market-price calibration.

Preserving external generator P and the six controlled transfers does not make each regional net AC interchange identical to the earlier lossless DC target: AC losses change delivered net exchange. P34 unit, timestamp and historical-sign qualifications also remain in the inherited control provenance. No parameters or interface expressions were fitted to P32 observations.

## Whole-network DLR implementation

[run_nygrid_2025_ac_dlr.m](System%20Matpower%20Format/run_nygrid_2025_ac_dlr.m) attaches weather-dependent current limits to every active modeled overhead section. At the tested pre/post-Dover points, this means 257 or 258 overhead electrical branches and 257 or 259 conductor segments, respectively. The 40–42 active cable sections, depending on dated topology, retain static engineering current limits.

There are distinct constraints for:

1. Overhead series-conductor ampacity, excluding lumped charging from the Joule-loss calculation.
2. A conductor-current envelope at both ends of each numerical section, including charging.
3. Hardware ampere limits at original endpoints, evaluated at the solved voltage; numerical interior buses do not acquire fictitious hardware.
4. Cable static ampere limits and separate non-overhead equipment MVA limits.

A nominal-kV MVA proxy alone would allow excessive amperes when voltage falls. The new terminal constraints therefore use the actual AC terminal current. Parallel and bundled conductors use per-subconductor current, with no gamma conversion. The sum of conductor three-phase I-squared-R heating is checked against the AC section's real-power loss.

These snapshots use **fixed reference resistance at 75 C for ACSR and 95 C for ACSS**, with steady-state weather ampacity evaluated at the declared temperature cap. They do not solve a transient temperature trajectory or the steady electrothermal temperature fixed point. Section endpoints provide an additional current envelope; an exact continuous along-route thermal maximum is not certified. Mechanical clearance, actual route weather, installed surface condition and mutual/bundle shielding are not validated by this study. Cold resistance extrapolation below the supplied manufacturer range is rejected.

## Fresh numerical results

Seven electrical snapshots were selected by season, load level and topology, before selecting successful results. Hours **2630, 8508, 8471 and 8472** pass bounded ACOPF and fresh Newton ACPF replay. Hours **523, 4000 and 4194** did not produce a qualified bounded solution; two additional starts at unchanged parameters and constraints did not qualify them either. These are failed numerical qualifications, not proofs of global infeasibility. All attempted states remain in the [electrical results](output/nygrid_2025_ac_system/ac_validation/electrical_final/electrical_validation.json).

The weather/current-constrained comparison keeps all eight attempts:

| Hour | Controlled weather scenario | ACOPF and all audited limits | AC real loss, MW | Deviation penalty |
|---:|---|---|---:|---:|
| 2630 | 25 C, 0.6096 m/s perpendicular wind | Pass | 171.536 | 59.905 |
| 2630 | 25 C, 2.0 m/s perpendicular wind | Pass | 181.330 | 38.522 |
| 4000 | Both wind scenarios | Failed qualification | — | — |
| 4194 | Both wind scenarios | Failed qualification | — | — |
| 8508 | 25 C, 0.6096 m/s perpendicular wind | Pass | 226.617 | 18.237 |
| 8508 | 25 C, 2.0 m/s perpendicular wind | Pass | 236.077 | 10.811 |

Both scenarios use 1,000 W/m2 irradiance and 101,325 Pa. They are uniform effective-weather counterfactuals, not observed weather for those dates. Increased wind permits dispatch closer to the prescribed generation prior; the objective decreases while losses rise, because the objective is not loss minimization. These numbers are not monetary savings or estimated historical DLR benefits.

For the four successful current-constrained points, maximum independently checked P/Q nodal residuals are approximately **6.50e-10 MW / 5.72e-9 MVAr**. Maximum overhead electrical-loss versus conductor-Joule discrepancy is **2.77e-11 MW**. Generator, voltage, apparatus, cable, conductor and prescribed-transfer checks pass. See the [eight-row snapshot table](output/nygrid_2025_ac_system/thermal/whole_system_snapshot_results.csv) and [whole-system result record](output/nygrid_2025_ac_system/thermal/whole_system_validation.json).

Construction validation also includes 11 branch-physics tests, exact MATLAB/Python parity for four dated networks, and 21 thermal/current adapter tests, including analytic derivative checks and a small ACOPF with simultaneous independent current constraints. Passing a constructor or adapter test does not turn a failed operating snapshot into a feasible one.

## Use the case

```matlab
cd('C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems');
addpath('System Matpower Format');
addpath('scripts/nygrid_2025_ac_system/ac_validation');

% Default whole-network ampacity scenario at a validated post-Dover hour:
[result, audit] = run_nygrid_2025_ac_dlr(8508);
assert(audit.passed);

% Explicit electrical ACOPF, followed by a fresh bounded-audited ACPF replay:
mpc = npcc_nygrid_2025_ac(8508);
opt = mpoption('model','AC','opf.ac.solver','IPOPT','verbose',0,'out.all',0);
opt.ipopt.opts.bound_relax_factor = 0;
opt.ipopt.opts.tol = 1e-9;
[opf, success] = runopf(mpc, opt);
assert(success);
opf_audit = audit_ac_solution(mpc, opf);
assert(opf_audit.passed);
[pf, pf_audit] = replay_acpf_solution(mpc, opf);
assert(pf_audit.passed);
```

The ACPF helper uses the loss-balanced point and its voltage setpoints, perturbs the initial voltage state, and runs legacy Newton PF with Q-limit enforcement disabled during the solve. Every P/Q, voltage, equipment and transfer limit is checked afterward. The legacy backend avoids a detected MP-Core colocated-VAR redistribution problem in this case without editing the MATPOWER installation. Running plain ACPF from the lossless DC dispatch still does not guarantee bounded operation.

This delivery supports whole-network synthetic AC and steady-ampacity DLR method experiments at qualified operating points. A full-year weather-driven study still needs route/segment weather, an explicit treatment of failed operating hours, and validation appropriate to any stronger claims about temperature dynamics, security, unit commitment, economic benefits or actual NYISO equipment. The unresolved composite interiors remain a separate physical-resolution limitation.

The [machine-readable use contract](output/nygrid_2025_ac_system/AC_SYSTEM_CONTRACT.json) records the qualified and unqualified tested points. The [delivery manifest](output/nygrid_2025_ac_system/DELIVERY_MANIFEST.json) binds the new files and preserved earlier cases. Verify the packaged evidence without rerunning models:

```powershell
python scripts/nygrid_2025_ac_system/finalize_ac_system.py --verify
```
