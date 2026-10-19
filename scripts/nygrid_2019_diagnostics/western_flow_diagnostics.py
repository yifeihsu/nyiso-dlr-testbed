"""Diagnose the corrected western NYgrid interfaces without fitting the model.

All baseline electrical states are read from the frozen released 57-bus annual
reproduction. The independent DC solver verifies them before analysis. Observed
interface differences imply an oracle injection only under the modeled cut and
lossless-balance assumptions; they are not measured zonal generation telemetry.
Writes only western_* files in the dedicated diagnostics output directory.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tmp/nygrid_2019_reproduction/upstream"
OUTPUT = ROOT / "output/nygrid_2019_diagnostics"
sys.path.insert(0, str(ROOT / "scripts/nygrid_2019"))
from replay_dc import INTERFACES, load_complete, network, operator, predict, require, sha_file, timestamp

ZONES = list("ABCDEFGHIJK")
THERMAL_TYPES = {"Combustion Turbine", "Combined Cycle", "Jet Engine", "Steam Turbine", "Internal Combustion"}


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, records: list[dict]) -> None:
    require(bool(records), f"Empty diagnostic output: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def maxabs(values) -> float:
    return float(np.max(np.abs(values), initial=0))


def source_hourly(filename: str, label: str, value: str, labels: list[str]) -> np.ndarray:
    values = np.full((8760, len(labels)), np.nan)
    lookup = {name: i for i, name in enumerate(labels)}
    start = datetime(2019, 1, 1)
    for row in read_csv(SOURCE / "Data" / filename):
        if row[label] not in lookup:
            continue
        stamp = row["TimeStamp"]
        t = datetime.strptime(stamp, "%m/%d/%Y %H:%M:%S" if stamp.count(":") == 2 else "%m/%d/%Y %H:%M")
        h = (t - start).total_seconds() / 3600
        require(h.is_integer() and 0 <= h < 8760, f"Source hour outside annual population: {filename}")
        h, j = int(h), lookup[row[label]]
        require(np.isnan(values[h, j]), f"Duplicate hour/category in {filename}")
        values[h, j] = float(row[value])
    require(np.isfinite(values).all(), f"Missing/nonfinite source values: {filename}")
    return values


def load_inputs() -> dict:
    """Shared immutable baseline loader for independent diagnostics.

    Returns case, net, pd, input_pg, result_pg, dc_pf, branch_pf, sim, obs,
    times, months, meta, bus_zones, gen_zones, genfuel, operator, and receipts.
    All hourly matrices have hours on rows; interfaces follow INTERFACES.
    """
    manifests = json.loads((ROOT / "output/nygrid_2019/upstream_manifest.json").read_text())
    require(manifests["commit"] == "47698b6c7823ae7b1bc6935e5601d5b64b8f918e", "Unexpected upstream commit")
    receipts = []
    sources = ["Data/npcc.csv", "Data/npcc_new.csv", "Data/RenewableGen.csv",
               "Data/loadHourly_2019.csv", "Data/fuelmixHourly_2019.csv",
               "Data/nuclearGenDaily_2019.csv", "Data/hydroGenMonthly_2019.csv",
               "Data/interflowHourly_2019.csv", "updateOpCond.m", "Utility/allocateLoad.m"]
    for relative in sources:
        path = SOURCE / relative
        record = next(r for r in manifests["files"] if r["path"] == relative)
        require(sha_file(path) == record["sha256"], f"Pinned source changed: {relative}")
        receipts.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha_file(path), "role": "pinned_source"})
    meta = {int(r["idx"]): r for r in read_csv(SOURCE / "Data/npcc.csv")}
    values = {key: [] for key in ["pd", "input_pg", "result_pg", "dc_pf", "branch_pf", "sim", "obs"]}
    times, cases = [], []
    solver_max = {key: 0.0 for key in ["branch_error_mw", "generator_error_mw", "nodal_balance_error_mw", "operator_error_mw"]}
    for quarter in range(1, 5):
        path = ROOT / f"output/nygrid_2019/annual_{quarter}.mat"
        m, records, info = load_complete(path)
        case = m["base_case"]
        net = network(case)
        require((len(net["bus"]), len(net["branch"]), len(net["gen"]), len(net["dc"])) == (57, 94, 271, 4),
                "Unexpected baseline inventory")
        if cases:
            first = cases[0]
            for key, columns in [("bus", [0, 1, 4, 5, 8, 9]), ("branch", list(range(13))),
                                 ("gen", [0, 7]), ("dcline", [0, 1, 2, 15, 16])]:
                require(np.array_equal(case[key][:, columns], first[key][:, columns]), f"Static {key} changed between chunks")
            require(np.array_equal(case["genfuel"], first["genfuel"]), "Generator classification changed")
        cases.append(case)
        imap = np.asarray(case["if"]["map"])
        op = operator([imap[imap[:, 0] == i, 1] for i in [1, 2, 3, 4, 5, 8, 10]], 94)
        n = info["hours"]
        pd = np.asarray(m["bus_pd"], float).reshape(n, 57)
        pg = np.asarray(m["input_pg"], float).reshape(n, 271)
        dc = np.asarray(m["dc_pf"], float).reshape(n, 4)
        flow = np.asarray(m["branch_pf"], float).reshape(n, 94)
        result_pg = np.asarray(m["result_pg"], float).reshape(n, 271)
        sim = np.asarray(m["corrected_sim"], float).reshape(n, 7)
        replay = predict(net, pd, pg, dc)
        errors = {"branch_error_mw": maxabs(replay["flow"] - flow),
                  "generator_error_mw": maxabs(replay["result_pg"] - result_pg),
                  "nodal_balance_error_mw": maxabs(replay["nodal_residual_mw"]),
                  "operator_error_mw": maxabs(flow @ op.T - sim)}
        require(max(errors.values()) < 1e-7, "Independent baseline replay failed")
        for key, value in errors.items():
            solver_max[key] = max(solver_max[key], value)
        obs = np.full((n, 7), np.nan)
        interface_csv = path.with_name(path.stem + "_interfaces.csv")
        for record in read_csv(interface_csv):
            t = timestamp(record["timestamp"])
            h = int((t - datetime(2019, 1, 1)).total_seconds() / 3600) + 1 - info["first_hour"]
            j = INTERFACES.index(record["interface"])
            require(0 <= h < n and np.isnan(obs[h, j]), "Duplicate or out-of-range interface observation")
            require(abs(float(record["corrected_operator_mw"]) - sim[h, j]) < 1e-7, "Interface CSV is stale")
            obs[h, j] = float(record["observed_mw"])
        require(np.isfinite(obs).all(), "Incomplete observed interface series")
        for key, array in [("pd", pd), ("input_pg", pg), ("result_pg", result_pg),
                           ("dc_pf", dc), ("branch_pf", flow), ("sim", sim), ("obs", obs)]:
            values[key].append(array)
        times.extend(timestamp(r["times"]) for r in records)
        for item, role in [(path, "released_annual_case"), (path.with_name(path.stem + "_cases.csv"), "annual_completeness"),
                           (interface_csv, "observations_and_corrected_operators")]:
            receipts.append({"path": item.relative_to(ROOT).as_posix(), "sha256": sha_file(item), "role": role})
    require(times == [datetime(2019, 1, 1) + timedelta(hours=i) for i in range(8760)], "Annual hourly sequence changed")
    case = cases[0]
    net = network(case)
    return {**{key: np.vstack(parts) for key, parts in values.items()},
            "case": case, "net": net, "operator": op, "times": times,
            "months": np.asarray([t.month for t in times]), "meta": meta,
            "bus_zones": np.asarray([meta[int(b)]["zone"] for b in net["bus"][:, 0]]),
            "gen_zones": np.asarray([meta[int(b)]["zone"] for b in net["gen"][:, 0]]),
            "genfuel": np.asarray(case["genfuel"]).astype(str), "inputs": receipts,
            "replay_checks": solver_max}


def metrics(sim: np.ndarray, obs: np.ndarray) -> dict:
    err = sim - obs
    require(sim.shape == obs.shape and len(sim) > 0, "Invalid metric population")
    absolute = np.abs(err)
    denom = np.abs(obs)
    nz = denom > 1e-12
    ape = absolute[nz] / denom[nz]
    return {"hours": len(sim), "mean_sim_mw": float(np.mean(sim)), "mean_observed_mw": float(np.mean(obs)),
            "mean_absolute_observed_mw": float(np.mean(denom)), "mae_mw": float(np.mean(absolute)),
            "rmse_mw": float(np.sqrt(np.mean(err ** 2))), "bias_sim_minus_observed_mw": float(np.mean(err)),
            "wape_pct": float(100 * absolute.sum() / denom.sum()) if denom.sum() > 0 else None,
            "mape_nonzero_pct": float(100 * ape.mean()) if len(ape) else None,
            "median_absolute_error_mw": float(np.median(absolute)), "p95_absolute_error_mw": float(np.quantile(absolute, .95)),
            "maximum_absolute_error_mw": float(absolute.max()), "opposite_direction_hours": int(np.sum(sim * obs < 0)),
            "positive_error_hours": int(np.sum(err > 1e-7)), "negative_error_hours": int(np.sum(err < -1e-7)),
            "zero_observed_hours": int(np.sum(~nz)), "observed_abs_below_100mw_hours": int(np.sum(denom < 100)),
            "observed_abs_below_250mw_hours": int(np.sum(denom < 250)), "observed_abs_below_500mw_hours": int(np.sum(denom < 500))}


def correlation(a, b) -> float | None:
    if np.std(a) < 1e-10 or np.std(b) < 1e-10:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def components(data: dict) -> dict:
    gross = source_hourly("loadHourly_2019.csv", "ZoneID", "Load", ZONES)
    fuel = source_hourly("fuelmixHourly_2019.csv", "FuelCategory", "GenMW", ["Hydro", "Wind", "Other Renewables"])
    renewables = read_csv(SOURCE / "Data/RenewableGen.csv")
    wind, other = np.zeros_like(gross), np.zeros_like(gross)
    for j, field, output in [(1, "Pg Wind Cap", wind), (2, "Pg Other Cap", other)]:
        capacity = np.asarray([float(r[field] or 0) for r in renewables])
        require(capacity.sum() > 0, "Renewable allocation denominator is empty")
        for k, record in enumerate(renewables):
            zone = data["meta"][int(record["bus_id"])]["zone"]
            require(zone in ZONES, "Renewable outside a NY zone")
            output[:, ZONES.index(zone)] += fuel[:, j] * capacity[k] / capacity.sum()
    pg, pd, net = data["result_pg"], data["pd"], data["net"]
    result = {"gross_load": gross, "wind_negative_load": wind, "other_negative_load": other}
    for label in ["thermal", "nuclear", "hydro", "modeled_import_generator", "net_demand", "gs_demand", "native_generation", "dc_net_import", "net_injection"]:
        result[label] = np.zeros_like(gross)
    for z, zone in enumerate(ZONES):
        busmask, genmask = data["bus_zones"] == zone, data["gen_zones"] == zone
        for label, types in [("thermal", THERMAL_TYPES), ("nuclear", {"Nuclear"}), ("hydro", {"Hydro"}), ("modeled_import_generator", {"Import"})]:
            selected = genmask & np.isin(data["genfuel"], list(types)) & (net["gen"][:, 7] > 0)
            result[label][:, z] = pg[:, selected].sum(axis=1)
        result["net_demand"][:, z] = pd[:, busmask].sum(axis=1)
        result["gs_demand"][:, z] = net["bus"][busmask, 4].sum()
        result["native_generation"][:, z] = sum(result[label][:, z] for label in ["thermal", "nuclear", "hydro"])
        result["dc_net_import"][:, z] = data["dc_pf"] @ net["D"][:, busmask].sum(axis=1)
        result["net_injection"][:, z] = (result["native_generation"][:, z] + result["modeled_import_generator"][:, z]
            + result["dc_net_import"][:, z] - result["net_demand"][:, z] - result["gs_demand"][:, z])
    demand_error = result["net_demand"] - (gross - wind - other)
    require(maxabs(demand_error) < 1e-6, "Reduced NY demand differs from independently reconstructed source load/renewables")
    result["checks"] = {"reconstructed_all_NY_zonal_net_demand_max_error_mw": maxabs(demand_error)}
    # Daily Ginna data can independently verify the western nuclear component.
    daily = {datetime.strptime(r["TimeStamp"], "%m/%d/%Y").date(): float(r["GinnaGen"])
             for r in read_csv(SOURCE / "Data/nuclearGenDaily_2019.csv")}
    expected_ginna = np.asarray([daily[t.date()] for t in data["times"]])
    result["checks"]["Ginna_daily_source_max_error_mw"] = maxabs(expected_ginna - result["nuclear"][:, 1])
    require(result["checks"]["Ginna_daily_source_max_error_mw"] < 1e-7, "Ginna differs from its daily source")
    result["statewide_hydro"] = fuel[:, 0]
    schedules = ["SCH - OH - NY", "SCH - PJ - NY", "SCH - NE - NY", "SCH - HQ - NY", "SCH - HQ_CEDARS",
                 "SCH - PJM_HTP", "SCH - PJM_NEPTUNE", "SCH - PJM_VFT", "SCH - NPX_1385", "SCH - NPX_CSC"]
    result["external_schedules"] = source_hourly("interflowHourly_2019.csv", "InterfaceName", "FlowMWH", schedules)
    result["schedule_names"] = schedules
    return result


def topology(data: dict, comp: dict) -> tuple[dict, list[dict]]:
    net, meta, zones = data["net"], data["meta"], data["bus_zones"]
    branch, op, flow = net["branch"], data["operator"], data["branch_pf"]
    signed = lambda mask: net["incidence"] @ np.asarray(mask, float)
    cut_a, cut_b = signed(zones == "A"), signed(zones == "B")
    fzone = np.asarray([meta[int(v)]["zone"] for v in branch[:, 0]])
    tzone = np.asarray([meta[int(v)]["zone"] for v in branch[:, 1]])
    semantic_dys = ((fzone == "A") & (tzone == "B")).astype(float) - ((fzone == "B") & (tzone == "A"))
    semantic_wc = ((fzone == "B") & (tzone == "C")).astype(float) - ((fzone == "C") & (tzone == "B"))
    require(np.array_equal(op[0], semantic_dys) and np.array_equal(op[1], semantic_wc), "Corrected operators do not match exact A-B and B-C boundaries")
    require(np.array_equal(cut_b, op[1] - op[0]), "Zone B has an additional unaccounted boundary")
    require(not np.any(((fzone == "A") & (tzone == "C")) | ((fzone == "C") & (tzone == "A"))), "An A-C bypass must be explicitly accounted")
    require(maxabs(comp["dc_net_import"][:, :2]) == 0, "A/B has an unaccounted DC link")
    external_a = cut_a - op[0]
    require(set(np.flatnonzero(external_a) + 1) == {39, 40}, "Zone A external boundary changed")
    ia = -(flow @ external_a)
    # Ontario's only three NY ties: two to A and one to D.
    ontario_mask = np.asarray([int(meta[int(v)]["area"]) == 4 for v in net["bus"][:, 0]])
    ontario_cut = signed(ontario_mask)
    ontario_import = flow @ ontario_cut
    id_coeff = ontario_cut + external_a
    require(len(np.flatnonzero(id_coeff)) == 1, "Ontario has more than one remaining northern NY tie")
    id_value = flow @ id_coeff
    e_d = data["sim"][:, 0] - data["obs"][:, 0]
    e_w = data["sim"][:, 1] - data["obs"][:, 1]
    b_error = comp["net_injection"][:, 1] - (data["obs"][:, 1] - data["obs"][:, 0])
    checks = {
        "WestCentral_minus_Dysinger_minus_B_injection_max_mw": maxabs(data["sim"][:, 1] - data["sim"][:, 0] - comp["net_injection"][:, 1]),
        "Dysinger_minus_A_injection_minus_Ontario_A_import_max_mw": maxabs(data["sim"][:, 0] - comp["net_injection"][:, 0] - ia),
        "error_difference_minus_B_balance_error_max_mw": maxabs(e_w - e_d - b_error),
        "Ontario_A_plus_D_minus_total_max_mw": maxabs(ia + id_value - ontario_import),
        "Ontario_modeled_import_minus_released_schedule_max_mw": maxabs(ontario_import - comp["external_schedules"][:, 0]),
    }
    require(max(checks[k] for k in checks if k != "Ontario_modeled_import_minus_released_schedule_max_mw") < 1e-6,
            "Topological conservation identity failed")
    rows = []
    for i, row in enumerate(branch):
        f, t = map(int, row[:2])
        rows.append({"branch_row": i + 1, "from_bus": f, "to_bus": t, "from_zone": meta[f]["zone"],
                     "to_zone": meta[t]["zone"], "from_name": meta[f]["name"], "to_name": meta[t]["name"],
                     "from_area": meta[f]["area"], "to_area": meta[t]["area"], "active": int(row[10]),
                     "x_pu": row[3], "rate_a_mva": row[5], "dysinger_coefficient": op[0, i],
                     "west_central_coefficient": op[1, i], "A_outflow_coefficient": cut_a[i],
                     "B_outflow_coefficient": cut_b[i], "Ontario_outflow_coefficient": ontario_cut[i]})
    return {"checks": checks, "ontario_a_import": ia, "ontario_d_import": id_value,
            "ontario_total_import": ontario_import, "b_error": b_error,
            "ontario_a_import_coeff": -external_a, "ontario_d_import_coeff": id_coeff,
            "no_A_to_C_bypass": True, "B_has_only_A_and_C_AC_neighbors": True}, rows


def covariance_summary(errors: np.ndarray) -> dict:
    a, b = errors[:, 0], errors[:, 1]
    common = (a + b) / 2
    differential_half = (b - a) / 2
    common_energy, differential_energy = np.sum(common ** 2), np.sum(differential_half ** 2)
    return {"error_correlation": correlation(a, b), "error_covariance_population_mw2": float(np.mean((a - a.mean()) * (b - b.mean()))),
            "same_error_sign_hours": int(np.sum(a * b > 0)), "both_overpredicted_hours": int(np.sum((a > 0) & (b > 0))),
            "both_underpredicted_hours": int(np.sum((a < 0) & (b < 0))),
            "common_error_bias_mw": float(common.mean()), "common_error_rmse_mw": float(np.sqrt(np.mean(common ** 2))),
            "differential_half_error_rmse_mw": float(np.sqrt(np.mean(differential_half ** 2))),
            "common_fraction_pair_squared_error": float(common_energy / (common_energy + differential_energy)),
            "common_fraction_centered_pair_variance": float(np.var(common) / (np.var(common) + np.var(differential_half))),
            "B_balance_error_bias_mw": float(np.mean(b - a)), "B_balance_error_mae_mw": float(np.mean(np.abs(b - a))),
            "B_balance_error_rmse_mw": float(np.sqrt(np.mean((b - a) ** 2))),
            "pair_MAE_lower_bound_if_B_injection_fixed_mw": float(np.mean(np.abs(b - a)) / 2),
            "pair_RMSE_lower_bound_if_B_injection_fixed_mw": float(np.sqrt(np.mean((b - a) ** 2)) / 2),
            "bound_scope": "algebraic_best_possible_common_flow_shift_not_necessarily_network_feasible"}


def diagnostic_sensitivities(data: dict, topo: dict) -> list[dict]:
    """Exact DC derivatives; these are not proposed feasible generation schedules."""
    net = data["net"]
    lookup = {int(v): i for i, v in enumerate(net["bus"][:, 0])}
    records = []
    for bus, name in [(55, "Niagara_bus_A"), (53, "Ginna_and_hydro_bus_B"), (62, "B_thermal_and_load_bus"), (48, "northern_NY_HQ_StLawrence_bus_D")]:
        # A -1 MW demand perturbation represents +1 MW net bus injection; the
        # reference generator supplies the exactly balancing adjustment.
        pd = data["pd"][:1].copy()
        pd[0, lookup[bus]] -= 1
        trial = predict(net, pd, data["input_pg"][:1], data["dc_pf"][:1])
        delta = trial["flow"][0] - data["branch_pf"][0]
        response = data["operator"] @ delta
        expected_difference = 1.0 if data["meta"][bus]["zone"] == "B" else 0.0
        require(abs(response[1] - response[0] - expected_difference) < 1e-7, "DC derivative violates B balance")
        records.append({"experiment": "linear_net_injection_derivative", "injection_bus": bus, "label": name,
                        "injection_mw": 1, "balancing_bus": 74, "Dysinger_response_mw_per_mw": response[0],
                        "WestCentral_response_mw_per_mw": response[1],
                        "WestCentral_minus_Dysinger_response_mw_per_mw": response[1] - response[0],
                        "Ontario_A_import_response_mw_per_mw": float(topo["ontario_a_import_coeff"] @ delta),
                        "feasible_dispatch_or_physical_uncertainty_bound": False})
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    data = load_inputs()
    comp = components(data)
    topo, topology_rows = topology(data, comp)
    sim, obs, months, times = data["sim"][:, :2], data["obs"][:, :2], data["months"], data["times"]
    errors = sim - obs
    cov = covariance_summary(errors)
    all_metrics = [{"population": "all_8760_prepared_hours", "interface": INTERFACES[j], **metrics(sim[:, j], obs[:, j])} for j in range(2)]
    monthly, zone_monthly, bucket_rows, lag_rows = [], [], [], []
    monthly_modes, denominator_filtered, external_monthly = [], [], []
    for month in range(1, 13):
        take = months == month
        monthly_modes.append({"month": month, "hours": int(take.sum()), **covariance_summary(errors[take])})
        for j in range(2):
            monthly.append({"month": month, "interface": INTERFACES[j], **metrics(sim[take, j], obs[take, j])})
        for z, zone in enumerate(ZONES):
            zone_monthly.append({"month": month, "zone": zone, "hours": int(take.sum()),
                **{name + "_mean_mw": float(array[take, z].mean()) for name, array in comp.items()
                   if isinstance(array, np.ndarray) and array.shape == (8760, 11)}})
        for j, name in enumerate(comp["schedule_names"]):
            value = comp["external_schedules"][take, j]
            external_monthly.append({"month": month, "source_channel": name, "hours": int(take.sum()),
                "mean_schedule_mw": float(value.mean()), "minimum_schedule_mw": float(value.min()),
                "maximum_schedule_mw": float(value.max()), "hourly_sum_schedule_mwh": float(value.sum()),
                "actual_physical_tie_flow_observed": False})
    for j in range(2):
        denom, absolute = np.abs(obs[:, j]), np.abs(errors[:, j])
        for threshold in [0, 100, 250, 500]:
            take = denom >= threshold
            denominator_filtered.append({"interface": INTERFACES[j], "minimum_absolute_observed_flow_mw": threshold,
                "exclusions_use_observed_denominator_only": True, **metrics(sim[take, j], obs[take, j])})
        ape = np.divide(absolute, denom, out=np.zeros_like(absolute), where=denom > 1e-12)
        bins = [(0, 100), (100, 250), (250, 500), (500, 1000), (1000, float("inf"))]
        for lo, hi in bins:
            take = (denom >= lo) & (denom < hi)
            bucket_rows.append({"interface": INTERFACES[j], "observed_absolute_flow_bin_mw": f"[{lo},{hi})",
                "hours": int(take.sum()), "share_hours_pct": float(100 * take.mean()),
                "share_total_absolute_error_pct": float(100 * absolute[take].sum() / absolute.sum()),
                "share_total_APE_sum_pct": float(100 * ape[take].sum() / ape.sum()),
                "mae_mw": float(absolute[take].mean()) if take.any() else None,
                "mean_absolute_observed_mw": float(denom[take].mean()) if take.any() else None,
                "mape_pct": float(100 * ape[take].mean()) if take.any() else None,
                "opposite_direction_hours": int(np.sum(sim[take, j] * obs[take, j] < 0))})
    overlap = np.arange(2, 8758)
    for lag in range(-2, 3):
        for j in range(2):
            lag_rows.append({"interface": INTERFACES[j], "observed_label_shift_hours": lag,
                "comparison": "simulation_at_t_vs_observation_at_t_plus_shift", "exploratory_not_a_timestamp_correction": True,
                **metrics(sim[overlap, j], obs[overlap + lag, j])})

    # These are target-inferred aggregate quantities, not independent generation.
    oracle_b = obs[:, 1] - obs[:, 0]
    required_delta_b = oracle_b - comp["net_injection"][:, 1]
    oracle_ontario_a = obs[:, 0] - comp["net_injection"][:, 0]
    oracle_ontario_d = topo["ontario_total_import"] - oracle_ontario_a
    implied_b_native = (oracle_b + comp["net_demand"][:, 1] + comp["gs_demand"][:, 1]
                        - comp["modeled_import_generator"][:, 1] - comp["dc_net_import"][:, 1])
    hourly = []
    for h, t in enumerate(times):
        row = {"hour_index": h + 1, "prepared_local_hour": t.isoformat(),
               "dysinger_sim_mw": sim[h, 0], "dysinger_observed_mw": obs[h, 0], "dysinger_error_mw": errors[h, 0],
               "west_central_sim_mw": sim[h, 1], "west_central_observed_mw": obs[h, 1], "west_central_error_mw": errors[h, 1],
               "common_error_mw": errors[h].mean(), "B_balance_error_mw": topo["b_error"][h],
               "Ontario_to_A_modeled_mw": topo["ontario_a_import"][h], "Ontario_to_D_modeled_mw": topo["ontario_d_import"][h],
               "Ontario_total_modeled_mw": topo["ontario_total_import"][h], "Ontario_released_schedule_mw": comp["external_schedules"][h, 0],
               "oracle_B_net_injection_from_observed_difference_mw": oracle_b[h],
               "oracle_B_injection_adjustment_needed_mw": required_delta_b[h],
               "oracle_B_native_generation_needed_mw": implied_b_native[h],
               "oracle_Ontario_to_A_if_A_injection_held_mw": oracle_ontario_a[h],
               "oracle_Ontario_to_D_if_total_import_held_mw": oracle_ontario_d[h]}
        for z in [0, 1, 2, 3]:
            for name in ["thermal", "nuclear", "hydro", "gross_load", "wind_negative_load", "other_negative_load", "net_injection"]:
                row[ZONES[z] + "_" + name + "_mw"] = comp[name][h, z]
        hourly.append(row)
    feature_series = {"Ontario_to_A_modeled": topo["ontario_a_import"], "Ontario_to_D_modeled": topo["ontario_d_import"],
                      "Ontario_schedule": comp["external_schedules"][:, 0], "statewide_hydro": comp["statewide_hydro"]}
    for z in [0, 1]:
        for name in ["hydro", "nuclear", "thermal", "gross_load", "wind_negative_load", "other_negative_load", "net_injection"]:
            feature_series[f"{ZONES[z]}_{name}"] = comp[name][:, z]
    associations = []
    for feature, x in feature_series.items():
        xwithin = x.copy()
        for month in range(1, 13):
            xwithin[months == month] -= x[months == month].mean()
        for label, y in [("Dysinger_error", errors[:, 0]), ("WestCentral_error", errors[:, 1]),
                         ("common_error", errors.mean(axis=1)), ("B_balance_error", topo["b_error"])]:
            ywithin = y.copy()
            for month in range(1, 13):
                ywithin[months == month] -= y[months == month].mean()
            associations.append({"feature": feature, "error_component": label,
                "pearson_correlation": correlation(x, y), "within_calendar_month_correlation": correlation(xwithin, ywithin),
                "causal_attribution_established": False})
    generator_rows = []
    for i, gen in enumerate(data["net"]["gen"]):
        values = data["result_pg"][:, i]
        generator_rows.append({"generator_row": i + 1, "bus_id": int(gen[0]), "bus_name": data["meta"][int(gen[0])]["name"],
            "zone": data["gen_zones"][i], "source_generator_category": data["genfuel"][i],
            "mean_pg_mw": float(values.mean()), "minimum_pg_mw": float(values.min()), "maximum_pg_mw": float(values.max()),
            "zero_output_hours": int(np.sum(np.abs(values) < 1e-8)), "first_hour_pmax_mw": gen[8],
            "pmax_scope": "first_hour_case_field_not_an_independent_historical_capability_record"})

    # The lower bound is a conservation result; no optimization is used.
    sensitivities = diagnostic_sensitivities(data, topo)
    max_errors = sorted(range(8760), key=lambda h: abs(errors[h, 0]) + abs(errors[h, 1]), reverse=True)[:30]
    summary = {"baseline": "pinned_released_57_bus_corrected_if_map", "hours": 8760,
        "interfaces": all_metrics, "replay_checks": data["replay_checks"], "component_checks": comp["checks"],
        "topology_checks": topo["checks"], "no_A_to_C_bypass": True, "B_has_no_external_or_DC_boundary": True,
        "exact_modeled_identities": ["WestCentral - DysingerEast = B native generation - B net demand - B GS",
                                    "DysingerEast = A native generation - A net demand - A GS + Ontario_to_A_import",
                                    "Ontario_to_A_import + Ontario_to_D_import = total modeled Ontario import"],
        "invariant_under_reactance_changes": "WestCentral-DysingerEast is fixed when net injection in B is fixed; common flow may change through Ontario import landing redistribution",
        "covariance_and_modes": cov,
        "percentage_disparity": {"WestCentral_to_Dysinger_MAE_ratio": all_metrics[1]["mae_mw"] / all_metrics[0]["mae_mw"],
            "Dysinger_to_WestCentral_mean_absolute_observed_ratio": all_metrics[0]["mean_absolute_observed_mw"] / all_metrics[1]["mean_absolute_observed_mw"],
            "WestCentral_to_Dysinger_WAPE_ratio": all_metrics[1]["wape_pct"] / all_metrics[0]["wape_pct"]},
        "B_component_annual_means_mw": {name: float(comp[name][:, 1].mean()) for name in ["nuclear", "thermal", "hydro", "gross_load", "wind_negative_load", "other_negative_load", "net_injection"]},
        "A_component_annual_means_mw": {name: float(comp[name][:, 0].mean()) for name in ["nuclear", "thermal", "hydro", "gross_load", "wind_negative_load", "other_negative_load", "net_injection"]},
        "oracle_diagnostics_not_observed_injections": {"B_required_injection_change_mean_mw": float(required_delta_b.mean()),
            "B_required_injection_change_rmse_mw": float(np.sqrt(np.mean(required_delta_b ** 2))),
            "B_required_injection_change_min_mw": float(required_delta_b.min()), "B_required_injection_change_max_mw": float(required_delta_b.max()),
            "B_implied_native_generation_min_mw": float(implied_b_native.min()), "B_implied_native_generation_max_mw": float(implied_b_native.max()),
            "B_implied_negative_native_generation_hours": int(np.sum(implied_b_native < 0)),
            "Ontario_A_import_required_min_mw": float(oracle_ontario_a.min()), "Ontario_A_import_required_max_mw": float(oracle_ontario_a.max()),
            "Ontario_D_import_required_min_mw": float(oracle_ontario_d.min()), "Ontario_D_import_required_max_mw": float(oracle_ontario_d.max()),
            "qualification": "derived from observed interface targets under modeled lossless-cut identities; not telemetry, proposed dispatch, or independent validation"},
        "limitations": ["No observed complete zonal generation or actual western Ontario tie flows were supplied.",
            "Source labels are naive prepared local hours; lag experiments do not establish timestamp semantics.",
            "Conservation holds exactly for the lossless modeled cuts. Real interfaces may differ in membership and losses.",
            "Correlation with modeled components is descriptive and cannot establish which input is erroneous.",
            "No electrical parameter, source dispatch, load allocation, or baseline result was modified."],
        "inputs": data["inputs"]}
    folder = args.output_dir
    folder.mkdir(parents=True, exist_ok=True)
    files = {"western_interface_metrics.csv": all_metrics, "western_monthly_metrics.csv": monthly,
             "western_monthly_modes.csv": monthly_modes, "western_denominator_filtered_metrics.csv": denominator_filtered,
             "western_external_schedule_monthly.csv": external_monthly,
             "western_denominator_buckets.csv": bucket_rows, "western_lag_diagnostics.csv": lag_rows,
             "western_zone_monthly_components.csv": zone_monthly, "western_hourly.csv": hourly,
             "western_topology_edges.csv": topology_rows, "western_error_associations.csv": associations,
             "western_generator_inventory.csv": generator_rows, "western_linear_sensitivities.csv": sensitivities,
             "western_largest_error_hours.csv": [hourly[h] for h in max_errors]}
    for filename, records in files.items():
        write_csv(folder / filename, records)
    (folder / "western_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    receipts = data["inputs"] + [{"path": Path(__file__).relative_to(ROOT).as_posix(), "sha256": sha_file(Path(__file__)), "role": "diagnostic_code"},
                                {"path": "scripts/nygrid_2019/replay_dc.py", "sha256": sha_file(ROOT / "scripts/nygrid_2019/replay_dc.py"), "role": "independent_solver"}]
    for filename in [*files, "western_summary.json"]:
        path = folder / filename
        receipts.append({"path": str(path.resolve().relative_to(ROOT)), "sha256": sha_file(path), "role": "diagnostic_output"})
    write_csv(folder / "western_manifest.csv", receipts)
    print(json.dumps({"interfaces": all_metrics, "conservation": topo["checks"], "covariance": cov}, indent=2))


if __name__ == "__main__":
    main()
