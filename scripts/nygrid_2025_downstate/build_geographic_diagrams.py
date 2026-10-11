"""Geographic figures with preserved coordinates and explicit nonphysical proxies.

Only text labels move for readability. Lines connect modeled endpoints directly;
they do not purport to trace real transmission rights-of-way or cable routes.
"""
from __future__ import annotations
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import PathPatch, Rectangle, FancyArrowPatch
from matplotlib.path import Path as MplPath
import networkx as nx
import numpy as np
import pandas as pd
from pyproj import CRS, Transformer
from shapely.geometry import shape, box
from shapely import transform as project_geometry

from build_network_diagrams import collect, COLORS, ROOT, BASE, grouped_edges

GEO = BASE / "geography"
OUT = GEO / "figures"
PROXY_IDS = {78, 79, 82}
CRS_TEXT = "+proj=lcc +lat_1=40 +lat_2=45 +lat_0=42 +lon_0=-76 +datum=WGS84 +units=m +no_defs"
PROJ = Transformer.from_crs("EPSG:4326", CRS.from_proj4(CRS_TEXT), always_xy=True)
HOST = {20009: 11129, 20010: 81, 20014: 11130}
NAMES = {"retained": "Retained original branch", "source": "Added historical circuit",
    "assumed": "Added assumed connection", "replaced": "Replaced original (inactive)",
    "scaffold": "Idle scaffold", "dc": "Unchanged DC equivalent"}
NYC_BOUNDS = (-74.30, 40.54, -73.48, 41.10)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def xy(lon, lat):
    x, y = PROJ.transform(lon, lat)
    return np.asarray(x) / 1000, np.asarray(y) / 1000


def coordinates(buses):
    parents = pd.read_csv(ROOT / "output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv").set_index("idx")
    result = buses.copy().set_index("model_bus")
    result["latitude_deg"] = np.nan
    result["longitude_deg"] = np.nan
    result["coordinate_basis"] = ""
    result["coordinate_quality"] = ""
    result["coordinate_source"] = ""
    result["notes"] = ""
    for key, row in parents.iterrows():
        result.loc[key, ["latitude_deg", "longitude_deg", "coordinate_basis", "coordinate_quality", "coordinate_source"]] = [
            row.ycoord, row.xcoord, "published_NPCC_model_point", "approximate_model_geography_not_verified_station", "output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv"]
    paths = [GEO / "source_historical/historical_station_coordinates.csv",
             GEO / "source_project/project_station_coordinates.csv",
             GEO / "source_historical/original_anchor_coordinates.csv"]
    for path in paths:
        source = pd.read_csv(path, keep_default_na=False)
        require(source.model_bus.is_unique, "Duplicate coordinate identity: " + str(path))
        for row in source.to_dict("records"):
            key = int(row["model_bus"])
            require(key in result.index, "Coordinate for an unknown model bus")
            for field in ["latitude_deg", "longitude_deg", "coordinate_basis", "coordinate_quality", "notes"]:
                if field in row:
                    result.loc[key, field] = row[field]
            result.loc[key, "coordinate_source"] = row.get("source_url", row.get("source_workbook", path.relative_to(ROOT).as_posix()))
            if "coordinate_precision" in row:
                result.loc[key, "coordinate_quality"] = row["coordinate_precision"]
    result["plot_on_geographic_map"] = ~result.index.isin(PROXY_IDS)
    result["added_bus"] = result.identity_role.ne("original_parent")
    require(np.isfinite(result[["latitude_deg", "longitude_deg"]].to_numpy(float)).all(), "Incomplete coordinates")
    require(result.latitude_deg.between(37.5, 47.5).all() and result.longitude_deg.between(-87, -67.5).all(), "Point outside expected NPCC extent")
    require(result.loc[result.added_bus, "coordinate_basis"].ne("").all(), "Added bus lacks coordinate provenance")
    require(result.added_bus.sum() == 51, "Added bus count changed")
    result["map_latitude_deg"] = result.latitude_deg.astype(float)
    result["map_longitude_deg"] = result.longitude_deg.astype(float)
    result["map_anchor_policy"] = "selected_source_station_point"
    for child, host in HOST.items():
        result.loc[child, ["map_latitude_deg", "map_longitude_deg"]] = result.loc[host, ["latitude_deg", "longitude_deg"]].to_numpy()
        result.loc[child, "map_anchor_policy"] = f"shared_host_station_point_bus{host};raw_source_coordinate_preserved"
    result["projected_easting_km"], result["projected_northing_km"] = xy(result.map_longitude_deg.to_numpy(float), result.map_latitude_deg.to_numpy(float))
    result.loc[list(PROXY_IDS), ["projected_easting_km", "projected_northing_km"]] = np.nan
    result.loc[list(PROXY_IDS), "coordinate_quality"] = "unlocated_aggregate_shown_in_nongeographic_inset"
    result.reset_index().to_csv(GEO / "bus_geographic_register.csv", index=False, lineterminator="\n")
    return result, paths


def rings_path(poly):
    paths = []
    for ring in [poly.exterior, *poly.interiors]:
        values = np.asarray(ring.coords)[:, :2] / 1000
        codes = np.full(len(values), MplPath.LINETO); codes[0] = MplPath.MOVETO; codes[-1] = MplPath.CLOSEPOLY
        paths.append(MplPath(values, codes))
    return MplPath.make_compound_path(*paths)


def draw_shape(ax, geom, face, line, width):
    if geom.is_empty:
        return
    if geom.geom_type == "Polygon":
        ax.add_patch(PathPatch(rings_path(geom), facecolor=face, edgecolor=line, lw=width, zorder=0))
    elif geom.geom_type in ["LineString", "LinearRing"]:
        a = np.asarray(geom.coords) / 1000
        ax.plot(a[:, 0], a[:, 1], color=line, lw=width, zorder=1)
    elif hasattr(geom, "geoms"):
        for part in geom.geoms:
            draw_shape(ax, part, face, line, width)


def basemap(ax, bounds):
    extent = box(*bounds)
    ax.set_facecolor("#E9F0F4")
    for layer, face, line, width in [
        ("ne_10m_land", "#FAFAF5", "#AEBCC1", .55),
        ("ne_10m_lakes", "#E9F0F4", "#B8C7CC", .35),
        ("ne_10m_admin_1_states_provinces_lines", "none", "#B7C0C6", .65)]:
        data = json.loads((GEO / "basemap" / (layer + "_npcc.geojson")).read_text())
        for feature in data["features"]:
            g = shape(feature["geometry"])
            if g.intersects(extent):
                draw_shape(ax, project_geometry(g.intersection(extent), PROJ.transform, interleaved=False), face, line, width)
    x, y = xy([bounds[0], bounds[2], bounds[0], bounds[2]], [bounds[1], bounds[1], bounds[3], bounds[3]])
    ax.set_xlim(min(x), max(x)); ax.set_ylim(min(y), max(y))
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#AEBCC1"); spine.set_linewidth(.6)
    width_km = max(x) - min(x)
    scale = 100 if width_km > 600 else 25 if width_km > 120 else 10 if width_km > 45 else 5
    left = min(x) + width_km * .045; bottom = min(y) + (max(y) - min(y)) * .035
    ax.plot([left, left + scale], [bottom, bottom], color="#425264", lw=2)
    ax.text(left + scale / 2, bottom + (max(y)-min(y))*.012, f"{scale} km", ha="center", fontsize=8, color="#425264")
    center_lon=(bounds[0]+bounds[2])/2;center_lat=(bounds[1]+bounds[3])/2
    nx,ny=xy([center_lon,center_lon],[center_lat,center_lat+.05])
    delta=np.array([nx[1]-nx[0],ny[1]-ny[0]])
    delta=delta/np.linalg.norm(delta)*.065
    ax.annotate("N", xy=(.963+delta[0], .89+delta[1]), xytext=(.963,.89), xycoords="axes fraction", ha="center", fontsize=9,
                arrowprops=dict(arrowstyle="-|>", color="#425264", lw=1), color="#425264")


def label_groups(frame):
    clusters = defaultdict(list)
    for key, row in frame.iterrows():
        host = HOST.get(int(key), int(key))
        if host in frame.index:
            anchor = frame.loc[host]
        else:
            anchor = row
        tag = (round(float(anchor.map_longitude_deg), 6), round(float(anchor.map_latitude_deg), 6))
        clusters[tag].append(int(key))
    return clusters


def place_labels(ax, labels, targets, marker_points):
    """Place text boxes without overlap; geographic anchors never move.

    Search nearest free display-space positions and draw thin leader lines.
    Unlike force-based placement this finishes with an explicit collision gate.
    """
    if not labels:
        return dict(label_boxes=0, overlap_pairs=0)
    canvas=ax.figure.canvas; canvas.draw(); renderer=canvas.get_renderer()
    bounds=ax.get_window_extent(renderer)
    anchors=ax.transData.transform(np.asarray(targets))
    points=ax.transData.transform(np.asarray(marker_points))
    sizes=[]
    for lab in labels:
        bbox=lab.get_window_extent(renderer)
        sizes.append((bbox.width+9,bbox.height+9))
    placed={}
    # Multi-line station labels are the most constrained; place them first.
    order=sorted(range(len(labels)),key=lambda i:(-sizes[i][1],-anchors[i,1],anchors[i,0]))
    def available(rect):
        a,b,c,d=rect
        if a<bounds.x0+3 or b<bounds.y0+3 or c>bounds.x1-3 or d>bounds.y1-3:
            return False
        if any(min(c,r[2])-max(a,r[0])>0 and min(d,r[3])-max(b,r[1])>0 for r in placed.values()):
            return False
        return not np.any((points[:,0]>a-3)&(points[:,0]<c+3)&(points[:,1]>b-3)&(points[:,1]<d+3))
    for i in order:
        px,py=anchors[i];w,h=sizes[i];best=None
        for radius in [18,30,45,65,90,120,160,210,270,340,430,540,680,850,1100,1400]:
            candidates=[]
            for angle in np.linspace(0,2*np.pi,40,endpoint=False):
                cx,cy=px+radius*np.cos(angle),py+radius*np.sin(angle)
                rect=(cx-w/2,cy-h/2,cx+w/2,cy+h/2)
                if available(rect):
                    candidates.append(((cx-px)**2+(cy-py)**2,rect,cx,cy))
            if candidates:
                best=min(candidates,key=lambda x:x[0]);break
        if best is None:
            candidates=[]
            for cx in np.arange(bounds.x0+w/2+4,bounds.x1-w/2-3,12):
                for cy in np.arange(bounds.y0+h/2+4,bounds.y1-h/2-3,12):
                    rect=(cx-w/2,cy-h/2,cx+w/2,cy+h/2)
                    if available(rect):candidates.append(((cx-px)**2+(cy-py)**2,rect,cx,cy))
            require(bool(candidates),"Insufficient geographic figure space for nonoverlapping labels")
            best=min(candidates,key=lambda x:x[0])
        _,rect,cx,cy=best;placed[i]=rect
        position=ax.transData.inverted().transform([cx,cy])
        labels[i].set_position(position)
        labels[i].set_ha("center");labels[i].set_va("center")
        ax.annotate("",xy=targets[i],xytext=position,arrowprops=dict(arrowstyle="-",lw=.45,color="#657B89",alpha=.8),zorder=4)
    canvas.draw()
    actual=[lab.get_window_extent(canvas.get_renderer()).expanded(1.01,1.03) for lab in labels]
    collisions=int(sum(actual[i].overlaps(actual[j]) for i in range(len(actual)) for j in range(i)))
    require(collisions==0,"Residual geographic label collision")
    return dict(label_boxes=len(labels),overlap_pairs=collisions,algorithm="nearest_free_display_box_with_fixed_geographic_anchor")


def draw_map(ax, registry, edges, selected, bounds, label_ids, fontsize=9):
    basemap(ax, bounds)
    shown = registry.loc[sorted(selected)].copy()
    shown = shown[shown.plot_on_geographic_map & shown.longitude_deg.between(bounds[0], bounds[2]) & shown.latitude_deg.between(bounds[1], bounds[3])]
    # Only endpoint coordinates define the connections; no polyline route is fabricated.
    groups=grouped_edges(edges,set(shown.index))
    for (a, b, category), records in groups.items():
        ra, rb = registry.loc[a], registry.loc[b]
        lw = .6 if category == "retained" else 1.25
        style = "--" if category in ["assumed", "replaced"] else ":" if category == "scaffold" else "-"
        gid="branch-"+"-".join(r["branch_key"] for r in records)
        coincident=category=="replaced" and any((a,b,c) in groups for c in ["source","assumed","retained"])
        if coincident:
            # Separate overlapping categories without moving either endpoint.
            # The arc is display-only, not an inferred transmission route.
            ax.add_patch(FancyArrowPatch((ra.projected_easting_km,ra.projected_northing_km),
                (rb.projected_easting_km,rb.projected_northing_km),connectionstyle="arc3,rad=0.075",
                arrowstyle="-",shrinkA=0,shrinkB=0,lw=1.4,linestyle="--",color=COLORS[category],zorder=3,gid=gid))
        else:
            ax.plot([ra.projected_easting_km, rb.projected_easting_km], [ra.projected_northing_km, rb.projected_northing_km],
                color=COLORS[category], lw=lw, ls=style, alpha=.55 if category=="retained" else .85, zorder=2,gid=gid)
    for added, marker, color in [(False, "o", "#87929F"), (True, "s", "#226AA5")]:
        d = shown[shown.added_bus.eq(added) & ~shown.index.isin([20003])]
        ax.scatter(d.projected_easting_km, d.projected_northing_km, s=24 if added else 17, marker=marker,
                   color=color, edgecolors="white", linewidths=.4, zorder=5)
    if 20003 in shown.index:
        dover=shown.loc[20003]
        ax.scatter([dover.projected_easting_km],[dover.projected_northing_km],s=36,marker="D",facecolors="white",edgecolors="#226AA5",linewidths=1.1,zorder=6)
    wanted = shown.loc[shown.index.intersection(list(label_ids))]
    labels, targets, memberships = [], [], []
    for (lon, lat), ids in label_groups(wanted).items():
        x, y = xy(lon, lat)
        lines = []
        for key in ids:
            row = registry.loc[key]
            name = re.sub(r" (345|138|69)$", "", str(row.model_name))
            if key==20003: name += " ≈"
            if key==20004: name += " [idle]"
            if key==80: name += " †"
            lines.append(f"{name} · {row.base_kv:g} kV · #{key}")
        text = "\n".join(lines)
        added = registry.loc[ids].added_bus.any()
        lab = ax.text(x, y, text, fontsize=fontsize, color="#234866" if added else "#526170", zorder=9,
            ha="center",va="center",
            bbox=dict(boxstyle="round,pad=0.20", fc="white", ec="#A9C7DB" if added else "#CCD1D6", lw=.45, alpha=.94),
            gid="label-buses-" + "-".join(map(str, ids)))
        labels.append(lab); targets.append((float(x), float(y))); memberships.append(ids)
    placement=place_labels(ax,labels,targets,shown[["projected_easting_km","projected_northing_km"]].to_numpy())
    return dict(geographic_bus_ids=list(map(int, shown.index)), labeled_bus_ids=[v for ids in memberships for v in ids],
                label_groups=memberships, point_coordinates_not_displaced=True,label_placement=placement)


def proxy_panel(ax, registry, edges):
    chosen = edges[edges.from_bus.isin(PROXY_IDS) | edges.to_bus.isin(PROXY_IDS)]
    groups = grouped_edges(chosen, set(chosen.from_bus) | set(chosen.to_bus))
    ids = sorted(set(chosen.from_bus) | set(chosen.to_bus))
    graph = nx.Graph(); graph.add_nodes_from(ids)
    graph.add_edges_from((a,b) for a,b,c in groups)
    positions = nx.kamada_kawai_layout(graph)
    for (a,b,category), records in groups.items():
        ax.plot([positions[a][0], positions[b][0]], [positions[a][1], positions[b][1]],
            color=COLORS[category], ls="--" if category in ["replaced","assumed"] else "-", lw=1.15, zorder=1)
    for key in ids:
        row = registry.loc[key]; x,y=positions[key]
        name = re.sub(r" (345|138|69)$", "", str(row.model_name))
        ax.text(x, y, f"{name}\n#{key} · {row.base_kv:g} kV", fontsize=7.8, ha="center", va="center", zorder=3,
                bbox=dict(boxstyle="round,pad=.3", fc="#DFEAF4" if row.added_bus else "#F2F4F6", ec="#9CAABA", lw=.5))
    ax.set_xlim(-1.32,1.32); ax.set_ylim(-1.30,1.30); ax.axis("off")
    ax.set_title("Unlocated aggregate connections — schematic inset", fontsize=11, loc="left", pad=7)
    return dict(proxy_ids=sorted(PROXY_IDS), inset_bus_ids=ids, individual_branch_records=len(chosen),
                meaning="Only buses78/79/82 lack geographic site aliases; other inset endpoints also appear at true coordinates on maps")


def header(fig, title, subtitle):
    fig.suptitle(title, x=.035, y=.975, ha="left", fontsize=20, color="#223246")
    fig.text(.035,.949,subtitle,fontsize=10.5,color="#44566A")
    handles = [Line2D([0],[0],marker="s",color="none",markerfacecolor="#226AA5",markeredgecolor="white",markersize=7,label="Added bus"),
               Line2D([0],[0],marker="o",color="none",markerfacecolor="#87929F",markeredgecolor="white",markersize=6,label="Original bus")]
    for category in ["source", "assumed", "replaced", "retained", "dc"]:
        handles.append(Line2D([0],[0],color=COLORS[category],lw=1.5,ls="--" if category in ["assumed","replaced"] else "-",label=NAMES[category]))
    fig.legend(handles=handles,loc="upper left",bbox_to_anchor=(.031,.94),ncol=4,frameon=False,fontsize=9)
    fig.text(.035,.031,"Markers use station anchors; labels use leader lines. Curves separate coincident branch categories. Lines show model connections, not physical routes.",fontsize=9,color="#44566A")
    fig.text(.035,.019,"≈ Dover: address-level approximation. † Northport: station-level anchor; model138kV / source115kV. Other original NPCC points are approximate model locations.",fontsize=8.5,color="#627487")
    fig.text(.035,.007,"Sources: PERFORM GIS, municipal/Census/owner data, © OpenStreetMap contributors (ODbL1.0). Basemap: Natural Earth (public domain).",fontsize=8.5,color="#627487")


def save(fig, name):
    for fmt in ["png","svg","pdf"]:
        fig.savefig(OUT/(name+"."+fmt),dpi=165,facecolor="white",metadata={"Creator":"NPCC reproducible geographic diagram"} if fmt=="pdf" else None)
    plt.close(fig)


def export_geojson(registry, edges):
    nodes=[]
    for key,row in registry.iterrows():
        geometry=dict(type="Point",coordinates=[float(row.map_longitude_deg),float(row.map_latitude_deg)]) if row.plot_on_geographic_map else None
        props=dict(model_bus=int(key),name=str(row.model_name),base_kv=float(row.base_kv),added=bool(row.added_bus),
            accounting_zone=str(row.accounting_zone),coordinate_basis=str(row.coordinate_basis),coordinate_quality=str(row.coordinate_quality),
            source=str(row.coordinate_source),map_anchor_policy=str(row.map_anchor_policy),
            preserved_source_latitude=float(row.latitude_deg),preserved_source_longitude=float(row.longitude_deg))
        nodes.append(dict(type="Feature",geometry=geometry,properties=props))
    connections=[]
    for row in edges.to_dict("records"):
        a,b=registry.loc[row["from_bus"]],registry.loc[row["to_bus"]]
        geometry=None
        if a.plot_on_geographic_map and b.plot_on_geographic_map:
            endpoints=[[float(a.map_longitude_deg),float(a.map_latitude_deg)],[float(b.map_longitude_deg),float(b.map_latitude_deg)]]
            geometry=dict(type="Point",coordinates=endpoints[0]) if endpoints[0]==endpoints[1] else dict(type="LineString",coordinates=endpoints)
        row.update(geometry_is_physical_line_route=False,unlocated_endpoint=geometry is None,
                   co_located_endpoints=bool(geometry and geometry["type"]=="Point"))
        connections.append(dict(type="Feature",geometry=geometry,properties=row))
    for name,features in [("geographic_nodes",nodes),("geographic_connections",connections)]:
        (GEO/(name+".geojson")).write_text(json.dumps(dict(type="FeatureCollection",features=features),indent=2)+"\n",encoding="utf-8",newline="\n")


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    buses, edges, counts = collect()
    registry, coordinate_inputs = coordinates(buses)
    export_geojson(registry,edges)
    added = set(registry.index[registry.added_bus])
    changed = edges[edges.category.isin(["source","assumed","scaffold","replaced"])]
    focus = added | set(changed.from_bus) | set(changed.to_bus)
    frame=registry.loc[sorted(focus)]
    in_nyc=set(frame.index[frame.longitude_deg.between(NYC_BOUNDS[0],NYC_BOUNDS[2]) & frame.latitude_deg.between(NYC_BOUNDS[1],NYC_BOUNDS[3])]) - PROXY_IDS
    plt.rcParams.update({"font.family":"DejaVu Sans","svg.fonttype":"none","pdf.fonttype":42})
    fig=plt.figure(figsize=(23,16));gs=fig.add_gridspec(2,2,left=.035,right=.975,bottom=.055,top=.875,width_ratios=[1.05,1],height_ratios=[.74,.26],wspace=.12,hspace=.16)
    main=fig.add_subplot(gs[:,0]);detail=fig.add_subplot(gs[0,1]);inset=fig.add_subplot(gs[1,1])
    header(fig,"Geographic Downstate refinement — all 51 added buses", "Year-end2025 core · geographic station points preserved · names, model bus IDs and nominal kV")
    main.set_title("Regional context: Hudson Valley, Connecticut and Long Island",fontsize=12,loc="left")
    detail.set_title("NYC / Westchester / western Long Island — enlarged",fontsize=12,loc="left")
    overall=draw_map(main,registry,edges,focus,(-74.45,40.48,-71.90,42.72),focus-in_nyc,10)
    zoom=draw_map(detail,registry,edges,focus,NYC_BOUNDS,in_nyc,8.6)
    x,y=xy([NYC_BOUNDS[0],NYC_BOUNDS[2]],[NYC_BOUNDS[1],NYC_BOUNDS[3]])
    main.add_patch(Rectangle((min(x),min(y)),abs(x[1]-x[0]),abs(y[1]-y[0]),fill=False,ec="#687C8E",lw=1,ls=":"))
    main.text(min(x),max(y)+3,"Enlarged at right",fontsize=9,color="#44566A")
    proxy=proxy_panel(inset,registry,edges)
    require(added <= set(overall["labeled_bus_ids"]) | set(zoom["labeled_bus_ids"]),"Atlas omits an added bus label")
    save(fig,"geographic_downstate_atlas")
    fig,ax=plt.subplots(figsize=(17,14));fig.subplots_adjust(left=.035,right=.97,bottom=.06,top=.865)
    header(fig,"Geographic NYC and western Long Island detail","All positions use source station points; co-located voltage-level buses share a label group")
    city=draw_map(ax,registry,edges,focus,NYC_BOUNDS,in_nyc,10.3)
    save(fig,"geographic_nyc_detail")
    fig=plt.figure(figsize=(28,19));ax=fig.add_axes([.035,.06,.78,.80]);pin=fig.add_axes([.835,.10,.155,.30])
    header(fig,"Full NPCC geographic context with 51 highlighted additions","All140 original buses retained · original model coordinates are approximate except eight source-backed anchors · added-bus labels are in the Downstate atlas")
    full=draw_map(ax,registry,edges,set(registry.index),(-86.3,38.4,-68.5,47.0),set(registry.index)-added,8.0)
    full_proxy=proxy_panel(pin,registry,edges)
    save(fig,"geographic_full_npcc")
    sources=[BASE/"network/network_cases.mat",BASE/"network/bus_register.csv",BASE/"network/branch_register.csv",
             ROOT/"output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv",*coordinate_inputs,GEO/"basemap/basemap_receipt.json",Path(__file__)]
    receipt=dict(passed=True,state="refined_2025",total_buses=191,added_buses=51,added_buses_geographically_located=51,
        geographic_bus_records=188,nongeographic_original_proxy_buses=sorted(PROXY_IDS),original_model_coordinate_points_approximate=129,
        original_source_backed_station_anchors=8,source_crs_interpretation="WGS84 longitude/latitude; historical workbook datum not explicitly declared",
        projected_crs=CRS_TEXT,branch_lines_are_actual_routes=False,labels_moved_station_anchors_not_displaced=True,
        PAR_display_policy="shared_host_station_point;raw_source_points_preserved",branch_counts=counts,
        replaced_branch_display_separation="PARENT88/PARENT91 curved slightly to expose inactive red paths beneath coextensive source circuits;endpoints unchanged",
        atlas_regional=overall,atlas_city=zoom,proxy_inset=proxy,city_detail=city,full_npcc=full,
        inputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sources],
        outputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sorted(OUT.glob("*")) if p.suffix in [".png",".svg",".pdf"]])
    (GEO/"geographic_validation.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({k:receipt[k] for k in ["passed","added_buses_geographically_located","geographic_bus_records","nongeographic_original_proxy_buses"]},indent=2))


if __name__=="__main__":
    build()
