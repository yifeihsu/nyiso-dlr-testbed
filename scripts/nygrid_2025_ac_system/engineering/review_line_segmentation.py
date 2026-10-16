"""Independent cascade-pi accuracy against exact distributed-line ABCD.

Frozen physical R/X/B totals are the inputs. No OPF outcomes enter.
Comparisons use a balanced, transposed, uniform, uncoupled positive-sequence
line, with no shunt compensation in either model. Reactor choice is separate.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'output/nygrid_2025_ac_system'


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def abcd(z,y,sections):
    zz,yy=z/sections,y/sections
    p=np.array([[1+zz*yy/2,zz],[yy*(1+zz*yy/4),1+zz*yy/2]],complex)
    return np.linalg.matrix_power(p,sections)


def exact(z,y):
    gamma=np.sqrt(z*y)
    a=np.cosh(gamma)
    scale=np.sinh(gamma)/gamma
    return np.array([[a,z*scale],[y*scale,a]],complex)


def main():
    path=BASE/'branches/branch_assignments.csv'
    df=pd.read_csv(path)
    rows=[]
    for b in df.loc[df.thermal_overhead_eligible].itertuples():
        z=b.applied_r_pu+1j*b.applied_x_pu;y=1j*b.applied_b_pu
        target=exact(z,y)
        for scheme in ['unchanged_lumped','long_only_100km','long_only_50km','all_over_100km','all_over_50km']:
            maximum=50_000 if '50km' in scheme else 100_000
            split=(b.route_length_m>120*1609.344) if scheme.startswith('long_only') else scheme.startswith('all_over')
            n=max(1,math.ceil(b.route_length_m/maximum)) if split else 1
            model=abcd(z,y,n)
            relative=np.abs((model-target)/target)
            vr=1/model[0,0];vr_exact=1/target[0,0]
            jin=model[1,0]/model[0,0];jin_exact=target[1,0]/target[0,0]
            rows.append(dict(branch_row=b.branch_row,branch_key=b.branch_key,base_kv=b.base_kv,length_km=b.route_length_m/1000,
                scheme=scheme,sections=n,max_section_km=b.route_length_m/n/1000,
                A_complex_relative_error=float(relative[0,0]),B_complex_relative_error=float(relative[0,1]),
                C_complex_relative_error=float(relative[1,0]),D_complex_relative_error=float(relative[1,1]),
                maximum_ABCD_relative_error=float(relative.max()),
                open_end_voltage_magnitude_error_pu=abs(abs(vr)-abs(vr_exact)),
                open_end_voltage_complex_relative_error=abs((vr-vr_exact)/vr_exact),
                open_end_input_charging_complex_relative_error=abs((jin-jin_exact)/jin_exact),
                cascade_reciprocity_error=abs(np.linalg.det(model)-1)))
    result=pd.DataFrame(rows)
    target=BASE/'engineering/line_segmentation_accuracy.csv';result.to_csv(target,index=False,lineterminator='\n')
    summary=[]
    for scheme,g in result.groupby('scheme'):
        w=g.loc[g.maximum_ABCD_relative_error.idxmax()]
        summary.append(dict(scheme=scheme,original_OH_corridors=len(g),total_sections=int(g.sections.sum()),
            extra_zero_injection_buses=int(g.sections.sum()-len(g)),worst_branch_row=int(w.branch_row),
            maximum_ABCD_relative_error=float(w.maximum_ABCD_relative_error),
            maximum_open_end_voltage_magnitude_error_pu=float(g.open_end_voltage_magnitude_error_pu.max()),
            maximum_open_end_charging_relative_error=float(g.open_end_input_charging_complex_relative_error.max()),
            maximum_reciprocity_error=float(g.cascade_reciprocity_error.max())))
    selected=result.loc[result.scheme=='all_over_100km']
    report=dict(status='independent_planning_accuracy_check_not_implemented_design_validation',created_utc=datetime.now(timezone.utc).isoformat(),
        physical_reference='exact distributed homogeneous positive-sequence line with the same total R, X and shunt B',
        scope='OH corridors only; source-design short heterogeneous branch treated as aggregate for this screening, not a distributed identity proof',
        declared_planning_tolerances=dict(maximum_ABCD_relative_error=.005,maximum_no_load_voltage_magnitude_error_pu=.005),
        no_OPF_dispatch_or_observed_interface_inputs=True,summary=summary,
        all_over_100km_passes_declared_screen=bool((selected.maximum_ABCD_relative_error<.005).all() and
            (selected.open_end_voltage_magnitude_error_pu<.005).all()),
        notes=['The 0.5 percent ABCD screen is a declared synthetic-study accuracy criterion, not a formal industry limit.',
            'Terminal ABCD accuracy does not independently prove local temperature accuracy or installed geometry.',
            'Compensation must be represented identically in later model comparisons; this calculation excludes external reactors.'],
        dependencies=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in [path,Path(__file__)]],
        results_file=dict(path=target.relative_to(ROOT).as_posix(),sha256=sha(target)))
    cable_path=BASE/'branches/cable_segments.csv'
    cable_rows=[]
    for b in pd.read_csv(cable_path).itertuples():
        z=b.reference_r_pu+1j*b.reference_x_pu;y=1j*b.reference_b_pu
        target_exact=exact(z,y)
        for maximum in [math.inf,30_000]:
            n=1 if not math.isfinite(maximum) else max(1,math.ceil(b.segment_length_m/maximum))
            model=abcd(z,y,n)
            cable_rows.append(dict(branch_row=b.branch_row,branch_key=b.branch_key,length_km=b.segment_length_m/1000,
                scheme='unchanged_lumped' if n==1 and not math.isfinite(maximum) else 'cable_max30km',sections=n,
                maximum_ABCD_relative_error=float(np.abs((model-target_exact)/target_exact).max()),
                open_end_voltage_magnitude_error_pu=abs(abs(1/model[0,0])-abs(1/target_exact[0,0]))))
    cable_result=pd.DataFrame(cable_rows)
    cable_csv=BASE/'engineering/cable_segmentation_accuracy.csv';cable_result.to_csv(cable_csv,index=False,lineterminator='\n')
    report['cable_summary']=[]
    for scheme,g in cable_result.groupby('scheme'):
        report['cable_summary'].append(dict(scheme=scheme,total_cable_sections=int(g.sections.sum()),
            extra_zero_injection_buses=int(g.sections.sum()-len(g)),
            maximum_ABCD_relative_error=float(g.maximum_ABCD_relative_error.max()),
            maximum_open_end_voltage_magnitude_error_pu=float(g.open_end_voltage_magnitude_error_pu.max())))
    report['cable_screen_exception_original_rows']=[319,320]
    report['cable_results_file']=dict(path=cable_csv.relative_to(ROOT).as_posix(),sha256=sha(cable_csv))
    report['dependencies'].append(dict(path=cable_path.relative_to(ROOT).as_posix(),sha256=sha(cable_path)))
    report['scope']='OH and cable electrical accuracy; source-design short heterogeneous branch treated as aggregate only for screening; no cable thermal certification'
    (BASE/'engineering/line_segmentation_accuracy.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
