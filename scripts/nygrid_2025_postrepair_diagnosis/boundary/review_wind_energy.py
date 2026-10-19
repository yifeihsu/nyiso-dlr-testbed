"""Independent compiled-wind/annual-EIA energy check; no reconstruction change."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_postrepair_diagnosis/boundary'
REPAIR=ROOT/'output/nygrid_2025_moses_repair'
DEPS={}


def sha(p):
    with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read(p):
    p=Path(p);DEPS[p.relative_to(ROOT).as_posix()]=sha(p);return p


def main():
    workbook=json.loads(read(OUT/'independent_wind_workbook_readback.json').read_text())
    assert sha(read(ROOT/workbook['workbook']))==workbook['workbook_sha256']
    source={int(r['plant_id']):r for r in workbook['source_rows']}
    registry=pd.read_csv(read(REPAIR/'model/model_generator_register.csv'))
    selected=registry[registry.role.eq('native')&registry.zone.eq('D')&registry.fuel_category.eq('Wind')].copy()
    assert len(selected)==6 and selected.plant_id.is_unique and set(selected.plant_id.astype(int))==set(source)
    ids=selected.gen_row.to_numpy(int)-1
    model=loadmat(read(REPAIR/'model/latest_model.mat'),simplify_cells=True)['model']
    q=np.asarray(model['axis']['source_qualified'],bool);gamma=float(model['scale_factor_gamma'])
    assert q.sum()==8651 and len(q)==8760 and np.all(np.asarray(model['generator_bus_ids'])[ids]==49)
    assert not np.asarray(model['external']['generator_mask'],bool)[ids].any()
    for template,policy in zip(model['templates'],model['loss_static']):
        lookup=dict(zip(template['bus'][:,0].astype(int),np.asarray(policy['bus_group'],int)))
        assert lookup[49]==4
    pg=np.empty((8760,6))
    for si,item in enumerate(model['profile_shards']):
        new=loadmat(read(REPAIR/'model'/item['name']),simplify_cells=True)['profiles']['generator_PG_MW'][:,ids]
        old=loadmat(read(ROOT/'output/nygrid_2025_physical_repair/model'/item['name']),simplify_cells=True)['profiles']['generator_PG_MW'][:,ids]
        assert np.array_equal(new,old,equal_nan=True),'Wind changed in Moses repair'
        pg[si*4380:(si+1)*4380]=new/gamma
    assert np.isfinite(pg[q]).all() and (pg[q]>=0).all()
    bounds=np.load(read(ROOT/'output/nygrid_2025_dispatch/fleet/fleet_bounds.npz'))
    index={int(fid):j for j,fid in enumerate(bounds['fleet_id'])};cols=[index[int(fid)]for fid in selected.fleet_id]
    lower=bounds['pmin_actual_mw'][:,cols];upper=bounds['pmax_actual_mw'][:,cols]
    assert np.all(lower[~q]==0)
    table=[]
    for j,row in enumerate(selected.itertuples(index=False)):
        src=source[int(row.plant_id)];known=float(pg[q,j].sum());low=known+float(lower[~q,j].sum());high=known+float(upper[~q,j].sum());energy=src['annual_MWh']
        table.append(dict(plant_id=int(row.plant_id),model_gen_row_1based=int(row.gen_row),device_key=row.device_key,
            model_bus=49,model_zone='D',mapping_method=row.mapping_method,respondent_frequency=src['respondent_frequency'],
            source_excel_row=src['source_excel_row'],annual_source_cell=src['annual_source_cell'],EIA_annual_MWh=energy,
            compiled_qualified_MWh=known,excluded_hours=int((~q).sum()),annual_interval_low_MWh=low,
            annual_interval_high_MWh=high,annual_interval_compatible=bool(low-1e-6<=energy<=high+1e-6),
            annual_interval_distance_MWh=max(0.,low-energy,energy-high)))
    independent=pd.DataFrame(table)
    published=pd.read_csv(read(ROOT/'output/nygrid_2025_postrepair_diagnosis/generation/D_wind_annual_EIA_comparison.csv')).set_index('plant_id')
    assert published.months_included.eq(12).all() and 'month' not in published
    errors=[]
    for row in independent.itertuples(index=False):
        actual=[row.EIA_annual_MWh,row.compiled_qualified_MWh,row.annual_interval_low_MWh,row.annual_interval_high_MWh,row.annual_interval_distance_MWh]
        fields=['EIA_net_generation_MWh','current_qualified_MWh','qualified_plus_excluded_min_MWh','qualified_plus_excluded_max_MWh','minimum_unexplained_source_difference_MWh']
        saved=published.loc[row.plant_id,fields].to_numpy(float)
        error=float(np.max(abs(np.asarray(actual)-saved)));assert error<1e-7;errors.append(error)
        assert bool(published.loc[row.plant_id,'EIA_within_excluded_hour_bounds'])==row.annual_interval_compatible
    independent.to_csv(OUT/'independent_wind_annual_readback.csv',index=False,lineterminator='\n')
    known=float(pg[q].sum());annual=sum(r['annual_MWh']for r in source.values());excess=known-annual
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        source_workbook_sha256=workbook['workbook_sha256'],plants=6,model_rows_1based=(ids+1).tolist(),
        exact_plant_fuel_WND_prime_mover_WT_state_NY_BA_NYIS_year2025_matching=True,
        map_scope='All six are current native ZoneD records at the Plattsburgh49 geographic proxy. This checks the model mapping, not a physical generator-to-feeder or Moses-meter certificate.',
        reporting_frequency_counts=independent.respondent_frequency.value_counts().to_dict(),
        frequency_interpretation='M reports monthly. AM supplies monthly values via an annual submission; AM must not be equated with annual-total monthly imputation. This does not establish hourly telemetry.',
        frequency_primary_context='EIA923 instructions Schedule3D printedpage16 requires renewable annual respondents to report each month and permits negative net generation; PUDL maintainer code separately defines AM as monthly values submitted once annually.',
        frequency_sources=['https://www.eia.gov/survey/form/eia_923/instructions.pdf','https://docs.catalyst.coop/pudl/en/v2026.2.0/_modules/pudl/metadata/codes.html'],
        model_hours=8760,qualified_hours=int(q.sum()),excluded_hours=int((~q).sum()),
        current_qualified_wind_MWh=known,reported_annual_wind_MWh=annual,
        qualified_energy_minus_reported_annual_MWh=excess,
        conditional_qualified_mean_excess_lower_bound_MW=excess/q.sum(),
        condition_for_that_lower_bound='Actual net generation on all109excludedhours is nonnegative. This follows the current modeling envelope, not an EIA rule: EIA allows negative net generation from station use.',
        excluded_energy_required_if_qualified_model_were_actual_MWh=annual-known,
        mean_excluded_power_required_if_qualified_model_were_actual_MW=(annual-known)/(~q).sum(),
        bound_on_actual_negative_auxiliary_power_established=False,source_based_Moses_causal_contribution_identified=False,
        wind_input_preexisted_latest_repair=True,corrected_annual_interval_table_max_difference_MWh=max(errors),
        earlier_annual_derived_field_aggregation_issue_resolved=True,
        public_scale_conversion='Compiled model MW divided once by gamma; sum one-hour power values toMWh.',
        primary_source_units='EIA worksheet reports electricity net generation inMWh, with an annual NetGeneration(Megawatthours) column; all six annual totals equal the sum of their12monthlycells.',
        default_model_map_package_changed=False,new_AC_power_flows=0,
        inputs=[dict(path=p,sha256=h)for p,h in DEPS.items()],script_sha256=sha(Path(__file__)))
    assert all(sha(ROOT/p)==h for p,h in DEPS.items())
    (OUT/'independent_wind_review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k]for k in ['passed','reporting_frequency_counts','current_qualified_wind_MWh','reported_annual_wind_MWh','qualified_energy_minus_reported_annual_MWh','conditional_qualified_mean_excess_lower_bound_MW','mean_excluded_power_required_if_qualified_model_were_actual_MW','corrected_annual_interval_table_max_difference_MWh']},indent=2))


if __name__=='__main__':main()
