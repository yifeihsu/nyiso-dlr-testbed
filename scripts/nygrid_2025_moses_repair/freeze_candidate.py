"""Bind a source-defined candidate before any interface-error scoring."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_moses_repair'


def record(p):
    with p.open('rb') as stream:
        h = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=p.relative_to(ROOT).as_posix(), sha256=h, bytes=p.stat().st_size)


def main():
    generation = OUT / 'generation/candidate_receipt.json'
    boundary = OUT / 'boundary/boundary_rerouting_receipt.json'
    assert json.loads(generation.read_text())['passed']
    assert json.loads(boundary.read_text())['passed']
    paths = [generation, boundary, OUT/'generation/generation_candidate.mat',
             OUT/'boundary/boundary_rerouting.mat', OUT/'boundary/PV20_source_receipt.json']
    paths += sorted((ROOT/'scripts/nygrid_2025_moses_repair/delivery/runtime').rglob('*.m'))
    paths += [ROOT/'scripts/nygrid_2025_moses_repair/delivery/export_model.m',
              ROOT/'scripts/nygrid_2025_moses_repair/prepare_boundary_rerouting.py']
    result = dict(passed=True, schema_version=1, created_utc=datetime.now(timezone.utc).isoformat(),
                  candidate_id='StLawrence_monthly_energy_PV20_boundary_proxy_v1',
                  baseline_guard=record(OUT/'baseline_guard.json'),
                  original_generator_rows_preserved=1464,
                  appended_StLawrence_unit21_row=1465, appended_PV20_boundary_row=1466,
                  original_six_transfer_records_preserved=True,
                  physical_branch_and_shunt_arrays_unchanged=True,
                  raw_P63_is_not_asserted_equal_to_reconciled_hourly_hydro=True,
                  fixed_regional_import_totals_preserved=True,
                  physical_PV20_meter_equivalence_certified=False,
                  actual_hourly_StLawrence_generation_claimed=False,
                  internal_interface_observations_used_to_choose_candidate=False,
                  candidate_annual_interface_scores_available_at_freeze=False,
                  files=[record(p) for p in paths])
    target = OUT/'candidate_receipt.json'
    if target.exists():
        assert json.loads(target.read_text())['files'] == result['files'], 'Candidate changed; explicitly version it.'
    else:
        target.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, candidate_id=result['candidate_id'], bound_files=len(paths))))


if __name__ == '__main__':
    main()
