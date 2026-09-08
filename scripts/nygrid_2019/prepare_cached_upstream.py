"""Create a separate NYgrid execution copy with indexed, immutable input caches.

The released sources and data are never edited. Only table loading/import
calls are replaced; the released hourly filters and all model arithmetic stay
in place. Run from any directory; defaults are relative to this repository.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "tmp/nygrid_2019_reproduction"
HELPERS = Path(__file__).resolve().parent / "cache_helpers"
MAT_FILES = {
    "Utility/readOpCond.m": 5,
    "Utility/allocateGen.m": 2,
    "Utility/allocateLoad.m": 1,
    "Data/allocateLoad.m": 1,
}
STATIC_IMPORTS = {
    "updateOpCond.m": ["importRenewableGen", "importBusInfo"],
    "OPFtestcase.m": ["importBusInfo"],
    "Utility/allocateGen.m": ["importNearestBus", "importFuelPrice", "importGenParam"],
    "Utility/allocateLoad.m": ["importBusInfo"],
    "Data/allocateLoad.m": ["importBusInfo"],
}
TIMED_IMPORTS = {
    "Utility/readOpCond.m": ["importFuelMix", "importInterFlow", "importZonalPrice", "importNuclearGen", "importHydroGen"],
    "Utility/allocateGen.m": ["importThermalGen"],
    "Utility/allocateLoad.m": ["importLoad"],
    "Data/allocateLoad.m": ["importLoad"],
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def transform(relative: str, original: bytes) -> tuple[bytes, list[dict]]:
    text = original.decode("utf-8")
    changes: list[dict] = []
    if relative in MAT_FILES:
        pattern = re.compile(r"(?m)^(\s*)load\((fullfile\([^\r\n]+\)),\s*'([A-Za-z]\w*)'\);([ \t]*\r?)$")
        def replace_load(match: re.Match) -> str:
            return f"{match[1]}nygrid_cached_load({match[2]},'{match[3]}',timeStamp);{match[4]}"
        text, count = pattern.subn(replace_load, text)
        if count != MAT_FILES[relative]:
            raise ValueError(f"Unexpected MAT load count in {relative}: {count}")
        changes.append({"kind": "MAT_table_load_to_indexed_cache", "count": count})
    for timed, mapping in [(False, STATIC_IMPORTS), (True, TIMED_IMPORTS)]:
        for name in mapping.get(relative, []):
            pattern = re.compile(r"(?m)^(\s*\w+\s*=\s*)" + name + r"\((fullfile\([^\r\n]+\))\);([ \t]*\r?)$")
            suffix = ",timeStamp" if timed else ""
            text, count = pattern.subn(lambda m: f"{m[1]}nygrid_cached_import(@{name},{m[2]}{suffix});{m[3]}", text)
            if count != 1:
                raise ValueError(f"Unexpected import count for {name} in {relative}: {count}")
            changes.append({"kind": "timed_CSV_import_cache" if timed else "static_CSV_import_cache", "reader": name, "count": count})
    return text.encode("utf-8"), changes


def prepare(source: Path, destination: Path, manifest_path: Path) -> dict:
    source, destination, manifest_path = source.resolve(), destination.resolve(), manifest_path.resolve()
    if not source.is_dir() or not (source / "updateOpCond.m").is_file():
        raise ValueError("Expected the verified, released NYgrid source directory")
    if source == destination or source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError("Execution copy must be separate from the immutable source")
    if not destination.is_relative_to(BASE.resolve()):
        raise ValueError("Execution copy must remain in tmp/nygrid_2019_reproduction")
    records, patches = [], []
    expected = set(MAT_FILES) | set(STATIC_IMPORTS) | set(TIMED_IMPORTS)
    seen = set()
    # Copy released code/data only; simulation results are never copied back.
    inputs = sorted(p for p in source.rglob("*") if p.is_file() and
                    not any(part in {"Result", "Result_Renewable", "Prep", ".git"} for part in p.relative_to(source).parts))
    staged = []
    for path in inputs:
        relative = path.relative_to(source).as_posix()
        original = path.read_bytes()
        if relative in expected:
            after, changes = transform(relative, original)
            seen.add(relative)
            patches.extend(difflib.unified_diff(original.decode("utf-8").splitlines(), after.decode("utf-8").splitlines(),
                fromfile="upstream/" + relative, tofile="cached_upstream/" + relative, lineterm=""))
        else:
            after, changes = original, []
        staged.append((destination / relative, after))
        records.append({"relative_path": relative, "source_sha256": sha(original), "generated_sha256": sha(after),
                        "bytes": len(after), "modified": original != after, "changes": changes})
    if seen != expected:
        raise ValueError(f"Missing expected released files: {sorted(expected - seen)}")
    helper_records = []
    for path in sorted(HELPERS.glob("nygrid_cached_*.m")):
        data = path.read_bytes()
        staged.append((destination / "Utility" / path.name, data))
        helper_records.append({"source_path": path.relative_to(ROOT).as_posix(),
                               "generated_path": "Utility/" + path.name, "sha256": sha(data)})
    if len(helper_records) != 3:
        raise ValueError("Expected all three cache helpers")
    # An existing different execution copy may be in use; do not overwrite it.
    for path, data in staged:
        if path.exists() and path.read_bytes() != data:
            raise FileExistsError(f"Refusing to replace a different execution copy: {path}")
    for path, data in staged:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
    patch_path = manifest_path.with_suffix(".patch")
    patch_bytes = ("\n".join(patches) + "\n").encode("utf-8")
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_bytes(patch_bytes)
    manifest = {
        "schema_version": 1,
        "purpose": "Performance-only separate execution copy of pinned NYgrid sources",
        "source_path": str(source), "execution_path": str(destination),
        "generator_script": Path(__file__).relative_to(ROOT).as_posix(),
        "generator_script_sha256": sha(Path(__file__).read_bytes()),
        "patch_path": str(patch_path), "patch_sha256": sha(patch_bytes),
        "upstream_files_modified": False,
        "model_math_or_network_reduction_modified": False,
        "cache_policy": "Immutable process-local tables; exact datetime row index; original filters preserved; clear nygrid_cached_table after changing any source file",
        "behavior_preserved": ["row order and duplicates", "MATLAB table metadata and categorical levels", "hour/day/month equality selection", "static weekly price selection", "original missing-value treatment", "all allocation, cost, reduction and solver arithmetic"],
        "known_upstream_behavior_preserved": "updateOpCond omits usemat when calling readOpCond, so CSV mode still uses MAT operation-condition files",
        "numeric_equivalence_validation": "pending root comparison against released sources",
        "files": records, "added_helpers": helper_records,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=BASE / "upstream")
    parser.add_argument("--destination", type=Path, default=BASE / "cached_upstream")
    parser.add_argument("--manifest", type=Path, default=ROOT / "output/nygrid_2019/cached_upstream_manifest.json")
    args = parser.parse_args()
    m = prepare(args.source, args.destination, args.manifest)
    print(json.dumps({"execution_path": m["execution_path"], "modified_code_files": sum(x["modified"] for x in m["files"]), "added_helpers": len(m["added_helpers"]), "manifest": str(args.manifest)}, indent=2))


if __name__ == "__main__":
    main()
