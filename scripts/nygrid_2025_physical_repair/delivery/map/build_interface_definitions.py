"""Bind frozen seven-cut semantics to current map identities and saved flows.

This is read-only postprocessing of existing model and annual results. It
does not solve a power flow, alter a cut, or fit an interface to observations.
"""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
import zipfile
import numpy as np
import pandas as pd
from scipy.io import loadmat
from repair_paths import ANNUAL, COMPARISON

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "output/nygrid_2025_physical_repair/delivery/map"
STATES = ["pre_may", "may21", "may30", "post_dover"]
IDS = ["dysinger_east", "west_central", "total_east", "moses_south", "central_east_vc", "upny_coned", "spr_dun_south"]
CONVENTIONS = ["legacy_signed_literal_from", "oriented_source_side", "oriented_target_side"]
LCC = "+proj=lcc +lat_1=40 +lat_2=45 +lat_0=42 +lon_0=-76 +datum=WGS84 +units=m +no_defs"
NAMES = ["West", "Genesee", "Central", "North", "Mohawk Valley", "Capital", "Hudson Valley", "Millwood", "Dunwoodie", "New York City", "Long Island"]
SOURCE_NAMES = ["WEST", "GENESE", "CENTRL", "NORTH", "MHK VL", "CAPITL", "HUD VL", "MILLWD", "DUNWOD", "N.Y.C.", "LONGIL"]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def record(path):
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    alignment = ROOT / "output/nygrid_2025_acpf_profile_audit/alignment"
    terms_path = alignment / "interface_operator_terms.csv"
    contract_path = alignment / "interface_operator_contract.json"
    intent_path = ROOT / "output/nygrid_2025_downstate/replay/interface_definitions.json"
    map_path = ROOT / "output/nygrid_2025_physical_repair/delivery/structure/runtime_branch_map.csv"
    bus_path = ROOT / "output/nygrid_2025_physical_repair/delivery/structure/detailed_bus_map.csv"
    retained_path = ROOT / "output/nygrid_2025_physical_repair/delivery/structure/retained_bus_map.csv"
    geo_path = ROOT / "output/nygrid_2025_downstate/geography/bus_geographic_register.csv"
    comparison_path = COMPARISON / "comparison_arrays.npz"
    annual = ANNUAL
    annual_receipt_path = annual / "annual_receipt.json"
    source_paths = [terms_path, contract_path, intent_path, map_path, bus_path, retained_path, geo_path, comparison_path, annual_receipt_path, Path(__file__)]
    contract = json.loads(contract_path.read_text()); intent = json.loads(intent_path.read_text())
    for item in contract["source_receipts"]:
        assert sha(ROOT / item["path"]) == item["sha256"], item["path"]
    terms = pd.read_csv(terms_path, keep_default_na=False)
    branchmap = pd.read_csv(map_path, keep_default_na=False)
    busmap = pd.read_csv(bus_path, keep_default_na=False)
    retained = set(pd.read_csv(retained_path).model_bus_id.astype(int))
    geography = pd.read_csv(geo_path, keep_default_na=False).set_index("model_bus")
    current = busmap[busmap.state.eq("post_dover")].set_index("model_bus_id")
    def location(bus):
        if bus not in geography.index or str(geography.loc[bus, "plot_on_geographic_map"]).lower() != "true":
            return None
        row = geography.loc[bus]; lon, lat = float(row.map_longitude_deg), float(row.map_latitude_deg)
        assert np.isfinite([lon, lat]).all()
        x, y = float(row.projected_easting_km), -float(row.projected_northing_km)
        assert np.isfinite([x, y]).all()
        return {"lonlat": [lon, lat], "xy": [x, y],
                "coordinate_quality": str(row.coordinate_quality), "coordinate_source": str(row.coordinate_source)}
    def mean_location(buses):
        used = [(b, location(b)) for b in sorted(set(buses))]
        used = [(b, value) for b, value in used if value is not None]
        if not used: return {"located_bus_ids": [], "lonlat": None, "xy": None}
        return {"located_bus_ids": [b for b, _ in used],
                "lonlat": np.mean([v["lonlat"] for _, v in used], axis=0).tolist(),
                "xy": np.round(np.mean([v["xy"] for _, v in used], axis=0), 6).tolist()}
    primary = ROOT / "output/nygrid_2025_inputs/load_source/raw/20250101palIntegrated_csv.zip"
    primary_proof = primary.with_suffix(primary.suffix + ".provenance.json")
    zone_mapping = ROOT / "System Matpower Format/NY_Lite/nyiso_public_zone_map.m"
    source_paths += [primary, primary_proof, zone_mapping]
    acquired = json.loads(primary_proof.read_text()); assert sha(primary) == acquired["sha256"]
    with zipfile.ZipFile(primary) as archive:
        member = next(n for n in archive.namelist() if n.endswith("20250101palIntegrated.csv"))
        payload = archive.read(member)
    zone_rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
    primary_zones = sorted({(r["Name"], int(r["PTID"])) for r in zone_rows})
    assert primary_zones == sorted(zip(SOURCE_NAMES, range(61752, 61763)))
    assert all("'" + name + "'" in zone_mapping.read_text() for name in SOURCE_NAMES)
    zones = []
    for i, (display, exact) in enumerate(zip(NAMES, SOURCE_NAMES)):
        letter = chr(65 + i); members = sorted(b for b in retained if current.loc[b, "accounting_group"] == letter)
        anchor = mean_location(members)
        zones.append({"id": letter, "display_name": display, "source_name": exact, "PTID": 61752 + i,
            "label": letter + " Â· " + display, "anchor_lonlat": anchor["lonlat"], "anchor_xy": anchor["xy"],
            "anchor_member_bus_ids": anchor["located_bus_ids"], "accounting_member_bus_ids": members,
            "anchor_basis": "Mean of located current retained model-bus coordinates in this accounting group",
            "official_zone_polygon": False, "display_name_is_readable_expansion_of_source_abbreviation": True})
    interfaces, structural_checks = [], []
    for j, definition in enumerate(intent):
        name = definition["interface"]; by_state = {}
        for state in STATES:
            table = terms[terms.state.eq(state) & terms.interface.eq(name)]
            mapping = branchmap[branchmap.state.eq(state)].set_index("branch_key")
            buses = busmap[busmap.state.eq(state)].set_index("model_bus_id")
            members = []
            for term in table.itertuples():
                parent, sign = int(term.original_branch_row), int(term.coefficient)
                first = mapping.loc[term.first_runtime_branch_key]; last = mapping.loc[term.last_runtime_branch_key]
                all_sections = mapping[mapping.parent_corridor_row.eq(parent)]
                assert first.parent_corridor_row == last.parent_corridor_row == parent
                assert int(first.from_bus) == term.original_from_bus and int(last.to_bus) == term.original_to_bus
                assert first.physical_terminal_from and last.physical_terminal_to
                assert len(all_sections) == term.section_count and all_sections.status.eq(1).all()
                assert int(first.runtime_branch_row) == term.first_runtime_branch_row and int(last.runtime_branch_row) == term.last_runtime_branch_row
                positive_from = int(term.original_from_bus if sign > 0 else term.original_to_bus)
                positive_to = int(term.original_to_bus if sign > 0 else term.original_from_bus)
                assert buses.loc[positive_from, "accounting_group"] in definition["source_zones"]
                assert buses.loc[positive_to, "accounting_group"] in definition["target_zones"]
                members.append({"parent_id": parent, "parent_key": str(term.original_corridor_key), "coefficient": sign,
                    "from_bus": int(term.original_from_bus), "to_bus": int(term.original_to_bus),
                    "positive_from_bus": positive_from, "positive_to_bus": positive_to,
                    "first_runtime_key": str(term.first_runtime_branch_key), "last_runtime_key": str(term.last_runtime_branch_key),
                    "first_runtime_row": int(term.first_runtime_branch_row), "last_runtime_row": int(term.last_runtime_branch_row),
                    "section_count": int(term.section_count), "indices_are_one_based": True})
            assert members
            by_state[state] = members
            structural_checks.append({"state": state, "interface": name, "members": len(members),
                "current_parent_and_physical_terminal_mapping_passed": True, "zone_orientation_passed": True})
        keys = ["parent_id", "parent_key", "coefficient", "from_bus", "to_bus", "first_runtime_key", "last_runtime_key"]
        canonical = [{k: v[k] for k in keys} for v in by_state[STATES[0]]]
        assert all([{k: v[k] for k in keys} for v in by_state[s]] == canonical for s in STATES)
        members = by_state["post_dover"]
        source = mean_location([r["positive_from_bus"] for r in members]); target = mean_location([r["positive_to_bus"] for r in members])
        assert source["xy"] and target["xy"]
        orientation = {"source_bus_ids": sorted({r["positive_from_bus"] for r in members}),
            "target_bus_ids": sorted({r["positive_to_bus"] for r in members}),
            "located_source_bus_ids": source["located_bus_ids"], "located_target_bus_ids": target["located_bus_ids"],
            "source_lonlat": source["lonlat"], "target_lonlat": target["lonlat"],
            "label_anchor_lonlat": ((np.array(source["lonlat"]) + target["lonlat"]) / 2).tolist(),
            "source_xy": source["xy"], "target_xy": target["xy"],
            "label_anchor_xy": np.round((np.array(source["xy"]) + target["xy"]) / 2, 6).tolist(),
            "geometry_basis": "Unweighted mean of unique located sign-oriented member endpoint model coordinates; schematic cut arrow, not a meter route",
            "positive_arrow": "source_to_target", "negative_arrow": "target_to_source", "zero_or_null_flow_arrow": "none"}
        interfaces.append({"id": IDS[j], "index": j + 1, "name": name,
            "inherited_interface_id": int(definition["inherited_interface_id"]),
            "source_zones": definition["source_zones"], "target_zones": definition["target_zones"],
            "member_count": len(members), "members_by_state": by_state, "positive_orientation": orientation,
            "physical_NYISO_meter_membership_certified": False})
    assert sum(i["member_count"] for i in interfaces) == 34
    assert [r["parent_id"] for r in interfaces[5]["members_by_state"]["post_dover"]] == [297, 361, 362, 363, 364, 365]
    assert [r["parent_id"] for r in interfaces[6]["members_by_state"]["post_dover"]] == [319, 320, 328, 329, 330, 336, 337, 338]
    with np.load(comparison_path, allow_pickle=False) as comparison:
        gamma = float(comparison["gamma"])
        assert [i["name"] for i in interfaces] == comparison["interface_names"].tolist()
        comparison_arrays = {c: comparison["candidate_" + c].copy() for c in CONVENTIONS}
        expected_qualified = comparison["candidate_qualified"].copy()
        expected_source = comparison["source_qualified"].copy(); expected_time = comparison["timestamp_utc"].copy()
    definitions = {"schema_version": 1, "model_version_source_commit": "2e0fcd5c3f0ae39d04f27a733ce30eb148b0b243",
        "scope": "Current model NY accounting-zone labels and frozen diagnostic interface cuts",
        "default_convention": CONVENTIONS[0], "conventions": contract["formulas"], "gamma": gamma,
        "default_units": "model_MW", "public_scale_formula": "model_MW / gamma", "ampere_gamma_rescaling": False,
        "flow_availability_mask": ["source_qualified", "PF_converged", "AC_equation_gate", "loss_allocation_gate", "reduction_and_equation_gate"],
        "missing_or_failed_model_flow": None, "negative_flow_reverses_arrow": True,
        "physical_gate_scope": "Modeled zone-cut diagnostic; physical NYISO P-32 meter membership and route are not certified",
        "observed_comparison_units": "Preserved numeric-as-MW interpretation of P32 Flow (MWH), not independently certified",
        "projection": {"proj4": LCC, "xy_definition": "[easting_m/1000, -northing_m/1000]", "geographic_axis": "[longitude,latitude]"},
        "zones": zones, "interfaces": interfaces,
        "zone_primary_source": {"url": acquired["source_url"], "archive_sha256": sha(primary), "member": member,
            "member_sha256": hashlib.sha256(payload).hexdigest(), "letter_mapping_source": record(zone_mapping)},
        "notes": ["State-specific numeric runtime rows must not index canonical annual arrays directly; join by runtime branch key.",
            "UPNY and SPR use the expanded current terms; unexpanded parent IDs in the older intent-only JSON are not current members.",
            "TOTAL EAST includes the four CENTRAL EAST - VC parents plus parent 224; overlapping cuts are not independent corridors.",
            "Unknown/unlocated model points are not geocoded or fabricated for these anchors."],
        "prepared_sources": [record(p) for p in source_paths]}
    (OUT / "interface_definitions.json").write_text(json.dumps(definitions, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("INTERFACE_DEFINITIONS_READY seven cuts,34 terms/state,11 zones", flush=True)
    calculated = {c: np.full((8760, 7), np.nan) for c in CONVENTIONS}
    qualified = np.zeros(8760, bool); source_mask = np.zeros(8760, bool); operating = np.zeros(8760, bool); seen = np.zeros(8760, int)
    annual_files = []
    fields = ["hour_index", "timestamp_utc", "gamma", "PF", "PT", "branch_keys", "branch_parent_row", "branch_present", "branch_active", "topology_state_index",
              "source_qualified", "PF_converged", "AC_equation_gate", "loss_allocation_gate", "reduction_and_equation_gate", "VQ_and_generator_assumption_gate"]
    max_loss_error = 0.0
    for month in range(1, 13):
        path = annual / f"monthly/profile_PF_2025_{month:02d}.mat"; annual_files.append(path)
        data = loadmat(path, variable_names=fields, simplify_cells=True)
        hours = np.asarray(data["hour_index"], int) - 1; seen[hours] += 1
        assert float(data["gamma"]) == gamma and np.array_equal(np.asarray(data["timestamp_utc"], str), expected_time[hours])
        good = np.ones(len(hours), bool)
        for field in definitions["flow_availability_mask"]: good &= np.asarray(data[field], bool)
        qualified[hours] = good; source_mask[hours] = data["source_qualified"]; operating[hours] = data["VQ_and_generator_assumption_gate"]
        keyrow = {str(key): k for k, key in enumerate(data["branch_keys"])}
        for state_no, state in enumerate(STATES, 1):
            selected = np.flatnonzero(good & (np.asarray(data["topology_state_index"]) == state_no))
            if not len(selected): continue
            actual_hours = hours[selected]
            for j, interface in enumerate(interfaces):
                signed_from = np.zeros(len(selected)); source_end = signed_from.copy(); target_end = signed_from.copy(); losses = signed_from.copy()
                for item in interface["members_by_state"][state]:
                    first, last = keyrow[item["first_runtime_key"]], keyrow[item["last_runtime_key"]]
                    assert np.all(data["branch_present"][selected][:, [first, last]]) and np.all(data["branch_active"][selected][:, [first, last]])
                    assert data["branch_parent_row"][first] == data["branch_parent_row"][last] == item["parent_id"]
                    pf = data["PF"][selected, first]; pt = data["PT"][selected, last]
                    assert np.isfinite(pf).all() and np.isfinite(pt).all()
                    signed_from += item["coefficient"] * pf
                    source_end += pf if item["coefficient"] > 0 else pt
                    target_end += -pt if item["coefficient"] > 0 else -pf
                    losses += pf + pt
                calculated[CONVENTIONS[0]][actual_hours, j] = signed_from
                calculated[CONVENTIONS[1]][actual_hours, j] = source_end
                calculated[CONVENTIONS[2]][actual_hours, j] = target_end
                max_loss_error = max(max_loss_error, float(np.max(np.abs(source_end - target_end - losses))))
        print(f"INTERFACE_MONTH {month:02d} qualified={int(good.sum())}", flush=True)
    assert np.all(seen == 1) and np.array_equal(qualified, expected_qualified) and np.array_equal(source_mask, expected_source)
    assert int(source_mask.sum()) == 8651
    operating &= qualified
    errors = {c: float(np.max(np.abs(calculated[c][qualified] / gamma - comparison_arrays[c][qualified]))) for c in CONVENTIONS}
    assert max(errors.values()) < 1e-8 and max_loss_error < 1e-8
    assert all(np.isnan(v[~qualified]).all() and np.isfinite(v[qualified]).all() for v in calculated.values())
    np.savez_compressed(OUT / "interface_flow_reference.npz", hour_index=np.arange(1, 8761), timestamp_utc=expected_time,
        interface_ids=np.array(IDS), interface_names=np.array([i["name"] for i in interfaces]), gamma=gamma,
        qualified=qualified, source_qualified=source_mask, operating_qualified=operating, **calculated)
    checks = {"passed": True, "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Independent current member/zone/terminal identity and saved annual flow reconstruction; no new electrical experiment",
        "interface_count": 7, "terms_per_state": 34, "unique_parent_members": len({r["parent_id"] for i in interfaces for r in i["members_by_state"]["post_dover"]}),
        "located_endpoint_buses": 31, "zone_count": 11, "source_qualified_hours": 8651, "flow_qualified_hours": int(qualified.sum()),
        "source_excluded_hours": 109, "source_eligible_failed_hours": int((source_mask & ~qualified).sum()), "operating_qualified_hours": int(operating.sum()),
        "maximum_public_scale_error_against_frozen_comparison_MW": errors,
        "maximum_oriented_source_target_loss_identity_error_model_MW": max_loss_error,
        "failure_rows_are_NaN_not_zero": True, "negative_qualified_values_per_interface": {IDS[j]: int((calculated[CONVENTIONS[0]][qualified, j] < 0).sum()) for j in range(7)},
        "structural_checks": structural_checks, "annual_source_files": [record(p) for p in annual_files],
        "prepared_sources": definitions["prepared_sources"], "outputs": [record(OUT / "interface_definitions.json"), record(OUT / "interface_flow_reference.npz")],
        "PF_OPF_or_annual_solution_run": False, "old_artifacts_modified": False,
        "physical_P32_membership_or_numeric_unit_convention_newly_certified": False}
    (OUT / "interface_semantics_review.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "qualified": int(qualified.sum()), "gamma": gamma, "max_public_MW_errors": errors, "loss_identity_error": max_loss_error}))


if __name__ == "__main__": main()
