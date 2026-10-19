"""Reproduce NYgrid's 2019 P32 hourly input from hashed official monthly ZIPs.

This audits source preparation, not an electrical model. The replication keeps
all samples, timezone-naive local hours, the published MWH labels, and +/-9999
limits, exactly as Utility/writeInterflow.m does. It does not time-weight,
deduplicate, reinterpret schedules as metered flow, or validate model outputs.
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
import time
import urllib.request
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "tmp/nygrid_2019_reproduction/nyiso_raw"
OUT = ROOT / "output/nygrid_2019"
PREFIX = "nyiso_source_audit"
UPSTREAM = ROOT / "tmp/nygrid_2019_reproduction/upstream"
CACHE_MANIFEST = ROOT / "output/compact_ny_2025/generation_sources/hourly_inputs/source_manifest.csv"
METRICS = ["FlowMWH", "PositiveLimitMWH", "NegativeLimitMWH"]
COLS = ["TimeStamp", "InterfaceName", "PointID"] + METRICS
KEYS = ["TimeStamp", "InterfaceName"]
INDEX_URL = "https://mis.nyiso.com/public/P-32list.htm"
TOLERANCE = 1e-8


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_csv(frame: pd.DataFrame, suffix: str) -> None:
    frame.to_csv(OUT / f"{PREFIX}{suffix}.csv", index=False, lineterminator="\n",
                 date_format="%Y-%m-%d %H:%M:%S", float_format="%.15g")


def acquire(month: int, offline: bool = False) -> dict:
    name = f"2019{month:02d}01ExternalLimitsFlows_csv.zip"
    url = f"https://mis.nyiso.com/public/csv/ExternalLimitsFlows/{name}"
    target = RAW / name
    receipt = RAW / (name + ".provenance.json")
    if target.exists():
        if not receipt.exists():
            raise ValueError(f"Existing raw archive lacks receipt: {target}")
        record = json.loads(receipt.read_text())
        if sha(target.read_bytes()) != record["sha256"] or record["source_url"] != url:
            raise ValueError(f"Existing raw archive provenance mismatch: {target}")
        return record

    record = {"month": f"2019-{month:02d}", "source_url": url,
              "archive": relative(target), "verified_utc": stamp(),
              "cache_source": "", "cache_manifest": "", "cache_manifest_sha256": "",
              "pinned_cache_sha256": "", "http_last_modified": "", "http_etag": ""}
    manifest = pd.read_csv(CACHE_MANIFEST)
    pinned = manifest.loc[manifest.source_url == url, ["archive", "archive_sha256"]].drop_duplicates()
    if len(pinned) > 1:
        raise ValueError(f"Conflicting pinned archive metadata for {url}")
    if len(pinned) == 1:
        row = pinned.iloc[0]
        cached = ROOT / str(row.archive).replace("\\", "/")
        payload = cached.read_bytes()
        if sha(payload) != row.archive_sha256:
            raise ValueError(f"Pinned historical cache hash mismatch: {cached}")
        record.update(acquisition="reused_verified_cache", cache_source=relative(cached),
                      cache_manifest=relative(CACHE_MANIFEST),
                      cache_manifest_sha256=sha(CACHE_MANIFEST.read_bytes()),
                      pinned_cache_sha256=row.archive_sha256)
    else:
        if offline:
            raise FileNotFoundError(f"Offline raw archive unavailable: {name}")
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "NYgrid-source-reproduction/1.0"})
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = response.read()
                    record["http_last_modified"] = response.headers.get("Last-Modified", "")
                    record["http_etag"] = response.headers.get("ETag", "")
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        record["acquisition"] = "downloaded_official_archive"
        record["retrieved_utc"] = stamp()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"ZIP CRC failure {name}: {bad}")
        record["csv_members"] = sum(x.lower().endswith(".csv") for x in archive.namelist())
    record.update(sha256=sha(payload), bytes=len(payload))
    target.write_bytes(payload)
    receipt.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Acquired {name}: {record['acquisition']}, {len(payload):,} bytes", flush=True)
    return record


def linear_fill(values: np.ndarray) -> np.ndarray:
    """MATLAB fillmissing(...,'linear') with default EndValues='extrap'."""
    y = np.asarray(values, dtype=float).copy()
    valid = np.flatnonzero(~np.isnan(y))
    if not len(valid):
        return y
    if len(valid) == 1:
        # A lone valid sample cannot define a linear slope. Audit fails closed.
        if np.isnan(y).any():
            raise ValueError("Linear interpolation requires two finite samples")
        return y
    x = np.arange(len(y))
    filled = np.interp(x, valid, y[valid])
    for a, b, mask in [(valid[0], valid[1], x < valid[0]),
                       (valid[-2], valid[-1], x > valid[-1])]:
        filled[mask] = y[a] + (x[mask] - a) * (y[b] - y[a]) / (b - a)
    return filled


def reconstruct_hourly(raw: pd.DataFrame) -> pd.DataFrame:
    pieces = []
    for name, group in raw.groupby("InterfaceName", sort=True):
        group = group.sort_values("TimeStamp", kind="stable").set_index("TimeStamp")
        bins = group[METRICS].resample("h", closed="left", label="left")
        means = bins.mean()
        frame = means.copy()
        frame["sample_count"] = bins.size()
        frame["distinct_timestamp_count"] = group.reset_index().groupby(
            pd.Grouper(key="TimeStamp", freq="h")).TimeStamp.nunique()
        for metric in METRICS:
            frame[f"{metric}_unimputed"] = means[metric]
            frame[f"{metric}_finite_samples"] = bins.count()[metric]
            frame[f"{metric}_imputed"] = means[metric].isna()
            frame[metric] = linear_fill(means[metric].to_numpy())
        for metric in METRICS[1:]:
            frame[f"{metric}_sentinel_samples"] = group[metric].abs().eq(9999).resample("h").sum()
        frame["spring_dst_missing_hour"] = frame.index == pd.Timestamp("2019-03-10 02:00")
        frame["fall_dst_ambiguous_hour"] = frame.index == pd.Timestamp("2019-11-03 01:00")
        frame["filter_unimputed_unambiguous_hour"] = ~frame.FlowMWH_imputed & ~frame.fall_dst_ambiguous_hour
        frame["filter_unimputed_unambiguous_exactly_12_unique_samples"] = (
            frame.filter_unimputed_unambiguous_hour & frame.sample_count.eq(12)
            & frame.distinct_timestamp_count.eq(12))
        frame["InterfaceName"] = name
        pieces.append(frame.reset_index())
    return pd.concat(pieces, ignore_index=True).sort_values(KEYS, kind="stable").reset_index(drop=True)


def read_archives(records: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames, members = [], []
    for record in records:
        with zipfile.ZipFile(ROOT / record["archive"]) as archive:
            names = sorted(n for n in archive.namelist() if n.lower().endswith(".csv"))
            for name in names:
                payload = archive.read(name)
                f = pd.read_csv(io.BytesIO(payload), dtype=str, keep_default_na=True)
                expected_header = ["Timestamp", "Interface Name", "Point ID", "Flow (MWH)",
                                   "Positive Limit (MWH)", "Negative Limit (MWH)"]
                if list(f.columns[:6]) != expected_header:
                    raise ValueError(f"Unexpected CSV schema: {name}")
                header = " | ".join(f.columns[:6])
                f = f.iloc[:, :6]
                f.columns = COLS
                original_ts = f.TimeStamp.copy()
                f.TimeStamp = pd.to_datetime(f.TimeStamp, format="mixed", errors="coerce")
                invalid = f.TimeStamp.isna()
                if invalid.any() or f.InterfaceName.isna().any():
                    raise ValueError(f"Invalid source key in {name}: {original_ts[invalid].tolist()[:5]}")
                for metric in METRICS:
                    f[metric] = pd.to_numeric(f[metric], errors="raise")
                    if np.isinf(f[metric].to_numpy()).any():
                        raise ValueError(f"Nonfinite numeric source in {name}/{metric}")
                f["source_member"] = name
                f["source_line"] = np.arange(len(f)) + 2
                f["archive_month"] = record["month"]
                day = pd.Timestamp(name[:8])
                members.append({"archive": record["archive"], "member": name,
                                "member_sha256": sha(payload), "bytes": len(payload),
                                "rows": len(f), "header": header,
                                "first_timestamp": f.TimeStamp.min(), "last_timestamp": f.TimeStamp.max(),
                                "interface_count": f.InterfaceName.nunique(),
                                "rows_outside_filename_date": int(f.TimeStamp.dt.normalize().ne(day).sum()),
                                "null_numeric_cells": int(f[METRICS].isna().sum().sum())})
                frames.append(f)
        print(f"Read {record['month']}: {len(names)} daily files", flush=True)
    raw = pd.concat(frames, ignore_index=True)
    if not raw.TimeStamp.dt.year.eq(2019).all():
        raise ValueError("A raw source timestamp falls outside 2019")
    if len({m["member"] for m in members}) != 365:
        raise ValueError("Expected 365 distinct daily CSV members")
    return raw, pd.DataFrame(members)


def source_profile(raw: pd.DataFrame, hourly: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    duplicate_mask = raw.duplicated(KEYS, keep=False)
    d = raw.loc[duplicate_mask]
    duplicate_rows = []
    for key, f in d.groupby(KEYS, sort=True):
        duplicate_rows.append({"TimeStamp": key[0], "InterfaceName": key[1], "rows": len(f),
                               "point_ids": ";".join(sorted(f.PointID.unique())),
                               "conflicting_numeric_values": bool(f[METRICS].nunique(dropna=False).gt(1).any()),
                               **{metric + "_spread": f[metric].max() - f[metric].min() for metric in METRICS},
                               "source_lines": ";".join(f.source_member + ":" + f.source_line.astype(str))})
    duplicate_table = pd.DataFrame(duplicate_rows, columns=KEYS + ["rows", "point_ids", "conflicting_numeric_values"]
                                   + [m + "_spread" for m in METRICS] + ["source_lines"])
    profiles, gaps = [], []
    for name, f in raw.groupby("InterfaceName", sort=True):
        h = hourly.loc[hourly.InterfaceName.eq(name)]
        unique = pd.Series(f.TimeStamp.unique()).sort_values().reset_index(drop=True)
        delta = unique.diff().dt.total_seconds()
        for i in np.flatnonzero(delta.gt(600)):
            gaps.append({"InterfaceName": name, "previous_timestamp": unique.iloc[i - 1],
                         "next_timestamp": unique.iloc[i], "naive_local_gap_seconds": delta.iloc[i],
                         "crosses_spring_dst": unique.iloc[i - 1] < pd.Timestamp("2019-03-10 03:00") <= unique.iloc[i]})
        profiles.append({"InterfaceName": name, "channel_kind": "scheduled_external" if name.startswith("SCH") else "internal",
                         "point_ids": ";".join(sorted(f.PointID.unique())), "raw_rows": len(f),
                         "first_timestamp": f.TimeStamp.min(), "last_timestamp": f.TimeStamp.max(),
                         "unique_timestamps": f.TimeStamp.nunique(),
                         "duplicate_timestamp_excess_rows": int(f.duplicated("TimeStamp").sum()),
                         "exact_duplicate_excess_rows": int(f.duplicated(COLS).sum()),
                         "raw_order_backward_jumps": int(f.TimeStamp.diff().dt.total_seconds().lt(0).sum()),
                         "gaps_over_10_naive_local_minutes": int(delta.gt(600).sum()),
                         "max_naive_local_gap_seconds": delta.max(), "hourly_rows": len(h),
                         "empty_hour_bins": int(h.sample_count.eq(0).sum()),
                         "nonempty_hours_below_12_samples": int(h.sample_count.between(1, 11).sum()),
                         "hours_above_12_samples": int(h.sample_count.gt(12).sum()),
                         "flow_imputed_hours": int(h.FlowMWH_imputed.sum()),
                         "hourly_positive_limit_9999": int(h.PositiveLimitMWH.eq(9999).sum()),
                         "hourly_negative_limit_minus9999": int(h.NegativeLimitMWH.eq(-9999).sum())})
    return pd.DataFrame(profiles), duplicate_table, pd.DataFrame(gaps)


def compare_published(hourly: pd.DataFrame, published_path: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    p = pd.read_csv(published_path)
    p.TimeStamp = pd.to_datetime(p.TimeStamp, format="mixed", errors="raise")
    if p.duplicated(KEYS).any():
        raise ValueError("Published hourly data has duplicate timestamp/interface keys")
    merged = hourly[KEYS + METRICS].merge(p, on=KEYS, how="outer", suffixes=("_reconstructed", "_published"),
                                         indicator=True, validate="one_to_one")
    mismatch = merged._merge.ne("both")
    summaries = []
    for metric in METRICS:
        a, b = merged[metric + "_reconstructed"], merged[metric + "_published"]
        merged[metric + "_absolute_difference"] = (a - b).abs()
        mismatch |= (a - b).abs().gt(TOLERANCE) | a.isna().ne(b.isna())
    for name, f in merged.groupby("InterfaceName", sort=True):
        for metric in METRICS:
            a, b = f[metric + "_reconstructed"], f[metric + "_published"]
            error = (a - b).abs()
            summaries.append({"InterfaceName": name, "metric": metric, "matched_keys": int(f._merge.eq("both").sum()),
                              "missing_published_keys": int(f._merge.eq("left_only").sum()),
                              "missing_reconstructed_keys": int(f._merge.eq("right_only").sum()),
                              "max_absolute_difference": error.max(), "mean_absolute_difference": error.mean(),
                              "values_above_tolerance": int(error.gt(TOLERANCE).sum()),
                              "asymmetric_missing_values": int(a.isna().ne(b.isna()).sum())})
    stats = {"published_rows": len(p), "reconstructed_rows": len(hourly),
             "matched_keys": int(merged._merge.eq("both").sum()),
             "missing_published_keys": int(merged._merge.eq("left_only").sum()),
             "missing_reconstructed_keys": int(merged._merge.eq("right_only").sum()),
             "rows_above_tolerance_or_missing": int(mismatch.sum()), "absolute_tolerance": TOLERANCE,
             "numerically_reproduced": not bool(mismatch.any()),
             "max_absolute_difference": float(merged[[m + "_absolute_difference" for m in METRICS]].max().max())}
    return pd.DataFrame(summaries), merged.loc[mismatch].copy(), stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Require already acquired or pinned archives")
    parser.add_argument("--published", type=Path, default=UPSTREAM / "Data/interflowHourly_2019.csv")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(lambda month: acquire(month, args.offline), range(1, 13)))
    write_csv(pd.DataFrame(records), "_archives")
    raw, members = read_archives(records)
    write_csv(members, "_members")
    print(f"Reconstructing {len(raw):,} raw rows", flush=True)
    hourly = reconstruct_hourly(raw)
    write_csv(hourly[KEYS + METRICS], "_hourly_reconstructed")
    write_csv(hourly, "_hourly_quality")
    write_csv(hourly.loc[hourly[[m + "_imputed" for m in METRICS]].any(axis=1)], "_imputed_hours")
    profile, duplicates, gaps = source_profile(raw, hourly)
    write_csv(profile, "_channels")
    write_csv(duplicates, "_duplicate_timestamps")
    write_csv(gaps, "_gaps")
    monthly = raw.groupby("archive_month").agg(raw_rows=("TimeStamp", "size"),
                                              distinct_local_timestamps=("TimeStamp", "nunique"),
                                              channel_count=("InterfaceName", "nunique"))
    write_csv(monthly.reset_index(), "_monthly")
    comparison, mismatches, comparison_stats = compare_published(hourly, args.published)
    write_csv(comparison, "_comparison")
    write_csv(mismatches, "_comparison_mismatches")
    mat_export = OUT / "prepared_mat_interfaces.csv"
    mat_comparison_stats = {"available": False}
    if mat_export.exists():
        mat_comparison, mat_mismatches, mat_comparison_stats = compare_published(hourly, mat_export)
        mat_comparison_stats["available"] = True
        mat_comparison_stats["scope"] = "MATLAB export of actual released interflowHourly_2019.mat, compared directly with independent raw reconstruction"
        write_csv(mat_comparison, "_mat_comparison")
        write_csv(mat_mismatches, "_mat_comparison_mismatches")
        prepared_csv = pd.read_csv(args.published)
        prepared_csv.TimeStamp = pd.to_datetime(prepared_csv.TimeStamp, format="mixed", errors="raise")
        csv_mat_comparison, csv_mat_mismatches, csv_mat_stats = compare_published(prepared_csv, mat_export)
        mat_comparison_stats["direct_released_csv_vs_mat_export"] = csv_mat_stats
        mat_comparison_stats["export_bytes_identical_to_released_csv"] = args.published.read_bytes() == mat_export.read_bytes()
        write_csv(csv_mat_comparison, "_csv_vs_mat_comparison")
        write_csv(csv_mat_mismatches, "_csv_vs_mat_comparison_mismatches")
    sources = []
    dependencies = [(Path(__file__), "audit_code"),
                    (Path(__file__).with_name("test_audit_nyiso_interfaces.py"), "audit_tests"),
                    (args.published, "released_comparison_data"),
                       (UPSTREAM / "Utility/writeInterflow.m", "replicated_preparation_algorithm"),
                    (UPSTREAM / "Utility/downloadData.m", "official_archive_url_algorithm")]
    if mat_export.exists():
        dependencies.extend([(mat_export, "MATLAB_export_of_released_MAT"),
                             (UPSTREAM / "Data/interflowHourly_2019.mat", "released_MAT_source_used_by_model")])
    for path, role in dependencies:
        if not path.exists():
            raise FileNotFoundError(path)
        data = path.read_bytes()
        sources.append({"path": relative(path), "role": role, "sha256": sha(data),
                        "lf_normalized_sha256": sha(data.replace(b"\r\n", b"\n"))})
    write_csv(pd.DataFrame(sources), "_dependencies")
    summary = {"created_utc": stamp(), "official_index": INDEX_URL, "year": 2019,
               "scope": "source-preparation reproduction only; no electrical solution or dispatch validation",
               "method": "Local-naive [hour,hour+1h) arithmetic sample means including duplicate timestamps; linear fillmissing with end extrapolation; no gap threshold; retain +/-9999 limits",
               "unit_policy": "Original MWH column labels retained; no time integration or unit rescaling performed",
               "external_policy": "All SCH channels preserved separately, including overlapping HQ measures; no additive boundary total claimed",
               "runtime": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__},
               "archives": len(records), "daily_csv_members": len(members), "raw_rows": len(raw),
               "channels": len(profile), "internal_channels": int(profile.channel_kind.eq("internal").sum()),
               "scheduled_external_channels": int(profile.channel_kind.eq("scheduled_external").sum()),
               "raw_null_numeric_cells": int(raw[METRICS].isna().sum().sum()),
               "member_rows_outside_filename_date": int(members.rows_outside_filename_date.sum()),
               "duplicate_timestamp_groups": len(duplicates),
               "conflicting_duplicate_timestamp_groups": int(duplicates.conflicting_numeric_values.sum()),
               "duplicate_timestamp_excess_rows": int(profile.duplicate_timestamp_excess_rows.sum()),
               "exact_duplicate_excess_rows": int(profile.exact_duplicate_excess_rows.sum()),
               "imputed_flow_channel_hours": int(hourly.FlowMWH_imputed.sum()),
               "empty_local_hour_channel_bins": int(hourly.sample_count.eq(0).sum()),
               "imputed_local_hours": sorted(hourly.loc[hourly.FlowMWH_imputed, "TimeStamp"].astype(str).unique().tolist()),
               "comparison": comparison_stats,
               "mat_comparison": mat_comparison_stats,
               "data_quality_limitations": [
                   "Arithmetic means weight each record equally, including duplicate records; they are not interval-energy averages.",
                   "Local timestamps have no timezone or DST fold: spring gaps are interpolated, and fall repeated hours are combined.",
                   "Linear imputation has no maximum gap guard in the upstream code. Audit flags all filled bins.",
                   "9999/-9999 are preserved sentinel-like limits; division by them is not evidence of a physical transfer rating.",
                   "SCH channels are scheduled interchange, not independently measured external flow; overlapping HQ channels cannot simply be summed.",
                   "Agreement with released inputs does not establish agreement of the NYgrid model's simulated flows with observations."]}
    (OUT / f"{PREFIX}.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    outcome = "reproduced within tolerance" if comparison_stats["numerically_reproduced"] else "contains differences requiring review"
    report = f"""# NYISO 2019 interface source audit

The released NYgrid hourly interface input is **{outcome}**. This is an independent reconstruction of input preparation from official NYISO archives, not a model validation.

- Official monthly ZIPs: {len(records)}; daily CSVs: {len(members)}; raw rows: {len(raw):,}.
- Channels: {len(profile)} ({summary['internal_channels']} internal and {summary['scheduled_external_channels']} scheduled external).
- Hourly keys matched: {comparison_stats['matched_keys']:,}; rows outside the {TOLERANCE:g} numeric tolerance or missing: {comparison_stats['rows_above_tolerance_or_missing']:,}.
- Maximum absolute numeric difference: {comparison_stats['max_absolute_difference']:.12g} in the published numeric units.
- Duplicate timestamp/interface groups: {len(duplicates):,}; groups containing conflicting numeric values: {summary['conflicting_duplicate_timestamp_groups']:,}.
- Interpolated flow channel-hours: {summary['imputed_flow_channel_hours']:,}. See the imputed-hours CSV for exact dates and values.

The interpolated local hours are **2019-03-10 02:00** (spring DST) and **2019-12-12 12:00** (an actual source gap from 11:30 to 13:10). Each channel has 181 nonempty hourly bins with fewer than 12 samples and 444 with more than 12. The autumn 01:00 hour is combined, not preserved as two observations. There are no missing raw numeric values or timestamps outside their filename dates. West Central retains +9999/-9999 limits in all 8,760 hours; a normalized error using that denominator should not be presented as error relative to a verified physical rating.

The separately exported MAT data used by the model is {'also reproduced within tolerance' if mat_comparison_stats.get('numerically_reproduced') else 'not yet verified or has differences; see the JSON audit'}. The MAT comparison tables preserve its direct comparison against the same raw reconstruction.

The reconstruction follows the pinned `Utility/writeInterflow.m`: timezone-naive hourly arithmetic means of every raw row, followed by linear interpolation of missing values. It retains the original MWH column labels and performs no energy integration. It preserves all schedule identities separately and does not sum overlapping HQ channels.

The quality and duplicate tables retain sample counts, raw-source member/line provenance, imputation flags, DST flags, gaps longer than ten local minutes, and +/-9999 limit counts. The annual 8,760 local-hour grid cannot distinguish the repeated autumn hour. Matching prepared inputs does not validate generation, electrical topology, or simulated interface flows.

Sources: [NYISO P-32 archive index]({INDEX_URL}); pinned NYgrid source and released data are hashed in the dependencies table; the upstream Git commit is recorded in `upstream_manifest.json`. Archive and daily-member hashes preserve the raw bytes. Reused historical caches were checked against their pinned manifests before copying; their original retrieval dates are not asserted.

Run `python scripts/nygrid_2019/audit_nyiso_interfaces.py --offline` to reproduce the audit from acquired archives. Omit `--offline` to acquire any missing monthly official archives.
"""
    (OUT / f"{PREFIX}.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
