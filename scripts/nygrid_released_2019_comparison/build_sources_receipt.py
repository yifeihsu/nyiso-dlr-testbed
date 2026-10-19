"""Prepare a source receipt that explicitly identifies the released baseline."""
from pathlib import Path
import json
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_released_2019_comparison'
def main():
    r=json.loads((OUT/'comparison_receipt.json').read_text());assert r['passed'] and not r['our_derived140bus_case_used']
    a=pd.read_csv(OUT/'independent/released2019_vs_othermodel2025.csv')
    payload={'schemaVersion':1,'items':[
        {'id':'author-release-identity','title':'Authors’ released model and 2019 inputs','queries':[{'id':'source-identity-check','reportingPeriod':'Authors’ 2019 model year; checks performed October 15, 2026',
         'source':{'label':'Pinned author release and fresh source checks','files':[{'label':'upstream_manifest.json'},{'label':'fresh_author_release_checks.csv'},{'label':'fresh_author_release_receipt.json'},{'label':'independent_released_2019_review.json'}],
                   'metricDefinitions':[{'label':'Reference model','definition':'The reference is the authors’ released 57-bus DC model, 94 AC branches, 271 generator records and four DC records, using their supplied 2019 inputs.'}],
                   'caveats':['The runtime uses MATLAB R2026a, MATPOWER 8.1 legacy core and a pinned historical reduction toolbox; the exact software revision used for the published figure is unknown.'],
                   'evidenceFlow':[{'kind':'validation','title':'Identity and numerical checks','detail':'All 73 author files match SHA-256 and Git-blob identities. Twelve fresh runs of unmodified author source match saved inputs and solutions exactly; all 8760 verified annual states are rescored. No reconstructed 140-bus case or 2025 inputs enter the 2019 runs.'}]},
         'rows':[{'annual_hours':8760,'fresh_source_check_hours':12,'maximum_input_or_solution_difference':0}],
         'columns':[{'field':'annual_hours','label':'Annual hours rescored'},{'field':'fresh_source_check_hours','label':'Fresh source checks'},{'field':'maximum_input_or_solution_difference','label':'Maximum difference'}]}]},
        {'id':'released-model-errors','title':'Two readouts of the same unchanged released model','queries':[{'id':'recomputed-comparison','reportingPeriod':'2019 released model versus separate current 2025 model',
         'source':{'label':'Released-model branch-flow aggregation','files':[{'label':'released_2019_recomputed_metrics.csv'},{'label':'released_operator_members.csv'},{'label':'released2019_vs_othermodel2025.csv'},{'label':'flow4Plot.m'},{'label':'updateOpCond.m'}],
                   'metricDefinitions':[{'label':'WAPE','definition':'WAPE divides total absolute flow mismatch by total absolute observed flow. Both 2019 readouts use the same unchanged power-flow solutions.'}],
                   'filters':['Authors’ supplied 2019 inputs and all 8760 prepared local hours','Current model shown only as a separate 2025 comparison with 8651 eligible physical hours'],
                   'caveats':['The plotting helper and the authors’ own interface map disagree for five interfaces. Reading the supplied map changes the measurement, not the network or operating inputs.','The 2019 columns are recomputed release results, not numbers quoted from a published WAPE table.','This remains a cross-year, different-input comparison; it is not a controlled model-improvement experiment.','Neither literal plotting nor the interface-map result is claimed to reproduce the published Figure 5 exactly.']},
         'rows':a[['interface','strict_literal_2019_WAPE_percent','authors_ifmap_2019_WAPE_percent','other_model_2025_WAPE_percent']].to_dict('records'),
         'columns':[{'field':'interface','label':'Interface'},{'field':'strict_literal_2019_WAPE_percent','label':'Literal plotting WAPE (%)'},{'field':'authors_ifmap_2019_WAPE_percent','label':'Authors’ map WAPE (%)'},{'field':'other_model_2025_WAPE_percent','label':'Current 2025 WAPE (%)'}]}]}
    ]}
    (OUT/'inline_sources.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
