"""Reproduce literal NYISO seasonal gate tables, without model/score access.

Manual transcription is checked against archived PDF text and the independently
rendered pages. Asterisks are preserved. Single-station device port ambiguity is
not resolved by assuming a meter terminal, model branch, sign, or effective hour.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re

from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"output/nygrid_2025_flowgate_definitions"
DEFS=OUT/"definitions"
SRC=OUT/"sources/central_north"
SUMMER=OUT/"sources/western/NYISO_Summer2025_Appendices_CE_Changes_APPROVED.pdf"
WINTER=SRC/"NYISO_Winter2025_2026_Appendices.pdf"
EARLY=SRC/"NYISO_Winter2024_2025_Appendices_APPROVED.pdf"


def require(value,message):
    if not value:raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def rel(path):return Path(path).relative_to(ROOT).as_posix()


# Tuple fields: source Name column, nominal from/to station, source Line ID,
# source Voltage column, identifiable metered end, regional heading.
CE=[
    ("Edic-Gordon Rd.*","Edic","Gordon Rd.","14","345","to","E -> F"),
    ("Marcy-New Scotland*","Marcy","New Scotland","18","345","to","E -> F"),
    ("*Edic-Princetown","Edic","Princetown","351","345","from","E -> F"),
    ("*Edic-Princetown","Edic","Princetown","352","345","from","E -> F"),
    ("East Springfield-Inghams*","East Springfield","Inghams","7-942","115","to","E -> F"),
    ("Inghams PAR","Inghams","","PAR","115","unspecified","E -> F"),
    ("Inghams Bus Tie","Inghams","","R81","115","unspecified","E -> F"),
    ("*Plattsburgh-Sand Bar","Plattsburgh","Sand Bar","PV20","115","from","D -> N"),
]
MS=[
    ("*Massena-Marcy","Massena","Marcy","MSU1","765","from","D -> E"),
    ("*Moses-Adirondack","Moses","Adirondack","MA1","230","from","D -> E"),
    ("*Moses-Adirondack","Moses","Adirondack","MA2","230","from","D -> E"),
    ("*Dennison-Norfolk","Dennison","Norfolk","4","115","from","D -> E"),
    ("*Dennison-Sandstone","Dennison","Sandstone","5","115","from","D -> E"),
    ("*Alcoa-N. Ogdensburg","Alcoa","N. Ogdensburg","13","115","from","D -> E"),
    ("Parishville-Colton*","Parishville","Colton","3","115","to","D -> E"),
]
TE=[
    CE[0],CE[1],("*Fraser-Gilboa","Fraser","Gilboa","GF5-35","345","from","E -> F"),CE[2],CE[3],CE[4],
    ("*Inghams PAR","Inghams","","PAR","115","unspecified","E -> F"),
    ("*Inghams Bus Tie","Inghams","","R81","115","unspecified","E -> F"),
    ("Middletown-Rock Tavern*","Middletown","Rock Tavern","CCRT34","345","to","E -> G"),
    ("Coopers Corners-Dolson Ave.*","Coopers Corners","Dolson Ave.","CCDA42","345","to","E -> G"),
    ("Middletown 345*/138","Middletown 345 kV","Middletown 138 kV","BK114","345/138","from","E -> G"),
    ("West Woodbourne 115/69*","West Woodbourne 115 kV","West Woodbourne 69 kV","BK1","115/69","to","E -> G"),CE[7],
    ("Hopatcong-Ramapo*","Hopatcong","Ramapo","5018","500","to","P -> G"),
    ("*Waldwick-S. Mahwah","Waldwick","S. Mahwah","J3410","345","from","P -> G"),
    ("*Waldwick-S. Mahwah","Waldwick","S. Mahwah","K3411","345","from","P -> G"),
    ("Marion-Farragut*","Marion","Farragut","C3403","345","to","P -> J"),
    ("Hudson-Farragut*","Hudson","Farragut","B3402","345","to","P -> J"),
    ("Linden-Goethals*","Linden","Goethals","A2253","230","to","P -> J"),
    ("*Cresskill-Sparkill","Cresskill","Sparkill","751","69","from","PJM RECo -> G"),
    ("*Harings Corners-W. Nyack","Harings Corners","W. Nyack","701","69","from","PJM RECo -> G"),
    ("*Harings Corners-Corporate Drive","Harings Corners","Corporate Drive","703","138","from","PJM RECo -> G"),
    ("*Montvale-Bluehill","Montvale","Bluehill","44","69","from","PJM RECo -> G"),
    ("*Montvale-Bluehill","Montvale","Bluehill","43","69","from","PJM RECo -> G"),
    ("*Montvale-Pearl River","Montvale","Pearl River","491","69","from","PJM RECo -> G"),
    ("*Harings Corners-Pearl River","Harings Corners","Pearl River","45","34","from","PJM RECo -> G"),
    ("*S. Mahwah-Ramapo","S. Mahwah","Ramapo","51","138","from","PJM RECo -> G"),
    ("*S. Mahwah-Hilburn","S. Mahwah","Hilburn","65","69","from","PJM RECo -> G"),
    ("S. Mahwah 138*/345","S. Mahwah 138 kV","S. Mahwah 345 kV","BK258","138/345","from","PJM RECo -> G"),
]


def normalized(value):return re.sub(r"[^a-z0-9*]","",value.lower())


def table_rows(season,path,posted,pages,printed_offset=0):
    pdf=PdfReader(path);date=str(pdf.metadata.get("/CreationDate",""))
    date=date[2:6]+"-"+date[6:8]+"-"+date[8:10] if date.startswith("D:") else ""
    rows=[]
    for (name,short,terms),page in zip([("MOSES SOUTH","MS",MS),("TOTAL EAST","TE",TE),("CENTRAL EAST","CE",CE)],pages):
        text=pdf.pages[page-1].extract_text() or ""
        require("indicates the metered end of the circuit" in text,"Source star legend missing")
        for i,t in enumerate(terms,1):
            if season=="WINTER2025_26" and name=="MOSES SOUTH" and i in [2,3]:
                t=("*Haverstock-Adirondack","Haverstock","Adirondack","HA"+str(i-1),"345","from","D -> E")
            literal,fr,to,ckt,kv,meter,heading=t
            row=dict(interface=name,definition_id=f"NYISO_{season}_{short}",term_id=f"{short}{i:02d}",source_name=literal,
                from_station=fr,to_station=to,circuit_id=ckt,voltage_kv=kv,metered_end=meter,source_pdf=rel(path),
                pdf_page=page,printed_page=page+printed_offset,source_date=date,posted_date=posted,
                scope_period=("Summer 2025" if season=="SUMMER2025" else "Winter 2025-26")+" operating-study definition; exact real-time effective interval unestablished",
                verbatimterm=f"{literal} | {ckt} | {kv}",asterisk_present="*" in literal,compound_term=False,
                source_zone_direction=heading,source_date_basis="PDF CreationDate; not assumed implementation date",
                numeric_meter_point_id_published=False,unresolved_terminal_pair=not bool(to),
                notes=("Single-station PAR/tie: no named terminal pair. Leading asterisk retained literally where present; physical metering port not independently resolved."
                       if not to else "Name order and regional heading recorded; numerical sign to any model branch requires a separately verified endpoint mapping."))
            if season=="WINTER2024_25":
                row["scope_period"]="Winter 2024-25 operating-study definition; exact real-time effective interval unestablished"
                if row["source_name"]=="Edic-Gordon Rd.*":row["source_name"]="Edic-Gordon Rd*"
                if name=="TOTAL EAST" and i==20:
                    row.update(source_name="*Closter-Sparkill",from_station="Closter",notes="Source circuit751 namedCloster-Sparkill inWinter2024-25 butCresskill-Sparkill inSummer2025; alias/equipment-change interpretation unestablished.")
                if name=="TOTAL EAST" and i==28:
                    row.update(source_name="*S. Mahwah-Hillburn",to_station="Hillburn",notes="Source spellingHillburn retained; Summer2025 spellsHilburn. Circuit65 andvoltage69 unchanged; no fitted endpoint reassignment.")
                if name=="CENTRAL EAST" and i==6:
                    row.update(source_name="Inghams PAR*",circuit_id="PAR 2",asterisk_present=True,notes="Trailing asterisk andLineID PAR 2 retained. Single-station term lacks namedportpair; physical metered end remainsunresolved. Summer2025 isunstarred PAR.")
                if name=="CENTRAL EAST" and i==7:
                    row.update(source_name="Inghams Bus Tie*",asterisk_present=True,notes="Trailing asterisk retained. Single-station term lacks namedportpair; physical meteredend unresolved. Summer2025 isunstarredR81.")
                row["verbatimterm"]=f"{row['source_name']} | {row['circuit_id']} | {row['voltage_kv']}"
            require(normalized(row["verbatimterm"]) in normalized(text),f"Literal source name/star/circuit/voltage not found: {season}/{name}/{i}")
            rows.append(row)
    require(len(rows)==44,"Expected44termsperseason")
    return rows


def csv_bytes(rows):
    stream=io.StringIO(newline="")
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def build(verify=False):
    DEFS.mkdir(parents=True,exist_ok=True)
    current=table_rows("SUMMER2025",SUMMER,"2025-06-20",[37,38,39])+table_rows("WINTER2025_26",WINTER,"2025-10-17",[36,37,38])
    early=table_rows("WINTER2024_25",EARLY,"2024-10-24",[36,37,38],27)
    output={DEFS/"central_north_2025.csv":csv_bytes(current),DEFS/"central_north_winter2024_25.csv":csv_bytes(early)}
    for path,data in output.items():
        if path.exists():require(path.read_bytes()==data,"Existing literal ledger differs: "+str(path))
        elif verify:raise ValueError("Missing ledger: "+str(path))
        else:path.write_bytes(data)
    # No whole-year timestamp range is inferred from a posting date. Source
    # periods remain study-season labels until independent implementation proof.
    proof_path=DEFS/"central_north_2025_qualifiers.json"
    proof=json.loads(proof_path.read_text())
    require(proof["exact_2025_operational_validity_established"] is False,"Unsupported hourly-period promotion")
    require(proof["P32_binding_qualifier"]["VC_expansion"]=="Voltage Collapse","Incorrect VC terminology")
    require(proof["P32_binding_qualifier"]["exact_P32_meter_expression_or_weighted_adjustment_published_in_examined_sources"] is False,"Unsupported P32 telemetry-expression claim")
    require(proof["csv_sha256"]==sha(DEFS/"central_north_2025.csv"),"Qualifier CSV hash stale")
    require(proof["early_2025_season_source"]["csv_sha256"]==sha(DEFS/"central_north_winter2024_25.csv"),"Early qualifier hash stale")
    images=[SRC/f"{prefix}{page}.png" for prefix,pages in [("Summer2025_page-",[37,38,39]),("Winter2025_26_page-",[36,37,38]),("Winter2024_25_page-",[36,37,38])] for page in pages]
    require(all(p.exists() for p in images),"A visual verification page is absent")
    deps=[Path(__file__),SUMMER,WINTER,EARLY,proof_path]+images
    deps+=sorted(SRC.glob("*.pdf"))+sorted(SRC.glob("*.receipt.json"))
    deps.append(SUMMER.with_suffix(".receipt.json"));deps=list(dict.fromkeys(deps))
    receipt=dict(passed=True,status="literal_three_season_source_definitions_verified_not_promoted_to_model_operators",
        source_only=True,no_observed_flow_or_metric_reads=True,no_fitted_signs_weights_or_parameters=True,
        old_reports_models_and_case_artifacts_modified=False,literal_terms_checked_against_source_PDF_text=132,
        distinct_seasonal_definitions=9,counts_per_season={"MOSES SOUTH":7,"TOTAL EAST":29,"CENTRAL EAST":8},
        visual_PDF_pages={"Winter2024-25":[36,37,38],"Summer2025":[37,38,39],"Winter2025-26":[36,37,38]},
        visual_printed_pages={"Winter2024-25":[63,64,65],"Summer2025":[37,38,39],"Winter2025-26":[36,37,38]},
        metered_end_policy="Only identifiable named endpoints receive from/to. Allsingle-stationInghamsPAR/bus-tie ports remainunspecified; literalasteriskplacement remainsin source_name/verbatimterm.",
        exact_operational_cutover_hours_established=False,P32_CEVC_exact_expression_established=False,
        physical_model_operator_promotion_allowed=False,
        structural_delta_summary={"late_2025_Moses":"Moses230 MA1/MA2 toHaverstock345 HA1/HA2;fiveothermembersunchanged.",
            "early_2025_CentralEast":"Inghams PAR 2 withtrailingstar andR81trailingstar versuslaterPAR/R81unstarred.",
            "early_2025_TotalEast":"Closter/Cresskillcircuit751nameconflict andHillburn/Hilburnspelling; noautomaticalias."},
        dependencies=[dict(path=rel(p),sha256=sha(p))for p in deps],
        outputs=[dict(path=rel(p),sha256=sha(p))for p in output])
    path=DEFS/"central_north_source_receipt.json"
    if verify:require(json.loads(path.read_text())==receipt,"Source receipt is stale")
    else:path.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in receipt.items()if k not in["dependencies","outputs"]},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--verify",action="store_true")
    build(parser.parse_args().verify)
