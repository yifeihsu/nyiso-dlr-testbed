# Phase 1C source electrical construction checkpoint

`build_s13_phase1c_candidate` creates a separate **partial construction case**
with 170 buses, 315 branches, and the unchanged 62 Phase 1B generator records.
The historical Phase 1B case wrapper and seven canonical registers remain
unchanged. Output files use the `s13_phase1c_` prefix exclusively.

The source manifests select a connected 23-terminal, 53-element subnetwork
from the full PERFORM 2019 case. Millwood and East Garden City reuse existing
345-kV model terminals; 21 terminals are added. The mesh separates Dunwoodie
and Sprain Brook at 345/138 kV, West 49th Street at 345/138 kV, Tremont at
138/69 kV, East Astoria at 345/138 kV, Jamaica at 138/69 kV, Valley Stream,
Great Neck, Corona, Bruckner and the connecting source terminals.

The builder copies source R/X/B, ratings, transformer ratios, phase shifts
and status exactly. Only the unusable source zero angle bounds are neutralized.
Every copied electrical row is pinned by source row and a SHA-256 of the
UTF-8 source text with LF-normalized line endings. `PERFORM_ROW_*` identifiers
are source-row keys, **not assertions of independently resolved PSS/E circuit
IDs**. No added element is DLR-eligible.

All source loads, generators, shunts and voltage-control requirements are
recorded in the injection audit. They are not copied onto the retained NPCC
aggregate injections. Thus this checkpoint establishes source electrical
identity and passivity, not a solved operating model. In particular it is not
valid to interpret zero-injection receiving buses as calibrated NYC demand.

The physical source puts Sprain Brook and Dunwoodie in Zone I. The operator
register therefore separates H-to-I northern approaches, I-to-J paths, and
the selected K-to-J paths. It does not relabel Zone I as H to manufacture a
direct H-J cut. `measure_s13_phase1c_flows` accepts a solved case and reports
received-terminal active/reactive imports for those components and total
Zone-J net import, including the retained aggregate paths. It preserves losses
and flags every measurement as a model operator, not an exact public operator.

Remaining construction blockers are explicit:

- Lake Success lacks a resolved identity in the inspected source.
- CE UG remains an aggregate proxy; it is not silently merged with physical
  Dunwoodie. The source device placement must be reconciled with existing J/K
  aggregate loads and generators before operating qualification.
- Rows 91, 92, 95, 98, 237, 240, 241 and 242 are possible downstate aggregate
  overlaps. They remain unchanged, with terminal/injection correspondence and
  a passive multi-terminal residual fit required before acceptance.
- Public interface membership and independently resolved circuit IDs remain
  incomplete. No equivalent, source-control qualification, or promotion is
  inferred from local source-row tests.

Run `test_s13_phase1c_candidate` for nominal construction and adversarial
resistance, transformer, parent-identity, promotion, zone, device-audit and
circuit-ID tests. The standalone validator recomputes source admittance and
terminal-current identities, passivity and cumulative provenance, and requires
all operating-source and delivery flags to remain false.

`apply_s13_phase1c_operating_allocation(candidate, scenario)` is a separate
operating transformation after `build_electrical_reconstruction_inputs`.
It replaces the selected zonal load allocation with source-PD spatial shares
and moves bounded portions of existing zonal generation and Q capability to
source terminals. Every zonal P/Q load and PG/PMIN/PMAX/QG/QMIN/QMAX sum is
conserved. Physical-unit capacity transfers are capped by gamma-scaled source
limits. The source West 49th Street Q limits of +/-9900 MVAr are placeholders;
they are never copied. Its added Q-only equivalent receives a bounded portion
of existing Zone-J reactive capability, with no additional active generation.
Existing shunts remain unchanged and source shunt qualification stays false.

The allocator rejects repeated application. Its returned `Pg_prior_mw` and
`Pg_sigma_mw` must replace the reconstruction control vectors because four
aggregate generator rows are appended in the summer-peak example. These are
reconstructed spatial assumptions, not observed current-vintage placements.
`test_s13_phase1c_operating_allocation` verifies eight conservation, identity,
bounded-control and failure-contract checks. The first representative bounded
S1 reconstruction still failed to converge; no solved-source qualification is
claimed by the allocation tests.
