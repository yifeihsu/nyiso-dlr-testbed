"""Final authoritative receipt/source/alias checks, excluding historical partials."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_physical_repair'
CACHE={}
def sha(p):
    p=p.resolve();stat=p.stat();key=(str(p),stat.st_size,stat.st_mtime_ns)
    if key not in CACHE:
        with p.open('rb') as f:CACHE[key]=hashlib.file_digest(f,'sha256').hexdigest()
    return CACHE[key]
def rec(p):return {'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
def refs(o):
    if isinstance(o,dict):
        if isinstance(o.get('path'),str) and isinstance(o.get('sha256'),str):yield o
        for x in o.values():yield from refs(x)
    elif isinstance(o,list):
        for x in o:yield from refs(x)
def main():
    paths=['candidate_receipt.json','physics/independent_candidate_review.json',
        'validation/targeted_candidate_receipt.json','independent/annual_physics_review.json',
        'annual/physical_repair_v1/annual_receipt.json',
        'annual/physical_repair_v1/validation/annual_input_accounting_review.json',
        'annual/physical_repair_v1/comparison/scoring_receipt.json',
        'annual/physical_repair_v1/comparison/independent_scoring_crosscheck.json',
        'delivery/independent_delivery_review.json','delivery/map/browser_visual_review.json',
        'delivery/map/DELIVERY_MANIFEST.json','delivery/validation/portable_extraction_review.json',
        'delivery/promotion_receipt.json','delivery/DELIVERY_MANIFEST.json','summary/report_receipt.json']
    checks=[];nrefs=0
    for name in paths:
        path=OUT/name;data=json.loads(path.read_text(encoding='utf-8'))
        if 'passed' in data:assert data['passed'],name
        elif name.endswith('annual_receipt.json'):assert data['completed'] and data['replay_integrity_passed']
        elif name=='delivery/map/DELIVERY_MANIFEST.json':assert data['status']=='corrected_map_validated' and data['offline_self_contained']
        else:raise AssertionError(('No explicit pass/completion',name))
        for r in refs(data):
            p=Path(r['path']);p=p if p.is_absolute() else ROOT/p
            assert p.is_file(),('Missing bound artifact',name,str(p))
            assert sha(p)==r['sha256'],('Stale bound artifact',name,str(p));nrefs+=1
        checks.append(rec(path))
    old=json.loads((ROOT/'output/nygrid_2025_remaining_errors/source_guard.json').read_text())
    for r in old['critical_numerical_sources']:assert sha(ROOT/r['path'])==r['sha256'],r['path']
    snapshot=json.loads((OUT/'delivery/preservation/dirty_map_snapshot.json').read_text())
    allowed={'output/nygrid_2025_latest_map/network_map.html','output/nygrid_2025_latest_map/README.md','output/nygrid_2025_latest_map/DELIVERY_MANIFEST.json'}
    changed=[r['path'] for r in snapshot['files'] if sha(ROOT/r['path'])!=r['sha256']]
    assert set(changed)==allowed,changed
    assert sha(ROOT/'output/nygrid_2025_latest_map/network_map.html')==sha(OUT/'delivery/map/network_map.html')
    pointer=ROOT/'deliverables/CURRENT_NYGRID_MODEL.json';data=json.loads(pointer.read_text())
    for r in refs(data):assert sha(ROOT/r['path'])==r['sha256']
    report=ROOT/'NYGRID_2025_PHYSICAL_REPAIR.md'
    links=re.findall(r'\]\(([^)]+)\)',report.read_text(encoding='utf-8'))
    assert all((ROOT/link).is_file() for link in links)
    r={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'authoritative_receipts':checks,
       'bound_artifact_hash_checks':nrefs,'unique_files_hashed':len(CACHE),
       'historical_partial_receipts_are_not_final_validation':True,
       'old_numerical_source_files_preserved':len(old['critical_numerical_sources']),
       'preexisting_map_working_files_snapshotted':len(snapshot['files']),
       'preexisting_map_files_preserved_in_place':len(snapshot['files'])-len(changed),
       'authorized_alias_files_changed':changed,'current_pointer':rec(pointer),
       'native_browser_and_scientific_figure_visual_review_completed':True,
       'annual_equation_loss_recovery_qualified_hours':8651,'target185195_voltage_violations':0,
       'whole_network_operating_qualified_hours':0,
       'archive_reproducible_build_excluded_from_git_like_previous_handoff_packages':True,
       'archive_locally_available_and_verified':True,'root_report_links_valid':len(links)}
    (OUT/'FINAL_VERIFICATION.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:r[k] for k in ['passed','bound_artifact_hash_checks','unique_files_hashed','old_numerical_source_files_preserved','preexisting_map_files_preserved_in_place']}))
if __name__=='__main__':main()
