"""Independently inventory a latest-only ZIP and optionally extract it safely.

This checks package contents and runtime references. It does not claim that a
MATLAB smoke test or annual solution has run; that evidence is recorded apart.
"""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import shutil
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_latest_handoff"
PUBLIC = {
    "runtime/setup_nygrid_latest.m", "runtime/load_nygrid_latest.m",
    "runtime/run_nygrid_latest_acpf.m", "runtime/screen_nygrid_latest_dlr.m",
    "runtime/smoke_nygrid_latest.m",
}
MODEL_FILES = {
    "model/latest_model.mat", "model/profiles_h0001_4380.mat",
    "model/profiles_h4381_8760.mat",
}
OLD_MODEL_FILES = {
    "dispatch.mat", "dispatch_bounds.mat", "operating_inputs.mat",
    "operating_states.mat", "network_cases.mat", "full191_network_cases.mat",
    "x_nominal.mat", "pre_may.mat", "may21.mat", "may30.mat", "post_dover.mat",
    "inverse_target_summary.csv", "feasible_candidate_realizations.csv",
    "prior_redesign_imported_rx_restoration_candidates.csv",
    "nygrid_2025_dlr_handoff.md", "nygrid_2025_conductor_inference.md",
}
FORBIDDEN_ROOTS = {
    "output", "scripts", "system matpower format", "raw", "raw_sources",
    "archives", "archive", "historical", "history", "legacy", "node_modules",
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--extract-root", type=Path)
    parser.add_argument("--receipt", type=Path, default=OUT / "independent_archive_inventory.json")
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    receipt = args.receipt.resolve()
    assert receipt.is_relative_to(OUT.resolve()), "Write the audit only in its current namespace"
    target = args.extract_root.resolve() if args.extract_root else None
    if target:
        temporary_root = Path(tempfile.gettempdir()).resolve()
        assert target.is_relative_to(temporary_root) and target != temporary_root, "Use an explicitly selected new directory beneath the OS temporary root"
        assert not target.is_relative_to(ROOT.resolve()), "Portable extraction must be outside the research checkout"
        assert not target.exists(), "Use a new extraction directory; existing artifacts are never replaced"
    findings, inventory, runtime_hits = [], [], []
    with zipfile.ZipFile(archive) as bundle:
        files = [info for info in bundle.infolist() if not info.is_dir()]
        model_paths = [i.filename for i in files if i.filename.endswith("model/latest_model.mat")]
        assert len(model_paths) == 1, "Expected exactly one consolidated model/latest_model.mat"
        prefix = model_paths[0][:-len("model/latest_model.mat")]
        assert all(i.filename.startswith(prefix) for i in files), "Files lie outside the declared package root"
        seen = set()
        for info in files:
            raw = info.filename
            path = PurePosixPath(raw)
            assert not path.is_absolute() and ".." not in path.parts and "\\" not in raw
            assert not any(":" in part for part in path.parts), "Unexpected drive or alternate data stream"
            assert not stat.S_ISLNK(info.external_attr >> 16), "Symlink archive entries are not permitted"
            relative = raw[len(prefix):]
            key = relative.casefold()
            assert key not in seen, "Duplicate or Windows case-colliding archive entry"
            seen.add(key)
            relpath = PurePosixPath(relative)
            lower = relative.lower()
            vendor = lower.startswith("vendor/")
            if relpath.parts[0].lower() in FORBIDDEN_ROOTS:
                findings.append({"path": relative, "reason": "historical_or_repository_tree_in_package"})
            if not vendor and relpath.name.lower() in OLD_MODEL_FILES:
                findings.append({"path": relative, "reason": "historical_model_or_corpus_file"})
            if not vendor and re.search(r"(?:^|/)(?:npcc_nygrid_2025_|run_nygrid_2025_|screen_nygrid_2025_)", lower):
                findings.append({"path": relative, "reason": "historical_project_entrypoint"})
            if lower.endswith((".zip", ".tar", ".tar.gz", ".tgz", ".7z", ".pdf")):
                findings.append({"path": relative, "reason": "nested_archive_or_unrequested_PDF"})
            if lower.endswith(".mat") and lower not in MODEL_FILES:
                findings.append({"path": relative, "reason": "additional_model_or_result_MAT_corpus"})
            if vendor and any(part.lower() in {"data", "examples", "tests", "test", "t", "docs", "most"} for part in relpath.parts[2:-1]):
                findings.append({"path": relative, "reason": "vendor_non_runtime_tree"})
            if vendor and relpath.suffix.lower() in {".dll", ".exe", ".mexw64", ".mexa64", ".mexmaci64"}:
                findings.append({"path": relative, "reason": "optional_vendor_binary"})
            if not vendor and relpath.suffix.lower() in {".m", ".py"}:
                text = bundle.read(info).decode("utf-8-sig")
                patterns = {
                    "prior_repository_namespace_reference": r"nygrid_2025_(?:ac_system|ac_loss_revision|compact_ac|dlr_handoff|conductor_inference|dispatch|dover_parameters|western_audit|par_controls|moses_audit|slim|line_parameters|inputs)",
                    "prior_loader_or_screen_reference": r"\b(?:npcc_nygrid_2025_|run_nygrid_2025_|screen_nygrid_2025_)",
                    "historical_model_option": r"legacy_single_slack|legacy_engineering|--audit-model",
                    "hardcoded_windows_runtime_path": r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]",
                }
                for reason, pattern in patterns.items():
                    for match in re.finditer(pattern, text):
                        runtime_hits.append({"path": relative, "reason": reason,
                                             "line": text.count("\n", 0, match.start()) + 1,
                                             "matched": match.group(0)})
            h = hashlib.sha256()
            with bundle.open(info) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(block)
            inventory.append({"path": relative, "bytes": info.file_size,
                              "sha256": h.hexdigest(), "vendor": vendor})
        present = {r["path"] for r in inventory}
        for name in sorted(PUBLIC | MODEL_FILES | {"model/model_receipt.json"}):
            if name not in present:
                findings.append({"path": name, "reason": "missing_required_current_entrypoint_or_model"})
        for component in ["", "mips/", "mp-opt-model/", "mptest/"]:
            for name in ["LICENSE", "AUTHORS"]:
                name = "vendor/matpower8.1/" + component + name
                if name not in present:
                    findings.append({"path": name, "reason": "missing_vendor_notice"})
        notice_inventory = OUT / "current_source_and_notices_inventory.json"
        if notice_inventory.exists():
            expected = json.loads(notice_inventory.read_text(encoding="utf-8"))
            actual = {r["path"]: r for r in inventory}
            for item in expected["required_original_notice_files"]:
                if item["package_path"] not in actual or actual[item["package_path"]]["sha256"] != item["sha256"]:
                    findings.append({"path": item["package_path"], "reason": "original_vendor_notice_missing_or_changed"})
        passed = not findings and not runtime_hits
        if target and passed:
            target.mkdir(parents=True)
            for info in files:
                relative = PurePosixPath(info.filename[len(prefix):])
                destination = target.joinpath(*relative.parts)
                assert destination.resolve().is_relative_to(target)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as source, destination.open("xb") as sink:
                    shutil.copyfileobj(source, sink)
            bad = [r["path"] for r in inventory if digest(target / r["path"]) != r["sha256"]]
            assert not bad, "Extracted files differ from their archive bytes"
    result = dict(passed=passed, created_utc=datetime.now(timezone.utc).isoformat(),
        scope="Independent latest-only archive membership, runtime-reference and byte-exact extraction audit",
        archive_path=str(archive), archive_sha256=digest(archive), archive_prefix=prefix,
        file_count=len(inventory), vendor_file_count=sum(r["vendor"] for r in inventory),
        total_uncompressed_bytes=sum(r["bytes"] for r in inventory),
        current_model_data_file_count=sum(r["path"].endswith(".mat") for r in inventory),
        model_variant_count=1,
        historical_file_findings=findings, runtime_dependency_reference_findings=runtime_hits,
        extracted_root=str(target) if target and passed else None,
        byte_exact_extraction_verified=bool(target and passed),
        portable_MATLAB_smoke_performed=False, annual_solution_run=False,
        audit_script_sha256=digest(Path(__file__)), files=inventory)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ["passed", "file_count", "vendor_file_count",
        "current_model_data_file_count", "historical_file_findings", "runtime_dependency_reference_findings", "extracted_root"]}))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
