"""Extract independently observed EPA gross generation for the compact NY snapshots.

No NYISO internal-interface observations are read.  All EPA unit-hour rows remain
unique by (facility ID, unit ID, date, hour); crosswalk one-to-many relationships
annotate an observation and NEVER duplicate its MW.  This is gross combustion-
unit output, not net grid injection or observed zonal generation.

Run with the bundled Python runtime.  --download obtains the pinned public EPA
bulk files into ignored tmp; ordinary runs use that cache.  --replay verifies and
reuses the small committed source extracts without downloading annual files.
"""
from __future__ import annotations

import argparse
import base64
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "tmp/epa_generation_raw"
OUTPUT = ROOT / "output/compact_ny_2025/generation_sources/epa"
EST = dt.timezone(dt.timedelta(hours=-5), "EST")
BULK = "https://api.epa.gov/easey/bulk-files/"
NYGRID_COMMIT = "47698b6c7823ae7b1bc6935e5601d5b64b8f918e"
DB_COMMIT = "3da401e329303638f1fac7e4d8754ec33779c2af"
SPECS = {
    "emissions-hourly-2019-ny.csv": (BULK + "emissions/hourly/state/emissions-hourly-2019-ny.csv", "e58710fec124f42d829ac340fe319562da3aa7aaea8345f5b595d2e1b42a0221", 485630847, "2025-10-02"),
    "emissions-hourly-2025-ny.csv": (BULK + "emissions/hourly/state/emissions-hourly-2025-ny.csv", "a2d0cfba9466fc2347fec867fafd9bba8c39d5a1b821664e5e792901e6148f6a", 442207147, "2026-08-29"),
    "emissions-daily-2025-ny.csv": (BULK + "emissions/daily/state/emissions-daily-2025-ny.csv", "0f74bcbfc13e3cacec751f3a61b844934dbaddc1f5ee341a4204d280f389bd1e", 16387133, "retrieved_2026-09-08"),
    "thermalGenMatched_2019.xlsx": (f"https://raw.githubusercontent.com/AndersonEnergyLab-Cornell/NYgrid/{NYGRID_COMMIT}/Data/thermalGenMatched_2019.xlsx", "dbf3542eea2250305ec3139a6d125e96dc4f6c67923fb87c027123812363296f", 39496, "2019_mapping_published_2022"),
    "epa_eia_crosswalk.csv": ("https://raw.githubusercontent.com/USEPA/camd-eia-crosswalk/master/epa_eia_crosswalk.csv", "acea4d8dbbfd133c1a4ec67f2831cbcbb0d48c13da72d0f47bea35c5618923ad", 2298091, "2018_EIA_basis_v0.3_2022_release"),
    "facility-2019.csv": (BULK + "facility/facility-2019.csv", "d6b074ba7e5173d4c3318b8178b85b055885b11c1c186c15180dc8af698d375d", 1717839, "retrieved_2026-09-08"),
    "facility-2025.csv": (BULK + "facility/facility-2025.csv", "d7b743273c8919b5af8a6fef45f813dd17f9dfada8c3330e508f342383a1690d", 1556685, "2026-09-06"),
}


def sha256(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def write_csv(path, rows, fields=None):
    rows = list(rows)
    fields = fields or list(dict.fromkeys(k for row in rows for k in row))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def source_file(cache, name, download=False):
    url, expected, size, _ = SPECS[name]
    path = cache / name
    if not path.exists():
        if not download:
            raise FileNotFoundError(f"Missing {path}; use --download or --replay")
        cache.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".partial")
        # The public bulk download endpoint uses no key.  Sending CAMPD's client
        # API key to this endpoint fails; no credentials are read or persisted.
        with urllib.request.urlopen(url, timeout=90) as response, tmp.open("wb") as f:
            shutil.copyfileobj(response, f, length=2**20)
        tmp.replace(path)
    if path.stat().st_size != size or sha256(path) != expected:
        raise ValueError(f"Source bytes changed: {name}; review a new release explicitly")
    return path


def source_scenarios(catalog, protocol):
    # Read only the explicitly allowed date/scale fields.  The source catalog
    # contains no internal-interface flow observations.
    fields = ["scenario_id", "vintage", "timestamp", "timestamp_utc", "source_time_zone", "scale_factor_gamma"]
    rows = [{k: row[k] for k in fields} for row in read_csv(catalog)]
    gamma = {r["vintage"]: r["scale_factor_gamma"] for r in rows}
    with Path(protocol).open(encoding="utf-8-sig") as f:
        new = json.load(f)["new_calendar_selected_2025_validation_hours"]
    for row in new:
        rows.append(dict(row, vintage="2025", scale_factor_gamma=gamma["2025"]))
    seen = set()
    for row in rows:
        if row["scenario_id"] in seen:
            raise ValueError("Duplicate scenario identity")
        seen.add(row["scenario_id"])
        utc = dt.datetime.fromisoformat(row["timestamp_utc"].replace("Z", "+00:00"))
        if utc.utcoffset() != dt.timedelta(0) or utc.minute or utc.second:
            raise ValueError("Snapshots must start on an exact UTC hour")
        offset = {"EST": -5, "EDT": -4}[row["source_time_zone"]]
        local = utc.astimezone(dt.timezone(dt.timedelta(hours=offset)))
        if local.strftime("%Y-%m-%d %H:%M") != row["timestamp"]:
            raise ValueError("Requested local and UTC timestamps disagree")
        if str(local.year) != str(row["vintage"]):
            raise ValueError("Scenario vintage disagrees with timestamp")
        standard = utc.astimezone(EST)
        row.update(
            timestamp_local_requested=row.pop("timestamp"),
            timestamp_utc_requested=row.pop("timestamp_utc"),
            interval_start_utc=utc.isoformat().replace("+00:00", "Z"),
            interval_end_utc=(utc + dt.timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            epa_date=standard.strftime("%Y-%m-%d"), epa_hour=str(standard.hour),
            epa_timestamp_lst=standard.strftime("%Y-%m-%d %H:%M"),
            time_alignment_policy="NYISO_hour_beginning_UTC_matched_to_EPA_fixed_EST_hour_0_to_23",
        )
    return rows


def iter_source_records(path):
    """Yield parsed records and exact record bytes, including multiline fields."""
    with Path(path).open("rb") as f:
        header = next(f)
        fields = next(csv.reader([header.decode("utf-8-sig")]))
        pending = []
        def lines():
            for raw in f:
                pending.append(raw)
                yield raw.decode("utf-8")
        reader = csv.reader(lines())
        for ordinal, values in enumerate(reader, 2):
            raw = b"".join(pending)
            pending.clear()
            if len(values) != len(fields):
                raise ValueError(f"Malformed source CSV record {ordinal}")
            yield ordinal, dict(zip(fields, values)), raw


def select_records(path, scenarios):
    target = {(s["epa_date"], s["epa_hour"]) for s in scenarios}
    selected, audit, units, seen = [], [], set(), set()
    for ordinal, row, raw in iter_source_records(path):
        if row["State"] != "NY":
            raise ValueError("Non-NY row in NY bulk source")
        unit = (row["Facility ID"], row["Unit ID"])
        units.add(unit)
        key = (row["Date"], row["Hour"])
        # Preserve a full unit-day with partial operation, independently checked
        # against EPA's daily MWh.  This is a source-units check, not a fit.
        evidence = row["Date"] == "2025-07-29" and unit == ("2480", "3")
        if key in target or evidence:
            identity = unit + key
            if identity in seen:
                raise ValueError(f"Duplicate EPA unit-hour: {identity}")
            seen.add(identity)
            record = dict(row, source_row_number=ordinal,
                          source_record_sha256=hashlib.sha256(raw).hexdigest(),
                          source_record_base64=base64.b64encode(raw).decode("ascii"))
            if key in target:
                selected.append(record)
            if evidence:
                audit.append(record)
    return selected, audit, len(units)


def number(value):
    if value is None or value == "":
        return None
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Nonfinite observed quantity")
    return value


def convert_gross(row):
    gross, op = number(row["Gross Load (MW)"]), number(row["Operating Time"])
    if op is not None and not 0 <= op <= 1:
        raise ValueError("Operating time must be a fraction of one clock hour")
    if gross is not None and gross < 0:
        raise ValueError("Negative gross electrical output requires explicit review")
    # Do not convert an absent source measurement into zero, even if op_time=0.
    # A downstream coverage/reconciliation rule may separately recognize offline
    # status, but it must not relabel that inference an observed gross value.
    energy = None if gross is None or op is None else gross * op
    status = ("reported_gross_rate_and_operating_time" if energy is not None else
              "reported_offline_gross_blank" if op == 0 else "gross_or_operating_time_missing")
    return gross, op, energy, status


def workbook_crosswalk(path):
    import openpyxl  # needed for initial raw-source rebuild only
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    values = iter(wb["Sheet1"].values)
    next(values)
    out = []
    def identifier(x):
        if x is None:
            return ""
        return str(int(x)) if isinstance(x, (float, int)) and int(x) == x else str(x).strip()
    for n, row in enumerate(values, 2):
        if row[4] is None:
            continue
        out.append(dict(source_excel_row=n, facility_id=identifier(row[4]), unit_id=identifier(row[5]),
                        nyiso_name=row[0] or "", nyiso_ptid=identifier(row[1]), zone=row[2] or "",
                        epa_facility_name=row[3] or "", source_id="NYGRID:2019:thermalGenMatched",
                        source_sha256=SPECS["thermalGenMatched_2019.xlsx"][1]))
    wb.close()
    return out


def mapping_indices(nygrid_rows, eia_rows):
    exact, facility, eia = (collections.defaultdict(list) for _ in range(3))
    for row in nygrid_rows:
        if row["zone"] not in list("ABCDEFGHIJK"):
            continue
        exact[(row["facility_id"], row["unit_id"])].append(row)
        facility[row["facility_id"]].append(row)
    for row in eia_rows:
        eia[(row["CAMD_PLANT_ID"], row["CAMD_UNIT_ID"])].append(row)
    for rows in exact.values():
        if len({r["zone"] for r in rows}) > 1:
            raise ValueError("One EPA unit maps to contradictory NYgrid zones")
    return exact, facility, eia


def map_unit(facility_id, unit_id, indices, manual_rows=()):
    exact, facility, eia = indices
    rows = exact.get((facility_id, unit_id), [])
    zones = {r["zone"] for r in rows}
    role = "nygrid_2019_exact_facility_unit_crosswalk"
    if not rows:
        rows = facility.get(facility_id, [])
        zones = {r["zone"] for r in rows}
        role = "assumed_same_facility_zone_from_2019_ORIS_identity"
    manual = [r for r in manual_rows if r["facility_id"] == facility_id]
    if len({r["zone"] for r in manual}) > 1:
        raise ValueError("Conflicting explicit facility-zone evidence")
    if len(zones) != 1:
        if manual:
            zones = {manual[0]["zone"]}
            role = "declared_facility_identity_geography_zone_inference"
        else:
            zones = set()
            role = "unmatched_zone_explicitly_retained"
    cross = eia.get((facility_id, unit_id), [])
    # EPA warns that boiler/generator crosswalks are many-to-many.  Store sets
    # as identity annotations instead of expanding observation rows.
    return dict(
        zone=next(iter(zones), ""), zone_mapping_kind=role,
        nygrid_crosswalk_rows="|".join(str(r["source_excel_row"]) for r in rows),
        nyiso_ptids="|".join(sorted({r["nyiso_ptid"] for r in rows if r["nyiso_ptid"]})),
        eia_plant_ids="|".join(sorted({r["EIA_PLANT_ID"] for r in cross if r["EIA_PLANT_ID"]})),
        eia_generator_ids="|".join(sorted({r["EIA_GENERATOR_ID"] for r in cross if r["EIA_GENERATOR_ID"]})),
        epa_eia_crosswalk_rows="|".join(r["SEQUENCE_NUMBER"] for r in cross),
        epa_eia_crosswalk_vintage="2018_EIA_basis_2022_release_not_a_2025_fleet_census",
        zone_mapping_source=(manual[0].get("source_id", "") if manual and role.startswith("declared") else "NYGRID:2019:thermalGenMatched" if zones else ""),
        current_zonal_observation=False, identity_continuity_assumed=True,
    )


def normalize(selected, scenarios, indices, manual_rows=(), facility_rows=()):
    by_hour = collections.defaultdict(list)
    facility_index = {(r["Year"], r["Facility ID"], r["Unit ID"]): r for r in facility_rows}
    if len(facility_index) != len(facility_rows):
        raise ValueError("Duplicate vintage/facility/unit attributes")
    for row in selected:
        by_hour[(row["Date"], row["Hour"])].append(row)
    out = []
    for scenario in scenarios:
        rows = by_hour[(scenario["epa_date"], scenario["epa_hour"])]
        if not rows:
            raise ValueError(f"No exact EPA rows for {scenario['scenario_id']}")
        seen = set()
        for row in rows:
            fid, uid = row["Facility ID"], row["Unit ID"]
            if (fid, uid) in seen:
                raise ValueError("Crosswalk cannot duplicate an EPA unit-hour")
            seen.add((fid, uid))
            gross, op, energy, status = convert_gross(row)
            attr = facility_index.get((scenario["vintage"], fid, uid), {})
            # The institutional/CHP Riverbay site lacks evidence that its gross
            # production is included in NYISO's grid fuel mix. Preserve it in
            # reported gross totals, but exclude it from the grid share prior.
            mapping = map_unit(fid, uid, indices, manual_rows)
            eligible = fid != "52168" and attr.get("Source Category") in ("Electric Utility", "Cogeneration")
            out.append(dict(scenario, facility_id=fid, unit_id=uid,
                            device_key=f"EPA:ORIS:{fid}:UNIT:{uid}",
                            facility_name=row["Facility Name"], primary_fuel=row["Primary Fuel Type"],
                            secondary_fuel=row["Secondary Fuel Type"], reconciliation_fuel_category="Combined Fossil",
                            epa_source_category=attr.get("Source Category", ""),
                            epa_county=attr.get("County", ""), epa_latitude=attr.get("Latitude", ""),
                            epa_longitude=attr.get("Longitude", ""),
                            epa_associated_generators_nameplate=attr.get("Associated Generators & Nameplate Capacity (MWe)", ""),
                            epa_facility_attribute_source_id=f"EPA:CAMPD:facility:{scenario['vintage']}",
                            grid_fossil_share_eligible=eligible,
                            grid_fossil_share_policy=("excluded_Riverbay_CHP_grid_delivery_unverified" if fid == "52168" else
                                                     "Electric_Utility_or_Cogeneration_source_category_gross_share_proxy" if eligible else
                                                     "excluded_grid_connection_or_facility_category_unverified"),
                            unit_type=row["Unit Type"], associated_stacks=row["Associated Stacks"],
                            program_codes=row["Program Code"], source_gross_load_mw=gross,
                            operating_time_hours=op, gross_generation_mwh=energy,
                            gross_clock_hour_average_mw=energy,
                            gross_quantity_status=status, net_generation_mw=None,
                            steam_load_1000_lb_per_hr=number(row["Steam Load (1000 lb/hr)"]),
                            gross_conversion_policy="hourly_gross_rate_times_operating_time_once_daily_bulk_verified",
                            source_id=f"EPA:CAMPD:hourly:{scenario['vintage']}:NY",
                            source_file_sha256=SPECS[f"emissions-hourly-{scenario['vintage']}-ny.csv"][1],
                            source_row_number=row["source_row_number"], source_record_sha256=row["source_record_sha256"],
                            **mapping))
    return out


def verify_extract(rows):
    for row in rows:
        raw = base64.b64decode(row["source_record_base64"], validate=True)
        if hashlib.sha256(raw).hexdigest() != row["source_record_sha256"]:
            raise ValueError("Extract source record bytes changed")
        values = next(csv.reader(io.StringIO(raw.decode("utf-8"))))
        original = [v for k, v in row.items() if not k.startswith("source_")]
        if values != original:
            raise ValueError("Extract columns disagree with original source record")


def coverage(rows, scenarios, annual_counts):
    out = []
    for s in scenarios:
        part = [r for r in rows if r["scenario_id"] == s["scenario_id"]]
        known = [r for r in part if r["gross_generation_mwh"] is not None]
        gross = sum(r["gross_generation_mwh"] for r in known)
        mapped = sum(r["gross_generation_mwh"] for r in known if r["zone"])
        out.append(dict(scenario_id=s["scenario_id"], vintage=s["vintage"],
                        timestamp_utc_requested=s["timestamp_utc_requested"],
                        epa_source_unit_rows=len(part), annual_reporting_unit_count=annual_counts[str(s["vintage"])],
                        gross_value_present_rows=len(known), gross_blank_rows=len(part)-len(known),
                        reported_offline_gross_blank_rows=sum(r["gross_quantity_status"] == "reported_offline_gross_blank" for r in part),
                        gross_source_total_mwh=gross, gross_zone_mapped_mwh=mapped,
                        gross_zone_unmatched_mwh=gross-mapped,
                        mapped_share_of_present_gross=mapped/gross if gross else None,
                        complete_NYISO_generation_coverage=False, observed_net_generation=False))
    return out


def zonal_gross(rows, scenarios):
    out = []
    for s in scenarios:
        part = [r for r in rows if r["scenario_id"] == s["scenario_id"]]
        for zone in list("ABCDEFGHIJK") + ["UNMAPPED"]:
            zone_rows = [r for r in part if (r["zone"] or "UNMAPPED") == zone]
            reported = [r for r in zone_rows if r["gross_generation_mwh"] is not None]
            eligible = [r for r in reported if r["grid_fossil_share_eligible"]]
            out.append(dict(scenario_id=s["scenario_id"], vintage=s["vintage"], zone=zone,
                            interval_start_utc=s["interval_start_utc"], interval_end_utc=s["interval_end_utc"],
                            fuel_category="Combined Fossil",
                            grid_eligible_gross_clock_hour_mw=sum(r["gross_generation_mwh"] for r in eligible),
                            all_reported_gross_clock_hour_mw=sum(r["gross_generation_mwh"] for r in reported),
                            source_unit_rows=len(zone_rows), gross_present_rows=len(reported),
                            gross_missing_rows=len(zone_rows)-len(reported), grid_eligible_present_rows=len(eligible),
                            zonal_generation_observed=False, net_generation_observed=False,
                            geographic_mapping_and_gross_share_proxy=True))
    return out


def quantity_audit(hourly, daily):
    h = [r for r in hourly if r["Facility ID"] == "2480" and r["Unit ID"] == "3" and r["Date"] == "2025-07-29"]
    d = [r for r in daily if r["Facility ID"] == "2480" and r["Unit ID"] == "3" and r["Date"] == "2025-07-29"]
    if len(h) != 24 or len(d) != 1:
        raise ValueError("Quantity audit requires all 24 unit-hour records and one daily record")
    weighted = sum(convert_gross(r)[2] or 0 for r in h)
    unweighted = sum(number(r["Gross Load (MW)"]) or 0 for r in h)
    truth = float(d[0]["Gross Load (MWh)"])
    if abs(weighted-truth) > 1e-7 or abs(unweighted-truth) < 1:
        raise ValueError("Current EPA bulk does not support the registered rate conversion")
    return [dict(facility_id="2480", unit_id="3", date="2025-07-29", hourly_records=24,
                 source_hourly_gross_sum=unweighted, weighted_clock_hour_energy_mwh=weighted,
                 official_daily_gross_energy_mwh=truth, absolute_error_mwh=abs(weighted-truth),
                 unweighted_error_mwh=abs(unweighted-truth), passed=True)]


def build(cache=CACHE, output=OUTPUT, download=False, replay=False):
    cache, output = Path(cache), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    catalog = ROOT / "output/compact_ny_2025/electrical_fixed_peak/source_snapshots.csv"
    protocol = ROOT / "output/compact_ny_2025/generation_sources/generation_reconstruction_protocol.json"
    scenarios = source_scenarios(catalog, protocol)
    if replay:
        with (output / "epa_source_manifest.json").open() as f:
            manifest = json.load(f)
        if sha256(catalog) != manifest["scenario_catalog_sha256"] or sha256(protocol) != manifest["preregistration_protocol_sha256"]:
            raise ValueError("Scenario catalog or preregistration changed; rebuild explicitly")
        for item in manifest["extracts"]:
            if sha256(output / item["filename"]) != item["sha256"]:
                raise ValueError(f"Pinned extract changed: {item['filename']}")
        selected = []
        for year in [2019, 2025]:
            part = read_csv(output / f"selected_epa_source_rows_{year}.csv")
            verify_extract(part)
            selected.extend(part)
        ng = read_csv(output / "nygrid_2019_identity_crosswalk.csv")
        eia = read_csv(output / "epa_eia_crosswalk_ny.csv")
        facilities = read_csv(output / "epa_facility_attributes_ny.csv")
        audit_hourly = read_csv(output / "quantity_audit_hourly_source.csv")
        audit_daily = read_csv(output / "quantity_audit_daily_source.csv")
        verify_extract(audit_hourly)
        verify_extract(audit_daily)
        counts = manifest["annual_reporting_unit_counts"]
    else:
        selected, audit_hourly, counts = [], [], {}
        for year in [2019, 2025]:
            path = source_file(cache, f"emissions-hourly-{year}-ny.csv", download)
            part, audit, count = select_records(path, [s for s in scenarios if s["vintage"] == str(year)])
            selected.extend(part)
            audit_hourly.extend(audit)
            counts[str(year)] = count
            write_csv(output / f"selected_epa_source_rows_{year}.csv", part)
        ng = workbook_crosswalk(source_file(cache, "thermalGenMatched_2019.xlsx", download))
        eia = [r for r in read_csv(source_file(cache, "epa_eia_crosswalk.csv", download)) if r["CAMD_STATE"] == "NY"]
        facilities = [r for y in [2019, 2025]
                      for r in read_csv(source_file(cache, f"facility-{y}.csv", download)) if r["State"] == "NY"]
        audit_daily = []
        for ordinal, row, raw in iter_source_records(source_file(cache, "emissions-daily-2025-ny.csv", download)):
            if row["Date"] == "2025-07-29" and (row["Facility ID"], row["Unit ID"]) == ("2480", "3"):
                audit_daily.append(dict(row, source_row_number=ordinal,
                                        source_record_sha256=hashlib.sha256(raw).hexdigest(),
                                        source_record_base64=base64.b64encode(raw).decode("ascii")))
        write_csv(output / "nygrid_2019_identity_crosswalk.csv", ng)
        write_csv(output / "epa_eia_crosswalk_ny.csv", eia)
        write_csv(output / "epa_facility_attributes_ny.csv", facilities)
        write_csv(output / "quantity_audit_hourly_source.csv", audit_hourly)
        write_csv(output / "quantity_audit_daily_source.csv", audit_daily)
    manual_path = output / "declared_facility_zone_evidence.csv"
    manual = read_csv(manual_path) if manual_path.exists() else []
    rows = normalize(selected, scenarios, mapping_indices(ng, eia), manual, facilities)
    audits = quantity_audit(audit_hourly, audit_daily)
    write_csv(output / "epa_generation_hourly.csv", rows)
    write_csv(output / "epa_snapshot_coverage.csv", coverage(rows, scenarios, counts))
    write_csv(output / "epa_selected_scenarios.csv", scenarios)
    write_csv(output / "epa_quantity_conversion_audit.csv", audits)
    write_csv(output / "epa_zonal_gross_generation.csv", zonal_gross(rows, scenarios))
    identities = {}
    for r in rows:
        key = (r["vintage"], r["device_key"])
        identities[key] = {k: r[k] for k in ["vintage", "device_key", "facility_id", "unit_id", "facility_name", "zone", "zone_mapping_kind", "nygrid_crosswalk_rows", "nyiso_ptids", "epa_eia_crosswalk_rows", "eia_plant_ids", "eia_generator_ids", "epa_eia_crosswalk_vintage", "zone_mapping_source", "identity_continuity_assumed"]}
    write_csv(output / "epa_unit_identity_register.csv", identities.values())
    write_csv(output / "epa_unmatched_generation.csv", [r for r in rows if not r["zone"]], list(rows[0]))
    extract_names = [f"selected_epa_source_rows_{y}.csv" for y in [2019, 2025]] + [
        "nygrid_2019_identity_crosswalk.csv", "epa_eia_crosswalk_ny.csv", "epa_facility_attributes_ny.csv",
        "quantity_audit_hourly_source.csv", "quantity_audit_daily_source.csv"]
    if manual_path.exists():
        extract_names.append(manual_path.name)
    manifest = dict(schema_version="compact_epa_generation_inputs_v1", source_accessed_utc="2026-09-08",
                    annual_reporting_unit_counts=counts,
                    source_files=[dict(filename=name, url=v[0], sha256=v[1], bytes=v[2], source_release=v[3]) for name, v in SPECS.items()],
                    extracts=[dict(filename=n, sha256=sha256(output/n), bytes=(output/n).stat().st_size) for n in extract_names],
                    scenario_catalog_sha256=sha256(catalog), preregistration_protocol_sha256=sha256(protocol),
                    code_sha256=sha256(Path(__file__)),
                    internal_interface_observations_read=False, unit_row_expansion=False,
                    source_gross_is_net=False, zonal_mapping_is_observed=False,
                    missing_gross_values_imputed_zero=False,
                    notes="Public EPA Part75 subset; 2019 crosswalk identity continuity is an assumption; 2022 EPA-EIA crosswalk is not a 2025 census. No NYISO internal-interface values used.")
    with (output / "epa_source_manifest.json").open("w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print(json.dumps(dict(scenarios=len(scenarios), selected_unit_hours=len(rows),
                          quantity_audit_passed=True, output=str(output))))
    return rows, manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    build(args.cache, args.output, args.download, args.replay)
