"""Build a portable offline interactive map of the148bus model.

Geography is projected with the same sourced LCC coordinates as the static
figures. Everything needed to display and interact is embedded in one HTML
file; no map tiles, external scripts, APIs or browser-local fetches are used.
"""
from pathlib import Path
import hashlib
import json
from collections import Counter, defaultdict
import numpy as np
from pyproj import Transformer, CRS
from shapely.geometry import shape
from shapely import transform as project_geometry

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/"output/nygrid_2025_slim"
GEO=BASE/"geography"
OUT=BASE/"interactive"
BASEMAP=ROOT/"output/nygrid_2025_downstate/geography/basemap"
CRS_TEXT="+proj=lcc +lat_1=40 +lat_2=45 +lat_0=42 +lon_0=-76 +datum=WGS84 +units=m +no_defs"
PROJ=Transformer.from_crs("EPSG:4326",CRS.from_proj4(CRS_TEXT),always_xy=True)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def point(coords):
    x,y=PROJ.transform(*coords)
    return [round(float(x)/1000,6),round(-float(y)/1000,6)]


def geometry_path(g):
    def line(coords,closed=False):
        a=np.asarray(coords)[:,:2]/1000
        return "M"+"L".join(f"{x:.3f},{-y:.3f}" for x,y in a)+("Z" if closed else "")
    if g.geom_type=="Polygon":return line(g.exterior.coords,True)+"".join(line(r.coords,True) for r in g.interiors)
    if g.geom_type in ["LineString","LinearRing"]:return line(g.coords)
    if hasattr(g,"geoms"):return "".join(geometry_path(p) for p in g.geoms)
    return ""


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    node_path=GEO/"geographic_nodes.geojson";edge_path=GEO/"geographic_connections.geojson"
    raw_nodes=json.loads(node_path.read_text());raw_edges=json.loads(edge_path.read_text())
    nodes=[]
    for feature in raw_nodes["features"]:
        p=feature["properties"];g=feature["geometry"]
        coord=g["coordinates"] if g else None
        nodes.append(dict(id=int(p["model_bus"]),name=p.get("name",p.get("model_name")),kv=float(p["base_kv"]),
            added=bool(p["added"]),zone=p.get("accounting_zone",""),lon=coord[0] if coord else None,
            lat=coord[1] if coord else None,xy=point(coord) if coord else None,
            basis=p.get("coordinate_basis",""),quality=p.get("coordinate_quality",""),source=p.get("source","")))
    by_id={n["id"]:n for n in nodes};edges=[]
    for feature in raw_edges["features"]:
        p=feature["properties"]
        edges.append(dict(key=p["branch_key"],row=int(p.get("model_branch_row",0)),a=int(p["from_bus"]),b=int(p["to_bus"]),
            category=p["category"],active=bool(p["active_in_core"]),basis=p.get("parameter_basis",""),
            source_row=int(p.get("source_branch_row",0)),full191_row=int(p.get("full191_branch_row",0)),
            mapped=bool(by_id[int(p["from_bus"])]["xy"] is not None and by_id[int(p["to_bus"])]["xy"] is not None)))
    groups=defaultdict(list)
    for index,edge in enumerate(edges):groups[(*sorted([edge["a"],edge["b"]]),edge["category"])].append(index)
    bundles=[dict(a=k[0],b=k[1],category=k[2],records=v) for k,v in groups.items()]
    basemap=[];sources=[node_path,edge_path]
    for layer,kind in [("ne_10m_land","land"),("ne_10m_lakes","water"),("ne_10m_admin_1_states_provinces_lines","boundary")]:
        path=BASEMAP/(layer+"_npcc.geojson");sources.append(path)
        data=json.loads(path.read_text())
        basemap.append(dict(kind=kind,path="".join(geometry_path(project_geometry(shape(f["geometry"]),PROJ.transform,interleaved=False)) for f in data["features"])))
    counts=dict(Counter(e["category"] for e in edges))
    assert len(nodes)==148 and sum(n["added"] for n in nodes)==8
    assert sum(n["xy"] is not None for n in nodes)==145
    assert counts==dict(retained=216,source=14,assumed=5,equivalent=30,replaced=9,dc=4),counts
    assert sorted(n["id"] for n in nodes if n["xy"] is None)==[78,79,82]
    focus_ids={e["a"] for e in edges if e["category"] in ["source","assumed","equivalent","replaced"]}|{e["b"] for e in edges if e["category"] in ["source","assumed","equivalent","replaced"]}
    payload=dict(nodes=nodes,edges=edges,bundles=bundles,basemap=basemap,counts=counts,
        focusIds=sorted(focus_ids),projection=CRS_TEXT,case="refined_2025",modelYear=2025,
        geographicBusCount=145,unlocatedProxyCount=3,sourceNetworkSha256=sha(BASE/"network/network_cases.mat"))
    data=json.dumps(payload,separators=(",",":"),ensure_ascii=True).replace("<","\\u003c")
    template=Path(__file__).with_name("interactive_map_template.html")
    page=template.read_text(encoding="utf-8").replace("__NETWORK_DATA__",data)
    assert "__NETWORK_DATA__" not in page
    (OUT/"network_map.html").write_text(page,encoding="utf-8",newline="\n")
    (OUT/"map_data.json").write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8",newline="\n")
    sources += [template,Path(__file__),BASE/"network/network_cases.mat"]
    receipt=dict(passed=True,buses=148,added_buses=8,geographic_buses=145,unlocated_proxies=[78,79,82],
        individual_branch_records=len(edges),branch_counts=counts,bundles=len(bundles),
        html_bytes=(OUT/"network_map.html").stat().st_size,offline_self_contained=True,external_runtime_requests=False,
        projection=CRS_TEXT,physical_route_claim=False,
        sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in sources],
        outputs=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in [OUT/"network_map.html",OUT/"map_data.json"]])
    (OUT/"build_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({k:v for k,v in receipt.items() if k not in ["sources","outputs"]},indent=2))


if __name__=="__main__":build()
