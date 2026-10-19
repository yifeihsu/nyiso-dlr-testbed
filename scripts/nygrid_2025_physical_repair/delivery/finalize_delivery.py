"""Seal the current map, then promote explicit pointers after portable QA."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[3]
REPAIR=ROOT/'output/nygrid_2025_physical_repair'
OUT=REPAIR/'delivery'
MAP=OUT/'map'


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def rec(path):
    path=Path(path);return dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=sha(path))
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def seal_map():
    names=['build_receipt.json','scientific_data_receipt.json','interface_semantics_review.json',
        'geography_validation.json','geography_independent_review.json','independent_annual_data_review.json',
        'independent_ui_flow_math_review.json','independent_embedded_payload_review.json',
        'interaction_validation.json','browser_visual_review.json']
    proofs=[read(MAP/name) for name in names];assert all(p['passed'] for p in proofs)
    digest=sha(MAP/'network_map.html')
    assert read(MAP/'independent_embedded_payload_review.json')['HTML_sha256']==digest
    browser=read(MAP/'browser_visual_review.json');assert browser['HTML_sha256']==digest
    build=read(MAP/'build_receipt.json')
    for row in build['sources']+build['outputs']:assert sha(ROOT/row['path'])==row['sha256'],row['path']
    model=read(REPAIR/'model/model_receipt.json')
    assert model['model_file']['sha256']==build['compiledModelSha256']
    manifest=dict(schema_version=1,status='corrected_map_validated',created_utc=datetime.now(timezone.utc).isoformat(),
        offline_self_contained=True,HTML=rec(MAP/'network_map.html'),README=rec(MAP/'README.md'),
        physical_repair_candidate_sha256=model['physical_repair']['candidate_receipt_sha256'],
        compiled_model_sha256=model['model_file']['sha256'],
        annual_run='physical_repair_v1',hours=8760,source_qualified_hours=8651,equation_loss_qualified_hours=8651,
        joint_voltage_generator_qualified_hours=0,full_operating_qualified_hours=0,
        evidence=[rec(MAP/name) for name in names],
        canonical_data=[rec(MAP/name) for name in ['annual_data.json','geography_data.json','interface_definitions.json','map_data.json']],
        preexisting_map_edits_preserved=rec(OUT/'preservation/dirty_map_snapshot.json'))
    write(MAP/'DELIVERY_MANIFEST.json',manifest)
    print(json.dumps(dict(passed=True,HTML_sha256=digest,map_manifest_sha256=sha(MAP/'DELIVERY_MANIFEST.json'))))


def promote():
    package=read(OUT/'package_receipts/final_package_receipt.json')
    portable=read(OUT/'validation/portable_extraction_review.json')
    independent=read(OUT/'independent_delivery_review.json')
    assert package['passed'] and portable['passed'] and independent['passed']
    archive=Path(package['archive_path']);assert sha(archive)==package['archive_sha256']
    assert portable['archive_sha256']==package['archive_sha256']
    manifest=read(MAP/'DELIVERY_MANIFEST.json');assert manifest['HTML']['sha256']==sha(MAP/'network_map.html')
    old=ROOT/'output/nygrid_2025_latest_map';snapshot=read(OUT/'preservation/dirty_map_snapshot.json')
    targets=['network_map.html','README.md','DELIVERY_MANIFEST.json']
    baseline={row['path']:row for row in snapshot['files']}
    for name in targets:
        path=old/name;assert sha(path)==baseline[path.relative_to(ROOT).as_posix()]['sha256'],f'Preexisting file changed after preservation: {path}'
    current=dict(schema_version=1,status='validated_current_corrected_model',created_utc=datetime.now(timezone.utc).isoformat(),
        archive=rec(archive),model_receipt=rec(REPAIR/'model/model_receipt.json'),
        structure_manual=rec(OUT/'docs/NYGRID_2025_PHYSICAL_REPAIR_MODEL_STRUCTURE.docx'),
        map=rec(MAP/'network_map.html'),map_manifest=rec(MAP/'DELIVERY_MANIFEST.json'),
        scientific_report=rec(ROOT/'NYGRID_2025_PHYSICAL_REPAIR.md'),
        portable_validation=rec(OUT/'validation/portable_extraction_review.json'),
        independent_delivery_review=rec(OUT/'independent_delivery_review.json'),
        old_sealed_numerical_bundles_preserved=True,prior_map_recovery=rec(OUT/'preservation/dirty_map_snapshot.json'))
    pointer=ROOT/'deliverables/CURRENT_NYGRID_MODEL.json';assert not pointer.exists(),'Preserve any existing current pointer before replacing it.'
    write(pointer,current)
    shutil.copyfile(MAP/'network_map.html',old/'network_map.html')
    (old/'README.md').write_text('''# Current NYgrid map entrypoint

`network_map.html` is an exact alias of the validated corrected map in
`../nygrid_2025_physical_repair/delivery/map/`. Open it directly in a browser.

The current model has a completed fresh annual replay with 8,651 equation and
loss-qualified hours, 109 source-excluded hours, and zero jointly qualified
voltage/generator operating hours. The current delivery manifest and all
validation receipts are in the versioned physical-repair delivery.

Other older files retained in this directory are baseline artifacts. Their
receipts do not validate this replacement HTML. The previous HTML, README,
manifest and all pre-existing map edits are preserved in the verified recovery
ZIP and per-file receipt under
`../nygrid_2025_physical_repair/delivery/preservation/`.

The current portable package and its hashes are listed in
`../../deliverables/CURRENT_NYGRID_MODEL.json`.
''',encoding='utf-8')
    alias=dict(schema_version=1,status='alias_to_versioned_corrected_delivery',HTML=rec(old/'network_map.html'),
        canonical_map=rec(MAP/'network_map.html'),canonical_manifest=rec(MAP/'DELIVERY_MANIFEST.json'),
        current_handoff_pointer=rec(pointer),older_receipts_in_this_directory_are_baseline_only=True,
        prior_edits_recoverable_from=rec(OUT/'preservation/dirty_map_snapshot.json'))
    write(old/'DELIVERY_MANIFEST.json',alias)
    assert sha(old/'network_map.html')==sha(MAP/'network_map.html')
    write(OUT/'promotion_receipt.json',dict(passed=True,pointer=rec(pointer),map_alias=rec(old/'network_map.html'),
        alias_manifest=rec(old/'DELIVERY_MANIFEST.json'),baseline_numerical_models_unchanged=True))
    write(OUT/'DELIVERY_MANIFEST.json',dict(schema_version=1,passed=True,status='corrected_model_map_manual_and_portable_package_validated',
        current_handoff=current,package_receipt=rec(OUT/'package_receipts/final_package_receipt.json'),
        promotion_receipt=rec(OUT/'promotion_receipt.json'),
        document_visual_review=rec(OUT/'structure_document_visual_review.json'),
        source_runtime_validation=rec(OUT/'validation/runtime_validation_receipt.json'),
        baseline_profile_shards_byte_identical=True,all8760_hour_positions_preserved=True,
        equation_loss_qualified_hours=8651,joint_voltage_generator_qualified_hours=0,full_operating_qualified_hours=0,
        remaining_scope='Synthetic research model; source, physical-asset, weather, dispatch and operating limitations remain explicit.'))
    print(json.dumps(dict(passed=True,current_pointer=str(pointer),archive_sha256=package['archive_sha256'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['seal-map','promote'])
    args=parser.parse_args();seal_map() if args.operation=='seal-map' else promote()
