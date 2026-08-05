# S13: NPCC-preserving 2019 augmentation

**Target case:** `npcc_ny_lite_s13_npcc_augmented_2019`
**Status:** pending; no S13 operating case is promoted yet
**Structural parent:** `npcc_ny_lite_s7_seven_interface_perform_direct_candidate`
**Reference oracle:** `npcc_ny_lite_s12_perform_retention_core`
**Highest-fidelity source:** full PERFORM 2019 case

## Model hierarchy

| Model | Role |
|---|---|
| Original NPCC / S7 full case | Structural parent |
| S13 NPCC-augmented case | Promoted DLR testbed only after all gates pass |
| S11 49-bus NY boundary equivalent | Diagnostic/reduced-model benchmark only |
| S12 317-bus PERFORM reduction | Calibration and validation oracle only |
| Full PERFORM 2019 case | Source dataset and highest-fidelity reference |

The inheritance path is original NPCC → S7 → Phase 0 source-backed corrections
→ selective physical NYISO additions → passive residualization → S13.

## Mandatory structural invariants

1. All 140 original NPCC bus rows and IDs remain traceable.
2. All 233 original NPCC branch rows retain their row identity and endpoints.
3. S7 transit buses 9001–9003 remain.
4. No external NPCC area is replaced by a boundary equivalent.
5. No S12 Ward/Kron-equivalent branch is copied into S13.
6. New buses and branches are appended and provenance-registered.
7. Only source-backed physical circuits are DLR-eligible.
8. Every adjusted original branch is registered with a residual class and the
   evidence required to authorize that adjustment.

Branch traceability is row-based, not just endpoint-pair based, because parallel
circuits can share endpoints. A topology-preservation gate must fail if an
original row moves, disappears, or changes endpoints.

## Admittance policy

Topology is addition-only; admittance is not blindly addition-only. Explicit
physical circuits can overlap transfer paths already embedded in original NPCC
aggregate branches. Adding both without adjustment would double-count series
admittance, charging, capability, losses, and interface flow.

The original row remains in place. Rows with demonstrated physical overlap are
classified as `physical_overlap_residual_candidate`. Adjacent equivalents that
might improve calibration but do not have direct overlap evidence are classified
as `adjacent_equivalent_calibration_candidate` and remain frozen until paired
multi-snapshot response evidence and stronger regularization are documented.
An authorized row's R/X/B may be refit to represent only the unmodeled remainder. A simple
two-terminal `Y_old - Y_physical` subtraction is insufficient where the old and
new networks have different terminals; use a passive multi-terminal fit. Reject
negative resistance, nonfinite parameters, or materially nonpassive residuals
and add more internal physical detail instead.

## Implementation phases

### Phase 0 — source-backed corrections

Keep the Zone-D and transit metadata fixes, source-backed cut ratings, protected
direct-PERFORM corridors, and ratings-only default. The reactance fit remains
off by default. Phase 0 adds no buses or branches and does not promote a case.

### Phase 1A — E-G path

Start from the full 143-bus S7 parent with Phase 0 applied. Add the source
Coopers Corner–Rock Tavern path and enough physical PERFORM detail to connect
the matching EDIC and Ramapo terminals without invented attachment impedance.
Validate E-F versus E-G flow split, Central East, Total East, physical-circuit
currents, losses, voltages, and reactive balance. Re-derive dispatch for every
changed topology before scoring it.

The current unpromoted Phase 1A artifact is built by
`add_npcc_perform_eg_corridor.m`. It adds PERFORM buses 1228 Fraser, 1222
Coopers Corner, 1567 Marcy, and 772 Rock Tavern and seven direct source branch
rows (2137, 2131, 2154, 2133, 1567, 1568, and 1571). Existing S7 buses 43 EDIC
and 76 Ramapo are exact-name, 345-kV, same-zone attachment matches to PERFORM
buses 1233 and 1519. The resulting 147-bus/253-branch/62-generator candidate
contains no invented attachment impedance. It is not promoted because the
overlapping aggregate residual fit and all operating-response gates are still
pending. The four added terminals have zero local source PD/QD/GS/BS and no
online generators; the committed bus map records those values explicitly.
They are not isolated zero-injection buses in the seven-branch fixture: eleven
other active PERFORM branches exchange power with them.

The no-fit local identity test therefore uses two distinct checks. First, it
recomputes the seven branch terminal powers from the solved PERFORM phasors and
the copied branch model. Second, it fixes EDIC and Ramapo at the source phasors
and solves the four interior buses with complex injections derived from the
omitted incident branches. All 20 mandatory local gates pass: maximum direct
P/Q errors are about 2.7e-11 MW and 1.9e-11 MVAr; the injection-supported solve
recovers interior voltage magnitude and angle to machine precision; and the
read-only S12 circuit comparison differs by at most 0.0848 MW. A separate
zero-injection truncation is diagnostic only. Its maximum angle error is about
2.45 degrees and one circuit reverses direction, so it is prohibited as an
acceptance gate.

The full same-snapshot comparison remains pending. The common-input audit
currently passes 14 of 18 readiness gates and fails closed on four prerequisites:
a common generation projection is missing for 15 scenario-zone rows (Zone H
has no S13 generator, while selected A/B/C/E priors exceed current mapped
capability), a full-NPCC regional tie-flow controller is not implemented, and
common AC-loss and voltage-control policies are not yet representable. S12 boundary generators are never added to
S13, interface-flow closure is disabled, and no R/X/B is fitted by the audit.

`run_s13_phase1a_oracle_comparison.m` preserves this claim boundary in durable
artifacts. It records 22 blocked same-snapshot metric rows, five blocked cut
operators, seven physical-circuit rows with real Stage-A evidence and separate
future common-baseline fields, twelve blocked perturbation summaries, and a
432-row long-form held-out metric manifest. That manifest reserves delta P/Q/
current for every circuit, delta voltage magnitude/aligned angle for every
terminal, and E-G/E-F cut plus internal-NY loss metrics for every perturbation.
All unexecuted values remain NaN, every row records the pending balancing policy
and no-refit rule, and the oracle ledger remains fail-closed at 38/59 gates.
Twelve committed S13.1 CSVs are compared byte-for-byte with canonical LF
serialization of freshly rebuilt tables.

### Phase 1B — UPNY-ConEd

Add East Fishkill and Ladentown and preserve the Pleasant Valley–East Fishkill,
Ladentown–Buchanan, and Pleasant Valley–Wood Street circuit groups. Define the
public interface as a nonintersecting cutset; do not sum series elements around
Wood Street.

### Phase 1C — downstate mesh

Add separate Sprain Brook, Dunwoodie, West 49th Street, Tremont or Academy,
Jamaica, Lake Success, and Valley Stream terminals. Keep H-J and K-J transfer
families separate. Report the Dunwoodie H-J component, Dunwoodie K-J component,
and total net import into Zone J before defining a combined public operator.

### Phase 1D — residual equivalents

Freeze all added physical circuits, the five DLR circuits, and nonoverlapping
original branches. Rows 34/36 are physical-overlap residual candidates. Rows
40/42 are adjacent E-F calibration candidates and remain frozen until paired
multi-snapshot S12/S13 evidence and strong deviation regularization authorize
them. Promotion remains blocked until every fitted residual passes the required
evidence and passive-admittance gates.

## Required registers

- `npcc_perform_overlay_bus_map.csv`
- `npcc_perform_overlay_branch_map.csv`
- `npcc_residual_equivalent_register.csv`
- `npcc_residual_shunt_register.csv`
- `npcc_overlay_path_register.csv`
- `npcc_added_physical_circuit_register.csv`
- `npcc_2019_interface_operator_map.csv`

Every added branch records source PERFORM row and endpoints, circuit ID, source
R/X/B and ratings, S13 endpoints, physical/equivalent class, DLR eligibility,
mapping confidence, construction method, and implementation status. S13
network-admittance rows may not name S12 as their source model.
The default reproduction also rebuilds and compares all seven bus, branch,
residual, residual-shunt, path, physical-circuit, and interface-operator tables
against their committed CSVs.
Any schema, row, column, type, or value mismatch fails closed.

`candidate.userdata.s13.overlay_report` is the cumulative register source of
truth. `candidate.userdata.s13.phase_reports` stores per-phase evidence, and
`phase1a_report` remains a compatibility alias that must exactly equal
`phase_reports.phase1a`. The generic model role is
`unpromoted_s13_candidate`; `current_phase` records `phase1a` through `phase1d`.
Every declared phase report must contain the seven registered table classes,
and every matched row must equal the cumulative report across all columns—not
only its key. The structural validator fails on role, phase, report, provenance,
or alias disagreement.

## Validation hierarchy and gates

1. **Structural preservation:** original rows and normalized names, transit
   buses, source-zero-injection evidence, append-only provenance, registered
   attachment paths, residual-candidate class policy, and no S12/Kron admittance.
   Passive residual fitting is a later promotion gate, not part of the current
   Phase 1A structural pass.
2. **Local identity:** verify exact copied branch physics and the omitted-network
   injection fixture before any system comparison. The isolated zero-injection
   fixture is non-gating.
3. **Same snapshot:** apply a common documented aggregate 2019 input to S12 and S13;
   compare physical-circuit flows/currents, interface operators, terminal
   voltages, identically scoped NY losses, and reactive balance. Do not claim
   identical bus-level injections across the two network representations.
4. **Held-out response:** without refitting S13, test ±250 MW and ±500 MW zonal
   transfers, Zone-J/Zone-K load changes, external interchange changes, and
   one-circuit outages against S12 response.
5. **Public hours:** only after the preceding stages pass, reconstruct all six
   similarity-scaled 2019 hours with bounded AC dispatch closure.

| Metric | Mandatory gate |
|---|---:|
| Standard and Q-limit PF | 6/6 |
| Exact-operator interface MAE | ≤100 MW |
| Maximum exact-interface error | ≤200 MW |
| Dispatch movement | ≤10% of scaled NY load |
| Voltage/Q/trusted-branch violations | 0 |
| DLR circuit-current error versus S12 | ≤15% |
| Held-out current-change error | ≤15% |
| Reference pickup | <1 MW |

No runner may label S13 promoted unless all mandatory gates pass. Failed cases
remain diagnostic evidence and must not be published under promoted filenames.

## Operating-point and claim boundaries

The selected public hours preserve the 10,902.22 MW NPCC-NY loading scale. They
are similarity-scaled reconstructions of 2019 operating patterns, not raw-MW
reproductions of roughly 30 GW NYISO snapshots. S12 closed dispatch requires
large zonal movement and is a feasibility benchmark, not observed dispatch.

The PERFORM source does not establish historical automatic tap or phase-shifter
schedules for the relevant devices. Represent those controls as fixed snapshot
values or bounded calibration variables with documented uncertainty.

Because S13 retains the external NPCC network, P-32 interchange schedules must
be imposed as tie-flow constraints or physical controls with balancing
redispatch in the corresponding external area. Do not add S11/S12 boundary
injections on top of the retained external network.
