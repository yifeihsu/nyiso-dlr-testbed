# EPA generation inputs for the compact NY study

The extraction contains **4,103 reported EPA unit-hour records for 16 exact hours**: six 2019 scenarios, six 2025 scenarios, and four new calendar-selected 2025 validation hours. These are independent public generation inputs. No internal NYISO interface-flow observations enter extraction, plant mapping, or aggregation.

The values are **gross combustion-unit output**, not net grid injections or observed zonal generation. EPA permits engineering estimates when a gross-load measurement is missing; the bulk file does not provide a separate gross-load measurement-quality flag. The module preserves source values and blanks without claiming that every reported number is direct telemetry. [EPA Part 75 Policy Manual, questions 13.4 and 13.6](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P100WXUK.TXT).

## Source files and reproducibility

EPA moved the former monthly FTP data to CAMPD in February 2023. The former `2019nyMM.zip` and `2025nyMM.zip` path in NYgrid's download utility is therefore not used. Current CAMPD provides annual state hourly bulk files; only New York's two annual files were downloaded, plus small facility metadata and a daily file used to verify quantity units. Annual raw files remain in `tmp/epa_generation_raw`, outside the deliverable. [EPA bulk-data migration notice](https://www.epa.gov/air-emissions-inventories/where-can-i-download-hourly-emissions-data-continuous-monitoring), [CAMPD bulk downloads](https://campd.epa.gov/data/bulk-data-files).

| Source | Raw bytes | SHA-256 |
|---|---:|---|
| 2019 NY hourly; release 2025-10-02 | 485,630,847 | `e58710fec124f42d829ac340fe319562da3aa7aaea8345f5b595d2e1b42a0221` |
| 2025 NY hourly; release 2026-08-29 | 442,207,147 | `a2d0cfba9466fc2347fec867fafd9bba8c39d5a1b821664e5e792901e6148f6a` |
| 2025 NY daily | 16,387,133 | `0f74bcbfc13e3cacec751f3a61b844934dbaddc1f5ee341a4204d280f389bd1e` |
| EPA 2019 facility attributes | 1,717,839 | `d6b074ba7e5173d4c3318b8178b85b055885b11c1c186c15180dc8af698d375d` |
| EPA 2025 facility attributes | 1,556,685 | `d7b743273c8919b5af8a6fef45f813dd17f9dfada8c3330e508f342383a1690d` |

`epa_source_manifest.json` contains full URLs, source byte counts, raw SHA-256 hashes, extract hashes, code hash, source-scenario catalog hash, and preregistration-protocol hash. Each selected source record also retains its ordinal, exact original record bytes encoded as base64, and record SHA-256. This preserves blanks, numeric text, EPA IDs, quoting, and original line endings. Selected CSVs themselves use LF for checkout portability.

The public bulk URL is case-sensitive and requires no API key. Refreshes fail if the pinned source bytes change. A new source release must be reviewed explicitly. The manifest's 2019 and 2025 annual reporting-unit counts are 310 and 234; these are EPA reporting identities, not counts of physical generators in the electrical model.

## Time and output conventions

NYISO labels are treated as hour beginnings using the separately recorded P58B/P58C time-alignment audit. Each requested UTC interval `[t,t+1h)` is converted to fixed EST before selecting EPA's date and hour. Thus 2025-07-29 18:00 EDT selects EPA 2025-07-29 hour 17 EST, covering 22:00–23:00 UTC. Winter 18:00 EST selects EPA hour 18. Both requested civil time and EPA local standard time remain in the ledger. EPA requires local standard time through daylight-saving changes. [EPA Part 75 Policy Manual, question 13.4](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P100WXUK.TXT).

For the current hourly bulk format:

`clock-hour gross energy (MWh) = Gross Load (MW) × Operating Time (hours)`

The average gross MW over the full one-hour interval has the same numerical value as that interval's MWh. Operating time is multiplied **once**. The current EPA database procedure copies hourly gross load as a rate, while the daily procedure multiplies gross load by operating time before summation. This is more specific than the general pre-publication-adjustment language in the 2022 data guide. [Pinned EPA hourly SQL](https://github.com/US-EPA-CAMD/easey-db-scripts/blob/3da401e329303638f1fac7e4d8754ec33779c2af/camdecmpsaux/procedures/pdem_update_public_load_p75_unit_hour.sql), [pinned EPA daily SQL](https://github.com/US-EPA-CAMD/easey-db-scripts/blob/3da401e329303638f1fac7e4d8754ec33779c2af/camdecmpsaux/procedures/pdem_update_public_load_p75_unit_day.sql).

The saved source fixture independently verifies the conversion for Danskammer, ORIS 2480/unit 3, 2025-07-29:

| Calculation | Result |
|---|---:|
| Sum of hourly gross MW values without weighting | 975 |
| Sum of gross MW × operating time | 951.75 MWh |
| Independently downloaded EPA daily gross total | 951.75 MWh |

All 24 raw hourly rows and the daily source row are retained in `quantity_audit_*_source.csv`. Initial read-only investigation also checked all 63 units with partial operation that day; the weighted daily totals agreed. The executable regression fixture uses the complete single-unit day above, whose unweighted result differs by 23.25 MWh.

Blank gross values remain blank, including reported offline rows. They are separately counted as `reported_offline_gross_blank`; they are never relabeled observed zero. A source record absent at a selected hour is likewise not synthesized. For example, the 2019 winter hour has 231 rows against 310 identities in the annual source, and the 2025 winter hours have 225 against 234. This is explicit reporting coverage, not evidence of complete statewide production.

## Identity and zone mapping

An observation's stable key is `EPA:ORIS:<facility ID>:UNIT:<unit ID>`. Leading zeros in EPA unit IDs are preserved. Initial zone mapping uses NYgrid's 2019 facility/unit crosswalk pinned to commit `47698b6c7823ae7b1bc6935e5601d5b64b8f918e`; same-facility zone fallback is explicitly labeled an assumption when every mapped unit at that ORIS facility agrees. Exact and fallback rows retain their original workbook row references. [Pinned NYgrid crosswalk](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/Data/thermalGenMatched_2019.xlsx).

The EPA–EIA crosswalk adds identifier annotations, but its 2018 EIA basis and 2022 release are not presented as a 2025 fleet census. Current year-specific EPA facility attributes independently verify reporting identities, location, category, and associated generators. EPA combustion units and EIA electricity generators have many-to-many relationships; crosswalk joins never multiply observed output. The three NYgrid rows for ORIS 2682/unit 20 therefore annotate one EPA observation, rather than tripling it. [EPA–EIA crosswalk scope and cautions](https://www.epa.gov/power-sector/power-sector-data-crosswalk), [EPA crosswalk methodology](https://github.com/USEPA/camd-eia-crosswalk).

Six site assignments are declared in `declared_facility_zone_evidence.csv`: Gowanus, Hudson Avenue, Narrows, and Riverbay in J; East Hampton in K; Cricket Valley in G. The file distinguishes Gold Book site evidence from geographic inference. EPA's current facility metadata identifies Cricket Valley as ORIS 57185 in Dutchess County, with U001/U002/U003 and associated combustion/steam generators; the 2025 Gold Book places Cricket Valley CC1–CC3 in G. Associated steam generators do not create extra EPA observations. [EPA 2025 facility attributes](https://api.epa.gov/easey/bulk-files/facility/facility-2025.csv), [NYISO 2025 Gold Book, PDF page 95](https://www.nyiso.com/documents/20142/2226333/2025-Gold-Book-Public.pdf/088438e1-02f1-5316-211b-dbca17c01b4b).

The Gold Book source SHA-256 is `cc43665b9344a04b4c9355edd1dc7e31d42a6bb759ffe027ad867221556aea8e`. Its generation table verifies site zones; it is not a complete EPA-unit electrical-landing crosswalk. Narrows and Riverbay retain an explicit NYC geographic proxy. All positive reported gross in these selected hours maps to a declared zone; unmatched zero/blank records remain in the output ledger.

Riverbay ORIS 52168 is excluded from the grid-fossil share because the available CHP evidence does not establish its gross output as NYISO grid delivery. All of its reported output remains in total gross and unit ledgers. Other Electric Utility/Cogeneration categories provide a gross-output share proxy, with net delivery left unresolved.

## Files for the electrical reconstruction

- `epa_generation_hourly.csv`: every selected unit-hour, source quantities, time alignment, stable identity, zone policy, current EPA attributes, and `grid_fossil_share_eligible`.
- `epa_zonal_gross_generation.csv`: 16 × 12 rows: A–K and an explicit `UNMAPPED` bucket. Fields `grid_eligible_gross_clock_hour_mw` and `all_reported_gross_clock_hour_mw` partition the unit ledger exactly.
- `epa_snapshot_coverage.csv`: source rows, blanks, annual reporting identities, mapped and unmatched gross.
- `epa_unit_identity_register.csv` and `epa_unmatched_generation.csv`: mapping and unresolved records.
- `epa_generation_input_tests.json`: 12 passing focused test groups, including exact-byte integrity, partial-hour conversion, missing values, duplicate/conflicting identities, zonal conservation, CHP exclusion, and independent offline replay.

EPA primary/secondary fuel categories do not establish the fuel actually burned during an individual dual-fuel hour. The aggregation therefore exposes a **Combined Fossil** category, with source fuel fields retained. A downstream normalization to NYISO's combined fossil fuel-mix total is a transparent estimate for net output and incomplete coverage; it does not turn these gross source shares into measured zonal net generation. At S1 2025, all reported gross is 20,022.58 MW averaged over the clock hour; grid-eligible gross is 19,999.58 MW, with 23 MW of Riverbay output separately excluded.

From the repository root, run `build_compact_epa_generation_inputs.py --replay` for a small-file rebuild, or run it against the existing raw cache for an independently filtered rebuild. Use `--download` only to obtain missing pinned raw sources. Run `test_build_compact_epa_generation_inputs.py` for the focused checks. Neither command solves an electrical case or uses interface fitting targets.
