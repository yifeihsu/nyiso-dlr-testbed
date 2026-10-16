"""Reconstruct native generation against all four actual boundary totals.

NYIS-reported physical imports replace all four scheduled regional totals at
once. Frozen per-region external-generator shares, native priors, weights,
bounds, loads, four original DC schedules and P34 controls remain unchanged.
The Ontario-only reconstruction is a separate diagnostic and is never edited.
No internal interface observation is consumed or used to qualify this result.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_western_audit"
BASE = ROOT / "output/nygrid_2025_dispatch/dispatch"
PAR = ROOT / "output/nygrid_2025_par_controls"
SOURCES = OUT / "boundary_actuals"
REVIEW = OUT / "boundary_source_review/independent_boundary_review.json"
REGISTER = ROOT / "output/nygrid_2025_moses_audit/corrected/model_generator_register.csv"
ALLOCATION = ROOT / "output/nygrid_2025_inputs/model/external_generator_allocation.csv"
SCHEDULES = ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv"
REGIONS = {"ISONE": "ISNE", "ONTARIO": "IESO", "PJM": "PJM", "HQ": "HQT"}
CHANNELS = {
    "ISONE": ["SCH - NE - NY", "SCH - NPX_1385", "SCH - NPX_CSC"],
    "ONTARIO": ["SCH - OH - NY"],
    "PJM": ["SCH - PJ - NY", "SCH - PJM_HTP", "SCH - PJM_NEPTUNE", "SCH - PJM_VFT"],
    "HQ": ["SCH - HQ - NY", "SCH - HQ_CEDARS"],
}
FROZEN = {
    BASE / "dispatch.mat": "0599e66f1bce13cbb9204bba74d6578a94dc34bea2ba4c1b56493ea33492707c",
    BASE / "dispatch_bounds.mat": "aea299a79e96a145dcaa25ab66b9118f29e53455e3ac274951d844223c6631ab",
    BASE / "dispatch_priors.mat": "495afac0bf995fc2dd4dcc9b107d272da3352154ae889910b62747fe1edad883",
    REGISTER: "1211d0f632df2ccd6306ce299de5d24644d4d28d0d987af8421c8b7559a01e21",
    ALLOCATION: "471ea55dc77808137342df764e89be6e4cededefdaad798e8687ebbe9ea42615",
    PAR / "controls/inputs.npz": "af93663aac002dc9e0a0c93015930ad597c2a43b2ee8f4dbd00b4e71c8e405f9",
    ROOT / "scripts/nygrid_2025_dispatch/build_dispatch.py": "3250a8f4b5052d97ebe9eee11129570c12b9fe5260b2181ad3add79a418d3f54",
}
TOL = 1e-7
sys.path.insert(0, str(ROOT / "scripts/nygrid_2025_dispatch"))
from build_dispatch import bounded_projection


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def checked_path(value):
    path = Path(value)
    path = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    require(path.is_relative_to(ROOT), "Source dependency escapes the research workspace")
    return path


def check_records(records, required=()):
    require(bool(records), "A required proof manifest is empty")
    paths = [checked_path(r["path"]) for r in records]
    require(len(set(paths)) == len(paths), "Duplicate dependency records")
    require(set(map(checked_path, required)).issubset(paths), "Proof manifest omits required source dependencies")
    for record, path in zip(records, paths):
        require(path.is_file() and sha(path) == record["sha256"], "Source dependency changed: " + str(path.relative_to(ROOT)))
    return paths


def bool_values(values):
    text = pd.Series(values).astype(str).str.lower()
    require(text.isin(["true", "false", "1", "0"]).all(), "Unknown source qualification boolean")
    return text.isin(["true", "1"]).to_numpy()


def close(actual, expected, label, tolerance=TOL, allow_nan=False):
    a, b = np.asarray(actual), np.asarray(expected)
    require(a.shape == b.shape, label + ": shape mismatch")
    require(np.allclose(a, b, atol=tolerance, rtol=0, equal_nan=allow_nan), label + ": value mismatch")


def verify_frozen():
    for path, digest in FROZEN.items():
        require(path.is_file() and sha(path) == digest, "Frozen reconstruction input changed: " + str(path.relative_to(ROOT)))
    groups = {
        ROOT / "output/nygrid_2025_dispatch/delivery_manifest.json": [BASE / "dispatch.mat", BASE / "dispatch_bounds.mat",
            BASE / "dispatch_priors.mat", ROOT / "scripts/nygrid_2025_dispatch/build_dispatch.py"],
        ROOT / "output/nygrid_2025_inputs/delivery_manifest.json": [ALLOCATION, SCHEDULES],
        ROOT / "output/nygrid_2025_moses_audit/delivery_manifest.json": [REGISTER],
        PAR / "delivery_manifest.json": [PAR / "controls/inputs.npz", PAR / "controls/input_receipt.json"],
    }
    paths = list(FROZEN)
    for path, required in groups.items():
        receipt = json.loads(path.read_text())
        records = receipt.get("entries", receipt.get("files", []))
        selected = [r for r in records if checked_path(r["path"]) in required]
        check_records(selected, required)
        paths.extend([path] + required)
    return list(dict.fromkeys(paths))


def original_schedules(times):
    columns = [c for values in CHANNELS.values() for c in values]
    data = pd.read_csv(SCHEDULES, usecols=["timestamp_utc"] + columns)
    require(np.array_equal(data.timestamp_utc.to_numpy(str), times), "Original boundary schedule UTC axis changed")
    # All ten columns are external schedules; no internal interface values read.
    original = np.column_stack([data[CHANNELS[r]].sum(axis=1, min_count=len(CHANNELS[r])).to_numpy(float) for r in REGIONS])
    dc = np.column_stack([data[["SCH - NPX_1385", "SCH - NPX_CSC"]].sum(axis=1, min_count=2),
                          data["SCH - PJM_NEPTUNE"], data["SCH - PJM_HTP"], data["SCH - PJM_VFT"]])
    return data, original, dc


def independent_region_quality(raw_actual, raw_total):
    """A single zero is valid; quarantine only the independent report conflict."""
    raw_actual, raw_total = np.asarray(raw_actual, float), np.asarray(raw_total, float)
    require(raw_actual.ndim == 2 and raw_actual.shape[1] == 4 and raw_total.shape == (len(raw_actual),),
            "Expected four regional observations and one total per physical hour")
    all_zero = np.all(raw_actual == 0, axis=1)
    total_nonzero = np.isfinite(raw_total) & (abs(raw_total) > 2.5)
    suspect = all_zero & total_nonzero
    return np.isfinite(raw_actual) & ~suspect[:, None], all_zero, total_nonzero


def frozen_vector_quality(raw_actual, ieso_actual, isne_actual, ieso_qualified):
    """Quarantine maximal frozen vectors only with two independent witnesses."""
    a = np.asarray(raw_actual, float)
    ieso, isne, iq = np.asarray(ieso_actual, float), np.asarray(isne_actual, float), np.asarray(ieso_qualified, bool)
    require(a.ndim == 2 and a.shape[1] == 4 and all(v.shape == (len(a),) for v in [ieso, isne, iq]),
            "Frozen-vector counterpart axes differ")
    equal_previous = np.all(a[1:] == a[:-1], axis=1)
    starts = np.r_[0, np.flatnonzero(~equal_previous) + 1]
    ends = np.r_[starts[1:], len(a)]
    lengths = np.zeros(len(a), int); suspect = np.zeros(len(a), bool); long_runs = 0
    for begin, end in zip(starts, ends):
        lengths[begin:end] = end - begin
        if end - begin < 3:
            continue
        long_runs += 1
        full = np.isfinite(ieso[begin:end]).all() and np.isfinite(isne[begin:end]).all() and iq[begin:end].all()
        if full and np.ptp(ieso[begin:end]) > 2 and np.ptp(isne[begin:end]) > 2:
            suspect[begin:end] = True
    return suspect, lengths, long_runs


def regional_pg_change(delta_public_mw, shares, gamma):
    delta, sharing = np.asarray(delta_public_mw, float), np.asarray(shares, float)
    require(delta.ndim == 2 and delta.shape[1] == 4 and sharing.ndim == 2 and sharing.shape[1] == 4,
            "Four-region delta/share axes differ")
    require(np.isfinite(delta).all() and np.isfinite(sharing).all() and np.isfinite(gamma) and gamma > 0,
            "Nonfinite boundary replacement data or invalid gamma")
    require((sharing >= 0).all() and np.allclose(sharing.sum(axis=0), np.ones(4), rtol=0, atol=1e-12),
            "Each frozen regional partition must sum to one")
    change = gamma * delta @ sharing.T
    close(change.sum(axis=1), gamma * delta.sum(axis=1), "All-region replacement aggregate", tolerance=1e-9)
    return change


def api_native_pages(receipts):
    """Recover native DOE records from complete archived API responses."""
    by_name = {r["file"]: r for r in receipts}
    bilateral_names = [f"NYIS_interchange_2025_{i:05d}.json" for i in range(0, 35040, 5000)]
    total_names = [f"NYIS_total_interchange_2025_{i:05d}.json" for i in range(0, 8760, 5000)]
    require(set(bilateral_names + total_names).issubset(by_name), "Complete8 bilateral and2 total-interchange API pages are required")
    tables = []
    for family, names, expected in [("interchange-data", bilateral_names, 35040), ("region-data", total_names, 8760)]:
        frames = []
        for offset, name in zip(range(0, expected, 5000), names):
            record = by_name[name]
            url = urlparse(record["url"]); query = parse_qs(url.query)
            require(url.scheme == "https" and url.netloc == "api.eia.gov" and url.path == "/v2/electricity/rto/" + family + "/data/", "Wrong native DOE route")
            require(query.get("frequency") == ["hourly"] and query.get("start") == ["2025-01-01T06"]
                    and query.get("end") == ["2026-01-01T05"] and query.get("offset") == [str(offset)], "Native query frequency/physical range/page differs")
            if family == "interchange-data":
                require(query.get("facets[fromba][]") == ["NYIS"] and "facets[toba][]" not in query, "Native bilateral respondent or complete-neighbor scope differs")
            else:
                require(query.get("facets[respondent][]") == ["NYIS"] and query.get("facets[type][]") == ["TI"], "Wrong native total-interchange respondent/code")
            payload = json.loads((SOURCES / "raw" / name).read_text())
            require("error" not in payload and "response" in payload, "Native API error payload")
            response = payload["response"]
            require(int(response["total"]) == expected and response["frequency"] == "hourly", "Native source total/frequency differs")
            require(len(response["data"]) == min(5000, expected - offset), "Truncated native API page")
            frames.append(pd.DataFrame(response["data"]))
        tables.append(pd.concat(frames, ignore_index=True))
    return tables[0], tables[1]


def bulk_native_records(receipts, audit):
    """Read complete official bulk records, verifying both stored/original bytes.

    Bulk headers explicitly identify average MW and UTC hour ending. The one-
    hour numeric values must also agree exactly with separately archived API
    MWh records, before either representation can be used for reconstruction.
    """
    by_name = {r["file"]: r for r in receipts}
    names = [f"EIA930_{kind}_2025_{half}.csv.gz"
             for kind in ["INTERCHANGE", "BALANCE"] for half in ["Jan_Jun", "Jul_Dec"]]
    require(set(names + ["EIA930_File_List_Meta.csv"]).issubset(by_name), "Complete official bilateral and balance bulk files are required")
    require({r["file"] for r in audit["bulk_source_receipts"]} == set(names), "Bulk source receipt scope differs")
    index = pd.read_csv(SOURCES / "raw/EIA930_File_List_Meta.csv", keep_default_na=False)
    require(set(name.removesuffix(".gz") for name in names).issubset(index.FILENAME), "Bulk files are absent from official public file index")
    native_frames, total_frames, counterpart_frames = [], [], []
    for name in names:
        record = by_name[name]; path = SOURCES / "raw" / name
        require(record == next(r for r in audit["bulk_source_receipts"] if r["file"] == name), "Bulk side proof differs from source collection")
        expected_url = "https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/" + name.removesuffix(".gz")
        require(record["url"] == expected_url and record["storage"] == "lossless_gzip_of_unmodified_published_CSV_bytes", "Unverified bulk acquisition/storage transformation")
        digest = hashlib.sha256(); size = 0
        with gzip.open(path, "rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block); size += len(block)
        require(digest.hexdigest() == record["original_csv_sha256"] and size == record["original_csv_bytes"], "Decoded official CSV bytes differ")
        interchange = "_INTERCHANGE_" in name
        columns = ["Balancing Authority", "UTC Time at End of Hour"]
        columns += ["Directly Interconnected Balancing Authority", "Interchange (MW)"] if interchange else ["Total Interchange (MW)"]
        for block in pd.read_csv(path, usecols=columns, chunksize=80000):
            if interchange:
                peers = block[block["Directly Interconnected Balancing Authority"].eq("NYIS")]
                if not peers.empty:
                    ending = pd.to_datetime(peers["UTC Time at End of Hour"], format="%m/%d/%Y %I:%M:%S %p", utc=True)
                    counterpart_frames.append(pd.DataFrame(dict(timestamp_utc=ending - pd.Timedelta(hours=1),
                        reporter=peers["Balancing Authority"].to_numpy(str),
                        import_to_NY_mw=pd.to_numeric(peers["Interchange (MW)"], errors="raise").to_numpy(float))))
            values = block[block["Balancing Authority"].eq("NYIS")]
            if values.empty:
                continue
            ending = pd.to_datetime(values["UTC Time at End of Hour"], format="%m/%d/%Y %I:%M:%S %p", utc=True)
            require(((ending.dt.minute == 0) & (ending.dt.second == 0)).all(), "Bulk source contains a non-hourly endpoint")
            period = ending.dt.strftime("%Y-%m-%dT%H").to_numpy()
            if interchange:
                native_frames.append(pd.DataFrame(dict(period=period, fromba="NYIS",
                    toba=values["Directly Interconnected Balancing Authority"].to_numpy(str),
                    value=pd.to_numeric(values["Interchange (MW)"], errors="raise").to_numpy(float),
                    **{"value-units": "megawatthours"})))
            else:
                total_frames.append(pd.DataFrame(dict(period=period, respondent="NYIS", type="TI",
                    value=pd.to_numeric(values["Total Interchange (MW)"], errors="raise").to_numpy(float),
                    **{"value-units": "megawatthours"})))
    native, total = pd.concat(native_frames, ignore_index=True), pd.concat(total_frames, ignore_index=True)
    require(len(native) == 35040 and len(total) == 8760, "Bulk native NYIS year is incomplete")
    require(native.period.between("2025-01-01T06", "2026-01-01T05").all()
            and total.period.between("2025-01-01T06", "2026-01-01T05").all(), "Bulk source does not cover the local-year physical UTC range")
    keys = ["period", "fromba", "toba"]
    require(not native.duplicated(keys).any(), "Bulk native bilateral identities duplicated")
    cached = []
    for name in sorted(by_name):
        if not name.startswith("NYIS_interchange_2025_") or not name.endswith(".json"):
            continue
        record = by_name[name]; query = parse_qs(urlparse(record["url"]).query)
        require(urlparse(record["url"]).netloc == "api.eia.gov" and query.get("frequency") == ["hourly"]
                and query.get("facets[fromba][]") == ["NYIS"] and "facets[toba][]" not in query,
                "Cached API proof has wrong native respondent/neighbor scope")
        payload = json.loads((SOURCES / "raw" / name).read_text())
        require("error" not in payload and payload["response"]["frequency"] == "hourly"
                and int(payload["response"]["total"]) == 35040, "Cached native API response scope differs")
        frame = pd.DataFrame(payload["response"]["data"])
        require(frame["value-units"].eq("megawatthours").all(), "Cached API unit differs from one-hour energy")
        cached.append(frame)
    require(cached, "Official bulk mode lacks independently acquired API crosscheck")
    api = pd.concat(cached, ignore_index=True)
    require(not api.duplicated(keys).any(), "Cached API crosscheck contains duplicate native observations")
    overlap = native.merge(api, on=keys, suffixes=("_bulk", "_api"), validate="one_to_one")
    require(len(overlap) == len(api), "Native bulk omits cached API observations")
    close(pd.to_numeric(overlap.value_bulk), pd.to_numeric(overlap.value_api), "Bulk/API independent source overlap", tolerance=0, allow_nan=True)
    proof = audit["api_overlap_verification"]
    require(proof["exact_value_equality"] and proof["maximum_absolute_difference_mw"] == 0
            and proof["cached_API_pages"] == len(cached) and proof["cached_API_records"] == len(api), "Recorded API overlap proof differs")
    require(len(api) >= 25000, "Expected already archived 25,000-record independent API crosscheck")
    counterparts = pd.concat(counterpart_frames, ignore_index=True)
    require(set(counterparts.reporter) == {"ISNE", "PJM"}
            and not counterparts.duplicated(["timestamp_utc", "reporter"]).any(), "Counterpart native BA/hour scope differs")
    return native, total, counterparts


def verify_boundary_sources(times, original):
    require(REVIEW.is_file(), "Independent all-four source review is not complete")
    review = json.loads(REVIEW.read_text())
    require(review["status"] == "passed_source_only_all_four_boundary_review" and review["passed"]
            and review["year"] == 2025 and review["reporting_BA"] == "NYIS" and review["regions"] == REGIONS,
            "Independent source review scope/status differs")
    require(not review["internal_interface_observations_consumed"] and not review["source_sign_or_clock_fitted"], "Source review uses internal fit")
    audit_path = SOURCES / "source_audit_receipt.json"
    audit = json.loads(audit_path.read_text())
    require(audit["status"].startswith("complete_source_audit") and audit["year"] == 2025, "Source audit is incomplete")
    require(audit["reporting_balancing_authority"] == "NYIS" and audit["neighboring_BA_codes"] == REGIONS
            and audit["full_NYIS_neighbor_set"] == sorted(REGIONS.values()) and audit["no_neighbor_filter_applied"], "Source native BA scope changed")
    require(audit["source_record_count"] == 35040 and audit["expected_physical_hours"] == 8760
            and audit["unique_region_hour_grid"], "Incomplete native region/hour grid")
    require(audit["output_units"] == "MW_hourly_average_public_unscaled"
            and audit["positive_direction"] == "neighbor_to_NewYork_import", "Source output units/direction differs")
    if audit.get("source_mode") == "official_EIA_six_month_bulk_CSV_with_cached_API_crosscheck":
        require(audit["source_units"] == "bulk_CSV_MW_hourly_average_with_API_one_hour_MWh_crosscheck"
                and audit["bulk_source_units"] == "MW_hourly_average" and audit["API_source_units"] == "megawatthours_per_one_hour_interval",
                "Bulk MW and one-hour API MWh source quantities were conflated")
        require(audit["sign_transform"] == "output_import_mw = -bulk_Interchange_MW = -NYIS_API_reported_value_MWh / 1_hour"
                and audit["time_transform"] == "timestamp_utc_start = bulk_UTC_Time_at_End_of_Hour - 1_hour = EIA_API_period_utc_hour_ending - 1_hour",
                "Unverified bulk/API sign or UTC hour-ending transformation")
    else:
        require(audit["source_units"] == "megawatthours_per_one_hour_interval"
                and audit["sign_transform"] == "output_import_mw = -NYIS_reported_value_MWh / 1_hour"
                and audit["time_transform"] == "timestamp_utc_start = EIA_period_utc_hour_ending - 1_hour", "Unverified API source units/sign/hour-ending transformation")
    require(not audit["source_sign_or_clock_fitted"] and not audit["internal_interface_observations_consumed"]
            and audit["physical_axis_matches_frozen_2025_UTC_axis"], "Source definition is not source-only")
    proofs = {r["id"]: r for r in audit["source_proof"]}
    require({"EIA930_hour_ending_UTC", "EIA930_FLOW_sign", "EIA930_physical_scope", "API_hourly_units"}.issubset(proofs), "Missing sign, clock, scope or unit proof")
    receipts = audit["source_receipts"]
    require(receipts and len({r["file"] for r in receipts}) == len(receipts), "Source receipt collection is empty or duplicated")
    source_paths = []
    for row in receipts:
        path = (SOURCES / "raw" / row["file"]).resolve()
        require(path.is_relative_to((SOURCES / "raw").resolve()) and path.is_file(), "Invalid raw source path")
        require(sha(path) == row["sha256"], "Archived raw source changed")
        sidecar = path.with_suffix(path.suffix + ".receipt.json")
        meta = json.loads(sidecar.read_text())
        require(meta["url"] == row["url"] and meta["sha256"] == row["sha256"] and meta["file"] == row["file"], "Raw sidecar disagrees with audited source")
        source_paths.extend([path, sidecar])
    required = [SOURCES / "hourly_regional_actuals.csv", SOURCES / "hourly_source_quality.csv",
        SOURCES / "external_schedule_actual_comparison.csv", SOURCES / "reported_total_sum_check.csv",
        SOURCES / "counterparty_actual_comparison.csv", SOURCES / "frozen_report_runs.csv",
        SOURCES / "source_manifest.csv", audit_path, ROOT / audit["audit_script_path"],
        SOURCES / "raw/EIA930_instructions.pdf", SOURCES / "raw/interchange_route_metadata.json",
        OUT / "ontario/raw/PUB_IntertieScheduleFlowYear_2025.csv", OUT / "ontario/hourly_exchange_quality.csv"] + source_paths
    review_paths = check_records(review["dependencies"], required)
    original_paths = check_records(audit["original_source_hashes"], [SCHEDULES,
        ROOT / "output/nygrid_2025_inputs/load_source/hour_catalog.csv", PAR / "controls/hourly_controls.csv"])
    actual_path = checked_path(audit["actual_input_path"])
    require(actual_path == SOURCES / "hourly_regional_actuals.csv" and sha(actual_path) == audit["actual_input_sha256"], "Audited actual input changed")
    require(sha(ROOT / audit["audit_script_path"]) == audit["audit_script_sha256"], "Source extraction code changed")
    check_records(audit["quality_evidence_files"], [SOURCES / name for name in ["hourly_source_quality.csv",
        "frozen_report_runs.csv", "counterparty_actual_comparison.csv", "reported_total_sum_check.csv"]])
    manifest = pd.read_csv(SOURCES / "source_manifest.csv", keep_default_na=False)
    require(set(manifest.file) == {r["file"] for r in receipts}, "Source manifest omits archived sources")
    for row in manifest.itertuples():
        expected = next(r for r in receipts if r["file"] == row.file)
        require(row.sha256 == expected["sha256"] and row.url == expected["url"], "Source manifest and receipt disagree")
    metadata = json.loads((SOURCES / "raw/interchange_route_metadata.json").read_text())["response"]
    require(metadata["id"] == "interchange-data" and metadata["data"]["value"]["units"] == "megawatthours"
            and any(x["id"] == "hourly" and x["alias"] == "hourly (UTC)" for x in metadata["frequency"]), "Native API code/unit/frequency proof differs")
    transport = audit.get("source_mode", "api_paged")
    if transport == "api_paged":
        native, total = api_native_pages(receipts)
        counterparts = None
    elif transport == "official_EIA_six_month_bulk_CSV_with_cached_API_crosscheck":
        native, total, counterparts = bulk_native_records(receipts, audit)
    else:
        raise ValueError("Unknown source transport has no audited native-record adapter")
    require(native.fromba.eq("NYIS").all() and set(native.toba) == set(REGIONS.values()), "Wrong bilateral reporting perspective/neighbors")
    require(native["value-units"].eq("megawatthours").all() and not native.duplicated(["period", "fromba", "toba"]).any(), "Bilateral units or unique identities differ")
    require(total.respondent.eq("NYIS").all() and total.type.eq("TI").all()
            and total["value-units"].eq("megawatthours").all() and not total.period.duplicated().any(), "Native total-interchange codes/units differ")
    native["timestamp_utc"] = pd.to_datetime(native.period, utc=True) - pd.Timedelta(hours=1)
    native["actual_import_mw"] = -pd.to_numeric(native.value, errors="raise")
    total["timestamp_utc"] = pd.to_datetime(total.period, utc=True) - pd.Timedelta(hours=1)
    total["actual_import_mw"] = -pd.to_numeric(total.value, errors="raise")
    axis = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    require(np.all(np.diff(axis.asi8) == 3600 * 10**9), "Physical hour-start axis is not continuous UTC")
    wide = native.pivot(index="timestamp_utc", columns="toba", values="actual_import_mw")
    total = total.sort_values("timestamp_utc")
    require(wide.index.equals(axis) and pd.DatetimeIndex(total.timestamp_utc).equals(axis), "Native hour-ending conversion does not match physical model hours")
    require(native.groupby("toba").size().eq(8760).all(), "Bilateral source omits physical hours")
    raw_actual = wide[list(REGIONS.values())].to_numpy(float)
    raw_total = total.actual_import_mw.to_numpy(float)
    frame = pd.read_csv(actual_path)
    quality = pd.read_csv(SOURCES / "hourly_source_quality.csv")
    compare = pd.read_csv(SOURCES / "external_schedule_actual_comparison.csv")
    for data in [frame, quality, compare]:
        require(len(data) == 8760 and np.array_equal(data.hour_index.to_numpy(int), np.arange(1, 8761))
                and np.array_equal(data.timestamp_utc.to_numpy(str), times), "Derived source physical axes differ")
    actual = frame[[r + "_actual_import_mw" for r in REGIONS]].to_numpy(float)
    close(actual, raw_actual, "Derived actual versus native DOE values", tolerance=0, allow_nan=True)
    per_region, all_zero, total_nonzero = independent_region_quality(raw_actual, raw_total)
    close(bool_values(quality.all_four_actual_zero), all_zero, "Native all-four-zero mask", tolerance=0)
    close(bool_values(quality.reported_total_nonzero_beyond_rounding), total_nonzero, "Native total-interchange rounding mask", tolerance=0)
    # Independently reconstruct source-freeze corroboration. IESO quality is
    # used only for a witness within a candidate run, never inherited globally.
    require(counterparts is not None, "Frozen-vector review requires archived native counterparty reports")
    peer_wide = counterparts.pivot(index="timestamp_utc", columns="reporter", values="import_to_NY_mw").reindex(axis)
    ieso_raw = pd.read_csv(OUT / "ontario/raw/PUB_IntertieScheduleFlowYear_2025.csv", header=[3, 4])
    require(len(ieso_raw) == 8760, "Independent IESO witness year is incomplete")
    he = pd.to_numeric(ieso_raw.iloc[:, 1]).to_numpy()
    require(np.isin(he, np.arange(1, 25)).all(), "Independent IESO witness HE labels differ")
    ieso_axis = pd.DatetimeIndex(pd.to_datetime(ieso_raw.iloc[:, 0], utc=True) + pd.to_timedelta(he + 4, unit="h"))
    require(ieso_axis.equals(axis), "Independent fixed-EST witness clock differs")
    ieso_value = pd.to_numeric(ieso_raw[("NEW-YORK", "Flow")]).to_numpy(float)
    flows = [c for c in ieso_raw.columns if c[1] == "Flow"]
    schedules = [c for c in ieso_raw.columns if c[1] in ["Imp", "Exp"]]
    require(len(flows) == 15 and len(schedules) == 30, "Independent IESO report scope differs")
    ieso_zero = ieso_raw[flows].apply(pd.to_numeric).eq(0).all(axis=1).to_numpy()
    ieso_scheduled = ieso_raw[schedules].apply(pd.to_numeric).abs().sum(axis=1).gt(0).to_numpy()
    ieso_quality = np.isfinite(ieso_value) & ~(ieso_zero & ieso_scheduled)
    saved_ieso_quality = pd.read_csv(OUT / "ontario/hourly_exchange_quality.csv")
    close(bool_values(saved_ieso_quality.source_quality_qualified), ieso_quality, "Independent IESO witness quality", tolerance=0)
    cross = pd.read_csv(SOURCES / "counterparty_actual_comparison.csv")
    require(np.array_equal(cross.timestamp_utc.to_numpy(str), times), "Counterparty derived UTC axis differs")
    close(cross.IESO_reported_import_to_NY_mw, ieso_value, "IESO witness versus native source", tolerance=0)
    close(cross.ISNE_reported_import_to_NY_mw, peer_wide.ISNE.to_numpy(float), "ISNE witness versus native source", tolerance=0, allow_nan=True)
    close(cross.PJM_reported_import_to_NY_mw, peer_wide.PJM.to_numpy(float), "PJM diagnostic versus native source", tolerance=0, allow_nan=True)
    frozen, run_lengths, run_count = frozen_vector_quality(raw_actual, ieso_value, peer_wide.ISNE.to_numpy(float), ieso_quality)
    close(quality.identical_four_vector_run_length.to_numpy(int), run_lengths, "Native maximal frozen-vector run lengths", tolerance=0)
    close(bool_values(quality.corroborated_frozen_report), frozen, "Independent corroborated frozen-report mask", tolerance=0)
    freeze_proof = audit["frozen_report_quality_review"]
    require(freeze_proof["repeated_runs_at_least_three_hours"] == run_count
            and freeze_proof["quarantined_hours"] == int(frozen.sum())
            and np.array_equal(freeze_proof["excluded_hour_indices"], np.flatnonzero(frozen) + 1)
            and not freeze_proof["corroboration_uses_internal_interface_observations"]
            and not freeze_proof["adjacent_transition_hours_automatically_excluded"], "Frozen-source corroboration proof differs")
    per_region &= ~frozen[:, None]
    qualified = per_region.all(axis=1)
    for j, region in enumerate(REGIONS):
        close(bool_values(frame[region + "_source_qualified"]), per_region[:, j], "Independent regional source mask", tolerance=0)
        close(compare[region + "_original_schedule_import_mw"], original[:, j], "Preserved regional schedule", tolerance=1e-10, allow_nan=True)
        close(compare[region + "_actual_minus_schedule_mw"], actual[:, j] - original[:, j], "Regional delta", tolerance=1e-9, allow_nan=True)
    close(bool_values(frame.coverage_qualified), qualified, "Independent all-four source mask", tolerance=0)
    require(int(qualified.sum()) == audit["coverage_qualified_hours"], "Qualified source count differs")
    # Neither IESO's separate six-zero mask nor paired-comparison exclusions enter.
    proof_paths = list(dict.fromkeys(required + source_paths + review_paths + original_paths + [REVIEW]))
    return actual, qualified, per_region, raw_total, audit, proof_paths


def verify_arrays(data, bounds, priors, register, par, allocation):
    gamma = float(data["gamma"])
    require(np.isfinite(gamma) and gamma > 0 and gamma == float(par["gamma"]), "Invalid/inconsistent power scale")
    require(np.array_equal(data["hour_index"], np.arange(1, 8761)), "Original physical hour IDs differ")
    times = np.asarray(data["timestamp_utc"]).astype(str)
    require(np.array_equal(times, par["timestamp_utc"].astype(str)), "PAR/dispatch UTC axes differ")
    for item in [bounds, priors, par]:
        require(np.array_equal(np.asarray(item["hour_index"]).reshape(-1), np.arange(1, 8761)), "Numerical artifact hour IDs differ")
    for item in [bounds, priors]:
        require(np.array_equal(data["native_fleet_ids"], item["native_fleet_ids"]), "Native numerical identities differ")
    native = np.flatnonzero(register.role.eq("native"))
    external = np.flatnonzero(register.role.eq("fixed_external"))
    require(np.array_equal(native, np.arange(1436)) and len(external) == 28 and len(register) == 1464, "Native/external axis differs")
    require(np.array_equal(register.gen_row.to_numpy(int), np.arange(1, 1465)), "Model generator order differs")
    require(np.array_equal(pd.to_numeric(register.iloc[native].fleet_id).to_numpy(), data["native_fleet_ids"]), "Register/native fleet axis differs")
    require(np.asarray(data["gen_pg"]).shape == np.asarray(priors["prior_pg"]).shape == (8760, 1464), "PG/prior shapes differ")
    require(np.asarray(bounds["gen_pmin"]).shape == np.asarray(bounds["gen_pmax"]).shape == (8760, 1464)
            and np.asarray(priors["objective_weights"]).shape == (8760, 1436), "Bound/weight shapes differ")
    q = np.asarray(data["dispatch_qualified"], bool)
    for name, values in [("prior", priors["prior_pg"][:, native]), ("lower", bounds["gen_pmin"][:, native]),
                         ("upper", bounds["gen_pmax"][:, native]), ("weight", priors["objective_weights"])]:
        require(np.isfinite(values[q]).all(), "Nonfinite original qualified native " + name)
    require((priors["objective_weights"][q] > 0).all() and (bounds["gen_pmax"][q] >= bounds["gen_pmin"][q]).all(), "Invalid native boxes or objective weights")
    require(bool(par["observed_direction_verified"]) and np.array_equal(par["ptids"], [25118, 25119])
            and np.array_equal(par["direction_ontario_to_NY_multiplier"], [1, 1]), "PAR source identities/direction differ")
    close(par["observed_model_mw"], par["observed_public_mw"] * gamma, "P34 power scale", tolerance=1e-12, allow_nan=True)
    require(set(allocation.region) == set(REGIONS) and len(allocation) == 28 and allocation.generator_row.is_unique, "Incomplete external allocation partition")
    parent_rows = pd.to_numeric(register.parent_gen_row, errors="coerce").to_numpy()
    matrix = np.zeros((1464, 4))
    records = []
    counts = {"ISONE": 9, "ONTARIO": 6, "PJM": 12, "HQ": 1}
    for j, region in enumerate(REGIONS):
        group = allocation[allocation.region.eq(region)]
        require(len(group) == counts[region] and np.isfinite(group.generation_share).all()
                and (group.generation_share >= 0).all() and abs(group.generation_share.sum() - 1) < 1e-12, "Invalid frozen regional partition")
        for row in group.itertuples():
            match = np.flatnonzero((parent_rows == row.generator_row) & register.role.eq("fixed_external").to_numpy())
            require(len(match) == 1 and int(register.iloc[match[0]].bus_id) == int(row.bus_id), "External allocation identity/terminal differs")
            col = int(match[0]); matrix[col, j] = row.generation_share
            records.append(dict(model_gen_row_1based=col + 1, parent_gen_row=int(row.generator_row), bus_id=int(row.bus_id),
                region=region, native_DOE_neighbor_code=REGIONS[region], frozen_generation_share=float(row.generation_share)))
    require(set(np.flatnonzero(matrix.sum(axis=1))) == set(external) and np.max(matrix[native]) == 0, "Region partition does not cover exactly external rows")
    return native, external, matrix, records


def kkt_metrics(pg, p0, lo, hi, weights, target, dual):
    require(np.isfinite(pg).all() and np.isfinite(dual).all(), "Nonfinite KKT candidate")
    projected = np.clip(p0 + dual[:, None] / weights, lo, hi)
    distance = np.max(abs(pg - projected), axis=1)
    balance = abs(pg.sum(axis=1) - target)
    violation = np.max(np.maximum(np.maximum(lo - pg, pg - hi), 0), axis=1)
    require(np.max(distance) < TOL and np.max(balance) < TOL and np.max(violation) < TOL, "Bounded projection fails KKT, balance or box check")
    return distance, balance, violation


def build():
    started = datetime.now(timezone.utc).isoformat()
    frozen_paths = verify_frozen()
    data = loadmat(BASE / "dispatch.mat", simplify_cells=True)
    bounds = loadmat(BASE / "dispatch_bounds.mat", simplify_cells=True)
    priors = loadmat(BASE / "dispatch_priors.mat", simplify_cells=True)
    register = pd.read_csv(REGISTER, keep_default_na=False)
    allocation = pd.read_csv(ALLOCATION)
    par = np.load(PAR / "controls/inputs.npz", allow_pickle=False)
    native, external, sharing, share_rows = verify_arrays(data, bounds, priors, register, par, allocation)
    times = np.asarray(data["timestamp_utc"]).astype(str); gamma = float(data["gamma"])
    _, original, original_dc_public = original_schedules(times)
    actual, source_mask, region_quality, reported_total, audit, source_paths = verify_boundary_sources(times, original)
    original_q = np.asarray(data["dispatch_qualified"], bool)
    close(original_dc_public[original_q] * gamma, data["dc_pf"][original_q], "Frozen four DC decomposition", tolerance=1e-9)
    source_q = original_q & np.asarray(par["observed_replay_qualified"], bool) & source_mask
    ix = np.flatnonzero(source_q)
    require(len(ix) > 0, "No independently qualified all-boundary reconstruction hours")
    delta = actual - original
    require(np.isfinite(delta[ix]).all(), "Qualified regional boundary change is nonfinite")
    protected = list(dict.fromkeys(frozen_paths + source_paths + [Path(__file__)]))
    # Fingerprints captured after verified proof gates but before reconstruction.
    before = {path: sha(path) for path in protected}
    old_pg = np.asarray(data["gen_pg"])
    p0, lo, hi, weights = priors["prior_pg"][:, native], bounds["gen_pmin"][:, native], bounds["gen_pmax"][:, native], priors["objective_weights"]
    old_kkt = kkt_metrics(old_pg[np.ix_(ix, native)], p0[ix], lo[ix], hi[ix], weights[ix],
                          np.asarray(data["native_required_pg"])[ix], np.asarray(data["dual_lambda"])[ix])
    pg = np.full_like(old_pg, np.nan)
    pg[ix] = old_pg[ix]
    pg[ix] += regional_pg_change(delta[ix], sharing, gamma)
    target = np.full(8760, np.nan)
    target[ix] = data["bus_pd"][ix].sum(axis=1) + data["base_case"]["bus"][:, 4].sum() - pg[np.ix_(ix, external)].sum(axis=1)
    total_delta = delta.sum(axis=1)
    close(target[ix], np.asarray(data["native_required_pg"])[ix] - gamma * total_delta[ix], "Simultaneous four-boundary/native balance cancellation")
    expected_feasible = (target[ix] >= lo[ix].sum(axis=1) - TOL) & (target[ix] <= hi[ix].sum(axis=1) + TOL)
    solved, dual, feasible = bounded_projection(p0[ix], lo[ix], hi[ix], target[ix], weights[ix])
    require(np.array_equal(feasible, expected_feasible), "Independent native feasibility interval disagrees")
    status = np.zeros(8760, np.int8); status[ix] = np.where(feasible, 1, 2)
    qualified = status == 1; good = ix[feasible]
    require(len(good) > 0, "Every all-boundary case is native-capacity infeasible")
    pg[np.ix_(good, native)] = solved[feasible]
    pg[~qualified] = np.nan
    multiplier = np.full(8760, np.nan); multiplier[good] = dual[feasible]
    kkt = kkt_metrics(pg[np.ix_(good, native)], p0[good], lo[good], hi[good], weights[good], target[good], multiplier[good])
    close(pg[good].sum(axis=1), data["bus_pd"][good].sum(axis=1) + data["base_case"]["bus"][:, 4].sum(), "Global lossless power balance")
    for j, region in enumerate(REGIONS):
        cols = np.flatnonzero(sharing[:, j])
        close((pg[np.ix_(good, cols)] - old_pg[np.ix_(good, cols)]).sum(axis=1), gamma * delta[good, j], "External regional replacement: " + region)
        close(pg[np.ix_(good, cols)] - old_pg[np.ix_(good, cols)], gamma * delta[good, j, None] * sharing[cols, j], "Frozen within-region shares: " + region)
    objective = np.full(8760, np.nan)
    objective[good] = .5 * np.sum(weights[good] * (pg[np.ix_(good, native)] - p0[good]) ** 2, axis=1)
    residual, balance, bound_error = [np.full(8760, np.nan) for _ in range(3)]
    residual[good], balance[good], bound_error[good] = kkt
    folder = OUT / "dispatch"; folder.mkdir(parents=True, exist_ok=True)
    path = folder / "all_boundary_actual_dispatch.mat"
    require(not path.exists(), "Use the existing completed reconstruction or explicitly preserve it before a rebuild")
    savemat(path, dict(hour_index=data["hour_index"], timestamp_utc=times.astype(object), gen_pg=pg,
        original_qualified=original_q, boundary_source_qualified=source_mask, region_source_qualified=region_quality,
        source_qualified=source_q, qualified=qualified, status_code=status,
        native_required_pg=target, dual_lambda=multiplier, objective_value=objective, gamma=gamma,
        region_labels=np.array(list(REGIONS), object), native_DOE_neighbor_codes=np.array(list(REGIONS.values()), object),
        original_regional_schedule_public_mw=original, actual_regional_import_public_mw=actual,
        delta_region_public_mw=delta, total_boundary_delta_public_mw=total_delta,
        NYIS_reported_total_actual_import_public_mw=reported_total,
        external_generator_rows_1based=external + 1, external_region_share_matrix=sharing[external],
        native_generator_rows_1based=native + 1, native_fleet_ids=data["native_fleet_ids"],
        original_four_dc_pf=data["dc_pf"], P34_control_targets_model_mw=par["observed_model_mw"],
        kkt_projection_residual_model_mw=residual, native_balance_residual_model_mw=balance,
        native_bound_violation_model_mw=bound_error), do_compression=True, oned_as="column")
    changes = []
    for j, row in register.iterrows():
        difference = (pg[good, j] - old_pg[good, j]) / gamma
        changes.append(dict(gen_row=j + 1, device_key=row.device_key, role=row.role, fuel_category=row.fuel_category,
            original_mean_public_mw=float(old_pg[good, j].mean() / gamma), reconstructed_mean_public_mw=float(pg[good, j].mean() / gamma),
            mean_change_public_mw=float(difference.mean()), mean_absolute_change_public_mw=float(abs(difference).mean()),
            max_absolute_change_public_mw=float(abs(difference).max())))
    pd.DataFrame(changes).to_csv(folder / "all_boundary_generator_adjustments.csv", index=False)
    hour_status = pd.DataFrame(dict(hour_index=data["hour_index"], timestamp_utc=times, original_qualified=original_q,
        EIA_all_four_qualified=source_mask, source_qualified=source_q, qualified=qualified, status_code=status,
        total_boundary_delta_public_mw=total_delta, native_required_model_mw=target,
        native_lower_margin_model_mw=target - lo.sum(axis=1), native_upper_margin_model_mw=hi.sum(axis=1) - target,
        kkt_projection_residual_model_mw=residual, native_balance_residual_model_mw=balance))
    for j, region in enumerate(REGIONS):
        hour_status[region + "_delta_public_mw"] = delta[:, j]
    hour_status.to_csv(folder / "all_boundary_hour_status.csv", index=False)
    pd.DataFrame(share_rows).to_csv(folder / "all_boundary_external_generator_shares.csv", index=False)
    require(all(sha(p) == digest for p, digest in before.items()), "An immutable input changed during reconstruction")
    receipt = dict(passed=True, status="four_region_actual_imports_simultaneous_bounded_native_reconstruction",
        started_utc=started, completed_utc=datetime.now(timezone.utc).isoformat(),
        source_reporting_BA="NYIS", regions=REGIONS, qualified_hours=int(qualified.sum()), source_qualified_hours=int(source_q.sum()),
        original_qualified_hours=int(original_q.sum()), additional_source_excluded_hours=int((original_q & ~source_q).sum()),
        capacity_infeasible_hours=int((status == 2).sum()),
        original_native_KKT_max_model_mw=float(max(np.max(x) for x in old_kkt)),
        reconstructed_native_KKT_max_model_mw=float(np.max(kkt[0])),
        native_balance_max_model_mw=float(np.max(kkt[1])), native_bound_violation_max_model_mw=float(np.max(kkt[2])),
        mean_total_boundary_delta_public_mw=float(total_delta[good].mean()),
        mean_absolute_total_boundary_delta_public_mw=float(abs(total_delta[good]).mean()),
        minimum_native_lower_margin_model_mw=float((target[good] - lo[good].sum(axis=1)).min()),
        minimum_native_upper_margin_model_mw=float((hi[good].sum(axis=1) - target[good]).min()),
        native_priors_objective_weights_capacity_and_admission_unchanged=True,
        original_PD_QD_four_DC_schedules_and_P34_controls_preserved=True,
        within_region_external_shares_unchanged_and_assumed=True,
        IESO_separate_six_zero_mask_inherited=False, no_internal_interface_observations_consumed=True,
        internal_interface_observations_used=False,
        source_sign_clock_units_or_weights_fit_to_internal_flows=False,
        source_proofs_verified_before_computation=True, all_input_hashes_unchanged=True,
        Ontario_only_reconstruction_modified=False, topology_or_generator_mapping_changed=False,
        policy="Replace all4regional schedules by NYIS-reported actual imports simultaneously; preserve frozen external shares and project native priors within original boxes using original weights.",
        limitations=["Regional actual totals do not establish circuit flows or observed native unit dispatch.",
            "The original four DC link schedules and P34 transfer controls remain; within-region AC/DC partition remains conditional.",
            "Per-hour lossless bounded source-prior reconstruction; no AC, thermal, ramp, commitment or reservoir-energy feasibility claim."],
        dispatch_file=path.relative_to(ROOT).as_posix(), dispatch_file_sha256=sha(path),
        source_input_sha256=audit["actual_input_sha256"], source_review_sha256=before[REVIEW],
        dependencies=[dict(path=p.relative_to(ROOT).as_posix(), sha256=digest) for p, digest in before.items()])
    (folder / "all_boundary_dispatch_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(build(), indent=2))
