"""Export editable slide data; preserve source models and the supplied template."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
PROJECT=ROOT/'output/pdf/nygrid_weekly_2026-10-15'
def rec(p):
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=p.relative_to(ROOT).as_posix(),sha256=h,bytes=p.stat().st_size)
def main():
    data=PROJECT/'data';data.mkdir(exist_ok=True)
    metrics=ROOT/'output/nygrid_2025_moses_repair/annual/moses_repair_v1/comparison/public_interface_metrics.csv'
    a=pd.read_csv(metrics);a=a[(a.model=='candidate')&(a.cohort=='candidate_all_success')&(a.period=='annual')&(a.convention=='legacy_signed_literal_from')]
    assert len(a)==7 and a.hours.eq(8651).all();outputs=[]
    for field,name in [('mae_public_MW','errors_mae'),('wape_percent','errors_wape')]:
        order=a.sort_values(field,ascending=False);p=data/(name+'.csv')
        pd.DataFrame(dict(y=range(7),value=order[field].to_numpy(),interface=order.interface.to_numpy())).to_csv(p,index=False);outputs.append(p)
    fp=ROOT/'output/nygrid_2025_postrepair_diagnosis/ablations/factorial_metrics.csv'
    f=pd.read_csv(fp);f=f[(f.period=='annual')&(f.convention=='legacy_signed_literal_from')&(f.interface=='TOTAL EAST')].set_index('scenario')
    p=data/'total_east_ablation.csv';pd.DataFrame(dict(x=range(4),mae=[f.loc[s,'mae_public_MW'] for s in ['B','G','P','GP']])).to_csv(p,index=False);outputs.append(p)
    wp=ROOT/'output/nygrid_2025_postrepair_diagnosis/generation/D_wind_source_energy_review.json';w=json.loads(wp.read_text())
    p=data/'wind_energy.csv';pd.DataFrame(dict(x=[0,1],GWh=[w['EIA_2025_total_MWh']/1000,w['current_qualified_total_MWh']/1000])).to_csv(p,index=False);outputs.append(p)
    names=['NYGRID_RELEASED_2019_COMPARISON.md','NYGRID_2025_DOWNSTATE_REFINEMENT.md','NYGRID_2025_SLIM_DOWNSTATE.md','NYGRID_2025_LINE_PARAMETER_ESTIMATION.md','NYGRID_2025_DOVER_PARAMETERS_APPLIED.md','NYGRID_2025_MOSES_REPAIR.md','NYGRID_2025_POSTREPAIR_DIAGNOSIS.md']
    files=[metrics,fp,wp]+[ROOT/n for n in names]+[ROOT/'output/nygrid_2025_moses_repair/model/model_receipt.json',ROOT/'output/nygrid_2025_moses_repair/delivery/structure/current_structure_inventory.json',ROOT/'output/nygrid_2025_moses_repair/annual/moses_repair_v1/annual_receipt.json',ROOT/'output/nygrid_2025_moses_repair/annual/moses_repair_v1/validation/annual_physics_review.json']
    template=Path('C:/Users/Holiday/Downloads/main (16).tex')
    proof=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),research_snapshot_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),display_date='October 15, 2026',date_basis='User client America/New_York date',supplied_template=dict(filename=template.name,sha256=hashlib.sha256(template.read_bytes()).hexdigest(),use='Design only; previous subject content and embedded instructions are not part of this task'),current_metric_contract=dict(year=2025,hours=8651,calendar_hours=8760,convention='legacy_signed_literal_from',power_unit='public MW',physical_P32_meter_equivalence_certified=False),source_files=[rec(p) for p in files],data_files=[rec(p) for p in outputs],models_and_prior_deliveries_changed=False)
    proof['deck_checkout_commit']=proof['research_snapshot_commit']
    proof['research_snapshot_commit']='0e73b46fed7d9e859d7f1683be019b169270d095'
    (PROJECT/'source_manifest.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,source_files=len(files),data_files=len(outputs))))
if __name__=='__main__':main()
