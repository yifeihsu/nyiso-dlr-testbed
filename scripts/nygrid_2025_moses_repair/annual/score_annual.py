"""Score the complete, independently validated repair on explicit cohorts."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat
from validate_annual import record, vec

ROOT=Path(__file__).resolve().parents[3]
CONVENTIONS=['legacy_signed_literal_from','oriented_source_side','oriented_target_side']
STATES=['pre_may','may21','may30','post_dover']


def stats(prediction,observation):
    e=prediction-observation;n=len(e)
    if not n:return {'hours':0,**{k:np.nan for k in ['mae_public_MW','rmse_public_MW','bias_public_MW','wape_percent']}}
    assert np.isfinite(e).all()
    return {'hours':n,'mae_public_MW':float(abs(e).mean()),'rmse_public_MW':float(np.sqrt(np.mean(e*e))),
        'bias_public_MW':float(e.mean()),'wape_percent':float(100*abs(e).sum()/abs(observation).sum())}


def main(run_dir):
    run_dir=run_dir.resolve();out=run_dir/'comparison';out.mkdir(exist_ok=True)
    receipt_path=run_dir/'annual_receipt.json';producer=json.loads(receipt_path.read_text())
    assert producer['completed'] and producer['months_complete']==12 and producer['source_files_unchanged_during_replay']
    check_path=run_dir/'validation/annual_input_accounting_review.json';check=json.loads(check_path.read_text())
    assert check['passed'] and check['completed'] and check['months_checked']==12
    physics_path=run_dir/'validation/annual_physics_review.json'
    physics=json.loads(physics_path.read_text());assert physics['passed'] and physics['completed_annual_review']
    old_path=ROOT/'output/nygrid_2025_physical_repair/annual/physical_repair_v1/comparison/comparison_arrays.npz';old=np.load(old_path,allow_pickle=False)
    axes_path=run_dir/'annual_axes.mat';axes=loadmat(axes_path,simplify_cells=True)
    network_path=run_dir/'annual_network.mat';templates=loadmat(network_path,simplify_cells=True)['templates']
    op_path=ROOT/'output/nygrid_2025_acpf_profile_audit/alignment/interface_operator_terms.csv';ops=pd.read_csv(op_path)
    names=old['interface_names'];gamma=float(axes['gamma']);hour=vec(axes,'hour_index',int);times=vec(axes,'timestamp_utc',str)
    source=vec(axes,'source_qualified',bool);current_good=vec(axes,'current_baseline_qualified',bool)
    state=vec(axes,'topology_state_index',int);keys=vec(axes,'branch_keys',str);parents=vec(axes,'branch_parent_row',int)
    assert np.array_equal(times,old['timestamp_utc']) and np.array_equal(source,old['source_qualified'])
    assert np.array_equal(current_good,old['candidate_qualified']) and current_good.sum()==8651 and source.sum()==8651
    assert gamma==float(old['gamma']) and np.array_equal(hour,np.arange(1,8761))
    observed=old['observed'];good=np.zeros(8760,bool);operating=good.copy();fulloperating=good.copy();seen=good.copy()
    status=np.full(8760,'',dtype='<U120');exceptions=good.copy()
    candidate={key:np.full((8760,7),np.nan) for key in CONVENTIONS}
    current={key:old['candidate_'+key] for key in CONVENTIONS}
    accounting={key:np.full((8760,n),np.nan) for key,n in [('NY_gross_target_MW',11),('NY_served_PD_MW',11),('NY_allocated_loss_MW',11),('regional_import_target_MW',3),('regional_import_solved_MW',3)]}
    paths=[receipt_path,check_path,physics_path,old_path,axes_path,network_path,op_path]
    for mon in range(1,13):
        path=run_dir/'monthly'/f'profile_PF_2025_{mon:02d}.mat';paths.append(path)
        d=loadmat(path,simplify_cells=True);ix=vec(d,'hour_index',int)-1
        assert not seen[ix].any();seen[ix]=True
        q=vec(d,'qualified',bool);assert np.all(~q|source[ix])
        good[ix]=q;exceptions[ix]=vec(d,'solver_exception',bool)
        operating[ix]=q&vec(d,'VQ_and_generator_assumption_gate',bool);fulloperating[ix]=q&vec(d,'full_operating_gate',bool)
        status[ix]=vec(d,'loss_status',str)
        for key in accounting:
            value=d['actual_budget_MW'][:,:11] if key=='NY_allocated_loss_MW' else d[key]
            accounting[key][ix[q]]=value[q]
        for s in np.unique(state[ix]):
            rows=np.flatnonzero(q&(state[ix]==s));target=ix[rows]
            if not len(rows):continue
            terms=ops.loc[ops.state.eq(STATES[int(s)-1])]
            assert len(terms)==34 and set(terms.interface_index)==set(range(1,8))
            local_keys=vec(templates[int(s)-1],'branch_keys',str)
            pf=d['PF'][rows];pt=d['PT'][rows]
            values={key:np.zeros((len(rows),7)) for key in CONVENTIONS}
            for term in terms.itertuples(index=False):
                first_key=str(term.first_runtime_branch_key);last_key=str(term.last_runtime_branch_key)
                assert local_keys[int(term.first_runtime_branch_row)-1]==first_key
                assert local_keys[int(term.last_runtime_branch_row)-1]==last_key
                f=int(np.flatnonzero(keys==first_key)[0]);t=int(np.flatnonzero(keys==last_key)[0]);j=int(term.interface_index)-1
                assert parents[f]==parents[t]==term.original_branch_row and str(names[j])==term.interface
                assert np.isfinite(pf[:,f]).all() and np.isfinite(pt[:,t]).all()
                sign=int(term.coefficient);values[CONVENTIONS[0]][:,j]+=sign*pf[:,f]
                values[CONVENTIONS[1]][:,j]+=pf[:,f] if sign>0 else pt[:,t]
                values[CONVENTIONS[2]][:,j]+=-pt[:,t] if sign>0 else -pf[:,f]
            for key in CONVENTIONS:candidate[key][target]=values[key]/gamma
    assert seen.all() and good.sum()==producer['policy_equation_qualified_hours']==check['candidate_qualified_hours']
    assert np.isfinite(observed[good]).all()
    for value in candidate.values():assert np.isfinite(value[good]).all() and np.isnan(value[~good]).all()
    paired=good&current_good;new=good&~current_good;lost=current_good&~good
    assert paired.sum()==producer['paired_current_baseline_hours']
    candidate['oriented_source_minus_target_loss']=candidate[CONVENTIONS[1]]-candidate[CONVENTIONS[2]]
    current['oriented_source_minus_target_loss']=current[CONVENTIONS[1]]-current[CONVENTIONS[2]]
    arrays={'hour_index':hour,'timestamp_utc':times,'interface_names':names,'gamma':gamma,'source_qualified':source,
        'candidate_qualified':good,'current_baseline_qualified':current_good,'paired_qualified':paired,
        'candidate_new_success':new,'current_success_lost':lost,'operating_qualified':operating,
        'full_operating_qualified':fulloperating,'observed':observed,'topology_state_index':state,
        'solver_exception':exceptions,'loss_status':status,**accounting}
    for key,value in candidate.items():arrays['candidate_'+key]=value
    for key,value in current.items():arrays['current_baseline_'+key]=value
    array_target=out/'comparison_arrays.npz';np.savez_compressed(array_target,**arrays)
    cohort=pd.DataFrame({key:arrays[key] for key in ['hour_index','timestamp_utc','source_qualified','candidate_qualified','current_baseline_qualified','paired_qualified','candidate_new_success','current_success_lost','operating_qualified','full_operating_qualified','solver_exception','loss_status']})
    cohort_target=out/'comparison_cohort.csv';cohort.to_csv(cohort_target,index=False)
    months=pd.DatetimeIndex(pd.to_datetime(times,utc=True)).tz_convert('America/New_York').month.to_numpy()
    periods={'annual':np.ones(8760,bool),**{f'month_{m:02d}':months==m for m in range(1,13)},'post_Dover':state==4}
    cohorts={'candidate_all_success':(good,['candidate']),
        'paired_current_baseline':(paired,['candidate','current_baseline']),
        'candidate_new_success':(new,['candidate']),
        'current_success_lost':(lost,['current_baseline']),
        'current_baseline_all8651':(current_good,['current_baseline'])}
    predictions={'candidate':candidate,'current_baseline':current};rows=[]
    for label,(mask,models) in cohorts.items():
        for period,p_mask in periods.items():
            use=mask&p_mask
            for model_name in models:
                for convention in CONVENTIONS:
                    for j,name in enumerate(names):rows.append({'cohort':label,'period':period,'model':model_name,'convention':convention,'interface':str(name),
                        **stats(predictions[model_name][convention][use,j],observed[use,j]),'diagnostic_only':True,'physical_P32_meter_certified':False})
    metric_target=out/'public_interface_metrics.csv';metrics=pd.DataFrame(rows);metrics.to_csv(metric_target,index=False)
    receipt={'passed':True,'completed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'run_label':producer['run_label'],
        'source_qualified_hours':int(source.sum()),'candidate_qualified_hours':int(good.sum()),'current_baseline_qualified_hours':8651,
        'paired_qualified_hours':int(paired.sum()),'candidate_new_success_hours':int(new.sum()),'current_success_lost_hours':int(lost.sum()),
        'operating_qualified_hours':int(operating.sum()),'full_operating_qualified_hours':int(fulloperating.sum()),'solver_exceptions':int(exceptions.sum()),
        'all8760_clock_rows_retained':True,'failed_or_unqualified_hours_are_not_predictions':True,
        'public_prediction_scaling':'Aggregate model MW divided once by frozen gamma; observations already public numeric MW.',
        'current_scaling':'Saved currents remain model amperes; never divided by gamma.',
        'physical_P32_meter_membership_certified':False,'P32_numeric_as_MW_header_interpretation_independently_certified':False,
        'cohort_and_terminal_convention_not_selected_by_score':True,'dependencies':[record(p) for p in paths],
        'outputs':[record(array_target),record(cohort_target),record(metric_target)],'producer':record(Path(__file__))}
    (out/'scoring_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:receipt[key] for key in ['passed','candidate_qualified_hours','paired_qualified_hours','candidate_new_success_hours','current_success_lost_hours','operating_qualified_hours']}))
    print(metrics.query("period=='annual' and cohort=='paired_current_baseline' and convention=='legacy_signed_literal_from'")[['model','interface','hours','mae_public_MW','wape_percent','bias_public_MW']].to_string(index=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True);args=p.parse_args();main(args.run_dir)
