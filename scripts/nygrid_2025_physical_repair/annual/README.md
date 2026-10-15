# Physical-repair annual replay

This producer uses the preserved current-model bundle, applies the frozen
`nyrepair_apply_case` repair, and runs the existing simultaneous compact
voltage/loss solver. It never overwrites the preceding annual delivery. The
comparison baseline is the current 8,170-hour equation-qualified result; the
source eligibility mask remains 8,651 of 8,760 UTC clock positions.

Run commands from the repository root:

```powershell
cd 'C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems'
```

The initial preparation authenticates and copies the baseline model and runtime
to `output/nygrid_2025_physical_repair/annual/baseline_bundle`. Existing copies
must match; they are not refreshed silently. Once that snapshot exists, replay
uses it directly and does not require rebuilding it after latest-model promotion.

```powershell
python scripts/nygrid_2025_physical_repair/annual/prepare_annual_contract.py
```

The candidate must already have a passing frozen
`output/nygrid_2025_physical_repair/candidate_receipt.json`. Its producer and
independent candidate validation are outside this annual directory. The schema
check solves one previously validated hour and confirms that the exact export
fields exist. Launch the annual replay only after candidate approval:

```powershell
& 'C:/Program Files/MATLAB/R2026a/bin/matlab.exe' -batch "addpath('scripts/nygrid_2025_physical_repair/annual');check_export_schema;"
& 'C:/Program Files/MATLAB/R2026a/bin/matlab.exe' -batch "addpath('scripts/nygrid_2025_physical_repair/annual');run_nyrepair_annual('physical_repair_v1',false);" *> 'output/nygrid_2025_physical_repair/annual/physical_repair_v1_matlab.log'
```

Choose a new run label for a new attempt. To resume the identical frozen attempt,
pass `true` as the second argument. Completed monthly checkpoints are verified
against their receipts before reuse. An incomplete monthly file without its
completion receipt is preserved and requires a new label. Schema, mapping,
candidate and export errors stop the campaign; they are not counted as ordinary
nonconvergence. The known `acLoss:NoAdmissibleState` rejection remains an explicit
attempt failure. No failed iterate is promoted to a valid prediction.

The driver saves `annual_axes.mat`, four candidate numeric templates in
`annual_network.mat`, monthly `profile_PF_2025_MM.mat` files, per-hour audits and
traces, all 8,760 quality rows, and final `annual_receipt.json`. The monthly files
include all generator P/Q values and finite P/Q/assumed-S capabilities, original
branch complex flows and three current columns, detailed and retained voltages,
served loads, loss budgets, topology masks and fixed-transfer outputs. Source,
solver, recovery, V/Q/S and full operating gates remain separate.

After completion, run both independent readbacks and then the scorer:

```powershell
python scripts/nygrid_2025_physical_repair/annual/validate_annual.py --run-dir output/nygrid_2025_physical_repair/annual/physical_repair_v1
python scripts/nygrid_2025_physical_repair/independent/review_annual_physics.py --run-dir output/nygrid_2025_physical_repair/annual/physical_repair_v1
python scripts/nygrid_2025_physical_repair/annual/score_annual.py --run-dir output/nygrid_2025_physical_repair/annual/physical_repair_v1
python scripts/nygrid_2025_physical_repair/annual/crosscheck_scoring.py --run-dir output/nygrid_2025_physical_repair/annual/physical_repair_v1
```

The input/accounting readback supports `--partial` for finished monthly
checkpoints and explicitly labels those receipts incomplete. The scorer requires
both full-year validation receipts. Its `comparison/` directory contains
`comparison_arrays.npz`, `comparison_cohort.csv`, `public_interface_metrics.csv`
and `scoring_receipt.json`. Primary rows use `model=candidate`,
`cohort=candidate_all_success`, `period=annual`, and
`convention=legacy_signed_literal_from`. The paired cohort compares candidate and
current baseline on identical successful hours; gained and lost hours remain
visible separately. All three inherited terminal conventions are retained.
The final crosscheck compares the scorer with the separate raw-physics
auditor's 28 independently calculated annual metric rows.

Public-flow comparisons divide aggregated model MW by the frozen gamma once.
Currents stay in model amperes, computed with actual voltage and the branch
voltage base. Equation qualification does not establish whole-system operating
feasibility, installed asset identity, or physical P-32 meter membership. The
producer hashes the candidate, baseline snapshot, numerical runtime and MATPOWER
sources before and after the run. Do not edit those frozen files during replay.
