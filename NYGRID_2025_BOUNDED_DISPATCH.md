# 2025 fleet mapping and bounded DC dispatch on the modified 2019 NPCC

The requested operating-model stage is complete. All **8,663 source-qualified
2025 hours** have a capacity-bounded, balanced DC state on the preserved
**140-bus, 225-AC-branch, four-DC-link modified 2019 network**. There are no
capacity-infeasible qualified hours and no load shedding or free balancing
generator. The remaining **97 hours** retain missing-source status and NaN
solved values; the case loader rejects them.

This is a reconstruction of independent hourly operating snapshots. It uses
continuous hourly-average active-power bounds, including a zero lower bound
for native generation. It does not establish minimum-stable loading or unit
commitment, ramping, reserves, AC/reactive feasibility, physical branch thermal
feasibility, or storage energy feasibility. Internal interface observations
were not used to map the fleet or choose dispatch.

The previous [2025 operating inputs](NYGRID_2025_OPERATING_INPUTS.md), frozen
2019 results, and earlier compact models remain preserved.

## Fleet and network mapping

[The fleet register](output/nygrid_2025_dispatch/fleet/fleet_register.csv)
contains **2,245 unique plant/generator identities**: 2,243 EIA 2025 records
and two explicit retired Indian Point tombstones. Capacity belongs to unique
EIA identities. Many-to-many EPA and legacy relationships are annotations and
allocation relationships, never additional copies of capacity.

The final case contains **1,436 native records with positive admitted capacity
in at least one hour**, plus the **27 inherited external equivalents and one
HQ equivalent**, for **1,464 generator rows**. Inactive, excluded, retired and
unresolved records remain in the full inventory and audit ledgers. There are
1,429 default-eligible records and 15 separately eligible pumped-hydro records;
eight nominally eligible combined-cycle component rows have no independently
reported capability and therefore never enter the dispatch case.

Bus mapping prefers an explicit reactor/major-hydro identity, a unique legacy
electrical landing, or a unique existing plant landing. Remaining assets use
the nearest retained bus within the paper-parent zone. These are coarse
geographic proxies, not verified interconnection substations. The parent
`npcc.csv` zone convention remains in force. The full register preserves the
source zone, parent-bus zone, mapping method, distance, and ambiguity flags.
Batavia GEN3 has one disclosed 1 MW source-zone A versus inherited bus-62
zone-B conflict; calculations follow its assigned electrical bus.

| Asset | Representation in this stage |
|---|---|
| Indian Point 2 and 3 | Retired, zero capability throughout 2025, absent from active dispatch and reference selection |
| Cricket Valley | Six unique EIA units at existing bus 73, zone G proxy; three EPA reporting trains are partitioned over the plant, without assuming matching unit-label strings |
| Bayonne Energy Center / Linden Cogen | Ten Bayonne records and eight corroborated Linden records at the existing bus 82 Zone-J proxy; Linden GTG6 is excluded as PJM |
| South Fork Wind | One EIA SFWND record at existing bus 80, zone K proxy; EIA-reported 130 MW capability is retained with the owner-source capacity discrepancy disclosed |
| St. Lawrence | Admitted units at bus 48; OA unit 21 excluded |
| Niagara | Thirteen distinct units at bus 55 |
| Nine Mile Point / FitzPatrick / Ginna | Existing nuclear landings at buses 50 / 50 / 53 |
| 74th Street | Two EIA generator records at inherited bus 82; separate EPA location repair resolves the seven previously unqualified fossil-prior hours |

Cricket Valley has 1,016.1 MW summer and 1,138.2 MW winter capability in this
EIA vintage. The capacity is distributed over its six physical inventory
records once. South Fork is part of statewide wind, never an extra addition
on top of the wind prior. The market-scope extension therefore follows
NYISO membership and primary unit evidence, not physical state alone.

Native eligibility requires EIA-reported **NYIS** balancing-authority
membership, an admitted utility/IPP sector, and no explicit unsynchronized
flag. During independent review, 53 previously admitted New York State rows
were found to report ISNE. They now have zero native bounds. All 55 ISNE-labeled
inventory rows remain visible, and their physical-capability arrays and bus
assignments remain unchanged. This follows the reported authority field; it
does not independently certify every EIA authority label or solar/BTM boundary.
See the [authority-scope ledger](output/nygrid_2025_dispatch/fleet/balancing_authority_scope_register.csv).

Market membership also required extending the geographic inventory beyond NY
State. Primary NYISO roster/2025 Gold Book and owner evidence corroborates ten
Bayonne Energy Center generators and Linden GTG1–GTG5/STG1–STG3 as NYC/Zone-J
resources. Their combined summer capability is **1,346.3 MW**; winter is
1,431.4 MW. Linden GTG6 belongs to PJM despite its plant-level NYIS metadata.
It is excluded, as are two uncorroborated NJ solar records (4.3 MW). The three
quarantined records have no native bus assignment. The remaining two PA
NYIS-labeled plant proposals have no generator records in the scanned sheets.
See the [outside-NY register](output/nygrid_2025_dispatch/fleet/outside_NY_scope_register.csv)
and [preserved primary receipts](output/nygrid_2025_dispatch/fleet/source_scope/source_receipts.json).

Bayonne/Linden native generation is separate from the Linden VFT merchant
transmission schedule. The VFT input remains unchanged and counted once. The
new NJ source records redistribute the existing P63 fossil total rather than
adding generation on top of it. P63 membership is inferred from their native
NYISO registration; P63 does not supply individual-unit telemetry.


## Capabilities and source priors

The fleet uses versioned 2025 early-release EIA seasonal net capabilities,
not inherited 2019 `9999` limits. Winter is November–March and summer is
April–October. Operating-month and retirement-month cutoffs are conservative:
the start month is excluded, and the retirement month is excluded. A unit
retiring during 2025 can operate before that cutoff. Forced outages and
within-year capability revisions are not fully reconstructed.

One explicit exception uses Arthur Kill GT1's 18 MW nameplate as a proxy for
missing seasonal capability through April, before its May retirement. Eight
other active combined-cycle component rows also have blank seasonal data;
they remain at zero because companion rows appear to carry combined
capability. Automatically filling those blanks would risk double counting.
The [seasonal-data ledger](output/nygrid_2025_dispatch/fleet/seasonal_capacity_gap_register.csv)
distinguishes missing values, reported zeroes and the narrowly applied proxy.

Generation preferences preserve the independently assembled source evidence:

- Fossil preferences use unique EPA reporting-unit gross output, weighted by
  operating time once, distributed through documented crosswalk/plant splits,
  and reconciled to NYISO statewide fossil totals. They are estimates of net
  unit output, not observed net dispatch.
- Nuclear preferences use NRC daily availability and EIA capability. Upper
  bounds are limited by both capability and that daily availability proxy.
- Hydro preferences retain the frozen monthly/plant reconstruction.
- Wind and solar cannot exceed their source-allocated hourly availability or
  physical capability. Their geographic and grid-delivery shares remain
  assumptions; gross demand is not reduced a second time for those generators.
- Pumped hydro cannot exceed its frozen estimated hourly generation prior or
  capability. It supplies no extra balancing output. Charging, reservoir energy
  and SOC are not modeled. Batteries remain disabled.

The official 2025 NJ EPA extract contains all 8,760 hours for each of 16
Bayonne/Linden reporting groups. Ten Bayonne records use official one-to-one
EIA associations. Five admitted Linden reporting groups are summed once and
partitioned once over eight unique native EIA generators. The GTG6-associated
reporting group 004001 is excluded conservatively. Because its EPA association
also lists shared steam generators, its gross output is **not asserted to be
entirely PJM energy**; a defensible hourly steam split is unavailable. This
uncertainty remains in the extraction receipt and source preferences.

Preferred MW can exceed an admitted capability or belong to an excluded
identity. Those conflicts are saved rather than silently reassigned. The
optimizer projects the preferences into the feasible set. See
[scope conflicts](output/nygrid_2025_dispatch/priors/fuel_hourly_scope_conflicts.csv.gz)
and [dispatch adjustments by fuel](output/nygrid_2025_dispatch/dispatch/fuel_adjustments.csv),
which distinguish the full source preference, admitted preference, excluded
preference and final output.

## Dispatch and electrical accounting

All public quantities use the existing fixed conversion
`gamma = 9561 / 31857.1773 = 0.30012075175285535`. Gross demand, native
generation/capabilities, external schedules and DC transfers share this scale.
Branch R/X/B, tap ratios, phase shifts, status, endpoints and baseMVA are
preserved. Bus operating types and the angle reference are updated for the
new generator fleet; no bus or network branch is added.

The continuous native objective is

`J = 0.5 * sum_g kappa_f / C_g * (PG_g - preferred_PG_g)^2`,

subject to the declared hourly generator boxes and exact native active-power
balance. `C_g` is positive seasonal physical capability in model MW; the
denominator is one only for a fixed zero-capacity variable. Penalties are
fossil 1, conventional hydro 25, nuclear/wind/other-renewables 100, and pumped
hydro 100. These are declared research preferences, not fitted uncertainty
estimates or economic costs. Capacity weighting avoids changing the aggregate
correction merely by splitting otherwise identical generators into more rows.

The solver uses a monotone multiplier search for the strictly convex box/equality
projection. It saves preferences, bounds, weights and multipliers so an
independent validator can check optimality. Neither limits nor load are relaxed
to produce a solution. Native required generation ranges from 2,718.84 to
8,765.47 model MW across the qualified hours.

External generation remains the regional load-plus-exchange equivalent from
the full network. Its hourly lower and upper bounds equal its prescribed
injection; this is a schedule constraint, not a claim about external plant
capability. HQ plus Cedars is counted once. DC transfers draw on those same
regional totals and likewise have fixed schedule bounds. Their physical
equipment ratings are not certified here.

The reference is bus 50 when it has admitted generation; otherwise the bus of
the largest dispatched native generator is used. It sets the angle gauge only.
Independent DC replays are required to leave generation unchanged within
numerical tolerance. Indian Point is never used as a balancing resource.

Reactive generator fields are zero DC placeholders, not physical Q limits.
No economic costs are supplied. Use `rundcpf` for this case; AC dispatch or
thermal-security conclusions require additional data and validation.

## Fresh validation and remaining interface discrepancies

**179 independent checks** pass across all 8,663 qualified hours, and **29
focused tests** pass, including adversarial optimality/balance tests. Fresh
MATPOWER replay passes at 16 calendar/stress/DST snapshots and confirms that
the loader rejects unqualified hours.

| Independent check | Maximum residual |
|---|---:|
| Generator active-power bound violation | **0 MW** |
| Quadratic optimality condition | **1.16e-14** |
| Nodal active-power balance | **3.30e-11 MW** |
| Independent Python DC branch-flow replay | **8.53e-12 MW** |
| Regional scheduled export balance | **1.86e-11 MW** |
| Fresh MATPOWER branch-flow replay | **1.36e-11 MW** |

See the [independent validation](output/nygrid_2025_dispatch/validation/validation_summary.json),
[per-hour checks](output/nygrid_2025_dispatch/validation/independent_hourly_checks.csv),
[focused tests](output/nygrid_2025_dispatch/validation/unit_tests.log), and
[MATPOWER replay](output/nygrid_2025_dispatch/dispatch/matlab_validation.json).
A separate clean dispatch run reproduces all **33 saved fields (30 numeric)**
exactly, including the same NaN masks; its CSV/contract files also match byte
for byte. See the [rebuild comparison](output/nygrid_2025_dispatch/validation/rebuild_comparison.json).

Interface observations were read only after the reconstruction was frozen.
The following are **unfitted diagnostics using inherited 2019 operators**,
whose membership is not certified as the physical 2025 flowgates. They use the
same 8,663 hours and public-equivalent MW (`model MW / gamma`).

| Inherited interface proxy | MAE, public-equivalent MW | WAPE |
|---|---:|---:|
| Dysinger East | 438.62 | 52.28% |
| West Central | 440.36 | 79.03% |
| Total East | 389.51 | 12.44% |
| Moses South | 513.57 | 95.14% |
| Central East | 453.76 | 27.27% |
| UpNY–ConEd | 193.84 | 6.47% |
| Sprain/Dunwoodie South | 163.89 | 8.87% |

The [post-hoc score receipt](output/nygrid_2025_dispatch/dispatch/posthoc_scoring_receipt.json)
ties these results to the exact fixed predictions and observations. These
errors do not invalidate the numerical balance checks, but they prevent an
interface-accuracy claim. In particular, Moses South has a large unresolved
directional bias. A read-only check found no concrete major hydro/nuclear
identity duplication or implemented HQ/Ontario double counting; that does not
establish the cause of its residual. Geographic allocation, actual-versus-
scheduled exchanges, controls, topology and interface definitions still need
review. The 2019 and 2025 scores use different operating years and populations
and are not a controlled before/after accuracy comparison.

## Use and reproduce

The loader is [npcc_nygrid_2025_full_dc.m](System%20Matpower%20Format/npcc_nygrid_2025_full_dc.m).

```matlab
addpath('System Matpower Format');
mpc = npcc_nygrid_2025_full_dc(1);
[result, success] = rundcpf(mpc, mpoption('verbose', 0, 'out.all', 0));
```

The 1-based index follows UTC physical hours; consult `hour_status.csv` for
timestamps and qualification. Saved data are split into four MAT files
without reducing precision: case/states, generator bounds, priors/weights,
and network flows/angles. Rebuild instructions and the isolated Python command
are in the [script README](scripts/nygrid_2025_dispatch/README.md).

This package establishes the requested bounded DC starting point. The next
network work can now use a fixed, inspectable 2025 operating baseline while
revising Downstate landings/topology and validating the corresponding flowgate
definitions. It should not treat the present interface residuals as already
resolved.
