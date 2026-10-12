"""Dover topology/port audit and source-preserving external PAR flow inputs.

No interface observations, fitted impedances, or phase/tap inference are used.
P34 values retain the pre-existing posted-flow numeric convention and literal
MWH header qualification. Source coverage, nonzero telemetry, and the selected
full-service cutover are distinct fields; pre-service zeros do not imply zero
intertie transfer through the separately metered bypass.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime,timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat,savemat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"output/nygrid_2025_dover_parameters/local_audit"
RAW=ROOT/"output/nygrid_2025_moses_audit/exchanges/raw"
SCHEDULES=ROOT/"output/nygrid_2025_par_controls/sources/schedules"
DIRECTION=ROOT/"output/nygrid_2025_par_controls/sources/direction"
PTIDS=np.array([625149,625150],int)
TZ="America/New_York"
CUTOVER_UTC=pd.Timestamp("2025-12-20T04:00:00Z")
P34_LIMIT=750. # Necessary |P|<=top-stage MVA screen, never a full P/Q guarantee.


def require(ok,text):
    if not bool(ok):raise ValueError(text)


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def rel(path):return str(Path(path).relative_to(ROOT)).replace("\\","/")


def dump(path,obj):Path(path).write_text(json.dumps(obj,indent=2)+"\n",encoding="utf-8")


def local_to_utc(local):
    probe=local.tz_localize(TZ,ambiguous="NaT",nonexistent="raise")
    ambiguous=np.asarray(probe.isna());flags=np.zeros(len(local),bool)
    rewinds=np.flatnonzero(np.diff(local.asi8)<-30*60*10**9)+1
    if ambiguous.any():
        candidates=[j for j in rewinds if ambiguous[j] and ambiguous[j-1]]
        require(len(candidates)==1,"Fall duplicate hour lacks an explicit source clock rewind")
        flags[:candidates[0]]=True
    result=local.tz_localize(TZ,ambiguous=flags,nonexistent="raise").tz_convert("UTC")
    return result,int(ambiguous.sum())


def aggregate(raw,hours):
    n=len(hours);values=np.full((n,2),np.nan);coverage=np.zeros((n,2));gap=np.zeros((n,2));spread=np.zeros((n,2))
    native_max=np.full((n,2),np.nan);duplicate_intervals=np.zeros((n,2),int)
    start=hours.asi8//10**9
    for column,ptid in enumerate(PTIDS):
        block=raw.loc[raw.point_id==ptid]
        grouped=block.groupby("timestamp_utc",sort=True).raw_posted_flow_value.agg(["mean","min","max","size","count"])
        ts=pd.DatetimeIndex(grouped.index).asi8//10**9
        mean=grouped["mean"].to_numpy(float);lo_value=grouped["min"].to_numpy(float);hi_value=grouped["max"].to_numpy(float)
        size=grouped["size"].to_numpy(int);count=grouped["count"].to_numpy(int)
        for h,left in enumerate(start):
            right=left+3600;lo=max(0,np.searchsorted(ts,left,side="right")-1);hi=min(len(ts)-1,np.searchsorted(ts,right,side="left"))
            integral=0.;seconds=0.;maximum_gap=0.;maximum_spread=0.;peak=0.;duplicates=0
            for j in range(lo,hi):
                touched=max(0,min(right,ts[j+1])-max(left,ts[j]))
                if touched==0:continue
                interval=ts[j+1]-ts[j];maximum_gap=max(maximum_gap,interval)
                maximum_spread=max(maximum_spread,float(hi_value[j]-lo_value[j]));duplicates+=int(size[j]>1)
                peak=max(peak,abs(float(lo_value[j])),abs(float(hi_value[j])))
                if interval<=600 and np.isfinite(mean[j]) and size[j]==count[j]:
                    seconds+=touched;integral+=touched*mean[j]
            coverage[h,column]=seconds;gap[h,column]=maximum_gap;spread[h,column]=maximum_spread;duplicate_intervals[h,column]=duplicates
            if maximum_gap>0:native_max[h,column]=peak
            if seconds==3600:values[h,column]=integral/3600.
    return values,coverage,gap,spread,native_max,duplicate_intervals


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    require(not (OUT/"Dover_P34_input_receipt.json").exists(),"Choose a fresh audit output namespace")
    dependencies={}
    def bind(path):
        path=Path(path);digest=sha(path);dependencies[rel(path)]=digest;return digest
    direction_pdf=DIRECTION/"NYISO_ParFlowDiagrams27.pdf"
    require(bind(direction_pdf)=="c0647d2abc38f216ccf5c1f197ca679cf16358fde5f507659bcdcd80a6938ba4","Direction diagram changed")
    bind(DIRECTION/"NYISO_ParFlowDiagrams27_layout.txt")
    bind(DIRECTION/"NYISO_ParFlowDiagrams27_page26.png")
    bind(OUT/"Dover_ParFlows_page06.png")
    guide=ROOT/"output/nygrid_2025_dover_parameters/sources/NYISO_MarketParticipants_UserGuide.pdf"
    if guide.exists():bind(guide)
    original_policy=ROOT/"output/nygrid_2025_par_controls/controls/input_receipt.json";bind(original_policy)
    base_path=ROOT/"output/nygrid_2025_dispatch/dispatch/dispatch.mat";bind(base_path)
    data=loadmat(base_path,simplify_cells=True,variable_names=["hour_index","timestamp_utc","gamma","dispatch_qualified"])
    times=np.asarray(data["timestamp_utc"]).astype(str);gamma=float(data["gamma"])
    hours=pd.date_range("2025-01-01","2026-01-01",freq="h",inclusive="left",tz=TZ).tz_convert("UTC")
    require(len(hours)==8760 and np.array_equal(times,hours.strftime("%Y-%m-%dT%H:%M:%SZ")),"Frozen physical hourly clock mismatch")
    common_path=ROOT/"output/nygrid_2025_western_audit/replay/paired_common_mask.npy";bind(common_path)
    common=np.load(common_path,allow_pickle=False);require(common.dtype==bool and common.shape==(8760,) and common.sum()==8651,"Frozen prior comparison cohort differs")
    receipt_path=ROOT/"output/nygrid_2025_moses_audit/exchanges/par_source_receipts.csv";bind(receipt_path)
    receipts=pd.read_csv(receipt_path);selected=receipts[(receipts.year==2025)|((receipts.year==2026)&(receipts.month==1))]
    require(len(selected)==13,"Expected12cachedmonths+endpointarchive")
    raw_parts=[];members=[];metadata=[]
    for entry in selected.itertuples(index=False):
        path=RAW/f"{int(entry.year)}{int(entry.month):02d}01ParFlows_csv.zip"
        require(bind(path)==entry.sha256,"P34 archive receipt mismatch")
        with zipfile.ZipFile(path) as archive:
            for member in sorted(archive.namelist()):
                if int(entry.year)!=2025 and member!="20260101ParFlows.csv":continue
                payload=archive.read(member);frame=pd.read_csv(io.BytesIO(payload),float_precision="round_trip")
                require(list(frame.columns)==["Timestamp","Point ID","Flow (MWH)"],"P34 schema changed")
                picked=frame[frame["Point ID"].isin(PTIDS)]
                members.append(dict(source_archive=rel(path),source_member=member,member_sha256=hashlib.sha256(payload).hexdigest(),Dover_records=len(picked)))
                for ptid in PTIDS:
                    part=picked[picked["Point ID"]==ptid]
                    metadata.append(dict(source_archive=path.name,source_member=member,local_date=member[:8],point_id=int(ptid),rows=len(part),present=bool(len(part))))
                    if not len(part):continue
                    local=pd.DatetimeIndex(pd.to_datetime(part.Timestamp,format="mixed"))
                    require((local.normalize()==pd.Timestamp(member[:8])).all(),"P34 source filename/day mismatch")
                    utc,ambiguous=local_to_utc(local)
                    value=pd.to_numeric(part["Flow (MWH)"],errors="raise").to_numpy(float)
                    raw_parts.append(pd.DataFrame(dict(timestamp_utc=utc,point_id=int(ptid),raw_posted_flow_value=value,
                        source_archive=path.name,source_member=member,source_csv_row_1based=part.index.to_numpy(int)+2,
                        raw_local_timestamp=part.Timestamp.to_numpy(str),ambiguous_local_clock_row=local.tz_localize(TZ,ambiguous="NaT",nonexistent="raise").isna())))
    require(len(members)==366,"Missing source day/endpoint")
    raw=pd.concat(raw_parts,ignore_index=True)
    require(np.isfinite(raw.raw_posted_flow_value).all(),"Native source contains nonfinite Dover values")
    values,coverage,gaps,spreads,native_max,duplicates=aggregate(raw,hours)
    coverage_ok=(coverage==3600)&np.isfinite(values)
    native_p_screen=np.isfinite(native_max)&(native_max<=P34_LIMIT+1e-9)
    duplicate_conflict=spreads>1e-9
    strict_source_quality=coverage_ok&native_p_screen&~duplicate_conflict
    post=np.asarray(hours>=CUTOVER_UTC)
    # Existing forward-hold policy averaged coincident postings. Preserve that
    # result separately; stricter duplicate-conflict qualification is explicit.
    combined=coverage_ok.all(axis=1)
    post_quality=post&strict_source_quality.all(axis=1)
    direction=dict(ptids=PTIDS.tolist(),bank_names=["T398-A","T398-B"],diagram_pdf=rel(direction_pdf),diagram_sha256=sha(direction_pdf),
        inspected_pdf_pages=[6,26],parallel_banks=True,normal_bypass_state="normally_open_as_drawn_not_hourly_switch_telemetry",
        current_documented_positive_direction="Dover_CT_LongMountain_ISONE_to_Dover_NY_CricketValley_NYISO",
        raw_to_NY_import_multiplier=[1,1],raw_to_NY_to_CT_model_branch_multiplier=[-1,-1],
        diagram_Dover_page_effective_date=None,source_document_vintage="current_2026_document_Dover_page_undated",
        historical_2025_sign_effective_date_verified=False,Moses_2024_12_03_annotation_applies_to_Dover=False,
        numeric_sign_not_selected_using_interface_fit=True,actual_tap_or_phase_telemetry_available=False)
    units=dict(literal_source_column="Flow (MWH)",numeric_policy="retain_existing_posted_PAR_flow_numeric_convention_no_energy_interval_rescaling",
        fresh_MW_unit_header_proof=False,source_row_interval="mostly5minutes_with_duplicate_or_irregular_postings",
        guide_scope="September2026_MPUG_section5.5.4_describes_hourly_SCUC_and_time_weighted_hourly_RTD_flows;does_not_relabel_literal_header",
        instantaneous_meter_MW_asserted=False,aggregation="forward_hold_between_postings_max600s;complete3600s_required;duplicates_averaged_and_spread_reported",
        no_factor12_applied=True,model_scale_gamma_applied_once=True)
    arrays=dict(hour_index=np.arange(1,8761),timestamp_utc=times,ptids=PTIDS,gamma=gamma,
        raw_posted_hourly_values=values,forward_NY_to_CT_model_mw=-gamma*values,import_CT_to_NY_model_mw=gamma*values,
        coverage_qualified=coverage_ok,both_banks_coverage_qualified=combined,coverage_seconds=coverage,maximum_source_gap_seconds=gaps,
        maximum_duplicate_spread_posted_units=spreads,duplicate_intervals=duplicates,duplicate_conflict=duplicate_conflict,
        native_max_abs_posted_value=native_max,necessary_P_only_screen=native_p_screen,strict_source_quality_qualified=strict_source_quality,
        post_full_service=post,post_full_service_source_qualified=post_quality,prior_common_comparison_mask=common,
        post_full_service_prior_common_qualified=post_quality&common,
        direction_metadata_json=json.dumps(direction),unit_metadata_json=json.dumps(units),
        historical_2025_direction_effective_date_verified=np.bool_(False),full_P_Q_thermal_qualification=np.bool_(False),
        pre_service_zero_means_zero_intertie_flow=np.bool_(False),observations_used_to_estimate_impedance=np.bool_(False))
    perbank=[];monthly=[];daily=[]
    for ptid in PTIDS:
        part=raw[raw.point_id==ptid].sort_values("timestamp_utc");inyear=part[part.timestamp_utc<hours[-1]+pd.Timedelta(hours=1)]
        nz=inyear[abs(inyear.raw_posted_flow_value)>1e-12]
        first_nz=nz.timestamp_utc.iloc[0] if len(nz) else None
        perbank.append(dict(point_id=int(ptid),bank_name="T398-A" if ptid==625149 else "T398-B",native_records_including_endpoint=len(part),native_2025_records=len(inyear),
            first_source_timestamp_utc=part.timestamp_utc.iloc[0].isoformat(),first_nonzero_timestamp_utc=first_nz.isoformat() if first_nz is not None else None,
            first_nonzero_timestamp_local=first_nz.tz_convert(TZ).isoformat() if first_nz is not None else None,
            native_2025_nonzero_rows=len(nz),native_2025_minimum=float(inyear.raw_posted_flow_value.min()),native_2025_maximum=float(inyear.raw_posted_flow_value.max()),
            pre_full_service_nonzero_rows=int(((inyear.timestamp_utc<CUTOVER_UTC)&(abs(inyear.raw_posted_flow_value)>1e-12)).sum())))
        for month in range(1,13):
            x=inyear[inyear.timestamp_utc.dt.tz_convert(TZ).dt.month==month]
            monthly.append(dict(point_id=int(ptid),month=month,source_rows=len(x),nonzero_rows=int((abs(x.raw_posted_flow_value)>1e-12).sum()),
                minimum=float(x.raw_posted_flow_value.min()) if len(x) else None,maximum=float(x.raw_posted_flow_value.max()) if len(x) else None))
        for member,x in inyear.groupby("source_member"):
            daily.append(dict(point_id=int(ptid),source_member=member,rows=len(x),nonzero_rows=int((abs(x.raw_posted_flow_value)>1e-12).sum()),minimum=float(x.raw_posted_flow_value.min()),maximum=float(x.raw_posted_flow_value.max())))
    pair=raw.groupby(["timestamp_utc","point_id"]).raw_posted_flow_value.mean().unstack()
    pair=pair.loc[(pair.index>=hours[0])&(pair.index<hours[-1]+pd.Timedelta(hours=1))].dropna()
    active_pair=pair.loc[(pair.abs()>1e-12).any(axis=1)]
    diff=active_pair[625149]-active_pair[625150]
    paircheck=dict(common_native_timestamps=len(pair),nonzero_pair_native_timestamps=len(active_pair),
        exactly_equal_nonzero_pair_timestamps=int((diff==0).sum()),maximum_absolute_bank_difference=float(abs(diff).max()) if len(diff) else None,
        mean_absolute_bank_difference=float(abs(diff).mean()) if len(diff) else None,
        independent_PTIDs_published=True,empirical_similarity_does_not_prove_sensor_alias_or_independent_measurement_accuracy=True)
    # P53A metadata only: identifiers, G/L control codes, dates and periods.
    schedule_records=[];schedule_manifest=read_json(SCHEDULES/"acquisition_receipts.json");bind(SCHEDULES/"acquisition_receipts.json")
    for receipt in schedule_manifest:
        path=ROOT/receipt["path"];require(bind(path)==receipt["sha256"],"P53A archive changed")
        with zipfile.ZipFile(path) as archive:
            for member in sorted(archive.namelist()):
                lines=archive.read(member).decode("utf-8").splitlines();header=lines[0].split()
                found={int(fields[0]):fields[1] for line in lines[1:] if len(fields:=line.split(maxsplit=2))>=2 and fields[0].isdigit() and int(fields[0]) in PTIDS}
                for ptid in PTIDS:schedule_records.append(dict(source_member=member,point_id=int(ptid),present=int(ptid) in found,
                    control_code=found.get(int(ptid),""),start_local=header[0]+" "+header[1],step_minutes=int(header[2]),periods=int(header[3]),
                    numeric_schedule_values_read=False,numeric_schedule_direction_promoted=False))
    # Existing electrical state and retained-axis contract, without mutation.
    model_folder=ROOT/"output/nygrid_2025_line_parameters/overlays/engineering_nominal"
    for name in ["full191_network_cases.mat","network_cases.mat","overlay_receipt.json"]:bind(model_folder/name)
    full=loadmat(model_folder/"full191_network_cases.mat",simplify_cells=True);slim=loadmat(model_folder/"network_cases.mat",simplify_cells=True)
    contract=dict(full_bus_count=191,full_branch_records=410,retained_bus_ids=np.asarray(slim["kept_bus_ids"],int).tolist(),retained_bus_count=148,
        retained_original_bus_count=140,retained_direct_branch_records=244,derived_equivalent_support_records=30,
        current_Dover_model_bus=20003,current_Dover_is_eliminated=True,CricketValley_retained_bus=20001,LongMountain_eliminated_bus=20002,
        nominal_full_base_mva=100,original_generators=1464,original_DC_records=4,existing_StLawrence_control_records=2,
        original_PAR_substitution_branch_row=211,original_PAR_substitution_endpoints=[48,100],
        new_PAR_parallel_ports_require_distinct_buses=True,internal_fixed_transfer_elimination_requires_input_affine_reduction=True,
        AC_phase_shifter_branch_controls_allow_zero_injection_phase_affine_recovery=True,
        new_internal_bus_requires_connected_zero_injection_leaf_before_cutover=True,old_states=[])
    for v in ["refined_2019","refined_2025_pre_may","refined_2025_may21","refined_2025_may30","refined_2025"]:
        case=full[v+"_case"]
        for j in [390,392,393,394]:contract["old_states"].append(dict(state=v,branch_row=j,from_bus=int(case["branch"][j-1,0]),to_bus=int(case["branch"][j-1,1]),
            r_pu=float(case["branch"][j-1,2]),x_pu=float(case["branch"][j-1,3]),b_pu=float(case["branch"][j-1,4]),status=int(case["branch"][j-1,10])))
    raw.to_csv(OUT/"Dover_P34_raw_2025_with_endpoint.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    pd.DataFrame(metadata).to_csv(OUT/"Dover_P34_channel_presence.csv",index=False)
    pd.DataFrame(members).to_csv(OUT/"Dover_P34_member_receipts.csv",index=False)
    pd.DataFrame(monthly).to_csv(OUT/"Dover_P34_monthly_native_audit.csv",index=False)
    pd.DataFrame(daily).to_csv(OUT/"Dover_P34_daily_native_audit.csv",index=False)
    pd.DataFrame(schedule_records).to_csv(OUT/"Dover_P53A_channel_metadata_only.csv",index=False)
    hourly=pd.DataFrame(dict(hour_index=np.arange(1,8761),timestamp_utc=times,timestamp_local=hours.tz_convert(TZ).astype(str),post_full_service=post,
                            both_banks_coverage_qualified=combined,post_full_service_source_qualified=post_quality,prior_common_mask=common))
    for j,ptid in enumerate(PTIDS):
        hourly[f"ptid_{ptid}_posted_hourly_value"]=values[:,j];hourly[f"ptid_{ptid}_coverage_seconds"]=coverage[:,j]
        hourly[f"ptid_{ptid}_NY_to_CT_model_mw"]=-gamma*values[:,j];hourly[f"ptid_{ptid}_maximum_gap_seconds"]=gaps[:,j]
        hourly[f"ptid_{ptid}_duplicate_spread"]=spreads[:,j];hourly[f"ptid_{ptid}_strict_source_quality"]=strict_source_quality[:,j]
    hourly.to_csv(OUT/"Dover_P34_hourly_2025.csv",index=False)
    np.savez_compressed(OUT/"Dover_P34_inputs.npz",**arrays);savemat(OUT/"Dover_P34_inputs.mat",arrays,do_compression=True,long_field_names=True)
    dump(OUT/"Dover_direction_source_qualification.json",direction);dump(OUT/"existing_model_contract.json",contract)
    bind(Path(__file__))
    require({p:sha(ROOT/p) for p in dependencies}==dependencies,"Protected source changed during Dover audit")
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),source_days=366,physical_2025_hours=8760,
        per_bank_native_summary=perbank,pair_comparison=paircheck,source_full_coverage_hours_per_bank=coverage_ok.sum(axis=0).tolist(),
        source_both_bank_coverage_hours=int(combined.sum()),source_duplicate_conflict_hours_per_bank=duplicate_conflict.sum(axis=0).tolist(),
        strict_source_quality_hours_per_bank=strict_source_quality.sum(axis=0).tolist(),post_full_service_hours=int(post.sum()),
        post_full_service_source_qualified_hours=int(post_quality.sum()),post_full_service_existing_common_hours=int((post_quality&common).sum()),
        fixed_full_service_cutover_utc=CUTOVER_UTC.isoformat(),cutover_scope="parent_selected_full_service_HB23_scenario_boundary_not_first_energization_inferred_from_P34",
        pre_service_zeros_not_promoted_to_zero_intertie_transfer=True,no_zero_fill_for_absent_channels=True,no_new_observation_download=True,
        no_internal_interface_observations_read=True,no_impedance_or_phase_fit=True,actual_tap_trajectory_inferred=False,
        direction=direction,units=units,necessary_P_only_screen_limit750_is_not_full_thermal_validation=True,
        schedule_scope="metadata_only_no_numeric_schedule_values_compiled_or_sign_promoted",
        source_hashes_unchanged=True,dependencies=dependencies,
        outputs={p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!="Dover_P34_input_receipt.json"})
    dump(OUT/"Dover_P34_input_receipt.json",report)
    print(json.dumps({k:report[k] for k in ["passed","per_bank_native_summary","pair_comparison","source_full_coverage_hours_per_bank","source_duplicate_conflict_hours_per_bank","post_full_service_hours","post_full_service_source_qualified_hours","post_full_service_existing_common_hours"]},indent=2))


def read_json(path):return json.loads(Path(path).read_text())


if __name__=="__main__":build()
