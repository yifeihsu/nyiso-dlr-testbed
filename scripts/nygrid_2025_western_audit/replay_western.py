"""Paired western source corrections on the fixed 148-bus PAR-controlled model.

Separate mapping-only, Ontario-only and all-boundary runs isolate the changes. No
internal interface target enters construction or generation reconstruction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_western_audit"
BASE = ROOT / "output/nygrid_2025_dispatch/dispatch"
PAR = ROOT / "output/nygrid_2025_par_controls"
SLIM = ROOT / "output/nygrid_2025_slim"
sys.path.insert(0, str(ROOT / "scripts/nygrid_2025_par_controls"))
from controlled_equivalent import make_controlled_case
from replay_controls import verify_control_sources
sys.path.insert(0, str(ROOT / "scripts/nygrid_2025_slim"))
from replay_slim import state_schedule, NAMES
sys.path.insert(0, str(ROOT / "scripts/nygrid_2019"))
from replay_dc import network, predict
from reconstruct_dispatch import check_records, require, sha, source_inputs


def replay():
    folder = OUT / "replay"; folder.mkdir(parents=True, exist_ok=True)
    dispatch_receipt = json.loads((OUT / "dispatch/dispatch_receipt.json").read_text())
    require(dispatch_receipt["passed"] and not dispatch_receipt["internal_interface_observations_used"], "Unqualified dispatch reconstruction")
    check_records(dispatch_receipt["dependencies"])
    updated_path = OUT / "dispatch/actual_Ontario_dispatch.mat"
    require(sha(updated_path) == dispatch_receipt["dispatch_file_sha256"], "Updated dispatch changed")
    all_receipt = json.loads((OUT / "dispatch/all_boundary_dispatch_receipt.json").read_text())
    require(all_receipt["passed"] and not all_receipt["internal_interface_observations_used"], "Unqualified all-boundary reconstruction")
    check_records(all_receipt["dependencies"])
    all_path = OUT / "dispatch/all_boundary_actual_dispatch.mat"
    require(sha(all_path) == all_receipt["dispatch_file_sha256"], "All-boundary dispatch changed")
    repair = json.loads((OUT / "corrected/repair_receipt.json").read_text())
    require(repair["passed"] and repair["previous_26_hydro_site_corrections_preserved"], "Mapping repair is unqualified")
    require(sha(ROOT / repair["model_generator_register_path"]) == repair["model_generator_register_sha256"], "Corrected generator register changed")
    check_records(pd.read_csv(OUT / "corrected/source_manifest.csv").to_dict("records"))
    original = pd.read_csv(ROOT / "output/nygrid_2025_moses_audit/corrected/model_generator_register.csv", keep_default_na=False)
    corrected = pd.read_csv(ROOT / repair["model_generator_register_path"], keep_default_na=False)
    require(np.array_equal(original.gen_row, corrected.gen_row) and np.array_equal(original.device_key, corrected.device_key), "Generator identity/order changed")
    data = loadmat(BASE / "dispatch.mat", simplify_cells=True)
    updated = loadmat(updated_path, simplify_cells=True)
    all_updated = loadmat(all_path, simplify_cells=True)
    model = loadmat(SLIM / "network/network_cases.mat", simplify_cells=True)
    controls = np.load(PAR / "controls/inputs.npz", allow_pickle=False)
    verify_control_sources(controls, json.loads((PAR / "controls/input_receipt.json").read_text()))
    gamma = float(data["gamma"])
    times = np.asarray(data["timestamp_utc"]).astype(str)
    require(np.array_equal(times, np.asarray(updated["timestamp_utc"]).astype(str)) and gamma == float(updated["gamma"]), "Updated dispatch axis/scale changed")
    require(np.array_equal(times, np.asarray(all_updated["timestamp_utc"]).astype(str)) and gamma == float(all_updated["gamma"]), "All-boundary dispatch axis/scale changed")
    _, source_ok, _ = source_inputs(times)
    old_q = np.asarray(data["dispatch_qualified"], bool) & np.asarray(controls["observed_replay_qualified"], bool)
    new_q = np.asarray(updated["qualified"], bool)
    all_q = np.asarray(all_updated["qualified"], bool)
    common = old_q & source_ok & new_q & all_q
    require(np.all(old_q[new_q]) and np.all(source_ok[new_q]) and np.all(old_q[all_q]) and common.sum() > 0, "Unexpected common source cohort")
    load = np.pad(data["bus_pd"], ((0, 0), (0, 8)))
    target = np.asarray(controls["observed_model_mw"])
    limits = np.asarray(controls["p_only_limit_model_mw"])
    dc = np.column_stack([data["dc_pf"], target])
    modes = [("previous_PAR_baseline", False, "scheduled"), ("mapping_only", True, "scheduled"),
             ("Ontario_actual_only", False, "Ontario"), ("Ontario_actual_and_mapping", True, "Ontario"),
             ("all_boundary_actual_only", False, "all"), ("combined", True, "all")]
    records, baseline_checks = [], []
    require(np.array_equal(np.asarray(updated['hour_index']).ravel(), np.arange(1, 8761))
            and np.array_equal(np.asarray(all_updated['hour_index']).ravel(), np.arange(1, 8761)), 'Updated dispatch physical-hour axis changed')
    for frame, q in [(updated, new_q), (all_updated, all_q)]:
        require(frame['gen_pg'].shape == data['gen_pg'].shape
                and np.isfinite(frame['gen_pg'][q]).all()
                and np.isnan(frame['gen_pg'][~q]).all(), 'Updated generation shape or missing-hour policy differs')
    for topology, dated in [("dated", True), ("year_end", False)]:
        states = state_schedule(times, dated)
        prior = loadmat(PAR / "replay" / (topology + "_verified_PAR_flows.mat"), simplify_cells=True)
        for name, remap, boundary_basis in modes:
            actual_exchange = boundary_basis != "scheduled"
            q = {"scheduled": old_q, "Ontario": new_q, "all": all_q}[boundary_basis]
            pg = {"scheduled": data, "Ontario": updated, "all": all_updated}[boundary_basis]["gen_pg"]
            register = corrected if remap else original
            nl = len(model[states[0]]["branch"])
            flows = np.full((8760, nl), np.nan)
            angles = np.full((8760, 148), np.nan)
            interfaces = np.full((8760, 7), np.nan)
            residual, slack = np.full(8760, np.nan), np.full(8760, np.nan)
            for key in sorted(set(states)):
                ix = np.flatnonzero(q & (states == key))
                if not len(ix):
                    continue
                case = make_controlled_case(model[key], register.bus_id.to_numpy(int), target[ix[0]], limits)
                result = predict(network(case), load[ix], pg[ix], dc[ix])
                a = result["angle_deg"]
                ref = np.asarray(data["reference_bus"], int)[ix] - 1
                a -= a[np.arange(len(ix)), ref][:, None]
                recovery = model["recovery"][key.removesuffix("_case")]
                interfaces[ix] = np.deg2rad(a) @ recovery["interface_angle_matrix"].T + recovery["interface_flow_offset"]
                flows[ix], angles[ix] = result["flow"], a
                residual[ix] = result["nodal_residual_mw"]
                slack[ix] = np.max(abs(result["result_pg"] - pg[ix]), axis=1)
            require(np.nanmax(residual) < 1e-7 and np.nanmax(slack) < 1e-7, "Network replay changed balanced input generation")
            if name == "previous_PAR_baseline":
                fe = float(np.max(abs(flows[q] - prior["branch_pf"][q])))
                ie = float(np.max(abs(interfaces[q] - prior["interface_pf"][q])))
                require(fe < 1e-7 and ie < 1e-7, "Replayed original PAR baseline changed")
                baseline_checks.append(dict(topology=topology, hours=int(q.sum()), maximum_branch_error_mw=fe,
                                            maximum_interface_error_mw=ie, original_file=(PAR / "replay" / (topology + "_verified_PAR_flows.mat")).relative_to(ROOT).as_posix()))
                continue
            variant = topology + "_" + name
            path = folder / (variant + ".mat")
            saved_target = target.copy(); saved_target[~q] = np.nan
            logical = -saved_target.sum(axis=1)
            savemat(path, dict(hour_index=data["hour_index"], timestamp_utc=times.astype(object),
                qualified=q, common_scoring_mask=common, network_state_ids=states,
                branch_pf=flows, bus_va=angles, interface_pf=interfaces,
                corrected_generator_buses=register.bus_id.to_numpy(int), par_transfer_model_mw=saved_target,
                logical_original_branch211_pf=logical, gamma=gamma, reference_bus=data["reference_bus"],
                nodal_residual_mw=residual, slack_change_mw=slack,
                generation_source={"scheduled": "frozen_original_dispatch", "Ontario": "actual_Ontario_dispatch", "all": "all_boundary_actual_dispatch"}[boundary_basis],
                boundary_basis=boundary_basis, all_boundary_actual_exchange_used=boundary_basis == "all",
                actual_Ontario_exchange_used=actual_exchange, additional_mapping_repair_used=remap),
                do_compression=True, oned_as="column")
            row = dict(variant=variant, topology=topology, mode=name, qualified_hours=int(q.sum()),
                common_scoring_hours=int(common.sum()), actual_exchange=actual_exchange, boundary_basis=boundary_basis, mapping_repaired=remap,
                maximum_nodal_residual_model_mw=float(np.nanmax(residual)),
                maximum_generation_change_by_powerflow_model_mw=float(np.nanmax(slack)),
                file=path.relative_to(ROOT).as_posix(), sha256=sha(path))
            records.append(row); print(json.dumps(row), flush=True)
    pd.DataFrame(baseline_checks).to_csv(folder / "baseline_replay_checks.csv", index=False)
    deps = [BASE / "dispatch.mat", BASE / "dispatch_bounds.mat", BASE / "dispatch_priors.mat", updated_path, all_path,
        OUT / "dispatch/all_boundary_dispatch_receipt.json",
        OUT / "dispatch/dispatch_receipt.json", OUT / "corrected/model_generator_register.csv", OUT / "corrected/repair_receipt.json",
        PAR / "controls/inputs.npz", PAR / "controls/input_receipt.json", SLIM / "network/network_cases.mat",
        OUT / "ontario/hourly_actual_exchange.csv", OUT / "ontario/hourly_exchange_quality.csv", OUT / "ontario/source_quality_receipt.json",
        ROOT / "scripts/nygrid_2025_par_controls/controlled_equivalent.py", ROOT / "scripts/nygrid_2019/replay_dc.py", Path(__file__)]
    np.save(folder / "paired_common_mask.npy", common, allow_pickle=False)
    deps += [folder / "paired_common_mask.npy"]
    deps += [PAR / "replay" / (t + "_verified_PAR_flows.mat") for t in ['dated', 'year_end']]
    receipt = dict(passed=True, qualified_common_hours=int(common.sum()), original_qualified_hours=int(old_q.sum()),
        all_boundary_qualified_hours=int(all_q.sum()), Ontario_only_qualified_hours=int(new_q.sum()),
        preferred_mode="combined", Ontario_only_modes_are_mixed_boundary_basis_diagnostics=True,
        raw_boundaries_and_internal_operators_not_fitted=True, internal_interface_observations_read=False,
        modes=[m[0] for m in modes], variants=records, baseline_replays=baseline_checks,
        native_generation_reconstructed_only_for_actual_exchange_modes=True, native_priors_capacities_weights_unchanged=True,
        load_original_four_DC_and_verified_PAR_controls_unchanged=True,
        topology_changed=False, physical_new_Dysinger_PAR_network_added=False,
        dependencies=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in deps])
    (folder / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def score():
    folder = OUT / "comparison"; folder.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((OUT / "replay/provenance.json").read_text())
    data = loadmat(BASE / "dispatch.mat", simplify_cells=True, variable_names=["gamma", "timestamp_utc"])
    check_records(receipt["dependencies"])
    common = np.load(OUT / "replay/paired_common_mask.npy", allow_pickle=False)
    require(common.dtype == bool and common.shape == (8760,) and int(common.sum()) == receipt["qualified_common_hours"], "Paired scoring mask changed")
    gamma = float(data["gamma"])
    obs_path = ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv"
    obs = pd.read_csv(obs_path)
    require(np.array_equal(obs.timestamp_utc.astype(str), np.asarray(data["timestamp_utc"]).astype(str)), "Scoring clock differs")
    y = obs[NAMES].to_numpy(float)
    months = pd.to_datetime(obs.timestamp_utc, utc=True).dt.tz_convert("America/New_York").dt.month.to_numpy()
    variants = [(r["variant"], ROOT / r["file"], r["sha256"]) for r in receipt["variants"]]
    variants += [(t + "_previous_PAR_baseline", PAR / "replay" / (t + "_verified_PAR_flows.mat"), None) for t in ["dated", "year_end"]]
    annual, monthly = [], []
    for name, path, expected in variants:
        if expected is not None:
            require(sha(path) == expected, "A replay changed before scoring")
        d = loadmat(path, simplify_cells=True, variable_names=["qualified", "interface_pf"])
        prediction = d["interface_pf"] / gamma
        for cohort, q in [("own_qualified", np.asarray(d["qualified"], bool)), ("paired_common", common)]:
            require(np.all(np.asarray(d["qualified"], bool)[q]) and np.isfinite(prediction[q]).all() and np.isfinite(y[q]).all(), "Invalid paired scoring hours")
            for j, interface in enumerate(NAMES):
                for month in [0] + list(range(1, 13)):
                    mask = q if month == 0 else q & (months == month)
                    e = prediction[mask, j] - y[mask, j]
                    row = dict(variant=name, cohort=cohort, month=month, interface=interface, hours=int(mask.sum()),
                        mae_public_equivalent_mw=float(np.mean(abs(e))), rmse_public_equivalent_mw=float(np.sqrt(np.mean(e**2))),
                        bias_public_equivalent_mw=float(np.mean(e)), wape_percent=float(100 * abs(e).sum() / abs(y[mask, j]).sum()),
                        internal_interface_observations_used_to_fit=False)
                    (annual if month == 0 else monthly).append(row)
    pd.DataFrame(annual).to_csv(folder / "interface_summary.csv", index=False)
    pd.DataFrame(monthly).to_csv(folder / "interface_monthly.csv", index=False)
    (folder / "scoring_receipt.json").write_text(json.dumps(dict(passed=True, internal_observations_only_posthoc=True,
        common_hours=int(common.sum()), original_observation_sha256=sha(obs_path),
        replay_receipt_sha256=sha(OUT / "replay/provenance.json"), code_sha256=sha(Path(__file__))), indent=2) + "\n", encoding="utf-8")
    print(pd.DataFrame(annual).query("variant == 'dated_combined' and cohort == 'paired_common'").to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--score-only", action="store_true")
    args = parser.parse_args()
    if not args.score_only:
        replay()
    score()
