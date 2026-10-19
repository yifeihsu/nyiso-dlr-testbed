"""Preserve public Dover sources with hashes; never alter the frozen model."""
from pathlib import Path
import concurrent.futures
import datetime
import hashlib
import json
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'output/nygrid_2025_dover_parameters/sources'
SOURCES = {
    'NYISO_ParFlowDiagrams27.pdf': 'https://www.nyiso.com/documents/20142/2268519/ParFlowDiagrams27.pdf/7bd78df8-311c-0b29-fa3f-ba0c8a51d123',
    'NYISO_MarketParticipants_UserGuide.pdf': 'https://www.nyiso.com/documents/20142/3625950/mpug.pdf',
    'Dover_DPS_Transfer_Petition_SA2734_2025.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B105FA79A-0000-C05B-90D0-E1213402FA37%7D',
    'Dover_NYISO_Consent_20221028.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B0035A486-0000-C95D-9442-22C72F5AC4B0%7D',
    'Dover_DPS_PressNotice_20230301.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BC0EC9D86-0000-C314-AAE5-3BC75C82AE95%7D',
    'Dover_DPS_CPCN_Order_20230316.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B8012EC86-0000-C613-8D37-858F1DF8EC94%7D',
    'Dover_DPS_Petition_20230209_Redacted.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B50336F09-AF0B-4BB3-B7A3-09086F04CB0E%7D',
    'Dover_DPS_Ex1_20230209.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B2509B0D2-4E62-487F-B156-AB70E3B1F965%7D',
    'Dover_DPS_Ex2_20230209.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B23EEE01D-688B-4683-B531-1F95F3F358FA%7D',
    'Dover_DPS_Ex3a_20230209.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BADCA1760-6044-4614-995F-29208849FC9E%7D',
    'Dover_DPS_Ex3b_20230209.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BB28EFC5A-E341-4727-B09C-D1296EC4465E%7D',
    'Dover_DPS_FacilitiesStudy_20230302_Redacted.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B0035A486-0000-C898-BEED-100CAF9C6C1A%7D',
}

def collect(item):
    name,url=item;target=OUT/name
    receipt=target.with_suffix(target.suffix+'.receipt.json')
    if target.exists() and receipt.exists():
        old=json.loads(receipt.read_text(encoding='utf-8'))
        if hashlib.sha256(target.read_bytes()).hexdigest()!=old['sha256']:
            raise RuntimeError('Existing archive hash mismatch: '+name)
        return dict(name=name,status='cached',bytes=target.stat().st_size)
    try:
        with urllib.request.urlopen(url,timeout=120) as r:
            data=r.read();content_type=r.headers.get('content-type');status=r.status;resolved=r.url
        if name.endswith('.pdf') and not data.startswith(b'%PDF'):
            raise RuntimeError('Response is not a PDF: '+str(content_type))
        target.write_bytes(data)
        proof=dict(source_url=url,resolved_url=resolved,http_status=status,content_type=content_type,
            retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        receipt.write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
        if name.endswith('.pdf'):
            subprocess.run(['pdftotext','-layout',str(target),str(target.with_suffix('.txt'))],check=True)
        return dict(name=name,status='downloaded',bytes=len(data))
    except Exception as error:
        return dict(name=name,status='error',error=str(error))

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        result=list(pool.map(collect,SOURCES.items()))
    print(json.dumps(result,indent=2))
    raise SystemExit(any(x['status']=='error' for x in result))
