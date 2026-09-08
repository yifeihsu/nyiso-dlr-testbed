"""Score three restored-fleet AC cases against the common raw-mean targets.

Predictions are constructed before observations are selected. No optimization.
The DC comparison uses REF42 and the same unclipped source-prior case; the
AC comparison includes bounded dispatch and control movement, not losses alone.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

from dc_model import DCModel

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'output/nygrid_compact_2019'
OUT = BASE / 'ac_scoring'
NAMES = ['Dysinger East', 'West Central', 'Total East', 'Moses South',
         'Central East', 'UpNY-Coned', 'Dun/SPR-South']
CURRENT_NAMES = ['Dysinger_East', 'West_Central', 'Total_East_proxy', 'Moses_South',
                 'Central_East', 'UPNY_ConEd', 'Dunwoodie_South']
EXTENSION_ROLES = {774: 'G', 858: 'G', 9001: 'G', 9002: 'G', 9003: 'K'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_manifest(folder, filename):
    m = pd.read_csv(folder / 'output_manifest.csv', dtype=str)
    r = m.loc[m.relative_path == filename]
    if len(r) != 1 or r.iloc[0].sha256 != sha(folder / filename):
        raise ValueError(f'Input fingerprint mismatch: {filename}')


def relative_error(model, observed):
    error = np.abs(np.asarray(model) - np.asarray(observed))
    result = np.full(error.shape, np.nan)
    np.divide(100 * error, np.abs(observed), out=result, where=np.abs(observed) != 0)
    return result


def wape(model, observed):
    denominator = np.abs(observed).sum()
    return float(100 * np.abs(model - observed).sum() / denominator) if denominator else None


def terminal_coefficients(signed_dc):
    signed_dc = np.asarray(signed_dc)
    if not np.isin(signed_dc, [-1, 0, 1]).all():
        raise ValueError('Only directed terminal memberships are supported')
    # Reverse AC power must be metered at the to terminal. It is not -PF.
    return (signed_dc == 1).astype(float), (signed_dc == -1).astype(float)


def paper_operators(net, metadata):
    roles = dict(zip(metadata.bus_id, metadata.paper_allocation_zone))
    roles.update(EXTENSION_ROLES)
    z = np.array([roles[int(b)] for b in net.ids])
    if not np.isin(z, list('ABCDEFGHIJK')).all():
        raise ValueError('Missing paper-role identity')
    def cut(u, d):
        return net.cut(net.ids[np.isin(z, list(u))], net.ids[np.isin(z, list(d))])
    return np.array([cut('A', 'B'), cut('B', 'C'), cut('E', 'FG'),
                     cut('D', 'E'), cut('E', 'F'), cut('G', 'H'), cut('I', 'J')])


def write(df, filename):
    df.to_csv(OUT / filename, index=False, float_format='%.12g', lineterminator='\n')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source_paths = [Path(__file__), Path(__file__).with_name('dc_model.py'),
                    Path(__file__).with_name('test_score_ac_checkpoint.py'),
                    Path(__file__).with_name('verify_ac_scoring_dc.m'),
                    BASE / 'paper_role_operator_members.csv',
                    BASE / 'annual_predictions.npz', BASE / 'compact/compact_network.mat',
                    BASE / 'compact/current_input_snapshots.mat', BASE / 'compact/bus_metadata.csv',
                    BASE / 'ac_checkpoint/restored_fleet_ac_checkpoint.mat',
                    BASE / 'ac_checkpoint/summary.csv', BASE / 'ac_checkpoint/generator_movement.csv',
                    BASE / 'ac_checkpoint/bus_movement.csv', BASE / 'ac_checkpoint/interface_flows.csv',
                    OUT / 'dc_matpower_parity.mat']
    hashes_before = [sha(p) for p in source_paths]
    for filename in ['compact_network.mat', 'current_input_snapshots.mat', 'bus_metadata.csv']:
        verify_manifest(BASE / 'compact', filename)
    for filename in ['restored_fleet_ac_checkpoint.mat', 'summary.csv', 'generator_movement.csv',
                     'bus_movement.csv', 'interface_flows.csv']:
        verify_manifest(BASE / 'ac_checkpoint', filename)
    network = loadmat(BASE / 'compact/compact_network.mat', simplify_cells=True)['network_data']
    inputs = loadmat(BASE / 'compact/current_input_snapshots.mat', simplify_cells=True)['input_data']
    checkpoint = loadmat(BASE / 'ac_checkpoint/restored_fleet_ac_checkpoint.mat', simplify_cells=True)['out']
    summary = pd.read_csv(BASE / 'ac_checkpoint/summary.csv')
    metadata = pd.read_csv(BASE / 'compact/bus_metadata.csv')
    gamma = float(network['gamma2019'])
    assert gamma == .358662225381536 and len(summary) == 3 and len(checkpoint['cases']) == 3
    assert summary.bounded_AC_qualified.eq(1).all() and summary.interface_objective_used.eq(0).all()
    input_by_id = {v['scenario_id']: v for v in inputs}
    current_names = list(network['current_interface_names'])
    order = [current_names.index(n) for n in CURRENT_NAMES]
    # MAT v7 can store exact 0/1 doubles as uint8; subtraction must remain
    # signed (otherwise a reverse member becomes +255 instead of -1).
    cf_current = np.asarray(network['current_from_coefficients'][order], dtype=float)
    ct_current = np.asarray(network['current_to_coefficients'][order], dtype=float)
    assert np.array_equal(cf_current-ct_current,network['current_dc_coefficients'][order])
    predictions = []; members = []; dc_flows = []; dc_gens = []
    for k, row in summary.iterrows():
        e = checkpoint['cases'][k]; s = e['snapshot']; result = e['fit']['result']
        m = input_by_id[row.scenario_id]['paper74']
        for field in ['bus', 'gen', 'branch']:
            assert np.array_equal(s['candidate'][field], m[field])
        assert np.array_equal(m['bus'][:, 0], network['bus_ids'])
        assert int(m['bus'][m['bus'][:, 1] == 3, 0].item()) == 42
        assert np.array_equal(result['branch'][:, :13], m['branch'])
        assert np.array_equal(result['gen'][:, [0, 3, 4, 7, 8, 9]], m['gen'][:, [0, 3, 4, 7, 8, 9]])
        net = DCModel(m['bus'], m['branch'], m['baseMVA'], reference_bus=42)
        pg = np.zeros(len(net.ids)); on = m['gen'][:, 7] > 0
        for g in m['gen'][on]:
            pg[net.lookup[int(g[0])]] += g[1]
        dc = net.solve(pg - m['bus'][:, 2] - m['bus'][:, 4])
        expected_gen = m['gen'][:, 1].copy()
        ref_generators = np.flatnonzero(on & (m['gen'][:, 0] == 42))
        assert len(ref_generators) > 0
        expected_gen[ref_generators[0]] += dc['slack_adjustment_mw'][0]
        dc_flows.append(dc['flow'][0]); dc_gens.append(expected_gen)
        paper = paper_operators(net, metadata); cf_paper, ct_paper = terminal_coefficients(paper)
        registered = pd.read_csv(BASE/'paper_role_operator_members.csv')
        registered = registered[registered.network.eq('compact51')]
        expected = np.zeros_like(paper)
        for member in registered.itertuples():
            j = int(member.branch_row)-1
            assert tuple(m['branch'][j,:2].astype(int)) == (member.from_bus,member.to_bus)
            expected[NAMES.index(member.interface),j] = member.coefficient
        assert np.array_equal(expected,paper), 'Paper-role identities differ from common comparison registry'
        for role, cf, ct in [('current_roles', cf_current, ct_current), ('paper_roles', cf_paper, ct_paper)]:
            assert not np.any((cf + ct)[:, m['branch'][:, 10] == 0])
            ac = cf @ result['branch'][:, 13] + ct @ result['branch'][:, 15]
            dc_interface = (cf - ct) @ dc['flow'][0]
            predictions.append(dict(scenario_id=row.scenario_id, timestamp=row.timestamp, role=role,
                                    ac=ac, dc=dc_interface, dc_reference_adjustment=dc['slack_adjustment_mw'][0],
                                    dc_nodal_residual=dc['nodal_residual_mw'][0],
                                    dc_max_P_bound_violation=float(np.maximum.reduce([
                                        np.maximum(0,m['gen'][on,9]-expected_gen[on]),
                                        np.maximum(0,expected_gen[on]-m['gen'][on,8])]).max()),
                                    raw_reference_PF_branch_loss_mw=float((e['raw_prior_PF']['branch'][:,13]+e['raw_prior_PF']['branch'][:,15]).sum()),
                                    bounded_AC_branch_loss_mw=float((result['branch'][:,13]+result['branch'][:,15]).sum())))
            if k == 0:
                for i, name in enumerate(NAMES):
                    for j in np.flatnonzero(cf[i] + ct[i]):
                        members.append(dict(operator_role=role, interface_name=name,
                                            branch_key=m['branch_keys'][j], branch_row=j+1,
                                            from_bus=int(m['branch'][j, 0]), to_bus=int(m['branch'][j, 1]),
                                            metered_terminal='PF' if cf[i, j] else 'PT', coefficient=1,
                                            exact_public_metering=False))
    # Independent MATPOWER parity at the same reference, including which
    # online reference generator receives the balance adjustment.
    parity = loadmat(OUT / 'dc_matpower_parity.mat', simplify_cells=True)
    assert list(parity['scenario_ids']) == summary.scenario_id.tolist()
    assert parity['reference_bus'] == 42
    assert parity['source_sha'] == sha(BASE / 'ac_checkpoint/restored_fleet_ac_checkpoint.mat')
    flow_parity = float(np.max(np.abs(np.array(dc_flows) - parity['dc_branch_pf'])))
    gen_parity = float(np.max(np.abs(np.array(dc_gens) - parity['dc_pg'])))
    assert flow_parity < 1e-7 and gen_parity < 1e-7
    # Load the shared observations only after constructing every prediction.
    archive = np.load(BASE / 'annual_predictions.npz')
    assert float(archive['gamma']) == gamma and list(archive['interfaces']) == NAMES
    times = pd.to_datetime(archive['timestamps'])
    assert len(times) == 8760 and not times.duplicated().any()
    rows = []; pooled = []
    for p in predictions:
        at = np.flatnonzero(times == pd.Timestamp(p['timestamp'])); assert len(at) == 1
        target = archive['observed_benchmark_mw'][at[0]]
        assert np.isfinite(target).all()
        ac_pct = relative_error(p['ac'], target); dc_pct = relative_error(p['dc'], target)
        ac_wape = wape(p['ac'], target); dc_wape = wape(p['dc'], target)
        pooled.append(dict(scenario_id=p['scenario_id'], timestamp=p['timestamp'], operator_role=p['role'],
                           DC_raw_prior_REF42_WAPE_pct=dc_wape, bounded_AC_WAPE_pct=ac_wape,
                           AC_minus_DC_WAPE_percentage_points=ac_wape-dc_wape,
                           DC_MAE_public_mw=float(np.abs(p['dc']-target).mean()/gamma),
                           AC_MAE_public_mw=float(np.abs(p['ac']-target).mean()/gamma),
                           DC_reference_adjustment_benchmark_mw=p['dc_reference_adjustment'],
                           DC_nodal_residual_mw=p['dc_nodal_residual'],
                           DC_max_generator_P_bound_violation_mw=p['dc_max_P_bound_violation'],
                           raw_reference_PF_branch_loss_mw=p['raw_reference_PF_branch_loss_mw'],
                           bounded_AC_branch_loss_mw=p['bounded_AC_branch_loss_mw'],
                           incremental_effect='bounded_P_dispatch_Q_voltage_and_AC_losses_combined'))
        for j, name in enumerate(NAMES):
            rows.append(dict(scenario_id=p['scenario_id'], timestamp=p['timestamp'], operator_role=p['role'],
                             interface_name=name, observed_benchmark_mw=target[j], observed_public_mw=target[j]/gamma,
                             DC_raw_prior_REF42_benchmark_mw=p['dc'][j], DC_raw_prior_REF42_public_mw=p['dc'][j]/gamma,
                             bounded_AC_benchmark_mw=p['ac'][j], bounded_AC_public_mw=p['ac'][j]/gamma,
                             DC_absolute_error_public_mw=abs(p['dc'][j]-target[j])/gamma,
                             AC_absolute_error_public_mw=abs(p['ac'][j]-target[j])/gamma,
                             DC_actual_flow_error_pct=dc_pct[j], AC_actual_flow_error_pct=ac_pct[j],
                             AC_minus_DC_error_percentage_points=ac_pct[j]-dc_pct[j],
                             AC_minus_DC_absolute_error_public_mw=(abs(p['ac'][j]-target[j])-abs(p['dc'][j]-target[j]))/gamma,
                             AC_minus_DC_flow_public_mw=(p['ac'][j]-p['dc'][j])/gamma,
                             DC_wrong_direction=bool(p['dc'][j]*target[j]<0),
                             AC_wrong_direction=bool(p['ac'][j]*target[j]<0),
                             exact_zero_observation=bool(target[j] == 0),
                             targets_used_in_optimization=False))
    errors = pd.DataFrame(rows)
    # Cross-check current-role flow export from the independent MATLAB audit.
    prior_flows = pd.read_csv(BASE / 'ac_checkpoint/interface_flows.csv')
    aliases = dict(zip(CURRENT_NAMES, NAMES)); prior_flows['name'] = prior_flows.interface_name.map(aliases)
    cross = errors[errors.operator_role.eq('current_roles')].merge(prior_flows, left_on=['scenario_id','interface_name'],
                                                                 right_on=['scenario_id','name'], validate='one_to_one')
    assert len(cross) == 21 and np.max(abs(cross.bounded_AC_benchmark_mw-cross.model_flow_benchmark_mw)) < 1e-7
    aggregate = []
    for role, group in errors.groupby('operator_role', sort=False):
        for name, g in [('ALL_7', group), *list(group.groupby('interface_name', sort=False))]:
            target = g.observed_benchmark_mw.to_numpy(); dc = g.DC_raw_prior_REF42_benchmark_mw.to_numpy(); ac = g.bounded_AC_benchmark_mw.to_numpy()
            aggregate.append(dict(operator_role=role, interface_name=name, points=len(g),
                                  DC_WAPE_pct=wape(dc,target), AC_WAPE_pct=wape(ac,target),
                                  AC_minus_DC_WAPE_percentage_points=wape(ac,target)-wape(dc,target),
                                  DC_MAE_public_mw=float(abs(dc-target).mean()/gamma), AC_MAE_public_mw=float(abs(ac-target).mean()/gamma),
                                  DC_wrong_direction_count=int((dc*target<0).sum()), AC_wrong_direction_count=int((ac*target<0).sum())))
    write(errors, 'interface_error_comparison.csv');write(pd.DataFrame(pooled), 'snapshot_comparison.csv')
    write(pd.DataFrame(aggregate), 'aggregate_comparison.csv');write(pd.DataFrame(members), 'operator_members.csv')
    gm = pd.read_csv(BASE / 'ac_checkpoint/generator_movement.csv')
    for c in ['raw_prior_pg_mw', 'solved_pg_mw', 'pg_departure_mw']:
        gm[c.replace('_mw','_public_mw')] = gm[c]/gamma
    write(gm, 'unit_control_movement.csv');write(pd.read_csv(BASE / 'ac_checkpoint/bus_movement.csv'), 'bus_control_movement.csv')
    write(summary, 'AC_feasibility_and_control_summary.csv')
    report = dict(gamma2019=gamma, snapshot_count=3, interfaces_per_snapshot=7, reference_bus=42,
                  observation_policy='same_2019_hourly_raw_arithmetic_sample_mean_as_annual_predictions',
                  source_input_policy='existing_independent_source_priors_P32_forward_hold_600s_gap_coverage',
                  current_roles='exported_51bus_current_physical_role_partitions',
                  paper_roles='released_adjacent_role_pairs_with_declared_compact_extension_roles',
                  paper_role_extension_assumptions=EXTENSION_ROLES,
                  AC_metering='forward_PF_reverse_PT_at_upstream_terminal_no_minus_PF_substitution',
                  DC_input='same_raw_unclipped_37generator_prior_same_effective_loads_REF42_balancing',
                  bounded_AC='same_network_existing_capabilities_reoptimized_P_Q_and_voltage_controls',
                  incremental_error_scope='combined_dispatch_control_and_AC_effect_not_isolated_AC_losses',
                  control_policy_caveat='P_only_prior_objective_has_no_Q_or_voltage_movement_penalty_and_may_change_losses_to_preserve_source_P',
                  Marcy_DC_hypothesis_AC_qualified=False, matrix_DC_REF74_comparison=False,
                  zero_denominator_policy='pointwise_percentage_undefined_no_floor_WAPE_uses_total_absolute_observed_flow',
                  MATPOWER_DC_branch_flow_parity_max_mw=flow_parity, MATPOWER_DC_generation_parity_max_mw=gen_parity,
                  overall=[r for r in aggregate if r['interface_name']=='ALL_7'])
    (OUT/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    assert [sha(p) for p in source_paths] == hashes_before, 'Inputs/code changed during scoring'
    write(pd.DataFrame([dict(relative_path=p.relative_to(ROOT).as_posix(),sha256=h) for p,h in zip(source_paths,hashes_before)]), 'input_manifest.csv')
    files=sorted(p for p in OUT.iterdir() if p.is_file() and p.name!='output_manifest.csv')
    write(pd.DataFrame([dict(relative_path=p.name,sha256=sha(p)) for p in files]), 'output_manifest.csv')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
