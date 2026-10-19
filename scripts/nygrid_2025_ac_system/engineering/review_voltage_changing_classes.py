"""Evidence classification for voltage-changing synthetic network equivalents.

The evidence is endpoint labels, source identity, positive charging and the
explicitly approximate geography. No operating flow, OPF or residual is read.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'output/nygrid_2025_ac_system'


def record(path):
    with path.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=h)


def main():
    source=BASE/'branches/revision_02_complete_mapping/branch_assignments.csv'
    geo_source=ROOT/'output/nygrid_2025_downstate/geography/bus_geographic_register.csv'
    default_path=BASE/'engineering/synthetic_equipment_defaults.json'
    defaults=json.loads(default_path.read_text())
    amps={int(k):v for k,v in defaults['overhead_terminal_current_per_physical_circuit_A'].items()}
    a=pd.read_csv(source);g=pd.read_csv(geo_source).set_index('model_bus')
    selected=a.loc[a.classification.eq('transformer_equivalent')].copy();out=[]
    for b in selected.itertuples():
        same=str(b.from_name).strip().upper()==str(b.to_name).strip().upper()
        charging=b.applied_b_pu>0
        composite=(not same) or charging
        available=[]
        for kv in [b.base_kv,b.to_base_kv]:
            if kv>=69:
                category=min(amps,key=lambda x:abs(x-kv))
                available.append(math.sqrt(3)*kv*amps[category]/1000)
        assert available
        capacity=min(available)
        item=dict(branch_row=b.branch_row,branch_key=b.branch_key,from_bus=b.from_bus,to_bus=b.to_bus,
            from_name=b.from_name,to_name=b.to_name,from_kv=b.base_kv,to_kv=b.to_base_kv,
            original_classification=b.classification,same_station_label=same,positive_shunt_charging=charging,
            inherited_total_x_pu=b.applied_x_pu,inherited_total_b_pu=b.applied_b_pu,
            approximate_model_chord_m=b.geographic_chord_m,source_branch_row=b.source_branch_row,
            revised_evidence_class='unresolved_composite_voltage_changing_equivalent' if composite else 'station_transformer_compatible_equivalent',
            primary_reason='different_station_labels_or_positive_line_charging;total_X_not_identified_transformer_leakage' if composite else
                'same_station_label_and_zero_shunt_charging;supports_transformer_compatible_model_not_verified_nameplate',
            asbuilt_or_pure_transformer_nameplate_verified=False,direct_overhead_thermal_eligible=False,
            total_X_used_to_size_composite_capacity=False,
            prior_own_X_selected_equipment_mva=b.equipment_ceiling_mva,
            recommended_composite_nominal_mva_proxy=capacity if composite else None,
            recommended_composite_from_A=capacity*1000/(math.sqrt(3)*b.base_kv) if composite else None,
            recommended_composite_to_A=capacity*1000/(math.sqrt(3)*b.to_base_kv) if composite else None,
            voltage_class_current_policy='use_existing_transmission_class_A_at_each_side_ge69kV;common_MVA_is_minimum_available_terminal_MVA;derive_both_end_A_from_common_MVA',
            generator_voltage_side_reflected_from_transmission_MVA=bool(composite and min(b.base_kv,b.to_base_kv)<69),
            no_dispatch_or_solver_input=True)
        for name,bus in [('from',b.from_bus),('to',b.to_bus)]:
            if bus in g.index:
                item[name+'_coordinate_quality']=g.loc[bus,'coordinate_quality']
                item[name+'_coordinate_basis']=g.loc[bus,'coordinate_basis']
        out.append(item)
    df=pd.DataFrame(out)
    composite=df.loc[df.revised_evidence_class.eq('unresolved_composite_voltage_changing_equivalent')]
    assert len(df)==103 and len(composite)==65
    assert len(df.loc[df.same_station_label&~df.positive_shunt_charging])==38
    assert len(df.loc[df.source_branch_row.gt(0)&df.same_station_label&~df.positive_shunt_charging])==17
    path=BASE/'engineering/voltage_changing_classification_review.csv';df.to_csv(path,index=False,lineterminator='\n')
    bus130=a.loc[(a.from_bus==130)|(a.to_bus==130)].copy()
    assert set(bus130.branch_row)=={180,181,182,183}
    bus130=bus130[['branch_row','branch_key','from_bus','to_bus','base_kv','route_length_m','applied_b_pu']]
    bus130['nominal_charging_mvar']=100*bus130.applied_b_pu
    bus130['old_length_only_reactor_eligible']=bus130.route_length_m>120*1609.344
    bpath=BASE/'engineering/bus130_charging_source_review.csv';bus130.to_csv(bpath,index=False,lineterminator='\n')
    parent_path=ROOT/'output/nygrid_2025_dover_parameters/network/x_nominal.mat'
    parent_bus=loadmat(parent_path,simplify_cells=True)['full_case']['bus']
    source_bs=float(parent_bus[parent_bus[:,0]==130,5][0])
    predicted_bs=source_bs-float(.75*bus130.loc[bus130.old_length_only_reactor_eligible,'nominal_charging_mvar'].sum()/2)
    report=dict(passed=True,status='evidence_classification_and_independent_capacity_prior_review;implementation_validation_separate',
        created_utc=datetime.now(timezone.utc).isoformat(),voltage_changing_equivalents=103,
        unresolved_composite_count=65,station_transformer_compatible_count=38,
        source_station_GIS_correlated_transformer_compatible_count=17,
        composite_branch_rows=composite.branch_row.tolist(),
        composite_low_voltage_reflection_rows=composite.loc[composite.generator_voltage_side_reflected_from_transmission_MVA,'branch_row'].tolist(),
        key_corrections=composite.loc[composite.branch_row.isin([173,186]),['branch_row','from_name','to_name',
            'prior_own_X_selected_equipment_mva','recommended_composite_nominal_mva_proxy','recommended_composite_from_A','recommended_composite_to_A']].to_dict('records'),
        source_basis='station labels plus positive inherited charging; parent coordinates explicitly approximate and not a stand-alone type certificate',
        limits_basis='existing finite voltage-class terminal current assumptions; independent of total X, operating flow and OPF residual',
        claim_boundary='Every explicitly modeled OH corridor has a thermal realization. Unknown line interiors inside composite equivalents remain undecomposed and are not certified by this model.',
        bus130=dict(source_BS_mvar=source_bs,predicted_BS_under_existing_length_rule_mvar=predicted_bs,incident_OH_rows=[180,181,182,183],
            all_below_old_120mile_reactor_selector=True,nominal_total_line_charging_mvar=float(bus130.nominal_charging_mvar.sum()),
            lumped_nominal_endpoint_half_charging_mvar=float(bus130.nominal_charging_mvar.sum()/2),
            finding='The declared length-based reactor selector excludes these shorter 500kV corridors. This is a policy boundary, not a source-shunt sign error or proof that further compensation is required.',
            additional_EHV_charging_selector_applied=False,
            no_reactor_value_fitted_to_failure_residual=True),
        dependencies=[record(p) for p in [source,geo_source,default_path,parent_path,Path(__file__)]],
        outputs=[record(path),record(bpath)])
    (BASE/'engineering/voltage_changing_classification_review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['dependencies','outputs','composite_branch_rows']},indent=2))


if __name__=='__main__':main()
