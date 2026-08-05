# NPCC-NY Lite Calibration Project Handoff

**Original handoff date:** 2026-07-12
**Model-hierarchy update:** 2026-08-05
**Structural provenance case:** `npcc_ny_lite_s7_seven_interface_perform_direct_candidate`
**Construction and validation parent:** `npcc_ny_lite_s13_npcc_augmented_2019` (`S13-FULL`)
**Promoted operating case:** pending `npcc_ny_lite_s14_nyiso_dlr_operating_model` (`S14-NYISO`)
**Reference oracle:** `npcc_ny_lite_s12_perform_retention_core`
**Current status:** S7 preserves structural provenance; S13-FULL preserves the
full NPCC construction network; S11 is diagnostic only; S12 is an oracle only;
and no S14 operating case has been built or promoted.

## 1. Executive Summary

This project augments the public NPCC MATPOWER case with selected New York
detail. S13-FULL preserves the full NPCC-derived network for provenance,
construction, and validation. The eventual DLR delivery model is S14-NYISO:
the retained NYISO subnetwork plus a validated AC multi-terminal equivalent of
only the non-NY network. S11 remains a historical diagnostic reduction and S12
remains a PERFORM-derived oracle; neither is the promoted operating model.

The S7 structural provenance case, which remains the ancestor of S13-FULL, has:

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
be held fixed in an ordinary power flow; that reduced validation model is a
diagnostic benchmark only.

### 1.1 Governing model hierarchy

| Model | Repository role |
|---|---|
| Original NPCC / S7 full case | Structural provenance case |
| S13-FULL NPCC-augmented case | Full-NPCC construction and validation parent |
| S11 49-bus NY boundary equivalent | Diagnostic/reduced-model benchmark only |
| S12 317-bus PERFORM reduction | Calibration and validation oracle only |
| Pending S14-NYISO | Promoted NYISO DLR operating model after its own gates pass |
| Full PERFORM 2019 case | Source dataset and highest-fidelity reference |

The intended inheritance is original NPCC → S7 → Phase 0 source-backed
corrections → S13-FULL selective physical NYISO augmentation and internal
residualization → S14-NYISO external reduction and operating validation. All
original NPCC bus IDs and branch records remain traceable in S13-FULL. No
external NPCC area may be replaced inside S13-FULL, and no S12 Kron-equivalent
branch may enter S13-FULL or S14. S14 may eliminate only non-NY detail after
retaining the NYISO network, physical overlays, controls, DLR terminals, and
registered boundary terminals. Added physical circuits may receive DLR
conductor data; aggregate, residual, and boundary-equivalent branches may not.

Topology is append-only, but admittance is not blindly additive. When an
original NPCC branch already embeds a newly explicit physical path, that
original row remains in place and may be refit only as a registered passive
residual equivalent. A nonpassive residual is rejected in favor of adding more
physical internal detail.

Current 2019 public-hour S7 validation:

```text
Current S4 seven-interface objective       0.499136
Direct-PERFORM S7 objective                0.489612
Improvement                                 1.9%
Held-out objective improvement              2.5%
Standard PF convergence                    6/6
Q-limit-enforced PF convergence            6/6
Worst interface residual                 888.553 MW
Minimum / maximum voltage             0.952721 / 1.110022 pu
```

Legacy 2025-target diagnostics retained for provenance, but not rerun against
the current 2019 public-hour targets:

```text
S8.1 inherited 0.8-cap minimum eta        2.7013
S9a free-voltage temporary Q support       0 MVAr
S9a full S1-reference status               not demonstrated
S9b last hard-feasible S1 weight           0.8075
S9b first restored S1 weight               0.8100
S9b refined/reference audit solves         182/182
```

Separate 2019 same-snapshot S10a diagnostic:

```text
S10a 2019 reduced Q-limit PF               converged
S10a retained/pilot voltage RMSE           0.003840 pu
S10a seven-interface MAE                   224.95 MW
S10a mean normalized control-group Q error 0.1870
```

The current Phase 1A S13-FULL construction checkpoint adds four exact PERFORM terminals (Fraser,
Coopers Corner, Marcy, and Rock Tavern) and seven direct physical source rows
between matching EDIC and Ramapo attachments. It has 147 buses, 253 branches,
and 62 generators. All 29 mandatory structural gates pass; the five
construction-validation gates remain fail-closed. Both
S7/Phase 0 and S13-FULL converge in
the inherited-snapshot standard-PF smoke test. Both fail that
snapshot's Q-limit PF, so the smoke result is not an operating gate. S13-FULL
is never the DLR delivery case; its remaining validation determines whether it
is fit to supply the NYISO topology and external reduction source for S14.
All seven canonical overlay registers and the structural ledger match fresh
in-memory tables, and all 20 adversarial mutations fail at their expected gate.

The S13.1 no-fit local fixture now passes 20/20 mandatory gates. Direct
seven-branch power recomputation differs from full PERFORM by at most
2.67e-11 MW and 1.87e-11 MVAr; the omitted-network-injection solve recovers
the four interior voltages to machine precision; and S12 retained-circuit
flows differ by at most 0.084744 MW. The isolated zero-injection fixture is
diagnostic only because it reaches 2.44455 degrees of angle error and reverses
one branch direction.

The full paired S12/S13-FULL diagnostic is still fail-closed. Its common
input audit passes 14/18 readiness gates. The blockers are the nonrepresentable
generation projection in 15 scenario-zone rows (H plus selected A/B/C/E
capacity cases), the missing full-NPCC regional tie-flow controller,
and missing common AC-loss and voltage-control policies. No S12 boundary
injection, interface-flow closure, or residual R/X/B fit is used to bypass
those prerequisites. These failures limit the S13-FULL paired diagnostic; they
do not make preservation of the full external NPCC network a prerequisite for
eventual S14 promotion.

The package is appropriate for continued S13-FULL structural augmentation and
diagnostic research. It is not yet appropriate for claiming a promoted S14
operating case, fully feasible NYISO operations, or detailed circuit-level
equivalence.

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
5. applies the ratings-only Phase 0 correction to the full S7 parent;
6. verifies the original 140 buses, original 233 branch-row identities and
   names, all three S7 transit buses, source-backed zero-injection terminals,
   append-only structure, registered attachment paths, and absence of
   S12/Kron admittance;
7. compares the seven committed S13 register CSVs and structural-gate ledger
   with freshly rebuilt in-memory tables and fails on any schema, row, column,
   type, or value drift;
8. verifies that the S12 oracle snapshot sidecar contains the complete
   eight-circuit Total East operator and matches a fresh recomputation;
9. reruns the durable S13 adversarial mutation suite; and
10. runs the exact S13.1 local physical-circuit identity fixture and the
    fail-closed common-input representability audit, then compares all twelve
    committed S13.1 evidence CSVs against canonical rebuilt tables; and
11. runs the inherited-snapshot S7/S13 standard- and Q-limit-PF smoke
    diagnostic, reporting its limitations without treating it as an S14 promotion
    gate or a 2019 operating-point comparison.

The `s13-artifact-integrity` GitHub workflow repeats the structural, artifact,
adversarial, S12-sidecar, S13.1 preflight, and inherited-snapshot smoke checks for pull requests,
`main`/`codex/**` pushes, and manual dispatch. CI writes no smoke artifacts and
asserts only `standard_pf_both_pass`; it reports but does not assert Q-limit PF
success because the inherited snapshot's Q-limit failure is a known diagnostic,
not an S13-FULL construction gate or an S14 promotion gate.

The default remains an S7 provenance and S13-FULL construction-parent
reproduction. It must report the promoted operating model as pending S14-NYISO
and must never report S7, S11, S12, or S13-FULL as the DLR delivery case.

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

To rebuild the device-level PERFORM control mapping and the similarity-scaled
2019 same-snapshot benchmark:

```matlab
outputs = run_handoff_reproduction(struct( ...
    'rebuild_public_targets', false, ...
    'run_s10a_control_benchmark', true));
```

This rebuilds the 649-row source-control map, audits the ten previously skipped
PQ locations, runs the fixed-source-Q benchmark plus two boundary-Q
sensitivities, and saves the solved 49-bus diagnostic case. S7 remains the
recommended structural case.

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

The direct PERFORM candidate remains the structural parent because it preserves
source-backed circuit parameters. The lower-training-error fitted-sensitivity
comparison discussed below is a legacy 2025-target result and has not been
rerun against the current 2019 public-hour targets.

### 4.9 S8: Iterative AC Injection Closure (legacy 2025-target diagnostic)

S8 does not change the structural case. This retained experiment applies an
operational re-estimation to the direct-PERFORM S7 network, but its numerical
results below have not been rerun against the current 2019 public-hour targets.

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

### 4.10 S8.1: Local Linear Capability-Envelope Certificate (legacy 2025-target diagnostic)

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

### 4.11 S9a: Minimum-Q and Voltage-Control Diagnostic (legacy 2025-target diagnostic)

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

### 4.12 S9b: Voltage-Reference and AC Restoration Audit (legacy 2025-target diagnostic)

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
brackets are 0.75-0.80 for original NPCC, 0.80-0.825 for the then-current S7,
and 0.90-1.00 for the provisional PERFORM zonal envelope. Therefore, no threshold
is interpreted as a real-system voltage-control limit.

The PERFORM PSS/E RAW source has now been parsed directly: all 649
generator-section records retain `VS` and `IREG`; 417 online records map to
NYISO A-K at 179 source buses, one uses remote regulation, and every online
regulated bus resolves in the source bus table. Preliminary classification
identifies 34 reactive-only `QS` records, 381 positive-active-capability
records, and two fixed-negative active-power boundary/import equivalents. The
417 records must not be interpreted as 417 conventional generators.

The S1 and original-NPCC reference sets request and apply 20 buses. The current
S7 and provisional PERFORM tables contain 30 requested rows, but only 20 are
applied because buses `37|38|39|41|43|44|73|76|81|9003` are PQ buses in the
study case. These requested/applied/skipped counts and IDs are written into
every S9b summary row. The S9b PERFORM reference remains a low-confidence zonal
aggregate; the later S10a mapping is deliberately not fed back into S9b.

All 182 refined/reference final solves return IPOPT status 0 with no exceptions.
The maximum independently evaluated P- or Q-balance component residual is
0.001067 MW or MVAr, while the maximum complex-power mismatch magnitude is
0.001069 MVA. Full dual/complementarity/KKT residuals are not exposed by the
installed wrapper and are reported as unavailable rather than inferred.

### 4.13 S10a: Control-Preserving 2019 PERFORM Benchmark

S10a maps each PERFORM RAW generator-section record by source bus and generator
ID to the converted MATPOWER row, then maps source devices into retained S7
control proxies. The identity map is one-to-one for all 615 non-`QS` rows. Six
RAW `STAT` values differ from converted `GEN_STATUS`, so both are archived and
the converted status is used for the 2019 benchmark. The effective snapshot has
411 online A-K control records, including 34 reactive-only `QS` records.

Plant/GSK provenance maps native active resources. Reactive-only devices and
the single remote `IREG` assignment use a Ward effective-impedance distance to
source anchors. The ten PQ-skipped S7 buses now have explicit source-control
audits. Seven are source-backed PV candidates; EDIC, Porter, and East Garden
City remain pending because of broad Q envelopes or low-confidence aggregation.
All ten are enabled as PV only in the S10a diagnostic.

The detailed PERFORM snapshot is similarity-scaled by:

```text
gamma = 10,902.2197987 / 29,799.66 = 0.3658504761
```

This preserves the detailed source per-unit operating point while scaling MW,
MVAr, ratings, and losses to the NPCC-NY load magnitude. The reduced benchmark
uses the NY-only portion of the S7 structural network, source zonal loads,
source native generation and external interchange, mapped Q limits and `VS`,
and fixed source boundary Q.

```text
Reduced case size                         49 buses / 81 branches / 47 generators
Source and reduced Q-limit PF             converged / converged
Retained/pilot voltage RMSE               0.003840 pu       pass (< 0.01)
Maximum retained/pilot voltage error      0.015684 pu       pass (< 0.03)
Seven-interface MAE                       224.95 MW         fail (< 100)
Maximum interface residual                559.57 MW
Mean normalized control-group Q error     0.1870            fail (< 0.10)
Scaled source / reduced active loss       229.00 / 103.72 MW
Reference balancing adjustment            -125.28 MW
Voltage / Q / branch violations           0 / 0 / 0
```

Fixed source boundary Q converges with effectively zero external-Q schedule
error. Allowing the boundary equivalents to redispatch Q also converges but
uses about 1.85 GVAr of external-Q movement, so it is a sensitivity rather than
the primary benchmark.

The first five flow comparisons use matched zone-pair cut proxies. UPNY-ConEd
and Dunwoodie South still use conceptual source-to-reduced cuts because exact
monitored-element operators are unavailable; Dunwoodie is the largest residual.
S10a therefore validates the initial control mapping and exposes remaining
reduction error, but it does not replace S7 provenance or satisfy any S14
promotion gate.

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

In the legacy 2025-target sweep, the fitted sensitivity used multipliers
`2.0 / 0.85 / 1.0` respectively and reduced that vintage's all-hour objective
to 0.22842. It was not promoted. Those fitted-sweep metrics are not comparable
to the current 2019-target objective and have not been rerun on that target set.

## 10. Current Results

| Case | Training objective | Holdout objective | All-hour objective | Worst residual |
|---|---:|---:|---:|---:|
| Current S4 ties, 2019 targets | 0.300342 | 0.198794 | 0.499136 | 890.08 MW |
| Direct PERFORM S7, 2019 targets | 0.295784 | 0.193827 | 0.489612 | 888.55 MW |

Direct PERFORM improves all-hour normalized consistency by 1.9% and held-out
consistency by 2.5% on the current 2019 target set. Standard and Q-limit-
enforced PF both converge 6/6. The maximum standard-PF branch overload is
341.03 MVA, the maximum standard-PF Q-limit violation is 253.46 MVAr, and the
voltage range is 0.952721-1.110022 pu. These are convergence and diagnostic
results, not promotion or feasibility certification.

Mean absolute residuals for the recommended case:

| Interface | MAE |
|---|---:|
| Dysinger East | 133.5 MW |
| West Central | 215.6 MW |
| Moses South | 53.7 MW |
| Central East | 110.1 MW |
| Total East proxy | 361.9 MW |
| UPNY-ConEd | 105.5 MW |
| Dunwoodie South | 276.6 MW |

### 10.1 Legacy 2025-target operational-closure diagnostic

The following S8 table is retained for method provenance only. It has not been
rerun against the current 2019 public-hour targets and is not current S7 or S13
performance evidence.

| Score | Objective | Mean absolute residual | Worst residual |
|---|---:|---:|---:|
| Initial DC estimate | 0.015599 | 36.41 MW | 354.89 MW |
| Frozen S6 dispatch on direct S7 | 0.233303 | 138.35 MW | 424.91 MW |
| S8 iterative AC dispatch | 0.015310 | 19.49 MW | 416.00 MW |

In that legacy experiment, S8 reduced UPNY-ConEd MAE from 259.81 to 11.40 MW
and Dunwoodie South MAE from 239.47 to 2.20 MW. It showed that loss and dispatch
closure had more leverage than another three-corridor impedance sweep for that
target vintage. It does not establish the same result for the current 2019
targets. The remaining legacy worst residual was the shoulder West-Central
target.

## 11. Open Problems and Legacy Diagnostics

For the current 2019 direct-S7 run, Q-limit PF converges 6/6, but the worst
interface residual remains 888.55 MW, the maximum branch overload is 341.03
MVA, and voltages reach 1.110022 pu. Sections 11.1-11.6 retain the older
2025-target diagnostic record for provenance; their numerical values are not
current 2019 public-hour results.

### 11.1 Shoulder operating-point infeasibility (legacy 2025-target diagnostic)

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

### 11.2 Capability-envelope conflict (legacy 2025-target diagnostic)

The shoulder West-Central target is linearly incompatible with the inherited
0.8 A/B/C participation envelope (`eta = 2.7013`). A minimum 272.58 MW A/B/C
relaxation reaches the reporting band, but restoring the full 1.0 envelope
worsens nonlinear voltage/Q feasibility. Scenario-specific available capability
cannot be tested until an independent hourly availability or commitment table
is supplied.

### 11.3 Remaining voltage violations (legacy 2025-target diagnostic)

The direct PERFORM charging improves the worst standard-PF minimum voltage from
0.8037 to 0.9022 pu. Maximum voltage remains 1.1128 pu, and up to three buses
still exceed their 1.10-pu upper bounds.

### 11.4 Persistent branch overload (legacy 2025-target diagnostic)

Branch 29, Niagara West-Huntley, overloads in every scenario. The largest
excess is 168.06 MVA in the shoulder case. The tie calibration did not remove
this western constraint.

### 11.5 Reference-generator loss balancing (legacy 2025-target diagnostic)

The frozen S7 comparison places AC loss imbalance on one Zone J reference unit.
Reference adjustment ranges from roughly 146 to 589 MW and biases downstream
interface flows. S8 closes this mismatch with headroom-weighted loss allocation
and reduces final reference pickup below 0.1 MW. Frozen S7 remains the structural
topology score; S8 is the separate in-sample operational score.

### 11.6 Interface residuals remain material (legacy 2025-target diagnostic)

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

### 11.9 S14-NYISO boundary policy

The promoted DLR operating model no longer needs to carry the full external
NPCC mesh. That mesh remains in S13-FULL for provenance, construction, and
validation. S14-NYISO will retain the NYISO network and replace only the non-NY
portion with a separately registered AC multi-terminal boundary equivalent.
The fail-closed implementation contract is documented in
`System Matpower Format/NY_Lite/S14_NYISO_DLR_OPERATING_MODEL.md`.

At the current Phase 1A checkpoint, S13-FULL has 53 NYISO-side buses and ten
active NY/external tie rows. Retaining the ten first external terminals gives a
provisional 63-bus inventory. It would preserve 88 NY-internal branch rows plus
the ten tie rows; all 155 external-external rows, including row 178 between
external terminals 124 and 125, belong to the eventual external equivalent.
This inventory is not final because Phase 1B/1C add NYISO terminals and the
downstate landing detail needed by several public schedule groups.
These figures come from a read-only design audit and are non-gating until the
future retention builder reproduces them in a canonical register.

The present S13-FULL topology distinguishes four regional AC cuts: HQ, Ontario,
ISONE, and PJM. It does not provide validated individual landing/control paths
for NPX 1385, NPX CSC, HTP, Neptune, or VFT. Those schedules therefore remain
fail-closed rather than being hidden in one regional slack. A preliminary
admittance audit also shows that a simple unit-tap branch-plus-diagonal-shunt
realization would require negative-conductance shunts even though the complete
multi-port is passive. The final reducer must use a passive synthesis or retain
more external buses; it must not copy the simple S12 realization blindly.
The coupling/passivity observations are likewise preliminary design evidence,
not a promotion artifact, until a committed reduction audit reproduces them.

## 12. Recommended Next Work

1. **Phase 1B — UPNY-ConEd physical cut.** Add East Fishkill and Ladentown and
   preserve Pleasant Valley–East Fishkill, Ladentown–Buchanan, and Pleasant
   Valley–Wood Street circuits. Replace the conceptual operator with a
   nonintersecting physical cutset.
2. **Phase 1C — downstate interface mesh.** Add separate Sprain Brook,
   Dunwoodie, West 49th Street, Tremont/Academy, Jamaica, Lake Success, and
   Valley Stream terminals. Diagnose H-J, K-J, and net Zone-J import separately.
3. **Phase 1D — passive internal residual equivalents.** Freeze added physical circuits,
   the five DLR circuits, and nonoverlapping original branches. Rows 34/36 are
   physical-overlap residual candidates. Rows 40/42 are adjacent E-F
   calibration candidates and remain frozen unless paired multi-snapshot
   response evidence and strong regularization explicitly authorize them.
   Reject negative-resistance or materially nonpassive residuals and add more
   physical detail instead.
4. **Define the cumulative S14 retention set.** Retain all Zones A-K buses,
   every Phase 1A-1C physical addition, NYISO generators and Q-control buses,
   DLR terminals, NY-side tie terminals, and only the first external terminals
   needed to distinguish boundary facilities. Register every retention reason
   and boundary group. A Phase 1A-only inventory is provisional and must not
   freeze the final set.
5. **Reduce only the non-NY external network.** Derive an AC multi-terminal
   equivalent from S13-FULL after the internal topology is complete. Preserve
   the scenario-specific equivalent injection vector, synthesize only passive
   equivalent branches/shunts, and reject a realization requiring negative
   resistance or materially nonpassive behavior. Do not reuse the historical
   prune-and-inject S1/S11 formulation as the S14 builder.
6. **Validate S13-FULL against S14.** Use the same solved operating point and
   compare retained-bus voltage, NYISO interface flow, NY losses, boundary P/Q,
   and DLR currents. The external equivalent must meet tighter direct-reduction
   gates before S12 is used for independent NYISO behavior validation.
7. **Build explicit interchange controls.** Preserve regional AC schedule sums
   while allowing the multi-port equivalent to determine sharing. NPX 1385,
   NPX CSC, HTP, Neptune, and VFT remain fail-closed until source-backed landing
   buses or explicit HVDC devices are present; do not hide them inside a generic
   regional slack.
8. Only after topology, reduction, response, and control gates pass, reconstruct
   the six similarity-scaled 2019 public hours with bounded dispatch closure.
   Report movement explicitly and do not treat S12 closed dispatch as observed
   history. Obtain scenario-specific unit availability and unsupported PAR/tap schedules
   where possible; otherwise use fixed snapshot values or bounded variables
   with documented uncertainty.

## 13. High-Value Files

### Recommended case and reproduction

```text
System Matpower Format/npcc_ny_lite_s7_seven_interface_perform_direct_candidate.m
System Matpower Format/npcc_ny_lite_s13_npcc_augmented_2019.m
System Matpower Format/NY_Lite/S13_NPCC_PRESERVING_AUGMENTATION.md
System Matpower Format/NY_Lite/add_npcc_perform_eg_corridor.m
System Matpower Format/NY_Lite/build_s13_phase1a_candidate.m
System Matpower Format/NY_Lite/validate_s13_structural_preservation.m
System Matpower Format/NY_Lite/validate_s13_artifact_consistency.m
System Matpower Format/NY_Lite/test_s13_structural_validator_adversarial.m
System Matpower Format/NY_Lite/run_s13_phase1a_local_identity.m
System Matpower Format/NY_Lite/test_s13_phase1a_local_identity.m
System Matpower Format/NY_Lite/assess_s13_phase1a_common_input_readiness.m
System Matpower Format/NY_Lite/test_s13_phase1a_common_input_readiness.m
System Matpower Format/NY_Lite/run_s13_phase1a_oracle_comparison.m
System Matpower Format/NY_Lite/test_s13_phase1a_oracle_comparison.m
System Matpower Format/NY_Lite/validate_s13_phase1a_oracle_artifact_consistency.m
System Matpower Format/NY_Lite/test_s13_phase1a_oracle_artifact_consistency.m
System Matpower Format/NY_Lite/s13_structural_adversarial_results.csv
System Matpower Format/NY_Lite/s12_generate_interface_snapshot_sums.m
System Matpower Format/NY_Lite/test_s12_interface_snapshot_sums.m
System Matpower Format/NY_Lite/s12_interface_snapshot_sums.csv
System Matpower Format/NY_Lite/validate_s13_phase1a_smoke.m
System Matpower Format/NY_Lite/npcc_perform_overlay_bus_map.csv
System Matpower Format/NY_Lite/npcc_perform_overlay_branch_map.csv
System Matpower Format/NY_Lite/npcc_residual_equivalent_register.csv
System Matpower Format/NY_Lite/npcc_residual_shunt_register.csv
System Matpower Format/NY_Lite/npcc_overlay_path_register.csv
System Matpower Format/NY_Lite/npcc_added_physical_circuit_register.csv
System Matpower Format/NY_Lite/npcc_2019_interface_operator_map.csv
System Matpower Format/npcc_ny_lite_s10a_perform_control_mapped_2019.m
System Matpower Format/npcc_ny_lite_s10a_perform_control_mapped_2019_pf_solution.m
run_handoff_reproduction.m
LATEST_MODEL_CONFIGURATION.csv
.github/workflows/s13-artifact-integrity.yml
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
System Matpower Format/NY_Lite/perform_voltage_control_classification_summary.csv
System Matpower Format/NY_Lite/run_s9b_reference_continuation_audit.m
System Matpower Format/NY_Lite/s9b_reference_continuation_summary.csv
System Matpower Format/NY_Lite/s9b_reference_continuation_slacks.csv
System Matpower Format/NY_Lite/s9b_reference_onset_brackets.csv
System Matpower Format/NY_Lite/build_perform_control_preserving_mapping.m
System Matpower Format/NY_Lite/build_s10a_perform_control_mapped_case.m
System Matpower Format/NY_Lite/run_s10a_perform_same_snapshot_benchmark.m
System Matpower Format/NY_Lite/perform_source_to_reduced_control_mapping.csv
System Matpower Format/NY_Lite/perform_reduced_control_groups.csv
System Matpower Format/NY_Lite/perform_pq_skipped_reference_audit.csv
System Matpower Format/NY_Lite/perform_discrete_control_summary.csv
System Matpower Format/NY_Lite/perform_discrete_control_mapping.csv
System Matpower Format/NY_Lite/perform_retained_control_anchors.csv
System Matpower Format/NY_Lite/s10a_control_preserving_benchmark_assessment.md
System Matpower Format/NY_Lite/s10a_same_snapshot_summary.csv
System Matpower Format/NY_Lite/s10a_retained_voltage_comparison.csv
System Matpower Format/NY_Lite/s10a_control_group_q_comparison.csv
System Matpower Format/NY_Lite/s10a_interface_flow_comparison.csv
System Matpower Format/NY_Lite/s10a_loss_comparison.csv
System Matpower Format/NY_Lite/s10a_external_boundary_q_comparison.csv
System Matpower Format/NY_Lite/s10a_branch_loading_comparison.csv
System Matpower Format/NY_Lite/s10a_discrete_control_actions.csv
System Matpower Format/NY_Lite/s10a_reduced_generator_groups.csv
System Matpower Format/NY_Lite/s10a_boundary_q_mode_sensitivity.csv
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
S9b PERFORM reference is only a provisional zonal aggregate. S10a separately
maps source `VS`, `IREG`, status, Q limits, and device classes into retained
control groups and pilot buses using plant/GSK rules plus a Ward
effective-impedance metric. That mapping is still provisional where Q envelopes
are broad or exact retained electrical equivalents are absent.

S7 remains the NPCC-derived structural provenance case and S13-FULL remains the
full-network construction and validation parent. Their inherited capability and
voltage-control states are not certified, and S8/S8.1/S9a/S9b/S10a/S11 are
diagnostic operating-point or reduced-model experiments rather than promoted
cases. S12 is a separate reference oracle. Only the future S14-NYISO retained
network plus validated external AC multi-port equivalent can become the DLR
operating model.

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

`PERFORM/` is included unchanged as the source dataset and highest-fidelity
reference.
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
