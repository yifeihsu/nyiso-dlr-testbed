"""Matched annual DC validation; internal observations enter --score-only.

All operating inputs are frozen at the validated all-boundary reconstruction.
No parameter, geometry case or conductor is chosen by comparison scores.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import sys
import numpy as np
import pandas as pd
from scipy.io import loadmat,savemat
from build_estimates import ROOT,OUT,DEST,sha,record,dump,require

sys.path.insert(0,str(ROOT/'scripts/nygrid_2025_par_controls'))
from controlled_equivalent import make_controlled_case
sys.path.insert(0,str(ROOT/'scripts/nygrid_2019'))
from replay_dc import network,predict
spec=importlib.util.spec_from_file_location('frozen_counterfactual_contract',ROOT/'scripts/nygrid_2025_western_counterfactuals/common.py')
contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
NAMES=contract.NAMES
FOLDER=OUT/'replay'
SCENARIOS=['identity_reference','engineering_nominal','geometry_spacing_80pct','geometry_spacing_120pct','ground_image_30ft']


def check_records(rows):
    require(bool(rows),'Empty source proof')
    for row in rows:
        require(sha(ROOT/row['path'])==row['sha256'],'Changed dependency: '+row['path'])


def build():
    FOLDER.mkdir(parents=True,exist_ok=True)
    basis=json.loads((DEST/'engineering_basis.json').read_text())
    require(basis['passed'] and not basis['internal_interface_observations_used'],'Unqualified parameter basis')
    check_records(basis['dependencies']);check_records(basis['outputs'])
    for name in ['parameter_source_review.json','physics_validation.json','estimate_values_validation.json']:
        proof=json.loads((OUT/'validation'/name).read_text())
        require(proof['passed'],'Parameter validation did not pass: '+name)
        if name=='physics_validation.json':
            require(proof['physics_code_sha256']==sha(Path(__file__).with_name('line_physics.py')),
                    'Physics validation is stale')
        else:
            check_records(proof.get('checked_files',proof.get('files',[])))
    b=contract.load_baseline();q=b['qualified'];times=b['times'];gamma=b['gamma']
    states=np.asarray(b['baseline']['network_state_ids']).astype(str)
    pd0=np.pad(b['data']['bus_pd'],((0,0),(0,8)))
    qd0=np.pad(b['data']['bus_qd'],((0,0),(0,8)))
    pg=np.asarray(b['dispatch']['gen_pg'])
    dc=np.column_stack([b['data']['dc_pf'],b['par']['observed_model_mw']])
    require(pg.shape==(8760,1464) and pd0.shape==(8760,148),'Changed operating axes')
    require(np.all(pg[q,:1436]>=b['bounds']['gen_pmin'][q,:1436]-1e-7)
            and np.all(pg[q,:1436]<=b['bounds']['gen_pmax'][q,:1436]+1e-7),'Native bounds changed')
    months=pd.to_datetime(times,utc=True).tz_convert('America/New_York').month.to_numpy()
    samples=sorted(set([int(np.flatnonzero(q&(states==s))[0]) for s in sorted(set(states))]
                      +[int(np.flatnonzero(q&(months==m))[0]) for m in [1,4,7,10]]))
    summaries=[];fixtures=[];baseline=None;full_f84=[];dependencies=list(b['paths'])
    dependencies += [DEST/'engineering_basis.json',Path(__file__),
        ROOT/'scripts/nygrid_2025_par_controls/controlled_equivalent.py',ROOT/'scripts/nygrid_2019/replay_dc.py']
    dependencies += [OUT/'validation'/name for name in ['parameter_source_review.json','physics_validation.json','estimate_values_validation.json']]
    for name in SCENARIOS:
        folder=OUT/'overlays'/name
        proof=json.loads((folder/'overlay_receipt.json').read_text())
        require(proof['passed'] and not proof['observed_interface_flows_used'],'Unqualified overlay')
        for p,h in proof['dependencies'].items():require(sha(ROOT/p)==h,'Changed overlay input: '+p)
        for p,h in proof['outputs'].items():require(sha(folder/p)==h,'Changed overlay output: '+p)
        require(sha(ROOT/'scripts/nygrid_2025_line_parameters/build_parameter_overlay.py')==proof['script_sha256'],'Changed overlay builder')
        model=loadmat(folder/'network_cases.mat',simplify_cells=True)
        full=loadmat(folder/'full191_network_cases.mat',simplify_cells=True)
        angle=np.full((8760,148),np.nan);ifs=np.full((8760,7),np.nan)
        residual=np.full(8760,np.nan);slack=np.full(8760,np.nan);f84=np.full(8760,np.nan)
        changes=np.zeros(7)
        for state in sorted(set(states)):
            ix=np.flatnonzero(q&(states==state))
            if not len(ix):continue
            case=make_controlled_case(model[state],b['register'].bus_id.to_numpy(int),dc[ix[0],4:],b['par']['p_only_limit_model_mw'])
            r=predict(network(case),pd0[ix],pg[ix],dc[ix])
            va=r['angle_deg'];ref=np.asarray(b['data']['reference_bus'],int)[ix]-1
            va-=va[np.arange(len(ix)),ref][:,None]
            rec=model['recovery'][state.removesuffix('_case')]
            angle[ix]=va;ifs[ix]=np.deg2rad(va)@rec['interface_angle_matrix'].T+rec['interface_flow_offset']
            residual[ix]=r['nodal_residual_mw'];slack[ix]=np.max(abs(r['result_pg']-pg[ix]),axis=1)
            theta=np.deg2rad(va)@rec['angle_lift'].T+rec['angle_offset']
            fc=full[state];lookup={int(x):j for j,x in enumerate(fc['bus'][:,0])};line=fc['branch'][390]
            require(tuple(line[:2])==(73,20001),'F84 physical branch identity changed')
            f84[ix]=(theta[:,lookup[73]]-theta[:,lookup[20001]])*float(fc['baseMVA'])/line[3]*line[10]
            for h in samples:
                if h in ix:
                    j=int(np.flatnonzero(ix==h)[0])
                    fixtures.append(dict(name=name,hour_index=h+1,gen_pg=pg[h],bus_pd=pd0[h],bus_qd=qd0[h],
                        bus_va=va[j],branch_pf=r['flow'][j],interface_pf=ifs[h]))
        require(np.nanmax(residual)<1e-7 and np.nanmax(slack)<1e-7,'Power balance or frozen generation failed')
        if name=='identity_reference':
            require(np.max(abs(ifs[q]-b['baseline']['interface_pf'][q]))<1e-7
                and np.max(abs(angle[q]-b['baseline']['bus_va'][q]))<1e-7,'Identity replay differs from frozen parent')
            baseline=ifs.copy()
        changes=np.max(abs(ifs[q]-baseline[q])/gamma,axis=0)
        path=FOLDER/(name+'.npz')
        np.savez_compressed(path,hour_index=np.arange(1,8761),timestamp_utc=times,qualified=q,
            network_state_ids=states,bus_va=angle,interface_pf=ifs,nodal_residual_mw=residual,
            slack_change_mw=slack,F84_line_pf_model_mw=f84,gamma=gamma)
        summaries.append(dict(scenario_name=name,path=path.relative_to(ROOT).as_posix(),sha256=sha(path),
            qualified_hours=int(q.sum()),max_nodal_residual_model_mw=float(np.nanmax(residual)),
            max_slack_change_model_mw=float(np.nanmax(slack)),
            maximum_interface_change_public_equivalent_mw=changes.tolist(),
            max_abs_F84_lossless_active_flow_model_mw=float(np.nanmax(abs(f84))),
            F84_apparent_power_or_actual_ampacity_validated=False))
        dependencies += [folder/'network_cases.mat',folder/'full191_network_cases.mat',folder/'overlay_receipt.json']
        print(name+': solved '+str(q.sum())+' matched hours',flush=True)
    savemat(FOLDER/'matlab_fixtures.mat',dict(fixtures=np.asarray(fixtures,dtype=object),gamma=gamma),do_compression=True)
    dump(FOLDER/'replay_receipt.json',dict(passed=True,internal_interface_observations_read=False,
        fixed_hours=int(q.sum()),inputs_and_all_six_boundary_transfers_preserved=True,
        native_generator_bounds_preserved=True,complete_physical_flowgate_validation=False,
        nominal_parameters_chosen_before_scores=True,scenarios=summaries,fixture_hours=[x+1 for x in samples],
        fixture_file=record(FOLDER/'matlab_fixtures.mat'),dependencies=[record(p) for p in dict.fromkeys(dependencies)]))


def score():
    """Posthoc comparisons only; scores cannot alter the sealed parameters."""
    receipt=json.loads((FOLDER/'replay_receipt.json').read_text())
    require(receipt['passed'] and not receipt['internal_interface_observations_read'],'Unqualified replay')
    check_records(receipt['dependencies'])
    b=contract.load_baseline();q=b['qualified'];gamma=b['gamma']
    obs_path=ROOT/'output/nygrid_2025_inputs/load_source/interface_wide.csv'
    observed=pd.read_csv(obs_path,usecols=['timestamp_utc']+NAMES)
    require(np.array_equal(observed.timestamp_utc.astype(str),b['times']),'Scoring timestamp mismatch')
    y=observed[NAMES].to_numpy(float);require(np.isfinite(y[q]).all(),'Missing matched observation')
    months=pd.to_datetime(b['times'],utc=True).tz_convert('America/New_York').month.to_numpy()
    with np.load(FOLDER/'identity_reference.npz',allow_pickle=False) as d:base=d['interface_pf']/gamma
    annual=[];monthly=[];deps=[obs_path,FOLDER/'replay_receipt.json',Path(__file__)]
    for item in receipt['scenarios']:
        path=ROOT/item['path'];require(sha(path)==item['sha256'],'Changed replay before scoring')
        deps.append(path)
        with np.load(path,allow_pickle=False) as d:
            require(np.array_equal(d['qualified'],q) and np.array_equal(d['timestamp_utc'].astype(str),b['times'])
                    and float(d['gamma'])==gamma,'Scoring axes/cohort/scale changed')
            predicted=d['interface_pf']/gamma
        for month in range(13):
            use=q if month==0 else q&(months==month)
            for j,name in enumerate(NAMES):
                error=predicted[use,j]-y[use,j];previous=base[use,j]-y[use,j]
                change=predicted[use,j]-base[use,j]
                row=dict(scenario=item['scenario_name'],interface=name,month=month,hours=int(use.sum()),
                    mae_public_mw=float(abs(error).mean()),rmse_public_mw=float(np.sqrt(np.mean(error**2))),
                    bias_public_mw=float(error.mean()),wape_percent=float(100*abs(error).sum()/abs(y[use,j]).sum()),
                    mae_change_from_baseline_public_mw=float(abs(error).mean()-abs(previous).mean()),
                    prediction_change_mean_public_mw=float(change.mean()),prediction_change_max_public_mw=float(abs(change).max()),
                    internal_observations_used_for_fit=False,physical_flowgate_certified=False)
                (annual if month==0 else monthly).append(row)
    folder=OUT/'comparison';folder.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(annual).to_csv(folder/'annual_metrics.csv',index=False,lineterminator='\n')
    pd.DataFrame(monthly).to_csv(folder/'monthly_metrics.csv',index=False,lineterminator='\n')
    dump(folder/'scoring_receipt.json',dict(passed=True,internal_observations_posthoc_only=True,
        scenarios=len(receipt['scenarios']),fixed_qualified_hours=int(q.sum()),annual_rows=len(annual),monthly_rows=len(monthly),
        source_nominal_case_not_selected_by_scores=True,dependencies=[record(p) for p in deps],
        outputs=[record(folder/p) for p in ['annual_metrics.csv','monthly_metrics.csv']]))
    print(pd.DataFrame(annual).query("scenario in ['identity_reference','engineering_nominal']")
          [['scenario','interface','mae_public_mw','wape_percent']].to_string(index=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--score-only',action='store_true')
    args=parser.parse_args();score() if args.score_only else build()
