"""Freeze replay axes and the current comparison baseline without running PF."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import shutil
import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_physical_repair/annual'


def record(path):
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':digest,'bytes':path.stat().st_size}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    array_path=ROOT/'output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_arrays.npz'
    model_path=ROOT/'output/nygrid_2025_latest_handoff/model/latest_model.mat'
    a=np.load(array_path,allow_pickle=False)
    m=loadmat(model_path,simplify_cells=True,variable_names=['model'])['model']
    assert np.array_equal(a['hour_index'],np.arange(1,8761))
    clock=pd.DatetimeIndex(pd.to_datetime(a['timestamp_utc'],utc=True))
    assert np.array_equal(np.diff(clock.asi8),np.full(8759,3600*10**9))
    model_receipt=json.loads((model_path.parent/'model_receipt.json').read_text())
    assert str(a['timestamp_utc'][0])==model_receipt['first_timestamp_utc']
    assert str(a['timestamp_utc'][-1])==model_receipt['last_timestamp_utc']
    # MATLAB's native string object is not decoded by scipy; the replay driver
    # compares the entire exported clock against this frozen cell-string axis.
    assert np.array_equal(a['source_qualified'],m['axis']['source_qualified'].astype(bool))
    assert a['source_qualified'].sum()==8651 and a['revised_qualified'].sum()==8170
    assert float(a['gamma'])==float(m['scale_factor_gamma'])
    files=[array_path,model_path,model_path.parent/'model_receipt.json',
           model_path.parent/'profiles_h0001_4380.mat',model_path.parent/'profiles_h4381_8760.mat',
           ROOT/'output/nygrid_2025_acpf_profile_audit/alignment/interface_operator_terms.csv']
    snapshot=OUT/'baseline_bundle'
    copy_sources=[(p,snapshot/'model'/p.name) for p in files[1:5]]
    runtime=ROOT/'scripts/nygrid_2025_latest_handoff/runtime'
    copy_sources += [(p,snapshot/'runtime'/p.relative_to(runtime)) for p in sorted(runtime.rglob('*.m'))]
    snapshot_records=[]
    for source,target in copy_sources:
        target.parent.mkdir(parents=True,exist_ok=True)
        source_record=record(source)
        if not target.exists():shutil.copy2(source,target)
        target_record=record(target)
        assert source_record['sha256']==target_record['sha256'],'Existing baseline snapshot differs from the source being frozen.'
        snapshot_records.append({'source':source_record,'snapshot':target_record})
    snapshot_receipt=snapshot/'snapshot_receipt.json'
    snapshot_proof={'passed':True,'files':snapshot_records,'fresh_PF_run':False,
        'purpose':'Executable baseline preserved before any latest-model promotion.'}
    if snapshot_receipt.exists():assert json.loads(snapshot_receipt.read_text())==snapshot_proof
    else:snapshot_receipt.write_text(json.dumps(snapshot_proof,indent=2)+'\n',encoding='utf-8')
    contract={'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),
        'source_HEAD':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
        'all_hour_slots':8760,'source_qualified_hours':8651,'frozen_current_baseline_qualified_hours':8170,
        'gamma':float(a['gamma']),'baseline_prediction':'revised_legacy_signed_literal_from',
        'candidate_apply_function':'nyrepair_apply_case','candidate_axes_and_profiles_must_be_preserved':True,
        'candidate_receipt':'output/nygrid_2025_physical_repair/candidate_receipt.json',
        'candidate_frozen_or_annual_started_by_this_preparation':False,
        'qualification':'Source eligibility AND PF convergence AND AC equation gate AND loss allocation gate AND recovery gate.',
        'operating_qualification':'Separate voltage, finite generator P/Q/assumed-S, fixed transfer Q, declared equipment and current checks; never inferred from equation qualification.',
        'cohorts':['candidate_all_success','paired_current_baseline','candidate_new_success','current_success_lost','current_baseline_all8170'],
        'score_conventions':['legacy_signed_literal_from','oriented_source_side','oriented_target_side'],
        'periods':['annual','each_NY_calendar_month','post_Dover'],
        'failure_policy':'Retain every source-qualified attempt and nonconverged returned iterate; flag invalid predictions. Never impute failed flows.',
        'current_units':'Model amperes use actual voltage and conductor voltage base, never divide by gamma.',
        'P32_physical_meter_membership_certified':False,'P32_numeric_as_MW_header_interpretation_certified':False,
        'baseline_snapshot':record(snapshot_receipt),'source_files':[record(p) for p in files]}
    path=OUT/'replay_contract.json'
    if path.exists():
        old=json.loads(path.read_text());old.pop('created_utc');new=contract.copy();new.pop('created_utc')
        if old!=new:
            assert not list(OUT.glob('*/annual_axes.mat')),'A replay already captured this contract; preserve its scope.'
            assert set(old)==set(new)-{'baseline_snapshot'},'Unexpected change to the pre-replay contract.'
            old['baseline_snapshot']=new['baseline_snapshot'];assert old==new
            path.write_text(json.dumps(contract,indent=2)+'\n',encoding='utf-8')
    else:path.write_text(json.dumps(contract,indent=2)+'\n',encoding='utf-8')
    target=OUT/'frozen_baseline_axes.mat'
    if not target.exists():
        savemat(target,{'hour_index':a['hour_index'],'timestamp_utc':a['timestamp_utc'],
            'source_qualified':a['source_qualified'],'current_baseline_qualified':a['revised_qualified'],
            'gamma':a['gamma'],'interface_names':a['interface_names']},do_compression=True)
    d=loadmat(target,simplify_cells=True)
    for key in ['hour_index','timestamp_utc','source_qualified']:
        assert np.array_equal(d[key],a[key])
    assert np.array_equal(d['current_baseline_qualified'],a['revised_qualified'])
    print(json.dumps({'prepared':True,'PF_started':False,'source_hours':8651,'baseline_hours':8170,'contract':str(path)}))


if __name__=='__main__':main()
