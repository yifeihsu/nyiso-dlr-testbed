"""Reconstruct released 2019 zonal loads from all official NYISO raw archives.

Run: python scripts/nygrid_2019_diagnostics/audit_raw_load.py
Repeat from hash-verified archives: add --offline.

This follows the released writeLoad.m literally: discard timezone for the
aggregation key, average every raw row in each local hourly bin, and linearly
fill missing bins (including linear endpoint extrapolation). No timestamp
shift, deduplication, or correction is used to force agreement. Raw timezone,
source archive/member/line and duplicate records remain in the audit outputs.
Original source and baseline model artifacts are never modified.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time
import urllib.request
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tmp/nygrid_2019_reproduction/upstream"
RAW = ROOT / "tmp/nygrid_2019_diagnostics/raw_load"
OUT = ROOT / "output/nygrid_2019_diagnostics"
TOLERANCE_MW = 1e-8
INDEX_URL = "https://mis.nyiso.com/public/P-58Clist.htm"
ZONE_IDS = {"CAPITL": "F", "CENTRL": "C", "DUNWOD": "I", "GENESE": "B",
            "HUD VL": "G", "LONGIL": "K", "MHK VL": "E", "MILLWD": "H",
            "N.Y.C.": "J", "NORTH": "D", "WEST": "A"}
KEYS = ["TimeStamp", "ZoneName"]
RAW_HEADER = ["Time Stamp", "Time Zone", "Name", "PTID", "Integrated Load"]
RAW_COLUMNS = ["TimeStamp", "TimeZone", "ZoneName", "PTID", "Load"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def write_frame(frame: pd.DataFrame, name: str, output: Path = OUT) -> None:
    frame.to_csv(output / f"load_audit_{name}.csv", index=False, lineterminator="\n",
                 date_format="%Y-%m-%d %H:%M:%S", float_format="%.15g")


def acquire(month: int, offline: bool = False) -> dict:
    name = f"2019{month:02d}01palIntegrated_csv.zip"
    url = f"https://mis.nyiso.com/public/csv/palIntegrated/{name}"
    target = RAW / name
    receipt = RAW / f"{name}.provenance.json"
    if target.exists():
        require(receipt.exists(), f"Raw archive has no provenance receipt: {target}")
        record = json.loads(receipt.read_text(encoding="utf-8"))
        payload = target.read_bytes()
        require(record["source_url"] == url and sha_bytes(payload) == record["sha256"],
                f"Raw archive provenance/hash mismatch: {target}")
        require(record["bytes"] == len(payload), f"Raw archive size mismatch: {target}")
        access = "verified_existing_receipt"
    else:
        require(not offline, f"Offline raw archive unavailable: {target}")
        record = {"month": f"2019-{month:02d}", "source_url": url, "archive": rel(target),
                  "acquisition": "fresh_official_download"}
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "NYgrid-2019-raw-load-source-audit/1.0"})
                with urllib.request.urlopen(request, timeout=45) as response:
                    payload = response.read()
                    record.update(http_last_modified=response.headers.get("Last-Modified", ""),
                                  http_etag=response.headers.get("ETag", ""),
                                  http_status=response.status)
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        record.update(retrieved_utc=now(), sha256=sha_bytes(payload), bytes=len(payload))
        access = "downloaded_this_run"
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        require(archive.testzip() is None, f"ZIP CRC failure: {name}")
        members = [m for m in archive.namelist() if m.lower().endswith(".csv")]
        dates = pd.date_range(f"2019-{month:02d}-01", periods=pd.Period(f"2019-{month:02d}").days_in_month, freq="D")
        expected = {d.strftime("%Y%m%d") + "palIntegrated.csv" for d in dates}
        require(set(members) == expected and len(members) == len(expected), f"Daily archive member coverage differs: {name}")
    if not target.exists():
        target.write_bytes(payload)
        receipt.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"{name}: {access}, {len(members)} days, {len(payload):,} bytes", flush=True)
    return {**record, "access_this_run": access, "csv_members": len(members), "verified_utc": now()}


def linear_fill(values: np.ndarray) -> np.ndarray:
    """MATLAB fillmissing(y,'linear'), including default endpoint extrapolation."""
    y = np.asarray(values, dtype=float).copy()
    require(not np.isinf(y).any(), "Infinite input in interpolation")
    valid = np.flatnonzero(np.isfinite(y))
    if not len(valid):
        return y
    require(len(valid) > 1 or not np.isnan(y).any(), "Cannot extrapolate from one finite sample")
    x = np.arange(len(y))
    result = np.interp(x, valid, y[valid])
    if len(valid) > 1:
        for a, b, mask in [(valid[0], valid[1], x < valid[0]), (valid[-2], valid[-1], x > valid[-1])]:
            result[mask] = y[a] + (x[mask] - a) * (y[b] - y[a]) / (b - a)
    return result


def read_archives(receipts: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw, members = [], []
    for receipt in receipts:
        path = ROOT / receipt["archive"]
        require(sha_file(path) == receipt["sha256"], "Archive changed after acquisition")
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if not name.lower().endswith(".csv"):
                    continue
                payload = archive.read(name)
                frame = pd.read_csv(io.BytesIO(payload), dtype=str)
                require(list(frame.columns) == RAW_HEADER, f"Unexpected raw load schema: {name}")
                frame.columns = RAW_COLUMNS
                frame["raw_timestamp_text"] = frame.TimeStamp
                frame.TimeStamp = pd.to_datetime(frame.TimeStamp, format="mixed", errors="raise")
                require(frame.TimeStamp.notna().all() and frame.ZoneName.notna().all(), f"Missing raw load key: {name}")
                require(set(frame.ZoneName).issubset(ZONE_IDS), f"Unrecognized raw load zone: {name}")
                require(frame.TimeZone.notna().all() and set(frame.TimeZone).issubset({"EST", "EDT"}),
                        f"Unrecognized raw timezone: {name}")
                frame.Load = pd.to_numeric(frame.Load, errors="raise")
                frame.PTID = pd.to_numeric(frame.PTID, errors="raise").astype(int)
                require(not np.isinf(frame.Load).any(), f"Infinite raw load: {name}")
                frame["source_archive"] = receipt["archive"]
                frame["source_member"] = name
                frame["source_line"] = np.arange(len(frame)) + 2
                frame["archive_month"] = receipt["month"]
                day = pd.to_datetime(name[:8], format="%Y%m%d")
                outside = int((frame.TimeStamp.dt.normalize() != day).sum())
                require(outside == 0, f"Raw date differs from member date: {name}")
                members.append({"source_archive": receipt["archive"], "source_member": name,
                                "member_sha256": sha_bytes(payload), "bytes": len(payload), "raw_rows": len(frame),
                                "zones": frame.ZoneName.nunique(), "missing_load_values": int(frame.Load.isna().sum()),
                                "timezone_labels": "|".join(sorted(set(frame.TimeZone))), "timestamp_outside_member_date": outside})
                raw.append(frame)
    out = pd.concat(raw, ignore_index=True)
    require(set(out.ZoneName) == set(ZONE_IDS), "Not all 11 zones present in raw records")
    require(all(out.groupby("ZoneName").PTID.nunique() == 1), "A zone has multiple PTIDs")
    require(out.groupby("PTID").ZoneName.nunique().eq(1).all(), "A PTID identifies multiple zones")
    # A separate diagnostic proves the raw DST repetitions are distinct physical
    # hours. This column is never used by the released-preprocessing replication.
    out["diagnostic_utc_timestamp"] = out.TimeStamp + pd.to_timedelta(out.TimeZone.map({"EST": 5, "EDT": 4}), unit="h")
    return out, pd.DataFrame(members)


def reconstruct_hourly(raw: pd.DataFrame) -> pd.DataFrame:
    pieces = []
    for zone, rows in raw.groupby("ZoneName", sort=True):
        rows = rows.sort_values("TimeStamp", kind="stable").set_index("TimeStamp")
        bins = rows.Load.resample("h", label="left", closed="left")
        means = bins.mean()
        h = pd.DataFrame({"Load_unimputed": means, "Load": linear_fill(means.to_numpy()),
                          "raw_rows": bins.size(), "finite_load_samples": bins.count(),
                          "distinct_raw_timestamp_count": rows.reset_index().groupby(pd.Grouper(key="TimeStamp", freq="h")).TimeStamp.nunique(),
                          "raw_timezone_labels": rows.TimeZone.resample("h").apply(lambda x: "|".join(sorted(set(x.dropna())))),
                          "Load_imputed": means.isna()})
        h["spring_dst_hour"] = h.index == pd.Timestamp("2019-03-10 02:00:00")
        h["fall_dst_ambiguous_hour"] = h.index == pd.Timestamp("2019-11-03 01:00:00")
        h["duplicate_raw_timestamp_rows"] = h.raw_rows - h.distinct_raw_timestamp_count
        h["ZoneName"] = zone
        h["ZoneID"] = ZONE_IDS.get(zone, "")
        pieces.append(h.reset_index())
    return pd.concat(pieces, ignore_index=True).sort_values(KEYS, kind="stable").reset_index(drop=True)


def read_published(path: Path) -> pd.DataFrame:
    p = pd.read_csv(path, dtype={"ZoneName": str, "ZoneID": str})
    require(list(p.columns) == ["TimeStamp", "ZoneName", "Load", "ZoneID"], f"Unexpected prepared load columns: {path}")
    p.TimeStamp = pd.to_datetime(p.TimeStamp, format="mixed", errors="raise")
    require(not p.duplicated(KEYS).any(), f"Prepared load contains duplicate keys: {path}")
    require(p[KEYS].notna().all().all(), f"Missing prepared load keys: {path}")
    require(pd.to_numeric(p.Load, errors="raise").notna().all(), f"Missing prepared load values: {path}")
    require(np.isfinite(p.Load).all(), f"Nonfinite prepared load values: {path}")
    require(p.ZoneID.eq(p.ZoneName.map(ZONE_IDS)).all(), f"Prepared zone identifier mismatch: {path}")
    return p


def compare(hourly: pd.DataFrame, published: pd.DataFrame, label: str) -> tuple[pd.DataFrame, dict]:
    require(not hourly.duplicated(KEYS).any(), "Reconstruction contains duplicate keys")
    require(not published.duplicated(KEYS).any(), "Published load contains duplicate keys")
    merged = hourly[KEYS + ["Load"]].rename(columns={"Load": "reconstructed_load_mw"}).merge(
        published[KEYS + ["Load"]].rename(columns={"Load": f"{label}_load_mw"}),
        on=KEYS, how="outer", validate="one_to_one", indicator=True)
    merged["ZoneID"] = merged.ZoneName.map(ZONE_IDS)
    merged[f"reconstructed_minus_{label}_mw"] = merged.reconstructed_load_mw - merged[f"{label}_load_mw"]
    merged[f"{label}_key_status"] = merged.pop("_merge").astype(str)
    error = merged[f"reconstructed_minus_{label}_mw"]
    matched = merged[f"{label}_key_status"].eq("both")
    bad = ~matched | error.abs().gt(TOLERANCE_MW)
    stats = {"rows": len(merged), "matched_keys": int(matched.sum()),
             "missing_published_keys": int(merged[f"{label}_key_status"].eq("left_only").sum()),
             "missing_reconstructed_keys": int(merged[f"{label}_key_status"].eq("right_only").sum()),
             "rows_above_tolerance_or_missing": int(bad.sum()),
             "max_absolute_difference_mw": float(error.abs().max()),
             "mae_mw": float(error.abs().mean()), "rmse_mw": float(np.sqrt(np.mean(error ** 2))),
             "reproduced_within_tolerance": bool(not bad.any()), "tolerance_mw": TOLERANCE_MW}
    return merged, stats


def matlab_export(output: Path = OUT) -> dict:
    """Export the actual MATLAB table; do not substitute its companion CSV."""
    source = SOURCE / "Data/loadHourly_2019.mat"
    target = output / "load_audit_mat_export.csv"
    semantics = output / "load_audit_matlab_semantics.json"
    executable = shutil.which("matlab")
    require(executable is not None, "MATLAB required to export actual released load table")
    q = lambda p: str(p.resolve()).replace("'", "''").replace("\\", "/")
    script = RAW.parent / "export_released_load.m"
    script.write_text(
        f"d=load('{q(source)}','loadHourly');\n"
        "assert(istable(d.loadHourly));\n"
        "assert(isequal(d.loadHourly.Properties.VariableNames,{'TimeStamp','ZoneName','Load','ZoneID'}));\n"
        "assert(height(d.loadHourly)==96360);\n"
        "d.loadHourly.TimeStamp.Format='MM/dd/yyyy HH:mm:ss';\n"
        f"writetable(d.loadHourly,'{q(target)}');\n"
        "v=fillmissing([NaN;2;NaN;NaN;8;NaN],'linear');\n"
        "assert(max(abs(v-[0;2;4;6;8;10]))<1e-12);\n"
        "t=datetime(2019,1,1)+minutes([0;0;59;60]);\n"
        "tt=timetable(t,[0;6;6;100],'VariableNames',{'Load'});\n"
        "hh=retime(tt,'hourly','mean');\n"
        "assert(isequal(hh.Load,[4;100]));\n"
        "report=struct('rows',height(d.loadHourly),'matlab_version',version,"
        "'linear_endpoint_extrapolation_passed',true,'duplicate_sample_mean_passed',true);\n"
        f"fid=fopen('{q(semantics)}','w');fwrite(fid,jsonencode(report,PrettyPrint=true));fclose(fid);\n",
        encoding="utf-8", newline="\n")
    source_hash = sha_file(source)
    args = [executable, "-batch", f"run('{q(script)}')", "-logfile", str((output / "load_audit_matlab_export.log").resolve())]
    result = subprocess.run(args, capture_output=True, text=True, timeout=180,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    require(result.returncode == 0, f"Actual MAT table export failed: {result.stdout[-3000:]} {result.stderr[-3000:]}")
    require(sha_file(source) == source_hash, "Original MAT source changed during export")
    # Canonical LF is a serialization normalization of this new export only.
    target.write_bytes(target.read_bytes().replace(b"\r\n", b"\n"))
    receipt = {"source_mat": rel(source), "source_sha256": source_hash, "export": rel(target),
               "export_sha256": sha_file(target), "export_script": rel(script), "export_script_sha256": sha_file(script),
               "exported_utc": now(), **json.loads(semantics.read_text())}
    (output / "load_audit_mat_export_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    return receipt


def grouped_comparison(comparison: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    rows = []
    for key, part in comparison.groupby(by, sort=True):
        if len(by) == 1:
            key = (key,) if not isinstance(key, tuple) else key
        entry = dict(zip(by, key))
        entry["rows"] = len(part)
        for label in ["released_csv", "released_mat"]:
            err = part[f"reconstructed_minus_{label}_mw"]
            entry[f"{label}_max_abs_difference_mw"] = float(err.abs().max())
            entry[f"{label}_rmse_mw"] = float(np.sqrt(np.mean(err ** 2)))
            entry[f"{label}_mismatched_rows"] = int((err.abs().gt(TOLERANCE_MW) | part[f"{label}_key_status"].ne("both")).sum())
        rows.append(entry)
    return pd.DataFrame(rows)


def run(offline: bool = False, output: Path = OUT) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    start = now()
    # MATLAB table export and official archive requests do not depend on one another.
    with ThreadPoolExecutor(max_workers=5) as pool:
        export_future = pool.submit(matlab_export, output)
        receipts = list(pool.map(lambda m: acquire(m, offline), range(1, 13)))
        export_receipt = export_future.result()
    raw, members = read_archives(receipts)
    hourly = reconstruct_hourly(raw)
    expected = pd.MultiIndex.from_product([pd.date_range("2019-01-01", "2019-12-31 23:00", freq="h"), sorted(ZONE_IDS)], names=KEYS)
    observed = pd.MultiIndex.from_frame(hourly[KEYS])
    require(observed.equals(expected), "Reconstruction does not cover exactly 8760 nominal hours by 11 zones")
    require(np.isfinite(hourly.Load).all(), "Unresolved reconstructed load gaps")
    csv_path = SOURCE / "Data/loadHourly_2019.csv"
    csv_comparison, csv_stats = compare(hourly, read_published(csv_path), "released_csv")
    mat_comparison, mat_stats = compare(hourly, read_published(output / "load_audit_mat_export.csv"), "released_mat")
    comp = csv_comparison.merge(mat_comparison.drop(columns=["ZoneID", "reconstructed_load_mw"]), on=KEYS, how="outer", validate="one_to_one")
    comp["month"] = comp.TimeStamp.dt.strftime("%Y-%m")
    comp["released_mat_minus_csv_mw"] = comp.released_mat_load_mw - comp.released_csv_load_mw
    comp["mismatch_or_missing"] = (comp.reconstructed_minus_released_csv_mw.abs().gt(TOLERANCE_MW)
                                  | comp.reconstructed_minus_released_mat_mw.abs().gt(TOLERANCE_MW)
                                  | comp.released_csv_key_status.ne("both") | comp.released_mat_key_status.ne("both"))
    dup_mask = raw.duplicated(KEYS, keep=False)
    duplicate_rows = raw.loc[dup_mask].sort_values(KEYS + ["TimeZone", "source_member", "source_line"])
    duplicate_groups = []
    for key, group in duplicate_rows.groupby(KEYS, sort=True):
        duplicate_groups.append({"TimeStamp": key[0], "ZoneName": key[1], "ZoneID": ZONE_IDS[key[1]],
                                 "raw_rows": len(group), "different_load_values": group.Load.nunique(dropna=False),
                                 "raw_timezone_labels": "|".join(sorted(group.TimeZone.unique())),
                                 "minimum_load_mw": group.Load.min(), "maximum_load_mw": group.Load.max(),
                                 "sample_mean_load_mw": group.Load.mean(),
                                 "sources": "|".join(f"{r.source_member}:{r.source_line}" for r in group.itertuples())})
    duplicate_groups = pd.DataFrame(duplicate_groups, columns=KEYS + ["ZoneID", "raw_rows", "different_load_values",
                "raw_timezone_labels", "minimum_load_mw", "maximum_load_mw", "sample_mean_load_mw", "sources"])
    write_frame(pd.DataFrame(receipts), "archives", output)
    write_frame(members, "members", output)
    write_frame(raw, "raw_rows", output)
    write_frame(duplicate_rows, "duplicate_raw_rows", output)
    write_frame(duplicate_groups, "duplicate_groups", output)
    write_frame(hourly, "hourly_quality", output)
    write_frame(hourly.loc[hourly.Load_imputed], "imputed_hours", output)
    write_frame(hourly.loc[hourly.spring_dst_hour | hourly.fall_dst_ambiguous_hour], "dst_hours", output)
    write_frame(comp, "comparison", output)
    write_frame(comp.loc[comp.mismatch_or_missing], "mismatches", output)
    write_frame(grouped_comparison(comp, ["month", "ZoneID"]), "monthly_zone_comparison", output)
    write_frame(grouped_comparison(comp, ["ZoneID"]), "zone_comparison", output)
    # Exactly the source schema, ready for an explicitly labelled counterfactual.
    write_frame(hourly[["TimeStamp", "ZoneName", "Load", "ZoneID"]], "reconstructed_hourly", output)
    dependencies = [(Path(__file__), "audit_code"), (SOURCE / "Utility/writeLoad.m", "released_preprocessing_algorithm"),
                    (SOURCE / "Utility/downloadData.m", "official_url_algorithm"),
                    (csv_path, "released_csv_comparison"), (SOURCE / "Data/loadHourly_2019.mat", "actual_mat_comparison_source"),
                    (output / "load_audit_mat_export.csv", "fresh_actual_mat_table_export"),
                    (RAW.parent / "export_released_load.m", "matlab_export_and_semantics_check"),
                    (Path(__file__).with_name("test_audit_raw_load.py"), "focused_adversarial_tests")]
    write_frame(pd.DataFrame([{"path": rel(p), "role": role, "sha256": sha_file(p)} for p, role in dependencies]), "dependencies", output)
    non_dst_duplicates = duplicate_groups.loc[duplicate_groups.TimeStamp.ne(pd.Timestamp("2019-11-03 01:00:00"))]
    summary = {"scope": "2019 official NYISO palIntegrated load source-preparation reproduction; no bus-level demand or electrical-flow validation",
               "official_archive_index": INDEX_URL,
               "started_utc": start, "completed_utc": now(), "status": "reproduced" if csv_stats["reproduced_within_tolerance"] and mat_stats["reproduced_within_tolerance"] else "differences_identified",
               "official_monthly_archives": len(receipts), "daily_csv_members": len(members), "raw_rows": len(raw),
               "raw_timezone_row_counts": {str(k): int(v) for k, v in raw.TimeZone.value_counts().items()},
               "unique_raw_timestamp_zone_keys": int(raw[KEYS].drop_duplicates().shape[0]),
               "diagnostic_unique_utc_timestamp_zone_keys": int(raw[["diagnostic_utc_timestamp", "ZoneName"]].drop_duplicates().shape[0]),
               "diagnostic_utc_timestamp_range": [str(raw.diagnostic_utc_timestamp.min()), str(raw.diagnostic_utc_timestamp.max())],
               "duplicate_timestamp_zone_groups": len(duplicate_groups), "duplicate_raw_rows_in_groups": len(duplicate_rows),
               "conflicting_duplicate_groups": int(duplicate_groups.different_load_values.gt(1).sum()),
               "non_fall_dst_duplicate_groups": len(non_dst_duplicates), "raw_missing_load_values": int(raw.Load.isna().sum()),
               "raw_negative_load_values": int(raw.Load.lt(0).sum()), "prepared_hour_zone_keys": len(hourly),
               "nominal_local_hours": 8760, "zones": 11, "interpolated_hour_zone_keys": int(hourly.Load_imputed.sum()),
               "imputed_hour_labels": sorted(hourly.loc[hourly.Load_imputed, "TimeStamp"].astype(str).unique().tolist()),
               "fall_dst_ambiguous_hour_zone_keys": int(hourly.fall_dst_ambiguous_hour.sum()),
               "csv_comparison": csv_stats, "mat_comparison": mat_stats,
               "max_actual_mat_vs_csv_difference_mw": float(comp.released_mat_minus_csv_mw.abs().max()),
               "archive_acquisition_counts": pd.Series([r["acquisition"] for r in receipts]).value_counts().to_dict(),
               "archive_access_this_run_counts": pd.Series([r["access_this_run"] for r in receipts]).value_counts().to_dict(),
               "first_archive_retrieved_utc": min(r["retrieved_utc"] for r in receipts), "last_archive_retrieved_utc": max(r["retrieved_utc"] for r in receipts),
               "matlab_export": export_receipt,
               "algorithm": {"timestamps": "timezone-naive published local labels; EST/EDT retained separately for diagnosis",
                             "hourly_aggregation": "left-closed hourly arithmetic mean of every raw sample, without deduplication or time weighting",
                             "missing_values": "linear interpolation with linear endpoint extrapolation, matching MATLAB fillmissing defaults",
                             "comparison": "no timestamp shifts, scale changes, or data alterations to force a match"},
               "limits": ["Current archive bytes describe historical 2019 loads; download freshness does not establish the original publication version",
                          "Matching zonal source inputs is not independent validation of within-zone bus allocation", "The released naive chronology combines the autumn repeated local hour and interpolates missing bins, including spring DST"],
               "versions": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__}}
    (output / "load_audit_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Require hash-verified acquired official archives; never fetch")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.offline, args.output.resolve()), indent=2))
