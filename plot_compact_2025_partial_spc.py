"""Draw the saved northern electrical topology, not a geographic map."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
import pandas as pd

ROOT = Path(__file__).resolve().parent
FOLDER = ROOT / "output/compact_ny_2025/partial_spc"


def main():
    branches = pd.read_csv(FOLDER / "partial_spc_branch_register.csv")
    expected = {"MH2", "MH3", "HA2", "HW2", "LINE11", "LINE13", "AT2", "AT3", "TR2", "PLATTS_REGIONAL_EQ"}
    if set(branches.branch_key.str.removeprefix("NY2025_SPC:")) != expected:
        raise ValueError("Update schematic for changed branch inventory")
    pos = {48: (0, 3), 9120: (2.8, 3), 9121: (5.6, 3), 1220: (8.4, 3), 9122: (11.2, 3),
           43: (14, 3), 9123: (5.6, .3), 9124: (2.8, .3), 49: (0, .3)}
    labels = {48: "Moses E\n230 kV", 9120: "Haverstock\n230 kV", 9121: "Haverstock\n345 kV",
              1220: "Adirondack\n345 kV", 9122: "Austin Road\n345 kV", 43: "Edic\n345 kV",
              9123: "Willis Annex\n345 kV", 9124: "Willis Annex\n230 kV", 49: "Plattsburgh\n115 kV"}
    fig, ax = plt.subplots(figsize=(15, 6.1))
    fig.patch.set_facecolor("#f8fafc")
    ax.set_facecolor("#f8fafc")
    for row in branches.itertuples():
        key = row.branch_key.removeprefix("NY2025_SPC:")
        a, b = pos[row.from_bus], pos[row.to_bus]
        thermal = key in {"MH2", "MH3", "HA2", "HW2", "LINE11", "LINE13"}
        curvature = {"MH2": .2, "MH3": -.2, "AT2": .2, "AT3": -.2}.get(key, 0)
        color = "#126e82" if thermal else "#657080"
        style = "--" if key == "PLATTS_REGIONAL_EQ" else "-"
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-", connectionstyle=f"arc3,rad={curvature}",
                                    linewidth=2.5, color=color, linestyle=style, shrinkA=45, shrinkB=45))
        x, y = ((a[0]+b[0])/2, (a[1]+b[1])/2)
        y += {"MH2": -.53, "MH3": .53, "AT2": -.53, "AT3": .53}.get(key, .22)
        label = key.replace("LINE", "Line ")
        if key == "PLATTS_REGIONAL_EQ":
            label = "Retained regional\n115/230-kV equivalent"
            y = -.4
        if key == "HW2":
            x += .5
        ax.text(x, y, label, ha="center", va="center", fontsize=10, color=color,
                bbox=dict(facecolor="#f8fafc", edgecolor="none", pad=2))
    for bus, (x, y) in pos.items():
        inherited = bus in {48, 43, 49}
        ax.text(x, y, labels[bus], ha="center", va="center", fontsize=10.5, weight="medium",
                bbox=dict(boxstyle="round,pad=.5", facecolor="#e8edf2" if inherited else "#d8f0ee",
                          edgecolor="#8292a0" if inherited else "#178279", linewidth=1.3))
    ax.text(8.2, .75, "71 New York buses in the complete case\n135 branch records · 117 active · 37 generators",
            fontsize=13, weight="semibold", color="#18333e", va="top")
    ax.text(8.2, -.2, "This view shows only the northern replacement.\nOther NPCC connections are omitted from the drawing.",
            fontsize=11, color="#526370", va="top")
    ax.set_xlim(-1.1, 15.1)
    ax.set_ylim(-1.35, 4.25)
    ax.axis("off")
    fig.suptitle("Selected infrastructure energized by year-end 2025", x=.055, y=.98, ha="left",
                 fontsize=19, weight="bold", color="#173744")
    fig.text(.055, .91, "Electrical schematic — approximate NPCC representation, not a geographic or as-built map",
             fontsize=11.5, color="#526370")
    fig.text(.055, .055, "Teal: six assumed overhead realizations. Gray: transformers and a regional equivalent.\n"
             "HA1 and Adirondack–Marcy Line 12 remain excluded; their energization occurred in 2026.",
             fontsize=10, color="#526370", linespacing=1.5)
    fig.subplots_adjust(left=.035, right=.985, top=.88, bottom=.13)
    for suffix in ("png", "pdf", "svg"):
        fig.savefig(FOLDER / f"northern_infrastructure_schematic.{suffix}", dpi=180, facecolor=fig.get_facecolor())
    svg = FOLDER / "northern_infrastructure_schematic.svg"
    svg.write_bytes(b"\n".join(line.rstrip() for line in svg.read_bytes().splitlines()) + b"\n")
    plt.close(fig)


if __name__ == "__main__":
    main()
