"""Project reviewed metric results for the approved inline chart/source renderer."""
from pathlib import Path
import inspect,json
import pandas as pd
import compare_metrics as calculation

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2019_2025_error_metrics'
names={'DYSINGER EAST':'Dysinger East','WEST CENTRAL':'West Central','TOTAL EAST':'Total East',
       'MOSES SOUTH':'Moses South','CENTRAL EAST - VC':'Central East',
       'UPNY CONED':'UPNY-ConEd','SPR/DUN-SOUTH':'SPR/DUN'}
annual=pd.read_csv(OUT/'per_interface_metrics.csv')
aggregate=pd.read_csv(OUT/'aggregate_metrics.csv')
receipt=json.loads((OUT/'calculation_receipt.json').read_text())
order=['TOTAL EAST','DYSINGER EAST','WEST CENTRAL','UPNY CONED','CENTRAL EAST - VC','SPR/DUN-SOUTH','MOSES SOUTH']
rows=[]
for interface in order:
    for row in annual[annual.interface.eq(interface)].sort_values('year').to_dict('records'):
        rows.append({'Interface':names[interface],
                     'Model':'2019 released DC' if row['year']==2019 else '2025 current AC',
                     'RMSE_MW':row['RMSE_MW']})
source=dict(label='Saved NYgrid hourly predictions and NYISO observations',
    files=[{'label':'2019 author-release annual partitions 1-4'},
           {'label':'2025 moses_repair_v1 comparison arrays'},
           {'label':'Current-model pointer and scoring receipts'}],
    caveats=[
        '2019 uses 8,760 prepared local-hour positions; 2025 uses 8,651 source-qualified physical hours.',
        'The released 2019 DC case and current 2025 AC case have different inputs, physics and diagnostic operators. This comparison does not isolate topology effects.',
        'Physical meter equivalence across the named interfaces and years remains unverified. Values were recomputed from saved results; no new power-flow run was performed.'
    ],
    filters=['2019: authors_released_if_map','2025: candidate_all_success; annual; legacy_signed_literal_from'],
    metricDefinitions=[{'label':'RMSE','definition':'Square root of mean squared prediction error, in public-scale MW. Larger hourly errors receive more weight.'}],
    evidenceFlow=[{'kind':'validation','title':'Independent source reconciliation',
                   'detail':'Primary metrics match the saved source tables within '+str(receipt['verification']['maximum_discrepancy_against_saved_primary_metrics'])+' in their stated units. Source fingerprints and the current model pointer were checked.'}])
chart=dict(schemaVersion=1,id='nygrid-rmse-2019-2025',title='Interface RMSE: 2019 reference and current 2025',
    chart={'type':'bar','x':'Interface','y':'RMSE_MW','series':'Model','showXAxisLabel':False,'yLabel':'RMSE (public MW)'},
    rows=rows,columns=['Interface','Model','RMSE_MW'],source=source,height=410,theme='codex-classic',
    generatedAt=receipt['created_utc'])
query=dict(id='saved-hourly-rmse',source=source,reportingPeriod='2019 and 2025 annual cohorts',
           columns=list(rows[0]),rows=rows,
           methods=[{'language':'python','code':inspect.getsource(calculation.metrics)}])
chart_sources=dict(schemaVersion=1,items=[dict(id='interface-rmse',title='How do interface RMSE values compare?',queries=[query])])
summary_source=dict(label='Annual metric aggregation',
    files=source['files'],
    caveats=source['caveats']+[
        'The seven interfaces overlap electrically. Pooled results are benchmark statistics, not statewide energy error.',
        'Signed errors can cancel. Mean absolute interface bias is separately calculated.',
        'Raw MAPE is sensitive to near-zero observed flow. The 100-MW threshold is a disclosed sensitivity and changes the included population.'
    ],
    filters=source['filters'],
    metricDefinitions=[
        {'label':'Equal-interface mean','definition':'Arithmetic mean of seven interface-level metrics; each interface has equal weight.'},
        {'label':'Pooled metric','definition':'Recompute the metric over all seven interface-hour arrays. This differs from averaging RMSE, WAPE and quantiles.'},
        {'label':'Bias','definition':'Mean predicted minus observed flow. Positive values denote numerical overprediction in the declared orientation.'},
        {'label':'WAPE','definition':'Sum of absolute errors divided by sum of absolute observed flows, expressed as a percentage.'},
        {'label':'Error standard deviation','definition':'Population standard deviation of signed errors around their mean.'},
        {'label':'P95 absolute error','definition':'95th percentile of absolute hourly error. The equal-interface summary averages the seven individual percentiles; it is not a confidence bound.'},
        {'label':'MAPE sensitivity','definition':'Mean hourly absolute percentage error, calculated both for nonzero observations and for observations whose absolute flow is at least 100 MW.'}
    ],
    evidenceFlow=source['evidenceFlow'])
keys=['year','aggregation','bias_MW','MAE_MW','RMSE_MW','error_SD_MW','WAPE_percent',
      'nRMSE_percent','average_absolute_interface_bias_MW','p95_AE_MW',
      'MAPE_nonzero_percent','MAPE_abs_actual_ge100_percent','MAPE_ge100_coverage_percent']
summary_rows=aggregate[keys].to_dict('records')
summary_query=dict(id='annual-aggregates',source=summary_source,reportingPeriod='2019 and 2025 annual cohorts',
                   columns=keys,rows=summary_rows,
                   methods=[{'language':'python','code':inspect.getsource(calculation.metrics)}])
summary_sources=dict(schemaVersion=1,items=[dict(id='average-error-metrics',
    title='How do the average error metrics compare?',queries=[summary_query])])
for filename,payload in [('inline_rmse.json',chart),('inline_rmse_sources.json',chart_sources),
                          ('inline_summary_sources.json',summary_sources)]:
    (OUT/filename).write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(passed=True,chart_rows=len(rows),summary_rows=len(summary_rows))))
