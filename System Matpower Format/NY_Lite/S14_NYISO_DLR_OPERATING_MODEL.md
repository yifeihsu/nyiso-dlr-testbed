# S14-NYISO: NY-only electrical operating model

**Target case:** `npcc_ny_lite_s14_nyiso_dlr_operating_model`

**Contract revision:** 2026-09-07, Package A (Steps 1–4)

**Operating form:** New York network with explicit NY-side boundary injections

**Electrical qualification:** determined by operating-result artifacts, never by this specification

**Reproduction entry point:** `run_ny_only_foundation`

## Model roles and scope

S14-NYISO is qualified directly as a NY-only electrical research model. Neither
qualification of neighboring NPCC systems, an external-network reduction, nor
a particular bus count is a prerequisite. Historical source files and previous
diagnostic outputs retain their original meaning.

| Model | Role |
|---|---|
| Original NPCC, S7 and existing S13 checkpoints | Immutable provenance and historical comparison cases |
| Original PERFORM NY case | Pinned source of internal topology, devices, boundary records and historical reference conditions |
| S12 PERFORM reduction | Optional comparison tool; its dense equivalent branches are not construction inputs |
| Existing 86-bus S14 reduction diagnostic | Preserved external-reduction experiment; optional comparison evidence |
| New S14-NYISO candidate | NY-only model with explicit boundary conditions and unrestricted internal refinement |

The operating candidate may replace, deactivate, split or aggregate an
inherited internal equivalent. Its original identity and electrical parameters
remain in the provenance mapping; its contribution need not remain active.
There is no requirement to retain every original NY bus or branch. Replacement
packages account for boundary terminals, voltage levels, branches, gross load,
native generation, shunts and controls together. Every old element receives an
explicit disposition: fully replaced, partially replaced, nonoverlapping, or
correspondence uncertain. Accepted regions cannot contain unresolved duplicate
paths or unexplained omitted injections. Prospective DLR terminals and current
definitions must remain traceable through any replacement.

This freedom applies to the new operating candidate. It does not rewrite the
historical NPCC/S7/S13 case builders, their append-only checkpoint contracts,
or their committed comparison records. An unresolved correspondence may remain
as a documented diagnostic alternative, but cannot silently define an accepted
region.

## Power scale, evidence and independent statuses

`research_model_contract.m` provides these distinct modes:

| Mode | Power convention |
|---|---|
| `historical_2019` | Backward-compatible historical similarity scaling |
| `historical_similarity_scaled` | Explicit name for the same historical scaled convention |
| `historical_actual_mw` | Full-scale 2019 source MW without constant-total normalization |
| `contemporary_2026` | Actual New York MW with the declared 2026 infrastructure cutoff |

The new actual-MW historical mode does not change archived approximately
10.9-GW similarity-scaled scenarios. Source and measurement vintages are
reported separately from the power base.

Three independent statuses are required:

| Status | Meaning |
|---|---|
| `electrical_baseline_qualified` | AC feasible and independently reproducible under declared assumptions and limits |
| `contemporary_validation_coverage` | Scope supported by dated infrastructure, matched observations and held-out evidence |
| `dlr_ready` | Conductor realization and independent electrothermal checks completed |

Observed, reconstructed and assumed values remain distinct. Missing exact
bus-level observations limits validation coverage; it does not prohibit an
explicitly assumed, bounded research baseline. An electrical qualification
does not establish contemporary realism or DLR readiness. The contract itself
sets no successful operating status.

## Package A: normalized source and explicit boundary conditions

Pin one original PERFORM electrical representation and its hash. Use stable
source keys and explicit source-to-model mappings. Classify generator records
as native generation, boundary import/export, reactive support, reference
placeholder or unresolved. A generator-section record is not automatically a
physical generating unit. Inventory shunts and converted controls so the same
device cannot enter once as a generator and again as a shunt. Reconcile the
19-row schedule mapping with the historical 21-record boundary description
using source identities; excluded or inactive records remain visible.

Every represented boundary connection registers its source identity,
schedule group, NY landing bus or buses, status and vintage, evidence class,
delivered P schedule, declared Q, uncertainty, and multi-landing allocation.
Positive P and Q enter the NY network; negative P represents exports. Regional
groups and separately scheduled facilities must have disjoint accounting.
Source bus identities, rather than S12 reduced numbering, locate the landings.

For the initial baseline use scheduled P and declared fixed Q. Keep gross
demand and boundary injections separate; allocate gross load before assembling
the solver case:

```text
Snet = Snative_generation - Sgross_load + Sboundary
Peffective_load = Pgross_load - Pboundary
Qeffective_load = Qgross_load - Qboundary
```

This convention also applies when a landing bus hosts native generation or
load. Fixed boundary records supply no undeclared slack or voltage regulation.
External losses lie outside a NY-side delivered-power model; any explicitly
retained connection's loss is counted once. Freeze and document multi-landing
allocation. Fixed allocation is an assumption, not reproduction of external
loop-flow sharing. Later bounded-Q or voltage-responsive variants require
separate model declarations and sensitivity evidence.

## Historical reference and acceptance

First reproduce the original PERFORM snapshot unchanged and report its
violations. Then construct a separate actual-MW research snapshot with the new
boundary convention and documented native-control assumptions. A reference
placeholder may not acquire arbitrary capability to conceal balancing needs.
Assign balancing to declared native resources and report dispatch movement.

The first reconstruction is prior-only, without internal-interface fitting.
Freeze topology, network parameters, gross demand, boundary schedules,
availability and capabilities. Optimize only native dispatch and explicitly
permitted voltage/reactive controls. A relaxed solution is diagnostic; any
relaxed nodal balance is reported as fictitious injection.

Qualification requires closed gross-load/native-generation/boundary/loss
accounting, independently replayable AC balance, finite P/Q capabilities,
declared voltage, branch-rating and angle limits, and accounted reference
adjustment. Report violations by bus, generator, branch or boundary in MW,
MVAr, pu, MVA and angle units. Preserve all attempted outcomes. Ordinary PF
convergence and implementation-test counts do not qualify the reference.

Package A ends with one qualified historical NY-only source reference or a
quantified report of the remaining repairs. This benchmark does not commit
the operating project to the entire PERFORM network. Internal replacement,
contemporary asset realization/calibration and full electrical release
validation belong to later Packages B, C and D respectively.

## Optional external-reduction experiment

The existing `build_s14_nyiso_retention_set`, `build_s14_external_equivalent`
and `validate_s14_against_s13_full` remain available through
`run_electrical_model_reproduction`. Their 86-bus diagnostic and historical
retention registers remain external-reduction evidence, not the new builder.
For that experiment only, retain the registered NY network and ports, form
the external Schur complement with sparse solves, register all equivalent
parameters/injections and enforce passive realization. No S12 equivalent
branch, negative-resistance shortcut or unlimited external slack is allowed.
Frozen-network replay cannot refit the matrix or conceal source violations.

The direct-reduction aggregate uses named required metrics, including the
registered interface-flow gate. Missing interface operators produce an
unavailable, failing gate. A missing public component is not a zero flow.

| Applicable matched-source simplification metric | Initial project tolerance |
|---|---:|
| Retained-bus voltage RMSE | 0.005 pu |
| Maximum retained-bus voltage error | 0.015 pu |
| Registered interface-flow error | 50 MW per interface |
| Circuit current error | 5% |
| NY active-loss error | 5% |
| Boundary reactive error | 10% or a registered MVAr band |

These are project comparison thresholds, not NYISO certification criteria.
They do not apply indiscriminately to uncertain public measurements or
post-2019 infrastructure. Optional reduction success is neither necessary nor
sufficient for qualifying the NY-only electrical baseline.

## Electrical handoff and future thermal use

An electrical release preserves its builder, fixed parameters, source and
replacement mappings, boundary register, declared study inputs, every attempted
operating result, replay and sensitivity evidence. Qualification must recompute
the applicable gates rather than trust a stored status flag.

Prospective physical overhead circuits and explicitly synthetic overhead
corridors retain their terminal/current definitions. Cable, transformer,
controlled-import and arbitrary equivalent elements remain distinct. Conductor
properties may not compensate for unresolved electrical failures. Thermal
readiness requires independent resistance/current/heating consistency and
conductor/weather provenance, after electrical qualification.
