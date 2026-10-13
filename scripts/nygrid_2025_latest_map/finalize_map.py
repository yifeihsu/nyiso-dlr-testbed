"""Seal the updated current map and preserve earlier model deliveries."""
from pathlib import Path
import hashlib
import json
import argparse

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_latest_map'
MANIFEST=OUT/'DELIVERY_MANIFEST.json'
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rec(path):return {'bytes':path.stat().st_size,'sha256':sha(path)}
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def expected():
    required=['scientific_data_receipt.json','geography_validation.json','geography_independent_review.json',
        'interface_semantics_review.json','independent_annual_data_review.json','independent_ui_flow_math_review.json',
        'independent_embedded_payload_review.json','interaction_validation.json','browser_visual_review.json','build_receipt.json']
    for name in required:assert (OUT/name).is_file() and read(OUT/name)['passed'],f'Incomplete proof: {name}'
    html=OUT/'network_map.html';interaction=read(OUT/'interaction_validation.json');browser=read(OUT/'browser_visual_review.json')
    assert interaction['html_sha256']==sha(html) and interaction['checks_run']==28 and interaction['final_ui_freeze_confirmed']
    assert browser['HTML_sha256']==sha(html) and browser['native_browser_checks']==13
    assert browser['viewport_override_reset'] and browser['blocked_file_navigation_not_bypassed']
    for item in browser['final_screenshots']+[browser['observations']]:assert sha(ROOT/item['path'])==item['sha256']
    build=read(OUT/'build_receipt.json')
    for item in build['sources']+build['outputs']:assert sha(ROOT/item['path'])==item['sha256'],f'Stale map binding: {item["path"]}'
    scientific=read(OUT/'independent_embedded_payload_review.json')
    assert scientific['HTML_sha256']==sha(html) and scientific['JS_sha256']==sha(ROOT/'scripts/nygrid_2025_latest_map/map.js')
    preserved={}
    for namespace in ['nygrid_2025_ac_system','nygrid_2025_acpf_profile_audit','nygrid_2025_compact_ac',
        'nygrid_2025_centraleast_diagnosis','nygrid_2025_ac_loss_revision','nygrid_2025_dlr_handoff',
        'nygrid_2025_conductor_inference','nygrid_2025_latest_handoff']:
        path=ROOT/f'output/{namespace}/DELIVERY_MANIFEST.json';old=read(path)
        for name,item in old['files'].items():assert rec(ROOT/name)==item,f'Changed prior model delivery: {name}'
        preserved[namespace]={'files':len(old['files']),'manifest_sha256':sha(path)}
    old_hand=read(ROOT/'output/nygrid_2025_dlr_handoff/DELIVERY_MANIFEST.json')
    archives=list(old_hand['archives'].values())+[read(ROOT/'output/nygrid_2025_conductor_inference/DELIVERY_MANIFEST.json')['supplement'],
        read(ROOT/'output/nygrid_2025_latest_handoff/DELIVERY_MANIFEST.json')['archive']]
    for item in archives:assert rec(ROOT/item['path'])=={'bytes':item['bytes'],'sha256':item['sha256']}
    assert sha(ROOT/'NYGRID_2025_WESTERN_SOURCE_AUDIT.md')=='e21175a942b85519688708eaba22b2100ad06281b256a5d1dd66b17371b3d4cb'
    old_map={}
    for item in interaction['previous_artifacts_preserved']:
        name=item['path'];path=ROOT/name
        assert sha(path)==item['sha256'];old_map[name]=rec(path)
    paths=[]
    for folder in [ROOT/'scripts/nygrid_2025_latest_map',OUT]:
        paths.extend(p for p in folder.rglob('*') if p.is_file() and p!=MANIFEST and '__pycache__' not in p.parts and p.suffix!='.pyc')
    files={p.relative_to(ROOT).as_posix():rec(p) for p in sorted(set(paths))}
    assert max(r['bytes'] for r in files.values())<100_000_000
    return {'schema_version':1,'status':'current_AC_model_interactive_map_with_zones_and_interface_flows_validated',
        'source_model_commit':'39402c2057b75670fe0591ab7f1f2ed304adec56',
        'html':{'path':html.relative_to(ROOT).as_posix(),**rec(html)},
        'source_qualified_hours':8651,'equation_loss_qualified_hours':8170,'hour_slots':8760,
        'NY_zones':11,'modeled_interfaces':7,'DOM_checks':28,'native_browser_checks':13,
        'direct_file_protocol_browser_visit_blocked':True,'browser_preview_protocol':'http_loopback',
        'new_PF_or_OPF_run':False,'old_deliveries':preserved,'old_maps':old_map,
        'old_handoff_archives_byte_preserved':True,'files':files}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args();result=expected()
    if args.verify:assert read(MANIFEST)==result,'Map delivery differs from its seal.'
    else:MANIFEST.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'files':len(result['files']),'bytes':sum(r['bytes'] for r in result['files'].values()),
        'preserved_files':sum(r['files'] for r in result['old_deliveries'].values()),'html':result['html']},indent=2))
