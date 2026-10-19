# NYgrid-to-compact 2019 role and operator crosswalk

The review's principal concern is confirmed: identical original bus IDs do not carry identical equivalent-area roles in the two models. All 46 original NY buses (37–82) are retained in the compact 51-bus case. A literal 2019 input transfer therefore needs **bus-level injection preservation and measurement harmonization**, before adding buses or fitting impedances. This audit changes no model, dispatch, target, or earlier artifact.

## Bus and injection roles

| Original bus | NYgrid allocation role | Compact declared zone | Consequence |
|---|---|---|---|
| 38 Gilboa | E | F | Paper Central East includes 37–38; compact's E–F cut excludes it. |
| 46 Colton | E | D | Paper Moses South includes 46–49; compact instead includes 45–46. |
| 47 Moses W | E | D | Paper Moses South includes 47–48; compact regards it as internal to D. |
| 62 Stolle Road | B | A | Moves the Dysinger boundary while the complete A+B export operator remains equivalent. |
| 69 Binghamton | E | C | Original 38–69 is E-internal in NYgrid, but crosses the compact Total East partition. |
| 77 Buchanan | G | H | Paper UPNY includes 77→74. |
| 79 RAV A-3 | K | J | Paper Dunwoodie excludes 78–79; the current compact I–J operator includes it. |

These are **model-role differences, not independent geographic verification**. Preserve both label sets. Extend the paper-role comparison with 774=G, 858=G, 9001=G, 9002=G and 9003=K; these five added transit assignments are explicit assumptions. The corresponding names are Ladentown, East Fishkill, Knickerbocker, Wood Street and East Garden City.

Five paper generator landings have no generator record in the compact fleet: **45, 49, 62, 74 and 77**. All five buses exist. Preserve their source bus-level injections in the fixed-DC experiment instead of redistributing them across existing compact generators. For the literal arm, Indian Point 2/3 remain at paper bus 74, with source capacities 1,025.9 and 1,039.9 MW. Bus 74 is also the paper reference: preserve pre-PF and solved generation separately so slack pickup is not called an observation. A physical-landing experiment at 77 must be separate.

NYgrid's load allocator uses `npcc_new.csv`, while its generation-residual allocator and operator roles use `npcc.csv`. Zone labels agree between those two files, but load weights differ. The modified G weights are 20% at 39, 20% at 73, 10% at 75, 10% at 76 and 40% at 77. K is 3/7 at 79 and 4/7 at 80. These differences cannot be preserved by transferring only zonal totals.

Use native solved generation plus the separately exported NY-side AC/DC/HQ boundary injections exactly once. The paper HQ record at bus 48 is a boundary injection, not additional native generation. Renewable negative load and gross demand must remain separately visible. Actual MW or a single consistently applied fixed gamma both support a DC comparison; every P input, boundary term, load and target must use the same scale.

## Compatible operators

`crosswalk_operator_members.csv` supplies stable keys and signed DC PF coefficients for the frozen current operator and the **paper-role corridor operator**. Its seven rules are A→B, B→C, E→F plus E→G, D→E, E→F, G→H and I→J, following the corrected released `if.map`. It includes every active compact branch crossing each specified pair.

| Interface | Paper-role members | Current members | Identical on the compact state? |
|---|---:|---:|---|
| Dysinger East | 4 | 3 | No |
| West Central | 4 | 4 | Yes |
| Total East | 5 | 4 | No |
| Moses South | 3 | 2 | No |
| Central East | 4 | 3 | No |
| UPNY–ConEd | 3 | 6 | No |
| Dunwoodie/Sprain South | 4 | 6 | No |

This is measurement harmonization on the same electrical solution. It does **not** establish exact official flowgate membership. In particular, the compact paper-role Total East includes added Gilboa–Leeds 38–39, where the reference's fifth member is Marcy-path 38–77. UPNY uses the two Wood Street→Millwood circuits plus 77→74, replacing the reference's direct 73→74 member. Dunwoodie includes the added parallel paths at 78–81 and 78–82.

The exported `PF_coefficient` is the literal signed-from-terminal DC convention. Separate upstream AC PF/PT columns avoid silently equating `-PF` and `PT` when losses are present. Never copy the source's numerical branch row indices into the compact matrix.

## Marcy and other network differences

Neither **43–38** nor **38–77** exists as an active compact edge, and no S4 addition has the same endpoint pair. The paper adds both with x=0.0427 and 0.0147 pu on 100 MVA. A separately named DC hypothesis may append them while retaining the complete primary compact network. **Do not retire 38–69:** NYgrid retains that original x=0.0485 branch alongside both additions.

Endpoint comparison establishes no exact duplicate of the two Marcy edges. It does not prove absence of broader equivalent-network functional overlap. The compact 38–39 Gilboa–Leeds path has different endpoints and source provenance; keep it in the primary experiment. With Marcy appended, recompute the same role rule: Total East gains 38–77 and has six members, while 43–38 remains E-internal. Copying the two additions' r=0.02 and unrated status into an AC/DLR claim is not justified by the paper's DC validation.

The shared NPCC ancestry also conceals backbone multiplicity differences. NYgrid's original source has 227 branch records; the compact ancestry has 233 before its 13 S4 additions. Compact has two Edic–Clay 43–50 records at x=0.0268, versus one in NYgrid. Its Millwood–Dunwoodie 74–78 connection has two inherited x=0.0045 records plus an S4 x=0.015 path, versus one x=0.0045 reference record. S4 also strengthens 78–79, 78–81 and 78–82 with added parallel paths. These are documented in `crosswalk_network_pairs.csv` and `crosswalk_s4_additions.csv`; pair susceptance is not a whole-network equivalence proof.

Retain all compact paths for the primary comparison. If necessary, test backbone multiplicity, individual S4 parallel paths, and the extra 39–9001–73 route as separately registered hypotheses. Removing all S4 additions together could isolate transit/generator nodes and would confound several effects. There is no source evidence here supporting blanket removal.

## Compact-input transfer to the 46-bus reference

The reverse input-transfer arm must handle generation at compact-only bus 9003 rather than dropping it. An exact DC Schur elimination of the five added buses supplies a defensible, explicitly network-dependent map. For retained buses R and eliminated buses E, use `p_equiv = p_R - B_RE * inv(B_EE) * p_E`, with the corresponding Schur network and any phase offsets kept distinct. Apply this same frozen linear map to generation, gross load and boundary components separately so their contributions remain visible.

The current network gives bus 9003 **50% at 78 and 50% at 80**. All five added-node columns have nonnegative weights summing to one. Independent dense-matrix testing on 12 balanced random injection vectors preserves retained angles within 5.45e-15 rad and every original branch flow within 7.17e-12 MW; the eliminated block has condition number 14.84. The exact coefficients and checks are in `crosswalk_kron_injection_map.csv` and `crosswalk_kron_validation.csv`.

This is an exact elimination **within the compact network**. Applying its equivalent injections to the different NYgrid network is a declared spatial-transfer hypothesis. It does not assert identical cross-network flows or that half the physical East Garden City generation is actually connected at Dunwoodie. A source-branch split is unnecessary for this diagnostic arm.

## Audit evidence and next comparison

Six construction checks pass, including exact agreement with the fresh MATLAB export of the current compact operators and all 24 corrected NYgrid operator terms in the annual reference export. The crosswalk was constructed without reading observed interface values. Source hashes and runtime versions are retained; `crosswalk_build.py` reproduces the CSV/JSON artifacts.

The next comparison should first hold bus-level injections and boundary terms fixed, report both operators on each state, then append the named Marcy hypothesis. Keep the January 8 example and other already examined hours labelled development diagnostics. A better score after changing only operator membership is a corrected measurement comparison, not evidence that the network improved. AC bounds, reactive controls and thermal consistency remain separate acceptance work.

Primary implementation sources: [NYgrid bus allocation table](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/Data/npcc_new.csv), [network modifications](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/modifyMPC.m), [operating reconstruction and corrected interface map](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/updateOpCond.m). Exact local dependencies are listed in `crosswalk_sources.csv`.
