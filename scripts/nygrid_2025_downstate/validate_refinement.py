"""Independent audit of controlled downstate refinements of the 2025 DC baseline.

No construction, dispatch optimizer, fitted parameter, or interface observation
enters the network identity checks. A source-exact overlay is not automatically
equivalent to its coarse parent. Identity includes fixed phase-shifter terms as
well as the nodal matrix, and applies before injection relocation.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "output/nygrid_2025_downstate"
BASELINE = ROOT / "output/nygrid_2025_dispatch/dispatch"
TOL = 1e-7
MATRIX_TOL = 1e-8
INTERFACE_DEFINITIONS = [
    (1, "DYSINGER EAST", "A", "B"),
    (2, "WEST CENTRAL", "B", "C"),
    (3, "TOTAL EAST", "ABCDE", "FGHIJK"),
    (4, "MOSES SOUTH", "D", "E"),
    (5, "CENTRAL EAST - VC", "E", "F"),
    (8, "UPNY CONED", "ABCDEFG", "HIJK"),
    (10, "SPR/DUN-SOUTH", "I", "J"),
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def maximum(values):
    return float(np.max(np.abs(np.asarray(values, float)), initial=0))


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def close(actual, expected, label, tolerance=TOL, allow_nan=False):
    actual, expected = np.asarray(actual, float), np.asarray(expected, float)
    require(actual.shape == expected.shape, label + ": shape mismatch")
    if allow_nan:
        require(np.array_equal(np.isnan(actual), np.isnan(expected)), label + ": missingness mismatch")
    valid = ~np.isnan(expected) if allow_nan else np.ones(expected.shape, bool)
    require(np.isfinite(actual[valid]).all() and np.isfinite(expected[valid]).all(), label + ": nonfinite value")
    error = maximum(actual[valid] - expected[valid])
    require(error <= tolerance, f"{label}: error {error:g} exceeds {tolerance:g}")
    return error


def dc_matrices(case):
    """Direct MW/radian incidence construction independent of the replay builder."""
    bus = np.atleast_2d(np.asarray(case["bus"], float))
    branch = np.atleast_2d(np.asarray(case["branch"], float))
    base = float(case["baseMVA"])
    require(np.isfinite(bus).all() and np.isfinite(branch).all() and base > 0, "Invalid network values")
    ids = bus[:, 0].astype(int)
    require(np.array_equal(ids, bus[:, 0]) and len(set(ids)) == len(ids), "Bus IDs must be unique integers")
    lookup = {value: index for index, value in enumerate(ids)}
    require(np.equal(branch[:, :2], np.floor(branch[:, :2])).all(), "Branch endpoint is not an integer")
    require(np.isin(branch[:, :2], ids).all(), "Unknown branch endpoint")
    require(np.isin(branch[:, 10], [0, 1]).all(), "Unknown branch status")
    on = branch[:, 10] == 1
    require(np.all(branch[on, 3] != 0), "Active branch has zero reactance")
    tap = np.where(branch[:, 8] == 0, 1., branch[:, 8])
    require(np.all(tap > 0), "Nonpositive transformer tap")
    C = np.zeros((len(branch), len(bus)))
    for row, endpoints in enumerate(branch[:, :2].astype(int)):
        C[row, lookup[endpoints[0]]] += 1.
        C[row, lookup[endpoints[1]]] -= 1.
    b = np.zeros(len(branch))
    b[on] = base / (branch[on, 3] * tap[on])
    phase = -b * np.deg2rad(branch[:, 9])
    B = C.T @ (b[:, None] * C)
    return dict(ids=ids, lookup=lookup, C=C, b=b, B=B, phase_branch=phase,
                phase_bus=C.T @ phase, bus=bus, branch=branch, base=base)


def schur_signature(case, retained_ids):
    """Eliminate added zero-injection buses, retaining affine phase-shift terms.

    Nodal equations use B theta + phase_bus = specified injection. The returned
    injection_projection maps arbitrary full-bus injections to retained buses.
    This makes injection-relocation effects explicit rather than calling them
    topology identity merely because statewide/zone totals remain unchanged.
    """
    net = dc_matrices(case)
    retained = np.asarray(retained_ids, int)
    require(len(set(retained)) == len(retained) and np.isin(retained, net["ids"]).all(), "Retained bus IDs changed")
    ri = np.array([net["lookup"][value] for value in retained])
    ni = np.array([j for j, value in enumerate(net["ids"]) if value not in set(retained)], int)
    B = net["B"]
    projection = np.zeros((len(ri), len(B)))
    projection[:, ri] = np.eye(len(ri))
    lift = np.zeros((len(B), len(ri)))
    lift[ri] = np.eye(len(ri))
    angle_offset = np.zeros(len(B))
    if len(ni):
        internal = B[np.ix_(ni, ni)]
        require(np.linalg.matrix_rank(internal) == len(ni), "Added network has an ungrounded or singular island")
        coupling = np.linalg.solve(internal, B[np.ix_(ni, ri)])
        projection[:, ni] = -np.linalg.solve(internal.T, B[np.ix_(ri, ni)].T).T
        lift[ni] = -coupling
        angle_offset[ni] = -np.linalg.solve(internal, net["phase_bus"][ni])
    reduced_B = projection @ B[:, ri]
    reduced_phase = projection @ net["phase_bus"]
    branch_angle_map = net["b"][:, None] * (net["C"] @ lift)
    branch_phase_offset = net["phase_branch"] + net["b"] * (net["C"] @ angle_offset)
    return dict(network=net, retained_index=ri, new_index=ni, B=reduced_B,
                phase_bus=reduced_phase, injection_projection=projection,
                angle_lift=lift, angle_offset=angle_offset,
                branch_angle_map=branch_angle_map, branch_phase_offset=branch_phase_offset)


def identity_metrics(parent, candidate):
    parent_net = dc_matrices(parent)
    require(float(candidate["baseMVA"]) == float(parent["baseMVA"]), "MVA base changed")
    reduced = schur_signature(candidate, parent_net["ids"])
    return dict(maximum_schur_matrix_error_mw_per_rad=maximum(reduced["B"] - parent_net["B"]),
                maximum_schur_phase_error_mw=maximum(reduced["phase_bus"] - parent_net["phase_bus"]),
                maximum_added_bus_fixed_GS_mw=maximum(reduced["network"]["bus"][reduced["new_index"], 4]),
                retained_bus_count=len(parent_net["ids"]), added_bus_count=len(reduced["new_index"]))


def assert_identity(parent, candidate):
    result = identity_metrics(parent, candidate)
    require(result["maximum_schur_matrix_error_mw_per_rad"] <= MATRIX_TOL, "Schur admittance identity failed")
    require(result["maximum_schur_phase_error_mw"] <= TOL, "Schur phase-source identity failed")
    require(result["maximum_added_bus_fixed_GS_mw"] == 0, "Added fixed shunt injection breaks zero-injection identity")
    return result


def passive_residual_metrics(matrix):
    """Require a realizable passive DC residual, not just a close response fit."""
    value = np.asarray(matrix, float)
    require(value.ndim == 2 and value.shape[0] == value.shape[1] and np.isfinite(value).all(), "Invalid residual matrix")
    close(value, value.T, "Residual symmetry", MATRIX_TOL)
    close(value.sum(axis=1), np.zeros(len(value)), "Residual row sums", MATRIX_TOL)
    off = value.copy()
    np.fill_diagonal(off, 0)
    minimum_eigenvalue = float(np.linalg.eigvalsh(value).min(initial=0))
    maximum_offdiagonal = float(off.max(initial=0))
    require(minimum_eigenvalue >= -MATRIX_TOL and maximum_offdiagonal <= MATRIX_TOL,
            "Nonpassive or nonrealizable residual cannot qualify as equivalent detail")
    return dict(minimum_eigenvalue=minimum_eigenvalue, maximum_offdiagonal=maximum_offdiagonal)


def exact_source_branches(candidate, source, records, bus_map, neutralized_angle_limits=False):
    """Source/model branch rows are one-based; orientations cannot be inferred."""
    require(float(candidate["baseMVA"]) == float(source["baseMVA"]), "Source and model MVA bases differ")
    target, original = np.asarray(candidate["branch"]), np.asarray(source["branch"])
    require(len({int(row["model_branch_row"]) for row in records}) == len(records), "Duplicate model source claim")
    require(len({int(row["source_branch_row"]) for row in records}) == len(records), "Source circuit copied more than once")
    maximum_parameter_error = 0.
    for row in records:
        model_row, source_row = int(row["model_branch_row"]) - 1, int(row["source_branch_row"]) - 1
        require(0 <= model_row < len(target) and 0 <= source_row < len(original), "Source/model branch row out of range")
        expected = original[source_row, :13].copy()
        require(all(int(value) in bus_map for value in expected[:2]), "Unregistered source branch endpoint")
        expected[:2] = [bus_map[int(value)] for value in expected[:2]]
        if neutralized_angle_limits:
            expected[11:13] = [-360., 360.]
        maximum_parameter_error = max(maximum_parameter_error,
            close(target[model_row, :13], expected, "Exact source branch " + str(source_row + 1), tolerance=0))
    return dict(exact_source_rows=len(records), maximum_source_parameter_error=maximum_parameter_error,
                source_angle_limits_neutralized=bool(neutralized_angle_limits))


def parent_structure(parent, candidate, replaced_parent_rows):
    """Retain row identity and admit only explicitly registered deactivations."""
    original_bus, new_bus = np.asarray(parent["bus"], float), np.asarray(candidate["bus"], float)
    original_branch, new_branch = np.asarray(parent["branch"], float), np.asarray(candidate["branch"], float)
    require(len(new_bus) >= len(original_bus) and len(new_branch) >= len(original_branch), "Original network rows removed")
    close(new_bus[:len(original_bus), 0], original_bus[:, 0], "Original bus order preserved", tolerance=0)
    close(new_bus[:len(original_bus)][:, [4, 5, 9]], original_bus[:, [4, 5, 9]],
          "Original bus fixed shunts and nominal voltages preserved", tolerance=0)
    require(len(set(new_bus[:, 0])) == len(new_bus), "Original bus identity duplicated")
    rows = np.asarray(replaced_parent_rows, int)
    require(len(set(rows)) == len(rows) and np.all((rows >= 1) & (rows <= len(original_branch))),
            "Invalid or repeated aggregate replacement row")
    expected = original_branch[:, :13].copy()
    expected[rows - 1, 10] = 0
    error = close(new_branch[:len(original_branch), :13], expected,
                  "Original branch identity or registered status", tolerance=0)
    return dict(retained_original_buses=len(original_bus), retained_original_branch_rows=len(original_branch),
                registered_replaced_parent_rows=len(rows), maximum_parent_row_error=error)


def load_relocation(parent_load, candidate_load, allocation, parent_zones, candidate_zones,
                    external_parent_mask=None):
    """Allocation rows are candidate buses, columns are parent buses."""
    W = np.asarray(allocation, float)
    pz, cz = np.asarray(parent_zones).astype(str), np.asarray(candidate_zones).astype(str)
    require(W.shape == (len(cz), len(pz)) and np.isfinite(W).all() and np.all(W >= 0), "Invalid load allocation")
    close(W.sum(axis=0), np.ones(len(pz)), "Every parent load allocated once", tolerance=1e-12)
    require(np.all(W[cz[:, None] != pz[None, :]] == 0), "Load relocation crosses a zone/region boundary")
    if external_parent_mask is not None:
        external = np.flatnonzero(np.asarray(external_parent_mask, bool))
        require(W.shape[0] >= W.shape[1], "Original bus positions missing")
        close(W[:, external], np.eye(W.shape[0], W.shape[1])[:, external], "External bus loads preserved", tolerance=0)
    error = close(candidate_load, np.asarray(parent_load) @ W.T, "Declared load relocation", allow_nan=True)
    return dict(maximum_load_relocation_error_mw=error)


def coverage_preserving_load_allocation(parent, source, bus_register, allocation):
    """Reconstruct partial source coverage; unrepresented load stays at its parent.

    A selected subset cannot be normalized to represent an entire zone. Source
    MW are spatial weights only; the fixed 2025 hourly zonal quantities are not
    replaced by the historical source snapshot.
    """
    W = np.asarray(allocation, float)
    old_ids = np.asarray(parent["bus"])[:, 0].astype(int)
    source_bus = np.asarray(source["bus"], float)
    source_lookup = {int(row[0]): row for row in source_bus}
    require(np.array_equal(bus_register.model_bus.to_numpy(int)[:len(old_ids)], old_ids), "Load coverage parent order differs")
    expected = np.eye(len(bus_register), len(old_ids))
    records = []
    for zone, source_zone in [("I", 72), ("J", 74), ("K", 75)]:
        original = np.flatnonzero(bus_register.accounting_zone.to_numpy()[:len(old_ids)] == zone)
        selected = np.flatnonzero(bus_register.accounting_zone.eq(zone).to_numpy()
                                  & (bus_register.source_pd_mw.to_numpy(float) > 0))
        # This pinned source has no negative PD in I/J/K; fail rather than
        # quietly choosing a gross/net convention if the source changes.
        full_values = source_bus[source_bus[:, 10] == source_zone, 2]
        require(len(full_values) > 0 and np.all(full_values >= 0), "Historical source load convention requires review")
        total = float(full_values.sum())
        require(total > 0, "No full source zonal load denominator")
        weights = []
        for ix in selected:
            sid = int(bus_register.iloc[ix].source_bus)
            require(sid in source_lookup and int(source_lookup[sid][10]) == source_zone, "Selected load source has wrong zone/identity")
            close(bus_register.iloc[ix].source_pd_mw, source_lookup[sid][2], "Selected source PD passthrough", tolerance=0)
            weights.append(float(source_lookup[sid][2]) / total)
        coverage = float(sum(weights))
        require(coverage <= 1 + 1e-12, "Selected source load exceeds complete-zone denominator")
        expected[:, original] = 0
        expected[original, original] = 1 - coverage
        expected[np.ix_(selected, original)] += np.asarray(weights)[:, None]
        records.append(dict(zone=zone, full_source_pd_mw=total,
                            selected_source_pd_mw=coverage * total, selected_source_fraction=coverage,
                            residual_fraction_retained_at_original_buses=1 - coverage,
                            selected_source_load_buses=len(selected)))
    close(W, expected, "Source coverage allocation and original-bus residual", tolerance=1e-12)
    return records


def zone_backbone_reachability(case, bus_zones, zone, original_anchor_ids, loaded_bus_ids):
    """Loaded detail must reach its zone's retained anchors without another zone."""
    net = dc_matrices(case)
    members = {int(bus) for bus, value in bus_zones.items() if value == zone}
    anchors, targets = set(map(int, original_anchor_ids)), set(map(int, loaded_bus_ids))
    require(anchors and anchors.issubset(members) and targets.issubset(members), "Invalid zone backbone targets/anchors")
    adjacency = {bus: set() for bus in members}
    for row in net["branch"]:
        first, second = map(int, row[:2])
        if row[10] == 1 and first in members and second in members:
            adjacency[first].add(second)
            adjacency[second].add(first)
    reached, pending = set(anchors), list(anchors)
    while pending:
        for neighbor in adjacency[pending.pop()] - reached:
            reached.add(neighbor)
            pending.append(neighbor)
    missing = sorted(targets - reached)
    require(not missing, f"Loaded {zone} buses require another-zone transit because their source backbone is incomplete: {missing}")
    return dict(zone=zone, loaded_bus_count=len(targets), retained_anchor_count=len(anchors),
                loaded_buses_unreachable_within_zone=0)


def unit_generation_identity(parent_pg, candidate_pg, parent_register, candidate_register):
    """Per-device equality prevents compensating redispatch from hiding in totals."""
    for frame in [parent_register, candidate_register]:
        require(frame.device_key.is_unique, "Duplicate generator identity")
    old, new = parent_register.device_key.astype(str), candidate_register.device_key.astype(str)
    require(set(old) == set(new), "Generator inventory changed")
    lookup = {key: row for row, key in enumerate(new)}
    order = np.array([lookup[key] for key in old])
    error = close(np.asarray(candidate_pg)[:, order], parent_pg, "Per-device PG preserved", tolerance=0, allow_nan=True)
    for field in ["zone", "role", "fuel_category"]:
        require(np.array_equal(parent_register[field].astype(str).to_numpy(),
                               candidate_register.iloc[order][field].astype(str).to_numpy()),
                "Generator accounting identity changed: " + field)
    external = parent_register.role.eq("fixed_external").to_numpy()
    close(candidate_register.iloc[order].bus_id.to_numpy(int)[external],
          parent_register.bus_id.to_numpy(int)[external], "External generator landings preserved", tolerance=0)
    return dict(generator_count=len(old), maximum_per_device_PG_difference_mw=error,
                fixed_external_generators=int(external.sum()))


def dc_channel_identity(parent, candidate, parent_schedule, candidate_schedule, landing_rows=None):
    """Preserve each signed DC channel, allowing only registered endpoint moves."""
    old = np.asarray(parent["dcline"], float).reshape(-1, 17)
    new = np.asarray(candidate["dcline"], float).reshape(-1, 17)
    require(old.shape == new.shape, "DC channel inventory changed")
    expected = old.copy()
    claimed = set()
    for row in landing_rows or []:
        line = int(row["dc_row"]) - 1
        endpoint = {"from": 0, "to": 1}.get(row["endpoint"])
        require(0 <= line < len(old) and endpoint is not None, "Unknown DC relocation channel/endpoint")
        require((line, endpoint) not in claimed, "DC endpoint relocation duplicated")
        claimed.add((line, endpoint))
        require(int(row["old_bus_id"]) == old[line, endpoint], "DC relocation origin mismatch")
        expected[line, endpoint] = int(row["new_bus_id"])
    close(new[:, [0, 1, 2, 15, 16]], expected[:, [0, 1, 2, 15, 16]],
          "DC channel endpoints, status and losses", tolerance=0)
    error = close(candidate_schedule, parent_schedule, "Each signed DC schedule preserved", tolerance=0, allow_nan=True)
    return dict(DC_channels=len(old), registered_endpoint_moves=len(claimed), maximum_DC_schedule_error_mw=error)


def operator_identity(parent, candidate, parent_operator, candidate_operator):
    """Compare operator response over every retained angle, including phase terms."""
    old_net = dc_matrices(parent)
    new = schur_signature(candidate, old_net["ids"])
    old, refined = np.asarray(parent_operator, float), np.asarray(candidate_operator, float)
    require(old.shape[1] == len(old_net["branch"]) and refined.shape[1] == len(new["network"]["branch"]),
            "Operator branch axis mismatch")
    expected = old @ (old_net["b"][:, None] * old_net["C"])
    actual = refined @ new["branch_angle_map"]
    expected_phase = old @ old_net["phase_branch"]
    actual_phase = refined @ new["branch_phase_offset"]
    return dict(maximum_operator_response_error_mw_per_rad=maximum(actual - expected),
                maximum_operator_phase_error_mw=maximum(actual_phase - expected_phase))


def physical_cut_identity(case, operator, side_bus_ids):
    """A physical cut counts each crossing once and excludes series support legs."""
    net = dc_matrices(case)
    side_ids = np.asarray(side_bus_ids, int)
    require(len(set(side_ids)) == len(side_ids) and np.isin(side_ids, net["ids"]).all(), "Invalid cut-side bus IDs")
    side = np.isin(net["ids"], side_ids).astype(float)
    require(0 < side.sum() < len(side), "Empty or universal cut side")
    return close(np.asarray(operator), net["C"] @ side, "Physical cut membership", tolerance=0)


def zone_interface_operators(case, bus_zones):
    """Rebuild the inherited NY zone-crossing functionals on every active edge.

    These functionals exactly match this parent but are still legacy proxies,
    not a claim that a named 2025 physical flowgate has certified membership.
    External-region edges are excluded. This distinction matters for zone-pair
    operators, which are not necessarily complete electrical graph cuts.
    """
    net = dc_matrices(case)
    require(set(int(value) for value in bus_zones) == set(net["ids"]), "Zone register must cover every bus exactly")
    zones = {int(key): str(value) for key, value in bus_zones.items()}
    fz = np.array([zones[int(value)] for value in net["branch"][:, 0]])
    tz = np.array([zones[int(value)] for value in net["branch"][:, 1]])
    active = net["branch"][:, 10] == 1
    rows = []
    for _, _, from_zones, to_zones in INTERFACE_DEFINITIONS:
        forward = np.isin(fz, list(from_zones)) & np.isin(tz, list(to_zones))
        reverse = np.isin(tz, list(from_zones)) & np.isin(fz, list(to_zones))
        rows.append((forward.astype(float) - reverse.astype(float)) * active)
    return np.array(rows)


def inherited_interface_operators(case):
    mapping = np.asarray(case["if"]["map"])
    operators = np.zeros((len(INTERFACE_DEFINITIONS), len(case["branch"])))
    for row, (key, _, _, _) in enumerate(INTERFACE_DEFINITIONS):
        signed = mapping[mapping[:, 0] == key, 1]
        require(np.equal(signed, np.floor(signed)).all() and np.all((abs(signed) >= 1) & (abs(signed) <= operators.shape[1])),
                "Invalid inherited signed branch row")
        for value in signed.astype(int):
            operators[row, abs(value) - 1] += np.sign(value)
    return operators


def parent_operator_definitions(parent, bus_zones):
    reconstructed = zone_interface_operators(parent, bus_zones)
    inherited = inherited_interface_operators(parent)
    close(reconstructed, inherited, "Parent zone-crossing operators reproduce inherited vectors", tolerance=0)
    return [dict(interface=name, inherited_interface_id=key, source_zones=list(from_zones), target_zones=list(to_zones),
                 signed_parent_branch_rows=[int(index + 1) * int(reconstructed[j, index]) for index in np.flatnonzero(reconstructed[j])],
                 coefficient_error=0., physical_2025_interface_membership_verified=False,
                 interpretation="legacy NY-zone crossing functional; excludes external-region branches")
            for j, (key, name, from_zones, to_zones) in enumerate(INTERFACE_DEFINITIONS)]


def paired_interface_scores(parent_predicted, candidate_predicted, actual, parent_qualified,
                            candidate_qualified, gamma, names):
    """Score a fixed cohort and report regressions without imposing a fitted gate."""
    p, c, y = [np.asarray(value, float) for value in [parent_predicted, candidate_predicted, actual]]
    pq, cq = [np.asarray(value, bool).reshape(-1) for value in [parent_qualified, candidate_qualified]]
    require(p.shape == c.shape == y.shape and p.shape == (len(pq), len(names)), "Interface score axes differ")
    require(np.array_equal(pq, cq), "Candidate changes the baseline qualification cohort")
    require(np.isfinite(p[pq]).all() and np.isfinite(c[cq]).all(), "Missing prediction on a qualified hour")
    require(np.isfinite(gamma) and gamma > 0, "Invalid frozen scaling factor")
    used = pq & np.isfinite(y).all(axis=1)
    require(used.any(), "No common scored hours")
    rows = []
    for j, name in enumerate(names):
        old_error, new_error = p[used, j] / gamma - y[used, j], c[used, j] / gamma - y[used, j]
        denominator = float(np.abs(y[used, j]).sum())
        require(denominator > 0, "Zero observed interface denominator")
        before, after = [float(100 * np.abs(error).sum() / denominator) for error in [old_error, new_error]]
        rows.append(dict(interface=name, hours=int(used.sum()), baseline_wape_percent=before,
                         candidate_wape_percent=after, wape_change_percentage_points=after - before,
                         baseline_mae_public_mw=float(np.abs(old_error).mean()),
                         candidate_mae_public_mw=float(np.abs(new_error).mean()),
                         candidate_bias_public_mw=float(new_error.mean()),
                         improved=after < before, observations_used_for_construction=False,
                         physical_2025_interface_membership_verified=False))
    return rows


def baseline_reference(folder=BASELINE):
    folder = Path(folder).resolve()
    d = loadmat(folder / "dispatch.mat", simplify_cells=True,
                variable_names=["base_case", "hour_index", "timestamp_utc", "gamma", "dispatch_qualified", "status_code"])
    case = d["base_case"]
    require(np.array_equal(d["hour_index"], np.arange(1, 8761)), "Baseline annual hour axis changed")
    require((len(case["bus"]), len(case["branch"]), len(case["dcline"])) == (140, 225, 4), "Baseline network counts changed")
    require(len(case["gen"]) == 1464 and int(np.asarray(d["dispatch_qualified"], bool).sum()) == 8663,
            "Final NJ-extended dispatch baseline required")
    summary = json.loads((folder / "summary.json").read_text())
    for name, expected in summary["file_sha256"].items():
        require(sha(folder / name) == expected, "Baseline dispatch artifact changed: " + name)
    names = ["dispatch.mat", "dispatch_bounds.mat", "dispatch_priors.mat", "dispatch_network.mat",
             "model_generator_register.csv", "hour_status.csv", "contract.json", "summary.json"]
    return dict(baseline_commit="c7874aa90fec1d4e883814297e91bfcd3567bdf2", buses=140, AC_branches=225,
                DC_links=4, generators=1464, annual_hours=8760, qualified_hours=8663,
                gamma=float(d["gamma"]), refinement_parameters_fit_to_interface_observations=False,
                artifacts=[dict(path=(folder / name).relative_to(ROOT).as_posix(), sha256=sha(folder / name)) for name in names])


def audit_construction(folder=DEFAULT / "network", output=DEFAULT / "validation"):
    """Audit saved construction artifacts without importing the network builder."""
    folder, output = Path(folder).resolve(), Path(output).resolve()
    data = loadmat(folder / "network_cases.mat", simplify_cells=True)
    baseline = loadmat(BASELINE / "dispatch.mat", simplify_cells=True, variable_names=["base_case", "gamma"])
    parent = baseline["base_case"]
    baseline_proof = baseline_reference()
    frozen_path = output / "baseline_reference.json"
    require(frozen_path.is_file() and json.loads(frozen_path.read_text()) == baseline_proof,
            "Pinned baseline reference is absent or changed")
    for key in ["bus", "branch", "gen", "dcline"]:
        close(data["parent_case"][key], parent[key], "Saved parent case " + key, tolerance=0)
    close(data["gamma"], baseline["gamma"], "Frozen single gamma", tolerance=0)
    buses = pd.read_csv(folder / "bus_register.csv", keep_default_na=False)
    branches = pd.read_csv(folder / "branch_register.csv", keep_default_na=False)
    replacements = pd.read_csv(folder / "replacement_register.csv", keep_default_na=False)
    source_map = pd.read_csv(folder / "source_bus_map.csv", keep_default_na=False)
    landing = pd.read_csv(folder / "generation_landing_register.csv", keep_default_na=False)
    register = pd.read_csv(BASELINE / "model_generator_register.csv", keep_default_na=False)
    require(buses.model_bus.is_unique and branches.branch_key.is_unique, "Duplicated construction identity")
    close(branches.model_branch_row, np.arange(1, len(branches) + 1), "Contiguous branch register", tolerance=0)
    close(data["bus_ids"], buses.model_bus, "Saved bus register identity", tolerance=0)
    require(np.array_equal(np.asarray(data["bus_zones"]).astype(str), buses.accounting_zone.astype(str)), "Saved zone register differs")
    require(np.array_equal(np.asarray(data["branch_keys"]).astype(str), branches.branch_key.astype(str)), "Saved branch keys differ")
    zones = dict(zip(buses.model_bus.astype(int), buses.accounting_zone.astype(str)))
    original_zones = pd.read_csv(ROOT / "output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv", keep_default_na=False).set_index("idx").zone.to_dict()
    definitions = parent_operator_definitions(parent, original_zones)
    require(all(zones[bus] == zone for bus, zone in original_zones.items()), "Retained bus accounting zones changed")
    for name in ["identity", "asset"]:
        W = np.asarray(data["load_allocation_" + name])
        # A basis of one MW at every original bus proves conservation for any
        # signed PD/QD series, not just the sampled annual operating points.
        load_relocation(np.eye(140), W.T, W, [original_zones[i] for i in range(1, 141)],
                        buses.accounting_zone.to_numpy(), np.array([original_zones[i] == "NA" for i in range(1, 141)]))
    close(data["load_allocation_identity"], np.eye(len(buses), 140), "Identity allocation adds only zero loads", tolerance=0)
    load_coverage = coverage_preserving_load_allocation(parent, data["source_case"], buses, data["load_allocation_asset"])
    close(data["generator_bus_identity"], register.bus_id, "Identity generator landings", tolerance=0)
    expected_gen = register.bus_id.to_numpy(int).copy()
    require(landing.device_key.is_unique and landing.gen_row.is_unique, "Duplicated generation landing record")
    primary_landings_path = folder.parent / "sources/asset_landing_crosswalk.csv"
    primary_landings = pd.read_csv(primary_landings_path, keep_default_na=False).set_index("device_key")
    for row in landing.itertuples(index=False):
        ix = int(row.gen_row) - 1
        require(0 <= ix < len(register) and register.iloc[ix].device_key == row.device_key, "Landing generator identity mismatch")
        require(register.iloc[ix].role == "native" and expected_gen[ix] == int(row.old_bus), "External or incorrect origin generator move")
        require(row.device_key in primary_landings.index and int(primary_landings.loc[row.device_key, "may_move_after_network_attachment_verified"]) == 1,
                "Generation landing lacks qualifying unit source evidence")
        evidence = primary_landings.loc[row.device_key]
        target_bus = buses.loc[buses.model_bus.eq(int(row.new_bus))].iloc[0]
        station = "".join(str(evidence.source_backed_receiving_station).upper().split())
        target_name = "".join(str(target_bus.model_name).upper().split())
        # Public POI wording reverses this literal historical station name.
        station = {"ASTORIAEAST": "EASTASTORIA"}.get(station, station)
        require(station in target_name and float(evidence.receiving_voltage_kv) == float(target_bus.base_kv),
                "Generation landing station/voltage differs from primary crosswalk")
        require(str(row.zone) == str(register.iloc[ix].zone) == zones[int(row.new_bus)], "Generator landing crosses accounting zone")
        expected_gen[ix] = int(row.new_bus)
    close(data["generator_bus_asset"], expected_gen, "Asset landing map exactly follows source ledger", tolerance=0)
    cases = {key: value for key, value in data.items() if key.endswith("_case") and key not in {"parent_case", "source_case"}}
    require({"expanded_identity_case", "refined_2019_case", "refined_2025_case"}.issubset(cases), "Required construction variants missing")
    static = []
    first_branch = np.asarray(cases["expanded_identity_case"]["branch"])
    for key, case in cases.items():
        name = key.removesuffix("_case")
        require(len(case["bus"]) == len(buses) and len(case["branch"]) == len(branches), "Variant matrix/register axes differ")
        close(case["bus"][:, 0], buses.model_bus, "Variant bus order " + name, tolerance=0)
        close(case["branch"][:, :2], branches[["from_bus", "to_bus"]], "Variant branch endpoint register " + name, tolerance=0)
        close(case["branch"][:, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12]],
              first_branch[:, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12]], "Variant changes only registered statuses " + name, tolerance=0)
        close(case["branch"][:, 10], branches[name + "_status"], "Variant active-status register " + name, tolerance=0)
        subset = replacements.loc[replacements.variant.eq(name)]
        result = parent_structure(parent, case, subset.parent_branch_row.astype(int).tolist())
        close(case["gen"], parent["gen"], "Topology construction preserves generation " + name, tolerance=0)
        close(case["dcline"], parent["dcline"], "Topology construction preserves DC channels " + name, tolerance=0)
        close(case["bus"][140:, 2:6], np.zeros((len(buses) - 140, 4)), "New topology buses start at zero injection " + name, tolerance=0)
        net = dc_matrices(case)
        require(np.linalg.matrix_rank(net["B"]) == len(net["B"]) - 1, "Disconnected or singular candidate " + name)
        for row in subset.itertuples(index=False):
            keys = [value for value in (row.replacement_keys + ";" + row.shared_source_mesh_keys).split(";") if value]
            require(keys and set(keys).issubset(set(branches.branch_key)), "Replacement lacks known successor rows")
            active = branches.set_index("branch_key").loc[keys, name + "_status"].astype(int)
            require(active.eq(1).all(), "Replacement refers to an inactive successor")
        reconstructed_operator = zone_interface_operators(case, zones)
        result.update(variant=name, active_AC_branches=int((net["branch"][:, 10] == 1).sum()),
                      **identity_metrics(parent, case))
        if name == "expanded_identity":
            assert_identity(parent, case)
            comparison = operator_identity(parent, case, inherited_interface_operators(parent), reconstructed_operator)
            require(comparison["maximum_operator_response_error_mw_per_rad"] <= MATRIX_TOL
                    and comparison["maximum_operator_phase_error_mw"] <= TOL, "Identity variant changes common interface functionals")
            result.update(comparison)
        else:
            loaded_k = buses.loc[buses.accounting_zone.eq("K") & buses.source_pd_mw.astype(float).gt(0), "model_bus"].astype(int)
            result.update(zone_backbone_reachability(case, zones, "K", [79, 80], loaded_k))
        static.append(result)
    # Direct source electrical rows are unchanged in every variant; only their
    # explicit participation changes. The source-detail case activates them.
    physical = branches.loc[branches.source_branch_row.astype(int) > 0]
    source_copy = exact_source_branches(cases["refined_2019_case"], data["source_case"], physical.to_dict("records"),
                                       dict(zip(source_map.source_bus.astype(int), source_map.model_bus.astype(int))),
                                       neutralized_angle_limits=True)
    require(not branches.thermal_eligible.astype(str).str.lower().isin(["1", "true"]).any(), "Unverified branch acquired thermal qualification")
    source_receipts = pd.read_csv(folder / "source_manifest.csv", keep_default_na=False)
    for row in source_receipts.itertuples(index=False):
        path = ROOT / row.path
        require(path.is_file() and sha(path) == row.sha256, "Construction source fingerprint changed: " + row.path)
    files = [folder / name for name in ["network_cases.mat", "bus_register.csv", "branch_register.csv",
             "replacement_register.csv", "source_bus_map.csv", "generation_landing_register.csv", "load_allocation_register.csv",
             "source_manifest.csv", "construction_summary.json"]] + [primary_landings_path, Path(__file__)]
    result = dict(passed=True, scope="independent construction and DC-equivalence audit; physical2025 flowgate and thermal qualification remain unverified",
                  variants=static, exact_source_copy=source_copy, source_qualified_asset_landing_rows=len(landing),
                  source_load_coverage=load_coverage,
                  common_interface_definitions=definitions, original_parent_bus_count=140,
                  original_parent_branch_count=225, files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in files])
    output.mkdir(parents=True, exist_ok=True)
    (output / "construction_validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(static).to_csv(output / "construction_variant_checks.csv", index=False, lineterminator="\n")
    return result


def expected_dated_states(timestamps, upgrade_register):
    times = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True))
    result = np.full(len(times), "refined_2025_pre_may_case", dtype=object)
    for project, state in [("RCC_Gowanus_Greenwood", "refined_2025_may21_case"),
                           ("RCC_Goethals_FoxHills", "refined_2025_may30_case"),
                           ("Dover_Segment_B_final", "refined_2025_case")]:
        source = upgrade_register.loc[upgrade_register.project.eq(project), "conservative_scenario_activation_local"].unique()
        require(len(source) == 1, "Missing or ambiguous source activation for " + project)
        activation = pd.Timestamp(source[0]).tz_convert("UTC")
        result[times >= activation] = state
    return result


def audit_replays(folder=DEFAULT, output=None):
    """Reconstruct unchanged inputs and independently solve every qualified case."""
    folder = Path(folder).resolve()
    output = Path(output).resolve() if output else folder / "validation"
    electrical_path = ROOT / "scripts/nygrid_2025_dispatch/validate_dispatch.py"
    spec = importlib.util.spec_from_file_location("independent_bounded_dispatch_audit", electrical_path)
    electrical_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(electrical_module)
    independent_electrical = electrical_module.electrical_audit
    d = loadmat(BASELINE / "dispatch.mat", simplify_cells=True)
    old_network = loadmat(BASELINE / "dispatch_network.mat", simplify_cells=True)
    n = loadmat(folder / "network/network_cases.mat", simplify_cells=True)
    parent = d["base_case"]
    valid = np.asarray(d["dispatch_qualified"], bool).reshape(-1)
    times = np.asarray(d["timestamp_utc"]).astype(str)
    hours = np.asarray(d["hour_index"], int).reshape(-1)
    gamma = float(d["gamma"])
    require(len(hours) == 8760 and int(valid.sum()) == 8663, "Fixed annual source cohort changed")
    buses = pd.read_csv(folder / "network/bus_register.csv", keep_default_na=False)
    zones = dict(zip(buses.model_bus.astype(int), buses.accounting_zone.astype(str)))
    parent_zones = [zones[int(value)] for value in parent["bus"][:, 0]]
    register = pd.read_csv(BASELINE / "model_generator_register.csv", keep_default_na=False)
    upgrades = pd.read_csv(folder / "sources/upgrade_register.csv", keep_default_na=False)
    dated = expected_dated_states(times, upgrades)
    receipt_path = folder / "replay/provenance.json"
    receipt = json.loads(receipt_path.read_text())
    require(receipt["observation_data_read"] is False and receipt["physical_2025_flowgate_membership_verified"] is False,
            "Replay observation/physical-flowgate scope changed")
    for item in receipt["dependencies"]:
        require(sha(ROOT / item["path"]) == item["sha256"], "Replay dependency fingerprint changed: " + item["path"])
    plans = {"expanded_identity": ("expanded_identity_case", "identity"),
             "source_detail_2019": ("refined_2019_case", "identity"),
             "upgrades_year_end": ("refined_2025_case", "identity"),
             "upgrades_dated": ("dated", "identity"),
             "assets_year_end": ("refined_2025_case", "asset"),
             "assets_dated": ("dated", "asset"),
             "nyes_assumption_year_end": ("refined_2025_nyes_case", "asset")}
    require({item["variant"] for item in receipt["variants"]} == set(plans), "Required paired scenarios missing or duplicated")
    observed_path = ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv"
    observed = pd.read_csv(observed_path)
    require(np.array_equal(times, observed.timestamp_utc.astype(str)), "Observation timestamp alignment changed")
    names = [row[1] for row in INTERFACE_DEFINITIONS]
    actual = observed[names].to_numpy(float)
    require(np.isfinite(actual[valid]).all(), "Observation missing from fixed qualified cohort")
    variants, score_rows, hourly_frames, state_rows, files = [], [], [], [], []
    for item in receipt["variants"]:
        name = item["variant"]
        expected_state, mapping = plans[name]
        path = ROOT / item["file"]
        require(sha(path) == item["sha256"], "Replay output fingerprint changed: " + name)
        files.append(path)
        replay = loadmat(path, simplify_cells=True)
        close(replay["hour_index"], hours, "Replay hour axis " + name, tolerance=0)
        close(replay["gamma"], gamma, "Replay gamma " + name, tolerance=0)
        require(np.array_equal(np.asarray(replay["timestamp_utc"]).astype(str), times), "Replay timestamp axis differs")
        require(np.array_equal(np.asarray(replay["qualified"], bool).reshape(-1), valid), "Replay qualification differs")
        require(replay["load_allocation_name"] == mapping and replay["generator_mapping_name"] == mapping, "Scenario injection mapping changed")
        states = np.asarray(replay["network_state_ids"]).astype(str).reshape(-1)
        expected = dated if expected_state == "dated" else np.full(8760, expected_state)
        require(np.array_equal(states, expected), "Dated/fixed topology schedule changed: " + name)
        close(replay["reference_bus"], d["reference_bus"], "Reference bus policy " + name, tolerance=0)
        for key, width in [("branch_pf", len(n[states[0]]["branch"])), ("bus_va", len(buses)), ("interface_pf", 7)]:
            require(np.shape(replay[key]) == (8760, width), "Replay output axes differ: " + key)
            require(np.isnan(replay[key][~valid]).all() and np.isfinite(replay[key][valid]).all(),
                    "Replay silently fills missing hours or loses qualified hours: " + key)
        W = np.asarray(n["load_allocation_" + mapping], float)
        pd_model, qd_model = [np.asarray(d[key]) @ W.T for key in ["bus_pd", "bus_qd"]]
        for label, loads, old in [("P", pd_model, d["bus_pd"]), ("Q", qd_model, d["bus_qd"])]:
            load_relocation(old, loads, W, parent_zones, buses.accounting_zone.to_numpy(), np.array(parent_zones) == "NA")
            for zone in set(parent_zones):
                close(loads[:, buses.accounting_zone.eq(zone).to_numpy()].sum(axis=1),
                      np.asarray(old)[:, np.array(parent_zones) == zone].sum(axis=1),
                      "Hourly gross zonal " + label + " conserved " + zone, tolerance=TOL)
        candidate_register = register.copy()
        candidate_register["bus_id"] = np.asarray(n["generator_bus_" + mapping], int)
        pg = np.asarray(d["gen_pg"])
        unit_generation_identity(pg, pg, register, candidate_register)
        metrics = {key: np.full(8760, np.nan) for key in ["nodal_residual_mw", "global_balance_residual_mw",
            "branch_angle_identity_error_mw", "independent_branch_error_mw", "independent_angle_error_deg"]}
        for state in sorted(set(states)):
            ix = np.flatnonzero(valid & (states == state))
            require(len(ix) > 0, "Network state has no qualified audit hours")
            case = copy.deepcopy(n[state])
            case["gen"][:, 0] = candidate_register.bus_id.to_numpy(int)
            close(case["gen"][:, 1:], parent["gen"][:, 1:], "Generator template only changes landing", tolerance=0)
            dc_channel_identity(parent, case, d["dc_pf"], d["dc_pf"])
            result = independent_electrical(case, pd_model[ix], pg[ix], np.asarray(d["dc_pf"])[ix],
                replay["branch_pf"][ix], replay["bus_va"][ix], np.asarray(d["reference_bus"])[ix])
            for key in metrics:
                metrics[key][ix] = result[key]
                close(result[key], np.zeros(len(ix)), name + ": independent " + key, tolerance=TOL)
            operator = zone_interface_operators(case, zones)
            close(replay["interface_pf"][ix], replay["branch_pf"][ix] @ operator.T,
                  "Saved common interface predictions " + name, tolerance=TOL)
            state_rows.append(dict(variant=name, network_state=state, annual_hours=int((states == state).sum()),
                                   qualified_hours=len(ix), active_AC_branches=int((case["branch"][:, 10] == 1).sum())))
        close(replay["hypothetical_slack_change_mw"][valid], np.zeros(int(valid.sum())), "No redispatch required " + name)
        close(replay["nodal_residual_mw"][valid], np.zeros(int(valid.sum())), "Recorded nodal balance " + name)
        if name == "expanded_identity":
            close(replay["bus_va"][valid, :140], old_network["bus_va"][valid], "Identity annual retained angles")
            close(replay["interface_pf"][valid], old_network["inherited_interface_pf"][valid], "Identity annual interfaces")
        scores = paired_interface_scores(old_network["inherited_interface_pf"], replay["interface_pf"], actual,
                                         valid, np.asarray(replay["qualified"], bool), gamma, names)
        for score in scores:
            score_rows.append(dict(variant=name, **score))
        variants.append(dict(variant=name, passed=True, qualified_hours=int(valid.sum()), missing_hours=int((~valid).sum()),
            gross_zonal_P_and_Q_allocation_checked=True, generator_P_and_bounds_reused_unchanged=True,
            signed_DC_channels_unchanged=True, **{"maximum_" + key: float(values[valid].max()) for key, values in metrics.items()}))
        hourly_frames.append(pd.DataFrame(dict(variant=name, hour_index=hours[valid], timestamp_utc=times[valid],
                                               **{key: values[valid] for key, values in metrics.items()})))
        print(json.dumps(variants[-1]), flush=True)
    # Compare independently recalculated scores with the published comparison,
    # when available; observations remain confined to this post-hoc stage.
    comparison = folder / "comparison/interface_summary.csv"
    if comparison.is_file():
        public = pd.read_csv(comparison).set_index(["variant", "interface"])
        for row in score_rows:
            saved = public.loc[(row["variant"], row["interface"])]
            close(saved.wape_percent, row["candidate_wape_percent"], "Published WAPE replay", tolerance=1e-10)
            close(saved.mae_public_equivalent_mw, row["candidate_mae_public_mw"], "Published MAE replay", tolerance=1e-9)
        files.append(comparison)
    files += [receipt_path, observed_path, folder / "network/network_cases.mat", folder / "sources/upgrade_register.csv",
              electrical_path, Path(__file__)]
    summary = dict(passed=True, annual_hours_per_variant=8760, qualified_hours_per_variant=int(valid.sum()),
        variant_count=len(variants), independently_solved_variant_hours=int(valid.sum()) * len(variants),
        physical_2025_flowgate_membership_verified=False, AC_or_storage_energy_qualification=False,
        reused_operator_definition="same tested zone-crossing definition shared with replay; electrical solves and score recalculation independent",
        variants=variants, files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in files])
    output.mkdir(parents=True, exist_ok=True)
    (output / "annual_validation.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(variants).to_csv(output / "annual_variant_checks.csv", index=False, lineterminator="\n")
    pd.DataFrame(state_rows).to_csv(output / "annual_state_hour_counts.csv", index=False, lineterminator="\n")
    pd.DataFrame(score_rows).to_csv(output / "independent_paired_interface_scores.csv", index=False, lineterminator="\n")
    pd.concat(hourly_frames, ignore_index=True).to_csv(output / "independent_hourly_checks.csv.gz", index=False,
        lineterminator="\n", compression={"method": "gzip", "mtime": 0})
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=DEFAULT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--construction-only", action="store_true")
    args = parser.parse_args()
    output_folder = args.output if args.output else args.folder / "validation"
    result = audit_construction(args.folder / "network", output_folder)
    print(json.dumps({"construction_passed": result["passed"], "variants": len(result["variants"])}), flush=True)
    if not args.construction_only:
        result = audit_replays(args.folder, output_folder)
        print(json.dumps({"annual_passed": result["passed"], "independently_solved_variant_hours": result["independently_solved_variant_hours"]}), flush=True)
