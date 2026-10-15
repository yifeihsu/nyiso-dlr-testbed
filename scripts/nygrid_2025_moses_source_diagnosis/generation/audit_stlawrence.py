"""Trace StLawrence2694 source inputs and conditional Moses sensitivities.

No optimization or PF. Source target construction does not use P32 values.
Existing default inputs remain untouched. National workbook caches are optional
when the authenticated plant-level extract is available.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,subprocess
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'output/nygrid_2025_moses_source_diagnosis'
OUT=BASE/'generation'
SOURCE=ROOT/'output/nygrid_2025_inputs/generation_source'


def record(path):
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':digest,'bytes':path.stat().st_size}


def bools(values):
    v=pd.Series(values).astype(str).str.lower();assert v.isin(['true','false','1','0']).all()
    return v.isin(['true','1']).to_numpy()


def error_stats(pred,obs):
    e=np.asarray(pred)-np.asarray(obs);assert np.isfinite(e).all()
    return {'hours':len(e),'MAE_public_MW':float(abs(e).mean()),'RMSE_public_MW':float(np.sqrt(np.mean(e*e))),
        'bias_public_MW':float(e.mean()),'WAPE_percent':float(100*abs(e).sum()/abs(obs).sum())}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    balance_path=BASE/'balance_hourly.csv';contract_path=BASE/'balance_contract.json'
    fleet_path=ROOT/'output/nygrid_2025_western_audit/corrected/fleet_register.csv'
    register_path=ROOT/'output/nygrid_2025_western_audit/corrected/model_generator_register.csv'
    prior_path=ROOT/'output/nygrid_2025_dispatch/dispatch/dispatch_priors.mat'
    plant_register_path=SOURCE/'hydro_monthly_plant_allocation_register.csv'
    early_eia_path=SOURCE/'eia923_monthly_hydro_2025.csv'
    final_eia_path=ROOT/'output/nygrid_2025_western_audit/generation/final_EIA923_NY_hydro_scope.csv'
    p63_path=SOURCE/'statewide_fuelmix_hourly.csv'
    reconciliation_path=ROOT/'output/nygrid_2025_western_audit/generation/monthly_P63_EIA_projection_reconciliation.csv'
    inventory_path=OUT/'EIA860_plant2694_inventory_source_rows.csv';inventory_receipt_path=OUT/'inventory_source_receipt.json'
    nypa_path=OUT/'sources/nypa_openny_net_generation.json';nypa_meta_path=OUT/'sources/nypa_openny_metadata.json'
    comparison_path=ROOT/'output/nygrid_2025_physical_repair/annual/physical_repair_v1/comparison/comparison_arrays.npz'
    paths=[balance_path,contract_path,fleet_path,register_path,prior_path,plant_register_path,early_eia_path,final_eia_path,p63_path,
        reconciliation_path,inventory_path,inventory_receipt_path,nypa_path,nypa_meta_path,comparison_path,
        ROOT/'scripts/nygrid_2025_inputs/generation_priors.py',ROOT/'build_compact_nonfossil_generation_inputs.py',
        ROOT/'scripts/nygrid_2025_dispatch/build_dispatch_priors.py',ROOT/'scripts/nygrid_2025_dispatch/build_fleet.py']
    profile_paths=[ROOT/'output/nygrid_2025_physical_repair/model'/name for name in ['profiles_h0001_4380.mat','profiles_h4381_8760.mat']]
    plant_prior_paths=[SOURCE/f'hydro_plant_priors_{month:02d}.npz' for month in range(1,13)]
    paths+=profile_paths+plant_prior_paths;before=[record(p) for p in paths]
    inventory_receipt=json.loads(inventory_receipt_path.read_text());assert inventory_receipt['passed']
    assert record(inventory_path)['sha256']==inventory_receipt['output']['sha256']
    contract=json.loads(contract_path.read_text());assert contract['passed'] and contract['qualified_hours']==8651
    balance=pd.read_csv(balance_path);assert np.array_equal(balance.hour_index,np.arange(1,8761))
    q=bools(balance.qualified);assert q.sum()==8651 and np.array_equal(q,bools(balance.source_qualified))
    months=balance.month_local.to_numpy(int);clock=pd.DatetimeIndex(pd.to_datetime(balance.timestamp_utc,utc=True))
    assert np.array_equal(clock.tz_convert('America/New_York').month,months)
    with np.load(comparison_path,allow_pickle=False) as comparison:gamma=float(comparison['gamma'])
    fleet=pd.read_csv(fleet_path,dtype={'eia_generator_id':str});register=pd.read_csv(register_path,dtype={'eia_generator_id':str})
    units=fleet.loc[pd.to_numeric(fleet.plant_id,errors='coerce').eq(2694)].copy()
    model_rows=register.loc[pd.to_numeric(register.plant_id,errors='coerce').eq(2694)].copy()
    assert len(units)==16 and len(model_rows)==15 and units.eia_generator_id.is_unique
    assert set(model_rows.bus_id)=={48} and set(model_rows.zone)=={'D'}
    rows=model_rows.gen_row.to_numpy(int)-1;pieces=[];cap_pieces=[]
    for path in profile_paths:
        d=loadmat(path,simplify_cells=True,variable_names=['profiles'])['profiles']
        pieces.append(d['generator_PG_MW'][:,rows].sum(axis=1)/gamma)
        cap_pieces.append(d['generator_Pmax_MW'][:,rows].sum(axis=1)/gamma)
    current=np.concatenate(pieces);cap=np.concatenate(cap_pieces)
    assert np.allclose(current,balance.StLawrence_PG_MW,equal_nan=True,rtol=0,atol=1e-10)
    assert np.max(abs(cap-balance.StLawrence_Pmax_MW))<1e-10
    assert np.max(abs(cap[q]-802.5))<1e-9
    # Missing source quality can leave the available-bound profile nonfinite. It is not
    # evidence of a plant outage. Allow the full admitted seasonal capability
    # in every excluded hour for a conservative missing-energy upper bound.
    nominal_cap=np.full(8760,802.5)
    admitted=set(model_rows.eia_generator_id);units['currently_admitted_model_unit']=units.eia_generator_id.isin(admitted)
    units['model_gen_row']=units.eia_generator_id.map(model_rows.set_index('eia_generator_id').gen_row)
    units.to_csv(OUT/'StLawrence_frozen_unit_scope.csv',index=False)

    inventory=pd.read_csv(inventory_path,dtype={'Generator ID':str});inventory['source_month']=inventory.source_month.astype(int)
    inventory['status_code']=inventory.Status.str.extract(r'(OP|OA|OS|SB|RE)',expand=False)
    inventory['summer_MW']=pd.to_numeric(inventory['Summer Capacity (MW)'],errors='coerce').fillna(pd.to_numeric(inventory['Net Summer Capacity (MW)'],errors='coerce'))
    inventory['winter_MW']=pd.to_numeric(inventory['Winter Capacity (MW)'],errors='coerce').fillna(pd.to_numeric(inventory['Net Winter Capacity (MW)'],errors='coerce'))
    inventory['nameplate_MW']=pd.to_numeric(inventory['Nameplate Capacity (MW)'])
    assert not inventory.duplicated(['source_month','Generator ID']).any() and len(inventory)==208
    final_inventory=inventory.loc[inventory.source_month.eq(0)].set_index('Generator ID')
    frozen=units.set_index('eia_generator_id')
    assert set(final_inventory.index)==set(frozen.index)
    for unit in frozen.index:
        assert final_inventory.loc[unit,'status_code']==frozen.loc[unit,'source_status']
        for new,old in [('summer_MW','summer_capacity_mw'),('winter_MW','winter_capacity_mw'),('nameplate_MW','nameplate_capacity_mw')]:
            assert final_inventory.loc[unit,new]==frozen.loc[unit,old]
    inventory['current_frozen_status']=inventory['Generator ID'].map(frozen.source_status)
    inventory['current_model_admitted']=inventory['Generator ID'].isin(admitted)
    inventory['status_differs_from_frozen_annual']=inventory.status_code.ne(inventory.current_frozen_status)
    inventory['status_is_hourly_observed_availability']=False
    keep=['source_month','Generator ID','status_code','current_frozen_status','current_model_admitted','status_differs_from_frozen_annual',
        'summer_MW','winter_MW','nameplate_MW','source_workbook','source_sheet','source_excel_row','source_sha256','status_is_hourly_observed_availability']
    inventory[keep].to_csv(OUT/'StLawrence_inventory_status_by_month.csv',index=False)
    inventory_summary=[]
    for month,group in inventory.groupby('source_month',sort=True):
        eligible=group.status_code.isin(['OP','SB'])
        inventory_summary.append({'month':int(month),'units':len(group),'OP_SB_units':int(eligible.sum()),
            'out_of_service_units':';'.join(group.loc[~eligible,'Generator ID']),
            'all_unit_summer_MW':group.summer_MW.sum(),'OP_SB_summer_MW':group.loc[eligible,'summer_MW'].sum(),
            'OP_SB_nameplate_MW':group.loc[eligible,'nameplate_MW'].sum(),
            'unit_status_differences_from_frozen_annual':int(group.status_differs_from_frozen_annual.sum()),
            'aggregate_summer_change_from_current_model_MW':group.loc[eligible,'summer_MW'].sum()-802.5})
    pd.DataFrame(inventory_summary).to_csv(OUT/'StLawrence_inventory_monthly_summary.csv',index=False)

    prior=loadmat(prior_path,simplify_cells=True,variable_names=['prior_pg'])['prior_pg'][:,rows].sum(axis=1)/gamma
    plant_register=pd.read_csv(plant_register_path);early=pd.read_csv(early_eia_path)
    early=early.loc[early.plant_id.eq(2694)&early.prime_mover.eq('HY')].set_index('month')
    eia=pd.read_csv(final_eia_path);eia=eia.loc[eia.plant_id.eq(2694)&eia.prime_mover.eq('HY')].set_index('month')
    assert len(eia)==len(early)==12 and eia.respondent_frequency.eq('M').all()
    assert np.array_equal(eia.loc[range(1,13),'net_generation_mwh'],early.loc[range(1,13),'net_generation_mwh'])
    fuel=pd.read_csv(p63_path);fuel=fuel.loc[fuel.fuel_category.eq('Hydro')].sort_values('hour_index')
    assert np.array_equal(fuel.hour_index,balance.hour_index) and np.array_equal(fuel.timestamp_utc,balance.timestamp_utc)
    hydro=fuel.generation_mw.to_numpy();hydro_q=bools(fuel.coverage_qualified)
    shared=pd.read_csv(reconciliation_path).set_index('month')
    plant_prior=np.full(8760,np.nan);reconstructed=plant_prior.copy();EIA_mean=plant_prior.copy();baseline_target=plant_prior.copy()
    clipped_target=plant_prior.copy();low=plant_prior.copy();high=plant_prior.copy();below=np.zeros(8760,bool);monthly=[]
    max_plant_projection_error=0.;max_statewide_conservation=0.
    for month,path in enumerate(plant_prior_paths,1):
        d=np.load(path,allow_pickle=False);ix=d['hour_index']-1;assert np.array_equal(ix,np.flatnonzero(months==month))
        r=plant_register.loc[plant_register.month.eq(month)].sort_values('column_index');values=d['prior_actual_mw']
        assert values.shape==(len(ix),len(r))
        j=int(r.loc[r.plant_id.eq(2694)&r.prime_mover.eq('HY'),'column_index'].iloc[0])
        base=r.baseline_mw.to_numpy();capacity=r.capability_mw.to_numpy();clipped=np.minimum(base,capacity)
        total=clipped.sum();headroom=capacity.sum()-total;T=hydro[ix]
        below[ix]=T<=total
        lo=np.where(T<=total,clipped[j]*(T/total-1),0.)
        hi=np.where(T>total,(capacity[j]-clipped[j])*(T-total)/headroom,0.)
        p=clipped[j]+lo+hi;valid=hydro_q[ix]&np.isfinite(T)
        assert np.isfinite(values[valid]).all()
        max_plant_projection_error=max(max_plant_projection_error,float(np.max(abs(p[valid]-values[valid,j]))))
        max_statewide_conservation=max(max_statewide_conservation,float(np.max(abs(values[valid].sum(axis=1)-T[valid]))))
        plant_prior[ix]=values[:,j];reconstructed[ix]=np.where(valid,p,np.nan)
        low[ix]=np.where(valid,lo,np.nan);high[ix]=np.where(valid,hi,np.nan)
        baseline_target[ix]=base[j];clipped_target[ix]=clipped[j]
        energy=float(eia.loc[month,'net_generation_mwh']);mu=energy/len(ix);EIA_mean[ix]=mu
        use=ix[q[ix]];available=ix[np.isfinite(current[ix])];pv=ix[np.isfinite(prior[ix])]
        assert len(use)>0 and np.isfinite(prior[use]).all()
        maximum_missing_energy=float(nominal_cap[ix[~q[ix]]].sum())
        known=float(current[use].sum());full_upper=known+maximum_missing_energy
        dispatch_delta=float((current[use]-prior[use]).mean())
        decomposition=mu+(base[j]-mu)+(clipped[j]-base[j])+float(low[use].mean())+float(high[use].mean())+dispatch_delta
        assert abs(decomposition-current[use].mean())<1e-8
        row={'month':month,'physical_calendar_hours':len(ix),'qualified_hours':len(use),'unmodeled_source_hours':len(ix)-len(use),
            'current_profile_finite_hours':len(available),'frozen_prior_finite_hours':len(pv),'P63_hydro_source_qualified_hours':int(valid.sum()),
            'EIA_final_net_generation_MWh':energy,'EIA_early_to_final_difference_MWh':energy-float(early.loc[month,'net_generation_mwh']),
            'EIA_full_physical_calendar_mean_MW':mu,'frozen_EIA_baseline_mean_MW':base[j],
            'frozen_mean_denominator_hours':energy/base[j], 'calendar_denominator_effect_MW':base[j]-mu,
            'frozen_StL_plant_cap_MW':capacity[j],'all_hours_at_current_cap_energy_MWh':float(nominal_cap[ix].sum()),
            'EIA_energy_above_all_hours_at_current_cap_MWh':max(0.,energy-float(nominal_cap[ix].sum())),
            'cap_clipping_contribution_to_prior_mean_MW':clipped[j]-base[j],
            'below_baseline_P63_contribution_to_prior_mean_MW':float(low[use].mean()),
            'above_baseline_P63_contribution_to_prior_mean_MW':float(high[use].mean()),
            'qualified_hours_below_statewide_clipped_baseline':int(below[use].sum()),
            'frozen_prior_qualified_mean_MW':float(prior[use].mean()),'current_dispatch_qualified_mean_MW':float(current[use].mean()),
            'final_dispatch_minus_prior_mean_MW':dispatch_delta,'current_dispatch_qualified_energy_MWh':known,
            'EIA_mean_transferred_to_qualified_cohort_target_MWh':mu*len(use),
            'EIA_mean_minus_current_qualified_mean_MW':mu-float(current[use].mean()),
            'unmodeled_hours_max_energy_under_current_cap_MWh':maximum_missing_energy,
            'full_month_completion_upper_bound_holding_qualified_dispatch_MWh':full_upper,
            'EIA_energy_above_that_completion_upper_bound_MWh':max(0.,energy-full_upper),
            'current_qualified_hours_at_upper_bound':int(np.sum(current[use]>=cap[use]-1e-7)),
            'current_profile_finite_energy_MWh':float(current[available].sum()),
            'P63_Hydro_mean_on_current_qualified_hours_MW':float(hydro[use].mean()),
            'P63_Hydro_mean_on_its_source_qualified_hours_MW':float(T[valid].mean()),
            'frozen_plant_baseline_sum_MW':float(base.sum()),'frozen_clipped_plant_baseline_sum_MW':float(total),
            'final_EIA_NY_HY_mean_on_frozen_denominator_MW':float(shared.loc[month,'final_EIA_NY_HY_net_mean_mw']),
            'final_EIA_NYIS_HY_mean_on_frozen_denominator_MW':float(shared.loc[month,'final_EIA_NYIS_HY_net_mean_mw']),
            'monthly_energy_constraint_enforced_by_current_projection':False,
            'oracle_StL_mean_if_other_inputs_and_terminal_correct_MW':float(balance.oracle_StLawrence_hold_other_inputs_and_terminal_MW.to_numpy()[use].mean()),
            'Moses_primary_bias_on_same_cohort_MW':float(balance.residual_primary_MW.to_numpy()[use].mean())}
        monthly.append(row)
    assert max_plant_projection_error<1e-8 and max_statewide_conservation<1e-7
    valid_prior=np.isfinite(prior)&np.isfinite(plant_prior)
    max_fleet_partition_difference=float(np.max(abs(prior[valid_prior]-plant_prior[valid_prior])))
    assert max_fleet_partition_difference<1e-8
    monthly=pd.DataFrame(monthly);monthly.to_csv(OUT/'StLawrence_monthly_source_energy_and_allocation.csv',index=False)
    hourly=balance[['hour_index','timestamp_utc','month_local','qualified']].copy()
    for name,value in {'current_StL_PG_MW':current,'frozen_StL_prior_MW':prior,'saved_plant_prior_MW':plant_prior,
        'independently_reconstructed_plant_prior_MW':reconstructed,'current_StL_Pmax_MW':cap,'P63_Hydro_MW':hydro,
        'EIA_full_month_mean_MW':EIA_mean,'frozen_month_baseline_MW':baseline_target,'clipped_month_baseline_MW':clipped_target,
        'low_P63_projection_contribution_MW':low,'high_P63_projection_contribution_MW':high,
        'current_minus_frozen_prior_MW':current-prior}.items():hourly[name]=value
    hourly.to_csv(OUT/'StLawrence_hourly_source_trace.csv',index=False)

    # Targets use only independent EIA monthly energy, current source-derived
    # generation, the frozen source mask, and calendar identity. P32 is used
    # below only for post-hoc error scoring and the explicitly labeled oracle.
    plans={'baseline':{'formula':'Current StLawrence source-derived PG; unchanged.'},
        'EIA_month_mean_preserve_qualified_shape':{'formula':'PG(h)+EIA_month_MWh/full_physical_month_hours-mean(PG on qualified month hours).'},
        'EIA_month_constant':{'formula':'EIA_month_MWh/full_physical_month_hours at each qualified hour; illustrative constant, not measured hourly output.'},
        'current_month_mean_constant_shape_ablation':{'formula':'Mean(currentPG on qualified month hours) at each qualified hour; preserves current qualified-month energy, not an EIA source correction.'}}
    plan={'scope':'Conditional single-component algebra; no AC solve or global fuel conservation adjustment.',
        'selection':'Explicit requested mean/shape contrasts; no fitted coefficient or scenario selected by residual score.',
        'initial_readonly_diagnostic_results_seen_before_receipt':True,'target_construction_uses_P32_values':False,
        'cohort_hours':8651,'full_calendar_hours':8760,'unmodeled_hours':109,'cohort_representativeness_assumption':
        'Applying a full-calendar EIA mean to qualified hours assumes their mean is representative; no full-month generated-energy claim.',
        'held_fixed':['other_D_native_PG','HQ','PAR1','PAR2','gross_D_load','primary_minus_midpoint_terminal_correction'],
        'cases':plans,'P63_Hydro_conservation_repaired':False,'finite_capability_feasibility_not_claimed':True,'default_model_changed':False}
    plan_path=OUT/'conditional_generation_plan.json';plan_path.write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
    variants={name:np.full(8760,np.nan) for name in plans};variants['baseline'][q]=current[q]
    for month in range(1,13):
        ix=q&(months==month);mean=float(current[ix].mean());mu=float(EIA_mean[ix][0])
        variants['EIA_month_mean_preserve_qualified_shape'][ix]=current[ix]+mu-mean
        variants['EIA_month_constant'][ix]=mu;variants['current_month_mean_constant_shape_ablation'][ix]=mean
        assert abs(variants['EIA_month_mean_preserve_qualified_shape'][ix].mean()-mu)<1e-9
        assert abs(variants['current_month_mean_constant_shape_ablation'][ix].sum()-current[ix].sum())<1e-7
    baseline=balance.primary_Moses_MW.to_numpy();observed=balance.observed_Moses_MW.to_numpy()
    scores=[];predictions={}
    for name,values in variants.items():
        pred=baseline+values-current;pred[~q]=np.nan;predictions[name]=pred
        for month in range(13):
            ix=q if month==0 else q&(months==month);stats=error_stats(pred[ix],observed[ix]);base_stats=error_stats(baseline[ix],observed[ix])
            scores.append({'scenario':name,'month':month,**stats,'MAE_change_from_baseline_MW':stats['MAE_public_MW']-base_stats['MAE_public_MW'],
                'StLawrence_mean_MW':float(values[ix].mean()),'StLawrence_mean_change_MW':float((values[ix]-current[ix]).mean()),
                'StLawrence_above_frozen_Pmax_hours':int((values[ix]>cap[ix]+1e-7).sum()),
                'StLawrence_below_frozen_Pmin_hours':int((values[ix]<-1e-7).sum()),
                'maximum_upper_bound_violation_MW':float(np.maximum(0,values[ix]-cap[ix]).max()),
                'AC_or_global_dispatch_feasibility_claimed':False,'hourly_generation_observed':False,'cohort_unchanged':True})
    scores=pd.DataFrame(scores);scores.to_csv(OUT/'conditional_generation_scores.csv',index=False)
    np.savez_compressed(OUT/'conditional_generation_variants.npz',hour_index=balance.hour_index.to_numpy(),timestamp_utc=balance.timestamp_utc.to_numpy(str),
        qualified=q,scenario_names=np.asarray(list(variants)),StLawrence_PG_MW=np.stack(list(variants.values())),
        conditional_Moses_MW=np.stack(list(predictions.values())),observed_Moses_MW=observed,
        actual_AC_replay=False,other_components_and_terminal_effect_held=True)

    nypa=json.loads(nypa_path.read_text());nypa_row=[r for r in nypa if r['year']=='2025' and r['nypa_facility_name']=='ST. LAWRENCE'];assert len(nypa_row)==1
    nypa_energy=float(nypa_row[0]['net_generation_mwh']);eia_energy=float(eia.net_generation_mwh.sum())
    known=float(current[q].sum());missing_upper=float(nominal_cap[~q].sum());finite=np.isfinite(current)
    annual={'EIA_final_full_year_net_MWh':eia_energy,'NYPA_official_OpenNY_full_year_net_MWh':nypa_energy,
        'NYPA_minus_EIA_MWh':nypa_energy-eia_energy,'NYPA_minus_EIA_percent_of_EIA':100*(nypa_energy-eia_energy)/eia_energy,
        'qualified_model_hours':int(q.sum()),'unmodeled_hours':int((~q).sum()),'known_qualified_model_energy_MWh':known,
        'maximum_unmodeled_energy_at_frozen_cap_MWh':missing_upper,
        'full_year_completion_upper_bound_holding_qualified_model_MWh':known+missing_upper,
        'minimum_EIA_gap_after_allowing_missing_hours_at_cap_MWh':eia_energy-known-missing_upper,
        'minimum_EIA_gap_after_missing_hours_percent':100*(eia_energy-known-missing_upper)/eia_energy,
        'current_profile_finite_hours':int(finite.sum()),'current_profile_known_energy_MWh':float(current[finite].sum()),
        'current_profile_all_missing_completion_upper_bound_MWh':float(current[finite].sum()+nominal_cap[~finite].sum()),
        'missing_hour_bound_uses_full_nominal_admitted_cap_even_where_available_cap_metadata_is_missing':True,
        'frozen_prior_finite_hours':int(np.isfinite(prior).sum()),'current_qualified_mean_MW':float(current[q].mean()),
        'frozen_prior_qualified_mean_MW':float(prior[q].mean()),'current_minus_prior_qualified_mean_MW':float((current[q]-prior[q]).mean()),
        'current_minus_prior_mean_absolute_MW':float(abs(current[q]-prior[q]).mean()),
        'current_at_cap_qualified_hours':int((current[q]>=cap[q]-1e-7).sum()),
        'calendar_denominator_mean_effect_MW':float((baseline_target[q]-EIA_mean[q]).mean()),
        'cap_clipping_mean_effect_MW':float((clipped_target[q]-baseline_target[q]).mean()),
        'below_P63_mean_effect_MW':float(low[q].mean()),'above_P63_mean_effect_MW':float(high[q].mean()),
        'qualified_hours_below_statewide_clipped_baseline':int(below[q].sum()),
        'oracle_StL_qualified_mean_if_all_other_terms_correct_MW':float(balance.oracle_StLawrence_hold_other_inputs_and_terminal_MW.to_numpy()[q].mean())}
    (OUT/'StLawrence_annual_energy_bounds.json').write_text(json.dumps(annual,indent=2)+'\n',encoding='utf-8')
    after=[record(p) for p in paths];assert before==after
    outputs=['StLawrence_frozen_unit_scope.csv','StLawrence_inventory_status_by_month.csv','StLawrence_inventory_monthly_summary.csv',
        'StLawrence_monthly_source_energy_and_allocation.csv','StLawrence_hourly_source_trace.csv','conditional_generation_plan.json',
        'conditional_generation_scores.csv','conditional_generation_variants.npz','StLawrence_annual_energy_bounds.json']
    receipt={'passed':True,'created_utc':datetime.now(timezone.utc).isoformat(),'HEAD':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'baseline_model':'Repaired2025 model; original source profiles unchanged','plant_id':2694,'current_native_generator_rows_1based':(rows+1).tolist(),
        'source_fullcalendar_hours':8760,'qualified_cohort_hours':8651,'EIA_plant_months':12,'monthly_inventory_snapshots':12,
        'early_vs_final_EIA860_plant_status_capability_identical':True,'early_vs_final_EIA923_plant_month_energy_identical':True,
        'monthly_inventory_status_disagreements_with_annual_freeze':int(inventory.loc[inventory.source_month.gt(0),'status_differs_from_frozen_annual'].sum()),
        'monthly_inventory_changes_aggregate_stlawrence_seasonal_capability':False,
        'EIA_month_energy_incompatible_with_current_hourly_cap_months':monthly.loc[monthly.EIA_energy_above_all_hours_at_current_cap_MWh.gt(1e-6),'month'].tolist(),
        'maximum_independent_P63_plant_projection_reproduction_error_MW':max_plant_projection_error,
        'maximum_independent_statewide_Hydro_conservation_error_MW':max_statewide_conservation,
        'maximum_saved_plant_prior_vs_unit_prior_aggregate_difference_MW':max_fleet_partition_difference,
        'monthly_plant_energy_preserved_by_frozen_P63_projection':False,'annual_energy_bounds':annual,
        'conditional_annual_scores':scores.loc[scores.month.eq(0)].to_dict('records'),
        'scope_conclusions':[
            'The aggregate802.5MW cap comes from15eligible units at53.5MW seasonal capability; finalannual inventory does not fix it.',
            'Monthly inventories swap the excluded unit from26 to21 afterFebruary, while aggregate seasonal capability remains802.5MW.',
            'April-July EIA monthly energy cannot be generated under an802.5MW hard hourly ceiling; this is a capability-interpretation conflict, not proof the16th unit was available.',
            'The main current monthly-energy suppression is already present in the P63-constrained plant prior; final dispatch changes the plant mean only slightly.',
            'Neither EIA monthly-mean diagnostic improves annual Moses MAE. The shape-only control improves conditional MAE but is not observed plant output or a source-validated correction.',
            'Other D native allocation, HQ/PAR sources, load boundary and interface-meter scope can offset or confound a missing StLawrence energy component; one residual cannot identify it.'],
        'new_PF_or_optimization_run':False,'default_model_changed':False,'no_source_files_mutated':True,
        'raw_national_workbook_cache_required_for_this_analysis':False,'authenticated_plant_extract_required':True,
        'limitations':['Full-calendar EIA means transferred to the qualified subset require a representative-missing-hours assumption.',
            'Energy bounds use the frozen model cap only; seasonal/net/nameplate/dependable ratings are not interchangeable physical hourly maxima.',
            'Conditional generation variants hold terminal loss corrections fixed and do not rebalance statewide Hydro or other generation.',
            'No verified public2025 StLawrence hourly electrical-output series is asserted.'],
        'sources':before,'outputs':[record(OUT/name) for name in outputs],'producer':record(Path(__file__))}
    (OUT/'generation_audit_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'source_hours':8651,'cap_conflict_months':receipt['EIA_month_energy_incompatible_with_current_hourly_cap_months'],
        'projection_error_MW':max_plant_projection_error,'minimum_unexplained_full_year_energy_gap_MWh':annual['minimum_EIA_gap_after_allowing_missing_hours_at_cap_MWh']}))
    print(scores.loc[scores.month.eq(0),['scenario','hours','MAE_public_MW','WAPE_percent','bias_public_MW','StLawrence_above_frozen_Pmax_hours']].to_string(index=False))


if __name__=='__main__':main()
