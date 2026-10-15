"""Independent saved-array validation of the frozen source-only generation fix."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_moses_repair/generation'


def record(path):
    with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':digest,'bytes':path.stat().st_size}


def maximum(x):return float(np.max(np.abs(x),initial=0.))


def check_kkt(x,reference,lo,hi,weights):
    """Derive an equality dual from free coordinates; no producer dual used."""
    gradient=weights*(x-reference);fixed=hi-lo<1e-9
    low=(x<=lo+1e-7)&~fixed;high=(x>=hi-1e-7)&~fixed;free=~(low|high|fixed)
    if free.any():dual=float(np.median(gradient[free]))
    else:
        left=float(np.max(gradient[high],initial=-np.inf));right=float(np.min(gradient[low],initial=np.inf))
        assert left<=right+1e-6
        dual=right if not np.isfinite(left) else left if not np.isfinite(right) else (left+right)/2
    errors=[maximum(gradient[free]-dual),float(np.max(np.maximum(0,dual-gradient[low]),initial=0.)),
            float(np.max(np.maximum(0,gradient[high]-dual),initial=0.))]
    return max(errors)


def main():
    proof_path=OUT/'candidate_receipt.json';proof=json.loads(proof_path.read_text());assert proof['passed']
    for item in proof['sources']+proof['outputs']:
        path=ROOT/item['path'];assert record(path)['sha256']==item['sha256'],path
    d=loadmat(OUT/'generation_candidate.mat',simplify_cells=True)
    with np.load(OUT/'generation_candidate.npz',allow_pickle=False) as z:
        for key in ['hydro_PG_public_MW','hydro_rows_1based','stlawrence_Pmax_public_MW','stlawrence_rows_1based','source_qualified']:
            assert np.array_equal(np.asarray(d[key]),z[key])
    pg=np.asarray(d['hydro_PG_public_MW']);hyrows=np.asarray(d['hydro_rows_1based'],int)-1;stlrows=np.asarray(d['stlawrence_rows_1based'],int)-1
    q=np.asarray(d['source_qualified'],bool);gamma=float(d['gamma'])
    assert pg.shape==(8760,364) and len(hyrows)==len(set(hyrows))==364 and hyrows[-1]==1464
    assert len(stlrows)==16 and stlrows[-1]==1464 and q.sum()==8651
    oldreg_path=ROOT/'output/nygrid_2025_western_audit/corrected/model_generator_register.csv'
    oldreg=pd.read_csv(oldreg_path,dtype={'eia_generator_id':str});reg=pd.read_csv(OUT/'model_generator_register_1465.csv',dtype={'eia_generator_id':str})
    assert reg.shape[0]==1465
    pd.testing.assert_frame_equal(reg.iloc[:1464].reset_index(drop=True),oldreg,check_dtype=False)
    assert reg.iloc[1464].eia_generator_id=='21' and reg.iloc[1464].plant_id==2694 and reg.iloc[1464].bus_id==48
    fleet=pd.read_csv(ROOT/'output/nygrid_2025_western_audit/corrected/fleet_register.csv')
    joined=oldreg.merge(fleet[['device_key','prime_mover']],on='device_key',validate='one_to_one')
    oldhy=np.flatnonzero(joined.role.eq('native')&joined.fuel_category.eq('Hydro'))
    assert np.array_equal(hyrows[:-1],oldhy)
    psrows=np.flatnonzero(joined.role.eq('native')&joined.fuel_category.eq('Hydro')&joined.prime_mover.eq('PS'))
    donors=np.array([r for r in oldhy if r not in set(stlrows) and r not in set(psrows)])
    assert len(donors)==333
    pos={r:i for i,r in enumerate(hyrows)};scols=np.array([pos[r] for r in stlrows]);pcols=np.array([pos[r] for r in psrows]);dcols=np.array([pos[r] for r in donors])
    reference=[];lower=[];upper=[]
    for name in ['profiles_h0001_4380.mat','profiles_h4381_8760.mat']:
        p=loadmat(ROOT/'output/nygrid_2025_physical_repair/model'/name,simplify_cells=True)['profiles']
        reference.append(p['generator_PG_MW']/gamma);lower.append(p['generator_Pmin_MW']/gamma);upper.append(p['generator_Pmax_MW']/gamma)
    reference=np.concatenate(reference);lower=np.concatenate(lower);upper=np.concatenate(upper)
    avail=np.isfinite(reference[:,oldhy]).all(axis=1);assert avail.sum()==8657
    sourcepriors=loadmat(ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat',simplify_cells=True)
    ref=np.where(avail[:,None],reference[:,oldhy],sourcepriors['prior_pg'][:,oldhy]/gamma)
    finite=np.isfinite(ref).all(axis=1);assert finite.sum()==8750
    for col in range(ref.shape[1]):ref[:,col]=np.interp(np.arange(8760),np.flatnonzero(finite),ref[finite,col])
    h=pd.read_csv(ROOT/'output/nygrid_2025_inputs/generation_source/statewide_fuelmix_hourly.csv')
    h=h.loc[h.fuel_category.eq('Hydro')].sort_values('hour_index')
    clock=pd.DatetimeIndex(pd.to_datetime(h.timestamp_utc,utc=True));months=clock.tz_convert('America/New_York').month.to_numpy()
    target=np.where(avail,reference[:,oldhy].sum(axis=1),h.generation_mw.to_numpy())
    target[~finite]=ref[~finite].sum(axis=1)
    conservation=maximum(pg.sum(axis=1)-target);assert conservation<1e-7
    baseline_conservation=maximum(pg[q].sum(axis=1)-reference[q][:,oldhy].sum(axis=1));assert baseline_conservation<1e-7
    ps_reference_error=maximum(pg[:,pcols]-ref[:,pcols])
    assert ps_reference_error<1e-9 and maximum(pg[q][:,pcols]-ref[q][:,pcols])==0.
    assert np.all(pg[q][:,dcols]>=lower[q][:,donors]-1e-8) and np.all(pg[q][:,dcols]<=upper[q][:,donors]+1e-8)
    b=np.load(ROOT/'output/nygrid_2025_dispatch/fleet/fleet_bounds.npz',allow_pickle=False);lookup={v:i for i,v in enumerate(b['fleet_id'])}
    dp=np.array([lookup[int(oldreg.iloc[r].fleet_id)] for r in donors]);lo=lower[:,donors].copy();hi=upper[:,donors].copy()
    missing=~np.isfinite(lo);lo[missing]=b['pmin_actual_mw'][:,dp][missing]
    missing=~np.isfinite(hi);hi[missing]=b['pmax_actual_mw'][:,dp][missing]
    assert np.all(pg[:,dcols]>=lo-1e-8) and np.all(pg[:,dcols]<=hi+1e-8)
    inventory=pd.read_csv(ROOT/'output/nygrid_2025_moses_source_diagnosis/generation/EIA860_plant2694_inventory_source_rows.csv',dtype={'Generator ID':str})
    inventory=inventory.loc[inventory.source_month.gt(0)];inventory['code']=inventory.Status.str.extract(r'(OP|OA|OS|SB|RE)',expand=False)
    cap=np.asarray(d['stlawrence_Pmax_public_MW']);assert np.all(cap.sum(axis=1)==855.)
    for month in range(1,13):
        inv=inventory.loc[inventory.source_month.eq(month)].set_index('Generator ID')
        for j,r in enumerate(stlrows):
            expected=57. if inv.loc[str(reg.iloc[r].eia_generator_id),'code'] in ['OP','SB'] else 0.
            assert np.all(cap[months==month,j]==expected)
    assert np.all(pg[:,scols]<=cap+1e-8) and np.all(pg[:,scols]>=0)
    assert maximum(pg[:,scols]-pg[:,scols].sum(axis=1)[:,None]*cap/855)<1e-9
    eia=pd.read_csv(ROOT/'output/nygrid_2025_western_audit/generation/final_EIA923_NY_hydro_scope.csv')
    eia=eia.loc[eia.plant_id.eq(2694)&eia.prime_mover.eq('HY')].set_index('month')
    plant=pg[:,scols].sum(axis=1);rplant=ref[:,[int(np.flatnonzero(oldhy==r)[0]) for r in stlrows[:-1]]].sum(axis=1)
    hlo=np.maximum(0,target-pg[:,pcols].sum(axis=1)-hi.sum(axis=1));hhi=np.minimum(855,target-pg[:,pcols].sum(axis=1)-lo.sum(axis=1))
    monthly_errors=[];stl_kkt=[];sensitivity=[]
    for month in range(1,13):
        use=months==month;E=float(eia.loc[month,'net_generation_mwh']);monthly_errors.append(abs(plant[use].sum()-E))
        stl_kkt.append(check_kkt(plant[use],rplant[use],hlo[use],hhi[use],np.ones(use.sum())))
        excluded=use&~q;qualified=use&q
        possible_min=max(float(hlo[excluded].sum()),E-float(hhi[qualified].sum()))
        possible_max=min(float(hhi[excluded].sum()),E-float(hlo[qualified].sum()))
        sensitivity.append({'month':month,'qualified_hours':int(qualified.sum()),'excluded_hours':int(excluded.sum()),
            'monthly_EIA_energy_MWh':E,'allocated_excluded_energy_MWh':float(plant[excluded].sum()),
            'minimum_feasible_excluded_energy_MWh':possible_min,'maximum_feasible_excluded_energy_MWh':possible_max,
            'excluded_energy_uncertainty_width_MWh':possible_max-possible_min,
            'equivalent_qualified_mean_uncertainty_width_MW':(possible_max-possible_min)/qualified.sum()})
        assert possible_min-1e-7<=plant[excluded].sum()<=possible_max+1e-7
    donor_kkt=0.
    for hour in range(8760):donor_kkt=max(donor_kkt,check_kkt(pg[hour,dcols],ref[hour,dcols],lo[hour],hi[hour],sourcepriors['objective_weights'][hour,donors]))
    assert max(monthly_errors)<1e-6 and max(stl_kkt)<1e-6 and donor_kkt<1e-5
    sensitivity_path=OUT/'excluded_hour_energy_sensitivity.csv';pd.DataFrame(sensitivity).to_csv(sensitivity_path,index=False)
    result={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'candidate_receipt':record(proof_path),
        'candidate_file':record(OUT/'generation_candidate.mat'),'all_original_generator_rows_preserved':True,
        'appended_actual_EIA_unit21_row':1465,'monthly_active_StLawrence_units':15,
        'all8760_calendar_energy_enforced':True,'qualified_hours':int(q.sum()),'unqualified_hours_not_promoted':int((~q).sum()),
        'maximum_monthly_energy_error_MWh':max(monthly_errors),'maximum_hourly_Hydro_conservation_error_MW':conservation,
        'maximum_qualified_total_generation_change_MW':baseline_conservation,
        'maximum_StLawrence_minchange_KKT_residual':max(stl_kkt),'maximum_otherHY_minchange_KKT_residual':donor_kkt,
        'PS_unchanged':True,'otherHY_original_qualified_bounds_preserved':True,'all_declared_latent_donor_bounds_pass':True,
        'maximum_PS_reference_reconstruction_roundoff_MW':ps_reference_error,
        'MAT_NPZ_values_identical':True,'no_PF_or_P32_scoring':True,
        'missing_hour_sensitivity':'Monthly feasible ranges for latent excluded energy are reported without reallocating all energy onto qualified hours.',
        'output':record(sensitivity_path),'producer':record(Path(__file__))}
    (OUT/'independent_generation_review.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
