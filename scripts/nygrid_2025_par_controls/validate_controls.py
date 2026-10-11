"""Independent source, DC-equation, full-network recovery and score validation.

The annual checker does not call the production network, solve, controller or
scoring functions. It forms Kirchhoff/branch equations directly from frozen
matrices and verifies every qualified hour. Only the explicit adversarial API
checks import the production controller. Run after final replay publication.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_par_controls"
BASE = ROOT / "output/nygrid_2025_dispatch/dispatch"
SLIM = ROOT / "output/nygrid_2025_slim"
REPAIR = ROOT / "output/nygrid_2025_moses_audit"
FULL = ROOT / "output/nygrid_2025_downstate/network/network_cases.mat"
NAMES = ["DYSINGER EAST", "WEST CENTRAL", "TOTAL EAST", "MOSES SOUTH", "CENTRAL EAST - VC", "UPNY CONED", "SPR/DUN-SOUTH"]
TOL = 1e-7


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def close(a, b, name, tol=TOL, nan=False):
    a, b = np.asarray(a), np.asarray(b)
    require(a.shape == b.shape, name + ": shape mismatch")
    if nan:
        require(np.array_equal(np.isnan(a), np.isnan(b)), name + ": NaN masks differ")
        q = np.isfinite(a) & np.isfinite(b)
    else:
        require(np.isfinite(a).all() and np.isfinite(b).all(), name + ": nonfinite")
        q = np.ones(a.shape, bool)
    e = float(np.max(abs(a[q] - b[q]), initial=0.))
    require(e <= tol, name + ": maximum error " + str(e))
    return e


def equations(case, generator_buses):
    """Construct lossless DC laws without production replay helpers."""
    bus, branch = np.asarray(case["bus"]), np.asarray(case["branch"]).copy()
    require(np.array_equal(branch[210, :2], [48, 100]) and branch[210, 10] == 1, "Original control branch identity changed")
    branch[210, 10] = 0
    ids = bus[:, 0].astype(int)
    lookup = {v: j for j, v in enumerate(ids)}
    require(len(lookup) == len(bus), "Duplicate buses")
    C = np.zeros((len(branch), len(bus)))
    f = np.array([lookup[int(v)] for v in branch[:, 0]])
    t = np.array([lookup[int(v)] for v in branch[:, 1]])
    C[np.arange(len(branch)), f] = 1
    C[np.arange(len(branch)), t] -= 1
    active = branch[:, 10] == 1
    adjacency = csr_matrix((np.ones(2 * active.sum()),
        (np.r_[f[active], t[active]], np.r_[t[active], f[active]])), shape=(len(bus), len(bus)))
    require(connected_components(adjacency, directed=False)[0] == 1, "Residual AC network is disconnected")
    tap = np.where(branch[:, 8] == 0, 1., branch[:, 8])
    require((tap > 0).all() and (branch[active, 3] != 0).all(), "Invalid branch impedance/tap")
    k = np.zeros(len(branch))
    k[active] = float(case["baseMVA"]) / (branch[active, 3] * tap[active])
    phase = -k * np.deg2rad(branch[:, 9])
    G = csr_matrix((np.asarray(case["gen"])[:, 7],
        (np.arange(len(generator_buses)), [lookup[int(v)] for v in generator_buses])), shape=(len(generator_buses), len(bus)))
    old_dc = np.asarray(case["dcline"])
    require(old_dc.shape == (4, 17) and np.all(old_dc[:, 15:17] == 0), "Original source DC count/loss model changed")
    D = np.zeros((6, len(bus)))
    for j, row in enumerate(old_dc):
        D[j, lookup[int(row[0])]] -= row[2]
        D[j, lookup[int(row[1])]] += row[2]
    D[4:, lookup[100]] = -1
    D[4:, lookup[48]] = 1
    return dict(C=C, k=k, phase=phase, G=G, D=D, bus=bus, branch=branch,
        B=C.T @ (k[:, None] * C), nodal_phase=C.T @ phase, lookup=lookup)


def fixture_solve(eq, pd_mw, pg_mw, transfers, ref_index=0):
    injection = pg_mw @ eq["G"] - pd_mw - eq["bus"][:, 4] + transfers @ eq["D"]
    nonref = np.array([j for j in range(len(eq["bus"])) if j != ref_index])
    theta = np.zeros(len(eq["bus"]))
    theta[nonref] = np.linalg.solve(eq["B"][np.ix_(nonref, nonref)], (injection - eq["nodal_phase"])[nonref])
    flow = eq["k"] * (eq["C"] @ theta) + eq["phase"]
    require(np.max(abs(flow @ eq["C"] - injection)) < TOL, "Independent fixture solve KCL failure")
    return theta, flow


def source_checks(inputs, d):
    receipt = json.loads((OUT / "controls/input_receipt.json").read_text())
    for record in receipt["dependencies"] + receipt["outputs"]:
        require(sha(ROOT / record["path"]) == record["sha256"], "Source dependency hash mismatch: " + record["path"])
    direction = json.loads((OUT / "sources/direction/direction_verification_receipt.json").read_text())
    limits = json.loads((OUT / "sources/limits/limits.json").read_text())
    require(json.loads(str(inputs["direction_metadata_json"])) == direction, "Direction metadata differ")
    require(json.loads(str(inputs["limit_metadata_json"])) == limits, "Limit metadata differ")
    require(direction["status"] == "verified_official_direction_for_2025" and direction["sign_convention_effective_date"] == "2024-12-03", "Direction source is not effective for2025")
    require(direction["visual_inspection_complete"] and direction["inspected_pdf_pages"] == [7, 26], "Direction and legend source proof missing")
    require(not direction["sign_selected_using_internal_interface_fit"] and not direction["internal_Moses_observations_used"], "Direction fitted to internal data")
    require([r["ptid"] for r in direction["ptid_directions"]] == [25118, 25119], "Source identity order differs")
    for row in direction["ptid_directions"]:
        require(row["positive_from_control_area"] == "IESO" and row["positive_to_control_area"] == "NYISO"
                and row["raw_to_ontario_to_new_york_multiplier"] == 1 and row["raw_to_model_branch211_multiplier"] == -1,
                "PTID source orientation differs")
    require(not limits["full_physical_PAR_qualification"], "Incomplete equipment evidence promoted to full qualification")
    for row in limits["devices"]:
        require(row["nominal_mva"] == 300. and row["necessary_abs_p_screen_mw"] == 300., "Per-device nominal envelope changed")
        require(row["phase_design_no_load_min_degree"] == -60. and row["phase_design_no_load_max_degree"] == 60., "Hardware source range changed")
        require(not row["phase_bound_applies_to_reduced_equivalent_SHIFT"] and not row["full_P_Q_thermal_capability_verified"]
                and not row["actual_2025_tap_trajectory_verified"] and not row["numeric_tap_to_phase_table_verified"], "Unverified hardware capability promoted")
        require(row["equipment_impedance_pu"] is None and row["normal_operating_active_power_limit_mw"] is None, "Unsupported physical parameter asserted")
    require(np.array_equal(inputs["ptids"], [25118, 25119]), "Input PTIDs differ")
    require(np.array_equal(inputs["timestamp_utc"].astype(str), np.asarray(d["timestamp_utc"]).astype(str)), "UTC source axis mismatch")
    require(float(inputs["gamma"]) == float(d["gamma"]), "Source gamma differs")
    close(inputs["observed_model_mw"], inputs["observed_public_mw"] * float(d["gamma"]), "Gamma exactly once", tol=1e-12, nan=True)
    require(not bool(inputs["hardware_phase_applies_to_equivalent"]) and not bool(inputs["full_P_Q_rating_feasible"]), "Physical limitation flags changed")
    require(bool(inputs["observed_direction_verified"]) and not bool(inputs["schedule_sign_verified"])
            and bool(inputs["schedule_mode_diagnostic"]), "Observed/schedule direction qualification conflated")
    require(np.array_equal(inputs["p_only_limit_public_mw"], [300., 300.]), "Per-device outer envelope mismatch")
    quality = np.asarray(inputs["observed_quality"], bool)
    finite_bound = np.isfinite(inputs["observed_public_mw"]) & (abs(inputs["observed_public_mw"]) <= 300. + 1e-9)
    expected = np.asarray(d["dispatch_qualified"], bool) & quality.all(axis=1) & finite_bound.all(axis=1)
    require(np.array_equal(expected, inputs["observed_replay_qualified"]), "Recomputed source mask differs")
    # Native source values are checked before averaging, including endpoint day.
    raw_path = REPAIR / "exchanges/par_stlawrence_raw_2025.csv.gz"
    raw = pd.read_csv(raw_path)
    require(set(raw.point_id.unique()) == {25118, 25119}, "Native source identities differ")
    native_rows = []
    for ptid, group in raw.groupby("point_id"):
        require(np.isfinite(group.original_flow_mw).all(), "Native point contains nonfinite flow")
        peak = float(abs(group.original_flow_mw).max())
        require(peak <= 300. + 1e-9, "Native-resolution value exceeds the nominal P-only envelope")
        native_rows.append(dict(ptid=int(ptid), records=len(group), maximum_abs_public_mw=peak,
            necessary_abs_P_screen_mw=300., full_P_Q_capability_verified=False))
    require(sum(r["records"] for r in native_rows) == receipt["native_P34_records"], "Native source screen omitted records")
    require(not receipt["internal_interface_observations_read"] and not receipt["sign_or_parameters_fit_to_internal_flows"], "Control source scope contaminated")
    return expected, native_rows


def controller_rejection_tests(model, generator_buses, gamma):
    from controlled_equivalent import make_controlled_case, qualify_targets
    case = model["refined_2025_case"]
    good = make_controlled_case(case, generator_buses, [0., 0.], [300 * gamma] * 2)
    original = case["branch"].copy()
    original[210, 10] = 0
    close(good["branch"], original, "Only passive representation status changes", tol=0)
    close(good["bus"], case["bus"], "All original148 buses retained", tol=0)
    close(good["dcline"][:4], case["dcline"], "Original four DC records retained", tol=0)
    require(np.array_equal(good["gen"][:, 0], generator_buses), "Hydro correction omitted")
    close(good["gen"][:, 1:], case["gen"][:, 1:], "Generator values unchanged by builder", tol=0)
    require(np.array_equal(good["dcline"][4:, :3], [[100, 48, 1], [100, 48, 1]]), "Ideal PAR directions changed")
    close(good["branch"][:, 9], case["branch"][:, 9], "No invented physical SHIFT", tol=0)
    rejected = []
    for label, target, limit in [("positive_over_limit", [301., 0.], [300., 300.]),
                                 ("negative_over_limit", [-301., 0.], [300., 300.]),
                                 ("cancelling_individual_violations", [301., -301.], [300., 300.]),
                                 ("missing_device", [np.nan, 0.], [300., 300.]),
                                 ("infinite_limit", [0., 0.], [np.inf, 300.]),
                                 ("negative_limit", [0., 0.], [-1., 300.])]:
        try:
            make_controlled_case(case, generator_buses, np.array(target) * gamma, np.array(limit) * gamma)
        except ValueError:
            rejected.append(label)
        else:
            raise ValueError("Controller accepted invalid fixture: " + label)
    require(np.array_equal(qualify_targets(np.array([[300., -300.], [301., -301.], [np.nan, 0.]]), [300., 300.]), [True, False, False]), "Per-device qualification or exact bound failed")
    return rejected


def validate():
    folder = OUT / "validation"; folder.mkdir(parents=True, exist_ok=True)
    start = datetime.now(timezone.utc).isoformat()
    provenance = json.loads((OUT / "replay/provenance.json").read_text())
    paths = [ROOT / row["path"] for row in provenance["dependencies"]]
    paths += [ROOT / row["file"] for row in provenance["variants"]]
    paths += [BASE / "dispatch_bounds.mat", FULL, OUT / "controls/inputs.mat",
              OUT / "comparison/interface_summary.csv", OUT / "comparison/interface_monthly.csv",
              ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv", Path(__file__)]
    paths = list(dict.fromkeys(paths))
    before = {p: sha(p) for p in paths}
    for row in provenance["dependencies"]:
        require(before[ROOT / row["path"]] == row["sha256"], "Final replay dependency hash mismatch")
    for row in provenance["variants"]:
        require(before[ROOT / row["file"]] == row["sha256"], "Final replay result hash mismatch")
    require(provenance["passed"] and not provenance["full_physical_operating_limits_verified"]
            and not provenance["PAR_flow_forecast_or_physical_tap_simulation"]
            and not provenance["internal_interface_observations_used"], "Replay qualification flags invalid")
    d = loadmat(BASE / "dispatch.mat", simplify_cells=True,
        variable_names=["hour_index", "timestamp_utc", "dispatch_qualified", "gamma", "bus_pd", "bus_qd", "gen_pg", "dc_pf", "reference_bus"])
    bounds = loadmat(BASE / "dispatch_bounds.mat", simplify_cells=True, variable_names=["gen_pmin", "gen_pmax"])
    inputs = np.load(OUT / "controls/inputs.npz", allow_pickle=False)
    q, native_checks = source_checks(inputs, d)
    model = loadmat(SLIM / "network/network_cases.mat", simplify_cells=True)
    full = loadmat(FULL, simplify_cells=True)
    register = pd.read_csv(REPAIR / "corrected/model_generator_register.csv")
    gen_buses = register.bus_id.to_numpy(int)
    rejected = controller_rejection_tests(model, gen_buses, float(d["gamma"]))
    gamma = float(d["gamma"])
    pg, dc4 = np.asarray(d["gen_pg"]), np.asarray(d["dc_pf"])
    require(np.all(pg[q] >= bounds["gen_pmin"][q] - TOL) and np.all(pg[q] <= bounds["gen_pmax"][q] + TOL), "Corrected frozen dispatch violates its original bounds")
    target = inputs["observed_model_mw"]
    dc6 = np.column_stack([dc4, target])
    pd148 = np.pad(d["bus_pd"], ((0, 0), (0, 8)))
    pd191 = np.pad(d["bus_pd"], ((0, 0), (0, 51)))
    equations_by_state = {}
    rows, fixture_rows = [], []
    variants = {}
    for record in provenance["variants"]:
        topology = record["topology"]
        result = loadmat(ROOT / record["file"], simplify_cells=True)
        variants[topology] = result
        require(np.array_equal(result["qualified"].astype(bool), q), "Replay common mask mismatch")
        require(np.array_equal(np.asarray(result["timestamp_utc"]).astype(str), np.asarray(d["timestamp_utc"]).astype(str)), "Replay UTC axis differs")
        close(result["original_four_dc_pf"], dc4, "Original four DC schedules preserved", tol=0, nan=True)
        require(np.array_equal(result["corrected_generator_buses"], gen_buses), "Replay generator correction differs")
        close(result["par_transfer_model_mw"][q], target[q], "Source per-device target preserved", tol=0)
        close(result["logical_original_branch211_pf"][q], -target[q].sum(axis=1), "Logical original branch transfer", tol=0)
        require(not bool(result["physical_tap_reconstruction_available"]) and int(result["physical_HVDC_devices_added"]) == 0
                and int(result["ideal_PAR_equivalents_added"]) == 2 and bool(result["passive_branch211_is_representation_substitution"]), "False physical equipment/tap claim")
        require("equivalent_shift_deg" not in result, "Fake aggregate physical SHIFT exported")
        for field in ["branch_pf", "bus_va", "interface_pf", "par_transfer_model_mw", "logical_original_branch211_pf"]:
            require(np.isnan(result[field][~q]).all(), "Missing source hour was filled in " + field)
        states = np.asarray(result["network_state_ids"]).astype(str)
        for key in sorted(set(states)):
            ix = np.flatnonzero(q & (states == key))
            if not len(ix):
                continue
            case, full_case = model[key], full[key]
            eq = equations(case, gen_buses)
            eq_full = equations(full_case, gen_buses)
            equations_by_state[key] = eq
            close(case["dcline"], full_case["dcline"], "Original DC records same in full and slim", tol=0)
            theta = np.deg2rad(result["bus_va"][ix])
            flow = theta @ (eq["k"][:, None] * eq["C"]).T + eq["phase"]
            law_error = close(flow, result["branch_pf"][ix], "Every slim branch law")
            injection = pg[ix] @ eq["G"] - pd148[ix] - eq["bus"][:, 4] + dc6[ix] @ eq["D"]
            kcl_error = close(flow @ eq["C"], injection, "Every slim bus KCL")
            close(flow[:, 210], np.zeros(len(ix)), "Inactive passive representation", tol=0)
            rec = model["recovery"][key.removesuffix("_case")]
            full_theta = theta @ np.asarray(rec["angle_lift"]).T + rec["angle_offset"]
            full_flow = full_theta @ (eq_full["k"][:, None] * eq_full["C"]).T + eq_full["phase"]
            full_injection = pg[ix] @ eq_full["G"] - pd191[ix] - eq_full["bus"][:, 4] + dc6[ix] @ eq_full["D"]
            full_kcl = close(full_flow @ eq_full["C"], full_injection, "Recovered full191 KCL")
            retained = np.asarray(rec["retained_full_indices_1based"], int) - 1
            close(full_theta[:, retained], theta, "Retained angles recovered unchanged", tol=1e-10)
            eliminated = np.asarray(rec["eliminated_full_indices_1based"], int) - 1
            close(full_injection[:, eliminated], np.zeros((len(ix), len(eliminated))), "Eliminated43 nodes remain zero injection", tol=0)
            interface_matrix = np.asarray(rec["full_interface_branch_matrix"])
            require(np.all(interface_matrix[:, 210] == 0), "Controlled boundary is accidentally a scored internal interface")
            mapped = full_flow @ interface_matrix.T
            full_if_error = close(mapped, result["interface_pf"][ix], "All7 full191 interface operators")
            angle_if = theta @ np.asarray(rec["interface_angle_matrix"]).T + rec["interface_flow_offset"]
            angle_if_error = close(angle_if, mapped, "Angle operator versus full191 branches")
            rows.append(dict(topology=topology, state=key, hours=len(ix), slim_branch_law_error_model_mw=law_error,
                slim_KCL_error_model_mw=kcl_error, recovered_full191_KCL_error_model_mw=full_kcl,
                full191_interface_error_model_mw=full_if_error, angle_interface_error_model_mw=angle_if_error,
                preserved_original_buses=140, added_retained_buses=8, recovered_interior_buses=43))
    pd.DataFrame(rows).to_csv(folder / "all_hour_equation_checks.csv", index=False)
    pd.DataFrame(native_checks).to_csv(folder / "independent_native_P34_screen.csv", index=False)

    # Recompute every reported metric on the exact same qualified physical hours.
    obs = pd.read_csv(ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv")
    require(np.array_equal(obs.timestamp_utc.to_numpy(str), np.asarray(d["timestamp_utc"]).astype(str)), "Score observation UTC axis differs")
    y = obs[NAMES].to_numpy(float)
    months = pd.to_datetime(obs.timestamp_utc, utc=True).dt.tz_convert("America/New_York").dt.month.to_numpy()
    expected_rows = []
    for topology, result in variants.items():
        for label, path in [(topology + "_frozen_baseline", SLIM / f"replay/topology_{topology}.mat"),
                            (topology + "_confirmed_hydro_repair", REPAIR / f"replay/{topology}_hydro_zone_corrected.mat"),
                            (topology + "_verified_PAR_flows", OUT / f"replay/{topology}_verified_PAR_flows.mat")]:
            values = loadmat(path, simplify_cells=True, variable_names=["qualified", "interface_pf"])
            require(np.asarray(values["qualified"], bool)[q].all(), "Comparison source lacks common hours")
            f = values["interface_pf"] / gamma
            for j, name in enumerate(NAMES):
                for month in range(13):
                    mask = q if month == 0 else q & (months == month)
                    error = f[mask, j] - y[mask, j]
                    require(np.isfinite(error).all(), "Nonfinite score")
                    expected_rows.append(dict(variant=label, month=month, interface=name, hours=int(mask.sum()),
                        mae_public_equivalent_mw=float(abs(error).mean()), rmse_public_equivalent_mw=float(np.sqrt(np.mean(error * error))),
                        bias_public_equivalent_mw=float(error.mean()), wape_percent=float(abs(error).sum() / abs(y[mask, j]).sum() * 100)))
    expected = pd.DataFrame(expected_rows).set_index(["variant", "month", "interface"]).sort_index()
    annual = pd.read_csv(OUT / "comparison/interface_summary.csv")
    monthly = pd.read_csv(OUT / "comparison/interface_monthly.csv")
    require(len(annual) == 42 and len(monthly) == 504, "Annual/monthly score row counts differ")
    actual = pd.concat([annual, monthly]).set_index(["variant", "month", "interface"]).sort_index()
    require(actual.index.is_unique and actual.index.equals(expected.index), "Score identities differ")
    score_error = close(actual[list(expected.columns)].to_numpy(float), expected.to_numpy(float), "Independent scores", tol=1e-9)
    require(~actual.internal_observations_used_to_fit.astype(bool).any(), "Internal scores used for fitting")
    expected.reset_index().to_csv(folder / "independent_all_scores.csv", index=False)

    # Explicit zero and reversed two-device fixtures for the MATLAB check.
    fixtures = []
    for topology, result in variants.items():
        h = int(np.flatnonzero(q)[0])
        key = str(result["network_state_ids"][h])
        eq = equations_by_state[key]
        rec = model["recovery"][key.removesuffix("_case")]
        for label, public in [("zero_both", [0., 0.]), ("counterflow_zero_sum", [100., -100.])]:
            par_model = np.array(public) * gamma
            transfer = np.r_[dc4[h], par_model]
            theta, f = fixture_solve(eq, pd148[h], pg[h], transfer, int(d["reference_bus"][h]) - 1)
            interfaces = np.asarray(rec["interface_angle_matrix"]) @ theta + rec["interface_flow_offset"]
            fixtures.append(dict(topology=topology, label=label, hour_index=h + 1, target_model_mw=par_model,
                                 branch_pf=f, bus_va=np.rad2deg(theta), interface_pf=interfaces))
    savemat(folder / "matlab_fixture_expected.mat", {"fixtures": fixtures}, do_compression=True)
    for p in paths:
        require(sha(p) == before[p], "Input changed during independent validation: " + str(p))
    summary = dict(passed=True, started_utc=start, completed_utc=datetime.now(timezone.utc).isoformat(),
        head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        qualified_hours_each=int(q.sum()), source_gap_hours_each=int((~q).sum()), topology_variants=len(variants),
        hourly_topology_checks=sum(r["hours"] for r in rows), native_P34_records=sum(r["records"] for r in native_checks),
        maximum_slim_KCL_error_model_mw=max(r["slim_KCL_error_model_mw"] for r in rows),
        maximum_slim_branch_law_error_model_mw=max(r["slim_branch_law_error_model_mw"] for r in rows),
        maximum_full191_KCL_error_model_mw=max(r["recovered_full191_KCL_error_model_mw"] for r in rows),
        maximum_full191_interface_error_model_mw=max(r["full191_interface_error_model_mw"] for r in rows),
        annual_score_rows=42, monthly_score_rows=504, maximum_score_difference=score_error,
        invalid_controller_fixtures_rejected=rejected, MATLAB_zero_counterflow_fixtures=len(fixtures),
        original_PG_PD_QD_bounds_and_four_DC_schedules_preserved=True,
        physical_HVDC_devices_added=0, physical_tap_reconstruction_available=False,
        full_physical_P_Q_thermal_or_tap_feasibility_certified=False,
        independent_validator_uses_production_solver=False, internal_observations_only_used_for_score_recalculation=True,
        dependencies=[dict(path=p.relative_to(ROOT).as_posix(), sha256=before[p]) for p in paths])
    (folder / "independent_validation.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
