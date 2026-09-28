"""Summarize the released 2019 DC model, keeping two operator definitions.

Primary replication retains all 8,760 timezone-naive local hourly labels,
including the released interpolation and DST treatment. Corrections to the
plotting indices come from the released if.map and bus-zone identities, not
observations. Metrics never use a denominator floor or change the DC solution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2019"
INTERFACES = {
    "Dysinger East": "DYSINGER EAST",
    "West Central": "WEST CENTRAL",
    "Total East": "TOTAL EAST",
    "Moses South": "MOSES SOUTH",
    "Central East": "CENTRAL EAST - VC",
    "UpNY-Coned": "UPNY CONED",
    "Dun/SPR-South": "SPR/DUN-SOUTH",
}
VARIANTS = {
    "literal_released_plot": "released_plot_mw",
    "corrected_released_if_map": "corrected_operator_mw",
}
METRIC_POLICY = {
    "paper_signed_error_pct": "100*(observed-simulated)/hourly_positive_limit; positive limit also used for reverse flow",
    "actual_flow_wape_pct": "100*sum(abs(simulated-observed))/sum(abs(observed)); includes errors at zero observed flow",
    "mape_nonzero_actual_pct": "mean(100*abs(simulated-observed)/abs(observed)) only where observed != 0; undefined rows counted explicitly; no floor",
    "zero_denominators": "pointwise percentage is undefined at exactly zero observed flow; WAPE undefined when the aggregate absolute-observation sum is zero",
    "sign_errors": "simulated and observed have strictly opposite nonzero signs; zero predictions counted separately",
    "paper_quantiles": "linear interpolation at 2.5,25,50,75,97.5 percent of signed limit-normalized errors",
    "overall": "pools seven overlapping interface comparisons; not a statewide independent energy-balance error",
    "primary": "all 8760 naive local 2019 hour labels, including source imputation and ambiguous DST hour",
    "sensitivity": "provided filter_unimputed_unambiguous_hour only; this removes imputed flow and fall-DST ambiguity, not every irregular sample/gap",
    "physical_scope": "released DC power flow; success does not establish bounded AC feasibility or installed-equipment thermal validation",
    "power_units": "released model and observations use the numerical MW convention of plotFlow; no benchmark gamma or time-integration rescaling",
}


def metrics(simulated: Any, observed: Any, positive_limit: Any) -> dict[str, Any]:
    """Numerical metrics with explicit zeros and no small-flow denominator floor."""
    sim, obs, limit = (np.asarray(x, dtype=float) for x in (simulated, observed, positive_limit))
    if sim.ndim != 1 or not len(sim) or sim.shape != obs.shape or obs.shape != limit.shape:
        raise ValueError("Metric vectors must be equal nonempty one-dimensional arrays")
    if not all(np.isfinite(x).all() for x in (sim, obs, limit)) or np.any(limit <= 0):
        raise ValueError("All evaluated flows and strictly positive limits must be finite")
    residual = sim - obs
    absolute = np.abs(residual)
    denominator = np.abs(obs).sum()
    nonzero = obs != 0
    point = 100 * absolute[nonzero] / np.abs(obs[nonzero])
    paper = -100 * residual / limit
    quantiles = np.quantile(paper, [.025, .25, .5, .75, .975], method="linear")
    return {
        "observations": int(len(sim)),
        "sum_absolute_error_mw": float(absolute.sum()),
        "sum_absolute_observed_mw": float(denominator),
        "actual_flow_wape_pct": float(100 * absolute.sum() / denominator) if denominator else None,
        "mae_mw": float(absolute.mean()),
        "rmse_mw": float(np.sqrt(np.mean(residual ** 2))),
        "bias_sim_minus_observed_mw": float(residual.mean()),
        "mape_nonzero_actual_pct": float(point.mean()) if len(point) else None,
        "max_nonzero_actual_error_pct": float(point.max()) if len(point) else None,
        "mape_defined_observations": int(nonzero.sum()),
        "zero_actual_flow_count": int((~nonzero).sum()),
        "min_absolute_observed_mw": float(np.abs(obs).min()),
        "min_nonzero_absolute_observed_mw": float(np.abs(obs[nonzero]).min()) if nonzero.any() else None,
        "opposite_direction_count": int(np.sum(np.sign(sim) * np.sign(obs) < 0)),
        "opposite_direction_fraction": float(np.mean(np.sign(sim) * np.sign(obs) < 0)),
        "zero_prediction_nonzero_actual_count": int(np.sum((sim == 0) & nonzero)),
        "positive_limit_9999_count": int(np.sum(limit == 9999)),
        "paper_error_q025_pct": float(quantiles[0]),
        "paper_error_q25_pct": float(quantiles[1]),
        "paper_error_median_pct": float(quantiles[2]),
        "paper_error_q75_pct": float(quantiles[3]),
        "paper_error_q975_pct": float(quantiles[4]),
        "fraction_absolute_paper_error_le_10pct": float(np.mean(np.abs(paper) <= 10)),
        "fraction_absolute_paper_error_le_15pct": float(np.mean(np.abs(paper) <= 15)),
    }


def booleans(series: pd.Series, label: str) -> pd.Series:
    values = series.astype(str).str.strip().str.lower()
    if not values.isin(["true", "false", "1", "0"]).all():
        raise ValueError(f"Unrecognized boolean in {label}")
    return values.isin(["true", "1"])


def load_campaign(paths: list[Path], *, pilot: bool) -> pd.DataFrame:
    if not pilot and len(paths) != 4:
        raise ValueError("Annual summary requires all four completed worker CSVs")
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError("Workers have not all completed: " + ", ".join(missing))
    frames = []
    for path in paths:
        frame = pd.read_csv(path)
        frame["worker_file"] = path.name
        frames.append(frame)
    frame = pd.concat(frames, ignore_index=True)
    frame["timestamp"] = pd.to_datetime(frame.timestamp, format="%d-%b-%Y %H:%M:%S", errors="raise")
    if frame.duplicated(["timestamp", "interface"]).any():
        raise ValueError("Duplicate interface/hour keys or overlapping worker partitions")
    if set(frame.interface) != set(INTERFACES):
        raise ValueError("Expected exactly the seven published internal interface labels")
    counts = frame.groupby("timestamp").interface.nunique()
    if not counts.eq(7).all():
        raise ValueError("Every hour must contain all seven interfaces")
    if not booleans(frame.pf_success, "pf_success").all():
        raise ValueError("Some DC solutions failed; cannot silently exclude them from the primary replication")
    columns = ["released_plot_mw", "corrected_operator_mw", "observed_mw", "positive_limit_mw", "released_paper_error_pct"]
    if not np.isfinite(frame[columns].to_numpy(dtype=float)).all() or not frame.positive_limit_mw.gt(0).all():
        raise ValueError("Nonfinite flow, error, or nonpositive positive-limit denominator")
    expected_paper = 100 * (frame.observed_mw - frame.released_plot_mw) / frame.positive_limit_mw
    if np.max(np.abs(expected_paper - frame.released_paper_error_pct)) > 1e-8:
        raise ValueError("Saved literal paper metric disagrees with its published formula")
    times = pd.DatetimeIndex(sorted(frame.timestamp.unique()))
    if not pilot:
        expected = pd.date_range("2019-01-01", "2019-12-31 23:00:00", freq="h")
        if not times.equals(expected) or len(frame) != 8760 * 7:
            raise ValueError("Annual primary must have exactly all 8760 naive local hour labels and 61320 rows")
    elif len(times) >= 8760:
        raise ValueError("Pilot mode is not a substitute for validating the complete annual grid")
    frame["InterfaceName"] = frame.interface.map(INTERFACES)
    return frame.sort_values(["timestamp", "interface"]).reset_index(drop=True)


def join_quality(frame: pd.DataFrame, quality_path: Path) -> pd.DataFrame:
    columns = ["TimeStamp", "InterfaceName", "FlowMWH", "PositiveLimitMWH", "sample_count", "distinct_timestamp_count",
               "FlowMWH_imputed", "PositiveLimitMWH_imputed", "spring_dst_missing_hour", "fall_dst_ambiguous_hour",
               "filter_unimputed_unambiguous_hour"]
    quality = pd.read_csv(quality_path, usecols=columns)
    quality = quality.loc[quality.InterfaceName.isin(INTERFACES.values())].copy()
    quality["timestamp"] = pd.to_datetime(quality.pop("TimeStamp"), format="%Y-%m-%d %H:%M:%S")
    if quality.duplicated(["timestamp", "InterfaceName"]).any():
        raise ValueError("Source quality keys are not unique")
    merged = frame.merge(quality, on=["timestamp", "InterfaceName"], how="left", validate="one_to_one", indicator=True)
    if not merged._merge.eq("both").all():
        raise ValueError("An evaluated observation lacks a source-quality record")
    merged = merged.drop(columns="_merge")
    for field in columns[6:]:
        merged[field] = booleans(merged[field], field)
    if np.max(np.abs(merged.observed_mw - merged.FlowMWH)) > 1e-7:
        raise ValueError("Quality table's reconstructed flow does not match model input observations")
    if np.max(np.abs(merged.positive_limit_mw - merged.PositiveLimitMWH)) > 1e-7:
        raise ValueError("Quality table's reconstructed limit does not match model scoring denominator")
    expected = ~merged.FlowMWH_imputed & ~merged.fall_dst_ambiguous_hour
    if not merged.filter_unimputed_unambiguous_hour.equals(expected):
        raise ValueError("The requested source sensitivity filter has changed meaning")
    return merged


def aggregate(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    interfaces, overall, monthly, quality_rows = [], [], [], []
    for name in INTERFACES:
        group = frame.loc[frame.interface == name]
        quality_rows.append({
            "interface": name, "observations": len(group), "imputed_flow_hours": int(group.FlowMWH_imputed.sum()),
            "imputed_positive_limit_hours": int(group.PositiveLimitMWH_imputed.sum()),
            "spring_dst_missing_hours": int(group.spring_dst_missing_hour.sum()),
            "fall_dst_ambiguous_hours": int(group.fall_dst_ambiguous_hour.sum()),
            "sensitivity_included_hours": int(group.filter_unimputed_unambiguous_hour.sum()),
            "duplicate_timestamp_sample_hours": int((group.sample_count > group.distinct_timestamp_count).sum()),
            "hours_with_fewer_than_12_samples": int((group.sample_count < 12).sum()),
        })
    scopes = {"primary_all_naive_hours": frame,
              "unimputed_unambiguous_hour_sensitivity": frame.loc[frame.filter_unimputed_unambiguous_hour]}
    for scope, selected in scopes.items():
        if selected.empty:
            continue
        for variant, column in VARIANTS.items():
            overall.append({"scope": scope, "operator_variant": variant, "unique_hour_labels": selected.timestamp.nunique(),
                            **metrics(selected[column], selected.observed_mw, selected.positive_limit_mw)})
            for name in INTERFACES:
                group = selected.loc[selected.interface == name]
                if group.empty:
                    continue
                interfaces.append({"scope": scope, "operator_variant": variant, "interface": name,
                                   **metrics(group[column], group.observed_mw, group.positive_limit_mw)})
                for month, part in group.groupby(group.timestamp.dt.month):
                    monthly.append({"scope": scope, "operator_variant": variant, "interface": name, "month": int(month),
                                    **metrics(part[column], part.observed_mw, part.positive_limit_mw)})
    return tuple(pd.DataFrame(rows) for rows in (interfaces, overall, monthly, quality_rows))


def plot_comparison(metrics_frame: pd.DataFrame, output_stem: Path, hours: int, pilot: bool) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    primary = metrics_frame.loc[metrics_frame.scope == "primary_all_naive_hours"]
    corrected = primary.loc[primary.operator_variant == "corrected_released_if_map"].set_index("interface").loc[list(INTERFACES)]
    literal = primary.loc[primary.operator_variant == "literal_released_plot"].set_index("interface").loc[list(INTERFACES)]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42, "ps.fonttype": 42,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, (left, right) = plt.subplots(1, 2, figsize=(13.0, 7.0), gridspec_kw={"width_ratios": [1.18, 1]}, layout=None)
    positions = np.arange(7)
    left.axvspan(-15, 15, color="#eef1f4", zorder=0)
    left.axvspan(-10, 10, color="#dceee8", zorder=0)
    left.axvline(0, color="#526370", linewidth=.8)
    box = [{"med": r.paper_error_median_pct, "q1": r.paper_error_q25_pct, "q3": r.paper_error_q75_pct,
            "whislo": r.paper_error_q025_pct, "whishi": r.paper_error_q975_pct, "fliers": []}
           for r in corrected.itertuples()]
    left.bxp(box, positions=positions, vert=False, showfliers=False, patch_artist=True, widths=.5,
             boxprops={"facecolor": "#257e78", "edgecolor": "#155b57"}, medianprops={"color": "white", "linewidth": 1.8},
             whiskerprops={"color": "#155b57"}, capprops={"color": "#155b57"}, manage_ticks=False)
    left.set_yticks(positions, list(INTERFACES))
    left.set_ylim(6.7, -.7)
    extent = max(16., abs(corrected.paper_error_q025_pct.min()), abs(corrected.paper_error_q975_pct.max()))
    left.set_xlim(-1.13 * extent, 1.13 * extent)
    left.set_xlabel("100 × (observed − simulated) / positive limit (%)")
    left.set_title("A   Corrected operator: paper error distribution", loc="left", fontsize=11, fontweight="bold", pad=15)
    left.grid(axis="x", alpha=.2, zorder=0)
    right.barh(positions - .18, literal.actual_flow_wape_pct, height=.32, color="#8c9cad", label="Released plotting indices")
    right.barh(positions + .18, corrected.actual_flow_wape_pct, height=.32, color="#257e78", label="Corrected if.map")
    maximum = max(literal.actual_flow_wape_pct.max(), corrected.actual_flow_wape_pct.max())
    for values, offset in ((literal.actual_flow_wape_pct, -.18), (corrected.actual_flow_wape_pct, .18)):
        for y, value in enumerate(values):
            right.text(value + maximum * .018, y + offset, f"{value:.1f}%", va="center", fontsize=9)
    right.set_yticks(positions, list(INTERFACES))
    right.set_ylim(6.7, -.7)
    right.set_xlim(0, maximum * 1.28)
    right.set_xlabel("100 × Σ|simulated − observed| / Σ|observed| (%)")
    right.set_title("B   Actual-flow relative aggregate error", loc="left", fontsize=11, fontweight="bold", pad=15)
    right.grid(axis="x", alpha=.2)
    handles, legend_labels = right.get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="center left", bbox_to_anchor=(.57, .205),
               ncol=2, frameon=False, fontsize=9)
    title = "PILOT QA — not annual results" if pilot else "NYgrid 2019 interface-flow reproduction"
    fig.suptitle(title, x=.07, y=.975, ha="left", fontsize=17, fontweight="bold")
    fig.text(.07, .925, f"{hours:,} naive local hourly labels · both operator definitions use exactly the same DC solutions", fontsize=11, color="#465361")
    footer = ("A: white line = median; boxes = 25th–75th percentiles; whiskers = 2.5th–97.5th percentiles. Tails beyond whiskers are not displayed.\n"
              "Shading marks ±10% and ±15% of the positive interface limit. These are not percentages of observed flow.\n"
              "Primary replication retains imputed and DST-ambiguous source hours. Operator correction uses model identities, not target fitting.\n"
              "DC convergence does not establish bounded AC feasibility. Actual-flow metrics use no denominator floor.")
    fig.text(.07, .145, footer, fontsize=9, va="top", linespacing=1.6, color="#465361")
    fig.subplots_adjust(left=.125, right=.98, top=.84, bottom=.30, wspace=.53)
    fig.savefig(output_stem.with_suffix(".png"), dpi=220, facecolor="white")
    fig.savefig(output_stem.with_suffix(".pdf"), facecolor="white", metadata={"Title": title, "Subject": "Same-PF operator comparison with distinct error denominators"})
    plt.close(fig)


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, np.generic):
        return clean_json(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")


def run(args: argparse.Namespace) -> dict[str, Any]:
    prefix = "pilot_reproduction" if args.pilot else "annual_reproduction"
    paths = [args.input_dir / "pilot_interfaces.csv"] if args.pilot else [args.input_dir / f"annual_{i}_interfaces.csv" for i in range(1, 5)]
    inputs = paths + [args.quality, Path(__file__).resolve(), Path(__file__).with_name("test_summarize_reproduction.py")]
    for relative in ["scripts/nygrid_2019/run_annual_reproduction.m", "scripts/nygrid_2019/audit_interface_operators.m",
                     "output/nygrid_2019/operator_audit_manifest.csv", "output/nygrid_2019/operator_audit_formulas.csv",
                     "output/nygrid_2019/upstream_manifest.json", "output/nygrid_2019/cached_upstream_manifest.json",
                     "output/nygrid_2019/nyiso_source_audit.json"]:
        path = ROOT / relative
        if path.is_file():
            inputs.append(path)
    before = {path: sha(path) for path in inputs}
    frame = join_quality(load_campaign(paths, pilot=args.pilot), args.quality)
    interface, overall, monthly, quality = aggregate(frame)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for suffix, table in (("interface_metrics", interface), ("overall_metrics", overall), ("monthly_metrics", monthly), ("source_quality", quality)):
        path = args.output_dir / f"{prefix}_{suffix}.csv"
        write_csv(table, path)
        artifacts.append(path)
    plot_stem = args.output_dir / f"{prefix}_comparison"
    plot_comparison(interface, plot_stem, frame.timestamp.nunique(), args.pilot)
    artifacts += [plot_stem.with_suffix(".png"), plot_stem.with_suffix(".pdf")]
    if args.write_hourly:
        hourly_path = args.output_dir / f"{prefix}_hourly_comparison.csv"
        write_csv(frame, hourly_path)
        artifacts.append(hourly_path)
    summary = {
        "scope": "PILOT_QA_not_annual_results" if args.pilot else "full_2019_8760_naive_hour_primary_paper_replication",
        "annual_complete": not args.pilot,
        "unique_hour_labels": int(frame.timestamp.nunique()), "interface_observations": len(frame),
        "all_dc_pf_successful": True, "operator_definitions_evaluated_on_same_PF": True,
        "observations_used_to_select_operator_correction": False, "denominator_floor_mw": None,
        "start_naive_local_hour": str(frame.timestamp.min()), "end_naive_local_hour": str(frame.timestamp.max()),
        "metric_policy": METRIC_POLICY, "overall_metrics": overall.to_dict("records"),
        "per_interface_metrics": interface.to_dict("records"), "source_quality": quality.to_dict("records"),
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
    }
    summary_path = args.output_dir / f"{prefix}_summary.json"
    summary_path.write_text(json.dumps(clean_json(summary), indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    artifacts.append(summary_path)
    if any(sha(path) != before[path] for path in inputs):
        raise RuntimeError("Input or summary code changed during calculation; generated results must not be frozen")
    manifest_rows = []
    for path in inputs:
        try:
            relative = path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            relative = path.name
        manifest_rows.append({"relative_path": relative, "sha256": before[path], "hash_policy": "exact_bytes"})
    input_manifest = args.output_dir / f"{prefix}_input_manifest.csv"
    write_csv(pd.DataFrame(manifest_rows), input_manifest)
    artifacts.append(input_manifest)
    write_csv(pd.DataFrame([{"artifact": path.name, "sha256": sha(path)} for path in artifacts]),
              args.output_dir / f"{prefix}_output_manifest.csv")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true", help="Use pilot_interfaces.csv and visibly separate pilot outputs")
    parser.add_argument("--input-dir", type=Path, default=OUT)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    parser.add_argument("--quality", type=Path, default=OUT / "nyiso_source_audit_hourly_quality.csv")
    parser.add_argument("--write-hourly", action="store_true", help="Also emit joined hourly rows; workers remain the canonical source")
    args = parser.parse_args()
    summary = run(args)
    print(json.dumps({"scope": summary["scope"], "hours": summary["unique_hour_labels"],
                      "overall": summary["overall_metrics"]}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
