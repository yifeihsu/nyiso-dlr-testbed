"""Verify and seal the source-corrected western research delivery."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_western_audit'
MANIFEST=OUT/'delivery_manifest.json'
REPORT=ROOT/'NYGRID_2025_WESTERN_SOURCE_AUDIT.md'

def require(value,message):
    if not value: raise ValueError(message)

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def read(name): return json.loads((OUT/name).read_text(encoding='utf-8'))

def check(rows):
    require(bool(rows),'Empty proof manifest')
    for row in rows:
        path=Path(row['path']); path=path if path.is_absolute() else ROOT/path
        require(path.is_file() and sha(path)==row['sha256'],'Changed dependency: '+str(path))

def finalize(verify=False):
    for name in ['dispatch/dispatch_receipt.json','dispatch/all_boundary_dispatch_receipt.json']:
        receipt=read(name)
        require(receipt['passed'] and not receipt['internal_interface_observations_used'],'Unqualified reconstruction '+name)
        require(receipt['capacity_infeasible_hours']==0,'Unexpected infeasible dispatch')
        check(receipt['dependencies'])
        file='actual_Ontario_dispatch.mat' if name=='dispatch/dispatch_receipt.json' else 'all_boundary_actual_dispatch.mat'
        require(sha(OUT/'dispatch'/file)==receipt['dispatch_file_sha256'],'Changed dispatch output')
    source=read('boundary_source_review/independent_boundary_review.json')
    require(source['passed'] and source['status']=='passed_source_only_all_four_boundary_review','External source review incomplete')
    check(source['dependencies'])
    gate=read('validation/source_gate_review.json')
    require(gate['status']=='passed' and gate['tests']>=52 and gate['failures']==gate['errors']==0,'Ontario guards failed')
    check(gate['dependencies'])
    all_gate=read('dispatch/all_boundary_guard_test_receipt.json')
    require(all_gate['passed'] and all_gate['tests']>=27 and all_gate['failures']==all_gate['errors']==0,
            'All-boundary guards failed')
    check(all_gate['dependencies'])
    replay=read('replay/provenance.json')
    require(replay['passed'] and len(replay['variants'])==10 and len(replay['baseline_replays'])==2,'Incomplete replay')
    require(not replay['internal_interface_observations_read'] and not replay['topology_changed'],'Replay scope changed')
    require(replay['preferred_mode']=='combined','Primary mode changed')
    check(replay['dependencies'])
    check([dict(path=r['file'],sha256=r['sha256']) for r in replay['variants']])
    common=np.load(OUT/'replay/paired_common_mask.npy',allow_pickle=False)
    require(common.dtype==bool and common.shape==(8760,) and common.sum()==replay['qualified_common_hours'],'Changed paired mask')
    score=read('comparison/scoring_receipt.json')
    require(score['passed'] and score['internal_observations_only_posthoc'],'Invalid scoring scope')
    require(score['replay_receipt_sha256']==sha(OUT/'replay/provenance.json'),'Stale scoring receipt')
    require(score['code_sha256']==sha(ROOT/'scripts/nygrid_2025_western_audit/replay_western.py'),'Scoring code changed')
    require(score['original_observation_sha256']==sha(ROOT/'output/nygrid_2025_inputs/load_source/interface_wide.csv'),'Scoring observations changed')
    annual=pd.read_csv(OUT/'comparison/interface_summary.csv')
    monthly=pd.read_csv(OUT/'comparison/interface_monthly.csv')
    require(len(annual)==168 and len(monthly)==2016,'Incomplete seven-interface comparisons')
    require(set(annual.variant)=={t+'_'+m for t in ['dated','year_end'] for m in replay['modes']},'Missing comparison variant')
    require(set(annual.loc[annual.cohort.eq('paired_common'),'hours'])=={int(common.sum())},'Unequal paired cohorts')
    independent=read('validation/independent_validation.json')
    require(independent['passed'],'Independent annual validation failed')
    check(independent['dependencies'])
    matlab=read('validation/matlab_validation.json')
    require(matlab['passed'] and matlab['fresh_MATPOWER_snapshots']>=60,'Fresh MATLAB verification incomplete')
    require(matlab['missing_hour_rejected'] and matlab['IESO_suspect_hours_rejected']==6,'Missing source not rejected')
    check(matlab['dependencies'])
    figure=read('figures/figure_validation.json')
    require(figure['passed'] and figure['paired_hours']==int(common.sum()),'Figure cohort changed')
    check(figure['inputs']);check(figure['outputs'])
    effects=read('effects/effects_validation.json')
    require(effects['passed'] and effects['paired_hours']==int(common.sum()),'Post-hoc decomposition differs')
    check(effects['dependencies'])
    links=[]
    for href in re.findall(r'\]\(([^\n]+?)\)',REPORT.read_text(encoding='utf-8')):
        href=href.strip('<>').split('#')[0]
        if not href or '://' in href:continue
        path=ROOT/unquote(href)
        require(path==MANIFEST or path.is_file(),'Missing report link: '+href)
        links.append(href)
    files=[p for folder in [OUT,ROOT/'scripts/nygrid_2025_western_audit'] for p in folder.rglob('*')
           if p.is_file() and '__pycache__' not in p.parts and p!=MANIFEST]
    files += [REPORT,ROOT/'.gitattributes',ROOT/'System Matpower Format/npcc_nygrid_2025_western_corrected_dc.m']
    entries=[]
    for path in sorted(files):
        require(path.stat().st_size<100*1024**2,'Oversized delivery file: '+str(path))
        entries.append(dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    result=dict(status='verified_source_conditioned_western_DC_reconstruction',
        buses=148,native_generators=1436,external_equivalents=28,primary_mode='combined',
        all_boundary_qualified_hours=replay['all_boundary_qualified_hours'],
        Ontario_only_qualified_hours=replay['Ontario_only_qualified_hours'],paired_hours=int(common.sum()),
        annual_score_rows=len(annual),monthly_score_rows=len(monthly),
        raw_source_and_prior_artifacts_preserved=True,internal_interface_fitting=False,
        physical_western_PAR_and_complete_2025_interface_meter_membership_verified=False,
        actual_hourly_native_unit_dispatch_observed=False,AC_operational_feasibility_verified=False,
        report_local_links_checked=len(links),files=len(entries),total_bytes=sum(e['bytes'] for e in entries),
        maximum_file_bytes=max(e['bytes'] for e in entries),entries=entries)
    if verify:require(read('delivery_manifest.json')==result,'Delivery manifest is stale')
    else:MANIFEST.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='entries'},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--verify',action='store_true')
    finalize(parser.parse_args().verify)
