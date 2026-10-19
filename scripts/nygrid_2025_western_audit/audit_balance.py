"""Diagnose the current western residuals using exact model-zone balances.

This reads internal observations to describe residuals, not to select or fit a
correction. Corrective sources and reconstruction are handled separately.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_western_audit/balance"
PATHS = ["output/nygrid_2025_dispatch/dispatch/dispatch.mat",
         "output/nygrid_2025_moses_audit/corrected/model_generator_register.csv",
         "output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv",
         "output/nygrid_2025_inputs/load_source/interface_wide.csv",
         "output/nygrid_2025_par_controls/replay/dated_verified_PAR_flows.mat",
         "output/nygrid_2025_slim/network/network_cases.mat"]


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def metric(pred, obs):
    e = np.asarray(pred) - np.asarray(obs)
    return dict(mae_public_mw=float(np.mean(abs(e))), rmse_public_mw=float(np.sqrt(np.mean(e**2))),
                bias_public_mw=float(np.mean(e)), wape_percent=float(100 * abs(e).sum() / abs(obs).sum()))


def audit():
    before = {p: sha(ROOT / p) for p in PATHS}
    data = loadmat(ROOT / PATHS[0], simplify_cells=True)
    register = pd.read_csv(ROOT / PATHS[1], keep_default_na=False)
    metadata = pd.read_csv(ROOT / PATHS[2], keep_default_na=False).set_index("idx")
    obs = pd.read_csv(ROOT / PATHS[3])
    replay = loadmat(ROOT / PATHS[4], simplify_cells=True)
    model = loadmat(ROOT / PATHS[5], simplify_cells=True)
    q = np.asarray(replay["qualified"], bool)
    gamma = float(data["gamma"])
    assert np.array_equal(data["timestamp_utc"], obs.timestamp_utc.astype(str))
    assert np.array_equal(data["timestamp_utc"], replay["timestamp_utc"])
    f = np.asarray(replay["interface_pf"]) / gamma
    branch = model["refined_2025_case"]["branch"]
    flow = np.asarray(replay["branch_pf"]) / gamma
    frame = pd.DataFrame(dict(hour_index=data["hour_index"], timestamp_utc=data["timestamp_utc"], qualified=q))
    cuts = []
    for zone in ["A", "B"]:
        ids = metadata.index[metadata.zone.eq(zone)].to_numpy(int)
        native_cols = register.role.eq("native").to_numpy() & np.isin(register.bus_id.to_numpy(int), ids)
        generation = data["gen_pg"][:, native_cols].sum(axis=1) / gamma
        load = data["bus_pd"][:, ids - 1].sum(axis=1) / gamma
        frame[f"zone_{zone}_generation_mw"] = generation
        frame[f"zone_{zone}_load_mw"] = load
        frame[f"zone_{zone}_net_mw"] = generation - load
        fi, ti = np.isin(branch[:, 0], ids), np.isin(branch[:, 1], ids)
        for j in np.flatnonzero((fi != ti) & (branch[:, 10] == 1)):
            cuts.append(dict(zone=zone, branch_row=j + 1, from_bus=int(branch[j, 0]),
                             to_bus=int(branch[j, 1]), export_sign=1 if fi[j] else -1))
    # Ontario's total is still prescribed by the old NYISO schedule. With the
    # measured northern PAR pair fixed, west import is the remaining transfer.
    ontario_to_A = obs["SCH - OH - NY"].to_numpy() - replay["par_transfer_model_mw"].sum(axis=1) / gamma
    frame["Ontario_to_A_model_mw"] = ontario_to_A
    frame["Dysinger_pred_mw"], frame["West_Central_pred_mw"] = f[:, 0], f[:, 1]
    frame["Dysinger_obs_mw"] = obs["DYSINGER EAST"]
    frame["West_Central_obs_mw"] = obs["WEST CENTRAL"]
    frame["Dysinger_error_mw"] = frame.Dysinger_pred_mw - frame.Dysinger_obs_mw
    frame["West_Central_error_mw"] = frame.West_Central_pred_mw - frame.West_Central_obs_mw
    frame["common_error_mw"] = (frame.Dysinger_error_mw + frame.West_Central_error_mw) / 2
    frame["difference_error_mw"] = frame.West_Central_error_mw - frame.Dysinger_error_mw
    a_error = f[:, 0] - (frame.zone_A_net_mw + ontario_to_A)
    b_error = f[:, 1] - f[:, 0] - frame.zone_B_net_mw
    assert np.max(abs(a_error[q])) < 1e-7 and np.max(abs(b_error[q])) < 1e-7
    rows = []
    months = pd.to_datetime(frame.timestamp_utc, utc=True).dt.tz_convert("America/New_York").dt.month
    for month in [0] + list(range(1, 13)):
        mask = q if month == 0 else q & months.eq(month)
        sample = frame.loc[mask]
        ed, ew = sample.Dysinger_error_mw.to_numpy(), sample.West_Central_error_mw.to_numpy()
        rows.append(dict(month=month, hours=len(sample), error_correlation=float(np.corrcoef(ed, ew)[0, 1]),
                         common_fraction_pair_squared_error=float(np.sum(2*((ed+ew)/2)**2) / np.sum(ed**2+ew**2)),
                         difference_error_mae_mw=float(np.mean(abs(ew-ed))),
                         **{"Dysinger_" + k: v for k, v in metric(sample.Dysinger_pred_mw, sample.Dysinger_obs_mw).items()},
                         **{"West_Central_" + k: v for k, v in metric(sample.West_Central_pred_mw, sample.West_Central_obs_mw).items()}))
    OUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT / "western_hourly.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    pd.DataFrame(rows).to_csv(OUT / "western_monthly_summary.csv", index=False)
    pd.DataFrame(cuts).to_csv(OUT / "western_cut_members.csv", index=False)
    assert all(sha(ROOT / p) == h for p, h in before.items())
    result = dict(passed=True, baseline="148bus_hydro_corrected_and_verified_PAR_transfers",
                  qualified_hours=int(q.sum()), maximum_A_balance_residual_mw=float(np.max(abs(a_error[q]))),
                  maximum_B_balance_residual_mw=float(np.max(abs(b_error[q]))),
                  annual=rows[0], observations_used_only_for_diagnostics=True,
                  within_A_relocation_changes_Dysinger_or_West_Central_at_fixed_injections=False,
                  interpretation="Common residual accounting is not causal attribution or a fitted correction.",
                  dependencies=[dict(path=p, sha256=h) for p, h in before.items()])
    (OUT / "balance_validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    audit()
