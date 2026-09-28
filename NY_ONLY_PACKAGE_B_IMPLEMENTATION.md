# Package B: NY-only regional electrical candidate

**Current role:** optional historical electrical reference. The preferred preliminary
testbed is now the [compact NPCC NY benchmark](COMPACT_NPCC_NY_TESTBED.md): 51 NY
buses, a hard 200-bus ceiling, benchmark load scale, and fixed boundary injections.
The Package B construction and results below retain their original meaning.

Package B replaces inherited regional network functions with a connected, explicitly mapped part of the original PERFORM NY model. The resulting historical electrical candidate contains **878 buses, 1,375 branch records, and 595 generator records**: 855 original-source buses in NY zones D–K and 23 retained NPCC buses in zones A–C. The construction follows the electrical boundary and device-accounting requirements; it does not force a predetermined reduced bus count.

The accepted operating route is bounded AC reconstruction using **MATPOWER MIPS with its default initialization (`opf.start=0`)**, followed by a fresh power flow with fixed operating inputs and an independent physical-limit audit. This establishes one assumed historical operating candidate. It does not establish contemporary validation, thermal readiness, or completion of the later research packages.

## Fixed inputs and interpretation

The immutable 2019 PERFORM source and the separately frozen Package A reference remain the source of electrical values and operating priors. Package B does not modify either artifact.

| Quantity or device family | Package B treatment |
| --- | --- |
| Power scale | Original actual MW on the common 100 MVA base |
| Gross active demand | **29,799.66 MW**, preserved in total and by original NY zone |
| Gross reactive demand | Original signed source QD, preserved separately from boundary Q |
| External exchange | All 20 Package A boundary records retain their frozen P/Q values and service status; 14 are active and six remain inactive |
| Native generation | 594 normalized source records retain their individual P/Q limits and status; reconstructed dispatch is compared with Package A priors |
| Declared reactive support | The separate Package A Marcy support retains P=0 and Q bounds of −900 to +900 MVAr; it is an assumed research device |
| Original Marcy RF record | Excluded from native generation and fixed external exchange; its ±9,900 MVAr placeholder bounds are not reused |
| Shunts | The 34 source shunt records contribute canonical bus BS once; the alternative QS generator representation is not added |
| Bus and branch limits | Retained NPCC limits and copied source limits remain explicit; no limit enlargement is used to obtain the accepted point |

“594 native records” is an accounting count, not a claim that the records identify 594 independently verified physical generating facilities. Source roles, unit identifiers, offline status, and mapping assumptions remain visible in the generator ledger. The 595th model record is the separately declared reactive support.

At every model bus, the accounting is

\[
P_D^{\mathrm{effective}}=P_D^{\mathrm{gross}}-P^{\mathrm{boundary}},\qquad
Q_D^{\mathrm{effective}}=Q_D^{\mathrm{gross}}-Q^{\mathrm{boundary}}.
\]

Positive boundary P supplies NY; negative P is an export. External exchange is never counted again as native generation. Legacy candidate PD, QD, GS, BS, and generator injections are retired before source values are applied. The old values remain in retirement ledgers rather than disappearing from the audit trail.

## Regional construction and stable identity

`build_ny_regional_candidate` assigns every original source bus to exactly one candidate bus. Original D–K buses have distinct model IDs `20000 + source_bus`; their base kV, voltage limits, source zones, and device associations are preserved. The native reference at source Roseton bus 847 therefore becomes model bus 20847. The separate Marcy support at source bus 1263 becomes model bus 21263.

All original-source branches internal to, or crossing into, the declared source region are copied once, including inactive records. Their R/X/B, ratings, tap, phase, status, and angle fields are preserved. Source crossing endpoints must map to compatible base-kV terminals. The construction expands a source boundary if a required voltage class is unavailable; it does not create an undocumented transformer to connect incompatible terminals.

NPCC A–C branches retained wholly within the remaining region keep their existing electrical parameters. Source A–C injections are aggregated through a complete same-zone source-bus map, using declared source-network distance and anchor rules. Those mappings are spatial assumptions. They do not establish that a retained NPCC bus is the exact physical terminal of every source device assigned to it.

`map_perform_injections_to_ny_candidate` applies the same source-bus map to gross load, native records, shunts, controls, support, and boundary exchange. This prevents a source load from moving to one proxy while its co-located support or generation silently moves elsewhere. Its audits compare source and mapped zonal demand, boundary P/Q, native dispatch priors and capability, GS/BS, and record counts.

Device kind and control representation are preserved explicitly. Copied two-winding transformers remain transformers with fixed taps and shifts; static shunts remain bus susceptance. Native controls use the canonical MATPOWER local-PV representation with finite Q bounds. Where several source devices share an aggregate terminal, one Q-range-weighted Package A voltage target supplies a declared initial prior. The subsequent bounded solve determines operating voltages. The known original RAW remote-control omission remains documented; the candidate does not claim to restore control behavior that the canonical MATPOWER source did not implement.

Electrical source identity does not validate overhead/cable construction, conductor properties, or thermal-device identity. Unresolved physical classifications and ambiguous parallel-circuit identities remain visible. No branch receives DLR qualification from its voltage level, parameter match, or successful AC solve.

## Exact row-235 proof and broader functional retirement

Historical parent row 235 joins Pleasant Valley and Wood Street, parent buses 73 and 9002. Its registered lineage identifies it as the parallel equivalent of original-source circuits 1391 and 1392, between source buses 651 and 902. Those same two circuits already appear individually as parent rows 256 and 257.

`build_row235_replacement` independently checks the pinned source, RAW circuit keys, terminal aliases, voltage classes, source/parent lineage, and electrical parameters. The aggregate two-terminal admittance equals the sum of the two individual circuit admittances. Matched-terminal complex-power tests confirm the same local relationship. This proves that retaining both the aggregate and the individual pair would duplicate that electrical function. The standalone replacement deactivates row 235 and keeps the two source circuits and their individual ratings.

The complete Package B construction carries this exact proof into its disposition registers while retiring the larger inherited D–K regional function. Every parent branch has one disposition: retained in the remaining NPCC region, retired by regional replacement, or removed with the external NPCC network whose exchanges are now explicit NY boundary injections. Retired equivalents are not superimposed on the imported source network.

**Only the row-235 pair has this particular exact aggregate-to-circuit proof.** Retirement of the other inherited regional rows is a declared replacement of the regional function, with uncertain individual physical correspondence. It does not assert a one-to-one facility crosswalk or that every old row was an exact duplicate. The historical parent remains available as an explicit alternative model; it is not combined with the replacement in the operating candidate.

## Why the source region includes D, E, and F

The smaller G–K and D-plus-G–K constructions passed structural accounting but did not produce accepted bounded operating points in the attempted solves. These are recorded failed attempts, not proofs of global AC infeasibility.

The diagnostics identified two different issues. The coarse Plattsburgh representation concentrated about 401 MW at NPCC bus 49 and approached its voltage limit. More broadly, distinct upstream source terminals were being merged into a single retained equivalent: five E-side ports mapped to Porter 115 kV despite a Package A voltage span of approximately 0.0566 pu and angle span of 8.48 degrees; four F-side ports mapped to Albany 115 kV despite an angle span of about 2.52 degrees. Matching zone and base kV alone did not establish the electrical response of those merged terminals.

Expanding E and F together with D removes those particular merged interfaces and retains their source electrical detail. D–K contains 855 source buses and leaves 14 active original-source crossing branches, all across C–E. The remaining A–C aggregation still has an explicit uncertainty boundary; a successful operating point does not make its response identical to the full source.

Large residuals at otherwise complete Long Island nodes in failed solver states were not used as evidence of missing local physical facilities. At the Package A source phasors, the retained H–K network reproduced local nodal balances to numerical tolerance. That check localized the difficulty to the mixed network and its operating conditions without inventing extra generation or support at residual locations.

## What the validation proves

`validate_ny_region_replacement` checks total and disjoint bus/branch provenance, complete source mapping, voltage classes, copied electrical parameters, parent-row dispositions, device/accounting conservation, and connectedness. Local branch-power, current, and admittance comparisons use **the same declared terminal phasors on both representations**. They establish identity of copied electrical elements under matched inputs. They do not establish upstream aggregation-response equivalence, independent operating feasibility, or held-out predictive accuracy.

The operating acceptance is separate. The bounded solve keeps gross demand, fixed boundary P/Q, shunts, network parameters, generator status, and capability fixed while adjusting permitted operating variables. The audit recomputes nodal P/Q balance, bus voltage limits, every online generator's P/Q limits including the reference, branch limits at both terminals, and angle limits. A fresh fixed-input power flow must reproduce the bounded result within the declared dispatch and voltage adjustment tolerances.

Initialization and solver sensitivity remain diagnostic evidence. Earlier source-state warm starts failed in attempted candidates, while IPOPT produced an accepted D–K diagnostic point. Subsequent MIPS tests from both default initialization and an accepted IPOPT seed passed their audits. The delivered reproducible route uses **default-start MIPS only**; it does not require IPOPT or silently select a favorable solver result. Detailed numerical metrics belong to the generated acceptance artifacts for that route, rather than to earlier exploratory logs.

The delivered default-MIPS run supplies 29,083.765450 MW of native generation
against 29,799.66 MW gross demand and 1,292.635022 MW net boundary injection,
with 576.740472 MW losses. Its fresh PF has no voltage, generator, branch or
angle violations; maximum active-dispatch replay adjustment is 0.000040573 MW.
Native P movement from Package A is only 0.001429 MW, while native Q movement
is 2,400.724194 MVAr. The assumed Marcy support absorbs 649.599563 MVAr with
zero active injection. Small P movement is not evidence of unchanged controls
or network response.

At their own independently solved voltages, the regional and source cases
have voltage RMSE 0.031391 pu and maximum difference 0.060333 pu across855
exact source buses. Across the copied active branches, terminal P RMSE is
19.134512 MW with maximum difference265.732429 MW; current-magnitude RMSE is
0.055939 kA with maximum difference0.564406 kA. These differences are retained
in `source_response_*.csv`; no response-equivalence threshold was imposed or
claimed passed. Aggregating GS/BS preserves coefficients, not necessarily
their realized power at differing voltages.

## Reproduction and independent replay

From the repository root:

```matlab
replay_ny_only_foundation;              % verify the committed Package A inputs
out = run_ny_only_regional_candidate;   % construct, test, solve and audit B
replay = replay_ny_only_regional_candidate;
```

Package B outputs are written under `output/ny_only_package_b`. The frozen operating input is `ny_regional_candidate.mat`, with its file fingerprint recorded in `candidate_input_manifest.csv`. The MATPOWER loader is `npcc_ny_lite_s14_ny_only_regional_candidate`. Source mappings, retained/retired branch dispositions, device and injection ledgers, structural validation, bounded-solve results, and independent replay evidence accompany the candidate.

The runner requires the authoritative committed Package A reference. If
Package A is deliberately rebuilt with `run_ny_only_foundation`, rebuild
Package B as well; an old embedded foundation cannot silently substitute for
the new authoritative artifact. Fast checks write under `implementation_only/`
and failed main operating attempts under `failed_candidate/`, preserving an
existing accepted candidate. Output paths overlapping Package A are rejected.

`replay_ny_only_regional_candidate` does not rerun the optimizer. It checks the candidate fingerprint, rereads the immutable source, verifies and independently replays the authoritative Package A artifact, rebuilds the declared region from the default parent, and compares saved provenance/accounting and frozen hardware against the fresh construction. It then runs a fresh power flow and limit audit. Stored terminal flows, embedded success flags, or a self-consistent but altered embedded foundation are insufficient replay evidence.

The generated acceptance record is the authority for final mismatch, loss, movement, violation, and replay-adjustment values. Those numerical results must be taken from the delivered default-MIPS run, not copied from an earlier candidate or diagnostic solver.

## Remaining scope

Package B delivers a historical NY-only regional electrical candidate with explicit network-function replacement and source accounting. Qualification applies to the one assumed 2019 fixed-input case that passes the bounded solve and independent replay.

Contemporary assets and operating scenarios belong to Package C; broader reconstruction and held-out validation belong to Package D. Remaining A–C aggregation uncertainty, physical line/cable identity, conductor/weather data, and thermal realization require their own evidence. This implementation is not DLR-ready and does not promote the candidate as a fully contemporary or finally validated operating model.
