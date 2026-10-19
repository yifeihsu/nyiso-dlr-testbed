"""Predeclared terminal operators for the seven inherited NY zone cuts.

These are diagnostic legacy cuts, not certified physical NYISO P-32 meters.
All indices exposed in term records are one based; matrix axes are zero based.
No operating-point/P-32 values are used to define membership or convention.
"""
from pathlib import Path
import json
import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
STATES = ("pre_may", "may21", "may30", "post_dover")
CONVENTIONS = ("legacy_signed_literal_from", "oriented_source_side", "oriented_target_side")


def source_case(state):
    if state not in STATES:
        raise ValueError(f"Unknown dated state: {state}")
    if state == "post_dover":
        d = loadmat(ROOT / "output/nygrid_2025_dover_parameters/network/x_nominal.mat", simplify_cells=True)
        return d["full_case"], np.asarray(d["full_bus_zones"]), np.asarray(d["full_branch_keys"]), d
    d = loadmat(ROOT / "output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat", simplify_cells=True)
    return d[f"refined_2025_{state}_case"], np.asarray(d["bus_zones"]), np.asarray(d["branch_keys"]), d


def interface_definitions(state="pre_may"):
    definitions = json.loads((ROOT / "output/nygrid_2025_downstate/replay/interface_definitions.json").read_text())
    full, _, _, _ = source_case(state)
    stored = full["if"]["map"]
    for definition in definitions:
        # JSON supplies names and zone intent, not expanded-corridor row IDs.
        # Its UPNY/SPR IDs refer to the historical unexpanded parent.
        definition["signed_parent_branch_rows"] = stored[stored[:, 0] == definition["inherited_interface_id"], 1].astype(int).tolist()
    return definitions


def build_runtime_operator(case_branch, branch_parent_row, state):
    """Map full-parent membership onto actual sectioned branches by endpoints.

    The first terminal is the original corridor's F_BUS; the last terminal is
    its original T_BUS. All sections must form an orientation-consistent chain.
    Runtime row order can differ, including canonical post-Dover axes.
    """
    branch = np.asarray(case_branch)
    parents = np.asarray(branch_parent_row, dtype=int).reshape(-1)
    if branch.ndim != 2 or len(branch) != len(parents) or branch.shape[1] < 2:
        raise ValueError("Branch/parent axes are incompatible")
    full, zones, keys, _ = source_case(state)
    definitions = interface_definitions(state)
    names = [d["interface"] for d in definitions]
    weights = {c: {p: np.zeros((len(names), len(branch))) for p in ("PF", "PT")} for c in CONVENTIONS}
    terms = []
    for j, definition in enumerate(definitions):
        for signed_row in definition["signed_parent_branch_rows"]:
            parent = abs(int(signed_row)); sign = int(np.sign(signed_row))
            candidates = np.flatnonzero(parents == parent)
            f, t = full["branch"][parent - 1, :2].astype(int)
            remaining = set(candidates.tolist()); cursor = f; chain = []
            while remaining:
                next_rows = [k for k in remaining if int(branch[k, 0]) == cursor]
                if len(next_rows) != 1:
                    raise ValueError(f"{state}: parent {parent} is not a single oriented chain at bus {cursor}")
                k = next_rows[0]; chain.append(k); remaining.remove(k); cursor = int(branch[k, 1])
            if not chain or cursor != t:
                raise ValueError(f"{state}: parent {parent} does not end at original T_BUS {t}")
            first, last = chain[0], chain[-1]
            if branch.shape[1] >= 11 and not np.all(branch[chain, 10] > 0):
                raise ValueError(f"Inactive inherited interface parent {parent}")
            weights[CONVENTIONS[0]]["PF"][j, first] += sign
            if sign > 0:
                weights[CONVENTIONS[1]]["PF"][j, first] += 1
                weights[CONVENTIONS[2]]["PT"][j, last] -= 1
            else:
                weights[CONVENTIONS[1]]["PT"][j, last] += 1
                weights[CONVENTIONS[2]]["PF"][j, first] -= 1
            terms.append(dict(state=state, interface=names[j], interface_index=j + 1,
                              inherited_interface_id=definition["inherited_interface_id"],
                              original_branch_row=parent, original_corridor_key=str(keys[parent - 1]),
                              coefficient=sign, original_from_bus=int(f), original_to_bus=int(t),
                              first_runtime_branch_row=first + 1, last_runtime_branch_row=last + 1,
                              section_count=len(chain)))
    return dict(state=state, interface_names=names, branch_count=len(branch), weights=weights, terms=terms)


def apply_interface_flows(PF, PT, operator, gamma=1.0):
    """Return H x 7 (or 7) flows. Divide aggregate MW by gamma only.

    This normalization is for public-scale comparison of the synthetic case;
    it is never an instruction to divide solved branch current by gamma.
    """
    pf, pt = np.asarray(PF, float), np.asarray(PT, float)
    if pf.shape != pt.shape or pf.shape[-1] != operator["branch_count"]:
        raise ValueError("PF/PT branch axes do not match the sealed operator")
    if not np.isfinite(gamma) or gamma <= 0:
        raise ValueError("gamma must be finite and positive")
    out = {}
    for convention, w in operator["weights"].items():
        # Select only member terms: NaN placeholders on absent nonmember
        # branches must not contaminate a mathematically zero coefficient.
        value = np.zeros(pf.shape[:-1] + (len(operator["interface_names"]),))
        for port, array in (("PF", pf), ("PT", pt)):
            for j in range(value.shape[-1]):
                idx = np.flatnonzero(w[port][j])
                value[..., j] += array[..., idx] @ w[port][j, idx]
        out[convention] = value / gamma
    out["oriented_source_minus_target_loss"] = out[CONVENTIONS[1]] - out[CONVENTIONS[2]]
    return out
