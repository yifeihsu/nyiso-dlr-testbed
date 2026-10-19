"""Run the focused suite and preserve code fingerprints with its actual result."""
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from replay_refinement import DEFAULT, sha

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern="test_*.py")
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    output = DEFAULT / "validation"
    output.mkdir(parents=True, exist_ok=True)
    text = stream.getvalue()
    (output / "focused_tests.txt").write_text(text, encoding="utf-8", newline="\n")
    paths = sorted(HERE.glob("*.py")) + [DEFAULT / "network/network_cases.mat"]
    receipt = dict(passed=result.wasSuccessful(), tests_run=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
        files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in paths])
    (output / "focused_tests.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(text)
    sys.exit(0 if result.wasSuccessful() else 1)
