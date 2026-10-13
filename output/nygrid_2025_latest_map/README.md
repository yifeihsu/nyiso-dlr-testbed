# Current AC model interactive map

[network_map.html](network_map.html) is the updated map. It contains its runtime,
basemap and data in one HTML file, with no external scripts, tiles or data
requests. The current model source is repository commit
`39402c2057b75670fe0591ab7f1f2ed304adec56`.

The default view is the 148 retained AC buses at hour 8508, 21 December 2025
16:00 UTC. It labels all eleven New York accounting zones and the seven modeled
interfaces. At narrow widths the map uses A–K letters and the legend supplies
the full zone names.

## Controls

- Select any of the 8,760 model hours using the UTC date/time, hour index,
  slider, or previous/next buttons. The network switches between its four
  effective-date states.
- Choose **Retained AC 148** for the current complex-admittance topology or
  **Detailed corridors** for the original parent records. Selecting an
  interface opens the detailed view and highlights its frozen members.
- Choose **Model MW** or **Public scale MW ÷ gamma**. This changes display units
  only. Values use full source precision; visible labels are rounded.
- Select a zone to see gross boundary demand, delivered demand, assigned AC
  loss and net native generation. Native generation excludes all 28 external
  equivalents, including HQ, and preserves negative pumping values.
- Select a bus, corridor or prescribed transfer to inspect its identity and
  current metadata. Proxies 78, 79 and 82 remain unlocated. Numerical section
  buses do not receive geographic positions. Dover auxiliary 21001 is offered
  only after its cutover and uses a declared shared display anchor.
- Pan the map background, use wheel/zoom controls, or focus the map and use
  arrow keys, plus/minus and Home. Labels and layer toggles are independent.

## Flow and geometry conventions

The seven interfaces are DYSINGER EAST, WEST CENTRAL, TOTAL EAST, MOSES SOUTH,
CENTRAL EAST - VC, UPNY CONED and SPR/DUN-SOUTH. Their default values sum each
frozen member coefficient times P at the original corridor from-terminal.
Negative totals reverse the schematic positive-direction arrow. The map does
not substitute older unexpanded interface indices.

The annual data retains all 8,760 clock positions: 8,651 source-qualified,
8,170 equation/loss-qualified, 109 source-excluded and 481 failed attempted
solutions. Interface, delivered-demand and loss values are unavailable outside
the qualified solutions. Known source inputs can remain visible on a
source-qualified failed hour. A source-excluded hour has no supplied model
power values. Gaps in the chart remain gaps.

Zone labels use current model membership and schematic location anchors;
official zone polygons are not implied. Network paths show adjacency, not
surveyed routes. Reduced AC couplings have no individual conductor flow or
rating. Parent R/X/B values sum detailed sections, with separate bus shunts and
reactors. Cable-evidence conflicts retain qualified display metadata.

These are the model's diagnostic cuts. Physical NYISO meter membership remains
uncertified. Public-scale model power is Model MW divided by
`gamma = 0.30012075175285535`; amperes are never gamma-scaled. No observed P32
series is displayed; its preserved numeric-as-MW interpretation remains
qualified in the source metadata. Equation and operating-limit gates are
separate; no saved hour passes the joint operating-limit gate.

## Validation

The canonical topology, full annual arrays and interface definitions are
embedded exactly. All 294 saved interface metric rows reproduce with zero
difference. Independent interface reconstruction, geography/terminal mapping,
11 JavaScript flow-math checks and 28 behavioral DOM checks pass.

Actual browser testing also checks pointer selection, units, masks, dated
cutovers and responsive layouts. Desktop and narrow-screen labels were visually
reviewed. Browser QA ran through a loopback preview; the Codex app browser
blocks direct file-protocol navigation. There are no external runtime requests.

The map uses saved current results. It performs no new PF, OPF or parameter
changes. Earlier maps, model deliveries and colleague archives are preserved.

## Rebuild

Run the data/geography builders only when their corresponding sources change.
For UI edits with frozen canonical data:

```text
python scripts/nygrid_2025_latest_map/build_network_map.py
node scripts/nygrid_2025_latest_map/test_interactive_map.cjs --final
node scripts/nygrid_2025_latest_map/audit_ui_flow_math.js
```

The test suite uses the pinned LinkeDOM test dependency from the established
task runtime. `build_receipt.json` records exact source/output hashes.
`DELIVERY_MANIFEST.json` seals the final artifact and its validation evidence.
