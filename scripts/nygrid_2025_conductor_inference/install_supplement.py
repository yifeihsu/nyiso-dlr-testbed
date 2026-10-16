"""Install this additive conductor-inference supplement into a v1 handoff.

Run the copy located beside SUPPLEMENT_MANIFEST.json in the extracted ZIP.
All source and target identities are checked before any file is copied.
Existing different files are never overwritten.
"""
from pathlib import Path,PurePosixPath
import argparse
import hashlib
import json
import shutil


def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(1024*1024):h.update(b)
    return h.hexdigest()


def safe(base,name):
    p=PurePosixPath(name)
    assert name and not p.is_absolute() and '..' not in p.parts and ':' not in name and '\\' not in name
    result=(base/name).resolve();assert result.is_relative_to(base.resolve())
    return result


def main(target):
    source=Path(__file__).resolve().parent
    manifest=json.loads((source/'SUPPLEMENT_MANIFEST.json').read_text(encoding='utf-8'))
    assert digest(Path(__file__))==manifest['installer']['sha256'],'Installer differs from its package manifest'
    target=target.resolve();assert target.is_dir(),'Target must be an existing extracted handoff or compatible checkout'
    for name,r in manifest['requires_existing_files'].items():
        p=safe(target,name)
        assert p.is_file() and digest(p)==r['sha256'],f'Incompatible or missing base file: {name}'
    plan=[];same=0
    for name,r in manifest['payload_files'].items():
        p=safe(source/'payload',name);q=safe(target,name)
        assert p.is_file() and p.stat().st_size==r['bytes'] and digest(p)==r['sha256'],f'Changed supplement payload: {name}'
        if q.exists():
            assert q.is_file() and digest(q)==r['sha256'],f'Existing different file would be overwritten: {name}'
            same+=1
        else:plan.append((p,q))
    before={name:digest(safe(target,name)) for name in manifest['requires_existing_files']}
    for source_file,target_file in plan:
        target_file.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source_file,target_file)
    for name,r in manifest['payload_files'].items():assert digest(safe(target,name))==r['sha256']
    assert before=={name:digest(safe(target,name)) for name in manifest['requires_existing_files']}
    report=dict(passed=True,installed_new_files=len(plan),already_identical_files=same,
        existing_base_files_preserved=len(before),electrical_parameters_modified=False,
        target=str(target),new_API='screen_nygrid_2025_rx_thermal',
        next_step="In MATLAB: addpath('scripts/nygrid_2025_conductor_inference'); use explicit weather.")
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--target',type=Path,required=True)
    main(p.parse_args().target)
