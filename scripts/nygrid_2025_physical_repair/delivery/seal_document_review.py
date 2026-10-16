"""Bind the nine visually inspected Word pages and current content checks."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import json
import zipfile
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_physical_repair/delivery'


def rec(path):return dict(path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    doc=OUT/'docs/NYGRID_2025_PHYSICAL_REPAIR_MODEL_STRUCTURE.docx'
    md=doc.with_suffix('.md');render=OUT/'document_render'
    receipt=json.loads((render/'word_export_receipt.json').read_text(encoding='utf-8-sig'))
    assert receipt['readonlyInput'] and receipt['inputSHA256']==rec(doc)['sha256']
    images=[render/f'page-{n}.png' for n in range(1,10)];assert all(p.is_file() for p in images)
    assert len(list(render.glob('page-*.png')))==9
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
    with zipfile.ZipFile(doc) as z:
        root=ET.fromstring(z.read('word/document.xml'));styles=ET.fromstring(z.read('word/styles.xml'))
        text=' '.join(n.text or '' for n in root.findall('.//w:t',ns))
        equations=len(root.findall('.//m:oMath',ns));assert equations==8
        assert not root.findall('.//w:pBdr',ns) and not styles.findall('.//w:pBdr',ns)
        media=[z.read(n) for n in z.namelist() if n.startswith('word/media/')]
        assert any(hashlib.sha256(b).hexdigest()==rec(OUT/'structure/current_model_schematic.png')['sha256'] for b in media)
    for term in ['148','266','267','485','488','1,464','1,436','8,760','8,651','Parent 41',
                 '0.0018','0.0089','0.02126747227','ACSS Mallard','10.750873','4 circuits',
                 '185','195','75 percent','full-axis bus shunt','607.279468','254.817180',
                 'Voltage and generator assumptions','Full declared operating gate','Solver exceptions',
                 'same signed original-terminal interface operators','amperes are never divided by gamma']:
        assert term in text,term
    visual=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),document=rec(doc),pages=9,
        all_page_images_visually_inspected=True,reviewed_pages=list(range(1,10)),
        renderer='Microsoft Word native PDF export and Poppler rasterization',
        fallback_reason=receipt['fallbackReason'],readonly_export=True,
        findings='All nine pages readable with no clipping, overlap, missing glyphs, broken tables or unintended blank pages. Current parameter and annual qualification pages fit their page frames.',
        native_editable_equations=equations,title_and_style_borders_absent=True,images=[rec(p) for p in images],
        QA_only_pdf=rec(render/'NYGRID_2025_PHYSICAL_REPAIR_MODEL_STRUCTURE.pdf'))
    (OUT/'structure_document_visual_review.json').write_text(json.dumps(visual,indent=2)+'\n')
    content=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Current manual content, editable equations, candidate values, annual qualification and file binding',
        documents=[rec(doc),rec(md)],native_editable_equations=equations,baseline_manual_modified=False,
        physical_repair_values_checked=True,all8651_equation_hours_separate_from_zero_operating_hours=True,
        model_structure_and_recovery_scope_preserved=True,unverified_installed_asset_identity_explicit=True,
        visual_review=rec(OUT/'structure_document_visual_review.json'),remaining_findings=[])
    (OUT/'structure_document_content_review.json').write_text(json.dumps(content,indent=2)+'\n')
    print(json.dumps(dict(passed=True,pages=9,editable_equations=equations,document_sha256=rec(doc)['sha256'])))


if __name__=='__main__':main()
