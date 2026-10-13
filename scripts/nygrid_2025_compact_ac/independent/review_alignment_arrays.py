"""Independently reconstruct compact interfaces from original endpoint chains.

No production interface operator or scorer is imported. This validates the
declared diagnostic convention and arithmetic, not physical meter membership.
"""
from pathlib import Path
from datetime import datetime,timezone
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat
from probe_kron_feasibility import rec

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'output/nygrid_2025_compact_ac'
CONVENTIONS=['legacy_signed_literal_from','oriented_source_side','oriented_target_side']


def main():
    folder=BASE/'alignment';paths=[Path(__file__),Path(__file__).with_name('probe_kron_feasibility.py')]
    scoring_path=folder/'scoring_receipt.json';scoring=json.loads(scoring_path.read_text());paths.append(scoring_path)
    assert scoring['passed'] and scoring['comparison_complete']
    for dep in scoring['dependencies']+scoring['outputs']:
        assert rec(ROOT/dep['path'])['sha256']==dep['sha256'],dep['path']
    annual_path=BASE/'independent/annual_arrays_independent_review.json'
    annual=json.loads(annual_path.read_text());assert annual['passed'];paths.append(annual_path)
    src=ROOT/'output/nygrid_2025_dover_parameters/replay/bounded_x_nominal.npz';paths.append(src)
    with np.load(src,allow_pickle=False) as d:
        gamma=float(d['gamma']);times=d['timestamp_utc'].astype(str);q=d['qualified'].astype(bool)
        source_state=d['network_state_ids'].astype(str)
    states=np.asarray([{'refined_2025_pre_may_case':'pre_may','refined_2025_may21_case':'may21',
                         'refined_2025_may30_case':'may30','refined_2025_case':'post_dover'}[s] for s in source_state])
    definitions_path=ROOT/'output/nygrid_2025_downstate/replay/interface_definitions.json';paths.append(definitions_path)
    definitions=json.loads(definitions_path.read_text());names=[d['interface'] for d in definitions]
    observed_path=ROOT/'output/nygrid_2025_inputs/load_source/interface_wide.csv';paths.append(observed_path)
    observed=pd.read_csv(observed_path,float_precision='round_trip');y=observed[names].to_numpy(float)
    assert np.array_equal(observed.timestamp_utc.to_numpy(str),times)
    cases_path=ROOT/'output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat'
    post_path=ROOT/'output/nygrid_2025_dover_parameters/network/x_nominal.mat';paths.extend([cases_path,post_path])
    full=loadmat(cases_path,simplify_cells=True);post=loadmat(post_path,simplify_cells=True)
    cases={s:full[f'refined_2025_{s}_case'] for s in ['pre_may','may21','may30']};cases['post_dover']=post['full_case']
    arrays={model:{c:np.full((8760,7),np.nan) for c in CONVENTIONS+['oriented_source_minus_target_loss']}
            for model in ['compact','detailed']}
    cohorts={model:np.zeros(8760,bool) for model in arrays};seen=np.zeros(8760,bool)
    maximum_loss_error=0.
    for month in range(1,13):
        for model,folder2 in [('compact',BASE/'validation/monthly'),('detailed',ROOT/'output/nygrid_2025_acpf_profile_audit/acpf/monthly')]:
            p=folder2/f'profile_PF_2025_{month:02d}.mat';paths.append(p)
            m=loadmat(p,simplify_cells=True);h=np.asarray(m['hour_index'],int)-1
            assert np.array_equal(np.asarray(m['timestamp_utc']).astype(str),times[h]) and float(m['gamma'])==gamma
            good=q[h]&np.asarray(m['AC_equation_gate'],bool)&np.asarray(m['P_profile_preservation_gate'],bool)
            if model=='compact':
                good&=np.asarray(m['reduction_and_equation_gate'],bool)&(np.asarray(m['native_retained_bus_count'])==148)
                assert not seen[h].any();seen[h]=True
            cohorts[model][h]=good
            parent=np.asarray(m['branch_parent_row'],int);ends=np.column_stack([m['branch_from_bus'],m['branch_to_bus']]).astype(int)
            pf=np.asarray(m['PF']);pt=np.asarray(m['PT'])
            for s in np.unique(states[h]):
                rows=np.flatnonzero((states[h]==s)&good);gh=h[rows]
                if not len(rows):continue
                for c in arrays[model]:arrays[model][c][gh]=0.
                mapping=cases[s]['if']['map']
                for j,d in enumerate(definitions):
                    for signed in mapping[mapping[:,0]==d['inherited_interface_id'],1].astype(int):
                        p=abs(signed);sign=1 if signed>0 else -1;pieces=np.flatnonzero(parent==p)
                        f,t=cases[s]['branch'][p-1,:2].astype(int)
                        first=pieces[ends[pieces,0]==f];last=pieces[ends[pieces,1]==t]
                        assert len(first)==len(last)==1
                        assert np.asarray(m['branch_active'],bool)[np.ix_(rows,pieces)].all()
                        assert np.asarray(m['branch_present'],bool)[np.ix_(rows,pieces)].all()
                        F=pf[rows,first[0]];T=pt[rows,last[0]]
                        arrays[model][CONVENTIONS[0]][gh,j]+=sign*F/gamma
                        arrays[model][CONVENTIONS[1]][gh,j]+=(F if sign>0 else T)/gamma
                        arrays[model][CONVENTIONS[2]][gh,j]+=(-T if sign>0 else -F)/gamma
                        arrays[model]['oriented_source_minus_target_loss'][gh,j]+=np.sum(pf[np.ix_(rows,pieces)]+pt[np.ix_(rows,pieces)],axis=1)/gamma
                error=np.max(abs(arrays[model][CONVENTIONS[1]][gh]-arrays[model][CONVENTIONS[2]][gh]-arrays[model]['oriented_source_minus_target_loss'][gh]))
                maximum_loss_error=max(maximum_loss_error,float(error));assert error<1e-7
    assert seen.all() and cohorts['detailed'].sum()==8494
    paired=cohorts['detailed']&cohorts['compact'];new=cohorts['compact']&~cohorts['detailed']
    assert paired.sum()==annual['independently_equivalent_detailed_pairs']
    assert (np.flatnonzero(new)+1).tolist()==annual['new_compact_qualified_prior_full_NR_failed_hours']
    maximum_flow_error=0.
    output_path=folder/'comparison_arrays.npz';paths.append(output_path)
    with np.load(output_path,allow_pickle=False) as d:
        assert np.array_equal(d['hour_index'],np.arange(1,8761)) and np.array_equal(d['timestamp_utc'].astype(str),times)
        assert d['interface_names'].tolist()==names and float(d['gamma'])==gamma
        assert np.array_equal(d['observed'],y,equal_nan=True)
        for name,value in [('source_qualified',q),('frozen_detailed_qualified',cohorts['detailed']),('compact_qualified',cohorts['compact']),('paired_qualified',paired),('compact_only_success',new)]:
            assert np.array_equal(d[name],value)
        for model,values in arrays.items():
            valid=cohorts[model]
            for convention,value in values.items():
                e=float(np.max(abs(d[model+'_'+convention][valid]-value[valid]),initial=0))
                maximum_flow_error=max(maximum_flow_error,e);assert e<1e-7
                if model=='compact':assert np.isnan(d[model+'_'+convention][~valid]).all()
    metrics_path=folder/'public_interface_metrics.csv';paths.append(metrics_path)
    metrics=pd.read_csv(metrics_path);local=pd.to_datetime(times,utc=True).tz_convert('America/New_York')
    maximum_metric_error=0.
    masks={'paired_frozen_detailed':paired,'compact_all_equation_qualified':cohorts['compact'],'compact_only_successes':new}
    unique=set()
    for r in metrics.itertuples():
        rowkey=(r.cohort,r.period,r.model,r.convention,r.interface);assert rowkey not in unique;unique.add(rowkey)
        mask=masks[r.cohort].copy()
        if r.period.startswith('month_'):mask&=local.month==int(r.period[-2:])
        elif r.period=='post_Dover':mask&=states=='post_dover'
        else:assert r.period=='annual'
        model={'compact_recovered':'compact','frozen_detailed':'detailed'}[r.model]
        if model=='detailed':assert r.cohort=='paired_frozen_detailed'
        j=names.index(r.interface);e=arrays[model][r.convention][mask,j]-y[mask,j]
        assert np.isfinite(e).all() and len(e)==r.hours
        denominator=np.sum(abs(y[mask,j]));assert denominator>0
        values=[np.mean(abs(e)),np.sqrt(np.mean(e*e)),np.mean(e),100*np.sum(abs(e))/denominator]
        actual=[r.mae_public_MW,r.rmse_public_MW,r.bias_public_MW,r.wape_percent]
        err=float(np.max(abs(np.asarray(values)-actual)));maximum_metric_error=max(maximum_metric_error,err);assert err<1e-8
        assert r.diagnostic_only and not r.physical_P32_meter_certified
    expected=set()
    for cname,base in masks.items():
        for period,mask in [('annual',base)]+[(f'month_{i:02d}',base&(local.month==i)) for i in range(1,13)]+[('post_Dover',base&(states=='post_dover'))]:
            if not mask.any():continue
            for model in (['frozen_detailed','compact_recovered'] if cname=='paired_frozen_detailed' else ['compact_recovered']):
                for convention in CONVENTIONS:
                    for name in names:expected.add((cname,period,model,convention,name))
    assert unique==expected
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
                scope='Independent original-terminal flow reconstruction and all public-interface metric rows',
                compact_qualified_hours=int(cohorts['compact'].sum()),fixed_detailed_cohort_hours=int(cohorts['detailed'].sum()),
                paired_hours=int(paired.sum()),compact_only_success_hours=int(new.sum()),
                metric_rows_independently_recomputed=len(metrics),
                maximum_interface_reconstruction_error_public_MW=maximum_flow_error,
                maximum_terminal_loss_identity_error_public_MW=maximum_loss_error,
                maximum_metric_reconstruction_error=maximum_metric_error,
                all_three_predeclared_original_terminal_conventions_verified=True,
                saved_reduced_edges_not_used_as_physical_interface_flows=True,
                original_branch_chains_and_active_presence_verified=True,
                source_timestamp_gamma_and_fixed_cohort_verified=True,
                MAE_RMSE_bias_WAPE_and_exact_period_coverage_verified=True,
                gamma_only_applies_to_aggregate_interface_MW=True,
                public_comparison_remains_diagnostic_not_physical_meter_certification=True,
                dependencies=[rec(p) for p in dict.fromkeys(paths)])
    target=BASE/'independent/alignment_scoring_independent_review.json';target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='dependencies'},indent=2))


if __name__=='__main__':main()
