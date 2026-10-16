"""Add a source-backed cable review overlay to the frozen current AC map."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import csv, hashlib, json, re

ROOT=Path(__file__).resolve().parents[2]
SRC=Path(__file__).parent
BASE=ROOT/'output/nygrid_2025_moses_repair/delivery/map'
OUT=ROOT/'output/nygrid_2025_cable_review_map'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def record(path):
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(path),bytes=path.stat().st_size)


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path,text):
    staged=path.with_name('.'+path.name+'.rebuild')
    staged.write_text(text,encoding='utf-8',newline='\n')
    staged.replace(path)


def main():
    OUT.mkdir(exist_ok=True)
    pointer=ROOT/'deliverables/CURRENT_NYGRID_MODEL.json'
    current=read(pointer)
    assert current['map']['path']==(BASE/'network_map.html').relative_to(ROOT).as_posix()
    assert sha(BASE/'network_map.html')==current['map']['sha256']
    protected=[pointer,BASE/'network_map.html',BASE/'DELIVERY_MANIFEST.json',
               BASE/'geography_data.json',BASE/'annual_data.json',
               BASE/'interface_definitions.json',BASE/'ny_display_mask.json',
               ROOT/'output/nygrid_2025_moses_repair/model/latest_model.mat']
    before=[record(p) for p in protected]
    geography,annual,interfaces=(read(BASE/p) for p in ['geography_data.json','annual_data.json','interface_definitions.json'])
    assert len(geography['parents'])==413 and len(annual['hours'])==8760
    assert sum(bool(h['qualified']) for h in annual['hours'])==8651
    audit=read(OUT/'cable_audit_recommendations.json')
    assert audit['passed']
    for source in audit['sourceFiles']:
        assert sha(ROOT/source['path'])==source['sha256'], 'Cable audit source changed: '+source['path']
    items=audit['items']
    parents={int(p['id']):p for p in geography['parents']}
    assert len(items)==len({int(p['parentId']) for p in items})
    allowed={'classification_conflict','documented_cable_assumptions','cable_identity_uncertain'}
    for item in items:
        parent=parents[int(item['parentId'])]
        assert item['status'] in allowed and item['priority'] in {'high','review'}
        assert item['reason'] and item['sourceRefs']
        item.update(a=parent['a'],b=parent['b'],key=parent['key'],
                    currentClassification=parent['classification'],
                    parameterBasis=parent['parameterBasis'],
                    presenceByState=parent['presenceByState'],
                    parametersByState={r['stateId']:dict(r=r['rPu'],x=r['xPu'],b=r['bPu'],
                      active=r['active'],overheadDlrEligible=r['thermalEligible']) for r in parent['stateRecords']})
    conflict_ids=sorted(int(i['parentId']) for i in items if i['status']=='classification_conflict')
    assert conflict_ids==[300,309,310,386], conflict_ids
    assert all(not r['thermalEligible'] for i in conflict_ids for r in parents[i]['stateRecords'] if r['active'])
    counts=dict(Counter(i['status'] for i in items))
    review=dict(schemaVersion=1,items=items,summary=dict(total=len(items),byStatus=counts,
        highPriority=sum(i['priority']=='high' for i in items),classificationConflictParentIds=conflict_ids),
        defaultFilter='priority',scope='Model parent records requiring cable-identity or electrical-parameter verification; not confirmed physical cable faults.',
        routeMeaning='Connections are schematic model adjacency; underground/submarine routes are not surveyed.',
        circuitCountWarning='Model rows are not installed-circuit counts. Y49 has two model rows, not evidence of two physical Y49 circuits.',
        parameterMeaning='Runtime R/X/B sums; separate bus shunts and reactors are excluded from branch B. A large B substitution is not a corresponding net reactive-injection multiplier.',
        sourceModelSha256=current['model_receipt']['sha256'],
        compiledModelSha256=annual['metadata']['compiledModelSha256'],
        annualRun=annual['metadata']['annualRun'],sourceAudit='cable_audit_recommendations.json')
    payload=dict(schemaVersion=1,sourceModelCommit=geography['mapSourceCommit'],
                 geography=geography,annual=annual,interfaces=interfaces,cableReview=review)
    compact=json.dumps(payload,separators=(',',':'),ensure_ascii=True,allow_nan=False).replace('<','\\u003c')
    template=(SRC/'map_template.html').read_text(encoding='utf-8')
    mask=read(BASE/'ny_display_mask.json')
    html=template.replace('__NY_MASK_PATH__',mask['svgPath']).replace('__NETWORK_DATA__',compact)
    html=html.replace('__MAP_CSS__',(SRC/'map.css').read_text(encoding='utf-8'))
    html=html.replace('__MAP_JS__',(SRC/'map.js').read_text(encoding='utf-8'))
    assert not re.search(r'__(?:NY_MASK_PATH|NETWORK_DATA|MAP_CSS|MAP_JS)__',html)
    write(OUT/'network_map.html',html)
    write(OUT/'cable_review.json',json.dumps(review,indent=2)+'\n')
    rows=[]
    for item in items:
        for state,parameters in item['parametersByState'].items():
            rows.append(dict(parent_id=item['parentId'],key=item['key'],title=item['title'],
                status=item['status'],priority=item['priority'],state=state,
                classification=item['currentClassification'],parameter_basis=item['parameterBasis'],
                reason=item['reason'],**parameters,
                sources=' | '.join(r.get('label',r.get('path','')) for r in item['sourceRefs'])))
    csvpath=OUT/'cable_review.csv'
    with csvpath.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    assert before==[record(p) for p in protected], 'Protected source changed during map build'
    inputs=[*protected,OUT/'cable_audit_recommendations.json',SRC/'map_template.html',SRC/'map.css',SRC/'map.js',Path(__file__)]
    receipt=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Cable review visualization only; frozen AC topology, parameters, annual arrays and interface definitions preserved.',
        baseMap=current['map'],compiledModelSha256=annual['metadata']['compiledModelSha256'],
        modelParametersChanged=False,annualPowerFlowRerun=False,currentModelPointerChanged=False,
        priorMapAndDataUnchanged=True,offlineSelfContained=True,externalRuntimeRequests=False,
        auditSourceFilesVerified=len(audit['sourceFiles']),
        hours=8760,equationLossQualifiedHours=8651,operatingQualifiedHours=0,
        reviewSummary=review['summary'],source_files=[record(p) for p in inputs],
        outputs=[record(OUT/p) for p in ['network_map.html','cable_review.json','cable_review.csv']],
        protected_source_fingerprints=before)
    write(OUT/'build_receipt.json',json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(passed=True,**review['summary'],html_sha256=sha(OUT/'network_map.html'))))


if __name__=='__main__':main()
