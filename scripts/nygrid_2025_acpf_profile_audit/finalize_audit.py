"""Bind the verification evidence without changing the audited AC model."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_acpf_profile_audit'
REPORT = ROOT / 'NYGRID_2025_ACPF_PROFILE_AUDIT.md'
MANIFEST = OUT / 'DELIVERY_MANIFEST.json'
BASELINE_HEAD = '330be1d90e6faab8d6c32c3d6c174aa364a30c73'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_record(path):
    return dict(sha256=sha(path), bytes=path.stat().st_size)


def verify_records(value, context):
    checked = 0
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            path = ROOT / value['path']
            if not path.is_file():
                path = context.parent / value['path']
            assert path.is_file(), f'Missing bound file: {value["path"]}'
            assert sha(path) == value['sha256'].lower(), f'Stale bound file in {context.name}: {path}'
            checked += 1
        for child in value.values():
            checked += verify_records(child, context)
    elif isinstance(value, list):
        for child in value:
            checked += verify_records(child, context)
    return checked


def expected_manifest():
    baseline_path = ROOT / 'output/nygrid_2025_ac_system/DELIVERY_MANIFEST.json'
    committed_manifest = subprocess.check_output(['git', 'show', BASELINE_HEAD + ':output/nygrid_2025_ac_system/DELIVERY_MANIFEST.json'], cwd=ROOT)
    assert hashlib.sha256(committed_manifest).hexdigest() == sha(baseline_path), 'Baseline manifest differs from audited commit'
    baseline = json.loads(baseline_path.read_text())
    for name, record in baseline['files'].items():
        assert file_record(ROOT / name) == record, f'Audited baseline was changed: {name}'
    assert sha(ROOT / 'NYGRID_2025_WESTERN_SOURCE_AUDIT.md') == 'e21175a942b85519688708eaba22b2100ad06281b256a5d1dd66b17371b3d4cb', 'Unrelated annotation changed'
    required = ['structure/structure_audit.json', 'structure/preservation_and_readability.json',
                'structure/scoring_representative_independent_review.json', 'structure/scoring_annual_independent_review.json',
                'alignment/profile_alignment_summary.json', 'alignment/interface_operator_contract.json',
                'alignment/finalizer_report_independent_review.json',
                'acpf/cache_parity_and_benchmark.json', 'acpf/representative_profile_PF_receipt.json',
                'acpf/annual_profile_PF_receipt.json', 'acpf/annual_hour_quality.csv',
                'acpf/Q_limit_sensitivity/Q_limit_sensitivity_receipt.json',
                'acpf/NR_recovery/NR_recovery_receipt.json', 'acpf/validation_source_receipt.json',
                'comparison/scoring_receipt.json', 'comparison/interface_metrics.csv']
    for relative in required:
        assert (OUT / relative).is_file(), f'Incomplete audit: {relative}'
    assert len(list((OUT / 'acpf/monthly').glob('profile_PF_2025_*.mat'))) == 12
    scoring = json.loads((OUT / 'comparison/scoring_receipt.json').read_text())
    assert scoring['passed'] and scoring['audit_complete'] and not scoring['OPF_used']
    assert scoring['source_qualified_hours'] == 8651 and scoring['evaluated_hours'] == 8760
    assert scoring['VQ_and_generator_qualified_comparison_hours'] == 0
    assert not scoring['physical_NYISO_meter_membership_and_terminal_convention_certified']
    annual = json.loads((OUT / 'acpf/annual_profile_PF_receipt.json').read_text())
    assert annual['completed'] and annual['attempted_hours'] == 8651 and annual['solver_exceptions'] == 0
    assert annual['AC_equation_qualified_hours'] == scoring['matched_comparison_hours']
    source_proof = json.loads((OUT / 'acpf/validation_source_receipt.json').read_text())
    assert source_proof['passed']
    report_review = json.loads((OUT / 'alignment/finalizer_report_independent_review.json').read_text())
    assert report_review['passed']
    independent = json.loads((OUT / 'structure/scoring_annual_independent_review.json').read_text())
    assert independent['passed'] and independent['matched_cohort_hours'] == scoring['matched_comparison_hours']
    qlimits = json.loads((OUT / 'acpf/Q_limit_sensitivity/Q_limit_sensitivity_receipt.json').read_text())
    assert qlimits['completed'] and len(qlimits['checks']) == 7 and not qlimits['OPF_used']
    recovery = json.loads((OUT / 'acpf/NR_recovery/NR_recovery_receipt.json').read_text())
    assert recovery['completed'] and recovery['primary_failed_hours'] == annual['attempted_hours'] - annual['PF_converged_hours']
    assert not recovery['primary_outputs_overwritten'] and not recovery['source_profiles_controls_or_parameters_changed']
    structure = json.loads((OUT / 'structure/structure_audit.json').read_text())
    assert structure['passed'] and structure['current_cable_equivalent_rows'] == 40
    assert structure['known_cable_corridor_conflicts_in_current_OH_rows'] == [300, 309, 310, 386]
    assert structure['bus_reconciliation']['AC_post_Dover'] == 267
    assert not structure['current_model_changed']
    alignment = json.loads((OUT / 'alignment/profile_alignment_summary.json').read_text())
    assert alignment['all_numeric_assertions_passed'] and alignment['no_frozen_input_or_model_mutations']
    assert alignment['NY_load']['maximum_public_scale_zone_reaggregation_error_MW'] < 1e-8
    paths = [REPORT]
    paths += [p for base in [ROOT / 'scripts/nygrid_2025_acpf_profile_audit', OUT]
              for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts
              and p.suffix != '.pyc' and p != MANIFEST]
    assert REPORT.is_file()
    proofs = 0
    for path in paths:
        if path.suffix == '.json':
            proofs += verify_records(json.loads(path.read_text(encoding='utf-8-sig')), path)
    links = []
    for target in re.findall(r'\]\(([^)]+)\)', REPORT.read_text(encoding='utf-8')):
        if target.startswith(('http://', 'https://', '#')):
            continue
        path = ROOT / unquote(target.strip('<>').split('#')[0])
        assert path.is_file() or path == MANIFEST, f'Broken report link: {target}'
        links.append(target)
    records = {p.relative_to(ROOT).as_posix(): file_record(p) for p in sorted(set(paths))}
    assert max(v['bytes'] for v in records.values()) < 100_000_000
    return dict(schema_version=1, status='verification_complete_current_DLR_baseline_conditions_not_satisfied',
                baseline_HEAD=BASELINE_HEAD, original_model_and_sealed_evidence_byte_preserved=True,
                baseline_files_checked=len(baseline['files']), baseline_manifest_sha256=sha(baseline_path),
                OPF_used_for_this_audit=False, model_parameters_or_profiles_fitted=False,
                all_year_physical_operating_qualification=False,
                matched_ACPF_interface_comparison_hours=scoring['matched_comparison_hours'],
                proof_file_hash_checks=proofs, report_local_links=len(links), files=records)


def main(verify):
    expected = expected_manifest()
    if verify:
        assert json.loads(MANIFEST.read_text()) == expected, 'Delivery manifest differs from current evidence'
    else:
        MANIFEST.write_text(json.dumps(expected, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, mode='verify' if verify else 'seal', files=len(expected['files']),
                          bytes=sum(v['bytes'] for v in expected['files'].values()),
                          proof_checks=expected['proof_file_hash_checks'],
                          baseline_files_unchanged=expected['baseline_files_checked'],
                          report_local_links=expected['report_local_links'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify', action='store_true')
    main(parser.parse_args().verify)
