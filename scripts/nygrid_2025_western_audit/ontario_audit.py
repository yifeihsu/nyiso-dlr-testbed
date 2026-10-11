"""Audit Ontario scheduled versus actual external exchanges without internal scores.

Only reads external-source fields, canonical hour identities and source-qualified
control masks. Positive IESO NEW-YORK Flow is Ontario-to-New-York. IESO reports
hour-ending1..24 in fixed EST, so HE1 starts00:00EST=05:00UTC year-round.

Writes new audit evidence only. A delivered hourly_actual_exchange.csv is never
silently overwritten with different bytes. External Ontario generation must
change by +gamma*delta and the required native balance by -gamma*delta in the
downstream bounded reconstruction; this script does not modify dispatch.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_western_audit/ontario"
RAW = OUT / "raw"
EST = timezone(timedelta(hours=-5))
NY_ZONE = "NEW-YORK"
P32 = ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv"
HOURS = ROOT / "output/nygrid_2025_inputs/load_source/hour_catalog.csv"
P34 = ROOT / "output/nygrid_2025_par_controls/controls/hourly_controls.csv"
CONTROL_RECEIPT = ROOT / "output/nygrid_2025_par_controls/controls/input_receipt.json"
DOE_URL = "https://www.energy.gov/documents/motion-intervene-request-rehearing-and-motion-stay-state-washington-exhibits-1-10-2"
IESO_BASE = "https://reports-public.ieso.ca/public/IntertieScheduleFlowYear/"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def acquire(name, url, offline):
    path = RAW / name
    receipt = path.with_suffix(path.suffix + ".receipt.json")
    if path.exists():
        require(receipt.exists(), f"Existing source lacks a receipt: {path}")
        record = json.loads(receipt.read_text())
        require(record["url"] == url and record["sha256"] == sha(path), f"Existing source mismatch: {name}")
        return record
    require(not offline, f"Missing offline source: {name}")
    request = urllib.request.Request(url, headers={"User-Agent": "NPCC-Ontario-source-audit/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read()
        record = dict(url=url, file=name, http_status=response.status, retrieved_utc=stamp(),
                      bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                      http_last_modified=response.headers.get("Last-Modified", ""))
    path.write_bytes(data)
    receipt.write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
    return record


def write_csv(frame, name, protect_existing=False):
    payload = frame.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%SZ", lineterminator="\n").encode("utf-8")
    path = OUT / name
    if protect_existing and path.exists():
        require(path.read_bytes() == payload, f"Delivered numeric input would change: {name}")
    else:
        path.write_bytes(payload)


def hour_start_utc(dates, ending):
    values = pd.to_numeric(ending, errors="raise").astype(int)
    require(values.between(1, 24).all(), "IESO hour ending is outside1..24")
    local = pd.DatetimeIndex(pd.to_datetime(dates) + pd.to_timedelta(values-1, unit="h"))
    return local.tz_localize(EST).tz_convert("UTC")


def read_year(path, year, complete=True):
    """Two independent CSV parsers verify every source value and field identity."""
    content = path.read_text(encoding="utf-8-sig")
    records = list(csv.reader(io.StringIO(content)))
    require(records[0][0].startswith("\\\\Yearly Intertie Schedule and Flow Report"), "Unknown annual source report")
    require(records[2][0] == f"\\\\For {year}", "Source year/header mismatch")
    groups, fields = records[3], records[4]
    require(fields[:2] == ["Date", "Hour"], "Annual date/hour header mismatch")
    names = ["date", "hour"] + [f"{group}__{field}" for group, field in zip(groups[2:], fields[2:])]
    require(len(names) == len(set(names)), "Duplicate annual field identity")
    table = pd.DataFrame(records[5:], columns=names)
    dates = pd.to_datetime(table.date)
    require(dates.dt.year.eq(year).all(), "Annual file contains another year")
    table["hour"] = pd.to_numeric(table.hour, errors="raise").astype(int)
    require(not table.duplicated(["date", "hour"]).any(), "Duplicate IESO date/hour")
    for column in names[2:]:
        table[column] = pd.to_numeric(table[column], errors="raise")
    second = pd.read_csv(path, header=[3, 4])
    require(len(second) == len(table), "CSV readers disagree on row count")
    for group, field in zip(groups[2:], fields[2:]):
        a = table[f"{group}__{field}"].to_numpy(float)
        b = pd.to_numeric(second[(group, field)], errors="raise").to_numpy(float)
        require(np.array_equal(a, b, equal_nan=True), f"CSV readers disagree: {group}/{field}")
    require(set(table.groupby("date").hour.apply(lambda x: tuple(x))) == {tuple(range(1,25))}, "Missing or reordered source hour")
    if complete:
        require(len(table) == 8760 and table.date.nunique() == 365, "Expected full non-leap year")
    table["timestamp_utc"] = hour_start_utc(table.date, table.hour)
    require(table.timestamp_utc.is_unique and table.timestamp_utc.is_monotonic_increasing, "Nonunique or unordered physical hour")
    require(np.all(np.diff(table.timestamp_utc.astype("int64")) == 3600*10**9), "Missing physical interval")
    imp = table[f"{NY_ZONE}__Imp"]
    exp = table[f"{NY_ZONE}__Exp"]
    actual = table[f"{NY_ZONE}__Flow"]
    require((imp.dropna() >= 0).all() and (exp.dropna() >= 0).all(), "Scheduled directional quantities must be nonnegative")
    result = pd.DataFrame(dict(timestamp_utc=table.timestamp_utc,
                               actual_ontario_to_ny_mw=actual,
                               source_net_schedule_mw=exp-imp,
                               source_scheduled_import_to_ontario_mw=imp,
                               source_scheduled_export_from_ontario_mw=exp,
                               ieso_trade_date=table.date,
                               ieso_hour_ending_EST=table.hour,
                               coverage_qualified=np.isfinite(actual)&np.isfinite(imp)&np.isfinite(exp)))
    zone_names = list(dict.fromkeys(groups[2:]))
    require(NY_ZONE in zone_names and "Total" in zone_names and len(zone_names) == 15, "Unexpected intertie-zone scope")
    # A literal zero for NEW-YORK alone is a valid possible observation. The
    # distinct report-wide signature below quarantines a suspect source hour:
    # every one of the 14 intertie actuals AND TotalFlow is zero even though
    # published directional schedules are nonzero. No internal NYISO interface
    # observation is read to define this predicate, and no raw value is replaced.
    all_flows = table[[f"{zone}__Flow" for zone in zone_names]]
    all_schedules = table[[f"{zone}__{field}" for zone in zone_names for field in ["Imp", "Exp"]]]
    result["all_intertie_actual_zero"] = all_flows.eq(0).all(axis=1)
    result["schedules_nonzero"] = all_schedules.ne(0).any(axis=1) & np.isfinite(all_schedules).all(axis=1)
    suspect = result.all_intertie_actual_zero & result.schedules_nonzero
    result["source_quality_qualified"] = result.coverage_qualified & ~suspect
    result["quality_reason"] = np.select(
        [~result.coverage_qualified, suspect],
        ["missing_or_nonfinite_new_york_value", "suspect_report_wide_actual_zero_with_nonzero_schedules"],
        default="finite_value_without_report_wide_zero_signature")
    totals = {}
    for field in ["Imp", "Exp", "Flow"]:
        summed = table[[f"{zone}__{field}" for zone in zone_names if zone != "Total"]].sum(axis=1, min_count=14)
        diff = summed - table[f"Total__{field}"]
        totals[field] = float(diff.abs().max())
    return result, dict(year=year, source_rows=len(table), source_days=table.date.nunique(),
                        all_numeric_cells_independently_parsed=True, fields=len(names),
                        zero_actual_flow_rows=int(actual.eq(0).sum()),
                        suspect_report_wide_zero_hours=int(suspect.sum()),
                        source_quality_qualified_hours=int(result.source_quality_qualified.sum()),
                        missing_actual_flow_rows=int(actual.isna().sum()),
                        qualified_rows=int(result.coverage_qualified.sum()),
                        intertie_zones=zone_names, maximum_rounded_total_minus_zone_sum_mw=totals)


def summarize(series):
    x = np.asarray(series, float); x = x[np.isfinite(x)]
    require(len(x) > 0, "Empty summary population")
    return dict(hours=len(x), mean=float(x.mean()), mae=float(np.abs(x).mean()),
                rmse=float(np.sqrt(np.mean(x*x))), minimum=float(x.min()), maximum=float(x.max()))


def source_checks():
    """Read the primary schema, stylesheet and a contemporary XML/CSV pair."""
    xsl = (RAW/"IntertieScheduleFlow_HTML_t1-2.xsl").read_text()
    xsd = (RAW/"IntertieScheduleFlow_r2.xsd").read_text()
    require("Hour 1 represents the period from 0:00 to 1:00 (EST)" in xsl, "Report-specific EST hour definition missing")
    require("midnight (EST) to the following midnight (EST)" in xsl, "Report day definition missing")
    require("Net schedule (Export - Import)" in xsl, "Scheduled net sign convention missing")
    require("Collection of tie lines between Ontario and a neighbouring jurisdiction" in xsd, "Intertie-zone scope definition missing")
    require("Net amount of active power (MW) flowing through an intertie zone" in xsd, "Actual-flow MW definition missing")
    require("Delivery hour indicates hour ending" in xsd, "Hour-ending definition missing")
    # This probe verifies the meaning/aggregation of the annual Flow field.
    # It does not pretend that2025 daily XML remains available after90dayretention.
    year26, _ = read_year(RAW/"PUB_IntertieScheduleFlowYear_2026.csv", 2026, complete=False)
    annual = year26.loc[year26.ieso_trade_date.eq("2026-10-10")].set_index("ieso_hour_ending_EST")
    ns = {"i":"http://www.theIMO.com/schema"}
    doc = ET.parse(RAW/"IntertieScheduleFlow_20261010.xml").getroot()
    zone = next(x for x in doc.findall(".//i:IntertieZone",ns) if x.find("i:IntertieZoneName",ns).text == NY_ZONE)
    actual = pd.DataFrame([dict(hour=int(x.find("i:Hour",ns).text), interval=int(x.find("i:Interval",ns).text),
                                flow=float(x.find("i:Flow",ns).text)) for x in zone.findall("i:Actuals/i:Actual",ns)])
    require(len(actual)==288 and not actual.duplicated(["hour","interval"]).any(), "Incomplete XML probe")
    means = actual.groupby("hour").flow.mean()
    require(actual.groupby("hour").size().eq(12).all(), "XML probe missing5minute interval")
    result = pd.DataFrame(dict(ieso_hour_ending_EST=means.index,
                               xml_twelve_interval_mean_mw=means.to_numpy(),
                               annual_csv_flow_mw=annual.loc[means.index,"actual_ontario_to_ny_mw"].to_numpy()))
    result["csv_minus_xml_mean_mw"] = result.annual_csv_flow_mw-result.xml_twelve_interval_mean_mw
    require(result.csv_minus_xml_mean_mw.abs().max() <= .5+1e-9, "Annual field is not the rounded XML hourly mean")
    for schedule in zone.findall("i:Schedules/i:Schedule",ns):
        hour=int(schedule.find("i:Hour",ns).text)
        require(float(schedule.find("i:Import",ns).text)==annual.loc[hour,"source_scheduled_import_to_ontario_mw"],"XML/CSV import mismatch")
        require(float(schedule.find("i:Export",ns).text)==annual.loc[hour,"source_scheduled_export_from_ontario_mw"],"XML/CSV export mismatch")
    write_csv(result,"cross_format_probe_20261010.csv")
    # Fixed EST preserves the physical instants around New York's local folds.
    samples=hour_start_utc(pd.Series(["2025-03-09","2025-11-02","2025-11-02","2025-07-01"]),pd.Series([3,1,2,1]))
    require(list(samples.strftime("%Y-%m-%dT%H:%MZ")) == ["2025-03-09T07:00Z","2025-11-02T05:00Z","2025-11-02T06:00Z","2025-07-01T05:00Z"],"FixedEST conversion fixture failed")
    local=samples.tz_convert("America/New_York")
    require(local[1].hour==local[2].hour==1 and local[1].utcoffset()!=local[2].utcoffset(),"NewYork fallfold identity lost")
    return dict(primary_XSD_actual_units_MW=True,primary_XSD_zone_is_collection_of_neighbor_ties=True,
                primary_XSL_EST_hour_ending_proof=True,physical_DST_conversion_fixtures_passed=True,
                contemporary_XML_CSV_probe_day="2026-10-10",contemporary_XML_CSV_probe_hours=24,
                XML_native_samples=288,maximum_CSV_minus_XML_hourly_average_mw=float(result.csv_minus_xml_mean_mw.abs().max()),
                historical_2025_daily_XML_crosscheck_available=False,
                historical_2025_daily_XML_limitation="Public daily directory retains90days; no all-year2025 native-interval coverage claim is made.")


def build(offline=False):
    OUT.mkdir(parents=True,exist_ok=True); RAW.mkdir(parents=True,exist_ok=True)
    protected=[P32,HOURS,P34,CONTROL_RECEIPT,ROOT/"output/nygrid_2025_dispatch/dispatch/dispatch.mat",
               ROOT/"output/nygrid_2025_par_controls/replay/dated_verified_PAR_flows.mat"]
    frozen={p.relative_to(ROOT).as_posix():sha(p) for p in protected}
    receipt_specs=[(f"PUB_IntertieScheduleFlowYear_{year}.csv",IESO_BASE+f"PUB_IntertieScheduleFlowYear_{year}.csv") for year in [2019,2025,2026]]
    receipt_specs.append(("PUB_IntertieScheduleFlowYear_2025_v394.csv",IESO_BASE+"PUB_IntertieScheduleFlowYear_2025_v394.csv"))
    receipt_specs += [("IntertieScheduleFlow_h1.pdf","https://reports-public.ieso.ca/docrefs/helpfile/IntertieScheduleFlow_h1.pdf"),
                     ("IntertieScheduleFlow_20261010.xml","https://reports-public.ieso.ca/public/IntertieScheduleFlow/PUB_IntertieScheduleFlow_20261010.xml"),
                     ("IntertieScheduleFlow_HTML_t1-2.xsl","https://reports-public.ieso.ca/docrefs/stylesheet/IntertieScheduleFlow_HTML_t1-2.xsl"),
                     ("IntertieScheduleFlow_r2.xsd","https://reports-public.ieso.ca/docrefs/schema/IntertieScheduleFlow_r2.xsd")]
    receipts=[acquire(name,url,offline) for name,url in receipt_specs]
    require((RAW/"PUB_IntertieScheduleFlowYear_2025.csv").read_bytes()==(RAW/"PUB_IntertieScheduleFlowYear_2025_v394.csv").read_bytes(),
            "Unversioned2025 source differs from final archivedv394")
    source_validation=source_checks()
    years={}; audits=[];annual_summary=[]
    for year in [2019,2025]:
        table,audit=read_year(RAW/f"PUB_IntertieScheduleFlowYear_{year}.csv",year)
        years[year]=table;audits.append(audit)
        for name in ["actual_ontario_to_ny_mw","source_net_schedule_mw"]:
            annual_summary.append(dict(year=year,quantity=name,**summarize(table[name])))
        annual_summary.append(dict(year=year,quantity="actual_minus_IESO_net_schedule_mw",**summarize(table.actual_ontario_to_ny_mw-table.source_net_schedule_mw)))
        write_csv(table,f"ieso_new_york_hourly_{year}.csv")
    original=pd.read_csv(P32,usecols=["timestamp_utc","SCH - OH - NY"])
    original["timestamp_utc"]=pd.to_datetime(original.timestamp_utc,utc=True)
    original=original.rename(columns={"SCH - OH - NY":"original_nyiso_schedule_mw"})
    hours=pd.read_csv(HOURS);hours["timestamp_utc"]=pd.to_datetime(hours.timestamp_utc,utc=True)
    frame=hours[["hour_index","timestamp_utc"]].merge(years[2025],on="timestamp_utc",validate="one_to_one").merge(original,on="timestamp_utc",validate="one_to_one")
    require(len(frame)==8760 and frame.timestamp_utc.equals(hours.timestamp_utc),"IESO/NYISO physical axes differ")
    frame["actual_minus_original_schedule_mw"]=frame.actual_ontario_to_ny_mw-frame.original_nyiso_schedule_mw
    frame["original_schedule_qualified"]=np.isfinite(frame.original_nyiso_schedule_mw)
    columns=["hour_index","timestamp_utc","actual_ontario_to_ny_mw","source_net_schedule_mw","original_nyiso_schedule_mw",
             "coverage_qualified","actual_minus_original_schedule_mw","original_schedule_qualified","ieso_trade_date","ieso_hour_ending_EST"]
    write_csv(frame[columns],"hourly_actual_exchange.csv",protect_existing=True)
    quality_columns=["hour_index","timestamp_utc","source_quality_qualified","all_intertie_actual_zero","schedules_nonzero","quality_reason"]
    write_csv(frame[quality_columns],"hourly_exchange_quality.csv")
    controls=pd.read_csv(P34,usecols=["timestamp_utc","observed_replay_qualified","ptid_25118_observed_public_mw","ptid_25119_observed_public_mw"])
    controls["timestamp_utc"]=pd.to_datetime(controls.timestamp_utc,utc=True)
    frame=frame.merge(controls,on="timestamp_utc",validate="one_to_one")
    frame["observed_north_ontario_to_ny_mw"]=frame[["ptid_25118_observed_public_mw","ptid_25119_observed_public_mw"]].sum(axis=1,min_count=2)
    frame["actual_western_residual_ontario_to_ny_mw"]=frame.actual_ontario_to_ny_mw-frame.observed_north_ontario_to_ny_mw
    frame["prior_mixed_basis_western_ontario_to_ny_mw"]=frame.original_nyiso_schedule_mw-frame.observed_north_ontario_to_ny_mw
    common_before_quality=frame.observed_replay_qualified.astype(str).str.lower().eq("true") & frame.coverage_qualified & frame.original_schedule_qualified
    require(int(common_before_quality.sum())==8663 and frame.loc[common_before_quality,columns[2:5]].notna().all().all(),"Incomplete common replay cohort")
    common=common_before_quality & frame.source_quality_qualified
    require(int(common.sum())==8657,"Unexpected source-quality common cohort")
    frame["common_replay_qualified_before_source_quality"]=common_before_quality
    frame["common_replay_qualified"]=common
    suspect=frame.all_intertie_actual_zero & frame.schedules_nonzero
    require(int(suspect.sum())==6 and int((suspect & common_before_quality).sum())==6,"Unexpected report-wide zero count")
    suspect_columns=quality_columns+["ieso_trade_date","ieso_hour_ending_EST","actual_ontario_to_ny_mw","source_net_schedule_mw",
                                     "original_nyiso_schedule_mw","observed_north_ontario_to_ny_mw","common_replay_qualified_before_source_quality"]
    write_csv(frame.loc[suspect,suspect_columns],"source_quality_suspect_hours.csv")
    gamma=float(json.loads(CONTROL_RECEIPT.read_text())["gamma"])
    frame["delta_ontario_external_generation_model_mw"]=gamma*frame.actual_minus_original_schedule_mw
    frame["delta_required_native_generation_model_mw"]=-gamma*frame.actual_minus_original_schedule_mw
    require(np.max(abs(frame.loc[common,"delta_ontario_external_generation_model_mw"]+frame.loc[common,"delta_required_native_generation_model_mw"]))==0,
            "Proposed external/native balance correction is not conservative")
    write_csv(frame,"external_source_comparison_2025.csv")
    comparisons=[]
    for name,difference in [("IESO_actual_minus_P32_schedule",frame.actual_minus_original_schedule_mw),
                            ("IESO_net_schedule_minus_P32_schedule",frame.source_net_schedule_mw-frame.original_nyiso_schedule_mw)]:
        for cohort,mask in [("source_overlap_before_source_quality",frame.coverage_qualified & frame.original_schedule_qualified),
                            ("source_overlap_quality_qualified",frame.source_quality_qualified & frame.original_schedule_qualified),
                            ("common_replay_before_source_quality",common_before_quality),("common_replay_quality_qualified",common)]:
            comparisons.append(dict(quantity=name,cohort=cohort,**summarize(difference[mask])))
    write_csv(pd.DataFrame(comparisons),"external_quantity_comparison.csv")
    write_csv(pd.DataFrame(annual_summary),"annual_external_summary.csv")
    timing=[]
    for lag in [-1,0,1]:
        shifted=frame.source_net_schedule_mw.shift(lag)
        ok=frame.original_schedule_qualified & shifted.notna()
        timing.append(dict(shift_hours=lag,documented_alignment=lag==0,**summarize(shifted[ok]-frame.loc[ok,"original_nyiso_schedule_mw"])))
    write_csv(pd.DataFrame(timing),"external_schedule_timing_sanity.csv")
    require(all(sha(ROOT/p)==value for p,value in frozen.items()),"A frozen input was changed")
    quality_receipt=dict(status="suspect_source_hours_quarantined_without_changing_reported_actuals",created_utc=stamp(),year=2025,
        quality_child_path=(OUT/"hourly_exchange_quality.csv").relative_to(ROOT).as_posix(),
        quality_child_sha256=sha(OUT/"hourly_exchange_quality.csv"),
        original_csv_path=(OUT/"hourly_actual_exchange.csv").relative_to(ROOT).as_posix(),
        original_csv_sha256=sha(OUT/"hourly_actual_exchange.csv"),
        actual_input_sha256=sha(OUT/"hourly_actual_exchange.csv"),
        original_csv_preserved=True,raw_reported_values_preserved=True,
        source_finite_reported_hours=int(frame.coverage_qualified.sum()),source_quality_qualified_hours=int(frame.source_quality_qualified.sum()),
        suspect_count=int(suspect.sum()),suspect_hours_in_common_cohort=int((suspect & common_before_quality).sum()),
        common_replay_hours_before_source_quality=int(common_before_quality.sum()),common_replay_hours=int(common.sum()),
        predicate="All 14 intertie Flow columns AND Total Flow equal literal zero, with finite nonzero directional schedules; flag the hour as suspect.",
        zero_policy="A NEW-YORK zero alone remains eligible. This predicate quarantines only the report-wide signature; values are not clipped, imputed, interpolated or rewritten.",
        interpretation="Suspected report-wide actual-data defect; the annual source has no native meter-quality flag, so the underlying cause is not conclusively established.",
        external_corroboration=dict(source=P34.relative_to(ROOT).as_posix(),sha256=sha(P34),quantity="P34 PS33 plus PS34 northern Ontario-to-NewYork flow",
                                    nonzero_at_all_six_suspect_hours=bool(frame.loc[suspect,"observed_north_ontario_to_ny_mw"].ne(0).all()),
                                    role="Independent external-boundary sanity check only; not used to select the quality predicate."),
        internal_interface_observations_consumed=False,quality_predicate_fitted_to_internal_flows=False,
        audit_script_path=Path(__file__).relative_to(ROOT).as_posix(),audit_script_sha256=sha(Path(__file__)),
        raw_sources=[dict(path=(RAW/name).relative_to(ROOT).as_posix(),sha256=sha(RAW/name)) for name in
                     ["PUB_IntertieScheduleFlowYear_2025.csv","PUB_IntertieScheduleFlowYear_2025_v394.csv"]],
        versioned_and_canonical_source_byte_identical=True,
        suspect_rows_csv=(OUT/"source_quality_suspect_hours.csv").relative_to(ROOT).as_posix(),
        suspect_rows_sha256=sha(OUT/"source_quality_suspect_hours.csv"),
        excluded_hour_indices=frame.loc[suspect,"hour_index"].astype(int).tolist(),
        excluded_timestamps_utc=frame.loc[suspect,"timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ").tolist())
    (OUT/"source_quality_receipt.json").write_text(json.dumps(quality_receipt,indent=2)+"\n",encoding="utf-8")
    # Literal source facts; the operator-report conventions fix the model basis.
    # DOE TableB.2 is used only to corroborate the direction, not its forecasts.
    evidence=[dict(id="IESO_schema",url=receipt_specs[-1][1],local_path=(RAW/receipt_specs[-1][0]).relative_to(ROOT).as_posix(),
                    finding="IntertieZone is a collection of tielines betweenOntario and neighbouring jurisdiction; Actual Flow is activepowerMW; Hour is hour-ending1..24."),
              dict(id="IESO_stylesheet",url=receipt_specs[-2][1],local_path=(RAW/receipt_specs[-2][0]).relative_to(ROOT).as_posix(),
                    finding="Hour1 spans00:00–01:00EST and eachtrade day is midnightEST to nextmidnightEST. Net schedule=Export−Import."),
              dict(id="IESO_data_directory",url="https://www.ieso.ca/power-data/data-directory",
                    finding="Yearly CSV supplies historical report; actual power flows are operational-meter observations, distinct from scheduled transactions."),
              dict(id="DOE_report_sign",url=DOE_URL,local_path=(RAW/"DOE2025_intertie_sign_source.pdf").relative_to(ROOT).as_posix(),
                    document_page="B-4",container_PDF_page=151,table="B.2",
                    finding="Explicitly identifies positive IESO Ontario–NY flow as Ontario exporting toNY and negative flow asOntario importing. Cited only for this source convention."),
              dict(id="IESO_border_corridors",url="https://ieso.ca/-/media/Files/IESO/Document-Library/planning-forecasts/reliability-outlook/TTCMethodology.pdf",sections="5.4 and5.5",
                    finding="NewYorkNiagara andNewYorkStLawrence arethetwoOntario–NewYork interconnectioncorridors. AnnualNEW-YORKzone isaggregate; noindividualNiagara circuitmeasurements present.")]
    summary=dict(status="source_basis_verified_actual_hourly_external_exchange_ready",created_utc=stamp(),year=2025,
        source_zone="NEW-YORK",source_actual_field="Flow",actual_units="MW_hourly_average",source_net_schedule="Exp_minus_Imp",
        positive_direction="Ontario_to_NewYork",source_time_basis="fixed_EST_UTCminus5_hour_ending;HE1starts00EST",
        source_sign_or_timing_fitted_to_internal_flows=False,internal_interface_observations_consumed=False,
        interval_axis_matches_frozen_2025_UTC_axis=True,finite_reported_actual_hours=int(frame.coverage_qualified.sum()),
        actual_qualified_hours=int(frame.source_quality_qualified.sum()),
        original_schedule_qualified_hours=int(frame.original_schedule_qualified.sum()),common_replay_hours_before_source_quality=int(common_before_quality.sum()),
        common_replay_hours=int(common.sum()),
        coverage_flag_meaning="published_hourly_value_present_and_finite_only; must additionally require separate source_quality_qualified child; historicalnative5mincoverage_not_asserted",
        source_quality_receipt_path=(OUT/"source_quality_receipt.json").relative_to(ROOT).as_posix(),
        source_quality_receipt_sha256=sha(OUT/"source_quality_receipt.json"),
        source_quality_child_sha256=sha(OUT/"hourly_exchange_quality.csv"),
        source_quality_suspect_hours=int(suspect.sum()),
        missing_policy="NaN preserved; no zero fill,interpolation,clipping or gap unlocking",
        western_exchange_policy="actualNEW-YORKtotal_minus_verified_actualStLawrenceP34sum;derivedwesternaggregate,notdirectNiagaraindividualcircuittelemetry",
        actual_change_implementation="OntarioexternalPG += gamma*(actual−originalschedule), allocated withfrozenregionalshares; requirednativePG -= samegamma*delta; rerunboundedprojectionwithsamepriors/bounds/weights.",
        other_regional_exchange_basis="Otherregionalboundariesretainexistingbasis;thisdoesnotclaimallinternationalboundariesareactualtelemetry.",
        comparisons=comparisons,source_validation=source_validation,annual_source_audits=audits,
        final2025_archive_v394_byte_identical=True,source_evidence=evidence,
        source_receipts=receipts,frozen_inputs=[dict(path=p,sha256=value,unchanged=True) for p,value in frozen.items()],
        actual_input_sha256=sha(OUT/"hourly_actual_exchange.csv"),audit_script_sha256=sha(Path(__file__)),
        limitations=["AnnualCSV doesnotexpose2025nativeintervalcoverage ormeter-qualityflags; allreported hourlyvalues remainliteral.",
                     "Six hours with all14 intertie actuals plusTotalFlow zero andnonzero schedules arequarantined as suspected source defects; cause isnot conclusivelyestablished. RawactualCSV ispreserved andneeds the separatequalitymask.",
                     "NEW-YORKincludesallOntario–NYties. IndividualNiagara/Queenstoncircuitflows arenotidentifiedbythisaggregate; westernresidualinheritsbothoperatorhourlyaggregation conventions andmeterboundary differences.",
                     "2019annualsourcecomparison iswithinIESOfixedESTtables; no positionaljoin tolegacy2019NYISOnaiveaxis isperformed."])
    (OUT/"ontario_audit_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    pd.DataFrame([dict(path=str((RAW/name).relative_to(ROOT)).replace("\\","/"),url=url,sha256=sha(RAW/name)) for name,url in receipt_specs]).to_csv(OUT/"source_manifest.csv",index=False,lineterminator="\n")
    print(json.dumps({k:summary[k] for k in ["status","actual_qualified_hours","original_schedule_qualified_hours","common_replay_hours","actual_input_sha256"]},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--offline",action="store_true")
    build(parser.parse_args().offline)
