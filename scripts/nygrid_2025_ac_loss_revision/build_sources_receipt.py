"""Project reviewed revision evidence into a native Sources disclosure."""
from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_ac_loss_revision'


def query(key,label,files,definition,caveats,rows,columns,calculation,filters):
    return dict(id=key,source=dict(label=label,files=[dict(label=p) for p in files],
        metricDefinitions=[dict(label=label,definition=definition)],filters=filters,caveats=caveats),
        reportingPeriod='2025 hourly profiles',rows=rows,columns=columns,
        methods=[dict(language='calculation',code=calculation)])


def main():
    s=json.loads((OUT/'summary/revision_summary.json').read_text());c=s['counts']
    cols=['interface','hours','old_WAPE_percent','revised_WAPE_percent','change_percentage_points','old_bias_public_MW','revised_bias_public_MW']
    scores=query('paired-interfaces','Seven-interface annual comparison',
        ['summary/paired_annual_interfaces.csv','comparison/combined/public_interface_metrics.csv','comparison/combined/comparison_cohort.csv'],
        'Old and revised AC errors use exactly the same paired qualified hours and original physical-branch interface operator.',
        ['Physical P32 meter membership and the inherited numeric-as-MW interpretation remain uncertified.',
         f"Revised qualification: {c['revised_qualified']} of 8651 eligible hours; {c['new']} new successes and {c['lost']} lost prior successes.",
         'No hour passes the joint voltage/reactive/generator-capability gate; numerical qualification is conditional.'],
        s['paired_annual_interfaces'],cols,
        'WAPE =100 × sum(abs(model/gamma − observed))/sum(abs(observed)); bias = mean(model/gamma − observed). Gamma is used only for aggregate power, never branch amperes.',
        [f"Common cohort: {c['paired']} hours",'Annual 2025','Inherited signed-literal-from terminal convention'])
    zones=pd.read_csv(OUT/'comparison/combined/NY_zonal_loss_accounting.csv')
    zcols=['zone','hours','mean_allocated_loss_model_MW','maximum_loss_fraction','minimum_served_PD_model_MW','hours_loss_fraction_over25percent']
    loss=query('loss-accounting','Declared loss accounting and load partition',
        ['policy_evidence/historical_definition_supplement.json','policy_evidence/loss_accounting_policy_contract.json',
         'comparison/combined/NY_zonal_loss_accounting.csv','comparison/combined/regional_NY_terminal_import_errors.csv'],
        'NYISO actual zonal load is generation plus net interchange. Modeled delivered demand plus assigned internal NY losses equals that frozen loss-inclusive boundary target.',
        ['The 2025 NYISO guide confirms the source definition; half-end zonal loss ownership is a model assumption.',
         'Zonal losses and modeled delivered bus demand are not observed. Large loss fractions indicate unresolved model limitations.',
         'External areas supply their internal and NY-border corridor losses within original finite bounds; native PG, HQ and six DC transfers stay fixed.'],
        zones[zcols].to_dict('records'),zcols,
        'Compute P_loss_MW = baseMVA × R_pu × |Iseries_pu|² on original branches. Split within-NY corridor losses equally across endpoint zones. External corridor and external internal losses are supplied by the corresponding external generators. Solve voltages and these allocations simultaneously.',
        [f"All {c['revised_qualified']} revised qualified hours",'Eleven NY zones','No internal-interface fitting'])
    impedance=query('equivalent-provenance','Gilboa–Buchanan equivalent provenance',
        ['impedance/impedance_recommendation.json','impedance/actual_case_implementation_review.json','impedance/parameter_ledger.csv'],
        'Parent 224 is an added Cornell NYgrid E–G network equivalent; its released tuple is source-reproducible but not physically validated.',
        ['No installed direct line, physical route or utility impedance certificate was identified.',
         'The original R and B have no recovered asset derivation. Lower WAPE is not physical validation.',
         'Parent 224 is excluded from conductor temperature, DLR and synthetic facility-rating claims.'],
        [dict(parameter='Released R',value=.02,unit='pu on 100 MVA'),dict(parameter='Released X',value=.0147,unit='pu on 100 MVA'),
         dict(parameter='Released B',value=0,unit='pu on 100 MVA'),dict(parameter='Paper X approximation',value=.014649863474060072,unit='pu on 100 MVA')],
        ['parameter','value','unit'],
        'Paper X = 47 miles × 0.371 ohm/mile / (345 kV squared / 100 MVA). Restore the complete released R/X/B in two unchanged numerical sections; preserve all other branch parameters.',
        ['Parent 224, Gilboa 38 to Buchanan 77','Pinned author source','No observed-flow calibration'])
    payload=dict(schemaVersion=1,items=[dict(id='ac-loss-revision',title='2025 AC revision and NYISO comparison',queries=[scores,loss,impedance])])
    path=OUT/'summary/sources_receipt_input.json';path.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8');print(str(path))


if __name__=='__main__':main()
