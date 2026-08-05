# Phase 0: source-backing the NPCC NY core

**Date:** 2026-08-05
**Scope:** corrections that add **no buses and no branches**, keeping the
NPCC-derived structure intact.
**Structural parent:** `npcc_ny_lite_s7_seven_interface_perform_direct_candidate`
(143-bus full NPCC-derived case).
**Diagnostic application:** `npcc_ny_lite_s11_dlr_pf_base` (49-bus NY-only
benchmark). S11 is not the promoted NPCC testbed.

Phase 0 is the foundation for the pending
`npcc_ny_lite_s13_npcc_augmented_2019` model. It corrects metadata and ratings
without changing topology; it does not promote a new operating case by itself.

## What ships

| File | Role |
|---|---|
| `build_ny_core_cutset_reference.m` | derives the reference from the PERFORM 2019 source |
| `ny_core_cutset_reference.csv` | 14 zone-pair boundaries: circuits, ΣRATE_A, snapshot MW, x_parallel, X_th |
| `ny_core_official_share_reference.csv` | NYISO monitored subset vs full-cut flow, per interface |
| `ny_core_corridor_reference.csv` | named corridors for core branches with no zone-pair counterpart |
| `ny_core_ptdf_reference.csv` | 150 (canonical transfer, cut) DC sensitivities |
| `apply_ny_core_phase0_corrections.m` | applies ratings and, only when explicitly enabled, fitted reactances to a case |

```matlab
addpath('System Matpower Format'); addpath('System Matpower Format/NY_Lite');
build_ny_core_cutset_reference();
mpc = apply_ny_core_phase0_corrections(loadcase( ...
    'npcc_ny_lite_s7_seven_interface_perform_direct_candidate'));
```

For the reduced diagnostic only:

```matlab
diagnostic = apply_ny_core_phase0_corrections( ...
    loadcase('npcc_ny_lite_s11_dlr_pf_base'));
```

## Zone D correction (prerequisite)

PERFORM's area field codes the whole Massena/Moses complex — St. Lawrence-FDR
hydro (16 × 57 MW), the HQ interconnections at Massena and Moses, and the
Massena–Marcy 765 kV line — as area 69 = Zone E. NYISO places it in Zone D.
`ny_bus_zone_map.csv` already had this right, so the correction is applied to
the **PERFORM side** (7 buses, by substation name) before any cut is computed.

Without it the D-E reference is meaningless. With it, Moses South becomes a
well-posed D-E cut for the first time.

## Interface definition audit (measured, not asserted)

Comparing each NYISO monitored-circuit subset against the full zone boundary it
sits on, at the solved PERFORM snapshot:

| Interface | Subset MW | Cut MW | share | verdict |
|---|---:|---:|---:|---|
| Dysinger East | 746.9 | 906.9 | 0.824 | ok |
| Moses South | 1238.4 | 1474.0 | 0.840 | ok |
| Total East (E-F+E-G+D-F) | 2661.9 | 3181.7 | 0.837 | ok |
| Central East | 1613.9 | 1841.6 | 0.876 | ok |
| West Central | 56.6 | −126.4 | **−0.448** | subset opposes its own boundary |
| UPNY-ConEd | 4839.1 | 3996.5 | **1.211** | subset exceeds the whole boundary |
| Dunwoodie South | 1420.7 | 1024.6 | **1.387** | subset exceeds the whole boundary |

A subset-to-net-cut share above one is not interpretable as a direct fraction
without checking counterflow and operator overlap. Here the topology identifies
specific defects: UPNY-ConEd sums the series pair Pleasant Valley→Wood Street
and Wood Street→Millwood (Wood Street is a pure transit node), while Dunwoodie
South mixes four Con Ed–LIPA K→J circuits into an I→J operator. A properly
oriented, nonintersecting cutset avoids those double-counting and mixed-boundary
defects. Rebuilding the two S12 operators needs new nodes → Phase 1.

The four consistent shares (0.82–0.88) are consistent with a monitored subset
of a boundary. Their agreement supports the internal consistency of the cut
definitions and Zone D correction; one solved snapshot is not independent
validation of either interpretation.

## 0.2 Transit bus zones

9001 KNICKERBOCKER, 9002 WOOD STREET, 9003 EAST GARDEN CITY are absent from
`nyiso_bus_zone_map` by design (it errors on buses the case lacks, and must stay
loadable against the 140-bus baseline). Cases normally carry them in
`userdata.ny_lite.transit_zone_metadata`.

| Case | Status before |
|---|---|
| `npcc_ny_lite_v0_baseline` (140) | buses absent — unaffected |
| `npcc_ny_lite_s11_dlr_pf_base` (49) | **9001, 9003 unzoned** |
| `..._s7_..._direct_candidate` (143) | carries the userdata — unaffected |

The 49-bus diagnostic case was the affected one. Zone-cut operators match on
zone pairs, so branches touching an unzoned bus were silently dropped — losing
the CE UG → East Garden City I-K (Con Ed–LIPA) crossing entirely. This finding
repairs the diagnostic benchmark; it does not change the S7 structural parent
or the pending S13 topology.

`attach_nyiso_zone_metadata` now carries a presence-guarded transit default
table (G / G / K, from PERFORM areas 71 / 71 / 75) replacing a hardcoded 9002
special case. Result: `ConEd_LIPA_IK` 1→2 branches, `UPNY_ConEd` 3→5 branches in
the 49-bus case; 140- and 143-bus cases unchanged.

Knickerbocker is synthetic (no PERFORM counterpart) and sits on the
Leeds–Pleasant Valley path; both neighbours are G, so G keeps that path
intra-zone. Labelling it F would manufacture two spurious F-G crossings.

## 0.1 / 0.3 / 0.4 Ratings

Each boundary group takes its PERFORM aggregate ΣRATE_A, allocated across the
core branches in proportion to 1/x.

| Cut | before (MVA) | after (MVA) | note |
|---|---:|---:|---|
| A-B Dysinger East | 1,580 | 5,581 | was 3.5× **under**-rated |
| B-C West Central | 7,500 | 3,935 | |
| D-E Moses South | 5,000 | 8,937 | |
| E-F Central East | 7,500 | 5,389 | |
| F-G Total East | 3,716 | 4,604 | |
| G-H UPNY-ConEd | 9,932 | 10,243 | |
| H-I Millwood South | 15,000 | 7,296 | was 2.1× over-rated |
| I-J Dunwoodie South | 22,500 | 5,804 | was 3.9× over-rated |
| I-K / J-K ConEd-LIPA | 7,500 / 5,000 | 3,850 / 2,950 | |
| A-C | 2,500 | 620 | 4× over-rated bypass (0.4) |
| C-F | 2,500 | 1,216 | Fraser–Gilboa corridor (0.3) |

**Correction to the earlier recommendation on C-F.** I previously suggested
deleting or relabelling `GILBOA(F)–BINGHAMTON(C)` as fictional. That was wrong.
It is inherited from the original 140-bus NPCC baseline, its x=0.0485 pu ≈ 58 Ω
≈ 96 miles at 345 kV is a plausible Southern-Tier→Catskills corridor, and it
almost certainly represents Fraser–Gilboa with Fraser (a Zone E substation with
no NPCC node) landed on the Binghamton bus. Under the composite Total East
boundary `{A..E}|{F..K}` a C-F branch is *already inside* Total East, and
Fraser–Gilboa genuinely is a Total East element — not a Central East one. So it
is correct where it matters; only the rating was wrong. It is now rated from the
real circuit (1,216 MVA) via the named-corridor mechanism.

**Protected branches.** Branches already carrying PERFORM-direct parameters —
GILBOA–LEEDS (38-39), PLEASANT_VLY–WOOD_STREET (73-9002), WOOD_STREET–MILLWOOD
(9002-74) — are excluded from both the multiplier and the reallocation. Without
this the 1/x split inside F-G re-rated GILBOA–LEEDS, a real 1,216 MVA circuit,
down to 340 MVA because the parallel New Scotland–Leeds equivalent has ~12× its
susceptance.

## 0.5 Reactances — **off by default, opt in with `fit_reactance`**

One multiplier per boundary group, fitted so the core's cut PTDFs match
PERFORM's over canonical zonal transfers, regularised toward m = 1
(`reg_weight` 0.30, bounds [0.25, 4]).

**It is off by default because it was measured against the project's own
acceptance metric and it loses.** See the validation section below.

Two other targets were tried and rejected:

- **Parallel-x of the crossing circuits.** Dominated by the smallest crossing
  reactance. For D-E that is short 115 kV taps inside the Massena area which
  carry no boundary transfer, giving a meaningless 0.00036 pu target.
- **Boundary Thévenin reactance X_th.** Confounded by intra-zone spread — large
  in PERFORM's fine-grained zones, tiny in the coarse core. Fitting it inflated
  G-H ×13, H-I ×17, I-K ×20 and made the independent cut-PTDF check *worse*
  (0.187 → 0.283).

**The honest ceiling is modest.** Cut-PTDF normalised RMS (the 49-bus row is
diagnostic evidence only; the 143-bus row governs the structural parent):

| Case | before | after | reduction |
|---|---:|---:|---:|
| 49-bus core | 0.1878 | 0.1489 | 20.7% |
| 143-bus full | 0.3199 | 0.2974 | 7.0% |

Unregularised it reaches ~27% on the 49-bus case, but only by pushing
multipliers onto their bounds; widening bounds from [0.25, 4] to [0.1, 10]
changes nothing, so the regularizer binds, not the bounds. **The remainder is
structural** — the fit was trying to correct a topology difference (zone I is
one bus in the core, a six-bus mesh in PERFORM) with corridor impedance.
Reactance is the wrong knob for that. This quantifies the case for Phase 1.

`BR_R` scales with `BR_X` to hold X/R constant. `BR_B` does **not** scale by
default: charging on a reduced equivalent is not physically tied to its
equivalent reactance, and scaling it inflated total charging 1,725 → 21,109 MVAr
in testing, against a source whose reactive load is already ≈ 0 MVAr.

## Validation (MATLAB R2026a, MATPOWER 8.1)

`validate_phase0_interfaces.m` rebuilds the S7 direct-PERFORM scenario path for
the selected candidate and scores the six 2019 scaled scenarios before and
after. **The "before" run reproduces the published S7 baseline exactly** —
all-hour 0.489612, train 0.295784, holdout 0.193827 — so the harness is sound.

### Ratings only (the default): objective-neutral, source-backed correction

`RATE_A` does not enter the power flow. With `fit_reactance = false` the
impedances are bit-identical, so the interface objective is **exactly
unchanged at 0.489612** while 33 branches gain source-backed ratings.

| metric | before | after |
|---|---:|---:|
| all-hour objective | 0.489612 | 0.489612 |
| PF convergence | 6/6 | 6/6 |
| placeholder ratings | 72 of 81 | 41 of 81 |
| distinct RATE_A values | 4 | 33 |

On the standalone 49-bus diagnostic case, rated-branch utilisation goes mean
0.232 → 0.302 and max 1.385 → 1.158: peak overload severity falls from 38.5%
to 15.8%, and more branches show as loaded because the prior case hid real
loading behind fake headroom (I-J alone was rated 22,500 MVA against a true
5,804).

### Reactance fit: a measured regression, hence off by default

| | all-hour J | train | holdout |
|---|---:|---:|---:|
| before | 0.489612 | 0.295784 | 0.193827 |
| with reactance fit | **0.561823** | 0.319691 | 0.242132 |

Per-interface MAE (MW), before → with fit:

| Interface | before | after | |
|---|---:|---:|---|
| Dysinger East | 133.5 | **113.3** | better |
| West Central | 215.6 | **192.6** | better |
| Moses South | 53.7 | 53.8 | flat |
| Central East | 110.1 | 148.7 | worse |
| Total East | 361.9 | 388.5 | worse |
| UPNY-ConEd | 105.5 | 110.8 | worse |
| Dunwoodie South | 276.6 | 308.2 | worse |

It helps exactly the two corridors diagnosed as too stiff and hurts everything
east of them. **The reason is structural.** The core has no E-G corridor at all
(PERFORM: 7 circuits, 3,054 MVA, Coopers Corners–Rock Tavern), so every
eastbound MW is forced through E-F. Matching PERFORM's E-F PTDF then requires
making E-F *stiffer*, reducing its flow — and the S7 dispatch already underflows
every eastern target. No reactance setting can substitute for a missing path.

A share-corrected scoring variant (comparing `share × cut_flow` to the target,
using the measured 0.82–0.88 shares) was tried and **does not rescue it**:
0.489612 → 1.044018 before, 1.138820 after. The model already underflows, so
scaling the cut flow down widens the gap. The prevailing "cut = interface"
convention is only accidentally reasonable — it happens to offset the underflow
bias.

This motivates testing the missing E-G path on the full 143-bus parent. It does
not establish that an NY-only 49-bus overlay should be promoted, and topology
changes must be rescored with operating-point closure re-derived for the changed
network.

## Known gaps left open

1. **Intra-zone branches are not re-rated.** Only boundary branches have an
   unambiguous PERFORM counterpart. Of the 47 intra-zone branches in the 49-bus
   core, 10 have endpoints matching a PERFORM substation pair. After Phase 0:
   all 36 boundary branches are source-backed (33 re-rated + 3 protected), 47
   intra-zone branches still carry placeholders.

2. **The chronic Niagara West–Huntley overload is NOT fixed, and the earlier
   attribution of it to the A-B cut under-rating was wrong.** It is the *only*
   overloaded branch in all six 2019 scenarios, before and after Phase 0:

   | scenario | worst overload (unchanged by Phase 0) |
   |---|---|
   | S1 summer peak | NIAGARA W–HUNTLEY 800/790 |
   | S2 winter peak | NIAGARA W–HUNTLEY 832/790 |
   | S3 shoulder | NIAGARA W–HUNTLEY 1131/790 |
   | S4 high NYC/LI | NIAGARA W–HUNTLEY 865/790 |
   | S5 high Total East | NIAGARA W–HUNTLEY 819/790 |
   | S6 low Total East | NIAGARA W–HUNTLEY 885/790 |

   It sits on an *intra-zone-A* branch carrying a 790 MVA placeholder. It cannot
   be fixed by substation name matching either: **PERFORM has no direct
   Niagara–Huntley circuit at all** (they connect indirectly via the 230/345 kV
   network), so this branch is a genuine equivalent with no single-circuit
   counterpart. Rating it needs a sub-zonal cutset abstraction — Phase 1.

3. **West Central, UPNY-ConEd and Dunwoodie South operator definitions** remain
   broken in the S12 operator file. Cutset semantics avoid the defect in the
   NPCC core, but the S12 side is unrepaired.

4. Everything in the operating-point layer — γ-scaling, ≈0 reactive load,
   the capability-proportional dispatch prior, absent PARs and external network
   — is untouched by Phase 0 and unchanged by it.
