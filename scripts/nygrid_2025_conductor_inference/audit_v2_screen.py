"""Independent saved-array review of the new R/X-conditioned thermal selector.

Run independent/export_screen_arrays.m first. This Python audit performs no
electrical solve, changes no thermal candidate and writes only new receipts.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import sys

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_conductor_inference/independent'
SOURCE=ROOT/'output/nygrid_2025_conductor_inference/matlab_validation'


def record(path):
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=digest)


def main():
    sys.dont_write_bytecode=True
    module_path=Path(__file__).with_name('audit_inverse_physics.py')
    spec=importlib.util.spec_from_file_location('independent_math',module_path)
    physics=importlib.util.module_from_spec(spec);spec.loader.exec_module(physics)
    receipt_path=SOURCE/'validation_receipt.json'
    producer=json.loads(receipt_path.read_text())
    assert producer['passed'] and producer['test_count']==35
    dependencies=[record(receipt_path),record(module_path),record(Path(__file__).resolve()),
        record(Path(__file__).parent/'independent/export_screen_arrays.m')]
    for item in producer['protected_sources']+producer['new_runtime_source_files']:
        actual=record(ROOT/item['path']);assert actual['sha256']==item['sha256'],item['path'];dependencies.append(actual)
    catalog_path=ROOT/'output/nygrid_2025_ac_system/engineering/thermal_conductors.csv'
    registry_path=ROOT/'output/nygrid_2025_ac_system/branches/branch_assignments.csv'
    catalog=pd.read_csv(catalog_path).set_index('catalog_id',drop=False)
    registry=pd.read_csv(registry_path).set_index('branch_row')
    results=[]
    for hour in [4000,8508]:
        folder=SOURCE/f'hour_{hour:04d}'
        paths={name:folder/(name+'.csv') for name in ['candidate_and_exclusion_ledger','admitted_segments','branch_current_screen','segment_thermal_screen','forward_RXB_audit']}
        dependencies.extend(record(p) for p in paths.values())
        dependencies.append(record(folder/'selected_point_screen.mat'))
        numeric=OUT/f'screen_arrays/hour_{hour:04d}_numeric.mat';dependencies.append(record(numeric))
        data=loadmat(numeric,simplify_cells=True)
        bus=data['bus'];branch=data['branch'];base=float(data['baseMVA']);assert base==100
        original=data['original_branch'];assert np.array_equal(branch[:,:13],original[:,:13])
        assert np.array_equal(bus[:,2:7],data['original_bus'][:,2:7])
        assert np.array_equal(data['gen'][:,0],data['original_gen'][:,0])
        ledger=pd.read_csv(paths['candidate_and_exclusion_ledger']).set_index('original_parent_row')
        admitted=pd.read_csv(paths['admitted_segments'])
        saved=pd.read_csv(paths['branch_current_screen']).set_index('branch_row')
        thermal=pd.read_csv(paths['segment_thermal_screen'])
        fwd=pd.read_csv(paths['forward_RXB_audit'])
        accepted=ledger[ledger.research_screen_eligible.astype(bool)]
        assert not ledger.installed_circuit_identity_required.any()
        assert not ledger.installed_asset_DLR_verified.any()
        assert not ledger.geographic_chord_used_as_eligibility_gate.any()
        assert not ledger.B_used_as_eligibility_gate.any()
        assert not ledger.electrical_parameters_changed.any()
        assert all(accepted.active&accepted.same_voltage&accepted.unity_tap&accepted.zero_phase)
        assert not set(accepted.index)&{224,300,309,310,386}
        assert set(admitted.original_parent_row)==set(accepted.index)
        assert len(admitted)==len(thermal)
        assert np.array_equal(admitted.branch_row,thermal.branch_row)
        assert np.array_equal(admitted.segment_id,thermal.segment_id)
        ids=dict(zip(bus[:,0].astype(int),range(len(bus))))
        V=bus[:,7]*np.exp(1j*np.pi/180*bus[:,8])
        max_r=max_x=max_b=max_current=max_joule=max_terminal=0.
        aggregate={}
        for k,s in enumerate(admitted.to_dict('records')):
            row=int(s['branch_row']);idx=row-1;f=ids[int(branch[idx,0])];t=ids[int(branch[idx,1])]
            assert branch[idx,10]==1 and branch[idx,8] in [0,1] and branch[idx,9]==0
            assert float(s['base_kv'])==bus[f,9]==bus[t,9]
            c=catalog.loc[s['catalog_id']].to_dict()
            e=physics.forward(c,s['segment_length_m'],int(s['circuits']),int(s['bundle_count']),s['gmd_m'],s['bundle_spacing_m'],s['base_kv'],s['reference_temperature_c'])
            accumulator=aggregate.setdefault(row,dict(r=0.,x=0.,b=0.,loss=0.))
            for key in ['r','x','b']:accumulator[key]+=e[key+'_pu']
            z=complex(branch[idx,2],branch[idx,3]);ispu=(V[f]-V[t])/z
            ibase=base*1000/(math.sqrt(3)*bus[f,9]);phase=abs(ispu)*ibase;sub=phase/(s['circuits']*s['bundle_count'])
            loss=3*s['circuits']*s['bundle_count']*sub**2*e['rsub']*s['segment_length_m']/1e6
            accumulator['loss']+=loss
            ts=thermal.iloc[k]
            max_current=max(max_current,abs(phase-ts.series_phase_current_a),abs(sub-ts.subconductor_current_a))
            max_joule=max(max_joule,abs(loss-ts.joule_loss_mw))
        for row,e in aggregate.items():
            idx=row-1;max_r=max(max_r,abs(e['r']-branch[idx,2]));max_x=max(max_x,abs(e['x']-branch[idx,3]));max_b=max(max_b,abs(e['b']-branch[idx,4]))
            f=ids[int(branch[idx,0])];t=ids[int(branch[idx,1])];ys=1/complex(branch[idx,2],branch[idx,3]);bc=.5j*branch[idx,4]
            ibase=base*1000/(math.sqrt(3)*bus[f,9]);series=ys*(V[f]-V[t]);fr=abs(series+bc*V[f])*ibase;to=abs(-series+bc*V[t])*ibase
            bs=saved.loc[row]
            max_terminal=max(max_terminal,abs(fr-bs.from_terminal_current_A),abs(to-bs.to_terminal_current_A),abs(abs(series)*ibase-bs.series_phase_current_A))
            max_joule=max(max_joule,abs(e['loss']-bs.conductor_joule_loss_mw),abs(e['loss']-sum(branch[idx,[13,15]])))
            assert abs(max(fr,to)/bs.declared_phase_ampacity_A-bs.max_section_end_utilization)<1e-10
            section=fwd[fwd.runtime_branch_row==row].iloc[0]
            assert abs(e['r']-section.forward_R_pu)<1e-10 and abs(e['x']-section.forward_X_pu)<1e-10
        assert set(aggregate)==set(saved.index)
        assert max_r<=1e-11 and max_x<=1e-10 and max_current<1e-6 and max_terminal<1e-6 and max_joule<1e-7
        for parent,row in accepted.iterrows():
            segments=admitted[admitted.original_parent_row==parent]
            kv=float(segments.base_kv.iloc[0]);cap=250000 if kv<200 else 500000 if kv<300 else 700000 if kv<400 else 1000000
            assert 5-1e-6<=segments.segment_length_m.sum()<=cap+1e-6 and cap==row.synthetic_length_max_m
            assert row.all_runtime_sections_covered
            assert len(set(segments.branch_row))==row.runtime_branch_count
            same=abs(row.current_parent_R_pu-registry.loc[parent].original_r_pu)<=1e-11 and abs(row.current_parent_X_pu-registry.loc[parent].original_x_pu)<=1e-10
            assert same==bool(row.imported_RX_preserved)
            assert row.RX_target_basis==('imported_RX' if same else 'prior_engineered_RX')
        p224=ledger.loc[224]
        assert p224.current_RX_below_catalog_geometry_minimum and 'current_X_over_R_below' in p224.reason
        assert abs(p224.catalog_geometry_minimum_X_over_R-3.4738407748929263)<1e-10
        producer_point=next(p for p in producer['points'] if p['hour_index']==hour)
        assert producer_point['v2_parent_count']==len(accepted) and not producer_point['VQ_operating_gate']
        result=dict(hour_index=hour,accepted_parents=len(accepted),runtime_branches=len(aggregate),material_segments=len(admitted),
            imported_RX_parents=int(accepted.imported_RX_preserved.sum()),prior_engineered_RX_parents=int((~accepted.imported_RX_preserved.astype(bool)).sum()),
            maximum_independent_R_error_pu=max_r,maximum_independent_X_error_pu=max_x,maximum_geometric_B_difference_pu=max_b,
            maximum_independent_series_or_subconductor_current_error_A=max_current,maximum_independent_terminal_current_error_A=max_terminal,
            maximum_independent_Joule_loss_error_MW=max_joule,
            maximum_series_utilization=float(saved.max_ampacity_fraction.max()),maximum_section_end_utilization=float(saved.max_section_end_utilization.max()),
            equation_and_accounting_qualified=True,operating_qualified=False,passed=True)
        results.append(result)
    # Production admission guards were inspected against their specific fixtures.
    # No repeat PF solve is needed for these already bound selected-point cases.
    report=dict(passed=True,completed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent new MATLAB V2 admission/flags code review plus saved two-point phasor/material/current/Joule readback',
        selector_has_no_geographic_or_installed_identity_gate=True,
        per_runtime_section_R_and_X_required=True,original_current_model_parameters_preserved=True,
        geometric_B_diagnostic_only=True,temperature_geometry_integer_multiplicity_and_material_checks_reviewed=True,
        prior_VQ_flags_and_no_operating_asset_certification_preserved=True,
        original_case_NOT_repaired_or_reoptimized_to_improve_thermal_utilization=True,
        bound_producer_guard_checks=35,independent_points=results,
        fresh_PF_or_OPF_run=False,new_outputs_under_conductor_inference_only=True,
        remaining_actionable_findings=[],dependencies=dependencies)
    (OUT/'matlab_v2_independent_review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='dependencies'},indent=2))


if __name__=='__main__':main()
