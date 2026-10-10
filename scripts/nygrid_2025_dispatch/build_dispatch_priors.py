"""Map frozen 2025 source estimates to unique EIA fleet rows, without dispatch.

Preferred generation is a soft estimate, not observed unit net generation or a
bound-feasible solution. Unique EPA reporting-unit weights are allocated once;
many-to-many crosswalks never duplicate MW or fleet capacity. Nuclear and hydro
plant priors are reused, and renewable capacity/daylight allocation follows the
frozen source method. The 74th Street location repair is a separate ledger.

All quantities are unscaled public MW. The root dispatch stage applies gamma.
No interface targets, solved dispatch, or model-flow residuals are read.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import sys
import urllib.request

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output/nygrid_2025_inputs"
SOURCE = INPUT / "generation_source"
FLEET = ROOT / "output/nygrid_2025_dispatch/fleet"
OUT = ROOT / "output/nygrid_2025_dispatch/priors"
ZONES = list("ABCDEFGHIJK")
FUELS = ["Combined Fossil", "Nuclear", "Hydro", "Wind", "Other Renewables"]
BOUNDARY_CHANNELS = ["SCH - HQ - NY", "SCH - HQ_CEDARS", "SCH - OH - NY", "SCH - NE - NY",
                     "SCH - NPX_1385", "SCH - NPX_CSC", "SCH - PJ - NY", "SCH - PJM_HTP",
                     "SCH - PJM_NEPTUNE", "SCH - PJM_VFT"]
XWALK = ROOT / "output/compact_ny_2025/generation_sources/epa/epa_eia_crosswalk_ny.csv"
LEGACY_EPA_ATTRIBUTES = ROOT / "tmp/epa_generation_raw/facility-2025.csv"
NJ_RAW = ROOT / "tmp/epa_generation_raw/emissions-hourly-2025-nj.csv"
NJ_URL = "https://api.epa.gov/easey/bulk-files/emissions/hourly/state/emissions-hourly-2025-nj.csv"
NJ_SCOPE = {56964: {f"GT{i}" for i in range(1, 11)},
            50006: {f"GTG{i}" for i in range(1, 6)} | {f"STG{i}" for i in range(1, 4)}}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def boolean(values):
    s = pd.Series(values).astype(str).str.lower()
    require(s.isin(["true", "false", "1", "0", "1.0", "0.0"]).all(), "Unknown qualification boolean")
    return s.isin(["true", "1", "1.0"]).to_numpy()


def write_csv(frame, path):
    compression = {"method": "gzip", "mtime": 0} if path.suffix == ".gz" else None
    frame.to_csv(path, index=False, lineterminator="\n", compression=compression)


def clean_id(value):
    s = str(value).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def preserve_facility_metadata(output):
    """Use a durable exact-byte metadata copy; ignored cache is bootstrap only."""
    manifest = pd.read_csv(SOURCE / "source_manifest.csv", dtype=str)
    match = manifest.loc[manifest.source_id.eq("EPA:facility-2025.csv"), "sha256"]
    require(len(match) == 1, "Frozen facility metadata hash is not unique")
    expected = match.iloc[0]
    target = output / "source_metadata/facility-2025.csv"
    if not target.exists():
        candidates = [OUT / "source_metadata/facility-2025.csv", LEGACY_EPA_ATTRIBUTES]
        source = next((p for p in candidates if p.is_file() and sha(p) == expected), None)
        require(source is not None, "Verified facility metadata unavailable")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    require(sha(target) == expected, "Durable facility metadata hash mismatch")
    return target


def association_ids(text):
    """Read official associated-generator labels; never equate EPA unit names."""
    names = re.findall(r"(?:^|,)\s*([^(),]+?)\s*\([^()]*\)", str(text))
    require(bool(names), "EPA associated-generator metadata could not be parsed")
    return {clean_id(v) for v in names}


def nj_admission(facility_id, associated):
    if facility_id == 56964:
        require(len(associated) == 1 and associated.issubset(NJ_SCOPE[56964]), "Bayonne source association is not uniquely admitted")
        return True, "official_2025_one_to_one_associated_generator"
    require(facility_id == 50006, "Unexpected NJ facility")
    if "GTG6" in associated:
        return False, "exclude_GT6_linked_group_conservative_prior_rule_shared_steam_market_attribution_unresolved"
    gas = associated & {f"GTG{i}" for i in range(1, 6)}
    require(len(gas) == 1 and associated.issubset(NJ_SCOPE[50006]), "Linden reporting association is not a declared native group")
    return True, "five_unique_reporting_groups_pooled_once_then_eight_unique_EIA_capacity_partition"


def ensure_nj_extract(output, hours, fleet, physical, attributes_path):
    """Persist only the two target plants; the full state bulk stays ignored."""
    extract = output / "nj_native_epa_unit_hourly.csv.gz"
    register_path = output / "nj_epa_unit_scope_register.csv"
    receipt_path = output / "nj_epa_extraction_receipt.json"
    # A shipped, hash-verified narrow extract suffices for a clean rebuild.
    # Its source-record bytes/hashes retain the official raw rows independently
    # of the large ignored annual state file.
    if output != OUT.resolve() and not receipt_path.exists() and (OUT / receipt_path.name).exists():
        prior_receipt = json.loads((OUT / receipt_path.name).read_text())
        for name, key in [(extract.name, "extract_sha256"), (register_path.name, "register_sha256")]:
            require(sha(OUT / name) == prior_receipt[key], "Delivered NJ extract hash mismatch")
            shutil.copyfile(OUT / name, output / name)
        shutil.copyfile(OUT / receipt_path.name, receipt_path)
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        require(sha(extract) == receipt["extract_sha256"] and sha(register_path) == receipt["register_sha256"], "NJ extract receipt mismatch")
        require(sha(attributes_path) == receipt["facility_metadata_sha256"], "NJ facility association metadata changed")
        registry = pd.read_csv(register_path, dtype=str).fillna("")
        records = pd.read_csv(extract, dtype={"facility_id": str, "unit_id": str})
    else:
        raw_receipt = NJ_RAW.with_suffix(NJ_RAW.suffix + ".provenance.json")
        if not NJ_RAW.exists():
            NJ_RAW.parent.mkdir(parents=True, exist_ok=True)
            request = urllib.request.Request(NJ_URL, headers={"User-Agent": "NYgrid2025-native-fleet-source-audit/1.0"})
            partial = NJ_RAW.with_suffix(NJ_RAW.suffix + ".partial")
            require(not partial.exists(), "Partial NJ download exists; preserve and inspect before retry")
            h = hashlib.sha256(); size = 0
            with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as out:
                meta = {"source_url": NJ_URL, "http_status": response.status,
                    "http_last_modified": response.headers.get("Last-Modified", ""), "http_etag": response.headers.get("ETag", "")}
                while True:
                    chunk = response.read(4 * 1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk); h.update(chunk); size += len(chunk)
            partial.replace(NJ_RAW)
            meta.update(path=str(NJ_RAW.relative_to(ROOT)).replace("\\", "/"), bytes=size, sha256=h.hexdigest(),
                retrieved_utc=dt.datetime.now(dt.timezone.utc).isoformat(), acquisition="fresh_official_EPA_bulk_download")
            raw_receipt.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")
        require(raw_receipt.exists(), "NJ raw cache has no provenance receipt")
        raw_meta = json.loads(raw_receipt.read_text())
        require(raw_meta["source_url"] == NJ_URL and raw_meta["sha256"] == sha(NJ_RAW), "NJ raw source hash mismatch")
        attrs = pd.read_csv(attributes_path, dtype=str).fillna("")
        attrs = attrs[attrs["Facility ID"].isin([str(p) for p in NJ_SCOPE]) & attrs.State.eq("NJ")]
        require(len(attrs) == 16 and not attrs.duplicated(["Facility ID", "Unit ID"]).any(), "Expected sixteen NJ reporting groups")
        reg = []
        for r in attrs.to_dict("records"):
            pid = int(r["Facility ID"]); names = association_ids(r["Associated Generators & Nameplate Capacity (MWe)"])
            admitted, policy = nj_admission(pid, names)
            reg.append({"facility_id": str(pid), "unit_id": r["Unit ID"], "device_key": f"EPA:ORIS:{pid}:UNIT:{r['Unit ID']}",
                "facility_name": r["Facility Name"], "zone": "J", "source_state": "NJ",
                "grid_fossil_share_eligible": int(admitted), "associated_generators": r["Associated Generators & Nameplate Capacity (MWe)"],
                "associated_generator_ids": "|".join(sorted(names)), "NJ_admission_policy": policy,
                "source_category": r["Source Category"], "county": r["County"],
                "shared_steam_attribution_unresolved": int(pid == 50006), "unit_net_generation_observed": 0})
        registry = pd.DataFrame(reg).sort_values(["facility_id", "unit_id"]).reset_index(drop=True)
        require(registry.loc[registry.grid_fossil_share_eligible.eq(0), "unit_id"].tolist() == ["004001"], "Unexpected excluded Linden reporting identity")
        by_key = {(r.facility_id, r.unit_id): r for r in registry.itertuples()}
        sys.path.insert(0, str(ROOT))
        from build_compact_epa_generation_inputs import iter_source_records, convert_gross
        rows = []; seen = set()
        for ordinal, r, raw_bytes in iter_source_records(NJ_RAW):
            if r["Facility ID"] not in {"50006", "56964"}:
                continue
            require(r["State"] == "NJ", "Target raw record is not NJ")
            key = (r["Facility ID"], r["Unit ID"])
            require(key in by_key, "Unknown NJ target reporting unit")
            date = dt.date.fromisoformat(r["Date"]); hour = int(r["Hour"])
            require(date.year == 2025 and 0 <= hour < 24, "Invalid NJ source date/hour")
            h = (date - dt.date(2025, 1, 1)).days * 24 + hour
            identity = (h, key)
            require(identity not in seen, "Duplicated NJ reporting-unit hour")
            seen.add(identity)
            gross, op, value, status = convert_gross(r)
            meta = by_key[key]
            rows.append({"hour_index": h + 1, "timestamp_utc": hours.timestamp_utc.iloc[h],
                "facility_id": key[0], "unit_id": key[1], "device_key": meta.device_key,
                "source_state": "NJ", "zone": "J", "grid_fossil_share_eligible": int(meta.grid_fossil_share_eligible),
                "source_gross_load_mw": gross, "operating_time_hours": op, "gross_clock_hour_average_mw": value,
                "gross_quantity_status": status, "source_record_ordinal": ordinal,
                "source_record_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "source_record_base64": base64.b64encode(raw_bytes).decode("ascii")})
        records = pd.DataFrame(rows)
        require(len(records) == 16 * 8760, "Incomplete target-plant EPA reporting coverage")
        write_csv(records, extract); write_csv(registry, register_path)
        receipt = {"scope": "Only Bayonne56964 and Linden50006 reporting records; originalNJstate bulk remains ignored cache",
            "source_url": NJ_URL, "raw_source_sha256": raw_meta["sha256"], "raw_source_bytes": raw_meta["bytes"],
            "source_retrieved_utc": raw_meta.get("retrieved_utc", ""), "http_last_modified": raw_meta.get("http_last_modified", ""),
            "raw_cache_role": "ignored_download_cache_not_required_when_verified_target_extract_available",
            "facility_metadata_path": str(attributes_path.relative_to(ROOT)).replace("\\", "/"), "facility_metadata_sha256": sha(attributes_path),
            "facility_metadata_url": "https://api.epa.gov/easey/bulk-files/facility/facility-2025.csv",
            "extract_sha256": sha(extract), "register_sha256": sha(register_path), "selected_source_unit_hours": len(records),
            "reporting_units": 16, "admitted_reporting_units": 15, "excluded_reporting_units": ["EPA:ORIS:50006:UNIT:004001"],
            "time_policy": "EPA fixed EST clock-hour date/hour mapped to canonical UTC; no daylight clock shift",
            "quantity_policy": "reported gross MW times operating fraction once, matching existing independently validated EPA convention",
            "Linden_shared_steam_limitation": "Excluded GTG6 reporting group004001 also lists NYISO steam units; no defensible hourly shared-steam split is available. Its entire gross weight is conservatively excluded. Five admitted reporting groups are pooled once and partitioned over eight unique native EIA generators.",
            "native_scope_evidence": "Current fleet outside_NY_scope_register.csv: primary NYISO P19 and2025GoldBook unit admission; VFT remains a separate transmission schedule"}
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    require(not records.duplicated(["hour_index", "device_key"]).any() and len(records) == 16 * 8760, "NJ target extract hour identity error")
    # Keep explanatory labels current without reinterpreting any source value.
    for i, row in registry.iterrows():
        admitted, policy = nj_admission(int(row.facility_id), set(row.associated_generator_ids.split("|")))
        require(admitted == bool(boolean([row.grid_fossil_share_eligible])[0]), "NJ admission policy changed")
        registry.loc[i, "NJ_admission_policy"] = policy
    write_csv(registry, register_path)
    receipt.update(register_sha256=sha(register_path), facility_metadata_path=str(attributes_path.relative_to(ROOT)).replace("\\", "/"),
        excluded_group_is_verified_all_PJM_energy=False,
        excluded_group_policy="Whole-group zero allocation weight is a conservative prior-construction choice, not verified hourly energy attribution; GTG6-linked group includes shared NYISO steam generators")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    for plant, expected in NJ_SCOPE.items():
        group = fleet[fleet.plant_id.eq(plant)]
        admitted = set(group.loc[boolean(group.unit_market_scope_eligible), "eia_generator_id"])
        require(admitted == expected, f"NJ EPA weights do not match the corroborated fleet admission: {plant}")
    gross = records.pivot(index="hour_index", columns="device_key", values="gross_clock_hour_average_mw").reindex(index=range(1, 8761), columns=registry.device_key).to_numpy(float)
    require(not np.isinf(gross).any() and (gross[np.isfinite(gross)] >= 0).all(), "Invalid NJ gross weight")
    included = boolean(registry.grid_fossil_share_eligible)
    weights = np.nan_to_num(gross) * included
    unit_audit = registry.copy()
    unit_audit["reported_hours"] = records.groupby("device_key").size().reindex(registry.device_key).to_numpy()
    unit_audit["positive_reported_gross_hours"] = np.count_nonzero(np.nan_to_num(gross) > 0, axis=0)
    unit_audit["missing_gross_observation_hours"] = np.count_nonzero(np.isnan(gross), axis=0)
    unit_audit["reported_gross_energy_mwh"] = np.nansum(gross, axis=0)
    unit_audit["admitted_gross_weight_energy_mwh"] = weights.sum(axis=0)
    write_csv(unit_audit, output / "nj_unit_quantity_audit.csv")
    gt6 = np.flatnonzero(fleet.plant_id.eq(50006).to_numpy() & fleet.eia_generator_id.eq("GTG6").to_numpy())
    require(len(gt6) == 1, "Linden GTG6 EIA identity is not unique")
    excluded = records[records.facility_id.eq("50006") & records.unit_id.eq("004001")]
    require(len(excluded) == 8760, "Excluded reporting group coverage differs")
    cap = physical[excluded.hour_index.to_numpy(int) - 1, gt6[0]]
    gross_clock = excluded.gross_clock_hour_average_mw.to_numpy(float)
    conflict = {"EPA_reporting_group": "EPA:ORIS:50006:UNIT:004001", "associated_generators": "GTG6|STG1|STG2|STG3",
        "single_EIA_generator": fleet.iloc[gt6[0]].device_key,
        "EIA_GTG6_nameplate_mw": float(fleet.iloc[gt6[0]].nameplate_capacity_mw),
        "EIA_GTG6_summer_net_capacity_mw": float(fleet.iloc[gt6[0]].summer_capacity_mw),
        "EIA_GTG6_winter_net_capacity_mw": float(fleet.iloc[gt6[0]].winter_capacity_mw),
        "EPA_group_max_reported_gross_rate_mw": float(excluded.source_gross_load_mw.max()),
        "EPA_group_max_gross_clock_average_mw": float(np.nanmax(gross_clock)),
        "finite_group_gross_hours": int(np.isfinite(gross_clock).sum()),
        "group_gross_clock_average_above_single_unit_net_capacity_hours": int(np.count_nonzero(gross_clock > cap + 1e-8)),
        "not_like_for_like_comparison": True, "equipment_overload_inferred": False,
        "all_group_energy_claimed_PJM": False,
        "interpretation": "Reporting-group gross covers overlapping generator associations and is not single-unit net telemetry; the exceedance diagnostic demonstrates that treating this entire group as GTG6 output would be unsupported"}
    (output / "nj_excluded_group_scope_diagnostic.json").write_text(json.dumps(conflict, indent=2) + "\n", encoding="utf-8", newline="\n")
    summary = {**receipt, "missing_gross_observation_cells": int(np.isnan(gross).sum()),
        "admitted_gross_weight_energy_mwh": float(weights.sum()),
        "excluded_GT6_group_reported_gross_energy_mwh": float(np.nansum(gross[:, ~included])),
        "admitted_reporting_unit_positive_hours": int(np.count_nonzero(weights > 0)),
        "excluded_group_scope_diagnostic": conflict}
    return registry, weights, summary, [extract, register_path, receipt_path]


def normalize_weights(weights, total, qualified):
    """Normalize source weights once per hour; missing source stays missing."""
    w, total = np.asarray(weights, float), np.asarray(total, float)
    require(w.ndim == 2 and w.shape[0] == len(total), "Bad normalization shape")
    require(np.isfinite(w).all() and (w >= 0).all(), "Invalid allocation weights")
    denominator = w.sum(axis=1)
    ok = np.asarray(qualified, bool) & np.isfinite(total) & (total >= 0) & ((denominator > 0) | (total == 0))
    out = np.full_like(w, np.nan)
    factor = np.full(len(total), np.nan)
    nonzero = ok & (denominator > 0)
    factor[nonzero] = total[nonzero] / denominator[nonzero]
    out[nonzero] = w[nonzero] * factor[nonzero, None]
    out[ok & (denominator == 0)] = 0
    require(np.max(np.abs(out[ok].sum(axis=1) - total[ok]), initial=0) < 1e-6, "Allocation loses statewide MW")
    return out, ok, factor


def capacity_split(capacity):
    c = np.asarray(capacity, float)
    require(c.ndim == 1 and len(c) > 0 and np.isfinite(c).all() and (c >= 0).all() and c.sum() > 0,
            "No usable positive capacity for source split")
    return c / c.sum()


def solar_weights(local_times, latitude, longitude):
    """Vectorized frozen geometric daylight formula; no weather inference."""
    day = local_times.dayofyear.to_numpy()
    dec = np.deg2rad(23.44 * np.sin(2 * np.pi * (284 + day) / 365.25))
    is_dst = np.asarray(local_times.strftime("%Z") == "EDT", float)
    clock = local_times.hour.to_numpy() + 0.5 - is_dst
    lat = np.deg2rad(np.asarray(latitude, float))
    solar_hour = clock[:, None] + (np.asarray(longitude)[None, :] + 75) / 15
    hour_angle = np.deg2rad(15 * (solar_hour - 12))
    return np.maximum(0, np.sin(dec[:, None]) * np.sin(lat) + np.cos(dec[:, None]) * np.cos(lat) * np.cos(hour_angle))


def active_month(row, month):
    start = (int(row.operating_year), int(row.operating_month))
    if start >= (2025, month) or row.source_status not in {"OP", "SB", "RE"}:
        return False
    if row.source_status == "RE":
        end = (int(row.retirement_year), int(row.retirement_month))
        if end[0] <= 0 or end[1] <= 0 or (2025, month) >= end:
            return False
    return True


def source_state():
    hours = pd.read_csv(INPUT / "load_source/hour_catalog.csv")
    utc = pd.DatetimeIndex(pd.to_datetime(hours.timestamp_utc, utc=True))
    require(utc.equals(pd.date_range("2025-01-01 05:00Z", periods=8760, freq="h")), "Wrong source hour axis")
    fuel = pd.read_csv(SOURCE / "statewide_fuelmix_hourly.csv")
    require(not fuel.duplicated(["hour_index", "fuel_category"]).any(), "Duplicate statewide fuel key")
    values = fuel.pivot(index="hour_index", columns="fuel_category", values="generation_mw").reindex(range(1, 8761))
    q = fuel.assign(q=boolean(fuel.coverage_qualified)).pivot(index="hour_index", columns="fuel_category", values="q").reindex(range(1, 8761))
    fossil = ["Dual Fuel", "Natural Gas", "Other Fossil Fuels"]
    totals = {f: values[f].to_numpy(float) for f in FUELS[1:]}
    totals["Combined Fossil"] = values[fossil].sum(axis=1, min_count=3).to_numpy(float)
    qualified = {f: q[f].to_numpy(bool) for f in FUELS[1:]}
    qualified["Combined Fossil"] = q[fossil].all(axis=1).to_numpy(bool)
    boundary = pd.read_csv(INPUT / "load_source/interface_quality_wide.csv")
    require(np.array_equal(boundary.timestamp_utc, hours.timestamp_utc), "Boundary hour axis differs")
    boundary_ok = np.column_stack([boolean(boundary[c]) for c in BOUNDARY_CHANNELS]).all(axis=1)
    return hours, utc, totals, qualified, boundary_ok


def epa_source_weights(hours, output, attributes_path):
    registry = pd.read_csv(SOURCE / "epa_unit_identity_register.csv", dtype=str).fillna("")
    require(registry.device_key.is_unique, "EPA unit identity not unique")
    key_to_col = {k: j for j, k in enumerate(registry.device_key)}
    source = pd.read_csv(SOURCE / "epa_unit_hourly.csv.gz", usecols=["hour_index", "device_key", "gross_clock_hour_average_mw"])
    require(not source.duplicated(["hour_index", "device_key"]).any(), "EPA unit-hour observation duplicated")
    require(source.device_key.isin(key_to_col).all(), "Unknown EPA unit")
    gross = np.full((8760, len(registry)), np.nan)
    rows = source.hour_index.to_numpy(int) - 1
    cols = source.device_key.map(key_to_col).to_numpy(int)
    gross[rows, cols] = source.gross_clock_hour_average_mw.to_numpy(float)
    require(not np.isinf(gross).any() and (gross[np.isfinite(gross)] >= 0).all(), "Invalid EPA gross observation")
    attrs = pd.read_csv(attributes_path, dtype=str).fillna("")
    evidence = attrs[(attrs["Facility ID"] == "2504") & (attrs["Year"] == "2025")]
    require(len(evidence) >= 2 and evidence["County"].eq("New York County").all() and evidence["FIPS Code"].eq("061").all(),
            "74th Street location evidence differs")
    repairs = []
    zones = registry.zone.to_numpy(str).copy()
    for j, row in enumerate(registry.itertuples()):
        if row.facility_id != "2504":
            continue
        e = evidence[evidence["Unit ID"] == row.unit_id]
        require(len(e) == 1, "74th Street EPA unit location not unique")
        require(abs(float(e.iloc[0]["Latitude"]) - 40.768) < 1e-6 and abs(float(e.iloc[0]["Longitude"]) + 73.9515) < 1e-6,
                "74th Street site coordinates differ")
        positive = np.flatnonzero(np.nan_to_num(gross[:, j]) > 0)
        repairs.append({"device_key": row.device_key, "old_zone": row.zone, "repaired_zone": "J",
            "positive_hours": len(positive), "positive_hour_indices": "|".join(str(v + 1) for v in positive),
            "reported_gross_annual_mwh": float(np.nansum(gross[:, j])),
            "source_evidence": "EPA2025_New_York_County_FIPS061_site_40.768_-73.9515_in_NYISO_NYC_zoneJ",
            "source_path": str(attributes_path.relative_to(ROOT)).replace("\\", "/"), "source_sha256": sha(attributes_path),
            "generation_observation_changed": False})
        zones[j] = "J"
    eligible = boolean(registry.grid_fossil_share_eligible)
    weights = np.nan_to_num(gross, nan=0) * eligible
    unlocated = ~np.isin(zones, ZONES)
    remaining = weights[:, unlocated].sum(axis=1)
    repaired_zone_weights = np.column_stack([weights[:, zones == zone].sum(axis=1) for zone in ZONES])
    require(np.max(np.abs(repaired_zone_weights.sum(axis=1) + remaining - weights.sum(axis=1)), initial=0) < 1e-6,
            "EPA zone repair changes gross weight")
    write_csv(pd.DataFrame(repairs), output / "epa_location_repairs.csv")
    summary = {"reporting_units": len(registry), "unique_source_unit_hours": len(source),
        "missing_gross_observation_cells": int(np.isnan(gross).sum()), "repair_unit_rows": len(repairs),
        "repair_positive_units": sum(r["positive_hours"] > 0 for r in repairs),
        "repair_positive_hours": int(np.count_nonzero(weights[:, registry.facility_id.eq("2504")].sum(axis=1) > 0)),
        "remaining_positive_unmapped_hours": int(np.count_nonzero(remaining > 1e-9)),
        "missing_observations_are_zero": False,
        "weight_policy": "Only reported eligible gross contributes allocation weight; absent/blank observations remain missing in frozen evidence, not observed zero"}
    return registry, weights, zones, remaining, repaired_zone_weights, summary


def thermal_prior(fleet, physical, registry, weights, repaired_zones, totals, qualified, months):
    ng = len(fleet)
    allocated = np.zeros((8760, ng))
    xwalk = pd.read_csv(XWALK, dtype=str).fillna("")
    keys = {(int(r.plant_id), clean_id(r.eia_generator_id)): j for j, r in enumerate(fleet.itertuples())}
    require(len(keys) == ng, "Fleet plant/generator capacity identity duplicated")
    records = []
    linden_columns = np.flatnonzero(registry.facility_id.eq("50006").to_numpy()
        & registry.source_state.eq("NJ").to_numpy() & boolean(registry.grid_fossil_share_eligible))
    linden_pooled = False
    for u, row in enumerate(registry.itertuples()):
        if not np.any(weights[:, u] > 0):
            continue
        unit_weight = weights[:, u]
        reporting_keys = [row.device_key]
        source_key = row.device_key
        forced_method = None
        cross = xwalk[(xwalk.CAMD_PLANT_ID == row.facility_id) & (xwalk.CAMD_UNIT_ID == row.unit_id)]
        paired = {(int(float(r.EIA_PLANT_ID)), clean_id(r.EIA_GENERATOR_ID)) for r in cross.itertuples()
                  if r.EIA_PLANT_ID and r.EIA_GENERATOR_ID}
        exact = sorted({keys[k] for k in paired if k in keys and fleet.iloc[keys[k]].fuel_category == "Combined Fossil"})
        if int(row.facility_id) == 57185:
            exact = []  # EPA U001 is a train, not EIA U001 steam-unit identity.
        plant_ids = {int(row.facility_id)} | {p for p, _ in paired}
        plant = np.flatnonzero(fleet.plant_id.isin(plant_ids).to_numpy() & fleet.fuel_category.eq("Combined Fossil").to_numpy()).tolist()
        if row.source_state == "NJ":
            if row.facility_id == "56964":
                associated = set(row.associated_generator_ids.split("|"))
                require(len(associated) == 1, "Bayonne association is not one-to-one")
                exact = [keys[(56964, name)] for name in associated]
                forced_method = "NJ_Bayonne_official2025_associated_generator_one_to_one"
            elif row.facility_id == "50006":
                if linden_pooled:
                    continue
                require(len(linden_columns) == 5, "Linden native reporting pool must contain five groups")
                linden_pooled = True
                unit_weight = weights[:, linden_columns].sum(axis=1)
                reporting_keys = registry.iloc[linden_columns].device_key.tolist()
                source_key = "EPA_POOL:50006:NYISO_FIVE_REPORTING_GROUPS"
                exact = sorted(keys[(50006, name)] for name in NJ_SCOPE[50006])
                require(len(exact) == 8, "Linden native EIA capacity must be owned by eight unique rows")
                forced_method = "NJ_Linden_five_reporting_groups_once_eight_unique_capacity_partition_shared_steam_uncertain"
            else:
                raise ValueError("Undeclared NJ source pool")
        for month in range(1, 13):
            ix = np.flatnonzero(months == month)
            if not np.any(unit_weight[ix] > 0):
                continue
            candidates = exact or plant
            method = forced_method or ("paired_EPA_EIA_crosswalk_capacity_partition" if exact else "same_plant_capacity_partition_no_unique_unit_crosswalk")
            if not candidates:
                candidates = np.flatnonzero(fleet.zone.eq(repaired_zones[u]).to_numpy() & fleet.fuel_category.eq("Combined Fossil").to_numpy()
                                             & (physical[ix[0]] > 0)).tolist()
                method = "unrepresented_EPA_identity_same_zone_capacity_proxy"
            require(bool(candidates), f"No fleet landing for positive EPA unit {row.device_key}")
            capacity = physical[ix[0], candidates]
            if capacity.sum() <= 0:
                capacity = fleet.iloc[candidates].nameplate_capacity_mw.to_numpy(float)
                method += "_source_preference_on_temporally_bound_off_identity"
            shares = capacity_split(capacity)
            for j, share in zip(candidates, shares):
                if share <= 0:
                    continue
                allocated[ix, j] += unit_weight[ix] * share
                records.append({"month": month, "EPA_device_key": source_key,
                    "source_reporting_unit_count": len(reporting_keys), "source_reporting_unit_keys": "|".join(reporting_keys),
                    "fleet_id": int(fleet.iloc[j].fleet_id),
                    "fleet_device_key": fleet.iloc[j].device_key, "weight_share": float(share), "mapping_method": method,
                    "reported_source_gross_mwh": float(unit_weight[ix].sum()),
                    "assigned_gross_weight_mwh": float(unit_weight[ix].sum() * share),
                    "unit_net_output_observed": False})
    error = np.max(np.abs(allocated.sum(axis=1) - weights.sum(axis=1)), initial=0)
    require(error < 1e-6, f"EPA reporting-unit output was duplicated or dropped: {error}")
    prior, ok, factor = normalize_weights(allocated, totals, qualified)
    return prior, ok, factor, pd.DataFrame(records), error


def nonfossil_prior(fleet, physical, local, totals, source_q):
    ng = len(fleet)
    output = np.zeros((8760, ng))
    nuclear_cap = np.zeros_like(output)
    key = {(int(r.plant_id), clean_id(r.eia_generator_id)): j for j, r in enumerate(fleet.itertuples())}
    methods = []
    nuclear = pd.read_csv(SOURCE / "nuclear_plant_hourly_priors.csv.gz", dtype={"generator_id": str})
    require(not nuclear.duplicated(["hour_index", "plant_id", "generator_id"]).any(), "Duplicated NRC reactor-hour prior")
    for (plant, generator), block in nuclear.groupby(["plant_id", "generator_id"], sort=False):
        j = key[(int(plant), clean_id(generator))]
        ix = block.hour_index.to_numpy(int) - 1
        require(len(ix) == 8760 and len(np.unique(ix)) == 8760, "Missing reactor-hour source")
        output[ix, j] = block.estimated_actual_mw.to_numpy(float)
        nuclear_cap[ix, j] = block.availability_weight_mw.to_numpy(float)
        methods.append({"fleet_id": int(fleet.iloc[j].fleet_id), "source_kind": "NRC_reactor_hour", "source_plant": int(plant),
                        "method": "frozen_daily_NRC_weight_normalized_to_P63_no_new_forecast"})
    inventory = pd.read_csv(SOURCE / "eia860_nonfossil_inventory_2025.csv", dtype={"generator_id": str})
    hydro = pd.read_csv(SOURCE / "hydro_monthly_plant_allocation_register.csv")
    month_array = local.month.to_numpy()
    for month in range(1, 13):
        saved = np.load(SOURCE / f"hydro_plant_priors_{month:02d}.npz")
        ix = saved["hour_index"].astype(int) - 1
        require(np.array_equal(ix, np.flatnonzero(month_array == month)), "Hydro monthly hour identities differ")
        register = hydro[hydro.month.eq(month)].sort_values("column_index")
        values = saved["prior_actual_mw"]
        require(values.shape == (len(ix), len(register)), "Hydro matrix/register dimensions differ")
        active = inventory[[active_month(r, month) for r in inventory.itertuples()]]
        season = "winter" if month in [11, 12, 1, 2, 3] else "summer"
        for source_row in register.itertuples():
            group = active[active.plant_id.eq(source_row.plant_id) & active.prime_mover.eq(source_row.prime_mover)]
            require(len(group) > 0, "Frozen hydro plant lost its generator identities")
            candidates = [key[(int(r.plant_id), clean_id(r.generator_id))] for r in group.itertuples()]
            capacity = group[season + "_capacity_mw"].to_numpy(float)
            if capacity.sum() <= 0:
                require(np.max(np.abs(np.nan_to_num(values[:, source_row.column_index])), initial=0) < 1e-8,
                        "Positive hydro prior has no source generator capability")
                continue
            shares = capacity_split(capacity)
            for j, share in zip(candidates, shares):
                output[ix, j] += values[:, source_row.column_index] * share
                methods.append({"month": month, "fleet_id": int(fleet.iloc[j].fleet_id), "source_kind": "frozen_hydro_plant_prior",
                    "source_plant": int(source_row.plant_id), "source_column_index": int(source_row.column_index),
                    "unit_share": float(share), "method": "plant_prime_mover_prior_partition_by_frozen_seasonal_capability"})
        for category, code_filter in [("Wind", lambda s: s.eq("WND")),
                                       ("Other Renewables", lambda s: ~s.isin(["NUC", "WAT", "WND"]))]:
            group = active[code_filter(active.energy_source_code)].copy()
            candidates = [key[(int(r.plant_id), clean_id(r.generator_id))] for r in group.itertuples()]
            weights = np.broadcast_to(group.nameplate_capacity_mw.to_numpy(float), (len(ix), len(group))).copy()
            solar = group.energy_source_code.eq("SUN").to_numpy()
            if solar.any():
                weights[:, solar] *= solar_weights(local[ix], group.loc[solar, "latitude"], group.loc[solar, "longitude"])
            allocated, ok, _ = normalize_weights(weights, totals[category][ix], source_q[category][ix])
            require(np.array_equal(ok, source_q[category][ix]), f"Renewable allocation coverage changed: {category}")
            output[np.ix_(ix, candidates)] += allocated
            for j in candidates:
                methods.append({"month": month, "fleet_id": int(fleet.iloc[j].fleet_id), "source_kind": category,
                    "method": "frozen_active_nameplate_capacity_and_solar_geometric_daylight"})
    return output, nuclear_cap, pd.DataFrame(methods)


def resource_bounds(fleet, physical, default_pmax, prior, nuclear_cap, generation_ok):
    generation_ok = np.asarray(generation_ok, bool)
    available = default_pmax.copy()
    variable = boolean(fleet.is_variable_renewable)
    pumped = boolean(fleet.is_pumped_hydro)
    ps_eligible = boolean(fleet.pumped_hydro_prior_eligible)
    battery = boolean(fleet.is_storage) & ~pumped
    nuclear = fleet.fuel_category.eq("Nuclear").to_numpy()
    available[:, variable] = np.minimum(default_pmax[:, variable], np.maximum(0, prior[:, variable]))
    available[:, pumped] = np.minimum(physical[:, pumped], np.maximum(0, prior[:, pumped])) * ps_eligible[pumped]
    available[:, nuclear] = np.minimum(default_pmax[:, nuclear], nuclear_cap[:, nuclear])
    available[:, battery] = 0
    available[~generation_ok] = np.nan
    require(np.isfinite(available[generation_ok]).all() and (available[generation_ok] >= 0).all(), "Invalid available capability")
    require(np.all(available[generation_ok] <= physical[generation_ok] + 1e-8), "Availability exceeds physical capability")
    return available


def build(output=OUT, fleet_folder=FLEET, previous_priors=None):
    output, fleet_folder = Path(output).resolve(), Path(fleet_folder).resolve()
    require(not (output / "dispatch_priors.npz").exists(), "Choose a new output folder; prior evidence already exists")
    output.mkdir(parents=True, exist_ok=True)
    attributes_path = preserve_facility_metadata(output)
    paths = [SOURCE / name for name in ["source_manifest.csv", "statewide_fuelmix_hourly.csv", "epa_unit_identity_register.csv", "epa_unit_hourly.csv.gz",
        "eia860_nonfossil_inventory_2025.csv", "nuclear_plant_hourly_priors.csv.gz", "hydro_monthly_plant_allocation_register.csv",
        "south_fork_hourly_prior.csv", "zonal_generation_priors.csv.gz"]]
    paths += sorted(SOURCE.glob("hydro_plant_priors_*.npz"))
    paths += [fleet_folder / "fleet_register.csv", fleet_folder / "fleet_bounds.npz", XWALK, attributes_path,
              INPUT / "load_source/hour_catalog.csv", INPUT / "load_source/interface_quality_wide.csv", Path(__file__),
              ROOT / "build_compact_epa_generation_inputs.py"]
    if previous_priors is not None:
        previous_priors = Path(previous_priors).resolve()
        require(previous_priors.is_file(), "Previous prior artifact missing")
        # Optional local comparison evidence must never become a prerequisite
        # for reproducing the delivered priors from current frozen sources.
        previous_fingerprint = sha(previous_priors)
    fingerprints = {str(p): sha(p) for p in paths}
    hours, utc, totals, source_q, boundary_ok = source_state()
    local = utc.tz_convert("America/New_York")
    fleet = pd.read_csv(fleet_folder / "fleet_register.csv", dtype={"eia_generator_id": str}, keep_default_na=False)
    require(fleet.fleet_id.tolist() == list(range(1, len(fleet) + 1)) and fleet.device_key.is_unique, "Fleet row identity changed")
    bound = np.load(fleet_folder / "fleet_bounds.npz")
    require(np.array_equal(bound["fleet_id"], fleet.fleet_id) and np.array_equal(bound["hour_index"], np.arange(1, 8761)), "Fleet bound identity mismatch")
    physical, default = bound["physical_pmax_actual_mw"], bound["pmax_actual_mw"]
    require(physical.shape == (8760, len(fleet)) and np.isfinite(physical).all(), "Incomplete physical bounds")
    registry, weights, repaired_zones, remaining, zone_weights, epa_summary = epa_source_weights(hours, output, attributes_path)
    registry["source_state"] = "NY"
    require(not registry.facility_id.isin(["50006", "56964"]).any(), "NJ source already present in NY EPA registry")
    nj_registry, nj_weights, nj_summary, nj_paths = ensure_nj_extract(output, hours, fleet, physical, attributes_path)
    for p in nj_paths:
        paths.append(p); fingerprints[str(p)] = sha(p)
    registry = pd.concat([registry, nj_registry], ignore_index=True).fillna("")
    require(registry.device_key.is_unique, "NJ extension duplicated an EPA reporting identity")
    weights = np.column_stack([weights, nj_weights])
    repaired_zones = np.r_[repaired_zones, np.full(len(nj_registry), "J")]
    zone_weights[:, ZONES.index("J")] += nj_weights.sum(axis=1)
    epa_summary.update(NY_state_reporting_units=epa_summary["reporting_units"],
        NY_state_unique_source_unit_hours=epa_summary["unique_source_unit_hours"],
        NY_state_missing_gross_observation_cells=epa_summary["missing_gross_observation_cells"],
        missing_gross_observation_cells=epa_summary["missing_gross_observation_cells"] + nj_summary["missing_gross_observation_cells"],
        reporting_units=len(registry), unique_source_unit_hours=epa_summary["unique_source_unit_hours"] + nj_summary["selected_source_unit_hours"],
        NJ_native_extension=nj_summary,
        source_region_scope="NY_state_plus_corroborated_NYISO_native_NJ_reporting_groups_before_P63_normalization")
    fossil_ok = source_q["Combined Fossil"] & (remaining <= 1e-9)
    fossil, fossil_ok, factors, thermal_map, gross_error = thermal_prior(fleet, physical, registry, weights, repaired_zones,
        totals["Combined Fossil"], fossil_ok, local.month.to_numpy())
    other, nuclear_cap, other_map = nonfossil_prior(fleet, physical, local, totals, source_q)
    prior = fossil.copy()
    thermal_rows = fleet.fuel_category.eq("Combined Fossil").to_numpy()
    prior[:, ~thermal_rows] = other[:, ~thermal_rows]
    generation_ok = fossil_ok & np.logical_and.reduce([source_q[f] for f in FUELS[1:]])
    conservation = []
    for f in FUELS:
        cols = fleet.fuel_category.eq(f).to_numpy()
        total = prior[:, cols].sum(axis=1)
        ok = fossil_ok if f == "Combined Fossil" else source_q[f]
        error = np.abs(total[ok] - totals[f][ok])
        require(error.max(initial=0) < 1e-6, f"Fleet {f} priors do not conserve source total")
        conservation.append({"fuel_category": f, "qualified_hours": int(ok.sum()), "maximum_absolute_source_total_error_mw": float(error.max(initial=0))})
    south = pd.read_csv(SOURCE / "south_fork_hourly_prior.csv")
    sf = fleet.plant_id.eq(65561).to_numpy()
    sf_ok = boolean(south.allocation_qualified)
    sf_error = float(np.max(np.abs(prior[sf_ok][:, sf].sum(axis=1) - south.loc[sf_ok, "estimated_actual_mw"].to_numpy(float)), initial=0))
    require(sf_error < 1e-6, "South Fork profile added or lost instead of mapped as one subset")
    prior[~generation_ok] = np.nan
    available = resource_bounds(fleet, physical, default, prior, nuclear_cap, generation_ok)
    minimum = np.zeros_like(available); minimum[~generation_ok] = np.nan
    joint = generation_ok & boundary_ok
    write_csv(thermal_map, output / "epa_to_fleet_allocation.csv")
    write_csv(other_map, output / "nonfossil_to_fleet_allocation.csv")
    write_csv(pd.DataFrame(conservation), output / "fuel_conservation.csv")
    repaired, repaired_ok, _ = normalize_weights(zone_weights, totals["Combined Fossil"], fossil_ok)
    repair_rows = []
    for j, z in enumerate(ZONES):
        f = hours[["hour_index", "timestamp_utc"]].copy(); f["zone"] = z
        f["repaired_fossil_prior_actual_mw"] = repaired[:, j]; f["qualified"] = repaired_ok
        f["eligible_reported_gross_weight_mw"] = zone_weights[:, j]
        repair_rows.append(f)
    write_csv(pd.concat(repair_rows).sort_values(["hour_index", "zone"]), output / "repaired_fossil_zonal_priors.csv.gz")
    scope_off = ~boolean(fleet.grid_scope_eligible)
    sector_off = ~boolean(fleet.sector_synchronization_scope_eligible)
    reported_other_ba = boolean(fleet.reported_other_balancing_authority)
    hourly = hours[["hour_index", "timestamp_utc"]].copy()
    hourly["generation_hour_qualified"] = generation_ok; hourly["boundary_hour_qualified"] = boundary_ok
    hourly["source_hour_qualified"] = joint; hourly["fossil_gross_to_net_allocation_factor"] = factors
    hourly["preferred_generation_actual_mw"] = prior.sum(axis=1)
    hourly["available_generation_actual_mw"] = available.sum(axis=1)
    hourly["preferred_on_grid_scope_excluded_rows_actual_mw"] = prior[:, scope_off].sum(axis=1)
    hourly["preferred_on_sector_sync_excluded_rows_actual_mw"] = prior[:, sector_off].sum(axis=1)
    hourly["preferred_on_reported_other_BA_rows_actual_mw"] = prior[:, reported_other_ba].sum(axis=1)
    hourly["preferred_above_available_bounds_actual_mw"] = np.maximum(prior - available, 0).sum(axis=1)
    write_csv(hourly, output / "hourly_prior_quality.csv")
    selected = np.any(np.nan_to_num(available) > 0, axis=0)
    fuel_conflicts = []
    for fuel in FUELS:
        mask = fleet.fuel_category.eq(fuel).to_numpy()
        f = hours[["hour_index", "timestamp_utc"]].copy(); f["fuel_category"] = fuel
        f["source_prior_actual_mw"] = prior[:, mask].sum(axis=1)
        f["prior_on_selected_fleet_actual_mw"] = prior[:, mask & selected].sum(axis=1)
        f["prior_on_excluded_fleet_actual_mw"] = prior[:, mask & ~selected].sum(axis=1)
        f["prior_on_grid_scope_excluded_rows_actual_mw"] = prior[:, mask & scope_off].sum(axis=1)
        f["prior_on_sector_sync_excluded_rows_actual_mw"] = prior[:, mask & sector_off].sum(axis=1)
        f["prior_on_reported_other_BA_rows_actual_mw"] = prior[:, mask & reported_other_ba].sum(axis=1)
        f["preferred_above_available_bound_actual_mw"] = np.maximum(prior[:, mask] - available[:, mask], 0).sum(axis=1)
        f["generation_hour_qualified"] = generation_ok
        # Empty excluded subsets sum to zero even on a missing hour; keep the
        # common missing-data contract explicit across all numerical columns.
        for column in [c for c in f if c.endswith("_mw")]:
            f.loc[~generation_ok, column] = np.nan
        fuel_conflicts.append(f)
    write_csv(pd.concat(fuel_conflicts).sort_values(["hour_index", "fuel_category"]), output / "fuel_hourly_scope_conflicts.csv.gz")
    prior_by_fuel = np.column_stack([prior[:, fleet.fuel_category.eq(f)].sum(axis=1) for f in FUELS])
    revision = None
    if previous_priors is not None:
        with np.load(previous_priors, allow_pickle=False) as old:
            require(np.array_equal(old["fleet_id"], fleet.fleet_id) and np.array_equal(old["hour_index"], np.arange(1, 8761)),
                    "Scope comparison changed fleet/hour identity")
            old_prior, old_available = old["prior_actual_mw"], old["available_pmax_actual_mw"]
            require(np.array_equal(old_prior, prior, equal_nan=True), "Balancing-area scope change altered source-preferred MW")
            require(np.array_equal(old["physical_pmax_actual_mw"], physical), "Scope change altered physical capability reference")
            require(np.array_equal(old["generation_hour_qualified"], generation_ok) and np.array_equal(old["source_hour_qualified"], joint),
                    "Scope change altered source qualification")
            old_selected = np.any(np.nan_to_num(old_available) > 0, axis=0)
            removed = old_selected & ~selected
            require(np.all(reported_other_ba[removed]), "New exclusion is not supported by the reported other-BA flag")
            difference = old_available[generation_ok] - available[generation_ok]
            require(np.min(difference, initial=0) >= -1e-8, "Balancing-area exclusion unexpectedly increased available capability")
            removed_preference = prior[generation_ok][:, removed].sum(axis=1)
            removed_capacity = difference.sum(axis=1)
            revision = {"previous_prior_path": str(previous_priors.relative_to(ROOT)).replace("\\", "/"),
                "previous_prior_sha256": previous_fingerprint,
                "previous_artifact_role": "local_intermediate_history_only_not_a_delivered_or_rebuild_dependency",
                "change": "exclude reported non-NYIS balancing-authority rows from default NY-native bounds; retain source preference",
                "fleet_and_hour_identities_unchanged": True, "source_preferred_MW_unchanged": True,
                "physical_capability_reference_unchanged": True, "qualification_masks_unchanged": True,
                "previous_ever_available_fleet_rows": int(old_selected.sum()), "current_ever_available_fleet_rows": int(selected.sum()),
                "newly_excluded_fleet_rows": int(removed.sum()), "newly_excluded_fleet_ids": fleet.loc[removed, "fleet_id"].astype(int).tolist(),
                "newly_excluded_preferred_mean_actual_mw": float(removed_preference.mean()),
                "newly_excluded_preferred_max_actual_mw": float(removed_preference.max()),
                "newly_excluded_preferred_energy_over_8750_qualified_hours_mwh": float(removed_preference.sum()),
                "removed_available_capacity_mean_actual_mw": float(removed_capacity.mean()),
                "removed_available_capacity_max_actual_mw": float(removed_capacity.max()),
                "classification_limitation": "EIA reported balancing authority controls this scope rule; per-unit classification is not independently verified"}
            changed = fleet.loc[removed, ["fleet_id", "device_key", "plant_name", "fuel_category", "balancing_authority_code"]].copy()
            changed["preferred_mean_actual_mw"] = prior[generation_ok][:, removed].mean(axis=0)
            changed["preferred_energy_over_qualified_hours_mwh"] = prior[generation_ok][:, removed].sum(axis=0)
            changed["previous_max_available_actual_mw"] = np.nanmax(old_available[:, removed], axis=0)
            changed["current_max_available_actual_mw"] = np.nanmax(available[:, removed], axis=0)
            write_csv(changed, output / "balancing_area_scope_changes.csv")
            (output / "scope_revision.json").write_text(json.dumps(revision, indent=2) + "\n", encoding="utf-8", newline="\n")
            require(sha(previous_priors) == previous_fingerprint, "Local history changed during comparison")
    for p in paths:
        require(sha(p) == fingerprints[str(p)], f"Input changed during prior build: {p}")
    np.savez_compressed(output / "dispatch_priors.npz", hour_index=np.arange(1, 8761), timestamp_utc=hours.timestamp_utc.to_numpy(dtype=str),
        fleet_id=fleet.fleet_id.to_numpy(int), prior_actual_mw=prior, available_pmax_actual_mw=available,
        available_pmin_actual_mw=minimum, physical_pmax_actual_mw=physical,
        generation_hour_qualified=generation_ok, source_hour_qualified=joint, boundary_hour_qualified=boundary_ok,
        fuel_category=fleet.fuel_category.to_numpy(dtype=str), fuel_names=np.asarray(FUELS), fuel_prior_actual_mw=prior_by_fuel)
    summary = {"status": "source_preserving_soft_fleet_priors_not_dispatch", "hours": 8760, "native_fleet_rows": len(fleet),
        "generation_qualified_hours": int(generation_ok.sum()), "joint_boundary_generation_qualified_hours": int(joint.sum()),
        "source_missing_generation_hours": int((~generation_ok).sum()), "scale": "actual MW; root applies gamma once", "gamma_applied": False,
        "EPA": epa_summary, "maximum_EPA_assignment_conservation_error_mw": float(gross_error),
        "South_Fork_source_profile_maximum_error_mw": sf_error,
        "preferred_generation_on_scope_excluded_rows_mean_mw": float(np.nanmean(hourly.preferred_on_grid_scope_excluded_rows_actual_mw)),
        "preferred_generation_on_sector_sync_excluded_rows_mean_mw": float(np.nanmean(hourly.preferred_on_sector_sync_excluded_rows_actual_mw)),
        "preferred_generation_on_reported_other_BA_rows_mean_mw": float(np.nanmean(hourly.preferred_on_reported_other_BA_rows_actual_mw)),
        "ever_available_fleet_rows": int(selected.sum()),
        "balancing_area_scope_revision": revision,
        "preferred_above_available_bounds_mean_mw": float(np.nanmean(hourly.preferred_above_available_bounds_actual_mw)),
        "thermal_mapping_method_counts": thermal_map.mapping_method.value_counts().to_dict(),
        "generation_observed_at_unit_net_level": False, "interface_targets_used": False, "dispatch_performed": False,
        "policies": {"fossil": "unique reporting-unit gross weights allocated once through paired crosswalk or explicitly labelled plant-capacity partition, then normalized to P63 combined fossil",
            "NJ_native_extension": "Bayonne56964 ten one-to-one EPA/EIA associations; Linden50006 five admitted reporting groups pooled once over eight EIA generators; GTG6 EPA004001 excluded; no addition to statewide P63 total or VFT transmission schedule",
            "Cricket_Valley": "three EPA train records apportioned over six unique EIA units at plant level; no same-string unit identity assumption",
            "nonfossil": "frozen NRC reactor and hydro plant estimates; original active-capacity/daylight renewable shares; South Fork subset once",
            "scope_conflicts": "source-preferred MW retained on exact frozen nonfossil identities even if new fleet bounds exclude them; conflict quantified, not silently reallocated",
            "bounds": "eligible wind/solar at min(physical capacity, source availability); eligible PS at min(physical capacity, frozen PS prior); batteries off; nuclear at min(capacity,NRC availability)",
            "missing": "all preferred/available rows NaN when generation sources unqualified; joint mask additionally excludes incomplete P32 boundaries"},
        "limitations": ["Preferred unit MW are estimates, not observed net dispatch and need not satisfy bounds",
            "Within-plant splits and grid-scope proxies are explicit assumptions", "Nuclear daily availability is not hourly telemetry",
            "Hydro/pumped-storage pumping, reservoir energy and SOC are not validated", "No ramps, commitment, network feasibility, or interface calibration is performed"],
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__}}
    (output / "prior_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    write_csv(pd.DataFrame([{"path": str(p.relative_to(ROOT)).replace("\\", "/"), "sha256": fingerprints[str(p)]} for p in paths]), output / "source_manifest.csv")
    products = sorted([p for p in output.iterdir() if p.is_file() and p.name != "output_manifest.csv"]
                      + [p for p in (output / "source_metadata").rglob("*") if p.is_file()])
    write_csv(pd.DataFrame([{"path": str(p.relative_to(ROOT)).replace("\\", "/"), "bytes": p.stat().st_size, "sha256": sha(p)} for p in products]), output / "output_manifest.csv")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--fleet-folder", type=Path, default=FLEET)
    parser.add_argument("--previous-priors", type=Path, help="Optional local historical NPZ for a scope-change receipt; not needed for clean reproduction")
    args = parser.parse_args()
    build(args.output, args.fleet_folder, args.previous_priors)
