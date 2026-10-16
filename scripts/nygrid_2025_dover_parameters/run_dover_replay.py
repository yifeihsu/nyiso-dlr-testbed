"""Apply Dover line/PAR parameters with explicit neutral or P34-conditioned states.

The external posted bank-flow convention is inherited, explicitly qualified,
and never used to estimate R/X. Internal interface observations enter only the
separate --score-only step. All previous operating inputs remain frozen.
"""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
import pandas as pd
from scipy.io import loadmat,savemat
from scipy.linalg import lu_solve
from scipy.optimize import lsq_linear
from build_dover_network import ROOT,OUT,PARENT,PAR_ROWS,SCRIPTS,sha,record,dump,require,maxabs

sys.path.insert(0,str(ROOT/'scripts/nygrid_2025_line_parameters'))
import run_parameter_replay as previous
network=previous.network;predict=previous.predict;make_controlled_case=previous.make_controlled_case
NAMES=previous.NAMES
FOLDER=OUT/'replay'
CUTOVER='2025-12-20T04:00:00Z'
SCENARIOS=[('prior_line_parameters','prior',None)] + [
    (mode+'_'+family,mode,family) for mode in ['neutral','bounded'] for family in ['x_nominal','x_low','x_high']
    ]+[('exact_tracking_x_nominal','exact','x_nominal')]


def verify_records(rows):
    require(bool(rows),'Empty dependency manifest')
    if isinstance(rows,dict):rows=[dict(path=p,sha256=h) for p,h in rows.items()]
    for row in rows:require(sha(ROOT/row['path'])==row['sha256'],'Changed dependency: '+row['path'])


def inputs():
    b=previous.contract.load_baseline()
    sourcefolder=OUT/'local_audit';sourceproof=json.loads((sourcefolder/'Dover_P34_input_receipt.json').read_text())
    independent=json.loads((sourcefolder/'Dover_P34_independent_validation.json').read_text())
    require(sourceproof['passed'] and independent['passed'] and sourceproof['no_internal_interface_observations_read'],
            'Dover source inputs lack independent validation')
    verify_records(sourceproof['dependencies'])
    for p,h in sourceproof['outputs'].items():require(sha(sourcefolder/p)==h,'Changed compiled Dover source: '+p)
    d=np.load(sourcefolder/'Dover_P34_inputs.npz',allow_pickle=False)
    times=b['times'];q=b['qualified'];gamma=b['gamma']
    require(np.array_equal(d['hour_index'],np.arange(1,8761)) and np.array_equal(d['timestamp_utc'],times)
        and np.array_equal(d['ptids'],[625149,625150]) and float(d['gamma'])==gamma,'Dover input axes/scale differ')
    post=times>=CUTOVER
    require(np.array_equal(post,d['post_full_service']) and np.array_equal(q,d['prior_common_comparison_mask']),
        'Dover full-service boundary/cohort changed')
    require(np.all(d['post_full_service_source_qualified'][q&post]),'Missing Dover source in fixed comparison cohort')
    require(int((q&post).sum())==287 and int(q.sum())==8651,'Unexpected fixed replay cohort')
    require(not bool(d['pre_service_zero_means_zero_intertie_flow']) and not bool(d['observations_used_to_estimate_impedance']),
        'Source no-fit/bypass qualification lost')
    target=np.asarray(d['forward_NY_to_CT_model_mw'])
    require(np.allclose(target[q&post],-gamma*d['raw_posted_hourly_values'][q&post],rtol=0,atol=1e-12),
        'Dover source sign or single power scaling changed')
    require(np.all(abs(target[q&post])<=750*gamma+1e-9)
        and np.all(d['necessary_P_only_screen'][q&post]),'Per-bank numeric P-only screen failed')
    pd0=np.pad(b['data']['bus_pd'],((0,0),(0,8)))
    qd0=np.pad(b['data']['bus_qd'],((0,0),(0,8)))
    pg=np.asarray(b['dispatch']['gen_pg'])
    dc=np.column_stack([b['data']['dc_pf'],b['par']['observed_model_mw']])
    return b,d,q,post,target,pg,pd0,qd0,dc


def fresh_parent(b,q,pg,pd0,dc):
    model=loadmat(PARENT/'network_cases.mat',simplify_cells=True)
    states=np.asarray(b['baseline']['network_state_ids']).astype(str)
    angle=np.full((8760,148),np.nan);flow=np.full((8760,274),np.nan);ifs=np.full((8760,7),np.nan)
    residual=np.full(8760,np.nan)
    for state in sorted(set(states)):
        ix=np.flatnonzero(q&(states==state))
        if not len(ix):continue
        case=make_controlled_case(model[state],b['register'].bus_id.to_numpy(int),dc[ix[0],4:],b['par']['p_only_limit_model_mw'])
        r=predict(network(case),pd0[ix],pg[ix],dc[ix]);va=r['angle_deg']
        ref=np.asarray(b['data']['reference_bus'],int)[ix]-1;va-=va[np.arange(len(ix)),ref][:,None]
        rec=model['recovery'][state.removesuffix('_case')]
        angle[ix]=va;flow[ix]=r['flow'];ifs[ix]=np.deg2rad(va)@rec['interface_angle_matrix'].T+rec['interface_flow_offset']
        residual[ix]=r['nodal_residual_mw']
        require(maxabs(r['result_pg']-pg[ix])<1e-7,'Parent reconstruction altered frozen PG')
    saved_path=ROOT/'output/nygrid_2025_line_parameters/replay/engineering_nominal.npz'
    with np.load(saved_path,allow_pickle=False) as old:
        require(np.array_equal(old['qualified'],q) and maxabs(angle[q]-old['bus_va'][q])<1e-7
            and maxabs(ifs[q]-old['interface_pf'][q])<1e-7,'Fresh parent differs from prior sealed case')
    return dict(bus_va=angle,branch_pf=flow,interface_pf=ifs,nodal_residual_mw=residual),states


def post_solution(b,model,ix,target,pg,pd0,dc,mode,ambiguous_zero_mode):
    case=make_controlled_case(model['slim_case'],b['register'].bus_id.to_numpy(int),dc[ix[0],4:],b['par']['p_only_limit_model_mw'])
    net=network(case);rec=model['recovery']
    r=predict(net,pd0[ix],pg[ix],dc[ix]);theta0=np.deg2rad(r['angle_deg'])
    require(maxabs(net['phase_branch'])==0,'Uniform gamma angle interpretation requires zero pre-existing fixed phase')
    G=np.asarray(rec['reduced_phase_bus_basis'])
    theta_response=np.zeros((148,2))
    theta_response[net['nonref']]=-lu_solve(net['lu'],G[net['nonref']])
    fullPAR_H=np.asarray(rec['branch_angle_matrix'])[PAR_ROWS]
    fullPAR_J=np.asarray(rec['branch_flow_phase_basis'])[PAR_ROWS]
    p0=theta0@fullPAR_H.T+np.asarray(rec['branch_flow_offset'])[PAR_ROWS]
    response=fullPAR_H@theta_response+fullPAR_J
    condition=float(np.linalg.cond(response));require(np.isfinite(condition) and condition<1e8,'Dover bank controls are not independently observable in this network')
    require(mode in ['neutral','bounded','exact'],'Unknown operating assumption')
    desired=np.linalg.solve(response,(target[ix]-p0).T).T
    limit=b['gamma']*np.deg2rad(40.)
    psi=np.zeros((len(ix),2));saturated=np.zeros(len(ix),bool)
    if mode=='exact':
        psi=desired.copy() # diagnostic only; no hardware feasibility claim
    elif mode=='bounded':
        for j in np.flatnonzero(~ambiguous_zero_mode):
            if np.all(abs(desired[j])<=limit):
                psi[j]=desired[j]
            else:
                fit=lsq_linear(response,target[ix[j]]-p0[j],bounds=(-limit,limit),method='bvls',tol=1e-12)
                require(fit.success,'Bounded external-control tracking failed')
                psi[j]=fit.x;saturated[j]=True
        # Both-native-zero bank channels do not establish zero total intertie
        # flow or bypass position. Keep normal topology with a flagged neutral
        # assumption in those hours; never force their intertie transfer to0.
        require(maxabs(psi[ambiguous_zero_mode])==0,'Unknown zero-channel mode was forced to a flow target')
        require(maxabs(psi)<=limit+1e-12,'Bounded controller exceeded its declared model-angle limit')
    theta=theta0+psi@theta_response.T
    ref=np.asarray(b['data']['reference_bus'],int)[ix]-1;theta-=theta[np.arange(len(ix)),ref][:,None]
    phase_branch_basis=-(net['base']*net['b'])[:,None]*rec['slim_shift_phase_basis']
    require(maxabs(net['incidence'].T@phase_branch_basis-G)<1e-8,'Condensed phase-injection basis differs')
    flows=(theta@net['incidence'].T)*(net['base']*net['b'])+net['phase_branch']+psi@phase_branch_basis.T
    injection=pg[ix]@net['G']-pd0[ix]-net['bus'][:,4]+dc[ix]@net['D']
    residual=np.max(abs(flows@net['incidence']-injection),axis=1)
    fulltheta=theta@rec['angle_lift'].T+rec['angle_offset']+psi@rec['angle_phase_basis'].T
    fullflow=theta@rec['branch_angle_matrix'].T+rec['branch_flow_offset']+psi@rec['branch_flow_phase_basis'].T
    fullflow[:,210]=0 # original Ontario equivalent replaced by its two retained controls
    bank=fullflow[:,PAR_ROWS]
    require(maxabs(rec['full_interface_branch_matrix'][:,210])==0,'Ontario substitution affects an inherited interface expression')
    ifs=theta@rec['interface_angle_matrix'].T+rec['interface_flow_offset']+psi@rec['interface_phase_basis'].T
    require(maxabs(ifs-fullflow@rec['full_interface_branch_matrix'].T)<1e-8,'Dover interface phase recovery failed')
    require(float(residual.max())<1e-7,'Dover phase reconstruction violated frozen-input KCL')
    targeterror=maxabs(bank-target[ix])
    if mode=='exact':require(targeterror<1e-7,'Exact diagnostic bank targets did not close')
    if mode in ['neutral','bounded']:
        require(np.all(abs(bank)<=750*b['gamma']+1e-8),'Modeled bank exceeds the necessary per-bank numeric P screen')
    return dict(bus_va=np.rad2deg(theta),branch_pf=flows,interface_pf=ifs,nodal_residual_mw=residual,
        full_bus_va=np.rad2deg(fulltheta),full_branch_pf=fullflow,bank_flow_model_mw=bank,
        bank_shift_model_deg=np.rad2deg(psi),bank_shift_unscaled_proxy_deg=np.rad2deg(psi)/b['gamma'],
        phase_radians=psi,bank_target_error_model_mw=targeterror,
        maximum_known_mode_tracking_residual_model_mw=maxabs((bank-target[ix])[~ambiguous_zero_mode]),
        phase_bound_active=saturated,ambiguous_zero_mode=ambiguous_zero_mode,
        exact_required_model_shift_deg=np.rad2deg(desired),
        control_response_condition_number=condition)


def build():
    FOLDER.mkdir(parents=True,exist_ok=True)
    proof=json.loads((OUT/'network/network_receipt.json').read_text());require(proof['passed'],'Unqualified Dover network')
    verify_records(proof['dependencies']);verify_records(proof['scenarios'])
    b,d,q,post,target,pg,pd0,qd0,dc=inputs();ix=np.flatnonzero(q&post)
    ambiguous=np.all(d['native_max_abs_posted_value'][ix]==0,axis=1)
    require(int(ambiguous.sum())==18,'Review changed Dover zero-channel operating-mode evidence')
    baseline,states=fresh_parent(b,q,pg,pd0,dc)
    require(np.all(states[ix]=='refined_2025_case'),'Post-cutover hours have an unexpected prior topology state')
    samples=[int(ix[0]),int(ix[len(ix)//2]),int(ix[-1])]
    sums=target[ix].sum(axis=1);samples+= [int(ix[np.argmin(sums)]),int(ix[np.argmax(sums)]),int(ix[np.argmin(abs(sums))])]
    samples=sorted(set(samples)) # extrema of external inputs, never internal-error selection
    fixtures=[];results=[];control_rows=[];operating={};deps=list(b['paths'])
    deps += [PARENT/'network_cases.mat',ROOT/'output/nygrid_2025_line_parameters/replay/engineering_nominal.npz',
        OUT/'network/network_receipt.json',OUT/'local_audit/Dover_P34_inputs.npz',
        OUT/'local_audit/Dover_P34_input_receipt.json',OUT/'local_audit/Dover_P34_independent_validation.json',
        Path(__file__),SCRIPTS/'build_dover_network.py',ROOT/'scripts/nygrid_2025_line_parameters/run_parameter_replay.py']
    models={r['scenario']:loadmat(ROOT/r['path'],simplify_cells=True) for r in proof['scenarios']}
    for r in proof['scenarios']:deps.append(ROOT/r['path'])
    coverage_probe=post_solution(b,models['x_nominal'],ix,target,pg,pd0,dc,'bounded',ambiguous)
    bound_indices=np.flatnonzero(coverage_probe['phase_bound_active'])
    if len(bound_indices):samples.append(int(ix[bound_indices[0]]))
    known=np.flatnonzero(~ambiguous)
    worst=known[np.argmax(np.max(abs(coverage_probe['exact_required_model_shift_deg'][known]),axis=1))]
    samples=sorted(set(samples+[int(ix[worst])]))
    for name,mode,family in SCENARIOS:
        result={k:v.copy() for k,v in baseline.items()}
        modelshift=np.full((8760,2),np.nan);proxyshift=np.full((8760,2),np.nan);bankflow=np.full((8760,2),np.nan)
        postdata=None
        if mode!='prior':
            model=models[family]
            require(model['metadata']['valid_from_utc']==CUTOVER,'Dover template effective interval differs')
            postdata=post_solution(b,model,ix,target,pg,pd0,dc,mode,ambiguous)
            for field in result:result[field][ix]=postdata[field]
            modelshift[ix]=postdata['bank_shift_model_deg'];proxyshift[ix]=postdata['bank_shift_unscaled_proxy_deg'];bankflow[ix]=postdata['bank_flow_model_mw']
            require(np.array_equal(result['bus_va'][q&~post],baseline['bus_va'][q&~post])
                and np.array_equal(result['branch_pf'][q&~post],baseline['branch_pf'][q&~post]),'Pre-cutover model changed')
            for h in samples:
                j=int(np.flatnonzero(ix==h)[0])
                fixtures.append(dict(scenario=name,mode=mode,impedance=family,hour_index=h+1,
                    gen_pg=pg[h],bus_pd=pd0[h],bus_qd=qd0[h],dc_pf=dc[h],
                    bus_va=result['bus_va'][h],branch_pf=result['branch_pf'][h],interface_pf=result['interface_pf'][h],
                    full_bus_va=postdata['full_bus_va'][j],full_branch_pf=postdata['full_branch_pf'][j],
                    bank_shift_model_deg=modelshift[h],bank_flow_model_mw=bankflow[h],
                    ambiguous_zero_mode=bool(ambiguous[j]),phase_bound_active=bool(postdata['phase_bound_active'][j])))
            for jj,h in enumerate(ix):
                for j,ptid in enumerate([625149,625150]):
                    control_rows.append(dict(scenario=name,hour_index=h+1,timestamp_utc=b['times'][h],ptid=ptid,
                        mode=mode,bank_flow_model_mw=bankflow[h,j],P34_forward_target_model_mw=target[h,j],
                        bank_shift_model_deg=modelshift[h,j],uniform_power_unscaled_angle_proxy_deg=proxyshift[h,j],
                        proxy_within_assumed_40deg=abs(proxyshift[h,j])<=40.,actual_tap_observed=False,
                        ambiguous_zero_native_mode=bool(ambiguous[jj]),
                        neutral_fallback=bool(mode=='bounded' and ambiguous[jj]),
                        phase_bound_active=bool(postdata['phase_bound_active'][jj]),
                        raw_target_preserved=True,tracking_residual_model_mw=bankflow[h,j]-target[h,j],
                        phase_derived_from_internal_interface_observation=False))
        path=FOLDER/(name+'.npz')
        np.savez_compressed(path,hour_index=np.arange(1,8761),timestamp_utc=b['times'],qualified=q,
            post_full_service=post,network_state_ids=states,gamma=b['gamma'],
            bus_va=result['bus_va'],interface_pf=result['interface_pf'],nodal_residual_mw=result['nodal_residual_mw'],
            bank_shift_model_deg=modelshift,bank_shift_unscaled_proxy_deg=proxyshift,bank_flow_model_mw=bankflow)
        item=dict(scenario=name,mode=mode,impedance=family,path=path.relative_to(ROOT).as_posix(),sha256=sha(path),
            matched_annual_hours=int(q.sum()),new_Dover_applied_hours=0 if mode=='prior' else len(ix),
            max_nodal_residual_model_mw=float(np.nanmax(result['nodal_residual_mw'])),
            max_change_from_parent_public_mw=np.max(abs(result['interface_pf'][q]-baseline['interface_pf'][q])/b['gamma'],axis=0).tolist())
        if postdata:
            item.update(bank_target_error_model_mw=postdata['bank_target_error_model_mw'],
                control_response_condition_number=postdata['control_response_condition_number'],
                target_tracking_hours=269 if mode=='bounded' else 287 if mode=='exact' else 0,
                ambiguous_zero_mode_hours=18,neutral_fallback_hours=18 if mode=='bounded' else 0,
                phase_bound_active_hours=int(postdata['phase_bound_active'].sum()),
                maximum_known_mode_tracking_residual_model_mw=postdata['maximum_known_mode_tracking_residual_model_mw'],
                angle_proxy_exceeds_40deg_hours=int(np.any(abs(proxyshift[ix])>40.+1e-8,axis=1).sum()),
                maximum_abs_model_shift_deg=maxabs(modelshift[ix]),maximum_abs_unscaled_angle_proxy_deg=maxabs(proxyshift[ix]),
                actual_hardware_tap_trajectory_established=False)
            active_mask=np.zeros(8760,bool);active_mask[ix]=postdata['phase_bound_active']
            fallback=np.zeros(8760,bool);fallback[ix]=ambiguous if mode=='bounded' else False
            unknown=np.zeros(8760,bool);unknown[ix]=ambiguous
            operating[name]=dict(bank_shift_model_deg=modelshift,bank_flow_model_mw=bankflow,
                phase_bound_active=active_mask,neutral_fallback=fallback,ambiguous_zero_native_mode=unknown,
                model_angle_limit_degree=40*b['gamma'],mode=mode,impedance=family)
        results.append(item);print(name+': complete '+str(q.sum())+' hours; post-Dover '+str(0 if mode=='prior' else len(ix)),flush=True)
    pd.DataFrame(control_rows).to_csv(FOLDER/'Dover_bank_states.csv',index=False,lineterminator='\n')
    savemat(FOLDER/'matlab_fixtures.mat',dict(fixtures=np.asarray(fixtures,dtype=object),gamma=b['gamma']),do_compression=True)
    savemat(FOLDER/'operating_states.mat',dict(hour_index=np.arange(1,8761),timestamp_utc=b['times'].astype(object),
        qualified=q,post_full_service=post,gamma=b['gamma'],controls=operating,
        raw_posted_hourly_values=d['raw_posted_hourly_values'],forward_NY_to_CT_model_mw=target,
        cutover_utc=CUTOVER,actual_physical_taps_observed=False,
        P34_numeric_as_MW_convention_independently_verified=False),do_compression=True,long_field_names=True)
    dump(FOLDER/'replay_receipt.json',dict(passed=True,preferred_scenario='bounded_x_nominal',
        internal_interface_observations_read=False,impedances_not_estimated_from_flows=True,
        external_P34_posted_numeric_convention_conditional=True,factory_R_X_or_taps_certified=False,
        fixed_annual_cohort=8651,post_cutover_source_hours=len(ix),new_source_cohort_loss=0,
        cutover_utc=CUTOVER,pre_cutover_parent_preserved_exactly=True,original_six_transfers_and_dispatch_preserved=True,
        bounded_controller_policy='box-constrained external-target tracking;rawtargets unchanged;residuals retained;no internal-interface fitting',
        zero_channel_policy='18 ambiguous hours retain normal topology with explicit neutral-phase assumption;no bypass-state or zero-intertie inference',
        model_angle_limit_policy='40deg times gamma;uniform-power-scaled coarse-network assumption,not measured physical tap',
        exact_tracking_is_diagnostic_only=True,
        scenarios=results,fixture_hours=[h+1 for h in samples],fixture_file=record(FOLDER/'matlab_fixtures.mat'),
        operating_state_file=record(FOLDER/'operating_states.mat'),
        bank_states_file=record(FOLDER/'Dover_bank_states.csv'),dependencies=[record(p) for p in dict.fromkeys(deps)]))


def score():
    receipt=json.loads((FOLDER/'replay_receipt.json').read_text());require(receipt['passed'] and not receipt['internal_interface_observations_read'],'Unsealed replay')
    verify_records(receipt['dependencies']);verify_records(receipt['scenarios'])
    b=previous.contract.load_baseline();q=b['qualified'];post=b['times']>=CUTOVER;gamma=b['gamma']
    observations=ROOT/'output/nygrid_2025_inputs/load_source/interface_wide.csv'
    obs=pd.read_csv(observations,usecols=['timestamp_utc']+NAMES)
    require(np.array_equal(obs.timestamp_utc.to_numpy(str),b['times']),'Observation time axis changed')
    y=obs[NAMES].to_numpy(float);require(np.isfinite(y[q]).all(),'Missing comparison observation')
    months=pd.to_datetime(b['times'],utc=True).tz_convert('America/New_York').month.to_numpy()
    with np.load(FOLDER/'prior_line_parameters.npz',allow_pickle=False) as p:base=p['interface_pf']/gamma
    rows=[];deps=[observations,FOLDER/'replay_receipt.json',Path(__file__)]
    for item in receipt['scenarios']:
        path=ROOT/item['path'];deps.append(path)
        with np.load(path,allow_pickle=False) as d:
            require(np.array_equal(d['qualified'],q) and np.array_equal(d['timestamp_utc'],b['times']) and float(d['gamma'])==gamma,'Scoring cohort/scale changed')
            prediction=d['interface_pf']/gamma
        periods=[('annual',q)]+[(f'month_{month:02}',q&(months==month)) for month in range(1,13)]+[('post_Dover_full_service',q&post)]
        for period,use in periods:
            for j,name in enumerate(NAMES):
                e=prediction[use,j]-y[use,j];old=base[use,j]-y[use,j]
                rows.append(dict(scenario=item['scenario'],period=period,interface=name,hours=int(use.sum()),
                    mae_public_mw=float(abs(e).mean()),rmse_public_mw=float(np.sqrt(np.mean(e**2))),bias_public_mw=float(e.mean()),
                    wape_percent=float(100*abs(e).sum()/abs(y[use,j]).sum()),mae_change_public_mw=float(abs(e).mean()-abs(old).mean()),
                    internal_observations_used_for_parameter_fit=False,external_flow_conditioning=item['mode'] in ['bounded','exact']))
    folder=OUT/'comparison';folder.mkdir(parents=True,exist_ok=True);df=pd.DataFrame(rows)
    for label,part in [('annual',df[df.period=='annual']),('monthly',df[df.period.str.startswith('month_')]),('post_cutover',df[df.period=='post_Dover_full_service'])]:
        part.to_csv(folder/(label+'_metrics.csv'),index=False,lineterminator='\n')
    dump(folder/'scoring_receipt.json',dict(passed=True,scenarios=len(receipt['scenarios']),total_rows=len(df),
        internal_observations_posthoc_only=True,source_parameters_frozen_before_scoring=True,
        dependencies=[record(p) for p in deps],outputs=[record(folder/(label+'_metrics.csv')) for label in ['annual','monthly','post_cutover']]))
    print(df[(df.scenario.isin(['prior_line_parameters','neutral_x_nominal','bounded_x_nominal']))&(df.period!='annual')&
             (df.period=='post_Dover_full_service')][['scenario','interface','mae_public_mw','wape_percent']].to_string(index=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--score-only',action='store_true')
    args=parser.parse_args();score() if args.score_only else build()
