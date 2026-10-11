"""Post-hoc exact western cut-balance decomposition; no fitting or source edits."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_western_audit'

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def build():
    paths=[ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch.mat',
        OUT/'dispatch/all_boundary_actual_dispatch.mat',OUT/'replay/dated_combined.mat',
        ROOT/'output/nygrid_2025_par_controls/replay/dated_verified_PAR_flows.mat',
        ROOT/'output/nygrid_2025_moses_audit/corrected/model_generator_register.csv',
        OUT/'corrected/model_generator_register.csv',
        ROOT/'output/nygrid_2025_inputs/load_source/interface_wide.csv',
        ROOT/'output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv',OUT/'replay/paired_common_mask.npy',Path(__file__)]
    d=loadmat(paths[0],simplify_cells=True);a=loadmat(paths[1],simplify_cells=True)
    r=loadmat(paths[2],simplify_cells=True);old=loadmat(paths[3],simplify_cells=True)
    g0=pd.read_csv(paths[4]);g1=pd.read_csv(paths[5]);obs=pd.read_csv(paths[6])
    metadata=pd.read_csv(paths[7]).set_index('idx')
    q=np.load(paths[8],allow_pickle=False);gamma=float(d['gamma'])
    assert np.array_equal(d['timestamp_utc'],obs.timestamp_utc.to_numpy())
    output=pd.DataFrame(dict(hour_index=d['hour_index'],timestamp_utc=d['timestamp_utc'],paired_qualified=q))
    labels=np.asarray(a['region_labels']).astype(str)
    on=int(np.flatnonzero(labels=='ONTARIO')[0])
    delta=a['delta_region_public_mw'][:,on]
    output['Ontario_actual_minus_schedule_mw']=delta
    output['all_four_boundary_delta_mw']=a['total_boundary_delta_public_mw']
    rows=[];errors=[]
    for j,(name,zones) in enumerate([('DYSINGER EAST',['A']),('WEST CENTRAL',['A','B'])]):
        ids=metadata.index[metadata.zone.isin(zones)].to_numpy(int)
        m0=(g0.role.eq('native')&g0.bus_id.isin(ids)).to_numpy(float)
        m1=(g1.role.eq('native')&g1.bus_id.isin(ids)).to_numpy(float)
        mapping=d['gen_pg']@(m1-m0)/gamma
        generation=(a['gen_pg']-d['gen_pg'])@m0/gamma
        interaction=(a['gen_pg']-d['gen_pg'])@(m1-m0)/gamma
        change=(r['interface_pf'][:,j]-old['interface_pf'][:,j])/gamma
        residual=change-(mapping+generation+interaction+delta)
        assert np.max(abs(residual[q]))<1e-7
        prediction=r['interface_pf'][:,j]/gamma
        error=prediction-obs[name].to_numpy(float);errors.append(error[q])
        prefix=['Dysinger','West_Central'][j]
        for key,value in [('mapping_at_original_PG',mapping),('generation_on_old_map',generation),
            ('mapping_generation_interaction',interaction),('prediction_change',change),('remaining_error',error)]:
            output[prefix+'_'+key+'_mw']=value
            rows.append(dict(interface=name,component=key,hours=int(q.sum()),mean_mw=float(np.mean(value[q])),
                mean_absolute_mw=float(np.mean(abs(value[q]))),minimum_mw=float(value[q].min()),maximum_mw=float(value[q].max())))
        rows.append(dict(interface=name,component='Ontario_actual_minus_schedule',hours=int(q.sum()),
            mean_mw=float(np.mean(delta[q])),mean_absolute_mw=float(np.mean(abs(delta[q]))),
            minimum_mw=float(delta[q].min()),maximum_mw=float(delta[q].max())))
    result=dict(passed=True,paired_hours=int(q.sum()),
        remaining_error_correlation=float(np.corrcoef(errors)[0,1]),
        remaining_common_fraction_pair_squared_error=float(np.sum((errors[0]+errors[1])**2/2)/np.sum(errors[0]**2+errors[1]**2)),
        component_mean_absolute_values_are_not_additive_error_attributions=True,
        internal_observations_used_only_after_reconstruction=True,
        dependencies=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in paths])
    folder=OUT/'effects';folder.mkdir(parents=True,exist_ok=True)
    output.to_csv(folder/'western_hourly_decomposition.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    pd.DataFrame(rows).to_csv(folder/'western_component_summary.csv',index=False)
    (folder/'effects_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':build()
