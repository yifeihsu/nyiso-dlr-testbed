"""Preserve the repaired baseline and optionally bind an immutable candidate.

No PF runs here. Baseline files are never rewritten. Candidate preparation is
explicit and requires the compiled model/runtime and a passing frozen receipt.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import shutil
import subprocess
import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_moses_repair/annual'
BASELINE_MODEL = ROOT / 'output/nygrid_2025_physical_repair/model'
BASELINE_RUNTIME = ROOT / 'scripts/nygrid_2025_physical_repair/delivery/runtime'
BASELINE_RUN = ROOT / 'output/nygrid_2025_physical_repair/annual/physical_repair_v1'
MODEL_FILES = ['latest_model.mat', 'profiles_h0001_4380.mat', 'profiles_h4381_8760.mat', 'model_receipt.json']


def record(path):
    path = Path(path)
    with path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    try: name = path.relative_to(ROOT).as_posix()
    except ValueError: name = str(path)
    return {'path': name, 'sha256': digest, 'bytes': path.stat().st_size}


def authenticated_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    source_record = record(source)
    if target.exists():
        assert record(target)['sha256'] == source_record['sha256'], f'Refusing to replace different snapshot: {target}'
    else: shutil.copy2(source, target)
    assert record(target)['sha256'] == source_record['sha256']
    return {'source': source_record, 'snapshot': record(target)}


def snapshot(model_dir, runtime_dir, target):
    proof = json.loads((model_dir / 'model_receipt.json').read_text()); assert proof['passed']
    for item in proof['model_files']:
        assert record(model_dir / item['name'])['sha256'] == item['sha256']
    files = [authenticated_copy(model_dir / name, target / 'model' / name) for name in MODEL_FILES]
    code = sorted(runtime_dir.rglob('*.m')); assert len(code) >= 20
    files += [authenticated_copy(p, target / 'runtime' / p.relative_to(runtime_dir)) for p in code]
    result = {'passed': True, 'purpose': 'Immutable executable snapshot; no PF or source mutation.', 'files': files}
    receipt = target / 'snapshot_receipt.json'
    if receipt.exists(): assert json.loads(receipt.read_text()) == result
    else: receipt.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return receipt


def main(candidate_model_dir=None, candidate_runtime_dir=None, candidate_receipt=None):
    OUT.mkdir(parents=True, exist_ok=True)
    array_path = BASELINE_RUN / 'comparison/comparison_arrays.npz'; a = np.load(array_path)
    baseline = loadmat(BASELINE_MODEL / 'latest_model.mat', simplify_cells=True)['model']
    clock = pd.DatetimeIndex(pd.to_datetime(a['timestamp_utc'], utc=True))
    assert len(clock) == 8760 and np.array_equal(np.diff(clock.asi8), np.full(8759, 3600 * 10 ** 9))
    assert np.array_equal(a['hour_index'], np.arange(1, 8761))
    assert np.array_equal(a['source_qualified'], baseline['axis']['source_qualified'].astype(bool))
    assert a['source_qualified'].sum() == a['candidate_qualified'].sum() == 8651
    assert float(a['gamma']) == float(baseline['scale_factor_gamma'])
    baseline_receipt = snapshot(BASELINE_MODEL, BASELINE_RUNTIME, OUT / 'baseline_bundle')
    axes_path = OUT / 'frozen_baseline_axes.mat'
    axes = {'hour_index': a['hour_index'], 'timestamp_utc': a['timestamp_utc'], 'source_qualified': a['source_qualified'],
        'current_baseline_qualified': a['candidate_qualified'], 'gamma': a['gamma'], 'interface_names': a['interface_names']}
    if axes_path.exists():
        existing = loadmat(axes_path, simplify_cells=True)
        for name, value in axes.items():
            left = np.char.rstrip(existing[name]) if name == 'interface_names' else existing[name]
            assert np.array_equal(left, value)
    else: savemat(axes_path, axes, do_compression=True)
    dependencies = [array_path, BASELINE_RUN / 'annual_receipt.json',
        BASELINE_RUN / 'validation/annual_input_accounting_review.json',
        ROOT / 'output/nygrid_2025_physical_repair/independent/annual_physics_review.json',
        ROOT / 'output/nygrid_2025_acpf_profile_audit/alignment/interface_operator_terms.csv']
    contract = {'schema_version': 1, 'source_HEAD': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
        'all_hour_slots': 8760, 'source_qualified_hours': 8651, 'baseline_qualified_hours': 8651,
        'baseline_run': BASELINE_RUN.relative_to(ROOT).as_posix(), 'baseline_arrays': array_path.relative_to(ROOT).as_posix(),
        'baseline_prediction_prefix': 'candidate_', 'gamma': float(a['gamma']),
        'baseline_generator_rows': len(baseline['generator_bus_ids']), 'baseline_fixed_transfer_rows': len(baseline['templates'][0]['dcline']),
        'baseline_snapshot': record(baseline_receipt), 'source_files': [record(p) for p in dependencies],
        'candidate_bound': False, 'candidate_loaded_directly_without_reapplying_physical_repair': True,
        'preserve_previous_repairs': 'Parent41 R/X/B and thermal realization; parent185/195 R/X/B and full-axis fixed-reactor placement.',
        'generator_and_transfer_axes': 'Candidate counts are read dynamically; existing row identities are preserved and any append is explicit.',
        'qualification': 'Fixed source mask AND PF convergence AND AC equation gate AND loss allocation gate AND recovery gate.',
        'operating_qualification': 'Separate V/Q/S, equipment, fixed-transfer and current checks; never inferred from equation closure.',
        'cohorts': ['candidate_all_success', 'paired_current_baseline', 'candidate_new_success', 'current_success_lost', 'current_baseline_all8651'],
        'failure_policy': 'Retain all attempted failures and all8760 slots. Failed iterates are never scored as valid predictions.',
        'current_units': 'Actual model amperes on appropriate bus kV; no gamma division.',
        'physical_P32_membership_certified': False, 'PF_started': False}
    any_candidate = any(p is not None for p in [candidate_model_dir, candidate_runtime_dir, candidate_receipt])
    if any_candidate:
        assert all(p is not None for p in [candidate_model_dir, candidate_runtime_dir, candidate_receipt]), 'Supply all three compiled candidate paths.'
        candidate_model_dir = candidate_model_dir.resolve(); candidate_runtime_dir = candidate_runtime_dir.resolve(); candidate_receipt = candidate_receipt.resolve()
        cp = json.loads(candidate_receipt.read_text()); assert cp.get('passed') is True
        candidate = loadmat(candidate_model_dir / 'latest_model.mat', simplify_cells=True)['model']
        assert np.array_equal(candidate['axis']['hour_index'], baseline['axis']['hour_index'])
        assert np.array_equal(candidate['axis']['state_index'], baseline['axis']['state_index'])
        assert np.array_equal(candidate['axis']['source_qualified'], baseline['axis']['source_qualified'])
        assert candidate['scale_factor_gamma'] == baseline['scale_factor_gamma']
        assert np.array_equal(candidate['retained_bus_ids'], baseline['retained_bus_ids'])
        for new, old in zip(candidate['templates'], baseline['templates']):
            assert np.array_equal(new['bus'][:, 0], old['bus'][:, 0]), 'Additional buses need an explicitly revised annual contract.'
            assert np.array_equal(new['branch'], old['branch']), 'AC branch/phase template changed outside this generation/control repair.'
            assert np.array_equal(new['bus'][:, [0, 4, 5, 6, 7, 8, 9, 10, 11, 12]], old['bus'][:, [0, 4, 5, 6, 7, 8, 9, 10, 11, 12]])
            assert np.array_equal(new['gen'][:len(old['gen']), 0], old['gen'][:, 0])
            assert np.array_equal(new['dcline'][:len(old['dcline']), :3], old['dcline'][:, :3])
        candidate_snapshot = snapshot(candidate_model_dir, candidate_runtime_dir, OUT / 'candidate_bundle')
        bound_receipt = OUT / 'candidate_receipt.json'; authenticated_copy(candidate_receipt, bound_receipt)
        contract.update(candidate_bound=True, candidate_receipt=record(bound_receipt), candidate_snapshot=record(candidate_snapshot),
            candidate_generator_rows=len(candidate['generator_bus_ids']), candidate_fixed_transfer_rows=len(candidate['templates'][0]['dcline']),
            candidate_model_directory=candidate_model_dir.relative_to(ROOT).as_posix(),
            candidate_runtime_directory=candidate_runtime_dir.relative_to(ROOT).as_posix())
    target = OUT / 'replay_contract.json'
    if target.exists():
        prior = json.loads(target.read_text())
        # These describe the original freeze, not a requirement to keep Git at
        # that commit forever. All executable inputs are authenticated above.
        # Reusing an identical frozen bundle after committing its delivery must
        # preserve the original provenance without rewriting the contract.
        contract['source_HEAD'] = prior['source_HEAD']
        contract['source_branch'] = prior['source_branch']
        if prior != contract:
            assert not list(OUT.glob('*/annual_axes.mat')), 'A replay already uses this frozen contract.'
            assert not prior['candidate_bound'] and contract['candidate_bound'], 'Refusing to revise an existing contract unexpectedly.'
            target.write_text(json.dumps(contract, indent=2) + '\n', encoding='utf-8')
    else: target.write_text(json.dumps(contract, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'prepared': True, 'candidate_bound': contract['candidate_bound'], 'PF_started': False,
        'baseline_qualified_hours': 8651, 'contract': target.relative_to(ROOT).as_posix()}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--candidate-model-dir', type=Path)
    parser.add_argument('--candidate-runtime-dir', type=Path); parser.add_argument('--candidate-receipt', type=Path)
    args = parser.parse_args(); main(args.candidate_model_dir, args.candidate_runtime_dir, args.candidate_receipt)
