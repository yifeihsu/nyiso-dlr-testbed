"""Embed current topology, annual flow data and definitions in an offline map."""
from pathlib import Path
from collections import Counter
import hashlib
import json

ROOT=Path(__file__).resolve().parents[4]
SRC=Path(__file__).parent
OUT=ROOT/'output/nygrid_2025_moses_repair/delivery/map'

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def main():
    sources=[OUT/'geography_data.json',OUT/'annual_data.json',OUT/'interface_definitions.json',
        SRC/'map_template.html',SRC/'map.css',SRC/'map.js',Path(__file__),OUT/'ny_display_mask.json']
    g,a,d=(read(p) for p in sources[:3])
    mask=read(sources[7]);assert mask['projection']==g['projection'] and not mask['officialBoundaryClaim']
    assert len(g['nodes'])==267 and sum(n['retained'] for n in g['nodes'])==148
    assert len(g['parents'])==413 and len(g['transfers'])==6
    assert len(a['hours'])==8760 and len(d['interfaces'])==7 and len(d['zones'])==11
    assert a['interfaceNames']==[x['name'] for x in d['interfaces']]
    assert a['zoneNames']==[x['id'] for x in d['zones']]
    assert sum(h['sourceQualified'] for h in a['hours'])==8651
    counts=a['metadata']['counts']
    assert sum(h['qualified'] for h in a['hours'])==counts['qualified']
    assert sum(h['operatingQualified'] for h in a['hours'])==counts['operatingQualified']
    assert all(len(v)==7 for v in a['interfaceFlowsModelMW'])
    assert all(all(v is None for v in row) for row,h in zip(a['interfaceFlowsModelMW'],a['hours']) if not h['qualified'])
    assert all(x['id'] in [s['id'] for s in g['states']] for x in g['states'])
    for row in a['hours']:assert row['state'] in [s['id'] for s in g['states']]
    payload={'schemaVersion':1,'sourceModelCommit':g['mapSourceCommit'],
        'geography':g,'annual':a,'interfaces':d}
    compact=json.dumps(payload,separators=(',',':'),ensure_ascii=True,allow_nan=False).replace('<','\\u003c')
    template=sources[3].read_text(encoding='utf-8')
    html=template.replace('__NY_MASK_PATH__',mask['svgPath']).replace('__NETWORK_DATA__',compact).replace('__MAP_CSS__',sources[4].read_text(encoding='utf-8')).replace('__MAP_JS__',sources[5].read_text(encoding='utf-8'))
    assert '__NETWORK_DATA__' not in html and '__MAP_CSS__' not in html and '__MAP_JS__' not in html and '__NY_MASK_PATH__' not in html
    page=OUT/'network_map.html';page.write_text(html,encoding='utf-8',newline='\n')
    data_path=OUT/'map_data.json';data_path.write_text(compact+'\n',encoding='utf-8',newline='\n')
    receipt={'passed':True,'scope':'Current-model offline map build and identity/availability contracts',
        'sourceModelCommit':g['mapSourceCommit'],'sourceElectricalModelCommit':g['sourceModelCommit'],
        'sourceElectricalModelCommitRole':'preserved_baseline','physicalRepairCandidateSha256':a['metadata']['physicalRepairCandidateSha256'],
        'mosesRepairCandidateSha256':a['metadata']['mosesRepairCandidateSha256'],
        'compiledModelSha256':a['metadata']['compiledModelSha256'],
        'offlineSelfContained':True,'externalRuntimeRequests':False,'modelParametersChanged':True,
        'annualPFOrOPFRerun':True,'annualReplayReceipt':a['metadata']['annualRun'],'retainedBuses':148,'detailedBusesByState':[s['detailedBusCount'] for s in g['states']],
        'parentRecordsByState':[s['parentRecordCount'] for s in g['states']],
        'hours':8760,'sourceQualifiedHours':8651,'equationLossQualifiedHours':counts['qualified'],'operatingQualifiedHours':counts['operatingQualified'],
        'interfaceCount':7,'zoneCount':11,'stateHours':dict(Counter(h['state'] for h in a['hours'])),
        'failedFlowValuesAreNull':True,'defaultHour':8508,'defaultPowerUnits':'model_MW',
        'sources':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in sources],
        'outputs':[{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in [page,data_path]]}
    (OUT/'build_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['sources','outputs']},indent=2))
    print(json.dumps(receipt['outputs'],indent=2))

if __name__=='__main__':main()
