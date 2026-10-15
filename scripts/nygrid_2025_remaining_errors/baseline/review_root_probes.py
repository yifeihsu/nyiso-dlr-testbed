"""Independent saved-data/algebra review of the 15-hour root probe campaign."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_remaining_errors/baseline'
PROBE=ROOT/'output/nygrid_2025_remaining_errors/probes'


def record(p):
    with p.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':p.relative_to(ROOT).as_posix(),'sha256':sha}


def main():
    files=[PROBE/f for f in ['probe_plan.json','probe_inputs.mat','probe_results.mat','probe_audit.csv','paired_interface_responses.csv','probe_receipt.json']]
    files += [ROOT/'scripts/nygrid_2025_remaining_errors'/f for f in ['prepare_probes.py','run_probes.m','score_probes.py']]
    files += [ROOT/'output/nygrid_2025_latest_handoff/model'/f for f in ['latest_model.mat','profiles_h0001_4380.mat','profiles_h4381_8760.mat']]
    files += [ROOT/'output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_arrays.npz',
              ROOT/'output/nygrid_2025_western_audit/corrected/model_generator_register.csv',
              ROOT/'output/nygrid_2025_western_audit/corrected/fleet_register.csv',
              ROOT/'output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv',
              ROOT/'output/nygrid_2025_acpf_profile_audit/alignment/interface_operator_terms.csv']
    before=[record(p) for p in files]
    plan=json.loads(files[0].read_text());inputs=loadmat(files[1],simplify_cells=True)
    results=loadmat(files[2],simplify_cells=True);audit=pd.read_csv(files[3]);score=pd.read_csv(files[4])
    proof=json.loads(files[5].read_text());model=loadmat(files[9],simplify_cells=True)['model']
    arrays=np.load(files[12],allow_pickle=False);gamma=float(arrays['gamma'])
    selected=np.asarray(inputs['hour_index'],int);ix=selected-1
    t=pd.DatetimeIndex(pd.to_datetime(arrays['timestamp_utc'],utc=True));states=model['axis']['state_index']
    targets=[pd.Timestamp(year=2025,month=m,day=15,hour=17,tz='UTC') for m in range(1,13)]
    targets += [pd.Timestamp(x) for x in ['2025-05-25T17:00:00Z','2025-05-31T17:00:00Z','2025-12-25T17:00:00Z']]
    expected=[]
    for target in targets:
        near=int(np.argmin(abs(t-target)))
        eligible=np.flatnonzero(arrays['revised_qualified']&(t.month==target.month)&(states==states[near]))
        expected.append(eligible[int(np.argmin(abs(t[eligible]-target)))]+1)
    assert np.array_equal(selected,np.sort(np.unique(expected))) and len(selected)==15
    assert set(states[ix])=={1,2,3,4}
    reg=pd.read_csv(files[13]);fleet=pd.read_csv(files[14]);bus=pd.read_csv(files[15]).set_index('idx')
    reg=reg.merge(fleet[['device_key','prime_mover']],on='device_key',validate='one_to_one',how='left')
    zones=reg.bus_id.map(bus.zone);plants=pd.to_numeric(reg.plant_id,errors='coerce')
    hy=reg.role.eq('native')&reg.fuel_category.eq('Hydro')&reg.prime_mover.eq('HY')
    targets_rows=[np.flatnonzero(hy&plants.eq(p)) for p in [2693,2694]]
    donors=np.flatnonzero(hy&~plants.isin([2693,2694])&~zones.isin(['A','B','D']))
    assert [len(x) for x in targets_rows]==[13,15]
    assert np.array_equal(donors+1,plan['hydro_donor_rows_1based'])
    assert all(np.array_equal(x+1,y) for x,y in zip(targets_rows,plan['hydro_target_rows_1based']))
    assert np.array_equal(model['generator_bus_ids'],reg.bus_id)
    pg=np.zeros((15,1464));lo=pg.copy();hi=pg.copy()
    for path,first in zip(files[10:12],[0,4380]):
        p=loadmat(path,simplify_cells=True)['profiles'];use=(ix>=first)&(ix<first+4380);row=ix[use]-first
        pg[use]=p['generator_PG_MW'][row];lo[use]=p['generator_Pmin_MW'][row];hi[use]=p['generator_Pmax_MW'][row]
    assert np.array_equal(pg,inputs['baseline_PG'])
    max_conservation=0.;max_target_error=0.;max_bound=0.;feasible_count=0
    pjm_new_bus_count=0;pjm_fractions=[];pjm_q_min=[]
    operators=pd.read_csv(files[16]);state_keys=['pre_may','may21','may30','post_dover']
    for i,h in enumerate(selected):
        pol=model['loss_static'][int(states[h-1])-1]
        terms=operators.loc[operators.state.eq(state_keys[int(states[h-1])-1])]
        assert len(terms)==34 and set(terms.interface_index)==set(range(1,8))
        assert np.array_equal(pol['parent'][terms.first_runtime_branch_row.to_numpy()-1],terms.original_branch_row)
        for j in range(4):
            target=targets_rows[j//2];delta=(1 if j%2==0 else -1)*100*gamma
            up=hi[i]-pg[i];down=pg[i]-lo[i]
            target_room=(up if delta>0 else down)[target].sum()
            donor_room=(down if delta>0 else up)[donors].sum()
            feasible=min(target_room,donor_room)>=abs(delta)-1e-9
            assert feasible==bool(inputs['hydro_feasible'][i,j])
            candidate=inputs['hydro_PG'][i,j]
            if not feasible:
                assert np.isnan(candidate).all();continue
            feasible_count+=1
            other=np.ones(1464,bool);other[target]=False;other[donors]=False
            assert np.array_equal(candidate[other],pg[i,other])
            conservation=abs((candidate-pg[i]).sum());max_conservation=max(max_conservation,conservation)
            target_error=abs((candidate[target]-pg[i,target]).sum()-delta);max_target_error=max(max_target_error,target_error)
            violation=max(0.,float(np.max(lo[i,:1436]-candidate[:1436])),float(np.max(candidate[:1436]-hi[i,:1436])))
            max_bound=max(max_bound,violation)
            assert conservation<1e-8 and target_error<1e-8 and violation<1e-8
        external=np.asarray(model['external']['generator_mask'],bool)
        finite_lo=lo[i].copy();finite_hi=hi[i].copy();er=pol['finite_external_generator_rows']-1
        finite_lo[er]=pol['finite_external_Pmin_MW'];finite_hi[er]=pol['finite_external_Pmax_MW']
        pjm=np.flatnonzero(pol['external_gen_group']==14);cap=finite_hi[pjm]-finite_lo[pjm]
        frac=(pg[i,pjm].sum()-finite_lo[pjm].sum())/cap.sum();assert 0<=frac<=1
        changed=finite_lo[pjm]+frac*cap
        assert np.isfinite(changed).all() and abs(changed.sum()-pg[i,pjm].sum())<1e-8
        assert np.all(changed>=finite_lo[pjm]-1e-8) and np.all(changed<=finite_hi[pjm]+1e-8)
        oldactive=(hi[i]>0)|(lo[i]<0);oldactive[external]=pg[i,external]!=0
        newactive=oldactive.copy();newactive[pjm]=finite_hi[pjm]>0
        newly_active=set(model['generator_bus_ids'][newactive])-set(model['generator_bus_ids'][oldactive])
        pjm_new_bus_count+=len(newly_active);assert not newly_active
        scap=np.asarray(model['external']['capability_proxy_MW'])/.95
        # capability_proxy_MW is indexed by external generator rows.
        ext_rows=np.flatnonzero(external);pjm_pos=np.flatnonzero(np.isin(ext_rows,pjm))
        q_squared=scap[pjm_pos]**2-changed**2
        assert np.min(q_squared)>0
        pjm_fractions.append(float(frac));pjm_q_min.append(float(np.sqrt(q_squared).min()))
    f=results['flows'];assert np.array_equal(results['hours'],selected)
    qualified=audit.qualified.to_numpy().astype(bool).reshape(15,10)
    assert np.array_equal(np.isfinite(f).all(axis=2),qualified)
    assert np.isnan(f[~qualified]).all() and qualified[:,0].all()
    diff=float(np.max(abs(f[:,0]-arrays['revised_legacy_signed_literal_from'][ix])))
    assert diff<1e-6
    max_score_delta=0.
    for j,variant in enumerate(plan['variants']):
        paired=qualified[:,j];y=arrays['observed'][ix[paired]];prediction=f[paired,j];baseline=f[paired,0]
        for k,name in enumerate(arrays['interface_names']):
            row=score.loc[score.variant.eq(variant)&score.interface.eq(name)].iloc[0]
            assert int(row.paired_hours)==paired.sum()
            checks={'variant_MAE_public_MW':np.abs(prediction[:,k]-y[:,k]).mean(),
                    'baseline_MAE_public_MW':np.abs(baseline[:,k]-y[:,k]).mean(),
                    'mean_response_public_MW':(prediction[:,k]-baseline[:,k]).mean(),
                    'variant_bias_public_MW':(prediction[:,k]-y[:,k]).mean(),
                    'MAE_change_public_MW':np.abs(prediction[:,k]-y[:,k]).mean()-np.abs(baseline[:,k]-y[:,k]).mean()}
            for key,value in checks.items():max_score_delta=max(max_score_delta,abs(float(row[key])-float(value)))
    assert max_score_delta<1e-9
    assert proof['qualified_cases']==int(qualified.sum())==142
    assert proof['rejected_cases']==int((~qualified).sum())==8
    assert before==[record(p) for p in files]
    result={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),
        'calendar_selection_reproduced_without_residuals':True,'selected_hours':selected.tolist(),
        'four_current_model_states_and_generator_bus_mapping_verified':True,
        'feasible_hydro_input_cases':feasible_count,'hydro_target_counts':[13,15],'donor_count':len(donors),
        'maximum_hydro_input_conservation_error_model_MW':max_conservation,
        'maximum_hydro_target_delta_error_model_MW':max_target_error,'maximum_native_bound_violation_MW':max_bound,
        'PJM_capacity_fraction_range':[min(pjm_fractions),max(pjm_fractions)],
        'PJM_recomputed_Q_cap_minimum_model_MVAr':min(pjm_q_min),'newly_active_PJM_bus_count':pjm_new_bus_count,
        'all_34_operator_terms_bound_to_parent_rows_in_all_selected_states':True,
        'maximum_baseline_vs_saved_annual_flow_difference_public_MW':diff,
        'maximum_independent_score_difference_public_MW':max_score_delta,
        'qualified_cases':int(qualified.sum()),'rejected_cases':int((~qualified).sum()),
        'whole_system_operating_qualified_cases':int(audit.operating_qualified.sum()),
        'fixed_during_review':['Root corrected initially empty state operator matching before final export.',
            'Root corrected integer inversion of qualified flag before final receipt; rejected count is8.',
            'Root added equality check between finite exported flows and equation-qualified audit flags.'],
        'limitations':['These15calendar-selected hours establish local response, not annual error improvement.',
            'PJM dispatch and loss shares remain alternative model proxies, not observed physical dispatch.',
            'Parent41admittance probes do not validate conductor or DLR metadata.',
            'No additional solver run was performed in this independent review; saved results and code/algebra were inspected.'],
        'source_hashes_unchanged':True,'sources':before,'producer':record(Path(__file__))}
    (OUT/'independent_probe_review.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['passed','qualified_cases','rejected_cases','maximum_baseline_vs_saved_annual_flow_difference_public_MW','maximum_independent_score_difference_public_MW']}))


if __name__=='__main__':main()
