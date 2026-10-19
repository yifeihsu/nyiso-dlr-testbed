"""Independent pre-promotion review; no solver or artifact mutation.

Reads frozen Ontario source and fleet evidence, writes only new review outputs.
Does not import the Ontario compiler or reconstruction implementation.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"output/nygrid_2025_western_audit/review"
DEPS={}
CHECKS=[]


def sha(p):
    with Path(p).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()


def use(p):
    path=ROOT/p;DEPS[p]=sha(path);return path


def check(name,ok,error=0):
    CHECKS.append(dict(check=name,passed=bool(ok),maximum_absolute_error=float(error)))
    if not ok:raise AssertionError(name)


def close(name,a,b,tol=1e-8):
    a,b=np.asarray(a),np.asarray(b)
    ok=a.shape==b.shape and np.array_equal(np.isfinite(a),np.isfinite(b))
    err=float(np.max(abs(a[np.isfinite(a)]-b[np.isfinite(b)]),initial=0)) if ok else np.inf
    check(name,ok and err<tol,err)


def source_review():
    folder="output/nygrid_2025_western_audit/ontario/"
    manifest=pd.read_csv(use(folder+"source_manifest.csv"))
    for r in manifest.to_dict("records"):check("source_hash_"+Path(r["path"]).name,sha(use(r["path"]))==r["sha256"])
    doe=folder+"raw/DOE2025_intertie_sign_source.pdf"
    receipt=json.loads(use(doe+".receipt.json").read_text())
    check("DOE_source_hash",sha(use(doe))==receipt["sha256"])
    use(folder+"raw/DOE2025_TableB2_sign.png")
    annual=pd.read_csv(use(folder+"raw/PUB_IntertieScheduleFlowYear_2025.csv"),header=[3,4])
    check("2025_v394_identical",sha(use(folder+"raw/PUB_IntertieScheduleFlowYear_2025_v394.csv"))==sha(use(folder+"raw/PUB_IntertieScheduleFlowYear_2025.csv")))
    check("8760_annual_rows",len(annual)==8760)
    ny=annual["NEW-YORK"]
    dates=pd.to_datetime(annual.iloc[:,0],format="%Y-%m-%d")
    he=annual.iloc[:,1].to_numpy(int)
    # Independent arithmetic UTC translation: local standard time +5 hours.
    stamps=pd.DatetimeIndex(dates+pd.to_timedelta(he+4,unit="h"),tz="UTC")
    check("hour_end_range",np.array_equal(np.unique(he),np.arange(1,25)))
    check("all_intervals_unique_consecutive",stamps.is_unique and np.all(np.diff(stamps.asi8)==3600e9))
    delivered=pd.read_csv(use(folder+"hourly_actual_exchange.csv"))
    check("delivered_UTC_exact",np.array_equal(stamps.strftime("%Y-%m-%dT%H:%M:%SZ"),delivered.timestamp_utc))
    close("raw_actual_delivered_identity",ny.Flow,delivered.actual_ontario_to_ny_mw)
    close("raw_schedule_delivered_identity",ny.Exp-ny.Imp,delivered.source_net_schedule_mw)
    check("actual_annual_values_present",np.isfinite(ny.Flow).all())
    xsl=use(folder+"raw/IntertieScheduleFlow_HTML_t1-2.xsl").read_text()
    xsd=use(folder+"raw/IntertieScheduleFlow_r2.xsd").read_text()
    check("primary_EST_HE_definition","Hour 1 represents the period from 0:00 to 1:00 (EST)" in xsl and "midnight (EST) to the following midnight (EST)" in xsl)
    check("primary_MW_and_border_scope","Net amount of active power (MW) flowing through an intertie zone" in xsd and "Collection of tie lines between Ontario and a neighbouring jurisdiction" in xsd)
    check("primary_hourly_mean_rounding","round($total div 12)" in xsl)
    flowcols=annual.columns[annual.columns.get_level_values(1)=="Flow"]
    check("14_border_zones_plus_total",len(flowcols)==15)
    all_zero=annual.loc[:,flowcols].eq(0).all(axis=1)
    schedule_nonzero=annual["Total"][["Imp","Exp"]].abs().sum(axis=1).gt(0)
    suspect=all_zero & schedule_nonzero
    check("six_suspect_all_border_zeros",int(suspect.sum())==6)
    original=pd.read_csv(use("output/nygrid_2025_inputs/load_source/interface_wide.csv"),usecols=["timestamp_utc","SCH - OH - NY"])
    check("P32_hour_identity",np.array_equal(original.timestamp_utc,delivered.timestamp_utc))
    close("P32_schedule_preserved",original["SCH - OH - NY"],delivered.original_nyiso_schedule_mw)
    control=pd.read_csv(use("output/nygrid_2025_par_controls/controls/hourly_controls.csv"))
    check("control_hour_identity",np.array_equal(control.timestamp_utc,delivered.timestamp_utc))
    prior_q=control.observed_replay_qualified.to_numpy(bool)
    q=prior_q & ~suspect.to_numpy()
    check("all_six_suspects_in_prior_cohort",int((prior_q&suspect).sum())==6)
    check("new_common_cohort8657",int(q.sum())==8657)
    check("two_NY_only_zero_values_retained",int((ny.Flow.eq(0)&~suspect).sum())==2 and q[ny.Flow.eq(0)&~suspect].all())
    quality=pd.read_csv(use(folder+"hourly_exchange_quality.csv"))
    quality_receipt=json.loads(use(folder+"source_quality_receipt.json").read_text())
    check("quality_child_UTC_identity",np.array_equal(quality.timestamp_utc,delivered.timestamp_utc))
    check("quality_child_predicate_independently_rebuilt",np.array_equal(quality.source_quality_qualified.to_numpy(bool),~suspect.to_numpy()))
    check("quality_child_hash",sha(ROOT/quality_receipt["quality_child_path"])==quality_receipt["quality_child_sha256"])
    check("quality_preserves_delivered_actual_bytes",sha(ROOT/quality_receipt["original_csv_path"])==quality_receipt["original_csv_sha256"]=="e59408bf1296bd92eb6c562395d98d629c6b9784d50767c9a94956c8400aa6b4")
    check("quality_source_only_no_internal_fit",quality_receipt["internal_interface_observations_consumed"] is False and quality_receipt["quality_predicate_fitted_to_internal_flows"] is False)
    check("quality_script_receipt_current",sha(use(quality_receipt["audit_script_path"]))==quality_receipt["audit_script_sha256"])
    check("quality_suspect_source_rows_hash",sha(use(quality_receipt["suspect_rows_csv"]))==quality_receipt["suspect_rows_sha256"])
    north=control[["ptid_25118_observed_public_mw","ptid_25119_observed_public_mw"]].sum(axis=1,min_count=2)
    check("nonzero_external_north_corroborates_suspects",north[suspect].notna().all() and north[suspect].ne(0).all())
    status=pd.DataFrame(dict(timestamp_utc=delivered.timestamp_utc,all14zones_plus_total_actual_zero=all_zero,scheduled_total_nonzero=schedule_nonzero,suspect_report_zero=suspect,prior_common_qualified=prior_q,reviewed_common_qualified=q,NY_actual_mw=ny.Flow,P32_schedule_mw=original["SCH - OH - NY"]))
    status.loc[suspect].to_csv(OUT/"suspect_report_zero_hours.csv",index=False,lineterminator="\n")
    differences={}
    for name,a,b in [("IESO_actual_minus_IESO_schedule",ny.Flow,ny.Exp-ny.Imp),("IESO_schedule_minus_P32_schedule",ny.Exp-ny.Imp,original["SCH - OH - NY"]),("IESO_actual_minus_P32_schedule",ny.Flow,original["SCH - OH - NY"])]:
        e=(a-b).to_numpy()[q]
        differences[name]=dict(hours=len(e),mean_mw=float(e.mean()),mae_mw=float(abs(e).mean()),rmse_mw=float(np.sqrt(np.mean(e**2))),minimum_mw=float(e.min()),maximum_mw=float(e.max()))
    timing={}
    for lag in [-1,0,1]:
        e=(ny.Exp-ny.Imp).shift(lag)-original["SCH - OH - NY"]
        timing[str(lag)]=float(e[q & np.isfinite(e)].abs().mean())
    # Scope of the intended algebra, without reconstructing or solving dispatch.
    d=loadmat(use("output/nygrid_2025_dispatch/dispatch/dispatch.mat"),simplify_cells=True,variable_names=["native_required_pg","gamma","gen_pg","bus_pd","base_case","timestamp_utc"])
    bounds=loadmat(use("output/nygrid_2025_dispatch/dispatch/dispatch_bounds.mat"),simplify_cells=True)
    gen=pd.read_csv(use("output/nygrid_2025_moses_audit/corrected/model_generator_register.csv"))
    allocation=pd.read_csv(use("output/nygrid_2025_inputs/model/external_generator_allocation.csv"))
    ont=allocation.loc[allocation.region=="ONTARIO"]
    check("six_Ontario_shares",len(ont)==6 and (ont.generation_share>0).all())
    close("Ontario_share_sum",[ont.generation_share.sum()],[1.])
    external=gen.loc[gen.parent_gen_row.isin(ont.generator_row)]
    check("Ontario_external_row_identity",np.array_equal(external.parent_gen_row.to_numpy(),ont.generator_row.to_numpy()) and np.array_equal(external.bus_id.to_numpy(),ont.bus_id.to_numpy()))
    delta=float(d["gamma"])*(ny.Flow.to_numpy()-original["SCH - OH - NY"].to_numpy())
    target=d["native_required_pg"]-delta
    native=gen.role.eq("native").to_numpy()
    low=bounds["gen_pmin"][:,native].sum(axis=1); high=bounds["gen_pmax"][:,native].sum(axis=1)
    feasible=(target>=low-1e-7)&(target<=high+1e-7)
    check("planned_native_sum_target_inside_frozen_box",feasible[q].all())
    original_pg=d["gen_pg"][:,external.gen_row.to_numpy(int)-1]
    planned_pg=original_pg+delta[:,None]*ont.generation_share.to_numpy()[None,:]
    close("planned_Ontario_change_conservative",planned_pg[q].sum(axis=1)-original_pg[q].sum(axis=1),delta[q])
    close("planned_native_external_delta_cancel",target[q]-d["native_required_pg"][q]+delta[q],np.zeros(q.sum()))
    return dict(status="passed_source_basis_and_independently_verified_quality_child",source_file_rows=8760,suspect_report_zero_hours=6,new_common_cohort_hours=8657,
        review_scope="Raw source semantics, independent UTC/value reconstruction, source quality and planned balance algebra; no dispatch or network solve performed.",
        semantic_conclusion="Source supports actual boundary power replacing scheduled transactions. Actual-minus-schedule discrepancy is present within the IESO file itself; not explainable by NYISO clock alignment or integer rounding.",
        sign_proof="DOE TableB.2 explicitly states positiveOntarioexport; visually inspected cachedPDFpage151. IESO primaryXSD definesExp/Imp directions and primaryXSL net schedule=Export-Import. No sign selected by internal scores.",
        actual_aggregation="Published integerMW hourly aggregate; contemporary XML probe only. Native2025 interval coverage/meter quality is not independently established.",
        source_quality_finding=dict(severity="high_for_affected_hours",confidence="high_in_pattern_suspect_cause_not_certified",rule="All14neighbor actualflows andTotalFlow equal0 while scheduledtotalimports or exports nonzero",raw_values_preserved=True,do_not_assert_primary_missing_sentinel=True,NY_only_zero_hours_retained=True),
        differences_on_reviewed_cohort=differences,external_schedule_lag_MAE_mw=timing,clock_selected_from_documentation_not_fit=True,
        native_box_feasible_hours=int(feasible[q].sum()),minimum_native_lower_margin_mw=float(np.min(target[q]-low[q])),minimum_native_upper_margin_mw=float(np.min(high[q]-target[q])),
        Ontario_model_generator_rows=external.gen_row.tolist(),Ontario_source_generator_rows=ont.generator_row.tolist(),Ontario_fixed_shares=ont.generation_share.tolist(),
        promotion_conditions=["Apply independently reconstructed6hour suspect mask consistently to baseline,mapping-only,actual-only,combined comparisons", "Source-gate hashes must include annualfile, archivedv394, deliveredactualinput, newqualitychild, XSL/XSD andDOEpdf", "Rerun bounded projection from unchangedp0,weights,nativebounds on revisednativeglobaltarget; do not merely add all imbalance to a slack", "Otherexternalregions,loads,fourDCschedules,P34northcontrols,topology,andinterfaceoperators remainunchanged", "Validate bounds,KKT,nodalbalance,slackchange andregionexports afteractual replay"],
        limitations=["OntarioWest is actualtotal minus independently observedNorth; individualNiagara lineflows remainundetermined by this aggregate", "IESO andNYISO meter terminals andhourlyaggregation can differ; noexactlosslessphysicalNorth/Westmeteridentityclaim", "All-other-regions remaintheir existing schedulebasis", "Finite publishedhour is not a nativeintervalmeter-quality certificate"])


def fleet_review():
    folder="output/nygrid_2025_western_audit/corrected/"
    oldf=pd.read_csv(use("output/nygrid_2025_moses_audit/corrected/fleet/fleet_register.csv"),dtype=str,keep_default_na=False)
    newf=pd.read_csv(use(folder+"fleet_register.csv"),dtype=str,keep_default_na=False)
    oldg=pd.read_csv(use("output/nygrid_2025_moses_audit/corrected/model_generator_register.csv"),dtype=str,keep_default_na=False)
    newg=pd.read_csv(use(folder+"model_generator_register.csv"),dtype=str,keep_default_na=False)
    check("fleet_column_order_preserved",list(oldf)==list(newf))
    check("model_column_order_preserved",list(oldg)==list(newg))
    check("fleet_identity_order_preserved",oldf[["fleet_id","device_key"]].equals(newf[["fleet_id","device_key"]]))
    check("model_identity_order_preserved",oldg[["gen_row","fleet_id","device_key"]].equals(newg[["gen_row","fleet_id","device_key"]]))
    allowed={"zone","zone_mapping_policy","bus_id","parent_bus_name","parent_bus_zone","mapping_method","bus_landing_proxy","mapping_distance_km","source_zone_parent_bus_zone_conflict"}
    model_allowed={"zone","bus_id","mapping_method"}
    protected=[c for c in oldf if c not in allowed]
    check("all_nonmapping_fleet_cells_unchanged",oldf[protected].equals(newf[protected]))
    check("all_nonmapping_generator_cells_unchanged",oldg[[c for c in oldg if c not in model_allowed]].equals(newg[[c for c in newg if c not in model_allowed]]))
    diff=oldf.ne(newf); gd=oldg.ne(newg)
    proposals=pd.read_csv(use("output/nygrid_2025_western_audit/mapping/source_confirmed_unit_zone_proposals.csv"),dtype=str,keep_default_na=False)
    lew=pd.read_csv(use("output/nygrid_2025_western_audit/generation/Lewiston_candidate_landing_correction.csv"),dtype=str,keep_default_na=False)
    expected=set(proposals.loc[proposals.zone_changes=="True","fleet_id"])|set(lew.fleet_id)
    actual=set(oldf.loc[diff.any(axis=1),"fleet_id"])
    check("exact_40_reviewed_changed_units",expected==actual and len(actual)==40)
    byid=newf.set_index("fleet_id")
    oldbyid=oldf.set_index("fleet_id")
    for r in proposals.to_dict("records"):
        n=byid.loc[r["fleet_id"]]
        check("site_destination_"+r["fleet_id"],n.zone==r["proposed_zone"] and n.bus_id==r["proposed_bus_id"])
        if n.bus_id != oldbyid.loc[r["fleet_id"],"bus_id"]:
            o=oldbyid.loc[r["fleet_id"]]
            check("site_move_no_legacy_anchor_"+r["fleet_id"],o.legacy_source_gen_rows==o.legacy_candidate_bus_ids=="" and o.mapping_method=="same_zone_nearest_parent_bus_geographic_proxy")
    for r in lew.to_dict("records"):
        n,o=byid.loc[r["fleet_id"]],oldbyid.loc[r["fleet_id"]]
        check("Lewiston_destination_"+r["fleet_id"],o.plant_id==n.plant_id=="2692" and o.zone==n.zone=="A" and o.bus_id=="57" and n.bus_id=="55")
        check("Lewiston_no_legacy_terminal_override_"+r["fleet_id"],o.legacy_source_gen_rows==o.legacy_candidate_bus_ids=="" and n.bus_landing_proxy=="1")
    bat=oldf.plant_id.eq("54593")
    controls=bat & oldf.eia_generator_id.isin(["GEN1","GEN2"])
    check("Batavia_two_legacy_controls_unchanged",oldf.loc[controls].equals(newf.loc[controls]))
    gen3=bat & oldf.eia_generator_id.eq("GEN3")
    check("Batavia_GEN3_landing_method_preserved",oldf.loc[gen3,["bus_id","mapping_method","mapping_distance_km"]].equals(newf.loc[gen3,["bus_id","mapping_method","mapping_distance_km"]]))
    moses=pd.read_csv(use("output/nygrid_2025_moses_audit/corrected/fleet/plant_zone_corrections.csv"),dtype=str)
    ids=set(moses.plant_id)
    keep=oldf.plant_id.isin(ids)
    check("prior_26_hydro_corrections_preserved",len(ids)==26 and oldf.loc[keep].equals(newf.loc[keep]) and newf.loc[keep,"zone"].eq("E").all())
    native=newg.role.eq("native")
    linked=byid.loc[newg.loc[native,"fleet_id"],["bus_id","zone","mapping_method"]].reset_index(drop=True)
    check("all_model_mapping_matches_corrected_fleet",linked.equals(newg.loc[native,["bus_id","zone","mapping_method"]].reset_index(drop=True)))
    check("all_external_register_rows_unchanged",oldg.loc[~native].equals(newg.loc[~native]))
    check("213_fleet_cells_71_model_cells",int(diff.sum().sum())==213 and int(gd.sum().sum())==71)
    check("39_fleet35_model_terminal_moves",int(oldf.bus_id.ne(newf.bus_id).sum())==39 and int(oldg.bus_id.ne(newg.bus_id).sum())==35)
    declared=pd.read_csv(use(folder+"changed_fleet_fields.csv"),dtype=str,keep_default_na=False)
    pairs={(oldf.iloc[i].fleet_id,oldf.columns[j],oldf.iloc[i,j],newf.iloc[i,j])for i,j in zip(*np.nonzero(diff.to_numpy()))}
    recorded={(r["fleet_id"],r["field"],r["old_value"],r["new_value"])for r in declared.to_dict("records")}
    check("changed_field_ledger_exact",pairs==recorded and len(declared)==len(pairs))
    contract=json.loads(use(folder+"numeric_reuse_contract.json").read_text())
    check("mapping_repair_declares_no_numeric_changes",not contract["PG_rebalanced_by_mapping_repair"] and not contract["numeric_artifacts_modified"] and not contract["numeric_artifacts_copied"])
    for name,r in contract["artifacts"].items():check("numeric_reuse_hash_"+name,sha(use(r["path"]))==r["sha256"])
    receipt=json.loads(use(folder+"repair_receipt.json").read_text())
    check("corrected_fleet_output_hash",sha(ROOT/folder/"fleet_register.csv")==receipt["fleet_register_sha256"])
    check("corrected_model_output_hash",sha(ROOT/folder/"model_generator_register.csv")==receipt["model_generator_register_sha256"])
    manifest=pd.read_csv(use(folder+"source_manifest.csv"))
    for r in manifest.to_dict("records"):check("repair_dependency_hash_"+Path(r["path"]).name,sha(use(r["path"]))==r["sha256"])
    return dict(status="passed_independent_mapping_only_scope_review",inventory_rows=len(newf),model_generator_rows=len(newg),changed_inventory_rows=len(actual),fleet_zone_changes=int(oldf.zone.ne(newf.zone).sum()),fleet_terminal_moves=39,model_terminal_moves=35,fleet_field_cells=213,model_field_cells=71,
        all_unit_identity_capacity_admission_prior_bounds_dispatch_unchanged=True,prior_26_Moses_hydro_corrections_preserved=True,Batavia_legacy_anchors_preserved=True,no_generator_units_added_or_removed=True,
        source_interpretation="2018NYISO diagram groups all12Lewiston machines atNiagara230; originalbuilder anchorsNiagara toNPCCbus55. This justifies declaredproject/voltageproxy awayfromHuntley115, not exact2025physicalunit-terminalidentity. GoldBook8sitezones correct countyderivedcoarseplacements; none claims exactsubstationconnection.",
        no_numerical_replay_performed=True,limitations=["Niagara main-generator6/4/3 split and hourlycontrols remainunresolved; no newunitdispatchassumption introduced", "Lewiston withinA move should not change closedzone-cut exports when injections/externalboundary conditions arefixed; verify in mapping-only replay", "Existingpump-dispatch/admissionlimits unchanged; sourcezone/capacitydifferences do not silently altercapability"])


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    result=source_review()
    fleet=fleet_review()
    use(str(Path(__file__).relative_to(ROOT).as_posix()))
    check("all_review_dependencies_unchanged",all(sha(ROOT/p)==h for p,h in DEPS.items()))
    result.update(completed_utc=datetime.now(timezone.utc).isoformat(),checks=CHECKS,failed_checks=0,dependencies=[dict(path=p,sha256=h)for p,h in DEPS.items()],all_dependencies_unchanged=True)
    (OUT/"source_pre_promotion_review.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    combined=dict(status="passed_source_quality_and_mapping_pre_promotion_review",source_review=result,fleet_review=fleet)
    (OUT/"pre_promotion_review.json").write_text(json.dumps(combined,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k]for k in ["status","suspect_report_zero_hours","new_common_cohort_hours","failed_checks"]},indent=2))


if __name__=="__main__":main()
