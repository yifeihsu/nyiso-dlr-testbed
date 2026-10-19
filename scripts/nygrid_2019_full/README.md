# Reproduce the full 2019 NPCC DC baseline and synthetic thermal scenarios

Read [the model review and results](../../NYGRID_2019_DLR_REBUILD.md) first.
The full final-device network is a derived 140-bus counterpart of the paper's
reduced release. Its small, quantified flow differences remain in the evidence.
It is not an AC or installed-conductor qualification.

## Check the delivered baseline

The delivered numerical artifacts are complete. This command checks their
inputs/results, independently recounts thermal exposures, canonicalizes CSV
line endings, and refreshes the current delivery fingerprints:

```powershell
cd "C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems"
python scripts/nygrid_2019_full/finalize_evidence.py
```

The loader is [npcc_nygrid_2019_full_dc.m](../../System%20Matpower%20Format/npcc_nygrid_2019_full_dc.m).
Its input is a 1-based prepared local-hour index from 1 through 8760, with
4818 corresponding to July 20 at 17:00. It supplies DC power-flow inputs;
it omits stale economic costs/interface constraints. An optional second
argument selects a different artifact folder.

## Rebuild separately from the delivered evidence

The verified environment is MATLAB R2026a Update 3, MATPOWER 8.1 legacy core,
and Python with NumPy/SciPy. The pinned NYgrid/cache/reduction downloads and
four complete annual MAT/final-case CSV pairs under `output/nygrid_2019` are
required. To recreate those prerequisites, follow [the original reproduction](../nygrid_2019/README.md),
including source fetches, cache-equivalence checks, and annual runs. The new
workflow reuses its verified generation-allocation evidence; it does not
re-download independent generator observations.

Use a **new output folder** for each numerical rebuild. The sequence below
never overwrites `output/nygrid_2019_full_stage1`. If the example folder already
contains a prior build, choose another name consistently in every command.
`replay_full_year.py` refuses to replace existing full-year outputs.

```powershell
cd "C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems"
python scripts/nygrid_2019_full/prepare_capture.py --output tmp/nygrid_full_rebuild_check
matlab -batch "addpath('scripts/nygrid_2019_full'); capture_full_stages(fullfile(pwd,'tmp','nygrid_full_rebuild_check'));" -logfile "tmp/nygrid_full_rebuild_check/matlab_capture.log"
python scripts/nygrid_2019_full/replay_full_year.py --captures tmp/nygrid_full_rebuild_check/captured_stages.mat --output tmp/nygrid_full_rebuild_check
python scripts/nygrid_2019_full/build_branch_register.py --full-year tmp/nygrid_full_rebuild_check/full_year.mat --stage-capture tmp/nygrid_full_rebuild_check/captured_stages.mat --output-dir tmp/nygrid_full_rebuild_check
matlab -batch "addpath('scripts/nygrid_2019_full'); evidence_folder=fullfile(pwd,'tmp','nygrid_full_rebuild_check'); validate_full_loader(evidence_folder); run_dc_thermal_scenarios(evidence_folder);" -logfile "tmp/nygrid_full_rebuild_check/matlab_validation_thermal.log"
python scripts/nygrid_2019_full/finalize_evidence.py --output tmp/nygrid_full_rebuild_check
```

Preparation verifies 73 upstream, 73 cached, and 20 reduction-toolbox files.
Its isolated runtime hard-links data inputs; never edit those linked files.
Released `Result` writes stay in that runtime. Constructor instrumentation is
limited to a reversible function/output rename and two stage captures.
The annual stage rebuilds demand from source CSVs, restores the original
nuclear slack prior, and independently solves all 8,760 full pre-device, full
final-device, and reduced states. Source reconstruction and nodal balance must
pass; final full/reduced exact equivalence is separately reported false.

The thermal stage reuses the existing conductor/heat-balance library, runs its
physics/integration checks, and evaluates four constant synthetic weather
scenarios on the same 39 structural candidates. Its limits are nominal-voltage,
unity-power-factor DC proxies. No redispatch, observed hourly weather,
installed-conductor identification, or AC qualification is performed. Severe
exceedances remain visible rather than being removed by increasing assumed
parallel circuits.

The finalizer reproducibly creates `capture_validation_manifest.json`,
`delivery_checks.json`, and `delivery_manifest.json` after checking current
source receipts and results. The initial local `capture_artifact_manifest.json`
is a historical receipt and is not part of the delivered manifest. To use an
alternate completed build in MATLAB:

```matlab
addpath('System Matpower Format');
mpc = npcc_nygrid_2019_full_dc(4818, fullfile(pwd,'tmp','nygrid_full_rebuild_check'));
[result, success] = rundcpf(mpc, mpoption('verbose',0,'out.all',0,'exp.use_legacy_core',1));
```
