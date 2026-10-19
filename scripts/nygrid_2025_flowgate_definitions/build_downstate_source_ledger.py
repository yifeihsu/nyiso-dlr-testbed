"""Literal downstate flowgate tables from approved seasonal NYISO appendices.

This is documentary reconstruction, with no P32 values, simulation or fitting.
Run with the bundled Python runtime providing pypdf.
"""
from pathlib import Path
import csv,hashlib,json,re,unicodedata
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_flowgate_definitions'
SUMMER=OUT/'sources/western/NYISO_Summer2025_Appendices_CE_Changes_APPROVED.pdf'
WINTER=OUT/'sources/central_north/NYISO_Winter2025_2026_Appendices.pdf'
EARLY=OUT/'sources/central_north/NYISO_Winter2024_2025_Appendices_APPROVED.pdf'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(s):
    s=unicodedata.normalize('NFKC',s).replace('\u2010','-').replace('\u2011','-').replace('\u2013','-').replace('\u2014','-')
    return re.sub(r'\s+','',s).lower().replace('.','')

UPNY=[('*Lovett-Buchanan South','Lovett','Buchanan South','Y88','345','from','line'),
 ('*Pleasant Valley-Wood St.','Pleasant Valley','Wood St.','F30','345','from','line'),
 ('*Pleasant Valley-Wood St.','Pleasant Valley','Wood St.','F31','345','from','line'),
 ('*Pleasant Valley-East Fishkill','Pleasant Valley','East Fishkill','F36','345','from','line'),
 ('*Pleasant Valley-East Fishkill','Pleasant Valley','East Fishkill','F37','345','from','line'),
 ('*Ramapo-Buchanan North','Ramapo','Buchanan North','Y94','345','from','line'),
 ('Roseton-East Fishkill*','Roseton','East Fishkill','RFK305','345','to','line'),
 ('*Fishkill Plains–Sylvan Lake','Fishkill Plains','Sylvan Lake','FP/990','115','from','line'),
 ('East Fishkill 115/345*','East Fishkill 115 kV','East Fishkill 345 kV','BK1','115/345','to','transformer'),
 ('East Fishkill 115/345*','East Fishkill 115 kV','East Fishkill 345 kV','BK2','115/345','to','transformer')]
SPR=[('*Dunwoodie-Mott Haven','Dunwoodie','Mott Haven','71','345','from','line'),
 ('*Dunwoodie-Mott Haven','Dunwoodie','Mott Haven','72','345','from','line'),
 ('Sprain Brook-Tremont*','Sprain Brook','Tremont','X28','345','to','line'),
 ('*Sprain Brook-West 49th Street','Sprain Brook','West 49th Street','M51','345','from','line'),
 ('*Sprain Brook-West 49th Street','Sprain Brook','West 49th Street','M52','345','from','line'),
 ('*Sprain Brook-Academy','Sprain Brook','Academy','M29','345','from','line'),
 ('*Dunwoodie-Sherman Creek','Dunwoodie','Sherman Creek','99031','138','from','line'),
 ('*Dunwoodie-Sherman Creek','Dunwoodie','Sherman Creek','99032','138','from','line'),
 ('*Dunwoodie-East 179th Street','Dunwoodie','East 179th Street','99153','138','from','line'),
 ('*Lake Success-Jamaica','Lake Success','Jamaica','903','138','from','line'),
 ('*Valley Stream-Jamaica','Valley Stream','Jamaica','901L_M','138','from','line')]

def build():
    headers=next(csv.reader((OUT/'definitions/western_2025.csv').open(encoding='utf-8')))
    rows=[];checks=[]
    for season,pdf,posted,up_page,spr_page in [('winter2024_25',EARLY,'2024-10-24',36,35),
                                             ('summer2025',SUMMER,'2025-06-20',37,36),
                                             ('winter2025_26',WINTER,'2025-10-17',36,35)]:
        doc=PdfReader(pdf)
        upny=list(UPNY)
        if season=='winter2024_25':
            upny[0]=('*Lovett-Buchanan','Lovett','Buchanan','Y88','345','from','line')
            upny[5]=('*Ramapo-Buchanan','Ramapo','Buchanan','Y94','345','from','line')
            upny[8]=('East Fishkill 345/115*','East Fishkill 345 kV','East Fishkill 115 kV','BK1','115/345','to','transformer')
            upny[9]=('East Fishkill 345/115*','East Fishkill 345 kV','East Fishkill 115 kV','BK2','115/345','to','transformer')
        for name,slug,members,page in [('UPNY-ConEd','upny_coned',upny,up_page),
                                       ('Sprain Brook-Dunwoodie South','sprain_dunwoodie_south',SPR,spr_page)]:
            text=norm(doc.pages[page-1].extract_text())
            definition=slug+'_'+season
            for i,(literal,f,t,cid,kv,meter,kind) in enumerate(members,1):
                # Exact displayed member/circuit/voltage sequence, independent
                # of layout whitespace and typographical dash/period glyphs.
                expected=norm(literal+cid+kv)
                if expected not in text:raise ValueError(f'Unmatched literal row: {season} {literal} {cid}')
                from_zone='G' if slug=='upny_coned' else ('I' if i<=9 else 'K')
                to_zone='H' if slug=='upny_coned' else 'J'
                rows.append(dict(interface=name,definition_id=definition,term_id=f'{definition}_{i:02}',
                    source_name=literal.replace('*',''),from_station=f,to_station=t,circuit_id=cid,
                    voltage_kv=kv,metered_end=meter,source_pdf=pdf.relative_to(ROOT).as_posix(),
                    pdf_page=page,printed_page=page+(27 if season=='winter2024_25' else 0),source_date=posted,posted_date=posted,
                    scope_period={'summer2025':'Summer 2025 study','winter2024_25':'Winter 2024-25 study','winter2025_26':'Winter 2025-26 study'}[season]+'; exact P32 validity interval not supplied',
                    source_quote_or_verbatim_term=literal,asterisk_present=True,compound_term=False,
                    element_kind=kind,source_from_zone=from_zone,source_to_zone=to_zone,
                    orientation_status='source table order; no numeric P32 sign asserted',
                    meter_note=('Literal name places star after115 (low-voltage side); Voltage column lists115/345. Meter/name order differs from later editions; no cutover date inferred.' if season=='winter2024_25' else 'asterisk identifies metered end; transformer star after345 marks high-voltage side') if kind=='transformer' else 'asterisk identifies circuit metered end'))
                checks.append(dict(definition_id=definition,term_id=rows[-1]['term_id'],exact_literal_row_found=True))
    path=OUT/'definitions/downstate_2025.csv'
    with path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=headers,lineterminator='\n');writer.writeheader();writer.writerows(rows)
    receipt=dict(passed=True,rows=len(rows),definitions=6,source_observations_read=False,
        visual_review=dict(passed=True,reviewer='root',pages={'winter2024_25':[35,36],'summer2025':[36,37],'winter2025_26':[35,36]}),
        operational_effective_timestamps_verified=False,P32_numeric_sign_binding_verified=False,
        notes=['2024 Lovett345 station bisects Y88; Lovett is not silently treated as an alias for Ladentown.',
               'Summer2025 and Winter2025-26 member lists agree; Winter2024-25 has unsuffixed Buchanan terminals and different EastFishkill transformer star/winding order.',
               'Historical and model station aliases and physical circuit identity require separate proof.'],
        checks=checks,outputs=[dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(path))],
        dependencies=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p))for p in [SUMMER,WINTER,EARLY,Path(__file__)]])
    path.with_suffix('.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:receipt[k]for k in ['passed','rows','definitions']},indent=2))

if __name__=='__main__':build()
