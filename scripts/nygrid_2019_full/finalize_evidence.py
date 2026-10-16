"""Check and fingerprint the delivered full2019 DC/thermal research evidence.

Does not rerun numerical models or change their values. Generated CSVs use
canonical LF. Initial local capture receipts are historical, not current gates.
"""
from __future__ import annotations

import csv
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2019_full_stage1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def finalize() -> dict:
    for path in OUT.glob("*.csv"):
        data = path.read_bytes()
        if b"\r\n" in data:
            path.write_bytes(data.replace(b"\r\n", b"\n"))
    annual = json.loads((OUT / "full_year_summary.json").read_text())
    loader = json.loads((OUT / "full_loader_validation.json").read_text())
    scope = json.loads((OUT / "synthetic_dlr_scope.json").read_text())
    assert annual["hours"] == 8760
    assert annual["full_year_mat_sha256"] == sha(OUT / "full_year.mat")
    assert annual["max_full_final_nodal_balance_residual_mw"] < 1e-7
    assert annual["reduced_final_equivalence"] is False
    assert loader["passed"] and loader["fresh_matpower_hours"] == 13
    assert loader["max_branch_error_mw"] < 1e-7
    assert scope["thermal_tests_passed"] and scope["fixed_dispatch"]
    for flag in ["observed_weather", "installed_conductors_verified", "ac_feasibility_validated",
                 "economic_redispatch_performed", "dynamic_temperature_time_series", "sag_clearance_validated"]:
        assert scope[flag] is False, flag
    tests = rows(OUT / "synthetic_thermal_tests.csv")
    assert len(tests) == 12 and all(r["passed"] in {"1", "true"} for r in tests)
    register = rows(OUT / "branch_register.csv")
    assert len(register) == 229 and len({r["branch_key"] for r in register}) == 229
    assert all(r["real_DLR_eligible"] == "0" for r in register)
    selection = rows(OUT / "synthetic_dlr_selection.csv")
    included = [r for r in selection if r["included_in_synthetic_screen"] == "1"]
    assert len(included) == 39
    by_key = {r["branch_key"]: r for r in register}
    assert all(by_key[r["branch_key"]]["structural_thermal_candidate_only"] == "1" for r in included)
    assert all(float(by_key[r["branch_key"]]["rate_a_mva"]) == 0 for r in included)
    data = loadmat(OUT / "full_year.mat", variable_names=["branch_pf", "hour_index"])
    flows = np.asarray(data["branch_pf"])
    assert flows.shape == (8760, 225) and np.isfinite(flows).all()
    assert np.array_equal(data["hour_index"].reshape(-1), np.arange(1, 8761))
    caps = rows(OUT / "synthetic_dlr_capacities.csv")
    summaries = rows(OUT / "synthetic_dlr_summary.csv")
    assert len(caps) == 156 and len(summaries) == 4
    for summary in summaries:
        scenario = [r for r in caps if r["scenario_id"] == summary["scenario_id"]]
        assert len(scenario) == 39
        branch_rows = np.asarray([int(r["branch_row"]) - 1 for r in scenario])
        limits = np.asarray([float(r["thermal_dc_proxy_mw"]) for r in scenario])
        assert (limits > 0).all()
        exceeded = np.abs(flows[:, branch_rows]) > limits + 1e-7
        assert int(exceeded.sum()) == int(summary["thermal_exceedance_branch_hours"])
        assert int(exceeded.any(axis=1).sum()) == int(summary["hours_any_thermal_exceedance"])
        assert abs(np.max(np.abs(flows[:, branch_rows]) / limits) -
                   float(summary["max_thermal_proxy_utilization"])) < 1e-9
    verified = 0
    for filename in ["full_year_source_manifest.csv", "branch_register_manifest.csv"]:
        for record in rows(OUT / filename):
            path = Path(record["path"])
            if not path.is_absolute():
                path = ROOT / path
            assert path.is_file() and sha(path) == record["sha256"], str(path)
            verified += 1
    # Generate the current receipt reproducibly after checking capture outcomes.
    # The annual manifest above binds the captured MAT to the annual replay.
    capture_rows = rows(OUT / "capture_inventory.csv")
    assert len(capture_rows) == 13
    for row in capture_rows:
        assert all(row[k] in {"1", "true"} for k in ["full_pf_success", "pre_pf_success", "final_pf_success"])
        assert all(float(v) < 1e-7 for k, v in row.items() if k.startswith("annual_") and "error" in k)
    preparation = json.loads((OUT / "capture_preparation_manifest.json").read_text())
    assert preparation["verified_upstream_files"] == 73 and preparation["verified_reduction_files"] == 20
    assert preparation["transformation_reverses_to_exact_cached_source"]
    current_paths = [OUT / name for name in ["captured_stages.mat", "capture_inventory.csv",
        "capture_preparation_manifest.json", "capture_instrumentation.patch", "capture_run_summary.json",
        "full_loader_validation.csv", "full_loader_validation.json"]]
    current_paths += [ROOT / "scripts/nygrid_2019_full" / name for name in
                     ["prepare_capture.py", "capture_full_stages.m", "validate_full_loader.m"]]
    current_paths += [ROOT / "System Matpower Format/npcc_nygrid_2019_full_dc.m"]
    current = {"receipt_scope": "current capture artifacts and reproducible runner code; execution inputs are bound by preparation and annual source manifests",
               "source_preparation_verified": {"upstream_files": 73, "reduction_files": 20,
                                                "instrumentation_reverse_exact": True},
               "fresh_full_loader_validation": loader,
               "files": [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size,
                          "sha256": sha(p)} for p in current_paths]}
    (OUT / "capture_validation_manifest.json").write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    check = {"verified_utc": datetime.now(timezone.utc).isoformat(), "passed": True,
             "input_and_component_manifest_entries_verified": verified,
             "independent_thermal_exposure_recounts": 4, "annual_hours": 8760,
             "synthetic_branches": 39, "physical_DLR_qualified": False,
             "full_vs_reduced_exact_equivalence": False}
    (OUT / "delivery_checks.json").write_text(json.dumps(check, indent=2) + "\n", encoding="utf-8")
    paths = list((ROOT / "scripts/nygrid_2019_full").glob("*.py"))
    paths += list((ROOT / "scripts/nygrid_2019_full").glob("*.m"))
    paths += [ROOT / "scripts/nygrid_2019_full/README.md", ROOT / "NYGRID_2019_DLR_REBUILD.md",
              ROOT / "System Matpower Format/npcc_nygrid_2019_full_dc.m"]
    ignored = {"delivery_manifest.json", "capture_artifact_manifest.json"}
    paths += [p for p in OUT.iterdir() if p.is_file() and p.name not in ignored]
    thermal = ROOT / "System Matpower Format/NY_Lite"
    paths += [thermal / name for name in ["dlr_conductor_library.m", "dlr_heat_balance.m",
              "dlr_steady_ampacity.m", "dlr_temperature_trace.m", "test_dlr_thermal_model.m",
              "fixtures/dlr_nrel_reference.csv"]]
    receipt = {"scope": "full2019 source reproduction plus derived DC thermal screening",
               "created_utc": check["verified_utc"], "checks": check,
               "files": [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size,
                          "sha256": sha(p)} for p in sorted(set(paths))]}
    (OUT / "delivery_manifest.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return {**check, "delivery_files": len(receipt["files"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    OUT = args.output.resolve()
    assert OUT.is_relative_to(ROOT) and OUT.is_dir(), "Use an existing evidence directory inside this repository"
    print(json.dumps(finalize(), indent=2))
