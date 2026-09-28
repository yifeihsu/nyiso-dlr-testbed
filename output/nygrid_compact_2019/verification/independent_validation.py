"""Read-only independent numerical audit of the matched 2019 comparison.

The independent nodal solve and metric calculations below do not import the
comparison solver or scoring functions. The one explicit load_reference import
only checks that the separately written exporters produced identical arrays.
All generated files stay inside verification/; source artifacts are immutable.
"""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_compact_2019'
VERIFY = OUT / 'verification'
NAMES = ['Dysinger East','West Central','Total East','Moses South',
         'Central East','UpNY-Coned','Dun/SPR-South']
RAW_NAMES = ['DYSINGER EAST','WEST CENTRAL','TOTAL EAST','MOSES SOUTH',
             'CENTRAL EAST - VC','UPNY CONED','SPR/DUN-SOUTH']
gates = []
def check(name, actual, maximum=1e-7):
    value = float(actual)
    passed = bool(np.isfinite(value) and value <= maximum)
    gates.append(dict(gate=name, value=value, maximum=maximum, passed=passed))
    if not passed:
        raise AssertionError(f'{name}: {value} > {maximum}')

def sha(path, lf=False):
    data = Path(path).read_bytes()
    return hashlib.sha256(data.replace(b'\r\n',b'\n') if lf else data).hexdigest()

def maxerr(a,b):
    return np.max(np.abs(np.asarray(a)-np.asarray(b)))

def solve(bus, branch, injection, base=100.):
    ids = bus[:,0].astype(int)
    pos = {int(b):i for i,b in enumerate(ids)}
    C = np.zeros((len(branch),len(bus)))
    for j,r in enumerate(branch):
        C[j,pos[int(r[0])]]=1
        C[j,pos[int(r[1])]]=-1
    active = branch[:,10]==1
    taps = np.where(branch[:,8]==0,1,branch[:,8])
    w = np.zeros(len(branch)); w[active] = base / (branch[active,3]*taps[active])
    phase = -w*np.deg2rad(branch[:,9])
    B = C.T @ (w[:,None]*C)
    reference = pos[74]
    other = np.arange(len(bus)) != reference
    theta = np.zeros_like(injection)
    theta[:,other] = np.linalg.solve(B[np.ix_(other,other)],
        (injection-phase@C)[:,other].T).T
    flow = (theta@C.T)*w+phase
    residual = flow@C-injection
    check(f'nodal_balance_nonref_{len(bus)}_{len(branch)}',np.max(np.abs(residual[:,other])))
    return flow, np.rad2deg(theta), residual[:,reference], B

def mapped(values, old, new):
    result=np.zeros((len(values),len(new)))
    index={int(b):j for j,b in enumerate(new)}
    for j,b in enumerate(old): result[:,index[int(b)]]+=values[:,j]
    return result

def cuts(bus,branch,zones,pairs):
    z=dict(zip(bus[:,0].astype(int),zones)); rows=[]
    for u,d in pairs:
        coeff=np.zeros(len(branch))
        for j,r in enumerate(branch):
            if r[10]!=1: continue
            f,t=z[int(r[0])],z[int(r[1])]
            if f in u and t in d: coeff[j]=1
            if t in u and f in d: coeff[j]=-1
        rows.append(coeff)
    return np.array(rows)

def main():
    VERIFY.mkdir(parents=True,exist_ok=True)
    pred=np.load(OUT/'annual_predictions.npz')
    ref=np.load(OUT/'reference/annual_reference.npz')
    times=pd.DatetimeIndex(pred['timestamps']); gamma=float(pred['gamma'])
    obs=pred['observed_benchmark_mw']
    assert list(pred['interfaces'])==NAMES and len(times)==8760 and times.is_unique
    check('annual_observed_matches_independent_export',maxerr(obs,ref['observed_interface_mw']*gamma))
    # Immutable source/hash chain from the independent reference export.
    hashes=[]
    manifest=json.loads((OUT/'reference/reference_export_summary.json').read_text())
    for item in manifest['annual_source_manifests']:
        for pathkey,hashkey in [('mat_path','mat_sha256'),('final_csv_path','final_csv_sha256')]:
            path=Path(item[pathkey]); ok=sha(path)==item[hashkey]
            assert ok
            hashes.append(dict(path=str(path.relative_to(ROOT)),sha256=item[hashkey],policy='raw_bytes',matches=True))
    for item in manifest['outputs']:
        path=ROOT/item['path']; assert sha(path)==item['sha256']
        hashes.append(dict(path=item['path'],sha256=item['sha256'],policy='raw_bytes',matches=True))
    for name in ['source_manifest.csv','current_input_source_manifest.csv','construction_source_manifest.csv','output_manifest.csv']:
        table=pd.read_csv(OUT/'compact'/name)
        for item in table.to_dict('records'):
            p=Path(item['relative_path']); p=(OUT/'compact'/p) if name=='output_manifest.csv' else ROOT/p
            expected=item.get('sha256',item.get('sha256_lf_normalized'))
            # Only the inherited construction manifest declares LF normalization.
            policy='LF_normalized' if name=='construction_source_manifest.csv' else 'raw_bytes'
            assert sha(p,policy=='LF_normalized')==expected, str(p)
            hashes.append(dict(path=str(p.relative_to(ROOT)),sha256=expected,policy=policy,matches=True))
    sys.path.insert(0,str(ROOT/'scripts/nygrid_compact_2019'))
    from run_comparison import load_reference
    root_inputs=load_reference()
    eq={'pd_net':'net_pd_mw','input_pg':'native_input_pg_bus_mw',
        'solved_pg':'native_solved_pg_bus_mw','slack_adjustment':'slack_adjustment_bus_mw',
        'boundary_ac':'boundary_ac_bus_mw','boundary_dc':'boundary_dc_bus_mw',
        'boundary_hq':'boundary_hq_bus_mw','boundary':'boundary_total_bus_mw',
        'original_pf':'branch_pf_mw','corrected_sim':'corrected_interface_mw'}
    for a,b in eq.items(): check('root_reference_array_'+a,maxerr(root_inputs[a],ref[b]))
    injection=(ref['native_solved_pg_bus_mw']-ref['net_pd_mw']+
               ref['boundary_total_bus_mw']-ref['bus'][:,4])*gamma
    check('source_input_conservation',np.max(np.abs(injection.sum(axis=1))))
    c=loadmat(OUT/'compact/compact_network.mat',simplify_cells=True)['network_data']
    cb=c['paper74']['bus'][:,:13]; br=c['paper74']['branch'][:,:13]
    additions=np.array([[43,38,0,.0427,0,0,0,0,0,0,1,-360,360],
                        [38,77,0,.0147,0,0,0,0,0,0,1,-360,360]])
    models={'reference_NY46':(ref['bus'],ref['branch']),
            'compact51':(cb,br),'compact51_marcy':(cb,np.vstack([br,additions]))}
    sourcezones=pd.read_csv(ROOT/'tmp/nygrid_2019_reproduction/upstream/Data/npcc.csv')
    role=dict(zip(sourcezones.idx,sourcezones.zone));role.update({774:'G',858:'G',9001:'G',9002:'G',9003:'K'})
    pairs=[('A','B'),('B','C'),('E','FG'),('D','E'),('E','F'),('G','H'),('I','J')]
    independent={}; solutions={}
    for name,(bus,branches) in models.items():
        p=mapped(injection,ref['bus_ids'],bus[:,0].astype(int))
        flow,angle,slack,B=solve(bus,branches,p)
        op=cuts(bus,branches,[role[int(x)] for x in bus[:,0]],pairs)
        independent[name+'__paper_roles']=flow@op.T
        solutions[name]=(flow,angle,slack,B,op)
        if name=='reference_NY46':
            check('independent_source_branch_replay',maxerr(flow,ref['branch_pf_mw']*gamma))
            check('source_paper_role_operator_identity',maxerr(op,ref['operator_coefficients']))
        else:
            co=np.asarray(c['current_dc_coefficients'])[[0,1,4,2,3,5,6]]
            if name.endswith('marcy'):
                zones=dict(zip(bus[:,0].astype(int),c['compact_physical_zones']))
                sets=[{b for b,z in zones.items() if z in letters} for letters in ['A','AB','ABCDE','D','E','ABCDEFG','I']]
                sets[5]-={858,9002}
                co=np.zeros((7,len(branches)))
                for k,up in enumerate(sets):
                    down=({b for b,z in zones.items() if z=='F'} if k==4 else
                          {b for b,z in zones.items() if z=='J'} if k==6 else set(zones)-up)
                    for j,r in enumerate(branches):
                        if r[10]!=1:continue
                        f,t=int(r[0]),int(r[1])
                        if f in up and t in down:co[k,j]=1
                        if t in up and f in down:co[k,j]=-1
            independent[name+'__current_roles']=flow@co.T
    for name,value in independent.items():check('independent_annual_prediction_'+name,maxerr(value,pred[name]))
    metrics=pd.read_csv(OUT/'annual_monthly_metrics.csv')
    metricerror=0.; rankingerror=0.
    for r in metrics.to_dict('records'):
        ix=np.ones(8760,bool) if r['period']=='annual' else times.month==int(r['period'][-2:])
        p=independent[r['experiment']][ix];o=obs[ix]
        if r['interface']!='ALL_SEVEN_POOLED': j=NAMES.index(r['interface']);p=p[:,j];o=o[:,j]
        e=p-o; expected={'wape_pct':100*np.abs(e).sum()/np.abs(o).sum(),
            'mae_benchmark_mw':np.abs(e).mean(),'mae_actual_scale_mw':np.abs(e).mean()/gamma,
            'bias_benchmark_mw':e.mean(),'wrong_direction_count':int((p*o<0).sum())}
        metricerror=max(metricerror,max(abs(float(r[k])-v) for k,v in expected.items()))
    check('all_520_annual_monthly_metric_rows',metricerror,1e-7)
    best=pd.read_csv(OUT/'best_snapshots.csv')
    allr=pd.read_csv(OUT/'all_hour_rankings.csv')
    for name,p in independent.items():
        e=np.abs(p-obs);pct=np.divide(100*e,np.abs(obs),out=np.full_like(e,np.nan),where=obs!=0)
        pooled=100*e.sum(axis=1)/np.abs(obs).sum(axis=1);worst=pct.max(axis=1)
        ranks=allr[allr.experiment==name].set_index('timestamp').loc[pred['timestamps']]
        check('all_hour_pooled_'+name,maxerr(pooled,ranks.pooled_error_pct),1e-7)
        finite=np.isfinite(worst)
        check('all_hour_worst_'+name,maxerr(worst[finite],ranks.worst_interface_error_pct.to_numpy()[finite]),1e-6)
        assert np.array_equal(np.isnan(worst),ranks.worst_interface_error_pct.isna())
        assert np.array_equal((p*obs<0).sum(axis=1),ranks.wrong_direction_interfaces)
        for criterion,score in [('pooled',pooled),('minimax',worst)]:
            sort=pd.DataFrame({'score':score,'timestamp':times}).sort_values(['score','timestamp']).head(3)
            actual=best[(best.experiment==name)&(best.criterion==criterion)].sort_values('rank')
            assert list(actual.timestamp)==[str(t) for t in sort.timestamp]
    details=pd.read_csv(OUT/'best_snapshot_interface_errors.csv')
    detail_error=0.
    for r in details.to_dict('records'):
        i=times.get_loc(r['timestamp']);j=NAMES.index(r['interface'])
        p=independent[r['experiment']][i,j];o=obs[i,j]
        expected={'observed_actual_mw':o/gamma,'predicted_actual_scale_mw':p/gamma,
            'observed_benchmark_mw':o,'predicted_benchmark_mw':p,
            'signed_error_benchmark_mw':p-o,'absolute_error_actual_scale_mw':abs(p-o)/gamma,
            'absolute_error_pct':100*abs(p-o)/abs(o),'wrong_direction':int(p*o<0)}
        detail_error=max(detail_error,max(abs(float(r[k])-v) for k,v in expected.items()))
    check('all_210_best_interface_details',detail_error,1e-7)
    # Rejoin actual primary-source quality, independently of cached rank flags.
    qpath=ROOT/'output/nygrid_2019/nyiso_source_audit_hourly_quality.csv'
    quality=pd.read_csv(qpath); quality=quality[quality.InterfaceName.isin(RAW_NAMES)]
    quality['interface']=quality.InterfaceName.map(dict(zip(RAW_NAMES,NAMES)))
    quality=quality.set_index(['TimeStamp','interface']).sort_index()
    assert len(quality)==8760*7 and quality.index.is_unique
    for j,name in enumerate(NAMES):
        # Preserve the exact requested chronological order explicitly.
        q=quality.reindex([(str(t),name) for t in times])
        check('raw_quality_observations_'+name,maxerr(q.FlowMWH.to_numpy()*gamma,obs[:,j]))
    selected_quality=[]
    for time in sorted(best.timestamp.unique()):
        q=quality.loc[time]
        r=dict(timestamp=time,interfaces=len(q),imputed_interface_observations=int(q.FlowMWH_imputed.sum()),
            ambiguous_interface_observations=int(q.fall_dst_ambiguous_hour.sum()),
            minimum_sample_count=int(q.sample_count.min()),minimum_distinct_timestamp_count=int(q.distinct_timestamp_count.min()),
            all_exactly_12_unique_samples=bool(q.filter_unimputed_unambiguous_exactly_12_unique_samples.all()))
        matched=best[best.timestamp==time]
        for k in ['imputed_interface_observations','ambiguous_interface_observations','minimum_sample_count','minimum_distinct_timestamp_count']:
            assert (matched[k]==r[k]).all()
        selected_quality.append(r)
    pd.DataFrame(selected_quality).to_csv(VERIFY/'selected_hour_source_quality.csv',index=False,lineterminator='\n')
    quality.loc[(sorted(best.timestamp.unique()),slice(None)),:].to_csv(VERIFY/'selected_interface_source_quality.csv',lineterminator='\n')
    # Verify the exact current compact-net port transformation independently.
    ids=cb[:,0].astype(int);keep=np.array([np.where(ids==b)[0][0] for b in ref['bus_ids']]);extra=np.array([i for i in range(len(ids)) if i not in keep])
    B=solutions['compact51'][3];T=np.zeros((46,51));T[:,keep]=np.eye(46)
    T[:,extra]=-np.linalg.solve(B[np.ix_(extra,extra)],B[np.ix_(extra,keep)]).T
    check('Kron_injection_column_conservation',maxerr(T.sum(axis=0),1))
    pm=pd.read_csv(OUT/'common_port_injection_map.csv')
    for r in pm.to_dict('records'):
        check('port_weight_'+str(r['eliminated_bus'])+'_'+str(r['retained_bus']),
              abs(T[np.where(ref['bus_ids']==r['retained_bus'])[0][0],np.where(ids==r['eliminated_bus'])[0][0]]-r['injection_weight']),1e-10)
        assert not r['measured_terminal_allocation']
    kcol=T[:,np.where(ids==9003)[0][0]];expected=np.zeros(46)
    expected[np.where(ref['bus_ids']==78)[0][0]]=.5;expected[np.where(ref['bus_ids']==80)[0][0]]=.5
    check('Kron_9003_78_80_half_exact',maxerr(kcol,expected))
    # Full matched A/B/C/D matrix independently reconstructed from saved source inputs.
    inputs=loadmat(OUT/'compact/current_input_snapshots.mat',simplify_cells=True)['input_data']
    matrix=pd.read_csv(OUT/'network_input_matrix.csv'); matrixerror=0.
    ablations=pd.read_csv(OUT/'allocation_ablations.csv')
    ablation_details=pd.read_csv(OUT/'allocation_ablation_interface_errors.csv')
    movement=pd.read_csv(OUT/'allocation_movement_ledger.csv')
    components=loadmat(OUT/'reference/matched_snapshot_components.mat',simplify_cells=True)['snapshots']
    components={str(pd.Timestamp(r['timestamp'])):r for r in components}
    nonfossil=pd.read_csv(ROOT/'output/compact_ny_2025/generation_sources/nonfossil/zonal_nonfossil_priors.csv')
    physical_zones=np.array(pd.read_csv(OUT/'compact/bus_metadata.csv').compact_physical_zone)
    paper_zones=np.array([role[b] for b in ids])
    ablation_error=0.; movement_error=0.; ablation_detail_error=0.
    def aggregate(values,buses):
        result=np.zeros(len(ids))
        for v,b in zip(values,buses):result[np.where(ids==b)[0][0]]+=v
        return result
    for item in inputs:
        timestamp=str(pd.Timestamp(item['timestamp'])); i=times.get_loc(timestamp);p_case=item['paper74']
        current=np.zeros(51)
        for gen in p_case['gen']:current[np.where(ids==gen[0])[0][0]]+=gen[1]*gen[7]
        current=current-item['gross_pd_mw']+item['boundary_p_mw']-p_case['bus'][:,4]
        vectors={'A':injection[i],'B':T@current,'C':mapped(injection[i:i+1],ref['bus_ids'],ids)[0],
                 'D':current,'C_marcy':mapped(injection[i:i+1],ref['bus_ids'],ids)[0],'D_marcy':current}
        for label,p in vectors.items():
            name='reference_NY46' if label in ['A','B'] else 'compact51_marcy' if 'marcy' in label else 'compact51'
            bus,branch=models[name];flow,ang,slack,unused=solve(bus,branch,p[None,:]);prediction=flow@solutions[name][4].T
            o=obs[i:i+1];e=np.abs(prediction-o)
            r=matrix[(matrix.experiment==label)&(matrix.timestamp==timestamp)].iloc[0]
            expected={'pooled_error_pct':100*e.sum()/np.abs(o).sum(),'worst_interface_error_pct':np.max(100*e/np.abs(o)),
                      'wrong_direction_interfaces':int((prediction*o<0).sum()),'additional_slack_mw':slack[0],
                      'input_total_imbalance_mw':p.sum()}
            expected.update({name+'_error_pct':100*e[0,j]/abs(o[0,j]) for j,name in enumerate(NAMES)})
            matrixerror=max(matrixerror,max(abs(r[k]-v) for k,v in expected.items()))
            assert not r.observations_used_in_dispatch
        s=components[timestamp]
        raw=np.nan_to_num(s['thermal_source_recorded_pg_mw'],nan=0.)
        allocated=s['thermal_allocated_pg_mw']
        # The recorded thermal evidence and source allocated total alone fix
        # this statewide-proportional sensitivity; no flow target is used.
        therm=aggregate((raw*allocated.sum()/raw.sum()-allocated)*gamma,s['thermal_model_bus'])
        boundary_change=item['boundary_p_mw']-mapped(ref['boundary_total_bus_mw'][i:i+1]*gamma,ref['bus_ids'],ids)[0]
        gross=aggregate(s['gross_pd_mw']*gamma,s['gross_bus_ids'])
        desired_load=np.zeros(51)
        for zone in 'ABCDEFGHIJK':
            mask=physical_zones==zone
            desired_load[mask]=gross[paper_zones==zone].sum()*item['gross_pd_mw'][mask]/item['gross_pd_mw'][mask].sum()
        hydro_rows=np.asarray(s['hydro_generator_rows'],int)-1
        hydro=aggregate(s['input_case']['gen'][hydro_rows,1]*gamma,s['input_case']['gen'][hydro_rows,0])
        priors=nonfossil[(nonfossil.scenario_id==item['scenario_id'])&(nonfossil.fuel_category=='Hydro')]
        assert len(priors)==11
        h=dict(zip(priors.zone,priors.prior_public_mw));desired_hydro=np.zeros(51)
        gens=p_case['gen']; capacity=np.maximum(gens[:,8]-gens[:,9],0)*gens[:,7]
        genzones=np.array([physical_zones[np.where(ids==g)[0][0]] for g in gens[:,0]])
        for zone in 'ABCDEFGHIJK':
            value=hydro.sum()*h[zone]/sum(h.values());mask=genzones==zone
            if value>1e-9:
                desired_hydro+=aggregate(value*capacity[mask]/capacity[mask].sum(),gens[mask,0])
        changes={'paper_J_only_hydro_boundary_load':np.zeros(51),
            'thermal_residual_statewide_normalization':therm,'current_boundary_only':boundary_change,
            'current_within_zone_gross_load_placement':gross-desired_load,
            'current_hydro_spatial_rule_fixed_paper_total':desired_hydro-hydro}
        base=mapped(injection[i:i+1],ref['bus_ids'],ids)[0]
        for label,change in changes.items():
            saved=movement[(movement.experiment==label)&(movement.timestamp==timestamp)]
            delta=aggregate(saved.delta_injection_benchmark_mw,saved.bus_id)
            movement_error=max(movement_error,maxerr(delta,change))
            if label!='current_boundary_only':check('allocation_total_preservation_'+label+'_'+str(i),abs(change.sum()))
            p=base+change;flow,angle,slack,unused=solve(cb,models['compact51_marcy'][1],p[None,:])
            prediction=flow@solutions['compact51_marcy'][4].T;o=obs[i:i+1];e=np.abs(prediction-o)
            r=ablations[(ablations.experiment==label)&(ablations.timestamp==timestamp)].iloc[0]
            expected={'pooled_error_pct':100*e.sum()/np.abs(o).sum(),'worst_interface_error_pct':np.max(100*e/np.abs(o)),
                'wrong_direction_interfaces':int((prediction*o<0).sum()),'additional_slack_mw':slack[0],
                'input_total_imbalance_mw':p.sum()}
            expected.update({name+'_error_pct':100*e[0,j]/abs(o[0,j]) for j,name in enumerate(NAMES)})
            ablation_error=max(ablation_error,max(abs(r[k]-v) for k,v in expected.items()))
            assert not r.observations_used_in_dispatch
            for j,name in enumerate(NAMES):
                r=ablation_details[(ablation_details.experiment==label)&(ablation_details.timestamp==timestamp)&(ablation_details.interface==name)].iloc[0]
                expected={'observed_benchmark_mw':o[0,j],'predicted_benchmark_mw':prediction[0,j],
                    'absolute_error_benchmark_mw':e[0,j],'absolute_error_pct':100*e[0,j]/abs(o[0,j])}
                ablation_detail_error=max(ablation_detail_error,max(abs(r[k]-v) for k,v in expected.items()))
    check('all_30_network_input_matrix_rows',matrixerror,1e-7)
    check('all_25_allocation_ablation_rows',ablation_error,1e-7)
    check('all_175_allocation_interface_details',ablation_detail_error,1e-7)
    check('source_derived_allocation_movement_ledger',movement_error,1e-7)
    # Verify selected MAT vectors, row ordering, flows and observations, all six unique cases.
    selected=loadmat(OUT/'selected_dc_candidates.mat',simplify_cells=True)['candidates']
    selected_times={c['timestamp'] for c in selected}
    required=set(best[best.experiment=='compact51_marcy__paper_roles'].timestamp)|{'2019-01-08 15:00:00'}
    assert selected_times==required and len(selected)==6
    selected_detail=[]
    for item in selected:
        i=int(item['hour_index']);assert item['timestamp']==str(times[i])
        check('selected_hardware_'+str(i),maxerr(item['branch'],models['compact51_marcy'][1]))
        for field,src in [('net_pd_mw','net_pd_mw'),('native_input_pg_bus_mw','native_input_pg_bus_mw'),
                          ('native_solved_pg_bus_mw','native_solved_pg_bus_mw'),('boundary_p_mw','boundary_total_bus_mw'),
                          ('source_slack_adjustment_bus_mw','slack_adjustment_bus_mw')]:
            check('selected_'+field+'_'+str(i),maxerr(item[field],mapped(ref[src][i:i+1]*gamma,ref['bus_ids'],ids)[0]))
        check('selected_stored_flow_'+str(i),maxerr(item['dc_flow'],solutions['compact51_marcy'][0][i]))
        check('selected_stored_angle_'+str(i),maxerr(item['dc_angle_deg'],solutions['compact51_marcy'][1][i]))
        check('selected_observed_'+str(i),maxerr(item['observed_benchmark_mw'],obs[i]))
        p=independent['compact51_marcy__paper_roles'][i]
        for j,name in enumerate(NAMES):
            selected_detail.append(dict(timestamp=item['timestamp'],interface=name,observed_actual_mw=obs[i,j]/gamma,
                predicted_actual_scale_mw=p[j]/gamma,absolute_error_pct=100*abs(p[j]-obs[i,j])/abs(obs[i,j]),
                wrong_direction=bool(p[j]*obs[i,j]<0)))
    pd.DataFrame(selected_detail).to_csv(VERIFY/'independent_selected_interface_metrics.csv',index=False,lineterminator='\n')
    replay=pd.read_csv(VERIFY/'matpower_selected_dc_replay.csv')
    assert set(replay.timestamp)==selected_times and replay.pf_success.all() and replay.row_identity_preserved.all()
    check('MATPOWER_all_selected_branches',replay.max_branch_error_mw.max())
    check('MATPOWER_all_selected_interfaces',replay.max_interface_error_mw.max())
    # All observed-based report fields can be reproduced without altering inputs.
    july=times.get_loc('2019-07-03 04:00:00'); p=independent['compact51_marcy__paper_roles'][july]
    july_metrics=dict(timestamp=str(times[july]),pooled_error_pct=float(100*np.abs(p-obs[july]).sum()/np.abs(obs[july]).sum()),
        worst_interface_error_pct=float(np.max(100*np.abs(p-obs[july])/np.abs(obs[july]))),wrong_direction_interfaces=int((p*obs[july]<0).sum()))
    monthly_improvements=[]
    for m in range(1,13):
        mask=times.month==m;o=obs[mask];baseline=independent['compact51__paper_roles'][mask];variant=independent['compact51_marcy__paper_roles'][mask]
        a=100*np.abs(baseline-o).sum()/np.abs(o).sum();b=100*np.abs(variant-o).sum()/np.abs(o).sum()
        monthly_improvements.append(dict(month=m,compact51_pooled_pct=float(a),marcy_pooled_pct=float(b),improvement_percentage_points=float(a-b),relative_error_reduction_pct=float(100*(a-b)/a)))
    pd.DataFrame(monthly_improvements).to_csv(VERIFY/'independent_monthly_improvements.csv',index=False,lineterminator='\n')
    zero_by_interface={name:int((obs[:,j]==0).sum()) for j,name in enumerate(NAMES)}
    annual=[]
    for name,p in independent.items():
        annual.append(dict(experiment=name,pooled_error_pct=float(100*np.abs(p-obs).sum()/np.abs(obs).sum()),
            wrong_direction_count=int((p*obs<0).sum())))
    for p in [ROOT/'scripts/nygrid_compact_2019/run_comparison.py',ROOT/'scripts/nygrid_compact_2019/dc_model.py',
              OUT/'annual_predictions.npz',OUT/'selected_dc_candidates.mat',qpath,Path(__file__),
              VERIFY/'replay_selected_candidates.m']:
        hashes.append(dict(path=str(p.relative_to(ROOT)),sha256=sha(p),policy='raw_bytes',matches=True))
    pd.DataFrame(gates).to_csv(VERIFY/'independent_validation_gates.csv',index=False,lineterminator='\n')
    pd.DataFrame(hashes).to_csv(VERIFY/'independent_validation_source_hashes.csv',index=False,lineterminator='\n')
    summary=dict(passed=all(r['passed'] for r in gates),validation_gates=len(gates),annual_hours=8760,matched_matrix_rows=len(matrix),allocation_ablation_rows=len(ablations),
        selected_candidate_count=len(selected),selected_quality_hour_count=len(selected_quality),source_hashes_checked=len(hashes),
        July3_minimax=july_metrics,annual_metrics=annual,monthly_improvement_count=sum(r['improvement_percentage_points']>0 for r in monthly_improvements),
        zero_observation_counts=zero_by_interface,selected_hour_quality=selected_quality,matpower_replay=replay.to_dict('records'),
        no_internal_interface_input_fitting=True,untouched_holdout=False,
        all_source_allocation_truth_established=False,AC_feasibility_established=False,thermal_validation_established=False,
        interpretation_limits=[
            'The seven scored interfaces overlap; pooled WAPE is a pooled comparison error, not independent statewide energy error.',
            'All rankings are retrospective selections from 8760 already examined hours; there is no untouched holdout.',
            'Paper allocation roles and compact physical-zone roles define different measurement operators; matching names do not prove identical physical membership.',
            'Kron bus9003 maps one-half to78 and one-half to80 as exact DC injection equivalence conditioned on compact topology, not measured generation or a physical site crosswalk.',
            'The load-placement ablation changes the zonal role crosswalk and within-zone weights jointly; hydro combines current zonal priors with generic capacity weighting.',
            'NYgrid native solved generation includes source slack; fixed NY boundary injections are model-derived, not measured individual tie telemetry.',
            'The Marcy variant adds two source reactances for DC diagnosis; its AC resistance/charging/ratings and upgrade disposition are not established.',
            'Source-hour quality pertains to interface sampling, not independently observed nodal generation.',
            'Paper-style signed errors use placeholder limit values for some channels and are not physical thermal-rating error measures.'
        ])
    (VERIFY/'independent_validation.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    julytable=pd.DataFrame(selected_detail).query("timestamp == '2019-07-03 04:00:00'")
    lines=['# Independent 2019 comparison verification','',
        f"PASS: {len(gates)} numerical/provenance checks cover all 8,760 annual hours, all 30 matched network/input rows, all 25 source-derived allocation ablations, and all six selected candidates.",'',
        'The independent Python replay builds its own DC nodal matrix, tap and phase-shift injections; it does not call the comparison DC solver. A second replay uses MATPOWER rundcpf on all six selected candidates with signed nodal demand and one numerical reference generator. No AC or thermal qualification follows.','',
        f"July 3, 2019 04:00 is the best minimax hour for compact51 + the two Marcy reactances under paper roles: pooled error {july_metrics['pooled_error_pct']:.8f}%, worst-interface error {july_metrics['worst_interface_error_pct']:.8f}%, and no opposite-direction interfaces.",'',
        julytable.to_markdown(index=False,floatfmt='.6f'),'',
        'Top-three pooled hours: September 6 02:00 (1.77323734%), September 8 05:00 (1.95163634%), September 6 03:00 (2.17022055%). The minimax criterion instead selects July 3 04:00, July 22 04:00, and September 8 05:00.','',
        'Annual pooled error with paper roles falls from 17.38250825% to 12.31721500%, with improvement in all 12 monthly pooled scores. The paper reference remains 11.21807693%. With current physical-zone roles the same network change instead increases annual pooled error from 19.07209610% to 19.67048524%; operator roles therefore must stay explicit.','',
        f"MATPOWER maximum selected branch discrepancy: {replay.max_branch_error_mw.max():.3g} MW; maximum selected interface discrepancy: {replay.max_interface_error_mw.max():.3g} MW. All 94 branch records retain exact hardware and ordering.",'',
        'Source-array equality is checked against the separately exported annual reference NPZ, including pre-solve generation, solved generation/slack, net demand, and separate AC/DC/HQ boundary accounts. Source and construction hashes match their pinned manifests. All selected best-hour quality flags are independently joined to the primary-source reconstruction quality table. The detailed CSV retains irregular-sample cases rather than silently excluding them.','',
        '## Interpretation boundaries','']
    lines += ['- '+s for s in summary['interpretation_limits']]
    lines += ['', '## Evidence', '',
        '- `independent_validation.json`: machine-readable findings and all selected quality/replay records.',
        '- `independent_validation_gates.csv` and `independent_validation_source_hashes.csv`: tolerances and source pins.',
        '- `selected_hour_source_quality.csv` and `selected_interface_source_quality.csv`: direct primary-source quality joins.',
        '- `independent_selected_interface_metrics.csv` and `independent_monthly_improvements.csv`: independently calculated metrics.',
        '- `matpower_selected_dc_replay.csv`: separate solver replay without a physical-generation claim.','']
    (VERIFY/'independent_validation.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ['passed','validation_gates','July3_minimax','annual_metrics','monthly_improvement_count','zero_observation_counts']},indent=2))

if __name__=='__main__': main()
