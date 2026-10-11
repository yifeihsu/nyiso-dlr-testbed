"""Cache a pinned Natural Earth basemap and clip it to the full NPCC region."""
from pathlib import Path
import hashlib
import json
import urllib.request
from shapely.geometry import box, shape, mapping

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_downstate/geography/basemap"
CACHE = ROOT / "tmp/nygrid_2025_downstate_geography_cache"
LAYERS = ["ne_10m_land", "ne_10m_lakes", "ne_10m_admin_1_states_provinces_lines"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "NPCC-research-geographic-figure/1.0"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read()


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    receipt_path = OUT / "basemap_receipt.json"
    previous = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    revision = previous["source_git_commit"] if previous else json.loads(get(
        "https://api.github.com/repos/nvkelso/natural-earth-vector/commits/master"))["sha"]
    bounds = [-87., 37.5, -67.5, 47.5]
    extent = box(*bounds)
    entries = []
    for layer in LAYERS:
        url = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{revision}/geojson/{layer}.geojson"
        cached = CACHE / (layer + ".geojson")
        raw = cached.read_bytes() if cached.exists() else get(url)
        digest = hashlib.sha256(raw).hexdigest()
        if previous:
            expected = next(r for r in previous["layers"] if r["name"] == layer)
            assert digest == expected["download_sha256"], "Pinned basemap source changed"
        cached.write_bytes(raw)
        data = json.loads(raw)
        features = []
        null_geometries = 0
        for feature in data["features"]:
            if not feature.get("geometry"):
                null_geometries += 1
                continue
            geom = shape(feature["geometry"])
            if not geom.intersects(extent):
                continue
            clipped = geom.intersection(extent)
            if clipped.is_empty:
                continue
            properties = {k: v for k, v in feature.get("properties", {}).items()
                          if k in ["name", "name_en", "featurecla", "scalerank", "adm0_name"]}
            features.append(dict(type="Feature", properties=properties, geometry=mapping(clipped)))
        path = OUT / (layer + "_npcc.geojson")
        path.write_text(json.dumps(dict(type="FeatureCollection", features=features), separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
        entries.append(dict(name=layer, source_url=url, download_sha256=digest, downloaded_bytes=len(raw),
                            clipped_path=path.relative_to(ROOT).as_posix(), clipped_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            clipped_features=len(features), global_source_null_geometries_skipped=null_geometries))
        print(layer, len(features), path.stat().st_size, flush=True)
    result = dict(source="Natural Earth 1:10m vector data", publisher="Natural Earth / NACIS",
        source_git_commit=revision, license="public_domain", geographic_CRS="EPSG:4326", clip_bounds_lonlat=bounds,
        source_documentation="https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-land/",
        purpose="geographic_context_only_not_electrical_facility_or_route_evidence", layers=entries)
    receipt_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    build()
