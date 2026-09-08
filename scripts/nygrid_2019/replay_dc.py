"""Independently replay saved NYgrid DC cases using NumPy/SciPy, not MATPOWER.

Examples:
  python replay_dc.py output/nygrid_2019/pilot.mat --output-prefix output/nygrid_2019/pilot_independent_dc
  python replay_dc.py --require-annual

The input *_cases.csv must be the final, complete companion of every MAT
checkpoint. Missing or failed hours are errors, never silently excluded.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import scipy
from scipy.io import loadmat
from scipy.linalg import lu_factor, lu_solve
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/nygrid_2019"
TOLERANCE_MW = 1e-7
VARIABLES = ["base_case", "first_hour", "last_hour", "branch_pf", "bus_pd", "bus_va",
             "input_pg", "result_pg", "dc_pf", "status", "sim", "corrected_sim"]
INTERFACES = ["Dysinger East", "West Central", "Total East", "Moses South",
              "Central East", "UpNY-Coned", "Dun/SPR-South"]
# Literal signed rows in the pinned upstream Utility/flow4Plot.m, not the
# different OPF limit map. Both interpretations are independently reported.
RELEASED_MEMBERS = [[-32, 34, 37, 47], [-28, -29, 33, 50], [-14, -12, -3, -6, 8],
                    [-24, -18, -23], [-14, -12, -3, -6], [65, -66], [73, 74]]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrix(value, rows: int, columns: int, name: str) -> np.ndarray:
    out = np.asarray(value, dtype=float).reshape(rows, columns)
    require(np.isfinite(out).all(), f"{name}: missing/nonfinite values")
    return out


def network(case: dict) -> dict:
    bus, branch, gen, dc = (np.atleast_2d(np.asarray(case[k], dtype=float))
                            for k in ["bus", "branch", "gen", "dcline"])
    base = float(case["baseMVA"])
    nb, nl, ng, nd = len(bus), len(branch), len(gen), len(dc)
    require(base > 0 and np.isfinite(base), "Invalid baseMVA")
    for name, value in [("bus", bus), ("branch", branch), ("gen", gen), ("dcline", dc)]:
        require(np.isfinite(value).all(), f"Nonfinite base {name}")
    ids = bus[:, 0]
    require(len(set(ids)) == nb and np.equal(ids, np.floor(ids)).all(), "Bus identities not unique integers")
    lookup = {int(b): i for i, b in enumerate(ids)}

    def indices(values):
        require(np.equal(values, np.floor(values)).all(), "Nonintegral bus endpoint")
        require(all(int(v) in lookup for v in values), "Unknown bus endpoint")
        return np.asarray([lookup[int(v)] for v in values], dtype=int)

    f, t = indices(branch[:, 0]), indices(branch[:, 1])
    gf = indices(gen[:, 0])
    df, dt = indices(dc[:, 0]), indices(dc[:, 1])
    require(np.isin(bus[:, 1], [1, 2, 3]).all(), "Isolated/unknown bus type is not silently omitted")
    for name, status in [("branch", branch[:, 10]), ("generator", gen[:, 7]), ("dcline", dc[:, 2])]:
        require(np.isin(status, [0, 1]).all(), f"Unknown {name} status")
    active = branch[:, 10] == 1
    require(np.all(branch[active, 3] != 0), "Active zero-reactance branch")
    tap = branch[:, 8].copy()
    tap[tap == 0] = 1.0
    require((tap > 0).all(), "Nonpositive branch tap")
    require(np.equal(dc[:, 15:17], 0).all(), "This replay requires declared lossless DC links")
    incidence = np.zeros((nl, nb))
    incidence[np.arange(nl), f] = 1.0
    incidence[np.arange(nl), t] -= 1.0
    b = np.zeros(nl)
    b[active] = 1.0 / (branch[active, 3] * tap[active])
    # MW/radian nodal matrix; phase shifters have an explicit fixed injection.
    B = base * incidence.T @ (b[:, None] * incidence)
    phase_branch = -base * b * np.deg2rad(branch[:, 9])
    phase_bus = incidence.T @ phase_branch
    adjacency = csr_matrix((np.ones(2 * int(active.sum())),
                            (np.r_[f[active], t[active]], np.r_[t[active], f[active]])), shape=(nb, nb))
    require(connected_components(adjacency, directed=False)[0] == 1, "Disconnected network is not silently dropped")
    ref = np.flatnonzero(bus[:, 1] == 3)
    require(len(ref) == 1, "Expected one frozen NYgrid reference bus")
    nonref = np.flatnonzero(bus[:, 1] != 3)
    G = np.zeros((ng, nb))
    G[np.arange(ng), gf] = gen[:, 7]
    D = np.zeros((nd, nb))
    D[np.arange(nd), df] -= dc[:, 2]
    D[np.arange(nd), dt] += dc[:, 2]
    ref_generators = np.flatnonzero((gf == ref[0]) & (gen[:, 7] == 1))
    require(len(ref_generators) > 0, "Reference bus has no online generator")
    return dict(bus=bus, branch=branch, gen=gen, dc=dc, base=base, incidence=incidence,
                b=b, B=B, phase_branch=phase_branch, phase_bus=phase_bus, G=G, D=D,
                ref=ref, nonref=nonref, ref_generator=int(ref_generators[0]),
                lu=lu_factor(B[np.ix_(nonref, nonref)]), active=active)


def predict(net: dict, pd: np.ndarray, pg: np.ndarray, dc_pf: np.ndarray) -> dict:
    """Solve nonreference nodal equations; saved branch results are not inputs."""
    count = len(pd)
    ref, nonref = net["ref"], net["nonref"]
    angle = np.zeros_like(pd)
    angle[:, ref] = np.deg2rad(net["bus"][ref, 8])
    injection = pg @ net["G"] - pd - net["bus"][:, 4] + dc_pf @ net["D"]
    rhs = injection - net["phase_bus"]
    rhs_nonref = rhs[:, nonref] - angle[:, ref] @ net["B"][np.ix_(nonref, ref)].T
    angle[:, nonref] = lu_solve(net["lu"], rhs_nonref.T).T
    flow = (angle @ net["incidence"].T) * (net["base"] * net["b"]) + net["phase_branch"]
    exits = flow @ net["incidence"]
    residual_before_slack = exits - injection
    predicted_pg = pg.copy()
    predicted_pg[:, net["ref_generator"]] += residual_before_slack[:, ref[0]]
    final_injection = predicted_pg @ net["G"] - pd - net["bus"][:, 4] + dc_pf @ net["D"]
    require(np.isfinite(angle).all() and np.isfinite(flow).all(), "Independent solve is nonfinite")
    return {"angle_deg": np.rad2deg(angle), "flow": flow, "result_pg": predicted_pg,
            "nodal_residual_mw": np.max(np.abs(exits - final_injection), axis=1)}


def operator(members: list, branches: int) -> np.ndarray:
    out = np.zeros((len(members), branches))
    for j, values in enumerate(members):
        for value in values:
            require(float(value).is_integer() and 1 <= abs(value) <= branches, "Invalid signed interface branch row")
            out[j, abs(int(value)) - 1] += np.sign(value)
    return out


def timestamp(value: str) -> datetime:
    for pattern in ["%d-%b-%Y %H:%M:%S", "%d-%b-%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            pass
    raise ValueError(f"Unrecognized companion CSV timestamp: {value}")


def load_complete(path: Path) -> tuple[dict, list[dict], dict]:
    companion = path.with_name(path.stem + "_cases.csv")
    require(companion.is_file(), f"No final companion {companion}; MAT may still be a partial checkpoint")
    # Request numeric fields explicitly, avoiding MATLAB datetime/string opaque
    # workspace records. Dates are independently checked in the final CSV.
    m = loadmat(path, simplify_cells=True, variable_names=VARIABLES)
    require(all(k in m for k in VARIABLES), f"Incomplete saved schema in {path}")
    first, last = int(m["first_hour"]), int(m["last_hour"])
    require(1 <= first <= last <= 8760, "Hour bounds outside2019")
    n = last - first + 1
    with companion.open(encoding="utf-8-sig", newline="") as stream:
        records = list(csv.DictReader(stream))
    require(len(records) == n, f"Final companion row count differs from bounds for {path}")
    status = np.asarray(m["status"]).reshape(-1)
    require(len(status) == n and np.isin(status, [False, True]).all() and status.astype(bool).all(),
            f"Failed/uncomputed source hours in {path}; none excluded")
    for k, row in enumerate(records):
        expected = datetime(2019, 1, 1) + timedelta(hours=first + k - 1)
        require(timestamp(row["times"]) == expected, "Companion timestamps not exact consecutive hour bounds")
        require(row["status"].lower() in {"1", "true"} and not row.get("errors", "").strip(),
                "Companion records a source failure")
    info = {"mat_path": str(path.resolve()), "mat_sha256": sha_file(path),
            "final_csv_path": str(companion.resolve()), "final_csv_sha256": sha_file(companion),
            "first_hour": first, "last_hour": last, "hours": n}
    return m, records, info


def replay(paths: list[Path], output_prefix: Path, require_annual: bool = False) -> dict:
    require(paths and len(set(p.resolve() for p in paths)) == len(paths), "No inputs or duplicate input paths")
    hourly, inputs, seen, inventory = [], [], set(), []
    first_net = None
    for path in paths:
        m, records, info = load_complete(path)
        inputs.append(info)
        n = info["hours"]
        case = m["base_case"]
        net = network(case)
        require((len(net["bus"]), len(net["branch"]), len(net["gen"]), len(net["dc"])) == (57, 94, 271, 4),
                "Unexpected NYgrid source inventory; nothing omitted")
        if first_net is not None:
            for label, columns in [("bus", [0, 1, 4, 5, 8]), ("gen", [0, 7]), ("branch", list(range(13))), ("dc", [0, 1, 2, 15, 16])]:
                require(np.array_equal(net[label][:, columns], first_net[label][:, columns]),
                        f"Cross-chunk static {label} fields changed")
        else:
            first_net = net
        pd = matrix(m["bus_pd"], n, 57, "bus_pd")
        pg = matrix(m["input_pg"], n, 271, "input_pg")
        dc = matrix(m["dc_pf"], n, 4, "dc_pf")
        saved_flow = matrix(m["branch_pf"], n, 94, "branch_pf")
        saved_angle = matrix(m["bus_va"], n, 57, "bus_va")
        saved_gen = matrix(m["result_pg"], n, 271, "result_pg")
        saved_released = matrix(m["sim"], n, 7, "sim")
        saved_corrected = matrix(m["corrected_sim"], n, 7, "corrected_sim")
        ref_error = np.max(np.abs(saved_angle[:, net["ref"]] - net["bus"][net["ref"], 8]), axis=1)
        require(np.all(ref_error <= 1e-10), "Saved reference angle differs from frozen input reference angle")
        result = predict(net, pd, pg, dc)
        plot_operator = operator(RELEASED_MEMBERS, 94)
        interface_map = np.atleast_2d(np.asarray(case["if"]["map"], dtype=float))
        map_operator = operator([interface_map[interface_map[:, 0] == j, 1] for j in [1, 2, 3, 4, 5, 8, 10]], 94)
        require(np.all(np.any(map_operator != 0, axis=1)), "Missing interface map members")
        branch_error = np.max(np.abs(result["flow"] - saved_flow), axis=1)
        angle_error = np.max(np.abs(result["angle_deg"] - saved_angle), axis=1)
        gen_error = np.max(np.abs(result["result_pg"] - saved_gen), axis=1)
        plot_error = np.max(np.abs(result["flow"] @ plot_operator.T - saved_released), axis=1)
        map_error = np.max(np.abs(result["flow"] @ map_operator.T - saved_corrected), axis=1)
        rated = net["active"] & (net["branch"][:, 5] > 0)
        overload = np.zeros(n)
        if rated.any():
            overload = np.max(np.maximum(np.abs(result["flow"][:, rated]) - net["branch"][rated, 5], 0), axis=1)
        for k, record in enumerate(records):
            h = info["first_hour"] + k
            require(h not in seen, "Overlapping source chunks/hours")
            seen.add(h)
            largest = max(branch_error[k], gen_error[k], plot_error[k], map_error[k], result["nodal_residual_mw"][k])
            hourly.append({"hour_index": h, "timestamp": timestamp(record["times"]).isoformat(), "source_chunk": path.name,
                           "max_branch_pf_error_mw": float(branch_error[k]), "max_bus_angle_error_deg": float(angle_error[k]),
                           "max_result_pg_error_mw": float(gen_error[k]), "max_released_operator_error_mw": float(plot_error[k]),
                           "max_corrected_operator_error_mw": float(map_error[k]), "max_independent_nodal_residual_mw": float(result["nodal_residual_mw"][k]),
                           "reference_angle_error_deg": float(ref_error[k]), "max_active_rated_branch_overload_mw": float(overload[k]),
                           "replay_passed": bool(largest <= TOLERANCE_MW)})
        inventory.append({"source_chunk": path.name, "buses": 57, "branch_records": 94,
                          "active_branches": int(net["active"].sum()), "generator_records": 271,
                          "online_generators": int((net["gen"][:, 7] == 1).sum()), "dc_link_records": 4,
                          "active_dc_links": int((net["dc"][:, 2] == 1).sum()), "active_branches_with_positive_rate_a": int(rated.sum()),
                          "unrated_active_branches": int((net["active"] & ~rated).sum()),
                          "reference_bus": int(net["bus"][net["ref"][0], 0]),
                          "reference_input_angle_deg": float(net["bus"][net["ref"][0], 8])})
    hourly.sort(key=lambda x: x["hour_index"])
    complete = seen == set(range(1, 8761))
    require(not require_annual or complete, f"Annual replay requires8760unique completed hours; found{len(seen)}")
    summary = {"schema_version": 1, "method": "independent_numpy_scipy_DC_nodal_solve_no_MATPOWER_calls",
               "hours_replayed": len(hourly), "complete_2019_annual_coverage": complete,
               "source_failures_or_missing_hours_silently_excluded": False,
               "scope": "complete2019" if complete else "explicit_complete_input_subset_not_annual",
               "tolerance_mw": TOLERANCE_MW, "passed": all(x["replay_passed"] for x in hourly),
               "maximum_branch_pf_error_mw": max(x["max_branch_pf_error_mw"] for x in hourly),
               "maximum_angle_error_deg": max(x["max_bus_angle_error_deg"] for x in hourly),
               "maximum_result_pg_error_mw": max(x["max_result_pg_error_mw"] for x in hourly),
               "maximum_nodal_residual_mw": max(x["max_independent_nodal_residual_mw"] for x in hourly),
               "maximum_released_operator_error_mw": max(x["max_released_operator_error_mw"] for x in hourly),
               "maximum_corrected_operator_error_mw": max(x["max_corrected_operator_error_mw"] for x in hourly),
               "hours_with_positive_rate_a_overload": sum(x["max_active_rated_branch_overload_mw"] > TOLERANCE_MW for x in hourly),
               "maximum_rate_a_overload_mw": max(x["max_active_rated_branch_overload_mw"] for x in hourly),
               "rating_note": "DC_PF does not enforce branch bounds; rateA applied as active-flow diagnostic only, no AC or thermal qualification",
               "equations": {"branch_pf_mw": "baseMVA*status/(x*tap)*(theta_from-theta_to-shift_rad)",
                             "nodal_net_input_mw": "online_input_generation - PD - GS + DCto - DCfrom",
                             "reference": "fixed base_case REF angle, checked against every saved REF angle; only first online REF generator absorbs balance",
                             "shunts": "GS included at unity DC voltage; BS and charging excluded by DC equations, not evidence of AC neglect",
                             "DC_links": "all four records accounted; loss0/loss1 must equalzero"},
               "static_input_scope": "Every saved input/output array is checked; per-hour static status/GS/tap hardware relies on savedbase_case and the separately verified released construction",
               "inputs": inputs, "inventory": inventory, "interfaces": INTERFACES,
               "runtime": {"python": sys.version, "executable": sys.executable, "numpy": np.__version__, "scipy": scipy.__version__, "platform": platform.platform()},
               "script_path": str(Path(__file__).resolve()), "script_sha256": sha_file(Path(__file__))}
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output_prefix.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(hourly[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(hourly)
    summary["per_hour_csv"] = str(csv_path.resolve())
    summary["per_hour_csv_sha256"] = sha_file(csv_path)
    output_prefix.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def self_test() -> None:
    # A two-bus case tests tap, phase shift, GS and a fixed DC transfer together.
    # Required branch P=20+1-4.633231299858238-10=6.366768700141762MW.
    bus = np.zeros((2, 13)); bus[:, 0] = [10, 20]; bus[:, 1] = [3, 1]; bus[1, 4] = 1
    branch = np.zeros((1, 13)); branch[0, [0, 1, 3, 8, 9, 10]] = [10, 20, .1, 2, 5, 1]
    gen = np.zeros((2, 21)); gen[:, 0] = [10, 20]; gen[:, 7] = 1
    dc = np.zeros((1, 17)); dc[0, :3] = [10, 20, 1]
    net = network(dict(baseMVA=100, bus=bus, branch=branch, gen=gen, dcline=dc))
    p = predict(net, np.array([[0., 20.]]), np.array([[50., 4.633231299858238]]), np.array([[10.]]))
    require(abs(p["flow"][0, 0] - 6.366768700141762) < 1e-12, "Tap/phase/GS/DC flow fixture failed")
    require(abs(p["angle_deg"][0, 1] - np.rad2deg(-.1)) < 1e-12, "Independent angle fixture failed")
    require(abs(p["result_pg"][0, 0] - 16.366768700141762) < 1e-12, "Reference balance fixture failed")
    require(p["nodal_residual_mw"][0] < 1e-12, "Nodal fixture failed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path, nargs="*")
    parser.add_argument("--output-prefix", type=Path, default=OUTPUT / "independent_dc_replay")
    parser.add_argument("--require-annual", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    self_test()
    if args.self_test:
        print("Independent DC formula fixtures passed")
        return
    paths = args.inputs or sorted(OUTPUT.glob("annual_*.mat"))
    try:
        summary = replay(paths, args.output_prefix, args.require_annual)
    except Exception as error:
        args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
        failure = {"passed": False, "complete_2019_annual_coverage": False,
                   "error": f"{type(error).__name__}: {error}", "script_sha256": sha_file(Path(__file__)),
                   "input_paths": [str(p) for p in paths], "source_failures_or_missing_hours_silently_excluded": False}
        args.output_prefix.with_suffix(".json").write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(failure, indent=2))
        raise SystemExit(2)
    print(json.dumps({k: summary[k] for k in ["hours_replayed", "complete_2019_annual_coverage", "passed", "maximum_branch_pf_error_mw", "maximum_nodal_residual_mw"]}, indent=2))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
