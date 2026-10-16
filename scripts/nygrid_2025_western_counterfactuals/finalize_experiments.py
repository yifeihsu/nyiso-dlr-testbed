"""Verify the matched experiment delivery and unchanged parent evidence."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import re
from urllib.parse import unquote
import numpy as np
import pandas as pd
from common import OUT,PARENT,ROOT,atomic_json,check_records,load_baseline,read,record,require,sha

MANIFEST=OUT/'delivery_manifest.json'

def finalize(verify=False):
    b=load_baseline();q=b['qualified']
    design=read(OUT/'design/experiment_plan.json');check_records(design['dependencies'])
    snapshot=read(OUT/'design/preservation_snapshot.json')
    note_path='NYGRID_2025_WESTERN_SOURCE_AUDIT.md'
    check_records([r for r in snapshot['preserved_parent_files'] if r['path']!=note_path])
    local_note=[r for r in snapshot['preserved_parent_files'] if r['path']==note_path][0]
    canonical_note=[r for r in read(PARENT/'delivery_manifest.json')['entries'] if r['path']==note_path][0]
    # The annotation is pre-existing, uncommitted user prose, not an input to
    # any calculation. Preserve it locally; a clean checkout contains the
    # canonical parent document and must still verify the numerical delivery.
    accepted_notes={local_note['sha256'],canonical_note['sha256']} if verify else {local_note['sha256']}
    require(sha(ROOT/note_path) in accepted_notes,'Unrecognized change to the prior report')
    # Additional scope rules may be appended to .gitattributes. Its original
    # bytes are retained as a prefix; no old evidence policy is rewritten.
    parent_attributes=[r for r in read(PARENT/'delivery_manifest.json')['entries'] if r['path']=='.gitattributes']
    require(len(parent_attributes)==1,'Missing original attribute policy')
    old=parent_attributes[0];raw=(ROOT/'.gitattributes').read_bytes()
    require(hashlib.sha256(raw[:old['bytes']]).hexdigest()==old['sha256'],'Original Git attribute policy changed')
    for name,kind in [('inputs/niagara_receipt.json','generation'),('inputs/load_receipt.json','load')]:
        d=read(OUT/name);require(d['passed'] and d['datasettype']==kind,'Input family failed')
        check_records(d['dependencies']);check_records([dict(path=s['file'],sha256=s['sha256']) for s in d['scenarios']])
    ng=read(OUT/'inputs/niagara_input_validation.json')
    require(ng['passed'] and ng['tests']==8 and ng['failures']==ng['errors']==0,'Niagara input checks failed')
    require(ng['source_receipt_sha256']==sha(OUT/'inputs/niagara_receipt.json'),'Stale Niagara validation')
    require(ng['validation_code_sha256']==sha(ROOT/'scripts/nygrid_2025_western_counterfactuals/test_niagara_inputs.py'),'Niagara checker changed')
    mp=read(OUT/'mapping/mapping_receipt.json');require(mp['passed'] and mp['no_parameter_or_operator_fit'],'Mapping source audit failed')
    check_records(mp['dependencies']);check_records(mp['outputs'])
    require(sha(OUT/'mapping/operators.npz')==mp['operators_sha256'],'Operator matrices changed')
    require(mp['complete_source_backed_physical_alternatives']==0,'Physical mapping scope unexpectedly changed')
    r=read(OUT/'replay/replay_receipt.json')
    require(r['passed'] and len(r['cases'])==16 and len(r['excluded_unscored_cases'])==2
            and r['fixed_qualified_hours']==8651 and not r['internal_observations_read'],'Incomplete matched replay')
    check_records(r['dependencies']);check_records([dict(path=c['file'],sha256=c['sha256']) for c in r['cases']])
    check_records([r['fixture_file']])
    op=read(OUT/'mapping/operator_replay_receipt.json')
    require(op['passed'] and len(op['cases'])==3 and not op['internal_observations_read'],'Incomplete operator-only evaluation')
    check_records(op['dependencies']);check_records([dict(path=c['file'],sha256=c['sha256']) for c in op['cases']])
    score=read(OUT/'comparison/scoring_receipt.json')
    require(score['passed'] and score['fixed_hours']==8651 and score['scenarios']==19
            and score['internal_observations_posthoc_only'] and score['no_infeasible_literal_hypothesis_scored'],'Invalid scoring scope')
    check_records(score['dependencies']);check_records(score['outputs'])
    a=pd.read_csv(OUT/'comparison/annual_metrics.csv');m=pd.read_csv(OUT/'comparison/monthly_metrics.csv')
    require(len(a)==133 and len(m)==1596 and set(a.hours)=={8651},'Incomplete or unmatched comparison rows')
    p=read(OUT/'validation/independent_load_interaction_validation.json')
    require(p['passed'] and p['scenario_hour_checks']==138416 and p['metadata_guard_mutations_rejected']==5,'Independent equations incomplete')
    check_records(p['dependencies'])
    s=read(OUT/'validation/mapping_score_validation.json')
    require(s['passed'] and s['failed_checks']==0 and s['annual_metric_rows']==133 and s['monthly_metric_rows']==1596,
            'Independent score validation incomplete')
    check_records(s['dependencies'])
    mat=read(OUT/'validation/matlab_validation.json')
    require(mat['passed'] and mat['fresh_MATPOWER_snapshots']==82 and mat['scenarios']==16,'Fresh MATLAB validation incomplete')
    check_records(mat['dependencies'])
    fig=read(OUT/'figures/figure_validation.json');require(fig['passed'] and fig['fixed_hours']==8651,'Figure scope changed')
    check_records(fig['inputs']);check_records(fig['outputs'])
    portability=read(OUT/'validation/document_dependency_portability.json')
    require(portability['passed'] and portability['all_experiment_plans_input_NPZ_replay_NPZ_and_metric_CSV_bytes_identical'],
            'Documentation dependency repair changed the experiment')
    check_records(portability['files'])
    report=ROOT/'NYGRID_2025_WESTERN_CONTROLLED_TESTS.md';links=[]
    for href in re.findall(r'\]\(([^\n]+?)\)',report.read_text(encoding='utf-8')):
        href=href.strip('<>').split('#')[0]
        if not href or '://' in href:continue
        path=ROOT/unquote(href);require(path==MANIFEST or path.is_file(),'Missing report link: '+href);links.append(href)
    files=[p for folder in [OUT,ROOT/'scripts/nygrid_2025_western_counterfactuals'] for p in folder.rglob('*')
           if p.is_file() and '__pycache__' not in p.parts and p!=MANIFEST]
    files += [report,ROOT/'.gitattributes']
    entries=[]
    for path in sorted(files):
        require(path.stat().st_size<100*1024**2,'Oversized evidence file: '+str(path))
        entries.append(dict(**record(path),bytes=path.stat().st_size))
    result=dict(status='validated_fixed_cohort_source_defined_counterfactuals_no_default_promotion',
        fixed_hours=int(q.sum()),powerflow_scenarios=16,operator_only_comparisons=3,
        scored_scenarios=19,unscored_literal_infeasible_hypotheses=2,annual_metric_rows=133,monthly_metric_rows=1596,
        internal_flow_fitting=False,actual_dispatch_or_physical_gate_error_uniquely_identified=False,
        complete_physical_2025_operator_crosswalk_available=False,old_numerical_artifacts_unchanged=True,
        existing_report_annotation_preserved_during_run=True,
        prior_report_is_not_a_numerical_dependency=True,
        accepted_prior_document_sha256=sorted({local_note['sha256'],canonical_note['sha256']}),default_model_changed=False,
        local_report_links_checked=len(links),files=len(entries),total_bytes=sum(e['bytes'] for e in entries),
        maximum_file_bytes=max(e['bytes'] for e in entries),entries=entries)
    if verify:require(read(MANIFEST)==result,'Delivery manifest is stale')
    else:atomic_json(MANIFEST,result)
    print({k:v for k,v in result.items() if k!='entries'})

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--verify',action='store_true');finalize(parser.parse_args().verify)
