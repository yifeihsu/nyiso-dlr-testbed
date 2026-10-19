"""Independent matrix-form checks of the saved engineering estimates.

Uses catalog SI values and balanced sequence vectors. It does not import the
estimator or its line_physics implementation and does not run a network PF.
"""
from pathlib import Path
import hashlib
import json
import math

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_line_parameters'
EPS0=8.8541878128e-12


def require(value,message):
    if not value:raise ValueError(message)


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def sequence_scalar(matrix):
    # Positive-sequence contraction equals the fully transposed modal value.
    a=np.exp(-2j*np.pi*np.arange(3)/3)
    return float(np.real(np.vdot(a,np.asarray(matrix)@a)/3))


def independent(conductor,length_m,points,n,bundle_m,temperature,ground):
    points=np.asarray(points,float)
    r=conductor.diameter_m/2
    ds=conductor.gmr_m
    if n==2:r=math.sqrt(r*bundle_m);ds=math.sqrt(ds*bundle_m)
    require(n in [1,2],'Unsupported bundle')
    inductance=np.zeros((3,3));potential=np.zeros((3,3))
    for i in range(3):
        for j in range(3):
            distance=float(np.linalg.norm(points[i]-points[j])) if i!=j else 0.
            inductance[i,j]=2e-7*math.log(1/(ds if i==j else distance))
            image=float(np.linalg.norm(points[i]-points[j]*[1,-1])) if ground else 1.
            potential[i,j]=math.log(image/(r if i==j else distance))/(2*math.pi*EPS0)
    rac=float(np.interp(temperature,[25,75,200],[conductor.r_ac25_ohm_per_m,conductor.r_ac75_ohm_per_m,conductor.r_ac200_ohm_per_m]))
    zbase=345**2/100
    return dict(r_pu=rac*length_m/n/zbase,
                x_pu=2*math.pi*60*sequence_scalar(inductance)*length_m/zbase,
                b_pu=2*math.pi*60/sequence_scalar(potential)*length_m*zbase)


def validate():
    cat_path=OUT/'conductors/conductor_catalog.csv'
    basis_path=OUT/'estimates/engineering_basis.json'
    estimates_path=OUT/'estimates/parameter_estimates.csv'
    dover_path=OUT/'estimates/Dover_line_only_estimates_not_applied.csv'
    catalogue=pd.read_csv(cat_path)
    def conductor(name):
        selected=catalogue.loc[catalogue.family.eq('ACSS')&catalogue.code_word.eq(name)]
        require(len(selected)==1,'Catalog family identity ambiguous')
        return selected.iloc[0]
    mallard,bluebird=conductor('Mallard'),conductor('Bluebird')
    basis=json.loads(basis_path.read_text());require(basis['internal_interface_observations_used'] is False,'Inference used observations')
    estimates=pd.read_csv(estimates_path);dover=pd.read_csv(dover_path)
    rows=[]
    for scenario in basis['F84_estimates']:
        value=estimates.loc[estimates.scenario_name.eq(scenario['scenario_name'])&estimates.full191_branch_key.eq('CV:PV_CV_F84')]
        require(len(value)==1,'Missing F84 estimate')
        # 18 inch bundle spacing is recorded in the project source register.
        source=pd.read_csv(OUT/'project_source_register.csv',keep_default_na=False)
        spacing=source.loc[source.asset_key.eq('CV:PV_CV_F84')&source.field.eq('bundle_spacing'),'value']
        require(len(spacing)==1,'Missing source bundle spacing')
        result=independent(mallard,scenario['length_m'],scenario['geometry_m'],2,float(spacing.iloc[0])*.0254,
                           scenario['conductor_temperature_c'],scenario['capacitance_ground_image_correction'])
        errors={key:abs(float(value.iloc[0][key])-expected) for key,expected in result.items()}
        require(max(errors.values())<1e-11,'F84 matrix-form estimate mismatch')
        rows.append(dict(kind='F84',scenario=scenario['scenario_name'],maximum_pu_error=max(errors.values())))
    require(len(dover)==36 and (~dover.applied_to_network.astype(bool)).all()
            and (~dover.includes_PAR_series_impedance.astype(bool)).all(),'Dover line-only scope changed')
    for row in dover.itertuples(index=False):
        if row.section=='Dover_LongMountain_composite_line_only':
            pieces=dover.loc[(dover.temperature_c==row.temperature_c)&(dover.adjacent_phase_spacing_ft==row.adjacent_phase_spacing_ft)
                &dover.section.isin(['398_NY_line_only','398_CT_line_only'])]
            require(len(pieces)==2,'Mixed-section composition lost')
            expected={key:float(pieces[key].sum()) for key in ['r_pu','x_pu','b_pu']}
        else:
            cv=bluebird if row.section=='398_CT_line_only' else mallard
            count=1 if row.section=='398_CT_line_only' else 2
            require(int(row.subconductors_per_phase)==count and row.family=='ACSS','Wrong conductor/bundle in section')
            s=row.adjacent_phase_spacing_ft*.3048
            expected=independent(cv,row.length_miles*1609.344,[[0,0],[s,0],[2*s,0]],count,.4572,row.temperature_c,False)
        err=max(abs(float(getattr(row,key))-value) for key,value in expected.items())
        require(err<1e-11,'Dover matrix-form/composite estimate mismatch')
        rows.append(dict(kind='Dover_line_only',scenario=f'{row.section}:{row.temperature_c}:{row.adjacent_phase_spacing_ft}',maximum_pu_error=err))
    # These two paths still contain unverified PAR/equipment impedance; cable
    # conductor geometry is not silently substituted with overhead conductor data.
    nominal=estimates.loc[estimates.scenario_name.eq('engineering_nominal')].set_index('full191_branch_key')
    inventory=pd.read_csv(OUT/'local_inventory/existing_project_parameter_assignments.csv').set_index('branch_key')
    for key in ['DOVER:CV_DOVER_Y17','DOVER:DOVER_LM_398']:
        for field in ['r_pu','x_pu','b_pu']:
            require(float(nominal.loc[key,field])==float(inventory.loc[key,field]),'Unqualified Dover value silently applied')
    files=[cat_path,basis_path,estimates_path,dover_path,OUT/'project_source_register.csv',Path(__file__)]
    report=dict(passed=True,independent_saved_parameter_rows=len(rows),
        maximum_pu_difference=max(row['maximum_pu_error'] for row in rows),
        method='independent3x3logarithmicinductance_and_potential_matrices_projected_onto_balanced_sequence',
        line_only_Dover_not_applied=True,network_power_flow_run=False,
        physical_installation_and_facility_thermal_rating_certified=False,
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p)) for p in files])
    dest=OUT/'validation';dest.mkdir(parents=True,exist_ok=True)
    (dest/'estimate_values_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    pd.DataFrame(rows).to_csv(dest/'independent_estimate_value_checks.csv',index=False,lineterminator='\n')
    print(json.dumps({key:value for key,value in report.items() if key!='files'},indent=2))
    return report


if __name__=='__main__':validate()
