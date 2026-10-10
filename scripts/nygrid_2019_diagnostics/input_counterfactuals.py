"""Paired western-flow diagnostics; no fitted or deployed model correction.

Scenarios preserve hourly net system injection. They separately test a monthly
hydro allocation consistent with the released EIA table, inherited B load
shares, conditional shared-RGGI-profile disaggregation, and restored raw
external ties. None identifies true hourly plant output or validates dispatch.
"""
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

from western_flow_diagnostics import load_inputs, metrics
from replay_dc import INTERFACES, network, operator, predict, require, sha_file

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tmp/nygrid_2019_reproduction/upstream/Data"
OUT = ROOT / "output/nygrid_2019_diagnostics"


def write_csv(name: str, records: list[dict]) -> None:
    with (OUT / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(records)


def run() -> dict:
    d = load_inputs()
    case, pg, pd0 = d["case"], d["input_pg"], d["pd"]
    case_gen = np.asarray(case["gen"])
    hydro = np.flatnonzero(d["genfuel"] == "Hydro")
    ni = np.flatnonzero((d["genfuel"] == "Hydro") & (case_gen[:, 0] == 55))
    st = np.flatnonzero((d["genfuel"] == "Hydro") & (case_gen[:, 0] == 48))
    require(len(ni) == len(st) == 1, "Major hydro identities changed")
    ni, st = int(ni[0]), int(st[0])
    small = np.setdiff1d(hydro, [ni, st])
    monthly = pd.read_csv(SOURCE / "hydroGenMonthly_2019.csv")
    monthly["month"] = pd.to_datetime(monthly.TimeStamp).dt.month
    new_hydro = pg.copy(); hydro_rows = []
    small_weights = case_gen[small, 8] / case_gen[small, 8].sum()
    for month in range(1, 13):
        mask = d["months"] == month
        target = monthly.loc[monthly.month == month].iloc[0]
        pool = pg[mask][:, hydro].sum(axis=1) - pg[mask, st]
        fraction = float(target.rmnGen / pool.sum())
        require(np.all(pool >= 0) and 0 <= fraction <= 1, "Monthly hydro pool cannot meet source target")
        new_hydro[mask, ni] = fraction * pool
        new_hydro[np.ix_(mask, small)] = ((1 - fraction) * pool)[:, None] * small_weights
        require(abs(new_hydro[mask, ni].sum() - target.rmnGen) < 1e-6, "Niagara monthly energy mismatch")
        require(np.max(np.abs(new_hydro[mask][:, hydro].sum(axis=1) - pg[mask][:, hydro].sum(axis=1))) < 1e-8,
                "Hydro counterfactual changed statewide hourly hydro")
        hydro_rows.append({"month": month, "prepared_hours": int(mask.sum()),
            "Niagara_model_nominal_mwh": float(pg[mask, ni].sum()), "Niagara_EIA_mwh": float(target.rmnGen),
            "Niagara_model_minus_EIA_mean_mw": float((pg[mask, ni].sum() - target.rmnGen) / mask.sum()),
            "StLawrence_model_nominal_mwh": float(pg[mask, st].sum()), "StLawrence_EIA_mwh": float(target.stlGen),
            "Niagara_hydro_pool_fraction": fraction})

    # Only the declared load split changes; gross B load and renewables stay fixed.
    old_meta = pd.read_csv(SOURCE / "npcc.csv", keep_default_na=False)
    new_meta = pd.read_csv(SOURCE / "npcc_new.csv", keep_default_na=False)
    b_old = old_meta.loc[old_meta.zone == "B"].set_index("idx")
    b_new = new_meta.loc[new_meta.zone == "B"].set_index("idx")
    old_weights = b_old.sumLoadP0.clip(lower=0) / b_old.sumLoadP0.clip(lower=0).sum()
    new_weights = b_new.sumLoadP0.clip(lower=0) / b_new.sumLoadP0.clip(lower=0).sum()
    loads = pd.read_csv(SOURCE / "loadHourly_2019.csv")
    loads["time"] = pd.to_datetime(loads.TimeStamp)
    b_gross = loads[loads.ZoneID == "B"].set_index("time").reindex(d["times"]).Load.to_numpy()
    require(np.isfinite(b_gross).all(), "Missing B source load")
    alternate_pd = pd0.copy()
    for bus_id in b_old.index:
        idx = np.flatnonzero(case["bus"][:, 0] == bus_id)
        require(len(idx) == 1, "B bus identity is not unique")
        alternate_pd[:, idx[0]] += b_gross * (old_weights.loc[bus_id] - new_weights.loc[bus_id])
    require(np.max(np.abs(alternate_pd.sum(axis=1) - pd0.sum(axis=1))) < 1e-8, "Load reallocation changed total demand")

    # The same source profile is currently copied into three bus60 records.
    thermal = pd.read_csv(SOURCE / "thermalGenHourly_2019.csv")
    thermal["time"] = pd.to_datetime(thermal.TimeStamp)
    names = ["Jamestown 5", "Jamestown 6", "Jamestown 7"]
    vectors = [thermal[thermal.NYISOName == name].set_index("time").reindex(d["times"]).hourlyGen.to_numpy() for name in names]
    require(all(np.array_equal(vectors[0], v) for v in vectors[1:]), "Shared source profiles are no longer identical")
    matched = [j for j in np.flatnonzero(case_gen[:, 0] == 60) if np.max(np.abs(pg[:, j] - vectors[0])) < 1e-8]
    require(len(matched) == 3 and np.allclose(sorted(case_gen[matched, 8]), [25, 28.7, 46]), "Shared-profile generator identification failed")
    repaired_pg = pg.copy()
    capacity_shares = case_gen[matched, 8] / case_gen[matched, 8].sum()
    repaired_pg[:, matched] = vectors[0][:, None] * capacity_shares
    moved = pg[:, matched].sum(axis=1) - repaired_pg[:, matched].sum(axis=1)
    jrows = np.flatnonzero((d["gen_zones"] == "J") & ~np.isin(d["genfuel"], ["Hydro", "Nuclear", "Import"]))
    jtotal = pg[:, jrows].sum(axis=1)
    require(np.all(jtotal > 0), "Source J thermal redistribution denominator is zero")
    repaired_pg[:, jrows] += moved[:, None] * pg[:, jrows] / jtotal[:, None]
    require(np.max(np.abs(repaired_pg.sum(axis=1) - pg.sum(axis=1))) < 1e-8, "Conditional profile scenario changed total generation")

    scenarios = [
        ("released_57_baseline", case, pg, pd0, d["dc_pf"], d["operator"]),
        ("monthly_EIA_hydro_pool", case, new_hydro, pd0, d["dc_pf"], d["operator"]),
        ("original_B_load_shares", case, pg, alternate_pd, d["dc_pf"], d["operator"]),
        ("conditional_shared_unit_once", case, repaired_pg, pd0, d["dc_pf"], d["operator"]),
    ]
    full_path = ROOT / "output/nygrid_2019_full_stage1/full_year.mat"
    full = loadmat(full_path, simplify_cells=True,
        variable_names=["base_case", "bus_pd", "input_pg", "dc_pf"])
    fc = full["base_case"]
    fmap = np.asarray(fc["if"]["map"])
    fop = operator([fmap[fmap[:, 0] == i, 1] for i in [1, 2, 3, 4, 5, 8, 10]], len(fc["branch"]))
    restored = copy.deepcopy(fc)
    raw = loadmat(SOURCE / "npcc.mat", simplify_cells=True)["mpc"]
    ties = []
    for f, t in [(84, 116), (87, 115), (90, 114)]:
        selected = raw["branch"][np.all(raw["branch"][:, :2] == [f, t], axis=1)]
        require(len(selected) == 1, "Restored raw tie identity is not unique")
        ties.append(selected[0])
    restored["branch"] = np.vstack([restored["branch"], ties])
    scenarios += [
        ("full_140_baseline", fc, full["input_pg"], full["bus_pd"], full["dc_pf"], fop),
        ("restored_raw_external_ties", restored, full["input_pg"], full["bus_pd"], full["dc_pf"], np.pad(fop, ((0, 0), (0, 3)))),
    ]
    rows, monthly_metrics, hourly, checks, flows = [], [], [], [], {}
    for name, c, generation, demand, dc, op in scenarios:
        net = network(c)
        solved = predict(net, demand, generation, dc)
        require(float(solved["nodal_residual_mw"].max()) < 1e-7, f"Counterfactual balance failed: {name}")
        sim = solved["flow"] @ op.T
        flows[name] = sim
        for j, interface in enumerate(INTERFACES):
            rows.append({"scenario": name, "interface": interface, **metrics(sim[:, j], d["obs"][:, j])})
            for month in range(1, 13):
                mask = d["months"] == month
                monthly_metrics.append({"scenario": name, "month": month, "interface": interface,
                    **metrics(sim[mask, j], d["obs"][mask, j])})
        for h, time in enumerate(d["times"]):
            hourly.append({"scenario": name, "timestamp": time.isoformat(),
                "Dysinger_sim_mw": sim[h, 0], "WestCentral_sim_mw": sim[h, 1],
                "Dysinger_error_mw": sim[h, 0] - d["obs"][h, 0],
                "WestCentral_error_mw": sim[h, 1] - d["obs"][h, 1]})
        checks.append({"scenario": name, "maximum_nodal_residual_mw": float(solved["nodal_residual_mw"].max()),
            "negative_generation_cells": int((generation < -1e-7).sum()),
            "no_bounded_operating_feasibility_claimed": True})
    require(np.max(np.abs(flows["released_57_baseline"] - d["sim"])) < 1e-7, "Paired baseline mismatch")
    require(np.max(np.abs((flows["original_B_load_shares"][:, 1] - flows["original_B_load_shares"][:, 0])
        - (d["sim"][:, 1] - d["sim"][:, 0]))) < 1e-7, "B load redistribution violated conservation")
    summary = {"scope": "paired diagnostic counterfactuals, not new validated operating models",
        "hours": 8760, "models_modified": False, "fitted_to_interface_targets": False,
        "Niagara_annual_model_minus_EIA_nominal_mwh": float(pg[:, ni].sum() - monthly.rmnGen.sum()),
        "Niagara_annual_model_minus_EIA_mean_mw": float((pg[:, ni].sum() - monthly.rmnGen.sum()) / 8760),
        "shared_unit_records_1based": [int(j + 1) for j in matched],
        "shared_profile_annual_nominal_mwh_each": float(vectors[0].sum()),
        "conditional_reallocated_A_to_J_mean_mw": float(moved.mean()),
        "conditional_reallocated_A_to_J_max_mw": float(moved.max()),
        "restored_external_ties": [[84, 116], [87, 115], [90, 114]],
        "checks": checks,
        "limitations": [
            "Monthly hydro inputs are from the released EIA-derived table, not newly retrieved unit telemetry; net/gross and pumped-storage scope are not independently reconciled.",
            "Hydro pool disaggregation is hypothetical and preserves the released hourly statewide hydro total and StLawrence schedule; matching monthly totals does not establish true hourly Niagara output.",
            "Nominal MWh are MW sums over the authors' prepared local labels, including DST handling.",
            "The once-counted shared RGGI unit scenario is conditional on an aggregate-unit interpretation and capacity-weighted disaggregation; exact physical unit semantics remain unresolved.",
            "Restoring raw external ties preserves all injections but changes each neighboring region's direct NY interchange; external inputs were originally scaled assuming those ties absent.",
            "No scenario enforces generator or thermal capability bounds; metric improvement does not qualify a correction.",
        ],
        "inputs": d["inputs"] + [{"path": str(p.relative_to(ROOT)), "sha256": sha_file(p), "role": "counterfactual_input_or_code"}
            for p in [full_path, SOURCE / "thermalGenHourly_2019.csv", SOURCE / "npcc.mat", Path(__file__), Path(__file__).with_name("western_flow_diagnostics.py")]],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv("hydro_monthly_balance.csv", hydro_rows)
    write_csv("counterfactual_metrics.csv", rows)
    write_csv("counterfactual_monthly_metrics.csv", monthly_metrics)
    write_csv("counterfactual_hourly.csv", hourly)
    (OUT / "counterfactual_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    for row in rows:
        if row["interface"] in INTERFACES[:2]:
            print(row["scenario"], row["interface"], "MAE", round(row["mae_mw"], 3), "WAPE", round(row["wape_pct"], 3))
    return summary


if __name__ == "__main__":
    run()
