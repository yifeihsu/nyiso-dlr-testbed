"""Promote only the verified model pointer and the three current-map files."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT=Path(__file__).resolve().parents[3]
REPAIR=ROOT/'output/nygrid_2025_moses_repair'
OUT=REPAIR/'delivery'


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def record(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p))


def main():
    package=read(OUT/'package_receipts/final_package_receipt.json')
    cold=read(OUT/'validation/portable_extraction_review.json')
    assert package['passed'] and cold['passed'] and cold['smoke_test_count']==20
    archive=Path(package['archive_path']);assert archive.is_relative_to(ROOT)
    assert sha(archive)==package['archive_sha256']==cold['archive_sha256']
    for p in [OUT/'independent_delivery_review.json',OUT/'map/browser_visual_review.json',
              OUT/'map/DELIVERY_MANIFEST.json',REPAIR/'summary/report_receipt.json',
              REPAIR/'annual/moses_repair_v1/validation/annual_input_accounting_review.json',
              REPAIR/'annual/moses_repair_v1/validation/annual_physics_review.json']:
        assert read(p)['passed'],p
    guard=read(REPAIR/'baseline_guard.json')
    for r in guard['immutable_prior_artifacts']+guard['unrelated_worktree_files']:
        assert sha(ROOT/r['path'])==r['sha256'],r['path']
    current=ROOT/'output/nygrid_2025_latest_map';assert current.resolve().is_relative_to(ROOT.resolve())
    current.mkdir(exist_ok=True)
    for name in ['network_map.html','README.md']:
        source=OUT/'map'/name;target=current/name
        target.write_bytes(source.read_bytes());assert sha(target)==sha(source)
    # Keep old QA files intact. The current entry manifest explicitly points
    # into the versioned evidence directory instead of implying those old QA
    # files belong to this new page.
    manifest=read(OUT/'map/DELIVERY_MANIFEST.json')
    manifest['source_delivery_manifest']=record(OUT/'map/DELIVERY_MANIFEST.json')
    manifest['evidence_path_basis']='repository_root'
    for r in manifest['numerical_and_interaction_evidence']:
        r['path']='output/nygrid_2025_moses_repair/delivery/map/'+r['path']
    (current/'DELIVERY_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    pointer=dict(schema_version=1,status='validated_current_corrected_model',
                 created_utc=datetime.now(timezone.utc).isoformat(),
                 usage_status='Synthetic research model: annual equation/loss validation passed; physical meter equivalence and complete operating feasibility remain qualified.',
                 archive=record(archive),model_receipt=record(REPAIR/'model/model_receipt.json'),
                 structure_manual=record(OUT/'docs/NYGRID_2025_MOSES_REPAIR_MODEL_STRUCTURE.docx'),
                 map=record(OUT/'map/network_map.html'),map_manifest=record(OUT/'map/DELIVERY_MANIFEST.json'),
                 current_map_entry_manifest=record(current/'DELIVERY_MANIFEST.json'),
                 scientific_report=record(ROOT/'NYGRID_2025_MOSES_REPAIR.md'),
                 portable_validation=record(OUT/'validation/portable_extraction_review.json'),
                 independent_delivery_review=record(OUT/'independent_delivery_review.json'),
                 generation_validation=record(REPAIR/'generation/independent_generation_review.json'),
                 boundary_verification=record(REPAIR/'boundary/boundary_verification_receipt.json'),
                 annual_validation=record(REPAIR/'annual/moses_repair_v1/validation/annual_input_accounting_review.json'),
                 physical_validation=record(REPAIR/'annual/moses_repair_v1/validation/annual_physics_review.json'),
                 physical_P32_meter_equivalence_certified=False,fully_operating_qualified_hours=0,
                 old_sealed_numerical_bundles_preserved=True,prior_map_recovery=guard['recovery_archive'])
    target=ROOT/'deliverables/CURRENT_NYGRID_MODEL.json';target.write_text(json.dumps(pointer,indent=2)+'\n',encoding='utf-8')
    proof=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
               current_pointer=record(target),current_map=record(current/'network_map.html'),
               current_manifest=record(current/'DELIVERY_MANIFEST.json'),
               archive=record(archive),portable_smoke_checks=20,
               changes_confined_to_current_pointer_and_three_current_map_files=True,
               versioned_map_and_sealed_archive_unchanged=True)
    (OUT/'promotion_receipt.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,current_map_sha256=sha(current/'network_map.html'),archive_sha256=sha(archive))))


if __name__=='__main__':main()
