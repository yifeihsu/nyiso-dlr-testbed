"""Record structural checks after all rendered pages were visually inspected."""
from pathlib import Path
import hashlib
import json
import zipfile
from lxml import etree
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_latest_handoff'
DOC=ROOT/'NYGRID_2025_LATEST_MODEL_STRUCTURE.docx'
RENDER=OUT/'document_render'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    export=json.loads((RENDER/'word_export_receipt.json').read_text(encoding='utf-8-sig'))
    assert export['inputSHA256']==sha(DOC)
    pdf=RENDER/'NYGRID_2025_LATEST_MODEL_STRUCTURE.pdf'
    reader=PdfReader(pdf);assert len(reader.pages)==7
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
        'm':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
    with zipfile.ZipFile(DOC) as z:
        xml=etree.fromstring(z.read('word/document.xml'));styles=etree.fromstring(z.read('word/styles.xml'))
        assert not xml.xpath('//w:pBdr',namespaces=ns) and not styles.xpath('//w:pBdr',namespaces=ns)
        equations=len(xml.xpath('//m:oMath',namespaces=ns));assert equations==8
    images=[RENDER/f'page-{j}.png' for j in range(1,8)]
    assert all(p.is_file() for p in images)
    result={'passed':True,'document':{'path':DOC.relative_to(ROOT).as_posix(),'sha256':sha(DOC)},
        'pages':7,'native_editable_OMML_equations':equations,'title_and_style_borders_absent':True,
        'render_backend':export['renderer'],'readonly_export':True,
        'all_seven_page_images_visually_inspected':True,
        'last_changed_pages_reinspected':[1,4,6,7],
        'visual_findings':'No clipping, overlap, missing glyphs, broken tables or stray pages. Schematic labels and native equations readable.',
        'QA_only_pdf_sha256':sha(pdf),'QA_only_page_image_sha256':{p.name:sha(p) for p in images}}
    (OUT/'structure_document_visual_review.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'pages':7,'native_equations':equations,'document_sha256':sha(DOC)}))
if __name__=='__main__':main()
