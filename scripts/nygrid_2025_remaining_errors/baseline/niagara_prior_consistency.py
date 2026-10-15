"""Compare conditional western corrections with frozen Niagara source priors.

No PF, fitting or new historical dispatch estimate. The EIA calendar means and
the selected-hour model means have explicitly different populations. Saved DC
counterfactuals are rescored on the current 8170-hour mask, not relabeled as AC.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import subprocess

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_remaining_errors/baseline'
CF = ROOT / 'output/nygrid_2025_western_counterfactuals'


def record(path):
    with path.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest,
            'bytes': path.stat().st_size}


def metrics(model, observed):
    e = model-observed
    return {'hours': len(e), 'mae_public_MW': float(np.abs(e).mean()),
            'bias_public_MW': float(e.mean()),
            'wape_percent': float(100*np.abs(e).sum()/np.abs(observed).sum())}


def main():
    array_path = ROOT/'output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_arrays.npz'
    prior_path = ROOT/'output/nygrid_2025_western_audit/generation/target_plant_hourly_audit.npz'
    eia_path = ROOT/'output/nygrid_2025_western_audit/generation/target_EIA923_final_monthly.csv'
    reg_path = ROOT/'output/nygrid_2025_western_audit/corrected/model_generator_register.csv'
    gate_path = ROOT/'output/nygrid_2025_remaining_errors/accounting/current_gate_terms.csv'
    model_path = ROOT/'output/nygrid_2025_latest_handoff/model/latest_model.mat'
    shard_paths = [model_path.parent/f for f in ['profiles_h0001_4380.mat','profiles_h4381_8760.mat']]
    scenarios = ['baseline'] + [f'niagara_{mode}_{donor}' for mode in
        ['legacy_bounded','month_shape_literal','month_shape_constrained']
        for donor in ['outside_ab','all_other']]
    replay_paths = [CF/'replay'/f'{s}.npz' for s in scenarios]
    input_paths = [CF/'inputs'/f'{s}.npz' for s in scenarios[1:]]
    paths = [array_path,prior_path,eia_path,reg_path,gate_path,model_path,*shard_paths,
             *replay_paths,*input_paths,CF/'inputs/niagara_hourly_changes.csv.gz']
    before = [record(p) for p in paths]

    a = np.load(array_path,allow_pickle=False)
    q = a['revised_qualified'].astype(bool); assert q.sum()==8170
    h = a['hour_index']; t = a['timestamp_utc']; names = a['interface_names']
    local = pd.DatetimeIndex(pd.to_datetime(t,utc=True)).tz_convert('America/New_York')
    months = local.month.to_numpy(); gamma = float(a['gamma'])
    obs = a['observed']; current = a['revised_legacy_signed_literal_from']
    prior = np.load(prior_path,allow_pickle=False)
    assert np.array_equal(prior['timestamp_utc'],t) and prior['dispatch_qualified'][q].all()
    k = list(prior['plant_ids']).index(2693)
    prior_rmn = prior['prior_public_mw'][:,k]
    earlier_dispatch = prior['dispatch_public_mw'][:,k]
    reg = pd.read_csv(reg_path)
    rmn_rows = np.flatnonzero(pd.to_numeric(reg.plant_id,errors='coerce').eq(2693)&reg.role.eq('native'))
    assert len(rmn_rows)==13
    model = loadmat(model_path,simplify_cells=True,variable_names=['model'])['model']
    assert np.array_equal(model['generator_bus_ids'],reg.bus_id)
    rmn_parts=[]; load_parts=[]
    for path in shard_paths:
        d=loadmat(path,simplify_cells=True,variable_names=['profiles'])['profiles']
        rmn_parts.append(d['generator_PG_MW'][:,rmn_rows].sum(axis=1)/gamma)
        load_parts.append(d['bus_PD_MW'])
    rmn = np.concatenate(rmn_parts)
    # Counterfactual baseline uses the same native PG as the current export.
    changes=pd.read_csv(paths[-1],usecols=['hour_index','scenario','baseline_RMN_public_mw'])
    cf_rmn=changes.loc[changes.scenario.eq('niagara_month_shape_constrained_outside_ab')].sort_values('hour_index')
    assert np.array_equal(cf_rmn.hour_index,h)
    rmn_match=float(np.max(abs(cf_rmn.baseline_RMN_public_mw.to_numpy()[q]-rmn[q])))
    assert rmn_match<1e-9
    gates=pd.read_csv(gate_path)
    for name in names[:2]:
        g=gates.loc[gates.interface.eq(name)].sort_values('hour_index')
        assert np.array_equal(g.hour_index,h[q]) and g.complete_NY_cut.all()
        j=list(names).index(name)
        assert np.max(abs(g.primary_public_MW-current[q,j]))<1e-9
        assert np.max(abs(g.observed_public_numeric_MW-obs[q,j]))<1e-9
        assert np.max(abs(g.primary_public_MW-g.midpoint_public_MW-g.signed_half_loss_correction_public_MW))<1e-9
    eia=pd.read_csv(eia_path)
    eia=eia.loc[eia.plant_id.eq(2693)&eia.prime_mover.eq('HY')&eia.sheet.eq('Page 1 Generation and Fuel Data')].set_index('month')
    assert len(eia)==12 and eia.respondent_frequency.eq('M').all()
    monthly=[]
    for m in range(1,13):
        use=q&(months==m);physical=int((months==m).sum());source_energy=float(eia.loc[m,'net_generation_mwh'])
        source_mean=source_energy/physical
        row={'month':m,'qualified_hours':int(use.sum()),'physical_calendar_hours':physical,
             'excluded_calendar_hours':physical-int(use.sum()),'EIA_full_month_net_generation_MWh':source_energy,
             'EIA_calendar_mean_public_MW':source_mean,'current_RMN_selected_mean_public_MW':float(rmn[use].mean()),
             'frozen_RMN_prior_selected_mean_public_MW':float(prior_rmn[use].mean()),
             'current_minus_prior_selected_mean_public_MW':float((rmn[use]-prior_rmn[use]).mean()),
             'earlier_audit_dispatch_selected_mean_public_MW':float(earlier_dispatch[use].mean()),
             'EIA_calendar_mean_minus_current_selected_mean_public_MW':float(source_mean-rmn[use].mean()),
             'EIA_selected_hour_generation_observed':False,'complete_month_energy_claim':False}
        for j,key in enumerate(['Dysinger','WestCentral']):
            g=gates.loc[gates.interface.eq(names[j])&gates.hour_index.isin(h[use])]
            assert len(g)==use.sum()
            row[f'{key}_oracle_observed_minus_complete_cut_midpoint_MW']=float(g.observed_minus_midpoint_public_MW.mean())
            row[f'{key}_oracle_net_correction_primary_terminal_effect_held_MW']=float(g.required_net_correction_if_primary_terminal_effect_held_MW.mean())
            row[f'{key}_primary_minus_midpoint_terminal_effect_MW']=float(g.signed_half_loss_correction_public_MW.mean())
            row[f'{key}_current_primary_bias_MW']=float((current[use,j]-obs[use,j]).mean())
        monthly.append(row)
    monthly=pd.DataFrame(monthly)
    monthly.to_csv(OUT/'niagara_monthly_prior_oracle_comparison.csv',index=False)

    base=np.load(replay_paths[0],allow_pickle=False)
    assert np.all(base['qualified'][q]) and np.array_equal(base['timestamp_utc'],t)
    base_pred=base['interface_pf']/gamma
    score_rows=[]; change_rows=[]
    for scenario,path in zip(scenarios,replay_paths):
        d=np.load(path,allow_pickle=False)
        assert np.array_equal(d['timestamp_utc'],t) and np.array_equal(d['hour_index'],h)
        assert float(d['gamma'])==gamma and d['qualified'][q].all()
        pred=d['interface_pf']/gamma;assert np.isfinite(pred[q]).all()
        for m in range(13):
            use=q if m==0 else q&(months==m)
            for j,name in enumerate(names):
                met=metrics(pred[use,j],obs[use,j]);old=metrics(base_pred[use,j],obs[use,j])
                score_rows.append({'scenario':scenario,'month':m,'interface':name,**met,
                    'mae_change_from_same_cohort_DC_baseline_MW':met['mae_public_MW']-old['mae_public_MW'],
                    'mean_prediction_change_from_same_cohort_DC_baseline_MW':float((pred[use,j]-base_pred[use,j]).mean()),
                    'prediction_family':'saved_historical_DC_rescored_current_8170_mask','new_AC_solution':False})
        if scenario!='baseline':
            data=np.load(CF/'inputs'/f'{scenario}.npz',allow_pickle=False)
            assert data['qualified'][q].all() and np.array_equal(data['timestamp_utc'],t)
            applied=data['applied_RMN_model_mw']/gamma
            for m in range(1,13):
                use=q&(months==m)
                change_rows.append({'scenario':scenario,'month':m,'hours':int(use.sum()),
                    'applied_RMN_selected_mean_public_MW':float(applied[use].mean()),
                    'current_RMN_selected_mean_public_MW':float(rmn[use].mean()),
                    'RMN_selected_mean_change_public_MW':float((applied[use]-rmn[use]).mean()),
                    'original_constraint_cohort_hours':int(data['fixed_experiment_mask'].sum()),
                    'monthly_constraint_retargeted_to_current_8170_mask':False})
    scores=pd.DataFrame(score_rows)
    scores.to_csv(OUT/'niagara_saved_DC_counterfactuals_same8170_metrics.csv',index=False)
    pd.DataFrame(change_rows).to_csv(OUT/'niagara_saved_counterfactual_RMN_changes_same8170.csv',index=False)

    # Descriptive load and source-shape association; no coefficient is fitted or applied.
    pd_all=np.concatenate(load_parts)
    pol=model['loss_static'][0];groups=np.asarray(pol['bus_group'])[:pd_all.shape[1]]
    assert all(np.array_equal(groups,np.asarray(p['bus_group'])[:pd_all.shape[1]]) for p in model['loss_static'])
    ny_load_difference=float(np.max(abs(pd_all[q][:,np.isin(groups,np.arange(1,12))].sum(axis=1)-a['NY_gross_target_MW'][q].sum(axis=1))))
    assert ny_load_difference<1e-8
    predictors={'zone_A_gross_load_public_MW':pd_all[:,groups==1].sum(axis=1)/gamma,
                'zone_AB_gross_load_public_MW':pd_all[:,np.isin(groups,[1,2])].sum(axis=1)/gamma,
                'NY_gross_load_public_MW':pd_all[:,np.isin(groups,np.arange(1,12))].sum(axis=1)/gamma,
                'Niagara_current_PG_public_MW':rmn,'Niagara_frozen_prior_public_MW':prior_rmn}
    residual=(current[q,0]+current[q,1]-obs[q,0]-obs[q,1])/2
    assoc=[];labels={'raw':np.zeros(q.sum(),int),'within_month':months[q],
                    'within_local_hour':local.hour.to_numpy()[q],
                    'within_month_and_local_hour':months[q]*100+local.hour.to_numpy()[q]}
    for label,group in labels.items():
        e=pd.Series(residual);ee=e-e.groupby(group).transform('mean')
        for name,value in predictors.items():
            x=pd.Series(value[q]);xx=x-x.groupby(group).transform('mean')
            assoc.append({'predictor':name,'adjustment':label,'hours':int(q.sum()),
                'pearson_with_western_common_residual':float(np.corrcoef(xx,ee)[0,1]),
                'causal_effect_or_fit_claimed':False})
    pd.DataFrame(assoc).to_csv(OUT/'western_source_shape_associations.csv',index=False)
    after=[record(p) for p in paths];assert before==after
    result={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),
        'git_branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
        'git_HEAD':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'current_qualified_hours':int(q.sum()),'original_DC_counterfactual_cohort_hours':int(base['qualified'].sum()),
        'source_hashes_unchanged':True,'current_RMN_vs_counterfactual_baseline_max_difference_public_MW':rmn_match,
        'earlier_generation_audit_dispatch_vs_current_max_difference_public_MW':float(np.max(abs(earlier_dispatch[q]-rmn[q]))),
        'NY_gross_load_export_vs_current_annual_max_difference_model_MW':ny_load_difference,
        'EIA_calendar_mean_minus_current_selected_mean_range_public_MW':[float(monthly.EIA_calendar_mean_minus_current_selected_mean_public_MW.min()),float(monthly.EIA_calendar_mean_minus_current_selected_mean_public_MW.max())],
        'EIA_minus_current_selected_mean_positive_months':int((monthly.EIA_calendar_mean_minus_current_selected_mean_public_MW>0).sum()),
        'current_minus_frozen_prior_monthly_mean_range_public_MW':[float(monthly.current_minus_prior_selected_mean_public_MW.min()),float(monthly.current_minus_prior_selected_mean_public_MW.max())],
        'interpretation':[
          'Observed minus complete-cut midpoint is an oracle net-injection correction conditional on a midpoint meter convention and all other terms held fixed.',
          'Holding the primary-minus-midpoint terminal effect fixed instead gives observed minus primary. Neither correction is observed Niagara dispatch or identifies its cause.',
          'Full-calendar EIA mean minus selected-hour dispatch compares different populations; interpreting it as selected-hour correction requires representative missing hours.',
          'Saved DC counterfactuals retain original 8651-hour design and monthly constraints. Only scoring is remasked to8170; no source constraint is retargeted and no current AC counterfactual is solved.',
          'Load and source associations are descriptive correlations after stated group demeaning, not causal estimates.'],
        'default_model_changed':False,'new_PF_run':False,'sources':before,
        'producer':record(Path(__file__)),
        'outputs':[record(OUT/f) for f in ['niagara_monthly_prior_oracle_comparison.csv','niagara_saved_DC_counterfactuals_same8170_metrics.csv','niagara_saved_counterfactual_RMN_changes_same8170.csv','western_source_shape_associations.csv']]}
    (OUT/'niagara_prior_consistency_receipt.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['passed','current_qualified_hours','EIA_minus_current_selected_mean_positive_months','EIA_calendar_mean_minus_current_selected_mean_range_public_MW','current_minus_frozen_prior_monthly_mean_range_public_MW']}))


if __name__=='__main__':
    main()
