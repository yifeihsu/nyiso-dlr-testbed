# Comparison using the authors' released 2019 model

This corrects the reference used in the preceding comparison. The 2019 benchmark here is the **authors' released final 57-bus NYgrid DC model with their supplied 2019 inputs**, pinned at NYgrid commit `47698b6c7823ae7b1bc6935e5601d5b64b8f918e`. It is not our reconstructed 140-bus counterpart and does not use any of our 2025 model changes or operating inputs.

## Model and input provenance

The authors' pipeline is `modifyMPC` → `updateOpCond` → `rundcpf`. Its final case has 57 buses, 94 AC branches, 271 generator records and four DC-link records. The provided 2019 load, generation, interchange and prepared observation inputs are retained at the authors' public-system power scale, with their original 8760 local-hour preparation and missing/DST treatment.

All 73 pinned upstream files passed SHA-256 and Git-blob identity checks. The archived annual run used a separate performance-only table-reading cache; its allocation, reduction and solver arithmetic remained unchanged. Existing original-versus-cache checks were verified, and **12 new monthly runs of the unmodified author source reproduce the saved inputs and solved flows exactly**. Each fresh case matches bus, generator, branch, DC, cost and interface arrays with maximum difference zero. No reconstructed/full counterpart or current 2025 case was loaded during those checks.

All 8760 saved author-model hours were independently rescored from their 94-branch flow arrays. This is a fresh provenance check, 12 fresh source solves, and a fresh full-year rescore of the verified archived release run; it is not represented as 8760 new MATLAB solves in this task.

## Two measurements of the same unchanged model

The release contains an internal discrepancy between five hard-coded branch-index formulas in `Utility/flow4Plot.m` and its own signed interface map `m.if.map` in `updateOpCond.m`. Both measurements are retained separately:

1. **Strict literal plotting-helper output:** execute the released formulas exactly. Pooled WAPE is 60.663879663%. These stale indices do not reproduce the reported validation figure and must not be used to claim that our current model is dramatically more accurate.
2. **Authors' supplied interface-map output:** aggregate the same unchanged solved branch flows using the authors' own `m.if.map`. Pooled WAPE is 11.218076931%. This changes the reported measurement only; no network parameter, load, generation, dispatch, input or power-flow solution changes.

The independent reviewer parsed the original source's member lists and verified that they equal the saved map in all four annual partitions. Both independently reconstructed interface series match their respective saved series exactly. The table below uses the supplied map for meaningful interface comparison and labels it explicitly.

## Corrected comparison reference

Both WAPE columns use `100 × sum(abs(simulated − observed)) / sum(abs(observed))`. These are our calculations from released-model outputs, not an author-published WAPE table. The current 2025 column remains a separate comparison model; it is never substituted for the 2019 reference.

| Interface | Authors supplied if.map: 2019 WAPE | Current 2025 WAPE | 2019 MAE, MW | Current MAE, MW |
|---|---:|---:|---:|---:|
| Dysinger East | 22.49% | 30.94% | 209.92 | 259.49 |
| West Central | 46.81% | 46.07% | 218.46 | 256.55 |
| Total East | 7.24% | 15.06% | 286.53 | 471.55 |
| Moses South | 8.99% | 22.01% | 152.70 | 118.82 |
| Central East | 9.63% | 13.85% | 211.80 | 230.42 |
| UpNY-Coned | 9.91% | 7.84% | 241.12 | 235.21 |
| Dun/SPR-South | 10.89% | 9.59% | 299.57 | 177.24 |

The released-model pooled WAPE is **11.21808%**, versus **15.11099%** for the current 2025 model. This is a cross-year benchmark: 2019 has 8760 prepared local-hour cases; 2025 has 8651 eligible physical-hour AC cases. Generation, demand, controls, topology and solver physics differ. Pooled error combines overlapping interfaces and is not a statewide energy-balance metric. The available comparison supports lower downstate errors and higher overall current errors, but does not identify a causal effect of model changes.

## Literal release diagnostic retained

| Interface | Literal flow4Plot WAPE | Authors if.map WAPE |
|---|---:|---:|
| Dysinger East | 57.54% | 22.49% |
| West Central | 409.85% | 46.81% |
| Total East | 7.24% | 7.24% |
| Moses South | 86.43% | 8.99% |
| Central East | 9.63% | 9.63% |
| UpNY-Coned | 157.06% | 9.91% |
| Dun/SPR-South | 19.06% | 10.89% |

These columns use precisely the same 57-bus solves and 2019 inputs. The large differences expose a measurement-index inconsistency in the release, not an alternative physical model. No observation-driven fitting or branch-index replacement was made inside the authors' files.

The paper's Equation 11 and released helper instead normalize signed observed-minus-simulated error by the hourly positive interface limit. That is distinct from WAPE. West Central's 9999 positive-limit field is not a verified physical rating. Literal helper errors, author-map errors, empirical limit-normalized quantiles, MAE, RMSE and bias are all retained in the metrics CSV.

## Reproduction and limitations

The source check uses MATLAB R2026a, MATPOWER 8.1 legacy core and the pinned June 2019 reduction-toolbox mirror. The precise software revision used to create the published figure is unknown. The result is a verified reproduction of the available pinned code/data release, not a claim to recover the authors' undisclosed execution environment or reproduce Figure 5 bit-for-bit. DC convergence also does not certify AC/reactive, thermal or operational feasibility.

From the repository root:

```powershell
cd "C:\Users\Holiday\Desktop\npcc_ny_lite_package_fixed\WECC and NPCC Systems"
& 'C:/Program Files/MATLAB/R2026a/bin/matlab.exe' -batch "addpath('scripts/nygrid_released_2019_comparison'); check_unmodified_release"
python scripts/nygrid_released_2019_comparison/independent/recompute_released_metrics.py
python scripts/nygrid_released_2019_comparison/build_report.py
```

- [Fresh unmodified-source checks](output/nygrid_released_2019_comparison/fresh_author_release_checks.csv)
- [Fresh source-run receipt](output/nygrid_released_2019_comparison/fresh_author_release_receipt.json)
- [Independent annual rescore and provenance](output/nygrid_released_2019_comparison/independent/independent_released_2019_review.json)
- [Both measurement variants and all metrics](output/nygrid_released_2019_comparison/independent/released_2019_recomputed_metrics.csv)
- [Corrected baseline comparison](output/nygrid_released_2019_comparison/independent/released2019_vs_othermodel2025.csv)
- [Original author-file manifest](output/nygrid_2019/upstream_manifest.json)
- [Original full-year release-run verification](output/nygrid_2019/independent_dc_replay.json)

This additive correction preserves both the authors' files and all earlier model/evidence artifacts. The previously used derived 140-bus counterpart remains a separate historical research artifact and is excluded from this benchmark.
