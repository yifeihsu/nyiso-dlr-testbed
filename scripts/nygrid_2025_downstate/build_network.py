"""Controlled full-NPCC Downstate expansion; never uses observed interface flows.

The identity case is an algebraic DC expansion, not an as-built network. The
source-detail case substitutes an exact historical PERFORM subnetwork and
explicit passive aggregate attachments. It intentionally changes the response.
Project electrical values without released impedances remain assumptions.
Original buses and branch records are retained; replaced branches are inactive.
No operating device, generator capacity, or external schedule is added here.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "output/nygrid_2025_downstate/network"
PARENT = ROOT / "output/nygrid_2025_dispatch/dispatch/dispatch.mat"
FLEET = ROOT / "output/nygrid_2025_dispatch/dispatch/model_generator_register.csv"
METADATA = ROOT / "output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv"
SOURCE = ROOT / "PERFORM/On Peak 2019 v23_Perform_NY/On Peak 2019 v23/nyiso_On_Peak_v23_shunts_as_z_load.m"
PHASE1C = ROOT / "System Matpower Format/NY_Lite/s13_phase1c_source_bus_manifest.csv"
LANDING_SOURCE = ROOT / "output/nygrid_2025_downstate/sources/asset_landing_crosswalk.csv"
PROJECT_SOURCE = ROOT / "output/nygrid_2025_downstate/sources/upgrade_register.csv"
TEMPLATE_WORKBOOK = ROOT / "PERFORM/Auxilliary_Perform_NY/Branch_changes_2019_to_2030.xlsx"
SOURCE_HASH_LF = "f6ba2d787a4f22fcb7ae9f597cdd3111500d79921829a245d50e516c47e209ca"
ANCHORS = {651: 73, 897: 74, 1519: 76, 900: 77, 1133: 20011}
K_BACKBONE_SOURCE = [561, 567, 588, 620, 995, 996]
EXTRA_SOURCE = [858, 902, 774, 1130, 1529, 1129, 1132, 1134, 79] + K_BACKBONE_SOURCE
PROJECT_BUSES = {
    "CRICKET_VALLEY": (20001, "CRICKET VALLEY 345", 345., "G", 73),
    "LONG_MOUNTAIN": (20002, "LONG MOUNTAIN 345", 345., "NA", 35),
    "DOVER": (20003, "DOVER 345", 345., "G", 73),
    "KNICKERBOCKER": (20004, "KNICKERBOCKER 345", 345., "G", 39),
    "NYPA_ANNEX": (20005, "NYPA ANNEX 345", 345., "J", 82),
    "EAST_HAMPTON": (20006, "EAST HAMPTON 69", 69., "K", 80),
    "GREENWOOD": (20007, "GREENWOOD 138", 138., "J", 81),
    "FOX_HILLS": (20008, "FOX HILLS 138", 138., "J", 81),
    "GOWANUS_PAR": (20009, "GOWANUS RCC PAR 138", 138., "J", 81),
    "GOETHALS_PAR": (20010, "GOETHALS RCC PAR 138", 138., "J", 81),
    "VERNON": (20011, "VERNON 138", 138., "J", 82),
    "FRESH_KILLS_138": (20012, "FRESH KILLS 138", 138., "J", 82),
    "FRESH_KILLS_345": (20013, "FRESH KILLS 345", 345., "J", 82),
    "RAINEY_PAR": (20014, "RAINEY RCC PAR 138", 138., "J", 82),
}
SOURCE_ZONE = dict(zip(range(65, 76), list("ABCDEFGIHJK")))
VARIANTS = ["expanded_identity", "refined_2019", "refined_2025_pre_may",
            "refined_2025_may21", "refined_2025_may30", "refined_2025", "refined_2025_nyes"]
INTERFACE_ZONES = [(1, "DYSINGER EAST", "A", "B"), (2, "WEST CENTRAL", "B", "C"),
                   (3, "TOTAL EAST", "ABCDE", "FGHIJK"), (4, "MOSES SOUTH", "D", "E"),
                   (5, "CENTRAL EAST - VC", "E", "F"), (8, "UPNY CONED", "ABCDEFG", "HIJK"),
                   (10, "SPR/DUN-SOUTH", "I", "J")]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def parse_source(path=SOURCE):
    text = Path(path).read_text(encoding="utf-8")
    digest = hashlib.sha256(text.replace("\r\n", "\n").replace("\r", "\n").encode()).hexdigest()
    require(digest == SOURCE_HASH_LF, "Pinned PERFORM electrical source changed")
    out = {"baseMVA": 100.}
    for key in ["bus", "branch", "gen"]:
        match = re.search(r"mpc\." + key + r"\s*=\s*\[(.*?)\];", text, re.S)
        require(match is not None, "Missing source matrix " + key)
        rows = [line.split("%")[0].strip().rstrip(";") for line in match[1].splitlines()]
        out[key] = np.array([list(map(float, line.split())) for line in rows if line])
    match = re.search(r"mpc\.bus_name\s*=\s*\{(.*?)\};", text, re.S)
    out["bus_name"] = np.array([x.replace("''", "'") for x in re.findall(r"'((?:[^']|'')*)'", match[1])], object)
    require(len(out["bus_name"]) == len(out["bus"]), "Source name alignment changed")
    return out


def series_split(row, nodes, weights):
    """Exact DC series identity including transformer tap and phase source.

    X*tap is the DC series budget. Only the first segment retains a nonunity
    parent tap and phase shift. R and B are inherited bookkeeping shares;
    the resulting branches are not AC-equivalent or physical source rows.
    """
    row = np.asarray(row, float)
    weights = np.asarray(weights, float)
    require(len(nodes) == len(weights) + 1 and np.all(weights > 0), "Invalid positive split")
    require(nodes[0] == row[0] and nodes[-1] == row[1], "Split endpoint mismatch")
    weights = weights / weights.sum()
    tap = row[8] if row[8] else 1.
    result = []
    for j, (a, b, weight) in enumerate(zip(nodes, nodes[1:], weights)):
        value = row[:13].copy()
        value[:2] = [a, b]
        value[2:5] = row[2:5] * weight
        value[8] = row[8] if j == 0 else 0.
        value[9] = row[9] if j == 0 else 0.
        value[3] = row[3] * tap * weight / (value[8] if value[8] else 1.)
        result.append(value)
    return np.asarray(result)


def matrices(case):
    ids = case["bus"][:, 0].astype(int)
    lookup = {v: j for j, v in enumerate(ids)}
    branch = case["branch"]
    C = np.zeros((len(branch), len(ids)))
    for j, row in enumerate(branch):
        C[j, lookup[int(row[0])]] += 1
        C[j, lookup[int(row[1])]] -= 1
    tap = np.where(branch[:, 8] == 0, 1., branch[:, 8])
    b = np.where(branch[:, 10] == 1, case["baseMVA"] / (branch[:, 3] * tap), 0.)
    phase = -b * np.deg2rad(branch[:, 9])
    return C.T @ (b[:, None] * C), C.T @ phase


def schur(case, retain=140):
    B, p = matrices(case)
    if len(B) == retain:
        return B, p
    A = B[retain:, retain:]
    return (B[:retain, :retain] - B[:retain, retain:] @ np.linalg.solve(A, B[retain:, :retain]),
            p[:retain] - B[:retain, retain:] @ np.linalg.solve(A, p[retain:]))


def zone_operator_map(case, zones):
    """Rebuild every supported measurement on active candidate branches.

    The inherited numeric IDs are retained, but the source OPF maps that do
    not define these seven comparison functionals are deliberately omitted.
    This is a model zone-crossing operator, not a physical 2025 flowgate claim.
    """
    lookup = dict(zip(case["bus"][:, 0].astype(int), zones))
    members, records = [], []
    for iid, label, left, right in INTERFACE_ZONES:
        for j, row in enumerate(case["branch"], 1):
            a, b = lookup[int(row[0])], lookup[int(row[1])]
            sign = int(a in list(left) and b in list(right)) - int(b in list(left) and a in list(right))
            if row[10] and sign:
                members.append([iid, sign * j])
                records.append(dict(interface_id=iid, interface_name=label, model_branch_row=j, sign=sign,
                                    from_accounting_zone=a, to_accounting_zone=b, source_zones=left, target_zones=right,
                                    operator_role="legacy_NY_zone_crossing_functional", exact_public_2025_flowgate=False))
    return np.asarray(members, int), records


def build(output=DEFAULT, attachment_scale=1., project_scale=1.):
    output = Path(output).resolve()
    require(not (output / "network_cases.mat").exists(), "Choose a fresh output folder")
    require(.5 <= attachment_scale <= 2 and .5 <= project_scale <= 2, "Sensitivity scale outside declared range")
    data = loadmat(PARENT, simplify_cells=True)
    parent = data["base_case"]
    require(parent["bus"].shape[0] == 140 and parent["branch"].shape[0] == 225 and
            parent["gen"].shape[0] == 1464 and parent["dcline"].shape[0] == 4, "Frozen parent dimensions changed")
    require(np.array_equal(parent["bus"][:, 0], np.arange(1, 141)), "Parent identities changed")
    source = parse_source()
    info = pd.read_csv(METADATA, keep_default_na=False)
    require(np.array_equal(info.idx.to_numpy(int), np.arange(1, 141)), "Parent metadata identity changed")
    source_bus_rows = {int(row[0]): j for j, row in enumerate(source["bus"])}
    source_ids = sorted(set(pd.read_csv(PHASE1C).source_bus.astype(int)) | set(EXTRA_SOURCE) | set(ANCHORS))
    source_map = {i: ANCHORS.get(i, 10000 + i) for i in source_ids}
    added_source = [i for i in source_ids if i not in ANCHORS]
    bus_rows = [row[:13].copy() for row in parent["bus"]]
    buses = []
    for row in info.itertuples(index=False):
        buses.append(dict(model_bus=int(row.idx), model_name=row.name, base_kv=float(row.Vn),
                          accounting_zone=row.zone, physical_source_zone="", source_bus=0,
                          identity_role="original_parent", source_pd_mw=0., source_qd_mvar=0.,
                          injection_policy="parent_devices_preserved", reference_parent_bus=int(row.idx)))
    bus_index = {int(r[0]): j for j, r in enumerate(bus_rows)}
    for sid in added_source:
        sr = source_bus_rows[sid]
        row = source["bus"][sr, :13].copy()
        zone = SOURCE_ZONE[int(row[10])]
        anchor = {"G": 73, "H": 74, "I": 78, "J": 82, "K": 80}[zone]
        row[0], row[1], row[6] = source_map[sid], 1, parent["bus"][anchor - 1, 6]
        row[2:6], row[7:9] = 0, [1., 0.]
        bus_index[int(row[0])] = len(bus_rows)
        bus_rows.append(row)
        buses.append(dict(model_bus=int(row[0]), model_name=str(source["bus_name"][sr]), base_kv=float(row[9]),
                          accounting_zone=zone, physical_source_zone=zone, source_bus=sid,
                          identity_role="source_named_station", source_pd_mw=float(source["bus"][sr, 2]),
                          source_qd_mvar=float(source["bus"][sr, 3]), injection_policy="zero_until_declared_asset_landing",
                          reference_parent_bus=anchor))
    for key, (bid, name, kv, zone, anchor) in PROJECT_BUSES.items():
        row = parent["bus"][anchor - 1, :13].copy()
        row[0], row[1], row[9] = bid, 1, kv
        row[2:6], row[7:9] = 0, [1., 0.]
        bus_index[bid] = len(bus_rows)
        bus_rows.append(row)
        source_pd = float(source["bus"][source_bus_rows[1133], 2]) if key == "VERNON" else 0.
        source_qd = float(source["bus"][source_bus_rows[1133], 3]) if key == "VERNON" else 0.
        buses.append(dict(model_bus=bid, model_name=name, base_kv=kv, accounting_zone=zone,
                          physical_source_zone=zone, source_bus=1133 if key == "VERNON" else 0, identity_role="source_named_station" if key == "VERNON" else "public_station_with_equivalent_connections",
                          source_pd_mw=source_pd, source_qd_mvar=source_qd, injection_policy="zero_until_declared_asset_landing",
                          reference_parent_bus=anchor))
    bus = np.asarray(bus_rows)
    require(len(bus) == 191, "Unexpected station count")
    sm = lambda sid: source_map[sid]
    pb = lambda key: PROJECT_BUSES[key][0]
    # Baseline replacement corridors. Numeric row claims always verify both endpoints.
    paths = {
        32: ([35, pb("LONG_MOUNTAIN"), pb("CRICKET_VALLEY"), 73], [1, 2, 2]),
        38: ([39, pb("KNICKERBOCKER"), 73], [1, 2]),
        87: ([73, sm(858), sm(902), 74], [.00527, .00713, .00563]),
        89: ([74, sm(547), sm(594), sm(593), 78], [.0043 / 3, .00427 / 4, .00063 / 4, .001]),
        91: ([76, sm(774), 77], [.00276, .00541]),
        92: ([78, sm(589), 79], [1, 1]),
        93: ([78, sm(560), 80], [1, 1]),
        94: ([78, sm(1136), sm(1134), sm(1132), sm(1129), 81], [3, 1, 1, 1, 3]),
        95: ([78, sm(557), sm(1493), 82], [1, 1, 1]),
    }
    refined_replaced = sorted((set(paths) | {88}) - {38})
    expected_ends = {32: (35, 73), 38: (39, 73), 87: (73, 74), 88: (74, 77), 89: (74, 78),
                     91: (76, 77), 92: (78, 79), 93: (78, 80), 94: (78, 81), 95: (78, 82)}
    for row, ends in expected_ends.items():
        require(np.array_equal(parent["branch"][row-1, :2], ends), "Parent corridor identity changed")
    branches = [r[:13].copy() for r in parent["branch"]]
    register = []
    for j, row in enumerate(branches, 1):
        record = dict(branch_key=f"PARENT:{j}", model_branch_row=j, from_bus=int(row[0]), to_bus=int(row[1]),
                      electrical_role="retained_parent", source_branch_row=0, parent_branch_row=j,
                      parameter_basis="frozen_modified2019_parent", assumption="", project="", activation_utc="",
                      neutralized_angle_limits=False, thermal_eligible=False)
        for name in VARIANTS:
            retired = paths if name == "expanded_identity" else refined_replaced + ([38] if name == "refined_2025_nyes" else [])
            record[name + "_status"] = int(row[10] if j not in retired else 0)
        register.append(record)

    def add(key, row, role, basis, active, *, parent_row=0, source_row=0, assumption="", project="", activation=""):
        require(key not in {r["branch_key"] for r in register}, "Duplicate branch key")
        value = np.asarray(row, float)[:13].copy()
        require(np.isfinite(value).all() and value[2] >= 0 and value[3] > 0, "Invalid passive added branch")
        require(int(value[0]) in bus_index and int(value[1]) in bus_index, "Unknown added endpoint")
        branches.append(value)
        rec = dict(branch_key=key, model_branch_row=len(branches), from_bus=int(value[0]), to_bus=int(value[1]),
                   electrical_role=role, source_branch_row=source_row, parent_branch_row=parent_row,
                   parameter_basis=basis, assumption=assumption, project=project, activation_utc=activation,
                   neutralized_angle_limits=source_row > 0, thermal_eligible=False)
        for name in VARIANTS:
            rec[name + "_status"] = int(name in active)
        register.append(rec)
        return len(branches)

    def assumed(key, a, b, r, x, rating=0., role="passive_attachment_equivalent", basis="inherited_parent_budget",
                active=None, parent_row=0, project="", assumption="", activation="", tap=None):
        if active is None:
            active = VARIANTS[1:]
        kv_change = bus[bus_index[a], 9] != bus[bus_index[b], 9]
        tap = float(kv_change) if tap is None else tap
        scale = project_scale if project else attachment_scale
        row = [a, b, r * scale, x * scale, 0, rating, rating, rating, tap, 0, 1, -360, 360]
        return add(key, row, role, basis, active, parent_row=parent_row, project=project,
                   assumption=assumption, activation=activation)

    used = set()
    for parent_row, (nodes, weights) in paths.items():
        split = series_split(parent["branch"][parent_row-1], nodes, weights)
        used.update(nodes[1:-1])
        for j, row in enumerate(split, 1):
            add(f"IDENTITY:SPLIT:{parent_row}:{j}", row, "algebraic_DC_identity_series_segment",
                "positive_normalized_parent_X_times_tap_budget", ["expanded_identity"], parent_row=parent_row,
                assumption="DC_equivalent_only_R_B_splits_do_not_establish_AC_equivalence")
    for rec in buses[140:]:
        if rec["model_bus"] in used:
            continue
        # This leaf's impedance has no Schur effect at zero injection.
        assumed("IDENTITY:LEAF:" + str(rec["model_bus"]), rec["reference_parent_bus"], rec["model_bus"],
                0., .01, role="algebraic_DC_identity_zero_injection_leaf", basis="arbitrary_positive_scaffold_X_no_port_effect",
                active=["expanded_identity"], assumption="algebraic_scaffold_not_physical_attachment")

    source_rows = np.flatnonzero(np.isin(source["branch"][:, 0], source_ids) & np.isin(source["branch"][:, 1], source_ids))
    require(len(source_rows) == 97, "Induced source-subnetwork selection changed")
    for j in source_rows:
        row = source["branch"][j, :13].copy()
        row[:2] = [sm(int(v)) for v in row[:2]]
        row[11:13] = [-360, 360]
        add(f"PERFORM:{j+1}", row, "exact_historical_source_circuit", "pinned_PERFORM_2019_electrical_row",
            VARIANTS[1:], source_row=int(j+1), assumption="source_row_identifier_not_independently_resolved_RAW_circuit_ID")

    # The retained CE UG, RAV A-3 and AK-3 proxies cannot be identified with
    # physical receiving stations. Positive residual attachments are declared
    # modeling assumptions, not imaginary source circuits or a claimed fit.
    attachment_specs = [("CEUG_DUNWOODIE", 78, sm(593), 89, .25),
                        ("RAVA3_EGC", 79, sm(589), 92, .5),
                        ("NORTHPORT_SHORERD", 80, sm(560), 93, .5),
                        ("GOETHALS_GOWANUS", 81, sm(1129), 94, .5),
                        ("AK3_ASTORIA138", 82, sm(1493), 95, .5)]
    for key, a, b, pr, fraction in attachment_specs:
        old = parent["branch"][pr-1]
        assumed("ATTACH:" + key, a, b, old[2] * fraction, old[3] * fraction, parent_row=pr,
                assumption=f"positive_{fraction:g}_fraction_of_replaced_parent_series_budget_not_a_fitted_residual")

    # Public stations with incomplete electrical evidence. These edges are
    # explicitly sensitivity parameters; public MW does not become a rating.
    old = parent["branch"][31]
    lm, cv, dover = [pb(k) for k in ["LONG_MOUNTAIN", "CRICKET_VALLEY", "DOVER"]]
    for key, a, b, weight in [("BOUNDARY_SOUTHINGTON_LM", 35, lm, .2), ("PV_CV_F83_PROXY", 73, cv, .4),
                             ("CV_LM_398_PROXY", cv, lm, .4)]:
        active = VARIANTS[1:] if "CV_LM" not in key else VARIANTS[1:5]
        assumed("CV:" + key, a, b, old[2] * weight, old[3] * weight, parent_row=32, active=active,
                project="CV_EXISTING", basis="parent_external_tie_positive_series_budget",
                assumption="source_backed_station_path_but_boundary35_is_Southington_not_LongMountain;impedance_assumed")
    assumed("CV:PV_CV_F84", 73, cv, old[2] * .4, old[3] * .4, active=VARIANTS[2:], project="CV_2020",
            basis="assumed_equal_existing_F83_proxy", assumption="new_parallel_F84_in_service2020_not_2019_observation_fit")
    assumed("CV:DOVER_IDLE_LEAF", cv, dover, 0., .01, active=VARIANTS[1:5], role="inactive_project_zero_injection_leaf",
            basis="algebraic_station_attachment_before_cutover", assumption="no_injection_or_through_path_before_Dover_cutover")
    for key, a, b in [("CV_DOVER_Y17", cv, dover), ("DOVER_LM_398", dover, lm)]:
        assumed("DOVER:" + key, a, b, old[2] * .2, old[3] * .2, active=VARIANTS[5:], parent_row=32,
                project="DOVER_2025", basis="positive_split_of_replaced_CV_LM_series_budget",
                assumption="fixed_nominal_tap_zero_phase_PAR_electrical_controls_unreleased", activation="2025-12-20T04:00:00Z")

    # NYES is outside the primary Downstate case because its correspondence
    # to the old Leeds/PV aggregate paths is unresolved. Core cases retain
    # both original rows; only the separate NYES sensitivity replaces row38.
    old = parent["branch"][37]
    for j, (a, b, fraction) in enumerate([(39, pb("KNICKERBOCKER"), 1/3), (pb("KNICKERBOCKER"), 73, 2/3)], 1):
        assumed(f"NYES:LEGACY_SEGMENT:{j}", a, b, old[2]*fraction, old[3]*fraction, parent_row=38,
                project="NYES_LEGACY", basis="positive_split_of_one_parent_Leeds_PV_equivalent", active=["refined_2025_nyes"],
                assumption="Knickerbocker_geographic_insertion_assumed_no_Churchtown345_terminal")
    assumed("NYES:2023_ADDITIONAL_345", pb("KNICKERBOCKER"), 73, .00293/112.3*54.5, .04468/112.3*54.5,
            active=["refined_2025_nyes"], project="NYES_2023", basis="historical_345kV_template_length_scaling_assumption",
            assumption="54.5mile_project_route;workbook800_1233_1row1945estimated112.3miletemplate;no_MVA_rating_inferred")
    assumed("NYES:KNICKER_IDLE_LEAF", 39, pb("KNICKERBOCKER"), 0., .01, active=VARIANTS[1:6],
            role="inactive_project_zero_injection_leaf", basis="optional_NYES_station_scaffold",
            assumption="NYES_omitted_from_core;source_to_parent_overlap_unresolved")

    # Existing receiving-network proxies give both RCC receiving terminals a
    # load-capable connection while project circuits are off. They are not
    # named physical cable claims and will be varied separately in replay.
    cable = source["branch"][1268, 2:4] / 5.5
    for key, a, b, length in [("GREENWOOD_CORONA", pb("GREENWOOD"), sm(601), 8),
                            ("FOXHILLS_GREENWOOD", pb("FOX_HILLS"), pb("GREENWOOD"), 10)]:
        assumed("RECEIVING:" + key, a, b, cable[0]*length, cable[1]*length,
                basis="declared_omitted_receiving_network_proxy", assumption="positive_historical_cable_template_proxy_not_physical_circuit")
    assumed("ASSET:ANNEX_E13_Q35_PROXY", pb("NYPA_ANNEX"), sm(79), .00012/2, .0023/2,
            basis="historical_EastAstoria_East13_two_circuit_template", assumption="Q35L_M_endpoints_public;exact_R_X_unreleased")
    assumed("ASSET:EASTHAMPTON_K_PROXY", pb("EAST_HAMPTON"), sm(1497), .001, .03,
            basis="declared_omitted_LongIsland69_network_proxy", assumption="EastHampton_POI_public;intermediate_K_network_equivalent_unresolved")
    for key, a, b, pr, fraction in [
        ("FRESHKILLS138_FOXHILLS", pb("FRESH_KILLS_138"), pb("FOX_HILLS"), 94, .25),
        ("FRESHKILLS345_GOETHALS", pb("FRESH_KILLS_345"), 81, 94, .25),
    ]:
        old = parent["branch"][pr-1]
        assumed("ASSET:" + key, a, b, old[2]*fraction, old[3]*fraction, parent_row=pr,
                basis="positive_inherited_local_attachment_budget", assumption="source_backed_unit_POI;intermediate_station_connection_is_declared_proxy")
    # Nominal fixed PARs remain connected before cable energization and carry
    # zero injection, avoiding a disconnected model node in pre-project cases.
    for key, a, b in [("GOWANUS", sm(1129), pb("GOWANUS_PAR")), ("GOETHALS", 81, pb("GOETHALS_PAR")),
                      ("RAINEY", sm(1130), pb("RAINEY_PAR"))]:
        assumed("RCC:PAR:" + key, a, b, .002, .03, project="RCC_PAR_ASSUMED",
                basis="explicit_fixed_transformer_assumption", assumption="tap1_shift0_no_automatic_PAR_control_no_projectMW_toMVA_conversion", tap=1.)
    for key, a, b, length, active, date in [
        ("QUEENS", pb("RAINEY_PAR"), sm(601), 6., VARIANTS[2:], "2025-01-01T05:00:00Z"),
        ("BROOKLYN", pb("GOWANUS_PAR"), pb("GREENWOOD"), 1., VARIANTS[3:], "2025-05-21T04:00:00Z"),
        ("STATEN", pb("GOETHALS_PAR"), pb("FOX_HILLS"), 9.2, VARIANTS[4:], "2025-05-30T04:00:00Z")]:
        assumed("RCC:CABLE:" + key, a, b, cable[0]*length, cable[1]*length, active=active, project="RCC_"+key,
                basis="2019_EastAstoria_Corona_cable_per_mile_template_assumption",
                assumption="public_project_endpoint_and_date;R_X_assumed;unrated_no_conductor_or_thermal_claim", activation=date)

    branch = np.asarray(branches)
    frames = pd.DataFrame(register)
    for column, index in [("r_pu", 2), ("x_pu", 3), ("b_pu", 4), ("rate_a_mva", 5),
                          ("rate_b_mva", 6), ("rate_c_mva", 7), ("tap", 8), ("shift_degree", 9)]:
        frames[column] = branch[:, index]
    frames["uncertainty_group"] = np.where(frames.electrical_role.isin(["retained_parent", "exact_historical_source_circuit"]),
                                             "frozen_source", np.where(frames.project.ne(""), "project_electrical_assumption", "proxy_attachment_assumption"))
    frames.loc[frames.electrical_role.str.contains("algebraic|inactive_project"), "uncertainty_group"] = "algebraic_scaffold"
    cases = {}
    operator_records = []
    for name in VARIANTS:
        case = copy.deepcopy(parent)
        case["bus"] = bus.copy()
        case["branch"] = branch.copy()
        case["branch"][:, 10] = frames[name+"_status"].to_numpy(int)
        case["bus_name"] = np.array([r["model_name"] for r in buses], object)
        member_map, member_records = zone_operator_map(case, [r["accounting_zone"] for r in buses])
        case["if"] = {"map": member_map,
                      "map_role": "legacy_NY_zone_crossing_functionals_not_exact_public_2025_flowgates",
                      "omitted_inherited_OPF_only_ids": np.array([6, 7, 9, 11])}
        operator_records.extend(dict(variant=name, **record) for record in member_records)
        cases[name + "_case"] = case
        B, _ = matrices(case)
        require(np.linalg.matrix_rank(B[:-1, :-1]) == len(B)-1, "Disconnected variant " + name)
    pB, pp = matrices(parent)
    iB, ip = schur(cases["expanded_identity_case"])
    identity_error = float(np.max(np.abs(iB-pB)))
    require(identity_error < 1e-8 and np.max(np.abs(ip-pp)) < 1e-8, "Identity expansion changed parent DC response")

    # Construction-only injection contracts: zero additions for topology-only,
    # source-PD coverage shares for I/J/K loads, and explicit plant POI changes.
    # A partial subnetwork must never be renormalized to carry an entire zone.
    identity_W = np.eye(len(bus), 140)
    asset_W = identity_W.copy()
    bus_frame = pd.DataFrame(buses)
    allocation_records = []
    coverage_records = []
    for zone in ["I", "J", "K"]:
        original = np.flatnonzero(info.zone.to_numpy() == zone)
        eligible = np.flatnonzero((bus_frame.accounting_zone.to_numpy() == zone) & (bus_frame.source_pd_mw.to_numpy() > 0))
        require(len(eligible) > 0, "No historical load shares for zone " + zone)
        full_zone = np.array([SOURCE_ZONE.get(int(row[10]), "") == zone for row in source["bus"]])
        full_source_pd = float(source["bus"][full_zone, 2].sum())
        shares = bus_frame.iloc[eligible].source_pd_mw.to_numpy(float)
        selected_source_pd = float(shares.sum())
        coverage = selected_source_pd / full_source_pd
        require(0 < coverage <= 1, "Invalid partial source coverage")
        shares /= full_source_pd
        asset_W[:, original] = identity_W[:, original] * (1-coverage)
        asset_W[np.ix_(eligible, original)] = shares[:, None]
        coverage_records.append(dict(zone=zone, full_source_pd_mw=full_source_pd,
                                     selected_source_pd_mw=selected_source_pd, represented_fraction=coverage,
                                     residual_parent_fraction=1-coverage,
                                     selected_source_bus_ids=";".join(map(str, bus_frame.iloc[eligible].source_bus.astype(int))),
                                     policy="selected_source_PD_divided_by_full_source_zone_PD;unrepresented_remainder_stays_at_each_original_parent_bus"))
        for target, share in zip(eligible, shares):
            for source_row in original:
                allocation_records.append(dict(parent_bus=int(info.iloc[source_row].idx), model_bus=int(bus[target, 0]),
                                               zone=zone, share=float(share), basis="2019_selected_source_PD_over_full_source_zone_PD_not_observed2025_nodal_load"))
        for source_row in original:
            allocation_records.append(dict(parent_bus=int(info.iloc[source_row].idx), model_bus=int(info.iloc[source_row].idx),
                                           zone=zone, share=1-coverage, basis="unrepresented_source_zone_load_preserved_at_original_parent_bus"))
    require(np.max(np.abs(asset_W.sum(axis=0)-1)) < 1e-12, "Load allocation is not conservative")
    # Necessary source-subnetwork completeness, independent of flow metrics:
    # a selected K load must have a K-only path to an original K anchor.
    k_ids = set(bus_frame.loc[bus_frame.accounting_zone.eq("K"), "model_bus"].astype(int))
    k_anchors = set(info.loc[info.zone.eq("K"), "idx"].astype(int))
    k_edges = [(int(r[0]), int(r[1])) for r in cases["refined_2025_case"]["branch"]
               if r[10] == 1 and int(r[0]) in k_ids and int(r[1]) in k_ids]
    connected = set(k_anchors)
    while True:
        expanded = connected | {b for a, b in k_edges if a in connected} | {a for a, b in k_edges if b in connected}
        if expanded == connected:
            break
        connected = expanded
    k_loaded = set(bus_frame.loc[bus_frame.accounting_zone.eq("K") & bus_frame.source_pd_mw.gt(0), "model_bus"].astype(int))
    require(k_loaded.issubset(connected), "Partial K source load is forced through another zone; missing K backbone")
    fleet = pd.read_csv(FLEET, keep_default_na=False)
    old_gen_buses = fleet.bus_id.to_numpy(int)
    new_gen_buses = old_gen_buses.copy()
    # Landing facts are supplied by the companion primary-source register;
    # unresolved units keep their original bus. Device keys prevent aliases.
    public_landings = pd.read_csv(LANDING_SOURCE, keep_default_na=False)
    require(public_landings.device_key.is_unique, "Duplicated source landing key")
    qualified_landings = public_landings.loc[public_landings.may_move_after_network_attachment_verified.astype(int).eq(1)].set_index("device_key")
    station_targets = {("Gowanus", "345"): sm(1129), ("Goethals", "345"): 81,
                       ("Astoria East", "138"): sm(1493), ("NYPA Annex", "345"): pb("NYPA_ANNEX"),
                       ("Cricket Valley", "345"): pb("CRICKET_VALLEY"), ("East Hampton", "69"): pb("EAST_HAMPTON"),
                       ("Vernon", "138"): pb("VERNON"), ("Rainey", "345"): sm(1130),
                       ("Fresh Kills", "138"): pb("FRESH_KILLS_138"), ("Fresh Kills", "345"): pb("FRESH_KILLS_345")}
    landings = []
    for j, row in enumerate(fleet.itertuples(index=False)):
        pid = int(row.plant_id) if str(row.plant_id) else 0
        if row.role == "native" and row.device_key in qualified_landings.index:
            evidence = qualified_landings.loc[row.device_key]
            station_key = (evidence.source_backed_receiving_station, str(evidence.receiving_voltage_kv))
            require(station_key in station_targets, "Qualified landing station not constructed: " + str(station_key))
            target = station_targets[station_key]
            require(str(row.zone) == bus_frame.iloc[bus_index[target]].accounting_zone, "Asset landing crosses accounting zone")
            new_gen_buses[j] = target
            landings.append(dict(gen_row=j+1, fleet_id=row.fleet_id, device_key=row.device_key, plant_id=pid,
                                 eia_generator_id=row.eia_generator_id, zone=row.zone, old_bus=int(row.bus_id), new_bus=target,
                                 policy="same_physical_EIA_generator_per_hour_PG_bounds_identity;POI_only_moved",
                                 source_ids=evidence.source_ids, source_evidence=evidence.landing_evidence_level,
                                 source_register="../sources/asset_landing_crosswalk.csv"))
    for name, case in cases.items():
        require(np.array_equal(case["gen"], parent["gen"]) and np.array_equal(case["dcline"], parent["dcline"]),
                "Topology-only construction altered devices")
    source_mapping = []
    for sid in source_ids:
        sr = source_bus_rows[sid]
        mid = source_map[sid]
        source_mapping.append(dict(source_bus=sid, model_bus=mid, source_name=str(source["bus_name"][sr]),
                                   source_base_kv=float(source["bus"][sr, 9]), source_physical_zone=SOURCE_ZONE[int(source["bus"][sr, 10])],
                                   parent_accounting_zone=bus_frame.iloc[bus_index[mid]].accounting_zone,
                                   mapping_policy="name_voltage_alias_accounting_zone_preserved" if mid <= 140 else "new_source_named_station"))
    replacements = []
    for pr in sorted(set(refined_replaced) | {38}):
        for name in VARIANTS:
            if frames.iloc[pr-1][name+"_status"] != 0:
                continue
            replacements.append(dict(variant=name, parent_branch_row=pr, parent_branch_key=f"PARENT:{pr}",
                                     from_bus=int(parent["branch"][pr-1, 0]), to_bus=int(parent["branch"][pr-1, 1]),
                                     old_status=1, new_status=0,
                                     replacement_keys=";".join(frames.loc[(frames.parent_branch_row == pr) &
                                          (frames.electrical_role != "retained_parent") & (frames[name+"_status"] == 1), "branch_key"]),
                                     shared_source_mesh_keys=";".join(frames.loc[frames.electrical_role.eq("exact_historical_source_circuit"), "branch_key"]) if name != "expanded_identity" and pr not in [32, 38] else "",
                                     disposition="entire_original_row_inactive_once;no_full_old_parallel_aggregate"))
    output.mkdir(parents=True, exist_ok=True)
    # The source subset is durable and independent of ignored MATLAB caches.
    source_subset_rows = [source_bus_rows[sid] for sid in source_ids]
    savemat(output / "source_subset.mat", dict(baseMVA=source["baseMVA"],
            source_bus_ids=np.asarray(source_ids), source_branch_rows=source_rows+1,
            bus=source["bus"][source_subset_rows], branch=source["branch"][source_rows],
            bus_name=source["bus_name"][source_subset_rows], source_sha256_lf=SOURCE_HASH_LF), do_compression=True)
    payload = dict(parent_case=parent, source_case=source, **cases, bus_ids=bus[:, 0],
                   bus_zones=bus_frame.accounting_zone.to_numpy(object), branch_keys=frames.branch_key.to_numpy(object),
                   load_allocation_identity=identity_W, load_allocation_asset=asset_W,
                   generator_bus_identity=old_gen_buses, generator_bus_asset=new_gen_buses, gamma=float(data["gamma"]))
    savemat(output / "network_cases.mat", payload, do_compression=True, long_field_names=True)
    for name, frame in [("bus_register", bus_frame), ("branch_register", frames),
                        ("source_bus_map", pd.DataFrame(source_mapping)), ("replacement_register", pd.DataFrame(replacements)),
                        ("generation_landing_register", pd.DataFrame(landings)), ("load_allocation_register", pd.DataFrame(allocation_records)),
                        ("load_coverage_register", pd.DataFrame(coverage_records)),
                        ("interface_operator_register", pd.DataFrame(operator_records))]:
        frame.to_csv(output / (name + ".csv"), index=False, lineterminator="\n")
    k_repair = frames.loc[frames.source_branch_row.gt(0) &
                         (frames.from_bus.isin([sm(x) for x in K_BACKBONE_SOURCE]) |
                          frames.to_bus.isin([sm(x) for x in K_BACKBONE_SOURCE]))].copy()
    k_repair["purpose"] = "restore_K_only_source_backbone_for_selected_K_loads;not_selected_against_interface_flow"
    k_repair.to_csv(output / "K_backbone_source_register.csv", index=False, lineterminator="\n")
    states = pd.DataFrame([
        dict(case_key="refined_2025_pre_may_case", start_utc="2025-01-01T05:00:00Z", end_utc="2025-05-21T04:00:00Z", policy="2025_pre_RCCGowanus;Queens2023_CV2020_in_service"),
        dict(case_key="refined_2025_may21_case", start_utc="2025-05-21T04:00:00Z", end_utc="2025-05-30T04:00:00Z", policy="Gowanus_day_only_2025May20_conservative_next_day"),
        dict(case_key="refined_2025_may30_case", start_utc="2025-05-30T04:00:00Z", end_utc="2025-12-20T04:00:00Z", policy="Goethals_day_only_2025May29_conservative_next_day"),
        dict(case_key="refined_2025_case", start_utc="2025-12-20T04:00:00Z", end_utc="2026-01-01T05:00:00Z", policy="Dover_documented_Dec19_hour_beginning23_EST"),
    ])
    states.to_csv(output / "project_state_register.csv", index=False, lineterminator="\n")
    manifest = [dict(role=role, path=str(path.relative_to(ROOT)).replace("\\", "/"), sha256=sha(path)) for role, path in
                [("frozen_parent_dispatch", PARENT), ("parent_generator_identity", FLEET), ("parent_metadata", METADATA),
                 ("exact_electrical_source", SOURCE), ("existing_source_selection", PHASE1C),
                 ("primary_asset_landing_evidence", LANDING_SOURCE), ("primary_project_evidence", PROJECT_SOURCE),
                 ("historical_parameter_template_workbook", TEMPLATE_WORKBOOK), ("builder", Path(__file__))]]
    manifest.append(dict(role="durable_source_subset", path=str((output / "source_subset.mat").relative_to(ROOT)).replace("\\", "/"),
                         sha256=sha(output / "source_subset.mat")))
    pd.DataFrame(manifest).to_csv(output / "source_manifest.csv", index=False, lineterminator="\n")
    summary = dict(status="constructed_DC_research_scenarios_not_as_built_or_AC_qualified", original_buses=140,
                   total_buses=len(bus), total_branch_records=len(branch), exact_source_branches=len(source_rows),
                   replaced_parent_rows=refined_replaced, source_sha256_lf=SOURCE_HASH_LF,
                   identity_maximum_B_error_mw_per_rad=identity_error,
                   identity_maximum_phase_error_mw=float(np.max(np.abs(ip-pp))),
                   observed_internal_flows_used=False, gamma=float(data["gamma"]),
                   attachment_scale=attachment_scale, project_scale=project_scale,
                   modified_generator_landings=len(landings), original_generators=len(parent["gen"]),
                   selected_K_loads_have_K_only_source_path_to_parent=True,
                   K_backbone_added_source_buses=K_BACKBONE_SOURCE,
                   load_coverage=coverage_records,
                   original_dclines=len(parent["dcline"]), dc_landings_changed=False,
                   source_parameter_exception="ANGMIN=-360,ANGMAX=360_only",
                   variant_interface_maps="rebuilt_on_active_zone_crossings_ids1_2_3_4_5_8_10;unsupported_parent_OPF_only_ids6_7_9_11_omitted",
                   nyes_policy="omitted_from_all_primary_cases;optional_refined_2025_nyes_variant_only",
                   accounting_zone_exception="Buchanan_source900_H_is_parent77_G;parent_accounting_zone_preserved",
                   limitations=["Identity is DC-only algebraic scaffolding; it does not certify AC admittance identity",
                                "Exact PERFORM circuits are historical source rows, not confirmed 2025 as-built topology",
                                "Positive proxy attachments are explicit assumptions, not fitted passive residuals",
                                "Project R/X and fixed PAR controls remain assumptions and require sensitivity",
                                "Source-PD spatial load shares are 2019 proxies; unrepresented fractions stay on parent buses; all2025 zonal totals are conserved",
                                "No new branch is thermal/DLR-qualified; project MW is never treated as ampacity/MVA rating"])
    (output / "construction_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT)
    parser.add_argument("--attachment-scale", type=float, default=1.)
    parser.add_argument("--project-scale", type=float, default=1.)
    options = parser.parse_args()
    print(json.dumps(build(options.output, options.attachment_scale, options.project_scale), indent=2))
