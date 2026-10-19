"""Replay source-backed generation repairs and separately qualified PAR controls.

Frozen dispatch, capacities, loads, total external exchanges, topology, and
internal observation operators remain unchanged. The native generator bus
correction has no effect on the original global box/equality dispatch optimum.
Internal interface observations are read only by the separate scoring step.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_moses_audit"
BASE = ROOT / "output/nygrid_2025_dispatch/dispatch"
SLIM = ROOT / "output/nygrid_2025_slim"
sys.path.insert(0, str(ROOT / "scripts/nygrid_2025_slim"))
from replay_slim import NAMES, state_schedule
from dc_control import controlled_predict, network, predict


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def corrected_register():
    original = pd.read_csv(BASE / "model_generator_register.csv", keep_default_na=False)
    fleet = pd.read_csv(OUT / "corrected/fleet/fleet_register.csv", keep_default_na=False).set_index("fleet_id")
    out = original.copy()
    native = out.role.eq("native")
    require(fleet.index.is_unique, "Corrected fleet IDs are duplicated")
    for index in np.flatnonzero(native):
        row = fleet.loc[int(out.loc[index, "fleet_id"])]
        out.loc[index, "bus_id"] = int(row.bus_id)
        out.loc[index, "zone"] = row.zone
        out.loc[index, "mapping_method"] = row.mapping_method
    changed = original.bus_id.to_numpy(int) != out.bus_id.to_numpy(int)
    require(changed.any() and np.all(native.to_numpy()[changed]), "No native correction or an external generator was moved")
    require(np.all(original.zone.to_numpy()[changed] == "D") and np.all(out.zone.to_numpy()[changed] == "E"),
            "Correction includes a move outside the confirmed D-to-E plant scope")
    require(np.isin(out.bus_id.to_numpy(int)[native], np.arange(37, 83)).all(), "Corrected native bus is not retained")
    return original, out, changed


def control_inputs(times):
    path = OUT / "exchanges/par_stlawrence_hourly_2025.csv"
    par = pd.read_csv(path)
    require(pd.DatetimeIndex(pd.to_datetime(par.timestamp_utc, utc=True)).equals(
        pd.DatetimeIndex(pd.to_datetime(times, utc=True))), "PAR source axis differs from the dispatch axis")
    target = par["combined_raw_mw"].to_numpy(float)
    qualified = par.coverage_qualified.astype(str).str.lower().eq("true").to_numpy()
    require(np.isfinite(target[qualified]).all(), "Qualified PAR target is nonfinite")
    return path, target, qualified


def replay():
    folder = OUT / "replay"; folder.mkdir(parents=True, exist_ok=True)
    data = loadmat(BASE / "dispatch.mat", simplify_cells=True)
    n = loadmat(SLIM / "network/network_cases.mat", simplify_cells=True)
    original, register, changed = corrected_register()
    register.to_csv(OUT / "corrected/model_generator_register.csv", index=False)
    q = np.asarray(data["dispatch_qualified"], bool)
    times = np.asarray(data["timestamp_utc"]).astype(str)
    gamma = float(data["gamma"])
    control_path, raw, cq = control_inputs(times)
    q_control = q & cq
    pg, dc = np.asarray(data["gen_pg"]), np.asarray(data["dc_pf"])
    loads = np.pad(data["bus_pd"], ((0, 0), (0, 8)))
    bounds = loadmat(BASE / "dispatch_bounds.mat", simplify_cells=True)
    require(np.array_equal(register.gen_row, original.gen_row), "Generator rows changed")
    plans = [
        ("baseline_replayed", False, None),
        ("hydro_zone_corrected", True, None),
        ("hydro_zone_par_from_moses", True, 1.),
        ("hydro_zone_par_toward_moses", True, -1.),
    ]
    records = []
    for topology, dated in [("dated", True), ("year_end", False)]:
        states = state_schedule(times, dated)
        frozen = loadmat(SLIM / "replay" / ("topology_" + topology + ".mat"), simplify_cells=True)
        for name, corrected, sign in plans:
            qualified = q if sign is None else q_control
            nl = len(n[states[0]]["branch"])
            flows = np.full((8760, nl), np.nan)
            angles = np.full((8760, 148), np.nan)
            interfaces = np.full((8760, 7), np.nan)
            shift = np.full(8760, np.nan)
            residual = np.full(8760, np.nan)
            control_error = np.full(8760, np.nan)
            slack = np.full(8760, np.nan)
            for key in sorted(set(states)):
                ix = np.flatnonzero(qualified & (states == key))
                if not len(ix):
                    continue
                case = copy.deepcopy(n[key])
                require(np.array_equal(case["branch"][210, :2], [48, 100]), "Controlled branch identity changed")
                require(np.array_equal(case["gen"][:, 0].astype(int), original.bus_id.to_numpy(int)),
                        "Frozen topology generator order or terminals changed")
                if corrected:
                    case["gen"][:, 0] = register.bus_id.to_numpy(int)
                if sign is None:
                    result = predict(network(case), loads[ix], pg[ix], dc[ix])
                    shift[ix] = case["branch"][210, 9]
                else:
                    result = controlled_predict(case, loads[ix], pg[ix], dc[ix], 211, raw[ix] * gamma * sign)
                    shift[ix] = result["equivalent_shift_deg"]
                    control_error[ix] = result["control_error_mw"]
                a = result["angle_deg"]
                a -= a[np.arange(len(ix)), np.asarray(data["reference_bus"], int)[ix] - 1][:, None]
                rec = n["recovery"][key.removesuffix("_case")]
                # The controlled branch is retained-original and is absent from
                # every scored interface. Eliminated components see no new
                # internal phase or injection, so their recovery is unchanged.
                interface = np.deg2rad(a) @ np.asarray(rec["interface_angle_matrix"]).T + rec["interface_flow_offset"]
                flows[ix], angles[ix], interfaces[ix] = result["flow"], a, interface
                residual[ix] = result["nodal_residual_mw"]
                slack[ix] = np.max(np.abs(result["result_pg"] - pg[ix]), axis=1)
            require(np.nanmax(residual) < 1e-7 and np.nanmax(slack) < 1e-7, "Replay failed injection preservation")
            if not corrected:
                require(np.max(np.abs(flows[q] - frozen["branch_pf"][q])) < 1e-7, "Fresh baseline no longer reproduces frozen flows")
                require(np.max(np.abs(interfaces[q] - frozen["interface_pf"][q])) < 1e-7, "Fresh baseline interface mismatch")
            variant = topology + "_" + name
            path = folder / (variant + ".mat")
            savemat(path, dict(hour_index=data["hour_index"], timestamp_utc=times.astype(object),
                qualified=qualified, network_state_ids=states, branch_pf=flows, bus_va=angles,
                interface_pf=interfaces, equivalent_shift_deg=shift, nodal_residual_mw=residual,
                slack_change_mw=slack, control_error_mw=control_error, gamma=gamma,
                corrected_generator_buses=register.bus_id.to_numpy(int) if corrected else original.bus_id.to_numpy(int),
                source_control_branch_row=211, raw_PAR_to_branch_sign=np.nan if sign is None else sign),
                do_compression=True, oned_as="column")
            record = dict(variant=variant, topology=topology, source_generation_mapping_corrected=corrected,
                par_controlled=sign is not None, raw_PAR_to_branch_sign=sign,
                par_orientation_is_promoted=False, qualified_hours=int(qualified.sum()),
                source_gap_hours=int((~qualified).sum()), maximum_nodal_residual_model_mw=float(np.nanmax(residual)),
                maximum_slack_change_model_mw=float(np.nanmax(slack)),
                equivalent_shift_min_deg=float(np.nanmin(shift)), equivalent_shift_max_deg=float(np.nanmax(shift)),
                file=path.relative_to(ROOT).as_posix(), sha256=sha(path))
            records.append(record); print(json.dumps(record), flush=True)
    sources = [BASE / "dispatch.mat", BASE / "dispatch_bounds.mat", BASE / "dispatch_priors.mat",
               BASE / "model_generator_register.csv", OUT / "corrected/fleet/fleet_register.csv",
               OUT / "corrected/fleet/repair_receipt.json", SLIM / "network/network_cases.mat", control_path,
               Path(__file__), Path(__file__).with_name("dc_control.py"),
               ROOT / "scripts/nygrid_2019/replay_dc.py"]
    receipt = dict(passed=True, status="source_generation_repair_plus_two_unpromoted_PAR_orientations",
        original_qualified_hours=int(q.sum()), par_qualified_hours=int(cq.sum()),
        common_qualified_hours=int(q_control.sum()), moved_admitted_generator_rows=int(changed.sum()),
        original_PG_PD_QD_bounds_DC_schedules_and_topology_preserved=True,
        original_unit_dispatch_remains_optimal=True,
        optimum_identity_reason="objective, generator boxes and global balance target are independent of generator bus IDs",
        internal_interface_observations_read=False, PAR_orientation_selection_uses_internal_observations=False,
        equivalent_phase_shift_is_physical_tap_telemetry=False,
        variants=records, dependencies=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in sources])
    (folder / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def score():
    folder = OUT / "comparison"; folder.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((OUT / "replay/provenance.json").read_text())
    base = loadmat(BASE / "dispatch.mat", simplify_cells=True, variable_names=["dispatch_qualified", "timestamp_utc", "gamma"])
    gamma = float(base["gamma"])
    obs_path = ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv"
    obs = pd.read_csv(obs_path)
    require(np.array_equal(obs.timestamp_utc.astype(str), np.asarray(base["timestamp_utc"]).astype(str)), "Observation axis differs")
    y = obs[NAMES].to_numpy(float)
    _, _, cq = control_inputs(base["timestamp_utc"])
    common = cq & np.asarray(base["dispatch_qualified"], bool)
    rows, monthly = [], []
    for item in receipt["variants"]:
        require(sha(ROOT / item["file"]) == item["sha256"], "Replay changed before scoring")
        data = loadmat(ROOT / item["file"], simplify_cells=True, variable_names=["interface_pf", "qualified"])
        for cohort, mask in [("own_qualified", np.asarray(data["qualified"], bool)), ("common_PAR_qualified", common)]:
            require(np.isfinite(data["interface_pf"][mask]).all() and np.isfinite(y[mask]).all(), "Missing comparison data")
            for j, name in enumerate(NAMES):
                error = data["interface_pf"][:, j] / gamma - y[:, j]
                for month in [0] + list(range(1, 13)):
                    month_mask = pd.to_datetime(obs.timestamp_utc, utc=True).dt.tz_convert("America/New_York").dt.month.to_numpy() == month
                    q = mask if month == 0 else mask & month_mask
                    e = error[q]
                    row = dict(variant=item["variant"], cohort=cohort, month=month, interface=name, hours=int(q.sum()),
                        mae_public_equivalent_mw=float(np.mean(abs(e))), rmse_public_equivalent_mw=float(np.sqrt(np.mean(e ** 2))),
                        bias_public_equivalent_mw=float(np.mean(e)), wape_percent=float(100 * abs(e).sum() / abs(y[q, j]).sum()),
                        mean_absolute_observed_public_mw=float(np.mean(abs(y[q, j]))), observations_used_to_fit_model=False)
                    (rows if month == 0 else monthly).append(row)
    pd.DataFrame(rows).to_csv(folder / "interface_summary.csv", index=False)
    pd.DataFrame(monthly).to_csv(folder / "interface_monthly.csv", index=False)
    (folder / "scoring_receipt.json").write_text(json.dumps(dict(passed=True, observations_used_only_posthoc=True,
        common_qualified_hours=int(common.sum()), observation_source_sha256=sha(obs_path),
        replay_provenance_sha256=sha(OUT / "replay/provenance.json"), code_sha256=sha(Path(__file__))), indent=2) + "\n", encoding="utf-8")
    print(pd.DataFrame(rows).query("interface == 'MOSES SOUTH' and cohort == 'common_PAR_qualified'").to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score-only", action="store_true")
    args = parser.parse_args()
    if not args.score_only:
        replay()
    score()
