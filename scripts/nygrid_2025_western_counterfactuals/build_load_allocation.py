"""Seal and build within-A/B historical load-share counterfactuals.

Only the source-defined bus allocation changes. Both zonal P/Q totals, every
other bus load, native/external generation, bounds, six controlled transfers
and the fixed8651-hour comparison cohort are preserved. No observed internal
interface file is opened. Linear response gives a priori bounds on every
nonnegative within-zone redistribution, without an annual power-flow replay.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.linalg import lu_factor, lu_solve

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_western_counterfactuals"
WEST = ROOT / "output/nygrid_2025_western_audit"
DISPATCH = ROOT / "output/nygrid_2025_dispatch/dispatch"
OPERATING = ROOT / "output/nygrid_2025_inputs/model"
UPSTREAM = ROOT / "tmp/nygrid_2019_reproduction/upstream/Data"
SLIM = ROOT / "output/nygrid_2025_slim/network/network_cases.mat"
PAR = ROOT / "output/nygrid_2025_par_controls/controls/inputs.npz"
BASE_REPLAY = WEST / "replay/dated_combined.mat"
BASE_PG = WEST / "dispatch/all_boundary_actual_dispatch.mat"
MASK = WEST / "replay/paired_common_mask.npy"
GLOBAL_PLAN = OUT / "design/experiment_plan.json"
MODES = {"load_original_A": ["A"], "load_original_B": ["B"], "load_original_AB": ["A", "B"]}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def close(a, b, label, tol=1e-9):
    a, b = np.asarray(a), np.asarray(b)
    require(a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all(), label + ": invalid axes/values")
    error = float(np.max(abs(a - b), initial=0.))
    require(error <= tol, label + ": " + str(error))
    return error


def verify_manifest(path, required):
    obj = json.loads(Path(path).read_text())
    rows = obj.get("entries", obj.get("dependencies", []))
    if not rows and isinstance(obj.get("files"), list):
        rows = obj["files"]
    by_path = {str(r["path"]).replace("\\", "/"): r["sha256"] for r in rows}
    for item in required:
        rel = item.relative_to(ROOT).as_posix()
        require(rel in by_path and sha(item) == by_path[rel], "Missing/changed immutable dependency: " + rel)


def source_shares(old, released, allocation, raw_bus):
    records, zones = [], {}
    require(np.array_equal(old.idx, released.idx) and np.array_equal(old.zone, released.zone), "Original/released bus identity zones differ")
    for zone in ["A", "B"]:
        rows = old[old.zone.eq(zone)].sort_values("idx")
        new = released.set_index("idx").loc[rows.idx]
        original = rows.sumLoadP0.clip(lower=0).to_numpy(float)
        paper = new.sumLoadP0.clip(lower=0).to_numpy(float)
        require(original.sum() > 0 and paper.sum() > 0, "Undefined source zone allocation")
        old_w, new_w = original / original.sum(), paper / paper.sum()
        ids = rows.idx.to_numpy(int)
        require(np.array_equal(raw_bus[ids - 1, 0], ids), "Raw MAT bus axis differs")
        raw = np.maximum(raw_bus[ids - 1, 2], 0)
        close(raw / raw.sum(), old_w, "Original NPCC CSV/MAT load shares", 1e-14)
        delivered = allocation.set_index("bus_id").loc[ids]
        close(delivered.weight.to_numpy(float), new_w, "Delivered npcc_new allocation", 1e-14)
        require(delivered.zone.eq(zone).all() and delivered.allocation_policy.eq("paper_npcc_new_positive_load_share").all(), "Unexpected delivered load policy")
        zones[zone] = dict(bus_ids=ids, original_weights=old_w, released_weights=new_w)
        for i, row in enumerate(rows.itertuples()):
            records.append(dict(zone=zone, bus_id=int(row.idx), bus_name=row.name, voltage_kv=float(row.Vn),
                original_npcc_sumLoadP0=float(original[i]), released_npcc_new_sumLoadP0=float(paper[i]),
                original_weight=float(old_w[i]), released_baseline_weight=float(new_w[i]),
                source_weight_difference=float(old_w[i] - new_w[i]),
                weights_are_observed_2025_bus_loads=False))
    require(np.array_equal(zones["A"]["original_weights"], zones["A"]["released_weights"]), "Expected source-defined ZoneA identity changed")
    require(np.array_equal(zones["B"]["bus_ids"], [52, 53, 62]), "ZoneB retained bus set changed")
    close(zones["B"]["original_weights"], [0, 1, 0], "Original ZoneB distribution", 0)
    return zones, records


def load_response(case, operator, bus_ids):
    """Linear response to moving1modelMW of load from first bus to each bus.

    The affine phase/source terms cancel. All original four DC schedules and
    the two ideal PAR transfers have zero perturbation. No baseline PG or
    measured/scored interface value enters this linear solve.
    """
    bus = np.asarray(case["bus"])
    branch = np.asarray(case["branch"]).copy()
    require(np.array_equal(branch[210, :2], [48, 100]), "PAR representation identity differs")
    branch[210, 10] = 0
    lookup = {int(v): j for j, v in enumerate(bus[:, 0])}
    C = np.zeros((len(branch), len(bus)))
    for i, row in enumerate(branch):
        C[i, lookup[int(row[0])]] = 1
        C[i, lookup[int(row[1])]] -= 1
    tap = np.where(branch[:, 8] == 0, 1., branch[:, 8])
    active = branch[:, 10] == 1
    k = np.zeros(len(branch)); k[active] = float(case["baseMVA"]) / (branch[active, 3] * tap[active])
    B = C.T @ (k[:, None] * C)
    reference = np.flatnonzero(bus[:, 1] == 3)
    require(len(reference) == 1, "Reference bus is not unique")
    nonref = np.flatnonzero(bus[:, 1] != 3)
    rhs = np.zeros((len(bus), len(bus_ids)))
    for j, bid in enumerate(bus_ids):
        rhs[lookup[int(bus_ids[0])], j] += 1
        rhs[lookup[int(bid)], j] -= 1
    theta = np.zeros_like(rhs)
    theta[nonref] = lu_solve(lu_factor(B[np.ix_(nonref, nonref)]), rhs[nonref])
    residual = close(B @ theta, rhs, "Balanced unit-relocation linear equations", 1e-10)
    return np.asarray(operator) @ theta, residual


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    inputs = OUT / "inputs"; analysis = OUT / "load_analysis"
    inputs.mkdir(exist_ok=True); analysis.mkdir(exist_ok=True)
    require(not (inputs / "load_receipt.json").exists(), "Existing sealed load deliverable must be preserved")
    global_plan = json.loads(GLOBAL_PLAN.read_text())
    require(global_plan["fixed_hours"] == 8651 and set(global_plan["load"]["candidates"]) == {name.removeprefix("load_") for name in MODES},
            "Global sealed design differs from source-defined load candidates")
    require(global_plan["constraints"]["no_internal_flow_fitting"] and global_plan["constraints"]["no_original_artifact_changes"], "Global preservation/fit constraints differ")
    verify_manifest(GLOBAL_PLAN, [BASE_REPLAY, BASE_PG, MASK, SLIM, PAR])
    source_manifest = ROOT / "output/nygrid_2019/upstream_manifest.json"
    source_records = json.loads(source_manifest.read_text())["files"]
    for name in ["npcc.csv", "npcc_new.csv", "npcc.mat"]:
        expected = next(r["sha256"] for r in source_records if r["path"] == "Data/" + name)
        require(sha(UPSTREAM / name) == expected, "Pinned upstream source changed: " + name)
    # Check only numerical dependencies; unrelated user-edited reports are not touched.
    verify_manifest(WEST / "delivery_manifest.json", [BASE_REPLAY, BASE_PG, MASK, WEST / "corrected/model_generator_register.csv"])
    verify_manifest(ROOT / "output/nygrid_2025_dispatch/delivery_manifest.json", [DISPATCH / "dispatch.mat", DISPATCH / "dispatch_bounds.mat"])
    verify_manifest(ROOT / "output/nygrid_2025_inputs/delivery_manifest.json", [OPERATING / "bus_allocation.csv", OPERATING / "operating_inputs.mat"])
    dependencies = [source_manifest, UPSTREAM / "npcc.csv", UPSTREAM / "npcc_new.csv", UPSTREAM / "npcc.mat",
        BASE_REPLAY, BASE_PG, MASK, WEST / "corrected/model_generator_register.csv", WEST / "replay/provenance.json",
        DISPATCH / "dispatch.mat", DISPATCH / "dispatch_bounds.mat", OPERATING / "bus_allocation.csv",
        OPERATING / "operating_inputs.mat", SLIM, PAR, GLOBAL_PLAN, Path(__file__)]
    before = {p: sha(p) for p in dependencies}
    original = pd.read_csv(UPSTREAM / "npcc.csv", keep_default_na=False)
    released = pd.read_csv(UPSTREAM / "npcc_new.csv", keep_default_na=False)
    allocation = pd.read_csv(OPERATING / "bus_allocation.csv", float_precision="round_trip")
    raw_bus = loadmat(UPSTREAM / "npcc.mat", simplify_cells=True)["mpc"]["bus"]
    zones, weights = source_shares(original, released, allocation, raw_bus)
    d = loadmat(DISPATCH / "dispatch.mat", simplify_cells=True,
        variable_names=["hour_index", "timestamp_utc", "bus_pd", "bus_qd", "dc_pf", "gamma"])
    baseline = loadmat(BASE_REPLAY, simplify_cells=True,
        variable_names=["qualified", "common_scoring_mask", "network_state_ids", "corrected_generator_buses", "gamma", "timestamp_utc"])
    operating = loadmat(OPERATING / "operating_inputs.mat", simplify_cells=True,
        variable_names=["zonal_load_model_mw", "zonal_load_public_mw", "zone_names", "gamma"])
    model = loadmat(SLIM, simplify_cells=True)
    q = np.load(MASK, allow_pickle=False)
    require(q.dtype == bool and q.shape == (8760,) and q.sum() == 8651, "Fixed common8651-hour cohort differs")
    require(np.array_equal(q, np.asarray(baseline["common_scoring_mask"], bool)) and np.asarray(baseline["qualified"], bool)[q].all(), "Baseline comparison mask differs")
    time = np.asarray(d["timestamp_utc"]).astype(str)
    require(np.array_equal(time, np.asarray(baseline["timestamp_utc"]).astype(str)), "Baseline physical UTC axis differs")
    gamma = float(d["gamma"])
    require(gamma == float(baseline["gamma"]) == float(operating["gamma"]) == float(model["gamma"]), "Power scale differs")
    pd0 = np.pad(np.asarray(d["bus_pd"]), ((0, 0), (0, 8)))
    qd0 = np.pad(np.asarray(d["bus_qd"]), ((0, 0), (0, 8)))
    require(pd0.shape == qd0.shape == (8760, 148) and np.isfinite(pd0).all() and np.isfinite(qd0).all(), "Baseline load matrices invalid")
    zone_p, zone_q = {}, {}
    for zone, definition in zones.items():
        positions = definition["bus_ids"] - 1
        require(np.array_equal(model["kept_bus_ids"][positions], definition["bus_ids"]), "Retained A/B positional identity changed")
        zone_p[zone] = pd0[:, positions].sum(axis=1)
        zone_q[zone] = qd0[:, positions].sum(axis=1)
        zi = list(np.asarray(operating["zone_names"]).astype(str)).index(zone)
        close(zone_p[zone], operating["zonal_load_model_mw"][:, zi], "Observed zone total preserved")
        close(pd0[:, positions], zone_p[zone][:, None] * definition["released_weights"], "Baseline uses npcc_new load shares")
        close(qd0[:, positions], pd0[:, positions] * np.tan(np.arccos(.98)), "Frozen NY0.98PF assumption")
    plan = dict(schema_version=1, experiment="within_zone_A_B_load_allocation_only",
        source_defined_before_posthoc_scoring=True, no_internal_interface_observation_access=True,
        baseline="final western dated_combined with all4actual regional imports and six fixed transfer records",
        baseline_replay=BASE_REPLAY.relative_to(ROOT).as_posix(), baseline_generation=BASE_PG.relative_to(ROOT).as_posix(),
        fixed_cohort=dict(hours=8651, file=MASK.relative_to(ROOT).as_posix(), sha256=before[MASK]),
        baseline_share_source="pinned released Data/npcc_new.csv positive sumLoadP0 shares, verified against delivered2025 allocation",
        alternative_share_source="pinned original Data/npcc.csv positive sumLoadP0 shares, independently agreeing with raw npcc.mat PD shares",
        scenarios=[dict(name=name, changed_zones=change, file=(inputs / (name + ".npz")).relative_to(ROOT).as_posix()) for name, change in MODES.items()],
        expected_source_aliases={"load_original_A": "baseline_exact_noop", "load_original_AB": "load_original_B_exact_alias"},
        QD_rule="Preserve each zone's frozen hourly totalQD and distribute by the same counterfactual P weights; baseline0.98PF remains; no AC feasibility claim",
        allowed_changes="Only within-A/B bus PD/QD distribution. No transfers of load between zones.",
        preserved=["observed hourly ZoneA andB totals", "all other busPD/QD", "all native and28external generator PG",
            "all native bounds/availability", "original4DC schedules", "both P34 transfers", "all148buses and branch parameters"],
        extreme_bound=dict(method="Linear response over nonnegative load-share simplexes on all8A and3B retained buses",
            zones={zone: definition["bus_ids"].tolist() for zone, definition in zones.items()},
            bus_load_capacity_constraints_assumed=False, purpose="Conservative algebraic maximum; not a physically observed or thermally feasible load arrangement",
            source_of_objective="Frozen model interface operators only; no observed interface values", annual_power_flow_required=False),
        scope="Historical-layout sensitivity, not a claim of observed2025 nodal loads or a promoted correction",
        dependencies=[dict(path=p.relative_to(ROOT).as_posix(), sha256=value) for p, value in before.items()])
    plan_path = OUT / "load_plan.json"
    require(not plan_path.exists(), "Load plan already sealed; preserve it before changing definitions")
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    plan_sha = sha(plan_path)
    pd.DataFrame(weights).to_csv(analysis / "source_bus_load_weights.csv", index=False)
    artifacts, checks, variant_arrays = [], [], {}
    for name, changed_zones in MODES.items():
        pd_new, qd_new = pd0.copy(), qd0.copy()
        changed_positions = []
        for zone in changed_zones:
            definition = zones[zone]; positions = definition["bus_ids"] - 1
            changed_positions.extend(positions)
            if np.array_equal(definition["original_weights"], definition["released_weights"]):
                continue
            pd_new[:, positions] = zone_p[zone][:, None] * definition["original_weights"]
            qd_new[:, positions] = zone_q[zone][:, None] * definition["original_weights"]
        allowed = np.zeros(148, bool); allowed[changed_positions] = True
        close(pd_new[:, ~allowed], pd0[:, ~allowed], "All other busPD unchanged", 0)
        close(qd_new[:, ~allowed], qd0[:, ~allowed], "All other busQD unchanged", 0)
        zone_errors = []
        for zone, definition in zones.items():
            positions = definition["bus_ids"] - 1
            zone_errors.append(close(pd_new[:, positions].sum(axis=1), zone_p[zone], "ZoneP conservation"))
            zone_errors.append(close(qd_new[:, positions].sum(axis=1), zone_q[zone], "ZoneQ conservation"))
        require((pd_new >= 0).all(), "Counterfactual introduces negative gross load")
        file = inputs / (name + ".npz")
        require(not file.exists(), "Counterfactual load input already exists")
        np.savez_compressed(file, bus_pd=pd_new, bus_qd=qd_new, qualified=q, hour_index=d["hour_index"],
            timestamp_utc=time, bus_ids=model["kept_bus_ids"], gamma=np.array(gamma),
            baseline_generation_file=np.array(BASE_PG.relative_to(ROOT).as_posix()),
            baseline_generation_sha256=np.array(before[BASE_PG]), scenario=np.array(name), load_plan_sha256=np.array(plan_sha))
        artifacts.append(dict(name=name, file=file.relative_to(ROOT).as_posix(), sha256=sha(file), qualified_hours=int(q.sum()),
            scope="Original historical shares in " + "+".join(changed_zones) + "; same-zone totals and all generation/boundaries fixed"))
        checks.append(dict(scenario=name, maximum_zone_PQ_total_error_model_units=max(zone_errors),
            maximum_bus_PD_change_model_mw=float(abs(pd_new[q] - pd0[q]).max()),
            maximum_bus_QD_change_model_mvar=float(abs(qd_new[q] - qd0[q]).max()),
            all_non_target_PD_QD_bit_identical=True, qualified_hours=8651))
        variant_arrays[name] = (pd_new, qd_new)
    require(np.array_equal(variant_arrays["load_original_A"][0], pd0) and np.array_equal(variant_arrays["load_original_A"][1], qd0), "Source-defined A-only no-op failed")
    require(all(np.array_equal(a, b) for a, b in zip(variant_arrays["load_original_B"], variant_arrays["load_original_AB"])), "Source-defined AB/B alias failed")
    pd.DataFrame(checks).to_csv(analysis / "load_preservation_checks.csv", index=False)

    # A priori response/bounds are computed after sealing definitions, without
    # any annual PF or observed internal interface. Fixed generation is absent
    # from the derivative because its perturbation is exactly zero.
    states = np.asarray(baseline["network_state_ids"]).astype(str)
    interfaces = np.asarray(model["interface_names"]).astype(str)
    bounds, gains, predictions = [], [], []
    max_linear_residual = 0.
    for key in sorted(set(states[q])):
        ix = np.flatnonzero(q & (states == key))
        rec = model["recovery"][key.removesuffix("_case")]
        by_zone = {}
        for zone, definition in zones.items():
            response, residual = load_response(model[key], rec["interface_angle_matrix"], definition["bus_ids"])
            max_linear_residual = max(max_linear_residual, residual)
            mean0 = response @ definition["released_weights"]
            by_zone[zone] = (response, mean0)
            for k, label in enumerate(interfaces):
                for j, bid in enumerate(definition["bus_ids"]):
                    gains.append(dict(network_state=key, interface=label, zone=zone, bus_id=int(bid),
                        anchor_bus_id=int(definition["bus_ids"][0]), model_MW_response_per_model_MW_load_relocated=float(response[k, j])))
        for k, label in enumerate(interfaces):
            joint_low = np.zeros(len(ix)); joint_high = np.zeros(len(ix))
            for zone, definition in zones.items():
                response, mean0 = by_zone[zone]
                lo = zone_p[zone][ix] * (response[k].min() - mean0[k]) / gamma
                hi = zone_p[zone][ix] * (response[k].max() - mean0[k]) / gamma
                joint_low += lo; joint_high += hi
                bounds.append(dict(network_state=key, interface=label, zone_scope=zone, qualified_hours=len(ix),
                    min_delta_public_equivalent_mw=float(lo.min()), max_delta_public_equivalent_mw=float(hi.max()),
                    maximum_absolute_delta_public_equivalent_mw=float(max(abs(lo).max(), abs(hi).max())),
                    sensitivity_spread_mw_per_mw=float(np.ptp(response[k])),
                    min_corner_bus_id=int(definition["bus_ids"][np.argmin(response[k])]),
                    max_corner_bus_id=int(definition["bus_ids"][np.argmax(response[k])]),
                    measured_interface_values_used=False, physical_AC_feasibility_claim=False))
            bounds.append(dict(network_state=key, interface=label, zone_scope="A+B", qualified_hours=len(ix),
                min_delta_public_equivalent_mw=float(joint_low.min()), max_delta_public_equivalent_mw=float(joint_high.max()),
                maximum_absolute_delta_public_equivalent_mw=float(max(abs(joint_low).max(), abs(joint_high).max())),
                sensitivity_spread_mw_per_mw=float(max(np.ptp(by_zone[z][0][k]) for z in zones)),
                min_corner_bus_id="separate_zone_corners", max_corner_bus_id="separate_zone_corners",
                measured_interface_values_used=False, physical_AC_feasibility_claim=False))
            for name, changed_zones in MODES.items():
                delta = np.zeros(len(ix))
                for zone in changed_zones:
                    response, _ = by_zone[zone]
                    difference = zones[zone]["original_weights"] - zones[zone]["released_weights"]
                    delta += zone_p[zone][ix] * float(response[k] @ difference) / gamma
                predictions.append(dict(network_state=key, scenario=name, interface=label, qualified_hours=len(ix),
                    mean_delta_public_equivalent_mw=float(delta.mean()), min_delta_public_equivalent_mw=float(delta.min()),
                    max_delta_public_equivalent_mw=float(delta.max()), maximum_absolute_delta_public_equivalent_mw=float(abs(delta).max()),
                    calculation="a_priori_linear_response_only_no_observed_interface_or_annual_PF"))
    pd.DataFrame(gains).to_csv(analysis / "unit_relocation_sensitivities.csv", index=False)
    bound_frame = pd.DataFrame(bounds)
    bound_frame.to_csv(analysis / "extreme_within_zone_load_bounds.csv", index=False)
    pd.DataFrame(predictions).to_csv(analysis / "source_variant_linear_response.csv", index=False)
    grouped = bound_frame[bound_frame.zone_scope.eq("A+B")].groupby("interface").maximum_absolute_delta_public_equivalent_mw.max()
    require(all(sha(p) == value for p, value in before.items()) and sha(plan_path) == plan_sha, "Immutable baseline or sealed plan changed")
    result = dict(passed=True, datasettype="load", dataset_type="load", completed_utc=datetime.now(timezone.utc).isoformat(),
        head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        plan_file=plan_path.relative_to(ROOT).as_posix(), plan_sha256=plan_sha, qualified_hours=8651,
        scenarios=artifacts, baseline_uses_released_npcc_new_shares=True, original_A_is_exact_noop=True,
        original_AB_is_exact_alias_of_original_B=True, zoneA_and_zoneB_PQ_totals_preserved=True,
        all_other_bus_PD_QD_preserved=True, native_and_external_PG_and_all_six_transfers_preserved_by_reference=True,
        hourly_power_flow_or_posthoc_scoring_performed=False, no_internal_interface_observation_access=True,
        a_priori_linear_equation_max_residual_model_mw=max_linear_residual,
        extreme_AB_bounds_public_equivalent_mw={str(k): float(v) for k, v in grouped.items()},
        all_frozen_input_hashes_unchanged=True, unrelated_user_reports_or_annotations_modified=False,
        limitations=["Original and released bus shares are historical layout assumptions, not observed2025 nodal loads.",
            "Extremal redistribution considers a full nonnegative within-zone simplex without bus demand-capacity or AC constraints.",
            "Invariance/bounds apply to this frozen lossless DC network and its frozen interface operators."],
        dependencies=[dict(path=p.relative_to(ROOT).as_posix(), sha256=value) for p, value in before.items()] +
                     [dict(path=plan_path.relative_to(ROOT).as_posix(), sha256=plan_sha)])
    (inputs / "load_receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
