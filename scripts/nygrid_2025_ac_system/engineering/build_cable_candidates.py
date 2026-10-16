"""Cu/XLPE synthetic electrical candidates anchored to Southwire geometry/C.

These are not installed-cable identifications or underground thermal ratings.
The conductor R and magnetic L are declared engineering approximations; cable
dimensions, relative permittivity and capacitance come from the catalog.
"""
from pathlib import Path
import csv,hashlib,json,math,re

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_ac_system/engineering'
PDF=ROOT/'output/nygrid_2025_line_parameters/sources/cables/Southwire_HV_underground_catalog.pdf'
TEXT=PDF.with_suffix('.txt')
URL='https://www.southwire.com/medias/sys_master/installation-manuals/installation-manuals/h17/he9/8902203342878/HighVoltageUndergroundTransmissionCatalogpdf.pdf'
EPS0=8.8541878128e-12

def main():
    parts=re.split(r'\nPDF PAGE (\d+)\n',TEXT.read_text(encoding='utf8'))
    pages={int(parts[i]):parts[i+1] for i in range(1,len(parts),2)}
    rows=[]
    for kv,page in [(69,11),(115,15),(138,19),(220,23),(230,23),(345,27),(400,27)]:
        for line in pages[page].splitlines():
            a=line.split()
            if len(a)!=10 or '/' not in a[5] or not a[0].isdigit():continue
            kcmil,diam,ins,overins,jacket=map(float,a[:5]);cap,charging,cuweight,alweight=map(float,a[6:])
            area=kcmil*1000*math.pi*(.0254e-3)**2/4
            rcon=diam*.0254/2;router=overins*.0254/2;overall=jacket*.0254
            capacitance=cap*1e-12/.3048
            # Equivalent electrostatic inner radius absorbs semiconductive
            # screens rather than pretending the nominal metal radius equals it.
            cap_inner=router/math.exp(2*math.pi*EPS0*2.3/capacitance)
            rho20=1.7241e-8;alpha20=.00393;kac=1.10;tref=90.
            rdc=rho20/area;rac=rdc*(1+alpha20*(tref-20))*kac
            gmr=.7788*rcon
            gmd=.2286*2**(1/6) # right-triangle 9-inch duct-centre layout, Fig1
            inductance=2e-7*math.log(gmd/gmr)
            x_per_m=2*math.pi*60*inductance
            assert 0<rcon<cap_inner<router and gmr<gmd and overall<.2286
            rows.append(dict(catalog_id=f'SYNTHETIC_CU_XLPE_{kv}KV_{int(kcmil)}KCMIL',nominal_kv=kv,
                manufacturer_geometry_family='Southwire_standard_wall_XLPE_laminate',conductor_material='Cu',conductor_kcmil=kcmil,
                conductor_area_m2=area,conductor_diameter_m=2*rcon,insulation_thickness_m=ins*.0254e-3,
                diameter_over_insulation_m=2*router,overall_cable_diameter_m=overall,relative_permittivity=2.3,
                capacitance_f_per_m=capacitance,effective_capacitance_inner_radius_m=cap_inner,
                gmr_approx_m=gmr,phase_gmd_reference_m=gmd,phase_gmd_min_m=overall,phase_gmd_max_m=.75,
                conductor_rho20_ohm_m_assumed=rho20,conductor_alpha20_per_c_assumed=alpha20,ac_resistance_factor_assumed=kac,
                reference_temperature_c=tref,r_dc20_ohm_per_m=rdc,r_ac90_ohm_per_m=rac,
                inductance_h_per_m_reference=inductance,x_60hz_ohm_per_m_reference=x_per_m,
                b_60hz_siemens_per_m=2*math.pi*60*capacitance,
                nparallel_min=1,nparallel_max=4,conductors_per_phase_per_circuit=1,
                selected_static_current_ceiling_A_per_circuit=1000,
                static_current_policy='declared_finite_study_ceiling_not_manufacturer_ampacity;no_IEC60287_site_assessment',
                bare_overhead_thermal_eligible=False,soil_thermal_model_validated=False,
                electrical_R_policy='synthetic_bulk_Cu_rho_alpha_with1p10_AC_factor;not_manufacturer_AC_test;factor_sensitivity1p05_to1p30',
                electrical_X_policy='0p7788_radius_GMR_and_transposed_nonmagnetic_phase_geometry;screen_bonding_magnetic_loss_not_resolved',
                electrical_B_policy='manufacturer_capacitance_per_conductor;parallel_circuits_add_shunt_C',
                source_pdf_page=page,source_printed_page=page-2,source_url=URL,source_pdf_sha256=hashlib.sha256(PDF.read_bytes()).hexdigest(),
                synthetic_not_asbuilt=True))
    path=OUT/'cable_candidates.csv'
    with path.open('w',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    proof=dict(passed=True,candidate_rows=len(rows),source_voltage_pages={'69':11,'115':15,'138':19,'220_from230':23,'230':23,'345_and400':27},
        source_geometry_and_capacitance_verified=True,R_and_L_are_synthetic_approximations=True,installed_Cu_XLPE_assignments_verified=False,
        actual_site_ampacity_established=False,IEC60287_or_buried_thermal_solver_implemented=False,
        fitting_scope='Passive electrical R/X/B only. No dispatch, OPF loading or internal-interface observations used.',
        source_static_rating_warning='Catalog current tables use75percent load factor and specific soil/bonding layout; not adopted as continuously valid site ratings. The345/400kV ampacity size header also differs from its geometry table, so it is not joined by row position.',
        inverse_relations='R_eq=r_per_m*L/n;X_eq=x_per_m*L/n;B_eq=b_per_m*L*n. n changes length and charging, not X/R. GMD must exceed cable diameter. Preserve source n=1 circuit identities unless explicitly reinterpreted.',
        counterpart_geometry='Source Fig1 has three live cable centres in a9-inch right triangle and one spare duct; GMD=9in*2^(1/6), not the horizontal3-phase factor2^(1/3).',
        source_pdf=dict(path=PDF.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(PDF.read_bytes()).hexdigest(),url=URL),
        output=dict(path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (OUT/'cable_candidates_receipt.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(passed=True,rows=len(rows),path=str(path.relative_to(ROOT))),indent=2))

if __name__=='__main__':main()
