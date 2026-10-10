"""Render source-checked schematics of the 51-bus refinement using Graphviz.

Figures are topological, not geographic. Parallel circuits are bundled only
for drawing; a complete per-branch ledger preserves their individual rows.
The year-end core excludes the optional NYES circuit scenario.
"""
from __future__ import annotations
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess

import graphviz
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "output/nygrid_2025_downstate"
OUT = BASE / "diagrams"
STATE = "refined_2025"
COLORS = {"retained": "#B7BEC7", "source": "#226AA5", "assumed": "#B87518",
          "replaced": "#C04754", "scaffold": "#7E8791", "dc": "#73508E"}
LABELS = {"retained": "Retained original AC branch", "source": "Added historical source circuit",
          "assumed": "Added connection with assumed parameters", "replaced": "Replaced original branch (inactive)",
          "scaffold": "Algebraic idle connection (not physical)", "dc": "Unchanged scheduled DC equivalent"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def collect():
    buses = pd.read_csv(BASE / "network/bus_register.csv", keep_default_na=False)
    branches = pd.read_csv(BASE / "network/branch_register.csv", keep_default_na=False)
    case = loadmat(BASE / "network/network_cases.mat", simplify_cells=True)[STATE + "_case"]
    require(list(buses.model_bus) == list(case["bus"][:, 0]), "Bus register does not match case")
    require(len(buses) == 191 and buses.identity_role.ne("original_parent").sum() == 51, "Bus count changed")
    require((branches[STATE + "_status"].to_numpy() == case["branch"][:, 10]).all(), "Branch status mismatch")
    entries = []
    for row in branches.to_dict("records"):
        parent = row["electrical_role"] == "retained_parent"
        active = row[STATE + "_status"] == 1
        if not active and not parent:
            continue  # construction-only alternatives and optional NYES rows
        category = "retained" if parent and active else "replaced" if parent else (
            "source" if row["electrical_role"] == "exact_historical_source_circuit" else
            "scaffold" if row["uncertainty_group"] == "algebraic_scaffold" else "assumed")
        entries.append(dict(branch_key=row["branch_key"], model_branch_row=row["model_branch_row"],
            from_bus=int(row["from_bus"]), to_bus=int(row["to_bus"]), category=category,
            active_in_core=active, parameter_basis=row["parameter_basis"], project=row["project"],
            assumption=row["assumption"], source_branch_row=row["source_branch_row"]))
    for j, row in enumerate(case["dcline"], 1):
        entries.append(dict(branch_key=f"DC:{j}", model_branch_row=0, from_bus=int(row[0]), to_bus=int(row[1]),
            category="dc", active_in_core=bool(row[2]), parameter_basis="unchanged inherited scheduled-transfer equivalent",
            project="", assumption="four channel endpoints unchanged; equivalent is not necessarily a physical HVDC circuit", source_branch_row=0))
    edge = pd.DataFrame(entries)
    counts = edge.category.value_counts().to_dict()
    require(counts == dict(retained=216, source=97, assumed=22, replaced=9, dc=4, scaffold=1), "Unexpected branch categories")
    return buses, edge, counts


def grouped_edges(edges, selected):
    groups = {}
    for r in edges.to_dict("records"):
        if r["from_bus"] not in selected or r["to_bus"] not in selected:
            continue
        key = (*sorted([r["from_bus"], r["to_bus"]]), r["category"])
        groups.setdefault(key, []).append(r)
    return groups


def node_label(row):
    name = str(row.model_name)
    # Source names are preserved in the ledger; remove only duplicated kV
    # suffixes because the second line prints the voltage explicitly.
    name = re.sub(r" (345|138|69)$", "", name)
    kv = f"{row.base_kv:g} kV"
    new = row.identity_role != "original_parent"
    label = f"{name}\n#{row.model_bus}  |  {kv}"
    if row.model_bus == 20004:
        label += "\nNYES idle placeholder"
    elif row.model_bus in [78, 79, 82]:
        label += "\ninherited aggregate proxy"
    return label, new


def render(name, title, subtitle, buses, edges, selected, groups, dpi=115):
    view = buses[buses.model_bus.isin(selected)]
    nnew = int(view.identity_role.ne("original_parent").sum())
    graph = graphviz.Graph(name, engine="neato")
    caption = ('<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="2"><TR><TD ALIGN="LEFT">'
        '<FONT POINT-SIZE="22">' + html.escape(title) + '</FONT></TD></TR><TR><TD ALIGN="LEFT">'
        '<FONT POINT-SIZE="15">' + html.escape(f"{nnew} added buses / {len(view)} shown  |  " + subtitle) + '</FONT></TD></TR>'
        '<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="12">Blue square boxes: ADDED buses; gray rounded boxes: ORIGINAL buses. Labels = name / model ID / nominal kV.</FONT></TD></TR>'
        '<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="12" COLOR="#226AA5">Blue lines: added historical source circuits</FONT>  |  '
        '<FONT POINT-SIZE="12" COLOR="#B87518">Gold dashed: added assumed connections</FONT></TD></TR>'
        '<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="12" COLOR="#C04754">Red dashed: replaced original branches (inactive)</FONT>  |  '
        '<FONT POINT-SIZE="12" COLOR="#73508E">Purple: unchanged DC equivalents</FONT>  |  '
        '<FONT POINT-SIZE="12" COLOR="#7E8791">Gray: retained; gray dotted: idle scaffold</FONT></TD></TR>'
        '<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="12">xN = parallel branch count. Schematic, not geographic. Cross-voltage proxies are not certified physical transformers.</FONT></TD></TR></TABLE>>')
    graph.attr(overlap="false", sep="+16", splines="true", outputorder="edgesfirst",
               start="17", bgcolor="white", fontname="Arial", fontsize="22", fontcolor="#223246",
               label=caption,
               labelloc="t", labeljust="l", pad="0.35", margin="0", dpi=str(dpi))
    graph.attr("node", shape="box", style="rounded,filled", fontname="Arial", fontsize="12", margin="0.10,0.08",
               color="#8E99A6", fillcolor="#F1F3F5", fontcolor="#293648", penwidth="1.0")
    for row in view.itertuples(index=False):
        label, new = node_label(row)
        tooltip = (f"Bus {row.model_bus}: {row.model_name}; {row.base_kv:g} kV; accounting zone {row.accounting_zone}; "
                   f"{'ADDED' if new else 'ORIGINAL'}; {row.identity_role}; source bus {row.source_bus}")
        graph.node(str(row.model_bus), label=label, id=f"bus-{row.model_bus}", tooltip=tooltip,
                   fillcolor="#DBEEF9" if new else "#F1F3F5", color="#226AA5" if new else "#8E99A6",
                   penwidth="2.1" if new else "1.0", style="filled" if new else "rounded,filled")
    for (a, b, category), records in groups.items():
        count = len(records)
        text = ""
        if category == "replaced":
            text = "replaced " + "/".join("P" + str(r["model_branch_row"]) for r in records)
        elif category == "dc":
            text = "/".join(r["branch_key"] for r in records)
        elif count > 1:
            text = f"x{count}"
        elif category == "scaffold":
            text = "idle"
        tooltip = LABELS[category] + " | " + "; ".join(
            f"{r['branch_key']} (model row {r['model_branch_row']}; {r['parameter_basis']})" for r in records)
        graph.edge(str(a), str(b), label=text, tooltip=tooltip, id=f"edge-{a}-{b}-{category}",
            color=COLORS[category], fontcolor=COLORS[category], fontname="Arial", fontsize="10",
            penwidth="1.1" if category == "retained" else "2.0",
            style="dashed" if category in ["replaced", "assumed"] else "dotted" if category == "scaffold" else "solid",
            len="2.0" if category in ["source", "assumed"] else "2.8", weight="0.05" if category == "replaced" else "1")
    dot_path = OUT / (name + ".dot")
    dot_path.write_text(graph.source, encoding="utf-8", newline="\n")
    # One layout, then identical fixed coordinates for SVG, PNG and PDF.
    layout = subprocess.check_output(["neato", "-Tdot", str(dot_path)])
    (OUT / (name + "_layout.dot")).write_bytes(layout)
    for fmt in ["svg", "png", "pdf"]:
        subprocess.run(["neato", "-n2", "-Gdpi=" + (str(dpi) if fmt == "png" else "72"),
                        "-T" + fmt, "-o", str(OUT / (name + "." + fmt))], input=layout, check=True)
    svg = (OUT / (name + ".svg")).read_text(encoding="utf-8")
    for bus in selected:
        require(f'id="bus-{bus}"' in html.unescape(svg), f"Bus {bus} missing from SVG")
    return dict(view=name, title=title, buses=len(selected), added_buses=nnew, branch_groups=len(groups),
                individual_branch_records=sum(len(v) for v in groups.values()), bus_ids=sorted(selected))


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    buses, edges, counts = collect()
    added = set(buses.loc[buses.identity_role.ne("original_parent"), "model_bus"])
    changed = edges[edges.category.isin(["source", "assumed", "scaffold", "replaced"])]
    focus = added | set(changed.from_bus) | set(changed.to_bus)
    northern = {35,39,73,74,76,77,78} | set(buses.loc[buses.model_bus.isin(added) & buses.accounting_zone.isin(["G","I","NA"]), "model_bus"])
    metro = {74,78,79,80,81,82} | set(buses.loc[buses.model_bus.isin(added) & buses.accounting_zone.isin(["I","J"]), "model_bus"])
    island = {78,79,80} | set(buses.loc[buses.model_bus.isin(added) & buses.accounting_zone.eq("K"), "model_bus"])
    # Include every direct boundary neighbor so regional panels expose cut edges.
    def neighbors(selected, categories):
        linked = edges[edges.category.isin(categories) & (edges.from_bus.isin(selected) | edges.to_bus.isin(selected))]
        return selected | set(linked.from_bus) | set(linked.to_bus)
    island = neighbors(island, ["source", "assumed", "scaffold", "replaced"])
    views = []
    for name, title, subtitle, selected in [
        ("downstate_changes", "Downstate additions and replaced aggregate branches", "year-end 2025 core; optional NYES paths excluded", focus),
        ("full_npcc", "Full NPCC backbone with all 51 added buses", "all active AC branches, four DC equivalents and nine retired aggregate rows", set(buses.model_bus)),
        ("hudson_westchester", "Hudson Valley and Westchester detail", "regional crop; connections outside this view remain in the full network", northern),
        ("new_york_city", "New York City receiving network detail", "regional crop; connections outside this view remain in the full network", metro),
        ("long_island", "Long Island detail and its neighboring connections", "K backbone, J-K ties and East Hampton terminal", island),
    ]:
        views.append(render(name, title, subtitle, buses, edges, selected, grouped_edges(edges, selected)))
    buses.assign(added_to_parent=buses.model_bus.isin(added)).to_csv(OUT / "diagram_buses.csv", index=False, lineterminator="\n")
    edges.to_csv(OUT / "diagram_branches.csv", index=False, lineterminator="\n")
    require(set(views[0]["bus_ids"]) >= added, "Change view omits an added bus")
    require(sum(len(x) for x in grouped_edges(edges, focus).values() if x[0]["category"] == "replaced") == 9, "Missing replaced original branch")
    inputs = [BASE / "network/bus_register.csv", BASE / "network/branch_register.csv", BASE / "network/network_cases.mat", Path(__file__)]
    result = dict(passed=True, state=STATE, original_buses=140, added_buses=51, total_buses=191,
        branch_counts=counts, active_AC_branches=336, displayed_inactive_parent_branches=9,
        parallel_circuits_bundled_for_drawing_only=True, geographic_layout=False, original_model_artifacts_changed=False,
        optional_NYES_circuits_displayed=False, added_idle_Knickerbocker_bus_displayed=True,
        views=views, source_files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in inputs],
        graphviz_version=subprocess.check_output(["neato", "-V"], stderr=subprocess.STDOUT).decode().strip())
    (OUT / "diagram_validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ["source_files","views"]}, indent=2))


if __name__ == "__main__":
    build()
