"""Independently compare saved annual arrays and seal compact-validation evidence.

No electrical simulation, fit, redispatch, or baseline rewrite occurs here.
The original 8494 detailed equation/profile-qualified hours remain the cohort.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output/nygrid_2025_compact_ac/validation"
BASE = ROOT / "output/nygrid_2025_acpf_profile_audit/acpf"
TARGET = OUT / "source_receipt.json"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def record(path):
    path = Path(path)
    assert path.is_file(), str(path)
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path), bytes=path.stat().st_size)


def flag(series):
    return series.astype(str).str.lower().isin(["true", "1"])


def maxdiff(a, b, mask):
    values = np.abs(np.asarray(a)[mask] - np.asarray(b)[mask])
    assert np.isfinite(values).all()
    return float(values.max(initial=0))


def main():
    annual = read(OUT / "annual_compact_PF_receipt.json")
    paired = read(OUT / "representative_pairs/representative_pair_receipt.json")
    qlim = read(OUT / "Q_limit_pairs/Q_limit_pair_receipt.json")
    independent = read(ROOT / "output/nygrid_2025_compact_ac/independent/compact_core_review.json")
    assert annual["completed"] and annual["passed"] and annual["attempted_hours"] == 8651
    assert annual["solver_exceptions"] == 0 and annual["fixed_detailed_paired_cohort_hours"] == 8494
    assert paired["passed"] and len(paired["checks"]) == 8 and independent["passed"]
    for dependency in independent["dependencies"]:
        assert sha(ROOT / dependency["path"]) == dependency["sha256"], f"Stale independent review: {dependency['path']}"
    assert qlim["completed"] and qlim["outcomes_consistent"] and len(qlim["checks"]) == 7
    assert not annual["OPF_used"] and not annual["generation_profiles_redispatched"]
    assert not annual["full_network_Newton_solve_used"]
    assert not annual["internal_interface_measurements_used_as_solver_input"]
    quality = pd.read_csv(OUT / "annual_hour_quality.csv")
    errors = pd.read_csv(OUT / "paired_detailed_error.csv")
    assert len(quality) == len(errors) == 8651 and quality.hour_index.is_unique and errors.hour_index.is_unique
    assert np.array_equal(quality.hour_index, errors.hour_index)
    solved = flag(quality.AC_equation_gate) & flag(quality.P_profile_preservation_gate) & flag(quality.reduction_and_equation_gate)
    assert int(solved.sum()) == annual["AC_equation_qualified_hours"]
    fixed = flag(errors.detailed_baseline_qualified)
    assert int(fixed.sum()) == 8494 and flag(errors.loc[fixed, "solution_equivalent"]).all()
    assert np.array_equal(quality.loc[solved, "hour_index"], errors.loc[flag(errors.compact_equation_qualified), "hour_index"])
    axes = loadmat(OUT / "annual_axes.mat", simplify_cells=True)
    old_axes = loadmat(BASE / "annual_axes.mat", simplify_cells=True)
    for key in ["hour_index", "timestamp_utc", "source_qualified", "gamma", "bus_id", "base_kv", "branch_keys", "branch_parent_row", "branch_from_bus", "branch_to_bus", "topology_state_index", "model_month", "DC_from_bus", "DC_to_bus"]:
        assert np.array_equal(axes[key], old_axes[key]), key
    seen = []
    monthly = []
    totals = dict(source=0, native=0, fixed=0, matched=0, new=0)
    maxima = dict(voltage_pu=0., branch_PQ_MVA=0., original_branch_current_A=0., bus_generation_PQ_MVA=0., DC_PQ_MVA=0.)
    extra = []
    for month in range(1, 13):
        name = f"profile_PF_2025_{month:02d}.mat"
        now = loadmat(OUT / "monthly" / name, simplify_cells=True)
        old = loadmat(BASE / "monthly" / name, simplify_cells=True)
        hours = np.atleast_1d(now["hour_index"]).astype(int)
        seen.extend(hours.tolist())
        for key in ["hour_index", "timestamp_utc", "source_qualified", "gamma", "bus_id", "branch_keys", "topology_state_index"]:
            assert np.array_equal(now[key], old[key]), (month, key)
        qualified = np.atleast_1d(now["source_qualified"]).astype(bool)
        baseline = np.atleast_1d(old["AC_equation_gate"]).astype(bool) & np.atleast_1d(old["P_profile_preservation_gate"]).astype(bool)
        native = np.atleast_1d(now["AC_equation_gate"]).astype(bool) & np.atleast_1d(now["P_profile_preservation_gate"]).astype(bool) & np.atleast_1d(now["reduction_and_equation_gate"]).astype(bool)
        assert np.array_equal(now["detailed_baseline_qualified"].astype(bool), baseline)
        assert native[baseline].all() and now["paired_detailed_solution_equivalent"][baseline].all()
        assert np.all(now["native_retained_bus_count"][qualified] == 148)
        assert np.asarray(now["retained_bus_ids"]).size == 148
        assert np.array_equal(now["bus_present"][qualified], old["bus_present"][qualified])
        assert np.array_equal(now["branch_present"][qualified], old["branch_present"][qualified])
        assert np.array_equal(now["branch_active"][qualified], old["branch_active"][qualified])
        busmask = baseline[:, None] & now["bus_present"].astype(bool)
        branchmask = baseline[:, None] & now["branch_present"].astype(bool)
        sourcebus = qualified[:, None] & now["bus_present"].astype(bool)
        assert maxdiff(now["PD"], old["PD"], sourcebus) == 0
        assert maxdiff(now["QD"], old["QD"], sourcebus) == 0
        vnow = now["VM"] * np.exp(1j * np.deg2rad(now["VA"]))
        vold = old["VM"] * np.exp(1j * np.deg2rad(old["VA"]))
        maxima["voltage_pu"] = max(maxima["voltage_pu"], maxdiff(vnow, vold, busmask))
        for key in ["PF", "QF", "PT", "QT"]:
            maxima["branch_PQ_MVA"] = max(maxima["branch_PQ_MVA"], maxdiff(now[key], old[key], branchmask))
        for key in ["Iseries", "Ifrom", "Ito"]:
            maxima["original_branch_current_A"] = max(maxima["original_branch_current_A"], maxdiff(now[key], old[key], branchmask))
        for key in ["bus_PG", "bus_QG"]:
            maxima["bus_generation_PQ_MVA"] = max(maxima["bus_generation_PQ_MVA"], maxdiff(now[key], old[key], busmask))
        for key in ["DC_PF", "DC_PT", "DC_QF", "DC_QT"]:
            maxima["DC_PQ_MVA"] = max(maxima["DC_PQ_MVA"], maxdiff(now[key], old[key], baseline))
        extra.extend(hours[native & ~baseline].tolist())
        totals["source"] += int(qualified.sum()); totals["native"] += int(native.sum())
        totals["fixed"] += int(baseline.sum()); totals["matched"] += int((baseline & native).sum())
        totals["new"] += int((native & ~baseline).sum())
        assert (OUT / "monthly" / name).stat().st_size < 100_000_000
        monthly.append(record(OUT / "monthly" / name))
    assert seen == list(range(1, 8761)) and totals["source"] == 8651 and totals["fixed"] == totals["matched"] == 8494
    for key, tol in [("voltage_pu", 1e-7), ("branch_PQ_MVA", 1e-4), ("original_branch_current_A", 1e-3), ("bus_generation_PQ_MVA", 1e-4), ("DC_PQ_MVA", 1e-4)]:
        assert maxima[key] < tol, (key, maxima[key], tol)
    # Extra native successes, if any, require separate detailed-PF warm checks.
    extra_receipt = None
    if extra:
        extra_receipt = read(OUT / "new_native_success_verification/receipt.json")
        assert extra_receipt["passed"] and sorted(extra_receipt["hours"]) == sorted(extra)
    gates = ["normal_voltage_gate", "generator_active_bound_gate", "generator_reactive_bound_gate", "generator_S_proxy_gate", "six_transfer_reactive_contract_gate", "VQ_and_generator_assumption_gate"]
    statistics = dict(statistics_cohort="native AC-equation, profile and reduction qualified; failed iterates excluded", native_qualified_hours=int(solved.sum()), frozen_detailed_cohort_hours=8494,
        runtime=dict(annual_wall_seconds=annual["elapsed_seconds"], total_compact_build_seconds=float(quality.compact_build_seconds.sum()),
            total_native_solve_recovery_audit_seconds=float(quality.PF_seconds.sum()),
            total_Newton_and_pfsoln_seconds=float(quality.native_NR_seconds.sum()),
            native_NR_seconds_column_includes_pfsoln_and_control_bookkeeping=True,
            numerical_solver_time_is_not_total_end_to_end_workflow_time=True),
        qualified_gate_counts={name: int(flag(quality.loc[solved, name]).sum()) for name in gates}, extrema={})
    for key in ["min_voltage_pu", "max_voltage_pu", "reference_PG_change_MW", "max_P_bound_violation_mw", "max_Q_bound_violation_mvar", "max_transfer_Q_bound_violation_mvar", "maximum_non_slack_PG_change_MW", "max_nodal_P_residual_mw", "max_nodal_Q_residual_mvar", "recovered_current_operator_crosscheck_A", "eliminated_current_residual_pu"]:
        values = quality.loc[solved, key].to_numpy(float)
        assert np.isfinite(values).all()
        statistics["extrema"][key] = dict(min=float(values.min()), max=float(values.max()))
    (OUT / "qualified_solution_summary.json").write_text(json.dumps(statistics, indent=2) + "\n")
    logs = OUT / "logs"; logs.mkdir(exist_ok=True)
    for path in [ROOT / "tmp/compact_ac_optimized_checks.log", ROOT / "tmp/compact_ac_annual_validation.log"]:
        assert path.is_file(); shutil.copyfile(path, logs / path.name)
    oldseal = BASE / "validation_source_receipt.json"
    old = read(oldseal)
    oldrecords = old["source_data"] + old["source_code"] + old["evidence"]
    for item in oldrecords:
        assert sha(ROOT / item["path"]) == item["sha256"], f"Changed preserved baseline: {item['path']}"
    source = sorted({ROOT / r["path"] for r in old["source_data"]} | {ROOT / "output/nygrid_2025_slim/network/bus_register.csv"})
    code = list((ROOT / "scripts/nygrid_2025_compact_ac/core").glob("*.m"))
    code += list((ROOT / "scripts/nygrid_2025_compact_ac/validation").glob("*.m"))
    code += list((ROOT / "scripts/nygrid_2025_compact_ac/validation").glob("*.py"))
    code += [ROOT / "System Matpower Format/npcc_nygrid_2025_compact_ac.m", ROOT / "System Matpower Format/run_nygrid_2025_compact_acpf.m"]
    code += [ROOT / item["path"] for item in old["source_code"] if item["path"].endswith(".m")]
    evidence = sorted(p for p in OUT.rglob("*") if p.is_file() and p != TARGET and p.suffix in {".json", ".csv", ".mat", ".log"})
    # The post-annual independent review may bind this receipt. Whitelist only
    # pre-annual core reviews so a later reseal cannot create a hash cycle.
    independent_paths = [ROOT / "output/nygrid_2025_compact_ac/independent" / name for name in [
        "bus_retention_ledger.json", "compact_core_review.json", "kernel_guard_results_before_performance.json",
        "kernel_guard_results.json", "kron_feasibility_review.json", "performance_source_diff_review.json"]]
    matpower_lib = Path("C:/Users/Holiday/OneDrive/Documents/MATLAB/matpower/lib")
    numerical_libraries = [matpower_lib / name for name in ["mpver.m", "runpf.m", "newtonpf.m", "pfsoln.m", "ext2int.m", "int2ext.m", "bustypes.m", "makeYbus.m", "makeSbus.m", "dSbus_dV.m", "toggle_dcline.m"]]
    assert all(path.is_file() for path in numerical_libraries)
    receipt = dict(passed=True, created_utc=datetime.now(timezone.utc).isoformat(), baseline_byte_preserved=True,
        preserved_baseline_record_count=len(oldrecords), preserved_baseline_seal=record(oldseal),
        all_8760_clock_rows_exported=True, source_qualified_hours=8651, native_qualified_hours=totals["native"],
        frozen_detailed_paired_cohort_hours=8494, frozen_detailed_cohort_equivalent_hours=totals["matched"],
        new_native_qualified_on_prior_failed_hours=extra, new_native_successes_separately_verified=extra_receipt is not None if extra else True,
        independent_saved_array_comparison_maxima=maxima, all_native_Newton_solves_have_148_retained_buses=True,
        original_canonical_bus_count=267, original_canonical_branch_count=488, monthly_files_below_100MB=True,
        OPF_used=False, parameter_or_profile_fitting_performed=False, full_network_Newton_used_inside_native_solver=False,
        old_detailed_annual_PF_rerun=False, internal_interface_measurements_used_as_native_solver_input=False,
        failed_outputs_retained=True, failed_iterates_excluded_from_accuracy_and_current_validity_statistics=True,
        physical_qualification_separate_from_equation_convergence=True, overload_not_a_convergence_rejection=True,
        physical_qualification_not_upgraded_by_reduction=True, global_infeasibility_claimed=False,
        source_data=[record(p) for p in source], source_code=[record(p) for p in sorted(set(code))],
        numerical_library_files=[dict(path=str(p), sha256=sha(p), bytes=p.stat().st_size) for p in numerical_libraries],
        evidence=[record(p) for p in evidence], independent_reviews=[record(p) for p in independent_paths], monthly_files=monthly)
    TARGET.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(dict(passed=True, preserved_records=len(oldrecords), native_qualified=totals["native"], frozen_paired_hours=8494, extra_native_hours=extra, paired_maxima=maxima, receipt_sha256=sha(TARGET))))


if __name__ == "__main__":
    main()
