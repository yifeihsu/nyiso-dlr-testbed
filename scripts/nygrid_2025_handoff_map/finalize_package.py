"""Seal the map-inclusive handoff without modifying earlier deliveries."""
from pathlib import Path
import hashlib
import json
import argparse

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_handoff_map'
MANIFEST=OUT/'DELIVERY_MANIFEST.json'
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rec(path):return {'bytes':path.stat().st_size,'sha256':sha(path)}
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def expected():
    build=read(OUT/'build_receipt.json');review=read(OUT/'independent_package_review.json')
    assert build['passed'] and review['passed']
    archive=ROOT/build['archive']['path'];assert rec(archive)=={k:build['archive'][k] for k in ['bytes','sha256']}
    assert review['archive_sha256']==sha(archive)
    assert build['payload_files']==669 and build['base_payload_files_unchanged']==665
    assert build['modified_base_files']==['START_HERE.md']
    assert build['map_HTML_bytes_identical'] and build['runtime_model_and_structure_documents_unchanged']
    base=ROOT/build['base_archive']['path'];assert rec(base)=={k:build['base_archive'][k] for k in ['bytes','sha256']}
    for item in build['sources']:assert sha(ROOT/item['path'])==item['sha256']
    preserved={}
    for namespace in ['nygrid_2025_latest_handoff','nygrid_2025_latest_map']:
        path=ROOT/f'output/{namespace}/DELIVERY_MANIFEST.json';old=read(path)
        for name,item in old['files'].items():assert rec(ROOT/name)==item,f'Changed sealed input: {name}'
        preserved[namespace]={'files':len(old['files']),'manifest_sha256':sha(path)}
    paths=[]
    for folder in [Path(__file__).parent,OUT]:
        paths.extend(p for p in folder.rglob('*') if p.is_file() and p!=MANIFEST and '__pycache__' not in p.parts and p.suffix!='.pyc')
    files={p.relative_to(ROOT).as_posix():rec(p) for p in sorted(set(paths))}
    return {'schema_version':1,'status':'latest_model_handoff_with_current_interactive_map_verified',
        'baseline_HEAD':'de9a0e3bc5d588bde157c0877d03a08f06743b10','archive':build['archive'],
        'payload_files':669,'unchanged_base_files':665,'map_path_in_package':'map/network_map.html',
        'START_HERE_links_to_map':True,'old_archive_byte_preserved':True,
        'source_deliveries_preserved':preserved,'new_simulation_run':False,'files':files}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args();result=expected()
    if args.verify:assert read(MANIFEST)==result
    else:MANIFEST.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'files':len(result['files']),'bytes':sum(r['bytes'] for r in result['files'].values()),'archive':result['archive']}))
