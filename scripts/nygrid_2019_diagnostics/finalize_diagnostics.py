"""Verify component receipts and fingerprint the completed diagnostic package.

Does not download, re-fit, or rerun any model. Source-reference PDFs may be
reacquired from their recorded URLs; their local availability is reported.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote

import nbformat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2019_diagnostics"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_record(record: dict) -> None:
    path = Path(record["path"])
    if not path.is_absolute():
        path = ROOT / path
    assert path.is_file() and sha(path) == record["sha256"], str(path)


def finalize() -> dict:
    verified = 0
    for name in ["load_audit_dependencies.csv", "western_manifest.csv"]:
        with (OUT / name).open(encoding="utf-8-sig", newline="") as stream:
            for record in csv.DictReader(stream):
                check_record(record); verified += 1
    counterfactual = json.loads((OUT / "counterfactual_summary.json").read_text())
    for record in counterfactual["inputs"]:
        check_record(record); verified += 1
    assert counterfactual["models_modified"] is False
    assert counterfactual["fitted_to_interface_targets"] is False
    assert len(counterfactual["checks"]) == 6
    assert all(r["maximum_nodal_residual_mw"] < 1e-7 for r in counterfactual["checks"])
    load = json.loads((OUT / "load_audit_summary.json").read_text())
    assert load["status"] == "reproduced" and load["official_monthly_archives"] == 12
    assert load["daily_csv_members"] == 365 and load["prepared_hour_zone_keys"] == 96360
    assert load["archive_acquisition_counts"] == {"fresh_official_download": 12}
    for name in ["csv_comparison", "mat_comparison"]:
        assert load[name]["rows_above_tolerance_or_missing"] == 0
        assert load[name]["max_absolute_difference_mw"] < 1e-8
    archive_bytes = 0
    for month in range(1, 13):
        name = f"2019{month:02d}01palIntegrated_csv.zip"
        path = OUT / "raw_archives" / name
        receipt = json.loads(path.with_name(name + ".provenance.json").read_text())
        assert sha(path) == receipt["sha256"]
        archive_bytes += path.stat().st_size
    sources = json.loads((OUT / "western_source_evidence.json").read_text())
    for record in sources["local_source_fingerprints"]:
        check_record(record); verified += 1
    references = {"available_and_hash_verified": [], "not_locally_cached": []}
    for record in sources["source_receipts"]:
        path = ROOT / record["path"]
        if path.is_file():
            assert sha(path) == record["sha256"]
            references["available_and_hash_verified"].append(record["filename"])
        else:
            references["not_locally_cached"].append(record["filename"])
    nb = nbformat.read(OUT / "2019_load_western_diagnostics.ipynb", as_version=4)
    nbformat.validate(nb)
    cells = [c for c in nb.cells if c.cell_type == "code"]
    assert len(cells) == 5 and all(c.execution_count is not None for c in cells)
    assert not any(o.output_type == "error" for c in cells for o in c.outputs)
    assert any("image/png" in o.get("data", {}) for c in cells for o in c.outputs)
    # The notebook's embedded input hashes bind its execution to this evidence.
    expected = re.search(r"EXPECTED_HASHES = (\{[^\n]+\})", cells[0].source)
    assert expected is not None
    import ast
    for name, digest in ast.literal_eval(expected.group(1)).items():
        assert sha(OUT / name) == digest, name
    for path in OUT.rglob("*.csv"):
        assert b"\r\n" not in path.read_bytes(), f"Noncanonical CSV: {path}"
    report = ROOT / "NYGRID_2019_LOAD_AND_WESTERN_DIAGNOSTICS.md"
    for target in re.findall(r"\]\(([^)]+)\)", report.read_text(encoding="utf-8")):
        if not target.startswith(("https://", "http://", "#")):
            assert (ROOT / unquote(target)).exists(), target
    check = {"verified_local_date": "2026-10-09", "passed": True,
             "component_input_output_fingerprints_verified": verified,
             "raw_monthly_archives_preserved": 12, "raw_archive_bytes": archive_bytes,
             "load_matched_zone_hours": 96360, "paired_scenarios": 6,
             "notebook_executed_code_cells": 5, "notebook_error_outputs": 0,
             "reference_pdf_status": references, "baseline_models_modified": False,
             "unique_physical_cause_identified": False}
    (OUT / "delivery_checks.json").write_text(json.dumps(check, indent=2) + "\n", encoding="utf-8", newline="\n")
    paths = [p for p in OUT.rglob("*") if p.is_file() and p.name != "delivery_manifest.json"]
    paths += list((ROOT / "scripts/nygrid_2019_diagnostics").glob("*.py"))
    paths += [report]
    manifest = {"scope": "raw-load verification and western flow diagnosis with preserved baseline",
                "checks": check, "files": [{"path": p.relative_to(ROOT).as_posix(),
                "bytes": p.stat().st_size, "sha256": sha(p)} for p in sorted(set(paths))]}
    (OUT / "delivery_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {**check, "delivery_files": len(manifest["files"])}


if __name__ == "__main__":
    print(json.dumps(finalize(), indent=2))
