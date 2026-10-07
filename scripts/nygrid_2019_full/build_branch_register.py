"""Inventory the captured full NYgrid 2019 network without inventing thermal assets.

The current-model register includes every AC row and every explicit DC link.
The separate lineage table retains raw source rows deleted by the released
workflow. A structural candidate is only a place where a separately declared
synthetic overhead experiment could be attached; no row is a verified DLR asset.

Run from any directory:
    python scripts/nygrid_2019_full/build_branch_register.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "output/nygrid_2019_full_stage1"
DEFAULT_SOURCE = ROOT / "tmp/nygrid_2019_reproduction/upstream"
NY_ZONES = frozenset("ABCDEFGHIJK")
PAPER_REPORTED_ORIGINAL_BRANCHES = 233


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict]) -> None:
    require(bool(rows), f"Refusing to write an empty inventory: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def numeric_case(case: dict, label: str) -> dict:
    require(isinstance(case, dict), f"{label} is not a MATPOWER case structure")
    out = {"baseMVA": float(case["baseMVA"])}
    require(out["baseMVA"] > 0, f"{label} has an invalid MVA base")
    for name, width in [("bus", 13), ("branch", 13), ("gen", 10)]:
        value = np.atleast_2d(np.asarray(case[name], dtype=float))
        require(value.shape[1] >= width and np.isfinite(value).all(),
                f"{label}.{name} has invalid dimensions or nonfinite values")
        out[name] = value
    dc = np.asarray(case.get("dcline", np.empty((0, 17))), dtype=float)
    out["dcline"] = dc.reshape(0, 17) if dc.size == 0 else np.atleast_2d(dc)
    require(np.isfinite(out["dcline"]).all(), f"{label}.dcline has nonfinite values")
    ids = out["bus"][:, 0]
    require(np.equal(ids, np.floor(ids)).all() and len(set(ids)) == len(ids),
            f"{label}: bus IDs must be unique integers")
    return out


def template_signature(row: np.ndarray, *, dc_only: bool = False) -> tuple:
    """Electrical-template identity, not evidence of a physical circuit ID.

    Kron reduction preserves X for retained branches but erases R and B. Use
    that explicitly narrower DC signature only for the reduced crosswalk.
    Equal parallel templates are paired in their preserved source row order.
    """
    indices = [0, 1, 3, 8, 9, 10] if dc_only else [0, 1, 2, 3, 4, 8, 9, 10]
    values = [float(row[i]) for i in indices]
    values[indices.index(8)] = 1.0 if row[8] == 0 else float(row[8])
    return tuple(round(value, 12) for value in values)


def match_templates(source: np.ndarray, target: np.ndarray, *, dc_only=False) -> dict[int, int]:
    pools = defaultdict(list)
    for i, row in enumerate(source):
        pools[template_signature(row, dc_only=dc_only)].append(i)
    matches = {}
    for j, row in enumerate(target):
        pool = pools[template_signature(row, dc_only=dc_only)]
        if pool:
            matches[j] = pool.pop(0)
    return matches


def metadata(path: Path, raw: dict, full: dict) -> dict[int, dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        records = list(csv.DictReader(handle))
    required = {"idx", "name", "Vn", "zone", "xcoord", "ycoord"}
    require(bool(records) and required <= set(records[0]), "npcc.csv metadata schema changed")
    output = {}
    for row in records:
        bus_id = int(row["idx"])
        require(bus_id not in output, f"Duplicate npcc.csv bus ID {bus_id}")
        output[bus_id] = row
    for label, case in [("raw", raw), ("full", full)]:
        for bus in case["bus"]:
            bus_id = int(bus[0])
            require(bus_id in output, f"{label} bus {bus_id} missing from npcc.csv")
            require(abs(float(output[bus_id]["Vn"]) - bus[9]) < 1e-9,
                    f"{label} bus {bus_id} base kV disagrees with npcc.csv")
    return output


def stable_key(row: np.ndarray, ordinals: Counter, family: str = "AC") -> str:
    ends = tuple(sorted((int(row[0]), int(row[1]))))
    ordinals[(family, *ends)] += 1
    return f"NYGRID2019:{family}:{ends[0]}:{ends[1]}:P{ordinals[(family, *ends)]:02d}"


def endpoints(row: np.ndarray, meta: dict[int, dict]) -> dict:
    f, t = int(row[0]), int(row[1])
    require(f in meta and t in meta, "Unknown device endpoint in npcc.csv")
    fm, tm = meta[f], meta[t]
    return {
        "from_bus": f, "to_bus": t,
        "from_name": fm["name"], "to_name": tm["name"],
        "from_zone": fm["zone"], "to_zone": tm["zone"],
        "from_kv": float(fm["Vn"]), "to_kv": float(tm["Vn"]),
        "from_metadata_xcoord": fm["xcoord"], "from_metadata_ycoord": fm["ycoord"],
        "to_metadata_xcoord": tm["xcoord"], "to_metadata_ycoord": tm["ycoord"],
        "coordinates_are_surveyed_line_route": 0,
    }


def classify(row: np.ndarray, end: dict, added_aggregate: bool, dc: bool = False) -> dict:
    both_ny = end["from_zone"] in NY_ZONES and end["to_zone"] in NY_ZONES
    voltage_change = abs(end["from_kv"] - end["to_kv"]) > 1e-9
    active = bool(row[2] > 0) if dc else bool(row[10] > 0)
    tap = False if dc else not (abs(row[8]) < 1e-12 or abs(row[8] - 1) < 1e-12)
    shift = False if dc else abs(row[9]) > 1e-12
    positive_r = False if dc else bool(row[2] > 0)
    positive_x = False if dc else bool(row[3] > 0)
    high_voltage = min(end["from_kv"], end["to_kv"]) >= 69
    reasons = []
    for excluded, reason in [
        (dc, "explicit_DC_link"), (not active, "inactive"),
        (not both_ny, "one_or_both_endpoints_outside_NY"),
        (added_aggregate, "released_added_EG_aggregate"),
        (voltage_change, "unequal_endpoint_voltage_bases"),
        (tap, "nontrivial_transformer_tap"), (shift, "phase_shifter"),
        (not dc and not positive_r, "nonpositive_or_unknown_resistance"),
        (not dc and not positive_x, "nonpositive_or_unknown_reactance"),
        (not high_voltage, "below_69kV"),
    ]:
        if excluded:
            reasons.append(reason)
    candidate = not reasons
    return {
        "active": int(active), "both_endpoints_ny": int(both_ny),
        "voltage_changing": int(voltage_change), "nontrivial_tap": int(tap),
        "nonzero_phase_shift": int(shift), "positive_r": int(positive_r),
        "positive_x": int(positive_x), "at_least_69kv": int(high_voltage),
        "released_added_aggregate": int(added_aggregate),
        "structural_thermal_candidate_only": int(candidate),
        "structural_exclusion_reasons": ";".join(reasons),
        "physical_asset_class": ("explicit_DC_link" if dc else
            "added_network_aggregate" if added_aggregate else
            "transformer_like_electrical_record" if voltage_change or tap or shift else
            "unverified_AC_network_record"),
        "physical_verified": 0, "overhead_verified": 0,
        "installed_conductor_verified": 0, "surveyed_route_verified": 0,
        "thermal_model_eligible": 0, "real_DLR_eligible": 0,
        "qualification_scope": "structural_inventory_only_no_thermal_parameters_assigned",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-year", type=Path, default=DEFAULT_OUTPUT / "full_year.mat")
    parser.add_argument("--stage-capture", type=Path, default=DEFAULT_OUTPUT / "captured_stages.mat")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    raw_path, metadata_path = args.source / "Data/npcc.mat", args.source / "Data/npcc.csv"
    raw = numeric_case(loadmat(raw_path, simplify_cells=True)["mpc"], "raw source")
    yearly = loadmat(args.full_year, variable_names=["base_case", "full_pre_hvdc_case", "reduced_final_case"],
                     simplify_cells=True)
    full = numeric_case(yearly["base_case"], "full final")
    pre = numeric_case(yearly["full_pre_hvdc_case"], "full pre-HVDC")
    reduced = numeric_case(yearly["reduced_final_case"], "reduced final")
    stage = loadmat(args.stage_capture, variable_names=["base", "captures"], simplify_cells=True)
    base = numeric_case(stage["base"], "captured modified base")
    captured = stage["captures"]
    first = captured if isinstance(captured, dict) else captured[0]
    reduced_pre = numeric_case(first["reduced_pre_hvdc"], "reduced pre-HVDC")
    require(len(raw["bus"]) == 140 and len(raw["branch"]) == 227,
            "This inventory expects the pinned 140-bus/227-branch raw source")
    require(np.array_equal(np.sort(full["bus"][:, 0]), np.sort(raw["bus"][:, 0]))
            and np.array_equal(np.sort(pre["bus"][:, 0]), np.sort(raw["bus"][:, 0])),
            "Full reconstruction must retain every original 140-bus identity")
    require(len(reduced["bus"]) == 57 and len(full["gen"]) == 271,
            "Unexpected final reduced buses or full generator inventory")
    require(len(pre["branch"]) == 226 and len(full["branch"]) == 225,
            "Unexpected full pre/final branch counts; investigate the released modifications")
    require(len(full["dcline"]) == 4 and len(reduced["branch"]) == 94,
            "Unexpected transferred final devices or reduced network")
    require(np.array_equal(base["branch"][:, :13], pre["branch"][:, :13]),
            "Full pre-HVDC hardware differs from captured modifyMPC hardware")
    meta = metadata(metadata_path, raw, full)

    # Track all source rows, including the three released remote removals.
    raw_match = match_templates(raw["branch"], pre["branch"])
    final_match = match_templates(pre["branch"], full["branch"])
    reduced_match = match_templates(full["branch"], reduced["branch"], dc_only=True)
    reduced_pre_match = match_templates(pre["branch"], reduced_pre["branch"], dc_only=True)
    require(len(raw_match) == 224, "Expected exactly 224 retained raw templates")
    require(len(final_match) == 225, "Every final full AC branch must have a pre-HVDC ancestor")
    removed_raw = sorted(set(range(227)) - set(raw_match.values()))
    require({tuple(raw["branch"][i, :2].astype(int)) for i in removed_raw} ==
            {(84, 116), (87, 115), (90, 114)}, "Unexpected raw source removal")
    added_pre = sorted(set(range(226)) - set(raw_match))
    require({tuple(pre["branch"][i, :2].astype(int)) for i in added_pre} == {(38, 77), (43, 38)},
            "Unexpected additions: only the two released E-G aggregate rows are declared")
    removed_final = sorted(set(range(226)) - set(final_match.values()))
    require(len(removed_final) == 1, "Expected one full branch deletion accompanying final DC links")

    ordinals = Counter()
    origins, pre_to_origin = [], {}
    for i, row in enumerate(raw["branch"]):
        origins.append({"key": stable_key(row, ordinals), "raw": i, "pre": None,
                        "row": row, "added": False})
    for p, r in raw_match.items():
        origins[r]["pre"] = p
        pre_to_origin[p] = r
    for p in added_pre:
        row = pre["branch"][p]
        pre_to_origin[p] = len(origins)
        origins.append({"key": stable_key(row, ordinals), "raw": None, "pre": p,
                        "row": row, "added": True})
    pre_to_final = {p: f for f, p in final_match.items()}
    full_to_reduced = {f: r for r, f in reduced_match.items()}
    pre_to_reduced = {p: r for r, p in reduced_pre_match.items()}
    lineage = []
    for origin in origins:
        p, r = origin["pre"], origin["raw"]
        f = pre_to_final.get(p)
        row = origin["row"]
        lineage.append({
            "branch_key": origin["key"], "raw_source_branch_row": "" if r is None else r + 1,
            "full_pre_hvdc_branch_row": "" if p is None else p + 1,
            "full_final_branch_row": "" if f is None else f + 1,
            "reduced_pre_hvdc_branch_row": "" if p not in pre_to_reduced else pre_to_reduced[p] + 1,
            "reduced_final_branch_row": "" if f not in full_to_reduced else full_to_reduced[f] + 1,
            "from_bus": int(row[0]), "to_bus": int(row[1]),
            "source_disposition": "removed_remote_PJM_IESO_tie_by_modifyMPC" if p is None else
                "removed_AC_row_when_released_DC_links_added" if f is None else
                "released_added_EG_aggregate" if origin["added"] else "retained_raw_electrical_template",
            "raw_lineage_match": "not_in_raw_source" if r is None else
                "oriented_endpoints_R_X_B_effective_tap_shift_status_parallel_source_order",
            "source_has_physical_circuit_identifier": 0,
        })

    register = []
    for f, row in enumerate(full["branch"]):
        p = final_match[f]
        origin = origins[pre_to_origin[p]]
        end = endpoints(row, meta)
        flags = classify(row, end, origin["added"])
        register.append({
            "branch_key": origin["key"], "device_family": "AC", "branch_row": f + 1, "dcline_row": "",
            "raw_source_branch_row": "" if origin["raw"] is None else origin["raw"] + 1,
            "full_pre_hvdc_branch_row": p + 1,
            "reduced_pre_hvdc_branch_row": "" if p not in pre_to_reduced else pre_to_reduced[p] + 1,
            "reduced_final_branch_row": "" if f not in full_to_reduced else full_to_reduced[f] + 1,
            "reduced_final_dcline_row": "",
            **end, "r_pu": row[2], "x_pu": row[3], "b_pu": row[4],
            "rate_a_mva": row[5], "rate_b_mva": row[6], "rate_c_mva": row[7],
            "tap_ratio_raw": row[8], "phase_shift_degrees": row[9],
            "base_mva": full["baseMVA"], "rate_a_zero_means_unconstrained": int(row[5] == 0),
            "electrical_rating_is_verified_thermal_rating": 0, **flags,
        })
    dc_crosswalk = {}
    unused_reduced_dc = set(range(len(reduced["dcline"])))
    for d, row in enumerate(full["dcline"]):
        match = [i for i in sorted(unused_reduced_dc)
                 if np.array_equal(row, reduced["dcline"][i])]
        require(bool(match), "DC link lacks an identical released template in final reduced model")
        dc_crosswalk[d] = match[0]
        unused_reduced_dc.remove(match[0])
        end = endpoints(row, meta)
        register.append({
            "branch_key": stable_key(row, ordinals, "DC"), "device_family": "DC", "branch_row": "", "dcline_row": d + 1,
            "raw_source_branch_row": "", "full_pre_hvdc_branch_row": "",
            "reduced_pre_hvdc_branch_row": "", "reduced_final_branch_row": "",
            "reduced_final_dcline_row": match[0] + 1,
            **end, "r_pu": "", "x_pu": "", "b_pu": "",
            "rate_a_mva": "", "rate_b_mva": "", "rate_c_mva": "",
            "tap_ratio_raw": "", "phase_shift_degrees": "", "base_mva": full["baseMVA"],
            "rate_a_zero_means_unconstrained": "", "electrical_rating_is_verified_thermal_rating": 0,
            **classify(row, end, False, dc=True),
        })

    crosswalk = []
    for r, row in enumerate(reduced["branch"]):
        f = reduced_match.get(r)
        crosswalk.append({
            "device_family": "AC", "reduced_branch_row": r + 1, "reduced_dcline_row": "",
            "from_bus": int(row[0]), "to_bus": int(row[1]),
            "full_branch_row": "" if f is None else f + 1, "full_dcline_row": "",
            "branch_key": "" if f is None else register[f]["branch_key"],
            "raw_source_branch_row": "" if f is None else register[f]["raw_source_branch_row"],
            "mapping_scope": "reduced_equivalent_without_direct_full_template" if f is None else
                "oriented_endpoints_X_effective_tap_shift_status_only_R_B_not_preserved",
            "physical_identity_verified": 0,
        })
    for d, r in dc_crosswalk.items():
        row = full["dcline"][d]
        crosswalk.append({
            "device_family": "DC", "reduced_branch_row": "", "reduced_dcline_row": r + 1,
            "from_bus": int(row[0]), "to_bus": int(row[1]), "full_branch_row": "", "full_dcline_row": d + 1,
            "branch_key": register[len(full["branch"]) + d]["branch_key"], "raw_source_branch_row": "",
            "mapping_scope": "identical_released_DC_template_parallel_source_order", "physical_identity_verified": 0,
        })

    require(len({r["branch_key"] for r in register}) == len(register), "Branch keys are not unique")
    require(len(lineage) == 229 and len(register) == 229 and len(crosswalk) == 98,
            "Incomplete lineage/current-device/reduced-device inventory")
    require(not any(r["real_DLR_eligible"] or r["physical_verified"] for r in register),
            "Structural classification must never create physical DLR qualification")
    discrepancy = {
        "paper_reported_original_npcc_branches": PAPER_REPORTED_ORIGINAL_BRANCHES,
        "released_raw_npcc_mat_branches": len(raw["branch"]),
        "released_raw_minus_paper": len(raw["branch"]) - PAPER_REPORTED_ORIGINAL_BRANCHES,
        "unresolved_count_difference": PAPER_REPORTED_ORIGINAL_BRANCHES - len(raw["branch"]),
        "explanation_status": "unresolved_source_version_difference_no_missing_branches_invented",
        "raw_branch_sha256": sha256(raw_path),
        "released_modifyMPC_deleted_raw_rows": [i + 1 for i in removed_raw],
        "released_modifyMPC_added_aggregate_endpoints": [[int(v) for v in pre["branch"][i, :2]] for i in added_pre],
        "modified_full_pre_hvdc_branches": len(pre["branch"]),
        "final_full_ac_branches": len(full["branch"]), "final_full_dc_links": len(full["dcline"]),
        "final_reduced_ac_branches": len(reduced["branch"]), "final_reduced_dc_links": len(reduced["dcline"]),
        "removed_full_pre_hvdc_branch_rows_for_DC_stage": [i + 1 for i in removed_final],
        "arithmetic": "227 - 3 remote ties + 2 aggregate AC rows - 1 AC-to-DC-stage deletion = 225 final full AC rows; 4 DC links are separate",
    }
    candidates = [r for r in register if r["structural_thermal_candidate_only"]]
    summary = {
        "full_buses": len(full["bus"]), "raw_source_ac_branches": len(raw["branch"]),
        "full_ac_branches": len(full["branch"]), "full_dc_links": len(full["dcline"]),
        "current_device_register_rows": len(register), "source_lineage_rows": len(lineage),
        "reduced_device_crosswalk_rows": len(crosswalk),
        "reduced_ac_rows_with_full_DC_template_match": len(reduced_match),
        "structural_thermal_candidates_only": len(candidates), "real_DLR_eligible_rows": 0,
        "candidates_by_kv": dict(Counter(str(r["from_kv"]) for r in candidates)),
        "rate_a_unconstrained_candidate_rows": sum(r["rate_a_zero_means_unconstrained"] for r in candidates),
        "thermal_parameters_assigned": False, "weather_assigned": False,
        "coordinates_interpretation": "npcc.csv bus metadata only; not surveyed routes or line directions",
        "parallel_identity_policy": "canonical_endpoint_pair_and_ordinal_in_raw_source_order; no physical circuit IDs supplied",
        "reduced_crosswalk_scope": "DC electrical templates only; no claim that reduced R/B or equivalents are physical overhead lines",
        "source_count_discrepancy": discrepancy,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {"branch_register.csv": register, "source_branch_lineage.csv": lineage,
               "reduced_branch_crosswalk.csv": crosswalk}
    for filename, records in outputs.items():
        write_csv(args.output_dir / filename, records)
    for filename, data in [("branch_register_summary.json", summary), ("paper_source_discrepancy.json", discrepancy)]:
        (args.output_dir / filename).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    inputs = [args.full_year, args.stage_capture, raw_path, metadata_path,
              args.source / "modifyMPC.m", args.source / "updateOpCond.m", Path(__file__)]
    manifest = [{"role": "input", "path": str(p.resolve()), "sha256": sha256(p)} for p in inputs]
    for name in [*outputs, "branch_register_summary.json", "paper_source_discrepancy.json"]:
        p = args.output_dir / name
        manifest.append({"role": "output", "path": str(p.resolve()), "sha256": sha256(p)})
    write_csv(args.output_dir / "branch_register_manifest.csv", manifest)
    print(json.dumps({k: summary[k] for k in ["full_ac_branches", "full_dc_links", "source_lineage_rows",
                     "structural_thermal_candidates_only", "real_DLR_eligible_rows"]}, indent=2))


if __name__ == "__main__":
    main()
