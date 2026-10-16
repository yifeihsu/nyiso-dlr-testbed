"""Verify a cable-overlay build without changing its frozen electrical payload."""
from pathlib import Path
from html.parser import HTMLParser
from datetime import datetime, timezone
import hashlib,json

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_cable_review_map'
BASE=ROOT/'output/nygrid_2025_moses_repair/delivery/map'
SRC=Path(__file__).parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)


class Blocks(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=False);self.current=None;self.blocks=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style'}:self.current={'tag':tag,'attrs':dict(attrs),'parts':[]}
    def handle_data(self,text):
        if self.current is not None:self.current['parts'].append(text)
    def handle_endtag(self,tag):
        if self.current and tag==self.current['tag']:self.blocks.append(self.current);self.current=None


def main():
    html=OUT/'network_map.html';parser=Blocks();parser.feed(html.read_text(encoding='utf-8'))
    payload=next(b for b in parser.blocks if b['attrs'].get('id')=='network-data')
    scripts=[b for b in parser.blocks if b['tag']=='script']
    assert len(scripts)==2 and not any('src' in b['attrs'] for b in scripts)
    data=json.loads(''.join(payload['parts']))
    for key,name in [('annual','annual_data.json'),('geography','geography_data.json'),('interfaces','interface_definitions.json')]:
        assert canonical(data[key])==canonical(read(BASE/name)),key+' changed'
    assert canonical(data['cableReview'])==canonical(read(OUT/'cable_review.json'))
    program=next(b for b in scripts if b is not payload)
    assert ''.join(program['parts']).strip()==(SRC/'map.js').read_text(encoding='utf-8').strip()
    style=next(b for b in parser.blocks if b['tag']=='style')
    assert ''.join(style['parts']).strip()==(SRC/'map.css').read_text(encoding='utf-8').strip()
    review=data['cableReview'];items=review['items']
    assert len(items)==44 and sum(i['priority']=='high' for i in items)==19
    expected={'pre_may':(42,17),'may21':(43,18),'may30':(44,19),'post_dover':(44,19)}
    parents={p['id']:p for p in data['geography']['parents']}
    for state,(active_count,high_count) in expected.items():
        active=[i for i in items if next(r for r in parents[i['parentId']]['stateRecords'] if r['stateId']==state)['active']]
        assert len(active)==active_count and sum(i['priority']=='high' for i in active)==high_count
        assert all(not i['parametersByState'][state]['overheadDlrEligible'] for i in items)
    build=read(OUT/'build_receipt.json')
    for source in build['source_files']+build['protected_source_fingerprints']+build['outputs']:
        assert sha(ROOT/source['path'])==source['sha256'],source['path']+' changed'
    interaction=read(OUT/'interaction_validation.json')
    assert interaction['passed'] and interaction['html_sha256']==sha(html)
    preview=read(OUT/'static_preview_receipt.json')
    assert preview['passed'] and preview['html_sha256']==sha(html)
    for image in preview['images']:assert sha(OUT/image['image'])==image['png_sha256']
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),html_sha256=sha(html),
        exactFrozenPayloadPreserved=['geography','annual','interfaces'],modelOrInputsChanged=False,
        parentRecordsFlagged=44,highPriorityRecords=19,conflicts=[300,309,310,386],
        activeCounts=expected,interactionChecks=interaction['checks_run'],
        nativeBrowserVerification=False,nativeBrowserReason='Browser URL policy rejected local file protocol; no workaround or alternate browser was used.',
        staticPreviewMethod=preview['method'],previousMapAndModelHashesPreserved=True,
        limitations=['Review flags are not confirmed physical cable faults.',
                     'Map chords are schematic; no installed route or circuit count is inferred.',
                     'Static SVG and DOM stubs do not verify full browser layout or native hit testing.'])
    (OUT/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
