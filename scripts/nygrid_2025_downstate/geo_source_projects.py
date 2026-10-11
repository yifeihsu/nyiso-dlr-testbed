"""Reproducible station-site coordinates for the 13 added project/proxy buses.

Uses saved OpenStreetMap geometries and one official address geocode. No model
bus/branch, baseline, prior-coordinate, or electrical-source file is modified.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import openpyxl
from pyproj import Geod, Transformer

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_downstate/geography/source_project'
CHECKED='2026-10-10'
CENSUS_URL='https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address=2238%20Route%2022%20Dover%20Plains%20NY&benchmark=Public_AR_Current&format=json'
DOVER_NOTICE='https://pub-doverny.escribemeetings.com/filestream.ashx?DocumentId=5604'
SPECS=[
 (20001,'Cricket Valley 345',1075629718,'Cricket Valley Substation','station',None),
 (20002,'Long Mountain 345',139896636,'Long Mountain Substation','station',None),
 (20004,'Knickerbocker 345',1221667976,'Knickerbocker Substation','station',None),
 (20005,'NYPA Annex 345',588777274,'Astoria Annex','station',None),
 (20006,'East Hampton 69',83199928,'East Hampton Substation','station',None),
 (20007,'Greenwood 138',374846762,'Greenwood Substation','station',None),
 (20008,'Fox Hills 138',383102712,'Fox Hill Substation','station',None),
 (20009,'Gowanus PAR 138',383102723,'Gowanus Substation','PAR_host_station',11129),
 (20010,'Goethals PAR 138',383102699,'Goethals Substation','PAR_host_station',81),
 (20012,'Fresh Kills 138',383102717,'Fresh Kills Substation','shared_station_voltage_section',None),
 (20013,'Fresh Kills 345',383102717,'Fresh Kills Substation','shared_station_voltage_section',None),
 (20014,'Rainey PAR 138',108298302,'Rainey Substation','PAR_host_station',11130),
]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_csv(path,rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,keys,lineterminator='\n');w.writeheader();w.writerows(rows)


def polygon_center(elements,way):
    points={int(e['id']):(float(e['lon']),float(e['lat'])) for e in elements if e['type']=='node'}
    coordinates=np.asarray([points[int(n)] for n in way['nodes']],float)
    if not np.array_equal(coordinates[0],coordinates[-1]):raise ValueError('Station footprint must be closed')
    project=Transformer.from_crs(4326,32618,always_xy=True)
    inverse=Transformer.from_crs(32618,4326,always_xy=True)
    x,y=project.transform(coordinates[:,0],coordinates[:,1]);xy=np.column_stack([x,y]);origin=xy[0].copy();xy-=origin
    cross=xy[:-1,0]*xy[1:,1]-xy[1:,0]*xy[:-1,1];twice_area=cross.sum()
    if abs(twice_area)<1:raise ValueError('Degenerate station footprint')
    center=origin+np.array([((xy[:-1,0]+xy[1:,0])*cross).sum(),((xy[:-1,1]+xy[1:,1])*cross).sum()])/(3*twice_area)
    lon,lat=inverse.transform(*center)
    return float(lat),float(lon),float(abs(twice_area)/2),coordinates


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=[];receipts={};features={};geojson=[]
    for bus,label,wayid,expected_name,role,hostbus in SPECS:
        path=OUT/f'osm_way_{wayid}.json';d=json.loads(path.read_bytes())
        way=next(e for e in d['elements'] if e['type']=='way' and e['id']==wayid)
        if way['tags'].get('name')!=expected_name or way['tags'].get('power')!='substation':raise ValueError('Station identity mismatch')
        lat,lon,area,coords=polygon_center(d['elements'],way)
        url=f'https://www.openstreetmap.org/way/{wayid}'
        note='Named open-data station footprint centroid; not surveyed equipment coordinates. OSM electrical tags are not used to change model ratings or topology.'
        if role=='PAR_host_station':note+=' PAR shown at its host station point; no separate regulator yard or exact equipment location claimed.'
        if role=='shared_station_voltage_section':note+=' Fresh Kills138/345 use the same station-site point; distinct bus sections are not separate geographic yards.'
        if bus==20005:note+=' Astoria Annex is the named NYPA345station; no alias to UNKNOWN124169 is asserted.'
        rows.append(dict(model_bus=bus,model_name=label,latitude_deg=lat,longitude_deg=lon,
            coordinate_basis='OSM_station_polygon_centroid_projected_UTM18N_returned_WGS84',
            coordinate_quality='station_site_approximation_not_surveyed',source_url=url,
            source_feature_id=f'way/{wayid}',notes=note,crs='EPSG:4326',source_crs='EPSG:4326',
            geometry_crs_used_for_centroid='EPSG:32618',source_name=way['tags']['name'],
            source_feature_version=way['version'],source_feature_timestamp=way['timestamp'],
            source_voltage_tags=way['tags'].get('voltage',''),source_role=role,
            host_model_bus=hostbus or '',coordinate_checked_on=CHECKED,source_path=path.relative_to(ROOT).as_posix(),
            source_sha256=sha(path),source_polygon_area_m2=area,position_is_equipment_survey=0,
            source_license='OpenStreetMap contributors; ODbL1.0',datum_transform_accuracy_m=''))
        receipts[str(wayid)]=dict(source_id=f'OSM:way:{wayid}',source_url=f'https://api.openstreetmap.org/api/0.6/way/{wayid}/full.json',
            feature_url=url,local_path=path.relative_to(ROOT).as_posix(),sha256=sha(path),bytes=path.stat().st_size,
            checked_on=CHECKED,representation='original_OSM_API_JSON',license='OpenStreetMap contributors; ODbL1.0')
        if wayid not in features:
            geojson.append(dict(type='Feature',properties=dict(osm_way_id=wayid,name=way['tags']['name'],source_url=url,
                centroid_latitude=lat,centroid_longitude=lon,source_version=way['version']),
                geometry=dict(type='Polygon',coordinates=[coords.tolist()])))
        features[wayid]=(lat,lon)
    # New Dover station has no matched OSM station polygon in the reviewed box.
    # Its primary municipal notice supplies a precise street address; the Census
    # service interpolates the position along that address range, not in its yard.
    path=OUT/'dover_address_census.json';d=json.loads(path.read_bytes());matches=d['result']['addressMatches']
    if len(matches)!=1 or matches[0]['matchedAddress']!='2238 STATE RTE 22, DOVER PLAINS, NY, 12522':raise ValueError('Dover exact-address match changed')
    match=matches[0];oldlon,oldlat=match['coordinates']['x'],match['coordinates']['y']
    transform=Transformer.from_crs(4269,4326,always_xy=True)
    lon,lat=transform.transform(oldlon,oldlat);operation=transform.get_last_used_operation()
    rows.append(dict(model_bus=20003,model_name='Dover 345',latitude_deg=lat,longitude_deg=lon,
        coordinate_basis='US_Census_interpolated_primary_project_address_2238_State_Rte22',
        coordinate_quality='approximate_address_location_not_station_footprint',source_url=CENSUS_URL,
        source_feature_id='TIGERLine:'+match['tigerLine']['tigerLineId']+':side:'+match['tigerLine']['side'],
        notes='Primary Town of Dover2024notice identifies NYTranscoDoverSubstation at2238Route22. Census exact street-number match is an interpolated roadside position, not a surveyed substation centroid. OSM did not supply a named matching2025Doverstation polygon. Do not use the rejected Nominatim OldRoute22 road midpoint.',
        crs='EPSG:4326',source_crs='EPSG:4269',geometry_crs_used_for_centroid='not_a_polygon',
        source_name=match['matchedAddress'],source_feature_version='Public_AR_Current benchmark4',source_feature_timestamp='',
        source_voltage_tags='',source_role='primary_project_address_proxy',host_model_bus='',coordinate_checked_on=CHECKED,
        source_path=path.relative_to(ROOT).as_posix(),source_sha256=sha(path),source_polygon_area_m2='',position_is_equipment_survey=0,
        source_license='US Census Bureau public data',datum_transform_accuracy_m=operation.accuracy,
        primary_site_identity_url=DOVER_NOTICE,datum_transform_description=operation.description,
        source_latitude_deg=oldlat,source_longitude_deg=oldlon))
    receipts['DOVER_GEOCODE']=dict(source_id='USCENSUS:Dover2238Route22',source_url=CENSUS_URL,feature_url='',
        local_path=path.relative_to(ROOT).as_posix(),sha256=sha(path),bytes=path.stat().st_size,checked_on=CHECKED,
        representation='original_USCensus_API_JSON',license='US Census public data')
    receipts['DOVER_PRIMARY']=dict(source_id='TOWN_DOVER:Document5604',source_url=DOVER_NOTICE,feature_url='',
        local_path='',sha256='',bytes=0,checked_on=CHECKED,representation='primary_web_index_text_reviewed_direct_download_HTTP403',
        supported_fact='TownofDoverPlanningBoard2024-06-03revisedSEQRA:NYTranscoDoverSubstation2238Route22',license='public_municipal_notice')
    receipts['CENSUS_DATUM']=dict(source_id='USCENSUS:GeocoderFAQ',
        source_url='https://www2.census.gov/geo/pdfs/maps-data/data/FAQ_for_Census_Bureau_Public_Geocoder.pdf',feature_url='',
        local_path='',sha256='',bytes=0,checked_on=CHECKED,representation='official_documentation_web_review',
        supported_fact='GeocoderlatitudelongitudecoordinatesareNAD83;positionsinterpolatedalongaddressranges',license='US Census public data')
    rows.sort(key=lambda r:r['model_bus'])
    expected=set(range(20001,20011))|{20012,20013,20014}
    if {r['model_bus'] for r in rows}!=expected or len(rows)!=13:raise ValueError('Missing or duplicate requested project bus')
    if not all(40<r['latitude_deg']<43 and -75<r['longitude_deg']<-71 for r in rows):raise ValueError('Coordinate range error')
    lookup={r['model_bus']:r for r in rows}
    if (lookup[20012]['latitude_deg'],lookup[20012]['longitude_deg'])!=(lookup[20013]['latitude_deg'],lookup[20013]['longitude_deg']):raise ValueError('FreshKills site should be shared')
    write_csv(OUT/'project_station_coordinates.csv',rows)
    write_csv(OUT/'coordinate_source_receipts.csv',list(receipts.values()))
    (OUT/'station_footprints.geojson').write_text(json.dumps(dict(type='FeatureCollection',features=geojson),indent=2)+'\n',encoding='utf-8')
    # Cross-check the host yard against the exact historical source point. This
    # does not overwrite the original spreadsheet or its coordinate provenance.
    wp=ROOT/'PERFORM/Auxilliary_Perform_NY/NYISO_MOD2MAP.xlsx';w=openpyxl.load_workbook(wp,read_only=True,data_only=True)
    checks=[];headers=None;geod=Geod(ellps='WGS84')
    try:
        for excel_row,values in enumerate(w['BUS SUB'].values,1):
            if headers is None:
                if 'BUSNUM' in values:headers=list(values)
                continue
            d=dict(zip(headers,values))
            mapping={1129:20009,1130:20014,736:20006}
            if d.get('BUSNUM') in mapping:
                target=lookup[mapping[int(d['BUSNUM'])]];_,_,dist=geod.inv(d['LONGITUDE'],d['LATITUDE'],target['longitude_deg'],target['latitude_deg'])
                checks.append(dict(model_bus=target['model_bus'],source_bus=int(d['BUSNUM']),source_name=d['NAME'],source_excel_row=excel_row,
                    source_latitude=d['LATITUDE'],source_longitude=d['LONGITUDE'],selected_latitude=target['latitude_deg'],selected_longitude=target['longitude_deg'],
                    difference_m=dist,interpretation='different_points_within_named_station_site_not_a_survey_accuracy_test',source_path=wp.relative_to(ROOT).as_posix(),source_sha256=sha(wp)))
    finally:w.close()
    write_csv(OUT/'local_coordinate_crosscheck.csv',checks)
    rejected=json.loads((OUT/'dover_address_nominatim.json').read_bytes())
    write_csv(OUT/'rejected_coordinate_candidates.csv',[dict(model_bus=20003,source_feature_id='way/'+str(r['osm_id']),
        latitude=r['lat'],longitude=r['lon'],name=r['display_name'],reason='road_only_OldRoute22_result_no_exact2238address_match_not_project_site') for r in rejected])
    summary=dict(status='complete_13_project_coordinates_with_explicit_precision_status',model_buses=13,osm_station_centroid_rows=12,
        distinct_osm_station_polygons=11,address_approximation_rows=1,address_approximation_bus=20003,crs='EPSG:4326',
        PAR_policy='same_hoststation_centroid_not_separate_equipment_location',FreshKills_policy='138and345sections_share_one_site',
        source_geometry_policy='centroidinUTM18NtheninverseWGS84;notOverpassboundingboxcenter',
        Dover_policy='primarymunicipaladdressplusofficialCensusinterpolation;NAD83toWGS84usingpyproj;lowerprecision_notyardcentroid',
        electrical_model_or_baseline_modified=False,OSM_attribution='Map data copyright OpenStreetMap contributors, ODbL1.0',
        script_sha256=sha(Path(__file__)),records=rows)
    (OUT/'coordinate_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=summary['status'],rows=13,points=[{k:r[k] for k in ['model_bus','latitude_deg','longitude_deg','coordinate_quality']} for r in rows]),indent=2))


if __name__=='__main__':build()
