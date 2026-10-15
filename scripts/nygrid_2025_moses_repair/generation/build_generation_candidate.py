"""Source-only StLawrence monthly-energy repair with coherent hydro allocation.

No P32/interface observation, solver result or residual score is read. The
current reconciled hydro total is preserved wherever its input profile exists.
All8760 physical hours participate in the monthly plant energy ledger; latent
source-gap assumptions are exposed and never qualify an excluded network hour.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
import numpy as np
import pandas as pd
from scipy.io import loadmat,savemat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_moses_repair/generation'
BASE=ROOT/'output/nygrid_2025_physical_repair/model'
DIAG=ROOT/'output/nygrid_2025_moses_source_diagnosis/generation'
SOURCE=ROOT/'output/nygrid_2025_inputs/generation_source'


def record(path):
    with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':digest,'bytes':path.stat().st_size}


def mx(a):
    a=np.asarray(a);assert np.isfinite(a).all();return float(np.max(abs(a),initial=0.))


def project_rows(reference,lower,upper,total,weights):
    """Unique positive-weight bounded L2 projection, independently checkable KKT."""
    ref=np.atleast_2d(reference);lo=np.broadcast_to(lower,ref.shape);hi=np.broadcast_to(upper,ref.shape)
    w=np.broadcast_to(weights,ref.shape);target=np.asarray(total,float).reshape(-1)
    assert np.isfinite([ref,lo,hi,w]).all() and np.all(w>0) and np.all(hi>=lo)
    assert target.shape==(len(ref),) and np.all(target>=lo.sum(1)-1e-7) and np.all(target<=hi.sum(1)+1e-7)
    left=np.min(w*(lo-ref),axis=1);right=np.max(w*(hi-ref),axis=1)
    for _ in range(80):
        mid=(left+right)/2;x=np.clip(ref+mid[:,None]/w,lo,hi);below=x.sum(1)<target
        left=np.where(below,mid,left);right=np.where(below,right,mid)
    dual=(left+right)/2;x=np.clip(ref+dual[:,None]/w,lo,hi)
    assert mx(x.sum(1)-target)<1e-7
    return x,dual


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    model_path=BASE/'latest_model.mat';model=loadmat(model_path,simplify_cells=True)['model']
    gamma=float(model['scale_factor_gamma']);source_q=np.asarray(model['axis']['source_qualified'],bool)
    assert source_q.shape==(8760,) and source_q.sum()==8651
    reg_path=ROOT/'output/nygrid_2025_western_audit/corrected/model_generator_register.csv'
    fleet_path=ROOT/'output/nygrid_2025_western_audit/corrected/fleet_register.csv'
    inventory_path=DIAG/'EIA860_plant2694_inventory_source_rows.csv';inventory_proof_path=DIAG/'inventory_source_receipt.json'
    eia_path=ROOT/'output/nygrid_2025_western_audit/generation/final_EIA923_NY_hydro_scope.csv'
    p63_path=SOURCE/'statewide_fuelmix_hourly.csv'
    prior_path=ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat'
    fleet_bounds_path=ROOT/'output/nygrid_2025_dispatch/fleet/fleet_bounds.npz'
    profile_paths=[BASE/f for f in ['profiles_h0001_4380.mat','profiles_h4381_8760.mat']]
    gold_path=ROOT/'output/nygrid_2025_dispatch/fleet/source_scope/2025_Gold_Book.pdf'
    paths=[model_path,BASE/'model_receipt.json',reg_path,fleet_path,inventory_path,inventory_proof_path,eia_path,p63_path,prior_path,fleet_bounds_path,*profile_paths,gold_path]
    frozen=[record(p) for p in paths]
    inventory_proof=json.loads(inventory_proof_path.read_text());assert inventory_proof['passed']
    assert record(inventory_path)['sha256']==inventory_proof['output']['sha256']
    register=pd.read_csv(reg_path,dtype={'eia_generator_id':str});fleet=pd.read_csv(fleet_path,dtype={'eia_generator_id':str})
    joined=register.merge(fleet[['device_key','prime_mover','plant_name']],on='device_key',validate='one_to_one')
    assert np.array_equal(register.gen_row,np.arange(1,1465)) and np.array_equal(register.bus_id,model['generator_bus_ids'])
    hydro=joined.role.eq('native')&joined.fuel_category.eq('Hydro');conventional=hydro&joined.prime_mover.eq('HY')
    stl=conventional&pd.to_numeric(joined.plant_id,errors='coerce').eq(2694)
    donor=conventional&~stl;ps=hydro&joined.prime_mover.eq('PS')
    hydro_rows=np.flatnonzero(hydro);stl_rows=np.flatnonzero(stl);donor_rows=np.flatnonzero(donor);ps_rows=np.flatnonzero(ps)
    assert len(stl_rows)==15 and len(donor_rows)==333 and len(ps_rows)==15 and len(hydro_rows)==363
    appended=fleet.loc[fleet.plant_id.eq(2694)&fleet.eia_generator_id.eq('21')];assert len(appended)==1
    assert appended.iloc[0].device_key not in set(register.device_key)
    new_row=register.iloc[stl_rows[0]].to_dict();new_row.update(gen_row=1465,fleet_id=int(appended.iloc[0].fleet_id),
        device_key=appended.iloc[0].device_key,eia_generator_id='21',mapping_method='same_plant_bus48_source_dated_unit_admission')
    new_register=pd.concat([register,pd.DataFrame([new_row])],ignore_index=True)
    assert new_register.device_key.is_unique and np.array_equal(new_register.gen_row,np.arange(1,1466))
    new_register.to_csv(OUT/'model_generator_register_1465.csv',index=False)
    stl_all=np.r_[stl_rows,1464];hydro_all=np.r_[hydro_rows,1464]
    new_stl_ids=new_register.iloc[stl_all].eia_generator_id.astype(str).to_numpy()
    source=pd.read_csv(p63_path);source=source.loc[source.fuel_category.eq('Hydro')].sort_values('hour_index')
    assert np.array_equal(source.hour_index,np.arange(1,8761))
    timestamp=source.timestamp_utc.to_numpy(str);clock=pd.DatetimeIndex(pd.to_datetime(timestamp,utc=True));months=clock.tz_convert('America/New_York').month.to_numpy()
    H=source.generation_mw.to_numpy(float);H_valid=source.coverage_qualified.astype(bool).to_numpy()&np.isfinite(H)
    assert H_valid.sum()==8750 and np.all(H_valid[source_q])
    parts={k:[] for k in ['generator_PG_MW','generator_Pmin_MW','generator_Pmax_MW']}
    for path in profile_paths:
        profiles=loadmat(path,simplify_cells=True)['profiles']
        for key in parts:parts[key].append(profiles[key]/gamma)
    pg,lo,hi=[np.concatenate(parts[key]) for key in parts]
    prior=loadmat(prior_path,simplify_cells=True,variable_names=['prior_pg','objective_weights'])
    pgprior=prior['prior_pg']/gamma;weights=prior['objective_weights'][:,donor_rows]
    bounds=np.load(fleet_bounds_path,allow_pickle=False);fleet_index={int(x):i for i,x in enumerate(bounds['fleet_id'])}
    fleet_pos=np.array([fleet_index[int(x)] for x in register.iloc[hydro_rows].fleet_id])
    raw_HY_pg=pg[:,hydro_rows];available=np.isfinite(raw_HY_pg).all(axis=1)
    assert available.sum()==8657 and np.all(available[source_q])
    ref=np.where(available[:,None],raw_HY_pg,pgprior[:,hydro_rows])
    prior_finite=np.isfinite(ref).all(axis=1);assert prior_finite.sum()==8750
    latent=np.flatnonzero(~prior_finite);assert np.array_equal(latent,np.flatnonzero(~H_valid))
    # Every missing run is internal, two consecutive UTC hours, and remains
    # unqualified. Linear interpolation is a declared latent-ledger assumption.
    groups=np.split(latent,np.flatnonzero(np.diff(latent)>1)+1)
    interpolation_rows=[]
    for group in groups:
        assert len(group)==2 and group[0]>0 and group[-1]<8759
        left=group[0]-1;right=group[-1]+1;assert prior_finite[left] and prior_finite[right]
        assert months[left]==months[right]
        for h in group:
            fraction=(h-left)/(right-left);ref[h]=(1-fraction)*ref[left]+fraction*ref[right]
            interpolation_rows.append({'hour_index':int(h+1),'timestamp_utc':timestamp[h],
                'left_hour_index':int(left+1),'right_hour_index':int(right+1),'right_weight':fraction,
                'promoted_source_qualified':False,'inferred_observation':False})
    assert np.isfinite(ref).all()
    hydro_target=np.where(available,raw_HY_pg.sum(axis=1),H)
    hydro_target[~H_valid]=ref[~H_valid].sum(axis=1)
    assert np.isfinite(hydro_target).all()
    reference_kind=np.where(available,'preserved_reconciled_profile',np.where(H_valid,'latent_frozen_prior_with_observed_P63_total','latent_two_hour_bracket_interpolation'))
    # Original otherHY bounds remain binding wherever present. Missing limits
    # in excluded source gaps use the already-frozen fleet capability only for
    # the latent energy ledger; the compiler does not replace otherHY bounds.
    hy_lo=lo[:,hydro_rows].copy();hy_hi=hi[:,hydro_rows].copy()
    missing_lo=~np.isfinite(hy_lo);missing_hi=~np.isfinite(hy_hi)
    fallback_lo=bounds['pmin_actual_mw'][:,fleet_pos];fallback_hi=bounds['pmax_actual_mw'][:,fleet_pos]
    hy_lo[missing_lo]=fallback_lo[missing_lo];hy_hi[missing_hi]=fallback_hi[missing_hi]
    assert np.isfinite(hy_lo).all() and np.isfinite(hy_hi).all()
    position={r:i for i,r in enumerate(hydro_rows)};dpos=np.array([position[r] for r in donor_rows]);spos=np.array([position[r] for r in stl_rows]);ppos=np.array([position[r] for r in ps_rows])
    ps_fixed=ref[:,ppos];assert np.all(ps_fixed>=hy_lo[:,ppos]-1e-8)
    # PS hourly source-derived availability bounds may be missing in10gaps;
    # its held output is checked against physical fleet capacity there.
    ps_physical=bounds['physical_pmax_actual_mw'][:,fleet_pos[ppos]]
    assert np.all(ps_fixed<=ps_physical+1e-8)
    unit_inventory=pd.read_csv(inventory_path,dtype={'Generator ID':str});unit_inventory=unit_inventory.loc[unit_inventory.source_month.gt(0)]
    unit_inventory['status_code']=unit_inventory.Status.str.extract(r'(OP|OA|OS|SB|RE)',expand=False)
    stl_hi=np.zeros((8760,16));status_rows=[]
    for month in range(1,13):
        inventory=unit_inventory.loc[unit_inventory.source_month.eq(month)].set_index('Generator ID')
        assert len(inventory)==16 and inventory.index.is_unique
        active=inventory.status_code.isin(['OP','SB']);assert active.sum()==15
        nameplate=pd.to_numeric(inventory['Nameplate Capacity (MW)']);assert np.all(nameplate==57.)
        for j,gid in enumerate(new_stl_ids):
            admitted=bool(active.loc[gid]);stl_hi[months==month,j]=57. if admitted else 0.
            status_rows.append({'month':month,'plant_id':2694,'eia_generator_id':gid,'model_gen_row_1based':int(stl_all[j]+1),
                'monthly_inventory_status':inventory.loc[gid,'status_code'],'hourly_availability_assumed_from_monthly_status':True,
                'engineering_Pmax_public_MW':57. if admitted else 0.,'source_nameplate_MW':57.,'source_seasonal_net_MW':53.5,
                'hourly_unit_generation_observed':False})
    plant_cap=stl_hi.sum(axis=1);assert np.all(plant_cap==855.)
    donor_lo=hy_lo[:,dpos];donor_hi=hy_hi[:,dpos]
    lower=np.maximum(0.,hydro_target-ps_fixed.sum(axis=1)-donor_hi.sum(axis=1))
    upper=np.minimum(plant_cap,hydro_target-ps_fixed.sum(axis=1)-donor_lo.sum(axis=1))
    assert np.all(upper>=lower-1e-8)
    eia=pd.read_csv(eia_path);eia=eia.loc[eia.plant_id.eq(2694)&eia.prime_mover.eq('HY')].set_index('month')
    assert len(eia)==12 and eia.respondent_frequency.eq('M').all()
    feasibility=[]
    for month in range(1,13):
        ix=months==month;target=float(eia.loc[month,'net_generation_mwh']);low=float(lower[ix].sum());high=float(upper[ix].sum())
        feasibility.append({'month':month,'physical_hours':int(ix.sum()),'qualified_model_hours':int((ix&source_q).sum()),
            'excluded_model_hours':int((ix&~source_q).sum()),'EIA_target_MWh':target,'minimum_feasible_MWh':low,'maximum_feasible_MWh':high,
            'target_minus_minimum_MWh':target-low,'maximum_minus_target_MWh':high-target,'feasible':bool(low-1e-6<=target<=high+1e-6)})
    feasibility=pd.DataFrame(feasibility);feasibility.to_csv(OUT/'source_only_feasibility.csv',index=False)
    assert feasibility.feasible.all(),'Source-only monthly constraints are infeasible; no generation candidate emitted.'
    discrepancy=raw_HY_pg[source_q].sum(axis=1)-H[source_q]
    policy={'schema_version':1,'source_HEAD':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_only':True,'P32_or_interface_observations_read':False,'Moses_residual_used_to_choose_policy':False,
        'StLawrence_monthly_energy':'Exact finalEIA923 plant2694 HY netMWh over all physical NewYork month hours, including latent excluded hours.',
        'hourly_Hydro_target':'Preserve current reconciled nativeHydro input total where that profile exists; retain its difference from rawP63 explicitly.',
        'excluded_hour_policy':'6excluded hours with finite reconciled profiles retain those targets;93use frozen HY prior with observedP63 total;10missingP63 hours use bracketed linear latent interpolation. All109 remain excluded from model qualification.',
        'StLawrence_engineering_upper_bound':'15 monthly-OP units times57MW EIAnameplate=855MW; engineering bound, not observed net hourly capability or availability.',
        'dated_capability_context':{'GoldBook2025_pdf_page':88,'GoldBook_notes_pdf_page':105,'Summer2025_DMNC_MW':856,'Winter2024_25_DMNC_MW':810,
            'CRIS_summer_winter_MW':[856,856],'historical_nameplate_MW':1088,'market_DMNC_used_as_hourly_hard_bound':False},
        'unit_identity':'Append EIA2694unit21 as row1465; retain all old rows including HQrow1464. Unit26offJan-Feb,21offMar-Dec; exactly15OP/month.',
        'StLawrence_hourly_shape':'Unique unweighted minimum squared deviation from existing reconciled plantPG where available, otherwise frozen sourceprior/declared latent interpolation, subject to exact monthlyenergy and hourly feasible intervals.',
        'StLawrence_unit_dispatch':'Equal nameplate-proportional allocation among15monthly-active equal57MW units; not observed unit telemetry.',
        'other_HY_redistribution':'Unique bounded weighted least-squares projection nearest existing unitPG/reference at eachhour, using frozen original objective_weights; preserves hourly target after held PS and repairedStL.',
        'PS_generation':'Held at existing source-derived positive generation profile/reference. Net-pumping/P63 scope is not newly certified.',
        'other_fuel_HQ_PAR_and_load':'Unchanged by this artifact. Only Hydro PG and StLawrence bounds are supplied to compiler.',
        'old_other_HY_bounds_changed_on_qualified_hours':False,'latent_missing_bounds':'Frozen fleet bounds only for excluded-hour energy ledger; not promoted as observed availability.',
        'raw_P63_vs_reconciled_HY_difference_qualified_MW':{'mean_model_minus_P63':float(discrepancy.mean()),'MAE':float(abs(discrepancy).mean()),'min':float(discrepancy.min()),'max':float(discrepancy.max())},
        'new_AC_run_or_interface_scoring':False,'sources':frozen}
    policy_path=OUT/'generation_policy.json'
    if policy_path.exists():assert json.loads(policy_path.read_text())==policy,'Frozen generation policy differs; use a new version.'
    else:policy_path.write_text(json.dumps(policy,indent=2)+'\n',encoding='utf-8')
    reference_stl=ref[:,spos].sum(axis=1);repaired_stl=np.zeros(8760);stl_duals=[]
    for month in range(1,13):
        ix=np.flatnonzero(months==month);target=float(eia.loc[month,'net_generation_mwh'])
        result,dual=project_rows(reference_stl[ix][None,:],lower[ix][None,:],upper[ix][None,:],[target],np.ones((1,len(ix))))
        repaired_stl[ix]=result[0];stl_duals.append({'month':month,'equality_dual':float(dual[0])})
    remaining=hydro_target-repaired_stl-ps_fixed.sum(axis=1)
    donors,donor_dual=project_rows(ref[:,dpos],donor_lo,donor_hi,remaining,weights)
    stl_units=repaired_stl[:,None]*stl_hi/plant_cap[:,None]
    repaired=np.zeros((8760,len(hydro_all)));repaired[:,:len(hydro_rows)]=ref
    repaired[:,dpos]=donors
    for j,row in enumerate(stl_all):
        col=int(np.flatnonzero(hydro_all==row)[0]);repaired[:,col]=stl_units[:,j]
    assert mx(repaired.sum(axis=1)-hydro_target)<1e-7
    assert mx(repaired[:,ppos]-ps_fixed)==0.
    assert np.all(donors>=donor_lo-1e-8) and np.all(donors<=donor_hi+1e-8)
    assert np.all(stl_units>=-1e-8) and np.all(stl_units<=stl_hi+1e-8)
    # KKT checks independently characterize the exact chosen min-change rules.
    stationary=weights*(donors-ref[:,dpos])-donor_dual[:,None]
    free=(donors>donor_lo+1e-7)&(donors<donor_hi-1e-7)
    kkt_free=mx(stationary[free]);assert kkt_free<1e-6
    lower_active=donors<=donor_lo+1e-7;upper_active=donors>=donor_hi-1e-7
    kkt_lower=float(np.max(np.maximum(0,-stationary[lower_active&~upper_active]),initial=0.))
    kkt_upper=float(np.max(np.maximum(0,stationary[upper_active&~lower_active]),initial=0.))
    assert max(kkt_lower,kkt_upper)<1e-5
    monthly=[];donor_monthly=[]
    for month in range(1,13):
        ix=months==month;target=float(eia.loc[month,'net_generation_mwh']);actual=float(repaired_stl[ix].sum())
        assert abs(actual-target)<1e-6
        monthly.append({'month':month,'physical_hours':int(ix.sum()),'qualified_hours':int((ix&source_q).sum()),'excluded_hours':int((ix&~source_q).sum()),
            'EIA_monthly_target_MWh':target,'repaired_all_hour_StLawrence_MWh':actual,'monthly_energy_error_MWh':actual-target,
            'qualified_StLawrence_MWh':float(repaired_stl[ix&source_q].sum()),'latent_excluded_StLawrence_MWh':float(repaired_stl[ix&~source_q].sum()),
            'reference_plant_mean_MW':float(reference_stl[ix].mean()),'repaired_plant_mean_MW':float(repaired_stl[ix].mean()),
            'repaired_min_MW':float(repaired_stl[ix].min()),'repaired_max_MW':float(repaired_stl[ix].max()),
            'reference_std_MW':float(reference_stl[ix].std()),'repaired_std_MW':float(repaired_stl[ix].std()),
            'hours_at_engineering_cap':int((repaired_stl[ix]>=855-1e-7).sum())})
        for plant,group in joined.iloc[donor_rows].groupby('plant_id',dropna=False):
            rr=group.gen_row.to_numpy(int)-1;cols=np.array([int(np.flatnonzero(donor_rows==r)[0]) for r in rr])
            donor_monthly.append({'month':month,'plant_id':plant,'reference_energy_MWh':float(ref[np.ix_(ix,dpos[cols])].sum()),
                'repaired_energy_MWh':float(donors[np.ix_(ix,cols)].sum()),'energy_change_MWh':float((donors[np.ix_(ix,cols)]-ref[np.ix_(ix,dpos[cols])]).sum())})
    pd.DataFrame(monthly).to_csv(OUT/'StLawrence_monthly_energy_ledger.csv',index=False)
    pd.DataFrame(donor_monthly).to_csv(OUT/'other_HY_monthly_energy_changes.csv',index=False)
    pd.DataFrame(status_rows).to_csv(OUT/'StLawrence_dated_unit_admission.csv',index=False)
    pd.DataFrame(interpolation_rows).to_csv(OUT/'latent_P63_gap_policy.csv',index=False)
    pd.DataFrame(stl_duals).to_csv(OUT/'StLawrence_monthly_projection_duals.csv',index=False)
    ledger=pd.DataFrame({'hour_index':np.arange(1,8761),'timestamp_utc':timestamp,'month_local':months,'source_qualified':source_q,
        'reconciled_profile_available':available,'P63_Hydro_observed_qualified':H_valid,'reference_kind':reference_kind,
        'observed_P63_Hydro_MW':H,'preserved_or_latent_Hydro_target_MW':hydro_target,'repaired_Hydro_total_MW':repaired.sum(axis=1),
        'reference_StLawrence_MW':reference_stl,'repaired_StLawrence_MW':repaired_stl,'StLawrence_engineering_cap_MW':plant_cap,
        'StLawrence_feasible_lower_MW':lower,'StLawrence_feasible_upper_MW':upper,'fixed_PS_generation_MW':ps_fixed.sum(axis=1),
        'other_HY_change_MW':(donors-ref[:,dpos]).sum(axis=1),'Hydro_conservation_error_MW':repaired.sum(axis=1)-hydro_target})
    ledger.to_csv(OUT/'full8760_generation_ledger.csv',index=False)
    data={'hour_index':np.arange(1,8761,dtype=np.int32),'timestamp_utc':timestamp.astype(object),'gamma':gamma,
        'hydro_rows_1based':hydro_all+1,'hydro_PG_public_MW':repaired,'stlawrence_rows_1based':stl_all+1,
        'stlawrence_Pmin_public_MW':np.zeros_like(stl_hi),'stlawrence_Pmax_public_MW':stl_hi,
        'source_qualified':source_q,'reconciled_profile_available':available,'P63_Hydro_observed_qualified':H_valid,
        'StLawrence_plant_PG_public_MW':repaired_stl,'Hydro_target_public_MW':hydro_target,
        'latent_interpolated_hours':~H_valid,'other_HY_projection_dual':donor_dual,
        'new_generator_row_1based':1465,'new_generator_bus_id':48,'new_generator_plant_id':2694,'new_generator_EIA_ID':'21'}
    mat_path=OUT/'generation_candidate.mat';savemat(mat_path,data,do_compression=True,oned_as='column')
    npz_path=OUT/'generation_candidate.npz';np.savez_compressed(npz_path,**{**data,'timestamp_utc':timestamp})
    readback=loadmat(mat_path,simplify_cells=True)
    assert np.array_equal(readback['hydro_PG_public_MW'],repaired) and np.array_equal(readback['source_qualified'].astype(bool),source_q)
    assert [record(p) for p in paths]==frozen
    outputs=[policy_path,OUT/'model_generator_register_1465.csv',OUT/'source_only_feasibility.csv',OUT/'StLawrence_monthly_energy_ledger.csv',
        OUT/'other_HY_monthly_energy_changes.csv',OUT/'StLawrence_dated_unit_admission.csv',OUT/'latent_P63_gap_policy.csv',
        OUT/'StLawrence_monthly_projection_duals.csv',OUT/'full8760_generation_ledger.csv',mat_path,npz_path]
    receipt={'passed':True,'policy_frozen_before_projection_and_before_Moses_scoring':True,'created_utc':datetime.now(timezone.utc).isoformat(),
        'source_HEAD':policy['source_HEAD'],'old_generator_rows':1464,'new_generator_rows':1465,'native_added_EIA_unit':'2694:21',
        'hydro_rows_in_compact_artifact':len(hydro_all),'StLawrence_rows':16,'monthly_OP_units':15,'hours':8760,'original_qualified_hours':8651,
        'full_calendar_StLawrence_energy_MWh':float(repaired_stl.sum()),'EIA_target_MWh':float(eia.net_generation_mwh.sum()),
        'maximum_monthly_energy_error_MWh':max(abs(r['monthly_energy_error_MWh']) for r in monthly),
        'maximum_hourly_Hydro_conservation_error_public_MW':mx(repaired.sum(axis=1)-hydro_target),
        'maximum_qualified_native_total_change_public_MW':mx(repaired[source_q].sum(axis=1)-raw_HY_pg[source_q].sum(axis=1)),
        'fixed_PS_change_public_MW':0.,'qualified_otherHY_bound_violation_public_MW':float(max(0,np.max(donor_lo[source_q]-donors[source_q]),np.max(donors[source_q]-donor_hi[source_q]))),
        'KKT_free_residual':kkt_free,'KKT_lower_violation':kkt_lower,'KKT_upper_violation':kkt_upper,
        'profile_available_reconciled_hours':int(available.sum()),'excluded_with_reconciled_profiles':int((~source_q&available).sum()),
        'excluded_with_observed_P63_and_frozen_prior':int((~available&H_valid).sum()),'latent_P63_gap_hours':int((~H_valid).sum()),
        'source_mask_changed':False,'other_fuel_HQ_PAR_load_changed':False,'otherHY_bounds_changed_on_qualified_hours':False,
        'P32_or_interface_observations_read':False,'Moses_metrics_computed':False,'AC_feasibility_or_hourly_telemetry_claimed':False,
        'raw_P63_total_preservation_claimed':False,'raw_P63_difference':policy['raw_P63_vs_reconciled_HY_difference_qualified_MW'],
        'all_inputs_unchanged':True,'MAT_roundtrip_passed':True,'candidate_file':record(mat_path),'policy':record(policy_path),
        'outputs':[record(p) for p in outputs],'sources':frozen,'producer':record(Path(__file__)),
        'limitations':['855MW is an engineering nameplate-derived bound, not observed hourly dependable capability or outage telemetry.',
            'Hourly shape minimizes changes to existing source-derived estimates; monthly energy does not identify actual hourly plant dispatch.',
            'Other conventional hydro monthly energies are allowed to move and are reported; they are not simultaneously reconciled to all EIA plant energies.',
            'Positive PS generation and existing reconciled fuel-group scope are retained; no new net-pumping scope certification is claimed.',
            '109excluded network hours remain excluded, although they participate in a separately labeled full-calendar source-energy ledger.']}
    (OUT/'candidate_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:receipt[k] for k in ['passed','new_generator_rows','full_calendar_StLawrence_energy_MWh','maximum_monthly_energy_error_MWh','maximum_hourly_Hydro_conservation_error_public_MW','maximum_qualified_native_total_change_public_MW']}))


if __name__=='__main__':main()
