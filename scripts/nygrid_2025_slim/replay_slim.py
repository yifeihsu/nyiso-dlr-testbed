"""Replay the small-bus alternative with the frozen fleet and dispatch.

Only new, zero-injection station detail is eliminated. Original NPCC buses,
per-device PG/bounds and four signed DC schedules remain unchanged. Interface
observations are read only after the paired numerical replay has finished.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_slim"
BASELINE = ROOT / "output/nygrid_2025_dispatch/dispatch"
DETAIL = ROOT / "output/nygrid_2025_downstate"
sys.path.insert(0,str(ROOT / "scripts/nygrid_2019"))
from replay_dc import network, predict

NAMES = ["DYSINGER EAST","WEST CENTRAL","TOTAL EAST","MOSES SOUTH","CENTRAL EAST - VC","UPNY CONED","SPR/DUN-SOUTH"]


def require(value,message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def state_schedule(times, dated):
    if not dated:
        return np.full(len(times),"refined_2025_case",object)
    states=np.full(len(times),"refined_2025_pre_may_case",object)
    for date,state in [("2025-05-21T04:00:00Z","refined_2025_may21_case"),
                       ("2025-05-30T04:00:00Z","refined_2025_may30_case"),
                       ("2025-12-20T04:00:00Z","refined_2025_case")]:
        states[np.asarray(times).astype(str)>=date]=state
    return states


def replay(folder=OUT):
    folder=Path(folder).resolve();output=folder/"replay";output.mkdir(parents=True,exist_ok=True)
    data=loadmat(BASELINE/"dispatch.mat",simplify_cells=True)
    source_receipt=json.loads((DETAIL/"replay/provenance.json").read_text())
    for record in source_receipt["dependencies"]:
        require(sha(ROOT/record["path"])==record["sha256"],"Frozen source dependency changed: "+record["path"])
    n=loadmat(folder/"network/network_cases.mat",simplify_cells=True)
    gamma=float(data["gamma"]);require(gamma==float(n["gamma"]),"Gamma changed")
    ids=np.asarray(n["kept_bus_ids"],int);nb=len(ids)
    require(nb==148 and np.array_equal(ids[:140],np.arange(1,141)),"Original buses missing or wrong addition count")
    valid=np.asarray(data["dispatch_qualified"],bool);hours=np.asarray(data["hour_index"],int)
    times=np.asarray(data["timestamp_utc"]).astype(str)
    require(valid.sum()==8663 and np.array_equal(hours,np.arange(1,8761)),"Frozen cohort changed")
    loads=np.zeros((8760,nb));loads[:,:140]=data["bus_pd"]
    pg=np.asarray(data["gen_pg"]);dc=np.asarray(data["dc_pf"])
    summaries=[]
    for variant,dated,reference_name in [("topology_dated",True,"upgrades_dated"),("topology_year_end",False,"upgrades_year_end")]:
        reference_path=DETAIL/"replay"/(reference_name+".mat")
        reference_record=next(r for r in source_receipt["variants"] if r["variant"]==reference_name)
        require(sha(reference_path)==reference_record["sha256"],"191-bus reference replay changed")
        ref=loadmat(reference_path,simplify_cells=True)
        require(np.array_equal(np.asarray(ref["qualified"],bool),valid),"Source reference cohort changed")
        states=state_schedule(times,dated)
        require(np.array_equal(states,np.asarray(ref["network_state_ids"]).astype(str)),"Chronology differs from191bus reference")
        nl=len(n[states[0]]["branch"])
        flow=np.full((8760,nl),np.nan);angle=np.full((8760,nb),np.nan);interfaces=np.full((8760,7),np.nan)
        metrics={key:np.full(8760,np.nan) for key in ["nodal_residual_mw","slack_change_mw","reference_interface_error_mw","reference_recovered_branch_error_mw","reference_angle_error_deg"]}
        for key in sorted(set(states)):
            ix=np.flatnonzero(valid&(states==key));case=copy.deepcopy(n[key])
            rec=n["recovery"][key.removesuffix("_case")]
            result=predict(network(case),loads[ix],pg[ix],dc[ix])
            delta=np.max(abs(result["result_pg"]-pg[ix]),axis=1)
            require(delta.max()<1e-7,"Reduction would need redispatch")
            a=result["angle_deg"]
            lookup={int(v):j for j,v in enumerate(ids)}
            refs=np.array([lookup[int(v)] for v in np.asarray(data["reference_bus"])[ix]])
            a-=a[np.arange(len(ix)),refs][:,None]
            radians=np.deg2rad(a)
            recovered=radians@np.asarray(rec["branch_angle_matrix"]).T+np.asarray(rec["branch_flow_offset"])
            interface=radians@np.asarray(rec["interface_angle_matrix"]).T+np.asarray(rec["interface_flow_offset"])
            lifted=radians@np.asarray(rec["angle_lift"]).T+np.asarray(rec["angle_offset"])
            errors=dict(reference_recovered_branch_error_mw=np.max(abs(recovered-ref["branch_pf"][ix]),axis=1),
                reference_interface_error_mw=np.max(abs(interface-ref["interface_pf"][ix]),axis=1),
                reference_angle_error_deg=np.max(abs(np.rad2deg(lifted)-ref["bus_va"][ix]),axis=1))
            require(all(v.max()<1e-7 for v in errors.values()),"Slim/full DC response mismatch")
            flow[ix]=result["flow"];angle[ix]=a;interfaces[ix]=interface
            metrics["nodal_residual_mw"][ix]=result["nodal_residual_mw"];metrics["slack_change_mw"][ix]=delta
            for metric,values in errors.items():metrics[metric][ix]=values
        path=output/(variant+".mat")
        savemat(path,dict(hour_index=hours,timestamp_utc=times.astype(object),qualified=valid,network_state_ids=states,
            branch_pf=flow,bus_va=angle,interface_pf=interfaces,reference_bus=data["reference_bus"],gamma=gamma,
            kept_bus_ids=ids,**metrics),do_compression=True,oned_as="column")
        item=dict(variant=variant,qualified_hours=int(valid.sum()),missing_source_hours=int((~valid).sum()),
            buses=nb,added_buses=nb-140,branch_records=nl,reference_variant=reference_name,
            file=path.relative_to(ROOT).as_posix(),sha256=sha(path),reference_file=reference_path.relative_to(ROOT).as_posix(),reference_sha256=sha(reference_path),
            **{"maximum_"+k:float(np.nanmax(v)) for k,v in metrics.items()})
        summaries.append(item);print(json.dumps(item),flush=True)
    pd.DataFrame(summaries).to_csv(output/"replay_summary.csv",index=False,lineterminator="\n")
    files=[BASELINE/"dispatch.mat",BASELINE/"dispatch_bounds.mat",DETAIL/"replay/provenance.json",
           folder/"network/network_cases.mat",Path(__file__),ROOT/"scripts/nygrid_2019/replay_dc.py"]
    receipt=dict(status="complete_fixed_dispatch_slim_replay",original_buses=140,added_buses=8,total_buses=148,
        original_NY_buses=46,result_NY_buses=54,external_buses=94,qualified_hours=8663,missing_source_hours=97,
        inputs_redispatched_or_relocated=False,observations_used_for_construction=False,
        interface_definition="recovered191buslegacyzonefunctionals;not_naive_reduced_graph_cut",variants=summaries,
        dependencies=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in files])
    (output/"provenance.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8",newline="\n")
    return receipt


def score(folder=OUT):
    folder=Path(folder).resolve();output=folder/"comparison";output.mkdir(parents=True,exist_ok=True)
    receipt=json.loads((folder/"replay/provenance.json").read_text())
    base=loadmat(BASELINE/"dispatch.mat",simplify_cells=True,variable_names=["dispatch_qualified","gamma","timestamp_utc"])
    old=loadmat(BASELINE/"dispatch_network.mat",simplify_cells=True,variable_names=["inherited_interface_pf"])
    observations=ROOT/"output/nygrid_2025_inputs/load_source/interface_wide.csv"
    actual=pd.read_csv(observations);q=np.asarray(base["dispatch_qualified"],bool);gamma=float(base["gamma"])
    require(np.array_equal(actual.timestamp_utc.astype(str),np.asarray(base["timestamp_utc"]).astype(str)),"Observation timestamps differ")
    y=actual[NAMES].to_numpy(float);require(np.isfinite(y[q]).all(),"Observation missing on frozen cohort")
    predictions={"original140":old["inherited_interface_pf"]}
    for item in receipt["variants"]:
        require(sha(ROOT/item["file"])==item["sha256"],"Replay changed before scoring")
        predictions[item["reference_variant"]+"_191bus"]=loadmat(ROOT/item["reference_file"],simplify_cells=True,variable_names=["interface_pf"])["interface_pf"]
        predictions[item["variant"]+"_148bus"]=loadmat(ROOT/item["file"],simplify_cells=True,variable_names=["interface_pf"])["interface_pf"]
    rows=[]
    for name,values in predictions.items():
        for j,interface in enumerate(NAMES):
            error=values[q,j]/gamma-y[q,j]
            rows.append(dict(variant=name,interface=interface,hours=int(q.sum()),mae_public_equivalent_mw=float(abs(error).mean()),
                rmse_public_equivalent_mw=float(np.sqrt(np.mean(error**2))),bias_public_equivalent_mw=float(error.mean()),
                wape_percent=float(100*abs(error).sum()/abs(y[q,j]).sum()),observations_used_to_fit_model=False))
    pd.DataFrame(rows).to_csv(output/"interface_summary.csv",index=False,lineterminator="\n")
    (output/"scoring_receipt.json").write_text(json.dumps(dict(qualified_hours=8663,observations_used_only_posthoc=True,
        observations_sha256=sha(observations),replay_receipt_sha256=sha(folder/"replay/provenance.json"),code_sha256=sha(Path(__file__))),indent=2)+"\n",encoding="utf-8",newline="\n")
    print(pd.DataFrame(rows).loc[lambda f:f.interface.isin(NAMES[-2:])].to_string(index=False))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--folder",type=Path,default=OUT)
    args=parser.parse_args();replay(args.folder);score(args.folder)
