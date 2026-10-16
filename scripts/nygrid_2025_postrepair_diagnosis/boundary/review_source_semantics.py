"""Seal cached primary-source semantics and the newly inspected older sign page."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_postrepair_diagnosis/boundary'


def record(p):
    p=Path(p)
    with p.open('rb')as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=p.relative_to(ROOT).as_posix(),sha256=digest,bytes=p.stat().st_size)


def main():
    prior=ROOT/'output/nygrid_2025_p34_qualification/sources'
    pdf=prior/'NYISO_PARdiagram_version1_0.pdf'
    receipt=json.loads((prior/'NYISO_PARdiagram_version1_0.pdf.receipt.json').read_text())
    assert record(pdf)['sha256']==receipt['sha256']=='98553ac3d45f1d836032180ea768ff1ad49ee61edf7bb4eaeabc3b69112ecac2'
    text=(prior/'NYISO_PARdiagram_version1_0.txt').read_text(encoding='utf-8')
    assert 'Published to NYISO Website on 01/09/2026' in text and '325270 SAND BAR' in text
    qualification=json.loads((prior/'primary_evidence_conclusion.json').read_text())
    assert not qualification['physical_unit_confirmed'] and not qualification['product_kind']['independent_metered_actual_confirmed']
    cevc=ROOT/'output/nygrid_2025_flowgate_definitions/sources/central_north/NYISO_CEVC24_2024.txt'
    ctext=cevc.read_text(encoding='utf-8')
    assert 'S HERO__-PLATSBRG_115_PV20 25027' in ctext
    sources=[pdf,prior/'NYISO_PARdiagram_version1_0.pdf.receipt.json',prior/'NYISO_PARdiagram_version1_0.txt',
        prior/'primary_evidence_conclusion.json',
        ROOT/'output/nygrid_2025_par_controls/sources/direction/NYISO_ParFlowDiagrams27.pdf',
        cevc,cevc.with_suffix('.pdf'),
        ROOT/'output/nygrid_2025_flowgate_definitions/definitions/central_north_2025_qualifiers.json',
        ROOT/'output/nygrid_2025_moses_repair/boundary/sources/ISONE_OP17A_boundaries_current.pdf',
        ROOT/'output/nygrid_2025_moses_repair/boundary/sources/VEC2025_IRP_section4_SouthHero.pdf',
        OUT/'sources/January2026_SandBar_direction_page08.png',OUT/'sources/January2026_direction_legend_page26.png']
    report=dict(status='cached_primary_sources_and_near_contemporaneous_sign_corroboration_reviewed',
        created_utc=datetime.now(timezone.utc).isoformat(),
        January2026_document_url=receipt['source_url'],publication_date='2026-01-09',
        visual_review=dict(pages=[8,26],completed=True,
            finding='Page8 labels PTID325270 Sand Bar PAR PS01 and a cyan plus arrow from Sand Bar ISO-NE toward South Hero and Plattsburgh NYISO. Page26 defines the cyan plus arrow as positive flow.'),
        July2026_direction_same=True,earliest_inspected_SandBar_document_date='2026-01-09',
        specific_2025_sign_effective_date_verified=False,
        historical_sign_interpretation='Near-contemporaneous official corroboration strengthens the declared 2025 continuity assumption; it does not replace a dated historical convention record.',
        P34_product_description='Operator-reported P34 numeric flow value',
        adopted_numeric_interpretation='Numeric-as-MW and exact forward-hold hourly integration, unchanged from the sealed model.',
        independently_resolved_native_P34_unit=False,independently_resolved_metered_or_calculated_publication_origin=False,
        independently_resolved_native_timestamp_support=False,
        qualifier_interpretation='These are unresolved metadata questions, not proof that the reported values are wrong or that another numerical multiplier should be selected.',
        physical_PV20_facility_identifier=dict(PTID=25027,label='S HERO__-PLATSBRG_115_PV20',
            source='CEVC24 page7 Figure4 transmission-facility outage table',
            distinct_from_SandBar_PAR_PTID=325270,
            public_hourly_flow_series_for_PTID25027_found=False,
            qualification='This is an official facility identifier, not proof of a public telemetry endpoint or its numerical sign.'),
        source_scope=dict(CEVC24_page13_contains_PV20=True,
            generic_CE_definition_not_a_certified_public_CE_VC_expression=True,
            complete_physical_TE_operator_requires_PJM_and_meter_end_terms_beyond_PV20=True),
        complete_SouthHero_loss_bypass_uncertainty_bound_MW=None,
        SouthHero_6_66_MVA_scope='2025 planning peak of feeder29-1A only; not a total hourly tap-load series, observed correction or full meter-error bound.',
        bounded_search_this_turn=['Targeted official-domain queries for 2025 PAR direction diagrams and Sand Bar positive-flow metadata returned no additional dated source. Existing archived January2026 source was inspected first; no source downloaded or replaced.'],
        source_or_operator_selected_by_P32_fit=False,existing_model_map_package_changed=False,
        dependencies=[record(p)for p in sources],script_sha256=record(Path(__file__))['sha256'])
    (OUT/'source_semantics_review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k]for k in ['status','earliest_inspected_SandBar_document_date','specific_2025_sign_effective_date_verified','independently_resolved_native_P34_unit','complete_SouthHero_loss_bypass_uncertainty_bound_MW']},indent=2))


if __name__=='__main__':main()
