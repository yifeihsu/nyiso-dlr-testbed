"""Seal the latest-only handoff and verify preservation of earlier deliveries."""
from pathlib import Path
import argparse
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_latest_handoff'
MANIFEST=OUT/'DELIVERY_MANIFEST.json'
BASE='2e0fcd5c3f0ae39d04f27a733ce30eb148b0b243'

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rec(path):return {'bytes':path.stat().st_size,'sha256':sha(path)}
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def expected():
    required=['model/model_receipt.json','structure/current_structure_inventory.json',
        'structure_document_visual_review.json','structure_document_independent_review.json',
        'validation/runtime_validation_receipt.json','validation/kernel_adaptation_receipt.json',
        'independent/current_data_review.json','independent/kernel_source_review.json',
        'model_bundle_independent_review.json','runtime_receipts_independent_review.json',
        'independent/portable_package_review.json']
    for name in required:
        path=OUT/name;assert path.is_file() and read(path)['passed'],f'Incomplete current proof: {name}'
    doc=ROOT/'NYGRID_2025_LATEST_MODEL_STRUCTURE.docx'
    visual=read(OUT/'structure_document_visual_review.json')
    assert visual['document']['sha256']==sha(doc) and visual['pages']==7
    assert visual['native_editable_OMML_equations']==8 and visual['all_seven_page_images_visually_inspected']
    package=read(OUT/'package_receipts/final_package_receipt.json')
    archive=Path(package['archive_path']);assert rec(archive)=={'bytes':package['archive_bytes'],'sha256':package['archive_sha256']}
    assert package['archive_integrity_check']['passed'] and package['extracted_integrity_check']['passed']
    independent=read(OUT/'independent/portable_package_review.json')
    assert independent['archive_sha256']==sha(archive),'Portable proof does not bind the final ZIP.'
    preserved={}
    for namespace in ['nygrid_2025_ac_system','nygrid_2025_acpf_profile_audit','nygrid_2025_compact_ac',
        'nygrid_2025_centraleast_diagnosis','nygrid_2025_ac_loss_revision','nygrid_2025_dlr_handoff',
        'nygrid_2025_conductor_inference']:
        path=ROOT/f'output/{namespace}/DELIVERY_MANIFEST.json';old=read(path)
        for name,item in old['files'].items():assert rec(ROOT/name)==item,f'Changed prior delivery: {name}'
        preserved[namespace]={'files':len(old['files']),'manifest_sha256':sha(path)}
    old_hand=read(ROOT/'output/nygrid_2025_dlr_handoff/DELIVERY_MANIFEST.json')
    for item in old_hand['archives'].values():assert rec(ROOT/item['path'])=={'bytes':item['bytes'],'sha256':item['sha256']}
    old_sup=read(ROOT/'output/nygrid_2025_conductor_inference/DELIVERY_MANIFEST.json')['supplement']
    assert rec(ROOT/old_sup['path'])=={'bytes':old_sup['bytes'],'sha256':old_sup['sha256']}
    assert sha(ROOT/'NYGRID_2025_WESTERN_SOURCE_AUDIT.md')=='e21175a942b85519688708eaba22b2100ad06281b256a5d1dd66b17371b3d4cb'
    paths=[doc,ROOT/'NYGRID_2025_LATEST_MODEL_STRUCTURE.md']
    for folder in [ROOT/'scripts/nygrid_2025_latest_handoff',OUT]:
        paths.extend(p for p in folder.rglob('*') if p.is_file() and p!=MANIFEST and
            '__pycache__' not in p.parts and 'document_render' not in p.parts and p.suffix!='.pyc')
    files={p.relative_to(ROOT).as_posix():rec(p) for p in sorted(set(paths))}
    assert max(r['bytes'] for r in files.values())<100_000_000,'Split oversized files before staging.'
    for name,item in package['selection'].items():
        assert rec(Path(item['source_path']))=={'bytes':item['bytes'],'sha256':item['sha256']},f'Stale ZIP source: {name}'
    return {'schema_version':1,'status':'latest_only_model_package_and_structure_document_validated',
        'source_model_commit':BASE,'four_date_states_one_model_version':True,
        'electrical_or_thermal_equations_changed':False,'new_annual_PF_or_OPF_run':False,
        'old_deliveries':preserved,'old_archives_byte_preserved':True,
        'document_pages':7,'native_editable_equations':8,
        'archive':{'path':archive.relative_to(ROOT).as_posix(),**rec(archive)},
        'package_payload_files':package['payload_files'],'package_payload_bytes':package['payload_bytes'],
        'files':files}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    result=expected()
    if args.verify:assert read(MANIFEST)==result,'Current delivery differs from its seal.'
    else:MANIFEST.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'mode':'verify' if args.verify else 'seal','files':len(result['files']),
        'bytes':sum(x['bytes'] for x in result['files'].values()),
        'preserved_files':sum(x['files'] for x in result['old_deliveries'].values()),'archive':result['archive']}))
