# S12: Retention-Set Reduction of PERFORM with Seasonal Priors and Device Controls

**Date:** 2026-07-20
**Case:** `npcc_ny_lite_s12_perform_retention_core.m` (network) +
`s12_case.mat` (authoritative only for the S12 reference artifact and its
operators/metadata userdata)
**Status:** calibration and validation oracle only. S12 is a reference
reduction used to design and test the NPCC-preserving S13 augmentation; it does
not supersede the full 143-bus S7 structural parent, promote the 49-bus S11
diagnostic, or replace full PERFORM as the highest-fidelity source.

## What S12 is

A 317-bus, 3,531-branch (359 physical + 3,172 equivalent) reduction of the
PERFORM 2019 NY case (1,576 buses). The listed same-snapshot quantities are
retained or reproduced at high precision, making S12 useful as an oracle. Its
dense Ward/Kron network is not the promoted NPCC DLR testbed:

- **All 47 monitored circuits** referenced by the seven NYISO interface
  operators (including every Dunwoodie South, UPNY-ConEd, and Total East
  element present in the source) are retained verbatim with their true
  impedances and ratings, plus the five DLR physical circuits.
- **All 615 generators stay native at their true buses** (the retention set
  includes every generator bus), so GSK/relocation error is zero.
- **All 34 switched shunts** are at retained buses (`s12_switched_shunts.csv`
  carries block data); the ≥230 kV backbone (130 buses) is retained.
- Eliminated buses are load-only. Their loads are Ward-mapped through the
  exact Kron elimination operator with **zone labels preserved**
  (`s12_zone_base_load_p/q` userdata), so per-zone scenario scaling works.

### Snapshot exactness for oracle comparisons

| Check | Result |
|---|---:|
| Ward identity residual | 3.7e-11 pu |
| Snapshot voltage reproduction | RMSE 1e-6 pu |
| Monitored-circuit flow error (47 circuits) | max 0.017 MW |
| Interface operator sums vs source | < 0.05 MW |

The S11 sparse admittance correction (Ward diagnostic 0.317 -> 0.889) is not
used in this reference artifact; the S12 equivalent derives from exact
elimination with only couplings below 1e-5 pu admittance dropped (their
diagonal effect kept as shunts). This is a reference-model distinction, not a
change to the repository model hierarchy.

## Interface operators

`s12_interface_operators.csv` contains reference per-circuit reduced-branch
operators with area-rule signs. Total East was rebuilt as the physical east-boundary cut
{5 Central East circuits + Fraser-Gilboa GF5-35 + Coopers Corner-Rock Tavern
CKT1/2} (8 circuits, 2,670 MW at snapshot). It remains a **proxy** for the
official composite (which also includes external ties and Rockland elements);
UPNY-ConEd (9 circuits) and Dunwoodie South (12 circuits) now use their full
source monitored sets. Those latter lists are not final S13 truth operators:
UPNY-ConEd double-counts series paths around Wood Street, and Dunwoodie mixes
H-J and K-J transfer families. S13 must use corrected nonintersecting physical
cutsets after the required terminals are added.

## Seasonal dispatch priors (NYGenUCV4 + NYISO fuel mix)

`s12_build_priors.m` builds unit-level priors for each 2019 scenario hour:

- NYISO real-time fuel mix (public `rtfuelmix` archives, Jan/Apr/Jul 2019
  downloaded to the cache) gives actual per-class statewide output at each
  scenario hour; classes are allocated to units proportional to capability.
- PERFORM `ng/dfo/rfo` labels cannot separate NYISO "Dual Fuel" from
  "Natural Gas", so both categories feed one Gas pool (documented merge);
  99.7%+ of fuel-mix MW allocate in every hour.
- **NYGenUCV4 winter capacities** matched 594/594 eligible units by plant name
  and cap winter-hour allocation weights.
- **Unit commitment is a constructed prior, not an observation**: each
  statewide fuel-class total is allocated across eligible positive-capability
  units in proportion to capability. This can assign output to units that are
  offline in the PERFORM on-peak snapshot, including Indian Point 2/3, but it
  does not establish historical unit commitment or plant-level dispatch.

Outputs: `s12_unit_dispatch_priors.csv`, `s12_zonal_generation_priors.csv`,
`s12_fuel_class_allocation.csv`.

## Device-level controls: what the source supports

- **Switched shunts**: 34 records preserved at retained buses (1,036 MVAr
  BINIT total), currently fixed at snapshot values inside bus GS/BS; block
  data retained for future discrete switching logic.
- **Transformers**: retained as physical branches, but the PERFORM NY RAW has
  **zero phase-shifter angles, zero automatic tap controls, and one
  off-nominal tap** across all 144 transformers. PAR device modeling (e.g.,
  Ramapo) **cannot be sourced from this dataset**; external PAR-controlled
  ties enter only as boundary schedules. This is a documented dataset
  limitation, not an omission.
- **HVDC**: the two-terminal DC section is empty; CSC/Neptune/HTP/VFT enter as
  boundary injections, now individually scheduled (see below).
- **Generator voltage controls**: snapshot VS via bus voltages; the S10a
  649-record control map remains the device-class source.

## External representation

`s12_external_boundary_groups.csv` maps the 21 PERFORM boundary-injection
records to nine P-32 schedules (HQ, OH, NE AC, NPX_1385, NPX_CSC, PJM AC,
PJM_HTP, PJM_NEPTUNE, PJM_VFT) — richer than the previous four-schedule
mapping; wheel paths are now individually scheduled at their true landing
buses (W 49th St, Newbridge, Gowanus, Shoreham, Northport).

## Six-scenario validation (2019 scaled targets)

`run_s12_scenario_validation.m`; results in `s12_scenario_summary.csv`,
`s12_scenario_interface_validation.csv`, `s12_zonal_closure_movement.csv`.

- **Standard PF: 6/6. Q-limit-enforced PF: 6/6** (S7 also reaches Q-PF 6/6
  after the 2019 retarget; the 2025-era shoulder failure is absent under this
  changed operating-point set, not demonstrated to be structurally eliminated).
- Voltages within [0.991, 1.068] pu in every scenario; reference pickup < 1 MW.
- Forward (prior-only, no interface fitting) vs closed (bounded zonal
  DC-inverse, per-zone trust +-1090 MW scaled) interface MAE across six hours:

| Interface | Forward MAE (MW) | Closed MAE (MW) |
|---|---:|---:|
| Dysinger East | 181.6 | 22.1 |
| West Central | 111.0 | 152.7 |
| Moses South | 243.8 | 4.8 |
| Central East | 225.5 | 40.5 |
| Total East proxy | 581.2 | 187.1 |
| UPNY-ConEd | 517.3 | 42.2 |
| Dunwoodie South | 321.9 | 13.0 |

- **All-hour fixed-scale objective: 0.0558 closed (S7 baseline: 0.4896 on
  identical targets and scales).** This is an in-sample oracle benchmark:
  interfaces inform the closure, so the numerical improvement cannot determine
  promoted-model status. Forward objective 1.587.

### Honest caveats

1. The closed numbers are in-sample (interfaces inform the zonal closure),
   like every S6/S8-class number before them; the forward numbers are the
   fitting-free reference.
2. Closure zonal movement is 1.7-3.0 GW scaled per hour (16-27% of NY load),
   above the old S11 10% gate; the fuel-mix prior is statewide-proportional
   and carries no locational merit order, so the closure does more work.
   A cost-based or historically-shaped prior would reduce this.
3. West Central slightly worsens under closure because its 4,479 MW objective
   scale makes it nearly weightless in the fixed-scale objective.
4. Total East remains a proxy of the official composite.
5. Switched shunts are static at BINIT; boundary Q is fixed at scaled
   snapshot values.
6. Equivalent branches (3,172) have no thermal ratings; only physical
   branches carry ratings. This is appropriate for reference-current
   comparisons, but it does not determine S13 DLR eligibility.

## How S12 may and may not be used

Use S12 to identify source endpoints, physical-circuit parameters and ratings,
interface membership, controls supported by the source, same-snapshot currents,
losses, PTDFs, and held-out perturbation responses. Do not copy its 3,172
Kron-equivalent branches, dense 317-bus topology, full 615-generator dispatch,
or fitted closed dispatch into S13. Full PERFORM remains the source dataset and
highest-fidelity reference.

## Reproduction

This refreshes the reference oracle only; it does not promote S12.

```matlab
addpath('System Matpower Format'); addpath('System Matpower Format/NY_Lite');
run('s12_build_retention');    % retention set CSV
run('s12_reduce_perform');     % Ward/Kron reduction + snapshot validation
run('s12_persist_case');       % case + operators + metadata
run('s12_update_te_operator'); % Total East boundary cut
run('s12_build_priors');       % seasonal priors (uses cached rtfuelmix)
out = run_s12_scenario_validation();
```
