"""Archive explicit public boundary-verification sources with immutable receipts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_moses_repair/boundary/sources'
SOURCES = {
    'NYPA_HA1_in_service_20260330.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B101D3F9D-0000-CA6E-AF99-F8341FEECB4B%7D&DocTitle=NYPA+Smart+Path+Connect%3A+In-Service+Notification+for+HA1',
    'NYPA_MH1_in_service_20260416.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BE06E969D-0000-CE21-B946-CF365666B73B%7D&DocTitle=NYPA+SPC+In-Service+Notification+MH1',
    'NYISO_transfer_limitations_20251022.pdf': 'https://mis.nyiso.com/public/pdf/ttcf/20251022ttcf.pdf',
    'NYPA_Smart_Path_Connect_current.html': 'https://www.nypa.gov/Power/Transmission/Transmission-Projects/Smart-Path-Connect',
    'DPS_21_T_0340_docket.html': 'https://documents.dps.ny.gov/public/MatterManagement/CaseMaster.aspx?MatterCaseNo=21-T-0340',
    'DPS_21_T_0340_public_documents.json': 'https://documents.dps.ny.gov/public/CaseMaster/PublicDocuments/65705',
    'NYPA_HA2_in_service_20251014.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B7068E499-0000-C447-80CF-7A033EE81A59%7D',
    'VELCO_OC_minutes_SandBar_failure_20210318.pdf': 'https://www.velco.com/sites/default/files/2023-12/III.%20DRAFT%20OC%20Minutes_210318.pdf',
    'ISONE_OP17A_boundaries_current.pdf': 'https://www.iso-ne.com/static-assets/documents/rules_proceds/operating/isone/op17/op17a_rto_final.pdf',
    'ISONE_weekly_20251116.pdf': 'https://www.iso-ne.com/static-assets/documents/100029/we_2025_11_16_weekly_final.pdf',
    'VEC2025_IRP_section4_SouthHero.pdf': 'https://vermontelectric.coop/client_media/files/2025_IRP_Section_4_Engage_Members_1.pdf',
}


def fetch(item):
    name, url = item
    path = OUT/name
    receipt_path = path.with_suffix(path.suffix+'.receipt.json')
    if path.exists():
        receipt = json.loads(receipt_path.read_text())
        assert receipt['url'] == url and receipt['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
        return receipt
    request = urllib.request.Request(url, headers={'User-Agent':'Research source verification/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read()
            assert response.status == 200
            if name.endswith('.pdf'):
                assert data.startswith(b'%PDF-'), 'Expected original PDF bytes'
            receipt = dict(url=url, final_url=response.url, retrieved_utc=datetime.now(timezone.utc).isoformat(),
                status=response.status, content_type=response.headers.get('Content-Type'),
                last_modified=response.headers.get('Last-Modified'), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        path.write_bytes(data)
        receipt_path.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        return dict(file=name, **receipt)
    except Exception as exc:
        failure = dict(file=name,url=url,status='failed',error=str(exc),attempted_utc=datetime.now(timezone.utc).isoformat())
        path.with_suffix(path.suffix+'.failure.json').write_text(json.dumps(failure,indent=2)+'\n',encoding='utf-8')
        return failure


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for receipt in pool.map(fetch,SOURCES.items()):
            print(json.dumps(receipt),flush=True)
