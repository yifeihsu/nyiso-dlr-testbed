"""Bind direct-profile PF evidence, current code and immutable source inputs.

No power flow is run here. Statistics exclude failed/non-equation-qualified
iterates. Previous AC/OPF artifacts are verified, never rewritten.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_acpf_profile_audit/acpf'
TARGET=OUT/'validation_source_receipt.json'


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def record(path):
    path=Path(path);assert path.is_file(),str(path)
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(path),bytes=path.stat().st_size)


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def flags(series):return series.astype(str).str.lower().isin(['true','1'])


def main():
    annual=read(OUT/'annual_profile_PF_receipt.json');recovery=read(OUT/'NR_recovery/NR_recovery_receipt.json')
    qlimits=read(OUT/'Q_limit_sensitivity/Q_limit_sensitivity_receipt.json')
    parity=read(OUT/'cache_parity_and_benchmark.json')
    assert annual['completed'] and annual['attempted_hours']==annual['source_qualified_hours']==8651
    assert annual['PF_converged_hours']==annual['AC_equation_qualified_hours']==annual['P_profile_preserved_hours']==8494
    assert annual['solver_exceptions']==0 and annual['VQ_and_generator_assumption_qualified_hours']==0
    assert len(annual['failed_NR_hours'])==157 and recovery['completed'] and recovery['attempts']==314
    assert recovery['recovered_hour_count']==0 and recovery['remaining_unresolved_count']==157
    assert set(annual['failed_NR_hours'])==set(recovery['remaining_unresolved_hours'])
    assert qlimits['completed'] and len(qlimits['checks'])==7 and parity['passed']
    assert not annual['OPF_used'] and not recovery['OPF_used'] and not qlimits['OPF_used']
    progress=read(OUT/'annual_progress.json')
    progress.update(completed=True,months_complete=12,attempted=8651,converged=8494,
        solver_exceptions=0,elapsed_seconds=annual['elapsed_seconds'],final_receipt='annual_profile_PF_receipt.json',
        completion_status_refreshed_after_worker_exit=True)
    (OUT/'annual_progress.json').write_text(json.dumps(progress,indent=2)+'\n')
    logs=OUT/'logs';logs.mkdir(exist_ok=True)
    for name in ['representatives','cache_benchmark','annual','Q_limit_sensitivity','NR_recovery']:
        source=ROOT/'tmp'/f'acpf_profile_{name}.log'
        assert source.is_file(),str(source);shutil.copyfile(source,logs/source.name)
    quality=pd.read_csv(OUT/'annual_hour_quality.csv')
    assert len(quality)==8651 and quality.hour_index.is_unique
    good=flags(quality.AC_equation_gate)&flags(quality.P_profile_preservation_gate)
    solved=quality.loc[good];assert len(solved)==8494
    flag_names=['normal_voltage_gate','generator_active_bound_gate','generator_reactive_bound_gate',
        'generator_S_proxy_gate','six_transfer_reactive_contract_gate','VQ_and_generator_assumption_gate']
    counts={name:int(flags(solved[name]).sum()) for name in flag_names}
    extremes={}
    for name in ['min_voltage_pu','max_voltage_pu','reference_PG_change_MW','max_P_bound_violation_mw',
                 'max_Q_bound_violation_mvar','max_transfer_Q_bound_violation_mvar',
                 'maximum_non_slack_PG_change_MW','slack_change_minus_required_loss_balance_MW',
                 'max_nodal_P_residual_mw','max_nodal_Q_residual_mvar']:
        values=solved[name].to_numpy(float);assert np.isfinite(values).all()
        extremes[name]={'min':float(values.min()),'max':float(values.max())}
    qgood=[x for x in qlimits['checks'] if x['PF_converged'] and x['AC_equation_gate']]
    assert len(qgood)==5
    summary=dict(completed=True,statistics_cohort='AC_equation_gate AND P_profile_preservation_gate; failed iterates excluded',
        source_qualified_hours=8651,equation_and_profile_qualified_hours=8494,unresolved_after_three_initializations=157,
        VQ_and_generator_assumption_qualified_hours=0,qualified_hour_gate_counts=counts,qualified_hour_extrema=extremes,
        Q_limit_seven_hour_diagnostic=dict(converged_and_equation_qualified=5,total=7,
            generator_Q_and_DC_Q_pass_count=sum(x['generator_Q_bound_gate'] and x['six_DC_Q_contract_gate'] for x in qgood),
            normal_voltage_pass_count=sum(x['normal_voltage_gate'] for x in qgood),
            generator_P_pass_count=sum(x['generator_P_bound_gate'] for x in qgood),
            solved_only_VM_min=min(x['VM_min'] for x in qgood),solved_only_VM_max=max(x['VM_max'] for x in qgood),
            reference_bus_changes=sum(x['reference_bus_changed'] for x in qgood)),
        overload_is_not_a_convergence_gate=True,global_infeasibility_proved=False,
        physically_meaningful_conditions_confirmed_for_all_source_profiles=False,
        generator_Q_capabilities_are_model_assumptions_not_observed=True,
        annual_core_numerical_run_seconds=annual['elapsed_seconds'],annual_core_was_not_rerun=True)
    (OUT/'qualified_solution_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    # Verify all clock rows and canonical axes; annual chunks preserve failed states.
    axes=loadmat(OUT/'annual_axes.mat',simplify_cells=True);seen=[];monthly=[]
    for mon in range(1,13):
        path=OUT/'monthly'/f'profile_PF_2025_{mon:02d}.mat'
        d=loadmat(path,simplify_cells=True,variable_names=['hour_index','source_qualified','bus_id','branch_keys','computed_current_available'])
        hh=np.atleast_1d(d['hour_index']).astype(int);seen.extend(hh.tolist())
        assert np.array_equal(d['bus_id'],axes['bus_id']) and np.array_equal(d['branch_keys'],axes['branch_keys'])
        assert np.array_equal(np.atleast_1d(d['source_qualified']).astype(bool),axes['source_qualified'][hh-1].astype(bool))
        assert path.stat().st_size<100_000_000
        monthly.append(record(path))
    assert sorted(seen)==list(range(1,8761))
    attempts=pd.read_csv(OUT/'NR_recovery/recovery_attempt_quality.csv')
    warm=attempts.loc[attempts.retry_strategy.eq('previous_equation_qualified_voltage')]
    seeds=warm.seed_hour.to_numpy(int);targets=warm.hour_index.to_numpy(int)
    state=axes['topology_state_index']
    assert np.all(seeds<targets) and np.array_equal(state[seeds-1],state[targets-1])
    assert not flags(attempts.computed_current_available).any()
    # Validate the previously sealed namespace without changing any byte.
    oldseal=ROOT/'output/nygrid_2025_ac_system/ac_validation/validation_source_receipt.json'
    old=read(oldseal);old_records=sum((old[name] for name in ['source_data','current_source_code','current_evidence']),[])
    for r in old_records:assert sha(ROOT/r['path'])==r['sha256'],f"Changed baseline: {r['path']}"
    inputs=[ROOT/r['path'] for r in old['source_data']]+[
        ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch.mat',
        ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch_bounds.mat',
        ROOT/'output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat',
        ROOT/'output/nygrid_2025_western_audit/replay/dated_combined.mat',
        ROOT/'output/nygrid_2025_dover_parameters/replay/operating_states.mat']
    code=list((ROOT/'scripts/nygrid_2025_acpf_profile_audit/acpf').glob('*.m'))+list((ROOT/'scripts/nygrid_2025_acpf_profile_audit/acpf').glob('*.py'))
    code+=list((ROOT/'System Matpower Format').glob('npcc_nygrid_2025_*.m'))
    code+=[ROOT/r['path'] for r in old['current_source_code'] if r['path'].endswith('.m')]
    evidence=sorted(p for p in OUT.rglob('*') if p.is_file() and p!=TARGET and p.suffix in {'.mat','.csv','.json','.log'})
    receipt=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),baseline_byte_preserved=True,
        old_AC_namespace_not_modified=True,old_seal_verified_records=len(old_records),baseline_seal=record(oldseal),
        current_baseline_commit='330be1d90e6faab8d6c32c3d6c174aa364a30c73',
        annual_source_qualified_hours=8651,annual_attempted_hours=8651,annual_primary_converged_hours=8494,
        annual_equation_and_profile_qualified_hours=8494,annual_VQ_assumption_qualified_hours=0,
        recovery_attempts=314,recovered_hours=0,unresolved_hours=157,all_failed_outputs_preserved=True,
        annual_primary_outputs_overwritten=False,OPF_used=False,parameter_or_profile_fit_performed=False,
        internal_NYISO_interface_observations_read_by_PF_or_initialization=False,
        recovery_prior_seed_is_earlier_and_same_topology=True,all_8760_rows_exported=True,
        canonical_bus_count=len(axes['bus_id']),canonical_branch_count=len(axes['branch_keys']),
        monthly_files_below_100MB=True,monthly_file_records=monthly,
        physical_qualification_separate_from_convergence=True,overload_not_a_convergence_rejection=True,
        normal_voltage_range=[.95,1.05],broad_diagnostic_voltage_range=[.9,1.1],
        global_infeasibility_claimed=False,source_profile_constraints_satisfied_for_all_hours=False,
        source_code_changed_after_annual_launch='Only EOF progress-status bookkeeping; numerical body was unchanged. Final progress was refreshed after worker exit.',
        annual_core_was_not_rerun=True,numerical_backend='MATLAB R2026a; MATPOWER8.1 legacy Newton; pf.enforce_q_lims0 primary; mode1 separate seven-hour sensitivity',
        source_data=[record(p) for p in sorted(set(inputs))],source_code=[record(p) for p in sorted(set(code))],
        evidence=[record(p) for p in evidence])
    TARGET.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(passed=True,baseline_records=len(old_records),code_files=len(receipt['source_code']),
        evidence_files=len(evidence),receipt_sha256=sha(TARGET),solved_hours=8494,unresolved=157,VQ_qualified=0)))


if __name__=='__main__':main()
