"""Independent masks, axes, units and current native-zone map data review."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
import numpy as np
from scipy.io import loadmat
from repair_paths import COMPARISON

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "output/nygrid_2025_physical_repair/delivery/map"


def record(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest, "bytes": path.stat().st_size}


def main():
    data_path = OUT / "annual_data.json"
    data = json.loads(data_path.read_text())
    definitions = json.loads((OUT / "interface_definitions.json").read_text())
    reference = np.load(OUT / "interface_flow_reference.npz", allow_pickle=False)
    comparison_path = COMPARISON / "comparison_arrays.npz"
    comparison = np.load(comparison_path, allow_pickle=False)
    model_root = ROOT / "output/nygrid_2025_physical_repair/model"
    model = loadmat(model_root / "latest_model.mat", simplify_cells=True)["model"]
    checks = []
    def check(name, value, details):
        checks.append({"name": name, "passed": bool(value), "details": details})
    hours = data["hours"]
    source = np.array([r["sourceQualified"] for r in hours], bool)
    good = np.array([r["qualified"] for r in hours], bool)
    operating = np.array([r["operatingQualified"] for r in hours], bool)
    check("full_time_interface_zone_axes", [h["hour"] for h in hours] == list(range(1, 8761))
          and [h["timestamp"] for h in hours] == reference["timestamp_utc"].tolist()
          and data["interfaceNames"] == reference["interface_names"].tolist()
          and data["zoneNames"] == list("ABCDEFGHIJK"), {"hours": len(hours), "interfaces": len(data["interfaceNames"]), "zones": len(data["zoneNames"])})
    check("source_equation_and_operating_masks", np.array_equal(source, reference["source_qualified"])
          and np.array_equal(good, reference["qualified"]) and np.array_equal(operating, reference['operating_qualified'])
          and np.array_equal(source, model["axis"]["source_qualified"]),
          {"source_qualified": int(source.sum()), "flow_qualified": int(good.sum()), "operating_qualified": int(operating.sum())})
    expected_states = ["pre_may"] * 3359 + ["may21"] * 216 + ["may30"] * 4896 + ["post_dover"] * 289
    check("effective_date_state_axis", [h["state"] for h in hours] == expected_states, dict(Counter(h["state"] for h in hours)))
    predicted = np.asarray(data["interfaceFlowsModelMW"], float)
    reference_flow = reference["legacy_signed_literal_from"]
    flow_error = float(np.max(np.abs(predicted[good] - reference_flow[good])))
    check("all_default_interface_values_from_independent_reconstruction", flow_error == 0,
          {"maximum_model_MW_error": flow_error, "qualified_hour_interface_values": int(good.sum()) * 7})
    check("failed_and_excluded_interface_values_remain_null", np.isnan(predicted[~good]).all() and np.isfinite(predicted[good]).all(),
          {"unavailable_rows": int((~good).sum()), "zero_filled_rows": int(np.all(predicted[~good] == 0, axis=1).sum())})
    observed = np.asarray(data["observationsPublicMW"], float)
    check("observations_keep_independent_public_availability", np.array_equal(observed, comparison["observed"], equal_nan=True),
          {"all_seven_observations_available_rows": int(np.isfinite(observed).all(axis=1).sum()),
           "model_unavailable_but_some_observation_available_rows": int(np.any(np.isfinite(observed[~good]), axis=1).sum())})
    gamma = float(data["metadata"]["gamma"])
    check("power_scale_and_no_current_rescaling", gamma == float(reference["gamma"]) == definitions["gamma"]
          and data["metadata"]["branchCurrentGammaDivisionApplied"] is False,
          {"gamma": gamma, "public_scale": "model_MW/gamma", "current_rescaling": False})
    native = ~np.asarray(model["external"]["generator_mask"], bool)
    template = model["templates"][3]; policy = model["loss_static"][3]
    bus_row = {int(b): i for i, b in enumerate(template["bus"][:, 0])}
    groups = np.asarray(policy["bus_group"], int)
    generator_groups = np.array([groups[bus_row[int(bus)]] for bus in model["generator_bus_ids"]])
    expected_gross = np.zeros((8760, 11)); expected_generation = expected_gross.copy(); expected_transfer = np.zeros((8760, 6))
    for part, filename in enumerate(["profiles_h0001_4380.mat", "profiles_h4381_8760.mat"]):
        profile = loadmat(model_root / filename, simplify_cells=True)["profiles"]
        sl = slice(part * 4380, (part + 1) * 4380)
        for zone in range(1, 12):
            expected_gross[sl, zone - 1] = profile["bus_PD_MW"][:, groups[:140] == zone].sum(axis=1)
            expected_generation[sl, zone - 1] = profile["generator_PG_MW"][:, native & (generator_groups == zone)].sum(axis=1)
        expected_transfer[sl] = profile["fixed_transfer_PF_MW"]
    zone_data = {name: np.asarray(array, float) for name, array in data["zoneSeriesModelMW"].items()}
    gross_error = float(np.max(np.abs(zone_data["gross"][source] - expected_gross[source])))
    native_error = float(np.max(np.abs(zone_data["generation"][source] - expected_generation[source])))
    check("gross_demand_and_native_generation_match_current_profiles", gross_error < 1e-9 and native_error < 1e-9,
          {"maximum_gross_model_MW_error": gross_error, "maximum_native_generation_model_MW_error": native_error,
           "native_generator_rows": int(native.sum()), "excluded_external_generator_rows": int((~native).sum()),
           "HQ_generator_row_excluded": int(policy["HQ"]), "HQ_is_native": bool(native[int(policy["HQ"]) - 1])})
    check("zone_field_availability_masks", all(np.isnan(zone_data[k][~source]).all() and np.isfinite(zone_data[k][source]).all() for k in ["gross", "generation"])
          and all(np.isnan(zone_data[k][~good]).all() and np.isfinite(zone_data[k][good]).all() for k in ["served", "loss"]),
          {"gross_and_native_generation_mask": "sourceQualified", "served_and_loss_mask": "qualified"})
    served_error = float(np.max(np.abs(zone_data["served"][good] - comparison["NY_served_PD_MW"][good])))
    loss_error = float(np.max(np.abs(zone_data["loss"][good] - comparison["NY_allocated_loss_MW"][good])))
    closure = float(np.max(np.abs(zone_data["gross"][good] - zone_data["served"][good] - zone_data["loss"][good])))
    check("P58_gross_served_and_loss_semantics", served_error < 1e-8 and loss_error < 1e-8 and closure < 1e-8,
          {"maximum_served_model_MW_difference": served_error, "maximum_loss_model_MW_difference": loss_error,
           "maximum_gross_equals_served_plus_loss_residual_MW": closure})
    transfers = np.asarray(data["fixedTransferFlowsModelMW"], float)
    check("fixed_transfer_values_and_input_mask", np.array_equal(transfers[source], expected_transfer[source])
          and np.isnan(transfers[~source]).all() and len(data["fixedTransferNames"]) == 6,
          {"records": 6, "physical_kind": "four original DC and two ideal PAR controls", "mask": "sourceQualified"})
    states = Counter(h["status"] for h in hours)
    expected_statuses=Counter('source_excluded' if not s else 'solution_failed' if not g else 'operating_qualified' if o else 'equation_loss_qualified' for s,g,o in zip(source,good,operating))
    check("failure_statuses_are_distinct_from_source_exclusions", states == expected_statuses
          and all((h["status"] in ['equation_loss_qualified','operating_qualified']) == h["qualified"] for h in hours)
          and all((h["status"] == "source_excluded") == (not h["sourceQualified"]) for h in hours), dict(states))
    meta = data["metadata"]
    check("diagnostic_scope_and_observation_units_disclosed", not meta["physicalP32MeterCorrespondenceCertified"]
          and not meta["reducedCouplingEdgesUsedForInterfaceFlow"] and not meta["failedIteratesShownAsPredictions"]
          and not meta["solverFailureProvesGlobalInfeasibility"] and "Flow(MWH)" in meta["observationUnitPolicy"]
          and "negative storage pumping is preserved" in meta["generationDefinition"],
          {"observations": meta["observationUnitPolicy"], "generation": meta["generationDefinition"]})
    passed = all(c["passed"] for c in checks)
    proof = {"passed": passed, "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Independent current offline-map annual JSON values, masks, axes, units and native-zone semantics",
        "check_count": len(checks), "checks": checks, "model_flow_values_compared": int(good.sum()) * 7,
        "fresh_simulation_run": False, "old_artifacts_modified": False,
        "browser_test_fixtures": {"default_hour": 8508, "default_Moses_South_model_MW": float(predicted[8507, 3]),
            "default_Moses_South_public_scale_MW": float(predicted[8507, 3] / gamma), "default_Moses_arrow": "reverse" if predicted[8507,3]<0 else "positive",
            "source_eligible_failed_hour": int(np.flatnonzero(source & ~good)[0] + 1) if (source & ~good).any() else None,
            "source_excluded_hour": int(np.flatnonzero(~source)[0] + 1)},
        "sources": [record(p) for p in [data_path, OUT / "interface_definitions.json", OUT / "interface_flow_reference.npz", comparison_path,
            model_root / "latest_model.mat", model_root / "profiles_h0001_4380.mat", model_root / "profiles_h4381_8760.mat", Path(__file__)]]}
    (OUT / "independent_annual_data_review.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "checks": len(checks), "failures": [x for x in checks if not x["passed"]], "fixtures": proof["browser_test_fixtures"]}))
    if not passed: raise SystemExit(1)


if __name__ == "__main__": main()
