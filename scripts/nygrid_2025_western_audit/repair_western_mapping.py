"""Combine reviewed western site-zone and Lewiston project-proxy repairs.

Starts from the already corrected Moses fleet. Only mapping fields change;
all unit identities, capacities, admission policies, priors and dispatch are
immutable. Large numeric artifacts are referenced by path and hash, not copied.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_western_audit"
DEFAULT = OUT / "corrected"
BASE = ROOT / "output/nygrid_2025_moses_audit/corrected"
FLEET = BASE / "fleet/fleet_register.csv"
REGISTER = BASE / "model_generator_register.csv"
PARENT = ROOT / "output/nygrid_2025_dispatch/fleet/source_parent"
UNITS = OUT / "mapping/source_confirmed_unit_zone_proposals.csv"
SITES = OUT / "mapping/source_confirmed_site_zone_proposals.csv"
LEWISTON = OUT / "generation/Lewiston_candidate_landing_correction.csv"
GOLD = ROOT / "output/nygrid_2025_dispatch/fleet/source_scope/2025_Gold_Book.pdf"
PINNED = {
    FLEET: "f7266a08faac3d65442482f8e5c3f2facfbf0c25960419820c7f2eb514710d13",
    REGISTER: "1211d0f632df2ccd6306ce299de5d24644d4d28d0d987af8421c8b7559a01e21",
    UNITS: "f78041d1a85458023bce6769effb910d9462160d8b910a9ccf2cc8621c41bc32",
    SITES: "7adec9c2193d181275dd5f2c0fef93c5ea833a552b9e11f6cf11eabc6f18ba98",
    LEWISTON: "d5730bb89e45bcea2795f2c8ef21aad26324616c13b7c7e57d60de80dea83838",
    OUT / "mapping/EIA_site_identity.csv": "29d9b4c5245d34f247014e78fdced50c6eb9d26ddbd987be31d39c86bd5ae60c",
    PARENT / "npcc.csv": "3f203b94d44b95607c48b4f5a8eb78adf42cbbc600294122ac87399e53626b2d",
    PARENT / "nygrid_full_updateOpCond.m": "2a0ad5224190194abe528a824dfd508005aa2cdf23f5b4d8845ec80e3726154a",
    GOLD: "cc43665b9344a04b4c9355edd1dc7e31d42a6bb759ffe027ad867221556aea8e",
    OUT / "generation/sources/NYISO_Niagara_Model_20180724.pdf": "7ace05f9231540b218add162fbe70398b649bd4089fc350f062d81e067178396",
}
ALLOWED = {"zone", "zone_mapping_policy", "bus_id", "parent_bus_name", "parent_bus_zone",
    "mapping_method", "bus_landing_proxy", "mapping_distance_km", "source_zone_parent_bus_zone_conflict"}
MODEL_ALLOWED = {"bus_id", "zone", "mapping_method"}
OLD_FIELDS = ["fleet_id", "plant_id", "device_key", "plant_name", "eia_generator_id", "zone", "zone_mapping_policy",
    "bus_id", "parent_bus_zone", "mapping_method", "legacy_source_gen_rows", "legacy_candidate_bus_ids",
    "legacy_mapping_ambiguous", "nameplate_capacity_mw", "summer_capacity_mw", "dispatch_eligible_default"]
NUMERIC_FIELDS = {"fleet_id", "plant_id", "bus_id", "legacy_mapping_ambiguous", "nameplate_capacity_mw",
    "summer_capacity_mw", "dispatch_eligible_default"}
EXPECTED_SITES = {2568: "B", 2623: "B", 61012: "B", 56987: "B", 50203: "B", 54593: "B", 50568: "C", 58399: "B"}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader), reader.fieldnames


def write(path, rows, fields=None):
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def distance(row, bus):
    lat1, lat2 = math.radians(float(row["latitude"])), math.radians(float(bus["ycoord"]))
    dlon = math.radians(float(row["longitude"]) - float(bus["xcoord"]))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1., math.sqrt(a)))


def build(output=DEFAULT):
    output = Path(output).resolve()
    require(not (output / "fleet_register.csv").exists(), "Choose a fresh output directory; corrected fleet already exists")
    for path, expected in PINNED.items():
        require(sha(path) == expected, "Reviewed source/base hash changed: " + str(path.relative_to(ROOT)))
    fleet, fields = read(FLEET); model, model_fields = read(REGISTER)
    proposals, _ = read(UNITS); sites, _ = read(SITES); lewiston, _ = read(LEWISTON)
    parents, _ = read(PARENT / "npcc.csv")
    by_id = {int(r["fleet_id"]): r for r in fleet}
    buses = {int(r["idx"]): r for r in parents}
    require(len(by_id) == len(fleet) == 2245 and len({r["device_key"] for r in fleet}) == 2245, "Fleet identity axis invalid")
    require([int(r["gen_row"]) for r in model] == list(range(1, 1465)), "Original model generator order changed")
    require(len(sites) == 8 and {int(r["plant_id"]): r["new_zone"] for r in sites} == EXPECTED_SITES, "Unreviewed site scope")
    require(len(proposals) == 30 and len({r["fleet_id"] for r in proposals}) == 30, "Reviewed western unit scope changed")
    require(len(lewiston) == 12 and {int(r["plant_id"]) for r in lewiston} == {2692}, "Lewiston unit scope changed")
    require(not ({r["fleet_id"] for r in proposals} & {r["fleet_id"] for r in lewiston}), "Proposal scopes overlap")
    source_summary = json.loads((OUT / "mapping/mapping_summary.json").read_text())
    require(source_summary["failed_checks"] == 0 and source_summary["all_frozen_inputs_unchanged"], "Mapping source audit is not qualified")
    original_moses, _ = read(BASE / "fleet/plant_zone_corrections.csv")
    original_moses_ids = {int(r["plant_id"]) for r in original_moses}
    require(len(original_moses_ids) == 26 and not original_moses_ids.intersection(set(EXPECTED_SITES) | {2692}), "Earlier Moses correction overlaps new repair")
    artifacts = {
        "fleet_bounds_npz": ROOT / "output/nygrid_2025_dispatch/fleet/fleet_bounds.npz",
        "fleet_bounds_mat": ROOT / "output/nygrid_2025_dispatch/fleet/fleet_bounds.mat",
        "per_unit_source_priors_npz": ROOT / "output/nygrid_2025_dispatch/priors/dispatch_priors.npz",
        "frozen_dispatch_mat": ROOT / "output/nygrid_2025_dispatch/dispatch/dispatch.mat",
        "dispatch_priors_mat": ROOT / "output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat",
        "dispatch_bounds_mat": ROOT / "output/nygrid_2025_dispatch/dispatch/dispatch_bounds.mat",
    }
    dependencies = list(PINNED) + list(artifacts.values()) + [BASE / "fleet/plant_zone_corrections.csv",
        OUT / "mapping/mapping_summary.json", OUT / "generation/generation_audit.json", Path(__file__)]
    before = {p: sha(p) for p in dependencies}
    revised = {fid: row.copy() for fid, row in by_id.items()}
    evidence, reviewed_unchanged = [], []
    for proposal in proposals:
        fid = int(proposal["fleet_id"]); old = by_id[fid]; new = revised[fid]
        for field in OLD_FIELDS:
            if field in NUMERIC_FIELDS:
                require(float(old[field]) == float(proposal[field]), "Proposal old numeric field differs: " + str(fid) + ":" + field)
            else:
                require(old[field] == proposal[field], "Proposal old identity/legacy field differs: " + str(fid) + ":" + field)
        pid = int(old["plant_id"]); zone = proposal["proposed_zone"]; bid = int(proposal["proposed_bus_id"])
        require(zone == EXPECTED_SITES[pid] and buses[bid]["zone"] == zone, "Destination site zone differs")
        require(buses[bid]["name"] == proposal["proposed_parent_bus_name"], "Destination bus identity differs")
        require(proposal["physical_terminal_verified"] == "False", "Unreviewed physical-terminal claim")
        move = bid != int(old["bus_id"])
        change_zone = zone != old["zone"]
        require((proposal["zone_changes"] == "True") == change_zone, "Zone-change flag differs")
        if not change_zone:
            require(pid == 54593 and old["eia_generator_id"] in {"GEN1", "GEN2"} and not move,
                    "Unexpected unchanged-site control")
            reviewed_unchanged.append(fid)
        else:
            table = "III2b" if int(proposal["source_pdf_page"]) == 100 else "III2a"
            new["zone"] = zone
            new["zone_mapping_policy"] = "NYISO_GoldBook2025_" + table + "_station_zone_verified_EIA_plant_join"
            new["source_zone_parent_bus_zone_conflict"] = "0"
            if move:
                require(not old["legacy_source_gen_rows"] and not old["legacy_candidate_bus_ids"]
                        and old["legacy_mapping_ambiguous"] == "0", "A moved fallback unit has unresolved or existing legacy terminals")
                require(old["coordinates_available"] == "1", "Moved fallback lacks coordinates")
                ranked = [(distance(old, b), int(b["idx"])) for b in parents if b["zone"] == zone]
                km, nearest = min(ranked)
                require(nearest == bid and abs(km - float(proposal["proposed_mapping_distance_km"])) < 1e-8,
                        "Reviewed destination does not reproduce existing nearest-in-zone rule")
                new.update(bus_id=str(bid), parent_bus_name=buses[bid]["name"], parent_bus_zone=zone,
                    mapping_method="same_zone_nearest_parent_bus_geographic_proxy", bus_landing_proxy="1", mapping_distance_km=str(km))
            else:
                require(pid == 54593 and old["eia_generator_id"] == "GEN3" and bid == 62 and old["parent_bus_zone"] == "B",
                        "Unexpected same-bus zone correction")
                # Existing same-plant legacy identity and its absent distance
                # remain intact; only incorrect zone metadata is corrected.
        evidence.append(dict(fleet_id=fid, kind="site_zone", site_proposal=next(r for r in sites if int(r["plant_id"]) == pid),
            reviewed_unit_proposal=proposal, exact_base_identity={k: old[k] for k in OLD_FIELDS},
            old_mapping={k: old[k] for k in sorted(ALLOWED)}, new_mapping={k: new[k] for k in sorted(ALLOWED)},
            legacy_association_fields_preserved=True, physical_terminal_verified=False))
    require(len(reviewed_unchanged) == 2, "Expected two unchanged Batavia control units")
    for proposal in lewiston:
        fid = int(proposal["fleet_id"]); old = by_id[fid]; new = revised[fid]
        for field in ["device_key", "eia_generator_id", "source_status"]:
            require(old[field] == proposal[field], "Lewiston old identity changed")
        require(int(old["plant_id"]) == 2692 and old["zone"] == "A" and old["bus_id"] == "57"
                and old["parent_bus_name"] == "HUNTLEY" and old["parent_bus_zone"] == "A", "Lewiston old landing changed")
        require(proposal["new_bus_id"] == "55" and proposal["new_zone"] == "A" and proposal["physical_terminal_ID_claim"] == "False", "Lewiston destination/claim changed")
        require(buses[55]["name"] == "NIAGARA E" and float(buses[55]["Vn"]) == 230 and buses[55]["zone"] == "A", "Canonical Niagara project anchor changed")
        require("Bus 55: zone A, Niagara" in (PARENT / "nygrid_full_updateOpCond.m").read_text(), "Legacy Niagara project anchor missing")
        require(not old["legacy_source_gen_rows"] and not old["legacy_candidate_bus_ids"], "Lewiston gained an unreviewed unit-terminal legacy association")
        new.update(bus_id="55", parent_bus_name="NIAGARA E", parent_bus_zone="A",
            mapping_method=proposal["new_mapping_method"], bus_landing_proxy="1", mapping_distance_km=str(distance(old, buses[55])),
            source_zone_parent_bus_zone_conflict="0")
        evidence.append(dict(fleet_id=fid, kind="Lewiston_project_voltage_proxy", reviewed_unit_proposal=proposal,
            exact_base_identity={k: old[k] for k in OLD_FIELDS}, old_mapping={k: old[k] for k in sorted(ALLOWED)},
            new_mapping={k: new[k] for k in sorted(ALLOWED)},
            unit_level_legacy_association_invented=False, legacy_project_anchor="Original builder explicitly names Niagara at bus55; no old2019 dispatch rule reused",
            physical_terminal_verified=False, within_ZoneA_relocation_changes_zone_cut_flow_at_fixed_injections=False))
    new_fleet = [revised[int(row["fleet_id"])] for row in fleet]
    changes, changed_units, landings = [], set(), []
    for old, new in zip(fleet, new_fleet):
        for key in fields:
            if old[key] != new[key]:
                require(key in ALLOWED, "Forbidden fleet field changed: " + key)
                changed_units.add(int(old["fleet_id"]))
                changes.append(dict(fleet_id=old["fleet_id"], device_key=old["device_key"], plant_id=old["plant_id"],
                    field=key, old_value=old[key], new_value=new[key]))
        if int(old["plant_id"]) in original_moses_ids:
            require(old == new and new["zone"] == "E", "Previous D-to-E hydro correction changed")
        if int(old["fleet_id"]) in changed_units:
            landings.append(dict(fleet_id=old["fleet_id"], plant_id=old["plant_id"], device_key=old["device_key"],
                old_zone=old["zone"], new_zone=new["zone"], old_bus_id=old["bus_id"], new_bus_id=new["bus_id"],
                old_parent_bus_name=old["parent_bus_name"], new_parent_bus_name=new["parent_bus_name"],
                mapping_method=new["mapping_method"], physical_terminal_verified=False))
    require(len(changed_units) == 40, "Changed inventory unit count differs")
    zone_changes = sum(a["zone"] != b["zone"] for a, b in zip(fleet, new_fleet))
    bus_changes = sum(a["bus_id"] != b["bus_id"] for a, b in zip(fleet, new_fleet))
    require(zone_changes == 28 and bus_changes == 39, "Zone/bus change counts differ")
    new_model, model_changes, active_changed, active_moved = [], [], set(), set()
    for old in model:
        new = old.copy()
        if old["role"] == "native":
            row = revised[int(old["fleet_id"])]
            original = by_id[int(old["fleet_id"])]
            require(old["device_key"] == row["device_key"] and all(old[k] == original[k] for k in ["bus_id", "zone", "mapping_method"]),
                    "Base model register is inconsistent with corrected Moses fleet")
            for key in MODEL_ALLOWED:
                new[key] = row[key]
        for key in model_fields:
            if old[key] != new[key]:
                require(old["role"] == "native" and key in MODEL_ALLOWED, "Forbidden model generator field changed")
                active_changed.add(int(old["gen_row"]))
                if key == "bus_id":
                    active_moved.add(int(old["gen_row"]))
                model_changes.append(dict(gen_row=old["gen_row"], fleet_id=old["fleet_id"], device_key=old["device_key"],
                    field=key, old_value=old[key], new_value=new[key]))
        new_model.append(new)
    require(len(active_changed) == 36 and len(active_moved) == 35, "Active generator mapping counts differ")
    output.mkdir(parents=True, exist_ok=True)
    write(output / "fleet_register.csv", new_fleet, fields)
    write(output / "model_generator_register.csv", new_model, model_fields)
    write(output / "changed_fleet_fields.csv", changes)
    write(output / "changed_model_fields.csv", model_changes)
    write(output / "corrected_bus_landings.csv", landings)
    contract = dict(numeric_artifacts_copied=False, numeric_artifacts_modified=False,
        PG_rebalanced_by_mapping_repair=False, parent_dispatch_will_handle_external_flow_reprojection_separately=True,
        artifacts={key: dict(path=path.relative_to(ROOT).as_posix(), sha256=before[path]) for key, path in artifacts.items()},
        reuse_basis="Generator identities, per-unit priors, capacities and admission are unchanged; mapping is separate from the global bounded dispatch objective")
    (output / "numeric_reuse_contract.json").write_text(json.dumps(contract, indent=2) + "\n")
    crosswalk = dict(status="reviewed_and_old_fields_verified_fail_closed", source_base_fleet_sha256=before[FLEET],
        source_base_model_register_sha256=before[REGISTER], previous_26_site_D_to_E_corrections_preserved=True,
        reviewed_unchanged_control_fleet_ids=reviewed_unchanged, crosswalks=evidence,
        source_hashes={p.relative_to(ROOT).as_posix(): expected for p, expected in PINNED.items()})
    (output / "immutable_site_legacy_crosswalk.json").write_text(json.dumps(crosswalk, indent=2) + "\n")
    write(output / "source_manifest.csv", [dict(path=p.relative_to(ROOT).as_posix(), sha256=before[p]) for p in dependencies])
    require(all(sha(p) == before[p] for p in dependencies), "Frozen source changed during repair")
    result = dict(passed=True, status="combined_source_confirmed_mapping_repair_created", created_utc=datetime.now(timezone.utc).isoformat(),
        checkout_HEAD_at_creation=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        inventory_rows=len(new_fleet), model_generator_rows=len(new_model), changed_inventory_rows=len(changed_units),
        source_zone_changes=zone_changes, moved_inventory_rows=bus_changes, changed_admitted_model_rows=len(active_changed),
        moved_admitted_model_rows=len(active_moved), unchanged_reviewed_Batavia_controls=2,
        changed_fleet_field_cells=len(changes), changed_model_field_cells=len(model_changes),
        Lewiston_inventory_rows=12, Lewiston_active_model_rows=11, previous_26_hydro_site_corrections_preserved=True,
        fleet_register_path=(output / "fleet_register.csv").relative_to(ROOT).as_posix(),
        fleet_register_sha256=sha(output / "fleet_register.csv"),
        model_generator_register_path=(output / "model_generator_register.csv").relative_to(ROOT).as_posix(),
        model_generator_register_sha256=sha(output / "model_generator_register.csv"),
        all_unit_identity_capacity_admission_prior_and_dispatch_values_unchanged=True,
        no_physical_terminal_or_hourly_unit_dispatch_claim=True, no_numeric_artifact_copies=True,
        original_builders_or_outputs_modified=False, all_input_hashes_unchanged=True, no_power_flow_run=True)
    (output / "repair_receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT)
    print(json.dumps(build(parser.parse_args().output), indent=2))
