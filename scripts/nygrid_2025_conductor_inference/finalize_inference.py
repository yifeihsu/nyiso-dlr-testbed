"""Seal the R/X policy update while preserving the model and v1 handoff."""
from pathlib import Path
import argparse
import hashlib
import json
import re

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_conductor_inference'
MANIFEST=OUT/'DELIVERY_MANIFEST.json'
REPORT=ROOT/'NYGRID_2025_CONDUCTOR_INFERENCE.md'


def sha(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def record(p):return dict(bytes=p.stat().st_size,sha256=sha(p))


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))


def proof(value,context):
    count=0
    if isinstance(value,dict):
        if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str):
            p=ROOT/value['path']
            if not p.is_file():p=context.parent/value['path']
            assert p.is_file() and sha(p)==value['sha256'].lower(),f'Stale or missing bound source in {context}: {value["path"]}'
            count+=1
        for child in value.values():count+=proof(child,context)
    elif isinstance(value,list):
        for child in value:count+=proof(child,context)
    return count


def expected():
    required=['inverse_search_receipt.json','independent/inverse_physics_review.json',
        'independent/inference_api_independent_review.json','matlab_validation/validation_receipt.json',
        'independent/matlab_v2_independent_review.json','provenance_and_runtime_RXB_review.json',
        'report_receipt.json','final_report_review.json','packaging/supplement_receipt.json',
        'supplement_validation/portable_supplement_receipt.json']
    for name in required:
        p=OUT/name;assert p.is_file() and read(p)['passed'],f'Unfinished or failed evidence: {name}'
    search=read(OUT/required[0]);tests=read(OUT/required[3]);installed=read(OUT/required[-1])
    assert search['current_targets_with_candidates']==185 and search['imported_targets_with_candidates']==141
    assert search['feasible_candidate_rows']==11701 and not search['selected_realizations_applied_to_electrical_or_thermal_model']
    assert tests['test_count']==35 and [p['v2_parent_count'] for p in tests['points']]==[179,180]
    assert not tests['electrical_input_files_changed'] and not tests['handoff_v1_changed']
    assert installed['old_v1_files_verified_after_execution']==770 and installed['MATLAB_eligible_parents']==180
    assert installed['supplement_payload_files_verified_after_execution']==81 and installed['idempotent_install_passed']
    assert installed['conflicting_destination_refused_before_writes'] and not installed['electrical_parameters_changed']
    assert not installed['OPF_run'] and not installed['original_VQ_gate']
    preserved={}
    for namespace in ['nygrid_2025_ac_system','nygrid_2025_acpf_profile_audit','nygrid_2025_compact_ac',
                      'nygrid_2025_centraleast_diagnosis','nygrid_2025_ac_loss_revision','nygrid_2025_dlr_handoff']:
        p=ROOT/f'output/{namespace}/DELIVERY_MANIFEST.json';old=read(p)
        for name,r in old['files'].items():assert record(ROOT/name)==r,f'Prior frozen delivery changed: {name}'
        preserved[namespace]=dict(files=len(old['files']),manifest_sha256=sha(p))
    old_handoff=read(ROOT/'output/nygrid_2025_dlr_handoff/DELIVERY_MANIFEST.json')
    for r in old_handoff['archives'].values():assert record(ROOT/r['path'])==dict(bytes=r['bytes'],sha256=r['sha256'])
    assert sha(ROOT/'NYGRID_2025_WESTERN_SOURCE_AUDIT.md')=='e21175a942b85519688708eaba22b2100ad06281b256a5d1dd66b17371b3d4cb'
    paths=[REPORT]
    for base in [ROOT/'scripts/nygrid_2025_conductor_inference',OUT]:
        paths += [p for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p!=MANIFEST]
    checks=0
    for p in paths:
        if p.suffix=='.json':checks+=proof(read(p),p)
    links=0
    for value in re.findall(r'\]\(([^)]+)\)',REPORT.read_text(encoding='utf-8')):
        if value.startswith(('https://','http://','#')):continue
        assert (ROOT/value).is_file(),f'Broken addendum link: {value}';links+=1
    files={p.relative_to(ROOT).as_posix():record(p) for p in sorted(set(paths))}
    assert max(r['bytes'] for r in files.values())<100_000_000
    package=read(OUT/'packaging/supplement_receipt.json')
    assert record(ROOT/package['archive']['path'])==dict(bytes=package['archive']['bytes'],sha256=package['archive']['sha256'])
    return dict(schema_version=1,status='RX_conditioned_synthetic_conductor_inference_and_DLR_screen_validated',
        baseline_HEAD='51e424a139e0d0ec42fcbbb35749deaf119cffc2',
        installed_circuit_identity_required=False,geographic_chord_required=False,
        model_R_X_B_or_dispatch_changed=False,original_electrical_and_handoff_deliveries_preserved=preserved,
        old_archives_byte_preserved=True,current_targets_with_candidates=185,imported_targets_with_candidates=141,
        current_post_Dover_eligible_parents=180,previous_post_Dover_eligible_parents=46,
        new_candidates_not_automatically_applied=True,installed_asset_qualification=False,
        proof_hash_checks=checks,local_addendum_links=links,supplement=package['archive'],files=files)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--verify',action='store_true');a=p.parse_args();result=expected()
    if a.verify:assert read(MANIFEST)==result,'Inference delivery changed'
    else:
        MANIFEST.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        archive=ROOT/result['supplement']['path']
        archive.with_suffix('.sha256.txt').write_text(f"{result['supplement']['sha256']}  {archive.name}\n",encoding='utf-8')
    print(json.dumps(dict(passed=True,mode='verify' if a.verify else 'seal',files=len(result['files']),
        bytes=sum(x['bytes'] for x in result['files'].values()),proof_hash_checks=result['proof_hash_checks'],
        preserved_files=sum(x['files'] for x in result['original_electrical_and_handoff_deliveries_preserved'].values()),
        supplement=result['supplement'])))
