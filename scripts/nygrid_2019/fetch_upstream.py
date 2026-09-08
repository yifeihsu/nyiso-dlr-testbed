"""Fetch the pinned paper implementation and prepared 2019 data, verifying Git blobs."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
PIN = "47698b6c7823ae7b1bc6935e5601d5b64b8f918e"
BASE = ROOT / "tmp/nygrid_2019_reproduction/upstream"
OUT = ROOT / "output/nygrid_2019"

def selected(path):
    return (not path.startswith("Data/") or "2019" in path or
            not any(str(year) in path for year in range(2016, 2022)))

def fetch(entry):
    path = entry["path"]
    url = f"https://raw.githubusercontent.com/AndersonEnergyLab-Cornell/NYgrid/{PIN}/{path}"
    target = BASE / path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        data = target.read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=90) as response:
            data = response.read()
    git_sha = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    if git_sha != entry["sha"]:
        raise ValueError(f"Git blob mismatch: {path}")
    if not target.exists():
        target.write_bytes(data)
    return {"path": path, "bytes": len(data), "git_blob_sha1": git_sha,
            "sha256": hashlib.sha256(data).hexdigest(), "url": url}

if __name__ == "__main__":
    manifest = OUT / "upstream_manifest.json"
    if manifest.exists():
        pinned = json.loads(manifest.read_text())
        assert pinned["commit"] == PIN
        entries = [{"path": e["path"], "sha": e["git_blob_sha1"]} for e in pinned["files"]]
    else:
        url = f"https://api.github.com/repos/AndersonEnergyLab-Cornell/NYgrid/git/trees/{PIN}?recursive=1"
        with urllib.request.urlopen(url, timeout=90) as response:
            tree = json.load(response)
        assert tree["sha"] == PIN and not tree.get("truncated", False)
        entries = [e for e in tree["tree"] if e["type"] == "blob" and selected(e["path"])]
    with ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(fetch, entries))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "upstream_manifest.json").write_text(json.dumps(
        {"commit": PIN, "files": records}, indent=2) + "\n")
    print(f"Verified {len(records)} upstream files, {sum(r['bytes'] for r in records):,} bytes", flush=True)
