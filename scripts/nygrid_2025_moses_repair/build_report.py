"""Build the Moses repair report and scientific comparison figure from final receipts.

Reads completed, versioned evidence only. Does not run PF or modify any input,
model, runtime, map, generation policy, or source-qualification mask.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'output/nygrid_2025_moses_repair'
RUN = BASE / 'annual/moses_repair_v1'
OUT = BASE / 'summary'
REPORT = ROOT / 'NYGRID_2025_MOSES_REPAIR.md'
ORDER = ['DYSINGER EAST', 'WEST CENTRAL', 'TOTAL EAST', 'MOSES SOUTH',
         'CENTRAL EAST - VC', 'UPNY CONED', 'SPR/DUN-SOUTH']
CONVENTION = 'legacy_signed_literal_from'


def record(path):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest,
            'bytes': path.stat().st_size}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def markdown_table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
                     ['| ' + ' | '.join(str(v) for v in row) + ' |' for row in rows])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    paths = {
        'metrics': RUN / 'comparison/public_interface_metrics.csv',
        'annual': RUN / 'annual_receipt.json',
        'accounting': RUN / 'validation/annual_input_accounting_review.json',
        'physics': RUN / 'validation/annual_physics_review.json',
        'scoring': RUN / 'comparison/scoring_receipt.json',
        'crosscheck': RUN / 'comparison/independent_scoring_crosscheck.json',
        'generation': BASE / 'generation/candidate_receipt.json',
        'generation_review': BASE / 'generation/independent_generation_review.json',
        'generation_policy': BASE / 'generation/generation_policy.json',
        'energy': BASE / 'generation/StLawrence_monthly_energy_ledger.csv',
        'boundary': BASE / 'boundary/boundary_verification_receipt.json',
        'PV20': BASE / 'boundary/PV20_source_receipt.json',
    }
    before = [record(p) for p in paths.values()]
    annual, accounting, physics, scoring, crosscheck, generation, generation_review, policy, boundary, pv20 = [
        read(paths[name]) for name in ['annual', 'accounting', 'physics', 'scoring', 'crosscheck',
                                      'generation', 'generation_review', 'generation_policy', 'boundary', 'PV20']]
    assert annual['completed'] and annual['policy_equation_qualified_hours'] == 8651
    assert accounting['completed'] and accounting['passed'] and physics['completed_annual_review'] and physics['passed']
    assert scoring['completed'] and scoring['passed'] and crosscheck['passed'] and generation_review['passed']
    assert not boundary['whole_2025_physical_Moses_meter_equivalence_verified']
    assert not policy['P32_or_interface_observations_read']
    assert generation['EIA_target_MWh'] == 6726939
    bindings = Counter(row['status'] for row in boundary['source_bindings'])
    assert bindings == {'verified': 15, 'assumed': 3, 'unresolved': 4}
    metrics = pd.read_csv(paths['metrics'])
    primary = metrics[(metrics.cohort == 'paired_current_baseline') & (metrics.convention == CONVENTION)]
    paired = primary[primary.period == 'annual']
    old = paired[paired.model == 'current_baseline'].set_index('interface').loc[ORDER]
    new = paired[paired.model == 'candidate'].set_index('interface').loc[ORDER]
    assert len(old) == len(new) == 7 and (old.hours == 8651).all() and (new.hours == 8651).all()
    monthly = primary[(primary.interface == 'MOSES SOUTH') & primary.period.str.startswith('month_')]
    old_month = monthly[monthly.model == 'current_baseline'].sort_values('period').reset_index(drop=True)
    new_month = monthly[monthly.model == 'candidate'].sort_values('period').reset_index(drop=True)
    assert len(old_month) == len(new_month) == 12
    assert np.array_equal(old_month.hours, new_month.hours) and new_month.hours.sum() == 8651
    energy = pd.read_csv(paths['energy']).sort_values('month')
    assert len(energy) == 12 and abs(energy.EIA_monthly_target_MWh.sum() - 6726939) < 1e-6
    assert np.max(abs(energy.monthly_energy_error_MWh)) < 1e-6
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    comparison = pd.DataFrame({'interface': ORDER, 'hours': new.hours.values,
        'baseline_MAE_public_MW': old.mae_public_MW.values, 'candidate_MAE_public_MW': new.mae_public_MW.values,
        'MAE_change_public_MW': new.mae_public_MW.values - old.mae_public_MW.values,
        'baseline_WAPE_percent': old.wape_percent.values, 'candidate_WAPE_percent': new.wape_percent.values,
        'baseline_bias_public_MW': old.bias_public_MW.values, 'candidate_bias_public_MW': new.bias_public_MW.values})
    comparison.to_csv(OUT / 'annual_paired_comparison.csv', index=False)
    monthly_comparison = pd.DataFrame({'month': np.arange(1, 13), 'hours': new_month.hours,
        'baseline_MAE_public_MW': old_month.mae_public_MW, 'candidate_MAE_public_MW': new_month.mae_public_MW,
        'baseline_WAPE_percent': old_month.wape_percent, 'candidate_WAPE_percent': new_month.wape_percent})
    monthly_comparison.to_csv(OUT / 'monthly_moses_comparison.csv', index=False)

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.titlesize': 12,
                         'axes.labelsize': 10, 'pdf.fonttype': 42, 'ps.fonttype': 42,
                         'axes.edgecolor': '#39424c', 'text.color': '#25303a', 'axes.labelcolor': '#25303a'})
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 6.4), gridspec_kw={'width_ratios': [1.12, 1]})
    fig.subplots_adjust(left=0.135, right=0.98, bottom=0.23, top=0.77, wspace=0.31)
    gray, blue = '#737c86', '#165e89'
    y = np.arange(7)
    a, b = axes
    bars_old = a.barh(y - 0.18, old.mae_public_MW, height=0.32, color='white', edgecolor=gray, linewidth=1.3,
                     label='Previous physical repair')
    bars_new = a.barh(y + 0.18, new.mae_public_MW, height=0.32, color=blue, label='Moses repair')
    for bars in [bars_old, bars_new]:
        a.bar_label(bars, fmt='%.1f', padding=4, fontsize=9)
    a.set_yticks(y, ORDER); a.invert_yaxis(); a.set_xlim(0, max(old.mae_public_MW.max(), new.mae_public_MW.max()) * 1.17)
    a.set_title('(a) Annual MAE across seven interfaces', loc='left', pad=14)
    a.set_xlabel('MAE (public MW)')
    x = np.arange(1, 13)
    b.plot(x, old_month.mae_public_MW, color=gray, linestyle='--', marker='s', markerfacecolor='white',
           linewidth=1.6, markersize=5, label='Previous physical repair')
    b.plot(x, new_month.mae_public_MW, color=blue, linestyle='-', marker='o', linewidth=1.8, markersize=5,
           label='Moses repair')
    b.set_xticks(x, month_names); b.set_xlim(0.7, 12.3); b.set_ylim(0, max(old_month.mae_public_MW.max(), new_month.mae_public_MW.max()) * 1.14)
    b.set_title('(b) Moses South MAE by month', loc='left', pad=14)
    b.set_xlabel('2025 local-calendar month'); b.set_ylabel('MAE (public MW)')
    for ax in axes:
        ax.set_axisbelow(True); ax.grid(axis='x' if ax is a else 'y', color='#e4e7ea', linewidth=0.7)
        ax.spines[['top', 'right']].set_visible(False)
    fig.suptitle('2025 interface comparison after the Moses generation and boundary repair', x=0.135, y=0.965,
                 ha='left', fontsize=15, fontweight='bold')
    fig.text(0.135, 0.91, 'Same 8,651 paired hours; unchanged source mask, public observations, gamma and primary terminal convention.', fontsize=10)
    fig.legend(handles=[bars_old, bars_new], labels=['Previous physical repair', 'Moses repair'],
               loc='upper left', bbox_to_anchor=(0.132, 0.89), ncol=2, frameon=False, fontsize=10)
    fig.text(0.135, 0.12, 'Moses South annual MAE: 118.821 → 108.945 MW. Total East: 471.551 → 499.304 MW.', fontsize=10)
    fig.text(0.135, 0.075, 'Equation-qualified predictions; 0 hours pass every operating limit. Physical P32 meter equivalence remains unverified.', fontsize=9, color='#4c5661')
    image = OUT / 'moses_repair_comparison.png'; pdf = OUT / 'moses_repair_comparison.pdf'
    fig.savefig(image, dpi=190, facecolor='white')
    fig.savefig(pdf, facecolor='white', metadata={'Title': '2025 Moses repair paired interface comparison',
        'Author': 'NYgrid model validation', 'Subject': 'Frozen 8651-hour diagnostic comparison; not physical P32 meter certification'})
    plt.close(fig)

    annual_rows = [[r.interface, f'{r.baseline_MAE_public_MW:.3f}', f'{r.candidate_MAE_public_MW:.3f}',
                    f'{r.MAE_change_public_MW:+.3f}', f'{r.baseline_WAPE_percent:.3f}', f'{r.candidate_WAPE_percent:.3f}']
                   for r in comparison.itertuples(index=False)]
    bias_rows = [[name, f'{old.loc[name,"bias_public_MW"]:+.6f}', f'{new.loc[name,"bias_public_MW"]:+.6f}'] for name in ORDER]
    energy_rows = [[month_names[int(r.month)-1], int(r.physical_hours), int(r.qualified_hours),
                    f'{r.EIA_monthly_target_MWh:,.0f}', f'{r.repaired_all_hour_StLawrence_MWh:,.0f}', int(r.hours_at_engineering_cap)]
                   for r in energy.itertuples(index=False)]
    monthly_rows = [[month_names[i], int(new_month.hours.iloc[i]), f'{old_month.mae_public_MW.iloc[i]:.3f}',
                     f'{new_month.mae_public_MW.iloc[i]:.3f}'] for i in range(12)]
    m0, m1 = old.loc['MOSES SOUTH'], new.loc['MOSES SOUTH']
    te0, te1 = old.loc['TOTAL EAST'], new.loc['TOTAL EAST']
    gain = 100 * (1 - m1.mae_public_MW / m0.mae_public_MW)
    loss = 100 * (te1.mae_public_MW / te0.mae_public_MW - 1)
    report = f'''# Moses South improves after a source-constrained generation and boundary repair

The completed 2025 replay reduces Moses South mean absolute error (MAE) from **{m0.mae_public_MW:.3f} to {m1.mae_public_MW:.3f} public MW ({gain:.2f}%)** on the same 8,651 hours as the previous physical-repair model. WAPE falls from **{m0.wape_percent:.4f}% to {m1.wape_percent:.4f}%**. This is a conditional, equation-qualified improvement: Moses South positive bias increases, Total East accuracy worsens, and **no hour passes every network operating limit**. Physical equivalence to the public P32 Moses South meter remains unverified.

This revision makes two source-supported changes: it reconstructs St. Lawrence generation under exact final-EIA monthly energy constraints, and explicitly routes the observed Sand Bar P34 boundary proxy into the northern pocket without changing the ISO-NE regional interchange total. The earlier parent 41 and parent 185/195 physical repairs are preserved. The generation policy and boundary sign were selected from source evidence before this comparison, without fitting their values to P32 errors. The combined replay does not separately identify the causal contribution of each repair.

![Two-panel comparison of all seven annual interface MAEs and monthly Moses South MAE](output/nygrid_2025_moses_repair/summary/moses_repair_comparison.png)

The [vector PDF figure](output/nygrid_2025_moses_repair/summary/moses_repair_comparison.pdf), [annual figure data](output/nygrid_2025_moses_repair/summary/annual_paired_comparison.csv), and [monthly figure data](output/nygrid_2025_moses_repair/summary/monthly_moses_comparison.csv) are reproducible from the final comparison CSV. All results below are fresh saved-run readbacks, completed on 2026-10-15; source documents retain their original dates.

## Generation repair: monthly energy is observed; hourly dispatch is reconstructed

Final EIA-923 plant 2694 HY net generation totals **6,726,939 MWh** in 2025. The candidate satisfies each of the 12 monthly totals over all physical hours in its New York calendar month, including the explicitly modeled energy of excluded hours. The maximum monthly energy error is **{generation_review['maximum_monthly_energy_error_MWh']:.3g} MWh**. It does not force the full monthly total onto the smaller PF-qualified subset.

EIA inventory supports 16 dated unit records, with 15 operating units in each month: unit 21 is operating in January–February while unit 26 is out of service; their status reverses from March through December. Unit 21 is appended as native generator row 1465 at model bus 48, preserving all original row identities. The upper bound **15 × 57 = 855 MW** uses operating-unit nameplate ratings as an engineering bound. It is not an observed hourly net capability or availability trace.

The plant profile is the unique unweighted minimum-squared-deviation reconstruction around the existing reconciled plant profile, subject to exact monthly energy and hourly feasible intervals. Dispatch among the 15 active equal-nameplate units is proportional to nameplate. Other HY units are redistributed by a bounded weighted least-squares projection using the frozen objective weights. These are declared reconstruction rules, not unit telemetry. The cap binds in many April–October hours, so monthly energy agreement alone does not validate the resulting hourly shape.

{markdown_table(['Month', 'Calendar hours', 'Qualified hours', 'EIA target MWh', 'Reconstructed MWh', 'Hours at 855 MW'], energy_rows)}

The current **reconciled** hourly NY HY total and total native PG are preserved on every qualified hour, as are other native fuels, pumped-storage positive-generation profiles, HQ, load, existing Ontario PAR/DC targets, and regional net-import targets. Raw P63 Hydro is a different series: the previous reconciled total differs from it by mean **{generation['raw_P63_difference']['mean_model_minus_P63']:.6f} MW** and MAE **{generation['raw_P63_difference']['MAE']:.6f} MW**. Exact preservation of raw P63 is not claimed.

All 109 previously excluded hours remain excluded: six retain available reconciled targets; 93 use the frozen HY prior and observed P63 total; ten P63-gap hours use explicitly declared bracketed linear interpolation only for the latent energy ledger. The [generation policy](output/nygrid_2025_moses_repair/generation/generation_policy.json), [monthly ledger](output/nygrid_2025_moses_repair/generation/StLawrence_monthly_energy_ledger.csv), [candidate receipt](output/nygrid_2025_moses_repair/generation/candidate_receipt.json), [independent generation review](output/nygrid_2025_moses_repair/generation/independent_generation_review.json), and [excluded-hour energy sensitivity](output/nygrid_2025_moses_repair/generation/excluded_hour_energy_sensitivity.csv) distinguish these constraints and assumptions.

## Northern boundary: missing routing is repaired, while meter equivalence remains conditional

The 2024 NYISO MS24 study's Figure 2 documents the North NYCA pocket connections to HQ, Cedars, Ontario PAR33/34, PV20 toward ISO-NE, and seven Moses South paths to Main NYCA. Together with the seasonal definitions, it supports PV20 as a separate D-to-N path: it contributes to Central East and Total East and is absent from the seven-term Moses South list. The baseline aggregate northern cut contained model parents 46/51/52 and the prescribed HQ/Ontario transfers but no explicit PV20 injection. This is structural evidence for the missing boundary component, not a complete bus-level injection or physical-meter crosswalk.

Native P34 PTID 325270, Sand Bar PAR PS01, contains 105,998 observations and covers 8,673 complete hours, including all 8,651 qualified model hours. Its mean on the qualified cohort is **−75.9885 public MW** under the current diagram's positive direction toward Plattsburgh/NY; the negative mean therefore denotes net export from NY under that convention. The source series is inserted at aggregate Plattsburgh bus 49 as generator row **1466**, with fixed P, **Q = 0**, Pmin = Pmax, no native-generation membership, no voltage regulation, and no external loss-balancing share. The existing ISO-NE generation pool receives the opposite adjustment. Each hour preserves:

`ISO_NE_total_import = PV20_proxy_import + ISO_NE_nonPV20_import_target`.

This is a boundary injection with six existing DC records retained; it is not a new DC line or an invented physical AC corridor. No Sand Bar bus, impedance, conductor rating, or PAR tap angle is manufactured.

The [boundary verification receipt](output/nygrid_2025_moses_repair/boundary/boundary_verification_receipt.json) records **22 bindings: 15 verified, 3 assumed, and 4 unresolved**. Its linked primary-source register is the documentary evidence ledger. The [P34 extraction receipt](output/nygrid_2025_moses_repair/boundary/PV20_source_receipt.json), [hourly proxy](output/nygrid_2025_moses_repair/boundary/PV20_hourly_source.csv), and [ISO-NE disaggregation contract](output/nygrid_2025_moses_repair/boundary/ISO_NE_PV20_disaggregation_contract.csv) provide numeric provenance.

The current PAR diagram establishes the sign direction, but it lacks a dated 2025 effective note; applying that sign throughout 2025 remains an assumption. The physical PV20 gate is at Plattsburgh, while the observed meter is at Sand Bar beyond South Hero. The required physical identity is:

`PV20_Platt_import = P34_SandBar_toward_Platt − SouthHero_net_load − intervening_real_losses + bypass_or_unmetered_parallel_transfer`.

South Hero load is documented. Its feeder 29-1A planning peak of 6.66 MVA is neither an hourly total-substation net-load series nor a full bound on meter error. The engineering proxy omits these intervening terms; it does not establish that they are physically zero. A complete dated pocket load/generator/loss census, terminal mapping, bypass history and P32 weights remain unresolved.

NYPA's formal filings establish **HA2 energization on October 13, 2025**, and **HA1 energization on March 27, 2026**. Thus, the winter planning definition cannot establish HA1 operation in 2025. Neither filing supplies the exact P32 switch hour or full intermediate topology; this repair does not infer a simultaneous seasonal meter cutover. The distinction between these documentary dates and measurement-effective intervals is preserved in the source receipt.

## Paired annual and monthly results

The comparator is the completed `physical_repair_v1` model, with 8,651 qualified hours, rather than the older 8,170-hour pre-repair baseline. The clock, source mask, observations, gamma and primary `legacy_signed_literal_from` operator are frozen. Public predictions are aggregate model MW divided by gamma once. Physical currents remain model amperes and are never divided by gamma. WAPE is `100 × sum(abs(prediction − observation)) / sum(abs(observation))`, evaluated over exactly the displayed cohort.

{markdown_table(['Interface', 'Previous MAE MW', 'Candidate MAE MW', 'MAE change MW', 'Previous WAPE %', 'Candidate WAPE %'], annual_rows)}

Total East MAE worsens by **{loss:.2f}%**. The UPNY MAE change is only **{new.loc['UPNY CONED','mae_public_MW']-old.loc['UPNY CONED','mae_public_MW']:+.6f} MW**; SPR/DUN-SOUTH is unchanged to the shown precision. MAE improvements do not imply bias improvements. Moses South signed mean bias rises from **{m0.bias_public_MW:+.6f} to {m1.bias_public_MW:+.6f} MW**:

{markdown_table(['Interface', 'Previous bias MW', 'Candidate bias MW'], bias_rows)}

Monthly Moses South MAE is lower in ten months but higher in September and November. The largest reductions occur in June and July. This is a paired descriptive result; it does not certify hourly St. Lawrence dispatch, establish a meter operator, or attribute the gain separately to the two simultaneous changes.

{markdown_table(['Month', 'Paired hours', 'Previous MAE MW', 'Candidate MAE MW'], monthly_rows)}

The [full metrics](output/nygrid_2025_moses_repair/annual/moses_repair_v1/comparison/public_interface_metrics.csv) retain all seven interfaces, annual/monthly and post-Dover periods, actual success cohorts, and all three predeclared terminal conventions. No alternate convention is selected by best fit. The [scoring receipt](output/nygrid_2025_moses_repair/annual/moses_repair_v1/comparison/scoring_receipt.json) explicitly marks physical P32 membership and the numerical-header-as-MW interpretation as uncertified. These remain diagnostic comparisons.

## Full-year equation validation and remaining physical limits

The annual replay attempted and converged on all **8,651 source-qualified hours**, with no exceptions, no lost baseline successes, and no additional source-qualified hours. All 8,760 clock rows are retained. Runtime was **{annual['elapsed_seconds']:.3f} seconds**. The saved final [annual receipt](output/nygrid_2025_moses_repair/annual/moses_repair_v1/annual_receipt.json) is completion evidence; earlier files labeled `partial_` are intermediate inspections.

The independent [input/accounting reader](output/nygrid_2025_moses_repair/annual/moses_repair_v1/validation/annual_input_accounting_review.json) validates compiled native/HQ/boundary profiles, finite capability metadata, fixed P/Q, loss ownership, external increments, zonal-load closure and regional imports. Maximum deviation from preserved baseline input constraints is **{accounting['maximum_independent_errors']['baseline_fixed_input_preservation_MW']:.3g} MW**, and from baseline regional net-import targets **{accounting['maximum_independent_errors']['baseline_regional_import_target_MW']:.3g} MW**. The explicit boundary P/Q deviation is exactly zero.

The separate [raw-physics reader](output/nygrid_2025_moses_repair/annual/moses_repair_v1/validation/annual_physics_review.json) reconstructs both-terminal complex power and currents from voltage, R/X/B, taps and phase shifts, checks nodal P/Q balance including the six DC records and the new boundary row, rebuilds passive-node voltage recovery, and verifies material I-squared-R loss. Maximum branch-power discrepancy is **{physics['maximum_recomputation_errors']['branch_complex_power_MVA']:.3g} MVA**, maximum nodal P/Q residual is **{physics['maximum_recomputation_errors']['nodal_P_MW']:.3g} MW / {physics['maximum_recomputation_errors']['nodal_Q_MVAr']:.3g} MVAr**, and full-voltage recovery discrepancy is **{physics['maximum_recomputation_errors']['full_voltage_lift_pu']:.3g} pu**. The independent [scoring crosscheck](output/nygrid_2025_moses_repair/annual/moses_repair_v1/comparison/independent_scoring_crosscheck.json) matches 28 raw-reader metric rows and direct WAPE recomputation exactly.

Parent 41 R/X/B and thermal realization, parent 185/195 branch parameters, and all fixed-reactor placements remain unchanged from the previous physical repair. Target 185 and 195 voltage violations remain zero across the full cohort; their voltage ranges are **1.020000–1.039389 pu** and **1.006566–1.046987 pu**. Parent 41 mean model loss changes **2.364978 → 2.356207 MW** with the dispatch change; this is not another impedance repair.

System-wide operating violations remain substantial: **8,651 overvoltage hours, 599 undervoltage hours, 8,651 hours with generator Q violations, 8,651 with assumed generator S violations, and 4,793 with branch MVA violations**. Overall voltage spans **0.841226–1.076098 pu**. Parent 41 still exceeds its declared hardware-current limit in **2,712 hours**. Consequently **0 hours pass the full operating gate**. Equation closure and recovery are established; full operating feasibility, physical P32 meter equivalence, and exact historical hourly generation are not.

## Reproduction and use

Use the [portable delivery instructions](output/nygrid_2025_moses_repair/delivery/docs/START_HERE.md) for the model API and limitations. The [data dictionary](output/nygrid_2025_moses_repair/delivery/docs/DATA_DICTIONARY.md) documents `model.source_model_commit`, `model.moses_source_repair`, the appended boundary row and capability conventions. The [annual replay README](scripts/nygrid_2025_moses_repair/annual/README.md) contains exact working-directory and command instructions, immutable baseline/candidate bundles, source-selected preflight checks, monthly checkpoints and independent reader commands. Keep these source metadata with the model; provenance is not a physical-meter certification.

To rebuild this report and both figure exports from the completed evidence, run:

```powershell
cd 'C:\\Users\\Holiday\\Desktop\\npcc_ny_lite_package_fixed\\WECC and NPCC Systems'
& '.\\tmp\\nygrid_2025_inputs_runtime_20261010\\Scripts\\python.exe' scripts/nygrid_2025_moses_repair/build_report.py
```

The [report receipt](output/nygrid_2025_moses_repair/summary/report_receipt.json) records input/output hashes, cohort checks and source limitations. No PF, source correction, policy refit, runtime modification or map rebuild occurs during report generation.
'''
    REPORT.write_text(report, encoding='utf-8')
    assert before == [record(p) for p in paths.values()], 'Report build modified an input.'
    links = re.findall(r'\]\(([^)]+)\)', report)
    missing = [link for link in links if not link.startswith(('https://', 'http://'))
               and link != 'output/nygrid_2025_moses_repair/summary/report_receipt.json' and not (ROOT / link).exists()]
    allowed_pending = 'output/nygrid_2025_moses_repair/delivery/docs/START_HERE.md'
    assert set(missing) <= {allowed_pending}, missing
    outputs = [REPORT, image, pdf, OUT / 'annual_paired_comparison.csv', OUT / 'monthly_moses_comparison.csv']
    receipt = {'passed': True, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'complete_annual_evidence': True, 'source_qualified_hours': 8651, 'paired_hours': 8651,
        'full_operating_qualified_hours': 0, 'interfaces': ORDER, 'primary_convention': CONVENTION,
        'source_binding_counts': dict(bindings), 'physical_P32_meter_equivalence_verified': False,
        'hourly_StLawrence_is_reconstruction': True, 'raw_P63_exact_preservation_claimed': False,
        'full_calendar_EIA_energy_MWh': 6726939, 'all_inputs_unchanged': True,
        'pending_packaging_links': missing, 'figure_visual_inspection': 'pending independent visual inspection',
        'inputs': before, 'outputs': [record(p) for p in outputs], 'producer': record(Path(__file__))}
    (OUT / 'report_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'report': str(REPORT), 'figure': str(image),
                      'source_binding_counts': dict(bindings), 'pending_packaging_links': missing}))


if __name__ == '__main__':
    main()
