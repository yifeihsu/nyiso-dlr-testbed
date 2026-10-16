"""Independent source reparse and interval-overlap validation of Dover P34.

Does not import the compiler, fit parameters, or read internal interface data.
The independent hourly integration distributes every valid source interval into
its intersected physical-hour bins, rather than looping over source brackets.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,io,json,zipfile
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"output/nygrid_2025_dover_parameters/local_audit"
PTIDS=[625149,625150]


def require(ok,text):
    if not bool(ok):raise ValueError(text)


def sha(path):
    with Path(path).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()


def validate():
    proof_path=OUT/"Dover_P34_input_receipt.json";proof=json.loads(proof_path.read_text())
    require(proof["passed"] and proof["no_internal_interface_observations_read"] and proof["no_impedance_or_phase_fit"],"Source scope changed")
    before=dict(proof["dependencies"])
    for p,h in before.items():require(sha(ROOT/p)==h,"Source dependency changed: "+p)
    for name,h in proof["outputs"].items():require(sha(OUT/name)==h,"Compiler artifact changed: "+name)
    raw=pd.read_csv(OUT/"Dover_P34_raw_2025_with_endpoint.csv.gz",float_precision="round_trip")
    keys=["source_archive","source_member","source_csv_row_1based","point_id"]
    require(not raw.duplicated(keys).any(),"Duplicate extracted source-row identity")
    source=raw.set_index(keys);expected_records=0;calendar=[]
    archives=sorted(p for p in before if p.endswith("ParFlows_csv.zip"))
    require(len(archives)==13,"Monthly source manifest incomplete")
    for p in archives:
        archive_path=ROOT/p
        with zipfile.ZipFile(archive_path) as archive:
            for name in sorted(archive.namelist()):
                if archive_path.name.startswith("2026") and name!="20260101ParFlows.csv":continue
                frame=pd.read_csv(io.BytesIO(archive.read(name)),float_precision="round_trip")
                for ptid in PTIDS:
                    part=frame[frame["Point ID"]==ptid]
                    if not len(part):continue
                    # pandas independently infers the repeated autumn clock
                    # interval from native chronological order in each bank.
                    local=pd.DatetimeIndex(pd.to_datetime(part.Timestamp,format="mixed"))
                    utc=local.tz_localize("America/New_York",ambiguous="infer",nonexistent="raise").tz_convert("UTC")
                    identity=pd.MultiIndex.from_arrays([[archive_path.name]*len(part),[name]*len(part),part.index.to_numpy()+2,[ptid]*len(part)],names=keys)
                    selected=source.loc[identity]
                    require(np.array_equal(pd.DatetimeIndex(pd.to_datetime(selected.timestamp_utc,utc=True)).asi8,utc.asi8),"Independent source UTC/DST mismatch")
                    require(np.array_equal(selected.raw_posted_flow_value.to_numpy(float),part["Flow (MWH)"].to_numpy(float)),"Extracted numeric source value mismatch")
                    expected_records+=len(part)
                    if name.startswith(("20250309","20251102","20251219","20260101")):
                        calendar.append(dict(source_member=name,ptid=ptid,source_records=len(part),unique_UTC_timestamps=utc.nunique(),
                                             first_UTC=utc[0].isoformat(),last_UTC=utc[-1].isoformat(),independent_DST_conversion_passed=True))
    require(expected_records==len(raw)==187324,"Native source coverage/count mismatch")
    with np.load(OUT/"Dover_P34_inputs.npz",allow_pickle=False) as z:arr={k:z[k] for k in z.files}
    times=pd.DatetimeIndex(pd.to_datetime(arr["timestamp_utc"].astype(str),utc=True));origin=int(times.asi8[0]//10**9)
    require(len(times)==8760 and np.array_equal(arr["hour_index"],np.arange(1,8761)) and np.array_equal(arr["ptids"],PTIDS),"Compiled clock/device axes changed")
    results=[]
    for bank,ptid in enumerate(PTIDS):
        selected=raw[raw.point_id==ptid].copy();selected["utc"]=pd.to_datetime(selected.timestamp_utc,utc=True)
        g=selected.groupby("utc",sort=True).raw_posted_flow_value.agg(["mean","min","max","count","size"])
        ts=pd.DatetimeIndex(g.index).asi8//10**9;value=g["mean"].to_numpy()
        seconds=np.zeros(8760);energy=np.zeros(8760)
        for start,end,power,count,size in zip(ts[:-1],ts[1:],value[:-1],g["count"].to_numpy()[:-1],g["size"].to_numpy()[:-1]):
            if end-start>600 or not np.isfinite(power) or count!=size:continue
            lo=max(int(start),origin);hi=min(int(end),origin+8760*3600)
            if hi<=lo:continue
            h0=(lo-origin)//3600;h1=(hi-1-origin)//3600
            for h in range(h0,h1+1):
                overlap=min(hi,origin+(h+1)*3600)-max(lo,origin+h*3600)
                seconds[h]+=overlap;energy[h]+=overlap*power
        q=seconds==3600;means=np.full(8760,np.nan);means[q]=energy[q]/3600
        require(np.array_equal(seconds,arr["coverage_seconds"][:,bank]) and np.array_equal(q,arr["coverage_qualified"][:,bank]),"Independent interval coverage mismatch")
        require(np.array_equal(np.isnan(means),np.isnan(arr["raw_posted_hourly_values"][:,bank])),"Missing-hour policy mismatch")
        error=float(np.max(abs(means[q]-arr["raw_posted_hourly_values"][q,bank]),initial=0.))
        require(error<1e-10,"Independent hourly aggregation mismatch")
        require(np.max(abs(arr["forward_NY_to_CT_model_mw"][q,bank]+float(arr["gamma"])*means[q]),initial=0.)<1e-10,"Sign/gamma conversion differs")
        require(np.max(abs(arr["import_CT_to_NY_model_mw"][q,bank]-float(arr["gamma"])*means[q]),initial=0.)<1e-10,"Import sign differs")
        results.append(dict(ptid=ptid,native_source_records=len(selected),qualified_hours=int(q.sum()),maximum_hourly_value_difference=error,
                            sign_gamma_once_checked=True,missing_channels_not_zero_filled=True))
    post=np.asarray(times>=pd.Timestamp("2025-12-20T04:00:00Z"))
    require(np.array_equal(post,arr["post_full_service"]) and post.sum()==289,"Explicit full-service scenario boundary changed")
    require(np.array_equal(arr["post_full_service_prior_common_qualified"],post&arr["prior_common_comparison_mask"]),"New source quality silently drops an old paired hour")
    require(arr["post_full_service_source_qualified"].sum()==287,"Post-service source coverage differs")
    direction=json.loads(str(arr["direction_metadata_json"]));units=json.loads(str(arr["unit_metadata_json"]))
    require(direction["raw_to_NY_to_CT_model_branch_multiplier"]==[-1,-1] and not direction["historical_2025_sign_effective_date_verified"],"Dover direction dating qualification changed")
    require(not direction["Moses_2024_12_03_annotation_applies_to_Dover"],"Moses annotation incorrectly transferred to Dover")
    require(units["literal_source_column"]=="Flow (MWH)" and units["no_factor12_applied"] and not units["instantaneous_meter_MW_asserted"],"Source unit qualification lost")
    require(not bool(arr["pre_service_zero_means_zero_intertie_flow"]) and not bool(arr["full_P_Q_thermal_qualification"]),"Bypass/thermal limitation promoted")
    transition=raw[(pd.to_datetime(raw.timestamp_utc,utc=True)>=pd.Timestamp("2025-12-19T22:00:00Z")) &
                   (pd.to_datetime(raw.timestamp_utc,utc=True)<pd.Timestamp("2025-12-20T04:00:00Z")) & (abs(raw.raw_posted_flow_value)>1e-12)]
    transition.to_csv(OUT/"Dover_pre_full_service_nonzero_samples.csv",index=False)
    pd.DataFrame(calendar).to_csv(OUT/"Dover_independent_clock_checks.csv",index=False)
    require({p:sha(ROOT/p) for p in before}==before,"Protected source changed during independent validation")
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),independent_source_records_reparsed=expected_records,per_bank_checks=results,
                clock_edge_checks=len(calendar),post_full_service_calendar_hours=289,post_full_service_source_and_old_common_hours=287,
                additional_old_common_hour_drops=0,pre_full_service_nonzero_native_samples=len(transition),
                sign_effective_date_2025_not_proven=True,posted_flow_unit_header_preserved=True,interface_observations_read=False,parameters_fit=False,
                source_dependencies=before,compiler_receipt_sha256=sha(proof_path),compiled_NPZ_sha256=sha(OUT/"Dover_P34_inputs.npz"),
                script_sha256=sha(__file__),source_hashes_unchanged=True,
                outputs={name:sha(OUT/name) for name in ["Dover_pre_full_service_nonzero_samples.csv","Dover_independent_clock_checks.csv"]})
    (OUT/"Dover_P34_independent_validation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ["passed","independent_source_records_reparsed","per_bank_checks","clock_edge_checks","post_full_service_source_and_old_common_hours","additional_old_common_hour_drops","pre_full_service_nonzero_native_samples"]},indent=2))


if __name__=="__main__":validate()
