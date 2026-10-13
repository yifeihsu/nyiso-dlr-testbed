"""Independent new inference API and saved candidate-table audit.

No existing electrical case or previously delivered artifact is written.
CLI preservation fixtures use unique directories inside this audit namespace.
"""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import uuid

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_conductor_inference/independent'
TARGET=ROOT/'scripts/nygrid_2025_conductor_inference/infer_conductors.py'


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def record(path):return dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(path))


def truth(value):return str(value).lower()=='true'


def key(c):return (c['catalog_id'],int(c['circuits']),int(c['bundle_count']),float(c['bundle_spacing_m']) if int(c['bundle_count'])>1 else 0.)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    sys.dont_write_bytecode=True
    api=load_module('reviewed_new_inference',TARGET)
    independent=load_module('independent_conductor_math',Path(__file__).with_name('audit_inverse_physics.py'))
    catalog_path=ROOT/'output/nygrid_2025_ac_system/engineering/thermal_conductors.csv'
    geometry_path=ROOT/'output/nygrid_2025_ac_system/engineering/geometry_defaults.csv'
    registry_path=ROOT/'output/nygrid_2025_ac_system/branches/branch_assignments.csv'
    summary_path=OUT.parent/'inverse_target_summary.csv'
    candidates_path=OUT.parent/'feasible_candidate_realizations.csv'
    producer_path=OUT.parent/'inverse_search_receipt.json'
    paths=[TARGET,catalog_path,geometry_path,registry_path,summary_path,candidates_path,producer_path,
           Path(__file__).with_name('audit_inverse_physics.py')]
    before=[record(p) for p in paths]
    catalog=pd.read_csv(catalog_path).set_index('catalog_id',drop=False)
    geometry=pd.read_csv(geometry_path).set_index('nominal_kv')
    checks=[]
    def check(name,condition,detail=None):
        assert condition,name
        checks.append(dict(name=name,passed=True,detail=detail))
    conductor=catalog.loc['PRYSMIAN_ACSR_DRAKE_795_0_26_7'].to_dict()
    g=geometry.loc[345].to_dict()
    e=independent.forward(conductor,50000,1,2,10.2,.4572,345)
    s100,c100=api.infer(e['r_pu'],e['x_pu'],345,100,e['b_pu'])
    s200,c200=api.infer(2*e['r_pu'],2*e['x_pu'],345,200,e['b_pu']/2)
    d100={key(c):c for c in c100};d200={key(c):c for c in c200}
    check('same_physical_ohms_100_and_200_MVA_same_candidate_keys',bool(c100) and d100.keys()==d200.keys())
    scale_error=0.
    for k,c in d100.items():
        other=d200[k]
        scale_error=max(scale_error,abs(c['length_m']-other['length_m']),abs(c['GMD_m']-other['GMD_m']),
                        abs(c['forward_R_pu']*2-other['forward_R_pu']),abs(c['forward_X_pu']*2-other['forward_X_pu']),
                        abs(c['derived_B_pu']/2-other['derived_B_pu']))
    check('base_conversion_preserves_geometry_length_and_physical_RXB',scale_error<1e-9,scale_error)
    # Hold conductor/bundle/spacing fixed to expose circuit-length degeneracy.
    subset=[c for c in c100 if c['catalog_id']==conductor['catalog_id'] and c['bundle_count']==2 and c['bundle_spacing_m']==.4572]
    subset.sort(key=lambda x:x['circuits'])
    check('all_four_integer_circuit_alternatives_visible',[c['circuits'] for c in subset]==[1,2,3,4])
    check('same_RX_length_linear_B_quadratic_in_circuit_count',all(
        abs(c['length_m']/c['circuits']-50000)<1e-7 and abs(c['derived_B_pu']/c['circuits']**2-e['b_pu'])<1e-12
        for c in subset))
    check('ranking_is_declared_conditional_not_unique_identification',
          s100['candidate_set_is_conditional_not_a_statistical_confidence_interval'] and not s100['installed_conductor_identified']
          and not s100['power_flow_or_interface_observations_used'] and not s100['targets_changed'])
    noB,noc=api.infer(e['r_pu'],e['x_pu'],345,catalog=[conductor],geometry=g)
    highB,highc=api.infer(e['r_pu'],e['x_pu'],345,b_pu=16*e['b_pu'],catalog=[conductor],geometry=g)
    check('B_is_explicit_secondary_ranking_not_RX_change',not noB['B_used_for_ranking'] and highB['B_used_for_ranking']
          and noc[0]['circuits']==1 and highc[0]['circuits']==4
          and all(abs(c['forward_R_pu']-e['r_pu'])<1e-12 for c in noc+highc))
    single=independent.forward(conductor,30000,1,1,5.5,.4572,115)
    ss,sc=api.infer(single['r_pu'],single['x_pu'],115)
    check('single_bundle_unused_spacing_duplicates_removed',bool(sc) and len(sc)==len({key(c) for c in sc})
          and all(c['bundle_count']==1 and c['bundle_spacing_m']==.4572 for c in sc))
    for r,x,label in [(0,.01,'zero_R'),(-.01,.01,'negative_R'),(.01,0,'zero_X'),(.01,-.01,'negative_X')]:
        s,c=api.infer(r,x,345)
        check(label+'_returns_explicit_no_fit',not c and s['status']=='nonpositive_R_or_X_not_a_bare_passive_OH_candidate' and not s['targets_changed'])
    s,c=api.infer(.01,.1,765)
    check('missing_voltage_geometry_returns_explicit_no_fit',not c and s['status']=='no_declared_geometry_window_for_voltage')
    s,c=api.infer(.02,.0147,345,minimum_length_m=1e-6,maximum_length_m=1e12)
    check('parent224_no_fit_is_not_a_geographic_length_restriction',not c and s['status']=='no_candidate_under_declared_catalog_and_bounds'
          and s['no_candidate_is_not_universal_physical_impossibility'])
    s,c=api.infer(e['r_pu'],e['x_pu'],345,minimum_length_m=1,maximum_length_m=2)
    check('too_short_declared_length_window_returns_explicit_no_fit',not c and s['status']=='no_candidate_under_declared_catalog_and_bounds')

    # Fresh CLI subprocess exercises the actual writer, including preservation.
    fixture=OUT/'api_cli_checks'/uuid.uuid4().hex;fixture.mkdir(parents=True)
    target=fixture/'nonempty';target.mkdir();sentinel=target/'user_note.txt';sentinel.write_bytes(b'Keep this existing result.\n')
    cli=[sys.executable,'-B',str(TARGET),'--r-pu',str(e['r_pu']),'--x-pu',str(e['x_pu']),'--kv','345']
    p=subprocess.run(cli+['--output',str(target)],cwd=ROOT,capture_output=True,text=True)
    check('CLI_rejects_nonempty_output_without_overwriting',p.returncode!=0 and sentinel.read_bytes()==b'Keep this existing result.\n'
          and set(x.name for x in target.iterdir())=={'user_note.txt'})
    good=fixture/'new_output';p=subprocess.run(cli+['--output',str(good)],cwd=ROOT,capture_output=True,text=True)
    check('CLI_writes_new_output',p.returncode==0 and (good/'inference_summary.json').is_file() and (good/'candidate_realizations.csv').is_file())
    saved={p.name:sha(p) for p in good.iterdir()}
    p=subprocess.run(cli+['--output',str(good)],cwd=ROOT,capture_output=True,text=True)
    check('CLI_repeat_preserves_existing_inference_bytes',p.returncode!=0 and saved=={p.name:sha(p) for p in good.iterdir()})
    empty=fixture/'new_nofit_output';p=subprocess.run([sys.executable,'-B',str(TARGET),'--r-pu','0.02','--x-pu','0.0147','--kv','345','--output',str(empty)],cwd=ROOT,capture_output=True,text=True)
    check('CLI_no_fit_writes_summary_without_fake_candidates',p.returncode==0 and json.loads((empty/'inference_summary.json').read_text())['candidate_count']==0
          and not (empty/'candidate_realizations.csv').exists())

    # Independent saved-table audit uses neither the new nor old forward helper.
    summaries=pd.read_csv(summary_path)
    candidates=pd.read_csv(candidates_path)
    registry=pd.read_csv(registry_path).set_index('branch_row')
    producer=json.loads(producer_path.read_text())
    check('372_target_rows_are_unique_parent_basis_pairs',len(summaries)==372 and not summaries.duplicated(['original_parent_row','target_basis']).any())
    check('186_parents_each_have_imported_and_current_target',all(set(v.target_basis)=={'imported_RX','current_model_RX'} for _,v in summaries.groupby('original_parent_row')))
    lookup=summaries.set_index(['original_parent_row','target_basis'])
    rx_error=b_error=diagnostic_error=0.
    count=Counter()
    for row in candidates.to_dict('records'):
        parent=int(row['original_parent_row']);basis=row['target_basis'];target=lookup.loc[parent,basis]
        c=catalog.loc[row['catalog_id']].to_dict()
        f=independent.forward(c,float(row['length_m']),int(row['circuits']),int(row['bundle_count']),float(row['GMD_m']),
                              float(row['bundle_spacing_m']),float(row['base_kV']),float(row['reference_temperature_C']))
        check_base=float(row['base_MVA'])
        assert check_base==100.
        rx_error=max(rx_error,abs(f['r_pu']-float(target.input_R_pu)),abs(f['x_pu']-float(target.input_X_pu)),
                     abs(f['r_pu']-float(row['forward_R_pu'])),abs(f['x_pu']-float(row['forward_X_pu'])))
        b_error=max(b_error,abs(f['b_pu']-float(row['derived_B_pu'])))
        signed=f['b_pu']-float(target.input_B_pu)
        diagnostic_error=max(diagnostic_error,abs(float(row['B_abs_difference_pu'])-abs(signed)))
        if 'B_signed_difference_pu' in row:diagnostic_error=max(diagnostic_error,abs(float(row['B_signed_difference_pu'])-signed))
        assert 5<=row['length_m']<=float(target.maximum_length_m) and row['circuits'] in [1,2,3,4]
        geo=geometry.loc[float(row['base_kV'])]
        assert float(geo.gmd_min_m)-1e-12<=row['GMD_m']<=float(geo.gmd_max_m)+1e-12
        count[parent,basis]+=1
    check('all_saved_candidates_independently_reproduce_target_RX_and_B',rx_error<1e-10 and b_error<1e-10,
          dict(candidate_rows=len(candidates),maximum_RX_error_pu=rx_error,maximum_B_error_pu=b_error))
    check('B_absolute_and_optional_signed_diagnostics_correct',diagnostic_error<1e-10 and (candidates.B_abs_difference_pu>=0).all(),diagnostic_error)
    for row in summaries.itertuples():
        original=registry.loc[row.original_parent_row]
        basis_prefix='original' if row.target_basis=='imported_RX' else 'applied'
        expected=[float(original[f'{basis_prefix}_{k}_pu']) for k in ['r','x','b']]
        if row.target_basis=='current_model_RX' and row.original_parent_row==224:expected=[.02,.0147,0]
        assert max(abs(np.array(expected)-np.array([row.input_R_pu,row.input_X_pu,row.input_B_pu])))<1e-12
        assert count[row.original_parent_row,row.target_basis]==row.candidate_count
    check('saved_targets_are_actual_imported_or_current_values_and_counts_match',True)
    check('producer_counts_match_actual_tables',producer['target_rows']==len(summaries) and producer['feasible_candidate_rows']==len(candidates)
          and producer['current_targets_with_candidates']==int(((summaries.target_basis=='current_model_RX')&(summaries.candidate_count>0)).sum()))
    check('saved_candidate_physical_hypotheses_not_duplicated',not candidates.assign(_spacing=candidates.bundle_spacing_m.where(candidates.bundle_count>1,0))
          .duplicated(['original_parent_row','target_basis','catalog_id','circuits','bundle_count','_spacing']).any())
    # Validate the sixteen newly feasible imported targets and isolate the
    # geographical prior change from the separate global length-cap expansion.
    recovered=[]
    for row in summaries[summaries.target_basis=='imported_RX'].itertuples():
        prior=registry.loc[row.original_parent_row]
        if truth(prior.original_R_X_preserved):continue
        assert prior.parameter_basis=='synthetic_positive_R_X_B_redesign_from_nominal_geometry_and_X_implied_length'
        assert prior.classification=='synthetic_overhead_corridor'
        kv=float(prior.base_kv)
        cap=250000 if kv<200 else 500000 if kv<300 else 700000 if kv<400 else 1000000
        geometry_only,cs=api.infer(row.input_R_pu,row.input_X_pu,kv,b_pu=row.input_B_pu,maximum_length_m=cap)
        extended,extended_candidates=api.infer(row.input_R_pu,row.input_X_pu,kv,b_pu=row.input_B_pu,maximum_length_m=1e6)
        if not extended_candidates:
            assert row.candidate_count==0
            continue
        original_window,old=api.infer(row.input_R_pu,row.input_X_pu,kv,b_pu=row.input_B_pu,
                                     minimum_length_m=float(prior.length_min_m),maximum_length_m=float(prior.length_max_m))
        assert not old
        recovered.append(dict(original_parent_row=int(row.original_parent_row),branch_key=row.branch_key,base_kV=kv,
            prior_classification=prior.classification,prior_parameter_basis=prior.parameter_basis,
            prior_geographic_minimum_m=float(prior.length_min_m),prior_geographic_maximum_m=float(prior.length_max_m),
            prior_voltage_class_maximum_m=cap,new_maximum_m=1e6,
            default_selected_length_m=float(row.selected_length_m) if cs else None,default_candidate_count=int(row.candidate_count),
            extended_selected_length_m=extended_candidates[0]['length_m'],extended_candidate_count=len(extended_candidates),
            feasible_with_geography_removed_but_old_voltage_cap=bool(cs),
            geography_only_candidate_count=len(cs),requires_expanded_global_length_cap=not bool(cs)))
    recovered=pd.DataFrame(recovered)
    check('16_extended_window_recoveries_are_prior_redesigns_not_mixed_designs',len(recovered)==16)
    extra=recovered.loc[recovered.requires_expanded_global_length_cap,'original_parent_row'].tolist()
    check('13_default_geography_only_recoveries_and3_explicit_global_cap_recoveries',int(recovered.feasible_with_geography_removed_but_old_voltage_cap.sum())==13 and extra==[152,163,164],extra)
    check('default_uses_original_voltage_caps_and_labels_override',all(
        float(row.maximum_length_m)==(250000 if row.base_kV<200 else 500000 if row.base_kV<300 else 700000 if row.base_kV<400 else 1000000)
        and row.length_cap_policy=='inherited_voltage_class_synthetic_cap_without_geographic_chord'
        for row in summaries.itertuples()) and extended['length_cap_policy']=='explicit_user_length_cap_sensitivity')
    recovered_path=OUT/'recovered_imported_RX_attribution.csv';recovered.to_csv(recovered_path,index=False)
    after=[record(p) for p in paths]
    check('reviewed_code_and_source_tables_unchanged_during_audit',before==after)
    report=dict(passed=True,completed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent new infer_conductors.py API, exact saved372target/candidate audit and original-RX recovery attribution; no electrical solve or target edits',
        test_count=len(checks),tests=checks,summary_target_rows=len(summaries),candidate_rows=len(candidates),
        current_targets_with_candidates=int(((summaries.target_basis=='current_model_RX')&(summaries.candidate_count>0)).sum()),
        imported_targets_with_candidates=int(((summaries.target_basis=='imported_RX')&(summaries.candidate_count>0)).sum()),
        recovered_prior_redesign_imported_targets_default=13,recovered_under_explicit_1000km_override=16,geography_only_recoveries=13,
        also_requires_expanded_global_length_cap=extra,
        maximum_saved_candidate_RX_error_pu=rx_error,maximum_saved_candidate_B_error_pu=b_error,
        independent_physics_functions='Explicit conductor-pair distance products and directly derived resistance/reactance/charging equations, not the new inference forward helper',
        no_unique_conductor_or_installed_asset_claim=True,no_old_model_or_handoff_artifact_modified=True,
        dependencies=before+[record(Path(__file__).resolve())],outputs=[record(recovered_path)],
        fixture_directory=fixture.relative_to(ROOT).as_posix())
    (OUT/'inference_api_independent_review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['tests','dependencies','outputs']},indent=2))


if __name__=='__main__':main()
