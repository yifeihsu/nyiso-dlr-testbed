# Small-bus Downstate transmission alternative

**Completed 2026-10-11.** This is the preferred smaller DC research case for
the requested scope: **eight added buses**, instead of 51. It retains all
140 original NPCC buses, including all **46 original New York buses**, and
adds eight critical 345-kV transmission stations. The result is **148 buses
overall: 54 in New York and 94 original external buses**.

The 43 other additions are represented through explicitly documented DC
equivalent connections. The earlier 191-bus model is preserved as the detailed
source/reference; none of its artifacts or the frozen 2025 fleet/dispatch was
overwritten. This change reduces model size while preserving the tested DC
response. It is not a new fit to measured interface flows.

Use [npcc_nygrid_2025_slim_dc.m](System%20Matpower%20Format/npcc_nygrid_2025_slim_dc.m)
for the small-bus model. The [workflow README](scripts/nygrid_2025_slim/README.md)
contains complete commands and the output contract.

The [updated geographic atlas](output/nygrid_2025_slim/geography/README.md)
shows the eight retained additions and the equivalent branch network. The
[interactive offline map](output/nygrid_2025_slim/interactive/network_map.html)
adds pan/zoom, bus and branch details, and separate layer controls. Its
[verification record](output/nygrid_2025_slim/interactive/README.md) distinguishes
passed DOM behavior checks from unverified browser visual rendering.

## Eight retained additions

Every retained addition is **345 kV**. Stations already present in NPCC,
including Pleasant Valley, Millwood, Buchanan, Ramapo and Goethals, remain at
their original bus IDs.

| Added station | Model bus | Reason to retain it |
|---|---:|---|
| East Fishkill | 10858 | Separates the parallel Pleasant Valley–East Fishkill and East Fishkill–Wood Street circuits. |
| Wood Street | 10902 | Retains the junction among Pleasant Valley, East Fishkill and Millwood. |
| Ladentown | 10774 | Preserves the distinct Ramapo–Ladentown and Ladentown–Buchanan sections. |
| Dunwoodie | 10593 | Keeps a named Westchester bulk receiving port. |
| East Garden City | 10589 | Keeps a named Long Island bulk receiving port. |
| Gowanus | 11129 | Retains a Brooklyn receiving port and its connection to the Goethals area. |
| Rainey | 11130 | Keeps the Queens receiving port distinct from Gowanus. |
| Cricket Valley | 20001 | Preserves the F83/F84 junction toward Pleasant Valley and the New England corridor. |

East Fishkill, Ladentown and Cricket Valley have only two distinct neighbors
in this selected network, but retain useful named line sections and parallel
circuits. They were kept for the transmission-path interpretation, not because
an interface error improved. Full rationale is in the
[station register](output/nygrid_2025_slim/network/retained_station_rationale.csv).

The retained eight buses have zero injection in the delivered baseline.
Generator landings were not changed simply because their nearby station is
now explicit. The 2025 per-device output and bounds remain frozen.

## Branch network and reduction method

| Branch class | Year-end active records |
|---|---:|
| Retained original NPCC branches | 216 |
| Direct historical PERFORM circuits, unchanged | 14 |
| Retained previously declared assumed connections | 5 |
| Passive DC equivalents of omitted station detail | 30 |
| **Total active branches** | **265** |

All 225 original branch records remain identifiable. Nine predecessor rows
remain inactive under the already registered replacements, making **274 total
branch records**. Compared with the original 225-active-branch network, this
retains 49 added source/assumed/equivalent connections and replaces nine old
aggregate paths. The **30 equivalents are not 30 new physical circuits**.

The eliminated set contains **only 43 added buses**. Every original bus,
generator terminal and DC endpoint remains. Under the primary fixed-location
dispatch, those 43 buses have zero P/Q load, fixed shunt injection, generator
injection and DC injection. Component-wise DC elimination therefore preserves
the retained nodal response, including fixed phase-shifter terms. All direct
retained-endpoint circuits are kept separately before eliminating the remaining
network, preventing double counting.

The equivalent network is passive, retains structurally required weak
couplings without a magnitude cutoff, and includes phase-affine recovery
operators. Its R/B/rating zeros are explicit DC placeholders. They do not
assert lossless physical conductors, known ampacities or an AC-equivalent model.
The [branch register](output/nygrid_2025_slim/network/branch_register.csv) and
[equivalent contribution register](output/nygrid_2025_slim/network/equivalent_contribution_register.csv)
separate direct source circuits, earlier assumptions and derived equivalents.

The original 191-bus model's optional asset-remapping diagnostic is excluded:
it places 11 generator rows and 23 nonzero load-allocation rows at eliminated
buses. Those injections cannot be discarded. This alternative uses the
primary frozen original-bus injection contract; any future asset remapping
would require a corresponding injection projection or retaining its terminals.

## Operating states and interface comparisons

The small case preserves the dated RCC/Dover state schedule and provides a
separate fixed year-end counterfactual. The construction also retains a
historical-detail control. Active branch counts are 257 in that control, 258
before May and from May21, and 265 from May30 and at year-end. The equivalent
parameters change with the inherited project state; the underlying source
assumptions were not refitted.

Recovered detailed angles and branch flows agree with the 191-bus reference
throughout both annual replays. The seven interface functionals also agree to
within **3.0e-10 model MW**, so their prediction errors remain the same:

| Interface proxy, dated replay | Original 140-bus WAPE | Detailed 191-bus WAPE | Small 148-bus WAPE |
|---|---:|---:|---:|
| UpNY–ConEd | 6.47% | 6.47% | 6.47% |
| Sprain/Dunwoodie South | 8.87% | 8.84% | 8.84% |
| Central East | 27.27% | 17.67% | 17.67% |

The [complete comparison](output/nygrid_2025_slim/comparison/interface_summary.csv)
includes all seven interfaces and both topology variants. The larger western
and Moses South errors are inherited; this reduction does not fix them.
The existing scale remains **gamma = 0.30012075175285535**.

**Dunwoodie requires the saved recovery operator.** Eliminating internal buses
changes the interpretation of a simple reduced-network zone-crossing sum.
The native raw-case integer map includes only the six functionals proven exact;
Dunwoodie is omitted there. The hourly loader removes native `if.map` and
provides one accessor for all seven comparable functionals:

```matlab
addpath('System Matpower Format');
mpc = npcc_nygrid_2025_slim_dc(1);
[r, success] = rundcpf(mpc, mpoption('verbose', 0, 'out.all', 0));
assert(success);
interfaces = npcc_nygrid_2025_slim_interfaces(r);
```

## Validation and usable scope

Independent validation covers all five topology states and **17,326 annual
variant-hours**: two variants using the same 8,663 qualified hours. The same
97 source-gap hours are rejected in each. It verifies original identities,
per-unit PG/bounds, gross original-bus P/Q, signed DC schedules, phase terms,
all recovery matrices, and all 35 published comparison rows. Maximum slim
nodal residual is **3.44e-11 model MW**; independent branch disagreement is
**2.23e-11 model MW**. Recovery of the detailed system also satisfies its nodal
equations.

**40 fresh MATPOWER snapshots** cover seasons, peak/valley, DST and topology
state boundaries. Maximum branch discrepancy is 3.14e-11 model MW; generation
change is 2.97e-11 model MW. The loader rejects missing-source hours, and the
interface accessor rejects unsolved cases. All **16 focused tests** pass, including nonunity
taps, nonzero phase shifts, weak-edge preservation, arbitrary retained
injections, nonzero-interior rejection, double counting, and incorrect local
interface definitions. A clean construction rebuild matches every MAT payload.

Evidence: [construction audit](output/nygrid_2025_slim/validation/construction_validation.json),
[annual audit](output/nygrid_2025_slim/validation/annual_validation.json),
[MATPOWER checks](output/nygrid_2025_slim/validation/matlab_validation.json),
[focused tests](output/nygrid_2025_slim/validation/focused_tests.json),
[rebuild](output/nygrid_2025_slim/network/rebuild_verification.json).

This is the smaller **DC research alternative**. It preserves the declared
detailed model's response, not a certified as-built 2025 grid. Physical
flowgate definitions, AC feasibility, project parameters/PAR schedules and
thermal/DLR qualification remain unverified. The 14 direct historical circuits
retain their identities for later conductor/thermal qualification; the 30
equivalent branches cannot directly receive a conductor DLR model.

[Simplified network diagram: SVG](output/nygrid_2025_slim/diagrams/eight_bus_network.svg)
· [PDF](output/nygrid_2025_slim/diagrams/eight_bus_network.pdf)
· [PNG](output/nygrid_2025_slim/diagrams/eight_bus_network.png)
