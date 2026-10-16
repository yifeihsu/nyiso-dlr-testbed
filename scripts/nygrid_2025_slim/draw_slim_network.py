"""Show the eight retained additions and distinguish physical/source equivalents."""
from pathlib import Path
import hashlib
import html
import json
import subprocess
import graphviz
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/"output/nygrid_2025_slim"
COLORS={"parent":"#BCC4CD","physical":"#226AA5","assumed":"#B87518","equivalent":"#8062A6","replaced":"#C04754"}


def build():
    out=BASE/"diagrams";out.mkdir(parents=True,exist_ok=True)
    buses=pd.read_csv(BASE/"network/bus_register.csv",keep_default_na=False).set_index("model_bus")
    branches=pd.read_csv(BASE/"network/branch_register.csv",keep_default_na=False)
    classes={}
    for row in branches.to_dict("records"):
        if row["model_branch_row"]<=225:
            category="parent" if row["refined_2025_status"] else "replaced"
        elif row["role"]=="exact_historical_source_circuit":category="physical"
        elif "equivalent" in row["role"].lower() or "schur" in row["role"].lower():category="equivalent"
        else:category="assumed"
        # The saved provenance boolean separates copied source circuits from
        # proxy attachments regardless of future role wording refinements.
        if row["model_branch_row"]>225 and str(row["physical_source_row_exact"]).lower()=="true":category="physical"
        classes[int(row["model_branch_row"])]=category
    additions=set(buses.index[buses.identity_role.ne("original_parent")])
    # All local changes are shown, including inactive predecessor records.
    changed=branches[branches.model_branch_row.map(classes).ne("parent")]
    shown=additions|set(changed.from_bus)|set(changed.to_bus)
    g=graphviz.Graph("critical_transmission_buses",engine="neato")
    g.attr(overlap="false",sep="+18",splines="true",start="23",outputorder="edgesfirst",bgcolor="white",pad="0.35",dpi="120")
    label=('<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="3"><TR><TD ALIGN="LEFT"><FONT POINT-SIZE="22">Eight critical added buses — transmission-focused alternative</FONT></TD></TR>'
           '<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="14">148 total buses = all140 original +8 additions;54 NY buses =46 original +8. Local change view; full backbone retained.</FONT></TD></TR>'
           '<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="12">Blue boxes: eight added345kV buses. Gray boxes: original NPCC terminals.</FONT></TD></TR>'
           '<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="12" COLOR="#226AA5">Blue:14 retained historical circuits</FONT> | <FONT POINT-SIZE="12" COLOR="#B87518">Gold:5 retained assumed connections</FONT></TD></TR>'
           '<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="12" COLOR="#8062A6">Purple dotted:30 DC equivalents of omitted detail</FONT> | <FONT POINT-SIZE="12" COLOR="#C04754">Red dashed:9 replaced inactive originals</FONT></TD></TR>'
           '<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="12">Equivalent connections are not individual physical lines and are not DLR-qualified. xN = parallel circuit count. Schematic layout.</FONT></TD></TR></TABLE>>')
    g.attr(label=label,labelloc="t",labeljust="l",fontname="Arial",fontcolor="#253144")
    for key in sorted(shown):
        row=buses.loc[key];added=key in additions
        name=str(row.model_name)
        if name.endswith(" 345"):name=name[:-4]
        g.node(str(key),f"{name}\n#{key} | {row.base_kv:g} kV",id=f"bus-{key}",shape="box",fontname="Arial",fontsize="13",
            style="filled" if added else "rounded,filled",fillcolor="#DCEFFA" if added else "#F1F3F5",
            color="#226AA5" if added else "#A5AFBC",penwidth="2.1" if added else "1",margin=".12,.08")
    groups={}
    for row in branches.to_dict("records"):
        a,b=int(row["from_bus"]),int(row["to_bus"])
        if a not in shown or b not in shown:continue
        if not row["refined_2025_status"] and row["model_branch_row"]>225:continue
        category=classes[int(row["model_branch_row"])]
        groups.setdefault((*sorted([a,b]),category),[]).append(row)
    for (a,b,category),records in groups.items():
        text="x"+str(len(records)) if len(records)>1 else ""
        if category=="replaced":text="P"+str(records[0]["model_branch_row"])
        g.edge(str(a),str(b),label=text,color=COLORS[category],fontcolor=COLORS[category],fontname="Arial",fontsize="10",
            style="dotted" if category=="equivalent" else "dashed" if category in ["replaced","assumed"] else "solid",
            penwidth=".85" if category=="equivalent" else "1.6",len="2.4",weight=".1" if category in ["equivalent","replaced"] else "1",
            tooltip="; ".join(r["branch_key"] for r in records))
    path=out/"eight_bus_network.dot";path.write_text(g.source,encoding="utf-8",newline="\n")
    layout=subprocess.check_output(["neato","-Tdot",str(path)])
    (out/"eight_bus_network_layout.dot").write_bytes(layout)
    for ext in ["svg","png","pdf"]:
        subprocess.run(["neato","-n2","-Gdpi="+("120" if ext=="png" else "72"),"-T"+ext,"-o",str(out/("eight_bus_network."+ext))],input=layout,check=True)
    svg=html.unescape((out/"eight_bus_network.svg").read_text())
    assert len(additions)==8 and all(f'id="bus-{key}"' in svg for key in additions)
    counts={category:sum(1 for r in changed.to_dict("records") if classes[int(r["model_branch_row"])]==category and(r["refined_2025_status"]or category=="replaced")) for category in ["physical","assumed","equivalent","replaced"]}
    assert counts==dict(physical=14,assumed=5,equivalent=30,replaced=9),counts
    receipt=dict(passed=True,added_buses=sorted(map(int,additions)),shown_bus_ids=sorted(map(int,shown)),branch_counts=counts,
        source_files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in [BASE/"network/bus_register.csv",BASE/"network/branch_register.csv",Path(__file__)]])
    (out/"diagram_validation.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(receipt["branch_counts"]))


if __name__=="__main__":build()
