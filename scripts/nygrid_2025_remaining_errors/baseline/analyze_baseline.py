"""Describe remaining seven-interface residuals on the frozen current cohort.

No PF/OPF, parameter fitting, resampling, interpolation, or official metric
changes. Daily/monthly sums and +/-1h shifts are explicitly scoped diagnostic
views of the same saved series, not replacement performance claims.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_remaining_errors/baseline'
SOURCE = ROOT / 'output/nygrid_2025_ac_loss_revision/comparison/combined'
CONVENTION = 'legacy_signed_literal_from'
SEASONS = {12:'DJF',1:'DJF',2:'DJF',3:'MAM',4:'MAM',5:'MAM',6:'JJA',7:'JJA',8:'JJA',9:'SON',10:'SON',11:'SON'}


def record(path):
    with path.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=digest)


def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,np.ndarray):return clean(value.tolist())
    if isinstance(value,np.generic):return clean(value.item())
    if isinstance(value,float) and not np.isfinite(value):return None
    return value


def stats(model,observed):
    model=np.asarray(model,float);observed=np.asarray(observed,float)
    assert model.shape==observed.shape and np.isfinite(model).all() and np.isfinite(observed).all()
    e=model-observed;n=len(e)
    if not n:return dict(hours=0)
    abs_e=np.abs(e);mean_obs_abs=float(np.mean(np.abs(observed)));bias=float(e.mean());mse=float(np.mean(e*e))
    centered_mse=float(np.mean((e-bias)**2));assert abs(mse-bias*bias-centered_mse)<max(1e-8,1e-12*mse)
    denom=np.abs(model)+np.abs(observed);smape=np.divide(200*abs_e,denom,out=np.zeros_like(abs_e),where=denom>0)
    nonzero=np.abs(observed)>1e-12
    corr=float(np.corrcoef(model,observed)[0,1]) if np.std(model)>0 and np.std(observed)>0 else np.nan
    return dict(hours=n,mae_public_MW=float(abs_e.mean()),rmse_public_MW=float(np.sqrt(mse)),
        bias_public_MW=bias,wape_percent=float(100*abs_e.sum()/np.abs(observed).sum()) if mean_obs_abs else np.nan,
        mean_abs_observed_public_MW=mean_obs_abs,mean_observed_public_MW=float(observed.mean()),mean_model_public_MW=float(model.mean()),
        median_signed_error_public_MW=float(np.median(e)),median_abs_error_public_MW=float(np.median(abs_e)),
        p90_abs_error_public_MW=float(np.quantile(abs_e,.90)),p95_abs_error_public_MW=float(np.quantile(abs_e,.95)),
        p99_abs_error_public_MW=float(np.quantile(abs_e,.99)),max_abs_error_public_MW=float(abs_e.max()),
        centered_rmse_public_MW=float(np.sqrt(centered_mse)),bias_squared_MSE_share_percent=100*bias*bias/mse if mse else 0.,
        normalized_RMSE_percent=100*np.sqrt(mse)/mean_obs_abs if mean_obs_abs else np.nan,
        symmetric_MAPE_percent=float(smape.mean()),nonzero_observed_hours=int(nonzero.sum()),
        median_APE_nonzero_percent=float(np.median(100*abs_e[nonzero]/np.abs(observed[nonzero]))) if nonzero.any() else np.nan,
        observed_std_public_MW=float(np.std(observed)),model_std_public_MW=float(np.std(model)),
        residual_std_public_MW=float(np.std(e)),model_observed_correlation=corr,
        variance_explained_R2=1-mse/float(np.var(observed)) if np.var(observed)>0 else np.nan,
        signed_error_positive_fraction=float(np.mean(e>0)),signed_error_negative_fraction=float(np.mean(e<0)),
        zero_observed_hours=int((~nonzero).sum()),absolute_error_sum_public_MW_samples=float(abs_e.sum()),
        absolute_observation_sum_public_MW_samples=float(np.abs(observed).sum()))


def group_analysis(meta,m,o,names,dimension):
    rows=[];coverage=[]
    for group,positions in meta.groupby(dimension,sort=True).groups.items():
        index=np.asarray(positions,int);q=meta.qualified.to_numpy()[index];take=index[q]
        c=dict(dimension=dimension,group=str(group),clock_hours=len(index),source_hours=int(meta.source.to_numpy()[index].sum()),
            qualified_hours=len(take),source_excluded_hours=int((~meta.source.to_numpy()[index]).sum()),
            source_failed_hours=int((meta.source.to_numpy()[index]&~meta.qualified.to_numpy()[index]).sum()),
            qualified_fraction_of_clock=float(q.mean()))
        coverage.append(c)
        for j,name in enumerate(names):
            rows.append(dict(interface=name,**c,**stats(m[take,j],o[take,j])))
    return pd.DataFrame(rows),pd.DataFrame(coverage)


def pair_stats(a,b):
    centered=np.column_stack([a-a.mean(),b-b.mean()]);cov=np.cov(centered,rowvar=False,ddof=0);trace=float(np.trace(cov))
    common=(a+b)/np.sqrt(2);difference=a-b
    top=max(1,int(np.ceil(len(a)*.10)));one=set(np.argsort(np.abs(a),kind='stable')[-top:]);two=set(np.argsort(np.abs(b),kind='stable')[-top:])
    return dict(hours=len(a),pearson=float(np.corrcoef(a,b)[0,1]),spearman=float(spearmanr(a,b).statistic),
        difference_bias_public_MW=float(difference.mean()),difference_MAE_public_MW=float(np.mean(np.abs(difference))),
        difference_std_public_MW=float(np.std(difference)),equal_weight_common_mode_variance_percent=100*float(np.var(common))/trace,
        first_PC_variance_percent=100*float(np.linalg.eigvalsh(cov).max())/trace,
        descriptive_OLS_slope_B_on_A=float(cov[0,1]/cov[0,0]),
        top10pct_count_each=top,top10pct_overlap_hours=len(one&two),top10pct_overlap_fraction=float(len(one&two)/top),
        top10pct_Jaccard=float(len(one&two)/len(one|two)))


def temporal_aggregation(meta,m,o,names):
    summaries=[];bins=[];good=meta.qualified.to_numpy();n=int(good.sum())
    for resolution,field in [('hourly','hour_index'),('daily','local_date'),('monthly','month')]:
        expected=meta.groupby(field).size();groups=meta.loc[good].groupby(field,sort=True).groups
        modeled=[];observed=[];counts=[];complete=[]
        for label,positions in groups.items():
            take=np.asarray(positions,int);mm=m[take].sum(axis=0);oo=o[take].sum(axis=0);count=len(take)
            modeled.append(mm);observed.append(oo);counts.append(count);complete.append(count==int(expected[label]))
            if resolution!='hourly':
                for j,name in enumerate(names):
                    bins.append(dict(resolution=resolution,bin=str(label),interface=name,qualified_hours=count,clock_hours=int(expected[label]),
                        full_calendar_bin_qualified=count==int(expected[label]),model_mean_public_MW=float(mm[j]/count),
                        observed_mean_public_MW=float(oo[j]/count),residual_mean_public_MW=float((mm[j]-oo[j])/count),
                        residual_sum_public_MW_samples=float(mm[j]-oo[j]),observed_sum_public_MW_samples=float(oo[j])))
        modeled=np.asarray(modeled);observed=np.asarray(observed);counts=np.asarray(counts);assert counts.sum()==n
        difference=modeled-observed;mean_difference=difference/counts[:,None]
        for j,name in enumerate([*names,'POOLED_7_DIAGNOSTIC_CUTS']):
            use=slice(None) if j==7 else slice(j,j+1);width=7 if j==7 else 1
            num=float(np.abs(difference[:,use]).sum());den=float(np.abs(observed[:,use]).sum())
            summaries.append(dict(resolution=resolution,interface=name,cohort='all8170qualified_hour_positions',
                qualified_hours=n,available_bins=len(counts),clock_bins=len(expected),fully_qualified_bins=int(np.sum(complete)),
                WAPE_of_qualified_hour_sums_percent=100*num/den,
                MAE_of_bin_means_hour_weighted_public_MW=num/(n*width),
                RMSE_of_bin_means_hour_weighted_public_MW=float(np.sqrt(np.sum(mean_difference[:,use]**2*counts[:,None])/(n*width))),
                weighted_bias_public_MW=float(difference[:,use].sum()/(n*width)),
                aggregation_numerator_public_MW_samples=num,aggregation_denominator_public_MW_samples=den))
    return pd.DataFrame(summaries),pd.DataFrame(bins)


def lag_diagnostics(meta,m,o,names):
    q=meta.qualified.to_numpy();state=meta.state.to_numpy();finite=np.isfinite(o).all(axis=1)
    same=np.zeros(len(q),bool);same[1:-1]=(state[:-2]==state[1:-1])&(state[1:-1]==state[2:])
    triplet=np.zeros(len(q),bool);triplet[1:-1]=finite[:-2]&finite[1:-1]&finite[2:]
    common=q&same&triplet
    allq=np.zeros(len(q),bool);allq[1:-1]=q[:-2]&q[1:-1]&q[2:];strict=common&allq
    masks={'qualified_center_observation_triplet_same_state':common,'fully_qualified_triplet_same_state':strict}
    rows=[]
    for cohort,mask in masks.items():
        ix=np.flatnonzero(mask);assert len(ix)>0 and ix.min()>0 and ix.max()<len(q)-1
        zero=[stats(m[ix,j],o[ix,j]) for j in range(7)]
        for lag in [-1,0,1]:
            for j,name in enumerate(names):
                score=stats(m[ix,j],o[ix+lag,j])
                rows.append(dict(cohort=cohort,interface=name,observation_shift_hours=lag,
                    **score,MAE_delta_from_lag0_public_MW=score['mae_public_MW']-zero[j]['mae_public_MW'],
                    WAPE_delta_from_lag0_percentage_points=score['wape_percent']-zero[j]['wape_percent'],
                    interpretation='compare model(t) with observation(t+shift); shared cohort for all three shifts; diagnostic only'))
    frame=meta[['hour_index','timestamp_utc','state','source','qualified']].copy()
    for name,mask in masks.items():frame[name]=mask
    return pd.DataFrame(rows),frame


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    files=[Path(__file__),SOURCE/'comparison_arrays.npz',SOURCE/'public_interface_metrics.csv',SOURCE/'scoring_receipt.json',
        ROOT/'output/nygrid_2025_ac_loss_revision/comparison/frozen_comparison_cohort.csv',
        ROOT/'output/nygrid_2025_ac_loss_revision/comparison/comparison_contract.json']
    before=[record(p) for p in files]
    sealed=json.loads((SOURCE/'scoring_receipt.json').read_text());assert sealed['passed']
    for p in files[1:3]:
        found=[x for x in sealed['outputs'] if x['path']==p.relative_to(ROOT).as_posix()];assert len(found)==1 and record(p)['sha256']==found[0]['sha256']
    contract=json.loads(files[-1].read_text());assert contract['primary_terminal_convention']==CONVENTION
    with np.load(files[1],allow_pickle=False) as a:
        names=a['interface_names'].astype(str).tolist();m=a['revised_'+CONVENTION].copy();o=a['observed'].copy()
        hours=a['hour_index'].astype(int);times=a['timestamp_utc'].astype(str);q=a['revised_qualified'].astype(bool)
        source=a['source_qualified'].astype(bool);operating=a['operating_qualified'].astype(bool);gamma=float(a['gamma'])
    assert np.array_equal(hours,np.arange(1,8761)) and source.sum()==8651 and q.sum()==8170 and operating.sum()==0
    assert np.all(~q|source) and np.isfinite(m[q]).all() and np.isfinite(o[q]).all() and np.isnan(m[~q]).all()
    cohort=pd.read_csv(files[-2]);assert np.array_equal(cohort.hour_index,hours) and np.array_equal(cohort.timestamp_utc,times)
    assert np.array_equal(cohort.frozen_source_qualified.to_numpy(bool),source)
    utc=pd.to_datetime(times,utc=True);assert np.all(np.diff(utc.asi8)==3600*10**9)
    local=utc.tz_convert('America/New_York')
    meta=pd.DataFrame(dict(hour_index=hours,timestamp_utc=times,local_timestamp=[x.isoformat() for x in local],
        local_date=local.strftime('%Y-%m-%d'),month=local.month,local_hour=local.hour,
        season=[SEASONS[x] for x in local.month],state=cohort.dated_state,source=source,qualified=q,operating_qualified=operating))
    residual=np.full_like(m,np.nan);residual[q]=m[q]-o[q];e=residual[q]
    annual=pd.DataFrame([dict(interface=name,**stats(m[q,j],o[q,j])) for j,name in enumerate(names)])
    annual['rank_WAPE']=annual.wape_percent.rank(ascending=False,method='min').astype(int)
    annual['rank_MAE']=annual.mae_public_MW.rank(ascending=False,method='min').astype(int)
    annual['share_of_seven_cut_absolute_error_numerator_percent']=100*annual.absolute_error_sum_public_MW_samples/annual.absolute_error_sum_public_MW_samples.sum()
    saved=pd.read_csv(files[2],float_precision='round_trip')
    selected=saved.loc[saved.model.eq('combined')&saved.cohort.eq('revised_all_qualified')&saved.period.eq('annual')&saved.convention.eq(CONVENTION)].set_index('interface')
    max_reproduction_error=0.
    for row in annual.itertuples(index=False):
        assert int(selected.loc[row.interface,'hours'])==row.hours
        for field in ['mae_public_MW','rmse_public_MW','bias_public_MW','wape_percent']:
            delta=abs(getattr(row,field)-float(selected.loc[row.interface,field]));max_reproduction_error=max(max_reproduction_error,delta);assert delta<1e-10
    annual.to_csv(OUT/'annual_metrics.csv',index=False,lineterminator='\n')
    residual_frame=meta.copy()
    for j,name in enumerate(names):residual_frame[name+' residual public MW']=residual[:,j]
    residual_frame.to_csv(OUT/'hourly_residuals.csv',index=False,lineterminator='\n')
    grouped={};coverage=[];decomposition=[]
    for dimension in ['month','local_hour','season','state','local_date']:
        table,cov=group_analysis(meta,m,o,names,dimension);grouped[dimension]=table;coverage.append(cov)
        table.to_csv(OUT/(dimension+'_metrics.csv'),index=False,lineterminator='\n')
        assert int(cov.qualified_hours.sum())==8170 and int(cov.clock_hours.sum())==8760
        if dimension!='local_date':
            for j,name in enumerate(names):
                row=annual.loc[annual.interface.eq(name)].iloc[0];group=table.loc[table.interface.eq(name)]
                between=float(np.sum(group.hours*(group.bias_public_MW-row.bias_public_MW)**2)/8170)
                total=float(np.var(e[:,j]));within=total-between
                decomposition.append(dict(dimension=dimension,interface=name,total_centered_variance_MW2=total,
                    between_group_variance_MW2=between,within_group_variance_MW2=within,
                    between_group_variance_percent=100*between/total,grouping_is_descriptive_not_causal=True))
    pd.concat(coverage,ignore_index=True).to_csv(OUT/'coverage_by_time.csv',index=False,lineterminator='\n')
    pd.DataFrame(decomposition).to_csv(OUT/'temporal_variance_decomposition.csv',index=False,lineterminator='\n')
    # Rankings describe concentration only; they do not alter any score cohort.
    concentration=[];top_rows=[];magnitude=[]
    cuts=[0,100,500,1000,2000,np.inf]
    for j,name in enumerate(names):
        r=e[:,j];order=np.argsort(-np.abs(r),kind='stable');total_l1=float(np.abs(r).sum());total_l2=float(np.sum(r*r))
        cumulative=np.cumsum(np.abs(r)[order])/total_l1
        for fraction in [.01,.05,.10,.25]:
            count=int(np.ceil(len(r)*fraction));take=order[:count]
            concentration.append(dict(interface=name,top_hour_fraction=fraction,hours=count,
                share_of_absolute_error_percent=100*float(np.abs(r[take]).sum())/total_l1,
                share_of_squared_error_percent=100*float(np.square(r[take]).sum())/total_l2,
                minimum_selected_absolute_error_public_MW=float(np.abs(r[take]).min()),
                hours_needed_for50percent_L1=int(np.searchsorted(cumulative,.5)+1),
                hours_needed_for80percent_L1=int(np.searchsorted(cumulative,.8)+1)))
        original=np.flatnonzero(q)
        for rank,k in enumerate(order[:20],1):
            ix=original[k];top_rows.append(dict(interface=name,rank=rank,**meta.iloc[ix].to_dict(),
                model_public_MW=float(m[ix,j]),observed_public_MW=float(o[ix,j]),residual_public_MW=float(residual[ix,j]),absolute_error_public_MW=abs(float(residual[ix,j]))))
        obs=np.abs(o[q,j])
        for lo,hi in zip(cuts[:-1],cuts[1:]):
            use=(obs>=lo)&(obs<hi)
            magnitude.append(dict(interface=name,absolute_observation_bin=f'[{lo},{hi}) MW',
                **stats(m[q,j][use],o[q,j][use]),absolute_error_numerator_share_percent=100*float(np.abs(r[use]).sum())/total_l1,
                absolute_observation_denominator_share_percent=100*float(obs[use].sum())/float(obs.sum())))
    pd.DataFrame(concentration).to_csv(OUT/'error_concentration.csv',index=False,lineterminator='\n')
    pd.DataFrame(top_rows).to_csv(OUT/'top20_error_hours_per_interface.csv',index=False,lineterminator='\n')
    pd.DataFrame(magnitude).to_csv(OUT/'error_by_observed_magnitude.csv',index=False,lineterminator='\n')
    pairs=[dict(interface_A=names[a],interface_B=names[b],**pair_stats(e[:,a],e[:,b])) for a,b in itertools.combinations(range(7),2)]
    pair_table=pd.DataFrame(pairs);pair_table.to_csv(OUT/'pairwise_residual_structure.csv',index=False,lineterminator='\n')
    pd.DataFrame(np.corrcoef(e,rowvar=False),index=names,columns=names).to_csv(OUT/'residual_pearson_matrix.csv',lineterminator='\n')
    pd.DataFrame(spearmanr(e).statistic,index=names,columns=names).to_csv(OUT/'residual_spearman_matrix.csv',lineterminator='\n')
    west_pair=[]
    for dimension in ['month','season','state']:
        for label,positions in meta.loc[q].groupby(dimension).groups.items():
            take=np.asarray(positions,int);west_pair.append(dict(dimension=dimension,group=str(label),**pair_stats(residual[take,0],residual[take,1])))
    pd.DataFrame(west_pair).to_csv(OUT/'Dysinger_WestCentral_shared_by_period.csv',index=False,lineterminator='\n')
    aggregate,bins=temporal_aggregation(meta,m,o,names)
    aggregate.to_csv(OUT/'time_aggregation_metrics.csv',index=False,lineterminator='\n');bins.to_csv(OUT/'time_aggregation_bins.csv',index=False,lineterminator='\n')
    lag,lag_masks=lag_diagnostics(meta,m,o,names);lag.to_csv(OUT/'lag_diagnostics.csv',index=False,lineterminator='\n');lag_masks.to_csv(OUT/'lag_cohorts.csv',index=False,lineterminator='\n')
    dy=annual.iloc[0];wc=annual.iloc[1];west=pair_table.loc[pair_table.interface_A.eq(names[0])&pair_table.interface_B.eq(names[1])].iloc[0].to_dict()
    west['WAPE_ratio_West_over_Dysinger']=wc.wape_percent/dy.wape_percent
    west['MAE_ratio_West_over_Dysinger']=wc.mae_public_MW/dy.mae_public_MW
    west['observed_denominator_ratio_Dysinger_over_West']=dy.mean_abs_observed_public_MW/wc.mean_abs_observed_public_MW
    west['WAPE_difference_percentage_points']=wc.wape_percent-dy.wape_percent
    west['MAE_component_percentage_points_using_Dysinger_denominator']=100*(wc.mae_public_MW-dy.mae_public_MW)/dy.mean_abs_observed_public_MW
    west['denominator_component_percentage_points']=100*wc.mae_public_MW*(1/wc.mean_abs_observed_public_MW-1/dy.mean_abs_observed_public_MW)
    strict=lag.loc[lag.cohort.eq('fully_qualified_triplet_same_state')]
    best={name:int(strict.loc[strict.interface.eq(name)].sort_values('mae_public_MW').iloc[0].observation_shift_hours) for name in names}
    summary=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        scope='Descriptive residual analysis of the frozen current annual primary-convention series; no model or metric tuning',
        official_cohort=dict(clock_hours=8760,source_qualified_hours=8651,equation_loss_qualified_hours=8170,source_excluded_hours=109,
            source_qualified_failed_hours=481,operating_qualified_hours=0),
        primary_convention=CONVENTION,gamma=gamma,units='Public-scale MW under frozen numeric-as-MW interpretation; model aggregate MW divided by gamma',
        residual_definition='model minus observation',max_annual_metric_reproduction_error=max_reproduction_error,
        annual_metrics=annual.to_dict(orient='records'),west_pair=west,
        month_bias_ranges={name:dict(min=float(grouped['month'].loc[grouped['month'].interface.eq(name),'bias_public_MW'].min()),
            max=float(grouped['month'].loc[grouped['month'].interface.eq(name),'bias_public_MW'].max())) for name in names},
        worst_month_by_MAE={name:grouped['month'].loc[grouped['month'].interface.eq(name)].sort_values('mae_public_MW',ascending=False).iloc[0].to_dict() for name in names},
        highest_10percent_error_concentration=pd.DataFrame(concentration).loc[lambda d:d.top_hour_fraction.eq(.10)].to_dict(orient='records'),
        time_aggregation=aggregate.to_dict(orient='records'),
        lag_diagnostic=dict(cohort_counts=lag.groupby('cohort').hours.first().to_dict(),best_MAE_shift_on_strict_common_cohort=best,
            shift_definition='model(t) vs observation(t+lag), lag in contiguous UTC hours; same dated state and a fixed shared cohort across -1/0/+1',
            no_shift_applied_to_official_scores=True),
        caveats=['All residual claims condition on8170 equation/loss-qualified hours;481 source-valid failures and109 exclusions remain visible, with no imputed errors.',
            'None of these hours passes the joint V/Q/generator operating gate.',
            'Physical P32 meter membership and published Flow(MWH) numeric-as-MW interpretation remain unverified.',
            'Adjacent interface cuts overlap physically; pooled error is a diagnostic metric pool, not an additive physical network power total.',
            'Daily/monthly aggregation sums only the same qualified hourly positions; partial calendar bins are labeled and within-bin residual cancellation changes the estimand.',
            'Season and topology-state comparisons are descriptive and confounded with calendar time and changing qualification coverage.',
            'Bias, residual correlation, in-sample variance decompositions and lag scores do not identify a causal mechanism; no fitted correction is applied.',
            'Season labels group calendar months within2025; DJF combines Jan-Feb andDec, not a continuous winter season.'],
        PF_run=False,OPF_run=False,annual_rerun=False,sources=before)
    (OUT/'baseline_summary.json').write_text(json.dumps(clean(summary),indent=2,allow_nan=False)+'\n',encoding='utf-8')
    after=[record(p) for p in files];assert before==after,'A controlling frozen source changed during analysis'
    outputs=[record(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='baseline_receipt.json']
    receipt=dict(passed=True,inputs_unchanged=True,sources=before,outputs=outputs,
        exact_annual_metric_reproduction=max_reproduction_error==0,cohort_count=8170,clock_rows=8760,
        primary_convention=CONVENTION,PF_run=False,OPF_run=False,official_scores_or_cohort_changed=False)
    (OUT/'baseline_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(annual[['interface','mae_public_MW','wape_percent','bias_public_MW','bias_squared_MSE_share_percent']].to_string(index=False))
    print(json.dumps(clean(dict(passed=True,west_pair=west,lag=summary['lag_diagnostic'],max_metric_error=max_reproduction_error)),indent=2))


if __name__=='__main__':main()
