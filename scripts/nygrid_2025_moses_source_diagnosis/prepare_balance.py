"""Freeze current Moses source balance, identities and immutable numeric inputs."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_moses_source_diagnosis'
MODEL=ROOT/'output/nygrid_2025_physical_repair/model'
COMP=ROOT/'output/nygrid_2025_physical_repair/annual/physical_repair_v1/comparison'
def rec(p):
    with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':digest}
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source_paths=[MODEL/n for n in ['latest_model.mat','profiles_h0001_4380.mat','profiles_h4381_8760.mat','model_receipt.json']]
    source_paths+=[COMP/n for n in ['comparison_arrays.npz','scoring_receipt.json','public_interface_metrics.csv']]
    regpath=ROOT/'output/nygrid_2025_western_audit/corrected/model_generator_register.csv';source_paths.append(regpath)
    source_paths +=[ROOT/'output/nygrid_2025_inputs/load_source/load_wide.csv',
                   ROOT/'output/nygrid_2025_par_controls/controls/input_receipt.json',
                   ROOT/'output/nygrid_2025_acpf_profile_audit/alignment/interface_operator_terms.csv']
    source_paths+=sorted((ROOT/'scripts/nygrid_2025_physical_repair/delivery/runtime').rglob('*.m'))
    guard={'created_utc':datetime.now(timezone.utc).isoformat(),'baseline_HEAD':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
           'branch':subprocess.check_output(['git','branch','--show-current'],text=True).strip(),'critical_sources':[rec(p) for p in source_paths]}
    guardpath=OUT/'source_guard.json'
    if guardpath.exists():assert json.loads(guardpath.read_text())['critical_sources']==guard['critical_sources'],'Frozen numerical sources changed.'
    else:guardpath.write_text(json.dumps(guard,indent=2)+'\n',encoding='utf-8')
    a=np.load(COMP/'comparison_arrays.npz',allow_pickle=False);model=loadmat(MODEL/'latest_model.mat',simplify_cells=True)['model']
    t=model['templates'][0];p=model['loss_static'][0];gamma=float(a['gamma']);q=a['candidate_qualified'];nh=8760
    assert q.sum()==8651 and a['source_qualified'].sum()==8651
    reg=pd.read_csv(regpath);assert np.array_equal(reg.gen_row,np.arange(1,1465))
    assert np.array_equal(reg.bus_id,t['gen'][:,0])
    group=dict(zip(t['bus'][:,0].astype(int),p['bus_group']));gD=np.array([group[int(b)]==4 for b in t['gen'][:,0]])
    native=np.asarray(p['native'],bool);nativeD=gD&native;HQ=int(p['HQ'])-1;assert gD[HQ] and not native[HQ]
    stl=reg.role.eq('native').to_numpy()&pd.to_numeric(reg.plant_id,errors='coerce').eq(2694).to_numpy();assert stl.sum()==15 and (gD[stl]).all()
    other=nativeD&~stl;busD=np.array([group[i]==4 for i in range(1,141)])
    times=pd.DatetimeIndex(pd.to_datetime(a['timestamp_utc'],utc=True));local=times.tz_convert('America/New_York')
    frame=pd.DataFrame({'hour_index':a['hour_index'],'timestamp_utc':a['timestamp_utc'],'timestamp_local':local.strftime('%Y-%m-%dT%H:%M:%S%z'),
                        'month_local':local.month,'hour_local':local.hour,'state_index':a['topology_state_index'],
                        'source_qualified':a['source_qualified'],'qualified':q})
    names=['StLawrence_PG_MW','StLawrence_Pmin_MW','StLawrence_Pmax_MW','other_D_PG_MW','native_D_PG_MW',
           'HQ_MW','PAR1_MW','PAR2_MW','gross_D_load_MW']
    fuels=sorted(reg.loc[other,'fuel_category'].unique());names +=['other_D_'+str(f).replace(' ','_')+'_MW' for f in fuels]
    for n in names:frame[n]=np.nan
    for filename,off in [('profiles_h0001_4380.mat',0),('profiles_h4381_8760.mat',4380)]:
        prof=loadmat(MODEL/filename,simplify_cells=True)['profiles'];pg=prof['generator_PG_MW'];ix=np.arange(off,off+4380)
        frame.loc[ix,'StLawrence_PG_MW']=pg[:,stl].sum(axis=1)/gamma
        for key,name in [('generator_Pmin_MW','StLawrence_Pmin_MW'),('generator_Pmax_MW','StLawrence_Pmax_MW')]:frame.loc[ix,name]=prof[key][:,stl].sum(axis=1)/gamma
        frame.loc[ix,'other_D_PG_MW']=pg[:,other].sum(axis=1)/gamma;frame.loc[ix,'native_D_PG_MW']=pg[:,nativeD].sum(axis=1)/gamma
        frame.loc[ix,'HQ_MW']=pg[:,HQ]/gamma
        frame.loc[ix,'PAR1_MW']=prof['fixed_transfer_PF_MW'][:,4]/gamma;frame.loc[ix,'PAR2_MW']=prof['fixed_transfer_PF_MW'][:,5]/gamma
        frame.loc[ix,'gross_D_load_MW']=prof['bus_PD_MW'][:,busD].sum(axis=1)/gamma
        for fuel in fuels:
            name='other_D_'+str(fuel).replace(' ','_')+'_MW';mask=other&reg.fuel_category.eq(fuel).to_numpy();frame.loc[ix,name]=pg[:,mask].sum(axis=1)/gamma
    frame['PAR_total_MW']=frame.PAR1_MW+frame.PAR2_MW
    frame['fixed_input_midpoint_MW']=frame.native_D_PG_MW+frame.HQ_MW+frame.PAR_total_MW-frame.gross_D_load_MW
    j=list(a['interface_names']).index('MOSES SOUTH');frame['observed_Moses_MW']=a['observed'][:,j]
    frame['primary_Moses_MW']=a['candidate_legacy_signed_literal_from'][:,j]
    frame['solved_midpoint_MW']=(a['candidate_oriented_source_side'][:,j]+a['candidate_oriented_target_side'][:,j])/2
    frame['terminal_correction_MW']=frame.primary_Moses_MW-frame.solved_midpoint_MW
    frame['residual_primary_MW']=frame.primary_Moses_MW-frame.observed_Moses_MW
    frame['oracle_net_input_adjustment_MW']=-frame.residual_primary_MW
    frame['oracle_StLawrence_hold_other_inputs_and_terminal_MW']=frame.StLawrence_PG_MW+frame.oracle_net_input_adjustment_MW
    for n in ['StLawrence_PG_MW','other_D_PG_MW','HQ_MW','PAR1_MW','PAR2_MW','gross_D_load_MW','observed_Moses_MW']:
        frame[n+'_finite']=np.isfinite(frame[n])
    assert np.max(abs(frame.loc[q,'fixed_input_midpoint_MW']-frame.loc[q,'solved_midpoint_MW']))<1e-7
    assert np.max(abs(frame.loc[q,'native_D_PG_MW']-frame.loc[q,'StLawrence_PG_MW']-frame.loc[q,'other_D_PG_MW']))<1e-8
    assert all(np.isfinite(frame.loc[q,n]).all() for n in names)
    source_load=pd.read_csv(source_paths[8]);assert np.array_equal(source_load.timestamp_utc,a['timestamp_utc'])
    assert np.max(abs(source_load.D-frame.gross_D_load_MW))<1e-8
    frame.to_csv(OUT/'balance_hourly.csv',index=False)
    arrays={c:frame[c].to_numpy() for c in frame.columns if c not in ['timestamp_local','timestamp_utc']}
    arrays.update(timestamp_utc=a['timestamp_utc'],timestamp_local=frame.timestamp_local.to_numpy(dtype=str),gamma=np.array(gamma),
                  all_interface_names=a['interface_names'],all_interface_predictions=a['candidate_legacy_signed_literal_from'],all_interface_observations=a['observed'])
    np.savez_compressed(OUT/'components.npz',**arrays)
    scope=reg[nativeD|np.arange(1464).__eq__(HQ)].copy();scope['StLawrence']=stl[scope.index];scope['HQ_equivalent']=scope.index==HQ
    scope.to_csv(OUT/'D_generator_scope.csv',index=False)
    contract={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'hours':8760,'qualified_hours':8651,'power_units':'public_scale_MW_except_gamma',
        'positive_Moses_direction':'D_to_E','primary_measurement':'sum(frozen coefficient * original parent from-terminal P)',
        'exact_midpoint_identity':'StLawrence + other_D_native + HQ + PAR1 + PAR2 - gross_D_load',
        'primary_identity':'fixed_input_midpoint + signed_terminal_half_loss_correction',
        'maximum_identity_residual_public_MW':float(np.max(abs(frame.loc[q,'fixed_input_midpoint_MW']-frame.loc[q,'solved_midpoint_MW']))),
        'baseline_MAE_public_MW':float(frame.loc[q,'residual_primary_MW'].abs().mean()),
        'baseline_WAPE_percent':float(100*frame.loc[q,'residual_primary_MW'].abs().sum()/frame.loc[q,'observed_Moses_MW'].abs().sum()),
        'counterfactual_policy':'No source or model promotion by residual fit. Source-only alternatives retain independent provenance. Algebraic holding-terminal-loss probes are not fresh AC validation.',
        'oracle_policy':'Residual-implied StLawrence column is conditional diagnostic, not observed generation or a dispatch target.',
        'timing_policy':'All8760physicalUTCslots retained; source masks and equal comparison cohorts required for lags; showallpredeterminedshifts.',
        'defaults_changed':False,'old_artifacts_preserved':True,'sources':[rec(p) for p in source_paths],
        'outputs':[rec(OUT/x) for x in ['balance_hourly.csv','components.npz','D_generator_scope.csv']],'producer':rec(Path(__file__))}
    (OUT/'balance_contract.json').write_text(json.dumps(contract,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:contract[k] for k in ['passed','hours','qualified_hours','maximum_identity_residual_public_MW','baseline_MAE_public_MW','baseline_WAPE_percent']}))
if __name__=='__main__':main()
