"""Independent algebra/source and four-state saved-candidate review.

Uses explicit conductor formulas and source templates, without importing the
repair builders or rerunning a PF. Only writes the new review receipt.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_physical_repair/physics'
VALID = ROOT / 'output/nygrid_2025_physical_repair/validation'


def record(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def same(a, b, tolerance=1e-10):
    a, b = np.asarray(a), np.asarray(b)
    assert a.shape == b.shape
    assert np.allclose(a, b, atol=tolerance, rtol=0, equal_nan=True)
    finite = np.isfinite(a) & np.isfinite(b)
    return float(np.max(np.abs(a[finite] - b[finite]))) if finite.any() else 0.


def main():
    parameter_path = OUT / 'parent41_parameters.json'
    p = json.loads(parameter_path.read_text()); c = p['selected_candidate']; s = p['thermal_segment']
    catalog_path = ROOT / 'output/nygrid_2025_ac_system/engineering/thermal_conductors.csv'
    geometry_path = ROOT / 'output/nygrid_2025_ac_system/engineering/geometry_defaults.csv'
    archived_path = ROOT / 'output/nygrid_2025_conductor_inference/feasible_candidate_realizations.csv'
    catalog = pd.read_csv(catalog_path).set_index('catalog_id'); con = catalog.loc[c['catalog_id']]
    geo = pd.read_csv(geometry_path).set_index('nominal_kv').loc[115]
    archived = pd.read_csv(archived_path)
    archived = archived[(archived.original_parent_row == 41) & (archived.target_basis == 'imported_RX')]
    assert len(archived) == p['candidate_count'] == 32
    first = archived.loc[archived.candidate_rank.idxmin()]
    assert first.catalog_id == c['catalog_id'] == 'PRYSMIAN_ACSS_MALLARD_795_0_30_19'
    for name in ['circuits', 'bundle_count', 'bundle_spacing_m', 'GMD_m', 'length_m', 'derived_B_pu']:
        same(c[name], first[name])
    assert c['circuits'] == 4 and c['bundle_count'] == 1 and c['reference_temperature_C'] == 95
    assert 1 <= c['circuits'] <= int(geo.nparallel_max_default)
    assert str(c['bundle_count']) in str(geo.allowed_bundle_counts).split(';')
    assert geo.gmd_min_m <= c['GMD_m'] <= geo.gmd_max_m
    assert geo.bundle_spacing_min_m <= c['bundle_spacing_m'] <= geo.bundle_spacing_max_m
    assert 5 <= c['length_m'] <= 250000
    assert con.temperature_min_c <= s['temperature_min_c'] <= s['reference_temperature_c'] <= s['temperature_max_c'] <= con.temperature_max_c
    assert con.resistance_supported_min_c <= s['temperature_min_c'] and s['temperature_max_c'] <= con.resistance_supported_max_c
    fields = ['diameter_m', 'gmr_m', 'r_ac25_ohm_per_m', 'r_ac75_ohm_per_m', 'r_ac200_ohm_per_m',
              'heat_capacity_j_m_k', 'emissivity', 'absorptivity', 'reference_temperature_c']
    for field in fields: same(s[field], con[field], 1e-10)
    rsub = float(con.r_ac75_ohm_per_m + (95 - 75) / (200 - 75) * (con.r_ac200_ohm_per_m - con.r_ac75_ohm_per_m))
    omega = 2 * math.pi * 60; zb = 115 ** 2 / 100; length = c['length_m']; nc = 4
    xp = omega * 2e-7 * math.log(c['GMD_m'] / con.gmr_m)
    cp = 2 * math.pi * 8.8541878128e-12 / math.log(c['GMD_m'] / (con.diameter_m / 2))
    calculated = np.array([rsub * length / (nc * zb), xp * length / (nc * zb), nc * omega * cp * length * zb])
    errors = np.abs(calculated - p['repaired_R_X_B']); assert errors.max() < 1e-12
    same(rsub, s['r_ref_ohm_per_m_per_subconductor']); same(xp, s['reactance_ohm_per_m_per_circuit'])
    same(cp, s['capacitance_f_per_m_per_circuit'])
    joule = []
    for current in [1., 500., 2000.]:
        material = 3 * nc * (current / nc) ** 2 * rsub * length / 1e6
        ibase = 100 * 1000 / (math.sqrt(3) * 115)
        electrical = 100 * calculated[0] * (current / ibase) ** 2
        assert abs(material - electrical) < 1e-10
        joule.append({'aggregate_series_current_A': current, 'per_subconductor_current_A': current / nc,
                      'material_loss_MW': material, 'electrical_loss_MW': electrical})
    model_path = ROOT / 'output/nygrid_2025_latest_handoff/model/latest_model.mat'
    model = loadmat(model_path, simplify_cells=True)['model']
    placement_path = OUT / 'reactor_placement_by_state.csv'; placement = pd.read_csv(placement_path)
    profiles = {}; source_files = [parameter_path, catalog_path, geometry_path, archived_path, model_path, placement_path]
    cases = []
    for state in range(1, 5):
        path = VALID / f'candidate_case_state{state}.mat'; source_files.append(path)
        m = loadmat(path, simplify_cells=True)['m']; old = model['templates'][state - 1]
        h = int(m['userdata']['latest_runtime']['hour_index']); part = 0 if h <= 4380 else 1
        if part not in profiles:
            shard = model['profile_shards'][part]; shard_path = model_path.parent / shard['name']
            profiles[part] = loadmat(shard_path, simplify_cells=True)['profiles']; source_files.append(shard_path)
        prof = profiles[part]; hh = h - 1 - part * 4380
        expected_branch = old['branch'].copy(); expected_branch[40, 2:5] = p['repaired_R_X_B']
        if model['axis']['post_dover_full_service'][h - 1]:
            expected_branch[410:412, 9] = prof['dover_bank_phase_shift_deg'][hh]
        branch_error = same(m['branch'], expected_branch)
        expected_bus = old['bus'].copy(); expected_bus[:140, 2] = prof['bus_PD_MW'][hh]; expected_bus[:140, 3] = prof['bus_QD_MVAr'][hh]
        ids = expected_bus[:, 0].astype(int); changes = placement[placement.state_index == state]
        for row in changes.itertuples(): expected_bus[ids == row.bus_id, 5] += row.net_bus_BS_change_MVAr_at1pu
        external = np.asarray(model['external']['generator_mask'], bool)
        expected_gen = old['gen'].copy(); expected_gen[:, 1] = prof['generator_PG_MW'][hh]
        expected_gen[:, 8] = prof['generator_Pmax_MW'][hh]; expected_gen[:, 9] = prof['generator_Pmin_MW'][hh]
        expected_gen[external, 8] = expected_gen[external, 1]; expected_gen[external, 9] = expected_gen[external, 1]
        expected_gen[:, 7] = (expected_gen[:, 8] > 0) | (expected_gen[:, 9] < 0)
        expected_bus[:, 1] = 1; expected_bus[np.isin(ids, expected_gen[expected_gen[:, 7] > 0, 0]), 1] = 2
        expected_bus[ids == model['axis']['reference_bus'][h - 1], 1] = 3
        pcap = np.max(np.abs(expected_gen[:, 8:10]), axis=1); cap = pcap.copy(); cap[external] = model['external']['capability_proxy_MW']
        qcap = cap * math.tan(math.acos(.95)); qcap[external] = np.sqrt(np.maximum(0, (cap[external] / .95) ** 2 - expected_gen[external, 1] ** 2))
        qcap[expected_gen[:, 7] == 0] = 0
        expected_gen[:, 2] = 0; expected_gen[:, 3] = qcap; expected_gen[:, 4] = -qcap
        generator_rows = np.array([np.flatnonzero(ids == x)[0] for x in expected_gen[:, 0]])
        expected_gen[:, 5] = expected_bus[generator_rows, 7]; expected_gen[:, 6] = np.maximum(cap / .95, 1)
        bus_error = same(m['bus'], expected_bus); gen_error = same(m['gen'], expected_gen)
        dc = old['dcline'].copy(); target = prof['fixed_transfer_PF_MW'][hh]
        dc[:, 3] = target; dc[:, 4] = target; dc[:, 9] = target; dc[:, 10] = target; dc[:, 5:7] = 0
        dc_error = same(m['dcline'], dc)
        acsec = m['userdata']['ac_sections']; oldsec = old['userdata']['ac_sections']
        segment = next(x for x in acsec['thermal_segments'] if x['branch_row'] == 41)
        for key, value in s.items():
            if isinstance(value, str): assert segment[key] == value
            else: same(segment[key], value)
        assert segment['section_count'] == 1 and segment['original_branch_row'] == 41
        same(segment['corridor_segment_length_m'], length)
        same(acsec['terminal_current_limit_A'], oldsec['terminal_current_limit_A'])
        same(acsec['terminal_current_limit_A'][40], [2000, 2000])
        bs = np.zeros(len(ids)); bs[:len(oldsec['reactor_BS_delta'])] = oldsec['reactor_BS_delta']
        for row in changes.itertuples(): bs[ids == row.bus_id] += row.net_bus_BS_change_MVAr_at1pu
        same(acsec['reactor_BS_delta_all_buses'], bs); same(acsec['reactor_BS_bus_ids'], ids)
        same(acsec['reactor_BS_delta'], bs[:int(acsec['original_bus_count'])])
        for parent in [185, 195]:
            newr = next(x for x in acsec['reactor_ledger'] if x['original_branch_row'] == parent)
            oldr = next(x for x in oldsec['reactor_ledger'] if x['original_branch_row'] == parent)
            same(newr['applied_total_reactor_mvar_at1pu'], oldr['applied_total_reactor_mvar_at1pu'])
            assert abs(sum(newr['distributed_bus_BS_delta_mvar']) + newr['applied_total_reactor_mvar_at1pu']) < 1e-8
        ledger_path = VALID / f'thermal_parent_ledger_state{state}.csv'; source_files.append(ledger_path)
        ledger = pd.read_csv(ledger_path); l41 = ledger[ledger.original_parent_row == 41].iloc[0]
        assert l41.research_screen_eligible and l41.forward_R_matches_current_case and l41.forward_X_matches_current_case and l41.geometric_B_matches_current_case
        cases.append({'state_index': state, 'hour_index': h, 'bus_count': len(ids), 'branch_count': len(expected_branch),
                      'maximum_branch_error_pu_or_native_units': branch_error, 'maximum_bus_error_native_units': bus_error,
                      'maximum_source_generator_error_native_units': gen_error, 'maximum_fixed_transfer_error_native_units': dc_error,
                      'parent41_runtime_thermal_segment_matches_parameter_record': True, 'aggregate_apparatus_ceiling_A_each_terminal': 2000})
    validation_path = VALID / 'targeted_candidate_receipt.json'; checks_path = VALID / 'targeted_candidate_checks.csv'
    validation = json.loads(validation_path.read_text()); checks = pd.read_csv(checks_path)
    assert validation['passed'] and validation['qualified_hours'] == len(checks) == 17
    assert set(checks.state_index) == {1, 2, 3, 4} and checks.qualified.astype(bool).all()
    assert (checks[['parent185_voltage_violation_pu', 'parent195_voltage_violation_pu']] <= 1e-7).all().all()
    assert validation['detailed_vs_compact_voltage_error_pu'] < 1e-8 and validation['detailed_vs_compact_flow_error_model_MW_MVAr'] < 1e-5
    assert not checks.global_operating_qualified.astype(bool).any()
    source_files.extend([validation_path, checks_path, Path(__file__),
        ROOT / 'scripts/nygrid_2025_physical_repair/prepare_parent41.py',
        ROOT / 'scripts/nygrid_2025_physical_repair/core/nyrepair_apply_parent41.m',
        ROOT / 'scripts/nygrid_2025_physical_repair/core/nyrepair_apply_case.m',
        ROOT / 'scripts/nygrid_2025_physical_repair/physics/nyrepair_apply_185195.m'])
    report = {'passed': True, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Independent formula, catalog, bound, source-profile and four-state saved-candidate validation plus review of completed 17-hour coupled checks. No repair helper imported and no new PF run.',
        'parent41': {'archived_rank1_match': True, 'catalog_id': c['catalog_id'], 'reference_temperature_C': 95,
            'circuits': 4, 'bundle_count': 1, 'length_m': length, 'GMD_m': c['GMD_m'],
            'manual_forward_R_X_B_pu': calculated.tolist(), 'maximum_forward_error_pu': float(errors.max()),
            'catalog_temperature_geometry_and_length_bounds_passed': True, 'material_electrical_Joule_checks': joule,
            'geometric_B_not_equal_to_imported_B': True, 'aggregate_apparatus_ceiling_preserved_A': 2000},
        'four_state_candidate_checks': cases,
        'targeted_checks': {'qualified_hours': 17, 'parent185_max_VM_pu': float(checks.parent185_max_VM.max()),
            'parent195_max_VM_pu': float(checks.parent195_max_VM.max()),
            'maximum_nodal_P_residual_model_MW': float(checks.nodal_P_residual_model_MW.max()),
            'maximum_nodal_Q_residual_model_MVAr': float(checks.nodal_Q_residual_model_MVAr.max()),
            'maximum_recovered_current_error_A': float(checks.recovered_current_error_A.max()),
            'detailed_vs_compact_voltage_error_pu': validation['detailed_vs_compact_voltage_error_pu'],
            'detailed_vs_compact_flow_error_model_MW_MVAr': validation['detailed_vs_compact_flow_error_model_MW_MVAr']},
        'limitations': ['No installed conductor, route or intermediate reactor-station identity is certified.',
            'The four-circuit realization is a selected synthetic hypothesis under declared R/X-conditioned catalog priors; parallel mutual coupling is not modeled.',
            'The conservative aggregate 2000A apparatus limit is independent of conductor multiplicity and does not establish thermal feasibility.',
            'This is targeted validation; annual results and final compiled handoff metadata require their separate checks.',
            'The authoring thermal ledger retains the historical registry parameter_basis; the final compiled registry must carry the new declared parent41 basis.',
            'All 17 sampled hours retain other global operating-limit violations.'],
        'sources': [record(path) for path in dict.fromkeys(source_files)]}
    target = OUT / 'independent_candidate_review.json'
    target.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'forward_error_pu': float(errors.max()), 'states': len(cases),
                      'qualified_targeted_hours': len(checks), 'output': target.relative_to(ROOT).as_posix()}))


if __name__ == '__main__':
    main()
