"""Compile, inspect and package the standalone native Beamer deliverable."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, re, shutil, subprocess, tempfile, zipfile
import pdfplumber
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / 'output/pdf/nygrid_weekly_2026-10-15'
EVIDENCE = ROOT / 'output/nygrid_weekly_20261015/evidence'
RENDER = ROOT / 'output/nygrid_weekly_20261015/render'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_pdf(folder):
    for _ in range(2):
        run = subprocess.run(['pdflatex', '-no-shell-escape', '-interaction=nonstopmode',
                              '-halt-on-error', 'main.tex'], cwd=folder,
                             capture_output=True, text=True)
        if run.returncode:
            raise RuntimeError(run.stdout[-5000:])
    log = (folder / 'main.log').read_text(errors='replace')
    assert not re.search(r'Overfull|Underfull|^!', log, re.M), 'TeX layout/build warning'
    return log


def build():
    compile_pdf(PROJECT)
    pdf = PROJECT / 'main.pdf'
    reader = PdfReader(pdf)
    assert len(reader.pages) == 15
    geometry = []
    with pdfplumber.open(pdf) as doc:
        for i, page in enumerate(doc.pages, 1):
            assert abs(page.width/page.height-16/9) < 0.002
            outside = [c for c in page.chars if c['x0'] < -0.5 or
                       c['x1'] > page.width+0.5 or c['top'] < -0.5 or
                       c['bottom'] > page.height+0.5]
            assert not outside, (i, outside[:3])
            text = page.extract_text()
            assert re.search(rf'\b{i}\s*/\s*15\b', text), (i, 'footer missing')
            geometry.append(dict(slide=i,chars=len(page.chars),text_in_page=True))
    manifest = json.loads((PROJECT/'source_manifest.json').read_text())
    all_sources = list(manifest['source_files']) + list(manifest['data_files'])
    for name, key in [('content_review.json', 'source_hashes'),
                      ('visual_downstate_source_audit.json', 'source_files')]:
        review = json.loads((EVIDENCE/name).read_text())
        all_sources += review[key]
    checked = {}
    for source in all_sources:
        path = ROOT / source['path']
        assert sha(path) == source['sha256'], f'Source changed: {path}'
        checked[source['path']] = source['sha256']
    companion = PROJECT/'evidence'
    companion.mkdir(exist_ok=True)
    for path in EVIDENCE.glob('*'):
        if path.suffix in {'.md', '.json'}:
            shutil.copyfile(path, companion/path.name)
    snapshot = companion/'source_snapshots'
    snapshot.mkdir(exist_ok=True)
    for relative in [
        'output/nygrid_2025_moses_repair/annual/moses_repair_v1/comparison/public_interface_metrics.csv',
        'output/nygrid_2025_postrepair_diagnosis/ablations/factorial_metrics.csv',
        'output/nygrid_2025_postrepair_diagnosis/ablations/factorial_attribution.csv',
        'output/nygrid_2025_postrepair_diagnosis/generation/D_wind_source_energy_review.json',
        'output/nygrid_2025_moses_repair/annual/moses_repair_v1/validation/annual_physics_review.json',
    ]:
        source = ROOT/relative
        shutil.copyfile(source, snapshot/source.name)
    RENDER.mkdir(exist_ok=True)
    subprocess.run(['pdftoppm', '-jpeg', '-r', '130', str(pdf), str(RENDER/'slide')],
                   check=True, capture_output=True)
    result = dict(created_utc=datetime.now(timezone.utc).isoformat(),
                  passed_build_and_source_checks=True,
                  final_pdf_sha256=sha(pdf), main_tex_sha256=sha(PROJECT/'main.tex'),
                  slide_count=15, aspect_ratio='16:9', native_editable_charts=True,
                  native_editable_topology=True, shell_escape=False,
                  tex_overfull_underfull_count=0, geometry=geometry,
                  source_fingerprints_checked=len(checked),
                  source_hashes=checked, visual_review='pending',
                  scope='Presentation only; saved research results were not rerun')
    (PROJECT/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['geometry','source_hashes']}))


def package():
    result = json.loads((PROJECT/'validation.json').read_text())
    visual = json.loads((EVIDENCE/'final_visual_review.json').read_text())
    assert visual['passed'] and visual['slides_reviewed'] == list(range(1,16))
    assert result['final_pdf_sha256'] == visual['pdf_sha256'] == sha(PROJECT/'main.pdf')
    assert (PROJECT/'presenter_notes.md').is_file()
    content = json.loads((EVIDENCE/'content_review.json').read_text())
    assert content['status'] == 'passed_after_parent_wording_fixes'
    for p in EVIDENCE.glob('*.json'):
        shutil.copyfile(p, PROJECT/'evidence'/p.name)
    result['visual_review'] = 'passed_all_15_slides'
    result['independent_content_review'] = content['status']
    paths = [PROJECT/n for n in ['main.tex','main.pdf','README.md','presenter_notes.md','source_manifest.json']]
    for folder in ['data','figures','evidence']:
        paths.extend(p for p in (PROJECT/folder).rglob('*') if p.is_file())
    # Ensure the distributable builds outside the research repository.
    with tempfile.TemporaryDirectory(prefix='nygrid_weekly_standalone_') as temp:
        target = Path(temp)
        for path in paths:
            to = target/path.relative_to(PROJECT)
            to.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, to)
        compile_pdf(target)
        original = [p.extract_text() for p in PdfReader(PROJECT/'main.pdf').pages]
        rebuilt = [p.extract_text() for p in PdfReader(target/'main.pdf').pages]
        assert original == rebuilt, 'Standalone text mismatch'
    result['standalone_build'] = 'passed; 15 pages with identical extracted text'
    result['passed'] = True
    (PROJECT/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    paths.append(PROJECT/'validation.json')
    target = PROJECT/'nygrid_weekly_20261015_source.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(paths):
            z.write(path,path.relative_to(PROJECT).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(paths)
        for path in paths:
            assert hashlib.sha256(z.read(path.relative_to(PROJECT).as_posix())).hexdigest() == sha(path)
    print(json.dumps(dict(passed=True,zip=str(target),files=len(paths),
                         zip_sha256=sha(target),standalone_build=True)))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=['build','package'])
    args=parser.parse_args()
    {'build':build,'package':package}[args.phase]()
