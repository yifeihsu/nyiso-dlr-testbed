"""Restore the pinned raw-load audit cache without downloading or overwriting.

The public NYISO ZIPs and their original receipts are preserved with the
research evidence, so an offline replay does not depend on archive availability.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "output/nygrid_2019_diagnostics/raw_archives"
CACHE = ROOT / "tmp/nygrid_2019_diagnostics/raw_load"


def restore() -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    for month in range(1, 13):
        name = f"2019{month:02d}01palIntegrated_csv.zip"
        receipt_name = name + ".provenance.json"
        receipt = json.loads((FROZEN / receipt_name).read_text())
        content = (FROZEN / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == receipt["sha256"], name
        assert receipt["source_url"] == f"https://mis.nyiso.com/public/csv/palIntegrated/{name}"
        for filename, data in [(name, content), (receipt_name, (FROZEN / receipt_name).read_bytes())]:
            target = CACHE / filename
            if target.exists():
                if filename == receipt_name:
                    existing = json.loads(target.read_text())
                    assert existing["sha256"] == receipt["sha256"] and existing["source_url"] == receipt["source_url"]
                else:
                    assert target.read_bytes() == data, f"Refusing to replace different cached archive {target}"
            else:
                target.write_bytes(data)
    return 12


if __name__ == "__main__":
    print(f"Verified or restored {restore()} pinned NYISO monthly archives without network access")
