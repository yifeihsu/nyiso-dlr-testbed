# NPCC-NY Lite Calibration Project Handoff

**Handoff date:** 2026-07-10  
**Recommended structural case:** `npcc_ny_lite_s7_seven_interface_perform_direct_candidate`  
**Current status:** the S7 network is the structural baseline; inherited capability
and voltage-control assumptions are not operationally certified.

## 1. Executive Summary

This project modifies the public NPCC MATPOWER case into a New-York-focused
reduced model that can reproduce scaled public NYISO zonal loads, external
interchange schedules, and seven public internal interface-flow patterns.

The final structural case has:

```text
143 buses
246 branches
62 generators
100 MVA base
```

The recommended S7 network uses direct PERFORM parameters for the three added
corridors with explicit support in the PERFORM dataset. It is a
**network-structural baseline with inherited S4 capability assumptions**, not a
certified operating case. Scenario validation is performed on a 49-bus NY
boundary-equivalent model so that each public external interchange schedule can
be held fixed in an ordinary power flow.

Main result:

```text
Current S4 seven-interface objective       0.285577
Direct-PERFORM S7 objective                0.233303
Improvement                                18.3%
Held-out objective improvement             30.7%
Standard PF convergence                    6/6
Q-limit-enforced PF convergence            5/6
S8.1 inherited 0.8-cap minimum eta        2.7013
S9a free-voltage temporary Q support       0 MVAr
S9a full S1-reference status               not demonstrated
S9b last hard-feasible S1 weight           0.8075
S9b first restored S1 weight               0.8100
S9b refined/reference audit solves         182/182
```

The model is appropriate for continued reduced-network calibration research.
It is not yet appropriate for claiming fully feasible NYISO operations or
detailed circuit-level equivalence.

## 2. Software and Reproduction

Final verification used:

```text
MATLAB R2026a Update 3, 26.1.0.3276743
MATPOWER 8.1
MATLAB Optimization Toolbox
IPOPT available through MATPOWER
Windows / PowerShell host
```

From the package root, run:

```matlab
outputs = run_handoff_reproduction;
```

This command:

1. rebuilds the six public load and seven-interface target scenarios from the
   included local NYISO cache;
2. rebuilds fixed interface objective scales;
3. reruns S6 zonal net-injection estimation and standard/Q-diagnostic PFs;
4. compares current ties with direct PERFORM ties;
5. reloads and verifies the recommended S7 case dimensions.

To rerun the iterative AC injection-closure diagnostic:

```matlab
outputs = run_handoff_reproduction(struct( ...
    'run_s8_operational_closure', true));
```

This adds the six-scenario S8 operational re-estimation and takes roughly one
minute on the verified host. It does not promote S8 to the structural baseline.

To refresh S8.1, S9a, the default S9b restoration, and the refined
reference/continuation audit:

```matlab
outputs = run_handoff_reproduction(struct( ...
    'run_s8_1_capability_certificate', true, ...
    'run_s9a_q_support_diagnostic', true, ...
    'run_s9b_feasibility_restoration', true, ...
    'run_s9b_reference_audit', true));
```

These options first refresh the S8 prerequisite. They diagnose inherited
capability and control assumptions; none creates a promoted S9 operating case.

To rerun the broad tie calibration grid as well:

```matlab
outputs = run_handoff_reproduction(struct('run_full_calibration', true));
```

The broad calibration takes several minutes and creates 1,356 standard PF
results. Refinement and edge-audit result files are already included.

## 3. Directory Guide

| Path | Purpose |
|---|---|
| `System Matpower Format/` | MATPOWER cases and all NY-lite helpers/results |
| `System Matpower Format/NY_Lite/` | Calibration code, public targets, reports, diagnostics |
| `PERFORM/` | Higher-resolution NYISO-oriented PERFORM dataset |
| `ENLITEN-Grid-Econ-Data-main/` | Downloaded original ENLITEN NPCC/WECC source data |
| `output/perform_comparison/` | PERFORM extraction, zonal comparison, and corridor reports |
| `LATEST_MODEL_CONFIGURATION.csv` | Machine-readable current configuration |
| `run_handoff_reproduction.m` | One-command verification entry point |

## 4. Case Evolution

### 4.1 Original NPCC and S0

The source case is:

```text
System Matpower Format/npcc_original.m
```

It is numerically identical to:

```text
ENLITEN-Grid-Econ-Data-main/WECC and NPCC Systems/
System Matpower Format/NPCC.m
```

The S0 wrapper attaches NYISO A-K metadata but does not change the network:

```text
npcc_ny_lite_v0_baseline.m
140 buses, 233 branches, 48 generators
30,349.761 MW total system load
10,902.220 MW mapped New York load
```

S0/original `runpf` converges, but its embedded dispatch is not generator-limit
feasible. The original reference generator absorbs a multi-GW generation
deficit. Convergence and operating-limit feasibility must always be reported
separately.

### 4.2 S1: Feasible ACOPF Dispatch

`npcc_ny_lite_s1_acopf_feasible_uncalibrated.m` stores the first full-NPCC
ACOPF-feasible dispatch. It preserves the original 140/233/48 structure.

The saved feasibility report records:

```text
objective                 823,806.98 $/h
load                       30,349.76 MW
generation                 31,108.16 MW
losses                         758.39 MW
voltage range               0.900-1.100 pu
binding branches                       2
```

S1 is a feasible operating base, not an interface-calibrated NYISO scenario.

### 4.3 S2: Downstate Delivery Spine

Public NYISO load redistribution moved several GW toward G/J/K proxy areas.
The original coarse NPCC topology could not deliver this load under normal AC
constraints. `add_ny_downstate_delivery_spine.m` introduced three zero-load
345-kV transit buses:

```text
9001  KNICKERBOCKER   Zone G
9002  WOOD STREET     Zone H
9003  EAST GARDEN CITY Zone K
```

The added branch names are:

```text
GILBOA_LEEDS
PLEASANT_VLY_WOOD_STREET
WOOD_STREET_MILLWOOD
MILLWOOD_CE_UG_DELIVERY
BUCHANAN_CE_UG_DELIVERY
CE_UG_GOETHALS_DELIVERY
CE_UG_RAV_A3_DELIVERY
CE_UG_AK3_DELIVERY
CE_UG_EAST_GARDEN_CITY
EAST_GARDEN_CITY_NORTHPORT
GOETHALS_NORTHPORT_DELIVERY
LEEDS_KNICKERBOCKER
KNICKERBOCKER_PLEASANT_VLY
```

Only Gilboa-Leeds, Pleasant Valley-Wood Street, and Wood Street-Millwood have
direct PERFORM parameter support. The remaining lines are reduced engineering
proxies and remain less defensible.

### 4.4 S3: Zone J Active-Supply Equivalent

Topology alone improved but did not solve full public-load relocation. The
missing control was active-power capability in NYC/Zone J.

S3 added a bounded 3,000-MW Zone J aggregate equivalent:

| Proxy bus | Share | PMAX | Interpretation |
|---|---:|---:|---|
| RAV A-3 | 40% | 1,200 MW | Queens/Ravenswood/Astoria/East River aggregate |
| AK-3 | 30% | 900 MW | Staten Island/Arthur Kill aggregate |
| Goethals | 30% | 900 MW | NYC import/Gowanus-adjacent aggregate |

These are aggregate equivalents, not literal generators. They use
`q_abs_ratio = 0`, which is one reason the final model remains reactive-power
fragile.

### 4.5 S4: Zonal Capability and Participation Alignment

`npcc_ny_lite_s4_cost_calibration_candidate_v2.m` adds E/F/G/K capability
equivalents using 2025 NYISO Gold Book zonal capability as an aggregate prior:

```text
Zone E equivalents:   600 MW
Zone F equivalents: 1,600 MW
Zone G equivalents: 2,200 MW
Zone K equivalents: 1,800 MW
```

Other S4 settings:

```text
Zone J equivalent PMAX       3,000 MW
equivalent linear cost c1      180
equivalent quadratic cost c2  0.02
A/B/C cap factor              0.80
spine impedance multiplier    1.00
CE UG                         high-cost interface/voltage proxy
```

This produced the 143-bus, 246-branch, 62-generator structural base used by
S5-S7.

### 4.6 S5: PERFORM Generator Allocation Audit

PERFORM 2019 On-Peak V23 contains:

```text
1,576 buses
2,371 branches
615 generators
29,799.66 MW embedded load
625.94 MW solved losses
0.9732-1.0337 pu solved voltage range
```

`build_perform_npcc_generation_shift_keys.m` maps PERFORM plant geography onto
retained NPCC generator buses. The GSK is used only inside each zone; it does
not set zonal generation totals.

Applying the PERFORM GSK alone to earlier full-NPCC PFs did not materially
improve interface matching. This demonstrated that zonal net injections and
external interchange had to be aligned before line/GSK conclusions were valid.

### 4.7 S6: Public Loads, External Interchange, and Net Injections

S6 uses a NY boundary-equivalent PF formulation:

```text
49 NY buses
81 NY branches
35 internal generators
8 fixed external boundary equivalent generators
43 total generators after external equivalents
```

This reduction is necessary because standard PF cannot independently enforce
multiple public interchange schedules inside the intact meshed external NPCC
network. The full 143-bus case remains the structural source model.

### 4.8 S7: Seven Interfaces and Direct PERFORM Ties

The public interface set was expanded to:

```text
Dysinger East      A-B
West Central       B-C
Moses South        D-E
Central East       E-F
Total East         F-G
UPNY-ConEd         G-H
Dunwoodie South    I-J
```

Four scenarios train tie parameters; two are held out:

```text
Training: S1 summer, S2 winter, S4 high NYC/LI, S5 high Total East
Holdout:  S3 shoulder light load, S6 low Total East
```

The direct PERFORM candidate is recommended over the lower-training-error
fitted sensitivity because it has slightly better holdout, minimum-voltage,
and worst-residual behavior.

### 4.9 S8: Iterative AC Injection Closure

S8 does not change the structural case. It applies an operational re-estimation
experiment to the direct-PERFORM S7 network.

`derive_nyiso_zonal_net_injections_ac_iterative.m` starts from the constrained
DC estimate, measures AC losses, distributes the loss requirement by available
zonal headroom, forms finite-difference AC interface sensitivities with a
distributed participation vector, and applies bounded damped redispatch.

This closes the previous single-bus loss-balancing loop. Across the six public
scenarios, final reference adjustment is below 0.1 MW and the historical
interface objective improves from 0.233303 to 0.015310. This is an in-sample
operational score because all seven interface targets are used to infer the
same scenario's dispatch. It is not independent validation of transmission
parameters or interface definitions.

The S8 shoulder dispatch remains unacceptable: minimum voltage is 0.85457 pu,
the maximum Q violation is 1189.18 MVAr, Q-limit PF fails, and the West-Central
residual remains 416.00 MW with A/B generation essentially at PMAX. Direct S7
therefore remains the recommended structural baseline.

### 4.10 S8.1: Local Linear Capability-Envelope Certificate

S8.1 tests the shoulder West-Central target against A/B/C capability envelopes
of 0.8, 0.9, and 1.0 using the final S8 AC sensitivity matrix. The inherited
0.8 envelope has minimum normalized infeasibility `eta = 2.7013`; at least
272.58 MW of A/B/C relaxation is required to reach `eta <= 1`. Restoring the
1.0 envelope reaches linear compatibility (`eta = 0.9937`), but its nonlinear
AC recheck has minimum voltage 0.86538 pu, 998.76 MVAr maximum Q violation, and
failed Q-limit PF. Cap factor 1.0 is therefore not promoted.

The zonal movements exceed 1 GW in total absolute redispatch, so this is a
local linear certificate with nonlinear recheck, not a global nonlinear
infeasibility certificate.

No independent hour-specific 2025 unit availability table is present. Static
Gold Book capability is not relabeled as scenario availability; a template is
included for that future input.

### 4.11 S9a: Minimum-Q and Voltage-Control Diagnostic

S9a adds penalized positive/negative temporary Q-only devices for diagnosis and
tests both inherited and PERFORM-scaled zonal Q envelopes. With free OPF voltage
variables (`opf.use_vg = 0`), the shoulder case solves under normal voltage and
branch constraints with zero temporary Q support. As the S1/current generator
`VG` fields are progressively weighted, required support rises from 36.07 MVAr
at 0.80 to 833.27 MVAr at 0.90. These values are primarily S1 OPF-solved
voltage references, not independently sourced control schedules. Full-reference
enforcement has no
successful saved solution: IPOPT encountered an implementation exception and
MIPS did not converge, including in the no-rating diagnostic.

Zero temporary support means only that free voltages, broad internal Q ranges,
active redispatch, and present boundary-equivalent Q injections jointly find a
solution. The archived 1189-MVAr standard-PF violation is therefore not evidence
of a proven bulk reactive-capability shortage. The leading issue is inconsistent
or missing voltage-control detail: generator schedules, transformer taps,
shunts, reactors, and scenario-dependent control status.

### 4.12 S9b: Voltage-Reference and AC Restoration Audit

S9b now selects an explicit source-controlled reference set, uses
`opf.start = 2`, and attempts a hard ACOPF before invoking MATPOWER AC soft
limits. AC balance and active-power bounds remain hard. Internal Q limits,
voltage/reference-derived bounds, and branch apparent-power limits receive
penalized nonnegative slacks only after the hard solve is unsuccessful.

The original continuation reference is now labeled
`S1_OPF_SOLVED_REFERENCE`. All 48 S1 generator `VG` fields differ from original
NPCC because S1 saved an OPF solution obtained with `opf.use_vg = 0`; CE UG
changed from 1.020000 to 0.974721 pu. CE UG is explicitly classified as a
Zone-I interface/voltage-support proxy.

The S1 reference interval was refined to 0.0025 steps with increasing and
decreasing warm continuations, cold starts, and two perturbed starts. All paths
agree on the local bracket:

```text
highest hard-feasible S1 reference weight       0.8075
lowest nonzero-restoration S1 reference weight  0.8100
first slack                                     CE UG VMAX, 0.00002727 pu
```

Reference provenance materially changes the result. Coarse hard-feasibility
brackets are 0.75-0.80 for original NPCC, 0.80-0.825 for S1/current S7, and
0.90-1.00 for the provisional PERFORM zonal envelope. Therefore, no threshold
is interpreted as a real-system voltage-control limit.

The PERFORM PSS/E RAW source has now been parsed directly: all 649 generator
records retain `VS` and `IREG`; 417 online records map to NYISO A-K, one uses
remote regulation, and every online regulated bus resolves in the source bus
table. These source controls are archived, but the current 30-bus PERFORM
reference remains a low-confidence zonal aggregate because individual
generator-to-retained-control mappings have not yet been constructed.

All 182 refined/reference final solves return IPOPT status 0 with no exceptions;
the maximum independently evaluated AC balance residual is 0.001067 MVA. Full
dual/complementarity/KKT residuals are not exposed by the installed wrapper and
are reported as unavailable rather than inferred.

## 5. Public Load Construction

Public loads come from NYISO P-58C Integrated Real-Time Actual Load. For hour
`t`, the scale factor is:

```text
gamma(t) = 10,902.2197987 / NYISO_total_load(t)
```

Each zonal target is:

```text
L_target,z(t) = gamma(t) * L_NYISO,z(t)
```

Thus the A-K shares follow the public NYISO hour while total mapped NPCC NY
load remains 10,902.2197987 MW.

Bus allocation rules in `apply_nyiso_zonal_loads.m`:

1. retain original within-zone active-load proportions where original load
   exists;
2. otherwise use explicit proxy weights from `ny_bus_zone_map.csv`;
3. preserve original signed Q/P for moved load at an originally loaded bus;
4. use 0.97 default power factor for newly created proxy load;
5. preserve exact original Q when the active load is unchanged.

The six included public hours are listed in `nyiso_public_scenarios.csv` and
cover summer peak, winter peak, shoulder minimum, high NYC/LI, high Total East,
and low Total East conditions.

## 6. External Interchange Construction

External schedules come from NYISO P-32. Positive target flow means import into
New York. The same `gamma(t)` scales each public schedule.

Eight boundary equivalents represent HQ, ISO-NE, Ontario/IESO, and PJM paths at
retained buses 48, 37, 73, 54, 66, 67, 75, and 81.

Each boundary generator is nearly fixed in active power:

```text
PG   = target_flow_mw
PMIN = target_flow_mw - 0.001 MW
PMAX = target_flow_mw + 0.001 MW
```

External Q values are modeled with the limited-Q assumptions stored in
`ny_external_interface_targets.csv`; they are not public measured Q schedules.

## 7. Zonal Generation and Net-Injection Estimation

P-32 provides seven internal measurements, not enough to uniquely determine
eleven zonal generation values. S6/S7 therefore solve a constrained inverse
problem using the current reduced DC response and a weak PERFORM prior.

For each zone:

```text
N_native,z    = G_z - L_z
N_effective,z = G_z - L_z + I_external,z
```

The estimator solves:

```text
min_G  sum_m ((F_DC,m(G) - F_target,m) / S_m)^2
       + lambda * sum_z ((G_z - G_PERFORM,z) / S_z)^2

subject to
       sum_z G_z = sum_z L_z - sum_z I_external,z
       PMIN_z <= G_z <= PMAX_z
```

Settings:

```text
lambda / prior_weight = 0.05
balance zone          = J
DC sensitivity step   = 1 MW
solver                = lsqlin
```

After zonal totals are inferred, PERFORM GSK weights allocate generation to
NPCC buses. AC losses are absorbed by the Zone J reference generator during
PF, so actual Zone J generation differs from the lossless inferred target.

## 8. Interface Metering and Objective

`ny_lite_interface_definitions.m` finds every active NPCC branch crossing each
mapped zonal boundary and records the positive metered direction. PF flows are
summed by `ny_lite_interface_flows.m`.

The scoring objective is:

```text
J = sum_s sum_m ((F_model(s,m) - F_target(s,m)) / S_m)^2
```

`S_m` is a fixed per-interface scale derived from the median available scaled
P-32 limit, with a 500-MW floor. It is not an individual branch rating.

## 9. Recommended Tie Parameters

The recommended S7 structural case uses direct PERFORM values:

| Corridor | R pu | X pu | B pu | RATE_A MVA |
|---|---:|---:|---:|---:|
| Gilboa-Leeds | 0.001310 | 0.019970 | 0.51614 | 1216 |
| Pleasant Valley-Wood Street | 0.000405 | 0.006185 | 0.63943 | 2432 |
| Wood Street-Millwood | 0.000185 | 0.002815 | 0.29107 | 2432 |

The fitted sensitivity used multipliers `2.0 / 0.85 / 1.0` respectively. It
reduced the all-hour objective to 0.22842 but was not promoted because direct
PERFORM had better held-out and feasibility-oriented diagnostics.

## 10. Current Results

| Case | Training objective | Holdout objective | All-hour objective | Worst residual |
|---|---:|---:|---:|---:|
| Current S4 ties | 0.13566 | 0.14992 | 0.28558 | 572.6 MW |
| Direct PERFORM S7 | 0.12945 | 0.10385 | 0.23330 | 424.9 MW |
| Fitted sensitivity | 0.12435 | 0.10407 | 0.22842 | 435.5 MW |

Direct PERFORM improves all-hour normalized consistency by 18.3% and held-out
consistency by 30.7%.

Mean absolute residuals for the recommended case:

| Interface | MAE |
|---|---:|
| Dysinger East | 57.0 MW |
| West Central | 138.9 MW |
| Moses South | 26.8 MW |
| Central East | 104.4 MW |
| Total East | 142.1 MW |
| UPNY-ConEd | 259.8 MW |
| Dunwoodie South | 239.5 MW |

Operational closure diagnostic:

| Score | Objective | Mean absolute residual | Worst residual |
|---|---:|---:|---:|
| Initial DC estimate | 0.015599 | 36.41 MW | 354.89 MW |
| Frozen S6 dispatch on direct S7 | 0.233303 | 138.35 MW | 424.91 MW |
| S8 iterative AC dispatch | 0.015310 | 19.49 MW | 416.00 MW |

S8 reduces UPNY-ConEd MAE from 259.81 to 11.40 MW and Dunwoodie
South MAE from 239.47 to 2.20 MW. This confirms that loss and dispatch closure
have substantially more leverage than another three-corridor impedance sweep.
The remaining worst residual is the shoulder West-Central target.

## 11. Current Problems

### 11.1 Shoulder operating-point infeasibility

Standard PF converges for all six scenarios, but Q-limit-enforced PF fails for
the shoulder-light-load hour. In standard PF for that hour:

```text
Huntley Q violation       81.27 MVAr
CE UG Q violation        472.98 MVAr
AK-3 Q violation           6.07 MVAr
```

MATPOWER cannot retain a valid REF/PV set after enforcing these limits. S9a
shows that a free-voltage ACOPF can find a feasible Q/V point without temporary
support, but progressively weighting the current generator `VG` fields requires
up to 833.27 MVAr at `opf.use_vg = 0.90`. Those fields are primarily S1
OPF-solved voltage references. Full-reference feasibility was not
demonstrated: IPOPT encountered an exception and MIPS did not converge. The
unresolved problem is therefore voltage-control-state consistency, not a
certified 1189-MVAr system shortage or a proven physical setpoint infeasibility.

S9b supplies the missing numerical diagnostic. For the S1 solved-voltage
reference, hard feasibility is retained through 0.8075 and nonzero restoration
begins at 0.8100 across tested directions and starts. Different reference sets
produce materially different brackets. These values remain reference-, metric-,
and trajectory-dependent and are not a global infeasibility certificate.

### 11.2 Capability-envelope conflict

The shoulder West-Central target is linearly incompatible with the inherited
0.8 A/B/C participation envelope (`eta = 2.7013`). A minimum 272.58 MW A/B/C
relaxation reaches the reporting band, but restoring the full 1.0 envelope
worsens nonlinear voltage/Q feasibility. Scenario-specific available capability
cannot be tested until an independent hourly availability or commitment table
is supplied.

### 11.3 Remaining voltage violations

The direct PERFORM charging improves the worst standard-PF minimum voltage from
0.8037 to 0.9022 pu. Maximum voltage remains 1.1128 pu, and up to three buses
still exceed their 1.10-pu upper bounds.

### 11.4 Persistent branch overload

Branch 29, Niagara West-Huntley, overloads in every scenario. The largest
excess is 168.06 MVA in the shoulder case. The tie calibration did not remove
this western constraint.

### 11.5 Reference-generator loss balancing

The frozen S7 comparison places AC loss imbalance on one Zone J reference unit.
Reference adjustment ranges from roughly 146 to 589 MW and biases downstream
interface flows. S8 closes this mismatch with headroom-weighted loss allocation
and reduces final reference pickup below 0.1 MW. Frozen S7 remains the structural
topology score; S8 is the separate in-sample operational score.

### 11.6 Interface residuals remain material

The objective improves, but UPNY-ConEd and Dunwoodie South MAEs remain roughly
260 and 240 MW. These errors likely combine coarse topology, missing transformer
and phase-shifter controls, boundary Q assumptions, proxy GSK errors, and
uncalibrated added branches without direct PERFORM matches.

After S8 operational re-estimation, the dominant unresolved residual moves to
West-Central in the shoulder case at 416.0 MW. Zones A and B are both nearly at
their aggregate PMAX, so this mismatch cannot be removed by additional bounded
zonal redispatch under the current capability and proxy measurement assumptions.

### 11.7 In-sample injection estimation

The seven P-32 flows participate in estimating zonal injections and are then
used for AC consistency scoring. The tie calibration has two held-out hours,
but the zonal injection estimator itself is not independently validated against
observed zonal generation. Avoid claiming independent NYISO dispatch recovery.

### 11.8 Boundary-equivalent scope

Exact public external schedules are tested only after removing the external
NPCC mesh. The result is a NY boundary-equivalent operating study, not a full
NPCC interchange-feasibility certification. Reintroducing the full external
network requires an outer area-interchange controller, OPF constraints, phase
shifters, or another equivalent formulation.

## 12. Recommended Next Work

1. Map the extracted PERFORM `VS`/`IREG` records to retained control devices;
   then import transformer taps/phase shifts, shunts/reactors, deadbands, and
   scenario control status to replace the provisional zonal voltage envelope.
2. Obtain scenario-specific unit availability/commitment and rerun the S8.1
   capability envelope; do not substitute static Gold Book PMAX.
3. Map exact monitored branch/sign cutsets for all seven public interfaces.
4. Audit Niagara West-Huntley branch data and western transfer representation.
5. Validate inferred dispatch with leave-one-interface-out and independent
   seasonal hours or observed zonal-generation estimates.
6. Derive unsupported proxy corridors from a PERFORM Ward/Kron equivalent and
   retain only identifiable parameter combinations.
7. Do not perform another R/X/B multiplier search until the capability,
   measurement, and Q/V-control issues above are resolved.
8. Implement lexicographic S9c only after the voltage controls and exact
   interface measurement operators are source-backed; Stage 1 must include
   normalized interface residual slack before Stage 2 minimizes control motion.

## 13. High-Value Files

### Recommended case and reproduction

```text
System Matpower Format/npcc_ny_lite_s7_seven_interface_perform_direct_candidate.m
run_handoff_reproduction.m
LATEST_MODEL_CONFIGURATION.csv
```

### Public-data pipeline

```text
System Matpower Format/NY_Lite/build_nyiso_public_targets.m
System Matpower Format/NY_Lite/import_p58c_zonal_loads.m
System Matpower Format/NY_Lite/import_p32_interface_targets.m
System Matpower Format/NY_Lite/nyiso_public_interface_map.m
System Matpower Format/NY_Lite/nyiso_public_scenarios.csv
System Matpower Format/NY_Lite/ny_zonal_load_targets.csv
System Matpower Format/NY_Lite/ny_external_interface_targets.csv
System Matpower Format/NY_Lite/nyiso_public_interface_targets.csv
```

### Load, generation, and boundary application

```text
System Matpower Format/NY_Lite/apply_nyiso_zonal_loads.m
System Matpower Format/NY_Lite/derive_nyiso_zonal_net_injections.m
System Matpower Format/NY_Lite/derive_nyiso_zonal_net_injections_ac_iterative.m
System Matpower Format/NY_Lite/run_s8_iterative_ac_injection_closure.m
System Matpower Format/NY_Lite/build_perform_npcc_generation_shift_keys.m
System Matpower Format/NY_Lite/apply_perform_generation_allocation.m
System Matpower Format/NY_Lite/apply_nyiso_external_interface_injections.m
System Matpower Format/NY_Lite/build_ny_only_equivalent_case.m
```

### Topology and tie calibration

```text
System Matpower Format/NY_Lite/add_ny_downstate_delivery_spine.m
System Matpower Format/NY_Lite/add_s4_zonal_capability_equivalents.m
System Matpower Format/NY_Lite/apply_perform_tieline_calibration.m
System Matpower Format/NY_Lite/run_s7_seven_interface_perform_tieline_calibration.m
```

### Final reports

```text
System Matpower Format/NY_Lite/s7_seven_interface_perform_calibration_assessment.md
System Matpower Format/NY_Lite/s7_perform_direct_pf_results.csv
System Matpower Format/NY_Lite/s7_perform_direct_interface_residuals.csv
System Matpower Format/NY_Lite/s7_perform_direct_branch_parameters.csv
System Matpower Format/NY_Lite/s7_perform_direct_q_diagnostics.csv
System Matpower Format/NY_Lite/s7_interface_consistency_comparison.csv
System Matpower Format/NY_Lite/s8_iterative_ac_injection_closure_assessment.md
System Matpower Format/NY_Lite/s8_structural_vs_operational_summary.csv
System Matpower Format/NY_Lite/s8_interface_summary.csv
System Matpower Format/NY_Lite/s8_ac_iterative_pf_results.csv
System Matpower Format/NY_Lite/s8_1_capability_feasibility_assessment.md
System Matpower Format/NY_Lite/s8_1_capability_envelope_summary.csv
System Matpower Format/NY_Lite/s8_1_capability_nonlinear_recheck.csv
System Matpower Format/NY_Lite/s9a_reactive_control_diagnostic_assessment.md
System Matpower Format/NY_Lite/s9a_q_support_case_summary.csv
System Matpower Format/NY_Lite/s9a_q_support_by_bus.csv
System Matpower Format/NY_Lite/s9a_perform_zonal_q_capability.csv
System Matpower Format/NY_Lite/s9a_external_boundary_q_dispatch.csv
System Matpower Format/NY_Lite/run_s9b_ac_feasibility_restoration.m
System Matpower Format/NY_Lite/s9b_ac_feasibility_restoration_assessment.md
System Matpower Format/NY_Lite/s9b_feasibility_restoration_summary.csv
System Matpower Format/NY_Lite/s9b_feasibility_restoration_slacks.csv
System Matpower Format/NY_Lite/s9b_external_boundary_q.csv
System Matpower Format/NY_Lite/build_ny_voltage_reference_sets.m
System Matpower Format/NY_Lite/ny_voltage_reference_sets.csv
System Matpower Format/NY_Lite/ny_voltage_reference_coverage.csv
System Matpower Format/NY_Lite/s1_opf_voltage_reference_provenance.csv
System Matpower Format/NY_Lite/perform_zonal_voltage_reference_summary.csv
System Matpower Format/NY_Lite/perform_generator_voltage_controls.csv
System Matpower Format/NY_Lite/perform_voltage_control_coverage.csv
System Matpower Format/NY_Lite/run_s9b_reference_continuation_audit.m
System Matpower Format/NY_Lite/s9b_reference_continuation_summary.csv
System Matpower Format/NY_Lite/s9b_reference_continuation_slacks.csv
System Matpower Format/NY_Lite/s9b_reference_onset_brackets.csv
```

## 14. Claim Boundaries

Defensible statement:

> The reduced NPCC-NY model preserves the NPCC New York load magnitude, uses
> scaled public NYISO zonal load and interchange snapshots, estimates bounded
> zonal injections against seven public internal interfaces, allocates generation
> with PERFORM-derived GSKs, and improves training and held-out interface-flow
> consistency when direct PERFORM corridor parameters are used.

Do not claim:

> The model reproduces detailed NYISO internal physics, observed zonal
> generation, or full NPCC AC feasibility.

Do not interpret an S9b reference weight as a fraction of real generator
setpoint enforcement. S1 values are OPF-solved numerical references, original
NPCC values are source-case fields of uncertain scenario applicability, and the
current PERFORM mapping is only a provisional zonal aggregate without regulated
bus/control preservation. Exact source `VS` and `IREG` fields are now archived,
but they have not yet been mapped device-by-device into the reduced model.

The current S7 network remains a reduced structural calibration candidate. Its
inherited S4 capability envelope and voltage-control state are not certified,
and S8/S8.1/S9a/S9b are diagnostic operating-point experiments rather than promoted
cases.

## 15. Handoff Package and Integrity

The compressed handoff package contains the complete reproducibility scope:

```text
PROJECT_HANDOFF.md
LATEST_MODEL_CONFIGURATION.csv
run_handoff_reproduction.m
PACKAGE_MANIFEST.csv
PACKAGE_CONTENT_ROOT.sha256
System Matpower Format/
PERFORM/
ENLITEN-Grid-Econ-Data-main/
output/
```

`PERFORM/` is included unchanged as the higher-resolution reference dataset.
`ENLITEN-Grid-Econ-Data-main/` is included so the original NPCC source case can
be traced independently. `System Matpower Format/NY_Lite/nyiso_public_cache/`
contains the downloaded NYISO public inputs used by the reproducible scenario
builders.

`PACKAGE_CONTENT_ROOT.sha256` stores a SHA-256 digest of payload records for
every packaged project file except the manifest and content-root file. Records
use `PACKAGE_MANIFEST.csv` row order after removing the content-root row. Each
record is lowercase file SHA-256, two ASCII spaces, and the case-preserved
package-relative path with `/` separators, followed by LF. The complete record
stream is UTF-8 without BOM and ends with LF. The exact ZIP checksum
cannot be embedded in that same ZIP without changing the ZIP; it is distributed
in the sibling `.zip.sha256.txt` file. Together, the internal content root and
external archive checksum provide payload-level and transfer-level verification.

`PACKAGE_MANIFEST.csv` lists every packaged file except itself, with relative
path, byte size, modification time, and SHA-256 hash. The archive-level SHA-256
is stored beside the ZIP file in a `.sha256.txt` file.

Transient working directories (`tmp/`) and local tool state (`.codex/`,
`.agents/`, and `.git/`) are deliberately excluded. They are not required to
run or audit the model.
