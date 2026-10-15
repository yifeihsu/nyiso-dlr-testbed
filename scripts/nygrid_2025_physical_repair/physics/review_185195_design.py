"""Source-bound compensation design and fixed-endpoint passive-line check.

Writes only the new physical-repair namespace. The preserved 75% rating is
redistributed from original terminals to every section endpoint. No interface
observations or voltage-based parameter optimization enters this design.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_physical_repair/physics'


def record(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def chain_matrix(branch, bus_ids, shunt_MVAr, base):
    lookup = {int(x): i for i, x in enumerate(bus_ids)}
    Y = np.diag(1j * np.asarray(shunt_MVAr) / base)
    for row in branch:
        assert row[10] > 0 and row[8] in (0, 1) and row[9] == 0
        f, t = lookup[int(row[0])], lookup[int(row[1])]
        y = 1 / complex(row[2], row[3]); b = 1j * row[4] / 2
        Y[f, f] += y + b; Y[t, t] += y + b
        Y[f, t] -= y; Y[t, f] -= y
    return Y


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    model_path = ROOT / 'output/nygrid_2025_latest_handoff/model/latest_model.mat'
    static = loadmat(model_path, simplify_cells=True)['model']
    plan_path = ROOT / 'output/nygrid_2025_remaining_errors/probes/probe_plan.json'
    plan = json.loads(plan_path.read_text()); hours = [int(x['hour_index']) for x in plan['samples']]
    sources = [model_path, plan_path,
        ROOT / 'output/nygrid_2025_ac_system/branches/branch_assignments.csv',
        ROOT / 'output/nygrid_2025_ac_system/branches/section_and_reactor_plan.csv',
        ROOT / 'output/nygrid_2025_ac_system/engineering/shunt_reactor_source_review.json',
        ROOT / 'output/nygrid_2025_ac_system/engineering/sources/SEL_Oncor_2013_shunt_reactors.pdf',
        ROOT / 'scripts/nygrid_2025_physical_repair/physics/nyrepair_apply_185195.m', Path(__file__)]
    declarations = []; placement = []; line_profiles = []; errors = []
    for state, template in enumerate(static['templates'], 1):
        bus = template['bus']; branch = template['branch']; ids = bus[:, 0].astype(int)
        sec = template['userdata']['ac_sections']; parents = template['userdata']['ac_system']['branch_parent_row']
        for parent in [185, 195]:
            rows = np.flatnonzero(parents == parent); br = branch[rows]
            ledger = next(x for x in sec['reactor_ledger'] if x['original_branch_row'] == parent)
            assert np.all(br[:, 10] > 0)
            n = len(rows); nodes = np.unique(br[:, :2]).astype(int); lookup = {x: i for i, x in enumerate(nodes)}
            q = .75 * float(static['baseMVA']) * br[:, 4].sum()
            assert abs(q - ledger['applied_total_reactor_mvar_at1pu']) < 1e-8
            old = np.zeros(len(nodes)); new = np.zeros(len(nodes))
            old[lookup[ledger['from_bus']]] = ledger['from_bus_BS_delta_mvar']
            old[lookup[ledger['to_bus']]] = ledger['to_bus_BS_delta_mvar']
            for row in br:
                for x in row[:2].astype(int): new[lookup[x]] -= .75 * static['baseMVA'] * row[4] / 2
            assert abs(old.sum() - new.sum()) < 1e-8
            for i, x in enumerate(nodes):
                placement.append({'state_index': state, 'parent_row': parent, 'bus_id': x,
                    'original_terminal': x in [ledger['from_bus'], ledger['to_bus']],
                    'old_parent_BS_MVAr_at1pu': old[i], 'new_parent_BS_MVAr_at1pu': new[i],
                    'net_bus_BS_change_MVAr_at1pu': new[i] - old[i]})
            declarations.append({'state_index': state, 'parent_row': parent, 'section_count': n,
                'nominal_kV': float(bus[np.flatnonzero(ids == nodes[0])[0], 9]),
                'R_X_B_pu_preserved': br[:, 2:5].sum(axis=0).tolist(),
                'total_nominal_reactor_MVAr_preserved': float(q),
                'original_end_reactor_MVAr_each': float(q / (2 * n)),
                'interior_reactor_MVAr_each': float(q / n)})
    # Read only selected saved qualified endpoints. This is a linear local
    # boundary-value check, not a new coupled annual model solution.
    for month in range(1, 13):
        path = ROOT / f'output/nygrid_2025_ac_loss_revision/validation/annual/released_equivalent_boundary_consistent/monthly/profile_PF_2025_{month:02d}.mat'
        d = loadmat(path, simplify_cells=True, variable_names=['hour_index', 'bus_id', 'VM', 'VA', 'topology_state_index', 'reduction_and_equation_gate', 'loss_allocation_gate'])
        selected = np.flatnonzero(np.isin(d['hour_index'], hours))
        if not len(selected): continue
        sources.append(path); saved_ids = np.asarray(d['bus_id'], int)
        for idx in selected:
            assert d['reduction_and_equation_gate'][idx] and d['loss_allocation_gate'][idx]
            template = static['templates'][int(d['topology_state_index'][idx]) - 1]
            parents = template['userdata']['ac_system']['branch_parent_row']
            for parent in [185, 195]:
                br = template['branch'][parents == parent]
                rec = next(x for x in template['userdata']['ac_sections']['reactor_ledger'] if x['original_branch_row'] == parent)
                nodes = np.unique(br[:, :2]).astype(int); lookup = {x: i for i, x in enumerate(nodes)}
                endpoints = np.array([lookup[rec['from_bus']], lookup[rec['to_bus']]])
                interior = np.setdiff1d(np.arange(len(nodes)), endpoints)
                saved_rows = np.array([np.flatnonzero(saved_ids == x)[0] for x in nodes])
                V = d['VM'][idx, saved_rows] * np.exp(1j * np.deg2rad(d['VA'][idx, saved_rows]))
                reactor = np.zeros(len(nodes))
                for row in br:
                    for x in row[:2].astype(int): reactor[lookup[x]] -= .75 * static['baseMVA'] * row[4] / 2
                for label, delta in [('baseline', np.zeros(len(nodes))), ('distributed_75pct', reactor)]:
                    Y = chain_matrix(br, nodes, delta, static['baseMVA'])
                    trial = V.copy()
                    trial[interior] = -np.linalg.solve(Y[np.ix_(interior, interior)], Y[np.ix_(interior, endpoints)] @ V[endpoints])
                    if label == 'baseline': errors.append(float(np.max(np.abs(trial - V))))
                    for i, bus_id in enumerate(nodes):
                        line_profiles.append({'hour_index': int(d['hour_index'][idx]), 'parent_row': parent,
                            'variant': label, 'bus_id': int(bus_id), 'VM_pu': float(abs(trial[i])),
                            'endpoint_phasor_fixed_to_saved_baseline': bool(i in endpoints)})
    assert max(errors) < 1e-8
    pd.DataFrame(placement).to_csv(OUT / 'reactor_placement_by_state.csv', index=False)
    profile = pd.DataFrame(line_profiles); profile.to_csv(OUT / 'fixed_endpoint_line_profiles.csv', index=False)
    summary = profile.groupby(['parent_row', 'variant']).VM_pu.agg(['min', 'max']).reset_index()
    summary.to_csv(OUT / 'fixed_endpoint_line_summary.csv', index=False)
    coupled_path = OUT / 'selected_coupled_probes.csv'
    coupled = pd.read_csv(coupled_path)
    assert len(coupled) == 30 and coupled.qualified.astype(bool).all()
    assert (coupled.retained_bus_count == 148).all()
    current = coupled[coupled.variant == 'distributed_75pct']
    baseline = coupled[coupled.variant == 'baseline']
    assert len(current) == len(baseline) == len(hours)
    assert set(current.hour_index) == set(hours)
    assert (current[['parent185_max_V_violation', 'parent195_max_V_violation']] <= 1e-7).all().all()
    sources.extend([coupled_path, OUT / 'selected_coupled_probes.mat',
                    ROOT / 'scripts/nygrid_2025_physical_repair/physics/run_185195_probes.m'])
    report = {'passed': True, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Source/RXB-preserving synthetic reactor-placement repair and passive fixed-endpoint line check; coupled probes are separate.',
        'fraction': .75, 'selection_rule': 'At each pi-section end, fixed reactor rating = 0.75 * baseMVA * section B / 2. Sum contributions at shared nodes.',
        'engineering_basis': 'Existing 70-80 percent generic shunt-compensation source supports retained 75 percent total. Distributed placement is an explicit synthetic design extension, not a claim about source-identified stations or installed hardware.',
        'source_url': 'https://cdn.selinc.com/assets/Literature/Publications/Technical%20Papers/6515_ImpactsShunt_NF_20131121_Web2.pdf',
        'additional_manufacturer_context_url': 'https://www.hitachienergy.com/in/en/products-and-solutions/transformers/reactors-and-inductors/shunt-reactors',
        'diagnosis': 'Geometric charging spans 593.6/657.6 km but the old 75 percent reactors occur only at original terminals. Passive uncompensated interior sections retain a large Ferranti rise.',
        'design_fit_to_observed_interface_flows': False, 'voltage_clipped_or_limits_relaxed': False,
        'total_reactor_rating_changed': False, 'branch_RXB_conductor_thermal_metadata_changed': False,
        'passive_elimination_remains_valid': True,
        'fixed_endpoint_baseline_maximum_complex_voltage_reconstruction_error_pu': max(errors),
        'selected_calendar_hours': hours, 'parameters_by_state': declarations,
        'line_only_results': summary.to_dict('records'),
        'selected_coupled_checks': {
            'cases': len(coupled), 'qualified_cases': int(coupled.qualified.astype(bool).sum()),
            'candidate_hours': len(current), 'retained_bus_count_all_cases': 148,
            'parent185_baseline_max_VM': float(baseline.parent185_max_VM.max()),
            'parent185_candidate_max_VM': float(current.parent185_max_VM.max()),
            'parent195_baseline_max_VM': float(baseline.parent195_max_VM.max()),
            'parent195_candidate_max_VM': float(current.parent195_max_VM.max()),
            'all_targeted_bus_voltages_within_unchanged_limits': True,
            'maximum_remaining_global_voltage_violation_pu': float(current.max_voltage_bound_violation_pu.max()),
            'maximum_remaining_global_Q_violation_model_MVAr': float(current.max_Q_bound_violation_MVAr.max()),
            'maximum_regional_import_residual_model_MW': float(current.regional_import_residual_MW.max()),
            'maximum_nodal_P_residual_model_MW': float(current.max_nodal_P_residual_MW.max()),
            'maximum_nodal_Q_residual_model_MVAr': float(current.max_nodal_Q_residual_MVAr.max()),
            'whole_network_operating_feasibility_claimed': False},
        'limitations': ['Line-only profiles hold original endpoint phasors; global response requires a coupled solve.',
            'Intermediate fixed shunts represent a synthetic compensated-line design; physical station existence, bank design and switching/transient behavior remain unverified.',
            'Preserved 75 percent rating is not evidence of annual voltage, reactive or thermal feasibility.'],
        'sources': [record(p) for p in sources],
        'outputs': [record(OUT / p) for p in ['reactor_placement_by_state.csv', 'fixed_endpoint_line_profiles.csv', 'fixed_endpoint_line_summary.csv']]}
    (OUT / 'compensation_design_review.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'fixed_endpoint_max_error_pu': max(errors), 'line_only': summary.to_dict('records')}))


if __name__ == '__main__':
    main()
