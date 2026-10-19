"""Independently recalculate factorial headline scores and source preservation."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_postrepair_diagnosis'


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    guard=json.loads((OUT/'source_guard.json').read_text())
    for r in guard['files']:assert sha(ROOT/r['path'])==r['sha256'],r['path']
    p=OUT/'ablations';a=np.load(p/'factorial_arrays.npz');base=np.load(OUT/'interface_evidence.npz')
    q=a['common_qualified'];assert q.sum()==8651 and np.array_equal(q,a['source_qualified'])
    assert np.array_equal(a['B_legacy_signed_literal_from'],base['current_baseline_legacy_signed_literal_from'],equal_nan=True)
    assert np.array_equal(a['GP_legacy_signed_literal_from'],base['candidate_legacy_signed_literal_from'],equal_nan=True)
    scores=pd.read_csv(p/'factorial_metrics.csv');effects=pd.read_csv(p/'factorial_attribution.csv')
    scores=scores.loc[(scores.period=='annual')&(scores.convention=='legacy_signed_literal_from')]
    effects=effects.loc[(effects.period=='annual')&(effects.convention=='legacy_signed_literal_from')]
    computed={};maximum=0.;checks=0
    for j,name in enumerate(a['interface_names']):
        obs=a['observed'][q,j];computed[name]={}
        for scenario in ['B','G','P','GP']:
            err=a[scenario+'_legacy_signed_literal_from'][q,j]-obs
            values=dict(mae_public_MW=abs(err).mean(),bias_public_MW=err.mean(),rmse_public_MW=np.sqrt(np.mean(err**2)),
                        wape_percent=100*abs(err).sum()/abs(obs).sum())
            computed[name][scenario]=values
            row=scores.loc[(scores.scenario==scenario)&(scores.interface==name)].iloc[0];assert row.hours==8651
            for field,value in values.items():maximum=max(maximum,abs(value-row[field]));checks+=1
        for field in computed[name]['B']:
            b,g,pv,gp=[computed[name][s][field] for s in ['B','G','P','GP']]
            expected=dict(combined_change=gp-b,G_Shapley_effect=.5*((g-b)+(gp-pv)),
                          P_Shapley_effect=.5*((pv-b)+(gp-g)),interaction=gp-g-pv+b)
            row=effects.loc[(effects.interface==name)&(effects.metric==field)].iloc[0]
            for key,value in expected.items():maximum=max(maximum,abs(value-row[key]));checks+=1
    assert maximum<1e-9
    wind=json.loads((OUT/'generation/D_wind_source_energy_review.json').read_text())
    lower=wind['current_qualified_total_MWh']-wind['EIA_2025_total_MWh'];assert lower>0
    report=dict(passed=True,checked_utc=datetime.now(timezone.utc).isoformat(),
                immutable_sources_and_current_delivery_files_checked=len(guard['files']),
                all_four_qualified_hours=int(q.sum()),independent_metric_and_effect_checks=checks,
                maximum_metric_discrepancy=float(maximum),
                D_wind_qualified_energy_exceeds_entire_EIA_year_MWh=lower,
                minimum_D_wind_mean_excess_on_qualified_hours_MW=lower/int(q.sum()),
                implied_Moses_bias_after_minimum_wind_energy_correction_holding_other_terms_MW=
                    computed['MOSES SOUTH']['GP']['bias_public_MW']-lower/int(q.sum()),
                full_year_wind_point_estimate_is_not_used_for_robust_bound=True,
                wind_lower_bound_requires_current_nonnegative_excluded_generation_bounds=True,
                EIA_net_generation_can_be_negative_when_station_service_exceeds_gross=True,
                excluded_hour_mean_net_generation_required_to_erase_excess_MW=-lower/109,
                individual_input_effects_are_within_model_not_real_world_causal_estimates=True,
                current_model_map_handoff_and_pointer_unchanged=True)
    (OUT/'independent_summary_review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
