"""Predeclared numeric diagnostics of public P34 unit/sign interpretations.

No case, PF, parameter fit, or internal P32 value is loaded. Regional external
totals are explicitly not treated as bank-level truth. This script cannot
promote a physical unit or independent-meter origin by minimizing residuals.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"output/nygrid_2025_p34_qualification/numeric_audit"
INPUTS={
 "Dover_raw":"output/nygrid_2025_dover_parameters/local_audit/Dover_P34_raw_2025_with_endpoint.csv.gz",
 "StLawrence_raw":"output/nygrid_2025_moses_audit/exchanges/par_stlawrence_raw_2025.csv.gz",
 "Dover_proof":"output/nygrid_2025_dover_parameters/local_audit/Dover_P34_input_receipt.json",
 "StLawrence_proof":"output/nygrid_2025_par_controls/controls/input_receipt.json",
 "StLawrence_rating":"output/nygrid_2025_par_controls/sources/limits/limits.json",
 "Dover_rating":"output/nygrid_2025_dover_parameters/engineering/conditional_impedance_basis.json",
 "primary_evidence":"output/nygrid_2025_p34_qualification/sources/primary_evidence_conclusion.json",
 "IESO_hourly":"output/nygrid_2025_western_audit/ontario/ieso_new_york_hourly_2025.csv",
 "IESO_raw":"output/nygrid_2025_western_audit/ontario/raw/PUB_IntertieScheduleFlowYear_2025.csv",
 "IESO_source_manifest":"output/nygrid_2025_western_audit/ontario/source_manifest.csv",
 "NYIS_regional":"output/nygrid_2025_western_audit/boundary_actuals/hourly_regional_actuals.csv",
 "counterparty_regional":"output/nygrid_2025_western_audit/boundary_actuals/counterparty_actual_comparison.csv",
 "regional_source_audit":"output/nygrid_2025_western_audit/boundary_actuals/source_audit_receipt.json",
 "P32_channel_metadata":"output/nygrid_2025_inputs/load_source/channels.csv",
}
HYPOTHESES=[
 dict(id="power_sample_MW_forward_hold",native_multiplier=1.,hourly_view="forward_hold",meaning="numeric power sample held to next posting;timestamp support unproved"),
 dict(id="hour_mean_MW_last_in_hour",native_multiplier=1.,hourly_view="last_in_hour",meaning="updated hourly-mean power;last posting before hour boundary;interval label unproved"),
 dict(id="rolling_hour_MWh_at_hour_end",native_multiplier=1.,hourly_view="at_hour_end",meaning="one-hour rolling energy divided by one hour;numerically meanMW;rolling-window semantics unproved"),
 dict(id="five_minute_interval_MWh",native_multiplier=12.,hourly_view="forward_hold",meaning="nominal five-minute interval energy divided by5/60h;mechanical alternative only"),
]


def require(ok,text):
    if not bool(ok):raise ValueError(text)


def sha(path):
    with Path(path).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()


def dump(path,obj):Path(path).write_text(json.dumps(obj,indent=2)+"\n",encoding="utf-8")


def declare():
    OUT.mkdir(parents=True,exist_ok=True);path=OUT/"hypothesis_plan.json"
    require(not path.exists(),"Existing hypothesis plan is immutable")
    plan=dict(created_utc=datetime.now(timezone.utc).isoformat(),purpose="numeric plausibility and comparability audit;not unit selection by fit",
        prior_knowledge="Earlier audits already exposed raw values and maxima;this declaration precedes new alternate-unit/cross-operator calculations,not all prior knowledge of the data",
        hypotheses=HYPOTHESES,signs=[1,-1],
        sign_meaning={"1":"documented external-to-NY direction;Ontario2025 source applicable,Dover historical effective date still unproved",
                      "-1":"deliberately reversed diagnostic;not a sign inferred from fit"},
        scope_devices={"StLawrence":[25118,25119],"Dover":[625149,625150]},
        diagnostics=["native UTC cadence/duplicate/off-grid counts", "factor1/factor12 conditional nominal-MVA screen per bank,includingnonzero record counts",
          "weighted-hour versus last-in-hour and hour-boundary values", "fixed independently sourced external-total clock/sign reciprocity with predeclared-1,0,+1hour lags",
          "regional total minus candidatePARbank subtotal as unmeasured-other-path remainder;never bank prediction error"],
        measurement_kind="operator-reported P34 product;SCADA versus calculatedRTD origin unresolved",
        rating_screen_scope="only conditional |P|<=nominalS plausibility;ifreportedvaluesarephysicalactivepower;not certified operating/emergency limit or proof of unit",
        aggregate_identifiability="T=s*m*P34+R_others;unmeasured R_others may vary hourly,so T does not identify multiplier m or sign s",
        prohibited=["internalP32numericvalues","PF/case/dispatchchanges","selectingunit/sign/lagsbyinternalerror","equatingDoverwithallNYISO-ISONEties","equatingtwoStLawrencePARswithallNYISO-IESOties"],
        inputs={role:dict(path=p,sha256=sha(ROOT/p)) for role,p in INPUTS.items()})
    dump(path,plan);print(json.dumps(dict(declared=True,path=str(path),sha256=sha(path))))


def views(part,hours):
    grouped=part.groupby("utc",sort=True).posted.agg(["mean","min","max","size"])
    ts=pd.DatetimeIndex(grouped.index).asi8//10**9;v=grouped["mean"].to_numpy(float)
    origin=int(hours.asi8[0]//10**9);finish=origin+8760*3600
    dt=np.diff(ts);left=np.maximum(ts[:-1],origin);right=np.minimum(ts[1:],finish)
    valid=(dt>0)&(dt<=600)&np.isfinite(v[:-1])&(right>left)
    lo,hi,val=left[valid],right[valid],v[:-1][valid]
    h0=(lo-origin)//3600;h1=(hi-1-origin)//3600
    duration=np.minimum(hi,origin+(h0+1)*3600)-lo
    seconds=np.zeros(8760);energy=np.zeros(8760)
    np.add.at(seconds,h0,duration);np.add.at(energy,h0,duration*val)
    crosses=h1>h0;duration2=hi[crosses]-(origin+h1[crosses]*3600)
    np.add.at(seconds,h1[crosses],duration2);np.add.at(energy,h1[crosses],duration2*val[crosses])
    mean=np.full(8760,np.nan);q=seconds==3600;mean[q]=energy[q]/3600.
    ends=origin+(np.arange(8760)+1)*3600;result={"forward_hold":mean}
    for name,side in [("last_in_hour","left"),("at_hour_end","right")]:
        ix=np.searchsorted(ts,ends,side=side)-1;ok=ix>=0;clipped=np.clip(ix,0,len(ts)-1)
        ok&=(ends-ts[clipped]<=600)&np.isfinite(v[clipped]);a=np.full(8760,np.nan);a[ok]=v[clipped[ok]];result[name]=a
    year=(ts>=origin)&(ts<finish);cadence=dt[year[:-1]]
    rawyear=part[(part.utc>=hours[0])&(part.utc<hours[-1]+pd.Timedelta(hours=1))]
    summary=dict(native_records_2025=len(rawyear),unique_native_timestamps_2025=int(year.sum()),duplicate_native_timestamps=int(len(rawyear)-year.sum()),
        first_source_UTC=pd.Timestamp(grouped.index[0]).isoformat(),median_posting_interval_seconds=float(np.median(cadence)),
        posting_intervals_under300s=int((cadence<300).sum()),posting_intervals_exact300s=int((cadence==300).sum()),
        posting_intervals_301_to600s=int(((cadence>300)&(cadence<=600)).sum()),posting_intervals_over600s=int((cadence>600).sum()),
        native_timestamps_off_nominal5minute_grid=int(((ts[year]%300)!=0).sum()),
        source_hours_full_forward_hold_coverage=int(q.sum()),maximum_duplicate_spread=float((grouped["max"]-grouped["min"]).max()))
    histogram=pd.Series(cadence).value_counts().sort_index().rename_axis("seconds").reset_index(name="count")
    return result,summary,histogram


def stat(x):
    x=np.asarray(x,float);x=x[np.isfinite(x)]
    return dict(count=len(x),mean=float(np.mean(x)) if len(x) else None,mean_absolute=float(np.mean(abs(x))) if len(x) else None,
                minimum=float(np.min(x)) if len(x) else None,maximum=float(np.max(x)) if len(x) else None,
                maximum_absolute=float(np.max(abs(x))) if len(x) else None,negative_count=int((x<0).sum()))


def run():
    plan_path=OUT/"hypothesis_plan.json";plan=json.loads(plan_path.read_text())
    require(plan["hypotheses"]==HYPOTHESES,"Hypotheses differ from frozen declaration")
    deps={item["path"]:item["sha256"] for item in plan["inputs"].values()}
    for p,h in deps.items():require(sha(ROOT/p)==h,"Frozen input changed: "+p)
    deps[str(plan_path.relative_to(ROOT)).replace("\\","/")]=sha(plan_path)
    primary=json.loads((ROOT/INPUTS["primary_evidence"]).read_text())
    require(primary["audit_complete"] and not primary["physical_unit_confirmed"] and not primary["product_kind"]["independent_metered_actual_confirmed"],"Revisit diagnostic design after changed primary qualification")
    limits=json.loads((ROOT/INPUTS["StLawrence_rating"]).read_text())
    require({int(d["ptid"]):float(d["nominal_mva"]) for d in limits["devices"]}=={25118:300.,25119:300.},"StLawrence reference rating changed")
    dover=json.loads((ROOT/INPUTS["Dover_rating"]).read_text());require(max(dover["source_nameplate"]["per_bank_cooling_nameplate_mva"])==750,"Dover selected rating changed")
    hours=pd.date_range("2025-01-01","2026-01-01",freq="h",inclusive="left",tz="America/New_York").tz_convert("UTC")
    times=hours.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy(str);post=np.asarray(hours>=pd.Timestamp("2025-12-20T04:00:00Z"))
    frames=[]
    for family,role,column in [("StLawrence","StLawrence_raw","original_flow_mw"),("Dover","Dover_raw","raw_posted_flow_value")]:
        d=pd.read_csv(ROOT/INPUTS[role],usecols=["timestamp_utc","point_id",column],float_precision="round_trip")
        d=d.rename(columns={column:"posted"});d["utc"]=pd.to_datetime(d.timestamp_utc,utc=True);d["family"]=family;frames.append(d)
    raw=pd.concat(frames,ignore_index=True);require(np.isfinite(raw.posted).all(),"Nonfinite native posted value")
    perdevice={};cadence=[];histograms=[];plausibility=[];aggregation=[];hourly={}
    for (family,ptid),g in raw.groupby(["family","point_id"]):
        vv,summary,hist=views(g,hours);perdevice[int(ptid)]=vv;summary.update(family=family,ptid=int(ptid));cadence.append(summary)
        hist["family"]=family;hist["ptid"]=int(ptid);histograms.append(hist)
        scope=[("all_available_2025",(g.utc>=hours[0])&(g.utc<hours[-1]+pd.Timedelta(hours=1)))]
        if family=="Dover":scope.append(("post_full_service",(g.utc>=pd.Timestamp("2025-12-20T04:00:00Z"))&(g.utc<hours[-1]+pd.Timedelta(hours=1))))
        rating=300. if family=="StLawrence" else 750.
        for scope_name,use in scope:
            x=g.loc[use,"posted"].to_numpy(float);nonzero=abs(x)>1e-12
            for factor in [1.,12.]:
                candidate=x*factor;exceed=abs(candidate)>rating+1e-9
                plausibility.append(dict(family=family,ptid=int(ptid),scope=scope_name,power_multiplier=factor,nominal_reference_mva=rating,
                    source_record_count=len(x),nonzero_source_records=int(nonzero.sum()),maximum_candidate_active_power_if_hypothesis_MW=float(abs(candidate).max()),
                    maximum_ratio_to_nominal_MVA=float(abs(candidate).max()/rating),nominal_envelope_conflict_records=int(exceed.sum()),
                    nominal_envelope_conflict_fraction_of_nonzero=float(exceed.sum()/nonzero.sum()) if nonzero.sum() else None,
                    conflict_over2x_nominal_records=int((abs(candidate)>2*rating).sum()),conflict_over5x_nominal_records=int((abs(candidate)>5*rating).sum()),
                    measured_physical_overload_established=False,unit_proven_by_rating_screen=False,measurement_kind_unresolved=True))
        for alternate in ["last_in_hour","at_hour_end"]:
            q=np.isfinite(vv["forward_hold"])&np.isfinite(vv[alternate]);use=q&post if family=="Dover" else q
            delta=vv[alternate][use]-vv["forward_hold"][use]
            aggregation.append(dict(family=family,ptid=int(ptid),scope="post_full_service" if family=="Dover" else "year",alternate=alternate,
                common_hours=int(use.sum()),mean_absolute_difference_posted_units=float(abs(delta).mean()),maximum_absolute_difference_posted_units=float(abs(delta).max()),
                mean_difference_posted_units=float(delta.mean()),correct_timestamp_support_identified=False))
    for family,ids in [("StLawrence",[25118,25119]),("Dover",[625149,625150])]:
        hourly[family]={view:np.sum(np.column_stack([perdevice[p][view] for p in ids]),axis=1) for view in ["forward_hold","last_in_hour","at_hour_end"]}
    region=pd.read_csv(ROOT/INPUTS["NYIS_regional"],usecols=["timestamp_utc","ONTARIO_actual_import_mw","ISONE_actual_import_mw","ONTARIO_source_qualified","ISONE_source_qualified"],float_precision="round_trip")
    ieso_path=ROOT/INPUTS["IESO_hourly"]
    ieso=pd.read_csv(ieso_path,float_precision="round_trip")
    counterpart=pd.read_csv(ROOT/INPUTS["counterparty_regional"],usecols=["timestamp_utc","ISNE_reported_import_to_NY_mw"],float_precision="round_trip")
    for label,frame in [("NYIS",region),("IESO",ieso),("ISNE",counterpart)]:require(np.array_equal(frame.timestamp_utc.to_numpy(str),times),label+" frozenUTCaxis mismatch")
    externals={"StLawrence":[("NYIS_reported_IESO_total",region.ONTARIO_actual_import_mw.to_numpy(float),region.ONTARIO_source_qualified.to_numpy(bool)),
                            ("IESO_reported_NEW_YORK_total",ieso.actual_ontario_to_ny_mw.to_numpy(float),ieso.source_quality_qualified.to_numpy(bool))],
               "Dover":[("NYIS_reported_ISONE_total",region.ISONE_actual_import_mw.to_numpy(float),region.ISONE_source_qualified.to_numpy(bool)),
                        ("ISNE_reported_NYIS_total",counterpart.ISNE_reported_import_to_NY_mw.to_numpy(float),np.isfinite(counterpart.ISNE_reported_import_to_NY_mw.to_numpy(float)))]}
    remainder=[];long=[]
    for family,sets in externals.items():
        for hypothesis in HYPOTHESES:
            candidate=hourly[family][hypothesis["hourly_view"]]*hypothesis["native_multiplier"]
            for sign in plan["signs"]:
                for external_label,total,quality in sets:
                    q=quality&np.isfinite(total)&np.isfinite(candidate)
                    if family=="Dover":q&=post
                    other=total[q]-sign*candidate[q]
                    remainder.append(dict(family=family,hypothesis=hypothesis["id"],sign=sign,external_total=external_label,
                        scope="post_full_service" if family=="Dover" else "year",**stat(other),
                        quantity="unmeasured_other_path_remainder_not_PAR_error",bank_unit_or_sign_identifiable_from_this_remainder=False,
                        includes_possible_Dover_bypass_and_other_ISONE_ties=family=="Dover"))
                    if external_label.startswith("IESO") or external_label.startswith("NYIS_reported_ISONE"):
                        for h in np.flatnonzero(q):long.append(dict(timestamp_utc=times[h],family=family,hypothesis=hypothesis["id"],sign=sign,
                            external_total_label=external_label,external_total_import_mw=total[h],candidate_PAR_subtotal_mw_if_hypothesis=sign*candidate[h],
                            unmeasured_other_path_remainder=total[h]-sign*candidate[h],not_an_error_metric=True))
    reciprocity=[]
    for family,(left,right) in [(f,x) for f,x in externals.items()]:
        name_a,a,qa=left;name_b,b,qb=right
        for lag in [-1,0,1]:
            ia=np.arange(max(0,-lag),min(8760,8760-lag));ib=ia+lag
            q=qa[ia]&qb[ib]&np.isfinite(a[ia])&np.isfinite(b[ib])
            diff=a[ia[q]]-b[ib[q]]
            reciprocity.append(dict(family=family,quantity="same_regional_boundary_two_reporting_perspectives",report_a=name_a,report_b=name_b,
                report_b_lag_hours=lag,**stat(diff),PAR_scale_or_sign_proven=False,lag_selected_for_model=False,
                qualification="IESOandNYISsourcequalityflags" if family=="StLawrence" else "NYISquality_and_ISNE_finite_only_no_independent_native_meter_quality_claim"))
    # Exact same-element external comparators were not found in cached products.
    # All residuals above deliberately leave other paths unmeasured.
    identity=[dict(P34_family="StLawrence",P34_ptids="25118;25119",P34_scope="two northern PAR-bank reports",external_product="IESO NEW-YORK / EIA NYIS-IESO",
                  external_scope="regional boundary total including western interties",same_physical_grain=False,independent_bank_meter_available=False),
              dict(P34_family="Dover",P34_ptids="625149;625150",P34_scope="two parallel PAR-bank reports;possible bypass is separately metered",
                  external_product="EIA NYIS-ISNE / ISNE-NYIS",external_scope="all regional AC/DC interties,not just Dover",same_physical_grain=False,independent_bank_meter_available=False),
              dict(P34_family="both",P34_ptids="same_PTIDs_in_P53A",P34_scope="operator-reportedP34flow",external_product="P53A schedules",
                  external_scope="scheduled quantities,not independent actual flow",same_physical_grain=False,independent_bank_meter_available=False)]
    outputs=[("cadence_summary.csv",pd.DataFrame(cadence)),("cadence_histogram.csv",pd.concat(histograms,ignore_index=True)),
             ("unit_scale_plausibility.csv",pd.DataFrame(plausibility)),("hourly_aggregation_sensitivity.csv",pd.DataFrame(aggregation)),
             ("external_remainder_diagnostics.csv",pd.DataFrame(remainder)),("regional_cross_operator_reciprocity.csv",pd.DataFrame(reciprocity)),
             ("comparator_identity_scope.csv",pd.DataFrame(identity))]
    for name,df in outputs:df.to_csv(OUT/name,index=False)
    pd.DataFrame(long).to_csv(OUT/"hourly_mechanical_remainders.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    require({p:sha(ROOT/p) for p in deps}==deps,"Frozen source changed during numeric audit")
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),predeclared_hypothesis_plan_sha256=sha(plan_path),
        devices=4,unit_semantic_hypotheses=len(HYPOTHESES),sign_diagnostics=2,source_header="Flow (MWH)",
        physical_P34_unit_established=False,independent_SCADA_or_RTD_origin_established=False,
        exact_same_bank_external_meter_found=False,source_time_support_established=False,
        numeric_unit_multiplier_selected=None,numeric_sign_selected=None,numeric_lag_selected=None,
        actual_nominal_envelope_overload_proven=False,confirmed_numeric_bug_requiring_case_change=False,
        internal_P32_value_columns_read=False,model_or_PF_or_dispatch_run=False,source_hashes_unchanged=True,
        conclusions=["Factor12 creates substantial nominal-rating conflicts ifvaluesrepresentphysicalactivepower;thisisplausibilityevidence,notunitproof.",
          "Factor1 power and one-hour-energy interpretations are not distinguished by scale alone.",
          "Irregular/off-grid postings require interval/revision semantics before they can be summed as nonoverlapping5minuteenergies.",
          "Regional external totals corroborate only their own scope/clock/sign; unmeasured other paths prevent identification of individualPARscale/sign.",
          "Reported P34 values must not be called independent sensor/SCADA observations without product-origin evidence."],
        dependencies=deps,script_sha256=sha(__file__),outputs={p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!="numeric_audit_receipt.json"})
    dump(OUT/"numeric_audit_receipt.json",report)
    print(pd.DataFrame(plausibility).query("scope=='all_available_2025'")[["family","ptid","power_multiplier","maximum_candidate_active_power_if_hypothesis_MW","maximum_ratio_to_nominal_MVA","nominal_envelope_conflict_records","nonzero_source_records"]].to_string(index=False))
    print(json.dumps(dict(passed=True,unit_selected=None,sign_selected=None,confirmed_model_bug=False)))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--declare",action="store_true");args=parser.parse_args()
    declare() if args.declare else run()
