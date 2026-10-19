"""Score already frozen independent AC predictions; never fit interface data."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from build_compact_nyiso_hourly_inputs import ROOT, verify_freeze, text_sha

FOLDER = ROOT/'output/compact_ny_2025/generation_reconstruction'
SOURCES = ROOT/'output/compact_ny_2025/generation_sources'


def main():
    freeze_sha = verify_freeze(SOURCES/'methodology_freeze.json')
    manifest = json.loads((SOURCES/'hourly_inputs/scored_extraction_manifest.json').read_text())
    assert manifest['internal_targets_extracted'] is True
    assert manifest['methodology_freeze_sha256'] == freeze_sha
    predicted = pd.read_csv(FOLDER/'blind_interface_predictions.csv')
    targets = pd.read_csv(SOURCES/'hourly_inputs/scored_interfaces.csv')
    metadata = pd.read_csv(SOURCES/'hourly_inputs/snapshots.csv')
    assert not targets.duplicated(['scenario_id','interface_name']).any()
    cols = ['scenario_id','interface_name','actual_flow_mw','target_flow_mw','coverage_qualified',
            'backward_hold_mean_mw','linear_mean_mw','duplicate_lower_hour_mean_mw','duplicate_upper_hour_mean_mw']
    targets = targets[cols].rename(columns={'coverage_qualified':'target_coverage_qualified'})
    d = predicted.merge(targets, on=['scenario_id','interface_name'], how='left', validate='one_to_one')
    meta = ['scenario_id'] + [c for c in ['campaign_role','vintage','scale_factor_gamma'] if c not in d.columns]
    d = d.merge(metadata[meta], on='scenario_id', validate='many_to_one')
    d['residual_mw'] = d.model_flow_mw-d.target_flow_mw
    d['absolute_residual_mw'] = d.residual_mw.abs()
    d['previous_operator_absolute_residual_mw'] = (d.previous_operator_model_flow_mw-d.target_flow_mw).abs()
    d['normalized_absolute_error_floor100'] = d.absolute_residual_mw/np.maximum(100,d.target_flow_mw.abs())
    d['observation_scale_residual_mw'] = d.residual_mw/d.scale_factor_gamma
    d['used_in_prior'] = False
    d['used_in_optimizer'] = False
    d['exact_public_operator'] = False
    d['methodology_freeze_sha256'] = freeze_sha
    rows = []
    for sid,b in d.groupby('scenario_id', sort=False):
        valid = (b.target_coverage_qualified.astype(str).str.lower().isin(['true','1'])
                 & b.electrical_baseline_qualified.astype(str).str.lower().isin(['true','1'])
                 & np.isfinite(b.target_flow_mw) & np.isfinite(b.model_flow_mw))
        q = b.loc[valid]
        rows.append(dict(scenario_id=sid, campaign_role=b.campaign_role.iloc[0],vintage=b.vintage.iloc[0],
                         scored_interfaces=len(q), interface_mae_benchmark_mw=q.absolute_residual_mw.mean(),
                         interface_max_error_benchmark_mw=q.absolute_residual_mw.max(),
                         previous_operator_mae_benchmark_mw=q.previous_operator_absolute_residual_mw.mean(),
                         mean_normalized_error_floor100=q.normalized_absolute_error_floor100.mean(),
                         interface_targets_used_in_optimizer=False, exact_public_operator=False))
    summary = pd.DataFrame(rows)
    d.to_csv(FOLDER/'scored_interface_comparison.csv',index=False,lineterminator='\n')
    summary.to_csv(FOLDER/'scored_interface_summary.csv',index=False,lineterminator='\n')
    record = dict(methodology_freeze_sha256=freeze_sha,
                  scored_targets_sha256_lf_normalized=text_sha(SOURCES/'hourly_inputs/scored_interfaces.csv'),
                  scoring_code_sha256_lf_normalized=text_sha(Path(__file__)),
                  optimizer_called_by_scoring=False, exact_public_interface_validation=False)
    (FOLDER/'scoring_manifest.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
    print(summary.to_string(index=False))


if __name__ == '__main__':
    main()
