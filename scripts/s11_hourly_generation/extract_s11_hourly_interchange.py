"""Build S11's four-region interchange schedule from public NYISO P-32 files.

These are hourly approximations of published SCH point samples, not metered
actual flows. The strict series rejects gaps over 600 s. A separately flagged
applied series holds bracketed gaps up to 3600 s for simulation. Neither series
extrapolates or applies load similarity scaling. The saved S11 mapping omits
separately named ties; they are diagnostic and not automatically additive.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = ROOT / "System Matpower Format/NY_Lite/nyiso_public_cache"
DEFAULT_OUT = ROOT / "output/s11_hourly_generation"
PRIMARY = {"SCH - HQ - NY": "HQ", "SCH - NE - NY": "ISONE",
           "SCH - OH - NY": "ONTARIO", "SCH - PJ - NY": "PJM"}
SUPPLEMENTAL = ["SCH - HQ_CEDARS", "SCH - HQ_IMPORT_EXPORT", "SCH - NPX_CSC",
                "SCH - NPX_1385", "SCH - PJM_NEPTUNE", "SCH - PJM_VFT", "SCH - PJM_HTP"]
CHANNELS = list(PRIMARY) + SUPPLEMENTAL
MAPPING = [
    ("HQ_NY_MOSES", "SCH - HQ - NY", 48, 1.0),
    ("NE_NY_NORTHFIELD", "SCH - NE - NY", 37, .4),
    ("NE_NY_PV", "SCH - NE - NY", 73, .6),
    ("OH_NY_NIAGARA", "SCH - OH - NY", 54, 1.0),
    ("PJM_NY_WATERCURE", "SCH - PJ - NY", 66, .35),
    ("PJM_NY_WRHL", "SCH - PJ - NY", 67, .15),
    ("PJM_NY_RAMAPO", "SCH - PJ - NY", 75, .25),
    ("PJM_NY_GOETHALS", "SCH - PJ - NY", 81, .25),
]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_source(day, cache, out, allow_download):
    """Prefer archived originals; copy only consumed daily files into handoff."""
    member = f"{day}ExternalLimitsFlows.csv"
    target = out / "sources" / "interchange" / member
    record_path = target.with_suffix(".provenance.json")
    archive = cache / f"{day[:6]}_ExternalLimitsFlows" / f"{day[:6]}01ExternalLimitsFlows_csv.zip"
    url = f"https://mis.nyiso.com/public/csv/ExternalLimitsFlows/{day[:6]}01ExternalLimitsFlows_csv.zip"
    if target.exists() and record_path.exists():
        raw = target.read_bytes()
        metadata = json.loads(record_path.read_text(encoding="utf-8"))
        if digest(raw) != metadata["source_sha256"]:
            raise ValueError(f"Changed cached source: {target}")
        return raw, metadata
    if archive.exists():
        archive_bytes = archive.read_bytes()
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
            members = [name for name in z.namelist() if Path(name).name == member]
            if len(members) != 1:
                raise ValueError(f"Expected unique archived {member}")
            raw = z.read(members[0])
        metadata = dict(source_url=url, source_archive_sha256=digest(archive_bytes),
                        source_member=members[0], source_origin="existing_monthly_archive")
    else:
        if not allow_download:
            raise FileNotFoundError(f"Missing {archive}; use --download-edges or supply handoff sources")
        # Historical daily endpoints may expire. The monthly archive retains
        # first-of-next-month records needed to bracket the final hourly mean.
        with urllib.request.urlopen(url, timeout=45) as response:
            archive_bytes = response.read()
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
            members = [name for name in z.namelist() if Path(name).name == member]
            if len(members) != 1:
                raise ValueError(f"Expected unique downloaded {member}")
            raw = z.read(members[0])
        metadata = dict(source_url=url, source_archive_sha256=digest(archive_bytes),
                        source_member=members[0], source_origin="downloaded_monthly_edge_archive")
    metadata.update(source_id=f"NYISO:ExternalLimitsFlows:{day}", day=day,
                    source_sha256=digest(raw), packaged_path=f"sources/interchange/{member}",
                    source_bytes=len(raw))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    record_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8", newline="\n")
    return raw, metadata


def channel_identity(block, name):
    if block.empty or set(block["Interface Name"]) != {name} or block["Point ID"].nunique() != 1:
        raise ValueError(f"Missing or ambiguous channel identity: {name}")
    return int(block["Point ID"].iloc[0])


def hourly_channel(block, starts, max_gap_seconds=600, applied_max_gap_seconds=3600):
    """Integrate forward sample hold with explicit bracket and gap coverage.

    Duplicate minute labels get one mean value, with min/max bounds retained.
    The quality mask uses the full bracketing gap, not just its hourly overlap.
    """
    numeric = pd.to_numeric(block["Flow (MWH)"], errors="raise")
    if not np.isfinite(numeric).all():
        raise ValueError("Nonfinite source schedule")
    b = block.assign(value=numeric).groupby("utc", sort=True).value.agg(["mean", "min", "max", "size"])
    t = b.index.as_unit("ns").asi8 / 1e9
    v, lower, upper, count = (b[c].to_numpy() for c in ["mean", "min", "max", "size"])
    rows = []
    for start in starts:
        s, e = start.timestamp(), start.timestamp() + 3600
        lo, hi = np.searchsorted(t, [s, e], side="right")
        grid = np.unique(np.r_[s, t[lo:hi], e])
        left = np.searchsorted(t, grid[:-1], side="right") - 1
        right = np.searchsorted(t, grid[1:], side="left")
        bracket = (left >= 0) & (right < len(t))
        duration = np.diff(grid)
        gap = np.full(len(duration), np.nan)
        gap[bracket] = t[right[bracket]] - t[left[bracket]]
        valid = bracket & (gap > 0) & (gap <= max_gap_seconds)
        applied_valid = bracket & (gap > 0) & (gap <= applied_max_gap_seconds)
        coverage = float(duration[valid].sum())
        complete = bool(np.isclose(coverage, 3600, atol=1e-8, rtol=0))
        applied_complete = bool(np.isclose(duration[applied_valid].sum(), 3600, atol=1e-8, rtol=0))
        involved = np.unique(np.r_[left[bracket], right[bracket]])
        source_dates = sorted(set(pd.to_datetime(t[involved], unit="s", utc=True).tz_convert("America/New_York").strftime("%Y%m%d")))
        row = dict(timestamp_utc=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   coverage_qualified=complete, coverage_seconds=coverage,
                   coverage_failure="" if complete else (
                       "Incomplete hourly bracket" if not bracket.all() else "Public sample gap exceeds policy"),
                   maximum_bracketing_gap_seconds=float(np.nanmax(gap)) if bracket.any() else np.nan,
                   duplicate_timestamp_count=int(np.sum(count[involved] > 1)),
                   max_duplicate_spread_mw=float(np.max(upper[involved] - lower[involved])) if len(involved) else np.nan,
                   schedule_mw=np.nan, backward_hold_mean_mw=np.nan,
                   linear_mean_mw=np.nan, duplicate_lower_mean_mw=np.nan,
                   duplicate_upper_mean_mw=np.nan)
        row["source_ids"] = ";".join(f"NYISO:ExternalLimitsFlows:{day}" for day in source_dates)
        row["applied_schedule_available"] = applied_complete
        row["schedule_imputed"] = applied_complete and not complete
        row["uncovered_seconds"] = 3600 - coverage
        row["applied_schedule_mw"] = float(np.dot(v[left], duration) / 3600) if applied_complete else np.nan
        if complete:
            row.update(schedule_mw=float(np.dot(v[left], duration) / 3600),
                       backward_hold_mean_mw=float(np.dot(v[right], duration) / 3600),
                       linear_mean_mw=float(np.dot((np.interp(grid[:-1], t, v) + np.interp(grid[1:], t, v)) / 2, duration) / 3600),
                       duplicate_lower_mean_mw=float(np.dot(lower[left], duration) / 3600),
                       duplicate_upper_mean_mw=float(np.dot(upper[left], duration) / 3600))
        rows.append(row)
    return pd.DataFrame(rows)


def build(load_profile, cache, out, allow_download=False):
    out.mkdir(parents=True, exist_ok=True)
    catalog = pd.read_csv(load_profile, usecols=["timestamp_utc", "timestamp_local", "source_time_zone"])
    starts = pd.DatetimeIndex(pd.to_datetime(catalog.timestamp_utc, utc=True))
    if not starts.is_unique or not starts.is_monotonic_increasing:
        raise ValueError("Load profile timestamps must be unique and increasing")
    local = starts.tz_convert("America/New_York")
    if not np.array_equal(local.strftime("%Z"), catalog.source_time_zone):
        raise ValueError("Load profile timezone tokens disagree with civil dates")
    if not np.array_equal(local.strftime("%Y-%m-%dT%H:%M:%S%z"), pd.DatetimeIndex(pd.to_datetime(catalog.timestamp_local, utc=True)).tz_convert("America/New_York").strftime("%Y-%m-%dT%H:%M:%S%z")):
        raise ValueError("Load profile local and UTC timestamps disagree")
    months = sorted(set(local.strftime("%Y%m")))
    tables, manifests = [], {}
    for month in months:
        mask = local.strftime("%Y%m") == month
        month_starts = starts[mask]
        days = sorted(set(local[mask].strftime("%Y%m%d")))
        edge_day = (local[mask][-1] + pd.Timedelta(hours=1)).strftime("%Y%m%d")
        days = sorted(set(days + [edge_day]))
        blocks = []
        for day in days:
            raw, manifest = load_source(day, cache, out, allow_download)
            manifests[day] = manifest
            frame = pd.read_csv(io.BytesIO(raw))
            frame = frame.loc[frame["Interface Name"].isin(CHANNELS)].copy()
            frame["utc"] = pd.to_datetime(frame.Timestamp, format="%m/%d/%Y %H:%M").dt.tz_localize(
                "America/New_York", ambiguous="raise", nonexistent="raise").dt.tz_convert("UTC")
            # Load the entire edge file for a self-contained source package,
            # but consume only samples through the required final bracket.
            blocks.append(frame)
        block = pd.concat(blocks, ignore_index=True)
        for name in CHANNELS:
            channel = block.loc[block["Interface Name"] == name]
            point_id = channel_identity(channel, name)
            table = hourly_channel(channel, month_starts)
            table.insert(1, "public_interface_name", name)
            table.insert(2, "point_id", point_id)
            table.insert(3, "s11_primary_channel", name in PRIMARY)
            table.insert(4, "external_region", PRIMARY.get(name, "diagnostic_only"))
            table["source_kind"] = "published_external_schedule_point_samples"
            table["actual_flow_observed"] = False
            tables.append(table)
        print(f"Extracted interchange {month}", flush=True)
    channels = pd.concat(tables, ignore_index=True).sort_values(["timestamp_utc", "public_interface_name"])
    if (channels.groupby("public_interface_name").point_id.nunique() != 1).any():
        raise ValueError("Public point identity changes across months")
    primary = channels.loc[channels.s11_primary_channel]
    wide = primary.pivot(index="timestamp_utc", columns="external_region", values="schedule_mw")
    regional = catalog.merge(wide, left_on="timestamp_utc", right_index=True, how="left", validate="one_to_one")
    regional["all_primary_coverage_qualified"] = regional[list(PRIMARY.values())].notna().all(axis=1)
    regional["total_s11_scheduled_import_mw"] = regional[list(PRIMARY.values())].sum(axis=1, min_count=4)
    boundary = catalog.copy()
    mapping = []
    for name, channel, bus, weight in MAPPING:
        boundary[name] = regional[PRIMARY[channel]] * weight
        mapping.append(dict(external_interface_name=name, public_interface_name=channel,
                            external_region=PRIMARY[channel], bus_id=bus, allocation_weight=weight,
                            direction_positive="import_into_ny", scheduled_q_mvar=0,
                            q_observed=False, allocation_basis="saved_S11_fixed_spatial_allocation"))
    boundary["all_primary_coverage_qualified"] = regional.all_primary_coverage_qualified
    boundary["total_s11_scheduled_import_mw"] = regional.total_s11_scheduled_import_mw
    applied_wide = primary.pivot(index="timestamp_utc", columns="external_region", values="applied_schedule_mw")
    applied_regional = catalog.merge(applied_wide, left_on="timestamp_utc", right_index=True, how="left", validate="one_to_one")
    applied_boundary = catalog.copy()
    for name, channel, _, weight in MAPPING:
        applied_boundary[name] = applied_regional[PRIMARY[channel]] * weight
    primary_status = primary.groupby("timestamp_utc").agg(
        schedule_imputed=("schedule_imputed", "any"),
        maximum_bracketing_gap_seconds=("maximum_bracketing_gap_seconds", "max"),
        uncovered_seconds=("uncovered_seconds", "max"))
    for applied in [applied_regional, applied_boundary]:
        applied["all_primary_coverage_qualified"] = regional.all_primary_coverage_qualified
        applied["applied_schedule_available"] = applied_regional[list(PRIMARY.values())].notna().all(axis=1)
        for column in primary_status:
            applied[column] = applied.timestamp_utc.map(primary_status[column])
        applied["total_s11_scheduled_import_mw"] = applied_regional[list(PRIMARY.values())].sum(axis=1, min_count=4)
    allocation_error = np.abs(boundary[[m[0] for m in MAPPING]].sum(axis=1, min_count=8) - regional.total_s11_scheduled_import_mw)
    if allocation_error.max() > 1e-9:
        raise AssertionError("Boundary allocation did not preserve regional schedule totals")
    for name, table in [("hourly_channels", channels), ("regional_mw", regional),
                        ("boundary_mw", boundary), ("mapping", pd.DataFrame(mapping)),
                        ("regional_applied_mw", applied_regional), ("boundary_applied_mw", applied_boundary),
                        ("source_manifest", pd.DataFrame(manifests.values()))]:
        table.to_csv(out / f"interchange_{name}.csv", index=False, lineterminator="\n", float_format="%.12g")
    quality = dict(
        aligned_hour_count=len(catalog), months=months, primary_channel_count=4, boundary_injection_count=8,
        source_daily_file_count=len(manifests),
        primary_complete_hours=int(regional.all_primary_coverage_qualified.sum()),
        primary_incomplete_hours=int((~regional.all_primary_coverage_qualified).sum()),
        primary_incomplete_timestamps=regional.loc[~regional.all_primary_coverage_qualified, "timestamp_utc"].tolist(),
        applied_complete_hours=int(applied_regional.applied_schedule_available.sum()),
        applied_imputed_hours=int(applied_regional.schedule_imputed.sum()),
        all_channel_complete_records=int(channels.coverage_qualified.sum()),
        all_channel_records=len(channels),
        coverage_by_channel=channels.groupby("public_interface_name").coverage_qualified.agg(["sum", "count"]).astype(int).to_dict("index"),
        source_header="Flow (MWH)", interpreted_units="MW", source_semantics="SCH external interchange schedule point samples; not measured actual flow",
        interval_convention="hour_beginning_[start,start+1hour)",
        interval_convention_evidence="Existing empirical P58B/P58C load audit; NYISO P32 integration convention is not independently specified",
        mean_policy="forward_sample_hold", maximum_bracketing_gap_seconds=600,
        extrapolation_allowed=False, strict_missing_observations_imputed=False, gamma_scaling_applied=False,
        applied_gap_completion_policy="forward hold only for fully bracketed gaps at most 3600 seconds; strict qualified hours unchanged",
        applied_maximum_bracketing_gap_seconds=3600,
        uncovered_seconds_definition="Maximum per-primary-channel seconds lacking strict 600s coverage; not summed across channels",
        duplicate_policy="mean per unique minute label; lower and upper hourly bounds retained",
        primary_direction="positive is interpreted as import into NY, consistent with saved S11 mapping",
        boundary_q_policy="fixed zero as in saved S11; not observed reactive interchange",
        additional_channels_injected=False, additional_channels=SUPPLEMENTAL,
        additional_channel_policy="diagnostic only; aggregate overlap and missing explicit S11 tie representations prevent unconditional addition",
        statewide_total_import_claim=False, measured_actual_flow_claim=False,
        maximum_boundary_allocation_error_mw=float(allocation_error.max()),
        source_load_profile_sha256=digest(load_profile.read_bytes()),
    )
    (out / "interchange_quality.json").write_text(json.dumps(quality, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: quality[k] for k in ["aligned_hour_count", "primary_complete_hours", "primary_incomplete_hours", "source_daily_file_count"]}), flush=True)
    return quality


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load-profile", type=Path, default=ROOT / "output/s11_hourly_load_profiles/pd_mw.csv")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--download-edges", action="store_true")
    args = parser.parse_args()
    build(args.load_profile, args.cache, args.output, args.download_edges)
