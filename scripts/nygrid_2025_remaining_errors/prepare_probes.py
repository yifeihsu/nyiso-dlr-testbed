"""Freeze calendar-selected, bounded sensitivities before reading their scores."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json
import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_remaining_errors/probes'

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def shift(pg,lo,hi,rows,delta):
    room=(hi-pg)[rows] if delta>0 else (pg-lo)[rows]
    if room.sum()<abs(delta)-1e-9:return False
    pg[rows]+=np.sign(delta)*abs(delta)*room/room.sum()
    return True

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    src=ROOT/'output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_arrays.npz'
    a=np.load(src);t=pd.DatetimeIndex(pd.to_datetime(a['timestamp_utc'],utc=True))
    q=a['revised_qualified'];state=np.select([np.arange(8760)<3359,np.arange(8760)<3575,np.arange(8760)<8471],[1,2,3],default=4)
    targets=[f'2025-{m:02d}-15T17:00:00Z' for m in range(1,13)]+['2025-05-25T17:00:00Z','2025-05-31T17:00:00Z','2025-12-25T17:00:00Z']
    selected=[]
    for target in targets:
        instant=pd.Timestamp(target);near=int(np.argmin(abs(t-instant)))
        eligible=np.flatnonzero(q&(t.month==instant.month)&(state==state[near]))
        k=int(eligible[np.argmin(abs(t[eligible]-instant))]);selected.append(k)
    ix=np.array(sorted(set(selected)));assert len(ix)==15 and len(set(state[ix]))==4
    samples=pd.DataFrame({'hour_index':ix+1,'timestamp_utc':a['timestamp_utc'][ix],'state_index':state[ix]})
    samples.to_csv(OUT/'calendar_sample.csv',index=False)
    files=[src,ROOT/'output/nygrid_2025_western_audit/corrected/model_generator_register.csv',
           ROOT/'output/nygrid_2025_western_audit/corrected/fleet_register.csv',
           ROOT/'output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv',
           ROOT/'output/nygrid_2025_conductor_inference/all_parent_parameter_provenance.csv']
    reg=pd.read_csv(files[1]).merge(pd.read_csv(files[2])[['device_key','prime_mover']],on='device_key',how='left',validate='one_to_one')
    assert np.array_equal(reg.gen_row,np.arange(1,1465))
    bus=pd.read_csv(files[3]).set_index('idx');zones=reg.bus_id.map(bus.zone)
    plant=pd.to_numeric(reg.plant_id,errors='coerce')
    hy=reg.role.eq('native')&reg.fuel_category.eq('Hydro')&reg.prime_mover.eq('HY')
    targets_rows=[np.flatnonzero(hy&plant.eq(p)) for p in [2693,2694]]
    donors=np.flatnonzero(hy&~plant.isin([2693,2694])&~zones.isin(['A','B','D']))
    assert len(targets_rows[0])==13 and len(targets_rows[1])==15
    pg=np.zeros((len(ix),1464));lo=pg.copy();hi=pg.copy()
    for shard,first in [('profiles_h0001_4380.mat',0),('profiles_h4381_8760.mat',4380)]:
        path=ROOT/'output/nygrid_2025_latest_handoff/model'/shard;files.append(path)
        p=loadmat(path,simplify_cells=True,variable_names=['profiles'])['profiles']
        take=(ix>=first)&(ix<first+4380);rows=ix[take]-first
        pg[take]=p['generator_PG_MW'][rows];lo[take]=p['generator_Pmin_MW'][rows];hi[take]=p['generator_Pmax_MW'][rows]
    gamma=float(a['gamma']);changed=np.repeat(pg[:,None,:],4,axis=1);feasible=np.ones((len(ix),4),bool)
    for k in range(len(ix)):
        for j in range(4):
            delta=(100 if j%2==0 else -100)*gamma;x=changed[k,j]
            feasible[k,j]=shift(x,lo[k],hi[k],targets_rows[j//2],delta) and shift(x,lo[k],hi[k],donors,-delta)
            if feasible[k,j]:
                assert abs(x.sum()-pg[k].sum())<1e-8 and np.max(lo[k,:1436]-x[:1436])<1e-8 and np.max(x[:1436]-hi[k,:1436])<1e-8
            else:changed[k,j]=np.nan
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'purpose':'Local sensitivities; not a new annual candidate or historical dispatch inference',
        'sample_selection':'Nearest current-equation-qualified hour in same calendar UTC month and topology state to each 15th17:00UTC plus May25, May31 and December25; no residual magnitude used',
        'samples':samples.to_dict('records'),'gamma':gamma,
        'variants':['baseline','niagara_plus100','niagara_minus100','stlawrence_plus100','stlawrence_minus100','pjm_PG_capacity_share','pjm_loss_capacity_share','pjm_both_capacity_share','parent41_imported_RX','parent41_imported_RXB'],
        'hydro_rule':'Shift exactly100publicMW if feasible using proportional headroom or downward room; balance conventional HY outside A/B/D; preserve statewideHY and all unitbounds',
        'hydro_donor_rows_1based':(donors+1).tolist(),'hydro_target_rows_1based':[(r+1).tolist() for r in targets_rows],
        'hydro_feasible':feasible.tolist(),
        'PJM_rule':'Redistribute baselinePG proportional to original finite(Pmax-Pmin) abovePmin, samegroupPG; lossweights separately proportional to original finitePmax. These are alternative proxy assumptions, not observed dispatch.',
        'parent41_rule':'Admittance-only sensitivity: imported R=.0018,X=.0089, retain currentB or restore importedB=.07. No conductor or DLR certification; no default promotion; current thermal metadata are not validated for these variants.',
        'cohort_rule':'Only equation+loss+recovery qualified paired solves scored; explicit rejection status retained',
        'held_fixed':['all hourlygrossNYload andexternaldeliveredload','HQ andsixDC/PARtargets','nativePGexceptdefinedhydrovariants','allotherbranchparameters'],
        'observations_used_for_parameter_selection':False,'model_modified':False,
        'sources':[{'path':f.relative_to(ROOT).as_posix(),'sha256':sha(f)} for f in files]}
    path=OUT/'probe_plan.json'
    if path.exists():
        old=json.loads(path.read_text());old.pop('created_utc');new=plan.copy();new.pop('created_utc');assert old==new
    else:path.write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
    savemat(OUT/'probe_inputs.mat',{'hour_index':ix+1,'baseline_PG':pg,'hydro_PG':changed,'hydro_feasible':feasible,'gamma':gamma},do_compression=True)
    print(json.dumps({'hours':len(ix),'states':len(set(state[ix])),'feasible_hydro_cases':int(feasible.sum()),'planned_solve_count':len(ix)*10}))

if __name__=='__main__':main()
