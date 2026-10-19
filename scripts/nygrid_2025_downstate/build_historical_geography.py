"""Extract immutable PERFORM GIS coordinates for the 38 added source terminals.

This is geography-only. It does not modify electrical network artifacts or
replace the parent model's proxy coordinates. Unnamed source terminals retain
their original UNKNOWN/TAP labels even when a GIS point is available.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
WORKBOOK = ROOT / "PERFORM/Auxilliary_Perform_NY/NYISO_MOD2MAP.xlsx"
SECOND_WORKBOOK = ROOT / "PERFORM/Auxilliary_Perform_NY/internal_NYISO_MOD2MAP.xlsx"
NETWORK_BUSES = ROOT / "output/nygrid_2025_downstate/network/bus_register.csv"
NETWORK_CASES = ROOT / "output/nygrid_2025_downstate/network/network_cases.mat"
PARENT_COORDINATES = ROOT / "output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv"
PROJECT_COORDINATES = ROOT / "output/nygrid_2025_downstate/geography/source_project/project_station_coordinates.csv"
OUTPUT = ROOT / "output/nygrid_2025_downstate/geography/source_historical"
PINNED_WORKBOOK_SHA256 = "4fe4e89009f70e8a31ea73dd14b9f22ef97121d92b99ab8a1f59aec29eef33ec"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def worksheet_records(path):
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=False)
    sheet = workbook["BUS SUB"]
    values = iter(sheet.values)
    header = next(values)
    assert header == ("BUSNUM", "OBJECTID", "ID", "NAME", "CITY", "LATITUDE", "LONGITUDE", "COUNTY", "NYISOZONE")
    records = {}
    for sheet_row, row in enumerate(values, 2):
        if row[0] is None:
            continue
        record = dict(zip(header, row))
        bus_id = int(record["BUSNUM"])
        assert bus_id not in records, "Duplicate electrical source BUSNUM"
        record["worksheet_row"] = sheet_row
        records[bus_id] = record
    workbook.close()
    return records


def build(output=OUTPUT):
    before_network = sha(NETWORK_CASES)
    assert sha(WORKBOOK) == PINNED_WORKBOOK_SHA256, "Pinned GIS workbook changed"
    first, second = worksheet_records(WORKBOOK), worksheet_records(SECOND_WORKBOOK)
    with NETWORK_BUSES.open(newline="", encoding="utf-8") as stream:
        selected = [row for row in csv.DictReader(stream) if int(row["source_bus"]) > 0 and int(row["model_bus"]) > 140]
    assert len(selected) == 38
    rows, conflicts = [], []
    for bus in selected:
        sid, mid = int(bus["source_bus"]), int(bus["model_bus"])
        raw = first[sid]
        assert raw == second[sid], "GIS workbook versions disagree for selected source bus"
        lat, lon = raw["LATITUDE"], raw["LONGITUDE"]
        assert isinstance(lat, (float, int)) and isinstance(lon, (float, int)), "Coordinate formula or missing value"
        assert math.isfinite(lat) and math.isfinite(lon) and 40 <= lat <= 43 and -75 <= lon <= -71
        name_matches = bus["model_name"] == raw["NAME"]
        assert name_matches or (mid == 20011 and raw["NAME"] == "VERNON" and bus["model_name"] == "VERNON 138")
        unresolved = str(raw["NAME"]).startswith(("UNKNOWN", "TAP"))
        zone_disagrees = bus["physical_source_zone"] != raw["NYISOZONE"]
        if zone_disagrees:
            conflicts.append(dict(model_bus=mid, source_bus=sid, electrical_zone=bus["physical_source_zone"],
                                  workbook_zone=raw["NYISOZONE"], action="preserve_electrical_zone_no_geographic_relabeling"))
        rows.append(dict(model_bus=mid, source_bus=sid, model_name=bus["model_name"],
                         base_kv=float(bus["base_kv"]), accounting_zone=bus["accounting_zone"],
                         physical_source_zone=bus["physical_source_zone"], latitude_deg=lat, longitude_deg=lon,
                         coordinate_basis="PERFORM_workbook_GIS_point", coordinate_quality="historical_facility_point_accuracy_unspecified",
                         coordinate_crs="geographic_decimal_degrees_WGS84_assumed_not_declared_in_worksheet",
                         source_gis_objectid=int(raw["OBJECTID"]), source_gis_id=str(raw["ID"]), source_gis_name=raw["NAME"],
                         source_gis_city=raw["CITY"], source_gis_county=raw["COUNTY"], source_gis_zone=raw["NYISOZONE"],
                         source_workbook=str(WORKBOOK.relative_to(ROOT)).replace("\\", "/"), source_sheet="BUS SUB",
                         source_row=raw["worksheet_row"], latitude_cell=f"F{raw['worksheet_row']}", longitude_cell=f"G{raw['worksheet_row']}",
                         source_sha256=PINNED_WORKBOOK_SHA256, is_geographic_proxy=False,
                         station_identity_unresolved=unresolved, imputed_coordinate=False, survey_accuracy_verified=False,
                         physical_dlr_endpoint_qualified=False, source_zone_conflict=zone_disagrees,
                         notes="UNKNOWN/TAP source identity remains unresolved; the coordinate is directly recorded in the source workbook" if unresolved
                         else "Co-voltage terminals share the source station point; no surveyed busbar position is asserted"))
    assert len({r["model_bus"] for r in rows}) == 38
    assert len({(r["latitude_deg"], r["longitude_deg"]) for r in rows}) == 30
    assert sha(NETWORK_CASES) == before_network
    output.mkdir(parents=True, exist_ok=True)
    for filename, values in [("historical_station_coordinates.csv", rows), ("zone_metadata_conflicts.csv", conflicts)]:
        with (output / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(values[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(values)
    receipts = [dict(role=role, path=str(path.relative_to(ROOT)).replace("\\", "/"), sha256=sha(path)) for role, path in
                [("primary_GIS_source_workbook", WORKBOOK), ("independent_existing_workbook_copy", SECOND_WORKBOOK),
                 ("frozen_electrical_bus_identity", NETWORK_BUSES), ("frozen_network_unchanged", NETWORK_CASES),
                 ("extractor", Path(__file__))]]
    summary = dict(status="complete_source_coordinate_extraction", source_terminal_rows=38, distinct_geographic_points=30,
                   directly_recorded_coordinates=38, imputed_coordinates=0,
                   unnamed_or_tap_identity_rows=sum(r["station_identity_unresolved"] for r in rows),
                   source_zone_conflicts=len(conflicts), zone_policy="electrical_source_zones_preserved;GIS_H_vs_I_error_not_propagated",
                   coordinates_match_both_local_workbooks=True, coordinate_formulas=0,
                   network_sha256_before=before_network, network_sha256_after=sha(NETWORK_CASES),
                   original_parent_coordinates_modified=False,
                   limitations=["Coordinates are the historical PERFORM GIS points, not newly surveyed 2025 station coordinates",
                                "Worksheet does not declare CRS, positional accuracy or GIS update vintage",
                                "UNKNOWN/TAP labels remain unresolved physical identities despite recorded GIS positions"],
                   source_receipts=receipts)
    (output / "coordinate_receipt.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def build_original_anchors(output=OUTPUT):
    """Station-location overrides for drawing only; preserve original proxies."""
    before = sha(NETWORK_CASES)
    gis = worksheet_records(WORKBOOK)
    with PARENT_COORDINATES.open(encoding="utf-8-sig", newline="") as stream:
        parent = {int(r["idx"]): r for r in csv.DictReader(stream)}
    with NETWORK_BUSES.open(encoding="utf-8", newline="") as stream:
        current = {int(r["model_bus"]): r for r in csv.DictReader(stream)}
    southington_path = output / "raw_receipts/eversource_southington.json"
    owner_query = json.loads(southington_path.read_text(encoding="utf-8"))
    assert owner_query["spatialReference"]["wkid"] == 4326
    features = owner_query["features"]
    assert len(features) == 1
    owner = features[0]
    assert owner["attributes"]["NAME"] == "SOUTHINGTON" and owner["attributes"]["HIGH_VOLTAGE"] == "345"
    with PROJECT_COORDINATES.open(encoding="utf-8", newline="") as stream:
        matches = [r for r in csv.DictReader(stream) if int(r["model_bus"]) == 20010]
    assert len(matches) == 1
    goethals = matches[0]
    assert goethals["host_model_bus"] == "81" and goethals["source_name"] == "Goethals Substation"
    assert goethals["source_feature_id"] == "way/383102699" and "345000" in goethals["source_voltage_tags"].split(";")
    assert goethals["geometry_crs_used_for_centroid"] == "EPSG:32618" and goethals["crs"] == "EPSG:4326"
    goethals_source = ROOT / goethals["source_path"]
    assert sha(goethals_source) == goethals["source_sha256"], "Canonical Goethals source geometry changed"
    # Four prior construction aliases plus two explicit station-name matches.
    workbook_ids = {39: 818, 73: 651, 74: 897, 76: 1519, 77: 900, 80: 19}
    rows = []
    for mid in [35, 39, 73, 74, 76, 77, 78, 79, 80, 81, 82]:
        old = parent[mid]
        lon, lat = float(old["xcoord"]), float(old["ycoord"])
        original_lon, original_lat = lon, lat
        proxy = mid in [78, 79, 82]
        source_bus, source_name, source_url, source_row, gis_id = 0, old["name"], "", "", ""
        match = "unresolved_aggregate_proxy"
        note = "Retain published model point in the data; show as a nongeographic inset or explicitly hollow proxy marker. No physical station alias asserted."
        basis = "published_NYgrid_model_point"
        precision = "schematic_or_aggregate_location_not_physical"
        crs = "geographic_decimal_degrees_WGS84_assumed"
        source_voltage, voltage_match = "", False
        if mid in workbook_ids:
            source_bus = workbook_ids[mid]
            raw = gis[source_bus]
            lat, lon = float(raw["LATITUDE"]), float(raw["LONGITUDE"])
            source_name, source_row, gis_id = raw["NAME"], raw["worksheet_row"], str(raw["ID"])
            source_url = str(WORKBOOK.relative_to(ROOT)).replace("\\", "/") + f"#BUS SUB!F{source_row}:G{source_row}"
            basis = "PERFORM_workbook_GIS_station_point"
            precision = "site_point_not_surveyed_busbar"
            match = "existing_source_name_and_voltage_alias" if mid in [73, 74, 76, 77] else "station_name_geographic_anchor_only"
            source_voltage = 115 if mid == 80 else 345
            voltage_match = source_voltage == float(current[mid]["base_kv"])
            note = "Geographic station anchor only. Original electrical IDs, zones and topology remain unchanged."
            if mid == 80:
                note += " Source Northport bus19 is115kV while the parent proxy is138kV; common station-name location does not establish an electrical-bus alias."
            if mid in [74, 77]:
                note += " Ignore the workbook's H/I zone swap and retain the parent accounting zone."
        elif mid == 35:
            lat, lon = owner["geometry"]["y"], owner["geometry"]["x"]
            source_name = "SOUTHINGTON"
            source_url = "https://dghostingexternalmapprod.eversource.com/dghosting/rest/services/Substations/Substation_Locations/MapServer/2"
            basis, precision, crs = "current_owner_GIS_station_point", "owner_point_not_surveyed_busbar", "EPSG:4326_explicit_API_output"
            source_voltage, voltage_match = 345, True
            match = "parent_SOUTHINGTEN_spelling_alias_to_owner_SOUTHINGTON345"
            note = "Unique Eversource existing Southington4C 345kV station at315BellviewAve; display-coordinate override only, not a LongMountain relabeling."
        elif mid == 81:
            lat, lon = float(goethals["latitude_deg"]), float(goethals["longitude_deg"])
            source_name = "Goethals Substation"
            source_url = "https://www.openstreetmap.org/way/383102699"
            basis, precision, crs = "current_OSM_named_substation_polygon_centroid", "UTM18N_area_centroid_not_surveyed_busbar", "EPSG:4326_from_EPSG32618_polygon_centroid"
            source_voltage, voltage_match = "345;230", True
            match = "matching_station_name_and_345kV_OSM_tag"
            note = "Canonical OSM polygon area centroid calculated inUTM18N and returned toWGS84; exactly shares projectPAR20010 host point. OSMfeatureversion" + goethals["source_feature_version"] + " dated" + goethals["source_feature_timestamp"] + ". Display-only override, not surveyed equipment coordinates."
        rows.append(dict(model_bus=mid, model_name=current[mid]["model_name"], base_kv=float(current[mid]["base_kv"]),
                         accounting_zone=current[mid]["accounting_zone"], latitude_deg=lat, longitude_deg=lon,
                         published_model_latitude_deg=original_lat, published_model_longitude_deg=original_lon,
                         coordinate_override_applied=not proxy, is_geographic_proxy=proxy,
                         geographic_site_located=not proxy, coordinate_basis=basis, coordinate_precision=precision,
                         coordinate_crs=crs, source_bus=source_bus, source_name=source_name,
                         source_gis_id=gis_id, source_workbook_row=source_row,
                         source_site_voltage_kv=source_voltage, source_voltage_matches_parent=voltage_match,
                         identity_mapping_basis=match, source_url=source_url,
                         recommended_display="nongeographic_proxy_inset" if proxy else "geographic_site_anchor",
                         survey_accuracy_verified=False, physical_dlr_endpoint_qualified=False, notes=note))
    with (output / "original_anchor_coordinates.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    assert sha(NETWORK_CASES) == before
    receipt = dict(status="complete_mapping_only_anchor_register", records=len(rows), located_station_anchors=8,
                   retained_unlocated_aggregate_proxies=[78, 79, 82], source_voltage_caveat_bus80=True,
                   no_electrical_arrays_or_zones_changed=True, network_sha256_before=before, network_sha256_after=sha(NETWORK_CASES),
                   goethals_canonical_host=dict(model_bus=81, shared_project_bus=20010,
                                               latitude_deg=float(goethals["latitude_deg"]), longitude_deg=float(goethals["longitude_deg"]),
                                               source_feature_id=goethals["source_feature_id"], source_feature_version=goethals["source_feature_version"],
                                               source_feature_timestamp=goethals["source_feature_timestamp"],
                                               geometry_crs="EPSG:32618", output_crs="EPSG:4326", method="polygon_area_centroid"),
                   sources=[dict(path=str(p.relative_to(ROOT)).replace("\\", "/"), sha256=sha(p)) for p in
                            [WORKBOOK, PARENT_COORDINATES, NETWORK_BUSES, southington_path, PROJECT_COORDINATES, goethals_source, Path(__file__)]])
    (output / "original_anchor_receipt.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return receipt


if __name__ == "__main__":
    build()
    build_original_anchors()
