"""Frozen common contract for matched 2025 western counterfactuals.

No internal interface observations are loaded here. They enter only the
separate, post-construction scoring command.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_western_counterfactuals'
PARENT=ROOT/'output/nygrid_2025_western_audit'
BASE=ROOT/'output/nygrid_2025_dispatch/dispatch'
PAR=ROOT/'output/nygrid_2025_par_controls'
SLIM=ROOT/'output/nygrid_2025_slim/network/network_cases.mat'
FULL=ROOT/'output/nygrid_2025_downstate/network/network_cases.mat'
NAMES=['DYSINGER EAST','WEST CENTRAL','TOTAL EAST','MOSES SOUTH','CENTRAL EAST - VC','UPNY CONED','SPR/DUN-SOUTH']

def require(value,message):
    if not value:raise ValueError(message)

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def record(path):
    path=Path(path)
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(path))

def check_records(rows):
    require(bool(rows),'Empty dependency proof')
    keys=[r['path'] for r in rows]
    require(len(keys)==len(set(keys)),'Duplicate dependency path')
    for row in rows:
        path=Path(row['path']);path=path if path.is_absolute() else ROOT/path
        require(path.is_file() and sha(path)==row['sha256'],'Changed dependency: '+str(path))

def load_baseline():
    provenance=read(PARENT/'replay/provenance.json')
    require(provenance['passed'] and provenance['preferred_mode']=='combined'
            and not provenance['internal_interface_observations_read'],'Unqualified parent replay')
    check_records(provenance['dependencies'])
    item=[r for r in provenance['variants'] if r['variant']=='dated_combined']
    require(len(item)==1 and sha(ROOT/item[0]['file'])==item[0]['sha256'],'Changed parent replay')
    receipt=read(PARENT/'dispatch/all_boundary_dispatch_receipt.json')
    require(receipt['passed'] and not receipt['internal_interface_observations_used'],'Unqualified parent dispatch')
    check_records(receipt['dependencies'])
    pg_path=PARENT/'dispatch/all_boundary_actual_dispatch.mat'
    require(sha(pg_path)==receipt['dispatch_file_sha256'],'Changed parent dispatch values')
    data=loadmat(BASE/'dispatch.mat',simplify_cells=True)
    dispatch=loadmat(pg_path,simplify_cells=True)
    baseline=loadmat(ROOT/item[0]['file'],simplify_cells=True)
    bounds=loadmat(BASE/'dispatch_bounds.mat',simplify_cells=True)
    priors=loadmat(BASE/'dispatch_priors.mat',simplify_cells=True)
    par=np.load(PAR/'controls/inputs.npz',allow_pickle=False)
    register=pd.read_csv(PARENT/'corrected/model_generator_register.csv',keep_default_na=False)
    q=np.load(PARENT/'replay/paired_common_mask.npy',allow_pickle=False)
    times=np.asarray(data['timestamp_utc']).astype(str)
    require(q.dtype==bool and q.shape==(8760,) and q.sum()==8651,'The fixed experiment cohort changed')
    require(np.all(np.asarray(dispatch['qualified'],bool)[q]) and np.all(np.asarray(baseline['qualified'],bool)[q]),'Unqualified baseline hour')
    require(np.array_equal(times,np.asarray(dispatch['timestamp_utc']).astype(str))
            and np.array_equal(times,np.asarray(baseline['timestamp_utc']).astype(str)), 'Baseline clock mismatch')
    require(np.array_equal(register.gen_row,np.arange(1,1465))
            and np.array_equal(register.bus_id,baseline['corrected_generator_buses']), 'Generator axis mismatch')
    paths=[BASE/'dispatch.mat',BASE/'dispatch_bounds.mat',BASE/'dispatch_priors.mat',pg_path,
           PARENT/'dispatch/all_boundary_dispatch_receipt.json',PARENT/'replay/provenance.json',ROOT/item[0]['file'],
           PARENT/'replay/paired_common_mask.npy',PARENT/'corrected/model_generator_register.csv',
           PAR/'controls/inputs.npz',SLIM,FULL,Path(__file__)]
    return dict(data=data,dispatch=dispatch,baseline=baseline,bounds=bounds,priors=priors,par=par,
                register=register,qualified=q,times=times,gamma=float(data['gamma']),paths=paths)

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
