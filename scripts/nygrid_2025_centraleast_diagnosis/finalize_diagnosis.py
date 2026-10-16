"""Seal diagnostic evidence while preserving every previous model delivery."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_centraleast_diagnosis'
REPORT = ROOT / 'NYGRID_2025_CENTRAL_EAST_DIAGNOSIS.md'
MANIFEST = OUT / 'DELIVERY_MANIFEST.json'
BASELINE = '6dcc77f071a9ce4aaaa2fcba9a9aabc15f7d5dbc'


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def record(path):
    return dict(sha256=sha(path), bytes=path.stat().st_size)


def verify_records(value, context):
    count = 0
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            p = ROOT / value['path']
            if not p.is_file(): p = context.parent / value['path']
            # The retained failed-trial receipt is rooted one directory above
            # itself and includes its own archive directory as the first part.
            reference = Path(value['path'])
            if not p.is_file() and reference.parts[0] == context.parent.name:
                p = context.parent.parent / reference
            assert p.is_file(), f'Missing bound source in {context.name}: {value["path"]}'
            assert sha(p) == value['sha256'].lower(), f'Stale bound source in {context.name}: {p}'
            count += 1
        for child in value.values(): count += verify_records(child, context)
    elif isinstance(value, list):
        for child in value: count += verify_records(child, context)
    return count


def expected_manifest():
    preserved = {}
    for namespace in ['nygrid_2025_ac_system', 'nygrid_2025_acpf_profile_audit', 'nygrid_2025_compact_ac']:
        relative = f'output/{namespace}/DELIVERY_MANIFEST.json'; p = ROOT / relative
        committed = subprocess.check_output(['git','show',BASELINE+':'+relative], cwd=ROOT)
        assert hashlib.sha256(committed).hexdigest() == sha(p), f'Prior manifest changed: {relative}'
        old = json.loads(p.read_text())
        for name, r in old['files'].items(): assert record(ROOT/name) == r, f'Prior delivery changed: {name}'
        preserved[namespace] = dict(files=len(old['files']), manifest_sha256=sha(p))
    assert sha(ROOT/'NYGRID_2025_WESTERN_SOURCE_AUDIT.md') == 'e21175a942b85519688708eaba22b2100ad06281b256a5d1dd66b17371b3d4cb'
    required = ['summary/diagnosis_summary.json', 'summary/stage_metrics.csv', 'summary/centraleast_diagnosis.png',
                'measurement/measurement_receipt.json', 'measurement/raw_source_check.json', 'measurement/final_review.json',
                'measurement/annual_bridges/annual_bridge_scoring_receipt.json',
                'experiments/experiment_source_receipt.json', 'experiments/representative_bridge/bridge_receipt.json',
                'experiments/annual_DC_bridge/annual_DC_bridge_receipt.json',
                'experiments/annual_loss_loaded_DCF/annual_loss_loaded_receipt.json',
                'model_delta/independent_review_closure.json', 'model_delta/annual_DC_independent_review.json',
                'model_delta/annual_loss_independent_review.json', 'model_delta/fallback_provenance_review.json']
    for name in required: assert (OUT/name).is_file(), f'Incomplete diagnosis: {name}'
    read = lambda name: json.loads((OUT/name).read_text(encoding='utf-8-sig'))
    for name in ['summary/diagnosis_summary.json','measurement/measurement_receipt.json',
                 'measurement/annual_bridges/annual_bridge_scoring_receipt.json',
                 'measurement/raw_source_check.json','measurement/final_review.json',
                 'experiments/experiment_source_receipt.json','model_delta/independent_review_closure.json']:
        assert read(name)['passed'], f'Review failed: {name}'
    summary = read('summary/diagnosis_summary.json')
    assert summary['hours'] == 8494 and summary['source_qualified_hours'] == 8651
    assert abs(summary['total_mean_delta_public_MW'] - summary['construction_mean_delta_public_MW']
               - summary['loss_loaded_mean_delta_public_MW'] - summary['remaining_mean_delta_public_MW']) < 1e-7
    assert summary['loss_loaded_DC_uses_solved_AC_losses'] and summary['loss_reconstruction_not_independent_forecast']
    assert summary['no_physical_meter_or_impedance_truth_established'] and summary['no_production_model_changes']
    bridge = read('experiments/annual_DC_bridge/annual_DC_bridge_receipt.json')
    loss = read('experiments/annual_loss_loaded_DCF/annual_loss_loaded_receipt.json')
    assert bridge['completed'] and bridge['passed'] and bridge['solves'] == 33976
    assert loss['completed'] and loss['passed'] and loss['solves'] == 25482
    paths = [REPORT]
    paths += [p for base in [ROOT/'scripts/nygrid_2025_centraleast_diagnosis', OUT] for p in base.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc' and p != MANIFEST]
    checks = 0
    for p in paths:
        assert p.is_file()
        if p.suffix == '.json': checks += verify_records(json.loads(p.read_text(encoding='utf-8-sig')), p)
    links = []
    for value in re.findall(r'\]\(([^)]+)\)', REPORT.read_text(encoding='utf-8')):
        if value.startswith(('http://','https://','#')): continue
        p = ROOT/unquote(value.strip('<>').split('#')[0])
        assert p.is_file() or p == MANIFEST, f'Broken report link: {value}'
        links.append(value)
    files = {p.relative_to(ROOT).as_posix():record(p) for p in sorted(set(paths))}
    assert max(r['bytes'] for r in files.values()) < 100_000_000
    return dict(schema_version=1, status='CENTRAL_EAST_model_regression_diagnosed_with_controlled_experiments',
                baseline_HEAD=BASELINE, prior_deliveries_byte_preserved=preserved,
                production_model_or_profiles_modified=False, OPF_or_observation_fitting_used=False,
                matched_hours=8494, posthoc_loss_allocation_not_unique_causal_attribution=True,
                proof_hash_checks=checks, report_local_links=len(links), files=files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--verify', action='store_true'); args=parser.parse_args()
    expected=expected_manifest()
    if args.verify: assert json.loads(MANIFEST.read_text()) == expected, 'Manifest differs from current evidence'
    else: MANIFEST.write_text(json.dumps(expected,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,mode='verify' if args.verify else 'seal',files=len(expected['files']),
                         bytes=sum(r['bytes'] for r in expected['files'].values()),proof_checks=expected['proof_hash_checks'],
                         preserved_files=sum(r['files'] for r in expected['prior_deliveries_byte_preserved'].values()),
                         report_local_links=expected['report_local_links'])))
