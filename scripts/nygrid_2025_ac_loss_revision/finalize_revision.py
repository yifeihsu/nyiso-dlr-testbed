"""Seal the versioned AC revision without changing any earlier delivery."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_ac_loss_revision'
REPORT=ROOT/'NYGRID_2025_AC_LOSS_REVISION.md'
MANIFEST=OUT/'DELIVERY_MANIFEST.json'
BASELINE='a7c90215b22f688acea9ee8a08a08fc4385be494'
RUN='released_equivalent_boundary_consistent'


def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def record(path):return dict(sha256=sha(path),bytes=path.stat().st_size)


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def verify_records(value,context):
    count=0
    if isinstance(value,dict):
        if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str):
            ref=Path(value['path']);p=ROOT/ref
            if not p.is_file():p=context.parent/ref
            assert p.is_file(),f'Missing bound source in {context}: {ref}'
            assert sha(p)==value['sha256'].lower(),f'Stale bound source in {context}: {ref}'
            count+=1
        for child in value.values():count+=verify_records(child,context)
    elif isinstance(value,list):
        for child in value:count+=verify_records(child,context)
    return count


def expected_manifest():
    preserved={}
    for namespace in ['nygrid_2025_ac_system','nygrid_2025_acpf_profile_audit','nygrid_2025_compact_ac','nygrid_2025_centraleast_diagnosis']:
        rel=f'output/{namespace}/DELIVERY_MANIFEST.json';p=ROOT/rel
        committed=subprocess.check_output(['git','show',BASELINE+':'+rel],cwd=ROOT)
        assert hashlib.sha256(committed).hexdigest()==sha(p),f'Prior manifest changed: {rel}'
        old=read(p)
        for name,r in old['files'].items():assert record(ROOT/name)==r,f'Prior delivery changed: {name}'
        preserved[namespace]=dict(files=len(old['files']),manifest_sha256=sha(p))
    assert sha(ROOT/'NYGRID_2025_WESTERN_SOURCE_AUDIT.md')=='e21175a942b85519688708eaba22b2100ad06281b256a5d1dd66b17371b3d4cb'
    required=[
        'summary/revision_summary.json','summary/paired_annual_interfaces.csv','summary/annual_interface_comparison.png',
        'summary/sources_receipt_input.json','impedance/impedance_recommendation.json','impedance/actual_case_implementation_review.json',
        f'impedance/{RUN}_annual_arrays_independent_review.json','impedance/representative_factorial_independent_review.json',
        'policy_evidence/policy_evidence_audit.json','policy_evidence/historical_definition_supplement.json',
        'validation/source_receipt.json','validation/policy_contract/policy_contract_receipt.json','validation/jacobian/jacobian_receipt.json',
        'validation/pairs/simultaneous_representatives/pair_receipt.json',f'validation/annual/{RUN}/annual_loss_policy_receipt.json',
        'comparison/combined/scoring_receipt.json','comparison/independent/final_scoring_independent_review.json',
        'comparison/final_delivery_review.json']
    for name in required:assert (OUT/name).is_file(),f'Missing completion evidence: {name}'
    for name in required:
        if name.endswith('.json') and name not in ['summary/sources_receipt_input.json',f'validation/annual/{RUN}/annual_loss_policy_receipt.json']:
            assert read(OUT/name)['passed'],f'Validation failed: {name}'
    annual=read(OUT/f'validation/annual/{RUN}/annual_loss_policy_receipt.json')
    summary=read(OUT/'summary/revision_summary.json')
    assert annual['completed'] and annual['replay_integrity_passed'] and annual['attempted_hours']==8651
    assert annual['source_files_unchanged_during_replay'] and annual['solver_exceptions']==0
    assert annual['native_voltage_solver_unknowns_retained_bus_count']==148
    assert annual['no_full_network_Newton_used'] and not annual['OPF_or_observation_fitting_used']
    assert not summary['physical_parent224_impedance_validated'] and not summary['internal_interface_fitting_used']
    factorial=read(OUT/'validation/representative_factorial/factorial_receipt.json')
    assert factorial['completed'] and factorial['source_files_unchanged'] and factorial['no_fitting_or_tuning']
    assert factorial['representative_attribution_not_annual_effect_estimate']
    assert factorial['common_success_hour_count']==summary['representative_factorial_common_hours']
    paths=[REPORT,ROOT/'System Matpower Format/run_nygrid_2025_loss_consistent_acpf.m']
    paths += [p for base in [ROOT/'scripts/nygrid_2025_ac_loss_revision',OUT] for p in base.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p!=MANIFEST]
    checks=0
    for p in paths:
        if p.suffix=='.json':checks+=verify_records(read(p),p)
    links=[]
    for value in re.findall(r'\]\(([^)]+)\)',REPORT.read_text(encoding='utf-8')):
        if value.startswith(('http://','https://','#')):continue
        p=ROOT/unquote(value.strip('<>').split('#')[0])
        assert p.is_file() or p==MANIFEST,f'Broken report link: {value}'
        links.append(value)
    files={p.relative_to(ROOT).as_posix():record(p) for p in sorted(set(paths))}
    assert max(r['bytes'] for r in files.values())<100_000_000
    return dict(schema_version=1,status='completed_versioned_synthetic_AC_loss_policy_replay_with_explicit_physical_limits',
        baseline_HEAD=BASELINE,prior_deliveries_byte_preserved=preserved,
        source_tuple_provenance_verified=True,physical_parent224_impedance_validated=False,
        native_PG_HQ_and_DC_targets_preserved=True,loss_ownership_declared_not_observed=True,
        counts=summary['counts'],proof_hash_checks=checks,report_local_links=len(links),files=files)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    expected=expected_manifest()
    if args.verify:assert read(MANIFEST)==expected,'Manifest differs from current evidence'
    else:MANIFEST.write_text(json.dumps(expected,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,mode='verify' if args.verify else 'seal',files=len(expected['files']),
        bytes=sum(r['bytes'] for r in expected['files'].values()),proof_checks=expected['proof_hash_checks'],
        preserved_files=sum(r['files'] for r in expected['prior_deliveries_byte_preserved'].values()),
        report_local_links=expected['report_local_links'])))
