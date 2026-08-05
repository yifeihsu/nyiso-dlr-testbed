# S14-NYISO: retained-network DLR operating model

**Target case:** `npcc_ny_lite_s14_nyiso_dlr_operating_model`
**Status:** pending; no S14 case, reducer, or promotion artifact exists
**Construction and validation parent:** `npcc_ny_lite_s13_npcc_augmented_2019` (`S13-FULL`)
**Reference oracle:** `npcc_ny_lite_s12_perform_retention_core`
**Highest-fidelity source:** full PERFORM 2019 case

## Role and scope

S14-NYISO is the only model in the current hierarchy that may become the
promoted DLR operating model. It will preserve the NPCC-derived NYISO
subnetwork and its traceable bus/branch identities while replacing only the
non-NY NPCC mesh with a validated AC multi-terminal boundary equivalent.

S13-FULL remains available unchanged as the construction, provenance, and
direct-reduction reference. S12 remains an independent NYISO behavior oracle.
Neither S13-FULL nor S12 is the DLR delivery model.

S14 must retain:

- every original NPCC bus assigned to NYISO Zones A-K;
- every branch with both endpoints in the retained NYISO set;
- every Phase 1A-1C source-backed NYISO terminal and physical circuit;
- all five DLR physical circuits and their physical terminals;
- NYISO loads, generators, shunts, and required voltage/Q controls;
- the NY-side terminal of every retained external tie; and
- only the selected first external terminals needed to distinguish physical
  boundary facilities and schedule groups.

S14 may eliminate:

- internal Ontario, Quebec, New England, and PJM buses;
- external generators and loads after their effects are mapped exactly once;
- external branches that are not retained tie facilities; and
- first external terminals that are not needed for a passive, controllable
  multi-port realization.

No S12 Ward/Kron branch, historical S11 boundary injection, or single unlimited
external slack may enter S14. Only one-to-one physical circuits with completed
conductor and weather provenance may be DLR-eligible.

## Safe implementation order

1. Preserve the completed S13-FULL Phase 1B UPNY-ConEd checkpoint.
2. Complete the S13-FULL Phase 1C downstate H-J/K-J topology.
3. Complete passive residualization of overlapping NYISO aggregate branches.
4. Freeze a cumulative S14 retention set from the completed S13-FULL topology.
5. Derive and passively realize the non-NY external multi-port.
6. Validate the same solved state in S13-FULL and S14.
7. Add bounded regional and facility-level interchange controls.
8. Run independent S12/PERFORM behavior tests and the six public-hour gates.

A Phase 1A retention inventory may be used for diagnostics, but it may not
freeze the final ports or equivalent. The completed Phase 1B overlay and the
pending Phase 1C topology change both the required retained detail and which
internal NPCC branches overlap the physical overlay.

## Historical Phase 1A provisional inventory

The immutable S13-FULL Phase 1A checkpoint contains 53 NYISO-side buses: 46 original
NPCC NY buses, three S7 transit buses, and four Phase 1A PERFORM terminals. It
contains 88 NY-internal branches: 68 original NPCC rows, 13 S7 rows, and seven
Phase 1A physical rows.

Ten active NY/external tie rows reach ten first external terminals. Retaining
those terminals gives a provisional 63-bus skeleton with 88 internal rows and
ten source tie rows. The remaining 155 external-external rows, including the
existing connection between external terminals 124 and 125, belong to the
eventual external-network reduction. These are historical Phase 1A diagnostic
counts and are already stale relative to the cumulative Phase 1B checkpoint.
They are a read-only manual design audit, not a promotion gate or canonical
artifact. No S14 retention builder may be created until Phase 1C and the
required S13-FULL construction-source gates are complete.

| Boundary group | NY-side buses | Provisional first external terminals |
|---|---|---|
| HQ | 48 Moses E | 100 PHAS |
| Ontario | 54 Niagara W | 102 BP76; 103 PA27 |
| ISONE | 37 New Seathed; 73 Pleasant Valley | 29 Northfield; 35 Southingten |
| PJM | 60 Dunkirk; 66 Watercure; 67 WRHL; 75 Ramapo; 81 Goethals | 140 TE; 134 Homer City; 138 E Tomano; 124 Branchburg; 125 Lindon |

The current topology distinguishes only these four regional AC cuts. It does
not yet establish individual physical landing/control paths for NPX 1385, NPX
CSC, HTP, Neptune, or VFT. Those schedules remain unavailable rather than being
silently assigned to a generic regional source.

## Reduction contract

Use MATPOWER internal indexing and partition the external-network nodal
equation by retained boundary ports `b` and eliminated external buses `e`:

```text
[Ybb Ybe] [Vb] = [Ib]
[Yeb Yee] [Ve]   [Ie]
```

With net current injection defined positive into the network, eliminate `Ve`
with a sparse linear solve, never an explicit inverse:

```text
Yext_eq = Ybb - Ybe * (Yee \ Yeb)
Iext_eq = Ib  - Ybe * (Yee \ Ie)
Yext_eq * Vb = Iext_eq
```

The implementation must:

- select retained and eliminated buses by registered bus ID, not area number
  alone;
- fingerprint all source branch R/X/B, tap, phase shift, status, and shunt data;
- remove external devices exactly once, including devices at retained external
  terminal buses, before applying the equivalent injection/control model;
- register the complex multi-port matrix, scenario injection vector, synthesis
  method, numerical conditioning, and source-case hash;
- preserve regional coupling, reactive exchange, and external losses; and
- fail if the eliminated block is singular, ill-conditioned beyond the stated
  gate, or cannot be represented passively at the required accuracy.

The Phase 1A algebraic audit produced a reciprocal passive multi-port with ten
ports and 22 nonzero unordered couplings. One retained terminal has no native
external admittance. A naive unit-tap branch plus diagonal-shunt synthesis
requires negative-conductance shunts, so that realization is prohibited. Use a
passive synthesis with taps/internal nodes or retain additional external buses.
These findings are preliminary and non-gating until a committed reduction
audit regenerates the multi-port and its passive-realization evidence.

## Planned artifacts

The implementation phase will create, but this checkpoint does not fabricate:

- `build_s14_nyiso_retention_set.m`;
- `s14_nyiso_retention_set.csv`;
- `reduce_external_npcc_to_boundary_equivalent.m`;
- `s14_external_multiport_register.csv`;
- `s14_boundary_control_register.csv`;
- `validate_s14_reduction_artifacts.m`;
- `validate_s14_against_s13_full.m`; and
- `validate_s14_promotion.m`.

The retention register must include bus ID, normalized name, zone, base kV,
retention reason, boundary group, physical/equivalent class, source row, and
confidence. Every synthesized branch, shunt, source, and control must have an
equivalent-parameter register row and a reproducible source pointer.

## Boundary controls

Represent each available external schedule with a registered control group:

- landing bus or buses;
- scheduled active power and tolerance;
- reference reactive power and bounded Q range;
- voltage-control mode and setpoint bounds;
- balancing participation; and
- source, timestamp, and confidence.

For multiple AC ties to one region, constrain the aggregate interchange while
letting the AC multi-port determine physical sharing. Do not independently fix
every tie flow unless the source provides separate controllable facilities. DC
or phase-controlled facilities require explicit device models; a passive AC
Kron equivalent cannot recreate their schedules.

## Validation and promotion gates

Direct S13-FULL/S14 same-state gates are tighter than independent S12 behavior
gates because S14 is reduced directly from S13-FULL:

| Metric | Mandatory initial gate |
|---|---:|
| Retained-bus voltage RMSE | <= 0.005 pu |
| Maximum retained-bus voltage error | <= 0.015 pu |
| NYISO interface-flow error | <= 50 MW per interface |
| DLR-circuit current error | <= 5% |
| NYISO active-loss error | <= 5% |
| Boundary reactive-power error | <= 10% or registered MVAr band |
| Equivalent passivity | mandatory |
| Unregistered or negative-resistance element | 0 |
| Unlimited external Q or slack pickup | 0 |

After direct reduction passes, validate NYISO physical-circuit flows, voltages,
losses, and held-out transfer/outage responses against S12 and full PERFORM.
Then reconstruct the six similarity-scaled 2019 public hours with bounded
dispatch and explicit movement reporting. Only `validate_s14_promotion.m` may
mark an S14 artifact promoted, and it must recompute every gate from canonical
committed artifacts rather than trust stored status flags.
