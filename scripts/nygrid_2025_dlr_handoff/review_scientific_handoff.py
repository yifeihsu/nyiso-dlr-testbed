"""Bind the handoff scientific review to its manuscript, evidence and helpers.

This performs no electrical solve and writes only inside the handoff namespace.
The scientific conclusions are a reviewer assessment; the checks below verify
that the assessed files and their dependencies are still the reviewed versions.
"""
from pathlib import Path
from urllib.parse import unquote
from datetime import datetime, timezone
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_dlr_handoff"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def record(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}


def main():
    inventory_path = OUT / "model_and_modification_inventory.json"
    thermal_path = OUT / "independent_thermal_scope/independent_thermal_scope_review.json"
    manuscript = ROOT / "NYGRID_2025_DLR_HANDOFF.md"
    document = ROOT / "NYGRID_2025_DLR_HANDOFF.docx"
    visual_path = OUT / "handbook_visual_review.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    thermal = json.loads(thermal_path.read_text(encoding="utf-8"))
    assert inventory["passed"] and thermal["passed"]
    assert inventory["baseline_HEAD"] == "8188cbec1172219a0414881121ad042b405a4044"
    checked = []
    for source in inventory["sources"] + thermal["dependencies"] + thermal["outputs"]:
        path = ROOT / source["path"]
        assert digest(path) == source["sha256"], f"Reviewed dependency changed: {path}"
        checked.append(source)
    text = manuscript.read_text(encoding="utf-8")
    for phrase in [
        "8,170 hours", "148 retained buses", "1,464 generator rows",
        "none satisfies the joint voltage", "Do not divide recovered AC amperes by gamma",
        "equation and accounting studies", "not an identified installed direct line",
        "Parent 224", "95.45%", "94.52%", "324 old successes are lost",
        "not an annual causal or WAPE decomposition", "same 8,170 hours",
        "not delivered by this handoff", "four of eight", "explicit weather",
        "Successive pi sections use their own recovered currents",
    ]:
        assert phrase in text, f"Required reviewed qualification missing: {phrase}"
    links = []
    for target in re.findall(r"\]\(([^)]+)\)", text):
        if re.match(r"[a-z]+://", target) or target.startswith("#"):
            continue
        relative = unquote(target.split("#", 1)[0])
        assert (ROOT / relative).is_file(), f"Broken handoff evidence link: {relative}"
        links.append(relative)
    case_checks = thermal["checks"]
    assert [x["hour_index"] for x in case_checks] == [4000, 8508]
    assert [x["candidate_parents"] for x in case_checks] == [44, 46]
    assert [x["candidate_segments"] for x in case_checks] == [44, 47]
    assert all(x["passed"] and not x["inherited_operating_qualified"] for x in case_checks)
    assert not thermal["fresh_PF_or_OPF_run"]
    visual = json.loads(visual_path.read_text(encoding="utf-8"))
    assert visual["passed"] and visual["page_count"] == 21
    assert visual["docx_sha256"] == digest(document)
    assert visual["markdown_sha256"] == digest(manuscript)
    report = {
        "passed": True,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Scientific review of handoff manuscript, historical model inventory and new one-way thermal helpers; no new PF or OPF",
        "model_base_commit": inventory["baseline_HEAD"],
        "new_handoff_documents_and_helpers_only": True,
        "old_models_results_and_core_modified_by_this_review": False,
        "old_numerical_results_are_saved_historical_evidence": True,
        "reviewed_claims": [
            "The S7/S13/S14, smaller calibrated NY models and Cornell NYgrid lineages are distinguished.",
            "Dated detailed and retained counts, source profiles, dispatch identities, scaling and original-branch axes are explicit.",
            "The loss-consistent replay is equation/accounting qualified on 8170 hours and operating qualified on none; extreme E/F loss fractions remain visible.",
            "Matched public comparisons use the same hours and disclose incomplete physical flowgate membership and terminal conventions.",
            "Parent 224 is an unresolved network equivalent with no conductor/DLR claim; identified source-conflicted parents are excluded.",
            "Screening uses catalog-reference resistance, current sharing and explicit scenario weather while retaining original PF qualifications.",
            "Independent cached-point phasor, Joule, terminal-current and guard checks passed on both network states.",
            "Material segments of one series element share its series current; successive pi sections use separately recovered currents.",
            "The new thermal helper is one-way screening; an integrated current-model DLR optimizer, electrothermal feedback and installed-asset qualification remain unavailable.",
            "The original bounded DLR optimizer and its four-of-eight record are historical, separately qualified evidence.",
        ],
        "manual_correction_resolved": "Clarified current sharing for material segments versus successive pi numerical sections.",
        "fresh_validation": {
            "reviewed_evidence_hash_checks": len(checked),
            "manuscript_local_links_checked": len(links),
            "cached_thermal_hours": [4000, 8508],
            "helper_dependency_hashes_current": True,
            "source_inventory_hashes_current": True,
        },
        "not_claimed": [
            "Historical asset or whole-system DLR validation",
            "Operating feasibility of the latest annual replay",
            "New annual replay or NYgrid OPF in this handoff review",
            "Archive portability; the separate extracted-package smoke provides that evidence",
            "Independent visual layout review; the document team's bound visual receipt provides that evidence",
        ],
        "dependencies": [record(manuscript), record(document), record(visual_path), record(inventory_path), record(thermal_path), record(Path(__file__).resolve())],
        "reviewed_evidence": checked,
    }
    target = OUT / "scientific_handoff_review.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"reviewed_evidence", "dependencies"}}, indent=2))


if __name__ == "__main__":
    main()
