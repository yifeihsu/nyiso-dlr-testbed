# Content audit: NYgrid interface update, 8 September 2026

Revision note: the delivered deck now has eight slides. The detailed review below describes the original 24-slide draft and its evidence; it remains as a source audit. The concise revision retains model identity, actual-flow error definitions, the measurement repair, common-input/role transfer, the Marcy hypothesis and annual tradeoff, two selected-hour error columns, and AC/holdout limitations. The annual and selected-hour table values were rechecked against the frozen CSVs. Detailed matrix, allocation and AC-control discussion moved out of the presentation into the linked reports.

Prepared independently from the two project reports and their numerical evidence. This file is a narrative/claim audit, not a new simulation or parameter fit. No existing model, output, or report was edited.

## Recommended framing

**Suggested title:** “NYgrid 2019 verification and compact-model calibration diagnostics”.

**Main message:** We reproduced the released historical DC study, repaired five measurement formulas without changing its electrical states, and ran a controlled transfer to the historical compact network. Source-informed Marcy-path experiments reduce annual pooled WAPE from 17.38% to 12.32%, with an important UPNY tradeoff. Selected compact snapshots are strong, but shared-parameter calibration, untouched validation and an AC realization of the Marcy variant remain unfinished.

Use “calibration diagnostics”, “representation experiment”, “source-informed topology hypothesis” or “fixed source-policy comparison”. Do not call this a newly calibrated electrical baseline: no new branch or injection parameter was fitted to interface observations. The compact ancestry retains its documented earlier S4/S7 calibration history, so also avoid claiming the entire network has never been fitted.

## Model identity ledger — show early and reuse consistent labels

| Deck label | Exact scope | What the evidence establishes |
|---|---|---|
| NYgrid source | 57 buses; 94 AC branch records; 4 MATPOWER DC-link records; 271 generator records | Released 2019 DC study, all 8,760 prepared local-hour labels; includes external equivalents/auxiliaries. |
| NY-only reference control | 46 original buses 37–82; 67 internal AC branch records; 243 native generator records | Exact fixed-snapshot DC replay of the NY portion after exporting NY-side AC/DC/HQ boundary effects. It is not an equivalent external response model for changed injections. |
| Historical compact | 51 buses; 92 branch records; 87 active | Existing historical compact topology. Fixed-DC paper-input transfer preserves bus injections and does not require its 35-record fleet to imitate every source unit. |
| Historical compact + Marcy hypothesis | 51 buses; 94 branch records; 89 active | Adds two AC-network branches used only in the DC approximation. No buses are added; no AC/DLR qualification of those two records is implied. |
| Separate restored-fleet AC checkpoint | Unchanged compact51 topology; 37 generator records including restored source-year nuclear representation | Three seasonal current-source inputs pass bounded AC optimization and fresh PF; this is a different experiment from the best Marcy DC snapshots. |
| Existing year-end 2025 variant | 71 buses | Preserved and unchanged by this task; do not attach the new 2019 scores to it. |

Sources: [source verification](../../../NYGRID_2019_INTERFACE_VERIFICATION.md); [reference export](../../nygrid_compact_2019/reference/REFERENCE_EXPORT.md); [compact construction description](../../nygrid_compact_2019/compact/export_description.json); [comparison report](../../../NYGRID_COMPACT_2019_COMPARISON.md).

## Suggested 22-slide outline

Each slide should have an outcome-bearing title and a short source footer. The following sources support the adjacent claims; they are not generic background citations.

### 1. NYgrid verification now supports a controlled compact-model comparison

State the purpose and date. Subtitle: “Historical 2019 DC reproduction, representation diagnostics, and a separate AC checkpoint.” Avoid “2025 model calibrated”.

Source: the two project reports linked above.

### 2. Annual error improves, while one important interface gets worse

Headline: compact paper-role WAPE 17.38% → 12.32%; source reference 11.22%. Preview Central East improvement and UPNY deterioration; reserve the selected good hour for later. These are the same 8,760 hours, paper inputs and common paper-role metering, not a comparison with the earlier four 2025 hours.

Visual: three annual bars plus two short tradeoff callouts.

Source: [annual/monthly metrics](../../nygrid_compact_2019/annual_monthly_metrics.csv), `period=annual`; [independent validation](../../nygrid_compact_2019/verification/independent_validation.json).

### 3. Four network roles must remain distinct

Show 57-bus source → 46-bus NY-only exact control; a separate branch to compact51 and compact51 + two Marcy branches. Place the unchanged 71-bus 2025 case in a separate box. Add a small note that the AC checkpoint uses compact51 without Marcy.

Source: model identity ledger above; [reference source-bus roles](../../nygrid_compact_2019/reference/source_bus_role_register.csv); [compact description](../../nygrid_compact_2019/compact/export_description.json).

### 4. NYgrid's useful method coordinates injections, locations and network representation

Historical thermal profiles; daily nuclear reconstruction; hydro split; zonal load allocation; external schedule reconstruction; selected Marcy additions; then DC PF. The released residual policy is J-only, not a universal prescription for later years. Source generation is reconstructed, not independently verified unit telemetry in this task.

Source: [pinned updateOpCond.m](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/updateOpCond.m); [allocateLoad.m](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/Utility/allocateLoad.m); [source report, input limits](../../../NYGRID_2019_INTERFACE_VERIFICATION.md).

### 5. Both the public input preparation and the DC replay were independently checked

12 NYISO archives, 365 daily files, 1,897,236 raw rows; all 157,680 hourly channel keys reproduced within 6.37e-12 in the published numeric units. All 8,760 source DC cases pass; independent branch replay error is about 1.21e-11 MW. Distinguish these machine-precision reproduction errors from model-versus-observation error.

Mention naive local time briefly: two interpolated labels and one combined fall-DST label. They remain in the primary annual score.

Sources: [NYISO source audit](../../nygrid_2019/nyiso_source_audit.json); [independent DC replay](../../nygrid_2019/independent_dc_replay.json). Optional footer: [official P32 archives](https://mis.nyiso.com/public/P-32list.htm).

### 6. “Ten percent error” requires a denominator

Show three definitions:

- Paper Eq. 11/released code: `100*(observed−simulated)/hourly positive limit` (signed).
- Annual interface WAPE: `100*sum(abs(simulated−observed))/sum(abs(observed))`.
- Selected-hour error: `100*abs(simulated−observed)/abs(observed)` for each interface.

Positive paper error means underprediction of signed flow. The negative limit is not used. West Central's positive limit is 9999 in every hour; that denominator is not a verified physical rating. Pooled WAPE spans overlapping interfaces and is not statewide energy imbalance.

Sources: [paper DOI](https://doi.org/10.1109/TPWRS.2022.3200887), Eq. 11; [released flow4Plot.m](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/Utility/flow4Plot.m); [source metric definitions](../../../NYGRID_2019_INTERFACE_VERIFICATION.md); [channel limit counts](../../nygrid_2019/nyiso_source_audit_channels.csv).

### 7. Five plotting formulas measure the wrong branch rows

Dysinger East, West Central, Moses South, UPNY–ConEd and Dunwoodie/Sprain are affected. Central East and Total East are not. The released `if.map` agrees with independently checked endpoint/role semantics. On identical solved states, literal plot WAPE is 60.66%; corrected-map WAPE is 11.22%. This is measurement repair, not improved dispatch or topology.

Visual: one UPNY endpoint example, plus “same PF → two measurement operators”.

Sources: [formula audit](../../nygrid_2019/operator_audit_formulas.csv); [term/end-point audit](../../nygrid_2019/operator_audit_terms.csv); [overall metrics](../../nygrid_2019/annual_reproduction_overall_metrics.csv). Avoid presenting the repair as a new fit.

### 8. Corrected reference accuracy is uneven across interfaces

Display annual WAPE: DE 22.49%, WC 46.81%, TE 7.24%, MS 8.99%, CE 9.63%, UPNY 9.91%, Dunwoodie 10.89%. Pooled WAPE is 11.22%. West Central has 1,006 opposite-direction hours; the seven-interface total is 1,092. All corrected IQRs lie within ±10% of the positive limit, but empirical 95% ranges are wider than ±15% for several interfaces.

Visual: per-interface WAPE bars; rating-normalized distributions only on a separately labelled panel.

Sources: [interface metrics](../../nygrid_2019/annual_reproduction_interface_metrics.csv), `scope=primary_all_naive_hours`, `operator_variant=corrected_released_if_map`; [existing figure PDF](../../nygrid_2019/annual_reproduction_comparison.pdf).

### 9. A successful DC replay is not a feasible operating baseline

8,745 source hours have at least one positive-RATE_A exceedance. DC PF did not enforce generator or equipment bounds; many branches are unrated. Do not describe these exceedances as failures of the reported flow-reproduction experiment, or zero RATE_A as unlimited validated capability. Exact paper-figure reproduction remains limited by the undisclosed original toolbox/code combination.

Sources: [verification report, limits/provenance](../../../NYGRID_2019_INTERFACE_VERIFICATION.md); [independent DC replay](../../nygrid_2019/independent_dc_replay.json); [toolbox manifest](../../nygrid_2019/toolbox_manifest.json).

### 10. Seven bus-role differences change both allocation and metering

Use the seven-row crosswalk (38; 46/47; 62; 69; 77; 79). Emphasize equivalent allocation roles rather than asserting one label set is geographic truth. All original 46 NY bus IDs exist in compact51. Five source generation landings lack compact generator records: 45, 49, 62, 74, 77. A fixed-DC transfer preserves their injections at the existing buses.

Sources: [bus-role crosswalk](../../nygrid_compact_2019/crosswalk_bus_roles.csv); [crosswalk review](../../nygrid_compact_2019/crosswalk_review.md); [pinned npcc_new.csv](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/Data/npcc_new.csv).

### 11. The 46-bus NY-only control preserves the reference problem

Original buses 37–82, 67 internal branches. Export 8 NY-side AC crossing effects, 4 DC schedules and the HQ injection once; keep native pre-PF generation, solved generation and bus-74 slack adjustment separate. All annual source internal flows reproduce to about 1e-11 MW. This proves each fixed snapshot, not external response under new NY injections.

Visual: ledger `native generation + boundary − net load`, with HQ separated.

Sources: [reference export contract](../../nygrid_compact_2019/reference/REFERENCE_EXPORT.md); [source branch register](../../nygrid_compact_2019/reference/source_branch_register.csv); [reference summary](../../nygrid_compact_2019/reference/reference_export_summary.json).

### 12. The comparison holds power scale and balancing policy explicit

Matrix A/B/C/D: two networks × paper/current inputs, plus Marcy variants. Paper-role operators on all arms and reference 74 in the DC matrix. One gamma, 0.358662225381536, multiplies every public P input/target/limit; percentages are unchanged and reactances are not scaled. B requires a declared exact compact-network Schur injection map: bus 9003 contributes 50/50 at 78/80. This is topology-dependent port equivalence, not observed generator relocation.

Sources: [comparison report, matrix](../../../NYGRID_COMPACT_2019_COMPARISON.md); [matrix rows](../../nygrid_compact_2019/network_input_matrix.csv); [independent Kron map](../../nygrid_compact_2019/crosswalk_kron_injection_map.csv); [Kron checks](../../nygrid_compact_2019/crosswalk_kron_validation.csv).

### 13. Marcy is a specific hypothesis, and the backbones are not identical

Add 43–38 with X=.0427 and 38–77 with X=.0147 pu on 100 MVA. Neither active endpoint pair existed. Retain 38–69 (NYgrid also retains it) and S4 38–39. No identical-edge duplicate is found; broader functional overlap is unresolved. Call these “two AC-network branch surrogates in the DC approximation”, not “two DC links”.

The source original NPCC file has 227 records, versus 233 in our inherited original parent. In particular, active 43–50 and 74–78 multiplicities differ, with S4 adding further parallel transfer paths. This comparison retained them; it did not prune branches to improve scores.

Sources: [modifyMPC.m](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/modifyMPC.m); [Marcy ledger](../../nygrid_compact_2019/crosswalk_marcy_hypothesis.csv); [network pairs](../../nygrid_compact_2019/crosswalk_network_pairs.csv); [S4 additions](../../nygrid_compact_2019/crosswalk_s4_additions.csv).

### 14. Marcy improves all monthly pooled scores but creates a UPNY tradeoff

Annual pooled WAPE: 17.3825% → 12.3172%, a **5.0653-percentage-point** reduction. Improvement occurs in all 12 months. CE: 49.23% → 7.09%. UPNY: 10.55% → 18.59%. WC remains 46.81%. Show the full per-interface table or paired bars; the variant does not meet a 10–15% per-interface target everywhere.

Sources: [annual/monthly metrics](../../nygrid_compact_2019/annual_monthly_metrics.csv); [independent validation](../../nygrid_compact_2019/verification/independent_validation.json). The source reference remains 11.2181%; do not round this to “the compact model matches NYgrid exactly”.

### 15. Total East diagnoses regional balance, not just impedance

At fixed regional injections in the lossless DC experiment, the complete western cut equals western net injection. Total East remains 7.235% WAPE before and after Marcy. Marcy changes sharing and Central East, while the total cut is unchanged. Keep the fixed-injection/complete-cut/DC qualifications next to the conservation equation; AC losses and redispatch require extra terms.

Sources: [Total East regional ledger](../../nygrid_compact_2019/total_east_regional_ledger.csv); [annual metrics](../../nygrid_compact_2019/annual_monthly_metrics.csv); [operator crosswalk](../../nygrid_compact_2019/crosswalk_operator_members.csv).

### 16. A strong compact example exists across every interface

July 3, 2019 at 04:00: pooled 3.2787%; worst interface 4.8518%; zero wrong directions. Show seven observed/model bars or a compact table. Label “retrospectively selected minimax development example”. The lowest pooled-error hour is different: September 6 at 02:00, pooled 1.7732% but worst interface 16.1524%. Selection criteria must remain visible.

Sources: [best snapshots](../../nygrid_compact_2019/best_snapshots.csv); [per-interface selected errors](../../nygrid_compact_2019/best_snapshot_interface_errors.csv); [independent selected checks](../../nygrid_compact_2019/verification/independent_validation.json). Do not conflate this with the source's January 8 15:00 example, which has 2.0321% pooled and 4.0683% worst error.

### 17. The paired matrix separates several causes of mismatch

Show the five-hour A/B/C/D/C_marcy/D_marcy heatmap. The July 17 08:00 current-source snapshot is excluded for its earlier boundary-coverage gap, while the full paper-input annual study still contains that hour. Paper input preparation is raw-sample arithmetic mean; current boundary preparation is forward hold. B includes the declared Schur spatial mapping. These are meaningful but not perfectly isolated “generation-only” differences.

Sources: [network/input matrix](../../nygrid_compact_2019/network_input_matrix.csv); [comparison report](../../../NYGRID_COMPACT_2019_COMPARISON.md); [input export description](../../nygrid_compact_2019/compact/export_description.json).

### 18. Fixed source-policy comparisons do not choose a universal winner

Statewide thermal residual normalization improves four of five examined hours relative to literal J-only allocation on the tested network. Current hydro spatial allocation improves two and worsens three. Load spatial replacement changes both role membership and weights; it is not a pure within-zone weight test. The released July St. Lawrence estimate is 921.12 MW against an 856-MW source capacity assumption, so faithful reproduction is not source-capability qualification.

Sources: [allocation ablations](../../nygrid_compact_2019/allocation_ablations.csv); [movement ledger](../../nygrid_compact_2019/allocation_movement_ledger.csv); [reference component report](../../nygrid_compact_2019/reference/REFERENCE_EXPORT.md). Describe the examples as diagnostics, not fitted parameters or untouched tests.

### 19. Three separate current-source snapshots pass bounded AC checks

Unchanged compact51 without Marcy; restored historical fleet. January 21, April 21 and July 20 pass bounded optimization and fresh PF. Solvers MIPS/IPOPT/MIPS; the failed April MIPS physical audit remains in the attempt ledger. Dispatch L1 movements are 162.46, 5.05 and 168.31 benchmark MW. Loads/boundaries/equipment bounds are unchanged and interfaces are absent from the objective.

Sources: [AC summary](../../nygrid_compact_2019/ac_checkpoint/summary.csv); [attempts](../../nygrid_compact_2019/ac_checkpoint/attempts.csv); [independent replay](../../nygrid_compact_2019/ac_checkpoint/independent_replay.csv). This does not qualify July 3 or the Marcy surrogate's AC parameters.

### 20. AC agreement includes redispatch and large control movement

For the three common-target cases at reference42, current-role WAPE is 19.06% DC → 17.54% AC; paper-role WAPE is 23.43% → 22.47%. These 21 comparisons are not the annual reference74 matrix. Reverse AC members use upstream PT. Maximum voltage movement is .145–.183 pu; Q movement is 3,518–8,096 MVAr. April losses rise about 98.99→206.54 benchmark MW. The P-only objective can change losses via voltage/Q controls to retain prior P: a control-reference policy is needed.

Sources: [AC scoring summary](../../nygrid_compact_2019/ac_scoring/summary.json); [AC control summary](../../nygrid_compact_2019/ac_scoring/AC_feasibility_and_control_summary.csv); [comparison report, separate AC checkpoint](../../../NYGRID_COMPACT_2019_COMPARISON.md). Say “combined AC/redispatch/control effect”, not “pure AC-loss penalty”.

### 21. Next calibration should estimate a small shared parameter set

Proposed work, not completed results: source-bounded uncovered-unit allocation, constrained hydro geography/energy, UPNY sharing and supported backbone hypotheses. Fit shared parameters on designated development blocks, report dispatch/control movement, freeze the method, then evaluate genuinely unexamined periods. Resolve R/B, finite ratings and reactive controls before an AC/DLR realization of the Marcy case. Do not tune conductor parameters to hide electrical residuals.

Source: [comparison report, next decision](../../../NYGRID_COMPACT_2019_COMPARISON.md). Mark this slide “proposed” so no viewer mistakes the optimization formulation for an implemented fit.

### 22. The deliverable is reproducible evidence with an explicit boundary

188 independent comparison checks cover all annual predictions, 30 matrix rows, 25 ablations and six selected DC replays. Source/Kron/AC replay evidence is saved separately. The new result is useful historical DC representation evidence; the 71-bus year-end 2025 case remains unchanged, and no new shared-parameter fit, untouched prediction or DLR qualification is claimed.

Sources: [independent validation report](../../nygrid_compact_2019/verification/independent_validation.md); [verification JSON](../../nygrid_compact_2019/verification/independent_validation.json); [reproduction guide](../../../scripts/nygrid_compact_2019/README.md).

## Phrases and claims to reject during final PDF review

| Avoid | Accurate replacement |
|---|---|
| “We calibrated the 71-bus 2025 model to 3%.” | “A separate 51-bus 2019 DC hypothesis has a retrospectively selected 3.28% pooled-error example.” |
| “The paper achieves less than 10% observed-flow error.” | “Its rating-normalized IQR claim is distinct from annual observed-flow WAPE; reference WAPE varies by interface.” |
| “All seven plotting formulas were wrong.” | “Five are affected; Total East and Central East require no index repair.” |
| “Correction improves the network from 60.66% to 11.22%.” | “Changing measurement coefficients on identical states changes the reported score.” |
| “The paper's Figure 5 was reproduced unchanged.” | “The released study was reproduced with a documented plotting repair and toolbox compatibility provenance.” |
| “The 46-bus model predicts external responses exactly.” | “It reproduces fixed snapshots with extracted source-model terminal injections.” |
| “Source boundaries are observed tie-line telemetry.” | “Public schedules drive source equivalents; extracted terminal flows are model-derived.” |
| “Marcy adds two HVDC links.” | “Two AC-network branch surrogates are added to the DC approximation.” |
| “No double counting is possible.” | “No identical active endpoint pair is duplicated; broader equivalent overlap remains unresolved.” |
| “Remove 38–69 to replace Marcy.” | “Retain it: the source also keeps 38–69 alongside both Marcy additions.” |
| “Both models start from the same electrical backbone.” | “Both are NPCC-derived; original files have 227 versus 233 records and different parallel multiplicities.” |
| “The best pooled hour is the most accurate on every interface.” | “Pooled and minimax rankings are separate; disclose both.” |
| “Marcy fixes Total East.” | “At fixed paper inputs the Total East cut is unchanged; Central East sharing improves.” |
| “The J-only allocation is proven superior.” | “The fixed-policy diagnostics show no universal advantage; normalization improves four tested hours.” |
| “AC feasibility validates the best DC Marcy case.” | “The AC checkpoint uses separate inputs and the unchanged compact51 topology.” |
| “AC effects add/remove X% error through losses.” | “The measured change combines AC physics, reference balancing, redispatch and control movement.” |
| “No parameters have ever been fitted.” | “No new interface-target fit occurred in this experiment; earlier compact construction history is retained.” |
| “Successful PF proves equipment adequacy.” | “DC solver success and bounded AC/thermal qualification are separate.” |
| “Independent replay is independent validation against reality.” | “Replay checks numerical reproducibility; input/model assumptions remain separate evidence questions.” |

## Presentation checks when the PDF is available

- Every score needs model, time coverage, operator, denominator and scale where relevant.
- Main annual chart must include the UPNY deterioration and unresolved West Central error.
- Model lineage and the unchanged 71-bus scope should be visible before comparing results.
- Footnotes should distinguish the 8,760-hour source study, five-hour matrix, three-hour AC checkpoint and selected-hour examples.
- Do not truncate the lower bars of observed/model snapshot charts to exaggerate agreement; show units and complete interface names.
- Use “percentage points” for 17.38−12.32; do not label the 5.07-point difference a 5.07% relative reduction.
- Keep the April Q/voltage/loss caveat on the AC-result slide rather than only in the appendix.
- Count AC branch records and active branches separately; preserve the four genuine source DC-link records as a different device type.

## Audit provenance

Primary reports read: `NYGRID_2019_INTERFACE_VERIFICATION.md` and `NYGRID_COMPACT_2019_COMPARISON.md`. Quantitative claims were checked against the cited CSV/JSON outputs rather than inferred from plots. The crosswalk, source-model counts and independent Kron evidence were previously audited from the actual pinned MATPOWER arrays. No new fitted solution or uncertainty estimate was generated for this content audit.
