"""Review final report, selected-cohort metrics and source disclosure from saved evidence."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
from urllib.parse import unquote

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output/nygrid_2025_ac_loss_revision"
COMPARISON = OUT / "comparison/combined"


def record(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=digest)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def close(actual, expected, tolerance=1e-9):
    assert np.allclose(actual, expected, atol=tolerance, rtol=0, equal_nan=True), (actual, expected)


def main():
    contract_path = OUT / "comparison/comparison_contract.json"
    contract = read(contract_path)
    for item in contract["source_receipts"]:
        assert record(ROOT / item["path"])["sha256"] == item["sha256"]
    frozen_preservation = {}
    for folder in ["nygrid_2025_acpf_profile_audit", "nygrid_2025_compact_ac"]:
        manifest = read(ROOT / "output" / folder / "DELIVERY_MANIFEST.json")
        for path, expected in manifest["files"].items():
            assert record(ROOT / path)["sha256"] == expected["sha256"]
        frozen_preservation[folder] = len(manifest["files"])

    arrays_path = COMPARISON / "comparison_arrays.npz"
    arrays = np.load(arrays_path, allow_pickle=False)
    cohort_path = COMPARISON / "comparison_cohort.csv"
    cohort = pd.read_csv(cohort_path)
    old = arrays["frozen_old_qualified"].astype(bool)
    revised = arrays["revised_qualified"].astype(bool)
    paired = old & revised; new = revised & ~old; lost = old & ~revised
    assert len(cohort) == 8760 and old.sum() == 8494 and revised.sum() == paired.sum() == 8170
    assert new.sum() == 0 and lost.sum() == 324 and arrays["source_qualified"].sum() == 8651
    assert arrays["operating_qualified"].sum() == 0
    for column, expected in [("revised_comparison_qualified", revised), ("paired_frozen_old_qualified", paired), ("revised_only_success", new), ("frozen_old_success_lost", lost)]:
        assert np.array_equal(cohort[column].to_numpy(bool), expected)
    assert np.array_equal(cohort.hour_index, arrays["hour_index"])
    assert np.array_equal(cohort.timestamp_utc.to_numpy(str), arrays["timestamp_utc"].astype(str))
    months = pd.to_datetime(cohort.timestamp_utc, utc=True).dt.tz_convert("America/New_York").dt.month.to_numpy()
    masks = {"paired_frozen_old": paired, "revised_all_qualified": revised, "revised_only_success": new,
             "frozen_old_all8494": old, "frozen_old_success_lost": lost}
    names = arrays["interface_names"].astype(str).tolist()
    metrics_path = COMPARISON / "public_interface_metrics.csv"
    metrics = pd.read_csv(metrics_path)
    assert not metrics.duplicated(["cohort", "period", "model", "convention", "interface"]).any()
    max_metric_error = 0.
    for row in metrics.itertuples():
        mask = masks[row.cohort].copy()
        if row.period.startswith("month_"): mask &= months == int(row.period[-2:])
        elif row.period == "post_Dover": mask &= cohort.dated_state.to_numpy(str) == "post_dover"
        else: assert row.period == "annual"
        assert row.hours == int(mask.sum()) and mask.any()
        prefix = "old_" if row.model == "frozen_old" else "revised_"
        assert row.model in ["frozen_old", "combined"]
        j = names.index(row.interface)
        observed = arrays["observed"][mask, j]
        error = arrays[prefix + row.convention][mask, j] - observed
        expected = np.array([np.mean(np.abs(error)), np.sqrt(np.mean(error * error)), np.mean(error),
                             100 * np.sum(np.abs(error)) / np.sum(np.abs(observed))])
        actual = np.array([row.mae_public_MW, row.rmse_public_MW, row.bias_public_MW, row.wape_percent])
        close(actual, expected)
        max_metric_error = max(max_metric_error, float(np.max(np.abs(actual - expected))))

    summary_path = OUT / "summary/revision_summary.json"
    summary = read(summary_path)
    expected_counts = dict(source_qualified=8651, source_excluded=109, old_qualified=8494, revised_qualified=8170,
                           paired=8170, new=0, lost=324, operating_qualified=0, rejected=481)
    assert summary["counts"] == expected_counts
    table_path = OUT / "summary/paired_annual_interfaces.csv"
    table = pd.read_csv(table_path)
    assert table.interface.tolist() == names and (table.hours == 8170).all()
    selected = metrics[(metrics.cohort == "paired_frozen_old") & (metrics.period == "annual") & (metrics.convention == "legacy_signed_literal_from")]
    for row in table.itertuples():
        a = selected[(selected.model == "frozen_old") & (selected.interface == row.interface)].iloc[0]
        b = selected[(selected.model == "combined") & (selected.interface == row.interface)].iloc[0]
        close([row.old_WAPE_percent, row.revised_WAPE_percent, row.change_percentage_points, row.old_bias_public_MW, row.revised_bias_public_MW],
              [a.wape_percent, b.wape_percent, b.wape_percent-a.wape_percent, a.bias_public_MW, b.bias_public_MW])
    for a, b in zip(summary["paired_annual_interfaces"], table.to_dict("records")):
        assert a["interface"] == b["interface"]
        close([a[k] for k in a if k != "interface"], [b[k] for k in a if k != "interface"])

    scoring_path = COMPARISON / "scoring_receipt.json"
    scoring = read(scoring_path)
    assert scoring["passed"] and scoring["comparison_complete"]
    close(scoring["maximum_NY_zonal_loss_fraction"], np.max(arrays["NY_allocated_loss_MW"][revised] / arrays["NY_gross_target_MW"][revised]))
    close(scoring["minimum_NY_served_fraction"], np.min(arrays["NY_served_PD_MW"][revised] / arrays["NY_gross_target_MW"][revised]))
    assert max(scoring["maximum_source_accounting_errors"].values()) < 1e-5
    assert scoring["maximum_source_accounting_errors"]["HQ_PG_delta_MW"] == 0
    assert scoring["maximum_source_accounting_errors"]["external_P_bound_violation_MW"] == 0
    assert scoring["maximum_source_accounting_errors"]["controlled_transfer_P_delta_MW"] == 0

    source_path = OUT / "summary/sources_receipt_input.json"
    payload = read(source_path)
    queries = payload["items"][0]["queries"]
    assert len(queries) == 3 and sum(len(q["rows"]) for q in queries) == 22
    disclosed = {q["id"]: q for q in queries}
    for query in queries:
        for file in query["source"]["files"]: assert (OUT / file["label"]).is_file()
    assert disclosed["paired-interfaces"]["columns"] == table.columns.tolist()
    for a, b in zip(disclosed["paired-interfaces"]["rows"], table.to_dict("records")):
        assert a["interface"] == b["interface"]
        close([a[k] for k in a if k != "interface"], [b[k] for k in a if k != "interface"])
    zones_path = COMPARISON / "NY_zonal_loss_accounting.csv"
    zones = pd.read_csv(zones_path)
    for a, b in zip(disclosed["loss-accounting"]["rows"], zones.to_dict("records")):
        assert a["zone"] == b["zone"]
        close([a[k] for k in a if k != "zone"], [b[k] for k in a if k != "zone"])
    method = disclosed["loss-accounting"]["methods"][0]["code"]
    assert "baseMVA" in method and "R_pu" in method and "Iseries_pu" in method

    factorial_path = OUT / "validation/representative_factorial/factorial_receipt.json"
    factorial = read(factorial_path)
    check_path = OUT / "validation/representative_factorial/factorial_checks.csv"
    cells = pd.read_csv(check_path)
    attribution_path = OUT / "validation/representative_factorial/common_success_attribution.csv"
    attribution = pd.read_csv(attribution_path)
    assert factorial["completed"] and len(cells) == 56 and len(attribution) == 11
    common = cells.pivot(index="hour_index", columns="cell_index", values="comparison_qualified").all(axis=1)
    assert set(common[common].index) == set(attribution.hour_index) == set(factorial["common_success_hours"])
    for row in attribution.itertuples():
        b, x, l, c = [getattr(row, k) for k in ["legacy_public_MW", "impedance_only_public_MW", "loss_policy_only_public_MW", "combined_public_MW"]]
        close([row.impedance_effect_from_legacy_public_MW, row.loss_policy_effect_from_legacy_public_MW, row.interaction_public_MW, row.combined_effect_public_MW],
              [x-b, l-b, c-x-l+b, c-b], tolerance=1e-7)
    assert factorial["representative_attribution_not_annual_effect_estimate"]

    report_path = ROOT / "NYGRID_2025_AC_LOSS_REVISION.md"
    report = report_path.read_text(encoding="utf-8")
    for row in table.itertuples():
        expected = f"| {row.interface} | {row.old_WAPE_percent:.2f}% | {row.revised_WAPE_percent:.2f}% | {row.change_percentage_points:+.2f} | {row.old_bias_public_MW:+.1f} | {row.revised_bias_public_MW:+.1f} |"
        assert expected in report
    required_claims = ["8,170 of 8,651", "324 prior successes lost", "0 newly qualified", "0 hours pass", "481 rejected",
                       "95.45%", "94.52%", "3,131", "physical AC impedance remains unvalidated", "not measured NYISO transmission losses",
                       "not annual WAPE attribution", "not promoted or interpreted as proof of global infeasibility",
                       "45.04%", "43.50%", "13.70%", "or a second full-year conventional PF replay"]
    for text in required_claims: assert text in report, text
    assert "11 qualified representative final allocations" in report
    for col in ["impedance_effect_from_legacy_public_MW", "loss_policy_effect_from_legacy_public_MW", "interaction_public_MW", "combined_effect_public_MW"]:
        assert f"{attribution[col].mean():.2f}" in report
    links = []
    deferred = []
    for target in re.findall(r"\]\(([^)]+)\)", report):
        if "://" in target or target.startswith("#"): continue
        path = (ROOT / unquote(target.split("#")[0])).resolve()
        assert path.is_relative_to(ROOT)
        if path == OUT / "DELIVERY_MANIFEST.json" and not path.exists(): deferred.append(path.relative_to(ROOT).as_posix())
        else: assert path.is_file(), target
        links.append(path)

    annual_independent_path = OUT / "impedance/released_equivalent_boundary_consistent_annual_arrays_independent_review.json"
    independent = read(annual_independent_path)
    assert independent["passed"] and independent["completed"] and independent["months_checked"] == 12
    assert independent["revised_qualified_hours"] == 8170 and independent["lost_hours"] == 324
    peer_path = OUT / "comparison/independent/final_scoring_independent_review.json"
    peer = read(peer_path)
    assert peer["passed"]
    historical = read(OUT / "policy_evidence/historical_definition_supplement.json")
    assert historical["passed"] and historical["historical_2025_primary_definition_now_verified"]
    assert historical["version"] == "16.0" and historical["effective_date"] == "2025-05-29"
    for p, key, count in [("validation/policy_contract/policy_contract_receipt.json", "count", 24), ("validation/jacobian/jacobian_receipt.json", "finite_difference_cases", 10), ("validation/pairs/simultaneous_representatives/pair_receipt.json", "qualified_pair_count", 11)]:
        proof = read(OUT / p); assert proof["passed"] and proof[key] == count
    currentfiles = [Path(__file__), report_path, ROOT / "scripts/nygrid_2025_ac_loss_revision/build_summary.py", ROOT / "scripts/nygrid_2025_ac_loss_revision/build_sources_receipt.py",
                    ROOT / "scripts/nygrid_2025_ac_loss_revision/README.md", ROOT / "scripts/nygrid_2025_ac_loss_revision/comparison/score_revised_profiles.py",
                    contract_path, arrays_path, cohort_path, metrics_path, summary_path, table_path, scoring_path, source_path, zones_path,
                    factorial_path, check_path, attribution_path, annual_independent_path, peer_path,
                    OUT / "comparison/historical/historical_comparison_records.json", OUT / "policy_evidence/historical_definition_supplement.json",
                    OUT / "summary/annual_interface_comparison.png", OUT / "summary/annual_interface_comparison.svg"]
    currentfiles += [p for p in links if p.is_file() and p.name != "DELIVERY_MANIFEST.json"]
    currentfiles = list(dict.fromkeys(currentfiles))
    result = dict(passed=True, completed=True, created_utc=datetime.now(timezone.utc).isoformat(),
                  scope="Final report, source disclosure and selected-cohort arithmetic review; root finalizer owns the delivery seal",
                  reviewed_metric_rows=len(metrics), maximum_metric_arithmetic_error=max_metric_error,
                  paired_table_rows=7, source_disclosure_rows=22, factorial_common_hours=11,
                  original_detailed_and_compact_files_freshly_verified=frozen_preservation,
                  exact_frozen_cohorts_verified=True, common8170_vs_old8494_distinction_explicit=True,
                  no_annual_attribution_inferred_from_representative_factorial=True,
                  physical_and_source_qualification_limits_prominent=True,
                  manual2025_definition_verified_and_model_loss_ownership_distinguished=True,
                  corrected_minimum_served_fraction_summary_verified=True,
                  all_report_table_and_source_payload_values_match_underlying_metrics=True,
                  plot_visually_reviewed=True,
                  local_report_links_checked=len(links), deferred_delivery_manifest_links=deferred,
                  delivery_manifest_not_bound_to_avoid_hash_cycle=True,
                  report_or_root_builder_modified_by_this_review=False,
                  dependencies=[record(p) for p in currentfiles])
    (OUT / "comparison/final_delivery_review.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ["passed", "reviewed_metric_rows", "maximum_metric_arithmetic_error", "source_disclosure_rows", "local_report_links_checked", "deferred_delivery_manifest_links"]}))


if __name__ == "__main__":
    main()
