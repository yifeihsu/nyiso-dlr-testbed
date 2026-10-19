"""Freeze post-repair evidence and reconstruct current/previous cut inputs."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_postrepair_diagnosis'
CURRENT=ROOT/'output/nygrid_2025_moses_repair'
OLD=ROOT/'output/nygrid_2025_physical_repair'


def record(p):
    with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=p.relative_to(ROOT).as_posix(),sha256=digest,bytes=p.stat().st_size)


def inputs(base,register):
    model=loadmat(base/'model/latest_model.mat',simplify_cells=True)['model']
    gamma=float(model['scale_factor_gamma']);p=model['loss_static'][0];t=model['templates'][0]
    groups=dict(zip(t['bus'][:,0].astype(int),np.asarray(p['bus_group'],int)))
    gg=np.array([groups[int(b)] for b in model['generator_bus_ids']]);native=np.asarray(p['native'],bool)
    reg=pd.read_csv(register);assert len(reg)==len(native)
    st=pd.to_numeric(reg.plant_id,errors='coerce').eq(2694).to_numpy()&native
    hy=reg.fuel_category.eq('Hydro').to_numpy()&native
    wind=reg.fuel_category.eq('Wind').to_numpy()&native
    d=native&(gg==4);other=d&~st
    names=['StLawrence','other_D_hydro','D_wind','other_D_nonhydro','native_D','HQ','PV20','PAR1','PAR2','gross_D','StLawrence_Pmax']
    names+=['native_'+z for z in 'ABCDEFGHIJK']
    names=list(dict.fromkeys(names))
    frame=pd.DataFrame(np.nan,index=np.arange(8760),columns=names)
    for off,name in [(0,'profiles_h0001_4380.mat'),(4380,'profiles_h4381_8760.mat')]:
        prof=loadmat(base/'model'/name,simplify_cells=True)['profiles'];pg=prof['generator_PG_MW']/gamma;ix=np.arange(off,off+4380)
        masks={'StLawrence':st,'other_D_hydro':other&hy,'D_wind':d&wind,
               'other_D_nonhydro':other&~hy&~wind,'native_D':d}
        masks.update({'native_'+z:native&(gg==i+1) for i,z in enumerate('ABCDEFGHIJK')})
        for key,mask in masks.items():frame.loc[ix,key]=pg[:,mask].sum(axis=1)
        frame.loc[ix,'HQ']=pg[:,int(p['HQ'])-1]
        frame.loc[ix,'PV20']=pg[:,1465] if len(native)==1466 else 0.
        frame.loc[ix,'PAR1']=prof['fixed_transfer_PF_MW'][:,4]/gamma
        frame.loc[ix,'PAR2']=prof['fixed_transfer_PF_MW'][:,5]/gamma
        frame.loc[ix,'gross_D']=prof['bus_PD_MW'][:,np.array([groups[i]==4 for i in range(1,141)])].sum(axis=1)/gamma
        frame.loc[ix,'StLawrence_Pmax']=prof['generator_Pmax_MW'][:,st].sum(axis=1)/gamma
    return frame,model


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    pointer=ROOT/'deliverables/CURRENT_NYGRID_MODEL.json'
    current_pointer=json.loads(pointer.read_text())
    files=[pointer]
    files += [ROOT/r['path'] for r in current_pointer.values() if isinstance(r,dict) and 'path' in r]
    for base,run in [(CURRENT,'moses_repair_v1'),(OLD,'physical_repair_v1')]:
        files +=[base/'model'/n for n in ['latest_model.mat','model_receipt.json','profiles_h0001_4380.mat','profiles_h4381_8760.mat']]
        files +=[base/'annual'/run/'comparison'/n for n in ['comparison_arrays.npz','public_interface_metrics.csv','scoring_receipt.json']]
    files+=sorted((ROOT/'scripts/nygrid_2025_moses_repair/delivery/runtime').rglob('*.m'))
    guard=dict(created_utc=datetime.now(timezone.utc).isoformat(),baseline_HEAD=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
               files=[record(p) for p in sorted(set(files))])
    gp=OUT/'source_guard.json'
    if gp.exists():assert json.loads(gp.read_text())['files']==guard['files']
    else:gp.write_text(json.dumps(guard,indent=2)+'\n',encoding='utf-8')
    current,model=inputs(CURRENT,CURRENT/'model/model_generator_register.csv')
    previous,_=inputs(OLD,ROOT/'output/nygrid_2025_western_audit/corrected/model_generator_register.csv')
    a=np.load(CURRENT/'annual/moses_repair_v1/comparison/comparison_arrays.npz',allow_pickle=False)
    q=a['paired_qualified'];assert q.sum()==8651 and np.array_equal(q,a['source_qualified'])
    time=pd.DatetimeIndex(pd.to_datetime(a['timestamp_utc'],utc=True));local=time.tz_convert('America/New_York')
    frame=pd.DataFrame(dict(hour_index=a['hour_index'],timestamp_utc=a['timestamp_utc'],month_local=local.month,
                            hour_local=local.hour,qualified=q,state_index=a['topology_state_index']))
    for prefix,src in [('current_',current),('previous_',previous)]:
        for name in src:frame[prefix+name+'_MW']=src[name].to_numpy()
    mapping={'Moses':'MOSES SOUTH','TotalEast':'TOTAL EAST','CentralEast':'CENTRAL EAST - VC'}
    for label,name in mapping.items():
        j=list(a['interface_names']).index(name)
        frame[label+'_observed_MW']=a['observed'][:,j]
        for prefix,key in [('current_','candidate_'),('previous_','current_baseline_')]:
            primary=a[key+'legacy_signed_literal_from'][:,j]
            midpoint=(a[key+'oriented_source_side'][:,j]+a[key+'oriented_target_side'][:,j])/2
            frame[prefix+label+'_primary_MW']=primary
            frame[prefix+label+'_midpoint_MW']=midpoint
            frame[prefix+label+'_terminal_MW']=primary-midpoint
            frame[prefix+label+'_residual_MW']=primary-frame[label+'_observed_MW']
    for prefix in ['current_','previous_']:
        balance=frame[prefix+'native_D_MW']+frame[prefix+'HQ_MW']+frame[prefix+'PV20_MW']+frame[prefix+'PAR1_MW']+frame[prefix+'PAR2_MW']-frame[prefix+'gross_D_MW']
        assert np.max(abs(balance[q]-frame.loc[q,prefix+'Moses_midpoint_MW']))<1e-8
        frame[prefix+'Moses_identity_MW']=balance
        frame[prefix+'parent224_primary_MW']=frame[prefix+'TotalEast_primary_MW']-frame[prefix+'CentralEast_primary_MW']
    frame['delta_native_D_MW']=frame.current_native_D_MW-frame.previous_native_D_MW
    frame['delta_StLawrence_MW']=frame.current_StLawrence_MW-frame.previous_StLawrence_MW
    frame['delta_other_D_MW']=frame.delta_native_D_MW-frame.delta_StLawrence_MW
    frame['delta_Moses_terminal_MW']=frame.current_Moses_terminal_MW-frame.previous_Moses_terminal_MW
    frame['delta_Moses_primary_MW']=frame.current_Moses_primary_MW-frame.previous_Moses_primary_MW
    closure=frame.delta_Moses_primary_MW-frame.delta_native_D_MW-frame.current_PV20_MW-frame.delta_Moses_terminal_MW
    assert np.max(abs(closure[q]))<1e-8
    frame.to_csv(OUT/'hourly_evidence.csv',index=False)
    np.savez_compressed(OUT/'interface_evidence.npz',**{k:a[k] for k in a.files})
    receipt=dict(passed=True,qualified_hours=int(q.sum()),physical_hours=len(frame),public_power_units=True,
                 current_Moses_cut_identity_max_error_MW=float(np.max(abs(frame.loc[q,'current_Moses_identity_MW']-frame.loc[q,'current_Moses_midpoint_MW']))),
                 changed_Moses_flow_reconciles_nativeD_PV20_and_terminal_max_error_MW=float(np.max(abs(closure[q]))),
                 TotalEast_operator_identity='TotalEast = CentralEast + original parent224 signed-from flow; physical-meter equivalence not certified.',
                 mean_Moses_change_components_MW={k:float(frame.loc[q,k].mean()) for k in ['delta_StLawrence_MW','delta_other_D_MW','current_PV20_MW','delta_Moses_terminal_MW','delta_Moses_primary_MW']},
                 source_guard_sha256=record(gp)['sha256'],outputs=[record(OUT/'hourly_evidence.csv'),record(OUT/'interface_evidence.npz')],
                 current_model_map_package_unchanged=True)
    (OUT/'evidence_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt))


if __name__=='__main__':main()
