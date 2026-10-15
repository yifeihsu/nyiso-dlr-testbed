# Current AC cut accounting

This analysis reads the saved current AC solutions on exactly 8,170 equation/loss-qualified hours. It runs no power flow and changes no input, impedance, dispatch, control or interface definition. The largest named cut-identity residual is **1.86e-10 model MW**; the independent reconstruction of allocated losses differs by at most **2.44e-10 model MW**. All source hashes remain unchanged.

Quantities in the equations below are synthetic model MW. Divide an aggregate power by gamma = 0.30012075175285535 to obtain the inherited public-scale comparison convention. Do not apply gamma to current. None of these hours passes the joint voltage/reactive/generator-capability gate.

## Terminal definitions and complete cuts

For a modeled parent corridor, PF and PT are powers entering its original from and to terminals; numerical interior sections are resolved by branch keys. Its real loss is L = PF + PT. A frozen membership coefficient s is +1 when the original from terminal lies on the positive-source side, and -1 otherwise.

```text
primary signed-literal-from flow F = sum(s * PF)
oriented midpoint M               = sum(s * (PF - PT) / 2)
signed half-loss correction C      = sum(s * L / 2)
F = M + C

oriented source-side flow = M + sum(L)/2
oriented target-side flow = M - sum(L)/2
```

For a set S of NY accounting zones, let N be native PG, H the HQ equivalent injection if its bus is inside S, A the AC external-region imports measured at NY terminals, D the signed controlled DC/PAR imports, and G the gross P58 demand target. All are summed over S. Current real shunt conductance and modeled DC losses are zero.

Summing the physical nodal equations gives source-side NY export equal to N + H + A + D minus served demand and internal real losses. The declared ownership rule allocates all internal-S losses to S and half of each NY-to-NY boundary loss to each side. The delivered demand is G minus allocated loss. Therefore the internal losses cancel:

```text
M_complete(S) = N(S) + H(S) + A(S) + D(S) - G(S)
```

This is a consequence of the current gross-demand/loss policy, not a generic assertion that physical transmission losses are irrelevant. Internal losses can change delivered demand and the scientific plausibility of the model while the complete-cut midpoint remains fixed.

If the selected interface I omits members of the complete S boundary:

```text
F_I = M_complete(S) - M_omitted(S,I) + C_I
```

The nine accounting scopes in `hourly_cut_drivers.csv` reconcile this formula, the direct nodal sum, and the independent loss-ownership reconstruction for every qualified hour.

## Which boundaries are complete

The following memberships and omissions hold in all four current dated states.

| Interface | Accounting set and completeness |
|---|---|
| Dysinger East | A is complete: four members. |
| West Central | A+B is complete: four members. Its declared B-to-C intent alone is a partial B boundary; the other four B-boundary members are the Dysinger corridor set. |
| Total East | A+B+C+D+E is complete: five members. |
| Moses South | D is complete: three members. |
| Central East - VC | It contains four E-to-F members. The complete E boundary has 13 members, also crossing toward C, D and G. When accounting over A–E, the only omitted member is parent 224. |
| UPNY ConEd | A–G is complete: six members. |
| Sprain/Dunwoodie South | I-to-J is partial: eight of 15 I-boundary members. Omitted parents are 294, 295, 296, 297, 300, 309 and 310, linking I toward H, G and K. |

Current expanded UPNY members are 297 and 361–365; current Sprain/Dunwoodie members are 319, 320, 328–330 and 336–338. The older intent JSON's unexpanded 87/88 and 94/95 entries are not used. `cut_completeness_and_bypass.csv` gives every state, signed membership and omitted parent ID.

## Western and northern invariants

Let R_ON be the prescribed Ontario regional import at NY terminals, Q_ON the sum of its two ideal PAR transfer records into D, and J_A the AC import through the nominal PJM-to-A parent 71.

```text
M_Dysinger = N_A - G_A + R_ON - Q_ON + J_A
M_WestCentral = M_Dysinger + N_B - G_B

F_WestCentral - F_Dysinger
  = N_B - G_B + C_WestCentral - C_Dysinger

M_Moses = N_D + HQ + Q_ON - G_D
```

There are no active AC external ties into B or D. The Ontario AC landings are parents 62 and 63 into A. Parent 71 ends at **bus 140**, which is assigned to PJM accounting but is a passive leaf: zero PD/QD/GS/BS, no generator, no DC terminal, and only parent 71 incident. It is not an independent bulk PJM import channel. Its current NY-terminal contribution is approximately **-0.00628002 public MW**, with variation below 3e-12 MW over the qualified cohort.

Thus within-zone active-power redistribution and internal impedance changes at fixed aggregate profiles, regional targets and controls cannot materially move the western midpoint through a bulk external-landing mode. Their remaining primary-flow effect is the signed boundary-loss correction (plus the tiny leaf loss). Moses has no external AC landing or omitted NY boundary at all. All three Moses coefficients are negative, so its primary flow is its fixed midpoint minus half the three member losses.

For UPNY, all regional AC landings are inside A–G. Let T1–T4 be the four prescribed original DC records terminating in J/K; the Ontario PAR records terminate inside D. Then:

```text
M_UPNY = N_A:G + HQ + R_ISONE + R_ON + R_PJM
         - (T1 + T2 + T3 + T4) - G_A:G
```

UPNY's complete midpoint is therefore fixed under the same aggregate-input contract. A large error cannot be attributed to adjustable internal routing merely because many lines lie inside the set.

## Shared A error and incremental B error

For the frozen primary convention, define e_DY = F_DY/gamma - observed_DY and e_WC similarly. Then:

```text
incremental_B_error = (F_WC - F_DY)/gamma - (observed_WC - observed_DY)
e_WC = e_DY + incremental_B_error
```

Fresh values on the same 8,170 hours are:

- Dysinger/West Central residual correlation: **0.998255707**.
- Incremental B MAE: **14.393481 public MW**; bias: **-2.697176 MW**.
- Dysinger MAE: **258.643547 MW**; West Central MAE: **255.043600 MW**.

This isolates an arithmetic common mode and an incremental mode. It does not prove that an observed physical Zone B net injection has been measured, or that Niagara generation causes the shared mode. Physical meter membership is not established. `hourly_residual_modes.csv` retains both observations and every correction.

## Total East, Central East and external landing

PJM AC landings are parents 71 into A, 79/82 into C, and 90 into G. Unlike the passive A leaf, the C and G ports connect to the PJM external mesh. Let J_N = J_A + J_C and let T2–T4 be the prescribed PJM DC records into J/K.

```text
M_TotalEast = N_A:E + HQ + R_ON + J_N - G_A:E
J_N = R_PJM - J_G - (T2 + T3 + T4)

M_CentralEast = M_TotalEast - M_parent224
F_CentralEast = F_TotalEast - PF_parent224
```

The last two equalities follow from the exact frozen memberships: Total East is the four Central East members plus parent 224. No physical meter alias is inferred. ISO-NE AC landings are F and G, outside A–E; ISO-NE has no direct term in the Total East western-set identity, although changing its network conditions could indirectly alter the PJM split.

The saved source-corrected DC reference is remasked to the same 8,170 hours. Its comparison is historical evidence, not a newly solved DC case:

| Interface | Mean AC minus DC, public MW | Mean signed half-loss correction | Remaining midpoint minus DC |
|---|---:|---:|---:|
| Dysinger East | 0.141314 | 0.147594 | -0.006280 |
| West Central | -0.266494 | -0.260214 | -0.006280 |
| Total East | -97.525960 | 59.329653 | -156.855613 |
| Moses South | -10.533327 | -10.533327 | 0 to numerical precision |
| Central East - VC | 457.127525 | -5.871547 | 462.999072 |
| UPNY ConEd | -0.031649 | -0.031649 | 0 to numerical precision |
| Sprain/Dunwoodie South | 6.316758 | -1.111756 | 7.428514 |

The Total East midpoint shift is consistent with a changed PJM north-versus-G landing partition; Central East also contains the parent-224 bypass partition. The CSV reports inferred DC landing/bypass terms explicitly as gate-accounting references. These identities identify available mechanisms; they do not establish which physical parameter or source error caused the residual.

## Measurement and interpretation limits

The seven modeled operators are inherited NY accounting-zone cut diagnostics, not certified NYISO P32 physical meter collections. The frozen primary functional mixes original literal from-end measurements according to signs; it need not equal a single physical sending or receiving meter convention. Source/target alternatives are sensitivity conventions, not confidence bounds.

The raw published P32 field is named `Flow (MWH)`; its numeric-as-MW interpretation and the saved time aggregation are inherited. No sign, scale, lag, meter membership or observation was adjusted in this analysis. An older public alias helper describes Total East as an F–G proxy and UPNY as G–H; those descriptions do not supersede the expanded current membership contract.

For a conditional net-input oracle, observed-minus-midpoint assumes midpoint metering. If the frozen primary terminal correction is held, the required net-input correction is observed-minus-midpoint-minus-C, which equals observed-minus-primary. Both are exported in `current_gate_terms.csv`; neither is a source-backed dispatch correction.

The passivity statement for Moses is conditional on the current model and fixed inputs: its primary cannot exceed its midpoint when member losses are nonnegative. Observations exceed that midpoint in 3,329 of the qualified hours. This is not a universal physical infeasibility conclusion or evidence of a particular source error.

## Reproducible artifacts

- `accounting_identity_review.json`: closure maxima, conditional identities, cohort and source/output hashes.
- `hourly_cut_drivers.csv`: nine explicit region scopes, source components, omitted-cut terms and closures.
- `cut_completeness_and_bypass.csv`: all four dated topologies and exact parent membership.
- `hourly_residual_modes.csv`: western common/differential residuals, PJM landings and parent-224 terms.
- `matched_AC_DC_terminal_decomposition.csv`: matched-cohort DC reference comparison.
- `current_gate_terms.csv`: primary, midpoint and both terminal conventions with conditional oracle definitions.
- `accounting_arrays.npz`: full-hour axes and reusable derived arrays; failed AC rows remain unavailable.

The producer is `scripts/nygrid_2025_remaining_errors/accounting/analyze_cut_accounting.py`. The gate-term exporter is separate. Existing inputs, prior artifacts and the uncommitted interactive-map work were preserved; no commit was made by this analysis.
