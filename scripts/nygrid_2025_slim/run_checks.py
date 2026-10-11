"""Run preservation and adversarial tests against the current slim artifacts."""
import io
import json
from pathlib import Path
import sys
import unittest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from replay_slim import ROOT,OUT,sha

if __name__=="__main__":
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.discover(str(HERE),pattern="test_*.py"))
    folder=OUT/"validation";folder.mkdir(parents=True,exist_ok=True)
    (folder/"focused_tests.txt").write_text(stream.getvalue(),encoding="utf-8",newline="\n")
    files=sorted(HERE.glob("*.py"))+[OUT/"network/network_cases.mat"]
    receipt=dict(passed=result.wasSuccessful(),tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in files])
    (folder/"focused_tests.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(stream.getvalue());sys.exit(0 if result.wasSuccessful() else 1)
