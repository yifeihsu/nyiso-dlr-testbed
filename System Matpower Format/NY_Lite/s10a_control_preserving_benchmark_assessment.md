# S10a Control-Preserving PERFORM Benchmark

## Status

S10a is a diagnostic same-snapshot benchmark. S7 remains the structural baseline.

The 2019 PERFORM source is similarity-scaled by `gamma = 0.365850476` so its per-unit operating point is preserved at the 10902.220-MW NPCC-NY load scale.

## Results

| Metric | Result | Initial target |
|---|---:|---:|
| Reduced Q-limit PF | 1 | 1 |
| Retained/pilot voltage RMSE | 0.002613 pu | < 0.01 pu |
| Maximum retained/pilot voltage error | 0.009576 pu | < 0.03 pu |
| Seven-interface MAE | 225.143 MW | < 100 MW |
| Mean normalized control-group Q error | 0.196362 | < 0.10 |
| Scaled source active loss | 229.000 MW | diagnostic |
| Reduced active loss | 103.082 MW | diagnostic |

## Interpretation

The benchmark isolates control/reduction error from the 2025 public scenarios. The first five interface rows use matched zone-pair cut proxies. UPNY-ConEd and Dunwoodie South remain conceptual source-to-reduced mappings because exact monitored-element operators are not yet available.

All ten previously PQ-skipped S7 generator/proxy locations have source control evidence, but broad Q limits or low-confidence aggregation remain at some locations. PV treatment in S10a is therefore diagnostic and does not promote those buses in S7.

Transformer control modes, switched-shunt block optimization, exact interface operators, and a full Ward/Kron network equivalent remain pending.
