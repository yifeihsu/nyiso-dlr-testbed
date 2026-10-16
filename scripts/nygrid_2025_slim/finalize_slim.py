"""Verify current slim-case evidence and fingerprint the complete delivery."""
import argparse
import json
from pathlib import Path
import pandas as pd
from replay_slim import ROOT,OUT,sha,require

MANIFEST=OUT/"delivery_manifest.json"


def check(path,key):
    data=json.loads(path.read_text())
    require(data.get("passed",True) is True,"Failed validation: "+str(path))
    for row in data.get(key,[]):
        target=Path(row["path"])
        if not target.is_absolute():target=ROOT/target
        require(target.is_file() and sha(target)==row["sha256"],"Stale validation dependency: "+str(target))
    return data


def finalize(verify=False):
    for name,key in [("construction_validation.json","files"),("annual_validation.json","files"),
                     ("matlab_validation.json","dependencies"),("focused_tests.json","files")]:
        check(OUT/"validation"/name,key)
    for row in pd.read_csv(OUT/"network/source_manifest.csv").itertuples(index=False):
        require(sha(ROOT/row.path)==row.sha256,"Construction source changed: "+row.path)
    replay=check(OUT/"replay/provenance.json","dependencies")
    for row in replay["variants"]:
        require(sha(ROOT/row["file"])==row["sha256"],"Slim replay changed")
        require(sha(ROOT/row["reference_file"])==row["reference_sha256"],"Detailed reference changed")
    score=json.loads((OUT/"comparison/scoring_receipt.json").read_text())
    require(score["replay_receipt_sha256"]==sha(OUT/"replay/provenance.json"),"Scoring receipt changed")
    require(score["code_sha256"]==sha(Path(__file__).with_name("replay_slim.py")),"Scoring code changed")
    diagram=json.loads((OUT/"diagrams/diagram_validation.json").read_text())
    require(diagram["passed"] is True and len(diagram["added_buses"])==8,"Diagram count mismatch")
    for row in diagram["source_files"]:
        require(sha(ROOT/row["path"])==row["sha256"],"Diagram source changed")
    files=[]
    for folder in [OUT,ROOT/"scripts/nygrid_2025_slim"]:
        files.extend(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p!=MANIFEST)
    files.extend([ROOT/"NYGRID_2025_SLIM_DOWNSTATE.md",ROOT/"System Matpower Format/npcc_nygrid_2025_slim_dc.m",
                  ROOT/"System Matpower Format/npcc_nygrid_2025_slim_interfaces.m"])
    entries=[]
    for path in sorted(files):
        require(path.stat().st_size<100*1024**2,"Oversized delivery file")
        entries.append(dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    result=dict(status="verified_148bus_DC_research_alternative",original_buses=140,added_buses=8,NY_buses=54,
        prior191_and_dispatch_preserved=True,files=len(entries),total_bytes=sum(x["bytes"] for x in entries),
        maximum_file_bytes=max(x["bytes"] for x in entries),entries=entries)
    if verify:require(json.loads(MANIFEST.read_text())==result,"Delivery manifest is stale")
    else:MANIFEST.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({k:v for k,v in result.items() if k!="entries"},indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--verify",action="store_true");finalize(p.parse_args().verify)
