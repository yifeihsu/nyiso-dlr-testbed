"""Isolated full191-to-slim148 parameter overlays using the frozen DC reducer.

Only explicit estimates for six project-path records absent from the frozen
2019 model are accepted; that baseline difference is not a commissioning date.
Topology, injections, historical source rows and fixed-control records are
immutable. Recovered operators remain the old accounting-zone functionals;
this module never promotes them to physical NYISO flowgates or reads observed
interface flows. R/B/ratings on Schur edges remain nonphysical DC placeholders.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
from datetime import datetime,timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat,savemat

ROOT=Path(__file__).resolve().parents[2]
DEFAULT=ROOT/"output/nygrid_2025_line_parameters/overlays"
PINS={
    "output/nygrid_2025_downstate/network/network_cases.mat":"89af6622ece7539d4056e3840ebda6059afcc830f0afbbdab749c43d90a503e4",
    "output/nygrid_2025_slim/network/network_cases.mat":"3c990e658464037ad36ab427150ba3c358624c1d0e3d795adb90aca91abdbc58",
    "output/nygrid_2025_downstate/network/branch_register.csv":"6a574d53b40eb2bf08dba851757a5d56ab6b4d89377b2a33e5d6319d5cd2a18f",
    "output/nygrid_2025_downstate/network/bus_register.csv":"bfab44648f3d2052e79a2a8db7c7e7390874f6bace1c575f6c94868206127f27",
    "output/nygrid_2025_slim/network/branch_register.csv":"547c40ce859c358ded212f1755b879ee508a2d56c1354e7d40782b11e0bfb82d",
    "scripts/nygrid_2025_slim/build_slim_network.py":"574d8d6eaac69fe2002fba8fa88e24ed0f179c8b78f66ebcdfffffdeea70d9bc",
}
VARIANTS=["refined_2019","refined_2025_pre_may","refined_2025_may21","refined_2025_may30","refined_2025"]
ALLOWED={"CV:PV_CV_F84","DOVER:CV_DOVER_Y17","DOVER:DOVER_LM_398","RCC:CABLE:QUEENS","RCC:CABLE:BROOKLYN","RCC:CABLE:STATEN"}
PARAMETERS={"r_pu":2,"x_pu":3,"b_pu":4,"rate_a_mva":5,"rate_b_mva":6,"rate_c_mva":7}


def require(condition,text):
    if not bool(condition):raise ValueError(text)


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def maxabs(value):return float(np.max(np.abs(value),initial=0.))


def load_frozen():
    hashes={p:sha(ROOT/p) for p in PINS};require(hashes==PINS,"Frozen model or reducer changed")
    spec=importlib.util.spec_from_file_location("frozen_slim_reducer",ROOT/"scripts/nygrid_2025_slim/build_slim_network.py")
    reducer=importlib.util.module_from_spec(spec);spec.loader.exec_module(reducer)
    full=loadmat(ROOT/"output/nygrid_2025_downstate/network/network_cases.mat",simplify_cells=True)
    slim=loadmat(ROOT/"output/nygrid_2025_slim/network/network_cases.mat",simplify_cells=True)
    fullreg=pd.read_csv(ROOT/"output/nygrid_2025_downstate/network/branch_register.csv",keep_default_na=False)
    slimreg=pd.read_csv(ROOT/"output/nygrid_2025_slim/network/branch_register.csv",keep_default_na=False)
    busreg=pd.read_csv(ROOT/"output/nygrid_2025_downstate/network/bus_register.csv",keep_default_na=False)
    require(len(fullreg)==410 and len(slimreg)==274 and fullreg.branch_key.is_unique and slimreg.branch_key.is_unique,"Branch identity axes changed")
    require(set(fullreg.loc[(fullreg.refined_2019_status==0)&(fullreg.refined_2025_status==1),"branch_key"])==ALLOWED,"Allowed project identities changed")
    return dict(full=full,slim=slim,fullreg=fullreg,slimreg=slimreg,busreg=busreg,reducer=reducer,hashes=hashes)


def validate_updates(frame):
    frame=frame.copy()
    if "full191_branch_key" not in frame and "branch_key" in frame:
        frame["full191_branch_key"]=frame.branch_key
    if "branch_key" in frame:
        require((frame.branch_key.astype(str)==frame.full191_branch_key.astype(str)).all(),"Conflicting branch identity columns")
    required={"scenario_name","full191_branch_key","base_mva",*PARAMETERS}
    require(required.issubset(frame.columns),"Estimate CSV missing explicit columns: "+str(sorted(required-set(frame.columns))))
    require(len(frame)>0,"Empty estimate CSV; use identity-only explicitly")
    require(not frame.duplicated(["scenario_name","full191_branch_key"]).any(),"Duplicate scenario/project estimate")
    require(frame.full191_branch_key.isin(ALLOWED).all(),"Estimate attempts to change a non-project or historical source record")
    require(all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}",str(x)) for x in frame.scenario_name),"Unsafe/ambiguous scenario name")
    require(not frame.scenario_name.isin(["identity_reference"]).any(),"Identity scenario name is reserved")
    nums=frame[["base_mva",*PARAMETERS]].apply(pd.to_numeric,errors="raise")
    require(np.isfinite(nums.to_numpy()).all(),"Nonfinite estimate")
    require((nums.base_mva==100.).all(),"Only explicit100MVA-base parameters are accepted")
    require((nums.r_pu>=0).all() and (nums.x_pu>0).all() and (nums.b_pu>=0).all(),"Estimate must be a finite passive positive-X circuit")
    require((nums[["rate_a_mva","rate_b_mva","rate_c_mva"]]>=0).all().all(),"Negative ratings are invalid; zero means unrated")
    # These fields may appear as provenance, but are never permitted to request
    # a topology, angle, or transformer-control change through this interface.
    forbidden=[c for c in ["from_bus","to_bus","status","tap","shift_degree"] if c in frame]
    require(not forbidden,"Topology/control fields are outside the parameter-overlay contract: "+str(forbidden))
    frame[nums.columns]=nums
    return frame


def reconstruct(frozen,updates,scenario):
    full,slim,reg,sreg,busreg,reducer=(frozen[k] for k in ["full","slim","fullreg","slimreg","busreg","reducer"])
    cases={v:copy.deepcopy(full[v+"_case"]) for v in VARIANTS}
    lookup=dict(zip(reg.branch_key,reg.index))
    changes=[]
    for row in updates.to_dict("records"):
        key=row["full191_branch_key"];j=int(lookup[key])
        require(key in ALLOWED and int(reg.iloc[j].source_branch_row)==0 and j>=225,"Historical source mutation rejected")
        for v in VARIANTS:
            old=full[v+"_case"]["branch"][j].copy()
            for field,column in PARAMETERS.items():cases[v]["branch"][j,column]=float(row[field])
            for field,column in PARAMETERS.items():
                changes.append(dict(scenario_name=scenario,variant=v,full191_branch_key=key,full191_branch_row=j+1,field=field,
                                    before=float(old[column]),after=float(cases[v]["branch"][j,column]),
                                    changed=bool(old[column]!=cases[v]["branch"][j,column]),status=int(old[10])))
    keep=np.asarray(slim["kept_bus_ids"],int)
    expected_direct=sreg.iloc[:244].full191_branch_row.to_numpy(int)-1
    expected_pairs=[tuple(map(int,row)) for row in sreg.iloc[244:][["from_bus","to_bus"]].to_numpy()]
    require(len(keep)==148 and np.array_equal(keep[:140],np.arange(1,141)),"Retained bus axis changed")
    require(len(expected_direct)==244 and len(expected_pairs)==30,"Frozen support changed")
    reductions={v:reducer.reduce_added_components(cases[v],keep) for v in VARIANTS}
    actual_direct=sorted({int(j) for r in reductions.values() for j in r["direct_rows"] if j<225 or any(c["branch"][j,10] for c in cases.values())})
    actual_pairs=sorted({pair for r in reductions.values() for pair in r["edges"]})
    require(np.array_equal(actual_direct,expected_direct) and actual_pairs==expected_pairs,"Parameter overlay changed structural direct/equivalent support")
    zones=dict(zip(busreg.model_bus,busreg.accounting_zone))
    outputs={};recovery={};checks=[];new_sreg=sreg.copy()
    source_ix=np.flatnonzero(reg.source_branch_row.to_numpy(int)>0)
    update_ix={lookup[k] for k in updates.full191_branch_key} if len(updates) else set()
    immutable_ix=np.array([j for j in range(410) if j not in update_ix],int)
    for v in VARIANTS:
        case,r=cases[v],reductions[v];old_full=full[v+"_case"]
        for field in ["bus","gen","dcline"]:
            require(np.array_equal(case[field],old_full[field]),"Overlay changed immutable "+field)
        require(np.array_equal(case["branch"][immutable_ix],old_full["branch"][immutable_ix]),"Unlisted branch changed")
        require(np.array_equal(case["branch"][source_ix],old_full["branch"][source_ix]),"One of97 historical source circuits changed")
        require(np.array_equal(case["branch"][:,[0,1,8,9,10,11,12]],old_full["branch"][:,[0,1,8,9,10,11,12]]),"Topology/control/angle bounds changed")
        require(np.array_equal(case["branch"][210],old_full["branch"][210]) and case["dcline"].shape==(4,17),"FourDC plusPS33/PS34 substitution contract changed")
        candidate=copy.deepcopy(slim[v+"_case"])
        direct=case["branch"][expected_direct,:13].copy();added=[]
        for pair in expected_pairs:
            active=pair in r["edges"];item=r["edges"].get(pair)
            if item is None:item=next(q["edges"][pair] for q in reductions.values() if pair in q["edges"])
            a,b=pair;added.append([a,b,0.,item["x_pu"],0.,0.,0.,0.,1.,item["shift_degree"],int(active),-360.,360.])
        candidate["branch"]=np.r_[direct,np.asarray(added)]
        net=reducer.dc(candidate)
        berr=maxabs(net["B"]-r["Schur_B"]);perr=maxabs(net["phase_bus"]-r["Schur_phase"])
        require(berr<1e-8 and perr<1e-8,"Reconstructed slim case differs from exact Schur response")
        c=reducer.zone_operators(case,zones);H=c@r["branch_angle_matrix"];h=c@r["branch_flow_offset"]
        lc=reducer.zone_operators(candidate,zones);lH=lc@net["F"];lh=lc@net["phase_branch"]
        maps=[];exact=[];omitted=[]
        for ix,iid in enumerate(slim["interface_ids"]):
            ok=maxabs(H[ix]-lH[ix])<1e-8 and abs(h[ix]-lh[ix])<1e-8
            (exact if ok else omitted).append(int(iid))
            if ok:maps.extend([int(iid),int(np.sign(lc[ix,j]))*(int(j)+1)] for j in np.flatnonzero(lc[ix]))
        candidate["if"]=dict(map=np.asarray(maps,int),map_role="only_verified_exact_local_signed_functionals",
                             exact_interface_ids=np.asarray(exact,int),omitted_interface_ids=np.asarray(omitted,int),
                             full_seven_interface_contract="recovery.interface_angle_matrix_times_retained_radians_plus_interface_flow_offset")
        recovery[v]=dict(angle_lift=r["angle_lift"],angle_offset=r["angle_offset"],branch_angle_matrix=r["branch_angle_matrix"],branch_flow_offset=r["branch_flow_offset"],
                         interface_angle_matrix=H,interface_flow_offset=h,angle_units="radians",operator_units="model_MW_per_radian",offset_units="model_MW",
                         local_interface_branch_matrix=lc,local_interface_angle_matrix=lH,local_interface_flow_offset=lh,full_interface_branch_matrix=c,
                         Schur_B=r["Schur_B"],Schur_phase=r["Schur_phase"],retained_full_indices_1based=r["retained_indices"]+1,
                         eliminated_full_indices_1based=r["eliminated_indices"]+1,injection_projection=r["injection_projection"],
                         exact_local_interface_ids=np.asarray(exact,int),omitted_local_interface_ids=np.asarray(omitted,int))
        for field,column in {**PARAMETERS,"status":10,"shift_degree":9}.items():new_sreg[v+"_"+field]=candidate["branch"][:,column]
        outputs[v+"_case"]=candidate
        baseline_branch_error=maxabs(candidate["branch"]-slim[v+"_case"]["branch"][:,:13])
        rec_errors={key:maxabs(np.atleast_1d(value).astype(float)-np.atleast_1d(slim["recovery"][v][key]).astype(float)) for key,value in recovery[v].items() if not isinstance(value,str)}
        if not len(updates):
            require(baseline_branch_error==0 and max(rec_errors.values())==0,"Unchanged overlay does not reproduce the frozen slim model exactly")
        checks.append(dict(scenario_name=scenario,variant=v,full_buses=191,slim_buses=148,full_branch_records=410,slim_branch_records=274,
                           direct_records=244,derived_equivalent_records=30,original_parent_buses_preserved=140,historical_circuits_preserved=97,
                           bus_gen_original4DC_unchanged=True,PS33_PS34_substitution_contract_unchanged=True,
                           maximum_Schur_B_realization_error_MW_per_rad=berr,maximum_affine_phase_realization_error_model_MW=perr,
                           branch_parameter_difference_from_reference=baseline_branch_error,maximum_recovery_difference_from_reference=max(rec_errors.values()),
                           reference_identity_exact=bool(not len(updates) and baseline_branch_error==0 and max(rec_errors.values())==0),
                           active_updated_project_rows=sum(case["branch"][j,10] for j in update_ix),physical_2025_flowgate_promoted=False,AC_equivalence_claimed=False))
    full_payload={v+"_case":cases[v] for v in VARIANTS}
    for field in ["parent_case","source_case","bus_ids","bus_zones","branch_keys","load_allocation_identity","load_allocation_asset","generator_bus_identity","generator_bus_asset","gamma"]:
        full_payload[field]=copy.deepcopy(full[field])
    slim_payload={k:copy.deepcopy(value) for k,value in slim.items() if not k.startswith("__") and k not in outputs and k!="recovery"}
    slim_payload.update(outputs);slim_payload["recovery"]=recovery
    metadata=dict(scenario_name=scenario,scope="parameter_only_project_paths_absent_from_frozen2019_model_not_calendar_commissioning_claim",input_bus_gen_load_control_axes_unchanged=True,
                  original_historical97_source_rows_unchanged=True,physical_2025_gate_promotion=False,
                  full191_R_B_retained_but_slim_is_DC_only=True,source_names_and_rows_do_not_certify_asbuilt_parameters=True)
    full_payload["parameter_overlay"]=metadata;slim_payload["parameter_overlay"]=metadata
    change_columns=["scenario_name","variant","full191_branch_key","full191_branch_row","field","before","after","changed","status"]
    return dict(full=full_payload,slim=slim_payload,slim_register=new_sreg,changes=pd.DataFrame(changes,columns=change_columns),checks=pd.DataFrame(checks),updates=updates)


def write_scenario(result,folder,scenario,dependencies,identity_checks):
    folder=Path(folder);require(not folder.exists(),"Scenario output already exists; choose a fresh directory")
    folder.mkdir(parents=True)
    savemat(folder/"full191_network_cases.mat",result["full"],do_compression=True,long_field_names=True)
    savemat(folder/"network_cases.mat",result["slim"],do_compression=True,long_field_names=True)
    result["slim_register"].to_csv(folder/"slim148_branch_register.csv",index=False)
    result["checks"].to_csv(folder/"reduction_checks.csv",index=False)
    result["changes"].to_csv(folder/"full191_parameter_changes.csv",index=False)
    result["updates"].to_csv(folder/"applied_parameter_estimates.csv",index=False)
    # Reload the actual saved numeric artifacts, not just in-memory objects.
    saved_full=loadmat(folder/"full191_network_cases.mat",simplify_cells=True)
    saved_slim=loadmat(folder/"network_cases.mat",simplify_cells=True)
    for v in VARIANTS:
        require(np.array_equal(saved_full[v+"_case"]["branch"],result["full"][v+"_case"]["branch"]),"Saved full branch mismatch")
        require(np.array_equal(saved_slim[v+"_case"]["branch"],result["slim"][v+"_case"]["branch"]),"Saved slim branch mismatch")
        for field in ["bus","gen","dcline"]:
            require(np.array_equal(saved_slim[v+"_case"][field],result["slim"][v+"_case"][field]),"Saved device data mismatch")
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),scenario_name=scenario,parameters_applied=len(result["updates"]),
                topology_variants=VARIANTS,unchanged_overlay_identity_checks=identity_checks,checks=result["checks"].to_dict("records"),
                dependencies=dependencies,script_sha256=sha(__file__),observed_interface_flows_used=False,annual_PF_run=False,
                physical_2025_flowgate_promoted=False,AC_or_thermal_certification=False,
                outputs={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
    (folder/"overlay_receipt.json").write_text(json.dumps(report,indent=2)+"\n")
    return report


def build(parameters=None,output=DEFAULT,identity_only=False):
    frozen=load_frozen();deps=frozen["hashes"].copy()
    empty=pd.DataFrame(columns=["scenario_name","full191_branch_key","base_mva",*PARAMETERS])
    identity=reconstruct(frozen,empty,"identity_reference")
    identity_checks=identity["checks"].to_dict("records")
    if identity_only:
        require(parameters is None,"Identity-only cannot apply estimates")
        jobs=[("identity_reference",identity)]
    else:
        require(parameters is not None,"Explicit finalized estimate CSV required")
        parameters=Path(parameters).resolve();df=validate_updates(pd.read_csv(parameters,keep_default_na=False,float_precision="round_trip"))
        deps[str(parameters.relative_to(ROOT)).replace("\\","/")]=sha(parameters)
        jobs=[("identity_reference",identity)]+[(name,reconstruct(frozen,part,name)) for name,part in df.groupby("scenario_name",sort=True)]
    reports=[]
    for scenario,result in jobs:
        reports.append(write_scenario(result,Path(output)/scenario,scenario,deps,identity_checks))
    require({p:sha(ROOT/p) for p in deps}==deps,"Protected source/estimates changed during overlay")
    print(json.dumps(dict(passed=True,scenarios=[r["scenario_name"] for r in reports],identity_exact_all_five_states=True,
                         maximum_Schur_error=max(c["maximum_Schur_B_realization_error_MW_per_rad"] for r in reports for c in r["checks"])),indent=2))
    return reports


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--parameters",type=Path);parser.add_argument("--output",type=Path,default=DEFAULT);parser.add_argument("--identity-only",action="store_true")
    args=parser.parse_args();build(args.parameters,args.output,args.identity_only)
