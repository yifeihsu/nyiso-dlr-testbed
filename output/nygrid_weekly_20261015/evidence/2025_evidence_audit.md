# 2025 operating-input and current-error evidence audit

Read-only audit of saved evidence on branch `codex/s13-phase1b-upny-coned`, HEAD `0e73b46fed7d9e859d7f1683be019b169270d095`. No new annual simulation was run for this audit. No pre-existing model, source, report, map, or artifact was edited. The existing dirty `NYGRID_2025_WESTERN_SOURCE_AUDIT.md` was read only; its numerical claims were treated as an earlier DC stage and not substituted for the current AC metrics.

## One presentation-safe status sentence

The current 2025 reconstruction closes the AC equations on all 8,651 source-qualified hours out of 8,760 calendar hours, but no hour passes the full operating gate; its seven interface comparisons are diagnostic public-series comparisons, with physical P32 meter equivalence still uncertified.

The current numerical source is `output/nygrid_2025_moses_repair/annual/moses_repair_v1/comparison/public_interface_metrics.csv`, selected by `cohort=candidate_all_success`, `period=annual`, `model=candidate`, `convention=legacy_signed_literal_from`. All values below are public MW or percentages. Do not compare these directly with historical 2019 errors or with benchmark-scaled MW.

## Current errors, ranked both ways

| Interface | MAE rank | MAE public MW | WAPE rank | WAPE % | Signed mean bias public MW |
|---|---:|---:|---:|---:|---:|
| Total East | 1 | 499.304 | 4 | 15.949 | -340.157 |
| Dysinger East | 2 | 249.433 | 2 | 29.742 | -68.489 |
| West Central | 3 | 247.053 | 1 | 44.362 | -71.926 |
| UPNY ConEd | 4 | 235.207 | 7 | 7.844 | -35.743 |
| Central East - VC | 5 | 208.719 | 5 | 12.545 | +112.615 |
| SPR/DUN-SOUTH | 6 | 177.242 | 6 | 9.592 | -75.480 |
| Moses South | 7 | 108.945 | 3 | 20.178 | +24.320 |

WAPE is `100 * sum(abs(prediction-observation)) / sum(abs(observation))` over exactly the same 8,651 hours. It is not the mean of hourly percentage errors. The low WAPE at UPNY and SPR should not obscure their 235 and 177 MW absolute errors. UPNY MAE changed by only +0.000278 MW and SPR by approximately -0.000000195 MW in the latest Moses repair, so the latest northern repair did not materially alter the downstate scores.

## Source -> native resolution -> transformation -> modeling assumption

| Input | Source and native resolution | Transformation into the 2025 model | Assumption or qualification | Authoritative local evidence |
|---|---|---|---|---|
| Gross NY load | NYISO P58C integrated hourly zonal load; 11 zones, all 96,360 zone-hours qualified | Physical UTC axis for local 2025; source EST/EDT and both fall hours retained. Multiply public MW once by gamma. Allocate zones to buses with frozen paper-parent positive-load shares; revised G shares and J half/half fallback inherited before downstate refinement | P58C labels treated as hour beginnings following empirical P58B/P58C timing audit; this is not a provider integration specification. Substation shares are estimates, not measured bus demand | `NYGRID_2025_OPERATING_INPUTS.md`; `output/nygrid_2025_inputs/load_source/quality_summary.json`; `source_receipts.csv`; `output/nygrid_2025_inputs/model/scaling_manifest.json` |
| Common scale | Paper-source NPCC NY snapshot anchor 9,561 MW and complete 2025 observed load peak 31,857.1773 MW at June 24 18:00 EDT / 22:00 UTC | `gamma=9561/31857.1773=0.30012075175285535`; same factor for demand, generation/capability, interchange and interface observations; model interface output divided by gamma once for public MW | Additional benchmark peak normalization is user-requested, not the original paper's actual-MW strategy. It removes between-year peak growth in benchmark MW. Currents remain model amperes and are never divided by gamma | `output/nygrid_2025_inputs/scaling_audit.json`; `model/scaling_manifest.json`; current `comparison/scoring_receipt.json` |
| Q demand and neighboring loads | Inherited NPCC P/Q plus observed total NY demand | NY QD at 0.98 lagging power factor; external absolute PD and signed QD follow NY total / 9,561, preserving external source Q/P | All QD and neighboring demand are assumed profiles, not 2025 measurements | `NYGRID_2025_OPERATING_INPUTS.md`; `output/nygrid_2025_inputs/scaling_audit.json` |
| Statewide generation by fuel | NYISO P63, nominal five-minute statewide fuel observations; all seven categories have 8,750 qualified hours, ten gaps | Source sample at t represents preceding interval; integrate to UTC hour beginnings; gaps >600 s uncovered. Allocate/reconcile through generation priors and bounded dispatch; current reconciled HY is retained in latest repair | No plant name or PTID: statewide fuel observations cannot validate hourly plant dispatch. Current reconciled HY differs from raw P63 by mean -3.803372 MW, MAE 4.886582 MW | `output/nygrid_2025_inputs/generation_source/generation_summary.json`; `source_manifest.csv`; `statewide_fuelmix_hourly.csv`; latest `generation/generation_policy.json` |
| Fossil preferences | EPA CAMPD hourly reporting-unit gross-load rate and operating fraction; unique ORIS/unit/hour; NY source plus NJ market members | Multiply gross rate by operating fraction once; unique reporting identities and explicit plant/unit splits; align local standard time to UTC; use gross shares to allocate P63 fossil total, then bounded weighted projection | Gross output is not net electrical injection. Crosswalks do not make reporting units unique generators. Missing is not zero. Market/CHP scope and shared steam allocation remain qualifications | `NYGRID_2025_BOUNDED_DISPATCH.md`; `output/nygrid_2025_inputs/generation_source/epa_unit_identity_register.csv`; `generation_summary.json`; `output/nygrid_2025_dispatch/priors/fuel_hourly_scope_conflicts.csv.gz` |
| Fleet identity and capability | Versioned EIA-860 2025 early-release plant/unit inventory and seasonal capability; corroborating NYISO Gold Book/rosters | Unique plant-generator identities; NYIS market scope including corroborated Bayonne/Linden; retirement/start-month rules; electrical landings from explicit identities, inherited anchors, then same-zone geographic proxy | Seasonal capacity and admission are not actual hourly unit commitment or forced outage telemetry. Some proxy landings remain coarse. Retired Indian Point is excluded. Original fleet used 1,436 native rows; latest repair appends St. Lawrence unit 21 as native row 1465 | `NYGRID_2025_BOUNDED_DISPATCH.md`; `output/nygrid_2025_dispatch/fleet/fleet_register.csv`; `source_scope/source_receipts.json`; `output/nygrid_2025_moses_repair/generation/generation_policy.json` |
| Nuclear preferences | NRC daily reactor availability plus EIA seasonal capability | Availability * capability, normalized to P63 nuclear; previous daily report used before 08:00 Eastern; availability also bounds reconstructed output | Daily availability is not hourly metered nuclear generation | `output/nygrid_2025_inputs/generation_source/generation_summary.json`; `nrc_daily_reactor_status.csv`; `nuclear_plant_hourly_priors.csv.gz` |
| Hydro preferences and latest St. Lawrence repair | EIA-923 plant-month energy; initial priors used 2025 early release; final 2025 release independently checked in western audit and used for current St. Lawrence exact constraints | Conventional hydro monthly priors + finite headroom. Current St. Lawrence plant 2694 exactly meets 12 final-EIA monthly targets totaling 6,726,939 MWh over all physical month hours, including latent excluded-hour ledger. Minimum squared deviation from prior, then bounded redistribution of other HY; current hourly reconciled HY preserved | Exact monthly energy is not hourly dispatch validation. 15 active 57 MW units -> 855 MW engineering ceiling, not measured net hourly capability. Pumped hydro positive output retained; pumping/SOC not newly validated. The ten P63-gap hours are interpolated only in the latent energy ledger and remain excluded | `output/nygrid_2025_moses_repair/generation/generation_policy.json`; `StLawrence_monthly_energy_ledger.csv`; `independent_generation_review.json`; `output/nygrid_2025_western_audit/generation/EIA923_target_vintage_comparison.csv` |
| Wind and other renewables | P63 statewide signal + EIA active capacity; solar geometric daylight proxy | Wind distributed using identical statewide capacity factor/nameplate shares; South Fork is within zone K's share, never added twice. Other renewable distribution uses active capacity/daylight | No plant-specific weather/curtailment or energy constraints. Current Zone D wind assignment contradicts independent annual EIA energy under model nonnegative bounds. Solar/BTM market boundary approximate | `output/nygrid_2025_inputs/generation_source/generation_summary.json`; `scripts/nygrid_2025_inputs/generation_priors.py`; `output/nygrid_2025_postrepair_diagnosis/generation/D_wind_source_energy_review.json` |
| Regional actual interchange, current choice | EIA-930 NYIS-reported bilateral physical exchanges with IESO, ISNE, PJM, HQT; hourly; 35,040 region-hours; retrieved 2026-10-11 | Negate export-positive values to import-positive; UTC hour ending minus one hour -> hour start. Apply frozen regional external-generator shares; reproject native output against net balance with same original priors/weights/bounds. Preserve regional totals in latest AC contract | Actual regional totals condition the reconstruction. They are not individual tie flows; DC/AC partition remains conditional. PJM counterparty disagreement remains unresolved (594.856 MW MAE on stated overlap), without score-driven filtering or substitution | `NYGRID_2025_WESTERN_SOURCE_AUDIT.md`; `output/nygrid_2025_western_audit/boundary_actuals/source_audit_receipt.json`; `boundary_source_review/independent_boundary_review.json`; `dispatch/all_boundary_dispatch_receipt.json` |
| Legacy schedule/device channels | P32 SCH channels and four inherited DC-device schedules | Ten disjoint region/device channels establish inherited accounting; duplicate HQ aggregate not counted again. Current aggregate regional totals replaced by EIA-930; four original DC schedules retained inside those totals | Schedules are not actual flows; within-region allocation is conditional. HQ/Cedars is aggregate regional input | `NYGRID_2025_OPERATING_INPUTS.md`; `NYGRID_2025_WESTERN_SOURCE_AUDIT.md` |
| Ontario Moses PAR controls | NYISO P34 PS33/PTID25118 and PS34/PTID25119, nominal five-minute postings; 211,996 native readings; 8,673 qualified hours | Forward-held time-weighted complete-hour means; max native gap 600 s; no fill/clipping. Sign positive Ontario -> Moses, documented effective 2024-12-03. Two ideal lossless transfer records replace passive parent211 contribution; necessary per-bank P screen against 300 MVA | `dcline` container is a transfer equivalent, not physical HVDC. No actual tap trajectory or full P/Q/current/thermal envelope. Raw `Flow(MWH)` numeric-as-MW interpretation remains conditional | `NYGRID_2025_VERIFIED_PAR_CONTROLS.md`; `output/nygrid_2025_par_controls/controls/input_receipt.json`; `necessary_p_only_screen.json` |
| PAR schedules, separate evidence | NYISO P53A, 60-minute schedule periods; 23/24/25-hour days; 17,520 Moses device-hours | Preserve full physical hours and raw signed G/L/control metadata separately. Dover P53A file is metadata-only in local audit | Moses P53A G/L sign is not independently verified; it is not substituted for P34 controls. Do not label P53A as observed dispatch or current applied Dover flow | `output/nygrid_2025_par_controls/controls/input_receipt.json`; `NYGRID_2025_VERIFIED_PAR_CONTROLS.md`; `output/nygrid_2025_dover_parameters/local_audit/Dover_P53A_channel_metadata_only.csv` |
| Dover bank controls | P34 T398-A/PTID625149, T398-B/PTID625150; nominal five-minute posts; 187,324 native records including endpoint | Separate bank signs retained; positive Long Mountain -> Cricket Valley becomes negative NY-to-CT branch flow. Full-service model boundary 2025-12-20 04:00 UTC (Dec19 23 EST). 287 source-qualified post-boundary hours. Bounded controller targets nonzero bank postings; 18 ambiguous zero-posting hours retain normal parallel topology with explicit neutral-phase assumption | Not first energization. Early zeros do not prove zero total intertie transfer; breaker/bypass states unavailable. Conditional MW/header semantics and historical direction. Two independent PTIDs do not establish independent sensor accuracy. Engineering X/tap bounds are not manufacturer-certified | `NYGRID_2025_DOVER_PARAMETERS_APPLIED.md`; `output/nygrid_2025_dover_parameters/local_audit/Dover_P34_input_receipt.json`; `replay/Dover_bank_states.csv` |
| PV20 northern routing | P34 Sand Bar PS01/PTID325270; 105,998 native observations; 8,673 complete hours, including all current 8,651 | Forward-held means; current diagram positive Sand Bar -> Plattsburgh. Fixed P, Q=0 boundary row1466 at model bus49; opposite ISO-NE-pool adjustment so aggregate ISO-NE import is unchanged. Qualified mean -75.988526 MW | Not a physical new AC/DC line. 2025 sign effective date unverified. Sand Bar != Plattsburgh: South Hero net load, intervening losses and bypass transfers omitted by proxy. No invented impedance or tap | `output/nygrid_2025_moses_repair/boundary/PV20_source_receipt.json`; `boundary_verification_receipt.json`; `ISO_NE_PV20_disaggregation_contract.csv` |
| Interface observations / score only | NYISO P32 public interface values; nominal five-minute source; 8,673 source-qualified hours before intersecting other inputs | Frozen forward-hold hourly aggregation, exact UTC axis, gamma conversion once, predeclared legacy operator and common 8,651 cohort | Not used to choose gamma, source values, bus mapping, priors or repairs. Physical P32 membership, terminal convention and numeric `Flow(MWH)` interpretation are uncertified. +/-9999 limits are invalid, not ratings | `output/nygrid_2025_inputs/load_source/quality_summary.json`; current `comparison/scoring_receipt.json`; `public_interface_metrics.csv` |

## Strong findings versus unresolved causes

### Total East: controlled cause of the latest regression, not full real-world attribution

Two-factor annual ablations, all 8,651 hours:

| MAE public MW | Previous physical repair B | Hydro only G | PV20 only P | Combined GP |
|---|---:|---:|---:|---:|
| Total East | 471.551177 | 465.320064 | 507.402104 | 499.304073 |
| Moses South | 118.820924 | 141.586389 | 123.014514 | 108.944975 |

For Total East, order-averaged PV20 effect is +34.917468 MW MAE; hydro is -7.164572 MW; sum +27.752896 MW (+5.89%). Mean-flow effects are -71.792482 MW PV20 and +17.420963 MW hydro, sum -54.371520 MW. Existing underprediction deepens from -285.785565 to -340.157085 MW. Interaction -1.866918 MW MAE is already divided between the order-averaged effects, not added again.

The current proxy imposes `Total East = Central East + parent224`. The physical Summer 2025 source has 29 Total East entries versus five model-parent proxy terms; Central East's four-parent proxy also lacks explicit PV20. A source-directed one-term readout sensitivity changes TE 499.304 -> 463.439 MW MAE but CE 208.719 -> 248.059. This is not a complete operator repair. Observed mean TE-CE minus modeled parent224 is 452.772 MW, an operator-relationship gap rather than evidence that one physical line is wrong by that amount.

Evidence: `NYGRID_2025_POSTREPAIR_DIAGNOSIS.md`; `output/nygrid_2025_postrepair_diagnosis/ablations/factorial_metrics.csv`; `factorial_attribution.csv`; `TotalEast_CentralEast_proxy_identity.csv`; `boundary/readout_sensitivity_metrics.csv`.

### Zone D wind: independently sourced energy conflict

Six matched NYIS wind plants (Clinton, Ellenburg, Marble River, Altona, Chateaugay, Jericho Rise) report 1,425,010 MWh in final 2025 EIA-923. Current model assigns 1,662,733.250582 MWh in qualified hours alone: excess 237,723.250582 MWh. Under the current nonnegative excluded-hour assumption, at least 27.479280 MW must be removed from mean qualified-hour Zone D wind. The lower bound does not use guessed excluded-hour profiles. EIA can report negative net generation; reconciling the excess only in 109 missing hours would require -2,180.947 MW mean net output, and no actual station-service lower bound is invented.

This capacity-share allocation mechanism is established in code. On the current fixed northern balance, with other inputs and saved terminal correction fixed, removing the lower-bound wind excess would move Moses bias +24.319610 -> at most -3.159670 MW. This diagnoses mean-input inconsistency, not a correct hourly wind profile, a proven MAE reduction, or physical meter validation. No correction has yet been promoted into the model.

Four raw EIA frequency codes are AM (monthly values supplied once annually), two are M. AM is not A (estimated monthly allocation). The annual-energy finding does not depend on this frequency distinction.

Evidence: `output/nygrid_2025_postrepair_diagnosis/generation/D_wind_source_energy_review.json`; `D_wind_asset_source_crosswalk.csv`; `D_wind_annual_EIA_comparison.csv`.

### St. Lawrence and northern meters: important but unresolved

Monthly EIA energy is exactly anchored; hourly shape is reconstructed. The 855 MW ceiling binds in 3,161 qualified hours. Daily mean St. Lawrence output is 647.5 MW at 03:00 versus 833.4 at 17:00; Moses residual means are -75.2 and +61.6 MW. These associations alone are not causal telemetry.

A source-defined monthly-flat/minimum-variance control preserves monthly energy and hourly HY balance. With the original terminal correction frozen, conditional annual Moses MAE becomes 90.187 MW versus 108.945, bias 24.821 versus 24.320. Only 12 extreme-change AC pairs were validated; this is not a new annual validated repair. St. Lawrence alone cannot reconcile residual-implied monthly energy in any of the 12 months under current other inputs/boundary/terminal assumptions, even allowing excluded-hour output 0..912 MW. Other terms or observation mapping must change.

Physical identity: `PV20_Platt_import = P34_SandBar_toward_Platt - SouthHero_net_load - intervening_real_losses + bypass_or_unmetered_transfer`. The 6.66 MVA documented peak of one South Hero feeder is not a bound on the full meter difference. HA2 documentary energization is Oct13 2025; HA1 is Mar27 2026, and neither identifies exact P32 cutover hour. The northern flow balance is fixed by injections; changing X cannot independently repair that balance.

Evidence: `NYGRID_2025_POSTREPAIR_DIAGNOSIS.md`; `output/nygrid_2025_postrepair_diagnosis/daily_profiles.csv`; `monthly_flat_frozen_terminal_scores.csv`; `generation/shape_ac/monthly_flat_AC_receipt.json`; `conditional_StLawrence_only_energy_compatibility.csv`; latest `boundary/PV20_source_receipt.json`.

### Western errors: common balance problem remains, exact attribution unresolved

The earlier DC western source audit established the mechanism `Dysinger East = Zone A generation - Zone A load + western Ontario net import`; `West Central - Dysinger East = Zone B generation - Zone B load`. Its near-identical western residuals motivated source correction. Those historical DC correlation values are not asserted as freshly measured properties of the current AC run.

Final EIA validated all 108 pre-used Niagara/Lewiston/Gilboa monthly target quantities. This rules out that specific arithmetic/source-vintage defect, not the hourly hydro shape. Niagara uses a soft plant-month prior with statewide projection; exact three-terminal hourly dispatch remains unknown. A new Dysinger-East Stolle Road345 PAR circuit is documented but omitted; source evidence does not yet establish complete 2025 terminal/control/rating/operator details. Current errors cannot be uniquely assigned to Niagara output, omitted control or physical-meter mismatch. Adding arbitrary generation or fitting X to a residual is unsupported.

Evidence: `NYGRID_2025_WESTERN_SOURCE_AUDIT.md`; `output/nygrid_2025_western_audit/generation/generation_audit.json`; `generation/EIA923_target_vintage_comparison.csv`; `mapping/physical_source_scope.json`; `balance/balance_validation.json`.

## Current validation boundary

| Check | Current established result |
|---|---|
| Calendar retained | 8,760 positions; 109 exclusions preserved |
| Source-qualified / attempted / converged / equation-qualified | 8,651 / 8,651 / 8,651 / 8,651; zero exceptions |
| Full operating gate | 0 hours |
| Overvoltage / undervoltage hours | 8,651 / 599 |
| Generator Q / assumed S violation hours | 8,651 / 8,651 |
| Branch MVA violation hours | 4,793 |
| Voltage range | 0.841226 to 1.076098 pu |
| Parent41 hardware-current exceedance hours | 2,712 |
| Max direct branch-power recomputation discrepancy | 2.7815e-10 MVA |
| Max nodal P/Q residual | 6.7388e-09 MW / 1.0000e-08 MVAr |
| Max passive/full voltage recovery discrepancy | 7.0210e-14 pu |
| Target parent185 / parent195 voltage violations | 0 / 0; local repair success does not imply full-network feasibility |

Sources: current `annual_receipt.json`, `validation/annual_input_accounting_review.json`, `validation/annual_physics_review.json`, `comparison/scoring_receipt.json`, `comparison/independent_scoring_crosscheck.json` under `output/nygrid_2025_moses_repair/annual/moses_repair_v1/`.

The summary may say "validated equation closure, exact reduction/recovery and source accounting." It must not say "validated 2025 operating model," "all 8,760 hours solved," "observed unit dispatch," "certified physical interface errors," or conflate the present 2025 results with the frozen 2019 reproduction.
