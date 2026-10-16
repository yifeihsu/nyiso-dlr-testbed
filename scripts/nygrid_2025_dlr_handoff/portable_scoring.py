"""Re-score the saved annual comparison without Git or changes to sealed evidence.

Requires the full research archive. The original numerical consumer is loaded
unchanged. Only its two historical Git-byte lookups are provided by an explicit
SHA-verified package identity provider. Every normal cohort, branch, allocation,
generation and metric check in that consumer still runs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import scipy

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "output/nygrid_2025_dlr_handoff/portable_scoring_contract.json"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def record(path):
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=digest(path), bytes=path.stat().st_size)


def main(output_dir):
    assert sys.version_info >= (3, 11), "Python3.11 or newer is required for hashlib.file_digest"
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    source = ROOT / contract["original_consumer"]["path"]
    assert digest(source) == contract["original_consumer"]["sha256"], "Sealed consumer differs from the pinned handoff version"
    pinned = {item["path"]: item for item in contract["historical_identity_bindings"]}
    for item in pinned.values():
        path = ROOT / item["path"]
        assert path.is_file() and digest(path) == item["sha256"], f"Package identity mismatch: {item['path']}"
    for item in contract["comparison_seed_files"]:
        path = ROOT / item["path"]
        assert path.is_file() and digest(path) == item["sha256"], f"Full research package is required; missing or changed: {item['path']}"
    output = (ROOT / output_dir).resolve()
    assert output.is_relative_to(ROOT), "Use a new output directory inside this extracted package, such as runs/comparison_2025"
    assert output != ROOT and not output.exists(), "Output directory must be new; sealed or previous results are never overwritten"
    # Restrict new outputs to a separate run namespace. This prevents accidental
    # mutation of any prior model, input, evidence, source or vendor directory.
    assert output.relative_to(ROOT).parts[0] == "runs", "Write recomputed outputs below a new runs/<name> directory"
    output.mkdir(parents=True)
    for item in contract["comparison_seed_files"]:
        if item["role"] == "comparison_contract": shutil.copyfile(ROOT / item["path"], output / "comparison_contract.json")
        elif item["role"] == "cohort": shutil.copyfile(ROOT / item["path"], output / "frozen_comparison_cohort.csv")

    spec = importlib.util.spec_from_file_location("handoff_sealed_comparison_consumer", source)
    assert spec is not None and spec.loader is not None
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    identity_calls = []

    def pinned_identity_lookup(command, cwd=None, **kwargs):
        assert isinstance(command, list) and len(command) == 3 and command[:2] == ["git", "show"], "Unrecognized external command requested by sealed consumer"
        assert not kwargs, "Unexpected Git-lookup options in sealed consumer"
        assert cwd is not None and Path(cwd).resolve() == ROOT
        git_ref, rel = command[2].split(":", 1)
        assert git_ref == contract["historical_identity_git_ref"] and rel in pinned, "Unrecognized historical identity request"
        path = ROOT / rel
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == pinned[rel]["sha256"]
        identity_calls.append(dict(path=rel, historical_git_ref=git_ref, provider="pinned_package_SHA256_bytes; Git not executed"))
        return data

    # This replaces the consumer's local provenance dependency, not the global
    # subprocess module or any numerical function. It never runs a Git process.
    consumer.subprocess = SimpleNamespace(check_output=pinned_identity_lookup)
    consumer.BASE = output
    arguments = SimpleNamespace(
        monthly=ROOT / contract["monthly_directory"],
        annual_receipt=ROOT / contract["annual_receipt"],
        variant="combined", loss_mode="boundary_consistent",
    )
    consumer.main(arguments)
    assert len(identity_calls) == 2 and {x["path"] for x in identity_calls} == set(pinned)
    scoring = json.loads((output / "combined/scoring_receipt.json").read_text())
    assert scoring["passed"] and scoring["revised_qualified_hours"] == 8170 and scoring["frozen_old_success_lost_hours"] == 324
    # Verify source bytes exactly, but compare recomputed floating-point outputs
    # numerically across supported NumPy/BLAS builds. Requiring serializer-byte
    # equality would incorrectly reject harmless last-bit platform differences.
    deterministic_checks = []
    for item in contract["reference_metric_outputs"]:
        reference = ROOT / item["path"]
        assert digest(reference) == item["sha256"], f"Changed frozen metric source: {reference.name}"
        produced = output / "combined" / Path(item["path"]).name
        expected = pd.read_csv(reference, float_precision="round_trip")
        actual = pd.read_csv(produced, float_precision="round_trip")
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False, check_exact=False, atol=1e-9, rtol=0)
        numeric = actual.select_dtypes(include=[np.number]).columns
        difference = np.abs(actual[numeric].to_numpy() - expected[numeric].to_numpy())
        finite = difference[np.isfinite(difference)]
        deterministic_checks.append({**record(produced), "reference_SHA256": item["sha256"],
                                     "byte_identical_on_this_host": digest(produced) == item["sha256"],
                                     "maximum_numeric_difference": float(finite.max(initial=0))})
    report = dict(passed=True, completed=True, created_utc=datetime.now(timezone.utc).isoformat(),
                  scope="Full saved-year comparison re-score with pinned package provenance; no PF or OPF rerun",
                  Git_process_executed=False, local_dotgit_exists=(ROOT / ".git").exists(),
                  git_executable_on_PATH=shutil.which("git") is not None,
                  tested_environment=dict(Python=sys.version.split()[0], NumPy=np.__version__, SciPy=scipy.__version__, pandas=pd.__version__),
                  untested_version_combinations_are_not_guaranteed=True,
                  original_consumer_bytes_unchanged=digest(source) == contract["original_consumer"]["sha256"],
                  historical_identity_checks=identity_calls,
                  qualification_and_numerical_checks_not_modified=True,
                  sealed_original_outputs_not_overwritten=True,
                  revised_qualified_hours=8170, paired_hours=8170, gained_hours=0, lost_hours=324,
                  reference_metric_CSV_values_reproduced=True,
                  reference_metric_numeric_tolerance=1e-9,
                  all_reference_CSV_bytes_identical_on_this_host=all(x["byte_identical_on_this_host"] for x in deterministic_checks),
                  source_code=record(Path(__file__)), contract=record(CONTRACT),
                  original_consumer=record(source), outputs=deterministic_checks,
                  scoring_receipt=record(output / "combined/scoring_receipt.json"))
    (output / "portable_scoring_receipt.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(portable_scoring_passed=True, output_directory=str(output), Git_process_executed=False, hours=8170)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, help="New package-relative output directory under runs/")
    args = parser.parse_args()
    main(args.output_dir)
