# Topology audit for the 15 October 2026 weekly report

Read-only audit of existing model sources and delivery tables. Checkout verified: `codex/s13-phase1b-upny-coned`, HEAD `0e73b46fed7d9e859d7f1683be019b169270d095`. This audit does not rerun power flow or alter a model. Counts below distinguish historical construction stages from the current Moses-repair delivery.

## Slide-ready model lineage

| Representation | Bus count | AC representation | Meaning |
| --- | ---: | --- | --- |
| Authors' released final NYgrid, supplied 2019 inputs | 57 | 94 AC branches; 271 generator records; four DC-link records | Correct comparison baseline, pinned author release |
| Our unreduced 2019 structural counterpart | 140 | 225 AC branch records; 271 generator records; four DC-link records | Preserves NPCC bus identities; separate derived model, not the released 57-bus benchmark |
| Downstate station-detail construction | 191 | 410 common-axis records; 336 active at historical year-end construction stage | 140 original buses plus 51 station/terminal representations; nine predecessor aggregates replaced |
| Slim DC representation, historical construction stage | 148 | 274 records, 265 active year-end: 216 original + 14 source circuits + five declared connections + 30 equivalents | Retains all 140 original buses plus eight 345-kV ports; eliminates 43 added passive buses |
| Current loss-consistent AC delivery | 148 retained; 266/267 detailed | 485/488 detailed branch rows before/after Dover; 410/413 parent corridor records | Exact complex-admittance reduction and recoverable detailed voltages/currents; 1,466 generator rows and six modeled transfer records |

Sources: `NYGRID_RELEASED_2019_COMPARISON.md:3-7`; `NYGRID_2019_DLR_REBUILD.md:21-38`; `NYGRID_2025_DOWNSTATE_REFINEMENT.md:41-55`; `NYGRID_2025_SLIM_DOWNSTATE.md:53-80`; current delivery `output/nygrid_2025_moses_repair/delivery/docs/NYGRID_2025_MOSES_REPAIR_MODEL_STRUCTURE.md:9-42` and `delivery/structure_inputs/structure_export_summary.json`.

The current 267 count is **not 267 substations**: 140 original buses + 51 station-detail additions + 75 numerical section buses + one Dover regulated port. The retained solution has 148 voltages; 43 additional terminals plus 75 numerical points and one regulated port are eliminated. Before Dover, omit the regulated port (266). This is not a successive physical expansion from 191 to 267 substations.

The original raw author download has 140 buses / 227 AC branches / 48 generators; the paper describes 233 branches. That six-branch source-version discrepancy remains unresolved. The released builder arithmetic is 227 - 3 remote ties + 2 aggregate rows - 1 AC-to-controlled-transfer deletion = 225 unreduced final AC rows. Do not use the paper's 233, downloaded 227, derived 225, or final released 94 interchangeably. Source: `NYGRID_2019_DLR_REBUILD.md:21-38` and `output/nygrid_2019_full_stage1/paper_source_discrepancy.json`.

## What changed geographically

All 140 original NPCC bus identities survive in the current retained set. The set contains 54 New York buses and 94 original external buses (36 ISONE, 31 Ontario, 27 PJM). This preserves the NPCC backbone and regional boundary structure; it does not mean every inherited R/X/B value or control is unchanged in the later synthetic AC model.

| Added retained port | Bus ID | Role in the refined transmission paths |
| --- | ---: | --- |
| East Fishkill, 345 kV | 10858 | Separates Pleasant Valley–East Fishkill and East Fishkill–Wood Street parallel sections |
| Wood Street, 345 kV | 10902 | Junction of Pleasant Valley, East Fishkill and Millwood paths |
| Ladentown, 345 kV | 10774 | Separates Ramapo–Ladentown and Ladentown–Buchanan |
| Dunwoodie, 345 kV | 10593 | Westchester bulk receiving port; distinct from Sprain Brook detail |
| East Garden City, 345 kV | 10589 | Long Island bulk receiving port; distinct from inherited RAV A-3 proxy |
| Gowanus, 345 kV | 11129 | Brooklyn receiving port, including Goethals-area attachment |
| Rainey, 345 kV | 11130 | Queens receiving port; exposes Rainey–Corona project response |
| Cricket Valley, 345 kV | 20001 | F83/F84 junction between Pleasant Valley and the New England/Dover corridor |

Sources: `NYGRID_2025_SLIM_DOWNSTATE.md:26-50`; `output/nygrid_2025_slim/network/retained_station_rationale.csv` (all eight data rows); current structure report lines 26-35. Pleasant Valley (73), Millwood (74), Ramapo (76), Buchanan (77) and Goethals (81) are existing NPCC buses, not new additions.

The historical 51 additions comprise 38 historical electrical-source terminal rows and 13 public project/plant/proxy terminal rows. These are voltage-level bus representations, not 51 newly constructed substations. Their accounting-zone counts are G=6, I=5, J=27, K=12, external/NA=1. Multiple voltage levels can occupy one station. Six UNKNOWN/TAP source labels remain unresolved; do not invent station names.

Regional examples beyond the retained eight:

- Hudson/Westchester: Sprain Brook 345/138, Dunwoodie 138, the Cricket Valley–Dover–Long Mountain corridor, and an idle Knickerbocker placeholder.
- NYC: East Astoria 345/138, Farragut, Leonard Street, West 49th Street 345/138, East 13th Street, Bruckner, Tremont, North Queens, Corona, Jamaica, Vernon, NYPA Annex, Greenwood and Fox Hills, with explicit RCC PAR ports.
- Long Island: Shore Road 345, East Garden City 69, Great Neck 69, West Hempstead 69, Valley Stream 69 and historical 69-kV connection/tap detail; East Hampton 69 is a declared plant-terminal proxy in the optional asset mapping.

Authoritative complete names and IDs: `output/nygrid_2025_downstate/network/bus_register.csv`, data rows with `identity_role != original_parent` (51 rows). Source-zone naming and geographic coordinates must not be substituted for accounting-zone definitions.

## Corridors and replacement policy

The nine replaced original branch records are 32, 87, 88, 89, 91, 92, 93, 94 and 95. Their records remain as inactive provenance. The detail is not placed as a complete new parallel network on top of the old aggregate.

| Original row | Original endpoints | Refined interpretation |
| ---: | --- | --- |
| 32 | Southington (35)–Pleasant Valley (73) | Explicit Cricket Valley / Long Mountain / Dover path plus a declared Southington–Long Mountain boundary equivalent |
| 87 | Pleasant Valley (73)–Millwood (74) | Historical Pleasant Valley–East Fishkill–Wood Street–Millwood mesh plus direct Pleasant Valley–Wood Street parallel circuits |
| 88 | Millwood (74)–Buchanan (77) | Historical parallel-circuit detail |
| 89 | Millwood (74)–CE UG (78) | Historical receiving mesh plus declared CE UG–Dunwoodie attachment |
| 91 | Ramapo (76)–Buchanan (77) | Ramapo–Ladentown–Buchanan source detail, with direct source path retained separately |
| 92 | CE UG (78)–RAV A-3 (79) | Receiving mesh and declared RAV A-3–East Garden City attachment |
| 93 | CE UG (78)–Northport (80) | Receiving mesh and declared Northport–Shore Road attachment |
| 94 | CE UG (78)–Goethals (81) | Receiving mesh; Goethals–Gowanus and Fresh Kills/Fox Hills attachments |
| 95 | CE UG (78)–AK-3 (82) | Receiving mesh and declared AK-3–East Astoria 138 attachment |

Source: `output/nygrid_2025_downstate/network/replacement_register.csv`, rows with `variant=refined_2025`; resolve bus names against `bus_register.csv`. Replacement by a shared mesh does not establish a one-to-one physical identity between each aggregate branch and a particular real circuit.

Selected exact historical source circuit references at construction:

- Pleasant Valley–East Fishkill: PERFORM:1389/1390, model rows 353/354.
- Pleasant Valley–Wood Street: PERFORM:1391/1392, rows 355/356.
- East Fishkill–Wood Street: PERFORM:1689/1690, rows 359/360.
- Wood Street–Millwood: PERFORM:1734/1735, rows 364/365.
- Ladentown–Buchanan: PERFORM:1576, row 357; Ramapo–Ladentown: PERFORM:1577, row 358.
- Gowanus–Farragut: PERFORM:1984/1985, rows 369/370; Farragut–Rainey: PERFORM:1988/1989, rows 371/372.
- Dunwoodie–Shore Road: PERFORM:1159, row 300; Sprain Brook–East Garden City: PERFORM:1214/1215, rows 309/310. These are cable paths and must not be presented as overhead DLR candidates.

Source: `output/nygrid_2025_downstate/network/branch_register.csv`, join endpoint IDs to `bus_register.csv`. The 97 exact PERFORM rows add historical source detail, not 97 new lines built after 2019. Later AC engineering parameter assignments are separately versioned; the current model does not claim all 97 remain electrically bit-identical.

## Projects and chronology suitable for a slide

| Representation | Historical evidence and current timing | Remaining assumptions |
| --- | --- | --- |
| Pleasant Valley–Cricket Valley F83/F84 and Cricket Valley–Long Mountain | F84 owner notice: energized **28 July 2019**; available throughout modeled 2025 | F84 design conductor + representative geometry estimate; other aggregate/boundary attachments remain equivalent assumptions |
| Rainey–Corona RCC, Queens | Feeder 36188, transformer 5W and PAR R5W completed **3 May 2023**; present all 2025 | Cable analog, nominal transformer/PAR choices; installed cable details unresolved |
| Gowanus–Greenwood RCC, Brooklyn | Feeder 42233, BkT20, R20 completed **20 May 2025**; model activates **21 May 00:00 EDT** | Day-precision date converted conservatively to next midnight; engineering electrical assumptions |
| Goethals–Fox Hills RCC, Staten Island | Feeder 39291, BkT6, P6 completed **29 May 2025**; activates **30 May 00:00 EDT** | 9.4-mile XLPE route supported; cable cross-section/bonding and installed electrical data unresolved |
| Cricket Valley–Dover Y17 / Dover–Long Mountain 398 | Full-service boundary **19 Dec 2025, HB23 EST** = **20 Dec 04:00 UTC** | Two explicit parallel 750-MVA PAR banks; factory impedances and measured taps unavailable; bounded external-control reconstruction |
| Long Island station detail / East Hampton terminal | Historical source detail is exposed; South Fork terminal is East Hampton **69 kV** | Optional plant mapping and omitted local network proxy; do not call all LI additions new 2025 grid construction |

Sources: `NYGRID_2025_DOWNSTATE_REFINEMENT.md:70-95`; `output/nygrid_2025_downstate/sources/upgrade_register.csv` named project rows; `NYGRID_2025_LINE_PARAMETER_ESTIMATION.md:18-20,43-68`; `NYGRID_2025_DOVER_PARAMETERS_APPLIED.md:9-39,53-79`; current `delivery/structure/dated_state_map.csv` (all four state rows).

Important chronological correction: the old register label `Cricket_Valley_2020` is not authoritative for F84 commissioning. The primary owner letter `output/nygrid_2025_line_parameters/sources/projects/CV_InServiceNotice_20190729.txt:28-29` explicitly gives 28 July 2019. Added relative to the frozen 2019 model means absent from that model, not necessarily built after 2019.

Dover's current two-bank representation supersedes the early downstate report's statement that its internal PAR configuration was unresolved. Parameter/tap uncertainty remains. Source: `NYGRID_2025_DOVER_PARAMETERS_APPLIED.md:9-39` and current delivery report.

NYES is excluded from the core and only appears in a separate historical assumption case; Knickerbocker is idle in the primary construction. Churchtown is 115 kV, not an invented 345-kV station. CEEC and partial Smart Path Connect are source-register material outside this downstate construction; future CHPE/Propel is not operating 2025 topology. Do not add these to the slide's implemented-upgrade list.

## Current source-backed versus assumed claims

Supported at appropriate strength: named source endpoints/circuit identities, documented dates, historical PERFORM electrical rows at import, project design conductor information, official nominal voltages, exact mathematical reduction/recovery of the declared synthetic network.

Explicit assumptions: coarse-network attachments; unobserved nodal load shares and plant landings; current engineered R/X/B where source values are insufficient; representative geometry and equivalent conductor realization; PAR operating reconstruction and neutral assumptions; voltage/reactive capability policies; fixed shunt compensation; actual physical flowgate mapping where not certified.

Current registry (`delivery/structure_inputs/current_branch_registry.csv`) has 413 parent rows: 183 synthetic overhead, three design-based overhead, 22 cable-compatible source equivalents, three documented underground cables, three synthetic cable equivalents, 12 urban non-overhead equivalents, 65 composite voltage-changing equivalents, 38 station-transformer-compatible equivalents, five PAR, three station-reactance equivalents, two accounting station links and 74 inactive provenance records. These are model classifications, not installed-asset counts.

The registry reports 125 overhead parents with `exact_R_X_inverse_with_integer_circuit_search`, 57 with declared `synthetic_positive_R_X_B_redesign_from_nominal_geometry_and_X_implied_length`, one imported-R/X physical-repair realization, and three preserved source-design line-only R/X/B parents. Thus preserving the NPCC backbone must not be paraphrased as preserving every original impedance.

## Exact paper reference and historical validation framing

M. Vivienne Liu, Bo Yuan, Zongjie Wang, Jeffrey A. Sward, K. Max Zhang, and C. Lindsay Anderson, **An Open Source Representation for the NYS Electric Grid to Support Power Grid and Market Transition Studies**, *IEEE Transactions on Power Systems*, vol. 38, no. 4, July **2023**, DOI **10.1109/TPWRS.2022.3200887**. Online publication was 24 August 2022; 2019 is the example operating-data year.

Verified against preserved local PDF extraction `tmp/pdfs/nygrid_2019_paper_review/paper.txt:1-7,31-55`; original PDF is `C:/Users/Holiday/Downloads/An-Open-Source-Representation-for-the-NYS-Electric-Grid-to-Support-Power-Grid-and-Market-Transition-Studies.pdf`. Paper's original NPCC description appears at extracted text lines 281-287; its methods explicitly use a 2019 example.

Use the authors' supplied `if.map` for the main released-2019 comparator. The literal `flow4Plot.m` indices disagree for five interfaces and are a release measurement discrepancy, not an inferior physical network. 2019 vs current 2025 is cross-year/cross-input/cross-physics evidence, not causal attribution to topology refinement. Do not claim that a low downstate interface error verifies physical topology or asset identity.

## Figure options and limitations

Historical construction diagrams already available: `output/nygrid_2025_downstate/diagrams/hudson_westchester.pdf`, `new_york_city.pdf`, `long_island.pdf`, and `downstate_changes.pdf`. Geographic atlas: `output/nygrid_2025_downstate/geography/figures/geographic_downstate_atlas.pdf`. They depict the historical 191-bus station-detail construction, not the latest 267-node numerical AC network; label them accordingly.

Current structure schematic: `output/nygrid_2025_moses_repair/delivery/structure/current_model_schematic.svg` or PNG. Existing geographical straight lines are connectivity drawings, not surveyed transmission routes. Original CE UG (78), RAV A-3 (79), AK-3 (82) have no verified physical site identity; source atlas puts them in a schematic inset. Parent bus 35 is Southington, not Long Mountain. Long Mountain is a distinct added Connecticut terminal.

## Source freshness

Current delivery tables were read fresh in this audit. Historical reports are used only for construction provenance. The older top-level `NYGRID_2025_LATEST_MODEL_STRUCTURE.md` has 1,464 generators and should not supply current counts. Use the Moses-repair delivery structure report with 1,466 (1,437 native resources, 27 regional loss participants, one signed HQ equivalent, one fixed PV20 boundary injection). PV20 adds no AC branch, no numerical bus and no seventh DC transfer record.
