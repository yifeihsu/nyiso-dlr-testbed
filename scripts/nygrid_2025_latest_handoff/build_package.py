"""Build one self-contained current-model package from an explicit allowlist."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import shutil
import zipfile
from verify_package import verify_root, verify_zip, safe_name

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_latest_handoff'
SRC=ROOT/'scripts/nygrid_2025_latest_handoff'
RELEASE=ROOT/'deliverables/nygrid_2025_latest_model_20261013'
BASE='2e0fcd5c3f0ae39d04f27a733ce30eb148b0b243'

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def gather():
    selected={}
    def add(source,target,role):
        source=Path(source);safe_name(target);assert source.is_file(),source
        assert target not in selected,target
        selected[target]={'source_path':str(source.resolve()),'bytes':source.stat().st_size,'sha256':sha(source),'role':role}
    for path in sorted((SRC/'runtime').rglob('*.m')):
        add(path,'runtime/'+path.relative_to(SRC/'runtime').as_posix(),'current_runtime')
    assert all('runtime/'+x+'.m' in selected for x in ['setup_nygrid_latest','load_nygrid_latest','run_nygrid_latest_acpf','screen_nygrid_latest_dlr'])
    for name in ['latest_model.mat','profiles_h0001_4380.mat','profiles_h4381_8760.mat','model_receipt.json']:
        add(OUT/'model'/name,'model/'+name,'current_model_data')
    structure=list((OUT/'structure').glob('*'))
    assert any(p.name=='current_structure_inventory.json' for p in structure)
    for path in sorted(structure):
        if path.is_file() and path.suffix in ['.json','.csv','.png','.svg']:
            add(path,'model/structure/'+path.name,'current_structure')
    for name in ['START_HERE.md','DATA_DICTIONARY.md','THIRD_PARTY_NOTICES.md']:
        add(OUT/'docs'/name,name,'current_documentation')
    for suffix in ['docx','md']:
        name='NYGRID_2025_LATEST_MODEL_STRUCTURE.'+suffix
        add(ROOT/name,name,'current_structure_document')
    add(SRC/'verify_package.py','verify_package.py','standalone_integrity_verifier')
    for path in sorted((SRC/'examples').glob('*.m')):
        add(path,'examples/'+path.name,'current_example')
    vendor=read(ROOT/'output/nygrid_2025_dlr_handoff/runtime_audit/vendor_code_closure.json')
    for record in vendor['entries']:
        if record['target'].endswith('/RUNTIME_SUBSET_NOTICE.txt'):continue
        source=Path(record['source_path']);assert sha(source)==record['sha256'],source
        add(source,record['target'],'licensed_vendor_code')
    add(OUT/'docs/MATPOWER_RUNTIME_SUBSET_NOTICE.txt','vendor/matpower8.1/RUNTIME_SUBSET_NOTICE.txt','current_vendor_subset_notice')
    # This is an explicit small receipt allowlist, not an evidence-tree copy.
    for name in ['current_source_and_notices_inventory.json','structure_document_receipt.json',
                 'structure_document_visual_review.json','structure_document_independent_review.json']:
        add(OUT/name,'verification/'+name,'current_provenance_receipt')
    for name in ['runtime_validation_receipt.json','kernel_adaptation_receipt.json']:
        source=OUT/'validation'/name
        if source.exists():add(source,'verification/'+name,'current_runtime_receipt')
    add(OUT/'independent/current_data_review.json','verification/current_data_review.json','independent_current_data_receipt')
    assert not any(x.startswith(('source_archive/','output/','System Matpower Format/','scripts/')) for x in selected)
    return selected

def build(label):
    assert label and all(c.isalnum() or c in '_-' for c in label)
    RELEASE.mkdir(parents=True,exist_ok=True)
    name='nygrid_latest_model_20261013'+('' if label=='final' else '_'+label)
    stage=RELEASE/'staging'/name;archive=RELEASE/(name+'.zip')
    assert not stage.exists(),'Use a new label; retained staging directories are never overwritten.'
    assert not archive.exists(),'Refusing to overwrite an archive.'
    selected=gather();stage.mkdir(parents=True)
    for target,record in selected.items():
        dest=stage/target;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(record['source_path'],dest)
        assert sha(dest)==record['sha256'],target
    files={key:{k:r[k] for k in ['sha256','bytes','role']} for key,r in sorted(selected.items())}
    manifest={'schema_version':1,'package_kind':'latest_model_only','source_model_commit':BASE,
        'created_utc':datetime.now(timezone.utc).isoformat(),'four_dated_states_are_one_model_version':True,
        'historical_models_and_experiment_corpora_included':False,'files':files}
    manifest_path=stage/'PACKAGE_MANIFEST.json';manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    checks={name:r['sha256'] for name,r in files.items()};checks['PACKAGE_MANIFEST.json']=sha(manifest_path)
    (stage/'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name,digest in sorted(checks.items())),encoding='utf-8')
    root_check=verify_root(stage)
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for path in sorted(stage.rglob('*')):
            if path.is_file():z.write(path,name+'/'+path.relative_to(stage).as_posix())
    zip_check=verify_zip(archive)
    receipt={'schema_version':1,'source_model_commit':BASE,'archive_path':str(archive),
        'archive_bytes':archive.stat().st_size,'archive_sha256':sha(archive),'stage_path':str(stage),
        'payload_files':len(files),'payload_bytes':sum(x['bytes'] for x in files.values()),
        'extracted_integrity_check':root_check,'archive_integrity_check':zip_check,
        'selection':selected,'clean_machine_execution':'separate validation required'}
    (OUT/'package_receipts').mkdir(exist_ok=True)
    (OUT/'package_receipts'/(label+'_package_receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    (archive.with_suffix('.sha256.txt')).write_text(receipt['archive_sha256']+'  '+archive.name+'\n',encoding='ascii')
    for suffix in ['docx','md']:
        source=ROOT/('NYGRID_2025_LATEST_MODEL_STRUCTURE.'+suffix);dest=RELEASE/source.name
        if dest.exists():assert sha(dest)==sha(source),'Refusing to overwrite a different released structure document.'
        else:shutil.copyfile(source,dest)
    print(json.dumps({k:v for k,v in receipt.items() if k!='selection'},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--label',required=True)
    build(parser.parse_args().label)
