"""Independent source checks plus mutation tests for the inspection-only loader."""
from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_flowgate_definitions"
DEFS = OUT / "definitions"
sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location("reviewed_inspector", Path(__file__).with_name("inspect_definition.py"))
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)

SOURCE_FILES = ["western_2025.csv", "western_winter2025_26.csv", "western_winter2024_25.csv",
                "central_north_2025.csv", "central_north_winter2024_25.csv", "downstate_2025.csv"]
COUNTS = {"dysinger_east": 10, "west_central": 14, "central_east": 8, "total_east": 29,
          "moses_south": 7, "upny_coned": 10, "sprain_dunwoodie_south": 11}
DATES = {"winter2024_25": "2024-10-24", "summer2025": "2025-06-20", "winter2025_26": "2025-10-17"}
SECTIONS = {"dysinger_east": ("DYSINGER EAST", "SPRAIN BROOK-DUNWOODIE SOUTH"),
            "sprain_dunwoodie_south": ("SPRAIN BROOK-DUNWOODIE SOUTH", "* indicates"),
            "moses_south": ("MOSES SOUTH", "UPNY-CONED"),
            "upny_coned": ("UPNY-CONED", "UPNY-SENY"),
            "total_east": ("TOTAL EAST", "* indicates"),
            "central_east": ("CENTRAL EAST", "CONED"),
            "west_central": ("West Central", "* indicates")}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def norm(value: str) -> str:
    for old, new in [("‐", "-"), ("‑", "-"), ("–", "-"), ("’", "'"), ("|", "")]:
        value = value.replace(old, new)
    return re.sub(r"\s+", "", value)


def main() -> None:
    checks = []

    def check(name, passed, detail=""):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    receipt = read(DEFS / "registry_receipt.json")
    registry = read(DEFS / "physical_flowgate_registry.json")
    before = {p: sha(ROOT / p) for p in receipt["dependencies"]}
    for path, digest in receipt["dependencies"].items():
        check("dependency:" + path, before[path] == digest)
    for path, digest in receipt["outputs"].items():
        check("output:" + path, sha(DEFS / path) == digest)
    originals = {}
    for filename in SOURCE_FILES:
        with (DEFS / filename).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                originals[row["definition_id"] + "::" + row["term_id"]] = row
    terms = registry["terms"]
    check("269 unique source rows, all preserved", len(originals) == len(terms) == len({x["term_key"] for x in terms}) == 269)
    check("source row key coverage", set(originals) == {x["term_key"] for x in terms})
    check("21 distinct gate editions", len(registry["definitions"]) == len({(x["gate_id"], x["edition"]) for x in registry["definitions"]}) == 21)
    cache = {}
    for row in terms:
        key = row["term_key"]
        original = originals[key]
        fields = ["definition_id", "term_id", "source_name", "from_station", "to_station", "circuit_id", "voltage_kv", "metered_end", "source_pdf", "pdf_page", "printed_page", "posted_date"]
        check("normalized_source_fields:" + key, all(str(row[field]) == original[field] for field in fields))
        check("date_and_unpromoted_flags:" + key,
              row["posted_date"] == DATES[row["edition"]] and not row["source_entry_unique_physical_identity_certified"]
              and not row["model_identity_certified"] and not row["P32_expression_certified"]
              and not row["operational_effective_start"] and not row["operational_effective_end"])
        check("source_issue_preserved:" + key, row["source_issue"] == original.get("source_issue", ""))
        expr = row["source_table_port_expression"]
        check("local_port_only:" + key, (not expr) if row["documentary_blockers"] else expr == {"from": "+PF", "to": "-PT"}.get(row["metered_end"], ""))
        pdfkey = row["source_pdf"], row["pdf_page"]
        if pdfkey not in cache:
            cache[pdfkey] = subprocess.run(["pdftotext", "-f", str(pdfkey[1]), "-l", str(pdfkey[1]), "-layout", "-enc", "UTF-8", str(ROOT / pdfkey[0]), "-"],
                                          check=True, capture_output=True, encoding="utf-8").stdout
        start, end = SECTIONS[row["gate_id"]]
        section = cache[pdfkey].split(start, 1)[1].split(end, 1)[0]
        literal = row["literal_term"]
        expected = norm(literal if "|" in literal else literal + row["circuit_id"] + row["voltage_kv"])
        check("own_pdf_complete_row:" + key, sum(norm(line) == expected for line in section.splitlines()) == 1)
        check("printed_page_footer:" + key, bool(re.search(r"\|\s*" + str(row["printed_page"]) + r"\s*$", cache[pdfkey].rstrip("\f\n\r "))))
    counter = Counter((x["edition"], x["gate_id"]) for x in terms)
    data = loader.load_registry()
    for edition in DATES:
        for gate, usual in COUNTS.items():
            expected = 16 if gate == "west_central" and edition == "winter2024_25" else usual
            label = edition + ":" + gate
            check("per_gate_cardinality:" + label, counter[(edition, gate)] == expected)
            try:
                selected = loader.select_definition(data, gate, edition)
                passed = len(selected["terms"]) == expected and selected["model_operator_usable"] is False and selected["definition"]["numeric_model_operator"] is None
            except Exception as exc:
                passed = False
            check("inspection_success:" + label, passed)
            try:
                loader.select_definition(data, gate, edition, True)
                rejected = False
            except ValueError:
                rejected = True
            check("numeric_operator_refusal:" + label, rejected)

    def refusal(name, action):
        try:
            action()
            check(name, False, "Invalid input was accepted")
        except (ValueError, OSError, KeyError):
            check(name, True)

    refusal("unknown_edition", lambda: loader.select_definition(data, "dysinger_east", "2025"))
    refusal("unknown_gate", lambda: loader.select_definition(data, "all_east", "summer2025"))
    changed = copy.deepcopy(data)
    target = changed["definitions"][0]
    target["members"].append(target["members"][0])
    refusal("duplicate_member_list", lambda: loader.select_definition(changed, target["gate_id"], target["edition"]))
    changed2 = copy.deepcopy(data)
    target2 = changed2["definitions"][0]
    target2["members"].pop()
    refusal("missing_member_list", lambda: loader.select_definition(changed2, target2["gate_id"], target2["edition"]))

    scratch_root = ROOT / "tmp"
    scratch_root.mkdir(exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="flowgate_registry_guard_", dir=scratch_root)).resolve()
    assert scratch.is_relative_to(scratch_root.resolve())
    try:
        def fixture(mutate=None, reseal=True):
            for name in receipt["outputs"]:
                shutil.copyfile(DEFS / name, scratch / name)
            shutil.copyfile(DEFS / "registry_receipt.json", scratch / "registry_receipt.json")
            altered = copy.deepcopy(registry)
            if mutate is not None:
                mutate(altered)
            dest = scratch / "physical_flowgate_registry.json"
            dest.write_text(json.dumps(altered), encoding="utf-8")
            if reseal:
                manifest = copy.deepcopy(receipt)
                manifest["outputs"][dest.name] = sha(dest)
                (scratch / "registry_receipt.json").write_text(json.dumps(manifest), encoding="utf-8")
        fixture(lambda obj: obj["terms"].pop())
        refusal("resealed_missing_term", lambda: loader.load_registry(scratch))
        fixture(lambda obj: obj["terms"].__setitem__(1, copy.deepcopy(obj["terms"][0])))
        refusal("resealed_duplicate_term_key", lambda: loader.load_registry(scratch))
        fixture(reseal=False)
        refusal("stale_output_hash", lambda: loader.load_registry(scratch))
    finally:
        # The resolved path was verified as a generated child of workspace/tmp.
        shutil.rmtree(scratch)
    check("all_source_hashes_unchanged", before == {p: sha(ROOT / p) for p in before})
    reviewed = {str((DEFS / p).relative_to(ROOT)).replace("\\", "/"): sha(DEFS / p) for p in receipt["outputs"]}
    reviewed.update(before)
    for path in [Path(__file__), Path(__file__).with_name("inspect_definition.py"), DEFS / "registry_receipt.json"]:
        reviewed[path.relative_to(ROOT).as_posix()] = sha(path)
    failures = [c for c in checks if not c["passed"]]
    result = dict(passed=not failures, status="independent_registry_and_loader_review", created_utc=datetime.now(timezone.utc).isoformat(),
                  check_count=len(checks), failed_count=len(failures), independent_pdf_pages=len(cache), literal_terms_checked=269,
                  inspection_successes=21, required_operator_refusals=21, reviewed_hashes=reviewed, checks=checks, failures=failures,
                  limitations=["Source-table port orientation is a local convention, not independently established P32 algebra.",
                               "A correct literal transcription does not resolve source duplicate possibilities, source voltage contradictions, model identity, or exact operational timestamps.",
                               "No internal-interface observations, model fitting, PF replay, or physical operator promotion was used."])
    output = OUT / "validation/registry_independent_review.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ["passed", "check_count", "failed_count", "independent_pdf_pages", "literal_terms_checked", "failures"]}))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
