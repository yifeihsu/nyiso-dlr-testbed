"""Infer a declared set of synthetic overhead realizations from R and X.

No geographic chord, power-flow result, NYISO error or weather selects a fit.
R and X are never changed. The catalog and engineering search bounds are the
preserved AC study's assumptions; this is not installed-asset identification.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import csv
import hashlib
import importlib.util
import json
import math

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_conductor_inference'
ENGINE=ROOT/'scripts/nygrid_2025_ac_system/branches/line_equivalents.py'
spec=importlib.util.spec_from_file_location('frozen_conductor_physics',ENGINE)
physics=importlib.util.module_from_spec(spec);spec.loader.exec_module(physics)
CATALOG=ROOT/'output/nygrid_2025_ac_system/engineering/thermal_conductors.csv'
GEOMETRY=ROOT/'output/nygrid_2025_ac_system/engineering/geometry_defaults.csv'
REGISTRY=ROOT/'output/nygrid_2025_ac_system/branches/branch_assignments.csv'


def sha(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def record(p):return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p))


def records(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def inputs():return records(CATALOG),{float(r['nominal_kv']):r for r in records(GEOMETRY)}


def default_maximum_length_m(kv):
    """Preserve the earlier study's broad voltage caps, without its map chord."""
    return 250_000. if kv<200 else 500_000. if kv<300 else 700_000. if kv<400 else 1_000_000.


def infer(r_pu,x_pu,kv,base_mva=100.,b_pu=None,circuits=(1,2,3,4),
          minimum_length_m=5.,maximum_length_m=None,catalog=None,geometry=None):
    """Return all feasible, ranked candidates and an explicit uncertainty summary.

    Geometry/length windows are declared synthetic priors. Identical circuit
    multiplicity is not identifiable from R/X; all allowed integer hypotheses
    remain visible. The default ranking uses B only when supplied and positive.
    """
    length_cap_policy='inherited_voltage_class_synthetic_cap_without_geographic_chord' if maximum_length_m is None else 'explicit_user_length_cap_sensitivity'
    maximum_length_m=default_maximum_length_m(kv) if maximum_length_m is None else maximum_length_m
    assert all(math.isfinite(x) for x in [r_pu,x_pu,kv,base_mva,minimum_length_m,maximum_length_m])
    assert kv>0 and base_mva>0 and 0<minimum_length_m<=maximum_length_m
    assert circuits and all(type(n) is int and 1<=n<=4 for n in circuits)
    assert b_pu is None or math.isfinite(b_pu)
    catalog,geometries=inputs() if catalog is None else (catalog,None)
    geometry=geometries.get(kv) if geometry is None and geometries is not None else geometry
    result=dict(input_R_pu=r_pu,input_X_pu=x_pu,input_B_pu=b_pu,base_kV=kv,base_MVA=base_mva,
        candidate_count=0,status='not_evaluated',targets_changed=False,
        installed_conductor_identified=False,geographic_chord_used=False,
        power_flow_or_interface_observations_used=False,
        circuits_allowed=list(circuits),minimum_length_m=minimum_length_m,maximum_length_m=maximum_length_m,
        length_cap_policy=length_cap_policy,
        resistance_temperature_policy='catalog_reference_75C_ACSR_or95C_ACSS',
        B_used_for_ranking=b_pu is not None and b_pu>0,
        candidate_set_is_conditional_not_a_statistical_confidence_interval=True)
    if r_pu<=0 or x_pu<=0:
        result['status']='nonpositive_R_or_X_not_a_bare_passive_OH_candidate';return result,[]
    if geometry is None:
        result['status']='no_declared_geometry_window_for_voltage';return result,[]
    zbase=kv*kv/base_mva
    bundles=[int(x) for x in geometry['allowed_bundle_counts'].split(';')]
    spacings=sorted({float(geometry[k]) for k in ['bundle_spacing_min_m','bundle_spacing_m','bundle_spacing_max_m']})
    candidates=[];ratio=r_pu and x_pu/r_pu
    achievable=[];implied=[]
    for c in catalog:
        temperature=float(c['reference_temperature_c']);rsub=physics.resistance(c,temperature)
        for nb in bundles:
            for spacing in spacings:
                gm=physics.bundle_radius(float(c['gmr_m']),nb,spacing)
                gmd=physics.geometry_for_ratio(c,ratio,nb,spacing)
                if math.isfinite(gmd):implied.append(gmd)
                for bound in ['gmd_min_m','gmd_max_m']:
                    achievable.append(nb*physics.OMEGA*2e-7*math.log(float(geometry[bound])/gm)/rsub)
                if not float(geometry['gmd_min_m'])<=gmd<=float(geometry['gmd_max_m']):continue
                for nc in circuits:
                    length=r_pu*zbase*nc*nb/rsub
                    if not minimum_length_m<=length<=maximum_length_m:continue
                    e=physics.electrical(c,length,nc,nb,gmd,spacing,temperature,kv,base_mva)
                    re=abs(e['r_pu']-r_pu);xe=abs(e['x_pu']-x_pu)
                    assert re<max(1e-12,1e-10*r_pu) and xe<max(1e-12,1e-10*x_pu)
                    berr=abs(math.log(e['b_pu']/b_pu)) if result['B_used_for_ranking'] else 0.
                    # Preserve the original electrical-study ranking convention.
                    # Its weights are priors, not observed probabilities.
                    score=2*berr+.15*(nc-1)+.04*abs(nb-float(geometry['default_bundle_count']))
                    score+=.03*abs(math.log(gmd/float(geometry['gmd_nominal_m'])))
                    score+=.005*abs(math.log(spacing/float(geometry['bundle_spacing_m'])))
                    candidates.append(dict(catalog_id=c['catalog_id'],family=c['family'],code_word=c['code_word'],
                        reference_temperature_C=temperature,circuits=nc,bundle_count=nb,
                        bundle_spacing_m=spacing,GMD_m=gmd,length_m=length,base_kV=kv,base_MVA=base_mva,
                        forward_R_pu=e['r_pu'],forward_X_pu=e['x_pu'],derived_B_pu=e['b_pu'],
                        R_abs_error_pu=re,X_abs_error_pu=xe,
                        B_abs_difference_pu=abs(e['b_pu']-b_pu) if b_pu is not None else None,
                        B_signed_difference_pu=(e['b_pu']-b_pu) if b_pu is not None else None,
                        B_log_difference=berr if result['B_used_for_ranking'] else None,
                        conductor_diameter_m=float(c['diameter_m']),conductor_GMR_m=float(c['gmr_m']),
                        conductor_reference_resistance_ohm_per_m=rsub,
                        heat_capacity_J_per_m_K=float(c['heat_capacity_j_m_k']),
                        ranking_score=score,installed_conductor_identified=False))
    candidates.sort(key=lambda x:(x['ranking_score'],x['circuits'],x['catalog_id'],x['bundle_count'],x['bundle_spacing_m']))
    # For a single subconductor, the unused bundle spacing is not a distinct fit.
    unique={};dedup=[]
    for candidate in candidates:
        key=(candidate['catalog_id'],candidate['circuits'],candidate['bundle_count'],
             candidate['bundle_spacing_m'] if candidate['bundle_count']>1 else 0)
        if key not in unique:unique[key]=True;dedup.append(candidate)
    candidates=dedup
    for i,candidate in enumerate(candidates,1):candidate['candidate_rank']=i;candidate['realization_id']=f'candidate_{i:04d}'
    result.update(status='feasible_declared_synthetic_realizations' if candidates else 'no_candidate_under_declared_catalog_and_bounds',
        candidate_count=len(candidates),distinct_catalog_choices=len({c['catalog_id'] for c in candidates}),
        X_over_R=ratio,declared_X_over_R_min=min(achievable),declared_X_over_R_max=max(achievable),
        maximum_implied_GMD_m=max(implied) if implied else None,
        required_GMD_min_m=float(geometry['gmd_min_m']),required_GMD_max_m=float(geometry['gmd_max_m']),
        no_candidate_is_not_universal_physical_impossibility=True)
    if candidates:
        result['selected_by_declared_ranking']=candidates[0]
        result['candidate_length_range_m']=[min(c['length_m'] for c in candidates),max(c['length_m'] for c in candidates)]
        result['candidate_derived_B_range_pu']=[min(c['derived_B_pu'] for c in candidates),max(c['derived_B_pu'] for c in candidates)]
    return result,candidates


def save_csv(p,rows):
    assert rows
    with p.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def audit_model():
    """Review imported versus CURRENT electrical targets; change no model file."""
    OUT.mkdir(parents=True,exist_ok=True);catalog,geometries=inputs()
    branch_rows=[r for r in records(REGISTRY) if r['classification'] in ['synthetic_overhead_corridor','design_based_overhead']]
    summaries=[];all_candidates=[];special=None
    for r in branch_rows:
        parent=int(r['branch_row']);kv=float(r['base_kv']);same=kv==float(r['to_base_kv'])
        assert same
        imported=tuple(float(r[f'original_{k}_pu']) for k in ['r','x','b'])
        current=tuple(float(r[f'applied_{k}_pu']) for k in ['r','x','b'])
        if parent==224:current=(.02,.0147,0.)  # frozen loss-consistent revision
        for basis,target in [('imported_RX',imported),('current_model_RX',current)]:
            summary,candidates=infer(target[0],target[1],kv,100.,target[2],catalog=catalog,geometry=geometries.get(kv))
            prefix=dict(original_parent_row=parent,branch_key=r['branch_key'],target_basis=basis,
                source_role=r['source_role'],prior_parameter_basis=r['parameter_basis'],
                known_cable_or_identity_conflict=parent in [300,309,310,386],
                current_RX_equals_imported=abs(current[0]-imported[0])<1e-12 and abs(current[1]-imported[1])<1e-12)
            summaries.append(dict(**prefix,**{k:v for k,v in summary.items() if not isinstance(v,(list,dict))},
                                  selected_catalog_id=candidates[0]['catalog_id'] if candidates else '',
                                  selected_circuits=candidates[0]['circuits'] if candidates else 0,
                                  selected_bundle_count=candidates[0]['bundle_count'] if candidates else 0,
                                  selected_GMD_m=candidates[0]['GMD_m'] if candidates else None,
                                  selected_length_m=candidates[0]['length_m'] if candidates else None))
            all_candidates.extend(dict(**prefix,**c) for c in candidates)
            if parent==224 and basis=='current_model_RX':special=summary
    save_csv(OUT/'inverse_target_summary.csv',summaries)
    save_csv(OUT/'feasible_candidate_realizations.csv',all_candidates)
    current=[r for r in summaries if r['target_basis']=='current_model_RX']
    original=[r for r in summaries if r['target_basis']=='imported_RX']
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='R/X-conditioned homogeneous synthetic overhead candidate search; not a new electrical model or installed-line identification',
        baseline_model_commit='51e424a139e0d0ec42fcbbb35749deaf119cffc2',
        parent_targets=len(branch_rows),target_rows=len(summaries),feasible_candidate_rows=len(all_candidates),
        current_targets_with_candidates=sum(r['candidate_count']>0 for r in current),
        imported_targets_with_candidates=sum(r['candidate_count']>0 for r in original),
        source_identity_or_geographic_chord_required=False,
        selected_realizations_applied_to_electrical_or_thermal_model=False,
        existing_heterogeneous_design_segments_remain_a_separate_valid_realization_class=True,
        no_candidate_scope='Only the archived14-conductor catalog, existing voltage geometry bounds, fixed catalog reference temperatures, integer circuits1..4 and lengths5m..the inherited250/500/700/1000km voltage-class cap were searched; no geographic chord is required.',
        original_vs_prior_engineered_parameters_kept_separate=True,
        parent224=special,dependencies=[record(p) for p in [Path(__file__),ENGINE,CATALOG,GEOMETRY,REGISTRY]],
        outputs=[record(OUT/'inverse_target_summary.csv'),record(OUT/'feasible_candidate_realizations.csv')])
    (OUT/'inverse_search_receipt.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['dependencies','outputs','parent224']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--audit-model',action='store_true')
    p.add_argument('--r-pu',type=float);p.add_argument('--x-pu',type=float);p.add_argument('--kv',type=float)
    p.add_argument('--base-mva',type=float,default=100.);p.add_argument('--b-pu',type=float)
    p.add_argument('--minimum-length-m',type=float,default=5.);p.add_argument('--maximum-length-m',type=float)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.audit_model:audit_model()
    else:
        p.error('--r-pu, --x-pu and --kv are required') if None in [a.r_pu,a.x_pu,a.kv] else None
        summary,candidates=infer(a.r_pu,a.x_pu,a.kv,a.base_mva,a.b_pu,
            minimum_length_m=a.minimum_length_m,maximum_length_m=a.maximum_length_m)
        if a.output:
            assert not a.output.exists() or not any(a.output.iterdir()), 'Choose a new or empty output directory to preserve earlier inference results'
            a.output.mkdir(parents=True,exist_ok=True)
            (a.output/'inference_summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8')
            if candidates:save_csv(a.output/'candidate_realizations.csv',candidates)
        print(json.dumps(summary,indent=2,allow_nan=False))
