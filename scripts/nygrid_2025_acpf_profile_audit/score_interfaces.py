"""Post-hoc AC/DC comparison on frozen hours; no fitting or model mutations.

The seven inherited zone cuts are not certified NYISO meter definitions.
Aggregate synthetic MW/gamma is a comparison convention, not a current scale.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'output/nygrid_2025_acpf_profile_audit'
sys.path.insert(0, str(Path(__file__).parent / 'alignment'))
from interface_operator import build_runtime_operator, apply_interface_flows, CONVENTIONS


def record(path):
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main(representative=False):
    destination = BASE / ('representative_comparison' if representative else 'comparison')
    destination.mkdir(parents=True, exist_ok=True)
    baseline = ROOT / 'output/nygrid_2025_dover_parameters/replay/bounded_x_nominal.npz'
    observation = ROOT / 'output/nygrid_2025_inputs/load_source/interface_wide.csv'
    dc_metric_path = ROOT / 'output/nygrid_2025_dover_parameters/comparison/annual_metrics.csv'
    dc_score_receipt_path = ROOT / 'output/nygrid_2025_dover_parameters/comparison/scoring_receipt.json'
    dc_score_receipt = json.loads(dc_score_receipt_path.read_text())
    assert dc_score_receipt['passed']
    for item in dc_score_receipt['dependencies'] + dc_score_receipt['outputs']:
        assert record(ROOT / item['path'])['sha256'] == item['sha256'], 'Stale frozen DC scoring dependency'
    contract_path = BASE / 'alignment/interface_operator_contract.json'
    contract = json.loads(contract_path.read_text())
    assert len(contract['checks']) == 4 and all(
        c['current_if_map_and_active_zone_crossing_match'] and c['original_physical_terminals_verified']
        and c['row_permutation_test_pass'] and c['positive_loss_orientation_test_pass'] for c in contract['checks'])
    for item in contract['source_receipts']:
        assert record(ROOT / item['path'])['sha256'] == item['sha256'], 'Stale interface operator dependency'
    with np.load(baseline, allow_pickle=False) as old:
        times = old['timestamp_utc'].astype(str)
        q = old['qualified'].astype(bool)
        state = old['network_state_ids'].astype(str)
        gamma = float(old['gamma'])
        dc = old['interface_pf'] / gamma
        assert np.array_equal(old['hour_index'], np.arange(1, 8761))
    state = np.array([{'refined_2025_case': 'post_dover', 'refined_2025_pre_may_case': 'pre_may',
                       'refined_2025_may21_case': 'may21', 'refined_2025_may30_case': 'may30'}[s] for s in state])
    sources = [BASE / 'acpf/representative_state_arrays.mat'] if representative else sorted((BASE / 'acpf/monthly').glob('profile_PF_2025_*.mat'))
    assert len(sources) == (1 if representative else 12), 'Incomplete ACPF output cohort'
    arrays = {name: np.full((8760, 7), np.nan) for name in (*CONVENTIONS, 'oriented_source_minus_target_loss')}
    seen = np.zeros(8760, dtype=bool)
    qualified = np.zeros(8760, dtype=bool)
    physical = np.zeros(8760, dtype=bool)
    maximum_direct_sum_error = 0.0
    names = None
    reference_keys = None
    reference_axes = None
    for path in sources:
        m = loadmat(path, simplify_cells=True)
        ix = np.asarray(m['hour_index'], int).reshape(-1) - 1
        assert np.all((ix >= 0) & (ix < 8760)), 'Hour index outside annual axis'
        assert len(np.unique(ix)) == len(ix) and not seen[ix].any()
        assert np.array_equal(np.asarray(m['timestamp_utc']).astype(str).reshape(-1), times[ix])
        assert float(m['gamma']) == gamma
        assert np.array_equal(np.asarray(m['source_qualified'], bool).reshape(-1), q[ix])
        seen[ix] = True
        eq = np.asarray(m['AC_equation_gate'], bool).reshape(-1)
        fidelity = np.asarray(m['P_profile_preservation_gate'], bool).reshape(-1)
        qualified[ix] = eq & fidelity & q[ix]
        physical[ix] = np.asarray(m['VQ_and_generator_assumption_gate'], bool).reshape(-1)
        keys = np.asarray(m['branch_keys']).astype(str)
        if reference_keys is None:
            reference_keys = keys.copy()
        assert np.array_equal(keys, reference_keys), 'Canonical branch-key axes changed'
        axes = {name: np.asarray(m[name]).reshape(-1) for name in
                ['branch_parent_row', 'branch_from_bus', 'branch_to_bus', 'bus_id', 'base_kv']}
        if reference_axes is None:
            reference_axes = {name: axis.copy() for name, axis in axes.items()}
        assert all(np.array_equal(axis, reference_axes[name]) for name, axis in axes.items()), 'Canonical node/branch metadata changed'
        parent = np.asarray(m['branch_parent_row'], int).reshape(-1)
        branch = np.column_stack((m['branch_from_bus'], m['branch_to_bus']))
        pf, pt = np.asarray(m['PF']), np.asarray(m['PT'])
        active = np.asarray(m['branch_active'], bool)
        for s in np.unique(state[ix]):
            rows = np.flatnonzero(state[ix] == s)
            operator = build_runtime_operator(branch, parent, s)
            if names is None:
                names = operator['interface_names']
            assert names == operator['interface_names']
            result = apply_interface_flows(pf[rows], pt[rows], operator, gamma)
            direct = {c: np.zeros((len(rows), 7)) for c in CONVENTIONS}
            total_loss = np.zeros((len(rows), 7))
            for term in operator['terms']:
                j = term['interface_index'] - 1
                first, last, sign = term['first_runtime_branch_row'] - 1, term['last_runtime_branch_row'] - 1, term['coefficient']
                chain = np.flatnonzero(parent == term['original_branch_row'])
                assert active[np.ix_(rows, chain)][qualified[ix[rows]]].all()
                direct[CONVENTIONS[0]][:, j] += sign * pf[rows, first] / gamma
                direct[CONVENTIONS[1]][:, j] += (pf[rows, first] if sign > 0 else pt[rows, last]) / gamma
                direct[CONVENTIONS[2]][:, j] -= (pt[rows, last] if sign > 0 else pf[rows, first]) / gamma
                total_loss[:, j] += np.sum(pf[np.ix_(rows, chain)] + pt[np.ix_(rows, chain)], axis=1) / gamma
            use = qualified[ix[rows]]
            for convention in CONVENTIONS:
                err = np.max(np.abs(direct[convention][use] - result[convention][use]), initial=0)
                maximum_direct_sum_error = max(maximum_direct_sum_error, float(err))
            assert np.allclose(total_loss[use], result['oriented_source_minus_target_loss'][use], rtol=0, atol=1e-5)
            for convention, value in result.items():
                arrays[convention][ix[rows]] = value
    if not representative:
        assert seen.all(), 'Annual files must retain all 8760 hours, including excluded placeholders'
    cohort = q & qualified & seen
    assert np.any(cohort)
    obs = pd.read_csv(observation, usecols=['timestamp_utc'] + names, float_precision='round_trip')
    assert np.array_equal(obs.timestamp_utc.to_numpy(str), times)
    y = obs[names].to_numpy(float)
    assert np.isfinite(y[cohort]).all() and np.isfinite(dc[cohort]).all()
    dc_metrics = pd.read_csv(dc_metric_path)
    dc_metrics = dc_metrics[(dc_metrics.scenario == 'bounded_x_nominal') & (dc_metrics.period == 'annual')]
    assert dc_metrics.interface.tolist() == names, 'Frozen DC companion interface-name order differs'
    assert np.all(dc_metrics.hours.to_numpy() == np.sum(q))
    for j, row in enumerate(dc_metrics.itertuples(index=False)):
        error = dc[q, j] - y[q, j]
        assert abs(float(np.mean(abs(error))) - row.mae_public_mw) < 1e-7
        assert abs(float(100 * np.sum(abs(error)) / np.sum(abs(y[q, j]))) - row.wape_percent) < 1e-7
    for name in CONVENTIONS:
        assert np.isfinite(arrays[name][cohort]).all()
    assert maximum_direct_sum_error < 1e-7
    local = pd.to_datetime(times, utc=True).tz_convert('America/New_York')
    periods = [('annual' if not representative else 'seven_selected_hours', cohort)]
    if not representative:
        periods += [(f'month_{month:02d}', cohort & (local.month == month)) for month in range(1, 13)]
        periods += [('post_Dover_full_service', cohort & (state == 'post_dover'))]
    rows = []
    for period, mask in periods:
        if not mask.any():
            continue
        for label, prediction in [('frozen_DC_bounded_x_nominal', dc)] + [(c, arrays[c]) for c in CONVENTIONS]:
            for j, name in enumerate(names):
                error = prediction[mask, j] - y[mask, j]
                dc_error = dc[mask, j] - y[mask, j]
                rows.append(dict(period=period, convention=label, interface=name, hours=int(mask.sum()),
                                 mae_public_MW=float(np.mean(abs(error))), rmse_public_MW=float(np.sqrt(np.mean(error ** 2))),
                                 bias_public_MW=float(np.mean(error)), wape_percent=float(100 * np.sum(abs(error)) / np.sum(abs(y[mask, j]))),
                                 mae_change_from_DC_public_MW=float(np.mean(abs(error)) - np.mean(abs(dc_error))),
                                 VQ_and_generator_qualified_hours=int(np.sum(physical & mask)), comparison_is_diagnostic=True))
    metrics = pd.DataFrame(rows)
    metrics.to_csv(destination / 'interface_metrics.csv', index=False, lineterminator='\n')
    np.savez_compressed(destination / 'comparison_arrays.npz', hour_index=np.arange(1, 8761), timestamp_utc=times,
                        interface_names=np.array(names), gamma=gamma, source_qualified=q, ACPF_comparison_cohort=cohort,
                        VQ_and_generator_assumption_gate=physical, observed=y, frozen_DC=dc, **arrays)
    loss_rows = [dict(interface=name, mean_source_minus_target_public_MW=float(np.mean(arrays['oriented_source_minus_target_loss'][cohort, j])),
                      maximum_source_minus_target_public_MW=float(np.max(arrays['oriented_source_minus_target_loss'][cohort, j]))) for j, name in enumerate(names)]
    pd.DataFrame(loss_rows).to_csv(destination / 'terminal_convention_differences.csv', index=False, lineterminator='\n')
    dependencies = sources + [baseline, observation, dc_metric_path, dc_score_receipt_path, contract_path,
                              Path(__file__), Path(__file__).parent / 'alignment/interface_operator.py']
    receipt = dict(passed=True, audit_complete=True, OPF_used=False, internal_interface_observations_used_for_fitting=False,
                   model_parameters_changed=False, source_qualified_hours=int(q.sum()), evaluated_hours=int(seen.sum()),
                   matched_comparison_hours=int(cohort.sum()), VQ_and_generator_qualified_comparison_hours=int(np.sum(cohort & physical)),
                   VQ_gate_excludes_branch_thermal_and_security_qualification=True,
                   frozen_DC_full_cohort_order_and_metrics_reproduced=True,
                   maximum_independent_direct_sum_error_public_MW=maximum_direct_sum_error,
                   interface_names=names, conventions=list(CONVENTIONS), gamma=gamma,
                   power_scale='aggregate_MW_divided_by_gamma_for_public_comparison_only',
                   physical_NYISO_meter_membership_and_terminal_convention_certified=False,
                   terminal_conventions_are_not_a_statistical_confidence_interval=True,
                   previous_DC_metrics_not_reused_as_AC_evidence=True,
                   dependencies=[record(p) for p in dependencies],
                   outputs=[record(destination / f) for f in ['interface_metrics.csv', 'comparison_arrays.npz', 'terminal_convention_differences.csv']])
    (destination / 'scoring_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(metrics[metrics.period == periods[0][0]][['convention', 'interface', 'hours', 'mae_public_MW', 'wape_percent']].to_string(index=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--representative', action='store_true')
    main(parser.parse_args().representative)
