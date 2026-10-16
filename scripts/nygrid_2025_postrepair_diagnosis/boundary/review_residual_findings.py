"""Independently check root residual and conditional-energy arithmetic.

The energy result is conditional on the fixed other inputs, comparison operator
and saved terminal correction. Engineering caps are not asserted physical limits.
"""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'output/nygrid_2025_postrepair_diagnosis'
OUT=BASE/'boundary'
REPAIR=ROOT/'output/nygrid_2025_moses_repair'
DEPS={}


def sha(p):
    with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read(p):
    p=Path(p);DEPS[p.relative_to(ROOT).as_posix()]=sha(p);return p


def same(a,b,label,tol=1e-8):
    a,b=np.asarray(a,float),np.asarray(b,float)
    assert a.shape==b.shape and np.allclose(a,b,rtol=0,atol=tol,equal_nan=True),label
    valid=np.isfinite(a)&np.isfinite(b)
    return float(np.max(abs(a[valid]-b[valid]),initial=0))


def main():
    own=pd.read_csv(read(OUT/'northern_balance_identity.csv'))
    root=pd.read_csv(read(BASE/'hourly_evidence.csv'))
    rr=json.loads(read(BASE/'residual_review.json').read_text())
    q=root.qualified.to_numpy(bool);month=root.month_local.to_numpy(int)
    assert q.sum()==8651 and np.array_equal(root.timestamp_utc,own.timestamp_utc) and np.array_equal(q,own.qualified)
    identity_checks={}
    for a,b in [('current_StLawrence_MW','StLawrence_MW'),('current_native_D_MW','native_D_MW'),('current_HQ_MW','HQ_import_MW'),
        ('current_PV20_MW','PV20_import_proxy_MW'),('current_gross_D_MW','gross_D_load_MW'),('current_Moses_primary_MW','primary_Moses_MW'),
        ('current_Moses_midpoint_MW','saved_midpoint_MW'),('current_Moses_terminal_MW','signed_terminal_correction_MW'),('Moses_observed_MW','observed_Moses_MW')]:
        identity_checks[a]=same(root.loc[q,a],own.loc[q,b],a)
    residual=own.primary_Moses_MW.to_numpy()-own.observed_Moses_MW.to_numpy()
    same(residual[q],root.current_Moses_residual_MW[q],'Residual convention')
    oracle=own.StLawrence_MW.to_numpy()-residual
    energy=pd.read_csv(read(REPAIR/'generation/StLawrence_monthly_energy_ledger.csv'))
    published=pd.read_csv(read(BASE/'conditional_StLawrence_only_energy_compatibility.csv'))
    rows=[]
    for cap in [855.,912.]:
        for mo in range(1,13):
            available=q&(month==mo);missing=(~q)&(month==mo);target=energy.loc[energy.month.eq(mo),'EIA_monthly_target_MWh'].item()
            known=float(oracle[available].sum());required=target-known;maximum=float(missing.sum()*cap)
            compatible=required>=-1e-7 and required<=maximum+1e-7
            distance=max(0.,-required,required-maximum)
            rows.append(dict(month=mo,engineering_cap_sensitivity_MW=cap,qualified_hours=int(available.sum()),excluded_hours=int(missing.sum()),
                EIA_monthly_energy_MWh=target,oracle_qualified_energy_MWh=known,required_excluded_energy_MWh=required,
                maximum_excluded_energy_MWh=maximum,energy_compatible_with_StLawrence_only=compatible,
                minimum_absolute_other_balance_change_mean_MW=distance/available.sum(),oracle_hours_below_zero=int((oracle[available]<-1e-7).sum()),
                oracle_hours_above_cap=int((oracle[available]>cap+1e-7).sum())))
    independent=pd.DataFrame(rows)
    keys=['engineering_cap_sensitivity_MW','month'];published=published.sort_values(keys).reset_index(drop=True);independent=independent.sort_values(keys).reset_index(drop=True)
    numeric=[k for k in independent if k!='energy_compatible_with_StLawrence_only']
    energy_error=same(independent[numeric],published[numeric],'Conditional monthly energy bounds',tol=1e-7)
    assert np.array_equal(independent.energy_compatible_with_StLawrence_only,published.energy_compatible_with_StLawrence_only)
    assert not independent.energy_compatible_with_StLawrence_only.any()
    independent.to_csv(OUT/'independent_conditional_energy_readback.csv',index=False,lineterminator='\n')
    assert int((oracle[q]>855+1e-7).sum())==rr['oracle_above_855_hours']==1403

    model=loadmat(read(REPAIR/'model/latest_model.mat'),simplify_cells=True)['model']
    oldhy=loadmat(read(REPAIR/'generation/generation_candidate.mat'),simplify_cells=True)
    control=loadmat(read(BASE/'generation/monthly_flat_generation_control.mat'),simplify_cells=True)
    hy=np.asarray(oldhy['hydro_rows_1based'],int)-1
    assert np.array_equal(hy,np.asarray(control['hydro_rows_1based'],int)-1)
    assert np.array_equal(q,np.asarray(control['source_qualified'],bool))
    bg=dict(zip(model['templates'][0]['bus'][:,0].astype(int),np.asarray(model['loss_static'][0]['bus_group'],int)))
    genbus=np.asarray(model['generator_bus_ids'],int)
    dmask=np.array([bg[int(genbus[g])]==4 for g in hy])
    delta=np.asarray(control['hydro_PG_public_MW'])-np.asarray(oldhy['hydro_PG_public_MW'])
    deltaD=delta[:,dmask].sum(axis=1)
    flatledger=pd.read_csv(read(BASE/'generation/monthly_flat_hourly_injection_delta.csv'))
    flat_delta_error=same(deltaD[q],flatledger.native_D_delta_public_MW[q],'Flat control D-hydro redistribution')
    assert np.max(abs(delta[q].sum(axis=1)))<1e-7
    predicted=own.primary_Moses_MW.to_numpy()+deltaD;observed=own.observed_Moses_MW.to_numpy()
    savedflat=pd.read_csv(read(BASE/'monthly_flat_frozen_terminal_scores.csv'))
    actual_flat=[]
    for mo in range(13):
        mask=q if mo==0 else q&(month==mo);err=predicted[mask]-observed[mask]
        actual_flat.append(dict(period='annual'if mo==0 else f'month_{mo:02d}',hours=int(mask.sum()),MAE_MW=float(abs(err).mean()),
            bias_MW=float(err.mean()),RMSE_MW=float(np.sqrt(np.mean(err**2))),WAPE_pct=float(100*abs(err).sum()/abs(observed[mask]).sum())))
    ff=pd.DataFrame(actual_flat).set_index('period');ss=savedflat.set_index('period')
    flat_score_error=same(ff,ss.loc[ff.index,ff.columns],'Flat source-control frozen-terminal scores')
    ff.reset_index().to_csv(OUT/'independent_flat_control_readback.csv',index=False,lineterminator='\n')

    proxies=pd.read_csv(read(BASE/'TotalEast_CentralEast_proxy_identity.csv')).set_index('model')
    proxy_errors=[]
    for label,prefix in [('previous','previous'),('current','current')]:
        te=root.loc[q,prefix+'_TotalEast_primary_MW'].to_numpy();ce=root.loc[q,prefix+'_CentralEast_primary_MW'].to_numpy()
        extra=root.loc[q,prefix+'_parent224_primary_MW'].to_numpy()
        proxy_errors.append(same(te-ce,extra,'TE minus CE parent224 identity'))
        obs_diff=(root.TotalEast_observed_MW-root.CentralEast_observed_MW)[q].mean()
        same([ce.mean(),te.mean(),extra.mean(),obs_diff,extra.mean()-obs_diff],proxies.loc[label].to_numpy(),'Proxy difference summary')
    report=dict(passed=True,status='independent_residual_arithmetic_and_conditional_energy_review_passed',created_utc=datetime.now(timezone.utc).isoformat(),
        qualified_hours=int(q.sum()),primitive_current_balance_checks=identity_checks,conditional_energy_table_max_difference=energy_error,
        engineering_caps_tested_MW=[855,912],months_incompatible_at_each_tested_cap=12,oracle_above_855_hours=1403,
        energy_interval_scope='Necessary aggregate compatibility test only; the distance divided by qualified hours is a lower bound on mean absolute other-balance change, not an attained optimum or a physical causal allocation.',
        exact_stl_only_condition='Hold all other inputs, the comparison operator and the saved terminal correction fixed; StLawrence_required = StLawrence_current - current_residual.',
        physical_capability_certificate_claimed=False,physical_meter_certificate_claimed=False,
        qualified_oracle_values_are_not_observed_dispatch=True,unqualified_hour_energy_not_treated_as_observed=True,
        flat_control_D_delta_readback_max_difference_MW=flat_delta_error,flat_control_score_max_difference=flat_score_error,
        flat_control_scope='The source-defined flat plant control also redistributes other hydro to preserve the hourly hydro total. The frozen-terminal Moses score uses total native-D change, not StLawrence change alone. This is not a fresh AC score.',
        flat_control_annual=actual_flat[0],TE_CE_identity_max_error_MW=max(proxy_errors),
        TE_CE_difference_scope='Exact frozen model operator identity; the observed difference is not an observed parent224 circuit flow.',
        new_AC_solves=0,default_model_map_package_changed=False,
        inputs=[dict(path=p,sha256=h)for p,h in DEPS.items()],script_sha256=sha(Path(__file__)))
    assert all(sha(ROOT/p)==h for p,h in DEPS.items())
    (OUT/'independent_residual_review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k]for k in ['passed','qualified_hours','conditional_energy_table_max_difference','months_incompatible_at_each_tested_cap','oracle_above_855_hours','flat_control_annual','TE_CE_identity_max_error_MW']},indent=2))


if __name__=='__main__':main()
