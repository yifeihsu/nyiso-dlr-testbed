"""Render-ready, path-redacted evidence cards for the final repair answer."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_physical_repair'
def main():
    p=json.loads((OUT/'independent/annual_physics_review.json').read_text())
    s=json.loads((OUT/'annual/physical_repair_v1/comparison/scoring_receipt.json').read_text())
    assert p['passed'] and p['completed_annual_review'] and s['passed'] and s['completed']
    def card(key,title,files,definition,rows,columns,caveats,check):
        return {'id':key,'title':title,'queries':[{'id':key+'-evidence','reportingPeriod':'2025 hourly model; repaired annual replay completed October 15, 2026',
            'source':{'label':title,'files':[{'label':x} for x in files],
                      'metricDefinitions':[{'label':title,'definition':definition}],
                      'filters':['The frozen 2025 source eligibility mask is unchanged.'],
                      'caveats':caveats,'evidenceFlow':[{'kind':'validation','title':'Independent checks','detail':check}]},
            'rows':rows,'columns':columns}]}
    loss=p['paired_parent41_loss_model_MW'];vol=p['target_voltage'];g=p['remaining_global_limits']
    items=[card('annual-coverage','Annual coverage and qualification',['annual_receipt.json','annual_input_accounting_review.json','annual_physics_review.json','scoring_receipt.json'],
        'Equation qualification requires convergence, AC equations, loss accounting and voltage/current recovery; operating limits are checked separately.',
        [{'source_hours':8651,'qualified_hours':s['candidate_qualified_hours'],'recovered_hours':s['candidate_new_success_hours'],'lost_hours':s['current_success_lost_hours'],'source_excluded_hours':109,'operating_qualified_hours':s['full_operating_qualified_hours']}],
        [{'field':'source_hours','label':'Eligible hours'},{'field':'qualified_hours','label':'Equation-qualified'},{'field':'recovered_hours','label':'Recovered hours'},{'field':'lost_hours','label':'Lost successes'},{'field':'source_excluded_hours','label':'Source-excluded'},{'field':'operating_qualified_hours','label':'Operating-qualified'}],
        ['Equation-qualified results do not establish whole-network operating feasibility.'],
        'All 8,760 clock positions and source masks are preserved. Independent raw branch laws, nodal balance, generator capabilities, regional accounting and passive recovery pass.'),
        card('parent41-loss','Parent 41 loss correction',['parent41_parameters.json','independent_candidate_review.json','target_parent_metrics.csv','annual_physics_review.json'],
        'Parent 41 mean real loss is compared on the identical 8,170 previously successful hours, in model-scale MW.',
        [{'previous_mean_MW':loss['old_mean'],'repaired_mean_MW':loss['new_mean'],'reduction_percent':loss['mean_reduction_percent'],'paired_hours':8170,'current_limit_exceedance_hours_all_new':p['candidate_parent41_hardware_current_exceedance_hours']}],
        [{'field':'previous_mean_MW','label':'Previous mean loss (model MW)'},{'field':'repaired_mean_MW','label':'Repaired mean loss (model MW)'},{'field':'reduction_percent','label':'Reduction (%)'},{'field':'paired_hours','label':'Matched hours'},{'field':'current_limit_exceedance_hours_all_new','label':'2,000 A exceedances in all 8,651 hours'}],
        ['The R/X-conditioned conductor is a synthetic realization, not an identified installed asset. The existing aggregate 2,000 A apparatus ceiling is retained and still fails in some hours.'],
        'Independent formulas verify the imported R/X, geometric B, conductor material data and Joule-loss identity; compiled templates preserve the corresponding thermal metadata.'),
        card('target-voltages','Voltage fixes and remaining limits',['compensation_design_review.json','target_parent_metrics.csv','annual_physics_review.json'],
        'The complete parent 185 and 195 corridors are checked against the unchanged 0.95–1.05 pu bounds in all 8,651 solved hours.',
        [{'parent':int(k),'minimum_pu':x['min_VM'],'maximum_pu':x['max_VM'],'violation_hours':x['violation_hours']} for k,x in vol.items()],
        [{'field':'parent','label':'Parent'},{'field':'minimum_pu','label':'Minimum voltage (pu)'},{'field':'maximum_pu','label':'Maximum voltage (pu)'},{'field':'violation_hours','label':'Violation hours'}],
        [f"Other locations still violate operating limits: {g['overvoltage_hours']} overvoltage hours and {g['undervoltage_hours']} undervoltage hours in the new qualified cohort.",
         'Distributed reactor placement is a declared synthetic design; total nominal compensation, conductor parameters, voltage setpoints and limits are unchanged.'],
        'Independent reconstruction confirms zero target-corridor voltage violations, exact total reactor rating conservation, full-axis shunt metadata and passive-network voltage recovery.')]
    (OUT/'summary/inline_sources.json').write_text(json.dumps({'schemaVersion':1,'items':items},indent=2)+'\n',encoding='utf-8')
    print('Three reviewed repair evidence cards prepared.')
if __name__=='__main__':main()
