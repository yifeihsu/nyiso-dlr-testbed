"""Compare every saved dispatch field across independent builds."""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_dispatch"
FILES = ["dispatch.mat", "dispatch_bounds.mat", "dispatch_priors.mat", "dispatch_network.mat"]


def read(folder):
    data = {}
    for name in FILES:
        part = loadmat(folder / name, simplify_cells=True)
        for key, value in part.items():
            if key.startswith("__"):
                continue
            if key in data:
                assert np.array_equal(data[key], value), key
            else:
                data[key] = value
    return data


def compare(reference, rebuilt, output):
    left, right = read(reference), read(rebuilt)
    records = []
    def check(a, b, key):
        if isinstance(a, dict):
            assert isinstance(b, dict) and set(a) == set(b), key
            for child in sorted(a):
                check(a[child], b[child], key + "." + child)
        else:
            x, y = np.asarray(a), np.asarray(b)
            numeric = x.dtype.kind in "biufc"
            assert x.shape == y.shape, key
            assert np.array_equal(x, y, equal_nan=True) if numeric else np.array_equal(x, y), key
            records.append(dict(field=key, shape=list(x.shape), numeric=numeric, exact_match=True))
    assert set(left) == set(right)
    for key in sorted(left):
        check(left[key], right[key], key)
    csv_records = []
    for name in ["model_generator_register.csv", "hour_status.csv", "fuel_adjustments.csv", "contract.json"]:
        digest = hashlib.sha256((reference / name).read_bytes()).hexdigest()
        assert digest == hashlib.sha256((rebuilt / name).read_bytes()).hexdigest(), name
        csv_records.append(dict(file=name, sha256=digest, byte_identical=True))
    result = dict(passed=True, all_saved_fields_exact=True, fields=len(records),
        numeric_fields=sum(r["numeric"] for r in records), compared_fields=records, text_files=csv_records,
        reference=reference.relative_to(ROOT).as_posix(), rebuilt=rebuilt.relative_to(ROOT).as_posix(),
        excluded_metadata="MAT creation timestamp headers; all saved scientific fields compared")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ["compared_fields", "text_files"]}, indent=2))


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference", type=Path, default=OUT / "dispatch")
    p.add_argument("--rebuilt", type=Path, required=True)
    p.add_argument("--output", type=Path, default=OUT / "validation/rebuild_comparison.json")
    a=p.parse_args()
    compare(a.reference.resolve(), a.rebuilt.resolve(), a.output.resolve())
