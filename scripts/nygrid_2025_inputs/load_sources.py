"""Build unscaled 2025 NYISO load, interface and interchange source tables.

Canonical load hours are the 8,760 physical hours of the New York local year,
identified uniquely in UTC. Load EST/EDT labels are preserved and checked.
P32 has no timezone field: its fall fold is resolved only from the explicit
clock rewind in each channel's raw file order; this inference is recorded.
P32 canonical means use forward sample hold with complete bracketing and a
600-second maximum source gap. Unqualified values stay NaN. Raw-sample hourly
arithmetic means are retained separately; neither gaps nor DST are interpolated.

No model scale, bus allocation, dispatch, or interface fitting is performed.
Run `python scripts/nygrid_2025_inputs/load_sources.py`; add `--offline` to
rebuild from hash-verified acquired sources only.
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
DEFAULT_OUTPUT = ROOT / "output/nygrid_2025_inputs/load_source"
LEGACY_MANIFEST = ROOT / "output/compact_ny_2025/generation_sources/hourly_inputs/source_manifest.csv"
TZ = "America/New_York"
YEAR = 2025
MAX_GAP_SECONDS = 600
LOAD_ZONES = {"CAPITL": "F", "CENTRL": "C", "DUNWOD": "I", "GENESE": "B",
              "HUD VL": "G", "LONGIL": "K", "MHK VL": "E", "MILLWD": "H",
              "N.Y.C.": "J", "NORTH": "D", "WEST": "A"}
LOAD_HEADER = ["Time Stamp", "Time Zone", "Name", "PTID", "Integrated Load"]
FLOW_HEADER = ["Timestamp", "Interface Name", "Point ID", "Flow (MWH)",
               "Positive Limit (MWH)", "Negative Limit (MWH)"]
FLOW_VALUES = ["flow_mw", "positive_limit_mw", "negative_limit_mw"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, lineterminator="\n", float_format="%.15g",
                 date_format="%Y-%m-%dT%H:%M:%SZ")


def physical_hours() -> pd.DatetimeIndex:
    hours = pd.date_range(f"{YEAR}-01-01", f"{YEAR + 1}-01-01", inclusive="left", freq="h", tz=TZ).tz_convert("UTC")
    require(len(hours) == 8760 and hours.is_unique, "Unexpected physical-hour calendar")
    require(np.all(np.diff(hours.asi8) == 3600 * 10**9), "Physical hours are not consecutive")
    return hours


def hour_catalog() -> pd.DataFrame:
    hours = physical_hours()
    local = hours.tz_convert(TZ)
    return pd.DataFrame({"hour_index": np.arange(1, len(hours) + 1), "timestamp_utc": hours,
                         "local_timestamp": local.strftime("%Y-%m-%dT%H:%M:%S"),
                         "time_zone": local.strftime("%Z"),
                         "utc_offset_minutes": [int(t.utcoffset().total_seconds() / 60) for t in local],
                         "dst_fold": [int(t.fold) for t in local]})


def legacy_receipts() -> dict[str, dict]:
    if not LEGACY_MANIFEST.exists():
        return {}
    frame = pd.read_csv(LEGACY_MANIFEST)
    records = {}
    for url, group in frame.groupby("source_url", sort=False):
        unique = group[["archive", "archive_sha256"]].drop_duplicates()
        require(len(unique) == 1, f"Ambiguous old cache receipt: {url}")
        row = unique.iloc[0]
        records[url] = {"path": ROOT / str(row.archive).replace("\\", "/"), "sha256": row.archive_sha256}
    return records


def acquire(family: str, year: int, month: int, output: Path, old: dict, offline: bool) -> dict:
    name = f"{year}{month:02d}01{family}_csv.zip"
    url = f"https://mis.nyiso.com/public/csv/{family}/{name}"
    raw_dir = output / "raw"
    target, receipt_path = raw_dir / name, raw_dir / (name + ".provenance.json")
    if target.exists():
        require(receipt_path.exists(), f"Existing archive lacks receipt: {target}")
        record = json.loads(receipt_path.read_text(encoding="utf-8"))
        payload = target.read_bytes()
        require(record["source_url"] == url and record["sha256"] == digest(payload), f"Existing source mismatch: {target}")
        access = "verified_existing_receipt"
    elif url in old and old[url]["path"].exists():
        cached = old[url]
        payload = cached["path"].read_bytes()
        require(digest(payload) == cached["sha256"], f"Historical cache hash mismatch: {cached['path']}")
        record = {"family": family, "month": f"{year}-{month:02d}", "source_url": url,
                  "acquisition": "verified_legacy_cache_copy", "copied_utc": stamp(),
                  "legacy_cache_path": relative(cached["path"]),
                  "legacy_cache_manifest": relative(LEGACY_MANIFEST),
                  "legacy_cache_manifest_sha256": digest(LEGACY_MANIFEST.read_bytes()),
                  "original_retrieval_time": "not_asserted"}
        access = "copied_verified_legacy_cache_this_run"
    else:
        require(not offline, f"Offline source missing: {name}")
        record = {"family": family, "month": f"{year}-{month:02d}", "source_url": url,
                  "acquisition": "fresh_official_download"}
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "NYgrid2025-UTC-source-inputs/1.0"})
                with urllib.request.urlopen(request, timeout=45) as response:
                    payload = response.read()
                    record.update(http_status=response.status, http_last_modified=response.headers.get("Last-Modified", ""),
                                  http_etag=response.headers.get("ETag", ""), retrieved_utc=stamp())
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        access = "downloaded_this_run"
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        require(archive.testzip() is None, f"ZIP CRC failed: {name}")
        members = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        expected = {t.strftime("%Y%m%d") + family + ".csv" for t in
                    pd.date_range(f"{year}-{month:02d}-01", periods=pd.Period(f"{year}-{month:02d}").days_in_month, freq="D")}
        require(set(members) == expected and len(members) == len(expected), f"Unexpected archive member coverage: {name}")
    if not target.exists():
        record.update(archive=relative(target), sha256=digest(payload), bytes=len(payload))
        target.write_bytes(payload)
        receipt_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {**record, "archive": relative(target), "bytes": len(payload), "csv_members": len(members),
            "access_this_run": access, "verified_utc": stamp()}


def load_utc(local: pd.DatetimeIndex, labels: np.ndarray) -> pd.DatetimeIndex:
    """Respect the load source's explicit EST/EDT field, including both folds."""
    require(set(labels).issubset({"EST", "EDT"}), "Unexpected explicit load timezone")
    offsets = np.asarray([5 if t == "EST" else 4 for t in labels])
    utc = (local + pd.to_timedelta(offsets, unit="h")).tz_localize("UTC")
    check = utc.tz_convert(TZ)
    require(np.array_equal(check.tz_localize(None).asi8, local.asi8), "Load source timestamp/zone conflicts with New York calendar")
    require(np.array_equal(check.strftime("%Z"), labels), "Load source timezone label conflicts with calendar")
    return utc


def p32_utc(local: pd.DatetimeIndex) -> tuple[pd.DatetimeIndex, dict]:
    """Resolve only source-supported fall folds, before sorting or deduplication."""
    probe = local.tz_localize(TZ, ambiguous="NaT", nonexistent="raise")
    ambiguous = np.asarray(probe.isna())
    rewinds = np.flatnonzero(np.diff(local.asi8) < -30 * 60 * 10**9) + 1
    ambiguous_flags = np.zeros(len(local), dtype=bool)
    if ambiguous.any():
        supported = [i for i in rewinds if ambiguous[i] and ambiguous[i - 1]]
        require(len(supported) == 1, "Ambiguous P32 fall hour lacks one explicit source clock rewind")
        boundary = supported[0]
        require(ambiguous[:boundary].any() and ambiguous[boundary:].any(), "Both source DST folds are required")
        ambiguous_flags[:boundary] = True  # First occurrence is EDT, second EST.
    resolved = local.tz_localize(TZ, ambiguous=ambiguous_flags, nonexistent="raise").tz_convert("UTC")
    return resolved, {"ambiguous_local_rows": int(ambiguous.sum()),
                      "fall_fold_resolved_from_raw_order": bool(ambiguous.any()),
                      "raw_local_clock_rewinds": int(np.count_nonzero(np.diff(local.asi8) < 0)),
                      "out_of_order_utc_rows": int(np.count_nonzero(np.diff(resolved.asi8) < 0))}


def read_sources(receipts: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    loads, flows, members, timing = [], [], [], []
    for receipt in receipts:
        path = ROOT / receipt["archive"]
        require(digest(path.read_bytes()) == receipt["sha256"], f"Archive changed after verification: {path}")
        family = receipt["family"]
        with zipfile.ZipFile(path) as archive:
            for member in sorted(archive.namelist()):
                # The January 2026 archive supplies only the Jan 1 endpoint day.
                if receipt["month"] == "2026-01" and member != "20260101ExternalLimitsFlows.csv":
                    continue
                payload = archive.read(member)
                f = pd.read_csv(io.BytesIO(payload), dtype=str)
                expected = LOAD_HEADER if family == "palIntegrated" else FLOW_HEADER
                require(list(f.columns) == expected, f"Unexpected raw schema: {member}")
                f["source_member"] = member
                f["source_line"] = np.arange(len(f)) + 2
                f["source_archive"] = receipt["archive"]
                f["source_url"] = receipt["source_url"]
                if family == "palIntegrated":
                    f = f.rename(columns=dict(zip(LOAD_HEADER, ["local_timestamp", "source_time_zone", "zone_name", "ptid", "load_mw"])))
                    local = pd.DatetimeIndex(pd.to_datetime(f.local_timestamp, format="mixed", errors="raise"))
                    require(set(f.zone_name).issubset(LOAD_ZONES), "Unknown load zone")
                    f["timestamp_utc"] = load_utc(local, f.source_time_zone.to_numpy())
                    f["zone"] = f.zone_name.map(LOAD_ZONES)
                    f["load_mw"] = pd.to_numeric(f.load_mw, errors="raise")
                    require(np.isfinite(f.load_mw).all(), f"Nonfinite raw load: {member}")
                    require(np.all(local.minute == 0) and np.all(local.second == 0), f"Integrated load timestamp is not hourly: {member}")
                    loads.append(f)
                else:
                    f = f.rename(columns=dict(zip(FLOW_HEADER, ["local_timestamp", "channel", "point_id", *FLOW_VALUES])))
                    local = pd.DatetimeIndex(pd.to_datetime(f.local_timestamp, format="mixed", errors="raise"))
                    f["timestamp_utc"] = pd.Series(pd.NaT, index=f.index, dtype="datetime64[ns, UTC]")
                    for name, group in f.groupby("channel", sort=False):
                        idx = group.index.to_numpy()
                        converted, report = p32_utc(local[idx])
                        f.loc[idx, "timestamp_utc"] = pd.Series(converted, index=idx)
                        timing.append({"source_member": member, "channel": name, **report})
                    f["inferred_time_zone"] = f.timestamp_utc.dt.tz_convert(TZ).dt.strftime("%Z")
                    f["source_timezone_provided"] = False
                    for name in FLOW_VALUES:
                        f[name] = pd.to_numeric(f[name], errors="raise")
                        require(not np.isinf(f[name]).any(), f"Infinite P32 value: {member}/{name}")
                    flows.append(f)
                expected_day = pd.to_datetime(member[:8], format="%Y%m%d")
                require(np.all(local.normalize() == expected_day), f"Source timestamp outside filename day: {member}")
                members.append({"family": family, "source_archive": receipt["archive"], "source_member": member,
                                "member_sha256": digest(payload), "bytes": len(payload), "raw_rows": len(f),
                                "source_url": receipt["source_url"], "endpoint_day_only": receipt["month"] == "2026-01"})
    load = pd.concat(loads, ignore_index=True)
    flow = pd.concat(flows, ignore_index=True)
    require(set(load.zone_name) == set(LOAD_ZONES), "Incomplete load zone identity set")
    require(load.groupby("zone").ptid.nunique().eq(1).all(), "Changing load-zone PTID")
    require(flow.groupby("channel").point_id.nunique().eq(1).all(), "Changing P32 channel identity")
    return load, flow, pd.DataFrame(members), pd.DataFrame(timing)


def canonical_load(raw: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    groups = raw.groupby(["timestamp_utc", "zone"], sort=True).load_mw.agg(["mean", "min", "max", "size"])
    expected = pd.MultiIndex.from_product([pd.DatetimeIndex(catalog.timestamp_utc), list("ABCDEFGHIJK")], names=["timestamp_utc", "zone"])
    require(groups.index.difference(expected).empty, "Unexpected load hour outside 2025 physical year")
    h = groups.reindex(expected).reset_index().rename(columns={"mean": "load_mw", "min": "minimum_source_load_mw",
        "max": "maximum_source_load_mw", "size": "source_rows"})
    h["source_rows"] = h.source_rows.fillna(0).astype(int)
    h["coverage_qualified"] = h.source_rows.gt(0) & (h.maximum_source_load_mw - h.minimum_source_load_mw).abs().le(1e-8)
    h.loc[~h.coverage_qualified, "load_mw"] = np.nan
    h["zone_name"] = h.zone.map({v: k for k, v in LOAD_ZONES.items()})
    h = h.merge(catalog, on="timestamp_utc", how="left", validate="many_to_one")
    return h.sort_values(["hour_index", "zone"]).reset_index(drop=True)


def forward_hourly(group: pd.DataFrame, hours: pd.DatetimeIndex, max_gap: int = MAX_GAP_SECONDS) -> pd.DataFrame:
    """Average duplicate timestamp values, integrate valid bracketed intervals."""
    averaged = group.groupby("timestamp_utc", sort=True)[FLOW_VALUES].mean()
    aggregate = group.groupby("timestamp_utc", sort=True).flow_mw.agg(["size", "min", "max"])
    sentinel_rows = group[["timestamp_utc", "positive_limit_mw", "negative_limit_mw"]].copy()
    sentinel_rows[["positive_limit_mw", "negative_limit_mw"]] = sentinel_rows[["positive_limit_mw", "negative_limit_mw"]].abs().eq(9999)
    limit_sentinels = sentinel_rows.groupby("timestamp_utc", sort=True)[["positive_limit_mw", "negative_limit_mw"]].any().to_numpy(dtype=bool)
    t = averaged.index.asi8 / 1e9
    values = averaged.to_numpy()
    require(len(t) >= 2 and np.all(np.diff(t) > 0), "Insufficient unique P32 timestamps")
    n = len(hours)
    start, end = hours[0].timestamp(), hours[-1].timestamp() + 3600
    integrated, coverage = np.zeros((n, len(FLOW_VALUES))), np.zeros((n, len(FLOW_VALUES)))
    bracketed, largest_gap = np.zeros(n), np.zeros(n)
    duplicate_spread, duplicate_samples = np.zeros(n), np.zeros(n, dtype=int)
    hourly_limit_sentinels = np.zeros((n, 2), dtype=bool)
    spread = (aggregate["max"] - aggregate["min"]).to_numpy()
    count = aggregate["size"].to_numpy()
    lo = max(0, np.searchsorted(t, start, side="right") - 1)
    hi = min(len(t) - 1, np.searchsorted(t, end, side="left"))
    for i in range(lo, hi):
        left, right = max(t[i], start), min(t[i + 1], end)
        if right <= left:
            continue
        gap = t[i + 1] - t[i]
        finite = np.isfinite(values[i])
        while left < right:
            hour = min(n - 1, int((left - start) // 3600))
            boundary = min(right, start + (hour + 1) * 3600)
            seconds = boundary - left
            bracketed[hour] += seconds
            largest_gap[hour] = max(largest_gap[hour], gap)
            duplicate_spread[hour] = max(duplicate_spread[hour], spread[i], spread[i + 1])
            duplicate_samples[hour] += int(count[i] > 1 or count[i + 1] > 1)
            # Only the left timestamp supplies the held value on this interval.
            # Detect sentinels before averaging same-timestamp source rows: a
            # mixed finite/9999 duplicate must never become a usable limit.
            hourly_limit_sentinels[hour] |= limit_sentinels[i]
            if gap <= max_gap:
                integrated[hour, finite] += seconds * values[i, finite]
                coverage[hour, finite] += seconds
            left = boundary
    qualified = np.isclose(coverage, 3600, atol=1e-7, rtol=0)
    rows = pd.DataFrame({"timestamp_utc": hours, "coverage_qualified": qualified[:, 0],
                         "coverage_seconds": coverage[:, 0], "bracketed_seconds": bracketed,
                         "maximum_bracketing_gap_seconds": np.where(bracketed > 0, largest_gap, np.nan),
                         "interval_pieces_touching_duplicate_timestamp": duplicate_samples,
                         "maximum_duplicate_spread_mw": duplicate_spread})
    rows["positive_limit_contains_sentinel"] = hourly_limit_sentinels[:, 0]
    rows["negative_limit_contains_sentinel"] = hourly_limit_sentinels[:, 1]
    for j, name in enumerate(FLOW_VALUES):
        rows[name] = np.where(qualified[:, j], integrated[:, j] / 3600, np.nan)
        rows[f"{name}_covered_seconds"] = coverage[:, j]
    rows["positive_limit_usable"] = qualified[:, 1] & ~hourly_limit_sentinels[:, 0]
    rows["negative_limit_usable"] = qualified[:, 2] & ~hourly_limit_sentinels[:, 1]
    # Keep raw-row arithmetic means as a separate paper-method diagnostic.
    inyear = group.loc[group.timestamp_utc.ge(hours[0]) & group.timestamp_utc.lt(hours[-1] + pd.Timedelta(hours=1))].copy()
    inyear["hour"] = inyear.timestamp_utc.dt.floor("h")
    means = inyear.groupby("hour")[FLOW_VALUES].mean().reindex(hours)
    rows["paper_arithmetic_mean_flow_mw"] = means.flow_mw.to_numpy()
    rows["raw_samples_in_hour"] = inyear.groupby("hour").size().reindex(hours, fill_value=0).to_numpy()
    rows["distinct_source_timestamps_in_hour"] = inyear.groupby("hour").timestamp_utc.nunique().reindex(hours, fill_value=0).to_numpy()
    rows["coverage_failure"] = np.where(rows.coverage_qualified, "", np.where(rows.bracketed_seconds < 3600 - 1e-7,
        "missing_bracket", np.where(rows.maximum_bracketing_gap_seconds > max_gap, "source_gap_over_600s", "nonfinite_source_value")))
    return rows


def build(offline: bool = False, output: Path = DEFAULT_OUTPUT) -> dict:
    started = stamp()
    output.mkdir(parents=True, exist_ok=True)
    (output / "raw").mkdir(exist_ok=True)
    catalog = hour_catalog()
    old = legacy_receipts()
    requests = [(family, YEAR, month) for family in ["palIntegrated", "ExternalLimitsFlows"] for month in range(1, 13)]
    requests.append(("ExternalLimitsFlows", YEAR + 1, 1))
    with ThreadPoolExecutor(max_workers=5) as pool:
        receipts = list(pool.map(lambda p: acquire(*p, output, old, offline), requests))
    print("All 24 monthly sources and the January 2026 boundary archive verified.", flush=True)
    raw_load, raw_flow, members, timing = read_sources(receipts)
    loads = canonical_load(raw_load, catalog)
    channels = raw_flow[["channel", "point_id"]].drop_duplicates().sort_values("channel")
    require(len(channels) == 18, "Unexpected P32 channel set; review before changing the source contract")
    channels["channel_kind"] = np.where(channels.channel.str.startswith("SCH - "), "scheduled_external_exchange", "observed_internal_interface")
    channels["source_timezone_provided"] = False
    channels["timezone_resolution"] = "America_New_York_calendar_and_explicit_raw_order_fall_clock_rewind"
    pieces = []
    hours = pd.DatetimeIndex(catalog.timestamp_utc)
    for row in channels.itertuples():
        block = raw_flow.loc[raw_flow.channel == row.channel]
        h = forward_hourly(block, hours)
        h["channel"] = row.channel
        h["point_id"] = row.point_id
        h["channel_kind"] = row.channel_kind
        pieces.append(h)
        print(f"{row.channel}: {int(h.coverage_qualified.sum())}/8760 strict source-qualified hours", flush=True)
    flows = pd.concat(pieces, ignore_index=True).merge(catalog, on="timestamp_utc", how="left", validate="many_to_one")
    flows = flows.sort_values(["hour_index", "channel"]).reset_index(drop=True)
    load_wide = loads.pivot(index="timestamp_utc", columns="zone", values="load_mw")
    load_wide["total_ny_load_mw"] = load_wide.sum(axis=1, min_count=11)
    load_wide = catalog.merge(load_wide, on="timestamp_utc", how="left", validate="one_to_one")
    flow_wide = catalog.merge(flows.pivot(index="timestamp_utc", columns="channel", values="flow_mw"), on="timestamp_utc", how="left", validate="one_to_one")
    flow_quality_wide = catalog.merge(flows.pivot(index="timestamp_utc", columns="channel", values="coverage_qualified"), on="timestamp_utc", how="left", validate="one_to_one")
    annual_flow = raw_flow.loc[raw_flow.timestamp_utc.ge(hours[0]) & raw_flow.timestamp_utc.lt(hours[-1] + pd.Timedelta(hours=1))]
    dup = annual_flow.loc[annual_flow.duplicated(["timestamp_utc", "channel"], keep=False)]
    duplicate_groups = dup.groupby(["timestamp_utc", "channel"], sort=True).agg(
        raw_rows=("flow_mw", "size"), different_flow_values=("flow_mw", "nunique"),
        minimum_flow_mw=("flow_mw", "min"), maximum_flow_mw=("flow_mw", "max")).reset_index()
    month_quality = flows.assign(local_month=flows.local_timestamp.str[:7]).groupby(["local_month", "channel"], sort=True).agg(
        hours=("coverage_qualified", "size"), qualified_hours=("coverage_qualified", "sum"),
        maximum_bracketing_gap_seconds=("maximum_bracketing_gap_seconds", "max"),
        raw_samples=("raw_samples_in_hour", "sum")).reset_index()
    channel_quality = flows.groupby("channel", sort=True).agg(hours=("coverage_qualified", "size"),
        qualified_hours=("coverage_qualified", "sum"), maximum_bracketing_gap_seconds=("maximum_bracketing_gap_seconds", "max"),
        positive_limit_9999_mean_hours=("positive_limit_mw", lambda s: int(s.eq(9999).sum())),
        positive_limit_contains_sentinel_hours=("positive_limit_contains_sentinel", "sum"),
        negative_limit_contains_sentinel_hours=("negative_limit_contains_sentinel", "sum")).reset_index()
    for name, frame in [("hour_catalog", catalog), ("load_hourly", loads), ("load_wide", load_wide),
                        ("interface_hourly", flows), ("interface_wide", flow_wide), ("interface_quality_wide", flow_quality_wide),
                        ("channels", channels), ("source_receipts", pd.DataFrame(receipts)), ("source_members", members),
                        ("p32_timezone_resolution", timing), ("p32_duplicate_groups", duplicate_groups),
                        ("p32_monthly_quality", month_quality), ("p32_channel_quality", channel_quality),
                        ("unqualified_interface_hours", flows.loc[~flows.coverage_qualified])]:
        write_csv(frame, output / f"{name}.csv")
    write_csv(raw_load, output / "load_raw.csv.gz")
    write_csv(raw_flow, output / "p32_raw.csv.gz")
    write_csv(dup, output / "p32_duplicate_raw_rows.csv.gz")
    summary = {"status": "complete_source_tables_with_explicit_quality_flags", "year": YEAR,
               "created_utc": stamp(), "started_utc": started, "physical_hours": len(catalog), "zones": 11,
               "source_scale": "unscaled_public_MW", "model_gamma_applied": False, "bus_allocation_performed": False,
               "hour_first_utc": hours[0].isoformat(), "hour_last_utc": hours[-1].isoformat(),
               "monthly_2025_archives": 24, "boundary_2026_archives": 1,
               "source_daily_members_consumed": len(members), "load_raw_rows": len(raw_load),
               "load_hour_zone_keys": len(loads), "load_qualified_hour_zone_keys": int(loads.coverage_qualified.sum()),
               "load_hours_all_zones_qualified": int(loads.groupby("hour_index").coverage_qualified.all().sum()),
               "load_conflicting_duplicate_keys": int((loads.maximum_source_load_mw - loads.minimum_source_load_mw).abs().gt(1e-8).sum()),
               "P32_annual_raw_rows": len(annual_flow), "P32_endpoint_day_rows": int(len(raw_flow) - len(annual_flow)),
               "P32_channels": len(channels), "P32_hour_channel_keys": len(flows),
               "P32_qualified_hour_channel_keys": int(flows.coverage_qualified.sum()),
               "P32_hours_all_channels_qualified": int(flows.groupby("hour_index").coverage_qualified.all().sum()),
               "P32_maximum_gap_seconds": float(flows.maximum_bracketing_gap_seconds.max()),
               "P32_duplicate_utc_channel_groups": len(duplicate_groups),
               "P32_conflicting_duplicate_utc_channel_groups": int(duplicate_groups.different_flow_values.gt(1).sum()),
               "P32_fall_fold_resolved_channels": int(timing.fall_fold_resolved_from_raw_order.sum()),
               "P32_raw_out_of_order_utc_rows": int(timing.out_of_order_utc_rows.sum()),
               "P32_positive_limit_sentinel_hour_channel_keys": int(flows.positive_limit_contains_sentinel.sum()),
               "P32_negative_limit_sentinel_hour_channel_keys": int(flows.negative_limit_contains_sentinel.sum()),
               "catalog_EST_hours": int(catalog.time_zone.eq("EST").sum()), "catalog_EDT_hours": int(catalog.time_zone.eq("EDT").sum()),
               "catalog_fall_second_fold_hours": int(catalog.dst_fold.sum()),
               "acquisition_counts": pd.Series([r["acquisition"] for r in receipts]).value_counts().to_dict(),
               "algorithms": {"load": "Official integrated hourly load, source EST/EDT retained; conflicting duplicate/missing keys remain NaN",
                   "P32_time": "No source timezone column; New York calendar plus explicit per-channel raw-order fall clock rewind, fail closed if ambiguous",
                   "P32_mean": "Forward-hold time-weighted mean on [UTC hour, next UTC hour); same-timestamp rows averaged; complete brackets and maximum source gap600s required",
                   "P32_alternative": "Unfilled raw-row arithmetic mean in physical UTC hour, retained only as paper-method diagnostic",
                   "P32_limit_sentinels": "Per-sign flags detect any contributing raw held sample with absolute value9999 before duplicate averaging; mixed sentinel/finite averages are not usable limits",
                   "missing_policy": "No interpolation, extrapolation, long-gap fill, or fabricated spring/fall hour"},
               "sources": {"loads_index": "https://mis.nyiso.com/public/P-58Clist.htm", "interfaces_index": "https://mis.nyiso.com/public/P-32list.htm"},
               "limitations": ["SCH channels are schedules, not observed actual interchange; overlapping HQ channels are retained separately and not summed",
                   "Published P32 Flow (MWH) numeric values are treated as power in MW consistently with the existing source pipeline; no energy rescaling",
                   "P32 EST/EDT is inferred from the calendar and raw clock order, not supplied telemetry",
                   "Source quality flags do not establish model accuracy, physical ratings, bus-level demand, or dispatch validity"],
               "runtime": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__}}
    (output / "quality_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    dependencies = [(Path(__file__), "source_builder"), (Path(__file__).with_name("test_load_sources.py"), "focused_tests")]
    if LEGACY_MANIFEST.exists():
        dependencies.append((LEGACY_MANIFEST, "verified_legacy_cache_receipts"))
    write_csv(pd.DataFrame([{"path": relative(p), "role": role, "sha256": digest(p.read_bytes())} for p, role in dependencies]), output / "code_manifest.csv")
    result_files = sorted(p for p in output.iterdir() if p.is_file() and p.name != "output_manifest.csv")
    write_csv(pd.DataFrame([{"path": relative(p), "bytes": p.stat().st_size, "sha256": digest(p.read_bytes())} for p in result_files]), output / "output_manifest.csv")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    print(json.dumps(build(arguments.offline, arguments.output.resolve()), indent=2))
