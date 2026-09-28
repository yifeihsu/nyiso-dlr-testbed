"""Freeze this separate package only after source/replay verification passes."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_compact_2019'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    old=json.loads((ROOT/'output/nygrid_2019/verification_manifest.json').read_text())
    for item in old['files']:
        assert sha(ROOT/item['path'])==item['sha256'], f'Frozen source changed: {item["path"]}'
    selection=json.loads((ROOT/'output/nygrid_2019/best_snapshots/selection_manifest.json').read_text())
    for item in selection['artifacts']:
        p=ROOT/'output/nygrid_2019/best_snapshots'/item['path']
        assert sha(p)==item['sha256'], f'Prior selected artifact changed: {p}'
    nested=0
    for folder in [OUT/'compact',OUT/'ac_checkpoint']:
        for row in pd.read_csv(folder/'output_manifest.csv').itertuples():
            assert sha(folder/row.relative_path)==row.sha256, f'Nested evidence changed: {row.relative_path}'
            nested+=1
    verification=json.loads((OUT/'verification/independent_validation.json').read_text())
    assert verification['passed'] and verification['validation_gates']==188
    ac=pd.read_csv(OUT/'ac_checkpoint/summary.csv')
    assert len(ac)==3 and ac.bounded_AC_qualified.astype(bool).all()
    assert not ac.interface_objective_used.astype(bool).any()
    # The independent audit's exact schema is also retained verbatim as an
    # artifact; fail if any documented failed check exists.
    assert (OUT/'verification/independent_validation.md').is_file()
    changed=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).splitlines()
    unexpected=[x for x in changed if x!='.gitattributes' and not x.startswith('output/perform_comparison/workbook_build/node_modules/')]
    assert not unexpected, f'Unexpected changes to prior tracked files: {unexpected}'
    files=[ROOT/'.gitattributes',ROOT/'NYGRID_COMPACT_2019_COMPARISON.md']
    for directory in [ROOT/'scripts/nygrid_compact_2019',OUT]:
        files += [p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                  and p.name!='package_manifest.json' and p.suffix not in {'.pyc','.tmp'}]
    files=sorted(set(files))
    artifacts=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in files]
    assert all(x['bytes']<100_000_000 for x in artifacts)
    manifest=dict(package='matched_2019_compact_DC_and_separate_restored_fleet_AC',
                  original_annual_evidence_files_unchanged=len(old['files']),
                  original_snapshot_artifacts_unchanged=len(selection['artifacts']),
                  nested_output_hashes_checked=nested,
                  new_interface_parameter_fit=False,untouched_holdout=False,
                  preferred_2025_model_changed=False,marcy_DC_best_snapshots_AC_qualified=False,
                  separate_existing_network_AC_cases_qualified=3,
                  independent_validation_sha256=sha(OUT/'verification/independent_validation.json'),
                  base_git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  artifact_count=len(artifacts),artifacts=artifacts)
    (OUT/'package_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:v for k,v in manifest.items() if k!='artifacts'},indent=2))


if __name__=='__main__':
    main()
