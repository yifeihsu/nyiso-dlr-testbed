# Full-NPCC Downstate refinement and paired 2025 replay

This workflow retains the frozen 2025 fleet/dispatch and the full modified-2019
NPCC backbone. It builds an algebraic identity control, historical station
detail, dated/year-end upgrades, optional asset placement, and a separate
NYES overlap-assumption scenario. Interface observations enter only the scoring
and independent reporting stages. No redispatch or parameter fitting occurs.

Use the repository-root [research report](../../NYGRID_2025_DOWNSTATE_REFINEMENT.md)
for results, scope and remaining physical uncertainties. Raw network templates
are construction inputs; use `npcc_nygrid_2025_downstate_dc` for hourly MATPOWER
cases with the correct generator bounds, load, DC schedules and reference bus.

## Load an existing qualified hour

From MATLAB with MATPOWER on the path:

```matlab
cd('C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems');
addpath('System Matpower Format');
mpc = npcc_nygrid_2025_downstate_dc(1, 'upgrades_dated');
[result, success] = rundcpf(mpc, mpoption('verbose', 0, 'out.all', 0));
```

The default variant is `upgrades_dated`, which preserves all baseline injection
landings. `assets_dated` applies the documented plant and partial-coverage load
mapping; it remains a spatial-allocation scenario. Other names are
`expanded_identity`, `source_detail_2019`, `upgrades_year_end`, `assets_year_end`,
and `nyes_assumption_year_end`. All variants reject the same 97 source-gap hours.
Year-end variants applied to earlier hours are counterfactuals.

## Rebuild without overwriting the delivered artifacts

The commands below use the existing task runtime (NumPy, SciPy, pandas,
matplotlib and openpyxl) and a new output directory. The frozen baseline and
primary source receipts must already be present. `audit_upgrade_sources.py`
acquires/verifies the public evidence separately; it is not needed to redownload
unchanged receipts for a numerical rebuild.

```powershell
cd 'C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems'
$taskPython = '.\tmp\nygrid_2025_inputs_runtime_20261010\Scripts\python.exe'
$taskRebuild = '.\tmp\nygrid_2025_downstate_rebuild_user'
if (Test-Path -LiteralPath $taskRebuild) { throw 'Choose a fresh rebuild directory' }
New-Item -ItemType Directory -Path "$taskRebuild\validation" | Out-Null
Copy-Item -LiteralPath '.\output\nygrid_2025_downstate\sources' -Destination "$taskRebuild\sources" -Recurse
Copy-Item -LiteralPath '.\output\nygrid_2025_downstate\validation\baseline_reference.json' -Destination "$taskRebuild\validation\baseline_reference.json"
& $taskPython scripts/nygrid_2025_downstate/build_network.py --output "$taskRebuild\network"
& $taskPython scripts/nygrid_2025_downstate/replay_refinement.py --folder $taskRebuild
& $taskPython scripts/nygrid_2025_downstate/score_refinement.py --folder $taskRebuild
& $taskPython scripts/nygrid_2025_downstate/validate_refinement.py --folder $taskRebuild
& $taskPython scripts/nygrid_2025_downstate/parameter_sensitivity.py --folder $taskRebuild
matlab -batch "addpath('scripts/nygrid_2025_downstate'); validate_matlab_refinement(fullfile(pwd,'tmp','nygrid_2025_downstate_rebuild_user'));"
```

Focused construction, chronology and adversarial-validation checks:

```powershell
& $taskPython -m unittest discover -s scripts/nygrid_2025_downstate -p 'test_*.py' -v
```

`finalize_refinement.py --verify` checks the delivered canonical evidence and
fingerprints. It intentionally refuses stale validation dependencies.

## Files and semantics

- `network/network_cases.mat`: common bus/branch axes, identity/source/project
  cases, conservative PD/QD allocation matrices and keyed generator landings.
- `network/*register.csv`: exact source rows, original aggregate replacement,
  numeric assumptions, load coverage and K-backbone continuity, plant landings,
  and commissioning chronology. Original rows are retained; replaced aggregate
  rows are inactive.
- `replay/*.mat`: seven sets of branch flows, angles and comparable interface
  predictions, with the same qualification mask and per-hour network-state key.
  Generation, bounds and DC schedules are referenced by hash from the immutable
  baseline instead of duplicating seven large input arrays.
- `comparison/`: before/after errors, monthly summaries, staged flow changes,
  hourly predictions, and PNG/PDF research figures.
- `sensitivity/`: assumed-X and fixed-PAR scenarios plus generation-only and
  load-only attribution; these are scenario ranges, not confidence intervals.
- `validation/`: independent construction/annual checks, MATPOWER snapshots,
  focused tests and reconstruction receipts.

All case values retain the frozen model scale `gamma = 0.30012075175285535`.
Comparison tables report public-equivalent MW (`model MW / gamma`). Neither
historical source detail nor a lower proxy error establishes an as-built 2025
network, AC feasibility, thermal ampacity, DLR readiness or certified physical
flowgate membership.
