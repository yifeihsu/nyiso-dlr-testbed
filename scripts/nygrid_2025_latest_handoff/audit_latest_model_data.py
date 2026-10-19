"""Independently compare the current portable data with frozen numeric inputs.

Reads all profile values and four current structure fixtures. No PF, OPF,
historical model rebuild, or annual numerical solution is performed.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_latest_handoff"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def record(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}


def main():
    checks = []
    def check(name, good, details):
        checks.append({"name": name, "passed": bool(good), "details": details})
    source_files = {
        "dispatch": ROOT / "output/nygrid_2025_dispatch/dispatch/dispatch.mat",
        "bounds": ROOT / "output/nygrid_2025_dispatch/dispatch/dispatch_bounds.mat",
        "western": ROOT / "output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat",
        "network": ROOT / "output/nygrid_2025_western_audit/replay/dated_combined.mat",
        "dover": ROOT / "output/nygrid_2025_dover_parameters/replay/operating_states.mat",
    }
    variables = {
        "dispatch": ["hour_index", "bus_pd", "bus_qd", "dc_pf", "reference_bus", "gamma"],
        "bounds": ["gen_pmin", "gen_pmax"],
        "western": ["gen_pg", "P34_control_targets_model_mw"],
        "network": ["corrected_generator_buses"],
        "dover": ["qualified", "post_full_service", "controls"],
    }
    source = {k: loadmat(path, variable_names=variables[k], simplify_cells=True)
              for k, path in source_files.items()}
    expected = {
        "bus_PD_MW": source["dispatch"]["bus_pd"],
        "bus_QD_MVAr": source["dispatch"]["bus_qd"],
        "generator_PG_MW": source["western"]["gen_pg"],
        "generator_Pmin_MW": source["bounds"]["gen_pmin"],
        "generator_Pmax_MW": source["bounds"]["gen_pmax"],
        "fixed_transfer_PF_MW": np.column_stack((source["dispatch"]["dc_pf"], source["western"]["P34_control_targets_model_mw"])),
        "dover_bank_phase_shift_deg": source["dover"]["controls"]["bounded_x_nominal"]["bank_shift_model_deg"],
    }
    receipt_path = OUT / "model/model_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    model_path = OUT / "model/latest_model.mat"
    model = loadmat(model_path, simplify_cells=True)["model"]
    schema = {}
    for item in receipt["model_files"]:
        path = OUT / "model" / item["name"]
        check("sealed_file_" + item["name"], path.stat().st_size == item["bytes"] and sha(path) == item["sha256"], item)
    for shard in receipt["profile_shards"]:
        path = OUT / "model" / shard["name"]
        profiles = loadmat(path, simplify_cells=True)["profiles"]
        lo, hi = int(shard["first_hour"]) - 1, int(shard["last_hour"])
        check("profile_field_set_" + shard["name"], set(profiles) == set(expected), sorted(profiles))
        for field, array in profiles.items():
            reference = expected[field][lo:hi, :]
            same = array.dtype == reference.dtype and np.array_equal(array, reference, equal_nan=True)
            check("exact_profile_" + field + "_" + str(lo + 1), same,
                  {"hours": [lo + 1, hi], "shape": list(array.shape), "dtype": str(array.dtype),
                   "NaN_count": int(np.isnan(array).sum()), "comparison": "exact numeric values and NaN locations"})
            schema[field] = {"annual_shape": list(expected[field].shape), "shard_shape": list(array.shape), "dtype": str(array.dtype)}
        del profiles
    axis = model["axis"]
    states = np.ones(8760, dtype=np.uint8)
    states[3359:3575] = 2; states[3575:8471] = 3; states[8471:] = 4
    check("hour_state_and_qualification_axes", np.array_equal(axis["hour_index"], np.arange(1, 8761))
          and np.array_equal(axis["state_index"], states)
          and np.array_equal(axis["source_qualified"], source["dover"]["qualified"])
          and int(np.sum(axis["source_qualified"])) == 8651
          and np.array_equal(axis["reference_bus"], source["dispatch"]["reference_bus"])
          and np.array_equal(axis["post_dover_full_service"], source["dover"]["post_full_service"]),
          {"hours": 8760, "qualified": 8651, "state_hour_ranges": [[1, 3359], [3360, 3575], [3576, 8471], [8472, 8760]]})
    external = model["external"]["generator_mask"].astype(bool)
    check("generator_identity_and_power_base", len(external) == 1464 and external.sum() == 28
          and not external[:1436].any() and external[1436:].all()
          and np.array_equal(model["generator_bus_ids"], source["network"]["corrected_generator_buses"])
          and model["baseMVA"] == 100 and model["frequency_Hz"] == 60
          and model["scale_factor_gamma"] == source["dispatch"]["gamma"],
          {"native_rows": 1436, "external_rows": 28, "MVA_base": 100, "frequency_Hz": 60,
           "gamma": float(model["scale_factor_gamma"])})
    fixture_paths = []
    for i, name in enumerate(["pre_may", "may21", "may30", "post_dover"]):
        path = OUT / f"structure_inputs/{name}.mat"; fixture_paths.append(path)
        fixture = loadmat(path, simplify_cells=True); template = model["templates"][i]; policy = model["loss_static"][i]
        # Hourly load, bus type, controls and generator P/Q vary across fixture
        # hours; compare the static electrical structure and identity columns.
        buscols = [0, 4, 5, 6, 9, 10, 11, 12]
        branchcols = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12]
        same = np.array_equal(template["bus"][:, buscols], fixture["bus"][:, buscols])
        same &= np.array_equal(template["branch"][:, branchcols], fixture["branch"][:, branchcols])
        same &= np.array_equal(template["gen"][:, 0], fixture["gen"][:, 0])
        same &= np.array_equal(template["dcline"][:, [0, 1, 2, 15, 16]], fixture["dcline"][:, [0, 1, 2, 15, 16]])
        same &= np.array_equal(model["retained_bus_ids"], fixture["retained_ids"])
        same &= "source_dc" not in template["userdata"] and "userfcn" not in template
        check("current_static_template_" + name, same,
              {"bus_rows": len(template["bus"]), "branch_rows": len(template["branch"]),
               "parent_rows": int(max(template["userdata"]["ac_system"]["branch_parent_row"])),
               "static_columns_exact_numeric_equal": bool(same), "fixture_hour": int(fixture["hour"])})
        keys = ["bus_group", "loss_ownership", "external_gen_group", "generator_share", "HQ", "native"]
        check("loss_static_vectors_" + name, all(np.array_equal(policy[k], fixture[k]) for k in keys), keys)
    passed = all(c["passed"] for c in checks)
    result = {"passed": passed, "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Independent current data-file, complete annual input-array, static structure and loss-vector review",
        "source_model_commit": receipt["source_model_commit"], "check_count": len(checks), "checks": checks,
        "profile_schema": schema, "full_annual_input_arrays_read": True,
        "PF_OPF_or_annual_solution_run": False, "historical_source_files_copied_into_package": False,
        "original_files_modified": False,
        "source_files": [record(path) for path in source_files.values()],
        "current_files": [record(model_path), record(receipt_path), *[record(OUT / "model" / s["name"]) for s in receipt["profile_shards"]]],
        "independent_current_structure_fixtures": [record(path) for path in fixture_paths],
        "audit_script": record(Path(__file__))}
    folder = OUT / "independent"; folder.mkdir(exist_ok=True)
    path = folder / "current_data_review.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "checks": len(checks), "failures": [c for c in checks if not c["passed"]], "profile_schema": schema}))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
