"""Static geographic views and GeoJSON for all140 original buses plus8 hubs.

Coordinates are an exact selection of the frozen191-bus geographic register.
Original aggregate proxies78/79/82 remain nongeographic. Straight connections
are model adjacency, never inferred transmission routes. Equivalent branches
are deliberately shown as purple dotted DC response connections.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Rectangle
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "output/nygrid_2025_downstate/geography"
BASE = ROOT / "output/nygrid_2025_slim"
OUT = BASE / "geography"
FIGURES = OUT / "figures"
SOURCE_COORDS = OLD / "bus_geographic_register.csv"
PINNED_COORD_SHA = "7aaedd8f68e6c1a9d2c13cf19158abe604a57c669ef1c3aa7e07df2e33476973"
NETWORK = BASE / "network/network_cases.mat"
PINNED_NETWORK_SHA = "3c990e658464037ad36ab427150ba3c358624c1d0e3d795adb90aca91abdbc58"
PROXIES = {78,79,82}
STATE = "refined_2025"
EXPECTED = dict(retained=216,source=14,assumed=5,equivalent=30,replaced=9,dc=4)
COLORS = dict(retained="#A5AEB8",source="#2166A5",assumed="#BA801D",equivalent="#8050A0",replaced="#C64C58",dc="#157F83")
STYLES = dict(retained="-",source="-",assumed="--",equivalent=":",replaced="--",dc="-.")
TITLES = dict(retained="Original retained (216)",source="Direct source circuit (14)",assumed="Declared connection (5)",
              equivalent="DC response equivalent (30)",replaced="Original replaced / inactive (9)",dc="Fixed DC transfer channel (4)")
NYC_BOUNDS = (-74.27,40.54,-73.48,41.10)
REGION_BOUNDS = (-74.43,40.48,-72.60,41.88)

# Reuse only pure projection, basemap and label-placement helpers. None of
# the191-bus pipeline's collect/export/build/save functions is called.
sys.path.insert(0,str(ROOT / "scripts/nygrid_2025_downstate"))
import build_geographic_diagrams as map_helpers


def require(condition,message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def native(value):
    if isinstance(value,np.generic):value=value.item()
    if isinstance(value,float) and not np.isfinite(value):return None
    return value


def collect():
    require(sha(SOURCE_COORDS)==PINNED_COORD_SHA,"Frozen geographic source changed")
    require(sha(NETWORK)==PINNED_NETWORK_SHA,"Frozen slim network changed")
    data=loadmat(NETWORK,simplify_cells=True);case=data[STATE+"_case"]
    ids=np.asarray(data["kept_bus_ids"],int)
    source=pd.read_csv(SOURCE_COORDS,keep_default_na=False,float_precision="round_trip")
    require(source.model_bus.is_unique,"Duplicate source coordinate ID")
    registry=source.set_index("model_bus").loc[ids].copy()
    require(len(registry)==148 and np.array_equal(ids[:140],np.arange(1,141)),"Not the148-bus model")
    for field in ["plot_on_geographic_map","added_bus"]:
        registry[field]=registry[field].astype(str).str.lower().eq("true")
    require(set(registry.index[~registry.plot_on_geographic_map])==PROXIES,"Proxy geography changed")
    require(registry.added_bus.sum()==8 and registry.loc[registry.added_bus,"base_kv"].eq(345).all(),"Added station contract changed")
    for field in ["latitude_deg","longitude_deg","map_latitude_deg","map_longitude_deg","projected_easting_km","projected_northing_km"]:
        registry[field]=pd.to_numeric(registry[field],errors="coerce")
    require(np.isfinite(registry.loc[registry.plot_on_geographic_map,["map_latitude_deg","map_longitude_deg"]]).all().all(),"Mapped coordinates missing")
    x,y=map_helpers.xy(registry.map_longitude_deg.to_numpy(),registry.map_latitude_deg.to_numpy())
    mapped=registry.plot_on_geographic_map.to_numpy()
    projection_error=max(float(np.max(abs(x[mapped]-registry.projected_easting_km.to_numpy()[mapped]))),
                         float(np.max(abs(y[mapped]-registry.projected_northing_km.to_numpy()[mapped]))))
    require(projection_error<1e-9,"Projection differs from saved geographic positions")
    branches=pd.read_csv(BASE/"network/branch_register.csv",keep_default_na=False)
    require(len(branches)==274 and np.array_equal(branches[STATE+"_status"],case["branch"][:,10]),"Branch register mismatch")
    entries=[]
    for record,values in zip(branches.to_dict("records"),case["branch"]):
        role=record["role"];active=bool(values[10])
        category=("retained" if active else "replaced") if role=="original_parent_record" else {
            "exact_retained_source_circuit":"source","retained_declared_assumption":"assumed",
            "passive_DC_Schur_equivalent":"equivalent"}[role]
        entries.append(dict(branch_key=record["branch_key"],model_branch_row=int(record["model_branch_row"]),
                            from_bus=int(values[0]),to_bus=int(values[1]),category=category,active_in_core=active,
                            state=STATE,parameter_basis=record["parameter_basis"],source_branch_row=int(record["source_PERFORM_row"]),
                            full191_branch_row=int(record["full191_branch_row"]),project="",assumption="" if category=="source" else record["parameter_basis"],
                            x_pu_model=float(values[3]),nominal_from_kv=float(registry.loc[int(values[0]),"base_kv"]),
                            nominal_to_kv=float(registry.loc[int(values[1]),"base_kv"]),
                            equivalent_is_physical_circuit=False if category=="equivalent" else None,
                            thermal_DLR_qualified=False))
    for j,values in enumerate(case["dcline"],1):
        entries.append(dict(branch_key=f"DC:{j}",model_branch_row=0,from_bus=int(values[0]),to_bus=int(values[1]),
                            category="dc",active_in_core=bool(values[2]),state=STATE,
                            parameter_basis="unchanged_inherited_scheduled_transfer_equivalent",source_branch_row=0,full191_branch_row=0,
                            project="",assumption="Scheduled transfer channel, not a claim of a physical HVDC route",x_pu_model=None,
                            nominal_from_kv=float(registry.loc[int(values[0]),"base_kv"]),nominal_to_kv=float(registry.loc[int(values[1]),"base_kv"]),
                            equivalent_is_physical_circuit=False,thermal_DLR_qualified=False))
    edges=pd.DataFrame(entries)
    require(edges.category.value_counts().to_dict()==EXPECTED,"Unexpected edge classification counts")
    require(edges.branch_key.is_unique,"Duplicate edge identity")
    require(set(edges.from_bus)|set(edges.to_bus)<=set(ids),"Connection contains an eliminated bus")
    return registry,edges,projection_error


def export_data(registry,edges):
    OUT.mkdir(parents=True,exist_ok=True)
    registry.reset_index().to_csv(OUT/"bus_geographic_register.csv",index=False,lineterminator="\n")
    nodes=[]
    for bid,row in registry.iterrows():
        props=dict(model_bus=int(bid),name=str(row.model_name),model_name=str(row.model_name),base_kv=float(row.base_kv),
                   added=bool(row.added_bus),accounting_zone=str(row.accounting_zone),coordinate_basis=str(row.coordinate_basis),
                   coordinate_quality=str(row.coordinate_quality),source=str(row.coordinate_source),notes=str(row.notes),
                   map_anchor_policy=str(row.map_anchor_policy),preserved_source_latitude=float(row.latitude_deg),
                   preserved_source_longitude=float(row.longitude_deg),plot_on_geographic_map=bool(row.plot_on_geographic_map),
                   role="added_345kv_transmission_station" if row.added_bus else "original_aggregate_proxy" if bid in PROXIES else "original_NPCC_bus")
        geometry=dict(type="Point",coordinates=[float(row.map_longitude_deg),float(row.map_latitude_deg)]) if row.plot_on_geographic_map else None
        nodes.append(dict(type="Feature",id=f"bus-{bid}",geometry=geometry,properties=props))
    connections=[]
    for raw in edges.to_dict("records"):
        row={k:native(v) for k,v in raw.items()}
        a,b=registry.loc[row["from_bus"]],registry.loc[row["to_bus"]]
        geometry=None
        if a.plot_on_geographic_map and b.plot_on_geographic_map:
            points=[[float(a.map_longitude_deg),float(a.map_latitude_deg)],[float(b.map_longitude_deg),float(b.map_latitude_deg)]]
            geometry=dict(type="Point",coordinates=points[0]) if points[0]==points[1] else dict(type="LineString",coordinates=points)
        row.update(geometry_is_physical_line_route=False,unlocated_endpoint=geometry is None,
                   co_located_endpoints=bool(geometry and geometry["type"]=="Point"),
                   from_name=str(a.model_name),to_name=str(b.model_name))
        connections.append(dict(type="Feature",id=row["branch_key"],geometry=geometry,properties=row))
    for name,features in [("geographic_nodes",nodes),("geographic_connections",connections)]:
        (OUT/(name+".geojson")).write_text(json.dumps(dict(type="FeatureCollection",features=features),indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return dict(node_features=len(nodes),mapped_nodes=sum(x["geometry"] is not None for x in nodes),
                connection_features=len(connections),mapped_connections=sum(x["geometry"] is not None for x in connections),
                nongeographic_connections=sum(x["geometry"] is None for x in connections))


def groups(edges,selected):
    result=defaultdict(list)
    for row in edges.to_dict("records"):
        a,b=row["from_bus"],row["to_bus"]
        if a in selected and b in selected:result[(*sorted([a,b]),row["category"])].append(row)
    return result


def name_label(row):
    name=re.sub(r" (345|138|69)$","",str(row.model_name))
    if row.name==80:name+=" †"
    return f"{name}\n#{int(row.name)} · {row.base_kv:g} kV"


def draw_map(ax,registry,edges,bounds,label_ids,fontsize=9):
    map_helpers.basemap(ax,bounds)
    shown=registry.loc[registry.plot_on_geographic_map & registry.map_longitude_deg.between(bounds[0],bounds[2]) & registry.map_latitude_deg.between(bounds[1],bounds[3])]
    grouped=groups(edges,set(shown.index))
    # Gray backbone first; purple response equivalents remain visibly distinct.
    for category in ["retained","equivalent","assumed","source","dc","replaced"]:
        for (a,b,c),records in grouped.items():
            if c!=category:continue
            ra,rb=registry.loc[a],registry.loc[b]
            A=(ra.projected_easting_km,ra.projected_northing_km);B=(rb.projected_easting_km,rb.projected_northing_km)
            width=.55 if c=="retained" else 1.35
            alpha=.55 if c in ["retained","equivalent"] else .88
            coincident=any((a,b,other) in grouped for other in ["retained","source","assumed"] if other!=c)
            gid="branch-"+"-".join(r["branch_key"] for r in records)
            if coincident and c in ["replaced","equivalent"]:
                radius=.075 if c=="replaced" else -.055
                ax.add_patch(FancyArrowPatch(A,B,connectionstyle=f"arc3,rad={radius}",arrowstyle="-",shrinkA=0,shrinkB=0,
                                            color=COLORS[c],linestyle=STYLES[c],lw=width,alpha=alpha,zorder=3,gid=gid))
            else:
                ax.plot([A[0],B[0]],[A[1],B[1]],color=COLORS[c],ls=STYLES[c],lw=width,alpha=alpha,zorder=2,gid=gid)
            if len(records)>1 and c=="source":
                ax.text((A[0]+B[0])/2,(A[1]+B[1])/2,f"×{len(records)}",fontsize=7.5,color=COLORS[c],ha="center",va="center",
                        bbox=dict(fc="white",ec="none",pad=.3,alpha=.9),zorder=4)
    originals=shown.loc[~shown.added_bus]
    approximate=originals.coordinate_basis.eq("published_NPCC_model_point")
    for frame,hollow in [(originals.loc[approximate],True),(originals.loc[~approximate],False)]:
        ax.scatter(frame.projected_easting_km,frame.projected_northing_km,s=18,marker="o",facecolors="white" if hollow else "#667685",
                   edgecolors="#8796A5",linewidths=.7,zorder=5)
    additions=shown.loc[shown.added_bus]
    ax.scatter(additions.projected_easting_km,additions.projected_northing_km,s=43,marker="s",facecolors=COLORS["source"],
               edgecolors="white",linewidths=.7,zorder=6)
    wanted=shown.loc[shown.index.intersection(list(label_ids))]
    labels,targets=[],[]
    for bid,row in wanted.iterrows():
        label=ax.text(row.projected_easting_km,row.projected_northing_km,name_label(row),fontsize=fontsize,ha="center",va="center",
                      color="#214965" if row.added_bus else "#526170",zorder=9,
                      bbox=dict(boxstyle="round,pad=.23",fc="white",ec="#A8C4D9" if row.added_bus else "#CCD2D7",lw=.6,alpha=.96),
                      gid=f"label-bus-{bid}")
        labels.append(label);targets.append((row.projected_easting_km,row.projected_northing_km))
    placed=map_helpers.place_labels(ax,labels,targets,shown[["projected_easting_km","projected_northing_km"]].to_numpy())
    return dict(geographic_bus_ids=list(map(int,shown.index)),labeled_bus_ids=list(map(int,wanted.index)),
                shown_connection_records=sum(len(v) for v in grouped.values()),label_placement=placed,geographic_anchors_not_displaced=True)


def proxy_panel(ax,registry,edges):
    ax.axis("off");ax.set_xlim(0,1);ax.set_ylim(0,1)
    ax.set_title("Aggregate proxies — nongeographic inset",loc="left",fontsize=11,pad=10)
    details=[]
    for bid,y in [(78,.78),(79,.47),(82,.16)]:
        node=registry.loc[bid]
        incident=edges.loc[edges.from_bus.eq(bid)|edges.to_bus.eq(bid)]
        counts=incident.category.value_counts().to_dict()
        count_text=" · ".join(f"{counts[k]} {label}" for k,label in [("assumed","declared"),("equivalent","DC response"),("dc","DC transfer"),("replaced","inactive")] if counts.get(k))
        ax.scatter([.035],[y],marker="D",s=50,facecolors="white",edgecolors="#7F8B96",linewidths=1.1)
        ax.text(.075,y+.065,f"{node.model_name}  #{bid}  |  {node.base_kv:g} kV  |  zone {node.accounting_zone}",fontsize=10,va="center",color="#3F5061")
        ax.text(.075,y-.035,count_text,fontsize=8.7,va="center",color="#6A7582")
        details.append(dict(model_bus=bid,incident_connection_records=len(incident),category_counts=counts))
    return dict(proxy_ids=sorted(PROXIES),geographic_positions_invented=False,connections=details)


def header(fig,title,subtitle):
    fig.suptitle(title,x=.035,y=.976,ha="left",fontsize=19,color="#25384B")
    fig.text(.035,.949,subtitle,fontsize=10.5,color="#526275")
    handles=[Line2D([0],[0],marker="s",color="none",markerfacecolor=COLORS["source"],markeredgecolor="white",markersize=7,label="Eight added 345-kV stations"),
             Line2D([0],[0],marker="o",color="none",markerfacecolor="white",markeredgecolor="#8796A5",markersize=6,label="Approximate original model point")]
    handles += [Line2D([0],[0],color=COLORS[c],ls=STYLES[c],lw=1.6,label=TITLES[c]) for c in ["retained","source","assumed","equivalent","replaced","dc"]]
    fig.legend(handles=handles,loc="upper left",bbox_to_anchor=(.03,.941),ncol=4,frameon=False,fontsize=8.8,columnspacing=1.7)
    fig.text(.035,.041,"Lines show model connections, not transmission routes. Purple dotted connections are passive DC equivalents, not physical circuits.",fontsize=9,color="#465A6E")
    fig.text(.035,.027,"145 mapped points + 3 aggregate proxies. Original locations: 129 approximate model points, 8 station anchors, 3 unlocated proxies. † Northport is a facility-level anchor.",fontsize=8.5,color="#607184")
    fig.text(.035,.013,"Sources: frozen PERFORM / NPCC geographic register; owner GIS; © OpenStreetMap contributors (ODbL1.0). Natural Earth basemap: public domain. Lambert conformal conic projection.",fontsize=8.5,color="#607184")


def save(fig,name):
    FIGURES.mkdir(parents=True,exist_ok=True)
    for ext in ["png","svg","pdf"]:
        fig.savefig(FIGURES/(name+"."+ext),dpi=160,facecolor="white",metadata={"Creator":"NPCC reproducible slim geographic diagram"} if ext=="pdf" else None)
    plt.close(fig)


def figures(registry,edges):
    plt.rcParams.update({"font.family":"DejaVu Sans","svg.fonttype":"none","pdf.fonttype":42})
    added=set(registry.index[registry.added_bus]);anchors={35,39,73,74,76,77,80,81}
    city_labels={10593,10589,11129,11130,80,81}
    upper_labels={10774,10858,10902,20001,35,73,74,76,77}
    fig=plt.figure(figsize=(22,15));gs=fig.add_gridspec(2,2,left=.035,right=.975,bottom=.08,top=.865,width_ratios=[1.05,1],height_ratios=[.72,.28],wspace=.12,hspace=.18)
    main=fig.add_subplot(gs[:,0]);city=fig.add_subplot(gs[0,1]);proxy=fig.add_subplot(gs[1,1])
    header(fig,"Geographic transmission map — eight retained additions","148 buses = all 140 original NPCC buses + 8 transmission stations · year-end 2025 topology · 265 active branch records")
    main.set_title("Hudson Valley, Connecticut and Long Island",loc="left",fontsize=12)
    city.set_title("NYC / Westchester / western Long Island",loc="left",fontsize=12)
    regional=draw_map(main,registry,edges,REGION_BOUNDS,upper_labels,10)
    enlarged=draw_map(city,registry,edges,NYC_BOUNDS,city_labels,10)
    x,y=map_helpers.xy([NYC_BOUNDS[0],NYC_BOUNDS[2]],[NYC_BOUNDS[1],NYC_BOUNDS[3]])
    main.add_patch(Rectangle((min(x),min(y)),abs(x[1]-x[0]),abs(y[1]-y[0]),fill=False,ec="#657C90",lw=.8,ls=":"))
    main.text(min(x),max(y)+3,"Enlarged at right",fontsize=8.5,color="#526275")
    inset=proxy_panel(proxy,registry,edges)
    require(added<=set(regional["labeled_bus_ids"])|set(enlarged["labeled_bus_ids"]),"Missing added station label")
    save(fig,"geographic_slim_atlas")
    fig,ax=plt.subplots(figsize=(17,13));fig.subplots_adjust(left=.04,right=.97,bottom=.085,top=.855)
    header(fig,"NYC and western Long Island — slim geographic detail","Four added 345-kV receiving stations · equivalents explicitly separated from direct source circuits")
    detail=draw_map(ax,registry,edges,NYC_BOUNDS,city_labels,11)
    save(fig,"geographic_slim_nyc_detail")
    fig=plt.figure(figsize=(23,15));ax=fig.add_axes([.035,.09,.79,.755]);inset_ax=fig.add_axes([.835,.20,.15,.31])
    header(fig,"Full NPCC geographic context — 148-bus model","All 140 original buses retained · eight blue station markers highlighted · see regional atlas for their names and kV")
    names={1,16,28,35,43,47,50,52,54,69,83,85,91,92,115,124,125,130,134,138,140}
    full=draw_map(ax,registry,edges,(-86.3,38.4,-68.5,47.0),names,8.5)
    inset_ax.axis("off")
    inset_ax.text(0,.96,"Eight retained additions",fontsize=11,color="#25384B",weight="bold",va="top")
    for j,bid in enumerate([10858,10902,10774,10593,10589,11129,11130,20001]):
        row=registry.loc[bid]
        inset_ax.text(0,.87-j*.09,name_label(row).replace("\n","  "),fontsize=8.8,color="#2166A5",va="top")
    inset_ax.text(0,.06,"Proxies 78 / 79 / 82\nare not plotted geographically.",fontsize=9,color="#667685",va="top")
    require(set(full["geographic_bus_ids"])==set(registry.index)-PROXIES,"Full geographic view omits mapped buses")
    save(fig,"geographic_slim_full_npcc")
    return dict(atlas_regional=regional,atlas_city=enlarged,aggregate_proxy_inset=inset,city_detail=detail,full_npcc=full)


def build(data_only=False):
    protected=[NETWORK,SOURCE_COORDS,ROOT/"output/nygrid_2025_downstate/network/network_cases.mat",ROOT/"output/nygrid_2025_dispatch/dispatch/dispatch.mat"]
    before={str(p.relative_to(ROOT)).replace("\\","/"):sha(p) for p in protected}
    registry,edges,projection_error=collect();exports=export_data(registry,edges)
    views={} if data_only else figures(registry,edges)
    require(all(sha(ROOT/p)==value for p,value in before.items()),"A frozen source changed while creating geography")
    sources=protected+[BASE/"network/branch_register.csv",OLD/"basemap/basemap_receipt.json",Path(__file__),
                       ROOT/"scripts/nygrid_2025_downstate/build_geographic_diagrams.py",ROOT/"scripts/nygrid_2025_downstate/build_network_diagrams.py"]
    sources+=sorted((OLD/"basemap").glob("*.geojson"))
    outputs=[OUT/"bus_geographic_register.csv",OUT/"geographic_nodes.geojson",OUT/"geographic_connections.geojson"]
    if not data_only:outputs+=sorted(FIGURES.glob("*"))
    receipt=dict(passed=True,figures_complete=not data_only,status="data_ready_figures_pending" if data_only else "complete_static_geography_and_map_exports",
                 state=STATE,total_buses=148,original_buses=140,added_buses=8,added_bus_ids=list(map(int,registry.index[registry.added_bus])),
                 added_nominal_kv=345,geographic_bus_records=145,nongeographic_original_proxy_buses=sorted(PROXIES),
                 coordinate_policy="exact_subset_of_frozen191_geographic_register_no_new_geocoding_or_imputation",
                 original_model_coordinate_points_approximate=129,original_source_backed_station_anchors=8,
                 branch_counts=EXPECTED,active_network_branch_records=265,inactive_replaced_branch_records=9,scheduled_DC_channels=4,
                 equivalents_are_physical_circuits=False,branch_lines_are_actual_routes=False,parallel_records_share_display_stroke=True,
                 projected_crs=map_helpers.CRS_TEXT,maximum_projected_coordinate_difference_km=projection_error,
                 original_network_and_PG_files_unchanged=True,coordinate_features=exports,views=views,
                 inputs=[dict(path=str(p.relative_to(ROOT)).replace("\\","/"),sha256=sha(p)) for p in sources],
                 outputs=[dict(path=str(p.relative_to(ROOT)).replace("\\","/"),sha256=sha(p)) for p in outputs])
    (OUT/"geographic_validation.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:receipt[k] for k in ["status","total_buses","added_buses","geographic_bus_records","branch_counts","coordinate_features"]},indent=2))
    return receipt


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--data-only",action="store_true")
    build(parser.parse_args().data_only)
