"""Apply sealed western measurement operators to identical baseline flows."""
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from scipy.io import loadmat
from common import FULL,OUT,ROOT,SLIM,atomic_json,check_records,load_baseline,read,record,require,sha
from run_experiments import full_flow

def evaluate():
    b=load_baseline();q=b['qualified']
    receipt=read(OUT/'mapping/mapping_receipt.json')
    require(receipt['passed'],'Incomplete operator source audit')
    check_records(receipt['dependencies'])
    replay=read(OUT/'replay/replay_receipt.json');require(replay['passed'],'Incomplete baseline replay')
    check_records(replay['dependencies'])
    primary=[r for r in replay['cases'] if r['name']=='baseline'];require(len(primary)==1,'Missing unique baseline')
    require(sha(ROOT/primary[0]['file'])==primary[0]['sha256'],'Baseline experiment changed')
    base=np.load(ROOT/primary[0]['file'],allow_pickle=False)
    require(sha(OUT/'mapping/operators.npz')==receipt['operators_sha256'], 'Sealed operator matrices changed')
    require(sha(OUT/'mapping/mapping_plan.json')==receipt['mapping_plan_sha256'], 'Sealed mapping definitions changed')
    operators=np.load(OUT/'mapping/operators.npz',allow_pickle=False)
    model=loadmat(SLIM,simplify_cells=True);full=loadmat(FULL,simplify_cells=True)
    states=np.asarray(base['network_state_ids']).astype(str)
    dc=np.column_stack([b['data']['dc_pf'],b['par']['observed_model_mw']])
    flow=np.full((8760,410),np.nan)
    for state in sorted(set(states)):
        ix=np.flatnonzero(q&(states==state));rec=model['recovery'][state.removesuffix('_case')]
        flow[ix]=full_flow(full[state],rec,base['bus_va'][ix])
    cases=[]
    for item in receipt['scenario_definitions']:
        key=item['key'];dc_key=item['dc_key'];op=operators[key];dop=operators[dc_key]
        require(op.shape==(7,410) and dop.shape==(7,6),'Operator dimensions differ')
        require(np.isfinite(op).all() and np.isfinite(dop).all(),'Operator has unmatched or nonfinite members')
        interface=flow@op.T+dc@dop.T;interface[~q]=np.nan
        name='mapping_'+key;path=OUT/'mapping'/(name+'.npz')
        np.savez_compressed(path,hour_index=np.arange(1,8761),timestamp_utc=b['times'],qualified=q,
            interface_pf=interface,gamma=b['gamma'])
        changed=np.max(abs((interface[q]-base['interface_pf'][q])/b['gamma']),axis=0)
        if key in ['baseline_corrected_full191_operator','independent_zone_cuts']:
            require(np.max(changed)<1e-7,'Equivalent source or cut operator changed baseline flows')
        else:
            require(key=='literal_released_plot_negative_control','An undeclared mapping operator entered the comparison')
            require(np.max(changed[2:])<1e-7,'Western-only mapping test changed another operator')
        cases.append(dict(name=name,family='mapping',file=path.relative_to(ROOT).as_posix(),sha256=sha(path),
            operator_key=key,operator_dc_key=dc_key,qualified_hours=int(q.sum()),
            interpretation='known_bug_negative_control' if key=='literal_released_plot_negative_control' else 'equivalence_check',
            maximum_interface_change_public_mw=changed.tolist(),generation=None,demand=None))
    require(len(cases)==3,'Incomplete sealed mapping family')
    result=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),cases=cases,
        fixed_hour_count=int(q.sum()),identical_injections_network_angles_and_boundary_flows=True,
        physical_as_built_2025_operator_identified=False,internal_observations_read=False,
        dependencies=[record(p) for p in [OUT/'mapping/mapping_receipt.json',OUT/'mapping/operators.npz',
            OUT/'replay/replay_receipt.json',ROOT/primary[0]['file'],SLIM,FULL,Path(__file__),Path(__file__).with_name('run_experiments.py')]])
    atomic_json(OUT/'mapping/operator_replay_receipt.json',result)
    print([(r['name'],r['maximum_interface_change_public_mw'][:2]) for r in cases])

if __name__=='__main__':evaluate()
