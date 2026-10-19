"""Record literal project/circuit searches in all historical/planning sheets."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
import openpyxl

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"output/nygrid_2025_line_parameters/local_inventory"
SOURCE=ROOT/"PERFORM/Auxilliary_Perform_NY/Branch_changes_2019_to_2030.xlsx"
PIN="31d519c74f75a06a77ed11fabf535e4579fbc5c94cbb7e0a6be14cec38a054b8"


def main():
    digest=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if digest!=PIN:raise ValueError("Historical/planning workbook changed")
    workbook=openpyxl.load_workbook(SOURCE,read_only=True,data_only=True)
    searches=[];hits=[]
    for sheet in workbook:
        rows=list(sheet.values);hi=next(i for i,row in enumerate(rows) if row[0]=="ID");headers=rows[hi]
        data=[(i,dict(zip(headers,row))) for i,row in enumerate(rows[hi+1:],hi+2) if row[0] is not None]
        for query,field,method in [(v,"endpoint_names","literal_substring") for v in ["CRICKET","DOVER","LONG MOUNTAIN","LONG MTN"]]+[(v,"Circuit","exact_cell") for v in ["F83","F84","Y17","398","36188","42233","39291"]]:
            matched=[]
            for excelrow,record in data:
                value=(str(record.get("From Name",""))+" "+str(record.get("To Name",""))).upper() if field=="endpoint_names" else str(record.get("Circuit","")).strip().upper()
                if (query in value if method=="literal_substring" else query==value):
                    matched.append(excelrow);hits.append(dict(sheet=sheet.title,excel_row=excelrow,query=query,record={str(k):v for k,v in record.items() if k is not None}))
            searches.append(dict(sheet=sheet.title,records_searched=len(data),query=query,field=field,method=method,matched_excel_rows=matched))
    workbook.close()
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=digest:raise ValueError("Workbook changed during search")
    OUT.mkdir(parents=True,exist_ok=True)
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),source_path=str(SOURCE.relative_to(ROOT)).replace("\\","/"),source_sha256=digest,
                searches=searches,hits=hits,matching_records=len(hits),direct_future_project_parameters_identified=False,
                search_scope="all6sheets;literal_endpoint_labels_and_exact_named_circuit_IDs;no_name_only_or_generic_number_promotion",
                limitations="No literal match is not proof of physical asset absence under undisclosed aliases. No source-backed alias to another workbook row was found.",
                observations_read=False,model_modified=False,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (OUT/"future_project_parameter_search.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(dict(passed=True,searches=len(searches),matching_records=len(hits))))


if __name__=="__main__":main()
