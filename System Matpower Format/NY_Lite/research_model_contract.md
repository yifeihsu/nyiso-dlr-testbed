# Research model contract and contemporary inputs

The historical S13/PERFORM 2019 case remains a separate regression reference.
The contemporary research contract declares an infrastructure cutoff of
**2026-09-06**, actual New York MW, and a conservative observation window
beginning at midnight New York time on **2026-06-23**, after the announced
Smart Path Connect energization. Its current registry is a construction input,
not an assertion that the existing 2019 admittance already represents 2026.

`research_model_contract.m` is the machine-readable contract. It permits
explicitly synthetic overhead corridor realizations. These must retain
synthetic provenance and independently demonstrate electrical resistance,
current sharing, and heating consistency before thermal use. Physical overhead
circuits require source identity. Nonthermal equivalents, underground and
submarine cables, DC imports, and transformers receive no overhead DLR model.
Eligibility does not attach a thermal model. No conductor or thermal solver is
implemented by this electrical-only change.

This contract extends the physical-only eligibility restriction in the earlier
S14 design for the new research branch. It does not alter historical case files
or relabel inherited equivalents as physical assets. Actual MW is a load-input
policy, not proof of AC feasibility. Applying these loads to an inherited case
does not rescale its admittance or establish appropriate aggregate capability.

## Dated assets and remaining engineering work

`contemporary_asset_register.csv` contains one project or independently
accounted segment group per row. Status and modeling action are distinct.
`status_known_by` is an evidence bound, not an exact commissioning timestamp
unless the source establishes that precision. Source descriptions, project MW,
and project route lengths are never converted into invented branch impedances.
Every row currently has `implemented=false`, `model_element_ids=unmapped`, and
`parameter_source=unavailable`. The register therefore blocks contemporary
release until physical/residual replacements and receiving connections are
mapped and independently checked for overlap.

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
Missing contemporary topology/capabilities and matched injection/control data
must be resolved before these load observations can establish a contemporary
AC baseline. Frozen parameters and independently held-out days remain required
for the electrical release; thermal stages are outside this implementation.
