"""Independent saved-array electrical and requested-repair annual readback.

Rebuilds branch laws and the passive-node voltage lift from numeric repaired
templates. No power-flow solve, model mutation, or authoring-helper import.
Use --months 1 for a separate partial receipt; omit for the completed year.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / 'output/nygrid_2025_moses_repair/annual/moses_repair_v1'
OUT = RUN / 'validation'
OLD = ROOT / 'output/nygrid_2025_physical_repair/annual/physical_repair_v1/monthly'


def record(path):
    with path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': digest}


def largest(value):
    return float(np.max(np.abs(value))) if np.size(value) else 0.


def build_lift(template, shift):
    """Explicit complex admittance stamping, including tap phase and bus BS."""
    bus, br = template['bus'], template['branch']; ids = bus[:, 0].astype(int)
    lookup = {x: i for i, x in enumerate(ids)}; n = len(ids)
    f = np.array([lookup[int(x)] for x in br[:, 0]]); t = np.array([lookup[int(x)] for x in br[:, 1]])
    on = br[:, 10] > 0; y = np.where(on, 1 / (br[:, 2] + 1j * br[:, 3]), 0)
    b = 1j * br[:, 4] * on / 2; tap = np.where(br[:, 8] == 0, 1, br[:, 8]) * np.exp(1j * np.deg2rad(shift))
    Y = np.diag((bus[:, 4] + 1j * bus[:, 5]) / float(template['baseMVA'])).astype(complex)
    np.add.at(Y, (f, f), (y + b) / np.abs(tap) ** 2); np.add.at(Y, (t, t), y + b)
    np.add.at(Y, (f, t), -y / np.conj(tap)); np.add.at(Y, (t, f), -y / tap)
    k = np.array([lookup[int(x)] for x in template['retained_bus_ids']])
    e = np.setdiff1d(np.arange(n), k)
    assert len(k) == 148 and np.all(bus[e, 2:5] == 0)
    L = np.zeros((n, len(k)), complex); L[k, np.arange(len(k))] = 1
    L[e] = -np.linalg.solve(Y[np.ix_(e, e)], Y[np.ix_(e, k)])
    residual = largest(Y[e] @ L)
    assert residual < 1e-8
    return L, residual


def main(months):
    OUT.mkdir(parents=True, exist_ok=True)
    complete = months == list(range(1, 13)); prefix = '' if complete else 'partial_' + '_'.join(f'{m:02d}' for m in months) + '_'
    if complete:
        annual = json.loads((RUN / 'annual_receipt.json').read_text()); assert annual['completed']
    axes_path = RUN / 'annual_axes.mat'; network_path = RUN / 'annual_network.mat'
    axes = loadmat(axes_path, simplify_cells=True); templates = loadmat(network_path, simplify_cells=True)['templates']
    names = np.asarray(axes['branch_keys']).astype(str); ids = np.asarray(axes['bus_id'], int)
    bus_lookup = {x: i for i, x in enumerate(ids)}; branch_lookup = {x: i for i, x in enumerate(names)}
    parents = np.asarray(axes['branch_parent_row'], int); gamma = float(axes['gamma'])
    baseline_path = ROOT / 'output/nygrid_2025_physical_repair/annual/physical_repair_v1/comparison/comparison_arrays.npz'
    reference = np.load(baseline_path); old_qualified = reference['candidate_qualified'].astype(bool)
    assert old_qualified.sum() == 8651 and np.array_equal(old_qualified, axes['current_baseline_qualified'].astype(bool))
    operator_path = ROOT / 'output/nygrid_2025_acpf_profile_audit/alignment/interface_operator_terms.csv'
    operators = pd.read_csv(operator_path); interface_names = operators.drop_duplicates('interface_index').sort_values('interface_index').interface.tolist()
    selected_parameter_path = ROOT / 'output/nygrid_2025_physical_repair/physics/parent41_parameters.json'
    parameter = json.loads(selected_parameter_path.read_text()); source_files = [axes_path, network_path, baseline_path, operator_path, selected_parameter_path, Path(__file__)]
    state_maps = {}; invariant_rows = []
    for state, template in enumerate(templates, 1):
        b = template['bus']; br = template['branch']; oldb = template['old_bus']; oldbr = template['old_branch']
        ib = np.array([bus_lookup[int(x)] for x in b[:, 0]]); il = np.array([branch_lookup[str(x)] for x in template['branch_keys']])
        row41 = np.flatnonzero(template['branch_parent_row'] == 41); assert len(row41) == 1
        assert np.allclose(br[row41[0], 2:5], parameter['repaired_R_X_B'], atol=1e-12, rtol=0)
        branch_columns = [*range(9), 10, 11, 12]
        assert np.array_equal(br[:, branch_columns], oldbr[:, branch_columns])
        assert np.array_equal(b[:, [0, 4, 5, 6, 7, 8, 9, 10, 11, 12]], oldb[:, [0, 4, 5, 6, 7, 8, 9, 10, 11, 12]])
        local_lookup = {int(x): i for i, x in enumerate(b[:, 0])}
        totals = {}
        for parent in [185, 195]:
            rr = np.flatnonzero(template['branch_parent_row'] == parent); target = br[rr]
            from_original = int(target[0, 0]); to_original = int(target[-1, 1])
            # Connectivity determines terminals independently of row ordering.
            starts = target[:, 0].astype(int); ends = target[:, 1].astype(int)
            from_original = int(np.setdiff1d(starts, ends)[0]); to_original = int(np.setdiff1d(ends, starts)[0])
            q = .75 * template['baseMVA'] * target[:, 4].sum()
            expected_parent = np.zeros(len(b))
            for r in target:
                for x in r[:2].astype(int): expected_parent[local_lookup[x]] -= .75 * template['baseMVA'] * r[4] / 2
            reactor = next(x for x in template['reactor_ledger'] if x['original_branch_row'] == parent)
            recorded = np.zeros(len(b))
            for node, value in zip(reactor['distributed_bus_ids'], reactor['distributed_bus_BS_delta_mvar']):
                recorded[local_lookup[int(node)]] = value
            assert largest(recorded - expected_parent) < 1e-10
            assert abs(reactor['applied_total_reactor_mvar_at1pu'] - q) < 1e-8
            totals[str(parent)] = float(q)
        assert largest(b[:, 5] - oldb[:, 5]) < 1e-10
        f = np.array([bus_lookup[int(x)] for x in br[:, 0]]); t = np.array([bus_lookup[int(x)] for x in br[:, 1]])
        state_maps[state] = {'ib': ib, 'il': il, 'f': f, 't': t}
        invariant_rows.append({'state_index': state, 'parent41_RXB': br[row41[0], 2:5].tolist(),
            'nominal_reactor_MVAr': totals, 'BS_change_from_repaired_baseline_MVAr': largest(b[:, 5] - oldb[:, 5]),
            'voltage_bounds_and_initial_PV_setpoints_unchanged': True, 'all_other_branch_fields_unchanged': True})
    max_errors = {name: 0. for name in ['branch_complex_power_MVA', 'series_current_A', 'from_current_A', 'to_current_A',
        'series_loss_identity_MW', 'parent41_material_loss_identity_MW', 'nodal_P_MW', 'nodal_Q_MVAr', 'full_voltage_lift_pu', 'retained_voltage_pu', 'passive_YL_pu']}
    new_good = np.zeros(8760, bool); seen = np.zeros(8760, bool); source_mask = np.zeros(8760, bool)
    prediction = np.full((8760, 7), np.nan); hourly = []; old_hourly = []; voltage_rows = []
    bus_over = np.zeros(len(ids), int); bus_under = np.zeros(len(ids), int); bus_count = np.zeros(len(ids), int)
    bus_min = np.full(len(ids), np.inf); bus_max = np.full(len(ids), -np.inf)
    for month in months:
        path = RUN / f'monthly/profile_PF_2025_{month:02d}.mat'; checkpoint = path.with_name(f'profile_PF_2025_{month:02d}_receipt.json')
        cp = json.loads(checkpoint.read_text()); assert cp['completed']
        assert any(Path(r['path']).name == path.name and r['sha256'] == record(path)['sha256'] for r in cp['outputs'])
        source_files.extend([path, checkpoint])
        d = loadmat(path, simplify_cells=True); h = np.asarray(d['hour_index'], int) - 1; q = np.asarray(d['qualified'], bool)
        assert not seen[h].any(); seen[h] = True; new_good[h] = q; source_mask[h] = np.asarray(d['source_qualified'], bool)
        assert np.array_equal(d['bus_id'], ids) and np.array_equal(d['branch_keys'].astype(str), names)
        assert np.array_equal(q, np.asarray(d['PF_converged'], bool) & np.asarray(d['AC_equation_gate'], bool) & np.asarray(d['loss_allocation_gate'], bool) & np.asarray(d['reduction_and_equation_gate'], bool))
        assert np.all(np.asarray(d['source_qualified'], bool)[q])
        V = d['VM'] * np.exp(1j * np.deg2rad(d['VA']))
        for state in sorted(set(np.asarray(d['topology_state_index'], int)[q])):
            use = np.flatnonzero(q & (d['topology_state_index'] == state)); template = templates[state - 1]; mapping = state_maps[state]
            ib, il, f, t = (mapping[x] for x in ['ib', 'il', 'f', 't']); b = template['bus']; br = template['branch']; base = float(template['baseMVA'])
            v = V[use]; on = br[:, 10] > 0
            assert np.all(d['bus_present'][np.ix_(use, ib)]) and np.all(d['branch_present'][np.ix_(use, il)])
            assert np.array_equal(d['branch_active'][np.ix_(use, il)].astype(bool), np.broadcast_to(on, (len(use), len(on))))
            shift = d['branch_SHIFT'][np.ix_(use, il)]; tap = np.where(br[:, 8] == 0, 1, br[:, 8])[None, :] * np.exp(1j * np.deg2rad(shift))
            y = np.where(on, 1 / (br[:, 2] + 1j * br[:, 3]), 0); bc = 1j * br[:, 4] * on / 2
            series = (v[:, f] / tap - v[:, t]) * y
            current_from = series / np.conj(tap) + bc * v[:, f] / np.abs(tap) ** 2
            current_to = -series + bc * v[:, t]
            sf = base * v[:, f] * np.conj(current_from); st = base * v[:, t] * np.conj(current_to)
            af = abs(current_from) * base * 1000 / (np.sqrt(3) * axes['base_kv'][f])
            at = abs(current_to) * base * 1000 / (np.sqrt(3) * axes['base_kv'][t])
            # The series element is on the MATPOWER to-side voltage base.
            ass = abs(series) * base * 1000 / (np.sqrt(3) * axes['base_kv'][t])
            max_errors['branch_complex_power_MVA'] = max(max_errors['branch_complex_power_MVA'], largest(sf - (d['PF'][np.ix_(use, il)] + 1j * d['QF'][np.ix_(use, il)])), largest(st - (d['PT'][np.ix_(use, il)] + 1j * d['QT'][np.ix_(use, il)])))
            for name, actual, saved in [('series_current_A', ass, 'Iseries'), ('from_current_A', af, 'Ifrom'), ('to_current_A', at, 'Ito')]:
                max_errors[name] = max(max_errors[name], largest(actual - d[saved][np.ix_(use, il)]))
            loss = (sf + st).real
            max_errors['series_loss_identity_MW'] = max(max_errors['series_loss_identity_MW'], largest(loss - base * br[:, 2] * abs(series) ** 2))
            rp41 = np.flatnonzero(template['branch_parent_row'] == 41)[0]; segment = parameter['thermal_segment']
            material = 3 * segment['circuits'] * segment['bundle_count'] * (ass[:, rp41] / (segment['circuits'] * segment['bundle_count'])) ** 2 * segment['r_ref_ohm_per_m_per_subconductor'] * segment['segment_length_m'] / 1e6
            max_errors['parent41_material_loss_identity_MW'] = max(max_errors['parent41_material_loss_identity_MW'], largest(loss[:, rp41] - material))
            injections = d['bus_PG'][use] + 1j * d['bus_QG'][use] - d['PD'][use] - 1j * d['QD'][use]
            injections[:, ib] -= abs(v[:, ib]) ** 2 * (b[:, 4] - 1j * b[:, 5])
            for j, dc in enumerate(template['dcline']):
                if dc[2] > 0:
                    injections[:, bus_lookup[int(dc[0])]] += -d['DC_PF'][use, j] + 1j * d['DC_QF'][use, j]
                    injections[:, bus_lookup[int(dc[1])]] += d['DC_PT'][use, j] + 1j * d['DC_QT'][use, j]
            for j in range(len(br)): injections[:, f[j]] -= sf[:, j]; injections[:, t[j]] -= st[:, j]
            max_errors['nodal_P_MW'] = max(max_errors['nodal_P_MW'], largest(injections[:, ib].real))
            max_errors['nodal_Q_MVAr'] = max(max_errors['nodal_Q_MVAr'], largest(injections[:, ib].imag))
            vk = d['retained_VM'][use] * np.exp(1j * np.deg2rad(d['retained_VA'][use]))
            retained = np.array([bus_lookup[int(x)] for x in template['retained_bus_ids']])
            max_errors['retained_voltage_pu'] = max(max_errors['retained_voltage_pu'], largest(v[:, retained] - vk))
            patterns, inverse = np.unique(shift, axis=0, return_inverse=True)
            for j, pattern in enumerate(patterns):
                rows = np.flatnonzero(inverse == j); L, error = build_lift(template, pattern)
                max_errors['passive_YL_pu'] = max(max_errors['passive_YL_pu'], error)
                max_errors['full_voltage_lift_pu'] = max(max_errors['full_voltage_lift_pu'], largest(v[rows][:, ib] - vk[rows] @ L.T))
            vm = d['VM'][np.ix_(use, ib)]; over = vm > b[:, 11] + 1e-7; under = vm < b[:, 12] - 1e-7
            bus_over[ib] += over.sum(axis=0); bus_under[ib] += under.sum(axis=0); bus_count[ib] += len(use)
            bus_min[ib] = np.minimum(bus_min[ib], vm.min(axis=0)); bus_max[ib] = np.maximum(bus_max[ib], vm.max(axis=0))
            state_name = ['pre_may', 'may21', 'may30', 'post_dover'][state - 1]; op = operators[operators.state == state_name]
            for k in range(7):
                terms = op[op.interface_index == k + 1]
                cols = np.array([branch_lookup[x] for x in terms.first_runtime_branch_key])
                prediction[h[use], k] = d['PF'][np.ix_(use, cols)] @ terms.coefficient.to_numpy() / gamma
            target_stats = {}
            for parent in [185, 195]:
                target_br = br[template['branch_parent_row'] == parent]; target_ids = np.unique(target_br[:, :2]).astype(int)
                target_rows = np.array([bus_lookup[x] for x in target_ids]); target_vm = d['VM'][np.ix_(use, target_rows)]
                target_stats[parent] = (target_vm.min(axis=1), target_vm.max(axis=1), ((target_vm < .95 - 1e-7) | (target_vm > 1.05 + 1e-7)).any(axis=1))
            q_violation = np.maximum(np.maximum(d['gen_Qmin'][use] - d['gen_QG'][use], d['gen_QG'][use] - d['gen_Qmax'][use]), 0).max(axis=1)
            s_violation = np.maximum(abs(d['gen_PG'][use] + 1j * d['gen_QG'][use]) - d['gen_S_cap'][use], 0).max(axis=1)
            rated = (br[:, 5] > 0) & on
            mva_violation = np.maximum(np.maximum(abs(sf[:, rated]), abs(st[:, rated])) - br[rated, 5], 0).max(axis=1)
            for k, row in enumerate(use):
                hourly.append({'hour_index': int(h[row] + 1), 'month': month, 'state_index': state,
                    'old_baseline_qualified': bool(old_qualified[h[row]]), 'parent41_loss_model_MW': float(loss[k, rp41]),
                    'parent41_max_terminal_current_A': float(max(af[k, rp41], at[k, rp41])),
                    'parent41_hardware_current_limit_exceeded': bool(max(af[k, rp41], at[k, rp41]) > 2000 * (1 + 1e-6)),
                    'NY_assigned_loss_model_MW': float(np.sum(d['actual_budget_MW'][row, :11])),
                    'all_network_branch_loss_model_MW': float(loss[k].sum()),
                    'global_min_VM': float(vm[k].min()), 'global_max_VM': float(vm[k].max()),
                    'global_overvoltage': bool(over[k].any()), 'global_undervoltage': bool(under[k].any()),
                    'global_Q_violation_model_MVAr': float(q_violation[k]), 'global_S_violation_model_MVA': float(s_violation[k]),
                    'global_branch_MVA_violation': float(mva_violation[k]), 'full_operating_qualified': bool(d['full_operating_gate'][row]),
                    **{f'parent{p}_{suffix}': (bool(target_stats[p][j][k]) if suffix == 'voltage_violation' else float(target_stats[p][j][k])) for p in [185, 195] for j, suffix in enumerate(['min_VM', 'max_VM', 'voltage_violation'])}})
        oldpath = OLD / path.name; source_files.append(oldpath)
        od = loadmat(oldpath, simplify_cells=True, variable_names=['hour_index', 'PF', 'PT', 'VM', 'bus_id', 'branch_parent_row', 'actual_budget_MW'])
        oh = np.asarray(od['hour_index'], int) - 1; oq = old_qualified[oh]; r41 = np.flatnonzero(od['branch_parent_row'] == 41)
        old_bus_lookup = {int(x): j for j, x in enumerate(od['bus_id'])}; old_target = {}
        for parent in [185, 195]:
            rr = parents == parent
            target_ids = np.unique(np.r_[axes['branch_from_bus'][rr], axes['branch_to_bus'][rr]]).astype(int)
            vm = od['VM'][:, [old_bus_lookup[x] for x in target_ids]]
            old_target[parent] = (vm.min(axis=1), vm.max(axis=1), ((vm < .95 - 1e-7) | (vm > 1.05 + 1e-7)).any(axis=1))
        for row in np.flatnonzero(oq):
            old_hourly.append({'hour_index': int(oh[row] + 1), 'parent41_loss_model_MW': float(np.sum(od['PF'][row, r41] + od['PT'][row, r41])),
                'NY_assigned_loss_model_MW': float(np.sum(od['actual_budget_MW'][row, :11])),
                **{f'parent{p}_{suffix}': (bool(old_target[p][j][row]) if suffix == 'voltage_violation' else float(old_target[p][j][row])) for p in [185, 195] for j, suffix in enumerate(['min_VM', 'max_VM', 'voltage_violation'])}})
        print(f'checked month {month:02d}: source {int(np.sum(d["source_qualified"]))}, qualified {int(q.sum())}', flush=True)
    assert largest(max_errors['branch_complex_power_MVA']) < 1e-5
    assert max(max_errors[x] for x in ['series_current_A', 'from_current_A', 'to_current_A']) < 1e-5
    assert max(max_errors[x] for x in ['series_loss_identity_MW', 'parent41_material_loss_identity_MW', 'nodal_P_MW', 'nodal_Q_MVAr']) < 1e-5
    assert max_errors['full_voltage_lift_pu'] < 1e-8 and max_errors['retained_voltage_pu'] < 1e-10
    frame = pd.DataFrame(hourly).sort_values('hour_index'); old_frame = pd.DataFrame(old_hourly).sort_values('hour_index')
    paired = frame.merge(old_frame, on='hour_index', suffixes=('_new', '_old'), validate='one_to_one')
    assert len(paired) == int(np.sum(new_good & old_qualified))
    targets = []
    for cohort, version, table in [('candidate_all_qualified', 'candidate', frame),
            ('paired_old_baseline', 'candidate', frame[frame.hour_index.isin(paired.hour_index)]),
            ('paired_old_baseline', 'baseline', old_frame[old_frame.hour_index.isin(paired.hour_index)]),
            ('old_baseline_all_qualified', 'baseline', old_frame)]:
        for parent in [41, 185, 195]:
            target = {'cohort': cohort, 'version': version, 'parent_row': parent, 'hours': len(table),
                'loss_mean_model_MW': None, 'loss_max_model_MW': None,
                'minimum_VM_pu': None, 'maximum_VM_pu': None, 'voltage_violation_hours': None}
            if parent == 41:
                target.update(loss_mean_model_MW=float(table.parent41_loss_model_MW.mean()), loss_max_model_MW=float(table.parent41_loss_model_MW.max()))
            else:
                target.update(minimum_VM_pu=float(table[f'parent{parent}_min_VM'].min()), maximum_VM_pu=float(table[f'parent{parent}_max_VM'].max()),
                    voltage_violation_hours=int(table[f'parent{parent}_voltage_violation'].sum()))
            targets.append(target)
    rows = []
    for cohort, mask in [('candidate_all_success', new_good), ('paired_current_baseline', new_good & old_qualified), ('candidate_new_success', new_good & ~old_qualified), ('old_baseline_same_calendar', seen & old_qualified), ('paired_baseline_reference', new_good & old_qualified)]:
        if not mask.any(): continue
        values = reference['candidate_legacy_signed_literal_from'][mask] if cohort in ['old_baseline_same_calendar', 'paired_baseline_reference'] else prediction[mask]
        observed = reference['observed'][mask]; assert np.isfinite(values).all() and np.isfinite(observed).all()
        for k, name in enumerate(interface_names):
            residual = values[:, k] - observed[:, k]
            rows.append({'cohort': cohort, 'interface': name, 'hours': int(mask.sum()), 'MAE_public_MW': float(np.abs(residual).mean()),
                'RMSE_public_MW': float(np.sqrt(np.mean(residual ** 2))), 'bias_public_MW': float(residual.mean())})
    for j, bus_id in enumerate(ids):
        if bus_count[j]: voltage_rows.append({'bus_id': int(bus_id), 'present_qualified_hours': int(bus_count[j]), 'overvoltage_hours': int(bus_over[j]),
            'undervoltage_hours': int(bus_under[j]), 'minimum_VM': float(bus_min[j]), 'maximum_VM': float(bus_max[j])})
    outputs = []
    for name, table in [('hourly_physical_readback.csv', frame), ('paired_loss_comparison.csv', paired), ('target_parent_metrics.csv', pd.DataFrame(targets)), ('interface_metrics.csv', pd.DataFrame(rows)), ('bus_voltage_readback.csv', pd.DataFrame(voltage_rows))]:
        path = OUT / (prefix + name); table.to_csv(path, index=False); outputs.append(record(path))
    if complete:
        assert seen.all() and source_mask.sum() == 8651
        assert new_good.sum() == annual['policy_equation_qualified_hours']
        source_files.append(RUN / 'annual_receipt.json')
    report = {'passed': True, 'completed_annual_review': complete, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'run_directory': RUN.relative_to(ROOT).as_posix(),
        'scope': 'Independent direct complex branch laws, nodal balance, passive-node reconstruction, material losses, requested-repair effects and remaining operating-limit readback of saved qualified annual arrays. No new PF solve.',
        'months': months, 'clock_rows_reviewed': int(seen.sum()), 'source_qualified_hours': int(source_mask.sum()),
        'candidate_qualified_hours': int(new_good.sum()), 'paired_old_baseline_hours': int(np.sum(new_good & old_qualified)),
        'new_success_hours': int(np.sum(new_good & ~old_qualified)), 'lost_old_success_hours': int(np.sum(seen & old_qualified & ~new_good)),
        'rejected_source_hours': int(np.sum(source_mask & ~new_good)), 'failed_iterates_excluded_from_physical_statistics': True,
        'maximum_recomputation_errors': max_errors, 'network_invariants': invariant_rows,
        'paired_parent41_loss_model_MW': {'old_mean': float(paired.parent41_loss_model_MW_old.mean()), 'new_mean': float(paired.parent41_loss_model_MW_new.mean()),
            'mean_reduction_percent': float(100 * (1 - paired.parent41_loss_model_MW_new.mean() / paired.parent41_loss_model_MW_old.mean()))},
        'candidate_parent41_mean_loss_model_MW': float(frame.parent41_loss_model_MW.mean()),
        'candidate_parent41_hardware_current_exceedance_hours': int(frame.parent41_hardware_current_limit_exceeded.sum()),
        'previous_parent41_RXB_and_parent185195_compensation_preserved': True,
        'previous_target_voltage_limits_pass_all_candidate_qualified_hours': not bool(frame[['parent185_voltage_violation', 'parent195_voltage_violation']].any().any()),
        'target_voltage': {str(p): {'min_VM': float(frame[f'parent{p}_min_VM'].min()), 'max_VM': float(frame[f'parent{p}_max_VM'].max()),
            'violation_hours': int(frame[f'parent{p}_voltage_violation'].sum())} for p in [185, 195]},
        'remaining_global_limits': {'overvoltage_hours': int(frame.global_overvoltage.sum()), 'undervoltage_hours': int(frame.global_undervoltage.sum()),
            'Q_violation_hours': int((frame.global_Q_violation_model_MVAr > 1e-5).sum()), 'S_violation_hours': int((frame.global_S_violation_model_MVA > 1e-5).sum()),
            'branch_MVA_violation_hours': int((frame.global_branch_MVA_violation > 1e-4).sum()), 'full_operating_qualified_hours': int(frame.full_operating_qualified.sum()),
            'minimum_VM': float(frame.global_min_VM.min()), 'maximum_VM': float(frame.global_max_VM.max())},
        'limitations': ['Research-model repair, not installed-asset certification or historical dispatch validation.',
            'Thermal DLR depends on weather and conductor temperature; this readback checks current bases, material-loss identity and the preserved 2000A parent41 apparatus ceiling, not a new annual thermal solve.',
            'Physical P32 meter membership and conditional source numeric-as-MW interpretation remain unchanged and unverified.',
            'Targeted voltage repairs do not imply whole-network operating feasibility.'],
        'sources': [record(p) for p in dict.fromkeys(source_files)], 'outputs': outputs}
    receipt = OUT / (prefix + 'annual_physics_review.json'); receipt.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['passed', 'completed_annual_review', 'candidate_qualified_hours', 'paired_old_baseline_hours', 'paired_parent41_loss_model_MW', 'target_voltage', 'remaining_global_limits']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--months', type=int, nargs='+')
    parser.add_argument('--run-dir', type=Path, default=RUN,
                        help='Saved annual run directory; defaults to moses_repair_v1.')
    parser.add_argument('--output-dir', type=Path,
                        help='Review output directory; a different run label defaults to its own subdirectory.')
    args = parser.parse_args(); default_run = RUN
    RUN = args.run_dir.resolve()
    OUT = args.output_dir.resolve() if args.output_dir else RUN / 'validation'
    months = sorted(set(args.months or range(1, 13)))
    assert all(1 <= x <= 12 for x in months)
    main(months)
