"""Select best historical examples from the frozen 2019 interface verification."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

from summarize_reproduction import INTERFACES, load_campaign, join_quality

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "output/nygrid_2019"
OUT = BASE / "best_snapshots"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    inputs = [BASE / f"annual_{i}_interfaces.csv" for i in range(1, 5)]
    inputs += [BASE / "nyiso_source_audit_hourly_quality.csv", Path(__file__).resolve(),
               Path(__file__).with_name("summarize_reproduction.py"), BASE / "verification_manifest.json"]
    hashes = {str(p): sha(p) for p in inputs}
    frozen = {r["path"]: r["sha256"] for r in json.loads(inputs[-1].read_text())["files"]}
    assert all(hashes[str(p)] == frozen[p.relative_to(ROOT).as_posix()] for p in inputs[:4]), "Frozen annual flow evidence changed"
    data = join_quality(load_campaign(inputs[:4], pilot=False), inputs[4])
    data["signed_error_mw"] = data.corrected_operator_mw - data.observed_mw
    data["absolute_error_mw"] = data.signed_error_mw.abs()
    data["absolute_observed_mw"] = data.observed_mw.abs()
    data["actual_flow_error_pct"] = np.where(data.absolute_observed_mw > 0,
        100 * data.absolute_error_mw / data.absolute_observed_mw, np.nan)
    data["paper_signed_error_pct"] = -100 * data.signed_error_mw / data.positive_limit_mw
    data["opposite_direction"] = np.sign(data.corrected_operator_mw) * np.sign(data.observed_mw) < 0
    ranked = data.groupby("timestamp", as_index=False).agg(
        interfaces=("interface", "nunique"),
        sum_absolute_error_mw=("absolute_error_mw", "sum"),
        sum_absolute_observed_mw=("absolute_observed_mw", "sum"),
        mean_absolute_error_mw=("absolute_error_mw", "mean"),
        max_interface_error_pct=("actual_flow_error_pct", "max"),
        defined_point_percentages=("actual_flow_error_pct", "count"),
        opposite_direction_interfaces=("opposite_direction", "sum"),
        imputed_interface_observations=("FlowMWH_imputed", "sum"),
        ambiguous_interface_observations=("fall_dst_ambiguous_hour", "sum"),
        minimum_sample_count=("sample_count", "min"),
        minimum_distinct_timestamp_count=("distinct_timestamp_count", "min"))
    assert len(ranked) == 8760 and (ranked.interfaces == 7).all()
    assert (ranked.sum_absolute_observed_mw > 0).all()
    ranked["pooled_proportional_error_pct"] = 100 * ranked.sum_absolute_error_mw / ranked.sum_absolute_observed_mw
    ranked = ranked.sort_values(["pooled_proportional_error_pct", "timestamp"]).reset_index(drop=True)
    ranked.insert(0, "pooled_rank", np.arange(1, len(ranked) + 1))
    # Minimax is a separate ranking; it never silently drops undefined ratios.
    minimax = ranked[ranked.defined_point_percentages == 7].sort_values(
        ["max_interface_error_pct", "pooled_proportional_error_pct", "timestamp"])
    minimax = minimax.assign(minimax_rank=np.arange(1, len(minimax) + 1))
    minimax_rank = dict(zip(minimax.timestamp, np.arange(1, len(minimax) + 1)))
    ranked["minimax_rank"] = ranked.timestamp.map(minimax_rank).astype("Int64")
    selected = ranked.head(3).copy()
    details = data[data.timestamp.isin(selected.timestamp)].copy()
    details["pooled_rank"] = details.timestamp.map(dict(zip(selected.timestamp, selected.pooled_rank)))
    details["interface_order"] = details.interface.map({name: i for i, name in enumerate(INTERFACES)})
    details = details.sort_values(["pooled_rank", "interface_order"])
    columns = ["pooled_rank", "timestamp", "interface", "observed_mw", "corrected_operator_mw",
               "signed_error_mw", "absolute_error_mw", "actual_flow_error_pct", "positive_limit_mw",
               "paper_signed_error_pct", "opposite_direction", "FlowMWH_imputed", "fall_dst_ambiguous_hour",
               "sample_count", "distinct_timestamp_count"]
    OUT.mkdir(parents=True, exist_ok=True)
    for filename, table in [("all_hour_rankings.csv", ranked), ("top_three_snapshots.csv", selected),
                            ("top_three_interface_errors.csv", details[columns]),
                            ("top_three_minimax_snapshots.csv", minimax.head(3))]:
        table.to_csv(OUT / filename, index=False, lineterminator="\n", float_format="%.12g", date_format="%Y-%m-%d %H:%M:%S")
    best = ranked.iloc[0]
    assert best.minimax_rank == 1, "The leading pooled snapshot is no longer the leading minimax snapshot"
    best_rows = details[details.pooled_rank == 1]
    assert (selected.imputed_interface_observations == 0).all() and (selected.ambiguous_interface_observations == 0).all()
    table = "| Interface | Observed MW | Model MW | Absolute error MW | Actual-flow error |\n|---|---:|---:|---:|---:|\n"
    for r in best_rows.itertuples():
        table += f"| {r.interface} | {r.observed_mw:.2f} | {r.corrected_operator_mw:.2f} | {r.absolute_error_mw:.2f} | {r.actual_flow_error_pct:.2f}% |\n"
    date_labels = [t.strftime("%b %d, %H:%M").replace(" 0", " ") for t in selected.timestamp]
    comparison = "| Interface | " + " | ".join(f"#{i}: {label}" for i, label in enumerate(date_labels, 1)) + " |\n|---|---:|---:|---:|\n"
    for name in INTERFACES:
        rows = details[details.interface == name].sort_values("pooled_rank")
        comparison += f"| {name} | " + " | ".join(f"{r.absolute_error_mw:.2f} MW / {r.actual_flow_error_pct:.2f}%" for r in rows.itertuples()) + " |\n"
    minimax_text = "; ".join(f"{r.timestamp:%b %d at %H:%M} ({r.max_interface_error_pct:.2f}% worst-interface error)" for r in minimax.head(3).itertuples())
    rank_table = "| Rank | 2019 New York local time | Pooled proportional error | Mean absolute error | Largest interface percentage error |\n|---|---|---:|---:|---:|\n"
    for r in selected.itertuples():
        rank_table += f"| {r.pooled_rank} | {r.timestamp:%Y-%m-%d %H:%M} | {r.pooled_proportional_error_pct:.4f}% | {r.mean_absolute_error_mw:.2f} MW | {r.max_interface_error_pct:.2f}% |\n"
    reverse = details[details.opposite_direction]
    reverse_note = ""
    for r in reverse.itertuples():
        reverse_note += f"On {r.timestamp:%B %d at %H:%M}, {r.interface} reverses direction: observed {r.observed_mw:.3f} MW versus modeled {r.corrected_operator_mw:.3f} MW. The {r.absolute_error_mw:.2f}-MW mismatch is {r.actual_flow_error_pct:.2f}% of that small observed flow. A low pooled error can therefore conceal a poor individual interface result.\n\n"
    report = f"""# Best-performing 2019 NYgrid snapshots

The best snapshot is **{best.timestamp:%B %d, %Y at %H:%M} New York local time**. Its pooled proportional error is **{best.pooled_proportional_error_pct:.4f}%**, and every individual interface is within **{best.max_interface_error_pct:.2f}%** of observed flow. It ranks first both by pooled proportional error and by minimizing the worst individual percentage error.

The selection uses the frozen 57-bus NYgrid DC results with the previously corrected interface measurements. All 8,760 snapshots, each with seven interfaces, were ranked by `100 * sum(abs(model - observed)) / sum(abs(observed))`, with earlier timestamp breaking any tie. No model or dispatch was changed and no additional power-flow solve was required. The selected three hours have no interpolated or fall-DST-ambiguous interface observations.

## Best snapshot: observed and modeled flows

{table}
Per-interface percentage error is `100 * abs(model - observed) / abs(observed)`. It uses actual flow, not the paper's positive-limit denominator. The signed residual (model minus observed), paper-style percentage, and raw input-quality counts are retained in the CSV.

## Three lowest pooled-error snapshots

{rank_table}
Every cell below shows absolute MW error followed by actual-flow percentage error.

{comparison}
{reverse_note}The [separate minimax ranking](top_three_minimax_snapshots.csv) identifies the three hours with the lowest worst-interface percentage error: {minimax_text}. This is a different explicit selection criterion, not an undisclosed replacement of the primary ranking.

These are deliberately selected best-case historical examples, not representative or held-out validation. The previous full-year pooled error remains **11.22%**. The original DC method does not enforce operating bounds; low interface error does not establish AC or thermal feasibility.

Run `python scripts/nygrid_2019/select_best_snapshots.py` from the repository root to regenerate the ranking and tables. The existing NYISO source-quality CSV can be regenerated with the prior source-audit workflow if absent. All original annual artifacts remain unchanged.
"""
    (OUT / "BEST_SNAPSHOTS.md").write_text(report, encoding="utf-8", newline="\n")
    policy = {"ranked_hours": 8760, "interfaces_per_hour": 7, "selected_hours": 3,
              "primary_criterion": "minimum pooled actual-flow proportional error, then timestamp",
              "alternative_criterion": "minimum worst defined individual interface percentage error, then pooled error and timestamp",
              "operator": "previously verified corrected released if.map",
              "selection_uses_observed_errors": True, "representative_or_heldout": False,
              "new_model_solves": False, "best_timestamp": str(best.timestamp),
              "best_pooled_error_pct": float(best.pooled_proportional_error_pct),
              "best_max_interface_error_pct": float(best.max_interface_error_pct),
              "best_is_also_minimax": bool(best.minimax_rank == 1), "denominator_floor_mw": None,
              "source_inputs": [{"path": p.relative_to(ROOT).as_posix(), "sha256": hashes[str(p)]} for p in inputs]}
    assert all(sha(p) == hashes[str(p)] for p in inputs), "Source artifacts changed during selection"
    policy["artifacts"] = [{"path": p.name, "sha256": sha(p)} for p in sorted(OUT.iterdir()) if p.name != "selection_manifest.json"]
    (OUT / "selection_manifest.json").write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(selected[["pooled_rank", "timestamp", "pooled_proportional_error_pct", "max_interface_error_pct"]].to_string(index=False))
    print(best_rows[columns].to_string(index=False))

if __name__ == "__main__":
    main()
