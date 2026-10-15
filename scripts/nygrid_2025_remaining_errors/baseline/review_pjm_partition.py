"""Independently read back the frozen PJM spatial sensitivity; no new PF."""
from pathlib import Path
from datetime import datetime, timezone
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat
from review_root_probes import record

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_remaining_errors/baseline'
PROBE=ROOT/'output/nygrid_2025_remaining_errors/probes'


def main():
    files=[PROBE/f for f in ['pjm_partition_results.csv','pjm_partition_plan.json','pjm_partition_responses.csv',
           'pjm_partition_receipt.json','probe_plan.json','probe_inputs.mat']]
    files += [ROOT/'scripts/nygrid_2025_remaining_errors'/f for f in ['run_pjm_partition_probe.m','score_pjm_partition.py']]
    files += [ROOT/'output/nygrid_2025_latest_handoff/model/latest_model.mat',
              ROOT/'output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_arrays.npz',
              OUT/'independent_probe_review.json']
    before=[record(p) for p in files]
    result=pd.read_csv(files[0]);score=pd.read_csv(files[2]);proof=json.loads(files[3].read_text())
    input=loadmat(files[5],simplify_cells=True);model=loadmat(files[8],simplify_cells=True)['model'];a=np.load(files[9])
    previous=json.loads(files[10].read_text());assert previous['passed'] and previous['maximum_baseline_vs_saved_annual_flow_difference_public_MW']==0
    hours=np.array(input['hour_index'],int);gamma=float(input['gamma']);groups=model['loss_static'][0]['external_gen_group']
    target=[np.flatnonzero((model['generator_bus_ids']==b)&(groups==14)) for b in [130,134]]
    assert all(len(x)==1 for x in target);r130=int(target[0][0]);r134=int(target[1][0])
    ext=np.flatnonzero(model['external']['generator_mask']);scap=np.asarray(model['external']['capability_proxy_MW'])/.95
    positions=[int(np.flatnonzero(ext==r)[0]) for r in [r130,r134]]
    minimum_margin=np.inf;minimum_q=np.inf;max_conservation=0.
    for i,h in enumerate(hours):
        pol=model['loss_static'][int(model['axis']['state_index'][h-1])-1]
        pmin=dict(zip(pol['finite_external_generator_rows']-1,pol['finite_external_Pmin_MW']))
        pmax=dict(zip(pol['finite_external_generator_rows']-1,pol['finite_external_Pmax_MW']))
        for direction in [1,-1]:
            pg=input['baseline_PG'][i].copy();pg[r130]-=direction*100*gamma;pg[r134]+=direction*100*gamma
            d=pg-input['baseline_PG'][i];assert np.count_nonzero(d)==2
            max_conservation=max(max_conservation,float(abs(d.sum())))
            for r,pos in zip([r130,r134],positions):
                margin=min(pg[r]-pmin[r],pmax[r]-pg[r]);minimum_margin=min(minimum_margin,float(margin));assert margin>=-1e-8
                square=scap[pos]**2-pg[r]**2;assert square>0;minimum_q=min(minimum_q,float(np.sqrt(square)))
                assert pg[r]>0 and input['baseline_PG'][i,r]>0
    assert max_conservation<1e-8
    fields=[f'flow_{c}_public_MW' for c in range(1,8)]
    assert len(result)==30 and result.qualified.eq(1).all() and np.isfinite(result[fields]).all().all()
    assert set(result.variant)=={'pjm_130_to134_100MW','pjm_134_to130_100MW'}
    max_score_difference=0.;responses={};outside_max=0.
    for name,g in result.groupby('variant'):
        assert np.array_equal(g.hour_index,hours)
        ix=g.hour_index.to_numpy()-1;pred=g[fields].to_numpy();baseline=a['revised_legacy_signed_literal_from'][ix];obs=a['observed'][ix]
        delta=pred-baseline;outside_max=max(outside_max,float(abs(delta[:,[0,1,3,5,6]]).max()))
        responses[name]={str(n):float(v) for n,v in zip(a['interface_names'],delta.mean(axis=0))}
        for j,interface in enumerate(a['interface_names']):
            row=score.loc[score.variant.eq(name)&score.interface.eq(interface)].iloc[0]
            expected={'mean_response_public_MW':delta[:,j].mean(),'max_abs_response_public_MW':abs(delta[:,j]).max(),
                      'baseline_MAE_public_MW':abs(baseline[:,j]-obs[:,j]).mean(),
                      'variant_MAE_public_MW':abs(pred[:,j]-obs[:,j]).mean(),
                      'MAE_change_public_MW':abs(pred[:,j]-obs[:,j]).mean()-abs(baseline[:,j]-obs[:,j]).mean()}
            assert row.paired_hours==15 and row.rejected_hours==0
            for key,value in expected.items():max_score_difference=max(max_score_difference,abs(float(row[key])-float(value)))
    assert max_score_difference<1e-9 and proof['qualified_cases']==30 and proof['rejected_cases']==0
    assert result.PJM_PG_conservation_model_MW.abs().max()<1e-8
    assert result.max_regional_import_residual_model_MW.abs().max()<1e-5
    assert before==[record(p) for p in files]
    out={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'qualified_cases':30,'rejected_cases':0,
        'same_previously_verified_15_calendar_hours':True,'target_generator_rows_1based':[r130+1,r134+1],
        'minimum_original_finite_P_bound_margin_model_MW':minimum_margin,
        'minimum_recomputed_target_Q_cap_model_MVAr':minimum_q,'changed_generator_status_or_PV_bus_required':False,
        'maximum_independent_PJM_P_conservation_error_model_MW':max_conservation,
        'maximum_independent_score_difference_MW':max_score_difference,
        'mean_responses_public_MW':responses,'maximum_response_outside_TotalEast_CentralEast_public_MW':outside_max,
        'unused_result_field':'maximum_flow_response_public_MW remains NaN; response is independently derived from saved current primary baseline.',
        'source_hashes_unchanged':True,'new_PF_run':False,
        'limitations':['The30cases establish local model sensitivity, not the historical correctness of a PJM allocation.',
            'The±100publicMW redistribution is an analyst-selected finite-bound perturbation; no source-supported hourly allocation is inferred.',
            'No annual error improvement, physical meter certification or full operating qualification is established.',
            'Supplement reruns retain the existing frozen plan after a timestamp-independent equality check.'],
        'sources':before,'producer':record(Path(__file__))}
    (OUT/'independent_pjm_partition_review.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:out[k] for k in ['passed','qualified_cases','rejected_cases','maximum_independent_score_difference_MW','maximum_response_outside_TotalEast_CentralEast_public_MW']}))


if __name__=='__main__':main()
