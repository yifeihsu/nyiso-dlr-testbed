# P34 qualifications and current DLR research readiness

The public-source P34 audit is complete. Ontario's 2025 flow direction is supported by an explicit effective-date note, and an older official diagram now corroborates Dover's direction. **Native P34 units, timestamp support and measured-versus-calculated origin remain unresolved.** The delivered DC model therefore retains its explicitly conditional posted-number convention; this audit does not change numerical inputs, line parameters, signs, controls or comparison results.

The current testbed is **ready for research on its declared DC topology and controls**. It is **not yet a runnable, coupled line-specific DLR experiment**. Its existing thermal kernels are reusable, but the current model still needs a physical-branch thermal adapter, matching weather, scale-aware current conversion and a declared thermal-state policy. A narrow F84 design-based DC DLR exposure study is the most direct next implementation. Full AC certification is not a prerequisite for a clearly labeled DC method study.

This assessment binds the [Dover loader](System%20Matpower%20Format/npcc_nygrid_2025_dover_dc.m) and its unchanged evidence at commit `797049c152073c0cdb800147ee2d11267d556cd6`: 148 retained buses, a 192-bus post-Dover reference, six fixed transfers and 8,651 qualified annual hours. The repository's older generic `LATEST_MODEL_CONFIGURATION.csv` points to a different 71-bus experiment; its thermal qualification does not transfer to this case.

## What the P34 source audit establishes

| Question | Finding | Allowed interpretation |
|---|---|---|
| Native unit | Fresh official CSV still says `Flow (MWH)` | Preserve the literal field and conditional numeric-as-MW convention; no automatic factor of 12 |
| Ontario direction, PTIDs 25118/25119 | Positive from St. Lawrence/IESO toward Moses/NYISO; explicit convention date December 3, 2024 | Direction supported for 2025 |
| Dover direction, PTIDs 625149/625150 | Positive from Long Mountain/ISONE toward Cricket Valley/NYISO in January and July 2026 diagrams | Documented direction corroborated; 2025 effective date remains qualified |
| Native timestamp support | Subhourly cadence is visible, but start/end/instantaneous/average semantics are unspecified | Existing forward hold is an explicit modeling policy |
| Measurement origin | Public product definition does not establish independent metered/SCADA flow or calculated RTD flow | Call it an operator-reported P34 flow value |
| P53A schedule units | Separate schedule-format document specifies hourly MW | Does not settle P34 units or transfer its sign convention |

The [primary evidence register](output/nygrid_2025_p34_qualification/sources/primary_evidence_register.csv) contains 13 source-backed findings. The audit archived the current OASIS UI, public report metadata, archive API response and a fresh December 19, 2025 CSV. The metadata has no P34 unit preamble or field definition. The [Market Participants User Guide](output/nygrid_2025_p34_qualification/sources/NYISO_MarketParticipants_UserGuide_Sep2026.pdf), section 5.5.4 (PDF page 90), describes hourly SCUC and time-weighted hourly RTD flows; that description does not resolve the subhourly file's unit or time support.

The recovered [January 9, 2026 diagram](output/nygrid_2025_p34_qualification/sources/NYISO_PARdiagram_version1_0.pdf) is a genuine older payload, verified by its cover, HTTP filename and SHA-256. Dover is on page 6; Ontario and its dated note are on page 7. The URL still contains `ParFlowDiagrams27.pdf`, while the returned older filename is `ParFlowDiagrams26.pdf`; filenames alone were not used to establish vintage. Public version 1.1 returned identical bytes, so it is not counted as an independent historical edition. The bounded older-version search did not retrieve a 2025 Dover-effective-date record.

Official links: [P34 archive index](https://mis.nyiso.com/public/P-34list.htm), [archived December 19 CSV](https://oasis-postings.prod.nysdi.com/PAR_FLOW/CSV/2025/12/19/ParFlows-20251219.csv), [older diagram request](https://www.nyiso.com/documents/20142/2268519/ParFlowDiagrams27.pdf/7bd78df8-311c-0b29-fa3f-ba0c8a51d123?version=1.0), [guide](https://www.nyiso.com/documents/20142/3625950/mpug.pdf).

## Numerical interpretation and use gate

The [qualification contract](output/nygrid_2025_p34_qualification/P34_qualification_contract.json) and [four-channel ledger](output/nygrid_2025_p34_qualification/P34_channel_qualifications.csv) separate documentary direction, historical applicability, unit assumptions, time policy and measurement origin. They retain `gamma = 0.30012075175285535`, applied once, and the existing complete-hour quality masks. Raw import-positive values are reoriented once when a modeled branch runs NY-to-external. They are not independently rescaled according to posting cadence.

The same contract preserves the 287 post-cutover Dover hours, including 18 ambiguous-zero hours assigned the explicit neutral-phase assumption and 49 hours at the declared model-angle bound in the nominal-impedance case. Zero bank postings do not identify a bypass state or establish zero total intertie flow. Similar bank values do not prove either independent sensors or a duplicated sensor. Older artifact fields containing the word `observed` do not certify the product as measured physical telemetry.

The numerical audit evaluates unit hypotheses as diagnostics and keeps regional interchange separate from individual PAR flows. IESO's regional NEW-YORK total and EIA's balancing-area interchange are broader quantities; subtracting a PAR pair leaves unobserved parallel-path flows. Such residuals cannot identify a bank unit multiplier or direction without additional physical-path evidence. Rating plausibility also cannot establish a unit definition. No internal P32 interface errors are used to choose units, signs or parameters.

The [numeric audit](output/nygrid_2025_p34_qualification/numeric_audit/numeric_audit_receipt.json) covers four declared unit/time interpretations and two sign diagnostics. Its plan precedes the new alternative calculations, while acknowledging that prior audits had already exposed the raw maxima. The [per-bank plausibility table](output/nygrid_2025_p34_qualification/numeric_audit/unit_scale_plausibility.csv) shows the consequence of treating each posting as five-minute interval energy:

| Bank | Maximum absolute posted number, native unit unresolved | Implied MW under x12 hypothesis | Nominal MVA reference |
|---|---:|---:|---:|
| St. Lawrence PS33 | 245.8 | 2,949.6 | 300 |
| St. Lawrence PS34 | 252.6 | 3,031.2 | 300 |
| Dover T398-A and T398-B, each | 323.4 | 3,880.8 | 750 |

These are strong conflicts with the nominal rating if the resulting quantity represents physical active power; they are not measured-overload findings or a proof that x1 is the correct interpretation. Power samples and one-hour energy quantities can also have the same numerical scale. Irregular and off-grid native postings prevent treating all rows as distinct, nonoverlapping five-minute energy intervals without a product definition.

Timing uncertainty is material even at x1. For each Dover bank over the same 287 post-cutover hours, replacing the held hourly mean with the last posting inside the hour changes values by about 15.73 posted units on average, reaching 133.19; using the posting at the hour boundary changes them by about 18.30 on average, reaching 186.99. The [aggregation sensitivity ledger](output/nygrid_2025_p34_qualification/numeric_audit/hourly_aggregation_sensitivity.csv) reports these diagnostic differences without selecting a time convention by model error.

Inspect conditional use, or request a stronger evidence check:

```powershell
python scripts/nygrid_2025_p34_qualification/qualification.py --use conditional_dc
python scripts/nygrid_2025_p34_qualification/qualification.py --use historically_verified_sign --ptid 25118 --ptid 25119
python scripts/nygrid_2025_p34_qualification/qualification.py --use verified_native_MW
```

The first two commands succeed. The last intentionally exits 2 and explains the missing evidence. Measured-telemetry and physical-thermal requests also fail closed. This is an evidence inspector, not a replacement loader or a hidden numeric conversion. Confirming the unresolved semantics requires a native P34 format/provenance specification and a Dover sign-effective-date record covering December 2025. No numerical correction was established that would justify replacing the sealed annual replay.

## Which DLR research claims are ready

| Research task | Current status | What is needed |
|---|---|---|
| DC topology and control sensitivity | Ready now within declared assumptions | Use the dated loader and explicit source-quality masks |
| Synthetic time-varying rating or congestion screening | Electrical platform ready; adapter absent | Recover physical-line MW and apply declared limits |
| F84 design-based DC thermal exposure | Best next experiment; not yet integrated | ACSS thermal record, weather binding, gamma/current conversion and thermal integration |
| Dover overhead-section sensitivity | Line estimates available; thermal adapter absent | Model NY twin-Mallard and CT single-Bluebird sections separately; keep PAR limits separate |
| Historical weather-driven asset DLR | Not ready | Route/critical-span weather, asset limits and qualified state initialization; field data for measured-performance claims |
| DLR redispatch or curtailment benefits | Not integrated | Physical-flow inequalities and a declared constrained-dispatch/controller policy |
| AC electrothermal feasibility | Not ready | Qualified AC network, reactive capability and physical series-current reconstruction |
| N-1 secure transfer or operational system capacity | Not ready | Physical contingency models, equipment ceilings and validation appropriate to those claims |

The [capability matrix](output/nygrid_2025_dlr_readiness/capability_matrix.csv), [687-row branch ledger](output/nygrid_2025_dlr_readiness/branch_readiness.csv) and [ten concrete integration gaps](output/nygrid_2025_dlr_readiness/code_and_data_gaps.csv) make the scope inspectable. The branch ledger covers the nominal **post-Dover** 274-row retained and 413-row reference representations, with branch 211 disabled under the existing controlled-transfer substitution. Earlier dated topologies remain distinct.

At the inspected post-Dover runtime state, 242 of 264 active retained branches have `RATE_A = 0`, meaning the current data do not supply their thermal rating. The legacy branch register declares no thermally qualified rows. There are 30 nonphysical Schur connections and 92 active voltage-changing connections. None should receive an overhead-conductor DLR rating merely because it appears in the branch matrix. Cables, PAR banks and transformers need their own equipment models and ceilings.

F84 is directly retained as slim row 244 / full row 391 and has a source-backed conductor design basis. It is the most defensible starting point, while installed critical-span limits and weather remain assumptions or missing inputs. Dover line rows 393 and 413 can support a later section-based study; PAR rows 411/412 are separate equipment. The heterogeneous 398 path must use the limiting section, not an averaged conductor.

## Integration requirements that affect scientific validity

1. **Preserve the electrical contract.** The older `solve_dlr_steady_operating_point.m` calls a `plain()` helper that removes `dcline` and control callbacks. Direct reuse would discard this case's six fixed transfers. A new adapter must preserve them and the declared bounded PAR policy.
2. **Recover physical branches first.** Apply the saved recovery matrices and phase offsets to eliminated physical lines. A Schur-equivalent edge is not a conductor and its outage is not a physical-line outage.
3. **Use the correct power/current scale.** For an explicitly declared nominal-voltage, unity-power-factor DC proxy:

   `I_sub[A] = 1000 * abs(P_model[MW]) / (gamma * sqrt(3) * Vnom[kV] * n_circuits * n_bundle)`

   The branch must actually represent those equal-sharing circuits; a single physical circuit uses `n_circuits = 1`. Reverse-convert its limit to model MW exactly once. Forgetting gamma gives only 30.012% of the intended current and 9.007% of its resistive heating. F84's 2,214 A design phase-current reference corresponds to 1,107 A per subconductor, not 2,214 A per subconductor. Modeled P/gamma at nominal V is a current proxy, not measured current or a guaranteed lower bound on actual current. Reactive power, actual voltage and charging matter for AC terminal/series current.
4. **Use a matching thermal model.** The existing runtime catalog contains ACSR surrogates; the new projects use ACSS Mallard/Bluebird. A versioned adapter must carry per-subconductor diameter, mass and catalog AC resistance versus temperature, with declared heat capacity, surface properties and mechanical temperature limits. The old assumed resistance-temperature law cannot silently replace the new catalog interpolation.
5. **Bind weather and state to the same physical hours.** Route segments need wind speed/direction, temperature and solar inputs, plus initialization and missing-data policies. Do not bridge the 109 excluded annual hours with invented weather or thermal state.
6. **Match the claim to the experiment.** Fixed-dispatch rating comparisons measure exposure. Mitigation or transfer-benefit claims require a constrained redispatch formulation. AC, N-1, ramps and storage-energy validation are required when making those particular claims; they are not universal prerequisites for every DC sensitivity experiment.

## Validation and reproducibility

The new qualification guard passes seven focused tests covering conditional use, device-specific sign dates, refusal of unit/measurement promotion, thermal claim boundaries, unknown devices, stale evidence and unreviewed sign/scale changes. The [validation receipt](output/nygrid_2025_p34_qualification/qualification_validation.json) binds the tested contract and code.

Fresh MATLAB checks pass **25 reusable-component tests**, including a 21-case independent NREL fixture comparison, thermal equilibrium and transients, bundle heating, series versus terminal current, and physical exclusion/constraint checks. These establish reusable components; they do not claim that the current 148-bus DLR workflow has been run. The previous 49 full plus 49 slim DC solves are separately preserved historical evidence for this delivered electrical model. See the [fresh component receipt](output/nygrid_2025_dlr_readiness/fresh_reusable_component_audit.json) and [readiness assessment](output/nygrid_2025_dlr_readiness/readiness_assessment.json).

Read-only verification:

```powershell
python scripts/nygrid_2025_p34_qualification/build_primary_evidence.py --verify
python scripts/nygrid_2025_dlr_readiness/audit_readiness.py --verify
python scripts/nygrid_2025_p34_qualification/finalize_qualification.py --verify
```

Adding `--require-physical-dlr` to the readiness command intentionally exits 2. The [delivery manifest](output/nygrid_2025_p34_qualification/DELIVERY_MANIFEST.json) binds the new evidence, code and this report. Earlier source inputs, fitted parameters, model files and replay artifacts remain unchanged.
