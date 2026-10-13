"""Build the reviewed annual comparison report from sealed, named cohorts."""
from pathlib import Path
import hashlib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_ac_loss_revision'
RUN = 'released_equivalent_boundary_consistent'
ANNUAL = OUT / 'validation/annual' / RUN


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def record(path):
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    comparison = OUT / 'comparison/combined'
    paths = [ANNUAL/'annual_loss_policy_receipt.json', comparison/'scoring_receipt.json',
             comparison/'public_interface_metrics.csv', comparison/'NY_zonal_loss_accounting.csv',
             ANNUAL/'annual_hour_quality.csv', OUT/'impedance/impedance_recommendation.json',
             OUT/'impedance/actual_case_implementation_review.json',
             OUT/'policy_evidence/historical_definition_supplement.json',
             OUT/'validation/pairs/simultaneous_representatives/pair_receipt.json',
             OUT/'validation/jacobian/jacobian_receipt.json', OUT/'validation/policy_contract/policy_contract_receipt.json',
             comparison/'comparison_cohort.csv',
             OUT/f'impedance/{RUN}_annual_arrays_independent_review.json',
             OUT/'validation/representative_factorial/factorial_receipt.json',
             OUT/'validation/representative_factorial/common_success_attribution.csv']
    producer, scored = read(paths[0]), read(paths[1])
    assert producer['completed'] and producer['replay_integrity_passed'] and scored['passed']
    assert producer['source_files_unchanged_during_replay']
    metrics = pd.read_csv(paths[2]); zones = pd.read_csv(paths[3]); quality = pd.read_csv(paths[4])
    cohort = pd.read_csv(comparison/'comparison_cohort.csv')
    independent = read(paths[-3]); factorial = read(paths[-2]); attribution = pd.read_csv(paths[-1])
    assert independent['passed'] and independent['completed'] and factorial['completed']
    assert len(attribution)==factorial['common_success_hour_count']==11
    factorial_means = attribution.drop(columns='hour_index').mean().to_dict()
    assert abs(factorial_means['combined_effect_public_MW']-factorial_means['impedance_effect_from_legacy_public_MW']-
               factorial_means['loss_policy_effect_from_legacy_public_MW']-factorial_means['interaction_public_MW'])<1e-8
    annual = metrics[(metrics.cohort=='paired_frozen_old') & (metrics.period=='annual') &
                     (metrics.convention=='legacy_signed_literal_from')]
    old = annual[annual.model=='frozen_old'].set_index('interface')
    assert old.index.tolist()==['DYSINGER EAST','WEST CENTRAL','TOTAL EAST','MOSES SOUTH','CENTRAL EAST - VC','UPNY CONED','SPR/DUN-SOUTH']
    new = annual[annual.model=='combined'].set_index('interface').loc[old.index]
    old_ce_all = metrics[(metrics.cohort=='frozen_old_all8494') & (metrics.period=='annual') &
        (metrics.convention=='legacy_signed_literal_from') & (metrics.interface=='CENTRAL EAST - VC')].wape_percent.item()
    assert len(old)==7 and np.all(old.hours==new.hours)
    table = pd.DataFrame({'interface':old.index, 'hours':new.hours.to_numpy(),
        'old_WAPE_percent':old.wape_percent.to_numpy(),'revised_WAPE_percent':new.wape_percent.to_numpy(),
        'change_percentage_points':(new.wape_percent-old.wape_percent).to_numpy(),
        'old_bias_public_MW':old.bias_public_MW.to_numpy(),'revised_bias_public_MW':new.bias_public_MW.to_numpy()})
    summarydir = OUT/'summary'; summarydir.mkdir(exist_ok=True)
    table.to_csv(summarydir/'paired_annual_interfaces.csv',index=False,lineterminator='\n')
    qualified_ids = cohort.loc[cohort.revised_comparison_qualified, 'hour_index']
    qualified = quality[quality.hour_index.isin(qualified_ids)]
    rejected = quality[~quality.hour_index.isin(qualified_ids)]
    counts = dict(source_qualified=8651, source_excluded=109, old_qualified=8494,
                  revised_qualified=scored['revised_qualified_hours'], paired=scored['paired_qualified_hours'],
                  new=scored['revised_only_success_hours'],lost=scored['frozen_old_success_lost_hours'],
                  operating_qualified=scored['revised_operating_qualified_hours'],
                  rejected=8651-scored['revised_qualified_hours'])
    assert counts['paired']+counts['new']==counts['revised_qualified']
    assert counts['paired']+counts['lost']==8494
    assert len(qualified)==counts['revised_qualified'] and len(rejected)==counts['rejected']
    summary = dict(passed=True,counts=counts,elapsed_seconds=producer['elapsed_seconds'],
        solver_exceptions=producer['solver_exceptions'],
        source_tuple_provenance_verified=True,physical_parent224_impedance_validated=False,
        actual_zonal_losses_or_delivered_load_observed=False,internal_interface_fitting_used=False,
        failed_iteration_implies_global_infeasibility=False,
        failed_status_counts={str(k):int(v) for k,v in rejected.loss_status.value_counts().items()},
        qualified_voltage_min_pu=float(qualified.min_voltage_pu.min()),qualified_voltage_max_pu=float(qualified.max_voltage_pu.max()),
        qualified_total_loss_mean_model_MW=float(qualified.AC_real_losses_mw.mean()),
        qualified_total_loss_max_model_MW=float(qualified.AC_real_losses_mw.max()),
        maximum_native_PG_change_model_MW=float(qualified.native_PG_change_from_original_MW.abs().max()),
        maximum_NY_load_balance_error_model_MW=float(qualified.NY_gross_load_accounting_residual_MW.max()),
        maximum_regional_import_error_model_MW=float(qualified.regional_NY_import_residual_MW.max()),
        maximum_zonal_loss_fraction=float(zones.maximum_loss_fraction.max()),
        qualified_hours_any_zone_loss_fraction_over25percent=int((qualified.maximum_NY_zonal_loss_fraction>.25).sum()),
        representative_factorial_common_hours=11,representative_factorial_means=factorial_means,
        representative_factorial_is_not_annual_attribution=True,
        independent_maximum_errors=independent['maximum_independent_errors'],
        equivalent224_loss_ranges=independent['equivalent224_qualified_loss_ranges'],
        paired_annual_interfaces=table.to_dict('records'),dependencies=[record(p) for p in paths])
    (summarydir/'revision_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    fig, ax = plt.subplots(figsize=(11.2,5.9)); fig.patch.set_facecolor('#fbfbf8'); ax.set_facecolor('#fbfbf8')
    labels = ['Dysinger East','West Central','Total East','Moses South','Central East–VC','UPNY ConEd','SPR/DUN South']
    y=np.arange(7); h=.34
    ax.barh(y-h/2,table.old_WAPE_percent,h,color='#89939e',label='Previous AC')
    ax.barh(y+h/2,table.revised_WAPE_percent,h,color='#087f8c',label='Revised AC + loss policy')
    for i,(a,b) in enumerate(zip(table.old_WAPE_percent,table.revised_WAPE_percent)):
        ax.text(a+.55,i-h/2,f'{a:.2f}%',va='center',fontsize=10,color='#56616b')
        ax.text(b+.55,i+h/2,f'{b:.2f}%',va='center',fontsize=10,color='#08646f')
    ax.set_yticks(y,labels);ax.invert_yaxis();ax.set_xlabel('WAPE (%) — identical matched hours')
    ax.set_xlim(0,max(table.old_WAPE_percent.max(),table.revised_WAPE_percent.max())*1.16)
    ax.xaxis.grid(True,alpha=.17);ax.set_axisbelow(True);ax.legend(frameon=False,loc='lower right')
    fig.suptitle('NYISO interface comparison after the AC loss revision',x=.04,ha='left',fontsize=17,fontweight='bold')
    fig.text(.04,.91,f"2025 • {counts['paired']:,} common qualified hours • inherited terminal convention",color='#57636d')
    fig.text(.04,.035,f"Coverage: {counts['revised_qualified']:,}/{8651:,} revised qualified; {counts['new']} gained, {counts['lost']} lost. "
             f"Physical V/Q/capability qualification: {counts['operating_qualified']:,}.\n"
             'Released equivalent impedance and zonal loss ownership are declared study assumptions; no interface fitting.',fontsize=9,color='#57636d')
    fig.subplots_adjust(left=.205,right=.97,top=.86,bottom=.16)
    fig.savefig(summarydir/'annual_interface_comparison.png',dpi=180,facecolor=fig.get_facecolor())
    fig.savefig(summarydir/'annual_interface_comparison.svg',facecolor=fig.get_facecolor());plt.close(fig)
    rows='\n'.join(f"| {r.interface} | {r.old_WAPE_percent:.2f}% | {r.revised_WAPE_percent:.2f}% | {r.change_percentage_points:+.2f} | {r.old_bias_public_MW:+.1f} | {r.revised_bias_public_MW:+.1f} |" for r in table.itertuples())
    zonerows='\n'.join(f"| {r.zone} | {r.mean_allocated_loss_model_MW:.3f} | {100*r.maximum_loss_fraction:.2f}% | {r.minimum_served_PD_model_MW:.3f} | {r.hours_loss_fraction_over25percent:,} |" for r in zones.itertuples())
    report=f'''# 2025 AC impedance and loss-accounting revision

The versioned 148-bus replay is complete: **{counts['revised_qualified']:,} of 8,651 source-eligible hours** pass the revised AC equations, exact recovery and declared loss accounting. The fair old/new comparison uses **{counts['paired']:,} common hours**, with {counts['new']} newly qualified hours and {counts['lost']} prior successes lost. There were {producer['solver_exceptions']} solver exceptions. **{counts['operating_qualified']} hours pass the joint voltage/reactive/generator-capability gate.** These are conditional synthetic AC results, not a fully feasible or as-built NYISO model.

## Impedance finding and implemented scope

Parent 224 (Gilboa bus 38 to Buchanan bus 77) was added by Cornell NYgrid as an E–G representation of the Marcy South corridor. It is absent from the original NPCC and S7 branches and is not an identified direct physical circuit. The pinned author code releases `(R,X,B)=(0.02,0.0147,0)` pu on 100 MVA. The paper's `47 miles × 0.371 ohm/mile / 1190.25 ohm` gives `X=0.0146498635` pu, within 0.342% of the released approximation; 0.0147 is not the exact four-decimal rounding of those displayed inputs. Neither the source R nor B has a recovered asset derivation. Historical detailed circuits connect Gilboa to Fraser, Leeds and New Scotland; those records do not identify a direct Gilboa–Buchanan asset.

The new overlay restores the complete released tuple in its existing two equal numerical sections and preserves original bus/branch axes. It removes this aggregate's synthetic conductor rating, R(T), and DLR eligibility. The earlier 177.5 km geographic-chord conductor realization has no verified physical identity. Every other branch parameter, dated topology change and bus shunt is preserved. Source provenance is validated; **physical AC impedance remains unvalidated**. No alternative resistance was selected to improve convergence or NYISO error.

Evidence: [source and parameter review](output/nygrid_2025_ac_loss_revision/impedance/impedance_recommendation.json), [actual implementation audit](output/nygrid_2025_ac_loss_revision/impedance/actual_case_implementation_review.json), [pinned original author code](https://github.com/AndersonEnergyLab-Cornell/NYgrid/blob/47698b6c7823ae7b1bc6935e5601d5b64b8f918e/modifyMPC.m), and [archived paper](output/nygrid_2025_ac_loss_revision/impedance/sources/NYgrid_published_paper.pdf).

## Loss policy and scientific assumptions

NYISO's actual zonal load is calculated as generation plus net interchange. The 2025 Market Participants User's Guide v16, effective May 29, confirms the same definition used by the current guide. Thus the model treats P58 actual load as a loss-inclusive boundary balance: `served_PD_z + allocated_NY_loss_z = frozen_P58_z`. It does not add all AC losses to the tiny Clay reference generator while keeping loss-inclusive demand untouched.

Within-NY corridor losses are split equally between endpoint zones. This is a declared accounting rule, not NYISO's observed metering assignment. Served load follows the existing within-zone spatial shares, and Q demand follows the inherited power factor. ISONE, Ontario and PJM generators supply their internal and NY-border corridor losses using frozen participation weights and their original finite P bounds. External delivered-load proxies remain fixed, so net imports at the NY terminals remain the original targets. Native PG, signed HQ injection and all six DC transfers remain fixed. External Q-circle assumptions are updated with PG, but Q limits are not enforced by the PF.

Evidence: [frozen policy contract](output/nygrid_2025_ac_loss_revision/policy_evidence/loss_accounting_policy_contract.json), [verified 2025 definition supplement](output/nygrid_2025_ac_loss_revision/policy_evidence/historical_definition_supplement.json), and [NYISO guide](https://www.nyiso.com/documents/20142/3625950/mpug.pdf). The source definition supports the balance equation; the spatial loss ownership, external proxy capabilities and estimated delivered load remain modeling assumptions.

The default solver jointly solves voltage and loss-dependent injections, with analytic derivatives and domain-preserving line search. All variable injections remain on the 148 retained buses. Original branch currents and voltages are recovered through the complex-admittance lift. It performs no full-network Newton solve inside the compact annual path and no OPF or observation fitting. A failed step near zero delivered demand is retained as a failed attempt, not promoted or interpreted as proof of global infeasibility.

## Annual NYISO comparison

All 8,760 clock positions remain in the delivery. The original 109 source-excluded hours are retained as excluded. The seven inherited interface cuts, gamma, clock alignment and three terminal conventions were frozen before inspecting revised results. The table uses the inherited signed-literal-from convention and the same {counts['paired']:,} common qualified hours for both columns. Aggregate power is divided by gamma; amperes are never rescaled. Physical P32 meter membership and the inherited numeric-as-MW interpretation remain uncertified.

| Interface | Previous WAPE | Revised WAPE | Change (pp) | Previous bias (public MW) | Revised bias (public MW) |
|---|---:|---:|---:|---:|---:|
{rows}

![Annual paired interface comparison](output/nygrid_2025_ac_loss_revision/summary/annual_interface_comparison.png)

The [complete metrics](output/nygrid_2025_ac_loss_revision/comparison/combined/public_interface_metrics.csv) include annual, monthly and post-Dover results; all three terminal conventions; revised-all, paired, newly qualified and lost cohorts. The [hour-level cohort ledger](output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_cohort.csv) prevents a change in solver coverage from being hidden inside the error comparison. These scores assess agreement with the public series, not impedance truth.

The earlier CENTRAL EAST WAPE of {old_ce_all:.2f}% used all 8,494 old successes. Restricting that unchanged old result to the current common {counts['paired']:,} hours gives {old.loc['CENTRAL EAST - VC','wape_percent']:.2f}%; the revised {new.loc['CENTRAL EAST - VC','wape_percent']:.2f}% must be compared with this matched value. The cohort change is reported separately from the model change.

An additional 14-hour four-cell check evaluates old impedance/old loss treatment, revised impedance alone, revised loss policy alone and both changes. Eleven hours qualify in all four cells. On only those selected hours, mean CENTRAL EAST flow changes are {factorial_means['impedance_effect_from_legacy_public_MW']:.2f} public MW for the full released impedance tuple alone, {factorial_means['loss_policy_effect_from_legacy_public_MW']:.2f} MW for the loss policy alone, and {factorial_means['interaction_public_MW']:.2f} MW for their interaction, summing to {factorial_means['combined_effect_public_MW']:.2f} MW. This is a representative flow decomposition, not annual WAPE attribution or a physical parameter fit. [All cases and explicit failures](output/nygrid_2025_ac_loss_revision/validation/representative_factorial/factorial_checks.csv) and [common-hour arithmetic](output/nygrid_2025_ac_loss_revision/validation/representative_factorial/common_success_attribution.csv) are retained.

## Closure, rejected hours and physical limits

On qualified hours, maximum original-native PG change is {summary['maximum_native_PG_change_model_MW']:.3g} model MW; maximum zonal served-plus-loss error is {summary['maximum_NY_load_balance_error_model_MW']:.3g} MW; maximum regional net-import error is {summary['maximum_regional_import_error_model_MW']:.3g} MW. Total modeled AC loss averages {summary['qualified_total_loss_mean_model_MW']:.3f} MW and reaches {summary['qualified_total_loss_max_model_MW']:.3f} MW. These closure checks are constraints of the model, not independent validation of actual delivered load or loss measurements.

The {counts['rejected']} rejected source-eligible hours have statuses `{json.dumps(summary['failed_status_counts'],sort_keys=True)}`. Failed/partial arrays and iteration traces are saved and excluded from all prediction checks. No negative NY delivered demand is accepted. There is no hidden slack fallback, loss clipping, or capacity expansion.

| Zone | Mean assigned loss (model MW) | Maximum loss / gross target | Minimum served PD (model MW) | Hours with loss fraction >25% |
|---|---:|---:|---:|---:|
{zonerows}

The maximum loss fraction is **{100*summary['maximum_zonal_loss_fraction']:.2f}%**; {summary['qualified_hours_any_zone_loss_fraction_over25percent']:,} qualified hours have at least one zone above 25%. Such large modeled fractions are a warning about the unresolved network equivalent, loss ownership and synthetic operating assumptions. They are not measured NYISO transmission losses. Across qualified cases voltage spans {summary['qualified_voltage_min_pu']:.6f}–{summary['qualified_voltage_max_pu']:.6f} pu. All {counts['revised_qualified']:,} fail the joint V/Q/capability gate. This revision fixes the stated real-power accounting contract but does not repair inherited voltage controls, reactive capability, conductor identity or full operating feasibility.

The unresolved parent-224 equivalent alone dissipates {independent['equivalent224_qualified_loss_ranges']['minimum_model_MW']:.3f}–{independent['equivalent224_qualified_loss_ranges']['maximum_model_MW']:.3f} model MW (mean {independent['equivalent224_qualified_loss_ranges']['mean_model_MW']:.3f} MW). Its resistance therefore remains a consequential research limitation even after removing the unsupported conductor interpretation.

## Verification and reproducibility

The annual run took {producer['elapsed_seconds']:.1f} seconds and checks source/code/MATPOWER hashes before and after the run. Independent checks cover original-branch laws, full-network KCL, all three recovered current columns, passive-bus voltage recovery, original non-224 parameters and dated source masks. The contract suite has 24 cases; the analytic Jacobian has 10 finite-difference cases. Compact and detailed coupled solvers agree on the 11 qualified cases among 14 representative hours; both reject the same three stress cases. A conventional detailed PF on each of the 11 qualified representative final allocations independently verifies the resulting network solution. This is a conditional numerical-equivalence result, not 14 successful physical cases or a second full-year conventional PF replay.

The [independent annual array review](output/nygrid_2025_ac_loss_revision/impedance/{RUN}_annual_arrays_independent_review.json) verifies all 12 months against separately reconstructed branch admittances and original source accounting. It also records equivalent losses, positive-demand checks and every rejected hour. Current recovery is validated on original branch sections and does not create verified amperes for an unidentified installed conductor.

Use the [public MATLAB entry point](System%20Matpower%20Format/run_nygrid_2025_loss_consistent_acpf.m) and [reproduction guide](scripts/nygrid_2025_ac_loss_revision/README.md). The delivered annual [producer receipt](output/nygrid_2025_ac_loss_revision/validation/annual/{RUN}/annual_loss_policy_receipt.json) and [scoring receipt](output/nygrid_2025_ac_loss_revision/comparison/combined/scoring_receipt.json) identify exact inputs and cohorts. The [delivery manifest](output/nygrid_2025_ac_loss_revision/DELIVERY_MANIFEST.json) seals the new namespace and verifies previous model deliveries remain byte-preserved.

Historical fixed-point prototypes, stress attempts and source-download failures are retained and explicitly classified. They are not current solver qualification. Current evidence is the simultaneous-solver validation, completed annual replay and independent final audits.
'''
    (ROOT/'NYGRID_2025_AC_LOSS_REVISION.md').write_text(report,encoding='utf-8')
    print(json.dumps(dict(passed=True,counts=counts,summary=str(summarydir/'revision_summary.json'))))


if __name__=='__main__':main()
