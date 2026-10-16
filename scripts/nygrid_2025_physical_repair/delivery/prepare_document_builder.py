"""Reuse the established manual layout with current repair and replay evidence."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
SRC=Path(__file__).parent


def main():
    old=ROOT/'scripts/nygrid_2025_latest_handoff/build_structure_document.py'
    text=old.read_text(encoding='utf-8')
    text=text.replace('parents[2]','parents[3]').replace("OUT = ROOT/'output/nygrid_2025_latest_handoff'", "OUT = ROOT/'output/nygrid_2025_physical_repair/delivery'")
    text=text.replace("TITLE = 'NYgrid 2025 current model structure'", "TITLE = 'NYgrid 2025 corrected model structure'")
    text=text.replace('13 October 2026','15 October 2026')
    text=text.replace("def main():\n    d = Document();", "def main():\n    import os\n    repair=ROOT/'output/nygrid_2025_physical_repair'\n    annual=repair/'annual'/os.environ.get('NYGRID_REPAIR_RUN_LABEL','physical_repair_v1')\n    ar=json.loads((annual/'annual_receipt.json').read_text());assert ar['completed']\n    score=json.loads((annual/'comparison/scoring_receipt.json').read_text());assert score['passed']\n    p41=json.loads((repair/'physics/parent41_parameters.json').read_text())\n    comp=json.loads((repair/'physics/compensation_design_review.json').read_text());assert comp['passed']\n    inventory=json.loads((OUT/'structure/current_structure_inventory.json').read_text());assert inventory['passed']\n    (OUT/'docs').mkdir(parents=True,exist_ok=True)\n    d = Document();")
    text=text.replace("'Prepared 15 October 2026. Current model snapshot '+BASE+'.'", "'Prepared 15 October 2026. Baseline model snapshot '+BASE+'; frozen physical-repair receipt '+inventory['physical_repair_receipt_sha256']+'.'")
    insertion="""
    page('Declared physical parameters')
    p('Parent 41 uses imported R = 0.0018 pu and X = 0.0089 pu with a coherent synthetic conductor realization. Its charging B is derived from the same geometry. Candidate selection uses the predeclared imported impedance inference and original charging only as a ranking aid. Neither observed interface errors nor a map chord selects these parameters.')
    c=p41['selected_candidate']
    tab(['Parent 41 quantity','Current value'],[
        ['Conductor family and catalog',c['family']+' '+c['code_word']+' 795 kcmil'],
        ['Parallel circuits and bundle',str(c['circuits'])+' circuits and '+str(c['bundle_count'])+' subconductor per phase'],
        ['Equivalent length',f"{c['length_m']/1000:.6f} km"],
        ['Phase GMD',f"{c['GMD_m']:.6f} m"],
        ['Reference and maximum temperature',f"{c['reference_temperature_C']:.0f} degrees C"],
        ['Total R and X',f"{p41['repaired_R_X_B'][0]:.7g} and {p41['repaired_R_X_B'][1]:.7g} pu"],
        ['Total derived charging B',f"{p41['repaired_R_X_B'][2]:.10g} pu"]],[2.9,4.0])
    p('This is an admissible equivalent realization, not an identification of installed conductors or physical route length. The aggregate apparatus current ceiling remains unchanged. The model registry and thermal segment records carry the current parameter basis and broad synthetic length bounds.')
    h('Section local compensation')
    p('Parents 185 and 195 retain their conductor parameters and their total fixed reactor rating of 75 percent of geometric line charging. Each pi section places half of its local 75 percent compensation at each end; contributions add at shared internal nodes. This distributed placement is a declared synthetic design. It does not identify installed intermediate stations or adjustable controllers.')
    selected=[r for r in comp['parameters_by_state'] if r['state_index']==1]
    tab(['Parent','Sections','Total reactor at 1 pu MVAr','Each terminal MVAr'],[
        [r['parent_row'],r['section_count'],f"{r['total_nominal_reactor_MVAr_preserved']:.6f}",f"{r['original_end_reactor_MVAr_each']:.6f}"] for r in selected],[.65,.8,2.7,2.75])
    p('The full-axis bus shunt vector and reactor ledger preserve this placement. Internal section buses remain passive nodes with zero prescribed injection, so their fixed shunts stay in the exact admittance reduction. Voltage limits, PV setpoints, hourly generation, demand and transfer targets are retained. The corrected admittance and current operators are rebuilt from the resulting case.')

"""
    text=text.replace("    page('Generation and controlled transfers')",insertion+"    page('Generation and controlled transfers')")
    annual_section="""
    page('Annual validation and use')
    p('The completed fresh annual coupled AC power-flow replay evaluates all 8,651 source-eligible hours on the preserved 8,760-hour axis. The compiled package preserves the hourly input shards byte for byte and uses the same four corrected templates. The public interface definitions, observation series, clock and power scale remain frozen.')
    tab(['Qualification measure','Hours'],[
        ['Full time axis',8760],['Source eligible',8651],['AC and loss equations',ar['policy_equation_qualified_hours']],
        ['Voltage and generator assumptions',ar['VQ_and_generator_assumption_qualified_hours']],
        ['Full declared operating gate',ar['full_operating_qualified_hours']],
        ['Solver exceptions',ar['solver_exceptions']]], [4.9,2.0])
    p('These flags answer different questions. Equation and loss closure supports a numerical flow result. Voltage, reactive and generator apparent-power checks test the declared operating assumptions. The full operating gate also includes the remaining modeled equipment and transfer checks. No count establishes installed facility ratings, actual dispatch feasibility, contingencies or an economic benefit from dynamic line rating.')
    p('The offline map shows predicted interface flows, delivered zonal load and assigned losses only where the equation and loss mask passes. Frozen gross load, native generation and prescribed transfers use the source mask. Failed iterates and source-excluded hours remain unavailable rather than being interpolated or shown as zero.')
    p('The annual comparison uses the same signed original-terminal interface operators and divides aggregate model MW by the fixed gamma for the public comparison. Separate files preserve the paired baseline cohort, new successful hours, lost successes and all-success cohort. Differences across cohorts must not be interpreted as paired model changes.')
    p('Exact model and candidate hashes, the annual and scoring receipts, structure ledgers and runtime checks are supplied with the package. The original baseline model and its earlier manual remain in the preserved baseline archive. The current package contains the corrected model described here.')

"""
    text=text.replace('    for el in list(d.styles.element.iter())',annual_section+'    for el in list(d.styles.element.iter())')
    text=text.replace("docx=ROOT/'NYGRID_2025_LATEST_MODEL_STRUCTURE.docx'; text=ROOT/'NYGRID_2025_LATEST_MODEL_STRUCTURE.md'", "docx=OUT/'docs/NYGRID_2025_PHYSICAL_REPAIR_MODEL_STRUCTURE.docx'; text=OUT/'docs/NYGRID_2025_PHYSICAL_REPAIR_MODEL_STRUCTURE.md'")
    text=text.replace("'scope':'current_model_structure_only'", "'scope':'corrected_model_structure_and_completed_annual_validation','candidate_receipt_sha256':inventory['physical_repair_receipt_sha256'],'annual_run':ar['run_label']")
    target=SRC/'build_structure_document.py';assert not target.exists();target.write_text(text,encoding='utf-8',newline='\n')
    old=ROOT/'scripts/nygrid_2025_latest_handoff/build_structure_schematic.py'
    text=old.read_text(encoding='utf-8').replace('parents[2]','parents[3]').replace('output/nygrid_2025_latest_handoff','output/nygrid_2025_physical_repair/delivery')
    target=SRC/'build_structure_schematic.py';assert not target.exists();target.write_text(text,encoding='utf-8',newline='\n')
    print('Prepared manual and schematic builders; completed annual receipt remains required.')


if __name__=='__main__':main()
