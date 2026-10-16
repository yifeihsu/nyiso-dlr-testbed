"""Scientific figure for the verified-direction P34-conditioned reconstruction.

Reads stable scored results and source-control receipts. Preserves all source
evidence, limits, replay arrays and existing historical figures. Exports a
reproducible PNG/PDF/SVG with exact plotted rows and SHA-256 provenance.
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

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "output/nygrid_2025_par_controls"
OUT = BASE / "figures"
METRICS = BASE / "comparison/interface_summary.csv"
SCREEN = BASE / "controls/necessary_p_only_screen.json"
INPUT_RECEIPT = BASE / "controls/input_receipt.json"
DIRECTION = BASE / "sources/direction/direction_verification_receipt.json"
LIMITS = BASE / "sources/limits/limits.json"
VARIANTS = ["dated_confirmed_hydro_repair", "dated_verified_PAR_flows"]
INTERFACES = ["DYSINGER EAST", "WEST CENTRAL", "TOTAL EAST", "MOSES SOUTH",
              "CENTRAL EAST - VC", "UPNY CONED", "SPR/DUN-SOUTH"]
NAMES = ["Dysinger East", "West Central", "Total East", "Moses South",
         "Central East", "UpNY-ConEd", "Sprain / Dunwoodie South"]
GRAY, BLUE, GOLD = "#818B95", "#2166A5", "#B58128"
INK, GRID = "#243446", "#DDE3E8"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_data():
    raw = pd.read_csv(METRICS)
    rows = raw.loc[raw.month.eq(0) & raw.variant.isin(VARIANTS)].copy()
    require(len(rows) == 14 and not rows.duplicated(["variant", "interface"]).any(), "Expected two variants and seven annual interfaces")
    require(set(rows.interface) == set(INTERFACES) and rows.hours.eq(8663).all(), "The plotted cohort changed")
    require(rows.internal_observations_used_to_fit.astype(str).str.lower().eq("false").all(), "Internal-observation fit policy changed")
    require(rows.loc[rows.variant.eq(VARIANTS[1]), "PAR_flows_used_as_external_inputs"].astype(str).str.lower().eq("true").all(),
            "P34 external-input qualification missing")
    for _, group in rows.groupby("interface"):
        denominators = 100 * group.mae_public_equivalent_mw / group.wape_percent
        require(np.ptp(denominators) < 1e-7, "The observed WAPE denominator differs between variants")
    screen = json.loads(SCREEN.read_text())
    require(screen["native_resolution_screen_precedes_hourly_aggregation"] and not screen["clipping_performed"], "Source-screen policy changed")
    limits = {int(row["ptid"]): row for row in json.loads(LIMITS.read_text())["devices"]}
    device_rows = []
    for row in screen["devices"]:
        ptid = int(row["ptid"]); native = row["native_resolution"]; limit = limits[ptid]
        require(native["scope"] == "necessary_abs_P_le_nominal_S_only" and not native["full_P_Q_rating_feasible"], "Physical feasibility must not be claimed")
        require(limit["continuous_mva"] is None and limit["nominal_mva"] == 300, "Nominal and continuous ratings must remain distinct")
        require(native["necessary_abs_p_screen_mw"] == 300 and native["violations"] == 0, "Nominal P-only screen result changed")
        device_rows.append(dict(ptid=ptid, device="PS33" if ptid == 25118 else "PS34",
                                native_records=native["records"],
                                maximum_absolute_public_mw=native["maximum_absolute_public_mw"],
                                nominal_apparent_capacity_mva=limit["nominal_mva"],
                                necessary_abs_p_screen_mw=native["necessary_abs_p_screen_mw"],
                                violations=native["violations"], full_physical_feasibility_verified=False))
    devices = pd.DataFrame(device_rows).sort_values("ptid")
    require(devices.ptid.tolist() == [25118,25119], "Unexpected device identity")
    inputs = json.loads(INPUT_RECEIPT.read_text())
    require(inputs["common_replay_hours"] == 8663 and inputs["native_P34_source_days"] == 366, "Input population changed")
    require(inputs["native_P34_endpoint_scope"].startswith("Includes the frozen Jan1,2026 endpoint day"), "Native sample endpoint scope changed")
    direction = json.loads(DIRECTION.read_text())
    require(direction["status"] == "verified_official_direction_for_2025", "Direction is not verified")
    require(all(d["raw_to_ontario_to_new_york_multiplier"] == 1 for d in direction["ptid_directions"]), "Source direction changed")
    return rows, devices, direction


def style(ax):
    ax.set_axisbelow(True)
    ax.grid(axis="x", color=GRID, linewidth=.7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#8897A6")
    ax.spines[["left", "bottom"]].set_linewidth(.75)
    ax.tick_params(axis="both", labelsize=10.5, labelcolor=INK, color="#8897A6")
    ax.tick_params(axis="y", length=0, pad=7)


def figure(rows, devices, direction):
    table = rows.set_index(["variant", "interface"])
    before = table.loc[VARIANTS[0]].loc[INTERFACES]
    after = table.loc[VARIANTS[1]].loc[INTERFACES]
    fig = plt.figure(figsize=(17.4, 8.7))
    left = fig.add_axes([.15,.245,.415,.555])
    right = fig.add_axes([.715,.42,.245,.32])
    fig.text(.035,.945,"Verified St. Lawrence PAR flow inputs: seven-interface reconstruction",
             color=INK,fontsize=18.5,weight="bold")
    fig.text(.035,.900,"2025 dated topology · panel a: the same 8,663 qualified hours · panel b: native-resolution source samples",
             color="#536478",fontsize=11.3)
    left.set_title("a  Internal interface error",loc="left",fontsize=13,color=INK,pad=34)
    y = np.arange(7)
    left.barh(y-.18,before.wape_percent,height=.29,color=GRAY,edgecolor=GRAY,linewidth=.7)
    left.barh(y+.18,after.wape_percent,height=.29,color=BLUE,edgecolor=BLUE,linewidth=.7)
    for index, (old, new) in enumerate(zip(before.wape_percent,after.wape_percent)):
        left.text(old+1.0,index-.18,f"{old:.2f}",va="center",fontsize=10.1,color="#586675")
        left.text(new+1.0,index+.18,f"{new:.2f}",va="center",fontsize=10.1,color=BLUE)
    left.set_yticks(y,NAMES);left.invert_yaxis();left.set_xlim(0,91)
    left.set_xticks([0,20,40,60,80])
    left.set_xlabel("WAPE (%) — lower is better",fontsize=11.5,color=INK,labelpad=10)
    left.legend(handles=[Patch(color=GRAY,label="Confirmed hydro repair alone"),
                         Patch(color=BLUE,label="P34 external-flow-conditioned")],
                loc="lower left",bbox_to_anchor=(-.01,1.008),ncol=2,frameon=False,fontsize=10,
                handlelength=1.2,columnspacing=1.5)
    style(left)

    right.set_title("b  Necessary nominal-capacity screen",loc="left",fontsize=13,color=INK,pad=19)
    values = devices.maximum_absolute_public_mw.to_numpy()
    right.barh([0,1],values,height=.43,facecolor=GOLD,edgecolor=GOLD,linewidth=.8)
    for i, value in enumerate(values):
        right.text(value+5,i,f"{value:.1f}",va="center",fontsize=11,color="#8E681E")
    right.set_yticks([0,1],["PS33\nPTID 25118","PS34\nPTID 25119"])
    right.set_ylim(1.8,-.8);right.set_xlim(0,350);right.set_xticks([0,100,200,300])
    right.axvline(300,color="#37495B",linestyle=(0,(4,3)),linewidth=1.4)
    right.text(300,-.66,"300",ha="center",va="center",fontsize=10.4,color="#37495B")
    right.set_xlabel("Maximum native |P| (public MW)",fontsize=11.3,color=INK,labelpad=10)
    style(right)
    count = int(devices.native_records.iloc[0])
    require(devices.native_records.eq(count).all(), "Different per-device sample populations need separate labels")
    sample_note = fig.text(.675,.304,f"{count:,} raw P34 samples per device; includes Jan 1, 2026\nendpoint day. Screen applied before hourly averaging.",
             fontsize=10.2,color="#536478",linespacing=1.5)
    capacity_note = fig.text(.675,.244,"300 MVA is nominal apparent capacity. |P| ≤ 300 MW\nis only a necessary outer screen, not an operating P-limit.",
             fontsize=10.2,color=INK,linespacing=1.5)

    fig.text(.035,.154,"P34 observed external flows are inputs; no internal interface flows were used to fit the model or choose direction.",
             fontsize=11.2,color=INK,weight="bold")
    fig.text(.035,.111,"Hardware tap trajectories, phase-dependent thermal limits, P-Q/current capability and contingency feasibility remain unverified.",
             fontsize=10.7,color="#526275")
    fig.text(.035,.076,"WAPE = 100 × Σ|modeled − observed| / Σ|observed|. Total East and Central East WAPE increase after conditioning.",
             fontsize=10.2,color="#526275")
    fig.text(.035,.043,"Direction evidence: NYISO Par Flow Direction Diagrams, page 7; legend page 26 (effective December 3, 2024).",
             fontsize=9.8,color=BLUE,url=direction["source_url"]+"#page=7")
    fig.text(.035,.015,"Sources: comparison/interface_summary.csv; controls/necessary_p_only_screen.json. Exact plotted rows and source SHA-256 hashes accompany this figure.",
             fontsize=9.2,color="#667688")
    fig.canvas.draw(); renderer=fig.canvas.get_renderer();canvas=fig.bbox
    require(not right.xaxis.label.get_window_extent(renderer).overlaps(sample_note.get_window_extent(renderer)),
            "Native-sample note overlaps the power-axis label")
    require(not sample_note.get_window_extent(renderer).overlaps(capacity_note.get_window_extent(renderer)),
            "Native-sample and capacity notes overlap")
    for text in fig.findobj(Text):
        if text.get_visible() and text.get_text():
            box=text.get_window_extent(renderer)
            require(box.x0>=canvas.x0-1 and box.y0>=canvas.y0-1 and box.x1<=canvas.x1+1 and box.y1<=canvas.y1+1,
                    "Figure text clipped: "+text.get_text())
    outputs=[]
    for ext in ["png","pdf","svg"]:
        path=OUT/('verified_PAR_reconstruction.'+ext)
        fig.savefig(path,dpi=180,facecolor="white",metadata={"Creator":"NPCC source-backed scientific plotting"} if ext=="pdf" else None)
        outputs.append(path)
    plt.close(fig)
    return outputs


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    sources=[METRICS,SCREEN,INPUT_RECEIPT,DIRECTION,LIMITS,Path(__file__)]
    hashes={p.relative_to(ROOT).as_posix():sha(p) for p in sources}
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":11,"svg.fonttype":"none","pdf.fonttype":42})
    rows,devices,direction=read_data()
    outputs=figure(rows,devices,direction)
    rows.to_csv(OUT/'plotted_interface_rows.csv',index=False,lineterminator='\n')
    devices.to_csv(OUT/'plotted_device_screen_rows.csv',index=False,lineterminator='\n')
    require(all(sha(ROOT/p)==value for p,value in hashes.items()),"An input changed while rendering")
    provenance=pd.DataFrame([dict(path=p,sha256=value) for p,value in hashes.items()])
    provenance.to_csv(OUT/'figure_provenance.csv',index=False,lineterminator='\n')
    validation=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),all_seven_interfaces_included=True,
        hours_per_interface_variant=8663,external_P34_observations_used_as_inputs=True,internal_interface_fitting=False,
        native_samples_per_device=int(devices.native_records.iloc[0]),native_sample_endpoint_day_included=True,
        nominal_capacity_screen_not_continuous_P_limit=True,hardware_taps_and_full_PQ_feasibility_claimed=False,
        direction_proof_link=direction['source_url']+'#page=7',direction_legend_page=26,
        all_rendered_text_inside_canvas=True,visual_QA='pending rendered PNG inspection',
        inputs=provenance.to_dict('records'),outputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in outputs])
    (OUT/'figure_validation.json').write_text(json.dumps(validation,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:validation[k] for k in ['passed','all_seven_interfaces_included','hours_per_interface_variant','native_samples_per_device']},indent=2))


if __name__=='__main__':
    build()
