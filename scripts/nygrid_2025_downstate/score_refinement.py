"""Post-hoc fixed-cohort comparison. This module never selects network parameters."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

from replay_refinement import BASELINE, DEFAULT, ROOT, require, sha

NAMES = ["DYSINGER EAST", "WEST CENTRAL", "TOTAL EAST", "MOSES SOUTH", "CENTRAL EAST - VC", "UPNY CONED", "SPR/DUN-SOUTH"]
LABELS = {"baseline": "Original network", "expanded_identity": "Identity expansion",
    "source_detail_2019": "Historical station detail", "upgrades_year_end": "Year-end upgrades",
    "upgrades_dated": "Dated upgrades", "assets_year_end": "Year-end + asset mapping",
    "assets_dated": "Dated + asset mapping", "nyes_assumption_year_end": "NYES assumption scenario"}


def metrics(prediction, observation):
    error = prediction - observation
    return dict(mae_public_equivalent_mw=float(np.abs(error).mean()),
        rmse_public_equivalent_mw=float(np.sqrt(np.mean(error ** 2))), bias_public_equivalent_mw=float(error.mean()),
        wape_percent=float(100 * np.abs(error).sum() / np.abs(observation).sum()),
        mean_prediction_public_equivalent_mw=float(prediction.mean()), mean_observation_public_mw=float(observation.mean()))


def score(folder=DEFAULT, figures=True):
    folder = Path(folder).resolve()
    out = folder / "comparison"
    out.mkdir(parents=True, exist_ok=True)
    d = loadmat(BASELINE / "dispatch.mat", simplify_cells=True,
                variable_names=["hour_index", "timestamp_utc", "gamma", "dispatch_qualified"])
    old = loadmat(BASELINE / "dispatch_network.mat", simplify_cells=True)
    provenance = json.loads((folder / "replay/provenance.json").read_text())
    require(provenance["observation_data_read"] is False, "Replay must be independent of observations")
    for dependency in provenance["dependencies"]:
        require(sha(ROOT / dependency["path"]) == dependency["sha256"], "Replay dependency changed")
    observed_path = ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv"
    observed = pd.read_csv(observed_path)
    require(np.array_equal(observed.timestamp_utc.astype(str), np.asarray(d["timestamp_utc"]).astype(str)), "Observation time axis differs")
    qualified = np.asarray(d["dispatch_qualified"], bool)
    actual = observed[NAMES].to_numpy(float)
    require(np.isfinite(actual[qualified]).all(), "Observation missing on fixed qualified cohort")
    require(qualified.sum() == 8663, "Fixed source cohort changed")
    gamma = float(d["gamma"])
    predictions = {"baseline": old["inherited_interface_pf"] / gamma}
    for item in provenance["variants"]:
        path = ROOT / item["file"]
        require(sha(path) == item["sha256"], "Replay output changed")
        r = loadmat(path, simplify_cells=True, variable_names=["hour_index", "qualified", "interface_pf"])
        require(np.array_equal(r["hour_index"], d["hour_index"]) and np.array_equal(r["qualified"].astype(bool), qualified), "Variant cohort changed")
        require(np.isfinite(r["interface_pf"][qualified]).all(), "Variant prediction missing")
        predictions[item["variant"]] = r["interface_pf"] / gamma
    months = pd.to_datetime(observed.timestamp_utc, utc=True).dt.tz_convert("America/New_York").dt.month.to_numpy()
    rows, monthly, hourly, changes = [], [], [], []
    baseline_scores = {}
    for name, pred in predictions.items():
        for j, interface in enumerate(NAMES):
            values = metrics(pred[qualified, j], actual[qualified, j])
            if name == "baseline":
                baseline_scores[interface] = values
            before = baseline_scores[interface]
            row = dict(variant=name, interface=interface, hours=int(qualified.sum()), **values,
                wape_change_percentage_points=values["wape_percent"] - before["wape_percent"],
                mae_change_public_equivalent_mw=values["mae_public_equivalent_mw"] - before["mae_public_equivalent_mw"],
                physical_2025_flowgate_membership_verified=False, observations_used_to_select_parameters=False)
            rows.append(row)
            for month in range(1, 13):
                selected = qualified & (months == month)
                monthly.append(dict(variant=name, interface=interface, month=month, hours=int(selected.sum()),
                    **metrics(pred[selected, j], actual[selected, j])))
            hourly.append(pd.DataFrame(dict(hour_index=d["hour_index"], timestamp_utc=observed.timestamp_utc,
                variant=name, interface=interface, scored=qualified, predicted_public_equivalent_mw=pred[:, j],
                observed_public_mw=actual[:, j])))
    for from_name, to_name, cause in [("baseline", "expanded_identity", "algebraic_identity"),
        ("baseline", "source_detail_2019", "historical_detail_and_declared_attachments"),
        ("source_detail_2019", "upgrades_year_end", "project_topology_fixed_year_end"),
        ("upgrades_year_end", "assets_year_end", "same_zone_plant_and_load_relocation"),
        ("assets_year_end", "assets_dated", "commissioning_chronology"),
        ("assets_year_end", "nyes_assumption_year_end", "unresolved_NYES_overlap_scenario")]:
        for j, interface in enumerate(NAMES):
            delta = predictions[to_name][qualified, j] - predictions[from_name][qualified, j]
            changes.append(dict(from_variant=from_name, to_variant=to_name, change=cause, interface=interface,
                hours=int(qualified.sum()), mean_signed_flow_change_public_equivalent_mw=float(delta.mean()),
                mean_absolute_flow_change_public_equivalent_mw=float(abs(delta).mean()),
                maximum_absolute_flow_change_public_equivalent_mw=float(abs(delta).max())))
    summary = pd.DataFrame(rows)
    month_frame = pd.DataFrame(monthly)
    summary.to_csv(out / "interface_summary.csv", index=False, lineterminator="\n")
    month_frame.to_csv(out / "monthly_interface_summary.csv", index=False, lineterminator="\n")
    pd.DataFrame(changes).to_csv(out / "staged_flow_changes.csv", index=False, lineterminator="\n")
    pd.concat(hourly, ignore_index=True).to_csv(out / "interface_hourly.csv.gz", index=False,
        lineterminator="\n", compression={"method": "gzip", "mtime": 0})
    receipt = dict(status="complete_paired_unfitted_proxy_comparison", qualified_hours=int(qualified.sum()),
        gamma=gamma, observed_sha256=sha(observed_path), replay_provenance_sha256=sha(folder / "replay/provenance.json"),
        scoring_code_sha256=sha(Path(__file__)), errors_reduced_is_not_a_construction_requirement=True,
        physical_2025_flowgate_membership_verified=False,
        limitations=["Legacy accounting-zone functionals are comparable but not certified physical flowgates",
                     "Year-end topology applied to all hours is a counterfactual, not historical chronology",
                     "No interface observations entered dispatch, topology, injection maps or parameter choices"])
    (out / "scoring_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if figures:
        make_figures(out, summary, month_frame)
    print(summary.loc[summary.interface.isin(NAMES[-2:]), ["variant", "interface", "wape_percent", "mae_public_equivalent_mw"]].to_string(index=False))
    return receipt


def make_figures(out, summary, monthly):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.labelcolor": "#253144", "text.color": "#253144"})
    colors = {"baseline": "#758295", "upgrades_dated": "#31688E", "assets_dated": "#BC6B2E"}
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2), constrained_layout=True)
    for j, name in enumerate(NAMES[-2:]):
        variants = ["baseline", "source_detail_2019", "upgrades_dated", "assets_dated", "assets_year_end", "nyes_assumption_year_end"]
        series = summary[summary.interface.eq(name)].set_index("variant").loc[variants]
        values = series.wape_percent.to_numpy()
        y = np.arange(len(values))
        axes[j].barh(y, values, color=[colors.get(v, "#97B4C5") for v in variants], height=.62)
        axes[j].set_yticks(y, [LABELS[v] for v in variants])
        axes[j].invert_yaxis()
        axes[j].set_xlim(0, max(values) * 1.2)
        for yi, val in zip(y, values):
            axes[j].text(val + max(values)*.02, yi, f"{val:.2f}%", va="center")
        axes[j].set_xlabel("WAPE (%) = sum |prediction − observation| / sum |observation|")
        axes[j].set_title(name)
        axes[j].grid(axis="x", alpha=.15)
        axes[j].set_axisbelow(True)
    fig.suptitle("Downstate interface proxy errors • same 8,663 hours, fixed generator outputs", fontsize=13)
    for suffix in ["png", "pdf"]:
        fig.savefig(out / ("downstate_error_comparison."+suffix), dpi=170, bbox_inches="tight")
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 7.4), constrained_layout=True)
    for j, name in enumerate(NAMES[-2:]):
        base = monthly[monthly.interface.eq(name) & monthly.variant.eq("baseline")]
        axes[j, 0].plot(base.month, base.mean_observation_public_mw, color="#253144", linewidth=2, label="NYISO observation")
        for variant, color in colors.items():
            data = monthly[monthly.interface.eq(name) & monthly.variant.eq(variant)]
            axes[j, 0].plot(data.month, data.mean_prediction_public_equivalent_mw, color=color,
                            linestyle={"baseline": "--", "upgrades_dated": "-.", "assets_dated": "-"}[variant],
                            marker="o", markersize=3, label=LABELS[variant])
            axes[j, 1].plot(data.month, data.wape_percent, color=color, marker="o", markersize=3,
                            linestyle={"baseline": "--", "upgrades_dated": "-.", "assets_dated": "-"}[variant], label=LABELS[variant])
        axes[j, 0].set_title(name + " • monthly mean flow")
        axes[j, 1].set_title(name + " • monthly WAPE")
        axes[j, 0].set_ylabel("Public-equivalent MW")
        axes[j, 1].set_ylabel("WAPE (%)")
        for ax in axes[j]:
            ax.set_xticks(range(1, 13), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
            ax.grid(alpha=.17)
            ax.axhline(0, color="#253144", linewidth=.6, alpha=.4)
        axes[j, 0].legend(fontsize=8, loc="best")
    axes[0, 1].text(.03, .06, "All three model series coincide:\nfixed net injection across the same cut.",
                    transform=axes[0, 1].transAxes, fontsize=9, color="#253144")
    fig.suptitle("2025 paired replay • dated commissioning • no parameter fitting to interface observations", fontsize=13)
    for suffix in ["png", "pdf"]:
        fig.savefig(out / ("downstate_monthly_comparison."+suffix), dpi=170, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=DEFAULT)
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args()
    score(args.folder, not args.no_figures)
