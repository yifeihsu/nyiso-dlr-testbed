"""Verify documentary deliverables, source proofs and unchanged model inputs."""
from pathlib import Path
import argparse
import json
import re
from urllib.parse import unquote
from build_registry import ROOT, OUT, DEFS, sha, dump
from inspect_definition import load_registry, select_definition

SCRIPTS = ROOT/'scripts/nygrid_2025_flowgate_definitions'
REPORT = ROOT/'NYGRID_2025_PHYSICAL_FLOWGATE_DEFINITIONS.md'
MANIFEST = OUT/'DELIVERY_MANIFEST.json'
RECEIPTS = [
    'definitions/registry_receipt.json',
    'definitions/western_2025.receipt.json',
    'definitions/western_winter2024_25.receipt.json',
    'definitions/western_winter2025_26.receipt.json',
    'definitions/downstate_2025.receipt.json',
    'definitions/central_north_source_receipt.json',
    'local_model/source_crosswalk_receipt.json',
    'local_model/candidates/model_term_candidate_receipt.json',
    'validation/model_lineage_independent_review.json',
    'validation/registry_independent_review.json',
    'validation/registry_guard_tests.json']


def verify_proof(obj, directory):
    count = 0
    if isinstance(obj, list):
        return sum(verify_proof(x, directory) for x in obj)
    if not isinstance(obj, dict):
        return 0
    if 'path' in obj and 'sha256' in obj:
        path = ROOT/obj['path']
        if not path.is_file() or sha(path) != obj['sha256']:
            raise ValueError('Stale proof: '+str(path))
        count += 1
    for key, value in obj.items():
        if key in ('dependencies', 'reviewed_hashes', 'outputs') and isinstance(value, dict):
            for path, digest in value.items():
                if isinstance(digest, str) and re.fullmatch('[a-f0-9]{64}', digest):
                    target = ROOT/path if (ROOT/path).is_file() else directory/path
                    if not target.is_file() or sha(target) != digest:
                        raise ValueError('Stale proof: '+str(target))
                    count += 1
        count += verify_proof(value, directory)
    return count


def files():
    return sorted([REPORT]+[p for base in (SCRIPTS,OUT) for p in base.rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p!=MANIFEST])


def main(verify=False):
    registry = load_registry()
    for definition in registry['definitions']:
        select_definition(registry, definition['gate_id'], definition['edition'])
        try:
            select_definition(registry, definition['gate_id'], definition['edition'], True)
        except ValueError as exc:
            if not str(exc).startswith('No certified physical model operator'):
                raise
        else:
            raise ValueError('An unverified model operator was exposed')
    proof_count = 0
    for relative in RECEIPTS:
        path = OUT/relative
        obj = json.loads(path.read_text(encoding='utf-8'))
        if obj.get('passed') is not True:
            raise ValueError('Review/check has not passed: '+relative)
        proof_count += verify_proof(obj, path.parent)
    links = re.findall(r'\[[^\]]+\]\(([^)]+)\)',REPORT.read_text(encoding='utf-8'))
    local_links = [s for s in links if not s.startswith(('https://','http://','#'))]
    for target in local_links:
        linked = REPORT.parent/unquote(target.split('#')[0])
        if linked == MANIFEST and not verify:
            continue  # This command creates the manifest after all checks.
        if not linked.is_file():
            raise ValueError('Missing report link: '+target)
    records = {p.relative_to(ROOT).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in files()}
    if verify:
        old = json.loads(MANIFEST.read_text(encoding='utf-8'))
        if records != old['files']:
            raise ValueError('Delivery files changed after finalization')
    else:
        dump(MANIFEST, dict(status='verified_source_definitions_model_calibration_unresolved',
             model_operators_promoted=0, interface_observations_used=False,
             scientific_status='documentary_membership_usable; contemporary_model_identity_P32_binding_and_effective_hours_unestablished',
             source_counts=registry['count'], proof_hash_checks=proof_count,
             report_local_links_checked=len(local_links), files=records))
    print(json.dumps(dict(passed=True, verify=verify, files=len(records),
        total_bytes=sum(r['bytes'] for r in records.values()), proof_hash_checks=proof_count,
        report_local_links=len(local_links), model_operators_promoted=0),indent=2))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true')
    main(parser.parse_args().verify)
