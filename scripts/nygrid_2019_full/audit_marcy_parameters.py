"""Verify the released Marcy South rows and reproduce the paper's arithmetic.

Read-only with respect to every electrical/thermal model. Writes a separate
audit, not replacement R/X/B values or a physical-conductor qualification.
Run from the repository root: python scripts/nygrid_2019_full/audit_marcy_parameters.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tmp/nygrid_2019_reproduction/upstream"
OUT = ROOT / "output/marcy_south_parameter_audit"
PIN = "47698b6c7823ae7b1bc6935e5601d5b64b8f918e"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proxy_distance_miles(a: dict, b: dict) -> float:
    lat1, lat2 = math.radians(float(a["ycoord"])), math.radians(float(b["ycoord"]))
    dlat = lat2 - lat1
    dlon = math.radians(float(b["xcoord"]) - float(a["xcoord"]))
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 3958.7613 * 2 * math.asin(math.sqrt(h))


def audit(paper: Path) -> dict:
    manifest = json.loads((ROOT / "output/nygrid_2019/upstream_manifest.json").read_text())
    assert manifest["commit"] == PIN
    inputs = []
    for relative in ["modifyMPC.m", "Data/npcc.mat", "Data/npcc.csv"]:
        record = next(r for r in manifest["files"] if r["path"] == relative)
        path = SOURCE / relative
        assert sha(path) == record["sha256"], f"Pinned input changed: {relative}"
        inputs.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)})
    source = (SOURCE / "modifyMPC.m").read_text(encoding="utf-8")
    raw = loadmat(SOURCE / "Data/npcc.mat", simplify_cells=True)["mpc"]
    base = float(raw["baseMVA"])
    assert base == 100
    with (SOURCE / "Data/npcc.csv").open(encoding="utf-8-sig", newline="") as stream:
        metadata = {int(r["idx"]): r for r in csv.DictReader(stream)}
    saved_path = ROOT / "output/nygrid_2019_full_stage1/full_year.mat"
    saved = loadmat(saved_path, simplify_cells=True,
                    variable_names=["base_case", "full_pre_hvdc_case", "reduced_final_case"])
    inputs.append({"path": saved_path.relative_to(ROOT).as_posix(), "sha256": sha(saved_path)})
    rows = []
    for variable, length, f, t in [("newlineEG2", 137, 43, 38), ("newlineEG", 47, 38, 77)]:
        match = re.search(r"\b" + variable + r"\s*=\s*\[([^\]]+)\]", source)
        assert match is not None
        branch = np.fromstring(match.group(1), sep=" ")
        assert len(branch) == 13 and np.array_equal(branch[:2], [f, t])
        assert not np.any(np.all(raw["branch"][:, :2] == [f, t], axis=1))
        assert not np.any(np.all(raw["branch"][:, :2] == [t, f], axis=1))
        kvs = [float(raw["bus"][raw["bus"][:, 0] == bus_id, 9][0]) for bus_id in [f, t]]
        assert kvs == [345, 345]
        zbase = kvs[0] ** 2 / base
        x_literal = length * 0.371 / zbase
        x_catalog_example = length * (0.0703 * 5.28) / zbase
        row = {"segment": f"{f}-{t}", "from_bus": f, "to_bus": t,
               "from_name": metadata[f]["name"], "to_name": metadata[t]["name"],
               "from_zone": metadata[f]["zone"], "to_zone": metadata[t]["zone"],
               "nominal_kv": kvs[0], "base_mva": base, "zbase_ohm": zbase,
               "paper_length_miles": length, "paper_x_coefficient_ohm_mile_inferred_units": 0.371,
               "x_formula_literal_pu": x_literal, "x_formula_rounded_4dp": round(x_literal, 4),
               "x_code_pu": branch[3], "x_code_minus_formula_pu": branch[3] - x_literal,
               "x_code_relative_difference_pct": 100 * (branch[3] - x_literal) / x_literal,
               "r_code_pu": branch[2], "r_code_ohm": branch[2] * zbase,
               "r_code_per_paper_mile_ohm": branch[2] * zbase / length,
               "b_code_pu": branch[4], "rate_a_mva": branch[5], "rate_b_mva": branch[6],
               "rate_c_mva": branch[7], "tap_raw": branch[8], "phase_shift_deg": branch[9],
               "status": branch[10], "angle_min_deg": branch[11], "angle_max_deg": branch[12],
               "manufacturer_reference_term_example_x_pu": x_catalog_example,
               "manufacturer_example_rounded_4dp": round(x_catalog_example, 4),
               "proxy_coordinate_straight_distance_miles": proxy_distance_miles(metadata[f], metadata[t]),
               "source_line": source[:match.start()].count("\n") + 1,
               "physical_conductor_verified": False, "physical_route_mapping_verified": False}
        for name in ["full_pre_hvdc_case", "base_case", "reduced_final_case"]:
            matrix = np.atleast_2d(saved[name]["branch"])
            found = np.flatnonzero(np.all(matrix[:, :2] == [f, t], axis=1))
            assert len(found) == 1 and np.array_equal(matrix[found[0], :13], branch)
            row[name + "_branch_row"] = int(found[0] + 1)
        rows.append(row)
    assert paper.is_file(), "Pass the supplied final paper PDF using --paper"
    result = {"verified_on": "2026-10-09", "upstream_commit": PIN,
              "arithmetic_status": "close_approximate_agreement_not_exact_rounding_for_47_mile_segment",
              "maximum_x_relative_difference_pct": max(abs(r["x_code_relative_difference_pct"]) for r in rows),
              "all_three_saved_stages_preserve_source_rows": True,
              "resistance_derivation_found": False, "charging_derivation_found": False,
              "physical_ampacity_supplied": False, "exact_reference_43_recovered": False,
              "manufacturer_match_scope": "Bobolink reference-spacing value is a numerical cross-check; installed conductor and author selection remain unverified",
              "geometry_scope": "proxy-coordinate straight distances are a mismatch diagnostic, not surveyed routes",
              "physical_line_parameters_validated": False, "models_modified": False,
              "paper": {"path": str(paper.resolve()), "sha256": sha(paper),
                        "pdf_page": 7, "journal_page": 3299, "equation": 10},
              "inputs": inputs, "rows": rows}
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "parameter_recalculation.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (OUT / "audit_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper", type=Path, default=Path.home() / "Downloads" /
        "An-Open-Source-Representation-for-the-NYS-Electric-Grid-to-Support-Power-Grid-and-Market-Transition-Studies.pdf")
    result = audit(parser.parse_args().paper)
    print(json.dumps({key: result[key] for key in ["arithmetic_status", "maximum_x_relative_difference_pct",
                    "all_three_saved_stages_preserve_source_rows", "physical_line_parameters_validated", "models_modified"]}, indent=2))
