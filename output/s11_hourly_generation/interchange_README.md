# S11 aligned hourly interchange schedules

The interchange files have the same 4,416 UTC timestamps, local timestamps,
and EST/EDT labels as `s11_hourly_load_profiles/pd_mw.csv`: January, April, and
July of 2019 and 2025. They approximate NYISO's published external **schedule**
point samples as hourly mean MW. They are not measured actual interchange.

Use `interchange_boundary_applied_mw.csv` for the complete modeled simulation
schedule. It has the eight existing S11 boundary injections in saved mapping
order. Positive MW means import into NY; negative MW means export. The
existing S11 boundary reactive-injection policy is fixed zero MVAr, which is
a model assumption rather than observed reactive exchange.

| Regional public channel | S11 boundary bus IDs and shares |
| --- | --- |
| `SCH - HQ - NY` | 48: 100% |
| `SCH - NE - NY` | 37: 40%; 73: 60% |
| `SCH - OH - NY` | 54: 100% |
| `SCH - PJ - NY` | 66: 35%; 67: 15%; 75: 25%; 81: 25% |

These are approximate spatial allocations inherited from
`NY_Lite/nyiso_public_external_interface_map.m`. Each regional schedule is
conserved by the eight-row allocation. The schedule values have no load
similarity scaling, optimization, or fitting against internal line flows.

## Coverage and modeled completion

The strict files, `interchange_regional_mw.csv` and
`interchange_boundary_mw.csv`, have **4,287 complete hours**. They retain NaN
for the **129 hours** whose public point-sample gaps exceed the existing
600-second integration guard.

The separately named `*_applied_mw.csv` files contain all **4,416 hours**.
They keep every strict qualified value unchanged. For the 129 remaining
hours they carry the last reported schedule forward through a gap only when
the gap is bracketed by actual observations and is no longer than the
prespecified 3,600-second completion cap. The largest encountered gap was
3,000 seconds. No series extrapolates before or after its source observations.

Applied-file quality columns are:

- `all_primary_coverage_qualified`: all four regional series pass the strict
  600-second coverage guard.
- `applied_schedule_available`: all eight boundary injections can be formed.
- `schedule_imputed`: at least one channel required the modeled gap hold.
- `maximum_bracketing_gap_seconds`: largest source gap among the four channels.
- `uncovered_seconds`: maximum per-channel seconds in the hour that lack
  strict coverage; this is not summed across channels.
- `total_s11_scheduled_import_mw`: signed sum of the four S11 regional channels.

The complete series should therefore be described as **modeled applied
interchange with 129 flagged gap-completed hours**, not as 4,416 fully observed
hourly dispatches.

## Temporal and source assumptions

The hour is `[timestamp_utc, timestamp_utc + 1 hour)`. Point samples are
integrated using a time-weighted forward hold. Duplicate minute labels get
one mean value; the detailed channel file also retains lower/upper duplicate
bounds and alternate backward-hold and linear means for qualified hours.
These alternate methods are diagnostics, not methods selected to improve a
power-flow fit.

The hour-beginning interpretation follows the repository's existing empirical
P58B/P58C load-label audit. It does not establish NYISO's unpublished P-32
integration convention. The legacy P-32 header says `Flow (MWH)`; the existing
project interpretation treats these schedule values as MW without an energy
conversion.

`sources/interchange/` contains 190 consumed daily CSVs and their provenance
JSON files: 184 days within the six load months, plus the first day of each
following month to bracket the final hour. `interchange_source_manifest.csv`
records official monthly archive URLs, original archive SHA-256 hashes,
member names, packaged CSV hashes, and source IDs. Detailed hourly rows link
to these IDs. The downloaded next-month records close all month-end brackets.

## Scope and files

`interchange_hourly_channels.csv` retains the four primary and seven
supplemental channels, their Point IDs, strict and applied values, duplicate
uncertainty, source IDs, and quality. The supplemental `HQ_CEDARS`,
`HQ_IMPORT_EXPORT`, `NPX_CSC`, `NPX_1385`, `PJM_NEPTUNE`, `PJM_VFT`, and
`PJM_HTP` schedules are **diagnostic only**. They are not injected or
automatically added to the four regional channels because S11 has no explicit
representation for all those ties and aggregate overlap is unresolved.
Consequently, the four-channel total is S11's modeled boundary scope and is
not claimed to be the complete statewide net-import total.

`interchange_mapping.csv` gives the eight boundary identities and bus weights.
`interchange_quality.json` records the extraction policy and per-channel
coverage. `interchange_validation.json` records the fresh alignment and
accounting checks: identical load timestamps, all strict qualified values
unchanged, five temporal/identity/accounting tests passed, and zero difference
for 36 independent real-source comparisons against the existing integrator.
CSV rounding conserves the regional/boundary total to within 6.1e-9 MW.

To regenerate in the repository using the included cached raw sources:

```powershell
python scripts/s11_hourly_generation/extract_s11_hourly_interchange.py
python -m unittest discover -s scripts/s11_hourly_generation -p test_s11_hourly_interchange.py -v
```

The extractor also accepts `--load-profile`, `--output`, and `--cache` paths.
Packaged raw sources under the output path are used before the original
archive cache, so extraction can run offline once those files are present.
`--download-edges` permits retrieval from official NYISO monthly archives if
the required next-month source files are absent. Python requires NumPy and
pandas. Recreating these schedules does not establish AC feasibility; that
belongs to the companion generation/operating-point validation.
