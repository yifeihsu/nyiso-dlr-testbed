"""Predeclared source-only monthly-flat St Lawrence shape control; no P32 or PF."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
import numpy as np,pandas as pd
from scipy.io import loadmat,savemat
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_postrepair_diagnosis/generation'
CURRENT=ROOT/'output/nygrid_2025_moses_repair/generation'
BASE=ROOT/'output/nygrid_2025_physical_repair/model'
sys.path.insert(0,str(ROOT/'scripts/nygrid_2025_moses_repair/generation'))
from build_generation_candidate import project_rows

def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
def mx(x):return float(np.max(np.abs(x),initial=0))
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 source_paths=[CURRENT/'generation_candidate.npz',CURRENT/'full8760_generation_ledger.csv',CURRENT/'StLawrence_monthly_energy_ledger.csv',
  ROOT/'output/nygrid_2025_moses_repair/model/model_generator_register.csv',ROOT/'output/nygrid_2025_western_audit/corrected/fleet_register.csv',
  ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat',ROOT/'output/nygrid_2025_dispatch/fleet/fleet_bounds.npz',
  BASE/'profiles_h0001_4380.mat',BASE/'profiles_h4381_8760.mat',ROOT/'scripts/nygrid_2025_moses_repair/generation/build_generation_candidate.py']
 frozen=[rec(p) for p in source_paths]
 policy=dict(schema_version=1,source_HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
  purpose='Diagnostic hourly-shape sensitivity only; no default model, map or package change',
  selection_uses_P32_or_interface_residuals=False,AC_solve_run=False,
  StLawrence_rule='Unique minimum hourly variance around each EIA monthly mean, projected to existing source-only hourly feasible intervals and exact full-calendar EIA monthly energy.',
  other_HY_rule='Same nearest-original-reference weighted bounded projection and frozen objective weights as current Moses repair; only StLawrence shape target differs.',
  fixed='Same full8760 clock,source mask,monthly StL energy,855engineering cap,dated15unit admission,PSgeneration,currentreconciledhourlyHYtotal,otherfuel,HQ,PV20,PAR,load,network.',
  excluded_hours='All109 remain excluded and keep the existing declared latent/reference policy; projected monthlyenergy includes them.',
  AC_test_hour_selection='For each calendar month select the source-qualified hour with maximum absolute ZoneD native generation delta; first chronological tie. No observed flows read.',
  frozen_loss_cut='Change in northern-cut publicMW equals change in nativeD publicMW only under frozen other boundary terms/load/losses; freshAC needed for exact flow effect.',sources=frozen)
 pp=OUT/'monthly_flat_shape_policy.json'
 if pp.exists():assert json.loads(pp.read_text())==policy
 else:pp.write_text(json.dumps(policy,indent=2)+'\n')
 z=np.load(CURRENT/'generation_candidate.npz');q=z['source_qualified'];gamma=float(z['gamma']);hydro_rows=z['hydro_rows_1based'].astype(int);cur=z['hydro_PG_public_MW']
 ledger=pd.read_csv(CURRENT/'full8760_generation_ledger.csv');monthly=pd.read_csv(CURRENT/'StLawrence_monthly_energy_ledger.csv').set_index('month');months=ledger.month_local.to_numpy()
 assert len(cur)==8760 and np.array_equal(ledger.hour_index,np.arange(1,8761)) and q.sum()==8651
 reg=pd.read_csv(ROOT/'output/nygrid_2025_moses_repair/model/model_generator_register.csv',dtype={'eia_generator_id':str})
 fleet=pd.read_csv(ROOT/'output/nygrid_2025_western_audit/corrected/fleet_register.csv',dtype={'eia_generator_id':str})
 lookup=reg.merge(fleet[['device_key','prime_mover','plant_name']],on='device_key',how='left',validate='one_to_one')
 hreg=lookup.set_index('gen_row').loc[hydro_rows];st=hreg.plant_id.eq(2694).to_numpy();ps=hreg.prime_mover.eq('PS').to_numpy();don=~st&~ps
 donor_rows=hydro_rows[don]-1
 parts=[loadmat(BASE/f,simplify_cells=True)['profiles'] for f in ['profiles_h0001_4380.mat','profiles_h4381_8760.mat']]
 oldpg=np.concatenate([p['generator_PG_MW'] for p in parts])/gamma
 oldlo=np.concatenate([p['generator_Pmin_MW'] for p in parts])/gamma
 oldhi=np.concatenate([p['generator_Pmax_MW'] for p in parts])/gamma
 prior=loadmat(ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat',simplify_cells=True,variable_names=['prior_pg','objective_weights'])
 reference=np.where(z['reconciled_profile_available'][:,None],oldpg[:,donor_rows],prior['prior_pg'][:,donor_rows]/gamma)
 missing=np.flatnonzero(~np.isfinite(reference).all(1));groups=np.split(missing,np.flatnonzero(np.diff(missing)>1)+1)
 for group in groups:
  left=group[0]-1;right=group[-1]+1;assert len(group)==2 and np.isfinite(reference[[left,right]]).all()
  for h in group:reference[h]=reference[left]+(reference[right]-reference[left])*(h-left)/(right-left)
 lo=oldlo[:,donor_rows];hi=oldhi[:,donor_rows]
 b=np.load(ROOT/'output/nygrid_2025_dispatch/fleet/fleet_bounds.npz');bindex={int(x):i for i,x in enumerate(b['fleet_id'])};fp=np.array([bindex[int(x)] for x in hreg.loc[don,'fleet_id']])
 lo=np.where(np.isfinite(lo),lo,b['pmin_actual_mw'][:,fp]);hi=np.where(np.isfinite(hi),hi,b['pmax_actual_mw'][:,fp]);weights=prior['objective_weights'][:,donor_rows]
 target=z['Hydro_target_public_MW'];lower=ledger.StLawrence_feasible_lower_MW.to_numpy();upper=ledger.StLawrence_feasible_upper_MW.to_numpy()
 alt_st=np.zeros(8760);mrows=[]
 for m in range(1,13):
  ix=np.flatnonzero(months==m);energy=float(monthly.loc[m,'EIA_monthly_target_MWh']);mean=energy/len(ix)
  x,d=project_rows(np.full((1,len(ix)),mean),lower[ix][None,:],upper[ix][None,:],[energy],np.ones((1,len(ix))))
  alt_st[ix]=x[0]
  mrows.append(dict(month=m,EIA_target_MWh=energy,physical_hours=len(ix),current_std_MW=float(z['StLawrence_plant_PG_public_MW'][ix].std()),control_std_MW=float(x.std()),
   current_cap_hours=int((z['StLawrence_plant_PG_public_MW'][ix]>=855-1e-7).sum()),control_cap_hours=int((x>=855-1e-7).sum()),control_energy_error_MWh=float(x.sum()-energy)))
 current_donor,_=project_rows(reference,lo,hi,target-z['StLawrence_plant_PG_public_MW']-cur[:,ps].sum(1),weights)
 assert mx(current_donor-cur[:,don])<1e-7,'Must reconstruct existing donor rule before comparison'
 alt_donor,dual=project_rows(reference,lo,hi,target-alt_st-cur[:,ps].sum(1),weights)
 alt=cur.copy();alt[:,don]=alt_donor;alt[:,st]=alt_st[:,None]*z['stlawrence_Pmax_public_MW']/855
 assert mx(alt.sum(1)-target)<1e-7 and mx(alt[:,ps]-cur[:,ps])==0
 dmask=hreg.zone.eq('D').to_numpy();delt=alt-cur;D=delt[:,dmask].sum(1);ST=alt_st-z['StLawrence_plant_PG_public_MW']
 out=ledger[['hour_index','timestamp_utc','month_local','source_qualified','reference_kind']].copy()
 out['current_StLawrence_public_MW']=z['StLawrence_plant_PG_public_MW'];out['control_StLawrence_public_MW']=alt_st;out['StLawrence_delta_public_MW']=ST
 out['current_D_HY_public_MW']=cur[:,dmask].sum(1);out['control_D_HY_public_MW']=alt[:,dmask].sum(1);out['native_D_delta_public_MW']=D
 out['native_D_delta_model_MW']=D*gamma;out['other_D_HY_delta_public_MW']=D-ST;out['NY_HY_total_delta_public_MW']=delt.sum(1)
 out.to_csv(OUT/'monthly_flat_hourly_injection_delta.csv',index=False)
 pd.DataFrame(mrows).to_csv(OUT/'monthly_flat_monthly_summary.csv',index=False)
 selected=[]
 for m in range(1,13):
  ids=np.flatnonzero((months==m)&q);h=ids[np.argmax(abs(D[ids]))];selected.append(out.iloc[h].to_dict())
 pd.DataFrame(selected).to_csv(OUT/'monthly_flat_source_selected_hours.csv',index=False)
 data=dict(hour_index=np.arange(1,8761),timestamp_utc=z['timestamp_utc'].astype(object),source_qualified=q,gamma=gamma,
  hydro_rows_1based=hydro_rows,hydro_PG_public_MW=alt,StLawrence_plant_PG_public_MW=alt_st,native_D_delta_public_MW=D,
  source_selected_hour_index=np.array([r['hour_index'] for r in selected]))
 savemat(OUT/'monthly_flat_generation_control.mat',data,do_compression=True,oned_as='column')
 bounds=max(mx(np.minimum(alt_donor-lo,0)),mx(np.maximum(alt_donor-hi,0)))
 report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),source_policy_frozen_before_projection=True,P32_or_flow_observations_read=False,
  no_AC_run=True,current_model_unchanged=True,source_qualified_hours=int(q.sum()),full_calendar_hours=8760,monthly_energy_error_MWh=max(abs(r['control_energy_error_MWh']) for r in mrows),
  hourly_HY_total_error_public_MW=mx(alt.sum(1)-target),donor_bounds_violation_MW=bounds,current_donor_reproduction_error_MW=mx(current_donor-cur[:,don]),
  qualified_StL_delta=dict(mean=float(ST[q].mean()),MAE=float(abs(ST[q]).mean()),min=float(ST[q].min()),max=float(ST[q].max())),
  qualified_native_D_delta=dict(mean=float(D[q].mean()),MAE=float(abs(D[q]).mean()),min=float(D[q].min()),max=float(D[q].max())),
  current_cap_hours_all=int((z['StLawrence_plant_PG_public_MW']>=855-1e-7).sum()),current_cap_hours_qualified=int(((z['StLawrence_plant_PG_public_MW']>=855-1e-7)&q).sum()),
  selected_hours=[r['hour_index'] for r in selected],policy=rec(pp),source_hashes_preserved=[rec(p) for p in source_paths]==frozen,
  limitations=['Source-feasible control is not observed hourly dispatch.','A frozen-loss cut response is not a fresh AC sensitivity.','OtherHYmonthlyenergy is not constrained to each EIA plant target.'])
 assert report['source_hashes_preserved']
 report['outputs']=[rec(OUT/n) for n in ['monthly_flat_hourly_injection_delta.csv','monthly_flat_monthly_summary.csv','monthly_flat_source_selected_hours.csv','monthly_flat_generation_control.mat']]
 (OUT/'monthly_flat_control_receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
