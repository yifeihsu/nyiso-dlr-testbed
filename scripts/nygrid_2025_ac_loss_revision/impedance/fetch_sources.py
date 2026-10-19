"""Archive public primary-source evidence without modifying baseline inputs."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,urllib.request

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_ac_loss_revision/impedance/sources'
PIN='47698b6c7823ae7b1bc6935e5601d5b64b8f918e'


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    OUT.mkdir(parents=True,exist_ok=True);rows=[]
    manifest=json.loads((ROOT/'output/nygrid_2019/upstream_manifest.json').read_text());assert manifest['commit']==PIN
    for relative,name in [('modifyMPC.m','Cornell_NYgrid_modifyMPC.m'),('Data/npcc.mat','Cornell_NYgrid_original_npcc.mat'),('Data/npcc.csv','Cornell_NYgrid_original_npcc.csv')]:
        old=ROOT/'tmp/nygrid_2019_reproduction/upstream'/relative;entry=next(x for x in manifest['files'] if x['path']==relative)
        assert sha(old)==entry['sha256'];target=OUT/name
        if not target.exists():shutil.copyfile(old,target)
        assert sha(target)==entry['sha256']
        rows.append(dict(name=name,source_type='pinned_author_repository',url=entry['url'],commit=PIN,sha256=sha(target),bytes=target.stat().st_size))
    prior=json.loads((ROOT/'output/marcy_south_parameter_audit/audit_summary.json').read_text())
    paper=Path(prior['paper']['path']);target=OUT/'NYgrid_published_paper.pdf';assert sha(paper)==prior['paper']['sha256']
    if not target.exists():shutil.copyfile(paper,target)
    assert sha(target)==sha(paper)
    rows.append(dict(name=target.name,source_type='user_supplied_published_paper_previously_archived',original_path=str(paper),sha256=sha(target),bytes=target.stat().st_size))
    sources=[
      ('NYPA_property_holdings_2023.pdf','https://www.nypa.gov/-/media/nypa/documents/document-library/real-estate/overview-of-all-nypa-holdings12312023-final.pdf'),
      ('NYISO_interface_stability_2004.pdf','https://www.nyiso.com/documents/20142/2964907/interface_stability_limit_analysis.pdf/2ed355de-8767-8cde-c397-eec7450439b8'),
      ('NYPA_trustee_minutes_2014_10_15.pdf','https://prod-www.nypa.gov/-/media/nypa/documents/document-library/meeting-minutes/minutes_october-15-2014-regular-meeting.pdf')]
    for name,url in sources:
        target=OUT/name
        try:
            if not target.exists():
                req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (source verification)'})
                with urllib.request.urlopen(req,timeout=30) as response:data=response.read()
                assert data.startswith(b'%PDF'),url;target.write_bytes(data)
            rows.append(dict(name=name,source_type='utility_or_system_operator_primary_document',url=url,sha256=sha(target),bytes=target.stat().st_size,download_verified=True))
            print(name,target.stat().st_size,flush=True)
        except Exception as e:
            rows.append(dict(name=name,url=url,download_verified=False,error=str(e)));print(name,str(e),flush=True)
    (OUT/'source_download_receipt.json').write_text(json.dumps(dict(created_utc=datetime.now(timezone.utc).isoformat(),sources=rows),indent=2)+'\n')


if __name__=='__main__':main()
