"""Independent complete-cohort Dover replay and bounded-controller audit.

Uses branch laws, nodal balance, source targets and convex KKT conditions.
Imports an older independent validation helper only for sparse incidence maps;
never imports a production predictor, reducer, controller or score function.
Internal interface observations enter only the final posthoc metric function.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,importlib.util,json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"output/nygrid_2025_dover_parameters"
DEST=OUT/"local_audit"
OLD=ROOT/"output/nygrid_2025_line_parameters"
WEST=ROOT/"output/nygrid_2025_western_audit"
BASE=ROOT/"output/nygrid_2025_dispatch/dispatch"
NAMES=["DYSINGER EAST","WEST CENTRAL","TOTAL EAST","MOSES SOUTH","CENTRAL EAST - VC","UPNY CONED","SPR/DUN-SOUTH"]
CUTOVER="2025-12-20T04:00:00Z"


def require(ok,text):
    if not bool(ok):raise ValueError(text)


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def maxabs(x):return float(np.max(np.abs(x),initial=0.))


def close(a,b,name,tol=1e-7):
    a,b=np.asarray(a),np.asarray(b)
    require(a.shape==b.shape and np.isfinite(a).all() and np.isfinite(b).all(),name+" shape/nonfinite")
    error=maxabs(a-b);require(error<=tol,name+" error "+str(error));return error


def read(path):return json.loads(Path(path).read_text())


def manifest(records):
    require(records and len({r["path"] for r in records})==len(records),"Empty/duplicate manifest")
    result={}
    for r in records:require(sha(ROOT/r["path"])==r["sha256"],"Changed dependency "+r["path"]);result[r["path"]]=r["sha256"]
    return result


def helpers():
    path=ROOT/"scripts/nygrid_2025_line_parameters/validate_annual_replay.py"
    spec=importlib.util.spec_from_file_location("independent_incidence_helpers",path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module,path


def derive(model,generator_buses,helper):
    full,slim=model["full_case"],model["slim_case"]
    large,small=helper.system(full,generator_buses),helper.system(slim,generator_buses)
    keep=np.asarray(model["kept_bus_ids"],int);ri=np.array([large["lookup"][b] for b in keep]);ii=np.array([j for j in range(192) if j not in set(ri)])
    F=large["C"].multiply(large["k"][:,None]).toarray();B=(large["C"].T@F)
    K=np.zeros((413,2));K[410,0]=-large["k"][410];K[411,1]=-large["k"][411]
    A=large["C"].T@K
    L=np.zeros((192,148));L[ri]=np.eye(148);L[ii]=-np.linalg.solve(B[np.ix_(ii,ii)],B[np.ix_(ii,ri)])
    D=np.zeros((192,2));D[ii]=-np.linalg.solve(B[np.ix_(ii,ii)],A[ii])
    reduced=B[np.ix_(ri,ri)]+B[np.ix_(ri,ii)]@L[ii]
    S=A[ri]+B[np.ix_(ri,ii)]@D[ii]
    W=F@D+K;H=F@L
    response_theta=np.zeros((148,2));response_theta[1:]=-np.linalg.solve(reduced[1:,1:],S[1:])
    response=(H@response_theta+W)[[410,411]]
    require(np.linalg.matrix_rank(response)==2,"Two-bank controller response singular")
    shift_basis=np.zeros((274,2));eq=np.flatnonzero((slim["branch"][:,0]==35)&(slim["branch"][:,1]==20001))
    require(len(eq)==1,"Dover condensed series path changed")
    bank_weights=large["k"][[410,411]];shift_basis[eq[0]]=-bank_weights/bank_weights.sum()
    close(shift_basis,model["recovery"]["slim_shift_phase_basis"],"Independent reversed weighted phase basis",1e-12)
    close(D,model["recovery"]["angle_phase_basis"],"Independent angle phase basis",1e-12)
    require(maxabs(full["branch"][:,9])==0 and maxabs(slim["branch"][:,9])==0,"Fixed nonzero phase invalidates declared uniform-power proxy")
    zones=dict(zip(full["bus"][:,0].astype(int),np.asarray(model["full_bus_zones"]).astype(str)))
    interface=helper.legacy_operator(large,zones)
    return dict(large=large,small=small,ri=ri,ii=ii,L=L,D=D,F=F,K=K,H=H,W=W,response=response,shift_basis=shift_basis,interface=interface)


def annual():
    helper,helper_path=helpers()
    receipt_path=OUT/"replay/replay_receipt.json";receipt=read(receipt_path)
    require(receipt["passed"] and receipt["preferred_scenario"]=="bounded_x_nominal" and receipt["fixed_annual_cohort"]==8651,"Final bounded replay is not sealed")
    require(receipt["exact_tracking_is_diagnostic_only"] and receipt["impedances_not_estimated_from_flows"] and not receipt["internal_interface_observations_read"],"Replay qualification changed")
    deps=manifest(receipt["dependencies"]);deps.update(manifest([receipt["fixture_file"],receipt["bank_states_file"],receipt["operating_state_file"]]))
    deps[str(receipt_path.relative_to(ROOT)).replace("\\","/")]=sha(receipt_path)
    deps[str(helper_path.relative_to(ROOT)).replace("\\","/")]=sha(helper_path)
    deps[str(Path(__file__).relative_to(ROOT)).replace("\\","/")]=sha(__file__)
    network=read(OUT/"network/network_receipt.json");deps.update(manifest(network["dependencies"]));deps.update(manifest(network["scenarios"]))
    sourceproof=read(DEST/"Dover_P34_independent_validation.json");require(sourceproof["passed"],"Independent source validation failed")
    require(sha(DEST/"Dover_P34_inputs.npz")==sourceproof["compiled_NPZ_sha256"],"Dover raw target arrays changed")
    with np.load(DEST/"Dover_P34_inputs.npz",allow_pickle=False) as z:source={k:z[k] for k in z.files}
    d=loadmat(BASE/"dispatch.mat",simplify_cells=True,variable_names=["timestamp_utc","bus_pd","bus_qd","dc_pf","gamma","reference_bus"])
    pg=loadmat(WEST/"dispatch/all_boundary_actual_dispatch.mat",simplify_cells=True,variable_names=["gen_pg"])["gen_pg"]
    bounds=loadmat(BASE/"dispatch_bounds.mat",simplify_cells=True,variable_names=["gen_pmin","gen_pmax"])
    register=pd.read_csv(WEST/"corrected/model_generator_register.csv",keep_default_na=False);genbus=register.bus_id.to_numpy(int)
    q=np.load(WEST/"replay/paired_common_mask.npy",allow_pickle=False);times=np.asarray(d["timestamp_utc"]).astype(str);gamma=float(d["gamma"])
    require(q.dtype==bool and q.shape==(8760,) and q.sum()==8651 and np.array_equal(times,source["timestamp_utc"]),"Frozen comparison clock/cohort differs")
    post=times>=CUTOVER;active=q&post;before=q&~post;ix=np.flatnonzero(active)
    require(active.sum()==287 and before.sum()==8364 and np.array_equal(source["prior_common_comparison_mask"],q),"Cutover/cohort differs")
    target=source["forward_NY_to_CT_model_mw"][ix]
    close(target,-gamma*source["raw_posted_hourly_values"][ix],"Raw target sign/scale retained",1e-12)
    unknown=np.all(source["native_max_abs_posted_value"][ix]==0,axis=1);known=~unknown
    require(unknown.sum()==18 and known.sum()==269,"Operating-mode evidence count differs")
    require(np.all(source["strict_source_quality_qualified"][ix]),"Source-qualified cohort changed")
    operating=loadmat(ROOT/receipt["operating_state_file"]["path"],simplify_cells=True)
    require(np.array_equal(operating["hour_index"],np.arange(1,8761)) and np.array_equal(np.asarray(operating["timestamp_utc"]).astype(str),times),"Runtime MAT clock differs")
    require(np.array_equal(np.asarray(operating["qualified"],bool),q) and np.array_equal(np.asarray(operating["post_full_service"],bool),post)
            and float(operating["gamma"])==gamma and str(operating["cutover_utc"])==CUTOVER,"Runtime MAT scope/scale differs")
    require(np.array_equal(operating["raw_posted_hourly_values"],source["raw_posted_hourly_values"],equal_nan=True)
            and np.array_equal(operating["forward_NY_to_CT_model_mw"],source["forward_NY_to_CT_model_mw"],equal_nan=True),"Runtime MAT raw targets changed")
    require(not operating["actual_physical_taps_observed"] and not operating["P34_numeric_as_MW_convention_independently_verified"],"Runtime MAT physical qualification changed")
    pd148=np.pad(d["bus_pd"],((0,0),(0,8)))
    with np.load(ROOT/"output/nygrid_2025_par_controls/controls/inputs.npz",allow_pickle=False) as p:dc=np.column_stack([d["dc_pf"],p["observed_model_mw"]])
    require(maxabs(np.maximum(bounds["gen_pmin"][q,:1436]-pg[q,:1436],0))<1e-7 and maxabs(np.maximum(pg[q,:1436]-bounds["gen_pmax"][q,:1436],0))<1e-7,"Frozen native PG bounds violated")
    items={r["scenario"]:r for r in receipt["scenarios"]};require(len(items)==8,"Final scenario count differs")
    require(set(operating["controls"])==set(items)-{"prior_line_parameters"},"Runtime MAT control scenario coverage differs")
    saved={}
    for name,item in items.items():
        require(sha(ROOT/item["path"])==item["sha256"],"Saved replay changed: "+name);deps[item["path"]]=item["sha256"]
        with np.load(ROOT/item["path"],allow_pickle=False) as z:saved[name]={k:z[k] for k in z.files}
        a=saved[name]
        require(np.array_equal(a["hour_index"],np.arange(1,8761)) and np.array_equal(a["timestamp_utc"],times) and np.array_equal(a["qualified"],q)
                and np.array_equal(a["post_full_service"],post) and float(a["gamma"])==gamma,"Replay axes changed: "+name)
        for field in ["bus_va","interface_pf","nodal_residual_mw"]:
            require(np.isfinite(a[field][q]).all() and np.isnan(a[field][~q]).all(),"Replay validity mask differs: "+name+field)
    prior=saved["prior_line_parameters"]
    with np.load(OLD/"replay/engineering_nominal.npz",allow_pickle=False) as original:
        close(prior["bus_va"][q],original["bus_va"][q],"Frozen be224ec parent angles")
        close(prior["interface_pf"][q],original["interface_pf"][q],"Frozen be224ec parent operators")
    oldfull=loadmat(OLD/"overlays/engineering_nominal/full191_network_cases.mat",simplify_cells=True)
    oldslim=loadmat(OLD/"overlays/engineering_nominal/network_cases.mat",simplify_cells=True)
    states=prior["network_state_ids"].astype(str);equations=[]
    # Independently check the parent equations over all8651hours once. Every
    # unchanged scenario prefix below must be bit-identical to these arrays.
    for state in sorted(set(states[q])):
        use=np.flatnonzero(q&(states==state));s=helper.system(oldslim[state],genbus);f=helper.system(oldfull[state],genbus)
        theta=np.deg2rad(prior["bus_va"][use]);fs=helper.branch_flows(s,theta)
        es=close(fs@s["C"],pg[use]@s["G"]-pd148[use]-s["bus"][:,4]+dc[use]@s["D"],"Prior148KCL")
        rec=oldslim["recovery"][state.removesuffix("_case")];tf=theta@rec["angle_lift"].T+rec["angle_offset"]
        ri=np.array([f["lookup"][b] for b in oldslim["kept_bus_ids"]]);pd191=np.zeros((len(use),191));pd191[:,ri]=pd148[use]
        ff=helper.branch_flows(f,tf);ef=close(ff@f["C"],pg[use]@f["G"]-pd191-f["bus"][:,4]+dc[use]@f["D"],"Prior191KCL")
        c=helper.legacy_operator(f,dict(zip(oldfull["bus_ids"],oldfull["bus_zones"])))
        ei=close(ff@c.T,prior["interface_pf"][use],"Prior inherited operators")
        equations.append(dict(scenario="prior_line_parameters",state=state,hours=len(use),slim_KCL_error=es,full_KCL_error=ef,interface_error=ei,bankflow_error=0.,retained_direct_flow_error=0.))
    bank_state=pd.read_csv(OUT/"replay/Dover_bank_states.csv",float_precision="round_trip")
    require(len(bank_state)==7*287*2 and not bank_state.duplicated(["scenario","hour_index","ptid"]).any(),"Bank-state identity coverage differs")
    require(not bank_state.actual_tap_observed.any() and not bank_state.phase_derived_from_internal_interface_observation.any() and bank_state.raw_target_preserved.all(),"Control qualification flags changed")
    models={r["scenario"]:loadmat(ROOT/r["path"],simplify_cells=True) for r in network["scenarios"]}
    systems={name:derive(model,genbus,helper) for name,model in models.items()}
    sreg=pd.read_csv(ROOT/"output/nygrid_2025_slim/network/branch_register.csv");direct=sreg.iloc[:244].full191_branch_row.to_numpy(int)-1
    control_checks=[];summaries=[]
    for name,item in items.items():
        a=saved[name]
        if item["mode"]=="prior":
            require(np.isnan(a["bank_shift_model_deg"]).all() and np.isnan(a["bank_flow_model_mw"]).all(),"Prior scenario acquired new bank states")
            continue
        require(np.array_equal(a["bus_va"][before],prior["bus_va"][before]) and np.array_equal(a["interface_pf"][before],prior["interface_pf"][before]),"A pre-cutover array changed")
        for field in ["bank_shift_model_deg","bank_shift_unscaled_proxy_deg","bank_flow_model_mw"]:
            require(np.isfinite(a[field][active]).all() and np.isnan(a[field][~active]).all(),"Bank field applied outside qualified post-cutover scope")
        runtime_control=operating["controls"][name]
        for field in ["bank_shift_model_deg","bank_flow_model_mw"]:
            require(np.array_equal(runtime_control[field],a[field],equal_nan=True),"Runtime MAT control state differs from validated NPZ")
        require(str(runtime_control["mode"])==item["mode"] and str(runtime_control["impedance"])==item["impedance"]
                and abs(float(runtime_control["model_angle_limit_degree"])-40*gamma)<1e-12,"Runtime MAT control labels/limit differ")
        e=systems[item["impedance"]];large,small=e["large"],e["small"]
        theta=np.deg2rad(a["bus_va"][ix]);psi=np.deg2rad(a["bank_shift_model_deg"][ix]);tf=theta@e["L"].T+psi@e["D"].T
        flow=tf@e["F"].T+psi@e["K"].T
        sf=helper.branch_flows(small,theta)-(psi@e["shift_basis"].T)*small["k"]
        pdfull=np.zeros((len(ix),192));pdfull[:,e["ri"]]=pd148[ix]
        ef=close(flow@large["C"],pg[ix]@large["G"]-pdfull-large["bus"][:,4]+dc[ix]@large["D"],name+"192KCL")
        es=close(sf@small["C"],pg[ix]@small["G"]-pd148[ix]-small["bus"][:,4]+dc[ix]@small["D"],name+"148KCL")
        require(maxabs(flow[:,210])==0 and maxabs(sf[:,210])==0,"Original Ontario AC surrogate reactivated")
        ed=close(flow[:,direct],sf[:,:244],name+" exact244directrows")
        ei=close(flow@e["interface"].T,a["interface_pf"][ix],name+"7inheritedoperators")
        bank=flow[:,[410,411]];eb=close(bank,a["bank_flow_model_mw"][ix],name+"savedbankflows")
        close(a["bank_shift_unscaled_proxy_deg"][ix],a["bank_shift_model_deg"][ix]/gamma,"Unscaled-angle proxy interpretation",1e-12)
        response=e["response"];residual=bank-target;limit=gamma*np.deg2rad(40.)
        gradient=residual@response
        lipschitz=float(np.linalg.norm(response,2)**2)
        projected=psi-np.clip(psi-gradient/lipschitz,-limit,limit)
        desired=psi-np.linalg.solve(response,residual.T).T
        mode=item["mode"];active_bound=np.zeros(len(ix),bool)
        if mode=="bounded":
            require(maxabs(psi)<=limit+1e-12,"Preferred bounded control exceeds declared phase box")
            require(maxabs(psi[unknown])==0,"Unknown both-zero mode was forced to a raw target")
            require(maxabs(projected[known])<1e-10,"Bounded controller violates convex KKT projected-gradient condition")
            lower=psi<=-limit+1e-10;upper=psi>=limit-1e-10;free=~(lower|upper)
            scale=max(1.,maxabs(response)*maxabs(residual))
            require(np.max(np.maximum(-gradient[known][lower[known]],0),initial=0.)<=1e-8*scale,"Lower-bound KKT sign failure")
            require(np.max(np.maximum(gradient[known][upper[known]],0),initial=0.)<=1e-8*scale,"Upper-bound KKT sign failure")
            require(np.max(abs(gradient[known][free[known]]),initial=0.)<=1e-8*scale,"Free-coordinate KKT stationarity failure")
            active_bound=known&np.any(abs(desired)>limit+1e-12,axis=1)
            require(int(active_bound.sum())==item["phase_bound_active_hours"],"Bounded saturation count differs")
            close(a["bus_va"][ix[unknown]],saved["neutral_"+item["impedance"]]["bus_va"][ix[unknown]],"Neutral fallback angles",1e-10)
            close(a["interface_pf"][ix[unknown]],saved["neutral_"+item["impedance"]]["interface_pf"][ix[unknown]],"Neutral fallback operators",1e-9)
        elif mode=="neutral":require(maxabs(psi)==0,"Neutral scenario has inferred phase")
        elif mode=="exact":require(maxabs(residual)<1e-7 and receipt["exact_tracking_is_diagnostic_only"],"Exact diagnostic target mismatch/scope")
        else:raise ValueError("Unknown operating mode")
        if mode in ["bounded","neutral"]:require(np.all(abs(bank)<=750*gamma+1e-8),"Per-bank necessary P screen failed")
        expected_unknown=np.zeros(8760,bool);expected_unknown[ix]=unknown
        expected_fallback=np.zeros(8760,bool);expected_fallback[ix]=unknown if mode=="bounded" else False
        expected_active=np.zeros(8760,bool);expected_active[ix]=active_bound
        require(np.array_equal(np.asarray(runtime_control["ambiguous_zero_native_mode"],bool),expected_unknown)
                and np.array_equal(np.asarray(runtime_control["neutral_fallback"],bool),expected_fallback)
                and np.array_equal(np.asarray(runtime_control["phase_bound_active"],bool),expected_active),"Runtime MAT operating-mode mask differs")
        for j,h in enumerate(ix):
            rows=bank_state[(bank_state.scenario==name)&(bank_state.hour_index==h+1)].sort_values("ptid")
            require(np.array_equal(rows.ptid,[625149,625150]),"Bank-state PTID ordering changed")
            close(rows.P34_forward_target_model_mw.to_numpy(),target[j],"Raw target record changed",1e-12)
            close(rows.bank_flow_model_mw.to_numpy(),bank[j],"Bank-state flow mismatch")
            close(rows.tracking_residual_model_mw.to_numpy(),residual[j],"Recorded residual was clipped")
            require(rows.ambiguous_zero_native_mode.eq(bool(unknown[j])).all() and rows.neutral_fallback.eq(bool(mode=="bounded" and unknown[j])).all(),"Unknown mode/fallback annotation changed")
            require(rows.phase_bound_active.eq(bool(active_bound[j])).all(),"Phase-bound annotation differs")
            control_checks.append(dict(scenario=name,hour_index=int(h+1),mode=mode,unknown_both_zero_native=bool(unknown[j]),neutral_fallback=bool(mode=="bounded" and unknown[j]),
                objective_tracking_enabled=bool(mode=="exact" or (mode=="bounded" and known[j])),phase_bound_active=bool(active_bound[j]),
                max_tracking_residual_model_mw=maxabs(residual[j]),maximum_abs_model_shift_degree=maxabs(a["bank_shift_model_deg"][h]),
                maximum_unscaled_angle_proxy_degree=maxabs(a["bank_shift_unscaled_proxy_deg"][h]),
                bounded_KKT_projected_gradient_rad=maxabs(projected[j]) if mode=="bounded" and known[j] else None,
                actual_hardware_tap_verified=False))
        equations.append(dict(scenario=name,state="post_full_service192",hours=len(ix),slim_KCL_error=es,full_KCL_error=ef,interface_error=ei,bankflow_error=eb,retained_direct_flow_error=ed))
        summaries.append(dict(scenario=name,mode=mode,post_hours=len(ix),pre_cutover_bit_exact_hours=int(before.sum()),
            phase_limited_hours=int(active_bound.sum()),neutral_fallback_hours=int(unknown.sum()) if mode=="bounded" else 0,
            maximum_known_target_residual_model_mw=maxabs(residual[known]),maximum_all_target_residual_model_mw=maxabs(residual),
            maximum_bounded_projected_gradient_rad=maxabs(projected[known]) if mode=="bounded" else None,
            maximum_actual_bank_abs_model_mw=maxabs(bank),raw_external_targets_preserved=True))
    require(len(control_checks)==2009,"Updated post-cutover scenario-hour coverage incomplete")
    require({p:sha(ROOT/p) for p in deps}==deps,"Protected source/model changed during replay validation")
    pd.DataFrame(equations).to_csv(DEST/"Dover_final_equation_checks.csv",index=False)
    pd.DataFrame(control_checks).to_csv(DEST/"Dover_final_control_checks.csv",index=False)
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),scenarios=8,annual_scenario_hours_accounted=69208,
        prior_complete_equation_hours=8651,new_post_cutover_equation_hours=2009,bit_exact_parent_prefix_hours_each_new_scenario=8364,
        original_97_source_rows_and_6_boundary_transfers_preserved=True,frozen_PG_PD_and_native_bounds_consistent=True,
        controller_KKT_independently_verified=True,raw_targets_not_clipped=True,both_zero_hours_not_forced_to_zero_intertie_flow=True,
        runtime_operating_MAT_all_clocks_controls_targets_and_masks_match=True,
        internal_interface_observations_read=False,impedance_or_phase_fit_to_internal_targets=False,
        physical_factory_R_X_taps_or_meter_units_certified=False,source_scope="conditional posted-flow numeric convention and historical direction-date qualification retained",
        maximum_equation_errors={k:max(float(r[k]) for r in equations) for k in equations[0] if "error" in k},
        summaries=summaries,dependencies=deps,source_hashes_unchanged=True,
        outputs={name:sha(DEST/name) for name in ["Dover_final_equation_checks.csv","Dover_final_control_checks.csv"]})
    (DEST/"Dover_final_replay_validation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ["passed","annual_scenario_hours_accounted","new_post_cutover_equation_hours","maximum_equation_errors"]},indent=2))


def metrics():
    equation_path=DEST/"Dover_final_replay_validation.json";equation=read(equation_path)
    require(equation["passed"] and not equation["internal_interface_observations_read"],"Equation validation must precede scoring")
    deps=dict(equation["dependencies"])
    for p,h in deps.items():require(sha(ROOT/p)==h,"Replay validation is stale")
    deps[str(equation_path.relative_to(ROOT)).replace("\\","/")]=sha(equation_path)
    proof_path=OUT/"comparison/scoring_receipt.json";proof=read(proof_path)
    require(proof["passed"] and proof["internal_observations_posthoc_only"] and proof["source_parameters_frozen_before_scoring"],"Comparison source boundary failed")
    deps.update(manifest(proof["dependencies"]));deps.update(manifest(proof["outputs"]));deps[str(proof_path.relative_to(ROOT)).replace("\\","/")]=sha(proof_path)
    replay=read(OUT/"replay/replay_receipt.json")
    with np.load(OUT/"replay/prior_line_parameters.npz",allow_pickle=False) as z:
        q=z["qualified"];post=z["post_full_service"];times=z["timestamp_utc"];gamma=float(z["gamma"]);base=z["interface_pf"]/gamma
    obs=pd.read_csv(ROOT/"output/nygrid_2025_inputs/load_source/interface_wide.csv",usecols=["timestamp_utc"]+NAMES,float_precision="round_trip")
    require(np.array_equal(obs.timestamp_utc.astype(str),times),"Observed score clock mismatch")
    y=obs[NAMES].to_numpy(float);require(np.isfinite(y[q]).all(),"Qualified observation missing")
    months=pd.to_datetime(times,utc=True).tz_convert("America/New_York").month.to_numpy()
    published=pd.concat([pd.read_csv(OUT/"comparison"/(name+"_metrics.csv"),float_precision="round_trip") for name in ["annual","monthly","post_cutover"]],ignore_index=True)
    require(len(published)==784 and not published.duplicated(["scenario","period","interface"]).any(),"Metric coverage differs")
    require(not published.internal_observations_used_for_parameter_fit.any(),"Internal observation fitting promoted")
    published=published.set_index(["scenario","period","interface"]);rows=[];maximum=0.
    for item in replay["scenarios"]:
        with np.load(ROOT/item["path"],allow_pickle=False) as z:prediction=z["interface_pf"]/gamma
        periods=[("annual",q)]+[(f"month_{m:02}",q&(months==m)) for m in range(1,13)]+[("post_Dover_full_service",q&post)]
        for period,use in periods:
            for j,name in enumerate(NAMES):
                error=prediction[use,j]-y[use,j];old=base[use,j]-y[use,j]
                values=dict(mae_public_mw=float(np.mean(abs(error))),rmse_public_mw=float(np.sqrt(np.dot(error,error)/len(error))),
                    bias_public_mw=float(np.sum(error)/len(error)),wape_percent=float(100*np.sum(abs(error))/np.sum(abs(y[use,j]))),
                    mae_change_public_mw=float(np.mean(abs(error))-np.mean(abs(old))))
                source=published.loc[(item["scenario"],period,name)];require(source.hours==use.sum(),"Score cohort mismatch")
                diff=max(abs(v-float(source[k])) for k,v in values.items());maximum=max(maximum,diff)
                require(diff<1e-9,"Independent metric mismatch")
                rows.append(dict(scenario=item["scenario"],period=period,interface=name,hours=int(use.sum()),maximum_published_difference=diff,**values))
    require({p:sha(ROOT/p) for p in deps}==deps,"Scoring dependency changed during independent check")
    pd.DataFrame(rows).to_csv(DEST/"Dover_independent_comparison_metrics.csv",index=False)
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),annual_rows=56,monthly_rows=672,post_cutover_rows=56,
        maximum_metric_difference=maximum,source_parameters_not_chosen_by_scores=True,internal_observations_posthoc_only=True,
        conditional_external_flow_assumptions_and_uncertified_physical_gates_retained=True,dependencies=deps,source_hashes_unchanged=True,
        output_sha256=sha(DEST/"Dover_independent_comparison_metrics.csv"))
    table=pd.DataFrame(rows)
    post_table=table[table.period=="post_Dover_full_service"].set_index(["scenario","interface"])
    attribution=[]
    for name in NAMES:
        prior=float(post_table.loc[("prior_line_parameters",name),"mae_public_mw"])
        neutral=float(post_table.loc[("neutral_x_nominal",name),"mae_public_mw"])
        bounded=float(post_table.loc[("bounded_x_nominal",name),"mae_public_mw"])
        attribution.append(dict(interface=name,period_hours=287,prior_mae_public_mw=prior,neutral_new_parameter_mae_public_mw=neutral,
            bounded_external_control_mae_public_mw=bounded,parameter_plus_neutral_state_mae_change=neutral-prior,
            external_control_given_same_new_parameters_mae_change=bounded-neutral,
            interpretation="within_model_counterfactual_difference_not_physical_flowgate_certification"))
    pd.DataFrame(attribution).to_csv(DEST/"Dover_post_cutover_effect_attribution.csv",index=False)
    report["post_cutover_effect_attribution"]=attribution
    report["effect_attribution_sha256"]=sha(DEST/"Dover_post_cutover_effect_attribution.csv")
    (DEST/"Dover_comparison_validation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ["passed","annual_rows","monthly_rows","post_cutover_rows","maximum_metric_difference"]},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--metrics-only",action="store_true");parser.add_argument("--equations-only",action="store_true")
    args=parser.parse_args()
    if not args.metrics_only:annual()
    if not args.equations_only:metrics()
