"""Broader error metrics for the released 2019 DC and current 2025 AC cases.

Read saved predictions only. No model, source, map or slide modification.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, re, subprocess
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2019_2025_error_metrics'
OLD=ROOT/'output/nygrid_2019'
NEW=ROOT/'output/nygrid_2025_moses_repair/annual/moses_repair_v1/comparison'
NAMES=['DYSINGER EAST','WEST CENTRAL','TOTAL EAST','MOSES SOUTH',
       'CENTRAL EAST - VC','UPNY CONED','SPR/DUN-SOUTH']
OLD_NAMES=['Dysinger East','West Central','Total East','Moses South',
           'Central East','UpNY-Coned','Dun/SPR-South']
VARIABLES=['A2B','B2C','C2E','D2E','E2F','G2H','I2J']
MAP_IDS=[1,2,3,4,5,8,10]
CONVENTION='legacy_signed_literal_from'
NUMERIC=['bias_MW','MAE_MW','MSE_MW2','RMSE_MW','error_SD_MW',
         'median_AE_MW','p95_AE_MW','WAPE_percent','nRMSE_percent',
         'normalized_bias_percent','MAPE_nonzero_percent',
         'MAPE_abs_actual_ge100_percent','sMAPE_percent']


def rec(path):
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=digest,bytes=path.stat().st_size)


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def metrics(predicted,observed):
    predicted=np.asarray(predicted,float).ravel()
    observed=np.asarray(observed,float).ravel()
    assert predicted.shape==observed.shape and len(predicted)>0
    assert np.isfinite(predicted).all() and np.isfinite(observed).all()
    error=predicted-observed;absolute=np.abs(error);obs_abs=np.abs(observed)
    denominator=float(obs_abs.mean());assert denominator>0
    mse=float(np.mean(error**2));bias=float(error.mean());sd=float(error.std(ddof=0))
    assert np.isclose(mse,bias*bias+sd*sd,rtol=1e-12,atol=1e-8)
    nonzero=obs_abs>0;guarded=obs_abs>=100
    symmetric=np.abs(predicted)+obs_abs
    smape=np.divide(200*absolute,symmetric,out=np.zeros_like(absolute),where=symmetric>0)
    result=dict(hours=len(error),bias_MW=bias,MAE_MW=float(absolute.mean()),
        MSE_MW2=mse,RMSE_MW=float(np.sqrt(mse)),error_SD_MW=sd,
        median_AE_MW=float(np.median(absolute)),
        p95_AE_MW=float(np.quantile(absolute,.95,method='linear')),
        WAPE_percent=float(100*absolute.sum()/obs_abs.sum()),
        nRMSE_percent=float(100*np.sqrt(mse)/denominator),
        normalized_bias_percent=float(100*bias/denominator),
        MAPE_nonzero_percent=float(100*np.mean(absolute[nonzero]/obs_abs[nonzero])),
        MAPE_abs_actual_ge100_percent=float(100*np.mean(absolute[guarded]/obs_abs[guarded])),
        sMAPE_percent=float(smape.mean()),
        MAPE_nonzero_hours=int(nonzero.sum()),
        MAPE_ge100_hours=int(guarded.sum()),
        MAPE_nonzero_coverage_percent=float(100*nonzero.mean()),
        MAPE_ge100_coverage_percent=float(100*guarded.mean()),
        observed_zero_hours=int((~nonzero).sum()),
        observed_abs_below100_hours=int((obs_abs<100).sum()),
        mean_abs_observed_MW=denominator)
    assert np.isclose(result['WAPE_percent'],100*result['MAE_MW']/denominator)
    return result


def load_arrays():
    pointer_path=ROOT/'deliverables/CURRENT_NYGRID_MODEL.json'
    pointer=read(pointer_path)
    assert pointer['model_receipt']['path']=='output/nygrid_2025_moses_repair/model/model_receipt.json'
    assert rec(ROOT/pointer['model_receipt']['path'])['sha256']==pointer['model_receipt']['sha256']
    old_manifest=read(OLD/'verification_manifest.json')
    upstream_manifest=read(OLD/'upstream_manifest.json')
    scoring=read(NEW/'scoring_receipt.json')
    assert old_manifest['complete'] and old_manifest['hours']==8760
    assert scoring['passed'] and scoring['completed'] and scoring['run_label']=='moses_repair_v1'
    assert upstream_manifest['commit']=='47698b6c7823ae7b1bc6935e5601d5b64b8f918e'
    map_path=ROOT/'tmp/nygrid_2019_reproduction/upstream/updateOpCond.m'
    assert rec(map_path)['sha256']==next(r['sha256'] for r in upstream_manifest['files'] if r['path']=='updateOpCond.m')
    terms=[]
    code=map_path.read_text(encoding='utf-8')
    for variable in VARIABLES:
        body=re.search(r'branchId'+variable+r'\s*=\s*\[([^\]]+)\];',code).group(1)
        terms.append(np.array([int(v) for v in re.findall(r'-?\d+',body)]))
    old_expected={r['path']:r['sha256'] for r in old_manifest['files']}
    observed_parts=[];predicted_parts=[]
    for i in range(1,5):
        path=OLD/f'annual_{i}.mat'
        assert rec(path)['sha256']==old_expected[path.relative_to(ROOT).as_posix()]
        saved=loadmat(path,simplify_cells=True,variable_names=[
            'actual','corrected_sim','branch_pf','status','first_hour','last_hour','base_case'])
        assert np.asarray(saved['status'],bool).all()
        assert saved['first_hour']==(i-1)*2190+1 and saved['last_hour']==i*2190
        assert saved['base_case']['bus'].shape[0]==57 and saved['base_case']['branch'].shape[0]==94
        stored=np.asarray(saved['base_case']['if']['map'],int)
        for ident,member in zip(MAP_IDS,terms):
            assert np.array_equal(stored[stored[:,0]==ident,1],member)
        flows=np.asarray(saved['branch_pf'],float)
        predicted=np.column_stack([np.sum(flows[:,np.abs(member)-1]*np.sign(member),axis=1) for member in terms])
        assert np.allclose(predicted,saved['corrected_sim'],rtol=0,atol=1e-9)
        observed_parts.append(np.asarray(saved['actual'],float));predicted_parts.append(predicted)
    z=np.load(NEW/'comparison_arrays.npz',allow_pickle=False)
    expected={r['path']:r['sha256'] for r in scoring['outputs']}
    for name in ['comparison_arrays.npz','public_interface_metrics.csv']:
        path=NEW/name;assert rec(path)['sha256']==expected[path.relative_to(ROOT).as_posix()]
    assert z['interface_names'].tolist()==NAMES
    mask=z['candidate_qualified'].astype(bool)
    assert mask.sum()==8651 and np.array_equal(mask,z['source_qualified'])
    assert np.array_equal(z['hour_index'],np.arange(1,8761))
    years={
        2019:(np.concatenate(predicted_parts),np.concatenate(observed_parts),
              pd.date_range('2019-01-01',periods=8760,freq='h').month.to_numpy()),
        2025:(z['candidate_'+CONVENTION][mask],z['observed'][mask],
              pd.to_datetime(z['timestamp_utc'],utc=True).tz_convert('America/New_York').month.to_numpy()[mask])
    }
    deps=[pointer_path,ROOT/pointer['model_receipt']['path'],
        OLD/'verification_manifest.json',OLD/'upstream_manifest.json',map_path,
        *[OLD/f'annual_{i}.mat' for i in range(1,5)],
        NEW/'comparison_arrays.npz',NEW/'scoring_receipt.json',NEW/'public_interface_metrics.csv',
        ROOT/'output/nygrid_released_2019_comparison/independent/released_2019_recomputed_metrics.csv']
    return years,deps


def main():
    OUT.mkdir(exist_ok=True)
    years,deps=load_arrays();before=[rec(p) for p in deps]
    annual=[];monthly=[];aggregate=[]
    for year,(predicted,observed,months) in years.items():
        for j,name in enumerate(NAMES):
            annual.append(dict(year=year,interface=name,**metrics(predicted[:,j],observed[:,j])))
            for month in range(1,13):
                mask=months==month
                monthly.append(dict(year=year,month=month,interface=name,**metrics(predicted[mask,j],observed[mask,j])))
        cohort=pd.DataFrame([r for r in annual if r['year']==year])
        macro={key:float(cohort[key].mean()) for key in NUMERIC}
        aggregate.append(dict(year=year,aggregation='macro_equal_interface',interfaces=7,
            hours_per_interface=len(observed),interface_hour_observations=observed.size,
            average_absolute_interface_bias_MW=float(np.abs(cohort.bias_MW).mean()),
            **macro,MAPE_nonzero_coverage_percent=float(cohort.MAPE_nonzero_coverage_percent.mean()),
            MAPE_ge100_coverage_percent=float(cohort.MAPE_ge100_coverage_percent.mean())))
        aggregate.append(dict(year=year,aggregation='pooled_interface_hours',interfaces=7,
            hours_per_interface=len(observed),interface_hour_observations=observed.size,
            average_absolute_interface_bias_MW=float(np.abs(cohort.bias_MW).mean()),
            **metrics(predicted,observed)))
    annual=pd.DataFrame(annual);monthly=pd.DataFrame(monthly);aggregate=pd.DataFrame(aggregate)
    old=annual[annual.year==2019].set_index('interface')
    new=annual[annual.year==2025].set_index('interface')
    rows=[]
    for name in NAMES:
        row=dict(interface=name,hours_2019=8760,hours_2025=8651)
        for key in NUMERIC:
            row['2019_'+key]=old.loc[name,key];row['2025_'+key]=new.loc[name,key]
            delta_key='delta_'+key.removesuffix('_percent')+'_pp' if key.endswith('_percent') else 'delta_'+key
            row[delta_key]=new.loc[name,key]-old.loc[name,key]
        for key in ['MAE_MW','RMSE_MW','p95_AE_MW']:
            row['relative_change_'+key+'_percent']=100*(new.loc[name,key]/old.loc[name,key]-1)
        rows.append(row)
    comparison=pd.DataFrame(rows)
    old_saved=pd.read_csv(deps[-1]).query("operator=='authors_released_if_map'").set_index('interface')
    new_saved=pd.read_csv(NEW/'public_interface_metrics.csv').query(
        "model=='candidate' and cohort=='candidate_all_success' and period=='annual' and convention==@CONVENTION").set_index('interface')
    discrepancies=[]
    for name,old_name in zip(NAMES,OLD_NAMES):
        for key,saved_key in [('MAE_MW','MAE_public_MW'),('RMSE_MW','RMSE_public_MW'),
                              ('bias_MW','bias_model_minus_observed_MW'),('WAPE_percent','WAPE_percent')]:
            discrepancies.append(abs(old.loc[name,key]-old_saved.loc[old_name,saved_key]))
        for key,saved_key in [('MAE_MW','mae_public_MW'),('RMSE_MW','rmse_public_MW'),
                              ('bias_MW','mean_bias_public_MW'),('WAPE_percent','wape_percent')]:
            # Current receipt uses a signed bias column; resolve its exact spelling.
            if key=='bias_MW':
                choices=[c for c in new_saved.columns if 'bias' in c and 'MW' in c and 'model' not in c]
                assert len(choices)==1,choices
                saved_key=choices[0]
            discrepancies.append(abs(new.loc[name,key]-new_saved.loc[name,saved_key]))
    assert max(discrepancies)<1e-8
    outputs=[]
    for name,frame in [('per_interface_metrics.csv',annual),('monthly_metrics.csv',monthly),
                       ('comparison.csv',comparison),('aggregate_metrics.csv',aggregate)]:
        path=OUT/name;frame.to_csv(path,index=False);outputs.append(path)
    assert before==[rec(p) for p in deps], 'Source file changed during calculation'
    metadata=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        checkout_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        source_years=[2019,2025],baseline='Reproduced authors released57bus DC case with supplied2019inputs',
        baseline_operator='authors_released_if_map',current_model='moses_repair_v1',
        current_operator=CONVENTION,current_model_pointer_verified=True,
        cohorts=dict(year2019=8760,year2025=8651,excluded2025=109),power_units='public scale MW',
        new_power_flow_run=False,model_or_deck_or_map_changed=False,
        definitions={
            'error':'predicted - observed; positive bias is numerical overprediction in the declared orientation',
            'bias_MW':'mean(error)',
            'MAE_MW':'mean(abs(error))',
            'MSE_MW2':'mean(error squared)',
            'RMSE_MW':'sqrt(mean(error squared))',
            'error_SD_MW':'population standard deviation of error, ddof=0',
            'median_AE_MW':'median absolute hourly error',
            'p95_AE_MW':'95th percentile absolute hourly error, linear quantile; not a confidence bound',
            'WAPE_percent':'100*sum(abs(error))/sum(abs(observed))',
            'nRMSE_percent':'100*RMSE/mean(abs(observed)); not normalized by range or standard deviation',
            'normalized_bias_percent':'100*bias/mean(abs(observed)); not hourly MPE',
            'MAPE_nonzero_percent':'100*mean(abs(error)/abs(observed)) over exactly nonzero observations',
            'MAPE_abs_actual_ge100_percent':'Same MAPE restricted to abs(observed)>=100MW, a fixed disclosed diagnostic threshold',
            'sMAPE_percent':'mean(200*abs(error)/(abs(predicted)+abs(observed))); both-zero terms defined as zero',
            'macro_equal_interface':'Arithmetic mean of the seven interface-specific metrics; each interface has equal weight',
            'macro_quantiles':'Mean of seven interface-specific quantiles; not the quantile of pooled errors',
            'pooled_interface_hours':'Metrics recomputed on all interface-hour observations; overlapping gates mean this is not statewide energy accuracy',
            'average_absolute_interface_bias_MW':'mean across interfaces of abs(mean hourly error for that interface))'
            ,'comparison_deltas':'delta_*_pp columns are percentage-point differences. Other delta columns use the stated physical units. relative_change_*_percent is100*(2025/2019-1).'
        },
        verification=dict(source_fingerprints=len(before),all_source_hashes_preserved=True,
            pinned_author_map_and_saved_annual_manifest_verified=True,
            current_arrays_scoring_receipt_verified=True,
            RMSE_squared_equals_bias_squared_plus_error_variance=True,
            maximum_discrepancy_against_saved_primary_metrics=float(max(discrepancies))),
        limitations=[
            'Cross-year descriptive comparison; load, generation, controls, topology, physics and cohorts differ.',
            '2019 uses prepared local-hour observations;2025 uses qualified physicalUTC hours. No harmonized same-input replay is claimed.',
            'Physical P32 meter equivalence and unchanged interface definitions across years are not certified.',
            'These metrics are recomputed from released outputs, not quoted from the paper, which used a different limit-normalized metric.',
            'MAPE near zero can dominate an average. Coverage and a fixed100MW sensitivity are exported; WAPE is the primary relative-error summary.',
            'Signed mean bias can cancel across hours and interfaces. Average absolute interface bias is provided separately.',
            'Percentile errors describe tails; no independence assumption or statistical-significance claim is made.',
            'Interface comparisons overlap electrically; pooled aggregates are descriptive benchmark statistics, not systemwide energy errors.'
        ],
        source_files=before,output_files=[rec(p) for p in outputs],script=rec(Path(__file__)))
    (OUT/'calculation_receipt.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    print(aggregate[['year','aggregation','bias_MW','MAE_MW','RMSE_MW','WAPE_percent','p95_AE_MW','average_absolute_interface_bias_MW']].to_string(index=False))
    print(json.dumps(dict(passed=True,max_saved_metric_difference=max(discrepancies),outputs=len(outputs))))


if __name__=='__main__':main()
