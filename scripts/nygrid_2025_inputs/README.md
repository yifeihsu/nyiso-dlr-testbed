# Build the 2025 operating-input layer

Read [the scope and accounting policy](../../NYGRID_2025_OPERATING_INPUTS.md).
Use Python with NumPy, pandas, SciPy and openpyxl. The existing research Python
has the first three; this delivery created an isolated runtime that adds
openpyxl without changing the global environment. The observed versions are
saved in [runtime.json](../../output/nygrid_2025_inputs/validation/runtime.json).
MATLAB is only needed to check the input accessor; no power-flow solve is
claimed in this stage.

From PowerShell:

```powershell
cd "C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems"
$nygridPython = (Resolve-Path 'tmp/nygrid_2025_inputs_runtime_20261010/Scripts/python.exe').Path
& $nygridPython scripts/nygrid_2025_inputs/finalize_inputs.py --verify
& $nygridPython -m unittest discover -s scripts/nygrid_2025_inputs -p "test_*.py" -v
```

If that ignored runtime has not been created on the current checkout, first
run the following once with the research Python that supplies NumPy, pandas
and SciPy, then set `$nygridPython` as above:

```powershell
python -m venv --system-site-packages tmp/nygrid_2025_inputs_runtime_20261010
& 'tmp/nygrid_2025_inputs_runtime_20261010/Scripts/python.exe' -m pip install openpyxl==3.1.5
```

The source extractors write only their dedicated `load_source` and
`generation_source` directories. The compiler consumes both source stages
and the preserved full 2019 parent. To compile separately from delivered
evidence after those prerequisites exist:

```powershell
& $nygridPython scripts/nygrid_2025_inputs/build_operating_inputs.py --source-root output/nygrid_2025_inputs --output tmp/nygrid_2025_model_rebuild
& $nygridPython scripts/nygrid_2025_inputs/validate_inputs.py --model-dir tmp/nygrid_2025_model_rebuild --output-dir tmp/nygrid_2025_model_rebuild/validation
& $nygridPython scripts/nygrid_2025_inputs/compare_rebuild.py --rebuilt tmp/nygrid_2025_model_rebuild --report tmp/nygrid_2025_model_rebuild/rebuild_comparison.json
matlab -batch "addpath('scripts/nygrid_2025_inputs'); validate_matlab_inputs(fullfile(pwd,'tmp','nygrid_2025_model_rebuild'));"
```

Choose a new folder if that folder already contains a MAT build. Do not edit
frozen 2019 source tables, compact outputs, or existing numerical artifacts to
make a rebuild pass.

The model rebuild needs the pinned `Data/npcc.mat` and `Data/npcc_new.csv` under
the existing 2019 source checkout, plus the delivered full 2019 MAT. Restore
those prerequisites through the [2019 reproduction](../nygrid_2019/README.md)
if absent; the compiler checks the pinned source hashes.

The delivered source tables and raw NYISO/NRC archives can be inspected without
the large EPA/EIA caches. To regenerate the source stages themselves, the
commands used were:

```powershell
& $nygridPython scripts/nygrid_2025_inputs/load_sources.py --offline
& $nygridPython scripts/nygrid_2025_inputs/generation_priors.py --offline
```

These commands refresh their dedicated source-stage outputs. Preserve a copy
before using them to compare versions. Full generation-source regeneration
also requires the pinned EPA/EIA files in the existing ignored caches, listed
with URLs and hashes in
[source_manifest.csv](../../output/nygrid_2025_inputs/generation_source/source_manifest.csv),
and the existing verified identity extracts used by the source reader. Those
large caches are not needed to use the delivered priors or recompile the model
inputs. P63 uses preceding sample intervals; P32 uses forward holds; both keep
their coverage flags. No source-stage command applies gamma or fits an
internal-interface target.

After an intentional new delivery has passed the recorded checks, the
finalizer can refresh the delivery receipt. For ordinary inspection use its
`--verify` mode, which does not write files.
