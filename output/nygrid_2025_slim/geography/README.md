# Updated geographic figures for the eight-bus alternative

These figures replace the 51-addition view for the preferred **148-bus case**.
They retain all 140 original buses and exactly eight added 345-kV stations,
using an exact subset of the previously verified geographic register.

| Figure | SVG | PDF | PNG |
|---|---|---|---|
| Downstate atlas with NYC enlargement and aggregate-proxy inset | [SVG](figures/geographic_slim_atlas.svg) | [PDF](figures/geographic_slim_atlas.pdf) | [PNG](figures/geographic_slim_atlas.png) |
| NYC / Westchester / western Long Island detail | [SVG](figures/geographic_slim_nyc_detail.svg) | [PDF](figures/geographic_slim_nyc_detail.pdf) | [PNG](figures/geographic_slim_nyc_detail.png) |
| Full NPCC geographic context | [SVG](figures/geographic_slim_full_npcc.svg) | [PDF](figures/geographic_slim_full_npcc.pdf) | [PNG](figures/geographic_slim_full_npcc.png) |

The [interactive offline map](../interactive/network_map.html) uses the same
nodes, coordinates and connection classifications. See its
[instructions and verification limits](../interactive/README.md).

Blue squares are the eight additions: East Fishkill, Wood Street, Ladentown,
Dunwoodie, East Garden City, Gowanus, Rainey and Cricket Valley. Names, IDs and
nominal kV appear across the atlas's geographic panels. The 43 removed model
bus IDs do not appear in the new geographic data or labels.

Branch classes remain distinct: 216 retained originals; 14 direct historical
source circuits in blue; five declared assumed connections in gold; 30 passive
DC equivalents in purple dotted lines; nine inactive original replacements in
red; and four scheduled DC channels in teal dash-dot lines. The 30 equivalents
are not physical conductors or surveyed transmission routes.

There are **145 geographic points and three nongeographic aggregate proxies**
(78, 79 and 82). Among original buses, 129 locations remain approximate model
points and eight use reviewed station anchors. Source coordinates and their
quality flags are preserved in [bus_geographic_register.csv](bus_geographic_register.csv).
Northport remains a station-level anchor with the documented source115kV /
model138kV distinction.

The [node GeoJSON](geographic_nodes.geojson) contains 148 records, including
three null geometries. The [connection GeoJSON](geographic_connections.geojson)
contains 278 individual records: 263 located connectors and 15 with an
unlocated endpoint. Null records remain part of the model and are not silently
dropped from the inventory. Parallel records can share one displayed path.

The electrical network, generator dispatch, bounds, loads, DC schedules and
earlier 191-bus geographic files were not changed. Independent checks confirm
exact coordinate selection, all eight labels, connection classifications,
projection and rendered marker positions. Evidence:
[renderer validation](geographic_validation.json) and
[independent geographic validation](independent_geographic_validation.json).

The figures use the existing Lambert conformal conic projection and pinned
Natural Earth basemap. Sources remain PERFORM/NPCC GIS, public station data,
owner GIS and © OpenStreetMap contributors (ODbL1.0). Full coordinate sourcing
is preserved in the [detailed-reference geography documentation](../../nygrid_2025_downstate/geography/README.md).

Rebuild with the existing Python runtime:

```powershell
& '.\tmp\nygrid_2025_inputs_runtime_20261010\Scripts\python.exe' scripts/nygrid_2025_slim/build_slim_geography.py
```
