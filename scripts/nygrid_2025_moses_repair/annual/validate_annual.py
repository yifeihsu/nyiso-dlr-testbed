"""Independently validate saved replay axes, profiles, bounds and accounting.

Raw branch laws and passive-network recovery receive a second, separate audit
under moses_repair/validation. No PF or producer function is called here.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'output/nygrid_2025_moses_repair/annual'


def record(path):
    path=Path(path)
    with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    try:name=path.relative_to(ROOT).as_posix()
    except ValueError:name=str(path)
    return {'path':name,'sha256':digest,'bytes':path.stat().st_size}


def vec(data,key,dtype=float):return np.asarray(data[key],dtype=dtype).reshape(-1)
def mx(x):
    a=np.asarray(x);assert np.isfinite(a).all()
    return float(np.max(np.abs(a),initial=0.))
def sequence(x):return [x] if isinstance(x,dict) else list(x)
def violation(x,lower,upper):return np.maximum(0,np.maximum(lower-x,x-upper)).max(axis=1)


def main(run_dir,partial=False):
    run_dir=run_dir.resolve();out=run_dir/'validation';out.mkdir(exist_ok=True)
    axes_path=run_dir/'annual_axes.mat';net_path=run_dir/'annual_network.mat'
    axes=loadmat(axes_path,simplify_cells=True);templates=loadmat(net_path,simplify_cells=True)['templates']
    capture_path=run_dir/('annual_progress.json' if partial else 'annual_receipt.json')
    producer=json.loads(capture_path.read_text());count=int(producer['months_complete'])
    assert count>0 and (partial or (count==12 and producer['completed']))
    source_records=sequence(axes['source_records'])
    for entry in source_records:assert record(Path(entry['path']))['sha256']==entry['sha256'],entry['path']
    baseline_path=ROOT/'output/nygrid_2025_physical_repair/annual/physical_repair_v1/comparison/comparison_arrays.npz'
    old=np.load(baseline_path,allow_pickle=False)
    snapshot=BASE/'candidate_bundle/model';model_path=snapshot/'latest_model.mat'
    model=loadmat(model_path,simplify_cells=True)['model']
    profiles={};profile_paths=[]
    for name in ['profiles_h0001_4380.mat','profiles_h4381_8760.mat']:
        p=snapshot/name;profile_paths.append(p);d=loadmat(p,simplify_cells=True)['profiles']
        for key,value in d.items():profiles.setdefault(key,[]).append(value)
    profiles={k:np.concatenate(v) for k,v in profiles.items()}
    old_model_path=BASE/'baseline_bundle/model/latest_model.mat'
    old_model=loadmat(old_model_path,simplify_cells=True)['model']
    old_profiles={}
    for name in ['profiles_h0001_4380.mat','profiles_h4381_8760.mat']:
        part=loadmat(BASE/'baseline_bundle/model'/name,simplify_cells=True)['profiles']
        for key in ['generator_PG_MW','bus_PD_MW','bus_QD_MVAr','fixed_transfer_PF_MW','dover_bank_phase_shift_deg']:
            old_profiles.setdefault(key,[]).append(part[key])
    old_profiles={k:np.concatenate(v) for k,v in old_profiles.items()}
    generation_path=ROOT/'output/nygrid_2025_moses_repair/generation/generation_candidate.mat'
    generation=loadmat(generation_path,simplify_cells=True,variable_names=['hydro_rows_1based'])
    hydro=vec(generation,'hydro_rows_1based',int)-1;old_ng=len(old_model['generator_bus_ids']);old_hydro=hydro[hydro<old_ng]
    old_native=~np.asarray(old_model['external']['generator_mask'],bool)
    old_nonhydro=old_native.copy();old_nonhydro[old_hydro]=False
    times=vec(axes,'timestamp_utc',str);hours=vec(axes,'hour_index',int);source=vec(axes,'source_qualified',bool)
    states=vec(axes,'topology_state_index',int);oldgood=vec(axes,'current_baseline_qualified',bool);gamma=float(axes['gamma'])
    assert np.array_equal(hours,np.arange(1,8761)) and np.array_equal(times,old['timestamp_utc'])
    assert np.array_equal(source,old['source_qualified']) and np.array_equal(oldgood,old['candidate_qualified'])
    assert np.array_equal(source,np.asarray(model['axis']['source_qualified'],bool))
    assert np.array_equal(states,model['axis']['state_index']) and source.sum()==8651 and oldgood.sum()==8651
    assert gamma==float(old['gamma'])==float(model['scale_factor_gamma'])
    months=pd.DatetimeIndex(pd.to_datetime(times,utc=True)).tz_convert('America/New_York').month.to_numpy()
    assert np.array_equal(months,vec(axes,'model_month',int))
    ids=vec(axes,'bus_id',int);keys=vec(axes,'branch_keys',str);genbus=vec(axes,'generator_bus_id',int)
    assert np.array_equal(genbus,model['generator_bus_ids'])
    bilook={x:i for i,x in enumerate(ids)};keylook={x:i for i,x in enumerate(keys)}
    ext=np.asarray(model['external']['generator_mask'],bool);native=~ext;extrows=np.flatnonzero(ext)
    assert np.array_equal(extrows+1,vec(axes,'external_generator_rows_1based',int))
    scap_external=np.asarray(model['external']['capability_proxy_MW'])/.95
    boundary=vec(model['boundary_injections'],'generator_rows',int)-1
    boundary_groups=vec(model['boundary_injections'],'external_groups',int)
    assert np.all(ext[boundary]) and np.all(np.asarray(model['boundary_injections']['fixed_Q_MVAr'])==0)
    assert np.array_equal(boundary+1,vec(axes,'boundary_generator_rows_1based',int))
    tolerances={'finite_capability_metadata_MW_MVAr':1e-8,'native_HQ_PG_MW':1e-7,'fixed_transfer_MW':1e-8,
        'loss_budget_MW':1e-5,'zonal_load_closure_MW':1e-5,'served_PD_QD_shape':1e-7,
        'external_loss_increment_MW':1e-5,'regional_import_MW':1e-5,'bus_generation_aggregation':1e-7,
        'reported_bound_violation_difference':1e-7,'current_from_power_A':1e-5,'phase_control_deg':1e-10,
        'fixed_boundary_PQ_MW_MVAr':1e-7,'baseline_fixed_input_preservation_MW':1e-7,
        'baseline_regional_import_target_MW':1e-7}
    maxima={key:0. for key in tolerances};seen=np.zeros(8760,bool);goodall=seen.copy();physicalall=seen.copy();fullall=seen.copy()
    failures=[];monthly=[];physical_rows=[];paths=[axes_path,net_path,baseline_path,model_path,old_model_path,generation_path,*profile_paths]
    for mon in range(1,count+1):
        path=run_dir/'monthly'/f'profile_PF_2025_{mon:02d}.mat';receipt_path=path.with_name(path.stem+'_receipt.json')
        receipt=json.loads(receipt_path.read_text());assert receipt['completed'] and receipt['month']==mon
        for item in receipt['outputs']:assert record(Path(item['path']))['sha256']==item['sha256']
        paths += [path,receipt_path]
        d=loadmat(path,simplify_cells=True);ix=vec(d,'hour_index',int)-1
        assert np.array_equal(ix,np.flatnonzero(months==mon)) and not seen[ix].any();seen[ix]=True
        assert np.array_equal(vec(d,'timestamp_utc',str),times[ix]) and float(d['gamma'])==gamma
        assert np.array_equal(vec(d,'source_qualified',bool),source[ix])
        assert np.array_equal(vec(d,'current_baseline_qualified',bool),oldgood[ix])
        assert np.array_equal(vec(d,'PF_attempted',bool),source[ix])
        for key,expected in [('bus_id',ids),('branch_keys',keys),('generator_bus_id',genbus)]:
            assert np.array_equal(vec(d,key,str if key=='branch_keys' else int),expected)
        exception=vec(d,'solver_exception',bool);good=source[ix]&~exception
        for flag in ['PF_converged','AC_equation_gate','loss_allocation_gate','reduction_and_equation_gate']:good&=vec(d,flag,bool)
        assert np.array_equal(good,vec(d,'qualified',bool)) and np.array_equal(good,vec(d,'computed_current_available',bool))
        assert not np.any(exception&~source[ix]);goodall[ix]=good
        assert np.isnan(d['VM'][~source[ix]]).all() and np.isnan(d['gen_PG'][~source[ix]]).all()
        for j in np.flatnonzero(source[ix]&~good):
            failures.append({'hour_index':int(ix[j]+1),'timestamp_utc':times[ix[j]],'status':str(vec(d,'loss_status',str)[j]),
                'solver_exception':bool(exception[j]),'baseline_current_qualified':bool(oldgood[ix[j]]),'valid_prediction':False})
        for state in np.unique(states[ix]):
            template=templates[int(state)-1];bus=template['bus'];br=template['branch'];pol=template['policy'];groups=np.asarray(pol['bus_group'],int)
            b=np.array([bilook[int(x)] for x in bus[:,0]]);l=np.array([keylook[str(x)] for x in np.asarray(template['branch_keys']).reshape(-1)])
            rows=np.flatnonzero(good&(states[ix]==state));hh=ix[rows]
            if not len(rows):continue
            pg=d['gen_PG'][rows];qg=d['gen_QG'][rows];pd0=profiles['bus_PD_MW'][hh];qd0=profiles['bus_QD_MVAr'][hh]
            assert np.isfinite(pg).all() and np.isfinite(qg).all()
            pg0=profiles['generator_PG_MW'][hh];lo=profiles['generator_Pmin_MW'][hh].copy();hi=profiles['generator_Pmax_MW'][hh].copy()
            oldpg=old_profiles['generator_PG_MW'][hh]
            maxima['baseline_fixed_input_preservation_MW']=max(maxima['baseline_fixed_input_preservation_MW'],
                mx(pg0[:,native].sum(axis=1)-oldpg[:,old_native].sum(axis=1)),
                mx(pg0[:,hydro].sum(axis=1)-oldpg[:,old_hydro].sum(axis=1)),
                mx(pg0[:,:old_ng][:,old_nonhydro]-oldpg[:,old_nonhydro]),
                mx(pd0-old_profiles['bus_PD_MW'][hh]),mx(qd0-old_profiles['bus_QD_MVAr'][hh]),
                mx(profiles['fixed_transfer_PF_MW'][hh,:old_profiles['fixed_transfer_PF_MW'].shape[1]]-old_profiles['fixed_transfer_PF_MW'][hh]))
            lo[:,ext]=pg0[:,ext];hi[:,ext]=pg0[:,ext]
            original_status=(hi>0)|(lo<0)
            gcap=np.maximum(abs(hi),abs(lo));scap=gcap/.95;scap[:,ext]=scap_external
            scap[:,boundary]=abs(pg0[:,boundary])
            qcap=gcap*np.tan(np.arccos(.95));qcap[~original_status]=0
            qcap[:,ext]=np.sqrt(np.maximum(0,scap[:,ext]**2-pg[:,ext]**2))
            qcap[:,boundary]=0
            saved_static=model['loss_static'][int(state)-1];finite=vec(saved_static,'finite_external_generator_rows',int)-1
            assert not np.isin(boundary,finite).any()
            lo[:,finite]=vec(saved_static,'finite_external_Pmin_MW');hi[:,finite]=vec(saved_static,'finite_external_Pmax_MW')
            for field,expected in [('gen_Pmin',lo),('gen_Pmax',hi),('gen_Qmin',-qcap),('gen_Qmax',qcap),('gen_S_cap',scap)]:
                maxima['finite_capability_metadata_MW_MVAr']=max(maxima['finite_capability_metadata_MW_MVAr'],mx(d[field][rows]-expected))
            assert np.array_equal(d['gen_status'][rows].astype(bool),original_status)
            hq=int(pol['HQ'])-1
            maxima['native_HQ_PG_MW']=max(maxima['native_HQ_PG_MW'],mx(pg[:,native]-pg0[:,native]),mx(pg[:,hq]-pg0[:,hq]))
            maxima['fixed_boundary_PQ_MW_MVAr']=max(maxima['fixed_boundary_PQ_MW_MVAr'],mx(pg[:,boundary]-pg0[:,boundary]),mx(qg[:,boundary]))
            assert np.array_equal(vec(pol,'boundary_injection_rows',int)-1,boundary)
            assert np.array_equal(vec(pol,'boundary_injection_external_groups',int),boundary_groups)
            assert np.all(np.asarray(pol['generator_share'])[boundary]==0)
            maxima['fixed_transfer_MW']=max(maxima['fixed_transfer_MW'],mx(d['DC_PF'][rows]-profiles['fixed_transfer_PF_MW'][hh]),mx(d['DC_PT'][rows]-profiles['fixed_transfer_PF_MW'][hh]))
            P=d['PF'][np.ix_(rows,l)];T=d['PT'][np.ix_(rows,l)];QF=d['QF'][np.ix_(rows,l)];QT=d['QT'][np.ix_(rows,l)]
            V=d['VM'][np.ix_(rows,b)];PD=d['PD'][np.ix_(rows,b)];QD=d['QD'][np.ix_(rows,b)]
            parents=vec(template,'branch_parent_row',int);owner=np.asarray(pol['loss_ownership']);parent_loss=np.zeros((len(rows),owner.shape[1]))
            for k,parent in enumerate(parents):parent_loss[:,parent-1]+=P[:,k]+T[:,k]
            budget=parent_loss@owner.T
            maxima['loss_budget_MW']=max(maxima['loss_budget_MW'],mx(budget-d['actual_budget_MW'][rows]))
            gross=np.column_stack([pd0[:,groups[:140]==g].sum(axis=1) for g in range(1,12)])
            served=np.column_stack([PD[:,groups==g].sum(axis=1) for g in range(1,12)])
            servedq=np.column_stack([QD[:,groups==g].sum(axis=1) for g in range(1,12)])
            assert np.all(served>0) and np.all(budget>=-1e-8)
            maxima['zonal_load_closure_MW']=max(maxima['zonal_load_closure_MW'],mx(served+budget[:,:11]-gross),mx(gross-d['NY_gross_target_MW'][rows]),mx(served-d['NY_served_PD_MW'][rows]),mx(servedq-d['NY_served_QD_MVAr'][rows]))
            ratio=served/gross;expectedPD=np.zeros_like(PD);expectedQD=np.zeros_like(QD);expectedPD[:,:140]=pd0;expectedQD[:,:140]=qd0
            for g in range(1,12):expectedPD[:,groups==g]*=ratio[:,g-1,None];expectedQD[:,groups==g]*=ratio[:,g-1,None]
            maxima['served_PD_QD_shape']=max(maxima['served_PD_QD_shape'],mx(PD-expectedPD),mx(QD-expectedQD))
            eg=np.asarray(pol['external_gen_group'],int)
            increments=np.column_stack([(pg-pg0)[:,eg==g].sum(axis=1) for g in range(12,15)])
            maxima['external_loss_increment_MW']=max(maxima['external_loss_increment_MW'],mx(increments-budget[:,11:]),mx(increments-d['external_PG_increment_MW'][rows]))
            imports=np.zeros((len(rows),3));gf=np.asarray(pol['parent_from'],int);gt=np.asarray(pol['parent_to'],int)
            for k in range(len(gf)):
                if gf[k]<=11 and gt[k]>11:imports[:,gt[k]-12]-=P[:,int(pol['from_runtime'][k])-1]
                elif gt[k]<=11 and gf[k]>11:imports[:,gf[k]-12]-=T[:,int(pol['to_runtime'][k])-1]
            # Derive transfer direction from endpoint groups independently of
            # the producer's regional-import implementation.
            bus_group_by_id=dict(zip(bus[:,0].astype(int),groups))
            for k,dc in enumerate(template['dcline']):
                gfrom=bus_group_by_id[int(dc[0])];gto=bus_group_by_id[int(dc[1])]
                if gfrom>11 and 1<=gto<=11:imports[:,gfrom-12]+=d['DC_PT'][rows,k]
                elif gto>11 and 1<=gfrom<=11:imports[:,gto-12]-=d['DC_PF'][rows,k]
                else:assert False,'A prescribed transfer lacks the declared external/NY boundary.'
            for row,g in zip(boundary,boundary_groups):imports[:,g-12]+=pg[:,row]
            targets=np.column_stack([pg0[:,eg==g].sum(axis=1)-pd0[:,groups[:140]==g].sum(axis=1) for g in range(12,15)])
            maxima['baseline_regional_import_target_MW']=max(maxima['baseline_regional_import_target_MW'],mx(targets-old['regional_import_target_MW'][hh]))
            maxima['regional_import_MW']=max(maxima['regional_import_MW'],mx(imports-targets),mx(imports-d['regional_import_solved_MW'][rows]),mx(targets-d['regional_import_target_MW'][rows]))
            aggregateP=np.zeros((len(rows),len(ids)));aggregateQ=aggregateP.copy()
            for k,node in enumerate(genbus):aggregateP[:,bilook[int(node)]]+=pg[:,k];aggregateQ[:,bilook[int(node)]]+=qg[:,k]
            maxima['bus_generation_aggregation']=max(maxima['bus_generation_aggregation'],mx(aggregateP-d['bus_PG'][rows]),mx(aggregateQ-d['bus_QG'][rows]))
            violations={'max_P_bound_violation_mw':violation(pg,lo,hi),
                'max_Q_bound_violation_mvar':violation(qg,-qcap,qcap),
                'max_assumed_generator_S_bound_violation_mva':np.maximum(0,np.hypot(pg,qg)-scap).max(axis=1),
                'max_voltage_bound_violation_pu':violation(V,bus[:,12],bus[:,11]),
                'max_transfer_Q_bound_violation_mvar':np.maximum(violation(d['DC_QF'][rows],template['dcline'][:,11],template['dcline'][:,12]),violation(d['DC_QT'][rows],template['dcline'][:,13],template['dcline'][:,14]))}
            for field,value in violations.items():maxima['reported_bound_violation_difference']=max(maxima['reported_bound_violation_difference'],mx(value-vec(d,field)[rows]))
            assert violations['max_P_bound_violation_mw'].max()<1e-5
            fys={int(x):k for k,x in enumerate(bus[:,0])};f=np.array([fys[int(x)] for x in br[:,0]]);to=np.array([fys[int(x)] for x in br[:,1]])
            If=1000*np.hypot(P,QF)/(np.sqrt(3)*bus[f,9]*V[:,f]);It=1000*np.hypot(T,QT)/(np.sqrt(3)*bus[to,9]*V[:,to])
            maxima['current_from_power_A']=max(maxima['current_from_power_A'],mx(If-d['Ifrom'][np.ix_(rows,l)]),mx(It-d['Ito'][np.ix_(rows,l)]))
            shift=np.broadcast_to(br[:,9],(len(rows),len(br))).copy()
            if state==4:shift[:,410:412]=profiles['dover_bank_phase_shift_deg'][hh]
            maxima['phase_control_deg']=max(maxima['phase_control_deg'],mx(shift-d['branch_SHIFT'][np.ix_(rows,l)]))
            physical=(violations['max_voltage_bound_violation_pu']<1e-7)&(violations['max_Q_bound_violation_mvar']<1e-5)&(violations['max_assumed_generator_S_bound_violation_mva']<1e-5)&(violations['max_transfer_Q_bound_violation_mvar']<1e-5)
            assert np.array_equal(physical,vec(d,'VQ_and_generator_assumption_gate',bool)[rows]);physicalall[hh]=physical
            # Full operating status additionally includes declared MVA/current limits.
            rate=br[:,5];rated=(br[:,10]>0)&(rate>0)
            mva=np.maximum(0,np.maximum(np.hypot(P[:,rated],QF[:,rated])-rate[rated],np.hypot(T[:,rated],QT[:,rated])-rate[rated])).max(axis=1,initial=0)
            maxima['reported_bound_violation_difference']=max(maxima['reported_bound_violation_difference'],mx(mva-vec(d,'max_equipment_MVA_violation')[rows]))
            full=physical&(mva<1e-4)
            for limits in sequence(template['current_limits']):
                rr=vec(limits,'branch_row',int)-1
                for key,amps in [('from_A',If),('to_A',It)]:
                    cap=vec(limits,key);known=np.isfinite(cap);full&=(amps[:,rr[known]]/cap[known]).max(axis=1,initial=0)<=1+1e-6
            assert np.array_equal(full,vec(d,'full_operating_gate',bool)[rows]);fullall[hh]=full
            for j,h in enumerate(hh):physical_rows.append({'hour_index':int(h+1),**{key:float(value[j]) for key,value in violations.items()},'VQ_qualified':bool(physical[j]),'full_operating_qualified':bool(full[j])})
        monthly.append({'month':mon,'source_qualified':int(source[ix].sum()),'candidate_qualified':int(good.sum()),'paired':int((good&oldgood[ix]).sum()),'new':int((good&~oldgood[ix]).sum()),'lost':int((oldgood[ix]&~good).sum()),'solver_exceptions':int(exception.sum())})
        print(f'Annual validation month{mon:02d}: {good.sum()}/{source[ix].sum()} qualified',flush=True)
    for key,limit in tolerances.items():assert maxima[key]<limit,(key,maxima[key],limit)
    assert np.array_equal(seen,months<=count) and goodall.sum()==producer['policy_equation_qualified_hours']
    if not partial:assert seen.all() and int((oldgood&goodall).sum())==producer['paired_current_baseline_hours']
    suffix=f'partial_{count:02d}' if partial else 'annual'
    failure_path=out/f'{suffix}_failed_hours.csv';pd.DataFrame(failures,columns=['hour_index','timestamp_utc','status','solver_exception','baseline_current_qualified','valid_prediction']).to_csv(failure_path,index=False)
    physical_path=out/f'{suffix}_physical_limits.csv';pd.DataFrame(physical_rows).to_csv(physical_path,index=False)
    report={'passed':True,'completed':not partial,'created_utc':datetime.now(timezone.utc).isoformat(),'months_checked':count,
        'source_qualified_hours':int(source[seen].sum()),'candidate_qualified_hours':int(goodall.sum()),'paired_current_baseline_hours':int((oldgood&goodall).sum()),
        'candidate_new_success_hours':int((source&~oldgood&goodall).sum()),'current_success_lost_hours':int((oldgood&seen&~goodall).sum()),
        'VQ_qualified_hours':int(physicalall.sum()),'full_operating_qualified_hours':int(fullall.sum()),
        'all_clock_rows_and_original_source_mask_preserved':True,'compiled_candidate_native_HQ_boundary_profiles_and_fixed_transfer_targets_preserved':True,
        'fixed_boundary_PQ_rows_verified':(boundary+1).tolist(),'fixed_boundary_not_native_or_loss_balancer':True,
        'finite_P_Q_S_capability_metadata_reconstructed':True,'physical_limit_violations_reported_without_promoting_failed_operating_cases':True,
        'loss_ownership_and_regional_accounting_recomputed_from_saved_flows':True,'terminal_amperes_checked_using_actual_voltage_without_gamma_lift':True,
        'raw_complex_branch_law_and_passive_recovery_audit':'Separate moses_repair/validation review required for final physical validation.',
        'maximum_independent_errors':maxima,'tolerances':tolerances,'monthly_counts':monthly,
        'source_hashes_verified':len(source_records),'producer':record(Path(__file__)),
        'dependencies':[record(p) for p in paths], 'outputs':[record(failure_path),record(physical_path)],
        'limitations':['Equation qualification does not certify all voltage/Q/S/current limits or historical as-built asset identity.',
            'Failed or partial returned iterates remain invalid predictions; failure does not prove global infeasibility.']}
    (out/f'{suffix}_input_accounting_review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['passed','completed','source_qualified_hours','candidate_qualified_hours','paired_current_baseline_hours','VQ_qualified_hours','full_operating_qualified_hours']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--partial',action='store_true');args=p.parse_args();main(args.run_dir,args.partial)
