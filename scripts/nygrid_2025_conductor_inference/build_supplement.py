"""Build an additive, hash-verified supplement without replacing v1 archives."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_conductor_inference'
DEST=ROOT/'deliverables/nygrid_rx_conductor_supplement_20261013'
FIXED=[
 'scripts/nygrid_2025_ac_system/branches/line_equivalents.py',
 'output/nygrid_2025_ac_system/engineering/thermal_conductors.csv',
 'output/nygrid_2025_ac_system/engineering/geometry_defaults.csv',
 'output/nygrid_2025_ac_system/branches/branch_assignments.csv',
 'output/nygrid_2025_acpf_profile_audit/structure/overhead_cable_classification_conflicts.csv']
REQUIRED=[
 'System Matpower Format/run_nygrid_2025_loss_consistent_acpf.m',
 'scripts/nygrid_2025_ac_loss_revision/core/ac_loss_prepare_case.m',
 'scripts/nygrid_2025_ac_system/thermal/ac_conductor_resistance.m',
 'scripts/nygrid_2025_ac_system/thermal/ac_dlr_limits.m',
 'scripts/nygrid_2025_dlr_handoff/runtime/setup_nygrid_2025_handoff.m',
 'output/nygrid_2025_ac_system/branches/engineering_overlay.mat']


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def rec(p):return dict(bytes=p.stat().st_size,sha256=sha(p))


def main():
    DEST.mkdir(parents=True,exist_ok=True)
    stage=DEST/'nygrid_rx_conductor_supplement_20261013'
    marker=stage/'.owned_supplement_stage'
    if stage.exists() and any(stage.iterdir()):assert marker.is_file(),'Refusing an unowned nonempty staging directory'
    stage.mkdir(exist_ok=True);marker.write_text('nygrid_rx_conductor_supplement_20261013\n')
    old=json.loads((stage/'SUPPLEMENT_MANIFEST.json').read_text()) if (stage/'SUPPLEMENT_MANIFEST.json').is_file() else {}
    old_payload=old.get('payload_files',{})
    old_controls={}
    if (stage/'SHA256SUMS.txt').is_file():
        for line in (stage/'SHA256SUMS.txt').read_text().splitlines():
            digest,name=line.split('  ',1);old_controls[name]=digest
    for name in ['install_supplement.py','SUPPLEMENT_MANIFEST.json','START_HERE.txt']:
        p=stage/name
        if p.exists():assert name in old_controls and sha(p)==old_controls[name],f'Modified or unowned staged control: {name}'
    payload=stage/'payload';payload.mkdir(exist_ok=True)
    paths=[ROOT/'NYGRID_2025_CONDUCTOR_INFERENCE.md']+[ROOT/p for p in FIXED]
    for base in [Path(__file__).parent,OUT]:
        paths += [p for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'
                  and not any(x in p.parts for x in ['supplement_validation','packaging'])
                  and p.name!='DELIVERY_MANIFEST.json']
    paths=sorted(set(paths));records={p.relative_to(ROOT).as_posix():rec(p) for p in paths}
    for p in paths:
        name=p.relative_to(ROOT);q=payload/name;q.parent.mkdir(parents=True,exist_ok=True)
        if q.exists() and rec(q)!=records[name.as_posix()]:
            assert name.as_posix() in old_payload and rec(q)==old_payload[name.as_posix()],f'Modified or unowned staged payload: {name}'
        shutil.copyfile(p,q);assert rec(q)==records[name.as_posix()]
    shutil.copyfile(Path(__file__).parent/'install_supplement.py',stage/'install_supplement.py')
    manifest=dict(schema_version=1,scope='Additive R/X-conditioned synthetic conductor policy, inference API and thermal-screen supplement',
        source_model_commit='51e424a139e0d0ec42fcbbb35749deaf119cffc2',
        previous_archives_replaced=False,electrical_model_or_dispatch_changed=False,
        requires_existing_files={name:rec(ROOT/name) for name in REQUIRED},payload_files=records,
        installer=rec(stage/'install_supplement.py'))
    (stage/'SUPPLEMENT_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    readme=r'''R/X-CONDITIONED CONDUCTOR SUPPLEMENT

This additive update supersedes the installed-circuit/source-keyed restriction
in the v1 handoff for SYNTHETIC overhead DLR studies. It does not change the
electrical case, R/X/B, dispatch or any v1 archive.

1. Extract this ZIP into a separate temporary directory.
2. Run from this supplement directory, using Python 3.11+:

   python install_supplement.py --target "C:\\research\\nygrid_dlr_runtime_20261013"

   The target may also be the complete research edition. Required base files
   and every payload are SHA-checked before any copying. An existing different
   file causes a refusal; no original file is overwritten.

3. Read NYGRID_2025_CONDUCTOR_INFERENCE.md in the target after installation.
4. In MATLAB after the v1 setup:

   addpath('scripts/nygrid_2025_conductor_inference');
   weather = table(25,.6096,90,1000,101325,'VariableNames', ...
       {'ambient_c','wind_m_s','wind_angle_deg','solar_w_m2','pressure_pa'});
   screen = screen_nygrid_2025_rx_thermal(8508,weather);

The old screen remains available for historical reproduction. Use the new API
for R/X-based synthetic eligibility. Its current operating flags still apply.
Conductor alternatives from infer_conductors.py are NOT silently substituted
into the model: choose one explicit scenario if exploring another realization.

R/X alone cannot uniquely identify conductor, circuit count, geometry or route.
Imported R/X and earlier engineered R/X remain separate provenance categories.
Catalog/geometry limits, non-overhead exclusions, numerical currents and
synthetic weather assumptions are documented in the addendum.
'''
    (stage/'START_HERE.txt').write_text(readme,encoding='utf-8')
    sums=[f"{r['sha256']}  payload/{name}" for name,r in records.items()]
    for name in ['install_supplement.py','SUPPLEMENT_MANIFEST.json','START_HERE.txt']:
        sums.append(f'{sha(stage/name)}  {name}')
    (stage/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    names=['payload/'+name for name in records]+['install_supplement.py','SUPPLEMENT_MANIFEST.json','START_HERE.txt','SHA256SUMS.txt']
    archive=DEST/'nygrid_rx_conductor_supplement_20261013.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for name in names:z.write(stage/name,stage.name+'/'+name)
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist())==len(set(z.namelist()))==len(names)
        for name in names:
            with z.open(stage.name+'/'+name) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==sha(stage/name)
    receipt=dict(passed=True,archive=dict(path=archive.relative_to(ROOT).as_posix(),**rec(archive)),
        payload_count=len(records),payload_bytes=sum(r['bytes'] for r in records.values()),
        every_archive_member_SHA_verified=True,electrical_parameters_changed=False,old_archives_unchanged=True,
        manifest=rec(stage/'SUPPLEMENT_MANIFEST.json'),payload_files=records,
        source_code={p.relative_to(ROOT).as_posix():rec(p) for p in [Path(__file__),Path(__file__).parent/'install_supplement.py']})
    out=OUT/'packaging';out.mkdir(exist_ok=True)
    (out/'supplement_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['payload_files','source_code']},indent=2))


if __name__=='__main__':main()
