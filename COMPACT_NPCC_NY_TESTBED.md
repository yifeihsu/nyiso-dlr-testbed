# Compact NPCC NY electrical testbed

**Historical 51-bus benchmark.** The subsequent [66-bus 2025 research baseline](COMPACT_NY_2025_DLR_METHODOLOGY.md) adds NYISO demand/interface calibration and assumed thermal realizations. This document and its saved artifacts retain their original benchmark scope.

The active direction is a **small NY-only testbed that retains the NPCC backbone and adds a few explicit source corridors**. The operating case has a hard limit of **200 buses**. The selected design has **51 buses, 92 branch records, 87 active branches, and 35 generator records**. It preserves all 46 original NPCC NY bus IDs, the three S7 transit buses, and two additional corridor terminals.

This is a preliminary electrical testbed at the **NPCC benchmark scale**, with gross NY demand of **10,902.2198 MW**. It is not an attempt to reproduce the full PERFORM load level or current NYISO operations. The [generated operating results](output/compact_npcc_ny/COMPACT_NPCC_NY_RESULTS.md) and independent replay establish electrical qualification under the declared benchmark assumptions. The contract alone does not establish feasibility. The `dlr` name indicates the intended later research use; no thermal model or DLR-ready status is supplied by this work.

## Selected construction

The construction starts from S7 with Phase 0 rating corrections. It does not automatically include the Phase 1A E–G overlay, the Phase 1C downstate mesh, or a wholesale PERFORM regional expansion.

| Representation | Buses | Branch records | Active branches |
| --- | ---: | ---: | ---: |
| Full construction used for provenance and benchmark-boundary preparation | 145 | 257 | 252 |
| NY-only operating testbed | 51 | 92 | 87 |

All 246 parent branch records remain in the full construction. Parent rows **88, 89, 94, 235, and 236** are deactivated with explicit disposition records. Eleven original-source circuit records are appended:

| Corridor detail | Original PERFORM branch rows |
| --- | --- |
| Pleasant Valley–East Fishkill–Wood Street–Millwood | 1389, 1390, 1391, 1392, 1689, 1690, 1734, 1735 |
| Ramapo–Ladentown–Buchanan | 1577, 1576, 1738 |

Electrical parameters, endpoint correspondence, individual source-circuit identities, and active/inactive contributions belong in the construction registers. Source row numbers remain lookup pointers alongside stable source keys. Existing equivalents are not kept active in parallel with their registered replacements. The known Pleasant Valley–Wood Street row-235 exact-parallel proof remains a specific piece of evidence; it does not turn every other retirement into a proven one-to-one physical facility replacement.

The 200-bus ceiling is a constraint, not a target to fill. Any future addition must remain a focused, registered corridor change while preserving the NPCC NY backbone. The compact builder must not automatically expand to hundreds of PERFORM buses to obtain a numerical solution.

## Benchmark load, generation, and boundary accounting

The NY-only case uses fixed boundary P/Q derived from a **matched NPCC benchmark reference**. These values must match the benchmark load and generator assumptions used for the compact case. They are reproduced benchmark quantities subsequently held fixed, not measured present-day interchange. The separate 20-record PERFORM exchange schedule is not used as this case's boundary schedule.

Positive boundary power enters NY; negative power is an export. A matched benchmark can have net exports. The model preserves that sign and quantity rather than imposing presumed contemporary imports. At each landing, gross demand and external injection remain separately registered before effective demand is assembled:

```text
P_effective_load = P_gross_benchmark_load - P_boundary
Q_effective_load = Q_gross_benchmark_load - Q_boundary
```

Boundary records have no undeclared slack or voltage-control capability. Each exchange is counted once, separately from modeled NY generation. Removing the outside network requires explicit accounting of its benchmark exchange; it does not justify an unregistered injection change.

The **35 NY generator records are inherited benchmark representations**:

| Record family | Count | Capability interpretation |
| --- | ---: | --- |
| Original NPCC generator identities carried through S7 | 21 | Inherited S7 aggregate capability bounds, including earlier S4 changes; total PMAX 7,992.895 MW |
| S4 P-only equivalents carried through S7 | 14 | Assumed active-power equivalents with zero Q capability; total PMAX 9,200 MW |

The compact model preserves **inherited S7 aggregate capability bounds**. It does not restore or claim original NPCC physical-machine bounds: S4 had already changed PMAX on some original identities. Broad inherited Q envelopes, including ±999 and ±9,999 MVAr where present, are explicit benchmark aggregate assumptions. Numerical compliance with them is not validation of physical machine capability.

Selected PERFORM corridor data supplies electrical network detail. It does not authorize importing all PERFORM generator records, the large regional candidate's separate Marcy support, or additional source shunts into this compact benchmark. Any later injection or control change needs its own accounting and assumption record.

## Preliminary electrical asset register

The register must distinguish a source AC circuit's electrical identity from an established overhead or cable realization. Required traceability includes:

- Candidate identity and fingerprint; original parent row/key; pinned source case, hash, row, circuit key, and any identity ambiguity.
- Model and source endpoints, orientation, both terminal base-kV values, corridor/parallel grouping, and device kind.
- R/X/B, tap, phase, status, static MVA ratings and their provenance; replacement or retirement disposition and overlap evidence.
- Recomputed from/to RMS branch-terminal current definitions tied to an audited benchmark operating point.
- Physical-realization status, interpretation of the computed current, and an explicit thermal-exclusion reason.

All current thermal eligibility remains false. A source electrical match does not establish overhead construction, conductor resistance at a stated temperature, conductor geometry, route/weather exposure, or ampacity. An inherited aggregate's model-branch current is not an individual conductor current. Transformers and fixed boundary injections cannot inherit an overhead-conductor thermal model. Static MATPOWER MVA ratings are retained electrical constraints, not newly verified conductor ampacities.

## Contract, acceptance, and reproduction

`compact_npcc_model_contract.m` is standalone. It declares the NY-only scope, hard ceiling, chosen corridors, benchmark scale, generator interpretation, and separate electrical/contemporary/thermal statuses. It does not alter the older `research_model_contract.m` modes.

Calling `compact_npcc_model_contract(candidate)` checks only the bus budget and original NY bus identity policy. It does not validate the full construction or accept a solved operating point, and it never inherits a candidate's self-reported qualification flags. The focused contract tests reject oversized cases, missing original NY buses, duplicate IDs, and nonfinite IDs; they also check that benchmark assumptions cannot become observation, physical-capability, or thermal claims.

The compact numerical workflow must separately check construction provenance and overlap disposition, fixed gross-load/boundary accounting, AC balance, voltage and branch limits, and all declared S7 benchmark P/Q envelopes including the reference. An independent fixed-input power flow must reproduce the accepted operating result without rerunning its optimizer or silently changing loads, bounds, or boundary injections. Failed attempts remain identifiable as failed attempts.

Entry points from the repository root are:

```matlab
out = run_compact_npcc_ny_testbed;
replay = replay_compact_npcc_ny_testbed;
```

The MATPOWER case name is **`npcc_ny_compact_dlr_testbed`**, and artifacts belong under **`output/compact_npcc_ny`**. Generated operating and replay artifacts determine electrical qualification and numerical metrics. This specification supplies neither an automatic success status nor a contemporary/DLR promotion.

## Preserved references and later work

The 878-bus Package B regional candidate, its immutable source/reference inputs, loaders, and comparison artifacts remain available as an **optional historical electrical reference**. They are not the compact operating target or a mandatory regional-expansion step. Earlier NPCC, S7, and construction checkpoints retain their original provenance roles.

Contemporary asset/operating validation and thermal implementation remain separate future work. The current objective is a reproducible small electrical testbed with honest benchmark assumptions and source-corridor/current traceability.
