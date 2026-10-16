"""Manufacturer-backed thermal properties and declared synthetic AC defaults.

The synthetic network retains its existing power scale and 100-MVA base. No
gamma current lift, impedance transformation or fractional circuit is used.
"""
from pathlib import Path
import csv
import io
import json
import hashlib
import math
import datetime
import urllib.request
import concurrent.futures

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'output/nygrid_2025_ac_system/engineering'
SRC=OUT/'sources'
CAT=ROOT/'output/nygrid_2025_line_parameters/conductors/conductor_catalog.csv'
URLS={
 'NIST_Aluminum_solid.web.txt':'https://webbook.nist.gov/cgi/cbook.cgi?ID=C7429905&Mask=2',
 'NIST_Iron_solid.web.txt':'https://webbook.nist.gov/cgi/cbook.cgi?ID=C7439896&Mask=2',
 'MATPOWER_caseformat_8_1.web.txt':'https://matpower.org/documentation/ref-manual/legacy/functions/caseformat.html',
 'DOE_CleanLine_thermal_example.pdf':'https://www.energy.gov/sites/prod/files/2015/04/f22/CleanLinePt2-Appendix-8-A.pdf',
}
SHOMATE={
 'Al':dict(molar_mass_kg=.0269815386,valid_K=[298.,933.],A=28.08920,B=-5.414849,C=8.560423,D=3.427370,E=-.277375),
 'Fe':dict(molar_mass_kg=.055845,valid_K=[298.,700.],A=18.42868,B=24.64301,C=-8.913720,D=9.664706,E=-.012643),
}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def cp(element,tc):
    row=SHOMATE[element];kelvin=tc+273.15
    if not row['valid_K'][0]<=kelvin<=row['valid_K'][1]:raise ValueError('Outside NIST coefficient range')
    t=kelvin/1000
    return (row['A']+row['B']*t+row['C']*t*t+row['D']*t*t*t+row['E']/t**2)/row['molar_mass_kg']

def fetch(item):
    name,url=item;p=SRC/name;receipt=p.with_suffix(p.suffix+'.receipt.json')
    if p.exists() and receipt.exists():
        old=json.loads(receipt.read_text());assert sha(p)==old['sha256'];return
    with urllib.request.urlopen(url,timeout=90) as r:data=r.read();content_type=r.headers.get('Content-Type');resolved=r.url
    if name.endswith('.pdf'):assert data.startswith(b'%PDF')
    p.write_bytes(data)
    receipt.write_text(json.dumps(dict(source_url=url,resolved_url=resolved,content_type=content_type,bytes=len(data),sha256=sha(p),retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2)+'\n',encoding='utf8')

def writecsv(p,rows):
    s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows);p.write_text(s.getvalue(),encoding='utf8')

def main():
    SRC.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(fetch,URLS.items()))
    al=(SRC/'NIST_Aluminum_solid.web.txt').read_text(encoding='utf8');fe=(SRC/'NIST_Iron_solid.web.txt').read_text(encoding='utf8')
    assert '28.08920' in al and '18.42868' in fe
    with CAT.open(encoding='utf8',newline='') as f:catalog=list(csv.DictReader(f))
    # Direct extension of the same archived primary manufacturer ACSR catalog.
    acsr_pdf=ROOT/'output/nygrid_2025_line_parameters/conductors/sources/prysmian_acsr_us.pdf'
    acsr_text=acsr_pdf.with_suffix('.txt').read_text(encoding='utf8')
    linnet_electrical=next(line for line in acsr_text.splitlines() if line.lstrip().startswith('Linnet') and '0.0615' in line)
    linnet_mechanical=next(line for line in acsr_text.splitlines() if line.lstrip().startswith('Linnet') and '315.6' in line)
    assert all(s in linnet_electrical for s in ['0.720','0.0514','0.0242'])
    assert '145.5' in linnet_mechanical
    lb_per_kft_to_kg_per_m=.45359237/304.8
    catalog.append(dict(catalog_id='PRYSMIAN_ACSR_LINNET_336_4_26_7',family='ACSR',code_word='Linnet',
        diameter_m=.720*.0254,gmr_m=.0242*.3048,aluminum_mass_kg_per_m=315.6*lb_per_kft_to_kg_per_m,
        steel_mass_kg_per_m=145.5*lb_per_kft_to_kg_per_m,r_ac25_ohm_per_m=.0514/304.8,r_ac75_ohm_per_m=.0615/304.8,
        r_ac200_ohm_per_m='',source_url='https://na.prysmian.com/sites/na.prysmian.com/files/media/documents/TransPowr%C2%AE%20ACSR%20Bare%20Overhead%20Conductor%20%28US%29.pdf'))
    candidate_columns=['catalog_id','family','code_word','diameter_m','gmr_m','aluminum_mass_kg_per_m','steel_mass_kg_per_m',
        'r_ac25_ohm_per_m','r_ac75_ohm_per_m','r_ac200_ohm_per_m','source_url']
    writecsv(OUT/'candidate_conductor_catalog.csv',[{k:c[k] for k in candidate_columns} for c in catalog])
    rows=[]
    for c in catalog:
        acss=c['family']=='ACSS';tc=95. if acss else 75.
        ma=float(c['aluminum_mass_kg_per_m']);ms=float(c['steel_mass_kg_per_m']);ca=cp('Al',tc);cs=cp('Fe',tc)
        row=dict(catalog_id=c['catalog_id'],family=c['family'],code_word=c['code_word'],diameter_m=float(c['diameter_m']),gmr_m=float(c['gmr_m']),
            aluminum_mass_kg_per_m=ma,steel_mass_kg_per_m=ms,heat_capacity_j_m_k=ma*ca+ms*cs,
            emissivity=.5,absorptivity=.5,temperature_min_c=25.,temperature_max_c=tc,
            r_ac25_ohm_per_m=float(c['r_ac25_ohm_per_m']),r_ac75_ohm_per_m=float(c['r_ac75_ohm_per_m']),
            r_ac200_ohm_per_m=float(c['r_ac200_ohm_per_m']) if acss else 'NaN',
            resistance_supported_min_c=25.,resistance_supported_max_c=200. if acss else 75.,
            reference_temperature_c=tc,cp_reference_temperature_c=tc,aluminum_cp_j_kg_k=ca,steel_proxy_cp_j_kg_k=cs,
            thermal_record_scope='one_physical_subconductor_per_metre',
            cp_policy='NIST_pure_Al_and_alpha_Fe_at_reference_temperature;Fe_is_proxy_for_catalog_steel;constant_cp_assumption',
            surface_policy='declared_epsilon0p5_alpha0p5_reference;not_measured_surface_condition;DOE_example_corroborates_plausibility',
            temperature_policy='synthetic_normal_mechanical_study_cap;not_installed_asset_sag_certificate;no_use_below25C_without_versioned_policy',
            resistance_policy='manufacturer_AC_piecewise_linear_within_supported_range;no_hot_or_cold_extrapolation',
            installed_manufacturer_verified=False,source_catalog_sha256=sha(OUT/'candidate_conductor_catalog.csv'),source_url=c['source_url'])
        assert row['gmr_m']<row['diameter_m']/2 and row['heat_capacity_j_m_k']>0
        rows.append(row)
    writecsv(OUT/'thermal_conductors.csv',rows)
    geometry=[]
    for kv,bundles,nom,lo,hi in [(69,'1',3.5,2.5,5.5),(115,'1',5.5,3.5,8),(138,'1',5.5,3.5,8),(220,'1;2',7.5,5,11),(230,'1;2',7.5,5,11),(345,'2;3;4',10.2,7,14),(500,'3;4',13,9,18)]:
        geometry.append(dict(nominal_kv=kv,default_bundle_count=4 if kv==500 else 2 if kv==345 else 1,allowed_bundle_counts=bundles,
            gmd_nominal_m=nom,gmd_min_m=lo,gmd_max_m=hi,bundle_spacing_m=.4572,bundle_spacing_min_m=.3048,bundle_spacing_max_m=.6096,
            nparallel_default=1,nparallel_max_default=4,geometry_evidence_class='declared_synthetic_engineering_search_window',
            note='No voltage-only rule uniquely identifies conductor or geometry. Larger circuit counts require explicit aggregate-corridor labeling. 345kV single Bluebird allowed only by explicit exception/source binding.'))
    writecsv(OUT/'geometry_defaults.csv',geometry)
    equipment=dict(status='declared_finite_synthetic_equipment_choices_not_installed_asset_ratings',
        source_positive_RATE_A_preferred_as_hardware_limit=False,
        source_positive_RATE_A_policy='Retain as source_static_rating_mva with a provenance role. Use as an equipment ceiling only when the source explicitly establishes an equipment/nameplate rating.',
        F84_static_rating_mva=1323,
        F84_static_rating_role='summer_conductor_design_capability_at95C;not_terminal_equipment_ceiling',
        required_ledger_rating_fields=['source_static_rating_mva','source_static_rating_kind','equipment_ceiling_mva','equipment_ceiling_basis'],
        overhead_terminal_current_per_physical_circuit_A={'69':2000,'115':2000,'138':2000,'220':3000,'230':3000,'345':4000,'500':4000},
        terminal_limit_formula='sqrt(3)*nominal_kV*selected_terminal_A*nparallel/1000 MVA; bundle count does not multiply terminal hardware ampere rating',
        unrated_cable_selected_current_per_circuit_A=1000,
        cable_scope='Finite synthetic equipment ceiling only; not bare-conductor DLR or an IEC60287 soil/sheath assessment.',
        transformer_per_bank_MVA_pool=[50,75,100,150,200,300,450,600,750,1000,1500],
        transformer_integer_parallel_bank_counts=[1,2,3,4],
        transformer_own_base_impedance_screen_pu=[.04,.25],
        transformer_own_base_screen_status='Broad declared engineering plausibility window, not a manufacturer or statutory requirement.',
        transformer_base_relation='Z_pu_own=Z_pu_system*nparallel*S_bank/S_system for equal banks; outside the window requires separate aggregate-equivalent labeling or a versioned redesign.',
        station_reactance_equivalent_policy='Same MVA pool may provide a finite study ceiling; do not claim actual reactor, transformer or breaker identity from a zero-R same-voltage branch.',
        station_rows_not_ideal_couplers=[52,213,208],
        Dover_PAR_nameplate_per_bank_MVA=750,
        no_fitting_to_OPF_loading=True,capacities_are_uncertain_synthetic_study_choices=True)
    (OUT/'synthetic_equipment_defaults.json').write_text(json.dumps(equipment,indent=2)+'\n',encoding='utf8')
    assumptions=dict(power_scale='synthetic_existing_gamma_scaled_injections',base_mva=100.,current_gamma_lift=False,impedance_gamma_transform=False,
        current_definition='nominal_pi_series_current_excluding_shunt_charging;divide_by_integer_circuits_times_bundle_count',
        line_identity='R_eq=R_sub(T)*L/(n_bundle*n_parallel); X_eq=omega*2e-7*ln(GMD/GMR_bundle)*L/n_parallel; B_eq=n_parallel*omega*C_per_length*L',
        ratio_invariant='X_eq/R_eq is independent of n_parallel and L for identical circuits; n_parallel cannot repair an infeasible X/R ratio.',
        bundle_formula='GMR_bundle=(GMR_sub*n*Rcircle**(n-1))**(1/n), Rcircle=bundle_spacing/(2*sin(pi/n)), n>=2; same expression with physical radius for capacitance',
        inferred_length='After selecting a feasible conductor/bundle/GMD, L=R_eq*n_bundle*n_parallel/R_sub or L=X_eq*n_parallel/x_per_length; compare both before accepting.',
        feasibility_policy='Reject or separately label a branch when no finite candidate has plausible GMD/length. Never force a physical identity by fractional circuit count or fitting interface observations.',
        line_R_state_policy='AC_reference_R_at75C_ACSR_or95C_ACSS is not equilibrium_R(T). Coupled thermal/electrical studies must explicitly update R(T) or retain a labeled fixed-reference approximation.',
        per_subconductor_loss_identity='P_series_loss=3*n_parallel*n_bundle*I_sub**2*R_sub(T)*length; must equal branch series I-squared-R loss.',
        heat_capacity_model=SHOMATE,
        heat_capacity_uncertainty='Pure Al and alpha-Fe proxy, constant at reference temperature; manufacturing alloy/coating effects unverified.',
        surface_sensitivity=dict(reference=dict(emissivity=.5,absorptivity=.5),weathered_example=dict(emissivity=.8,absorptivity=.8),high_solar_low_emission_stress=dict(emissivity=.5,absorptivity=.9),status='declared scenarios, not statistical bounds'),
        equipment_classification='Voltage-changing, PAR, underground cable, fixed transfer, station reactance and accounting branches are excluded from bare overhead-conductor thermal equations.',
        same_voltage_zero_R_policy='Do not call a finite-X zero-R station equivalent an ideal breaker or fabricate its conductor identity. Assign a finite synthetic equipment ceiling and explicit class.',
        Q_policy='Enforce finite generator Q limits and record PV-to-PQ changes. A synthetic nameplate capability circle requires a declared S_rating and is not a certified machine capability curve.',
        source_field_semantics='MATPOWER branch B is total line charging; RATE_A is MVA; tap0 means the line convention, not proof of an absence of voltage-changing equipment.',
        synthetic_not_asbuilt=True,internal_interface_observations_used=False,
        sources=[dict(path=(SRC/name).relative_to(ROOT).as_posix(),url=url,sha256=sha(SRC/name)) for name,url in URLS.items()],
        source_catalog=dict(path=CAT.relative_to(ROOT).as_posix(),sha256=sha(CAT)),
        Linnet_extension=dict(source_pdf=acsr_pdf.relative_to(ROOT).as_posix(),sha256=sha(acsr_pdf),electrical_pdf_page=3,mechanical_pdf_page=2,
            electrical_row=linnet_electrical,mechanical_row=linnet_mechanical),
        outputs=[dict(path=(OUT/name).relative_to(ROOT).as_posix(),sha256=sha(OUT/name)) for name in ['thermal_conductors.csv','geometry_defaults.csv','candidate_conductor_catalog.csv','synthetic_equipment_defaults.json']])
    (OUT/'engineering_defaults.json').write_text(json.dumps(assumptions,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(passed=True,thermal_rows=len(rows),geometry_rows=len(geometry),cp_Al75=cp('Al',75),cp_Fe75=cp('Fe',75),thermal_path=str((OUT/'thermal_conductors.csv').relative_to(ROOT))),indent=2))

if __name__=='__main__':main()
