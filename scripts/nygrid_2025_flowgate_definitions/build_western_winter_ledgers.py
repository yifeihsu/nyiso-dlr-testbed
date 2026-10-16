"""Transcribe both winter western tables without overwriting the summer ledger.

Every output row is checked as a complete line against its own PDF, including
source ambiguities. A successful transcription does not resolve those ambiguities.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_flowgate_definitions"
SUMMER = OUT / "definitions/western_2025.csv"
SOURCES = [
    ("2025_26", "2025-10-17", "NYISO_Winter2025_2026_Appendices.pdf", "bcf26e7ac908f43a29f34230067b5b1afc6e587845b26246d7ca39a41ef9f072", 0),
    ("2024_25", "2024-10-24", "NYISO_Winter2024_2025_Appendices_APPROVED.pdf", "546402b7e85f51441e64a6b68adac53579f83828f6bc8c1195ccc480e082dc0b", 27),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: str) -> str:
    return re.sub(r"\s+", "", text.replace("‐", "-").replace("–", "-"))


def modify(base: dict, **changes) -> dict:
    return dict(base, **changes)


def early_rows(summer: list[dict]) -> list[dict]:
    dys = [dict(row) for row in summer if row["interface"] == "Dysinger East"]
    west = [dict(row) for row in summer if row["interface"] == "West Central"]
    dys[4].update(source_name="Lockport- Telegraph", to_station="Telegraph",
                  source_quote_or_verbatim_term="*Lockport- Telegraph",
                  source_issue="winter2024_25_Telegraph_111_vs_later_Sweden1_111_no_alias_or_change_timestamp_proven")
    result = dys + [
        west[0], west[1],
        modify(west[2], source_issue="possible_duplicate_of_Quaker_Rd_Macedon_930_row_not_deduplicated", possible_duplicate_group="winter2024_25_WC_930"),
        modify(west[3], source_name="Mortimer-Fairport", to_station="Fairport", circuit_id="1", source_quote_or_verbatim_term="*Mortimer‐Fairport", compound_term=False, element_kind="line"),
        modify(west[4], source_name="Mortimer-Fairport", to_station="Fairport", circuit_id="2", source_quote_or_verbatim_term="*Mortimer‐Fairport"),
        modify(west[5], circuit_id="4-977"),
        modify(west[6], source_name="Quaker Rd-Sleight Rd", from_station="Quaker Rd", circuit_id="13-980", source_quote_or_verbatim_term="*Quaker Rd‐Sleight Rd"),
        modify(west[2], source_name="Quaker Rd-Macedon", from_station="Quaker Rd", source_quote_or_verbatim_term="*Quaker Rd-Macedon", source_issue="possible_duplicate_of_Quaker_Macedon_930_row_not_deduplicated", possible_duplicate_group="winter2024_25_WC_930"),
        west[7],
        modify(west[8], source_name="Hook Rd 34/115", from_station="Hook Rd", circuit_id="BK1", source_quote_or_verbatim_term="Hook Rd 34/115"),
        modify(west[8], source_name="Hook Rd 34/115", from_station="Hook Rd", circuit_id="BK2", source_quote_or_verbatim_term="Hook Rd 34/115"),
        modify(west[9], source_name="Clyde 34/115", source_quote_or_verbatim_term="Clyde 34/115"),
        modify(west[10], source_name="Farmington 34.5/115kV", source_quote_or_verbatim_term="Farmington 34.5/115kV"),
        modify(west[11], source_name="Farmington 12/115 kV", from_station="Farmington", voltage_kv="34.5/115", source_quote_or_verbatim_term="Farmington 12/115 kV", compound_term=False, element_kind="transformer", source_issue="source_name_12_115_conflicts_with_voltage_column_34p5_115_no_correction_inferred", voltage_name_column_conflict=True),
        west[12], west[13],
    ]
    return result


def main() -> None:
    before = sha(SUMMER)
    with SUMMER.open(newline="", encoding="utf-8") as handle:
        summer = list(csv.DictReader(handle))
    for season, posted, filename, expected, page_offset in SOURCES:
        pdf = OUT / "sources/central_north" / filename
        assert sha(pdf) == expected
        entries = [dict(row) for row in summer] if season == "2025_26" else early_rows(summer)
        checks, counts = [], {}
        for interface, page, heading, end_heading in [
            ("Dysinger East", 35, "DYSINGER EAST", "SPRAIN BROOK-DUNWOODIE SOUTH"),
            ("West Central", 41, "West Central", "* indicates the metered end"),
        ]:
            text = subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), "-layout", "-enc", "UTF-8", str(pdf), "-"],
                                  check=True, capture_output=True, encoding="utf-8").stdout
            section = text.split(heading, 1)[1].split(end_heading, 1)[0]
            lines = [norm(line) for line in section.splitlines()]
            rows = [row for row in entries if row["interface"] == interface]
            counts[interface] = len(rows)
            voltage_rows = [line for line in section.splitlines() if re.search(r"\s(?:345|230|115|34\.5/115|34\.5/115\s*&\s*12/115)\s*$", line)]
            assert len(voltage_rows) == len(rows), (season, interface, len(voltage_rows), len(rows))
            for i, row in enumerate(rows, 1):
                source_line = norm(row["source_quote_or_verbatim_term"] + row["circuit_id"] + row["voltage_kv"])
                assert lines.count(source_line) == 1, (season, interface, i, source_line)
                stem = "dysinger_east" if interface == "Dysinger East" else "west_central"
                definition = f"{stem}_winter{season}"
                row.update(definition_id=definition, term_id=f"{definition}_{i:02d}", source_pdf=str(pdf.relative_to(ROOT)).replace("\\", "/"),
                           pdf_page=page, printed_page=page+page_offset, source_date=posted, posted_date=posted,
                           scope_period=f"Winter {season.replace('_', '-')} study; exact P32 validity interval not supplied")
                row.setdefault("source_issue", "")
                row.setdefault("voltage_name_column_conflict", False)
                row.setdefault("possible_duplicate_group", "")
                row["source_entry_certified_as_unique_physical_circuit"] = False
                checks.append({"term_id": row["term_id"], "exact_own_pdf_row": True})
        expected_count = 24 if season == "2025_26" else 26
        assert len(entries) == expected_count
        assert len({row["term_id"] for row in entries}) == expected_count
        # Normalize column order while retaining each literal source value.
        columns = list(summer[0]) + ["source_issue", "voltage_name_column_conflict", "possible_duplicate_group", "source_entry_certified_as_unique_physical_circuit"]
        destination = OUT / f"definitions/western_winter{season}.csv"
        with destination.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(entries)
        dependencies = [SUMMER, pdf, pdf.with_suffix(".receipt.json"), Path(__file__),
                        OUT / f"sources/western/Winter{season}_Appendix_page035.png",
                        OUT / f"sources/western/Winter{season}_Appendix_page041.png"]
        issues = [dict(term_id=row["term_id"], source_issue=row["source_issue"]) for row in entries if row["source_issue"]]
        receipt = {
            "passed": True, "status": "passed_literal_transcription_source_ambiguities_preserved",
            "created_utc": datetime.now(timezone.utc).isoformat(), "row_counts": counts,
            "checks": checks, "source_issues": issues,
            "unmarked_meter_entries": sum(row["metered_end"] == "unspecified" for row in entries),
            "visual_review": f"Winter {season} PDF pages 35 and 41 inspected; printed pages {35+page_offset} and {41+page_offset}",
            "physical_definition_ready_for_numerical_compilation": False,
            "limitations": ["Publication date is not the effective timestamp of an hourly P32 definition.",
                            "All literal entries are preserved; apparent duplicate identities and inconsistent voltage labels are not silently corrected.",
                            "Changes across seasonal publications may include editing and physical resection; the source alone does not distinguish them.",
                            "No historical-to-2025 circuit alias, positive P32 sign, physical meter loss, or reduced-model coefficient is inferred."],
            "dependencies": [{"path": str(p.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(p)} for p in dependencies],
            "output": {"path": str(destination.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(destination)},
        }
        destination.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(json.dumps({"season": season, "row_counts": counts, "literal_checks": len(checks), "source_issues": issues}))
    assert sha(SUMMER) == before, "Summer ledger changed"


if __name__ == "__main__":
    main()
