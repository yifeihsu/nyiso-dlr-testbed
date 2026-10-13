"""Assemble the fixed-cohort CENTRAL EAST diagnosis from completed experiments."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_centraleast_diagnosis'
SUMMARY = OUT / 'summary'


def record(path):
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def table(rows, headings):
    return '\n'.join(['| ' + ' | '.join(headings) + ' |', '| ' + ' | '.join(['---'] * len(headings)) + ' |'] +
                     ['| ' + ' | '.join(map(str, r)) + ' |' for r in rows])


def main():
    SUMMARY.mkdir(parents=True, exist_ok=True)
    saved_path = ROOT / 'output/nygrid_2025_acpf_profile_audit/comparison/comparison_arrays.npz'
    bridge_path = OUT / 'experiments/annual_DC_bridge/annual_DC_bridge_arrays.mat'
    loss_path = OUT / 'experiments/annual_loss_loaded_DCF/annual_loss_loaded_arrays.mat'
    saved = np.load(saved_path, allow_pickle=False)
    bridge = loadmat(bridge_path, simplify_cells=True)
    loss = loadmat(loss_path, simplify_cells=True)
    for relative in ['experiments/annual_DC_bridge/annual_DC_bridge_receipt.json',
                     'experiments/annual_loss_loaded_DCF/annual_loss_loaded_receipt.json']:
        proof = json.loads((OUT / relative).read_text())
        assert proof['completed'] and proof['passed']
    q = saved['ACPF_comparison_cohort'].astype(bool)
    assert q.sum() == 8494 and np.array_equal(q, bridge['cohort'].astype(bool)) and np.array_equal(q, loss['cohort'].astype(bool))
    hours = saved['hour_index']; times = saved['timestamp_utc'].astype(str); gamma = float(saved['gamma'])
    for m in [bridge, loss]:
        assert np.array_equal(m['hour_index'], hours) and np.array_equal(np.asarray(m['timestamp_utc']).astype(str), times)
        assert float(m['gamma']) == gamma and np.asarray(m['audit_passed'])[q].all()
    assert saved['interface_names'][4] == 'CENTRAL EAST - VC'
    y = saved['observed'][:, 4]
    p = {
        'original_network_DC': saved['frozen_DC'][:, 4],
        'AC_network_DC': bridge['interface_model_MW'][:, 4, 0] / gamma,
        'AC_network_DC_half_losses': loss['interface_model_MW'][:, 4, 0] / gamma,
        'AC_network_AC': saved['legacy_signed_literal_from'][:, 4],
        'AC_network_DC_from_losses': loss['interface_model_MW'][:, 4, 1] / gamma,
        'AC_network_DC_to_losses': loss['interface_model_MW'][:, 4, 2] / gamma,
        'restore_224_X_DC': bridge['interface_model_MW'][:, 4, 1] / gamma,
        'restore_41_X_DC': bridge['interface_model_MW'][:, 4, 2] / gamma,
        'restore_all_33_X_DC': bridge['interface_model_MW'][:, 4, 3] / gamma,
    }
    assert all(np.isfinite(v[q]).all() for v in p.values()) and np.isfinite(y[q]).all()
    assert np.max(np.abs(p['AC_network_AC'][q] - loss['baseline_AC_interface_model_MW'][q, 4] / gamma)) < 1e-7
    month = pd.to_datetime(times, utc=True).tz_convert('America/New_York').month.to_numpy()
    rows = []
    for period, mask in [('annual', q)] + [(f'month_{m:02d}', q & (month == m)) for m in range(1, 13)]:
        for name, value in p.items():
            e = value[mask] - y[mask]
            rows.append(dict(period=period, stage=name, hours=int(mask.sum()), observed_mean_public_MW=float(y[mask].mean()),
                             observed_mean_absolute_public_MW=float(np.abs(y[mask]).mean()), mean_flow_public_MW=float(value[mask].mean()),
                             bias_public_MW=float(e.mean()), mae_public_MW=float(np.abs(e).mean()),
                             rmse_public_MW=float(np.sqrt(np.mean(e**2))), wape_percent=float(100*np.abs(e).sum()/np.abs(y[mask]).sum())))
    metrics = pd.DataFrame(rows); metrics.to_csv(SUMMARY / 'stage_metrics.csv', index=False)
    annual = metrics[metrics.period == 'annual'].set_index('stage')
    construction = p['AC_network_DC'] - p['original_network_DC']
    loss_effect = p['AC_network_DC_half_losses'] - p['AC_network_DC']
    remainder = p['AC_network_AC'] - p['AC_network_DC_half_losses']
    total = p['AC_network_AC'] - p['original_network_DC']
    assert np.max(abs((construction + loss_effect + remainder - total)[q])) < 1e-8
    impact224 = p['AC_network_DC'] - p['restore_224_X_DC']
    cohort = pd.DataFrame(dict(hour_index=hours, timestamp_utc=times, fixed_cohort=q, observed_public_MW=y, **p,
                              construction_delta_public_MW=construction, half_loss_delta_public_MW=loss_effect,
                              remaining_delta_public_MW=remainder, total_delta_public_MW=total))
    cohort.to_csv(SUMMARY / 'hourly_stage_comparison.csv', index=False)
    stats = dict(passed=True, created_utc=datetime.now(timezone.utc).isoformat(), baseline_HEAD='6dcc77f071a9ce4aaaa2fcba9a9aabc15f7d5dbc',
        hours=8494, source_qualified_hours=8651, matched_cohort_selected_before_diagnostics=True,
        construction_mean_delta_public_MW=float(construction[q].mean()), loss_loaded_mean_delta_public_MW=float(loss_effect[q].mean()),
        remaining_mean_delta_public_MW=float(remainder[q].mean()), remaining_MAE_public_MW=float(abs(remainder[q]).mean()),
        remaining_maximum_absolute_public_MW=float(abs(remainder[q]).max()), total_mean_delta_public_MW=float(total[q].mean()),
        parent224_X_restoration_mean_reduction_public_MW=float(impact224[q].mean()),
        parent224_share_of_mean_construction_displacement_percent=float(100*impact224[q].mean()/construction[q].mean()),
        half_loss_reconstruction_share_of_mean_same_network_AC_DC_displacement_percent=float(100*loss_effect[q].mean()/(loss_effect[q]+remainder[q]).mean()),
        WAPE_original_DC_percent=float(annual.loc['original_network_DC','wape_percent']),
        WAPE_AC_network_DC_percent=float(annual.loc['AC_network_DC','wape_percent']),
        WAPE_loss_loaded_DC_percent=float(annual.loc['AC_network_DC_half_losses','wape_percent']),
        WAPE_AC_percent=float(annual.loc['AC_network_AC','wape_percent']),
        WAPE_construction_step_percentage_points=float(annual.loc['AC_network_DC','wape_percent']-annual.loc['original_network_DC','wape_percent']),
        WAPE_same_network_AC_step_percentage_points=float(annual.loc['AC_network_AC','wape_percent']-annual.loc['AC_network_DC','wape_percent']),
        mean_baseline_AC_loss_model_MW=float(np.asarray(loss['baseline_AC_loss_MW'])[q].mean()),
        nonunique_allocation_mean_effect_public_MW=[float((p[k]-p['AC_network_DC'])[q].mean()) for k in ['AC_network_DC_to_losses','AC_network_DC_from_losses']],
        voltage_and_angle_remainder_is_not_unique_causal_decomposition=True,
        loss_loaded_DC_uses_solved_AC_losses=True, loss_reconstruction_not_independent_forecast=True,
        no_physical_meter_or_impedance_truth_established=True, no_production_model_changes=True,
        source_receipts=[record(x) for x in [saved_path, bridge_path, loss_path, Path(__file__)]])
    (SUMMARY / 'diagnosis_summary.json').write_text(json.dumps(stats, indent=2) + '\n', encoding='utf-8')

    # Scientific figure: matched cohort, signed bias and calendar trend.
    order = ['original_network_DC','AC_network_DC','AC_network_DC_half_losses','AC_network_AC']
    colors = {'original_network_DC':'#6b7280','AC_network_DC':'#3d6eae','AC_network_DC_half_losses':'#a27026','AC_network_AC':'#bc4b3c'}
    labels = ['Original DC','DC, AC-network X','DC + solved AC losses','Current AC']
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,
                         'axes.labelcolor':'#202938','text.color':'#202938','xtick.color':'#374151','ytick.color':'#374151'})
    fig, ax = plt.subplots(1,2,figsize=(13.7,5.8),gridspec_kw={'width_ratios':[1,1.13]})
    vals = [annual.loc[k,'bias_public_MW'] for k in order]
    ax[0].bar(np.arange(4), vals, color=[colors[k] for k in order], width=.65, zorder=3)
    ax[0].axhline(0,color='#384152',lw=1)
    ax[0].set_xticks(np.arange(4),['Original\nDC','DC on AC\nnetwork','DC + solved\nAC losses','Current\nAC'])
    ax[0].set_ylabel('Mean signed error (public MW)'); ax[0].set_ylim(-425,940)
    ax[0].set_title('The bias changes sign, then grows',loc='left',fontweight='bold',pad=17)
    for i,v in enumerate(vals):
        ax[0].text(i,v+(22 if v>0 else -25),f'{v:+.1f}',ha='center',va='bottom' if v>0 else 'top',fontsize=11,fontweight='bold')
    styles = [(':','o'),('-','s'),('--','D'),('-','o')]
    for name,label,(line,marker) in zip(order,labels,styles):
        d=metrics[(metrics.stage==name)&(metrics.period!='annual')]
        ax[1].plot(range(1,13),d.wape_percent,color=colors[name],ls=line,marker=marker,ms=4,lw=1.8,label=label)
    ax[1].set_xticks(range(1,13),['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'])
    ax[1].set_ylabel('Monthly WAPE (%)');ax[1].set_ylim(bottom=0)
    ax[1].set_title('The discrepancy persists throughout 2025',loc='left',fontweight='bold',pad=17)
    ax[1].legend(frameon=False,fontsize=9,ncol=2,loc='upper left')
    for a in ax:a.grid(axis='y',color='#e4e7eb',lw=.65,zorder=0);a.set_axisbelow(True)
    fig.suptitle('CENTRAL EAST–VC: separating network redesign from AC loss supply',x=.055,ha='left',fontsize=16,fontweight='bold',y=.99)
    fig.text(.055,.927,'Same 8,494 matched hours. Diagnostic loss reconstruction uses losses from the solved AC model.',fontsize=10,color='#5a6575')
    fig.text(.055,.025,'Receiving-side convention; original observations and aggregate power scaling preserved. These are synthetic-model diagnostics.',fontsize=9,color='#5a6575')
    fig.subplots_adjust(left=.07,right=.985,bottom=.18,top=.80,wspace=.31)
    fig.savefig(SUMMARY/'centraleast_diagnosis.png',dpi=180,facecolor='white')
    fig.savefig(SUMMARY/'centraleast_diagnosis.svg',facecolor='white')
    plt.close(fig)

    display_names = ['Original network, DC','AC network parameters, DC','AC network, DC plus half-end AC losses','Current AC solution']
    stage_rows = [[label,f"{annual.loc[k,'mean_flow_public_MW']:.2f}",f"{annual.loc[k,'bias_public_MW']:+.2f}",f"{annual.loc[k,'wape_percent']:.4f}%"] for k,label in zip(order,display_names)]
    replacement = float(annual.loc['restore_224_X_DC','wape_percent'])
    report = f'''# Why CENTRAL EAST–VC WAPE increased from DC to AC

The increase is a systematic switch from underprediction to overprediction. Two effects explain almost all of the mean flow change: **reactance-driven rerouting adds {stats['construction_mean_delta_public_MW']:.2f} public MW**, and **a reconstruction that explicitly supplies the solved AC losses adds {stats['loss_loaded_mean_delta_public_MW']:.2f} public MW**. The remaining mean difference is {stats['remaining_mean_delta_public_MW']:.2f} MW. The observed hourly benchmark, cohort, interface signs and compact reduction do not explain the increase.

The earlier DC and AC results used different network parameterizations. A same-network DC intermediate is therefore necessary to separate network construction from AC effects. All results below use the **same 8,494 hours** and the inherited receiving-side CENTRAL EAST functional. Source data and all production model/evidence files remain unchanged; these are separate diagnostic cases, with no OPF or observation fitting.

## Reproduced change and controlled comparison

{table(stage_rows,['Stage','Mean flow, public MW','Mean error, public MW','WAPE'])}

The public observed mean is {y[q].mean():.2f} MW; the mean absolute observed flow, which supplies the WAPE denominator, is {abs(y[q]).mean():.2f} MW. WAPE is `100 * sum(abs(model - observed)) / sum(abs(observed))`, not an average of hourly percentages.

Construction moves the signed error from −291.70 to +308.62 MW but raises WAPE by only **{stats['WAPE_construction_step_percentage_points']:.4f} percentage points**, because the error changes sign. Moving from that same-network DC solution to AC adds **{stats['WAPE_same_network_AC_step_percentage_points']:.4f} percentage points**. Consequently, shares of mean flow displacement must not be described as shares of the WAPE increase.

![CENTRAL EAST diagnosis](output/nygrid_2025_centraleast_diagnosis/summary/centraleast_diagnosis.png)

The original DC score over all 8,651 source-qualified hours is 19.0256%, versus 18.5268% on the matched 8,494 hours. Excluding the 157 failed-AC hours slightly improves the DC score; it cannot account for the matched-cohort 26.5091-point increase. The compiled public CE series was also independently reconstructed from the original P32 archives, including the clock rewind and hourly aggregation. [Measurement/source evidence](output/nygrid_2025_centraleast_diagnosis/measurement/raw_source_check.json).

## 1. A parallel route was substantially weakened

The CENTRAL EAST comparison uses original signed branch rows `[-33, -36, -40, -42]`, oriented E→F. Their total reactances are unchanged. Series sections preserve those totals, and the recovered original-terminal operator reproduces the archived DC functional. The recently built 148-bus AC reduction also reproduces the detailed AC results to numerical precision.

The consequential change occurs on **row 224, Gilboa–Buchanan**, a parallel E→G path. It is included in TOTAL EAST but is absent from CENTRAL EAST. Its 100-MVA-base reactance increases from **0.0147 to 0.055458 pu**, a **3.7726-fold increase**, during synthetic conductor construction. The stronger impedance on that bypass redirects flow toward the CENTRAL EAST routes.

Across all 8,494 hours, restoring only row 224's former X in the DC diagnostic removes **{stats['parent224_X_restoration_mean_reduction_public_MW']:.2f} MW**, or **{stats['parent224_share_of_mean_construction_displacement_percent']:.2f}% of the mean construction-induced displacement**. The remaining displacement is {float((p['restore_224_X_DC']-p['original_network_DC'])[q].mean()):.2f} MW. That diagnostic's WAPE is {replacement:.4f}%. Restoring all 33 changed reactances reproduces the original DC results across all seven interfaces. Restoring row 41's X alone has no DC flow effect: it connects a pendant Albany bus.

The code used a fallback geometric prior because it could not realize the original R/X pair with the searched conductor/geometry candidates. For row 224, the original-X-implied length is 47.060 km, below the declared 71.016-km lower bound. The implementation selects the **177.539-km preferred length**, 1.25 times an approximate geographic chord. This is not a measured route, installed conductor identification or factory impedance. Its helper docstring's “nearest length boundary” description does not match that preferred-length behavior. The diagnostic records the executed behavior without modifying the old code.

[Parameter/operator audit](output/nygrid_2025_centraleast_diagnosis/model_delta/model_delta_review.json), [fallback provenance](output/nygrid_2025_centraleast_diagnosis/model_delta/fallback_provenance_review.json), [annual X experiment](output/nygrid_2025_centraleast_diagnosis/experiments/annual_DC_bridge/annual_DC_bridge_receipt.json), and [independent annual DC reconstruction](output/nygrid_2025_centraleast_diagnosis/model_delta/annual_DC_independent_review.json).

## 2. The reference generator supplies the omitted AC losses

The supplied active-power profiles balance demand before AC losses. In the AC run, the original reference generator at **bus 50, CLAY, zone C**, supplies the entire extra real-power requirement while other generators and the six transfer targets remain fixed. Mean whole-network loss is **{stats['mean_baseline_AC_loss_model_MW']:.3f} model MW**. This is distinct from the interface flow changes reported on the public scale.

To test this mechanism, the experiment takes the already-solved AC loss `PF + PT` on each original runtime branch, assigns half as an additional withdrawal at each end, and solves DC on the same network. It preserves the other active injections and controls. The reference increase equals the original AC loss, and the resulting CENTRAL EAST displacement is **{stats['loss_loaded_mean_delta_public_MW']:.2f} public MW**. This reconstructs **{stats['half_loss_reconstruction_share_of_mean_same_network_AC_DC_displacement_percent']:.2f}% of the mean same-network AC–DC displacement**. Its mean absolute difference from AC is {stats['remaining_MAE_public_MW']:.2f} MW, with a maximum of {stats['remaining_maximum_absolute_public_MW']:.2f} MW.

The allocation is a diagnostic convention. Assigning all loss to the original from ends or all to the original to ends changes the mean interface increment to {min(stats['nonunique_allocation_mean_effect_public_MW']):.2f}–{max(stats['nonunique_allocation_mean_effect_public_MW']):.2f} MW. These alternatives are not confidence bounds. Because the reconstruction uses solved AC losses, it is not an independent forecast or a unique causal decomposition of resistance, voltage and reactive-power effects. The small residual contains the remaining full-admittance/voltage/angle differences and the chosen loss-allocation convention.

[Annual loss reconstruction](output/nygrid_2025_centraleast_diagnosis/experiments/annual_loss_loaded_DCF/annual_loss_loaded_receipt.json) records all 25,482 allocation-case solves. The [stage metrics](output/nygrid_2025_centraleast_diagnosis/summary/stage_metrics.csv) include every month and allocation, with the fixed cohort retained.

## Excluded explanations and interpretation limits

- Changing the terminal convention does not remove the discrepancy. The inherited negative-from sum equals receiving-side flow for these four negatively signed members; source-side WAPE is 45.9933%, only 0.9573 points above 45.0359%. Mean separation is 16.05 public MW.
- The large increase is mainly a route redistribution plus a smaller increase in total eastward transfer. The exact inherited relation is `TOTAL EAST = CENTRAL EAST + row224 contribution`. CE rises by 1,046.65 public MW while the bypass contribution falls by 746.84 MW; TOTAL EAST rises by only 299.81 MW. This is accounting support, not an independent causal experiment.
- The source generator relocations, six-transfer controls, branch-211 substitution and dated topologies are already shared by the DC and AC comparators. They are not newly introduced AC differences. No duplicated sections, double-applied reactors or direct CE-X change was found.
- X-only AC restorations are deliberately mixed parameter sets, not approved fixes. In particular, restoring row 41's former X while retaining its redesigned R produces R/X≈6.72; an all-X-only restoration reaches about 1.70 pu in the selected AC tests. Lower WAPE does not validate an impedance or operating state.
- The coherent original-parent AC and zero-resistance experiments are selected-hour diagnostics, not annual results. Original-parent AC converges in all 11 selected cases; zero-resistance AC qualifies in only 5. Failed trials remain flagged and are excluded from solution claims.
- None of the baseline annual AC solutions passes the combined voltage/generator/converter assumptions. The inherited physical P32 meter membership and numeric interpretation of `Flow(MWH)` also remain uncertified. This investigation establishes why these model outputs differ, not which parameter set represents the actual grid.

The next model-development step is to validate the Gilboa–Buchanan equivalent/route assumptions and construct an AC loss-balanced generation/interchange policy with defensible participation, then reassess the seven interfaces and physical operating limits together. The diagnostic X restoration should not be promoted merely because it lowers this one error metric.

## Reproduction and evidence boundary

The [summary receipt](output/nygrid_2025_centraleast_diagnosis/summary/diagnosis_summary.json) binds the original saved comparisons and both annual experiments. [Hourly comparison rows](output/nygrid_2025_centraleast_diagnosis/summary/hourly_stage_comparison.csv) retain all 8,760 positions and explicit matched-hour flags. Methods are in `scripts/nygrid_2025_centraleast_diagnosis`; experiment runners use the existing MATLAB/MATPOWER environment and preserve failed diagnostic trials separately.

To regenerate the summary and scientific figure after completing the saved diagnostic runners:

```powershell
python scripts/nygrid_2025_centraleast_diagnosis/build_diagnosis.py
```

The [delivery manifest](output/nygrid_2025_centraleast_diagnosis/DELIVERY_MANIFEST.json) binds this investigation and verifies the prior AC, profile-audit and compact-model files against commit `6dcc77f071a9ce4aaaa2fcba9a9aabc15f7d5dbc`. Rebuilding outputs requires a fresh review and manifest seal; it does not update the production model.
'''
    (ROOT / 'NYGRID_2025_CENTRAL_EAST_DIAGNOSIS.md').write_text(report, encoding='utf-8')
    print(json.dumps({k:stats[k] for k in ['passed','construction_mean_delta_public_MW','loss_loaded_mean_delta_public_MW',
                                        'remaining_mean_delta_public_MW','WAPE_original_DC_percent','WAPE_AC_percent']}))


if __name__ == '__main__':
    main()
