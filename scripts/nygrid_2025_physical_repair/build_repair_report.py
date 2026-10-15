"""Publish the completed physical-repair results from sealed annual receipts."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_physical_repair'
RUN=OUT/'annual/physical_repair_v1'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def rec(p):
    with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':p.relative_to(ROOT).as_posix(),'sha256':digest,'bytes':p.stat().st_size}
def main():
    physics_path=OUT/'independent/annual_physics_review.json';a=read(physics_path)
    score_path=RUN/'comparison/scoring_receipt.json';s=read(score_path)
    validation_path=RUN/'validation/annual_input_accounting_review.json';v=read(validation_path)
    assert a['passed'] and a['completed_annual_review'] and s['passed'] and s['completed'] and v['passed'] and v['completed']
    n=s['candidate_qualified_hours'];paired=s['paired_qualified_hours'];new=s['candidate_new_success_hours'];lost=s['current_success_lost_hours']
    p41=a['paired_parent41_loss_model_MW'];vol=a['target_voltage'];remaining=a['remaining_global_limits']
    targets_path=OUT/'independent/target_parent_metrics.csv';t=pd.read_csv(targets_path)
    metrics_path=RUN/'comparison/public_interface_metrics.csv';metrics=pd.read_csv(metrics_path)
    m=metrics.query("period=='annual' and cohort=='paired_current_baseline' and convention=='legacy_signed_literal_from'")
    old=m[m.model.eq('current_baseline')].set_index('interface');fresh=m[m.model.eq('candidate')].set_index('interface');assert len(old)==len(fresh)==7
    table=['| Interface | Previous MAE | Repaired MAE | Previous WAPE | Repaired WAPE |','|---|---:|---:|---:|---:|']
    for name,r in fresh.iterrows():
        b=old.loc[name];table.append(f'| {name} | {b.mae_public_MW:.2f} | {r.mae_public_MW:.2f} | {b.wape_percent:.2f}% | {r.wape_percent:.2f}% |')
    dest=OUT/'summary';dest.mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white','savefig.facecolor':'white'})
    fig,ax=plt.subplots(1,2,figsize=(11,4.8),layout='constrained')
    values=[p41['old_mean'],p41['new_mean']];ax[0].bar(['Previous','Repaired'],values,color=['#9B6C28','#2763A8'],width=.6)
    for i,x in enumerate(values):ax[0].text(i,x+1,f'{x:.2f}',ha='center')
    ax[0].set_ylim(0,max(values)*1.16);ax[0].set_ylabel('Mean real loss (model MW)');ax[0].set_title('Parent 41');ax[0].grid(axis='y',alpha=.18);ax[0].set_axisbelow(True)
    q=t[t.cohort.eq('paired_old_baseline')]
    for j,(label,color,marker) in enumerate([('baseline','#9B6C28','o'),('candidate','#2763A8','s')]):
        z=q[q.version.eq(label)&q.parent_row.isin([185,195])].sort_values('parent_row');x=np.arange(2)+(j-.5)*.16
        ax[1].plot(x,z.maximum_VM_pu,marker=marker,ls='none',color=color,label='Previous' if j==0 else 'Repaired',markersize=7)
        for xx,yy in zip(x,z.maximum_VM_pu):ax[1].text(xx,yy+(.003 if j==0 else -.007),f'{yy:.4f}',ha='center',fontsize=9)
    ax[1].axhline(1.05,color='#333333',ls='--',lw=1,label='Existing upper limit');ax[1].set_xticks([0,1],['Parent 185','Parent 195']);ax[1].set_ylim(1.0,1.14);ax[1].set_xlim(-.35,1.35);ax[1].set_ylabel('Maximum whole-line voltage (pu)');ax[1].set_title('Targeted voltage violations');ax[1].legend(frameon=False,loc='lower left');ax[1].grid(axis='y',alpha=.18)
    fig.suptitle(f'2025 physical repair · same {paired:,} qualified hours',fontsize=13)
    for suffix in ['png','pdf']:fig.savefig(dest/f'physical_repair_comparison.{suffix}',dpi=180)
    plt.close(fig)
    text=f'''# Physical repair of parents 41, 185 and 195

Completed annual replay of the frozen `physical_repair_41_185_195_20261015` candidate, based on repository commit 6d46babc3af4335638241e3abff525425a0a6d7e. The requested physical defects are evaluated below using fresh solves and independent reconstruction. The previous model, annual results and pre-existing map work have recoverable preserved copies.

## Result

The repaired model qualifies **{n:,} of 8,651 source-qualified hours**, retaining all 8,760 clock rows and the 109 source-excluded positions. There are **{new:,} newly qualified hours** and **{lost:,} previously qualified hours lost**. The comparison cohort contains {paired:,} identical hours. The solver used 148 retained voltage buses, preserved all 1,464 generator rows and six prescribed transfers, and did not fit observed interface flows.

On that paired cohort, parent 41 mean loss falls from **{p41['old_mean']:.5f} to {p41['new_mean']:.5f} model MW**, a **{p41['mean_reduction_percent']:.3f}% reduction**. On all {n:,} new qualified hours, its mean loss is {a['candidate_parent41_mean_loss_model_MW']:.5f} model MW. Its preserved aggregate 2,000 A apparatus ceiling is exceeded in {a['candidate_parent41_hardware_current_exceedance_hours']:,} hours; the loss repair does not certify equipment or weather-dependent DLR adequacy.

| Repaired parent | Minimum whole-line voltage | Maximum whole-line voltage | Hours outside 0.95–1.05 pu |
|---|---:|---:|---:|
|185|{vol['185']['min_VM']:.6f}|{vol['185']['max_VM']:.6f}|{vol['185']['violation_hours']}|
|195|{vol['195']['min_VM']:.6f}|{vol['195']['max_VM']:.6f}|{vol['195']['violation_hours']}|

The voltage table uses all {n:,} qualified hours, including newly successful hours. The figure uses the paired cohort for direct before/after comparison.

![Paired physical repair comparison](output/nygrid_2025_physical_repair/summary/physical_repair_comparison.png)

## What changed

**Parent 41:** restore the imported R/X = 0.0018/0.0089 pu on 100 MVA. Rebuild the conductor realization from the already-declared inverse search's first-ranked imported-R/X candidate: ACSS Mallard, four uncoupled parallel circuits, one conductor per phase, 10.750872722 km effective length, GMD 3.948477 m, 95°C reference resistance. The corresponding geometric B is 0.021267472267637012 pu. Electrical/thermal metadata and current registry provenance are updated together. The prior aggregate 2,000 A terminal apparatus ceiling is retained as an independent conservative bound. Approximate map geography is not used to force the electrical length, and no installed-line identity is claimed.

**Parents 185/195:** retain current conductors, section R/X/B and the existing 75% nominal shunt-compensation rating. Remove the old endpoint-only reactor allocation and distribute it in proportion to local charging: each section contributes `0.75 × baseMVA × B_section /2` MVAr at 1 pu to each endpoint. The total nominal reactor rating does not increase. Interior shunts remain passive admittances, so the same exact complex-network reduction and current recovery apply. These intermediate reactors are a declared synthetic design, not a claim about installed substations.

The source profiles, hourly native/HQ active generation, regional interchange targets, six DC/PAR targets, voltage limits, generator voltage setpoints and bus/branch/generator axes remain unchanged.

## Annual interface comparison

Mean absolute errors below are public-scale MW on the same {paired:,} hours, using the frozen signed original-from-terminal convention. WAPE uses total absolute observed flow as its denominator. Physical repairs are assessed independently of improvements or regressions in interface fit.

{chr(10).join(table)}

The full scoring output separately reports all newly qualified hours, the common cohort, any lost hours, each calendar month, post-Dover hours, and alternate terminal conventions. Physical 2025 P32 meter membership and the inherited numeric-as-MW interpretation of the source `Flow(MWH)` header remain unverified. Oracle adjustments were not used as generation inputs.

## Remaining operating limitations

The requested parent 185/195 voltage issue is evaluated explicitly; whole-network operating qualification remains **{remaining['full_operating_qualified_hours']:,} hours**. Elsewhere the annual readback finds {remaining['overvoltage_hours']:,} hours with overvoltage, {remaining['undervoltage_hours']:,} with undervoltage, {remaining['Q_violation_hours']:,} with generator-Q violations, {remaining['S_violation_hours']:,} with assumed generator-S violations, and {remaining['branch_MVA_violation_hours']:,} with branch-MVA violations. The overall voltage range is {remaining['minimum_VM']:.6f}–{remaining['maximum_VM']:.6f} pu. These violations remain visible in the map/package; equation qualification is not an operating certificate.

The model is usable as a reproducible synthetic research model with the stated limits. It is not a validated historical dispatch, installed-asset model, or new annual weather/thermal simulation. No voltage value was clipped and no voltage, reactive or apparatus threshold was relaxed to obtain a pass.

## Verification and delivery

The targeted preflight passed 17 hours across all four topology states, matched parent 41 forward R/X/B to 1.74e−18 pu and detailed/compact voltages to 1.17e−12 pu. The full-year checks independently reconstruct the source inputs, finite P/Q/assumed-S capabilities, active/reactive nodal equations, branch complex powers and terminal currents, material I²R losses, passive voltage recovery, and zonal/regional loss accounting. Failed or source-excluded rows are never rendered as valid predictions.

- [Annual producer receipt](output/nygrid_2025_physical_repair/annual/physical_repair_v1/annual_receipt.json)
- [Independent input/accounting review](output/nygrid_2025_physical_repair/annual/physical_repair_v1/validation/annual_input_accounting_review.json)
- [Independent physical review](output/nygrid_2025_physical_repair/independent/annual_physics_review.json)
- [Scoring receipt](output/nygrid_2025_physical_repair/annual/physical_repair_v1/comparison/scoring_receipt.json)
- [Target-parent comparison table](output/nygrid_2025_physical_repair/independent/target_parent_metrics.csv)
- [Reproduction instructions](scripts/nygrid_2025_physical_repair/README.md)

The updated interactive map and portable handoff use the newly compiled corrected templates and this completed annual replay. Their individual delivery manifests bind the model, source profiles, annual arrays, interface definitions, geography, runtime, documentation and offline assets. Old numerical bundles remain preserved for reproducing prior reports.
'''
    report=ROOT/'NYGRID_2025_PHYSICAL_REPAIR.md';report.write_text(text,encoding='utf-8')
    receipt={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'completed_annual_evidence_required':True,
             'sources':[rec(p) for p in [physics_path,score_path,validation_path,targets_path,metrics_path]],
             'outputs':[rec(report),rec(dest/'physical_repair_comparison.png'),rec(dest/'physical_repair_comparison.pdf')]}
    (dest/'report_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'candidate_qualified':n,'paired':paired,'new':new,'lost':lost,'report':report.name}))
if __name__=='__main__':main()
