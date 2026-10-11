"""Audit retained St Lawrence boundary representation without changing a case.

Historical PERFORM/RAW is used only to determine what it actually represents.
No scored internal interface observations, physical limits, or control signs
are inferred here. Source direction/limits belong to the independent source
audit. All output is new evidence under nygrid_2025_par_controls/representation.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.linalg import lu_factor, lu_solve

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_par_controls/representation"
PERFORM = ROOT / "PERFORM/On Peak 2019 v23_Perform_NY/On Peak 2019 v23"
RAW = PERFORM / "NYISO_onpeak2019_v23_shuntsRgens.RAW"
SOURCE = PERFORM / "nyiso_On_Peak_v23_shunts_as_z_load.m"
ORIGINAL = ROOT / "ENLITEN-Grid-Econ-Data-main/WECC and NPCC Systems/System Matpower Format/NPCC.m"
INVENTORY = ROOT / "output/ny_only_package_a/source_inventory"
SLIM = ROOT / "output/nygrid_2025_slim/network/network_cases.mat"
PAR = ROOT / "output/nygrid_2025_moses_audit/exchanges/par_stlawrence_hourly_2025.csv"
DISPATCH = ROOT / "output/nygrid_2025_dispatch/dispatch/dispatch.mat"
REGISTER = ROOT / "output/nygrid_2025_moses_audit/corrected/model_generator_register.csv"
sys.path.insert(0, str(ROOT / "scripts/nygrid_2025_downstate"))
from build_network import parse_source
sys.path.insert(0, str(ROOT / "scripts/nygrid_2025_moses_audit"))
from dc_control import controlled_predict, network, phase_response, predict


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def json_file(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def raw_transformers():
    lines = RAW.read_text().splitlines()
    i = next(i for i, line in enumerate(lines) if "BEGIN TRANSFORMER DATA" in line) + 1
    rows = []
    while not lines[i].strip().startswith("0"):
        first = next(csv.reader([lines[i]], skipinitialspace=True))
        impedance = next(csv.reader([lines[i + 1]], skipinitialspace=True))
        winding = next(csv.reader([lines[i + 2]], skipinitialspace=True))
        rows.append(dict(raw_line_1based=i + 1, from_bus=int(first[0]), to_bus=int(first[1]),
            third_bus=int(first[2]), circuit_id=first[3].strip(" '"),
            transformer_name=first[10].strip(" '"), r_12=float(impedance[0]), x_12=float(impedance[1]),
            impedance_base_mva=float(impedance[2]), angle_deg=float(winding[2]),
            raw_control_code=int(winding[6]), raw_RMA=float(winding[8]), raw_RMI=float(winding[9]),
            raw_NTP=int(winding[12]), historical_source_only=True))
        i += 4 if int(first[2]) == 0 else 5
    require(len(rows) == 144, "Historical RAW transformer inventory changed")
    return pd.DataFrame(rows), lines


def independent_constrained_dc(case, pd_mw, pg_mw, dc_mw, target):
    """Solve one flow equality with a free branch affine MW source.

    This formulation does not call the phase-response algorithm. It uses
    nodal KCL plus f_j=t in a single augmented linear system. The scalar
    lambda is a branch affine MW offset, not a physical phase/tap setting.
    """
    net = network(case)
    j = 210
    c = net["incidence"][j]
    k = net["base"] * net["b"][j]
    nr, ref = net["nonref"], net["ref"]
    injection = pg_mw @ net["G"] - pd_mw - net["bus"][:, 4] + dc_mw @ net["D"]
    angles = np.zeros_like(pd_mw)
    angles[:, ref] = np.deg2rad(net["bus"][ref, 8])
    rhs = injection - net["phase_bus"]
    rhs_nonref = rhs[:, nr] - angles[:, ref] @ net["B"][np.ix_(nr, ref)].T
    system = np.block([[net["B"][np.ix_(nr, nr)], c[nr, None]],
                       [k * c[None, nr], np.ones((1, 1))]])
    rhs_flow = target - net["phase_branch"][j] - (angles[:, ref] * (k * c[ref])).sum(axis=1)
    solved = lu_solve(lu_factor(system), np.column_stack([rhs_nonref, rhs_flow]).T).T
    angles[:, nr] = solved[:, :-1]
    affine_mw = solved[:, -1]
    flow = (angles @ net["incidence"].T) * (net["base"] * net["b"]) + net["phase_branch"]
    flow[:, j] += affine_mw
    return flow, angles, affine_mw


def scale_fixture():
    """Two mathematically valid scale conventions have different angles.

    This synthetic fixture proves why an unchanged aggregate impedance plus
    scaled MW does not identify physical tap degrees. It does not calibrate
    an actual device or prescribe a new impedance for the retained network.
    """
    incidence = np.array([[1., -1., 0.], [0., 1., -1.], [1., 0., -1.]])
    x = np.array([0.04, 0.07, 0.10])
    physical_phase = np.deg2rad([12., 0., 0.])
    physical_p = np.array([200., -80., -120.])
    gamma = 0.30012075175285535

    def solve(p, reactance, phase):
        k = 100 / reactance
        B = incidence.T @ (k[:, None] * incidence)
        offset = -k * phase
        theta = np.r_[0., np.linalg.solve(B[1:, 1:], (p - incidence.T @ offset)[1:])]
        return theta, k * (incidence @ theta - phase)

    theta, flow = solve(physical_p, x, physical_phase)
    theta_fixed_x, flow_fixed_x = solve(gamma * physical_p, x, gamma * physical_phase)
    theta_scaled_x, flow_scaled_x = solve(gamma * physical_p, x / gamma, physical_phase)
    errors = dict(fixed_x_angle_scaling=float(np.max(abs(theta_fixed_x - gamma * theta))),
                  fixed_x_flow_scaling=float(np.max(abs(flow_fixed_x - gamma * flow))),
                  scaled_x_angle_identity=float(np.max(abs(theta_scaled_x - theta))),
                  scaled_x_flow_scaling=float(np.max(abs(flow_scaled_x - gamma * flow))))
    require(max(errors.values()) < 1e-10, "Power-scale invariance fixture failed")
    return dict(passed=True, gamma=gamma, synthetic_physical_phase_deg=12.,
        same_x_equivalent_model_phase_deg=gamma * 12.,
        x_divided_by_gamma_equivalent_model_phase_deg=12., errors=errors,
        consequence="Neither convention identifies a physical angle for a differently aggregated network",
        no_change_to_operational_impedances=True)


def ideal_transfers(case, pd_mw, pg_mw, dc_mw, device_model_mw):
    """Independent ideal-transfer fixture; dcline is a mathematical container.

    The two new records are NOT physical HVDC devices. No physical rating or
    tap bound is asserted by this fixture. Original branch211 remains present
    but inactive as a representation substitution, not an observed outage.
    """
    modified = copy.deepcopy(case)
    modified["branch"][210, 10] = 0
    count, width = len(case["dcline"]), case["dcline"].shape[1]
    new = np.zeros((2, width))
    new[:, :3] = [100, 48, 1]
    new[:, 7:9] = 1
    # Numerical fixture only; operational limits belong to the source contract.
    new[:, 9:11] = [-1e6, 1e6]
    modified["dcline"] = np.vstack([case["dcline"], new])
    require(np.array_equal(modified["dcline"][:count], case["dcline"]), "Existing DC records changed")
    require(np.array_equal(modified["gen"], case["gen"]), "Input generator matrix changed")
    require(np.array_equal(modified["bus"], case["bus"]), "Input bus matrix changed")
    check = modified["branch"].copy()
    check[210, 10] = case["branch"][210, 10]
    require(np.array_equal(check, case["branch"]), "Original AC records changed beyond explicit representation status")
    result = predict(network(modified), pd_mw, pg_mw, np.column_stack([dc_mw, device_model_mw]))
    result["logical_original_branch211_mw"] = -np.sum(device_model_mw, axis=1)
    return result


def bridge_rejection_fixture():
    """A sole tie cannot independently set flow while its injections stay fixed."""
    bus = np.zeros((2, 13))
    bus[:, 0] = [1, 2]
    bus[:, 1] = [3, 1]
    bus[:, 7] = 1
    bus[:, 9] = 230
    gen = np.zeros((1, 21))
    gen[0, 0] = 1
    gen[0, 7] = 1
    case = dict(baseMVA=100., bus=bus, gen=gen, dcline=np.empty((0, 17)),
        branch=np.array([[1., 2., 0., .1, 0., 100., 100., 100., 1., 0., 1., -360., 360.]]))
    try:
        phase_response(network(case), 1)
    except ValueError as error:
        require("fixed by a cut" in str(error), "Unexpected bridge test failure")
        return dict(passed=True, rejected=True, reason=str(error),
            applicability="Residual AC connectivity is required before replacing a passive branch by ideal transfers")
    raise ValueError("A singular bridge flow control was accepted")


def audit():
    OUT.mkdir(parents=True, exist_ok=True)
    historical = parse_source()
    names = dict(zip(historical["bus"][:, 0].astype(int), historical["bus_name"]))
    nodes = [1230, 1231, 1546, 1547]
    connections = []
    for j, row in enumerate(historical["branch"], 1):
        if any(v in nodes for v in row[:2]):
            connections.append(dict(source_branch_row=j, from_bus=int(row[0]), to_bus=int(row[1]),
                from_name=str(names[int(row[0])]), to_name=str(names[int(row[1])]),
                r_pu=row[2], x_pu=row[3], rate_a_mva=row[5], tap=row[8], shift_deg=row[9],
                status=int(row[10]), historical_source_only=True))
    pd.DataFrame(connections).to_csv(OUT / "historical_moses_massena_connections.csv", index=False)
    transformers, raw_lines = raw_transformers()
    transformers.to_csv(OUT / "historical_RAW_transformers.csv", index=False)
    boundary = pd.read_csv(INVENTORY / "perform_ny_boundary_reconciliation.csv")
    boundary = boundary[boundary.proposed_schedule_group.str.contains("OH|HQ", regex=True)].copy()
    boundary["source_bus_name"] = boundary.source_bus.map(names)
    boundary.to_csv(OUT / "historical_Ontario_HQ_boundary_proxies.csv", index=False)
    candidates = [dict(line=i + 1, text=line) for i, line in enumerate(raw_lines)
                  if any(term in line.lower() for term in ["ps33", "ps34", "saunder", "stlawrence", "st lawrence", "st. lawrence"])]
    source_evidence = dict(historical_vintage=2019, RAW_export_not_2025_operating_proof=True,
        transformers=len(transformers), transformer_control_code_counts={str(k): int(v) for k, v in transformers.raw_control_code.value_counts().items()},
        maximum_absolute_transformer_angle_deg=float(abs(transformers.angle_deg).max()),
        literal_PAR_name_candidates=candidates,
        Ontario_proxy_buses=boundary.loc[boundary.proposed_schedule_group.eq("SCH - OH - NY"), "source_bus"].astype(int).tolist(),
        HQ_proxy_buses=boundary.loc[boundary.proposed_schedule_group.eq("SCH - HQ - NY"), "source_bus"].astype(int).tolist(),
        PS33_PS34_physical_impedances_or_tap_limits_recoverable=False,
        reason="No explicit St Lawrence Ontario PAR corridor exists in the pinned NY-only source; its Ontario proxies are at two western buses")
    json_file("historical_source_scope.json", source_evidence)

    text = ORIGINAL.read_text()
    block = re.search(r"mpc.branch\s*=\s*\[(.*?)\];", text, re.S)[1]
    rows = [line.split("%")[0].strip().rstrip(";") for line in block.splitlines()]
    original_branch = np.array([list(map(float, line.split())) for line in rows if line])
    match = np.flatnonzero((original_branch[:, 0] == 48) & (original_branch[:, 1] == 100))
    require(len(match) == 1, "Original NPCC branch identity is ambiguous")
    n = loadmat(SLIM, simplify_cells=True)
    gamma = float(n["gamma"])
    variants = [str(v) for v in n["variant_names"]]
    sensitivities = []
    response = {}
    for key in variants:
        case = n[key + "_case"]
        branch = case["branch"][210]
        require(np.array_equal(branch[:2], [48, 100]), "Retained control terminals changed")
        require(np.array_equal(branch[2:5], original_branch[match[0], 2:5]), "Original branch R/X/B changed")
        net = network(case)
        flow_response, angle_response = phase_response(net, 211)
        c = net["incidence"][210]
        k = net["base"] * net["b"][210]
        nr = net["nonref"]
        leverage = float(k * c[nr] @ lu_solve(net["lu"], c[nr]))
        closed = -k * (1 - leverage) * np.pi / 180
        require(abs(closed - flow_response[210]) < 1e-10, "Independent derivative formula disagrees")
        response[key + "_case"] = flow_response[210]
        sensitivities.append(dict(state=key, retained_branch_row=211, original_NPCC_branch_row=int(match[0] + 1),
            from_bus=48, to_bus=100, model_base_mva=net["base"], r_pu=branch[2], x_pu=branch[3], tap=branch[8],
            inherited_rate_a_model_mva=branch[5], original_NPCC_rate_a_mva=original_branch[match[0], 5],
            direct_model_mw_per_degree=-k * np.pi / 180, closed_loop_model_mw_per_degree=flow_response[210],
            closed_loop_public_equivalent_mw_per_degree=flow_response[210] / gamma,
            mesh_angle_feedback_fraction=leverage,
            source_physical_rating_inferred=False, source_physical_tap_limit_inferred=False))
    pd.DataFrame(sensitivities).to_csv(OUT / "retained_branch_sensitivity.csv", index=False)

    par = pd.read_csv(PAR)
    qualified_source = par.coverage_qualified.astype(str).str.lower().eq("true").to_numpy()
    records, phase_rows = [], []
    replay_sources = []
    for topology in ["dated", "year_end"]:
        path = ROOT / f"output/nygrid_2025_moses_audit/replay/{topology}_hydro_zone_corrected.mat"
        replay_sources.append(path)
        baseline = loadmat(path, simplify_cells=True)
        baseline_axis = pd.DatetimeIndex(pd.to_datetime(np.asarray(baseline["timestamp_utc"]).astype(str), utc=True))
        source_axis = pd.DatetimeIndex(pd.to_datetime(par.timestamp_utc, utc=True))
        require(baseline_axis.equals(source_axis), "PAR/baseline axes differ")
        mask = qualified_source & np.asarray(baseline["qualified"], bool)
        state_ids = np.asarray(baseline["network_state_ids"]).astype(str)
        denominator = np.array([response[k] for k in state_ids])
        f0 = baseline["branch_pf"][:, 210]
        source = par.combined_raw_mw.to_numpy(float)
        for sign in [1., -1.]:
            target = sign * source * gamma
            phase = (target - f0) / denominator
            qrows = np.flatnonzero(mask)
            rec = dict(topology=topology, raw_to_retained_branch_sign=int(sign), sign_is_selected_here=False,
                hours=int(mask.sum()), baseline_public_mean=float(np.mean(f0[mask] / gamma)),
                source_target_public_mean=float(np.mean(sign * source[mask])),
                equivalent_phase_min_deg=float(np.min(phase[mask])), equivalent_phase_mean_deg=float(np.mean(phase[mask])),
                equivalent_phase_max_deg=float(np.max(phase[mask])), physical_tap_angle_claim=False)
            records.append(rec)
            for label, pos in [("minimum", np.argmin(phase[mask])), ("maximum", np.argmax(phase[mask]))]:
                row = qrows[pos]
                phase_rows.append(dict(**rec, extreme=label, hour_index=int(row + 1), timestamp_utc=par.timestamp_utc.iloc[row],
                    state=state_ids[row], uncontrolled_model_mw=float(f0[row]), target_model_mw=float(target[row]),
                    equivalent_phase_deg=float(phase[row]), gain_model_mw_per_degree=float(denominator[row])))
    pd.DataFrame(records).to_csv(OUT / "equivalent_phase_summary.csv", index=False)
    pd.DataFrame(phase_rows).to_csv(OUT / "equivalent_phase_extremes.csv", index=False)

    dispatch = loadmat(DISPATCH, simplify_cells=True)
    register = pd.read_csv(REGISTER)
    pg = np.asarray(dispatch["gen_pg"])
    loads = np.pad(dispatch["bus_pd"], ((0, 0), (0, 8)))
    dc = np.asarray(dispatch["dc_pf"])
    hour = int(np.flatnonzero(np.asarray(dispatch["dispatch_qualified"], bool))[0])
    # Test targets are numerical algebra fixtures only, not operational limits.
    synthetic_targets_public_mw = np.array([-600., -200., 0., 200., 600.])
    tests, ideal_tests = [], []
    for key in variants:
        case = copy.deepcopy(n[key + "_case"])
        case["gen"][:, 0] = register.bus_id.to_numpy(int)
        count = len(synthetic_targets_public_mw)
        pd_mw = np.repeat(loads[hour, None], count, axis=0)
        pg_mw = np.repeat(pg[hour, None], count, axis=0)
        dc_mw = np.repeat(dc[hour, None], count, axis=0)
        target = synthetic_targets_public_mw * gamma
        result = controlled_predict(case, pd_mw, pg_mw, dc_mw, 211, target)
        f, a, affine = independent_constrained_dc(case, pd_mw, pg_mw, dc_mw, target)
        e = float(np.max(abs(f - result["flow"])))
        ae = float(np.max(abs(np.rad2deg(a) - result["angle_deg"])))
        se = float(np.max(abs(-affine / (100 / 0.1595) * 180 / np.pi - result["equivalent_shift_deg"])))
        require(max(e, ae, se) < 1e-7, "Constrained boundary-flow solve disagrees with phase implementation")
        tests.append(dict(state=key, target_count=count, max_flow_error_model_mw=e,
            max_angle_error_deg=ae, max_equivalent_shift_error_deg=se,
            max_control_error_model_mw=float(result["control_error_mw"].max()),
            max_kcl_error_model_mw=float(result["nodal_residual_mw"].max()),
            input_generation_change_model_mw=float(abs(result["result_pg"] - pg_mw).max()),
            target_values_are_synthetic_not_operational_limits=True))
        # New device orientations100->48 oppose the original branch211.
        # Unequal decompositions of the same aggregate must give equal flows.
        device = np.column_stack([-target / 2 - 5., -target / 2 + 5.])
        ideal = ideal_transfers(case, pd_mw, pg_mw, dc_mw, device)
        keep = np.arange(len(case["branch"])) != 210
        err = float(abs(ideal["flow"][:, keep] - result["flow"][:, keep]).max())
        angle_err = float(abs(ideal["angle_deg"] - result["angle_deg"]).max())
        logical_err = float(abs(ideal["logical_original_branch211_mw"] - result["flow"][:, 210]).max())
        rec = n["recovery"][key]
        mapped_ideal = np.deg2rad(ideal["angle_deg"]) @ np.asarray(rec["interface_angle_matrix"]).T + rec["interface_flow_offset"]
        mapped_phase = np.deg2rad(result["angle_deg"]) @ np.asarray(rec["interface_angle_matrix"]).T + rec["interface_flow_offset"]
        interface_err = float(abs(mapped_ideal - mapped_phase).max())
        require(max(err, angle_err, logical_err, interface_err) < 1e-7, "Ideal-transfer representation is not equivalent")
        require(np.max(abs(ideal["flow"][:, 210])) == 0, "Inactive AC element carries flow")
        ideal_tests.append(dict(state=key, target_count=count, max_other_AC_flow_error_model_mw=err,
            max_angle_error_deg=angle_err, max_logical_original_branch_flow_error_model_mw=logical_err,
            max_seven_interface_error_model_mw=interface_err,
            maximum_generation_change_model_mw=float(abs(ideal["result_pg"] - pg_mw).max()),
            all_148_buses_preserved=True, all_original_branch_records_preserved=True,
            original_four_DC_records_preserved=True, original_branch211_inactive_is_representation_substitution=True,
            two_new_records_are_ideal_PAR_transfers_not_physical_HVDC=True))
    pd.DataFrame(tests).to_csv(OUT / "independent_constrained_solver_checks.csv", index=False)
    pd.DataFrame(ideal_tests).to_csv(OUT / "ideal_transfer_equivalence_checks.csv", index=False)
    json_file("power_scaling_fixture.json", scale_fixture())
    json_file("bridge_rejection_fixture.json", bridge_rejection_fixture())

    recommendation = dict(
        recommended_representation="two_ideal_PAR_controlled_transfer_equivalents_with_retained_passive_branch_inactive",
        retained_branch=dict(row=211, from_bus=48, from_name="MOSES E", to_bus=100, to_name="PHAS"),
        mathematical_variable="two fixed lossless active-power transfers in the dcline mathematical container; not physical HVDC",
        phase_parameter_policy="Do not export an invented aggregate phase as a physical tap; equivalent SHIFT belongs only in separate diagnostic evidence",
        passive_branch_policy="Retain original branch211 record with identical parameters and inactive status as an explicit representation substitution, not an observed physical outage",
        ideal_transfer_direction="100 PHAS -> 48 MOSES E; positive raw source direction must be independently confirmed before promotion",
        logical_aggregate_flow_reporting="AC PF211 is0 for the inactive record; report logical original48->100 transfer separately as -(PF_new33+PF_new34)",
        preserve=["all 140 original buses", "all 8 retained added buses", "original retained branch R/X/B/tap",
            "native and external generation", "load", "total external exchanges", "other branch records",
            "seven fixed internal interface observation operators"],
        source_input_contract=[
            "Resolve PS33/PTID25118 and PS34/PTID25119 direction from independent primary sources.",
            "Keep two source series and their identities; combine only after direction and coverage checks.",
            "Distinguish measured flow from operating setpoint; if flow telemetry is used, label replay as boundary-conditioned.",
            "Check source-established per-device and aggregate limits in PUBLIC MW before applying gamma exactly once.",
            "An MVA nameplate is not a verified active-power operating limit without Q/voltage/context; do not silently substitute.",
            "Reject or separately qualify missing, stale, out-of-bound, or unavailable-device inputs; do not silently clip evidence.",
            "Hourly averages cannot certify 5-minute operating-limit compliance; perform source-resolution checks where data exist.",
            "For confirmed raw Ontario->Moses sign, apply P33_model=gamma*raw33 and P34_model=gamma*raw34 on100->48 ideal transfers; preserve original generation and loads.",
            "Store source provenance, validity mask, bound provenance and maximum target/KCL residual per hour.",
            "Do not compare reconstructed aggregate SHIFT to individual-device physical angle limits.",
            "Do not impose physical tap feasibility or contingency-operating claims without device impedances, discrete tap map, topology and limits.",
            "Nameplate-MVA-derived active-power envelopes are necessary outer bounds only; unknownQ prevents apparent-power qualification.",
            "Keep PAR equivalents out of physical HVDC inventory, new-generation capacity, conductor DLR, and equipment thermal claims.",
            "Verify the residual AC network remains connected when passive branch211 is represented by controlled transfers."
        ],
        explicit_two_PAR_branch_alternative=dict(ready=False,
            missing=["source electrical endpoints on both sides", "per-device R/X and MVA base", "winding orientation",
                     "tap angle map and control sign", "normal and contingency status", "current applicable limits",
                     "defensible projection between source terminals and retained NPCC terminal angles"],
            restriction="Do not duplicate the already retained boundary path or replace its passive admittance with a guessed two-device network.",
            why_parallel_equivalence_is_not_enough="For real parallel devices K=sum(K_i), phi_eq=sum(K_i*phi_i)/K, but this only holds at the same physical terminals. Retained NPCC aggregate endpoints/impedance have not been proven to equal those terminals/parameters."),
        algebra=dict(branch="f = K C theta + q0 + e_j lambda, K=baseMVA/(X*tap)",
            nodal="B theta + C.T q0 + c_j lambda = p, B=C.T K C",
            flow_constraint="K_j c_j.T theta + q0_j + lambda = gamma * t_public",
            ideal_transfer_equivalence="With f211=t fixed, B_without211*theta=p-c211*t; two100->48 injections with P33+P34=-t give the same equation. All other AC flows and angle-based interfaces are identical.",
            equivalent_phase="delta_SHIFT_deg = -lambda/K_j * 180/pi = (target_model - f0_j)/h_jj",
            phase_derivative="h_jj = -K_j * (1 - K_j*c_j.T*B_ref_inverse*c_j) * pi/180",
            current_gain="-3.36964316845 model MW/degree; direct=-10.9425031473; mesh feedback=0.6920592004",
            units="gamma=0.30012075175285535 scales MW once. Impedances and 100MVA model base stay frozen. Output public-equivalent MW=f_model/gamma.",
            scale_caution="If the same physical B were retained, P_model=gamma*P_physical would require phi_model=gamma*phi_physical for proportional solutions; X_model=X_physical/gamma instead preserves angles. Neither identifies physical angles after an unproved network aggregation."),
        tests_required_for_operational_promotion=[
            "Independent signed PTID mapping and source limit checks at native resolution.",
            "Per-device limits before aggregation; invalid source masks remain invalid.",
            "MW scale applied once and invertible output conversion.",
            "All buses, branch parameters and input injections preserved except explicit affine control offsets.",
            "Independent constrained linear solve versus phase-export implementation, including reversed and zero flow.",
            "A bridge/singular control path rejects infeasible fixed-flow requests.",
            "Fresh MATLAB/MATPOWER replay agrees at extrema, DST boundaries and topology states.",
            "All seven interfaces scored only after controls and source sign/limits are frozen."
        ],
        physical_device_feasibility_proved=False,
        internal_interface_observations_read=False,
        source_direction_or_limit_selected_from_model_fit=False)
    json_file("implementation_choice.json", recommendation)
    dependencies = [RAW, SOURCE, ORIGINAL, INVENTORY / "perform_ny_boundary_reconciliation.csv", SLIM, PAR,
                    DISPATCH, REGISTER, Path(__file__), ROOT / "scripts/nygrid_2025_moses_audit/dc_control.py",
                    ROOT / "scripts/nygrid_2025_downstate/build_network.py", ROOT / "scripts/nygrid_2019/replay_dc.py"] + replay_sources
    pd.DataFrame([dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in dependencies]).to_csv(OUT / "source_manifest.csv", index=False)
    result = dict(passed=True, status="representation_audit_complete_source_operating_limit_audit_separate",
        head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        gamma=gamma, historical_transformer_count=len(transformers), historical_explicit_PAR_found=False,
        network_states=len(variants), independent_constrained_test_snapshots=sum(r["target_count"] for r in tests),
        ideal_transfer_test_snapshots=sum(r["target_count"] for r in ideal_tests),
        maximum_ideal_transfer_other_AC_error_model_mw=max(r["max_other_AC_flow_error_model_mw"] for r in ideal_tests),
        maximum_ideal_transfer_seven_interface_error_model_mw=max(r["max_seven_interface_error_model_mw"] for r in ideal_tests),
        maximum_constrained_flow_error_model_mw=max(r["max_flow_error_model_mw"] for r in tests),
        maximum_constrained_angle_error_deg=max(r["max_angle_error_deg"] for r in tests),
        original_case_or_builder_modified=False, observed_internal_interface_data_read=False,
        recommended_representation=recommendation["recommended_representation"])
    json_file("representation_audit.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
