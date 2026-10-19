"""Freeze the diagnostic frame and numerical sources without changing inputs."""
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_remaining_errors'
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rec(path):return {'path':path.relative_to(ROOT).as_posix(),'bytes':path.stat().st_size,'sha256':sha(path)}
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    critical=[]
    for folder,pattern in [('scripts/nygrid_2025_ac_loss_revision/core','*.m'),
        ('scripts/nygrid_2025_latest_handoff/runtime','*.m'),
        ('output/nygrid_2025_latest_handoff/model','*'),
        ('output/nygrid_2025_ac_loss_revision/comparison/combined','*'),
        ('output/nygrid_2025_acpf_profile_audit/alignment','interface_operator*')]:
        critical.extend(p for p in (ROOT/folder).rglob(pattern) if p.is_file())
    critical.extend([ROOT/'System Matpower Format/run_nygrid_2025_loss_consistent_acpf.m',
        ROOT/'output/nygrid_2025_western_audit/replay/dated_combined.mat'])
    dirty=subprocess.check_output(['git','diff','--name-only','-z','--','scripts/nygrid_2025_latest_map','output/nygrid_2025_latest_map']).decode().split('\0')
    dirty+=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z','--','scripts/nygrid_2025_latest_map','output/nygrid_2025_latest_map']).decode().split('\0')
    dirty_paths=[ROOT/n for n in sorted(set(dirty)-{''}) if (ROOT/n).is_file()]
    guard={'created_utc':datetime.now(timezone.utc).isoformat(),
        'branch':subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
        'HEAD_at_start':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'critical_numerical_sources':[rec(p) for p in sorted(set(critical))],
        'unrelated_map_working_changes_at_start':[rec(p) for p in dirty_paths],
        'unrelated_map_changes_are_not_diagnostic_inputs':True}
    target=OUT/'source_guard.json'
    if target.exists():
        old=json.loads(target.read_text(encoding='utf-8'))
        assert old['critical_numerical_sources']==guard['critical_numerical_sources'],'A frozen numerical source changed.'
    else:target.write_text(json.dumps(guard,indent=2)+'\n',encoding='utf-8')
    contract={'question':'Identify and quantify the strongest supported explanations for remaining current-model interface-flow errors.',
        'primary_source':'output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_arrays.npz',
        'primary_prediction':'revised_legacy_signed_literal_from','primary_cohort':'revised_qualified',
        'hour_slots':8760,'source_qualified_hours':8651,'primary_qualified_hours':8170,
        'prediction_and_observation_units':'public_scale_MW_in_comparison_NPZ; do not divide a second time by gamma',
        'physical_P32_meter_membership_certified':False,
        'numeric_as_MW_P32_header_interpretation_independently_certified':False,
        'ranking':['annual_MAE_public_MW','annual_WAPE_percent','signed_bias_and_temporal_shape'],
        'hypothesis_families':['source_input_timing_and_spatial_allocation','complete_cut_accounting_and_external_landing',
            'terminal_convention_and_loss_corrections','current_AC_versus_source_corrected_DC',
            'physical_impedance_reactive_and_operating_assumptions','measurement_scope_or_clock_mismatch'],
        'controlled_probe_policy':'Only small versioned diagnostics justified by saved-data findings; no arbitrary fitting or default-model promotion.',
        'failed_solutions_are_not_predictions':True,'source_masks_preserved':True,
        'new_annual_PF_required':False,'old_files_and_unrelated_work_preserved':True,
        'claim_policy':'Separate exact arithmetic, controlled model responses, source-supported causes, plausible hypotheses, and unresolved physical attribution.'}
    contract_path=OUT/'investigation_contract.json'
    if not contract_path.exists():contract_path.write_text(json.dumps(contract,indent=2)+'\n',encoding='utf-8')
    else:assert json.loads(contract_path.read_text(encoding='utf-8'))==contract
    print(json.dumps({'passed':True,'critical_sources':len(guard['critical_numerical_sources']),
        'unrelated_map_working_files':len(guard['unrelated_map_working_changes_at_start']),
        'baseline_HEAD':guard['HEAD_at_start']}))
if __name__=='__main__':main()
