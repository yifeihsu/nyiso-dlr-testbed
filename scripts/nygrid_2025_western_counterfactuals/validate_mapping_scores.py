"""Independent operator evaluation, zonal attribution and posthoc score audit.

Does not import a production solver, operator evaluator or scorer. Numeric
replay branch/KCL verification is delivered separately by the other reviewer.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"output/nygrid_2025_western_counterfactuals"
WEST=ROOT/"output/nygrid_2025_western_audit"
NAMES=["DYSINGER EAST","WEST CENTRAL","TOTAL EAST","MOSES SOUTH","CENTRAL EAST - VC","UPNY CONED","SPR/DUN-SOUTH"]
DEPS={};CHECKS=[]


def sha(p):
    with Path(p).open("rb")as f:return hashlib.file_digest(f,"sha256").hexdigest()


def use(p):
    p=Path(p);p=p if p.is_absolute()else ROOT/p;DEPS[p.relative_to(ROOT).as_posix()]=sha(p);return p


def check(name,ok,error=0.):
    CHECKS.append(dict(check=name,passed=bool(ok),maximum_absolute_error=float(error)))
    if not ok:raise AssertionError(name+": "+str(error))


def close(name,a,b,tol=1e-7,nan=False):
    a,b=np.asarray(a),np.asarray(b);ok=a.shape==b.shape
    if ok:ok=np.array_equal(np.isfinite(a),np.isfinite(b))if nan else np.isfinite(a).all()and np.isfinite(b).all()
    e=float(np.max(abs(a[np.isfinite(a)]-b[np.isfinite(b)]),initial=0))if ok else np.inf
    check(name,ok and e<=tol,e);return e


def proof(path):
    d=json.loads(use(path).read_text());records=d["dependencies"]
    check("nonempty_unique_proof_"+Path(path).name,bool(records)and len({r["path"]for r in records})==len(records))
    for r in records:check("dependency_"+r["path"],sha(use(r["path"]))==r["sha256"])
    return d


def arr(path):return np.load(use(path),allow_pickle=False)


def mat(path,fields):return loadmat(use(path),simplify_cells=True,variable_names=fields)


def full_flow(case,recovery,angle):
    # Independent explicit branch law with the original passive211 removed.
    theta=np.deg2rad(angle)@np.asarray(recovery["angle_lift"]).T+recovery["angle_offset"]
    b=np.asarray(case["branch"]);lookup={int(v):i for i,v in enumerate(case["bus"][:,0])}
    f=[lookup[int(v)]for v in b[:,0]];t=[lookup[int(v)]for v in b[:,1]]
    live=b[:,10]==1;live[210]=False;tap=np.where(b[:,8]==0,1.,b[:,8]);k=np.zeros(len(b))
    k[live]=float(case["baseMVA"])/(b[live,3]*tap[live])
    return (theta[:,f]-theta[:,t]-np.deg2rad(b[:,9]))*k


def main():
    start=datetime.now(timezone.utc).isoformat();dest=OUT/"validation";dest.mkdir(exist_ok=True)
    design=proof(OUT/"design/experiment_plan.json")
    replay=proof(OUT/"replay/replay_receipt.json")
    mapping=proof(OUT/"mapping/mapping_receipt.json")
    op_replay=proof(OUT/"mapping/operator_replay_receipt.json")
    scoreproof=proof(OUT/"comparison/scoring_receipt.json")
    check("predeclared_fixed8651_source_only",design["fixed_hours"]==8651 and replay["passed"]and not replay["internal_observations_read"]and not op_replay["internal_observations_read"]and mapping["no_internal_observation_files_read"])
    check("posthoc_scoring_scope",scoreproof["passed"]and scoreproof["internal_observations_posthoc_only"]and scoreproof["no_infeasible_literal_hypothesis_scored"])
    for r in scoreproof["outputs"]:check("scored_output_hash",sha(use(r["path"]))==r["sha256"])
    catalog=proof(OUT/"replay/candidate_catalog.json")
    check("catalog_preobservations",catalog["all_internal_observation_access_deferred"])
    check("exact16numeric3operator_cases",len(replay["cases"])==16 and len(op_replay["cases"])==3)
    cases=replay["cases"]+op_replay["cases"]
    names={c["name"]for c in cases};excluded={c["name"]for c in catalog["excluded_literal_hypotheses"]}
    check("excluded_literal_hypotheses_not_scored",len(names)==19 and len(excluded)==2 and not names&excluded)
    q=np.load(use(WEST/"replay/paired_common_mask.npy"),allow_pickle=False)
    check("exact_fixed8651_mask",q.dtype==bool and q.shape==(8760,)and q.sum()==8651)
    basecase=next(c for c in replay["cases"]if c["name"]=="baseline")
    for c in cases:check("case_hash_"+c["name"],sha(use(c["file"]))==c["sha256"])
    base=arr(basecase["file"]);gamma=float(base["gamma"]);times=base["timestamp_utc"].astype(str);states=base["network_state_ids"].astype(str)
    parent=mat(WEST/"replay/dated_combined.mat",["bus_va","interface_pf","common_scoring_mask","timestamp_utc","gamma"])
    check("parent_baseline_mask",np.array_equal(parent["common_scoring_mask"],q)and np.array_equal(np.asarray(parent["timestamp_utc"]).astype(str),times))
    close("baseline_reproduces_parent_angles",base["bus_va"][q],parent["bus_va"][q])
    close("baseline_reproduces_parent_interfaces",base["interface_pf"][q],parent["interface_pf"][q])
    operators=arr(OUT/"mapping/operators.npz")
    check("operator_hash",sha(OUT/"mapping/operators.npz")==mapping["operators_sha256"])
    check("operator_plan_hash",sha(use(OUT/"mapping/mapping_plan.json"))==mapping["mapping_plan_sha256"])
    check("operator_shapes",mapping["operator_shape"]==[7,410]and mapping["DC_operator_shape"]==[7,6])
    check("no_incomplete_physical_operator_promoted",mapping["complete_source_backed_physical_alternatives"]==0 and mapping["negative_control_is_known_wrong"])
    check("operator_fixed_axis",np.array_equal(operators["qualified"],q)and np.array_equal(operators["timestamp_utc"].astype(str),times)and float(operators["gamma"])==gamma)
    model=mat("output/nygrid_2025_slim/network/network_cases.mat",["recovery","kept_bus_ids"])
    full=mat("output/nygrid_2025_downstate/network/network_cases.mat",list(sorted(set(states)))+["bus_ids","bus_zones"])
    d=mat("output/nygrid_2025_dispatch/dispatch/dispatch.mat",["bus_pd","bus_qd","dc_pf","timestamp_utc"])
    par=arr("output/nygrid_2025_par_controls/controls/inputs.npz")
    dc6=np.column_stack([d["dc_pf"],par["observed_model_mw"]])
    flow=np.full((8760,410),np.nan)
    for state in sorted(set(states)):
        ix=np.flatnonzero(q&(states==state));rec=model["recovery"][state.removesuffix("_case")]
        flow[ix]=full_flow(full[state],rec,base["bus_va"][ix])
        close(state+"_current_operator_equals_sealed_baseline",rec["full_interface_branch_matrix"],operators["baseline_corrected_full191_operator"],0)
    op_checks=[]
    for c in op_replay["cases"]:
        value=arr(c["file"]);op=operators[c["operator_key"]];dop=operators[c["operator_dc_key"]]
        check(c["name"]+"_complete_finite_operator",op.shape==(7,410)and dop.shape==(7,6)and np.isfinite(op).all()and np.isfinite(dop).all())
        expected=flow[q]@op.T+dc6[q]@dop.T
        e=close(c["name"]+"_independent_full191_measurement",value["interface_pf"][q],expected)
        close(c["name"]+"_otherfive_preserved",value["interface_pf"][q,2:],base["interface_pf"][q,2:])
        if c["operator_key"]!="literal_released_plot_negative_control":close(c["name"]+"_equivalence_control",value["interface_pf"][q],base["interface_pf"][q])
        else:check("literal_knownbug_never_claimed_fix",c["interpretation"]=="known_bug_negative_control")
        op_checks.append(dict(scenario=c["name"],hours=int(q.sum()),maximum_reconstruction_error_model_mw=e))
    # Reconstruct each compact generation/load hypothesis and check zonal
    # conservation attribution; this is model accounting, not physical cause.
    PG=mat(WEST/"dispatch/all_boundary_actual_dispatch.mat",["gen_pg"])["gen_pg"]
    register=pd.read_csv(use(WEST/"corrected/model_generator_register.csv"))
    zones=dict(zip(np.asarray(full["bus_ids"],int),np.asarray(full["bus_zones"]).astype(str)))
    genzones=np.array([zones[int(b)]for b in register.bus_id]);buszones=np.array([zones[int(b)]for b in model["kept_bus_ids"]])
    basePD=np.pad(d["bus_pd"],((0,0),(0,8)));baseQD=np.pad(d["bus_qd"],((0,0),(0,8)))
    bounds=mat("output/nygrid_2025_dispatch/dispatch/dispatch_bounds.mat",["gen_pmin","gen_pmax"])
    weights=mat("output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat",["objective_weights"])["objective_weights"]
    attribution=[];arrays={}
    extop=operators["external_cut_branch"][0];borderrows=np.flatnonzero(extop)
    base_border=flow[:,borderrows]@extop[borderrows]
    for c in replay["cases"]:
        value=arr(c["file"]);arrays[c["name"]]=value["interface_pf"]
        delta=np.zeros((8760,1464));PD=basePD;QD=baseQD
        if c["generation"]is not None:
            g=arr(c["generation"]["file"]);rows=g["gen_rows_1based"].astype(int)-1
            check(c["name"]+"_generation_axis",len(rows)==len(set(rows))and np.isin(rows,np.arange(1436)).all()and np.array_equal(g["qualified"],q))
            delta[:,rows]=g["gen_pg_changed"]-PG[:,rows]
            close(c["name"]+"_same_hourly_totalPG",delta[q].sum(axis=1),np.zeros(q.sum()))
            changed=PG[q][:,rows]+delta[q][:,rows]
            violation=np.max(np.maximum(np.maximum(bounds["gen_pmin"][q][:,rows]-changed,changed-bounds["gen_pmax"][q][:,rows]),0))
            check(c["name"]+"_original_unit_bounds",violation<=1e-7,violation)
            protected=register.plant_id.isin([2692,2694]).to_numpy()|register.role.eq("fixed_external").to_numpy()|register.fuel_category.ne("Hydro").to_numpy()
            check(c["name"]+"_protected_gen_rows_not_changed",not set(rows)&set(np.flatnonzero(protected)))
            for group,dualname in [("RMN_generator_rows_1based","RMN_projection_dual"),("donor_generator_rows_1based","donor_projection_dual")]:
                group_rows=g[group].astype(int)-1;loc=np.searchsorted(rows,group_rows)
                close(c["name"]+group+"_local_projection_KKT",g["gen_pg_changed"][q][:,loc],np.clip(PG[q][:,group_rows]+g[dualname][q,None]/weights[q][:,group_rows],bounds["gen_pmin"][q][:,group_rows],bounds["gen_pmax"][q][:,group_rows]))
        if c["demand"]is not None:
            load=arr(c["demand"]["file"]);PD=load["bus_pd"];QD=load["bus_qd"]
            check(c["name"]+"_load_axis",np.array_equal(load["qualified"],q)and np.array_equal(load["bus_ids"],model["kept_bus_ids"]))
            for zone in set(buszones):
                mask=buszones==zone;close(c["name"]+zone+"_PDtotal",PD[q][:,mask].sum(axis=1),basePD[q][:,mask].sum(axis=1))
                close(c["name"]+zone+"_QDtotal",QD[q][:,mask].sum(axis=1),baseQD[q][:,mask].sum(axis=1))
            other=~np.isin(buszones,["A","B"])
            close(c["name"]+"_otherbusPD",PD[q][:,other],basePD[q][:,other],0);close(c["name"]+"_otherbusQD",QD[q][:,other],baseQD[q][:,other],0)
        expected=[]
        for region in [["A"],["A","B"]]:
            expected.append(delta[q][:,np.isin(genzones,region)].sum(axis=1)-(PD[q]-basePD[q])[:,np.isin(buszones,region)].sum(axis=1))
        predicted=value["interface_pf"][q,:2]-base["interface_pf"][q,:2]
        error=close(c["name"]+"_western_delta_equals_net_injection",predicted,np.column_stack(expected))
        # The three active external A-boundary branches use retained buses.
        own_border=np.full(8760,np.nan)
        for state in sorted(set(states)):
            ix=np.flatnonzero(q&(states==state));b=full[state]["branch"][borderrows];lookup={int(v):i for i,v in enumerate(model["kept_bus_ids"])}
            f=[lookup[int(v)]for v in b[:,0]];t=[lookup[int(v)]for v in b[:,1]];tap=np.where(b[:,8]==0,1.,b[:,8])
            coeff=float(full[state]["baseMVA"])*b[:,10]/(b[:,3]*tap)
            borderflow=(np.deg2rad(value["bus_va"][ix][:,f]-value["bus_va"][ix][:,t])-np.deg2rad(b[:,9]))*coeff
            own_border[ix]=borderflow@extop[borderrows]
        border_error=close(c["name"]+"_western_external_border_fixed",own_border[q],base_border[q])
        attribution.append(dict(scenario=c["name"],hours=int(q.sum()),maximum_western_delta_identity_error_model_mw=error,maximum_external_border_change_model_mw=border_error,
            mean_A_net_injection_delta_public_mw=float(np.mean(expected[0])/gamma),mean_AB_net_injection_delta_public_mw=float(np.mean(expected[1])/gamma),interpretation="exact_frozen_model_accounting_not_unique_physical_cause"))
    close("load_A_noop_all7",arrays["load_original_A"][q],arrays["baseline"][q])
    close("load_AB_equals_B_all7",arrays["load_original_AB"][q],arrays["load_original_B"][q])
    for c in replay["cases"]:
        if c["family"]=="interaction":
            pure=c["generation"]["name"]
            close(c["name"]+"_linear_superposition_all7",arrays[c["name"]][q]-arrays[pure][q],arrays["load_original_B"][q]-arrays["baseline"][q])
    # All source-only definitions are sealed. Observations enter only here.
    obs=pd.read_csv(use("output/nygrid_2025_inputs/load_source/interface_wide.csv"),usecols=["timestamp_utc"]+NAMES)
    check("observation_axis",np.array_equal(obs.timestamp_utc,times));Y=obs[NAMES].to_numpy(float)
    months=pd.to_datetime(times,utc=True).tz_convert("America/New_York").month.to_numpy();baseline=base["interface_pf"]/gamma;rows=[]
    for c in cases:
        a=arr(c["file"])
        check(c["name"]+"_fixed_comparison_axis",np.array_equal(a["qualified"],q)and np.array_equal(a["timestamp_utc"].astype(str),times)and np.array_equal(a["hour_index"],np.arange(1,8761))and float(a["gamma"])==gamma)
        pred=a["interface_pf"]/gamma;check(c["name"]+"_unqualified_unfilled",np.isnan(pred[~q]).all())
        for month in range(13):
            mask=q if month==0 else q&(months==month)
            check(c["name"]+str(month)+"_finite_score",mask.any()and np.isfinite(Y[mask]).all()and np.isfinite(pred[mask]).all())
            for j,interface in enumerate(NAMES):
                e=pred[mask,j]-Y[mask,j];old=baseline[mask,j]-Y[mask,j];delta=pred[mask,j]-baseline[mask,j];den=abs(Y[mask,j]).sum();check("nonzero_WAPE_denominator",den>0)
                rows.append(dict(scenario=c["name"],family=c["family"],interface=interface,month=month,hours=int(mask.sum()),mae_public_mw=float(abs(e).mean()),rmse_public_mw=float(np.sqrt(np.mean(e**2))),bias_public_mw=float(e.mean()),wape_percent=float(100*abs(e).sum()/den),mae_change_from_baseline_public_mw=float(abs(e).mean()-abs(old).mean()),prediction_change_mean_public_mw=float(delta.mean()),prediction_change_mae_public_mw=float(abs(delta).mean()),prediction_change_max_public_mw=float(abs(delta).max())))
    expected=pd.DataFrame(rows).set_index(["scenario","family","interface","month"]).sort_index()
    annual=pd.read_csv(use(OUT/"comparison/annual_metrics.csv"));monthly=pd.read_csv(use(OUT/"comparison/monthly_metrics.csv"))
    check("133annual1596monthly",len(annual)==133 and len(monthly)==1596)
    actual=pd.concat([annual,monthly]).set_index(["scenario","family","interface","month"]).sort_index()
    check("score_keys_unique_and_complete",actual.index.is_unique and actual.index.equals(expected.index))
    for column in expected:close("independent_metric_"+column,actual[column],expected[column],1e-8)
    check("all_reported_fit_flags_false",not actual.internal_observations_used_for_fit.astype(str).str.lower().eq("true").any())
    expected.reset_index().to_csv(dest/"independent_mapping_all_scores.csv",index=False,lineterminator="\n")
    pd.DataFrame(op_checks).to_csv(dest/"independent_operator_checks.csv",index=False,lineterminator="\n")
    pd.DataFrame(attribution).to_csv(dest/"independent_western_delta_attribution.csv",index=False,lineterminator="\n")
    use(Path(__file__));check("all_inputs_unchanged",all(sha(ROOT/p)==h for p,h in DEPS.items()))
    result=dict(passed=True,started_utc=start,completed_utc=datetime.now(timezone.utc).isoformat(),fixed_hours=8651,numeric_scenarios=16,operator_scenarios=3,annual_metric_rows=133,monthly_metric_rows=1596,
        internal_observations_used_only_for_final_metric_recalculation=True,production_solver_or_scorer_imported=False,all_observation_denominators_and_scale_factors_verified=True,
        maximum_operator_error_model_mw=max(r["maximum_reconstruction_error_model_mw"]for r in op_checks),maximum_western_attribution_error_model_mw=max(r["maximum_western_delta_identity_error_model_mw"]for r in attribution),
        failed_checks=0,checks=CHECKS,all_input_hashes_unchanged=True,dependencies=[dict(path=p,sha256=h)for p,h in DEPS.items()],
        limits=["Known-bug operator is a diagnostic negative control, not a candidate correction.","Incomplete physical meter crosswalk is an identifiability gap; no source-certified new physical operator was created.","Niagara-to-western-flow delta attribution is exact model conservation under fixed boundaries; it is not a share of true physical forecast error."])
    (dest/"mapping_score_validation.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k]for k in ["passed","fixed_hours","numeric_scenarios","operator_scenarios","annual_metric_rows","monthly_metric_rows","maximum_operator_error_model_mw","maximum_western_attribution_error_model_mw","failed_checks"]},indent=2))


if __name__=="__main__":main()
