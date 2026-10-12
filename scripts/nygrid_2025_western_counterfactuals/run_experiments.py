"""Source-only matched DC replays, followed by an explicit posthoc score step.

Default invocation constructs and solves experiments without opening internal
observations. --score-only is allowed after complete full-cohort outputs are
sealed. Literal infeasible hypotheses are reported, never scored on fewer hours.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from scipy.io import loadmat,savemat
from common import BASE,FULL,NAMES,OUT,PAR,PARENT,ROOT,SLIM,atomic_json,check_records,load_baseline,read,record,require,sha

sys.path.insert(0,str(ROOT/'scripts/nygrid_2025_par_controls'))
from controlled_equivalent import make_controlled_case
sys.path.insert(0,str(ROOT/'scripts/nygrid_2019'))
from replay_dc import network,predict

def check_axes(d,b,is_load=False):
    require(np.array_equal(d['hour_index'],np.arange(1,8761))
            and np.array_equal(d['timestamp_utc'].astype(str),b['times']), 'Candidate physical-hour axis differs')
    require(np.asarray(d['gamma']).shape==() and float(d['gamma'])==b['gamma'], 'Candidate power scale differs')
    if is_load:
        expected=loadmat(SLIM,simplify_cells=True,variable_names=['kept_bus_ids'])['kept_bus_ids']
        require(np.array_equal(d['bus_ids'],expected), 'Candidate load bus axis differs')

def inputs(b,generation=None,demand=None):
    q=b['qualified'];pg=np.asarray(b['dispatch']['gen_pg']).copy()
    pd0=np.pad(b['data']['bus_pd'],((0,0),(0,8)))
    qd0=np.pad(b['data']['bus_qd'],((0,0),(0,8)))
    if generation is not None:
        path=ROOT/generation['file'];require(sha(path)==generation['sha256'],'Generation candidate changed')
        with np.load(path,allow_pickle=False) as d:
            check_axes(d,b)
            require(np.array_equal(d['qualified'],q),'Incomplete generation hypotheses are not primary experiments')
            require(np.array_equal(d['fixed_experiment_mask'],q) and str(d['variant_name'])==generation['name'], 'Generation candidate identity differs')
            raw_rows=np.asarray(d['gen_rows_1based']).ravel()
            require(np.isfinite(raw_rows).all() and np.equal(raw_rows,np.floor(raw_rows)).all(), 'Nonintegral generator identity')
            rows=raw_rows.astype(int)-1
            require(len(rows)==len(set(rows)) and np.isin(rows,np.arange(1436)).all(),'Changed rows include an external or duplicate generator')
            require(d['gen_pg_changed'].shape==(8760,len(rows)),'Compact generator axis changed')
            pg[:,rows]=d['gen_pg_changed']
    if demand is not None:
        path=ROOT/demand['file'];require(sha(path)==demand['sha256'],'Load candidate changed')
        with np.load(path,allow_pickle=False) as d:
            check_axes(d,b,True)
            require(np.array_equal(d['qualified'],q),'Incomplete load candidate')
            require(str(d['scenario'])==demand['name'],'Load candidate identity differs')
            pd0=np.asarray(d['bus_pd']).copy();qd0=np.asarray(d['bus_qd']).copy()
    require(pd0.shape==qd0.shape==(8760,148) and pg.shape==(8760,1464),'Experiment matrix shape changed')
    require(np.isfinite(pg[q]).all() and np.isfinite(pd0[q]).all() and np.isfinite(qd0[q]).all(),'Missing qualified injection')
    require(np.array_equal(pg[q,1436:],b['dispatch']['gen_pg'][q,1436:]),'External boundary equivalents changed')
    require(np.max(abs(pg[q].sum(axis=1)-pd0[q].sum(axis=1)-b['data']['base_case']['bus'][:,4].sum()))<1e-7,
            'An experiment changed hourly total net injection')
    lo,hi=b['bounds']['gen_pmin'][:,:1436],b['bounds']['gen_pmax'][:,:1436]
    require(np.min(pg[q,:1436]-lo[q])>=-1e-7 and np.max(pg[q,:1436]-hi[q])<=1e-7,'Native capability bound violated')
    pg[~q]=np.nan
    return pg,pd0,qd0

def full_flow(fullcase,recovery,angle):
    theta=np.deg2rad(angle)@recovery['angle_lift'].T+recovery['angle_offset']
    branch=np.asarray(fullcase['branch']);bus=np.asarray(fullcase['bus'])
    ids={int(v):i for i,v in enumerate(bus[:,0])}
    f=np.array([ids[int(x)] for x in branch[:,0]]);t=np.array([ids[int(x)] for x in branch[:,1]])
    active=branch[:,10].astype(bool).copy();active[210]=False
    tap=np.where(branch[:,8]==0,1,branch[:,8]);k=np.zeros(len(branch))
    k[active]=float(fullcase['baseMVA'])/(branch[active,3]*tap[active])
    return (theta[:,f]-theta[:,t]-np.deg2rad(branch[:,9]))*k

def solve(b,model,pg,pd0):
    q=b['qualified'];states=np.asarray(b['baseline']['network_state_ids']).astype(str)
    angles=np.full((8760,148),np.nan);flows=np.full((8760,274),np.nan)
    interface=np.full((8760,7),np.nan);residual=np.full(8760,np.nan);slack=np.full(8760,np.nan)
    dc=np.column_stack([b['data']['dc_pf'],b['par']['observed_model_mw']])
    for state in sorted(set(states)):
        ix=np.flatnonzero(q&(states==state))
        if not len(ix):continue
        case=make_controlled_case(model[state],b['register'].bus_id.to_numpy(int),dc[ix[0],4:],b['par']['p_only_limit_model_mw'])
        r=predict(network(case),pd0[ix],pg[ix],dc[ix])
        angle=r['angle_deg'];ref=np.asarray(b['data']['reference_bus'],int)[ix]-1
        angle-=angle[np.arange(len(ix)),ref][:,None]
        rec=model['recovery'][state.removesuffix('_case')]
        angles[ix]=angle;flows[ix]=r['flow']
        interface[ix]=np.deg2rad(angle)@rec['interface_angle_matrix'].T+rec['interface_flow_offset']
        residual[ix]=r['nodal_residual_mw'];slack[ix]=np.max(abs(r['result_pg']-pg[ix]),axis=1)
    require(np.nanmax(residual)<1e-7 and np.nanmax(slack)<1e-7,'Counterfactual power flow changed balanced generation')
    return dict(bus_va=angles,interface_pf=interface,branch_pf=flows,nodal_residual_mw=residual,slack_change_mw=slack)

def build():
    b=load_baseline();q=b['qualified'];model=loadmat(SLIM,simplify_cells=True)
    design=read(OUT/'design/experiment_plan.json');check_records(design['dependencies'])
    require(design['fixed_hour_mask']['sha256']==sha(PARENT/'replay/paired_common_mask.npy'),'Experimental mask changed')
    gen_receipt=read(OUT/'inputs/niagara_receipt.json');load_receipt=read(OUT/'inputs/load_receipt.json')
    for receipt,kind in [(gen_receipt,'generation'),(load_receipt,'load')]:
        require(receipt['passed'] and receipt['datasettype']==kind,'Unqualified input family')
        check_records(receipt['dependencies']);check_records([dict(path=s['file'],sha256=s['sha256']) for s in receipt['scenarios']])
    full_gen=[r for r in gen_receipt['scenarios'] if r['full_fixed_cohort']]
    excluded=[r for r in gen_receipt['scenarios'] if not r['full_fixed_cohort']]
    require(len(full_gen)>0 and all(r['qualified_hours']==8651 for r in full_gen),'No complete Niagara hypotheses')
    load_b=[r for r in load_receipt['scenarios'] if r['name']=='load_original_B']
    require(len(load_b)==1,'Missing predeclared load interaction control')
    cases=[dict(name='baseline',family='baseline',generation=None,demand=None)]
    cases += [dict(name=r['name'],family='niagara',generation=r,demand=None) for r in full_gen]
    cases += [dict(name=r['name'],family='load',generation=None,demand=r) for r in load_receipt['scenarios']]
    cases += [dict(name=r['name']+'__load_original_B',family='interaction',generation=r,demand=load_b[0]) for r in full_gen]
    folder=OUT/'replay';folder.mkdir(parents=True,exist_ok=True)
    # This catalog is sealed before any internal observation file is opened.
    catalog=dict(created_utc=datetime.now(timezone.utc).isoformat(),fixed_hours=8651,
        cases=cases,excluded_literal_hypotheses=excluded,
        excluded_policy='No power flow or score on the reduced feasible cohort; only feasibility is reported.',
        all_internal_observation_access_deferred=True,
        dependencies=[record(OUT/p) for p in ['design/experiment_plan.json','inputs/niagara_receipt.json','inputs/load_receipt.json']])
    atomic_json(folder/'candidate_catalog.json',catalog)
    states=np.asarray(b['baseline']['network_state_ids']).astype(str)
    months=pd.to_datetime(b['times'],utc=True).tz_convert('America/New_York').month.to_numpy()
    fixed_samples=[]
    for state in sorted(set(states)):fixed_samples.append(int(np.flatnonzero(q&(states==state))[0]))
    for month in [1,4,7,10]:fixed_samples.append(int(np.flatnonzero(q&(months==month))[0]))
    samples=sorted(set(fixed_samples))
    records=[];fixtures=[];baseline_result=None
    for c in cases:
        pg,pd0,qd0=inputs(b,c['generation'],c['demand']);r=solve(b,model,pg,pd0)
        if c['name']=='baseline':
            for field in ['bus_va','interface_pf','branch_pf']:
                require(np.max(abs(r[field][q]-b['baseline'][field][q]))<1e-7,'Fresh experiment baseline changed '+field)
            baseline_result=r
        path=folder/(c['name']+'.npz')
        np.savez_compressed(path,hour_index=np.arange(1,8761),timestamp_utc=b['times'],qualified=q,
            network_state_ids=states,bus_va=r['bus_va'],interface_pf=r['interface_pf'],
            nodal_residual_mw=r['nodal_residual_mw'],slack_change_mw=r['slack_change_mw'],gamma=b['gamma'])
        row=dict(name=c['name'],family=c['family'],qualified_hours=int(q.sum()),file=path.relative_to(ROOT).as_posix(),sha256=sha(path),
            generation=c['generation'],demand=c['demand'],
            maximum_nodal_residual_model_mw=float(np.nanmax(r['nodal_residual_mw'])),
            maximum_slack_change_model_mw=float(np.nanmax(r['slack_change_mw'])),
            maximum_western_change_public_mw=np.max(abs((r['interface_pf'][q,:2]-baseline_result['interface_pf'][q,:2])/b['gamma']),axis=0).tolist())
        records.append(row)
        # Predetermined state/season fixtures; no observation-error selection.
        selected=samples if c['family']!='interaction' else samples[:2]
        for h in selected:
            fixtures.append(dict(name=c['name'],hour_index=h+1,gen_pg=pg[h],bus_pd=pd0[h],bus_qd=qd0[h],
                bus_va=r['bus_va'][h],branch_pf=r['branch_pf'][h],interface_pf=r['interface_pf'][h]))
        print(c['name']+' solved8651hours',flush=True)
    savemat(OUT/'replay/matlab_fixtures.mat',dict(fixtures=np.asarray(fixtures,dtype=object),gamma=b['gamma']),do_compression=True)
    deps=b['paths']+[OUT/'design/experiment_plan.json',OUT/'replay/candidate_catalog.json',OUT/'inputs/niagara_receipt.json',
        OUT/'inputs/load_receipt.json',Path(__file__),ROOT/'scripts/nygrid_2025_par_controls/controlled_equivalent.py',
        ROOT/'scripts/nygrid_2019/replay_dc.py']
    deps += [ROOT/r['file'] for r in full_gen+load_receipt['scenarios']]
    receipt=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),fixed_qualified_hours=int(q.sum()),
        internal_observations_read=False,all_boundaries_unchanged=True,original_unit_bounds_unchanged=True,
        topology_unchanged=True,cases=records,excluded_unscored_cases=excluded,
        fixture_file=record(OUT/'replay/matlab_fixtures.mat'),
        dependencies=[record(p) for p in dict.fromkeys(deps)])
    atomic_json(folder/'replay_receipt.json',receipt)
    return receipt

def score():
    receipt=read(OUT/'replay/replay_receipt.json');require(receipt['passed'] and not receipt['internal_observations_read'],'Unqualified experiment build')
    check_records(receipt['dependencies'])
    # Operator-only comparisons are appended separately before this stage.
    if (OUT/'mapping/operator_replay_receipt.json').exists():
        mapping=read(OUT/'mapping/operator_replay_receipt.json');require(mapping['passed'],'Mapping replay incomplete')
        check_records(mapping['dependencies']);cases=receipt['cases']+mapping['cases']
    else:raise ValueError('Complete the sealed operator-only evaluation before scoring any family')
    b=load_baseline();q=b['qualified'];gamma=b['gamma']
    obs_path=ROOT/'output/nygrid_2025_inputs/load_source/interface_wide.csv'
    observations=pd.read_csv(obs_path,usecols=['timestamp_utc']+NAMES)
    require(np.array_equal(observations.timestamp_utc.astype(str),b['times']),'Score clock differs')
    y=observations[NAMES].to_numpy(float);require(np.isfinite(y[q]).all(),'Missing qualified internal observation')
    months=pd.to_datetime(b['times'],utc=True).tz_convert('America/New_York').month.to_numpy()
    base=np.load(OUT/'replay/baseline.npz',allow_pickle=False)['interface_pf']/gamma
    annual=[];monthly=[]
    for c in cases:
        path=ROOT/c['file'];require(sha(path)==c['sha256'],'Experiment output changed before scoring')
        with np.load(path,allow_pickle=False) as d:
            require(np.array_equal(d['qualified'],q),'A comparison dropped fixed hours')
            require(np.array_equal(d['timestamp_utc'].astype(str),b['times']) and float(d['gamma'])==gamma,'Scoring axes differ')
            prediction=d['interface_pf']/gamma
        for month in range(13):
            use=q if month==0 else q&(months==month)
            for j,name in enumerate(NAMES):
                e=prediction[use,j]-y[use,j];old=base[use,j]-y[use,j];change=prediction[use,j]-base[use,j]
                row=dict(scenario=c['name'],family=c['family'],interface=name,month=month,hours=int(use.sum()),
                    mae_public_mw=float(abs(e).mean()),rmse_public_mw=float(np.sqrt(np.mean(e**2))),bias_public_mw=float(e.mean()),
                    wape_percent=float(100*abs(e).sum()/abs(y[use,j]).sum()),
                    mae_change_from_baseline_public_mw=float(abs(e).mean()-abs(old).mean()),
                    prediction_change_mean_public_mw=float(change.mean()),prediction_change_mae_public_mw=float(abs(change).mean()),
                    prediction_change_max_public_mw=float(abs(change).max()),internal_observations_used_for_fit=False)
                (annual if month==0 else monthly).append(row)
    folder=OUT/'comparison';folder.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(annual).to_csv(folder/'annual_metrics.csv',index=False,lineterminator='\n')
    pd.DataFrame(monthly).to_csv(folder/'monthly_metrics.csv',index=False,lineterminator='\n')
    proof=dict(passed=True,scenarios=len(cases),fixed_hours=int(q.sum()),annual_rows=len(annual),monthly_rows=len(monthly),
        internal_observations_posthoc_only=True,no_infeasible_literal_hypothesis_scored=True,
        dependencies=[record(p) for p in [obs_path,OUT/'replay/replay_receipt.json',OUT/'mapping/operator_replay_receipt.json',Path(__file__)]],
        outputs=[record(folder/p) for p in ['annual_metrics.csv','monthly_metrics.csv']])
    atomic_json(folder/'scoring_receipt.json',proof)
    print(pd.DataFrame(annual).query("interface in ['DYSINGER EAST','WEST CENTRAL']")[['scenario','interface','mae_public_mw','wape_percent']].to_string(index=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--score-only',action='store_true');a=p.parse_args()
    score() if a.score_only else build()
