# Labeled full-NPCC and Downstate network schematics

The diagrams use the saved **year-end 2025 core** (`refined_2025_case`):
191 buses, including all 140 originals and 51 additions. They show 336 active
AC branch records, plus the nine inactive original branches that were replaced.
The full view also includes the four unchanged scheduled DC equivalents.
Positions and line lengths are schematic, not geographic.

| View | Vector SVG | PDF | PNG |
|---|---|---|---|
| All 51 additions and nearby original buses | [SVG](downstate_changes.svg) | [PDF](downstate_changes.pdf) | [PNG](downstate_changes.png) |
| Full 191-bus NPCC | [SVG](full_npcc.svg) | [PDF](full_npcc.pdf) | [PNG](full_npcc.png) |
| Hudson Valley / Westchester | [SVG](hudson_westchester.svg) | [PDF](hudson_westchester.pdf) | [PNG](hudson_westchester.png) |
| New York City receiving network | [SVG](new_york_city.svg) | [PDF](new_york_city.pdf) | [PNG](new_york_city.png) |
| Long Island and neighboring ties | [SVG](long_island.svg) | [PDF](long_island.pdf) | [PNG](long_island.png) |

Use SVG or PDF to zoom into labels. Every bus label includes its saved name,
model bus number and nominal voltage. Regional crops overlap and include
neighboring context; their bus counts must not be added together.

- **Blue square boxes:** added model buses. Gray rounded boxes are retained
  original buses.
- **Blue solid lines:** 97 added historical source circuits.
- **Gold dashed lines:** 22 connections with assumed electrical parameters.
- **Red dashed lines:** nine replaced original branches, now inactive. Labels
  `P32`, `P87`–`P89`, and `P91`–`P95` identify their original branch rows.
- **Gray lines:** retained original branches. One gray dotted line is the
  nonphysical idle connection for Knickerbocker.
- **Purple lines:** unchanged scheduled DC equivalents.

`xN` bundles N parallel model branches for readability. It does not combine
their electrical parameters or change the case. The complete individual
branch keys, model rows, endpoints and categories are in
[diagram_branches.csv](diagram_branches.csv); complete bus names and voltages
are in [diagram_buses.csv](diagram_buses.csv). SVG tooltips retain individual
branch identities within each bundle.

Knickerbocker is explicitly marked as an **idle placeholder**. Optional NYES
paths are excluded. Dover is active in this year-end view; earlier dated
variants differ. UNKNOWN/TAP labels are retained because their physical
station names remain unresolved. Original CE UG, RAV A-3 and AK-3 are marked
as inherited aggregate proxies. Cross-voltage assumed connections do not
establish physical transformer designs.

The 51 added model buses expose historical detail and project/plant terminals;
they are not a count of substations newly built in 2025. Replaced aggregate
branches can be represented by a shared detailed mesh, so a red dashed branch
does not necessarily correspond to one uniquely identifiable new physical
route.

Reproduce from the repository root with the existing Python runtime and
Graphviz on PATH:

```powershell
& '.\tmp\nygrid_2025_inputs_runtime_20261010\Scripts\python.exe' scripts/nygrid_2025_downstate/build_network_diagrams.py
```

Graphviz DOT sources and fixed-coordinate layouts accompany the figures.
[diagram_validation.json](diagram_validation.json) records source hashes,
per-view node sets, branch counts and renderer version. The diagram build does
not alter network parameters, bus/branch identities or operating results.
