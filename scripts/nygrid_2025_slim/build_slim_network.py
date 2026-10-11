"""Keep the complete 140-bus NPCC backbone and eight transmission stations.

Only 43 added, zero-injection interior buses of the frozen 191-bus construction
are eliminated. Direct retained-endpoint rows are copied exactly. Their
admittance is excluded from the component Schur reductions, so passive fill-in
does not duplicate retained physical circuits. Structural component boundaries
determine all equivalent edges; no impedance or flow threshold drops an edge.

This is a DC-only equivalence under zero eliminated-bus injections. Equivalent
R/B/rating zero fields are DC placeholders, not physical resistance, charging,
ampacity, or an infinite thermal capability claim. Source branch flows and the
seven source measurement functionals are recovered from retained radians.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[2]
SOURCE_FOLDER = ROOT / "output/nygrid_2025_downstate/network"
SOURCE_CASES = SOURCE_FOLDER / "network_cases.mat"
PINNED_SOURCE_SHA = "89af6622ece7539d4056e3840ebda6059afcc830f0afbbdab749c43d90a503e4"
DEFAULT = ROOT / "output/nygrid_2025_slim/network"
KEEP_ADDED = [10774, 10858, 10902, 10593, 10589, 11129, 11130, 20001]
VARIANTS = ["refined_2019", "refined_2025_pre_may", "refined_2025_may21",
            "refined_2025_may30", "refined_2025"]
INTERFACES = [(1, "DYSINGER EAST", "A", "B"), (2, "WEST CENTRAL", "B", "C"),
              (3, "TOTAL EAST", "ABCDE", "FGHIJK"), (4, "MOSES SOUTH", "D", "E"),
              (5, "CENTRAL EAST - VC", "E", "F"), (8, "UPNY CONED", "ABCDEFG", "HIJK"),
              (10, "SPR/DUN-SOUTH", "I", "J")]
MATRIX_TOL = 1e-8
RATIONALE = {
    10774: "Named Ladentown terminal separates the registered Ramapo-Ladentown and Ladentown-Buchanan source circuits; retained as a transmission-path waypoint despite degree2.",
    10858: "East Fishkill distinguishes the two PleasantValley-EastFishkill and two EastFishkill-WoodStreet circuits from the direct PleasantValley-WoodStreet circuits; degree2 by neighbors but four physical circuit rows.",
    10902: "Wood Street retains the junction of the PleasantValley,EastFishkill and Millwood transmission paths.",
    10593: "Dunwoodie345 retains the main ZoneI delivery junction and its explicit CEUG aggregate attachment.",
    10589: "EastGardenCity345 retains the LongIsland delivery port and separates that port from the RAVA3 ZoneK aggregate proxy.",
    11129: "Gowanus345 retains the StatenIsland/Brooklyn delivery port and declared Goethals regional attachment.",
    11130: "Rainey345 retains the Queens receiving port and exposes the Rainey-Corona project response in the condensed network.",
    20001: "CricketValley345 retains the dated PV-CV F83/F84 and CV-LongMountain/Dover path boundary; degree2 is intentional station-level path identification, not a copied generator injection.",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def maxabs(values):
    return float(np.max(np.abs(values), initial=0.))


def dc(case):
    bus, branch = np.asarray(case["bus"], float), np.asarray(case["branch"], float)
    ids = bus[:, 0].astype(int)
    require(len(set(ids)) == len(ids), "Duplicate bus IDs")
    lookup = {bid: j for j, bid in enumerate(ids)}
    C = np.zeros((len(branch), len(ids)))
    for j, row in enumerate(branch):
        C[j, lookup[int(row[0])]] += 1
        C[j, lookup[int(row[1])]] -= 1
    tap = np.where(branch[:, 8] == 0, 1., branch[:, 8])
    require(np.all(tap > 0) and np.all(branch[:, 3] != 0), "Invalid DC impedance/tap")
    w = float(case["baseMVA"]) * branch[:, 10] / (branch[:, 3] * tap)
    phase = -w * np.deg2rad(branch[:, 9])
    F = w[:, None] * C
    return dict(ids=ids, lookup=lookup, C=C, w=w, B=C.T @ F, F=F,
                phase_branch=phase, phase_bus=C.T @ phase)


def zone_operators(case, zones):
    operators = np.zeros((7, len(case["branch"])))
    for j, (_, _, left, right) in enumerate(INTERFACES):
        for k, row in enumerate(case["branch"]):
            a, b = zones[int(row[0])], zones[int(row[1])]
            operators[j, k] = row[10] * (int(a in list(left) and b in list(right)) - int(b in list(left) and a in list(right)))
    return operators


def components(interior, branch):
    """Exact active graph components; isolated dangling nodes remain visible."""
    inside = set(interior)
    adjacency = {bid: set() for bid in interior}
    for row in branch:
        a, b = map(int, row[:2])
        if row[10] and a in inside and b in inside:
            adjacency[a].add(b)
            adjacency[b].add(a)
    remaining, result = set(interior), []
    while remaining:
        root = min(remaining)
        part, stack = set(), [root]
        while stack:
            node = stack.pop()
            if node in part:
                continue
            part.add(node)
            stack.extend(adjacency[node] - part)
        remaining -= part
        result.append(sorted(part))
    return result


def reduce_added_components(case, keep_ids):
    """Return direct rows, all structural fill-in edges, and affine recovery."""
    net = dc(case)
    keep = np.asarray(keep_ids, int)
    require(len(set(keep)) == len(keep) and np.isin(keep, net["ids"]).all(), "Invalid retained bus set")
    kept = set(keep)
    interior = [int(bid) for bid in net["ids"] if bid not in kept]
    ri = np.array([net["lookup"][bid] for bid in keep], int)
    ii = np.array([net["lookup"][bid] for bid in interior], int)
    bus, branch = np.asarray(case["bus"]), np.asarray(case["branch"])
    require(np.all(bus[ii, 2:6] == 0), "Eliminated bus has PD/QD/GS/BS; zero-injection contract violated")
    if "gen" in case:
        require(not np.isin(np.atleast_2d(case["gen"])[:, 0], interior).any(), "Eliminated bus has a generator record")
    if "dcline" in case:
        require(not np.isin(np.atleast_2d(case["dcline"])[:, :2], interior).any(), "Eliminated bus is a DC-link terminal")
    direct = np.flatnonzero(np.isin(branch[:, 0], keep) & np.isin(branch[:, 1], keep))
    lift = np.zeros((len(bus), len(keep)))
    lift[ri] = np.eye(len(keep))
    offset = np.zeros(len(bus))
    projection = np.zeros((len(keep), len(bus)))
    projection[:, ri] = np.eye(len(keep))
    if len(ii):
        Lii, Lir = net["B"][np.ix_(ii, ii)], net["B"][np.ix_(ii, ri)]
        lift[ii] = -np.linalg.solve(Lii, Lir)
        offset[ii] = -np.linalg.solve(Lii, net["phase_bus"][ii])
        projection[:, ii] = -np.linalg.solve(Lii.T, net["B"][np.ix_(ri, ii)].T).T
    reduced_B = projection @ net["B"][:, ri]
    reduced_phase = projection @ net["phase_bus"]
    edges = {}
    component_records = []
    for cid, part in enumerate(components(interior, branch), 1):
        part_set = set(part)
        source_rows = [j for j, row in enumerate(branch) if row[10] and
                       (int(row[0]) in part_set or int(row[1]) in part_set)]
        ports = sorted({int(value) for j in source_rows for value in branch[j, :2] if int(value) in kept})
        require(bool(ports), "Unattached eliminated component")
        local_ids = ports + part
        indices = [net["lookup"][bid] for bid in local_ids]
        # Only rows touching an interior bus enter this Schur complement.
        # All physical/assumed direct retained rows are excluded exactly.
        C = net["C"][np.ix_(source_rows, indices)]
        weights = net["w"][source_rows]
        require(np.all(weights > 0), "Nonpassive added interior branch cannot form passive equivalent")
        L = C.T @ (weights[:, None] * C)
        q = C.T @ net["phase_branch"][source_rows]
        p = len(ports)
        reduced = L[:p, :p] - L[:p, p:] @ np.linalg.solve(L[p:, p:], L[p:, :p])
        phase = q[:p] - L[:p, p:] @ np.linalg.solve(L[p:, p:], q[p:])
        require(maxabs(reduced-reduced.T) < MATRIX_TOL and maxabs(reduced.sum(axis=1)) < MATRIX_TOL,
                "Component Schur matrix is not a symmetric Laplacian")
        require(abs(phase.sum()) < MATRIX_TOL, "Component affine injection is not balanced")
        check_B = np.zeros((p, p))
        if p > 1:
            potential = np.zeros(p)
            potential[1:] = np.linalg.solve(reduced[1:, 1:], phase[1:])
            for a, b in itertools.combinations(range(p), 2):
                conductance = float(-.5 * (reduced[a, b] + reduced[b, a]))
                # Connected interiors imply every boundary pair is coupled.
                # Do not suppress small positive terms or silently clip negatives.
                require(conductance > 0 and np.isfinite(conductance), "Lost or nonpassive structural fill-in edge")
                pair = (ports[a], ports[b])
                item = edges.setdefault(pair, dict(weight=0., phase_flow=0., component_ids=[], source_rows=[]))
                item["weight"] += conductance
                item["phase_flow"] += conductance * (potential[a]-potential[b])
                item["component_ids"].append(cid)
                item["source_rows"].extend(j+1 for j in source_rows)
                check_B[a, a] += conductance
                check_B[b, b] += conductance
                check_B[a, b] -= conductance
                check_B[b, a] -= conductance
        require(maxabs(check_B-reduced) < MATRIX_TOL, "Complete fill-in does not recover component Schur matrix")
        component_records.append(dict(component_id=cid, interior_bus_ids=part, retained_port_ids=ports,
                                      source_branch_rows=[j+1 for j in source_rows], interior_count=len(part), port_count=p,
                                      structural_pair_count=p*(p-1)//2,
                                      disposition="zero_port_response_single_attachment" if p == 1 else "all_boundary_pairs_retained",
                                      maximum_reconstruction_error=maxabs(check_B-reduced)))
    for pair, item in edges.items():
        item["x_pu"] = float(case["baseMVA"]) / item["weight"]
        item["shift_degree"] = float(np.rad2deg(-item["phase_flow"] / item["weight"]))
    return dict(retained_indices=ri, eliminated_indices=ii, eliminated_bus_ids=np.asarray(interior, int),
                direct_rows=direct, edges=edges, components=component_records, angle_lift=lift, angle_offset=offset,
                injection_projection=projection, Schur_B=reduced_B, Schur_phase=reduced_phase,
                branch_angle_matrix=net["F"] @ lift,
                branch_flow_offset=net["F"] @ offset + net["phase_branch"])


def build(output=DEFAULT):
    output = Path(output).resolve()
    require(not (output / "network_cases.mat").exists(), "Choose a fresh output folder")
    require(sha(SOURCE_CASES) == PINNED_SOURCE_SHA, "Frozen 191-bus construction changed")
    source = loadmat(SOURCE_CASES, simplify_cells=True)
    source_register = pd.read_csv(SOURCE_FOLDER / "branch_register.csv", keep_default_na=False)
    source_buses = pd.read_csv(SOURCE_FOLDER / "bus_register.csv", keep_default_na=False)
    keep = np.array(list(range(1, 141)) + KEEP_ADDED)
    zones = dict(zip(source_buses.model_bus, source_buses.accounting_zone))
    require(source_register.branch_key.is_unique, "Source branch keys are not unique")
    cases = {name: source[name+"_case"] for name in VARIANTS}
    reductions = {name: reduce_added_components(case, keep) for name, case in cases.items()}
    direct_rows = sorted({int(j) for r in reductions.values() for j in r["direct_rows"]
                          if j < 225 or any(c["branch"][j, 10] for c in cases.values())})
    require(direct_rows[:225] == list(range(225)), "Original parent branch records must all survive")
    require(len(direct_rows) == 244, "Unexpected retained direct branch count")
    pairs = sorted({pair for r in reductions.values() for pair in r["edges"]})
    require(len(pairs) == 30, "Unexpected structural fill-in support")
    branch_keys = source_register.iloc[direct_rows].branch_key.tolist() + [f"DC_EQ:{a}:{b}" for a,b in pairs]
    busreg = source_buses.set_index("model_bus").loc[keep].reset_index()
    register, component_rows, equivalent_rows, recovery, output_cases, validation = [], [], [], {}, {}, []
    for nr, oldrow in enumerate(direct_rows, 1):
        old = source_register.iloc[oldrow]
        role = "original_parent_record" if oldrow < 225 else (
            "exact_retained_source_circuit" if old.electrical_role == "exact_historical_source_circuit" else "retained_declared_assumption")
        register.append(dict(model_branch_row=nr, branch_key=old.branch_key, from_bus=int(old.from_bus), to_bus=int(old.to_bus),
                             role=role, full191_branch_row=oldrow+1, source_PERFORM_row=int(old.source_branch_row),
                             parameter_basis=old.parameter_basis, physical_source_row_exact=role == "exact_retained_source_circuit",
                             equivalent_r_b_rating_fields="not_applicable_copied_row", thermal_dlr_eligible=False))
    for offset, (a,b) in enumerate(pairs, len(direct_rows)+1):
        register.append(dict(model_branch_row=offset, branch_key=f"DC_EQ:{a}:{b}", from_bus=a, to_bus=b,
                             role="passive_DC_Schur_equivalent", full191_branch_row=0, source_PERFORM_row=0,
                             parameter_basis="complete_component_Schur_at_zero_eliminated_injection",
                             physical_source_row_exact=False, equivalent_r_b_rating_fields="R0_B0_RATE0_DC_placeholders_unrated_not_physical", thermal_dlr_eligible=False))
    for name, full in cases.items():
        reduced = reductions[name]
        case = copy.deepcopy(full)
        case["bus"] = full["bus"][reduced["retained_indices"]].copy()
        case["bus_name"] = np.asarray(full["bus_name"])[reduced["retained_indices"]]
        direct = full["branch"][direct_rows, :13].copy()
        added = []
        for pair in pairs:
            active = pair in reduced["edges"]
            item = reduced["edges"].get(pair)
            if item is None:
                # Inactive rows keep a real equivalent parameter from a state
                # where that graph pair exists, avoiding NaNs or invented X.
                item = next(r["edges"][pair] for r in reductions.values() if pair in r["edges"])
            a,b = pair
            added.append([a,b,0.,item["x_pu"],0.,0.,0.,0.,1.,item["shift_degree"],int(active),-360.,360.])
        case["branch"] = np.r_[direct, np.asarray(added)]
        candidate = dc(case)
        B_error = maxabs(candidate["B"]-reduced["Schur_B"])
        phase_error = maxabs(candidate["phase_bus"]-reduced["Schur_phase"])
        require(B_error < MATRIX_TOL and phase_error < MATRIX_TOL, "Slim circuit realization differs from exact Schur response")
        full_operator = zone_operators(full, zones)
        H = full_operator @ reduced["branch_angle_matrix"]
        h = full_operator @ reduced["branch_flow_offset"]
        local_operator = zone_operators(case, zones)
        local_H = local_operator @ candidate["F"]
        local_h = local_operator @ candidate["phase_branch"]
        map_rows, exact_ids, omitted_ids = [], [], []
        for j, (iid, _, _, _) in enumerate(INTERFACES):
            exact = maxabs(H[j]-local_H[j]) < MATRIX_TOL and abs(h[j]-local_h[j]) < MATRIX_TOL
            (exact_ids if exact else omitted_ids).append(iid)
            if exact:
                map_rows.extend([iid, int(np.sign(local_operator[j,k]))*(int(k)+1)] for k in np.flatnonzero(local_operator[j]))
        case["if"] = dict(map=np.asarray(map_rows, int), map_role="only_verified_exact_local_signed_functionals",
                          exact_interface_ids=np.array(exact_ids, int), omitted_interface_ids=np.array(omitted_ids, int),
                          full_seven_interface_contract="recovery.interface_angle_matrix_times_retained_radians_plus_interface_flow_offset")
        case["userdata"] = dict(slim_DC_equivalence=dict(original_parent_buses_retained=140, retained_added_stations=8,
                                  eliminated_added_zero_injection_buses=43, physical_line_model=False, AC_equivalent=False,
                                  interface_angle_units="radians", equivalent_R_B_rating_fields_are_placeholders=True))
        output_cases[name+"_case"] = case
        recovery[name] = dict(angle_lift=reduced["angle_lift"], angle_offset=reduced["angle_offset"],
                              branch_angle_matrix=reduced["branch_angle_matrix"], branch_flow_offset=reduced["branch_flow_offset"],
                              interface_angle_matrix=H, interface_flow_offset=h,
                              angle_units="radians", operator_units="model_MW_per_radian", offset_units="model_MW",
                              local_interface_branch_matrix=local_operator, local_interface_angle_matrix=local_H,
                              local_interface_flow_offset=local_h, full_interface_branch_matrix=full_operator,
                              Schur_B=reduced["Schur_B"], Schur_phase=reduced["Schur_phase"],
                              retained_full_indices_1based=reduced["retained_indices"]+1,
                              eliminated_full_indices_1based=reduced["eliminated_indices"]+1,
                              injection_projection=reduced["injection_projection"],
                              exact_local_interface_ids=np.asarray(exact_ids), omitted_local_interface_ids=np.asarray(omitted_ids))
        for record, branch in zip(register, case["branch"]):
            for key, col in [("status",10),("x_pu",3),("shift_degree",9)]:
                record[name+"_"+key] = float(branch[col])
        for component in reduced["components"]:
            component_rows.append(dict(variant=name, **{k:";".join(map(str,v)) if isinstance(v,list) else v for k,v in component.items()}))
        for pair,item in reduced["edges"].items():
            source_rows=sorted(set(item["source_rows"]))
            equivalent_rows.append(dict(variant=name,model_branch_row=len(direct_rows)+pairs.index(pair)+1,
                                        branch_key=f"DC_EQ:{pair[0]}:{pair[1]}",from_bus=pair[0],to_bus=pair[1],
                                        weight_MW_per_rad=item["weight"],x_pu=item["x_pu"],
                                        affine_branch_flow_MW=item["phase_flow"],shift_degree=item["shift_degree"],
                                        component_ids=";".join(map(str,item["component_ids"])),
                                        full191_source_branch_rows=";".join(map(str,source_rows)),
                                        full191_source_branch_keys=";".join(source_register.iloc[j-1].branch_key for j in source_rows),
                                        direct_retained_rows_excluded=True,pruned_by_magnitude_threshold=False))
        validation.append(dict(variant=name, buses=len(case["bus"]), branch_records=len(case["branch"]),
                               active_branches=int(case["branch"][:,10].sum()), retained_exact_source_circuits=14,
                               active_retained_assumptions=int(case["branch"][225:244,10].sum())-14,
                               active_Schur_equivalents=len(reduced["edges"]), maximum_B_error_MW_per_rad=B_error,
                               maximum_affine_phase_error_MW=phase_error, exact_local_interface_ids=";".join(map(str,exact_ids)),
                               omitted_local_interface_ids=";".join(map(str,omitted_ids)),
                               maximum_local_vs_recovered_operator_difference=maxabs(H-local_H),
                               minimum_equivalent_weight_MW_per_rad=min(x["weight"] for x in reduced["edges"].values())))
    output.mkdir(parents=True, exist_ok=True)
    payload = dict(**output_cases, parent_case=source["parent_case"], recovery=recovery,
                   kept_bus_ids=keep, eliminated_bus_ids=reductions[VARIANTS[0]]["eliminated_bus_ids"],
                   bus_names=busreg.model_name.to_numpy(object), bus_zones=busreg.accounting_zone.to_numpy(object),
                   branch_keys=np.asarray(branch_keys,object), gamma=float(source["gamma"]),
                   variant_names=np.asarray(VARIANTS,object), interface_names=np.asarray([x[1] for x in INTERFACES],object),
                   interface_ids=np.asarray([x[0] for x in INTERFACES]),
                   full_source_path=str(SOURCE_CASES.relative_to(ROOT)).replace("\\","/"), full_source_sha256=PINNED_SOURCE_SHA,
                   injection_contract="original140_parent_hourly_PD_QD_PG_DC_unchanged;all8_added_bus_injections_zero;no_asset_remap")
    savemat(output / "network_cases.mat", payload, do_compression=True, long_field_names=True)
    selection=[]
    last=cases["refined_2025"]
    for bid in KEEP_ADDED:
        neighbors=set()
        for row in last["branch"]:
            if row[10] and bid in row[:2]:neighbors.add(int(row[1] if row[0]==bid else row[0]))
        selection.append(dict(model_bus=bid, model_name=busreg.set_index("model_bus").loc[bid,"model_name"],
                              base_kv=345, active_full191_unique_neighbor_count=len(neighbors), rationale=RATIONALE[bid],
                              added_P_Q_GS_BS_zero=True, native_generator_relocated=False))
    for name, frame in [("bus_register",busreg),("branch_register",pd.DataFrame(register)),
                        ("eliminated_component_register",pd.DataFrame(component_rows)),
                        ("equivalent_contribution_register",pd.DataFrame(equivalent_rows)),
                        ("retained_station_rationale",pd.DataFrame(selection)),("construction_checks",pd.DataFrame(validation))]:
        frame.to_csv(output/(name+".csv"),index=False,lineterminator="\n")
    eliminated=source_buses.loc[source_buses.model_bus.isin(payload["eliminated_bus_ids"])].copy()
    eliminated["elimination_policy"]="added_zero_injection_interiors_only;original_parent_buses_never_eliminated"
    eliminated.to_csv(output/"eliminated_bus_register.csv",index=False,lineterminator="\n")
    manifest=[dict(role=role,path=str(path.relative_to(ROOT)).replace("\\","/"),sha256=sha(path)) for role,path in
              [("frozen_191_construction",SOURCE_CASES),("191_branch_provenance",SOURCE_FOLDER/"branch_register.csv"),
               ("191_bus_identity",SOURCE_FOLDER/"bus_register.csv"),("builder",Path(__file__))]]
    pd.DataFrame(manifest).to_csv(output/"source_manifest.csv",index=False,lineterminator="\n")
    summary=dict(status="exact_DC_condensation_of_added_zero_injection_nodes_only",original_buses_preserved=140,
                 retained_added_buses=KEEP_ADDED,eliminated_added_bus_count=43,total_buses=148,total_branch_records=274,
                 original_branch_records_preserved=225,registered_original_inactive_rows=[32,87,88,89,91,92,93,94,95],
                 exact_retained_PERFORM_circuits=14,retained_declared_assumption_records=5,
                 union_Schur_equivalent_pairs=30,arbitrary_threshold_pruning=False,observed_interface_data_used=False,
                 original_generation_and_DC_devices_unchanged=True,asset_load_or_generator_remapping_used=False,
                 response_scope="DC_nodal_and_affine_phase_exact;full191_branch_and_seven_interface_recovery_from_retained_radians",
                 equivalent_branch_fields="R=0 B=0 rates=0 are explicitly unqualified DC placeholders;X_and_fixed_shift_are_derived",
                 source_sha256=PINNED_SOURCE_SHA,case_checks=validation)
    (output/"construction_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    require(sha(SOURCE_CASES)==PINNED_SOURCE_SHA,"Frozen construction changed during reduction")
    print(json.dumps(summary,indent=2))
    return summary


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=DEFAULT)
    build(parser.parse_args().output)
