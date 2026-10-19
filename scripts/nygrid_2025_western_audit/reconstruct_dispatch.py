"""Replace Ontario's scheduled total with independently measured actual flow.

The six Ontario regional equivalents retain their original sharing rule. A
fresh bounded projection restores the native-generation balance using the
same per-unit priors, availability, capacities and weights. No internal
interface observation is read by this reconstruction.
"""
from __future__ import annotations

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
sys.path.insert(0, str(ROOT / "scripts/nygrid_2025_dispatch"))
from build_dispatch import bounded_projection


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def boolean(series):
    s = pd.Series(series).astype(str).str.lower()
    require(s.isin(["true", "false", "1", "0"]).all(), "Unknown quality boolean")
    return s.isin(["true", "1"]).to_numpy()


def check_records(records):
    require(bool(records), "Source dependency manifest is empty")
    paths = [r["path"] for r in records]
    require(len(set(paths)) == len(paths), "Duplicated source dependency path")
    for r in records:
        p = Path(r["path"]); p = p if p.is_absolute() else ROOT / p
        require(p.is_file() and sha(p) == r["sha256"], "Source dependency changed: " + str(p))


def require_coverage(records, paths, label):
    present = {r["path"] for r in records}
    require(set(paths).issubset(present), "Incomplete " + label + " dependency coverage")


def verify_frozen_dependencies():
    groups = {
        "output/nygrid_2025_dispatch/delivery_manifest.json": [
            "output/nygrid_2025_dispatch/dispatch/dispatch.mat",
            "output/nygrid_2025_dispatch/dispatch/dispatch_bounds.mat",
            "output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat",
            "scripts/nygrid_2025_dispatch/build_dispatch.py"],
        "output/nygrid_2025_inputs/delivery_manifest.json": [
            "output/nygrid_2025_inputs/model/external_generator_allocation.csv"],
        "output/nygrid_2025_moses_audit/delivery_manifest.json": [
            "output/nygrid_2025_moses_audit/corrected/model_generator_register.csv"],
        "output/nygrid_2025_par_controls/delivery_manifest.json": [
            "output/nygrid_2025_par_controls/controls/inputs.npz",
            "output/nygrid_2025_par_controls/controls/input_receipt.json"],
    }
    for manifest, needed in groups.items():
        d = json.loads((ROOT / manifest).read_text())
        records = d["entries"] if "entries" in d else d["files"]
        selected = [r for r in records if r["path"] in needed]
        require_coverage(selected, needed, manifest)
        check_records(selected)


def verify_dispatch_sources(data, bounds, priors, register, par, allocation):
    hours = np.asarray(data["hour_index"]).reshape(-1)
    require(np.isfinite(float(data["gamma"])) and float(data["gamma"]) > 0
            and float(data["gamma"]) == float(par["gamma"]), "Dispatch/PAR power scale differs")
    require(np.array_equal(np.asarray(data["timestamp_utc"]).astype(str), par["timestamp_utc"].astype(str)), "Dispatch/PAR UTC axes differ")
    for item in [bounds, priors, par]:
        require(np.array_equal(hours, np.asarray(item["hour_index"]).reshape(-1)), "Numerical input hour axes differ")
    for item in [bounds, priors]:
        require(np.array_equal(data["native_fleet_ids"], item["native_fleet_ids"]), "Native fleet identity axis differs")
    native = register.role.eq("native").to_numpy()
    require(np.array_equal(pd.to_numeric(register.loc[native, "fleet_id"]).to_numpy(), data["native_fleet_ids"]), "Register/native numerical identity differs")
    ng, nn, nh = len(register), int(native.sum()), len(hours)
    require(np.array_equal(register.gen_row.to_numpy(int), np.arange(1, ng + 1)), "Model generator row order changed")
    require(np.asarray(data["gen_pg"]).shape == np.asarray(priors["prior_pg"]).shape == (nh, ng), "Prior/PG shape mismatch")
    require(np.asarray(bounds["gen_pmin"]).shape == np.asarray(bounds["gen_pmax"]).shape == (nh, ng), "Generator bound shape mismatch")
    require(np.asarray(priors["objective_weights"]).shape == (nh, nn), "Native weight shape mismatch")
    q = np.asarray(data["dispatch_qualified"], bool)
    require(np.isfinite(priors["prior_pg"][q][:, native]).all()
            and np.isfinite(priors["objective_weights"][q]).all()
            and (priors["objective_weights"][q] > 0).all(), "Invalid qualified native prior/weight")
    require(np.isfinite(bounds["gen_pmin"][q]).all() and np.isfinite(bounds["gen_pmax"][q]).all()
            and (bounds["gen_pmax"][q] >= bounds["gen_pmin"][q]).all(), "Invalid qualified generator bounds")
    require(bool(par["observed_direction_verified"])
            and np.array_equal(par["direction_ontario_to_NY_multiplier"], [1, 1]), "P34 direction is not verified")
    require(np.allclose(par["observed_model_mw"], par["observed_public_mw"] * float(data["gamma"]),
                        atol=1e-12, rtol=0, equal_nan=True), "P34 power scale is inconsistent")
    ont = allocation.loc[allocation.region.eq("ONTARIO")]
    require(len(ont) == 6 and ont.generator_row.is_unique and np.isfinite(ont.generation_share).all()
            and (ont.generation_share >= 0).all() and abs(ont.generation_share.sum() - 1) < 1e-12,
            "Ontario sharing partition is invalid")


def source_inputs(times):
    folder = OUT / "ontario"
    audit = json.loads((folder / "ontario_audit_summary.json").read_text())
    require(audit["status"] == "source_basis_verified_actual_hourly_external_exchange_ready" and audit["year"] == 2025,
            "Ontario source audit is incomplete or from another year")
    require(audit["positive_direction"] == "Ontario_to_NewYork" and audit["actual_units"] == "MW_hourly_average",
            "Actual-flow direction or unit scope changed")
    require(audit["source_zone"] == "NEW-YORK" and audit["source_actual_field"] == "Flow"
            and audit["source_time_basis"] == "fixed_EST_UTCminus5_hour_ending;HE1starts00EST",
            "Actual exchange scope or documented time basis changed")
    require(not audit["source_sign_or_timing_fitted_to_internal_flows"]
            and not audit["internal_interface_observations_consumed"], "Source definition was fitted to internal observations")
    source_records = pd.read_csv(folder / "source_manifest.csv").to_dict("records")
    required_raw = ["PUB_IntertieScheduleFlowYear_2025.csv", "PUB_IntertieScheduleFlowYear_2025_v394.csv",
                    "IntertieScheduleFlow_HTML_t1-2.xsl", "IntertieScheduleFlow_r2.xsd"]
    require_coverage(source_records, [(folder / "raw" / p).relative_to(ROOT).as_posix() for p in required_raw], "Ontario actual/clock/schema")
    check_records(source_records)
    require_coverage(audit["frozen_inputs"], ["output/nygrid_2025_inputs/load_source/interface_wide.csv",
        "output/nygrid_2025_dispatch/dispatch/dispatch.mat", "output/nygrid_2025_par_controls/controls/hourly_controls.csv"], "frozen comparison")
    check_records(audit["frozen_inputs"])
    require(sha(folder / "hourly_actual_exchange.csv") == audit["actual_input_sha256"], "Actual input CSV changed")
    require(sha(ROOT / "scripts/nygrid_2025_western_audit/ontario_audit.py") == audit["audit_script_sha256"], "Source audit code changed")
    source = pd.read_csv(folder / "hourly_actual_exchange.csv")
    quality = pd.read_csv(folder / "hourly_exchange_quality.csv")
    receipt = json.loads((folder / "source_quality_receipt.json").read_text())
    require(receipt["status"] == "suspect_source_hours_quarantined_without_changing_reported_actuals"
            and receipt["original_csv_preserved"] and receipt["raw_reported_values_preserved"], "Source-wide quality screen failed")
    require(receipt["internal_interface_observations_consumed"] is False
            and not receipt["quality_predicate_fitted_to_internal_flows"], "Source exclusions were chosen from interface residuals")
    require(receipt["original_csv_sha256"] == sha(folder / "hourly_actual_exchange.csv"), "Quality screen used a different source")
    require(receipt["quality_child_sha256"] == sha(folder / "hourly_exchange_quality.csv"), "Source quality mask changed")
    require(audit["source_quality_child_sha256"] == receipt["quality_child_sha256"]
            and audit["source_quality_receipt_sha256"] == sha(folder / "source_quality_receipt.json"), "Source audit and quality child disagree")
    check_records(receipt["raw_sources"])
    require_coverage(receipt["raw_sources"], [(folder / "raw" / p).relative_to(ROOT).as_posix()
                     for p in required_raw[:2]], "source-quality raw annual")
    require(receipt["audit_script_sha256"] == audit["audit_script_sha256"], "Quality screen code is not the audited source extractor")
    for frame in [source, quality]:
        require(len(frame) == 8760 and np.array_equal(frame.hour_index.to_numpy(int), np.arange(1, 8761)), "Source hour IDs differ")
        require(np.array_equal(frame.timestamp_utc.astype(str), times), "Actual or quality UTC axis differs from dispatch")
    valid = boolean(quality.source_quality_qualified)
    suspect = boolean(quality.all_intertie_actual_zero) & boolean(quality.schedules_nonzero)
    require(np.array_equal(valid, boolean(source.coverage_qualified) & ~suspect), "Source-wide quality rule and mask differ")
    require(int(suspect.sum()) == receipt["suspect_count"]
            and np.array_equal(np.flatnonzero(suspect) + 1, receipt["excluded_hour_indices"]), "Source-quality exclusions changed")
    actual = source.actual_ontario_to_ny_mw.to_numpy(float)
    old = source.original_nyiso_schedule_mw.to_numpy(float)
    require(np.isfinite(actual[valid]).all(), "Qualified actual exchanges are nonfinite")
    # A receipt must not make an edited derived CSV or quality mask authoritative.
    # Independently recover the report's values, EST clock and all-zone signature.
    raw = pd.read_csv(folder / "raw/PUB_IntertieScheduleFlowYear_2025.csv", header=[3, 4])
    require(len(raw) == 8760, "Raw annual report row count changed")
    he = pd.to_numeric(raw.iloc[:, 1]).to_numpy()
    require(np.isin(he, np.arange(1, 25)).all(), "Invalid fixed-EST hour ending")
    raw_times = (pd.to_datetime(raw.iloc[:, 0], utc=True) + pd.to_timedelta(he + 4, unit="h")).dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy()
    require(np.array_equal(raw_times, times), "Raw EST clock differs from the requested physical UTC axis")
    raw_actual = pd.to_numeric(raw[("NEW-YORK", "Flow")]).to_numpy(float)
    raw_schedule = pd.to_numeric(raw[("NEW-YORK", "Exp")]).to_numpy(float) - pd.to_numeric(raw[("NEW-YORK", "Imp")]).to_numpy(float)
    require(np.array_equal(actual, raw_actual) and np.array_equal(source.source_net_schedule_mw.to_numpy(float), raw_schedule),
            "Derived actual or schedule value differs from the original report")
    flow_columns = [c for c in raw.columns if c[1] == "Flow"]
    schedule_columns = [c for c in raw.columns if c[1] in ["Imp", "Exp"]]
    require(len(flow_columns) == 15 and len(schedule_columns) == 30, "Unexpected intertie collection")
    raw_zero = raw[flow_columns].apply(pd.to_numeric).eq(0).all(axis=1).to_numpy()
    raw_nonzero_schedule = raw[schedule_columns].apply(pd.to_numeric).abs().sum(axis=1).gt(0).to_numpy()
    require(np.array_equal(raw_zero, boolean(quality.all_intertie_actual_zero))
            and np.array_equal(raw_nonzero_schedule, boolean(quality.schedules_nonzero)), "Quality child differs from the raw all-intertie signature")
    require(np.array_equal(valid, np.isfinite(raw_actual) & ~(raw_zero & raw_nonzero_schedule)), "Raw source qualification mismatch")
    original = pd.read_csv(ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv", usecols=["timestamp_utc", "SCH - OH - NY"])
    require(np.array_equal(original.timestamp_utc.astype(str), times)
            and np.allclose(old, original["SCH - OH - NY"], rtol=0, atol=1e-10, equal_nan=True), "Original Ontario schedule changed")
    require(np.allclose(source.actual_minus_original_schedule_mw, actual - old, atol=1e-9, rtol=0, equal_nan=True), "Source delta changed")
    review = json.loads((OUT / "review/pre_promotion_review.json").read_text())
    require(review["status"] == "passed_source_quality_and_mapping_pre_promotion_review"
            and review["source_review"]["failed_checks"] == 0, "Independent source review is unqualified")
    proof = review["source_review"]["dependencies"]
    require_coverage(proof, [(folder / p).relative_to(ROOT).as_posix() for p in
        ["raw/DOE2025_intertie_sign_source.pdf", "hourly_actual_exchange.csv", "hourly_exchange_quality.csv",
         "source_quality_receipt.json", "source_manifest.csv"]], "independent sign/quality review")
    check_records(proof)
    return source, valid, receipt


def build():
    folder = OUT / "dispatch"; folder.mkdir(parents=True, exist_ok=True)
    verify_frozen_dependencies()
    data = loadmat(BASE / "dispatch.mat", simplify_cells=True)
    bounds = loadmat(BASE / "dispatch_bounds.mat", simplify_cells=True)
    priors = loadmat(BASE / "dispatch_priors.mat", simplify_cells=True)
    register = pd.read_csv(ROOT / "output/nygrid_2025_moses_audit/corrected/model_generator_register.csv", keep_default_na=False)
    gamma = float(data["gamma"])
    times = np.asarray(data["timestamp_utc"]).astype(str)
    source, source_ok, quality_receipt = source_inputs(times)
    par = np.load(PAR / "controls/inputs.npz", allow_pickle=False)
    allocation = pd.read_csv(ROOT / "output/nygrid_2025_inputs/model/external_generator_allocation.csv")
    verify_dispatch_sources(data, bounds, priors, register, par, allocation)
    require(np.array_equal(times, par["timestamp_utc"].astype(str)), "P34 and dispatch time axes differ")
    original_q = np.asarray(data["dispatch_qualified"], bool)
    source_ok &= original_q & np.asarray(par["observed_replay_qualified"], bool)
    ix = np.flatnonzero(source_ok)
    require(len(ix) > 0, "No jointly qualified reconstruction hours")
    delta = source.actual_minus_original_schedule_mw.to_numpy(float)
    require(np.isfinite(delta[ix]).all(), "Qualified boundary change is missing")
    require(np.max(abs(delta[ix] - (source.actual_ontario_to_ny_mw.to_numpy()[ix]
            - source.original_nyiso_schedule_mw.to_numpy()[ix]))) < 1e-8, "Incorrect boundary change")
    native = np.flatnonzero(register.role.eq("native"))
    external = np.flatnonzero(register.role.eq("fixed_external"))
    require(np.array_equal(native, np.arange(1436)) and len(external) == 28, "Native/external identity axis changed")
    allocations_path = ROOT / "output/nygrid_2025_inputs/model/external_generator_allocation.csv"
    allocation = pd.read_csv(allocations_path)
    ontario = allocation.loc[allocation.region.eq("ONTARIO")]
    require(len(ontario) == 6 and abs(ontario.generation_share.sum() - 1) < 1e-12, "Ontario shares do not form the original six-row partition")
    parent_rows = pd.to_numeric(register.parent_gen_row, errors="coerce").to_numpy()
    columns, shares = [], []
    for r in ontario.itertuples(index=False):
        match = np.flatnonzero((parent_rows == r.generator_row) & register.role.eq("fixed_external").to_numpy())
        require(len(match) == 1 and int(register.iloc[match[0]].bus_id) == r.bus_id, "Ontario generator identity mismatch")
        columns.append(int(match[0])); shares.append(float(r.generation_share))
    columns, shares = np.asarray(columns), np.asarray(shares)
    old_pg = np.asarray(data["gen_pg"])
    pg = np.full_like(old_pg, np.nan)
    pg[ix] = old_pg[ix]
    pg[np.ix_(ix, columns)] += gamma * delta[ix, None] * shares[None, :]
    target = data["bus_pd"].sum(axis=1) + data["base_case"]["bus"][:, 4].sum() - pg[:, external].sum(axis=1)
    old_target = data["native_required_pg"]
    require(np.max(abs(target[ix] - (old_target[ix] - gamma * delta[ix]))) < 1e-7,
            "Boundary replacement and native balance target do not cancel")
    p0 = priors["prior_pg"][:, native]
    lo, hi, weights = bounds["gen_pmin"][:, native], bounds["gen_pmax"][:, native], priors["objective_weights"]
    solved, dual, feasible = bounded_projection(p0[ix], lo[ix], hi[ix], target[ix], weights[ix])
    status = np.zeros(8760, np.int8); status[ix] = np.where(feasible, 1, 2)
    qualified = status == 1
    good = ix[feasible]
    pg[np.ix_(good, native)] = solved[feasible]
    pg[~qualified] = np.nan
    multiplier = np.full(8760, np.nan); multiplier[good] = dual[feasible]
    objective = np.full(8760, np.nan)
    objective[good] = .5 * np.sum(weights[good] * (pg[np.ix_(good, native)] - p0[good]) ** 2, axis=1)
    require(np.max(abs(pg[good].sum(axis=1) - data["bus_pd"][good].sum(axis=1)
            - data["base_case"]["bus"][:, 4].sum())) < 1e-7, "New injections are not globally balanced")
    unaffected = np.setdiff1d(external, columns)
    require(np.array_equal(pg[np.ix_(good, unaffected)], old_pg[np.ix_(good, unaffected)]), "An unrelated external schedule changed")
    require(np.max(np.maximum(lo[good] - pg[np.ix_(good, native)], 0)) < 1e-7
            and np.max(np.maximum(pg[np.ix_(good, native)] - hi[good], 0)) < 1e-7, "Native capacity was violated")
    path = folder / "actual_Ontario_dispatch.mat"
    savemat(path, dict(hour_index=data["hour_index"], timestamp_utc=times.astype(object), gen_pg=pg,
        original_qualified=original_q, source_qualified=source_ok, qualified=qualified, status_code=status,
        native_required_pg=target, dual_lambda=multiplier, objective_value=objective, gamma=gamma,
        delta_ontario_public_mw=delta, actual_ontario_public_mw=source.actual_ontario_to_ny_mw.to_numpy(),
        ontario_generator_rows_1based=columns + 1, ontario_generator_shares=shares,
        native_generator_rows_1based=native + 1), do_compression=True, oned_as="column")
    changes = []
    for j, r in register.iterrows():
        d = (pg[good, j] - old_pg[good, j]) / gamma
        changes.append(dict(gen_row=j + 1, device_key=r.device_key, role=r.role, fuel_category=r.fuel_category,
                            mean_change_public_mw=float(d.mean()), mean_absolute_change_public_mw=float(abs(d).mean()),
                            max_absolute_change_public_mw=float(abs(d).max())))
    pd.DataFrame(changes).to_csv(folder / "generator_adjustments.csv", index=False)
    pd.DataFrame(dict(hour_index=data["hour_index"], timestamp_utc=times, original_qualified=original_q,
        source_qualified=source_ok, qualified=qualified, status_code=status,
        delta_ontario_public_mw=delta, native_required_model_mw=target)).to_csv(folder / "hour_status.csv", index=False)
    dependencies = [BASE / n for n in ["dispatch.mat", "dispatch_bounds.mat", "dispatch_priors.mat"]]
    dependencies += [allocations_path, PAR / "controls/inputs.npz", OUT / "ontario/hourly_actual_exchange.csv",
        OUT / "ontario/hourly_exchange_quality.csv", OUT / "ontario/source_quality_receipt.json",
        OUT / "ontario/ontario_audit_summary.json", ROOT / "scripts/nygrid_2025_dispatch/build_dispatch.py", Path(__file__)]
    receipt = dict(passed=True, qualified_hours=int(qualified.sum()), source_qualified_hours=int(source_ok.sum()),
        previous_qualified_hours=int(original_q.sum()), source_excluded_additional_hours=int((original_q & ~source_ok).sum()),
        capacity_infeasible_hours=int((status == 2).sum()), native_priors_weights_and_bounds_unchanged=True,
        original_loads_and_other_external_exchanges_unchanged=True, original_P34_controls_unchanged=True,
        internal_interface_observations_used=False, sign_timing_or_weights_fit_to_internal_flows=False,
        boundary_policy="IESO measured NEW-YORK aggregate replaces prior NYISO Ontario schedule; other regions keep their declared source basis",
        dispatch_policy="same strictly convex bounded source-prior projection with corrected native balance target",
        dispatch_file_sha256=sha(path), dependencies=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in dependencies])
    (folder / "dispatch_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return receipt


if __name__ == "__main__":
    build()
