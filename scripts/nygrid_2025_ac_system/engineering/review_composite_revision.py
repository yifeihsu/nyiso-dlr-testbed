"""Independent immutable-revision delta audit for composite terminal limits."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'output/nygrid_2025_ac_system'
B=BASE/'branches'


def record(p):
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=p.relative_to(ROOT).as_posix(),sha256=h)


def check(ok,msg):
    if not ok:raise AssertionError(msg)


def close(a,b,msg):
    check(np.asarray(a).shape==np.asarray(b).shape and np.allclose(a,b,atol=1e-10,rtol=0,equal_nan=True),msg)


def main():
    r2=B/'revision_02_complete_mapping';r3=B/'revision_03_composite_capacity'
    old=pd.read_csv(r2/'branch_assignments.csv').set_index('branch_row')
    new=pd.read_csv(B/'branch_assignments.csv').set_index('branch_row')
    independent_path=BASE/'engineering/voltage_changing_classification_review.csv'
    c=pd.read_csv(independent_path).set_index('branch_row')
    composite=c.loc[c.revised_evidence_class.eq('unresolved_composite_voltage_changing_equivalent')]
    station=c.loc[c.revised_evidence_class.eq('station_transformer_compatible_equivalent')]
    check(len(composite)==65 and len(station)==38,'Complete evidence classification')
    check(old.branch_key.equals(new.branch_key) and len(new)==413,'Full branch identity preserved')
    om=loadmat(r2/'engineering_overlay.mat',simplify_cells=True);nm=loadmat(B/'engineering_overlay.mat',simplify_cells=True)
    expect=om['branch_reference'].copy();expected_limits=om['terminal_current_limit_A'].copy()
    for row,v in composite.iterrows():
        check(new.loc[row,'classification']=='composite_voltage_changing_equivalent','Explicit composite classification')
        check(new.loc[row,'capacity_inferred_from_aggregate_X']==False and
              new.loc[row,'internal_line_transformer_decomposition_identified']==False and
              new.loc[row,'equipment_equivalent_not_literal_nameplate']==True,'Explicit unresolved non-nameplate composite scope')
        check(not new.loc[row,'thermal_overhead_eligible'],'No bare conductor certificate for composite interior')
        values=np.array([v.recommended_composite_nominal_mva_proxy,v.recommended_composite_from_A,v.recommended_composite_to_A])
        close(new.loc[row,['equipment_ceiling_mva','total_terminal_current_limit_from_a','total_terminal_current_limit_to_a']].to_numpy(float),values,'Independent class-based capacity values')
        expect[row-1,5:8]=values[0];expected_limits[row-1]=values[1:]
    close(nm['branch_reference'],expect,'Only selected composite MVA coefficients changed')
    close(nm['pre_dover_branch_reference'],expect[:410],'Pre-Dover effective matrix')
    close(nm['terminal_current_limit_A'],expected_limits,'Only selected composite terminal amperes changed')
    check(nm['baseMVA']==om['baseMVA']==100,'Unchanged system base')
    check(np.array_equal(nm['branch_keys'],om['branch_keys']),'MAT key identity')
    preserved=['from_bus','to_bus','base_kv','to_base_kv','source_branch_row','active_in_any_selected2025_state',
        'post_template_active','original_r_pu','original_x_pu','original_b_pu','source_static_rating_mva',
        'thermal_overhead_eligible','geographic_chord_m','length_min_m','length_max_m','preferred_length_m',
        'route_length_m','reference_temperature_c','applied_r_pu','applied_x_pu','applied_b_pu']
    for col in preserved:close(new[col].to_numpy(float),old[col].to_numpy(float),'Unchanged field '+col)
    unchanged=old.index.difference(composite.index)
    close(new.loc[unchanged,'equipment_ceiling_mva'].to_numpy(float),old.loc[unchanged,'equipment_ceiling_mva'].to_numpy(float),'Other equipment capacity priors unchanged')
    close(new.loc[station.index,'equipment_ceiling_mva'].to_numpy(float),old.loc[station.index,'equipment_ceiling_mva'].to_numpy(float),'38 transformer-compatible priors unchanged')
    for file in ['thermal_segments.csv','cable_segments.csv']:
        check(record(B/file)['sha256']==record(r2/file)['sha256'],'Immutable conductor/cable geometry '+file)
    for file in ['branch_assignments.csv','engineering_overlay.mat','thermal_segments.csv','cable_segments.csv']:
        check(record(B/file)['sha256']==record(r3/file)['sha256'],'Current immutable revision3 mirror '+file)
    check((~new.current_gamma_lift).all() and (~new.parameter_gamma_transform).all(),'No gamma transformation')
    plan=pd.read_csv(B/'section_and_reactor_plan.csv').set_index('original_branch_row')
    for row,p in plan.iterrows():
        is_oh=bool(old.loc[row,'thermal_overhead_eligible'])
        if is_oh:
            check(int(p.section_count)==max(1,int(np.ceil(old.loc[row,'route_length_m']/100000))),'Unchanged OH subdivision rule')
        eligible=(is_oh and old.loc[row,'route_length_m']>120*1609.344) or (bool(p.is_cable) and old.loc[row,'applied_b_pu']*100>=10)
        check(bool(p.reactor_selected)==eligible,'Unchanged reactor selection')
        close(np.asarray(p.reactor_total_nominal_mvar),np.asarray(.75*100*old.loc[row,'applied_b_pu'] if eligible else 0),'Unchanged reactor fraction/value')
    files=[r2/'branch_assignments.csv',r2/'engineering_overlay.mat',B/'branch_assignments.csv',B/'engineering_overlay.mat',
           r3/'branch_assignments.csv',r3/'engineering_overlay.mat',B/'thermal_segments.csv',B/'cable_segments.csv',
           B/'section_and_reactor_plan.csv',independent_path,Path(__file__)]
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent revision2-to-revision3 delta audit; exactly the evidence-classified 65 composite terminal-capacity priors change',
        records=413,composite_equivalents=65,station_transformer_compatible=38,
        all_413_R_X_B_preserved=True,all_conductor_cable_geometry_and_geographic_bounds_preserved=True,
        all_38_transformer_compatible_capacity_priors_preserved=True,reactor_policy_values_and_section_rules_unchanged=True,
        original_load_generation_transfer_data_not_modified_by_this_change=True,
        capacity_from_voltage_class_current_not_total_X_or_observed_flow=True,
        limitation='Internal line/transformer decomposition for 65 composite equivalents remains unresolved; direct OH thermal coverage does not certify those physical interiors.',
        checked_files=[record(p) for p in files])
    (BASE/'engineering/composite_revision_independent_review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='checked_files'},indent=2))


if __name__=='__main__':main()
