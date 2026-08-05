# S5 PERFORM-referenced PF assessment

## Purpose

This benchmark tests whether PERFORM can improve the calibrated full-NPCC
model by supplying two structural references:

1. within-zone generation shift keys (GSKs) mapped to retained NPCC buses;
2. direct equivalent parameters for Gilboa-Leeds and the
   Pleasant Valley-Wood Street-Millwood corridor.

For each of the six public NYISO scenarios, an S4 NY-only IPOPT ACOPF first
provides the aggregate generation total in each zone. Those zonal totals are
then held fixed while the bus-level allocation and tie-line assumptions are
changed. A full-NPCC AC power flow is run after selecting an external reference
generator. This isolates the structural effect of the GSK and tie parameters
from a new economic redispatch.

Interface consistency is scored with the established fixed scale for each
public P-32 proxy:

```text
J_fixed = sum_s sum_m ((F_model(s,m) - F_target(s,m)) / S_m)^2
```

Lower is better. The reported PF score is diagnostic only; PF convergence does
not enforce generator P limits, branch ratings, or voltage feasibility.

## Main result

| Allocation and ties | PF success | J_fixed | Change from S4/current | Mean bus redispatch |
|---|---:|---:|---:|---:|
| S4 GSK, current ties | 6/6 | 3.5341 | baseline | 0 MW |
| PERFORM GSK, current S4 capacities | 6/6 | 3.5339 | +0.005% | 2,660 MW |
| PERFORM GSK, PERFORM R/X | 6/6 | 3.5544 | -0.575% | 2,660 MW |
| PERFORM capacity and GSK, current ties | 6/6 | 3.7208 | -5.281% | 5,764 MW |
| PERFORM capacity and GSK, PERFORM R/X | 6/6 | 3.7949 | -7.379% | 5,764 MW |
| PERFORM capacity/GSK, PERFORM R/X/B | 6/6 | 3.7968 | -7.431% | 5,764 MW |

The small 0.005% improvement from the clipped PERFORM GSK is not material and
comes with worse voltage and limit diagnostics. The faithful capacity-aligned
PERFORM allocation worsens the interface objective. Direct corridor alignment
also worsens it, although it modestly reduces the largest external overload and
reference-generator P-limit violation.

## Feasibility diagnostics

All 54 PF runs converge, but none of the full-NPCC variants is certified
feasible. In the S4-GSK/current-tie baseline:

| Violation | Element | Result |
|---|---|---:|
| Branch overload | 80, Watercure-Homer City | up to 722.67 MVA over RATE_A |
| Branch overload | 116, Vida-Marysville | up to 83.90 MVA over RATE_A |
| Branch overload | 190, Whitpain-Peach Bottom | up to 921.19 MVA over RATE_A |
| Low voltage, winter peak | Whitpain | 0.88556 pu versus 0.90 pu minimum |
| Low voltage, winter peak | Keeney | 0.89965 pu versus 0.90 pu minimum |
| Reference P limit, winter peak | Peach Bottom generator 43 | 263.05 MW over PMAX |

The full-PERFORM R/X/B sensitivity does not recreate the earlier system-wide
overvoltage, but it provides no interface-score benefit over the R/X-only
case. New line charging therefore remains excluded from the recommended path.

## Interpretation and recommendation

PERFORM is useful as a higher-resolution source of plant geography, candidate
GSKs, and corridor priors. Its 2019 on-peak dispatch is not a universal bus
allocation for the six 2025 public scenarios. Exact transfer of that allocation
helps one operating condition but degrades most others.

Retain `npcc_ny_lite_s4_cost_calibration_candidate_v2` as the working default.
Keep `npcc_ny_lite_s5_perform_referenced_candidate` as an experimental
sensitivity only. The next defensible calibration is to blend S4 and PERFORM
GSKs or treat the PERFORM pattern as a soft regularization prior, with
scenario-dependent zonal totals and P-32 interface residuals retained as the
validation metric.
