"""Represent observed PAR transfers without inventing physical tap settings.

Two ideal, lossless controlled-transfer records use MATPOWER's dcline container.
They are not physical HVDC links. Original branch211 stays as an inactive
provenance record; this is a representation substitution, not an asserted outage.
"""
from __future__ import annotations

import copy
import numpy as np


def make_controlled_case(case, generator_buses, targets_model_mw, limits_model_mw):
    result = copy.deepcopy(case)
    targets = np.asarray(targets_model_mw, float).reshape(-1)
    limits = np.asarray(limits_model_mw, float).reshape(-1)
    if targets.shape != (2,) or limits.shape != (2,) or not np.isfinite(targets).all():
        raise ValueError("Provide two finite, individually qualified PS33/PS34 targets")
    if not np.isfinite(limits).all() or np.any(limits <= 0) or np.any(abs(targets) > limits + 1e-9):
        raise ValueError("A device target exceeds its necessary nominal-MVA-derived active-power envelope")
    branch = np.asarray(result["branch"], float)
    if not np.array_equal(branch[210, :2], [48, 100]) or branch[210, 10] != 1:
        raise ValueError("Expected the active original Moses48-to-Ontario100 aggregate record")
    gen = np.asarray(result["gen"], float)
    buses = np.asarray(generator_buses, int).reshape(-1)
    if len(buses) != len(gen) or not np.isin(buses, result["bus"][:, 0]).all():
        raise ValueError("Generator identity axis or retained terminal is invalid")
    gen[:, 0] = buses
    branch[210, 10] = 0
    old_dc = np.asarray(result["dcline"], float)
    if old_dc.shape != (4, 17):
        raise ValueError("Expected exactly four frozen source DC records")
    added = np.zeros((2, 17))
    added[:, :3] = [100, 48, 1]
    added[:, 3] = added[:, 4] = targets
    added[:, 7:9] = 1.
    added[:, 9] = added[:, 10] = targets
    result["gen"], result["branch"] = gen, branch
    result["dcline"] = np.vstack([old_dc, added])
    return result


def qualify_targets(public_targets, public_limits):
    """Fail closed at per-device granularity; never clip source measurements."""
    x = np.asarray(public_targets, float)
    limit = np.asarray(public_limits, float).reshape(-1)
    if x.ndim != 2 or x.shape[1] != 2 or limit.shape != (2,):
        raise ValueError("Expected hour-by-two device values and two limits")
    if not np.isfinite(limit).all() or np.any(limit <= 0):
        raise ValueError("Device envelopes must be finite and strictly positive")
    return np.isfinite(x).all(axis=1) & np.all(abs(x) <= limit + 1e-9, axis=1)
