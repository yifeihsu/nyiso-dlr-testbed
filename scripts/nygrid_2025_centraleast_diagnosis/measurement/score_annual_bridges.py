"""Post-hoc scoring of controlled annual experiments on the frozen8494 hours.

No power-flow solver is called. Loss-loaded DCPF uses previously solved AC
losses as diagnostic input; it is not an independent prediction or a unique
causal attribution. Mean flow shares are distinct from WAPE changes.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat
from account_central_east import ROOT, NAME, metrics, period_masks, record, sha

BASE = ROOT / 'output/nygrid_2025_centraleast_diagnosis'
OUT = BASE / 'measurement/annual_bridges'
CE = 4


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        'construction_arrays':BASE/'experiments/annual_DC_bridge/annual_DC_bridge_arrays.mat',
        'construction_receipt':BASE/'experiments/annual_DC_bridge/annual_DC_bridge_receipt.json',
        'loss_arrays':BASE/'experiments/annual_loss_loaded_DCF/annual_loss_loaded_arrays.mat',
        'loss_receipt':BASE/'experiments/annual_loss_loaded_DCF/annual_loss_loaded_receipt.json',
        'measurement_receipt':BASE/'measurement/measurement_receipt.json',
        'measurement_hours':BASE/'measurement/CE_hourly_accounting.csv',
        'member_terms':BASE/'measurement/original_member_hourly_terms.csv',
        'public':ROOT/'output/nygrid_2025_inputs/load_source/interface_wide.csv',
        'frozen_arrays':ROOT/'output/nygrid_2025_acpf_profile_audit/comparison/comparison_arrays.npz',
    }
    records = [record(p) for p in files.values()]
    construction_receipt=json.loads(files['construction_receipt'].read_text())
    loss_receipt=json.loads(files['loss_receipt'].read_text())
    assert construction_receipt['completed'] and construction_receipt['passed'] and not construction_receipt['OPF_or_fitting_used']
    assert loss_receipt['completed'] and loss_receipt['passed'] and not loss_receipt['OPF_or_fitting_used']
    assert loss_receipt['only_diagnostic_PD_changed'] and loss_receipt['all_three_allocate_same_total_baseline_AC_losses']
    assert loss_receipt['non_slack_PG_six_transfers_and_network_parameters_preserved']
    construction=loadmat(files['construction_arrays'],simplify_cells=True,variable_names=['cohort','variant_names','interface_model_MW',
        'CE_member_model_MW','converged','audit_passed','hour_index','timestamp_utc','gamma','source_qualified','state_index',
        'CE_signed_parent_rows','archived_DC_interface_model_MW'])
    loss=loadmat(files['loss_arrays'],simplify_cells=True,variable_names=['cohort','labels','interface_model_MW','baseline_AC_interface_model_MW',
        'audit_passed','hour_index','timestamp_utc','gamma','source_qualified','state_index','baseline_detailed_DCF_interface_model_MW',
        'archived_DC_interface_model_MW','construction_delta_model_MW','loss_allocation_delta_model_MW',
        'remaining_AC_minus_loss_loaded_DCF_model_MW','baseline_AC_loss_MW','max_non_slack_PG_change_MW'])
    previous=pd.read_csv(files['measurement_hours'],float_precision='round_trip')
    old=np.load(files['frozen_arrays'],allow_pickle=False)
    hours=old['hour_index'];times=old['timestamp_utc'].astype(str);mask=old['ACPF_comparison_cohort'].astype(bool)
    source=old['source_qualified'].astype(bool);gamma=float(old['gamma'])
    assert mask.sum()==8494 and source.sum()==8651
    for d in [construction,loss]:
        assert np.array_equal(d['hour_index'],hours) and np.array_equal(np.asarray(d['timestamp_utc']).astype(str),times)
        assert np.array_equal(np.asarray(d['cohort'],bool),mask) and np.array_equal(np.asarray(d['source_qualified'],bool),source)
        assert float(d['gamma'])==gamma and np.asarray(d['audit_passed'],bool)[mask].all()
        assert np.max(np.abs(d['archived_DC_interface_model_MW'][mask]/gamma-old['frozen_DC'][mask]))<1e-7
    assert np.asarray(construction['converged'],bool)[mask].all()
    assert np.array_equal(construction['CE_signed_parent_rows'],np.array([-33,-36,-40,-42]))
    cnames=np.asarray(construction['variant_names']).astype(str).tolist()
    lnames=np.asarray(loss['labels']).astype(str).tolist()
    assert cnames==['detailed_AC_network_DCPF','restore_parent224_X','restore_parent41_X','restore_all33_X']
    assert lnames==['half_each_runtime_branch_end','all_at_runtime_from_end','all_at_runtime_to_end']
    assert np.max(np.abs(construction['CE_member_model_MW'][mask].sum(axis=1)-construction['interface_model_MW'][mask,CE,:]))<1e-8
    assert np.max(np.abs(loss['baseline_detailed_DCF_interface_model_MW'][mask]-construction['interface_model_MW'][mask,:,0]))<1e-8
    assert np.max(np.abs(loss['baseline_AC_interface_model_MW'][mask]/gamma-old['legacy_signed_literal_from'][mask]))<1e-7
    assert np.max(np.abs(loss['max_non_slack_PG_change_MW'][mask]))<1e-8
    public=pd.read_csv(files['public'],float_precision='round_trip');y=public[NAME].to_numpy(float)
    assert np.array_equal(public.timestamp_utc,times) and np.array_equal(y,old['observed'][:,CE],equal_nan=True)
    assert np.array_equal(previous.hour_index,hours) and np.array_equal(previous.timestamp_utc,times)
    state=previous.dated_state.to_numpy(str);local=pd.to_datetime(times,utc=True).tz_convert('America/New_York')
    expected_state=np.array([{'pre_may':1,'may21':2,'may30':3,'post_dover':4}[s] for s in state])
    assert np.array_equal(construction['state_index'],expected_state) and np.array_equal(loss['state_index'],expected_state)
    model={'archived_DC':old['frozen_DC'][:,CE].copy(),
        'detailed_network_DCF':construction['interface_model_MW'][:,CE,0]/gamma,
        'baseline_AC_legacy':old['legacy_signed_literal_from'][:,CE].copy(),
        'restore_parent224_X_DCF':construction['interface_model_MW'][:,CE,1]/gamma,
        'restore_parent41_X_DCF':construction['interface_model_MW'][:,CE,2]/gamma,
        'restore_all33_X_DCF':construction['interface_model_MW'][:,CE,3]/gamma,
        'loss_half_each_end_DCF':loss['interface_model_MW'][:,CE,0]/gamma,
        'loss_all_at_runtime_from_end_DCF':loss['interface_model_MW'][:,CE,1]/gamma,
        'loss_all_at_runtime_to_end_DCF':loss['interface_model_MW'][:,CE,2]/gamma}
    for values in model.values():
        assert np.isfinite(values[mask]).all();values[~mask]=np.nan
    assert np.max(np.abs(model['restore_all33_X_DCF'][mask]-model['archived_DC'][mask]))<1e-7
    periods=period_masks(local,state);metric_rows=[];step_rows=[];restore_rows=[];allocation_rows=[]
    steps=[('construction','archived_DC','detailed_network_DCF'),
        ('same_network_AC_step','detailed_network_DCF','baseline_AC_legacy'),
        ('total_AC_minus_archived_DC','archived_DC','baseline_AC_legacy'),
        ('half_end_loss_loading','detailed_network_DCF','loss_half_each_end_DCF'),
        ('remaining_AC_minus_half_loss_DCF','loss_half_each_end_DCF','baseline_AC_legacy')]
    for period,period_mask in periods:
        use=mask&period_mask
        if not use.any():continue
        stats={name:metrics(values,y,use) for name,values in model.items()}
        metric_rows += [dict(period=period,model=name,cohort='fixed_matched_8494',**value) for name,value in stats.items()]
        total_mean=float((model['baseline_AC_legacy'][use]-model['archived_DC'][use]).mean())
        total_wape=stats['baseline_AC_legacy']['WAPE_percent']-stats['archived_DC']['WAPE_percent']
        for label,start,end in steps:
            change=model[end][use]-model[start][use]
            step_rows.append(dict(period=period,step=label,start_model=start,end_model=end,hours=int(use.sum()),
                mean_flow_change_public_MW=float(change.mean()),mean_absolute_flow_change_public_MW=float(np.abs(change).mean()),
                minimum_flow_change_public_MW=float(change.min()),maximum_flow_change_public_MW=float(change.max()),
                bias_change_public_MW=stats[end]['bias_public_MW']-stats[start]['bias_public_MW'],
                MAE_change_public_MW=stats[end]['MAE_public_MW']-stats[start]['MAE_public_MW'],
                WAPE_change_percentage_points=stats[end]['WAPE_percent']-stats[start]['WAPE_percent'],
                share_of_total_mean_flow_change_percent=float(100*change.mean()/total_mean),
                share_of_total_WAPE_change_along_this_ordered_bridge_percent=float(100*(stats[end]['WAPE_percent']-stats[start]['WAPE_percent'])/total_wape),
                flow_share_must_not_be_interpreted_as_WAPE_share=True))
        construction_change=model['detailed_network_DCF'][use]-model['archived_DC'][use]
        removed=model['detailed_network_DCF'][use]-model['restore_parent224_X_DCF'][use]
        restore_rows.append(dict(period=period,hours=int(use.sum()),mean_construction_shift_public_MW=float(construction_change.mean()),
            mean_shift_removed_by_restoring_224_X_public_MW=float(removed.mean()),
            percent_of_mean_construction_shift_removed=float(100*removed.mean()/construction_change.mean()),
            residual_mean_shift_after_restore224_public_MW=float((model['restore_parent224_X_DCF'][use]-model['archived_DC'][use]).mean()),
            restore224_WAPE_percent=stats['restore_parent224_X_DCF']['WAPE_percent'],
            restore41_maximum_absolute_flow_effect_public_MW=float(np.abs(model['restore_parent41_X_DCF'][use]-model['detailed_network_DCF'][use]).max()),
            restore_all33_maximum_absolute_vs_archived_DC_public_MW=float(np.abs(model['restore_all33_X_DCF'][use]-model['archived_DC'][use]).max()),
            controlled_DCF_X_effect_not_WAPE_fraction_or_model_promotion=True))
        for allocation in ['half_each_end','all_at_runtime_from_end','all_at_runtime_to_end']:
            name='loss_'+allocation+'_DCF';increment=model[name][use]-model['detailed_network_DCF'][use]
            residual=model['baseline_AC_legacy'][use]-model[name][use]
            allocation_rows.append(dict(period=period,allocation=allocation,hours=int(use.sum()),
                mean_loss_loading_flow_increment_public_MW=float(increment.mean()),
                mean_remaining_AC_minus_loaded_DCF_public_MW=float(residual.mean()),
                mean_absolute_remaining_public_MW=float(np.abs(residual).mean()),maximum_absolute_remaining_public_MW=float(np.abs(residual).max()),
                mean_loading_fraction_of_same_network_AC_flow_change_percent=float(100*increment.mean()/(model['baseline_AC_legacy'][use]-model['detailed_network_DCF'][use]).mean()),
                loaded_DCF_WAPE_percent=stats[name]['WAPE_percent'],conditioned_on_solved_model_AC_losses=True,
                independent_prediction=False,allocation_sensitivity_not_confidence_interval=True))
    metric_frame=pd.DataFrame(metric_rows);step_frame=pd.DataFrame(step_rows)
    metric_frame.to_csv(OUT/'CE_stage_metrics.csv',index=False,lineterminator='\n')
    step_frame.to_csv(OUT/'CE_ordered_stage_changes.csv',index=False,lineterminator='\n')
    pd.DataFrame(restore_rows).to_csv(OUT/'CE_X_restoration_effects.csv',index=False,lineterminator='\n')
    allocation_frame=pd.DataFrame(allocation_rows);allocation_frame.to_csv(OUT/'CE_loss_allocation_sensitivity.csv',index=False,lineterminator='\n')
    hourtable=previous.loc[:,['hour_index','timestamp_utc','local_timestamp','dated_state','source_qualified','AC_equation_profile_qualified']].copy()
    hourtable['fixed_bridge_cohort']=mask;hourtable['observed_CE_public_MW']=y
    for name,values in model.items():hourtable[name+'_public_MW']=values
    hourtable['construction_delta_public_MW']=model['detailed_network_DCF']-model['archived_DC']
    hourtable['same_network_AC_delta_public_MW']=model['baseline_AC_legacy']-model['detailed_network_DCF']
    hourtable['half_loss_loading_delta_public_MW']=model['loss_half_each_end_DCF']-model['detailed_network_DCF']
    hourtable['half_loss_remainder_public_MW']=model['baseline_AC_legacy']-model['loss_half_each_end_DCF']
    hourtable.to_csv(OUT/'CE_annual_bridge_hourly.csv',index=False,lineterminator='\n')
    original=pd.read_csv(files['member_terms'],float_precision='round_trip')
    original=original.loc[original.role=='CE_member']
    dc_member=original.pivot(index='hour_index',columns='original_branch_row',values='DC_signed_public_MW').reindex(hours).to_numpy()
    ac_member=original.pivot(index='hour_index',columns='original_branch_row',values='AC_legacy_signed_literal_from_signed_public_MW').reindex(hours).to_numpy()
    members=np.array([33,36,40,42]);member_rows=[]
    assert np.max(np.abs(dc_member[mask].sum(axis=1)-model['archived_DC'][mask]))<1e-7
    for period,period_mask in periods:
        use=mask&period_mask
        if not use.any():continue
        for j,parent in enumerate(members):
            newer=construction['CE_member_model_MW'][:,j,0]/gamma
            restored=construction['CE_member_model_MW'][:,j,1]/gamma
            member_rows.append(dict(period=period,original_branch_row=int(parent),hours=int(use.sum()),
                mean_archived_DC_term_public_MW=float(dc_member[use,j].mean()),mean_detailed_network_DCF_term_public_MW=float(newer[use].mean()),
                mean_AC_term_public_MW=float(ac_member[use,j].mean()),
                mean_construction_shift_public_MW=float((newer[use]-dc_member[use,j]).mean()),
                mean_same_network_AC_shift_public_MW=float((ac_member[use,j]-newer[use]).mean()),
                mean_effect_removed_by_restoring224_X_public_MW=float((newer[use]-restored[use]).mean()),
                member_accounting_not_independent_member_parameter_effect=True))
    pd.DataFrame(member_rows).to_csv(OUT/'CE_member_stage_accounting.csv',index=False,lineterminator='\n')
    annual=metric_frame.loc[metric_frame.period=='annual'].set_index('model')
    delta=step_frame.loc[step_frame.period=='annual'].set_index('step')
    allocations=allocation_frame.loc[allocation_frame.period=='annual'].set_index('allocation')
    restore=pd.DataFrame(restore_rows).query("period=='annual'").iloc[0]
    assert abs(delta.loc['construction','mean_flow_change_public_MW']+delta.loc['same_network_AC_step','mean_flow_change_public_MW']-delta.loc['total_AC_minus_archived_DC','mean_flow_change_public_MW'])<1e-8
    assert abs(delta.loc['construction','WAPE_change_percentage_points']+delta.loc['same_network_AC_step','WAPE_change_percentage_points']-delta.loc['total_AC_minus_archived_DC','WAPE_change_percentage_points'])<1e-10
    for r in records:assert sha(ROOT/r['path'])==r['sha256'],r['path']
    scalar=lambda row:{k:(v.item() if isinstance(v,np.generic) else v) for k,v in row.items()}
    summary=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        status='fixed_cohort_controlled_experiment_scoring_complete',matched_hours=int(mask.sum()),interface=NAME,gamma=gamma,
        exact_same_observations_cohort_time_and_operator_for_all_stages=True,
        annual_model_metrics={name:scalar(row) for name,row in annual.iterrows()},
        annual_ordered_changes={name:scalar(row) for name,row in delta.iterrows()},
        annual_224_restoration=scalar(restore),annual_loss_allocation_sensitivity={name:scalar(row) for name,row in allocations.iterrows()},
        flow_shares_are_not_WAPE_shares=True,
        construction_mean_flow_share_percent=float(delta.loc['construction','share_of_total_mean_flow_change_percent']),
        construction_WAPE_increment_percentage_points=float(delta.loc['construction','WAPE_change_percentage_points']),
        same_network_AC_WAPE_increment_percentage_points=float(delta.loc['same_network_AC_step','WAPE_change_percentage_points']),
        loss_loading_conditioned_on_previously_solved_model_AC_losses=True,
        loss_loading_is_independent_prediction=False,unique_physical_causal_attribution_claimed=False,
        diagnostic_parameter_or_loss_allocation_variants_promoted_to_production=False,
        earlier_measurement_outputs_overwritten=False,PF_or_OPF_run_by_this_script=False,
        qualifications=['The construction bridge changes model X values before comparing AC and DCPF on the same detailed network.',
            'The row224 intervention quantifies its X effect within the declared DCPF counterfactual, not a fraction of WAPE or proof of its real physical impedance.',
            'Loss-loaded DCPF adds known model AC branch losses as artificial bus demand; it is an explanatory reconstruction, not an independently predicted operating state.',
            'From-end, to-end and half-end allocations are nonunique bookkeeping sensitivities, not a confidence interval.',
            'Mean flow changes and WAPE changes telescope separately along this declared ordered path; their percentage shares are not interchangeable.',
            'Public P32 physical-meter correspondence/quantity assumptions and inherited AC operating-limit failures remain unchanged.'],
        dependencies=records+[record(Path(__file__)),record(Path(__file__).with_name('account_central_east.py'))],
        outputs=[record(p) for p in sorted(OUT.glob('*.csv'))])
    (OUT/'annual_bridge_scoring_receipt.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(annual[['mean_prediction_public_MW','bias_public_MW','MAE_public_MW','WAPE_percent']].to_string())
    print(delta[['mean_flow_change_public_MW','WAPE_change_percentage_points']].to_string())
    print(allocations[['mean_loss_loading_flow_increment_public_MW','mean_remaining_AC_minus_loaded_DCF_public_MW','mean_absolute_remaining_public_MW']].to_string())


if __name__=='__main__':main()
