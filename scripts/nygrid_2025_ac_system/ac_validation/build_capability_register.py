"""Audit finite generator assumptions independently of OPF convergence.

Reads source operating inputs and the existing generator identity register;
never reads internal-interface observations or changes an active-power input.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_ac_system/ac_validation'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    source = ROOT / 'output/nygrid_2025_inputs/model/operating_inputs.mat'
    register_path = ROOT / 'output/nygrid_2025_dispatch/dispatch/model_generator_register.csv'
    d = loadmat(source, simplify_cells=True)
    parent = d['base_case']
    pg = np.asarray(parent['gen'])
    ext_rows = np.flatnonzero(np.asarray(parent['genfuel']) == 'Import')
    reg = pd.read_csv(register_path, keep_default_na=False)
    ext = reg.loc[reg['role'].eq('fixed_external')].copy()
    assert len(ext) == 28 and len(ext_rows) == 28
    parent_ids = pd.to_numeric(ext['parent_gen_row']).to_numpy(int)
    assert np.array_equal(parent_ids, ext_rows + 1)
    assert np.array_equal(ext['bus_id'].to_numpy(int), pg[ext_rows, 0])
    cap = np.max(abs(pg[ext_rows, 8:10]), axis=1)
    assert np.isfinite(cap).all() and (cap > 0).all()
    posted = np.asarray(d['external_input_pg'])[:, ext_rows]
    abs_peak = np.nanmax(abs(posted), axis=0)
    assumed_s = cap/.95
    previous_rectangular_qcap = cap * np.tan(np.arccos(.95))
    qcap_hourly = np.sqrt(assumed_s[None,:]**2-posted**2)
    assert np.all(abs_peak <= cap)
    ext['parent_generator_row'] = parent_ids
    ext['parent_Pmax_model_MW'] = pg[ext_rows, 8]
    ext['parent_Pmin_model_MW'] = pg[ext_rows, 9]
    ext['finite_capacity_reference_model_MW'] = cap
    ext['assumed_power_factor'] = .95
    ext['previous_individual_machine_PF_rectangle_Qmax_MVAr'] = previous_rectangular_qcap
    ext['minimum_2025_fixed_P_circle_slice_Qmax_MVAr_if_online'] = np.nanmin(qcap_hourly,axis=0)
    ext['maximum_2025_fixed_P_circle_slice_Qmax_MVAr_if_online'] = np.nanmax(qcap_hourly,axis=0)
    ext['assumed_S_proxy_MVA'] = assumed_s
    ext['maximum_absolute_2025_fixed_P_model_MW'] = abs_peak
    ext['maximum_P_to_capacity_ratio'] = abs_peak/cap
    ext['finite_source_hour_count'] = np.isfinite(posted).sum(axis=0)
    ext['zero_fixed_P_hour_count'] = (posted == 0).sum(axis=0)
    ext['capacity_basis'] = 'immutable_historical_synthetic_parent_Pmax_Pmin_no_gamma_rescaling'
    ext['physical_nameplate_verified'] = False
    ext['existing_P_schedule_changed'] = False
    ext['offline_Q_support_allowed'] = False
    OUT.mkdir(parents=True, exist_ok=True)
    mapping = OUT/'external_capability_mapping.csv'
    ext.to_csv(mapping, index=False)
    policy = {
        'passed': True,
        'modeltype': 'bounded_synthetic_AC',
        'baseMVA': 100,
        'power_scale': 'synthetic_existing_gamma_scaled_injections',
        'impedance_rescaled_to_unscale_power': False,
        'current_divided_by_gamma': False,
        'native_Q_policy': 'Online Qmin/Qmax = plus/minus hourly max(abs(Pmin),abs(Pmax))*tan(acos(0.95)).',
        'external_Q_policy': 'Regional boundary equivalent Qmin/Qmax = plus/minus sqrt(unchanged_assumed_S^2-fixed_P^2) if admitted; fixed external P schedule remains unchanged.',
        'external_class_is_individual_synchronous_generator': False,
        'external_assumed_S_enlarged_when_Q_policy_changed': False,
        'external_previous_PF_rectangle_trial_retained_as_diagnostic': True,
        'external_capacity_policy': 'max(abs(parent Pmax),abs(parent Pmin)) on existing model base; no gamma multiplier; not an observed nameplate.',
        'offline_Q_policy': 'Existing GEN_STATUS=0 implies Qmin=Qmax=0; no assumed offline STATCOM service.',
        'GEN_STATUS_is_DC_availability_admission_not_observed_commitment': True,
        'admitted_zero_PG_rows_may_provide_Q_in_the_synthetic_model': True,
        'physical_unit_commitment_or_generator_D_curves_validated': False,
        'assumed_generator_S_proxy_MVA': 'Capability reference /0.95. Native rectangular box lies inside this circle; external boundary equivalents use the full fixed-P circle slice at the same S. Reject fixed P above S.',
        'voltage_limits_pu': [.95,1.05],
        'active_power_objective': 'sum((PG-PG_DC_prior)^2/max(hourly max(abs(Pmin),abs(Pmax)),1))',
        'reactive_power_objective': 'sum(0.01*QG^2/max(Qcap,1))',
        'objective_is_economic_cost': False,
        'fixed_external_P_refers_to_generator_injections_not_loss_corrected_regional_AC_interchange': True,
        'external_fixed_P_source_finite_rows_checked': int(np.isfinite(posted).sum()),
        'external_fixed_P_source_rows_above_capacity': int(np.sum(abs(posted)>cap)),
        'maximum_external_fixed_P_to_parent_capacity': float(np.max(abs_peak/cap)),
        'source_external_Q_limits_999_and_9999_used': False,
        'reactive_nameplate_capability_verified': False,
        'historical_AC_state_reconstructed': False,
        'annual_ACOPF_performed': False,
        'internal_interface_observations_read': False,
        'assumptions_sized_from_solver_residuals': False,
        'sources': [{'path':str(p.relative_to(ROOT)), 'sha256':sha(p)} for p in [source, register_path]],
        'outputs': [{'path':str(mapping.relative_to(ROOT)), 'sha256':sha(mapping)}],
        'script_sha256':sha(__file__),
    }
    (OUT/'generator_capability_policy.json').write_text(json.dumps(policy, indent=2)+'\n')
    print(json.dumps({'passed':True,'external_rows':len(ext),'maximum_P_capacity_ratio':policy['maximum_external_fixed_P_to_parent_capacity']}))


if __name__ == '__main__':
    main()
