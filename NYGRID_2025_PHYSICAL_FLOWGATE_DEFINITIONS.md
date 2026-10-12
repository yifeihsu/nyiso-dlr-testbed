# 2025 NYISO physical flowgate definitions

The source definitions have been reconstructed for all seven interfaces from the official Winter 2024-25, Summer 2025 and Winter 2025-26 operating-study appendices. The deliverable contains **269 printed entries in 21 seasonal definitions**, with circuit identifiers, terminal names, voltage levels, metered-end asterisks, PDF pages and source hashes.

**Numerical calibration of the current model remains unestablished.** The available network does not have a verified, complete physical mapping for any of the seven gates. No interface observations were used to choose members, signs, weights, aliases or parameters. No new numerical operator, annual replay or improved error claim is being promoted from this audit.

## Use the reconstructed definitions

- [All seasonal members](output/nygrid_2025_flowgate_definitions/definitions/all_seasonal_members.csv) is the complete flat register. A row is a printed source entry, not necessarily a unique physical circuit.
- [Physical definition registry](output/nygrid_2025_flowgate_definitions/definitions/physical_flowgate_registry.json) preserves each edition independently and includes terminal conventions and qualification fields.
- [Definition summary](output/nygrid_2025_flowgate_definitions/definitions/definition_summary.csv) reports membership and documentary gaps for each gate/edition.
- [Term-by-term model audit](output/nygrid_2025_flowgate_definitions/local_model/candidates/physical_term_model_identifiability.csv) identifies missing stations, historical candidates, voltage mismatches and unverified circuit identities.
- [Model binding template](output/nygrid_2025_flowgate_definitions/definitions/model_binding_template.csv) lists the evidence still needed for each source entry. Blank mappings are intentional; they do not mean zero flow.

The sources are historical study documents, retrieved and inspected in this audit. Their posting dates are not verified real-time effective dates. The registry therefore requires an explicit study edition; it does not assign one definition to every 2025 hour.

## What the seven definitions establish

| Interface | Winter 2024-25 entries | Summer 2025 entries | Winter 2025-26 entries | Material finding |
|---|---:|---:|---:|---|
| Dysinger East | 10 | 10 | 10 | DH1/DH2 are Dysinger-Henrietta. Circuit 111 is labelled Telegraph in the early table and Sweden 1 in the later tables. The A-C ties are retained. |
| West Central | 16 | 14 | 14 | Early and later tables differ in Mortimer paths, Hook Road transformers and circuit identifiers. Early source ambiguities cannot be silently repaired. |
| Total East | 29 | 29 | 29 | Includes lower-voltage ties and transformers as well as the large transmission paths. Inghams device ports and an early Closter/Cresskill naming change need resolution. |
| Moses South | 7 | 7 | 7 | Winter 2025-26 HA1/HA2 at Haverstock 345 kV replace MA1/MA2 at Moses 230 kV, including a changed metering location. |
| Central East | 8 | 8 | 8 | Includes Edic-Princetown 351/352, Inghams PAR/R81 and PV20. Early Inghams identifiers and asterisks differ from the later tables. |
| UPNY-ConEd | 10 | 10 | 10 | Lovett is present; later Buchanan North/South labels and East Fishkill transformer metered-side wording differ from the early table. |
| Sprain Brook-Dunwoodie South | 11 | 11 | 11 | The inspected membership is unchanged across the three editions. It includes two Long Island-NYC ties; X28 is 345 kV and metered at Tremont. |

Counts refer to literal entries. In particular, the early West Central list is not certified to contain 16 distinct circuits.

### Dysinger East and West Central

The summer Dysinger list contains DH1/DH2, six Lockport 115-kV entries, Stolle Road-High Sheldon 67 and Andover-Palmiter 157-932. Reusing the older Somerset/Rochester and Niagara/Rochester identities would lose the source-confirmed 2025 terminal definitions. All three inspected study editions already contain DH1/DH2; this audit does not assign their commissioning to a particular 2025 date.

The early West Central source contains both Quaker-Macedon 930 and Quaker Road-Macedon 930. They remain separate source rows with a possible-duplicate flag. Farmington #4 is named 12/115 kV while its voltage column says 34.5/115 kV. The later tables contain a compound Mortimer-Hook Road-Elbridge 1/7 entry and four unstarred transformer entries. The registry preserves these facts and does not choose a missing winding or collapse the compound path to one arbitrary line.

The current accounting model puts the Stolle Road aggregate in Zone B, while the historical physical source inventory has the Stolle buses in Zone A. The current accounting-zone cut does not by itself prove the official A-B plus A-C membership. A conservation-based aggregate equivalent could be valid, but it needs a source-backed proof of the complete cut and enclosed injections.

### Moses South

Early winter and summer use Moses-Adirondack MA1/MA2 at 230 kV, with the asterisk at Moses. Winter 2025-26 uses Haverstock-Adirondack HA1/HA2 at 345 kV, metered at Haverstock. The other five entries agree. Page 9 of the [winter main study](output/nygrid_2025_flowgate_definitions/sources/central_north/NYISO_Winter2025_2026_OperatingStudy_APPROVED.pdf) connects the definition change to Smart Path Connect.

This is a physical terminal/voltage/meter change. The study editions do not establish the operational cutover hour. Applying either version to the entire year would require evidence beyond these tables.

### Central East and Total East

The eight Central East entries include Edic-Gordon Road 14, Marcy-New Scotland 18, East Springfield-Inghams 7-942, Inghams PAR, Inghams Bus Tie R81, Edic-Princetown 351/352 and Plattsburgh-Sand Bar PV20. Early winter lists Inghams PAR* as PAR 2 and Inghams Bus Tie*; the later tables use unstarred PAR and R81. A single-station device name does not identify its physical ports.

The published P32 label used in previous comparisons is `CENTRAL EAST - VC`. NYISO expands VC as Voltage Collapse in the December 2023 Dynamic Reserves presentation. The examined documents do not independently certify the complete P32 measurement expression or a separate correction term. Appendix H distribution factors describe transfer/outage sensitivities; they are not flowgate membership weights. The [source qualifications](output/nygrid_2025_flowgate_definitions/definitions/central_north_2025_qualifiers.json) retain this distinction and the relevant primary references.

Total East has 29 entries, including lower-voltage PJM/RECo ties. The 2025 tables identify Marion-Farragut C3403 and the 138-kV metered side of South Mahwah BK258. Winter 2024-25 calls circuit 751 Closter-Sparkill; the later editions call it Cresskill-Sparkill. That naming bridge is unresolved. Inghams PAR/R81 are starred in the later Total East tables even though they are unstarred in Central East; no missing terminal pair was invented.

Summer Appendix B models B3402/C3403 out of service, while Appendix E retains them as Total East members. A study-base status is not an instruction to delete a definition entry or assume zero flow for all 2025. Likewise, the study's statement about Neptune and Total East limits is not sufficient to alter an independently unspecified P32 telemetry formula.

### UPNY-ConEd and Sprain Brook-Dunwoodie South

The [October 2024 UPNY voltage-limit report](output/nygrid_2025_flowgate_definitions/sources/downstate/UPNY_ConEd_VCAP_2024_OC_approved.pdf) explains that the new Lovett 345-kV station bisects Y88. Lovett is therefore not silently aliased to historical Ladentown. Later seasonal tables identify Buchanan South for Y88 and Buchanan North for Y94; the early table says Buchanan without those suffixes.

The early UPNY table names East Fishkill `345/115*` for BK1/BK2, while its voltage column lists 115/345. The later tables name `115/345*`. The literal starred side moves from 115 to 345 in the documents. The register preserves the name order and the voltage column separately; it does not infer when a real meter changed or whether the early wording was an editorial issue.

Sprain-Dunwoodie contains eleven entries in each edition, including Lake Success-Jamaica 903 and Valley Stream-Jamaica 901L_M. Sprain Brook-Tremont X28 is a 345-kV member metered at Tremont. Historical Tremont 138-kV branches cannot establish that circuit identity merely because the station names are similar.

## Metering and numerical use

The source asterisk identifies the metered end. In the registry's local terminal convention, `PF` and `PT` both mean active power entering an asset at its respective terminal. Flow from the first printed terminal toward the second, measured at the first terminal, is `+PF`; measured at the second, it is `-PT`. These local expressions are not certified coefficients for a P32 gate.

For AC results, sending-end and receiving-end readings differ by active loss. Under a verified lossless DC representation, `PF = -PT`; that identity does not prove which physical circuits belong to a gate. Unknown ports, compound terms, source contradictions and possible duplicate entries are left unresolved.

Source-table order, model branch orientation, telemetry sign and public-channel expression are separate bindings. An operator may be promoted only after complete physical mapping or an equivalent aggregate proof, port/sign binding and the appropriate operational interval have been established. No such whole-gate certificate was found for the current model.

## Model audit and validation

The [model-candidate receipt](output/nygrid_2025_flowgate_definitions/local_model/candidates/model_term_candidate_receipt.json) covers all 269 entries and 21 definitions. There are 24 entries with embedded historical candidates: five UPNY and three Sprain-Dunwoodie entries in each edition. None has a certified 2025 physical mapping. Across all entries, 169 have unresolved stations/new terminals, 42 have historical candidates that are not embedded, 28 have no direct historical circuit candidate, and six have voltage mismatches. These are search outcomes, not proof that an electrical aggregate representation is impossible.

The [source lineage audit](output/nygrid_2025_flowgate_definitions/local_model/source_crosswalk_receipt.json) traced 97 historical PERFORM branches in the 191-bus model: 14 survive directly in the 148-bus case and 83 can be recovered by the existing affine reduction. It also distinguishes the 225 original retained NPCC branch records from physical circuit identities. Exact mathematical recovery of historical branches does not supply missing 2025 equipment identity.

Validation includes 269 literal source-row checks and visual review of every relevant table page. The current model audit passed 240 historical candidate/state checks and 35 legacy interface/state checks, with maximum legacy-operator difference below `7.3e-12 MW/rad`. The independent lineage review also checked all five topology variants and all 26 ambiguous parallel bundles. Parallel-bundle sums are numerically invariant to within-bundle circuit permutations; this does not certify their 2025 gate membership.

The [independent registry review](output/nygrid_2025_flowgate_definitions/validation/registry_independent_review.json) checks the literal fields, metered ports, date distinctions and refusal of unsupported model operators. The [registry guard checks](output/nygrid_2025_flowgate_definitions/validation/registry_guard_tests.json) cover missing/duplicate terms, mismatched scope, changed hashes and invalid edition requests.

The existing cases, dispatch, external transfers, fitted inputs and prior comparison artifacts are preserved. The previous comparison errors still describe the existing aggregate operators. This source reconstruction does not turn those errors into validated physical-flowgate errors.

## Reproduce and inspect

From PowerShell:

```powershell
cd "C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems"
$fgPython = 'C:/Users/Holiday/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
& $fgPython scripts/nygrid_2025_flowgate_definitions/build_central_north_definitions.py --verify
python scripts/nygrid_2025_flowgate_definitions/build_registry.py
python scripts/nygrid_2025_flowgate_definitions/inspect_definition.py --gate moses_south --edition winter2025_26
python scripts/nygrid_2025_flowgate_definitions/inspect_definition.py --gate moses_south --edition winter2025_26 --require-model-operator
```

The last command is expected to refuse numerical promotion with an explanation. The inspector verifies the registry/source hashes and requires one of the three explicit study editions. The source builders and validation receipts are saved in the new `nygrid_2025_flowgate_definitions` namespace; the [registry receipt](output/nygrid_2025_flowgate_definitions/definitions/registry_receipt.json) identifies the exact inputs and outputs.

`python scripts/nygrid_2025_flowgate_definitions/finalize_definitions.py --verify` checks the packaged file hashes, linked proof receipts, unchanged source/model dependencies and report links against the [delivery manifest](output/nygrid_2025_flowgate_definitions/DELIVERY_MANIFEST.json).

## Evidence needed to finish numerical calibration

A detailed 2025 PSS/E, PowerWorld or equivalent case with utility circuit identifiers and station sections would support the physical-to-model crosswalk. The EMS/OASIS flowgate or monitor file should specify the metered terminals, signs, compound-device expressions and the exact `CENTRAL EAST - VC` expression. Versioned change records should give the effective times of the Moses/Smart Path Connect transition and the other seasonal discrepancies. A source-backed aggregate cut certificate can substitute for individual circuit mappings where it proves the same measurement.

Until those bindings are supplied, changing branch coefficients or assigning zeros to absent terms would be an assumption rather than a confirmed correction. The reconstructed definitions and complete gap ledger are usable now; the current model is not newly certified against the physical 2025 flowgates.

## Primary seasonal documents

- [Winter 2024-25 appendices](output/nygrid_2025_flowgate_definitions/sources/central_north/NYISO_Winter2024_2025_Appendices_APPROVED.pdf): posted October 24, 2024; PDF pages 35-38 and 41, printed pages 62-65 and 68. [NYISO source](https://www.nyiso.com/documents/20142/3691300/Winter2024-25-Operating-Study-Appendices-APPROVED.pdf/241b1b08-07b7-620a-3db5-7971deeb090f).
- [Summer 2025 appendices, CE changes](output/nygrid_2025_flowgate_definitions/sources/western/NYISO_Summer2025_Appendices_CE_Changes_APPROVED.pdf): posted June 20, 2025; PDF/printed pages 36-39 and 42. [NYISO source](https://www.nyiso.com/documents/20142/3691300/Summer2025-Operating-Study-Appendices-CE-Changes-APPROVED.pdf/c2ba37b6-d7f3-5731-b1d1-84258bea3456).
- [Winter 2025-26 appendices](output/nygrid_2025_flowgate_definitions/sources/central_north/NYISO_Winter2025_2026_Appendices.pdf): posted October 17, 2025; PDF/printed pages 35-38 and 41. [NYISO source](https://www.nyiso.com/documents/20142/3691300/Winter2025-2026-Operating-Study-Appendices.pdf/3c61e4df-5eb5-5786-44fd-1e24cbdf9926).

Each download has an adjacent source receipt. Source publication, literal transcription, historical electrical recovery, physical circuit identity, P32 measurement binding and hourly validity are recorded as separate evidence requirements.
