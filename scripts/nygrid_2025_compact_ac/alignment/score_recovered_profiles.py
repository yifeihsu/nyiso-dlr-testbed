"""Score recovered full-terminal compact AC outputs against frozen evidence.

The compact kernel must export the full canonical physical branch axes.
Reduced-network branch powers are never interpreted as NYISO interfaces.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import sys
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_compact_ac/alignment'
FROZEN = ROOT / 'output/nygrid_2025_acpf_profile_audit'
sys.path.insert(0, str(ROOT / 'scripts/nygrid_2025_acpf_profile_audit/alignment'))
from interface_operator import build_runtime_operator, apply_interface_flows, CONVENTIONS

AXES = ['branch_keys','branch_parent_row','branch_from_bus','branch_to_bus','bus_id','base_kv']
BRANCH_FIELDS = ['PF','QF','PT','QT','Iseries','Ifrom','Ito']
BUS_FIELDS = ['VM','VA','PD','QD','bus_PG','bus_QG']
FLAGS = ['source_qualified','AC_equation_gate','P_profile_preservation_gate','VQ_and_generator_assumption_gate']
READ_FIELDS = ['hour_index','timestamp_utc','gamma','branch_present','branch_active','bus_present'] + AXES + BRANCH_FIELDS + BUS_FIELDS + FLAGS
COMPACT_EXTRA_FIELDS = ['reduction_and_equation_gate','native_retained_bus_count','paired_detailed_solution_equivalent']


def record(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=h.hexdigest())


def enforce_receipts(receipts):
    for entry in receipts:
        assert record(ROOT / entry['path'])['sha256'] == entry['sha256'], f"Changed frozen source: {entry['path']}"


def flag(m, name):
    return np.asarray(m[name], bool).reshape(-1)


def interface_values(m, states, use, gamma):
    branch = np.column_stack((m['branch_from_bus'], m['branch_to_bus']))
    parent = np.asarray(m['branch_parent_row'], int).reshape(-1)
    n = len(states)
    arrays = {c: np.full((n, 7), np.nan) for c in (*CONVENTIONS, 'oriented_source_minus_target_loss')}
    names = None
    for state in np.unique(states):
        rows = np.flatnonzero((states == state) & use)
        if not len(rows): continue
        operator = build_runtime_operator(branch, parent, str(state))
        if names is None: names = operator['interface_names']
        assert names == operator['interface_names']
        for term in operator['terms']:
            chain = np.flatnonzero(parent == term['original_branch_row'])
            assert np.asarray(m['branch_active'], bool)[np.ix_(rows, chain)].all()
            assert np.asarray(m['branch_present'], bool)[np.ix_(rows, chain)].all()
        values = apply_interface_flows(np.asarray(m['PF'])[rows], np.asarray(m['PT'])[rows], operator, gamma)
        for key, value in values.items(): arrays[key][rows] = value
    return names, arrays


def accumulate_error(stats, field, error, valid, hours, keys, units):
    selected = np.asarray(error)[valid]
    assert np.isfinite(selected).all(), f'Nonfinite paired {field}'
    if not len(selected): return
    absolute = np.abs(selected)
    entry = stats.setdefault(field, dict(field=field, units=units, entries=0, absolute_error_sum=0., squared_error_sum=0., maximum_absolute_error=-1.))
    entry['entries'] += len(selected)
    entry['absolute_error_sum'] += float(absolute.sum())
    entry['squared_error_sum'] += float(np.square(absolute).sum())
    if absolute.max() > entry['maximum_absolute_error']:
        position = np.argwhere(valid)[int(absolute.argmax())]
        entry['maximum_absolute_error'] = float(absolute.max())
        entry['maximum_error_hour_index'] = int(hours[position[0]])
        entry['maximum_error_component'] = str(keys[position[1]])


def main(compact_monthly, annual_receipt):
    contract_path = OUT / 'comparison_contract.json'
    contract = json.loads(contract_path.read_text())
    enforce_receipts(contract['source_receipts'])
    cohort_path = OUT / 'frozen_comparison_cohort.csv'
    cohort = pd.read_csv(cohort_path)
    hours = cohort.hour_index.to_numpy(int)
    times = cohort.timestamp_utc.to_numpy(str)
    states = cohort.dated_state.to_numpy(str)
    source = cohort.frozen_source_qualified.to_numpy(bool)
    frozen_good = cohort.frozen_detailed_equation_and_profile_qualified.to_numpy(bool)
    gamma = float(contract['gamma']); names = contract['interface_names']
    observed_path = ROOT / contract['public_observation_path']
    obs = pd.read_csv(observed_path, float_precision='round_trip')
    assert np.array_equal(obs.hour_index, hours) and np.array_equal(obs.timestamp_utc, times)
    y = obs[names].to_numpy(float)
    with np.load(FROZEN / 'comparison/comparison_arrays.npz', allow_pickle=False) as old:
        assert np.array_equal(y, old['observed'], equal_nan=True)
        reference = {c: old[c].copy() for c in (*CONVENTIONS, 'oriented_source_minus_target_loss')}
    files = sorted(compact_monthly.glob('*.mat'))
    assert len(files) == 12, f'Expected twelve completed compact monthly MAT files, found {len(files)}'
    completed = json.loads(annual_receipt.read_text())
    assert completed.get('completed') is True or completed.get('passed') is True, 'Compact annual validation is not complete'
    result = {c: np.full((8760, 7), np.nan) for c in (*CONVENTIONS, 'oriented_source_minus_target_loss')}
    seen = np.zeros(8760, bool); compact_good = seen.copy(); compact_operating = seen.copy()
    canonical = None; statistics = {}; comparison_rows = []
    source_load_errors = {'PD': 0., 'QD': 0.}
    local = pd.to_datetime(times, utc=True).tz_convert('America/New_York')
    used_detailed = []
    for compact_path in files:
        m = loadmat(compact_path, simplify_cells=True, variable_names=READ_FIELDS + COMPACT_EXTRA_FIELDS)
        missing = set(READ_FIELDS + COMPACT_EXTRA_FIELDS) - set(m)
        assert not missing, f'{compact_path.name} missing fields: {sorted(missing)}'
        h = np.asarray(m['hour_index'], int).reshape(-1); ix = h - 1
        assert np.all((ix >= 0) & (ix < 8760)) and len(np.unique(ix)) == len(ix) and not seen[ix].any()
        assert np.array_equal(np.asarray(m['timestamp_utc']).astype(str).reshape(-1), times[ix])
        assert np.array_equal(flag(m,'source_qualified'), source[ix]) and float(m['gamma']) == gamma
        months = np.unique(local.month[ix]); assert len(months) == 1
        detailed_path = FROZEN / f'acpf/monthly/profile_PF_2025_{months[0]:02d}.mat'
        d = loadmat(detailed_path, simplify_cells=True, variable_names=READ_FIELDS)
        used_detailed.append(detailed_path)
        assert np.array_equal(np.asarray(d['hour_index']).reshape(-1), h)
        assert np.array_equal(np.asarray(d['timestamp_utc']).astype(str).reshape(-1), times[ix])
        assert np.array_equal(flag(d,'source_qualified'), source[ix]) and float(d['gamma']) == gamma
        if canonical is None: canonical = {k: np.asarray(m[k]).reshape(-1).copy() for k in AXES}
        for axis in AXES:
            assert np.array_equal(np.asarray(m[axis]).reshape(-1), canonical[axis]), f'Compact axis drift: {axis}'
            assert np.array_equal(np.asarray(d[axis]).reshape(-1), canonical[axis]), f'Compact/detailed axis mismatch: {axis}'
        assert len(set(canonical['branch_keys'])) == 488 and len(set(canonical['bus_id'])) == 267
        good = source[ix] & flag(m,'AC_equation_gate') & flag(m,'P_profile_preservation_gate') & flag(m,'reduction_and_equation_gate')
        assert np.all(np.asarray(m['native_retained_bus_count']).reshape(-1)[good] == 148)
        detailed_good = source[ix] & flag(d,'AC_equation_gate') & flag(d,'P_profile_preservation_gate')
        assert np.array_equal(detailed_good, frozen_good[ix])
        # The frozen exports retain input demand even on their failed PF hours.
        # Check demand on every compact success, including newly solved hours.
        source_bus_mask = good[:, None] & np.asarray(m['bus_present'], bool)
        assert np.array_equal(np.asarray(m['bus_present'], bool)[good], np.asarray(d['bus_present'], bool)[good])
        for field in source_load_errors:
            error = np.abs(np.asarray(m[field]) - np.asarray(d[field]))[source_bus_mask]
            assert np.isfinite(error).all()
            source_load_errors[field] = max(source_load_errors[field], float(error.max(initial=0)))
            assert source_load_errors[field] < 1e-10, f'Compact recovered demand differs from frozen profile: {field}'
        paired = good & detailed_good
        assert flag(m,'paired_detailed_solution_equivalent')[paired].all(), 'Producer rejected paired reduction equivalence'
        n, values = interface_values(m, states[ix], good, gamma)
        assert n is None or n == names
        for convention, value in values.items(): result[convention][ix] = value
        # Recompute frozen detailed interfaces through the same sealed original
        # terminals, guarding against comparing to stale or differently ordered scores.
        dn, detailed_values = interface_values(d, states[ix], detailed_good, gamma)
        assert dn is None or dn == names
        for convention in CONVENTIONS:
            assert np.allclose(detailed_values[convention][detailed_good], reference[convention][ix[detailed_good]], rtol=0, atol=1e-8)
        if paired.any():
            bp = np.asarray(m['branch_present'], bool)
            dp = np.asarray(d['branch_present'], bool)
            assert np.array_equal(bp[paired], dp[paired])
            assert np.array_equal(np.asarray(m['branch_active'])[paired], np.asarray(d['branch_active'])[paired])
            busp = np.asarray(m['bus_present'], bool)
            assert np.array_equal(busp[paired], np.asarray(d['bus_present'], bool)[paired])
            branch_mask = paired[:, None] & bp
            bus_mask = paired[:, None] & busp
            for field in BRANCH_FIELDS:
                unit = 'A' if field.startswith('I') else ('model_MVAr' if field.startswith('Q') else 'model_MW')
                accumulate_error(statistics, field, np.asarray(m[field]) - np.asarray(d[field]), branch_mask, h, canonical['branch_keys'], unit)
            for field in ['VM','PD','QD','bus_PG','bus_QG']:
                unit = 'pu' if field == 'VM' else ('model_MVAr' if 'Q' in field else 'model_MW')
                accumulate_error(statistics, field, np.asarray(m[field]) - np.asarray(d[field]), bus_mask, h, canonical['bus_id'], unit)
            # Use the first original bus as a phase gauge; electrical equality
            # should not fail because two solvers use a different angle origin.
            angle_delta = np.asarray(m['VA']) - np.asarray(d['VA'])
            assert busp[paired, 0].all()
            angle_delta = np.rad2deg(np.angle(np.exp(1j * np.deg2rad(angle_delta - angle_delta[:, :1]))))
            accumulate_error(statistics, 'VA_phase_gauge_aligned', angle_delta, bus_mask, h, canonical['bus_id'], 'degree')
            for convention in CONVENTIONS:
                error = (values[convention] - detailed_values[convention]) * gamma
                accumulate_error(statistics, f'interface_{convention}', error, np.broadcast_to(paired[:, None], error.shape), h, names, 'model_MW')
        seen[ix] = True; compact_good[ix] = good
        compact_operating[ix] = flag(m,'VQ_and_generator_assumption_gate') & good
    assert seen.all(), 'Compact monthly files omit annual hour positions'
    paired = frozen_good & compact_good; new = compact_good & ~frozen_good
    lost = frozen_good & ~compact_good
    assert paired.any() and np.isfinite(y[compact_good]).all()
    masks = [('paired_frozen_detailed',paired), ('compact_all_equation_qualified',compact_good), ('compact_only_successes',new)]
    for cohort_name, base_mask in masks:
        if not base_mask.any(): continue
        periods = [('annual',base_mask)] + [(f'month_{month:02d}', base_mask & (local.month == month)) for month in range(1,13)]
        periods += [('post_Dover',base_mask & (states == 'post_dover'))]
        for period, mask in periods:
            if not mask.any(): continue
            for convention in CONVENTIONS:
                predictions = [('compact_recovered',result[convention])]
                if cohort_name == 'paired_frozen_detailed': predictions.insert(0, ('frozen_detailed',reference[convention]))
                for model, prediction in predictions:
                    assert np.isfinite(prediction[mask]).all()
                    for j, name in enumerate(names):
                        error = prediction[mask,j] - y[mask,j]
                        comparison_rows.append(dict(cohort=cohort_name,period=period,model=model,convention=convention,interface=name,
                            hours=int(mask.sum()),mae_public_MW=float(np.abs(error).mean()),rmse_public_MW=float(np.sqrt(np.square(error).mean())),
                            bias_public_MW=float(error.mean()),
                            wape_percent=float(100 * np.abs(error).sum() / np.abs(y[mask,j]).sum()) if np.abs(y[mask,j]).sum() > 0 else np.nan,
                            diagnostic_only=True,physical_P32_meter_certified=False))
    numeric = []
    for entry in statistics.values():
        entry['mean_absolute_error'] = entry.pop('absolute_error_sum') / entry['entries']
        entry['root_mean_square_error'] = (entry.pop('squared_error_sum') / entry['entries']) ** .5
        numeric.append(entry)
    pd.DataFrame(numeric).to_csv(OUT / 'paired_recovery_errors.csv', index=False, lineterminator='\n')
    pd.DataFrame(comparison_rows).to_csv(OUT / 'public_interface_metrics.csv', index=False, lineterminator='\n')
    export = cohort.copy()
    export['compact_equation_and_profile_qualified'] = compact_good
    export['paired_frozen_detailed_qualified'] = paired
    export['compact_only_success'] = new
    export['frozen_detailed_success_lost'] = lost
    export['compact_VQ_generator_qualified'] = compact_operating
    export.to_csv(OUT / 'comparison_cohort.csv', index=False, lineterminator='\n')
    np.savez_compressed(OUT / 'comparison_arrays.npz', hour_index=hours,timestamp_utc=times,interface_names=np.array(names),gamma=gamma,
        source_qualified=source,frozen_detailed_qualified=frozen_good,compact_qualified=compact_good,paired_qualified=paired,
        compact_only_success=new,observed=y,**{f'compact_{c}':a for c,a in result.items()},**{f'detailed_{c}':a for c,a in reference.items()})
    enforce_receipts(contract['source_receipts'])
    outputs = [OUT / p for p in ['paired_recovery_errors.csv','public_interface_metrics.csv','comparison_cohort.csv','comparison_arrays.npz']]
    receipt = dict(passed=True, comparison_complete=True, created_utc=datetime.now(timezone.utc).isoformat(),
        audit_scope='Recovered full-terminal numerical comparison and exact paired public observation scoring; not a physical-meter or operating-feasibility certification.',
        source_qualified_hours=int(source.sum()), frozen_detailed_qualified_hours=int(frozen_good.sum()),
        compact_equation_and_profile_qualified_hours=int(compact_good.sum()), paired_qualified_hours=int(paired.sum()),
        compact_only_success_hours=int(new.sum()), frozen_detailed_success_lost_hours=int(lost.sum()),
        compact_VQ_generator_qualified_hours=int(compact_operating.sum()),
        compact_reduction_and_equation_gate_required_for_comparison=True,
        actual_export_API_confirmed=True,
        actual_export_fields_verified=READ_FIELDS + COMPACT_EXTRA_FIELDS,
        maximum_recovered_PD_vs_frozen_source_error_model_MW=source_load_errors['PD'],
        maximum_recovered_QD_vs_frozen_source_error_model_MVAr=source_load_errors['QD'],
        numerical_equivalence_acceptance_receipt=annual_receipt.relative_to(ROOT).as_posix(),
        numerical_equivalence_acceptance_redefined_by_this_scorer=False,
        current_gamma_division_applied=False, reduced_edge_interface_flows_used=False,
        original_terminal_operator_reused_without_fitting=True,
        public_observations_profiles_operators_and_previous_detailed_results_changed=False,
        comparison_tolerances_not_fit_to_public_errors=True, gamma=gamma, conventions=list(CONVENTIONS),
        numerical_equivalence_errors_reported_without_hiding_coverage_losses=True,
        physical_P32_meter_membership_certified=False, inherited_operating_failures_claimed_fixed=False,
        angle_error_gauge_reference_bus=int(canonical['bus_id'][0]),
        dependencies=[record(p) for p in [Path(__file__),contract_path,cohort_path,annual_receipt,observed_path] + files + used_detailed],
        outputs=[record(p) for p in outputs])
    (OUT / 'scoring_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:receipt[k] for k in ['passed','source_qualified_hours','frozen_detailed_qualified_hours',
        'compact_equation_and_profile_qualified_hours','paired_qualified_hours','compact_only_success_hours','frozen_detailed_success_lost_hours']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--compact-monthly', type=Path, required=True)
    parser.add_argument('--annual-receipt', type=Path, required=True)
    args = parser.parse_args()
    main(args.compact_monthly.resolve(), args.annual_receipt.resolve())
