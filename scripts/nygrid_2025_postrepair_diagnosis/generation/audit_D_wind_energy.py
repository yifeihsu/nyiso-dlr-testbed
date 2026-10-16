"""Current ZoneD wind plant energy versus final2025 EIA923; excluded-hour bounds."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,calendar
import numpy as np,pandas as pd,openpyxl
from scipy.io import loadmat
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'output/nygrid_2025_postrepair_diagnosis/generation'
def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def main():
 base=ROOT/'output/nygrid_2025_moses_repair/model';reg=pd.read_csv(base/'model_generator_register.csv');fleet=pd.read_csv(ROOT/'output/nygrid_2025_western_audit/corrected/fleet_register.csv')
 group=reg.loc[reg.role.eq('native')&reg.zone.eq('D')&reg.fuel_category.eq('Wind')];pids=set(group.plant_id.astype(int));assert len(group)==6 and len(pids)==6
 epath=ROOT/'output/nygrid_2025_western_audit/generation/sources/EIA923_Schedules_2_3_4_5_M_12_2025_Final.xlsx'
 assert rec(epath)['sha256']=='95684212d89ac688a355a5c8b51935111247e6f60716eba250464b28d14cfd2c'
 w=openpyxl.load_workbook(epath,read_only=True,data_only=True);s=w['Page 1 Generation and Fuel Data'];header=None;records=[]
 for line,values in enumerate(s.iter_rows(values_only=True),1):
  norm=[' '.join(str(v).split()) if v is not None else '' for v in values]
  if 'Plant Id' in norm:header=norm;continue
  if header is None:continue
  r=dict(zip(header,values));pid=r.get('Plant Id')
  if pid not in pids or r.get('Reported Fuel Type Code')!='WND':continue
  for month in range(1,13):records.append(dict(plant_id=int(pid),plant_name=r['Plant Name'],source_excel_row=line,prime_mover=r['Reported Prime Mover'],respondent_frequency=r['Respondent Frequency'],
   balancing_authority=r['Balancing Authority Code'],month=month,EIA_net_generation_MWh=float(r['Netgen '+calendar.month_name[month]]),EIA_annual_reported_MWh=float(r['Net Generation (Megawatthours)'])))
 w.close();source=pd.DataFrame(records);scheck=source.groupby('plant_id').agg(sum_months=('EIA_net_generation_MWh','sum'),reported=('EIA_annual_reported_MWh','first'));assert np.max(abs(scheck.sum_months-scheck.reported))<1e-6
 assert len(source)==72 and not source.duplicated(['plant_id','month']).any();source.to_csv(OUT/'D_wind_final_EIA923_source_rows.csv',index=False)
 model=loadmat(base/'latest_model.mat',simplify_cells=True)['model'];gamma=float(model['scale_factor_gamma']);q=np.array(model['axis']['source_qualified'],bool)
 clock=pd.read_csv(ROOT/'output/nygrid_2025_moses_repair/generation/full8760_generation_ledger.csv');assert np.array_equal(clock.source_qualified.to_numpy(bool),q)
 time=pd.DatetimeIndex(pd.to_datetime(clock.timestamp_utc,utc=True));months=time.tz_convert('America/New_York').month.to_numpy()
 parts=[loadmat(base/n,simplify_cells=True)['profiles'] for n in ['profiles_h0001_4380.mat','profiles_h4381_8760.mat']]
 rows=group.gen_row.to_numpy(int)-1;pg=np.concatenate([p['generator_PG_MW'] for p in parts])[:,rows]/gamma
 b=np.load(ROOT/'output/nygrid_2025_dispatch/fleet/fleet_bounds.npz');bidx={int(v):i for i,v in enumerate(b['fleet_id'])};pos=np.array([bidx[int(v)] for v in group.fleet_id]);lo=b['pmin_actual_mw'][:,pos];hi=b['pmax_actual_mw'][:,pos]
 prior=loadmat(ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat',simplify_cells=True,variable_names=['prior_pg'])['prior_pg'][:,rows]/gamma
 reference=np.where(np.isfinite(pg),pg,prior);missing=np.flatnonzero(~np.isfinite(reference).all(1))
 for run in np.split(missing,np.flatnonzero(np.diff(missing)>1)+1):
  if not len(run):continue
  l=run[0]-1;r=run[-1]+1
  for h in run:reference[h]=reference[l]+(reference[r]-reference[l])*(h-l)/(r-l)
 assert np.isfinite(reference).all() and np.isfinite(pg[q]).all()
 records=[]
 for j,plant in enumerate(group.plant_id.astype(int)):
  for month in range(1,13):
   ix=months==month;qualified=ix&q;excluded=ix&~q;src=source.loc[source.plant_id.eq(plant)&source.month.eq(month)].iloc[0];e=float(src.EIA_net_generation_MWh)
   qualifiedE=float(pg[qualified,j].sum());lower=qualifiedE+float(lo[excluded,j].sum());upper=qualifiedE+float(hi[excluded,j].sum());latentE=float(reference[excluded,j].sum())
   records.append(dict(plant_id=plant,plant_name=src.plant_name,month=month,EIA_net_generation_MWh=e,respondent_frequency=src.respondent_frequency,
    current_qualified_MWh=qualifiedE,excluded_hours=int(excluded.sum()),qualified_plus_excluded_min_MWh=lower,qualified_plus_excluded_max_MWh=upper,
    EIA_within_excluded_hour_bounds=bool(lower-1e-6<=e<=upper+1e-6),minimum_unexplained_source_difference_MWh=max(lower-e,e-upper,0),
    diagnostic_frozen_prior_excluded_MWh=latentE,diagnostic_full_calendar_MWh=qualifiedE+latentE,diagnostic_full_minus_EIA_MWh=qualifiedE+latentE-e,
    excluded_reference_is_assumed=True,full_calendar_value_is_not_observed=True))
 df=pd.DataFrame(records);df.to_csv(OUT/'D_wind_monthly_EIA_comparison.csv',index=False)
 energy_columns=['EIA_net_generation_MWh','current_qualified_MWh','qualified_plus_excluded_min_MWh','qualified_plus_excluded_max_MWh',
  'diagnostic_frozen_prior_excluded_MWh','diagnostic_full_calendar_MWh','diagnostic_full_minus_EIA_MWh']
 annual=df.groupby(['plant_id','plant_name'],as_index=False).agg(**{c:(c,'sum') for c in energy_columns},
  months_included=('month','nunique'),respondent_frequency=('respondent_frequency','first'),excluded_hours=('excluded_hours','sum'))
 annual['EIA_within_excluded_hour_bounds']=(annual.EIA_net_generation_MWh>=annual.qualified_plus_excluded_min_MWh-1e-6)&(annual.EIA_net_generation_MWh<=annual.qualified_plus_excluded_max_MWh+1e-6)
 annual['minimum_unexplained_source_difference_MWh']=np.maximum.reduce([annual.qualified_plus_excluded_min_MWh-annual.EIA_net_generation_MWh,annual.EIA_net_generation_MWh-annual.qualified_plus_excluded_max_MWh,np.zeros(len(annual))])
 annual['excluded_reference_is_assumed']=True;annual['full_calendar_value_is_not_observed']=True
 annual['relative_difference_pct']=100*annual.diagnostic_full_minus_EIA_MWh/annual.EIA_net_generation_MWh
 annual.to_csv(OUT/'D_wind_annual_EIA_comparison.csv',index=False)
 monthly=df.groupby('month',as_index=False).agg(**{c:(c,'sum') for c in energy_columns},plants_included=('plant_id','nunique'),excluded_hours=('excluded_hours','first'))
 monthly['EIA_within_excluded_hour_bounds']=(monthly.EIA_net_generation_MWh>=monthly.qualified_plus_excluded_min_MWh-1e-6)&(monthly.EIA_net_generation_MWh<=monthly.qualified_plus_excluded_max_MWh+1e-6)
 monthly['minimum_unexplained_source_difference_MWh']=np.maximum.reduce([monthly.qualified_plus_excluded_min_MWh-monthly.EIA_net_generation_MWh,monthly.EIA_net_generation_MWh-monthly.qualified_plus_excluded_max_MWh,np.zeros(len(monthly))])
 monthly['contains_AM_monthly_values_reported_annually']=True;monthly.to_csv(OUT/'D_wind_monthly_totals.csv',index=False)
 report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),plant_count=6,all_monthly_respondents=bool(source.respondent_frequency.eq('M').all()),
  EIA_2025_total_MWh=float(df.EIA_net_generation_MWh.sum()),current_qualified_total_MWh=float(df.current_qualified_MWh.sum()),
  qualified_plus_excluded_min_MWh=float(df.qualified_plus_excluded_min_MWh.sum()),qualified_plus_excluded_max_MWh=float(df.qualified_plus_excluded_max_MWh.sum()),
  diagnostic_full_calendar_total_MWh=float(df.diagnostic_full_calendar_MWh.sum()),diagnostic_full_minus_EIA_MWh=float(df.diagnostic_full_minus_EIA_MWh.sum()),
  robust_qualified_energy_excess_MWh=float(df.current_qualified_MWh.sum()-df.EIA_net_generation_MWh.sum()),robust_qualified_mean_overallocation_lower_bound_public_MW=float((df.current_qualified_MWh.sum()-df.EIA_net_generation_MWh.sum())/q.sum()),
  annual_reported_equals_sum_of_months=True,frequency_sources=['https://www.eia.gov/survey/form/eia_923/instructions.pdf', 'https://docs.catalyst.coop/pudl/en/v2026.2.0/_modules/pudl/metadata/codes.html'],
  condition_for_qualified_lower_bound='Current nonnegative net generation bounds on the109excludedhours; not an EIA rule.',
  excluded_net_energy_required_if_qualified_model_is_actual_MWh=float(df.EIA_net_generation_MWh.sum()-df.current_qualified_MWh.sum()),
  excluded_mean_net_power_required_if_qualified_model_is_actual_MW=float((df.EIA_net_generation_MWh.sum()-df.current_qualified_MWh.sum())/(~q).sum()),
  actual_negative_auxiliary_power_bound_established=False,frequency_by_plant=source[['plant_id','plant_name','respondent_frequency','balancing_authority']].drop_duplicates().to_dict('records'),
  current_qualified_minus_original_wind_prior_max_MW=float(np.max(abs(pg[q]-prior[q]))),
  EIA_outside_excluded_bounds_plantmonths=int((~df.EIA_within_excluded_hour_bounds).sum()),
  plants=annual[['plant_id','plant_name','EIA_net_generation_MWh','diagnostic_full_calendar_MWh','diagnostic_full_minus_EIA_MWh','relative_difference_pct']].to_dict('records'),
  no_model_change=True,no_PF_or_residual_fitting=True,annual_interval_distance_recomputed_from_annual_energy=True,annual_derived_flags_are_boolean=True,inputs=[rec(epath),rec(base/'model_generator_register.csv'),rec(base/'latest_model.mat'),rec(base/'profiles_h0001_4380.mat'),rec(base/'profiles_h4381_8760.mat'),rec(ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat'),rec(ROOT/'output/nygrid_2025_dispatch/fleet/fleet_bounds.npz')],
  latent_policy='Qualified modeledPG plus frozenprior on excludedhours where available;10missingP63hours linearly interpolated for diagnosticpointestimate only; robustminmaxbounds are also reported.',
  mechanism_code_citations=[dict(path='scripts/nygrid_2025_inputs/generation_priors.py',lines='484-506',claim='Wind zonal allocation weights active nameplate against statewide Wind total.'),dict(path='scripts/nygrid_2025_dispatch/build_dispatch_priors.py',lines='500-514',claim='Unit/plant allocation broadcasts active nameplate weights across hours and normalizes to P63 Wind total.'),dict(path='scripts/nygrid_2025_inputs/generation_priors.py',lines='651',claim='Explicit same statewide capacity factor assumption.')],
  limitations=['Four plants have raw code AM and supply monthly generation values once annually; Marble River and Jericho Rise have code M and report monthly. AM is not annual-total monthly imputation. Neither reporting frequency establishes hourly telemetry.','The 27.479 MW lower bound on qualified-hour overallocation is conditional on the current nonnegative excluded-hour wind bounds. EIA permits negative net generation when station service exceeds gross generation; no actual auxiliary-power lower bound is established.','Wind plant hourly output is reconstructed from statewide signal, not telemetry.','Plant energy mismatch does not by itself identify physical Moses meter error or certify all market-scope mappings.'])
 (OUT/'D_wind_source_energy_review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
