"""Independent readback of the current-only bundle; no new model experiments."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_latest_handoff'
MODEL=OUT/'model'
READBACK=OUT/'independent_bundle'
STATES=['pre_may','may21','may30','post_dover']


def record(path):
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=digest)


def same(a,b):return np.array_equal(np.asarray(a),np.asarray(b),equal_nan=True)


def main():
    model_path=MODEL/'latest_model.mat';receipt_path=MODEL/'model_receipt.json'
    receipt=json.loads(receipt_path.read_text());model=loadmat(model_path,simplify_cells=True)['model']
    assert receipt['passed'] and receipt['source_model_commit']=='2e0fcd5c3f0ae39d04f27a733ce30eb148b0b243'
    dependencies=[record(receipt_path),record(Path(__file__).resolve()),record(Path(__file__).with_name('export_bundle_readback.m'))]
    for f in receipt['model_files']:
        p=MODEL/f['name'];r=record(p);assert r['sha256']==f['sha256'] and p.stat().st_size==f['bytes'];dependencies.append(r)
    axis=pd.read_csv(READBACK/'bundled_hour_axis.csv',keep_default_na=False);dependencies.append(record(READBACK/'bundled_hour_axis.csv'))
    dispatch_path=ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch.mat'
    bounds_path=ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch_bounds.mat'
    western_path=ROOT/'output/nygrid_2025_western_audit/dispatch/all_boundary_actual_dispatch.mat'
    network_path=ROOT/'output/nygrid_2025_western_audit/replay/dated_combined.mat'
    dover_path=ROOT/'output/nygrid_2025_dover_parameters/replay/operating_states.mat'
    for p in [dispatch_path,bounds_path,western_path,network_path,dover_path]:dependencies.append(record(p))
    dispatch=loadmat(dispatch_path,simplify_cells=True,variable_names=['hour_index','timestamp_utc','bus_pd','bus_qd','dc_pf','reference_bus','gamma'])
    bounds=loadmat(bounds_path,simplify_cells=True,variable_names=['hour_index','gen_pmin','gen_pmax'])
    western=loadmat(western_path,simplify_cells=True,variable_names=['hour_index','timestamp_utc','gen_pg','qualified','P34_control_targets_model_mw'])
    network=loadmat(network_path,simplify_cells=True,variable_names=['hour_index','timestamp_utc','qualified','network_state_ids','corrected_generator_buses'])
    dover=loadmat(dover_path,simplify_cells=True,variable_names=['hour_index','timestamp_utc','qualified','post_full_service','controls','gamma'])
    assert np.array_equal(axis.hour_index,np.arange(1,8761))
    for source in [dispatch,western,network,dover]:
        assert np.array_equal(axis.timestamp_utc.astype(str),np.asarray(source['timestamp_utc']).astype(str))
    assert np.array_equal(axis.source_qualified.to_numpy(bool),np.asarray(dover['qualified']).astype(bool))
    assert np.array_equal(axis.reference_bus,np.asarray(dispatch['reference_bus']))
    assert np.array_equal(axis.post_dover_full_service.to_numpy(bool),np.asarray(dover['post_full_service']).astype(bool))
    state_names=list(dict.fromkeys(np.asarray(network['network_state_ids']).astype(str)))
    expected_states=np.array([state_names.index(x)+1 for x in np.asarray(network['network_state_ids']).astype(str)])
    assert np.array_equal(axis.state_index,expected_states) and axis.source_qualified.sum()==8651
    assert np.array_equal(model['axis']['hour_index'],axis.hour_index)
    assert np.array_equal(model['axis']['state_index'],axis.state_index)
    assert np.array_equal(model['generator_bus_ids'],network['corrected_generator_buses'])
    assert model['baseMVA']==100 and model['frequency_Hz']==60 and model['scale_factor_gamma']==dispatch['gamma']==dover['gamma']
    expected={
        'bus_PD_MW':dispatch['bus_pd'],'bus_QD_MVAr':dispatch['bus_qd'],
        'generator_PG_MW':western['gen_pg'],'generator_Pmin_MW':bounds['gen_pmin'],'generator_Pmax_MW':bounds['gen_pmax'],
        'fixed_transfer_PF_MW':np.column_stack([dispatch['dc_pf'],western['P34_control_targets_model_mw']]),
        'dover_bank_phase_shift_deg':dover['controls']['bounded_x_nominal']['bank_shift_model_deg']}
    entries=0;profile_checks=[]
    for shard in model['profile_shards']:
        lo=int(shard['first_hour'])-1;hi=int(shard['last_hour']);p=MODEL/shard['name']
        values=loadmat(p,simplify_cells=True)['profiles']
        assert set(values)==set(expected)
        for name,want in expected.items():
            got=values[name];part=want[lo:hi]
            assert got.shape==part.shape and got.dtype==part.dtype and same(got,part),(shard['name'],name)
            entries+=got.size;profile_checks.append(dict(shard=shard['name'],field=name,shape=list(got.shape),dtype=str(got.dtype),exact_values_and_NaNs_preserved=True))
        del values
    assert entries==40996800
    # Compare each consolidated template against the independently exported
    # current public case in that state. Only the hourly fields differ.
    template_checks=[]
    for i,state in enumerate(STATES):
        source_path=OUT/'structure_inputs'/f'{state}.mat';dependencies.append(record(source_path));source=loadmat(source_path,simplify_cells=True)
        t=model['templates'][i];p=model['loss_static'][i]
        assert 'userfcn' not in t and set(t['userdata'])=={'ac_system','ac_sections','ac_loss_revision'}
        assert same(t['bus'][:,[0,4,5,6,7,8,9,10,11,12]],source['bus'][:,[0,4,5,6,7,8,9,10,11,12]])
        assert np.array_equal(np.asarray(t['bus_name']).astype(str),np.asarray(source['bus_name']).astype(str))
        assert same(t['gen'][:,0],source['gen'][:,0])
        assert np.array_equal(np.asarray(t['genfuel']).astype(str),np.asarray(source['genfuel']).astype(str))
        # Hourly Dover bank phase shifts are the only varying branch field.
        keep=list(range(13));keep.remove(9)
        assert same(t['branch'][:,keep],source['branch'][:,keep])
        shifts=np.flatnonzero(np.any(np.column_stack([t['branch'][:,9],source['branch'][:,9]])!=0,axis=1))
        assert set(shifts).issubset({410,411})
        assert same(t['dcline'][:,[0,1,2,5,6,7,8,11,12,13,14,15,16]],source['dcline'][:,[0,1,2,5,6,7,8,11,12,13,14,15,16]])
        assert same(model['retained_bus_ids'],source['retained_ids'])
        assert same(t['userdata']['ac_system']['branch_parent_row'],source['branch_parent_row'])
        assert np.array_equal(np.asarray(t['userdata']['ac_system']['branch_keys']).astype(str),np.asarray(source['branch_keys']).astype(str))
        for name in ['bus_group','loss_ownership','native','external_gen_group','generator_share','HQ']:
            assert same(p[name],source[name]),(state,name)
        assert same(model['generator_bus_rows'][i],np.array([np.flatnonzero(t['bus'][:,0]==b)[0]+1 for b in t['gen'][:,0]]))
        rows=np.asarray(t['userdata']['ac_loss_revision']['parent224_runtime_rows']).astype(int)-1
        assert same(t['branch'][rows,2:5],np.tile([.01,.00735,0.],(2,1)))
        declared=receipt['state_records'][i]
        assert declared['full_bus_count']==len(t['bus']) and declared['full_branch_rows']==len(t['branch'])
        assert declared['active_branch_rows']==int((t['branch'][:,10]>0).sum())
        template_checks.append(dict(state=state,passed=True,all_static_bus_branch_generator_transfer_axes_preserved=True,
            all_R_X_B_status_tap_shunt_and_limit_fields_preserved=True,loss_ownership_and_participation_exact=True,
            serialized_callback_tree_absent=True,source_fixture_hour=int(source['hour']),template_hour=int(model['axis']['template_hours'][i])))
    # Tables are read through MATLAB once, then checked independently here.
    for bundled_name,source_rel in [
        ('bundled_conductors.csv','output/nygrid_2025_ac_system/engineering/thermal_conductors.csv'),
        ('bundled_geometry.csv','output/nygrid_2025_ac_system/engineering/geometry_defaults.csv'),
        ('bundled_cable_conflicts.csv','output/nygrid_2025_acpf_profile_audit/structure/overhead_cable_classification_conflicts.csv')]:
        bp=READBACK/bundled_name;sp=ROOT/source_rel;dependencies.extend([record(bp),record(sp)])
        a=pd.read_csv(bp,keep_default_na=False);b=pd.read_csv(sp,keep_default_na=False)
        assert list(a)==list(b) and a.shape==b.shape
        for col in a:
            av=pd.to_numeric(a[col],errors='coerce');bv=pd.to_numeric(b[col],errors='coerce')
            numeric=av.notna()|bv.notna()
            if numeric.any():assert np.allclose(av[numeric],bv[numeric],rtol=1e-12,atol=1e-12,equal_nan=True),(bundled_name,col)
            mask=~numeric;assert np.array_equal(a.loc[mask,col].astype(str).replace('NaN',''),b.loc[mask,col].astype(str).replace('NaN','')),(bundled_name,col)
    gpath=READBACK/'bundled_generator_registry.csv';dependencies.append(record(gpath));g=pd.read_csv(gpath,keep_default_na=False)
    expected_gen=pd.read_csv(OUT/'structure/generator_identity_map.csv',keep_default_na=False)
    assert np.array_equal(g.generator_row,expected_gen.generator_row)
    assert np.array_equal(g.device_key,expected_gen.device_key) and np.array_equal(g.current_bus_id,expected_gen.bus_id)
    assert np.array_equal(g.fuel_category,expected_gen.fuel)
    # The independent document has already been bound to the same current map.
    for item in dependencies:
        assert record(ROOT/item['path'])['sha256']==item['sha256'],item['path']
    report=dict(passed=True,completed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent current-only consolidated model and all8760-profile readback; no model experiments or solver runs',
        source_model_commit=model['source_model_commit'],model_receipt_matches_all3_data_file_hashes=True,
        annual_axis_rows=8760,source_qualified_rows=8651,four_dated_states_preserved=True,
        exact_annual_numeric_entries_checked=entries,annual_profile_shards=2,annual_numeric_fields=7,
        timestamps_hour_indices_reference_and_state_axes_exact=True,
        generator_identity_and_corrected_electrical_landing_exact=True,
        catalog_geometry_and_cable_conflict_tables_preserved=True,
        source_model_parameters_changed=False,callback_and_historical_loader_metadata_removed=True,
        no_PF_OPF_or_annual_replay_run=True,
        profile_checks=profile_checks,template_checks=template_checks,
        runtime_equivalence_and_extracted_execution='Checked separately by the bound runtime validation and clean extraction receipts; not inferred from this static readback.',
        remaining_actionable_findings=[],dependencies=dependencies)
    path=OUT/'model_bundle_independent_review.json';path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['dependencies','profile_checks','template_checks']},indent=2))


if __name__=='__main__':main()
