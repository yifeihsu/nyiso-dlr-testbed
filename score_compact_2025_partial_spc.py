"""Score previously exposed NYISO hours as year-end-topology diagnostics.

No predictions are altered and no fitting or optimization is performed.
Earlier-year inputs are counterfactual stress cases, not historical replays.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score(folder: Path) -> dict:
    manifest = pd.read_csv(folder / "campaign_manifest.csv")
    if len(manifest) != 1 or manifest.iloc[0]["artifact"] != "campaign.mat":
        raise ValueError("Expected one saved campaign identity")
    campaign = folder / "campaign.mat"
    if digest(campaign) != manifest.iloc[0]["sha256"]:
        raise ValueError("Campaign bytes changed")
    flow_file = folder / "target_free_interface_flows.csv"
    source_file = ROOT / "output/compact_ny_2025/generation_reconstruction/scored_interface_comparison.csv"
    flows = pd.read_csv(flow_file)
    source = pd.read_csv(source_file)
    key = ["scenario_id", "interface_name"]
    if flows.duplicated(["variant_id"] + key).any() or source.duplicated(key).any():
        raise ValueError("Duplicate prediction or target identity")
    if not flows["target_flow_mw"].isna().all() or flows["used_in_optimizer"].astype(bool).any():
        raise ValueError("Expected target-free predictions")
    targets = source[key + ["target_flow_mw", "actual_flow_mw", "scale_factor_gamma",
                            "target_coverage_qualified", "model_flow_mw", "absolute_residual_mw"]].rename(
        columns={"model_flow_mw": "parent_model_flow_mw", "absolute_residual_mw": "parent_absolute_error_mw"})
    joined = flows.drop(columns=["target_flow_mw", "residual_mw", "absolute_residual_mw"]).merge(
        targets, on=key, how="left", validate="many_to_one", indicator=True)
    if not joined["_merge"].eq("both").all():
        raise ValueError("A prediction lacks a registered comparison hour")
    joined = joined.drop(columns="_merge")
    coverage = joined["target_coverage_qualified"].astype(str).str.lower().isin(["true", "1"])
    physical = joined["electrically_qualified"].astype(str).str.lower().isin(["true", "1"])
    finite = np.isfinite(joined[["model_flow_mw", "target_flow_mw"]]).all(axis=1)
    joined["diagnostic_score_qualified"] = physical & coverage & finite
    joined["residual_mw"] = (joined["model_flow_mw"] - joined["target_flow_mw"]).where(joined.diagnostic_score_qualified)
    joined["absolute_error_mw"] = joined.residual_mw.abs()
    joined["normalized_absolute_error_floor100"] = joined.absolute_error_mw / joined.target_flow_mw.abs().clip(lower=100)
    joined["scope"] = "revisited_year_end_topology_counterfactual_not_historical_as_operated_or_fresh_holdout"
    joined["topology_as_of"] = "2025-12-31"
    joined["parameters_or_dispatch_fitted_to_interfaces"] = False
    summary = joined.groupby(["variant_id", "scenario_id"], sort=False).agg(
        qualified_interfaces=("diagnostic_score_qualified", "sum"),
        mean_absolute_error_mw=("absolute_error_mw", "mean"),
        max_absolute_error_mw=("absolute_error_mw", "max"),
        mean_normalized_error_floor100=("normalized_absolute_error_floor100", "mean"),
        parent_mean_absolute_error_mw=("parent_absolute_error_mw", "mean")).reset_index()
    joined.to_csv(folder / "revisited_interface_comparison.csv", index=False, lineterminator="\n")
    summary.to_csv(folder / "revisited_interface_summary.csv", index=False, lineterminator="\n")
    evidence = {
        "campaign_sha256": digest(campaign), "prediction_csv_sha256": digest(flow_file),
        "previously_exposed_target_csv_sha256": digest(source_file),
        "scorer_sha256": digest(Path(__file__)), "fresh_holdout_validation": False,
        "historical_as_operated_reconstruction": False, "optimizer_called": False,
        "scored_prediction_rows": int(joined.diagnostic_score_qualified.sum()),
        "registered_prediction_rows": len(joined), "topology_as_of": "2025-12-31",
        "result_csv_sha256": digest(folder / "revisited_interface_comparison.csv"),
        "summary_csv_sha256": digest(folder / "revisited_interface_summary.csv"),
    }
    (folder / "revisited_scoring_manifest.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8", newline="\n")
    return evidence


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=ROOT / "output/compact_ny_2025/partial_spc")
    args = parser.parse_args()
    print(json.dumps(score(args.folder), indent=2))
