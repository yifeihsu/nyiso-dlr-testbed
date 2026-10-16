"""Run focused source/control fixtures and save a reproducible current receipt."""
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "output/nygrid_2025_par_controls/validation"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    receipt_path = OUT / "source_gate_validation.json"
    initial = OUT / "source_gate_initial_review.json"
    if receipt_path.exists() and not initial.exists():
        initial.write_bytes(receipt_path.read_bytes())
    paths = [HERE / name for name in ["replay_controls.py", "controlled_equivalent.py",
             "build_control_inputs.py", "test_control_sources.py", "run_checks.py"]]
    paths += [ROOT / "output/nygrid_2025_par_controls" / name for name in
              ["controls/inputs.npz", "controls/inputs.mat", "controls/input_receipt.json",
               "sources/direction/direction_verification_receipt.json", "sources/limits/limits.json"]]
    paths += [ROOT / "System Matpower Format/npcc_nygrid_2025_par_controlled_dc.m"]
    before = {p: sha(p) for p in paths}
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern="test_*.py")
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    unchanged = all(sha(p) == value for p, value in before.items())
    record = dict(status="passed" if result.wasSuccessful() and unchanged else "failed",
        checked_utc=datetime.now(timezone.utc).isoformat(), tests_run=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), all_inputs_unchanged_during_tests=unchanged,
        frozen_source_or_replay_files_modified=not unchanged,
        physical_claim_scope="verified direction and necessary nominal P screen; no full hardware tap/PQ qualification",
        inputs=[dict(path=p.relative_to(ROOT).as_posix(), sha256=h) for p, h in before.items()],
        test_output=stream.getvalue())
    receipt_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(stream.getvalue())
    if not result.wasSuccessful() or not unchanged:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
