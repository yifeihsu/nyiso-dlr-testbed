"""Seal one corrected current model, offline map and evidence-backed manual."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import re
import shutil
import zipfile
from verify_package import verify_root,verify_zip,safe_name

ROOT=Path(__file__).resolve().parents[3]
SRC=Path(__file__).parent
REPAIR=ROOT/'output/nygrid_2025_physical_repair'
OUT=REPAIR/'delivery'
RELEASE=ROOT/'deliverables/nygrid_2025_physical_repair_20261015'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def gather():
    annual=REPAIR/'annual'/os.environ.get('NYGRID_REPAIR_RUN_LABEL','physical_repair_v1')
    ar=read(annual/'annual_receipt.json');assert ar['completed'] and ar['months_complete']==12
    score=read(annual/'comparison/scoring_receipt.json');assert score['passed']
    selected={}
    def add(source,target,role):
        source=Path(source);safe_name(target);assert source.is_file(),source
        assert target not in selected,target
        selected[target]=dict(source_path=str(source.resolve()),bytes=source.stat().st_size,sha256=sha(source),role=role)
    gates=[OUT/'validation/runtime_validation_receipt.json',OUT/'validation/cold_smoke/smoke_receipt.json',
        OUT/'structure_document_visual_review.json',OUT/'structure_document_content_review.json',OUT/'independent_delivery_review.json',
        OUT/'map/scientific_data_receipt.json',OUT/'map/independent_annual_data_review.json',
        OUT/'map/geography_independent_review.json',OUT/'map/independent_ui_flow_math_review.json',
        OUT/'map/independent_embedded_payload_review.json',OUT/'map/interaction_validation.json',OUT/'map/browser_visual_review.json']
    for path in gates:assert read(path)['passed'],path
    for path in sorted((SRC/'runtime').rglob('*.m')):add(path,'runtime/'+path.relative_to(SRC/'runtime').as_posix(),'corrected_runtime')
    for path in sorted((SRC/'examples').glob('*.m')):add(path,'examples/'+path.name,'current_example')
    for name in ['latest_model.mat','profiles_h0001_4380.mat','profiles_h4381_8760.mat','model_receipt.json']:
        add(REPAIR/'model'/name,'model/'+name,'corrected_model')
    for path in sorted((OUT/'structure').iterdir()):
        if path.is_file() and path.suffix in ['.json','.csv','.png','.svg']:add(path,'model/structure/'+path.name,'corrected_structure')
    for name in ['START_HERE.md','DATA_DICTIONARY.md','THIRD_PARTY_NOTICES.md','NYGRID_2025_PHYSICAL_REPAIR_MODEL_STRUCTURE.docx','NYGRID_2025_PHYSICAL_REPAIR_MODEL_STRUCTURE.md']:
        add(OUT/'docs'/name,name,'current_documentation')
    report_source=ROOT/'NYGRID_2025_PHYSICAL_REPAIR.md'
    report=report_source.read_text(encoding='utf-8')
    replacements={
        'output/nygrid_2025_physical_repair/summary/physical_repair_comparison.png':'analysis/physical_repair_comparison.png',
        'output/nygrid_2025_physical_repair/annual/physical_repair_v1/annual_receipt.json':'verification/annual_receipt.json',
        'output/nygrid_2025_physical_repair/annual/physical_repair_v1/validation/annual_input_accounting_review.json':'verification/annual_input_accounting_review.json',
        'output/nygrid_2025_physical_repair/independent/annual_physics_review.json':'verification/annual_physics_review.json',
        'output/nygrid_2025_physical_repair/annual/physical_repair_v1/comparison/scoring_receipt.json':'verification/scoring_receipt.json',
        'output/nygrid_2025_physical_repair/independent/target_parent_metrics.csv':'analysis/target_parent_metrics.csv',
        '[Reproduction instructions](scripts/nygrid_2025_physical_repair/README.md)':'[Portable setup and run instructions](START_HERE.md)'}
    for old,new in replacements.items():assert old in report,old;report=report.replace(old,new)
    report_target=OUT/'docs/NYGRID_2025_PHYSICAL_REPAIR.md';report_target.write_text(report,encoding='utf-8')
    add(report_target,'NYGRID_2025_PHYSICAL_REPAIR.md','current_scientific_report_with_portable_links')
    adaptation=OUT/'docs/report_portable_link_adaptation.json'
    adaptation.write_text(json.dumps(dict(passed=True,source_path=report_source.relative_to(ROOT).as_posix(),
        source_sha256=sha(report_source),portable_path='NYGRID_2025_PHYSICAL_REPAIR.md',portable_sha256=sha(report_target),
        changes='Only relative package paths and the linked setup-instruction label are adapted; scientific prose and numerical content are unchanged.',
        replacements=replacements),indent=2)+'\n')
    add(adaptation,'verification/report_portable_link_adaptation.json','portable_document_link_receipt')
    for suffix in ['png','pdf']:add(REPAIR/f'summary/physical_repair_comparison.{suffix}',f'analysis/physical_repair_comparison.{suffix}','paired_physical_comparison_figure')
    add(SRC/'verify_package.py','verify_package.py','standard_library_integrity_verifier')
    vendor=read(ROOT/'output/nygrid_2025_dlr_handoff/runtime_audit/vendor_code_closure.json')
    for row in vendor['entries']:
        if row['target'].endswith('/RUNTIME_SUBSET_NOTICE.txt'):continue
        assert sha(row['source_path'])==row['sha256'],row['source_path']
        add(row['source_path'],row['target'],'licensed_vendor_code')
    add(OUT/'docs/MATPOWER_RUNTIME_SUBSET_NOTICE.txt','vendor/matpower8.1/RUNTIME_SUBSET_NOTICE.txt','vendor_subset_notice')
    for name in ['network_map.html','README.md','DELIVERY_MANIFEST.json']:add(OUT/'map'/name,'map/'+name,'offline_current_map')
    for path in gates:add(path,'verification/'+path.name,'fresh_validation_receipt')
    for path in [REPAIR/'candidate_receipt.json',REPAIR/'physics/independent_candidate_review.json',
                 REPAIR/'physics/parent41_parameters.json',REPAIR/'physics/compensation_design_review.json',
                 annual/'annual_receipt.json',annual/'comparison/scoring_receipt.json',
                 annual/'validation/annual_input_accounting_review.json',REPAIR/'independent/annual_physics_review.json',REPAIR/'summary/report_receipt.json']:
        add(path,'verification/'+path.name,'frozen_physics_and_annual_receipt')
    for path in [annual/'annual_hour_quality.csv',annual/'comparison/public_interface_metrics.csv',annual/'comparison/comparison_cohort.csv',
                 REPAIR/'physics/reactor_placement_by_state.csv',REPAIR/'independent/target_parent_metrics.csv']:
        add(path,'analysis/'+path.name,'inspectable_current_results')
    for path in sorted((annual/'comparison').glob('*.json')):
        if path.name!='scoring_receipt.json':add(path,'analysis/'+path.name,'current_comparison_summary')
    return selected,ar


def build(label):
    assert label and all(c.isalnum() or c in '_-' for c in label)
    selected,annual=gather();model=read(REPAIR/'model/model_receipt.json')
    name='nygrid_physical_repair_20261015'+('' if label=='final' else '_'+label)
    stage=RELEASE/'staging'/name;archive=RELEASE/(name+'.zip')
    assert not stage.exists() and not archive.exists(),'Choose a new label; existing releases are preserved.'
    stage.mkdir(parents=True)
    for target,row in selected.items():
        dest=stage/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(row['source_path'],dest)
        assert sha(dest)==row['sha256'],target
    relative_links=[]
    for document in stage.rglob('*.md'):
        for href in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',document.read_text(encoding='utf-8')):
            if '://' in href or href.startswith('#'):continue
            target=(document.parent/href.split('#',1)[0]).resolve()
            assert target.is_relative_to(stage.resolve()) and target.exists(),(document,href)
            relative_links.append(dict(document=document.relative_to(stage).as_posix(),target=href))
    files={name:{key:row[key] for key in ['sha256','bytes','role']} for name,row in sorted(selected.items())}
    manifest=dict(schema_version=1,package_kind='physical_repair_current_model_with_map',
        source_model_commit=model['baseline_source_model_commit'],source_model_commit_role='preserved_baseline',
        physical_repair_candidate_sha256=model['physical_repair']['candidate_receipt_sha256'],
        current_model_sha256=model['model_file']['sha256'],created_utc=datetime.now(timezone.utc).isoformat(),
        annual_run=annual['run_label'],profile_shards_byte_identical_to_baseline=True,
        historical_model_versions_included=False,files=files)
    mp=stage/'PACKAGE_MANIFEST.json';mp.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    sums={name:row['sha256'] for name,row in files.items()};sums['PACKAGE_MANIFEST.json']=sha(mp)
    (stage/'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name,digest in sorted(sums.items())),encoding='utf-8')
    extracted=verify_root(stage)
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for path in sorted(stage.rglob('*')):
            if path.is_file():z.write(path,name+'/'+path.relative_to(stage).as_posix())
    zipped=verify_zip(archive)
    receipt=dict(passed=True,archive_path=str(archive),archive_bytes=archive.stat().st_size,archive_sha256=sha(archive),
        stage_path=str(stage),payload_files=len(files),extracted_integrity_check=extracted,archive_integrity_check=zipped,
        physical_repair_candidate_sha256=manifest['physical_repair_candidate_sha256'],model_sha256=manifest['current_model_sha256'],
        selection=selected,relative_markdown_links_checked=relative_links,
        cold_portable_execution='separate fresh extraction validation required')
    (OUT/'package_receipts').mkdir(exist_ok=True)
    (OUT/'package_receipts'/f'{label}_package_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    archive.with_suffix('.sha256.txt').write_text(receipt['archive_sha256']+'  '+archive.name+'\n',encoding='ascii')
    for suffix in ['docx','md']:
        source=OUT/f'docs/NYGRID_2025_PHYSICAL_REPAIR_MODEL_STRUCTURE.{suffix}';dest=RELEASE/source.name
        if dest.exists():assert sha(source)==sha(dest)
        else:shutil.copyfile(source,dest)
    print(json.dumps({k:v for k,v in receipt.items() if k!='selection'},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--label',required=True);build(p.parse_args().label)
