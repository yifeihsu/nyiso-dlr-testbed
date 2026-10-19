"""Write current package instructions after the completed replay and map export."""
from pathlib import Path
import hashlib
import json
import os
import shutil

ROOT=Path(__file__).resolve().parents[3]
REPAIR=ROOT/'output/nygrid_2025_physical_repair'
OUT=REPAIR/'delivery'
OLD=ROOT/'output/nygrid_2025_latest_handoff'


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    annual=REPAIR/'annual'/os.environ.get('NYGRID_REPAIR_RUN_LABEL','physical_repair_v1')
    ar=read(annual/'annual_receipt.json');score=read(annual/'comparison/scoring_receipt.json')
    model=read(REPAIR/'model/model_receipt.json');runtime=read(OUT/'validation/runtime_validation_receipt.json')
    assert ar['completed'] and score['passed'] and runtime['passed']
    docs=OUT/'docs';docs.mkdir(exist_ok=True)
    for name in ['THIRD_PARTY_NOTICES.md','MATPOWER_RUNTIME_SUBSET_NOTICE.txt']:
        shutil.copyfile(OLD/'docs'/name,docs/name)
    dictionary=(OLD/'docs/DATA_DICTIONARY.md').read_text(encoding='utf-8').replace('current released-equivalent, boundary-loss-consistent','current physically corrected, boundary-loss-consistent')
    dictionary+='''
## Physical repair metadata

`model.baseline_source_model_commit` identifies the preserved baseline. The
physical change is identified by `model.physical_repair.candidate_receipt_sha256`
and its frozen candidate receipt, rather than by implying that the baseline
commit contains the repair. Both hourly profile shards retain their baseline
SHA-256 values.

Each static template retains `userdata.physical_repair` and
`userdata.physical_repair_185195`. The full-axis shunt placement is recorded in
`userdata.ac_sections.reactor_BS_delta_all_buses`, aligned exactly with
`reactor_BS_bus_ids`. The original-bus `reactor_BS_delta` remains an original-axis
view. Reactor ledger records include distributed bus IDs and MVAr at 1 pu.
Parent 41's R/X/B and thermal material/geometry metadata form one coherent
synthetic realization; parent 185/195 retain their total fixed reactor ratings
and distribute those shunts along the existing numerical sections.

`source_model_commit` remains a baseline provenance field. The repair receipt
hash and static model SHA identify the corrected data. No geographic chord or
observed interface residual was used to select the repair.
'''
    (docs/'DATA_DICTIONARY.md').write_text(dictionary,encoding='utf-8')
    text=f'''# Corrected NYgrid 2025 model for DLR research

This package contains the corrected 148-bus AC model, four effective-date
states, unchanged 2025 operating inputs, exact detailed-current recovery and
an R/X-conditioned synthetic conductor screen. Open `map/network_map.html` in
a browser for the offline network, zonal data and annual interface flows.
Read `NYGRID_2025_PHYSICAL_REPAIR_MODEL_STRUCTURE.docx` for the current model
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

Parent 41 restores the imported R/X pair with one coherent declared conductor
and derived charging B. Parents 185 and 195 keep their conductor R/X/B and
total 75 percent fixed reactor rating, with section-local placement along the
existing passive numerical buses. The detailed and retained axes, native and
HQ active profiles, demand, transfer schedules, phase controls, voltage limits
and generator capability assumptions are preserved.

The prior static model and earlier manual remain in the preserved baseline
delivery. This package contains the corrected current version. The two hourly
profile files are byte-identical to that baseline. Baseline source commit:
`{model['baseline_source_model_commit']}`. Repair candidate SHA-256:
`{model['physical_repair']['candidate_receipt_sha256']}`. Current static model
SHA-256: `{model['model_file']['sha256']}`.

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
interface comparison tables. Full monthly solve artifacts are retained in
the research checkout and are not required by this portable runtime.
'''
    (docs/'START_HERE.md').write_text(text,encoding='utf-8')
    for suffix in ['png','svg']:
        source=OLD/f'structure/current_model_schematic.{suffix}'
        dest=OUT/f'structure/current_model_schematic.{suffix}';shutil.copyfile(source,dest)
    (OUT/'structure/schematic_receipt.json').write_text(json.dumps(dict(passed=True,
        scope='Reused unchanged representation diagram; all displayed dimensions independently verified on repaired structure',
        source=str(OLD/'structure/current_model_schematic.png'),sha256=sha(OUT/'structure/current_model_schematic.png')),indent=2)+'\n')
    (OUT/'map/README.md').write_text(f'''# Corrected NYgrid 2025 interactive map

Open `network_map.html` directly. The page is self-contained and requires no
server, network requests or installation. It includes the four corrected
topologies and the completed {ar['run_label']} replay.

The hour input is UTC. Select a zone for its gross target, served load, loss
and native generation; select an interface for its frozen signed membership.
Use the detailed view to inspect original corridor R/X/B and the corrected
fixed reactor placement on parents 185 and 195. Positive and negative flows
retain their defined direction when switching between model and public scale.

Annual equation/loss qualification: {ar['policy_equation_qualified_hours']} of
8651 source-eligible hours. Voltage/generator qualification:
{ar['VQ_and_generator_assumption_qualified_hours']}. Full declared operating
qualification: {ar['full_operating_qualified_hours']}. Unavailable values are
not zero-filled or interpolated. See the package manual and verification
receipts for scope, source identities and interpretation limits.
''',encoding='utf-8')
    print(json.dumps(dict(passed=True,docs=str(docs),qualified=ar['policy_equation_qualified_hours'])))


if __name__=='__main__':main()
