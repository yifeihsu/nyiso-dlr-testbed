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
8. Every adjusted original branch is registered as an aggregate residual.

Branch traceability is row-based, not just endpoint-pair based, because parallel
circuits can share endpoints. A topology-preservation gate must fail if an
original row moves, disappears, or changes endpoints.

## Admittance policy

Topology is addition-only; admittance is not blindly addition-only. Explicit
physical circuits can overlap transfer paths already embedded in original NPCC
aggregate branches. Adding both without adjustment would double-count series
admittance, charging, capability, losses, and interface flow.

The original row remains in place and is classified as an aggregate residual.
Its R/X/B may be refit to represent only the unmodeled remainder. A simple
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
pending.

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
original branches. Fit only registered overlapping aggregate rows and shunts.
Promotion remains blocked until every residual passes passive-admittance gates.

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

## Validation hierarchy and gates

1. **Structural preservation:** original rows, transit buses, append-only
   provenance, registered attachment paths, and no S12/Kron admittance.
   Passive residual fitting is a later promotion gate, not part of the current
   Phase 1A structural pass.
2. **Same snapshot:** apply identical PERFORM 2019 injections to S12 and S13;
   compare physical-circuit flows/currents, interface operators, terminal
   voltages, active losses, and reactive balance.
3. **Held-out response:** without refitting S13, test ±250 MW and ±500 MW zonal
   transfers, Zone-J/Zone-K load changes, external interchange changes, and
   one-circuit outages against S12 response.
4. **Public hours:** only after the first three stages pass, reconstruct all six
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
