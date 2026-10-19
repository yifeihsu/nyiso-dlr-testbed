"""Independent DC audit of an eight-hub refinement retaining the full NPCC parent.

The eliminated nodes belong only to the added 191-bus research overlay. The
94 external and 46 NY original buses stay explicit. Equivalents preserve DC
terminal response under zero interior injection; they are not physical lines,
AC equivalents, or conductor/thermal data.
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
DEFAULT = ROOT / "output/nygrid_2025_slim"
SOURCE = ROOT / "output/nygrid_2025_downstate/network/network_cases.mat"
BASELINE = ROOT / "output/nygrid_2025_dispatch/dispatch"
CORE_IDS = {10774, 10858, 10902, 10593, 10589, 11129, 11130, 20001}
MATRIX_TOL = 1e-8
MW_TOL = 1e-7
INTERFACE_IDS = [1, 2, 3, 4, 5, 8, 10]
INTERFACE_NAMES = ["DYSINGER EAST", "WEST CENTRAL", "TOTAL EAST", "MOSES SOUTH", "CENTRAL EAST - VC", "UPNY CONED", "SPR/DUN-SOUTH"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def error(actual, expected):
    a, b = np.asarray(actual, float), np.asarray(expected, float)
    require(a.shape == b.shape, "Shape mismatch in independent comparison")
    require(np.isfinite(a).all() and np.isfinite(b).all(), "Nonfinite independent comparison")
    return float(np.max(np.abs(a - b), initial=0))


def matrices(case):
    """Form branch/nodal MW equations directly, independently of the reducer."""
    buses = np.asarray(case["bus"], float)
    branches = np.asarray(case["branch"], float)
    ids = buses[:, 0].astype(int)
    require(np.array_equal(ids, buses[:, 0]) and len(set(ids)) == len(ids), "Duplicate/noninteger bus ID")
    lookup = {value: i for i, value in enumerate(ids)}
    C = np.zeros((len(branches), len(ids)))
    for i, row in enumerate(branches):
        require(row[0] == int(row[0]) and row[1] == int(row[1])
                and int(row[0]) in lookup and int(row[1]) in lookup, "Unknown branch endpoint")
        C[i, lookup[int(row[0])]] += 1
        C[i, lookup[int(row[1])]] -= 1
    require(np.isin(branches[:, 10], [0, 1]).all(), "Unknown branch status")
    active = branches[:, 10] == 1
    tap = np.where(branches[:, 8] == 0, 1., branches[:, 8])
    require((tap > 0).all() and (branches[active, 3] != 0).all(), "Invalid active tap/reactance")
    b = np.zeros(len(branches))
    b[active] = float(case["baseMVA"]) / (branches[active, 3] * tap[active])
    phase = -b * np.deg2rad(branches[:, 9])
    return dict(ids=ids, lookup=lookup, C=C, b=b, B=C.T @ (b[:, None] * C),
                branch_phase=phase, nodal_phase=C.T @ phase, bus=buses, branch=branches)


def eliminated_response(source, retained_ids):
    """Schur complement with affine phase terms and generic flow functionals."""
    net = matrices(source)
    retained_ids = np.asarray(retained_ids, int)
    require(len(set(retained_ids)) == len(retained_ids) and set(retained_ids).issubset(set(net["ids"])), "Invalid retained IDs")
    retained = np.array([net["lookup"][value] for value in retained_ids])
    internal = np.array([i for i, value in enumerate(net["ids"]) if value not in set(retained_ids)], int)
    B = net["B"]
    lift = np.zeros((len(B), len(retained)))
    lift[retained] = np.eye(len(retained))
    affine = np.zeros(len(B))
    projection = np.zeros((len(retained), len(B)))
    projection[:, retained] = np.eye(len(retained))
    if len(internal):
        block = B[np.ix_(internal, internal)]
        require(np.linalg.matrix_rank(block) == len(internal), "Eliminated interior is singular")
        lift[internal] = -np.linalg.solve(block, B[np.ix_(internal, retained)])
        affine[internal] = -np.linalg.solve(block, net["nodal_phase"][internal])
        projection[:, internal] = -np.linalg.solve(block.T, B[np.ix_(retained, internal)].T).T
    return dict(network=net, retained=retained, internal=internal, angle_lift=lift, angle_offset=affine,
                B=projection @ B[:, retained], nodal_phase=projection @ net["nodal_phase"],
                source_flow_angle_map=net["b"][:, None] * (net["C"] @ lift),
                source_flow_offset=net["branch_phase"] + net["b"] * (net["C"] @ affine),
                injection_projection=projection)


def assert_dc_equivalence(source, slim):
    require(float(source["baseMVA"]) == float(slim["baseMVA"]), "MVA base changed")
    net = matrices(slim)
    expected = eliminated_response(source, net["ids"])
    matrix_error = error(net["B"], expected["B"])
    phase_error = error(net["nodal_phase"], expected["nodal_phase"])
    require(matrix_error < MATRIX_TOL, "Slim network does not match exact retained-bus DC response")
    require(phase_error < MW_TOL, "Slim network dropped the affine phase source")
    require(np.linalg.matrix_rank(net["B"]) == len(net["ids"]) - 1, "Slim network disconnected/singular")
    return dict(maximum_B_error_mw_per_rad=matrix_error, maximum_phase_error_mw=phase_error,
                retained_bus_count=len(net["ids"]), eliminated_bus_count=len(expected["internal"]))


def zero_interior_injection_contract(source, retained_ids, pd=None, qd=None, generator_bus_ids=None,
                                     dc_from_bus_ids=None, dc_to_bus_ids=None):
    retained = set(map(int, retained_ids))
    buses = np.asarray(source["bus"])
    interior = np.array([int(value) not in retained for value in buses[:, 0]])
    require(np.all(buses[interior, 2:6] == 0), "Nonzero interior load or fixed shunt invalidates zero-injection reduction")
    for label, values in [("PD", pd), ("QD", qd)]:
        if values is not None:
            require(np.asarray(values).shape[-1] == len(buses), "Interior input bus axis differs")
            require(np.all(np.asarray(values)[..., interior] == 0), "Hourly interior " + label + " is not zero")
    gen_ids = np.asarray(source["gen"])[:, 0] if generator_bus_ids is None else np.asarray(generator_bus_ids)
    require(set(gen_ids.astype(int)).issubset(retained), "Interior generator landing invalidates frozen-dispatch reduction")
    dc = np.asarray(source["dcline"]).reshape(-1, 17)
    for label, values in [("from", dc[:, 0] if dc_from_bus_ids is None else dc_from_bus_ids),
                          ("to", dc[:, 1] if dc_to_bus_ids is None else dc_to_bus_ids)]:
        require(set(np.asarray(values, int)).issubset(retained), "Interior DC " + label + " endpoint invalidates zero-injection reduction")
    return dict(interior_injection_zero=True, frozen_generator_landings_retained=True,
                frozen_DC_endpoints_retained=True, asset_mapping_allowed=False)


def expected_generic_operator(source, retained_ids, source_operator):
    reduced = eliminated_response(source, retained_ids)
    operator = np.asarray(source_operator, float)
    require(operator.ndim == 2 and operator.shape[1] == len(source["branch"]), "Source operator branch axis differs")
    return (operator @ reduced["source_flow_angle_map"], operator @ reduced["source_flow_offset"])


def assert_generic_operator(source, retained_ids, source_operator, retained_angle_operator, offset):
    expected_matrix, expected_offset = expected_generic_operator(source, retained_ids, source_operator)
    matrix_error = error(retained_angle_operator, expected_matrix)
    offset_error = error(np.asarray(offset).reshape(-1), expected_offset.reshape(-1))
    require(matrix_error < MATRIX_TOL and offset_error < MW_TOL,
            "Generic operator does not preserve source functional and affine offset")
    return dict(maximum_generic_operator_error_mw_per_rad=matrix_error,
                maximum_generic_operator_offset_error_mw=offset_error)


def passive_residual(source, slim, direct_branch_rows):
    """Subtract retained direct circuits once before constructing equivalents."""
    reduced = eliminated_response(source, np.asarray(slim["bus"])[:, 0].astype(int))
    direct_branch_rows = np.asarray(direct_branch_rows, int)
    require(len(set(direct_branch_rows)) == len(direct_branch_rows), "Direct circuit counted more than once")
    require(np.all((direct_branch_rows >= 1) & (direct_branch_rows <= len(slim["branch"]))), "Invalid retained direct row")
    direct = dict(baseMVA=slim["baseMVA"], bus=slim["bus"], branch=np.asarray(slim["branch"])[direct_branch_rows - 1])
    residual = reduced["B"] - matrices(direct)["B"]
    require(error(residual, residual.T) < MATRIX_TOL and np.max(np.abs(residual.sum(axis=1))) < MATRIX_TOL,
            "Residual is not a symmetric Laplacian")
    offdiagonal = residual.copy(); np.fill_diagonal(offdiagonal, 0)
    require(np.max(offdiagonal) < MATRIX_TOL and np.linalg.eigvalsh(residual).min() >= -MATRIX_TOL,
            "Nonpassive residual or double-counted direct circuit")
    return dict(residual=residual, required_positive_residual_pairs=int((np.triu(residual, 1) < -MATRIX_TOL).sum()))


def source_interface_matrix(case):
    table = np.atleast_2d(np.asarray(case["if"]["map"], float))
    result = np.zeros((7, len(case["branch"])))
    for i, key in enumerate(INTERFACE_IDS):
        for signed in table[table[:, 0] == key, 1]:
            require(signed == int(signed) and 1 <= abs(signed) <= result.shape[1], "Invalid source interface row")
            result[i, abs(int(signed)) - 1] += np.sign(signed)
    return result


def retained_hub_degrees(source, slim, added_ids):
    """Report, rather than conceal, degree-two hubs and Schur fill-in."""
    rows = []
    for bus in added_ids:
        counts = []
        for case in [source, slim]:
            br = np.asarray(case["branch"])
            neighbors = set(br[(br[:, 0] == bus) & (br[:, 10] == 1), 1].astype(int))
            neighbors |= set(br[(br[:, 1] == bus) & (br[:, 10] == 1), 0].astype(int))
            counts.append(len(neighbors))
        require(counts[0] >= 2 and counts[1] >= 2, "Retained hub is a dead-end zero-injection leaf")
        rows.append(dict(bus_id=int(bus), detailed_distinct_neighbors=counts[0], slim_distinct_neighbors=counts[1],
                         degree_two_in_detailed=counts[0] == 2,
                         purpose="named major-corridor/project endpoint" if counts[0] == 2 else "retained multi-terminal station"))
    return rows


def validate_recovery(source, slim, recovery):
    ids = np.asarray(slim["bus"])[:, 0].astype(int)
    reduced = eliminated_response(source, ids)
    mappings = [("angle_lift", reduced["angle_lift"]), ("angle_offset", reduced["angle_offset"]),
                ("branch_angle_matrix", reduced["source_flow_angle_map"]),
                ("branch_flow_offset", reduced["source_flow_offset"])]
    out = {}
    for name, expected in mappings:
        actual = np.asarray(recovery[name])
        if expected.ndim == 1:
            actual = actual.reshape(-1)
        difference = error(actual, expected)
        require(difference < MATRIX_TOL, "Recovery map differs from independent elimination: " + name)
        out["maximum_" + name + "_error"] = difference
    source_operator = source_interface_matrix(source)
    out.update(assert_generic_operator(source, ids, source_operator,
        recovery["interface_angle_matrix"], recovery["interface_flow_offset"]))
    if "full_interface_branch_matrix" in recovery:
        require(error(recovery["full_interface_branch_matrix"], source_operator) == 0,
                "Recorded source interface coefficients changed")
    return out


def equivalent_placeholder_contract(case, equivalent_rows):
    branch = np.asarray(case["branch"])
    rows = np.asarray(equivalent_rows, int) - 1
    require(len(set(rows)) == len(rows) and np.all((rows >= 0) & (rows < len(branch))), "Invalid equivalent row identity")
    values = branch[rows]
    pairs = [tuple(sorted(map(int, row[:2]))) for row in values]
    require(len(set(pairs)) == len(pairs) and all(first != second for first, second in pairs),
            "Equivalent pairs duplicated or self-looped; unnecessary line expansion")
    require(np.all(values[:, [2, 4, 5, 6, 7]] == 0),
            "DC equivalent acquired invented resistance, charging, or thermal rating")
    require(np.isin(values[:, 8], [0., 1.]).all(), "DC equivalent acquired an unsupported nonunity tap")
    require(np.all(values[values[:, 10] == 1, 3] > 0), "Equivalent is not passive")
    return dict(equivalent_row_count=len(rows), R_B_rating_values_are_DC_placeholders=True,
                physical_thermal_or_conductor_claim=False)


def component_provenance(source, slim, components, contributions, full_branch_register, direct_rows):
    """Check that each equivalent's cited interior graph is its actual source."""
    parse = lambda value: set(int(part) for part in str(value).split(";") if part)
    kept = set(np.asarray(slim["bus"])[:, 0].astype(int))
    interior = set(np.asarray(source["bus"])[:, 0].astype(int)) - kept
    source_branch = np.asarray(source["branch"])
    assigned, graphs = set(), {}
    for row in components.itertuples(index=False):
        nodes = parse(row.interior_bus_ids)
        ports = parse(row.retained_port_ids)
        require(nodes and nodes.issubset(interior) and assigned.isdisjoint(nodes), "Interior component duplicated or not eliminated")
        assigned |= nodes
        incident = (source_branch[:, 10] == 1) & np.any(np.isin(source_branch[:, :2], list(nodes)), axis=1)
        rows = set(np.flatnonzero(incident) + 1)
        endpoints = set(source_branch[incident, :2].astype(int).ravel())
        require(endpoints - nodes == ports and ports.issubset(kept), "Component ports omit an active path or cross another interior component")
        require(parse(row.source_branch_rows) == rows, "Component cites incorrect source circuits")
        require(int(row.interior_count) == len(nodes) and int(row.port_count) == len(ports)
                and int(row.structural_pair_count) == len(ports) * (len(ports) - 1) // 2, "Component structural counts differ")
        graphs[int(row.component_id)] = (nodes, ports, rows)
    require(assigned == interior, "Eliminated interior provenance is incomplete")
    residual = passive_residual(source, slim, direct_rows)["residual"]
    ids = np.asarray(slim["bus"])[:, 0].astype(int)
    index = {value: i for i, value in enumerate(ids)}
    seen = set()
    for row in contributions.itertuples(index=False):
        pair = tuple(sorted([int(row.from_bus), int(row.to_bus)]))
        require(pair not in seen, "Equivalent provenance pair duplicated")
        seen.add(pair)
        expected_components = {key for key, (_, ports, _) in graphs.items() if set(pair).issubset(ports)}
        require(parse(row.component_ids) == expected_components and expected_components, "Equivalent cites the wrong interior component")
        rows = set().union(*(graphs[key][2] for key in expected_components))
        require(parse(row.full191_source_branch_rows) == rows, "Equivalent source circuit lineage is incomplete")
        expected_keys = {str(full_branch_register.iloc[value - 1].branch_key) for value in rows}
        require(set(str(row.full191_source_branch_keys).split(";")) == expected_keys, "Equivalent source keys differ from source rows")
        require(str(row.direct_retained_rows_excluded).lower() in {"true", "1"}
                and str(row.pruned_by_magnitude_threshold).lower() in {"false", "0"}, "Equivalent provenance allows double counting or magnitude pruning")
        value = np.asarray(slim["branch"])[int(row.model_branch_row) - 1]
        require(value[10] == 1 and tuple(map(int, value[:2])) == (int(row.from_bus), int(row.to_bus)), "Equivalent record is not its active case branch")
        expected_weight = -residual[index[pair[0]], index[pair[1]]]
        require(abs(float(row.weight_MW_per_rad) - expected_weight) < MATRIX_TOL
                and abs(float(row.x_pu) - value[3]) < 1e-12, "Equivalent documented weight differs from derived residual")
    required_pairs = {tuple(sorted([int(ids[i]), int(ids[j])])) for i, j in np.argwhere(np.triu(residual, 1) < -MATRIX_TOL)}
    require(seen == required_pairs, "Positive equivalent connection omitted from contribution register")
    return dict(eliminated_components=len(graphs), equivalent_contribution_rows=len(seen), complete_circuit_lineage_checked=True)


def verify_construction(folder=DEFAULT):
    folder = Path(folder).resolve()
    path = folder / "network/network_cases.mat"
    data, full = [loadmat(p, simplify_cells=True) for p in [path, SOURCE]]
    branch = pd.read_csv(folder / "network/branch_register.csv", keep_default_na=False)
    bus = pd.read_csv(folder / "network/bus_register.csv", keep_default_na=False)
    full_branch = pd.read_csv(SOURCE.parent / "branch_register.csv", keep_default_na=False)
    rationale = pd.read_csv(folder / "network/retained_station_rationale.csv", keep_default_na=False)
    component_register = pd.read_csv(folder / "network/eliminated_component_register.csv", keep_default_na=False)
    contribution_register = pd.read_csv(folder / "network/equivalent_contribution_register.csv", keep_default_na=False)
    ids = np.asarray(data["kept_bus_ids"], int).reshape(-1)
    eliminated = np.asarray(data["eliminated_bus_ids"], int).reshape(-1)
    require(len(ids) == 148 and np.array_equal(ids[:140], np.arange(1, 141)) and set(ids[140:]) == CORE_IDS,
            "All140 original buses plus precisely eight declared hubs required")
    require(len(eliminated) == 43 and set(eliminated).isdisjoint(set(range(1, 141))), "Original bus was eliminated or extra detail remains")
    require(set(ids) | set(eliminated) == set(np.asarray(full["refined_2025_case"]["bus"])[:, 0].astype(int)), "Retained/eliminated partition differs")
    require(np.array_equal(bus.model_bus.to_numpy(int), ids) and bus.model_bus.is_unique, "Bus identity register differs")
    require(int(bus.accounting_zone.eq("NA").sum()) == 94 and int(bus.accounting_zone.ne("NA").sum()) == 54,
            "Original full external network not preserved")
    require(np.array_equal(branch.model_branch_row, np.arange(1, len(branch) + 1)) and branch.branch_key.is_unique,
            "Branch row identity differs")
    require(len(branch) == 274 and branch.role.value_counts().to_dict() == {
        "original_parent_record": 225, "exact_retained_source_circuit": 14,
        "retained_declared_assumption": 5, "passive_DC_Schur_equivalent": 30}, "Declared physical/proxy/equivalent counts differ")
    require(not branch.thermal_dlr_eligible.astype(str).str.lower().isin(["true", "1"]).any(), "Unqualified connection acquired DLR eligibility")
    require(set(rationale.model_bus.astype(int)) == CORE_IDS and rationale.rationale.astype(str).str.len().gt(30).all(),
            "Retained station lacks an explicit purpose")
    require(data["full_source_sha256"] == sha(SOURCE), "Frozen191 source fingerprint changed")
    require("no_asset_remap" in data["injection_contract"], "Zero-interior injection restriction not disclosed")
    for name in ["bus", "branch", "gen", "dcline"]:
        require(error(data["parent_case"][name], full["parent_case"][name]) == 0, "Original parent metadata changed: " + name)
    source_rows = branch.full191_branch_row.to_numpy(int)
    direct = source_rows > 0
    equivalent = ~direct
    direct_rows = branch.loc[direct, "model_branch_row"].to_numpy(int)
    equivalent_rows = branch.loc[equivalent, "model_branch_row"].to_numpy(int)
    require(len(set(source_rows[direct])) == int(direct.sum()), "A full191 direct circuit was copied more than once")
    require(np.array_equal(source_rows[:225], np.arange(1, 226)), "Original branch records reordered")
    for row in branch.loc[direct].itertuples(index=False):
        original = full_branch.iloc[int(row.full191_branch_row) - 1]
        require(row.branch_key == original.branch_key and int(row.source_PERFORM_row) == int(original.source_branch_row),
                "Direct circuit provenance altered")
    case_keys = [key for key in data if key.endswith("_case") and key != "parent_case"]
    require(set(case_keys) == {name + "_case" for name in ["refined_2019", "refined_2025_pre_may", "refined_2025_may21", "refined_2025_may30", "refined_2025"]},
            "Expected five dated source network states")
    ever_active = np.any([np.asarray(full[key]["branch"])[225:, 10] == 1 for key in case_keys], axis=0)
    endpoints_retained = np.all(np.isin(np.asarray(full[case_keys[0]]["branch"])[225:, :2], ids), axis=1)
    expected_direct = np.r_[np.arange(1, 226), np.flatnonzero(ever_active & endpoints_retained) + 226]
    require(np.array_equal(np.sort(source_rows[direct]), expected_direct), "Direct retained source circuit missing or extra")
    cases, operators = [], []
    for key in case_keys:
        name = key.removesuffix("_case")
        source, case, rec = full[key], data[key], data["recovery"][name]
        require(np.array_equal(np.asarray(case["bus"])[:, 0], ids), "Case bus order differs")
        lookup = {int(value): i for i, value in enumerate(source["bus"][:, 0])}
        take = [lookup[value] for value in ids]
        require(error(case["bus"], source["bus"][take]) == 0, "Retained source bus record changed")
        for field in ["gen", "dcline"]:
            require(error(case[field], source[field]) == 0, "Frozen devices changed: " + field)
        require(error(case["branch"][direct], source["branch"][source_rows[direct] - 1]) == 0, "Direct circuit parameter/status altered")
        for suffix, column in [("status", 10), ("x_pu", 3), ("shift_degree", 9)]:
            require(error(case["branch"][:, column], branch[name + "_" + suffix]) < 1e-12, "Per-state branch ledger differs")
        result = assert_dc_equivalence(source, case)
        result.update(zero_interior_injection_contract(source, ids))
        result.update(validate_recovery(source, case, rec))
        result.update(equivalent_placeholder_contract(case, equivalent_rows))
        residual = passive_residual(source, case, direct_rows)
        result.update(component_provenance(source, case, component_register.loc[component_register.variant.eq(name)],
            contribution_register.loc[contribution_register.variant.eq(name)], full_branch, direct_rows))
        eq_case = dict(baseMVA=case["baseMVA"], bus=case["bus"], branch=case["branch"][equivalent])
        require(error(matrices(eq_case)["B"], residual["residual"]) < MATRIX_TOL, "Equivalent budget double-counts or omits direct circuits")
        active_equivalents = int((case["branch"][equivalent, 10] == 1).sum())
        require(active_equivalents == residual["required_positive_residual_pairs"], "Equivalent count does not match positive Schur pairs")
        require(rec["angle_units"] == "radians" and rec["operator_units"] == "model_MW_per_radian" and rec["offset_units"] == "model_MW",
                "Recovery operator units are ambiguous")
        independent = eliminated_response(source, ids)
        require(error(rec["Schur_B"], independent["B"]) < MATRIX_TOL and error(rec["Schur_phase"], independent["nodal_phase"]) < MW_TOL,
                "Saved Schur certificate differs")
        require(error(rec["injection_projection"], independent["injection_projection"]) < MATRIX_TOL,
                "Saved injection projection differs")
        require(np.array_equal(np.asarray(rec["retained_full_indices_1based"], int), np.asarray(take) + 1), "Recovery retained-index axis differs")
        net = matrices(case)
        local = np.asarray(rec["local_interface_branch_matrix"])
        expected_H, expected_c = expected_generic_operator(source, ids, source_interface_matrix(source))
        local_H = local @ (net["b"][:, None] * net["C"])
        local_c = local @ net["branch_phase"]
        local_error = np.max(np.abs(local_H - expected_H), axis=1)
        local_offset_error = np.abs(local_c - expected_c)
        exact_ids = [number for j, number in enumerate(INTERFACE_IDS) if local_error[j] < MATRIX_TOL and local_offset_error[j] < MW_TOL]
        saved_if_ids = sorted(set(np.asarray(case["if"]["map"])[:, 0].astype(int)))
        require(saved_if_ids == exact_ids == [1, 2, 3, 4, 5, 8], "Integer branch interface map misrepresents generic recovery")
        require(10 in np.asarray(case["if"]["omitted_interface_ids"]).reshape(-1), "Dun functional must use generic recovery")
        for j, number in enumerate(INTERFACE_IDS):
            operators.append(dict(variant=name, interface_id=number, interface=INTERFACE_NAMES[j],
                native_branch_map_exact=number in exact_ids, local_angle_coefficient_error_mw_per_rad=float(local_error[j]),
                generic_operator_validated=True, physical_2025_flowgate_membership_verified=False))
        result.update(variant=name, active_branches=int((case["branch"][:, 10] == 1).sum()),
                      original_active_branches=int((case["branch"][:225, 10] == 1).sum()),
                      active_exact_source_circuits=14,
                      active_declared_proxies=int((case["branch"][branch.role.eq("retained_declared_assumption"), 10] == 1).sum()),
                      active_DC_equivalents=active_equivalents)
        cases.append(result)
    degrees = retained_hub_degrees(full["refined_2025_case"], data["refined_2025_case"], ids[140:])
    for row in degrees:
        source_row = rationale.loc[rationale.model_bus.eq(row["bus_id"])].iloc[0]
        require(row["detailed_distinct_neighbors"] == int(source_row.active_full191_unique_neighbor_count), "Retained hub degree rationale changed")
        row["documented_rationale"] = source_row.rationale
    manifest = pd.read_csv(folder / "network/source_manifest.csv", keep_default_na=False)
    for row in manifest.itertuples(index=False):
        require(sha(ROOT / row.path) == row.sha256, "Source dependency fingerprint changed: " + row.path)
    files = [folder / "network" / name for name in ["network_cases.mat", "branch_register.csv", "bus_register.csv",
        "eliminated_bus_register.csv", "eliminated_component_register.csv", "equivalent_contribution_register.csv", "retained_station_rationale.csv", "source_manifest.csv"]]
    files += [SOURCE, Path(__file__)]
    out = folder / "validation"; out.mkdir(parents=True, exist_ok=True)
    summary = dict(passed=True, original_buses=140, added_hubs=8, NY_buses=54, external_buses=94,
        total_buses=148, eliminated_added_buses=43, branch_records=274, year_end_active_branches=265,
        added_connection_record_breakdown=dict(historical_source_circuits=14, declared_proxies=5, DC_equivalents=30),
        phase_and_generic_operator_scope="exact DC affine response and full191 source branch/interface recovery at zero interior injection",
        asset_mapping_allowed=False, AC_or_thermal_equivalence_claimed=False,
        cases=cases, files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in files])
    (out / "construction_validation.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(cases).to_csv(out / "construction_case_checks.csv", index=False, lineterminator="\n")
    pd.DataFrame(operators).to_csv(out / "interface_operator_checks.csv", index=False, lineterminator="\n")
    pd.DataFrame(degrees).to_csv(out / "retained_hub_degree_audit.csv", index=False, lineterminator="\n")
    return summary


def verify_annual(folder=DEFAULT):
    folder = Path(folder).resolve()
    independent_path = ROOT / "scripts/nygrid_2025_dispatch/validate_dispatch.py"
    specification = importlib.util.spec_from_file_location("independent_slim_electrical_audit", independent_path)
    module = importlib.util.module_from_spec(specification); specification.loader.exec_module(module)
    electrical_audit = module.electrical_audit
    source_hash_before = sha(SOURCE)
    n, full, d = [loadmat(path, simplify_cells=True) for path in [folder / "network/network_cases.mat", SOURCE, BASELINE / "dispatch.mat"]]
    ids = np.asarray(n["kept_bus_ids"], int).reshape(-1)
    hours = np.asarray(d["hour_index"], int).reshape(-1)
    valid = np.asarray(d["dispatch_qualified"], bool).reshape(-1)
    times = np.asarray(d["timestamp_utc"]).astype(str)
    gamma = float(d["gamma"])
    require(np.array_equal(hours, np.arange(1, 8761)) and int(valid.sum()) == 8663, "Frozen annual cohort changed")
    receipt_path = folder / "replay/provenance.json"
    receipt = json.loads(receipt_path.read_text())
    require(receipt["inputs_redispatched_or_relocated"] is False and receipt["observations_used_for_construction"] is False,
            "Replay input or fitting scope changed")
    require({item["variant"] for item in receipt["variants"]} == {"topology_dated", "topology_year_end"}, "Expected two primary identity-landing scenarios")
    for row in receipt["dependencies"]:
        require(sha(ROOT / row["path"]) == row["sha256"], "Replay source fingerprint changed: " + row["path"])
    scalar_load = np.zeros((8760, len(ids))); scalar_load[:, :140] = d["bus_pd"]
    reactive_load = np.zeros_like(scalar_load); reactive_load[:, :140] = d["bus_qd"]
    full_load = np.zeros((8760, 191)); full_load[:, :140] = d["bus_pd"]
    full_qd = np.zeros_like(full_load); full_qd[:, :140] = d["bus_qd"]
    require(error(scalar_load.sum(axis=1), np.asarray(d["bus_pd"]).sum(axis=1)) < MW_TOL and
            error(reactive_load.sum(axis=1), np.asarray(d["bus_qd"]).sum(axis=1)) < MW_TOL, "Gross P/Q totals changed")
    upgrades_path = ROOT / "output/nygrid_2025_downstate/sources/upgrade_register.csv"
    upgrades = pd.read_csv(upgrades_path, keep_default_na=False)
    expected_dated = np.full(8760, "refined_2025_pre_may_case", dtype=object)
    utc = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    for project, key in [("RCC_Gowanus_Greenwood", "refined_2025_may21_case"),
                         ("RCC_Goethals_FoxHills", "refined_2025_may30_case"),
                         ("Dover_Segment_B_final", "refined_2025_case")]:
        dates = upgrades.loc[upgrades.project.eq(project), "conservative_scenario_activation_local"].unique()
        require(len(dates) == 1, "Ambiguous commissioning source date")
        expected_dated[utc >= pd.Timestamp(dates[0]).tz_convert("UTC")] = key
    rows, hourly, files, predictions = [], [], [], {}
    for item in receipt["variants"]:
        variant = item["variant"]
        path, reference_path = ROOT / item["file"], ROOT / item["reference_file"]
        require(sha(path) == item["sha256"] and sha(reference_path) == item["reference_sha256"], "Paired replay fingerprint changed")
        replay, reference = [loadmat(p, simplify_cells=True) for p in [path, reference_path]]
        files += [path, reference_path]
        for saved in [replay, reference]:
            require(np.array_equal(np.asarray(saved["hour_index"], int), hours)
                    and np.array_equal(np.asarray(saved["qualified"], bool), valid)
                    and np.array_equal(np.asarray(saved["timestamp_utc"]).astype(str), times), "Paired hour/source axes differ")
            require(float(saved["gamma"]) == gamma, "Paired gamma differs")
        require(np.array_equal(np.asarray(replay["kept_bus_ids"], int), ids), "Replay retained bus axis differs")
        require(np.array_equal(np.asarray(replay["reference_bus"], int), np.asarray(d["reference_bus"], int)), "Reference bus changed")
        states = np.asarray(replay["network_state_ids"]).astype(str)
        expected = expected_dated if variant == "topology_dated" else np.full(8760, "refined_2025_case")
        require(np.array_equal(states, expected) and np.array_equal(states, np.asarray(reference["network_state_ids"]).astype(str)),
                "Source commissioning/fixed-year-end states differ")
        for key, width in [("branch_pf", 274), ("bus_va", 148), ("interface_pf", 7)]:
            require(np.shape(replay[key]) == (8760, width) and np.isnan(replay[key][~valid]).all()
                    and np.isfinite(replay[key][valid]).all(), "Missing/source-qualified replay values changed")
        metrics = {key: np.full(8760, np.nan) for key in ["slim_nodal_residual_mw", "slim_independent_branch_error_mw",
            "slim_independent_angle_error_deg", "recovered191_nodal_residual_mw", "recovered191_reference_branch_error_mw",
            "recovered191_reference_angle_error_deg", "recovered191_interface_error_mw", "saved_generic_operator_error_mw"]}
        for key in sorted(set(states)):
            selected = np.flatnonzero(valid & (states == key))
            source, case, rec = full[key], n[key], n["recovery"][key.removesuffix("_case")]
            zero_interior_injection_contract(source, ids, pd=full_load, qd=full_qd)
            require(error(case["gen"], d["base_case"]["gen"]) == 0 and error(case["dcline"], d["base_case"]["dcline"]) == 0,
                    "Frozen unit template or DC channels changed")
            result = electrical_audit(case, scalar_load[selected], np.asarray(d["gen_pg"])[selected], np.asarray(d["dc_pf"])[selected],
                replay["branch_pf"][selected], replay["bus_va"][selected], np.asarray(d["reference_bus"])[selected])
            for from_key, to_key in [("nodal_residual_mw", "slim_nodal_residual_mw"),
                                     ("independent_branch_error_mw", "slim_independent_branch_error_mw"),
                                     ("independent_angle_error_deg", "slim_independent_angle_error_deg")]:
                metrics[to_key][selected] = result[from_key]
            # Recompute recovery from the full191 equations, not saved maps.
            proof = eliminated_response(source, ids)
            radians = np.deg2rad(replay["bus_va"][selected])
            recovered_flow = radians @ proof["source_flow_angle_map"].T + proof["source_flow_offset"]
            recovered_angle = np.rad2deg(radians @ proof["angle_lift"].T + proof["angle_offset"])
            operator = source_interface_matrix(source)
            recovered_interface = recovered_flow @ operator.T
            detailed = electrical_audit(source, full_load[selected], np.asarray(d["gen_pg"])[selected], np.asarray(d["dc_pf"])[selected],
                recovered_flow, recovered_angle, np.asarray(d["reference_bus"])[selected])
            metrics["recovered191_nodal_residual_mw"][selected] = detailed["nodal_residual_mw"]
            metrics["recovered191_reference_branch_error_mw"][selected] = np.max(np.abs(recovered_flow - reference["branch_pf"][selected]), axis=1)
            metrics["recovered191_reference_angle_error_deg"][selected] = np.max(np.abs(recovered_angle - reference["bus_va"][selected]), axis=1)
            metrics["recovered191_interface_error_mw"][selected] = np.max(np.abs(recovered_interface - reference["interface_pf"][selected]), axis=1)
            metrics["saved_generic_operator_error_mw"][selected] = np.max(np.abs(recovered_interface - replay["interface_pf"][selected]), axis=1)
        for key, values in metrics.items():
            require(np.isfinite(values[valid]).all() and float(values[valid].max()) < MW_TOL,
                    "Independent paired DC audit failed: " + key)
        require(float(np.max(np.abs(replay["slack_change_mw"][valid]))) < MW_TOL, "Replay required balancing redispatch")
        row = dict(variant=variant, passed=True, qualified_hours=8663, source_gap_hours=97,
                   per_unit_PG_bounds_original_PD_QD_and_four_DC_channels_unchanged=True,
                   **{"maximum_" + key: float(values[valid].max()) for key, values in metrics.items()})
        rows.append(row); print(json.dumps(row), flush=True)
        hourly.append(pd.DataFrame(dict(variant=variant, hour_index=hours[valid], timestamp_utc=times[valid],
                                       **{key: values[valid] for key, values in metrics.items()})))
        predictions[variant + "_148bus"] = replay["interface_pf"]
        predictions[item["reference_variant"] + "_191bus"] = reference["interface_pf"]
    # Independently verify all original/full/slim published post-hoc rows.
    old_network = loadmat(BASELINE / "dispatch_network.mat", simplify_cells=True, variable_names=["inherited_interface_pf"])
    predictions["original140"] = old_network["inherited_interface_pf"]
    observation_path = ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv"
    observation = pd.read_csv(observation_path)
    require(np.array_equal(observation.timestamp_utc.astype(str), times), "Observation timestamp axis differs")
    actual = observation[INTERFACE_NAMES].to_numpy(float)
    require(np.isfinite(actual[valid]).all(), "Observation missing from fixed source cohort")
    published_path = folder / "comparison/interface_summary.csv"
    published = pd.read_csv(published_path).set_index(["variant", "interface"])
    require(len(published) == 35 and published.index.is_unique, "Expected35 unique original/full/slim score rows")
    scores = []
    for name, prediction in predictions.items():
        for j, interface in enumerate(INTERFACE_NAMES):
            delta = prediction[valid, j] / gamma - actual[valid, j]
            mae = float(np.abs(delta).mean())
            wape = float(100 * np.abs(delta).sum() / np.abs(actual[valid, j]).sum())
            saved = published.loc[(name, interface)]
            require(int(saved.hours) == 8663 and abs(saved.mae_public_equivalent_mw - mae) < 1e-9
                    and abs(saved.wape_percent - wape) < 1e-10, "Published score differs from independent fixed-cohort calculation")
            scores.append(dict(variant=name, interface=interface, hours=8663, mae_public_equivalent_mw=mae, wape_percent=wape,
                               physical_2025_flowgate_membership_verified=False))
    require(sha(SOURCE) == source_hash_before == n["full_source_sha256"], "Frozen191 source changed during validation")
    files += [receipt_path, folder / "network/network_cases.mat", SOURCE, BASELINE / "dispatch.mat", BASELINE / "dispatch_bounds.mat",
              observation_path, published_path, upgrades_path, independent_path, Path(__file__)]
    summary = dict(passed=True, original_network_source_unchanged=True, source191_sha256=source_hash_before,
        primary_variants=2, qualified_hours_per_variant=8663, independently_solved_slim_hours=17326,
        recovered191_KCL_checked_hours=17326, source_gap_hours_per_variant=97, published_score_rows_verified=35,
        usable_scope="exact source191 primary DC response with frozen original140 injections and recovered interfaces",
        asset_remapping_AC_and_thermal_qualification=False, variants=rows,
        files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in files])
    out = folder / "validation"; out.mkdir(parents=True, exist_ok=True)
    (out / "annual_validation.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(out / "annual_variant_checks.csv", index=False, lineterminator="\n")
    pd.concat(hourly, ignore_index=True).to_csv(out / "independent_hourly_checks.csv.gz", index=False,
        lineterminator="\n", compression={"method": "gzip", "mtime": 0})
    pd.DataFrame(scores).to_csv(out / "independent_interface_scores.csv", index=False, lineterminator="\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=DEFAULT)
    parser.add_argument("--construction-only", action="store_true")
    args = parser.parse_args()
    result = verify_construction(args.folder)
    print(json.dumps({"construction_passed": result["passed"], "cases": len(result["cases"])}), flush=True)
    if not args.construction_only:
        result = verify_annual(args.folder)
        print(json.dumps({"annual_passed": result["passed"], "independently_solved_slim_hours": result["independently_solved_slim_hours"],
                          "published_score_rows_verified": result["published_score_rows_verified"]}), flush=True)
