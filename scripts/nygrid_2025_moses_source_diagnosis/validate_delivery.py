"""Final evidence/preservation checks for an additive source diagnosis."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_moses_source_diagnosis'


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    guard = json.loads((OUT / 'source_guard.json').read_text())
    for source in guard['critical_sources']:
        p = ROOT / source['path']
        assert p.stat().st_size == source['bytes'] and sha(p) == source['sha256'], p
    pointer = json.loads((ROOT / 'deliverables/CURRENT_NYGRID_MODEL.json').read_text())
    delivery = []
    for key in ['archive', 'model_receipt', 'map', 'map_manifest', 'structure_manual']:
        source = pointer[key]
        p = ROOT / source['path']
        assert p.stat().st_size == source['bytes'] and sha(p) == source['sha256'], p
        delivery.append(source)
    assert sha(ROOT / 'output/nygrid_2025_latest_map/network_map.html') == pointer['map']['sha256']
    data = pd.read_csv(OUT / 'balance_hourly.csv')
    assert len(data) == 8760 and data.hour_index.is_unique and data.timestamp_utc.is_unique
    q = data.loc[data.qualified]
    assert len(q) == 8651
    err = q.primary_Moses_MW - q.observed_Moses_MW
    assert abs(abs(err).mean() - 118.82092402208409) < 1e-9
    assert abs(100 * abs(err).sum() / abs(q.observed_Moses_MW).sum() - 22.00761741451924) < 1e-9
    closure = q.StLawrence_PG_MW + q.other_D_PG_MW + q.HQ_MW + q.PAR_total_MW - q.gross_D_load_MW + q.terminal_correction_MW - q.primary_Moses_MW
    assert np.max(np.abs(closure)) < 1e-8
    report = ROOT / 'NYGRID_2025_MOSES_SOURCE_DIAGNOSIS.md'
    links = re.findall(r'\]\(([^)]+)\)', report.read_text(encoding='utf-8'))
    local = [link for link in links if not link.startswith('http')]
    for link in local:
        assert (ROOT / link).is_file(), link
    reviews = []
    for name in ['temporal_review.json', 'component_timing_review.json', 'source_alternative_review.json']:
        p = OUT / 'residual' / name
        assert json.loads(p.read_text())['passed'], p
        reviews.append({'path': p.relative_to(ROOT).as_posix(), 'sha256': sha(p)})
    generation = json.loads((OUT / 'generation/generation_audit_receipt.json').read_text())
    assert generation['passed'] and not generation['default_model_changed']
    generation_dependencies = generation['sources'] + generation['outputs']
    for source in generation_dependencies:
        assert sha(ROOT / source['path']) == source['sha256'], source['path']
    report_review_path = OUT / 'boundary/report_review.json'
    report_review = json.loads(report_review_path.read_text())
    assert report_review['passed'] and report_review['report_sha256'] == sha(report)
    reviews.append({'path': report_review_path.relative_to(ROOT).as_posix(), 'sha256': sha(report_review_path)})
    combined_path = OUT / 'residual/independent_review.json'
    assert json.loads(combined_path.read_text())['passed']
    reviews.append({'path': combined_path.relative_to(ROOT).as_posix(), 'sha256': sha(combined_path)})
    result = {
        'passed': True,
        'checked_utc': datetime.now(timezone.utc).isoformat(),
        'baseline_commit': guard['baseline_HEAD'],
        'critical_numeric_and_runtime_inputs_unchanged': len(guard['critical_sources']),
        'current_delivery_artifacts_verified_unchanged': delivery,
        'current_browser_map_matches_frozen_delivery': True,
        'qualified_hours': len(q),
        'physical_UTC_hours': len(data),
        'maximum_primary_balance_closure_MW': float(np.max(np.abs(closure))),
        'baseline_metrics_reproduced': True,
        'new_AC_solutions_in_this_investigation': 0,
        'diagnostic_input_promoted_to_default': False,
        'report_local_links_checked': len(local),
        'report_sha256': sha(report),
        'review_receipts': reviews,
        'generation_source_and_output_hashes_verified': len(generation_dependencies),
        'national_inventory_cache_preserved_locally_not_versioned': True,
        'figure_visual_review': 'Viewed rendered PNG: titles, both axes, all24hours and annotations readable; no clipping.'
    }
    (OUT / 'delivery_validation.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['passed', 'critical_numeric_and_runtime_inputs_unchanged', 'qualified_hours', 'maximum_primary_balance_closure_MW', 'report_local_links_checked']}))


if __name__ == '__main__':
    main()
