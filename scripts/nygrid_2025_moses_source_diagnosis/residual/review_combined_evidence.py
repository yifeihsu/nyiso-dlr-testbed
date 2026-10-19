"""Independent readback of completed source, timing and boundary diagnostics.

No PF, source replacement, fitted correction or producer-module import.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'output/nygrid_2025_moses_source_diagnosis'
OUT = BASE / 'residual'


def record(path):
    with path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest}


def close(a, b, tolerance=1e-8):
    a, b = np.asarray(a, float), np.asarray(b, float)
    assert a.shape == b.shape and np.array_equal(np.isfinite(a), np.isfinite(b))
    mask = np.isfinite(a); error = float(np.max(abs(a[mask] - b[mask]))) if mask.any() else 0.
    assert error < tolerance, error
    return error


def main():
    generation = BASE / 'generation'; paths = [BASE / 'components.npz', BASE / 'balance_contract.json']
    a = np.load(paths[0]); contract = json.loads(paths[1].read_text()); q = a['qualified'].astype(bool)
    assert contract['passed'] and q.sum() == 8651 and len(q) == 8760
    pg = a['StLawrence_PG_MW']; f = a['primary_Moses_MW']; observed = a['observed_Moses_MW']; month = a['month_local']
    generation_receipt_path = generation / 'generation_audit_receipt.json'; g = json.loads(generation_receipt_path.read_text())
    assert g['passed'] and not g['new_PF_or_optimization_run'] and not g['default_model_changed']
    assert record(generation_receipt_path)['sha256'] == '8d38b658e34113c41e1ef4015550366fdf40a092d5090f1078301013b07df264'
    # Bind every final producer output and the source code, without rerunning it.
    for item in g['outputs']:
        assert record(ROOT / item['path'])['sha256'] == item['sha256']
    assert record(ROOT / g['producer']['path'])['sha256'] == g['producer']['sha256']
    monthly_path = generation / 'StLawrence_monthly_source_energy_and_allocation.csv'
    monthly = pd.read_csv(monthly_path).set_index('month')
    trace_path = generation / 'StLawrence_hourly_source_trace.csv'; trace = pd.read_csv(trace_path)
    assert np.array_equal(trace.hour_index, a['hour_index']) and np.array_equal(trace.qualified, q)
    close(trace.current_StL_PG_MW, pg)
    bounds_path = generation / 'StLawrence_annual_energy_bounds.json'; bounds = json.loads(bounds_path.read_text())
    energy = monthly.EIA_final_net_generation_MWh.sum(); known = pg[q].sum(); missing_upper = (~q).sum() * 802.5
    close(energy, 6726939.); close(bounds['known_qualified_model_energy_MWh'], known)
    close(bounds['maximum_unmodeled_energy_at_frozen_cap_MWh'], missing_upper)
    close(bounds['minimum_EIA_gap_after_allowing_missing_hours_at_cap_MWh'], energy - known - missing_upper)
    assert bounds['missing_hour_bound_uses_full_nominal_admitted_cap_even_where_available_cap_metadata_is_missing']
    close(bounds['NYPA_official_OpenNY_full_year_net_MWh'], 6730000.)
    current_flat = np.full(8760, np.nan); eia_flat = current_flat.copy(); monthly_checks = []
    for m in range(1, 13):
        all_month = month == m; use = q & all_month; row = monthly.loc[m]
        n = int(all_month.sum()); count = int(use.sum()); mu = float(row.EIA_final_net_generation_MWh / n)
        assert int(row.physical_calendar_hours) == n and int(row.qualified_hours) == count
        assert n - count == int(row.unmodeled_source_hours)
        close(row.EIA_full_physical_calendar_mean_MW, mu)
        close(row.current_dispatch_qualified_energy_MWh, pg[use].sum())
        close(row.unmodeled_hours_max_energy_under_current_cap_MWh, (n - count) * 802.5)
        close(row.full_month_completion_upper_bound_holding_qualified_dispatch_MWh, pg[use].sum() + (n - count) * 802.5)
        lower_gap = row.EIA_final_net_generation_MWh - pg[use].sum() - (n - count) * 802.5
        close(row.EIA_energy_above_that_completion_upper_bound_MWh, lower_gap); assert lower_gap > 0
        decomposition = (row.EIA_full_physical_calendar_mean_MW + row.calendar_denominator_effect_MW
            + row.cap_clipping_contribution_to_prior_mean_MW + row.below_baseline_P63_contribution_to_prior_mean_MW
            + row.above_baseline_P63_contribution_to_prior_mean_MW + row.final_dispatch_minus_prior_mean_MW)
        close(decomposition, pg[use].mean())
        close(trace.loc[use, 'clipped_month_baseline_MW'] + trace.loc[use, 'low_P63_projection_contribution_MW']
              + trace.loc[use, 'high_P63_projection_contribution_MW'], trace.loc[use, 'frozen_StL_prior_MW'])
        close(trace.loc[use, 'current_minus_frozen_prior_MW'], pg[use] - trace.loc[use, 'frozen_StL_prior_MW'].to_numpy())
        current_flat[use] = pg[use].mean(); eia_flat[use] = mu
        monthly_checks.append({'month': m, 'physical_hours': n, 'qualified_hours': count,
            'missing_hours_max_energy_MWh': float((n - count) * 802.5), 'minimum_source_energy_gap_MWh': float(lower_gap)})
    assert monthly.loc[3, 'physical_calendar_hours'] == 743 and monthly.loc[11, 'physical_calendar_hours'] == 721
    conflict_months = monthly.index[monthly.EIA_final_net_generation_MWh > monthly.physical_calendar_hours * 802.5].tolist()
    assert conflict_months == [4, 5, 6, 7]
    inventory_path = generation / 'StLawrence_inventory_status_by_month.csv'; inventory = pd.read_csv(inventory_path)
    active = inventory[inventory.status_code == 'OP']
    for m in range(13):
        z = active[active.source_month == m]; assert len(z) == 15
        close(z.summer_MW.sum(), 802.5); close(z.nameplate_MW.sum(), 855.)
    swapping = inventory[inventory['Generator ID'].isin([21, 26])].set_index(['source_month', 'Generator ID'])
    for m in range(1, 13):
        assert swapping.loc[(m, 21), 'status_code'] == ('OP' if m <= 2 else 'OA')
        assert swapping.loc[(m, 26), 'status_code'] == ('OA' if m <= 2 else 'OP')
    assert not inventory.status_is_hourly_observed_availability.any()
    variants_path = generation / 'conditional_generation_variants.npz'; variants = np.load(variants_path)
    scores_path = generation / 'conditional_generation_scores.csv'; scores = pd.read_csv(scores_path)
    assert np.array_equal(variants['qualified'], q) and not bool(variants['actual_AC_replay'])
    expected = {'baseline': np.where(q, pg, np.nan), 'EIA_month_mean_preserve_qualified_shape': pg - current_flat + eia_flat,
        'EIA_month_constant': eia_flat, 'current_month_mean_constant_shape_ablation': current_flat}
    variant_checks = []; score_error = 0.
    for i, name in enumerate(variants['scenario_names']):
        x = expected[str(name)]; close(x, variants['StLawrence_PG_MW'][i])
        prediction = f + x - pg; close(prediction, variants['conditional_Moses_MW'][i])
        for m in range(13):
            use = q if m == 0 else q & (month == m); row = scores[(scores.scenario == name) & (scores.month == m)].iloc[0]
            error = prediction[use] - observed[use]
            assert int(row.hours) == int(use.sum())
            for key, value in {'MAE_public_MW': abs(error).mean(), 'RMSE_public_MW': np.sqrt(np.mean(error ** 2)),
                              'bias_public_MW': error.mean(), 'WAPE_percent': 100 * abs(error).sum() / abs(observed[use]).sum()}.items():
                score_error = max(score_error, close(row[key], value))
            assert row.StLawrence_above_frozen_Pmax_hours == np.sum(x[use] > a['StLawrence_Pmax_MW'][use] + 1e-7)
            assert row.StLawrence_below_frozen_Pmin_hours == np.sum(x[use] < a['StLawrence_Pmin_MW'][use] - 1e-7)
            assert not row.AC_or_global_dispatch_feasibility_claimed and not row.hourly_generation_observed and row.cohort_unchanged
            if m == 0: variant_checks.append({'scenario': str(name), 'hours': int(use.sum()), 'MAE_public_MW': float(abs(error).mean()),
                'bias_public_MW': float(error.mean()), 'above_current_cap_hours': int(row.StLawrence_above_frozen_Pmax_hours)})
            if name == 'current_month_mean_constant_shape_ablation' and m:
                close(x[use].sum(), pg[use].sum(), 1e-7)
    timing_path = OUT / 'timing_diagnostics.csv'; timing = pd.read_csv(timing_path)
    state = a['state_index']; common = q & np.r_[False, q[:-1]] & np.r_[q[1:], False]
    common &= np.r_[False, state[1:] == state[:-1]] & np.r_[state[:-1] == state[1:], False]
    assert common.sum() == 8480
    keys = {'StLawrence_generation': ('StLawrence_PG_MW', 1), 'HQ_import': ('HQ_MW', 1), 'Ontario_PAR1': ('PAR1_MW', 1),
        'Ontario_PAR2': ('PAR2_MW', 1), 'Ontario_PAR_sum': ('PAR_total_MW', 1), 'gross_zoneD_load': ('gross_D_load_MW', -1),
        'P32_observation': ('observed_Moses_MW', None)}
    timing_error = 0.
    for name, (key, sign) in keys.items():
        for lag in [-1, 0, 1]:
            replacement = pd.Series(a[key]).shift(-lag).to_numpy()
            if sign is None: prediction, target = f, replacement
            else: prediction, target = f + sign * (replacement - a[key]), observed
            row = timing[(timing.component == name) & (timing.cohort == 'all_component_common_triplet') & (timing.lag_physical_hours == lag)].iloc[0]
            assert row.hours == 8480
            timing_error = max(timing_error, close(row.MAE_public_MW, abs(prediction[common] - target[common]).mean()))
            if lag: assert row.MAE_change_public_MW > 0
    source_review_path = OUT / 'source_alternative_review.json'; source_review = json.loads(source_review_path.read_text()); assert source_review['passed']
    for item in source_review['sources'] + source_review['outputs']:
        assert record(ROOT / item['path'])['sha256'] == item['sha256']
    model_path = ROOT / 'output/nygrid_2025_physical_repair/model/latest_model.mat'; model = loadmat(model_path, simplify_cells=True)['model']
    graph_checks = []
    for state, t in enumerate(model['templates'], 1):
        ids = t['bus'][:, 0].astype(int); lookup = {x: i for i, x in enumerate(ids)}; br = t['branch']
        keep = br[:, 10] > 0; keep[np.array([46, 51, 52]) - 1] = False; edge = br[keep, :2].astype(int)
        def components(edges):
            ff = np.array([lookup[x] for x in edges[:, 0]]); tt = np.array([lookup[x] for x in edges[:, 1]])
            return connected_components(coo_matrix((np.ones(2 * len(ff)), (np.r_[ff, tt], np.r_[tt, ff])), shape=(len(ids), len(ids))), directed=False)
        count, label = components(edge); isolated = set(ids[label == label[lookup[48]]])
        mixed, _ = components(np.vstack([edge, t['dcline'][t['dcline'][:, 2] > 0, :2].astype(int)]))
        assert count == 2 and isolated == {48, 49, 64601, 65101} and mixed == 1
        parent = t['userdata']['ac_system']['branch_parent_row']; assert br[parent == 211, 10].item() == 0
        graph_checks.append({'state_index': state, 'AC_components_after_cut_removal': count,
            'D_side_bus_ids_including_passive_interiors': sorted(map(int, isolated)), 'components_including_prescribed_transfers': mixed})
    physical_path = BASE / 'physical_boundary/physical_boundary_review.json'; physical = json.loads(physical_path.read_text())
    assert physical['physical_definition_entries'] == 21 and set(physical['entries_per_edition'].values()) == {7}
    assert not physical['physical_P32_equivalence_proved'] and physical['causal_MW_attributed_to_boundary_mismatch'] is None
    figure_path = BASE / 'daily_shape_figure_data.csv'; figure = pd.read_csv(figure_path).set_index('hour_local')
    for h in range(24):
        use = q & (a['hour_local'] == h)
        close(figure.loc[h, 'StLawrence_PG_MW'], pg[use].mean()); close(figure.loc[h, 'residual_MW'], (f[use] - observed[use]).mean())
        assert figure.loc[h, 'hours'] == use.sum()
    report_path = ROOT / 'NYGRID_2025_MOSES_SOURCE_DIAGNOSIS.md'; report = report_path.read_text(encoding='utf-8')
    assert 'pre-specified recipes' not in report
    for token in ['118.820924', '22.007617', '91.869', '148.614', '125.184', '4,160', '2,882', '8,480', 'no verified circuit-to-model mapping']:
        assert token.lower() in report.lower(), token
    assert 'not feasible redispatches' in report and 'not evidence that the real plant is constant' in report
    plan_path = generation / 'conditional_generation_plan.json'; plan = json.loads(plan_path.read_text())
    assert plan['initial_readonly_diagnostic_results_seen_before_receipt'] and not plan['target_construction_uses_P32_values']
    paths += [generation_receipt_path, monthly_path, trace_path, bounds_path, inventory_path, variants_path, scores_path, plan_path,
        timing_path, source_review_path, physical_path, model_path, figure_path, BASE / 'daily_shape_diagnosis.png', BASE / 'figure_receipt.json',
        report_path, generation / 'hourly_source_search_receipt.json', Path(__file__)]
    result = {'passed': True, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Independent completed-evidence consistency review: calendar/month energy and missing-hour bounds, source-defined generation mean/shape probes, timing cohorts, native boundary probes, graph versus physical-meter claims, final report and figure data. No new PF, optimization or source promotion.',
        'report': record(report_path), 'generation_receipt_sha256': record(generation_receipt_path)['sha256'],
        'qualified_hours': 8651, 'clock_hours': 8760, 'missing_hours': 109,
        'conservative_missing_hour_energy_bound_MWh': float(missing_upper),
        'minimum_annual_EIA_energy_gap_MWh': float(energy - known - missing_upper),
        'monthly_energy_checks': monthly_checks, 'status_inventory_operating_units_each_month': 15,
        'aggregate_seasonal_cap_MW_each_month': 802.5, 'aggregate_nameplate_MW_each_month': 855,
        'unit21_unit26_status_swap_does_not_change_aggregate_bus48_capability': True,
        'physical_calendar_hours_preserve_DST': {'March': 743, 'November': 721},
        'generation_score_maximum_recomputation_difference': score_error, 'generation_cases': variant_checks,
        'shape_only_qualified_month_energy_preserved': True, 'generation_recipes_not_claimed_preregistered': True,
        'timing_identical_triplet_hours': 8480, 'timing_maximum_independent_difference': timing_error,
        'all_tested_nonzero_lags_worsen_annual_MAE': True, 'graph_checks': graph_checks,
        'physical_definition_counts_mean_seven_members_per_edition_not_21_simultaneous_circuits': True,
        'physical_cut_equivalence_or_causal_MW_claimed': False, 'root_report_and_figure_numbers_supported': True,
        'findings': [],
        'material_limits': ['The generation energy inconsistency is independently supported, but one observed net interface cannot uniquely attribute the residual among generation, load, boundary inputs and meter scope.',
            'The illustrative flat-month profile is a sensitivity control, not actual hourly generation or a promoted source correction.',
            'Transferring full-calendar EIA means to the qualified subset assumes representativeness; separate missing-hour upper bounds address complete-year energy.',
            'Seasonal and nameplate ratings are not interchangeable actual hourly capability, and monthly status is not hourly availability.',
            'Fixed-terminal source substitutions are not AC-feasible annual replays; all current model/default inputs remain unchanged.'],
        'sources': [record(p) for p in dict.fromkeys(paths)]}
    output = OUT / 'independent_review.json'; output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'report_sha256': result['report']['sha256'], 'generation_score_error': score_error,
        'timing_error': timing_error, 'energy_gap_MWh': result['minimum_annual_EIA_energy_gap_MWh'], 'output': output.relative_to(ROOT).as_posix()}))


if __name__ == '__main__': main()
