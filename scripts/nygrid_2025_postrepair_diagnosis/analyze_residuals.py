"""Current residual patterns and conditional monthly-energy compatibility."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_postrepair_diagnosis'


def metric(pred,obs):
    err=np.asarray(pred)-np.asarray(obs)
    return dict(hours=len(err),MAE_MW=float(np.mean(abs(err))),bias_MW=float(np.mean(err)),
                RMSE_MW=float(np.sqrt(np.mean(err**2))),WAPE_pct=float(100*np.sum(abs(err))/np.sum(abs(obs))))


def record(p):
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=p.relative_to(ROOT).as_posix(),sha256=h)


def main():
    path=OUT/'hourly_evidence.csv';full=pd.read_csv(path);d=full.loc[full.qualified].copy();assert len(d)==8651
    files=[];metrics=[]
    for label in ['Moses','TotalEast','CentralEast']:
        for period,part in [('annual',d)]+[(f'month_{m:02d}',g) for m,g in d.groupby('month_local')]:
            for prefix in ['previous','current']:
                metrics.append(dict(interface=label,model=prefix,period=period,**metric(part[prefix+'_'+label+'_primary_MW'],part[label+'_observed_MW'])))
    p=OUT/'residual_metrics.csv';pd.DataFrame(metrics).to_csv(p,index=False);files.append(p)
    a=np.load(OUT/'interface_evidence.npz',allow_pickle=False);j=list(a['interface_names']).index('MOSES SOUTH')
    terminal=[]
    for convention in ['legacy_signed_literal_from','oriented_source_side','oriented_target_side']:
        value=a['candidate_'+convention][full.qualified.to_numpy(),j]
        terminal.append(dict(convention=convention,**metric(value,d.Moses_observed_MW),
                             mean_difference_from_primary_MW=float(np.mean(value-d.current_Moses_primary_MW))))
    terminal.append(dict(convention='midpoint_accounting_not_meter',**metric(d.current_Moses_midpoint_MW,d.Moses_observed_MW),
                         mean_difference_from_primary_MW=float(np.mean(d.current_Moses_midpoint_MW-d.current_Moses_primary_MW))))
    p=OUT/'Moses_terminal_convention_sensitivity.csv';pd.DataFrame(terminal).to_csv(p,index=False);files.append(p)
    columns=['current_StLawrence_MW','current_other_D_hydro_MW','current_D_wind_MW','current_other_D_nonhydro_MW',
             'current_HQ_MW','current_PV20_MW','current_PAR1_MW','current_PAR2_MW','current_gross_D_MW',
             'current_Moses_residual_MW','previous_Moses_residual_MW','current_TotalEast_residual_MW',
             'previous_TotalEast_residual_MW','delta_StLawrence_MW','delta_other_D_MW','delta_Moses_primary_MW']
    for key,label in [('hour_local','daily_profiles'),('month_local','monthly_profiles')]:
        table=d.groupby(key)[columns].mean();table['hours']=d.groupby(key).size()
        table['Moses_MAE_MW']=d.groupby(key).current_Moses_residual_MW.apply(lambda x:abs(x).mean())
        table['StLawrence_at_engineering_cap_fraction']=d.groupby(key).current_StLawrence_MW.apply(lambda x:np.mean(x>=855-1e-7))
        p=OUT/(label+'.csv');table.to_csv(p);files.append(p)
    # A fixed signed proxy identity, not a certificate for physical P32 channels.
    terms=[]
    for prefix in ['previous','current']:
        ce=float(d[prefix+'_CentralEast_primary_MW'].mean());te=float(d[prefix+'_TotalEast_primary_MW'].mean())
        observed_extra=float((d.TotalEast_observed_MW-d.CentralEast_observed_MW).mean())
        terms.append(dict(model=prefix,CentralEast_mean_MW=ce,TotalEast_mean_MW=te,parent224_mean_MW=te-ce,
                          observed_TotalEast_minus_CentralEast_mean_MW=observed_extra,
                          error_in_difference_mean_MW=te-ce-observed_extra))
    p=OUT/'TotalEast_CentralEast_proxy_identity.csv';pd.DataFrame(terms).to_csv(p,index=False);files.append(p)
    d['TE_abs_error_change_MW']=abs(d.current_TotalEast_residual_MW)-abs(d.previous_TotalEast_residual_MW)
    d['TE_prediction_change_MW']=d.current_TotalEast_primary_MW-d.previous_TotalEast_primary_MW
    d['old_TE_error_sign']=np.where(d.previous_TotalEast_residual_MW<0,'underprediction','overprediction_or_zero')
    d['flow_change_direction']=np.where(d.TE_prediction_change_MW<0,'lower_prediction','higher_prediction_or_zero')
    parts=[]
    for (sign,direction),g in d.groupby(['old_TE_error_sign','flow_change_direction']):
        parts.append(dict(previous_error_sign=sign,prediction_change=direction,hours=len(g),
                          contribution_to_annual_MAE_change_MW=float(g.TE_abs_error_change_MW.sum()/len(d)),
                          mean_flow_change_MW=float(g.TE_prediction_change_MW.mean())))
    assert abs(sum(p['contribution_to_annual_MAE_change_MW'] for p in parts)-d.TE_abs_error_change_MW.mean())<1e-10
    p=OUT/'TotalEast_absolute_error_change_partition.csv';pd.DataFrame(parts).to_csv(p,index=False);files.append(p)
    # Hold every other modeled term and each saved AC terminal correction fixed.
    # This oracle is diagnostic only and never becomes a generation source.
    d['oracle_StLawrence_MW']=d.current_StLawrence_MW-d.current_Moses_residual_MW
    source=ROOT/'output/nygrid_2025_moses_repair/generation/StLawrence_monthly_energy_ledger.csv'
    energy=pd.read_csv(source);energy_col=next(c for c in energy if ('target' in c.lower() or 'eia' in c.lower()) and 'mwh' in c.lower())
    month_col=next(c for c in energy if c.lower()=='month')
    rows=[]
    for cap in [855.,912.]:
        for m,g in d.groupby('month_local'):
            allm=full.loc[full.month_local.eq(m)];missing=len(allm)-len(g)
            target=float(energy.loc[energy[month_col].eq(m),energy_col].iloc[0]);oracle_energy=float(g.oracle_StLawrence_MW.sum())
            required_missing=target-oracle_energy;lo=target-missing*cap;hi=target
            incompatibility=max(lo-oracle_energy,0)+max(oracle_energy-hi,0)
            rows.append(dict(month=m,engineering_cap_sensitivity_MW=cap,qualified_hours=len(g),excluded_hours=missing,
                             EIA_monthly_energy_MWh=target,oracle_qualified_energy_MWh=oracle_energy,
                             required_excluded_energy_MWh=required_missing,maximum_excluded_energy_MWh=missing*cap,
                             energy_compatible_with_StLawrence_only=0<=required_missing<=missing*cap,
                             minimum_absolute_other_balance_change_mean_MW=incompatibility/len(g),
                             oracle_hours_below_zero=int((g.oracle_StLawrence_MW<0).sum()),
                             oracle_hours_above_cap=int((g.oracle_StLawrence_MW>cap).sum())))
    p=OUT/'conditional_StLawrence_only_energy_compatibility.csv';pd.DataFrame(rows).to_csv(p,index=False);files.append(p)
    p=OUT/'oracle_StLawrence_DIAGNOSTIC_ONLY.csv';d[['hour_index','month_local','current_StLawrence_MW','current_Moses_residual_MW','oracle_StLawrence_MW']].to_csv(p,index=False);files.append(p)
    # Source-defined monthly-flat control (recipe contains no P32 input).
    shape_path=OUT/'generation/monthly_flat_hourly_injection_delta.csv'
    shape_scores=[]
    if shape_path.exists():
        s=pd.read_csv(shape_path)
        delta_col=next(c for c in s if 'delta' in c.lower() and ('native_d' in c.lower() or 'zoneD' in c))
        assert np.array_equal(s.hour_index,full.hour_index)
        delta=s.loc[full.qualified,delta_col].to_numpy()
        for period,mask in [('annual',np.ones(len(d),bool))]+[(f'month_{m:02d}',d.month_local.eq(m).to_numpy()) for m in range(1,13)]:
            shape_scores.append(dict(period=period,**metric(d.current_Moses_primary_MW.to_numpy()[mask]+delta[mask],d.Moses_observed_MW.to_numpy()[mask]),
                                     frozen_terminal_correction=True,new_annual_AC_solve=False))
        p=OUT/'monthly_flat_frozen_terminal_scores.csv';pd.DataFrame(shape_scores).to_csv(p,index=False);files.append(p)
    summary=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),qualified_hours=len(d),
                 Current_Moses_metrics=metric(d.current_Moses_primary_MW,d.Moses_observed_MW),
                 TE_mean_prediction_change_MW=float(d.TE_prediction_change_MW.mean()),
                 TE_MAE_increase_MW=float(d.TE_abs_error_change_MW.mean()),
                 StLawrence_at_855_hours=int((d.current_StLawrence_MW>=855-1e-7).sum()),
                 oracle_above_855_hours=int((d.oracle_StLawrence_MW>855).sum()),
                 incompatible_StLawrence_only_months_by_cap={str(int(c)): [r['month'] for r in rows if r['engineering_cap_sensitivity_MW']==c and not r['energy_compatible_with_StLawrence_only']] for c in [855.,912.]},
                 conditional_shape_control=shape_scores[:1],
                 limits=['The oracle holds all other source terms, physical-meter mapping and saved terminal corrections fixed; it is not observed generation or a feasible dispatch.',
                         '912MW is the 16-unit full-nameplate sensitivity, not certified net capability or a revised availability assumption.',
                         'TE/CE/parent224 identity describes the model proxies, not certified physical P32 definitions.',
                         'Daily correlations and control sensitivities do not establish actual plant-level causal error.'],
                 inputs=[record(path),record(source)]+([record(shape_path)] if shape_path.exists() else []),outputs=[record(p) for p in files])
    (OUT/'residual_review.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['inputs','outputs','limits']}))


if __name__=='__main__':main()
