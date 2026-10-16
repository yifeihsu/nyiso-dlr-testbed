"""Bind the independent final-report accuracy/link review to saved evidence."""
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import unquote
import hashlib,json,re
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'output/nygrid_2025_ac_system'


def record(p):
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=p.relative_to(ROOT).as_posix(),sha256=h)


def main():
    report=ROOT/'NYGRID_2025_AC_SYSTEM.md';content=report.read_text(encoding='utf-8')
    destinations=re.findall(r'\[[^\]]+\]\(([^)]+)\)',content)
    assert len(destinations)==21
    linked=[ROOT/unquote(p) for p in destinations]
    assert all(p.is_file() for p in linked)
    manifest_path=BASE/'DELIVERY_MANIFEST.json'
    contract_path=BASE/'AC_SYSTEM_CONTRACT.json'
    assert manifest_path in linked and contract_path in linked
    contract=json.loads(contract_path.read_text())
    assert contract['selected_electrical_attempts']==7
    assert contract['qualified_electrical_and_ACPF_hours']==[2630,8471,8472,8508]
    assert contract['unqualified_selected_electrical_hours']==[523,4000,4194]
    assert contract['whole_network_weather_attempts']==8 and len(contract['qualified_weather_points'])==4
    assert contract['failed_weather_points_retained']==4 and contract['no_global_infeasibility_proof']
    assert not contract['all_year_AC_feasibility_established'] and not contract['historical_weather_bound']
    assert contract['reference_temperature_resistance_not_equilibrium']
    assert not contract['composite_physical_interior_conductor_coverage_established']
    assert not contract['asbuilt_parameters_or_actual_equipment_ratings_certified']
    assert 'python scripts/nygrid_2025_ac_system/finalize_ac_system.py --verify' in content
    electrical_path=BASE/'ac_validation/electrical_final/electrical_validation.json'
    electrical=json.loads(electrical_path.read_text())
    thermal_path=BASE/'thermal/whole_system_snapshot_results.csv'
    thermal=pd.read_csv(thermal_path)
    thermal_summary_path=BASE/'thermal/whole_system_validation.json'
    thermal_summary=json.loads(thermal_summary_path.read_text())
    epassed=[r for r in electrical['checks'] if r['passed'] and r['ACPF_replay_passed']]
    assert len(electrical['checks'])==7 and len(epassed)==4 and not electrical['passed']
    assert set(r['hour_index'] for r in epassed)=={2630,8508,8471,8472}
    good=thermal[['solver_success','electrical_pass','thermal_pass','terminal_current_pass','section_end_thermal_pass']].eq(1).all(axis=1)
    assert len(thermal)==8 and good.sum()==4 and thermal_summary['snapshots']==8
    assert not thermal_summary['all_snapshot_constraints_passed']
    assert not thermal_summary['historical_annual_AC_DLR_replay_completed']
    assert thermal.fixed_reference_R.eq(1).all()
    for row in thermal.loc[good].itertuples():
        formatted=f'| {row.hour} | 25 C, '+('0.6096' if row.scenario=='catalog_reference' else '2.0')
        matching=[x for x in content.splitlines() if x.startswith(formatted)]
        assert len(matching)==1 and f'| {row.loss_mw:.3f} | {row.objective:.3f} |' in matching[0]
    for h,g in thermal.loc[good].groupby('hour'):
        x=g.set_index('scenario')
        assert x.loc['breezy','objective']<x.loc['catalog_reference','objective']
        assert x.loc['breezy','loss_mw']>x.loc['catalog_reference','loss_mw']
    pf_paths=[]
    for row in epassed:
        path=BASE/f'ac_validation/electrical_final/hour_{row["hour_index"]}_ACPF.json'
        p=json.loads(path.read_text());pf_paths.append(path)
        assert p['passed'] and p['PF_backend']=='MATPOWER_legacy_NR'
        assert p['PF_Q_limit_enforcement']==0 and p['all_Q_limits_checked_after_solve']
        assert p['replayed_successful_ACOPF_point'] and not p['lossless_DC_dispatch_used_as_PF_state']
    extra_path=BASE/'ac_validation/electrical_solver_starts/solver_start_diagnostics.json'
    extra=json.loads(extra_path.read_text())
    assert len(extra['checks'])==6 and all(not r['passed'] for r in extra['checks'])
    assert {r['hour_index'] for r in extra['checks']}=={4194,523,4000}
    assert not extra['constraints_changed'] and not extra['parameter_fitting_performed'] and not extra['global_infeasibility_proved']
    initial=BASE/'ac_validation/initial_diagnostic';initial_losses=[];initial_files=[]
    for f in sorted(initial.glob('*_PF_NR.mat')):
        r=loadmat(f,simplify_cells=True)['r']
        ip=f.with_name(f.name.replace('_PF_NR','_input'))
        d=loadmat(ip,simplify_cells=True)
        m=next(v for v in d.values() if isinstance(v,dict) and 'gen' in v)
        loss=float(np.sum(r['branch'][:,13]+r['branch'][:,15]))
        increase=float(np.sum(r['gen'][:,1]-m['gen'][:,1]))
        assert r['success'] and r['iterations']==4 and abs(loss-increase)<1e-6
        initial_losses.append(dict(case=f.stem,AC_loss_mw=loss,slack_generation_increase_mw=increase))
        initial_files.extend([f,ip])
    assert '232–239 MW' in content and '40–42 active cable sections' in content
    assert 'Q-limit enforcement disabled during the solve' in content
    assert 'mutual/bundle shielding are not validated by this study' in content
    assert 'fixed reference resistance at 75 C for ACSR and 95 C for ACSS' in content
    assert 'not proofs of global infeasibility' in content
    assert 'internal physical lines remain undecomposed and are not covered by the overhead DLR equations' in content
    assert 'opf_audit = audit_ac_solution(mpc, opf);' in content and 'assert(opf_audit.passed);' in content
    topology_path=BASE/'branches/sectioned_design_checks.csv';topology=pd.read_csv(topology_path).set_index('state')
    assert topology.loc['pre_may','active_runtime_cable_sections']==40 and topology.loc['post_dover','active_runtime_cable_sections']==42
    design_path=BASE/'branches/sectioned_design_receipt.json';design=json.loads(design_path.read_text())
    assert design['designed_extra_buses']==75 and design['OH_split_corridors']==44
    assert design['OH_reactor_corridors']==16 and design['cable_reactor_corridors']==19
    adapter_path=BASE/'thermal/adapter_validation.json';adapter=json.loads(adapter_path.read_text())
    assert adapter['passed'] and adapter['tests']==21
    claims={
        'ACPF_convergence_distinct_from_bounded_feasibility':True,
        'electrical_snapshot_scope_separate_from_weather_constrained_scope':True,
        'four_of_seven_electrical_and_four_ACPF_replays_supported':True,
        'four_of_eight_weather_current_snapshots_supported':True,
        'failed_attempts_retained_not_claimed_globally_infeasible':True,
        'tables_match_saved_successful_point_values_to_reported_precision':True,
        'actual_voltage_hardware_and_conductor_current_constraints_distinguished':True,
        'no_gamma_current_rescaling':True,
        '65_composite_interiors_explicitly_not_thermalized':True,
        '75_percent_reactor_midpoint_and_selectors_explicit_study_assumptions':True,
        'cable_reactor_extension_not_claimed_as_installed_or_mandated':True,
        'fixed_hot_R_not_claimed_as_steady_electrothermal_equilibrium':True,
        'uniform_weather_not_claimed_observed':True,
        'objective_reduction_not_claimed_as_economic_or_historical_benefit':True,
        'ACPF_start_and_postsolve_Q_audit_scope_explicit':True,
        'annual_historical_security_and_asbuilt_claims_excluded':True}
    files=[report,electrical_path,thermal_path,thermal_summary_path,extra_path,topology_path,design_path,adapter_path,
        BASE/'engineering/composite_revision_independent_review.json',BASE/'engineering/sectioned_design_independent_review.json',
        BASE/'engineering/thermal_adapter_independent_review.json',ROOT/'scripts/nygrid_2025_ac_system/ac_validation/replay_acpf_solution.m',Path(__file__)]
    files.extend(pf_paths+initial_files)
    receipt=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent numerical/physical wording, saved-evidence and link review of the final report; no new operating solve',
        report=record(report),electrical_qualified=4,electrical_attempted=7,ACPF_qualified_replays=4,
        weather_current_qualified=4,weather_current_attempted=8,local_links_checked=len(linked),missing_links=[],
        delivery_manifest_checked_for_existence_only_to_avoid_circular_sealing=True,
        machine_readable_contract_partial_qualification_matches_saved_results=True,
        initial_ACPF_verified_losses=initial_losses,
        successful_weather_max_P_KCL_mw=float(thermal.loc[good,'max_P_KCL_mw'].max()),
        successful_weather_max_Q_KCL_mvar=float(thermal.loc[good,'max_Q_KCL_mvar'].max()),
        successful_weather_max_conductor_loss_discrepancy_mw=float(thermal.loc[good,'max_loss_identity_error_mw'].max()),
        corrected_findings=['Initial ACPF loss range corrected to approximately 232-239 MW.',
            'Active cable sections qualified as 40-42 by topology.',
            'Unvalidated physical assumptions described as not validated.',
            'Q-limit enforcement during ACPF explicitly distinguished from the post-solve bound audit.'],
        unresolved_report_findings=[],physical_scope_review=claims,
        dependencies=[record(p) for p in sorted(set(files))],
        links=[dict(path=p.relative_to(ROOT).as_posix(),exists=True,validation='existence_only;manifest_excluded_from_hash_dependencies_to_avoid_cycle')
               if p==manifest_path else record(p) for p in linked])
    (BASE/'engineering/report_review.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['dependencies','links','initial_ACPF_verified_losses','physical_scope_review']},indent=2))


if __name__=='__main__':main()
