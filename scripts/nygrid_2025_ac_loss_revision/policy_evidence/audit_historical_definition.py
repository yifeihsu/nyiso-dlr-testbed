"""Verify the archived 2025 NYISO actual-load definition without changing policy."""
from pathlib import Path
from datetime import datetime, timezone
import base64
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output/nygrid_2025_ac_loss_revision/policy_evidence"
SOURCES = OUT / "sources"


def record(path):
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def main():
    stem = "NYISO_MPG_archived_20250806"
    pdf = SOURCES / (stem + ".pdf")
    text_path = SOURCES / (stem + ".txt")
    download_receipt = SOURCES / (stem + ".receipt.json")
    receipt = json.loads(download_receipt.read_text())
    raw = pdf.read_bytes()
    assert record(pdf)["sha256"] == receipt["sha256"]
    assert len(raw) == receipt["bytes"] == 6843019
    assert raw.startswith(b"%PDF") and b"%%EOF" in raw[-1024:]
    archive_sha1_base32 = base64.b32encode(hashlib.sha1(raw).digest()).decode().rstrip("=")
    assert archive_sha1_base32 == "5G62PJZSKHDGAEEGOJOIYDME3RC2U2OV"
    pages = text_path.read_text(encoding="utf-8").split("\f")
    norm = lambda value: " ".join(value.split())
    assert "Issued: May 2025" in norm(pages[0])
    assert "Version: 16.0" in norm(pages[1]) and "Effective Date: 05/29/2025" in norm(pages[1])
    actual = "Actual loads are calculated as generation plus net interchange for each zone, based on real-time telemetered data."
    integrated = "The Integrated Real-Time Actual Load is posted after each hour and represents the time-weighted hourly load for each zone."
    assert actual in norm(pages[89]) and integrated in norm(pages[90])
    current_text = SOURCES / "NYISO_Market_Participants_User_Guide.txt"
    assert actual in norm(current_text.read_text(encoding="utf-8"))
    assert integrated in norm(current_text.read_text(encoding="utf-8"))
    figures = [SOURCES / x for x in ["NYISO_MPG_2025_version_pdf2.png", "NYISO_MPG_2025_ActualLoad_pdf90.png", "NYISO_MPG_2025_IntegratedLoad_pdf91.png"]]
    assert all(p.exists() for p in figures)
    sealed_policy = OUT / "loss_accounting_policy_contract.json"
    sealed_comparison = ROOT / "output/nygrid_2025_ac_loss_revision/comparison/comparison_contract.json"
    comparison = json.loads(sealed_comparison.read_text())
    expected_policy = next(r for r in comparison["source_receipts"] if r["path"] == sealed_policy.relative_to(ROOT).as_posix())
    assert record(sealed_policy)["sha256"] == expected_policy["sha256"]
    result = dict(
        passed=True, created_utc=datetime.now(timezone.utc).isoformat(),
        role="Historical source-definition supplement; policy and comparison criteria unchanged",
        publisher="New York Independent System Operator",
        document="Market Participants User's Guide", version="16.0", effective_date="2025-05-29", issued="May 2025",
        original_official_url=receipt["source_url"], archived_official_url=receipt["archive_url"],
        archive_capture_timestamp="2025-08-06T05:18:58Z", archive_original_last_modified=receipt["archive_original_last_modified"],
        archive_CDX_SHA1_base32=archive_sha1_base32, full_PDF_sha256=record(pdf)["sha256"],
        complete_PDF_eof_and_parser_verified=True, title_and_definition_pages_visually_verified=True,
        source_sections=[
            dict(section="5.6.2 Actual Load", printed_page=56, PDF_page_1based=90,
                 primary_fact="Actual zonal load is calculated using generation and net interchange from telemetry."),
            dict(section="Integrated Real-Time Actual Load", printed_page=57, PDF_page_1based=91,
                 primary_fact="The integrated series is a time-weighted hourly value published after the hour."),
        ],
        same_actual_and_integrated_definition_text_in_current_2026_MPG=True,
        historical_2025_primary_definition_now_verified=True,
        scope_of_temporal_caveat_reduction="The actual-load balance definition now has a verified2025 primary-document snapshot; this does not establish that every 2025 manual revision was examined.",
        retained_scientific_limits=[
            "No observed2025 zonal transmission-loss values or exact physical meter terminals are supplied by this definition.",
            "Half-zone and whole-border loss ownership remain declared model accounting assumptions.",
            "The supplemental document does not change frozen timestamp interpretation, scaling, operating profiles, or interface operators.",
            "The transmission-dispatch forecast rule and EIA instructions previously archived remain2026 sources; no older versions of those were verified here.",
        ],
        unsuccessful_capture=dict(archive_capture_timestamp="2025-05-13T10:57:18Z",
                                  receipt=record(SOURCES / "NYISO_MPG_archived_20250513.receipt.json"),
                                  status="Archived PDF payload truncated at5242880bytes; excluded from definition evidence"),
        sealed_policy_and_comparison_contract_not_rewritten=True,
        sealed_policy=record(sealed_policy), sealed_comparison=record(sealed_comparison),
        sources=[record(p) for p in [pdf, text_path, download_receipt, current_text] + figures],
        source_code=record(Path(__file__)),
    )
    (OUT / "historical_definition_supplement.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "version": "16.0", "effective_date": "2025-05-29", "actual_load_PDF_page": 90,
                      "archive_digest_matches_CDX": True, "sealed_contracts_unchanged": True}))


if __name__ == "__main__":
    main()
