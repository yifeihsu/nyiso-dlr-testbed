"""Verify an extracted handoff or ZIP using only Python's standard library."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import zipfile


def stream_sha(stream):
    digest=hashlib.sha256()
    while block:=stream.read(1024*1024):digest.update(block)
    return digest.hexdigest()


def safe_name(value):
    p=PurePosixPath(value)
    assert value and str(p)!='.' and not p.is_absolute() and '..' not in p.parts and ':' not in value and '\\' not in value, value
    return p


def verify_checksum_table(manifest,manifest_bytes,table_bytes):
    expected={name:r['sha256'] for name,r in manifest['files'].items()}
    expected['PACKAGE_MANIFEST.json']=hashlib.sha256(manifest_bytes).hexdigest()
    lines=table_bytes.decode('utf-8').splitlines();observed={}
    for line in lines:
        digest,name=line.split('  ',1);safe_name(name)
        assert name not in observed,'Duplicate checksum-table path'
        assert len(digest)==64 and all(c in '0123456789abcdef' for c in digest),'Invalid SHA256'
        observed[name]=digest
    assert observed==expected,'SHA256SUMS is incomplete or differs from the package manifest'


def verify_root(root):
    root=Path(root).resolve();manifest_bytes=(root/'PACKAGE_MANIFEST.json').read_bytes();manifest=json.loads(manifest_bytes)
    verify_checksum_table(manifest,manifest_bytes,(root/'SHA256SUMS.txt').read_bytes())
    for name,expected in manifest['files'].items():
        safe_name(name);p=(root/name).resolve();assert p.is_relative_to(root),name
        assert p.is_file() and p.stat().st_size==expected['bytes'],f'Missing or changed size: {name}'
        with p.open('rb') as f:assert stream_sha(f)==expected['sha256'],f'Changed file: {name}'
    return dict(passed=True,kind=manifest['package_kind'],files=len(manifest['files']),
                bytes=sum(r['bytes'] for r in manifest['files'].values()),source_commit=manifest['source_model_commit'],
                checksum_table_and_manifest_digest_verified=True)


def verify_zip(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist();assert len(names)==len(set(names)),'Duplicate ZIP members'
        for name in names:safe_name(name)
        manifests=[n for n in names if n.endswith('/PACKAGE_MANIFEST.json')];assert len(manifests)==1
        prefix=manifests[0][:-len('PACKAGE_MANIFEST.json')]
        manifest_bytes=z.read(manifests[0]);manifest=json.loads(manifest_bytes);expected_names={prefix+x for x in manifest['files']}
        verify_checksum_table(manifest,manifest_bytes,z.read(prefix+'SHA256SUMS.txt'))
        assert set(names)==expected_names|{prefix+'PACKAGE_MANIFEST.json',prefix+'SHA256SUMS.txt'},'Unmanifested archive members'
        for name,expected in manifest['files'].items():
            info=z.getinfo(prefix+name);assert info.file_size==expected['bytes'],name
            with z.open(info) as f:assert stream_sha(f)==expected['sha256'],f'Archive hash mismatch: {name}'
    return dict(passed=True,kind=manifest['package_kind'],files=len(manifest['files']),
                bytes=sum(r['bytes'] for r in manifest['files'].values()),source_commit=manifest['source_model_commit'],
                checksum_table_and_manifest_digest_verified=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--root',type=Path);group.add_argument('--archive',type=Path);a=parser.parse_args()
    print(json.dumps(verify_root(a.root) if a.root else verify_zip(a.archive),indent=2))
