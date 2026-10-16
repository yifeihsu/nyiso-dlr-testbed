# Presenter notes — weekly report, October 15, 2026

Slide numbers include the title page. Source paths below are relative to the repository root. This deck summarizes saved, completed research artifacts at snapshot `0e73b46fed7d9e859d7f1683be019b169270d095`; preparing the deck did not rerun annual power flow or change the model. The current annual result is `moses_repair_v1`. Earlier construction and source-audit results are historical stages, not interchangeable current metrics.

## 1. Weekly Report

- The story is the progression from the paper's 2019-data reference, through downstate network detail, to the current 2025 operating reconstruction and its largest remaining errors.
- Keep three achievements separate: building a more explicit network, satisfying its equations, and reproducing public measurements. None alone establishes full physical operating validity.
- The report date remains October 15, 2026; some source-review receipts have October 16 UTC timestamps.

Sources: `main.tex`; `source_manifest.json`; `NYGRID_2025_MOSES_REPAIR.md`; `NYGRID_2025_POSTREPAIR_DIAGNOSIS.md`.

## 2. The 2019 Reference and the Current Model

- The paper was published in IEEE TPWRS in 2023; 2019 is its example operating-data year. Do not call it a paper published in 2019.
- The authors' released benchmark is 57 buses and 94 AC branch records. Our separate 140-bus structural counterpart retains the original NPCC bus identities; it is the parent of the downstate work.
- The 191-bus station-detail stage adds 51 station/terminal representations. The current AC solve retains 148 buses and recovers the rest algebraically.
- The 266/267 detailed AC count includes 75 numerical line-section points and, after Dover full service, one regulated port. It does not mean 267 physical substations.

Sources: `NYGRID_RELEASED_2019_COMPARISON.md`; `NYGRID_2019_DLR_REBUILD.md`; `NYGRID_2025_DOWNSTATE_REFINEMENT.md`; `output/nygrid_2025_moses_repair/delivery/structure/current_structure_inventory.json`.

## 3. Downstate Network Modifications

- Use the diagram to explain which coarse connections are now exposed as named ports and receiving paths. It is selected connectivity, not a complete geographic or electrical one-line diagram.
- All 140 original NPCC bus identities remain. Eight added 345-kV ports remain explicit: East Fishkill, Wood Street, Ladentown, Dunwoodie, East Garden City, Gowanus, Rainey and Cricket Valley.
- The other 43 added terminals are passive in the declared model and are reduced and recovered. Their elimination is mathematical; it does not delete the represented source paths.
- Several voltage ports or parallel circuits are combined in the drawing. Detailed branch IDs and distinctions remain in the source registers.

Sources: `NYGRID_2025_SLIM_DOWNSTATE.md`; `output/nygrid_2025_slim/network/retained_station_rationale.csv`; `output/nygrid_2025_downstate/network/bus_register.csv`; `branch_register.csv`; deck `figures/data/`.

## 4. Corridor Detail and Dated Operating States

- Separate historical detail from projects actually entering service in 2025. A feature absent from the frozen reference is not necessarily a newly built 2025 asset.
- Rainey–Corona is present throughout 2025. Gowanus–Greenwood activates May 21 at 00:00 EDT and Goethals–Fox Hills May 30 at 00:00 EDT in the model. These use the next midnight after day-precision completion notices, not observed breaker-switch timestamps.
- Dover's retained full-service boundary is December 19, hour beginning 23 EST, equivalent to December 20 at 04:00 UTC. It is not claimed as first energization. Two parallel banks are explicit; actual taps and hourly bypass states remain unknown.
- Nine predecessor aggregate records remain inactive to prevent counting complete old and new paths twice. F84's documented energization date is July 28, 2019.

Sources: `NYGRID_2025_DOWNSTATE_REFINEMENT.md`; `output/nygrid_2025_downstate/network/replacement_register.csv`; `sources/upgrade_register.csv`; `NYGRID_2025_DOVER_PARAMETERS_APPLIED.md`; `output/nygrid_2025_line_parameters/sources/projects/CV_InServiceNotice_20190729.txt`.

## 5. Updating the Operating Inputs to 2025

- P58C supplies hourly gross zonal load. P63 supplies statewide generation by fuel, not plant dispatch. EIA-860 supplies unit identity/capability and EIA-923 plant energy; EPA gross reporting-unit output and NRC daily availability support source priors. Individual generator schedules remain reconstructed.
- EIA-930 uses a consistent NYIS reporting perspective for Ontario, New England, PJM and Hydro-Québec. Export-positive is negated to import-positive; UTC hour-ending labels move back one hour. These actual reported regional exchanges condition the reconstruction; they do not establish every individual tie flow.
- P34 device postings are aggregated hourly with gap checks. Ontario PS33/PTID25118 and PS34/PTID25119 are positive from Ontario toward Moses, with an explicit December 3, 2024 effective date. That verification must not be transferred to PV20 or Dover's historically qualified directions.
- P53A schedules remain separate evidence. Their Moses G/L sign was not independently established, and they are not substituted for P34 reported controls. The Ontario control records use the `dcline` container as transfer equivalents; they are not new physical HVDC links.
- P32 is the interface comparison source. Source values, signs and repair parameters were not fitted to P32. This does not mean residual diagnostics were never used to prioritize an investigation.
- The common physical-hour axis retains all 8,760 positions, with 109 excluded from the current source-qualified replay. No missing hour is silently promoted as a model prediction.

Sources: `NYGRID_2025_OPERATING_INPUTS.md`; `NYGRID_2025_BOUNDED_DISPATCH.md`; `NYGRID_2025_WESTERN_SOURCE_AUDIT.md`; `output/nygrid_2025_par_controls/controls/input_receipt.json`; `output/nygrid_2025_moses_repair/boundary/PV20_source_receipt.json`.

## 6. AC Reconstruction of the Declared Network

- The latest solver couples voltages with the declared loss-accounting policy. P58 actual load is treated as a loss-inclusive boundary balance: served demand plus assigned NY losses equals frozen gross zonal load.
- Native generation and signed HQ injection remain fixed during loss balancing; external regional loss participants supply their assigned internal/border losses while preserving NY terminal import targets. Spatial loss ownership and served-load allocation are modeling assumptions.
- The complex-admittance reduction solves 148 retained voltages and reconstructs detailed voltages and original branch currents. It preserves the declared synthetic network, rather than independently validating installed assets.
- Parent 41's R/X/B and conductor realization were made coherent. Parents 185/195 retain the same total nominal reactor rating but distribute compensation in proportion to section charging at section endpoints.
- Conductor DLR excludes voltage-changing branches. This does not remove their declared equipment, terminal-current or branch-MVA screens. Installed line parameters and complete physical ratings remain qualified.

Sources: `NYGRID_2025_AC_LOSS_REVISION.md`; `NYGRID_2025_PHYSICAL_REPAIR.md`; `NYGRID_2025_AC_SYSTEM.md`; `output/nygrid_2025_moses_repair/annual/moses_repair_v1/validation/annual_physics_review.json`.

## 7. Annual Validation and Downstate Performance

- The latest completed replay attempted and converged on all 8,651 source-qualified hours, with zero solver exceptions. Equation, input/loss-accounting and detailed-recovery checks pass for that cohort; all 109 other clock positions remain excluded.
- The targeted parent 185/195 voltage repairs retain zero violations over the full current qualified cohort. This is a local success, not whole-network feasibility.
- UPNY–ConEd has 235.207068 MW MAE and 7.844154% WAPE. SPR/DUN-SOUTH has 177.241927 MW MAE and 9.591505% WAPE. The current northern repair changed these by negligible amounts.
- The operating qualification remains failed: zero hours pass every operating limit. The current annual readback has 8,651 overvoltage hours, 599 undervoltage hours, 8,651 Q-violation hours, 8,651 assumed-S-violation hours and 4,793 branch-MVA-violation hours. These categories overlap and must not be summed.

Sources: `output/nygrid_2025_moses_repair/annual/moses_repair_v1/annual_receipt.json`; `validation/annual_input_accounting_review.json`; `validation/annual_physics_review.json`; `comparison/public_interface_metrics.csv`.

## 8. Where the Largest Interface Errors Occur

- Every score here is the current annual candidate, on the same 8,651 hours, using `legacy_signed_literal_from` and public MW. These are diagnostic comparisons to P32; physical meter equivalence remains uncertified.
- Total East is largest by absolute error; West Central is largest by WAPE. The rankings differ because WAPE divides accumulated absolute error by accumulated absolute observed flow.
- WAPE is not an average of hourly percentage errors. A small WAPE for a high-flow interface can coexist with a substantial MW error.

| Interface | MAE public MW | WAPE % | MAE rank | WAPE rank |
|---|---:|---:|---:|---:|
| Total East | 499.304073 | 15.949299 | 1 | 4 |
| Dysinger East | 249.433183 | 29.741813 | 2 | 2 |
| West Central | 247.052572 | 44.362102 | 3 | 1 |
| UPNY ConEd | 235.207068 | 7.844154 | 4 | 7 |
| Central East - VC | 208.719124 | 12.544670 | 5 | 5 |
| SPR/DUN-SOUTH | 177.241927 | 9.591505 | 6 | 6 |
| Moses South | 108.944975 | 20.178427 | 7 | 3 |

Sources: `output/nygrid_2025_moses_repair/annual/moses_repair_v1/comparison/public_interface_metrics.csv`; `scoring_receipt.json`; deck `data/errors_mae.csv` and `data/errors_wape.csv`. Full-precision source rows remain in the CSVs.

## 9. Total East: Why the Latest Error Increased

- Define the factorial scenarios before interpreting the chart: **B** is the previous physical-repair baseline; **G** applies the corrected St. Lawrence hydro allocation, dated unit admission and capability bounds; **P** applies PV20 routing with the opposite ISO-NE pool adjustment; **GP** is the released combined Moses repair.
- G and P are two additional completed annual ablations, compared on the same 8,651 hours as the saved B and GP cases. Their purpose is controlled attribution inside this model.

| Same-cohort MAE, public MW | B: previous | G: hydro only | P: PV20 only | GP: both |
|---|---:|---:|---:|---:|
| Total East | 471.551177 | 465.320064 | 507.402104 | 499.304073 |
| Moses South | 118.820924 | 141.586389 | 123.014514 | 108.944975 |

- The Total East order-averaged MAE effects are +34.917468 MW from PV20 and -7.164572 MW from hydro, adding to the +27.752896 MW regression. The interaction is already allocated between those two effects; do not add it again.
- PV20 lowers the predicted main eastbound flow, deepening prior Total East underprediction. A repair can improve source consistency or another interface while worsening this score.
- The five-parent Total East proxy is not certified as the 29-entry physical NYISO definition. A one-term PV20 readout sensitivity cannot establish the whole operator, its terminal signs or telemetry expression.

Sources: `NYGRID_2025_POSTREPAIR_DIAGNOSIS.md`; `output/nygrid_2025_postrepair_diagnosis/ablations/scenario_recipe.json`; `factorial_metrics.csv`; `factorial_attribution.csv`; `boundary/readout_sensitivity_metrics.csv`.

## 10. Moses South: Remaining Generation Issues

- The chart compares combined energy for the same six matched Zone D wind plants. Final EIA annual energy is 1,425,010 MWh; modeled energy in the 8,651 qualified hours alone is 1,662,733.250582 MWh. It does not claim every plant individually has excess energy.
- The excess is 237,723.250582 MWh. Under the current nonnegative wind-output bounds for all 109 excluded hours, at least 27.479280 MW of mean qualified-hour Zone D wind must be removed to meet the annual source total. This lower bound does not rely on an invented missing-hour shape.
- EIA net generation can be negative when station service exceeds gross generation. Thus nonnegativity is a model assumption, not an EIA accounting rule. Current Moses mean bias is +24.319610 MW, but comparing these numbers does not establish exact causal MAE attribution or an hourly correction.
- St. Lawrence now meets exact monthly EIA energy constraints, while hourly shape is reconstructed. The energy-preserving shape control is a conditional diagnostic, not a replacement annual model already validated and released.
- Sand Bar and Plattsburgh are distinct locations. Intervening South Hero net load, losses, bypass/parallel paths and exact P32 meter mapping remain unresolved. Do not assign their individual MW effects from one residual.

Sources: `output/nygrid_2025_postrepair_diagnosis/generation/D_wind_source_energy_review.json`; `D_wind_annual_EIA_comparison.csv`; `monthly_flat_frozen_terminal_scores.csv`; `generation/shape_ac/monthly_flat_AC_receipt.json`; `output/nygrid_2025_moses_repair/boundary/PV20_source_receipt.json`.

## 11. Western Interfaces: Source and Control Gaps

- The 44.362102% West Central and 29.741813% Dysinger East WAPEs are current AC results. Earlier western DC comparisons and correlation diagnostics remain historical evidence about the reconstruction mechanism, not new current-AC statistics.
- The earlier source audit matched all 108 Niagara/Lewiston/Gilboa monthly target quantities to final EIA. That supports those source quantities and arithmetic; it does not establish accurate hourly dispatch or hard satisfaction of every plant-month energy total after statewide reconciliation.
- NYISO documents Niagara230, Niagara115 East and Niagara115 West. The current aggregate main-plant landing does not supply a validated unit-by-unit hourly split across these physical terminals.
- The documented Dysinger–East Stolle Road PAR path and complete western physical-meter mapping remain gaps. The residual is not a uniquely diagnosed line-X error, and arbitrary injection or impedance adjustments would not resolve the source-identification problem.

Sources: `NYGRID_2025_WESTERN_SOURCE_AUDIT.md`; `output/nygrid_2025_western_audit/generation/EIA923_target_vintage_comparison.csv`; `generation/source_interpretation.json`; `mapping/physical_source_scope.json`; current `public_interface_metrics.csv`.

## 12. Next Modeling Priorities

- First correct the source-backed plant-energy inconsistency while preserving statewide generation totals and physical bounds. Keep reported monthly energy separate from inferred hourly shape.
- Complete the interface operators before treating agreement with their current proxies as a physical calibration objective.
- Then rerun and compare on a clearly declared common cohort; report equation qualification, operating feasibility and public-flow agreement separately.
- The latest wind/operator investigation has not been promoted into a new model. The completed delivered annual model remains `moses_repair_v1`; do not describe its diagnostic alternatives as released improvements.

Sources: `NYGRID_2025_POSTREPAIR_DIAGNOSIS.md`; `output/nygrid_2025_moses_repair/delivery/docs/START_HERE.md`; current annual `annual_receipt.json`.

## 13. Appendix: Counts, Units and Comparison Scope

- Each count refers to a named representation: the released 57-bus benchmark, the derived 140-bus structural counterpart, the 191-bus station-detail construction, or the 266/267-bus detailed AC network recovered from 148 retained voltages. Do not treat these as interchangeable networks.
- The current 1,466 generator rows comprise 1,437 native rows, 27 regional loss participants, fixed HQ and fixed PV20 boundary rows. Six transfer records mean four inherited transfers plus two Ontario PAR equivalents, not six physical HVDC assets.
- Public interface MW equals model MW divided by gamma once. Gamma is 0.30012075175285535. Currents stay in model amperes; no division by gamma is applied.
- MAE and WAPE use the displayed cohort. The paper's limit-normalized metric differs. The 2019 reference and current 2025 result use different years and modeling conditions and are not a controlled head-to-head test.

Sources: `NYGRID_RELEASED_2019_COMPARISON.md`; `NYGRID_2019_DLR_REBUILD.md`; `output/nygrid_2025_moses_repair/model/model_generator_register.csv`; `delivery/structure/current_structure_inventory.json`; current `comparison/scoring_receipt.json`.

## 14. Appendix: Public Generation Data and Assumptions

- P63 verifies statewide fuel totals, not individual plant dispatch. The Gold Book provides named resources and prior-year annual energy; the verified 2025 edition's annual generation refers to 2024.
- EIA-923 gives the matched plant-energy evidence used in these audits. It does not provide the hourly dispatch shape inferred by the model.
- AM means monthly values reported once annually and must not be conflated with the annual-only A category. The six-plant wind annual-energy result does not depend on this monthly-frequency distinction.
- P27 masked bid data are not named metered output; its Dispatch MW fields are bid-curve points. P34 and EIA-930 constrain reported devices/regions but do not certify every physical circuit-meter identity.
- Assumptions persist in bus-level load shares, plant hourly allocation, capability bounds, engineering parameters, reactive policy and boundary proxies. They should accompany every handoff.

Sources: `NYGRID_2025_POSTREPAIR_DIAGNOSIS.md`; `output/nygrid_2025_postrepair_diagnosis/generation/generation_data_availability.csv`; `generation_source_review.json`; `D_wind_source_energy_review.json`.

## 15. Appendix: Sources and Reproducibility

- `source_manifest.json` binds source filenames and hashes; the `data/` CSVs hold exact plotted values. `main.tex` is the editable slide source; this file supplies speaking notes and interpretation limits.
- Current headline values are fresh readbacks of completed saved runs, not new solves performed for this deck. The historical 2019 reproduction and intermediate DC/AC stages remain separately named and preserved.
- The completed annual receipt, independent raw-physics/accounting reviews and scoring crosscheck support current numerical claims. Source provenance and numerical consistency do not establish physical meter equivalence, historical unit telemetry or full operating feasibility.

Sources: deck `source_manifest.json`; `data/`; `output/nygrid_weekly_20261015/evidence/2025_metrics_evidence.json`; `content_review.json`; current annual `annual_receipt.json`, `validation/annual_physics_review.json`, `validation/annual_input_accounting_review.json`, `comparison/independent_scoring_crosscheck.json`.
