"""Independent public nonfossil priors for registered NY research snapshots.

Only registered timestamps and the fixed MW scale are consumed from the existing
campaign. No internal interface values, model flows, or fitted participation are
read. P63 is statewide observed data; geographic allocations are estimates.
Run with Python + openpyxl. Original downloads are cached and SHA256 registered.
"""
from __future__ import annotations

import argparse
import calendar
from collections import defaultdict
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import html
import io
import json
import math
from pathlib import Path
import re
import urllib.request
import zipfile

import openpyxl

ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / 'output/compact_ny_2025/generation_sources/nonfossil'
DEFAULT_CACHE = ROOT / 'tmp/nonfossil_sources'
GOLD_URL = 'https://www.nyiso.com/documents/20142/2226333/2025-Gold-Book-Public.pdf/088438e1-02f1-5316-211b-dbca17c01b4b'
EIA_URLS = {
    ('923', 2019): 'https://www.eia.gov/electricity/data/eia923/archive/xls/f923_2019.zip',
    ('923', 2025): 'https://www.eia.gov/electricity/data/eia923/xls/f923_2025er.zip',
    ('860', 2019): 'https://www.eia.gov/electricity/data/eia860/archive/xls/eia8602019.zip',
    ('860', 2025): 'https://www.eia.gov/electricity/data/eia860/xls/eia8602025ER.zip',
}
REACTORS = {
    (2497, '2'): ('Indian Point 2', 'H'),
    (8907, '3'): ('Indian Point 3', 'H'),
    (2589, '1'): ('Nine Mile Point 1', 'C'),
    (2589, '2'): ('Nine Mile Point 2', 'C'),
    (6110, '1'): ('FitzPatrick', 'C'),
    (6122, '1'): ('Ginna', 'B'),
}
# EIA plant IDs joined to explicitly inspected 2025 Gold Book III-2a sites.
# Historical use assumes a site's delivery zone is unchanged; capacities are
# taken from each year's EIA inventory, not backcast from 2025.
WIND_ZONES = {
    56575:'A',56620:'A',57078:'A',61673:'A',58777:'A',65495:'A',
    55790:'C',56633:'C',56634:'C',56953:'C',56902:'C',57867:'C',
    58088:'C',58768:'C',66052:'C',60596:'C',56619:'D',56618:'D',
    56901:'D',56904:'D',56857:'D',59629:'D',55769:'E',56290:'E',
    56594:'E',57287:'E',58979:'E',61041:'E',65522:'E',65496:'E',65561:'K',
}
# County proxies are deliberately not asserted to be electrical NYISO zones.
# Exact wind/nuclear/major-hydro site overrides take precedence.
COUNTY_GROUPS = {
 'A':'Allegany Cattaraugus Chautauqua Erie Genesee Niagara Orleans Wyoming',
 'B':'Monroe Ontario Wayne',
 'C':'Broome Cayuga Chemung Cortland Livingston Onondaga Oswego Schuyler Seneca Steuben Tioga Tompkins Yates',
 'D':'Clinton Essex Franklin St_Lawrence',
 'E':'Chenango Fulton Hamilton Herkimer Jefferson Lewis Madison Montgomery Oneida Otsego Schoharie',
 'F':'Albany Columbia Greene Rensselaer Saratoga Schenectady Warren Washington',
 'G':'Delaware Dutchess Orange Putnam Rockland Sullivan Ulster',
 'H':'Westchester',
 'J':'Bronx Kings New_York Queens Richmond',
 'K':'Nassau Suffolk',
}
COUNTY_ZONE = {c.replace('_',' ').lower():z for z,cs in COUNTY_GROUPS.items() for c in cs.split()}
OTHER_FUELS = {'SUN','MSW','LFG','WDS','OBG','OBS','BLQ','AB','GEO','SLW','OBL'}
NONFOSSIL = ['Nuclear','Hydro','Wind','Other Renewables']
POLICY = {
 'scope':'Retrospective approximate zonal generation priors; not observed zonal telemetry or as-of operational forecast.',
 'forbidden_inputs':'No internal interface observations, fitted participation, model flow results or interface-derived generation.',
 'p63_interval':'Sample value represents preceding interval ending at its timestamp (declared integration assumption); both trailing and leading one-hour bins retained.',
 'p63_gap':'Intervals longer than 600 seconds are uncovered; no bridging long gaps or silent nearest-hour substitution.',
 'nuclear':'NRC daily morning availability fraction times EIA seasonal net capability; normalized to statewide P63 nuclear MW. Status is not an observed hourly electrical output.',
 'nrc_timing':'Reports collected 04:00-08:00 Eastern. Use previous day for hours before 08:00; otherwise same day; daily within-day constancy remains assumed.',
 'hydro':'Positive published monthly EIA923 conventional HY/WAT mean MW form plant baselines, clipped to active EIA860 seasonal net capability. Below-baseline totals scale these baselines down. Above-baseline P63 Hydro is allocated in proportion to unused HY and PS generation headroom. PS monthly net pumping is retained separately and never relabeled zero observed generation. Annual-respondent monthly values, plant-hour output and PS residual are estimates; storage energy availability is unobserved. Totals above all HY/PS capability fail qualification.',
 'wind':'Vintage EIA860 nameplate capacities of units in operation by the snapshot month determine geographic shares. Gold Book site-zone identities override approximate county zones. Same capacity factor across sites is assumed.',
 'other_renewables':'Vintage EIA860 biomass/waste/solar capacities determine approximate shares. Solar weight multiplied by positive sine of approximate local solar altitude (no weather). Market/behind-meter category coverage is not exact; storage is not separately allocated.',
 'inventory_vintage':'Annual end-year operating plus within-year retired inventory is filtered by operating/retirement month. Start-month units excluded until next month; retirement-month units excluded. Intra-year capacity changes not reconstructed.',
 'annual_status_assumption':'OP/SB annual units are eligible; OA/OS units are excluded throughout that vintage as a conservative assumption. Annual outage status is not hourly availability evidence. For 2025 this excludes St Lawrence unit21 and Lewiston unit2 from seasonal capability.',
 'geography':'Explicit site overrides plus county-to-zone approximations; county borders need not match electrical zones. H/I distinction for generic Westchester remains approximate.',
 '2025_release':'EIA860/923 2025 early release downloaded 2026-09-08; retrospective information, not fully validated by EIA.',
 'scaling':'Uniform fixed-year peak gamma copied from registered snapshot metadata; no independent fitting.',
 'double_counting':'These four nonfossil fuel totals replace corresponding source priors; they must not be added to total fleet priors a second time.',
}

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f'Cannot silently emit empty table {path}')
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f, fields,lineterminator='\n'); w.writeheader(); w.writerows(rows)

class Sources:
    def __init__(self, cache: Path, offline: bool=False):
        self.cache=cache; self.cache.mkdir(parents=True,exist_ok=True)
        self.offline=offline; self.manifest={}

    def register(self, key, url, path, data, role):
        entry=dict(source_id=key,source_url=url,local_cache=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                   sha256=sha(data),bytes=len(data),evidence_role=role,retrieval_date='2026-09-08')
        if key in self.manifest and self.manifest[key]['sha256'] != entry['sha256']:
            raise ValueError('Source identity has conflicting bytes: '+key)
        self.manifest[key]=entry
        return data

    def get(self,key,url,name,role):
        path=self.cache/name
        if not path.exists():
            if self.offline: raise FileNotFoundError(path)
            with urllib.request.urlopen(url,timeout=120) as response: data=response.read()
            path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
        return self.register(key,url,path,path.read_bytes(),role)

    def eia_member(self,form,year,needle):
        url=EIA_URLS[(form,year)]; sid=f'EIA{form}:{year}'
        data=self.get(sid,url,f'eia{form}_{year}.zip','official_annual_archive_2025_early_release' if year==2025 else 'official_final_annual_archive')
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names=[n for n in z.namelist() if needle in n and n.endswith('.xlsx')]
            if len(names)!=1:raise ValueError('Ambiguous EIA workbook '+str(names))
            name=names[0]; member=z.read(name)
        path=self.cache/f'eia{form}_{year}'/Path(name).name
        path.parent.mkdir(exist_ok=True); path.write_bytes(member)
        key=sid+':'+Path(name).name
        self.register(key,url,path,member,'original_archive_workbook')
        return path,key,sha(member)

def registered_hours(snapshot_csv: Path, protocol_json: Path) -> list[dict]:
    # Strict field projection is intentional: source snapshot files contain
    # unrelated metadata that must not enter generation reconstruction.
    fields=['scenario_id','vintage','timestamp','timestamp_utc','source_time_zone','scale_factor_gamma']
    with snapshot_csv.open(encoding='utf-8-sig',newline='') as f:
        rows=[{k:r[k] for k in fields} for r in csv.DictReader(f)]
    if len(rows)!=12:raise ValueError('Expected exactly twelve registered original hours')
    year_gamma={int(r['vintage']):float(r['scale_factor_gamma']) for r in rows}
    for r in rows:
        if abs(float(r['scale_factor_gamma'])-year_gamma[int(r['vintage'])])>1e-12:
            raise ValueError('Scale is not fixed by vintage')
        r['selection_role']='historical_or_revisited_diagnostic'
    protocol=json.loads(protocol_json.read_text())
    for src in protocol['new_calendar_selected_2025_validation_hours']:
        r={k:src[k] for k in ['scenario_id','timestamp','timestamp_utc','source_time_zone']}
        r.update(vintage='2025',scale_factor_gamma=year_gamma[2025],selection_role='preregistered_calendar_validation')
        rows.append(r)
    if len(rows)!=16 or len({r['scenario_id'] for r in rows})!=16:raise ValueError('Sixteen unique scenarios required')
    for r in rows:
        r['vintage']=int(r['vintage']);r['scale_factor_gamma']=float(r['scale_factor_gamma'])
        local=datetime.fromisoformat(r['timestamp'])
        offset={'EST':-5,'EDT':-4}[r['source_time_zone']]
        utc=local.replace(tzinfo=timezone(timedelta(hours=offset))).astimezone(timezone.utc)
        if utc.strftime('%Y-%m-%dT%H:%M:%SZ')!=r['timestamp_utc']:raise ValueError('Timestamp/timezone disagreement')
    return rows

def meta(r):
    return dict(scenario_id=r['scenario_id'],vintage=r['vintage'],timestamp_local_requested=r['timestamp'],
                timestamp_utc_requested=r['timestamp_utc'],scale_factor_gamma=r['scale_factor_gamma'])

def integrate_samples(samples, start, end):
    """Backward interval rectangles; long gaps remain missing, not imputed."""
    samples=sorted(samples,key=lambda s:s[0]);integral=coverage=0.; count=0; maxgap=0.
    if len({s[0] for s in samples})!=len(samples):raise ValueError('Duplicate fuel/time sample')
    for (ta,_,_),(tb,p,_) in zip(samples,samples[1:]):
        seconds=max(0.,(min(tb,end)-max(ta,start)).total_seconds())
        if not seconds:continue
        gap=(tb-ta).total_seconds();maxgap=max(maxgap,gap)
        if gap>600:continue
        if not math.isfinite(p):raise ValueError('Nonfinite source MW')
        integral+=seconds*p;coverage+=seconds;count+=1
    mean=integral/coverage if coverage else math.nan
    return mean,coverage,count,maxgap

def fuelmix(sources: Sources,hours: list[dict]):
    hourly=[];raw=[];cache={}
    for r in hours:
        dt=datetime.fromisoformat(r['timestamp']);month=dt.strftime('%Y%m');day=dt.strftime('%Y%m%d')
        if day not in cache:
            url=f'https://mis.nyiso.com/public/csv/rtfuelmix/{month}01rtfuelmix_csv.zip'
            name=f'{month}01rtfuelmix_csv.zip';sid=f'NYISO:P63:{month}:ZIP'
            p=sources.cache/name
            # Reuse source bytes without editing pre-existing historical caches.
            old=ROOT/f'System Matpower Format/NY_Lite/nyiso_public_cache/{month}_rtfuelmix'/name
            old2=ROOT/'tmp/nygrid_source_audit'/name
            if not p.exists():
                for q in [old,old2]:
                    if q.exists():p.write_bytes(q.read_bytes());break
            data=sources.get(sid,url,name,'official_monthly_fuelmix_archive')
            with zipfile.ZipFile(io.BytesIO(data)) as z:member=z.read(day+'rtfuelmix.csv')
            p=sources.cache/(day+'rtfuelmix.csv');p.write_bytes(member)
            key=f'NYISO:P63:{day}';sources.register(key,url,p,member,'original_daily_csv_member')
            parsed=defaultdict(list)
            for line,row in enumerate(csv.DictReader(io.StringIO(member.decode('utf-8-sig'))),2):
                t=datetime.strptime(row['Time Stamp'],'%m/%d/%Y %H:%M:%S')
                parsed[row['Fuel Category']].append((t,float(row['Gen MW']),line,row['Time Zone']))
            if set(parsed)!={'Dual Fuel','Natural Gas','Nuclear','Other Fossil Fuels','Other Renewables','Wind','Hydro'}:
                raise ValueError('Unexpected fuel categories')
            cache[day]=(parsed,key,sha(member))
        parsed,key,digest=cache[day]
        for fuel,ss in sorted(parsed.items()):
            for t,p,line,tz in ss:
                if dt-timedelta(hours=1,minutes=10)<=t<=dt+timedelta(hours=1,minutes=10):
                    if tz!=r['source_time_zone']:raise ValueError('P63 timezone mismatch')
                    raw.append(dict(**meta(r),fuel_category=fuel,source_timestamp=t.isoformat(sep=' '),
                                    source_time_zone=tz,source_generation_mw=p,source_csv_line=line,source_id=key,source_sha256=digest))
            samples=[s[:3] for s in ss]
            for window,a,b in [('hour_ending',dt-timedelta(hours=1),dt),('hour_beginning',dt,dt+timedelta(hours=1))]:
                mean,coverage,count,gap=integrate_samples(samples,a,b)
                hourly.append(dict(**meta(r),fuel_category=fuel,window_policy=window,window_start_local=str(a),window_end_local=str(b),
                                   duration_weighted_generation_mw=mean,coverage_seconds=coverage,interval_count=count,max_source_gap_seconds=gap,
                                   coverage_qualified=int(abs(coverage-3600)<1e-6),statewide_generation_observed=1,zonal_generation_observed=0,
                                   source_id=key,source_sha256=digest,integration_assumption=POLICY['p63_interval']))
    return hourly,raw

def sheet_dicts(path,sheet,marker):
    w=openpyxl.load_workbook(path,read_only=True,data_only=True)
    try:
        ws=w[sheet] if isinstance(sheet,str) else w.worksheets[sheet]
        keys=None
        for i,row in enumerate(ws.values,1):
            if keys is None:
                if marker in row:keys=[re.sub(r'\s+',' ',str(x)).strip() for x in row]
            else:yield i,dict(zip(keys,row))
        if keys is None:raise ValueError('Required EIA header missing')
    finally:w.close()

def num(value,default=0.):
    if value is None or str(value).strip() in {'','.','NA','N/A'}:return default
    x=float(value)
    if not math.isfinite(x):raise ValueError('Nonfinite numeric value')
    return x

def plant_zone(pid,gid,county,fuel):
    if (pid,gid) in REACTORS:return REACTORS[(pid,gid)][1],'explicit_reactor_site_zone'
    if pid in {2691,2692,2693,2694}:return {2691:'F',2692:'A',2693:'A',2694:'D'}[pid],'major_hydro_site_zone_Gold_Book'
    if fuel=='WND' and pid in WIND_ZONES:return WIND_ZONES[pid],'Gold_Book_2025_wind_site_join_historical_zone_constancy_assumed'
    c=re.sub(r'\s+',' ',str(county)).strip().replace('St. ','St ').lower()
    if c=='genesse':return 'A','approximate_county_zone_EIA_Genesse_spelling_normalized_to_Genesee'
    if c not in COUNTY_ZONE:raise ValueError(f'Unmapped EIA county {pid}: {county}')
    return COUNTY_ZONE[c],'approximate_county_zone_not_verified_electrical_delivery'

def inventories(sources):
    inventory=[];plants={}
    for year in [2019,2025]:
        pp,ps,ph=sources.eia_member('860',year,'2___Plant')
        for line,d in sheet_dicts(pp,'Plant','Plant Code'):
            if d.get('State')=='NY':plants[(year,int(d['Plant Code']))]=d
        path,sid,digest=sources.eia_member('860',year,'3_1_Generator')
        for sheet in ['Operable','Retired and Canceled']:
            for line,d in sheet_dicts(path,sheet,'Plant Code'):
                fuel=str(d.get('Energy Source 1','')).strip()
                if d.get('State')!='NY' or fuel not in {'NUC','WAT','WND'}|OTHER_FUELS:continue
                if sheet!='Operable' and str(d.get('Status')).strip()!='RE':continue
                pid=int(d['Plant Code']);gid=str(d['Generator ID']).strip()
                zone,method=plant_zone(pid,gid,d['County'],fuel)
                p=plants[(year,pid)]
                inventory.append(dict(vintage=year,plant_id=pid,generator_id=gid,device_key=f'EIA860:{year}:PLANT:{pid}:GEN:{gid}',
                  plant_name=d['Plant Name'],county=d['County'],estimated_zone=zone,zone_mapping_policy=method,energy_source_code=fuel,
                  prime_mover=d.get('Prime Mover'),technology=d.get('Technology'),source_status=d.get('Status'),source_sheet=sheet,
                  nameplate_capacity_mw=num(d.get('Nameplate Capacity (MW)')),summer_capacity_mw=num(d.get('Summer Capacity (MW)')),
                  winter_capacity_mw=num(d.get('Winter Capacity (MW)')),operating_year=int(num(d.get('Operating Year'))),
                  operating_month=int(num(d.get('Operating Month'))),retirement_year=int(num(d.get('Retirement Year'))),
                  retirement_month=int(num(d.get('Retirement Month'))),latitude=num(p.get('Latitude'),42.5),longitude=num(p.get('Longitude'),-75),
                  source_excel_row=line,source_id=sid,source_sha256=digest,capacity_observed=1,hourly_dispatch_observed=0,
                  release_status='early_release' if year==2025 else 'final'))
    keys=[r['device_key'] for r in inventory]
    if len(set(keys))!=len(keys):raise ValueError('Duplicate EIA generator identity')
    return inventory,plants

def is_active(d,dt):
    start=(d['operating_year'],d['operating_month']);current=(dt.year,dt.month)
    if start>=(dt.year,dt.month):return False
    if d['source_status'] not in {'OP','SB','RE'}:return False
    if d['source_status']=='RE':
        if not d['retirement_year'] or not d['retirement_month']:return False
        if current>=(d['retirement_year'],d['retirement_month']):return False
    return True

def hydro_monthly(sources,plants):
    rows=[]
    for year in [2019,2025]:
        path,sid,digest=sources.eia_member('923',year,'Schedules_2_3_4_5')
        for line,d in sheet_dicts(path,0,'Plant Id'):
            if d.get('Plant State')!='NY' or d.get('Reported Fuel Type Code')!='WAT':continue
            pid=int(d['Plant Id']);p=plants.get((year,pid))
            if p is None and pid!=99999:raise ValueError('Hydro plant missing EIA860 location: '+str(pid))
            zone,method=plant_zone(pid,'',p['County'],'WAT') if p else ('UNLOCATED','state_fuel_increment_not_a_locatable_plant')
            for month in [1,4,7]:
                value=num(d['Netgen '+calendar.month_name[month]],math.nan)
                if not math.isfinite(value):raise ValueError('Missing monthly hydro value')
                pm=str(d['Reported Prime Mover']);eligible=pm=='HY' and value>0 and p is not None
                rows.append(dict(vintage=year,month=month,plant_id=pid,plant_name=d['Plant Name'],estimated_zone=zone,
                    zone_mapping_policy=method,prime_mover=pm,net_generation_mwh=value,monthly_mean_net_mw=value/(calendar.monthrange(year,month)[1]*24),
                    share_weight_mwh=value if eligible else 0,allocation_eligible=int(eligible),
                    disposition='positive_conventional_hydro_share' if eligible else 'pumped_storage_or_nonpositive_or_unlocated_excluded_from_share',
                    respondent_frequency=d.get('Respondent Frequency'),monthly_source_value_published=1,
                    monthly_generation_observed=int(d.get('Respondent Frequency')=='M'),hourly_generation_observed=0,
                    source_excel_row=line,source_id=sid,source_sha256=digest,release_status='early_release' if year==2025 else 'final'))
    return rows

def parse_nrc(data):
    result={}
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',data.decode('utf-8'),flags=re.S|re.I):
        cells=[html.unescape(re.sub('<[^>]+>','',c)).strip() for c in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>',row,flags=re.S|re.I)]
        if cells and cells[0] in {v[0] for v in REACTORS.values()}:
            if cells[0] in result:raise ValueError('Duplicate NRC reactor')
            pct=float(cells[1])
            if not 0<=pct<=110:raise ValueError('Invalid NRC percentage')
            result[cells[0]]=(pct,'; '.join(cells[2:]))
    return result

def nuclear_daily(sources,hours,inventory):
    rows=[]
    for r in hours:
        dt=datetime.fromisoformat(r['timestamp']);date=dt.date() if dt.hour>=8 else (dt-timedelta(days=1)).date()
        day=date.strftime('%Y%m%d');key='NRC:DAILY:'+day
        url=f'https://www.nrc.gov/reading-rm/doc-collections/event-status/reactor-status/{date.year}/{day}ps'
        data=sources.get(key,url,day+'ps.html','daily_morning_reactor_availability_not_hourly_MW')
        status=parse_nrc(data)
        expected=6 if dt.year==2019 else 4
        units=[d for d in inventory if d['vintage']==dt.year and d['energy_source_code']=='NUC' and is_active(d,dt)]
        if len(units)!=expected:raise ValueError('Unexpected nuclear fleet vintage')
        for d in units:
            name,zone=REACTORS[(d['plant_id'],d['generator_id'])]
            if name not in status:raise ValueError('NRC report missing expected reactor '+name)
            pct,comment=status[name];season='winter' if dt.month in [11,12,1,2,3] else 'summer'
            cap=d[season+'_capacity_mw']
            rows.append(dict(**meta(r),plant_id=d['plant_id'],generator_id=d['generator_id'],reactor_name=name,estimated_zone=zone,
                nrc_report_date=str(date),report_collection_window_eastern='04:00-08:00',report_power_percent=pct,
                seasonal_net_capacity_mw=cap,seasonal_capacity_basis=season,estimated_available_net_mw=cap*pct/100,
                daily_status_observed=1,hourly_output_observed=0,status_comment=comment,source_id=key,source_sha256=sha(data),
                eia_capacity_source_id=d['source_id'],eia_capacity_source_sha256=d['source_sha256'],timing_policy=POLICY['nrc_timing']))
    return rows

def solar_weight(dt,latitude,longitude,zone):
    # Simple geometric daylight weighting, not irradiance or an observed CF.
    dec=math.radians(23.44*math.sin(2*math.pi*(284+dt.timetuple().tm_yday)/365.25))
    standard_hour=dt.hour+dt.minute/60-(1 if zone=='EDT' else 0)
    solar_hour=standard_hour+(longitude+75)/15
    ha=math.radians(15*(solar_hour-12));lat=math.radians(latitude)
    return max(0.,math.sin(lat)*math.sin(dec)+math.cos(lat)*math.cos(dec)*math.cos(ha))

def bounded_hydro_projection(baseline,capability,total):
    """Conserve a published total within finite plant generation capability.

    This is an explicitly assumed allocation, not a reservoir scheduling model.
    Zero monthly net PS is not interpreted as measured hourly generation.
    """
    if len(baseline)!=len(capability) or not baseline:raise ValueError('Hydro plant dimensions')
    if not all(math.isfinite(x) and x>=0 for x in baseline+capability+[total]):raise ValueError('Invalid hydro allocation inputs')
    caps=sum(capability)
    if total>caps+1e-7:return [math.nan]*len(baseline),False
    base=[min(p,c) for p,c in zip(baseline,capability)];base_total=sum(base)
    if total<=base_total:
        output=[p*total/base_total for p in base] if base_total else [0.]*len(base)
    elif caps>base_total:
        fraction=(total-base_total)/(caps-base_total)
        output=[p+fraction*(c-p) for p,c in zip(base,capability)]
    else:output=base
    return output,True

def hydro_plant_allocation(hours,hourly,inventory,hydro,window):
    output=[]
    observations={d['scenario_id']:d for d in hourly if d['window_policy']==window and d['fuel_category']=='Hydro'}
    for r in hours:
        dt=datetime.fromisoformat(r['timestamp']);season='winter' if dt.month in [11,12,1,2,3] else 'summer'
        plants={}
        for d in inventory:
            if d['vintage']!=dt.year or d['energy_source_code']!='WAT' or d['prime_mover'] not in {'HY','PS'} or not is_active(d,dt):continue
            key=(d['plant_id'],d['prime_mover'])
            if key not in plants:
                plants[key]=dict(plant_id=d['plant_id'],plant_name=d['plant_name'],prime_mover=d['prime_mover'],
                    zone=d['estimated_zone'],zone_mapping_policy=d['zone_mapping_policy'],seasonal_capacity_mw=0.,
                    monthly_mean_net_mw=0.,positive_conventional_baseline_mw=0.,seasonal_capacity_basis=season,
                    capacity_source_id=d['source_id'],capacity_source_sha256=d['source_sha256'],capacity_generator_keys=[],
                    monthly_source_ids=set(),monthly_source_sha256=set(),monthly_source_rows=[])
            p=plants[key]
            if p['zone']!=d['estimated_zone']:raise ValueError('Hydro unit delivery zone disagrees within plant')
            p['seasonal_capacity_mw']+=d[season+'_capacity_mw'];p['capacity_generator_keys'].append(d['device_key'])
        for d in hydro:
            key=(d['plant_id'],d['prime_mover'])
            if d['vintage']!=dt.year or d['month']!=dt.month or key not in plants:continue
            p=plants[key];p['monthly_mean_net_mw']+=d['monthly_mean_net_mw']
            if d['prime_mover']=='HY':p['positive_conventional_baseline_mw']+=max(0.,d['monthly_mean_net_mw'])
            p['monthly_source_ids'].add(d['source_id']);p['monthly_source_sha256'].add(d['source_sha256']);p['monthly_source_rows'].append(str(d['source_excel_row']))
        rows=list(plants.values());obs=observations[r['scenario_id']]
        baseline=[p['positive_conventional_baseline_mw'] for p in rows];caps=[p['seasonal_capacity_mw'] for p in rows]
        total=obs['duration_weighted_generation_mw']
        if obs['coverage_qualified']:values,cap_ok=bounded_hydro_projection(baseline,caps,total)
        else:values=[math.nan]*len(rows);cap_ok=False
        for p,mw in zip(rows,values):
            for field in ['capacity_generator_keys','monthly_source_ids','monthly_source_sha256','monthly_source_rows']:
                p[field]=';'.join(sorted(p[field]))
            output.append(dict(**meta(r),**p,estimated_generation_mw=mw,estimated_benchmark_generation_mw=mw*r['scale_factor_gamma'],
                clipped_baseline_mw=min(p['positive_conventional_baseline_mw'],p['seasonal_capacity_mw']),
                generation_capability_qualified=int(cap_ok),coverage_qualified=obs['coverage_qualified'],
                allocation_qualified=int(cap_ok and obs['coverage_qualified']),statewide_observed_hydro_mw=total,
                statewide_inventory_hydro_capability_mw=sum(caps),source_id=obs['source_id'],source_sha256=obs['source_sha256'],
                window_policy=window,hourly_generation_observed=0,storage_energy_observed=0,
                generation_policy='monthly_HY_baseline_then_finite_HY_PS_headroom_projection',
                pumped_storage_policy='unobserved_hourly_positive_generation_residual_no_storage_energy_claim' if p['prime_mover']=='PS' else 'conventional_hydro'))
    return output

def allocate_priors(hours,hourly,inventory,hydro,nuclear,window,hydro_plants=None):
    priors=[];shares=[]
    if hydro_plants is None:hydro_plants=hydro_plant_allocation(hours,hourly,inventory,hydro,window)
    totals={(d['scenario_id'],d['fuel_category']):d for d in hourly if d['window_policy']==window}
    for r in hours:
        dt=datetime.fromisoformat(r['timestamp'])
        weights={f:defaultdict(float) for f in NONFOSSIL};ids=defaultdict(set)
        for d in nuclear:
            if d['scenario_id']==r['scenario_id']:
                weights['Nuclear'][d['estimated_zone']]+=d['estimated_available_net_mw'];ids['Nuclear'].add(d['source_id'])
        hp=[d for d in hydro_plants if d['scenario_id']==r['scenario_id']]
        hydro_qualified=all(d['allocation_qualified'] for d in hp)
        for d in hp:
            weights['Hydro'][d['zone']]+=d['estimated_generation_mw'] if hydro_qualified else d['seasonal_capacity_mw']
            ids['Hydro'].update(d['monthly_source_ids'].split(';'));ids['Hydro'].add(d['capacity_source_id'])
        for d in inventory:
            if d['vintage']!=dt.year or not is_active(d,dt):continue
            f=d['energy_source_code'];cat='Wind' if f=='WND' else 'Other Renewables' if f in OTHER_FUELS else ''
            if not cat:continue
            weight=d['nameplate_capacity_mw']
            if f=='SUN':weight*=solar_weight(dt-timedelta(minutes=30) if window=='hour_ending' else dt+timedelta(minutes=30),d['latitude'],d['longitude'],r['source_time_zone'])
            weights[cat][d['estimated_zone']]+=weight;ids[cat].add(d['source_id'])
        for f in NONFOSSIL:
            obs=totals[(r['scenario_id'],f)]
            total=obs['duration_weighted_generation_mw'];denom=sum(weights[f].values())
            if (denom<=0 and total!=0) or (math.isfinite(total) and total<0):raise ValueError('Invalid allocation denominator or nonfossil total')
            qualified=obs['coverage_qualified'] and (hydro_qualified or f!='Hydro')
            method={'Nuclear':'daily_NRC_times_seasonal_EIA_capacity','Hydro':'monthly_EIA923_baseline_with_finite_EIA860_HY_PS_headroom',
                    'Wind':'vintage_EIA860_nameplate_capacity','Other Renewables':'vintage_EIA860_capacity_with_assumed_solar_daylight_weight'}[f]
            for z in 'ABCDEFGHIJK':
                share=weights[f][z]/denom if denom else 1/11;mw=total*share if qualified else math.nan
                common=dict(**meta(r),zone=z,fuel_category=f,allocation_method=method,allocation_weight=weights[f][z],allocation_share=share,
                    zonal_generation_observed=0,geographic_estimate=1,source_id=obs['source_id'],source_sha256=obs['source_sha256'],
                    allocation_source_ids=';'.join(sorted(ids[f])),window_policy=window,
                    coverage_qualified=int(qualified),source_interval_coverage_qualified=obs['coverage_qualified'],
                    plant_generation_capability_qualified=int(hydro_qualified) if f=='Hydro' else 1,coverage_seconds=obs['coverage_seconds'])
                priors.append(dict(**common,prior_public_mw=mw,prior_benchmark_mw=mw*r['scale_factor_gamma'],statewide_observed_mw=total))
                shares.append(dict(**common,weight_denominator=denom))
    return priors,shares

def named_renewable_priors(hours,hourly,inventory,priors,window):
    """Identify a subset of zone K wind, never an additional injection."""
    rows=[]
    for r in hours:
        dt=datetime.fromisoformat(r['timestamp'])
        wind=[d for d in inventory if d['vintage']==dt.year and d['energy_source_code']=='WND' and is_active(d,dt)]
        asset=[d for d in wind if d['plant_id']==65561]
        if any(d['estimated_zone']!='K' for d in asset):raise ValueError('South Fork delivery zone changed')
        denominator=sum(d['nameplate_capacity_mw'] for d in wind);capacity=sum(d['nameplate_capacity_mw'] for d in asset)
        obs=next(d for d in hourly if d['scenario_id']==r['scenario_id'] and d['fuel_category']=='Wind' and d['window_policy']==window)
        share=capacity/denominator if denominator else 0
        mw=obs['duration_weighted_generation_mw']*share if obs['coverage_qualified'] else math.nan
        zone=next(d for d in priors if d['scenario_id']==r['scenario_id'] and d['fuel_category']=='Wind' and d['zone']=='K')
        if obs['coverage_qualified'] and not (-1e-8<=mw<=zone['prior_public_mw']+1e-8):raise ValueError('Named wind is not a subset of its zonal prior')
        rows.append(dict(**meta(r),asset_id='SOUTH_FORK',model_generator_key='NY2025:GEN:SOUTH_FORK:K9003',
            plant_id=65561,source_generator_ids=';'.join(d['generator_id'] for d in asset),zone='K',fuel_category='Wind',
            active_in_source_vintage=int(bool(asset)),active_nameplate_capacity_mw=capacity,statewide_active_wind_capacity_mw=denominator,
            statewide_wind_capacity_share=share,statewide_observed_wind_mw=obs['duration_weighted_generation_mw'],
            prior_public_mw=mw,prior_benchmark_mw=mw*r['scale_factor_gamma'],parent_zone_fuel_prior_public_mw=zone['prior_public_mw'],
            subset_of_zone_fuel_prior=1,coverage_qualified=obs['coverage_qualified'],zonal_generation_observed=0,plant_generation_observed=0,
            allocation_method='same_statewide_EIA_wind_capacity_share_as_parent_zone_not_additional_generation',
            source_id=obs['source_id'],source_sha256=obs['source_sha256'],
            capacity_source_ids=';'.join(sorted({d['source_id'] for d in wind})),
            capacity_source_sha256=';'.join(sorted({d['source_sha256'] for d in wind})),window_policy=window))
    return rows

def build(snapshot_csv=None,protocol_json=None,output_dir=None,cache_dir=None,window='hour_beginning',offline=False):
    if window not in {'hour_ending','hour_beginning'}:raise ValueError('Declared hour window required')
    output_dir=Path(output_dir or DEFAULT_OUT);output_dir.mkdir(parents=True,exist_ok=True)
    snapshot_csv=Path(snapshot_csv or ROOT/'output/compact_ny_2025/electrical_fixed_peak/source_snapshots.csv')
    protocol_json=Path(protocol_json or ROOT/'output/compact_ny_2025/generation_sources/generation_reconstruction_protocol.json')
    hours=registered_hours(snapshot_csv,protocol_json);sources=Sources(Path(cache_dir or DEFAULT_CACHE),offline)
    sources.get('NYISO:GOLD_BOOK:2025',GOLD_URL,'2025_Gold_Book.pdf','site_zone_identity_reference_not_hourly_generation')
    hourly,raw=fuelmix(sources,hours)
    inventory,plants=inventories(sources)
    hydro=hydro_monthly(sources,plants)
    nuclear=nuclear_daily(sources,hours,inventory)
    hydro_plants=hydro_plant_allocation(hours,hourly,inventory,hydro,window)
    priors,shares=allocate_priors(hours,hourly,inventory,hydro,nuclear,window,hydro_plants)
    named=named_renewable_priors(hours,hourly,inventory,priors,window)
    tables={'registered_hours.csv':hours,'statewide_fuelmix_hourly.csv':hourly,'statewide_fuelmix_raw_samples.csv':raw,
            'eia860_nonfossil_inventory.csv':inventory,'eia923_monthly_hydro.csv':hydro,'nrc_daily_reactor_inputs.csv':nuclear,
            'hydro_plant_hourly_estimates.csv':hydro_plants,'zonal_nonfossil_priors.csv':priors,
            'named_renewable_priors.csv':named,'zonal_allocation_shares.csv':shares,'source_manifest.csv':list(sources.manifest.values())}
    for name,rows in tables.items():write_csv(output_dir/name,rows)
    reconciliation=[]
    for r in hours:
        for f in NONFOSSIL:
            selected=[d for d in priors if d['scenario_id']==r['scenario_id'] and d['fuel_category']==f]
            error=sum(d['prior_public_mw'] for d in selected)-selected[0]['statewide_observed_mw']
            qualified=selected[0]['coverage_qualified']
            check=abs(error)<1e-7 if qualified else all(math.isnan(d['prior_public_mw']) for d in selected)
            reconciliation.append(dict(scenario_id=r['scenario_id'],fuel_category=f,zone_count=len(selected),public_mw_conservation_error=error,
                                       coverage_qualified=qualified,all_zonal_values_estimated=int(all(d['zonal_generation_observed']==0 for d in selected)),
                                       passed=int(len(selected)==11 and check)))
    write_csv(output_dir/'allocation_validation.csv',reconciliation)
    report=dict(policy=POLICY,primary_window=window,scenario_count=len(hours),row_counts={k:len(v) for k,v in tables.items()},
                all_conservation_checks_pass=all(d['passed'] for d in reconciliation),
                incomplete_primary_fuel_hours=[dict(scenario_id=d['scenario_id'],fuel_category=d['fuel_category'],coverage_seconds=d['coverage_seconds'])
                    for d in hourly if d['window_policy']==window and not d['coverage_qualified']],
                hydro_capacity_ineligible_scenarios=sorted({d['scenario_id'] for d in hydro_plants if not d['generation_capability_qualified']}),
                input_metadata_projection_sha256=sha(json.dumps(hours,sort_keys=True).encode()),
                protocol_sha256=sha(protocol_json.read_bytes()),source_input_interface_values_read=False)
    (output_dir/'nonfossil_input_summary.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    outputs=[]
    for p in sorted(output_dir.glob('*.csv')):
        if p.name!='output_manifest.csv':outputs.append(dict(artifact=p.name,sha256=sha(p.read_bytes())))
    outputs.append(dict(artifact='nonfossil_input_summary.json',sha256=sha((output_dir/'nonfossil_input_summary.json').read_bytes())))
    write_csv(output_dir/'output_manifest.csv',outputs)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot-csv',type=Path);parser.add_argument('--protocol-json',type=Path)
    parser.add_argument('--output-dir',type=Path);parser.add_argument('--cache-dir',type=Path)
    parser.add_argument('--window',choices=['hour_ending','hour_beginning'],default='hour_beginning')
    parser.add_argument('--offline',action='store_true')
    print(json.dumps(build(**vars(parser.parse_args())),indent=2))
