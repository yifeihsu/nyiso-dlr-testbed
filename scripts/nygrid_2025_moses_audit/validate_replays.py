"""Independent annual numerical gate for eight Moses audit replay variants.

No production power-flow, phase-response, interface, or scoring helper is
imported. All-hour branch laws and KCL use the frozen input arrays directly.
Representative states are independently solved, with a bordered system for a
PAR target. Only the new annual validation receipt is written.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_moses_audit"
DEST = OUT / "validation/annual_validation.json"
CHECKS: list[dict] = []
INPUTS: dict[str, str] = {}
TOL = 1e-7
NAMES = ["DYSINGER EAST", "WEST CENTRAL", "TOTAL EAST", "MOSES SOUTH",
         "CENTRAL EAST - VC", "UPNY CONED", "SPR/DUN-SOUTH"]
PAIRS = [("A", "B"), ("B", "C"), ("ABCDE", "FGHIJK"), ("D", "E"),
         ("E", "F"), ("ABCDEFG", "HIJK"), ("I", "J")]


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source(relative: str) -> Path:
    path = ROOT / relative
    value = sha(path)
    if relative in INPUTS and INPUTS[relative] != value:
        raise AssertionError("Input changed during validation: " + relative)
    INPUTS[relative] = value
    return path


def csv(relative: str) -> pd.DataFrame:
    return pd.read_csv(source(relative), keep_default_na=False)


def mat(relative: str, variables=None) -> dict:
    return loadmat(source(relative), simplify_cells=True, variable_names=variables)


def check(name: str, condition: bool, detail="", maximum_error=None) -> None:
    record = dict(check=name, passed=bool(condition), detail=detail)
    if maximum_error is not None:
        record["maximum_absolute_error"] = float(maximum_error)
    CHECKS.append(record)
    if not condition:
        raise AssertionError(name + ": " + str(detail))


def close(name, a, b, tol=TOL, relative=0.) -> float:
    a, b = np.asarray(a), np.asarray(b)
    valid_shape = a.shape == b.shape
    check(name + "_shape", valid_shape, f"{a.shape} versus {b.shape}")
    check(name + "_missingness", np.array_equal(np.isnan(a), np.isnan(b)))
    finite = np.isfinite(a) & np.isfinite(b)
    check(name + "_finite_pattern", np.array_equal(np.isfinite(a), np.isfinite(b)))
    error = float(np.max(np.abs(a[finite] - b[finite]), initial=0))
    allowed = tol + relative * np.abs(b[finite])
    check(name, bool(np.all(np.abs(a[finite] - b[finite]) <= allowed)),
          f"absolute tolerance {tol:g}; relative tolerance {relative:g}", error)
    return error


def geometry(case: dict) -> dict:
    bus, branch = np.asarray(case["bus"]), np.asarray(case["branch"])
    ids = bus[:, 0].astype(int)
    index = {b: i for i, b in enumerate(ids)}
    f = np.array([index[int(v)] for v in branch[:, 0]])
    t = np.array([index[int(v)] for v in branch[:, 1]])
    tap = np.where(branch[:, 8] == 0, 1., branch[:, 8])
    k = np.zeros(len(branch))
    active = branch[:, 10] == 1
    k[active] = float(case["baseMVA"]) / (branch[active, 3] * tap[active])
    c = np.zeros((len(branch), len(bus)))
    c[np.arange(len(branch)), f] = 1
    c[np.arange(len(branch)), t] -= 1
    return dict(bus=bus, branch=branch, ids=ids, index=index, f=f, t=t, k=k, C=c)


def injections(case, gen_buses, pg, pd_values, dc_values, geo):
    result = -pd_values.copy() - geo["bus"][:, 4]
    status = np.asarray(case["gen"])[:, 7]
    for bus in np.unique(gen_buses):
        selected = gen_buses == bus
        result[:, geo["index"][int(bus)]] += (pg[:, selected] * status[selected]).sum(axis=1)
    for j, row in enumerate(np.atleast_2d(case["dcline"])):
        if row[2]:
            result[:, geo["index"][int(row[0])]] -= dc_values[:, j]
            result[:, geo["index"][int(row[1])]] += dc_values[:, j]
    return result


def exits(flow, geo):
    result = np.zeros((len(flow), len(geo["ids"])))
    for j, (a, b) in enumerate(zip(geo["f"], geo["t"])):
        result[:, a] += flow[:, j]
        result[:, b] -= flow[:, j]
    return result


def state_labels(times, topology):
    if topology == "year_end":
        return np.full(len(times), "refined_2025_case", object)
    states = np.full(len(times), "refined_2025_pre_may_case", object)
    for time, label in [("2025-05-21T04:00:00Z", "refined_2025_may21_case"),
                        ("2025-05-30T04:00:00Z", "refined_2025_may30_case"),
                        ("2025-12-20T04:00:00Z", "refined_2025_case")]:
        states[times >= time] = label
    return states


def independent_solve(case, injection, reference_bus, target=None):
    """Solve from elementary incidence equations, with no production helper."""
    geo = geometry(case)
    c, k = geo["C"], geo["k"]
    ref = geo["index"][int(reference_bus)]
    keep = np.delete(np.arange(len(geo["ids"])), ref)
    b = c.T @ (k[:, None] * c)
    phase = np.deg2rad(geo["branch"][:, 9].copy())
    if target is None:
        offset = -k * phase
        theta = np.zeros(len(keep) + 1)
        theta[keep] = np.linalg.solve(b[np.ix_(keep, keep)], (injection - c.T @ offset)[keep])
    else:
        phase[210] = 0.
        offset = -k * phase
        a = np.zeros((len(keep) + 1, len(keep) + 1))
        a[:-1, :-1] = b[np.ix_(keep, keep)]
        a[:-1, -1] = -k[210] * c[210, keep]
        a[-1, :-1] = k[210] * c[210, keep]
        a[-1, -1] = -k[210]
        answer = np.linalg.solve(a, np.r_[(injection - c.T @ offset)[keep], target])
        theta = np.zeros(len(keep) + 1)
        theta[keep], phase[210] = answer[:-1], answer[-1]
    return k * (c @ theta - phase), np.rad2deg(theta), float(np.rad2deg(phase[210]))


def main():
    started = datetime.now(timezone.utc).isoformat()
    receipt = json.loads(source("output/nygrid_2025_moses_audit/replay/provenance.json").read_text())
    for r in receipt["dependencies"]:
        check("replay_dependency_" + r["path"], sha(source(r["path"])) == r["sha256"])
    repair = json.loads(source("output/nygrid_2025_moses_audit/corrected/fleet/repair_receipt.json").read_text())
    for p, h in repair["source_hashes"].items():
        check("repair_frozen_source_" + p, sha(source(p)) == h)
    dispatch = mat("output/nygrid_2025_dispatch/dispatch/dispatch.mat")
    bounds = mat("output/nygrid_2025_dispatch/dispatch/dispatch_bounds.mat")
    priors = mat("output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat")
    slim = mat("output/nygrid_2025_slim/network/network_cases.mat")
    full = mat("output/nygrid_2025_downstate/network/network_cases.mat")
    original = csv("output/nygrid_2025_dispatch/dispatch/model_generator_register.csv")
    corrected = csv("output/nygrid_2025_moses_audit/corrected/model_generator_register.csv")
    fleet = csv("output/nygrid_2025_moses_audit/corrected/fleet/fleet_register.csv").set_index("fleet_id")
    par = csv("output/nygrid_2025_moses_audit/exchanges/par_stlawrence_hourly_2025.csv")
    obs = csv("output/nygrid_2025_inputs/load_source/interface_wide.csv")
    scores = csv("output/nygrid_2025_moses_audit/comparison/interface_summary.csv")
    monthly = csv("output/nygrid_2025_moses_audit/comparison/interface_monthly.csv")
    times = np.asarray(dispatch["timestamp_utc"]).astype(str)
    q = np.asarray(dispatch["dispatch_qualified"], bool)
    cq = par.coverage_qualified.astype(str).str.lower().eq("true").to_numpy()
    common = q & cq
    check("base_hours_8760", len(times) == 8760 and np.array_equal(dispatch["hour_index"], np.arange(1, 8761)))
    check("base_cohort_8663", q.sum() == 8663)
    check("P34_qualified_8673", cq.sum() == 8673)
    check("common_cohort_8663", common.sum() == 8663)
    check("P34_UTC_axis", pd.DatetimeIndex(pd.to_datetime(par.timestamp_utc, utc=True)).equals(pd.DatetimeIndex(pd.to_datetime(times, utc=True))))
    check("observation_UTC_axis", np.array_equal(obs.timestamp_utc.astype(str), times))
    raw = pd.to_numeric(par.combined_raw_mw, errors="coerce").to_numpy(float)
    parts = par[["PS33_raw_mw", "PS34_raw_mw"]].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    close("P34_target_equals_two_raw_channels", raw[cq], parts[cq].sum(axis=1), tol=1e-10)
    y = obs[NAMES].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    check("observed_all7_finite_on_common", np.isfinite(y[common]).all())
    check("all8_variant_plan", len(receipt["variants"]) == 8 and len({r["variant"] for r in receipt["variants"]}) == 8)
    check("112_annual_scores_unique", len(scores) == 112 and not scores.duplicated(["variant", "cohort", "interface"]).any())
    check("1344_monthly_scores_unique", len(monthly) == 1344 and not monthly.duplicated(["variant", "cohort", "month", "interface"]).any())
    check("register_row_order", np.array_equal(original.gen_row, corrected.gen_row))
    expected_buses = original.bus_id.to_numpy(int).copy()
    native = original.role.eq("native").to_numpy()
    expected_buses[native] = fleet.loc[original.loc[native, "fleet_id"].astype(int), "bus_id"].to_numpy(int)
    check("corrected_buses_from_fleet_ID_join", np.array_equal(corrected.bus_id.to_numpy(int), expected_buses))
    moved = expected_buses != original.bus_id.to_numpy(int)
    check("46_admitted_rows_moved_only_native", moved.sum() == 46 and np.all(native[moved]))
    check("non_mapping_register_fields_preserved", original.drop(columns=["bus_id", "zone", "mapping_method"]).equals(corrected.drop(columns=["bus_id", "zone", "mapping_method"])))
    pg, dc = np.asarray(dispatch["gen_pg"]), np.asarray(dispatch["dc_pf"])
    gamma = float(dispatch["gamma"])
    check("scale_consistent", gamma == float(slim["gamma"]) == float(full["gamma"]))
    nn = int(native.sum())
    check("native_order_and_count", nn == 1436 and native[:nn].all() and not native[nn:].any())
    max_bound, max_kkt, max_sum, max_objective = 0., 0., 0., 0.
    for ix in np.array_split(np.flatnonzero(q), 70):
        p, lo, hi = pg[ix], bounds["gen_pmin"][ix], bounds["gen_pmax"][ix]
        max_bound = max(max_bound, float(np.max(np.maximum(lo - p, p - hi), initial=0)))
        w, p0 = priors["objective_weights"][ix], priors["prior_pg"][ix, :nn]
        check("positive_objective_weights_block_" + str(ix[0]), np.isfinite(w).all() and np.all(w > 0))
        opt = np.clip(p0 + dispatch["dual_lambda"][ix, None] / w, lo[:, :nn], hi[:, :nn])
        max_kkt = max(max_kkt, float(np.max(abs(opt - p[:, :nn]))))
        max_sum = max(max_sum, float(np.max(abs(p[:, :nn].sum(axis=1) - dispatch["native_required_pg"][ix]))))
        objective = .5 * np.sum(w * (p[:, :nn] - p0) ** 2, axis=1)
        max_objective = max(max_objective, float(np.max(abs(objective - dispatch["objective_value"][ix]))))
    check("all_qualified_PG_within_frozen_bounds", max_bound < TOL, maximum_error=max_bound)
    check("all_native_KKT_projection", max_kkt < TOL, maximum_error=max_kkt)
    check("all_native_global_balance", max_sum < TOL, maximum_error=max_sum)
    check("saved_objective_recomputed", max_objective < 1e-7, maximum_error=max_objective)
    month_ids = pd.to_datetime(times, utc=True).tz_convert("America/New_York").month.to_numpy()
    zones = dict(zip(np.asarray(full["bus_ids"], int), np.asarray(full["bus_zones"]).astype(str)))
    variants = []
    for item in receipt["variants"]:
        name = item["variant"]
        path = source(item["file"])
        check(name + "_recorded_hash", sha(path) == item["sha256"])
        data = loadmat(path, simplify_cells=True)
        mask = q if not item["par_controlled"] else common
        gen_buses = expected_buses if item["source_generation_mapping_corrected"] else original.bus_id.to_numpy(int)
        states = state_labels(times, item["topology"])
        check(name + "_cohort", np.array_equal(data["qualified"].astype(bool), mask))
        check(name + "_hours_and_times", np.array_equal(data["hour_index"], np.arange(1, 8761)) and np.array_equal(np.asarray(data["timestamp_utc"]).astype(str), times))
        check(name + "_network_chronology", np.array_equal(np.asarray(data["network_state_ids"]).astype(str), states))
        check(name + "_generator_terminal_identity", np.array_equal(data["corrected_generator_buses"], gen_buses))
        check(name + "_same_gamma", float(data["gamma"]) == gamma)
        check(name + "_branch211_record", int(data["source_control_branch_row"]) == 211)
        check(name + "_PAR_unpromoted", item["par_orientation_is_promoted"] is False)
        for field in ["branch_pf", "bus_va", "interface_pf", "equivalent_shift_deg"]:
            check(name + "_qualified_finite_" + field, np.isfinite(data[field][mask]).all())
            check(name + "_unqualified_NaN_" + field, np.isnan(data[field][~mask]).all())
        if item["par_controlled"]:
            check(name + "_sign_metadata", float(data["raw_PAR_to_branch_sign"]) == item["raw_PAR_to_branch_sign"])
            close(name + "_all_P34_targets", data["branch_pf"][mask, 210], raw[mask] * gamma * item["raw_PAR_to_branch_sign"])
        else:
            check(name + "_no_PAR_sign_metadata", np.isnan(data["raw_PAR_to_branch_sign"]))
        max_law, max_kcl, max_full_kcl, max_recovery = 0., 0., 0., 0.
        sample_hours = {int(np.flatnonzero(mask)[0]), int(np.flatnonzero(mask)[-1]), int(np.nanargmax(abs(data["equivalent_shift_deg"])))}
        representative = []
        for state in sorted(set(states)):
            ix = np.flatnonzero(mask & (states == state))
            if not len(ix):
                continue
            sample_hours.add(int(ix[0]))
            case, fullcase = slim[state], full[state]
            geo, fg = geometry(case), geometry(fullcase)
            check(name + state + "_control_retained_endpoints", np.array_equal(geo["branch"][210, :2], [48, 100]) and np.array_equal(fg["branch"][210, :2], [48, 100]))
            check(name + state + "_lossless_DClinks", np.all(np.atleast_2d(case["dcline"])[:, 15:17] == 0))
            theta = np.deg2rad(data["bus_va"][ix])
            phase = np.broadcast_to(np.deg2rad(geo["branch"][:, 9]), (len(ix), len(geo["branch"]))).copy()
            phase[:, 210] = np.deg2rad(data["equivalent_shift_deg"][ix])
            expected_flow = geo["k"] * (theta[:, geo["f"]] - theta[:, geo["t"]] - phase)
            max_law = max(max_law, close(name + state + "_native_branch_laws", data["branch_pf"][ix], expected_flow))
            loads = np.pad(dispatch["bus_pd"][ix], ((0, 0), (0, 8)))
            injection = injections(case, gen_buses, pg[ix], loads, dc[ix], geo)
            max_kcl = max(max_kcl, close(name + state + "_native_KCL", exits(data["branch_pf"][ix], geo), injection))
            rec = slim["recovery"][state.removesuffix("_case")]
            lifted = theta @ np.asarray(rec["angle_lift"]).T + rec["angle_offset"]
            fphase = np.broadcast_to(np.deg2rad(fg["branch"][:, 9]), (len(ix), len(fg["branch"]))).copy()
            fphase[:, 210] = np.deg2rad(data["equivalent_shift_deg"][ix])
            fflow = fg["k"] * (lifted[:, fg["f"]] - lifted[:, fg["t"]] - fphase)
            op = np.zeros((7, len(fg["branch"])))
            for j, (left, right) in enumerate(PAIRS):
                for z, branch in enumerate(fg["branch"]):
                    a, b = zones[int(branch[0])], zones[int(branch[1])]
                    op[j, z] = branch[10] * (int(a in list(left) and b in list(right)) - int(b in list(left) and a in list(right)))
            check(name + state + "_control_absent_from_all7_interfaces", np.all(op[:, 210] == 0))
            full_loads = np.pad(dispatch["bus_pd"][ix], ((0, 0), (0, len(fg["ids"]) - 140)))
            full_injection = injections(fullcase, gen_buses, pg[ix], full_loads, dc[ix], fg)
            max_full_kcl = max(max_full_kcl, close(name + state + "_lifted_full191_KCL", exits(fflow, fg), full_injection))
            max_recovery = max(max_recovery, close(name + state + "_all7_from_full_branch_laws", data["interface_pf"][ix], fflow @ op.T))
            if not item["par_controlled"]:
                close(name + state + "_uncontrolled_phase_preserved", data["equivalent_shift_deg"][ix], np.full(len(ix), geo["branch"][210, 9]))
        for h in sorted(sample_hours):
            case = slim[states[h]]
            geo = geometry(case)
            load = np.pad(dispatch["bus_pd"][[h]], ((0, 0), (0, 8)))
            injection = injections(case, gen_buses, pg[[h]], load, dc[[h]], geo)[0]
            target = raw[h] * gamma * item["raw_PAR_to_branch_sign"] if item["par_controlled"] else None
            f, angle, shift = independent_solve(case, injection, dispatch["reference_bus"][h], target)
            error = close(name + "_independent_solve_flow_hour" + str(h + 1), f, data["branch_pf"][h])
            close(name + "_independent_solve_angle_hour" + str(h + 1), angle, data["bus_va"][h])
            close(name + "_independent_solve_SHIFT_hour" + str(h + 1), [shift], [data["equivalent_shift_deg"][h]])
            representative.append(dict(hour_index=h + 1, timestamp_utc=times[h], state=states[h],
                                       equivalent_SHIFT_degrees=float(shift), maximum_flow_error_mw=error,
                                       physical_tap_claim=False))
        if not item["source_generation_mapping_corrected"]:
            old = mat("output/nygrid_2025_slim/replay/topology_" + item["topology"] + ".mat", ["branch_pf", "interface_pf"])
            close(name + "_baseline_frozen_branch_identity", data["branch_pf"], old["branch_pf"])
            close(name + "_baseline_frozen_interface_identity", data["interface_pf"], old["interface_pf"])
        maximum_score_error = 0.
        for cohort, score_mask in [("own_qualified", mask), ("common_PAR_qualified", common)]:
            for month in range(13):
                m = score_mask if month == 0 else score_mask & (month_ids == month)
                table = scores if month == 0 else monthly
                selection = (table.variant == name) & (table.cohort == cohort)
                if month:
                    selection &= table.month == month
                section = table.loc[selection].set_index("interface")
                check(name + cohort + str(month) + "_all7_score_rows", len(section) == 7 and set(section.index) == set(NAMES))
                error = data["interface_pf"][m] / gamma - y[m]
                values = dict(mae_public_equivalent_mw=np.mean(abs(error), axis=0),
                              rmse_public_equivalent_mw=np.sqrt(np.mean(error ** 2, axis=0)),
                              bias_public_equivalent_mw=np.mean(error, axis=0),
                              wape_percent=100 * np.sum(abs(error), axis=0) / np.sum(abs(y[m]), axis=0),
                              mean_absolute_observed_public_mw=np.mean(abs(y[m]), axis=0))
                check(name + cohort + str(month) + "_score_hours", section.hours.eq(int(m.sum())).all())
                for metric, expected in values.items():
                    maximum_score_error = max(maximum_score_error, close(name + cohort + str(month) + metric,
                                              section.loc[NAMES, metric].to_numpy(float), expected, tol=1e-8))
        variants.append(dict(variant=name, qualified_hours=int(mask.sum()), maximum_native_branch_law_error_mw=max_law,
                             maximum_native_KCL_error_mw=max_kcl, maximum_lifted_full191_KCL_error_mw=max_full_kcl,
                             maximum_interface_recovery_error_mw=max_recovery, maximum_score_error=maximum_score_error,
                             representative_independent_solves=representative))
        print(name + ": all-hour laws, KCL, recovery, targets, scores passed", flush=True)
    loader = source("System Matpower Format/npcc_nygrid_2025_moses_corrected_dc.m").read_text()
    check("loader_default_hydro_only", "control='hydro_zone_corrected'" in loader)
    check("loader_rejects_unpromoted_controls", "assert(strcmp(control,'hydro_zone_corrected')" in loader)
    check("loader_no_schedule_placeholder", "par_schedule" not in loader)
    check("loader_qualifies_source_hour", "r.qualified(hour_index)" in loader)
    source("scripts/nygrid_2025_moses_audit/validate_replays.py")
    for relative, value in INPUTS.items():
        check("unchanged_at_completion_" + relative, sha(ROOT / relative) == value)
    report = dict(status="passed_independent_annual_gate", started_utc=started,
                  completed_utc=datetime.now(timezone.utc).isoformat(), checks=len(CHECKS), failed_checks=0,
                  branch=subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
                  HEAD=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  annual_variants=8, annual_score_rows=112, monthly_score_rows=1344, interfaces=7,
                  qualified_hours_per_variant=8663, raw_P34_qualified_hours=8673,
                  capacity_bound_maximum_violation_mw=max_bound, KKT_projection_error_mw=max_kkt,
                  native_global_balance_error_mw=max_sum, saved_objective_error=max_objective,
                  optimum_preservation_proof="The unchanged strictly convex separable quadratic objective, native bounds and single global sum have the same unique optimum. Generator terminal IDs do not appear in that optimization. All-hour KKT projection, objective and sum are rechecked directly. No network-constrained OPF optimum is claimed.",
                  all_inputs_unchanged=True, production_solve_functions_imported=False,
                  annual_powerflow_rerun=False,
                  loader_review="Static review: default and accepted control is hydro_zone_corrected only; no PAR schedule placeholder. MATLAB execution is a separate validation.",
                  limitations=["PAR sign orientations remain unpromoted; lower posthoc error is not direction evidence.",
                               "Equivalent phase shifts, including extremes near100degrees, are diagnostic network controls and not measured or validated physical tap settings.",
                               "DC nodal consistency is not AC, thermal, reactive, security, storage-energy or unit-commitment feasibility."],
                  variants=variants, checks_detail=CHECKS,
                  inputs=[dict(path=p, sha256=h) for p, h in sorted(INPUTS.items())])
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["status", "checks", "annual_variants", "annual_score_rows", "monthly_score_rows", "KKT_projection_error_mw"]}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        DEST.parent.mkdir(parents=True, exist_ok=True)
        DEST.write_text(json.dumps(dict(status="failed_independent_annual_gate", error=str(exc),
                         checks_detail=CHECKS, inputs=[dict(path=p, sha256=h) for p, h in sorted(INPUTS.items())]), indent=2) + "\n")
        raise
