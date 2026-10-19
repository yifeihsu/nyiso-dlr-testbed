"""Fresh 148-bus replay conditioned on direction-verified external PAR flows.

Observed internal interfaces are used only afterward for scoring. Hardware
phase limits remain equipment metadata; no aggregate equivalent phase is
exported as a physical tap angle.
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
OUT = ROOT / "output/nygrid_2025_par_controls"
BASE = ROOT / "output/nygrid_2025_dispatch/dispatch"
SLIM = ROOT / "output/nygrid_2025_slim"
REPAIR = ROOT / "output/nygrid_2025_moses_audit"
sys.path.insert(0, str(ROOT / "scripts/nygrid_2025_slim"))
from replay_slim import state_schedule, NAMES
sys.path.insert(0, str(ROOT / "scripts/nygrid_2019"))
from replay_dc import network, predict
from controlled_equivalent import make_controlled_case, qualify_targets


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_control_sources(controls, input_receipt):
    require(input_receipt["status"] == "complete_source_only_two_device_controls"
            and input_receipt["P34_direction_verified"]
            and input_receipt["P34_direction_effective_date"] == "2024-12-03"
            and input_receipt["necessary_active_power_screen_passed"]
            and not input_receipt["internal_interface_observations_read"],
            "Source direction, source-only scope or necessary device screen is unqualified")
    require(bool(controls["observed_direction_verified"])
            and np.array_equal(controls["direction_ontario_to_NY_multiplier"], [1, 1]),
            "The documented Ontario-to-New-York sign was not applied")
    required_dependencies = {
        "output/nygrid_2025_dispatch/dispatch/dispatch.mat",
        "output/nygrid_2025_par_controls/sources/direction/direction_verification_receipt.json",
        "output/nygrid_2025_par_controls/sources/direction/direction_manifest.json",
        "output/nygrid_2025_par_controls/sources/direction/verified_ptid_directions.csv",
        "output/nygrid_2025_par_controls/sources/direction/NYISO_ParFlowDiagrams27.pdf",
        "output/nygrid_2025_par_controls/sources/limits/limits.json",
        "output/nygrid_2025_moses_audit/exchanges/par_source_receipts.csv",
        "output/nygrid_2025_moses_audit/exchanges/par_stlawrence_hourly_2025.csv",
        "output/nygrid_2025_moses_audit/exchanges/par_stlawrence_raw_2025.csv.gz",
        "scripts/nygrid_2025_par_controls/build_control_inputs.py",
    }
    required_outputs = {"output/nygrid_2025_par_controls/controls/" + name for name in
                        ["inputs.npz", "inputs.mat", "hourly_controls.csv", "necessary_p_only_screen.json"]}
    for label, required in [("dependencies", required_dependencies), ("outputs", required_outputs)]:
        records = input_receipt[label]
        require(bool(records), "Missing compiler " + label + " proof")
        paths = [r["path"] for r in records]
        require(len(paths) == len(set(paths)) and required.issubset(paths),
                "Incomplete or duplicate compiler " + label + " proof")
    for record in input_receipt["dependencies"] + input_receipt["outputs"]:
        require(sha(ROOT / record["path"]) == record["sha256"], "Source compiler dependency or output changed: " + record["path"])
    limits = json.loads((OUT / "sources/limits/limits.json").read_text())
    direction = json.loads((OUT / "sources/direction/direction_verification_receipt.json").read_text())
    require(json.loads(str(controls["limit_metadata_json"])) == limits, "NPZ equipment metadata differ from their source")
    require(json.loads(str(controls["direction_metadata_json"])) == direction, "NPZ direction metadata differ from their source")
    devices = {int(x["ptid"]): x for x in limits["devices"]}
    require(np.array_equal(controls["p_only_limit_public_mw"], [devices[int(p)]["necessary_abs_p_screen_mw"] for p in controls["ptids"]]),
            "Numerical P-only envelopes differ from the per-device source metadata")
    require(not bool(controls["hardware_phase_applies_to_equivalent"]), "Physical phase bound was incorrectly mapped to the network equivalent")


def replay():
    folder = OUT / "replay"; folder.mkdir(parents=True, exist_ok=True)
    data = loadmat(BASE / "dispatch.mat", simplify_cells=True)
    model = loadmat(SLIM / "network/network_cases.mat", simplify_cells=True)
    controls = np.load(OUT / "controls/inputs.npz", allow_pickle=False)
    input_receipt = json.loads((OUT / "controls/input_receipt.json").read_text())
    verify_control_sources(controls, input_receipt)
    gen = pd.read_csv(REPAIR / "corrected/model_generator_register.csv")
    times = np.asarray(data["timestamp_utc"]).astype(str)
    gamma = float(data["gamma"])
    require(np.array_equal(controls["ptids"], [25118, 25119]), "PAR order/identity changed")
    require(np.array_equal(controls["timestamp_utc"].astype(str), times), "Control UTC axis changed")
    require(float(controls["gamma"]) == gamma, "Control scale factor changed")
    p = np.asarray(controls["observed_public_mw"], float)
    target = np.asarray(controls["observed_model_mw"], float)
    limits = np.asarray(controls["p_only_limit_public_mw"], float).reshape(-1)
    require(np.allclose(target, p * gamma, equal_nan=True, atol=1e-12, rtol=0), "Control scale applied incorrectly")
    native = np.asarray(data["dispatch_qualified"], bool)
    source_quality = np.asarray(controls["observed_quality"], bool)
    if source_quality.ndim == 2:
        source_quality = source_quality.all(axis=1)
    qualified = native & source_quality & qualify_targets(p, limits)
    require(qualified.sum() > 0, "No qualified source-controlled cases")
    require(np.array_equal(qualified, np.asarray(controls["observed_replay_qualified"], bool)), "Independent source-mask disagreement")
    loads = np.pad(data["bus_pd"], ((0, 0), (0, 8)))
    pg = np.asarray(data["gen_pg"])
    dc = np.column_stack([data["dc_pf"], target])
    bus_ids = np.asarray(model["kept_bus_ids"], int)
    results = []
    for topology, dated in [("dated", True), ("year_end", False)]:
        states = state_schedule(times, dated)
        nl = len(model[states[0]]["branch"])
        flow = np.full((8760, nl), np.nan)
        angle = np.full((8760, 148), np.nan)
        interfaces = np.full((8760, 7), np.nan)
        residual, slack, phase_equivalence_error = [np.full(8760, np.nan) for _ in range(3)]
        prior_diagnostic = loadmat(REPAIR / "replay" / (topology + "_hydro_zone_par_toward_moses.mat"), simplify_cells=True)
        cases = {}
        for key in sorted(set(states)):
            ix = np.flatnonzero(qualified & (states == key))
            if not len(ix):
                continue
            case = make_controlled_case(model[key], gen.bus_id.to_numpy(int), target[ix[0]], limits * gamma)
            cases[key] = case
            net = network(case)
            solved = predict(net, loads[ix], pg[ix], dc[ix])
            a = solved["angle_deg"]
            refs = np.asarray(data["reference_bus"], int)[ix] - 1
            a -= a[np.arange(len(ix)), refs][:, None]
            rec = model["recovery"][key.removesuffix("_case")]
            interfaces[ix] = np.deg2rad(a) @ rec["interface_angle_matrix"].T + rec["interface_flow_offset"]
            flow[ix], angle[ix] = solved["flow"], a
            residual[ix] = solved["nodal_residual_mw"]
            slack[ix] = np.max(abs(solved["result_pg"] - pg[ix]), axis=1)
            other = np.arange(nl) != 210
            phase_equivalence_error[ix] = np.max(abs(solved["flow"][:, other] - prior_diagnostic["branch_pf"][ix][:, other]), axis=1)
            require(np.max(abs(interfaces[ix] - prior_diagnostic["interface_pf"][ix])) < 1e-7,
                    "Fixed operator differs from independently signed constrained-flow equivalent")
        require(np.nanmax(residual) < 1e-7 and np.nanmax(slack) < 1e-7 and np.nanmax(phase_equivalence_error) < 1e-7,
                "Source-controlled replay failed conservation or representation equivalence")
        require(np.nanmax(abs(flow[:, 210])) == 0, "Retired passive representation still carries AC flow")
        logical_transfer = -target.sum(axis=1)
        logical_transfer[~qualified] = np.nan
        saved_target = target.copy(); saved_target[~qualified] = np.nan
        path = folder / (topology + "_verified_PAR_flows.mat")
        savemat(path, dict(hour_index=data["hour_index"], timestamp_utc=times.astype(object), qualified=qualified,
            network_state_ids=states, branch_pf=flow, bus_va=angle, interface_pf=interfaces,
            par_transfer_model_mw=saved_target, logical_original_branch211_pf=logical_transfer,
            original_four_dc_pf=data["dc_pf"], corrected_generator_buses=gen.bus_id.to_numpy(int),
            gamma=gamma, ptids=controls["ptids"], necessary_p_only_limits_model_mw=limits * gamma,
            nodal_residual_mw=residual, slack_change_mw=slack,
            maximum_other_ac_equivalence_error_mw=phase_equivalence_error,
            physical_tap_reconstruction_available=False, physical_HVDC_devices_added=0,
            ideal_PAR_equivalents_added=2, passive_branch211_is_representation_substitution=True),
            do_compression=True, oned_as="column")
        row = dict(variant=topology + "_verified_PAR_flows", topology=topology, qualified_hours=int(qualified.sum()),
            source_gap_hours=int((~qualified).sum()), original_buses=140, added_buses=8,
            original_DC_records_preserved=4, ideal_PAR_equivalents=2, added_physical_HVDC=0,
            maximum_nodal_residual_model_mw=float(np.nanmax(residual)),
            maximum_generation_change_model_mw=float(np.nanmax(slack)),
            maximum_other_ac_representation_error_model_mw=float(np.nanmax(phase_equivalence_error)),
            file=path.relative_to(ROOT).as_posix(), sha256=sha(path))
        results.append(row); print(json.dumps(row), flush=True)
    dependencies = [BASE / "dispatch.mat", BASE / "dispatch_bounds.mat", SLIM / "network/network_cases.mat",
        REPAIR / "corrected/model_generator_register.csv", OUT / "controls/inputs.npz", OUT / "controls/input_receipt.json",
        OUT / "sources/direction/direction_verification_receipt.json", OUT / "sources/limits/limits.json",
        Path(__file__), Path(__file__).with_name("controlled_equivalent.py"), ROOT / "scripts/nygrid_2019/replay_dc.py"]
    receipt = dict(passed=True, status="source_direction_verified_external_PAR_flow_conditioned_DC_replay",
        internal_interface_observations_used=False, observed_PAR_flows_are_external_inputs=True,
        PAR_flow_forecast_or_physical_tap_simulation=False, full_physical_operating_limits_verified=False,
        source_noload_phase_range_applied_to_aggregate_equivalent=False, physical_HVDC_devices_added=0,
        native_PG_PD_QD_bounds_and_total_external_exchanges_preserved=True,
        variants=results, dependencies=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in dependencies])
    (folder / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def score():
    folder = OUT / "comparison"; folder.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((OUT / "replay/provenance.json").read_text())
    obs_path = ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv"
    obs = pd.read_csv(obs_path)
    baseline = loadmat(BASE / "dispatch.mat", simplify_cells=True, variable_names=["gamma", "timestamp_utc", "dispatch_qualified"])
    require(np.array_equal(obs.timestamp_utc.astype(str), np.asarray(baseline["timestamp_utc"]).astype(str)), "Observation time alignment changed")
    gamma = float(baseline["gamma"])
    y = obs[NAMES].to_numpy(float)
    months = pd.to_datetime(obs.timestamp_utc, utc=True).dt.tz_convert("America/New_York").dt.month.to_numpy()
    annual, monthly = [], []
    for item in receipt["variants"]:
        require(sha(ROOT / item["file"]) == item["sha256"], "Replay changed before scoring")
        new = loadmat(ROOT / item["file"], simplify_cells=True)
        q = np.asarray(new["qualified"], bool)
        topology = item["topology"]
        for label, path, key in [
            (topology + "_frozen_baseline", SLIM / "replay" / ("topology_" + topology + ".mat"), "interface_pf"),
            (topology + "_confirmed_hydro_repair", REPAIR / "replay" / (topology + "_hydro_zone_corrected.mat"), "interface_pf"),
            (item["variant"], ROOT / item["file"], "interface_pf"),
        ]:
            data = loadmat(path, simplify_cells=True, variable_names=[key, "qualified"])
            require(np.all(np.asarray(data["qualified"], bool)[q]), "Comparison baseline lacks a selected hour")
            f = data[key] / gamma
            require(np.isfinite(f[q]).all() and np.isfinite(y[q]).all(), "Nonfinite score on common cohort")
            for j, interface in enumerate(NAMES):
                for month in [0] + list(range(1, 13)):
                    mask = q if month == 0 else q & (months == month)
                    e = f[mask, j] - y[mask, j]
                    row = dict(variant=label, month=month, interface=interface, hours=int(mask.sum()),
                        mae_public_equivalent_mw=float(np.mean(abs(e))), rmse_public_equivalent_mw=float(np.sqrt(np.mean(e**2))),
                        bias_public_equivalent_mw=float(np.mean(e)), wape_percent=float(100 * abs(e).sum() / abs(y[mask, j]).sum()),
                        PAR_flows_used_as_external_inputs=label == item["variant"], internal_observations_used_to_fit=False)
                    (annual if month == 0 else monthly).append(row)
    pd.DataFrame(annual).to_csv(folder / "interface_summary.csv", index=False)
    pd.DataFrame(monthly).to_csv(folder / "interface_monthly.csv", index=False)
    (folder / "scoring_receipt.json").write_text(json.dumps(dict(passed=True, internal_observations_only_posthoc=True,
        observed_internal_sha256=sha(obs_path), replay_provenance_sha256=sha(OUT / "replay/provenance.json"),
        code_sha256=sha(Path(__file__))), indent=2) + "\n", encoding="utf-8")
    print(pd.DataFrame(annual).query("variant == 'dated_verified_PAR_flows'").to_string(index=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--score-only", action="store_true")
    args = p.parse_args()
    if not args.score_only:
        replay()
    score()
