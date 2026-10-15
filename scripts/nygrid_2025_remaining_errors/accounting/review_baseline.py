"""Bounded independent review of current primary metrics and lag cohorts."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_remaining_errors/accounting'
BASE=ROOT/'output/nygrid_2025_remaining_errors/baseline'


def record(path):return {'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def metric(model,observed):
    error=model-observed
    return {'hours':len(error),'mae_public_MW':float(np.mean(abs(error))),
            'rmse_public_MW':float(np.sqrt(np.mean(error**2))),'bias_public_MW':float(np.mean(error)),
            'wape_percent':float(100*np.sum(abs(error))/np.sum(abs(observed)))}


def main():
    path=ROOT/'output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_arrays.npz'
    d=np.load(path,allow_pickle=False);q=d['revised_qualified'];m=d['revised_legacy_signed_literal_from'];o=d['observed'];names=d['interface_names'].tolist()
    assert q.sum()==8170 and np.isfinite(o[q]).all()
    published=pd.read_csv(BASE/'annual_metrics.csv').set_index('interface');annual_error=0.
    for j,name in enumerate(names):
        expected=metric(m[q,j],o[q,j])
        annual_error=max(annual_error,max(abs(published.loc[name,k]-v) for k,v in expected.items()))
    assert annual_error<1e-9
    error=m[q]-o[q];correlation=float(np.corrcoef(error[:,0],error[:,1])[0,1]);increment=error[:,1]-error[:,0]
    summary=json.loads((BASE/'baseline_summary.json').read_text());west=summary['west_pair']
    assert abs(west['pearson']-correlation)<1e-12 and abs(west['difference_MAE_public_MW']-np.mean(abs(increment)))<1e-9
    assert abs(west['difference_bias_public_MW']+increment.mean())<1e-9
    states=np.array(['pre_may']*3359+['may21']*216+['may30']*4896+['post_dover']*289)
    finite=np.isfinite(o).all(axis=1);strict=np.zeros(8760,bool);common=np.zeros(8760,bool)
    for i in range(1,8759):
        common[i]=q[i] and bool(finite[i-1:i+2].all()) and len(set(states[i-1:i+2]))==1
        strict[i]=common[i] and bool(q[i-1:i+2].all())
    assert strict.sum()==7936 and common.sum()==8042
    masks=pd.read_csv(BASE/'lag_cohorts.csv')
    assert np.array_equal(masks.fully_qualified_triplet_same_state,strict)
    assert np.array_equal(masks.qualified_center_observation_triplet_same_state,common)
    assert np.array_equal(masks.hour_index,np.arange(1,8761)) and np.array_equal(masks.state,states)
    clock=pd.to_datetime(d['timestamp_utc'],utc=True);assert (np.diff(clock.asi8)==3600*10**9).all()
    lag=pd.read_csv(BASE/'lag_diagnostics.csv');lag=lag[lag.cohort.eq('fully_qualified_triplet_same_state')];lag_error=0.;ix=np.flatnonzero(strict)
    for row in lag.itertuples():
        j=names.index(row.interface);expected=metric(m[ix,j],o[ix+row.observation_shift_hours,j])
        lag_error=max(lag_error,max(abs(getattr(row,k)-v) for k,v in expected.items()))
    assert len(lag)==21 and lag_error<1e-9
    local=clock.tz_convert('America/New_York');groups={'hourly':np.arange(1,8761),'daily':local.strftime('%Y-%m-%d').to_numpy(),'monthly':local.month.to_numpy()}
    aggregation=pd.read_csv(BASE/'time_aggregation_metrics.csv');aggregation_error=0.
    for row in aggregation.itertuples():
        group=groups[row.resolution];labels=np.unique(group[q]);columns=list(range(7)) if row.interface=='POOLED_7_DIAGNOSTIC_CUTS' else [names.index(row.interface)]
        differences=[];observations=[];counts=[]
        for label in labels:
            use=q&(group==label);counts.append(int(use.sum()));differences.append((m[use][:,columns]-o[use][:,columns]).sum(axis=0));observations.append(o[use][:,columns].sum(axis=0))
        delta=np.asarray(differences);obs=np.asarray(observations);count=np.asarray(counts);width=len(columns);assert count.sum()==8170
        expected={'WAPE_of_qualified_hour_sums_percent':100*np.abs(delta).sum()/np.abs(obs).sum(),
            'MAE_of_bin_means_hour_weighted_public_MW':np.abs(delta).sum()/(8170*width),
            'RMSE_of_bin_means_hour_weighted_public_MW':np.sqrt(np.sum((delta/count[:,None])**2*count[:,None])/(8170*width)),
            'weighted_bias_public_MW':delta.sum()/(8170*width)}
        aggregation_error=max(aggregation_error,max(abs(getattr(row,k)-v) for k,v in expected.items()))
    assert len(aggregation)==24 and aggregation_error<1e-8
    sources=[path,BASE/'annual_metrics.csv',BASE/'baseline_summary.json',BASE/'lag_cohorts.csv',BASE/'lag_diagnostics.csv',BASE/'time_aggregation_metrics.csv',Path(__file__)]
    result={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'scope':'Seven primary annual metrics, western residual arithmetic, fixed same-state lag cohorts and aggregation semantics',
        'qualified_hours':8170,'annual_interface_count':7,'max_primary_metric_difference':annual_error,
        'western_error_correlation':correlation,'incremental_B_MAE_public_MW':float(np.mean(abs(increment))),
        'incremental_B_bias_WC_minus_DY_public_MW':float(increment.mean()),
        'baseline_pair_difference_sign':'Baseline pair_stats uses DY minus WC; incremental B uses WC minus DY. MAE is identical and signed bias reverses.',
        'strict_lag_cohort_hours':int(strict.sum()),'qualified_center_lag_cohort_hours':int(common.sum()),
        'strict_lag_metric_rows_checked':len(lag),'max_strict_lag_metric_difference':lag_error,
        'lag_semantics':'model(t) against observation(t+shift), -1/0/+1 UTC hours, all using the identical qualified same-state center cohort',
        'aggregation_rows_checked':len(aggregation),'max_aggregation_metric_difference':aggregation_error,
        'aggregation_scope':'All8170positions retained; qualified hour sums within local calendar bins; cancellation is explicit and not improved hourly accuracy',
        'new_model_run_or_fit':False,'baseline_outputs_modified':False,'sources':[record(p) for p in sources]}
    (OUT/'independent_baseline_review.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='sources'}))


if __name__=='__main__':main()
