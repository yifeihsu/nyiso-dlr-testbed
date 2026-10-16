"""Verify compact-model delivery and byte preservation of the detailed baseline."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_compact_ac'
REPORT = ROOT / 'NYGRID_2025_COMPACT_AC.md'
MANIFEST = OUT / 'DELIVERY_MANIFEST.json'
BASELINE_HEAD = '3d2d3104879815180b82804861788dd132aed729'
PUBLIC = [ROOT / 'System Matpower Format' / name for name in
          ['npcc_nygrid_2025_compact_ac.m', 'run_nygrid_2025_compact_acpf.m']]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def record(path):
    return dict(sha256=sha(path), bytes=path.stat().st_size)


def verify_bound_records(value, context):
    checks = 0
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            path = ROOT / value['path']
            if not path.is_file():
                path = context.parent / value['path']
            assert path.is_file(), f'Missing dependency in {context.name}: {value["path"]}'
            assert sha(path) == value['sha256'].lower(), f'Stale dependency in {context.name}: {path}'
            checks += 1
        for child in value.values():
            checks += verify_bound_records(child, context)
    elif isinstance(value, list):
        for child in value:
            checks += verify_bound_records(child, context)
    return checks


def expected_manifest():
    preserved = {}
    for namespace in ['nygrid_2025_ac_system', 'nygrid_2025_acpf_profile_audit']:
        relative = f'output/{namespace}/DELIVERY_MANIFEST.json'
        path = ROOT / relative
        committed = subprocess.check_output(['git', 'show', BASELINE_HEAD + ':' + relative], cwd=ROOT)
        assert hashlib.sha256(committed).hexdigest() == sha(path), f'Baseline manifest changed: {relative}'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        for name, expected in manifest['files'].items():
            assert record(ROOT / name) == expected, f'Detailed baseline/evidence changed: {name}'
        preserved[namespace] = dict(files=len(manifest['files']), manifest_sha256=sha(path))
    assert sha(ROOT / 'NYGRID_2025_WESTERN_SOURCE_AUDIT.md') == 'e21175a942b85519688708eaba22b2100ad06281b256a5d1dd66b17371b3d4cb'
    required = ['MODEL_CONTRACT.json', 'models/model_exports.json',
                'validation/independent_reference_recovery.json',
                'validation/representative_pairs/representative_pair_receipt.json',
                'validation/annual_compact_PF_receipt.json',
                'validation/source_receipt.json',
                'validation/Q_limit_pairs/Q_limit_pair_receipt.json',
                'alignment/comparison_contract.json', 'alignment/scoring_receipt.json',
                'independent/kron_feasibility_review.json', 'independent/compact_core_review.json',
                'independent/annual_arrays_independent_review.json',
                'independent/alignment_scoring_independent_review.json',
                'alignment/final_delivery_review.json']
    for name in required:
        assert (OUT / name).is_file(), f'Incomplete compact delivery: {name}'
    get = lambda name: json.loads((OUT / name).read_text(encoding='utf-8-sig'))
    model = get('models/model_exports.json')
    assert model['passed'] and not model['OPF_used'] and len(model['models']) == 5
    for item in model['models']:
        assert item['retained_bus_count'] == 148 and item['promoted_necessary_bus_count'] == 0
        assert item['validation']['passed'] and item['eliminated_bus_count'] in [118, 119]
        assert (OUT / 'models' / item['filename']).is_file()
    representative = get('validation/representative_pairs/representative_pair_receipt.json')
    assert representative['completed'] and representative['passed'] and len(representative['checks']) == 8
    annual = get('validation/annual_compact_PF_receipt.json')
    assert annual['completed'] and annual['passed'] and not annual['OPF_used']
    assert len(list((OUT / 'validation/monthly').glob('*.mat'))) == 12
    scoring = get('alignment/scoring_receipt.json')
    assert scoring['passed'] and scoring['comparison_complete'] and scoring['source_qualified_hours'] == 8651
    assert scoring['paired_qualified_hours'] == 8494 and scoring['frozen_detailed_success_lost_hours'] == 0
    assert not scoring['current_gamma_division_applied'] and not scoring['reduced_edge_interface_flows_used']
    assert not scoring['public_observations_profiles_operators_and_previous_detailed_results_changed']
    assert not scoring['physical_P32_meter_membership_certified']
    for name in ['independent/compact_core_review.json', 'independent/annual_arrays_independent_review.json',
                 'independent/alignment_scoring_independent_review.json',
                 'alignment/final_delivery_review.json']:
        assert get(name)['passed'], f'Independent review failed: {name}'
    assert get('validation/source_receipt.json')['passed']
    qlimit = get('validation/Q_limit_pairs/Q_limit_pair_receipt.json')
    assert qlimit['completed'] and qlimit['outcomes_consistent'] and len(qlimit['checks']) == 7
    contract = get('MODEL_CONTRACT.json')
    assert contract['retained_bus_count'] == 148 and not contract['AC_OPF_used']
    paths = [REPORT] + PUBLIC
    paths += [p for base in [ROOT / 'scripts/nygrid_2025_compact_ac', OUT]
              for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts
              and p.suffix != '.pyc' and p != MANIFEST]
    checks = 0
    for path in paths:
        assert path.is_file(), f'Missing delivery file: {path}'
        if path.suffix == '.json':
            checks += verify_bound_records(json.loads(path.read_text(encoding='utf-8-sig')), path)
    links = []
    for target in re.findall(r'\]\(([^)]+)\)', REPORT.read_text(encoding='utf-8')):
        if target.startswith(('http://', 'https://', '#')):
            continue
        path = ROOT / unquote(target.strip('<>').split('#')[0])
        assert path.is_file() or path == MANIFEST, f'Broken report link: {target}'
        links.append(target)
    files = {p.relative_to(ROOT).as_posix(): record(p) for p in sorted(set(paths))}
    assert max(r['bytes'] for r in files.values()) < 100_000_000
    return dict(schema_version=1, status='compact_148_bus_AC_reduction_validated', baseline_HEAD=BASELINE_HEAD,
                detailed_model_and_prior_audit_byte_preserved=True, preserved_baselines=preserved,
                AC_OPF_used=False, public_alignment_or_physical_assumptions_claimed_repaired=False,
                paired_detailed_success_hours=scoring['paired_qualified_hours'],
                compact_equation_and_profile_qualified_hours=scoring['compact_equation_and_profile_qualified_hours'],
                proof_file_hash_checks=checks, report_local_links=len(links), files=files)


def main(verify):
    expected = expected_manifest()
    if verify:
        assert json.loads(MANIFEST.read_text()) == expected, 'Delivery manifest differs from current evidence'
    else:
        MANIFEST.write_text(json.dumps(expected, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, mode='verify' if verify else 'seal', files=len(expected['files']),
                         bytes=sum(v['bytes'] for v in expected['files'].values()),
                         proof_checks=expected['proof_file_hash_checks'],
                         preserved_baseline_files=sum(v['files'] for v in expected['preserved_baselines'].values()),
                         report_local_links=expected['report_local_links'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify', action='store_true')
    main(parser.parse_args().verify)
