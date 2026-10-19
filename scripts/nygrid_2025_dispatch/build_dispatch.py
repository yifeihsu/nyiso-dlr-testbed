"""Capacity-bounded hourly DC reconstruction on the fixed modified-2019 NPCC.

The objective uses generation-source priors only. It does not read internal
interface observations. No slack generation, load shedding, or enlarged bounds
are allowed to turn an infeasible or source-incomplete hour into a valid case.
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
OUT = ROOT / "output/nygrid_2025_dispatch"
INPUTS = ROOT / "output/nygrid_2025_inputs/model/operating_inputs.mat"
sys.path.insert(0, str(ROOT / "scripts/nygrid_2019"))
from replay_dc import network, predict, operator

PENALTIES = {"Combined Fossil": 1., "Nuclear": 100., "Hydro": 25.,
             "Wind": 100., "Other Renewables": 100.}
STATUS = {0: "missing_source", 1: "bounded_dc_qualified", 2: "infeasible_native_capacity"}
TOL = 1e-7


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def boolean(series):
    return series.astype(str).str.lower().isin(["1", "true", "1.0"]).to_numpy()


def bounded_projection(prior, lower, upper, target, weights):
    """Unique weighted quadratic projection onto boxes and one exact sum.

    J = 0.5 sum(weights * (p-prior)^2), Lagrangian J-lambda*(sum(p)-target).
    The returned dual supports an independent KKT check. Infeasible targets
    return NaNs, never a relaxed bound or unscheduled balancing generator.
    """
    p0, lo, hi, w = [np.asarray(x, float) for x in [prior, lower, upper, weights]]
    target = np.asarray(target, float).reshape(-1)
    require(p0.ndim == 2 and p0.shape == lo.shape == hi.shape == w.shape, "Projection shape mismatch")
    require(len(target) == len(p0), "Projection target shape mismatch")
    require(all(np.isfinite(x).all() for x in [p0, lo, hi, w, target]), "Nonfinite projection input")
    require((hi >= lo).all() and (w > 0).all(), "Invalid bounds or objective weights")
    feasible = (target >= lo.sum(axis=1) - TOL) & (target <= hi.sum(axis=1) + TOL)
    result, dual = np.full_like(p0, np.nan), np.full(len(p0), np.nan)
    rows = np.flatnonzero(feasible)
    for block_start in range(0, len(rows), 128):
        ix = rows[block_start:block_start + 128]
        q, l, u, v = p0[ix], lo[ix], hi[ix], 1 / w[ix]
        a = np.min((l - q) / v, axis=1) - 1
        b = np.max((u - q) / v, axis=1) + 1
        for _ in range(64):
            mid = (a + b) / 2
            proposed = np.clip(q + mid[:, None] * v, l, u)
            below = proposed.sum(axis=1) < target[ix]
            a = np.where(below, mid, a)
            b = np.where(below, b, mid)
        lam = (a + b) / 2
        result[ix] = np.clip(q + lam[:, None] * v, l, u)
        dual[ix] = lam
    if len(rows):
        require(np.max(np.abs(result[rows].sum(axis=1) - target[rows])) < TOL,
                "Projection did not achieve exact balance within tolerance")
    return result, dual, feasible


def static_case(parent, register, pd0, qd0, pg0, lower0, upper0, dc0, reference_bus):
    case = {k: copy.deepcopy(parent[k]) for k in ["version", "baseMVA", "bus", "branch", "dcline", "if"]}
    case["version"] = "2"
    case["baseMVA"] = float(case["baseMVA"])
    bus = np.asarray(case["bus"], float).copy()
    gen = np.zeros((len(register), 21))
    gen[:, 0] = register.bus_id.to_numpy(int)
    gen[:, 1] = pg0
    gen[:, 5] = 1.0
    gen[:, 6] = case["baseMVA"]
    # Static connectivity template. Hourly loader deactivates unavailable rows.
    gen[:, 7] = 1
    gen[:, 8], gen[:, 9] = upper0, lower0
    bus[:, 2], bus[:, 3], bus[:, 8] = pd0, qd0, 0
    bus[:, 1] = 1
    bus[np.isin(bus[:, 0], gen[:, 0]), 1] = 2
    bus[bus[:, 0] == reference_bus, 1] = 3
    dc = np.asarray(case["dcline"], float).copy()
    dc[:, 3], dc[:, 4] = dc0, dc0
    dc[:, 5:7] = 0
    dc[:, 9], dc[:, 10] = dc0, dc0
    dc[:, 11:15] = 0
    case.update(bus=bus, gen=gen, dcline=dc,
                genfuel=register.fuel_category.to_numpy(dtype=object))
    case["if"] = {"map": np.asarray(parent["if"]["map"]).copy()}
    return case


def build(source_root=OUT, output=None):
    source_root = Path(source_root).resolve()
    output = Path(output).resolve() if output else source_root / "dispatch"
    require(not (output / "dispatch.mat").exists(), "Choose a new output folder; dispatch.mat already exists")
    fleet_path = source_root / "fleet/fleet_register.csv"
    bounds_path = source_root / "fleet/fleet_bounds.npz"
    prior_path = source_root / "priors/dispatch_priors.npz"
    prior_sources = pd.read_csv(source_root / "priors/source_manifest.csv")
    for row in prior_sources.itertuples(index=False):
        require(sha(ROOT / row.path) == row.sha256, f"Prior dependency changed: {row.path}")
    fleet = pd.read_csv(fleet_path, keep_default_na=False)
    bounds = np.load(bounds_path, allow_pickle=False)
    priors = np.load(prior_path, allow_pickle=False)
    d = loadmat(INPUTS, simplify_cells=True)
    hours = np.arange(1, 8761)
    require(np.array_equal(priors["hour_index"], hours), "Prior physical-hour axis changed")
    require(np.array_equal(bounds["hour_index"], hours), "Bound physical-hour axis changed")
    require(np.array_equal(fleet.fleet_id, priors["fleet_id"])
            and np.array_equal(fleet.fleet_id, bounds["fleet_id"]), "Fleet identity/order mismatch")
    require(np.array_equal(priors["timestamp_utc"].astype(str), np.asarray(d["timestamp_utc"]).astype(str)),
            "Source/prior UTC hours differ")
    gamma = float(d["gamma"])
    public_upper = np.asarray(priors["available_pmax_actual_mw"], float)
    public_lower = np.asarray(priors["available_pmin_actual_mw"], float)
    physical = np.asarray(bounds["physical_pmax_actual_mw"], float)
    preferred = np.asarray(priors["prior_actual_mw"], float)
    require(public_upper.shape == public_lower.shape == physical.shape == preferred.shape == (8760, len(fleet)),
            "Fleet/prior matrix shape mismatch")
    # Excluded/retired/zero-output records stay in the complete source register.
    # Only units with positive admitted capacity somewhere enter the case.
    selected = np.flatnonzero(np.any(np.isfinite(public_upper) & (public_upper > 0), axis=0))
    require(len(selected) > 0, "No admitted native generators")
    native = fleet.iloc[selected].copy().reset_index(drop=True)
    native_ids = native.fleet_id.to_numpy(int)
    buses = pd.to_numeric(native.bus_id).to_numpy(int)
    require(np.isin(buses, np.arange(37, 83)).all(), "Native generator outside retained NY buses")
    require(native.device_key.is_unique, "Duplicated native physical generator identity")
    require(native.balancing_authority_code.eq("NYIS").all(), "Admitted native fleet includes an unqualified balancing authority")
    require(set(native.fuel_category).issubset(PENALTIES), "Unknown dispatch fuel family")
    native_lower = public_lower[:, selected] * gamma
    native_upper = public_upper[:, selected] * gamma
    native_prior = preferred[:, selected] * gamma
    native_physical = physical[:, selected] * gamma
    penalties = np.array([PENALTIES[f] for f in native.fuel_category])
    if "is_pumped_hydro" in native:
        penalties[boolean(native.is_pumped_hydro)] = 100
    weights = penalties[None, :] / np.where(native_physical > 0, native_physical, 1.)
    source_ok = np.asarray(priors["source_hour_qualified"], bool).reshape(-1)
    source_ok &= np.asarray(d["boundary_hour_qualified"], bool).reshape(-1)
    require(len(source_ok) == 8760, "Qualification length mismatch")
    ix = np.flatnonzero(source_ok)
    require(len(ix) > 0, "No source-qualified hours")
    for label, values in [("prior", native_prior), ("lower", native_lower), ("upper", native_upper)]:
        require(np.isfinite(values[ix]).all(), f"Qualified hour has nonfinite {label}")
    require((native_lower[ix] >= 0).all() and (native_upper[ix] >= native_lower[ix]).all(), "Invalid native P bounds")
    require(np.max(native_upper[ix] - native_physical[ix]) < TOL, "Availability exceeds source physical capacity")

    parent = d["base_case"]
    parent_gen = np.asarray(parent["gen"])
    ext_rows = np.flatnonzero(np.asarray(parent["genfuel"]) == "Import")
    require(len(ext_rows) == 28, "Expected 27 external equivalents and one HQ record")
    fixed = np.asarray(d["external_input_pg"], float)[:, ext_rows]
    bus_pd, bus_qd, dc_pf = [np.asarray(d[k], float) for k in ["bus_gross_pd", "bus_gross_qd", "dcline_pf"]]
    target = bus_pd.sum(axis=1) + np.asarray(parent["bus"])[:, 4].sum() - fixed.sum(axis=1)
    independent_ny_target = np.asarray(d["zonal_load_model_mw"]).sum(axis=1) - np.asarray(d["boundary_model_mw"]).sum(axis=1)
    require(np.max(np.abs(target[ix] - independent_ny_target[ix])) < TOL, "Global and NY boundary balances differ")
    dispatch_native = np.full_like(native_prior, np.nan)
    dual = np.full(8760, np.nan)
    p, lam, feasible = bounded_projection(native_prior[ix], native_lower[ix], native_upper[ix], target[ix], weights[ix])
    dispatch_native[ix] = p
    dual[ix] = lam
    status = np.zeros(8760, dtype=np.int8)
    status[ix] = np.where(feasible, 1, 2)
    valid = status == 1
    vi = np.flatnonzero(valid)
    require(len(vi) > 0, "No bounded feasible dispatch hours")
    register_rows = []
    for j, r in native.iterrows():
        register_rows.append(dict(gen_row=j + 1, fleet_id=int(r.fleet_id), device_key=r.device_key,
            role="native", bus_id=int(r.bus_id), zone=r.zone, fuel_category=r.fuel_category,
            plant_id=r.plant_id, eia_generator_id=r.eia_generator_id,
            mapping_method=r.mapping_method, parent_gen_row="", penalty=float(penalties[j])))
    parent_metadata_path = source_root / "fleet/source_parent/npcc.csv"
    original_info = pd.read_csv(parent_metadata_path, keep_default_na=False).set_index("idx")
    for k, row in enumerate(ext_rows):
        bus_id = int(parent_gen[row, 0])
        register_rows.append(dict(gen_row=len(native) + k + 1, fleet_id=0,
            device_key=f"NPCC2019:EXTERNAL_GEN_ROW:{row + 1}", role="fixed_external",
            bus_id=bus_id, zone=original_info.loc[bus_id, "zone"], fuel_category="Import",
            plant_id="", eia_generator_id="", mapping_method="preserved_full2019_external_or_HQ_equivalent",
            parent_gen_row=int(row + 1), penalty=0.))
    register = pd.DataFrame(register_rows)
    ng, nn = len(register), len(native)
    pg, prior_pg, lower, upper = [np.full((8760, ng), np.nan) for _ in range(4)]
    pg[valid, :nn], pg[valid, nn:] = dispatch_native[valid], fixed[valid]
    prior_pg[:, :nn], prior_pg[:, nn:] = native_prior, fixed
    lower[:, :nn], lower[:, nn:] = native_lower, fixed
    upper[:, :nn], upper[:, nn:] = native_upper, fixed
    reference = np.zeros(8760, dtype=np.int32)
    for h in vi:
        preferred_bus = np.flatnonzero((buses == 50) & (native_upper[h] > 0))
        ref_col = preferred_bus[0] if len(preferred_bus) else int(np.argmax(pg[h, :nn]))
        reference[h] = buses[ref_col]
        require(upper[h, ref_col] > 0, "No online native reference generator")
    first = int(vi[0])
    case = static_case(parent, register, bus_pd[first], bus_qd[first], pg[first], lower[first], upper[first],
                       dc_pf[first], int(reference[first]))
    net = network(case)
    replay = predict(net, bus_pd[valid], pg[valid], dc_pf[valid])
    slack_change = np.max(np.abs(replay["result_pg"] - pg[valid]), axis=1)
    require(slack_change.max() < TOL, "DC solve changed balanced input generation")
    require(replay["nodal_residual_mw"].max() < TOL, "DC nodal balance failed")
    branch_pf = np.full((8760, 225), np.nan)
    bus_va = np.full((8760, 140), np.nan)
    branch_pf[valid] = replay["flow"]
    angles = replay["angle_deg"]
    angles -= angles[np.arange(len(vi)), reference[valid] - 1][:, None]
    bus_va[valid] = angles
    residual = np.full(8760, np.nan); residual[valid] = replay["nodal_residual_mw"]
    delta = np.full(8760, np.nan); delta[valid] = slack_change
    objective = np.full(8760, np.nan)
    objective[valid] = .5 * np.sum(weights[valid] * (pg[valid, :nn] - native_prior[valid]) ** 2, axis=1)
    # Save inherited interface predictions only. Observations are intentionally absent.
    imap = np.asarray(parent["if"]["map"])
    op = operator([imap[imap[:, 0] == j, 1] for j in [1, 2, 3, 4, 5, 8, 10]], 225)
    interface_pf = branch_pf @ op.T
    output.mkdir(parents=True, exist_ok=True)
    register.to_csv(output / "model_generator_register.csv", index=False, lineterminator="\n")
    results = dict(hour_index=hours, timestamp_utc=priors["timestamp_utc"].astype(object), base_case=case,
        native_fleet_ids=native_ids, bus_pd=bus_pd, bus_qd=bus_qd, gen_pg=pg, gen_pmin=lower, gen_pmax=upper,
        prior_pg=prior_pg, objective_weights=weights, objective_value=objective, dual_lambda=dual,
        dc_pf=dc_pf, branch_pf=branch_pf, bus_va=bus_va, inherited_interface_pf=interface_pf,
        source_qualified=source_ok, dispatch_qualified=valid, status_code=status, reference_bus=reference,
        native_required_pg=target, native_physical_pmax=native_physical,
        nodal_residual_mw=residual, dc_slack_change_mw=delta, gamma=gamma)
    # Separate states, bounds and priors retain exact float64 arrays while
    # keeping individual annual artifacts portable below repository size caps.
    for filename, names in [("dispatch_bounds.mat", ["gen_pmin", "gen_pmax", "native_physical_pmax"]),
                            ("dispatch_priors.mat", ["prior_pg", "objective_weights"]),
                            ("dispatch_network.mat", ["branch_pf", "bus_va", "inherited_interface_pf"])]:
        portion = {name: results.pop(name) for name in names}
        portion.update(hour_index=hours, native_fleet_ids=native_ids)
        savemat(output / filename, portion, do_compression=True, oned_as="column")
    savemat(output / "dispatch.mat", results, do_compression=True, oned_as="column")
    table = pd.DataFrame(dict(hour_index=hours, timestamp_utc=priors["timestamp_utc"].astype(str),
        source_qualified=source_ok, dispatch_qualified=valid, status_code=status,
        status=[STATUS[int(s)] for s in status], native_required_model_mw=target,
        native_minimum_model_mw=np.sum(native_lower, axis=1), native_maximum_model_mw=np.sum(native_upper, axis=1),
        reference_bus=reference, nodal_residual_mw=residual, slack_change_mw=delta, objective_value=objective))
    table.to_csv(output / "hour_status.csv", index=False, lineterminator="\n")
    fuel_rows = []
    for fuel in PENALTIES:
        mask = native.fuel_category.eq(fuel).to_numpy()
        before = native_prior[:, mask].sum(axis=1)
        full_preferred = preferred[:, fleet.fuel_category.eq(fuel).to_numpy()].sum(axis=1) * gamma
        after = pg[:, :nn][:, mask].sum(axis=1)
        for h in range(8760):
            fuel_rows.append(dict(hour_index=h + 1, fuel_category=fuel, dispatch_qualified=bool(valid[h]),
                prior_model_mw=before[h], full_source_prior_model_mw=full_preferred[h],
                excluded_prior_model_mw=full_preferred[h] - before[h], dispatch_model_mw=after[h],
                adjustment_model_mw=after[h] - before[h], total_source_adjustment_model_mw=after[h] - full_preferred[h]))
    pd.DataFrame(fuel_rows).to_csv(output / "fuel_adjustments.csv", index=False, lineterminator="\n")
    contract = dict(model_year=2025, parent="modified2019_full_NPCC", buses=140, branches=225, dc_links=4,
        hourly_scope="independent_capacity_bounded_DC_snapshots", gamma=gamma,
        objective="0.5 sum(kappa_fuel / physical_model_Pmax * (PG-prior)^2); exact native sum and box bounds",
        penalties=PENALTIES, pumped_hydro_penalty=100,
        weight_zero_capacity_policy="denominator1 only for a fixed zero-capacity variable",
        penalty_interpretation="declared research preference; not estimated uncertainty or economic cost",
        status_codes=STATUS, native_pmin_policy="zero; continuous on/off and within-hour output relaxation",
        external_p_bounds="equal to prescribed hourly equivalent generation and HQ injection",
        dcline_p_bounds="equal to prescribed hourly schedules; not certified physical ratings",
        reference_policy="bus50 if it has positive admitted native capacity, otherwise bus of largest dispatched native generator",
        reference_is_free_balancing_generator=False, load_shedding_allowed=False, bounds_relaxed=False,
        topology_changed=False, internal_interface_observations_read=False, interface_calibration_performed=False,
        ac_feasibility_validated=False, reactive_capabilities_available=False,
        reactive_case_fields="zero DC placeholders only; not physical Q capability bounds",
        physical_branch_thermal_feasibility_validated=False, unit_commitment_validated=False,
        ramping_validated=False, reserve_feasibility_validated=False, storage_energy_feasibility_validated=False,
        pumped_hydro_policy="generation ceiling at frozen estimated hourly prior; no extra balancing output, pumping or SOC model",
        battery_dispatch_enabled=False, source_gap_policy="retain all8760 rows; incomplete source hours have no solved state",
        generation_ledger="all renewables are generators; gross loads not netted again",
        array_files={"dispatch.mat":"case and solved states", "dispatch_bounds.mat":"generator active-power bounds",
                     "dispatch_priors.mat":"generation priors and objective weights",
                     "dispatch_network.mat":"solved branch flows and bus angles"},
        provenance=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p))
                    for p in [INPUTS, fleet_path, bounds_path, prior_path, parent_metadata_path, Path(__file__)]])
    summary = dict(hours=8760, source_qualified_hours=int(source_ok.sum()), dispatched_hours=int(valid.sum()),
        missing_source_hours=int((status == 0).sum()), capacity_infeasible_hours=int((status == 2).sum()),
        native_generators=nn, fixed_external_generators=28, generators=ng,
        maximum_nodal_residual_mw=float(residual[valid].max()), maximum_slack_change_mw=float(delta[valid].max()),
        maximum_generator_bound_violation_mw=float(max(0., np.max(lower[valid] - pg[valid]), np.max(pg[valid] - upper[valid]))),
        minimum_native_requirement_mw=float(target[valid].min()), maximum_native_requirement_mw=float(target[valid].max()),
        dc_snapshot_qualified=True, all_source_qualified_hours_solved=bool(np.all(status[source_ok] == 1)),
        ac_feasibility_validated=False, topology_changed=False,
        file_sha256={name:sha(output / name) for name in ["dispatch.mat", "dispatch_bounds.mat", "dispatch_priors.mat", "dispatch_network.mat"]})
    for filename, record in [("contract.json", contract), ("summary.json", summary)]:
        (output / filename).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=OUT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    build(args.source_root, args.output)
