"""Write current package instructions after the completed replay and map export."""
from pathlib import Path
import hashlib
import json
import os
import shutil

ROOT=Path(__file__).resolve().parents[3]
REPAIR=ROOT/'output/nygrid_2025_moses_repair'
OUT=REPAIR/'delivery'
OLD=ROOT/'output/nygrid_2025_latest_handoff'


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    annual=REPAIR/'annual'/os.environ.get('NYGRID_REPAIR_RUN_LABEL','moses_repair_v1')
    ar=read(annual/'annual_receipt.json');score=read(annual/'comparison/scoring_receipt.json')
    model=read(REPAIR/'model/model_receipt.json');runtime=read(OUT/'validation/runtime_validation_receipt.json')
    assert ar['completed'] and score['passed'] and runtime['passed']
    docs=OUT/'docs';docs.mkdir(exist_ok=True)
    for name in ['THIRD_PARTY_NOTICES.md','MATPOWER_RUNTIME_SUBSET_NOTICE.txt']:
        shutil.copyfile(OLD/'docs'/name,docs/name)
    dictionary=(OLD/'docs/DATA_DICTIONARY.md').read_text(encoding='utf-8').replace('current released-equivalent, boundary-loss-consistent','current physically corrected, boundary-loss-consistent')
    dictionary = dictionary.replace('1,464','1,466').replace('1464','1466')
    dictionary = dictionary.replace('28-entry finite external capability vector','29-entry finite external capability vector')
    dictionary = dictionary.replace('Rows 1–1436','Rows 1–1436 and 1465')
    dictionary = dictionary.replace('Remaining 28 rows','Rows 1437–1464 and 1466')
    dictionary = dictionary.replace('including the fixed HQ row; they are not 28 observed physical generating units','including the fixed HQ and PV20 rows; only 27 rows participate in loss balancing')
    dictionary = dictionary.replace('Native and HQ active generation remain fixed.','Native and HQ active generation and PV20 active/reactive injection remain fixed.')
    dictionary+="""
## Moses repair metadata and inputs

`model.source_model_commit` identifies the preserved source-code baseline.
`model.moses_source_repair` and the new candidate receipt identify this repair.
The hourly profile shards change: 1,465 is the additional native St Lawrence
unit 21 and 1,466 is the PV20 fixed-PQ boundary row. Existing row IDs remain
stable. There are 1,437 native rows, 27 regional loss participants, one fixed
signed HQ row and one fixed-PQ PV20 row.

PV20 uses P34 PTID 325270 at bus 49, positive import to New York. Its Q is
fixed to zero. Subtracting that P from the existing nine ISONE injection rows
preserves aggregate ISONE exchange. Its loss share is zero; a positive external
group code does not imply loss participation. Sand Bar and Plattsburgh meter
equality is not certified. South Hero load, intervening losses and historical
2025 sign continuity remain disclosed uncertainties.

The appended PV20 `external.capability_proxy_MW` entry is a zero sentinel.
The loader sets its hourly capability to absolute PG, Q limits to zero and
apparent-power capability to absolute PG. It does not represent a zero-capacity
physical asset. Fixed signed Pmin/Pmax hold the scheduled injection.

The native hydro reconstruction preserves the existing reconciled hourly HY
total and pumped-storage profiles, while conserving EIA 2694 monthly energy
across all 8,760 physical hours. The 109 source-excluded hours retain latent
energy and remain excluded. Unit 21 is admitted in January-February and unit
26 in March-December; all other St Lawrence unit IDs retain their prior rows.
The 855 MW plant bound is an engineering nameplate constraint, not an observed
hourly availability series. `analysis/generation/` contains the full-year,
monthly, latent-hour, unit-admission and sensitivity ledgers.

Inherited `model.physical_repair` metadata describes the prior parent 41 and
185/195 repair. The Moses repair keeps those network R/X/B and fixed shunts.
`userdata.ac_sections.reactor_BS_delta_all_buses` remains aligned with
`reactor_BS_bus_ids`; the original-axis view remains `reactor_BS_delta`.
Profiles are not byte-identical to the prior delivery. No interface residual
selects the generation projection, boundary sign or network parameters.
"""
    (docs/'DATA_DICTIONARY.md').write_text(dictionary,encoding='utf-8')
    text=f'''# Corrected NYgrid 2025 model for DLR research

This package contains the corrected 148-bus AC model, four effective-date
states, corrected hydro and PV20 operating inputs, exact detailed-current recovery and
an R/X-conditioned synthetic conductor screen. Open `map/network_map.html` in
a browser for the offline network, zonal data and annual interface flows.
Read `NYGRID_2025_MOSES_REPAIR_MODEL_STRUCTURE.docx` for the current model
and `DATA_DICTIONARY.md` for axes, units and qualification flags.

The completed fresh annual replay retained all 8,760 timestamps and attempted
all 8,651 source-eligible hours. {ar['policy_equation_qualified_hours']:,} hours
passed the AC equation and loss-accounting gates;
{ar['VQ_and_generator_assumption_qualified_hours']:,} passed the joint voltage
and generator assumptions; {ar['full_operating_qualified_hours']:,} passed the
full declared operating gate. These gates are separate. The package does not
claim installed facility ratings or a feasible historical dispatch.

## Setup and run

Use MATLAB with JVM support. The included numerical vendor subset is MATPOWER
8.1; validation used MATLAB R2026a. Extract this ZIP and change MATLAB's current
directory to the folder containing this file. Use a fresh MATLAB session when
switching between package versions.

```matlab
addpath(fullfile(pwd, 'runtime'));
env = setup_nygrid_latest(pwd);
mpc = load_nygrid_latest(8508);
[result, audit, detailed, allocation] = run_nygrid_latest_acpf(8508);
assert(result.success && audit.loss_allocation_gate);
```

`result` contains the retained network and recovered currents. `detailed`
contains the recovered detailed solution. Always inspect the separate audit
flags before interpreting an operating point. The callable runtime uses the
compiled corrected templates and does not invoke the original model builders.

```matlab
weather = table(25, 0.6096, 90, 1000, 101325, ...
    'VariableNames', {{'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'}});
cached = struct('full', detailed, 'audit', audit, 'allocation', allocation);
screen = screen_nygrid_latest_dlr(cached, weather);
check = smoke_nygrid_latest(fullfile(pwd, 'runs', 'smoke'));
assert(check.passed);
```

The thermal screen needs explicit weather and preserves the electrical
solution. It is a one-way synthetic conductor calculation with no OPF or
temperature-feedback solve. MATLAB is not included. Optional Python verifies
package integrity using only its standard library:

```text
python verify_package.py --root .
```

## What changed

St Lawrence monthly EIA net generation is conserved over the entire year,
including explicit latent energy on the 109 excluded hours. Dated unit
admission keeps 15 active 57 MW units each month. Conventional hydro is
redistributed within original bounds while hourly reconciled hydro totals,
pumped storage and other fuel profiles remain fixed.

A new fixed-PQ PV20 input uses Sand Bar P34 PTID 325270 at bus 49, with the
same P removed from existing ISONE injections to preserve aggregate exchange.
Q is assumed zero. Sand Bar is a proxy for the physical Plattsburgh gate;
South Hero load, intervening losses and the 2025 sign convention are not
independently measured. The physical seven-term Moses boundary is documented
but not certified against the synthetic comparison operator.

The parent 41 and 185/195 network corrections are inherited unchanged. Gross
load, other fuel profiles, HQ and Ontario PAR inputs, clock, scale, source
mask and original comparison operators are preserved. Both hourly profile
files change. Source baseline commit: `{model['source_model_commit']}`.
Current static model SHA-256: `{model['model_file']['sha256']}`.
Candidate hashes are recorded under `verification/`; source-policy receipts
and ledgers are under `analysis/generation/` and `analysis/boundary/`.

## Map and evidence

The map contains all 8,760 hours and switches dated topology automatically.
It displays model MW by default; the public-scale option divides aggregate
power by the fixed gamma. Failed or source-excluded solved flows remain null.
Gross load, prescribed native generation and fixed transfers use the source
mask. Coordinates are qualified source anchors and schematic connections,
not a reconstruction of transmission routes or physical interface meters.

`verification/` includes the frozen candidate, annual, scoring, runtime and
map receipts. `model/structure/` contains exact bus, branch, generator and
transfer ledgers. `analysis/` contains the annual hour-quality and public
interface comparison tables plus the generation and boundary source policies.
`sources/` contains primary evidence and extraction receipts. The
`SOURCE_PATH_INDEX.json` maps original paths retained in frozen receipts to
their portable counterparts. Historical authoring inputs not included in the
package remain provenance references. Full monthly solve artifacts are retained
in the research checkout and are not required by this portable runtime.
'''
    (docs/'START_HERE.md').write_text(text,encoding='utf-8')
    print(json.dumps(dict(passed=True,docs=str(docs),qualified=ar['policy_equation_qualified_hours'])))


if __name__=='__main__':main()
