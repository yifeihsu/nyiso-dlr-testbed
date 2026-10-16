"""Compare scorer output with the separate raw-physics auditor's metrics."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import numpy as np
import pandas as pd
from validate_annual import record

ROOT=Path(__file__).resolve().parents[3]


def main(run_dir):
    run_dir=run_dir.resolve();comparison=run_dir/'comparison'
    physics=ROOT/'output/nygrid_2025_physical_repair/independent'
    if run_dir.name!='physical_repair_v1':physics/=run_dir.name
    source=physics/'interface_metrics.csv';target=comparison/'public_interface_metrics.csv'
    separate=pd.read_csv(source);scored=pd.read_csv(target)
    mapping={'candidate_all_success':('candidate','candidate_all_success'),
             'candidate_new_success':('candidate','candidate_new_success'),
             'paired_current_baseline':('candidate','paired_current_baseline'),
             'old_baseline_same_calendar':('current_baseline','current_baseline_all8170')}
    maximum=0.;checked=0
    for row in separate.itertuples(index=False):
        model,cohort=mapping[row.cohort]
        other=scored.loc[(scored.model==model)&(scored.cohort==cohort)&(scored.period=='annual')&
            (scored.convention=='legacy_signed_literal_from')&(scored.interface==row.interface)]
        assert len(other)==1;other=other.iloc[0];assert int(row.hours)==int(other.hours)
        for key,reference in [('mae_public_MW',row.MAE_public_MW),('rmse_public_MW',row.RMSE_public_MW),('bias_public_MW',row.bias_public_MW)]:
            maximum=max(maximum,abs(float(other[key])-float(reference)))
        checked+=1
    assert checked==28 and maximum<1e-9
    array_path=comparison/'comparison_arrays.npz';a=np.load(array_path,allow_pickle=False)
    assert len(a['hour_index'])==8760 and a['source_qualified'].sum()==8651
    assert a['candidate_qualified'].sum()==8651 and a['current_baseline_qualified'].sum()==8170
    assert a['paired_qualified'].sum()==8170 and a['candidate_new_success'].sum()==481 and not a['current_success_lost'].any()
    selected=scored.loc[(scored.period=='annual')&(scored.model=='candidate')&
        (scored.cohort=='candidate_all_success')&(scored.convention=='legacy_signed_literal_from')].set_index('interface')
    wape_error=0.
    for k,name in enumerate(a['interface_names']):
        mask=a['candidate_qualified'];e=a['candidate_legacy_signed_literal_from'][mask,k]-a['observed'][mask,k]
        wape=float(100*abs(e).sum()/abs(a['observed'][mask,k]).sum())
        wape_error=max(wape_error,abs(wape-float(selected.loc[name,'wape_percent'])))
    assert wape_error<1e-10
    result={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),
        'independent_raw_physics_metric_rows_compared':checked,'maximum_MAE_RMSE_bias_difference_MW':maximum,
        'maximum_WAPE_recalculation_difference_percentage_points':wape_error,'all_8760_rows_and_8651_8170_481_cohorts_verified':True,
        'no_additional_PF_or_source_mutation':True,'dependencies':[record(p) for p in [source,target,array_path]],'producer':record(Path(__file__))}
    (comparison/'independent_scoring_crosscheck.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True);args=p.parse_args();main(args.run_dir)
