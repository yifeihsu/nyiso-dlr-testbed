"""Extract archived Sand Bar PTID325270 actual flows without fitting a gate.

The Sand Bar meter is not silently equated to the Plattsburgh PV20 boundary
meter: South Hero net load/injection, intervening losses and bypass state remain
explicit unresolved terms. This supplies a reproducible prescribed-transfer
proxy for engineering scenarios, not a physically certified Moses operator.
"""
from datetime import datetime, timezone
import importlib.util
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_moses_repair/boundary'


def sha(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    helper=ROOT/'scripts/nygrid_2025_moses_source_diagnosis/boundary/audit_sources.py'
    spec=importlib.util.spec_from_file_location('checked_native_source_integration',helper)
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    native.PTIDS=[325270]
    baseline_path=ROOT/'output/nygrid_2025_moses_source_diagnosis/balance_hourly.csv'
    baseline=pd.read_csv(native.read(baseline_path),usecols=['hour_index','timestamp_utc','qualified'])
    axis=pd.DatetimeIndex(pd.to_datetime(baseline.timestamp_utc,utc=True))
    assert len(axis)==8760 and baseline.qualified.sum()==8651
    native.read(helper)
    pdf=ROOT/'output/nygrid_2025_par_controls/sources/direction/NYISO_ParFlowDiagrams27.pdf'
    native.read(pdf)
    raw,timing=native.native_par()
    assert raw.point_id.eq(325270).all()
    hourly,meta=native.aggregate_par(raw,axis)
    result=baseline.copy()
    result['PV20_SandBar_import_to_NY_proxy_MW']=hourly.PAR_325270_forward_hold_MW.to_numpy()
    result['PV20_SandBar_export_from_NY_proxy_MW']=-result.PV20_SandBar_import_to_NY_proxy_MW
    for method in ['backward_hold','linear','arithmetic_mean']:
        result[f'PV20_{method}_import_to_NY_proxy_MW']=hourly[f'PAR_325270_{method}_MW'].to_numpy()
    for field in ['coverage_seconds','max_gap_seconds','native_count']:
        result['PV20_'+field]=hourly[f'PAR_325270_{field}'].to_numpy()
    result['PV20_coverage_qualified']=np.isfinite(result.PV20_SandBar_import_to_NY_proxy_MW)
    result['current_and_PV20_qualified']=result.qualified & result.PV20_coverage_qualified
    # Direction is observed in the currently archived official diagram. This
    # page has no explicit historical effective date; applicability to2025 is a
    # declared engineering assumption pending a dated direction source.
    result['P34_current_diagram_to_import_positive_multiplier']=1
    result['historical_2025_sign_effective_date_independently_verified']=False
    result['Plattsburgh_meter_equivalence_verified']=False
    result.to_csv(OUT/'PV20_hourly_source.csv',index=False,lineterminator='\n')
    raw.to_csv(OUT/'PV20_P34_native_raw.csv.gz',index=False,lineterminator='\n',compression={'method':'gzip','mtime':0})
    timing.to_csv(OUT/'PV20_native_timing_receipts.csv',index=False,lineterminator='\n')
    stats=[]
    for label,mask in [('all_PV20_covered',result.PV20_coverage_qualified),('fixed8651_if_available',result.current_and_PV20_qualified)]:
        x=result.loc[mask,'PV20_SandBar_import_to_NY_proxy_MW'].to_numpy()
        stats.append(dict(cohort=label,**native.summary(x)))
    pd.DataFrame(stats).to_csv(OUT/'PV20_source_statistics.csv',index=False,lineterminator='\n')
    assert all(sha(ROOT/p)==h for p,h in native.DEPENDENCIES.items())
    receipt=dict(status='native_actual_PTID325270_extracted_with_explicit_meter_and_historical_sign_assumptions',
        created_utc=datetime.now(timezone.utc).isoformat(),physical_hours=8760,current_qualified_hours=8651,
        source_records=len(raw),coverage_qualified_hours=int(result.PV20_coverage_qualified.sum()),
        current_and_PV20_qualified_hours=int(result.current_and_PV20_qualified.sum()),
        current_qualified_hours_missing_PV20=int((result.qualified & ~result.PV20_coverage_qualified).sum()),
        native_metadata=meta,source_statistics=stats,
        observed_PTID=325270,observed_device='Sand Bar PAR PS01',
        current_direction_source='Official ParFlowDiagrams27 page8 cyanplus arrow from SandBarISO-NE toward SouthHeroISO-NE and PlattsburghNYISO; page26legend',
        positive_direction='SandBar toward Plattsburgh, import-positive to NewYork in the engineering proxy',
        historical_2025_direction_effective_date_verified=False,
        physical_PV20_boundary_meter='Plattsburgh, per official2025AppendixE D-to-N table',
        intervening_station='South Hero115kV ISO-NE',
        exact_physical_identity='PV20_Platt_import = P34_SandBar_toward_Platt - SouthHero_net_load - intervening_real_losses + bypass_or_other_unmetered_parallel_transfer',
        historical_direction_and_meter_equivalence_assumptions_required=True,
        required_global_balance_rule='PV20 is a component of the existing NYIS-ISNE physical aggregate. Reroute this share intoZoneD and subtract it from the remainingISO-NE exchange target; never add it on top of the unchanged total.',
        physical_circuit_ID_to_model_AC_branch_mapping_claimed=False,
        model_inputs_changed=False,internal_P32_observations_used_to_select_values=False,
        aggregation='Exactforwardhold overlap; reject any nativegapover600s; noimputation; keepallphysicalUTChours; alternateconventionsretained',
        source_manifest=[dict(path=p,sha256=h)for p,h in native.DEPENDENCIES.items()],script_sha256=sha(Path(__file__)))
    (OUT/'PV20_source_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:receipt[k]for k in ['status','source_records','coverage_qualified_hours','current_and_PV20_qualified_hours','current_qualified_hours_missing_PV20','source_statistics']},indent=2))


if __name__=='__main__':main()
