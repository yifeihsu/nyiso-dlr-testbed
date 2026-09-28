"""Document and bundle aligned S11 loads, modeled dispatch, and interchange."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'output/s11_hourly_generation'
DEST = ROOT / 'output/s11_aligned_operating_handoff'
PACKAGE = 'S11_aligned_load_generation_interchange'


def boolean(series):
    return series.astype(str).str.lower().isin(['true', '1'])


def guide(summary, validation):
    good = summary['valid_hours']
    bad = summary['invalid_requested_hours']
    return f'''# S11 aligned load, generation, and interchange package

This research dataset contains the same **4,416 hourly timestamps** for
49-bus S11 loads, eight external schedule injections, and modeled generator
dispatch. It covers January, April, and July of 2019 and 2025, as six separate
complete monthly segments. Missing months and years are not interpolated.

**Usable AC operating points: {good:,} of 4,416 hours.** The remaining
**{bad:,} hours are explicitly unverified** under the fixed S11 model and
declared solver/commitment policy. Their dispatch/voltage arrays are NaN;
they are not filled with unconverged solutions. The load and interchange
inputs still exist for those timestamps. This is not a fully validated
4,416-hour operating trajectory or a mathematical infeasibility certificate.

## Ready-to-use files

Extract the ZIP and work from its `{PACKAGE}` folder. Relative folder paths
match the original project so the included scripts can find their inputs.

`output/s11_hourly_load_profiles/` contains the previously delivered load
CSV/MAT data, mapping, and validation. Its older README describes the earlier
load-only handoff; the new hourly generation ledger gives the current operating
coverage for this companion. `output/s11_hourly_generation/` contains:

| File | Meaning |
|---|---|
| `s11_hourly_operating_profiles.mat` | `operating` struct with generator/control P, Q, voltage setpoint, status, solved bus voltage/angle/type, identities, times, and validity flags |
| `gen_pg_mw.csv` | Active injections for all 49 generator/control rows, including eight external schedules |
| `gen_qg_mvar.csv` | Solved/scheduled generator and control reactive injections, MVAr |
| `gen_vg_pu.csv`, `gen_status.csv` | Per-hour setpoints and binary modeled aggregate status |
| `generator_mapping.csv` | Stable IDs, bus IDs, device roles, fuel/type identity, and original capability limits |
| `interchange_boundary_applied_mw.csv` | Complete modeled eight-boundary schedules used by dispatch |
| `interchange_boundary_mw.csv` | Strict source-derived schedules; unqualified hours remain NaN |
| `interchange_regional_applied_mw.csv` | Four regional public schedule means before spatial allocation |
| `interchange_mapping.csv` | Regional-channel to boundary-bus shares and sign convention |
| `hourly_validation.csv` | All hours with validity, failure reason, generation/import totals, offline rows, and electrical checks |
| `usable_hours.csv`, `unverified_hours.csv` | Explicit selections with one-based hour indices |
| `coverage_summary.csv` | Valid/unverified counts and modeled schedule completion by month |
| `generation_summary.json`, `independent_generation_validation.json` | Generation campaign and independent AC/serialization checks |
| `failure_analysis.json`, `initial_hourly_validation.csv`, `retry_before.mat` | Failure patterns and the initial/retry audit trail |
| `interchange_README.md`, `interchange_quality.json` | Source coverage, temporal assumptions, and schedule interpretation |
| `sources/interchange/` | All 190 consumed public daily CSVs with provenance |

CSV matrices are **hour by device**. Generation CSVs have six metadata columns
(three timestamp fields and three validity/source flags), then `gen_001` to
`gen_049`. MATLAB operating arrays are **device by hour**. The generator table
and bus table both have 49 rows but are different identities: multiple control
rows share a bus. Resolve devices using `generator_mapping.csv` or the included
MATLAB helper, not by assuming row index equals bus ID.

**Do not double-count imports:** rows 42-49 of `gen_pg_mw.csv` already contain
the eight external schedule injections. Sum rows 1-41 for internal generation;
add interchange only if you have excluded those external rows.

## Generation model

These are **modeled research dispatches**, not historical generator telemetry
or reconstructed market outcomes. The saved S11 fleet/capability model is used
for both source vintages; it is not a vintage-specific plant inventory.

- There are 31 active-power aggregates, ten other source/control rows, and
  eight external equivalents. The ten include remote/reactive-only controls
  and the zero-P Marcy reference-Q provenance record.
- Each hour independently minimizes normalized squared active-dispatch
  movement from the saved S11 participation prior adjusted to net demand.
  This is a dispatch regularizer, not an economic cost model.
- At low net demand, eligible non-regulating, variable-Q aggregate blocks may
  be shut down in descending original PMIN order. The bounded fallback tries
  additional shutdowns and an alternate solver. This is not an optimized unit
  commitment; ramps, minimum up/down times, outages, and chronological storage
  energy constraints are not modeled. No ramp continuity is inferred across
  the six separate monthly segments.
- Every online aggregate retains its original P/Q limits. Fixed-Q records,
  zero-P provenance, network parameters, and GS/BS shunts are preserved.
  Only the seven original candidate buses can regulate voltage, with REF73.
- OPF chooses Q for variable-capability controls at PQ buses; their solved Q
  is then a fixed input during PF replay. The PV/REF controls regulate voltage.
- Each accepted hour passes standard and Q-limit-enforced AC PF, nodal power
  balance, generator P/Q bounds, voltage bounds, exact external P schedules,
  and the **five trusted physical branch ratings**. Other reduced-equivalent
  branch ratings are diagnostic; acceptance does not mean all 83 legacy
  RATE_A values are respected. No limit relaxation or restoration slack is used.

The initial campaign's accepted hours were retained. Initially rejected hours
were retried with tighter IPOPT tolerances and ordinary PF replay of the final
Q-limit control state, correctly preserving any PV-to-PQ conversion. The audit
files retain the earlier results. Reproduction uses the final solver settings;
small numerical differences do not change the declared validation tolerances.

Some unverified hours coincide with large northbound exports through the HQ
proxy at bus48. Representative diagnostics saturated northern aggregate P/Q
capabilities. The ledger is authoritative for each hour; solver failure alone
does not prove mathematical infeasibility. The helper refuses unverified hours.

## Interchange and timing

The source channels are public **SCH schedule point samples**, not measured
actual interchange. Four channels (HQ, New England, Ontario, PJM) are mapped to
the existing eight S11 boundary equivalents. Positive means import into NY.
Supplemental named ties remain diagnostic and are not unconditionally added;
the sum is the S11 modeled schedule scope, not complete statewide net imports.
External reactive exchange stays fixed at zero as an explicit S11 assumption.

Of 4,416 hours, **4,287** satisfy the strict 600-second bracketing-gap policy.
The other **129** use explicitly flagged forward holds across fully bracketed
gaps capped at 3,600 seconds (largest encountered gap: 3,000 seconds). Qualified
values are unchanged and no extrapolation is used. Both strict and applied
series are included; `schedule_imputed` identifies the completion.

The interchange mean is formed on `[timestamp, timestamp + 1 hour)`, following
the project's empirical load-label alignment. The NYISO P-32 integration
convention is not independently established. The original load labels, UTC
conversion, EST/EDT tags, and local offsets are retained. Duplicate public minute
labels use their mean; uncertainty bounds are retained in the channel table.

## MATLAB quick start

From the extracted package root:

```matlab
addpath('System Matpower Format', 'System Matpower Format/NY_Lite');
l = load('output/s11_hourly_load_profiles/s11_hourly_load_profiles.mat');
g = load('output/s11_hourly_generation/s11_hourly_operating_profiles.mat');
k = find(g.operating.valid, 1); % choose a validated hour
mpc = npcc_ny_lite_s11_dlr_pf_base;
[mpc, hour] = apply_s11_hourly_operating_profile(mpc, l.profile, g.operating, k);
disp(hour);
% With MATPOWER installed:
r = runpf(mpc, mpoption('verbose',0,'out.all',0,'pf.enforce_q_lims',1));
```

The helper maps bus and compound generator identities, preserves internal
capabilities and network data, and applies the exact external schedule bounds.
Applying data requires MATLAB; rerunning PF requires MATPOWER. Generated data
were checked with MATLAB R2026a, MATPOWER, and IPOPT with a MIPS fallback.
Those runtimes/solvers are not bundled. Other runtime versions were not tested.

## Verification and reproduction

Python with NumPy, SciPy, and pandas:

```text
python scripts/s11_hourly_generation/verify_s11_hourly_generation.py
python scripts/s11_hourly_generation/test_s11_hourly_interchange.py
```

The independent verifier constructs admittance matrices separately and checks
the delivered voltages/injections, limits, timestamps, source schedules, and
CSV/MAT agreement. Current maximum accepted-hour nodal mismatch:
**{validation.get('maximum_ac_nodal_mismatch_mva', 'see validation JSON')} MVA**.

Re-extract schedules from the bundled raw files, without downloads:

```text
python scripts/s11_hourly_generation/extract_s11_hourly_interchange.py
```

Recompute modeled dispatch (requires MATPOWER and the stated solvers):

```matlab
addpath('scripts/s11_hourly_generation');
build_s11_hourly_generation(struct('worker_count',4));
test_apply_s11_hourly_operating_profile;
```

Parallel Computing Toolbox is optional; the builder falls back to a serial
run. Rebuilding changes outputs, so rerun the independent verifier afterward.
Its JSON is printed to stdout rather than automatically replacing saved reports.
`PACKAGE_MANIFEST.json` and `PACKAGE_CONTENTS.csv` identify the delivered files.
'''


def main():
    summary = json.loads((DATA / 'generation_summary.json').read_text())
    validation = json.loads((DATA / 'independent_generation_validation.json').read_text())
    if summary['requested_hours'] != 4416 or summary['not_run_hours'] != 0:
        raise ValueError('Do not package an unfinished campaign')
    if not validation['passed']:
        raise ValueError('Independent generation validation did not pass')
    ledger = pd.read_csv(DATA / 'hourly_validation.csv', keep_default_na=False)
    ledger.insert(0, 'hour_index', np.arange(1, len(ledger) + 1))
    valid = boolean(ledger.generation_valid)
    if int(valid.sum()) != summary['valid_hours']:
        raise ValueError('Summary and ledger disagree')
    for name, selected in [('usable_hours', valid), ('unverified_hours', ~valid)]:
        ledger.loc[selected].to_csv(DATA / f'{name}.csv', index=False, lineterminator='\n')
    month = ledger.timestamp_local.str[:7]
    coverage = pd.DataFrame({'month':month, 'hours':1, 'ac_verified_hours':valid.astype(int),
        'ac_unverified_hours':(~valid).astype(int),
        'gap_completed_interchange_hours':boolean(ledger.interchange_gap_completed).astype(int)})
    coverage = coverage.groupby('month',as_index=False).sum()
    coverage.to_csv(DATA / 'coverage_summary.csv',index=False,lineterminator='\n')
    boundary = pd.read_csv(DATA / 'interchange_boundary_applied_mw.csv')
    failed_hq = boundary.loc[~valid,'HQ_NY_MOSES']
    failure = {'unverified_hours':int((~valid).sum()),
        'status_counts':ledger.loc[~valid,'status'].value_counts().to_dict(),
        'unverified_hours_by_month':month[~valid].value_counts().sort_index().to_dict(),
        'unverified_hours_with_hq_export':int((failed_hq<0).sum()),
        'unverified_hq_schedule_min_mw':float(failed_hq.min()),
        'unverified_hq_schedule_max_mw':float(failed_hq.max()),
        'unverified_gap_completed_hours':int(boolean(boundary.loc[~valid,'schedule_imputed']).sum()),
        'mathematical_infeasibility_proven':False,
        'interpretation':'All listed operating points remain unverified under the fixed S11 model and declared bounded solver/commitment attempts.'}
    (DATA/'failure_analysis.json').write_text(json.dumps(failure,indent=2)+'\n',encoding='utf-8',newline='\n')
    readme = guide(summary, validation)
    (DATA / 'README.md').write_text(readme,encoding='utf-8',newline='\n')

    old = ROOT / 'scripts/s11_hourly_load_profiles/package_s11_hourly_load_profiles.py'
    spec = importlib.util.spec_from_file_location('s11_load_pack',old)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paths = set(module.payload_paths())
    paths.update(p.relative_to(ROOT) for p in DATA.rglob('*') if p.is_file())
    paths.update(p.relative_to(ROOT) for p in (ROOT/'scripts/s11_hourly_generation').iterdir()
                 if p.suffix in {'.m','.py'})
    paths.update(Path('System Matpower Format/NY_Lite')/name for name in (
        'apply_s11_hourly_operating_profile.m','s11_physical_circuit_map.csv',
        'nyiso_public_external_interface_map.m'))
    paths.add(Path('System Matpower Format/npcc_ny_lite_s11_dlr_pf_solution.m'))
    paths = sorted(paths)
    contents = io.StringIO(newline='')
    writer = csv.writer(contents,lineterminator='\n')
    writer.writerow(['relative_path','bytes'])
    writer.writerows((p.as_posix(),(ROOT/p).stat().st_size) for p in paths)
    manifest = {'package':PACKAGE,'aligned_hours':4416,'ac_verified_hours':int(valid.sum()),
        'ac_unverified_hours':int((~valid).sum()),'interchange_gap_completed_hours':129,
        'dispatch_is_observed':False,'payload_file_count':len(paths),
        'load_dataset_commit':subprocess.check_output(['git','log','-1','--format=%H','--',
            'output/s11_hourly_load_profiles'],cwd=ROOT,text=True).strip()}
    DEST.mkdir(parents=True,exist_ok=True)
    archive = DEST/f'{PACKAGE}.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in paths:
            if p.is_absolute() or not (ROOT/p).resolve().is_relative_to(ROOT):
                raise ValueError('Unsafe archive path')
            z.write(ROOT/p,f'{PACKAGE}/{p.as_posix()}')
        z.writestr(f'{PACKAGE}/README.md',readme)
        z.writestr(f'{PACKAGE}/PACKAGE_MANIFEST.json',json.dumps(manifest,indent=2)+'\n')
        z.writestr(f'{PACKAGE}/PACKAGE_CONTENTS.csv',contents.getvalue())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None or len(z.namelist()) != len(paths)+3:
            raise ValueError('Archive verification failed')
        for p in paths:
            if z.read(f'{PACKAGE}/{p.as_posix()}') != (ROOT/p).read_bytes():
                raise ValueError(f'Changed archive member: {p}')
    receipt = {**manifest,'archive_file_count':len(paths)+3,'zip_bytes':archive.stat().st_size,
        'zip_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'zip_crc_and_payload_equality_passed':True}
    (DEST/'README.md').write_text(readme,encoding='utf-8',newline='\n')
    (DEST/'package_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(receipt,indent=2))


if __name__ == '__main__':
    main()
