"""Independent all-hour branch/KCL and posthoc score audit of sealed overlays.

No production network, prediction, dispatch, reduction or score helper is
imported. Annual equations are completed and written before observations are
opened for the separate metric check. No parameter or operating input is edited.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"output/nygrid_2025_line_parameters"
WEST=ROOT/"output/nygrid_2025_western_audit"
BASE=ROOT/"output/nygrid_2025_dispatch/dispatch"
NAMES=["DYSINGER EAST","WEST CENTRAL","TOTAL EAST","MOSES SOUTH","CENTRAL EAST - VC","UPNY CONED","SPR/DUN-SOUTH"]
ZONE_PAIRS=[("A","B"),("B","C"),("ABCDE","FGHIJK"),("D","E"),("E","F"),("ABCDEFG","HIJK"),("I","J")]
TOL=1e-7


def require(ok,text):
    if not bool(ok):raise ValueError(text)


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def read(path):return json.loads(Path(path).read_text())


def maxabs(value):return float(np.max(np.abs(value),initial=0.))


def compare(a,b,text,tol=TOL):
    a,b=np.asarray(a),np.asarray(b)
    require(a.shape==b.shape and np.isfinite(a).all() and np.isfinite(b).all(),text+" axis/nonfinite failure")
    error=maxabs(a-b);require(error<=tol,text+" error "+str(error));return error


def verify_manifest(items):
    require(items and len({item["path"] for item in items})==len(items),"Empty/duplicate dependency manifest")
    result={}
    for item in items:
        require(sha(ROOT/item["path"])==item["sha256"],"Changed dependency: "+item["path"])
        result[item["path"]]=item["sha256"]
    return result


def system(case,generator_buses):
    bus=np.asarray(case["bus"],float);branch=np.array(case["branch"],float,copy=True)
    require(np.array_equal(branch[210,:2],[48,100]) and branch[210,10]==1,"Original controlled aggregate record changed")
    branch[210,10]=0
    ids=bus[:,0].astype(int);lookup={v:j for j,v in enumerate(ids)}
    require(len(lookup)==len(ids),"Duplicate bus ID")
    f=np.array([lookup[int(v)] for v in branch[:,0]]);t=np.array([lookup[int(v)] for v in branch[:,1]])
    rows=np.arange(len(branch));C=csr_matrix((np.r_[np.ones(len(branch)),-np.ones(len(branch))],(np.r_[rows,rows],np.r_[f,t])),shape=(len(branch),len(bus)))
    active=branch[:,10]==1;tap=np.where(branch[:,8]==0,1.,branch[:,8])
    graph=csr_matrix((np.ones(2*active.sum()),(np.r_[f[active],t[active]],np.r_[t[active],f[active]])),shape=(len(bus),len(bus)))
    require(connected_components(graph,directed=False)[0]==1,"Controlled AC graph disconnected")
    k=np.zeros(len(branch));k[active]=float(case["baseMVA"])/(branch[active,3]*tap[active])
    G=csr_matrix((np.asarray(case["gen"])[:,7],(np.arange(len(generator_buses)),[lookup[int(v)] for v in generator_buses])),shape=(len(generator_buses),len(bus)))
    old_dc=np.asarray(case["dcline"]);require(old_dc.shape==(4,17) and np.all(old_dc[:,15:17]==0),"Original four lossless transfers changed")
    D=np.zeros((6,len(bus)))
    for j,row in enumerate(old_dc):D[j,lookup[int(row[0])]]=-row[2];D[j,lookup[int(row[1])]]=row[2]
    D[4:,lookup[100]]=-1;D[4:,lookup[48]]=1
    return dict(bus=bus,branch=branch,ids=ids,lookup=lookup,f=f,t=t,k=k,C=C,G=G,D=D)


def branch_flows(net,theta):
    return (theta[:,net["f"]]-theta[:,net["t"]]-np.deg2rad(net["branch"][:,9]))*net["k"]


def legacy_operator(net,zones):
    matrix=np.zeros((7,len(net["branch"])))
    for i,(left,right) in enumerate(ZONE_PAIRS):
        for j,row in enumerate(net["branch"]):
            a,b=zones[int(row[0])],zones[int(row[1])]
            matrix[i,j]=row[10]*(int(a in set(left) and b in set(right))-int(b in set(left) and a in set(right)))
    return matrix


def annual():
    replay_path=OUT/"replay/replay_receipt.json";replay=read(replay_path)
    require(replay["passed"] and replay["fixed_hours"]==8651 and not replay["internal_interface_observations_read"],"Unsealed or unqualified replay")
    require(replay["nominal_parameters_chosen_before_scores"] and not replay["complete_physical_flowgate_validation"],"Replay scope flags changed")
    deps=verify_manifest(replay["dependencies"])
    deps.update(verify_manifest([replay["fixture_file"]]))
    validation_path=OUT/"validation/independent_parameter_overlay_validation.json"
    prior=read(validation_path);require(prior["passed"],"Prior parameter/matrix validation failed")
    for path,digest in prior["dependencies"].items():require(sha(ROOT/path)==digest,"Independent matrix validation is stale: "+path)
    deps[str(validation_path.relative_to(ROOT)).replace("\\","/")]=sha(validation_path)
    for path in [replay_path,Path(__file__)]:deps[str(path.relative_to(ROOT)).replace("\\","/")]=sha(path)
    d=loadmat(BASE/"dispatch.mat",simplify_cells=True,variable_names=["hour_index","timestamp_utc","bus_pd","bus_qd","dc_pf","gamma","reference_bus"])
    dispatch=loadmat(WEST/"dispatch/all_boundary_actual_dispatch.mat",simplify_cells=True,variable_names=["gen_pg","qualified","timestamp_utc"])
    reference=loadmat(WEST/"replay/dated_combined.mat",simplify_cells=True,variable_names=["bus_va","interface_pf","network_state_ids","common_scoring_mask","corrected_generator_buses","qualified"])
    bounds=loadmat(BASE/"dispatch_bounds.mat",simplify_cells=True,variable_names=["gen_pmin","gen_pmax"])
    register=pd.read_csv(WEST/"corrected/model_generator_register.csv",keep_default_na=False)
    q=np.load(WEST/"replay/paired_common_mask.npy",allow_pickle=False)
    require(q.dtype==bool and q.shape==(8760,) and q.sum()==8651,"Frozen cohort differs")
    require(np.array_equal(q,np.asarray(reference["common_scoring_mask"],bool)),"Saved original common mask differs")
    require(np.asarray(dispatch["qualified"],bool)[q].all() and np.asarray(reference["qualified"],bool)[q].all(),"Fixed cohort includes unqualified operating input")
    times=np.asarray(d["timestamp_utc"]).astype(str);gamma=float(d["gamma"]);pg=np.asarray(dispatch["gen_pg"])
    require(np.array_equal(times,np.asarray(dispatch["timestamp_utc"]).astype(str)),"Dispatch clock differs")
    generator_buses=register.bus_id.to_numpy(int)
    require(np.array_equal(register.gen_row,np.arange(1,1465)) and np.array_equal(generator_buses,reference["corrected_generator_buses"]),"Generator identity/landing axis differs")
    pd148=np.pad(d["bus_pd"],((0,0),(0,8)));qd148=np.pad(d["bus_qd"],((0,0),(0,8)))
    with np.load(ROOT/"output/nygrid_2025_par_controls/controls/inputs.npz",allow_pickle=False) as par:
        require(np.array_equal(par["timestamp_utc"].astype(str),times) and float(par["gamma"])==gamma,"PAR source clock/scale differs")
        dc=np.column_stack([d["dc_pf"],par["observed_model_mw"]])
        compare(par["observed_model_mw"][q],par["observed_public_mw"][q]*gamma,"PAR scaling once",1e-12)
        require(np.asarray(par["observed_replay_qualified"],bool)[q].all(),"Unqualified PAR hour")
    require(pg.shape==(8760,1464) and dc.shape==(8760,6) and np.isfinite(pg[q]).all() and np.isfinite(dc[q]).all(),"Operating array axes/nonfinite values")
    lower=np.maximum(bounds["gen_pmin"][q,:1436]-pg[q,:1436],0);upper=np.maximum(pg[q,:1436]-bounds["gen_pmax"][q,:1436],0)
    bound_error=max(maxabs(lower),maxabs(upper));require(bound_error<TOL,"Native dispatch bound violated")
    states=np.asarray(reference["network_state_ids"]).astype(str);refbus=np.asarray(d["reference_bus"],int)-1
    fixtures=loadmat(OUT/"replay/matlab_fixtures.mat",simplify_cells=True)["fixtures"]
    fixtures=[fixtures] if isinstance(fixtures,dict) else list(fixtures)
    scenarios={item["scenario_name"]:item for item in replay["scenarios"]}
    require(len(scenarios)==5 and "identity_reference" in scenarios and "engineering_nominal" in scenarios,"Replay scenario scope differs")
    records=[];fixture_checks=[];saved={};summaries=[]
    for name,item in scenarios.items():
        path=ROOT/item["path"];require(sha(path)==item["sha256"],"Annual saved scenario changed")
        deps[item["path"]]=item["sha256"]
        with np.load(path,allow_pickle=False) as z:data={k:z[k] for k in z.files}
        require(np.array_equal(data["hour_index"],np.arange(1,8761)) and np.array_equal(data["timestamp_utc"].astype(str),times),"Replay time axis differs")
        require(data["qualified"].dtype==bool and np.array_equal(data["qualified"],q) and float(data["gamma"])==gamma,"Replay cohort/scale differs")
        require(np.array_equal(data["network_state_ids"].astype(str),states),"Replay topology timeline differs")
        for field in ["bus_va","interface_pf","F84_line_pf_model_mw","nodal_residual_mw","slack_change_mw"]:
            require(np.isfinite(data[field][q]).all() and np.isnan(data[field][~q]).all(),"Replay missing-hour policy differs: "+field)
        require(maxabs(data["bus_va"][q][np.arange(q.sum()),refbus[q]])<1e-12,"Reference-angle gauge differs")
        require(maxabs(data["slack_change_mw"][q])<TOL and maxabs(data["nodal_residual_mw"][q])<TOL,"Recorded balance/slack check failed")
        folder=OUT/"overlays"/name
        full=loadmat(folder/"full191_network_cases.mat",simplify_cells=True);slim=loadmat(folder/"network_cases.mat",simplify_cells=True)
        zones=dict(zip(np.asarray(full["bus_ids"],int),np.asarray(full["bus_zones"]).astype(str)))
        keep=np.asarray(slim["kept_bus_ids"],int)
        maximums={key:0. for key in ["slim_KCL_model_mw","full191_KCL_model_mw","interface_model_mw","F84_model_mw","inactive211_model_mw"]}
        for state in sorted(set(states[q])):
            ix=np.flatnonzero(q&(states==state));small=system(slim[state],generator_buses);large=system(full[state],generator_buses)
            theta=np.deg2rad(data["bus_va"][ix]);fsmall=branch_flows(small,theta)
            inj_small=pg[ix]@small["G"]-pd148[ix]-small["bus"][:,4]+dc[ix]@small["D"]
            es=compare(fsmall@small["C"],inj_small,name+" "+state+" 148KCL")
            rec=slim["recovery"][state.removesuffix("_case")]
            theta_full=theta@rec["angle_lift"].T+rec["angle_offset"]
            ri=np.array([large["lookup"][b] for b in keep]);interior=np.array([j for j in range(191) if j not in set(ri)])
            compare(theta_full[:,ri],theta,"Retained lifted angles",1e-12)
            fullpd=np.zeros((len(ix),191));fullpd[:,ri]=pd148[ix]
            require(np.all(large["bus"][interior,2:6]==0) and np.all(fullpd[:,interior]==0),"Eliminated interior injection violated")
            ffull=branch_flows(large,theta_full)
            inj_full=pg[ix]@large["G"]-fullpd-large["bus"][:,4]+dc[ix]@large["D"]
            ef=compare(ffull@large["C"],inj_full,name+" "+state+" 191KCL")
            require(maxabs(ffull[:,210])==0 and maxabs(fsmall[:,210])==0,"Original controlled AC row211 is not inactive")
            operator=legacy_operator(large,zones)
            ei=compare(ffull@operator.T,data["interface_pf"][ix],name+" seven inherited operators")
            require(np.array_equal(large["branch"][390,:2],[73,20001]),"F84 full-row identity changed")
            e84=compare(ffull[:,390],data["F84_line_pf_model_mw"][ix],name+" savedF84lineflow")
            records.append(dict(scenario=name,state=state,qualified_hours=len(ix),slim_KCL_model_mw=es,full191_KCL_model_mw=ef,
                                seven_inherited_operator_error_model_mw=ei,F84_flow_error_model_mw=e84,inactive211_flow_model_mw=0.,
                                generation_and_PD_from_frozen_inputs=True,six_boundary_transfers_from_frozen_inputs=True,physical_flowgate_certified=False))
            for key,value in [("slim_KCL_model_mw",es),("full191_KCL_model_mw",ef),("interface_model_mw",ei),("F84_model_mw",e84)]:maximums[key]=max(maximums[key],value)
            for fixture in fixtures:
                hour=int(fixture["hour_index"])-1
                if str(fixture["name"])==name and hour in ix:
                    loc=int(np.flatnonzero(ix==hour)[0])
                    epg=compare(fixture["gen_pg"],pg[hour],"Fixture frozenPG",0.)
                    epd=compare(fixture["bus_pd"],pd148[hour],"Fixture frozenPD",0.)
                    eqd=compare(fixture["bus_qd"],qd148[hour],"Fixture frozenQD",0.)
                    eb=compare(fixture["branch_pf"],fsmall[loc],"Fixture all274branchflows")
                    eif=compare(fixture["interface_pf"],ffull[loc]@operator.T,"Fixture inheritedinterfaces")
                    fixture_checks.append(dict(scenario=name,hour_index=hour+1,frozen_PG_error=epg,frozen_PD_error=epd,frozen_QD_error=eqd,
                                               branchflow_error_model_mw=eb,interface_error_model_mw=eif))
        if name=="identity_reference":
            compare(data["bus_va"][q],reference["bus_va"][q],"Identity original annual angles")
            compare(data["interface_pf"][q],reference["interface_pf"][q],"Identity original annual operators")
        summaries.append(dict(scenario=name,hours=int(q.sum()),maximum_errors=maximums,
                              F84_max_abs_lossless_active_flow_model_mw=float(np.max(np.abs(data["F84_line_pf_model_mw"][q]))),
                              F84_actual_current_or_apparent_power_validation=False))
        saved[name]=data
    require(len(fixture_checks)==len(fixtures),"Fixture coverage incomplete")
    c_only_angle=compare(saved["ground_image_30ft"]["bus_va"][q],saved["engineering_nominal"]["bus_va"][q],"DC charging-only sensitivity angle invariance")
    c_only_if=compare(saved["ground_image_30ft"]["interface_pf"][q],saved["engineering_nominal"]["interface_pf"][q],"DC charging-only sensitivity flow invariance")
    require({p:sha(ROOT/p) for p in deps}==deps,"Protected input/output changed during annual validation")
    dest=OUT/"validation";dest.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(records).to_csv(dest/"annual_replay_equation_checks.csv",index=False)
    pd.DataFrame(fixture_checks).to_csv(dest/"annual_replay_fixture_checks.csv",index=False)
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),scenarios=len(scenarios),hours_per_scenario=int(q.sum()),scenario_hours=int(q.sum())*len(scenarios),
                state_checks=len(records),stored_fixture_checks=len(fixtures),native_bound_violation_model_mw=bound_error,
                independent_from_production_predict_network_reducer=True,internal_interface_observations_read=False,parameters_selected_by_scores=False,
                frozen_input_KCL_and_all_six_transfer_checks_passed=True,original_full_row211_inactive=True,full191_branchlaw_and_F84_checked_all_hours=True,
                charging_only_sensitivity_angle_difference_degree=c_only_angle,charging_only_sensitivity_interface_difference_model_mw=c_only_if,
                actual_conductor_thermal_AC_or_physical_flowgate_certification=False,dependencies=deps,source_hashes_unchanged=True,scenarios_summary=summaries,
                outputs={name:sha(dest/name) for name in ["annual_replay_equation_checks.csv","annual_replay_fixture_checks.csv"]})
    (dest/"annual_replay_validation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(dict(passed=True,scenario_hours=report["scenario_hours"],state_checks=len(records),fixture_checks=len(fixtures),
                         maxima={key:max(s["maximum_errors"][key] for s in summaries) for key in summaries[0]["maximum_errors"]}),indent=2),flush=True)


def metrics():
    annual_path=OUT/"validation/annual_replay_validation.json";proof=read(annual_path)
    require(proof["passed"] and not proof["internal_interface_observations_read"],"Independent equations must pass before scoring")
    deps={str(annual_path.relative_to(ROOT)).replace("\\","/"):sha(annual_path)}
    for p,h in proof["dependencies"].items():require(sha(ROOT/p)==h,"Annual validation is stale");deps[p]=h
    scoring_path=OUT/"comparison/scoring_receipt.json";scoring=read(scoring_path)
    require(scoring["passed"] and scoring["internal_observations_posthoc_only"] and scoring["source_nominal_case_not_selected_by_scores"],"Scoring source boundary failed")
    deps.update(verify_manifest(scoring["dependencies"]));deps.update(verify_manifest(scoring["outputs"]))
    deps[str(scoring_path.relative_to(ROOT)).replace("\\","/")]=sha(scoring_path)
    replay=read(OUT/"replay/replay_receipt.json")
    with np.load(OUT/"replay/identity_reference.npz",allow_pickle=False) as z:
        times=z["timestamp_utc"].astype(str);q=z["qualified"];gamma=float(z["gamma"]);reference=z["interface_pf"]/gamma
    obs_path=ROOT/"output/nygrid_2025_inputs/load_source/interface_wide.csv"
    obs=pd.read_csv(obs_path,usecols=["timestamp_utc"]+NAMES,float_precision="round_trip")
    require(np.array_equal(obs.timestamp_utc.astype(str),times),"Independent scoring clock differs")
    y=obs[NAMES].to_numpy(float);require(np.isfinite(y[q]).all(),"Qualified observation missing")
    months=pd.DatetimeIndex(pd.to_datetime(times,utc=True)).tz_convert("America/New_York").month.to_numpy()
    published=pd.concat([pd.read_csv(OUT/"comparison/annual_metrics.csv",float_precision="round_trip"),pd.read_csv(OUT/"comparison/monthly_metrics.csv",float_precision="round_trip")],ignore_index=True)
    require(len(published)==455 and not published.duplicated(["scenario","interface","month"]).any(),"Published metric identity coverage differs")
    require(not published.internal_observations_used_for_fit.any() and not published.physical_flowgate_certified.any(),"Metric qualification flags changed")
    published=published.set_index(["scenario","interface","month"]);rows=[];maximum=0.
    for item in replay["scenarios"]:
        with np.load(ROOT/item["path"],allow_pickle=False) as z:pred=z["interface_pf"]/gamma
        for month in range(13):
            use=q if month==0 else q&(months==month)
            for j,name in enumerate(NAMES):
                residual=pred[use,j]-y[use,j];old=reference[use,j]-y[use,j];delta=pred[use,j]-reference[use,j]
                require(use.sum()>0 and abs(y[use,j]).sum()>0,"Undefined score denominator")
                values=dict(mae_public_mw=float(np.mean(np.abs(residual))),rmse_public_mw=float(np.sqrt(np.dot(residual,residual)/len(residual))),
                            bias_public_mw=float(np.sum(residual)/len(residual)),wape_percent=float(100*np.sum(np.abs(residual))/np.sum(np.abs(y[use,j]))),
                            mae_change_from_baseline_public_mw=float(np.mean(np.abs(residual))-np.mean(np.abs(old))),
                            prediction_change_mean_public_mw=float(np.sum(delta)/len(delta)),prediction_change_max_public_mw=float(np.max(np.abs(delta))))
                key=(item["scenario_name"],name,month);existing=published.loc[key]
                require(int(existing.hours)==int(use.sum()),"Published score cohort differs")
                error=max(abs(value-float(existing[field])) for field,value in values.items());maximum=max(maximum,error)
                require(error<1e-9,"Independent metric mismatch: "+str(key))
                rows.append(dict(scenario=item["scenario_name"],interface=name,month=month,hours=int(use.sum()),maximum_published_difference=error,**values))
    require({p:sha(ROOT/p) for p in deps}==deps,"Scoring input/output changed during independent validation")
    dest=OUT/"validation";pd.DataFrame(rows).to_csv(dest/"independent_comparison_metrics.csv",index=False)
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),annual_rows=sum(r["month"]==0 for r in rows),monthly_rows=sum(r["month"]!=0 for r in rows),
                fixed_hours=int(q.sum()),maximum_metric_difference=maximum,internal_observations_used_only_after_sealed_equation_validation=True,
                parameters_or_preferred_scenario_changed=False,physical_flowgate_certification=False,dependencies=deps,source_hashes_unchanged=True,
                outputs={"independent_comparison_metrics.csv":sha(dest/"independent_comparison_metrics.csv")})
    (dest/"comparison_validation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ["passed","annual_rows","monthly_rows","fixed_hours","maximum_metric_difference"]},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--metrics-only",action="store_true");parser.add_argument("--equations-only",action="store_true")
    args=parser.parse_args()
    if not args.metrics_only:annual()
    if not args.equations_only:metrics()
