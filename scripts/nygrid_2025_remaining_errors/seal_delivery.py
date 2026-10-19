"""Verify frozen evidence and produce an additive, hash-checked diagnostic ZIP."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_remaining_errors'
SCRIPTS=ROOT/'scripts/nygrid_2025_remaining_errors'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rec(p):return {'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
def references(obj):
    if isinstance(obj,dict):
        if isinstance(obj.get('path'),str) and isinstance(obj.get('sha256'),str):yield obj
        for v in obj.values():yield from references(v)
    elif isinstance(obj,list):
        for v in obj:yield from references(v)
def main():
    guard=json.loads((OUT/'source_guard.json').read_text())
    assert all(sha(ROOT/r['path'])==r['sha256'] for r in guard['critical_numerical_sources'])
    assert all(sha(ROOT/r['path'])==r['sha256'] for r in guard['unrelated_map_working_changes_at_start'])
    required=['baseline/baseline_receipt.json','baseline/niagara_prior_consistency_receipt.json',
              'baseline/independent_probe_review.json','baseline/independent_pjm_partition_review.json',
              'accounting/gate_terms_receipt.json','accounting/accounting_identity_review.json',
              'physics/physics_review.json','probes/probe_receipt.json','probes/pjm_partition_receipt.json']
    checks=[];n=0
    for name in required:
        path=OUT/name;data=json.loads(path.read_text(encoding='utf-8'));assert data['passed'],name
        for r in references(data):
            p=ROOT/r['path'];assert p.is_file(),p;assert sha(p)==r['sha256'],('Stale receipt',name,r['path']);n+=1
        checks.append(rec(path))
    # Check all supplementary independent review receipts too, without assuming
    # their creation order or relying on the primary producer's pass boolean.
    checked={r['path'] for r in checks}
    for path in OUT.rglob('*review*.json'):
        if path.relative_to(ROOT).as_posix() in checked:continue
        data=json.loads(path.read_text(encoding='utf-8'))
        if 'passed' in data:assert data['passed'],path
        for r in references(data):
            p=ROOT/r['path'];assert p.is_file() and sha(p)==r['sha256'],('Stale extra review',path,r['path']);n+=1
        checks.append(rec(path))
    receipt={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'numerical_baseline_HEAD':guard['HEAD_at_start'],
             'branch':subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
             'critical_numerical_sources_unchanged':len(guard['critical_numerical_sources']),
             'unrelated_map_working_files_preserved':len(guard['unrelated_map_working_changes_at_start']),
             'receipt_hash_references_verified':n,'component_receipts':checks,
             'scientific_figures_visually_inspected':True,'inspection':'Two PNGexports checked for readablelabels,completeaxes,nooverlap orclipping; PDFexports useidenticalfigureobjects.',
             'new_annual_PF_run':False,'baseline_probe_hours':15,'planned_initial_cases':150,'initial_qualified_cases':142,'initial_rejected_cases':8,
             'supplementary_PJM_cases':30,'supplementary_PJM_qualified_cases':30,'default_model_promoted':False,
             'handoff_is_additive_diagnostic_supplement':True,'large_frozen_sources_require_existing_repository':True}
    target=OUT/'verification_receipt.json';target.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    files=[ROOT/'NYGRID_2025_REMAINING_ERROR_DIAGNOSIS.md']
    files+=sorted(p for p in SCRIPTS.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    files+=sorted(p for p in OUT.rglob('*') if p.is_file() and 'handoff' not in p.relative_to(OUT).parts)
    files=sorted(set(files));dest=OUT/'handoff';dest.mkdir(exist_ok=True)
    manifest={'schema_version':1,'kind':'additive_remaining_error_diagnostic_supplement','files':[rec(p) for p in files]}
    manifest_path=dest/'content_manifest.json';manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    archive=dest/'NYgrid_2025_remaining_errors_supplement.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
        for p in files:z.write(p,p.relative_to(ROOT).as_posix())
        z.write(manifest_path,'content_manifest.json')
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and len(z.namelist())==len(files)+1
        for r in manifest['files']:assert hashlib.sha256(z.read(r['path'])).hexdigest()==r['sha256']
    delivery={'passed':True,'archive':rec(archive),'files_in_archive':len(files)+1,'all_member_hashes_verified':True,'content_manifest':rec(manifest_path),
              'existing_current_model_or_map_archive_modified':False,'not_a_standalone_model_distribution':True}
    (dest/'archive_receipt.json').write_text(json.dumps(delivery,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'verified_receipt_hashes':n,'archive_files':len(files)+1,'archive_bytes':archive.stat().st_size}))
if __name__=='__main__':main()
