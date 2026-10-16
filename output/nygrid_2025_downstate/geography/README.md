# Geographic network diagrams

These figures place the **51 added model buses** at source-backed station
locations while preserving the saved year-end 2025 electrical network. They
retain the previous color scheme for added source circuits, assumed
connections and replaced original branches. Bus labels include names, model
IDs and nominal voltage levels.

| Figure | SVG for zooming | PDF | PNG |
|---|---|---|---|
| Downstate geographic atlas, including NYC enlargement and proxy inset | [SVG](figures/geographic_downstate_atlas.svg) | [PDF](figures/geographic_downstate_atlas.pdf) | [PNG](figures/geographic_downstate_atlas.png) |
| NYC / Westchester / western Long Island detail | [SVG](figures/geographic_nyc_detail.svg) | [PDF](figures/geographic_nyc_detail.pdf) | [PNG](figures/geographic_nyc_detail.png) |
| Full NPCC geographic context | [SVG](figures/geographic_full_npcc.svg) | [PDF](figures/geographic_full_npcc.pdf) | [PNG](figures/geographic_full_npcc.png) |

The atlas labels all 51 additions across its two geographic panels. The full
NPCC overview labels original buses and highlights the additions; use the
atlas for the added-bus labels at a readable regional scale. Only text labels
are offset, with leader lines. Markers remain at the selected station anchors.

## Geographic evidence and precision

- **38 additions:** exact source-bus matches to the existing PERFORM
  `NYISO_MOD2MAP.xlsx`, `BUS SUB` worksheet. These are 30 distinct recorded GIS
  locations; voltage-level buses can share a station point. The six UNKNOWN/TAP
  names retain their source identities and coordinates. Their physical names
  remain unresolved. The worksheet does not state survey accuracy or datum;
  geographic decimal degrees are interpreted as WGS84 for display.
- **12 project/plant/PAR bus rows:** centroids of 11 named OpenStreetMap
  substation footprints, computed in UTM zone 18N and transformed to WGS84.
  Fresh Kills 138/345 share a site. PARs use their host station's common map
  point, not an invented separate yard. Raw source centroids are preserved.
- **Dover:** an explicitly approximate address point, marked **≈** and a hollow
  diamond. A [Town of Dover project notice](https://pub-doverny.escribemeetings.com/filestream.ashx?DocumentId=5604)
  identifies 2238 Route 22; the Census address match gives a street-interpolated
  position. This is not a surveyed substation centroid.
- **Eight original Downstate anchors:** buses 35, 39, 73, 74, 76, 77, 80 and 81
  use reviewed station locations for this map. Southington comes from
  [Eversource's GIS service](https://dghostingexternalmapprod.eversource.com/dghosting/rest/services/Substations/Substation_Locations/MapServer/2),
  Goethals from a named [OSM station footprint](https://www.openstreetmap.org/way/383102699),
  and the others from the source GIS workbook. Northport is marked **†**:
  the source site is associated with a 115-kV bus while this model bus remains
  138 kV; the geographic station anchor is not an electrical-terminal alias.
- **Three original aggregate proxies:** buses 78 CE UG, 79 RAV A-3 and 82 AK-3
  lack verified physical-site identities. They appear in a **nongeographic
  schematic inset**. Their old published model points remain in the data but
  are not presented as physical station positions.
- **Other original buses:** the full NPCC context retains 129 published model
  coordinates as approximate regional locations. They were not individually
  geocoded or promoted to surveyed station points by this mapping task.

No electrical bus identity, nominal kV, accounting zone, branch parameter,
status, load, generator output or DC schedule was changed. Workbook GIS zone
labels that conflict with the electrical H/I assignments were not imported.

## Reading the connections

Blue squares are added buses; gray circles are original buses. Blue lines show
historical source circuits, gold dashed lines assumed connections, and red
dashed lines replaced original branches that are inactive. Parallel model
circuits share a displayed connection. Co-located intra-station connections
collapse at the common station point; the earlier schematic retains their
separate voltage-level topology.

All nine replaced branches are included: four in the geographic panels and
five in the proxy inset. PARENT88 and PARENT91 have a small display-only curve
to distinguish their inactive red paths from active source circuits with the
same endpoints. **No displayed line or curve is an actual transmission route.**
The four scheduled DC equivalents retain their inherited model meaning.
Knickerbocker is labeled idle because optional NYES paths are excluded from
the core case, although the geographic station itself exists.

## Data and reproducibility

- [Unified geographic register](bus_geographic_register.csv): original source
  coordinates, chosen map anchors, quality flags, projected positions and
  source references.
- [Historical coordinate evidence](source_historical/historical_station_coordinates.csv)
  and [original anchor evidence](source_historical/original_anchor_coordinates.csv).
- [Project coordinate evidence](source_project/project_station_coordinates.csv),
  raw responses, footprint geometries and source receipts.
- [Geographic node GeoJSON](geographic_nodes.geojson) contains all 191 records:
  188 point geometries and three null geometries for unresolved proxies.
- [Connection GeoJSON](geographic_connections.geojson) contains the 336 active
  AC records, nine inactive replaced records and four DC equivalents. Links
  with an unlocated endpoint have null geometry; intra-station links with
  identical endpoints use point geometry. These are topological connectors.
- [Renderer checks](geographic_validation.json) and
  [independent coordinate/rendering audit](independent_geographic_validation.json).

Projection: Lambert conformal conic, central meridian 76°W, latitude of origin
42°N, standard parallels 40°N and 45°N, WGS84. Positions are calculated with
`pyproj`; labels are placed in display space with an explicit non-overlap gate.

The basemap uses clipped [Natural Earth 1:10m land](https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-land/),
lakes and state/province boundaries, pinned to Git commit
`ca96624a56bd078437bca8184e78163e5039ad19`. Natural Earth is public domain.
OpenStreetMap source geometry is **© OpenStreetMap contributors**, available
under [ODbL 1.0](https://www.openstreetmap.org/copyright). The source receipts
retain feature IDs, versions, timestamps, raw geometry hashes and attribution.

From the repository root, using the existing task runtime:

```powershell
$taskPython = '.\tmp\nygrid_2025_inputs_runtime_20261010\Scripts\python.exe'
& $taskPython scripts/nygrid_2025_downstate/build_historical_geography.py
& $taskPython scripts/nygrid_2025_downstate/geo_source_projects.py
& $taskPython scripts/nygrid_2025_downstate/prepare_geographic_basemap.py
& $taskPython scripts/nygrid_2025_downstate/build_geographic_diagrams.py
```

The renderer needs NumPy, pandas, SciPy, matplotlib, networkx, pyproj and
shapely. Source workbook extraction also uses openpyxl. Saved source receipts
and clipped basemap layers support rendering without reacquiring live data.
