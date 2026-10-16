"""Conditional cable-charging estimates; never installed-conductor assignments.

The manufacturer lists many138kV products. Voltage/construction alone does not
select one, and its installation ampacity assumptions are not RCC field data.
"""
from pathlib import Path
import csv
import json
import math
import re
from build_estimates import ROOT,OUT,DEST,sha,record,dump,require


def build():
    pdf=OUT/'sources/cables/Southwire_HV_underground_catalog.pdf'
    txt=pdf.with_suffix('.txt');receipt=pdf.with_suffix('.receipt.json')
    png=pdf.with_name('Southwire_138kV_laminate_page19.png')
    require(sha(pdf)==json.loads(receipt.read_text())['sha256'],'Changed manufacturer catalog')
    section=txt.read_text(encoding='utf-8').split('PDF PAGE 19\n')[1].split('PDF PAGE 20')[0]
    require('(pF/ft)' in section and '(A/kft)' in section,'Cable capacitance/current units missing')
    catalog=[]
    for line in section.splitlines():
        tokens=line.split()
        if len(tokens)==10 and tokens[0].isdigit() and '/' in tokens[5]:
            size=int(tokens[0]);cap=float(tokens[6]);current=float(tokens[7])
            # pF per foot *1000ft -> nF per1000ft. Use the phase voltage,
            # because published138kV is the line-to-line system voltage.
            predicted=2*math.pi*60*(138000/math.sqrt(3))*cap*1e-9
            require(abs(predicted-current)<.011,'Manufacturer capacitance/charging-current identity failed')
            catalog.append(dict(size_kcmil=size,capacitance_pf_per_ft=cap,
                 capacitance_f_per_m=cap*1e-12/.3048,source_charging_current_a_per_kft=current,
                 calculated_charging_current_a_per_kft=predicted,
                 conductor_metal='copper_or_aluminum_product_family;actual_RCC_metal_unknown',
                 source_pdf_page=19,printed_page=17,installed_on_RCC_verified=False))
    require(len(catalog)==12 and len({r['size_kcmil'] for r in catalog})==12,'Incomplete138kV product family')
    rows=[]
    for key,miles,basis in [('QUEENS',6.,'inherited_public_route_approximation'),
                            ('BROOKLYN',1.,'inherited_public_route_approximation'),
                            ('STATEN',9.4,'contractor_completed_route')]:
        for item in catalog:
            capacitance=item['capacitance_f_per_m']*miles*1609.344
            b=2*math.pi*60*capacitance
            rows.append(dict(branch_key='RCC:CABLE:'+key,length_miles=miles,length_basis=basis,
                **item,total_capacitance_f=capacitance,total_b_siemens=b,
                b_pu_on_100MVA_138kV=b*(138**2/100),nominal_charging_mvar=b*138**2,
                applied_to_model=False,interpretation='conditional_manufacturer_product_scenario;not_installed_parameter_or_exhaustive_bound'))
    path=DEST/'RCC_charging_catalog_scenarios_not_applied.csv'
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    dump(OUT/'validation/cable_catalog_validation.json',dict(passed=True,source_rows=12,conditional_scenarios=36,
        manufacturer_charging_identity_max_error_a_per_kft=max(abs(x['source_charging_current_a_per_kft']-x['calculated_charging_current_a_per_kft']) for x in catalog),
        source_page_visually_reviewed=True,source_page=19,installed_conductor_or_field_rating_verified=False,
        no_conductor_selected_by_voltage_or_interface_error=True,applied_to_network=False,
        unknowns=['conductor_material_and_area','sheath_bonding','installation_geometry','R_temperature','series_inductance','thermal_environment','terminal_limits'],
        dependencies=[record(p) for p in [pdf,txt,receipt,png,Path(__file__),OUT/'sources/cables/Haugland_Goethals_FoxHills.html']],
        outputs=[record(path)]))
    print(json.dumps(dict(passed=True,manufacturer_rows=12,conditional_scenarios=36,applied_to_model=False)))


if __name__=='__main__':build()
