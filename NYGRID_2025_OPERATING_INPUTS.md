# 2025 operating inputs for the full NYgrid NPCC model

This is the first build stage for the requested 2025 Downstate refinement.
It updates the operating-data layer and retains the unreduced 140-bus parent.
It does not claim a completed 2025 generator dispatch or a calibrated network.
The frozen 2019 reproduction and the older compact models remain separate.

## Scale and accounting

The user requested the existing load-scaling strategy because the NPCC
benchmark demand differs from actual NYISO demand. The new package uses one
constant factor throughout 2025:

`gamma = 9,561 MW / max_hour(sum_zone(observed 2025 NYISO load MW))`.

Every public load, generation prior, external schedule, and interface observation
has an original-MW representation and a benchmark-MW representation using this
same gamma. The 9,561 MW numerator is the NY total at buses 37–82 in the pinned
paper-source `Data/npcc.mat`, after the paper's absolute-PD correction. It is a
declared snapshot anchor normalized to the annual observed peak, not evidence
that the NPCC snapshot was an actual peak condition. The 10,902.2198 MW anchor
in the older compact build belongs to a different source case and is not reused.
See [the source audit](output/nygrid_2025_inputs/scaling_audit.json) and
[the generated scale manifest](output/nygrid_2025_inputs/model/scaling_manifest.json).

The complete-year peak is **31,857.1773 MW at June 24, 2025, 18:00 EDT**
(`22:00 UTC`), giving **gamma = 0.30012075175285535**. This combines the paper's
spatial allocation with the user-requested NPCC benchmark normalization. The
paper itself replaced NY demand with observed MW and scaled the external
regions; it did not impose this additional global peak normalization.

This policy preserves each zone's hourly shape and simultaneous statewide
share. Year-specific peak normalization removes between-year peak-load growth
from the benchmark; retain the public-MW columns when studying that growth.
Any later interface comparison must use either both sides in benchmark MW or
both sides in public MW. The 2019 baseline is in actual MW and cannot be
compared directly to the new benchmark MW without that conversion.

Within each zone, the pinned paper `npcc_new.csv` positive-load weights allocate
demand to existing buses. Zone J has no positive weights, so the paper's
uniform fallback assigns half to bus 81 and half to bus 82. Zone G uses the
paper's explicit revised weights. These allocations remain coarse pending
the Downstate bus expansion; they are not measured substation demand.

Gross NY load is kept separately from every generation source. No renewable
or import series is subtracted from it in this stage. NY QD assumes 0.98
lagging power factor. Neighboring-area demand uses the original NPCC absolute
PD scaled by `NY benchmark gross load / 9,561`; its signed QD uses the same
ratio to preserve the original Q/P. Neighboring loads and all QD are assumed
profiles, not 2025 observations. Scaling external QD is an explicit correction
to the paper implementation's frozen external QD convention.

## External exchanges and generation

The full neighboring networks are retained. Ten disjoint schedule channels
follow the paper's region/device accounting: primary HQ plus Cedars; Ontario;
primary New England plus 1385 and CSC; primary PJM plus HTP, Neptune and VFT.
`SCH - HQ_IMPORT_EXPORT` is not counted again. Four inherited DC transfer rows
draw on the corresponding regional generation total. They are not added a
second time as independent net supply.

The external generator proxy uses original NPCC generator shares within each
region and `regional assumed load + scaled exchange`. HQ plus Cedars occupies
the inherited single injection at bus 48. Ontario's flow distribution remains
a result of the retained external network, not an imposed landing solely at
bus 54. This prepares injections; it does not establish 2025 external unit
availability or exact physical line flows.

Generation source tables retain NYISO statewide fuel observations, EPA gross
output evidence, and explicitly allocated zonal priors. EPA reporting units
are not automatically individual generators or net grid injections. Gross/net
differences, reporting scope, duplicate mappings, and missing values remain
visible in the source evidence. The fleet/mapping registers distinguish
retirements, retained identities and additions that require a landing decision.
Indian Point 2 and 3 cannot serve as 2025 generation or as a slack generator.
Cricket Valley and South Fork must be represented once when the fleet is
assembled, including any prior contribution already attributed to their zones.

The MAT file's `base_case` is the immutable 2019 structural parent, including
historical generator rows. It is not presented as an updated runnable case.
`external_input_pg` supplies only the 28 inherited external/HQ proxy rows;
the 243 native NY rows are NaN until generation reconstruction. The explicit
flags `ny_generation_dispatch_available=false` and
`ready_for_dc_power_flow=false` prevent a partial input build being mistaken
for a balanced power-flow result. The separate source balance residual is
diagnostic; it is not assigned silently to a retired Indian Point slack unit.

The generation layer contains 2,010,528 EPA unit-hour records for 234 reporting
identities and 481,800 estimated zone/fuel prior rows. All seven NYISO fuel
categories have 8,750 qualified hours and 10 gap hours. Fossil allocation loses
seven additional hours because EPA ORIS 2504 / CT0002 (74th Street, at most
14 MW) has no zone match under the declared identity mapping policy. The
source ledger retains that output as `UNMAPPED`; a future mapping update can
resolve it explicitly. Thus **8,743 hours have every generation-prior category
qualified**, and **8,656 hours have both qualified priors and boundary inputs**.
The remaining 104 hours retain their failed source-quality flags and NaNs.

Nuclear weights use NRC daily availability and EIA seasonal capability;
hydro uses EIA monthly baselines and finite generation headroom; wind uses
active capacity shares; other renewables use active capacity and a solar
daylight proxy. These allocations are assumptions. EIA 2025 is an early
release, and published annual-respondent monthly hydro values are estimates.
Neither these inputs nor an `allocation_qualified` flag establishes observed
zonal generation, storage-energy feasibility, or a bounded unit dispatch.

Across the 8,663 hours with statewide fuel totals and all boundary channels,
`generation + scheduled imports - gross load` has a mean of **92.93 public MW**
and mean absolute value of **121.98 public MW**, ranging from -760.88 to
2,440.61 MW. This is a
[source reconciliation diagnostic](output/nygrid_2025_inputs/validation/source_reconciliation.json),
not a solved balance. Scheduled/actual interchange, losses, reporting scope
and aggregation conventions are possible contributors; their attribution
has not been established.

## Time, missingness and provenance

The canonical axis consists of the 8,760 physical hours from
`2025-01-01T05:00:00Z` through `2026-01-01T04:00:00Z`, with local civil labels
and EST/EDT retained. Fall's repeated civil hour remains two different UTC
hours; spring's nonexistent hour is not invented. EPA local-standard-time
records are aligned to this same axis explicitly.

Source extraction keeps raw archives or source retrieval manifests, hashes,
sample coverage and duplicate/gap diagnostics. P32 hourly schedule/flow
estimates use time-weighted forward sample hold and a maximum admitted sample
gap of 600 seconds. P63 has its own recorded interval convention. Their
quality reports state the data-specific consequences. Missing/unqualified
source windows remain NaN; scaling cannot make them qualified.

The P58C labels are treated as hour beginnings following the repository's
earlier empirical P58B/P58C timing audit. This is a declared alignment
convention, not a claim that the hourly file supplies a formal integration
specification. All **96,360 zone-hour loads** pass source checks. P32 has
**8,673 qualified hours and 87 gap hours**, with a longest source gap of
3,000 seconds. Original numeric interface-limit averages remain available,
but any interval touched by a `+9999` or `-9999` sentinel receives an unusable
model-limit flag and a NaN model limit; those values are not physical ratings.

The 2019 interface member map is not certified as a physical 2025 flowgate
definition. The 2025 public interface observations are saved for later
mapping/calibration and are not used to choose gamma, allocate load, or fit
generation priors. No new line R/X/B, network node, or physical DLR rating is
introduced by this operating-input stage.

## Reproduce and inspect

Run from the repository root. See the
[rebuild instructions](scripts/nygrid_2025_inputs/README.md) for source,
compiler and validation commands. The compiler refuses to replace an existing
`operating_inputs.mat`; use a new output directory for a numerical rebuild.
Source dependencies are tied to the pinned 2019 reproduction and the public
2025 retrieval receipts. Large raw EPA/EIA downloads use the existing ignored
cache rather than being copied into the model artifact.

In MATLAB, add `System Matpower Format` to the path and call:

```matlab
inputs = npcc_nygrid_2025_operating_inputs(1);
```

This returns the selected hour's inputs, UTC identity and qualification flags.
It deliberately returns an input struct without `bus`, `branch` or `gen`
fields, so it cannot be accidentally treated as a runnable MATPOWER case.

Fresh validation passed **289 independent accounting checks**, **26 focused
tests**, and the MATLAB accessor check at six representative hours including
the annual peak, both fall folds and a gap. A separate compiler run reproduced
all **41 saved data fields, including 33 numeric fields, exactly**; generated
CSV files also match byte-for-byte. The largest accounting residual in the
independent input checks is 3.87e-12 MW. See the
[validation summary](output/nygrid_2025_inputs/validation/validation_summary.json),
[test log](output/nygrid_2025_inputs/validation/unit_tests.log),
[MATLAB check](output/nygrid_2025_inputs/model/matlab_accessor_validation.json),
and [rebuild comparison](output/nygrid_2025_inputs/validation/rebuild_comparison.json).
These checks establish source handling, scaling and allocation consistency.
They do not establish power-flow feasibility or interface-fit accuracy.

The subsequent build work is to finalize the 2025 fleet and bus landings,
reconstruct a bounded balanced dispatch, choose an active reference bus,
then add dated Downstate topology and establish 2025 interface definitions.
Those are separate validation claims from the source/scaling checks here.
