"""Independent readback of current-map geography, topology and cut bindings."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_latest_map'
STATES=['pre_may','may21','may30','post_dover']


def record(path):
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=digest)


def main():
    path=OUT/'geography_data.json';payload=json.loads(path.read_text(encoding='utf-8'))
    proof_path=OUT/'geography_validation.json';proof=json.loads(proof_path.read_text())
    definition_path=OUT/'interface_definitions.json';definitions=json.loads(definition_path.read_text(encoding='utf-8'))
    assert proof['passed'] and proof['outputs'][0]['sha256']==record(path)['sha256']
    dependencies=[record(p) for p in [path,proof_path,definition_path,Path(__file__).resolve()]]
    for source in proof['sources']:
        assert record(ROOT/source['path'])['sha256']==source['sha256'],source['path']
    nodes={n['id']:n for n in payload['nodes']};parents={p['id']:p for p in payload['parents']}
    assert len(nodes)==267 and len(parents)==413 and len(payload['transfers'])==6 and len(payload['couplings'])==253
    assert len(nodes)==len(payload['nodes']) and len(parents)==len(payload['parents'])
    assert sum(n['retained'] for n in nodes.values())==148
    numerical={i for i,n in nodes.items() if n['role']=='numericalSectionBus'}
    assert len(numerical)==75 and all(nodes[i]['xy'] is None and nodes[i]['lonlat'] is None for i in numerical)
    for i in [78,79,82]:
        assert nodes[i]['role']=='unlocatedAggregateProxy' and nodes[i]['xy'] is None and nodes[i]['lonlat'] is None
        assert not nodes[i]['geographicCoordinateAssigned']
    assert nodes[21001]['displayAnchorOf']==20003 and nodes[21001]['xy']==nodes[20003]['xy'] and nodes[21001]['lonlat'] is None
    assert not nodes[21001]['geographicCoordinateAssigned']
    old=json.loads((ROOT/'output/nygrid_2025_slim/interactive/map_data.json').read_text())
    assert old['projection']==payload['projection'] and old['basemap']==payload['basemap']
    for n in old['nodes']:
        got=nodes[n['id']];assert got['xy']==n['xy']
        if n['xy'] is not None:assert got['lon']==n['lon'] and got['lat']==n['lat']
    assert payload['provenance']['oldDCSchurEquivalentEdgesImported'] is False
    assert {i for i,p in parents.items() if p['knownCableEvidenceConflict']}=={300,309,310,386}
    for i in [300,309,310,386]:
        p=parents[i];assert p['cableEvidence'] and p['cableEvidenceSource'] and 'conflict' in p['displayClassification']
        assert not any(r['thermalEligible'] for r in p['stateRecords'])
    state_checks=[];matrix_error=0.;parameter_error=0.
    for state in STATES:
        source_path=ROOT/'output/nygrid_2025_latest_handoff/structure_inputs'/(state+'.mat')
        source=loadmat(source_path,simplify_cells=True);dependencies.append(record(source_path))
        ids=source['bus'][:,0].astype(int);br=source['branch'];paxis=source['branch_parent_row'].astype(int);keys=source['branch_keys'].astype(str)
        bmap=source['branch_map'];rids=source['retained_ids'].astype(int);group=source['bus_group'];labels=source['group_labels']
        assert {i for i,n in nodes.items() if n['presenceByState'][state]}==set(ids)
        for j,bid in enumerate(ids):
            n=nodes[int(bid)];assert n['name']==source['bus_name'][j] and n['kv']==source['bus'][j,9]
            assert n['retained']==(bid in set(rids))
            expected=labels[int(group[j])-1] if group[j] else 'PASSIVE_INTERIOR'
            assert n['zone']==expected
        covered=[];parent_count=active_count=0
        for parent in parents.values():
            matches=[r for r in parent['stateRecords'] if r['stateId']==state]
            assert len(matches)==int(parent['presenceByState'][state])
            if not matches:continue
            record_state=matches[0];rows=np.flatnonzero(paxis==parent['id'])
            assert record_state['runtimeRows']==(rows+1).tolist() and record_state['runtimeKeys']==keys[rows].tolist()
            first=[j for j in rows if bmap[j]['physical_terminal_from']];last=[j for j in rows if bmap[j]['physical_terminal_to']]
            assert len(first)==len(last)==1
            assert parent['a']==br[first[0],0] and parent['b']==br[last[0],1]
            assert parent['a'] not in numerical and parent['b'] not in numerical
            assert record_state['physicalFromRuntimeKey']==keys[first[0]] and record_state['physicalToRuntimeKey']==keys[last[0]]
            assert record_state['physicalFromRuntimeRow']==first[0]+1 and record_state['physicalToRuntimeRow']==last[0]+1
            for col,name in [(2,'rPu'),(3,'xPu'),(4,'bPu')]:parameter_error=max(parameter_error,abs(br[rows,col].sum()-record_state[name]))
            assert record_state['active']==bool(np.all(br[rows,10]>0))
            assert parent['physicalRouteClaim'] is False
            covered+=record_state['runtimeRows'];parent_count+=1;active_count+=record_state['active']
        assert sorted(covered)==list(range(1,len(br)+1)) and len(covered)==len(set(covered))
        y=source['Yred'].toarray();lookup={int(b):i for i,b in enumerate(rids)};expected_pairs=set()
        for i in range(148):
            for j in range(i+1,148):
                if y[i,j]!=0 or y[j,i]!=0:expected_pairs.add((int(rids[i]),int(rids[j])))
        actual_pairs=set()
        for coupling in payload['couplings']:
            assert not coupling['physicalCorridorClaim'] and not coupling['branchFlowMeaning'] and not coupling['thermalEligible']
            coeff=[v for v in coupling['representativeCoefficients'] if v['stateId']==state]
            assert len(coeff)==int(coupling['presenceByState'][state])
            if not coeff:continue
            actual_pairs.add((coupling['a'],coupling['b']));c=coeff[0];i=lookup[coupling['a']];j=lookup[coupling['b']]
            matrix_error=max(matrix_error,abs(complex(c['yABRealPu'],c['yABImagPu'])-y[i,j]),abs(complex(c['yBARealPu'],c['yBAImagPu'])-y[j,i]))
            assert c['hourIndex']==source['hour'] and not c['exactForSelectedMapHour']
        assert actual_pairs==expected_pairs
        for transfer in payload['transfers']:
            row=source['dcline'][transfer['id']-1]
            assert (transfer['a'],transfer['b'])==(int(row[0]),int(row[1])) and not transfer['physicalHVDCIdentityClaim']
            sr=next(x for x in transfer['stateRecords'] if x['stateId']==state);assert sr['active']==bool(row[2])
        state_checks.append(dict(state=state,bus_count=len(ids),parent_records=parent_count,active_parent_records=int(active_count),
            runtime_branch_rows=len(covered),complex_couplings=len(actual_pairs),passed=True))
    assert parameter_error==0 and matrix_error==0
    zones={z['id']:z for z in definitions['zones']}
    for zone in payload['zoneLabels']:
        assert zone['name']==zones[zone['id']]['display_name'] and zone['sourcePTID']==zones[zone['id']]['PTID']
        assert zone['sourceAbbreviation']==zones[zone['id']]['source_name']
        located=[n['id'] for n in nodes.values() if n['retained'] and n['zone']==zone['id'] and n['xy'] is not None]
        assert sorted(located)==sorted(zone['locatedMemberIds'])
        assert np.array_equal(np.median([nodes[i]['xy'] for i in located],axis=0),zone['xy'])
        assert zone['schematicOnly'] and not zone['officialZoneBoundary'] and not zone['officialZonePolygon']
        assert '\ufffd' not in zone['label']
    member_checks=0;anchor_error=0.
    for interface in definitions['interfaces']:
        o=interface['positive_orientation']
        for member_field,point_field in [('located_source_bus_ids','source_xy'),('located_target_bus_ids','target_xy')]:
            got=np.mean([nodes[i]['xy'] for i in o[member_field]],axis=0)
            anchor_error=max(anchor_error,float(np.max(abs(got-np.asarray(o[point_field])))))
        for state,members in interface['members_by_state'].items():
            for m in members:
                p=parents[m['parent_id']];sr=next(x for x in p['stateRecords'] if x['stateId']==state)
                assert p['key']==m['parent_key'] and (p['a'],p['b'])==(m['from_bus'],m['to_bus'])
                assert sr['active'] and sr['physicalFromRuntimeKey']==m['first_runtime_key'] and sr['physicalToRuntimeKey']==m['last_runtime_key']
                assert sr['physicalFromRuntimeRow']==m['first_runtime_row'] and sr['physicalToRuntimeRow']==m['last_runtime_row']
                oriented=(p['a'],p['b']) if m['coefficient']==1 else (p['b'],p['a'])
                assert oriented==(m['positive_from_bus'],m['positive_to_bus']);member_checks+=1
    assert member_checks==136 and anchor_error<1e-6
    for r in dependencies:assert record(ROOT/r['path'])['sha256']==r['sha256']
    report=dict(passed=True,completed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent current-map coordinate/topology/Yred support and interface geometry readback; no HTML or solver work',
        geography_payload_sha256=record(path)['sha256'],canonical_nodes=267,parent_corridors=413,controlled_transfers=6,union_Yred_couplings=253,
        state_checks=state_checks,all_145_retained_geographic_coordinates_unchanged=True,basemap_paths_unchanged=True,
        aggregate_proxies_without_coordinates=[78,79,82],numerical_nodes_without_coordinates=75,
        auxiliary21001_is_display_anchor_only=True,known_cable_conflicts_qualified_in_display=True,
        maximum_parent_parameter_error_pu=float(parameter_error),maximum_representative_Yred_coefficient_error_pu=float(matrix_error),
        interface_state_member_bindings_checked=member_checks,maximum_interface_anchor_rounding_difference_km=anchor_error,
        zone_names_and_PTIDs_match_primary_source_definition=True,zone_anchors_are_declared_schematic_medians=True,
        physical_routes_official_zone_polygons_or_flows_on_Yred_couplings_claimed=False,
        old_map_archive_and_source_changes=False,remaining_actionable_findings=[],dependencies=dependencies)
    (OUT/'geography_independent_review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='dependencies'},indent=2))


if __name__=='__main__':main()
