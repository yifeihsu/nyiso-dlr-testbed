"""Reproduce the Moses South regional balance without fitting observations.

The 2019 PD is net of some renewables; 2025 PD is gross and all renewables are
generator rows. Comparisons of individual components preserve that distinction.
All exported power values are on the public-MW scale.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_moses_audit/balance"
INPUTS = [
    "output/nygrid_2019_full_stage1/full_year.mat",
    "output/nygrid_2025_dispatch/dispatch/dispatch.mat",
    "output/nygrid_2025_dispatch/dispatch/dispatch_network.mat",
    "output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat",
    "output/nygrid_2025_dispatch/dispatch/model_generator_register.csv",
    "output/nygrid_2025_inputs/load_source/interface_wide.csv",
    "output/nygrid_2025_slim/replay/topology_dated.mat",
]


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def metric(pred, obs):
    error = pred - obs
    return dict(hours=len(obs), mae_public_mw=float(np.mean(np.abs(error))),
                rmse_public_mw=float(np.sqrt(np.mean(error ** 2))),
                bias_public_mw=float(np.mean(error)),
                mean_absolute_observed_public_mw=float(np.mean(np.abs(obs))),
                wape_percent=float(100 * np.sum(np.abs(error)) / np.sum(np.abs(obs))))


def build():
    before = {p: sha(ROOT / p) for p in INPUTS}
    OUT.mkdir(parents=True, exist_ok=True)
    old = loadmat(ROOT / INPUTS[0], simplify_cells=True)
    new = loadmat(ROOT / INPUTS[1], simplify_cells=True)
    solved = loadmat(ROOT / INPUTS[2], simplify_cells=True)
    priors = loadmat(ROOT / INPUTS[3], simplify_cells=True)
    register = pd.read_csv(ROOT / INPUTS[4], keep_default_na=False)
    observations = pd.read_csv(ROOT / INPUTS[5])
    slim = loadmat(ROOT / INPUTS[6], simplify_cells=True)
    assert np.array_equal(new["timestamp_utc"], observations.timestamp_utc.astype(str))
    assert np.array_equal(new["dispatch_qualified"], slim["qualified"])
    rows, summaries, ledgers, hourly = [], [], [], []
    for year, data in [(2019, old), (2025, new)]:
        case = data["base_case"]
        bus, branch, gen = [np.asarray(case[k]) for k in ["bus", "branch", "gen"]]
        scale = float(data.get("gamma", 1.0))
        qualified = np.asarray(data.get("dispatch_qualified", np.ones(8760)), bool)
        columns = np.flatnonzero(np.isin(bus[:, 0], [48, 49]))
        native = np.isin(gen[:, 0], [48, 49])
        pg = data["result_pg"] if year == 2019 else data["gen_pg"]
        flows = old["branch_pf"] if year == 2019 else solved["branch_pf"]
        mapping = np.asarray(case["if"]["map"])
        terms = mapping[mapping[:, 0] == 4, 1].astype(int)
        assert set(terms) == {-46, -51, -52}
        prediction = sum(np.sign(k) * flows[:, abs(k) - 1] for k in terms) / scale
        observed = old["observed_interface_mw"][:, 3] if year == 2019 else observations["MOSES SOUTH"].to_numpy()
        # Discover every directed cut edge by bus identity, independently of if.map.
        f_in, t_in = np.isin(branch[:, 0], [48, 49]), np.isin(branch[:, 1], [48, 49])
        cut = np.flatnonzero(f_in != t_in)
        assert set(cut + 1) == {46, 51, 52, 211}
        assert np.array_equal(branch[210, :2], [48, 100])
        ontario = -flows[:, 210] / scale
        gross_or_net_pd = data["bus_pd"][:, columns].sum(axis=1) / scale
        total_pg = pg[:, native].sum(axis=1) / scale
        shunt = float(bus[columns, 4].sum()) / scale
        reconstructed = total_pg - gross_or_net_pd - shunt + ontario
        difference = prediction - reconstructed
        assert np.max(np.abs(difference[qualified])) < 1e-7
        frame = pd.DataFrame({
            "year": year, "hour_index": data["hour_index"],
            "timestamp": data["timestamp_iso"] if year == 2019 else data["timestamp_utc"],
            "qualified": qualified, "zone_D_total_PG_mw": total_pg,
            "zone_D_PD_mw": gross_or_net_pd, "Ontario_to_D_mw": ontario,
            "Moses_predicted_mw": prediction, "Moses_observed_mw": observed,
            "Moses_error_mw": prediction - observed,
            "cut_identity_residual_mw": difference,
        })
        fuel = np.asarray(case["genfuel"]) if year == 2019 else register.fuel_category.to_numpy()
        for name in sorted(set(fuel[native])):
            mask = native & (fuel == name)
            field = "zone_D_PG_" + str(name).replace(" ", "_") + "_mw"
            frame[field] = pg[:, mask].sum(axis=1) / scale
        for j in cut:
            ledgers.append(dict(year=year, branch_row=j + 1,
                                from_bus=int(branch[j, 0]), to_bus=int(branch[j, 1]),
                                in_Moses_operator=bool(j + 1 in np.abs(terms)),
                                coefficient=float(np.sign(next((v for v in terms if abs(v) == j + 1), 0)))))
        frame["month"] = pd.to_datetime(frame.timestamp, utc=(year == 2025)).dt.month
        # The monthly mean is on each year's own declared cohort, not paired years.
        for month in [0] + list(range(1, 13)):
            sample = frame.loc[qualified & ((frame.month == month) | (month == 0))]
            record = dict(year=year, month=month, **metric(sample.Moses_predicted_mw.to_numpy(), sample.Moses_observed_mw.to_numpy()))
            record.update({name + "_mean": float(sample[name].mean()) for name in frame.columns if name.endswith("_mw")})
            rows.append(record)
        summaries.append(dict(year=year, hours=int(qualified.sum()),
                              gamma=scale, pd_scope="net_of_some_renewables" if year == 2019 else "gross_load",
                              time_scope="released_prepared_naive_local_labels" if year == 2019 else "physical_UTC_hours",
                              maximum_cut_identity_residual_mw=float(np.max(np.abs(difference[qualified])))))
        hourly.append(frame)
    baseline = hourly[1]
    mask = np.asarray(new["dispatch_qualified"], bool)
    pd.DataFrame(rows).to_csv(OUT / "regional_balance_summary.csv", index=False)
    pd.concat(hourly, ignore_index=True).to_csv(OUT / "regional_balance_hourly.csv.gz", index=False,
                                             compression={"method": "gzip", "mtime": 0})
    pd.DataFrame(ledgers).to_csv(OUT / "zone_D_cut_members.csv", index=False)
    error = baseline.Moses_error_mw.to_numpy()[mask]
    frozen_delta = (slim["interface_pf"][:, 3] / float(new["gamma"]) - baseline.Moses_predicted_mw.to_numpy())[mask]
    topological = dict(mean_change_public_mw=float(np.mean(frozen_delta)),
                       maximum_absolute_change_public_mw=float(np.max(np.abs(frozen_delta))))
    # This correlation identifies an association, not a measured causal contribution.
    correlations = {col: float(np.corrcoef(error, baseline[col].to_numpy()[mask])[0, 1])
                    for col in ["Ontario_to_D_mw", "zone_D_PD_mw", "zone_D_total_PG_mw"]}
    final = {p: sha(ROOT / p) for p in INPUTS}
    assert before == final
    report = dict(passed=True, input_files_unchanged=True, years=summaries,
                  identity="Moses = ZoneD generation - ZoneD PD - ZoneD GS + Ontario-to-D AC inflow",
                  identity_scope="model lossless regional balance; not an observed tie-flow identity",
                  cross_year_comparison_is_causal=False,
                  original140_to_slim148=topological,
                  error_correlations_not_causal=correlations,
                  files=[dict(path=p, sha256=h) for p, h in before.items()])
    (OUT / "balance_validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    build()
