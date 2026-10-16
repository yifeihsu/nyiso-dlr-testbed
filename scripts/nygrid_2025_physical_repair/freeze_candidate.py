"""Seal the tested three-parent repair before the annual replay."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_physical_repair'
def rec(p):
    with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':digest}
def main():
    checks=[OUT/'validation/targeted_candidate_receipt.json',OUT/'physics/compensation_design_review.json',OUT/'physics/independent_candidate_review.json']
    for p in checks:assert json.loads(p.read_text(encoding='utf-8'))['passed'],p
    files=sorted((ROOT/'scripts/nygrid_2025_physical_repair/core').glob('*.m'))
    files+=[ROOT/'scripts/nygrid_2025_physical_repair/physics/nyrepair_apply_185195.m',OUT/'physics/parent41_parameters.json']
    files+=checks
    source=ROOT/'output/nygrid_2025_latest_handoff/model'
    base=[source/x for x in ['latest_model.mat','profiles_h0001_4380.mat','profiles_h4381_8760.mat','model_receipt.json']]
    r={'schema_version':1,'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),
       'baseline_HEAD':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
       'model_revision':'physical_repair_41_185_195_20261015','apply_function':'nyrepair_apply_case',
       'parent41':'ImportedR/X restored using existing rank1 synthetic conductor; geometricB and matching thermal metadata; existing aggregate apparatus bounds retained.',
       'parents185195':'Existing75percent nominal compensation distributed proportional to section-local charging; total rating, conductorRXB, PV setpoints and V limits retained.',
       'parameter_selection_uses_interface_observations':False,'all_hourly_source_arrays_and_controls_preserved':True,
       'same_bus_branch_generator_axes':True,'targeted_preannual_checks_passed':True,'annual_validation_complete':False,
       'installed_asset_identity_claimed':False,'whole_system_operating_qualification_claimed':False,
       'candidate_files':[rec(p) for p in files],'baseline_model_files':[rec(p) for p in base]}
    target=OUT/'candidate_receipt.json'
    if target.exists():
        old=json.loads(target.read_text());a=old.copy();b=r.copy();a.pop('created_utc');b.pop('created_utc');assert a==b,'Frozen candidate changed.'
    else:target.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'candidate_sha256':rec(target)['sha256'],'candidate_files':len(files),'annual_validation_complete':False}))
if __name__=='__main__':main()
