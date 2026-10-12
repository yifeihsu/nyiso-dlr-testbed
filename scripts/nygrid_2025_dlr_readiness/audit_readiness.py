"""Read-only DLR capability audit of the delivered 148/192-bus Dover model.

This writes an assessment, not a DLR operating case. It never promotes old
compact-case thermal runs, changes branch parameters, or invokes a refit.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import subprocess

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_dlr_readiness'
DOVER = ROOT / 'output/nygrid_2025_dover_parameters'
LINE = ROOT / 'output/nygrid_2025_line_parameters'
LITE = ROOT / 'System Matpower Format/NY_Lite'
BASELINE_HEAD = '797049c152073c0cdb800147ee2d11267d556cd6'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def rel(path):
    return Path(path).relative_to(ROOT).as_posix()


def dump(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def source_line(path, needle):
    lines = Path(path).read_text(encoding='utf-8-sig').splitlines()
    matches = [i for i, line in enumerate(lines, 1) if needle in line]
    require(bool(matches), f'Source evidence moved or disappeared: {path}: {needle}')
    return f'{rel(path)}:{matches[0]}'


def verify():
    """Read a sealed assessment without regenerating timestamps or outputs."""
    path=OUT/'readiness_assessment.json'
    require(path.is_file(),'No sealed readiness assessment; run the audit first')
    summary=json.loads(path.read_text())
    require(summary['assessment_completed'] and summary['loader']=='System Matpower Format/npcc_nygrid_2025_dover_dc.m',
            'Assessment scope or completion state changed')
    records=summary['dependencies']+summary['outputs']
    kernel=json.loads((OUT/'fresh_reusable_component_audit.json').read_text())
    records+=kernel['dependencies']
    for item in records:
        p=Path(item['path']);p=p if p.is_absolute() else ROOT/p
        require(p.is_file() and sha(p)==item['sha256'],'Changed assessment dependency or output: '+item['path'])
    print(json.dumps(dict(sealed_assessment_verified=True,files_verified=len(records),
        audited_checkout_commit=summary['audited_checkout_commit'],
        physical_DLR_readiness_passed=summary['physical_DLR_readiness_passed'],
        mode='read_only_no_receipt_or_output_regeneration'),indent=2))
    return summary


def branch_audit(payload):
    rows = []
    for case_name, keys_name in [('slim_case', 'slim_branch_keys'), ('full_case', 'full_branch_keys')]:
        case = payload[case_name]
        keys = np.asarray(payload[keys_name]).astype(str)
        kv = dict(zip(case['bus'][:, 0].astype(int), case['bus'][:, 9]))
        require(len(keys) == len(case['branch']) and len(set(keys)) == len(keys), 'Branch keys changed')
        for i, (key, br) in enumerate(zip(keys, case['branch']), 1):
            active = bool(br[10]) and i != 211  # six-transfer runtime substitution
            volts = kv[int(br[0])] != kv[int(br[1])]
            if not active:
                status = 'inactive_provenance_record_not_thermalized'
            elif key.startswith('DC_EQ:'):
                status = 'excluded_DC_Schur_connection_not_a_physical_conductor'
            elif key.startswith('RCC:CABLE:'):
                status = 'excluded_underground_cable_needs_separate_cable_thermal_model'
            elif key.startswith('DOVER:PAR:'):
                status = 'excluded_PAR_needs_equipment_current_Q_cooling_limits'
            elif volts or br[8] not in [0, 1] or br[9] != 0:
                status = 'excluded_voltage_changing_or_control_equipment'
            elif key == 'CV:PV_CV_F84':
                status = 'F84_design_based_thermal_candidate_adapter_and_weather_not_built'
            elif key in ['DOVER:CV_DOVER_Y17', 'DOVER:RESOLVED_398']:
                status = 'Dover_line_section_candidate_adapter_weather_and_facility_limits_missing'
            else:
                status = 'unqualified_electrical_record_overhead_identity_conductor_and_route_unresolved'
            rows.append(dict(representation=case_name, branch_row=i, branch_key=key,
                from_bus=int(br[0]), to_bus=int(br[1]), from_kv=float(kv[int(br[0])]), to_kv=float(kv[int(br[1])]),
                runtime_active=active, voltage_changing=bool(volts), inherited_rate_a_mva=float(br[5]),
                thermal_readiness=status, current_thermal_runtime_bound=False, physical_DLR_ready=False))
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    require(subprocess.run(['git', 'merge-base', '--is-ancestor', BASELINE_HEAD, head], cwd=ROOT).returncode == 0,
            'Current checkout does not descend from the requested Dover delivery')
    kernel_file = OUT / 'fresh_reusable_component_audit.json'
    kernel = json.loads(kernel_file.read_text())
    require(kernel['fresh_reusable_component_tests_passed'] and kernel['component_tests'] == 25,
            'Run the focused MATLAB component audit first')
    for item in kernel['dependencies']:
        require(sha(item['path']) == item['sha256'], 'Reusable component or inspected loader changed: ' + item['path'])
    require(kernel['buses'] == 148 and kernel['fixed_transfer_records'] == 6
            and kernel['old_plain_helper_would_remove_six_transfer_records'], 'Delivered operating contract differs')
    netpath = DOVER / 'network/x_nominal.mat'
    payload = loadmat(netpath, simplify_cells=True)
    require(payload['full_case']['bus'].shape == (192, 13) and payload['slim_case']['branch'].shape == (274, 13),
            'Wrong current model family')
    register_path = ROOT / 'output/nygrid_2025_slim/network/branch_register.csv'
    register = pd.read_csv(register_path)
    require(len(register) == 274 and not register.thermal_dlr_eligible.astype(str).str.lower().isin(['true', '1']).any(),
            'Thermal eligibility changed; inspect the new evidence')
    require(int((register.role == 'passive_DC_Schur_equivalent').sum()) == 30, 'Schur identity set changed')
    replay_path = DOVER / 'replay/replay_receipt.json'
    replay = json.loads(replay_path.read_text())
    require(replay['passed'] and replay['fixed_annual_cohort'] == 8651 and replay['post_cutover_source_hours'] == 287,
            'Current operating cohort changed')
    previous_validation = DOVER / 'validation/matlab_validation.json'
    validation = json.loads(previous_validation.read_text())
    require(validation['passed'] and validation['fresh_full192_DC_solves'] == 49
            and validation['fresh_slim148_DC_solves'] == 49, 'Missing delivered electrical validation')
    contract_path = ROOT / 'output/nygrid_2025_dispatch/dispatch/contract.json'
    contract = json.loads(contract_path.read_text())
    require(not contract['ac_feasibility_validated'] and not contract['physical_branch_thermal_feasibility_validated'],
            'Dispatch scope changed')
    physical = branch_audit(payload)
    physical.to_csv(OUT / 'branch_readiness.csv', index=False, lineterminator='\n')
    capability = [
        ('DC topology and fixed-input control sensitivity', 'ready_now', True,
         '148-bus delivered loader and exact 192-bus DC recovery; fixed generation and six transfers; source cohort explicit.',
         'Claims concern the declared DC model and assumed controls; no measured circuit-current or thermal-capacity claim.'),
        ('Synthetic rating-threshold or congestion screening', 'platform_ready_adapter_not_delivered', False,
         'Recovered physical-branch MW can be compared with explicitly assumed time-varying limits after a small adapter.',
         'Current saved replay is unconstrained by line thermal limits; changing a rating alone does not redispatch power.'),
        ('F84 design-based DC DLR exposure study', 'narrow_next_step_not_current_runnable_experiment', False,
         'Full branch391 and slim branch244; 14.6mi source design, twin795 Mallard ACSS, 95C normal-temperature anchor.',
         'Bind ACSS thermal properties, route weather, gamma/current conversion and thermal time integration first; use DC current proxy labels.'),
        ('Dover overhead section DLR sensitivity', 'line_data_available_adapter_and_section_weather_missing', False,
         'Y17 full393 and resolved398 full413 separated from PAR411/412; 398 includes NY twin795 and CT single2156 sections.',
         'Use the same series phase current in both sections, different per-subconductor currents, and the limiting section; PAR capacity stays separate.'),
        ('Historical weather-driven physical-line DLR backtest', 'not_ready', False,
         'No route-bound weather time series, selected critical spans, or current-model thermal replay was found in the audited namespaces.',
         'A modeled weather backtest can use public weather and explicit engineering assumptions; calling it measured asset performance needs field validation.'),
        ('DLR redispatch and curtailment benefit experiment', 'not_integrated', False,
         'Native power boxes and declared generation-prior objective are available; no current DLR-constrained dispatch routine exists.',
         'Add explicit physical-branch inequalities, preserve six transfers and bounded PAR policy, and keep cost/ramp/storage assumptions visible.'),
        ('AC electrothermal operating-feasibility study', 'not_ready', False,
         'Thermal/current kernels exist for older synthetic AC examples; current network reduction and generator Q fields are DC-only.',
         'Requires a qualified AC network and controls plus physical series-current reconstruction; older AC results do not qualify this case.'),
        ('N-1 secure transfer capacity or operational system-capacity claim', 'not_ready', False,
         'No current physical-outage set, security-constrained replay, field-calibrated weather/conductors, or terminal-limit qualification.',
         'Rebuild reduction/recovery for physical outages; do not equate a Schur-edge outage with a physical circuit outage.'),
    ]
    cap = pd.DataFrame(capability, columns=['capability', 'status', 'runnable_in_current_delivery', 'evidence', 'claim_boundary'])
    cap.to_csv(OUT / 'capability_matrix.csv', index=False, lineterminator='\n')
    thermal = LITE / 'dlr_heat_balance.m'
    oldsolver = LITE / 'solve_dlr_steady_operating_point.m'
    loader = ROOT / 'System Matpower Format/npcc_nygrid_2025_dover_dc.m'
    gaps = [
        ('G01', 'physical_branch_to_thermal_segment_adapter', 'small_new_adapter',
         source_line(loader, 'mpc.userdata.slim.interface_angle_matrix='),
         'Loader exposes interface recovery only; full branch recovery exists in the MAT payload, but no keyed current/thermal segment runtime.',
         'Bind F84 first; use dated full391/slim244 identity. Use H*theta+h+phase_basis*psi for eliminated physical branches. Never thermalize DC_EQ rows.'),
        ('G02', 'ACSS_thermal_property_interface', 'new_versioned_thermal_input_schema',
         source_line(LITE / 'dlr_conductor_library.m', 'code=['),
         'The runtime catalog contains only three ACSR surrogates; current project catalog contains ACSS Mallard/Bluebird and AC resistance points.',
         'Accept project/catalog keyed ACSS records, per-subconductor diameter/mass and AC R(T) interpolation; declare cp/surface aging/temperature assumptions.'),
        ('G03', 'ACSS_resistance_temperature_law', 'replace_in_new_adapter_not_legacy_history',
         source_line(thermal, 'r=c.r_ref_ohm_m*'),
         'Old kernel hard-codes a linear assumed alpha20 law; current line estimates interpolate manufacturer AC resistance at25/75/200C.',
         'Pass a consistent AC R(T) law into the new heat-balance adapter; reject extrapolation outside the adopted catalog range.'),
        ('G04', 'weather_and_thermal_state_binding', 'public_data_adapter_plus_explicit_assumptions',
         source_line(LITE / 'compact_partial_spc_dlr_contract.m', 'weather=table('),
         'Existing four-row weather inputs are constant synthetic conditions for an older compact model.',
         'Bind route segments and wind angle/height/temperature/solar/pressure to the same UTC hours; preserve gaps; define initialization and gap policy.'),
        ('G05', 'power_scale_and_multiplicity', 'explicit_unit_contract',
         source_line(loader, 'states.gamma==mpc.userdata.nygrid2025.scale_factor_gamma'),
         'Current powers use gamma0.30012075175; physical conductor ratings and source MVA are unscaled.',
         'For declared unity-PF nominal-V DC studies use I_sub[A]=1000|P_model[MW]|/(gamma*sqrt(3)*V[kV]*circuits*bundle). Reverse-convert ratings once.'),
        ('G06', 'old_AC_solver_removes_current_boundary_devices', 'new_current_contract_adapter_required',
         source_line(oldsolver, "keep=intersect(fieldnames(m),{'version'"),
         'plain() whitelist at lines90-91 removes dcline and userfcn; invoked at44 and65. Direct reuse loses the six fixed-transfer records and callbacks.',
         'Preserve current boundary/controller fields and add invariance assertions in a new adapter; do not change archived solver evidence.'),
        ('G07', 'line_constraints_and_dispatch_feedback', 'new_DC_research_formulation',
         source_line(ROOT / 'scripts/nygrid_2025_dispatch/build_dispatch.py', 'hourly_scope='),
         'Current dispatch projects generation priors onto boxes and a native sum; saved cases are not DLR-constrained OPF.',
         'For fixed-dispatch studies report exposure only. For mitigation add physical-flow constraints and reoptimize a declared objective; preserve PG boxes and six transfers.'),
        ('G08', 'equipment_ceiling_and_zero_rate_semantics', 'document_assumption_or_obtain_asset_rating',
         source_line(ROOT / 'scripts/nygrid_2025_line_parameters/validate_parameter_overlays.py', 'rating_scope='),
         '242 active runtime branches have RATE_A0; F84 1323MVA is a conductor design reference, not a current terminal-limited facility guarantee.',
         'Keep unknown limits explicitly unknown. Thermal line limits cannot override transformer/PAR/breaker/terminal ceilings.'),
        ('G09', 'physical_outage_security', 'needed_only_for_security_claims',
         source_line(ROOT / 'scripts/nygrid_2025_slim/build_slim_network.py', 'thermal_dlr_eligible=False'),
         'No current physical-contingency DLR campaign; the reduced network contains30 nonphysical Schur connections.',
         'Apply outages to physical parent rows then recompute network reduction and recovery; validate fixed-device identities and control policies.'),
        ('G10', 'legacy_latest_pointer_scope', 'documentation_routing_only',
         source_line(ROOT / 'LATEST_MODEL_CONFIGURATION.csv', 'preferred_operating_candidate'),
         'Generic latest pointer still names the older71-bus partial-SPC case.',
         'This assessment explicitly binds the delivered Dover loader and audited hashes; do not borrow the older candidate thermal qualification.'),
    ]
    gap = pd.DataFrame(gaps, columns=['gap_id', 'topic', 'minimal_action_class', 'evidence_location', 'finding', 'minimum_next_action'])
    gap.to_csv(OUT / 'code_and_data_gaps.csv', index=False, lineterminator='\n')
    scope_dirs = [ROOT / 'scripts/nygrid_2025_dover_parameters', ROOT / 'scripts/nygrid_2025_line_parameters',
                  ROOT / 'output/nygrid_2025_dover_parameters', ROOT / 'output/nygrid_2025_line_parameters']
    weather_paths = sorted(rel(p) for directory in scope_dirs for p in directory.rglob('*')
                           if p.is_file() and 'weather' in p.name.lower())
    require(not weather_paths, 'A new weather artifact appeared; inspect it before describing the gap')
    catalogs = pd.read_csv(LINE / 'conductors/conductor_catalog.csv')
    require(((catalogs.family == 'ACSS') & (catalogs.code_word == 'Mallard')).sum() == 1, 'Mallard catalog identity changed')
    require(((catalogs.family == 'ACSS') & (catalogs.code_word == 'Bluebird')).sum() == 1, 'Bluebird catalog identity changed')
    requirements = dict(keyed_current_thermal_branch_registry=False, qualified_ACSS_thermal_input_adapter=False,
        route_segment_weather_bound_to_2025_hours=False, gamma_aware_current_and_rating_adapter=False,
        current_model_thermal_state_and_gap_policy=False, current_model_DLR_replay_validated=False,
        authoritative_terminal_and_clearance_limits=False, measured_asset_current_or_temperature_validation=False)
    minimum_next = [
        'Build a separate F84-only design-based experiment; retain all existing cases. Declare one circuit, two subconductors per phase and the95C design reference.',
        'Version a keyed ACSS thermal record with catalog AC R(T), diameter and mass; declare cp, emissivity, absorptivity and sag/clearance assumptions.',
        'Add route/weather mapping and a source-preserving common-hour mask. Run a declared DC current-proxy, fixed-dispatch exposure replay against static and weather-varying limits.',
        'Validate unit/base/bundle identities and thermal equilibrium/transients. Export per-hour current, limit, temperature, gap and assumptions ledgers without silently clipping inputs.',
        'Only if studying mitigation, add constrained DC redispatch using recovered physical-flow inequalities and a stated controller policy. Keep the six fixed transfers and original generation boxes.',
    ]
    summary = dict(assessment_completed=True, physical_DLR_readiness_passed=False,
        created_utc=datetime.now(timezone.utc).isoformat(), requested_baseline_commit=BASELINE_HEAD,
        audited_checkout_commit=head, branch=branch, loader=rel(loader),
        evidence_status='fresh_read_only_audit_plus25_fresh_component_checks;existing_delivered_DC_validation_separately_verified',
        current_model=dict(retained_buses=148,full_buses=192,retained_branch_records=274,full_branch_records=413,
            runtime_active_retained_branches=kernel['active_branch_records'],active_zero_RATE_A=kernel['active_zero_RATE_A_records'],
            active_voltage_changing_retained_branches=kernel['active_voltage_changing_records'],
            generator_records=1464,fixed_transfer_records=6,annual_common_hours=8651,
            post_Dover_hours=287,source_gap_hours_retained=8760-8651,gamma=kernel['gamma'],
            retained_branch_registry_thermal_eligible=0,nonphysical_Schur_connections=30,
            preserved_historical_source_circuits=97),
        answer='Ready as a validated DC platform for declared control/topology research; a current-model DLR experiment is not yet integrated. A narrow F84-first design-based DC DLR exposure study is the minimum defensible next implementation.',
        AC_is_not_a_prerequisite_for_explicitly_declared_DC_DLR_method_research=True,
        current_DLR_coupled_replay_run=False, reusable_kernel_checks=kernel['component_tests'],
        branch_ledger_scope='Nominal x_nominal full-service Dover topology with original branch211 disabled by the six-transfer runtime contract; consistent with inspected hour8508. Earlier2025 hours retain their dated pre-cutover topology and cannot inherit post-cutover Dover line/bank availability.',
        control_source_scope='Numerical DC/control validation is conditional on adopted P34 posted-number units and hourly aggregation; it does not certify native MW units, measured telemetry origin, actual taps, or a Dover sign effective date covering December2025.',
        existing_Dover_DC_validation=dict(full192=49,slim148=49,scope='DC electrical and phase-recovery validation, not DLR validation'),
        physical_readiness_required_evidence=requirements, minimal_next_implementation=minimum_next,
        scaling=dict(current_proxy_formula='I_sub_A=1000*abs(P_model_MW)/(gamma*sqrt(3)*Vnom_kV*n_circuits*n_bundle)',
            reverse_limit_formula='P_limit_model_MW=gamma*sqrt(3)*Vnom_kV*n_circuits*n_bundle*I_sub_limit_A/1000',
            DC_proxy_assumptions='nominal voltage; unity power factor; equal sharing only for explicitly represented equal parallel circuits and bundle members',
            gamma_lift_status='declared uniform model-to-public power mapping, not a validation of physical circuit current',
            current_lower_bound_qualification='At a fixed actual terminal voltage and correct actual P, |P|/(sqrt(3)*V) is a lower bound on total terminal current when Q is unknown. Using modeled P/gamma and nominal V is only a DC proxy; it is not a measured or guaranteed lower bound on the actual line current, and terminal current differs from series conductor current when charging is present.',
            physical_branch_recovery_required_before_conversion='Recover keyed full physical line flows before conversion; never interpret an individual DC_EQ connection as a physical circuit. F84 is retained directly at slim244/full391; Dover line flows require the full recovery and phase offsets.',
            not_measured_or_AC_series_current=True,
            forgotten_gamma_current_ratio=kernel['unconverted_scaled_power_current_ratio'],
            forgotten_gamma_heating_ratio=kernel['unconverted_scaled_power_Joule_heating_ratio'],
            F84_2214A_is_total_phase_current_not_per_subconductor=True,
            mixed_Dover_398_phase_limit='min(2*I_Mallard_NY_sub,1*I_Bluebird_CT_sub) across all weather segments; use separate PAR/equipment limits'),
        hard_asset_unknowns=['Critical-span routes, terrain-adjusted wind and segment weather for the actual2025 operating hours',
            'As-installed conductor condition, surface emissivity/absorptivity and thermal/mechanical temperature limits',
            'Current terminal/breaker/transformer limits; actual PAR tap/bypass/cooling and reactive flows',
            'For RCC cables: conductor/sheath/bonding and soil/installation thermal properties; overhead heat balance is inapplicable'],
        conditional_not_universal_requirements=['AC/reactive/voltage validation is needed for AC current and AC operating-feasibility claims, not every DC method experiment',
            'N-1 contingency validation is needed for security claims; not for a clearly labeled intact-system sensitivity study',
            'Unit commitment, ramps, reserves and storage energy are needed when claiming corresponding operational dispatch feasibility, not for fixed-dispatch thermal exposure'],
        audited_weather_namespaces=[rel(p) for p in scope_dirs], weather_artifacts_in_current_namespaces=weather_paths,
        existing_synthetic_weather_scope='Four constant cases on older compact models; no current route-weather binding',
        no_old_models_or_kernels_modified=True,no_redispatch_or_refit_run=True,
        supporting_primary_references=[
            dict(url='https://matpower.app/manual/matpower/DCModeling.html',supports='DC equations carry active power and angles under lossless near-unit-voltage assumptions'),
            dict(url='https://raw.githubusercontent.com/NatLabRockies/DynamicLineRatings/d8e443eb09e428fb0fc8452370fd72fe8819f927/dlr/physics.py',supports='Pinned upstream convection/radiation/solar reference underlying saved numeric fixtures'),
            dict(url='https://www.nrel.gov/docs/fy25osti/91599.pdf',supports='Route-segment weather-based ampacity methodology and research assumptions')])
    files = [Path(__file__), kernel_file, OUT/'fresh_reusable_component_tests.csv', netpath, register_path, replay_path,
             previous_validation, contract_path, loader, oldsolver, thermal, LITE/'dlr_conductor_library.m',
             LITE/'build_dlr_corridor_realizations.m', LITE/'compact_partial_spc_dlr_contract.m',
             ROOT/'LATEST_MODEL_CONFIGURATION.csv', LINE/'conductors/conductor_catalog.csv',
             LINE/'project_source_register.csv', LINE/'estimates/engineering_basis.json',
             LINE/'estimates/Dover_line_only_estimates_not_applied.csv', DOVER/'network/Dover_applied_branch_register.csv',
             DOVER/'network/network_receipt.json',DOVER/'replay/operating_states.mat',
             ROOT/'output/nygrid_2025_western_audit/dispatch/all_boundary_dispatch_receipt.json']
    summary['dependencies'] = [dict(path=rel(p), sha256=sha(p)) for p in dict.fromkeys(files)]
    summary['outputs'] = [dict(path=rel(OUT/name),sha256=sha(OUT/name))
                          for name in ['branch_readiness.csv','capability_matrix.csv','code_and_data_gaps.csv']]
    dump('readiness_assessment.json', summary)
    print(json.dumps({key:summary[key] for key in ['assessment_completed','physical_DLR_readiness_passed',
        'audited_checkout_commit','current_model','answer','reusable_kernel_checks']},indent=2))
    return summary


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true',
                        help='Read-only verification of the sealed assessment and its dependency/output hashes.')
    parser.add_argument('--require-physical-dlr',action='store_true',
                        help='Return exit2 when current physical DLR evidence is incomplete, after writing the assessment.')
    arguments=parser.parse_args()
    result=verify() if arguments.verify else main()
    if arguments.require_physical_dlr and not result['physical_DLR_readiness_passed']:
        raise SystemExit(2)
