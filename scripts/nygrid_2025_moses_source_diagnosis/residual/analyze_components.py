"""Fixed-cut source-component diagnostics; no model, source or dispatch fit."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from metrics import metrics, distribution, pearson, spearman, demean, shifted, strict_triplet, contiguous_pairs, finite_json

ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / 'output/nygrid_2025_moses_source_diagnosis'
OUT = INPUT / 'residual'


def record(path):
    with path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    input_path = INPUT / 'components.npz'; contract_path = INPUT / 'balance_contract.json'; csv_path = INPUT / 'balance_hourly.csv'
    a = np.load(input_path); contract = json.loads(contract_path.read_text()); assert contract['passed']
    q = a['qualified'].astype(bool); state = a['state_index']; f = a['primary_Moses_MW']; y = a['observed_Moses_MW']; e = f - y
    mid = a['fixed_input_midpoint_MW']; c = a['terminal_correction_MW']
    time = pd.DatetimeIndex(pd.to_datetime(a['timestamp_utc'], utc=True)); local = time.tz_convert('America/New_York')
    assert len(time) == 8760 and q.sum() == 8651 and np.all(np.diff(time.asi8) == 3600 * 10 ** 9)
    assert np.array_equal(local.month, a['month_local']) and np.array_equal(local.hour, a['hour_local'])
    component_keys = ['StLawrence_PG_MW', 'other_D_PG_MW', 'HQ_MW', 'PAR1_MW', 'PAR2_MW', 'PAR_total_MW', 'gross_D_load_MW']
    components = {k: a[k] for k in component_keys}
    for key in component_keys:
        assert np.isfinite(components[key][q]).all()
        if key + '_finite' in a: assert np.array_equal(a[key + '_finite'], np.isfinite(components[key]))
    identity = a['StLawrence_PG_MW'] + a['other_D_PG_MW'] + a['HQ_MW'] + a['PAR1_MW'] + a['PAR2_MW'] - a['gross_D_load_MW']
    identity_error = float(np.max(abs(identity[q] - mid[q])))
    primary_error = float(np.max(abs(identity[q] + c[q] - f[q])))
    assert max(identity_error, primary_error) < 1e-8
    assert np.max(abs(e[q] - a['residual_primary_MW'][q])) < 1e-10
    assert np.max(abs(a['StLawrence_PG_MW'][q] - e[q] - a['oracle_StLawrence_hold_other_inputs_and_terminal_MW'][q])) < 1e-9
    source_comparison = ROOT / 'output/nygrid_2025_physical_repair/annual/physical_repair_v1/comparison/comparison_arrays.npz'
    current = np.load(source_comparison); assert np.array_equal(q, current['candidate_qualified'])
    assert np.max(abs(f[q] - current['candidate_legacy_signed_literal_from'][q, 3])) < 1e-10
    adjacent = contiguous_pairs(q, state)
    effects = {'StLawrence_generation': ('StLawrence_PG_MW', 1), 'HQ_import': ('HQ_MW', 1),
        'Ontario_PAR1': ('PAR1_MW', 1), 'Ontario_PAR2': ('PAR2_MW', 1), 'Ontario_PAR_sum': ('PAR_total_MW', 1),
        'gross_zoneD_load': ('gross_D_load_MW', -1), 'P32_observation': ('observed_Moses_MW', None)}
    cohorts = {name: strict_triplet(q, state, a[key], y) for name, (key, sign) in effects.items()}
    common = np.logical_and.reduce(list(cohorts.values()))
    timing = []; timing_month = []; membership = []
    for name, (key, sign) in effects.items():
        x = a[key]
        for cohort_name, selected in [('component_triplet', cohorts[name]), ('all_component_common_triplet', common)]:
            base = metrics(f[selected], y[selected]); n = int(selected.sum())
            membership.extend({'component': name, 'cohort': cohort_name, 'hour_index': int(h + 1)} for h in np.flatnonzero(selected))
            for lag in [-1, 0, 1]:
                if sign is None: trial = f; target = shifted(y, lag); delta = target - y
                else: delta = sign * (shifted(x, lag) - x); trial = f + delta; target = y
                result = metrics(trial[selected], target[selected]); assert result['hours'] == n
                if lag == 0: assert abs(result['MAE_public_MW'] - base['MAE_public_MW']) < 1e-12
                row = {'component': name, 'cohort': cohort_name, 'lag_physical_hours': lag,
                    'positive_lag': 'use source at t+lag for evaluation at t', 'baseline_MAE_public_MW': base['MAE_public_MW'],
                    'MAE_change_public_MW': result['MAE_public_MW'] - base['MAE_public_MW'],
                    'mean_absolute_changed_term_public_MW': float(abs(delta[selected]).mean()), **result}
                timing.append(row)
                for month in range(1, 13):
                    use = selected & (local.month == month)
                    b = metrics(f[use], y[use]); z = metrics(trial[use], target[use])
                    timing_month.append({'component': name, 'cohort': cohort_name, 'lag_physical_hours': lag, 'month': month,
                        'baseline_MAE_public_MW': b['MAE_public_MW'], 'MAE_change_public_MW': z['MAE_public_MW'] - b['MAE_public_MW'], **z})
    pd.DataFrame(timing).to_csv(OUT / 'timing_diagnostics.csv', index=False)
    pd.DataFrame(timing_month).to_csv(OUT / 'timing_monthly_stability.csv', index=False)
    pd.DataFrame(membership).to_csv(OUT / 'timing_cohort_membership.csv', index=False)
    profiles = []; associations = []; conditional = []; ramps = []
    all_components = {**components, 'other_D_Hydro_MW': a['other_D_Hydro_MW'], 'other_D_Wind_MW': a['other_D_Wind_MW'],
        'other_D_Combined_Fossil_MW': a['other_D_Combined_Fossil_MW'], 'other_D_Other_Renewables_MW': a['other_D_Other_Renewables_MW'],
        'terminal_correction_MW': c, 'fixed_input_midpoint_MW': mid, 'observed_Moses_MW': y}
    for key, x in all_components.items():
        for group_kind, labels in [('month', local.month), ('local_hour', local.hour)]:
            for group in sorted(set(labels[q])):
                use = q & (labels == group)
                profiles.append({'component': key, 'group_kind': group_kind, 'group_value': int(group), **distribution(x[use]),
                    'primary_residual_mean_public_MW': float(e[use].mean()), 'primary_residual_MAE_public_MW': float(abs(e[use]).mean())})
        dx = x - shifted(x, -1); de = e - shifted(e, -1)
        associations.append({'component': key, 'hours': int(q.sum()), 'raw_Pearson_with_primary_residual': pearson(e[q], x[q]),
            'raw_Spearman_with_primary_residual': spearman(e[q], x[q]),
            'month_demeaned_Pearson': pearson(demean(e[q], local.month[q]), demean(x[q], local.month[q])),
            'local_hour_demeaned_Pearson': pearson(demean(e[q], local.hour[q]), demean(x[q], local.hour[q])),
            'ramp_pairs': int(adjacent.sum()), 'ramp_Pearson': pearson(de[adjacent], dx[adjacent]),
            'covariance_with_primary_residual_MW2': float(np.cov(e[q], x[q], ddof=0)[0, 1]),
            'mechanical_dependence_warning': 'Residual algebra contains these balance terms; correlation does not establish source error or causation.'})
        for hour in range(24):
            use = adjacent & (local.hour == hour)
            ramps.append({'component': key, 'local_hour_at_end_of_ramp': hour, **distribution(dx[use]),
                'mean_residual_ramp_public_MW': float(de[use].mean())})
        if key in component_keys:
            bins = pd.qcut(pd.Series(x[q]), 4, duplicates='drop')
            for interval in bins.cat.categories:
                inside = (bins == interval).to_numpy(); use = np.flatnonzero(q)[inside]
                conditional.append({'component': key, 'group_type': 'source_value_quartile', 'group_label': str(interval),
                    'source_min_public_MW': float(x[use].min()), 'source_max_public_MW': float(x[use].max()), **metrics(f[use], y[use])})
            for label, use in [('negative', q & (x < 0)), ('zero', q & (x == 0)), ('positive', q & (x > 0))]:
                if use.any(): conditional.append({'component': key, 'group_type': 'source_sign', 'group_label': label,
                    'source_min_public_MW': float(x[use].min()), 'source_max_public_MW': float(x[use].max()), **metrics(f[use], y[use])})
    pd.DataFrame(profiles).to_csv(OUT / 'component_calendar_profiles.csv', index=False)
    pd.DataFrame(associations).to_csv(OUT / 'component_residual_associations.csv', index=False)
    pd.DataFrame(conditional).to_csv(OUT / 'source_conditioned_error_metrics.csv', index=False)
    pd.DataFrame(ramps).to_csv(OUT / 'component_local_hour_ramps.csv', index=False)
    # Required changes are algebraic oracle diagnostics. No replacement input
    # vector is fed into any PF or source file; global balance is not repaired.
    required = {'hold_terminal_correction': y - f, 'remove_terminal_correction': y - mid}
    bounds = []; required_summaries = []; required_hourly = pd.DataFrame({'hour_index': a['hour_index'], 'timestamp_utc': a['timestamp_utc'], 'qualified': q})
    pg = a['StLawrence_PG_MW']; lower = a['StLawrence_Pmin_MW']; upper = a['StLawrence_Pmax_MW']
    assert np.isfinite(np.c_[pg[q], lower[q], upper[q]]).all() and np.all(lower[q] <= pg[q] + 1e-8) and np.all(pg[q] <= upper[q] + 1e-8)
    for case, adjustment in required.items():
        oracle = pg + adjustment; below = oracle < lower - 1e-7; above = oracle > upper + 1e-7
        required_hourly[case + '_required_net_adjustment_public_MW'] = adjustment
        required_hourly[case + '_oracle_StLawrence_public_MW'] = oracle
        required_hourly[case + '_oracle_below_StLawrence_bound'] = q & below
        required_hourly[case + '_oracle_above_StLawrence_bound'] = q & above
        for month in [0] + list(range(1, 13)):
            use = q if month == 0 else q & (local.month == month)
            calendar_hours = 8760 if month == 0 else int(np.sum(local.month == month))
            required_summaries.append({'required_adjustment_definition': case, 'month': month, **distribution(adjustment[use])})
            bounds.append({'required_adjustment_definition': case, 'month': month, 'qualified_hours': int(use.sum()),
                'calendar_hours': calendar_hours, 'qualified_fraction_of_calendar': float(use.sum() / calendar_hours),
                'oracle_StLawrence_below_lower_bound_hours': int((use & below).sum()),
                'oracle_StLawrence_above_upper_bound_hours': int((use & above).sum()),
                'oracle_within_current_StLawrence_bounds_hours': int((use & ~below & ~above).sum()),
                'current_StLawrence_at_upper_bound_hours': int((use & (abs(pg - upper) <= 1e-7)).sum()),
                'maximum_oracle_lower_shortfall_public_MW': float(np.maximum(lower[use] - oracle[use], 0).max()),
                'maximum_oracle_upper_excess_public_MW': float(np.maximum(oracle[use] - upper[use], 0).max()),
                'current_StLawrence_mean_public_MW': float(pg[use].mean()), 'oracle_StLawrence_mean_public_MW': float(oracle[use].mean()),
                'current_StLawrence_energy_on_qualified_hours_MWh': float(pg[use].sum()),
                'oracle_StLawrence_energy_on_qualified_hours_MWh': float(oracle[use].sum()),
                'required_energy_change_on_qualified_hours_MWh': float(adjustment[use].sum()),
                'necessary_plant_bound_check_only': True, 'full_calendar_EIA_energy_comparison': False,
                'statewide_balance_ramping_reservoir_and_AC_feasibility_checked': False})
    required_hourly.to_csv(OUT / 'required_adjustment_hourly_DIAGNOSTIC_ONLY.csv', index=False)
    pd.DataFrame(required_summaries).to_csv(OUT / 'required_adjustment_distributions.csv', index=False)
    pd.DataFrame(bounds).to_csv(OUT / 'conditional_StLawrence_bound_checks.csv', index=False)
    # Fixed UTC triplets, rather than repeated/omitted local-clock labels, bind
    # all timing tests. Explicitly count DST-adjacent evaluated hours.
    offsets = np.array([int(x.utcoffset().total_seconds()) for x in local.to_pydatetime()])
    dst_change = np.flatnonzero(np.r_[False, np.diff(offsets) != 0])
    dst_examples = []
    for pos in dst_change:
        for i in range(max(0, pos - 2), min(8760, pos + 3)):
            dst_examples.append({'hour_index': i + 1, 'UTC': time[i].isoformat(), 'NY_local': local[i].isoformat(),
                'current_qualified': bool(q[i]), 'common_triplet_eligible': bool(common[i])})
    pd.DataFrame(dst_examples).to_csv(OUT / 'timing_DST_boundary_readback.csv', index=False)
    report = {'passed': True, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Frozen-cut residual/source timing and necessary-bound diagnostics; no model/source replacement or new PF.',
        'qualified_hours': int(q.sum()), 'exact_component_to_midpoint_error_public_MW': identity_error,
        'exact_component_to_primary_error_public_MW': primary_error,
        'baseline_primary': metrics(f[q], y[q]), 'baseline_midpoint': metrics(mid[q], y[q]),
        'mean_terminal_correction_public_MW': float(c[q].mean()),
        'timing_common_triplet_hours': int(common.sum()),
        'timing_component_triplet_hours': {k: int(v.sum()) for k, v in cohorts.items()},
        'timing_neighbor_availability_policy': 'Conservative current-qualified same-state triplets plus finite component/observation arrays; no claim that finite-only flags certify independent raw source quality.',
        'every_predeclared_lag_reported': True, 'clock_shift_selected_or_promoted': False,
        'required_adjustment_distributions_annual': [row for row in required_summaries if row['month'] == 0],
        'conditional_StLawrence_bounds_annual': [row for row in bounds if row['month'] == 0],
        'source_errors_identified_from_correlation': False, 'oracle_input_applied': False,
        'global_balance_of_oracle_changes_claimed': False,
        'limitations': ['Every timing replacement holds the original hour terminal-loss correction fixed; it is an accounting sensitivity, not a new AC solution.',
            'An error-reducing lag does not establish a timestamp defect. Provider clock semantics and independent source evidence govern any correction.',
            'Residual/source associations contain shared algebraic terms and common reconstruction constraints; they are noncausal.',
            'An oracle StLawrence value assumes every other input and the meter boundary are correct. Passing its plant box is necessary, not sufficient for feasible generation or attribution.',
            'Qualified-hour energy totals are not complete calendar-month energy; they must not be equated to EIA monthly generation.'],
        'sources': [record(p) for p in [input_path, csv_path, contract_path, source_comparison, Path(__file__), Path(__file__).with_name('metrics.py'), Path(__file__).with_name('analysis_design.json')]],
        'outputs': [record(OUT / name) for name in ['timing_diagnostics.csv', 'timing_monthly_stability.csv', 'timing_cohort_membership.csv',
            'component_calendar_profiles.csv', 'component_residual_associations.csv', 'source_conditioned_error_metrics.csv', 'component_local_hour_ramps.csv',
            'required_adjustment_hourly_DIAGNOSTIC_ONLY.csv', 'required_adjustment_distributions.csv', 'conditional_StLawrence_bound_checks.csv', 'timing_DST_boundary_readback.csv']]}
    (OUT / 'component_timing_review.json').write_text(json.dumps(finite_json(report), indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'hours': int(q.sum()), 'common_triplet': int(common.sum()), 'annual_bounds': report['conditional_StLawrence_bounds_annual']}))


if __name__ == '__main__': main()
