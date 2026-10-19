"""Materialize and seal portable research packages without changing prior work.

Large archives/staging trees live in the ignored deliverables directory. The
inventory, archive hashes, code and handbook remain normal versioned artifacts.
"""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile

from verify_package import verify_root, verify_zip, safe_name

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_dlr_handoff'
BASELINE='8188cbec1172219a0414881121ad042b405a4044'
DEFAULT_RELEASE=ROOT/'deliverables/nygrid_2025_dlr_handoff_20261013'


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def direct(p,target=None,role='handoff_delivery'):
    return dict(source_path=str(p.resolve()),target=target or p.relative_to(ROOT).as_posix(),
                bytes=p.stat().st_size,sha256=sha(p),role=role)


def gather(kind):
    inventory=read(OUT/'package_inventory.json');assert inventory['source_head']==BASELINE
    bytarget={};aliases=[]
    def add(r):
        target=r.get('target',r.get('path'));safe_name(target)
        value=dict(r,target=target)
        if target in bytarget:
            assert bytarget[target]['sha256']==value['sha256'],f'Conflicting inputs: {target}'
        else:bytarget[target]=value
    if kind=='research':
        for r in inventory['files']:add(r)
    else:
        for r in inventory['default_runtime_data']['entries']:add(r)
        for r in inventory['files']:
            if r['path'].endswith('.md') and '/' not in r['path']:add(r)
    for file in ['runtime_code_closure.json','vendor_code_closure.json']:
        for r in read(OUT/'runtime_audit'/file)['entries']:add(r)
    # Every primary handbook link is available in both editions. Linked older
    # reports may refer onward to large evidence present only in research.
    for path in read(OUT/'handbook_build_receipt.json')['source_links'].values():
        matching=[r for r in inventory['files'] if r['path']==path]
        add(matching[0] if matching else direct(ROOT/path))
    if kind=='research':
        for r in inventory['curated_untracked_historical_sources']:
            candidates=[x for x in r.get('already_in_research_at_same_content',[]) if x in bytarget]
            if not candidates:candidates=[target for target,item in bytarget.items() if item['sha256']==r['sha256']]
            if candidates:target=candidates[0]
            else:
                target=r['recommended_target'];add(direct(ROOT/r['path'],target,'curated_historical_source_capture'))
            aliases.append(dict(original_reference=r['path'],packaged_path=target,sha256=r['sha256'],
                                original_receipts_not_rewritten=True))
        # Earlier Git text normalization changed some CSV byte hashes without
        # changing values. Retain both the committed primary file and the exact
        # receipt-era working bytes, named explicitly as a line-ending variant.
        for r in inventory['existing_worktree_differences']:
            if r.get('difference_kind')!='line_endings_only':continue
            target='source_archive/line_ending_variants/'+r['path']
            item=direct(ROOT/r['path'],target,'historical_receipt_line_ending_variant')
            assert item['sha256']==r['working_sha256'];add(item)
            aliases.append(dict(original_reference=r['path'],packaged_path=target,sha256=item['sha256'],
                                primary_committed_sha256=r['baseline_sha256'],difference='line_endings_only'))
    for r in inventory['external_references']:
        candidates=[target for target,item in bytarget.items() if item['sha256']==r['sha256']]
        aliases.append(dict(original_reference=r['original_path'],packaged_path=candidates[0] if candidates else None,
                            sha256=r['sha256'],role=r['role'],available_in_this_edition=bool(candidates)))
    # Exclude render PNGs/PDFs and package receipts to prevent self-inclusion
    # cycles. A final independent delivery receipt is shipped beside archives.
    for base in [ROOT/'scripts/nygrid_2025_dlr_handoff',OUT]:
        for p in base.rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts or p.suffix=='.pyc':continue
            rel=p.relative_to(OUT).as_posix() if p.is_relative_to(OUT) else ''
            if rel.startswith(('document_render/','package_receipts/','extracted_validation/')):continue
            if rel in ['DELIVERY_MANIFEST.json','final_delivery_review.json']:continue
            # Runtime edition does not include an annual rescorer's large
            # reference arrays. Its command documents the full-edition need.
            add(direct(p))
    for name in ['NYGRID_2025_DLR_HANDOFF.docx','NYGRID_2025_DLR_HANDOFF.md']:
        add(direct(ROOT/name))
    return bytarget,aliases,inventory


def start_text(kind):
    return f'''NYGRID 2025 DLR RESEARCH HANDOFF
Edition: {kind}
Model snapshot: {BASELINE}
Prepared: 2026-10-13

1. Read NYGRID_2025_DLR_HANDOFF.docx (or the matching Markdown file).
2. In MATLAB, change directory to this extracted package root, then run:

   addpath(fullfile(pwd,'scripts','nygrid_2025_dlr_handoff','runtime'));
   env = setup_nygrid_2025_handoff(pwd);
   check = smoke_nygrid_2025_handoff(fullfile(pwd,'runtime_results'));

3. Run a current hour:

   [r,audit,recovered,allocation] = run_nygrid_2025_loss_consistent_acpf(8508);

The accounting and current-recovery gates can pass while the physical operating
gate fails. No annual hour is fully V/Q/capability-qualified. This is a synthetic
research model. The new thermal screen is one-way; it is not joint electrothermal
optimization. The older run_nygrid_2025_ac_dlr function uses a separate model.

MATLAB with JVM is required and is not bundled. MATPOWER 8.1 code and notices are
under vendor/matpower8.1. Use the recorded version for reproducibility. Python
3.9+ suffices for the standalone integrity verifier; scientific re-scoring has
additional dependencies documented in its handoff wrapper.

Verify every sealed file with:
   python scripts/nygrid_2025_dlr_handoff/verify_package.py --root .

The runtime edition supports default dated PF and filtered thermal screening.
The research edition additionally includes the full selected historical corpus,
raw-source captures, annual arrays, alternate cases and evidence. Original raw
source rebuilding may require network services and optional tools. Historical
Git-dependent finalizers are preserved as provenance; use this package verifier
and the portable handoff scoring wrapper after relocation.

PACKAGE_MANIFEST.json records per-file hashes and SOURCE_PATH_ALIASES.json maps
selected historical references without changing their old receipts. New work
belongs in runtime_results or a new scenario namespace. Do not overwrite frozen
inputs or mistake earlier model-family results for current qualification.

The package grants no new blanket license. Preserve source attribution and all
third-party notices; MATLAB and optional external solvers are not redistributed.
'''


def build(kind,release,stage_only):
    records,aliases,inventory=gather(kind)
    stage=release/kind;stage.mkdir(parents=True,exist_ok=True)
    marker=stage/'.handoff_build_marker.json'
    if any(stage.iterdir()) and not marker.is_file():raise RuntimeError(f'Unowned nonempty staging directory: {stage}')
    if marker.is_file():assert read(marker)['source_model_commit']==BASELINE
    else:marker.write_text(json.dumps({'source_model_commit':BASELINE,'created_by':'build_packages.py'})+'\n')
    # Old generated manifests identify only files owned by this builder. Do not
    # remove user additions or recurse through arbitrary directories.
    previous=read(stage/'PACKAGE_MANIFEST.json')['files'] if (stage/'PACKAGE_MANIFEST.json').is_file() else {}
    generated={'START_HERE.txt','SOURCE_PATH_ALIASES.json','THIRD_PARTY_NOTICES.txt'}
    removed=[]
    for name in set(previous)-set(records)-generated:
        target=(stage/name).resolve();assert target.is_relative_to(stage.resolve())
        assert target.is_file() and sha(target)==previous[name]['sha256'],f'Changed previously packaged file: {name}'
        target.unlink();removed.append(name)
    for i,(name,r) in enumerate(sorted(records.items()),1):
        target=stage/name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.is_file() and target.stat().st_size==r['bytes'] and sha(target)==r['sha256']:continue
        if target.exists():
            assert name in previous and target.is_file() and sha(target)==previous[name]['sha256'],f'Changed or unowned staging target: {name}'
        source=Path(r.get('source_path',str(ROOT/r.get('path',name))))
        if source.is_file() and source.stat().st_size==r['bytes'] and sha(source)==r['sha256']:
            shutil.copyfile(source,target)
        else:
            assert r.get('git_blob'),f'Changed or missing input: {source}'
            with target.open('wb') as f:subprocess.run(['git','cat-file','blob',r['git_blob']],cwd=ROOT,stdout=f,check=True)
        assert target.stat().st_size==r['bytes'] and sha(target)==r['sha256'],name
        if i%500==0:print(f'{kind}: copied {i}/{len(records)} files',flush=True)
    for name in generated:
        target=stage/name
        if target.exists():
            assert name in previous and target.is_file() and sha(target)==previous[name]['sha256'],f'Changed or unowned generated staging target: {name}'
    (stage/'START_HERE.txt').write_text(start_text(kind),encoding='utf-8')
    (stage/'SOURCE_PATH_ALIASES.json').write_text(json.dumps({'source_model_commit':BASELINE,'aliases':aliases},indent=2)+'\n',encoding='utf-8')
    notices=['SOURCE AND THIRD PARTY NOTICES','',
             'This research handoff grants no new blanket license over its mixed code, data and source documents.',
             'Preserve original notices. MATLAB and optional proprietary or compiled solvers are not bundled.','']
    for item in inventory['sharing_and_license_observations']:
        notices.extend([item['component'],item['observation'],item['action'],''])
    notices.extend(['Bundled numerical runtime',
        'MATPOWER 8.1, MIPS, MP-Opt-Model and MP-Test code and their LICENSE/AUTHORS notices are retained under vendor/matpower8.1.',
        'The vendor subset excludes MATPOWER example/case data and compiled solvers. The project-specific compact kernel notice is retained.',''])
    (stage/'THIRD_PARTY_NOTICES.txt').write_text('\n'.join(notices),encoding='utf-8')
    files={name:dict(bytes=r['bytes'],sha256=r['sha256'],role=r.get('role',r.get('group','prior_research')))
           for name,r in sorted(records.items())}
    for name in sorted(generated):files[name]=dict(bytes=(stage/name).stat().st_size,sha256=sha(stage/name),role='package_navigation')
    manifest=dict(schema_version=1,package_kind=kind,source_model_commit=BASELINE,
        source_model_branch='codex/s13-phase1b-upny-coned',prepared_date='2026-10-13',
        model_status='conditional_synthetic_research; latest_annual_joint_operating_qualification_zero',
        includes_MATLAB_runtime=False,includes_MATPOWER_case_data=False,
        preserves_original_evidence=True,original_Git_finalizers_not_promised_portable=True,
        runtime_results_are_unsealed_user_outputs=True,files=files)
    manifestpath=stage/'PACKAGE_MANIFEST.json';manifestpath.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    sums=[f"{r['sha256']}  {name}" for name,r in files.items()]+[f'{sha(manifestpath)}  PACKAGE_MANIFEST.json']
    (stage/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    validated=verify_root(stage)
    receipt=dict(**validated,stage_directory=str(stage),package_manifest_sha256=sha(manifestpath),
        inventory_sha256=sha(OUT/'package_inventory.json'),removed_builder_owned_files=removed,archive_created=False)
    if not stage_only:
        archive=release/f'nygrid_dlr_{kind}_20261013.zip';prefix=f'nygrid_dlr_{kind}_20261013/'
        allnames=sorted(files)+['PACKAGE_MANIFEST.json','SHA256SUMS.txt']
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True,strict_timestamps=False) as z:
            for i,name in enumerate(allnames,1):
                z.write(stage/name,prefix+name)
                if i%1000==0:print(f'{kind}: archived {i}/{len(allnames)} files',flush=True)
        checked=verify_zip(archive);assert checked==validated
        receipt.update(archive_created=True,archive_path=str(archive),archive_bytes=archive.stat().st_size,
                       archive_sha256=sha(archive),archive_readback_and_every_member_SHA256_passed=True)
    dest=OUT/'package_receipts';dest.mkdir(exist_ok=True)
    (dest/f'{kind}_package_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt),flush=True)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--kind',choices=['runtime','research','both'],default='both')
    p.add_argument('--release-dir',type=Path,default=DEFAULT_RELEASE);p.add_argument('--stage-only',action='store_true');a=p.parse_args()
    release=a.release_dir.resolve();release.mkdir(parents=True,exist_ok=True)
    assert release.is_relative_to((ROOT/'deliverables').resolve()),'Keep generated packages inside the dedicated deliverables workspace.'
    for kind in (['runtime','research'] if a.kind=='both' else [a.kind]):build(kind,release,a.stage_only)
