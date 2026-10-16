"""Latest-model structure inventory and exact row maps, without history prose."""
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import Counter
import hashlib
import json

import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy import sparse

ROOT=Path(__file__).resolve().parents[2]
NS=ROOT/'output/nygrid_2025_latest_handoff'
INPUT=NS/'structure_inputs'
OUT=NS/'structure'
STATES=['pre_may','may21','may30','post_dover']
BASELINE='2e0fcd5c3f0ae39d04f27a733ce30eb148b0b243'


def record(path):
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=digest)


def dense(value):return value.toarray() if sparse.issparse(value) else np.asarray(value)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    generator_path=ROOT/'output/nygrid_2025_western_audit/corrected/model_generator_register.csv'
    registry_path=ROOT/'output/nygrid_2025_ac_system/branches/branch_assignments.csv'
    dated_path=ROOT/'output/nygrid_2025_slim/replay/topology_dated.mat'
    dover_path=ROOT/'output/nygrid_2025_dover_parameters/replay/operating_states.mat'
    summary_path=INPUT/'structure_export_summary.json'
    generators=pd.read_csv(generator_path,keep_default_na=False).set_index('gen_row')
    registry=pd.read_csv(registry_path,keep_default_na=False).set_index('branch_row')
    dated=loadmat(dated_path,simplify_cells=True,variable_names=['hour_index','timestamp_utc','network_state_ids','reference_bus'])
    source=loadmat(dover_path,simplify_cells=True,variable_names=['hour_index','timestamp_utc','qualified','post_full_service','gamma','cutover_utc'])
    clock=np.asarray(source['timestamp_utc']).astype(str)
    assert np.array_equal(clock,np.asarray(dated['timestamp_utc']).astype(str))
    stateids=np.asarray(dated['network_state_ids']).astype(str)
    edges=np.r_[0,np.flatnonzero(stateids[1:]!=stateids[:-1])+1,len(stateids)]
    assert edges.tolist()==[0,3359,3575,8471,8760]
    assert np.flatnonzero(source['post_full_service'])[0]==8471
    exported=json.loads(summary_path.read_text())
    dependencies=[record(p) for p in [generator_path,registry_path,dated_path,dover_path,summary_path,
        Path(__file__).with_name('export_current_structure.m')]]
    rows_bus=[];rows_branch=[];rows_gen=[];rows_dc=[];summaries=[];retained_first=None;retained_table=None
    topology=[];models={};matrix_checks=[]
    for i,state in enumerate(STATES):
        path=INPUT/(state+'.mat');d=loadmat(path,simplify_cells=True);models[state]=d;dependencies.append(record(path))
        er=next(x for x in exported if x['state']==state)
        bus=np.asarray(d['bus']);branch=np.asarray(d['branch']);gen=np.asarray(d['gen']);dc=np.asarray(d['dcline']);base=float(d['baseMVA'])
        ids=bus[:,0].astype(int);lookup={b:j for j,b in enumerate(ids)};names=np.asarray(d['bus_name']).astype(str)
        retained=np.asarray(d['retained_ids']).astype(int);k=np.asarray(d['retained_rows']).astype(int)-1;e=np.asarray(d['eliminated_rows']).astype(int)-1
        parent=np.asarray(d['branch_parent_row']).astype(int);keys=np.asarray(d['branch_keys']).astype(str)
        group=np.asarray(d['bus_group']).astype(int);labels=np.asarray(d['group_labels']).astype(str)
        name_map=dict(zip(ids,names));zone_map={b:labels[group[j]-1] if group[j]>0 else 'PASSIVE_INTERIOR' for j,b in enumerate(ids)}
        assert base==100 and len(retained)==148 and np.array_equal(ids[k],retained)
        if retained_first is None:retained_first=retained.copy()
        else:assert np.array_equal(retained_first,retained)
        assert gen.shape==(1464,21) and dc.shape==(6,17)
        assert np.isin(gen[:,0],retained).all() and np.isin(dc[:,:2],retained).all()
        assert (bus[e,2:4]==0).all() and not np.isin(ids[e],gen[:,0]).any() and (bus[e,1]==1).all()
        assert np.array_equal(gen[:,0],generators.loc[np.arange(1,1465),'bus_id'].to_numpy(float))
        assert int(d['reference_bus'])==50 and int(d['reference_generator_row'])==110 and int(np.sum(d['native']))==1436
        assert np.array_equal(np.asarray(d['external_current_rows']).astype(int),np.arange(1437,1465))
        assert float(d['gamma'])==float(source['gamma'])
        eligibility_path=INPUT/(state+'_thermal_eligibility.csv');eligibility=pd.read_csv(eligibility_path).set_index('original_parent_row');dependencies.append(record(eligibility_path))
        thermal_path=INPUT/(state+'_thermal_segments.csv');thermal=pd.read_csv(thermal_path);dependencies.append(record(thermal_path))
        ret_path=INPUT/(state+'_retention.csv');retention=pd.read_csv(ret_path).set_index('bus_id');dependencies.append(record(ret_path))
        active_parents=[]
        for pp in np.unique(parent):
            ix=np.flatnonzero(parent==pp);assert len(set(branch[ix,10]))==1
            if branch[ix[0],10]>0:active_parents.append(int(pp))
        group_count=Counter(zone_map[b] for b in retained)
        active=branch[:,10]>0
        bus_types=Counter(bus[k,1].astype(int))
        maprows=d['branch_map'] if isinstance(d['branch_map'],list) else [d['branch_map']]
        for j,b in enumerate(ids):
            reason=[]
            rr=retention.loc[b]
            for field,label in [('anchor_148','retained_port_contract'),('nonzero_load','nonzero_load'),('generator_terminal','generator_terminal'),('DC_terminal','fixed_transfer_terminal'),('voltage_control','voltage_control')]:
                if bool(rr[field]):reason.append(label)
            if not bool(rr.retained):reason.append('passive_zero_prescribed_injection_interior')
            rows_bus.append(dict(state=state,representative_hour=int(d['hour']),full_row_1based=j+1,model_bus_id=int(b),model_name=names[j],
                nominal_kV=bus[j,9],accounting_group=zone_map[b],retained=int(b in set(retained)),
                retained_row_1based=int(np.flatnonzero(retained==b)[0]+1) if b in set(retained) else 0,
                bus_type_at_fixture=int(bus[j,1]),GS_MW_at_1pu=bus[j,4],BS_MVAr_at_1pu=bus[j,5],
                Vmin_pu=bus[j,12],Vmax_pu=bus[j,11],role=';'.join(reason)))
        if retained_table is None:
            retained_table=pd.DataFrame([dict(retained_row_1based=j+1,model_bus_id=int(b),model_name=name_map[b],
                nominal_kV=bus[lookup[b],9],accounting_group=zone_map[b],is_reference_bus=b==50,
                has_generator_rows=bool(np.any(gen[:,0]==b)),has_fixed_transfer_terminal=bool(np.any(dc[:,:2]==b))) for j,b in enumerate(retained)])
        for j,br in enumerate(branch):
            pp=int(parent[j]);reg=registry.loc[pp];maprow=maprows[j]
            classified=str(reg.classification)
            if pp==224:classified='unresolved_network_equivalent'
            rows_branch.append(dict(state=state,runtime_branch_row=j+1,branch_key=keys[j],parent_corridor_row=pp,
                parent_corridor_key=str(reg.branch_key),from_bus=int(br[0]),from_name=name_map[int(br[0])],to_bus=int(br[1]),to_name=name_map[int(br[1])],
                from_kV=bus[lookup[int(br[0])],9],to_kV=bus[lookup[int(br[1])],9],R_pu=br[2],X_pu=br[3],total_B_pu=br[4],
                status=int(br[10]),tap=br[8],phase_shift_deg_at_fixture=br[9],class_in_current_model=classified,
                synthetic_OH_screen_eligible=bool(eligibility.loc[pp].research_screen_eligible),
                physical_terminal_from=bool(maprow['physical_terminal_from']),physical_terminal_to=bool(maprow['physical_terminal_to'])))
        gen_group=np.asarray(d['external_gen_group']).astype(int);native=np.asarray(d['native']).astype(bool);HQ=int(d['HQ'])
        for j,row in enumerate(gen):
            gr=generators.loc[j+1];region=zone_map[int(row[0])]
            role='native_fixed_P' if native[j] else 'HQ_fixed_signed_P' if j+1==HQ else 'external_bounded_loss_participant'
            rows_gen.append(dict(state=state,representative_hour=int(d['hour']),generator_row=j+1,device_key=str(gr.device_key),
                role=role,bus_id=int(row[0]),bus_name=name_map[int(row[0])],bus_accounting_group=region,fuel=str(np.asarray(d['genfuel'])[j]),
                EIA_plant_id=gr.plant_id,EIA_generator_id=gr.eia_generator_id,GEN_STATUS_at_fixture=int(row[7]),
                PG_prior_MW_at_fixture=row[1],Pmin_MW_at_fixture=row[9],Pmax_MW_at_fixture=row[8],
                Qmin_MVAr_at_fixture=row[4],Qmax_MVAr_at_fixture=row[3],VG_pu_at_fixture=row[5],
                assumed_S_MVA_at_fixture=float(np.asarray(d['assumed_s_cap'])[j]),
                loss_participation_group=labels[gen_group[j]-1] if gen_group[j]>0 else '',
                frozen_loss_participation_weight=float(np.asarray(d['generator_share'])[j])))
        dc_names=['CSC','NEPTUNE','HTP','VFT','ONTARIO_PAR_25118','ONTARIO_PAR_25119']
        for j,row in enumerate(dc):
            assert row[2]==1 and row[3]==row[4]==row[9]==row[10] and (row[[5,6,11,12,13,14,15,16]]==0).all()
            rows_dc.append(dict(state=state,representative_hour=int(d['hour']),transfer_row=j+1,control_channel=dc_names[j],
                from_bus=int(row[0]),from_model_name=name_map[int(row[0])],from_accounting_group=zone_map[int(row[0])],
                to_bus=int(row[1]),to_model_name=name_map[int(row[1])],to_accounting_group=zone_map[int(row[1])],
                fixed_signed_P_MW_at_fixture=row[3],positive_direction='from_model_bus_to_model_bus',
                modeled_active_loss_zero=True,modeled_terminal_Q_zero=True,
                model_endpoint_names_are_not_physical_asset_terminal_identification=True))
        # Rebuild the full nodal/current operators independently from the case.
        n=len(bus);nl=len(branch);Y=np.zeros((n,n),complex);Yf=np.zeros((nl,n),complex);Yt=Yf.copy();Ys=Yf.copy()
        for j,br in enumerate(branch):
            if not br[10]:continue
            f=lookup[int(br[0])];t=lookup[int(br[1])];series=1/complex(br[2],br[3]);charge=.5j*br[4]
            tap=(br[8] if br[8] else 1)*np.exp(1j*np.deg2rad(br[9]));ff=(series+charge)/abs(tap)**2;ft=-series/np.conj(tap);tf=-series/tap;tt=series+charge
            Y[f,f]+=ff;Y[f,t]+=ft;Y[t,f]+=tf;Y[t,t]+=tt
            Yf[j,f]=ff;Yf[j,t]=ft;Yt[j,f]=tf;Yt[j,t]=tt;Ys[j,f]=series/tap;Ys[j,t]=-series
        Y[np.arange(n),np.arange(n)]+=complex(1,0)*bus[:,4]/base+1j*bus[:,5]/base
        L=np.zeros((n,148),complex);L[k,np.arange(148)]=1;L[e,:]=-np.linalg.solve(Y[np.ix_(e,e)],Y[np.ix_(e,k)])
        Yr=Y[k,:]@L
        errors=dict(Yfull=float(np.max(abs(Y-dense(d['Yfull'])))),Yred=float(np.max(abs(Yr-dense(d['Yred'])))),
            voltage_lift=float(np.max(abs(L-dense(d['voltage_lift'])))),YfL=float(np.max(abs(Yf@L-dense(d['YfL'])))),
            YtL=float(np.max(abs(Yt@L-dense(d['YtL'])))),YseriesL=float(np.max(abs(Ys@L-dense(d['YseriesL'])))))
        assert max(errors.values())<1e-9
        matrix_checks.append(dict(state=state,passed=True,maximum_absolute_operator_errors=errors))
        start,end=int(edges[i]),int(edges[i+1]);local=datetime.fromisoformat(clock[start].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York'))
        topo=dict(state=state,first_hour_index=start+1,last_hour_index=end,start_utc=clock[start],start_local=local.isoformat(),hours=end-start,
            source_qualified_hours=int(np.asarray(source['qualified'])[start:end].sum()))
        topology.append(topo)
        summaries.append(dict(state=state,representative_hour=int(d['hour']),timestamp_utc=er['timestamp_utc'],
            retained_bus_count=148,detailed_bus_count=len(bus),passive_eliminated_bus_count=len(e),
            runtime_branch_records=len(branch),active_runtime_branch_records=int(active.sum()),inactive_runtime_branch_records=int((~active).sum()),
            parent_corridor_records=len(np.unique(parent)),active_parent_corridors=len(active_parents),
            generator_rows=len(gen),native_generator_rows=int(native.sum()),external_loss_participant_rows=int((gen_group>0).sum()),HQ_rows=1,
            admitted_generator_rows_at_fixture=int((gen[:,7]>0).sum()),fixed_transfer_records=len(dc),
            retained_bus_type_counts_at_fixture={str(k):v for k,v in bus_types.items()},
            real_Newton_unknowns_at_fixture=147+bus_types[1],reference_bus=50,reference_generator_row=110,
            retained_accounting_group_counts=dict(group_count),Yred_shape=[148,148],Yred_nonzeros=int(np.count_nonzero(dense(d['Yred']))),
            voltage_lift_shape=[len(bus),148],current_recovery_operator_shape=[len(branch),148],
            synthetic_thermal_parent_count=int(eligibility.research_screen_eligible.sum()),
            synthetic_thermal_runtime_branch_count=int(thermal.branch_row.nunique()),synthetic_thermal_material_segments=len(thermal)))

    files=[]
    for name,table in [('retained_bus_map',retained_table),('detailed_bus_map',pd.DataFrame(rows_bus)),
                       ('runtime_branch_map',pd.DataFrame(rows_branch)),('generator_map',pd.DataFrame(rows_gen)),
                       ('controlled_transfer_map',pd.DataFrame(rows_dc)),('dated_state_map',pd.DataFrame(topology))]:
        path=OUT/(name+'.csv');table.to_csv(path,index=False);files.append(path)
    # A one-row-per-generator structural map, separate from four fixture values.
    gmap=pd.DataFrame(rows_gen)
    static_cols=['generator_row','device_key','role','bus_id','bus_name','bus_accounting_group','fuel','EIA_plant_id','EIA_generator_id','loss_participation_group','frozen_loss_participation_weight']
    gen_static=gmap.loc[gmap.state==STATES[-1],static_cols]
    assert len(gen_static)==1464
    path=OUT/'generator_identity_map.csv';gen_static.to_csv(path,index=False);files.append(path)
    transfers=pd.DataFrame(rows_dc);static=[c for c in transfers.columns if c not in ['state','representative_hour','fixed_signed_P_MW_at_fixture']]
    path=OUT/'controlled_transfer_identity_map.csv';transfers.loc[transfers.state==STATES[-1],static].to_csv(path,index=False);files.append(path)
    inventory=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),model_snapshot_commit=BASELINE,
        scope='Current model structure and field semantics only; no model-evolution or modification narrative',
        model_kind='148-retained-voltage synthetic AC network with coupled boundary-consistent losses and original-section thermal screening',
        base_MVA=100,frequency_Hz=60,power_scale_gamma=float(source['gamma']),current_gamma_lift=False,impedance_gamma_transform=False,
        retained_bus_count=148,retained_bus_ids=retained_first.tolist(),retained_accounting_groups=summaries[-1]['retained_accounting_group_counts'],
        explicit_345kV_ports=retained_table.loc[retained_table.model_bus_id>140].to_dict('records'),
        states=summaries,topology_windows=topology,
        hourly_axis=dict(rows=8760,first_UTC=clock[0],last_UTC=clock[-1],source_qualified_rows=int(np.asarray(source['qualified']).sum()),
            hour_index_base=1,time_rule='Stored hourly UTC instants span the local2025 calendar; no local-hour duplication or DST inference is required.'),
        network=dict(branch_model='Positive-sequence nominal pi with totalB split between ends, complex tap=tau exp(j shift), explicit bus shunts; inactive records retained with status0.',
            branch_rows_are_runtime_sections=True,reduced_matrix_entries_are_physical_lines=False,
            parent224=dict(total_R_pu=.02,total_X_pu=.0147,total_B_pu=0.,numerical_sections=2,role='unresolved_network_equivalent_without_an_admitted_plain_OH_conductor'),
            eliminated_ports='No prescribed load, generator terminal, controlled transfer terminal or independently controlled voltage is eliminated. Fixed shunts remain in Y.',
            reduction='Ve=-Yee^{-1}Yek Vk; L embeds retained identity and passive lift; Yred=Ykk-Yke Yee^{-1}Yek.',
            recovery='Vfull=L Vk; If=Yf L Vk; It=Yt L Vk; Iseries=Yseries L Vk.',
            current_bases='From/to terminal amperes use their respective nominal endpoint kV; series amperes use the to-side base. Ibase=100000/(sqrt(3)*kV).',
            rebuild_required='Rebuild operators when R,X,B,tap,phase,shunt,status or retained/injection/control contract changes; hourly input fingerprints reject stale operators.'),
        generation=dict(total_rows=1464,native_fixed_active_power_rows=1436,external_loss_participants=27,HQ_fixed_signed_injection_rows=1,
            external_group_counts=dict(ISONE=9,ONTARIO=6,PJM=12),reference_bus=50,reference_name='CLAY',reference_generator_row=110,
            reference_role='One retained voltage angle/reference magnitude; its finalP is checked against the same native schedule, not an unlimited loss supplier.',
            native_Q='Online Qmax=-Qmin=max(abs(Pmin),abs(Pmax))*tan(acos(.95)); inactive rows have zeroQ capability.',
            external_Q='Finite declared apparent-power proxy; Qmax=-Qmin=sqrt(S_assumed^2-P_final^2), updated after allocated regional loss changesP.',
            commitment='GEN_STATUS is hourly availability/admission, not observed synchronization or a unit-commitment result.',
            voltage_limits_pu=[.95,1.05],PF_Q_limits_enforced_by_default=False),
        controlled_transfers=dict(count=6,channel_names=['CSC','NEPTUNE','HTP','VFT','ONTARIO_PAR_25118','ONTARIO_PAR_25119'],
            interpretation='Signed fixedP model ports in the MATPOWER dcline container; not six identified physicalHVDC assets.',
            active_loss_model='LOSS0=LOSS1=0 and PT=PF',reactive_model='Fixed QF=QT=0 with zero terminal Q bounds',
            positive_direction='from endpoint toward to endpoint; a negative target reverses the signed injection'),
        loss_policy=dict(groups=['A','B','C','D','E','F','G','H','I','J','K','ISONE','ONTARIO','PJM'],
            NY_boundary_identity='Delivered_PD_z + assigned_NY_loss_z = frozen_P58_boundary_target_z.',
            NY_ownership='Half of each within-NY corridor loss to each endpoint zone; both halves accrue to one zone for an internal corridor.',
            external_ownership='Each external region supplies its internal corridor losses and its AC-corridor losses intoNY through bounded frozen generation participation.',
            fixed_quantities='NativePG, signedHQ injection, six controlled transfers and regional import targets atNY terminals remain fixed.',
            reactive_load='QD scales with deliveredPD at the fixed inherited power factor.',
            required_contract='Zero busGS, zero modeled DC losses and no AC connection between different external regions.',
            numerical_method='Simultaneous voltage and loss-dependent injection Newton solve; referenceP and boundary identities checked afterward.',
            failure_policy='Reject unsupported contracts, negative served-demand/domain failures and exhausted external capability; do not clip loss or promote failed iterates.'),
        conductor_screen=dict(eligible_parent_corridors_by_state={s['state']:s['synthetic_thermal_parent_count'] for s in summaries},
            admission='Active same-voltage OH class; integer circuit/bundle counts; valid catalog temperature/geometry; independently forward-matching R andX in every runtime section.',
            installed_identity_required=False,geographic_chord_required=False,geometric_B='Predicted and reported separately; not rewritten or used as an admission gate.',
            broad_length_caps_m=dict(below200kV=250000,below300kV=500000,below400kV=700000,otherwise=1000000),
            heat='Per-subconductor Joule/convection/radiation/solar heat balance under explicit weather; total circuit phase current is divided by circuits times bundle count.',
            scope='One-way reference-resistance steady-ampacity screen; does not alter electrical parameters, solve equilibriumtemperature, runOPF or certify an installed facility.',
            known_non_OH_conflicts=[300,309,310,386]),
        field_units=dict(bus_PD='modelMW; NY input is a boundary target, final allocated input is delivered demand',bus_QD='modelMVAr',
            gen_PG_Pmin_Pmax='modelMW',gen_QG_Qmin_Qmax='modelMVAr',branch_R_X_B='perunit on100MVA and terminal voltagebases;B is totalcharging',
            branch_PF_PT='modelMW',branch_QF_QT='modelMVAr',bus_VM='perunit',bus_VA_and_phase_shift='degrees',
            recovered_voltage='complex perunit',recovered_current='amperes at synthetic AC base, never divided by gamma',
            public_power_comparison='publicMW=modelMW/gamma only for explicitly mapped public power quantities',
            weather='ambientC,windm/s,wind/conductor angledegrees,solarW/m2,pressurePa'),
        solve_outputs=dict(result_bus='148retained rows',result_gen='1464rows on generatoridentityaxis',result_dcline='6fixed-transfer rows',
            recovered_bus='266/267detailed rows',recovered_branch='485/488runtime rows; columns14:17=PF,QF,PT,QT',
            recovered_full_voltage='266/267complex perunit vector',recovered_line_current_A='485/488by3 [fromterminal,toterminal,series]',
            result_success='Converged AC equations and required loss policy; distinct from joint operating qualification.',
            audit_passed='Also requires declared voltage, reactive and assumed apparent-power capability gates.',
            allocation_final_input='Exact delivered-demand/loss-adjusted generator input underlying the returned solution.'),
        interpretation_limits=['Synthetic electrical and conductor parameters are not an installed-asset survey.',
            'Fixed external load shapes, within-zone spatial loads, unit dispatch and reactive capability are explicit modeling assumptions.',
            'Model-port names and diagnostic interface cuts do not certify actual physical facility membership.',
            'Thermal current identities do not establish voltage/reactive feasibility, terminalequipment limits, N-1 security or economicbenefit.',
            'Source eligibility, AC/loss-equation qualification, operating bounds and thermal exposure are separate flags.'],
        independent_matrix_checks=matrix_checks,no_PF_OPF_or_annual_replay_run=True,
        dependencies=dependencies+[record(Path(__file__).resolve())],outputs=[record(p) for p in files])
    p=OUT/'current_structure_inventory.json';p.write_text(json.dumps(inventory,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:inventory[k] for k in ['passed','retained_bus_count','retained_accounting_groups','hourly_axis','states']},indent=2))


if __name__=='__main__':main()
