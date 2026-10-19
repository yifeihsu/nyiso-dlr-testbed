"""Rebuild the unreduced 2019 NPCC DC baseline from source and verified captures.

The 8,760-hour PG evidence is the full-system DC solution embedded by the
upstream reduction's LoadRedistribution routine. Only its reference generator
is replaced by the released daily Indian Point 2 input to recover literal
pre-PF PG. All loads are reallocated independently from released source CSVs.
The final-device variant transfers the release's four lossless DC links and
the uniquely identified 81-125 AC branch removal onto the full network.
Source reproduction is accepted only when fresh captures and every annual
retained NY load/full solved PG agree within the stated tolerance. The final
device transfer is separately labelled: shunts in the released Ward reduction
make its incremental DC response differ from the full DC network. The full
derived variant must solve nodal DC equations, but is not called equivalent to
the released reduced model; its branch and interface discrepancies are saved.

Run after capture_full_stages.m. No annual MATLAB run or source modification.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import platform
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import scipy
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/nygrid_2019"))
from replay_dc import INTERFACES, load_complete, network, operator, predict, require, sha_file

SOURCE = ROOT / "tmp/nygrid_2019_reproduction/upstream"
DEFAULT_OUTPUT = ROOT / "output/nygrid_2019_full_stage1"
TOL_MW = 1e-6


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict]) -> None:
    require(bool(rows), f"No records for {path}")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def maxerr(left, right) -> float:
    require(np.shape(left) == np.shape(right), "Comparison shapes differ")
    return float(np.max(np.abs(np.asarray(left) - np.asarray(right)), initial=0))


def clean_case(case: dict) -> dict:
    """Retain data fields; remove callbacks and stale 140-name reduced metadata."""
    out = {key: copy.deepcopy(case[key]) for key in
           ["version", "baseMVA", "bus", "branch", "gen", "gencost", "genfuel", "if"] if key in case}
    out["version"] = "2"
    out["dcline"] = np.asarray(case.get("dcline", np.empty((0, 17))), dtype=float).reshape(-1, 17)
    return out


def hourly_table(path: Path, label: str, value: str, labels: list[str]) -> np.ndarray:
    out = np.full((8760, len(labels)), np.nan)
    start = datetime(2019, 1, 1)
    for row in read_csv(path):
        date = datetime.strptime(row["TimeStamp"], "%m/%d/%Y %H:%M:%S")
        hour = (date - start).total_seconds() / 3600
        require(hour.is_integer() and 0 <= hour < 8760, f"Invalid source hour {date}")
        if row[label] not in labels:
            continue
        h, j = int(hour), labels.index(row[label])
        require(np.isnan(out[h, j]), f"Duplicate source hour/category {date} {row[label]}")
        out[h, j] = float(row[value])
    require(np.isfinite(out).all(), f"Incomplete/nonfinite hourly source: {path}")
    return out


def source_loads(base: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Literal weighted allocation + renewable negative loads + external scaling."""
    bus = np.asarray(base["bus"])
    require(np.array_equal(bus[:, 0], np.arange(1, 141)), "Full source bus identities changed")
    zones = list("ABCDEFGHIJK")
    info = read_csv(SOURCE / "Data/npcc_new.csv")
    ny_info = [r for r in info if r["zone"] != "NA"]
    require(sorted(int(r["idx"]) for r in ny_info) == list(range(37, 83)), "NY bus set changed")
    loads = hourly_table(SOURCE / "Data/loadHourly_2019.csv", "ZoneID", "Load", zones)
    gross = np.zeros((8760, 140))
    for z, zone in enumerate(zones):
        members = [r for r in ny_info if r["zone"] == zone and float(r["sumLoadP0"]) > 0]
        if members:
            weight = np.asarray([float(r["sumLoadP0"]) for r in members])
            weight /= weight.sum()
        else:
            members = [r for r in ny_info if r["zone"] == zone]
            require(bool(members), f"Missing NY zone {zone}")
            weight = np.full(len(members), 1 / len(members))
        indices = np.asarray([int(r["idx"]) - 1 for r in members])
        gross[:, indices] = loads[:, z, None] * weight
    fuel = hourly_table(SOURCE / "Data/fuelmixHourly_2019.csv", "FuelCategory", "GenMW",
                        ["Wind", "Other Renewables"])
    renewable = np.zeros_like(gross)
    records = read_csv(SOURCE / "Data/RenewableGen.csv")
    for j, field in enumerate(["Pg Wind Cap", "Pg Other Cap"]):
        capacity = np.asarray([float(r[field] or 0) for r in records])
        require(capacity.sum() > 0, f"Missing renewable capacities {field}")
        for k, row in enumerate(records):
            renewable[:, int(row["bus_id"]) - 1] += fuel[:, j] * capacity[k] / capacity.sum()
    pd = np.broadcast_to(bus[:, 2], gross.shape).copy()
    qd = np.broadcast_to(bus[:, 3], gross.shape).copy()
    ny = np.arange(36, 82)
    external = np.r_[0:36, 82:140]
    # All external areas covered by source updateOpCond scaling: NE, IESO, PJM.
    source_info = read_csv(SOURCE / "Data/npcc.csv")
    require(all(int(r["area"]) in [1, 4, 5, 6] for r in source_info if r["zone"] == "NA"),
            "Unknown external scaling area")
    require(np.all(bus[:, 2] >= 0), "modifyMPC must have taken absolute original loads")
    ratio = gross[:, ny].sum(axis=1) / bus[ny, 2].sum()
    pd[:, external] *= ratio[:, None]
    pd[:, ny] = (gross - renewable)[:, ny]
    # Source changes only external PD. NY QD uses gross load at 0.98 PF.
    qd[:, ny] = gross[:, ny] * np.tan(np.arccos(0.98))
    return pd, qd, gross[:, ny].sum(axis=1)


def restore_reference_input(pg: np.ndarray, full_case: dict) -> tuple[np.ndarray, int]:
    ref_id = np.asarray(full_case["bus"])[np.asarray(full_case["bus"])[:, 1] == 3, 0]
    require(np.array_equal(ref_id, [74]), "Unknown full reference bus")
    gen = np.asarray(full_case["gen"])
    rows = np.flatnonzero((gen[:, 0] == 74) & (gen[:, 7] == 1))
    require(len(rows) == 2 and abs(gen[rows[0], 8] - 1025.9) < 1e-8,
            "Reference first generator is not the released Indian Point 2 row")
    daily = read_csv(SOURCE / "Data/nuclearGenDaily_2019.csv")
    require(len(daily) == 365, "Incomplete daily nuclear source")
    by_day = {}
    for row in daily:
        date = datetime.strptime(row["TimeStamp"], "%m/%d/%Y").date()
        require(date not in by_day, "Duplicate nuclear source date")
        by_day[date] = float(row["IndianPoint2Gen"])
    out = pg.copy()
    for hour in range(8760):
        day = (datetime(2019, 1, 1) + timedelta(hours=hour)).date()
        require(day in by_day, "Missing nuclear source day")
        out[hour, rows[0]] = by_day[day]
    return out, int(rows[0])


def physical_branch_map(full: np.ndarray, reduced: np.ndarray) -> dict[int, int]:
    """One-to-one match using endpoints and DC parameters, allowing parallel rows."""
    result, used = {}, set()
    # Reduction discards R/B; x, tap, phase, status identify preserved DC elements.
    for j, row in enumerate(reduced):
        candidates = []
        for i, candidate in enumerate(full):
            taps = [v if v else 1.0 for v in (candidate[8], row[8])]
            if (i not in used and np.array_equal(candidate[[0, 1, 10]], row[[0, 1, 10]])
                    and abs(candidate[3] - row[3]) < 1e-12
                    and abs(taps[0] - taps[1]) < 1e-12
                    and abs(candidate[9] - row[9]) < 1e-12):
                candidates.append(i)
        if candidates:
            result[j] = candidates[0]
            used.add(candidates[0])
    return result


def full_device_case(full: dict, pre: dict, final: dict) -> tuple[dict, int]:
    before, after = np.asarray(pre["branch"]), np.asarray(final["branch"])
    require(before.shape == (95, 13) and after.shape == (94, 13), "Unexpected reduced device stages")
    require(maxerr(np.delete(before, 75, axis=0), after) < 1e-12,
            "Final released AC branch mutation is not exactly row 76 removal")
    deleted = before[75]
    mapping = physical_branch_map(np.asarray(full["branch"]), deleted[None, :])
    require(0 in mapping, "Deleted reduced AC branch has no physical full counterpart")
    matching_endpoints = np.flatnonzero(np.all(np.asarray(full["branch"])[:, :2] == deleted[:2], axis=1))
    require(len(matching_endpoints) == 1, "Full removed branch endpoints are not unique")
    removed = mapping[0]
    out = clean_case(full)
    out["branch"] = np.delete(out["branch"], removed, axis=0)
    out["dcline"] = np.asarray(final["dcline"]).copy()
    for key in ["gencost", "genfuel"]:
        if key in final:
            out[key] = copy.deepcopy(final[key])
    # Remap every released interface member by physical identity, not row number.
    mapping = physical_branch_map(out["branch"], after)
    imap = np.asarray(final["if"]["map"]).copy()
    for row in imap:
        reduced_row = abs(int(row[1])) - 1
        require(reduced_row in mapping, "Interface uses an unmatched equivalent branch")
        row[1] = np.sign(row[1]) * (mapping[reduced_row] + 1)
    out["if"] = {"map": imap, "lims": np.asarray(final["if"]["lims"]).copy()}
    return out, removed


def interface_operator(case: dict) -> np.ndarray:
    imap = np.asarray(case["if"]["map"])
    return operator([imap[imap[:, 0] == j, 1] for j in [1, 2, 3, 4, 5, 8, 10]], len(case["branch"]))


def reduction_diagnostics(full: dict, pre_reduced: dict) -> dict:
    """Explain a source-code-supported discrepancy without changing the model."""
    nf, nr = network(clean_case(full)), network(clean_case(pre_reduced))
    lookup = {int(b): i for i, b in enumerate(nf["bus"][:, 0])}
    retained = np.asarray([lookup[int(b)] for b in nr["bus"][:, 0]])
    eliminated = np.setdiff1d(np.arange(len(nf["bus"])), retained)

    def schur(B):
        return (B[np.ix_(retained, retained)] - B[np.ix_(retained, eliminated)] @
                np.linalg.solve(B[np.ix_(eliminated, eliminated)], B[np.ix_(eliminated, retained)]))

    dc_schur = schur(nf["B"])
    charging = nf["bus"][:, 5].copy()
    for endpoint in [0, 1]:
        indices = np.asarray([lookup[int(b)] for b in nf["branch"][:, endpoint]])
        np.add.at(charging, indices, nf["base"] * nf["branch"][:, 4] / 2)
    source_schur = schur(nf["B"] + np.diag(charging))
    offdiag = ~np.eye(len(retained), dtype=bool)
    source_error = float(np.abs(source_schur - nr["B"])[offdiag].max())
    require(source_error <= 1e-6, "Unexpected reduction mechanism; source shunts do not explain its off-diagonal matrix")
    return {"pure_dc_schur_vs_reduced_offdiagonal_max_mw_per_rad": float(np.abs(dc_schur - nr["B"])[offdiag].max()),
            "source_shunt_augmented_schur_vs_reduced_offdiagonal_max_mw_per_rad": source_error,
            "cause": "Initiation.m includes bus BS and branch B/2 in SelfB before elimination. DC PF ignores these shunts. LoadRedistribution.m matches the original solved state by adjusting reduced PD, but subsequent device changes need not match full-network responses.",
            "source_files": ["reduction_toolbox/mirror/Initiation.m", "reduction_toolbox/mirror/LoadRedistribution.m"]}


def verify_sources() -> list[dict]:
    manifest_path = ROOT / "output/nygrid_2019/upstream_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    records = []
    for item in manifest["files"]:
        path = SOURCE / item["path"]
        digest = sha_file(path)
        require(digest == item["sha256"], f"Frozen upstream source changed: {path}")
        records.append({"path": str(path.relative_to(ROOT)), "sha256": digest,
                        "role": "pinned_upstream_source", "upstream_commit": manifest["commit"]})
    return records


def replay(output: Path, captures_path: Path) -> dict:
    names = ["full_year.mat", "full_year_summary.json", "full_year_hourly.csv", "full_year_capture_checks.csv",
             "full_year_source_manifest.csv", "full_year_interface_metrics.csv", "full_year_branch_correspondence.csv"]
    require(not any((output / name).exists() for name in names),
            "Replay refuses to overwrite existing full-year evidence; select a new output directory")
    provenance = verify_sources()
    evidence = loadmat(captures_path, simplify_cells=True,
                       variable_names=["base", "captures", "hour_indices", "timestamps"])
    captures = evidence["captures"]
    if isinstance(captures, dict):
        captures = [captures]
    require(len(captures) == 13, "Require the 12 monthly source captures and summer peak capture")
    capture_hours = np.asarray(evidence["hour_indices"], dtype=int).reshape(-1)
    expected_hours = [int((datetime(2019, m, 1) - datetime(2019, 1, 1)).total_seconds() / 3600) + 1
                      for m in range(1, 13)]
    expected_hours.append(int((datetime(2019, 7, 20, 17) - datetime(2019, 1, 1)).total_seconds() / 3600) + 1)
    require(sorted(capture_hours) == sorted(expected_hours), "Unexpected capture coverage")
    full = clean_case(captures[0]["full_input"])
    require((len(full["bus"]), len(full["branch"]), len(full["gen"])) == (140, 226, 271),
            "Unexpected full unreduced inventory")
    full_final, removed = full_device_case(full, captures[0]["reduced_pre_hvdc"], captures[0]["final_input"])
    reduced = clean_case(captures[0]["final_input"])
    net_pre, net_final, net_reduced = network(full), network(full_final), network(reduced)
    chunks, source_chunks, hour_order = [], [], []
    for quarter in range(1, 5):
        path = ROOT / f"output/nygrid_2019/annual_{quarter}.mat"
        chunk, _, receipt = load_complete(path)
        chunk.update(loadmat(path, simplify_cells=True, variable_names=["actual", "limit"]))
        for key, columns in [("bus", [0, 1, 4]), ("gen", [0, 7]), ("branch", list(range(13)))]:
            require(maxerr(np.asarray(chunk["base_case"][key])[:, columns], reduced[key][:, columns]) < 1e-10,
                    f"Saved annual topology/identity changed: {key}")
        chunks.append(chunk)
        source_chunks.append(receipt)
        hour_order.extend(range(receipt["first_hour"], receipt["last_hour"] + 1))
    require(hour_order == list(range(1, 8761)), "Annual evidence not complete and ordered")
    joined = {key: np.concatenate([np.atleast_2d(c[key]) for c in chunks]) for key in
              ["bus_pd", "input_pg", "result_pg", "dc_pf", "branch_pf", "bus_va", "corrected_sim", "actual", "limit"]}
    for key, array in joined.items():
        require(len(array) == 8760 and np.isfinite(array).all(), f"Nonfinite/incomplete annual {key}")
    pd, qd, gross_ny = source_loads(evidence["base"])
    pg, slack_row = restore_reference_input(joined["input_pg"], full)
    ny_reduced = np.flatnonzero((reduced["bus"][:, 0] >= 37) & (reduced["bus"][:, 0] <= 82))
    require(np.array_equal(reduced["bus"][ny_reduced, 0], np.arange(37, 83)), "Retained NY bus order changed")
    source_pd_error = maxerr(pd[:, 36:82], joined["bus_pd"][:, ny_reduced])
    require(source_pd_error <= TOL_MW, f"Source NY load reconstruction differs: {source_pd_error} MW")
    require(np.array_equal(full["gen"][:, 7], reduced["gen"][:, 7]), "Generator status preservation failed")
    pre_result = predict(net_pre, pd, pg, np.empty((8760, 0)))
    final_result = predict(net_final, pd, pg, joined["dc_pf"])
    # Reduced replay is separate and assures saved annual arrays are coherent.
    reduced_result = predict(net_reduced, joined["bus_pd"], joined["input_pg"], joined["dc_pf"])
    reduced_replay_error = maxerr(reduced_result["flow"], joined["branch_pf"])
    require(reduced_replay_error <= TOL_MW, "Saved reduced annual replay failed")
    full_pg_error = maxerr(pre_result["result_pg"], joined["input_pg"])
    require(full_pg_error <= TOL_MW, f"Source full-solution PG preservation failed: {full_pg_error} MW")
    post_op = interface_operator(full_final)
    # Before device mutation, the same physical interface members use full rows.
    pre_op = np.insert(post_op, removed, 0, axis=1)
    interfaces = final_result["flow"] @ post_op.T
    pre_interfaces = pre_result["flow"] @ pre_op.T
    mapping = physical_branch_map(full_final["branch"], reduced["branch"])
    reduced_rows = np.asarray(sorted(mapping))
    full_rows = np.asarray([mapping[j] for j in reduced_rows])
    require(len(mapping) == 78, f"Unexpected preserved physical branch count: {len(mapping)}")
    branch_errors = np.max(np.abs(final_result["flow"][:, full_rows] - joined["branch_pf"][:, reduced_rows]), axis=1)
    interface_errors = np.max(np.abs(interfaces - joined["corrected_sim"]), axis=1)
    reduced_equivalence = bool(float(branch_errors.max()) <= TOL_MW and float(interface_errors.max()) <= TOL_MW)
    reduction_explanation = reduction_diagnostics(full, captures[0]["reduced_pre_hvdc"])
    checks = []
    for i, cap in enumerate(captures):
        h = capture_hours[i] - 1
        native = clean_case(cap["full_input"])
        for key, columns in [("bus", [0, 1, 4, 5, 8]), ("gen", [0, 7]), ("branch", list(range(13)))]:
            require(maxerr(native[key][:, columns], full[key][:, columns]) < 1e-10,
                    f"Capture full static fields changed: {key}")
        cap_final, cap_removed = full_device_case(native, cap["reduced_pre_hvdc"], cap["final_input"])
        require(cap_removed == removed, "Removed full branch changed across captures")
        row = {"hour_index": int(h + 1), "timestamp": (datetime(2019, 1, 1) + timedelta(hours=int(h))).isoformat(),
               "full_input_pd_error_mw": maxerr(pd[h], native["bus"][:, 2]),
               "full_input_qd_error_mvar": maxerr(qd[h], native["bus"][:, 3]),
               "full_input_pg_error_mw": maxerr(pg[h], native["gen"][:, 1]),
               "full_pre_matpower_flow_error_mw": maxerr(pre_result["flow"][h], np.asarray(cap["full_result"]["branch"])[:, 13]),
               "full_pre_matpower_pg_error_mw": maxerr(pre_result["result_pg"][h], np.asarray(cap["full_result"]["gen"])[:, 1]),
               "saved_reduced_input_pg_error_mw": maxerr(joined["input_pg"][h], np.asarray(cap["final_input"]["gen"])[:, 1]),
               "saved_reduced_final_flow_error_mw": maxerr(joined["branch_pf"][h], np.asarray(cap["final_result"]["branch"])[:, 13]),
               "full_final_vs_reduced_flow_error_mw": float(branch_errors[h]),
               "full_final_vs_reduced_interface_error_mw": float(interface_errors[h])}
        # Every fresh MATLAB pre-reduction PF and pre-HVDC reduced PF agree on
        # retained physical branches, independent of post-reduction additions.
        pre_map = physical_branch_map(full["branch"], np.asarray(cap["reduced_pre_hvdc"]["branch"]))
        pre_r = np.asarray(sorted(pre_map))
        pre_f = np.asarray([pre_map[j] for j in pre_r])
        row["full_pre_vs_reduced_pre_flow_error_mw"] = maxerr(pre_result["flow"][h, pre_f],
                    np.asarray(cap["reduced_pre_hvdc_result"]["branch"])[pre_r, 13])
        require(max(v for k, v in row.items() if k.endswith(("_mw", "_mvar")) and not k.startswith("full_final_vs_reduced")) <= TOL_MW,
                f"Source capture reconstruction mismatch: {row}")
        checks.append(row)
    # Preserve hourly external PMAX for DC diagnostics. Hourly generation cost
    # and ramp metadata are not reconstructed; base-case values are a snapshot.
    pmax = np.broadcast_to(full["gen"][:, 8], pg.shape).copy()
    external_rows = np.flatnonzero((full["gen"][:, 0] < 37) | (full["gen"][:, 0] > 82))
    pmax[:, external_rows] = 1.5 * pg[:, external_rows]
    for i, cap in enumerate(captures):
        require(maxerr(pmax[capture_hours[i] - 1], np.asarray(cap["full_input"]["gen"])[:, 8]) <= TOL_MW,
                "Hourly generator PMAX reconstruction failed")
    for result in [pre_result, final_result, reduced_result]:
        require(float(result["nodal_residual_mw"].max()) <= TOL_MW, "Nodal DC balance failed")
    # Baseline case corresponds to the first source hour. Full input PG remains
    # literal pre-PF PG, so its first reference nuclear unit is not pre-balanced.
    for case in [full, full_final]:
        case["bus"][:, 2] = pd[0]
        case["bus"][:, 3] = qd[0]
        case["gen"][:, 1] = pg[0]
    full_final["dcline"][:, 3] = joined["dc_pf"][0]
    timestamps = [(datetime(2019, 1, 1) + timedelta(hours=h)).isoformat() for h in range(8760)]
    summary = {
        "status": "validated_source_full_pre_hvdc_plus_derived_full_final_devices_dc_baseline", "hours": 8760, "fresh_source_capture_hours": len(checks),
        "created_utc": datetime.now(timezone.utc).isoformat(), "tolerance_mw": TOL_MW,
        "stages": {"full_pre_hvdc": {"buses": 140, "ac_branches": 226, "generators": 271, "dc_links": 0},
                   "full_with_final_devices": {"buses": 140, "ac_branches": 225, "generators": 271, "dc_links": 4},
                   "released_reduced_final": {"buses": 57, "ac_branches": 94, "generators": 271, "dc_links": 4}},
        "removed_full_branch_row_1based": int(removed + 1),
        "removed_full_branch_endpoints": full["branch"][removed, :2].astype(int).tolist(),
        "preserved_physical_reduced_branches_verified": len(mapping),
        "max_source_ny_pd_error_mw": source_pd_error, "max_full_solution_pg_preservation_error_mw": full_pg_error,
        "max_reduced_annual_replay_error_mw": reduced_replay_error,
        "max_full_final_retained_branch_error_mw": float(branch_errors.max()),
        "max_full_final_interface_error_mw": float(interface_errors.max()),
        "reduced_final_equivalence": reduced_equivalence,
        "rms_full_final_retained_branch_difference_mw": float(np.sqrt(np.mean((final_result["flow"][:, full_rows] - joined["branch_pf"][:, reduced_rows]) ** 2))),
        "rms_full_final_interface_difference_mw": float(np.sqrt(np.mean((interfaces - joined["corrected_sim"]) ** 2))),
        "reduction_discrepancy_explanation": reduction_explanation,
        "full_final_vs_nyiso_pooled_wape_pct": float(100 * np.abs(interfaces - joined["actual"]).sum() / np.abs(joined["actual"]).sum()),
        "reduced_final_vs_nyiso_pooled_wape_pct": float(100 * np.abs(joined["corrected_sim"] - joined["actual"]).sum() / np.abs(joined["actual"]).sum()),
        "observation_metric_scope": "Primary all8760 nominal local hours, including source imputation and DST ambiguity; seven interfaces overlap and pooled WAPE is not statewide balance error",
        "max_full_pre_nodal_balance_residual_mw": float(pre_result["nodal_residual_mw"].max()),
        "max_full_final_nodal_balance_residual_mw": float(final_result["nodal_residual_mw"].max()),
        "reference_input_restoration": {"generator_row_1based": slack_row + 1, "bus": 74,
            "source": "nuclearGenDaily_2019.csv:IndianPoint2Gen", "reason": "LoadRedistribution overwrites PG with full solved PG"},
        "evidence_status": "Fresh 13-hour source/MATPOWER validation; annual independent replay using frozen saved annual PG and fresh raw CSV load allocation",
        "model_scope": "DC research model; source full pre-HVDC reconstruction verified exactly within tolerance; separately derived full final-device transfer has quantified nonzero differences from released reduced network",
        "snapshot_metadata": {"base_case_hour_index": 1, "hourly_generator_pmax_available": True,
                              "hourly_generator_cost_available": False, "hourly_ramp_metadata_available": False,
                              "hourly_interface_positive_limits_available": True,
                              "hourly_interface_negative_limits_available": False,
                              "note": "base_case gencost, ramp columns and if.lims are first-hour snapshot metadata; hourly DC diagnostic loaders must not silently reuse them"},
        "limits": ["Annual thermal generator PG reuses frozen validated 2019 allocation evidence; not a fresh annual RGGI allocation run",
                   "Full final-device expansion is derived here, not an unreduced file published by the paper",
                   "Full final-device variant is not claimed equivalent to released reduced model; the exact-equivalence gate fails and the measured differences are retained",
                   "DC convergence is not AC feasibility or thermal/rating certification", "Inherited capacities and hourly dispatch can violate generator or branch limits",
                   "Source labels are 8760 nominal local hourly labels; DST source-quality qualifications remain applicable"],
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "annual_input_receipts": source_chunks,
    }
    output.mkdir(parents=True, exist_ok=True)
    savemat(output / "full_year.mat", {
        "base_case": full_final, "full_pre_hvdc_case": full, "reduced_final_case": reduced,
        "hour_index": np.arange(1, 8761)[:, None], "timestamp_iso": np.asarray(timestamps, dtype=object)[:, None],
        "bus_pd": pd, "bus_qd": qd, "input_pg": pg, "result_pg": final_result["result_pg"],
        "gen_pmax": pmax, "external_generator_rows_1based": external_rows + 1,
        "dc_pf": joined["dc_pf"], "branch_pf": final_result["flow"], "bus_va": final_result["angle_deg"],
        "pre_hvdc_branch_pf": pre_result["flow"], "pre_hvdc_bus_va": pre_result["angle_deg"],
        "pre_hvdc_result_pg": pre_result["result_pg"], "interface_mw": interfaces,
        "pre_hvdc_interface_mw": pre_interfaces, "interface_names": np.asarray(INTERFACES, dtype=object),
        "observed_interface_mw": joined["actual"], "interface_positive_limit_mw": joined["limit"],
        "reduced_final_interface_mw": joined["corrected_sim"], "reduced_final_equivalence": reduced_equivalence,
        "gross_ny_load_mw": gross_ny, "removed_full_branch_row_1based": removed + 1,
        "reference_generator_row_1based": slack_row + 1,
        "nodal_balance_residual_mw": final_result["nodal_residual_mw"],
        "reduced_interface_error_mw": interface_errors,
    }, do_compression=True, long_field_names=True)
    rows = [{"hour_index": h + 1, "timestamp": timestamps[h], "gross_ny_load_mw": gross_ny[h],
             "full_nodal_balance_residual_mw": final_result["nodal_residual_mw"][h],
             "retained_branch_error_mw": branch_errors[h], "interface_error_mw": interface_errors[h],
             "reference_pg_adjustment_mw": final_result["result_pg"][h, slack_row] - pg[h, slack_row],
             **{f"interface_{j + 1}_mw": interfaces[h, j] for j in range(7)}} for h in range(8760)]
    write_csv(output / "full_year_hourly.csv", rows)
    write_csv(output / "full_year_capture_checks.csv", checks)
    write_csv(output / "full_year_interface_metrics.csv", [
        {"interface": name, "hours": 8760, "max_abs_reduced_error_mw": float(np.abs(interfaces[:, j] - joined["corrected_sim"][:, j]).max()),
         "rms_reduced_difference_mw": float(np.sqrt(np.mean((interfaces[:, j] - joined["corrected_sim"][:, j]) ** 2))),
         "full_final_vs_nyiso_wape_pct": float(100 * np.abs(interfaces[:, j] - joined["actual"][:, j]).sum() / np.abs(joined["actual"][:, j]).sum()),
         "reduced_final_vs_nyiso_wape_pct": float(100 * np.abs(joined["corrected_sim"][:, j] - joined["actual"][:, j]).sum() / np.abs(joined["actual"][:, j]).sum()),
         "mean_mw": float(interfaces[:, j].mean()), "min_mw": float(interfaces[:, j].min()), "max_mw": float(interfaces[:, j].max()),
         "max_final_minus_pre_device_mw": float(np.abs(interfaces[:, j] - pre_interfaces[:, j]).max())}
        for j, name in enumerate(INTERFACES)])
    write_csv(output / "full_year_branch_correspondence.csv", [
        {"reduced_final_row_1based": int(r + 1), "full_final_row_1based": int(mapping[r] + 1),
         "from_bus": int(reduced["branch"][r, 0]), "to_bus": int(reduced["branch"][r, 1]),
         "max_abs_annual_flow_error_mw": float(np.abs(final_result["flow"][:, mapping[r]] - joined["branch_pf"][:, r]).max())}
        for r in sorted(mapping)])
    extra = [captures_path, Path(__file__), ROOT / "scripts/nygrid_2019/replay_dc.py",
             ROOT / "output/nygrid_2019/upstream_manifest.json"]
    for receipt in source_chunks:
        extra.extend([Path(receipt["mat_path"]), Path(receipt["final_csv_path"])])
    extra.extend(sorted((ROOT / "tmp/nygrid_2019_reproduction/reduction_toolbox/mirror").glob("*.m")))
    for path in extra:
        provenance.append({"path": str(path.relative_to(ROOT)), "sha256": sha_file(path),
                           "role": "replay_input_or_code", "upstream_commit": ""})
    write_csv(output / "full_year_source_manifest.csv", provenance)
    summary["full_year_mat_sha256"] = sha_file(output / "full_year.mat")
    (output / "full_year_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--captures", type=Path, default=DEFAULT_OUTPUT / "captured_stages.mat")
    args = parser.parse_args()
    print(json.dumps(replay(args.output.resolve(), args.captures.resolve()), indent=2))
