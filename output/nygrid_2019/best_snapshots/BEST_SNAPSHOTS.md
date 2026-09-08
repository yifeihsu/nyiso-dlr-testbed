# Best-performing 2019 NYgrid snapshots

The best snapshot is **January 08, 2019 at 15:00 New York local time**. Its pooled proportional error is **2.0321%**, and every individual interface is within **4.07%** of observed flow. It ranks first both by pooled proportional error and by minimizing the worst individual percentage error.

The selection uses the frozen 57-bus NYgrid DC results with the previously corrected interface measurements. All 8,760 snapshots, each with seven interfaces, were ranked by `100 * sum(abs(model - observed)) / sum(abs(observed))`, with earlier timestamp breaking any tie. No model or dispatch was changed and no additional power-flow solve was required. The selected three hours have no interpolated or fall-DST-ambiguous interface observations.

## Best snapshot: observed and modeled flows

| Interface | Observed MW | Model MW | Absolute error MW | Actual-flow error |
|---|---:|---:|---:|---:|
| Dysinger East | 1471.68 | 1467.33 | 4.34 | 0.30% |
| West Central | 844.62 | 875.31 | 30.69 | 3.63% |
| Total East | 4738.22 | 4856.35 | 118.14 | 2.49% |
| Moses South | 1996.77 | 2078.01 | 81.23 | 4.07% |
| Central East | 2725.36 | 2772.48 | 47.13 | 1.73% |
| UpNY-Coned | 2106.42 | 2153.15 | 46.74 | 2.22% |
| Dun/SPR-South | 2422.56 | 2419.48 | 3.08 | 0.13% |

Per-interface percentage error is `100 * abs(model - observed) / abs(observed)`. It uses actual flow, not the paper's positive-limit denominator. The signed residual (model minus observed), paper-style percentage, and raw input-quality counts are retained in the CSV.

## Three lowest pooled-error snapshots

| Rank | 2019 New York local time | Pooled proportional error | Mean absolute error | Largest interface percentage error |
|---|---|---:|---:|---:|
| 1 | 2019-01-08 15:00 | 2.0321% | 47.34 MW | 4.07% |
| 2 | 2019-10-30 12:00 | 2.1446% | 43.15 MW | 539.20% |
| 3 | 2019-10-10 16:00 | 2.1532% | 40.44 MW | 14.12% |

Every cell below shows absolute MW error followed by actual-flow percentage error.

| Interface | #1: Jan 8, 15:00 | #2: Oct 30, 12:00 | #3: Oct 10, 16:00 |
|---|---:|---:|---:|
| Dysinger East | 4.34 MW / 0.30% | 3.03 MW / 0.56% | 54.29 MW / 8.52% |
| West Central | 30.69 MW / 3.63% | 45.48 MW / 539.20% | 24.76 MW / 14.12% |
| Total East | 118.14 MW / 2.49% | 6.29 MW / 0.16% | 10.40 MW / 0.28% |
| Moses South | 81.23 MW / 4.07% | 90.22 MW / 5.00% | 24.80 MW / 1.67% |
| Central East | 47.13 MW / 1.73% | 105.41 MW / 5.20% | 29.90 MW / 1.54% |
| UpNY-Coned | 46.74 MW / 2.22% | 21.35 MW / 0.88% | 110.33 MW / 4.79% |
| Dun/SPR-South | 3.08 MW / 0.13% | 30.30 MW / 0.91% | 28.59 MW / 0.98% |

On October 30 at 12:00, West Central reverses direction: observed -8.435 MW versus modeled 37.046 MW. The 45.48-MW mismatch is 539.20% of that small observed flow. A low pooled error can therefore conceal a poor individual interface result.

The [separate minimax ranking](top_three_minimax_snapshots.csv) identifies the three hours with the lowest worst-interface percentage error: Jan 08 at 15:00 (4.07% worst-interface error); Sep 02 at 13:00 (4.27% worst-interface error); Feb 01 at 15:00 (5.53% worst-interface error). This is a different explicit selection criterion, not an undisclosed replacement of the primary ranking.

These are deliberately selected best-case historical examples, not representative or held-out validation. The previous full-year pooled error remains **11.22%**. The original DC method does not enforce operating bounds; low interface error does not establish AC or thermal feasibility.

Run `python scripts/nygrid_2019/select_best_snapshots.py` from the repository root to regenerate the ranking and tables. The existing NYISO source-quality CSV can be regenerated with the prior source-audit workflow if absent. All original annual artifacts remain unchanged.
