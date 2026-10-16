"""Compare only four modeled PAR identifiers in two archived public releases."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,io,json,zipfile
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"output/nygrid_2025_p34_qualification/numeric_audit"
FRESH=ROOT/"output/nygrid_2025_p34_qualification/sources/NYISO_OASIS_ParFlows_20251219.csv"
OLD=ROOT/"output/nygrid_2025_moses_audit/exchanges/raw/20251201ParFlows_csv.zip"
MEMBER="20251219ParFlows.csv"
PTIDS=[25118,25119,625149,625150]


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def main():
    before={str(p.relative_to(ROOT)).replace("\\","/"):sha(p) for p in [FRESH,OLD]}
    current=pd.read_csv(FRESH,float_precision="round_trip")
    with zipfile.ZipFile(OLD) as archive:payload=archive.read(MEMBER)
    original=pd.read_csv(io.BytesIO(payload),float_precision="round_trip")
    fields=["Timestamp","Point ID","Flow (MWH)"]
    if list(original.columns)!=fields or list(current.columns)!=fields:raise ValueError("Native schema changed")
    records=[]
    for ptid in PTIDS:
        a=original[original["Point ID"]==ptid].copy();b=current[current["Point ID"]==ptid].copy()
        for x in [a,b]:x["time_ns"]=pd.DatetimeIndex(pd.to_datetime(x.Timestamp,format="mixed")).asi8
        a=a.sort_values(["time_ns","Flow (MWH)"]);b=b.sort_values(["time_ns","Flow (MWH)"])
        same_axis=np.array_equal(a.time_ns.to_numpy(),b.time_ns.to_numpy())
        same_values=same_axis and np.array_equal(a["Flow (MWH)"].to_numpy(),b["Flow (MWH)"].to_numpy())
        records.append(dict(ptid=ptid,frozen_records=len(a),new_download_records=len(b),timestamp_axis_exact=same_axis,
                            posted_values_exact=same_values,maximum_posted_value_difference=float(np.max(abs(a["Flow (MWH)"].to_numpy()-b["Flow (MWH)"].to_numpy()),initial=0.)) if same_axis else None))
    if {p:sha(ROOT/p) for p in before}!=before:raise ValueError("Source changed during publication comparison")
    OUT.mkdir(parents=True,exist_ok=True);pd.DataFrame(records).to_csv(OUT/"December19_publication_comparison.csv",index=False)
    report=dict(passed=all(r["timestamp_axis_exact"] and r["posted_values_exact"] for r in records),created_utc=datetime.now(timezone.utc).isoformat(),
        scope="2025-12-19only;fourmodeledPTIDsonly;notallarchiveversions",modeled_ptids=PTIDS,comparisons=records,
        native_unit_header_unchanged="Flow (MWH)",quantity_unit_or_SCADA_origin_proven=False,
        frozen_zip_member_sha256=hashlib.sha256(payload).hexdigest(),dependencies=before,source_hashes_unchanged=True,
        output_sha256=sha(OUT/"December19_publication_comparison.csv"),script_sha256=sha(__file__))
    (OUT/"publication_drift_check.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
