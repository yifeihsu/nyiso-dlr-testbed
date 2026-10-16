"""Score the frozen small probes, with paired cohorts and explicit failures."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_remaining_errors/probes'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    p=loadmat(OUT/'probe_results.mat',simplify_cells=True);a=np.load(ROOT/'output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_arrays.npz')
    plan=json.loads((OUT/'probe_plan.json').read_text());audit=pd.read_csv(OUT/'probe_audit.csv')
    assert set(audit.qualified.unique())<=set([0,1])
    audit['qualified']=audit.qualified.astype(bool)
    h=np.asarray(p['hours'],int);v=np.asarray(plan['variants']);f=p['flows'];loss=p['losses'];pl=p['parent_losses']
    assert len(audit)==len(h)*len(v)==150 and f.shape==(15,10,7)
    assert h.tolist()==[x['hour_index'] for x in plan['samples']]
    assert np.array_equal(audit.variant.to_numpy(),np.tile(v,len(h))) and np.array_equal(audit.hour_index,np.repeat(h,len(v)))
    assert np.array_equal(np.isfinite(f).all(axis=2).reshape(-1),audit.qualified.to_numpy())
    assert np.isfinite(f[:,0,:]).all()
    assert audit[['hour_index','variant']].drop_duplicates().shape[0]==150
    assert np.max(abs(audit.native_PG_sum_change_model_MW))<1e-8 and np.max(abs(audit.PJM_baseline_PG_sum_change_model_MW))<1e-8
    maxdiff=float(np.max(abs(f[:,0,:]-a['revised_legacy_signed_literal_from'][h-1])))
    assert maxdiff<1e-6,('Current baseline reproduction failed',maxdiff)
    observed=a['observed'][h-1];rows=[];phys=[];hourly=[]
    for j,name in enumerate(v):
        paired=np.isfinite(f[:,j,:]).all(axis=1);base=f[paired,0,:];var=f[paired,j,:];obs=observed[paired];delta=var-base
        for k,interface in enumerate(a['interface_names']):
            err=var[:,k]-obs[:,k];err0=base[:,k]-obs[:,k]
            rows.append({'variant':name,'interface':interface,'paired_hours':int(paired.sum()),'unavailable_hours':int((~paired).sum()),
                'baseline_MAE_public_MW':np.mean(abs(err0)),'variant_MAE_public_MW':np.mean(abs(err)),
                'MAE_change_public_MW':np.mean(abs(err))-np.mean(abs(err0)),
                'baseline_bias_public_MW':np.mean(err0),'variant_bias_public_MW':np.mean(err),
                'mean_response_public_MW':np.mean(delta[:,k]),'mean_absolute_response_public_MW':np.mean(abs(delta[:,k])),
                'min_response_public_MW':np.min(delta[:,k]),'max_response_public_MW':np.max(delta[:,k])})
            for ii in np.flatnonzero(paired):
                hourly.append({'hour_index':h[ii],'variant':name,'interface':interface,'predicted_public_MW':f[ii,j,k],
                    'baseline_public_MW':f[ii,0,k],'observed_public_MW':observed[ii,k],'response_public_MW':f[ii,j,k]-f[ii,0,k]})
        au=audit[(audit.variant==name)&audit.qualified]
        phys.append({'variant':name,'qualified_hours':int(paired.sum()),'NY_total_loss_mean_model_MW':np.mean(loss[paired,j,:11].sum(axis=1)),
            'baseline_NY_total_loss_mean_model_MW':np.mean(loss[paired,0,:11].sum(axis=1)),
            'zone_F_assigned_loss_mean_model_MW':np.mean(loss[paired,j,5]),
            'baseline_zone_F_assigned_loss_mean_model_MW':np.mean(loss[paired,0,5]),
            'parent41_loss_mean_model_MW':np.mean(pl[paired,j,0]),'baseline_parent41_loss_mean_model_MW':np.mean(pl[paired,0,0]),
            'parent224_loss_mean_model_MW':np.mean(pl[paired,j,1]),'baseline_parent224_loss_mean_model_MW':np.mean(pl[paired,0,1]),
            'max_voltage_bound_violation_pu':au.voltage_bound_violation_pu.max(),'max_Q_bound_violation_model_MVAr':au.Q_bound_violation_model_MVAr.max(),
            'max_NY_zonal_loss_fraction':au.maximum_NY_zonal_loss_fraction.max()})
    pd.DataFrame(rows).to_csv(OUT/'paired_interface_responses.csv',index=False)
    pd.DataFrame(phys).to_csv(OUT/'paired_physical_responses.csv',index=False)
    pd.DataFrame(hourly).to_csv(OUT/'hourly_interface_responses.csv',index=False)
    counts=audit.groupby(['variant','qualified','status'],dropna=False).size().reset_index(name='hours');counts.to_csv(OUT/'solve_status.csv',index=False)
    sources=[OUT/'probe_results.mat',OUT/'probe_audit.csv',OUT/'probe_plan.json',OUT/'probe_inputs.mat',
             ROOT/'scripts/nygrid_2025_remaining_errors/run_probes.m',ROOT/'scripts/nygrid_2025_remaining_errors/prepare_probes.py']
    receipt={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'planned_cases':150,'baseline_hours':15,
        'qualified_cases':int(audit.qualified.sum()),'rejected_cases':int((~audit.qualified).sum()),
        'maximum_baseline_vs_saved_annual_flow_difference_public_MW':maxdiff,
        'maximum_native_or_PJM_group_P_conservation_error_model_MW':float(max(abs(audit.native_PG_sum_change_model_MW).max(),abs(audit.PJM_baseline_PG_sum_change_model_MW).max())),
        'design_selected_without_interface_observations':True,'annual_error_improvement_claimed':False,
        'parent41_probe_conductor_or_DLR_metadata_validated':False,'default_model_changed':False,
        'sources':[{'path':x.relative_to(ROOT).as_posix(),'sha256':sha(x)} for x in sources],
        'source_plan_hashes_still_match':all(sha(ROOT/x['path'])==x['sha256'] for x in plan['sources'])}
    assert receipt['source_plan_hashes_still_match']
    (OUT/'probe_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:receipt[k] for k in ['passed','qualified_cases','rejected_cases','maximum_baseline_vs_saved_annual_flow_difference_public_MW']}))
if __name__=='__main__':main()
