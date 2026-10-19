"""Independent annual DCPF branch laws, nodal balance and interfaces from VA."""
from pathlib import Path
from datetime import datetime,timezone
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat
from review_bridge_outputs import ROOT,BASE,IDS,record,mx


def main():
    folder=BASE/'experiments/annual_DC_bridge';proof_path=folder/'annual_DC_bridge_receipt.json'
    proof=json.loads(proof_path.read_text());assert proof['completed'] and proof['passed']
    paths=[Path(__file__),Path(__file__).with_name('review_bridge_outputs.py'),proof_path]
    def mat(path,**kw):paths.append(path);return loadmat(path,simplify_cells=True,**kw)
    d=mat(folder/'annual_DC_bridge_arrays.mat');gamma=float(d['gamma'])
    archive_path=ROOT/'output/nygrid_2025_dover_parameters/replay/bounded_x_nominal.npz';paths.append(archive_path)
    with np.load(archive_path,allow_pickle=False) as a:
        old=a['interface_pf'].copy();times=a['timestamp_utc'].astype(str);sourceq=a['qualified'].astype(bool);states=a['network_state_ids'].astype(str)
        phase=a['bank_shift_model_deg'].copy();assert float(a['gamma'])==gamma
    names=['detailed_AC_network_DCPF','restore_parent224_X','restore_parent41_X','restore_all33_X']
    assert np.asarray(d['variant_names']).tolist()==names
    assert np.array_equal(d['hour_index'],np.arange(1,8761)) and np.array_equal(np.asarray(d['timestamp_utc']).astype(str),times)
    assert np.array_equal(np.asarray(d['source_qualified'],bool),sourceq)
    state_names=['refined_2025_pre_may_case','refined_2025_may21_case','refined_2025_may30_case','refined_2025_case']
    stateindex=np.asarray([state_names.index(s)+1 for s in states]);assert np.array_equal(d['state_index'],stateindex)
    fixed=np.zeros(8760,bool)
    for mon in range(1,13):
        a=mat(ROOT/f'output/nygrid_2025_acpf_profile_audit/acpf/monthly/profile_PF_2025_{mon:02d}.mat',
              variable_names=['hour_index','source_qualified','AC_equation_gate','P_profile_preservation_gate'])
        h=np.asarray(a['hour_index'],int)-1;fixed[h]=np.asarray(a['source_qualified'],bool)&np.asarray(a['AC_equation_gate'],bool)&np.asarray(a['P_profile_preservation_gate'],bool)
    assert fixed.sum()==8494 and np.array_equal(fixed,np.asarray(d['cohort'],bool))
    assert np.asarray(d['converged'],bool)[fixed].all() and np.asarray(d['audit_passed'],bool)[fixed].all()
    assert not np.asarray(d['converged'],bool)[~fixed].any() and not np.asarray(d['audit_passed'],bool)[~fixed].any()
    for key in ['interface_model_MW','CE_member_model_MW','VA_deg','slack_increment_MW']:
        assert np.isnan(d[key][~fixed]).all() and np.isfinite(d[key][fixed]).all() if key!='VA_deg' else np.isnan(d[key][~fixed]).all()
    dispatch=mat(ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch.mat',variable_names=['bus_pd','dc_pf','reference_bus'])
    western=mat(ROOT/'output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat',variable_names=['gen_pg','P34_control_targets_model_mw'])
    registry_path=BASE/'model_delta/x_changed_corridors.csv';paths.append(registry_path)
    registry=pd.read_csv(registry_path).branch_row.to_numpy(int)
    sourceDC=np.column_stack([dispatch['dc_pf'],western['P34_control_targets_model_mw']])
    ids=np.asarray(d['bus_id'],int);lookup={int(x):i for i,x in enumerate(ids)}
    interface=np.full_like(d['interface_model_MW'],np.nan);CE=np.full_like(d['CE_member_model_MW'],np.nan)
    maximum_kcl=0.;maximum_flow_reconstruction=0.;maximum_CE_reconstruction=0.;maximum_producer_residual_error=0.
    variant_kcl=np.zeros(4)
    for state,hour in enumerate([523,3360,4000,8508],1):
        b=mat(BASE/f'experiments/representative_bridge/bridge_h{hour:04d}.mat');m=b['detailed'];full=b['full']
        bus=m['bus'];br=m['branch'];parent=np.asarray(m['userdata']['ac_system']['branch_parent_row'],int)
        keep=np.asarray([lookup[int(x)] for x in bus[:,0]]);ix=np.flatnonzero(fixed&(stateindex==state));n=len(ix)
        bi={int(x):i for i,x in enumerate(bus[:,0])};f=np.asarray([bi[int(x)] for x in br[:,0]]);t=np.asarray([bi[int(x)] for x in br[:,1]])
        on=br[:,10]>0;tap=np.where(br[:,8]==0,1.,br[:,8]);base=float(m['baseMVA'])
        shifts=np.broadcast_to(br[:,9],(n,len(br))).copy()
        if state==4:shifts[:,410:412]=phase[ix]
        weights=np.zeros((7,len(br)));cefirst=[]
        mapping=full['if']['map']
        for j,ident in enumerate(IDS):
            members=mapping[mapping[:,0]==ident,1].astype(int);assert len(members)
            for member in members:
                p=abs(member);start=np.flatnonzero((parent==p)&(br[:,0]==full['branch'][p-1,0]));assert len(start)==1
                weights[j,start[0]]+=np.sign(member)
                if ident==5:cefirst.append(int(start[0]))
        P=np.zeros((n,len(bus)))
        for j,gb in enumerate(m['gen'][:,0]):P[:,bi[int(gb)]]+=western['gen_pg'][ix,j]
        P[:,:140]-=dispatch['bus_pd'][ix];P-=bus[:,4]
        for j,c in enumerate(m['dcline']):
            if c[2]>0:P[:,bi[int(c[0])]]-=sourceDC[ix,j];P[:,bi[int(c[1])]]+=sourceDC[ix,j]
        refs=np.asarray([bi[int(x)] for x in np.asarray(dispatch['reference_bus'])[ix]])
        for variant,chosen in enumerate([[],[224],[41],registry]):
            X=br[:,3].copy()
            for p in chosen:
                use=parent==p;X[use]*=full['branch'][p-1,3]/np.sum(X[use])
            angle=np.deg2rad(d['VA_deg'][np.ix_(ix,keep,[variant])][:,:,0]);assert np.isfinite(angle).all()
            coefficient=np.zeros(len(br));coefficient[on]=base/(X[on]*tap[on])
            F=coefficient*(angle[:,f]-angle[:,t]-np.deg2rad(shifts))
            injection=P.copy();injection[np.arange(n),refs]+=d['slack_increment_MW'][ix,variant]
            for j in range(len(br)):injection[:,f[j]]-=F[:,j];injection[:,t[j]]+=F[:,j]
            residual=np.max(abs(injection),axis=1);variant_kcl[variant]=max(variant_kcl[variant],mx(residual));maximum_kcl=max(maximum_kcl,mx(residual))
            assert mx(residual)<1e-7
            maximum_producer_residual_error=max(maximum_producer_residual_error,mx(residual-d['max_KCL_MW'][ix,variant]))
            got=F@weights.T;member=-F[:,cefirst]
            interface[ix,:,variant]=got;CE[ix,:,variant]=member
            error=mx(got-d['interface_model_MW'][ix,:,variant]);maximum_flow_reconstruction=max(maximum_flow_reconstruction,error);assert error<1e-7
            error=mx(member-d['CE_member_model_MW'][ix,:,variant]);maximum_CE_reconstruction=max(maximum_CE_reconstruction,error);assert error<1e-7
            assert mx(member.sum(axis=1)-got[:,4])<1e-7
    all33_error=mx(interface[fixed,:,3]-old[fixed]);assert all33_error<1e-7
    assert mx(interface[fixed,:,2]-interface[fixed,:,0])<1e-7
    assert mx(d['archived_DC_interface_model_MW'][fixed]-old[fixed])==0
    summary=[];reported={x['variant']:x for x in proof['summary']}
    for k,name in enumerate(names):
        ce=interface[fixed,4,k]/gamma;delta=ce-old[fixed,4]/gamma
        r=dict(variant=name,hours=int(fixed.sum()),mean_CE_public_MW=float(ce.mean()),
               mean_CE_minus_archived_DC_public_MW=float(delta.mean()),minimum_CE_minus_archived_DC_public_MW=float(delta.min()),
               maximum_CE_minus_archived_DC_public_MW=float(delta.max()),maximum_independent_nodal_residual_MW=float(variant_kcl[k]))
        for field,expected in [('CE_mean_public_MW',r['mean_CE_public_MW']),('CE_mean_minus_archived_DC_public_MW',r['mean_CE_minus_archived_DC_public_MW']),
                               ('CE_min_minus_archived_DC_public_MW',r['minimum_CE_minus_archived_DC_public_MW']),('CE_max_minus_archived_DC_public_MW',r['maximum_CE_minus_archived_DC_public_MW'])]:
            assert abs(reported[name][field]-expected)<1e-7
        summary.append(r)
    output=BASE/'model_delta/annual_DC_independent_summary.csv';pd.DataFrame(summary).to_csv(output,index=False)
    paths.extend(ROOT/'scripts/nygrid_2025_centraleast_diagnosis/experiments'/name for name in ['run_annual_DC_bridge.m','restore_parent_X_only.m','audit_diagnostic_DCPF.m'])
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent branch-law, input-profile KCL and seven-interface reconstruction from all saved annual DCPF angles',
        fixed_original_detailed_AC_cohort_hours=8494,DC_variant_cases=4*8494,cohort_and_UTC_state_axes_exact=True,
        original_source_P_load_generation_locations_and_six_transfers_used_for_KCL=True,
        hourly_Dover_phases_included_exactly=True,all_seven_original_terminal_interfaces_independently_reconstructed=True,
        maximum_branch_law_interface_reconstruction_error_model_MW=maximum_flow_reconstruction,
        maximum_CE_member_flow_reconstruction_error_model_MW=maximum_CE_reconstruction,
        maximum_independent_nodal_balance_error_MW=maximum_kcl,
        maximum_all33_X_restored_DC_vs_archived_all7_interface_error_model_MW=all33_error,
        branch41_X_only_restoration_leaves_all_lossless_DC_interface_flows_unchanged=True,
        annual_mean_construction_delta_public_MW=summary[0]['mean_CE_minus_archived_DC_public_MW'],
        annual_mean_gap_after_only224_X_restoration_public_MW=summary[1]['mean_CE_minus_archived_DC_public_MW'],
        annual_mean_construction_gap_removed_by224_fraction=1-summary[1]['mean_CE_minus_archived_DC_public_MW']/summary[0]['mean_CE_minus_archived_DC_public_MW'],
        summary=summary,limitations=['These are lossless DC interventions on the AC parameter set. They do not certify AC voltage/Q feasibility or establish a physically correct replacement impedance.',
            'The reported96.9percent is removal of mean construction-related CE flow displacement; it is not a reduction percentage of total AC WAPE.'],
        dependencies=[record(p) for p in dict.fromkeys(paths)],outputs=[record(output)])
    (BASE/'model_delta/annual_DC_independent_review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['dependencies','outputs']},indent=2))


if __name__=='__main__':main()
