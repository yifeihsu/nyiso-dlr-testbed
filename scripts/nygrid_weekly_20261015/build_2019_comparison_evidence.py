"""Rescore saved author-2019 and current-2025 results; no model or deck edits.

Uses the pinned authors' if.map on saved 57-bus branch flows, never the stale
flow4Plot indices. Current values come only from moses_repair_v1. Cross-year
denominator effects are arithmetic decompositions, not causal model effects.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_weekly_20261015/evidence"
OLD = ROOT / "output/nygrid_2019"
CURRENT = ROOT / "output/nygrid_2025_moses_repair/annual/moses_repair_v1/comparison"
UPSTREAM = ROOT / "tmp/nygrid_2019_reproduction/upstream"
NAMES = ["DYSINGER EAST", "WEST CENTRAL", "TOTAL EAST", "MOSES SOUTH",
         "CENTRAL EAST - VC", "UPNY CONED", "SPR/DUN-SOUTH"]
OLD_NAMES = ["Dysinger East", "West Central", "Total East", "Moses South",
             "Central East", "UpNY-Coned", "Dun/SPR-South"]
VARIABLES = ["A2B", "B2C", "C2E", "D2E", "E2F", "G2H", "I2J"]
MAP_IDS = [1, 2, 3, 4, 5, 8, 10]
OLD_OPERATOR = "authors_released_if_map"
CURRENT_OPERATOR = "legacy_signed_literal_from"


def record(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def metric(prediction: np.ndarray, observed: np.ndarray) -> dict:
    assert prediction.shape == observed.shape
    assert np.isfinite(prediction).all() and np.isfinite(observed).all()
    error = prediction - observed
    mae = float(np.mean(np.abs(error)))
    denominator = float(np.mean(np.abs(observed)))
    assert denominator > 0
    wape = float(100 * np.abs(error).sum() / np.abs(observed).sum())
    assert abs(wape - 100 * mae / denominator) < 1e-10
    return {"hours": len(error), "MAE_MW": mae,
            "WAPE_percent": wape, "bias_MW": float(error.mean()),
            "RMSE_MW": float(np.sqrt(np.mean(error**2))),
            "mean_abs_observed_MW": denominator}


def characteristics(values: np.ndarray) -> dict:
    assert values.ndim == 1 and np.isfinite(values).all()
    q = np.quantile(values, [.05, .25, .5, .75, .95])
    return {"hours": len(values), "signed_mean_MW": float(values.mean()),
            "mean_abs_MW": float(np.abs(values).mean()),
            "standard_deviation_MW": float(values.std(ddof=0)),
            "minimum_MW": float(values.min()), "q05_MW": float(q[0]),
            "q25_MW": float(q[1]), "median_MW": float(q[2]),
            "q75_MW": float(q[3]), "q95_MW": float(q[4]),
            "maximum_MW": float(values.max()), "IQR_MW": float(q[3]-q[1]),
            "negative_hours": int((values < 0).sum()),
            "zero_hours": int((values == 0).sum()),
            "positive_hours": int((values > 0).sum()),
            "negative_percent": float(100 * np.mean(values < 0)),
            "abs_below_100MW_percent": float(100 * np.mean(np.abs(values) < 100))}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    old_manifest_path = OLD / "verification_manifest.json"
    upstream_manifest_path = OLD / "upstream_manifest.json"
    author_map_path = UPSTREAM / "updateOpCond.m"
    old_metric_path = ROOT / "output/nygrid_released_2019_comparison/independent/released_2019_recomputed_metrics.csv"
    current_metric_path = CURRENT / "public_interface_metrics.csv"
    current_array_path = CURRENT / "comparison_arrays.npz"
    current_receipt_path = CURRENT / "scoring_receipt.json"
    source_observation_path = ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv"
    source_quality_path = source_observation_path.with_name("interface_quality_wide.csv")
    deps = [old_manifest_path, upstream_manifest_path, author_map_path,
            old_metric_path, current_metric_path, current_array_path,
            current_receipt_path, source_observation_path, source_quality_path,
            *[OLD / f"annual_{i}.mat" for i in range(1, 5)]]
    before = [record(path) for path in deps]

    old_manifest = read_json(old_manifest_path)
    upstream_manifest = read_json(upstream_manifest_path)
    receipt = read_json(current_receipt_path)
    assert old_manifest["complete"] and old_manifest["hours"] == 8760
    assert upstream_manifest["commit"] == "47698b6c7823ae7b1bc6935e5601d5b64b8f918e"
    assert receipt["passed"] and receipt["completed"]
    assert receipt["candidate_qualified_hours"] == 8651
    expected_old = {item["path"]: item["sha256"] for item in old_manifest["files"]}
    for i in range(1, 5):
        item = record(OLD / f"annual_{i}.mat")
        assert item["sha256"] == expected_old[item["path"]]
    map_expected = next(x for x in upstream_manifest["files"] if x["path"] == "updateOpCond.m")
    assert record(author_map_path)["sha256"] == map_expected["sha256"]
    current_expected = {item["path"]: item["sha256"] for item in receipt["outputs"]}
    for path in [current_array_path, current_metric_path]:
        item = record(path)
        assert item["sha256"] == current_expected[item["path"]]

    code = author_map_path.read_text(encoding="utf-8")
    member_lists = []
    for variable in VARIABLES:
        assignment = re.search(r"branchId" + variable + r"\s*=\s*\[([^\]]+)\];", code).group(1)
        member_lists.append(np.array([int(v) for v in re.findall(r"-?\d+", assignment)]))
    observed_parts, predicted_parts = [], []
    max_saved_prediction_difference = 0.0
    for i in range(1, 5):
        d = loadmat(OLD / f"annual_{i}.mat", simplify_cells=True,
                    variable_names=["actual", "corrected_sim", "branch_pf", "status",
                                    "first_hour", "last_hour", "base_case"])
        assert d["first_hour"] == (i-1)*2190+1 and d["last_hour"] == i*2190
        assert np.asarray(d["status"], bool).all()
        case = d["base_case"]
        assert case["bus"].shape[0] == 57 and case["branch"].shape[0] == 94
        stored_map = np.asarray(case["if"]["map"], int)
        for map_id, terms in zip(MAP_IDS, member_lists):
            assert np.array_equal(stored_map[stored_map[:, 0] == map_id, 1], terms)
        pf = np.asarray(d["branch_pf"], float)
        assert pf.shape == (2190, 94)
        prediction = np.column_stack([np.sum(pf[:, np.abs(terms)-1] * np.sign(terms), axis=1)
                                      for terms in member_lists])
        max_saved_prediction_difference = max(max_saved_prediction_difference,
                                             float(np.max(np.abs(prediction-d["corrected_sim"]))))
        observed_parts.append(np.asarray(d["actual"], float))
        predicted_parts.append(prediction)
    obs19 = np.concatenate(observed_parts)
    pred19 = np.concatenate(predicted_parts)
    assert obs19.shape == pred19.shape == (8760, 7)
    assert max_saved_prediction_difference < 1e-9

    z = np.load(current_array_path, allow_pickle=False)
    assert z["interface_names"].tolist() == NAMES
    assert np.array_equal(z["hour_index"], np.arange(1, 8761))
    mask = z["candidate_qualified"].astype(bool)
    assert mask.sum() == 8651 and np.array_equal(mask, z["source_qualified"])
    obs25 = z["observed"][mask]
    # The scorer already divides aggregate model MW once by gamma.
    pred25 = z["candidate_" + CURRENT_OPERATOR][mask]
    times25 = pd.to_datetime(z["timestamp_utc"], utc=True)
    source = pd.read_csv(source_observation_path)
    quality = pd.read_csv(source_quality_path)
    assert source.timestamp_utc.tolist() == z["timestamp_utc"].tolist()
    assert source.timestamp_utc.tolist() == quality.timestamp_utc.tolist()
    source_obs = source[NAMES].to_numpy(float)
    source_ok = quality[NAMES].apply(lambda c: c.astype(str).str.lower().eq("true")).to_numpy(bool)
    assert source_ok[mask].all()
    source_delta = float(np.max(np.abs(source_obs[mask]-obs25)))
    assert source_delta < 1e-8
    all_source_mask = source_ok.all(axis=1) & np.isfinite(source_obs).all(axis=1)
    assert all_source_mask.sum() == 8673

    saved_old = pd.read_csv(old_metric_path).query("operator == @OLD_OPERATOR").set_index("interface")
    saved_current = pd.read_csv(current_metric_path).query(
        "cohort == 'candidate_all_success' and period == 'annual' and model == 'candidate' and convention == @CURRENT_OPERATOR"
    ).set_index("interface")
    comparisons, observed_rows, monthly_rows = [], [], []
    max_metric_difference = 0.0
    months19 = pd.date_range("2019-01-01", periods=8760, freq="h").month.to_numpy()
    months25 = times25.tz_convert("America/New_York").month.to_numpy()
    for j, (name, old_name) in enumerate(zip(NAMES, OLD_NAMES)):
        old = metric(pred19[:, j], obs19[:, j])
        new = metric(pred25[:, j], obs25[:, j])
        for key, saved_key in [("MAE_MW", "MAE_public_MW"), ("WAPE_percent", "WAPE_percent")]:
            max_metric_difference = max(max_metric_difference, abs(old[key]-float(saved_old.loc[old_name, saved_key])))
        for key, saved_key in [("MAE_MW", "mae_public_MW"), ("WAPE_percent", "wape_percent")]:
            max_metric_difference = max(max_metric_difference, abs(new[key]-float(saved_current.loc[name, saved_key])))
        a0, a1 = old["MAE_MW"], new["MAE_MW"]
        d0, d1 = old["mean_abs_observed_MW"], new["mean_abs_observed_MW"]
        mae_effect = 50 * (a1-a0) * (1/d0+1/d1)
        denominator_effect = 50 * (a0+a1) * (1/d1-1/d0)
        delta_wape = new["WAPE_percent"]-old["WAPE_percent"]
        assert abs(mae_effect+denominator_effect-delta_wape) < 1e-10
        assert abs(new["WAPE_percent"]/old["WAPE_percent"]-(a1/a0)/(d1/d0)) < 1e-10
        row = {"interface": name, "2019_operator": OLD_OPERATOR,
               "2025_operator": CURRENT_OPERATOR, "2019_hours": 8760, "2025_hours": 8651,
               **{f"2019_{k}": v for k, v in old.items() if k != "hours"},
               **{f"2025_{k}": v for k, v in new.items() if k != "hours"},
               "delta_MAE_MW": a1-a0, "delta_MAE_percent": 100*(a1/a0-1),
               "delta_WAPE_percentage_points": delta_wape,
               "delta_WAPE_relative_percent": 100*(new["WAPE_percent"]/old["WAPE_percent"]-1),
               "delta_mean_abs_observed_MW": d1-d0,
               "delta_mean_abs_observed_percent": 100*(d1/d0-1),
               "arithmetic_MAE_effect_on_WAPE_pp": mae_effect,
               "arithmetic_denominator_effect_on_WAPE_pp": denominator_effect,
               "2025_MAE_over_2019_flow_denominator_percent": 100*a1/d0,
               "2019_MAE_over_2025_flow_denominator_percent": 100*a0/d1,
               "controlled_same_inputs_comparison": False}
        comparisons.append(row)
        populations = [
            (2019, "authors_prepared_local_8760", obs19[:, j], months19),
            (2025, "current_AC_eligible_physical_8651", obs25[:, j], months25[mask]),
            (2025, "all_P32_source_qualified_physical_8673", source_obs[all_source_mask, j], months25[all_source_mask]),
        ]
        for year, cohort, values, months in populations:
            observed_rows.append({"year": year, "cohort": cohort, "interface": name, **characteristics(values)})
            for month in range(1, 13):
                use = months == month
                monthly_rows.append({"year": year, "cohort": cohort, "interface": name,
                                     "local_month": month, **characteristics(values[use])})
    assert max_metric_difference < 1e-9
    frame = pd.DataFrame(comparisons)
    observed_frame = pd.DataFrame(observed_rows)
    monthly_frame = pd.DataFrame(monthly_rows)
    current_rows = []
    for j, row in enumerate(comparisons):
        current_rows.append({
            "interface": row["interface"],
            "mae_2019_MW": row["2019_MAE_MW"], "mae_2025_MW": row["2025_MAE_MW"],
            "delta_mae_MW": row["delta_MAE_MW"], "delta_mae_percent": row["delta_MAE_percent"],
            "wape_2019_percent": row["2019_WAPE_percent"], "wape_2025_percent": row["2025_WAPE_percent"],
            "delta_wape_pp": row["delta_WAPE_percentage_points"],
            "mean_abs_flow_2019_MW": row["2019_mean_abs_observed_MW"],
            "mean_abs_flow_2025_MW": row["2025_mean_abs_observed_MW"],
            "delta_mean_abs_flow_percent": row["delta_mean_abs_observed_percent"],
            "mean_signed_flow_2019_MW": float(obs19[:, j].mean()),
            "mean_signed_flow_2025_MW": float(obs25[:, j].mean()),
            "negative_hours_2019_percent": float(100*np.mean(obs19[:, j] < 0)),
            "negative_hours_2025_percent": float(100*np.mean(obs25[:, j] < 0)),
        })
    paths = [OUT / "2019_comparison_metrics.csv", OUT / "2019_comparison_observed_characteristics.csv",
             OUT / "2019_comparison_observed_monthly.csv", OUT / "2019_comparison_current.csv"]
    for data, path in zip([frame, observed_frame, monthly_frame, pd.DataFrame(current_rows)], paths):
        data.to_csv(path, index=False)

    pooled_old = metric(pred19.reshape(-1), obs19.reshape(-1))
    pooled_new = metric(pred25.reshape(-1), obs25.reshape(-1))
    sensitivity = []
    for name in NAMES:
        a = observed_frame.query("interface == @name and cohort == 'current_AC_eligible_physical_8651'").iloc[0]
        b = observed_frame.query("interface == @name and cohort == 'all_P32_source_qualified_physical_8673'").iloc[0]
        sensitivity.append({"interface": name, "scored_mean_abs_MW": float(a.mean_abs_MW),
                            "all_source_mean_abs_MW": float(b.mean_abs_MW),
                            "all_source_minus_scored_mean_abs_MW": float(b.mean_abs_MW-a.mean_abs_MW),
                            "all_source_minus_scored_signed_mean_MW": float(b.signed_mean_MW-a.signed_mean_MW),
                            "all_source_minus_scored_negative_percentage_points": float(b.negative_percent-a.negative_percent)})
    assert before == [record(path) for path in deps]
    report = {
        "passed": True, "created_utc": datetime.now(timezone.utc).isoformat(),
        "checkout_HEAD": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "method": "Fresh read-only rescore of saved hourly results; no PF or model/source edits.",
        "baseline": {"model": "authors released57bus94ACbranch DC model", "upstream_commit": upstream_manifest["commit"],
                     "year": 2019, "hours": 8760, "operator": OLD_OPERATOR,
                     "observations": "Authors prepared2019 observation arrays, including their missing/DST preparation.",
                     "clock": "8760 naive local-hour labels; not asserted to be the same physical-hour treatment as2025."},
        "current": {"model": "moses_repair_v1", "year": 2025, "hours": 8651,
                    "operator": CURRENT_OPERATOR, "calendar_hours": 8760,
                    "all_source_observation_hours": 8673,
                    "clock": "Physical UTC hours within local NewYork2025; source/solver eligible mask frozen.",
                    "power_scale": "Public MW; candidate npz already divided by gamma once; no additional scaling.",
                    "gamma": float(z["gamma"])},
        "definitions": {"MAE": "mean(abs(predicted-observed))",
                        "WAPE_percent": "100*sum(abs(predicted-observed))/sum(abs(observed)) =100*MAE/mean(abs(observed))",
                        "delta_MAE_percent": "100*(MAE2025/MAE2019-1)",
                        "delta_WAPE_percentage_points": "WAPE2025-WAPE2019",
                        "observation_spread": "Population SD (ddof0), NumPy linear quantiles; negative share uses signed reported numeric series.",
                        "WAPE_arithmetic_decomposition": "Two-factor order-averaged effects for a=MAE,d=mean|observed|: MAE effect=50*(a1-a0)*(1/d0+1/d1); denominator effect=50*(a0+a1)*(1/d1-1/d0). Effects sum exactly to deltaWAPE; not causal attribution."},
        "checks": {"saved2019_manifest_hashes_verified": 4, "pinned_author_map_hash_verified": True,
                   "current_arrays_and_metrics_receipt_hashes_verified": True,
                   "authors_source_map_equals_saved_map_all_partitions": True,
                   "maximum_author_ifmap_vs_saved_prediction_difference_MW": max_saved_prediction_difference,
                   "maximum_metric_rescore_discrepancy": max_metric_difference,
                   "2025_source_CSV_vs_scoring_observation_max_difference_MW": source_delta,
                   "WAPE_identity_and_decomposition_all_seven_passed": True,
                   "source_hashes_unchanged_after_analysis": True,
                   "older2025_comparison_table_not_used": True},
        "comparison": comparisons, "observed_characteristics": observed_rows,
        "2025_source_coverage_sensitivity": sensitivity,
        "pooled_context": {"2019": pooled_old, "2025": pooled_new,
                           "qualification": "Combines overlapping interfaces, not a statewide energy metric; hours here are interface-hour comparison counts."},
        "limitations": [
            "Cross-year benchmark only:2019 and2025 differ in load,generation,control inputs,topology,physics and selected hours. It cannot isolate the causal effect of downstate refinements.",
            "2019 author if.map and2025 legacy_signed_literal_from are distinct declared operators; physical interface-meter equivalence across years and dated P32 membership/terminal conventions remain uncertified.",
            "Negative percentages and mean-sign changes describe reported/prepared numeric observations, not independently certified reversal of the same physical interface.",
            "2019 observations retain released interpolation/repeated-hour preparation;2025 uses explicit physicalUTC hours and gap-aware forward-hold source aggregation. No attempt was made to harmonize or refill them.",
            "2025 all-source sensitivity covers8673 qualified observation hours, not a complete unbroken8760-hour record.87 gaps remain unavailable; no fill is used.",
            "WAPE changes decompose arithmetically into error magnitude and observed-flow denominator changes; these are not separate causal effects on physical accuracy.",
            "WAPE is recomputed from released outputs, not the paper's originally published limit-normalized statistic. Stale literal flow4Plot indices are not the selected2019 measurement operator.",
            "Current2025 equation-qualified results still have zero full-operating-qualified hours; no current physical-meter or installed-asset certification is implied.",
        ],
        "source_files": before, "outputs": [record(path) for path in paths],
        "producer": record(Path(__file__)),
    }
    report_path = OUT / "2019_comparison_review.json"
    report_path.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(frame[["interface", "2019_MAE_MW", "2025_MAE_MW", "delta_MAE_MW",
                 "2019_WAPE_percent", "2025_WAPE_percent", "delta_WAPE_percentage_points",
                 "2019_mean_abs_observed_MW", "2025_mean_abs_observed_MW",
                 "delta_mean_abs_observed_percent"]].to_string(index=False))
    print(json.dumps({"passed": True, "maximum_metric_discrepancy": max_metric_difference,
                      "output_files": [p.relative_to(ROOT).as_posix() for p in [*paths, report_path]]}))


if __name__ == "__main__":
    main()
