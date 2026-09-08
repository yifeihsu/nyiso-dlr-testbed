"""Run fixed-input, retrospective NYgrid-to-compact 2019 DC comparisons.

Network/injection construction has no access to internal observations.
Scoring is a subsequent step, after all predictions are computed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

from dc_model import DCModel, map_bus_values, port_injection_map, score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_compact_2019'
sys.path.insert(0, str(ROOT / 'scripts/nygrid_2019'))
from replay_dc import load_complete

NAMES = ['Dysinger East', 'West Central', 'Total East', 'Moses South',
         'Central East', 'UpNY-Coned', 'Dun/SPR-South']
GAMMA = .358662225381536
EXTENSION_ROLES = {774: 'G', 858: 'G', 9001: 'G', 9002: 'G', 9003: 'K'}


def write_csv(frame, name):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, float_format='%.12g', lineterminator='\n')


def load_reference():
    chunks = [load_complete(ROOT / f'output/nygrid_2019/annual_{i}.mat')[0] for i in range(1, 5)]
    c = chunks[0]['base_case']
    ids = c['bus'][:, 0].astype(int)
    ny = np.isin(ids, np.arange(37, 83))
    ny_ids = ids[ny]
    gf = c['gen'][:, 0].astype(int)
    native = np.arange(243)
    assert np.isin(gf[native], ny_ids).all()
    hq = len(gf) - 1
    assert gf[hq] == 48
    branches = c['branch'][:, :13]
    fny = np.isin(branches[:, 0], ny_ids)
    tny = np.isin(branches[:, 1], ny_ids)
    internal = fny & tny
    assert internal.sum() == 67 and (fny ^ tny).sum() == 8
    lookup = {v: k for k, v in enumerate(ny_ids)}
    values = {k: np.concatenate([m[k] for m in chunks]) for k in
              ['branch_pf', 'bus_pd', 'input_pg', 'result_pg', 'dc_pf', 'corrected_sim']}
    assert values['bus_pd'].shape == (8760, 57)
    def aggregate(pg, rows):
        r = np.zeros((8760, 46))
        for j in rows:
            r[:, lookup[gf[j]]] += pg[:, j]
        return r
    input_pg = aggregate(values['input_pg'], native)
    solved_pg = aggregate(values['result_pg'], native)
    boundary_ac = np.zeros((8760, 46))
    for j in np.flatnonzero(fny ^ tny):
        endpoint = int(branches[j, 0] if fny[j] else branches[j, 1])
        boundary_ac[:, lookup[endpoint]] += values['branch_pf'][:, j] * (-1 if fny[j] else 1)
    boundary_dc = np.zeros_like(boundary_ac)
    for j, dc in enumerate(c['dcline']):
        if int(dc[0]) in lookup:
            boundary_dc[:, lookup[int(dc[0])]] -= values['dc_pf'][:, j]
        if int(dc[1]) in lookup:
            boundary_dc[:, lookup[int(dc[1])]] += values['dc_pf'][:, j]
    boundary_hq = np.zeros_like(boundary_ac)
    boundary_hq[:, lookup[48]] = values['input_pg'][:, hq]
    boundary = boundary_ac + boundary_dc + boundary_hq
    pd_net = values['bus_pd'][:, ny]
    injection = solved_pg - pd_net + boundary - c['bus'][ny, 4]
    assert np.max(np.abs(injection.sum(axis=1))) < 1e-7
    return dict(case=c, ids=ny_ids, bus=c['bus'][ny, :13], branch=branches[internal],
                input_pg=input_pg, solved_pg=solved_pg, pd_net=pd_net,
                boundary=boundary, boundary_ac=boundary_ac, boundary_dc=boundary_dc,
                boundary_hq=boundary_hq, injection=injection,
                original_pf=values['branch_pf'][:, internal],
                corrected_sim=values['corrected_sim'],
                slack_adjustment=solved_pg-input_pg)


def paper_roles(ids):
    data = pd.read_csv(ROOT / 'tmp/nygrid_2019_reproduction/upstream/Data/npcc.csv')
    lookup = dict(zip(data.idx, data.zone)) | EXTENSION_ROLES
    roles = np.array([lookup[int(b)] for b in ids])
    assert np.isin(roles, list('ABCDEFGHIJK')).all()
    return roles


def operators(net):
    roles = paper_roles(net.ids)
    def cut(u, d):
        return net.cut(net.ids[np.isin(roles, list(u))], net.ids[np.isin(roles, list(d))])
    # Adjacent-zone semantics are the released Table-I/if.map convention.
    result = np.array([cut('A', 'B'), cut('B', 'C'), cut('E', 'FG'),
                       cut('D', 'E'), cut('E', 'F'), cut('G', 'H'), cut('I', 'J')])
    assert (np.abs(result).sum(axis=1) > 0).all()
    return result


def marcy_variant(case):
    branch = np.array(case['branch'], copy=True)
    for f, t, x in [(43, 38, .0427), (38, 77, .0147)]:
        pairs = [set(map(int, r[:2])) for r in branch if r[10] == 1]
        assert {f, t} not in pairs, 'Existing active source path would be double counted'
        # DC-only X experiment: NaN AC claims are kept in the register, not
        # the numerical case. Zero RATE_A means unrated, never infinite safety.
        branch = np.vstack([branch, [f, t, 0, x, 0, 0, 0, 0, 0, 0, 1, -360, 360]])
    return branch


def metric_rows(predictions, observed, dates):
    rows = []
    for label, pred in predictions.items():
        for period in ['annual'] + [f'month_{m:02d}' for m in range(1, 13)]:
            ix = np.ones(len(dates), dtype=bool) if period == 'annual' else dates.month == int(period[-2:])
            for j, name in list(enumerate(NAMES)) + [(None, 'ALL_SEVEN_POOLED')]:
                p, o = pred[ix], observed[ix]
                if j is not None:
                    p, o = p[:, j], o[:, j]
                err = p-o
                rows.append(dict(experiment=label, period=period, interface=name, hours=int(ix.sum()),
                                 observations=o.size, wape_pct=100*np.abs(err).sum()/np.abs(o).sum(),
                                 mae_benchmark_mw=np.abs(err).mean(), mae_actual_scale_mw=np.abs(err).mean()/GAMMA,
                                 bias_benchmark_mw=err.mean(), wrong_direction_count=int((p*o < 0).sum())))
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ref = load_reference()
    exported = loadmat(OUT / 'compact/compact_network.mat', simplify_cells=True)['network_data']
    case = exported['paper74']
    assert abs(float(exported['gamma2019'])-GAMMA) < 1e-15
    networks = {
        'reference_NY46': DCModel(ref['bus'], ref['branch']),
        'compact51': DCModel(case['bus'], case['branch']),
        'compact51_marcy': DCModel(case['bus'], marcy_variant(case)),
    }
    current_op = np.asarray(exported['current_dc_coefficients'])[[0, 1, 4, 2, 3, 5, 6]]
    coefficients = {k: operators(n) for k, n in networks.items()}
    solutions, predictions, evidence = {}, {}, []
    for label, net in networks.items():
        inj = map_bus_values(ref['injection'] * GAMMA, ref['ids'], net.ids)
        solved = net.solve(inj)
        solutions[label] = solved
        predictions[label + '__paper_roles'] = solved['flow'] @ coefficients[label].T
        if label != 'reference_NY46':
            op = np.pad(current_op, ((0, 0), (0, len(net.branch)-current_op.shape[1])))
            # Recompute changed physical-zone cuts on the added path: current
            # names/landings stay fixed, but every new member must be included.
            if label.endswith('marcy'):
                zones = np.asarray(exported['compact_physical_zones'])
                def cut(u, d=None):
                    return net.cut(net.ids[np.isin(zones, list(u))], None if d is None else net.ids[np.isin(zones, list(d))])
                op[0], op[1], op[2], op[3], op[4], op[6] = cut('A'), cut('AB'), cut('ABCDE'), cut('D'), cut('E','F'), cut('I','J')
                up = net.ids[np.isin(zones, list('ABCDEFG')) & ~np.isin(net.ids, [858, 9002])]
                op[5] = net.cut(up)
            predictions[label + '__current_roles'] = solved['flow'] @ op.T
        rate = net.branch[:, 5]
        exceed = np.maximum(np.abs(solved['flow'])-rate, 0)
        exceed[:, rate <= 0] = 0
        evidence.append(dict(network=label, buses=len(net.ids), branch_records=len(net.branch),
                             active_branches=int((net.branch[:, 10] == 1).sum()),
                             positive_rated_branches=int(((rate > 0)&(net.branch[:, 10] == 1)).sum()),
                             max_nodal_residual_mw=float(solved['nodal_residual_mw'].max()),
                             max_additional_slack_mw=float(np.abs(solved['slack_adjustment_mw']).max()),
                             hours_with_positive_rate_exceedance=int((exceed.max(axis=1)>1e-6).sum()),
                             max_positive_rate_exceedance_benchmark_mw=float(exceed.max()),
                             ac_qualified=False, dlr_qualified=False))
    reference_error = np.max(np.abs(solutions['reference_NY46']['flow'] - ref['original_pf'] * GAMMA))
    operator_error = np.max(np.abs(predictions['reference_NY46__paper_roles'] - ref['corrected_sim'] * GAMMA))
    assert reference_error < 1e-7 and operator_error < 1e-7
    write_csv(pd.DataFrame(evidence), 'dc_network_checks.csv')
    members = []
    for name, net in networks.items():
        for k, interface in enumerate(NAMES):
            for j in np.flatnonzero(coefficients[name][k]):
                members.append(dict(network=name, interface=interface, branch_row=j+1,
                                    from_bus=int(net.branch[j,0]), to_bus=int(net.branch[j,1]),
                                    coefficient=coefficients[name][k,j],
                                    observations_used=False, exact_public_metering=False))
    write_csv(pd.DataFrame(members), 'paper_role_operator_members.csv')

    # Observations first enter here, after every annual electrical solve.
    records = pd.concat([pd.read_csv(ROOT / f'output/nygrid_2019/annual_{i}_interfaces.csv') for i in range(1,5)])
    records['timestamp'] = pd.to_datetime(records.timestamp, format='%d-%b-%Y %H:%M:%S')
    dates = pd.date_range('2019-01-01', periods=8760, freq='h')
    observed = records.pivot(index='timestamp', columns='interface', values='observed_mw').loc[dates,NAMES].to_numpy()*GAMMA
    limits = records.pivot(index='timestamp', columns='interface', values='positive_limit_mw').loc[dates,NAMES].to_numpy()*GAMMA
    assert observed.shape == (8760,7) and np.isfinite(observed).all()
    metrics = metric_rows(predictions, observed, dates)
    write_csv(metrics, 'annual_monthly_metrics.csv')
    quality_columns=['imputed_interface_observations','ambiguous_interface_observations',
                     'minimum_sample_count','minimum_distinct_timestamp_count']
    quality=pd.read_csv(ROOT/'output/nygrid_2019/best_snapshots/all_hour_rankings.csv')
    quality['timestamp']=pd.to_datetime(quality.timestamp)
    assert quality.timestamp.is_unique and len(quality)==8760
    quality=quality.set_index('timestamp').loc[dates,quality_columns]
    ranks, top, details = [], [], []
    for label, pred in predictions.items():
        s = score(pred, observed)
        ranking = pd.DataFrame(dict(experiment=label, timestamp=dates,
                                   pooled_error_pct=s['pooled_error_pct'],
                                   worst_interface_error_pct=s['worst_interface_error_pct'],
                                   wrong_direction_interfaces=s['wrong_direction'].sum(axis=1)))
        for col in quality_columns:
            ranking[col]=quality[col].to_numpy()
        order = ranking.sort_values(['pooled_error_pct','timestamp']).index
        ranking.loc[order, 'pooled_rank'] = np.arange(1,8761)
        minimax = ranking.sort_values(['worst_interface_error_pct','timestamp']).index
        ranking.loc[minimax, 'minimax_rank'] = np.arange(1,8761)
        ranks.append(ranking)
        for criterion, selected in [('pooled',order[:3]), ('minimax',minimax[:3])]:
            for rank, i in enumerate(selected,1):
                top.append(dict(experiment=label, criterion=criterion, rank=rank, **ranking.loc[i].drop('experiment').to_dict()))
                for j, name in enumerate(NAMES):
                    details.append(dict(experiment=label, criterion=criterion, rank=rank, timestamp=dates[i], interface=name,
                                        observed_actual_mw=observed[i,j]/GAMMA, predicted_actual_scale_mw=pred[i,j]/GAMMA,
                                        observed_benchmark_mw=observed[i,j], predicted_benchmark_mw=pred[i,j],
                                        signed_error_benchmark_mw=s['error_mw'][i,j],
                                        absolute_error_actual_scale_mw=s['absolute_error_mw'][i,j]/GAMMA,
                                        absolute_error_pct=s['absolute_error_pct'][i,j],
                                        paper_rating_error_pct=100*(observed[i,j]-pred[i,j])/limits[i,j],
                                        wrong_direction=bool(s['wrong_direction'][i,j])))
    write_csv(pd.concat(ranks), 'all_hour_rankings.csv')
    write_csv(pd.DataFrame(top), 'best_snapshots.csv')
    write_csv(pd.DataFrame(details), 'best_snapshot_interface_errors.csv')
    np.savez_compressed(OUT/'annual_predictions.npz', timestamps=dates.astype(str).to_numpy(dtype=str),
                        interfaces=np.array(NAMES), observed_benchmark_mw=observed, gamma=GAMMA, **predictions)
    matrix, ablations, ablation_details, movements = matched_matrix(ref, networks, coefficients, observed, dates)
    write_csv(matrix, 'network_input_matrix.csv')
    write_csv(ablations, 'allocation_ablations.csv')
    write_csv(ablation_details, 'allocation_ablation_interface_errors.csv')
    write_csv(movements, 'allocation_movement_ledger.csv')
    # Export fixed-input candidate states for a separate AC attempt. Gross
    # load is loaded from the source components only when available; the net
    # load/renewable distinction is always preserved in the reference export.
    selected_label = 'compact51_marcy__paper_roles'
    ranking = pd.concat(ranks).query('experiment == @selected_label')
    selected = list(ranking.sort_values(['pooled_error_pct','timestamp']).head(3).index)
    minimax_indices = list(ranking.sort_values(['worst_interface_error_pct','timestamp']).head(3).index)
    selected = list(dict.fromkeys(selected+minimax_indices+[int(dates.get_loc('2019-01-08 15:00'))]))
    saved = []
    for i in selected:
        net=networks['compact51_marcy']
        saved.append(dict(timestamp=str(dates[i]), hour_index=i,
                          bus=net.bus, branch=net.branch, baseMVA=100., gamma=GAMMA,
                          net_pd_mw=map_bus_values(ref['pd_net'][i]*GAMMA,ref['ids'],net.ids)[0],
                          native_input_pg_bus_mw=map_bus_values(ref['input_pg'][i]*GAMMA,ref['ids'],net.ids)[0],
                          native_solved_pg_bus_mw=map_bus_values(ref['solved_pg'][i]*GAMMA,ref['ids'],net.ids)[0],
                          source_slack_adjustment_bus_mw=map_bus_values(ref['slack_adjustment'][i]*GAMMA,ref['ids'],net.ids)[0],
                          boundary_p_mw=map_bus_values(ref['boundary'][i]*GAMMA,ref['ids'],net.ids)[0],
                          dc_flow=solutions['compact51_marcy']['flow'][i],
                          dc_angle_deg=solutions['compact51_marcy']['angle_deg'][i],
                          operator_coefficients=coefficients['compact51_marcy'],
                          interface_names=np.array(NAMES,dtype=object),
                          observed_benchmark_mw=observed[i], predicted_benchmark_mw=predictions[selected_label][i]))
    savemat(OUT/'selected_dc_candidates.mat', {'candidates':np.array(saved,dtype=object)}, do_compression=True)
    summary=dict(hours=8760, gamma=GAMMA, reference_ny_only_max_branch_error_mw=float(reference_error),
                 reference_ny_only_max_interface_error_mw=float(operator_error),
                 annual_pooled=metrics.query("period=='annual' and interface=='ALL_SEVEN_POOLED'").to_dict('records'),
                 input_parameter_fitting=False, untouched_holdout=False,
                 preferred_2025_baseline_changed=False,
                 boundary_source='NYgrid model-derived NY terminal injections, not measured tie telemetry',
                 scope='DC matched-representation diagnostic; AC and thermal not established here')
    (OUT/'comparison_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(summary,indent=2))


def matched_matrix(ref, networks, coefficients, observed, dates):
    data=loadmat(OUT/'compact/current_input_snapshots.mat',simplify_cells=True)['input_data']
    components=loadmat(OUT/'reference/matched_snapshot_components.mat',simplify_cells=True)['snapshots']
    components={pd.Timestamp(s['timestamp']):s for s in components}
    nonfossil=pd.read_csv(ROOT/'output/compact_ny_2025/generation_sources/nonfossil/zonal_nonfossil_priors.csv')
    matrix, ablations, detail, movements=[],[],[],[]
    total_east_ledger=[]
    compact=networks['compact51'];paper=networks['reference_NY46']
    port_map, equivalent_B, retained, eliminated = port_injection_map(compact, ref['ids'])
    port_rows=[]
    for j in eliminated:
        for k in np.flatnonzero(np.abs(port_map[:,j])>1e-12):
            port_rows.append(dict(eliminated_bus=int(compact.ids[j]),retained_bus=int(ref['ids'][k]),
                                  injection_weight=port_map[k,j],basis='exact_compact_DC_Kron_injection_map',
                                  measured_terminal_allocation=False))
    write_csv(pd.DataFrame(port_rows),'common_port_injection_map.csv')
    port_checks=[]
    def pg_at_buses(case, ids):
        out=np.zeros(len(ids));lookup={b:j for j,b in enumerate(ids)}
        for g in case['gen']:
            out[lookup[int(g[0])]] += g[1]*g[7]
        return out
    def save_result(target, name, time, netlabel, inj, input_label, ablation=False):
        idx=dates.get_loc(time);net=networks[netlabel]
        result=net.solve(inj);pred=result['flow']@coefficients[netlabel].T;s=score(pred,observed[idx:idx+1])
        row=dict(experiment=name,timestamp=time,network=netlabel,inputs=input_label,
                 pooled_error_pct=s['pooled_error_pct'][0],worst_interface_error_pct=s['worst_interface_error_pct'][0],
                 wrong_direction_interfaces=int(s['wrong_direction'].sum()),
                 additional_slack_mw=result['slack_adjustment_mw'][0],
                 input_total_imbalance_mw=float(np.sum(inj)),observations_used_in_dispatch=False)
        for j,n in enumerate(NAMES):
            row[n+'_error_pct']=s['absolute_error_pct'][0,j]
        target.append(row)
        if ablation:
            for j,n in enumerate(NAMES):
                detail.append(dict(experiment=name,timestamp=time,interface=n,
                                   observed_benchmark_mw=observed[idx,j],predicted_benchmark_mw=pred[0,j],
                                   absolute_error_benchmark_mw=s['absolute_error_mw'][0,j],absolute_error_pct=s['absolute_error_pct'][0,j]))
        return pred[0]
    for item in data:
        time=pd.Timestamp(item['timestamp']);i=dates.get_loc(time)
        input_case=item['paper74'];ids=input_case['bus'][:,0].astype(int)
        current_pg=pg_at_buses(input_case,ids)
        ours=current_pg-item['gross_pd_mw']+item['boundary_p_mw']-input_case['bus'][:,4]
        source=ref['injection'][i]*GAMMA
        # Prove the common-port reduction on this current input before using
        # it in the different reference network. Retain full51bus C/D solves.
        direct=compact.solve(ours)
        eqp=port_map@ours
        refpos=list(ref['ids']).index(74);keep=np.delete(np.arange(46),refpos)
        angles=np.zeros(51)
        angles[retained[keep]]=np.linalg.solve(equivalent_B[np.ix_(keep,keep)],eqp[keep])
        angles[eliminated]=np.linalg.solve(compact.B[np.ix_(eliminated,eliminated)],
                         ours[eliminated]-compact.B[np.ix_(eliminated,retained)]@angles[retained])
        reconstructed=(compact.incidence@angles)*compact.b
        branch_error=np.max(np.abs(reconstructed-direct['flow'][0]))
        assert branch_error<1e-7 and abs(eqp.sum()-ours.sum())<1e-7
        port_checks.append(dict(timestamp=time,max_reconstructed_branch_error_mw=branch_error,
                                total_injection_error_mw=eqp.sum()-ours.sum(),
                                missing_9003_injection_mw=ours[compact.lookup[9003]]))
        for letter,network,vector,from_ids,label in [
                ('A','reference_NY46',source,ref['ids'],'NYgrid_bus_inputs_and_solved_slack'),
                ('B','reference_NY46',eqp,ref['ids'],'current_sources_plus_H_at74_compact_port_equivalent'),
                ('C','compact51',source,ref['ids'],'NYgrid_bus_inputs_and_solved_slack'),
                ('D','compact51',ours,ids,'current_sources_plus_H_at74'),
                ('C_marcy','compact51_marcy',source,ref['ids'],'NYgrid_bus_inputs_and_solved_slack'),
                ('D_marcy','compact51_marcy',ours,ids,'current_sources_plus_H_at74')]:
            save_result(matrix,letter,time,network,map_bus_values(vector,from_ids,networks[network].ids),label)
        for input_name,pg,pd_net,boundary in [
                ('paper_bus_inputs',map_bus_values(ref['solved_pg'][i]*GAMMA,ref['ids'],ids)[0],
                 map_bus_values(ref['pd_net'][i]*GAMMA,ref['ids'],ids)[0],
                 map_bus_values(ref['boundary'][i]*GAMMA,ref['ids'],ids)[0]),
                ('current_sources_with_H_restored',current_pg,item['gross_pd_mw'],item['boundary_p_mw'])]:
            injection=pg-pd_net+boundary-input_case['bus'][:,4]
            result=compact.solve(injection)
            for role_name,zones in [('paper_allocation',paper_roles(ids)),
                                    ('compact_physical',np.array(pd.read_csv(OUT/'compact/bus_metadata.csv').compact_physical_zone))]:
                region=np.isin(zones,list('ABCDE'))
                closed_cut=compact.cut(ids[region])
                model_flow=float(result['flow'][0]@closed_cut)
                adjustment=float(result['slack_adjustment_mw'][0]) if region[compact.reference] else 0.
                ledger_flow=float(pg[region].sum()+boundary[region].sum()-pd_net[region].sum()
                                  -input_case['bus'][region,4].sum()+adjustment)
                assert abs(ledger_flow-model_flow)<1e-7
                total_east_ledger.append(dict(timestamp=time,inputs=input_name,region_roles=role_name,
                    generation_mw=pg[region].sum(),net_load_after_renewable_offsets_mw=pd_net[region].sum(),
                    boundary_injection_mw=boundary[region].sum(),shunt_active_demand_mw=input_case['bus'][region,4].sum(),
                    regional_slack_adjustment_mw=adjustment,dc_losses_mw=0.,regional_export_mw=ledger_flow,
                    complete_modeled_cut_flow_mw=model_flow,closed_cut_accounting_error_mw=ledger_flow-model_flow,
                    observed_total_east_benchmark_mw=observed[i,2],observed_minus_modeled_mw=observed[i,2]-model_flow,
                    exact_public_measurement_membership=False,scale_gamma=GAMMA))
        s=components[time];target=networks['compact51_marcy'];base=map_bus_values(source,ref['ids'],target.ids)[0]
        save_result(ablations,'paper_J_only_hydro_boundary_load',time,'compact51_marcy',base,'paper_components',True)
        def aggregate(values,busids):
            vals=np.zeros(len(target.ids))
            for value,b in zip(values,busids): vals[target.lookup[int(b)]]+=value
            return vals
        recorded=np.nan_to_num(s['thermal_source_recorded_pg_mw'],nan=0)
        allocated=np.asarray(s['thermal_allocated_pg_mw'])
        normalized=recorded*allocated.sum()/recorded.sum()
        changes={
            'thermal_residual_statewide_normalization':aggregate((normalized-allocated)*GAMMA,s['thermal_model_bus']),
            'current_boundary_only':map_bus_values(item['boundary_p_mw'],ids,target.ids)[0]-map_bus_values(ref['boundary'][i]*GAMMA,ref['ids'],target.ids)[0],
        }
        # Spatial load ablation preserves the paper's zonal totals and gross
        # total. It changes only the within-zone bus weights / role crosswalk.
        gross=map_bus_values(s['gross_pd_mw']*GAMMA,s['gross_bus_ids'],target.ids)[0]
        paper_z=paper_roles(target.ids)
        physical_z=np.array(pd.read_csv(OUT/'compact/bus_metadata.csv').compact_physical_zone)
        desired=np.zeros(len(target.ids))
        for z in 'ABCDEFGHIJK':
            amount=gross[paper_z==z].sum();mask=physical_z==z
            weights=np.asarray(item['gross_pd_mw'])[mask]
            assert weights.sum()>0
            desired[mask]=amount*weights/weights.sum()
        changes['current_within_zone_gross_load_placement']=gross-desired
        # Existing source-informed hydro zoning, with its statewide amplitude
        # matched to the paper. Within-zone allocation follows current generic
        # generator headroom weights; this is an explicit combined spatial rule.
        hydro_rows=np.asarray(s['hydro_generator_rows'],dtype=int)-1
        pg=s['input_case']['gen'][hydro_rows,1];gb=s['input_case']['gen'][hydro_rows,0]
        source_hydro=aggregate(pg*GAMMA,gb)
        h=nonfossil[(nonfossil.scenario_id==item['scenario_id'])&(nonfossil.fuel_category=='Hydro')]
        assert len(h)==11
        amount=dict(zip(h.zone,h.prior_public_mw));total=sum(amount.values())
        desired_h=np.zeros(len(target.ids))
        gen=input_case['gen'];capacity=np.maximum(gen[:,8]-gen[:,9],0)*gen[:,7]
        gen_z=np.array([physical_z[target.lookup[int(b)]] for b in gen[:,0]])
        for z in 'ABCDEFGHIJK':
            value=amount[z]/total*source_hydro.sum();mask=gen_z==z
            if value>1e-9:
                assert capacity[mask].sum()>0
                desired_h+=aggregate(value*capacity[mask]/capacity[mask].sum(),gen[mask,0])
        changes['current_hydro_spatial_rule_fixed_paper_total']=desired_h-source_hydro
        for name,change in changes.items():
            # Boundary method also changes total imports; report bus74 balance.
            if name!='current_boundary_only': assert abs(change.sum())<1e-7
            save_result(ablations,name,time,'compact51_marcy',base+change,'one_declared_input_rule_changed',True)
            for j,b in enumerate(target.ids):
                if abs(change[j])>1e-9:
                    movements.append(dict(timestamp=time,experiment=name,bus_id=b,delta_injection_benchmark_mw=change[j],
                                          delta_injection_actual_scale_mw=change[j]/GAMMA))
    write_csv(pd.DataFrame(port_checks),'common_port_equivalence_checks.csv')
    write_csv(pd.DataFrame(total_east_ledger),'total_east_regional_ledger.csv')
    return pd.DataFrame(matrix),pd.DataFrame(ablations),pd.DataFrame(detail),pd.DataFrame(movements)


if __name__=='__main__':
    main()
