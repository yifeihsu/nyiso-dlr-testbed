"""Audit current ZoneD hydro energy against final EIA plant totals; no fitting."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
import numpy as np,pandas as pd
from scipy.io import loadmat
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'output/nygrid_2025_postrepair_diagnosis/generation'
def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def main():
 zp=ROOT/'output/nygrid_2025_moses_repair/generation/generation_candidate.npz';rp=ROOT/'output/nygrid_2025_moses_repair/model/model_generator_register.csv'
 fp=ROOT/'output/nygrid_2025_western_audit/corrected/fleet_register.csv';ep=ROOT/'output/nygrid_2025_western_audit/generation/final_EIA923_NY_hydro_scope.csv'
 z=np.load(zp);q=z['source_qualified'];clock=pd.DatetimeIndex(pd.to_datetime(z['timestamp_utc'],utc=True));month=clock.tz_convert('America/New_York').month.to_numpy()
 reg=pd.read_csv(rp).set_index('gen_row');fleet=pd.read_csv(fp).set_index('device_key');h=reg.loc[z['hydro_rows_1based']].copy();h['prime_mover']=h.device_key.map(fleet.prime_mover);h['plant_name']=h.device_key.map(fleet.plant_name)
 pg=z['hydro_PG_public_MW'];eia=pd.read_csv(ep);eia=eia.loc[eia.prime_mover.eq('HY')]
 assert not eia.duplicated(['plant_id','month']).any()
 b=np.load(ROOT/'output/nygrid_2025_dispatch/fleet/fleet_bounds.npz');ix={int(v):i for i,v in enumerate(b['fleet_id'])}
 bpos=np.array([ix[int(v)] for v in h.fleet_id]);lo=b['pmin_actual_mw'][:,bpos];hi=b['pmax_actual_mw'][:,bpos]
 pp=[ROOT/'output/nygrid_2025_physical_repair/model'/n for n in ['profiles_h0001_4380.mat','profiles_h4381_8760.mat']]
 parts=[loadmat(p,simplify_cells=True)['profiles'] for p in pp];rows=z['hydro_rows_1based']-1;old=rows<1464;gamma=float(z['gamma'])
 for key,dest in [('generator_Pmin_MW',lo),('generator_Pmax_MW',hi)]:
  values=np.concatenate([p[key] for p in parts])[:,rows[old]]/gamma;dest[:,old]=np.where(np.isfinite(values),values,dest[:,old])
 monthly=[];D=h.zone.eq('D')&h.prime_mover.eq('HY')
 for plant in sorted(h.loc[D,'plant_id'].unique()):
  cols=np.flatnonzero((h.plant_id.eq(plant)&D).to_numpy());complete=set(h.loc[h.plant_id.eq(plant),'zone'])=={'D'}
  for m in range(1,13):
   t=eia.loc[eia.plant_id.eq(plant)&eia.month.eq(m)];assert len(t)<=1
   ids=month==m;qualified=ids&q;excluded=ids&~q;total=float(pg[np.ix_(ids,cols)].sum());qualifiedE=float(pg[np.ix_(qualified,cols)].sum());latent=float(pg[np.ix_(excluded,cols)].sum())
   E=float(t.net_generation_mwh.iloc[0]) if len(t) else np.nan
   L=float(lo[np.ix_(ids,cols)].sum());U=float(hi[np.ix_(ids,cols)].sum())
   monthly.append(dict(plant_id=int(plant),plant_name=h.iloc[cols[0]].plant_name,month=m,model_unit_rows=len(cols),all_model_plant_rows_in_D=complete,
    EIA_row_present=bool(len(t)),EIA_respondent_frequency=t.respondent_frequency.iloc[0] if len(t) else '',EIA_net_generation_MWh=E,current_full_calendar_reconstruction_MWh=total,
    current_qualified_MWh=qualifiedE,current_excluded_latent_MWh=latent,full_calendar_minus_EIA_MWh=total-E,
    bounds_min_energy_MWh=L,bounds_max_energy_MWh=U,EIA_within_independent_plant_bound=bool(L-1e-6<=E<=U+1e-6),
    monthly_shape_telemetry_observed=False,latent_energy_is_assumed=True,StLawrence_hard_monthly_target=plant==2694))
 df=pd.DataFrame(monthly);df.to_csv(OUT/'D_HY_plant_monthly_EIA_comparison.csv',index=False)
 annual=df.groupby(['plant_id','plant_name'],as_index=False).agg(EIA_net_generation_MWh=('EIA_net_generation_MWh',lambda x:x.sum(min_count=12)),
  current_full_calendar_reconstruction_MWh=('current_full_calendar_reconstruction_MWh','sum'),current_qualified_MWh=('current_qualified_MWh','sum'),current_excluded_latent_MWh=('current_excluded_latent_MWh','sum'),
  modeled_rows=('model_unit_rows','first'),EIA_months=('EIA_row_present','sum'),EIA_frequency=('EIA_respondent_frequency',lambda x:';'.join(sorted(set(x)))),StLawrence=('StLawrence_hard_monthly_target','first'))
 annual['difference_MWh']=annual.current_full_calendar_reconstruction_MWh-annual.EIA_net_generation_MWh;annual['relative_difference_pct']=100*annual.difference_MWh/annual.EIA_net_generation_MWh
 annual['absolute_difference_MWh']=abs(annual.difference_MWh);annual=annual.sort_values('absolute_difference_MWh',ascending=False)
 annual.to_csv(OUT/'D_HY_plant_annual_EIA_comparison.csv',index=False)
 donor=annual.loc[~annual.StLawrence];comparison=pd.read_csv(ROOT/'output/nygrid_2025_moses_repair/generation/other_HY_monthly_energy_changes.csv')
 matched=donor.loc[donor.EIA_months.eq(12)];unmatched=donor.loc[~donor.EIA_months.eq(12)]
 dcomp=comparison.loc[comparison.plant_id.isin(donor.plant_id)];assert abs(dcomp.repaired_energy_MWh.sum()-donor.current_full_calendar_reconstruction_MWh.sum())<1e-6
 result=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),modeled_D_HY_plants=len(annual),D_HY_generator_rows=int(D.sum()),
  nonStL_D_HY=dict(plants=len(donor),matched_EIA_plants=len(matched),missing_EIA_plants=unmatched[['plant_id','plant_name','current_full_calendar_reconstruction_MWh']].to_dict('records'),EIA_target_MWh=float(matched.EIA_net_generation_MWh.sum()),matched_current_full_calendar_MWh=float(matched.current_full_calendar_reconstruction_MWh.sum()),all_current_full_calendar_MWh=float(donor.current_full_calendar_reconstruction_MWh.sum()),
   current_qualified_MWh=float(donor.current_qualified_MWh.sum()),excluded_latent_MWh=float(donor.current_excluded_latent_MWh.sum()),
   full_calendar_difference_MWh=float(donor.difference_MWh.sum()),reference_before_StL_repair_MWh=float(dcomp.reference_energy_MWh.sum()),
   change_due_to_StL_repair_MWh=float(dcomp.energy_change_MWh.sum())),
  frequency_sources=['https://www.eia.gov/survey/form/eia_923/instructions.pdf', 'https://docs.catalyst.coop/pudl/en/v2026.2.0/_modules/pudl/metadata/codes.html'],top_nonStL_differences=donor.head(8).to_dict('records'),no_PF_or_fitting=True,inputs=[rec(p) for p in [zp,rp,fp,ep]],
  limitations=['Plant EIA net generation and public P63/current reconciled HY may differ in market and net-pumping scope.','AM respondents supply monthly generation values once annually. AM must not be equated with annual-total monthly imputation; these monthly reports do not establish hourly telemetry.',
    '109excludedhour values are latent assumptions, shown separately.','Independent plant energy bounds do not establish simultaneous feasibility with all plant targets and statewide hour totals.','Zone/bus mappings of smaller plants remain inherited proxies.'])
 (OUT/'D_HY_source_energy_review.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
