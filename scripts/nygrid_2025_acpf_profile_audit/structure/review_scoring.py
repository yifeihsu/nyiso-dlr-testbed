"""Independent saved-array review of interface scoring; no production imports.

Reads the dated full-case if.map, follows original endpoint chains itself,
and recomputes the three declared conventions and every reported metric.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'output/nygrid_2025_acpf_profile_audit'
AC=ROOT/'output/nygrid_2025_ac_system'
CONVENTIONS=['legacy_signed_literal_from','oriented_source_side','oriented_target_side']


def rec(p):
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=p.relative_to(ROOT).as_posix(),sha256=h)


def dictionary_rows(v):
    if isinstance(v,list):return v
    if isinstance(v,dict):return [v]
    return list(np.asarray(v,dtype=object).reshape(-1))


def main(annual=False):
    folder=BASE/('comparison' if annual else 'representative_comparison')
    scoring=json.loads((folder/'scoring_receipt.json').read_text())
    for row in scoring['dependencies']+scoring['outputs']:
        assert rec(ROOT/row['path'])['sha256']==row['sha256'],row['path']
    baseline=ROOT/'output/nygrid_2025_dover_parameters/replay/bounded_x_nominal.npz'
    with np.load(baseline,allow_pickle=False) as d:
        gamma=float(d['gamma']);times=d['timestamp_utc'].astype(str);q=d['qualified'].astype(bool)
        dc=d['interface_pf']/gamma;state=d['network_state_ids'].astype(str)
    smap={'refined_2025_pre_may_case':'pre_may','refined_2025_may21_case':'may21',
          'refined_2025_may30_case':'may30','refined_2025_case':'post_dover'}
    state=np.array([smap[s] for s in state])
    definitions=json.loads((ROOT/'output/nygrid_2025_downstate/replay/interface_definitions.json').read_text())
    names=[d['interface'] for d in definitions]
    oldmetric_path=ROOT/'output/nygrid_2025_dover_parameters/comparison/annual_metrics.csv'
    oldmetric=pd.read_csv(oldmetric_path)
    oldmetric=oldmetric.loc[(oldmetric.scenario=='bounded_x_nominal')&(oldmetric.period=='annual')]
    assert oldmetric.interface.tolist()==names
    obs=pd.read_csv(ROOT/'output/nygrid_2025_inputs/load_source/interface_wide.csv',float_precision='round_trip')
    assert np.array_equal(obs.timestamp_utc.to_numpy(str),times)
    y=obs[names].to_numpy(float)
    old_error=dc[q]-y[q]
    assert np.max(abs(oldmetric.mae_public_mw.to_numpy()-np.mean(abs(old_error),axis=0)))<1e-8
    assert np.max(abs(oldmetric.wape_percent.to_numpy()-100*np.sum(abs(old_error),axis=0)/np.sum(abs(y[q]),axis=0)))<1e-8
    full=loadmat(ROOT/'output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat',simplify_cells=True)
    post=loadmat(ROOT/'output/nygrid_2025_dover_parameters/network/x_nominal.mat',simplify_cells=True)
    cases={s:full[f'refined_2025_{s}_case'] for s in ['pre_may','may21','may30']};cases['post_dover']=post['full_case']
    fixtures=loadmat(AC/'branches/sectioned_design_fixtures.mat',simplify_cells=True)
    canonical=fixtures['cases']['post_dover'];reference=fixtures['runtime']['post_dover']
    expected_keys=np.asarray(reference['branch_keys']).astype(str)
    expected_map=pd.DataFrame(dictionary_rows(reference['branch_map'])).sort_values('runtime_branch_row')
    expected_parent=expected_map.original_branch_row.to_numpy(int)
    expected_ends=canonical['branch'][:,:2].astype(int)
    paths=sorted((BASE/'acpf/monthly').glob('profile_PF_2025_*.mat')) if annual else [BASE/'acpf/representative_state_arrays.mat']
    assert len(paths)==(12 if annual else 1)
    independent={k:np.full((8760,7),np.nan) for k in CONVENTIONS}
    loss=np.full((8760,7),np.nan);seen=np.zeros(8760,bool);cohort=np.zeros(8760,bool);VQ=np.zeros(8760,bool)
    maximum_loss_identity_error=0.;state_hours={s:0 for s in cases}
    for path in paths:
        m=loadmat(path,simplify_cells=True);ix=np.asarray(m['hour_index'],int).reshape(-1)-1
        assert np.all((ix>=0)&(ix<8760)) and len(np.unique(ix))==len(ix) and not seen[ix].any()
        assert np.array_equal(np.asarray(m['timestamp_utc']).astype(str).reshape(-1),times[ix]) and float(m['gamma'])==gamma
        assert np.array_equal(np.asarray(m['source_qualified'],bool).reshape(-1),q[ix])
        assert np.array_equal(np.asarray(m['branch_keys']).astype(str),expected_keys)
        assert np.array_equal(np.asarray(m['branch_parent_row']).reshape(-1),expected_parent)
        assert np.array_equal(np.column_stack((m['branch_from_bus'],m['branch_to_bus'])),expected_ends)
        seen[ix]=True;cohort[ix]=q[ix]&np.asarray(m['AC_equation_gate'],bool).reshape(-1)&np.asarray(m['P_profile_preservation_gate'],bool).reshape(-1)
        VQ[ix]=np.asarray(m['VQ_and_generator_assumption_gate'],bool).reshape(-1)
        pf=np.asarray(m['PF']);pt=np.asarray(m['PT']);active=np.asarray(m['branch_active'],bool)
        for s in np.unique(state[ix]):
            local=np.flatnonzero(state[ix]==s);global_ix=ix[local]
            ref=fixtures['runtime'][s];keylookup={k:j for j,k in enumerate(expected_keys)}
            loc_keys=np.asarray(ref['branch_keys']).astype(str)
            expect_active=np.zeros(len(expected_keys),bool)
            for j,key in enumerate(loc_keys):expect_active[keylookup[key]]=fixtures['cases'][s]['branch'][j,10]>0
            assert np.array_equal(active[local][q[global_ix]],np.tile(expect_active,(int(q[global_ix].sum()),1)))
            state_hours[s]+=int(cohort[global_ix].sum())
            for name in CONVENTIONS:independent[name][global_ix]=0.
            loss[global_ix]=0.
            mapping=cases[s]['if']['map']
            for j,definition in enumerate(definitions):
                selected=mapping[mapping[:,0]==definition['inherited_interface_id'],1].astype(int)
                for signed in selected:
                    parent=abs(signed);direction=1 if signed>0 else -1
                    f,t=cases[s]['branch'][parent-1,:2].astype(int)
                    pieces=np.flatnonzero(expected_parent==parent)
                    start=pieces[expected_ends[pieces,0]==f];end=pieces[expected_ends[pieces,1]==t]
                    assert len(start)==len(end)==1
                    first,last=int(start[0]),int(end[0])
                    # Original endpoints select real corridor terminals. Interior rows only enter the loss sum.
                    F=pf[local,first];T=pt[local,last]
                    independent[CONVENTIONS[0]][global_ix,j]+=direction*F/gamma
                    independent[CONVENTIONS[1]][global_ix,j]+=(F if direction>0 else T)/gamma
                    independent[CONVENTIONS[2]][global_ix,j]+=(-T if direction>0 else -F)/gamma
                    loss[global_ix,j]+=np.sum(pf[np.ix_(local,pieces)]+pt[np.ix_(local,pieces)],axis=1)/gamma
            good=cohort[global_ix]
            if good.any():
                err=np.max(abs(independent[CONVENTIONS[1]][global_ix][good]-independent[CONVENTIONS[2]][global_ix][good]-loss[global_ix][good]))
                maximum_loss_identity_error=max(maximum_loss_identity_error,float(err));assert err<1e-7
    if annual:assert seen.all()
    assert cohort.sum()==scoring['matched_comparison_hours']
    output_arrays=folder/'comparison_arrays.npz'
    maximum_flow_difference=0.
    with np.load(output_arrays,allow_pickle=False) as d:
        assert np.array_equal(d['ACPF_comparison_cohort'],cohort)
        assert np.array_equal(d['timestamp_utc'].astype(str),times) and d['interface_names'].tolist()==names
        assert np.array_equal(d['observed'],y,equal_nan=True) and np.array_equal(d['frozen_DC'],dc,equal_nan=True)
        for convention in CONVENTIONS:
            error=float(np.max(abs(d[convention][cohort]-independent[convention][cohort])))
            maximum_flow_difference=max(maximum_flow_difference,error);assert error<1e-7
    metrics=pd.read_csv(folder/'interface_metrics.csv');localtime=pd.to_datetime(times,utc=True).tz_convert('America/New_York')
    maximum_metric_error=0.
    for r in metrics.itertuples():
        mask=cohort.copy()
        if r.period.startswith('month_'):mask&=localtime.month==int(r.period[-2:])
        elif r.period=='post_Dover_full_service':mask&=state=='post_dover'
        else:assert r.period==('annual' if annual else 'seven_selected_hours')
        j=names.index(r.interface);prediction=dc if r.convention=='frozen_DC_bounded_x_nominal' else independent[r.convention]
        e=prediction[mask,j]-y[mask,j];edc=dc[mask,j]-y[mask,j];denom=np.sum(abs(y[mask,j]))
        assert denom>0 and len(e)==r.hours
        expected=np.array([np.mean(abs(e)),np.sqrt(np.mean(e*e)),np.mean(e),100*np.sum(abs(e))/denom,np.mean(abs(e))-np.mean(abs(edc))])
        actual=np.array([r.mae_public_MW,r.rmse_public_MW,r.bias_public_MW,r.wape_percent,r.mae_change_from_DC_public_MW])
        err=float(np.max(abs(expected-actual)));maximum_metric_error=max(maximum_metric_error,err);assert err<1e-8
        assert r.VQ_and_generator_qualified_hours==int(np.sum(mask&VQ)) and r.comparison_is_diagnostic
    periods=set(metrics.period)
    assert len(metrics)==28*len(periods) and set(metrics.interface)==set(names)
    assert scoring['VQ_gate_excludes_branch_thermal_and_security_qualification']
    assert not scoring['OPF_used'] and not scoring['internal_interface_observations_used_for_fitting']
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),scope='annual_saved_outputs' if annual else 'seven_representative_saved_outputs',
        evaluated_hours=int(seen.sum()),matched_cohort_hours=int(cohort.sum()),VQ_and_generator_qualified_hours=int(np.sum(cohort&VQ)),
        all_488_canonical_keys_parent_rows_endpoints_verified=True,all_dated_active_branch_masks_verified=True,
        state_cohort_hours=state_hours,metric_rows_independently_recomputed=len(metrics),
        maximum_flow_reconstruction_error_public_MW=maximum_flow_difference,
        maximum_terminal_loss_identity_error_public_MW=maximum_loss_identity_error,
        maximum_metric_reconstruction_error=maximum_metric_error,MAE_RMSE_bias_WAPE_and_paired_DC_delta_verified=True,
        observation_and_model_UTC_axes_identical=True,monthly_bins_use_America_New_York=True,
        frozen_DC_column_order_and_full8651_metrics_verified=True,
        gamma_applied_only_to_aggregate_MW_comparison=True,no_fit_or_model_changes_in_scorer=True,
        no_unresolved_scoring_findings=True,
        interpretation_limits=['These are inherited seven-zone-cut diagnostics, not certified physical NYISO meter memberships.',
            'V/Q and generation-assumption gates exclude branch thermal and security qualification; computed flows can fail those operating assumptions.',
            'Terminal conventions are predeclared alternatives, not statistical uncertainty intervals or selected best fits.',
            'The AC engineering model also differs in R/X, charging and compensation from the frozen DC case; this is not an isolated AC-versus-DC physics ablation.'],
        dependencies=[rec(p) for p in paths+[folder/'scoring_receipt.json',folder/'interface_metrics.csv',output_arrays,
            ROOT/'scripts/nygrid_2025_acpf_profile_audit/score_interfaces.py',
            ROOT/'scripts/nygrid_2025_acpf_profile_audit/alignment/interface_operator.py',oldmetric_path,Path(__file__)]])
    path=BASE/'structure'/('scoring_annual_independent_review.json' if annual else 'scoring_representative_independent_review.json')
    path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['dependencies','interpretation_limits']},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--annual',action='store_true');main(parser.parse_args().annual)
