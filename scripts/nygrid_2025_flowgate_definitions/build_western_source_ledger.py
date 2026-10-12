"""Transcribe the visually checked 2025 NYISO western interface tables.

This source-only ledger makes no circuit-to-model or P32 effective-date claim.
The PDF pages and their rendered images must be inspected before changing rows.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_flowgate_definitions"
PDF = OUT / "sources/western/NYISO_Summer2025_Appendices_CE_Changes_APPROVED.pdf"
EXPECTED_PDF_SHA256 = "32e4fb86cc8397ab458fdf790ab52decfcaa9e9686de7aa9bec7527eaf04b901"

# source name, from station, to station, circuit, kV, meter end,
# verbatim source term, compound term, element kind, source zone, destination zone.
DYSINGER = [
    ("Dysinger-Station 255 (Henrietta)", "Dysinger", "Station 255 (Henrietta)", "DH1", "345", "from", "*Dysinger-Station 255 (Henrietta)", False, "line", "A", "B"),
    ("Dysinger-Station 255 (Henrietta)", "Dysinger", "Station 255 (Henrietta)", "DH2", "345", "from", "*Dysinger-Station 255 (Henrietta)", False, "line", "A", "B"),
    ("Lockport-N. Akron", "Lockport", "N. Akron", "108", "115", "from", "*Lockport-N. Akron", False, "line", "A", "B"),
    ("Lockport-Oakfield", "Lockport", "Oakfield", "112", "115", "from", "*Lockport-Oakfield", False, "line", "A", "B"),
    ("Lockport-Sweden 1", "Lockport", "Sweden 1", "111", "115", "from", "*Lockport-Sweden 1", False, "line", "A", "B"),
    ("Lockport-Shelby", "Lockport", "Shelby", "113", "115", "from", "*Lockport-Shelby", False, "line", "A", "B"),
    ("Lockport-Telegraph", "Lockport", "Telegraph", "107", "115", "from", "*Lockport-Telegraph", False, "line", "A", "B"),
    ("Lockport-Telegraph", "Lockport", "Telegraph", "114", "115", "from", "*Lockport-Telegraph", False, "line", "A", "B"),
    ("Stolle Road-High Sheldon", "Stolle Road", "High Sheldon", "67", "230", "from", "*Stolle Road-High Sheldon", False, "line", "A", "C"),
    ("Andover-Palmiter", "Andover", "Palmiter", "157-932", "115", "from", "*Andover-Palmiter", False, "line", "A", "C"),
]

WEST_CENTRAL = [
    ("Pannell Rd-Clay", "Pannell Rd", "Clay", "PC1", "345", "to", "Pannell Rd‐Clay*", False, "line", "B", "C"),
    ("Pannell Rd-Clay", "Pannell Rd", "Clay", "PC2", "345", "to", "Pannell Rd‐Clay*", False, "line", "B", "C"),
    ("Quaker-Macedon", "Quaker", "Macedon", "930", "115", "from", "*Quaker‐Macedon", False, "line", "B", "C"),
    ("Mortimer-Hook Rd-Elbridge", "Mortimer", "Elbridge", "1/7", "115", "from", "*Mortimer‐Hook Rd‐ Elbridge", True, "compound_path", "B", "C"),
    ("Mortimer-Elbridge", "Mortimer", "Elbridge", "2", "115", "from", "*Mortimer‐Elbridge", False, "line", "B", "C"),
    ("Pannell-Farmington", "Pannell", "Farmington", "4", "115", "from", "*Pannell‐Farmington", False, "line", "B", "C"),
    ("Quaker-Sleight Rd", "Quaker", "Sleight Rd", "13", "115", "from", "*Quaker‐Sleight Rd", False, "line", "B", "C"),
    ("St. 162-S. Perry", "St. 162", "S. Perry", "906", "115", "from", "*St. 162 ‐ S. Perry", False, "line", "B", "C"),
    ("Hook Rd (RGE-NGRID)", "Hook Rd (RGE-NGRID)", "", "TB#3", "34.5/115", "unspecified", "Hook Rd (RGE‐NGRID)", False, "transformer", "B", "C"),
    ("Clyde", "Clyde", "", "TR1", "34.5/115", "unspecified", "Clyde", False, "transformer", "B", "C"),
    ("(Farmington 34.5/115kV)", "Farmington", "", "#7", "34.5/115", "unspecified", "(Farmington 34.5/115kV)", False, "transformer", "B", "C"),
    ("(Farmtington 34.5/115kV&12/115 kV)", "Farmtington", "", "#4", "34.5/115 & 12/115", "unspecified", "(Farmtington 34.5/115kV&12/115 kV)", True, "compound_transformer", "B", "C"),
    DYSINGER[-2],
    DYSINGER[-1],
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", text.replace("‐", "-").replace("–", "-"))


def main() -> None:
    assert sha256(PDF) == EXPECTED_PDF_SHA256
    pages = PDF.with_suffix(".txt").read_text(encoding="utf-8").split("\f")
    rows = []
    checks = []
    for interface, def_id, page, entries in [
        ("Dysinger East", "dysinger_east_summer2025", 36, DYSINGER),
        ("West Central", "west_central_summer2025", 42, WEST_CENTRAL),
    ]:
        lines = [normalized(line) for line in pages[page - 1].splitlines()]
        for i, entry in enumerate(entries, 1):
            name, start, end, circuit, kv, meter, quote, compound, kind, zfrom, zto = entry
            # Require the quoted term, circuit ID and voltage on the same PDF row.
            found = any(normalized(quote + circuit + kv) == line for line in lines)
            checks.append({"check": f"{def_id}_{i:02d}_exact_pdf_row", "passed": found})
            assert found, (interface, i, quote, circuit, kv)
            rows.append({
                "interface": interface,
                "definition_id": def_id,
                "term_id": f"{def_id}_{i:02d}",
                "source_name": name,
                "from_station": start,
                "to_station": end,
                "circuit_id": circuit,
                "voltage_kv": kv,
                "metered_end": meter,
                "source_pdf": str(PDF.relative_to(ROOT)).replace("\\", "/"),
                "pdf_page": page,
                "printed_page": page,
                "source_date": "2025-06-20",
                "posted_date": "2025-06-20",
                "scope_period": "Summer 2025 study; exact P32 validity interval not supplied",
                "source_quote_or_verbatim_term": quote,
                "asterisk_present": "*" in quote,
                "compound_term": compound,
                "element_kind": kind,
                "source_from_zone": zfrom,
                "source_to_zone": zto,
                "orientation_status": "source table order; no numeric P32 sign asserted",
                "meter_note": "asterisk identifies circuit metered end" if meter != "unspecified" else "source has no asterisk; do not infer metered winding",
            })
    assert len(rows) == 24
    assert sum(row["metered_end"] == "unspecified" for row in rows) == 4
    assert len({row["term_id"] for row in rows}) == 24
    dest = OUT / "definitions/western_2025.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    dependencies = [PDF, PDF.with_suffix(".txt"), PDF.with_suffix(".receipt.json"), Path(__file__),
                    PDF.parent / "Summer2025_Appendix_page036.png", PDF.parent / "Summer2025_Appendix_page042.png"]
    receipt = {
        "status": "passed_source_transcription_only",
        "passed": True,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "definition_row_counts": {"Dysinger East": 10, "West Central": 14},
        "unstarred_meter_terms": 4,
        "visual_inspection": "PDF pages 36 and 42 rendered with Poppler and inspected directly",
        "checks": checks,
        "dependencies": [{"path": str(p.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(p)} for p in dependencies],
        "output": {"path": str(dest.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(dest)},
        "limitations": [
            "14 West Central entries include compound paths and transformer entries, not 14 certified single circuits.",
            "Farmtington spelling is preserved from the source; no source identity repair is implied.",
            "Source table order and asterisk position are transcribed; P32 numeric sign and exact validity dates need separate evidence.",
            "No circuit-to-NPCC/PERFORM mapping, circuit parameters, measured flows, fitting, or model updates occur in this script.",
            "Summer 2025 publication is a dated operating-study definition and does not itself prove annual hourly P32 membership.",
        ],
    }
    dest.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "rows": len(rows), "checks": len(checks), "path": str(dest)}))


if __name__ == "__main__":
    main()
