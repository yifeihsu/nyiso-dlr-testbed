"""Independent parameter-isolation and saved-array checks of X-only trials."""
from pathlib import Path
from datetime import datetime,timezone
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat
from review_bridge_outputs import ROOT,BASE,record,mx,flows,check_network


def main():
    out=BASE/'experiments/X_only_ablations';bridge=BASE/'experiments/representative_bridge'
    proof_path=out/'X_only_receipt.json';proof=json.loads(proof_path.read_text())
    assert proof['completed'] and proof['all_DCPF_audits_passed']
    baseline_proof_path=bridge/'bridge_receipt.json';baseline_proof=json.loads(baseline_proof_path.read_text())
    registry_path=BASE/'model_delta/x_changed_corridors.csv';registry=pd.read_csv(registry_path)
    allparents=registry.branch_row.to_numpy(int)
    selections={'restore_parent224_X':np.array([224]),'restore_parent41_X':np.array([41]),'restore_all33_X':allparents}
    paths=[Path(__file__),Path(__file__).with_name('review_bridge_outputs.py'),proof_path,baseline_proof_path,registry_path]
    rows=[];maximum_preservation=0.;maximum_recompute=0.;maximum_allX_DC_parity=0.;qualified_count=0
    for hour in proof['hours']:
        h=int(hour);bpath=bridge/f'bridge_h{h:04d}.mat';paths.append(bpath);b=loadmat(bpath,simplify_cells=True)
        original=b['detailed'];full=b['full'];parent=np.asarray(original['userdata']['ac_system']['branch_parent_row'],int)
        gamma=float(b['a']['gamma']);primary=bool(b['a']['original_eight_hour_cohort'])
        for label,chosen in selections.items():
            path=out/f'{label}_h{h:04d}.mat';paths.append(path);d=loadmat(path,simplify_cells=True);m=d['m'];a=d['a']
            assert str(a['variant'])==label and int(a['hour_index'])==h
            for name in ['bus','gen','dcline','gencost']:
                assert np.array_equal(m[name],original[name]),(h,label,name)
            keep=np.arange(original['branch'].shape[1])!=3
            assert np.array_equal(m['branch'][:,keep],original['branch'][:,keep])
            expected=original['branch'][:,3].copy();total=np.zeros(len(full['branch']))
            for p in range(1,len(full['branch'])+1):total[p-1]=original['branch'][parent==p,3].sum()
            for p in chosen:
                use=parent==p;expected[use]=original['branch'][use,3]/total[p-1]*full['branch'][p-1,3]
                assert abs(m['branch'][use,3].sum()-full['branch'][p-1,3])<1e-12
            preserve_error=mx(expected-m['branch'][:,3]);maximum_preservation=max(maximum_preservation,preserve_error);assert preserve_error<1e-14
            ledger=np.atleast_2d(d['ledger']);assert np.array_equal(ledger[:,0].astype(int),chosen)
            assert int(a['changed_parent_count'])==len(chosen)
            dc=check_network(m,d['rdc'],False);dcflow=flows(d['rdc'],parent,full);assert mx(dcflow-d['fdc'])<1e-6
            expected_values={'CE_DCPF_public_MW':dcflow[4,0]/gamma,
                             'CE_DCPF_delta_from_detailed_baseline_public_MW':(dcflow[4,0]-b['detailed_dc_if'][4,0])/gamma,
                             'CE_DCPF_minus_archived_DC_public_MW':(dcflow[4,0]-b['archived_if'][4])/gamma}
            if label=='restore_all33_X':
                error=mx(dcflow[:,0]-b['archived_if']);maximum_allX_DC_parity=max(maximum_allX_DC_parity,error);assert error<1e-7
            qualified=bool(a['AC_equation_gate']) and bool(a['P_profile_gate'])
            assert qualified==bool(a['AC_comparison_qualified'])
            if qualified:
                qualified_count+=1;ac=check_network(m,d['rac'],True);acflow=flows(d['rac'],parent,full);assert mx(acflow-d['fac'])<1e-6
                expected_values.update(CE_ACPF_public_MW=acflow[4,0]/gamma,
                    CE_ACPF_delta_from_detailed_baseline_public_MW=(acflow[4,0]-b['detailed_ac_if'][4,0])/gamma,
                    CE_ACPF_minus_archived_DC_public_MW=(acflow[4,0]-b['archived_if'][4])/gamma,
                    AC_loss_model_MW=ac['total_real_loss_MW'],slack_P_increment_model_MW=ac['slack_increment_MW'])
            for name,value in expected_values.items():
                error=abs(value-a[name]);maximum_recompute=max(maximum_recompute,error);assert error<1e-6
            rows.append(dict(hour_index=h,variant=label,original_eight_hour_cohort=primary,
                             selected_parent_count=len(chosen),active_selected_parent_count=int(np.count_nonzero(full['branch'][chosen-1,10]>0)),
                             AC_equation_and_profile_qualified=qualified,VQ_and_generator_assumption_gate=bool(a['VQ_assumption_gate']),
                             min_VM_pu=float(a['min_VM_pu']),max_VM_pu=float(a['max_VM_pu']),**expected_values))
    assert len(rows)==proof['attempts']==33 and qualified_count==proof['AC_equation_and_profile_qualified']
    table=pd.DataFrame(rows);summary=[]
    for label,g in table[table.original_eight_hour_cohort].groupby('variant',sort=False):
        summary.append(dict(variant=label,hours=len(g),
            mean_DC_delta_from_detailed_baseline_public_MW=float(g.CE_DCPF_delta_from_detailed_baseline_public_MW.mean()),
            mean_AC_delta_from_detailed_baseline_public_MW=float(g.CE_ACPF_delta_from_detailed_baseline_public_MW.mean()),
            mean_remaining_DC_gap_public_MW=float(g.CE_DCPF_minus_archived_DC_public_MW.mean()),
            mean_remaining_AC_gap_public_MW=float(g.CE_ACPF_minus_archived_DC_public_MW.mean()),
            maximum_VM_pu=float(g.max_VM_pu.max()),VQ_generator_qualified=int(g.VQ_and_generator_assumption_gate.sum())))
    # Albany bus42 is a pendant terminal; its fixed-P DC net injection fixes
    # branch41 flow, independent of its nonzero series X.
    example=loadmat(bridge/f"bridge_h{int(proof['hours'][0]):04d}.mat",simplify_cells=True)
    br=example['full']['branch'];pendant=np.flatnonzero(np.any(br[:,:2]==42,axis=1)&(br[:,10]>0))+1
    assert np.array_equal(pendant,[41]);assert not np.isin(example['full']['dcline'][:,:2],42).any()
    outcsv=BASE/'model_delta/X_only_independent_checks.csv';table.to_csv(outcsv,index=False)
    source=ROOT/'scripts/nygrid_2025_centraleast_diagnosis/experiments'
    paths.extend(source/n for n in ['restore_parent_X_only.m','run_X_only_ablations.m','physical_interface_flows.m','audit_diagnostic_DCPF.m'])
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent saved-array isolation and numerical audits for eleven-hour, three-variant X-only trials',
        attempt_count=len(rows),DC_qualified=len(rows),AC_equation_and_profile_qualified=qualified_count,
        original_eight_hour_cohort=baseline_proof['primary_hours'],additional_posthoc_diagnostic_hours=baseline_proof['additional_diagnostic_extremes'],
        selected_X_only_changed=True,all_R_B_taps_phases_status_shunts_bus_gen_gencost_and_dcline_arrays_unchanged=True,
        section_X_proportions_preserved=True,maximum_X_restoration_array_error_pu=maximum_preservation,
        maximum_recomputed_report_value_error=maximum_recompute,
        maximum_all33_X_restored_DC_all7_interface_vs_archived_error_model_MW=maximum_allX_DC_parity,
        all_qualified_DC_AC_branch_laws_KCL_and_loss_identities_passed=True,
        branch41_Albany_bus42_is_pendant_with_only_active_branch41=True,
        branch41_X_change_cannot_change_fixed_injection_lossless_DC_flow=True,
        primary_eight_hour_results=summary,
        interpretation_limits=['The X-only cases deliberately retain the AC resistance, charging and compensation; they are hybrid causal diagnostics, not conductor-realizable replacement models.',
            'Changing one parameter can interact with retained R/B and AC voltage support, so isolated AC responses do not add uniquely to the total baseline error.',
            'Restoring all33 original X values restores the lossless DC interface predictions but does not restore the original AC physics or make the hybrid AC case physically qualified.',
            'Albany branch41 has AC R0.059833 retained while X is restored0.0089, yielding R/X about6.72; its large AC response cannot be described as a practical impedance repair.',
            'These selected-hour effects are not annual WAPE changes and lower WAPE is not physical impedance validation.'],
        dependencies=[record(p) for p in dict.fromkeys(paths)],outputs=[record(outcsv)])
    (BASE/'model_delta/X_only_independent_review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['dependencies','outputs']},indent=2))


if __name__=='__main__':main()
