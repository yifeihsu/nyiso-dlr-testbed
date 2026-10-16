# Interactive geographic map — 148 buses, eight additions

Open **[network_map.html](network_map.html)** in a modern browser such as Edge
or Chrome. It is one self-contained offline file: no server, online tiles,
external scripts or API calls are required. The map uses the year-end 2025 core
case. Opening and interacting with it does not change model data.

The controls support:

- **Downstate / Full NPCC** framing, drag-to-pan, wheel zoom, zoom buttons and
  Fit view. The focused SVG also accepts arrow keys, +/− and Home.
- **Bus selection** by clicking a marker or choosing its name/ID from the
  dropdown. Details show nominal kV, accounting zone, coordinate provenance,
  source links and incident branch records.
- **Branch inspection**, including the individual records inside a parallel
  bundle. Details distinguish historical circuits, assumptions, DC equivalents
  and inactive replacements.
- Six independent **branch layers**: retained originals, direct historical
  source circuits, assumed connections, DC equivalents, replaced originals,
  and scheduled DC transfers.
- **Labels** for added buses, all buses as space allows, or none. Hover/focus
  details remain available even when a persistent label is omitted.
- **Clear selection**, Escape, an empty bus choice, or a background click to
  remove the highlight and restore normal edge visibility.

Blue squares identify exactly eight added 345-kV buses. The model contains
148 buses, of which **145 have geographic points**. Aggregate proxies 78, 79
and 82 are listed separately without invented geographic positions.

The complete connection inventory has **278 records**: 216 retained originals,
14 direct historical source circuits, five declared assumed connections,
30 DC equivalents, nine inactive replaced originals, and four scheduled DC
equivalents. **263 records have located endpoints; 15 involve an unlocated
proxy.** Layer counts refer to the full model. The map reports enabled mapped
and unlocated records separately, along with the number of buses in view.

Parallel circuits share a displayed line but remain separately inspectable.
Small curves separate overlapping categories. Lines and curves show model
connectivity, not physical transmission routes. DC equivalents are not
conductors and are not assigned certified ampacity or DLR ratings. Original
model locations remain approximate except the eight separately sourced
Downstate anchor updates. Coordinate details are preserved in the
[geographic register](../geography/bus_geographic_register.csv).

## Verification status

Data and source-hash checks passed, and **18 behavioral DOM tests** passed for
view controls, zoom/pan state, every layer, all eight station selections,
parallel branch inspection, proxy handling, labels, tooltip positioning logic,
keyboard activation, clearing selection, visibility-note updates and resize
logic. The tests execute the actual map JavaScript using LinkeDOM with explicit
layout stubs. [Interaction validation](interaction_validation.json).

**Actual browser visual rendering and native pointer hit testing remain
unverified.** Automatic approval review rejected starting the loopback preview
server with the reason "blocked by policy." No alternate server or browser
workaround was attempted. DOM tests are not a claim of browser visual QA.

## Rebuild

From the repository root:

```powershell
$taskPython = '.\tmp\nygrid_2025_inputs_runtime_20261010\Scripts\python.exe'
& $taskPython scripts/nygrid_2025_slim/build_slim_geography.py
& $taskPython scripts/nygrid_2025_slim/build_interactive_map.py
```

For the separate DOM behavior checks, use Node.js and the pinned test-only
dependency in the ignored task runtime:

```powershell
npm.cmd install --prefix tmp/nygrid_2025_slim_map_test --no-audit --no-fund --ignore-scripts linkedom@0.18.12
node scripts/nygrid_2025_slim/test_interactive_map.cjs
```

[build_receipt.json](build_receipt.json) pins data, basemap, template and builder
hashes. [map_data.json](map_data.json) contains the same payload embedded in the
HTML, with preprojected geographic geometry from the pinned Natural Earth
basemap and source-backed station coordinates.
