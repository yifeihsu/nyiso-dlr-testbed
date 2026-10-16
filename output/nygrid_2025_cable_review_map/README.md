# NYgrid cable review map

Open network_map.html directly in a browser. The map is a self-contained
offline file with the current Moses-repair model and all 8,760 annual clock
positions. It starts in Downstate / Detailed corridors with review highlights
enabled and the 19 high-priority model parent records selected.

Use the sidebar to select a flagged corridor, see the reason and sources, and
inspect its current parameters. Switch from High-priority flags to All review
flags for the full set of 44 model parent records. Category checkboxes and the
Review highlights toggle control the display. The existing hour, unit, zone,
interface and network controls remain available.

## Highlight meanings

| Color / category | Records in the full review set | Meaning |
| --- | ---: | --- |
| Red / Classification conflict | 4 | Documented cable-corridor evidence conflicts with a retained overhead parameter template |
| Amber / Parameter review | 18 | Charging or cable-construction assumptions need verification; installed identity is recorded separately |
| Magenta / Cable identity uncertain | 22 | Cable-compatible source equivalents lack a complete installed-asset identification |

The high-priority set contains the four conflicts, twelve large gross-charging
substitutions and three documented Reliable Clean City cable feeders.
The four conflicts are parent 300 (Y50), parents 309/310 (Y49) and parent 386
(a synthetic Goethals–Gowanus attachment). The two Y49 model rows do not establish
two physical Y49 circuits.

These are research-model review flags, not confirmed physical cable faults.
All 44 candidates are already excluded from the current overhead-conductor
screen. This update does not change electrical parameters, operating inputs,
annual results, the sealed prior map or the current-model pointer.

Gross branch charging B excludes separate bus reactors. The twelve large
substitutions have declared nominal 75% compensation; their 15.59–20.12
gross-B ratios are not net reactive-power multipliers or a proven cause of
voltage error.

## Dates and network mode

The selected hour controls whether a project is active. There are 42 active
review records before May 21, 43 from May 21, and 44 from May 30 onward.
High-priority active counts are 17, 18 and 19 respectively. Enabling Inactive
shows the dated inactive records explicitly.

Flags belong to detailed parent corridors. Retained AC mode hides them and
offers a button to return to Detailed corridors. Reduced admittance couplings
are not labeled as installed cables. Map connections are schematic adjacency,
not surveyed underground or submarine routes.

## Evidence and validation

- cable_review.csv and cable_review.json contain the full flagged list.
- cable_audit_recommendations.json and .md preserve classification evidence,
  independent runtime checks, parameter assumptions and source fingerprints.
- build_receipt.json records the frozen base-map/model sources.
- interaction_validation.json records actual inline-code DOM-event tests.
- validation.json confirms that the complete annual, geography and interface
  payloads match the frozen current map.
- qa/ contains static SVG-derived previews, not native browser screenshots.

The browser tool rejected the local file protocol, so native browser layout
and native pointer hit testing were not verified. Code-level interaction tests
and native SVG previews are identified separately; no alternate browser or
local-server workaround was used.

## Rebuild from the repository root

~~~powershell
python scripts/nygrid_2025_cable_review_map/build_review_map.py
node scripts/nygrid_2025_cable_review_map/test_interactive_map.cjs --final
node scripts/nygrid_2025_cable_review_map/render_static_preview.cjs <path-to-installed-@napi-rs/canvas>
python scripts/nygrid_2025_cable_review_map/audit_review_map.py
~~~

The interaction suite reuses the existing pinned LinkeDOM runtime under
tmp/nygrid_2025_slim_map_test/node_modules. It discloses its layout/IDL stubs
and does not substitute the application code.
