"""Independent saved-array validation of the controlled G/P interventions.

No PF, loader import, P32 observation read, or scenario-input modification.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_postrepair_diagnosis/ablations'
BASE = ROOT / 'output/nygrid_2025_moses_repair/annual'


def record(path):
    with path.open('rb') as f: digest = hashlib.file_digest(f, 'sha256').hexdigest()
    try: name=path.relative_to(ROOT).as_posix()
    except ValueError: name=str(path)
    return {'path': name, 'sha256': digest, 'bytes': path.stat().st_size}


def mx(value):
    value = np.asarray(value); assert np.isfinite(value).all()
    return float(np.abs(value).max(initial=0))


def vec(d, key, dtype=float): return np.asarray(d[key], dtype=dtype).reshape(-1)


class Inputs:
    def __init__(self):
        self.models = {}; self.profiles = {}
        for label, folder in [('B','baseline_bundle'), ('GP','candidate_bundle')]:
            path = BASE / folder / 'model'
            self.models[label] = loadmat(path / 'latest_model.mat', simplify_cells=True)['model']
            parts = [loadmat(path / name, simplify_cells=True)['profiles'] for name in ['profiles_h0001_4380.mat','profiles_h4381_8760.mat']]
            self.profiles[label] = {k:np.concatenate([x[k] for x in parts]) for k in parts[0]}
        self.model = self.models['GP']; self.ext = vec(self.model['external'],'generator_mask',bool)
        assert len(self.ext)==1466 and self.ext[-1] and not self.ext[-2]

    def arrays(self, scenario, hh):
        new, old = self.profiles['GP'], self.profiles['B']; e=self.ext
        pg = new['generator_PG_MW'][hh].copy(); hi=new['generator_Pmax_MW'][hh].copy(); lo=new['generator_Pmin_MW'][hh].copy()
        if scenario in ['B','P']:
            use=np.flatnonzero(~e[:1464])
            pg[:,use]=old['generator_PG_MW'][hh][:,use];hi[:,use]=old['generator_Pmax_MW'][hh][:,use];lo[:,use]=old['generator_Pmin_MW'][hh][:,use]
            pg[:,1464]=0;hi[:,1464]=0;lo[:,1464]=0
        if scenario in ['B','G']:
            use=np.flatnonzero(e[:1464])
            pg[:,use]=old['generator_PG_MW'][hh][:,use];hi[:,use]=old['generator_Pmax_MW'][hh][:,use];lo[:,use]=old['generator_Pmin_MW'][hh][:,use]
            pg[:,1465]=0;hi[:,1465]=0;lo[:,1465]=0
        hi[:,e]=pg[:,e];lo[:,e]=pg[:,e]
        status=(hi>0)|(lo<0);pcap=np.maximum(abs(hi),abs(lo));cap=pcap.copy()
        cap[:,e]=vec(self.model['external'],'capability_proxy_MW');cap[:,1465]=abs(pg[:,1465])
        scap=cap/.95;scap[:,1465]=abs(pg[:,1465])
        qcap=cap*np.tan(np.arccos(.95));qcap[:,e]=np.sqrt(np.maximum(0,(cap[:,e]/.95)**2-pg[:,e]**2))
        qcap[~status]=0;qcap[:,1465]=0
        return dict(pg=pg,hi=hi,lo=lo,status=status,pcap=pcap,cap=cap,scap=scap,qcap=qcap,
                    wp=1/np.maximum(pcap,1),wq=.01/np.maximum(qcap,1))


def validate_samples(inputs):
    path=OUT/'bridge_samples.mat';samples=loadmat(path,simplify_cells=True)['sample'];worst=0.;count=0
    for sample in samples:
        label=str(sample['scenario']);h=int(sample['hour_index'])-1;m=sample['input'];d=inputs.arrays(label,np.array([h]));gen=m['gen']
        for col,key in [(1,'pg'),(3,'qcap'),(7,'status'),(8,'hi'),(9,'lo')]:worst=max(worst,mx(gen[:,col]-d[key][0]))
        worst=max(worst,mx(gen[:,4]+d['qcap'][0]),mx(gen[:,2]),mx(gen[:,6]-np.maximum(d['cap'][0]/.95,1)))
        u=m['userdata']['ac_system']
        for name,key in [('generator_p_reference','pg'),('generator_capability_reference','cap'),('generator_q_cap','qcap'),('generator_assumed_s_cap','scap'),('p_objective_weight','wp'),('q_objective_weight','wq')]:
            worst=max(worst,mx(vec(u,name)-d[key][0]))
        pg=d['pg'][0];wp=d['wp'][0];wq=d['wq'][0];n=len(pg)
        cost=np.vstack([np.column_stack([np.full(n,2),np.zeros((n,2)),np.full(n,3),wp,-2*wp*pg,wp*pg**2]),
                        np.column_stack([np.full(n,2),np.zeros((n,2)),np.full(n,3),wq,np.zeros((n,2))])])
        worst=max(worst,mx(m['gencost']-cost));s=int(inputs.model['axis']['state_index'][h])-1;template=inputs.model['templates'][s]
        bus=m['bus'];ref=int(inputs.model['axis']['reference_bus'][h]);control=d['status'][0].copy();control[1465]=False
        types=np.ones(len(bus));types[np.isin(bus[:,0],gen[control,0])]=2;types[bus[:,0]==ref]=3
        assert np.array_equal(bus[:,1],types)
        lookup={int(x):j for j,x in enumerate(bus[:,0])};vg=np.array([template['bus'][lookup[int(x)],7] for x in gen[:,0]])
        worst=max(worst,mx(gen[:,5]-vg),mx(bus[:140,2]-inputs.profiles['GP']['bus_PD_MW'][h]),mx(bus[:140,3]-inputs.profiles['GP']['bus_QD_MVAr'][h]))
        assert np.array_equal(gen[:,0],inputs.model['generator_bus_ids'])
        count+=1
    assert count==48 and worst<1e-7,(count,worst)
    return {'passed':True,'sample_input_cases':count,'scenarios':['B','G','P','GP'],
            'reconstructed_fields':['PG','Pmin','Pmax','status','Qcaps','Scap','MBASE','VG','bus types','gencost','all generator capability/objective metadata'],
            'maximum_numeric_difference':worst,'source':record(path)}


def main(scenario, partial=False):
    run=OUT/f'{scenario}_v1';capture=run/('progress.json' if partial else 'annual_receipt.json');receipt=json.loads(capture.read_text())
    months=int(receipt['months_complete']);assert months>0 and (partial or receipt['completed'])
    recipe_path=OUT/'scenario_recipe.json';recipe=json.loads(recipe_path.read_text())
    for item in recipe['inputs']:assert record(ROOT/item['path'])['sha256']==item['sha256'],item['path']
    if not partial:
        for item in receipt['source_records']:assert record(Path(item['path']))['sha256']==item['sha256'],item['path']
    inputs=Inputs();sample_review=validate_samples(inputs)
    source_axes=loadmat(OUT/'source_axes.mat',simplify_cells=True);axes=loadmat(run/'axes.mat',simplify_cells=True)
    network_path=BASE/'moses_repair_v1/annual_network.mat';templates=loadmat(network_path,simplify_cells=True)['templates']
    ids=vec(axes,'bus_id',int);keys=vec(axes,'branch_keys',str);genbus=vec(axes,'generator_bus_id',int)
    lookup={x:j for j,x in enumerate(ids)};kl={x:j for j,x in enumerate(keys)}
    source=vec(source_axes,'source_qualified',bool);states=vec(source_axes,'topology_state_index',int);month_axis=vec(source_axes,'model_month',int)
    names=['branch_power_MVA','nodal_P_MW','nodal_Q_MVAr','native_HQ_fixed_boundary_P_MW','fixed_boundary_Q_MVAr',
           'generator_P_aggregation_MW','fixed_DC_P_MW','regional_import_MW','regional_target_preserved_MW','loss_ownership_MW',
           'zonal_load_closure_MW','served_load_shape_MW_MVAr','external_loss_increment_MW','phase_control_deg','generator_P_bounds_MW']
    worst={k:0. for k in names};seen=np.zeros(8760,bool);goodall=seen.copy();qrows=[];delta_rows=[];deps=[capture,recipe_path,network_path,run/'axes.mat',OUT/'source_axes.mat',OUT/'bridge_samples.mat']
    generation=loadmat(ROOT/'output/nygrid_2025_moses_repair/generation/generation_candidate.mat',simplify_cells=True,variable_names=['stlawrence_rows_1based','hydro_rows_1based'])
    stl=vec(generation,'stlawrence_rows_1based',int)-1;hy=vec(generation,'hydro_rows_1based',int)-1
    for mon in range(1,months+1):
        path=run/'monthly'/f'ablation_{mon:02d}.mat';d=loadmat(path,simplify_cells=True);ix=vec(d,'hour_index',int)-1;deps.append(path)
        assert record(path)['sha256']==receipt['months'][mon-1]['output']['sha256']
        assert np.array_equal(ix,np.flatnonzero(month_axis==mon)) and not seen[ix].any();seen[ix]=True
        q=vec(d,'source_qualified',bool)&~vec(d,'solver_exception',bool)
        for flag in ['PF_converged','AC_equation_gate','loss_allocation_gate','reduction_and_equation_gate']:q&=vec(d,flag,bool)
        assert np.array_equal(q,vec(d,'qualified',bool)) and np.array_equal(vec(d,'PF_attempted',bool),source[ix]);goodall[ix]=q
        assert np.isnan(d['gen_PG'][~source[ix]]).all()
        for state in np.unique(states[ix]):
            use=np.flatnonzero(q&(states[ix]==state));hh=ix[use]
            if not len(use):continue
            template=templates[int(state)-1];b=template['bus'];br=template['branch'];pol=template['policy'];groups=vec(pol,'bus_group',int)
            ib=np.array([lookup[int(x)] for x in b[:,0]]);il=np.array([kl[x] for x in vec(template,'branch_keys',str)])
            f=np.array([lookup[int(x)] for x in br[:,0]]);t=np.array([lookup[int(x)] for x in br[:,1]])
            initial=inputs.arrays(scenario,hh);pg0=initial['pg'];pg=d['gen_PG'][use];eg=vec(pol,'external_gen_group',int)
            fixed=(~inputs.ext)|(np.arange(1466)==1463)|(np.arange(1466)==1465)
            worst['native_HQ_fixed_boundary_P_MW']=max(worst['native_HQ_fixed_boundary_P_MW'],mx(pg[:,fixed]-pg0[:,fixed]))
            worst['fixed_boundary_Q_MVAr']=max(worst['fixed_boundary_Q_MVAr'],mx(vec(d,'fixed_boundary_QG')[use]))
            lo=initial['lo'].copy();hi=initial['hi'].copy();static=inputs.model['loss_static'][int(state)-1]
            finite=vec(static,'finite_external_generator_rows',int)-1;lo[:,finite]=vec(static,'finite_external_Pmin_MW');hi[:,finite]=vec(static,'finite_external_Pmax_MW')
            worst['generator_P_bounds_MW']=max(worst['generator_P_bounds_MW'],float(np.maximum(0,np.maximum(lo-pg,pg-hi)).max()))
            ag=np.zeros((len(use),len(ids)))
            for k,node in enumerate(genbus):ag[:,lookup[node]]+=pg[:,k]
            worst['generator_P_aggregation_MW']=max(worst['generator_P_aggregation_MW'],mx(ag-d['bus_PG'][use]))
            V=d['VM'][use]*np.exp(1j*np.deg2rad(d['VA'][use]));shift=d['branch_SHIFT'][np.ix_(use,il)]
            expected_shift=np.broadcast_to(br[:,9],shift.shape).copy()
            if state==4:expected_shift[:,410:412]=inputs.profiles['GP']['dover_bank_phase_shift_deg'][hh]
            worst['phase_control_deg']=max(worst['phase_control_deg'],mx(shift-expected_shift))
            on=br[:,10]>0;tap=np.where(br[:,8]==0,1,br[:,8])[None,:]*np.exp(1j*np.deg2rad(shift))
            y=np.where(on,1/(br[:,2]+1j*br[:,3]),0);bc=1j*br[:,4]*on/2;series=(V[:,f]/tap-V[:,t])*y
            sf=100*V[:,f]*np.conj(series/np.conj(tap)+bc*V[:,f]/abs(tap)**2);st=100*V[:,t]*np.conj(-series+bc*V[:,t])
            pf=d['PF'][np.ix_(use,il)];pt=d['PT'][np.ix_(use,il)]
            worst['branch_power_MVA']=max(worst['branch_power_MVA'],mx(sf-(pf+1j*d['QF'][np.ix_(use,il)])),mx(st-(pt+1j*d['QT'][np.ix_(use,il)])))
            injection=d['bus_PG'][use]+1j*d['bus_QG'][use]-d['PD'][use]-1j*d['QD'][use]
            injection[:,ib]-=abs(V[:,ib])**2*(b[:,4]-1j*b[:,5])
            dc_expected=inputs.profiles['GP']['fixed_transfer_PF_MW'][hh]
            worst['fixed_DC_P_MW']=max(worst['fixed_DC_P_MW'],mx(d['DC_PF'][use]-dc_expected),mx(d['DC_PT'][use]-dc_expected))
            for k,dc in enumerate(template['dcline']):
                if dc[2]>0:
                    injection[:,lookup[int(dc[0])]]+=-d['DC_PF'][use,k]+1j*d['DC_QF'][use,k]
                    injection[:,lookup[int(dc[1])]]+=d['DC_PT'][use,k]+1j*d['DC_QT'][use,k]
            for k in range(len(br)):injection[:,f[k]]-=sf[:,k];injection[:,t[k]]-=st[:,k]
            worst['nodal_P_MW']=max(worst['nodal_P_MW'],mx(injection[:,ib].real));worst['nodal_Q_MVAr']=max(worst['nodal_Q_MVAr'],mx(injection[:,ib].imag))
            parents=vec(template,'branch_parent_row',int);owner=np.asarray(pol['loss_ownership']);pl=np.zeros((len(use),owner.shape[1]))
            for k,parent in enumerate(parents):pl[:,parent-1]+=pf[:,k]+pt[:,k]
            budget=pl@owner.T;worst['loss_ownership_MW']=max(worst['loss_ownership_MW'],mx(budget-d['actual_budget_MW'][use]))
            pd0=inputs.profiles['GP']['bus_PD_MW'][hh];qd0=inputs.profiles['GP']['bus_QD_MVAr'][hh]
            served_pd=d['PD'][np.ix_(use,ib)];served_qd=d['QD'][np.ix_(use,ib)]
            gross=np.column_stack([pd0[:,groups[:140]==g].sum(axis=1) for g in range(1,12)])
            served=np.column_stack([served_pd[:,groups==g].sum(axis=1) for g in range(1,12)])
            worst['zonal_load_closure_MW']=max(worst['zonal_load_closure_MW'],mx(served+budget[:,:11]-gross),mx(gross-d['NY_gross_target_MW'][use]),mx(served-d['NY_served_PD_MW'][use]))
            epd=np.zeros_like(served_pd);eqd=np.zeros_like(served_qd);epd[:,:140]=pd0;eqd[:,:140]=qd0
            for g in range(1,12):ratio=served[:,g-1]/gross[:,g-1];epd[:,groups==g]*=ratio[:,None];eqd[:,groups==g]*=ratio[:,None]
            worst['served_load_shape_MW_MVAr']=max(worst['served_load_shape_MW_MVAr'],mx(served_pd-epd),mx(served_qd-eqd))
            increments=np.column_stack([(pg-pg0)[:,eg==g].sum(axis=1) for g in range(12,15)])
            worst['external_loss_increment_MW']=max(worst['external_loss_increment_MW'],mx(increments-budget[:,11:]),mx(increments-d['external_PG_increment_MW'][use]))
            imports=np.zeros((len(use),3));gf=vec(pol,'parent_from',int);gt=vec(pol,'parent_to',int)
            for k in range(len(gf)):
                if gf[k]<=11 and gt[k]>11:imports[:,gt[k]-12]-=pf[:,int(pol['from_runtime'][k])-1]
                elif gt[k]<=11 and gf[k]>11:imports[:,gf[k]-12]-=pt[:,int(pol['to_runtime'][k])-1]
            group_by_id=dict(zip(b[:,0].astype(int),groups))
            for k,dc in enumerate(template['dcline']):
                gfrom=group_by_id[int(dc[0])];gto=group_by_id[int(dc[1])]
                if gfrom>11 and 1<=gto<=11:imports[:,gfrom-12]+=d['DC_PT'][use,k]
                elif gto>11 and 1<=gfrom<=11:imports[:,gto-12]-=d['DC_PF'][use,k]
                else:raise AssertionError('DC transfer does not join external and NY groups.')
            imports[:,0]+=pg[:,1465]
            targets=np.column_stack([pg0[:,eg==g].sum(axis=1)-pd0[:,groups[:140]==g].sum(axis=1) for g in range(12,15)])
            baseline_pg=np.column_stack([inputs.profiles['B']['generator_PG_MW'][hh],np.zeros((len(hh),2))])
            baseline_targets=np.column_stack([baseline_pg[:,eg==g].sum(axis=1)-pd0[:,groups[:140]==g].sum(axis=1) for g in range(12,15)])
            worst['regional_target_preserved_MW']=max(worst['regional_target_preserved_MW'],mx(targets-baseline_targets))
            worst['regional_import_MW']=max(worst['regional_import_MW'],mx(imports-targets),mx(imports-d['regional_import_solved_MW'][use]),mx(targets-d['regional_import_target_MW'][use]))
            for j,h in enumerate(hh):
                delta_rows.append({'hour_index':int(h+1),'scenario':scenario,'native_PG_change_public_MW':float((pg0[j,~inputs.ext]-baseline_pg[j,~inputs.ext]).sum()/source_axes['gamma']),
                    'StLawrence_PG_change_public_MW':float((pg0[j,stl]-baseline_pg[j,stl]).sum()/source_axes['gamma']),
                    'other_HY_PG_change_public_MW':float((pg0[j,hy]-baseline_pg[j,hy]).sum()/source_axes['gamma']-(pg0[j,stl]-baseline_pg[j,stl]).sum()/source_axes['gamma']),
                    'PV20_public_MW':float(pg0[j,1465]/source_axes['gamma']),
                    'ISONE_nonPV20_PG_change_public_MW':float((pg0[j,(eg==12)&(np.arange(1466)!=1465)]-baseline_pg[j,(eg==12)&(np.arange(1466)!=1465)]).sum()/source_axes['gamma']),
                    'northern_nodal_P_residual_MW':mx(injection[j,[lookup[48],lookup[49]]].real)})
        qrows.append({'month':mon,'source_qualified':int(source[ix].sum()),'qualified':int(q.sum())})
        print(f'{scenario} independent month{mon:02d}: {q.sum()}/{source[ix].sum()} qualified',flush=True)
    assert seen.sum()==np.count_nonzero(month_axis<=months)
    for name,value in worst.items():assert value<1e-5,(scenario,name,value)
    assert worst['native_HQ_fixed_boundary_P_MW']<1e-7 and worst['regional_target_preserved_MW']<1e-7
    suffix=f'partial_{months:02d}' if partial else 'annual';pd.DataFrame(delta_rows).sort_values('hour_index').to_csv(run/f'{suffix}_scenario_PG_deltas.csv',index=False)
    result={'passed':True,'completed':not partial,'created_utc':datetime.now(timezone.utc).isoformat(),'scenario':scenario,
        'source_qualified_hours_checked':int(source[seen].sum()),'qualified_hours':int(goodall.sum()),'monthly_counts':qrows,
        'maximum_independent_errors':worst,'sample_metadata_review':sample_review,
        'all_hour_raw_branch_laws_and_nodal_KCL_verified':True,'all_hour_native_HQ_boundary_P_and_DC_preserved':True,
        'regional_targets_identical_to_baseline':True,'all_hour_loss_ownership_recomputed':True,
        'no_P32_observation_read':True,'no_PF_called':True,'inputs':[record(p) for p in deps],'producer':record(Path(__file__))}
    (run/f'{suffix}_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'scenario':scenario,'completed':not partial,'qualified_hours':int(goodall.sum()),'maxima':worst}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('scenario',choices=['G','P']);parser.add_argument('--partial',action='store_true')
    args=parser.parse_args();main(args.scenario,args.partial)
