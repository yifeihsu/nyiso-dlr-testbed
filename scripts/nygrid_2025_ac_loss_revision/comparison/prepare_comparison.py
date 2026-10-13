"""Seal cohorts, observations, operators, and scoring before revised results.

The comparison is diagnostic and never fits internal NYISO interface data.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import subprocess

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output/nygrid_2025_ac_loss_revision/comparison"
FROZEN = ROOT / "output/nygrid_2025_acpf_profile_audit"
BASELINE_HEAD = "6dcc77f071a9ce4aaaa2fcba9a9aabc15f7d5dbc"
TASK_BASE_HEAD = "a7c90215b22f688acea9ee8a08a08fc4385be494"


def record(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=digest, bytes=path.stat().st_size)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    contract_path = OUT / "comparison_contract.json"
    assert not contract_path.exists(), "Comparison contract already sealed; do not overwrite it after result inspection"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    assert head == TASK_BASE_HEAD and branch == "codex/s13-phase1b-upny-coned"
    preserved = {}; manifest_paths = []
    for folder in ["nygrid_2025_acpf_profile_audit", "nygrid_2025_compact_ac"]:
        path = ROOT / "output" / folder / "DELIVERY_MANIFEST.json"
        committed = subprocess.check_output(["git", "show", BASELINE_HEAD + ":" + path.relative_to(ROOT).as_posix()], cwd=ROOT)
        assert path.read_bytes() == committed, f"Frozen manifest changed: {folder}"
        manifest = json.loads(committed)
        for relative, expected in manifest["files"].items():
            r = record(ROOT / relative)
            assert r["sha256"] == expected["sha256"] and r["bytes"] == expected["bytes"], relative
        preserved[folder] = len(manifest["files"])
        manifest_paths.append(path)

    source_cohort_path = FROZEN / "alignment/source_comparison_cohort.csv"
    old_arrays_path = FROZEN / "comparison/comparison_arrays.npz"
    source_cohort = pd.read_csv(source_cohort_path)
    with np.load(old_arrays_path, allow_pickle=False) as a:
        hours = a["hour_index"].copy(); times = a["timestamp_utc"].astype(str)
        source = a["source_qualified"].astype(bool); old_good = a["ACPF_comparison_cohort"].astype(bool)
        old_operating = a["VQ_and_generator_assumption_gate"].astype(bool)
        names = a["interface_names"].astype(str).tolist(); gamma = float(a["gamma"])
        assert np.isfinite(a["observed"][source]).all()
    assert np.array_equal(hours, np.arange(1, 8761))
    assert np.array_equal(source_cohort.hour_index, hours) and np.array_equal(source_cohort.timestamp_utc, times)
    assert np.array_equal(source_cohort.final_source_and_P32_comparison_cohort.to_numpy(bool), source)
    assert source.sum() == 8651 and old_good.sum() == 8494 and old_operating.sum() == 0
    assert np.all(~old_good | source)
    cohort = source_cohort[["hour_index", "timestamp_utc", "local_timestamp", "time_zone", "utc_offset_minutes", "dst_fold", "dated_state"]].copy()
    cohort["frozen_source_qualified"] = source
    cohort["frozen_old_equation_profile_qualified"] = old_good
    cohort["frozen_old_VQ_generator_qualified"] = old_operating
    cohort["all_seven_public_P32_qualified"] = source_cohort.all_seven_P32_qualified
    cohort.to_csv(OUT / "frozen_comparison_cohort.csv", index=False, lineterminator="\n")

    files = [Path(__file__), OUT / "frozen_comparison_cohort.csv", source_cohort_path, old_arrays_path] + manifest_paths
    files += [FROZEN / ("alignment/" + p) for p in ["interface_operator_contract.json", "interface_operator_terms.csv", "profile_alignment_summary.json"]]
    files += [ROOT / p for p in [
        "scripts/nygrid_2025_acpf_profile_audit/alignment/interface_operator.py",
        "output/nygrid_2025_inputs/load_source/interface_wide.csv",
        "output/nygrid_2025_inputs/load_source/interface_quality_wide.csv",
        "output/nygrid_2025_inputs/load_source/load_wide.csv",
        "output/nygrid_2025_inputs/model/operating_inputs.mat",
        "output/nygrid_2025_dispatch/dispatch/dispatch.mat",
        "output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat",
        "output/nygrid_2025_western_audit/dispatch/all_boundary_external_generator_shares.csv",
        "output/nygrid_2025_ac_loss_revision/policy_evidence/loss_accounting_policy_contract.json",
    ]]
    operator = json.loads((FROZEN / "alignment/interface_operator_contract.json").read_text())
    for entry in operator["source_receipts"]:
        p = ROOT / entry["path"]
        assert record(p)["sha256"] == entry["sha256"]
        files.append(p)
    files = list(dict.fromkeys(files))
    fields = {
        "hour_axes": ["hour_index", "timestamp_utc", "gamma", "source_qualified"],
        "canonical_axes": ["branch_keys", "branch_parent_row", "branch_from_bus", "branch_to_bus", "bus_id", "base_kv"],
        "original_physical_network": ["PF", "PT", "QF", "QT", "Iseries", "Ifrom", "Ito", "VM", "VA", "PD", "QD", "bus_PG", "bus_QG", "branch_present", "branch_active", "bus_present"],
        "qualification_flags": ["PF_converged", "AC_equation_gate", "loss_allocation_gate", "reduction_and_equation_gate", "VQ_and_generator_assumption_gate"],
        "allocation_arrays": ["NY_gross_target_MW", "NY_served_PD_MW", "actual_budget_MW", "regional_import_target_MW", "regional_import_solved_MW", "external_PG_increment_MW"],
        "audit_vectors": ["native_PG_change_from_original_MW", "HQ_PG_change_from_original_MW", "NY_gross_load_accounting_residual_MW", "regional_NY_import_residual_MW", "max_P_bound_violation_mw", "max_fixed_transfer_P_change_mw"],
    }
    contract = dict(
        created_utc=datetime.now(timezone.utc).isoformat(),
        status="sealed_before_revised_result_inspection",
        baseline_HEAD=BASELINE_HEAD, task_base_HEAD=TASK_BASE_HEAD, checkout_branch=branch,
        frozen_deliveries_files_verified_unchanged=preserved,
        retained_hour_positions=8760, source_qualified_hours=8651, frozen_old_qualified_hours=8494,
        frozen_old_VQ_generator_qualified_hours=0, interface_names=names, gamma=gamma,
        primary_revised_variant="combined", optional_diagnostic_variants=["loss_only", "impedance_only"],
        source_qualification_policy="Use the original8651 eligibility mask without interpolation, filling, retiming, or removal for revised solver behavior.",
        revised_qualification="source_qualified AND PF_converged AND AC_equation_gate AND loss_allocation_gate AND reduction_and_equation_gate",
        operating_qualification="Revised qualification AND VQ_and_generator_assumption_gate, reported separately.",
        primary_paired_cohort="Each variant's qualified hours intersect the frozen old8494 success mask; compare old and new only on that identical paired mask.",
        all_revised_cohort="Report every revised-qualified hour separately from primary paired metrics.",
        new_success_cohort="Revised-qualified AND NOT frozen-old-qualified; report separately.",
        lost_success_cohort="Frozen-old-qualified AND NOT revised-qualified; publish hours and old metrics separately.",
        coverage_policy="Publish all8760 positions, original8651 eligibility, old8494 successes, paired/new/lost counts and explicit failure flags.",
        legacy_impedance_ablation_qualification="If legacy_single_slack is deliberately retained, use source AND PF AND equations AND reduction only for diagnostic scoring; loss_allocation_gate remains false and no policy-validity claim is made.",
        factorial_effect_policy="If all four cells are supplied, attribute loss/impedance effects only on their common qualification intersection; keep each cell's coverage changes separate.",
        frozen_old_reference_directory="output/nygrid_2025_acpf_profile_audit/acpf/monthly",
        public_observation_path="output/nygrid_2025_inputs/load_source/interface_wide.csv",
        primary_terminal_convention="legacy_signed_literal_from",
        alternative_terminal_conventions=["oriented_source_side", "oriented_target_side"],
        interface_operator="scripts/nygrid_2025_acpf_profile_audit/alignment/interface_operator.py",
        interface_membership="Frozen original-parent cuts and original physical F/T terminals through section chains; never use reduced-network edges.",
        public_power_scale="Aggregate model MW divided by frozen gamma; no rescaling of line amperes.",
        error_metrics=["MAE_public_MW", "RMSE_public_MW", "bias_public_MW", "WAPE_percent"],
        WAPE_definition="100*sum(abs(predicted-observed))/sum(abs(observed)) on one explicitly named cohort and period; undefined if denominator is zero.",
        reporting_periods=["annual", "month_01_to_month_12", "post_Dover"],
        fitting_policy="No internal seven-interface observations tune parameters, dispatch, loss participation, operator conventions, signs, or time alignment.",
        NY_load_check="Verify each of11 gamma-scaled P58 targets equals served_PD plus its allocated NY loss, rather than asserting served_PD itself still equals P58.",
        regional_check="Compare ISONE/Ontario/PJM solved NY-terminal net imports against frozen NYIS actual targets, plus fixed HQ and six controlled transfers.",
        generation_check="Native/HQ input PG unchanged within declared numerical tolerance; external increments match regional assigned losses and stay within original finite bounds.",
        comparison_tolerance_model_MW=1e-5,
        source_target_tolerance_model_MW=1e-8,
        terminal_recompute_tolerance_public_MW=1e-8,
        physical_parameter_verification=False,
        physical_P32_meter_certification=False,
        allocation_policy_is_declared_not_observed=True,
        expected_export_fields=fields,
        export_API_status="Field contract proposed to producer; any naming adaptation must be recorded without changing cohorts or numerical criteria.",
        source_receipts=[record(p) for p in files],
        comparison_results_inspected=False, PF_or_OPF_run_by_this_script=False,
    )
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "contract": str(contract_path), "source_hours": 8651, "frozen_old_hours": 8494, "preserved": preserved}))


if __name__ == "__main__":
    main()
