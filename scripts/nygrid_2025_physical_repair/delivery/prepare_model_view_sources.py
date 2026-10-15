"""Prepare isolated structure/map builders from the preserved current builders."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[3]
SRC=Path(__file__).parent
OUT=ROOT/'output/nygrid_2025_physical_repair/delivery'
OLD=ROOT/'scripts/nygrid_2025_latest_handoff'
MAP=ROOT/'scripts/nygrid_2025_latest_map'


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write(name,source,text):
    target=SRC/name;assert not target.exists(),target
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8',newline='\n')
    return dict(source=source.relative_to(ROOT).as_posix(),source_sha256=sha(source),
                target=target.relative_to(ROOT).as_posix(),target_sha256=sha(target))


def main():
    rows=[]
    source=OLD/'export_current_structure.m';text=source.read_text()
    text=text.replace('root=fileparts(fileparts(fileparts(mfilename(\'fullpath\'))));',
                      'root=fileparts(fileparts(fileparts(fileparts(mfilename(\'fullpath\')))));')
    start=text.index("addpath(fullfile(root,'scripts','nygrid_2025_dlr_handoff','runtime'));")
    end=text.index("if ~isfolder(out),mkdir(out);end",start)
    text=text[:start]+"runtime=fullfile(root,'scripts','nygrid_2025_physical_repair','delivery','runtime');addpath(runtime);\nsetup_nygrid_latest(root,'C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower');\ndata=nylatest_data();\nout=fullfile(root,'output','nygrid_2025_physical_repair','delivery','structure_inputs');\n"+text[end:]
    text=text.replace("m=ac_loss_prepare_case(npcc_nygrid_2025_ac(hour),'released_equivalent');",'m=load_nygrid_latest(hour);')
    for old,new in [('ac_loss_prepare_policy','nylatest_prepare_policy'),('compact_ac_build','nylatest_compact_build'),('nygrid_rx_thermal_candidates','nylatest_thermal_candidates')]:text=text.replace(old,new)
    text=text.replace('external_current_rows=m.userdata.ac_system.external_current_generator_rows;','external_current_rows=find(data.external.generator_mask);')
    text=text.replace('original_external_parent_rows=m.userdata.ac_system.external_parent_generator_rows;',
        "original_external_parent_rows=(244:271)'; % Frozen identity map of the 28 external equivalents.\n    reactor_ledger=m.userdata.ac_sections.reactor_ledger;\n    reactor_BS_delta_all_buses=m.userdata.ac_sections.reactor_BS_delta_all_buses;\n    reactor_BS_bus_ids=m.userdata.ac_sections.reactor_BS_bus_ids;\n    physical_repair=m.userdata.physical_repair;")
    text=text.replace("'gamma','timestamp_utc','compact_validation'", "'gamma','timestamp_utc','reactor_ledger','reactor_BS_delta_all_buses','reactor_BS_bus_ids','physical_repair','compact_validation'")
    rows.append(write('export_current_structure.m',source,text))
    source=OLD/'build_current_structure.py';text=source.read_text()
    text=text.replace('parents[2]','parents[3]').replace("NS=ROOT/'output/nygrid_2025_latest_handoff'", "NS=ROOT/'output/nygrid_2025_physical_repair/delivery'")
    text=text.replace("scope='Current model structure and field semantics only; no model-evolution or modification narrative',", "scope='Current physical-repair model structure and field semantics',\n        physical_repair_receipt=json.loads((ROOT/'output/nygrid_2025_physical_repair/candidate_receipt.json').read_text()),\n        physical_repair_receipt_sha256=record(ROOT/'output/nygrid_2025_physical_repair/candidate_receipt.json')['sha256'],")
    rows.append(write('build_current_structure.py',source,text))
    for name in ['build_geography_data.py','build_network_map.py','build_interface_definitions.py','export_annual_data.py']:
        source=MAP/name;text=source.read_text().replace('parents[2]','parents[4]')
        text=text.replace('output/nygrid_2025_latest_map','output/nygrid_2025_physical_repair/delivery/map')
        text=text.replace('output/nygrid_2025_latest_handoff/structure','output/nygrid_2025_physical_repair/delivery/structure')
        rows.append(write('map/'+name,source,text))
    # Preserve the exact baseline runtime used by the annual driver before any promotion.
    snapshot=OUT/'preservation/baseline_runtime.zip';assert not snapshot.exists()
    files=sorted((OLD/'runtime').rglob('*.m'));entries=[]
    with zipfile.ZipFile(snapshot,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            name=path.relative_to(OLD).as_posix();archive.write(path,name)
            entries.append(dict(path=path.relative_to(ROOT).as_posix(),archive_path=name,sha256=sha(path)))
    with zipfile.ZipFile(snapshot) as archive:
        assert all(hashlib.sha256(archive.read(e['archive_path'])).hexdigest()==e['sha256'] for e in entries)
    receipt=dict(passed=True,runtime_archive=snapshot.relative_to(ROOT).as_posix(),archive_sha256=sha(snapshot),
                 files=entries,baseline_model_receipt_sha256=sha(ROOT/'output/nygrid_2025_latest_handoff/model/model_receipt.json'))
    (OUT/'preservation/baseline_runtime_snapshot.json').write_text(json.dumps(receipt,indent=2)+'\n')
    (OUT/'model_view_source_preparation.json').write_text(json.dumps(dict(passed=True,entries=rows),indent=2)+'\n')
    print(json.dumps(dict(passed=True,builders=len(rows),preserved_runtime_files=len(files))))


if __name__=='__main__':main()
