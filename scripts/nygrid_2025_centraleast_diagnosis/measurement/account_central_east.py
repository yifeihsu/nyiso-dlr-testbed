"""Reproduce CE-VC errors and original-terminal accounting without PF/fitting.

Branch contributions explain an arithmetic flow change. They are not causal
effects of independently changing a branch or of switching DC to AC physics.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_centraleast_diagnosis/measurement'
HEAD = '6dcc77f071a9ce4aaaa2fcba9a9aabc15f7d5dbc'
OLD = ROOT / 'output/nygrid_2025_acpf_profile_audit'
NAME = 'CENTRAL EAST - VC'
MEMBERS = np.array([33,36,40,42,224])
SIGNS = np.array([-1,-1,-1,-1,1])
sys.path.insert(0, str(ROOT / 'scripts/nygrid_2025_acpf_profile_audit/alignment'))
from interface_operator import build_runtime_operator, CONVENTIONS


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()


def record(path):
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path))


def preserved_baselines():
    result = []; files = []
    for name in ['nygrid_2025_ac_system','nygrid_2025_acpf_profile_audit','nygrid_2025_compact_ac']:
        rel = f'output/{name}/DELIVERY_MANIFEST.json'; p = ROOT / rel
        committed = subprocess.check_output(['git','show',HEAD + ':' + rel], cwd=ROOT)
        assert p.read_bytes() == committed
        d = json.loads(committed)
        for relative, expected in d['files'].items():
            f = ROOT / relative
            assert sha(f) == expected['sha256'] and f.stat().st_size == expected['bytes'], relative
        files.append(p)
        result.append(dict(namespace=name, file_records=len(d['files']), manifest_sha256=sha(p)))
    return result, files


def metrics(predicted, observed, mask):
    x, y = predicted[mask], observed[mask]
    assert len(x) and np.isfinite(x).all() and np.isfinite(y).all()
    error = x - y; absolute = np.abs(error)
    out = dict(hours=len(x), mean_observed_public_MW=float(y.mean()), mean_prediction_public_MW=float(x.mean()),
        observed_absolute_sum_public_MWh=float(np.abs(y).sum()),
        absolute_error_sum_public_MWh=float(absolute.sum()),
        MAE_public_MW=float(absolute.mean()), RMSE_public_MW=float(np.sqrt(np.square(error).mean())),
        bias_public_MW=float(error.mean()), WAPE_percent=float(100 * absolute.sum() / np.abs(y).sum()),
        underprediction_hours=int((error < 0).sum()), overprediction_hours=int((error > 0).sum()),
        zero_error_hours=int((error == 0).sum()))
    for label, quantile in [('min',0),('p01',.01),('p05',.05),('p25',.25),('p50',.5),('p75',.75),('p95',.95),('p99',.99),('max',1)]:
        out[f'signed_error_{label}_public_MW'] = float(np.quantile(error, quantile))
    for label, quantile in [('p50',.5),('p90',.9),('p95',.95),('p99',.99),('max',1)]:
        out[f'absolute_error_{label}_public_MW'] = float(np.quantile(absolute, quantile))
    return out


def period_masks(local, state):
    return [('annual',np.ones(len(local),bool))] + [(f'month_{m:02d}',local.month == m) for m in range(1,13)] + [
        (f'state_{s}',state == s) for s in ['pre_may','may21','may30','post_dover']]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    preserved, dependencies = preserved_baselines()
    paths = {
        'dc': ROOT / 'output/nygrid_2025_dover_parameters/replay/bounded_x_nominal.npz',
        'ac': OLD / 'comparison/comparison_arrays.npz',
        'public': ROOT / 'output/nygrid_2025_inputs/load_source/interface_wide.csv',
        'quality': ROOT / 'output/nygrid_2025_inputs/load_source/interface_quality_wide.csv',
        'catalog': ROOT / 'output/nygrid_2025_inputs/load_source/hour_catalog.csv',
        'pre_slim': ROOT / 'output/nygrid_2025_line_parameters/overlays/engineering_nominal/network_cases.mat',
        'pre_full': ROOT / 'output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat',
        'post': ROOT / 'output/nygrid_2025_dover_parameters/network/x_nominal.mat',
        'operator': OLD / 'alignment/interface_operator_contract.json',
        'raw_check': OUT / 'raw_source_check.json',
    }
    dependencies += list(paths.values()) + [Path(__file__), ROOT / 'scripts/nygrid_2025_acpf_profile_audit/alignment/interface_operator.py']
    start_records = [record(p) for p in dependencies]
    raw_check = json.loads(paths['raw_check'].read_text()); assert raw_check['passed']
    original_operator = json.loads(paths['operator'].read_text())
    for r in original_operator['source_receipts']:
        p = ROOT / r['path']; assert sha(p) == r['sha256']; dependencies.append(p)
    dc = np.load(paths['dc'], allow_pickle=False); ac = np.load(paths['ac'], allow_pickle=False)
    catalog = pd.read_csv(paths['catalog']); public = pd.read_csv(paths['public'], float_precision='round_trip')
    quality = pd.read_csv(paths['quality'])
    hours = dc['hour_index']; times = dc['timestamp_utc'].astype(str); gamma = float(dc['gamma'])
    source = dc['qualified'].astype(bool); paired = ac['ACPF_comparison_cohort'].astype(bool)
    names = ac['interface_names'].astype(str).tolist(); ce = names.index(NAME); te = names.index('TOTAL EAST')
    assert ce == 4 and te == 2 and len(hours) == 8760
    assert np.array_equal(hours, np.arange(1,8761)) and np.array_equal(hours, ac['hour_index'])
    assert np.array_equal(times, ac['timestamp_utc']) and np.array_equal(times, catalog.timestamp_utc)
    assert np.array_equal(times, public.timestamp_utc) and np.array_equal(times, quality.timestamp_utc)
    assert np.array_equal(source, ac['source_qualified']) and float(ac['gamma']) == gamma
    assert source.sum() == 8651 and paired.sum() == 8494 and np.all(~paired | source)
    assert quality[NAME].to_numpy(bool)[source].all()
    y = public[NAME].to_numpy(float)
    assert np.array_equal(y, ac['observed'][:,ce], equal_nan=True)
    assert np.allclose(dc['interface_pf'][source,ce] / gamma, ac['frozen_DC'][source,ce], rtol=0, atol=1e-10)
    state = np.array([{'refined_2025_pre_may_case':'pre_may','refined_2025_may21_case':'may21',
        'refined_2025_may30_case':'may30','refined_2025_case':'post_dover'}[s] for s in dc['network_state_ids']])
    local = pd.to_datetime(times, utc=True).tz_convert('America/New_York')
    periods = period_masks(local, state)
    pre = loadmat(paths['pre_slim'], simplify_cells=True); full_pre = loadmat(paths['pre_full'], simplify_cells=True)
    post = loadmat(paths['post'], simplify_cells=True)
    dc_raw = np.full((8760,len(MEMBERS)),np.nan); parameter_rows = []; recovery_errors = []
    for s in np.unique(state):
        mask = source & (state == s); ix = np.flatnonzero(mask); raw_state = dc['network_state_ids'][ix[0]]
        if s == 'post_dover':
            full, rec, ids = post['full_case'],post['recovery'],post['kept_bus_ids']
        else:
            full, rec, ids = full_pre[raw_state],pre['recovery'][str(raw_state).replace('_case','')],pre['kept_bus_ids']
        assert len(ids) == 148
        stored_map = full['if']['map']
        assert sorted(stored_map[stored_map[:,0] == 5,1].astype(int)) == [-42,-40,-36,-33]
        difference = np.zeros(len(full['branch']))
        for interface_id, factor in [(3,1),(5,-1)]:
            for signed in stored_map[stored_map[:,0] == interface_id,1].astype(int): difference[abs(signed)-1] += factor*np.sign(signed)
        assert np.flatnonzero(difference).tolist() == [223] and difference[223] == 1
        va = np.deg2rad(dc['bus_va'][ix]); rows = MEMBERS - 1
        lifted = va @ rec['branch_angle_matrix'][rows].T + rec['branch_flow_offset'][rows]
        if s == 'post_dover': lifted += np.deg2rad(dc['bank_shift_model_deg'][ix]) @ rec['branch_flow_phase_basis'][rows].T
        direct = np.zeros_like(lifted)
        for j, parent in enumerate(MEMBERS):
            b = full['branch'][parent-1]; f,t = int(b[0]),int(b[1]); tap = float(b[8]) or 1.
            assert b[10] > 0 and f in ids and t in ids
            fi,ti = np.flatnonzero(ids == f)[0],np.flatnonzero(ids == t)[0]
            direct[:,j] = full['baseMVA'] * (va[:,fi]-va[:,ti]-np.deg2rad(b[9])) / (b[3]*tap)
            bnames = dict(zip(full['bus'][:,0].astype(int),full['bus_name']))
            parameter_rows.append(dict(state=s, original_branch_row=int(parent), role='CE_member' if j<4 else 'TotalEast_minus_CE_residual',
                coefficient=int(SIGNS[j]), from_bus=f,to_bus=t,model_from_bus_name=str(bnames[f]),model_to_bus_name=str(bnames[t]),
                DC_source_R_pu=float(b[2]),DC_source_X_pu=float(b[3]),DC_source_B_pu=float(b[4]),tap=tap,phase_shift_deg=float(b[9]),
                both_original_terminals_retained_in148=True, physical_P32_circuit_binding_certified=False))
        assert np.max(np.abs(direct-lifted)) < 1e-9
        dc_raw[ix] = direct
        ce_error = np.max(np.abs(-direct[:,:4].sum(axis=1)-dc['interface_pf'][ix,ce]))
        te_error = np.max(np.abs(-direct[:,:4].sum(axis=1)+direct[:,4]-dc['interface_pf'][ix,te]))
        assert max(ce_error,te_error) < 1e-8
        recovery_errors.append(dict(state=s,source_hours=len(ix),maximum_direct_vs_affine_member_error_model_MW=float(np.max(np.abs(direct-lifted))),
            maximum_member_sum_vs_archived_CE_error_model_MW=float(ce_error),maximum_member_sum_vs_archived_TotalEast_error_model_MW=float(te_error)))
    dc_terms = dc_raw * SIGNS / gamma
    ac_terms = {c:np.full_like(dc_raw,np.nan) for c in CONVENTIONS}
    losses = np.full_like(dc_raw,np.nan); terminal_rows = []; seen = np.zeros(8760,bool)
    for path in sorted((OLD/'acpf/monthly').glob('profile_PF_2025_*.mat')):
        m = loadmat(path, simplify_cells=True, variable_names=['hour_index','timestamp_utc','gamma','source_qualified','AC_equation_gate',
            'P_profile_preservation_gate','branch_keys','branch_parent_row','branch_from_bus','branch_to_bus','branch_active','branch_present','PF','PT'])
        ix = np.asarray(m['hour_index'],int).reshape(-1)-1
        assert not seen[ix].any() and np.array_equal(np.asarray(m['timestamp_utc']).astype(str).reshape(-1),times[ix])
        assert float(m['gamma']) == gamma and np.array_equal(np.asarray(m['source_qualified'],bool).reshape(-1),source[ix])
        good = source[ix] & np.asarray(m['AC_equation_gate'],bool).reshape(-1) & np.asarray(m['P_profile_preservation_gate'],bool).reshape(-1)
        assert np.array_equal(good,paired[ix]); seen[ix] = True
        branch = np.column_stack((m['branch_from_bus'],m['branch_to_bus'])); parents = np.asarray(m['branch_parent_row'],int)
        for s in np.unique(state[ix]):
            local_rows = np.flatnonzero(good & (state[ix] == s)); global_rows = ix[local_rows]
            if not len(local_rows): continue
            operator = build_runtime_operator(branch,parents,str(s))
            for j,parent in enumerate(MEMBERS):
                interface = NAME if j<4 else 'TOTAL EAST'
                terms = [r for r in operator['terms'] if r['interface']==interface and r['original_branch_row']==parent]
                assert len(terms)==1;term=terms[0];first=term['first_runtime_branch_row']-1;last=term['last_runtime_branch_row']-1
                assert term['coefficient']==SIGNS[j]
                chain = np.flatnonzero(parents==parent)
                assert np.asarray(m['branch_active'],bool)[np.ix_(local_rows,chain)].all()
                pf = m['PF'][local_rows,first];pt = m['PT'][local_rows,last]
                ac_terms[CONVENTIONS[0]][global_rows,j] = SIGNS[j]*pf/gamma
                ac_terms[CONVENTIONS[1]][global_rows,j] = (pf if SIGNS[j]>0 else pt)/gamma
                ac_terms[CONVENTIONS[2]][global_rows,j] = (-pt if SIGNS[j]>0 else -pf)/gamma
                loss = np.sum(m['PF'][np.ix_(local_rows,chain)] + m['PT'][np.ix_(local_rows,chain)],axis=1)/gamma
                assert np.max(np.abs(loss-(pf+pt)/gamma)) < 1e-5
                losses[global_rows,j] = loss
                terminal_rows.append(dict(state=s,original_branch_row=int(parent),first_canonical_branch_key=str(m['branch_keys'][first]),
                    last_canonical_branch_key=str(m['branch_keys'][last]),section_count=len(chain),sign=int(SIGNS[j])))
        dependencies.append(path)
    assert seen.all()
    dc_ce = dc_terms[:,:4].sum(axis=1);dc_te = dc_ce + dc_terms[:,4]
    ac_ce = {c:terms[:,:4].sum(axis=1) for c,terms in ac_terms.items()}
    for c in CONVENTIONS:
        assert np.max(np.abs(ac_ce[c][paired]-ac[c][paired,ce])) < 1e-7
        assert np.max(np.abs(ac_ce[c][paired]+ac_terms[c][paired,4]-ac[c][paired,te])) < 1e-7
    assert np.array_equal(ac_terms[CONVENTIONS[0]][paired,:4],ac_terms[CONVENTIONS[2]][paired,:4])
    loss_ce = losses[:,:4].sum(axis=1)
    assert np.max(np.abs(ac_ce[CONVENTIONS[1]][paired]-ac_ce[CONVENTIONS[2]][paired]-loss_ce[paired])) < 1e-5
    metric_rows = []
    for group,group_mask,models in [
        ('source_8651',source,{'DC':dc_ce}),
        ('matched_8494',paired,{'DC':dc_ce,**{f'AC_{c}':x for c,x in ac_ce.items()}}),
        ('excluded_AC_failed_157',source & ~paired,{'DC':dc_ce})]:
        for period,period_mask in periods:
            mask = group_mask & period_mask
            if not mask.any(): continue
            for model,prediction in models.items():metric_rows.append(dict(cohort=group,period=period,model=model,**metrics(prediction,y,mask)))
    metric_frame = pd.DataFrame(metric_rows);metric_frame.to_csv(OUT/'CE_metrics_by_cohort_period.csv',index=False,lineterminator='\n')
    hourly = catalog.copy();hourly['dated_state']=state;hourly['source_qualified']=source;hourly['AC_equation_profile_qualified']=paired
    hourly['public_CE_qualified']=quality[NAME];hourly['observed_CE_public_MW']=y
    hourly['DC_CE_public_MW']=dc_ce;hourly['DC_error_public_MW']=dc_ce-y
    for c in CONVENTIONS:
        hourly[f'AC_{c}_CE_public_MW']=ac_ce[c];hourly[f'AC_{c}_error_public_MW']=ac_ce[c]-y
        hourly[f'AC_minus_DC_{c}_public_MW']=ac_ce[c]-dc_ce
        hourly[f'absolute_error_change_{c}_public_MW']=np.abs(ac_ce[c]-y)-np.abs(dc_ce-y)
    hourly['CE_source_minus_target_loss_public_MW']=loss_ce
    hourly['DC_TotalEast_public_MW']=dc_te
    hourly['AC_TotalEast_legacy_public_MW']=ac_ce[CONVENTIONS[0]]+ac_terms[CONVENTIONS[0]][:,4]
    hourly['DC_224_signed_public_MW']=dc_terms[:,4];hourly['AC_224_legacy_signed_public_MW']=ac_terms[CONVENTIONS[0]][:,4]
    hourly.to_csv(OUT/'CE_hourly_accounting.csv',index=False,lineterminator='\n')
    member_hourly = [];member_summary = []
    for j,parent in enumerate(MEMBERS):
        frame = hourly.loc[source,['hour_index','timestamp_utc','local_timestamp','dated_state','AC_equation_profile_qualified']].copy()
        frame['original_branch_row']=parent;frame['coefficient']=SIGNS[j];frame['role']='CE_member' if j<4 else 'TotalEast_minus_CE_residual'
        frame['DC_signed_public_MW']=dc_terms[source,j]
        for c in CONVENTIONS:
            frame[f'AC_{c}_signed_public_MW']=ac_terms[c][source,j]
            frame[f'delta_{c}_public_MW']=ac_terms[c][source,j]-dc_terms[source,j]
        frame['AC_corridor_loss_public_MW']=losses[source,j];member_hourly.append(frame)
        for period,period_mask in periods:
            mask = paired & period_mask
            if not mask.any():continue
            for c in CONVENTIONS:
                delta=ac_terms[c][mask,j]-dc_terms[mask,j];total=ac_ce[c][mask]-dc_ce[mask]
                member_summary.append(dict(period=period,convention=c,original_branch_row=int(parent),role='CE_member' if j<4 else 'TotalEast_minus_CE_residual',
                    hours=int(mask.sum()),mean_DC_signed_public_MW=float(dc_terms[mask,j].mean()),mean_AC_signed_public_MW=float(ac_terms[c][mask,j].mean()),
                    mean_AC_minus_DC_public_MW=float(delta.mean()),mean_absolute_AC_minus_DC_public_MW=float(np.abs(delta).mean()),
                    median_AC_minus_DC_public_MW=float(np.median(delta)),p05_AC_minus_DC_public_MW=float(np.quantile(delta,.05)),
                    p95_AC_minus_DC_public_MW=float(np.quantile(delta,.95)),min_AC_minus_DC_public_MW=float(delta.min()),max_AC_minus_DC_public_MW=float(delta.max()),
                    signed_share_of_mean_CE_change_percent=float(100*delta.mean()/total.mean()),
                    mean_corridor_loss_public_MW=float(losses[mask,j].mean()),share_is_accounting_not_causal_attribution=True))
    pd.concat(member_hourly,ignore_index=True).to_csv(OUT/'original_member_hourly_terms.csv',index=False,lineterminator='\n')
    pd.DataFrame(member_summary).to_csv(OUT/'original_member_contributions.csv',index=False,lineterminator='\n')
    pd.DataFrame(parameter_rows).to_csv(OUT/'DC_original_member_parameters.csv',index=False,lineterminator='\n')
    pd.DataFrame(terminal_rows).drop_duplicates().to_csv(OUT/'AC_original_terminal_mapping.csv',index=False,lineterminator='\n')
    selected = hourly.loc[paired].copy()
    delta_key=f'AC_minus_DC_{CONVENTIONS[0]}_public_MW';error_key=f'absolute_error_change_{CONVENTIONS[0]}_public_MW'
    worst_delta=selected.loc[selected[delta_key].abs().nlargest(20).index].copy();worst_delta['selection_rule']='largest_absolute_AC_minus_DC_flow_shift'
    worst_error=selected.nlargest(20,error_key).copy();worst_error['selection_rule']='largest_absolute_error_worsening'
    pd.concat([worst_delta,worst_error],ignore_index=True).to_csv(OUT/'diagnostic_extreme_hours.csv',index=False,lineterminator='\n')
    e0=dc_ce[paired]-y[paired];e1=ac_ce[CONVENTIONS[0]][paired]-y[paired]
    delta=ac_ce[CONVENTIONS[0]][paired]-dc_ce[paired]
    maedelta=float(np.abs(e1).mean()-np.abs(e0).mean())
    underpenalty_change=float(2*(np.maximum(-e1,0).mean()-np.maximum(-e0,0).mean()))
    assert abs(maedelta-delta.mean()-underpenalty_change)<1e-8
    bridge_delta=float((hourly.loc[paired,'AC_TotalEast_legacy_public_MW']-dc_te[paired]).mean())
    bypass_delta=float((ac_terms[CONVENTIONS[0]][paired,4]-dc_terms[paired,4]).mean())
    assert abs(delta.mean()+bypass_delta-bridge_delta)<1e-8
    mdc=metrics(dc_ce,y,paired);mac=metrics(ac_ce[CONVENTIONS[0]],y,paired);msource=metrics(ac_ce[CONVENTIONS[1]],y,paired)
    summary=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),baseline_HEAD=HEAD,
        status='measurement_and_original_terminal_accounting_complete_no_causal_claim',interface=NAME,point_id=23330,
        gamma=gamma,source_hours=int(source.sum()),matched_hours=int(paired.sum()),excluded_source_hours=int((source&~paired).sum()),
        member_rows=[-33,-36,-40,-42],auxiliary_cut_identity='TotalEast = CentralEast + signed_original_branch224 under each matched terminal convention',
        DC_matched=mdc,AC_legacy_matched=mac,AC_source_side_matched=msource,
        DC_source_8651=metrics(dc_ce,y,source),DC_excluded_157=metrics(dc_ce,y,source&~paired),
        matched_WAPE_increase_percentage_points=mac['WAPE_percent']-mdc['WAPE_percent'],
        matched_MAE_increase_public_MW=maedelta,mean_signed_AC_minus_DC_public_MW=float(delta.mean()),
        DC_source_to_matched_WAPE_change_percentage_points=mdc['WAPE_percent']-metrics(dc_ce,y,source)['WAPE_percent'],
        DC_underprediction_hours=int((e0<0).sum()),AC_underprediction_hours=int((e1<0).sum()),
        DC_under_to_AC_over_hours=int(((e0<0)&(e1>=0)).sum()),positive_AC_minus_DC_hours=int((delta>0).sum()),
        L1_accounting=dict(identity='delta_MAE = mean_flow_shift + 2*(mean_negative_error_part_AC - mean_negative_error_part_DC)',
            mean_flow_shift_public_MW=float(delta.mean()),underprediction_penalty_change_public_MW=underpenalty_change,delta_MAE_public_MW=maedelta,
            interpretation='Exact error-sign accounting, not attribution of physical causes.'),
        terminal_convention=dict(legacy_equals_oriented_target_exactly=True,
            explanation='All four signs are negative, so legacy -PF at the literal F terminal is the oriented target-side flow.',
            mean_source_minus_target_loss_public_MW=float(loss_ce[paired].mean()),maximum_source_minus_target_loss_public_MW=float(loss_ce[paired].max()),
            source_side_minus_legacy_WAPE_percentage_points=msource['WAPE_percent']-mac['WAPE_percent'],
            diagnostic_sensitivity_not_confidence_interval=True),
        eastern_cut_accounting=dict(mean_CE_shift_public_MW=float(delta.mean()),mean_branch224_shift_public_MW=bypass_delta,
            mean_TotalEast_shift_public_MW=bridge_delta,interpretation='Exact overlapping-cut identity; no independent-branch causal effect claimed.'),
        DC_member_reconstruction_checks=recovery_errors,
        maximum_raw_public_reaggregation_difference=raw_check['maximum_compiled_vs_independent_hourly_difference'],
        raw_public_source_reaggregation_qualified_hours=raw_check['qualified_hours'],
        prior_deliveries_byte_preserved=preserved,
        no_PF_or_OPF_executed=True,no_parameter_profile_operator_or_public_observation_changes=True,
        no_interface_fitting=True,physical_P32_meter_binding_or_numeric_units_certified=False,
        accounting_is_not_causal_model_attribution=True,
        qualifications=['AC metrics use only frozen equation/profile-qualified hours; failed AC iterates are not scored.',
            'Native dispatch and external loads are reconstructed assumptions; AC operating-limit qualification remains false.',
            'The model cut is not yet bound to the exact physical NYISO P32 meter expression.',
            'The published Flow(MWH) numeric-as-MW assumption is retained, not certified by reproducing the source.',
            'Controlled physics/model bridge experiments are needed to assign causes to the measured change.'])
    for r in start_records:assert sha(ROOT/r['path'])==r['sha256'],r['path']
    dependencies=list(dict.fromkeys(dependencies))
    outputs=[p for p in OUT.glob('*.csv')]
    summary['dependencies']=[record(p) for p in dependencies]
    summary['outputs']=[record(p) for p in sorted(outputs)]
    (OUT/'measurement_receipt.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ['passed','matched_hours','matched_WAPE_increase_percentage_points','matched_MAE_increase_public_MW','mean_signed_AC_minus_DC_public_MW','terminal_convention','eastern_cut_accounting']},indent=2))


if __name__=='__main__':main()
