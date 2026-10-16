"""Unfitted electrical-parameter scenarios for the Downstate reconstruction.

The year-end topology is held fixed over the same 8,663 qualified hours. Parameter
runs hold the asset injection mapping fixed; separate diagnostics isolate the
generator and I/J/K load mappings. This is not a chronology replay, confidence
interval, calibration, or physical-rating validation. No interface observation
file is read and no per-unit generation or aggregate load is changed.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / 'output/nygrid_2025_downstate'
BASELINE = ROOT / 'output/nygrid_2025_dispatch/dispatch'
sys.path.insert(0, str(ROOT / 'scripts/nygrid_2019'))
from replay_dc import network, predict
from validate_refinement import zone_interface_operators, INTERFACE_DEFINITIONS

GROUPS = ['project_electrical_assumption', 'proxy_attachment_assumption']
TOL = 1e-7


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def operator_helper_fingerprint(path):
    """Pin the imported operator's definitions while unrelated audits evolve."""
    parsed=ast.parse(Path(path).read_text(encoding='utf-8'))
    nodes=[]
    for node in parsed.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in {'require','dc_matrices','zone_interface_operators'}:
            nodes.append(ast.dump(node,include_attributes=False))
        elif isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='INTERFACE_DEFINITIONS' for t in node.targets):
            nodes.append(ast.dump(node,include_attributes=False))
    require(len(nodes)==4,'Operator helper definitions not found')
    return hashlib.sha256('\n'.join(nodes).encode()).hexdigest()


def edge_on_cycle(branch, edge):
    """True when another active path joins these terminals, including parallels."""
    adjacency = {}
    start, target = map(int, branch[edge, :2])
    for j, row in enumerate(branch):
        if j == edge or row[10] != 1:
            continue
        a, b = map(int, row[:2])
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)
    seen, queue = {start}, [start]
    while queue:
        current = queue.pop()
        if current == target:
            return True
        for nxt in adjacency.get(current, []):
            if nxt not in seen:
                seen.add(nxt); queue.append(nxt)
    return False


def scenario_plans(case, register):
    branch = np.asarray(case['branch'])
    active = branch[:, 10] == 1
    plans = [dict(scenario='nominal', parameter_family='reference', group='', factor=1., phase_delta_degree=0., rows=[])]
    group_rows = {}
    for group in GROUPS:
        rows = np.flatnonzero(active & register.uncertainty_group.eq(group).to_numpy()).tolist()
        require(rows, 'No active declared uncertainty rows for ' + group)
        require((branch[rows, 3] > 0).all(), 'Reactance sensitivity requires positive base reactances')
        group_rows[group] = rows
        for factor in [.5, 2.]:
            plans.append(dict(scenario=group + ('_x050' if factor == .5 else '_x200'),
                parameter_family='reactance', group=group, factor=factor, phase_delta_degree=0., rows=rows))
    combined = sorted(set(sum(group_rows.values(), [])))
    for factor in [.5, 2.]:
        plans.append(dict(scenario='all_assumptions' + ('_x050' if factor == .5 else '_x200'),
            parameter_family='reactance', group='both_assumption_groups', factor=factor, phase_delta_degree=0., rows=combined))
    # PARENT:* must not match a loose substring "PAR". Only explicitly modeled
    # project PAR rows with a verified alternate path are candidates.
    par_rows = np.flatnonzero(active & register.branch_key.str.startswith('RCC:PAR:').to_numpy()
                             & register.uncertainty_group.eq('project_electrical_assumption').to_numpy())
    par_audit = []
    for j in par_rows:
        loop = edge_on_cycle(branch, int(j))
        par_audit.append(dict(branch_key=register.iloc[j].branch_key, model_branch_row=int(j+1),
            from_bus=int(branch[j, 0]), to_bus=int(branch[j, 1]), active=True, alternate_path_exists=loop,
            stressed=loop, base_shift_degree=float(branch[j, 9]),
            interpretation='modeled_combined_transformer_PAR_equivalent;no_asbuilt_angle_schedule_claim'))
        if loop:
            short = str(register.iloc[j].branch_key).replace(':', '_').lower()
            for delta in [-5., 5.]:
                plans.append(dict(scenario=short + ('_phase_minus5' if delta < 0 else '_phase_plus5'),
                    parameter_family='phase_shift', group=str(register.iloc[j].branch_key), factor=1.,
                    phase_delta_degree=delta, rows=[int(j)]))
    require(len({p['scenario'] for p in plans}) == len(plans), 'Duplicated sensitivity scenario')
    for plan in plans:
        plan.update(generator_mapping='asset', load_mapping='asset')
    for name, gen, load in [('topology_only_control','identity','identity'),
                            ('generation_only','asset','identity'),('load_only','identity','asset'),
                            ('load_I_only','identity','asset_I'),('load_J_only','identity','asset_J'),
                            ('load_K_only','identity','asset_K')]:
        plans.append(dict(scenario=name, parameter_family='injection_diagnostic', group=name,
            factor=1., phase_delta_degree=0., rows=[], generator_mapping=gen, load_mapping=load))
    return plans, par_audit


def run(folder=DEFAULT):
    folder = Path(folder).resolve()
    output = folder / 'sensitivity'
    output.mkdir(parents=True, exist_ok=True)
    require(not (output / 'sensitivity_manifest.json').exists(), 'Choose a fresh sensitivity output root; completed results already exist')
    case_path = folder / 'network/network_cases.mat'
    branch_path, bus_path = folder / 'network/branch_register.csv', folder / 'network/bus_register.csv'
    reference_path = folder / 'validation/baseline_reference.json'
    baseline_receipt = json.loads(reference_path.read_text())
    for item in baseline_receipt['artifacts']:
        require(sha(ROOT / item['path']) == item['sha256'], 'Frozen baseline changed: ' + item['path'])
    dependencies = [case_path, branch_path, bus_path, reference_path, BASELINE / 'dispatch.mat',
        folder / 'network/generation_landing_register.csv', folder / 'network/load_allocation_register.csv',
        Path(__file__), ROOT / 'scripts/nygrid_2019/replay_dc.py', Path(__file__).parent / 'validate_refinement.py']
    receipts = [dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in dependencies]
    helper_path=Path(__file__).parent/'validate_refinement.py'
    helper_fingerprint=operator_helper_fingerprint(helper_path)
    baseline = loadmat(BASELINE / 'dispatch.mat', simplify_cells=True,
        variable_names=['hour_index', 'timestamp_utc', 'dispatch_qualified', 'gamma', 'gen_pg', 'bus_pd', 'dc_pf'])
    construction = loadmat(case_path, simplify_cells=True)
    register = pd.read_csv(branch_path, keep_default_na=False)
    bus_register = pd.read_csv(bus_path, keep_default_na=False)
    zones = dict(zip(bus_register.model_bus.astype(int), bus_register.accounting_zone.astype(str)))
    case = copy.deepcopy(construction['refined_2025_case'])
    require(np.array_equal(register.model_branch_row.to_numpy(int), np.arange(1, len(case['branch'])+1)), 'Branch register order changed')
    require(np.array_equal(register.branch_key.astype(str), np.asarray(construction['branch_keys']).astype(str)), 'Branch keys differ')
    require(np.array_equal(case['branch'][:, 10], register.refined_2025_status), 'Refined case status differs from register')
    require(np.allclose(case['branch'][:, 3], register.x_pu.to_numpy(float), rtol=0, atol=1e-15), 'Refined X differs from register')
    generator_mappings={kind:np.asarray(construction['generator_bus_'+kind]).reshape(-1) for kind in ['asset','identity']}
    case['gen'][:, 0] = generator_mappings['asset']
    allocations={kind:np.asarray(construction['load_allocation_'+kind],float) for kind in ['asset','identity']}
    original_ids=np.asarray(construction['parent_case']['bus'])[:,0].astype(int)
    original_zones=np.array([zones[i] for i in original_ids])
    for zone in ['I','J','K']:
        w=allocations['identity'].copy(); w[:,original_zones==zone]=allocations['asset'][:,original_zones==zone]
        allocations['asset_'+zone]=w
    for weights in allocations.values():
        require(np.max(abs(weights.sum(axis=0)-1)) < 1e-12, 'Load scenario shares not conservative')
    loads={name:np.asarray(baseline['bus_pd'],float)@w.T for name,w in allocations.items()}
    pg, dc = np.asarray(baseline['gen_pg'], float), np.asarray(baseline['dc_pf'], float)
    hours = np.asarray(baseline['hour_index'], int).reshape(-1)
    times = np.asarray(baseline['timestamp_utc']).astype(str).reshape(-1)
    valid = np.asarray(baseline['dispatch_qualified'], bool).reshape(-1)
    gamma = float(baseline['gamma'])
    require(valid.sum() == 8663 and len(hours) == 8760, 'Sensitivity cohort must equal the frozen 8663 of 8760 hours')
    require(gamma == float(construction['gamma']), 'Frozen gamma differs')
    require(pg.shape == (8760, len(case['gen'])) and dc.shape == (8760, len(case['dcline'])), 'Frozen injection shape differs')
    require(np.isfinite(pg[valid]).all() and all(np.isfinite(load[valid]).all() for load in loads.values())
            and np.isfinite(dc[valid]).all(), 'Qualified injections contain missing values')
    plans, par_audit = scenario_plans(case, register)
    names = [row[1] for row in INTERFACE_DEFINITIONS]
    operator = zone_interface_operators(case, zones)
    frozen_rows = register.uncertainty_group.isin(['frozen_source', 'algebraic_scaffold']).to_numpy()
    changed, summaries, interface_summaries, predictions = [], [], [], []
    nominal = None
    for plan in plans:
        candidate = copy.deepcopy(case)
        candidate['gen'][:,0]=generator_mappings[plan['generator_mapping']]
        load=loads[plan['load_mapping']]
        rows = np.asarray(plan['rows'], int)
        column = 3 if plan['parameter_family'] == 'reactance' else 9
        if len(rows):
            if plan['parameter_family'] == 'reactance':
                candidate['branch'][rows, 3] *= plan['factor']
            else:
                candidate['branch'][rows, 9] += plan['phase_delta_degree']
            for j in rows:
                changed.append(dict(scenario=plan['scenario'], branch_key=register.iloc[j].branch_key,
                    model_branch_row=int(j+1), uncertainty_group=register.iloc[j].uncertainty_group,
                    project=register.iloc[j].project, parameter='x_pu' if column == 3 else 'shift_degree',
                    before=float(case['branch'][j, column]), after=float(candidate['branch'][j, column]),
                    parameter_basis=register.iloc[j].parameter_basis))
        require(np.array_equal(candidate['branch'][frozen_rows], case['branch'][frozen_rows]), 'Frozen source or scaffold branch changed')
        for key in ['bus', 'dcline']:
            require(np.array_equal(candidate[key], case[key]), 'Sensitivity changed ' + key)
        require(np.array_equal(candidate['gen'][:,1:],case['gen'][:,1:]),'Sensitivity changed generator fields other than declared bus mapping')
        require(np.array_equal(zone_interface_operators(candidate, zones), operator), 'Sensitivity changed interface membership')
        result = predict(network(candidate), load[valid], pg[valid], dc[valid])
        residual = float(np.max(result['nodal_residual_mw']))
        slack = float(np.max(abs(result['result_pg'] - pg[valid])))
        require(residual < TOL and slack < TOL, 'Parameter scenario requires balancing generation: ' + plan['scenario'])
        prediction = result['flow'] @ operator.T
        require(np.isfinite(prediction).all(), 'Nonfinite scenario prediction')
        if nominal is None:
            nominal = prediction.copy()
        predictions.append(prediction)
        full = np.full((8760, len(names)), np.nan); full[valid] = prediction
        result_path = output / (plan['scenario'] + '.mat')
        savemat(result_path, dict(hour_index=hours, timestamp_utc=times.astype(object), qualified=valid,
            interface_pf=full, interface_names=np.asarray(names, object), gamma=gamma,
            scenario=plan['scenario'], topology_scope='fixed_year_end_2025_not_dated_annual_replay',
            generator_mapping=plan['generator_mapping'], load_allocation=plan['load_mapping']), do_compression=True, oned_as='column')
        delta = (prediction-nominal)/gamma
        summaries.append(dict(scenario=plan['scenario'], parameter_family=plan['parameter_family'], group=plan['group'],
            x_factor=plan['factor'], phase_delta_degree=plan['phase_delta_degree'], changed_branches=len(rows),
            generator_mapping=plan['generator_mapping'],load_mapping=plan['load_mapping'],
            qualified_hours=int(valid.sum()), maximum_nodal_residual_model_mw=residual,
            maximum_hypothetical_slack_change_model_mw=slack,
            maximum_absolute_interface_change_actual_equivalent_mw=float(abs(delta).max()),
            output_path=result_path.relative_to(ROOT).as_posix(), output_sha256=sha(result_path)))
        for j, name in enumerate(names):
            interface_summaries.append(dict(scenario=plan['scenario'], interface=name, qualified_hours=int(valid.sum()),
                mean_prediction_actual_equivalent_mw=float(prediction[:, j].mean()/gamma),
                mean_change_from_nominal_actual_equivalent_mw=float(delta[:, j].mean()),
                mean_absolute_change_from_nominal_actual_equivalent_mw=float(abs(delta[:, j]).mean()),
                maximum_absolute_change_from_nominal_actual_equivalent_mw=float(abs(delta[:, j]).max()),
                change_rmse_actual_equivalent_mw=float(np.sqrt(np.mean(delta[:, j]**2))),
                measured_interface_observations_used=False))
        print(json.dumps(summaries[-1]), flush=True)
    # Electrical parameter envelopes exclude the separate injection-mapping
    # diagnostics, which investigate a different assumption and error mechanism.
    parameter_indices=[i for i,p in enumerate(plans) if p['parameter_family']!='injection_diagnostic']
    stack = np.stack([predictions[i] for i in parameter_indices])/gamma
    minimum, maximum = stack.min(axis=0), stack.max(axis=0)
    spread = maximum-minimum
    envelope = []
    for j, name in enumerate(names):
        means = stack[:, :, j].mean(axis=1)
        envelope.append(dict(interface=name, scenario_count=len(parameter_indices), qualified_hours=int(valid.sum()),
            minimum_scenario_mean_actual_equivalent_mw=float(means.min()),
            maximum_scenario_mean_actual_equivalent_mw=float(means.max()),
            scenario_mean_range_actual_equivalent_mw=float(means.max()-means.min()),
            mean_hourly_scenario_spread_actual_equivalent_mw=float(spread[:, j].mean()),
            p95_hourly_scenario_spread_actual_equivalent_mw=float(np.quantile(spread[:, j], .95)),
            maximum_hourly_scenario_spread_actual_equivalent_mw=float(spread[:, j].max()),
            interpretation='declared_scenario_range_not_a_confidence_interval_or_full_uncertainty_bound'))
    by_name={plan['scenario']:prediction for plan,prediction in zip(plans,predictions)}
    control=by_name['topology_only_control']
    gen_delta=by_name['generation_only']-control
    load_delta=by_name['load_only']-control
    both_delta=by_name['nominal']-control
    zone_sum=sum(by_name['load_'+zone+'_only']-control for zone in ['I','J','K'])
    gen_load_error=float(np.max(abs(both_delta-gen_delta-load_delta)))
    zone_error=float(np.max(abs(load_delta-zone_sum)))
    require(gen_load_error<TOL and zone_error<TOL,'Fixed-network injection diagnostics fail linear decomposition')
    attribution=[]
    for name in ['topology_only_control','generation_only','load_only','load_I_only','load_J_only','load_K_only','nominal']:
        values=by_name[name];delta=(values-control)/gamma
        for j,interface in enumerate(names):
            attribution.append(dict(scenario=name,interface=interface,qualified_hours=int(valid.sum()),
                mean_prediction_actual_equivalent_mw=float(values[:,j].mean()/gamma),
                mean_change_from_topology_only_actual_equivalent_mw=float(delta[:,j].mean()),
                mean_absolute_change_from_topology_only_actual_equivalent_mw=float(abs(delta[:,j]).mean()),
                maximum_absolute_change_from_topology_only_actual_equivalent_mw=float(abs(delta[:,j]).max()),
                classification='fixed_dispatch_mapping_diagnostic_not_observed_nodal_load_validation'))
    pd.DataFrame(summaries).to_csv(output/'scenarios.csv', index=False, lineterminator='\n')
    pd.DataFrame(interface_summaries).to_csv(output/'interface_scenario_summary.csv', index=False, lineterminator='\n')
    pd.DataFrame(envelope).to_csv(output/'scenario_envelope_summary.csv', index=False, lineterminator='\n')
    pd.DataFrame(par_audit).to_csv(output/'par_loop_eligibility.csv', index=False, lineterminator='\n')
    pd.DataFrame(attribution).to_csv(output/'injection_attribution_summary.csv',index=False,lineterminator='\n')
    (output/'parameter_changes.json').write_text(json.dumps(changed,indent=2)+'\n',encoding='utf-8')
    for receipt in receipts:
        final_hash=sha(ROOT/receipt['path'])
        if final_hash!=receipt['sha256'] and ROOT/receipt['path']==helper_path:
            require(operator_helper_fingerprint(helper_path)==helper_fingerprint,'Scientific operator helper changed during run')
            receipt.update(initial_sha256=receipt['sha256'],sha256=final_hash,
                           change_policy='unrelated_validation_code_changed;used_helper_AST_and_interface_definitions_unchanged')
        else:
            require(final_hash == receipt['sha256'], 'Dependency changed during sensitivity run: ' + receipt['path'])
    manifest = dict(status='completed_unfitted_parameter_scenario_experiment', base_case='refined_2025_case',
        injection_mapping='asset_for_parameter_runs_declared_per_plan_for_injection_diagnostics', chronology='year_end_topology_held_fixed_over_all_8663_qualified_2025_hours',
        annual_hours=8760, qualified_hours=8663, missing_source_hours=97, gamma=gamma,
        scenario_count=len(plans), scenarios=plans, dependencies=receipts,
        used_operator_helper_AST_sha256=helper_fingerprint,
        electrical_parameter_scenarios=len(parameter_indices),injection_diagnostic_scenarios=len(plans)-len(parameter_indices),
        generation_plus_load_superposition_error_model_mw=gen_load_error,
        zone_load_superposition_error_model_mw=zone_error,
        outputs=summaries, interface_observation_data_read=False, model_fitted=False, scenario_selected_by_error=False,
        per_unit_generation_zonal_demand_DC_schedules_unchanged=True,
        electrical_parameter_scenarios_injection_mapping_unchanged=True,
        injection_diagnostics_change_only_declared_generator_bus_or_IJK_spatial_load_mapping=True,
        source_and_scaffold_parameters_unchanged=True,
        interface_operator='inherited_zone_crossing_proxy_rebuilt_on_active_edges_not_certified_physical_flowgate',
        scope='reactance0.5x_2x_by_assumption_group_and_joint;individual_explicit_RCC_loop_PAR_minus5_plus5degree',
        range_interpretation='declared_scenarios_not_probabilistic_confidence_intervals_not_exhaustive_uncertainty_bounds',
        exclusions='NoR_B_thermal_rating_unitcommitment_AC_voltage_or_newnodal_load_uncertainty_sweep;DoverinternalPARconfigurationnotinvented',
        thermal_and_AC_feasibility_validated=False)
    (output/'sensitivity_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=manifest['status'], scenarios=len(plans), qualified_hours=8663,
                         envelope=envelope),indent=2),flush=True)
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--folder',type=Path,default=DEFAULT)
    run(parser.parse_args().folder)
