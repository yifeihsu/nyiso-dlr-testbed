"""Seal the handoff, archive identities, clean-room proofs and preservation."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_dlr_handoff'
RELEASE=ROOT/'deliverables/nygrid_2025_dlr_handoff_20261013'
MANIFEST=OUT/'DELIVERY_MANIFEST.json'
BASELINE='8188cbec1172219a0414881121ad042b405a4044'


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))


def sha(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def record(p):return dict(bytes=p.stat().st_size,sha256=sha(p))


def verify_bound_records(value,context):
    count=0
    if isinstance(value,dict):
        if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str):
            p=ROOT/value['path']
            if not p.is_file():p=context.parent/value['path']
            assert p.is_file(),f'Missing current proof dependency: {value["path"]}'
            assert sha(p)==value['sha256'].lower(),f'Stale current proof dependency in {context.name}: {p}'
            count+=1
        for child in value.values():count+=verify_bound_records(child,context)
    elif isinstance(value,list):
        for child in value:count+=verify_bound_records(child,context)
    return count


def expected():
    required=[
        'handbook_build_receipt.json','handbook_visual_review.json','scientific_handoff_review.json',
        'independent_thermal_scope/independent_thermal_scope_review.json',
        'package_receipts/packaging_code_independent_review.json',
        'extracted_validation/runtime/final/final_runtime_validation_receipt.json',
        'extracted_validation/research/final/final_research_validation_receipt.json',
        'extracted_validation/runtime_extraction_receipt.json',
        'extracted_validation/research_extraction_receipt.json',
        'package_receipts/runtime_package_receipt.json','package_receipts/research_package_receipt.json']
    checks=0
    for name in required:
        p=OUT/name;assert p.is_file(),f'Unfinished handoff validation: {name}';value=read(p)
        if name!='handbook_build_receipt.json':assert value['passed'],f'Failed handoff validation: {name}'
        checks+=verify_bound_records(value,p)
    runtime=read(OUT/required[5]);research=read(OUT/required[6])
    assert runtime['smoke_test_count']==18 and not runtime['extraction_patched_before_smoke']
    assert runtime['setup_default_bundled_vendor_used'] and runtime['git_ancestor_absent']
    assert not runtime['unapproved_executed_files'] and not runtime['unapproved_search_paths']
    assert not runtime['installed_asset_DLR_qualification'] and not runtime['whole_system_operating_qualification']
    assert research['completed'] and not research['extraction_patched_before_scoring']
    assert research['git_ancestor_absent'] and not research['Git_process_executed'] and not research['git_executable_on_PATH']
    assert research['paired_hours']==8170 and research['metric_rows_recomputed']==1302
    assert research['gained_hours']==0 and research['lost_hours']==324
    assert research['all_reference_CSV_bytes_identical_on_this_host'] and research['all_reference_NPZ_arrays_identical']
    assert research['NPZ_array_count']==26 and not research['PF_or_OPF_rerun']
    assert research['post_scoring_manifest_verification']['sealed_files_unchanged_after_scoring']
    assert read(OUT/'package_receipts/packaging_code_independent_review.json')['fixture_check_count']==31
    visual=read(OUT/'handbook_visual_review.json')
    assert visual['page_count']==21 and visual['native_editable_equations']==9 and visual['all_pages_visually_reviewed']
    assert sha(ROOT/'NYGRID_2025_DLR_HANDOFF.docx')==visual['docx_sha256']
    assert sha(ROOT/'NYGRID_2025_DLR_HANDOFF.md')==visual['markdown_sha256']
    # Recheck the delivered numerical-model families, including the latest
    # loss revision. New handoff work must not alter any of these 1218 entries.
    preserved={}
    for namespace in ['nygrid_2025_ac_system','nygrid_2025_acpf_profile_audit','nygrid_2025_compact_ac',
                      'nygrid_2025_centraleast_diagnosis','nygrid_2025_ac_loss_revision']:
        p=ROOT/f'output/{namespace}/DELIVERY_MANIFEST.json';old=read(p)
        for name,r in old['files'].items():assert record(ROOT/name)==r,f'Prior delivery changed: {name}'
        preserved[namespace]=dict(files=len(old['files']),manifest_sha256=sha(p))
    assert sha(ROOT/'NYGRID_2025_WESTERN_SOURCE_AUDIT.md')=='e21175a942b85519688708eaba22b2100ad06281b256a5d1dd66b17371b3d4cb'
    inventory=read(OUT/'package_inventory.json');assert inventory['source_head']==BASELINE
    differences={r['path']:r for r in inventory['existing_worktree_differences']}
    for r in inventory['files']:
        if r['path'] in {'.gitignore','.gitattributes'}:continue  # explicitly owned packaging configuration changes
        p=ROOT/r['path'];wanted=differences.get(r['path'],{}).get('working_sha256',r['sha256'])
        assert p.is_file() and sha(p)==wanted,f'Pre-existing working artifact changed: {r["path"]}'
    archives={}
    for kind in ['runtime','research']:
        receipt=read(OUT/f'package_receipts/{kind}_package_receipt.json')
        p=Path(receipt['archive_path']);assert p.resolve().is_relative_to(RELEASE.resolve()) and p.suffix=='.zip'
        assert p.stat().st_size==receipt['archive_bytes'] and sha(p)==receipt['archive_sha256']
        assert receipt['archive_readback_and_every_member_SHA256_passed'] and receipt['checksum_table_and_manifest_digest_verified']
        extraction=read(OUT/f'extracted_validation/{kind}_extraction_receipt.json')
        assert extraction['archive_sha256']==receipt['archive_sha256'] and not extraction['extraction_patched']
        assert extraction['no_git_in_any_ancestor']
        archives[kind]=dict(path=p.relative_to(ROOT).as_posix(),**record(p),sealed_files=receipt['files'],
                            uncompressed_payload_bytes=receipt['bytes'],actual_archive_extracted_and_verified=True)
    assert runtime['archive']['sha256']==archives['runtime']['sha256']
    assert research['archive']['sha256']==archives['research']['sha256']
    # All final runtime witness files are carried with their exact receipt.
    final=OUT/'extracted_validation/runtime/final'
    for r in runtime['evidence_files']:
        assert record(final/r['name'])==dict(bytes=r['bytes'],sha256=r['sha256'])
    links=[]
    for value in re.findall(r'\]\(([^)]+)\)',(ROOT/'NYGRID_2025_DLR_HANDOFF.md').read_text(encoding='utf-8')):
        if value.startswith(('https://','http://','#')):continue
        p=ROOT/unquote(value.strip('<>').split('#')[0]);assert p.is_file(),f'Broken handoff link: {value}'
        links.append(value)
    paths=[ROOT/'NYGRID_2025_DLR_HANDOFF.docx',ROOT/'NYGRID_2025_DLR_HANDOFF.md']
    for base in [ROOT/'scripts/nygrid_2025_dlr_handoff',OUT]:
        paths += [p for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                  and p.suffix!='.pyc' and 'document_render' not in p.parts and p!=MANIFEST]
    files={p.relative_to(ROOT).as_posix():record(p) for p in sorted(set(paths))}
    assert max(r['bytes'] for r in files.values())<100_000_000
    return dict(schema_version=1,status='complete_colleague_research_handoff_with_verified_local_archives',
        source_model_commit=BASELINE,handbook_pages=21,prior_deliveries_byte_preserved=preserved,
        prior_selected_working_files_preserved=len(inventory['files'])-2,archives=archives,
        runtime_fresh_untouched_archive_checks=18,packaging_integrity_preservation_checks=31,
        research_no_Git_rescore_passed=True,current_proof_hash_checks=checks,
        local_handbook_links=len(links),current_model_joint_operating_qualification=False,
        final_execution_receipts_are_shipped_beside_archives=True,
        early_failed_archive_and_patched_diagnostic_are_historical_only=True,
        no_upload_or_message_to_colleague_performed=True,files=files)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--verify',action='store_true');a=p.parse_args();result=expected()
    if a.verify:assert read(MANIFEST)==result,'Handoff seal changed'
    else:
        MANIFEST.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        public={k:v for k,v in result.items() if k!='files'}
        (RELEASE/'FINAL_DELIVERY_RECEIPT.json').write_text(json.dumps(public,indent=2)+'\n',encoding='utf-8')
        lines=[f"{r['sha256']}  {Path(r['path']).name}" for r in result['archives'].values()]
        for name in ['NYGRID_2025_DLR_HANDOFF.docx','NYGRID_2025_DLR_HANDOFF.md']:
            shutil.copyfile(ROOT/name,RELEASE/name)
            lines.append(f"{sha(ROOT/name)}  {name}")
        (RELEASE/'ARCHIVE_SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,mode='verify' if a.verify else 'seal',handoff_files=len(result['files']),
        bytes=sum(r['bytes'] for r in result['files'].values()),proof_hash_checks=result['current_proof_hash_checks'],
        prior_delivery_files=sum(x['files'] for x in result['prior_deliveries_byte_preserved'].values()),
        archives={k:{x:v for x,v in r.items() if x!='sha256'} for k,r in result['archives'].items()})))
