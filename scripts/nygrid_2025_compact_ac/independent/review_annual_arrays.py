"""Independent annual compact-PF readback from saved voltage/flow arrays.

No production solver or auditor is imported, and no new PF is run. The manual
branch laws, Kirchhoff balance, exact passive-interior lift, immutable cohort,
input profiles and paired error thresholds are checked separately.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.linalg import solve
from probe_kron_feasibility import network, rec

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'output/nygrid_2025_compact_ac'
OLD = ROOT / 'output/nygrid_2025_acpf_profile_audit/acpf'
OUT = BASE / 'independent'


def flag(m, name):
    return np.asarray(m[name], bool).reshape(-1)


def maximum(x):
    return float(np.max(np.abs(x), initial=0))


def main():
    paths = [Path(__file__), Path(__file__).with_name('probe_kron_feasibility.py')]

    def mat(path, **kw):
        paths.append(path)
        return loadmat(path, simplify_cells=True, **kw)

    receipt_path = BASE / 'validation/annual_compact_PF_receipt.json'
    producer = json.loads(receipt_path.read_text()); paths.append(receipt_path)
    assert producer['completed'] and producer['passed']
    axes = mat(BASE / 'validation/annual_axes.mat')
    anchor_path = ROOT / 'output/nygrid_2025_slim/network/bus_register.csv'
    anchors = pd.read_csv(anchor_path).model_bus.to_numpy(int); paths.append(anchor_path)
    assert len(anchors) == len(set(anchors)) == 148
    dispatch = mat(ROOT / 'output/nygrid_2025_dispatch/dispatch/dispatch.mat',
                   variable_names=['hour_index','timestamp_utc','bus_pd','bus_qd','dc_pf','reference_bus','gamma'])
    western = mat(ROOT / 'output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat',
                  variable_names=['gen_pg','P34_control_targets_model_mw','timestamp_utc','qualified','gamma'])
    dover = mat(ROOT / 'output/nygrid_2025_dover_parameters/replay/operating_states.mat',
                variable_names=['qualified','post_full_service','controls','timestamp_utc','gamma'])
    npz_path = ROOT / 'output/nygrid_2025_dover_parameters/replay/bounded_x_nominal.npz'
    paths.append(npz_path)
    with np.load(npz_path, allow_pickle=False) as d:
        source_state = d['network_state_ids'].astype(str)
        assert np.array_equal(d['timestamp_utc'].astype(str), np.asarray(dispatch['timestamp_utc']).astype(str))
        assert np.array_equal(d['qualified'].astype(bool), flag(dover,'qualified'))
    state_names = ['refined_2025_pre_may_case','refined_2025_may21_case',
                   'refined_2025_may30_case','refined_2025_case']
    expected_state = np.asarray([state_names.index(s)+1 for s in source_state])
    source_q = flag(dover, 'qualified'); assert source_q.sum() == 8651
    assert np.all(flag(western,'qualified')[source_q])
    gamma = float(dispatch['gamma'])
    assert gamma == float(western['gamma']) == float(dover['gamma']) == float(axes['gamma'])
    times = np.asarray(dispatch['timestamp_utc']).astype(str)
    for s in [axes, western, dover]:
        assert np.array_equal(np.asarray(s['timestamp_utc']).astype(str), times)
    assert np.array_equal(axes['topology_state_index'], expected_state)
    assert np.array_equal(flag(axes,'source_qualified'), source_q)
    assert np.array_equal(axes['hour_index'], np.arange(1,8761))
    local_month = pd.to_datetime(times, utc=True).tz_convert('America/New_York').month.to_numpy()
    assert np.array_equal(axes['model_month'], local_month)
    ids = np.asarray(axes['bus_id'],int); key = np.asarray(axes['branch_keys']).astype(str)
    lookup = {int(x):i for i,x in enumerate(ids)}; key_lookup = {x:i for i,x in enumerate(key)}
    keep = np.asarray([lookup[int(x)] for x in anchors])
    templates = {}
    for state, hour in enumerate([1,3360,3576,8472],1):
        model = mat(BASE/f'models/compact_ac_h{hour:04d}.mat')['model']
        m = model['detailed_mpc']; assert expected_state[hour-1] == state
        b = np.asarray([lookup[int(x)] for x in m['bus'][:,0]])
        l = np.asarray([key_lookup[x] for x in np.asarray(model['branch_keys']).astype(str)])
        k = np.asarray([np.flatnonzero(m['bus'][:,0] == x)[0] for x in anchors])
        e = np.asarray([j for j in range(len(b)) if j not in set(k)])
        assert np.all(m['bus'][e,2:4] == 0)
        assert not np.isin(m['gen'][:,0],m['bus'][e,0]).any()
        assert not np.isin(m['dcline'][:,:2],m['bus'][e,0]).any()
        assert np.array_equal(ids[b],m['bus'][:,0])
        assert np.array_equal(axes['branch_from_bus'][l],m['branch'][:,0])
        assert np.array_equal(axes['branch_to_bus'][l],m['branch'][:,1])
        assert np.array_equal(axes['branch_parent_row'][l],model['branch_parent_row'])
        assert np.array_equal(axes['DC_from_bus'],m['dcline'][:,0])
        assert np.array_equal(axes['DC_to_bus'],m['dcline'][:,1])
        templates[state] = (m,b,l,k,e)
    bounds = dict(branch_law_MVA=1e-6,current_A=1e-5,series_loss_MW=1e-6,
                  nodal_PQ_MVA=1e-5,interior_lift_pu=1e-8,eliminated_current_pu=1e-8,
                  nonreference_bus_generation_P_MW=1e-7,fixed_transfer_P_MW=1e-7)
    errors = {k:0. for k in bounds}
    paired_errors = dict(voltage_pu=0.,branch_PQ_MVA=0.,current_A=0.,bus_generation_PQ_MVA=0.,DC_PQ_MVA=0.)
    all_seen = np.zeros(8760,bool); all_good = np.zeros(8760,bool)
    old_good = np.zeros(8760,bool); all_equiv = np.zeros(8760,bool); all_vq = np.zeros(8760,bool)
    month_rows=[]
    qnames = ['PF','QF','PT','QT']; inames = ['Iseries','Ifrom','Ito']
    gnames = ['bus_PG','bus_QG']; dnames = ['DC_PF','DC_PT','DC_QF','DC_QT']
    for month in range(1,13):
        path=BASE/f'validation/monthly/profile_PF_2025_{month:02d}.mat'
        a=mat(path); old=mat(OLD/f'monthly/profile_PF_2025_{month:02d}.mat')
        h=np.asarray(a['hour_index'],int)-1; n=len(h)
        assert np.array_equal(h,np.flatnonzero(local_month==month)) and not all_seen[h].any()
        all_seen[h]=True
        for v in [a,old]:
            assert np.array_equal(v['hour_index'],h+1)
            assert np.array_equal(np.asarray(v['timestamp_utc']).astype(str),times[h])
            assert float(v['gamma'])==gamma
            assert np.array_equal(flag(v,'source_qualified'),source_q[h])
            assert np.array_equal(v['bus_id'],ids)
            assert np.array_equal(np.asarray(v['branch_keys']).astype(str),key)
        assert np.array_equal(a['topology_state_index'],expected_state[h])
        assert np.array_equal(a['retained_bus_ids'],anchors)
        assert np.array_equal(flag(a,'PF_attempted'),source_q[h])
        assert not flag(a,'solver_exception').any()
        good = (source_q[h] & flag(a,'AC_equation_gate') & flag(a,'P_profile_preservation_gate')
                & flag(a,'reduction_and_equation_gate') & (a['native_retained_bus_count']==148))
        og = source_q[h]&flag(old,'AC_equation_gate')&flag(old,'P_profile_preservation_gate')
        all_good[h]=good;old_good[h]=og;all_vq[h]=flag(a,'VQ_and_generator_assumption_gate')
        assert np.array_equal(flag(a,'detailed_baseline_qualified'),og)
        assert np.all(good[og])
        assert np.all(flag(a,'PF_converged')[good])
        assert np.array_equal(a['retained_VM'][good],a['VM'][good][:,keep])
        assert np.array_equal(a['retained_VA'][good],a['VA'][good][:,keep])
        # Excluded clock positions are retained as missing data with false gates.
        for name in ['AC_equation_gate','P_profile_preservation_gate','reduction_and_equation_gate',
                     'PF_converged','computed_current_available','paired_detailed_solution_equivalent']:
            assert not flag(a,name)[~source_q[h]].any()
        for name in ['VM','VA','PD','QD']+qnames+inames+gnames+dnames:
            assert np.isnan(a[name][~source_q[h]]).all()
        expected_equiv=np.zeros(n,bool)
        for state in np.unique(expected_state[h]):
            m,b,l,k,e=templates[int(state)]; br=m['branch'];bus=m['bus'];base=float(m['baseMVA'])
            idx=np.flatnonzero((expected_state[h]==state)&source_q[h]); gh=h[idx]
            assert np.array_equal(a['PD'][idx,:140],dispatch['bus_pd'][gh])
            assert np.array_equal(a['QD'][idx,:140],dispatch['bus_qd'][gh])
            assert np.all(a['PD'][np.ix_(idx,b[140:])]==0) and np.all(a['QD'][np.ix_(idx,b[140:])]==0)
            bp=np.zeros(len(ids),bool);bp[b]=True
            lp=np.zeros(len(key),bool);lp[l]=True
            active=np.zeros(len(key),bool);active[l]=br[:,10]>0
            for name,value in [('bus_present',bp),('branch_present',lp),('branch_active',active)]:
                assert np.array_equal(np.asarray(a[name],bool)[idx],np.broadcast_to(value,(len(idx),len(value))))
                assert np.array_equal(np.asarray(a[name],bool)[idx],np.asarray(old[name],bool)[idx])
            use=np.flatnonzero((expected_state[h]==state)&good); hu=h[use]
            if not len(use):continue
            V=a['VM'][np.ix_(use,b)]*np.exp(1j*np.deg2rad(a['VA'][np.ix_(use,b)]))
            assert np.isfinite(V).all()
            busindex={int(x):i for i,x in enumerate(bus[:,0])}
            f=np.asarray([busindex[int(x)] for x in br[:,0]]);t=np.asarray([busindex[int(x)] for x in br[:,1]])
            on=br[:,10]>0;y=np.zeros(len(br),complex);y[on]=1/(br[on,2]+1j*br[on,3])
            bc=np.where(on,1j*br[:,4]/2,0.)
            shifts=np.broadcast_to(br[:,9],(len(use),len(br))).copy()
            if state==4:
                phase=np.asarray(dover['controls']['bounded_x_nominal']['bank_shift_model_deg'])[hu]
                assert np.array_equal(a['Dover_model_SHIFT_deg'][use],phase)
                shifts[:,410:412]=phase
            else:assert np.isnan(a['Dover_model_SHIFT_deg'][use]).all()
            tap=np.where(br[:,8]==0,1,br[:,8])*np.exp(1j*np.deg2rad(shifts))
            Is=y*(V[:,f]/tap-V[:,t]);If=Is/np.conj(tap)+bc*V[:,f]/abs(tap)**2;It=-Is+bc*V[:,t]
            Sf=base*V[:,f]*np.conj(If);St=base*V[:,t]*np.conj(It)
            savedSf=a['PF'][np.ix_(use,l)]+1j*a['QF'][np.ix_(use,l)]
            savedSt=a['PT'][np.ix_(use,l)]+1j*a['QT'][np.ix_(use,l)]
            errors['branch_law_MVA']=max(errors['branch_law_MVA'],maximum(Sf-savedSf),maximum(St-savedSt))
            current_values=[abs(Is)*base*1000/(np.sqrt(3)*bus[t,9]),
                            abs(If)*base*1000/(np.sqrt(3)*bus[f,9]),abs(It)*base*1000/(np.sqrt(3)*bus[t,9])]
            for name,value in zip(inames,current_values):
                errors['current_A']=max(errors['current_A'],maximum(value-a[name][np.ix_(use,l)]))
            errors['series_loss_MW']=max(errors['series_loss_MW'],maximum((Sf+St).real-base*br[:,2]*abs(Is)**2))
            net=np.zeros_like(V);Ibus=np.zeros_like(V)
            for j in range(len(br)):
                net[:,f[j]]+=Sf[:,j];net[:,t[j]]+=St[:,j]
                Ibus[:,f[j]]+=If[:,j];Ibus[:,t[j]]+=It[:,j]
            shunt=abs(V)**2*(bus[:,4]-1j*bus[:,5])
            Ibus+=(bus[:,4]+1j*bus[:,5])*V/base
            errors['eliminated_current_pu']=max(errors['eliminated_current_pu'],maximum(Ibus[:,e]))
            Sdc=np.zeros_like(V)
            for j,d in enumerate(m['dcline']):
                if d[2]<=0:continue
                Sdc[:,busindex[int(d[0])]]+=-a['DC_PF'][use,j]+1j*a['DC_QF'][use,j]
                Sdc[:,busindex[int(d[1])]]+=a['DC_PT'][use,j]+1j*a['DC_QT'][use,j]
            Sgen=a['bus_PG'][np.ix_(use,b)]+1j*a['bus_QG'][np.ix_(use,b)]
            Sload=a['PD'][np.ix_(use,b)]+1j*a['QD'][np.ix_(use,b)]
            errors['nodal_PQ_MVA']=max(errors['nodal_PQ_MVA'],maximum(Sgen+Sdc-Sload-shunt-net))
            expected_dc=np.column_stack([dispatch['dc_pf'][hu],western['P34_control_targets_model_mw'][hu]])
            errors['fixed_transfer_P_MW']=max(errors['fixed_transfer_P_MW'],maximum(a['DC_PF'][use]-expected_dc))
            expectedPG=np.zeros_like(V.real)
            for j,gb in enumerate(m['gen'][:,0]):expectedPG[:,busindex[int(gb)]]+=western['gen_pg'][hu,j]
            pgdiff=a['bus_PG'][np.ix_(use,b)]-expectedPG
            for j,rbus in enumerate(np.asarray(dispatch['reference_bus'])[hu]):pgdiff[j,busindex[int(rbus)]]=0
            errors['nonreference_bus_generation_P_MW']=max(errors['nonreference_bus_generation_P_MW'],maximum(pgdiff))
            # Recover passive voltages from independently assembled complex Y.
            # Three states have fixed Y; the post-Dover bank phases vary hourly.
            if state != 4:
                Y=network(m)[0];recovered=-solve(Y[np.ix_(e,e)],Y[np.ix_(e,k)]@V[:,k].T,assume_a='gen').T
                errors['interior_lift_pu']=max(errors['interior_lift_pu'],maximum(recovered-V[:,e]))
            else:
                for j in range(len(use)):
                    mm=copy.copy(m);mm['branch']=br.copy();mm['branch'][:,9]=shifts[j]
                    Y=network(mm)[0];recovered=-solve(Y[np.ix_(e,e)],Y[np.ix_(e,k)]@V[j,k],assume_a='gen')
                    errors['interior_lift_pu']=max(errors['interior_lift_pu'],maximum(recovered-V[j,e]))
            paired=np.flatnonzero((expected_state[h]==state)&og)
            va=a['VM'][np.ix_(paired,b)]*np.exp(1j*np.deg2rad(a['VA'][np.ix_(paired,b)]))
            vo=old['VM'][np.ix_(paired,b)]*np.exp(1j*np.deg2rad(old['VA'][np.ix_(paired,b)]))
            assert np.array_equal(a['PD'][np.ix_(paired,b)],old['PD'][np.ix_(paired,b)])
            assert np.array_equal(a['QD'][np.ix_(paired,b)],old['QD'][np.ix_(paired,b)])
            local={'voltage_pu':np.max(abs(va-vo),axis=1)}
            for outname,names,cols in [('branch_PQ_MVA',qnames,l),('current_A',inames,l),
                                      ('bus_generation_PQ_MVA',gnames,b),('DC_PQ_MVA',dnames,np.arange(6))]:
                local[outname]=np.max(np.column_stack([abs(a[name][np.ix_(paired,cols)]-old[name][np.ix_(paired,cols)]) for name in names]),axis=1)
            equiv=np.ones(len(paired),bool)
            for name,limit in [('voltage_pu',1e-7),('branch_PQ_MVA',1e-4),('current_A',1e-3),
                               ('bus_generation_PQ_MVA',1e-4),('DC_PQ_MVA',1e-4)]:
                paired_errors[name]=max(paired_errors[name],maximum(local[name]));equiv&=local[name]<limit
            expected_equiv[paired]=equiv
        assert np.array_equal(flag(a,'paired_detailed_solution_equivalent'),expected_equiv)
        all_equiv[h]=expected_equiv
        month_rows.append(dict(month=month,clock_hours=n,source_qualified=int(source_q[h].sum()),
                               compact_qualified=int(good.sum()),fixed_detailed_cohort=int(og.sum()),paired_equivalent=int(expected_equiv.sum())))
        print(f'Independent annual readback month {month:02d}: qualified {good.sum()}, pairs {expected_equiv.sum()}',flush=True)
    assert all_seen.all() and old_good.sum()==8494 and all_equiv[old_good].all()
    for name,limit in bounds.items():assert errors[name]<limit,(name,errors[name],limit)
    assert all_good.sum()==producer['reduction_and_equation_qualified_hours']
    assert all_equiv.sum()==producer['fixed_detailed_cohort_equivalent_hours']
    assert all_vq.sum()==producer['VQ_and_generator_assumption_qualified_hours']==0
    new_hours=(np.flatnonzero(all_good&~old_good)+1).tolist()
    assert new_hours==producer['new_compact_qualified_on_prior_failed_hours']
    # Current source hashes must still equal the already reviewed core closure.
    core_path=OUT/'compact_core_review.json';core=json.loads(core_path.read_text());paths.append(core_path)
    for dep in core['dependencies']:
        assert rec(ROOT/dep['path'])['sha256']==dep['sha256'],dep['path']
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
                scope='Independent readback of all annual saved arrays, no additional PF or OPF run',
                all_8760_local_2025_clock_positions_checked=True,source_qualified_hours=int(source_q.sum()),
                compact_qualified_hours=int(all_good.sum()),fixed_detailed_cohort_hours=int(old_good.sum()),
                independently_equivalent_detailed_pairs=int(all_equiv.sum()),
                validity_mask='source_qualified & AC_equation_gate & P_profile_preservation_gate & reduction_and_equation_gate & native_retained_bus_count==148',
                timestamp_gamma_source_mask_and_topology_exact=True,all_original_branch_identities_checked=True,
                current_uses_synthetic_baseMVA_and_actual_voltage_without_gamma_lift=True,
                retained_voltages_and_all_eliminated_voltages_independently_checked=True,
                branch_laws_terminal_and_series_currents_KCL_and_loss_identity_checked=True,
                original_load_profiles_six_transfer_P_and_nonreference_bus_PG_checked=True,
                new_compact_qualified_prior_full_NR_failed_hours=new_hours,
                new_compact_hours_have_full_network_KCL_checked=True,
                voltage_Q_generator_assumption_qualified_hours=int(all_vq.sum()),
                PF_equivalence_does_not_establish_operating_feasibility_or_asset_accuracy=True,
                full_network_NR_failure_not_claimed_global_infeasibility=True,
                independent_identity_maximum_errors=errors,independent_identity_tolerances=bounds,
                independently_recomputed_paired_maximum_errors=paired_errors,months=month_rows,
                dependencies=[rec(p) for p in dict.fromkeys(paths)])
    target=OUT/'annual_arrays_independent_review.json';target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['dependencies','months','new_compact_qualified_prior_full_NR_failed_hours']},indent=2))


if __name__=='__main__':main()
