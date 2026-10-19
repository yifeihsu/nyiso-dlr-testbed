"""Qualified Dover PST engineering model; no factory-impedance claim or PF run.

Orientation is NY/Y17 from-port to CT/398 to-port. Positive physical advance
means the load-side no-load voltage leads the source. MATPOWER SHIFT has the
opposite sign. The public +/-40 degree range is interpreted as a no-load
reference ONLY as a stated assumption; SA2510 does not explicitly label it so.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_dover_parameters/engineering'


def require(condition,message):
    if not condition:raise ValueError(message)


def conditional_reactance(delta_deg=8.,receiving_v_pu=1.,load_mva_pu=1.,power_factor=1.,
                          reactive_sign=1,r_pu=0.):
    """Invert arg(V + (R+jX)*conj(S/V)) under explicitly selected conditions.

    X = [V^2*tan(beta) + R*(P*tan(beta)+Q)] / [P-Q*tan(beta)].
    At R=0, V=1, S=1, unity PF, this is tan(beta), not sin(beta).
    """
    require(all(math.isfinite(float(x)) for x in [delta_deg,receiving_v_pu,load_mva_pu,power_factor,r_pu]),'Nonfinite phasor condition')
    require(0<delta_deg<90 and receiving_v_pu>0 and load_mva_pu>0 and 0<power_factor<=1
            and reactive_sign in [-1,1] and r_pu>=0,'Invalid phasor condition')
    p=load_mva_pu*power_factor
    q=reactive_sign*load_mva_pu*math.sqrt(max(0.,1-power_factor**2))
    tangent=math.tan(math.radians(delta_deg))
    denominator=p-q*tangent
    require(denominator>0,'No passive positive-X solution under the declared load condition')
    x=(receiving_v_pu**2*tangent+r_pu*(p*tangent+q))/denominator
    require(x>0,'Nonpositive inferred reactance')
    return x


def load_phasor(r_pu,x_pu,receiving_v_pu=1.,load_mva_pu=1.,power_factor=1.,reactive_sign=1):
    p=load_mva_pu*power_factor
    q=reactive_sign*load_mva_pu*math.sqrt(max(0.,1-power_factor**2))
    vl=complex(receiving_v_pu,0.)
    current=np.conj(complex(p,q)/vl)
    internal=vl+complex(r_pu,x_pu)*current
    return dict(receiving_voltage=vl,load_current=current,internal_ideal_voltage=internal,
                leakage_load_angle_deg=math.degrees(np.angle(internal/vl)),
                internal_voltage_magnitude_pu=abs(internal))


def change_base(z_pu,from_mva=750.,from_kv=345.,to_mva=100.,to_kv=345.):
    require(all(math.isfinite(float(x)) and x>0 for x in [from_mva,from_kv,to_mva,to_kv]),'Invalid impedance base')
    return z_pu*(to_mva/from_mva)*(from_kv/to_kv)**2


def pst_y(r_pu,x_pu,shift_deg=0.,tap_magnitude=1.):
    """Power-conserving ideal complex tap plus passive series impedance."""
    require(all(math.isfinite(float(x)) for x in [r_pu,x_pu,shift_deg,tap_magnitude])
            and r_pu>=0 and x_pu>0 and tap_magnitude>0,'Invalid passive PST parameters')
    tap=tap_magnitude*np.exp(1j*math.radians(shift_deg))
    incidence=np.array([[1/tap,-1]],complex)
    return incidence.conj().T @ incidence / complex(r_pu,x_pu)


def port_powers(v_from,v_to,r_pu,x_pu,shift_deg=0.,tap_magnitude=1.,base_mva=100.):
    volts=np.array([v_from,v_to],complex)
    current=pst_y(r_pu,x_pu,shift_deg,tap_magnitude)@volts
    return base_mva*volts*np.conj(current)


def dc_power(theta_from_deg,theta_to_deg,shift_deg,x_pu,base_mva=100.,tap_magnitude=1.):
    require(x_pu>0 and base_mva>0 and tap_magnitude>0,'Invalid DC branch coefficient')
    return base_mva/(x_pu*tap_magnitude)*np.deg2rad(np.asarray(theta_from_deg)-np.asarray(theta_to_deg)-np.asarray(shift_deg))


def dc_shift_for_target(theta_from_deg,theta_to_deg,target_model_mw,x_pu,base_mva=100.,tap_magnitude=1.):
    require(x_pu>0 and base_mva>0 and tap_magnitude>0,'Invalid DC branch coefficient')
    return np.asarray(theta_from_deg)-np.asarray(theta_to_deg)-np.rad2deg(np.asarray(target_model_mw)*x_pu*tap_magnitude/base_mva)


def parallel_dc_equivalent(x_pu,shift_deg,base_mva=100.):
    x=np.asarray(x_pu,float);phase=np.asarray(shift_deg,float)
    require(x.ndim==1 and len(x)>0 and x.shape==phase.shape and np.isfinite(x).all()
            and (x>0).all() and np.isfinite(phase).all(),'Invalid parallel-bank data')
    weights=base_mva/x
    return dict(x_pu=float(base_mva/weights.sum()),shift_deg=float(np.dot(weights,phase)/weights.sum()),
                active_banks=len(x),same_phase_equal_X_shares_equally=bool(np.all(x==x[0]) and np.all(phase==phase[0])))


def necessary_p_screen(model_mw,bank_ratings_mva,gamma):
    powers=np.asarray(model_mw,float);ratings=np.asarray(bank_ratings_mva,float)
    require(gamma>0 and np.isfinite(powers).all() and np.isfinite(ratings).all()
            and ratings.shape==powers.shape and np.all(ratings>0),'Invalid bank capacity screen')
    return np.abs(powers)<=ratings*gamma+1e-9


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def build_basis():
    OUT.mkdir(parents=True,exist_ok=True)
    source_receipts=json.loads((OUT/'source_receipts.json').read_text())
    for row in source_receipts:
        if row['retrieval_status']=='downloaded':require(sha(ROOT/row['path'])==row['sha256'],'Changed engineering source '+row['source_id'])
    x750=conditional_reactance()
    x100=change_base(x750)
    calibration=load_phasor(0,x750)
    regimes=[]
    for v in [.95,1.,1.05]:
        for pf,sign in [(1.,1),(.95,1),(.95,-1),(.9,1),(.9,-1)]:
            x=conditional_reactance(receiving_v_pu=v,power_factor=pf,reactive_sign=sign)
            regimes.append(dict(receiving_v_pu=v,load_mva_pu=1.,power_factor=pf,reactive_sign=sign,
                x_pu_on_750MVA=x,x_pu_on_100MVA=change_base(x),
                reconstructed_angle_drop_deg=load_phasor(0,x,v,1.,pf,sign)['leakage_load_angle_deg'],
                interpretation='illustrative_condition_grid_not_confidence_interval_or_factory_test'))
    sensitivity=[]
    for name,multiplier in [('x_low',1/1.5),('x_nominal',1.),('x_high',1.5)]:
        each=x100*multiplier
        sensitivity.append(dict(scenario=name,impedance_multiplier=multiplier,per_bank_model_r_pu=0.,
            per_bank_x_pu_100MVA=each,two_equal_parallel_x_pu_100MVA=each/2,
            per_bank_x_ohm=each*345**2/100,per_bank_selected_nameplate_mva=750.,
            phase_load_drop_at_reference_condition_deg=math.degrees(math.atan(x750*multiplier)),
            R_physically_known=False,neutral_factory_X_known=False,
            scope='declared_generic_tap_impedance_sensitivity_not_Dover_test_data_or_confidence_bounds'))
    alternatives=[dict(method='receiving_V1_I1_unityPF',x_pu_750=x750,receiving_v_pu=1.,internal_v_pu=1/math.cos(math.radians(8)),
                       caveat='nominal conditional model;source magnitude can be sec8 under unity ideal tap'),
                  dict(method='internal_E1_I1_unityPF',x_pu_750=math.sin(math.radians(8)),receiving_v_pu=math.cos(math.radians(8)),internal_v_pu=1.,
                       caveat='different voltage/loading condition;receiving apparent power is cos8 pu,not1pu'),
                  dict(method='both_terminal_magnitudes1_I1',x_pu_750=2*math.sin(math.radians(4)),receiving_v_pu=1.,internal_v_pu=1.,
                       caveat='load power factor cos4 leading;notunityPF'),
                  dict(method='small_angle_DC_approximation',x_pu_750=math.radians(8),receiving_v_pu=1.,internal_v_pu=1.,
                       caveat='linearizedangle approximation;notexactACphasorcalibration')]
    public_project=ROOT/'output/nygrid_2025_line_parameters/sources/projects/NYTransco_SA2510_2023.pdf'
    basis=dict(status='qualified_public_only_engineering_estimate_ready_for_explicit_application',
        source_nameplate=dict(per_bank_kv=345,per_bank_cooling_nameplate_mva=[450,600,750],normal_parallel_banks=2,detached_spares=1,
            published_phase_range_degree=40,maximum_advance_at_750MVA_degree=32,
            phase40_explicitly_labeled_no_load_in_SA2510=False,actual_factory_R_X_and_tap_curve_publicly_established=False),
        selected_model=dict(r_pu_on100MVA=0.,physical_resistance_ohm=None,
            R_policy='lossless_DC_model_placeholder;not_claimed_zero_physical_winding_loss',
            x_pu_on750MVA=x750,x_pu_on100MVA=x100,x_ohm=x750*345**2/750,
            two_parallel_equal_phase_x_pu_on100MVA=x100/2,
            design_range_assumed_no_load_deg=40.,reference_loaded_advance_deg=32.,reference_angle_drop_deg=8.,
            calibration_receiving_voltage_pu=1.,calibration_load_MVA_pu=1.,calibration_load_power_factor=1.,
            calibration_internal_voltage_pu=calibration['internal_voltage_magnitude_pu'],
            constant_leakage_is_model_assumption_not_factory_neutral_value=True,
            tap_magnitude=1.,symmetrical_unity_no_load_voltage_ratio_is_assumed=True,
            default_unconditioned_phase_shift_deg=0.,default_phase_is_not_measured_operating_state=True),
        formula=dict(inference='X=[V^2*tan(beta)+R*(P*tan(beta)+Q)]/[P-Q*tan(beta)]',
            load_phasor='E=V+(R+jX)*conj(S/V); beta=arg(E/V)',
            forward_orientation='NY/Y17 to CT/398',positive_physical_advance_definition='load-side no-load voltage leads source',
            MATPOWER_shift_sign='SHIFT=-physical_advance for the declared from/to orientation',
            P34_target_sign='positive rawP34 is CT-to-NY;forward_model_target=-gamma*rawP34',
            inferred_DC_shift='thetaNY-thetaCT-target_model_MW*X_pu*tap/baseMVA [radians]',
            parallel_equivalent='inverse sum inverse X for equal unit tap; phase weighted by inverse X',
            model_phase_not_telemetry='gamma-scaled coarse-network inferred phase is not a measured physical tap or an independently verified hardware phase'),
        operating_scope=dict(normal_bypass_open=True,actual_breaker_and_tap_states_measured=False,
            normal_banks_in_parallel=True,no_three_unit_capacity_from_detached_spare=True,
            actual_Q_cooling_tap_steps_and_equipment_limits_unresolved=True,
            necessary_P_only_screen='abs(P_model_i)<=selected_rating_MVA_i*gamma individually;aggregate limit alone is insufficient',
            external_P34_flow_conditioning_allowed_after_verified_cutover=True,internal_P32_observations_used=False),
        sensitivity_policy='1/1.5,1,1.5 are declared stress factors informed by generic correction-table practice;notDoverconfidencebounds;onlynominalmatchesreference8degreeassumptions',
        evidence_limits=['SA2510 phase-range interpretation is conditional','unknown zero-phase versus maximum-phase leakage relation',
                         'no public load-loss or winding-resistance test found','no technology-specific asymmetrical/symmetrical construction certificate found',
                         'P34 measures reported active transfer,notphysicaltap','AC apparent-power/current/cooling feasibility is not established by a DC MW screen'],
        sources=[dict(path=str(public_project.relative_to(ROOT)).replace('\\','/'),sha256=sha(public_project),pdf_page=44,printed_page=7),
                 dict(path=str((OUT/'source_receipts.json').relative_to(ROOT)).replace('\\','/'),sha256=sha(OUT/'source_receipts.json'))])
    (OUT/'conditional_impedance_basis.json').write_text(json.dumps(basis,indent=2)+'\n')
    pd.DataFrame(regimes).to_csv(OUT/'load_voltage_power_factor_condition_grid.csv',index=False,lineterminator='\n')
    pd.DataFrame(alternatives).to_csv(OUT/'angle_drop_interpretation_comparison.csv',index=False,lineterminator='\n')
    pd.DataFrame(sensitivity).to_csv(OUT/'PST_parameter_scenarios.csv',index=False,lineterminator='\n')
    families={row['scenario']:dict(bank_r_pu=0.,bank_x_pu100=row['per_bank_x_pu_100MVA'],
        bank_rated_mva=750.,impedance_multiplier=row['impedance_multiplier'],
        pair_parallel_x_pu100=row['two_equal_parallel_x_pu_100MVA'],
        R_unknown_physically=True,R_model_is_lossless_DC_placeholder=True,
        phase_range_deg=[-40.,40.],phase_range_is_scenario_screen_not_tap_telemetry_qualification=True,
        rating_scope='selected_maximum_cooling_nameplate;necessary_P_only_screen_not_complete_thermal_feasibility') for row in sensitivity}
    require(abs(calibration['leakage_load_angle_deg']-8)<1e-12 and abs(x100*345**2/100-x750*345**2/750)<1e-12,
            'Reference phasor/base consistency failed')
    register=dict(passed=True,qualification='conditional_public_only_engineering_model_not_factory_test',
        nominal_family='x_nominal',normal_active_parallel_banks=2,detached_spare_in_network=False,
        families=families,referencepoint=basis['selected_model'],assumptions=basis['evidence_limits'],
        source_phase_range40_is_explicit_no_load_label=False,
        nonlinear_tap_impedance_curve_established=False,internal_interface_observations_used=False,
        sources=basis['sources'],engineering_code_sha256=sha(Path(__file__)))
    (OUT/'PAR_estimates.json').write_text(json.dumps(register,indent=2)+'\n')
    pd.DataFrame([dict(family=name,**record) for name,record in families.items()]).to_csv(OUT/'PAR_estimates.csv',index=False,lineterminator='\n')
    print(json.dumps(basis['selected_model'],indent=2))
    return basis


if __name__=='__main__':build_basis()
