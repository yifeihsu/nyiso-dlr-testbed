"""Score one complete revised annual campaign under the sealed comparison contract.

Original physical terminals, frozen source axes, and comparison cohorts remain
fixed. A completed comparison does not certify physical meter assignments.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "output/nygrid_2025_ac_loss_revision/comparison"
FROZEN = ROOT / "output/nygrid_2025_acpf_profile_audit"
sys.path.insert(0, str(ROOT / "scripts/nygrid_2025_acpf_profile_audit/alignment"))
from interface_operator import CONVENTIONS, apply_interface_flows, build_runtime_operator, source_case

ZONES = list("ABCDEFGHIJK")
REGIONS = ["ISONE", "ONTARIO", "PJM"]
AXES = ["branch_keys", "branch_parent_row", "branch_from_bus", "branch_to_bus", "bus_id", "base_kv"]
NETWORK = ["PF", "PT", "QF", "QT", "Iseries", "Ifrom", "Ito", "VM", "VA", "PD", "QD", "bus_PG", "bus_QG",
           "branch_present", "branch_active", "bus_present", "DC_PF", "DC_PT", "DC_from_bus", "DC_to_bus"]
FLAGS = ["source_qualified", "PF_converged", "AC_equation_gate", "loss_allocation_gate", "reduction_and_equation_gate", "VQ_and_generator_assumption_gate"]
BUDGET_FIELDS = ["NY_gross_target_MW", "NY_served_PD_MW", "actual_budget_MW", "regional_import_target_MW", "regional_import_solved_MW", "external_PG_increment_MW"]
AUDIT_FIELDS = ["native_PG_change_from_original_MW", "HQ_PG_change_from_original_MW", "NY_gross_load_accounting_residual_MW",
                "regional_NY_import_residual_MW", "max_P_bound_violation_mw", "max_fixed_transfer_P_change_mw"]
EXTRA = ["external_gen_PG", "external_generator_rows_1based", "generator_bus_id"]
READ_FIELDS = ["hour_index", "timestamp_utc", "gamma", "impedance_mode", "loss_mode"] + AXES + NETWORK + FLAGS + BUDGET_FIELDS + AUDIT_FIELDS + EXTRA
VARIANT_OPTIONS = {
    "combined": ("released_equivalent", "boundary_consistent"),
    "loss_only": ("legacy_engineering", "boundary_consistent"),
    "impedance_only": ("released_equivalent", "legacy_single_slack"),
    "legacy_baseline_replay": ("legacy_engineering", "legacy_single_slack"),
}


def record(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=digest)


def enforce_receipts(entries):
    for item in entries:
        assert record(ROOT / item["path"])["sha256"] == item["sha256"], f"Changed frozen dependency: {item['path']}"


def vector(m, key, dtype=float):
    return np.asarray(m[key], dtype=dtype).reshape(-1)


def maxabs(a):
    a = np.asarray(a)
    assert np.isfinite(a).all()
    return float(np.max(np.abs(a), initial=0))


def region(area):
    return {1: "ISONE", 2: "NY", 3: "NY", 4: "ONTARIO", 5: "PJM", 6: "PJM"}[int(area)]


def physical_accounting_operators(m, state):
    """Independently rebuild loss ownership and NY-terminal boundary cuts."""
    parent = vector(m, "branch_parent_row", int)
    faxis = vector(m, "branch_from_bus", int); taxis = vector(m, "branch_to_bus", int)
    c, zones, _, _ = source_case(state)
    buses = c["bus"][:, 0].astype(int); lookup = {b: j for j, b in enumerate(buses)}
    owner = np.zeros((14, len(parent)))
    wf = np.zeros((3, len(parent))); wt = wf.copy()
    dc = np.zeros((3, len(vector(m, "DC_from_bus"))))
    for j, row in enumerate(c["branch"]):
        members = np.flatnonzero(parent == j + 1)
        assert len(members)
        f, t = (lookup[int(x)] for x in row[:2])
        rf, rt = region(c["bus"][f, 6]), region(c["bus"][t, 6])
        if rf == rt == "NY":
            owner[ZONES.index(str(zones[f])), members] += .5
            owner[ZONES.index(str(zones[t])), members] += .5
        elif rf == rt:
            owner[11 + REGIONS.index(rf), members] = 1
        else:
            assert "NY" in (rf, rt), "Inter-external tie requires a different boundary contract"
            ext = REGIONS.index(rt if rf == "NY" else rf)
            owner[11 + ext, members] = 1
            # Parent211 is replaced by two explicit lossless PAR transfers.
            if row[10] <= 0 or j == 210:
                continue
            first = members[faxis[members] == int(row[0])]
            last = members[taxis[members] == int(row[1])]
            assert len(first) == len(last) == 1
            if rf == "NY": wf[ext, first[0]] = -1
            else: wt[ext, last[0]] = -1
    for j, (fb, tb) in enumerate(zip(vector(m, "DC_from_bus", int), vector(m, "DC_to_bus", int))):
        assert region(c["bus"][lookup[tb], 6]) == "NY"
        dc[REGIONS.index(region(c["bus"][lookup[fb], 6])), j] = 1
    return owner, wf, wt, dc


def reconstruct(m, states, use, gamma, names):
    n = len(states)
    result = {c: np.full((n, 7), np.nan) for c in (*CONVENTIONS, "oriented_source_minus_target_loss")}
    budgets = np.full((n, 14), np.nan); imports = np.full((n, 3), np.nan)
    branch = np.column_stack((m["branch_from_bus"], m["branch_to_bus"]))
    parent = vector(m, "branch_parent_row", int)
    for state in np.unique(states):
        rows = np.flatnonzero((states == state) & use)
        if not len(rows): continue
        op = build_runtime_operator(branch, parent, str(state))
        assert op["interface_names"] == names
        active = np.asarray(m["branch_active"], bool)[rows]
        present = np.asarray(m["branch_present"], bool)[rows]
        for term in op["terms"]:
            members = parent == term["original_branch_row"]
            assert active[:, members].all() and present[:, members].all()
        pf = np.asarray(m["PF"])[rows]; pt = np.asarray(m["PT"])[rows]
        values = apply_interface_flows(pf, pt, op, gamma)
        for key, value in values.items(): result[key][rows] = value
        owner, wf, wt, dc = physical_accounting_operators(m, str(state))
        assert np.allclose(np.broadcast_to(owner.sum(axis=0), active.shape)[active], 1, atol=0, rtol=0)
        # Absent dated branches may contain NaN; they carry zero physical loss.
        losses = np.where(present & active, pf + pt, 0)
        assert np.isfinite(losses).all()
        budgets[rows] = losses @ owner.T
        imports[rows] = np.nan_to_num(pf) @ wf.T + np.nan_to_num(pt) @ wt.T + np.asarray(m["DC_PT"])[rows] @ dc.T
    return result, budgets, imports


def metric_rows(model, prediction, observed, names, cohort_name, mask, months, states, convention):
    rows = []
    periods = [("annual", mask)] + [(f"month_{j:02d}", mask & (months == j)) for j in range(1, 13)]
    periods += [("post_Dover", mask & (states == "post_dover"))]
    for period, use in periods:
        if not use.any(): continue
        assert np.isfinite(prediction[use]).all() and np.isfinite(observed[use]).all()
        for j, name in enumerate(names):
            e = prediction[use, j] - observed[use, j]
            denom = np.abs(observed[use, j]).sum()
            rows.append(dict(cohort=cohort_name, period=period, model=model, convention=convention,
                             interface=name, hours=int(use.sum()), mae_public_MW=float(np.abs(e).mean()),
                             rmse_public_MW=float(np.sqrt(np.square(e).mean())), bias_public_MW=float(e.mean()),
                             wape_percent=float(100 * np.abs(e).sum() / denom) if denom else np.nan,
                             diagnostic_only=True, physical_P32_meter_certified=False))
    return rows


def main(args):
    out = BASE / args.variant
    out.mkdir(parents=True, exist_ok=True)
    contract_path = BASE / "comparison_contract.json"
    contract = json.loads(contract_path.read_text())
    enforce_receipts(contract["source_receipts"])
    cohort_path = BASE / "frozen_comparison_cohort.csv"
    cohort = pd.read_csv(cohort_path)
    hours = cohort.hour_index.to_numpy(int); times = cohort.timestamp_utc.to_numpy(str)
    states = cohort.dated_state.to_numpy(str); source = cohort.frozen_source_qualified.to_numpy(bool)
    old_good = cohort.frozen_old_equation_profile_qualified.to_numpy(bool)
    months = pd.to_datetime(times, utc=True).tz_convert("America/New_York").month.to_numpy()
    gamma, names = float(contract["gamma"]), contract["interface_names"]
    tol = contract["comparison_tolerance_model_MW"]; target_tol = contract["source_target_tolerance_model_MW"]
    with np.load(FROZEN / "comparison/comparison_arrays.npz", allow_pickle=False) as old:
        observed = old["observed"].copy()
        reference = {c: old[c].copy() for c in (*CONVENTIONS, "oriented_source_minus_target_loss")}
    obs = pd.read_csv(ROOT / contract["public_observation_path"], float_precision="round_trip")
    assert np.array_equal(obs.hour_index, hours) and np.array_equal(obs.timestamp_utc, times)
    assert np.array_equal(obs[names].to_numpy(), observed, equal_nan=True)

    operating = loadmat(ROOT / "output/nygrid_2025_inputs/model/operating_inputs.mat", simplify_cells=True,
                        variable_names=["zone_names", "zonal_load_model_mw", "base_case"])
    baseline = loadmat(ROOT / "output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat", simplify_cells=True)
    share_path = ROOT / "output/nygrid_2025_western_audit/dispatch/all_boundary_external_generator_shares.csv"
    shares = pd.read_csv(share_path).sort_values("model_gen_row_1based")
    bus_registry_path = ROOT / "output/nygrid_2025_downstate/network/bus_register.csv"
    assert bus_registry_path.read_bytes() == subprocess.check_output(
        ["git", "show", contract["baseline_HEAD"] + ":" + bus_registry_path.relative_to(ROOT).as_posix()], cwd=ROOT
    ), "Bus accounting-zone registry differs from the frozen baseline"
    register = pd.read_csv(bus_registry_path, keep_default_na=False)
    assert list(operating["zone_names"]) == ZONES and list(baseline["region_labels"]) == REGIONS + ["HQ"]
    assert np.array_equal(baseline["hour_index"], hours) and np.array_equal(baseline["timestamp_utc"].astype(str), times)
    ext_rows = shares.model_gen_row_1based.to_numpy(int)
    assert np.array_equal(ext_rows, baseline["external_generator_rows_1based"])
    native_rows = np.asarray(baseline["native_generator_rows_1based"], int) - 1
    source_pg = np.asarray(baseline["gen_pg"])
    landing_path = ROOT / "output/nygrid_2025_western_audit/replay/dated_combined.mat"
    assert landing_path.read_bytes() == subprocess.check_output(
        ["git", "show", contract["baseline_HEAD"] + ":" + landing_path.relative_to(ROOT).as_posix()], cwd=ROOT
    ), "Corrected generator landing source differs from the frozen baseline"
    gen_bus = np.asarray(loadmat(landing_path, simplify_cells=True, variable_names=["corrected_generator_buses"])["corrected_generator_buses"], int)
    assert len(gen_bus) == source_pg.shape[1] == 1464
    originals = shares.parent_gen_row.to_numpy(int) - 1
    caps = np.asarray(operating["base_case"]["gen"])[originals]
    assert np.array_equal(caps[:, 0].astype(int), shares.bus_id.to_numpy(int))
    HQ_column = int(np.flatnonzero(shares.region.to_numpy() == "HQ")[0])

    receipt = json.loads(args.annual_receipt.read_text())
    assert receipt.get("completed") is True, "Annual producer receipt not complete"
    options = receipt["options"]
    declared = VARIANT_OPTIONS[args.variant]
    assert (options["impedance_mode"], options["loss_mode"]) == declared, "Variant label conflicts with producer options"
    assert args.loss_mode == declared[1], "Requested loss-mode conflicts with declared variant"
    files = sorted(args.monthly.glob("profile_PF_2025_*.mat"))
    assert len(files) == 12, "Require twelve completed monthly exports"
    result = {c: np.full((8760, 7), np.nan) for c in (*CONVENTIONS, "oriented_source_minus_target_loss")}
    seen = np.zeros(8760, bool); good = seen.copy(); operating_good = seen.copy()
    flag_arrays = {f: seen.copy() for f in FLAGS}
    accounting = {k: np.full(8760, np.nan) for k in [
        "NY_gross_target_error_MW", "NY_gross_load_closure_MW", "NY_served_export_error_MW", "loss_budget_reconstruction_error_MW",
        "regional_source_target_error_MW", "regional_import_reconstruction_error_MW", "regional_import_target_error_MW",
        "native_PG_delta_MW", "native_bus_PG_delta_MW", "HQ_PG_delta_MW", "external_P_bound_violation_MW",
        "external_increment_reconstruction_error_MW", "external_loss_budget_error_MW", "controlled_transfer_P_delta_MW",
        "delivered_PD_share_and_external_profile_error_MW", "QD_power_factor_and_external_profile_error_MVAr",
        "maximum_NY_zonal_loss_fraction", "minimum_NY_served_fraction", "global_generation_demand_loss_residual_MW"]}
    zonal_losses = np.full((8760, 11), np.nan); served = zonal_losses.copy()
    targets = np.asarray(operating["zonal_load_model_mw"])
    imported = np.full((8760, 3), np.nan)
    import_target = baseline["actual_regional_import_public_mw"][:, :3] * gamma
    old_imported = np.full((8760, 3), np.nan)
    canonical = None; frozen_months = []
    for path in files:
        m = loadmat(path, simplify_cells=True, variable_names=READ_FIELDS)
        assert set(READ_FIELDS) <= set(m), f"Missing fields in {path.name}: {sorted(set(READ_FIELDS)-set(m))}"
        h = vector(m, "hour_index", int); ix = h - 1
        assert len(np.unique(ix)) == len(ix) and np.all((ix >= 0) & (ix < 8760)) and not seen[ix].any()
        assert np.array_equal(vector(m, "timestamp_utc", str), times[ix]) and float(m["gamma"]) == gamma
        assert np.array_equal(vector(m, "source_qualified", bool), source[ix])
        assert np.array_equal(vector(m, "generator_bus_id", int), gen_bus), "Revised generator landing differs from the corrected frozen profile"
        assert (str(m["impedance_mode"]), str(m["loss_mode"])) == declared, "Monthly options differ from annual receipt"
        month = np.unique(months[ix]); assert len(month) == 1
        frozen_path = FROZEN / f"acpf/monthly/profile_PF_2025_{month[0]:02d}.mat"
        d = loadmat(frozen_path, simplify_cells=True, variable_names=["hour_index", "timestamp_utc", "gamma"] + AXES + NETWORK + ["source_qualified", "AC_equation_gate", "P_profile_preservation_gate"])
        frozen_months.append(frozen_path)
        assert np.array_equal(vector(d, "hour_index", int), h)
        if canonical is None: canonical = {a: vector(m, a).copy() if a != "branch_keys" else vector(m, a, str) for a in AXES}
        for axis in AXES:
            dtype = str if axis == "branch_keys" else float
            assert np.array_equal(vector(m, axis, dtype), canonical[axis])
            assert np.array_equal(vector(d, axis, dtype), canonical[axis])
        assert len(canonical["bus_id"]) == 267 and len(canonical["branch_keys"]) == 488
        use = source[ix] & vector(m, "PF_converged", bool) & vector(m, "AC_equation_gate", bool) & vector(m, "reduction_and_equation_gate", bool)
        if args.loss_mode == "boundary_consistent": use &= vector(m, "loss_allocation_gate", bool)
        frozen_use = source[ix] & vector(d, "AC_equation_gate", bool) & vector(d, "P_profile_preservation_gate", bool)
        assert np.array_equal(frozen_use, old_good[ix])
        for mask_name in ["bus_present", "branch_present", "branch_active"]:
            assert np.array_equal(np.asarray(m[mask_name], bool)[use], np.asarray(d[mask_name], bool)[use]), f"Changed dated topology: {mask_name}"
        for dc_axis in ["DC_from_bus", "DC_to_bus"]:
            assert np.array_equal(vector(m, dc_axis, int), vector(d, dc_axis, int)), f"Changed controlled-transfer terminal: {dc_axis}"
        values, reconstructed_budget, regional_imports = reconstruct(m, states[ix], use, gamma, names)
        old_values, _, old_imports = reconstruct(d, states[ix], frozen_use, gamma, names)
        for convention in CONVENTIONS:
            assert maxabs(old_values[convention][frozen_use] - reference[convention][ix[frozen_use]]) < contract["terminal_recompute_tolerance_public_MW"]
        for key in result: result[key][ix] = values[key]
        old_imported[ix] = old_imports
        good[ix] = use; operating_good[ix] = use & vector(m, "VQ_and_generator_assumption_gate", bool)
        for flag in FLAGS: flag_arrays[flag][ix] = vector(m, flag, bool)
        seen[ix] = True
        if not use.any(): continue
        take = ix[use]
        bus_present = np.asarray(m["bus_present"], bool)[use]
        for field in ["PD", "QD", "bus_PG"]:
            assert np.isfinite(np.asarray(m[field])[use][bus_present]).all(), f"Nonfinite active bus {field}"
        assert np.array_equal(vector(m, "external_generator_rows_1based", int), ext_rows)
        ext_pg = np.asarray(m["external_gen_PG"])[use]
        assert ext_pg.shape == (len(take), 28)
        native_bus_expected = np.zeros((len(take), 267))
        for g in native_rows:
            native_bus_expected[:, np.flatnonzero(canonical["bus_id"] == gen_bus[g])[0]] += source_pg[take, g]
        exported_bus_pg = np.nan_to_num(np.asarray(m["bus_PG"])[use]).copy()
        for j, bid in enumerate(shares.bus_id):
            exported_bus_pg[:, np.flatnonzero(canonical["bus_id"] == bid)[0]] -= ext_pg[:, j]
        pd_full = np.asarray(m["PD"])[use]
        zonal = np.column_stack([np.nansum(pd_full[:, np.isin(canonical["bus_id"], register.loc[register.accounting_zone == z, "model_bus"])], axis=1) for z in ZONES])
        expected_pd = np.asarray(d["PD"])[use].copy()
        expected_qd = np.asarray(d["QD"])[use].copy()
        for j, zone in enumerate(ZONES):
            buses = np.isin(canonical["bus_id"], register.loc[register.accounting_zone == zone, "model_bus"])
            assert maxabs(np.nansum(expected_pd[:, buses], axis=1) - targets[take, j]) < target_tol
            ratio = zonal[:, j] / targets[take, j]
            expected_pd[:, buses] *= ratio[:, None]
            expected_qd[:, buses] *= ratio[:, None]
        pd_profile_error = np.where(bus_present, pd_full - expected_pd, 0)
        qd_profile_error = np.where(bus_present, np.asarray(m["QD"])[use] - expected_qd, 0)
        ext_increment = np.column_stack([(ext_pg - source_pg[take][:, ext_rows - 1])[:, shares.region.to_numpy() == r].sum(axis=1) for r in REGIONS])
        hourly = {
            "NY_gross_target_error_MW": np.max(np.abs(np.asarray(m["NY_gross_target_MW"])[use] - targets[take]), axis=1),
            "NY_gross_load_closure_MW": np.max(np.abs(zonal + reconstructed_budget[use, :11] - targets[take]), axis=1),
            "NY_served_export_error_MW": np.max(np.abs(zonal - np.asarray(m["NY_served_PD_MW"])[use]), axis=1),
            "loss_budget_reconstruction_error_MW": np.max(np.abs(reconstructed_budget[use] - np.asarray(m["actual_budget_MW"])[use]), axis=1),
            "regional_source_target_error_MW": np.max(np.abs(np.asarray(m["regional_import_target_MW"])[use] - import_target[take]), axis=1),
            "regional_import_reconstruction_error_MW": np.max(np.abs(regional_imports[use] - np.asarray(m["regional_import_solved_MW"])[use]), axis=1),
            "regional_import_target_error_MW": np.max(np.abs(regional_imports[use] - import_target[take]), axis=1),
            "native_PG_delta_MW": np.abs(vector(m, "native_PG_change_from_original_MW")[use]),
            "native_bus_PG_delta_MW": np.max(np.abs(exported_bus_pg - native_bus_expected), axis=1),
            "HQ_PG_delta_MW": np.abs(ext_pg[:, HQ_column] - source_pg[take, ext_rows[HQ_column] - 1]),
            "external_P_bound_violation_MW": np.maximum(0, np.maximum(caps[:, 9] - ext_pg, ext_pg - caps[:, 8])).max(axis=1),
            "external_increment_reconstruction_error_MW": np.max(np.abs(ext_increment - np.asarray(m["external_PG_increment_MW"])[use]), axis=1),
            "external_loss_budget_error_MW": np.max(np.abs(ext_increment - reconstructed_budget[use, 11:]), axis=1),
            "controlled_transfer_P_delta_MW": np.maximum(np.max(np.abs(np.asarray(m["DC_PF"])[use] - np.asarray(d["DC_PF"])[use]), axis=1), np.max(np.abs(np.asarray(m["DC_PT"])[use] - np.asarray(d["DC_PT"])[use]), axis=1)),
            "delivered_PD_share_and_external_profile_error_MW": np.max(np.abs(pd_profile_error), axis=1),
            "QD_power_factor_and_external_profile_error_MVAr": np.max(np.abs(qd_profile_error), axis=1),
            "maximum_NY_zonal_loss_fraction": np.max(reconstructed_budget[use, :11] / targets[take], axis=1),
            "minimum_NY_served_fraction": np.min(zonal / targets[take], axis=1),
            "global_generation_demand_loss_residual_MW": np.abs(np.nansum(np.asarray(m["bus_PG"])[use] - pd_full, axis=1) - reconstructed_budget[use].sum(axis=1)),
        }
        for key, a in hourly.items():
            assert np.isfinite(a).all(), key
            accounting[key][take] = a
        # The impedance-only legacy ablation deliberately violates active-loss
        # accounting; preserve those discrepancies without calling it qualified.
        invariants = ["NY_gross_target_error_MW", "NY_served_export_error_MW", "loss_budget_reconstruction_error_MW", "regional_source_target_error_MW", "regional_import_reconstruction_error_MW", "HQ_PG_delta_MW", "external_increment_reconstruction_error_MW", "controlled_transfer_P_delta_MW", "global_generation_demand_loss_residual_MW", "delivered_PD_share_and_external_profile_error_MW", "QD_power_factor_and_external_profile_error_MVAr"]
        if args.loss_mode == "boundary_consistent":
            invariants += ["NY_gross_load_closure_MW", "regional_import_target_error_MW", "native_PG_delta_MW", "native_bus_PG_delta_MW", "external_P_bound_violation_MW", "external_loss_budget_error_MW"]
            assert np.all(zonal >= 0) and np.all(hourly["minimum_NY_served_fraction"] > 0)
        for key in invariants:
            threshold = target_tol if key in ["NY_gross_target_error_MW", "regional_source_target_error_MW", "HQ_PG_delta_MW", "controlled_transfer_P_delta_MW"] else tol
            assert maxabs(hourly[key]) < threshold, f"{args.variant}/{path.name}/{key}: {maxabs(hourly[key])}"
        assert maxabs(np.abs(vector(m, "HQ_PG_change_from_original_MW")[use]) - hourly["HQ_PG_delta_MW"]) < target_tol
        assert maxabs(vector(m, "NY_gross_load_accounting_residual_MW")[use] - hourly["NY_gross_load_closure_MW"]) < tol
        assert maxabs(vector(m, "regional_NY_import_residual_MW")[use] - hourly["regional_import_target_error_MW"]) < tol
        served[take] = zonal; zonal_losses[take] = reconstructed_budget[use, :11]; imported[take] = regional_imports[use]
    assert seen.all(), "Annual export omits hour positions"
    assert int(good.sum()) == receipt["policy_equation_qualified_hours"], "Scorer/producer qualified masks disagree"
    paired = old_good & good; new = good & ~old_good; lost = old_good & ~good
    assert paired.any()
    rows = []
    for convention in CONVENTIONS:
        for cohort_name, mask in [("paired_frozen_old", paired), ("revised_all_qualified", good), ("revised_only_success", new)]:
            rows += metric_rows(args.variant, result[convention], observed, names, cohort_name, mask, months, states, convention)
            if cohort_name == "paired_frozen_old":
                rows += metric_rows("frozen_old", reference[convention], observed, names, cohort_name, mask, months, states, convention)
        rows += metric_rows("frozen_old", reference[convention], observed, names, "frozen_old_all8494", old_good, months, states, convention)
        rows += metric_rows("frozen_old", reference[convention], observed, names, "frozen_old_success_lost", lost, months, states, convention)
    pd.DataFrame(rows).to_csv(out / "public_interface_metrics.csv", index=False, lineterminator="\n")
    coverage = cohort.copy()
    for flag, a in flag_arrays.items(): coverage["revised_" + flag] = a
    coverage["revised_comparison_qualified"] = good; coverage["paired_frozen_old_qualified"] = paired
    coverage["revised_only_success"] = new; coverage["frozen_old_success_lost"] = lost
    coverage["revised_operating_qualified"] = operating_good
    coverage.to_csv(out / "comparison_cohort.csv", index=False, lineterminator="\n")
    pd.DataFrame({"hour_index": hours, "timestamp_utc": times, "revised_comparison_qualified": good, **accounting}).to_csv(out / "hourly_source_accounting.csv", index=False, lineterminator="\n")
    load_rows = []
    for j, z in enumerate(ZONES):
        fractions = zonal_losses[good, j] / targets[good, j]
        load_rows.append(dict(zone=z, hours=int(good.sum()), maximum_gross_target_closure_model_MW=maxabs(served[good, j] + zonal_losses[good, j] - targets[good, j]),
                              mean_allocated_loss_model_MW=float(zonal_losses[good, j].mean()), maximum_allocated_loss_model_MW=float(zonal_losses[good, j].max()),
                              minimum_served_PD_model_MW=float(served[good, j].min()), minimum_served_fraction=float((served[good, j] / targets[good, j]).min()),
                              maximum_loss_fraction=float(fractions.max()), hours_loss_fraction_over25percent=int((fractions > .25).sum()),
                              load_closure_is_construction_constraint=True, actual_zonal_losses_observed=False))
    pd.DataFrame(load_rows).to_csv(out / "NY_zonal_loss_accounting.csv", index=False, lineterminator="\n")
    region_rows = []
    for cohort_name, mask in [("paired_frozen_old", paired), ("revised_all_qualified", good), ("revised_only_success", new)]:
        if not mask.any(): continue
        for j, reg in enumerate(REGIONS):
            models = [(args.variant, imported)] + ([("frozen_old", old_imported)] if cohort_name == "paired_frozen_old" else [])
            for label, pred in models:
                err = pred[mask, j] - import_target[mask, j]
                region_rows.append(dict(region=reg, cohort=cohort_name, model=label, hours=int(mask.sum()),
                                        maximum_absolute_error_model_MW=maxabs(err), MAE_model_MW=float(np.abs(err).mean()),
                                        MAE_public_MW=float(np.abs(err).mean() / gamma), bias_public_MW=float(err.mean() / gamma)))
    pd.DataFrame(region_rows).to_csv(out / "regional_NY_terminal_import_errors.csv", index=False, lineterminator="\n")
    np.savez_compressed(out / "comparison_arrays.npz", hour_index=hours, timestamp_utc=times, interface_names=np.array(names), gamma=gamma,
                        source_qualified=source, frozen_old_qualified=old_good, revised_qualified=good, paired_qualified=paired, revised_only_success=new,
                        frozen_old_success_lost=lost, operating_qualified=operating_good, observed=observed,
                        NY_gross_target_MW=targets, NY_served_PD_MW=served, NY_allocated_loss_MW=zonal_losses,
                        regional_import_target_MW=import_target, regional_import_solved_MW=imported, old_regional_import_solved_MW=old_imported,
                        **{"revised_" + c: a for c, a in result.items()}, **{"old_" + c: a for c, a in reference.items()})
    enforce_receipts(contract["source_receipts"])
    outputs = [out / p for p in ["public_interface_metrics.csv", "comparison_cohort.csv", "hourly_source_accounting.csv", "NY_zonal_loss_accounting.csv", "regional_NY_terminal_import_errors.csv", "comparison_arrays.npz"]]
    summary = dict(passed=True, comparison_complete=True, created_utc=datetime.now(timezone.utc).isoformat(), variant=args.variant, loss_mode=args.loss_mode,
                   revised_results_are_declared_synthetic_equivalent=True, physical_parameter_verification=False,
                   source_qualified_hours=int(source.sum()), frozen_old_qualified_hours=int(old_good.sum()), revised_qualified_hours=int(good.sum()),
                   paired_qualified_hours=int(paired.sum()), revised_only_success_hours=int(new.sum()), frozen_old_success_lost_hours=int(lost.sum()),
                   revised_operating_qualified_hours=int(operating_good.sum()),
                   loss_policy_qualified_hours=int(np.sum(good & flag_arrays["loss_allocation_gate"])),
                   maximum_source_accounting_errors={k: float(np.nanmax(v[good])) for k, v in accounting.items() if not k.endswith("fraction")},
                   maximum_NY_zonal_loss_fraction=float(np.nanmax(accounting["maximum_NY_zonal_loss_fraction"][good])),
                   minimum_NY_served_fraction=float(np.nanmin(accounting["minimum_NY_served_fraction"][good])),
                   qualification_frozen_before_revised_inspection=True, internal_interface_fitting_performed=False,
                   original_three_terminal_operators_reused=True, current_gamma_division_applied=False,
                   legacy_impedance_ablation_is_policy_qualified=args.loss_mode != "legacy_single_slack",
                   export_contract_adaptation="Added external28 PG/row-axis, corrected generator-bus axis and HQ delta; all originally sealed cohorts, operators, and tolerances retained.",
                   dependencies=[record(p) for p in [Path(__file__), contract_path, cohort_path, args.annual_receipt, bus_registry_path, share_path, landing_path] + files + frozen_months],
                   outputs=[record(p) for p in outputs])
    (out / "scoring_receipt.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ["passed", "variant", "revised_qualified_hours", "paired_qualified_hours", "revised_only_success_hours", "frozen_old_success_lost_hours"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--monthly", type=Path, required=True)
    parser.add_argument("--annual-receipt", type=Path, required=True)
    parser.add_argument("--variant", choices=list(VARIANT_OPTIONS), required=True)
    parser.add_argument("--loss-mode", choices=["boundary_consistent", "legacy_single_slack"], default="boundary_consistent")
    arguments = parser.parse_args()
    arguments.monthly = arguments.monthly.resolve(); arguments.annual_receipt = arguments.annual_receipt.resolve()
    main(arguments)
