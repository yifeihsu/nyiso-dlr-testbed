"""Preserve official final860 and monthly860M source evidence for plant2694.

Run with bundled Python/openpyxl. Reads workbooks; never writes a workbook or
modifies a model. Existing source bytes must match their acquisition receipts.
"""
from pathlib import Path
from datetime import datetime,timezone
from html.parser import HTMLParser
from urllib.parse import urljoin,urlparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import csv,hashlib,json,re,urllib.request,zipfile
import openpyxl

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_moses_source_diagnosis/generation'
SOURCES=OUT/'sources'
MONTHS=['january','february','march','april','may','june','july','august','september','october','november','december']


def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def download(url,name):
    assert urlparse(url).hostname in ['www.eia.gov','www.nypa.gov','nypa.gov']
    target=SOURCES/name;proof=target.with_suffix(target.suffix+'.receipt.json')
    legacy=SOURCES/'eia8602025_final.receipt.json'
    existing_proof=proof if proof.exists() else (legacy if name=='eia8602025_final.zip' and legacy.exists() else None)
    expected=json.loads(existing_proof.read_text()) if existing_proof is not None else None
    if target.exists():
        assert expected is not None and sha(target)==expected['sha256']
        return target
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 scientific source audit'})
    with urllib.request.urlopen(request,timeout=60) as response:
        data=response.read();metadata={'source_url':url,'resolved_url':response.url,'http_status':response.status,
            'http_last_modified':response.headers.get('Last-Modified'),'retrieved_utc':datetime.now(timezone.utc).isoformat(),
            'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    if expected is not None:
        assert metadata['sha256']==expected['sha256'],f'Source vintage changed at {url}; preserve the old receipt and acquire under a new version.'
        # Authenticate the historical bytes before writing a missing raw cache.
        # Identical restoration retains the original acquisition receipt.
        target.write_bytes(data)
    else:
        target.write_bytes(data);proof.write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    return target


class Links(HTMLParser):
    def __init__(self):super().__init__();self.urls=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            for name,value in attrs:
                if name=='href':self.urls.append(value)


def normalized(value):return re.sub(r'[^a-z0-9]','',str(value).lower())


def extract(path,year,month,kind):
    book=openpyxl.load_workbook(path,read_only=True,data_only=True);records=[];sheets=[]
    for sheet in book:
        if not any(x in sheet.title.lower() for x in ['operating','operable','retired']):continue
        rows=sheet.iter_rows(values_only=True);header=None;plant_col=None
        for excel_row,row in enumerate(rows,1):
            if header is None:
                candidates=[i for i,value in enumerate(row) if normalized(value) in ['plantcode','plantid']]
                if candidates:header=[str(v).strip() if v is not None else f'unnamed_{i}' for i,v in enumerate(row)];plant_col=candidates[0];sheets.append({'sheet':sheet.title,'header_row':excel_row})
                elif excel_row>15:break
                continue
            if str(row[plant_col]).strip() not in ['2694','2694.0']:continue
            records.append({'source_kind':kind,'source_year':year,'source_month':month,'source_workbook':path.name,
                'source_sheet':sheet.title,'source_excel_row':excel_row,'source_sha256':sha(path),**dict(zip(header,row))})
    book.close();assert records,f'No StLawrence rows in {path}'
    return records,sheets


def main():
    SOURCES.mkdir(parents=True,exist_ok=True)
    page_url='https://www.eia.gov/electricity/data/eia860m/index.php'
    page=download(page_url,'eia860m_index.html');parser=Links();parser.feed(page.read_text(encoding='utf-8',errors='replace'))
    urls={}
    for month,name in enumerate(MONTHS,1):
        hits=[urljoin(page_url,u) for u in parser.urls if u.lower().endswith('/'+name+'_generator2025.xlsx')]
        assert len(set(hits))==1,(month,hits);urls[month]=hits[0]
    records=[];manifest=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(download,url,f'eia860m_{month:02d}_2025.xlsx'):month for month,url in urls.items()}
        for future in as_completed(jobs):
            month=jobs[future];path=future.result();rows,sheets=extract(path,2025,month,'monthly_EIA860M')
            records+=rows;manifest.append({'month':month,'url':urls[month],'path':path.relative_to(ROOT).as_posix(),
                'sha256':sha(path),'selected_rows':len(rows),'sheets':sheets})
            print(f'Monthly inventory {month:02d}: {len(rows)} StLawrence rows',flush=True)
    path=download('https://www.eia.gov/electricity/data/eia860/xls/eia8602025.zip','eia8602025_final.zip')
    with zipfile.ZipFile(path) as archive:
        member=next(n for n in archive.namelist() if '3_1_Generator' in n and n.endswith('.xlsx'))
        target=SOURCES/Path(member).name;data=archive.read(member)
        if target.exists():assert target.read_bytes()==data
        else:target.write_bytes(data)
    final,sheets=extract(target,2025,0,'final_annual_EIA860');records+=final
    manifest.append({'month':0,'url':'https://www.eia.gov/electricity/data/eia860/xls/eia8602025.zip',
        'path':target.relative_to(ROOT).as_posix(),'sha256':sha(target),'selected_rows':len(final),'sheets':sheets})
    records.sort(key=lambda r:(r['source_month'],r['source_sheet'],r['source_excel_row']))
    fields=list(dict.fromkeys(k for row in records for k in row))
    output=OUT/'EIA860_plant2694_inventory_source_rows.csv'
    with output.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(records)
    result={'passed':True,'retrieved_and_extracted_utc':datetime.now(timezone.utc).isoformat(),'plant_id':2694,
        'monthly_inventory_count':12,'final_annual_inventory_count':1,'records':len(records),'source_records':sorted(manifest,key=lambda r:r['month']),
        'workbooks_modified':False,'default_model_changed':False,'output':{'path':output.relative_to(ROOT).as_posix(),'sha256':sha(output)},
        'interpretation':'Monthly inventories are dated status/capacity snapshots, not observed hourly dispatch or availability.'}
    receipt_path=OUT/'inventory_source_receipt.json'
    if receipt_path.exists():
        previous=json.loads(receipt_path.read_text());old=previous.copy();new=result.copy()
        old.pop('retrieved_and_extracted_utc');new.pop('retrieved_and_extracted_utc')
        assert old==new,'Inventory extraction differs from the existing source receipt; version the new evidence.'
    else:receipt_path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'records':len(records),'inventory_files':13}))


if __name__=='__main__':main()
