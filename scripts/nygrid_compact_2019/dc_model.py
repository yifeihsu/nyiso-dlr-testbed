"""Small, independent DC solver for fixed bus-injection comparisons.

Inputs and outputs are MW. Positive bus injection supplies the AC network.
Only the designated reference bus balances a mismatch; its adjustment is
returned explicitly. The solver does not know interface observations.
"""
from __future__ import annotations

import numpy as np
from scipy.linalg import lu_factor, lu_solve
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components


class DCModel:
    def __init__(self, bus, branch, base_mva=100.0, reference_bus=74):
        self.bus = np.asarray(bus, dtype=float)
        self.branch = np.asarray(branch, dtype=float)
        self.ids = self.bus[:, 0].astype(int)
        self.lookup = {int(b): k for k, b in enumerate(self.ids)}
        if len(self.lookup) != len(self.ids) or reference_bus not in self.lookup:
            raise ValueError("Bus identities/reference are invalid")
        if not np.isfinite(self.bus).all() or not np.isfinite(self.branch).all():
            raise ValueError("Nonfinite network data")
        self.reference = self.lookup[reference_bus]
        self.other = np.flatnonzero(self.ids != reference_bus)
        self.incidence = np.zeros((len(self.branch), len(self.bus)))
        for k, row in enumerate(self.branch):
            self.incidence[k, self.lookup[int(row[0])]] = 1
            self.incidence[k, self.lookup[int(row[1])]] -= 1
        active = self.branch[:, 10] == 1
        if not np.isin(self.branch[:, 10], [0, 1]).all():
            raise ValueError("Unrecognized branch status")
        if (self.branch[active, 3] == 0).any():
            raise ValueError("Zero active reactance")
        graph = np.abs(self.incidence[active]).T @ np.abs(self.incidence[active])
        if connected_components(csr_matrix(graph), directed=False)[0] != 1:
            raise ValueError("Disconnected network")
        tap = self.branch[:, 8].copy()
        tap[tap == 0] = 1
        if (tap <= 0).any():
            raise ValueError("Nonpositive tap")
        self.b = np.zeros(len(self.branch))
        self.b[active] = base_mva / (self.branch[active, 3] * tap[active])
        self.phase = -self.b * np.deg2rad(self.branch[:, 9])
        self.B = self.incidence.T @ (self.b[:, None] * self.incidence)
        self.lu = lu_factor(self.B[np.ix_(self.other, self.other)])

    def solve(self, injection):
        p = np.atleast_2d(np.asarray(injection, dtype=float))
        if p.shape[1] != len(self.ids) or not np.isfinite(p).all():
            raise ValueError("Invalid bus-injection matrix")
        angle = np.zeros_like(p)
        rhs = p - self.phase @ self.incidence
        angle[:, self.other] = lu_solve(self.lu, rhs[:, self.other].T).T
        flow = (angle @ self.incidence.T) * self.b + self.phase
        exits = flow @ self.incidence
        adjustment = exits[:, self.reference] - p[:, self.reference]
        balanced = p.copy()
        balanced[:, self.reference] += adjustment
        residual = np.max(np.abs(exits - balanced), axis=1)
        if not np.isfinite(flow).all() or np.max(residual) > 1e-7:
            raise ValueError("Independent DC nodal balance failed")
        return dict(flow=flow, angle_deg=np.rad2deg(angle), injection=balanced,
                    slack_adjustment_mw=adjustment, nodal_residual_mw=residual)

    def cut(self, upstream, downstream=None):
        """Signed PF coefficients, including all active crossing branches."""
        up = set(map(int, upstream))
        down = set(map(int, downstream)) if downstream is not None else set(self.ids) - up
        if up & down or not (up | down) <= set(self.ids):
            raise ValueError("Invalid/disjoint cut identities")
        coefficients = np.zeros(len(self.branch))
        for k, row in enumerate(self.branch):
            if row[10] == 0:
                continue
            f, t = int(row[0]), int(row[1])
            if f in up and t in down:
                coefficients[k] = 1
            elif t in up and f in down:
                coefficients[k] = -1
        return coefficients


def map_bus_values(values, source_ids, target_ids):
    values = np.atleast_2d(np.asarray(values, dtype=float))
    source_ids = np.asarray(source_ids, dtype=int)
    target_ids = np.asarray(target_ids, dtype=int)
    target = {b: i for i, b in enumerate(target_ids)}
    result = np.zeros((len(values), len(target_ids)))
    if len(set(source_ids)) != len(source_ids) or len(target) != len(target_ids):
        raise ValueError("Duplicate bus identities")
    if values.shape[1] != len(source_ids):
        raise ValueError("Bus values/identities are misaligned")
    for i, b in enumerate(source_ids):
        if b not in target:
            if np.max(np.abs(values[:, i])) > 1e-9:
                raise ValueError(f"Nonzero injection at missing terminal {b}")
        else:
            result[:, target[b]] = values[:, i]
    if np.max(np.abs(result.sum(axis=1) - values.sum(axis=1))) > 1e-7:
        raise ValueError("Mapping did not preserve total injection")
    return result


def score(predicted, observed):
    predicted, observed = np.asarray(predicted), np.asarray(observed)
    if predicted.shape != observed.shape or not np.isfinite(predicted).all() or not np.isfinite(observed).all():
        raise ValueError("Prediction and observation coverage mismatch")
    error = predicted - observed
    denom = np.abs(observed)
    percentage = np.full_like(error, np.nan)
    np.divide(100 * np.abs(error), denom, out=percentage, where=denom != 0)
    return dict(error_mw=error, absolute_error_mw=np.abs(error), absolute_error_pct=percentage,
                pooled_error_pct=100 * np.abs(error).sum(axis=1) / denom.sum(axis=1),
                worst_interface_error_pct=np.max(percentage, axis=1),
                wrong_direction=(predicted * observed < 0))


def port_injection_map(net, retained_ids):
    """Exact linear elimination of added DC terminals, for a common-port study.

    A map constructed from the compact topology is frozen before it is used
    on another topology. It must not be represented as observed geography.
    """
    retained = np.array([net.lookup[int(b)] for b in retained_ids])
    eliminated = np.array([k for k in range(len(net.ids)) if k not in retained])
    if np.any(net.phase != 0):
        raise ValueError('Port mapping requires a separate phase-offset transformation')
    transform = np.zeros((len(retained), len(net.ids)))
    transform[np.arange(len(retained)), retained] = 1
    inv_ee_er = np.linalg.solve(net.B[np.ix_(eliminated, eliminated)], net.B[np.ix_(eliminated, retained)])
    transform[:, eliminated] = -inv_ee_er.T
    equivalent_B = net.B[np.ix_(retained, retained)] - net.B[np.ix_(retained, eliminated)] @ inv_ee_er
    if np.max(np.abs(transform.sum(axis=0)-1))>1e-10:
        raise ValueError('Port mapping does not preserve net injection')
    return transform, equivalent_B, retained, eliminated
