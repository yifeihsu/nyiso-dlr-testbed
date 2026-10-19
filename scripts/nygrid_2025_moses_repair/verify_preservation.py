"""Verify prior numeric evidence and unrelated work survive the new release."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_moses_repair'


def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    guard=json.loads((OUT/'baseline_guard.json').read_text())
    immutable=guard['immutable_prior_artifacts']
    unrelated=guard['unrelated_worktree_files']
    replaced={'output/nygrid_2025_latest_map/'+name for name in ['network_map.html','README.md','DELIVERY_MANIFEST.json']}
    maps=[r for r in guard['previous_map_and_sources'] if r['path'] not in replaced]
    for row in immutable+unrelated+maps:
        assert sha(ROOT/row['path'])==row['sha256'],row['path']
    archive=guard['recovery_archive'];assert sha(ROOT/archive['path'])==archive['sha256']
    receipt=dict(passed=True,checked_utc=datetime.now(timezone.utc).isoformat(),
                 immutable_prior_artifacts_checked=len(immutable),unrelated_worktree_files_checked=len(unrelated),
                 prior_map_files_and_sources_preserved=len(maps),
                 intended_current_map_entrypoint_replacements=sorted(replaced),
                 recovery_archive=archive,
                 previous_models_annual_evidence_and_handoff_archives_unchanged=True)
    (OUT/'preservation/final_preservation_review.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt))


if __name__=='__main__':main()
