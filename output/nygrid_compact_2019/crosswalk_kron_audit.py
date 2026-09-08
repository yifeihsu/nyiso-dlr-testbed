"""Independent DC common-port injection audit; no interface targets read."""
from pathlib import Path
import json
import hashlib
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
path=ROOT/'output/compact_npcc_ny/compact_npcc_ny_reference.mat'
m=loadmat(path,simplify_cells=True)['mpc']
bus,branch=m['bus'],m['branch'];ids=bus[:,0].astype(int)
lookup={b:k for k,b in enumerate(ids)}
keep=np.flatnonzero(np.isin(ids,np.arange(37,83)))
remove=np.flatnonzero(~np.isin(ids,np.arange(37,83)))
assert len(keep)==46 and len(remove)==5
A=np.zeros((len(branch),len(bus)))
for k,row in enumerate(branch):
    A[k,lookup[int(row[0])]]=1;A[k,lookup[int(row[1])]]=-1
on=branch[:,10]>0;tap=branch[:,8].copy();tap[tap==0]=1
b=np.zeros(len(branch));b[on]=100/(branch[on,3]*tap[on])
B=A.T@(b[:,None]*A)
phase=-b*np.deg2rad(branch[:,9]);p0=A.T@phase
EE=B[np.ix_(remove,remove)];ER=B[np.ix_(remove,keep)];RE=ER.T
schur=B[np.ix_(keep,keep)]-RE@np.linalg.solve(EE,ER)
T=np.zeros((len(keep),len(ids)));T[:,keep]=np.eye(len(keep));T[:,remove]=-RE@np.linalg.solve(EE,np.eye(len(remove)))
p0_reduced=T@p0
assert np.max(np.abs(T.sum(axis=0)-1))<1e-12
assert np.min(T)>-1e-12 and np.max(np.abs(p0))==0
ref=lookup[74];nonref=np.flatnonzero(np.arange(len(ids))!=ref)
ref_small=int(np.flatnonzero(ids[keep]==74)[0]);nr_small=np.flatnonzero(np.arange(len(keep))!=ref_small)
rng=np.random.default_rng(20190108);p=rng.normal(0,100,(12,len(ids)));p[:,ref]-=p.sum(axis=1)
theta=np.zeros_like(p);theta[:,nonref]=np.linalg.solve(B[np.ix_(nonref,nonref)],(p-p0)[:,nonref].T).T
pr=p@T.T;small=np.zeros_like(pr)
small[:,nr_small]=np.linalg.solve(schur[np.ix_(nr_small,nr_small)],(pr-p0_reduced)[:,nr_small].T).T
recovered=np.zeros_like(theta);recovered[:,keep]=small
recovered[:,remove]=np.linalg.solve(EE,(p[:,remove]-p0[remove]-small@ER.T).T).T
flow=(theta@A.T)*b+phase;replayed=(recovered@A.T)*b+phase
angle_error=float(np.max(np.abs(theta[:,keep]-small)))
flow_error=float(np.max(np.abs(flow-replayed)))
assert angle_error<1e-10 and flow_error<1e-8
rows=[]
for j,bid in enumerate(ids):
    for i,target in enumerate(ids[keep]):
        if abs(T[i,j])>1e-14:
            rows.append({'source_compact_bus':bid,'retained_common_bus':target,'injection_coefficient':T[i,j],
                         'source_bus_eliminated':bool(j in remove),
                         'method':'exact_compact_DC_Schur_port_injection_map_not_geographic_telemetry'})
pd.DataFrame(rows).to_csv(OUT/'crosswalk_kron_injection_map.csv',index=False,lineterminator='\n',float_format='%.15g')
checks=[('five_added_nodes_eliminated',True,len(remove)),
        ('every_injection_column_sum_is_one',True,float(np.max(np.abs(T.sum(axis=0)-1)))),
        ('nonnegative_participation_weights',True,float(np.min(T))),
        ('present_network_phase_offsets_zero',True,float(np.max(np.abs(p0)))),
        ('independent_random_probe_retained_angles',True,angle_error),
        ('independent_random_probe_all_original_branch_flows',True,flow_error)]
pd.DataFrame(checks,columns=['gate','passed','value']).to_csv(OUT/'crosswalk_kron_validation.csv',index=False,lineterminator='\n',float_format='%.15g')
summary={'probes':12,'targets_read':False,'retained_bus_ids':ids[keep].tolist(),
         'eliminated_bus_ids':ids[remove].tolist(),'eliminated_block_condition_number':float(np.linalg.cond(EE)),
         'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
         'code_sha256_lf':hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
         'maximum_retained_angle_error_rad':angle_error,'maximum_original_branch_flow_error_mw':flow_error,
         'scope':'Exact elimination within compact DC graph. Applying its mapped injections to NYgrid changes the network and is a declared spatial-transfer hypothesis, not a claim of exact cross-network flow identity.'}
(OUT/'crosswalk_kron_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
print(pd.DataFrame(rows).query('source_bus_eliminated').to_string(index=False))
