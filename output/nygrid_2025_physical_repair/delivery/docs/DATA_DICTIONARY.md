# Current model data dictionary

This dictionary describes the current physically corrected, boundary-loss-consistent synthetic AC model and its one-way R/X-conditioned overhead thermal screen. The package contains one model with four effective-date states during 2025. The default snapshot is hour 8508. The compact network retains 148 buses and recovers voltages and currents on the detailed network.

## Files and access

The current model uses three data files. `model/latest_model.mat` contains its current templates, identity/time axes, loss-accounting data and conductor metadata. `model/profiles_h0001_4380.mat` and `model/profiles_h4381_8760.mat` contain the exact hourly operating arrays for hours 1–4380 and 4381–8760, respectively. These two storage partitions are parts of the same current model. `model/model_receipt.json` records their schema and content identities.

Use `load_nygrid_latest(hour_index)` after `setup_nygrid_latest` to obtain a current MATPOWER case; use `run_nygrid_latest_acpf` for the coupled AC/loss solution and `screen_nygrid_latest_dlr` for the explicit-weather thermal screen. The runtime reads these files within the extracted package.

The static MAT file contains one variable, `model`. Each profile file contains one variable, `profiles`. `nylatest_data` verifies the three file hashes, joins the two profile parts in hour order, and exposes the combined arrays internally as `model.profiles`.

| Static `model` field | Shape or content |
|---|---|
| `axis.hour_index`, `axis.timestamp_utc`, `axis.source_qualified` | 8760-by-1 index, UTC string and logical qualification axes |
| `axis.state_index`, `axis.reference_bus`, `axis.post_dover_full_service` | 8760-by-1 state selector, reference-bus identity and post-Dover flag |
| `axis.state_names`, `axis.state_labels`, `axis.template_hours` | Four ordered state identities/labels and their template hours: 1, 3360, 3576 and 8472 |
| `templates` | Four detailed current MATPOWER templates; hourly fields are replaced by the loader |
| `retained_bus_ids` | 148 ordered compact-network bus IDs |
| `generator_bus_ids`, `generator_bus_rows` | 1464 current generator-terminal IDs and their detailed row lookup for each of four states |
| `generator_registry` | Stable row/device key, current bus ID, fuel category and logical native-device flag; `native_profile_row` is a boolean flag |
| `fixed_transfer_registry` | Six transfer rows with endpoint identities and record kind |
| `external.generator_mask`, `external.capability_proxy_MW` | 1464-entry logical mask and 28-entry finite external capability vector |
| `loss_static` | Four state-specific accounting contracts: group membership, parent terminals/ownership, external shares, HQ identity and finite regional P bounds |
| `thermal` | Current branch interpretation registry, 14 conductor records, geometry windows and four cable-conflict records |
| `policy`, `profile_shards` | Current method declarations and the two profile-file names, hour bounds, sizes and SHA-256 bindings |

| Field in each `profiles` variable | Stored shape | Combined annual shape | Units and interpretation |
|---|---:|---:|---|
| `bus_PD_MW` | 4380 × 140 | 8760 × 140 | Supplied gross active demand at bus IDs 1–140, MW |
| `bus_QD_MVAr` | 4380 × 140 | 8760 × 140 | Corresponding supplied reactive demand, MVAr |
| `generator_PG_MW` | 4380 × 1464 | 8760 × 1464 | Reconstructed current baseline generator active power, MW |
| `generator_Pmin_MW`, `generator_Pmax_MW` | Each 4380 × 1464 | Each 8760 × 1464 | Supplied hourly admission bounds, MW; the loader fixes external baseline P to PG, and the loss policy subsequently applies its finite regional balancing bounds |
| `fixed_transfer_PF_MW` | 4380 × 6 | 8760 × 6 | Four prescribed DC and two ideal PAR transfer active-power values, MW |
| `dover_bank_phase_shift_deg` | 4380 × 2 | 8760 × 2 | Post-Dover bank model phase angles, degrees; used only when the post-Dover flag is true |

Every profile array retains double precision. The first file's local row 1 is annual hour 1; the second file's local row 1 is annual hour 4381. The other detailed buses have zero prescribed demand. Missing or inapplicable values can remain in stored arrays; source qualification and the relevant state flags determine whether an input is usable. The runtime does not interpolate those values.

## Time and qualification

| Item | Current contract |
|---|---|
| Physical-hour index | One-based integer, 1 through 8760 |
| UTC timestamp range | 2025-01-01T05:00:00Z through 2026-01-01T04:00:00Z, inclusive |
| Time interval | One physical hour; UTC remains unique across daylight-saving transitions |
| Source-qualified hours | 8651; the other 109 hours are rejected by the loader |
| Meaning of source qualification | Required operating-input sources and the bounded reconstruction passed their input gates; this is not an AC solution or an operating-limit certificate |
| Power base | 100 MVA |
| Input power scale | Existing synthetic scale factor gamma = 0.30012075175285535 |
| Current convention | Compute amperes from the actual synthetic AC voltage/power base; do not divide or multiply recovered current by gamma |

The timestamp strings define the time axis. A local-clock label alone can be ambiguous at daylight-saving transitions. All hourly arrays use this same ordered axis, and the loader does not replace an unqualified hour with a neighboring one.

## Effective-date network states

| State | Inclusive hour indices | First UTC timestamp | Hours | Source-qualified hours | Detailed buses | Numerical AC branches | Parent corridors |
|---|---:|---|---:|---:|---:|---:|---:|
| Pre-May | 1–3359 | 2025-01-01T05:00:00Z | 3359 | 3315 | 266 | 485 | 410 |
| May 21 | 3360–3575 | 2025-05-21T04:00:00Z | 216 | 214 | 266 | 485 | 410 |
| May 30 | 3576–8471 | 2025-05-30T04:00:00Z | 4896 | 4835 | 266 | 485 | 410 |
| Post-Dover | 8472–8760 | 2025-12-20T04:00:00Z | 289 | 287 | 267 | 488 | 413 |

These are the dated states required to represent the current model over its time axis. Every state uses the current impedance, generator-capability, loss-accounting and thermal-selection policies. The 148 retained buses are common to all states. The detailed voltage-recovery matrix has 266 or 267 rows; the branch-current recovery operators have 485 or 488 rows. Retained admittance entries are matrix coefficients, not physical overhead conductors.

## Electrical and identity axes

| Returned case or metadata | Axis and units | Meaning |
|---|---|---|
| `baseMVA` | Scalar, MVA | 100 MVA three-phase system base |
| `bus` | Detailed bus rows; standard MATPOWER bus columns | `BUS_I` is the bus identity. `PD/QD` are MW/MVAr; `VM/VA` are pu/degrees; `BASE_KV` is line-to-line kV. Bus IDs are not array-row indices. |
| `gen` | 1464 ordered rows; standard MATPOWER generator columns | Stable generator/device axis with hourly active-power inputs and bounds; MW/MVAr and declared MVA capability proxies |
| Native generators | Rows 1–1436 | Reconstructed 2025 native device records; row existence does not imply the device is admitted or online in every hour |
| External equivalents | Remaining 28 rows | Regional boundary equivalents, including the fixed HQ row; they are not 28 observed physical generating units |
| `branch(:,1:13)` | 485 or 488 ordered numerical AC branch rows | Endpoint bus IDs, total branch R/X/B in pu, ratings, taps, phase shift, status and angle bounds. B is total branch shunt susceptance, divided between ends by the pi model. |
| `branch(:,14:17)` after a solution | Same branch rows; MW/MVAr | From- and to-terminal P/Q, including modeled charging and tap effects |
| `userdata.ac_system.branch_keys` | One key per numerical branch row | Stable runtime identity within the selected state; use keys and parent mapping when comparing dated states |
| `userdata.ac_system.branch_parent_row` | One parent ID per numerical branch row | Groups numerical sections into 410 or 413 modeled parent corridors |
| `userdata.ac_sections.branch_map` | Same numerical branch axis | Identifies physical corridor terminals and numerical section membership |
| `dcline` | Six ordered transfer records; standard MATPOWER DC-line columns | Four original DC records plus two ideal PAR-controlled transfer equivalents; this count does not mean six physical HVDC links |
| Retained bus IDs | 148 ordered identities | Defines compact voltage/admittance axes and their mapping to detailed rows |

Native generation and its hourly availability/capability reconstruction are study inputs, not observed unit telemetry or a validated commitment schedule. `GEN_STATUS` represents modeled hourly admission. Storage energy, ramping and individual generator capability curves are not established by these data.

The six controlled active-power transfers are held at their supplied hourly values. The two added ideal PAR transfers represent Ontario-to-New-York controlled exchange in the `dcline` container. Their representation is not a claim about a physical HVDC device or measured tap position. The post-Dover AC bank phase controls are separate hourly model controls.

## Gross demand and loss accounting

The supplied NY zonal demand is a gross boundary-demand target consistent with the study's P58 convention. For each NY zone, the current solver enforces:

```text
gross zonal demand = delivered load PD + allocated AC real losses
```

NY delivered `PD` is obtained by scaling that zone's gross bus demands by `1 - allocated_loss / gross_zonal_demand`. `QD` uses the same ratio, preserving the supplied demand power factor. Native and HQ active generation remain fixed. External regional equivalents supply their assigned losses through finite capability bounds and frozen regional allocation shares; their external delivered PD/QD remains unchanged.

The loss-accounting groups are NY zones A–K, ISO-NE, Ontario and PJM. Parent-corridor Joule losses are summed from their numerical sections before allocation. An internal NY corridor assigns half its loss to each endpoint zone; a corridor within one external region assigns all its loss to that region; a NY/external tie assigns all its modeled loss to the external region. Modeled DC losses are zero. These ownership rules are declared modeling assumptions, not observed NYISO meter assignments.

The released parent-224 equivalent uses total R/X/B = 0.02/0.0147/0 pu across its two numerical sections. It has no conductor-based DLR record or asserted installed equipment rating.

## Conductor and thermal axes

`userdata.ac_system.thermal_segments` describes current material segments. Join each segment to the selected case by its branch key, branch row and segment ID. Several material segments may belong to one numerical branch; several numerical branches may belong to one parent corridor. These counts are distinct.

| Thermal quantity | Units and meaning |
|---|---|
| `catalog_id` | Identity in the current 14-entry ACSR/ACSS manufacturer-derived catalog |
| `segment_length_m` | Declared equivalent material-segment length, metres |
| `circuits` | Integer count of identical uncoupled parallel circuits |
| `bundle_count` | Integer number of subconductors per phase in each circuit |
| `base_kv` | Line-to-line voltage base, kV |
| `gmd_m` / `bundle_spacing_m` | Phase GMD / adjacent bundle spacing, metres |
| `reference_temperature_c` | Temperature at which the current electrical R is represented |
| `temperature_min_c` / `temperature_max_c` | Supported/declaratively permitted thermal range, degrees C |
| Catalog AC resistance | Ohms per metre of one subconductor, interpolated only within the supported manufacturer range |
| Diameter / GMR | Metres; physical radius for capacitance and GMR for inductance are treated separately |
| Heat capacity | Joules per metre per kelvin for one subconductor; material and constant-heat-capacity assumptions remain explicit |
| Emissivity / absorptivity | Dimensionless declared surface assumptions |

The current selector admits 179 parents / 251 numerical branches / 251 material segments before Dover and 180 / 252 / 253 afterward. Admission requires compatible overhead classification, matching voltage bases and ordinary taps, valid material/geometry/temperature metadata, and forward reproduction of both current R and X. Known cable conflicts 300, 309, 310 and 386 remain excluded. Catalog/geometry inference does not identify an installed conductor.

Thermal heating uses AC series current, excluding line charging. The per-subconductor current is phase current divided by `circuits * bundle_count`; all series material segments share the branch phase current. Terminal currents are reported separately for equipment and section-end comparisons. The one-way screen holds electrical R and the solved operating point fixed and evaluates weather-dependent steady ampacity at each declared temperature cap.

Weather must be supplied explicitly with `ambient_c`, `wind_m_s`, `wind_angle_deg`, `solar_w_m2` and `pressure_pa`. One row declares uniform scenario weather; multiple rows must match the returned branch-key/segment-ID order exactly. Supplied scenario weather is not labeled as observed route weather.

## Result qualification and usable scope

The package supports current-case loading, compact AC solution with detailed recovery and boundary-consistent loss accounting, and one-way synthetic overhead current/ampacity screening. MATLAB is external; the bundled numerical dependency is MATPOWER 8.1. Validation uses MATLAB R2026a Update 3 with JVM enabled. Compatibility with other MATLAB releases is not established by that validation.

Read the returned audit gates separately:

- `PF_converged` and `AC_equation_gate` describe numerical convergence and independently checked AC equations.
- `loss_allocation_gate` and `reduction_and_equation_gate` describe demand/loss-accounting closure and detailed voltage/current recovery.
- `VQ_and_generator_assumption_gate` and `audit.passed` address the additional operating bounds and assumptions. A converged solution alone does not establish these gates.
- Thermal numerical identities and `all_candidate_current_envelopes_satisfied` are separate. A valid current/heat calculation may report an exceeded synthetic ampacity.

No whole-system operating qualification, installed-asset DLR certificate, conductor-temperature equilibrium, thermal-resistance feedback or DLR-constrained OPF is established by this handoff. Source-qualified annual inputs are provided; use the included validation receipt to distinguish the actual portable smoke checks from any unperformed annual solution run.

## Physical repair metadata

`model.baseline_source_model_commit` identifies the preserved baseline. The
physical change is identified by `model.physical_repair.candidate_receipt_sha256`
and its frozen candidate receipt, rather than by implying that the baseline
commit contains the repair. Both hourly profile shards retain their baseline
SHA-256 values.

Each static template retains `userdata.physical_repair` and
`userdata.physical_repair_185195`. The full-axis shunt placement is recorded in
`userdata.ac_sections.reactor_BS_delta_all_buses`, aligned exactly with
`reactor_BS_bus_ids`. The original-bus `reactor_BS_delta` remains an original-axis
view. Reactor ledger records include distributed bus IDs and MVAr at 1 pu.
Parent 41's R/X/B and thermal material/geometry metadata form one coherent
synthetic realization; parent 185/195 retain their total fixed reactor ratings
and distribute those shunts along the existing numerical sections.

`source_model_commit` remains a baseline provenance field. The repair receipt
hash and static model SHA identify the corrected data. No geographic chord or
observed interface residual was used to select the repair.
