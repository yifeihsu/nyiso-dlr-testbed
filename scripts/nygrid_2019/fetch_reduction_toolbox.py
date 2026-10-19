"""Restore the historically pinned reduction toolbox from its evidence manifest."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import urllib.request
import zipfile
import io

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "tmp/nygrid_2019_reproduction/reduction_toolbox"
MANIFEST = ROOT / "output/nygrid_2019/toolbox_manifest.json"

def download(url):
    with urllib.request.urlopen(url, timeout=90) as response:
        return response.read()

def write_verified(path, data, expected):
    assert hashlib.sha256(data).hexdigest() == expected, f"Hash mismatch: {path}"
    if path.exists():
        assert path.read_bytes() == data, f"Existing dependency changed: {path}"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

def main():
    m = json.loads(MANIFEST.read_text())
    pin = m["selected_commit"]
    def fetch_file(record):
        relative = record["relative_path"]
        target = BASE / "mirror" / relative
        url = f"https://raw.githubusercontent.com/MATPOWER/mx-reduction/{pin}/{relative}"
        data = target.read_bytes() if target.exists() else download(url)
        write_verified(target, data, record["sha256"])
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(fetch_file, m["mirror"]["files"]))
    archive = m["official_archive"]
    target = BASE / "official.zip"
    data = target.read_bytes() if target.exists() else download(archive["url"])
    write_verified(target, data, archive["sha256"])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for record in archive["files"]:
            relative = record["relative_path"]
            payload = z.read("NetworkReduction2/" + relative)
            write_verified(BASE / "official/NetworkReduction2" / relative, payload, record["sha256"])
        for record in m["official_compatibility"]["files"]:
            relative = record["relative_path"]
            original = z.read("NetworkReduction2/" + relative)
            payload = original.replace(b"interp1q(", b"interp1(")
            write_verified(BASE / "official_compatibility" / relative, payload, record["sha256"])
    print(f"Verified pinned toolbox {pin}; original and compatibility copies restored")

if __name__ == "__main__":
    main()
