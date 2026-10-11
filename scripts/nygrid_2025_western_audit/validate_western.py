"""Independent annual equations, dispatch KKT, source identity and scoring.

No production solver/controller/scorer is imported. Evaluates each saved
qualified hour from branch laws, nodal conservation and fixed source arrays.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"output/nygrid_2025_western_audit"
BASE=ROOT/"output/nygrid_2025_dispatch/dispatch"
PAR=ROOT/"output/nygrid_2025_par_controls"
DEPS={};CHECKS=[]
TOL=1e-7
REGIONS=["ISONE","ONTARIO","PJM","HQ"]
NAMES=["DYSINGER EAST","WEST CENTRAL","TOTAL EAST","MOSES SOUTH","CENTRAL EAST - VC","UPNY CONED","SPR/DUN-SOUTH"]
MODES={"previous_PAR_baseline":("scheduled",False),"mapping_only":("scheduled",True),
 "Ontario_actual_only":("Ontario",False),"Ontario_actual_and_mapping":("Ontario",True),
 "all_boundary_actual_only":("all",False),"combined":("all",True)}


def sha(path):
    with Path(path).open("rb")as f:return hashlib.file_digest(f,"sha256").hexdigest()


def use(path):
    path=Path(path);path=path if path.is_absolute()else ROOT/path
    DEPS[path.relative_to(ROOT).as_posix()]=sha(path);return path


def mat(path,variables=None):return loadmat(use(path),simplify_cells=True,variable_names=variables)


def check(name,condition,error=0.):
    CHECKS.append(dict(check=name,passed=bool(condition),maximum_absolute_error=float(error)))
    if not condition:raise AssertionError(name+": "+str(error))


def close(name,a,b,tolerance=TOL,allow_nan=False):
    a,b=np.asarray(a),np.asarray(b)
    ok=a.shape==b.shape
    if ok:
        ok=np.array_equal(np.isfinite(a),np.isfinite(b))if allow_nan else np.isfinite(a).all()and np.isfinite(b).all()
    err=float(np.max(abs(a[np.isfinite(a)]-b[np.isfinite(b)]),initial=0))if ok else np.inf
    check(name,ok and err<=tolerance,err);return err


def boolean(s):
    a=pd.Series(s).astype(str).str.lower()
    check("boolean_contract",a.isin(["true","false","1","0"]).all())
    return a.isin(["true","1"]).to_numpy()


def proof(path,required=()):
    receipt=json.loads(use(path).read_text())
    records=receipt["dependencies"]
    keys=[r["path"]for r in records]
    check("proof_nonempty_unique_"+Path(path).name,len(keys)>0 and len(keys)==len(set(keys))and set(required).issubset(keys))
    for r in records:check("dependency_"+r["path"],sha(use(r["path"]))==r["sha256"])
    return receipt


def equations(case,buses):
    bus=np.asarray(case["bus"]);branch=np.asarray(case["branch"]).copy()
    check("original_controlled_branch211_identity",np.array_equal(branch[210,:2],[48,100])and branch[210,10]==1)
    branch[210,10]=0
    index={int(v):i for i,v in enumerate(bus[:,0])}
    check("unique_bus_ids",len(index)==len(bus))
    f=np.array([index[int(v)]for v in branch[:,0]]);t=np.array([index[int(v)]for v in branch[:,1]])
    C=np.zeros((len(branch),len(bus)));C[np.arange(len(branch)),f]=1;C[np.arange(len(branch)),t]-=1
    active=branch[:,10]==1
    adjacency=csr_matrix((np.ones(2*active.sum()),(np.r_[f[active],t[active]],np.r_[t[active],f[active]])),shape=(len(bus),len(bus)))
    check("AC_connected_without_passive211",connected_components(adjacency,directed=False)[0]==1)
    tap=np.where(branch[:,8]==0,1.,branch[:,8]);check("branch_tap_and_x_valid",(tap>0).all()and(branch[active,3]!=0).all())
    k=np.zeros(len(branch));k[active]=float(case["baseMVA"])/(branch[active,3]*tap[active])
    phase=-k*np.deg2rad(branch[:,9])
    G=csr_matrix((np.asarray(case["gen"])[:,7],(np.arange(len(buses)),[index[int(b)]for b in buses])),shape=(len(buses),len(bus)))
    dc=np.asarray(case["dcline"])
    check("exact_four_original_lossless_DC",dc.shape==(4,17)and np.all(dc[:,15:17]==0))
    D=np.zeros((6,len(bus)))
    for j,r in enumerate(dc):D[j,index[int(r[0])]]-=r[2];D[j,index[int(r[1])]]+=r[2]
    D[4:,index[100]]=-1;D[4:,index[48]]=1
    return dict(C=C,k=k,phase=phase,G=G,D=D,bus=bus,lookup=index)


def validate_dispatch(data,bounds,priors,par,original_register):
    gamma=float(data["gamma"]);times=np.asarray(data["timestamp_utc"]).astype(str)
    check("dispatch_gamma_PAR",gamma>0 and gamma==float(par["gamma"]))
    check("PAR_time_axis",np.array_equal(times,par["timestamp_utc"].astype(str)))
    close("PAR_scale_once",par["observed_model_mw"],par["observed_public_mw"]*gamma,1e-12,True)
    native=np.flatnonzero(original_register.role.eq("native"));external=np.flatnonzero(original_register.role.eq("fixed_external"))
    check("fixed_original_generator_inventory",len(native)==1436 and len(external)==28 and np.array_equal(original_register.gen_row,np.arange(1,1465)))
    allocation=pd.read_csv(use("output/nygrid_2025_inputs/model/external_generator_allocation.csv"))
    shares=np.zeros((1464,4));regional_columns={}
    for j,region in enumerate(REGIONS):
        a=allocation.loc[allocation.region==region]
        cols=[]
        for row in a.itertuples(index=False):
            match=original_register.loc[(original_register.parent_gen_row==row.generator_row)&original_register.role.eq("fixed_external")]
            check("allocation_identity_"+str(row.generator_row),len(match)==1 and int(match.iloc[0].bus_id)==row.bus_id)
            i=int(match.iloc[0].gen_row)-1;shares[i,j]=row.generation_share;cols.append(i)
        close("regional_share_sum_"+region,[shares[:,j].sum()],[1.],1e-12)
        regional_columns[region]=np.array(cols,int)
    p0=priors["prior_pg"][:,native];lo=bounds["gen_pmin"][:,native];hi=bounds["gen_pmax"][:,native];w=priors["objective_weights"]
    oldq=np.asarray(data["dispatch_qualified"],bool)&np.asarray(par["observed_replay_qualified"],bool)
    ont_csv=pd.read_csv(use(OUT/"ontario/hourly_actual_exchange.csv"));ont_quality=pd.read_csv(use(OUT/"ontario/hourly_exchange_quality.csv"))
    all_csv=pd.read_csv(use(OUT/"boundary_actuals/hourly_regional_actuals.csv"))
    for frame in [ont_csv,ont_quality,all_csv]:check("dispatch_source_time_axis",np.array_equal(frame.timestamp_utc,times))
    ontq=oldq&boolean(ont_quality.source_quality_qualified);allq=oldq&boolean(all_csv.coverage_qualified)
    check("expected_masks_counts",int(oldq.sum())==8663 and int(ontq.sum())==8657 and int(allq.sum())==8657 and int((ontq&allq).sum())==8651)
    p32cols=["SCH - NE - NY","SCH - NPX_1385","SCH - NPX_CSC","SCH - OH - NY","SCH - PJ - NY","SCH - PJM_HTP","SCH - PJM_NEPTUNE","SCH - PJM_VFT","SCH - HQ - NY","SCH - HQ_CEDARS"]
    p32=pd.read_csv(use("output/nygrid_2025_inputs/load_source/interface_wide.csv"),usecols=["timestamp_utc"]+p32cols)
    sch=np.column_stack([p32[p32cols[:3]].sum(axis=1,min_count=3),p32["SCH - OH - NY"],p32[p32cols[4:8]].sum(axis=1,min_count=4),p32[p32cols[8:]].sum(axis=1,min_count=2)])
    allactual=all_csv[[r+"_actual_import_mw"for r in REGIONS]].to_numpy(float)
    all_delta=allactual-sch
    ont_delta=np.zeros((8760,4));ont_delta[:,1]=ont_csv.actual_ontario_to_ny_mw-p32["SCH - OH - NY"]
    results={"scheduled":data};qby={"scheduled":oldq,"Ontario":ontq,"all":allq};rows=[]
    for key,file,receipt,delta in [("Ontario","actual_Ontario_dispatch.mat","dispatch_receipt.json",ont_delta),("all","all_boundary_actual_dispatch.mat","all_boundary_dispatch_receipt.json",all_delta)]:
        record=proof(OUT/"dispatch"/receipt)
        check(key+"_source_only_receipt",record["passed"]and not record["internal_interface_observations_used"])
        path=OUT/"dispatch"/file;check(key+"_dispatch_output_hash",sha(use(path))==record["dispatch_file_sha256"])
        d=mat(path);results[key]=d;q=qby[key];ix=np.flatnonzero(q)
        check(key+"_qualified_mask",np.array_equal(np.asarray(d["qualified"],bool),q))
        check(key+"_timestamp_axis",np.array_equal(np.asarray(d["timestamp_utc"]).astype(str),times))
        close(key+"_gamma",[float(d["gamma"])],[gamma],0)
        pg=d["gen_pg"]
        check(key+"_all_invalid_PG_NaN",np.isnan(pg[~q]).all())
        expected_ext=data["gen_pg"][np.ix_(ix,external)]+gamma*delta[q]@shares[external].T
        external_error=close(key+"_all28_fixed_external_update",pg[np.ix_(ix,external)],expected_ext)
        target=data["native_required_pg"][q]-gamma*delta[q].sum(axis=1)
        close(key+"_native_balance_target",d["native_required_pg"][q],target)
        close(key+"_native_sum",pg[np.ix_(ix,native)].sum(axis=1),target)
        balance_error=close(key+"_global_balance",pg[q].sum(axis=1),data["bus_pd"][q].sum(axis=1)+data["base_case"]["bus"][:,4].sum())
        projected=np.clip(p0[q]+d["dual_lambda"][q,None]/w[q],lo[q],hi[q])
        kkt_error=close(key+"_KKT_against_original_P0_and_weights",pg[np.ix_(ix,native)],projected,1e-8)
        violation=float(np.max(np.maximum(np.maximum(lo[q]-pg[np.ix_(ix,native)],pg[np.ix_(ix,native)]-hi[q]),0)))
        check(key+"_original_native_bounds",violation<=1e-8,violation)
        objective=.5*np.sum(w[q]*(pg[np.ix_(ix,native)]-p0[q])**2,axis=1)
        close(key+"_original_objective",d["objective_value"][q],objective,1e-6)
        check(key+"_no_hidden_capacity_relaxation",not np.any(d["status_code"]==2))
        if key=="all":
            close("all_original4DC_unchanged",d["original_four_dc_pf"],data["dc_pf"],0,True)
            close("all_P34_targets_unchanged",d["P34_control_targets_model_mw"],par["observed_model_mw"],0,True)
            close("all_saved_original_region_schedules",d["original_regional_schedule_public_mw"],sch,1e-10,True)
            close("all_saved_actual_regions",d["actual_regional_import_public_mw"],allactual,0,True)
            close("all_saved_external_shares",d["external_region_share_matrix"],shares[external],0)
        rows.append(dict(basis=key,hours=int(q.sum()),external_update_error_model_mw=external_error,global_balance_error_model_mw=balance_error,KKT_error_model_mw=kkt_error,native_bound_violation_model_mw=violation))
    return results,qby,rows


def validate():
    folder=OUT/"validation";folder.mkdir(exist_ok=True)
    start=datetime.now(timezone.utc).isoformat()
    provenance=proof(OUT/"replay/provenance.json")
    check("replay_source_only_scope",provenance["passed"]and not provenance["internal_interface_observations_read"]and not provenance["topology_changed"]and not provenance["physical_new_Dysinger_PAR_network_added"])
    source_review=proof(OUT/"boundary_source_review/independent_boundary_review.json")
    check("all_boundary_source_review_passed",source_review["passed"]and source_review["failed_checks"]==0)
    data=mat(BASE/"dispatch.mat");bounds=mat(BASE/"dispatch_bounds.mat");priors=mat(BASE/"dispatch_priors.mat")
    original=pd.read_csv(use("output/nygrid_2025_moses_audit/corrected/model_generator_register.csv"))
    corrected=pd.read_csv(use(OUT/"corrected/model_generator_register.csv"))
    check("generator_identity_order_preserved",original[["gen_row","fleet_id","device_key","role"]].equals(corrected[["gen_row","fleet_id","device_key","role"]]))
    mapping_proof=json.loads(use(OUT/"review/pre_promotion_review.json").read_text())
    check("mapping_independent_review_passed",mapping_proof["fleet_review"]["status"]=="passed_independent_mapping_only_scope_review")
    for r in mapping_proof["source_review"]["dependencies"]:check("mapping_review_input_"+r["path"],sha(use(r["path"]))==r["sha256"])
    par=np.load(use(PAR/"controls/inputs.npz"),allow_pickle=False)
    par_receipt=json.loads(use(PAR/"controls/input_receipt.json").read_text())
    for r in par_receipt["dependencies"]+par_receipt["outputs"]:check("P34_proof_"+r["path"],sha(use(r["path"]))==r["sha256"])
    dispatches,qby,dispatch_rows=validate_dispatch(data,bounds,priors,par,original)
    common=qby["scheduled"]&qby["Ontario"]&qby["all"]
    saved_common=np.load(use(OUT/"replay/paired_common_mask.npy"),allow_pickle=False)
    check("actual_paired_mask_intersection8651",np.array_equal(common,saved_common)and int(common.sum())==8651)
    model=mat("output/nygrid_2025_slim/network/network_cases.mat")
    full=mat("output/nygrid_2025_downstate/network/network_cases.mat")
    check("model_bus_inventories",len(model["kept_bus_ids"])==148 and len(full["bus_ids"])==191 and np.array_equal(model["kept_bus_ids"][:140],np.arange(1,141)))
    gamma=float(data["gamma"]);times=np.asarray(data["timestamp_utc"]).astype(str)
    close("frozen_network_scale",[model["gamma"],full["gamma"]],[gamma,gamma],0)
    pd148=np.pad(data["bus_pd"],((0,0),(0,8)));pd191=np.pad(data["bus_pd"],((0,0),(0,51)))
    dc6=np.column_stack([data["dc_pf"],par["observed_model_mw"]])
    records=provenance["variants"]
    check("ten_new_replays",len(records)==10 and len({r["variant"]for r in records})==10)
    for topology in ["dated","year_end"]:
        records.append(dict(variant=topology+"_previous_PAR_baseline",topology=topology,mode="previous_PAR_baseline",file=(PAR/"replay"/(topology+"_verified_PAR_flows.mat")).relative_to(ROOT).as_posix()))
    eq_cache={};equation_rows=[];score_rows=[];interface_arrays={}
    obs=pd.read_csv(use("output/nygrid_2025_inputs/load_source/interface_wide.csv"),usecols=["timestamp_utc"]+NAMES)
    check("observation_hour_axis",np.array_equal(obs.timestamp_utc,times));y=obs[NAMES].to_numpy(float)
    months=pd.to_datetime(times,utc=True).tz_convert("America/New_York").month.to_numpy()
    baseline_states={t:mat(PAR/"replay"/(t+"_verified_PAR_flows.mat"),["network_state_ids"])["network_state_ids"]for t in ["dated","year_end"]}
    for r in records:
        name,topology,mode=r["variant"],r["topology"],r["mode"]
        path=use(r["file"])
        if "sha256"in r:check(name+"_saved_hash",sha(path)==r["sha256"])
        d=mat(path);basis,remap=MODES[mode];q=qby[basis];pg=dispatches[basis]["gen_pg"]
        buses=(corrected if remap else original).bus_id.to_numpy(int)
        check(name+"_mask",np.array_equal(np.asarray(d["qualified"],bool),q))
        check(name+"_time",np.array_equal(np.asarray(d["timestamp_utc"]).astype(str),times))
        close(name+"_scale",[d["gamma"]],[gamma],0)
        check(name+"_generator_terminals",np.array_equal(d["corrected_generator_buses"],buses))
        check(name+"_frozen_topology_chronology",np.array_equal(d["network_state_ids"],baseline_states[topology]))
        if mode!="previous_PAR_baseline":
            check(name+"_paired_mask",np.array_equal(d["common_scoring_mask"],common))
            check(name+"_declared_basis",str(d["boundary_basis"])==basis and bool(d["additional_mapping_repair_used"])==remap)
        close(name+"_unaltered_P34_targets",d["par_transfer_model_mw"][q],par["observed_model_mw"][q],0)
        close(name+"_logical_branch211",d["logical_original_branch211_pf"][q],-par["observed_model_mw"][q].sum(axis=1),0)
        for field in ["branch_pf","bus_va","interface_pf","par_transfer_model_mw","logical_original_branch211_pf"]:check(name+"_missing_unfilled_"+field,np.isnan(d[field][~q]).all())
        check(name+"_no_slack_balancing",np.nanmax(abs(d["slack_change_mw"]))<=TOL)
        states=np.asarray(d["network_state_ids"]).astype(str)
        for state in sorted(set(states)):
            ix=np.flatnonzero(q&(states==state))
            if not len(ix):continue
            key=(state,remap)
            if key not in eq_cache:eq_cache[key]=(equations(model[state],buses),equations(full[state],buses))
            eq,feq=eq_cache[key];theta=np.deg2rad(d["bus_va"][ix]);flow=theta@(eq["k"][:,None]*eq["C"]).T+eq["phase"]
            law=close(name+state+"_all_branch_laws",flow,d["branch_pf"][ix])
            injection=pg[ix]@eq["G"]-pd148[ix]-eq["bus"][:,4]+dc6[ix]@eq["D"]
            kcl=close(name+state+"_all148_bus_KCL",flow@eq["C"],injection)
            close(name+state+"_passive211_zero",flow[:,210],np.zeros(len(ix)),0)
            rec=model["recovery"][state.removesuffix("_case")]
            lifted=theta@np.asarray(rec["angle_lift"]).T+rec["angle_offset"]
            fullflow=lifted@(feq["k"][:,None]*feq["C"]).T+feq["phase"]
            fullinj=pg[ix]@feq["G"]-pd191[ix]-feq["bus"][:,4]+dc6[ix]@feq["D"]
            fkcl=close(name+state+"_full191_KCL",fullflow@feq["C"],fullinj)
            kept=np.asarray(rec["retained_full_indices_1based"],int)-1;elim=np.asarray(rec["eliminated_full_indices_1based"],int)-1
            close(name+state+"_retained_angles",lifted[:,kept],theta,1e-10)
            close(name+state+"_43_eliminated_nodes_zero_injection",fullinj[:,elim],np.zeros((len(ix),len(elim))),0)
            op=np.asarray(rec["full_interface_branch_matrix"]);check(name+state+"_no_control_in_scored_interfaces",np.all(op[:,210]==0))
            mapped=fullflow@op.T
            iferr=close(name+state+"_all7_full191_operators",mapped,d["interface_pf"][ix])
            close(name+state+"_angle_functional_recovery",mapped,theta@rec["interface_angle_matrix"].T+rec["interface_flow_offset"])
            equation_rows.append(dict(variant=name,state=state,hours=len(ix),branch_law_max_model_mw=law,KCL148_max_model_mw=kcl,KCL191_max_model_mw=fkcl,interface_recovery_max_model_mw=iferr))
        interface_arrays[name]=np.asarray(d["interface_pf"])
        prediction=d["interface_pf"]/gamma
        for cohort,mask in [("own_qualified",q),("paired_common",common)]:
            for month in range(13):
                usemask=mask if month==0 else mask&(months==month)
                check(name+cohort+str(month)+"_score_finite",np.isfinite(prediction[usemask]).all()and np.isfinite(y[usemask]).all()and usemask.any())
                for j,interface in enumerate(NAMES):
                    error=prediction[usemask,j]-y[usemask,j];denom=abs(y[usemask,j]).sum();check("positive_WAPE_denominator",denom>0)
                    score_rows.append(dict(variant=name,cohort=cohort,month=month,interface=interface,hours=int(usemask.sum()),mae_public_equivalent_mw=float(abs(error).mean()),rmse_public_equivalent_mw=float(np.sqrt(np.mean(error**2))),bias_public_equivalent_mw=float(error.mean()),wape_percent=float(100*abs(error).sum()/denom)))
        print("Validated "+name+" "+str(int(q.sum()))+" hours",flush=True)
    expected=pd.DataFrame(score_rows).set_index(["variant","cohort","month","interface"]).sort_index()
    annual=pd.read_csv(use(OUT/"comparison/interface_summary.csv"));monthly=pd.read_csv(use(OUT/"comparison/interface_monthly.csv"))
    check("168_annual_2016_monthly_scores",len(annual)==168 and len(monthly)==2016)
    published=pd.concat([annual,monthly],ignore_index=True).set_index(["variant","cohort","month","interface"]).sort_index()
    check("unique_complete_metric_keys",published.index.is_unique and published.index.equals(expected.index))
    for column in expected.columns:close("independent_all_scores_"+column,published[column].to_numpy(),expected[column].to_numpy(),1e-8)
    check("posthoc_metrics_no_fit",not boolean(published.internal_interface_observations_used_to_fit).any())
    scoring=json.loads(use(OUT/"comparison/scoring_receipt.json").read_text())
    check("scoring_receipt_binding",scoring["passed"]and scoring["internal_observations_only_posthoc"]and scoring["common_hours"]==int(common.sum())and scoring["original_observation_sha256"]==sha(ROOT/"output/nygrid_2025_inputs/load_source/interface_wide.csv")and scoring["replay_receipt_sha256"]==sha(OUT/"replay/provenance.json")and scoring["code_sha256"]==sha(use(ROOT/"scripts/nygrid_2025_western_audit/replay_western.py")))
    expected.reset_index().to_csv(folder/"independent_all_scores.csv",index=False,lineterminator="\n")
    pd.DataFrame(equation_rows).to_csv(folder/"all_hour_equation_checks.csv",index=False,lineterminator="\n")
    pd.DataFrame(dispatch_rows).to_csv(folder/"independent_dispatch_checks.csv",index=False,lineterminator="\n")
    use(Path(__file__))
    check("all_dependency_hashes_unchanged",all(sha(ROOT/p)==h for p,h in DEPS.items()))
    summary=dict(passed=True,started_utc=start,completed_utc=datetime.now(timezone.utc).isoformat(),paired_hours=int(common.sum()),own_qualified_hours={k:int(v.sum())for k,v in qby.items()},
        replays_checked=12,new_replays_checked=10,original_baselines_checked=2,annual_scores_checked=len(annual),monthly_scores_checked=len(monthly),equation_state_checks=len(equation_rows),
        maximum_branch_law_error_model_mw=max(r["branch_law_max_model_mw"]for r in equation_rows),maximum_KCL148_error_model_mw=max(r["KCL148_max_model_mw"]for r in equation_rows),maximum_KCL191_error_model_mw=max(r["KCL191_max_model_mw"]for r in equation_rows),maximum_interface_recovery_error_model_mw=max(r["interface_recovery_max_model_mw"]for r in equation_rows),
        production_solver_controller_scorer_imported=False,validation_scope="allqualifiedhours_losslessDClaws_KCL_full191recovery_nativeoriginalP0_KKT_bounds_sourceidentity_generatorremaps_allannualmonthlymetrics",
        metric_semantics="publicMW=prediction/gamma once; UTC→America/New_York months; WAPE=sumabs(error)/sumabs(observed); ownmasksandactualintersectioncheckedbyarrayequality",
        checks=CHECKS,failed_checks=0,all_input_hashes_unchanged=True,dependencies=[dict(path=p,sha256=h)for p,h in DEPS.items()],
        limitations=["Inheritedinternalinterfaceoperatorsremainuncertifiedphysical2025meterdefinitions.","No AC/reactive/thermal/commitment/ramp/reservoir feasibilityclaim.","All-boundaryactualtotalsandtwoP34controlsdo not establishallindividualcircuit/DCflows."])
    (folder/"independent_validation.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items()if k not in ["checks","dependencies"]},indent=2))


if __name__=="__main__":validate()
