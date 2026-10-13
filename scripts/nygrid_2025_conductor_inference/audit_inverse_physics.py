"""Independent R/X-conditioned conductor mathematics and identifiability audit.

Reads frozen engineering/reference sources; writes this new audit namespace only.
No operating observations, AC solver, geographical chord or installed identity
enters the inverse feasibility calculation.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import re
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/nygrid_2025_conductor_inference/independent'
ENG = ROOT / 'output/nygrid_2025_ac_system/engineering'
OMEGA = 2 * math.pi * 60
KX = OMEGA * 2e-7
EPS = 8.8541878128e-12
BASE = 100.


def record(path):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=digest)


def radius_product(radius, n, spacing):
    """Use explicit all-pair distances, independently of the closed formula."""
    if n == 1:
        return radius
    circumradius = spacing / (2 * math.sin(math.pi / n))
    points = circumradius * np.exp(2j * math.pi * np.arange(n) / n)
    distances = np.abs(points[:, None] - points[None, :])
    np.fill_diagonal(distances, radius)
    return float(np.exp(np.log(distances).mean()))


def r_at(c, temperature):
    if 25 <= temperature <= 75:
        return c['r_ac25_ohm_per_m'] + (temperature - 25) / 50 * (c['r_ac75_ohm_per_m'] - c['r_ac25_ohm_per_m'])
    assert 75 < temperature <= 200 and math.isfinite(c['r_ac200_ohm_per_m'])
    return c['r_ac75_ohm_per_m'] + (temperature - 75) / 125 * (c['r_ac200_ohm_per_m'] - c['r_ac75_ohm_per_m'])


def forward(c, length, circuits, bundles, gmd, spacing, kv, temperature=None):
    temperature = c['reference_temperature_c'] if temperature is None else temperature
    rsub = r_at(c, temperature)
    gm = radius_product(c['gmr_m'], bundles, spacing)
    cr = radius_product(c['diameter_m'] / 2, bundles, spacing)
    assert gmd > max(gm, cr) and length > 0 and circuits >= 1
    xp = KX * math.log(gmd / gm)
    cp = 2 * math.pi * EPS / math.log(gmd / cr)
    zb = kv * kv / BASE
    return dict(r_pu=rsub * length / (circuits * bundles * zb),
                x_pu=xp * length / (circuits * zb),
                b_pu=circuits * OMEGA * cp * length * zb,
                rsub=rsub, xp=xp, cp=cp, gm=gm, cr=cr, zbase=zb)


def inverse_gmd(c, ratio, bundles, spacing):
    return radius_product(c['gmr_m'], bundles, spacing) * math.exp(ratio * r_at(c, c['reference_temperature_c']) / (bundles * KX))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    catalog_path = ENG / 'thermal_conductors.csv'
    geometry_path = ENG / 'geometry_defaults.csv'
    old_code = ROOT / 'scripts/nygrid_2025_ac_system/branches/line_equivalents.py'
    assignment_path = ROOT / 'output/nygrid_2025_ac_system/branches/branch_assignments.csv'
    recommendation_path = ROOT / 'output/nygrid_2025_ac_loss_revision/impedance/impedance_recommendation.json'
    source_text = ROOT / 'output/nygrid_2025_line_parameters/conductors/sources/prysmian_acsr_us.txt'
    paths = [catalog_path, geometry_path, old_code, assignment_path, recommendation_path, source_text,
             ROOT / 'scripts/nygrid_2025_ac_system/branches/build_assignments.py',
             ROOT / 'scripts/nygrid_2025_ac_loss_revision/core/ac_loss_prepare_case.m',
             ROOT / 'output/nygrid_2025_line_parameters/conductors/sources/prysmian_acsr_us.pdf',
             ROOT / 'output/nygrid_2025_line_parameters/conductors/sources/powerworld_translinecalc_v2.pdf']
    before = [record(p) for p in paths]
    catalog = pd.read_csv(catalog_path).to_dict('records')
    geometries = pd.read_csv(geometry_path).to_dict('records')
    # Import only the existing mathematical utility for cross-check, disabling
    # bytecode writes into its frozen source directory.
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('frozen_line_equivalents', old_code)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    radius_error = forward_error = inverse_error = joule_error = 0.
    checks = 0
    for c in catalog:
        for n in range(1, 9):
            for s in [.3048, .4572, .6096]:
                for rr in [c['gmr_m'], c['diameter_m']/2]:
                    radius_error = max(radius_error, abs(radius_product(rr, n, s) - reference.bundle_radius(rr, n, s)))
        for g in geometries:
            for n in map(int, str(g['allowed_bundle_counts']).split(';')):
                for nc in [1, 2, 4]:
                    length = 17000. * nc
                    e = forward(c, length, nc, n, g['gmd_nominal_m'], g['bundle_spacing_m'], g['nominal_kv'])
                    old = reference.electrical(c, length, nc, n, g['gmd_nominal_m'], g['bundle_spacing_m'], base_kv=g['nominal_kv'])
                    forward_error = max(forward_error, *(abs(e[key]-old[key]) for key in ['r_pu','x_pu','b_pu']))
                    inferred = inverse_gmd(c, e['x_pu']/e['r_pu'], n, g['bundle_spacing_m'])
                    inverse_error = max(inverse_error, abs(inferred-g['gmd_nominal_m']))
                    phase_current = 420.
                    sub_current = phase_current / (nc*n)
                    material_loss = 3*nc*n*sub_current**2*e['rsub']*length/1e6
                    base_current = BASE*1000/(math.sqrt(3)*g['nominal_kv'])
                    electrical_loss = BASE*e['r_pu']*(phase_current/base_current)**2
                    joule_error = max(joule_error, abs(material_loss-electrical_loss))
                    checks += 1
    assert max(radius_error,forward_error,inverse_error,joule_error)<1e-10

    recommendation = json.loads(recommendation_path.read_text())
    R, X, B = recommendation['accepted_R_X_B_pu']
    assert [R,X,B] == [.02,.0147,0.] and recommendation['nominal_kV']==345
    ratio = X/R
    g = next(row for row in geometries if row['nominal_kv']==345)
    rows = []
    for c in catalog:
        for nb in [2,3,4]:
            for spacing in [g['bundle_spacing_min_m'],g['bundle_spacing_m'],g['bundle_spacing_max_m']]:
                required = inverse_gmd(c, ratio, nb, spacing)
                at_min = forward(c, 1., 1, nb, g['gmd_min_m'], spacing, 345)
                at_max = forward(c, 1., 1, nb, g['gmd_max_m'], spacing, 345)
                rows.append(dict(catalog_id=c['catalog_id'],bundle_count=nb,bundle_spacing_m=spacing,
                    required_GMD_m=required,GMD_min_m=g['gmd_min_m'],GMD_max_m=g['gmd_max_m'],
                    target_X_over_R=ratio,minimum_X_over_R=at_min['x_pu']/at_min['r_pu'],
                    maximum_X_over_R=at_max['x_pu']/at_max['r_pu'],
                    inferred_length_nc1_m=R*at_min['zbase']*nb/at_min['rsub'],
                    inferred_length_nc4_m=4*R*at_min['zbase']*nb/at_min['rsub'],
                    geometry_feasible=g['gmd_min_m']<=required<=g['gmd_max_m']))
    grid = pd.DataFrame(rows)
    assert not grid.geometry_feasible.any()
    # The minimum is attained at minimum GMD and maximum bundle spacing, so
    # the failure is continuous over the declared spacing interval, not merely
    # a missed point in the three-value search grid.
    minimum_row = grid.loc[grid.minimum_X_over_R.idxmin()].to_dict()
    assert minimum_row['bundle_spacing_m']==g['bundle_spacing_max_m']
    no_geo = reference.inverse_candidates(R,X,B,345,catalog,g,tuple(range(1,65)),1e12,1e-6)
    assert no_geo==[]
    grid_path = OUT/'parent224_declared_catalog_feasibility.csv'
    grid.to_csv(grid_path,index=False)

    # A deliberately out-of-policy catalogue expansion demonstrates why an
    # exact R/X match alone is not a sufficient voltage-class design screen.
    # These real small ACSR catalogue entries are NOT admitted as candidates.
    small=[]
    allowed_names={'Turkey','Swan','Swanate','Sparrow','Sparate','Robin','Raven','Quail','Pigeon','Penguin'}
    for line in source_text.read_text(encoding='utf-8').splitlines():
        fields=re.split(r'\s{2,}',line.strip())
        if len(fields)!=15 or fields[0] not in allowed_names or '%' in fields[10]:
            continue
        small.append(dict(catalog_id='DIAGNOSTIC_ONLY_ACSR_'+fields[0],size=fields[1],diameter_m=float(fields[6])*.0254,
            r_ac25_ohm_per_m=float(fields[8])/304.8,r_ac75_ohm_per_m=float(fields[9])/304.8,
            r_ac200_ohm_per_m=float('nan'),gmr_m=float(fields[12])*.3048,reference_temperature_c=75.))
    assert len(small)==10
    counter=[]
    for c in small:
        for nb in [2,3,4]:
            for spacing in [.3048,.4572,.6096]:
                distance=inverse_gmd(c,ratio,nb,spacing)
                if 7<=distance<=14:
                    length=R*345**2/BASE*nb/r_at(c,75.)
                    e=forward(c,length,1,nb,distance,spacing,345)
                    assert abs(e['r_pu']-R)<1e-12 and abs(e['x_pu']-X)<1e-12
                    counter.append(dict(catalog_id=c['catalog_id'],size=c['size'],diameter_m=c['diameter_m'],
                        bundle_count=nb,circuits=1,bundle_spacing_m=spacing,gmd_m=distance,length_m=length,
                        inferred_b_pu=e['b_pu'],admitted=False,
                        reason='outside_predeclared_transmission_candidate_catalog;345kV_surface_gradient_corona_mechanical_design_not_checked'))
    counter_path=OUT/'parent224_small_conductor_counterexamples_NOT_ADMITTED.csv'
    pd.DataFrame(counter).to_csv(counter_path,index=False)

    # Explicit demonstration of the uncoupled identical-circuit ambiguity.
    con=next(c for c in catalog if c['catalog_id']=='PRYSMIAN_ACSR_DRAKE_795_0_26_7')
    degenerate=[]
    for nc in [1,2,3,4]:
        e=forward(con,50000*nc,nc,2,10.2,.4572,345)
        degenerate.append(dict(circuits=nc,bundle_count=2,length_m=50000*nc,r_pu=e['r_pu'],x_pu=e['x_pu'],
            b_pu=e['b_pu'],phase_ampacity_multiplier_at_same_subconductor_ampacity=nc*2,
            current_per_subconductor_at_1000A_phase_series=1000/(nc*2)))
    assert np.ptp([x['r_pu'] for x in degenerate])<1e-12 and np.ptp([x['x_pu'] for x in degenerate])<1e-12
    degeneracy_path=OUT/'same_R_X_different_circuits_length_charging.csv'
    pd.DataFrame(degenerate).to_csv(degeneracy_path,index=False)
    assignments=pd.read_csv(assignment_path)
    overhead=assignments[assignments.thermal_overhead_eligible.astype(str).str.lower().eq('true')]
    preserved=overhead.original_R_X_preserved.astype(str).str.lower().eq('true')
    assert len(overhead)==186 and int(preserved.sum())==128
    sources=[dict(publisher='PowerWorld',url='https://www.powerworld.com/WebHelp/Content/MainDocumentation_HTML/Transmission_Line_Parameter_Calculator.htm',
                  supports='Forward conductor/tower/length/base inputs and R/X/B methods; local version2 PDF printed13-14 contains the formulas.'),
             dict(publisher='Prysmian',url='https://na.prysmian.com/sites/na.prysmian.com/files/media/documents/TransPowr%C2%AE%20ACSR%20Bare%20Overhead%20Conductor%20%28US%29.pdf',
                  supports='Manufacturer diameter, GMR and AC resistance temperature points; page3 was visually inspected; small conductor entries are not voltage-class qualification.')]
    assert before==[record(p) for p in paths]
    report=dict(passed=True,created_utc=datetime.now(timezone.utc).isoformat(),
        scope='Independent nominal-pi R/X conductor inverse mathematics and synthetic acceptance review; no model, source case or prior artifact edited',
        installed_asset_identity_required_for_synthetic_eligibility=False,geographic_chord_required=False,
        fresh_electrical_or_thermal_solve_run=False,internal_interface_observations_read=False,
        independent_forward_inverse_current_cases=checks,max_errors=dict(bundle_product_radius_m=radius_error,forward_parameter_pu=forward_error,
            inverse_GMD_m=inverse_error,Joule_identity_MW=joule_error),
        equations=dict(R='Rpu = rsub(T) L / (nc nb Zbase)',X='Xpu = omega 2e-7 ln(GMD/GMRb) L / (nc Zbase)',
            B='Bpu = nc omega [2 pi epsilon0 / ln(GMD/rbundle)] L Zbase',
            ratio='X/R = nb omega 2e-7 ln(GMD/GMRb) / rsub(T)',
            inverse_GMD='GMRb exp[(X/R) rsub(T)/(nb omega 2e-7)]',
            inverse_length='L = Rpu Zbase nc nb/rsub(T)',
            current='Isub = Iseries_phase/(nc nb); Ibase_A = baseMVA*1000/(sqrt(3)*basekV)',
            loss='P_MW = 3 nc nb Isub^2 rsub L/1e6 = baseMVA Rpu |Iseries_pu|^2'),
        identifiability=dict(R_X_uniquely_identify_conductor=False,parallel_circuits_can_repair_ratio=False,
            length_and_circuit_tradeoff='At fixed conductor, bundle and GMD, same R/X permits L proportional to nc; B then scales as nc^2 and ampacity as nc.',
            temperature='Reference conductor temperature is an explicit inversion assumption, not determined by R/X.',
            charging='Trusted positive B supplies an additional constraint; source B=0 may mean omitted/net model charging and is not evidence for zero geometric capacitance.',
            mutual='Equations assume transposed, identical uncoupled parallel circuits; unequal or mutually coupled circuits need a separate primitive model.',
            long_line='R/X here are integrated nominal-pi series parameters. Long-line corrected equivalent-pi R/X are not interchangeable without conversion.'),
        parent224=dict(target_R_X_B_pu=[R,X,B],target_X_over_R=ratio,geometry_GMD_interval_m=[7,14],
            declared_catalog_size=len(catalog),bundle_counts=[2,3,4],spacing_interval_m=[.3048,.6096],
            feasible_without_geographic_or_meaningful_length_limit=False,checked_circuits_1_through_64=True,
            minimum_achievable_X_over_R=minimum_row['minimum_X_over_R'],minimum_ratio_candidate=minimum_row,
            maximum_required_GMD_over_declared_candidates_m=float(grid.required_GMD_m.max()),
            ratio_shortfall_fraction=1-ratio/minimum_row['minimum_X_over_R'],
            counterexamples_outside_declared_catalog=len(counter),universal_physical_impossibility_claimed=False,
            recommendation='Keep the released network R/X unchanged and leave224 without an accepted plain-OH thermal realization under the declared catalog. Do not add resistance or series compensation to manufacture a match.'),
        legacy_overhead_provenance=dict(total=186,imported_or_source_design_R_X_preserved=128,prior_engineering_R_X_redesigned=58,
            interpretation='An inverse fit to current redesigned R/X validates internal consistency of the synthetic engineering choice; it does not independently recover the original imported impedance.'),
        acceptance_metrics=[
            'Declare catalog, frequency, baseMVA/kV, reference temperature, geometry, positive integer circuit/bundle choices and electrical-length bounds before examining loading or interface errors.',
            'Accept only finite positive parameters whose independently recomputed R and X match each runtime section within relative1e-8 or absolute1e-10pu, whichever is larger; report both residuals.',
            'Use manufacturer resistance interpolation only inside its temperature domain and check geometry against physical radius as well as GMR.',
            'Preserve original/current R/X and provenance tier; no silent fallback redesign earns an inverse-inference label.',
            'Report predicted geometric B, preserved model B and mismatch separately; B mismatch may remain a qualification on a one-way series-heating screen, never an exact R/X/B claim.',
            'Keep all credible alternatives or summarize ampacity/current/length sensitivity; do not select circuit count by eliminating overload or matching interface observations.',
            'Current must use recovered original runtime phasors and actual voltage base, with no gamma lift; material and electrical I-squared-R loss must agree.',
            'Only one selected realization per parent per screen; alternative candidates are not parallel installed circuits. Homogeneous numerical sections must forward-match separately.',
            'Known cable/device/transformer technology remains outside bare-overhead equations; missing installed identity by itself is not an exclusion.',
            'An out-of-catalog tiny conductor fit requires an independent voltage/corona/mechanical design screen before transmission-study eligibility; exact R/X alone does not establish reasonableness.'
        ],primary_sources=sources,dependencies=before+[record(Path(__file__).resolve())],
        outputs=[record(p) for p in [grid_path,counter_path,degeneracy_path]])
    target=OUT/'inverse_physics_review.json'
    target.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['passed','independent_forward_inverse_current_cases','max_errors','parent224','legacy_overhead_provenance']},indent=2))


if __name__=='__main__':
    main()
