# Research model contract: NY-only electrical baseline and evidence coverage

The operating candidate is a NY-only electrical model with explicit NY-side
boundary injections. Full external-NPCC qualification, external reduction and
a fixed bus count are optional diagnostics. Original NPCC, S7, S13 and PERFORM
files remain historical sources and comparisons. S12 remains optional and may
not supply dense equivalent branches to the operating candidate. The existing
86-bus S14 experiment retains its external-reduction role.

`research_model_contract.m` schema 2 permits replacing, deactivating, splitting
or aggregating internal equivalents. Preserve original identities and
parameters in source-to-model mappings, together with explicit old-element
dispositions and conservation of loads, generation, shunts and controls.
Historical checkpoint builders remain unchanged; the new candidate does not
have to keep every original NY element electrically active.

| Contract mode | Vintage and power convention |
|---|---|
| `historical_2019` | Existing 2019 similarity-scaled behavior, preserved for compatibility |
| `historical_similarity_scaled` | Explicit alias for the same scaled historical convention |
| `historical_actual_mw` | 2019 source at actual MW, without statewide normalization |
| `contemporary_2026` | Actual MW and the declared contemporary infrastructure cutoff |

The initial NY-only boundary model uses scheduled P and declared fixed Q at
registered NY landings, positive into NY. Gross load, native generation and
boundary injection remain separate records. Allocate gross load first; then
assemble effective demand as gross demand minus boundary P/Q exactly once.
Boundary supply cannot also appear in native zonal generation. Multi-landing
allocation is a frozen, documented assumption; it does not reconstruct
external loop flows or provide undeclared voltage support.

Three statuses are independent:

| Field | Claim supported |
|---|---|
| `electrical_baseline_qualified` | Feasible, accounted and independently replayable under declared finite controls and operating limits |
| `contemporary_validation_coverage` | Dated infrastructure and matched observational/held-out coverage |
| `dlr_ready` | Completed conductor realization and independent electrothermal validation |

The contract does not qualify a result: its electrical and DLR statuses start
false, and coverage starts not evaluated (not applicable for historical
cases). Missing exact bus-level observations limits the validation claim and
does not automatically block an explicitly assumed research baseline.
Assumptions must remain labeled; they cannot serve as observed or independent
validation evidence. `release_ready` remains a compatibility field and is
never inferred from the contract or input-schema tests.

The contemporary research mode declares an infrastructure cutoff of
**2026-09-06**, actual New York MW, and a conservative observation window
beginning at midnight New York time on **2026-06-23**, after the announced
Smart Path Connect energization. Its current registry is a construction input,
not an assertion that the existing 2019 admittance already represents 2026.

The contract permits explicitly synthetic overhead corridor realizations.
These must retain
synthetic provenance and independently demonstrate electrical resistance,
current sharing, and heating consistency before thermal use. Physical overhead
circuits require source identity. Nonthermal equivalents, underground and
submarine cables, DC imports, and transformers receive no overhead DLR model.
Eligibility does not attach a thermal model. No conductor or thermal solver is
implemented by this electrical-only change.

This contract does not alter historical case files or relabel inherited
equivalents as physical assets. Actual MW is a load-input
policy, not proof of AC feasibility. Applying these loads to an inherited case
does not rescale its admittance or establish appropriate aggregate capability.

## Dated assets and remaining engineering work

`contemporary_asset_register.csv` contains one project or independently
accounted segment group per row. Status and modeling action are distinct.
`status_known_by` is an evidence bound, not an exact commissioning timestamp
unless the source establishes that precision. Source descriptions, project MW,
and project route lengths are never converted into invented branch impedances.
Every row currently has `implemented=false`, `model_element_ids=unmapped`, and
`parameter_source=unavailable`. These gaps limit contemporary asset-validation
coverage until physical/residual replacements and receiving connections are
mapped and independently checked for overlap. They do not prevent qualifying
a separate actual-MW historical reference under explicit assumptions.

| Asset | Verified evidence and modeling consequence |
|---|---|
| CEEC | The owner reports full energization in December 2023. Reconcile the upgraded corridor with inherited paths before inserting impedance or capacity. [LS Power](https://www.lspower.com/celebrating-central-east-energy-connect-one-year-later/) |
| NYES | The developer reports June 2023 energization and identifies the Schodack–Pleasant Valley 345 kV corridor and station work. Exact case terminal mapping and compensation remain required. [Developer project description](https://nytransco.com/new-york-energy-solution/) |
| Smart Path and Smart Path Connect | The 2023 Smart Path rebuild initially operated at 230 kV; the June 22, 2026 announcement describes the connected 345 kV route. The 78-mile Smart Path and the separate 100-mile Connect project must not be counted as duplicate additions. [2023 state announcement](https://www.governor.ny.gov/news/governor-hochul-announces-completion-north-countrys-smart-path-78-mile-clean-energy), [2026 state announcement](https://www.governor.ny.gov/news/governor-hochul-celebrates-completion-100-mile-smart-path-connect-transmission-project) |
| CHPE | The June 16, 2026 owner release confirms commercial operation, a 1,250 MW underground/submarine HVDC link, and an Astoria receiving converter. June 1 is the stated contract start, not an inferred exact commercial-operation date. The nameplate does not establish any hour's import or converter Q capability. [TDI owner release](https://chpexpress.com/news/the-champlain-hudson-power-express-marks-completion-of-a-landmark-1250-mw-energy-infrastructure-project-connecting-quebec-to-new-york-city/) |
| RCC Queens | DPS reports May 2023 energization; Con Edison identifies the completed Corona–Long Island City underground connection. It remains cable infrastructure outside overhead DLR. [DPS annual report](https://dps.ny.gov/2023-2024-annual-report), [Con Edison projects](https://www.coned.com/en/our-energy-future/our-energy-vision/where-we-are-going/reliable-clean-city-project) |
| RCC Staten Island / Brooklyn | The utility page still labels these active. Scheduled 2025/2026 dates alone do not establish commissioning; both remain `completion_unverified`. [Con Edison projects](https://www.coned.com/en/our-energy-future/our-energy-vision/where-we-are-going/reliable-clean-city-project) |
| Propel NY | The developer describes construction expected from late 2026 to 2030, pending approval. Keep this out of the present baseline. [Developer route and schedule](https://www.propelnyenergy.com/queens-route) |

These are verified public status observations reviewed against the cutoff, not
an exhaustive NYISO asset database. The generator register contains all 62
inherited S13 generator rows with their original P/Q limits and source row.
Its contemporary unit identities, operating status, and P/Q capabilities remain
unverified/NaN. This accounts for inherited records without pretending that
their bus names identify currently operating physical units. A dated unit
crosswalk to NYISO planning inventory and EIA inventory is still needed for
actual retirement/addition reconciliation. See [NYISO publications](https://www.nyiso.com/publications)
and [EIA generator inventory](https://www.eia.gov/electricity/data/eia860m/).

## Real public operating inputs

`contemporary_source_data/` preserves original daily CSV bytes for August 1,
15, and 25, 2026 from the [NYISO August 2026 integrated-load archive](https://mis.nyiso.com/public/csv/palIntegrated/20260801palIntegrated_csv.zip).
The normalized `contemporary_operating_observations.csv` has **792 zonal rows /
72 complete hourly operating points**. These days were chosen as reproducible
examples covering the month, not selected or certified as a representative
stress-test population. All rows remain `diagnostic` / `input`; none claim
held-out electrical-model validation.

The importer performs no normalization, interpolation, or aggregation. It
maps the source's A–K zone names, preserves raw local time and the explicit
EST/EDT tag, and writes UTC. `source_sha256` fingerprints the unmodified daily
archive member, whose filename and CSV line are stored alongside the source
archive URL. `contemporary_source_manifest.csv` records those hashes and the
archive hash. The August 1 midnight EDT point is **18,600.504 MW**, not the
historical constant-total 10,902 MW target. Reactive loads, generation,
interchange, voltage, and outages have not been fabricated to fill gaps.

The required observation schema is:

| Fields | Meaning |
|---|---|
| `scenario_id`, `timestamp_utc` | One operating point with one exact UTC timestamp |
| `kind`, `entity_id`, `value`, `unit` | Explicit electrical quantity and identity; load zones A–K; MW/MVAr/pu |
| `power_scale` | `actual_mw` for the contemporary case; historical similarity targets stay separate |
| `provenance_class`, `source_uri`, `source_sha256` | Public observation or declared assumption; real observations require source URL and SHA256 |
| `accounting_id` | Unique injection/observation accounting key per timestamp |
| `dataset_split`, `target_use` | Diagnostic/calibration/held-out and input/calibration-target/validation-target roles |

For `external_import_p/q`, positive means into the retained NY system. Regional
AC aggregate schedules and controlled facility imports must use separately
registered devices without duplicate coverage. Source-observation schema
validation does not establish interchange-device feasibility or cover generator
capacity reconciliation.

`validate_research_inputs` rejects mismatched vintage, units and scale,
duplicate electrical keys even under different scenario/accounting aliases,
missing zones, mixed timestamps, nonfinite values, negative active demand,
missing provenance, and assumption/calibration misuse as independent evidence.
It does not download or cryptographically authenticate a supplied source URL;
use the byte-preserving importer to generate verified local source hashes.

`contemporary_apply_loads` requires one A–K load point and an explicit bus
allocation table with `bus_id, zone, weight, q_over_p, source_uri`. Weights must
sum to one per zone. It preserves raw MW and assigns reactive demand using
declared per-bus Q/P assumptions, while leaving branches and generators
unchanged. It rejects omitted inherited NY loads. Allocation weights and Q/P
are frozen research inputs to validate, not measured bus-level disaggregation.

## Reproduction and readiness

With `System Matpower Format/NY_Lite` on the MATLAB path:

```matlab
historical = research_model_contract('historical_actual_mw');
legacy = research_model_contract('historical_2019'); % remains similarity-scaled
contract = research_model_contract('contemporary_2026');
checks = contemporary_test_inputs();
% To regenerate normalized inputs from the three committed original CSVs:
h = fileparts(which('contemporary_import_nyiso_loads'));
raw = dir(fullfile(h,'contemporary_source_data','*palIntegrated.csv'));
obs = contemporary_import_nyiso_loads(fullfile({raw.folder},{raw.name}));
% Supply a reviewed allocation table before applying a single point:
% [mpc, audit] = contemporary_apply_loads(mpc, obs(rows,:), allocation, contract);
```

`contemporary_test_inputs` verifies authentic source totals and UTC conversion,
actual-MW time variation, exact allocation and Q accounting, external-load and
branch/generator invariance, and adversarial input/register rejection.
`contemporary_validate_registers` reports structural accounting separately from
release readiness. All current outputs explicitly remain `release_ready=false`.
These load observations alone do not establish contemporary operating realism.
Missing topology/capability evidence and matched injection/control data remain
visible limitations on contemporary validation coverage. Frozen parameters and
held-out days are required for independent contemporary validation claims.
Thermal readiness remains a separate later status.

Package A is reproduced with `run_ny_only_foundation` from the repository root.
It first reports source-snapshot violations, then attempts a prior-only bounded
historical reference with explicit boundary accounting. Qualification depends
on independently replayed AC balance, finite native P/Q limits, declared
voltage/rating/angle limits and accounted reference adjustment. A relaxed or
failed solution is a diagnostic outcome, never a qualified baseline. Package A
does not implement later internal replacement or contemporary asset packages.
