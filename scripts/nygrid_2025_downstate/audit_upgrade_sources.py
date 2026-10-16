"""Primary evidence register for the 2025 Downstate refinement.

No operating inputs, dispatch, topology or interface measurements are changed.
Cached receipts remain distinct from sources freshly checked on 2026-10-10.
Run with --fetch to preserve source bytes; reruns verify existing local bytes.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request
from zoneinfo import ZoneInfo
import openpyxl

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_downstate/sources'
BASELINE = 'c7874aa90fec1d4e883814297e91bfcd3567bdf2'
CHECKED = '2026-10-10'
INFRA = ROOT / 'tmp/infrastructure_status_audit'


def source(sid, publisher, date, url, name, purpose, cache='', fresh=True):
    return dict(source_id=sid, publisher=publisher, publication_date=date, source_url=url,
        filename=name, evidence_role=purpose, cache_path=cache, fresh_web_reviewed=fresh)


SOURCES = [
 source('NYISO_MAY2025_OPS','NYISO / NYSRC','2025-06',
  'https://www.nysrc.org/wp-content/uploads/2025/06/7.3.2-Operations_Report_202505_v1-long-form-Attachment-7.3.2.pdf',
  'nyiso_may2025_operations.pdf','Actual May20 and May29 RCC dates and exact equipment IDs; report p3'),
 source('NYISO_DEC2025_OPS','NYISO / NYSRC','2026-01',
  'https://www.nysrc.org/wp-content/uploads/2026/01/7.3.2-Operations_Report_202512_v1-long-form-Attachment-7.3.2.pdf',
  'nyiso_dec2025_operations.pdf','Actual Dover service 2025-12-19 HB23; report p3',
  'tmp/infrastructure_status_audit/nyiso_dec_2025_operations.pdf'),
 source('RCC_QUEENS_OWNER','Con Edison','2023-05-03',
  'https://www.coned.com/en/about-us/media-center/news/2023/05-03/con-edison-completes-important-clean-energy-project-in-queens',
  'coned_rainey_corona_2023.html','Rainey-Corona completion announcement; six-mile route',
  'tmp/infrastructure_status_audit/RCC_QUEENS_COMPLETION.html'),
 source('RCC_MAY_OWNER','Con Edison','2025-05-16',
  'https://www.coned.com/en/about-us/media-center/news/2025/05-16/con-edison-investing-in-major-reliability-projects--serving-customers-in-brooklyn-and-staten-island',
  'coned_rcc_may2025.html','138kV cables, Brooklyn one mile, Staten Island just over nine miles; planned energization that month',
  'tmp/infrastructure_status_audit/RCC_MAY_ANNOUNCEMENT.html'),
 source('CONED_JAN2025_LTP','Con Edison / NYISO','2025-01-21',
  'https://www.nyiso.com/documents/20142/49295323/CECONY%27s_LTP_Update_1_21_2025.pdf/',
  'coned_ltp_jan2025.pdf','Greenwood138 local network diagram and RCC additions; future CHPE separate'),
 source('NYISO_WINTER2023','NYISO','2023-11',
  'https://www.nyiso.com/documents/20142/41164815/05a_Winter2023-24_OpStudyReport_OC.pdf/1f1f3954-2776-58b4-74a7-99825e41aaab',
  'nyiso_winter2023_24.pdf','In-service Rainey transformer5W, PAR R5W, feeder36188; SegmentA/B additions'),
 source('NYISO_SUMMER2025','NYISO','2025',
  'https://www.nyiso.com/documents/20142/3691300/Summer2025-OperatingStudy-APPROVED.pdf/3aaa5eb6-9fa4-53b5-181a-189e3ac52fcb',
  'nyiso_summer2025_study.pdf','Planned/model facility list; Dover changes NY-NE interface membership; not actual commissioning proof'),
 source('NYES_COMPLETION','New York Transco','2023-08-16',
  'https://nytransco.com/wp-content/uploads/2023/08/NYES-News-Release.8.16.23_updated.pdf',
  'nyes_energization_2023.pdf','Owner successful energization announcement; core2023 distinct from late Dover'),
 source('NYES_OWNER_INDEX','New York Transco','2023-08-16',
  'https://www.ny-es.com/project-news','nyes_owner_news.html','Owner index corroborates August16,2023 energization announcement'),
 source('NYES_EMCP','New York Transco / NYDPS','2021',
  'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BF97024BB-23C9-405A-BC3A-AFC80D04ADEA%7D',
  'nyes_phaseII_emcp.pdf','Knickerbocker-PleasantValley54.5mi345; Churchtown115;50pctseriescomp;VanWagner; p51 onward'),
 source('NYES_2023_OWNER_REPORT','New York Transco / NYDPS','2024',
  'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BC092AE8D-0000-C135-8370-80F5C83F2263%7D',
  'nyes_2023_owner_inspection.pdf','Retrospective all core NYES facilities in service end2023;55.6mi345 and56mi115'),
 source('CEEC_COMPLETION','New York Governor / NYPA / LS Power','2023-12-13',
  'https://www.governor.ny.gov/news/governor-hochul-announces-completion-central-east-energy-connect-transmission-line',
  'ceec_completion2023.html','93mi rebuild completed; Princetown/GordonRoad substations; route and eventdate'),
 source('NYISO_GOLDBOOK2024','NYISO','2024-04',
  'https://www.nyiso.com/documents/20142/2226333/2024-Gold-Book-Public.pdf',
  'nyiso_goldbook2024.pdf','TableVII retrospective CEEC2023 components, lengths/conductors/ratings; plain rating numbers are amperes'),
 source('NYISO_GOLDBOOK2025','NYISO','2025-04',
  'https://www.nyiso.com/documents/20142/2226333/2025-Gold-Book-Public.pdf/088438e1-02f1-5316-211b-dbca17c01b4b',
  'nyiso_goldbook2025.pdf','Project device identities and nominal voltages; planned dates not commissioning proof',
  'tmp/nonfossil_sources/2025_Gold_Book.pdf'),
 source('NYISO_CV_2020_STABILITY','NYISO / ISO New England','2020',
  'https://www.nyiso.com/documents/20142/3694233/NY-NE-Stability-Analysis-FINAL.pdf/8be950c7-6e2e-1a75-c232-7d0c0d7839d1',
  'nyiso_cv2020_stability.pdf','p8:existing398tappedCV;PV-CV F83 plus new F84;CV-LM398; factual 2020 in-service topology'),
 source('NYISO_CRP2021_FACILITIES','NYISO','2021',
  'https://www.nyiso.com/documents/20142/26735166/2021-2030-Comprehensive-Reliability-Plan-Appendices.pdf',
  'nyiso_crp2021_appendices.pdf','Historical physical terminal identities/voltages; p132CV,134FreshKills,142Ravenswood1/2'),
 source('NYISO_CLASS2001','NYISO','2001',
  'https://www.nyiso.com/documents/20142/1400542/class_2001_cost_allocation.pdf/41676250-28f0-a847-6c4f-514e529adbc9',
  'nyiso_class2001.pdf','Historical project connection evidence:AstoriaI138,NYPAexpansion138,EastRiver138/69,RavenswoodCC345'),
 source('ASTORIA_II_LGIA','Astoria Energy II / NYISO / NYDPS','2010',
  'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B7C5F64FC-B599-439A-82A4-11AF4A71A01B%7D',
  'astoriaII_lgia1678.pdf','AppC:NYPAAnnex345POI,Q35L/M toEast13th345; explicit historicalGSUnameplates not updated2025ratings'),
 source('BAYONNE_POI','Bayonne Energy Center / NYDPS','2011-02-22',
  'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B2A3250AB-C8E7-413B-8E39-92996977AF02%7D',
  'bayonne_gowanus_emcp.pdf','Section6.4:345kVcable terminatesatGowanusBrooklyn'),
 source('LINDEN_POI','Project owner / NYDPS','2013',
  'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BC4CD2C80-2903-40DD-A8CC-3D0F6EE7084F%7D',
  'linden_goethals_project.pdf','Existing1992Linden-Goethals345connectionG23L/M; source project proposal uses existingcable'),
 source('LINDEN_VFT_SEPARATION','NYISO','2012-05-24',
  'https://nyisoviewer.etariff.biz/ViewerDocLibrary/FercDockets/2012_05_24_NYISO_Pblc_Answr_Cmplnt_13131.htm',
  'nyiso_linden_vft.html','VFT merchanttransmission is separatefromLindennativegenerator',
  'output/nygrid_2025_dispatch/fleet/source_scope/nyiso_linden_vft_20120524.html'),
 source('SOUTH_FORK_POI','South Fork developer / BOEM','2020-02-10',
  'https://www.boem.gov/sites/default/files/documents/oil-gas-energy/App%20J3_SFWF_Acoustic%20Assessment%20Onshore_2020-02-10.pdf',
  'southfork_onshore_primary.pdf','p6:interconnectionexistingLIPA69kVEastHamptonbus; onsitefacilityCoveHollowRoad'),
 source('SOUTH_FORK_COMPLETION','New York Governor / project owners','2024-03-14',
  'https://www.governor.ny.gov/news/governor-hochul-announces-completion-south-fork-wind-first-utility-scale-offshore-wind-farm',
  'southfork_completion2024.html','All12turbinesinstalledanddelivering2024; energizationnotparameterdata'),
 source('NYISO_OCT2025_OPS','NYISO / NYSRC','2025-11',
  'https://www.nysrc.org/wp-content/uploads/2025/11/7.3.2-Operations_Report_202510_v1-long-form-Attachment-7.3.2.pdf',
  'nyiso_oct2025_operations.pdf','SPC device identities and345/230transformers;partial2025notfull2026',
  'tmp/infrastructure_status_audit/nyiso_oct_2025_operations.pdf'),
 source('HTP_NYISO_2013','NYISO','2013-12-20',
  'https://www.nyiso.com/documents/20142/3025085/NYISO%20ICAP%20Annl%20Rprt%20Pblc%20Dcmnts%2020131220.pdf/99401c51-6afc-b3d0-f160-94056b186f1e',
  'htp_nyiso2013.pdf','In-service HTP interconnection at West49thStreet345; Queue206'),
 source('NEPTUNE_OWNER_CABLE','Neptune Regional Transmission System','undated_current_owner_page',
  'https://neptunerts.com/neptune-cables/','neptune_owner_cables.html',
  '500kVDC system;Duffyconverter345kVACcable1.5miles toNewbridgeRoad;NJACterminal230kV'),
 source('CSC_NYISO_2018','NYISO','2018',
  'https://www.nyiso.com/documents/20142/3691300/Winter-2018-19-Operating-Study-Report.pdf/626d4865-3020-52e4-4fa6-f3289fc4300f',
  'csc_nyiso2018.pdf','CrossSoundHVDCNewHavenHarbor345toShoreham138;separatelymeteredfrommainNYNEinterface'),
 source('NYISO_RNA2012_TERMINALS','NYISO','2012-09-18',
  'https://www.nyiso.com/documents/20142/3657944/2012_RNA_Final_Report_9-18-12_PDF.pdf/0dac54f6-e42b-1f49-c37a-d3dbfcd82a59',
  'nyiso_rna2012_terminals.pdf','HistoricalHTPBergen230-West49th345 andVFTPSEG230-Goethals345viaLindenCogen345terminalidentities'),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def csvrows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fields, lineterminator='\n'); w.writeheader(); w.writerows(rows)


def preserve_source(spec, fetch):
    out = {k: v for k, v in spec.items() if k != 'filename'}
    p = OUT / 'raw' / spec['filename']; p.parent.mkdir(parents=True, exist_ok=True)
    out.update(checked_on=CHECKED, primary_source=1, baseline_commit=BASELINE)
    if not p.exists() and spec['cache_path'] and (ROOT / spec['cache_path']).is_file():
        shutil.copy2(ROOT / spec['cache_path'], p)
        out['byte_origin'] = 'preserved_preexisting_primary_source_cache'
    elif not p.exists() and fetch:
        try:
            req = urllib.request.Request(spec['source_url'], headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read()
            if len(data) < 500 or (spec['filename'].endswith('.pdf') and not data.startswith(b'%PDF')):
                raise ValueError('Response is not the expected source document')
            p.write_bytes(data)
            out['byte_origin'] = 'fresh_primary_download'
        except Exception as exc:
            out.update(byte_origin='download_failed', download_error=str(exc), local_path='', sha256='', bytes=0)
    if p.exists():
        out.update(local_path=p.relative_to(ROOT).as_posix(), sha256=sha(p), bytes=p.stat().st_size)
        out.setdefault('byte_origin', 'existing_task_receipt')
    else:
        out.setdefault('byte_origin', 'web_text_review_only_no_local_bytes')
        out.setdefault('local_path', ''); out.setdefault('sha256', ''); out.setdefault('bytes', 0)
    return out


def component(key, project, kind, a, av, b, bv, circuit, date, precision, sources, claim,
              action='add_physical_device_or_declared_aggregate', scope='core_downstate', length='', notes='',
              parameters='identity_endpoints_nominal_voltage_status_only', hour=''):
    year_end = bool(date and date[:4] <= '2025')
    whole_year = bool(date and date[:4] < '2025')
    activation = '2025-01-01T00:00:00-05:00' if whole_year else ''
    if year_end and not whole_year and precision == 'day':
        activation = (datetime.fromisoformat(date) + timedelta(days=1)).replace(tzinfo=ZoneInfo('America/New_York')).isoformat()
    if year_end and not whole_year and precision == 'month':
        yy,mm=map(int,date.split('-'))
        activation=datetime(yy+(mm==12),1 if mm==12 else mm+1,1,tzinfo=ZoneInfo('America/New_York')).isoformat()
    if hour:
        activation = date + 'T23:00:00-05:00'
    return dict(asset_key=key, project=project, device_kind=kind, from_station=a, from_kv=av,
        to_station=b, to_kv=bv, circuit_id=circuit, documented_event_date=date,
        event_hour_local=hour, date_precision=precision, publication_date_distinct_from_event=1,
        in_service_by_2025_year_end=int(year_end), eligible_all_2025=int(whole_year),
        conservative_scenario_activation_local=activation,
        activation_policy='exact_operator_HB' if hour else 'next_month_if_month_only_not_observed_hour' if precision=='month' and date[:4]=='2025' else 'next_day_if_day_only_not_observed_hour' if date[:4] == '2025' else 'already_in_service_before_2025',
        chronology_is_availability_telemetry=0, source_ids=sources, supported_fact=claim,
        recommended_action=action, scope_recommendation=scope, route_length_miles=length,
        parameters_supported=parameters, r_x_b_asbuilt_available=0,
        par_tap_or_angle_schedule_available=0, physical_thermal_rating_certified=0,
        parent_branch_replacement_proven=0,
        parent_overlap_policy='explicit_source_to_parent_functional_ledger_required_no_automatic_parallel_addition',
        limitations=notes or 'Source supports physical identity and chronology; historical/proxy electrical parameters must remain labeled assumptions.')


def upgrades():
    r=[]
    for project, date, a, b, feeder, transformer, par in [
        ('RCC_Rainey_Corona','2023-05-03','Rainey','Corona','36188','5W','R5W'),
        ('RCC_Gowanus_Greenwood','2025-05-20','Gowanus','Greenwood','42233','BkT20','R20'),
        ('RCC_Goethals_FoxHills','2025-05-29','Goethals','Fox Hills','39291','BkT6','P6')]:
        sid='RCC_QUEENS_OWNER|NYISO_WINTER2023' if a=='Rainey' else 'NYISO_MAY2025_OPS|RCC_MAY_OWNER'
        lengths={'Rainey':6,'Gowanus':1,'Goethals':9}
        common=dict(date=date, precision='day', sources=sid,
            claim='Operator reports new PAR-controlled feeder, transformer and PAR in service; owner corroborates underground route.')
        r.append(component(project+':FEEDER',project,'underground_cable',a+'138',138,b,138,feeder,
            **common,length=lengths[a],notes='RCC Goethals length is just over9mi;300MWpublictransfer capability is not an as-built MVA rating. Existing parallel feeders remain distinct.'))
        r.append(component(project+':TRANSFORMER',project,'transformer',a,345,a+'138',138,transformer,**common))
        r.append(component(project+':PAR',project,'phase_angle_regulator',a+'138',138,a+'138PAR',138,par,**common))
    cvsrc='NYISO_CV_2020_STABILITY|NYISO_CRP2021_FACILITIES'
    r.extend([
        component('CV:F83','Cricket_Valley_2020','overhead_line','Pleasant Valley',345,'Cricket Valley',345,'F83','2020','year',cvsrc,
            'OldPleasantValley-LongMountain398 terminated atCV; westernsegmentrenamedF83',action='resegment_existing_398_western_function',length=14.6),
        component('CV:F84','Cricket_Valley_2020','overhead_line','Pleasant Valley',345,'Cricket Valley',345,'F84','2020','year',cvsrc,
            'Newparallel345kVlineF84installedPVtoCV',length=14.6),
        component('CV:398_PRE_DOVER','Cricket_Valley_2020','overhead_line','Cricket Valley',345,'Long Mountain',345,'398','2020','year',cvsrc,
            'Existing398easternsegmentnowterminatesCV; retaineduntilDovercut-in',action='resegment_existing_398_eastern_function',
            notes='NY-NEinterfacecut before2025-12-19HB23 isCV-LongMountain398; do not add this in parallel to its unsegmented parentfunction.'),
    ])
    for key, a, b, kind, ckt in [('Y17','Cricket Valley','Dover','overhead_line','Y17'),
                                ('398','Dover','Long Mountain','overhead_line','398'),
                                ('PAR_A','Dover','Dover','phase_angle_regulator','T398-A'),
                                ('PAR_B','Dover','Dover','phase_angle_regulator','T398-B')]:
        r.append(component('DOVER:'+key,'Dover_Segment_B_final',''+kind,a,345,b,345,ckt,'2025-12-19','day',
            'NYISO_DEC2025_OPS|NYISO_SUMMER2025','Operatoractualservice2025-12-19HB23;summerstudywasplannedmodelinclusion',
            action='replace_pre_Dover_CV_LongMountain_function',scope='late_2025_separate_chronology',hour='HB23',
            notes='NY-NEcutmustmovefromCV-LongMountain398toDover-LongMountain398. TwoPARbanksidentified; exactinternalseries/parallelbusbarconfigurationandanglesnotresolved.'))
    r.extend([
      component('NYES:KNICKERBOCKER','NYES_core','switching_station','New Scotland-Alps line2',345,'Knickerbocker',345,'#2 cut-in','2023-08-16','day',
        'NYES_COMPLETION|NYES_EMCP|NYES_2023_OWNER_REPORT','NewKnickerbocker345switchingstationreceivesexistingNewScotland-Alps#2',scope='upstream_feed_separate_stage'),
      component('NYES:KB_PV345','NYES_core','overhead_line','Knickerbocker',345,'Pleasant Valley',345,'NYES345','2023-08-16','day',
        'NYES_COMPLETION|NYES_EMCP|NYES_2023_OWNER_REPORT','New54.5mi345kVlineco-locatedwithrebuilt115kVcircuit',scope='upstream_feed_separate_stage',length=54.5),
      component('NYES:CHURCHTOWN115','NYES_core','switching_station','Churchtown',115,'Churchtown',115,'5-terminal breaker-and-half','2023-08-16','day',
        'NYES_EMCP|NYES_2023_OWNER_REPORT','Churchtownstationis115kV; corridorpassingthroughdoesnotestablishChurchtown345bus',
        action='replace_115kV_station_role_not_invent_345_terminal',scope='upstream_feed_separate_stage'),
      component('NYES:SERIES_COMP','NYES_core','series_compensation','Knickerbocker',345,'NYES345',345,'50percent design compensation','2023-08-16','day',
        'NYES_EMCP|NYES_2023_OWNER_REPORT','Ownerdesignstates50percentseriescompensationequipment',scope='upstream_feed_separate_stage',
        parameters='nominal345kV_design50percentcompensation;deviceohmicXandhourlybypassstateunverified'),
      component('NYES:VAN_WAGNER','NYES_core','series_capacitor_station','Pleasant Valley',345,'Van Wagner',345,'two345kVleadcircuits','2023-08-16','day',
        'NYES_EMCP|NYES_2023_OWNER_REPORT','0.8mi two345kVcircuitsleadtoVanWagnercapacitorstation',scope='upstream_feed_separate_stage',length=.8),
    ])
    for key,a,b,count,length in [('EDIC_PRINCETOWN','Edic','Princetown',2,67),('PRINCETOWN_NS','Princetown','New Scotland',2,20.2),
                                ('GORDON_PRINCETOWN','Gordon Road','Princetown',1,5.3),('PRINCETOWN_NS_EXISTING','Princetown','New Scotland',1,19.8)]:
        r.append(component('CEEC:'+key,'CEEC_2023','overhead_line_group',a,345,b,345,f'{count} circuits','2023-12-13','day',
            'CEEC_COMPLETION|NYISO_GOLDBOOK2024',f'GoldBook2024retrospectiveinservice2023: {count}circuits;physicalprojectcompletedDecember2023',
            scope='upstream_feed_separate_stage',length=length,
            parameters='terminal345kV_circuitcount_length_conductorfamily_GoldBookampere_ratings;R_X_Bunavailable',
            notes='ParentPorter-RotterdamandEdic-NewScotlandaggregatefunctionsneedexplicitretained/replacedledger. PlainGoldBookthermalratingnumbersareamperesnotMVA.'))
    # Partial SPC is registered but deliberately not conflated with Downstate refinement.
    old = csvrows(ROOT / 'output/compact_ny_2025/partial_spc/partial_spc_commissioning_register.csv')
    for d in old:
        if d['asset_key'] == 'SPC_XFMR_2025':
            a,b,av,bv='Haverstock/WillisAnnex','Haverstock/WillisAnnex',345,230
        else:
            names={'SPC_MH2':('Moses','Haverstock'), 'SPC_MH3':('Moses','Haverstock'),
                   'SPC_HA2':('Haverstock','Adirondack'), 'SPC_HW2':('Haverstock','WillisAnnex'),
                   'SPC_LINE11':('Austin Road','Edic'), 'SPC_LINE13':('Adirondack','Austin Road')}
            a,b=names[d['asset_key']];av=bv=int(d['nominal_voltage_kv'])
        evidence=d['source_ids'].replace(';','|').replace('NYISO_OCT_OPERATIONS','NYISO_OCT2025_OPS').replace('NYISO_2025_GOLD_BOOK','NYISO_GOLDBOOK2025')
        r.append(component(d['asset_key'],'Smart_Path_Connect_partial2025','line_or_transformer',a,av,b,bv,d['component'],
            d['documented_event_date'],d['date_precision'],evidence,
            'Cachedprimaryowner/operatorenergizationnotice;partial2025componentnotfullproject',
            scope='exclude_from_core_downstate_use_separate_upstate_sensitivity',
            notes='Noautomaticretirementofparentaggregatepaths;HA1andLine12notenergizeduntil2026. Historical230kVperunitvaluescannotbevoltage-relabeledwithoutbaseconversion.'))
    return r


def landing_rows():
    fleet=csvrows(ROOT/'output/nygrid_2025_dispatch/fleet/fleet_register.csv')
    rows=[]
    for d in fleet:
        pid=int(d['plant_id']);gid=d['eia_generator_id']
        if d['dispatch_eligible_default']!='1':continue
        a=kv=evidence=certainty=limit='';move=1
        if pid==56964:a,kv,evidence,certainty='Gowanus',345,'BAYONNE_POI','physical_POI_verified'
        elif pid==50006:a,kv,evidence,certainty='Goethals',345,'LINDEN_POI|LINDEN_VFT_SEPARATION','physical_NYISO_delivery_terminal_verified'
        elif pid==57185:a,kv,evidence,certainty='Cricket Valley',345,'NYISO_CV_2020_STABILITY|NYISO_CRP2021_FACILITIES','physical_POI_verified'
        elif pid==65561:a,kv,evidence,certainty='East Hampton',69,'SOUTH_FORK_POI|SOUTH_FORK_COMPLETION','physical_POI_verified'
        elif pid==57664:a,kv,evidence,certainty='NYPA Annex',345,'ASTORIA_II_LGIA','physical_POI_verified_historical_interconnection'
        elif pid==2500 and gid in {'1','2'}:a,kv,evidence,certainty='Vernon',138,'NYISO_CRP2021_FACILITIES','historical_unit_terminal_verified'
        elif pid==2500 and gid=='3':a,kv,evidence,certainty='Rainey',345,'NYISO_CRP2021_FACILITIES','historical_unit_terminal_verified'
        elif pid==2500 and gid in {'4','4S'}:a,kv,evidence,certainty='Rainey',345,'NYISO_CLASS2001','historical_project_POI_verified'
        elif pid==2490 and gid=='3':a,kv,evidence,certainty='Fresh Kills',345,'NYISO_CRP2021_FACILITIES','historical_unit_terminal_verified'
        elif pid==2490 and gid=='2':a,kv,evidence,certainty='Fresh Kills',138,'NYISO_CRP2021_FACILITIES','historical_unit_terminal_verified'
        elif pid==55375:a,kv,evidence,certainty='Astoria East',138,'NYISO_CLASS2001','historical_project_POI_verified'
        elif pid==56196:a,kv,evidence,certainty='Astoria East / Astoria West',138,'NYISO_CLASS2001','historical_project_two_terminal_split_unresolved';move=0
        elif pid==2493:a,kv,evidence,certainty='East River / East 13th Street','69|138','NYISO_CLASS2001','plant_voltage_levels_supported_unit_split_unresolved';move=0
        elif pid in {2494,2499}:a,kv,evidence,certainty='Greenwood',138,'CONED_JAN2025_LTP','transmission_load_area_delivery_supported_exact_barge_terminal_unresolved';move=0
        elif pid in {8906,54914,2490}:
            a,kv,evidence,certainty='unresolved','','EIA860_2025_FLEET','requires_unit_terminal_primary_crosswalk';move=0
        else:continue
        if pid==65561:limit='138kVexport-to69kVinterconnectionrequiresvoltageinterface;EastHampton69upstreamnetworknotresolvedbyNorthport138proxy'
        elif pid==50006:limit='ExcludeGTG6PJM; nativeinjectionseparatefromPJM_VFTschedule; site-toGoethalsconnectionnotanextraPJMimport'
        elif pid==57185:limit='PreserveF83/F84anddated398/Doverinterfacecut;baselinebus73isPleasantValleyproxy'
        elif pid==57664:limit='AstoriaII345AnnexisnotAstoriaIEast138;historicalLGIAparametersnotautomatically2025verified'
        else:limit='PreserveunitMWonce; existingbus82AK3and79RAVA3arecoarsegeneratorproxiesnotgenericNYCgridbuses; networkattachmentparametersremainseparate'
        rows.append(dict(fleet_id=d['fleet_id'],device_key=d['device_key'],plant_id=pid,eia_generator_id=gid,plant_name=d['plant_name'],
            inventory_state=d['inventory_state'],source_zone=d['zone'],baseline_bus_id=d['bus_id'],
            source_backed_receiving_station=a,receiving_voltage_kv=kv,landing_evidence_level=certainty,
            may_move_after_network_attachment_verified=move,source_ids=evidence,annual_dispatch_mw_reestimated=0,
            generation_count_policy='one_original_fleet_key_one_injection_never_add_duplicate_generator',limitations=limit))
    return rows


def merchant_landings():
    records=[
      ('HTP','SCH - PJM_HTP',3,81,'PJM','Bergen',230,'West 49th Street',345,'back_to_back_converter_plus_345kV_AC_cable','HTP_NYISO_2013|NYISO_RNA2012_TERMINALS',
       'Standalonefixedschedule; anylaterremapmustretainMWandPJMregionalaccountingonce'),
      ('NEPTUNE','SCH - PJM_NEPTUNE',2,79,'PJM','Sayreville',230,'Newbridge Road',345,'HVDC_500kV_with_AC_terminal_cables','NEPTUNE_OWNER_CABLE',
       'Standalonefixedschedule;baseline79is22kVregionalproxy;physicalNYreceivingterminal345kV'),
      ('CSC','SCH - NPX_CSC',1,80,'ISONE','New Haven Harbor',345,'Shoreham',138,'HVDC','CSC_NYISO_2018',
       'BaselineDCrow1combinesCSC_and1385;splitonlyusingoriginalindividualhourlychannelsandpreservecombinedsum'),
      ('1385','SCH - NPX_1385',1,80,'ISONE','Norwalk Harbor',138,'Northport',138,'AC_cable_represented_by_ideal_controlled_transfer','NYISO_CRP2021_FACILITIES',
       'BaselineDCrow1combinesCSC_and1385;1385isnotphysicalHVDC;splitmustnotduplicatefullcombinedschedule'),
      ('LINDEN_VFT','SCH - PJM_VFT',4,81,'PJM','PSEG switching station',230,'Goethals via Linden Cogen ring bus',345,
       'AC_variable_frequency_transformer','LINDEN_POI|LINDEN_VFT_SEPARATION|NYISO_RNA2012_TERMINALS',
       'ExistingGoethalsnamedterminalmayremain;nativeLindenplantgenerationisseparatefromPJM_VFTtransmission'),
    ]
    return [dict(asset_key=k,source_schedule_channel=channel,baseline_dcline_row=row,baseline_NY_bus_id=bus,
        external_region=region,physical_external_station=a,physical_external_ac_kv=av,
        physical_NY_receiving_station=b,physical_NY_receiving_ac_kv=bv,physical_technology=tech,
        source_ids=sid,automatic_remap_authorized=0,main_topology_variant_endpoints_unchanged=1,
        source_hourly_schedule_changes_allowed=0,regional_energy_double_counting_allowed=0,
        exact_asbuilt_impedances_and_controls_verified=0,implementation_condition=note)
        for k,channel,row,bus,region,a,av,b,bv,tech,sid,note in records]


def historical_templates():
    """Extract requested historical template provenance without adopting it."""
    workbook=ROOT/'PERFORM/Auxilliary_Perform_NY/Branch_changes_2019_to_2030.xlsx'
    w=openpyxl.load_workbook(workbook,read_only=True,data_only=True)
    try:
        ws=w['2019 On Peak'];headers=None;matches=[]
        for i,values in enumerate(ws.values,1):
            if i==2:headers=list(values)
            elif i>2 and values[0]=='800_1233_1':
                matches.append((i,dict(zip(headers,values))))
        if len(matches)!=1:raise ValueError('Historical345kVtemplateidentitynotunique')
        line,d=matches[0]
        if d['Length, Estimated from X and B (Miles)']!=112.3:raise ValueError('Historicaltemplatelengthchanged')
        write_csv(OUT/'historical_parameter_template_register.csv',[dict(template_key=d['ID'],source_path=workbook.relative_to(ROOT).as_posix(),
            source_sha256=sha(workbook),source_sheet='2019 On Peak',source_excel_row=line,
            from_bus=d['From Number'],from_name=d['From Name'],to_bus=d['To Number'],to_name=d['To Name'],
            from_kv=d['From Nom kV'],to_kv=d['To Nom kV'],r_pu=d['R'],x_pu=d['X'],b_pu=d['B'],
            rateA_MVA=d['Lim MVA A'],rateB_MVA=d['Lim MVA B'],rateC_MVA=d['Lim MVA C'],
            geographic_station_distance_miles=d['Distance Between Substations (Miles)'],
            electrical_estimated_length_miles=d['Length, Estimated from X and B (Miles)'],
            new_project_parameters_verified=0,per_mile_reuse_policy='112.3mileelectricalestimatedlength;newprojectparametersremainhistoricaltemplateassumptions_not_asbuilt')])
    finally:w.close()
    bp=ROOT/'tmp/contemporary_sources/inventory_export_check/perform_ny_bus_inventory.csv'
    ep=ROOT/'tmp/contemporary_sources/inventory_export_check/perform_ny_branch_inventory.csv'
    buses=csvrows(bp);branches=csvrows(ep);names={int(x['source_bus']):x['source_bus_name'] for x in buses}
    connections=[]
    for r in branches:
        if int(r['source_from_bus'])==1133 or int(r['source_to_bus'])==1133:
            connections.append(dict(**r,from_name=names[int(r['source_from_bus'])],to_name=names[int(r['source_to_bus'])],
                reuse_status='historicalsourceparameters_not2025asbuiltcertification',source_register_sha256=sha(ep)))
    write_csv(OUT/'vernon_historical_connection_register.csv',connections)
    write_csv(OUT/'station_alias_cautions.csv',[
        dict(source_bus='1133',source_name='VERNON',source_kv=138,physical_station='Vernon138',identity_status='literal_named_source_station'),
        dict(source_bus='26',source_name='UNKNOWN124169',source_kv=345,physical_station='unverified',identity_status='cannot_certify_NYPAAnnex_from_unknown_source_name'),
        dict(source_bus='',source_name='',source_kv='138|345',physical_station='FreshKills',identity_status='no_literal_FreshKills_name_in_reviewed_source_bus_inventory_do_not_guess_alias'),
    ])
    return [workbook,bp,ep]


def main(fetch=False):
    OUT.mkdir(parents=True,exist_ok=True)
    current=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    # Subsequent commits may contain this audit. Pin the actual baseline inputs,
    # rather than making the documented audit impossible to rerun after commit.
    if subprocess.run(['git','merge-base','--is-ancestor',BASELINE,current],cwd=ROOT,capture_output=True).returncode:
        raise ValueError('Pinned baseline is not an ancestor of this checkout')
    for relative in ['output/nygrid_2025_dispatch/fleet/fleet_register.csv',
                     'output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv']:
        original=subprocess.check_output(['git','show',BASELINE+':'+relative],cwd=ROOT).decode('utf-8-sig')
        if list(csv.DictReader(io.StringIO(original))) != csvrows(ROOT/relative):
            raise ValueError('Pinned baseline table changed: '+relative)
    # Append exact cached SPC owner receipts; no dependency on old assumed circuits.
    registry=csvrows(ROOT/'output/compact_ny_2025/sources/infrastructure_status_source_manifest.csv')
    wanted={'SPC_HA2','SPC_LINE11','SPC_LINE13','SPC_MH2','SPC_MH3','SPC_HW2','NYISO_20251107_TTC'}
    specs=list(SOURCES)
    for x in registry:
        if x['source_id'] in wanted:
            p=ROOT/x['cache_path']
            if sha(p)!=x['sha256']:raise ValueError('Cached primary SPC receipt changed')
            specs.append(source(x['source_id'],x['publisher'],x['publication_date'],x['source_url'],p.name,
                x['verification'],x['cache_path'],fresh=False))
    with ThreadPoolExecutor(max_workers=5) as pool:
        receipts=list(pool.map(lambda x:preserve_source(x,fetch),specs))
    eia=ROOT/'tmp/nonfossil_sources/eia860_2025/3_1_Generator_Y2025_Early_Release.xlsx'
    receipts.append(dict(source_id='EIA860_2025_FLEET',publisher='EIA',publication_date='2026_early_release_for_2025',
        source_url='https://www.eia.gov/electricity/data/eia860/xls/eia8602025ER.zip',
        evidence_role='Unit identity/status/capability; not exact unit-level electrical interconnection',
        cache_path=eia.relative_to(ROOT).as_posix(),fresh_web_reviewed=False,checked_on=CHECKED,primary_source=1,
        baseline_commit=BASELINE,byte_origin='existing_pinned_primary_workbook_reference',local_path=eia.relative_to(ROOT).as_posix(),
        sha256=sha(eia),bytes=eia.stat().st_size))
    write_csv(OUT/'source_receipts.csv',receipts)
    register=upgrades();write_csv(OUT/'upgrade_register.csv',register)
    landings=landing_rows();write_csv(OUT/'asset_landing_crosswalk.csv',landings)
    merchant=merchant_landings();write_csv(OUT/'merchant_boundary_landing_crosswalk.csv',merchant)
    templates=historical_templates()
    known={x['source_id'] for x in receipts}
    for row in register+landings+merchant:
        for sid in row['source_ids'].split('|'):
            if sid not in known:raise ValueError('Unregistered evidence source '+sid)
    exclusions=[
      dict(project='CHPE',exclude_2025=1,reason='commercialoperation2026; no2025operatinginjection_or_newnetworkpath'),
      dict(project='Propel_NY',exclude_2025=1,reason='futureproject_not2025operatingnetwork'),
      dict(project='RCC_Vernon_Newtown',exclude_2025=1,reason='separate2026LICproject_not2023RaineyCorona'),
      dict(project='SPC_HA1_Line12',exclude_2025=1,reason='owneractualenergizationMarch2026;partialSPC2025isnotwholeproject'),
      dict(project='Dover_before_2025_12_19_HB23',exclude_2025=0,reason='excludeuntilactualoperatorcommissioning;summerstudyforecastdoesnotoverrideDecemberevent'),
    ];write_csv(OUT/'excluded_or_deferred_projects.csv',exclusions)
    dependencies=[ROOT/'output/nygrid_2025_dispatch/fleet/fleet_register.csv',
                  ROOT/'output/nygrid_2025_dispatch/fleet/source_parent/npcc.csv',Path(__file__)] + templates
    write_csv(OUT/'audit_dependencies.csv',[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in dependencies])
    summary=dict(status='primary_evidence_registered_not_asbuilt_electrical_model_certification',baseline_commit=BASELINE,
        audit_run_git_head=current,baseline_input_tables_verified_against_commit=True,
        checked_on=CHECKED,upgrade_records=len(register),asset_landing_records=len(landings),source_receipts=len(receipts),
        merchant_boundary_landing_records=len(merchant),merchant_remap_status='optional_evidence_only_no_model_endpoint_changes',
        sources_with_local_bytes=sum(bool(x['sha256']) for x in receipts),sources_without_local_bytes=[x['source_id'] for x in receipts if not x['sha256']],
        all_2025_core=['Rainey-Corona2023','NYEScore2023','CEEC2023','CricketValley2020topology','SouthFork2024POI'],
        dated_2025_core=['Gowanus-Greenwood2025-05-20','Goethals-FoxHills2025-05-29'],
        late_2025_only=['DoverY17_398_T398A_T398B2025-12-19HB23'],
        separate_upstate_sensitivity='partialSPCcomponentswithowneractualdates;notwhole2026project',
        constructible_now='physicalstation/circuit/voltage/statusschemaandconservativechronology;largesource-backedgenerationlandingimprovements',
        assumptions_required='R_X_B,newcableandtransformerparameters,PARschedules,aggregate-to-physicalreplacementledger,andmostphysicalterminalratings',
        important_corrections=['Churchtownstation115not345','AstoriaEnergyIIAnnex345distinctfromAstoriaIEast138',
          'SouthForkEastHampton69notNorthport138','Ravenswood1_2Vernon138versus3Rainey345',
          '300MWprojectbenefitnot300MVAequipmentrating','DoveractualDecemberdateoverridessummerforecast'],
        fitted_to_interface_observations=False,baseline_files_modified=False)
    (OUT/'scope_recommendation.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fetch',action='store_true');args=p.parse_args();main(args.fetch)
