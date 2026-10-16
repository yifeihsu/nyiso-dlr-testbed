"""Current AC topology and qualified geographic anchors for an offline map.

No old DC-equivalent edges, geographical route inference, invented proxy
coordinates, source changes or HTML generation occur in this builder.
"""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import csv,hashlib,io,json,math,subprocess,zipfile

import numpy as np
import pandas as pd
from scipy.io import loadmat
from pyproj import CRS,Transformer

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_latest_map'
STRUCTURE=ROOT/'output/nygrid_2025_latest_handoff/structure_inputs'
GEO=ROOT/'output/nygrid_2025_downstate/geography/bus_geographic_register.csv'
OLD_MAP=ROOT/'output/nygrid_2025_slim/interactive/map_data.json'
BASEMAP=ROOT/'output/nygrid_2025_downstate/geography/basemap'
REGISTRY=ROOT/'output/nygrid_2025_ac_system/branches/branch_assignments.csv'
CONFLICTS=ROOT/'output/nygrid_2025_acpf_profile_audit/structure/overhead_cable_classification_conflicts.csv'
CURRENT=ROOT/'output/nygrid_2025_latest_handoff/structure/current_structure_inventory.json'
ZONE_SOURCE=ROOT/'output/nygrid_2025_inputs/load_source/raw/20250101palIntegrated_csv.zip'
STATES=['pre_may','may21','may30','post_dover']
CRS_TEXT='+proj=lcc +lat_1=40 +lat_2=45 +lat_0=42 +lon_0=-76 +datum=WGS84 +units=m +no_defs'
PROJ=Transformer.from_crs('EPSG:4326',CRS.from_proj4(CRS_TEXT),always_xy=True)
PROXIES={78,79,82}
ZONE_NAMES=dict(zip('ABCDEFGHIJK',['West','Genesee','Central','North','Mohawk Valley','Capital','Hudson Valley','Millwood','Dunwoodie','New York City','Long Island']))
ZONE_CODES=dict(zip('ABCDEFGHIJK',['WEST','GENESE','CENTRL','NORTH','MHK VL','CAPITL','HUD VL','MILLWD','DUNWOD','N.Y.C.','LONGIL']))


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def record(path):return dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(path))
def native_bool(value):return str(value).lower() in ['true','1']
def xy(lon,lat):
    x,y=PROJ.transform(float(lon),float(lat));return [round(x/1000,6),round(-y/1000,6)]
def category(kind):
    if kind in ['synthetic_overhead_corridor','design_based_overhead']:return 'overhead'
    if 'cable' in kind or kind=='urban_non_OH_network_equivalent':return 'cable'
    if kind=='PAR':return 'par'
    if kind=='station_transformer_compatible_equivalent':return 'transformer'
    if kind=='composite_voltage_changing_equivalent':return 'composite'
    if kind=='inactive_provenance':return 'inactiveRecord'
    return 'equivalent'


def bounds(points,padding=.08):
    a=np.asarray(points,float);lo=a.min(axis=0);hi=a.max(axis=0);span=np.maximum(hi-lo,1)
    return [float(lo[0]-padding*span[0]),float(lo[1]-padding*span[1]),float(hi[0]+padding*span[0]),float(hi[1]+padding*span[1])]


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    inventory=json.loads(CURRENT.read_text());old=json.loads(OLD_MAP.read_text());basemap_receipt=json.loads((BASEMAP/'basemap_receipt.json').read_text())
    assert old['projection']==CRS_TEXT and len(old['basemap'])==3
    geo=pd.read_csv(GEO,keep_default_na=False,float_precision='round_trip').set_index('model_bus')
    registry=pd.read_csv(REGISTRY,keep_default_na=False,float_precision='round_trip').set_index('branch_row')
    conflicts=pd.read_csv(CONFLICTS,keep_default_na=False).set_index('branch_row')
    assert set(conflicts.index)=={300,309,310,386}
    assert len(geo)==191 and geo.index.is_unique
    sources=[GEO,OLD_MAP,REGISTRY,CONFLICTS,CURRENT,BASEMAP/'basemap_receipt.json',ZONE_SOURCE]
    sources.extend(BASEMAP/(name+'_npcc.geojson') for name in ['ne_10m_land','ne_10m_lakes','ne_10m_admin_1_states_provinces_lines'])
    cases={};eligibility={}
    for state in STATES:
        p=STRUCTURE/(state+'.mat');cases[state]=loadmat(p,simplify_cells=True);sources.append(p)
        p=STRUCTURE/(state+'_thermal_eligibility.csv');eligibility[state]=pd.read_csv(p).set_index('original_parent_row');sources.append(p)
    before=[record(p) for p in sources]
    latest=cases['post_dover'];canonical_ids=np.asarray(latest['bus'][:,0]).astype(int)
    names=dict(zip(canonical_ids,np.asarray(latest['bus_name']).astype(str)))
    retained_ids=np.asarray(latest['retained_ids']).astype(int);retained=set(retained_ids)
    latest_rows={bid:i for i,bid in enumerate(canonical_ids)}
    group=np.asarray(latest['bus_group']).astype(int);labels=np.asarray(latest['group_labels']).astype(str)
    numerical=set(canonical_ids)-set(geo.index)-{21001};assert len(numerical)==75
    present={state:set(np.asarray(c['bus'][:,0]).astype(int)) for state,c in cases.items()}
    nodes=[];by_id={}
    for bid in canonical_ids:
        bid=int(bid);j=latest_rows[bid];g=int(group[j]);zone=labels[g-1] if g else 'PASSIVE_INTERIOR'
        n=dict(id=bid,name=names[bid],kv=float(latest['bus'][j,9]),zone=str(zone),retained=bid in retained,
            role='retainedBus' if bid in retained else 'stationPort',
            xy=None,lonlat=None,lon=None,lat=None,displayAnchorOf=None,
            presenceByState={state:bid in present[state] for state in STATES},
            coordinateBasis='',quality='',source='',coordinateSourceModelName='',
            geographicCoordinateAssigned=False,displayLocationClaim='none')
        if bid in geo.index:
            row=geo.loc[bid];n.update(coordinateBasis=str(row.coordinate_basis),quality=str(row.coordinate_quality),
                source=str(row.coordinate_source),coordinateSourceModelName=str(row.model_name),coordinateNotes=str(row.notes),
                mapAnchorPolicy=str(row.map_anchor_policy))
            if native_bool(row.plot_on_geographic_map):
                lon=float(row.map_longitude_deg);lat=float(row.map_latitude_deg)
                assert math.isfinite(lon) and math.isfinite(lat)
                n.update(xy=xy(lon,lat),lonlat=[lon,lat],lon=lon,lat=lat,geographicCoordinateAssigned=True,
                    displayLocationClaim='approximateSourceModelPoint' if row.coordinate_basis=='published_NPCC_model_point' else 'sourceStationOrFacilityAnchor')
            else:
                assert bid in PROXIES
                n.update(role='unlocatedAggregateProxy',displayLocationClaim='nongeographicProxy')
        elif bid in numerical:
            incident=np.flatnonzero((latest['branch'][:,0]==bid)|(latest['branch'][:,1]==bid))
            parents=set(np.asarray(latest['branch_parent_row'])[incident].astype(int));assert len(parents)==1
            n.update(role='numericalSectionBus',parentId=int(next(iter(parents))),
                coordinateBasis='no_geographic_meaning_for_numerical_section_bus',
                quality='computational_discretization_only',source='current_case_section_map',
                displayLocationClaim='notGeographic;collapsedInParentCorridorView')
        else:
            assert bid==21001
            n.update(role='regulatedAuxiliaryPort',displayAnchorOf=20003,
                coordinateBasis='co_located_model_auxiliary_anchor',quality='display_anchor_not_independent_station_coordinate',
                source='current_PAR_endpoint_topology_20003_to_21001',
                displayLocationClaim='coLocatedModelPortAtSourceAnchor20003')
        nodes.append(n);by_id[bid]=n
    by_id[21001]['xy']=list(by_id[20003]['xy'])
    assert by_id[21001]['lonlat'] is None
    assert all(by_id[b]['xy'] is None and by_id[b]['lonlat'] is None for b in PROXIES|numerical)
    # Every retained coordinate and original basemap path must remain exact.
    for n in old['nodes']:
        assert by_id[int(n['id'])]['xy']==n['xy'],n['id']
        if n['xy'] is not None:
            assert by_id[int(n['id'])]['lon']==n['lon'] and by_id[int(n['id'])]['lat']==n['lat']

    parents={};transfers={};couplings={};state_info=[]
    transfer_names=['CSC','NEPTUNE','HTP','VFT','ONTARIO PAR 25118','ONTARIO PAR 25119']
    for state,c in cases.items():
        br=np.asarray(c['branch']);par=np.asarray(c['branch_parent_row']).astype(int);maps=c['branch_map'];keys=np.asarray(c['branch_keys']).astype(str)
        current_ids=np.asarray(c['bus'][:,0]).astype(int);current_lookup={b:j for j,b in enumerate(current_ids)}
        snapshot_hour=int(c['hour']);snapshot_utc=str(c['timestamp_utc'])
        for pp in np.unique(par):
            pp=int(pp);rows=np.flatnonzero(par==pp)
            start=[i for i in rows if maps[i]['physical_terminal_from']];end=[i for i in rows if maps[i]['physical_terminal_to']]
            assert len(start)==len(end)==1
            a=int(br[start[0],0]);b=int(br[end[0],1]);row=registry.loc[pp]
            kind='unresolved_network_equivalent' if pp==224 else str(row.classification)
            if pp not in parents:
                parents[pp]=dict(id=pp,key=str(row.branch_key),a=a,b=b,category=category(kind),classification=kind,
                    displayClassification='Overhead parameter template with documented cable-evidence conflict' if pp in conflicts.index else kind.replace('_',' '),
                    knownCableEvidenceConflict=pp in conflicts.index,
                    cableEvidence=str(conflicts.loc[pp].finding) if pp in conflicts.index else '',
                    cableEvidenceSource=(str(conflicts.loc[pp].source_ids)+' / '+str(conflicts.loc[pp].source_locator)) if pp in conflicts.index else '',
                    mapped=by_id[a]['xy'] is not None and by_id[b]['xy'] is not None,
                    coLocated=by_id[a]['xy'] is not None and by_id[a]['xy']==by_id[b]['xy'],
                    physicalRouteClaim=False,geometryMeaning='schematic_adjacency_between_model_endpoints',
                    parameterAggregation='Sum of runtime-section series R/X and line charging B; bus shunts/reactors are separate; not a newly fitted single-pi equivalent.',
                    sourceRole=str(row.source_role),parameterBasis=str(row.parameter_basis),
                    presenceByState={s:False for s in STATES},stateRecords=[])
            p=parents[pp];assert (p['a'],p['b'])==(a,b);p['presenceByState'][state]=True
            active=br[rows,10]>0;assert active.all() or (~active).all()
            assert a not in numerical and b not in numerical
            ef=eligibility[state].loc[pp]
            p['stateRecords'].append(dict(stateId=state,active=bool(active.all()),rPu=float(br[rows,2].sum()),
                xPu=float(br[rows,3].sum()),bPu=float(br[rows,4].sum()),runtimeRows=(rows+1).astype(int).tolist(),
                runtimeKeys=keys[rows].tolist(),physicalFromRuntimeRow=int(start[0]+1),physicalToRuntimeRow=int(end[0]+1),
                physicalFromRuntimeKey=str(keys[start[0]]),physicalToRuntimeKey=str(keys[end[0]]),
                thermalEligible=bool(ef.research_screen_eligible),
                representativeHour=snapshot_hour,representativeTimestampUtc=snapshot_utc,
                representativePhaseShiftDegrees=br[rows,9].astype(float).tolist(),
                phaseMayVaryByHour=pp in [411,412]))
        for j,line in enumerate(np.asarray(c['dcline'])):
            a=int(line[0]);b=int(line[1]);key=f'DC:{j+1}'
            if key not in transfers:
                transfers[key]=dict(id=j+1,key=key,name=transfer_names[j],a=a,b=b,category='controlledTransfer',
                    mapped=by_id[a]['xy'] is not None and by_id[b]['xy'] is not None,
                    physicalRouteClaim=False,physicalHVDCIdentityClaim=False,positiveDirection='from_to',
                    electricalContainer='MATPOWER_dcline',presenceByState={s:False for s in STATES},stateRecords=[])
            t=transfers[key];assert(t['a'],t['b'])==(a,b);t['presenceByState'][state]=True
            t['stateRecords'].append(dict(stateId=state,active=bool(line[2]),transferRow=j+1,
                declaredRealLossZero=bool(line[15]==0 and line[16]==0),declaredReactiveTransferZero=bool(line[5]==0 and line[6]==0)))
        y=c['Yred'].toarray();rids=np.asarray(c['retained_ids']).astype(int);assert np.array_equal(rids,retained_ids)
        edge_count=0
        for i in range(148):
            for j in range(i+1,148):
                if y[i,j]==0 and y[j,i]==0:continue
                a=int(rids[i]);b=int(rids[j]);key=f'YRED:{a}:{b}';edge_count+=1
                if key not in couplings:
                    couplings[key]=dict(key=key,a=a,b=b,category='complexAdmittanceCoupling',
                        physicalCorridorClaim=False,physicalRouteClaim=False,thermalEligible=False,
                        branchFlowMeaning=False,uniqueParentAssignment=False,
                        mapped=by_id[a]['xy'] is not None and by_id[b]['xy'] is not None,
                        presenceByState={s:False for s in STATES},representativeCoefficients=[])
                edge=couplings[key];edge['presenceByState'][state]=True
                edge['representativeCoefficients'].append(dict(stateId=state,hourIndex=snapshot_hour,timestampUtc=snapshot_utc,
                    yABRealPu=float(y[i,j].real),yABImagPu=float(y[i,j].imag),
                    yBARealPu=float(y[j,i].real),yBAImagPu=float(y[j,i].imag),
                    exactForSelectedMapHour=False,coefficientScope='representative_fixture_only;hourly_control_phases_can_change_values'))
        physical=[b for b in current_ids if b not in numerical]
        source_geo=[b for b in current_ids if by_id[int(b)]['geographicCoordinateAssigned']]
        displayed=[b for b in current_ids if by_id[int(b)]['xy'] is not None]
        state_info.append(dict(id=state,representativeHour=snapshot_hour,representativeTimestampUtc=snapshot_utc,
            detailedBusCount=len(current_ids),retainedBusCount=148,numericalBusCount=len(numerical),
            physicalOrProxyPortCount=len(physical),sourceGeographicPointCount=len(source_geo),displayedAnchorCount=len(displayed),
            retainedGeographicPointCount=sum(by_id[int(b)]['xy'] is not None for b in rids),
            unlocatedProxyIds=sorted(PROXIES),parentRecordCount=len(np.unique(par)),activeParentRecordCount=int(len(set(par[br[:,10]>0]))),
            runtimeBranchCount=len(br),activeRuntimeBranchCount=int((br[:,10]>0).sum()),complexCouplingCount=edge_count,
            fixedTransferCount=6,sourceQualifiedHourCount=next(s['source_qualified_hours'] for s in inventory['topology_windows'] if s['state']==state)))
    assert len(parents)==413 and len(transfers)==6
    # Zone names bind to the frozen primary NYISO source. Label positions use
    # medians of located retained points, not an official geographic boundary.
    with zipfile.ZipFile(ZONE_SOURCE) as z:
        member='20250101palIntegrated.csv';raw=z.read(member)
    primary=pd.read_csv(io.BytesIO(raw));zone_source_names=dict(zip(primary.PTID.astype(int),primary.Name.astype(str)))
    zone_labels=[]
    for j,(zone,name) in enumerate(ZONE_NAMES.items()):
        ptid=61752+j;assert zone_source_names[ptid]==ZONE_CODES[zone]
        members=[n for n in nodes if n['retained'] and n['zone']==zone and n['xy'] is not None]
        all_members=[n['id'] for n in nodes if n['retained'] and n['zone']==zone]
        assert members
        anchor=np.median(np.asarray([n['xy'] for n in members]),axis=0).astype(float).tolist()
        zone_labels.append(dict(id=zone,zone=zone,name=name,label=f'{zone} · {name}',sourceAbbreviation=ZONE_CODES[zone],sourcePTID=ptid,
            xy=anchor,locatedMemberIds=[n['id'] for n in members],retainedMemberIds=all_members,
            omittedUnlocatedMemberIds=sorted(set(all_members)-{n['id'] for n in members}),
            coordinateBasis='median_projected_coordinates_of_located_retained_model_nodes',
            schematicOnly=True,officialZoneBoundary=False,officialZonePolygon=False,
            nameSource=dict(path=ZONE_SOURCE.relative_to(ROOT).as_posix(),member=member,memberSha256=hashlib.sha256(raw).hexdigest())))
    ny_points=[n['xy'] for n in nodes if n['retained'] and n['zone'] in ZONE_NAMES and n['xy'] is not None]
    down_bounds=(-74.43,40.48,-72.60,41.88)
    down_points=[xy(lon,lat) for lon in down_bounds[::2] for lat in down_bounds[1::2]]
    full_points=[n['xy'] for n in nodes if n['xy'] is not None]
    payload=dict(schemaVersion=1,modelYear=2025,modelKind='current_148_retained_voltage_AC_with_detailed_corridor_recovery',
        sourceModelCommit=inventory['model_snapshot_commit'],mapSourceCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        electricalBaseMVA=100,frequencyHz=60,projection=CRS_TEXT,xyUnits='kilometres;SVG_y_is_negative_northing',
        nodes=nodes,parents=list(parents.values()),transfers=list(transfers.values()),couplings=list(couplings.values()),
        states=state_info,basemap=old['basemap'],zoneLabels=zone_labels,
        viewBounds=dict(ny=bounds(ny_points),downstate=bounds(down_points,.02),fullNPCC=bounds(full_points)),
        viewPolicy=dict(default='retainedAC148',retainedAC148='Show retained nodes and complex-Yred mathematical support; never label couplings as physical lines or assign them physical branch flows.',
            detailedCorridors='Show source-positioned station/device ports and parent corridors; collapse numerical section buses while retaining their runtime row/key maps.',
            unlocatedProxies='Keep78/79/82 in search/inspection and nongeographic UI; never plot their archived placeholder coordinates.',
            auxiliary21001='Co-located display anchor of20003, not independently geolocated.',
            numericalNodes='All75 have null coordinates; they are computational line subdivisions, not additional geographical stations.'),
        coordinateCoverage=dict(canonicalBusCount=len(nodes),sourceGeographicPoints=sum(n['geographicCoordinateAssigned'] for n in nodes),
            countsAreBusRecordsNotUniquePhysicalSites=True,
            colocatedDisplayOnlyPorts=[21001],unlocatedAggregateProxies=sorted(PROXIES),numericalNongeographicBuses=len(numerical),
            retainedGeographicPoints=145,retainedNongeographicProxies=3),
        provenance=dict(coordinateSource=record(GEO),basemapSource=basemap_receipt,
            basemapRenderedPathsPreservedExactly=True,retainedCoordinatesPreservedExactly=True,
            coordinateAttribution='Frozen NPCC/PERFORM model or station anchors; owner GIS; © OpenStreetMap contributors (ODbL1.0). Coordinate quality is retained per node.',
            basemapAttribution='Natural Earth / NACIS 1:10m, public domain; geographical context only.',
            geographyIsAsBuilt=False,connectionsAreSurveyedRoutes=False,zoneLabelsAreOfficialPolygons=False,
            oldDCSchurEquivalentEdgesImported=False,newGeocodingPerformed=False))
    assert before==[record(p) for p in sources]
    for state in STATES:
        all_rows=[]
        for p in payload['parents']:
            for sr in p['stateRecords']:
                if sr['stateId']==state:all_rows+=sr['runtimeRows']
        assert sorted(all_rows)==list(range(1,len(cases[state]['branch'])+1))
    assert all(e['category']=='complexAdmittanceCoupling' and not e['branchFlowMeaning'] for e in payload['couplings'])
    path=OUT/'geography_data.json';path.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    receipt=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Current AC topology and qualified source/display coordinate builder; no HTML, physical-route reconstruction or source modification',
        canonical_nodes=len(nodes),parents=len(parents),controlled_transfers=len(transfers),complex_Yred_couplings=len(couplings),
        state_counts=state_info,coordinate_coverage=payload['coordinateCoverage'],
        exact_old_retained_coordinates_and_basemap_paths_preserved=True,
        geographic_proxy_coordinates_invented=False,numerical_bus_coordinates_invented=False,
        all_runtime_branches_accounted_once_by_state_parent=True,
        source_files_unchanged=True,old_map_or_archives_modified=False,
        sources=before+[record(Path(__file__).resolve())],outputs=[record(path)])
    (OUT/'geography_validation.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['sources','outputs']},indent=2))


if __name__=='__main__':build()
