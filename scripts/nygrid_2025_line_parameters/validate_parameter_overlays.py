"""Independent saved-overlay and engineering-basis validation; no PF/observations.

No production line-physics or Schur solver is imported for numerical checks.
The overlay parser is imported only for adversarial input-contract probes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from datetime import datetime,timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/"output/nygrid_2025_line_parameters"
VARIANTS=["refined_2019","refined_2025_pre_may","refined_2025_may21","refined_2025_may30","refined_2025"]
FIELDS={"r_pu":2,"x_pu":3,"b_pu":4,"rate_a_mva":5,"rate_b_mva":6,"rate_c_mva":7}
F84="CV:PV_CV_F84";STATEN="RCC:CABLE:STATEN"
PASS_THROUGH={"DOVER:CV_DOVER_Y17","DOVER:DOVER_LM_398","RCC:CABLE:QUEENS","RCC:CABLE:BROOKLYN"}


def require(ok,text):
    if not bool(ok):raise ValueError(text)


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def maxabs(value):return float(np.max(np.abs(value),initial=0.))


def law(case):
    bus,branch=np.asarray(case["bus"],float),np.asarray(case["branch"],float)
    ids=bus[:,0].astype(int);lookup={b:j for j,b in enumerate(ids)}
    C=np.zeros((len(branch),len(bus)))
    for j,row in enumerate(branch):C[j,lookup[int(row[0])]]=1;C[j,lookup[int(row[1])]]=-1
    tap=branch[:,8].copy();tap[tap==0]=1
    w=float(case["baseMVA"])*branch[:,10]/branch[:,3]/tap
    F=w[:,None]*C;phase=-w*np.deg2rad(branch[:,9])
    return dict(C=C,F=F,phase=phase,B=C.T@F,p=C.T@phase,ids=ids,lookup=lookup)


def independent_f84(catalog,project,geometry,images):
    def value(field):
        selected=project[(project.asset_key==F84)&(project.field==field)]
        require(len(selected)==1,"Missing/ambiguous source field "+field)
        return selected.iloc[0].value
    conductor=catalog.loc["PRYSMIAN_ACSS_MALLARD_795_0_30_19"]
    require(conductor.family=="ACSS" and conductor.code_word=="Mallard" and float(conductor.aluminum_kcmil)==795.,"Wrong conductor family/size")
    require(int(value("subconductors_per_phase"))==2,"Wrong phase bundle size")
    diameter=float(conductor.diameter_m);gmr=float(conductor.gmr_m)
    require(abs(diameter-float(value("conductor_diameter"))*.0254)<1e-14,"Project/catalog diameter mismatch")
    temperature=float(value("normal_rating_conductor_temperature"))
    require(75<=temperature<=200,"Source temperature outside validated interpolation range")
    resistance=float(conductor.r_ac75_ohm_per_m)+(float(conductor.r_ac200_ohm_per_m)-float(conductor.r_ac75_ohm_per_m))*(temperature-75.)/125.
    length=float(value("length"))*1609.344;bundle_spacing=float(value("bundle_spacing"))*.0254
    xy=np.asarray(geometry,float);pairs=[(0,1),(1,2),(2,0)]
    distances=np.array([np.hypot(*(xy[a]-xy[b])) for a,b in pairs])
    gmd=float(np.exp(np.mean(np.log(distances))))
    ds=np.sqrt(gmr*bundle_spacing);req=np.sqrt(diameter/2*bundle_spacing)
    L=2e-7*np.log(gmd/ds)
    if images:
        require(np.all(xy[:,1]>0),"Image geometry below ground")
        potential=np.zeros((3,3))
        for j in range(3):potential[j,j]=np.log(2*xy[j,1]/req)
        for (a,b),d in zip(pairs,distances):
            potential[a,b]=potential[b,a]=np.log(np.hypot(xy[a,0]-xy[b,0],xy[a,1]+xy[b,1])/d)
        factor=np.trace(potential)/3-(potential.sum()-np.trace(potential))/6
    else:factor=np.log(gmd/req)
    C=2*np.pi*8.8541878128e-12/factor;omega=2*np.pi*60;zb=float(value("nominal_voltage"))**2/100.
    return dict(r_pu=resistance*length/2/zb,x_pu=omega*L*length/zb,b_pu=omega*C*length*zb,
                gmd_m=gmd,bundle_gmr_m=ds,bundle_radius_m=req,rac95_ohm_per_m=resistance,
                design_rating_mva=np.sqrt(3)*float(value("nominal_voltage"))*float(value("summer_normal_current"))/1000.)


def guard_checks(valid_frame):
    spec=importlib.util.spec_from_file_location("overlay_input_guards_only",ROOT/"scripts/nygrid_2025_line_parameters/build_parameter_overlay.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    probes=[]
    def rejected(name,mutate):
        value=mutate(valid_frame.iloc[:1].copy())
        try:module.validate_updates(value)
        except (ValueError,TypeError):probes.append(dict(probe=name,rejected=True));return
        raise ValueError("Invalid estimate accepted: "+name)
    def setcol(df,key,value):df[key]=value;return df
    rejected("historical_PERFORM_row_mutation",lambda d:setcol(d,"full191_branch_key","PERFORM:1389"))
    rejected("original_PAR_control_row_mutation",lambda d:setcol(d,"full191_branch_key","PARENT:211"))
    rejected("duplicate_project_row",lambda d:pd.concat([d,d],ignore_index=True))
    rejected("nonfinite_impedance",lambda d:setcol(d,"x_pu",float("nan")))
    rejected("zero_series_reactance",lambda d:setcol(d,"x_pu",0.))
    rejected("negative_resistance",lambda d:setcol(d,"r_pu",-1.))
    rejected("wrong_MVA_base",lambda d:setcol(d,"base_mva",50.))
    rejected("path_traversal_scenario",lambda d:setcol(d,"scenario_name","../escape"))
    rejected("status_mutation",lambda d:setcol(d,"status",0))
    rejected("missing_explicit_emergency_rating_field",lambda d:d.drop(columns="rate_c_mva"))
    accepted=module.validate_updates(valid_frame.iloc[:1].copy())
    require(float(accepted.iloc[0].rate_b_mva)==0 and float(accepted.iloc[0].rate_c_mva)==0,"Unknown emergency rating placeholders rejected")
    probes.append(dict(probe="explicit_zero_unknown_emergency_ratings",rejected=False,accepted=True))
    return probes


def validate(overlays=BASE/"overlays",output=BASE/"validation"):
    overlays,output=Path(overlays),Path(output)
    basis_path=BASE/"estimates/engineering_basis.json";basis=json.loads(basis_path.read_text())
    require(basis["passed"] and basis["internal_interface_observations_used"] is False,"Engineering basis scope invalid")
    dependencies={str(basis_path.relative_to(ROOT)).replace("\\","/"):sha(basis_path)}
    for item in basis["dependencies"]+basis["outputs"]:
        require(sha(ROOT/item["path"])==item["sha256"],"Engineering source/output hash changed: "+item["path"])
        dependencies[item["path"]]=item["sha256"]
    frame=pd.read_csv(BASE/"estimates/parameter_estimates.csv",keep_default_na=False,float_precision="round_trip")
    require(len(frame)==24 and frame.scenario_name.nunique()==4,"Final estimate scenario axes differ")
    require(not frame.duplicated(["scenario_name","full191_branch_key"]).any(),"Duplicate estimate identity")
    catalog=pd.read_csv(BASE/"conductors/conductor_catalog.csv",keep_default_na=False,float_precision="round_trip").set_index("catalog_id")
    project=pd.read_csv(BASE/"project_source_register.csv",keep_default_na=False,float_precision="round_trip")
    full_path=ROOT/"output/nygrid_2025_downstate/network/network_cases.mat"
    slim_path=ROOT/"output/nygrid_2025_slim/network/network_cases.mat"
    ref_full=loadmat(full_path,simplify_cells=True);ref_slim=loadmat(slim_path,simplify_cells=True)
    reg=pd.read_csv(ROOT/"output/nygrid_2025_downstate/network/branch_register.csv",keep_default_na=False)
    source_rows=np.flatnonzero(reg.source_branch_row.to_numpy(int)>0);lookup=dict(zip(reg.branch_key,reg.index))
    require(len(source_rows)==97,"Historical source count changed")
    for p in [full_path,slim_path,ROOT/"output/nygrid_2025_downstate/network/branch_register.csv",Path(__file__)]:
        dependencies[str(p.relative_to(ROOT)).replace("\\","/")]=sha(p)
    physics=[]
    original_geometry=np.asarray(json.loads(project[(project.asset_key==F84)&(project.field=="representative_phase_centers")].iloc[0].value))*0.3048
    geometries={"engineering_nominal":(original_geometry,False),"geometry_spacing_80pct":(original_geometry*.8,False),
                "geometry_spacing_120pct":(original_geometry*1.2,False),"ground_image_30ft":(original_geometry+np.array([0,30*.3048]),True)}
    for item in basis["F84_estimates"]:
        scenario=item["scenario_name"];geometry,images=geometries[scenario]
        require(maxabs(np.asarray(item["geometry_m"])-geometry)==0,"Scenario geometry differs from declared source/sensitivity")
        result=independent_f84(catalog,project,geometry,images)
        row=frame[(frame.scenario_name==scenario)&(frame.full191_branch_key==F84)].iloc[0]
        error=max(abs(result[f]-float(row[f])) for f in ["r_pu","x_pu","b_pu"])
        json_error=max(abs(result[f]-float(item[f])) for f in ["r_pu","x_pu","b_pu"])
        require(error<1e-12 and json_error<1e-12,"Independent F84 calculation mismatch")
        require(float(row.rate_a_mva)==1323 and float(row.rate_b_mva)==float(row.rate_c_mva)==0,"F84 design/emergency rating distinction lost")
        require(abs(result["design_rating_mva"]-1323)<.01,"Bundle current to design MVA conversion failed")
        physics.append(dict(scenario_name=scenario,independent_R_X_B_max_error_pu=error,engineering_basis_max_error_pu=json_error,
                            design_rating_rounding_difference_mva=abs(result["design_rating_mva"]-1323),
                            no_bundle_double_count_in_rating=True,geometry_is_declared_estimate_not_route_average=True,**result))
    # Verify exact retention and the separately sourced Staten length correction
    # against original MAT binary values, never against a rounded register CSV.
    old_branch=ref_full["refined_2025_case"]["branch"]
    for row in frame.to_dict("records"):
        j=lookup[row["full191_branch_key"]]
        if row["full191_branch_key"] in PASS_THROUGH:
            require(np.array_equal(np.array([row[f] for f in FIELDS]),old_branch[j,list(FIELDS.values())]),"Retained project estimate was rounded or changed")
        elif row["full191_branch_key"]==STATEN:
            require(abs(row["r_pu"]-old_branch[j,2]*9.4/9.2)<1e-16 and abs(row["x_pu"]-old_branch[j,3]*9.4/9.2)<1e-16,"Staten length-ratio correction differs")
            require(all(row[f]==old_branch[j,c] for f,c in FIELDS.items() if c not in [2,3]),"Staten unknown charging/rating was invented")
    html=(BASE/"sources/cables/Haugland_Goethals_FoxHills.html").read_text(encoding="utf-8")
    require(all(s in html for s in ["9.4-mile","138 kV XLPE","single-circuit"]),"Staten primary route/classifier evidence absent")
    folders=sorted(p for p in overlays.iterdir() if p.is_dir())
    expected={"identity_reference",*frame.scenario_name.unique()}
    require({p.name for p in folders}==expected,"Missing/extra overlay scenario")
    equations=[]
    for folder in folders:
        receipt_path=folder/"overlay_receipt.json";receipt=json.loads(receipt_path.read_text());require(receipt["passed"],"Failed overlay receipt")
        for path,digest in receipt["dependencies"].items():
            require(sha(ROOT/path)==digest,"Overlay dependency changed: "+path);dependencies[path]=digest
        require(sha(ROOT/"scripts/nygrid_2025_line_parameters/build_parameter_overlay.py")==receipt["script_sha256"],"Overlay builder code changed")
        dependencies[str((ROOT/"scripts/nygrid_2025_line_parameters/build_parameter_overlay.py").relative_to(ROOT)).replace("\\","/")]=receipt["script_sha256"]
        dependencies[str(receipt_path.relative_to(ROOT)).replace("\\","/")]=sha(receipt_path)
        for name,digest in receipt["outputs"].items():
            require(sha(folder/name)==digest,"Saved overlay file changed: "+name)
            dependencies[str((folder/name).relative_to(ROOT)).replace("\\","/")]=digest
        full=loadmat(folder/"full191_network_cases.mat",simplify_cells=True);slim=loadmat(folder/"network_cases.mat",simplify_cells=True)
        supplied=frame[frame.scenario_name==folder.name]
        for v in VARIANTS:
            fc,sc=full[v+"_case"],slim[v+"_case"];old=ref_full[v+"_case"]
            expected_branch=old["branch"].copy()
            for row in supplied.to_dict("records"):
                for f,c in FIELDS.items():expected_branch[lookup[row["full191_branch_key"]],c]=row[f]
            require(np.array_equal(fc["branch"],expected_branch),"Saved full191 parameters differ from explicit CSV")
            for field in ["bus","gen","dcline"]:
                require(np.array_equal(fc[field],old[field]),"Full input/device record changed: "+field)
                require(np.array_equal(sc[field],ref_slim[v+"_case"][field]),"Slim input/device record changed: "+field)
            require(np.array_equal(fc["branch"][source_rows],old["branch"][source_rows]),"Historical source circuit changed")
            require(np.array_equal(fc["branch"][210],old["branch"][210]),"Original PS33/PS34 replacement row changed")
            net,small=law(fc),law(sc);keep=np.asarray(slim["kept_bus_ids"],int)
            require(np.array_equal(keep,np.asarray(ref_slim["kept_bus_ids"],int)) and 48 in keep and 100 in keep,"Control terminal/retained axes changed")
            ri=np.array([net["lookup"][b] for b in keep]);ii=np.array([j for j,b in enumerate(net["ids"]) if b not in set(keep)])
            L=np.zeros((191,148));L[ri]=np.eye(148);d=np.zeros(191)
            L[ii]=-np.linalg.solve(net["B"][np.ix_(ii,ii)],net["B"][np.ix_(ii,ri)])
            d[ii]=-np.linalg.solve(net["B"][np.ix_(ii,ii)],net["p"][ii])
            require(np.all(fc["bus"][ii,2:6]==0) and not np.isin(fc["gen"][:,0],net["ids"][ii]).any(),"Eliminated interior injection contract broken")
            require(not np.isin(fc["dcline"][:,:2],net["ids"][ii]).any(),"Eliminated DC terminal")
            Bred=net["B"][np.ix_(ri,ri)]+net["B"][np.ix_(ri,ii)]@L[ii]
            pred=net["p"][ri]+net["B"][np.ix_(ri,ii)]@d[ii]
            H=net["F"]@L;h=net["F"]@d+net["phase"];recovery=slim["recovery"][v]
            errors=dict(independent_angle_lift_error=maxabs(L-recovery["angle_lift"]),independent_angle_offset_error=maxabs(d-recovery["angle_offset"]),
                        independent_branch_operator_error_MW_per_rad=maxabs(H-recovery["branch_angle_matrix"]),
                        independent_branch_offset_error_model_MW=maxabs(h-recovery["branch_flow_offset"]),
                        independent_Schur_matrix_error_MW_per_rad=maxabs(Bred-small["B"]),
                        independent_Schur_phase_error_model_MW=maxabs(pred-small["p"]),
                        eliminated_KCL_operator_error_MW_per_rad=maxabs(net["C"][:,ii].T@H),
                        eliminated_KCL_offset_error_model_MW=maxabs(net["C"][:,ii].T@h))
            require(max(errors.values())<1e-8,"Independent full/slim matrix validation failed")
            legacy_c=np.asarray(ref_slim["recovery"][v]["full_interface_branch_matrix"])
            iface_error=maxabs(legacy_c@H-recovery["interface_angle_matrix"])
            require(iface_error<1e-8,"Recovered legacy interface operator mismatch")
            identity_error=maxabs(sc["branch"]-ref_slim[v+"_case"]["branch"])
            if folder.name=="identity_reference":require(identity_error==0,"Identity overlay changed original parameters")
            # All30 Schur edges retain DC-only placeholderR/B/rating semantics.
            require(np.all(sc["branch"][244:,[2,4,5,6,7]]==0),"Derived edges acquired physical conductor fields")
            changed_rows=np.flatnonzero(np.any(fc["branch"]!=old["branch"],axis=1))
            require(set(changed_rows).issubset({lookup[F84],lookup[STATEN]}),"Unexpected actual parameter mutation")
            for key in PASS_THROUGH:require(np.array_equal(fc["branch"][lookup[key]],old["branch"][lookup[key]]),"Retained path lost bit-exactness")
            equations.append(dict(scenario_name=folder.name,variant=v,full_branch_records=410,slim_branch_records=274,retained_bus_count=148,
                                  original97source_circuits_unchanged=True,bus_gen_original4DC_unchanged=True,PS33_PS34_boundary_unchanged=True,
                                  actual_changed_full_rows=";".join(str(j+1) for j in changed_rows),retained4project_paths_bit_exact=True,
                                  legacy_interface_operator_error_MW_per_rad=iface_error,**errors))
    probes=guard_checks(frame)
    after={path:sha(ROOT/path) for path in dependencies};require(after==dependencies,"Dependency changed during independent validation")
    output.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(equations).to_csv(output/"independent_parameter_overlay_equations.csv",index=False)
    pd.DataFrame(physics).to_csv(output/"independent_F84_physics.csv",index=False)
    pd.DataFrame(probes).to_csv(output/"parameter_overlay_guard_checks.csv",index=False)
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),scenario_topology_checks=len(equations),independent_physics_scenarios=len(physics),guard_probes=len(probes),
                production_numerical_solvers_imported=False,production_parser_imported_only_for_adversarial_probes=True,
                all_4_retained_project_paths_bit_exact=True,identity_overlay_branch_parameters_exact=True,
                actual_parameter_changed_full_rows=[lookup[F84]+1,lookup[STATEN]+1],
                ground_image_scenario="30ft_minimum_clearance_sensitivity;drawingAppS_PDFpage2_note8_visually_verified_not_route_average_height",
                F84_geometry_scope="transposed_representative_structure_and_equal_insulator_drop_assumption;not_route_average_or_asbuilt_parameters",
                rating_scope="1323MVA_conductor_design_value_only;not_certified_terminal_limited_facility_rating;no_thermal_validation_here",
                cable_scope="Staten_source9p4mi_XLPE_construction_only;electrical_parameters_retained_historical_analog;no_installed_conductor_match",
                full191_R_B_saved_but_slim_schur_DC_only=True,physical_gate_promotion=False,observed_interface_flows_used=False,PF_run=False,
                maximum_errors={k:max(float(row[k]) for row in equations) for k in equations[0] if "error" in k},
                dependencies=dependencies,source_hashes_unchanged=True,
                outputs={name:sha(output/name) for name in ["independent_parameter_overlay_equations.csv","independent_F84_physics.csv","parameter_overlay_guard_checks.csv"]})
    (output/"independent_parameter_overlay_validation.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ["passed","scenario_topology_checks","independent_physics_scenarios","guard_probes","actual_parameter_changed_full_rows","maximum_errors"]},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--overlays",type=Path,default=BASE/"overlays");parser.add_argument("--output",type=Path,default=BASE/"validation")
    args=parser.parse_args();validate(args.overlays,args.output)
