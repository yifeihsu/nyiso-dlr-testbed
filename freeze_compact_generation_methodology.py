"""Freeze target-free methods, inputs and saved predictions before scoring."""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import pandas as pd
from build_compact_nyiso_hourly_inputs import ROOT, PROTOCOL, sha, text_sha, verify_freeze

FOLDER = ROOT/'output/compact_ny_2025/generation_reconstruction'
DEST = ROOT/'output/compact_ny_2025/generation_sources/methodology_freeze.json'
NEW_CODE = [
    'audit_compact_nyiso_time_alignment.py', 'build_compact_nyiso_hourly_inputs.py',
    'build_compact_epa_generation_inputs.py', 'build_compact_nonfossil_generation_inputs.py',
    'build_compact_combined_generation_prior.py', 'freeze_compact_generation_methodology.py',
    'build_compact_named_generation_priors.py', 'replay_compact_generation_reconstruction.m',
    'score_compact_generation_reconstruction.py', 'run_compact_ny_generation_reconstruction.m',
    'System Matpower Format/NY_Lite/compact_nyiso_interface_operator_variant.m',
    'System Matpower Format/NY_Lite/apply_compact_independent_generation_prior.m',
]


def freeze():
    assert not DEST.exists(), 'Existing freeze must not be silently replaced'
    extraction = json.loads((ROOT/'output/compact_ny_2025/generation_sources/hourly_inputs/extraction_manifest.json').read_text())
    assert extraction['internal_targets_extracted'] is False
    targets = pd.read_csv(ROOT/'output/compact_ny_2025/generation_sources/hourly_inputs/interfaces.csv')
    assert targets.target_flow_mw.isna().all() and targets.actual_flow_mw.isna().all()
    predictions = pd.read_csv(FOLDER/'blind_interface_predictions.csv')
    assert 'target_flow_mw' not in predictions and 'actual_flow_mw' not in predictions
    assert not predictions.duplicated(['scenario_id','interface_name']).any()
    reserved = json.loads(PROTOCOL.read_text())['new_calendar_selected_2025_validation_hours']
    assert set(x['scenario_id'] for x in reserved).issubset(set(predictions.scenario_id))
    paths = set(ROOT/name for name in NEW_CODE)
    old_manifest = ROOT/'output/compact_ny_2025/electrical_fixed_peak/electrical_code_manifest.csv'
    paths.add(old_manifest)
    paths.update(ROOT/p for p in pd.read_csv(old_manifest).relative_path)
    paths.add(ROOT/'output/compact_ny_2025/electrical_fixed_peak/compact_ny_2025_electrical_campaign.mat')
    sources = ROOT/'output/compact_ny_2025/generation_sources'
    paths.update(p for p in sources.rglob('*') if p.is_file() and p.suffix in {'.csv','.json'}
                 and not p.name.startswith('scored_') and p != DEST)
    paths.update(p for p in FOLDER.rglob('*') if p.is_file() and p.suffix in {'.csv','.mat','.json'})
    files = []
    for p in sorted(paths):
        assert p.is_file(), f'Missing frozen dependency {p}'
        normalization = 'raw_bytes' if p.suffix == '.mat' else 'LF_text'
        files.append(dict(path=p.relative_to(ROOT).as_posix(), normalization=normalization,
                          sha256=sha(p) if normalization == 'raw_bytes' else text_sha(p)))
    manifest = dict(method='independent_generation_v1_target_free_prediction_freeze',
                    frozen_at_utc=datetime.now(timezone.utc).isoformat(),
                    internal_targets_used_to_form_prior=False,
                    internal_targets_used_to_solve_saved_predictions=False,
                    original_hours_role='revisited_diagnostics_not_fresh_holdouts',
                    new_hours_role='calendar_selected_before_internal_target_access',
                    protocol_sha256_lf_normalized=text_sha(PROTOCOL),
                    new_validation_scenarios=[x['scenario_id'] for x in reserved],
                    prediction_scenarios=predictions.scenario_id.nunique(), files=files)
    DEST.write_bytes((json.dumps(manifest, indent=2)+'\n').encode())
    print(f'Frozen {len(files)} dependencies and {len(predictions)} target-free interface predictions.')
    print('Verified freeze SHA256:', verify_freeze(DEST))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        print('Verified freeze SHA256:', verify_freeze(DEST))
    else:
        freeze()
