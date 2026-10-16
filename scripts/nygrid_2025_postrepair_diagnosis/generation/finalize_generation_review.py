"""Seal primary-source generation availability and current spatial-prior diagnosis."""
from pathlib import Path
from datetime import datetime,timezone
import csv,hashlib,json,re
import pandas as pd
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'output/nygrid_2025_postrepair_diagnosis/generation';S=OUT/'sources'
def rec(p):return dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
def main():
 rows=[
  dict(dataset='NYISO P63 Real-Time Fuel Mix',grain='Timestamp x statewide fuel category',time_resolution='Nominal five minutes; irregular additional intervals occur',history='Public index includes Dec2015 onward and every2025 monthly archive',plant_identification='No plant, generator or PTID field',access='Public daily CSV and monthly ZIP',usefulness='Observed statewide Hydro/Wind totals; cannot identify StLawrence or spatial plant dispatch',url='https://mis.nyiso.com/public/P-63list.htm',evidence='P63_schema_cadence_review.json;sources/NYISO_P63_index.html'),
  dict(dataset='NYISO Gold Book existing generating facilities',grain='Named generator or fleet row; some annual energy is grouped',time_resolution='Annual prior-year net energy; seasonal capability and annual inventory snapshot',history='Verified2025 edition reports2024 net energy and March2025 resource inventory',plant_identification='Yes, at listed resource or grouped fleet grain',access='Public PDF',usefulness='StLawrenceFDR fleet PTID23600:2024 net energy7355.0GWh; capacity context; not2025 hourly output',url='https://www.nyiso.com/documents/20142/2226333/2025-Gold-Book-Public.pdf',evidence='sources/NYISO_2025_GoldBook.pdf;TableIII-2a printed84/PDF88'),
  dict(dataset='NYISO Gold Book annual zonal energy',grain='Zone x generator type',time_resolution='Annual',history='Verified2025 edition TableIII-3c covers2024',plant_identification='No individual plant in this table',access='Public PDF',usefulness='Independent zonal annual generation summary, but year must match study',url='https://www.nyiso.com/documents/20142/2226333/2025-Gold-Book-Public.pdf',evidence='sources/NYISO_2025_GoldBook.pdf;TableIII-3c printed104/PDF108'),
  dict(dataset='NYISO P19 Generator Names',grain='Named resource/PTID with zone and location fields',time_resolution='Reference list',history='Live list inspected',plant_identification='Yes',access='Public CSV/HTML/PDF',usefulness='Identity and zone crosswalk only; no generatedMW/MWh',url='https://mis.nyiso.com/public/P-19list.htm',evidence='sources/NYISO_P19_generator_names.html'),
  dict(dataset='NYISO P2B/P24B/P4B generator LBMP',grain='Timestamp x named generator pricing node/PTID',time_resolution='Day-ahead hourly, real-time nominal5min, integrated hourly',history='Public daily files and archives; sample2026-10-12 inspected',plant_identification='Yes for price node',access='Public',usefulness='Prices in dollars/MWh, not generator electrical output',url='https://mis.nyiso.com/public/P-4Blist.htm',evidence='sources/NYISO_P4B_generator_LBMP.csv'),
  dict(dataset='NYISO P27 delayed bid release',grain='Masked generator/bidder x bid record',time_resolution='Time-stamped offers and commitment parameters; monthly publication after three-month lag',history='Index includes all2025 months and older history',plant_identification='Generator and bidder identities deliberately masked; trackable pseudonyms',access='Public monthly ZIP',usefulness='Offer curves/commitment parameters, not named actual metered dispatch; DispatchMW1-12 are bid points',url='https://mis.nyiso.com/public/P-27list.htm',evidence='sources/NYISO_P27_masked_bid_description.pdf'),
  dict(dataset='NYISO participant posted schedules',grain='Resource/participant schedule',time_resolution='Day-ahead/real-time schedule intervals',history='Access controlled by entitlement',plant_identification='Entitled participants can view their schedules',access='Private to authorized registered participants',usefulness='Detailed schedules exist but are not an unrestricted public plant-output feed',url='https://www.nyiso.com/documents/20142/2923301/dayahd_schd_mnl.pdf/0024bc71-4dd9-fa80-a816-f9f3e26ea53a',evidence='sources/NYISO_DayAheadSchedulingManual.pdf;Sections3.2 printed12-13'),
  dict(dataset='NYISO P30 DAM daily energy report',grain='NYCA aggregate market categories',time_resolution='Daily summary with hourly aggregate detail',history='Public daily and monthly archives including2025',plant_identification='No named plant output',access='Public',usefulness='Offered/scheduled market energy; virtual supply explicitly distinct from physical production',url='https://mis.nyiso.com/public/P-30list.htm',evidence='sources/NYISO_P30_DAM_energy_report.html'),
  dict(dataset='NYISO P15 generation maintenance',grain='Date x NYCA forecast outage MW',time_resolution='Daily forecast',history='Current public report inspected',plant_identification='No unit or plant field in current CSV',access='Public',usefulness='Aggregate outage context; cannot establish StLawrence unit outages',url='https://mis.nyiso.com/public/P-15list.htm',evidence='sources/NYISO_P15_generation_maintenance.csv'),
  dict(dataset='NYISO P61 economic dispatch analysis',grain='Aggregated above/below ideal dispatch chart',time_resolution='Historical daily charts',history='Inspected index lists Jul2004-Jan2005 archives',plant_identification='No named hourly meter series in report description',access='Public historical charts',usefulness='Not a2025 StLawrence generation source',url='https://mis.nyiso.com/public/P-61list.htm',evidence='sources/NYISO_P61_index.html'),
  dict(dataset='EIA923 final2025 generation (complementary source)',grain='Plant x prime mover/fuel x month; respondent frequency matters',time_resolution='Monthly generation values: M submitted monthly; AM submitted once annually',history='Frozen final2025 workbook verified by hash',plant_identification='Yes, stable EIA plantID',access='Public',usefulness='Observed annual plant energy and monthly StLawrence totals; no hourly net output',url='https://www.eia.gov/electricity/data/eia923/',evidence='sources/EIA923_official_index.html;D_wind_final_EIA923_source_rows.csv'),
 ]
 pd.DataFrame(rows).to_csv(OUT/'generation_data_availability.csv',index=False)
 mapping={56618:(323605,'Clinton Wind Power'),56619:(323604,'Ellenburg Wind Power'),56857:(323696,'Marble River Wind'),56901:(323606,'Altona Wind Power'),56904:(323614,'Chateaugay Wind Power'),59629:(323719,'Jericho Rise Wind Farm')}
 reg=pd.read_csv(ROOT/'output/nygrid_2025_moses_repair/model/model_generator_register.csv');fleet=pd.read_csv(ROOT/'output/nygrid_2025_western_audit/corrected/fleet_register.csv');eia=pd.read_csv(OUT/'D_wind_final_EIA923_source_rows.csv')
 public=BeautifulSoup((S/'NYISO_P19_generator_names.html').read_text(),'html.parser');book=(S/'NYISO_2025_GoldBook.txt').read_text(encoding='utf-8');cross=[]
 for pid,(ptid,name) in mapping.items():
  rr=reg.loc[reg.plant_id.eq(pid)];assert len(rr)==1 and rr.zone.iloc[0]=='D' and rr.role.iloc[0]=='native'
  fr=fleet.loc[fleet.device_key.eq(rr.device_key.iloc[0])];assert len(fr)==1
  src=eia.loc[eia.plant_id.eq(pid)];assert len(src)==12 and src.balancing_authority.eq('NYIS').all()
  booklines=[line for line in book.splitlines() if name in line and re.search(r'\bD\s+'+str(ptid)+r'\b',line)];assert len(booklines)==1
  prows=[tr.get_text(' ',strip=True) for tr in public.find_all('tr') if any(td.get_text(strip=True)==str(ptid) for td in tr.find_all('td'))];assert len(prows)==1 and 'NORTH' in prows[0]
  cross.append(dict(EIA_plant_id=pid,EIA_plant_name=src.plant_name.iloc[0],EIA923_balancing_authority='NYIS',EIA860_balancing_authority=fr.balancing_authority_code.iloc[0],
   respondent_frequency=src.respondent_frequency.iloc[0],model_gen_row=int(rr.gen_row.iloc[0]),model_bus_id=int(rr.bus_id.iloc[0]),model_zone='D',NYISO_PTID=ptid,NYISO_name=name,NYISO_GoldBook_zone='D',
   EIA860_nameplate_MW=float(fr.nameplate_capacity_mw.iloc[0]),GoldBook_source_line=booklines[0],P19_source_row=prows[0],
   identity_crosswalk_basis='EIA plant/device row identity and corresponding named GoldBook/P19 resource, zone, and nameplate; modeled electrical landing remains an aggregate bus proxy.'))
 pd.DataFrame(cross).to_csv(OUT/'D_wind_asset_source_crosswalk.csv',index=False)
 wind=json.loads((OUT/'D_wind_source_energy_review.json').read_text());hy=json.loads((OUT/'D_HY_source_energy_review.json').read_text());shape=json.loads((OUT/'monthly_flat_control_receipt.json').read_text());ac=json.loads((OUT/'shape_ac/monthly_flat_AC_receipt.json').read_text())
 report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),headline='NYISO publishes generation data, but inspected public products do not provide named StLawrence hourly metered generation.',
  data_catalog=rows,NYISO_2026_GoldBook_check=dict(official_catalog='https://www.nyiso.com/load-capacity-data-report-gold-book-',catalog_found_from_official_system_outlook=True,
   catalog_HTML_cached=True,dynamic_public_listing_attempt_HTTP_status=500,exact2026_document_located=False,unavailability_or_nonexistence_claimed=False,
   conclusion='No2026file was verified through current catalog/search; only2025edition is used. This is a retrieval limitation, not a claim that2026does not exist.'),
  public_named_StLawrence_hourly_generation_found=False,universal_absence_claimed=False,
  named_generation_nuance='GoldBook has named generator/fleet annual net energy; StLawrence is a fleet aggregate and its2025edition energy is2024, not2025.',
  source_supported_remaining_driver=dict(kind='ZoneD wind spatial allocation inconsistent with final annual plant energy',qualified_model_energy_MWh=wind['current_qualified_total_MWh'],
   entire_year_EIA_energy_MWh=wind['EIA_2025_total_MWh'],qualified_energy_excess_MWh=wind['robust_qualified_energy_excess_MWh'],
   qualified_mean_overallocation_lower_bound_MW=wind['robust_qualified_mean_overallocation_lower_bound_public_MW'],
   condition_for_qualified_lower_bound=wind['condition_for_qualified_lower_bound'],
   excluded_net_energy_required_if_qualified_model_is_actual_MWh=wind['excluded_net_energy_required_if_qualified_model_is_actual_MWh'],
   excluded_mean_net_power_required_if_qualified_model_is_actual_MW=wind['excluded_mean_net_power_required_if_qualified_model_is_actual_MW'],
   actual_negative_auxiliary_power_bound_established=False,frequency_sources=wind['frequency_sources'],
   mechanism='The existing prior allocates the statewide wind signal using active nameplate shares and the same capacity factor at every site. Plant-specific annual energy and weather or curtailment are not imposed.',
   causal_limit='The energy excess is established. Its exact contribution to Moses error is conditional on northern load/boundary/operator correctness; no wind repair or causal intervention is performed.',
   annual_EIA_equal_sum_months=wind['annual_reported_equals_sum_of_months'],plants=wind['plants'],source_crosswalk=rec(OUT/'D_wind_asset_source_crosswalk.csv'),
   AM_monthly_caveat='Four plants have raw code AM and supply monthly generation values once annually; Marble River and Jericho Rise have code M and report monthly. AM is not annual-total monthly imputation. Neither reporting frequency establishes hourly telemetry.',
   code_citations=wind['mechanism_code_citations']),
  other_D_HY_summary=hy['nonStL_D_HY'],shape_control_summary={k:shape[k] for k in ['qualified_StL_delta','qualified_native_D_delta','monthly_energy_error_MWh','hourly_HY_total_error_public_MW','current_cap_hours_qualified']},
  shape_AC_summary={k:ac[k] for k in ['passed','hours','sample_current_Moses_MAE_public_MW','sample_control_Moses_MAE_public_MW','maximum_cut_closure_error_public_MW','maximum_terminal_correction_delta_public_MW']},
  model_map_package_unchanged=True,no_wind_projection=True,
  receipt_files=[rec(OUT/n) for n in ['official_source_cache_receipt.json','P63_schema_cadence_review.json','D_wind_source_energy_review.json','D_HY_source_energy_review.json','monthly_flat_control_receipt.json','shape_ac/monthly_flat_AC_receipt.json']],
  source_download_receipts=[json.loads(p.read_text()) for p in sorted(S.glob('*.receipt.json'))])
 (OUT/'generation_source_review.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(passed=True,catalog_rows=len(rows),wind_asset_crosswalk_rows=len(cross),qualified_wind_overallocation_lower_bound_MW=wind['robust_qualified_mean_overallocation_lower_bound_public_MW'],outputs=[rec(OUT/n) for n in ['generation_data_availability.csv','D_wind_asset_source_crosswalk.csv','generation_source_review.json']]),indent=2))
if __name__=='__main__':main()
