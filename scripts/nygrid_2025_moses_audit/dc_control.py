"""Lossless DC replay with independently supplied retained-branch flow controls.

Controls change the equivalent phase offset, not generation, load, reactance,
or a scored internal interface. Reconstructed shifts are model-equivalent
values and are not claims about observed individual physical PAR tap settings.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.linalg import lu_solve

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/nygrid_2019"))
from replay_dc import network, predict


def phase_response(net, branch_row):
    """Derivative of all flows and angles with respect to one degree of SHIFT."""
    j = int(branch_row) - 1
    if not 0 <= j < len(net["branch"]) or not net["active"][j]:
        raise ValueError("Control requires an active one-based branch row")
    direct = np.zeros(len(net["branch"]))
    direct[j] = -net["base"] * net["b"][j] * np.pi / 180
    nodal = net["incidence"].T @ direct
    angle = np.zeros(len(net["bus"]))
    nonref = net["nonref"]
    angle[nonref] = lu_solve(net["lu"], -nodal[nonref])
    flow = (net["incidence"] @ angle) * (net["base"] * net["b"]) + direct
    if np.max(np.abs(net["incidence"].T @ flow)) > 1e-8:
        raise ValueError("Phase response does not preserve nodal injections")
    if abs(flow[j]) < 1e-8:
        raise ValueError("Flow of this branch is fixed by a cut; phase control is singular")
    return flow, np.rad2deg(angle)


def controlled_predict(case, pd, pg, dc_pf, branch_row, target_flow_mw):
    """Impose an external branch transfer while preserving all input injections."""
    target = np.asarray(target_flow_mw, float).reshape(-1)
    if len(target) != len(pd) or not np.isfinite(target).all():
        raise ValueError("Control target must have one finite value per solved hour")
    net = network(case)
    result = predict(net, pd, pg, dc_pf)
    response, angle_response = phase_response(net, branch_row)
    j = branch_row - 1
    delta_deg = (target - result["flow"][:, j]) / response[j]
    result["flow"] += delta_deg[:, None] * response
    result["angle_deg"] += delta_deg[:, None] * angle_response
    injections = pg @ net["G"] - pd - net["bus"][:, 4] + dc_pf @ net["D"]
    residual = result["flow"] @ net["incidence"] - injections
    result["nodal_residual_mw"] = np.max(np.abs(residual), axis=1)
    result["control_error_mw"] = np.abs(result["flow"][:, j] - target)
    result["equivalent_shift_deg"] = np.asarray(case["branch"])[j, 9] + delta_deg
    if result["nodal_residual_mw"].max() >= 1e-7 or result["control_error_mw"].max() >= 1e-7:
        raise ValueError("Controlled replay failed nodal balance or target-flow equality")
    if np.max(np.abs(result["result_pg"] - pg)) >= 1e-7:
        raise ValueError("Input generation is not already balanced; control cannot use slack correction")
    return result
