"""Independent annual audit of three declared allocations of solved AC losses."""
from pathlib import Path
from datetime import datetime,timezone
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat
from review_bridge_outputs import ROOT,BASE,IDS,record,mx


def main():
    folder=BASE/'experiments/annual_loss_loaded_DCF';proof_path=folder/'annual_loss_loaded_receipt.json'
    proof=json.loads(proof_path.read_text());assert proof['completed'] and proof['passed']
    paths=[Path(__file__),Path(__file__).with_name('review_bridge_outputs.py'),proof_path]
    def mat(path,**kw):paths.append(path);return loadmat(path,simplify_cells=True,**kw)
    d=mat(folder/'annual_loss_loaded_arrays.mat');cohort=np.asarray(d['cohort'],bool);assert cohort.sum()==8494
    labels=['half_each_runtime_branch_end','all_at_runtime_from_end','all_at_runtime_to_end'];assert np.asarray(d['labels']).tolist()==labels
    dc=mat(BASE/'experiments/annual_DC_bridge/annual_DC_bridge_arrays.mat',variable_names=['cohort','interface_model_MW','archived_DC_interface_model_MW','gamma'])
    assert np.array_equal(cohort,np.asarray(dc['cohort'],bool)) and d['gamma']==dc['gamma'];gamma=float(d['gamma'])
    dc_review_path=BASE/'model_delta/annual_DC_independent_review.json';dc_review=json.loads(dc_review_path.read_text());assert dc_review['passed'];paths.append(dc_review_path)
    archive_path=ROOT/'output/nygrid_2025_dover_parameters/replay/bounded_x_nominal.npz';paths.append(archive_path)
    with np.load(archive_path,allow_pickle=False) as a:
        times=a['timestamp_utc'].astype(str);states=a['network_state_ids'].astype(str);phase=a['bank_shift_model_deg'].copy();q=a['qualified'].astype(bool)
        archive=a['interface_pf'].copy();assert float(a['gamma'])==gamma
    assert np.array_equal(d['hour_index'],np.arange(1,8761)) and np.array_equal(np.asarray(d['timestamp_utc']).astype(str),times)
    assert np.array_equal(np.asarray(d['source_qualified'],bool),q)
    state_names=['refined_2025_pre_may_case','refined_2025_may21_case','refined_2025_may30_case','refined_2025_case']
    stateindex=np.asarray([state_names.index(s)+1 for s in states]);assert np.array_equal(d['state_index'],stateindex)
    assert np.asarray(d['audit_passed'],bool)[cohort].all() and not np.asarray(d['audit_passed'],bool)[~cohort].any()
    for key in ['interface_model_MW','baseline_AC_interface_model_MW','VA_deg','slack_increment_MW','baseline_AC_loss_MW']:
        assert np.isnan(d[key][~cohort]).all()
    source=mat(ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch.mat',variable_names=['bus_pd','bus_qd','dc_pf','reference_bus'])
    western=mat(ROOT/'output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat',variable_names=['gen_pg','P34_control_targets_model_mw'])
    dcP=np.column_stack([source['dc_pf'],western['P34_control_targets_model_mw']])
    ids=np.asarray(d['bus_id'],int);lookup={int(x):i for i,x in enumerate(ids)}
    templates={}
    for state,hour in enumerate([523,3360,4000,8508],1):
        b=mat(BASE/f'experiments/representative_bridge/bridge_h{hour:04d}.mat');m=b['detailed'];bus=m['bus'];br=m['branch'];full=b['full']
        keep=np.asarray([lookup[int(x)] for x in bus[:,0]]);bi={int(x):i for i,x in enumerate(bus[:,0])}
        f=np.asarray([bi[int(x)] for x in br[:,0]]);t=np.asarray([bi[int(x)] for x in br[:,1]])
        parent=np.asarray(m['userdata']['ac_system']['branch_parent_row'],int);W=np.zeros((7,len(br)));mapping=full['if']['map']
        for j,ident in enumerate(IDS):
            members=mapping[mapping[:,0]==ident,1].astype(int);assert len(members)
            for member in members:
                p=abs(member);first=np.flatnonzero((parent==p)&(br[:,0]==full['branch'][p-1,0]));assert len(first)==1
                W[j,first[0]]+=np.sign(member)
        templates[state]=(m,keep,bi,f,t,W)
    result=np.full_like(d['interface_model_MW'],np.nan);baseline=np.full_like(d['baseline_AC_interface_model_MW'],np.nan)
    seen=np.zeros(8760,bool);maxkcl=0.;maxflow=0.;maxloss=0.;maxslack=0.
    for month in range(1,13):
        old=mat(ROOT/f'output/nygrid_2025_acpf_profile_audit/acpf/monthly/profile_PF_2025_{month:02d}.mat',
                variable_names=['hour_index','timestamp_utc','gamma','source_qualified','AC_equation_gate','P_profile_preservation_gate','PF','PT','PD','QD','branch_keys'])
        h=np.asarray(old['hour_index'],int)-1;assert not seen[h].any();seen[h]=True
        assert np.array_equal(np.asarray(old['timestamp_utc']).astype(str),times[h]) and float(old['gamma'])==gamma
        good=np.asarray(old['source_qualified'],bool)&np.asarray(old['AC_equation_gate'],bool)&np.asarray(old['P_profile_preservation_gate'],bool)
        assert np.array_equal(good,cohort[h]);keylookup={str(x):i for i,x in enumerate(np.asarray(old['branch_keys']).astype(str))}
        for state in np.unique(stateindex[h]):
            local=np.flatnonzero(good&(stateindex[h]==state));ix=h[local]
            if not len(ix):continue
            m,keep,bi,f,t,W=templates[int(state)];br=m['branch'];bus=m['bus'];n=len(ix);base=float(m['baseMVA'])
            branchkeys=np.asarray(m['userdata']['ac_system']['branch_keys']).astype(str);il=np.asarray([keylookup[x] for x in branchkeys])
            assert np.array_equal(old['PD'][np.ix_(local,keep)][:,:140],source['bus_pd'][ix])
            assert np.array_equal(old['QD'][np.ix_(local,keep)][:,:140],source['bus_qd'][ix])
            pf=old['PF'][np.ix_(local,il)];pt=old['PT'][np.ix_(local,il)];loss=pf+pt
            assert np.isfinite(loss).all() and np.min(loss)>-1e-6 and mx(loss[:,br[:,10]==0])<1e-8
            baseline[ix]=pf@W.T;assert mx(baseline[ix]-d['baseline_AC_interface_model_MW'][ix])<1e-7
            total=loss.sum(axis=1);maxloss=max(maxloss,mx(total-d['baseline_AC_loss_MW'][ix]));assert mx(total-d['baseline_AC_loss_MW'][ix])<1e-7
            fromloss=np.zeros((n,len(bus)));toloss=np.zeros_like(fromloss)
            for j in range(len(br)):fromloss[:,f[j]]+=loss[:,j];toloss[:,t[j]]+=loss[:,j]
            P=np.zeros((n,len(bus)))
            for j,gb in enumerate(m['gen'][:,0]):P[:,bi[int(gb)]]+=western['gen_pg'][ix,j]
            P[:,:140]-=source['bus_pd'][ix];P-=bus[:,4]
            for j,c in enumerate(m['dcline']):
                if c[2]>0:P[:,bi[int(c[0])]]-=dcP[ix,j];P[:,bi[int(c[1])]]+=dcP[ix,j]
            shifts=np.broadcast_to(br[:,9],(n,len(br))).copy()
            if state==4:shifts[:,410:412]=phase[ix]
            tap=np.where(br[:,8]==0,1.,br[:,8]);on=br[:,10]>0;bcoef=np.zeros(len(br));bcoef[on]=base/(br[on,3]*tap[on])
            refs=np.asarray([bi[int(x)] for x in source['reference_bus'][ix]])
            for k,added in enumerate([(fromloss+toloss)/2,fromloss,toloss]):
                assert mx(added.sum(axis=1)-total)<1e-7
                angle=np.deg2rad(d['VA_deg'][np.ix_(ix,keep,[k])][:,:,0]);assert np.isfinite(angle).all()
                F=bcoef*(angle[:,f]-angle[:,t]-np.deg2rad(shifts));net=P-added
                net[np.arange(n),refs]+=d['slack_increment_MW'][ix,k]
                for j in range(len(br)):net[:,f[j]]-=F[:,j];net[:,t[j]]+=F[:,j]
                maxkcl=max(maxkcl,mx(net));assert mx(net)<1e-7
                maxslack=max(maxslack,mx(d['slack_increment_MW'][ix,k]-total));assert mx(d['slack_increment_MW'][ix,k]-total)<1e-6
                got=F@W.T;result[ix,:,k]=got;error=mx(got-d['interface_model_MW'][ix,:,k]);maxflow=max(maxflow,error);assert error<1e-7
    assert seen.all()
    assert mx(d['baseline_detailed_DCF_interface_model_MW'][cohort]-dc['interface_model_MW'][cohort,:,0])==0
    assert mx(d['archived_DC_interface_model_MW'][cohort]-archive[cohort])==0
    construction=dc['interface_model_MW'][:,:,0]-archive
    allocation=result-dc['interface_model_MW'][:,:,0,None]
    remaining=baseline[:,:,None]-result
    for key,value in [('construction_delta_model_MW',construction),('loss_allocation_delta_model_MW',allocation),('remaining_AC_minus_loss_loaded_DCF_model_MW',remaining)]:
        assert mx(value[cohort]-d[key][cohort])<1e-7
    identity=construction[:,:,None]+allocation+remaining-(baseline-archive)[:,:,None]
    assert mx(identity[cohort])<1e-8
    summary=[];proofrows={r['allocation']:r for r in proof['checks']}
    for k,label in enumerate(labels):
        delta=allocation[cohort,4,k]/gamma;rest=remaining[cohort,4,k]/gamma
        r=dict(allocation=label,hours=8494,mean_loss_allocation_delta_public_MW=float(delta.mean()),
               mean_remaining_AC_minus_loss_loaded_public_MW=float(rest.mean()),mean_absolute_remaining_public_MW=float(abs(rest).mean()),
               maximum_absolute_remaining_public_MW=float(abs(rest).max()))
        for key,value in r.items():
            if key not in ['allocation','hours']:assert abs(value-proofrows[label][key])<1e-7
        summary.append(r)
    output=BASE/'model_delta/annual_loss_independent_summary.csv';pd.DataFrame(summary).to_csv(output,index=False)
    paths.extend(ROOT/'scripts/nygrid_2025_centraleast_diagnosis/experiments'/n for n in ['run_annual_loss_loaded_DCF.m','audit_diagnostic_DCPF.m'])
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent annual source-loss reconstruction, three allocation rules, branch laws, KCL and exact seven-interface additive identities',
        fixed_original_cohort_hours=8494,loss_loaded_DC_cases=25482,original_UTC_state_and_physical_branch_axes_preserved=True,
        all_three_runtime_endpoint_loss_allocations_reconstructed_from_frozen_AC_PF_PT=True,
        no_negative_roundoff_loss_clipping_applied=True,source_non_slack_P_generation_and_six_transfers_preserved=True,
        original_X_status_taps_and_hourly_phases_used_for_all_saved_angle_checks=True,
        maximum_frozen_AC_loss_sum_reconstruction_error_MW=maxloss,
        maximum_loaded_DC_interface_reconstruction_error_model_MW=maxflow,
        maximum_independent_nodal_balance_error_MW=maxkcl,maximum_slack_minus_added_loss_error_MW=maxslack,
        maximum_additive_identity_error_model_MW=mx(identity[cohort]),
        annual_CE_total_AC_minus_archived_DC_mean_public_MW=float((baseline[cohort,4]-archive[cohort,4]).mean()/gamma),
        annual_CE_construction_mean_public_MW=float(construction[cohort,4].mean()/gamma),summary=summary,
        limitations=['The loss demands are computed from the already solved baseline AC branch powers. This is an after-the-fact reconstruction, not a forward independent prediction or observed loss measurement.',
            'The from/to labels refer to saved runtime branch orientation, not electric flow direction; all allocations contain the same total solved losses.',
            'Allocation sensitivity is nonunique and does not define a confidence interval or uniquely identify physical causality.',
            'Loaded DC has artificial demand at some numerical section interiors; original-terminal source-target differences include those demands and must not be called actual resistive branch losses.',
            'The additive numbers are mean signed flow displacements, not a decomposition of WAPE percentages.'],
        dependencies=[record(p) for p in dict.fromkeys(paths)],outputs=[record(output)])
    (BASE/'model_delta/annual_loss_independent_review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['dependencies','outputs']},indent=2))


if __name__=='__main__':main()
