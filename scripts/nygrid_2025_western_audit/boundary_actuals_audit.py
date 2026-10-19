"""Audit 2025 NYIS-reported EIA-930 physical boundary exchanges.

The source fixes sign and clock: NYIS-reported positive values leave New York;
UTC period labels are hour ending. Negate values and subtract one hour to obtain
import-positive hourly-average MW on the frozen model's hour-start axis. API
MWh values cover exactly one hour, so MWh / 1h is numerically the same MW.

No internal interface measurements, numerical fits or dispatch outputs are read.
Only new boundary_actuals evidence is written. Existing schedules and Ontario
deliverables are preserved. This is source preparation, not a dispatch rebuild.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import gzip
import json
from pathlib import Path
import urllib.parse
import urllib.request
import urllib.error

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_western_audit/boundary_actuals"
RAW = OUT / "raw"
ONTARIO = ROOT / "output/nygrid_2025_western_audit/ontario"
HOURS = ROOT / "output/nygrid_2025_inputs/load_source/hour_catalog.csv"
P32 = ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv"
P34 = ROOT / "output/nygrid_2025_par_controls/controls/hourly_controls.csv"
BASE = "https://api.eia.gov/v2/electricity/rto/"
DOCS = "https://www.eia.gov/survey/form/eia_930/instructions.pdf"
BULK_BASE = "https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/"
START, END = "2025-01-01T06", "2026-01-01T05"
REGIONS = {"ISONE": "ISNE", "ONTARIO": "IESO", "PJM": "PJM", "HQ": "HQT"}
CHANNELS = {
    "ISONE": ["SCH - NE - NY", "SCH - NPX_1385", "SCH - NPX_CSC"],
    "ONTARIO": ["SCH - OH - NY"],
    "PJM": ["SCH - PJ - NY", "SCH - PJM_HTP", "SCH - PJM_NEPTUNE", "SCH - PJM_VFT"],
    "HQ": ["SCH - HQ - NY", "SCH - HQ_CEDARS"],
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def acquire(name, url, offline=False):
    path = RAW / name
    receipt = path.with_suffix(path.suffix + ".receipt.json")
    if path.exists():
        require(receipt.exists(), f"Missing cached receipt: {path}")
        record = json.loads(receipt.read_text())
        require(record["url"] == url and record["sha256"] == sha(path), f"Cached source changed: {path}")
        return record
    require(not offline, f"Missing source in offline mode: {path}")
    request = urllib.request.Request(url, headers={"User-Agent": "NPCC-physical-boundary-audit/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=50) as response:
            data = response.read()
            record = dict(file=name, url=url, http_status=response.status, retrieved_utc=stamp(),
                          bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                          content_type=response.headers.get("Content-Type", ""),
                          http_last_modified=response.headers.get("Last-Modified", ""))
    except urllib.error.HTTPError as error:
        failure = dict(status="source_acquisition_incomplete", http_status=error.code, failed_file=name,
                       url=url, observed_utc=stamp(), response_body=error.read().decode("utf-8", errors="replace"),
                       response_headers=dict(error.headers), cached_successful_pages_preserved=True)
        (OUT/"acquisition_failure.json").write_text(json.dumps(failure, indent=2)+"\n", encoding="utf-8")
        print(json.dumps(failure, indent=2), flush=True)
        raise
    # Do not replace an existing receipt or response. A failed API call leaves
    # prior successful pages available for a later explicit/offline resume.
    path.write_bytes(data)
    receipt.write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
    print(f"Acquired {name}: HTTP {record['http_status']}, {len(data)} bytes", flush=True)
    return record


def api_url(route, extra):
    params = {"api_key": "DEMO_KEY", "frequency": "hourly", "data[0]": "value",
              "start": START, "end": END, "length": "5000",
              "sort[0][column]": "period", "sort[0][direction]": "asc"}
    params.update(extra)
    return BASE + route + "/data/?" + urllib.parse.urlencode(params)


def paged(route, prefix, params, expected, offline):
    tables, receipts = [], []
    for offset in range(0, expected, 5000):
        url = api_url(route, dict(params, offset=str(offset)))
        name = f"{prefix}_{offset:05d}.json"
        receipts.append(acquire(name, url, offline))
        payload = json.loads((RAW/name).read_text())
        require("response" in payload and "error" not in payload, f"EIA API error in {name}")
        result = payload["response"]
        require(int(result["total"]) == expected, f"Unexpected EIA source total: {result.get('total')}")
        require(result["frequency"] == "hourly", "Source API frequency mismatch")
        require(len(result["data"]) == min(5000, expected-offset), f"Truncated API page: {name}")
        tables.append(pd.DataFrame(result["data"]))
    return pd.concat(tables, ignore_index=True), receipts


def acquire_bulk(name, offline=False):
    """Lossless gzip archive of a published bulk CSV, with both byte hashes."""
    path = RAW/(name+".gz")
    receipt = path.with_suffix(path.suffix+".receipt.json")
    url = BULK_BASE+name
    if path.exists():
        record = json.loads(receipt.read_text())
        require(record["url"] == url and record["sha256"] == sha(path), "Cached bulk archive changed")
        with gzip.open(path, "rb") as source:
            decoded_sha = hashlib.file_digest(source, "sha256").hexdigest()
        require(decoded_sha == record["original_csv_sha256"], "Bulk decompression hash differs")
        return record
    require(not offline, f"Missing bulk CSV: {name}")
    original_hash = hashlib.sha256(); byte_count = 0
    partial = path.with_suffix(path.suffix+".part")
    with urllib.request.urlopen(url, timeout=50) as response:
        record = dict(file=path.name, url=url, http_status=response.status, retrieved_utc=stamp(),
                      content_type=response.headers.get("Content-Type", ""),
                      http_last_modified=response.headers.get("Last-Modified", ""),
                      storage="lossless_gzip_of_unmodified_published_CSV_bytes")
        with partial.open("wb") as disk:
            with gzip.GzipFile(filename="", mode="wb", fileobj=disk, mtime=0, compresslevel=6) as target:
                while chunk := response.read(1024*1024):
                    original_hash.update(chunk); byte_count += len(chunk); target.write(chunk)
    partial.rename(path)
    record.update(bytes=path.stat().st_size, sha256=sha(path), original_csv_bytes=byte_count,
                  original_csv_sha256=original_hash.hexdigest())
    receipt.write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
    print(f"Acquired bulk {name}: {byte_count} original bytes, {record['bytes']} gzip bytes", flush=True)
    return record


def bulk_tables(offline):
    index_receipt = acquire("EIA930_File_List_Meta.csv", BULK_BASE+"EIA930_File_List_Meta.csv", offline)
    index_text = (RAW/"EIA930_File_List_Meta.csv").read_text()
    receipts, native_parts, total_parts = [index_receipt], [], []
    for half in ["Jan_Jun", "Jul_Dec"]:
        for kind in ["INTERCHANGE", "BALANCE"]:
            name = f"EIA930_{kind}_2025_{half}.csv"
            require(name in index_text, "Bulk source not listed in official published file index")
            receipts.append(acquire_bulk(name, offline))
            columns = ["Balancing Authority", "UTC Time at End of Hour"]
            columns += (["Directly Interconnected Balancing Authority", "Interchange (MW)"] if kind=="INTERCHANGE"
                        else ["Total Interchange (MW)", "Sum(Valid DIBAs) (MW)"])
            for chunk in pd.read_csv(RAW/(name+".gz"), usecols=columns, chunksize=100000):
                selected = chunk.loc[chunk["Balancing Authority"].eq("NYIS")].copy()
                if selected.empty:
                    continue
                ending = pd.to_datetime(selected["UTC Time at End of Hour"], format="%m/%d/%Y %I:%M:%S %p", utc=True)
                selected["period"] = ending.dt.strftime("%Y-%m-%dT%H")
                selected["value-units"] = "megawatthours"
                # The CSV explicitly labels average MW. Over exactly one hour
                # it is numerically equivalent to the API's MWh; preserve this
                # normalization and verify exact cached API overlap below.
                if kind=="INTERCHANGE":
                    selected = selected.rename(columns={"Balancing Authority":"fromba", "Directly Interconnected Balancing Authority":"toba", "Interchange (MW)":"value"})
                    native_parts.append(selected[["period", "fromba", "toba", "value", "value-units"]])
                else:
                    selected = selected.rename(columns={"Balancing Authority":"respondent", "Total Interchange (MW)":"value"})
                    selected["type"] = "TI"
                    total_parts.append(selected[["period", "respondent", "type", "value", "value-units", "Sum(Valid DIBAs) (MW)"]])
    native = pd.concat(native_parts, ignore_index=True)
    total = pd.concat(total_parts, ignore_index=True)
    require(len(native)==35040 and len(total)==8760, "Bulk source year does not cover expected local-year hours")
    require(native.period.between(START, END).all() and total.period.between(START, END).all(), "Bulk source period outside model year")
    cached_api, api_receipts = [], []
    for path in sorted(RAW.glob("NYIS_interchange_2025_*.json")):
        if path.name.endswith(".receipt.json"):
            continue
        r = json.loads(path.with_suffix(path.suffix+".receipt.json").read_text())
        require(r["sha256"]==sha(path), "Cached API crosscheck response changed")
        api_receipts.append(r)
        cached_api.append(pd.DataFrame(json.loads(path.read_text())["response"]["data"]))
    require(len(cached_api)>0, "Bulk mode requires independently retrieved API overlap")
    api = pd.concat(cached_api, ignore_index=True)
    require(not api.duplicated(["period", "fromba", "toba"]).any(), "Cached API overlap duplicated")
    overlap = native.merge(api, on=["period", "fromba", "toba"], suffixes=("_bulk", "_api"), validate="one_to_one")
    require(len(overlap)==len(api), "Some cached API records are absent from bulk")
    a = pd.to_numeric(overlap.value_bulk, errors="raise").to_numpy(float)
    b = pd.to_numeric(overlap.value_api, errors="raise").to_numpy(float)
    require(np.array_equal(a, b, equal_nan=True), "Bulk and API values disagree")
    return native, total, receipts+api_receipts, dict(cached_API_pages=len(cached_api), cached_API_records=len(api),
        exact_value_equality=True, maximum_absolute_difference_mw=float(np.nanmax(abs(a-b))),
        metadata_units_binding="Published CSV explicitly labels Interchange (MW); one-hour API MWh values agree exactly.")


def counterpart_and_freeze_checks(frame, compare):
    """Corroborate simultaneous frozen NYIS reports using external operators."""
    parts=[]
    columns=["Balancing Authority", "Directly Interconnected Balancing Authority", "Interchange (MW)", "UTC Time at End of Hour"]
    for half in ["Jan_Jun", "Jul_Dec"]:
        for chunk in pd.read_csv(RAW/f"EIA930_INTERCHANGE_2025_{half}.csv.gz", usecols=columns, chunksize=100000):
            selected=chunk.loc[chunk["Directly Interconnected Balancing Authority"].eq("NYIS")].copy()
            if not selected.empty:
                parts.append(selected)
    peers=pd.concat(parts, ignore_index=True)
    require(set(peers["Balancing Authority"])=={"ISNE", "PJM"}, "Unexpected counterpart reporting scope")
    peers["timestamp_utc"]=pd.to_datetime(peers["UTC Time at End of Hour"], format="%m/%d/%Y %I:%M:%S %p", utc=True)-pd.Timedelta(hours=1)
    require(not peers.duplicated(["timestamp_utc", "Balancing Authority"]).any(), "Counterpart source hour duplicated")
    wide=peers.pivot(index="timestamp_utc", columns="Balancing Authority", values="Interchange (MW)")
    # Counterparty positive FLOW leaves the neighbor and therefore enters NY.
    # Canadian BAs are not EIA respondents in these bulk files; use the
    # separately audited original IESO annual source for Ontario corroboration.
    cross=frame[["hour_index", "timestamp_utc"]].merge(wide, on="timestamp_utc", how="left", validate="one_to_one")
    cross=cross.rename(columns={"ISNE":"ISNE_reported_import_to_NY_mw", "PJM":"PJM_reported_import_to_NY_mw"})
    cross["IESO_reported_import_to_NY_mw"]=compare.actual_ontario_to_ny_mw
    cross["IESO_source_quality_qualified"]=compare.source_quality_qualified
    for region,code in [("ISONE","ISNE"),("PJM","PJM")]:
        cross[f"NYIS_reported_{region}_import_mw"]=frame[f"{region}_actual_import_mw"]
        cross[f"NYIS_minus_{code}_reported_import_mw"]=frame[f"{region}_actual_import_mw"]-cross[f"{code}_reported_import_to_NY_mw"]
    cross["NYIS_reported_ONTARIO_import_mw"]=frame.ONTARIO_actual_import_mw
    cross["NYIS_minus_IESO_reported_import_mw"]=frame.ONTARIO_actual_import_mw-cross.IESO_reported_import_to_NY_mw
    actual_cols=[f"{r}_actual_import_mw" for r in REGIONS]
    groups=frame[actual_cols].ne(frame[actual_cols].shift()).any(axis=1).cumsum()
    frozen=pd.Series(False, index=frame.index)
    run_lengths=groups.map(groups.value_counts()).astype(int)
    runs=[]
    for group, indices in frame.groupby(groups).groups.items():
        if len(indices)<3:
            continue
        idx=list(indices)
        ieso=cross.loc[idx,"IESO_reported_import_to_NY_mw"]
        isne=cross.loc[idx,"ISNE_reported_import_to_NY_mw"]
        full=np.isfinite(ieso).all() and np.isfinite(isne).all() and cross.loc[idx,"IESO_source_quality_qualified"].all()
        # Two independent rounded operator quantities change by more than2MW
        # while the complete four-component NYIS vector remains bit-identical.
        # This categorical source-freeze signature does not use NYISO internal
        # interface errors, a fitted tolerance, or neighboring transition hours.
        corroborated=bool(full and np.ptp(ieso.to_numpy())>2 and np.ptp(isne.to_numpy())>2)
        if corroborated:
            frozen.loc[idx]=True
        runs.append(dict(run_start_hour_index=int(frame.loc[idx[0],"hour_index"]),
                         run_end_hour_index=int(frame.loc[idx[-1],"hour_index"]),
                         start_utc=frame.loc[idx[0],"timestamp_utc"], end_utc=frame.loc[idx[-1],"timestamp_utc"],
                         consecutive_identical_hours=len(idx), independent_IESO_range_mw=float(np.ptp(ieso.to_numpy())),
                         independent_ISNE_range_mw=float(np.ptp(isne.to_numpy())),
                         independently_corroborated=corroborated,
                         **{c:float(frame.loc[idx[0],c]) for c in actual_cols}))
    frame["identical_four_vector_run_length"]=run_lengths
    frame["corroborated_frozen_report"]=frozen
    cross["identical_four_vector_run_length"]=run_lengths
    cross["corroborated_frozen_report"]=frozen
    write_csv(cross,"counterparty_actual_comparison.csv")
    write_csv(pd.DataFrame(runs),"frozen_report_runs.csv")
    return frozen,dict(rule="Maximal run of at least three identical complete four-region NYIS actual vectors, corroborated by independently qualified IESO and ISNE actual ranges greater than2MW. Quarantine the whole run, including its first hour.",
                      repeated_runs_at_least_three_hours=len(runs), quarantined_hours=int(frozen.sum()),
                      excluded_hour_indices=frame.loc[frozen,"hour_index"].astype(int).tolist(),
                      corroboration_uses_internal_interface_observations=False,
                      adjacent_transition_hours_automatically_excluded=False,
                      counterparty_differences={code:stats(cross[f"NYIS_minus_{code}_reported_import_mw"]) for code in ["ISNE","PJM"]},
                      PJM_reciprocity_limitation="PJM-counterparty values show substantial disagreement with NYIS; reporting-scope/counterparty consistency is unestablished. They are diagnostic only, with no averaging, fitted shift or eligibility exclusions.")


def write_csv(frame, name, protect_existing=False):
    path = OUT/name
    data = frame.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%SZ", lineterminator="\n").encode()
    if protect_existing and path.exists():
        require(path.read_bytes() == data, f"Delivered numeric input would change: {name}")
    else:
        path.write_bytes(data)


def stats(series):
    values = np.asarray(series, float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return dict(hours=0, mean=None, mae=None, rmse=None, minimum=None, maximum=None)
    return dict(hours=len(values), mean=float(values.mean()), mae=float(abs(values).mean()),
                rmse=float(np.sqrt(np.mean(values**2))), minimum=float(values.min()), maximum=float(values.max()))


def build(offline=False):
    OUT.mkdir(parents=True, exist_ok=True); RAW.mkdir(parents=True, exist_ok=True)
    protected = [HOURS, P32, P34] + sorted(p for p in ONTARIO.rglob("*") if p.is_file())
    frozen = {p.relative_to(ROOT).as_posix(): sha(p) for p in protected}
    receipts = [acquire("EIA930_instructions.pdf", DOCS, offline)]
    receipts.append(acquire("interchange_route_metadata.json", BASE+"interchange-data/?api_key=DEMO_KEY", offline))
    metadata = json.loads((RAW/"interchange_route_metadata.json").read_text())["response"]
    require(metadata["id"] == "interchange-data", "Unexpected source route")
    require(metadata["data"]["value"]["units"] == "megawatthours", "Unknown interchange source units")
    require(any(x["id"] == "hourly" and x["alias"] == "hourly (UTC)" for x in metadata["frequency"]),
            "EIA source lacks UTC hourly frequency metadata")
    # fromba is the respondent, not a requirement that net flow be outgoing.
    # No toba filter is applied: the complete NYIS neighbor set is retained.
    native, total, data_receipts, api_overlap = bulk_tables(offline)
    receipts += data_receipts
    require(native.fromba.eq("NYIS").all(), "Source contains another reporting perspective")
    require(set(native.toba) == set(REGIONS.values()), "NYIS neighbor scope differs from four audited regions")
    require(native["value-units"].eq("megawatthours").all(), "Unexpected source unit label")
    require(not native.duplicated(["period", "fromba", "toba"]).any(), "Duplicated bilateral record")
    native["value"] = pd.to_numeric(native.value, errors="raise")
    native["timestamp_utc"] = pd.to_datetime(native.period, utc=True)-pd.Timedelta(hours=1)
    native["actual_import_mw"] = -native.value / 1.0
    hours = pd.read_csv(HOURS, usecols=["hour_index", "timestamp_utc"])
    hours["timestamp_utc"] = pd.to_datetime(hours.timestamp_utc, utc=True)
    require(len(hours)==8760 and hours.timestamp_utc.is_unique, "Frozen hour axis malformed")
    require(hours.timestamp_utc.iloc[0] == pd.Timestamp(START, tz="UTC")-pd.Timedelta(hours=1), "EIA first hour does not match")
    require(hours.timestamp_utc.iloc[-1] == pd.Timestamp(END, tz="UTC")-pd.Timedelta(hours=1), "EIA last hour does not match")
    require(native.groupby("toba").size().eq(8760).all(), "Incomplete region/hour grid")
    wide = native.pivot(index="timestamp_utc", columns="toba", values="actual_import_mw")
    require(wide.index.equals(pd.DatetimeIndex(hours.timestamp_utc)), "EIA physical axis differs from frozen axis")
    require(total.respondent.eq("NYIS").all() and total.type.eq("TI").all(), "Wrong total interchange source")
    require(total["value-units"].eq("megawatthours").all(), "Unexpected total interchange units")
    require(not total.period.duplicated().any(), "Duplicated total interchange hour")
    total["timestamp_utc"] = pd.to_datetime(total.period, utc=True)-pd.Timedelta(hours=1)
    total["NYIS_reported_total_actual_import_mw"] = -pd.to_numeric(total.value, errors="raise")
    total = total.sort_values("timestamp_utc").reset_index(drop=True)
    require(total.timestamp_utc.equals(hours.timestamp_utc), "Total interchange physical axis differs")
    frame = hours.copy()
    for region, code in REGIONS.items():
        frame[f"{region}_actual_import_mw"] = wide[code].to_numpy()
    schedules = pd.read_csv(P32, usecols=["timestamp_utc"]+[c for items in CHANNELS.values() for c in items])
    schedules["timestamp_utc"] = pd.to_datetime(schedules.timestamp_utc, utc=True)
    compare = frame.merge(schedules, on="timestamp_utc", validate="one_to_one")
    require(len(compare)==8760 and compare.timestamp_utc.equals(frame.timestamp_utc), "P32 physical axis differs")
    for region, columns in CHANNELS.items():
        compare[f"{region}_original_schedule_import_mw"] = compare[columns].sum(axis=1, min_count=len(columns))
        compare[f"{region}_actual_minus_schedule_mw"] = compare[f"{region}_actual_import_mw"]-compare[f"{region}_original_schedule_import_mw"]
    # Preserve all original channel values. These four derived DC schedules
    # reproduce the frozen model's link decomposition and are not actual meters.
    compare["original_DC1_NPX1385_plus_CSC_schedule_mw"] = compare[["SCH - NPX_1385", "SCH - NPX_CSC"]].sum(axis=1, min_count=2)
    compare["original_DC2_NEPTUNE_schedule_mw"] = compare["SCH - PJM_NEPTUNE"]
    compare["original_DC3_HTP_schedule_mw"] = compare["SCH - PJM_HTP"]
    compare["original_DC4_VFT_schedule_mw"] = compare["SCH - PJM_VFT"]
    o = pd.read_csv(ONTARIO/"hourly_actual_exchange.csv", usecols=["timestamp_utc", "actual_ontario_to_ny_mw"])
    oq = pd.read_csv(ONTARIO/"hourly_exchange_quality.csv", usecols=["timestamp_utc", "source_quality_qualified"])
    o = o.merge(oq, on="timestamp_utc", validate="one_to_one")
    o["timestamp_utc"] = pd.to_datetime(o.timestamp_utc, utc=True)
    compare = compare.merge(o, on="timestamp_utc", validate="one_to_one")
    frozen_report, freeze_review = counterpart_and_freeze_checks(frame, compare)
    actual_cols = [f"{r}_actual_import_mw" for r in REGIONS]
    schedule_cols = [f"{r}_original_schedule_import_mw" for r in REGIONS]
    frame["all_four_actual_zero"] = frame[actual_cols].eq(0).all(axis=1)
    schedules_nonzero = compare[schedule_cols].ne(0).any(axis=1) & np.isfinite(compare[schedule_cols]).all(axis=1)
    independent_total_nonzero = total.NYIS_reported_total_actual_import_mw.abs().gt(2.5) & np.isfinite(total.NYIS_reported_total_actual_import_mw)
    suspect_zero = frame.all_four_actual_zero & independent_total_nonzero
    frame["schedules_nonzero"] = schedules_nonzero
    frame["reported_total_nonzero_beyond_rounding"] = independent_total_nonzero
    for region in REGIONS:
        frame[f"{region}_source_qualified"] = np.isfinite(frame[f"{region}_actual_import_mw"]) & ~suspect_zero & ~frozen_report
    flags = [f"{r}_source_qualified" for r in REGIONS]
    frame["coverage_qualified"] = frame[flags].all(axis=1)
    frame["quality_reason"] = np.select([~np.isfinite(frame[actual_cols]).all(axis=1), suspect_zero, frozen_report],
        ["missing_or_nonfinite_bilateral_actual", "suspect_all_four_actual_zero_with_nonzero_reported_total", "corroborated_frozen_four_region_report"],
        default="finite_bilateral_actual_without_categorical_source_defect")
    primary_cols = ["hour_index", "timestamp_utc"]+actual_cols+["coverage_qualified"]+flags
    write_csv(frame[primary_cols], "hourly_regional_actuals.csv", protect_existing=True)
    write_csv(frame[["hour_index", "timestamp_utc", "all_four_actual_zero", "schedules_nonzero",
                     "reported_total_nonzero_beyond_rounding", "identical_four_vector_run_length",
                     "corroborated_frozen_report", "quality_reason"]], "hourly_source_quality.csv")
    for c in flags+["coverage_qualified", "quality_reason"]:
        compare[c] = frame[c]
    compare["sum_all_four_actual_import_mw"] = frame[actual_cols].sum(axis=1, min_count=4)
    compare["sum_all_four_original_schedule_import_mw"] = compare[schedule_cols].sum(axis=1, min_count=4)
    compare["sum_all_four_actual_minus_schedule_mw"] = compare.sum_all_four_actual_import_mw-compare.sum_all_four_original_schedule_import_mw
    compare["sum_other_three_actual_minus_schedule_mw"] = compare[[f"{r}_actual_minus_schedule_mw" for r in ["ISONE", "PJM", "HQ"]]].sum(axis=1, min_count=3)
    controls = pd.read_csv(P34, usecols=["timestamp_utc", "observed_replay_qualified"])
    controls["timestamp_utc"] = pd.to_datetime(controls.timestamp_utc, utc=True)
    compare = compare.merge(controls, on="timestamp_utc", validate="one_to_one")
    compare["original_schedules_qualified"] = np.isfinite(compare[schedule_cols]).all(axis=1)
    compare["common_replay_qualified"] = compare.coverage_qualified & compare.original_schedules_qualified & compare.observed_replay_qualified.astype(str).str.lower().eq("true")
    # Independent Ontario-operator source is compared only where its own
    # separate quality mask passes. It does not replace NYIS measurements.
    compare["EIA_minus_IESO_actual_ontario_mw"] = compare.ONTARIO_actual_import_mw-compare.actual_ontario_to_ny_mw
    compare["common_with_ontario_only_scenario"] = compare.common_replay_qualified & compare.source_quality_qualified
    write_csv(compare, "external_schedule_actual_comparison.csv")
    # Source-quality sum-check: NYIS-reported total net interchange is a
    # separate EIA-930 quantity, not a NYISO internal-interface observation.
    sumcheck = compare[["hour_index", "timestamp_utc", "sum_all_four_actual_import_mw"]].merge(
        total[["timestamp_utc", "NYIS_reported_total_actual_import_mw"]], on="timestamp_utc", validate="one_to_one")
    require(len(sumcheck)==8760, "Total interchange does not cover the full model axis")
    sumcheck["bilateral_sum_minus_reported_total_mw"] = sumcheck.sum_all_four_actual_import_mw-sumcheck.NYIS_reported_total_actual_import_mw
    write_csv(sumcheck, "reported_total_sum_check.csv")
    comparisons = []
    for population, mask in [("finite_schedule_overlap", compare.coverage_qualified & compare.original_schedules_qualified),
                             ("common_replay", compare.common_replay_qualified),
                             ("common_with_ontario_only", compare.common_with_ontario_only_scenario)]:
        for r in REGIONS:
            comparisons.append(dict(population=population, quantity=f"{r}_actual_minus_schedule", **stats(compare.loc[mask, f"{r}_actual_minus_schedule_mw"])))
        for col in ["sum_other_three_actual_minus_schedule_mw", "sum_all_four_actual_minus_schedule_mw"]:
            comparisons.append(dict(population=population, quantity=col, **stats(compare.loc[mask, col])))
    write_csv(pd.DataFrame(comparisons), "annual_external_difference_summary.csv")
    pair_mask = compare.common_replay_qualified & compare.source_quality_qualified
    qualified = compare.common_replay_qualified
    x, other = compare.loc[qualified, "ONTARIO_actual_minus_schedule_mw"], compare.loc[qualified, "sum_other_three_actual_minus_schedule_mw"]
    zero_rows = []
    for r in REGIONS:
        zero_rows.append(dict(region=r, exact_zero_hours=int(frame[f"{r}_actual_import_mw"].eq(0).sum()),
                              finite_hours=int(np.isfinite(frame[f"{r}_actual_import_mw"]).sum()),
                              qualified_hours=int(frame[f"{r}_source_qualified"].sum())))
    require(all(sha(ROOT/p)==v for p,v in frozen.items()), "A preserved input or Ontario artifact changed")
    receipt = dict(status="complete_source_audit_with_categorical_quality_screen", created_utc=stamp(), year=2025,
        source_mode="official_EIA_six_month_bulk_CSV_with_cached_API_crosscheck",
        bulk_source_receipts=[r for r in receipts if r.get("storage")=="lossless_gzip_of_unmodified_published_CSV_bytes"],
        api_overlap_verification=api_overlap,
        API_acquisition_limit="DEMO_KEY returned HTTP429 after five bilateral pages; completed from separately published official bulk CSVs without further API calls.",
        reporting_balancing_authority="NYIS", neighboring_BA_codes=REGIONS, source_record_count=len(native),
        expected_physical_hours=8760, unique_region_hour_grid=True, no_neighbor_filter_applied=True,
        full_NYIS_neighbor_set=list(sorted(native.toba.unique())),
        source_units="bulk_CSV_MW_hourly_average_with_API_one_hour_MWh_crosscheck",
        bulk_source_units="MW_hourly_average", API_source_units="megawatthours_per_one_hour_interval",
        output_units="MW_hourly_average_public_unscaled", positive_direction="neighbor_to_NewYork_import",
        sign_transform="output_import_mw = -bulk_Interchange_MW = -NYIS_API_reported_value_MWh / 1_hour",
        time_transform="timestamp_utc_start = bulk_UTC_Time_at_End_of_Hour - 1_hour = EIA_API_period_utc_hour_ending - 1_hour",
        first_source_period=START, last_source_period=END, source_sign_or_clock_fitted=False,
        physical_axis_matches_frozen_2025_UTC_axis=True, internal_interface_observations_consumed=False,
        no_dispatch_or_inventory_ND_replacement=True, original_schedule_and_DC_values_preserved=True,
        coverage_qualified_hours=int(frame.coverage_qualified.sum()),
        original_schedule_qualified_hours=int(compare.original_schedules_qualified.sum()),
        common_replay_hours=int(qualified.sum()), common_with_ontario_only_hours=int(compare.common_with_ontario_only_scenario.sum()),
        region_zero_and_finite_checks=zero_rows, all_four_actual_zero_hours=int(frame.all_four_actual_zero.sum()),
        suspect_all_four_zero_with_nonzero_reported_total_hours=int(suspect_zero.sum()),
        frozen_report_quality_review=freeze_review,
        quality_evidence_files=[dict(path=(OUT/name).relative_to(ROOT).as_posix(), sha256=sha(OUT/name)) for name in
                                ["hourly_source_quality.csv", "frozen_report_runs.csv", "counterparty_actual_comparison.csv", "reported_total_sum_check.csv"]],
        initial_unpromoted_finite_only_candidate=dict(path=(OUT/"hourly_regional_actuals_initial_finite_only.csv").relative_to(ROOT).as_posix(),
                                                    sha256=sha(OUT/"hourly_regional_actuals_initial_finite_only.csv"))
                                                    if (OUT/"hourly_regional_actuals_initial_finite_only.csv").exists() else None,
        zero_policy="Individual zeros retained. All-four actual zero with independent reported total nonzero beyond 2.5MW integer-rounding bound is quarantined; schedules are corroborative only. No clipping or imputation.",
        reported_total_sum_check=stats(sumcheck.bilateral_sum_minus_reported_total_mw),
        total_sum_mismatch_over_integer_rounding_bound_2point5MW_hours=int(sumcheck.bilateral_sum_minus_reported_total_mw.abs().gt(2.5).sum()),
        total_sum_mismatch_over_10MW_hours=int(sumcheck.bilateral_sum_minus_reported_total_mw.abs().gt(10).sum()),
        reported_total_check_policy="Diagnostic consistency check only; EIA permits method differences. No arbitrary total-difference threshold changes eligibility.",
        EIA_vs_independent_IESO_actual_common=stats(compare.loc[pair_mask, "EIA_minus_IESO_actual_ontario_mw"]),
        Ontario_delta_vs_other_three_delta=dict(common_hours=int(qualified.sum()), correlation=float(x.corr(other)),
                                              opposite_sign_hours=int((x*other<0).sum()), same_sign_hours=int((x*other>0).sum())),
        source_proof=[dict(id="EIA930_hour_ending_UTC", source="raw/EIA930_instructions.pdf", PDF_page=3,
                          finding="Hourly integrated values, nearest-integer reporting, UTC hour-ending labels; example EST HE1 maps to 06UTC."),
                      dict(id="EIA930_FLOW_sign", source="raw/EIA930_instructions.pdf", PDF_page=5,
                          finding="FLOW is net metered tie-line flow; positive values leave the reporting balancing authority and negative values enter."),
                      dict(id="EIA930_physical_scope", source="raw/EIA930_instructions.pdf", PDF_page=9,
                          finding="Report physical tie-boundary operations; sums and counterparties should be consistent, with documented reporting-method exceptions."),
                      dict(id="API_hourly_units", source="raw/interchange_route_metadata.json",
                          finding="API hourly frequency is UTC and values are in megawatthours. Divide each one-hour energy quantity by one hour to obtain average MW."),
                      dict(id="EIA_bulk_header_units_and_clock", source="raw/EIA930_INTERCHANGE_2025_Jan_Jun.csv.gz",
                          finding="Published columns explicitly name Interchange (MW) and UTC Time at End of Hour. All cached API values agree exactly with the bulk average MW values.")],
        source_receipts=receipts,
        original_source_hashes=[dict(path=p, sha256=v, unchanged=True) for p,v in frozen.items()],
        actual_input_path=(OUT/"hourly_regional_actuals.csv").relative_to(ROOT).as_posix(),
        actual_input_sha256=sha(OUT/"hourly_regional_actuals.csv"),
        audit_script_path=Path(__file__).relative_to(ROOT).as_posix(), audit_script_sha256=sha(Path(__file__)),
        limitations=["NYIS-reported aggregate regional actuals do not identify individual circuit flows or recover actual native unit dispatch.",
                     "Six externally corroborated simultaneous four-region frozen-report hours are quarantined; adjacent transition hours retain discrepancies and remain uncertain rather than being expanded by a fitted threshold.",
                     "PJM counterpart reciprocity is not established; NYIS is used consistently as the reporting perspective and no counterpart averaging or data-driven clock shifts are applied.",
                     "Existing four DC schedules remain source schedules; matching aggregate regional totals leaves within-region AC/DC partition conditional.",
                     "EIA data are rounded operational reports, may be revised, and can reflect documented physical-boundary reporting agreements.",
                     "The current instructions PDF is the version retrieved with this audit; API raw source and exact transformations are archived.",
                     "No meter-quality metadata are exposed per API observation. Finite and source-wide-zero screening does not prove every observation physically exact."])
    (OUT/"source_audit_receipt.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    pd.DataFrame(receipts).to_csv(OUT/"source_manifest.csv", index=False, lineterminator="\n")
    print(json.dumps({k:receipt[k] for k in ["status", "coverage_qualified_hours", "common_replay_hours", "common_with_ontario_only_hours", "reported_total_sum_check", "EIA_vs_independent_IESO_actual_common", "Ontario_delta_vs_other_three_delta", "actual_input_sha256"]}, indent=2))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    build(parser.parse_args().offline)
