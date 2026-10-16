# Cable review recommendations for the current Moses-repair map

This is an audit-only overlay of the existing synthetic research model. It changes no network parameters, classifications, source inputs or prior map. Review flags distinguish documented conflicts, material parameter assumptions and unresolved physical identity; they do not mark all cables as wrong.

## Recommended display groups

| UI label | Model parents | Meaning |
| --- | ---: | --- |
| Cable evidence conflicts with overhead template | 4 | Documented cable-corridor evidence conflicts with an overhead parameter template; already excluded from overhead DLR. |
| Parameter review | 18 | Parameters warrant review; installed identity varies and is recorded separately. |
| Cable identity uncertain | 22 | Cable/urban or proxy treatment is not a verified physical cable inventory. |

There are **44 candidate parent records**, comprising the existing **40 cable-like equivalents** plus **four documented classification conflicts**. The 40 comprise 22 cable-compatible source equivalents, 12 urban non-overhead equivalents, three explicit synthetic cable proxies and three documented project feeders. Evidence tiers are A=3 project identities, B=11 historical matching corridors, C=7 unresolved terminal aliases, D=16 electrical/urban assumptions and E=3 explicit proxies.

## High-priority interpretation and parameter reviews

| Parent IDs | Named path | Reason |
| --- | --- | --- |
| 300 | Shore Road–Dunwoodie / Y50 | Owner cable evidence conflicts with overhead template. |
| 309, 310 | East Garden City–Sprain Brook / Y49 | Documented underground/submarine corridor; two model rows do not prove two real Y49 circuits. |
| 386 | Goethals–Gowanus | Named cable corridor, but model record is a synthetic aggregate attachment; no owner feeder identity is asserted. |
| 286, 287, 288, 289, 319, 320, 369, 370, 371, 372, 375, 379 | Historical 345-kV urban/cable equivalents | Synthetic gross charging is 15.59–20.12 times the imported B while imported R/X remain. Review the construction and charging assumptions; neither source nor current B is certified as installed. |
| 408, 409, 410 | Rainey–Corona, Gowanus–Greenwood, Goethals–Fox Hills RCC feeders | Physical underground project identity is supported. Current copper/XLPE R/X/B and the 1,000 A ceiling are engineering assumptions, not installed cable or buried-ampacity verification. |

These are **19 high-priority parent records**. The other 25 retain a review/context flag. The tenfold B threshold is only transparent audit triage, not a physical validity criterion or an observation-driven fit.

**Gross B is not net Q.** The twelve large-B substitutions each have declared 75% nominal charging compensation stored as separate bus reactors. The gross B ratio is not a multiplier of net reactive injection, solved branch Q or voltage error. Reactor absorption depends on voltage squared and is itself a synthetic assumption.

The three RCC feeder lengths used in the present model are six miles (Queens), one mile (Brooklyn), and 9.4 miles (Staten Island). In particular, the current AC feeder R/X/B are route-length synthetic cable constructions; do not describe the current AC values as the earlier DC cable analog unchanged.

## State-aware counts

| State | Cable equivalents active | Conflicts active | All review parents active | High-priority active |
| --- | ---: | ---: | ---: | ---: |
| pre_may | 38 | 4 | 42 | 17 |
| may21 | 39 | 4 | 43 | 18 |
| may30 | 40 | 4 | 44 | 19 |
| post_dover | 40 | 4 | 44 | 19 |

Use the current parent `stateRecords[stateId].active` flag at the selected map hour. Parent409 becomes active May21 at00:00 EDT; parent410 becomes active May30 at00:00 EDT. Do not present future dated rows as energized. All44 candidates are excluded from the current overhead conductor research screen in all four states, including the four retained overhead-template conflicts.

## Exclusions and limits

- Controlled merchant transfers and Ontario controls are separate modeling records, not ordinary AC cable parent rows. They are outside this R/X/B audit.
- Do not infer cable identity from a city location, a straight map chord, high capacitance, or a voltage-changing composite alone. The65 composite equivalents, transformer/PAR equipment, numerical section buses and reduced-admittance couplings are not added cable flags.
- Parallel model rows do not certify physical circuit multiplicity. No count here is an installed-asset inventory.
- Unknown construction does not mean incorrect R/X/B. All40 cable-equivalent models lack installed construction/buried ampacity certification, but only the stated evidence and parameter-change criteria drive the priority flags.
- Electrical line ratings are declared model screens, not installed equipment nameplates. No actual facility overload or safety conclusion is made.

## Reproducibility

The JSON contains44 ready-to-use items with parentId/key/title/status/priority/reason, separate cableIdentity and evidenceTier, current and imported R/X/B, per-state active flags and runtime rows, model ratings, reactor context, source references/URLs, source file hashes and independent cross-checks. Current runtime matrices were read directly for all four states, and aggregated parent R/X/B, status and ratings were checked against current map records. Primary-source receipt hashes and current overhead-screen exclusions were verified. No PF/OPF or annual replay was run.

Detailed machine-readable artifact: `cable_audit_recommendations.json`.
