"""Build a separate whole-network synthetic AC engineering branch overlay.

No dispatch, solver outcome, or observed interface value is read. Existing
cases are immutable inputs. Every energized overhead-class branch receives
an explicit conductor realization; other equipment is classified separately.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,math
import numpy as np
import pandas as pd
from scipy.io import loadmat,savemat
from line_equivalents import require,electrical,segment,inverse_candidates,fallback_candidate

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_ac_system/branches'
ENGINEERING=ROOT/'output/nygrid_2025_ac_system/engineering'
LINE=ROOT/'output/nygrid_2025_line_parameters'
PARENT=LINE/'overlays/engineering_nominal/full191_network_cases.mat'
POST=ROOT/'output/nygrid_2025_dover_parameters/network/x_nominal.mat'
PRE_STATES=['refined_2025_pre_may_case','refined_2025_may21_case','refined_2025_may30_case']
URBAN_SOURCE_NON_OH={210,211,212,213,1236,1237,1984,1985,1988,1989,1994,2000}
STATION_EQUIVALENT_ROWS={52,208,213}
SPECIAL_OH={391,393,413}


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def record(path):
    p=Path(path);return dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p))


def clean(obj):
    if isinstance(obj,dict):return {k:clean(v) for k,v in obj.items()}
    if isinstance(obj,list):return [clean(v) for v in obj]
    if isinstance(obj,np.generic):return clean(obj.item())
    if isinstance(obj,float) and not math.isfinite(obj):return None
    return obj


def dump(path,obj):
    Path(path).write_text(json.dumps(clean(obj),indent=2,allow_nan=False)+'\n',encoding='utf-8')


def default_conductor(kv,catalog):
    family,code=('ACSR','Linnet') if kv<=69 else ('ACSR','Hawk') if kv<200 else ('ACSR','Drake') if kv<300 else ('ACSS','Mallard') if kv<400 else ('ACSR','Cardinal')
    choices=[c for c in catalog if c['family']==family and c['code_word']==code]
    require(len(choices)==1,'Default conductor is absent or ambiguous')
    return choices[0]


def equipment_equivalent(source,kind,defaults):
    """Finite pre-solve equipment proxy, never sized from solved loading."""
    z=source.copy();basis=[]
    if z[3]<=0:
        z[3]=.1;basis.append('nonpositive_X_replaced_by_declared0p1pu_equipment_reactance')
    if z[2]<=0 or not .003<=z[2]/z[3]<=.4:
        z[2]=z[3]/(60 if kind=='PAR' else 100 if kind in ['station_reactance_equivalent','accounting_station_link'] else 40)
        basis.append('positive_winding_or_station_loss_assumption_X_over_R')
    require(z[4]>=0,'Negative source B requires explicit equipment review')
    if kind=='PAR' and source[0]==20003 and source[1]==21001:
        ceiling=750.;banks=1;bank_mva=750.;basis.append('source_Dover750MVA_per_bank_nameplate')
    else:
        pool=defaults['transformer_per_bank_MVA_pool']
        options=[]
        for banks in defaults['transformer_integer_parallel_bank_counts']:
            for bank_mva in pool:
                own=math.hypot(z[2],z[3])*banks*bank_mva/100
                penalty=abs(math.log(own/.12))+.02*(banks-1)
                options.append((penalty,banks,float(bank_mva),own))
        _,banks,bank_mva,_=min(options)
        ceiling=banks*bank_mva;basis.append('finite_synthetic_equipment_MVA_selected_by_impedance_own_base_plausibility_not_loading')
    own=math.hypot(z[2],z[3])*ceiling/100
    normal=defaults['transformer_own_base_impedance_screen_pu'][0]<=own<=defaults['transformer_own_base_impedance_screen_pu'][1]
    z[5:8]=ceiling
    return z,dict(equipment_ceiling_mva=ceiling,equipment_parallel_banks=int(banks),equipment_per_bank_mva=bank_mva,
        equipment_own_base_z_pu=own,equipment_own_base_screen_pass=normal,
        equipment_ceiling_basis=';'.join(basis),equipment_equivalent_not_literal_nameplate=not(kind=='PAR' and source[0]==20003))


def classification(i,key,row,kv,source_row,role,ever):
    if not ever:return 'inactive_provenance',False,'inactive_in_all_selected2025_operating_topologies'
    if key.startswith('DOVER:PAR:') or key.startswith('RCC:PAR:'):return 'PAR',False,'registered_phase_shifting_equipment'
    if abs(kv[0]-kv[1])>1e-9 or row[8] not in [0,1]:return 'transformer_equivalent',False,'voltage_base_change_or_nonunity_tap;not_bare_overhead_conductor'
    if 'IDLE_LEAF' in key or role.startswith('algebraic_'):return 'accounting_station_link',False,'zero_injection_station_or_identity_scaffold_not_a_physical_line'
    if i in STATION_EQUIVALENT_ROWS:return 'station_reactance_equivalent',False,'same_station_finite_reactance_not_an_ideal_breaker;equipment_identity_unverified'
    if kv[0]<69:return 'station_reactance_equivalent',False,'low_voltage_station_equivalent_outside_transmission_conductor_scope'
    if key.startswith('RCC:CABLE:'):return 'documented_underground_cable',False,'primary_project_construction;conductor_geometry_and_sheath_unverified'
    if key.startswith('RECEIVING:') or key=='ASSET:ANNEX_E13_Q35_PROXY':return 'synthetic_cable_network_equivalent',False,'inherited_urban_cable_template_or_project_connection;not_a_unique_installed_cable'
    if source_row in URBAN_SOURCE_NON_OH:return 'urban_non_OH_network_equivalent',False,'conservative_urban_or_mixed_route_classification_assumption;not_an_installed_cable_certificate'
    if source_row>0 and kv[0]==138 and row[4]>0:return 'cable_compatible_source_equivalent',False,'historical_source_high_charging138kV_circuit;electrical_cable_compatibility_not_unique_type_identification'
    if i in SPECIAL_OH:return 'design_based_overhead',True,'project_design_conductor_and_line_only_estimate'
    return 'synthetic_overhead_corridor',True,'explicit_synthetic_OH_interpretation_of_passive_same_voltage_network_path'


def anchor_segments(i,key,catalog):
    by={(c['family'],c['code_word']):c for c in catalog}
    if i==391:
        basis=json.loads((LINE/'estimates/engineering_basis.json').read_text())
        item=next(x for x in basis['F84_estimates'] if x['scenario_name']=='engineering_nominal')
        return [segment(by['ACSS','Mallard'],i,key,'F84',item['length_m'],1,2,345.,item['gmd_m'],.4572,
                'source_design_Mallard_twin14p6mi_representative_geometry;synthetic_system_loading')]
    table=pd.read_csv(LINE/'estimates/Dover_line_only_estimates_not_applied.csv')
    table=table.loc[(table.temperature_c==95)&(table.adjacent_phase_spacing_ft==25.6)].set_index('section')
    names=['Y17_NY_line_only'] if i==393 else ['398_NY_line_only','398_CT_line_only']
    result=[]
    for name in names:
        item=table.loc[name];con=by['ACSS','Bluebird' if name=='398_CT_line_only' else 'Mallard']
        result.append(segment(con,i,key,name,float(item.length_m),1,int(item.subconductors_per_phase),345.,float(item.gmd_m),.4572,
                              'source_design_heterogeneous_Dover_line_section;no_PAR_impedance_in_conductor'))
    return result


def provisional_cable(source,key,kv,defaults):
    """Positive historical R/X electrical equivalent pending candidate audit."""
    z=source.copy();require(z[2]>0 and z[3]>0,'Cable equivalent lacks passive source R/X')
    length_miles={'RCC:CABLE:QUEENS':6.,'RCC:CABLE:BROOKLYN':1.,'RCC:CABLE:STATEN':9.4,
                  'RECEIVING:GREENWOOD_CORONA':8.,'RECEIVING:FOXHILLS_GREENWOOD':10.}
    length=length_miles[key]*1609.344 if key in length_miles else z[3]*kv**2/100/.00015
    if z[4]<=0:z[4]=2*math.pi*60*.2e-9*length*kv**2/100
    ceiling=math.sqrt(3)*kv*defaults['unrated_cable_selected_current_per_circuit_A']/1000
    z[5:8]=ceiling
    return z,dict(equipment_ceiling_mva=ceiling,equipment_parallel_banks=1,equipment_per_bank_mva=ceiling,
        equipment_ceiling_basis='declared1000A_single_cable_circuit_static_study_ceiling;not_IEC60287_or_nameplate',
        provisional_cable_candidate_mapping=True,cable_length_m=length,
        cable_parameter_scope='positive_historical_R_X_and_source_B_or_declared0p2nF_per_m_fallback;candidate_inverse_audit_pending')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    input_paths=[POST,PARENT,ENGINEERING/'thermal_conductors.csv',ENGINEERING/'geometry_defaults.csv',
        ENGINEERING/'synthetic_equipment_defaults.json',ENGINEERING/'engineering_defaults.json',
        ROOT/'output/nygrid_2025_downstate/network/branch_register.csv',
        LINE/'estimates/engineering_basis.json',LINE/'estimates/Dover_line_only_estimates_not_applied.csv']
    before={str(p):sha(p) for p in input_paths}
    post=loadmat(POST,simplify_cells=True);pre=loadmat(PARENT,simplify_cells=True)
    original=np.asarray(post['full_case']['branch'],float)
    require(original.shape==(413,13),'Wrong post-Dover branch parent')
    keys=np.asarray(post['full_branch_keys']).astype(str)
    bus=post['full_case']['bus'];kvmap=dict(zip(bus[:,0].astype(int),bus[:,9]));names=dict(zip(bus[:,0].astype(int),post['full_case']['bus_name']))
    catalog=pd.read_csv(ENGINEERING/'thermal_conductors.csv').to_dict('records')
    geometry=pd.read_csv(ENGINEERING/'geometry_defaults.csv');defaults=json.loads((ENGINEERING/'synthetic_equipment_defaults.json').read_text())
    require(len(catalog)>=14 and any(c['code_word']=='Linnet' for c in catalog),'Complete current catalog required')
    register=pd.read_csv(ROOT/'output/nygrid_2025_downstate/network/branch_register.csv',keep_default_na=False)
    ever=original[:,10]>0
    for state in PRE_STATES:ever[:410]|=np.asarray(pre[state]['branch'])[:,10]>0
    # Physical original branch211 is replaced by six retained transfer records.
    ever[210]=False
    overlay=original.copy();assignments=[];segments=[];candidate_rows=[];replacement_rows=[]
    for ix,(key,source) in enumerate(zip(keys,original)):
        i=ix+1;vfrom=float(kvmap[int(source[0])]);vto=float(kvmap[int(source[1])])
        rr=register.iloc[ix] if ix<410 else None
        src=int(rr.source_branch_row) if rr is not None else 0
        role=str(rr.electrical_role) if rr is not None else 'new_Dover_PAR_or_line'
        kind,thermal,why=classification(i,key,source,(vfrom,vto),src,role,bool(ever[ix]))
        row=dict(branch_row=i,branch_key=key,from_bus=int(source[0]),to_bus=int(source[1]),from_name=str(names[int(source[0])]),
            to_name=str(names[int(source[1])]),base_kv=vfrom,to_base_kv=vto,classification=kind,classification_basis=why,
            source_branch_row=src,source_role=role,active_in_any_selected2025_state=bool(ever[ix]),post_template_active=bool(source[10]),
            original_r_pu=float(source[2]),original_x_pu=float(source[3]),original_b_pu=float(source[4]),
            source_static_rating_mva=float(source[5]),source_static_rating_kind='conductor_design_summer_normal' if i==391 else
            'PAR_nameplate' if key.startswith('DOVER:PAR:') else 'historical_unspecified_facility_or_line_rating' if source[5]>0 else 'unspecified',
            thermal_overhead_eligible=thermal,installed_conductor_or_route_identified=False,asbuilt_identity_qualified=False,
            power_scale='existing_gamma_scaled_synthetic_AC',current_gamma_lift=False,parameter_gamma_transform=False,
            no_dispatch_or_interface_fit=True,parameter_quality='not_yet_evaluated',mapping_status='complete_classification')
        new=source.copy()
        if not ever[ix]:
            row.update(parameter_quality='inactive_provenance_not_used_in_AC_or_thermal_constraints',equipment_ceiling_mva=0.,equipment_ceiling_basis='inactive_no_runtime_equipment_claim')
        elif thermal:
            if i in SPECIAL_OH:
                ss=anchor_segments(i,key,catalog)
                new[2:5]=[sum(s['reference_'+p+'_pu'] for s in ss) for p in ['r','x','b']]
                require(np.max(abs(new[2:5]-source[2:5]))<1e-10,'Source design anchor reconstruction changed')
                derivation='preserved_source_design_line_only_R_X_B'
                ncircuits=1;rx_preserved=True;num_candidates=1
            else:
                geo=geometry.iloc[int(np.argmin(abs(geometry.nominal_kv.to_numpy(float)-vfrom)))].to_dict()
                max_length=250_000. if vfrom<200 else 500_000. if vfrom<300 else 700_000. if vfrom<400 else 1_000_000.
                counts=(1,) if src>0 else (1,2,3,4)
                candidates=inverse_candidates(source[2],source[3],source[4],vfrom,catalog,geo,counts,max_length)
                if candidates:
                    chosen=candidates[0];rx_preserved=True
                else:
                    chosen=fallback_candidate(source[2],source[3],vfrom,default_conductor(vfrom,catalog),geo,max_length);rx_preserved=False
                ss=[segment(chosen['conductor'],i,key,'equivalent_line',chosen['segment_length_m'],chosen['circuits'],
                    chosen['bundle_count'],vfrom,chosen['gmd_m'],chosen['bundle_spacing_m'],chosen['derivation'])]
                new[2:5]=[ss[0]['reference_'+p+'_pu'] for p in ['r','x','b']]
                derivation=chosen['derivation'];ncircuits=chosen['circuits'];num_candidates=len(candidates)
                for rank,cand in enumerate(candidates[:5],1):
                    candidate_rows.append(dict(branch_row=i,branch_key=key,rank=rank,score=cand['score'],catalog_id=cand['conductor']['catalog_id'],
                        circuits=cand['circuits'],bundle_count=cand['bundle_count'],length_m=cand['segment_length_m'],gmd_m=cand['gmd_m'],
                        bundle_spacing_m=cand['bundle_spacing_m'],geometric_b_pu=cand['electrical']['b_pu']))
                if not rx_preserved:replacement_rows.append(dict(branch_row=i,branch_key=key,reason='no_feasible_exact_R_X_catalog_geometry_and_length_candidate',
                    raw_X_implied_length_m=chosen['raw_X_implied_length_m'],length_clamped=chosen['length_clamped']))
            segments.extend(ss)
            current_limit=float(defaults['overhead_terminal_current_per_physical_circuit_A'][str(int(geometry.iloc[int(np.argmin(abs(geometry.nominal_kv.to_numpy(float)-vfrom)))].nominal_kv))])
            ceiling=math.sqrt(3)*vfrom*current_limit*ncircuits/1000
            new[5:8]=ceiling
            row.update(parameter_quality='positive_conductor_geometric_R_X_B_and_integer_multiplicity',parameter_basis=derivation,
                original_R_X_preserved=rx_preserved,geometric_B_used=True,reactive_compensation_invented=False,
                exact_inverse_candidates=num_candidates,thermal_segment_count=len(ss),circuits=ncircuits,
                bundle_count=ss[0]['bundle_count'] if len({s['bundle_count'] for s in ss})==1 else 'section_specific',
                route_length_m=sum(s['segment_length_m'] for s in ss),reference_temperature_c=ss[0]['reference_temperature_c'],
                equipment_ceiling_mva=ceiling,equipment_ceiling_basis='declared_voltage_class_terminal_A_per_circuit;independent_of_conductor_DLR_and_not_an_installed_limit',
                declared_terminal_current_per_circuit_A=current_limit,mapping_status='complete_synthetic_conductor_realization')
        elif 'cable' in kind or kind=='urban_non_OH_network_equivalent':
            new,equipment=provisional_cable(source,key,vfrom,defaults);row.update(equipment)
            row.update(parameter_quality='passive_cable_or_composite_R_L_C_equivalent;unique_conductor_mapping_pending',mapping_status='provisional_cable_candidate_review')
        else:
            new,equipment=equipment_equivalent(source,kind,defaults);row.update(equipment)
            row.update(parameter_quality='positive_passive_non_overhead_equipment_equivalent',mapping_status='complete_non_OH_equipment_assumption')
        if ever[ix]:require(new[2]>0 and new[3]>0 and new[4]>=0 and new[5]>0,'Incomplete passive active branch assignment')
        require(np.array_equal(new[[0,1,8,9,10,11,12]],source[[0,1,8,9,10,11,12]]),'Branch identity/status/control changed')
        overlay[ix]=new
        row.update(applied_r_pu=float(new[2]),applied_x_pu=float(new[3]),applied_b_pu=float(new[4]),applied_rate_a_mva=float(new[5]),
            delta_r_pu=float(new[2]-source[2]),delta_x_pu=float(new[3]-source[3]),delta_b_pu=float(new[4]-source[4]))
        assignments.append(row)
    overlay[210,10]=0
    assignments=pd.DataFrame(assignments);segments=pd.DataFrame(segments)
    require(len(assignments)==413 and assignments.branch_key.is_unique,'Incomplete branch identity ledger')
    needed=set(assignments.loc[assignments.thermal_overhead_eligible,'branch_row'])
    require(set(segments.branch_row)==needed,'An overhead branch lacks thermal segments')
    max_r=max_x=max_b=0.
    for branch_row,group in segments.groupby('branch_row'):
        total=group[['reference_r_pu','reference_x_pu','reference_b_pu']].sum().to_numpy(float)
        delta=np.abs(total-overlay[int(branch_row)-1,2:5]);max_r=max(max_r,delta[0]);max_x=max(max_x,delta[1]);max_b=max(max_b,delta[2])
        require(float(delta.max())<1e-10,'Segment series composition disagrees with branch reference')
    paths=[]
    for name,table in [('branch_assignments',assignments),('thermal_segments',segments),('inverse_candidates',pd.DataFrame(candidate_rows)),
                       ('explicit_R_X_replacements',pd.DataFrame(replacement_rows))]:
        path=OUT/(name+'.csv');table.to_csv(path,index=False,lineterminator='\n');paths.append(path)
    metadata=dict(status='provisional_electrical_and_OH_math_checked;cable_candidate_mapping_and_independent_review_pending',
        study_scale='existing_gamma_scaled_injections_as_synthetic_AC_system',baseMVA=100.,
        thermal_current_gamma_lift=False,impedance_gamma_transform=False,internal_interface_observations_read=False,
        dispatch_or_OPF_outcomes_read=False,asbuilt_identity_claim=False,all_active_OH_have_thermal_segments=True,
        branch_status_policy='apply_the_parent_dated_status_then_disable_original211_for_the_six_transfer_contract',
        overwrite_columns_1based=[3,4,5,6,7,8],preserve_endpoints_tap_shift_and_dated_status=True,
        pure_geometric_B_for_OH=True,zero_RATE_A_means_unknown_in_parent_not_zero_thermal_capability=True)
    mat=OUT/'engineering_overlay.mat'
    savemat(mat,dict(branch_reference=overlay,pre_dover_branch_reference=overlay[:410].copy(),branch_keys=np.asarray(keys,dtype=object),
        baseMVA=100.,metadata=metadata),do_compression=True,long_field_names=True);paths.append(mat)
    require(before=={str(p):sha(p) for p in input_paths},'Source inputs changed during assembly')
    report=dict(passed=True,construction_math_checked=True,whole_system_AC_or_thermal_validation=False,
        provisional_cable_mapping_pending=True,independent_review_pending=True,created_utc=datetime.now(timezone.utc).isoformat(),
        total_branch_records=413,ever_active_records=int(ever.sum()),OH_branch_count=len(needed),thermal_segment_count=len(segments),
        classification_counts=assignments.groupby('classification').size().to_dict(),
        active_classification_counts=assignments.loc[assignments.active_in_any_selected2025_state].groupby('classification').size().to_dict(),
        overhead_exact_R_X_preserved=int(assignments.get('original_R_X_preserved',pd.Series()).fillna(False).sum()),
        overhead_R_X_redesigned=len(replacement_rows),source_record_identities_preserved=97,
        max_segment_R_error_pu=max_r,max_segment_X_error_pu=max_x,max_segment_B_error_pu=max_b,
        rating_role_policy='source_static_ratings_separate_from_synthetic_hardware_ceilings;F84_1323MVA_is_conductor_design_not_hardware',
        dependencies=[record(p) for p in input_paths+[Path(__file__),Path(__file__).with_name('line_equivalents.py')]],
        outputs=[record(p) for p in paths])
    dump(OUT/'branch_engineering_receipt.json',report)
    print(json.dumps(clean({k:v for k,v in report.items() if k not in ['dependencies','outputs']}),indent=2))


if __name__=='__main__':main()
