"""Read back the nontrivial PJM spatial-allocation sensitivity."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_remaining_errors/probes'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    x=pd.read_csv(OUT/'pjm_partition_results.csv');a=np.load(ROOT/'output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_arrays.npz')
    plan=json.loads((OUT/'probe_plan.json').read_text());hours=np.array([r['hour_index'] for r in plan['samples']]);rows=[]
    assert len(x)==30 and x[['hour_index','variant']].drop_duplicates().shape[0]==30
    assert set(x.qualified.unique())<={0,1};x['qualified']=x.qualified.astype(bool)
    fields=[f'flow_{i}_public_MW' for i in range(1,8)]
    assert np.array_equal(np.isfinite(x[fields]).all(axis=1),x.qualified)
    assert x.PJM_PG_conservation_model_MW.abs().max()<1e-8
    assert x.loc[x.qualified,'max_regional_import_residual_model_MW'].max()<1e-5
    for name,group in x.groupby('variant'):
        assert np.array_equal(group.hour_index,hours)
        g=group[group.qualified];h=g.hour_index.to_numpy()-1;f=g[fields].to_numpy();base=a['revised_legacy_signed_literal_from'][h];obs=a['observed'][h]
        for k,interface in enumerate(a['interface_names']):
            d=f[:,k]-base[:,k]
            rows.append({'variant':name,'interface':interface,'paired_hours':len(g),'rejected_hours':len(group)-len(g),
                         'mean_response_public_MW':d.mean(),'max_abs_response_public_MW':abs(d).max(),
                         'baseline_MAE_public_MW':np.mean(abs(base[:,k]-obs[:,k])),
                         'variant_MAE_public_MW':np.mean(abs(f[:,k]-obs[:,k])),
                         'MAE_change_public_MW':np.mean(abs(f[:,k]-obs[:,k]))-np.mean(abs(base[:,k]-obs[:,k]))})
    pd.DataFrame(rows).to_csv(OUT/'pjm_partition_responses.csv',index=False)
    files=[OUT/'pjm_partition_results.csv',OUT/'pjm_partition_plan.json',OUT/'probe_plan.json',ROOT/'scripts/nygrid_2025_remaining_errors/run_pjm_partition_probe.m',ROOT/'scripts/nygrid_2025_remaining_errors/score_pjm_partition.py']
    receipt={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'planned_cases':30,'qualified_cases':int(x.qualified.sum()),'rejected_cases':int((~x.qualified).sum()),
             'same_15_calendar_hours':True,'annual_candidate_or_improvement_claimed':False,'default_model_changed':False,
             'maximum_PJM_baseline_PG_conservation_error_model_MW':float(x.PJM_PG_conservation_model_MW.abs().max()),
             'maximum_regional_import_residual_model_MW':float(x.loc[x.qualified,'max_regional_import_residual_model_MW'].max()),
             'sources':[{'path':f.relative_to(ROOT).as_posix(),'sha256':sha(f)} for f in files]}
    (OUT/'pjm_partition_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
