"""Seal or verify the P34 audit and DLR readiness assessment without rerunning models."""
from pathlib import Path
import argparse
import importlib.util
import json
import re
import sys
from urllib.parse import unquote
from qualification import ROOT, OUT, CONTRACT, sha, require, load_contract, inspect_use

REPORT = ROOT / 'NYGRID_2025_P34_QUALIFICATION_AND_DLR_READINESS.md'
SCRIPTS = ROOT / 'scripts/nygrid_2025_p34_qualification'
DLR = ROOT / 'output/nygrid_2025_dlr_readiness'
DLR_SCRIPTS = ROOT / 'scripts/nygrid_2025_dlr_readiness'
MANIFEST = OUT / 'DELIVERY_MANIFEST.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def packaged_files():
    return sorted([REPORT] + [p for base in (SCRIPTS, OUT, DLR_SCRIPTS, DLR)
        for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts
        and p.suffix != '.pyc' and p != MANIFEST])


def main(verify=False):
    helper = ROOT / 'scripts/nygrid_2025_line_parameters/finalize_line_parameters.py'
    sys.path.insert(0, str(helper.parent))
    spec = importlib.util.spec_from_file_location('preserved_proof_verifier', helper)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    proofs = [OUT / 'sources/primary_evidence_conclusion.json',
              OUT / 'numeric_audit/numeric_audit_receipt.json',
              OUT / 'numeric_audit/publication_drift_check.json',
              OUT / 'qualification_validation.json',
              OUT / 'validation/independent_qualification_review.json',
              DLR / 'readiness_assessment.json',
              DLR / 'fresh_reusable_component_audit.json']
    checked = 0
    for path in proofs:
        proof = read(path)
        if path.parent == DLR:
            require(proof.get('assessment_completed', proof.get('audit_completed')) is True,
                    'Incomplete readiness audit: ' + str(path))
        else:
            require(proof.get('passed') is True, 'Unpassed proof: ' + str(path))
        checked += module.verify_proof(proof, path.parent)
    c = load_contract()
    require(inspect_use(c, 'conditional_dc')['allowed'], 'Conditional DC inspection failed')
    require(inspect_use(c, 'historically_verified_sign', [25118, 25119])['allowed'], 'Ontario sign qualification failed')
    require(not inspect_use(c, 'historically_verified_sign', [625149, 625150])['allowed'], 'Dover historical date promoted')
    for use in ('verified_native_MW', 'measured_physical_telemetry', 'physical_thermal_validation'):
        require(not inspect_use(c, use)['allowed'], 'Unestablished physical claim allowed: ' + use)
    require(c['no_new_numeric_case_or_replay'] and not c['native_numeric_MW_unit_verified'], 'Numerical scope changed')
    checked += module.verify_proof(c, OUT)
    tests = read(OUT / 'qualification_validation.json')
    require(tests['tests'] == 7 and tests['contract_sha256'] == sha(CONTRACT), 'Stale contract tests')
    numeric = read(OUT / 'numeric_audit/numeric_audit_receipt.json')
    require(numeric['script_sha256'] == sha(SCRIPTS / 'numeric_audit/run_numeric_audit.py')
            and not numeric['confirmed_numeric_bug_requiring_case_change']
            and numeric['numeric_unit_multiplier_selected'] is None
            and not numeric['internal_P32_value_columns_read'], 'Numeric audit scope or code changed')
    drift = read(OUT / 'numeric_audit/publication_drift_check.json')
    require(drift['script_sha256'] == sha(SCRIPTS / 'numeric_audit/compare_dec19_publication.py')
            and drift['output_sha256'] == sha(OUT / 'numeric_audit/December19_publication_comparison.csv')
            and all(r['timestamp_axis_exact'] and r['posted_values_exact'] for r in drift['comparisons']),
            'Publication drift proof changed')
    ready = read(DLR / 'readiness_assessment.json')
    require(not ready['physical_DLR_readiness_passed'] and not ready['current_DLR_coupled_replay_run'],
            'DLR claim scope changed')
    require(ready['current_model']['retained_buses'] == 148
            and ready['current_model']['fixed_transfer_records'] == 6
            and ready['current_model']['annual_common_hours'] == 8651, 'Wrong electrical baseline')
    kernel = read(DLR / 'fresh_reusable_component_audit.json')
    require(kernel['fresh_reusable_component_tests_passed'] and kernel['component_tests'] == 25,
            'Reusable component tests incomplete')
    # The earlier numerical delivery must remain byte-identical. This is a file
    # verification, not an unnecessary annual replay or repeated power-flow run.
    old_manifest = ROOT / 'output/nygrid_2025_dover_parameters/DELIVERY_MANIFEST.json'
    old = read(old_manifest)
    for rel, entry in old['files'].items():
        require(sha(ROOT / rel) == entry['sha256'], 'Earlier Dover artifact changed: ' + rel)
        checked += 1
    links = re.findall(r'\[[^\]]+\]\(([^)]+)\)', REPORT.read_text(encoding='utf-8'))
    local = [v for v in links if not v.startswith(('http://', 'https://', '#'))]
    for link in local:
        p = ROOT / unquote(link.split('#')[0])
        if p == MANIFEST and not verify:
            continue
        require(p.is_file(), 'Missing report target: ' + link)
    files = {p.relative_to(ROOT).as_posix(): dict(sha256=sha(p), bytes=p.stat().st_size)
             for p in packaged_files()}
    if verify:
        require(read(MANIFEST)['files'] == files, 'New delivery changed after sealing')
    else:
        MANIFEST.write_text(json.dumps(dict(
            status='public_P34_audit_complete_with_unresolved_native_semantics;DLR_readiness_assessed',
            native_MW_unit_verified=False, Dover_historical_sign_effective_date_verified=False,
            Ontario_historical_sign_effective_date_verified=True,
            current_coupled_physical_DLR_ready=False, conditional_DC_research_platform_ready=True,
            no_numeric_model_or_replay_change=True, no_internal_interface_fit=True,
            source_and_preservation_hash_checks=checked, report_local_links=len(local),
            preserved_Dover_manifest=dict(path=old_manifest.relative_to(ROOT).as_posix(), sha256=sha(old_manifest)),
            files=files), indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, verify=verify, files=len(files),
        bytes=sum(v['bytes'] for v in files.values()), proof_hash_checks=checked,
        report_local_links=len(local), new_numerical_replay=False), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--verify', action='store_true')
    main(parser.parse_args().verify)
