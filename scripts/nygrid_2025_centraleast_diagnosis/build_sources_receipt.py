"""Project reviewed CENTRAL EAST evidence into one native Sources disclosure."""
from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_centraleast_diagnosis'


def query(key, label, files, definition, caveats, rows, columns, calculation):
    return dict(id=key, source=dict(label=label,files=[dict(label=p) for p in files],
                metricDefinitions=[dict(label=label,definition=definition)],
                filters=['Interface: CENTRAL EAST–VC','Cohort: 8,494 unchanged matched hours','Terminal convention: inherited receiving side'],
                caveats=caveats),reportingPeriod='2025 hourly profiles',rows=rows,columns=columns,
                methods=[dict(language='calculation',code=calculation)])


def main():
    s=json.loads((OUT/'summary/diagnosis_summary.json').read_text())
    m=pd.read_csv(OUT/'summary/stage_metrics.csv')
    labels={'original_network_DC':'Original DC','AC_network_DC':'DC on AC network',
            'AC_network_DC_half_losses':'DC plus solved AC losses','AC_network_AC':'Current AC'}
    preview=m[m.stage.isin(labels)].copy();preview['stage']=preview.stage.map(labels)
    cols=['period','stage','hours','mean_flow_public_MW','bias_public_MW','mae_public_MW','wape_percent']
    stages=query('matched-stages','Matched DC/AC stages',
        ['summary/stage_metrics.csv','summary/hourly_stage_comparison.csv','measurement/raw_source_check.json'],
        'WAPE compares absolute prediction errors with the sum of absolute observed flow on identical hours; mean signed error distinguishes underprediction from overprediction.',
        ['The model is synthetic. Physical P32 meter membership and the inherited numeric-as-MW interpretation remain uncertified.',
         'The loss-loaded intermediate uses losses already calculated by the AC solver.',
         'The 157 failed AC hours and 109 source-excluded hours are outside this matched comparison.'],
        preview[cols].to_dict('records'),cols,
        'WAPE = 100 × sum(abs(predicted − observed)) / sum(abs(observed)). Mean signed error = mean(predicted − observed). Only aggregate model MW is divided by gamma.')
    stages['preview']=dict(kind='aggregate',note='Annual and monthly summaries for the four plotted stages.',totalRows=len(preview))
    parameters=pd.read_csv(ROOT/'output/nygrid_2025_ac_system/branches/branch_assignments.csv')
    x=parameters[parameters.branch_row==224].iloc[0]
    reactance=query('reactance-intervention','Gilboa–Buchanan reactance diagnostic',
        ['model_delta/fallback_provenance_review.json','model_delta/annual_DC_independent_review.json',
         'experiments/annual_DC_bridge/variant_summary.csv','branches/branch_assignments.csv'],
        'The row-224 intervention changes only its reactance, leaving other network parameters and prescribed injections fixed; the reported share concerns mean construction-related flow displacement.',
        ['The reactance values and preferred route describe model assumptions, not verified installed equipment.',
         'A lower WAPE does not establish physical impedance correctness.',
         '96.88 percent refers to mean construction-induced flow displacement, not the total WAPE increase.'],
        [dict(quantity='Original reactance',value=float(x.original_x_pu),unit='pu on 100 MVA'),
         dict(quantity='Applied reactance',value=float(x.applied_x_pu),unit='pu on 100 MVA'),
         dict(quantity='Synthetic preferred route',value=float(x.route_length_m)/1000,unit='km'),
         dict(quantity='Mean displacement removed by restoring only X224',value=s['parent224_X_restoration_mean_reduction_public_MW'],unit='public MW'),
         dict(quantity='Share of mean construction displacement removed',value=s['parent224_share_of_mean_construction_displacement_percent'],unit='percent')],
        ['quantity','value','unit'],
        'Mean construction displacement = mean(AC-network DC − archived DC). Row-224 effect = mean(AC-network DC − row224-X-restored DC); share = effect / construction displacement.')
    allocations=pd.read_csv(OUT/'experiments/annual_loss_loaded_DCF/allocation_summary.csv')
    lcols=['allocation','hours','mean_loss_allocation_delta_public_MW','mean_remaining_AC_minus_loss_loaded_public_MW','mean_absolute_remaining_public_MW']
    losses=query('loss-reconstruction','Solved-loss reconstruction',
        ['experiments/annual_loss_loaded_DCF/allocation_summary.csv','model_delta/annual_loss_independent_review.json',
         'summary/diagnosis_summary.json'],
        'Solved AC branch losses are added as diagnostic withdrawals and supplied by the existing Clay reference generator; the resulting DC solution reconstructs most of the same-network AC flow increase.',
        ['This is an after-the-fact reconstruction from solved AC losses, not an independent forecast or unique causal decomposition.',
         'Half-end, original-from-end and original-to-end allocation are sensitivity conventions, not confidence intervals.',
         'The production model, profiles and prior results remain unchanged.'],
        allocations[lcols].to_dict('records'),lcols,
        'For each runtime branch, loss = PF + PT. Allocate loss to its endpoints, add those withdrawals to the diagnostic DC case, and retain non-slack PG and all six transfer targets. The reference increment must equal total baseline AC loss.')
    payload=dict(schemaVersion=1,items=[dict(id='central-east-regression',title='Why CENTRAL EAST–VC WAPE increased',queries=[stages,reactance,losses])])
    path=OUT/'summary/sources_receipt_input.json';path.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    print(str(path))


if __name__=='__main__': main()
