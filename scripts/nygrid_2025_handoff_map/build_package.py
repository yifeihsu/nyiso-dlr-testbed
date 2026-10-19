"""Add the current offline map to the sealed latest-model handoff archive."""
from pathlib import Path
from datetime import datetime, timezone
from copy import deepcopy
import hashlib
import json
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/nygrid_2025_latest_handoff'))
from verify_package import verify_zip

OUT=ROOT/'output/nygrid_2025_handoff_map'
MAP=ROOT/'output/nygrid_2025_latest_map'
RELEASE=ROOT/'deliverables/nygrid_2025_latest_model_20261013'
ARCHIVE=RELEASE/'nygrid_latest_model_with_map_20261013.zip'
PREFIX='nygrid_latest_model_with_map_20261013/'
MAP_COMMIT='de9a0e3bc5d588bde157c0877d03a08f06743b10'

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def record(path):return {'bytes':path.stat().st_size,'sha256':sha(path)}
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def encoded(value):return (json.dumps(value,indent=2)+'\n').encode('utf-8')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    old_receipt=read(ROOT/'output/nygrid_2025_latest_handoff/package_receipts/final_package_receipt.json')
    base=Path(old_receipt['archive_path'])
    assert record(base)=={'bytes':old_receipt['archive_bytes'],'sha256':old_receipt['archive_sha256']}
    assert verify_zip(base)['passed']
    map_manifest=read(MAP/'DELIVERY_MANIFEST.json')
    html=MAP/'network_map.html';assert record(html)=={k:map_manifest['html'][k] for k in ['bytes','sha256']}
    for name in ['build_receipt.json','interaction_validation.json','browser_visual_review.json','independent_embedded_payload_review.json']:
        assert read(MAP/name)['passed']
        assert record(MAP/name)==map_manifest['files'][(MAP/name).relative_to(ROOT).as_posix()]
    assert read(MAP/'build_receipt.json')['offlineSelfContained']
    assert not read(MAP/'build_receipt.json')['externalRuntimeRequests']
    map_intro='''## Interactive network map

Open **[map/network_map.html](map/network_map.html)** for the current network,
zone labels and saved hourly interface flows. The HTML contains its data,
basemap and runtime; viewing it does not require MATLAB or a data server.

The map includes the 148 retained AC view, detailed corridor view, all eleven
NY zones, seven signed interface flows and the four dated 2025 network states.
Use its UTC date/time, hour index or slider to choose a point. Select an
interface to highlight its current member corridors, or a zone to inspect its
load, loss and net native generation. Model MW and public-scale MW are separate
display options. Unavailable computed hours remain blank.

The map displays saved results and does not recompute a power flow when its
controls change. See [map/README.md](map/README.md) for conventions and
`verification/MAP_PROVENANCE.json` for source and validation identities.

'''
    map_readme='''# Interactive map included with this model

Open [network_map.html](network_map.html) in a modern browser. It is one
self-contained HTML file; no external scripts, tiles or data requests are
needed. MATLAB is required for the electrical runtime, not for viewing the map.

The default point is hour 8508, 21 December 2025 at 16:00 UTC. Use the date/time,
index or slider for any of the 8,760 model hours. The network follows the four
dated topology states. The 148 retained AC view and detailed parent-corridor
view are two representations of the same current model.

All eleven New York accounting zones are labeled. Narrow screens use A-K
letters with full names in the legend. Select a zone for its gross boundary
demand, delivered demand, assigned AC loss and net native generation. Native
generation excludes all 28 external equivalents, including HQ.

The seven interface labels use the frozen signed corridor from-terminal
definition. Select a label to highlight its member corridors. Negative totals
reverse the schematic arrow. Public-scale model MW equals model MW divided by
gamma = 0.30012075175285535. The map does not rescale amperes.

There are 8,170 equation/loss-qualified saved hours. Computed interface,
delivered-load and loss values remain unavailable outside that cohort; known
source inputs can remain available on source-qualified failed hours. A source-
excluded hour has no supplied model power values. Operating-limit qualification
is separate and remains false in the saved annual results.

Zone anchors and connection paths are schematic model geography, not official
zone polygons or surveyed routes. The seven cuts are model diagnostics with
uncertified physical NYISO meter membership. Reduced AC couplings have no
individual conductor flow or rating. Proxies 78, 79 and 82 remain unlocated.

The map and electrical input files are included in the package checksum table.
Run the root `verify_package.py --root .` to verify both. The source and prior
browser/DOM validation identities are in `verification/MAP_PROVENANCE.json`.
Browser QA used a loopback preview; the Codex app browser restricts direct file-
protocol navigation. The HTML itself has no external runtime dependencies.
'''
    provenance={'schema_version':1,'scope':'Exact current offline map included with the latest model',
        'map_source_commit':MAP_COMMIT,'model_package_source_commit':map_manifest['source_model_commit'],
        'HTML':{'package_path':'map/network_map.html',**record(html)},
        'source_map_delivery_manifest_sha256':sha(MAP/'DELIVERY_MANIFEST.json'),
        'source_qualified_hours':8651,'equation_loss_qualified_hours':8170,'hour_slots':8760,
        'NY_zones':11,'modeled_interfaces':7,'DOM_checks':28,'native_browser_checks':13,
        'offline_self_contained':True,'external_runtime_requests':False,
        'new_PF_or_OPF_run_for_packaging':False,
        'source_receipts':{name:sha(MAP/name) for name in ['build_receipt.json','interaction_validation.json',
            'browser_visual_review.json','independent_embedded_payload_review.json']}}
    with zipfile.ZipFile(base) as z:
        old_names=z.namelist();manifest_name=next(n for n in old_names if n.endswith('/PACKAGE_MANIFEST.json'))
        old_prefix=manifest_name[:-len('PACKAGE_MANIFEST.json')]
        old_manifest=json.loads(z.read(manifest_name));assert len(old_manifest['files'])==666
        start_original=z.read(old_prefix+'START_HERE.md');start=start_original.decode('utf-8')
        anchor='## Requirements and setup';assert start.count(anchor)==1
        newline='\r\n' if '\r\n' in start else '\n'
        start=start.replace(anchor,map_intro.replace('\n',newline)+anchor,1).encode('utf-8')
        additions={'map/network_map.html':html.read_bytes(),'map/README.md':map_readme.encode('utf-8'),
            'verification/MAP_PROVENANCE.json':encoded(provenance)}
        changes={'START_HERE.md':start}
        files=deepcopy(old_manifest['files'])
        for name,blob in {**changes,**additions}.items():
            files[name]={'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),
                'role':'current_documentation' if name.endswith('.md') else 'current_offline_map' if name.endswith('.html') else 'map_provenance'}
        unchanged=[name for name in old_manifest['files'] if name not in changes]
        assert len(unchanged)==665 and len(files)==669
        assert all(files[name]==old_manifest['files'][name] for name in unchanged)
        manifest={'schema_version':1,'package_kind':'latest_model_with_interactive_map',
            'source_model_commit':old_manifest['source_model_commit'],'map_source_commit':MAP_COMMIT,
            'created_utc':datetime.now(timezone.utc).isoformat(),'four_dated_states_are_one_model_version':True,
            'historical_models_and_experiment_corpora_included':False,
            'base_archive_sha256':sha(base),'base_payload_files_unchanged':665,
            'modified_base_files':list(changes),'added_files':list(additions),'files':files}
        manifest_bytes=encoded(manifest)
        checks={name:r['sha256'] for name,r in files.items()};checks['PACKAGE_MANIFEST.json']=hashlib.sha256(manifest_bytes).hexdigest()
        checksum_bytes=''.join(f'{digest}  {name}\n' for name,digest in sorted(checks.items())).encode('ascii')
        partial=ARCHIVE.with_suffix('.zip.partial');assert not ARCHIVE.exists() and not partial.exists(),'Refusing to overwrite a retained archive.'
        with zipfile.ZipFile(partial,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as target:
            for name in sorted(old_manifest['files']):target.writestr(PREFIX+name,changes[name] if name in changes else z.read(old_prefix+name))
            for name,blob in additions.items():target.writestr(PREFIX+name,blob)
            target.writestr(PREFIX+'PACKAGE_MANIFEST.json',manifest_bytes)
            target.writestr(PREFIX+'SHA256SUMS.txt',checksum_bytes)
    verification=verify_zip(partial);assert verification['passed']
    partial.rename(ARCHIVE)
    assert record(base)=={'bytes':old_receipt['archive_bytes'],'sha256':old_receipt['archive_sha256']}
    (OUT/'START_HERE.md').write_bytes(start)
    (OUT/'MAP_README.md').write_text(map_readme,encoding='utf-8',newline='\n')
    (OUT/'MAP_PROVENANCE.json').write_bytes(encoded(provenance))
    (OUT/'PACKAGE_MANIFEST.json').write_bytes(manifest_bytes)
    result={'passed':True,'base_archive':{'path':base.relative_to(ROOT).as_posix(),**record(base)},
        'archive':{'path':ARCHIVE.relative_to(ROOT).as_posix(),**record(ARCHIVE)},
        'payload_files':len(files),'payload_bytes':sum(r['bytes'] for r in files.values()),
        'base_payload_files_unchanged':len(unchanged),'modified_base_files':list(changes),'added_files':list(additions),
        'map_HTML_bytes_identical':True,'runtime_model_and_structure_documents_unchanged':True,
        'archive_verification':verification,'fresh_extraction_verification':'separate receipt',
        'sources':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in [base,html,MAP/'DELIVERY_MANIFEST.json',Path(__file__)]]}
    (OUT/'build_receipt.json').write_bytes(encoded(result))
    ARCHIVE.with_suffix('.sha256.txt').write_text(result['archive']['sha256']+'  '+ARCHIVE.name+'\n',encoding='ascii')
    print(json.dumps({k:v for k,v in result.items() if k!='sources'},indent=2))

if __name__=='__main__':main()
