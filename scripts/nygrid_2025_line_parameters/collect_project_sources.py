"""Archive public project documents and extract searchable PDF text."""
from pathlib import Path
import concurrent.futures
import datetime
import hashlib
import json
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_line_parameters/sources/projects'
SOURCES = {
    'CV_InServiceNotice_20190729.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BD4E0E3FE-8AA2-47C3-AEBC-390451443B89%7D',
    'CT_398_Interrogatories_20160316.pdf': 'https://portal.ct.gov/lib/csc/pending_petitions/2_petitions_1201through1300/pe1216-responsetointerrogatories-set1-newmilford.pdf',
    'CT_398_Completion_20190618.pdf': 'https://portal.ct.gov/lib/csc/pending_petitions/2_petitions_1201through1300/pe1216_completion_20190618.pdf',
    'CT_398_Completion_20191120.pdf': 'https://portal.ct.gov/lib/csc/pending_petitions/2_petitions_1201through1300/pe1216_second_completion_20191120.pdf',
    'CT_398_Petition1216_Filing_2016.pdf': 'https://portal.ct.gov/lib/csc/pending_petitions/2_petitions_1201through1300/pe1216_filing_eversource.pdf',
    'CV_EMCP_AppS_EngineeringDrawings_20170825.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B6481A05E-CA8A-4527-9CEF-9EAFB8D643C5%7D',
    'CV_Exhibit5_2013.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BF30B2009-F203-4346-A21E-D2EA4E3C81A7%7D',
    'CV_ExhibitsE1_E6_2013.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B23EBEB9A-39B8-4120-805A-1B0C8E3D0D0C%7D',
    'CV_EMF_SmithRd_2014.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B50050D61-5E13-4FF4-A6BD-6E288D76E50F%7D',
    'CV_Transmission_Project_DOE_ref.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B8FEFC9AE-4ECE-41FC-9658-020AFFEFEF25%7D',
    'CV_EMCP_Rev2_VolI_2017.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7BD6338C27-6589-4A30-84A5-B185CF6E6EC8%7D',
    'NYTransco_SA2510_2023.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B1035A486-0000-C032-B710-872FC127F6F4%7D',
    'NYISO_2022Q2_STAR.pdf': 'https://www.nyiso.com/documents/20142/16004172/2022-Q2-STAR-Report-Final.pdf/d672bb9f-c5a6-934c-ebcf-4f9e1c3d94e0',
}
# Preserved research archives from an earlier candidate scope. These sources are
# not inputs to the current six-added-line estimator and are not recollected.
OUT_OF_SCOPE_SOURCES = {
    'SPC_ArtVII_ExE1_2021.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B5116AECE-ACD5-4D37-96B7-A727F94C1CF8%7D&DocTitle=SmartPathConnect_ArtVII_ExE-1_DesProposedTransLine',
    'SPC_ArtVII_Ex5_2021.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B7A79C915-8F60-4439-81D2-56C68B53280A%7D&DocTitle=SmartPathConnect_ArtVII_Ex5-DesignDrawings',
    'SPC_ArtVII_Ex4_AppD_2021.pdf': 'https://documents.dps.ny.gov/public/Common/ViewDoc.aspx?DocRefId=%7B63761FC3-9E9E-4275-B42A-C1C795E799AB%7D&DocTitle=SmartPathConnect_ArtVII_Ex4_AppD',
    'NYISO_NEETNY_OperatingAgreement_SA2628_2021.pdf': 'https://nyisoviewer.etariff.biz/ViewerDocLibrary/temp/0941705b-38f1-4ae3-adea-d13abf0b1299.pdf',
    'EmpireStateLine_FAQ.html': 'https://www.empirestateline.com/faq.html',
    'EmpireStateLine_Regulatory.html': 'https://www.empirestateline.com/regulatory.html',
}

def collect(item):
    name, url = item
    target = OUT / name
    receipt = target.with_suffix(target.suffix + '.receipt.json')
    if target.exists() and receipt.exists():
        record = json.loads(receipt.read_text(encoding='utf-8'))
        if hashlib.sha256(target.read_bytes()).hexdigest() == record['sha256']:
            return {'name': name, 'status': 'cached', 'bytes': target.stat().st_size}
        raise RuntimeError(f'Existing archive hash mismatch: {name}')
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
            content_type = response.headers.get('content-type')
            status = response.status
            resolved = response.url
        if name.endswith('.pdf') and not data.startswith(b'%PDF'):
            raise ValueError(f'Non-PDF response: {content_type}, {len(data)} bytes')
        target.write_bytes(data)
        record = dict(name=name, source_url=url, resolved_url=resolved, retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), http_status=status, content_type=content_type, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        receipt.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        if name.endswith('.pdf'):
            subprocess.run(['pdftotext', '-layout', str(target), str(target.with_suffix('.txt'))], check=True)
        return {'name': name, 'status': 'downloaded', 'bytes': len(data)}
    except Exception as error:
        return {'name': name, 'status': 'error', 'error': str(error)}

if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(collect, SOURCES.items()))
    print(json.dumps(results, indent=2))
    if any(item['status'] == 'error' for item in results):
        raise SystemExit(1)
