"""Compare independently compiled input files without relying on MAT headers."""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "output/nygrid_2025_inputs/model"


def compare(reference, rebuilt, report):
    left = loadmat(reference / "operating_inputs.mat", simplify_cells=True)
    right = loadmat(rebuilt / "operating_inputs.mat", simplify_cells=True)
    fields = []

    def check(a, b, key):
        if isinstance(a, dict):
            assert isinstance(b, dict) and set(a) == set(b), key
            for name in sorted(a):
                check(a[name], b[name], key + "." + name)
        else:
            x, y = np.asarray(a), np.asarray(b)
            assert x.shape == y.shape, key
            numeric = x.dtype.kind in "biufc"
            assert np.array_equal(x, y, equal_nan=True) if numeric else np.array_equal(x, y), key
            fields.append(dict(field=key, shape=list(x.shape), numeric=numeric, exact_match=True))

    keys = {k for k in left if not k.startswith("__")}
    assert keys == {k for k in right if not k.startswith("__")}
    for key in sorted(keys):
        check(left[key], right[key], key)
    csv_files = []
    for p in sorted(reference.iterdir()):
        if p.name.endswith((".csv", ".csv.gz")):
            other = rebuilt / p.name
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            assert other.is_file() and hashlib.sha256(other.read_bytes()).hexdigest() == digest, p.name
            csv_files.append(dict(file=p.name, byte_identical=True, sha256=digest))
    result = dict(passed=True, numerical_and_text_fields=len(fields),
                  numeric_fields=sum(r["numeric"] for r in fields), exact_match=True,
                  mat_header_policy="creation timestamps may differ; every saved data field compared",
                  fields=fields, csv_files=csv_files,
                  reference=str(reference.relative_to(ROOT)).replace("\\", "/"),
                  rebuilt=str(rebuilt.relative_to(ROOT)).replace("\\", "/"))
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"fields", "csv_files"}}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT)
    parser.add_argument("--rebuilt", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=ROOT / "output/nygrid_2025_inputs/validation/rebuild_comparison.json")
    args = parser.parse_args()
    compare(args.reference.resolve(), args.rebuilt.resolve(), args.report.resolve())
