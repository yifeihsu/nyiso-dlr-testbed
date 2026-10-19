"""Build unscaled, source-backed 2025 generation priors, never a dispatch.

EPA unit observations are not expanded by many-to-many crosswalks. NYISO P63
hourly totals use a declared preceding-interval integration convention. The
geographic allocations are estimates with explicit coverage/mapping flags.
No compact model dispatch, benchmark scale, or internal-interface targets enter.
Run with Python containing numpy, pandas and openpyxl (the bundled runtime).
"""
from __future__ import annotations

import argparse
import calendar
import collections
import csv
import datetime as dt
import gzip
import hashlib
import importlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
epa = importlib.import_module("build_compact_epa_generation_inputs")
nf = importlib.import_module("build_compact_nonfossil_generation_inputs")
OUT = ROOT / "output/nygrid_2025_inputs/generation_source"
EST = dt.timezone(dt.timedelta(hours=-5), "EST")
NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
START = dt.datetime(2025, 1, 1, tzinfo=EST).astimezone(UTC)
N = 8760
ZONES = list("ABCDEFGHIJK")
FUELS = ["Dual Fuel", "Natural Gas", "Other Fossil Fuels", "Nuclear", "Hydro", "Wind", "Other Renewables"]
PRIOR_FUELS = ["Combined Fossil", "Nuclear", "Hydro", "Wind", "Other Renewables"]
P63_POLICY = "sample_at_t_represents_preceding_interval; UTC_hour_beginning; gaps_over600s_uncovered"


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def frame_write(path: Path, rows) -> None:
    data = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    compression = {"method": "gzip", "mtime": 0} if path.suffix == ".gz" else None
    data.to_csv(path, index=False, lineterminator="\n", compression=compression)


def hour_axis() -> pd.DataFrame:
    utc = [START + dt.timedelta(hours=h) for h in range(N)]
    local = [t.astimezone(NY) for t in utc]
    return pd.DataFrame({"hour_index": np.arange(1, N + 1),
        "timestamp_utc": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in utc],
        "timestamp_local": [t.strftime("%Y-%m-%d %H:%M:%S") for t in local],
        "time_zone": [t.tzname() for t in local]})


def utc_seconds(label: str, zone: str) -> int:
    if zone not in {"EST", "EDT"}:
        raise ValueError("Unrecognized NYISO time zone: " + zone)
    local = dt.datetime.strptime(label, "%m/%d/%Y %H:%M:%S")
    return int(local.replace(tzinfo=dt.timezone(dt.timedelta(hours=-5 if zone == "EST" else -4))).timestamp())


def integrate_hourly(samples, start_seconds: int, hours: int):
    """Time-weight preceding values; never fill incomplete hour means."""
    by_time = {}
    duplicate_count = 0
    for t, p in samples:
        if t in by_time:
            if by_time[t] != p:
                raise ValueError("Conflicting values at one UTC timestamp")
            duplicate_count += 1
        by_time[t] = p
    values = sorted(by_time.items())
    energy = np.zeros(hours); coverage = np.zeros(hours)
    counts = np.zeros(hours, dtype=int); maxgap = np.zeros(hours)
    end_seconds = start_seconds + 3600 * hours
    for (left, _), (right, power) in zip(values, values[1:]):
        a, b = max(left, start_seconds), min(right, end_seconds)
        if b <= a:
            continue
        gap = right - left
        first, last = (a - start_seconds) // 3600, (b - 1 - start_seconds) // 3600
        for h in range(int(first), int(last) + 1):
            overlap = min(b, start_seconds + 3600 * (h + 1)) - max(a, start_seconds + 3600 * h)
            maxgap[h] = max(maxgap[h], gap)
            if gap > 600 or not math.isfinite(power):
                continue
            energy[h] += power * overlap
            coverage[h] += overlap
            counts[h] += 1
    qualified = np.abs(coverage - 3600) <= 1e-8
    mean = np.full(hours, np.nan); mean[qualified] = energy[qualified] / 3600
    partial = np.divide(energy, coverage, out=np.full(hours, np.nan), where=coverage > 0)
    return mean, coverage, qualified, counts, maxgap, partial, duplicate_count


class Sources:
    def __init__(self, out: Path, offline=False):
        self.out = out; self.cache = out / "raw_sources"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.offline = offline; self.rows = {}

    def local(self, path, source_id, url="", release="", role="", expected=None):
        path = Path(path).resolve()
        digest = sha(path)
        if expected and digest != expected:
            raise ValueError(f"Pinned source changed: {path}")
        row = dict(source_id=source_id, path=path.relative_to(ROOT).as_posix(), sha256=digest,
                   bytes=path.stat().st_size, source_url=url, source_release=release, role=role)
        if source_id in self.rows and self.rows[source_id]["sha256"] != digest:
            raise ValueError("Conflicting source identity " + source_id)
        self.rows[source_id] = row
        return path

    def fetch(self, name, source_id, url, role, legacy=None, expected=None):
        path = self.cache / name; receipt = path.with_suffix(path.suffix + ".receipt.json")
        if path.exists():
            if not receipt.exists():
                raise ValueError("Existing source lacks receipt: " + str(path))
            metadata = json.loads(receipt.read_text())
            if metadata["source_url"] != url or sha(path) != metadata["sha256"]:
                raise ValueError("Cached download differs from its receipt")
        else:
            if legacy and Path(legacy).exists():
                if expected and sha(Path(legacy)) != expected:
                    raise ValueError("Legacy cache differs from pinned source")
                shutil.copyfile(legacy, path)
                status = "reused_pinned_cache"
            else:
                if self.offline:
                    raise FileNotFoundError(path)
                print("Downloading", source_id, flush=True)
                with urllib.request.urlopen(url, timeout=90) as response:
                    data = response.read()
                if name.endswith(".zip") and not data.startswith(b"PK"):
                    raise ValueError("Expected archive from " + url)
                if name.endswith(".txt") and b"<html" in data[:1000].lower():
                    raise ValueError("Expected data, received HTML from " + url)
                path.write_bytes(data); status = "downloaded_current_historical_archive"
            metadata = dict(source_url=url, sha256=sha(path), bytes=path.stat().st_size,
                            retrieved_utc=dt.datetime.now(UTC).isoformat(), status=status)
            receipt.write_text(json.dumps(metadata, indent=2) + "\n")
        return self.local(path, source_id, url, metadata["retrieved_utc"], role, expected)


def fuelmix(sources: Sources, axis):
    legacy_root = ROOT / "tmp/nonfossil_sources"
    legacy = pd.read_csv(ROOT / "output/compact_ny_2025/generation_sources/nonfossil/source_manifest.csv")
    hashes = {Path(str(r.local_cache)).name: r.sha256 for r in legacy.itertuples()}
    samples = {f: [] for f in FUELS}; member_rows = []; clock_cache = {}
    months = ["202412"] + [f"2025{m:02d}" for m in range(1, 13)] + ["202601"]
    start, end = int(START.timestamp()), int((START + dt.timedelta(hours=N)).timestamp())
    for month in months:
        name = month + "01rtfuelmix_csv.zip"
        url = "https://mis.nyiso.com/public/csv/rtfuelmix/" + name
        path = sources.fetch(name, "NYISO:P63:" + month, url, "official_monthly_fuelmix_archive",
                             legacy_root / name, hashes.get(name))
        with zipfile.ZipFile(path) as archive:
            members = sorted(n for n in archive.namelist() if n.endswith("rtfuelmix.csv"))
            for member in members:
                # One adjacent day on either side suffices for interval boundaries.
                day = Path(member).name[:8]
                if day < "20241231" or day > "20260101":
                    continue
                data = archive.read(member)
                nrows = 0
                for row in csv.DictReader(io.StringIO(data.decode("utf-8-sig"))):
                    key = (row["Time Stamp"], row["Time Zone"])
                    if key not in clock_cache:
                        clock_cache[key] = utc_seconds(*key)
                    t = clock_cache[key]; f = row["Fuel Category"]
                    if f not in samples:
                        raise ValueError("Unexpected P63 category " + f)
                    p = float(row["Gen MW"])
                    if start - 86400 <= t <= end + 86400:
                        samples[f].append((t, p))
                    nrows += 1
                member_rows.append(dict(archive_source_id="NYISO:P63:" + month, member=member,
                    sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), records=nrows))
        print("Parsed P63", month, flush=True)
    outputs = []; totals = {}; quals = {}; diagnostics = {}
    for f in FUELS:
        p, coverage, q, counts, gap, partial, duplicates = integrate_hourly(samples[f], start, N)
        if np.any(p[q] < 0):
            raise ValueError("Negative P63 category requires explicit policy review: " + f)
        frame = axis.copy(); frame["fuel_category"] = f
        frame["generation_mw"] = p; frame["coverage_seconds"] = coverage
        frame["coverage_qualified"] = q.astype(int); frame["max_gap_seconds"] = gap
        frame["interval_count"] = counts; frame["covered_portion_mean_mw"] = partial
        frame["quantity_role"] = "reported_statewide_fuel_total_time_aggregated"
        frame["interval_policy"] = P63_POLICY
        outputs.append(frame); totals[f] = p; quals[f] = q
        diagnostics[f] = dict(qualified_hours=int(q.sum()), missing_hours=int((~q).sum()),
                              identical_duplicate_samples_removed=duplicates)
    total = pd.concat(outputs, ignore_index=True).sort_values(["hour_index", "fuel_category"])
    frame_write(sources.out / "statewide_fuelmix_hourly.csv", total)
    frame_write(sources.out / "p63_archive_members.csv", member_rows)
    return totals, quals, diagnostics


def pinned_compact_extract(sources, filename):
    folder = ROOT / "output/compact_ny_2025/generation_sources/epa"
    manifest = json.loads((folder / "epa_source_manifest.json").read_text())
    entry = next(r for r in manifest["extracts"] if r["filename"] == filename)
    return sources.local(folder / filename, "REUSED_IDENTITY:" + filename,
                         release="previously_verified_source_identity_only", role="identity_not_dispatch", expected=entry["sha256"])


def extract_epa(sources, axis):
    raw = ROOT / "tmp/epa_generation_raw"
    for name in ["emissions-hourly-2025-ny.csv", "facility-2025.csv", "emissions-daily-2025-ny.csv"]:
        url, digest, size, release = epa.SPECS[name]
        path = sources.local(raw / name, "EPA:" + name, url, release, "official_CAMPD_source", digest)
        if path.stat().st_size != size:
            raise ValueError("EPA source byte count changed")
    ng = epa.read_csv(pinned_compact_extract(sources, "nygrid_2019_identity_crosswalk.csv"))
    cross = epa.read_csv(pinned_compact_extract(sources, "epa_eia_crosswalk_ny.csv"))
    manual = epa.read_csv(pinned_compact_extract(sources, "declared_facility_zone_evidence.csv"))
    indices = epa.mapping_indices(ng, cross)
    attrs = {(r["Facility ID"], r["Unit ID"]): r for r in epa.read_csv(raw / "facility-2025.csv") if r["State"] == "NY"}
    mappings = {}; seen = {}; registry = {}; positive = collections.Counter()
    zlist = ZONES + ["UNMAPPED"]
    arrays = {k: np.zeros((N, 12)) for k in ["all_reported_gross_clock_hour_mw", "grid_eligible_gross_clock_hour_mw",
        "source_unit_rows", "gross_present_rows", "gross_missing_rows", "reported_offline_gross_blank_rows", "active_unknown_gross_rows"]}
    path = sources.out / "epa_unit_hourly.csv.gz"
    fields = ["hour_index", "timestamp_utc", "facility_id", "unit_id", "device_key", "zone", "source_gross_load_mw",
        "operating_time_hours", "gross_clock_hour_average_mw", "gross_quantity_status", "grid_fossil_share_eligible",
        "zone_mapping_kind", "primary_fuel_type", "secondary_fuel_type", "source_record_ordinal"]
    count = 0; partial_hour_count = 0
    utc_labels = axis.timestamp_utc.to_numpy()
    with gzip.GzipFile(filename=str(path), mode="wb", mtime=0) as gz, io.TextIOWrapper(gz, encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, lineterminator="\n"); writer.writeheader()
        for ordinal, row, _ in epa.iter_source_records(raw / "emissions-hourly-2025-ny.csv"):
            if row["State"] != "NY":
                raise ValueError("Non-NY record in state bulk")
            key = (row["Facility ID"], row["Unit ID"])
            date = dt.date.fromisoformat(row["Date"])
            hour = int(row["Hour"])
            if date.year != 2025 or not 0 <= hour < 24:
                raise ValueError("Invalid EPA date/hour")
            h = (date - dt.date(2025, 1, 1)).days * 24 + hour
            if key not in mappings:
                mapping = epa.map_unit(*key, indices, manual)
                attr = attrs.get(key, {})
                eligible = key[0] != "52168" and attr.get("Source Category") in {"Electric Utility", "Cogeneration"}
                zone = mapping["zone"] or "UNMAPPED"
                mappings[key] = (mapping, zlist.index(zone), eligible)
                seen[key] = np.zeros(N, dtype=bool)
                registry[key] = dict(facility_id=key[0], unit_id=key[1], device_key=f"EPA:ORIS:{key[0]}:UNIT:{key[1]}",
                    facility_name=row["Facility Name"], zone=zone, grid_fossil_share_eligible=int(eligible),
                    source_category=attr.get("Source Category", ""), county=attr.get("County", ""),
                    associated_generators=attr.get("Associated Generators & Nameplate Capacity (MWe)", ""),
                    **{k: v for k, v in mapping.items() if k != "zone"})
                registry[key]["zone"] = zone
            if seen[key][h]:
                raise ValueError(f"Duplicate EPA unit/hour: {key} {date} {hour}")
            seen[key][h] = True
            mapping, z, eligible = mappings[key]
            gross, op, energy, status = epa.convert_gross(row)
            arrays["source_unit_rows"][h, z] += 1
            if energy is None:
                arrays["gross_missing_rows"][h, z] += 1
                arrays["reported_offline_gross_blank_rows" if op == 0 else "active_unknown_gross_rows"][h, z] += 1
            else:
                arrays["gross_present_rows"][h, z] += 1
                arrays["all_reported_gross_clock_hour_mw"][h, z] += energy
                if eligible:
                    arrays["grid_eligible_gross_clock_hour_mw"][h, z] += energy
                if energy > 0:
                    positive[key] += 1
            partial_hour_count += int(op is not None and 0 < op < 1)
            writer.writerow(dict(hour_index=h + 1, timestamp_utc=utc_labels[h],
                facility_id=key[0], unit_id=key[1], device_key=f"EPA:ORIS:{key[0]}:UNIT:{key[1]}",
                zone=zlist[z], source_gross_load_mw=gross, operating_time_hours=op, gross_clock_hour_average_mw=energy,
                gross_quantity_status=status, grid_fossil_share_eligible=int(eligible),
                zone_mapping_kind=mapping["zone_mapping_kind"], primary_fuel_type=row["Primary Fuel Type"],
                secondary_fuel_type=row["Secondary Fuel Type"], source_record_ordinal=ordinal))
            count += 1
            if count % 250000 == 0:
                print("EPA records", count, flush=True)
    frames = []
    for z, zone in enumerate(zlist):
        frame = axis.copy(); frame["zone"] = zone
        for k, array in arrays.items():
            frame[k] = array[:, z]
        frame["fuel_category"] = "Combined Fossil"
        frame["observed_net_generation"] = 0
        frame["complete_grid_generation_coverage"] = 0
        frames.append(frame)
    frame_write(sources.out / "epa_zonal_hourly.csv.gz", pd.concat(frames, ignore_index=True).sort_values(["hour_index", "zone"]))
    unit_rows = []
    for key, r in sorted(registry.items()):
        r.update(reported_hour_count=int(seen[key].sum()), absent_hour_count=int((~seen[key]).sum()),
                 positive_reported_gross_hours=positive[key])
        unit_rows.append(r)
    frame_write(sources.out / "epa_unit_identity_register.csv", unit_rows)
    # Independent published daily-energy fixture, kept source-only and unscaled.
    fixture = ROOT / "output/compact_ny_2025/generation_sources/epa"
    quantity = epa.quantity_audit(epa.read_csv(pinned_compact_extract(sources, "quantity_audit_hourly_source.csv")),
                                  epa.read_csv(pinned_compact_extract(sources, "quantity_audit_daily_source.csv")))
    frame_write(sources.out / "epa_quantity_validation.csv", quantity)
    return arrays, unit_rows, ng, dict(source_records=count, reporting_unit_count=len(registry),
        partial_operating_hours=partial_hour_count, unknown_active_gross_rows=int(arrays["active_unknown_gross_rows"].sum()),
        gross_blank_rows=int(arrays["gross_missing_rows"].sum()),
        positive_unmapped_eligible_hours=int((arrays["grid_eligible_gross_clock_hour_mw"][:, 11] > 0).sum()),
        reported_gross_is_net=False, reporting_scope_complete_NY_generation=False)


def source_inventory(sources):
    folder = ROOT / "output/compact_ny_2025/generation_sources/nonfossil"
    output_manifest = {r["artifact"]: r["sha256"] for r in epa.read_csv(folder / "output_manifest.csv")}
    path = sources.local(folder / "eia860_nonfossil_inventory.csv", "EIA860:validated_nonfossil_inventory",
        release="2025_early_release_retrieved_2026-09-08", role="full_source_inventory_not_compact_dispatch",
        expected=output_manifest["eia860_nonfossil_inventory.csv"])
    inventory = [r for r in epa.read_csv(path) if r["vintage"] == "2025"]
    for r in inventory:
        for field in ["plant_id", "operating_year", "operating_month", "retirement_year", "retirement_month"]:
            r[field] = int(r[field])
        for field in ["nameplate_capacity_mw", "summer_capacity_mw", "winter_capacity_mw", "latitude", "longitude"]:
            r[field] = float(r[field])
    entries = epa.read_csv(folder / "source_manifest.csv")
    for r in entries:
        if r["source_id"].startswith(("EIA860:2025", "EIA923:2025")) or r["source_id"] == "NYISO:GOLD_BOOK:2025":
            sources.local(ROOT / r["local_cache"], r["source_id"], r["source_url"], r["retrieval_date"], r["evidence_role"], r["sha256"])
    hydro_entry = next(r for r in entries if r["source_id"].startswith("EIA923:2025:") and "Schedules_2_3_4_5" in r["source_id"])
    hydro = []
    zones = {r["plant_id"]: (r["estimated_zone"], r["zone_mapping_policy"]) for r in inventory}
    print("Reading all twelve EIA923 hydro months", flush=True)
    for line, row in nf.sheet_dicts(ROOT / hydro_entry["local_cache"], 0, "Plant Id"):
        if row.get("Plant State") != "NY" or row.get("Reported Fuel Type Code") != "WAT":
            continue
        pid = int(row["Plant Id"])
        for month in range(1, 13):
            value = nf.num(row.get("Netgen " + calendar.month_name[month]), math.nan)
            zone, policy = zones.get(pid, ("UNMAPPED", "no_locatable_inventory_plant"))
            hydro.append(dict(plant_id=pid, plant_name=row["Plant Name"], prime_mover=row["Reported Prime Mover"],
                month=month, zone=zone, zone_mapping_policy=policy, net_generation_mwh=value,
                monthly_mean_net_mw=value / (24 * calendar.monthrange(2025, month)[1]),
                respondent_frequency=row.get("Respondent Frequency"),
                monthly_source_value_published=int(math.isfinite(value)),
                monthly_generation_observed=int(row.get("Respondent Frequency") == "M"),
                source_excel_row=line, source_id=hydro_entry["source_id"], source_sha256=hydro_entry["sha256"]))
    frame_write(sources.out / "eia860_nonfossil_inventory_2025.csv", inventory)
    frame_write(sources.out / "eia923_monthly_hydro_2025.csv", hydro)
    return inventory, hydro


def parse_nrc_year(data: bytes):
    result = {}
    text = data.decode("utf-8-sig")
    for row in csv.DictReader(io.StringIO(text), delimiter="|"):
        lowered = {k.strip().lower(): v.strip() for k, v in row.items() if k is not None}
        name = lowered.get("unit", "")
        if name not in {v[0] for v in nf.REACTORS.values()}:
            continue
        date_text = lowered.get("reportdt", lowered.get("date", lowered.get("timestamp", "")))
        date = dt.datetime.strptime(date_text.split()[0], "%m/%d/%Y").date()
        value = float(lowered.get("power", ""))
        if not 0 <= value <= 110:
            raise ValueError("Invalid NRC power percentage")
        key = (date, name)
        if key in result and result[key] != value:
            raise ValueError("Conflicting daily NRC availability")
        result[key] = value
    if not result:
        raise ValueError("No NY reactors in NRC annual file")
    return result


def nrc_inputs(sources):
    result = {}
    for year in [2024, 2025]:
        url = f"https://www.nrc.gov/reading-rm/doc-collections/event-status/reactor-status/{year}/{year}PowerStatus.txt"
        path = sources.fetch(f"{year}PowerStatus.txt", f"NRC:annual:{year}", url, "daily_reactor_availability_not_hourly_electrical_output")
        result.update(parse_nrc_year(path.read_bytes()))
    frame_write(sources.out / "nrc_daily_reactor_status.csv", [dict(report_date=str(date), reactor_name=name,
        power_percent=p, hourly_output_observed=0) for (date, name), p in sorted(result.items())
        if dt.date(2024, 12, 31) <= date <= dt.date(2025, 12, 31)])
    return result


def normalise_weights(weights, total, source_ok):
    weights = np.asarray(weights, dtype=float)
    if not np.all(np.isfinite(weights)) or np.any(weights < 0):
        return np.full(len(weights), np.nan), np.full(len(weights), np.nan), False
    denominator = weights.sum()
    shares = weights / denominator if denominator else np.ones(len(weights)) / len(weights)
    ok = bool(source_ok and math.isfinite(total) and total >= 0 and (denominator > 0 or total == 0))
    values = total * shares if ok else np.full(len(weights), np.nan)
    return values, shares, ok


def allocate(sources, axis, totals, quals, epa_arrays, inventory, hydro, nrc):
    outputs = []; hydro_plant_frames = []; nuclear_plant_rows = []; south_fork = []
    p = np.full((N, 11, 5), np.nan); shares = np.full_like(p, np.nan)
    qualified = np.zeros((N, 5), bool); source_ok = np.zeros((N, 5), bool)
    fossil_total = sum(totals[f] for f in FUELS[:3])
    fossil_q = np.logical_and.reduce([quals[f] for f in FUELS[:3]])
    statewide = [fossil_total] + [totals[f] for f in PRIOR_FUELS[1:]]
    active_by_month = {}; hydro_by_month = {}
    for month in range(1, 13):
        local = dt.datetime(2025, month, 15)
        active = [r for r in inventory if nf.is_active(r, local)]
        active_by_month[month] = active
        season = "winter" if month in [11, 12, 1, 2, 3] else "summer"
        plants = {}
        for r in active:
            if r["energy_source_code"] != "WAT" or r["prime_mover"] not in {"HY", "PS"}:
                continue
            key = (r["plant_id"], r["prime_mover"])
            if key not in plants:
                plants[key] = dict(plant_id=r["plant_id"], plant_name=r["plant_name"], prime_mover=r["prime_mover"],
                    zone=r["estimated_zone"], capability_mw=0., baseline_mw=0., monthly_net_mwh=0.,
                    monthly_source_rows=0, monthly_source_missing_rows=0)
            plants[key]["capability_mw"] += r[season + "_capacity_mw"]
        for r in hydro:
            key = (r["plant_id"], r["prime_mover"])
            if r["month"] != month or key not in plants:
                continue
            plants[key]["monthly_source_rows"] += 1
            plants[key]["monthly_source_missing_rows"] += int(not math.isfinite(r["monthly_mean_net_mw"]))
            plants[key]["monthly_net_mwh"] += r["net_generation_mwh"]
            if r["prime_mover"] == "HY" and math.isfinite(r["monthly_mean_net_mw"]):
                plants[key]["baseline_mw"] += max(r["monthly_mean_net_mw"], 0)
        hydro_by_month[month] = list(plants.values())
    for h, row in enumerate(axis.itertuples()):
        local = (START + dt.timedelta(hours=h)).astimezone(NY)
        month = local.month; active = active_by_month[month]
        season = "winter" if month in [11, 12, 1, 2, 3] else "summer"
        source_ok[h, 0] = fossil_q[h]
        fossil_weights = epa_arrays["grid_eligible_gross_clock_hour_mw"][h, :11]
        mapping_ok = epa_arrays["grid_eligible_gross_clock_hour_mw"][h, 11] <= 1e-9
        p[h, :, 0], shares[h, :, 0], qualified[h, 0] = normalise_weights(fossil_weights, fossil_total[h], fossil_q[h] and mapping_ok)
        # NRC reports are morning availability measurements; using previous day
        # before08:00 avoids assuming today's report was available overnight.
        report_date = local.date() if local.hour >= 8 else local.date() - dt.timedelta(days=1)
        nuclear_weights = np.zeros(11); nrows = []; nrc_ok = True
        for r in active:
            if r["energy_source_code"] != "NUC":
                continue
            name, zone = nf.REACTORS[(r["plant_id"], r["generator_id"])]
            value = nrc.get((report_date, name), math.nan)
            availability = value / 100 * r[season + "_capacity_mw"]
            nrc_ok &= math.isfinite(availability)
            nuclear_weights[ZONES.index(zone)] += availability
            nrows.append(dict(hour_index=h + 1, plant_id=r["plant_id"], generator_id=r["generator_id"], reactor_name=name,
                zone=zone, nrc_report_date=str(report_date), report_power_percent=value,
                seasonal_capacity_mw=r[season + "_capacity_mw"], availability_weight_mw=availability,
                hourly_electrical_output_observed=0))
        source_ok[h, 1] = quals["Nuclear"][h]
        p[h, :, 1], shares[h, :, 1], qualified[h, 1] = normalise_weights(nuclear_weights, totals["Nuclear"][h], quals["Nuclear"][h] and nrc_ok)
        denominator = nuclear_weights.sum()
        for item in nrows:
            item["estimated_actual_mw"] = totals["Nuclear"][h] * item["availability_weight_mw"] / denominator if qualified[h, 1] and denominator > 0 else math.nan
            item["allocation_qualified"] = int(qualified[h, 1]); nuclear_plant_rows.append(item)
        plants = hydro_by_month[month]
        base = [r["baseline_mw"] for r in plants]; cap = [r["capability_mw"] for r in plants]
        source_ok[h, 2] = quals["Hydro"][h]
        if quals["Hydro"][h]:
            values, ok = nf.bounded_hydro_projection(base, cap, totals["Hydro"][h])
        else:
            values, ok = [math.nan] * len(plants), False
        weights = np.zeros(11)
        for r, value in zip(plants, values):
            weights[ZONES.index(r["zone"])] += value if ok else r["capability_mw"]
        p[h, :, 2], shares[h, :, 2], qualified[h, 2] = normalise_weights(weights, totals["Hydro"][h], quals["Hydro"][h] and ok)
        # Plant-hour arrays are emitted later as a compact matrix, not millions
        # of repeated provenance strings. Monthly plant keys remain inspectable.
        hydro_plant_frames.append(values)
        for fi, fuel in [(3, "Wind"), (4, "Other Renewables")]:
            weights = np.zeros(11); sf_weight = 0.
            for r in active:
                code = r["energy_source_code"]
                if (fuel == "Wind" and code != "WND") or (fuel == "Other Renewables" and code not in nf.OTHER_FUELS):
                    continue
                weight = r["nameplate_capacity_mw"]
                if code == "SUN":
                    weight *= nf.solar_weight(local.replace(tzinfo=None) + dt.timedelta(minutes=30), r["latitude"], r["longitude"], local.tzname())
                weights[ZONES.index(r["estimated_zone"])] += weight
                if r["plant_id"] == 65561:
                    sf_weight += weight
            source_ok[h, fi] = quals[fuel][h]
            p[h, :, fi], shares[h, :, fi], qualified[h, fi] = normalise_weights(weights, totals[fuel][h], quals[fuel][h])
            if fuel == "Wind":
                south_fork.append(dict(hour_index=h + 1, timestamp_utc=row.timestamp_utc, plant_id=65561,
                    zone="K", fuel_category="Wind", nameplate_weight_mw=sf_weight,
                    estimated_actual_mw=totals[fuel][h] * sf_weight / weights.sum() if qualified[h, fi] and weights.sum() else math.nan,
                    allocation_qualified=int(qualified[h, fi]), subset_of_zone_fuel_prior=1,
                    full_2019_generator_landing_qualified=0, hourly_generation_observed=0))
    methods = ["P63_combined_fossil_total_times_available_unique_EPA_gross_zone_shares",
               "NRC_daily_availability_times_EIA_seasonal_capability_normalized_to_P63",
               "EIA_monthly_conventional_baseline_then_HY_PS_generation_headroom",
               "EIA_active_nameplate_capacity_shared_statewide_wind_profile",
               "EIA_active_capacity_with_assumed_solar_daylight_weight"]
    for fi, fuel in enumerate(PRIOR_FUELS):
        if not np.allclose(np.nansum(p[qualified[:, fi], :, fi], axis=1), statewide[fi][qualified[:, fi]], atol=1e-7, rtol=0):
            raise ValueError("Zonal priors fail statewide conservation")
        for z, zone in enumerate(ZONES):
            f = axis.copy(); f["zone"] = zone; f["fuel_category"] = fuel
            f["prior_actual_mw"] = p[:, z, fi]; f["statewide_actual_mw"] = statewide[fi]
            f["allocation_share"] = shares[:, z, fi]; f["allocation_qualified"] = qualified[:, fi].astype(int)
            f["source_coverage_qualified"] = source_ok[:, fi].astype(int)
            f["allocation_method"] = methods[fi]; f["observed_zonal_generation"] = 0
            outputs.append(f)
    frame_write(sources.out / "zonal_generation_priors.csv.gz", pd.concat(outputs, ignore_index=True).sort_values(["hour_index", "zone", "fuel_category"]))
    frame_write(sources.out / "nuclear_plant_hourly_priors.csv.gz", nuclear_plant_rows)
    frame_write(sources.out / "south_fork_hourly_prior.csv", south_fork)
    # Hydro monthly inventories plus matrices preserve the plant grain without
    # pretending to have observed reservoir dispatch or pumping schedules.
    hydro_register = []
    for month, plants in hydro_by_month.items():
        for j, r in enumerate(plants):
            hydro_register.append(dict(month=month, column_index=j, **r, hourly_generation_observed=0))
    frame_write(sources.out / "hydro_monthly_plant_allocation_register.csv", hydro_register)
    for month in range(1, 13):
        ix = [h for h in range(N) if (START + dt.timedelta(hours=h)).astimezone(NY).month == month]
        np.savez_compressed(sources.out / f"hydro_plant_priors_{month:02d}.npz", hour_index=np.asarray(ix) + 1,
                            prior_actual_mw=np.asarray([hydro_plant_frames[h] for h in ix]))
    return {fuel: dict(qualified_hours=int(qualified[:, fi].sum()), unqualified_hours=int((~qualified[:, fi]).sum())) for fi, fuel in enumerate(PRIOR_FUELS)}


def legacy_mapping(sources, unit_rows, ng, inventory):
    path = sources.local(ROOT / "output/nygrid_compact_2019/reference/jan08_generator_input_and_solution.csv",
                         "NYGRID:2019:generator_identity_export", role="row_identity_only_no_2019_dispatch_reuse")
    original = epa.read_csv(path)
    if len(original) != 271 or [int(r["source_gen_row"]) for r in original] != list(range(1, 272)):
        raise ValueError("Expected complete 271-row released identity ledger")
    full_path = sources.local(ROOT / "output/nygrid_2019_full_stage1/full_year.mat",
                              "NYGRID:2019:full_model_base_case", role="full271_generator_bus_identity_only")
    try:
        from scipy.io import loadmat
        full_gen = loadmat(full_path, variable_names=["base_case"], simplify_cells=True)["base_case"]["gen"]
    except ModuleNotFoundError:
        # Some bundled runtimes have openpyxl while the existing research
        # runtime provides SciPy. Use that runtime read-only for this MAT field.
        interpreter = shutil.which("python")
        if not interpreter or Path(interpreter).resolve() == Path(sys.executable).resolve():
            raise RuntimeError("Reading the full model MAT requires a Python runtime with SciPy")
        code = "import json,sys;from scipy.io import loadmat;print(json.dumps(loadmat(sys.argv[1],variable_names=['base_case'],simplify_cells=True)['base_case']['gen'].tolist()))"
        result = subprocess.run([interpreter, "-c", code, str(full_path)], check=True, capture_output=True, text=True)
        full_gen = np.asarray(json.loads(result.stdout), dtype=float)
    if full_gen.shape != (271, 21):
        raise ValueError("Full model generator identity matrix differs from271x21")
    if not np.array_equal(full_gen[:227, 0], np.asarray([int(r["source_bus"]) for r in original[:227]])):
        raise ValueError("Full model thermal bus order differs from source identity export")
    params_path = sources.local(ROOT / "tmp/nygrid_2019_reproduction/upstream/Data/genParamAll_newramp.csv",
                                "NYGRID:2019:thermal_parameter_identities", role="exact_name_PTID_and_Pmax_identity_check")
    assignments_path = sources.local(ROOT / "tmp/nygrid_2019_reproduction/upstream/Data/gen_bus_assignment.csv",
                                     "NYGRID:2019:thermal_bus_assignments", role="native227_bus_identity_check")
    params = epa.read_csv(params_path)
    if len(params) != 227:
        raise ValueError("Expected all227 legacy thermal parameter rows")
    assignments = {(r["NYISOName"], r["PTID"]): int(r["HubName"]) for r in epa.read_csv(assignments_path)}
    params_by_key = {(r["NYISOName"], r["PTID"]): r for r in params}
    original_keys = {(r["NYISO_name"], r["PTID"]) for r in original[:227]}
    if len(params_by_key) != 227 or original_keys != set(params_by_key):
        raise ValueError("Thermal name/PTID identity sets differ")
    order_differences = sum((r["NYISO_name"], r["PTID"]) != (p["NYISOName"], p["PTID"])
                            for r, p in zip(original[:227], params))
    for i, row in enumerate(original[:227]):
        key = (row["NYISO_name"], row["PTID"])
        param = params_by_key[key]
        if int(row["source_bus"]) != assignments[key] or abs(full_gen[i, 8] - float(param["maxPower"])) > 1e-7:
            raise ValueError("Released thermal identity/bus/Pmax differs from source parameter/assignment tables")
    by_unit = {(r["facility_id"], r["unit_id"]): r for r in unit_rows}
    output = []
    for row in original:
        candidates = [r for r in ng if r["nyiso_name"] == row["NYISO_name"] and r["nyiso_ptid"] == row["PTID"]]
        keys = sorted({(r["facility_id"], r["unit_id"]) for r in candidates})
        available = [k for k in keys if k in by_unit]
        kind = "legacy_native_aggregate_landing_unresolved"
        if row["role"] == "native_thermal":
            kind = "candidate_EPA_reporting_identity_not_a_unique_generator_dispatch_mapping" if available else "no_2025_EPA_reporting_match_retirement_not_inferred"
        elif not row["role"].startswith("native"):
            kind = "external_or_HQ_boundary_record_not_native_generation_prior"
        r = dict(source_gen_row=int(row["source_gen_row"]), stable_key=row["stable_key"], role=row["role"],
                 full_source_bus=int(full_gen[int(row["source_gen_row"]) - 1, 0]),
                 source_57_bus=int(row["source_bus"]), native_full_bus=row["source_bus"] if row["role"].startswith("native") else "",
                 NYISO_name=row["NYISO_name"], PTID=row["PTID"],
                 candidate_EPA_device_keys=";".join(f"EPA:ORIS:{a}:UNIT:{b}" for a, b in available),
                 mapping_status=kind, dispatch_assigned=0, retirement_confirmed=0)
        if r["source_gen_row"] in [232, 233]:
            r.update(mapping_status="Indian_Point_confirmed_retired_excluded_from2025", retirement_confirmed=1)
        output.append(r)
    frame_write(sources.out / "full_2019_generator_mapping.csv", output)
    fleet = [dict(asset="Indian Point 2", zone="H", source_identity="EIA:2497:2;NYGRID2019:GEN:232", status_2025="retired",
        effective_date="2020-04-30", included_in_2025_prior=0, legacy_landing_qualified=1,
        evidence_url="https://www.nrc.gov/facilities-safety/facility-finder/reactors/ip2"),
        dict(asset="Indian Point 3", zone="H", source_identity="EIA:8907:3;NYGRID2019:GEN:233", status_2025="retired",
        effective_date="2021-04-30", included_in_2025_prior=0, legacy_landing_qualified=1,
        evidence_url="https://www.eia.gov/todayinenergy/detail.php?id=50619"),
        dict(asset="Cricket Valley CC1-CC3", zone="G", source_identity="EPA:ORIS:57185:U001|U002|U003",
        status_2025="positive2025_EPA_reporting_new_to_legacy_fleet", effective_date="2020-04_full_commercial_operation",
        included_in_2025_prior=1, legacy_landing_qualified=0,
        evidence_url="https://api.epa.gov/easey/bulk-files/facility/facility-2025.csv",
        commissioning_evidence_url="https://www.cricketvalley.com/wp-content/uploads/2025/01/Ambient-Air-Quality-Monitoring-Data-Review.pdf"),
        dict(asset="South Fork Wind", zone="K", source_identity="EIA860:PLANT:65561",
        status_2025="active_EIA_inventory_new_to_legacy_wind_placement", effective_date="2024-03",
        included_in_2025_prior=1, legacy_landing_qualified=0, evidence_url="https://southforkwind.com/about-south-fork-wind")]
    frame_write(sources.out / "fleet_change_register.csv", fleet)
    return dict(legacy_rows=len(output), thermal_rows_order_and_bus_assignment_verified=227,
                complete_2025_unit_dispatch_mapping=False, full_source_bus_verified_from_base_case=True,
                parameter_csv_position_differences=order_differences,
                thermal_identity_join="exact_NYISO_name_and_PTID_preserving_captured_constructor_row_order",
                source_57_bus_is_separate_reduced_reference=True)


def build(output=OUT, offline=False):
    output = Path(output).resolve()
    allowed = (ROOT / "output/nygrid_2025_inputs/generation_source").resolve()
    if output != allowed and not output.is_relative_to(allowed):
        raise ValueError("Generation outputs must remain in the assigned generation_source tree")
    output.mkdir(parents=True, exist_ok=True)
    sources = Sources(output, offline)
    for path in [Path(__file__), Path(__file__).with_name("test_generation_priors.py"), ROOT / "build_compact_epa_generation_inputs.py", ROOT / "build_compact_nonfossil_generation_inputs.py"]:
        sources.local(path, "CODE:" + path.name, role="reused_source_method_not_compact_dispatch")
    axis = hour_axis(); frame_write(output / "hour_axis.csv", axis)
    totals, quals, p63_summary = fuelmix(sources, axis)
    arrays, units, ng, epa_summary = extract_epa(sources, axis)
    inventory, hydro = source_inventory(sources)
    nrc = nrc_inputs(sources)
    allocation = allocate(sources, axis, totals, quals, arrays, inventory, hydro, nrc)
    mapping = legacy_mapping(sources, units, ng, inventory)
    frame_write(output / "source_manifest.csv", list(sources.rows.values()))
    summary = dict(schema_version=1, stage="actual_MW_generation_source_priors", year=2025,
        created_utc=dt.datetime.now(UTC).isoformat(), hours=N, utc_start=axis.iloc[0].timestamp_utc,
        utc_last_hour=axis.iloc[-1].timestamp_utc, state_fuel_categories=FUELS, prior_fuel_categories=PRIOR_FUELS,
        p63=p63_summary, epa=epa_summary, allocation=allocation, legacy_mapping=mapping,
        unmapped_positive_EPA_units=[{k: r[k] for k in ["facility_id", "unit_id", "facility_name", "county", "positive_reported_gross_hours"]}
                                    for r in units if r["zone"] == "UNMAPPED" and r["positive_reported_gross_hours"] > 0],
        gamma_applied=False, internal_interface_targets_used=False, compact_dispatch_used=False,
        ready_for_dc_power_flow=False, dispatch_feasibility_established=False,
        policies=dict(p63=P63_POLICY, epa="gross_rate_times_operating_fraction_once; unique_ORIS_unit_hour; blank_is_not_observed_zero",
            fossil="P63 combined fossil normalized by available eligible EPA gross zone shares; gross shares do not measure net zonal generation",
            mapping="2019 crosswalk continuity and explicit2025 facility zones; many-to-many identifiers annotate, never duplicate MW",
            nuclear="NRC daily availability times seasonal EIA capability, normalized to P63; previous report before08:00 Eastern",
            hydro="monthly conventional baseline and finite HY/PS headroom; no reservoir or pumping schedule; EIA annual-respondent months are estimates",
            wind="EIA active capacities, identical statewide capacity factor assumption; SouthFork is a subset of K, never additional",
            other="EIA active capacity with geometric daylight for solar; category/BTM coverage remains approximate",
            inventory="2025 early release; OP/SB eligible, OA/OS excluded; start-month excluded until next month, retirement-month excluded",
            qualification="time/source/share arithmetic only; qualified prior is not a solved or capability-qualified dispatch"),
        limitations=["Missing or unqualified P63/prior values remain NaN; no silent fill",
            "EPA absent and blank reports do not establish zero observed electricity",
            "EPA gross/CHP coverage differs from NYISO net generation; Riverbay excluded from grid shares but retained in gross ledger",
            "Plant geography includes explicit site zones plus labeled county proxies",
            "Cricket Valley and South Fork have no qualified full2019 electrical landing",
            "Many-to-many thermal mapping, nonfossil aggregation, storage energy and hourly capability remain unresolved",
            "Indian Point2/3 are excluded; absence from EPA alone is not used as a retirement proof",
            "No 37-generator compact dispatch or scaling was read"])
    (output / "generation_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    artifacts = [dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=sha(p))
                 for p in sorted(output.iterdir()) if p.is_file() and p.name != "output_manifest.csv"]
    frame_write(output / "output_manifest.csv", artifacts)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    build(args.output, args.offline)
