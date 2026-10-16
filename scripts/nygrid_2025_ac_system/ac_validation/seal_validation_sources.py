"""Seal current AC validation code, inputs and complete unfiltered evidence.

This is source/evidence integrity checking, not an additional numerical run.
It distinguishes an audited test cohort from universal operating feasibility.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT=Path(__file__).resolve().parents[3]
PACKAGE=ROOT/'output/nygrid_2025_ac_system'
AUDIT=PACKAGE/'ac_validation'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def record(path):
    path=Path(path)
    assert path.is_file(),f'Missing required evidence: {path}'
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':digest(path),'bytes':path.stat().st_size}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    electrical_file=AUDIT/'electrical_final/electrical_validation.json'
    independent_file=AUDIT/'independent_thermal_snapshots/independent_thermal_snapshot_validation.json'
    thermal_file=PACKAGE/'thermal/whole_system_validation.json'
    starts_file=AUDIT/'electrical_solver_starts/solver_start_diagnostics.json'
    electrical=read(electrical_file);independent=read(independent_file);thermal=read(thermal_file);starts=read(starts_file)
    assert electrical['complete'] and len(electrical['checks'])==7
    assert {x['hour_index'] for x in electrical['checks']}=={2630,4194,523,4000,8508,8471,8472}
    good_electrical=[x for x in electrical['checks'] if x['passed']]
    assert {x['hour_index'] for x in good_electrical}=={2630,8508,8471,8472}
    assert all(x['solver_success'] and x['ACPF_replay_passed'] for x in good_electrical)
    assert not electrical['passed'] and not electrical['all_selected_ACPF_replays_passed']
    assert thermal['completed'] and len(thermal['results'])==8 and not thermal['all_snapshot_constraints_passed']
    expected={(h,w) for h in [2630,4000,4194,8508] for w in ['catalog_reference','breezy']}
    assert {(x['hour'],x['scenario']) for x in thermal['results']}==expected
    good_thermal=[x for x in thermal['results'] if x['solver_success']]
    assert {(x['hour'],x['scenario']) for x in good_thermal}=={(h,w) for h in [2630,8508] for w in ['catalog_reference','breezy']}
    assert all(x['electrical_pass'] and x['thermal_pass'] and x['terminal_current_pass'] and x['section_end_thermal_pass'] for x in good_thermal)
    assert all(not x['electrical_pass'] and not x['thermal_pass'] for x in thermal['results'] if not x['solver_success'])
    assert independent['independent_audit_complete'] and independent['root_classification_confirmed']
    assert independent['snapshot_attempts']==8 and independent['qualified_constrained_operating_points']==4
    assert independent['failed_OPF_trials_not_promoted']==4 and independent['all_four_successful_points_ACPF_replay_passed']
    assert len(independent['checks'])==8 and {(x['hour_index'],x['scenario']) for x in independent['checks']}==expected
    assert starts['complete'] and not starts['constraints_changed'] and not starts['parameter_fitting_performed']
    assert len(starts['checks'])==6 and not any(x['passed'] for x in starts['checks'])
    bound_sources={
        'branch_parameter_overlay_sha256':PACKAGE/'branches/engineering_overlay.mat',
        'sectioned_design_plan_sha256':PACKAGE/'branches/sectioned_design_plan.mat',
        'generator_capability_policy_sha256':AUDIT/'generator_capability_policy.json',
    }
    for key,path in bound_sources.items():
        value=digest(path)
        assert electrical[key]==value
        electrical_key='branch_overlay_sha256' if key=='branch_parameter_overlay_sha256' else key
        assert all(row[electrical_key]==value for row in electrical['checks'])
        assert all(row[key]==value for row in independent['checks'])
    inputs=list(bound_sources.values())+[
        PACKAGE/'branches/sectioned_design_receipt.json',
        PACKAGE/'engineering/sectioned_design_independent_review.json',
        PACKAGE/'engineering/final_branch_mapping_review.json',
        PACKAGE/'engineering/thermal_conductors.csv',
        PACKAGE/'thermal/declared_weather_scenarios.csv',
        AUDIT/'external_capability_mapping.csv',
        ROOT/'output/nygrid_2025_inputs/model/operating_inputs.mat',
        ROOT/'output/nygrid_2025_dispatch/dispatch/model_generator_register.csv',
    ]
    source_code=[ROOT/'System Matpower Format/npcc_nygrid_2025_ac.m',
        ROOT/'System Matpower Format/run_nygrid_2025_ac_dlr.m',
        ROOT/'System Matpower Format/NY_Lite/dlr_series_constraint.m',
        ROOT/'System Matpower Format/NY_Lite/add_dlr_series_current_constraints.m']
    for folder in ['ac_validation','thermal','branches']:
        base=ROOT/'scripts/nygrid_2025_ac_system'/folder
        source_code.extend(sorted(p for p in base.iterdir() if p.is_file() and p.suffix in {'.py','.m'}))
    evidence=[thermal_file,starts_file]
    for folder in [AUDIT/'electrical_final',AUDIT/'independent_thermal_snapshots',AUDIT/'electrical_solver_starts']:
        evidence.extend(sorted(p for p in folder.iterdir() if p.is_file() and p.suffix in {'.mat','.json','.csv'}))
    for row in thermal['results']:
        evidence.append(PACKAGE/'thermal'/f"h{row['hour']}_{row['scenario']}.mat")
    evidence.append(PACKAGE/'thermal/whole_system_snapshot_results.csv')
    report={
        'integrity_audit_passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),
        'numerical_solves_performed_by_this_sealing_step':False,
        'modeltype':'bounded_synthetic_AC','model_scale':'existing_gamma_scaled_powers_at100MVA_no_impedance_or_current_gamma_lift',
        'default_demonstration_hour':8508,
        'electrical_attempts':7,'electrical_qualified_OPF_and_ACPF_hours':[2630,8508,8471,8472],
        'electrical_failed_hours':[4194,523,4000],
        'additional_initialization_trials':6,'additional_qualified_hours':[],
        'thermal_attempts':8,'thermal_qualified_points':4,'thermal_failed_points_retained':4,
        'all_four_thermal_successes_independently_audited_and_ACPF_replayed':True,
        'all_hours_or_all_tested_snapshots_feasible':False,
        'global_infeasibility_proved_for_failed_hours':False,
        'historical_annual_AC_DLR_replay_or_asbuilt_certification_claimed':False,
        'steady_ampacity_at_declared_reference_R_only':True,'conductor_temperature_equilibrium_validated':False,
        'PF_backend':'MATPOWER legacy NR with deterministic initial perturbation; Q enforcement0 then independent bounds audit',
        'source_data':[record(p) for p in sorted(set(inputs))],
        'current_source_code':[record(p) for p in sorted(set(source_code))],
        'current_evidence':[record(p) for p in sorted(set(evidence))],
        'prior_failed_sectioned_Q_rectangle_archive':record(AUDIT/'electrical_revision03/archive_receipt.json'),
        'behavior_changes_require_relevant_numerical_revalidation':True,
    }
    target=AUDIT/'validation_source_receipt.json'
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'integrity_audit_passed':True,'source_files':len(report['current_source_code']),
        'evidence_files':len(report['current_evidence']),'electrical_qualified':4,'thermal_qualified':4,
        'receipt_sha256':digest(target)}))


if __name__=='__main__':
    main()
