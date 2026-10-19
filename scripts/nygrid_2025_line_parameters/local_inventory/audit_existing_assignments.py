"""Inventory existing 2019-to-2025 NYgrid project parameters without refitting.

This reads frozen electrical cases and their builders. It distinguishes model
detail added to a coarse 2019 parent from project paths activated after the
refined 2019 baseline. Engineering analog calculations are exported separately
and do not modify a case, conductor assignment, or historical result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"output/nygrid_2025_line_parameters/local_inventory"
PINS={
    "output/nygrid_2025_downstate/network/network_cases.mat":"89af6622ece7539d4056e3840ebda6059afcc830f0afbbdab749c43d90a503e4",
    "output/nygrid_2025_slim/network/network_cases.mat":"3c990e658464037ad36ab427150ba3c358624c1d0e3d795adb90aca91abdbc58",
    "output/nygrid_2025_downstate/network/branch_register.csv":"6a574d53b40eb2bf08dba851757a5d56ab6b4d89377b2a33e5d6319d5cd2a18f",
    "output/nygrid_2025_downstate/network/bus_register.csv":"bfab44648f3d2052e79a2a8db7c7e7390874f6bace1c575f6c94868206127f27",
    "output/nygrid_2025_slim/network/branch_register.csv":"547c40ce859c358ded212f1755b879ee508a2d56c1354e7d40782b11e0bfb82d",
    "scripts/nygrid_2025_downstate/build_network.py":"5b4626d91eeab7c0aa0be5e59a06db140502c8da715cbfc89295f2cc209115ec",
    "PERFORM/Auxilliary_Perform_NY/Branch_changes_2019_to_2030.xlsx":"31d519c74f75a06a77ed11fabf535e4579fbc5c94cbb7e0a6be14cec38a054b8",
    "PERFORM/On Peak 2019 v23_Perform_NY/On Peak 2019 v23/nyiso_On_Peak_v23_shunts_as_z_load.m":"36e86cea63f1dea0872d1c2ec57f09e20d5c5ce99dad20d9977a1b014b20edb5",
    "output/ny_only_package_a/source_inventory/perform_ny_branch_inventory.csv":"09898f0857ca417c99ad19516578b9b7b15adef565529fe066ae7f5df6ecd97b",
}
FILES=["output/nygrid_2025_downstate/sources/upgrade_register.csv",
       "output/nygrid_2025_downstate/sources/source_receipts.csv"]
VARIANTS=["refined_2019","refined_2025_pre_may","refined_2025_may21","refined_2025_may30","refined_2025"]
ASSETS={
    "CV:PV_CV_F84":"CV:F84",
    "DOVER:CV_DOVER_Y17":"DOVER:Y17",
    "DOVER:DOVER_LM_398":"DOVER:398",
    "RCC:CABLE:QUEENS":"RCC_Rainey_Corona:FEEDER",
    "RCC:CABLE:BROOKLYN":"RCC_Gowanus_Greenwood:FEEDER",
    "RCC:CABLE:STATEN":"RCC_Goethals_FoxHills:FEEDER",
}
LENGTHS={"RCC:CABLE:QUEENS":6.,"RCC:CABLE:BROOKLYN":1.,"RCC:CABLE:STATEN":9.2}
FIELDS=["from_bus","to_bus","r_pu","x_pu","b_pu","rate_a_mva","rate_b_mva","rate_c_mva","tap","shift_degree","status","angle_min_degree","angle_max_degree"]


def require(condition,text):
    if not bool(condition):raise ValueError(text)


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def maxabs(value):return float(np.max(np.abs(value),initial=0.))


def source_branch_matrix(path):
    text=Path(path).read_text(encoding="utf-8")
    base=float(re.search(r"mpc\.baseMVA\s*=\s*([\d.]+)",text).group(1))
    raw=re.search(r"mpc\.branch\s*=\s*\[(.*?)\];",text,re.S).group(1)
    lines=[line.split("%")[0].strip().rstrip(";") for line in raw.splitlines()]
    return base,np.array([list(map(float,line.split())) for line in lines if line])


def build(output=OUT):
    output=Path(output)
    require(not (output/"existing_assignment_receipt.json").exists(),"Choose fresh output directory")
    before={p:sha(ROOT/p) for p in PINS}
    require(before==PINS,"Frozen source/model changed")
    before.update({p:sha(ROOT/p) for p in FILES})
    full=loadmat(ROOT/"output/nygrid_2025_downstate/network/network_cases.mat",simplify_cells=True)
    slim=loadmat(ROOT/"output/nygrid_2025_slim/network/network_cases.mat",simplify_cells=True)
    reg=pd.read_csv(ROOT/"output/nygrid_2025_downstate/network/branch_register.csv",keep_default_na=False)
    bus=pd.read_csv(ROOT/"output/nygrid_2025_downstate/network/bus_register.csv",keep_default_na=False).set_index("model_bus")
    sreg=pd.read_csv(ROOT/"output/nygrid_2025_slim/network/branch_register.csv",keep_default_na=False)
    assets=pd.read_csv(ROOT/FILES[0],keep_default_na=False).set_index("asset_key")
    source_identity=pd.read_csv(ROOT/"output/ny_only_package_a/source_inventory/perform_ny_branch_inventory.csv",keep_default_na=False).set_index("source_branch_row")
    source_path=next(p for p in PINS if p.endswith("shunts_as_z_load.m"))
    source_base,raw_source=source_branch_matrix(ROOT/source_path)
    base=float(full["refined_2025_case"]["baseMVA"])
    require(base==source_base==float(full["parent_case"]["baseMVA"])==100.,"MVA base changed")
    old=np.asarray(full["refined_2019_case"]["branch"],float)[:,:13]
    new=np.asarray(full["refined_2025_case"]["branch"],float)[:,:13]
    require(old.shape==new.shape==(410,13),"Frozen branch axes changed")
    changed=np.flatnonzero(np.any(old!=new,axis=1))
    activated=np.flatnonzero((old[:,10]==0)&(new[:,10]==1))
    retired=np.flatnonzero((old[:,10]==1)&(new[:,10]==0))
    parameter_columns=[i for i in range(13) if i!=10]
    require(maxabs(new[:,parameter_columns]-old[:,parameter_columns])==0,"Unexpected parameter reassignment beyond status")
    require(len(changed)==8 and len(activated)==6 and len(retired)==2,"Project delta count changed")
    require(set(reg.iloc[activated].branch_key)==set(ASSETS),"Activated project identity changed")
    delta=[]
    for j in changed:
        row=reg.iloc[j].to_dict()
        row.update(change="activated_project_path" if j in activated else "retired_proxy_or_scaffold",parameter_values_reassigned=False,
                   old_status=int(old[j,10]),new_status=int(new[j,10]),changed_fields="status",
                   from_name=bus.loc[int(new[j,0]),"model_name"],to_name=bus.loc[int(new[j,1]),"model_name"],
                   from_base_kv=bus.loc[int(new[j,0]),"base_kv"],to_base_kv=bus.loc[int(new[j,1]),"base_kv"],base_mva=base)
        delta.append(row)
    parent32=full["parent_case"]["branch"][31,:13]
    template=raw_source[1268,:13]
    require(np.array_equal(parent32[:2],[35,73]) and np.array_equal(template[:2],[1493,601]),"Template endpoint changed")
    require(maxabs(template-full["source_case"]["branch"][1268,:13])==0,"Saved source template differs from original MATPOWER text")
    require(np.array_equal(template[2:8],[.0008,.00401,.03037,562,562,562]),"RCC source template changed")
    workbook=openpyxl.load_workbook(ROOT/"PERFORM/Auxilliary_Perform_NY/Branch_changes_2019_to_2030.xlsx",read_only=True,data_only=True)
    template_rows=[]
    named_project_hits=[]
    for sheet in workbook:
        rows=list(sheet.values);hi=next(j for j,row in enumerate(rows) if row[0]=="ID");headers=rows[hi]
        for excelrow,values in enumerate(rows[hi+1:],hi+2):
            if values[0] is None:continue
            data=dict(zip(headers,values))
            if str(data["ID"]) in ["1493_601_"+str(k) for k in range(1,5)]:
                template_rows.append(dict(source_sheet=sheet.title,source_excel_row=excelrow,**{str(k):v for k,v in data.items() if k is not None}))
            label=(str(data["From Name"])+" "+str(data["To Name"])).upper()
            if any(s in label for s in ["CRICKET","DOVER","LONG MOUNTAIN"]):
                named_project_hits.append(dict(source_sheet=sheet.title,source_excel_row=excelrow,**{str(k):v for k,v in data.items() if k is not None}))
    workbook.close()
    wr=pd.DataFrame(template_rows)
    first=wr[(wr.source_sheet=="2019 On Peak")&(wr.ID=="1493_601_1")].iloc[0]
    template_length=float(first["Length, Estimated from X and B (Miles)"])
    station_distance=float(first["Distance Between Substations (Miles)"])
    require(template_length==5.5 and station_distance==3.7,"Historical length metadata changed")
    require(maxabs(np.array([first[k] for k in ["R","X","B","Lim MVA A","Lim MVA B","Lim MVA C"]])-template[2:8])==0,"Workbook/source template mismatch")
    support=reg[reg.branch_key.str.startswith("RCC:PAR:")]
    assigned=[]
    for j in list(activated)+support.index.to_list():
        r=reg.iloc[j];br=new[j]
        a,b=map(int,br[:2]);kv_a,kv_b=float(bus.loc[a,"base_kv"]),float(bus.loc[b,"base_kv"])
        asset=assets.loc[ASSETS[r.branch_key]] if r.branch_key in ASSETS else None
        if r.branch_key in LENGTHS:
            expected=template[2:4]*LENGTHS[r.branch_key]/template_length
            require(maxabs(br[2:4]-expected)<1e-15,"RCC template reconstruction failed")
            length_used=LENGTHS[r.branch_key];factor=length_used/template_length
            provenance="historical_R_X_per_inferred_electrical_mile_times_assumed_project_route_length"
            source_reference="PERFORM2019 branch1269 and workbook2019 row956 ID1493_601_1"
            physical_kind="underground_cable_project_with_unverified_historical_circuit_analog"
        elif r.branch_key=="CV:PV_CV_F84":
            factor=.4;expected=parent32[2:4]*factor
            require(maxabs(br[2:4]-expected)<1e-15,"F84 parent budget reconstruction failed")
            length_used="";provenance="40_percent_of_old_Southington_PleasantValley_aggregate_R_X_equal_F83_proxy"
            source_reference="frozen modified2019 parent branch32; historical 345kV aggregate not physical F84 parameters"
            physical_kind="overhead_line_project_with_aggregate_impedance_proxy"
        elif r.branch_key.startswith("DOVER:"):
            factor=.2;expected=parent32[2:4]*factor
            require(maxabs(br[2:4]-expected)<1e-15,"Dover parent budget reconstruction failed")
            length_used="";provenance="half_of_existing_CV_LongMountain_proxy_R_X_with_nominal_zero_phase_PAR"
            source_reference="frozen modified2019 parent branch32 and replaced CV:CV_LM_398_PROXY"
            physical_kind="line_resection_and_control_project_with_series_budget_proxy"
        else:
            factor="";length_used="";provenance="fixed_nominal_transformer_PAR_assumption"
            source_reference="build_network.py explicit R=.002 X=.03 tap=1 shift=0"
            physical_kind="voltage_changing_equipment_proxy_conductor_matching_not_applicable"
            require(np.array_equal(br[2:5],[.002,.03,0]) and br[8]==1 and br[9]==0,"Supporting PAR proxy changed")
        record=dict(model_family="NYgrid_full191_recovered_by_slim148",model_branch_row=j+1,branch_key=r.branch_key,
                    scope="activated_since_refined2019" if j in activated else "supporting_RCC_equipment_present_both_states",
                    asset_key=ASSETS.get(r.branch_key,""),circuit_id=asset.circuit_id if asset is not None else "",
                    from_bus=a,to_bus=b,from_name=bus.loc[a,"model_name"],to_name=bus.loc[b,"model_name"],
                    from_base_kv=kv_a,to_base_kv=kv_b,base_mva=base,
                    **{k:float(br[i]) for i,k in enumerate(FIELDS) if i>=2},
                    status_refined2019=int(old[j,10]),status_refined2025=int(new[j,10]),
                    existing_parameter_provenance=provenance,parameter_source_reference=source_reference,physical_kind=physical_kind,
                    source_public_route_length_miles=asset.route_length_miles if asset is not None else "",
                    route_length_used_for_existing_R_X_miles=length_used,parameter_scale_factor=factor,
                    source_template_length_miles=template_length if r.branch_key in LENGTHS else "",
                    source_template_length_basis="estimated_from_X_and_B_not_surveyed_route" if r.branch_key in LENGTHS else "not_length_based",
                    reference_resistance_temperature_c="",conductor_type="unassigned",bundle_count="",installed_conductor_verified=False,
                    current_B_policy="omitted_DC_placeholder_not_physical_zero_capacitance",current_rating_policy="zero_unrated_placeholder_not_zero_rating_or_infinite_certification",
                    source_ids=asset.source_ids if asset is not None else "",physical_parameter_ground_truth_verified=False,
                    new_parameter_estimation_performed=False,interface_observations_used=False)
        # Conversion is a unit audit only. An aggregate proxy's ohms are not
        # independently established physical line or conductor measurements.
        zb=kv_a**2/base
        record.update(reference_side_zbase_ohm=zb,model_r_ohm_on_from_voltage_base=float(br[2]*zb),
                      model_x_ohm_on_from_voltage_base=float(br[3]*zb),model_b_siemens_on_from_voltage_base=float(br[4]/zb),
                      physical_per_line_ohms_established=False)
        assigned.append(record)
    assignments=pd.DataFrame(assigned)
    require(np.all(assignments.loc[assignments.scope=="activated_since_refined2019",["b_pu","rate_a_mva","rate_b_mva","rate_c_mva"]].to_numpy(float)==0),"Expected DC placeholder semantics changed")
    sl_old=slim["refined_2019_case"]["branch"][:,:13];sl_new=slim["refined_2025_case"]["branch"][:,:13]
    slim_ix=np.flatnonzero(np.any(sl_old!=sl_new,axis=1));slim_delta=sreg.iloc[slim_ix].copy()
    slim_delta["changed_fields"]=[";".join(FIELDS[k] for k in np.flatnonzero(sl_old[j]!=sl_new[j])) for j in slim_ix]
    slim_delta["physical_new_line_countable"]=False
    slim_delta["role_note"]=np.where(slim_delta.role=="passive_DC_Schur_equivalent","derived_equivalent_response_change_not_new_physical_line","direct_retained_project_assumption_F84")
    require(len(slim_delta)==29 and sum(slim_delta.role=="passive_DC_Schur_equivalent")==28,"Slim delta changed")
    old_cv=reg.set_index("branch_key").loc["CV:CV_LM_398_PROXY",["r_pu","x_pu"]].to_numpy(float)
    dover=assignments[assignments.branch_key.str.startswith("DOVER:")][["r_pu","x_pu"]].sum().to_numpy(float)
    require(maxabs(old_cv-dover)<1e-15,"Dover resection no longer preserves nominal aggregate series budget")
    dover_schur=maxabs(slim["recovery"]["refined_2025"]["Schur_B"]-slim["recovery"]["refined_2025_may30"]["Schur_B"])
    require(dover_schur==0,"Dover zero-injection nominal split changes retained DC response")
    counts=[]
    for variant in VARIANTS:
        br=full[variant+"_case"]["branch"]
        for role,part in reg.groupby("electrical_role"):
            ix=part.index.to_numpy(int)
            counts.append(dict(variant=variant,electrical_role=role,records=len(ix),active_records=int(br[ix,10].sum()),
                               new_physical_2025_identity_implied=False))
    added=reg.iloc[225:].copy()
    added["representation_addition_vs_140_parent"]=True
    added["post2019_project_activation"]=added.index.isin(activated)
    added["historical_2019_detail_not_new_2025_build"]=added.electrical_role=="exact_historical_source_circuit"
    added["verified_installed_conductor"]=False
    template_audit=dict(source_branch_row=1269,source_branch_raw_identity=source_identity.loc[1269].to_dict(),
                        source_base_mva=source_base,source_terminal_kv=138,workbook_base_mva_explicit=False,
                        workbook_base_support="R_X_B_and_ratings_match_original100MVA_MATPOWER_row_exactly",
                        source_R_pu=float(template[2]),source_X_pu=float(template[3]),source_B_pu=float(template[4]),
                        source_rating_A_B_C_MVA=template[5:8].tolist(),electrical_length_miles=template_length,station_distance_miles=station_distance,
                        length_is_inferred_from_X_and_B=True,surveyed_route_length_available=False,
                        physical_underground_cable_classifier_available=False,installed_conductor_available=False,resistance_reference_temperature_available=False,
                        original_builder_calls_cable=True,source_inventory_device_class=source_identity.loc[1269,"source_device_role"],
                        source_B_semantics="MATPOWER_total_branch_charging_susceptance_B_not_per_end_B_half",frequency_hz=60,
                        frequency_basis="North_American_nominal_frequency_only_used_for_optional_B_to_C_conversion",
                        current_RCC_B_zero_is_DC_omission=True,assigned_current_RCC_B_is_not_AC_line_parameter_validation=True,
                        original_template_has_parallel_identity_ambiguity=not bool(source_identity.loc[1269,"individual_circuit_identity_resolved"]),
                        source_vintage="2019_study_exported2022_not_new_RCC_asbuilt")
    # Two transparent normalization scenarios, not a statistical interval.
    # The shorter station distance is not claimed to be the physical cable route.
    analog=[]
    for key,length in LENGTHS.items():
        for denominator,label in [(template_length,"historical_electrical_length5p5mi"),(station_distance,"station_distance3p7mi_sensitivity_only")]:
            br=template[2:5]*length/denominator;zb=138.**2/base
            analog.append(dict(branch_key=key,scenario=label,target_length_miles=length,target_length_basis="existing_model_length_reproduced_not_newest_owner_measurement",
                               historical_template_row=1269,source_base_mva=100,target_base_mva=100,target_kv=138,
                               normalization_length_miles=denominator,r_pu=float(br[0]),x_pu=float(br[1]),b_pu=float(br[2]),
                               r_ohm=float(br[0]*zb),x_ohm=float(br[1]*zb),b_siemens=float(br[2]/zb),
                               total_capacitance_microfarad_at60Hz=float(br[2]/zb/(2*np.pi*60)*1e6),
                               installed_conductor="unknown_not_ACSR_default",physical_parameter_verified=False,
                               proposed_only_current_model_unchanged=True,uncertainty_interval=False,
                               limitation="historical_circuit_analog_unknown_construction_geometry_resistance_temperature_and_route;do_not_reuse562MVA_as_new_equipment_rating"))
    output.mkdir(parents=True,exist_ok=True)
    for name,df in [("full191_2019_to_2025_delta",pd.DataFrame(delta)),("existing_project_parameter_assignments",assignments),
                    ("slim148_derived_parameter_delta",slim_delta),("representation_role_counts",pd.DataFrame(counts)),
                    ("all_representation_additions",added),("RCC_historical_workbook_template_rows",wr),
                    ("RCC_template_analog_scenarios_not_installed_parameters",pd.DataFrame(analog))]:
        df.to_csv(output/(name+".csv"),index=False)
    (output/"RCC_template_source_audit.json").write_text(json.dumps(template_audit,indent=2,default=lambda x:x.item() if hasattr(x,"item") else str(x))+"\n")
    after={p:sha(ROOT/p) for p in before};require(before==after,"Protected source changed during inventory")
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),scope="actual_current_NYgrid_2019_to_2025_project_delta_and_existing_parameter_provenance",
                full191_records=410,original_parent_records=225,representation_addition_records=185,yearend_active_added_records=int(new[225:,10].sum()),
                active_exact_historical_detail_rows=int(((reg.electrical_role=="exact_historical_source_circuit")&(new[:,10]==1)).sum()),
                full191_changed_rows=len(changed),activated_project_paths=len(activated),retired_proxy_or_scaffold_rows=len(retired),
                any_existing_R_X_B_tap_rating_reassigned=False,slim_changed_records=len(slim_delta),slim_changed_derived_equivalent_records=28,
                existing_project_parameters_already_assigned=True,installed_conductor_assignments_verified=0,
                Dover_series_R_X_reconstruction_error=maxabs(old_cv-dover),Dover_nominal_zero_injection_Schur_change_MW_per_radian=dover_schur,
                RCC_template_original_source_workbook_equality_passed=True,RCC_template_electrical_length_miles=template_length,RCC_template_station_distance_miles=station_distance,
                workbook_named_Cricket_Dover_LongMountain_rows_found=len(named_project_hits),
                engineering_analog_scenarios_only=True,new_model_parameters_applied=False,annual_PF_run=False,interface_observations_used=False,
                dependencies=before,script_sha256=sha(__file__),source_hashes_unchanged=True,
                other_model_families="Older compact_NY_CEEC_SPC_parameter_assignments_exist_but_are_not_in_the_current_NYgrid148_project_delta;do_not_reuse_their_row_numbers_or_installed_conductor_claims",
                interpretation="2019refined_and2025cases_share_preassigned_branch_records;2025projectchanges_activate6andretire2. Added historical detail and Schur equivalents are not physical lines built after2019.")
    report["outputs"]={p.name:sha(p) for p in output.iterdir() if p.is_file()}
    (output/"existing_assignment_receipt.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ["passed","representation_addition_records","yearend_active_added_records","active_exact_historical_detail_rows","full191_changed_rows","activated_project_paths","retired_proxy_or_scaffold_rows","any_existing_R_X_B_tap_rating_reassigned","slim_changed_records","slim_changed_derived_equivalent_records"]},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,default=OUT)
    build(parser.parse_args().output)
