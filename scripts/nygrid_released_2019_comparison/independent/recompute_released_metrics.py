"""Read-only numerical verification of the authors' released 57-bus replay.

Both operator views use the same saved branch-PF solutions and released 2019
observations. This script performs no PF, input replacement or network edit.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OLD=ROOT/'output/nygrid_2019'
UPSTREAM=ROOT/'tmp/nygrid_2019_reproduction/upstream'
OUT=ROOT/'output/nygrid_released_2019_comparison/independent'
NAMES=['Dysinger East','West Central','Total East','Moses South','Central East','UpNY-Coned','Dun/SPR-South']
CURRENT_NAMES=['DYSINGER EAST','WEST CENTRAL','TOTAL EAST','MOSES SOUTH','CENTRAL EAST - VC','UPNY CONED','SPR/DUN-SOUTH']
VARIABLES=['A2B','B2C','C2E','D2E','E2F','G2H','I2J']
MAP_IDS=[1,2,3,4,5,8,10]


def record(path):
    with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':digest,'bytes':path.stat().st_size}


def metrics(prediction,actual,limit):
    p=np.asarray(prediction).reshape(-1);a=np.asarray(actual).reshape(-1);L=np.asarray(limit).reshape(-1)
    assert p.shape==a.shape==L.shape and np.isfinite([p,a,L]).all() and np.all(L>0)
    e=p-a;r=-100*e/L;nonzero=a!=0
    return {'comparisons':len(e),'MAE_public_MW':float(abs(e).mean()),'RMSE_public_MW':float(np.sqrt(np.mean(e*e))),
        'bias_model_minus_observed_MW':float(e.mean()),'WAPE_percent':float(100*abs(e).sum()/abs(a).sum()),
        'mean_abs_observed_MW':float(abs(a).mean()),'MAPE_nonzero_actual_percent':float(np.mean(100*abs(e[nonzero])/abs(a[nonzero]))),
        'zero_observed_count':int((~nonzero).sum()),'positive_limit_9999_count':int((L==9999).sum()),
        'paper_signed_limit_q025_percent':float(np.quantile(r,.025)),'paper_signed_limit_q25_percent':float(np.quantile(r,.25)),
        'paper_signed_limit_median_percent':float(np.quantile(r,.5)),'paper_signed_limit_q75_percent':float(np.quantile(r,.75)),
        'paper_signed_limit_q975_percent':float(np.quantile(r,.975)),
        'mean_absolute_limit_normalized_error_percent':float(abs(r).mean()),
        'fraction_abs_paper_error_at_most10pct':float(np.mean(abs(r)<=10)),
        'fraction_abs_paper_error_at_most15pct':float(np.mean(abs(r)<=15))}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    old_manifest_path=OLD/'verification_manifest.json';up_manifest_path=OLD/'upstream_manifest.json'
    old_manifest=json.loads(old_manifest_path.read_text());up_manifest=json.loads(up_manifest_path.read_text())
    assert old_manifest['complete'] and old_manifest['hours']==8760
    assert up_manifest['commit']=='47698b6c7823ae7b1bc6935e5601d5b64b8f918e'
    checks=[];before=[]
    for entry in up_manifest['files']:
        p=UPSTREAM/entry['path'];current=record(p)
        assert current['sha256']==entry['sha256'],p
        data=p.read_bytes();blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        assert blob==entry['git_blob_sha1'],p
        checks.append({'scope':'pinned_authors_release','path':current['path'],'sha256_verified':True,'git_blob_verified':True})
        before.append(current)
    expected={item['path']:item for item in old_manifest['files']}
    paths=[]
    for part in range(1,5):
        paths += [OLD/f'annual_{part}.mat',OLD/f'annual_{part}_cases.csv',OLD/f'annual_{part}_interfaces.csv']
    for path in paths:
        current=record(path);reference=expected[current['path']]
        assert current['sha256']==reference['sha256'],path
        checks.append({'scope':'saved_authors_57bus_annual_replay','path':current['path'],'sha256_verified':True,'git_blob_verified':False})
        before.append(current)
    flow_source=UPSTREAM/'Utility/flow4Plot.m';text=flow_source.read_text()
    map_source=UPSTREAM/'updateOpCond.m';map_text=map_source.read_text()
    literal=[]
    released_members=[]
    for variable in VARIABLES:
        expression=re.search(r'^'+variable+r'Result\s*=\s*([^;]+);',text,re.M).group(1)
        terms=re.findall(r'([+-]?)\s*resultBranch\((\d+),PF\)',expression)
        assert terms and not re.sub(r'([+-]?)\s*resultBranch\(\d+,PF\)','',expression).strip()
        literal.append([(-1 if sign=='-' else 1)*int(row) for sign,row in terms])
        assignment=re.search(r'branchId'+variable+r'\s*=\s*\[([^\]]+)\];',map_text).group(1)
        released_members.append([int(value) for value in re.findall(r'-?\d+',assignment)])
    arrays={key:[] for key in ['sim','corrected_sim','actual','limit','paper','branch_pf']}
    hours=[];clock=[];maps=None;base_numeric=None;max_literal=0.;max_ifmap=0.;max_paper=0.;max_csv=0.
    for part in range(1,5):
        file=OLD/f'annual_{part}.mat'
        d=loadmat(file,simplify_cells=True,variable_names=[*arrays,'first_hour','last_hour','status','base_case'])
        first=int(d['first_hour']);last=int(d['last_hour']);n=last-first+1
        assert first==(part-1)*2190+1 and last==part*2190 and n==2190 and np.asarray(d['status'],bool).all()
        base=d['base_case'];assert base['bus'].shape[0]==57 and base['branch'].shape[0]==94 and base['gen'].shape[0]==271 and base['dcline'].shape[0]==4
        current_numeric={'bus_ids':base['bus'][:,0],'branch':base['branch'][:,:13],'generator_bus_ids':base['gen'][:,0]}
        if base_numeric is None:base_numeric=current_numeric
        else:
            for key,value in current_numeric.items():assert np.array_equal(value,base_numeric[key]),key
        stored_map=np.asarray(base['if']['map'],int)
        members=[stored_map[stored_map[:,0]==map_id,1] for map_id in MAP_IDS]
        assert all(np.array_equal(a,b) for a,b in zip(released_members,members))
        if maps is None:maps=members
        else:assert all(np.array_equal(a,b) for a,b in zip(maps,members))
        pf=np.asarray(d['branch_pf']);assert pf.shape==(n,94) and np.isfinite(pf).all()
        literal_prediction=np.column_stack([sum(np.sign(r)*pf[:,abs(r)-1] for r in terms) for terms in literal])
        ifmap_prediction=np.column_stack([sum(np.sign(r)*pf[:,abs(r)-1] for r in terms) for terms in members])
        max_literal=max(max_literal,float(np.max(abs(literal_prediction-d['sim']))))
        max_ifmap=max(max_ifmap,float(np.max(abs(ifmap_prediction-d['corrected_sim']))))
        max_paper=max(max_paper,float(np.max(abs(100*(d['actual']-d['sim'])/d['limit']-d['paper']))))
        assert max_literal<1e-9 and max_ifmap<1e-9 and max_paper<1e-9
        cases=pd.read_csv(OLD/f'annual_{part}_cases.csv');observations=pd.read_csv(OLD/f'annual_{part}_interfaces.csv')
        assert len(cases)==n and len(observations)==n*7 and cases.status.astype(bool).all() and observations.pf_success.astype(bool).all()
        assert np.array_equal(observations.interface.to_numpy(),np.tile(NAMES,n))
        for field,column in [('sim','released_plot_mw'),('corrected_sim','corrected_operator_mw'),('actual','observed_mw'),('limit','positive_limit_mw'),('paper','released_paper_error_pct')]:
            delta=float(np.max(abs(d[field]-observations[column].to_numpy().reshape(n,7))))
            max_csv=max(max_csv,delta)
        assert max_csv<1e-8
        parsed=pd.to_datetime(cases.times,format='%d-%b-%Y %H:%M:%S')
        assert np.array_equal(parsed.to_numpy(),pd.date_range('2019-01-01',periods=8760,freq='h')[first-1:last].to_numpy())
        clock.extend(parsed.dt.strftime('%Y-%m-%dT%H:%M:%S').tolist());hours.extend(range(first,last+1))
        for key in arrays:arrays[key].append(np.asarray(d[key]))
    assert hours==list(range(1,8761)) and len(set(clock))==8760
    arrays={key:np.concatenate(value) for key,value in arrays.items()}
    rows=[]
    for label,field in [('strict_literal_flow4Plot','sim'),('authors_released_if_map','corrected_sim')]:
        for j,name in enumerate(NAMES):rows.append({'model':'authors_released_57bus','year':2019,'operator':label,'interface':name,'hours':8760,
            **metrics(arrays[field][:,j],arrays['actual'][:,j],arrays['limit'][:,j])})
        rows.append({'model':'authors_released_57bus','year':2019,'operator':label,'interface':'ALL_SEVEN_POOLED','hours':8760,
            **metrics(arrays[field],arrays['actual'],arrays['limit'])})
    metric_frame=pd.DataFrame(rows);metric_path=OUT/'released_2019_recomputed_metrics.csv';metric_frame.to_csv(metric_path,index=False)
    members_path=OUT/'released_operator_members.csv'
    pd.DataFrame([{'interface':name,'authors_map_id':mid,'strict_literal_signed_branch_rows':';'.join(map(str,lit)),
        'authors_if_map_signed_branch_rows':';'.join(map(str,mapped)),'same_coefficients':lit==mapped.tolist()}
        for name,mid,lit,mapped in zip(NAMES,MAP_IDS,literal,maps)]).to_csv(members_path,index=False)
    current_path=ROOT/'output/nygrid_2025_physical_repair/annual/physical_repair_v1/comparison/public_interface_metrics.csv'
    current_receipt_path=current_path.parent/'scoring_receipt.json'
    current_receipt=json.loads(current_receipt_path.read_text());assert current_receipt['passed'] and current_receipt['completed']
    expected_current=next(x for x in current_receipt['outputs'] if x['path']==current_path.relative_to(ROOT).as_posix())
    assert record(current_path)['sha256']==expected_current['sha256']
    before.extend([record(current_path),record(current_receipt_path)])
    current=pd.read_csv(current_path)
    current=current.loc[(current.model=='candidate')&(current.cohort=='candidate_all_success')&(current.period=='annual')&(current.convention=='legacy_signed_literal_from')].set_index('interface')
    assert len(current)==7 and current.hours.eq(8651).all();comparison=[]
    for name,new_name in zip(NAMES,CURRENT_NAMES):
        oldrows=metric_frame.loc[metric_frame.interface.eq(name)].set_index('operator');new=current.loc[new_name]
        comparison.append({'interface':name,'released_2019_hours':8760,'other_model_2025_hours':8651,
            'strict_literal_2019_MAE_MW':oldrows.loc['strict_literal_flow4Plot','MAE_public_MW'],
            'strict_literal_2019_WAPE_percent':oldrows.loc['strict_literal_flow4Plot','WAPE_percent'],
            'authors_ifmap_2019_MAE_MW':oldrows.loc['authors_released_if_map','MAE_public_MW'],
            'authors_ifmap_2019_WAPE_percent':oldrows.loc['authors_released_if_map','WAPE_percent'],
            'other_model_2025_MAE_MW':new.mae_public_MW,'other_model_2025_WAPE_percent':new.wape_percent,
            'controlled_model_comparison':False})
    comparison_path=OUT/'released2019_vs_othermodel2025.csv';pd.DataFrame(comparison).to_csv(comparison_path,index=False)
    for item in before:assert record(ROOT/item['path'])==item
    proof={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),
        'HEAD':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'baseline':'Authors released57-bus model with authors released2019 inputs only',
        'authors_release_commit':up_manifest['commit'],'released_code_data_files_verified':len(up_manifest['files']),
        'annual_mat_and_companion_files_hash_verified':len(paths),'hours':8760,'successful_saved_DC_hours':8760,
        'inventory':{'buses':57,'AC_branches':94,'generators':271,'DC_links':4},
        'same_unchanged_branch_PF_solutions_for_both_operators':True,
        'stored_ifmap_members_match_pinned_authors_updateOpCond_source_exactly':True,
        'maximum_literal_formula_recomputation_error_MW':max_literal,'maximum_authors_ifmap_recomputation_error_MW':max_ifmap,
        'maximum_saved_paper_error_recomputation_difference_percentage_points':max_paper,
        'maximum_MAT_vs_companion_CSV_difference':max_csv,
        'strict_literal_pooled':metric_frame.loc[(metric_frame.operator=='strict_literal_flow4Plot')&(metric_frame.interface=='ALL_SEVEN_POOLED')].iloc[0].to_dict(),
        'authors_ifmap_pooled':metric_frame.loc[(metric_frame.operator=='authors_released_if_map')&(metric_frame.interface=='ALL_SEVEN_POOLED')].iloc[0].to_dict(),
        'paper_metric':'100*(observed-simulated)/positive hourly interface limit; signed and distinct from WAPE.',
        'WAPE_metric':'100*sum(abs(simulated-observed))/sum(abs(observed)); no denominator floor or hour exclusion.',
        'new_PF_run':False,'source_or_network_modified':False,'derived_network_used_as_2019_baseline':False,
        'original_2019_source_time_preparation_retained':True,
        'current_2025_used_only_as_separate_existing_other_model_metrics':True,
        'limitations':['2019 uses the authors8760naive local labels including their interpolation and repeated-hour preparation.',
            'Strictliteral and authorsif.map are distinct measurement views; if.map aggregation does not alter any solved model state.',
            '2025 has different inputs, topology,AC/loss treatment and8651qualified physical hours; the cross-year table is not a controlled model-performance comparison.',
            'No physical-meter, operating-feasibility or original-paper-Figure5 exact-reproduction certification is made.'],
        'hash_checks':checks,'source_hashes_unchanged_after_analysis':True,
        'dependencies':[record(p) for p in [old_manifest_path,up_manifest_path,current_path,current_receipt_path,*paths,flow_source,map_source]],
        'outputs':[record(p) for p in [metric_path,members_path,comparison_path]],'producer':record(Path(__file__))}
    (OUT/'independent_released_2019_review.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(metric_frame[['operator','interface','hours','MAE_public_MW','WAPE_percent']].to_string(index=False))
    print(json.dumps({k:proof[k] for k in ['passed','released_code_data_files_verified','annual_mat_and_companion_files_hash_verified','maximum_literal_formula_recomputation_error_MW','maximum_authors_ifmap_recomputation_error_MW','maximum_MAT_vs_companion_CSV_difference']}))


if __name__=='__main__':main()
