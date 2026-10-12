"""Build the source-backed handoff for the sealed controlled experiment family."""
from pathlib import Path
import numpy as np
import pandas as pd
from common import NAMES,OUT,PARENT,ROOT,read,require

def build():
    a=pd.read_csv(OUT/'comparison/annual_metrics.csv').set_index(['scenario','interface'])
    monthly=pd.read_csv(OUT/'comparison/monthly_metrics.csv')
    physics=read(OUT/'validation/independent_load_interaction_validation.json')
    scoring=read(OUT/'validation/mapping_score_validation.json')
    matlab=read(OUT/'validation/matlab_validation.json')
    require(physics['passed'] and scoring['passed'] and matlab['passed'],'Validation is incomplete')
    modes=[('baseline','Baseline'),('niagara_legacy_bounded_outside_ab','Bounded legacy Niagara rule'),
           ('niagara_month_shape_literal_outside_ab','EIA monthly mean; baseline hourly shape'),
           ('load_original_B','Original Zone B load allocation'),
           ('mapping_independent_zone_cuts','Independent zone-cut operators')]
    western=['| Full-cohort experiment | Dysinger MAE (MW) | West Central MAE (MW) | Dysinger WAPE | West Central WAPE |',
             '|---|---:|---:|---:|---:|']
    for key,label in modes:
        d,w=a.loc[(key,NAMES[0])],a.loc[(key,NAMES[1])]
        western.append(f'| {label} | {d.mae_public_mw:.3f} | {w.mae_public_mw:.3f} | {d.wape_percent:.3f}% | {w.wape_percent:.3f}% |')
    all7=['| Interface | Baseline MAE | Bounded legacy MAE | EIA-mean MAE |','|---|---:|---:|---:|']
    for name in NAMES:
        v=[a.loc[(key,name),'mae_public_mw'] for key,_ in modes[:3]]
        all7.append(f'| {name} | {v[0]:.3f} | {v[1]:.3f} | {v[2]:.3f} |')
    niagara=read(OUT/'inputs/niagara_receipt.json')
    fixed=np.load(PARENT/'replay/paired_common_mask.npy',allow_pickle=False)
    hourly=pd.read_csv(OUT/'inputs/niagara_hourly_changes.csv.gz',nrows=0)
    # The source-quantity ledger remains the authoritative detailed lookup;
    # this document summarizes only independently reviewed aggregate findings.
    body=f'''# Controlled 2025 tests: Niagara, load allocation and western interface mapping

The controlled tests use **the same 8,651 physical 2025 hours and boundary flows in every scored case**. The bounded legacy Niagara rule yields only modest western MAE improvements; matching Niagara's source monthly mean produces no material annual improvement. Within-zone load redistribution has no effect on these two modeled gate totals. Independent operators reproduce the current gates exactly, but the true physical 2025 meter mapping remains unidentified.

These are conditional sensitivity results. No operating case is promoted, no interface observation is used to choose a target or parameter, and the unexplained residual is not automatically assigned to mapping error. Existing numerical artifacts and the annotation in the previous report are preserved.

## Matched results

All MW values are public-equivalent MW. Topology follows the same dated commissioning states. The Niagara rows below use the primary compensation pool outside Zones A/B.

{chr(10).join(western)}

The bounded legacy rule reduces Dysinger MAE by **3.992 MW (1.54%)** and West Central by **6.128 MW (2.39%)**. These changes are small compared with the remaining 255–250 MW errors. The EIA-monthly-mean case raises MAE by **1.232 / 1.266 MW**, while reducing RMSE slightly by **0.141 / 0.698 MW**; it is a mixed, small annual effect rather than a uniform worsening of every metric.

![Matched annual and monthly comparisons](output/nygrid_2025_western_counterfactuals/figures/matched_western_tests.png)

[Figure PDF](output/nygrid_2025_western_counterfactuals/figures/matched_western_tests.pdf) · [Figure SVG](output/nygrid_2025_western_counterfactuals/figures/matched_western_tests.svg) · [all 133 annual metric rows](output/nygrid_2025_western_counterfactuals/comparison/annual_metrics.csv) · [all 1,596 monthly rows](output/nygrid_2025_western_counterfactuals/comparison/monthly_metrics.csv)

## What was held fixed

The [experiment plan](output/nygrid_2025_western_counterfactuals/design/experiment_plan.json) and the three family plans were frozen before new scores were computed. The baseline is the current source-corrected 148-bus case at parent commit `8290ced`, with all four external regions on the same NYIS-reported actual-flow basis.

- Every scenario uses the exact same physical-hour mask; no hour is selected or excluded using interface error.
- All 28 external equivalents, the four original DC schedules, and the two observed northern Ontario P34 transfers remain fixed.
- Network R/X, taps, status chronology, generator identities and original capacity bounds remain fixed.
- Niagara tests preserve every load, St. Lawrence plant 2694, all pumped-storage/Lewiston output and all nonhydro generation. Equal and opposite changes to other conventional hydro preserve hourly statewide hydro generation and global balance.
- Load tests preserve all generation and each zone's hourly P and Q demand totals. Operator tests use identical injections, angles and branch flows.

Construction and scoring are separate commands. `run_experiments.py` builds and solves source-defined cases without opening internal observations; `--score-only` opens them only after the input and operator families are sealed. The [candidate catalog](output/nygrid_2025_western_counterfactuals/replay/candidate_catalog.json) preserves all candidates and the unscored infeasible hypotheses.

## Niagara dispatch tests

**Bounded legacy share.** The requested target is `0.8 × P63 hourly Hydro − fixed current St. Lawrence output`. It tests the legacy share mechanism on 2025 data, not a wholesale swap to every 2019 modeling assumption. The target is assigned to Robert Moses Niagara plant 2693; Lewiston pumped storage remains fixed. Compensation minimizes weighted changes from the current donor dispatch, using the original weights and unit bounds.

The literal request exceeds the frozen 2025 model's Niagara upper bound of **2,434.9 MW** in **277 hours (3.20%)**. Its largest request is **3,174.535 MW**, at `2025-06-23T23:00:00Z`. The bounded case explicitly adjusts that hypothesis by **739.635 MW** in the largest case. No raw measurement is clipped. Both literal variants remain saved as feasibility diagnostics and are **not power-flowed or scored on their smaller 8,374-hour feasible subset**.

**Monthly source mean.** Final EIA-923 plant-month energy divided by actual local-calendar hours supplies the requested mean. The baseline's normalized within-month shape is retained. The mean is imposed on the fixed qualified hours, which assumes those hours represent the full month's mean; this does not establish actual hourly dispatch or full-month energy. March has 743 physical hours and November has 721. A separately constrained construction is feasible without modifying the requested shape, so it reproduces the literal monthly construction to numerical precision; these are duplicate controls, not independent evidence.

| Robert Moses Niagara quantity on 8,651 hours | Baseline | Bounded legacy | EIA-mean shape |
|---|---:|---:|---:|
| Mean output, MW | 1,524.734 | 1,528.184 | 1,634.300 |
| Output standard deviation, MW | 313.683 | 465.117 | 336.255 |
| Mean absolute hourly change from baseline, MW | 0 | 157.816 | 109.566 |

The legacy rule mainly changes timing and variation, with only a **+3.450 MW** annual mean change. It improves Dysinger MAE in seven months but worsens it in five. For example, April MAE worsens by **149.29 MW**, while July improves by **60.53 MW**. The monthly-mean case improves December Dysinger MAE by **99.42 MW** but worsens April by **84.30 MW**. Neither alternative supplies a consistent correction throughout the year.

The primary donor pool has **314 conventional-hydro units outside A/B**. The all-other-HY sensitivity adds six Zone B units and none in Zone A. Dysinger is therefore unchanged between donor policies; West Central MAE becomes **249.868 MW** for bounded legacy and **257.483 MW** for the monthly case, only **0.331 / 0.111 MW** below the respective primary results. These are compensation-location effects, not evidence of actual Zone B dispatch.

[Niagara plan](output/nygrid_2025_western_counterfactuals/niagara_plan.json) · [input receipt](output/nygrid_2025_western_counterfactuals/inputs/niagara_receipt.json) · [eight-test input validation](output/nygrid_2025_western_counterfactuals/inputs/niagara_input_validation.json) · [hourly changes](output/nygrid_2025_western_counterfactuals/inputs/niagara_hourly_changes.csv.gz) · [monthly energy scope](output/nygrid_2025_western_counterfactuals/inputs/niagara_monthly_scope.csv)

## Load-allocation tests

The current baseline uses released `npcc_new.csv` load shares. Original `npcc.csv` Zone A shares are identical, so A-only is an exact no-op. Zone B changes from **21.13% at Rochester345 and 78.87% at Rochester115** to **100% at Rochester115**. The A+B case is exactly the B-only case. Zonal totals and all other inputs remain fixed.

Both western interfaces remain unchanged. Beyond these particular shares, an a priori linear proof spans every nonnegative redistribution over the eight retained A buses and three B buses, in all four topology states. Conservative maximum changes are **1.75e-12 MW for Dysinger** and **1.47e-12 MW for West Central**, i.e. numerical zero. Other interfaces can respond: the corresponding unrestricted-load bounds are 55.81 MW for Total East and 35.32 MW for Central East.

This rules out within-zone shares as a remedy for these two complete modeled cuts under the fixed controls. It does not rule out errors in zonal totals, actual zone assignments, embedded generation/pumping treatment, or nodal-load sensitivity of a differently defined physical NYISO gate.

[Load plan](output/nygrid_2025_western_counterfactuals/load_plan.json) · [input receipt](output/nygrid_2025_western_counterfactuals/inputs/load_receipt.json) · [source shares](output/nygrid_2025_western_counterfactuals/load_analysis/source_bus_load_weights.csv) · [extreme redistribution bounds](output/nygrid_2025_western_counterfactuals/load_analysis/extreme_within_zone_load_bounds.csv)

## Interface-mapping tests and the unresolved physical mapping

The baseline 148-bus operators are recovered on the full 191-bus network and compared with independently enumerated Zone A and A+B cuts, after explicit external-border removal. Both operator matrices are coefficient-for-coefficient equal. Their evaluated flows agree to numerical precision on all 8,651 hours. This establishes numerical and accounting consistency, not complete physical meter equivalence.

A negative control translates the original, known-wrong released 57-bus plotting formulas through exact branch lineage into the full network. Only the first two operator rows change. It produces **637.854 MW Dysinger MAE and 1,578.925 MW West Central MAE**. This demonstrates that the old plotting error is detectable; it is not a candidate repair and is not present in the preferred baseline. Charging-field differences in five reduced branches are recorded explicitly and do not enter the lossless DC law.

The source ledger lists ten physical Dysinger entries from 2019 and fourteen West Central entries from the dated 2014 definition. Neither provides a complete, certified circuit/meter-terminal crosswalk into this aggregate model for 2025. No physical alternative is emitted by guessing aliases or assigning zero to unmatched circuits. **The true physical mapping contribution is therefore not identified by these tests.** Needed evidence is the complete 2025 flowgate member list, signed metering terminal for each circuit, and an exact mapping into the retained or recoverable network, including post-2019 station/PAR changes.

[Mapping plan](output/nygrid_2025_western_counterfactuals/mapping/mapping_plan.json) · [mapping receipt](output/nygrid_2025_western_counterfactuals/mapping/mapping_receipt.json) · [physical coverage ledger](output/nygrid_2025_western_counterfactuals/mapping/physical_member_coverage.csv) · [literal-operator lineage](output/nygrid_2025_western_counterfactuals/mapping/literal_operator_exact_lineage.csv) · [operator-only results](output/nygrid_2025_western_counterfactuals/mapping/operator_replay_receipt.json)

## All seven interfaces and interaction checks

The three primary cases below all use the same cohort and external flows. Their donor policy is outside A/B. Values are MAE in public-equivalent MW.

{chr(10).join(all7)}

These effects belong to the entire Niagara-plus-donor redistribution. In particular, a Central East improvement is not a measured fraction of Central East error caused by Niagara.

All six full-cohort Niagara cases were also crossed with the original-B load allocation. Their predictions equal the sum of the separately computed changes to within **{physics['maximum_interface_interaction_error_model_mw']:.3g} model MW**. This is the expected affine behavior of fixed-topology DC power flow. Changes in MAE/WAPE interaction are properties of the loss function, not a newly identified physical interaction.

## Validation, preservation and reproduction

Independent validation checks **16 power-flow scenarios × 8,651 hours = 138,416 scenario-hours**, plus three operator-only comparisons. It verifies source/time/scale axes, all held-fixed injections and zonal demands, native bounds, direct 148-bus equations, reconstructed 191-bus equations, all seven operators, load nulls and interaction identities. Maximum full-network KCL error is **{physics['maximum_full191_KCL_error_model_mw']:.3g} model MW**. Five in-memory metadata mutations are rejected by the runner.

Fresh MATPOWER validation passes **{matlab['fresh_MATPOWER_snapshots']} predetermined snapshots** across all 16 scenarios, selected by source topology states and seasons rather than observed errors. Maximum branch disagreement is **{matlab['maximum_branch_error_model_mw']:.3g} model MW**, and maximum interface disagreement is **{matlab['maximum_interface_error_model_mw']:.3g} model MW**. An independent checker also rebuilds all operator-only outputs and all 133 annual plus 1,596 monthly metrics.

[Independent equations and interaction validation](output/nygrid_2025_western_counterfactuals/validation/independent_load_interaction_validation.json) · [independent mapping and score validation](output/nygrid_2025_western_counterfactuals/validation/mapping_score_validation.json) · [MATPOWER validation](output/nygrid_2025_western_counterfactuals/validation/matlab_validation.json) · [delivery manifest](output/nygrid_2025_western_counterfactuals/delivery_manifest.json)

From `C:\\Users\\Holiday\\Desktop\\npcc_ny_lite_package_fixed\\WECC and NPCC Systems`, the source builders are `build_niagara.py`, `build_load_allocation.py`, and the mapping builder under `scripts/nygrid_2025_western_counterfactuals/mapping`. Existing frozen plans must not be silently revised after scoring. To replay the sealed inputs:

```powershell
python scripts/nygrid_2025_western_counterfactuals/run_experiments.py
python scripts/nygrid_2025_western_counterfactuals/evaluate_operators.py
python scripts/nygrid_2025_western_counterfactuals/run_experiments.py --score-only
python scripts/nygrid_2025_western_counterfactuals/validate_load_interactions.py
python scripts/nygrid_2025_western_counterfactuals/validate_mapping_scores.py
matlab -batch "addpath('scripts/nygrid_2025_western_counterfactuals'); validate_matlab_counterfactuals"
```

For a read-only check of the delivered files and parent preservation, run `python scripts/nygrid_2025_western_counterfactuals/finalize_experiments.py --verify`. A deliberate rebuild requires refreshing dependent validations, figures, report and manifest. The previous report's existing annotation is retained unchanged; the original numerical model and its defaults are not overwritten.

These tests do not certify actual hourly plant dispatch, a complete physical 2025 gate mapping, AC/reactive/thermal feasibility, ramping, commitment or reservoir energy. They establish the response to declared source alternatives under fixed controls. The remaining western residual is still not uniquely attributable to one physical error source.
'''
    target=ROOT/'NYGRID_2025_WESTERN_CONTROLLED_TESTS.md';target.write_text(body,encoding='utf-8',newline='\n')
    print(target)

if __name__=='__main__':build()
