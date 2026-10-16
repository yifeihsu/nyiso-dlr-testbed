# Rebuild the 2025 fleet and bounded dispatch

Read [the model report](../../NYGRID_2025_BOUNDED_DISPATCH.md) for the accepted
DC scope and unresolved interface discrepancies. No topology refinement or
internal-interface fitting occurs in this pipeline.

The checked environment is the isolated research runtime from the operating-
input build: Python with NumPy, pandas, SciPy and openpyxl. MATLAB R2026a with
MATPOWER 8.1 is used for independent loader replay.

```powershell
cd "C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems"
$nygridPython = (Resolve-Path 'tmp/nygrid_2025_inputs_runtime_20261010/Scripts/python.exe').Path
& $nygridPython scripts/nygrid_2025_dispatch/finalize_dispatch.py --verify
& $nygridPython -m unittest discover -s scripts/nygrid_2025_dispatch -p "test_*.py" -v
```

If the ignored runtime is absent, follow the setup commands in the
[operating-input README](../nygrid_2025_inputs/README.md). The delivered fleet
and prior arrays are sufficient to rebuild dispatch without downloading the
large original EPA/EIA sources.

To reconstruct into a **new folder**, preserving delivered results:

```powershell
& $nygridPython scripts/nygrid_2025_dispatch/build_dispatch.py --output tmp/nygrid_2025_dispatch_independent_run
& $nygridPython scripts/nygrid_2025_dispatch/validate_dispatch.py --dispatch-dir tmp/nygrid_2025_dispatch_independent_run --output-dir tmp/nygrid_2025_dispatch_independent_run/validation
matlab -batch "addpath('scripts/nygrid_2025_dispatch'); validate_matlab_dispatch(fullfile(pwd,'tmp','nygrid_2025_dispatch_independent_run'));"
& $nygridPython scripts/nygrid_2025_dispatch/compare_rebuild.py --rebuilt tmp/nygrid_2025_dispatch_independent_run --output tmp/nygrid_2025_dispatch_independent_run/rebuild_comparison.json
& $nygridPython scripts/nygrid_2025_dispatch/score_interfaces.py --folder tmp/nygrid_2025_dispatch_independent_run
```

Choose another new folder if that one already contains `dispatch.mat`; the
builder refuses to replace an existing numerical dispatch. Post-hoc scoring
is separate from reconstruction and never feeds back into its weights or
parameters.

With the pinned source dependencies available, rebuild fleet and priors into
separate new directories as follows:

```powershell
$nygridSourceCheck = Join-Path (Get-Location).ProviderPath 'tmp/nygrid_2025_dispatch_source_check'
& $nygridPython scripts/nygrid_2025_dispatch/build_fleet.py --out (Join-Path $nygridSourceCheck 'fleet')
& $nygridPython scripts/nygrid_2025_dispatch/build_dispatch_priors.py --fleet-folder (Join-Path $nygridSourceCheck 'fleet') --output (Join-Path $nygridSourceCheck 'priors')
```

Those builders require the versioned source dependencies in their manifests,
including the cached EIA workbooks for full fleet extraction and the preserved
2025 source priors for unit allocation. Parent identity files are saved under
`fleet/source_parent` with SHA-256 checks. Inspect their command options before
refreshing a source stage; preserve a separate version for comparisons. The
dispatch rebuild above deliberately uses the already verified delivered
fleet/priors unless `--source-root` is explicitly changed.
The `initial_pre_ba_filter`, `initial_pre_nj_native_extension` and
`archive_ny_state_only_20261010` directories are optional local intermediate
history, excluded from delivery and not required by clean reproduction.
The narrow verified NJ EPA extract and national facility metadata are
delivered with the priors; the original 171 MB NJ download remains an ignored
cache and is not required when those verified extracts are available.

The four annual files share exact hour/fleet axes:

| File | Main contents |
|---|---|
| `dispatch.mat` | Case template, final PG, gross bus loads, DC transfers, status and source identity |
| `dispatch_bounds.mat` | Active-power bounds and physical capacity references |
| `dispatch_priors.mat` | Preferred PG and quadratic weights |
| `dispatch_network.mat` | Branch flows, bus angles, inherited interface predictions |

Only `status_code=1` hours are usable DC snapshots. Code 0 means incomplete
source coverage; code 2 would mean insufficient admitted capacity. The
delivered run has 8,663 code-1, 97 code-0 and zero code-2 hours. The loader
never chooses a different hour or alters bounds to satisfy a request.
