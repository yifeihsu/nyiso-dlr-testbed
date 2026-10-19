"""Create file-copy manifests; this helper does not perform any bulk copy.

Project paths retain checkout-relative locations. MATPOWER is a code-only
BSD runtime subset; case data, tests, examples, docs, MOST and binaries are
excluded. Preserve each component's LICENSE and AUTHORS files unchanged.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/nygrid_2025_dlr_handoff/runtime_audit'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def entry(source, target, role):
    return dict(source_path=str(source.resolve()), target=target, bytes=source.stat().st_size,
        sha256=sha(source), role=role)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--matpower-root', type=Path, required=True)
    args = parser.parse_args(); mp = args.matpower_root.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    deps = pd.read_csv(OUT / 'static_function_dependencies.csv', keep_default_na=False)
    project_paths = {ROOT / p for p in deps.loc[deps.scope.eq('project'), 'relative_path']}
    project_paths.update(p for p in Path(__file__).parent.iterdir() if p.suffix in {'.m', '.py'})
    # License notice is required by the compact kernel's MATPOWER adaptation.
    project_paths.add(ROOT / 'scripts/nygrid_2025_compact_ac/THIRD_PARTY_NOTICES.md')
    project = [entry(p, p.relative_to(ROOT).as_posix(), 'portable_project_runtime_code') for p in sorted(project_paths)]
    project_receipt = dict(schema_version=1, created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Public default-dated PF/legacyDLR code closure plus handoff helpers; data closure is separate.',
        count=len(project), bytes=sum(e['bytes'] for e in project), entries=project,
        source_static_analysis='output/nygrid_2025_dlr_handoff/runtime_audit/static_function_dependency_receipt.json')
    (OUT / 'runtime_code_closure.json').write_text(json.dumps(project_receipt, indent=2) + '\n')
    vendor = []
    for component in ['', 'mips', 'mp-opt-model', 'mptest']:
        folder = mp / component / 'lib'
        for path in sorted(folder.rglob('*.m')):
            relative = path.relative_to(folder)
            if any(part.lower() in {'t', 'test', 'tests', 'examples', 'data'} for part in relative.parts[:-1]):
                continue
            vendor.append(entry(path, 'vendor/matpower8.1/' + path.relative_to(mp).as_posix(), 'BSD_3_clause_numerical_code'))
        for name in ['LICENSE', 'AUTHORS', 'CITATION']:
            path = mp / component / name
            if name in {'LICENSE', 'AUTHORS'}: assert path.is_file(), path
            if path.is_file(): vendor.append(entry(path, 'vendor/matpower8.1/' + path.relative_to(mp).as_posix(), 'unchanged_license_copyright_or_citation'))
    notice = OUT / 'MATPOWER_RUNTIME_SUBSET_NOTICE.txt'
    notice.write_text('This folder is a code-only runtime subset of MATPOWER 8.1, MIPS 1.5.2, MP-Opt-Model 5.0, and MP-Test 8.1.\n'
        'It is not the complete MATPOWER distribution. Case data, examples, tests, docs, MOST, and optional solver binaries are omitted.\n'
        'The unmodified source code and retained LICENSE/AUTHORS/CITATION files govern use and redistribution.\n'
        'MATPOWER case data are not covered by its code BSD license and are not included in this vendor subset.\n'
        'MATLAB and any MathWorks toolbox are external prerequisites and are not redistributed.\n'
        'Use setup_nygrid_2025_handoff for this project; the full MATPOWER installer/test suite is intentionally not shipped.\n'
        'Official sources: https://matpower.org/license/ and https://github.com/MATPOWER/matpower\n', encoding='utf-8')
    vendor.append(entry(notice, 'vendor/matpower8.1/RUNTIME_SUBSET_NOTICE.txt', 'runtime_subset_notice'))
    vendor_receipt = dict(schema_version=1, created_utc=datetime.now(timezone.utc).isoformat(), source_root=str(mp),
        target_root='vendor/matpower8.1', MATPOWER_version='8.1', MIPS_version='1.5.2', MP_Opt_Model_version='5.0', MP_Test_version='8.1',
        license='BSD-3-Clause code; component licenses and copyright notices retained',
        original_notice_conditions_preserved=True, MATPOWER_case_data_included=False, MATLAB_included=False,
        external_optional_solver_binaries_included=False, count=len(vendor), bytes=sum(e['bytes'] for e in vendor), entries=vendor)
    (OUT / 'vendor_code_closure.json').write_text(json.dumps(vendor_receipt, indent=2) + '\n')
    print(json.dumps(dict(project_files=len(project), project_bytes=project_receipt['bytes'], vendor_files=len(vendor), vendor_bytes=vendor_receipt['bytes'])))


if __name__ == '__main__': main()
