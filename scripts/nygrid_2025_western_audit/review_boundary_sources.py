"""Independent read-only review of four EIA-930 boundary sources.

Uses the Python CSV reader for published gzip payloads; does not import the
compiler. No internal interface measurement, dispatch, or solver is read.
"""
from datetime import datetime, timedelta, timezone
import csv
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"output/nygrid_2025_western_audit/boundary_actuals"
OUT=ROOT/"output/nygrid_2025_western_audit/boundary_source_review"
DEPS={};CHECKS=[]
REGIONS={"ISONE":"ISNE","ONTARIO":"IESO","PJM":"PJM","HQ":"HQT"}
CHANNELS={"ISONE":["SCH - NE - NY","SCH - NPX_1385","SCH - NPX_CSC"],
 "ONTARIO":["SCH - OH - NY"],"PJM":["SCH - PJ - NY","SCH - PJM_HTP","SCH - PJM_NEPTUNE","SCH - PJM_VFT"],
 "HQ":["SCH - HQ - NY","SCH - HQ_CEDARS"]}


def sha(path):
    with Path(path).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()


def use(path):
    path=Path(path);path=path if path.is_absolute()else ROOT/path
    DEPS[path.relative_to(ROOT).as_posix()]=sha(path)
    return path


def check(name,passed,error=0.):
    CHECKS.append(dict(check=name,passed=bool(passed),maximum_absolute_error=float(error)))
    if not passed:raise AssertionError(name)


def close(name,a,b,tolerance=1e-8):
    a,b=np.asarray(a,float),np.asarray(b,float)
    ok=a.shape==b.shape and np.array_equal(np.isfinite(a),np.isfinite(b))
    error=float(np.max(abs(a[np.isfinite(a)]-b[np.isfinite(b)]),initial=0))if ok else np.inf
    check(name,ok and error<tolerance,error)


def boolean(s):
    x=pd.Series(s).astype(str).str.lower()
    check("known_boolean_values",x.isin(["true","false","1","0"]).all())
    return x.isin(["true","1"]).to_numpy()


def number(value):return float(value)if value.strip()else np.nan


def timestamp(value):
    end=datetime.strptime(value,"%m/%d/%Y %I:%M:%S %p").replace(tzinfo=timezone.utc)
    return (end-timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def stats(x):
    v=np.asarray(x,float);v=v[np.isfinite(v)]
    return dict(hours=len(v),mean_mw=float(v.mean()),mae_mw=float(abs(v).mean()),rmse_mw=float(np.sqrt(np.mean(v*v))),maximum_absolute_mw=float(abs(v).max()))if len(v)else dict(hours=0)


def read_primary():
    bilaterals=[];totals=[];counterparts=[]
    for half in ["Jan_Jun","Jul_Dec"]:
        for kind in ["INTERCHANGE","BALANCE"]:
            name=f"EIA930_{kind}_2025_{half}.csv.gz"
            path=use(SOURCE/"raw"/name)
            receipt=json.loads(use(Path(str(path)+".receipt.json")).read_text())
            check(name+"_compressed_hash",sha(path)==receipt["sha256"])
            check(name+"_official_published_url",receipt["url"]=="https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/"+name.removesuffix(".gz"))
            digest=hashlib.sha256();count=0
            with gzip.open(path,"rb")as f:
                for chunk in iter(lambda:f.read(1024*1024),b""):
                    digest.update(chunk);count+=len(chunk)
            check(name+"_decoded_hash_bytes",digest.hexdigest()==receipt["original_csv_sha256"]and count==receipt["original_csv_bytes"])
            with gzip.open(path,"rt",encoding="utf-8-sig",newline="")as stream:
                rows=csv.DictReader(stream)
                check(name+"_UTC_hour_ending_header","UTC Time at End of Hour"in rows.fieldnames)
                for row in rows:
                    ba=row["Balancing Authority"]
                    if kind=="INTERCHANGE":
                        neighbor=row["Directly Interconnected Balancing Authority"]
                        if ba=="NYIS":
                            bilaterals.append(dict(timestamp_utc=timestamp(row["UTC Time at End of Hour"]),fromba=ba,toba=neighbor,value=number(row["Interchange (MW)"])))
                        elif ba in ["ISNE","PJM"]and neighbor=="NYIS":
                            counterparts.append(dict(timestamp_utc=timestamp(row["UTC Time at End of Hour"]),reporter=ba,import_to_NY_mw=number(row["Interchange (MW)"])))
                    elif ba=="NYIS":
                        totals.append(dict(timestamp_utc=timestamp(row["UTC Time at End of Hour"]),TI_export_mw=number(row["Total Interchange (MW)"]),sum_valid_DIBA_export_mw=number(row["Sum(Valid DIBAs) (MW)"]),demand_mw=number(row["Demand (MW)"]),net_generation_mw=number(row["Net Generation (MW)"])))
    return pd.DataFrame(bilaterals),pd.DataFrame(totals),pd.DataFrame(counterparts)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    audit=json.loads(use(SOURCE/"source_audit_receipt.json").read_text())
    check("compiler_status",audit["status"]=="complete_source_audit_with_categorical_quality_screen")
    check("source_only_scope",audit["internal_interface_observations_consumed"]is False and audit["source_sign_or_clock_fitted"]is False)
    check("compiler_hash",sha(use(ROOT/audit["audit_script_path"]))==audit["audit_script_sha256"])
    check("delivered_actual_hash",sha(use(ROOT/audit["actual_input_path"]))==audit["actual_input_sha256"])
    manifest=use(SOURCE/"source_manifest.csv")
    for record in audit["source_receipts"]:
        path=use(SOURCE/"raw"/record["file"])
        side=use(Path(str(path)+".receipt.json"))
        local=json.loads(side.read_text())
        check("source_receipt_"+record["file"],local["sha256"]==record["sha256"]==sha(path)and local["url"]==record["url"])
    for record in audit["original_source_hashes"]:
        check("preserved_"+Path(record["path"]).name,sha(use(ROOT/record["path"]))==record["sha256"])
    index=use(SOURCE/"raw/EIA930_File_List_Meta.csv").read_text()
    for half in ["Jan_Jun","Jul_Dec"]:
        for kind in ["INTERCHANGE","BALANCE"]:check("published_index_"+kind+half,f"EIA930_{kind}_2025_{half}.csv"in index)
    doc=use(SOURCE/"raw/EIA930_instructions.pdf")
    check("primary_document_independent_copy_match",sha(doc)==sha(use(OUT/"EIA930_instructions.pdf")))
    metadata=json.loads(use(SOURCE/"raw/interchange_route_metadata.json").read_text())["response"]
    check("API_hourly_MWh_unitproof",metadata["data"]["value"]["units"]=="megawatthours"and any(r["id"]=="hourly"and r["alias"]=="hourly (UTC)"for r in metadata["frequency"]))
    raw,total,counterpart=read_primary()
    check("complete_four_neighbor_scope",set(raw.toba)==set(REGIONS.values())and set(raw.fromba)=={"NYIS"})
    check("35040_unique_primary_bilaterals",len(raw)==35040 and not raw.duplicated(["timestamp_utc","fromba","toba"]).any())
    check("8760_each_neighbor",raw.groupby("toba").size().eq(8760).all())
    check("8760_unique_raw_total",len(total)==8760 and total.timestamp_utc.is_unique)
    hours=pd.read_csv(use("output/nygrid_2025_inputs/load_source/hour_catalog.csv"),usecols=["hour_index","timestamp_utc"])
    grid=raw.pivot(index="timestamp_utc",columns="toba",values="value").sort_index()
    check("bulk_HE_to_UTCstart_exact",np.array_equal(grid.index.to_numpy(),hours.timestamp_utc.to_numpy()))
    values=-grid[list(REGIONS.values())].to_numpy()
    total=total.set_index("timestamp_utc").loc[hours.timestamp_utc].reset_index()
    sums=values.sum(axis=1)
    close("all8760_SumValidDIBAs_exact",sums,-total.sum_valid_DIBA_export_mw)
    api=[]
    for path in sorted((SOURCE/"raw").glob("NYIS_interchange_2025_*.json")):
        if path.name.endswith(".receipt.json"):continue
        response=json.loads(use(path).read_text())["response"]
        api.extend(response["data"])
    api=pd.DataFrame(api)
    check("25000_cached_API_records",len(api)==25000 and not api.duplicated(["period","fromba","toba"]).any())
    api["timestamp_utc"]=(pd.to_datetime(api.period,utc=True)-pd.Timedelta(hours=1)).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    joined=raw.merge(api,on=["timestamp_utc","fromba","toba"],validate="one_to_one",suffixes=("_bulk","_api"))
    check("all_cached_API_rows_join",len(joined)==25000)
    close("all_cached_API_values_equal_bulk",joined.value_bulk,pd.to_numeric(joined.value_api))
    delivered=pd.read_csv(use(SOURCE/"hourly_regional_actuals.csv"))
    cols=[r+"_actual_import_mw"for r in REGIONS]
    check("derived_hour_ids_and_axis",np.array_equal(delivered.hour_index,hours.hour_index)and np.array_equal(delivered.timestamp_utc,hours.timestamp_utc))
    close("derived_values_no_fit_scale_or_shift",delivered[cols],values)
    counterpart=counterpart.pivot(index="timestamp_utc",columns="reporter",values="import_to_NY_mw").reindex(hours.timestamp_utc)
    oldOntario=pd.read_csv(use("output/nygrid_2025_western_audit/ontario/hourly_actual_exchange.csv"))
    oldQuality=pd.read_csv(use("output/nygrid_2025_western_audit/ontario/hourly_exchange_quality.csv"))
    check("IESO_primary_companion_axis",np.array_equal(oldOntario.timestamp_utc,hours.timestamp_utc)and np.array_equal(oldQuality.timestamp_utc,hours.timestamp_utc))
    ieso=oldOntario.actual_ontario_to_ny_mw.to_numpy();ieso_q=boolean(oldQuality.source_quality_qualified)
    changes=np.r_[True,np.any(np.diff(values,axis=0)!=0,axis=1)]
    starts=np.flatnonzero(changes);ends=np.r_[starts[1:],len(values)]
    frozen=np.zeros(len(values),bool);runs=[]
    for start,end in zip(starts,ends):
        if end-start<3:continue
        ont=ieso[start:end];isne=counterpart.ISNE.to_numpy()[start:end]
        corroborated=np.isfinite(ont).all()and np.isfinite(isne).all()and ieso_q[start:end].all()and np.ptp(ont)>2 and np.ptp(isne)>2
        runs.append(dict(first_hour_index=int(start+1),last_hour_index=int(end),hours=int(end-start),first_timestamp_utc=hours.timestamp_utc.iloc[start],last_timestamp_utc=hours.timestamp_utc.iloc[end-1],IESO_range_mw=float(np.ptp(ont)),ISNE_counterpart_range_mw=float(np.ptp(isne)),independently_corroborated=bool(corroborated),**dict(zip(cols,values[start]))))
        if corroborated:frozen[start:end]=True
    check("two_corroborated_sourcewide_frozen_runs",len(runs)==2 and all(r["independently_corroborated"]for r in runs))
    check("six_frozen_hours_exact",np.array_equal(np.flatnonzero(frozen)+1,[2999,3000,3001,3007,3008,3009]))
    allzero=np.all(values==0,axis=1);TI=-total.TI_export_mw.to_numpy()
    inconsistent_zero=allzero & np.isfinite(TI)&(abs(TI)>2.5)
    expected=np.isfinite(values).all(axis=1)&~inconsistent_zero&~frozen
    check("derived_quality_matches_independent_raw_rules",np.array_equal(boolean(delivered.coverage_qualified),expected))
    for r in REGIONS:check("regional_quality_"+r,np.array_equal(boolean(delivered[r+"_source_qualified"]),expected))
    use(SOURCE/"hourly_source_quality.csv")
    p32cols=list(dict.fromkeys(c for v in CHANNELS.values()for c in v))
    p32=pd.read_csv(use("output/nygrid_2025_inputs/load_source/interface_wide.csv"),usecols=["timestamp_utc"]+p32cols)
    check("external_schedule_axis",np.array_equal(p32.timestamp_utc,hours.timestamp_utc))
    comparison=pd.read_csv(use(SOURCE/"external_schedule_actual_comparison.csv"))
    check("external_comparison_axis",np.array_equal(comparison.timestamp_utc,hours.timestamp_utc))
    close("original_external_channels_preserved",comparison[p32cols],p32[p32cols])
    schedule=np.column_stack([p32[c].sum(axis=1,min_count=len(c))for c in CHANNELS.values()])
    for j,r in enumerate(REGIONS):
        close(r+"_original_schedule_aggregate",comparison[r+"_original_schedule_import_mw"],schedule[:,j])
        close(r+"_delta",comparison[r+"_actual_minus_schedule_mw"],values[:,j]-schedule[:,j])
    dcnames=["original_DC1_NPX1385_plus_CSC_schedule_mw","original_DC2_NEPTUNE_schedule_mw","original_DC3_HTP_schedule_mw","original_DC4_VFT_schedule_mw"]
    dc=np.column_stack([p32[["SCH - NPX_1385","SCH - NPX_CSC"]].sum(axis=1,min_count=2),p32["SCH - PJM_NEPTUNE"],p32["SCH - PJM_HTP"],p32["SCH - PJM_VFT"]])
    close("four_original_DC_schedule_values_unchanged",comparison[dcnames],dc)
    p34=pd.read_csv(use("output/nygrid_2025_par_controls/controls/hourly_controls.csv"),usecols=["timestamp_utc","observed_replay_qualified"])
    check("P34_hour_axis",np.array_equal(p34.timestamp_utc,hours.timestamp_utc))
    common=expected & np.isfinite(schedule).all(axis=1)&boolean(p34.observed_replay_qualified)
    paired=common&ieso_q
    check("new_common_cohort8657",int(common.sum())==8657)
    check("Ontario_only_intersection8651",int(paired.sum())==8651)
    check("saved_common_mask",np.array_equal(boolean(comparison.common_replay_qualified),common))
    check("saved_intersection_mask",np.array_equal(boolean(comparison.common_with_ontario_only_scenario),paired))
    sumcheck=pd.read_csv(use(SOURCE/"reported_total_sum_check.csv"))
    gap=sums-TI
    close("saved_total_sumcheck",sumcheck.bilateral_sum_minus_reported_total_mw,gap)
    detail=pd.DataFrame(dict(timestamp_utc=hours.timestamp_utc,bilateral_import_sum_mw=sums,reported_total_import_mw=TI,reported_valid_DIBA_import_sum_mw=-total.sum_valid_DIBA_export_mw,bilateral_minus_total_mw=gap,bilateral_minus_source_D_minus_NG_mw=sums-total.demand_mw+total.net_generation_mw))
    detail.loc[abs(gap)>2.5].to_csv(OUT/"total_series_discrepancy_hours.csv",index=False,lineterminator="\n")
    pd.DataFrame(runs).to_csv(OUT/"independent_frozen_vector_runs.csv",index=False,lineterminator="\n")
    pair_stats={"Ontario_NYIS_minus_IESO":stats((values[:,1]-ieso)[paired]),"ISONE_NYIS_minus_ISNE":stats((values[:,0]-counterpart.ISNE.to_numpy())[common]),"PJM_NYIS_minus_PJM":stats((values[:,2]-counterpart.PJM.to_numpy())[common])}
    use(OUT/"quality_protocol.json");use(Path(__file__))
    # Include additional producer evidence in the review proof without treating
    # it as an independently measured source or importing its implementation.
    for path in SOURCE.glob("*.csv"):
        if "initial_candidate"not in path.name:use(path)
    check("all_review_dependencies_unchanged",all(sha(ROOT/p)==h for p,h in DEPS.items()))
    result=dict(status="passed_source_only_all_four_boundary_review",passed=True,created_utc=datetime.now(timezone.utc).isoformat(),year=2025,reporting_BA="NYIS",regions=REGIONS,
        source_mode="official_EIA_six_month_bulk_CSV_with_cached_API_crosscheck",internal_interface_observations_consumed=False,source_sign_or_clock_fitted=False,
        source_record_count=35040,physical_hours=8760,source_finite_hours=int(np.isfinite(values).all(axis=1).sum()),source_qualified_hours=int(expected.sum()),common_replay_hours=int(common.sum()),common_with_ontario_only_hours=int(paired.sum()),
        transforms=dict(sign="import_positive=-NYIS_reported_value",time="UTCstart=UTC_hour_ending-1hour",bulk_units="explicitMWcolumn",API_units="MWh_per_one_hour; numericagreementverifiedon25000records"),
        excluded_hour_indices=(np.flatnonzero(~expected)+1).tolist(),excluded_timestamps_utc=hours.timestamp_utc.loc[~expected].tolist(),
        quality_policy=dict(individual_zero_or_reversal_retained=True,sourcewide_zero_count=int(allzero.sum()),inconsistent_sourcewide_zero_count=int(inconsistent_zero.sum()),frozen_vector_hours=int(frozen.sum()),frozen_rule="maximal identical all-four vector run>=3hours, corroborated by independentlyvarying IESO andISNE actuals; eachrange>2MW conservative integer-rounding allowance",no_error_magnitude_filter=True,no_clipping_or_interpolation=True),
        total_series_review=dict(all8760_bilateral_sum_equals_published_SumValidDIBAs=True,max_error_mw=0.,total_difference=stats(gap),beyond_2_5MW_hours=int((abs(gap)>2.5).sum()),beyond_10MW_hours=int((abs(gap)>10).sum()),interpretation="SeparateTIseries has26large discrepancies, including15Jan15-16hours mostlyTIzero. Do notreplacecoherentbilateralswithTI orautomaticallyquarantinefromTIalone."),
        operator_comparisons=pair_stats,cached_API_overlap_records=25000,all_cached_API_values_identical=True,
        limitations=["ChosenNYISreportingperspective isconsistentacrossallfourregions; oppositePJMreporter haslargesystematicdiscrepancies andunresolvedreporting-scopeconventions, not corrected orusedforfiltering.","May6adjacenttransitionhoursretainambiguousoperator discrepancies; only categorical corroboratedwhole-vectorplateaus areexcluded.","Finitequalifiedpublishedflow isnot certificateofmeterexactness; EIAallowsrevisionsanddocumentedphysical-boundaryreportingagreements.","All-fouractualregionaltotalsleaveindividualAC/DCpartitionconditional; originalfourDCschedulesremainunchanged.","NewEIAexcludedhours differfromoldIESOexcludedhours; count8657alone doesnotestablishcohortequality; cross-scenariointersection8651isexplicit."],
        checks=CHECKS,failed_checks=0,dependencies=[dict(path=p,sha256=h)for p,h in DEPS.items()],all_input_hashes_unchanged=True,no_dispatch_or_powerflow_run=True)
    (OUT/"independent_boundary_review.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k]for k in ["status","source_finite_hours","source_qualified_hours","common_replay_hours","common_with_ontario_only_hours","failed_checks"]},indent=2))


if __name__=="__main__":main()
