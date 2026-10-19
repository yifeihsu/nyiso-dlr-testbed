"""Cache official generation-data catalog evidence; no model mutations or PF."""
from pathlib import Path
from datetime import datetime, timezone
import concurrent.futures, hashlib, json, re, requests, io, zipfile
import pandas as pd
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_postrepair_diagnosis/generation'
SOURCES=OUT/'sources'
URLS={
 'NYISO_P63_index.html':'https://mis.nyiso.com/public/P-63list.htm',
 'NYISO_P27_index.html':'https://mis.nyiso.com/public/P-27list.htm',
 'NYISO_P27_masked_bid_description.pdf':'https://mis.nyiso.com/public/postings/NYISO%203%20Month%20Bid%20Data%20Release%20Description_V1.pdf',
 'NYISO_public_menu.html':'https://mis.nyiso.com/public/menu.htm',
 'NYISO_P19_generator_names.html':'https://mis.nyiso.com/public/htm/generator/generator.htm',
 'NYISO_P15_index.html':'https://mis.nyiso.com/public/P-15list.htm',
 'NYISO_P61_index.html':'https://mis.nyiso.com/public/P-61list.htm',
 'NYISO_P30_DAM_energy_report.html':'https://mis.nyiso.com/public/htm/damenergy/20261016DAM_energy_rep.htm',
 'NYISO_P4B_index.html':'https://mis.nyiso.com/public/P-4Blist.htm',
 'NYISO_2025_GoldBook.pdf':'https://www.nyiso.com/documents/20142/2226333/2025-Gold-Book-Public.pdf',
 'NYISO_DayAheadSchedulingManual.pdf':'https://www.nyiso.com/documents/20142/2923301/dayahd_schd_mnl.pdf/0024bc71-4dd9-fa80-a816-f9f3e26ea53a',
 'NYISO_P63_202501.zip':'https://mis.nyiso.com/public/csv/rtfuelmix/20250101rtfuelmix_csv.zip',
 'NYISO_P63_20261014.csv':'https://mis.nyiso.com/public/csv/rtfuelmix/20261014rtfuelmix.csv',
}
def fetch(item):
 name,url=item;p=SOURCES/name
 saved=p.with_name(p.name+'.receipt.json')
 if saved.exists():
  row=json.loads(saved.read_text());assert row['url']==url and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];return row
 r=requests.get(url,timeout=45);r.raise_for_status();body=r.content
 expected_pdf=not name.endswith('.pdf') or body.startswith(b'%PDF')
 expected_zip=not name.endswith('.zip') or body.startswith(b'PK')
 blocked=b'JavaScript is disabled' in body or b'not a robot' in body
 status='downloaded_and_type_verified' if expected_pdf and expected_zip and not blocked else 'challenge_or_wrong_content_type'
 target=p if status=='downloaded_and_type_verified' else p.with_name(p.name+'.unavailable.html')
 if target.exists():assert target.read_bytes()==body,'Existing cached source differs; use a new date label'
 else:target.write_bytes(body)
 receipt=dict(url=url,final_url=r.url,retrieved_utc=datetime.now(timezone.utc).isoformat(),http_status=r.status_code,
  status=status,content_type=r.headers.get('Content-Type'),path=target.relative_to(ROOT).as_posix(),bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
 target.with_name(target.name+'.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 return receipt

def main():
 SOURCES.mkdir(parents=True,exist_ok=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
  results=list(pool.map(fetch,URLS.items()))
 (OUT/'official_source_cache_receipt.json').write_text(json.dumps(dict(retrieved_utc=datetime.now(timezone.utc).isoformat(),sources=results),indent=2)+'\n')
 with zipfile.ZipFile(SOURCES/'NYISO_P63_202501.zip') as z:
  names=sorted(n for n in z.namelist() if n.endswith('.csv'));frame=pd.concat([pd.read_csv(io.BytesIO(z.read(n))).assign(source_file=n) for n in names],ignore_index=True)
  sample=pd.read_csv(io.BytesIO(z.read(names[0])));sample.to_csv(OUT/'P63_20250101_schema_sample.csv',index=False)
 hydro=frame.loc[frame['Fuel Category'].eq('Hydro')].copy();ts=pd.to_datetime(hydro['Time Stamp']);deltas=ts.diff().dt.total_seconds().dropna()
 summary=dict(archive_month='2025-01',daily_files=len(names),columns=list(sample.columns),rows=len(frame),fuel_categories=sorted(frame['Fuel Category'].unique().tolist()),
   hydro_rows=len(hydro),date_start=str(ts.min()),date_end=str(ts.max()),hydro_time_deltas_seconds={str(k):int(v) for k,v in deltas.value_counts().head(12).items()},
   median_Hydro_interval_seconds=float(deltas.median()),nominal_five_minute_share=float((deltas==300).mean()),
   has_generator_name_or_PTID_column=False,scope='Observed 2025-01 source-schema and nominal-cadence check; not certification of every annual interval.')
 (OUT/'P63_schema_cadence_review.json').write_text(json.dumps(summary,indent=2)+'\n')
 for receipt in results:print(receipt['path'],receipt['status'],receipt['bytes'])
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
