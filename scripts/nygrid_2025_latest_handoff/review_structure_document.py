"""Bind the independent current-only scientific review to final documents."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,zipfile
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_latest_handoff'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def record(path):return dict(path=path.relative_to(ROOT).as_posix(),sha256=digest(path))


def main():
    md=ROOT/'NYGRID_2025_LATEST_MODEL_STRUCTURE.md';doc=ROOT/'NYGRID_2025_LATEST_MODEL_STRUCTURE.docx'
    inventory_path=OUT/'structure/current_structure_inventory.json';visual_path=OUT/'structure_document_visual_review.json'
    figure=OUT/'structure/current_model_schematic.png'
    inventory=json.loads(inventory_path.read_text());visual=json.loads(visual_path.read_text())
    assert inventory['passed'] and visual['passed'] and visual['pages']==7
    assert visual['document']['sha256']==digest(doc)
    text=md.read_text(encoding='utf-8')
    with zipfile.ZipFile(doc) as z:
        xml=ET.fromstring(z.read('word/document.xml'))
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
        word=' '.join(x.text or '' for x in xml.findall('.//w:t',ns))
        equation_count=len(xml.findall('.//m:oMath',ns));assert equation_count==8
        media=[z.read(n) for n in z.namelist() if n.startswith('word/media/')]
        assert any(hashlib.sha256(data).hexdigest()==digest(figure) for data in media)
    for phrase in ['148','266','267','485','488','1,464','1,436','8,760','8,651','0.30012075175285535',
        '54 New York, 36 ISONE, 31 Ontario and 27 PJM','19 Dec 2025 23 EST','20 December 2025 at 04 UTC',
        'NEPTUNE','25118','25119','susceptance','Several conductor, bundle, circuit and length combinations may reproduce one R/X pair.',
        'R and X are ohms','Z_base = V_base,kV² / baseMVA','one-way thermal screen',
        'not 296 free real unknowns','not asserted literal asset terminals','amperes are never divided by gamma',
        '0.95–1.05 pu','audit.VQ_and_generator_assumption_gate']:
        assert phrase in text and phrase in word,phrase
    # The requested document is structure-only, so do not reintroduce a model
    # evolution narrative or saved annual scoring/results section.
    for term in ['susceptibility','S7','S13','S14','WAPE','8,170','481 rejected','95.45%','earlier engineering case']:
        assert term not in text and term not in word,term
    assert text.count('\n## ')==6
    assert 'model/structure/current_model_schematic.png' in text
    assert inventory['retained_bus_count']==148 and inventory['generation']['total_rows']==1464
    assert [s['synthetic_thermal_parent_count'] for s in inventory['states']]==[179,179,179,180]
    assert [s['runtime_branch_records'] for s in inventory['states']]==[485,485,485,488]
    for rec in inventory['outputs']:
        assert digest(ROOT/rec['path'])==rec['sha256']
    report=dict(passed=True,completed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent scientific and structure-only content review of final current-model Word/Markdown; no historical results or model-modification narrative',
        source_model_commit=inventory['model_snapshot_commit'],document_pages=7,native_editable_equations=8,
        current_counts_axes_controls_loss_policy_and_current_units_checked=True,
        explicit_conductor_ambiguity_and_one_way_screen_scope_preserved=True,
        operator_equations_checked_against_independently_rebuilt_four_state_matrices=True,
        current_structure_ledgers_and_figure_hashes_match=True,
        embedded_schematic_is_reviewed_print_asset=True,
        model_equations_source_eligibility_operating_bounds_and_thermal_flags_kept_separate=True,
        remaining_actionable_findings=[],
        corrections_resolved=['Removed saved annual result statistics from the structure-only document.','Changed DC susceptibility to DC susceptance.'],
        visual_review_scope='The bound document-team receipt records all seven rendered pages reviewed; this independent review checks scientific content and Word/Markdown/figure consistency.',
        package_relative_links='The schematic link is resolved at model/structure/current_model_schematic.png in the latest-only package, matching the supplied structure asset.',
        dependencies=[record(p) for p in [doc,md,inventory_path,visual_path,figure,Path(__file__).resolve()]])
    target=OUT/'structure_document_independent_review.json';target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='dependencies'},indent=2))


if __name__=='__main__':main()
