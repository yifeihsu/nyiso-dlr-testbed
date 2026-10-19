"""Verify current evidence dependencies and fingerprint the scoped delivery."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import pandas as pd
from replay_refinement import DEFAULT, ROOT, require, sha

MANIFEST = DEFAULT / "delivery_manifest.json"
EXCLUDED = {"__pycache__", "initial_partial_K_load_20261010"}


def check_receipt(path, list_names):
    data = json.loads(path.read_text(encoding="utf-8"))
    if "passed" in data:
        require(data["passed"] is True, "Evidence not passed: " + str(path))
    for key in list_names:
        for entry in data.get(key, []):
            target = Path(entry["path"])
            if not target.is_absolute():
                target = ROOT / target
            require(target.is_file() and sha(target) == entry["sha256"], "Stale dependency: " + str(target))
    return data


def finalize(verify=False):
    for receipt, keys in [
        ("validation/baseline_reference.json", ["artifacts"]),
        ("validation/construction_validation.json", ["files"]),
        ("validation/annual_validation.json", ["files"]),
        ("validation/matlab_validation.json", ["dependencies"]),
        ("validation/focused_tests.json", ["files"]),
        ("replay/provenance.json", ["dependencies"]),
        ("sensitivity/sensitivity_manifest.json", ["dependencies"]),
    ]:
        check_receipt(DEFAULT / receipt, keys)
    construction = pd.read_csv(DEFAULT / "network/source_manifest.csv")
    for row in construction.itertuples(index=False):
        require(sha(ROOT / row.path) == row.sha256, "Construction dependency changed: " + row.path)
    score = json.loads((DEFAULT / "comparison/scoring_receipt.json").read_text())
    require(score["replay_provenance_sha256"] == sha(DEFAULT / "replay/provenance.json"), "Scoring replay receipt changed")
    require(score["scoring_code_sha256"] == sha(Path(__file__).with_name("score_refinement.py")), "Scoring code changed")
    replay = json.loads((DEFAULT / "replay/provenance.json").read_text())
    for row in replay["variants"]:
        require(sha(ROOT / row["file"]) == row["sha256"], "Replay artifact changed")
    sensitivity = json.loads((DEFAULT / "sensitivity/sensitivity_manifest.json").read_text())
    for row in sensitivity["outputs"]:
        require(sha(ROOT / row["output_path"]) == row["output_sha256"], "Sensitivity artifact changed")
    paths = []
    for folder in [DEFAULT, ROOT / "scripts/nygrid_2025_downstate"]:
        paths += [p for p in folder.rglob("*") if p.is_file() and not set(p.parts) & EXCLUDED and p != MANIFEST]
    paths += [ROOT / "System Matpower Format/npcc_nygrid_2025_downstate_dc.m", ROOT / "NYGRID_2025_DOWNSTATE_REFINEMENT.md"]
    entries = []
    for path in sorted(paths):
        require(path.stat().st_size < 100 * 1024**2, "Individual file exceeds portable Git size: " + str(path))
        entries.append(dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    manifest = dict(status="verified_current_research_delivery", files=len(entries),
        total_bytes=sum(e["bytes"] for e in entries), maximum_file_bytes=max(e["bytes"] for e in entries),
        baseline_files_modified=False, physical_2025_model_certification=False,
        local_intermediate_history_excluded=True, entries=entries)
    if verify:
        require(json.loads(MANIFEST.read_text()) == manifest, "Delivery manifest is stale")
    else:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in manifest.items() if k != "entries"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    finalize(parser.parse_args().verify)
