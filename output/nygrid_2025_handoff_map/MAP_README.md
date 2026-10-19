# Interactive map included with this model

Open [network_map.html](network_map.html) in a modern browser. It is one
self-contained HTML file; no external scripts, tiles or data requests are
needed. MATLAB is required for the electrical runtime, not for viewing the map.

The default point is hour 8508, 21 December 2025 at 16:00 UTC. Use the date/time,
index or slider for any of the 8,760 model hours. The network follows the four
dated topology states. The 148 retained AC view and detailed parent-corridor
view are two representations of the same current model.

All eleven New York accounting zones are labeled. Narrow screens use A-K
letters with full names in the legend. Select a zone for its gross boundary
demand, delivered demand, assigned AC loss and net native generation. Native
generation excludes all 28 external equivalents, including HQ.

The seven interface labels use the frozen signed corridor from-terminal
definition. Select a label to highlight its member corridors. Negative totals
reverse the schematic arrow. Public-scale model MW equals model MW divided by
gamma = 0.30012075175285535. The map does not rescale amperes.

There are 8,170 equation/loss-qualified saved hours. Computed interface,
delivered-load and loss values remain unavailable outside that cohort; known
source inputs can remain available on source-qualified failed hours. A source-
excluded hour has no supplied model power values. Operating-limit qualification
is separate and remains false in the saved annual results.

Zone anchors and connection paths are schematic model geography, not official
zone polygons or surveyed routes. The seven cuts are model diagnostics with
uncertified physical NYISO meter membership. Reduced AC couplings have no
individual conductor flow or rating. Proxies 78, 79 and 82 remain unlocated.

The map and electrical input files are included in the package checksum table.
Run the root `verify_package.py --root .` to verify both. The source and prior
browser/DOM validation identities are in `verification/MAP_PROVENANCE.json`.
Browser QA used a loopback preview; the Codex app browser restricts direct file-
protocol navigation. The HTML itself has no external runtime dependencies.
