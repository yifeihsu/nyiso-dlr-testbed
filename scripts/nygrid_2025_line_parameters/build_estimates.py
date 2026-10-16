"""Source-informed line estimates, before any observed-interface scoring.

The applied case improves F84's old aggregate-budget impedance and the Staten
route length. Dover estimates are line-only and remain outside the operating
overlay because the public PAR series impedance is unresolved. Underground
cables retain their explicitly qualified historical electrical analog.
"""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
import pandas as pd
from scipy.io import loadmat
from line_physics import (overhead_transposed, interpolate_resistance,
                          design_mva_from_phase_current, M_PER_MILE, base_impedance)

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_line_parameters'
DEST=OUT/'estimates'
F84='CV:PV_CV_F84'
Y17='DOVER:CV_DOVER_Y17'
LM='DOVER:DOVER_LM_398'
KEYS=[F84,Y17,LM,'RCC:CABLE:QUEENS','RCC:CABLE:BROOKLYN','RCC:CABLE:STATEN']
FIELDS=['r_pu','x_pu','b_pu','rate_a_mva','rate_b_mva','rate_c_mva']


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def record(path):return dict(path=Path(path).relative_to(ROOT).as_posix(),sha256=sha(path))
def dump(path,obj):Path(path).write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8',newline='\n')
def require(ok,message):
    if not ok:raise ValueError(message)


def build():
    DEST.mkdir(parents=True,exist_ok=True)
    project=OUT/'project_source_register.csv'
    catpath=OUT/'conductors/conductor_catalog.csv'
    catproof=OUT/'conductors/catalog_validation.json'
    register=ROOT/'output/nygrid_2025_downstate/network/branch_register.csv'
    network_path=ROOT/'output/nygrid_2025_downstate/network/network_cases.mat'
    inventory=OUT/'local_inventory/existing_project_parameter_assignments.csv'
    sources=pd.read_csv(project,keep_default_na=False)
    catalog=pd.read_csv(catpath,keep_default_na=False).set_index('catalog_id')
    old=pd.read_csv(register,keep_default_na=False).set_index('branch_key')
    frozen_branch=loadmat(network_path,simplify_cells=True)['refined_2025_case']['branch']
    for field,column in zip(FIELDS,[2,3,4,5,6,7]):
        old[field]=frozen_branch[old.model_branch_row.to_numpy(int)-1,column]
    proof=json.loads(catproof.read_text())
    require(proof['passed'] and not proof['R_matching_alone_can_certify_conductor'],'Unqualified conductor catalog')
    for item in proof['files']:
        require(sha(ROOT/item['path'])==item['sha256'],'Changed conductor catalog artifact')
    deps=[project,catpath,catproof,register,network_path,inventory,Path(__file__),Path(__file__).with_name('line_physics.py')]
    for path,digest in sources[['local_path','sha256']].drop_duplicates().itertuples(index=False,name=None):
        require(sha(ROOT/path)==digest,'Changed project source')
        deps.append(ROOT/path)
    for path,digest in catalog[['source_id','source_sha256']].drop_duplicates().itertuples(index=False,name=None):
        p=OUT/f'conductors/sources/{path}.pdf'
        require(sha(p)==digest,'Changed manufacturer PDF')
        deps.append(p)
    def value(asset,field):
        x=sources[(sources.asset_key==asset)&(sources.field==field)]
        require(len(x)==1,'Missing/ambiguous project field '+asset+' '+field)
        return x.iloc[0]['value']
    mallard=catalog.loc['PRYSMIAN_ACSS_MALLARD_795_0_30_19']
    bluebird=catalog.loc['PRYSMIAN_ACSS_BLUEBIRD_2156_0_84_19']
    require(value(F84,'conductor')=='Mallard 795 ACSS','Wrong F84 conductor family')
    require(int(value(F84,'subconductors_per_phase'))==2,'Wrong F84 bundle count')
    require(abs(float(mallard.diameter_m)/.0254-float(value(F84,'conductor_diameter')))<1e-12,'Project/catalog diameter disagreement')
    length=float(value(F84,'length'))
    spacing=float(value(F84,'bundle_spacing'))*.0254
    points=np.asarray(json.loads(value(F84,'representative_phase_centers')),float)*.3048
    temp=float(value(F84,'normal_rating_conductor_temperature'))
    kv=float(value(F84,'nominal_voltage'))
    def estimate(conductor,miles,geometry,bundle,temperature=temp,images=False):
        rac=interpolate_resistance(temperature,[25,75,200],
             np.asarray([conductor.r_ac25_ohm_per_m,conductor.r_ac75_ohm_per_m,conductor.r_ac200_ohm_per_m],float)*304.8)
        return overhead_transposed(length_m=miles*M_PER_MILE,conductor_diameter_m=float(conductor.diameter_m),
              conductor_gmr_m=float(conductor.gmr_m),ac_resistance_ohm_per_m=rac,
              bundle_count=bundle,bundle_spacing_m=spacing if bundle==2 else None,
              phase_xy_m=geometry,include_ground_images=images,base_kv=kv,base_mva=100.)
    nominal=estimate(mallard,length,points,2)
    require(abs(nominal['gmd_m']-float(value(F84,'representative_GMD')))<1e-12,'Geometry conversion mismatch')
    rating=float(value(F84,'summer_normal_apparent_power'))
    rating_calculated=design_mva_from_phase_current(float(value(F84,'summer_normal_current')),kv)
    require(abs(rating_calculated-rating)<.6,'Project ampere/MVA rating conversion failed')
    # The percentages below are declared geometry sensitivity assumptions, not
    # measured route bounds or statistical confidence limits.
    scenarios=[('engineering_nominal',points,False,'representative_project_drawing_geometry;earth_images_omitted'),
               ('geometry_spacing_80pct',points*.8,False,'declared_20pct_smaller_phase_spacing_sensitivity'),
               ('geometry_spacing_120pct',points*1.2,False,'declared_20pct_larger_phase_spacing_sensitivity'),
               ('ground_image_30ft',points+np.array([0,30*.3048]),True,
                'minimum_clearance_drawing_sensitivity;not_route_average_sag')]
    applied=[]; f84physics=[]
    for name,geometry,images,basis in scenarios:
        est=estimate(mallard,length,geometry,2,images=images)
        f84physics.append(dict(scenario_name=name,geometry_m=geometry.tolist(),geometry_basis=basis,
                              conductor_temperature_c=temp,**est))
        for key in KEYS:
            row=dict(scenario_name=name,full191_branch_key=key,base_mva=100.,
                     **{f:float(old.loc[key,f]) for f in FIELDS})
            if key==F84:
                row.update({f:est[f] for f in ['r_pu','x_pu','b_pu']})
                row.update(rate_a_mva=rating,rate_b_mva=0.,rate_c_mva=0.,
                    parameter_decision='source_design_conductor_and_representative_geometry_estimate',
                    rating_scope='summer_normal_conductor_design_only;not_verified_terminal_limited_facility_rating')
            elif key=='RCC:CABLE:STATEN':
                row['r_pu']*=9.4/9.2;row['x_pu']*=9.4/9.2
                row.update(parameter_decision='9p4mi_contractor_route_with_retained_uncertain_historical_per_mile_analog',
                           rating_scope='unknown;zero_placeholder_is_not_physical_infinite_capacity')
            else:
                row.update(parameter_decision='retained_qualified_assumption;line_only_or_installed_cable_parameters_unresolved',
                           rating_scope='unknown;zero_placeholder_is_not_physical_infinite_capacity')
            applied.append(row)
    cable_page=OUT/'sources/cables/Haugland_Goethals_FoxHills.html'
    cable_receipt=cable_page.with_suffix('.receipt.json')
    cable_proof=json.loads(cable_receipt.read_text())
    require(sha(cable_page)==cable_proof['sha256'],'Changed Staten contractor page')
    text=cable_page.read_text(encoding='utf-8')
    require('9.4-mile' in text and '138 kV XLPE' in text and 'single-circuit' in text,'Missing contractor route/construction evidence')
    deps.extend([cable_page,cable_receipt])
    frame=pd.DataFrame(applied)
    frame.to_csv(DEST/'parameter_estimates.csv',index=False,lineterminator='\n')

    # Dover is heterogeneous. Do not put the NY-only length into the entire
    # Dover-Long Mountain path or silently set the two PAR impedances to zero.
    # 25.6-ft adjacent spacing is an explicit generic H-frame geometry scenario,
    # corroborated as a geometry type but not a measured CT route-wide spacing.
    dover=[]
    for spacing_ft in [20.,25.6,35.]:
        geometry=np.array([[0,0],[spacing_ft,0],[2*spacing_ft,0]])*.3048
        for temperature in [75.,95.,180.]:
            pieces=[('Y17_NY_line_only',mallard,float(value(Y17,'length_NY')),2),
                    ('398_NY_line_only',mallard,float(value(LM,'length_NY')),2),
                    ('398_CT_line_only',bluebird,float(value(LM,'length_CT')),1)]
            estimates=[]
            for section,conductor,miles,bundle in pieces:
                item=estimate(conductor,miles,geometry,bundle,temperature)
                row=dict(section=section,temperature_c=temperature,adjacent_phase_spacing_ft=spacing_ft,
                    length_miles=miles,conductor=conductor.code_word,family=conductor.family,
                    subconductors_per_phase=bundle,geometry_status='declared_H_frame_spacing_sensitivity_not_asbuilt',
                    includes_PAR_series_impedance=False,applied_to_network=False,
                    **{k:v for k,v in item.items() if isinstance(v,(int,float,bool,str))})
                dover.append(row);estimates.append(item)
            composite=dict(dover[-1]);composite.update(section='Dover_LongMountain_composite_line_only',
                length_miles=float(value(LM,'length_NY'))+float(value(LM,'length_CT')),
                conductor='Mallard_NY_plus_Bluebird_CT',subconductors_per_phase='2_NY;1_CT',
                parallel_subconductors_per_phase='section_specific_see_component_rows')
            for k in ['length_m','r_pu','x_pu','b_pu','r_ohm','x_ohm','b_siemens','charging_mvar_at_nominal_kv']:
                composite[k]=estimates[1][k]+estimates[2][k]
            for k in ['gmd_m','bundle_gmr_m','bundle_capacitance_radius_m','inductance_h_per_m',
                      'capacitance_f_per_m','r_ac_ohm_per_m_per_subconductor']:
                composite[k]='section_specific_see_component_rows'
            dover.append(composite)
    pd.DataFrame(dover).to_csv(DEST/'Dover_line_only_estimates_not_applied.csv',index=False,lineterminator='\n')

    matches=[dict(branch_key=F84,construction='overhead',matched_design='2x795_Mallard_ACSS',
                  catalog_match='family_size_codeword_stranding_geometry_match',unresolved='installed_manufacturer_core_coating_route_average_geometry'),
             dict(branch_key=Y17,construction='overhead_line_and_unresolved_PAR_path',matched_design='2x795_Mallard_ACSS_line_only',
                  catalog_match='source_design_family_size_codeword',unresolved='PAR_series_impedance_and_tap_state;route_geometry'),
             dict(branch_key=LM,construction='heterogeneous_overhead_line_and_unresolved_PAR_path',matched_design='NY_2x795_Mallard_ACSS_plus_CT_1x2156_Bluebird_ACSS',
                  catalog_match='source_design_section_specific_family_size',unresolved='PAR_series_impedance_and_tap_state;CT_geometry_and_exact_transition_stationing')]
    for name in ['QUEENS','BROOKLYN','STATEN']:
        matches.append(dict(branch_key='RCC:CABLE:'+name,construction='underground_XLPE' if name=='STATEN' else 'underground_cable',
            matched_design='XLPE_insulation_family_only' if name=='STATEN' else 'underground_construction_only',
            catalog_match='no_unique_installed_conductor_match',unresolved='metal_area_material_sheath_bonding_R_temperature_inductance_capacitance_and_terminal_rating'))
    pd.DataFrame(matches).to_csv(DEST/'circuit_conductor_matches.csv',index=False,lineterminator='\n')
    nominalrows=frame[frame.scenario_name=='engineering_nominal'].copy()
    for f in FIELDS:
        nominalrows['old_'+f]=nominalrows.full191_branch_key.map(old[f])
        nominalrows['delta_'+f]=nominalrows[f]-nominalrows['old_'+f]
    nominalrows.to_csv(DEST/'before_after_parameters.csv',index=False,lineterminator='\n')
    dump(DEST/'engineering_basis.json',dict(passed=True,
        preferred_scenario='engineering_nominal',internal_interface_observations_used=False,
        scope='six_paths_added_relative_to_frozen2019_model;not_six_lines_built_after_calendar2019',
        F84_energized_date=value(F84,'energized_date'),F84_estimates=f84physics,
        F84_rating_design_mva=rating,F84_rating_from_current_mva=rating_calculated,
        rating_is_current_operational_facility_rating=False,
        Dover_policy='line_only_segment_estimates_saved;not_applied_until_PAR_series_impedance_and_path_binding_resolved',
        cable_policy='R_X_remain_qualified_historical_analog;Staten_length_updated9p2_to9p4mi;B0_and_rate0remain_unknown_placeholders',
        uncertainty_policy='declared_engineering_sensitivity_cases_not_confidence_intervals_or_exhaustive_bounds',
        dependencies=[record(p) for p in dict.fromkeys(deps)],
        outputs=[record(p) for p in [DEST/'parameter_estimates.csv',DEST/'Dover_line_only_estimates_not_applied.csv',
                                    DEST/'circuit_conductor_matches.csv',DEST/'before_after_parameters.csv']]))
    print(json.dumps(dict(passed=True,scenarios=len(scenarios),applied_table_rows=len(applied),
          f84_nominal={k:nominal[k] for k in ['r_pu','x_pu','b_pu']},dover_line_only_rows=len(dover)),indent=2))


if __name__=='__main__':build()
