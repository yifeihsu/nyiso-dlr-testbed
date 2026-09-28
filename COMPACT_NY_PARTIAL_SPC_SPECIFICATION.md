# Small partial Smart Path Connect overlay: implementation specification

Version: 2026-09-08, fixed before the new electrical campaign. This specification describes the separate implemented helper `System Matpower Format/NY_Lite/apply_compact_2025_partial_spc.m`. The original infrastructure helper, 66-bus reference, dispatch inputs and historical artifacts are preserved. It is a **71-New-York-bus research alternative**, with all 46 original NPCC New York buses retained. It is not a reconstruction of the exact network in operation at each selected 2025 hour.

The helper has passed 16 focused test groups in `test_compact_2025_partial_spc.m`. Test artifacts are `tmp/infrastructure_status_audit/partial_spc_implementation_tests.mat` and `.csv`. These establish topology/accounting/base-conversion properties, not AC operating feasibility. The main campaign owns bounded AC/PF qualification and sensitivity results; no parameter was chosen from interface-flow residuals.

## API and expected size

```matlab
modern_build = apply_compact_2025_generation(apply_compact_2025_infrastructure());
variant = apply_compact_2025_partial_spc(modern_build, options);
```

The input is the nominal generation-applied modern construction: 160 full buses, 66 New York buses, 290 full branch records and 64 generator records. `candidate` and `full_candidate` must agree. Sensitivities are applied only by this new helper; a pre-scaled old infrastructure parent is rejected.

Options are `impedance_scale` in [0.75, 1.25], `charging_scale` in [0, 1.5], and `rating_scale` in [0.8, 1.2], each defaulting to 1. Unknown options, nonfinite values and reapplication are rejected. These options change the nine new line/transformer assumptions. The relocated inherited regional equivalent retains its complete original parameter budget.

The output has **165 full / 71 New York buses**, **300 full / 135 New York branch records**, and **117 active New York branches**. Generator count, identities, capability bounds, costs and all parent PD/QD/GS/BS are unchanged. Five new station buses are zero-injection PQ buses. No new generator, external exchange, shunt or reactive-support device is introduced.

## Commissioning facts and their limits

The evidence register is `output/compact_ny_2025/sources/infrastructure_cutoff_status_audit.csv`; URLs and available source-byte hashes are in `infrastructure_status_source_manifest.csv`. The new helper reads both as strings so mixed day/month precision and voltages such as `345/230` cannot silently become missing values. It checks the expected source keys, dates, pre-cutoff status and voltage evidence for each included named component.

| Component | Owner-reported energization | Nominal voltage / source |
|---|---|---|
| MH2, Moses–Haverstock 2 | 2025-10-08 | 230 kV, owner notice plus NYISO October report. [Notice](https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BE031C999-0000-C531-A4C4-16D562D34460%7D) |
| MH3, Moses–Haverstock 3 | 2025-10-26 | 230 kV, owner notice plus NYISO October report. [Notice](https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B8034269A-0000-C526-9C99-74AC5F0E7BDF%7D) |
| HA2, Haverstock–Adirondack 2 | 2025-10-13 | 345 kV, owner notice plus contemporaneous NYISO facility designation. [Notice](https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B7068E499-0000-C447-80CF-7A033EE81A59%7D) |
| HW2, Haverstock–Willis 2 | 2025-10-02 | 345 kV, owner notice plus NYISO October report. [Notice](https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B8094B999-0000-C718-99E2-5B687BD30A50%7D) |
| Austin Road–Edic Line 11 | 2025-10-08 | 345 kV explicitly in owner notice. [Notice](https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B804FE499-0000-C12E-8CA7-F547F681A4FA%7D) |
| Adirondack–Austin Road Line 13 | 2025-11-17 | 345 kV explicitly in owner notice. [Notice](https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B50BC9D9A-0000-CA11-81D7-A2EA72DF9164%7D) |
| Haverstock AT2/AT3 and WillisAnnex TR2 | 2025-10, month precision | 345/230 kV in the [NYISO October operations report](https://www.nysrc.org/wp-content/uploads/2025/11/7.3.2-Operations_Report_202510_v1-long-form-Attachment-7.3.2.pdf). |

HA1 was energized March 27, 2026 and Adirondack–Marcy Line 12 on March 28, 2026. Neither is included. [HA1 notice](https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B101D3F9D-0000-CA6E-AF99-F8341FEECB4B%7D), [Line 12 notice](https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B30EE449D-0000-C554-9B1F-EEA1FBA5E0FB%7D).

An energization notice is not proof of continuous availability. The [November 7, 2025 TTC report](https://mis.nyiso.com/public/pdf/ttcf/20251107ttcf.pdf) identifies HA2 as 345 kV but still lists a scheduled outage through November 15. The proposed study therefore uses a declared fixed year-end topology, with the selected equipment available, as a counterfactual stress model for earlier dispatch hours. It does not claim their actual hourly outage states.

Lengths, nominal currents and conductor descriptions come from **planning entries**, not commissioned-asset measurements, in the [2025 NYISO Gold Book, Table VII](https://www.nyiso.com/documents/20142/2226333/2025-Gold-Book-Public.pdf/088438e1-02f1-5316-211b-dbca17c01b4b). Actual energization notices override its forecast dates. NYISO zone assignments for the new model station sections have not been independently established; the D/E allocations below are explicit compact-model assumptions, not geographic proof of an official interface definition.

## Bus changes

| Model bus | Role | kV | Model zone | Action |
|---|---|---:|---|---|
| 48 | Existing MOSES E | 230 | D | Retain hardware, generation and boundary landing. It represents the compact Moses connection. |
| 43 | Existing EDIC | 345 | E | Retain; endpoint of new Line 11. |
| 49 | Existing PLATTSBURGH | 115 | D | Retain; **not** relabeled Willis, Ryan or Patnode. |
| 44 / 45 | Existing PORTER sections | 230 / 115 | E | Retain with original support connections. |
| 1220 | ADIRONDACK 345 SPC PROXY | 345 | E | Replace only the old added zero-injection 230-kV proxy's role. |
| 9120 | HAVERSTOCK 230 SPC PROXY | 230 | D | New PQ station section; initial phasor from bus48. |
| 9121 | HAVERSTOCK 345 SPC PROXY | 345 | D | New PQ station section; initial phasor from bus48. |
| 9122 | AUSTIN ROAD 345 SPC PROXY | 345 | E | New PQ station section; initial phasor from bus43. |
| 9123 | WILLIS ANNEX 345 SPC PROXY | 345 | D | New PQ station section; initial phasor from bus48. |
| 9124 | WILLIS ANNEX 230 SPC PROXY | 230 | D | New PQ station section; initial phasor from bus48. |

Reusing ID1220 is a model bookkeeping choice. It is **not** a claim that a 2019 physical 230-kV bus and a newly commissioned 345-kV station are the same device. Its exact before/after row, name, zone and role are saved in `partial_spc_bus_role_change`. The live `bus_map_2025` row is corrected to 345 kV and its old source-voltage identity cleared; the original map is retained as `partial_spc_parent_bus_map_2025`. All original NPCC bus voltages remain unchanged.

Five new station sections, with reuse of the already-added Adirondack proxy, give 71 New York buses. Haverstock and Willis each need two voltage sections to avoid implicit 345/230-kV jumps. Austin Road remains an explicit intermediate station separating the two independently identified southern lines. No explicit Ryan/Patnode/local load detail is needed for the selected aggregate scope. This is the smallest version adopted here that retains those named circuit endpoints and voltage transitions; a more aggressively reduced network could merge stations but would discard that electrical asset identity.

## Retirements and additions

The following five **stable keys**, resolved and checked against endpoints/hardware, change status from 1 to 0. Rows and original numeric values remain in the branch matrix; only status changes. Exact predecessor matrices and historical endpoint voltages are also archived. Inactive old rows touching1220 retain their historical 230-kV interpretation in the archive, even though the current model ID now represents345 kV.

| Retired key | Historical endpoints | Reason |
|---|---|---|
| `NY2025:SMART_PATH:1` | 1220–48, 230/230 kV | Whole functional replacement of historical Moses leg. |
| `NY2025:SMART_PATH:2` | 1220–48, 230/230 kV | Same replacement group; not individually identified with HA1/HA2. |
| `NY2025:SMART_PATH:3` | 1220–44, 230/230 kV | Whole functional replacement of historical Porter leg. |
| `NY2025:SMART_PATH:4` | 1220–44, 230/230 kV | Same replacement group; not individually identified with Lines11/12/13. |
| `NPCC_S7:BRANCH_ROW:220` | 49–48, 115/230 kV | Relocate the old northern regional-equivalent function through the new Willis path once. |

`NPCC_S7:BRANCH_ROW:47`, the original 44–48 super-corridor already retired by the frozen overlay, stays off. No uncertain residual fraction of any predecessor is fitted or left in parallel. Whole functional retirement is an explicit **aggregation assumption**, not a proved five-device physical retirement crosswalk. In particular, unverified transitional 230-kV parallel routes are not recreated.

New keys have prefix `NY2025_SPC:`:

| Suffix | From → to | kV | Type | Planning length, miles | Circuit / bundle count |
|---|---|---|---|---:|---|
| MH2 | 48 → 9120 | 230 / 230 | Overhead surrogate | 2.0 | 1 / 1 |
| MH3 | 48 → 9120 | 230 / 230 | Overhead surrogate | 2.0 | 1 / 1 |
| HA2 | 9121 → 1220 | 345 / 345 | Overhead surrogate | 83.7 | 1 / 2 |
| HW2 | 9121 → 9123 | 345 / 345 | Overhead surrogate | 35.0 | 1 / 2 |
| LINE11 | 9122 → 43 | 345 / 345 | Overhead surrogate | 42.5 | 1 / 2 |
| LINE13 | 1220 → 9122 | 345 / 345 | Overhead surrogate | 11.6 | 1 / 2 |
| AT2 | 9120 → 9121 | 230 / 345 | Assumed transformer | — | One unit |
| AT3 | 9120 → 9121 | 230 / 345 | Assumed transformer | — | One unit |
| TR2 | 9123 → 9124 | 345 / 230 | Assumed transformer | — | One unit |
| PLATTS_REGIONAL_EQ | 49 → 9124 | 115 / 230 | Relocated inherited regional equivalent | Unknown | Nonthermal aggregate |

The new core path is Moses–Haverstock–HA2–Adirondack–Line13–Austin Road–Line11–Edic. The northern branch is Haverstock–HW2–WillisAnnex–Plattsburgh regional equivalent. W1/WRY1/WPN1/WPN2 energization evidence motivates the local network's aggregate coverage; the last row is not claimed to be any one of those physical circuits, and their individual lengths/ratings are not superimposed as extra branches.

## Edic, Porter and Plattsburgh compatibility

The input's following exact support keys and matrices remain unchanged:

- `NPCC_S7:BRANCH_ROW:43`: Edic43–Porter44, 345/230-kV equivalent.
- `NPCC_S7:BRANCH_ROW:46`: Porter44–Porter45, 230/115-kV equivalent.
- `NPCC_S7:BRANCH_ROW:48`: Porter45–Colton46, 115-kV support path.
- `NPCC_S7:BRANCH_ROW:52`: Colton46–Plattsburgh49, 115-kV regional path.
- `NPCC_S7:BRANCH_ROW:53`: MosesW47–MosesE48, 230-kV connection.

These retain the original Porter115 and northern load support. Their late-2025 device-level correspondence is not independently verified, so they remain NPCC equivalents and receive no physical overhead/DLR identity from this overlay. The unchanged CEEC lower-voltage support also remains. New Line11 terminates at Edic345, not directly at Porter230. No unexplained transformer is inserted merely to repair a voltage mismatch.

The original row220 is `[49,48,R=.0156,X=.1536,B=0,RATE_A=2500,tap=1,shift=0]` on the 100-MVA 115/230-kV bus bases. Its relocated replacement is 49→9124 with the same R/X/B, tap, shift and finite RATE_A. Thus Plattsburgh115 still has an explicit nominal voltage-transforming equivalent to a230-kV endpoint, while the overlapping Moses–Plattsburgh aggregate is off. This relocates a regional series-impedance budget; it does not preserve the original whole-network response.

`compact_nyiso_interface_operator_variant` recomputes active cut membership from keys, statuses and bus-aligned zones. HA2 enters the model Moses South D-export cut at its Haverstock terminal; inactive historical Smart Path members leave it. The separate Porter–Colton115 path remains. The six source UPNY circuits and other hard operator anchors are unchanged. Recomputing this model cut does not establish an exact official NYISO Moses South metering definition or restore the missing Massena–Marcy765-kV system.

## Electrical assumptions and conversion

All values are on100 MVA. Each new overhead row uses `DRAKE_795_ACSR` from the existing `dlr_conductor_library`: AC resistance at75°C is0.026 ohm/1000ft, or0.026/304.8 ohm/m. This April2026 catalog is a surrogate source, not proof of installed2025 equipment. The Gold Book's nominal Drake size motivates the choice. Its HW2/Line11/Line13 descriptions specify ACSS; using the available ACSR library for them is explicitly a different surrogate, not a claim of material equivalence.

For one circuit with `n` subconductors per phase, declared length `L_m`, and base impedance `Zbase = kV^2 / baseMVA`:

```text
R_ohm = r_AC75_ohm_per_m * L_m / n
R_pu  = R_ohm / Zbase
```

X and total π-model shunt susceptance use the historical PERFORM230-kV templates in the parent's `historical_template_register`:

| Template | X pu | B pu | Estimated miles | Applied to |
|---|---:|---:|---:|---|
| `1220_1230_1` | 0.10931 | 0.41705 | 105.5 | MH2, MH3, HA2, HW2 |
| `1220_1232_1` | 0.0655 | 0.24990 | 63.2 | Line11, Line13 |

Convert to physical units first, then to the new voltage base:

```text
X_ohm_per_mile = X_old_pu * (230^2 / 100) / old_length_miles
B_S_per_mile  = B_old_pu / (230^2 / 100) / old_length_miles
X_new_pu = X_ohm_per_mile * new_length_miles / (new_kV^2 / 100)
B_new_pu = B_S_per_mile  * new_length_miles * (new_kV^2 / 100)
```

For identical physical geometry/length,230→345-kV rebasing scales per-unit X by4/9 and per-unit B by9/4. It does not scale both in the same direction. New R is independently conductor-derived; the frozen old0.85 resistance multiplier is not copied. Historical electrical parameters and workbook length estimates are template assumptions, not surveyed route or geometry measurements.

Nominal line values, independently checked in physical units:

| Key suffix | R pu | X pu | B pu | Reference MVA |
|---|---:|---:|---:|---:|
| MH2 / MH3, each | 0.000519017013 | 0.002072227488 | 0.007906161137 | 433.826766 |
| HA2 | 0.004826858223 | 0.038543431280 | 0.744463898104 | 1300.882740 |
| HW2 | 0.002018399496 | 0.016117324908 | 0.311305094787 | 1863.781932 |
| LINE11 | 0.002450913674 | 0.019576300985 | 0.378112143987 | 1863.781932 |
| LINE13 | 0.000668955262 | 0.005343178622 | 0.103202373418 | 1863.781932 |

Reference MVA is `sqrt(3)*kV*I_A/1000`, using planning summer currents1089 A for MH2/MH3,2177 A for HA2, and3119 A for HW2/11/13. This is a finite research limit, also treated as an assumed equipment ceiling by the thermal selection. It is not verified substation equipment ampacity or an observed interface limit.

AT2/AT3 use450 MVA each and TR2 uses1350 MVA, rounded approximations motivated by planning currents753 A and2259 A at345 kV. Each has assumed own-rating-base R=0.005 pu and X=0.12 pu, converted by multiplying by100/rating_MVA. Tap1 represents the nominal voltage ratio on the stated bus bases; phase shift and shunt are zero. No transformer impedance, tap position or missing voltage-control action is asserted as observed.

## Thermal policy and sensitivity

Only MH2/MH3/HA2/HW2/LINE11/LINE13 have `thermal_surrogate_eligible=true`. Each is one circuit; the discrete bundle choices are explicit in the register. Transformers, the Plattsburgh regional aggregate, inactive historical Smart Path records and inherited support equivalents are excluded.

At nominal impedance scale, the existing `build_dlr_corridor_realizations` reconstructs exactly the declared line lengths from catalog R75, circuit count and bundle count. This identity is tested. An impedance-scale sensitivity changes R and X on the nine new line/transformer records; with the same conductor library it changes effective thermal realization length by that factor. `effective_thermal_length_miles` records this effect and must not be relabeled surveyed route length. Charging scales only B; rating scales only the finite reference limits. The regional row and old infrastructure stay unchanged.

Thermal eligibility is permission to test a declared surrogate, not validation of real installed conductors. `physical_conductor_verified=false`, `parameter_ground_truth_verified=false`, and `thermal_surrogate_qualified=false` remain explicit. Bounded AC, fresh PF, electrothermal equilibrium and operating-state checks belong to the separate campaign.

## Required output registers and validation

The helper returns updated `candidate`, `full_candidate`, branch keys and NY bus/branch/generator masks. New outputs are:

- `partial_spc_branch_register`: exact key/row/endpoints/voltages/electrical parameters/status; source IDs; nominal values; physical X/B conversion intermediates; conductor/bundle/length policy; thermal whitelist; finite assumed equipment ceiling.
- `partial_spc_bus_register`, `partial_spc_bus_role_change`, and `partial_spc_branch_dispositions`.
- Exact predecessor branch matrix, infrastructure register, project register, assumptions and bus map under `partial_spc_predecessor_*` / `partial_spc_parent_*` fields.
- `partial_spc_commissioning_register`, `partial_spc_commissioning_sources`, and `partial_spc_source_manifest`. The latter hashes the two durable evidence CSVs, the new helper and conductor library using CRLF-to-LF-normalized source bytes. It includes `source_path`, `relative_path`, `sha256_lf_normalized` and an explicit hash policy; no ignored-cache download is needed to run the helper.
- `partial_spc_assumptions` and16 structural validation gates.

The live project register marks Smart Path Connect included as `selected_partial2025_with2026_exclusions`; the old four230-kV template representation is marked superseded. Their original labels remain in preserved parent registers, not passed off as current status.

The16 focused test groups include immutable parent accounting, the71/135/117 NY topology counts, exact inactive predecessor archives, proxy-ID role replacement, independent ohm/siemens/MVA and terminal-current calculations, transformer own-base conversion, correct Platts115 landing, recomputed Moses South membership, thermal R/length consistency, bounded sensitivities, preserved mixed-precision source evidence, and rejection of duplicate application, wrong endpoints, changed regional budgets, nonzero proxy injection, incorrect landing voltage, wrong MVA base, stale templates and unregistered options.
