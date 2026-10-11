"""Source-backed scientific figures for the Moses South diagnosis.

The confirmed hydro-zone repair and two unpromoted PAR orientations are kept
visually and semantically distinct. No orientation is ranked or selected.
Only new figure artifacts are written; frozen model and metric inputs are read.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.text import Text
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "output/nygrid_2025_moses_audit"
OUT = BASE / "figures"
METRICS = BASE / "comparison/interface_summary.csv"
HISTORICAL_METRICS = ROOT / "output/nygrid_2019_full_stage1/full_year_interface_metrics.csv"
HISTORICAL_MAT = ROOT / "output/nygrid_2019_full_stage1/full_year.mat"
VARIANTS = ["dated_baseline_replayed", "dated_hydro_zone_corrected",
            "dated_hydro_zone_par_from_moses", "dated_hydro_zone_par_toward_moses"]
INTERFACES = ["DYSINGER EAST", "WEST CENTRAL", "TOTAL EAST", "MOSES SOUTH",
              "CENTRAL EAST - VC", "UPNY CONED", "SPR/DUN-SOUTH"]
NAMES = ["Dysinger East", "West Central", "Total East", "Moses South",
         "Central East", "UpNY–ConEd", "Sprain / Dunwoodie South"]
GRAY, BLUE, GOLD = "#7F8993", "#2166A5", "#9E711E"
INK, GRID = "#243446", "#DDE3E8"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def style(ax):
    ax.set_axisbelow(True)
    ax.grid(axis="x", color=GRID, linewidth=.7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#8493A2")
    ax.spines[["left", "bottom"]].set_linewidth(.75)
    ax.tick_params(axis="both", labelsize=10.5, color="#8493A2", labelcolor=INK)
    ax.tick_params(axis="y", length=0, pad=7)


def save(fig, name):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    canvas = fig.bbox
    for text in fig.findobj(Text):
        if not text.get_visible() or not text.get_text():
            continue
        box = text.get_window_extent(renderer)
        require(box.x0 >= canvas.x0 - 1 and box.y0 >= canvas.y0 - 1
                and box.x1 <= canvas.x1 + 1 and box.y1 <= canvas.y1 + 1,
                f"Text clipped by figure boundary in {name}: {text.get_text()}")
    outputs = []
    for ext in ["png", "pdf", "svg"]:
        path = OUT / f"{name}.{ext}"
        fig.savefig(path, dpi=180, facecolor="white",
                    metadata={"Creator": "NPCC source-backed scientific plotting"} if ext == "pdf" else None)
        outputs.append(path)
    plt.close(fig)
    return outputs


def read_metrics():
    raw = pd.read_csv(METRICS)
    reviewed = raw.loc[raw.month.eq(0) & raw.cohort.eq("common_PAR_qualified") & raw.variant.isin(VARIANTS)].copy()
    require(len(reviewed) == 28 and not reviewed.duplicated(["variant", "interface"]).any(), "Expected4 variants ×7 annual interfaces")
    require(reviewed.hours.eq(8663).all(), "Displayed variants do not share8663 hours")
    require(reviewed.observations_used_to_fit_model.astype(str).str.lower().eq("false").all(), "Observation-use claim changed")
    require(np.max(abs(reviewed.wape_percent - 100 * reviewed.mae_public_equivalent_mw / reviewed.mean_absolute_observed_public_mw)) < 1e-10,
            "WAPE/MAE denominator consistency failed")
    for _, group in reviewed.groupby("interface"):
        require(np.ptp(group.mean_absolute_observed_public_mw) < 1e-9, "Cross-variant observed cohort changed")
    historical = pd.read_csv(HISTORICAL_METRICS)
    row = historical.loc[historical.interface.eq("Moses South")].iloc[0]
    case = loadmat(HISTORICAL_MAT, simplify_cells=True,
                   variable_names=["interface_mw", "observed_interface_mw", "interface_names"])
    col = list(case["interface_names"]).index("Moses South")
    actual = np.asarray(case["observed_interface_mw"], float)[:, col]
    modeled = np.asarray(case["interface_mw"], float)[:, col]
    require(len(actual) == int(row.hours) == 8760 and np.isfinite(actual).all() and np.isfinite(modeled).all(), "Historical cohort changed")
    mae = float(np.mean(abs(modeled-actual)))
    mean_abs = float(np.mean(abs(actual)))
    wape = 100 * mae / mean_abs
    require(abs(wape - row.full_final_vs_nyiso_wape_pct) < 1e-8, "Historical2019 metric does not match saved arrays")
    historical_row = dict(year=2019, variant="frozen_full_NPCC_historical_reference", interface="MOSES SOUTH",
                          hours=8760, mae_public_equivalent_mw=mae, mean_absolute_observed_public_mw=mean_abs,
                          wape_percent=wape, role="historical_context_not_a_controlled_repair_comparison")
    return reviewed, historical_row


def repair_figure(rows):
    table = rows.set_index(["variant", "interface"])
    baseline = table.loc[VARIANTS[0]].loc[INTERFACES]
    repaired = table.loc[VARIANTS[1]].loc[INTERFACES]
    fig = plt.figure(figsize=(17.8, 8.8))
    left = fig.add_axes([.145, .22, .355, .56])
    right = fig.add_axes([.70, .22, .265, .56])
    fig.text(.035, .945, "Moses South investigation: confirmed repair and diagnostic scenarios",
             fontsize=19, color=INK, weight="bold")
    fig.text(.035, .901, "2025 dated topology · the same 8,663 qualified hours · lower error is better",
             fontsize=11.5, color="#536478")
    left.set_title("a  Seven-interface WAPE", loc="left", fontsize=13, color=INK, pad=35)
    right.set_title("b  Moses South MAE", loc="left", fontsize=13, color=INK, pad=35)
    y = np.arange(7)
    left.barh(y-.18, baseline.wape_percent, height=.29, color=GRAY, edgecolor=GRAY, linewidth=.7)
    left.barh(y+.18, repaired.wape_percent, height=.29, color=BLUE, edgecolor=BLUE, linewidth=.7)
    for j, (before, after) in enumerate(zip(baseline.wape_percent, repaired.wape_percent)):
        left.text(before+1.2, j-.18, f"{before:.2f}", va="center", fontsize=10.1, color="#586674")
        left.text(after+1.2, j+.18, f"{after:.2f}", va="center", fontsize=10.1, color=BLUE)
    left.set_yticks(y, NAMES)
    left.invert_yaxis()
    left.set_xlim(0, 111)
    left.set_xticks([0,20,40,60,80,100])
    left.set_xlabel("WAPE (%)", fontsize=11.5, color=INK, labelpad=10)
    left.legend(handles=[Patch(color=GRAY, label="Baseline"), Patch(color=BLUE, label="Confirmed hydro-zone repair")],
                loc="lower left", bbox_to_anchor=(-.01, 1.015), ncol=2, frameon=False, fontsize=10,
                handlelength=1.3, columnspacing=1.5)
    style(left)

    ys = [0, 1, 2.65, 3.65]
    category_labels = ["Baseline", "Hydro-zone repair\nCONFIRMED", "Hydro repair + P34\nraw positive: Moses → Ontario",
                       "Hydro repair + P34\nraw positive: Ontario → Moses"]
    for j, (variant, ypos) in enumerate(zip(VARIANTS, ys)):
        row = table.loc[(variant,"MOSES SOUTH")]
        is_diagnostic = j >= 2
        right.barh(ypos, row.mae_public_equivalent_mw, height=.56,
                   facecolor="white" if is_diagnostic else [GRAY,BLUE][j],
                   edgecolor=GOLD if is_diagnostic else [GRAY,BLUE][j],
                   hatch=["///", "\\\\\\"][j-2] if is_diagnostic else None,
                   linewidth=1.2 if is_diagnostic else .8)
        right.text(row.mae_public_equivalent_mw+12, ypos,
                   f"{row.mae_public_equivalent_mw:.2f} MW\nWAPE {row.wape_percent:.2f}%",
                   va="center", fontsize=10.2, color=GOLD if is_diagnostic else [GRAY,BLUE][j])
    right.set_yticks(ys, category_labels)
    right.set_ylim(4.35, -.7)
    right.set_xlim(0, 705)
    right.set_xticks([0,150,300,450,600])
    right.axhline(1.85, color="#B5BDC5", linewidth=.9, linestyle=(0,(4,3)))
    right.text(-.58, .524, "UNPROMOTED P34 ORIENTATIONS", transform=right.transAxes,
                fontsize=10.3, color=GOLD, weight="bold")
    right.set_xlabel("MAE (public-scale MW)", fontsize=11.5, color=INK, labelpad=10)
    style(right)
    for label, index in zip(right.get_yticklabels(), range(4)):
        if index >= 2:
            label.set_color(GOLD)
    fig.text(.035, .129, "WAPE = 100 × Σ|modeled − observed| / Σ|observed|.  MAE = mean |modeled − observed|.  Model MW are divided by the fixed γ for public-scale comparison.",
             fontsize=10, color="#526275")
    fig.text(.035, .084, "The hydro-zone assignment repair is source-confirmed. P34 direction remains unresolved; neither diagnostic orientation is selected or promoted.",
             fontsize=10.5, color=INK)
    fig.text(.035, .051, "Derived DC phase controls are not qualified physical PAR tap settings. The two hatched bars are alternative scenarios, not uncertainty bounds.",
             fontsize=10.1, color="#526275")
    fig.text(.035, .023, "Source: comparison/interface_summary.csv · annual rows, common_PAR_qualified cohort · full-precision inputs and SHA-256 provenance accompany this figure.",
             fontsize=9.3, color="#657386")
    return save(fig, "moses_repair_and_diagnostics")


def historical_figure(rows, historical):
    current = rows.loc[rows.variant.eq(VARIANTS[0]) & rows.interface.eq("MOSES SOUTH")].iloc[0]
    records = [historical, current.to_dict()]
    fig = plt.figure(figsize=(12.8, 6.8))
    axes = [fig.add_axes([.205,.31,.27,.45]), fig.add_axes([.69,.31,.27,.45])]
    fig.text(.035,.936,"Moses South: historical context",fontsize=18,color=INK,weight="bold")
    fig.text(.035,.884,"WAPE depends on both absolute error and the magnitude of observed flow.",fontsize=11.5,color="#536478")
    labels=["2019 historical reference\n8,760 hours", "2025 dated baseline\n8,663 hours"]
    for ax, column, title, limit in [
        (axes[0],"mae_public_equivalent_mw","a  Mean absolute error",620),
        (axes[1],"mean_absolute_observed_public_mw","b  Mean |observed flow|",2050)]:
        values = [float(r[column]) for r in records]
        ax.barh([0,1],values,height=.43,color=[GRAY,BLUE],edgecolor=[GRAY,BLUE],linewidth=.8)
        for y,value in enumerate(values):
            ax.text(value+limit*.025,y,f"{value:,.2f}",va="center",fontsize=11,color=[GRAY,BLUE][y])
        ax.set_yticks([0,1],labels)
        ax.set_ylim(1.55,-.55);ax.set_xlim(0,limit)
        ax.set_xticks([0,150,300,450,600] if limit==620 else [0,500,1000,1500,2000])
        ax.set_title(title,loc="left",fontsize=13,color=INK,pad=17)
        ax.set_xlabel("Public-scale MW",fontsize=11.3,color=INK,labelpad=9)
        style(ax)
    fig.text(.035,.211,f"Historical 2019 WAPE: {historical['wape_percent']:.2f}%     |     2025 dated-baseline WAPE: {current.wape_percent:.2f}%",fontsize=12,color=INK,weight="bold")
    fig.text(.035,.145,"Historical context only: these are different years, operating conditions, source-processing conventions and hour cohorts.",fontsize=10.2,color="#536478")
    fig.text(.035,.108,"This is not a controlled before/after repair comparison. The confirmed 2025 repair comparison uses the same 8,663 hours in the companion figure.",fontsize=10.2,color="#536478")
    fig.text(.035,.054,"Sources: frozen 2019 full_year.mat and full_year_interface_metrics.csv; 2025 comparison/interface_summary.csv. Lower error is better.",fontsize=9.4,color="#657386")
    return save(fig,"moses_historical_context")


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    sources=[METRICS,HISTORICAL_METRICS,HISTORICAL_MAT,Path(__file__)]
    hashes={str(p.relative_to(ROOT)).replace("\\","/"):sha(p) for p in sources}
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":11,"svg.fonttype":"none","pdf.fonttype":42,
                         "axes.unicode_minus":True,"hatch.linewidth":.7})
    rows,historical=read_metrics()
    outputs=repair_figure(rows)+historical_figure(rows,historical)
    rows.to_csv(OUT/"figure_source_rows_2025.csv",index=False,lineterminator="\n")
    pd.DataFrame([historical]).to_csv(OUT/"figure_source_rows_2019.csv",index=False,lineterminator="\n")
    require(all(sha(ROOT/path)==value for path,value in hashes.items()),"Source changed during figure generation")
    provenance=pd.DataFrame([dict(role="input",path=path,sha256=value) for path,value in hashes.items()])
    provenance.to_csv(OUT/"figure_provenance.csv",index=False,lineterminator="\n")
    summary=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        annual_2025_common_hours=8663,annual_2019_historical_hours=8760,
        common_denominators_verified=True,WAPE_equals_100_MAE_over_mean_absolute_observation=True,
        confirmed_variant=VARIANTS[1],unpromoted_symmetric_display_variants=VARIANTS[2:],
        diagnostic_orientation_selected=False,diagnostics_are_confidence_intervals=False,
        physical_PAR_tap_qualification_claimed=False,
        all_rendered_text_inside_canvas=True,
        inputs=provenance.to_dict("records"),
        outputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in outputs],
        visual_QA="pending rendered PNG inspection")
    (OUT/"figure_validation.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:summary[k] for k in ["passed","annual_2025_common_hours","diagnostic_orientation_selected"]},indent=2))


if __name__=="__main__":
    build()
