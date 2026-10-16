"""Prepare/finalize a cold MATLAB smoke from an OS-temp ZIP extraction."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from verify_package import safe_name,verify_root,verify_zip

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_physical_repair/delivery'


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def prepare():
    receipt=read(OUT/'package_receipts/final_package_receipt.json');archive=Path(receipt['archive_path'])
    assert sha(archive)==receipt['archive_sha256'];verify_zip(archive)
    base=Path(tempfile.mkdtemp(prefix='nygrid_physical_repair_'));assert not base.is_relative_to(ROOT)
    with zipfile.ZipFile(archive) as z:
        roots=set()
        for row in z.infolist():
            name=safe_name(row.filename);target=base.joinpath(*name.parts).resolve();assert target.is_relative_to(base)
            roots.add(name.parts[0]);target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(row) as incoming,target.open('wb') as outgoing:shutil.copyfileobj(incoming,outgoing)
    assert len(roots)==1;package=base/next(iter(roots));integrity=verify_root(package)
    results=base/'results';results.mkdir()
    quote=lambda p:p.as_posix().replace("'","''")
    script=base/'check_package.m'
    batch="addpath('"+quote(package/'runtime')+"'); check=smoke_nygrid_latest('"+quote(results)+"'); assert(check.passed);"
    script.write_text(batch+'\n',encoding='utf-8')
    evidence=dict(archive_path=str(archive),archive_sha256=receipt['archive_sha256'],package_root=str(package),
        temp_root=str(base),result_root=str(results),script_path=str(script),matlab_batch_command=batch,extracted_integrity=integrity)
    write(OUT/'validation/portable_extraction_start.json',evidence)
    print(json.dumps(evidence,indent=2))


def finish():
    start=read(OUT/'validation/portable_extraction_start.json');package=Path(start['package_root'])
    results=Path(start['result_root']);smoke=read(results/'smoke_receipt.json')
    assert smoke['passed'] and smoke['test_count']==20
    assert Path(smoke['setup']['package_root']).resolve()==package.resolve()
    assert not smoke['unapproved_executed_files'] and not smoke['unapproved_search_paths']
    integrity=verify_root(package);archive=Path(start['archive_path']);assert sha(archive)==start['archive_sha256']
    assert smoke['setup']['model_sha256']==read(OUT.parent/'model/model_receipt.json')['model_file']['sha256']
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),archive_path=start['archive_path'],
        archive_sha256=start['archive_sha256'],extraction_outside_research_checkout=True,package_root=str(package),
        integrity_after_cold_execution=integrity,smoke_test_count=smoke['test_count'],smoke_receipt=smoke,
        optional_optimization_toolbox_required=False,baseline_model_builder_required=False,
        fresh_annual_replay_claimed=False,OPF_claimed=False)
    write(OUT/'validation/portable_extraction_review.json',report)
    write(archive.with_suffix('.portable-check.json'),report)
    print(json.dumps(dict(passed=True,archive_sha256=report['archive_sha256'],tests=smoke['test_count'],package_root=str(package))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['prepare','finish']);args=p.parse_args()
    prepare() if args.operation=='prepare' else finish()
