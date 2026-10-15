"""Copy the preserved delivery sources into an isolated repair namespace.

This is preparation only. It never exports a repaired model, runs PF, or seals
a package. Re-running is allowed only while every prepared target is identical.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
SRC = Path(__file__).parent
OUT = ROOT / 'output/nygrid_2025_physical_repair/delivery'
OLD = ROOT / 'scripts/nygrid_2025_latest_handoff'
MAP = ROOT / 'scripts/nygrid_2025_latest_map'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    preservation = json.loads((OUT / 'preservation/dirty_map_snapshot.json').read_text())
    rows = []

    def copy(source, target, change=None):
        raw = source.read_bytes()
        if change:
            content = change(raw.decode('utf-8-sig')).replace('\r\n', '\n').encode('utf-8')
        else:
            content = raw
        if target.exists():
            assert target.read_bytes() == content, f'Prepared target changed: {target}'
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        rows.append(dict(source=source.relative_to(ROOT).as_posix(), source_sha256=sha(source),
                         target=target.relative_to(ROOT).as_posix(), target_sha256=sha(target),
                         mechanical_adaptation=change is not None))

    def paths(text):
        return text.replace('/scripts/nygrid_2025_latest_handoff/runtime', '/scripts/nygrid_2025_physical_repair/delivery/runtime').replace(
            'root=fileparts(fileparts(fileparts(runtime)));', 'root=fileparts(fileparts(fileparts(fileparts(runtime))));').replace(
            "'output','nygrid_2025_latest_handoff','model'", "'output','nygrid_2025_physical_repair','model'")

    for path in sorted((OLD / 'runtime').rglob('*.m')):
        copy(path, SRC / 'runtime' / path.relative_to(OLD / 'runtime'), paths if path.name == 'nylatest_paths.m' else None)
    for path in sorted((OLD / 'examples').glob('*.m')):
        copy(path, SRC / 'examples' / path.name)
    copy(OLD / 'verify_package.py', SRC / 'verify_package.py')
    for name in ['map_template.html', 'map.css', 'map.js', 'audit_ui_flow_math.js', 'test_interactive_map.cjs']:
        copy(MAP / name, SRC / 'map' / name)
    copy(ROOT / 'output/nygrid_2025_latest_map/ny_display_mask.json', OUT / 'map/ny_display_mask.json')
    receipt = dict(passed=True, created_utc=datetime.now(timezone.utc).isoformat(),
                   scope='Isolated source preparation; no repaired data or annual claims',
                   preservation_receipt_sha256=sha(OUT / 'preservation/dirty_map_snapshot.json'), entries=rows)
    (OUT / 'source_preparation_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(passed=True, prepared_files=len(rows))))


if __name__ == '__main__':
    main()
