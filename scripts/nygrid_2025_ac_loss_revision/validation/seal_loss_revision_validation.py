"""Seal qualified replay evidence, failed outcomes and frozen source closure.

No PF/OPF is run. Current qualification excludes all preliminary experiments,
and external independent reviews/final reports are excluded to prevent cycles.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_ac_loss_revision/validation'
ANNUAL = OUT / 'annual/released_equivalent_boundary_consistent'
TARGET = OUT / 'source_receipt.json'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(path):
    path = Path(path)
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path), bytes=path.stat().st_size)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def flag(value):
    return value.astype(str).str.lower().isin(['true', '1'])


def resolve(path):
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def main():
    annual = read(ANNUAL / 'annual_loss_policy_receipt.json')
    pairs = read(OUT / 'pairs/simultaneous_representatives/pair_receipt.json')
    jacobian = read(OUT / 'jacobian/jacobian_receipt.json')
    guards = read(OUT / 'policy_contract/policy_contract_receipt.json')
    factorial = read(OUT / 'representative_factorial/factorial_receipt.json')
    benchmark = read(OUT / 'benchmark/benchmark_receipt.json')
    assert annual['completed'] and annual['replay_integrity_passed'] and annual['source_files_unchanged_during_replay']
    assert annual['attempted_hours'] == annual['source_qualified_hours'] == 8651 and annual['solver_exceptions'] == 0
    assert pairs['passed'] and pairs['qualified_pair_count'] == 11 and not pairs['all_attempted_cases_converged']
    assert jacobian['passed'] and jacobian['finite_difference_cases'] == 10
    assert guards['passed'] and guards['count'] == 24
    assert factorial['completed'] and factorial['common_success_hour_count'] == 11
    assert factorial['cell_qualified_counts'] == [14, 14, 11, 11]
    assert benchmark['source_files_unchanged'] and benchmark['count'] == 100
    for item in annual['source_records']:
        assert sha(resolve(item['path'])) == item['sha256'], f"Annual source changed: {item['path']}"
    quality = pd.read_csv(ANNUAL / 'annual_hour_quality.csv')
    assert len(quality) == 8651 and quality.hour_index.is_unique
    good = flag(quality.PF_converged) & flag(quality.AC_equation_gate) & flag(quality.loss_allocation_gate) & flag(quality.reduction_and_equation_gate)
    assert good.sum() == annual['policy_equation_qualified_hours'] == 8170
    assert flag(quality.VQ_and_generator_assumption_gate).sum() == 0
    assert not flag(quality.OPF_used).any() and flag(quality.no_full_network_Newton_used).all()
    axes = loadmat(ANNUAL / 'annual_axes.mat', simplify_cells=True)
    old_axes = loadmat(ROOT / 'output/nygrid_2025_acpf_profile_audit/acpf/annual_axes.mat', simplify_cells=True)
    for key in ['hour_index', 'timestamp_utc', 'source_qualified', 'bus_id', 'base_kv', 'branch_keys', 'branch_parent_row', 'branch_from_bus', 'branch_to_bus', 'gamma', 'topology_state_index', 'model_month', 'DC_from_bus', 'DC_to_bus']:
        assert np.array_equal(axes[key], old_axes[key]), key
    corrected_path = ROOT / 'output/nygrid_2025_western_audit/replay/dated_combined.mat'
    corrected = loadmat(corrected_path, simplify_cells=True, variable_names=['corrected_generator_buses'])['corrected_generator_buses']
    assert np.array_equal(axes['generator_bus_id'], corrected)
    seen = []; all_good = np.zeros(8760, bool); monthly_records = []
    sums = dict(PF=0, equation=0, policy=0, VQ=0, source=0)
    for month in range(1, 13):
        path = ANNUAL / 'monthly' / f'profile_PF_2025_{month:02d}.mat'
        m = loadmat(path, simplify_cells=True, variable_names=['hour_index', 'timestamp_utc', 'gamma', 'source_qualified',
            'bus_id', 'branch_keys', 'generator_bus_id', 'external_generator_rows_1based', 'PF_attempted', 'solver_exception',
            'PF_converged', 'AC_equation_gate', 'loss_allocation_gate', 'reduction_and_equation_gate', 'VQ_and_generator_assumption_gate',
            'computed_current_available', 'native_PG_change_from_original_MW', 'HQ_PG_change_from_original_MW',
            'NY_gross_target_MW', 'NY_served_PD_MW', 'actual_budget_MW', 'regional_import_target_MW', 'regional_import_solved_MW',
            'external_PG_increment_MW', 'max_P_bound_violation_mw', 'max_fixed_transfer_P_change_mw'])
        hh = m['hour_index'].astype(int); seen.extend(hh.tolist()); ix = hh - 1
        assert np.array_equal(m['timestamp_utc'], axes['timestamp_utc'][ix]) and m['gamma'] == axes['gamma']
        assert np.array_equal(m['source_qualified'], axes['source_qualified'][ix])
        assert np.array_equal(m['bus_id'], axes['bus_id']) and np.array_equal(m['branch_keys'], axes['branch_keys'])
        assert np.array_equal(m['generator_bus_id'], corrected) and np.array_equal(m['external_generator_rows_1based'], axes['external_generator_rows_1based'])
        assert np.array_equal(m['PF_attempted'], m['source_qualified']) and not m['solver_exception'].any()
        valid = m['source_qualified'].astype(bool) & m['PF_converged'].astype(bool) & m['AC_equation_gate'].astype(bool) & m['loss_allocation_gate'].astype(bool) & m['reduction_and_equation_gate'].astype(bool)
        assert np.array_equal(valid, m['computed_current_available'].astype(bool)); all_good[ix] = valid
        assert np.max(abs(m['native_PG_change_from_original_MW'][valid]), initial=0) < 1e-7
        assert np.max(abs(m['HQ_PG_change_from_original_MW'][valid]), initial=0) < 1e-8
        assert np.max(abs(m['regional_import_solved_MW'][valid] - m['regional_import_target_MW'][valid]), initial=0) < 1e-5
        assert np.max(abs(m['NY_served_PD_MW'][valid] + m['actual_budget_MW'][valid, :11] - m['NY_gross_target_MW'][valid]), initial=0) < 1e-5
        assert np.max(abs(m['external_PG_increment_MW'][valid] - m['actual_budget_MW'][valid, 11:]), initial=0) < 1e-5
        assert np.all(m['NY_served_PD_MW'][valid] > 0)
        assert np.max(m['max_P_bound_violation_mw'][valid], initial=0) < 1e-5
        assert np.max(m['max_fixed_transfer_P_change_mw'][valid], initial=0) < 1e-8
        sums['source'] += int(m['source_qualified'].sum()); sums['PF'] += int(m['PF_converged'].sum())
        sums['equation'] += int(m['AC_equation_gate'].sum()); sums['policy'] += int(valid.sum()); sums['VQ'] += int(m['VQ_and_generator_assumption_gate'].sum())
        assert path.stat().st_size < 100_000_000
        monthly_records.append(record(path))
    assert seen == list(range(1, 8761)) and sums == dict(PF=8170, equation=8170, policy=8170, VQ=0, source=8651)
    assert np.array_equal(np.flatnonzero(all_good) + 1, quality.loc[good, 'hour_index'].to_numpy(int))
    old = axes['old_cohort'].astype(bool)
    assert old.sum() == 8494 and (old & all_good).sum() == 8170 and (old & ~all_good).sum() == 324 and (~old & all_good).sum() == 0
    solved = quality.loc[good]
    extrema = {}
    for name in ['max_nodal_P_residual_mw', 'max_nodal_Q_residual_mvar', 'native_PG_change_from_original_MW', 'HQ_PG_change_from_original_MW',
        'reference_PG_change_from_original_MW', 'regional_NY_import_residual_MW', 'NY_gross_load_accounting_residual_MW',
        'loss_budget_residual_MW', 'max_P_bound_violation_mw', 'max_fixed_transfer_P_change_mw', 'recovery_voltage_error_pu',
        'recovered_current_error_A', 'maximum_NY_zonal_loss_fraction', 'minimum_NY_served_PD_MW', 'min_voltage_pu', 'max_voltage_pu',
        'max_Q_bound_violation_mvar', 'max_transfer_Q_bound_violation_mvar', 'AC_real_losses_mw', 'total_NR_iterations']:
        a = solved[name].to_numpy(float); assert np.isfinite(a).all()
        extrema[name] = dict(min=float(a.min()), mean=float(a.mean()), max=float(a.max()))
    failures = quality.loc[~good, 'loss_status'].value_counts().to_dict()
    summary = dict(completed=True, all_counts_are_fresh=True, source_hours=8651, attempted_hours=8651, qualified_hours=8170,
        failed_hours=481, frozen_old_qualified_hours=8494, common_qualified_hours=8170, lost_old_qualified_hours=324, new_qualified_hours=0,
        VQ_physical_qualified_hours=0, solver_exception_hours=0, failure_status_counts={str(k): int(v) for k, v in failures.items()},
        qualified_statistics_only=True, qualified_extrema=extrema,
        qualified_hours_NY_zonal_loss_fraction_above25pct=int((solved.maximum_NY_zonal_loss_fraction > .25).sum()),
        qualified_hours_NY_zonal_loss_fraction_above50pct=int((solved.maximum_NY_zonal_loss_fraction > .5).sum()),
        qualified_hours_NY_zonal_loss_fraction_above90pct=int((solved.maximum_NY_zonal_loss_fraction > .9).sum()),
        annual_elapsed_seconds=annual['elapsed_seconds'], paired_valid_points=11, paired_failed_both_hours=pairs['both_failed_hours'],
        standard_full_PF_replays_passed=sum(r['standard_full_PF_replay_passed'] for r in pairs['checks']),
        representative_factorial_cell_success_counts=factorial['cell_qualified_counts'], representative_factorial_common_hours=factorial['common_success_hours'],
        representative_factorial_is_not_annual_attribution=True, global_infeasibility_not_claimed=True,
        allocation_and_equation_qualification_does_not_certify_VQ_thermal_security_or_real_meter_equivalence=True)
    (OUT / 'qualified_solution_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    logs = OUT / 'logs'; logs.mkdir(exist_ok=True)
    for name in ['ac_loss_revision_coupled_jacobian.log', 'ac_loss_revision_simultaneous_pairs.log', 'ac_loss_revision_primary_annual.log',
                 'ac_loss_revision_final_factorial_and_contract.log', 'ac_loss_revision_warm100_final_frozen.log']:
        shutil.copyfile(ROOT / 'tmp' / name, logs / name)
    # Read every JSON path/SHA reference as a live binding. Historical receipt
    # bytes use explicit .json.txt snapshots, with their own honest receipt.
    checked = 0; cache = {}
    def visit(value):
        nonlocal checked
        if isinstance(value, dict):
            if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
                path = resolve(value['path']); key = str(path)
                if key not in cache: cache[key] = sha(path)
                assert cache[key] == value['sha256'], f"Stale validation reference: {value['path']}"
                checked += 1
            for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    for path in OUT.rglob('*.json'):
        if path != TARGET: visit(read(path))
    baseline = ROOT / 'output/nygrid_2025_compact_ac/validation/source_receipt.json'
    oldseal = read(baseline); protected = sum([oldseal.get(k, []) for k in ['source_data', 'source_code', 'evidence', 'independent_reviews']], [])
    for item in protected: assert sha(resolve(item['path'])) == item['sha256'], item['path']
    code = sorted(p for p in (ROOT / 'scripts/nygrid_2025_ac_loss_revision/validation').iterdir() if p.suffix in {'.m', '.py'})
    evidence = sorted(p for p in OUT.rglob('*') if p.is_file() and p != TARGET and p.suffix in {'.json', '.mat', '.csv', '.log', '.m', '.txt'})
    receipt = dict(passed=True, created_utc=datetime.now(timezone.utc).isoformat(), current_kernel_and_source_bundle=annual['source_records'],
        annual_source_bundle_unchanged_before_after_and_now=True, all_validation_JSON_live_path_SHA_records_verified=checked,
        old_compact_full_AC_sealed_records_byte_preserved=len(protected), preserved_baseline_receipt=record(baseline),
        source_hours=8651, current_qualified_hours=8170, failed_hours=481, old_qualified_hours_lost=324, new_qualified_hours=0,
        full_physical_VQ_qualified_hours=0, all8760clockpositions_exported=True, original267bus488branch_axes_preserved=True,
        current_policy_contract_tests_passed=24, current_Jacobian_cases_passed=10, current_paired_qualified_cases=11,
        current_paired_failed_both_hours=pairs['both_failed_hours'], standard_full_PF_replays_passed=11,
        preliminary_prototypes_explicitly_historical_not_current_qualification=True,
        benchmark_previous_receipt_and_exact_previous_guard_source_preserved=True,
        no_OPF_or_internal_interface_parameter_fit=True, no_global_infeasibility_claim=True,
        independent_comparison_impedance_reviews_and_root_reports_excluded_to_avoid_cycles=True,
        validation_source_code=[record(p) for p in code], evidence=[record(p) for p in evidence], monthly_files=monthly_records)
    TARGET.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(passed=True, source_receipt_sha256=sha(TARGET), validation_JSON_live_records=checked,
        preserved_baseline_records=len(protected), qualified=8170, failed=481, lost_old=324, new=0, failure_status_counts=failures,
        maximum_native_PG_delta_MW=extrema['native_PG_change_from_original_MW']['max'],
        maximum_regional_import_residual_MW=extrema['regional_NY_import_residual_MW']['max'],
        maximum_NY_loss_fraction=extrema['maximum_NY_zonal_loss_fraction']['max'])))


if __name__ == '__main__': main()
