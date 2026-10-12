"""Check western source rows against the separate 2025-26 winter PDF."""
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
WINTER = OUT / "sources/central_north/NYISO_Winter2025_2026_Appendices.pdf"
EXPECTED_WINTER_SHA256 = "bcf26e7ac908f43a29f34230067b5b1afc6e587845b26246d7ca39a41ef9f072"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: str) -> str:
    return re.sub(r"\s+", "", text.replace("‐", "-").replace("–", "-"))


def main() -> None:
    assert sha256(WINTER) == EXPECTED_WINTER_SHA256
    source = OUT / "definitions/western_2025.csv"
    with source.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    checks = []
    for interface, page, section_end in [
        ("Dysinger East", 35, "SPRAIN BROOK-DUNWOODIE SOUTH"),
        ("West Central", 41, "* indicates the metered end"),
    ]:
        text = subprocess.run(
            ["pdftotext", "-f", str(page), "-l", str(page), "-layout", "-enc", "UTF-8", str(WINTER), "-"],
            check=True, capture_output=True, encoding="utf-8",
        ).stdout
        section = text.split("DYSINGER EAST" if interface == "Dysinger East" else "West Central", 1)[1].split(section_end, 1)[0]
        lines = [norm(line) for line in section.splitlines() if line.strip()]
        entries = [row for row in rows if row["interface"] == interface]
        for row in entries:
            exact = norm(row["source_quote_or_verbatim_term"] + row["circuit_id"] + row["voltage_kv"])
            matched = lines.count(exact) == 1
            checks.append({"term_id": row["term_id"], "winter_pdf_page": page, "same_term_circuit_voltage_meter_marker": matched})
            assert matched, (row["term_id"], exact)
        # Candidate rows each end in a voltage field. Count these independently to
        # exclude an unnoticed additional term in the later seasonal definition.
        voltage_rows = [line for line in section.splitlines() if re.search(r"\s(?:345|230|115|34\.5/115|34\.5/115\s*&\s*12/115)\s*$", line)]
        checks.append({"interface": interface, "winter_pdf_page": page, "same_number_of_terms": len(voltage_rows) == len(entries), "winter_term_count": len(voltage_rows)})
        assert len(voltage_rows) == len(entries), (interface, len(voltage_rows), len(entries))
    dependencies = [source, source.with_suffix(".receipt.json"), WINTER, WINTER.with_suffix(".receipt.json"), Path(__file__),
                    OUT / "sources/western/Winter2025_26_Appendix_page035.png",
                    OUT / "sources/western/Winter2025_26_Appendix_page041.png"]
    result = {
        "status": "passed_source_only_western_seasonal_comparison",
        "passed": True,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "summer_catalog_posted": "2025-06-20",
        "winter_catalog_posted": "2025-10-17",
        "compared_terms": 24,
        "checks": checks,
        "visual_review": "Winter PDF pages 35 and 41 rendered with Poppler and inspected directly",
        "conclusion": "Dysinger East 10 entries and West Central 14 entries have unchanged names, circuit IDs, voltages and asterisk positions between the two seasonal publications.",
        "limitations": ["Publication dates are not asserted to be exact P32 effective timestamps.", "Four West Central transformer entries remain without marked meter ends.", "Winter 2024-25 is not included in this two-source comparison.", "No reduced-model circuit mapping, observed-flow calibration, or numerical sign inference is performed."],
        "dependencies": [{"path": str(p.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(p)} for p in dependencies],
    }
    destination = OUT / "definitions/western_seasonal_comparison.json"
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": len(checks), "path": str(destination)}))


if __name__ == "__main__":
    main()
