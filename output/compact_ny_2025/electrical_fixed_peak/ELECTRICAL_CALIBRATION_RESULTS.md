# Compact NY matched-snapshot electrical results

12/12 snapshots pass bounded AC constraints and independent fixed-input PF. Electrical baseline qualified: 1.

Scale policy: fixed_year_peak. A fixed year-specific summer-peak scale maps the reference peak to 10,902.2198 MW while preserving seasonal demand variation. Observed NYISO zonal MW and scheduled boundary P use the same year scale. Boundary Q=0 and bus landing splits are assumptions. Ten distinct scheduled channels include separate Cedars. The nested HQ_IMPORT_EXPORT record is excluded from the default total. A separate S1 sensitivity replaces HQ-NY with HQ_IMPORT_EXPORT without adding both; scheduled imports change by -104.237 benchmark MW.

2025 S1-S4 fit seven declared AC interface proxies. Mean normalized training generation is frozen before S5/S6 prediction. Heldout and all 2019 interface values are used only for scoring, never optimizer targets or generation priors. Generator observations are unavailable: interface agreement does not validate dispatch.

The seven operators remain conceptual/source-backed proxies with public completeness gaps. Total East is a partial F-G proxy; UPNY is six nonoverlapping local source circuits. Low fit residuals are calibration results, not exact-public-operator validation.

| Scenario | Qualified | MAE benchmark MW | Maximum benchmark MW |
|---|---:|---:|---:|
| S1_2025_SUMMER_PEAK_PUBLIC | 1 | 2.017 | 3.207 |
| S2_2025_WINTER_PEAK_PUBLIC | 1 | 1.180 | 2.028 |
| S3_2025_SHOULDER_LIGHT_LOAD_EXACT | 1 | 1.075 | 3.080 |
| S4_2025_HIGH_NYC_LI_LOAD_PUBLIC | 1 | 1.995 | 3.431 |
| S1_2019_SUMMER_PEAK_PUBLIC | 1 | 282.923 | 529.141 |
| S2_2019_WINTER_PEAK_PUBLIC | 1 | 674.264 | 1585.808 |
| S3_2019_SHOULDER_LIGHT_LOAD_PUBLIC | 1 | 294.068 | 916.450 |
| S4_2019_HIGH_NYC_LI_LOAD_PUBLIC | 1 | 287.778 | 685.974 |
| S5_2019_HIGH_TOTAL_EAST_PUBLIC | 1 | 417.168 | 1170.773 |
| S6_2019_LOW_TOTAL_EAST_PUBLIC | 1 | 239.432 | 359.854 |
| S5_2025_HIGH_TOTAL_EAST_PUBLIC | 1 | 284.372 | 500.849 |
| S6_2025_LOW_TOTAL_EAST_PUBLIC | 1 | 317.055 | 941.507 |

Normalized errors use max(100 MW, absolute scaled observation) as denominator; near-zero targets are flagged. Observation-scale flows are uniform mathematical rescalings, not a full-size physical network. No thermal validation or DLR-ready claim is made.
