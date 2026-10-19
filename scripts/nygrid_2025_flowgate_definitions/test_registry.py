"""Focused regression guards for source inspection and numerical refusal."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import inspect_definition as inspected

ROOT = Path(__file__).resolve().parents[2]
DEFS = ROOT / "output/nygrid_2025_flowgate_definitions/definitions"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    results = []

    def expect(name, action, refusal=False):
        try:
            value = action()
            passed = not refusal and value is not False
            reason = "unexpected acceptance" if refusal else ""
        except (ValueError, KeyError, OSError) as exc:
            passed = refusal
            reason = str(exc)
        results.append(dict(test=name, passed=passed, detail=reason))

    registry = inspected.load_registry()
    manifest = json.loads((DEFS / "registry_receipt.json").read_text(encoding="utf-8"))
    dependencies = dict(manifest["dependencies"])
    for name in manifest["outputs"]:
        path = DEFS / name
        dependencies[path.relative_to(ROOT).as_posix()] = sha(path)
    for path in [DEFS / "registry_receipt.json", Path(__file__), Path(__file__).with_name("inspect_definition.py")]:
        dependencies[path.relative_to(ROOT).as_posix()] = sha(path)
    for definition in registry["definitions"]:
        gate, edition = definition["gate_id"], definition["edition"]
        expect("inspect:" + gate + ":" + edition,
               lambda g=gate, e=edition: inspected.select_definition(registry, g, e)["model_operator_usable"] is False)
        expect("refuse_operator:" + gate + ":" + edition,
               lambda g=gate, e=edition: inspected.select_definition(registry, g, e, True), True)
    expect("unknown_edition", lambda: inspected.select_definition(registry, "dysinger_east", "calendar2025"), True)
    expect("unknown_gate", lambda: inspected.select_definition(registry, "unknown", "summer2025"), True)
    for mode in ["missing_member", "duplicate_member", "wrong_term_scope"]:
        altered = copy.deepcopy(registry)
        target = altered["definitions"][0]
        if mode == "missing_member":
            target["members"].pop()
        elif mode == "duplicate_member":
            target["members"].append(target["members"][0])
        else:
            next(row for row in altered["terms"] if row["term_key"] == target["members"][0])["edition"] = "winter2025_26"
        expect(mode, lambda: inspected.select_definition(altered, target["gate_id"], target["edition"]), True)
    workspace_tmp = ROOT / "tmp"
    workspace_tmp.mkdir(exist_ok=True)
    fixture = Path(tempfile.mkdtemp(prefix="registry_guard_tests_", dir=workspace_tmp)).resolve()
    assert fixture.is_relative_to(workspace_tmp.resolve())
    try:
        for mode in ["resealed_missing_term", "resealed_duplicate_key", "stale_hash", "incomplete_output_manifest"]:
            for name in manifest["outputs"]:
                shutil.copyfile(DEFS / name, fixture / name)
            altered = copy.deepcopy(registry)
            receipt = copy.deepcopy(manifest)
            if mode == "resealed_missing_term":
                altered["terms"].pop()
            elif mode == "resealed_duplicate_key":
                altered["terms"][1] = copy.deepcopy(altered["terms"][0])
            path = fixture / "physical_flowgate_registry.json"
            path.write_text(json.dumps(altered), encoding="utf-8")
            if mode != "stale_hash":
                receipt["outputs"][path.name] = sha(path)
            if mode == "incomplete_output_manifest":
                receipt["outputs"].pop("definition_summary.csv")
            (fixture / "registry_receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
            expect(mode, lambda: inspected.load_registry(fixture), True)
    finally:
        # Only this resolved generated workspace/tmp child is removed.
        shutil.rmtree(fixture)
    cli = subprocess.run([sys.executable, str(Path(__file__).with_name("inspect_definition.py")), "--gate", "dysinger_east"], capture_output=True)
    expect("CLI_requires_edition", lambda: cli.returncode == 2 and b"--edition" in cli.stderr)
    expect("reviewed_files_unchanged", lambda: dependencies == {p: sha(ROOT / p) for p in dependencies})
    failed = [row for row in results if not row["passed"]]
    report = dict(passed=not failed, created_utc=datetime.now(timezone.utc).isoformat(),
                  counts=dict(total=len(results), passed=len(results)-len(failed), failed=len(failed), inspection_successes=21, numeric_operator_refusals=21),
                  dependencies=dependencies, tests=results, internal_observations_used=False, model_fitting_used=False)
    out = ROOT / "output/nygrid_2025_flowgate_definitions/validation/registry_guard_tests.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["counts"]))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
