"""Create reviewed, path-redacted source metadata for the inline answer."""
from pathlib import Path
import json
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_remaining_errors'
def item(id,title,files,definition,filters,caveats,rows=None,columns=None,validation=None):
    source={'label':title,'files':[{'label':x} for x in files],
            'metricDefinitions':[{'label':title,'definition':definition}], 'filters':filters,'caveats':caveats}
    if validation:source['evidenceFlow']=[{'kind':'validation','title':'Recorded checks','detail':validation}]
    query={'id':id+'-evidence','source':source,'reportingPeriod':'2025 hourly model results; diagnosis completed October15,2026'}
    if rows is not None:query.update(rows=rows,columns=columns)
    return {'id':id,'title':title,'queries':[query]}
def main():
    annual=pd.read_csv(OUT/'baseline/annual_metrics.csv')[['interface','hours','mae_public_MW','bias_public_MW','wape_percent']]
    pair=pd.read_csv(OUT/'baseline/pairwise_residual_structure.csv').iloc[0]
    phys=json.loads((OUT/'physics/physics_review.json').read_text())
    pjm=pd.read_csv(OUT/'probes/pjm_partition_responses.csv')
    rows=pjm[pjm.interface.isin(['TOTAL EAST','CENTRAL EAST - VC'])][['variant','interface','paired_hours','mean_response_public_MW']]
    payload={'schemaVersion':1,'items':[
        item('annual-errors','Remaining interface errors',['comparison_arrays.npz','annual_metrics.csv','baseline_receipt.json'],
             'MAE and signed bias compare the frozen original-from-terminal model cuts with the corresponding observations, in public-scale MW. WAPE divides total absolute error by total absolute observed flow.',
             ['Current equation, loss and recovery qualified cohort:8170hours','Failed solutions excluded'],
             ['Physical2025 P32 meter membership and the conditional numeric-as-MW source interpretation remain unverified.'],
             annual.to_dict('records'),[{'field':'interface','label':'Interface'},{'field':'hours','label':'Hours'},{'field':'mae_public_MW','label':'MAE(MW)'},{'field':'bias_public_MW','label':'Bias(MW)'},{'field':'wape_percent','label':'WAPE(%)'}],
             'All seven annual metrics reproduce the sealed current-model comparison exactly.'),
        item('western-pattern','Shared western residual',['pairwise_residual_structure.csv','month_metrics.csv','local_hour_metrics.csv','niagara_monthly_prior_oracle_comparison.csv','niagara_saved_DC_counterfactuals_same8170_metrics.csv','accounting_identity_review.json'],
             'Dysinger East and West Central share a variable residual; their complete model-cut identities isolate fixed zonal source inputs and small terminal corrections.',
             ['Identical8170-hour annual cohort'],['The pattern does not identify Niagara as the sole historical cause. EIA full-calendar means and selected-hour model means have different populations. Saved counterfactuals are DC responses.'],
             [{'correlation':float(pair.pearson),'difference_mae_public_MW':float(pair.difference_MAE_public_MW),'common_variance_percent':float(pair.equal_weight_common_mode_variance_percent)}],
             [{'field':'correlation','label':'Residual correlation'},{'field':'difference_mae_public_MW','label':'Residual difference MAE(MW)'},{'field':'common_variance_percent','label':'Common variance(%)'}],
             'Exact cut-identity closure is below1.9e-10modelMW. Zero lag has the lowest MAE for all seven interfaces on7936 common qualified triplets.'),
        item('pjm-response','Eastern import allocation sensitivity',['pjm_partition_plan.json','pjm_partition_responses.csv','independent_pjm_partition_review.json','current_AC_vs_corrected_DC_same_hours.csv'],
             'A bounded100publicMW transfer between external proxy buses130 and134 changes Total East and Central East while preserving regional generation totals.',
             ['15 calendar-selected hours','30 qualified directional cases'],['This is a local sensitivity, not observed historical dispatch or an annual improvement. Capacity-proportional alternatives were no-op controls.'],
             rows.to_dict('records'),[{'field':'variant','label':'Direction'},{'field':'interface','label':'Interface'},{'field':'paired_hours','label':'Hours'},{'field':'mean_response_public_MW','label':'Mean response(MW)'}],
             'Independent checks confirm finite unit bounds, regional total conservation, refreshed Q capabilities and score agreement within5.7e-14MW.'),
        item('physical-limitations','Loss and voltage limitations',['physics_review.json','parent_loss_concentration.csv','voltage_bound_concentration.csv','paired_physical_responses.csv','independent_probe_review.json'],
             'Annual losses are model-scale MW. Parent41 dominates zoneF assigned loss; all qualified annual hours exceed the voltage upper bound somewhere.',
             ['8170 annual qualified hours','Parent41 sensitivity uses15 calendar-selected hours'],
             ['The parent41 admittance probe does not rebuild conductor or DLR metadata and was not promoted. Equation qualification does not establish operating feasibility.'],
             [{'parent41_mean_loss_model_MW':phys['parent41']['mean_loss_model_MW'],'F_loss_share_percent':100*phys['parent41']['share_of_F_assigned_loss'],'overvoltage_hours':phys['voltage']['hours_above_upper_limit'],'maximum_voltage_pu':phys['voltage']['maximum_pu']}],
             [{'field':'parent41_mean_loss_model_MW','label':'Parent41 mean loss(modelMW)'},{'field':'F_loss_share_percent','label':'Share of F loss(%)'},{'field':'overvoltage_hours','label':'Overvoltage hours'},{'field':'maximum_voltage_pu','label':'Maximum voltage(pu)'}],
             'The15 baseline cases reproduce all105 saved interface values exactly. Parent41 importedR/X reduces its sampled mean loss92.87→2.34modelMW with negligible interface response.')
    ]}
    (OUT/'inline_sources.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    print('Wrote four reviewed source cards with no absolute paths or external publication.')
if __name__=='__main__':main()
