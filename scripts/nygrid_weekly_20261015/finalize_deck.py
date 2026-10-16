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
SLIDE_COUNT = 16


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path,value):
    staged=path.with_name('.'+path.name+'.rebuild')
    staged.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    staged.replace(path)


def copy_file(source,target):
    if target.exists() and sha(source)==sha(target):
        return
    staged=target.with_name('.'+target.name+'.rebuild')
    shutil.copyfile(source,staged)
    staged.replace(target)


def compile_pdf(folder, output_folder=None):
    destination=output_folder or folder
    for _ in range(2):
        run = subprocess.run(['pdflatex', '-no-shell-escape', '-interaction=nonstopmode',
                              '-halt-on-error', f'-output-directory={destination}',
                              'main.tex'], cwd=folder,
                             capture_output=True, text=True)
        if run.returncode:
            raise RuntimeError(run.stdout[-5000:])
    log = (destination / 'main.log').read_text(errors='replace')
    problems=re.findall(r'^.*(?:Overfull|Underfull|^!).*$',log,re.M)
    assert not problems, 'TeX layout/build warning: '+'; '.join(problems)
    return log


def build():
    pdf = PROJECT / 'main.pdf'
    # Finish both passes privately before replacing a PDF open in the app.
    with tempfile.TemporaryDirectory(prefix='nygrid_weekly_compile_') as temp:
        destination=Path(temp)
        compile_pdf(PROJECT,destination)
        staged=PROJECT/'.main.rebuild.pdf'
        shutil.copyfile(destination/'main.pdf',staged)
        staged.replace(pdf)
        copy_file(destination/'main.log',PROJECT/'main.log')
    reader = PdfReader(pdf)
    assert len(reader.pages) == SLIDE_COUNT
    geometry = []
    with pdfplumber.open(pdf) as doc:
        for i, page in enumerate(doc.pages, 1):
            assert abs(page.width/page.height-16/9) < 0.002
            outside = [c for c in page.chars if c['x0'] < -0.5 or
                       c['x1'] > page.width+0.5 or c['top'] < -0.5 or
                       c['bottom'] > page.height+0.5]
            assert not outside, (i, outside[:3])
            text = page.extract_text()
            assert re.search(rf'\b{i}\s*/\s*{SLIDE_COUNT}\b', text), (i, 'footer missing')
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
        if path.suffix in {'.md', '.json', '.csv'}:
            copy_file(path, companion/path.name)
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
        copy_file(source, snapshot/source.name)
    RENDER.mkdir(exist_ok=True)
    subprocess.run(['pdftoppm', '-jpeg', '-r', '130', str(pdf), str(RENDER/'slide')],
                   check=True, capture_output=True)
    result = dict(created_utc=datetime.now(timezone.utc).isoformat(),
                  passed_build_and_source_checks=True,
                  final_pdf_sha256=sha(pdf), main_tex_sha256=sha(PROJECT/'main.tex'),
                  slide_count=SLIDE_COUNT, aspect_ratio='16:9', native_editable_charts=True,
                  native_editable_topology=True, shell_escape=False,
                  tex_overfull_underfull_count=0, geometry=geometry,
                  source_fingerprints_checked=len(checked),
                  source_hashes=checked, visual_review='pending',
                  scope='Presentation only; saved research results were not rerun')
    write_json(PROJECT/'validation.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['geometry','source_hashes']}))


def package():
    result = json.loads((PROJECT/'validation.json').read_text())
    visual = json.loads((EVIDENCE/'final_visual_review.json').read_text())
    assert visual['passed'] and visual['slides_reviewed'] == list(range(1,SLIDE_COUNT+1))
    assert result['final_pdf_sha256'] == visual['pdf_sha256'] == sha(PROJECT/'main.pdf')
    assert (PROJECT/'presenter_notes.md').is_file()
    content = json.loads((EVIDENCE/'content_review.json').read_text())
    assert content['status'] == 'passed_after_parent_wording_fixes'
    comparison=json.loads((EVIDENCE/'2019_comparison_slide_review.json').read_text())
    assert comparison['passed'], 'New comparison slide has unresolved findings'
    for p in EVIDENCE.glob('*.json'):
        copy_file(p, PROJECT/'evidence'/p.name)
    result['visual_review'] = f'passed_all_{SLIDE_COUNT}_slides'
    result['independent_content_review'] = content['status']
    result['independent_comparison_review'] = 'passed; all seven interfaces and cross-year scope'
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
    result['standalone_build'] = f'passed; {SLIDE_COUNT} pages with identical extracted text'
    result['passed'] = True
    write_json(PROJECT/'validation.json',result)
    paths.append(PROJECT/'validation.json')
    target = PROJECT/'nygrid_weekly_20261015_source.zip'
    staged_zip=target.with_name('.'+target.name+'.rebuild')
    with zipfile.ZipFile(staged_zip,'w',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(paths):
            z.write(path,path.relative_to(PROJECT).as_posix())
    staged_zip.replace(target)
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
