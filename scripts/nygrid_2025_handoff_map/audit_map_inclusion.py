"""Independently review the map-inclusive ZIP without rerunning model/UI tests."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import urlsplit, unquote
import hashlib
import json
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_handoff_map"
RELEASE = ROOT / "deliverables/nygrid_2025_latest_model_20261013"
BASE = RELEASE / "nygrid_latest_model_20261013.zip"
NEW = RELEASE / "nygrid_latest_model_with_map_20261013.zip"
MAP = ROOT / "output/nygrid_2025_latest_map/network_map.html"
BASE_SHA = "b349bfc5587162fd8d945dd0e81485ed6748c205d432f4ce93e2ad42e2732f6a"
NEW_SHA = "7e6d13ea54f49aa141bd1d6bcfc77ef4e1ba64cbe2542c4675a3e9dd1cb16810"
MAP_SHA = "077d297471ff17655f01bd9a163466c522817dae7df16cc90a95453e1f01fa51"
ADDED = {"map/network_map.html", "map/README.md", "verification/MAP_PROVENANCE.json"}


def digest(stream):
    return hashlib.file_digest(stream, "sha256").hexdigest()


def sha(path):
    with path.open("rb") as stream: return digest(stream)


def inventory(archive):
    items = [i for i in archive.infolist() if not i.is_dir()]
    names = [i.filename for i in items]
    assert len(names) == len(set(n.casefold() for n in names)), "Duplicate or case-colliding member"
    manifests = [n for n in names if n.endswith("/PACKAGE_MANIFEST.json")]
    assert len(manifests) == 1
    prefix = manifests[0][:-len("PACKAGE_MANIFEST.json")]
    for item in items:
        p = PurePosixPath(item.filename)
        assert not p.is_absolute() and ".." not in p.parts and ":" not in item.filename and "\\" not in item.filename
        assert item.filename.startswith(prefix) and not stat.S_ISLNK(item.external_attr >> 16)
    manifest = json.loads(archive.read(manifests[0]))
    assert set(names) == {prefix + p for p in manifest["files"]} | {prefix + "PACKAGE_MANIFEST.json", prefix + "SHA256SUMS.txt"}
    hashes = {}
    for item in items:
        relative = item.filename[len(prefix):]
        with archive.open(item) as stream: hashes[relative] = digest(stream)
        if relative in manifest["files"]:
            expected = manifest["files"][relative]
            assert item.file_size == expected["bytes"] and hashes[relative] == expected["sha256"], relative
    return prefix, manifest, hashes, items


def main():
    assert sha(BASE) == BASE_SHA and sha(NEW) == NEW_SHA and sha(MAP) == MAP_SHA
    temp_parent = Path(tempfile.mkdtemp(prefix="nygrid_handoff_map_")).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    assert temp_parent.is_relative_to(temp_root) and temp_parent != temp_root and not temp_parent.is_relative_to(ROOT.resolve())
    extracted = temp_parent / "package"; assert not extracted.exists(); extracted.mkdir()
    print(json.dumps({"phase": "inventory_and_extract", "temporary_root": str(extracted)}), flush=True)
    with zipfile.ZipFile(BASE) as old, zipfile.ZipFile(NEW) as new:
        op, om, oh, oi = inventory(old); nprefix, nm, nh, ni = inventory(new)
        assert len(om["files"]) == 666 and len(nm["files"]) == 669 and len(ni) == 671
        assert set(nm["files"]) - set(om["files"]) == ADDED and not set(om["files"]) - set(nm["files"])
        changed = sorted(p for p in om["files"] if oh[p] != nh[p]); assert changed == ["START_HERE.md"]
        unchanged = sorted(p for p in om["files"] if oh[p] == nh[p]); assert len(unchanged) == 665
        old_start = old.read(op + "START_HERE.md").decode("utf-8").splitlines(keepends=True)
        new_start = new.read(nprefix + "START_HERE.md").decode("utf-8").splitlines(keepends=True)
        changes = [tag for tag, *_ in SequenceMatcher(a=old_start, b=new_start).get_opcodes() if tag != "equal"]
        assert changes == ["insert"], "START_HERE change must only insert the map section"
        assert new.read(nprefix + "map/network_map.html") == MAP.read_bytes()
        provenance = json.loads(new.read(nprefix + "verification/MAP_PROVENANCE.json"))
        assert provenance["HTML"]["package_path"] == "map/network_map.html" and provenance["HTML"]["sha256"] == MAP_SHA
        assert provenance["HTML"]["bytes"] == MAP.stat().st_size
        map_sources = ROOT / "output/nygrid_2025_latest_map"
        assert provenance["source_map_delivery_manifest_sha256"] == sha(map_sources / "DELIVERY_MANIFEST.json")
        for name, expected in provenance["source_receipts"].items(): assert sha(map_sources / name) == expected
        for item in ni:
            relative = PurePosixPath(item.filename[len(nprefix):])
            destination = extracted.joinpath(*relative.parts)
            assert destination.resolve().is_relative_to(extracted)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with new.open(item) as src, destination.open("xb") as dst: shutil.copyfileobj(src, dst)
        assert all(sha(extracted / name) == value for name, value in nh.items())
    git_ancestors = [str(p) for p in [extracted, *extracted.parents] if (p / ".git").exists()]
    assert not git_ancestors
    link_checks = []
    for name in ["START_HERE.md", "map/README.md"]:
        file = extracted / name
        for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", file.read_text(encoding="utf-8")):
            url = urlsplit(target.strip("<>"))
            assert not url.scheme and not url.netloc, "New documentation links must be package-relative"
            path = (file.parent / unquote(url.path)).resolve()
            assert path.is_relative_to(extracted) and path.is_file()
            link_checks.append({"document": name, "relative_link": target, "resolved_package_path": path.relative_to(extracted).as_posix(), "passed": True})
    assert len(link_checks) == 3
    print(json.dumps({"phase": "included_standalone_verifier", "unchanged_base_files": len(unchanged), "portable_links": len(link_checks)}), flush=True)
    command = [sys.executable, str(extracted / "verify_package.py"), "--root", str(extracted)]
    completed = subprocess.run(command, cwd=extracted, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    verified = json.loads(completed.stdout); assert verified["passed"] and verified["files"] == 669 and verified["bytes"] == 130345898
    assert sha(BASE) == BASE_SHA and sha(NEW) == NEW_SHA and sha(MAP) == MAP_SHA
    assert all(sha(extracted / name) == value for name, value in nh.items())
    receipt = {"passed": True, "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Bounded actual-ZIP map inclusion, unchanged base payload, relative links, clean extraction and included standard-library verifier",
        "archive_path": NEW.relative_to(ROOT).as_posix(), "archive_sha256": NEW_SHA, "archive_bytes": NEW.stat().st_size,
        "base_archive_sha256": BASE_SHA, "base_archive_preserved": True,
        "archive_member_count": len(ni), "payload_file_count": len(nm["files"]), "payload_bytes": verified["bytes"],
        "unchanged_base_payload_file_count": len(unchanged), "modified_base_files": changed, "added_files": sorted(ADDED),
        "START_HERE_only_inserts_map_section": True, "original_runtime_commands_preserved": True,
        "map_HTML_sha256": MAP_SHA, "map_HTML_bytes_identical_to_approved_source": True,
        "map_source_delivery_and_validation_hashes_match": True, "relative_link_checks": link_checks,
        "fresh_OS_temporary_extraction": {"root": str(extracted), "outside_research_checkout": True, "git_ancestors": git_ancestors,
            "preexisting_directory_overwritten": False, "all671_member_hashes_verified": True},
        "included_standalone_verifier": {"command": command, "working_directory": str(extracted), "exit_code": completed.returncode, "result": verified},
        "all_payload_and_manifest_bytes_unchanged_after_verifier": True,
        "MATLAB_PF_OPF_or_browser_rerun": False, "validation_inheritance_basis": "All runtime/model payload bytes and approved map HTML are unchanged",
        "old_archives_manifests_and_map_sources_modified": False,
        "source_new_build_receipt_sha256": sha(OUT / "build_receipt.json"),
        "audit_script_sha256": sha(Path(__file__))}
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "independent_package_review.json"
    output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "archive_sha256": NEW_SHA, "base_unchanged": len(unchanged),
        "payload_files": len(nm["files"]), "links": len(link_checks), "review_sha256": sha(output)}))


if __name__ == "__main__": main()
