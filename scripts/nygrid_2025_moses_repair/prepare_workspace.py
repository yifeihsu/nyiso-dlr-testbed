"""Preserve existing inputs and prepare an isolated current-model delivery."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_moses_repair'
SRC = Path(__file__).parent
OLD = ROOT / 'scripts/nygrid_2025_physical_repair/delivery'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(path):
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=sha(path))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    guard_path = OUT / 'baseline_guard.json'
    if not guard_path.exists():
        old = json.loads((ROOT / 'output/nygrid_2025_moses_source_diagnosis/source_guard.json').read_text())
        paths = [ROOT / row['path'] for row in old['critical_sources']]
        pointer = json.loads((ROOT / 'deliverables/CURRENT_NYGRID_MODEL.json').read_text())
        paths += [ROOT / row['path'] for row in pointer.values() if isinstance(row, dict) and 'path' in row]
        paths += [ROOT / 'deliverables/CURRENT_NYGRID_MODEL.json']
        edited = subprocess.check_output(['git', 'diff', '--name-only'], cwd=ROOT, text=True).splitlines()
        unrelated = [ROOT / name for name in edited if 'node_modules' not in name and (ROOT / name).is_file()]
        saved = OUT / 'preservation'; saved.mkdir(exist_ok=True)
        current = list((ROOT / 'output/nygrid_2025_latest_map').rglob('*'))
        current += list((ROOT / 'scripts/nygrid_2025_latest_map').rglob('*'))
        current = [p for p in current if p.is_file() and '__pycache__' not in p.parts]
        with zipfile.ZipFile(saved / 'previous_map_and_sources.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for p in current:
                archive.write(p, p.relative_to(ROOT).as_posix())
        guard = dict(created_utc=datetime.now(timezone.utc).isoformat(),
                     baseline_HEAD=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                     branch=subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
                     immutable_prior_artifacts=[record(p) for p in sorted(set(paths)) if p.name != 'CURRENT_NYGRID_MODEL.json'],
                     prior_current_pointer=record(ROOT / 'deliverables/CURRENT_NYGRID_MODEL.json'),
                     unrelated_worktree_files=[record(p) for p in unrelated],
                     previous_map_and_sources=[record(p) for p in current],
                     recovery_archive=record(saved / 'previous_map_and_sources.zip'))
        guard_path.write_text(json.dumps(guard, indent=2) + '\n', encoding='utf-8')
    guard = json.loads(guard_path.read_text())
    for row in guard['immutable_prior_artifacts']:
        assert sha(ROOT / row['path']) == row['sha256'], row['path']
    copied = []
    for folder, suffixes in [('runtime', {'.m'}), ('examples', {'.m'}), ('map', {'.py', '.js', '.cjs', '.css', '.html'})]:
        for p in sorted((OLD / folder).rglob('*')):
            if not p.is_file() or p.suffix not in suffixes or '__pycache__' in p.parts:
                continue
            relative = p.relative_to(OLD)
            target = SRC / 'delivery' / relative
            raw = p.read_bytes()
            if folder == 'runtime' and p.name == 'nylatest_paths.m':
                raw = raw.replace(b'nygrid_2025_physical_repair', b'nygrid_2025_moses_repair')
            if folder == 'map':
                raw = raw.replace(b'nygrid_2025_physical_repair', b'nygrid_2025_moses_repair')
                raw = raw.replace(b'physical_repair_v1', b'moses_repair_v1')
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(raw)
            copied.append(dict(source=record(p), target=record(target)))
    mask = ROOT / 'output/nygrid_2025_physical_repair/delivery/map/ny_display_mask.json'
    target = OUT / 'delivery/map/ny_display_mask.json'; target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(mask.read_bytes())
    proof = OUT / 'delivery/source_preparation_receipt.json'
    if not proof.exists():
        proof.write_text(json.dumps(dict(passed=True, entries=copied, preservation_sha256=sha(guard_path)), indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, immutable_inputs=len(guard['immutable_prior_artifacts']), prepared_sources=len(copied))))


if __name__ == '__main__':
    main()
