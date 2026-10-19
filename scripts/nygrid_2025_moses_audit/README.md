# Reproduce the Moses South diagnosis and confirmed hydro repair

Read [the diagnosis](../../NYGRID_2025_MOSES_SOUTH_DIAGNOSIS.md). Existing 2019
and 2025 source, dispatch, downstate and slim artifacts are frozen inputs to
this separate revision. None of their builders or numerical files is replaced.

For ordinary inspection, run `finalize_audit.py --verify`. To deliberately
rerun the audits, load flow and validation using the delivered corrected fleet,
run these commands from the repository root. They refresh only this revision's
audit and replay outputs:

```powershell
cd 'C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems'
$taskPython = '.\tmp\nygrid_2025_inputs_runtime_20261010\Scripts\python.exe'
& $taskPython scripts/nygrid_2025_moses_audit/generation_audit.py
& $taskPython scripts/nygrid_2025_moses_audit/exchange_audit.py --offline
& $taskPython scripts/nygrid_2025_moses_audit/mapping_audit.py
& $taskPython scripts/nygrid_2025_moses_audit/audit_balance.py
& $taskPython -m unittest discover -s scripts/nygrid_2025_moses_audit -p 'test_*.py' -v
& $taskPython scripts/nygrid_2025_moses_audit/replay_corrections.py
& $taskPython scripts/nygrid_2025_moses_audit/validate_replays.py
matlab -batch "addpath('scripts/nygrid_2025_moses_audit'); validate_matlab_moses;"
& $taskPython scripts/nygrid_2025_moses_audit/build_figures.py
& $taskPython scripts/nygrid_2025_moses_audit/finalize_audit.py
```

The audit scripts require NumPy, SciPy, pandas, openpyxl and the existing PDF
extraction libraries in the isolated research runtime. MATLAB/MATPOWER are
needed only for the independent MATLAB validation. The source manifests name
the precise frozen Gold Book, EIA workbook and existing per-unit data. P34 raw
archives and extraction receipts are retained under the new exchange folder;
`--offline` refuses missing or changed cached archives. Refresh public-source
downloads only as a separately reviewed source update.

The fleet repair builder refuses to overwrite an existing fleet. To independently
reconstruct it from the frozen original fleet and the curated primary-source
crosswalk, choose a fresh directory:

```powershell
& $taskPython scripts/nygrid_2025_moses_audit/repair_fleet_mapping.py --output tmp/nygrid_2025_moses_fleet_check
```

Compare the resulting fleet, bounds, location ledgers and parent files with
`output/nygrid_2025_moses_audit/corrected/fleet`. The saved
`corrected/fleet/rebuild_verification.json` documents an exact independent
eight-file reconstruction. Creation times and checkout IDs in receipts are
expected to differ across rebuilds. The main replay intentionally consumes the
delivered corrected fleet, with its recorded hashes.

The correction changes only confirmed plant zone/location metadata and native
generator terminals. Capacity, availability, output, objective weights and
the global balance target are unchanged, so the previous dispatch remains
the bounded optimum. The prior arrays are reused by reference, not refitted.
Corrected load flow is freshly solved for every qualified hour.

`replay_corrections.py` saves dated and year-end variants for a reproduced
baseline, the confirmed hydro repair, and two explicitly unpromoted P34 sign
diagnostics. Scoring runs afterward and reads internal interface observations
only then. `--score-only` rescans saved replay hashes and regenerates metrics
without a new numerical solve. Both own and common-PAR-qualified cohorts are
reported; each contains the same 8,663 hours in this delivery.

`dc_control.py` computes an aggregate branch phase offset to reproduce an
independently supplied external flow while preserving nodal injections. Its
offset is not actual physical tap telemetry. The sign and physical control
limits remain unqualified. Those diagnostics are saved for investigation and
are rejected by the normal corrected-case loader.

The preferred confirmed loader is
`npcc_nygrid_2025_moses_corrected_dc(hour_index)`. Use the existing
`npcc_nygrid_2025_slim_interfaces` accessor after a successful `rundcpf`.
All 140 original buses plus eight added transmission buses remain.

After an intentional rebuild and successful validation, run
`finalize_audit.py` without `--verify` to update the exact-byte manifest.
Ordinary inspection should use `--verify`.
