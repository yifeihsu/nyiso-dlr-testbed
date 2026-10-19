"""Compile bounded public evidence for Dover topology and published ratings.

No hidden/redacted electrical content is extracted, and no interface observation
is read. Missing factory parameters remain missing in this source layer.
"""
from pathlib import Path
import csv
import hashlib
import io
import json
import argparse

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/nygrid_2025_dover_parameters/sources'
PROJECT=OUT/'Dover_DPS_Transfer_Petition_SA2734_2025.pdf'
DESIGN=ROOT/'output/nygrid_2025_line_parameters/sources/projects/NYTransco_SA2510_2023.pdf'
ORDER=OUT/'Dover_DPS_CPCN_Order_20230316.pdf'
ROWS=[]

def add(field,value,units,file,pdf_page,printed_page,evidence,qualification,anchor=''):
    proof=json.loads(file.with_suffix('.pdf.receipt.json').read_text())
    digest=hashlib.sha256(file.read_bytes()).hexdigest()
    assert digest==proof['sha256'],file
    if anchor:
        assert anchor in file.with_suffix('.txt').read_text(encoding='utf8'),(file,anchor)
    ROWS.append(dict(field=field,value=value,units=units,evidence_class=evidence,
        pdf_page_1based=pdf_page,printed_page=printed_page,qualification=qualification,
        source_url=proof['source_url'],local_path=file.relative_to(ROOT).as_posix(),sha256=digest))

def build():
    ROWS.clear()
    add('active_design_bank_count',2,'count',PROJECT,7,'6','primary_owner_2025_project_description','Two active design positions; this does not establish that both are online at every hour.','two parallel 750')
    add('bank_connection','parallel','',PROJECT,7,'6','primary_owner_2025_project_description','Two banks span the same station port pair. They are not two sequential banks, and the spare is not an active third parallel branch.','two parallel 750')
    add('bank_rating',750,'MVA_per_bank',PROJECT,7,'6','primary_owner_2025_project_description','Nameplate/design capacity; 1500MVA aggregate requires two banks available and sharing appropriately, and does not establish line or system transfer capability.','750 Mega Volt Ampere')
    add('spare_bank_count',1,'count',ORDER,4,'4','primary_regulator_order','Order explicitly says third PAR is stored onsite and left unenergized for replacement; do not count as an online power path.','spare PAR')
    add('bypass_equipment_present','true','boolean',PROJECT,7,'6','primary_owner_2025_project_description','Published bypass switches establish physical capability, not historical hourly switching state.','bypass switches')
    add('station_voltage',345,'kV',PROJECT,100,'A-2','primary_interconnection_agreement','Air-insulated station intercepts the existing345kV circuit398.','345 kV nominal')
    add('west_port_line','Y17 to Cricket Valley','',PROJECT,101,'A-3','primary_interconnection_agreement','Source identifies new/reconductored segment to Dover West as Y17.','Substation (West), to be redesignated Y-17')
    add('east_port_line','398 to Long Mountain via NY-CT border','',PROJECT,115,'C-3','primary_interconnection_agreement_and_public_POI_figure','The public ownership figure separately identifies Y17 toward Cricket Valley and398 toward Long Mountain.','the NY- CT state')
    add('NY_loop_conductor','twin-bundled 795 kcmil ACSS Mallard','',PROJECT,101,'A-3','primary_interconnection_agreement','Connects Dover into the pre-existing398 line; line-only parameters must remain separate from PAR impedances.','twin-bundled 795 kcmil ACSS Mallard')
    add('bypass_revenue_meter_location','Cricket Valley','',PROJECT,118,'C-6','primary_interconnection_agreement','Existing revenue meter retained whenever PARs are bypassed/out of service. Missing PAR meter values cannot alone prove zero total intertie flow.','whenever the PARs are bypassed (out of service)')
    add('in_service_revenue_meter_location','Dover PAR Substation','',PROJECT,118,'C-6','primary_interconnection_agreement','Dover revenue meters used when PARs are in service; actual hourly mode still requires observations.','whenever the PARs are in-service')
    add('station_status_on_2025_11_21','completed_and_partially_energized','',PROJECT,7,'6','primary_owner_2025_status_statement','Do not describe a later full-control/in-service cutover as necessarily first electrical energization.','partially energized')
    add('bank_rating_sequence','450/600/750','MVA',DESIGN,44,'7','primary_development_agreement','Published per-bank rating sequence. Source does not label the cooling modes.','450/600/750')
    add('phase_shift_design_range',40,'degree_plus_minus',DESIGN,44,'7','primary_development_agreement','Source states+/-40degrees but does not explicitly name this no-load angle; using it as no-load in a phasor calculation is an additional assumption.','40')
    add('maximum_advance_at_750MVA',32,'degree',DESIGN,44,'7','primary_development_agreement','Source does not state voltage ratio, power factor, tap-specific impedance, or loss conditions.40-to32 alone does not uniquely identify factory X.','shift capability at 750 MVA = 32')
    add('factory_series_R_X','not_established','',PROJECT,116,'C-4','public_source_gap','Station FigureC-2 is redacted; no factory seriesR/X or tap-dependent impedance table found in the reviewed public sources.')
    add('factory_no_load_and_load_loss','not_established','',PROJECT,116,'C-4','public_source_gap','No factory no-load/load-loss test results found in the reviewed public source set.')
    add('hourly_bypass_and_tap_schedule_2025','not_established_by_project_documents','',PROJECT,118,'C-6','public_source_gap','Physical mode capability and meter relocation do not supply actual hourly tap angles or breaker states.')
    diagram=OUT/'NYISO_ParFlowDiagrams27.pdf'
    add('normal_bypass_state','open','',diagram,6,'6; legend26','primary_operator_diagram','Dover bypass explicitly labeledN.O.; page26 legend defines normally open. Normal diagram state is not hourly breaker telemetry.','N.O.')
    add('bank_PTIDs','T398-A:625149;T398-B:625150','',diagram,6,'6','primary_operator_diagram','Two parallel bank paths shown betweenY17 and398 station ports.','625149')
    add('positive_flow_direction','Long Mountain to Cricket Valley','',diagram,6,'6; legend26','primary_operator_diagram','Cyan plus-marked arrows point from398 east side towardY17 west side; document publishedJuly17,2026. Dover page has no specific2024 effective-date label; the December3,2024 note applies to Moses page7.','625150')
    guide=OUT/'NYISO_MarketParticipants_UserGuide.pdf'
    add('P34_report_time_basis','time-weighted hourly RTD flow','',guide,90,'55; section5.5.4','primary_operator_report_definition','Retrieved guide issuedSeptember2026. Specifies hourly aggregation; does not explicitly explain literalCSV headerFlow(MWH).','time-weighted hourly flows in RTD')
    add('P34_energy_to_mean_power_numeric_equivalence','MWh_over_one_hour_equals_average_MW','',guide,90,'55; section5.5.4','unit_interpretation_conditioned_on_hourly_rows','For verified one-hour rows, numericalMWh/1h equals meanMW. Preserve rawMWHheader; this is not an operator statement that the header is a typo.','time-weighted hourly flows in RTD')
    return ROWS

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    rows=build();buffer=io.StringIO(newline='');w=csv.DictWriter(buffer,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    content=buffer.getvalue().encode('utf8');dest=OUT/'dover_source_register.csv'
    proof=dict(passed=True,record_count=len(rows),internal_interface_observations_used=False,
        source_only=True,exact_factory_R_X_established=False,hourly_taps_established=False,
        parallel_topology_established=True,bypass_capability_established=True,
        phase40_explicitly_labeled_no_load_by_source=False,
        register_sha256=hashlib.sha256(content).hexdigest(),
        reviewed_project_files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(OUT.glob('*.pdf'))],
        visually_inspected_images=['Dover_2025_parallel_bypass_p7.png','Dover_bypass_metering_p118.png','Dover_ownership_diagram_p115.png','Dover_SA2734_public_C2_p116.png','Dover_site_layout_p4.png','NYISO_Dover_PAR_diagram_p6.png','NYISO_MPUG_PAR_hourly_p90.png'])
    proofbytes=(json.dumps(proof,indent=2)+'\n').encode('utf8');proofpath=OUT/'dover_source_evidence_receipt.json'
    if args.verify:
        assert dest.read_bytes()==content,'Source register changed'
        assert proofpath.read_bytes()==proofbytes,'Evidence receipt changed'
    else:
        dest.write_bytes(content);proofpath.write_bytes(proofbytes)
    print(json.dumps(dict(passed=True,rows=len(rows),sha256=proof['register_sha256']),indent=2))

if __name__=='__main__':main()
