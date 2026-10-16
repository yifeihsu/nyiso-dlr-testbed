"""Describe current Moses residuals on the preserved physical-hour axis."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from metrics import metrics, distribution, pearson, spearman, demean, shifted, lag_availability, contiguous_pairs, grouped_metrics, finite_json

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_moses_source_diagnosis/residual'


def record(path):
    with path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'output/nygrid_2025_physical_repair/annual/physical_repair_v1/comparison/comparison_arrays.npz'
    a = np.load(source); times = pd.DatetimeIndex(pd.to_datetime(a['timestamp_utc'], utc=True)); local = times.tz_convert('America/New_York')
    assert len(times) == 8760 and times.is_unique and np.all(np.diff(times.asi8) == 3600 * 10 ** 9)
    q = a['candidate_qualified'].astype(bool); state = a['topology_state_index']; assert q.sum() == 8651
    names = a['interface_names'].astype(str); index = np.flatnonzero(names == 'MOSES SOUTH').item()
    prediction = a['candidate_legacy_signed_literal_from']; observation = a['observed']; errors = prediction - observation
    f = prediction[:, index]; y = observation[:, index]; e = errors[:, index]
    seasons = np.array(['DJF', 'DJF', 'MAM', 'MAM', 'MAM', 'JJA', 'JJA', 'JJA', 'SON', 'SON', 'SON', 'DJF'])[local.month - 1]
    groups = {'month': local.month, 'season': seasons, 'local_hour': local.hour,
              'weekday_weekend': np.where(local.dayofweek < 5, 'weekday', 'weekend'), 'topology_state': state}
    rows = [{'group_kind': 'annual', 'group_value': '2025', **metrics(f[q], y[q])}]
    for label, values in groups.items(): rows.extend(grouped_metrics(f, y, q, values, label))
    summaries = pd.DataFrame(rows); summaries.to_csv(OUT / 'temporal_metrics.csv', index=False)
    adjacent = contiguous_pairs(q, state); de = e - shifted(e, -1); df = f - shifted(f, -1); dy = y - shifted(y, -1)
    frame = pd.DataFrame({'hour_index': np.arange(1, 8761), 'timestamp_utc': times.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'timestamp_local_with_offset': local.strftime('%Y-%m-%dT%H:%M:%S%z'), 'qualified': q, 'state_index': state,
        'local_month': local.month, 'local_hour': local.hour, 'local_weekday': local.dayofweek, 'season': seasons,
        'predicted_public_MW': f, 'observed_public_MW': y, 'residual_public_MW': e,
        'required_primary_balance_adjustment_public_MW': -e, 'adjacent_pair_qualified_same_state': adjacent,
        'prediction_ramp_public_MW': np.where(adjacent, df, np.nan), 'observation_ramp_public_MW': np.where(adjacent, dy, np.nan),
        'residual_ramp_public_MW': np.where(adjacent, de, np.nan)})
    frame.to_csv(OUT / 'residual_hourly_base.csv', index=False)
    ramp_rows = [{'group_kind': 'annual', 'group_value': '2025', **metrics(df[adjacent], dy[adjacent])}]
    for label, values in groups.items(): ramp_rows.extend(grouped_metrics(df, dy, adjacent, values, label))
    pd.DataFrame(ramp_rows).to_csv(OUT / 'ramp_metrics.csv', index=False)
    autocorr = []
    for lag in [1, 24, 168]:
        use = q & lag_availability(q, state, -lag)
        autocorr.append({'lag_physical_hours': lag, 'paired_hours': int(use.sum()), 'residual_Pearson': pearson(e[use], shifted(e, -lag)[use]),
            'scope': 'eligible endpoints at exact physical-hour lag; same topology state; no row compression or interpolation'})
    pd.DataFrame(autocorr).to_csv(OUT / 'residual_autocorrelation.csv', index=False)
    shared = []
    for k, name in enumerate(names):
        if k == index: continue
        other = errors[:, k]; raw = other[q]; current = e[q]
        monthcorr = pearson(demean(current, local.month[q]), demean(raw, local.month[q]))
        hourcorr = pearson(demean(current, local.hour[q]), demean(raw, local.hour[q]))
        high_moses = abs(current) >= np.quantile(abs(current), .95); high_other = abs(raw) >= np.quantile(abs(raw), .95)
        shared.append({'other_interface': name, 'hours': int(q.sum()), 'raw_Pearson': pearson(current, raw),
            'raw_Spearman': spearman(current, raw), 'month_demeaned_Pearson': monthcorr, 'local_hour_demeaned_Pearson': hourcorr,
            'same_state_ramp_pairs': int(adjacent.sum()), 'ramp_Pearson': pearson(de[adjacent], (other - shifted(other, -1))[adjacent]),
            'covariance_public_MW2': float(np.cov(current, raw, ddof=0)[0, 1]),
            'Moses_top5pct_hours': int(high_moses.sum()), 'other_top5pct_hours': int(high_other.sum()),
            'joint_top5pct_hours': int((high_moses & high_other).sum()),
            'interpretation': 'descriptive shared residuals; overlapping cuts and common source reconstruction are not independent evidence of causation'})
    pd.DataFrame(shared).to_csv(OUT / 'shared_interface_residuals.csv', index=False)
    # Rank errors for inspection only. No source/default/experiment choice uses these rows.
    extremes = frame[q].assign(absolute_error=lambda d: abs(d.residual_public_MW)).sort_values('absolute_error', ascending=False).head(30)
    extremes.to_csv(OUT / 'largest_residual_hours_descriptive.csv', index=False)
    runs = []; start = None
    for i in range(8760 + 1):
        valid = i < 8760 and q[i]
        continuous = valid and start is not None and q[i - 1] and state[i] == state[i - 1] and np.sign(e[i]) == np.sign(e[i - 1])
        if start is not None and not continuous:
            values = e[start:i]; runs.append({'start_hour_index': start + 1, 'last_hour_index': i, 'hours': i - start,
                'start_utc': times[start].isoformat(), 'end_utc': times[i - 1].isoformat(), 'sign': int(np.sign(values[0])),
                'mean_residual_public_MW': float(values.mean()), 'maximum_absolute_residual_public_MW': float(abs(values).max())})
            start = None
        if valid and start is None: start = i
    pd.DataFrame(runs).sort_values('hours', ascending=False).to_csv(OUT / 'same_sign_residual_runs.csv', index=False)
    score_path = ROOT / 'output/nygrid_2025_physical_repair/annual/physical_repair_v1/comparison/public_interface_metrics.csv'
    scores = pd.read_csv(score_path)
    official = scores.query("cohort=='candidate_all_success' and period=='annual' and model=='candidate' and convention=='legacy_signed_literal_from' and interface=='MOSES SOUTH'").iloc[0]
    summary = metrics(f[q], y[q])
    for key, other in [('MAE_public_MW', 'mae_public_MW'), ('RMSE_public_MW', 'rmse_public_MW'), ('bias_public_MW', 'bias_public_MW'), ('WAPE_percent', 'wape_percent')]:
        assert abs(summary[key] - official[other]) < 1e-9
    outputs = [OUT / name for name in ['temporal_metrics.csv', 'residual_hourly_base.csv', 'ramp_metrics.csv', 'residual_autocorrelation.csv',
        'shared_interface_residuals.csv', 'largest_residual_hours_descriptive.csv', 'same_sign_residual_runs.csv']]
    report = {'passed': True, 'created_utc': datetime.now(timezone.utc).isoformat(), 'qualified_hours': int(q.sum()),
        'scope': 'Fresh read-only summaries of the saved repaired annual comparison. Source inputs/model unchanged; no PF or fitted correction.',
        'annual_primary_metrics': summary, 'required_primary_balance_adjustment_distribution': distribution(-e[q]),
        'adjacent_same_state_qualified_pairs': int(adjacent.sum()), 'autocorrelation': autocorr,
        'DST_preserved_in_UTC_axis': True, 'local_time_used_only_for_grouping': True,
        'causal_attribution_claimed': False, 'oracle_correction_applied': False,
        'source_component_diagnosis_and_timing_tests_complete': False,
        'sources': [record(x) for x in [source, score_path, Path(__file__), Path(__file__).with_name('metrics.py'), Path(__file__).with_name('analysis_design.json')]],
        'outputs': [record(x) for x in outputs]}
    (OUT / 'temporal_review.json').write_text(json.dumps(finite_json(report), indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'hours': int(q.sum()), 'annual': summary, 'autocorrelation': autocorr}))


if __name__ == '__main__': main()
