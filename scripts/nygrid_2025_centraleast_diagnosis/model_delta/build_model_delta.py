"""Read-only structural audit of the frozen DC comparator and synthetic AC.

This script compares source parameters, maps and algebraic network operators.
It does not fit observations, rerun power flow or change either baseline.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.linalg import solve
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_centraleast_diagnosis/model_delta'


def record(p):
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=p.relative_to(ROOT).as_posix(),sha256=h)


def dc_operators(bus,branch,base):
    lookup={int(x):j for j,x in enumerate(bus[:,0])}
    f=np.asarray([lookup[int(x)] for x in branch[:,0]]);t=np.asarray([lookup[int(x)] for x in branch[:,1]])
    tap=np.where(branch[:,8]==0,1.,branch[:,8]);on=branch[:,10]>0
    b=np.zeros(len(branch));b[on]=1/(branch[on,3]*tap[on])
    C=np.zeros((len(branch),len(bus)));C[np.arange(len(branch)),f]=1;C[np.arange(len(branch)),t]-=1
    Bf=base*b[:,None]*C;Bbus=C.T@Bf
    offset=-base*b*np.deg2rad(branch[:,9]);pinj=C.T@offset
    return Bbus,Bf,offset,pinj,f,t


def lift_matrix(B,keep):
    e=np.asarray([i for i in range(len(B)) if i not in set(keep)])
    L=np.zeros((len(B),len(keep)));L[keep]=np.eye(len(keep))
    if len(e):L[e]=-solve(B[np.ix_(e,e)],B[np.ix_(e,keep)],assume_a='sym')
    return L,e


def main():
    OUT.mkdir(parents=True,exist_ok=True);paths=[Path(__file__)];data={}
    def readmat(rel,**kw):
        p=ROOT/rel;paths.append(p);return loadmat(p,simplify_cells=True,**kw)
    def readcsv(rel):
        p=ROOT/rel;paths.append(p);return pd.read_csv(p)
    full=readmat('output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat')
    post=readmat('output/nygrid_2025_dover_parameters/network/x_nominal.mat')
    slim=readmat('output/nygrid_2025_line_parameters/overlays/engineering_nominal/network_cases.mat')
    assignments=readcsv('output/nygrid_2025_ac_system/branches/branch_assignments.csv').set_index('branch_row')
    anchors=readcsv('output/nygrid_2025_slim/network/bus_register.csv').model_bus.to_numpy(int)
    net=readmat('output/nygrid_2025_western_audit/replay/dated_combined.mat',variable_names=['corrected_generator_buses'])
    genbus=np.asarray(net['corrected_generator_buses'],int)
    dispatch=readmat('output/nygrid_2025_dispatch/dispatch/dispatch.mat',variable_names=['hour_index','timestamp_utc','bus_pd','bus_qd','dc_pf','reference_bus','gamma'])
    western=readmat('output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat',variable_names=['gen_pg','P34_control_targets_model_mw','qualified'])
    dover=readmat('output/nygrid_2025_dover_parameters/replay/operating_states.mat',variable_names=['qualified','controls'])
    q=np.asarray(dover['qualified'],bool);gamma=float(dispatch['gamma'])
    state_specs=[('pre_may',1),('may21',3360),('may30',3576),('post_dover',8472)]
    rows=[];cutrows=[];boundary=[];summaries=[];busrows=[]
    cutmembers=[33,36,40,42]
    for state,hour in state_specs:
        c=readmat(f'output/nygrid_2025_compact_ac/models/compact_ac_h{hour:04d}.mat')['model'];ac=c['detailed_mpc']
        original=post['full_case'] if state=='post_dover' else full[f'refined_2025_{state}_case']
        zones=np.asarray(post['full_bus_zones'] if state=='post_dover' else full['bus_zones']).astype(str)
        dcbranch=np.asarray(original['branch']).copy();dcbranch[210,10]=0
        if state=='post_dover':dcbranch[410:412,9]=np.asarray(dover['controls']['bounded_x_nominal']['bank_shift_model_deg'])[hour-1]
        bus=np.asarray(original['bus']);br=np.asarray(ac['branch']);ab=np.asarray(ac['bus'])
        parent=np.asarray(c['branch_parent_row'],int);ids=bus[:,0].astype(int)
        ai={int(x):i for i,x in enumerate(ab[:,0])};oi={int(x):i for i,x in enumerate(ids)}
        az={int(x):str(z) for x,z in zip(ids,zones)};names={int(x):str(n) for x,n in zip(ids,original['bus_name'])}
        oldrows=np.asarray([ai[int(x)] for x in ids]);interior=np.asarray([i for i,x in enumerate(ab[:,0]) if int(x) not in oi])
        assert len(interior)==75 and np.all(ab[interior,2:6]==0)
        assert np.array_equal(ac['gen'][:,0],genbus)
        assert np.array_equal(ac['gen'][:,1],western['gen_pg'][hour-1])
        expected_load=np.zeros((len(ab),2));expected_load[:140,0]=dispatch['bus_pd'][hour-1];expected_load[:140,1]=dispatch['bus_qd'][hour-1]
        assert np.array_equal(ac['bus'][:,2:4],expected_load)
        expected_dc=np.r_[dispatch['dc_pf'][hour-1],western['P34_control_targets_model_mw'][hour-1]]
        assert np.array_equal(ac['dcline'][:,3],expected_dc)
        assert tuple(ac['dcline'][4:,:2].flatten())==(100,48,100,48)
        reactors=readcsv(f'output/nygrid_2025_ac_system/branches/{state}_reactor_ledger.csv')
        expected_bs=np.zeros(len(bus))
        for r in reactors.itertuples():
            expected_bs[oi[int(r.from_bus)]]+=r.from_bus_BS_delta_mvar
            expected_bs[oi[int(r.to_bus)]]+=r.to_bus_BS_delta_mvar
        shunt_error=float(np.max(abs(ab[oldrows,5]-bus[:,5]-expected_bs)))
        assert shunt_error<1e-10 and np.array_equal(ab[oldrows,4],bus[:,4])
        unsplit=dcbranch.copy();maxsum=0.;cuttotal=0.;membership=original['if']['map']
        assert np.array_equal(membership[membership[:,0]==5,1],-np.asarray(cutmembers))
        for j,old in enumerate(dcbranch):
            p=j+1;parts=np.flatnonzero(parent==p);remaining=set(parts.tolist());chain=[];cursor=int(old[0])
            while remaining:
                cand=[x for x in remaining if int(br[x,0])==cursor];assert len(cand)==1
                x=cand[0];remaining.remove(x);chain.append(x);cursor=int(br[x,1])
            assert cursor==int(old[1]);parts=np.asarray(chain)
            assert np.all(br[parts,10]==old[10])
            a=assignments.loc[p];total=br[parts,2:5].sum(axis=0)
            error=float(np.max(abs(total-np.asarray([a.applied_r_pu,a.applied_x_pu,a.applied_b_pu]))));maxsum=max(maxsum,error)
            assert error<1e-12
            assert np.prod(np.where(br[parts,8]==0,1,br[parts,8]))==np.where(old[8]==0,1,old[8])
            assert abs(br[parts,9].sum()-old[9])<1e-10
            unsplit[j,2:5]=total
            f,t=map(int,old[:2]);source_b=1/(old[3]*(old[8] if old[8] else 1)) if old[10] else 0
            applied_b=1/(total[1]*(old[8] if old[8] else 1)) if old[10] else 0
            item=dict(state=state,branch_row=p,branch_key=a.branch_key,from_bus=f,to_bus=t,
                      from_name=names[f],to_name=names[t],from_zone=az[f],to_zone=az[t],
                      active=bool(old[10]),classification=a.classification,asbuilt_qualified=bool(a.asbuilt_identity_qualified),
                      source_R_pu=old[2],source_X_pu=old[3],source_B_pu=old[4],
                      AC_total_R_pu=total[0],AC_total_X_pu=total[1],AC_total_B_pu=total[2],
                      delta_R_pu=total[0]-old[2],delta_X_pu=total[1]-old[3],delta_B_pu=total[2]-old[4],
                      X_ratio=total[1]/old[3] if old[3] else np.nan,
                      source_DC_susceptance_pu=source_b,AC_derived_DC_susceptance_pu=applied_b,
                      source_tap=old[8],AC_effective_tap=np.prod(np.where(br[parts,8]==0,1,br[parts,8])),
                      source_shift_deg=old[9],AC_total_shift_deg=br[parts,9].sum(),
                      section_count=len(parts),runtime_rows=';'.join(str(x+1) for x in parts),
                      parameter_basis=a.parameter_basis,original_R_X_preserved=a.original_R_X_preserved,
                      installed_conductor_or_route_identified=a.installed_conductor_or_route_identified,
                      declared_route_length_m=a.route_length_m,geographic_chord_m=a.geographic_chord_m,
                      declared_length_min_m=a.length_min_m,declared_length_max_m=a.length_max_m,
                      declared_preferred_length_m=a.preferred_length_m,circuits=a.circuits,bundle_count=a.bundle_count)
            rows.append(item)
            if p in cutmembers:
                assert az[f]=='F' and az[t]=='E';assert old[8] in [0,1] and old[9]==0
                item=item.copy();item.update(interface_coefficient=-1,E_source_terminal_bus=t,F_target_terminal_bus=f,
                    literal_from_uses_first_section=True,source_side_uses_last_to_terminal=True,
                    same_total_X=True,DC_series_weight=1/total[1],
                    AC_small_angle_series_weight=total[1]/(total[0]**2+total[1]**2),
                    AC_over_DC_small_angle_factor=1/(1+(total[0]/total[1])**2),
                    reactor_on_member=False,reactor_at_any_member_endpoint=False)
                assert not reactors.original_branch_row.isin([p]).any()
                assert not (reactors.from_bus.isin([f,t])|reactors.to_bus.isin([f,t])).any()
                cutrows.append(item)
            if old[10] and az[f]!=az[t] and ({az[f],az[t]}&{'E','F'}):
                boundary.append(dict(state=state,branch_row=p,from_bus=f,to_bus=t,from_name=names[f],to_name=names[t],
                                     from_zone=az[f],to_zone=az[t],CENTRAL_EAST_member=p in cutmembers,
                                     TOTAL_EAST_member=p in set(abs(membership[membership[:,0]==3,1]).astype(int)),
                                     source_X_pu=old[3],AC_X_pu=total[1]))
        B0,H0,off0,inj0,f0,t0=dc_operators(bus,dcbranch,float(ac['baseMVA']))
        B1,H1,off1,inj1,f1,t1=dc_operators(ab,br,float(ac['baseMVA']))
        Bu,Hu,offu,inju,_,_=dc_operators(bus,unsplit,float(ac['baseMVA']))
        Ln,internal=lift_matrix(B1,oldrows)
        reduced=B1[np.ix_(oldrows,np.arange(len(B1)))]@Ln
        segmentation_error=float(np.max(abs(reduced-Bu)));assert segmentation_error<1e-8
        phase_offset_error=float(np.max(abs(inj1[oldrows]+B1[np.ix_(oldrows,internal)]@(-solve(B1[np.ix_(internal,internal)],inj1[internal],assume_a='sym'))-inju)))
        assert phase_offset_error<1e-8
        ko=np.asarray([oi[int(x)] for x in anchors]);ka=np.asarray([ai[int(x)] for x in anchors])
        Lo,_=lift_matrix(B0,ko);La,_=lift_matrix(B1,ka)
        h0=-H0[np.asarray(cutmembers)-1].sum(axis=0)
        firstrows=[int(np.flatnonzero((parent==p)&(br[:,0]==dcbranch[p-1,0]))[0]) for p in cutmembers]
        h1=-H1[firstrows].sum(axis=0)
        K0=h0@Lo;K1=h1@La
        rec=post['recovery'] if state=='post_dover' else slim['recovery'][f'refined_2025_{state}']
        refH=np.asarray(rec['interface_angle_matrix'])[4]
        old_kernel_error=float(np.max(abs(K0-refH)));assert old_kernel_error<1e-8
        graph=np.zeros((len(bus),len(bus)));on=(dcbranch[:,10]>0)&~np.isin(np.arange(1,len(dcbranch)+1),cutmembers)
        graph[f0[on],t0[on]]=1;graph[t0[on],f0[on]]=1
        ncomp,label=connected_components(csr_matrix(graph),directed=False)
        assert ncomp==1
        for j,bid in enumerate(ids):
            busrows.append(dict(state=state,bus_id=int(bid),bus_name=names[int(bid)],zone=zones[j],
                                retained_in_148=bool(bid in anchors),has_generator=bool(bid in genbus),
                                source_GS_MW=bus[j,4],AC_GS_MW=ab[ai[int(bid)],4],source_BS_MVAr=bus[j,5],
                                AC_BS_MVAr=ab[ai[int(bid)],5],declared_reactor_BS_delta_MVAr=expected_bs[j]))
        summaries.append(dict(state=state,template_hour=hour,original_bus_count=len(bus),AC_bus_count=len(ab),
            original_branches=len(dcbranch),AC_branches=len(br),numerical_section_buses=len(interior),
            topology_identical_after_contracting_sections=True,all_status_tap_and_phase_contracts_match=True,
            current_generator_locations_match_corrected_DC_contract=True,
            raw_source_template_generator_locations_differ_but_preexisting_DC_correction_count=int(np.count_nonzero(original['gen'][:,0]!=genbus)),
            source_load_PQ_and_six_active_transfers_exactly_preserved=True,
            maximum_section_sum_R_X_B_error_pu=maxsum,
            maximum_sectioned_DC_Bbus_Schur_vs_unsplit_overlay_error_MW_per_rad=segmentation_error,
            maximum_sectioned_phase_injection_vs_unsplit_overlay_error_MW=phase_offset_error,
            maximum_original_DC_CE_kernel_vs_sealed_operator_error_MW_per_rad=old_kernel_error,
            DC_Bbus_relative_Frobenius_change=float(np.linalg.norm(Bu-B0)/np.linalg.norm(B0)),
            CE_retained_angle_kernel_relative_L2_change=float(np.linalg.norm(K1-K0)/np.linalg.norm(K0)),
            CE_retained_angle_kernel_maximum_delta_MW_per_rad=float(np.max(abs(K1-K0))),
            largest_CE_kernel_change_retained_bus=int(anchors[np.argmax(abs(K1-K0))]),
            graph_components_after_removing_all_CE_members=int(ncomp),
            CE_members_are_not_a_complete_graph_separating_cut=True,
            reactor_rows=int(len(reactors)),reactor_total_nominal_MVAr=float(reactors.applied_total_reactor_mvar_at1pu.sum()),
            maximum_single_application_reactor_BS_audit_error_MVAr=shunt_error))
    allrows=pd.DataFrame(rows);cut=pd.DataFrame(cutrows)
    allrows.to_csv(OUT/'branch_parameter_deltas.csv',index=False)
    cut.to_csv(OUT/'CENTRAL_EAST_member_deltas.csv',index=False)
    changes=allrows[(allrows.state=='post_dover')&allrows.active&(abs(allrows.delta_X_pu)>1e-12)].copy()
    assert len(changes)==33
    changes.to_csv(OUT/'x_changed_corridors.csv',index=False)
    pd.DataFrame(boundary).to_csv(OUT/'zone_E_F_boundary_branches.csv',index=False)
    pd.DataFrame(busrows).to_csv(OUT/'bus_shunt_and_injection_locations.csv',index=False)
    # Source input accounting by original zone; these are fixed P schedules,
    # before the AC reference generator adds losses. No measured interfaces enter.
    base=post['full_case'];zmap={int(b):str(z) for b,z in zip(base['bus'][:,0],post['full_bus_zones'])}
    zone_names=sorted(set(zmap.values()));profiles=[];profile_summary=[]
    generator_zones=np.asarray([zmap[int(b)] for b in genbus]);dclines=ac['dcline'];dc=np.column_stack([dispatch['dc_pf'],western['P34_control_targets_model_mw']])
    refzones=np.asarray([zmap.get(int(b),'SOURCE_EXCLUDED') for b in dispatch['reference_bus']])
    assert not np.any(refzones[q]=='SOURCE_EXCLUDED')
    for zone in zone_names:
        pg=np.sum(western['gen_pg'][:,generator_zones==zone],axis=1)
        ld=[b-1 for b in range(1,141) if zmap[b]==zone];pdemand=np.sum(dispatch['bus_pd'][:,ld],axis=1)
        dcin=np.zeros(8760)
        for j,d in enumerate(dclines):
            if zmap[int(d[0])]==zone:dcin-=dc[:,j]
            if zmap[int(d[1])]==zone:dcin+=dc[:,j]
        netP=pg+dcin-pdemand
        profile_summary.append(dict(zone=zone,source_qualified_hours=int(q.sum()),
            mean_generation_model_MW=float(pg[q].mean()),mean_load_model_MW=float(pdemand[q].mean()),
            mean_fixed_transfer_injection_model_MW=float(dcin[q].mean()),mean_net_injection_before_AC_losses_model_MW=float(netP[q].mean()),
            minimum_net_injection_model_MW=float(netP[q].min()),maximum_net_injection_model_MW=float(netP[q].max()),
            reference_generator_hours=int(np.count_nonzero(q&(refzones==zone)))))
    pd.DataFrame(profile_summary).to_csv(OUT/'zone_input_summary.csv',index=False)
    source_code=[ROOT/'System Matpower Format'/n for n in ['npcc_nygrid_2025_ac.m','npcc_nygrid_2025_dover_dc.m','npcc_nygrid_2025_line_estimated_dc.m','npcc_nygrid_2025_western_corrected_dc.m']]
    source_code += [ROOT/'scripts/nygrid_2025_par_controls/controlled_equivalent.py',ROOT/'scripts/nygrid_2025_dover_parameters/run_dover_replay.py',ROOT/'scripts/nygrid_2025_ac_system/branches/nygrid_ac_apply_sections.m',
                    ROOT/'scripts/nygrid_2025_ac_system/branches/line_equivalents.py',ROOT/'scripts/nygrid_2025_ac_system/branches/build_assignments.py']
    paths.extend(source_code)
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),baseline_HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        scope='Structural parameter/operator/input-contract comparison; no new PF, no observation fitting, no causal dominance claim',
        exact_DC_comparator='bounded_x_nominal with corrected generator locations, six fixed transfers and branch211 disabled',
        gamma=gamma,all_four_CENTRAL_EAST_member_total_X_values_preserved=True,
        CENTRAL_EAST_parent_rows=cutmembers,all_raw_member_orientations='F_to_E',comparison_direction='E_to_F',
        historical_negative_literal_PF_equals_oriented_target_side=True,
        no_reactors_on_CENTRAL_EAST_members_or_endpoint_buses=True,
        active_corridors_with_changed_X=33,
        candidate_experiments=[dict(parent_rows=[224],reason='Direct E-to-G bypass in TOTAL EAST but not CENTRAL EAST; X increases3.772646x.'),
                              dict(parent_rows=[41],reason='F-to-F Rotterdam-Albany neighboring path X increases22.926433x.'),
                              dict(parent_rows=changes.branch_row.astype(int).tolist(),reason='All33 active X redesigns, preserving current AC R/B/status/taps/control as an isolated bridge.')],
        hypotheses_not_established_causes=['Surrounding-path X changes can reroute the fixed injections through CE although CE member X is unchanged.',
            'Single-reference loss balancing at CLAY in zoneC can increase eastward transfers; quantify separately from X changes.',
            'AC voltage products, conductance and reactive support can change real-power routing; PF equivalence does not validate those assumptions.'],
        source_data_caveats=['Inherited zone-crossing functional is not certified physical NYISO meter membership.',
            'Generic conductor/geometry redesign and external equivalent impedances are synthetic; unchanged totalX on CE does not establish physical circuit accuracy.',
            'Raw full-network template gen.bus contains81 preexisting stale placements; the frozen DC replay already applies the same corrected generator buses used by AC.',
            'The row224/41 redesigns use fallback_candidate after no exact R/X/catalog/geometry/length candidate exists. If originalX implies a route outside the declared length interval, it uses the preferred1.25-geographic-chord route before clipping; these are not measured routes.',
            'A lower public-interface WAPE under an alternative impedance does not establish that impedance as physically correct.'],
        states=summaries,dependencies=[record(p) for p in dict.fromkeys(paths)],
        outputs=[record(p) for p in sorted(OUT.glob('*.csv'))])
    (OUT/'model_delta_review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['dependencies','outputs','states']},indent=2))
    print(json.dumps(summaries,indent=2))


if __name__=='__main__':main()
