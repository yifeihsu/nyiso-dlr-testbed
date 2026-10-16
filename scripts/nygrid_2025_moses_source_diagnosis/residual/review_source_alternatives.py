"""Independently score source-defined HQ/PAR aggregation alternatives.

All 8651 fixed hours, one component changed, original terminal loss held fixed.
No AC replay or source/model promotion is performed.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from metrics import metrics, finite_json

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'output/nygrid_2025_moses_source_diagnosis'
OUT = BASE / 'residual'


def record(path):
    with path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest}


def main():
    component_path = BASE / 'components.npz'; source_path = BASE / 'boundary/hourly_boundary_diagnostics.csv'
    receipt_path = BASE / 'boundary/boundary_audit_receipt.json'; producer_path = BASE / 'boundary/algebraic_probe_metrics.csv'
    a = np.load(component_path); b = pd.read_csv(source_path); source_receipt = json.loads(receipt_path.read_text())
    producer = pd.read_csv(producer_path).set_index('probe')
    q = a['qualified'].astype(bool); f = a['primary_Moses_MW']; y = a['observed_Moses_MW']
    assert q.sum() == 8651 and np.array_equal(b.hour_index.to_numpy(), a['hour_index'])
    assert np.array_equal(b.timestamp_utc.astype(str), a['timestamp_utc']) and np.array_equal(b.qualified.to_numpy(), q)
    assert b.loc[q, 'PAR_aggregation_common_cohort'].all() and b.loc[q, 'EIA_source_quality_qualified'].all()
    assert np.max(abs(b.loc[q, 'PAR_total_forward_hold_MW'].to_numpy() - a['PAR_total_MW'][q])) < 1e-9
    assert np.max(abs(b.loc[q, 'HQ_native_actual_import_MW'].to_numpy() - a['HQ_MW'][q])) < 1e-9
    assert source_receipt['new_AC_power_flows_run'] == 0 and not source_receipt['source_replacement_promoted']
    delta = {
        'current_frozen_inputs': np.zeros(8760),
        'PAR_backward_hold_only': b.PAR_total_backward_hold_MW.to_numpy() - a['PAR_total_MW'],
        'PAR_linear_interpolation_only': b.PAR_total_linear_MW.to_numpy() - a['PAR_total_MW'],
        'PAR_unweighted_sample_mean_only': b.PAR_total_arithmetic_mean_MW.to_numpy() - a['PAR_total_MW'],
        'HQ_original_schedule_including_Cedars_only': b.HQ_original_schedule_with_Cedars_MW.to_numpy() - a['HQ_MW']}
    rows = []; differences = []
    for name, change in delta.items():
        assert np.isfinite(change[q]).all()
        for month in [0] + list(range(1, 13)):
            use = q if month == 0 else q & (a['month_local'] == month)
            base = metrics(f[use], y[use]); trial = metrics(f[use] + change[use], y[use])
            amount = float(np.mean(abs(change[use]))); difference = trial['MAE_public_MW'] - base['MAE_public_MW']
            assert abs(difference) <= amount + 1e-9
            rows.append({'probe': name, 'month': month, 'cohort': 'same_current_8651_hours_by_month', **trial,
                'baseline_MAE_public_MW': base['MAE_public_MW'], 'MAE_change_public_MW': difference,
                'mean_absolute_changed_input_public_MW': amount,
                'maximum_possible_MAE_reduction_from_this_delta_public_MW': amount,
                'MAE_lower_bound_from_triangle_inequality_public_MW': max(0., base['MAE_public_MW'] - amount),
                'total_absolute_error_on_qualified_hours_MWh': float(abs(f[use] + change[use] - y[use]).sum()),
                'original_terminal_correction_held_fixed': True, 'fresh_AC_validation': False, 'source_or_model_promoted': False})
            if month == 0:
                original = producer.loc[name]; assert int(original.hours) == int(use.sum())
                mapping = {'MAE_public_MW': 'MAE_MW', 'RMSE_public_MW': 'RMSE_MW', 'WAPE_percent': 'WAPE_percent',
                    'bias_public_MW': 'mean_residual_MW', 'absolute_error_p95_public_MW': 'p95_absolute_error_MW'}
                for key, source_key in mapping.items():
                    discrepancy = abs(trial[key] - float(original[source_key])); assert discrepancy < 1e-9
                    differences.append(discrepancy)
                assert abs(amount - original.mean_absolute_input_change_MW) < 1e-9
                assert not bool(original.fresh_AC_replay_run) and not bool(original.source_replacement_promoted)
    table = pd.DataFrame(rows); output = OUT / 'source_defined_alternative_metrics.csv'; table.to_csv(output, index=False)
    annual = table[table.month == 0]
    report = {'passed': True, 'created_utc': datetime.now(timezone.utc).isoformat(), 'qualified_hours': int(q.sum()),
        'scope': 'Independent arithmetic readback and scoring of source-defined P34 aggregations and original HQ schedule on an identical current cohort; no AC solve.',
        'same_cohort_all_probes': True, 'maximum_producer_metric_discrepancy': max(differences),
        'source_defined_alternatives': annual.to_dict('records'),
        'original_terminal_correction_held_fixed': True, 'no_clock_sign_default_or_source_replacement_promoted': True,
        'interpretation': 'For a fixed input delta, the possible MAE improvement cannot exceed mean(abs(delta)). This bounds only the tested aggregation/schedule substitutions, not all possible raw-source or physical-meter errors.',
        'limitations': ['P34 timestamp interval semantics remain unverified; alternative aggregations are sensitivities, not validated source corrections.',
            'The original HQ schedule is a different quantity from NYIS actual interchange; replacing actual with schedule is not a proposed correction.',
            'Holding all other inputs and terminal losses fixed does not restore whole-system active/reactive feasibility or constitute a new annual PF.'],
        'sources': [record(p) for p in [component_path, source_path, receipt_path, producer_path, Path(__file__), Path(__file__).with_name('metrics.py')]],
        'outputs': [record(output)]}
    (OUT / 'source_alternative_review.json').write_text(json.dumps(finite_json(report), indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(annual[['probe', 'hours', 'MAE_public_MW', 'MAE_change_public_MW', 'mean_absolute_changed_input_public_MW']].to_string(index=False))
    print(json.dumps({'passed': True, 'producer_max_difference': max(differences)}))


if __name__ == '__main__': main()
