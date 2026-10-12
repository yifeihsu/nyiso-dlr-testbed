"""Seal the bounded primary-source P34 unit, origin and direction audit.

No numeric scale or sign is selected using model/interface agreement. The source
layer distinguishes explicit operator statements from historical corroboration
and unresolved publication semantics.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import io
import json

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_p34_qualification/sources'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def evidence_source(filename):
    p=OUT/filename
    receipt=json.loads(p.with_suffix(p.suffix+'.receipt.json').read_text(encoding='utf8'))
    assert sha(p)==receipt['sha256'],filename
    return dict(source_path=p.relative_to(ROOT).as_posix(),source_sha256=sha(p),source_url=receipt['source_url'])

def build():
    rows=[]
    def add(claim_id,status,claim,qualification,filename,location,date='not stated'):
        rows.append(dict(claim_id=claim_id,status=status,claim=claim,qualification=qualification,evidence_location=location,document_date=date,**evidence_source(filename)))
    native='NYISO_OASIS_ParFlows_20251219.csv'
    raw=(OUT/native).read_text(encoding='utf8')
    assert raw.splitlines()[0]=='"Timestamp","Point ID","Flow (MWH)"'
    meta=json.loads((OUT/'NYISO_OASIS_frontend_postings.json').read_text())
    p34=next(x for x in meta if x['reportRef']=='P-34')
    assert p34['postingEnum']=='PAR_FLOW' and p34['preambleText'] is None and p34['preambleHtml'] is None
    assert p34['supportedFormats']==['CSV']
    schedule=(OUT/'NYISO_PARschedule_definition_printable.txt').read_text(encoding='utf8')
    assert 'Hourly MWs (# of Time Steps)' in schedule and 'Nominal PAR Schedule' in schedule
    guide=(OUT/'NYISO_MarketParticipants_UserGuide_Sep2026.txt').read_text(encoding='utf8')
    assert 'time-weighted hourly flows in RTD' in guide
    jan=(OUT/'NYISO_PARdiagram_version1_0.txt').read_text(encoding='utf8')
    july=(OUT/'NYISO_PARdiagram_version2_0.txt').read_text(encoding='utf8')
    assert '01/09/2026' in jan and '07/17/2026' in july
    assert all(x in jan for x in ['625149','625150','25118','25119','12/03/2024'])
    assert sha(OUT/'NYISO_PARdiagram_version1_0.pdf')=='98553ac3d45f1d836032180ea768ff1ad49ee61edf7bb4eaeabc3b69112ecac2'
    assert sha(OUT/'NYISO_PARdiagram_version2_0.pdf')=='c0647d2abc38f216ccf5c1f197ca679cf16358fde5f507659bcdcd80a6938ba4'
    assert sha(OUT/'NYISO_PARdiagram_version1_1.pdf')==sha(OUT/'NYISO_PARdiagram_version1_0.pdf')
    add('U01','confirmed','Fresh official OASIS P34 archive CSV labels its native value Flow (MWH).','This is the literal header; it does not establish interval duration, whether the quantity is energy, or whether MWH is an erroneous label.',native,'CSV header','2025-12-19 data; retrieved 2026-10-12')
    add('U02','confirmed','Current OASIS metadata identifies report P-34 as PAR_FLOW with CSV only and no explanatory preamble.','No unit or measurement-origin definition is supplied by this public metadata record.','NYISO_OASIS_frontend_postings.json','P-34 record','retrieved 2026-10-12')
    add('U03','confirmed_schedule_only','The operator-linked P53A PAR Schedule Definition specifies Hourly MWs.','The document defines Nominal PAR Schedule and is linked only by P53A. It cannot directly certify the native P34 flow unit.','NYISO_PARschedule_definition.doc','Nominal PAR Schedule row','not stated')
    add('U04','confirmed_report_description','The Market Participants User Guide describes PAR flows as hourly SCUC flows and time-weighted hourly RTD flows.','The retrieved native P34 file has subhourly timestamps. The guide does not resolve that cadence mismatch or the literal native MWH header.','NYISO_MarketParticipants_UserGuide_Sep2026.pdf','PDF90 / printed55 / section5.5.4','2026-09')
    add('U05','unresolved','A direct public definition of the native P34 physical unit and required time scaling was not established.','Neither dividing by 12 nor multiplying by 12 nor relabeling as confirmed MW is justified solely by the inspected primary definitions.',native,'CSV header and timestamps','2025-12-19')
    add('O01','unresolved','The native P34 publication was not established to be independent SCADA/metered actual flow or a calculated RTD flow.','Safe label: operator-reported P34 flow value. Market scheduling context and telemetry in other operating agreements do not prove this specific public product origin.','NYISO_MarketParticipants_UserGuide_Sep2026.pdf','PDF90 / printed55 / section5.5.4','2026-09')
    add('T01','unresolved','Native P34 timestamp meaning as interval beginning, interval ending, instantaneous sample, or average was not established by a direct format definition.','Subhourly cadence is observable; that alone does not define the time support of each numeric value.',native,'Timestamp field','2025-12-19')
    add('S01','confirmed','The public version=1.0 diagram request returns a genuine older document published January9,2026.','URL path still says ParFlowDiagrams27.pdf; server Content-Disposition says ParFlowDiagrams26.pdf. Content date and SHA distinguish it from the July17,2026 edition.','NYISO_PARdiagram_version1_0.pdf','Cover page1 and HTTP receipt','2026-01-09')
    add('S02','confirmed_documented_convention','Dover PTIDs625149/625150 are positive from Long Mountain/ISONE toward Cricket Valley/NYISO.','Visually confirmed on January2026 page6 and its positive-arrow legend. No Dover-specific effective date is printed.','NYISO_PARdiagram_version1_0.pdf','Dover page6; legend page26','2026-01-09')
    add('S03','indirect_historical_corroboration','January9,2026 Dover arrows agree with the July17,2026 operator diagram.','This near-contemporaneous publication supports the convention but is not explicit proof of its effective date throughout December2025. No2025 dated Dover diagram was retrieved.','NYISO_PARdiagram_version2_0.pdf','Dover page6; cover page1','2026-07-17')
    add('S04','confirmed_explicit_effective_note','St.Lawrence PTIDs25118/25119 are positive IESO-to-Moses/NYISO under the convention explicitly stated as of December3,2024.','The note applies to St.Lawrence/Moses page7 only. It supports2025 Ontario sign use and must not be transferred to Dover.','NYISO_PARdiagram_version1_0.pdf','St.Lawrence page7; legend page26','2026-01-09, with explicit convention date2024-12-03')
    add('A01','confirmed_duplicate_response','Requests version=1.0 and version=1.1 returned identical older diagram bytes.','Do not count these as two distinct historical releases.','NYISO_PARdiagram_version1_1.pdf','SHA comparison and cover','2026-01-09 content')
    add('A02','confirmed_archive_binding','Current official OASIS API binds the selected December19,2025 PAR_FLOW archive to ParFlows-20251219.csv.','The listing supplies archive timestamps and download location, not field units or telemetry provenance.','NYISO_OASIS_PAR_FLOW_postings_20251219.json','Public postings API response','2025-12-19 fileDate')
    return rows,p34

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    rows,p34=build();buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    data=buffer.getvalue().encode('utf8');register=OUT/'primary_evidence_register.csv'
    archive_files=[p for p in sorted(OUT.iterdir()) if p.is_file() and p.name not in ['primary_evidence_register.csv','primary_evidence_conclusion.json']]
    files=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in archive_files]
    conclusion=dict(passed=True,audit_complete=True,audit_scope='bounded primary public-source audit; no internal-interface fit or model mutation',
        physical_unit_confirmed=False,raw_header='Flow (MWH)',raw_quantity_unit_status='unresolved_from_primary_native_product_definition',
        numeric_scale_selected_by_this_audit=None,scale_or_sign_selected_by_internal_fit=False,
        product_kind=dict(safe_label='operator-reported P34 flow value',independent_metered_actual_confirmed=False,SCADA_origin_confirmed=False,calculated_RTD_origin_confirmed=False,status='unresolved_native_publication_origin'),
        native_timestamp_support_status='unresolved_begin_end_instantaneous_or_average',
        guide_scope='September2026 MPUG describes hourlySCUC andtime-weighted hourlyRTD reports; nativeCSV is subhourly andthe guide doesnot defineitsMWHlabel',
        schedule_definition_scope='P53A nominal PAR schedule explicitly usesHourlyMWs; not aP34unit specification',
        sign={
            'Dover':dict(ptids=[625149,625150],positive_direction='ISONE_LongMountain_to_NYISO_CricketValley',documented_convention_confirmed=True,earliest_retrieved_operator_document_date='2026-01-09',specific_2025_effective_date_confirmed=False,qualification='near-contemporaneous official corroboration, not a2025-effective-date certificate'),
            'Ontario_StLawrence':dict(ptids=[25118,25119],positive_direction='IESO_StLawrence_to_NYISO_Moses',documented_convention_confirmed=True,explicit_convention_date='2024-12-03',applies_to_2025=True,qualification='explicitnote onStLawrence/Mosespage7, not Dover')},
        historical_search=dict(status='bounded_search_completed',version1_0_actual_filename='ParFlowDiagrams26.pdf',version1_0_content_date='2026-01-09',version1_0_sha256=sha(OUT/'NYISO_PARdiagram_version1_0.pdf'),version1_1_same_payload=True,version2_0_content_date='2026-07-17',version2_0_sha256=sha(OUT/'NYISO_PARdiagram_version2_0.pdf'),older_by_filename25='HTTP404',public_folder_listing='HTTP404',targeted_2024_2025_archive_index='empty_result; not proof that no other historical copy exists'),
        current_OASIS_P34_metadata=p34,
        code_inspection=dict(public_bundle='NYISO_OASIS_index-BcpghG6r.js',finding='Generic posting/download UI only; no native P34 chart-unit or value-schema definition found.',definition_coverage='public UI and metadata inspected, not private backend implementation'),
        visual_verification=dict(completed=True,older_diagram_pages=[1,6,7,26],current_diagram_previously_verified_same_sha256=True),
        unchanged_existing_model_and_artifacts=True,internal_interface_observations_read=False,
        register_sha256=hashlib.sha256(data).hexdigest(),evidence_rows=len(rows),archived_files=files,
        reproducer=dict(path=Path(__file__).relative_to(ROOT).as_posix(),sha256=sha(__file__)))
    # Write readable prose without promoting a qualified interpretation to a fact.
    conclusion['guide_scope']='The September 2026 MPUG describes hourly SCUC and time-weighted hourly RTD reports. Native P34 CSV is subhourly, and the guide does not define its MWH label.'
    conclusion['schedule_definition_scope']='P53A nominal PAR schedules explicitly use hourly MWs. This is not a P34 unit specification.'
    proof=(json.dumps(conclusion,indent=2)+'\n').encode('utf8');proofpath=OUT/'primary_evidence_conclusion.json'
    if args.verify:
        assert register.read_bytes()==data,'Register reproduction failed'
        assert proofpath.read_bytes()==proof,'Conclusion reproduction failed'
    else:
        register.write_bytes(data);proofpath.write_bytes(proof)
    print(json.dumps(dict(passed=True,evidence_rows=len(rows),register_sha256=conclusion['register_sha256'],conclusion_sha256=hashlib.sha256(proof).hexdigest(),unit_status='unresolved',Dover2025_sign_status='near-contemporaneous_corroboration'),indent=2))

if __name__=='__main__':main()
