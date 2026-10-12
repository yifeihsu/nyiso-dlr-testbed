"""Independent arithmetic/scope review of the frozen revision2 branch ledger.

Does not import the assignment implementation or consume dispatch results.
The bundle self-GMD is calculated from explicit polygon vertex distances.
This checks the selected lumped-pi realization, not its distributed-line
accuracy, buried-cable ampacity, installed identity, or AC feasibility.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'output/nygrid_2025_ac_system'
FROZEN = BASE / 'branches/revision_02_complete_mapping'


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def record(path):
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path))


def check(ok, label):
    if not ok:
        raise AssertionError(label)


def close(a, b, label, tol=1e-10):
    err = float(np.max(np.abs(np.asarray(a, float)-np.asarray(b, float))))
    check(err < tol, f'{label}: error={err}')
    return err


def polygon_self_gmd(radius, n, spacing):
    if n == 1:
        return radius
    circle = spacing / (2 * math.sin(math.pi/n))
    vertices = [circle * np.exp(2j*math.pi*k/n) for k in range(n)]
    distances = [abs(vertices[i]-vertices[j]) if i != j else radius
                 for i in range(n) for j in range(n)]
    return math.exp(sum(math.log(x) for x in distances)/(n*n))


def main():
    branch = pd.read_csv(FROZEN/'branch_assignments.csv').set_index('branch_row', drop=False)
    oh = pd.read_csv(FROZEN/'thermal_segments.csv')
    cable = pd.read_csv(FROZEN/'cable_segments.csv')
    conductors = pd.read_csv(BASE/'engineering/thermal_conductors.csv').set_index('catalog_id')
    cables = pd.read_csv(BASE/'engineering/cable_candidates.csv').set_index('catalog_id')
    geometry = pd.read_csv(BASE/'engineering/geometry_defaults.csv').set_index('nominal_kv')
    equipment = json.loads((BASE/'engineering/synthetic_equipment_defaults.json').read_text())
    mat = loadmat(FROZEN/'engineering_overlay.mat', simplify_cells=True)
    source = loadmat(ROOT/'output/nygrid_2025_dover_parameters/network/x_nominal.mat', simplify_cells=True)
    pre = loadmat(ROOT/'output/nygrid_2025_line_parameters/overlays/engineering_nominal/full191_network_cases.mat', simplify_cells=True)
    ref = mat['branch_reference']
    original = source['full_case']['branch']
    check(ref.shape == (413, 13) and len(branch) == 413, 'Complete branch axis')
    check(branch.branch_key.is_unique, 'Unique branch identity')
    check(mat['baseMVA'] == 100, '100 MVA synthetic system')
    check(np.array_equal(np.asarray(mat['branch_keys']).astype(str), branch.branch_key.to_numpy(str)), 'MAT/CSV keys')
    close(ref[:,2:6], branch[['applied_r_pu','applied_x_pu','applied_b_pu','applied_rate_a_mva']], 'MAT/CSV parameters')
    close(ref[:,[0,1,8,9,11,12]], original[:,[0,1,8,9,11,12]], 'Preserve endpoints/taps/shift/angle limits')
    status = original[:,10].copy(); status[210] = 0
    check(np.array_equal(ref[:,10], status), 'Only original211 transfer-contract status override')
    check(np.array_equal(ref[:410], mat['pre_dover_branch_reference']), 'Pre-Dover matrix prefix')
    check(len(source['full_case']['bus']) == 192, 'Post-Dover full system buses')
    ever = original[:,10] > 0
    for state in ['refined_2025_pre_may_case','refined_2025_may21_case','refined_2025_may30_case']:
        check(len(pre[state]['bus']) == 191, 'Pre-Dover full system buses')
        ever[:410] |= pre[state]['branch'][:,10] > 0
    ever[210] = False
    check(np.array_equal(ever, branch.active_in_any_selected2025_state), 'Independent dated active union')
    check(ever.sum() == 339 and (~ever).sum() == 74, 'Active/provenance accounting')
    check((ref[ever,2:4] > 0).all() and (ref[ever,4] >= 0).all() and (ref[ever,5] > 0).all(), 'Passive finite active parameters')
    check((~branch.current_gamma_lift).all() and (~branch.parameter_gamma_transform).all(), 'No gamma transformations')
    check(branch.no_dispatch_or_interface_fit.all(), 'No dispatch fit claim')
    check((~branch.asbuilt_identity_qualified).all(), 'No invented installed identity')
    check(set(oh.branch_row) == set(branch.loc[branch.thermal_overhead_eligible,'branch_row']), 'Complete OH coverage')
    check(len(oh) == 187 and oh.branch_row.nunique() == 186 and len(cable) == 40, 'Physical realization counts')
    totals = {}
    maxerr = loss_error = 0.
    for s in oh.itertuples():
        b = branch.loc[s.branch_row]
        c = conductors.loc[s.catalog_id]
        g = geometry.loc[s.base_kv]
        n, nb = int(s.circuits), int(s.bundle_count)
        check(n == s.circuits and nb == s.bundle_count and 1 <= n <= 4 and 1 <= nb <= 4, 'Integer multiplicities')
        check(b.base_kv == b.to_base_kv and ref[s.branch_row-1,8] in [0,1], 'OH voltage and tap scope')
        if b.source_branch_row > 0:
            check(n == 1, 'Historical source individual circuit retained')
        if s.branch_row not in [391,393,413]:
            check(nb in map(int, str(g.allowed_bundle_counts).split(';')), 'Voltage-class bundle window')
            check(g.gmd_min_m <= s.gmd_m <= g.gmd_max_m, 'OH GMD window')
            check(b.length_min_m <= s.segment_length_m <= b.length_max_m, 'OH geographic length window')
        else:
            check(s.parameter_basis.startswith('source_design'), 'Source design anchor exception')
        check(g.bundle_spacing_min_m <= s.bundle_spacing_m <= g.bundle_spacing_max_m, 'Bundle spacing window')
        check(s.temperature_min_c <= s.reference_temperature_c <= s.temperature_max_c, 'Resistance temperature scope')
        ts, rs = [25.,75.], [c.r_ac25_ohm_per_m,c.r_ac75_ohm_per_m]
        if np.isfinite(c.r_ac200_ohm_per_m):
            ts.append(200.); rs.append(c.r_ac200_ohm_per_m)
        rsub = np.interp(s.reference_temperature_c,ts,rs)
        gm = polygon_self_gmd(c.gmr_m,nb,s.bundle_spacing_m)
        rc = polygon_self_gmd(c.diameter_m/2,nb,s.bundle_spacing_m)
        xpm = 2*math.pi*60*2e-7*math.log(s.gmd_m/gm)
        cpm = 2*math.pi*8.8541878128e-12/math.log(s.gmd_m/rc)
        zb = s.base_kv**2/100
        rxbc = np.array([rsub*s.segment_length_m/(n*nb)/zb,
                         xpm*s.segment_length_m/n/zb,
                         n*2*math.pi*60*cpm*s.segment_length_m*zb])
        maxerr=max(maxerr,close(rxbc,[s.reference_r_pu,s.reference_x_pu,s.reference_b_pu],f'OH row {s.branch_row}'))
        totals[s.branch_row] = totals.get(s.branch_row, np.zeros(3)) + rxbc
        i = 1234.5
        joule = 3*n*nb*(i/(n*nb))**2*rsub*s.segment_length_m
        lumped = 3*i*i*rxbc[0]*zb
        loss_error=max(loss_error,close(joule,lumped,'Three-phase Joule identity',tol=1e-7))
        check(not s.current_gamma_lift and s.bare_overhead_thermal_model_applicable, 'OH thermal boundary')
        amps = equipment['overhead_terminal_current_per_physical_circuit_A'][str(int(s.base_kv))]*n
        close(amps,b.total_terminal_current_limit_from_a,'Hardware amps independent of bundle count')
    for s in cable.itertuples():
        b = branch.loc[s.branch_row]; c = cables.loc[s.catalog_id]
        n = int(s.circuits)
        check(n == s.circuits and 1 <= n <= 4 and s.bundle_count == 1, 'Cable multiplicity')
        check(b.base_kv == b.to_base_kv and s.base_kv == c.nominal_kv, 'Cable voltage family')
        check(c.phase_gmd_min_m <= s.gmd_m <= c.phase_gmd_max_m, 'Cable geometry window')
        if b.source_branch_row > 0:
            check(n == 1, 'Cable source individual circuit retained')
        if not s.source_route_length_used:
            check(b.length_min_m <= s.segment_length_m <= b.length_max_m, 'Cable length window')
        else:
            miles={'RCC:CABLE:QUEENS':6.,'RCC:CABLE:BROOKLYN':1.,'RCC:CABLE:STATEN':9.4}[s.branch_key]
            close(s.segment_length_m,miles*1609.344,'Documented/assumed RCC route')
        zb=s.base_kv**2/100
        rp=c.conductor_rho20_ohm_m_assumed/c.conductor_area_m2*(1+c.conductor_alpha20_per_c_assumed*70)*c.ac_resistance_factor_assumed
        xp=2*math.pi*60*2e-7*math.log(s.gmd_m/(.7788*c.conductor_diameter_m/2))
        vals=[rp*s.segment_length_m/n/zb,xp*s.segment_length_m/n/zb,2*math.pi*60*c.capacitance_f_per_m*s.segment_length_m*n*zb]
        maxerr=max(maxerr,close(vals,[s.reference_r_pu,s.reference_x_pu,s.reference_b_pu],f'Cable row {s.branch_row}'))
        totals[s.branch_row]=np.array(vals)
        check(not s.overhead_IEEE738_applicable and not s.buried_thermal_model_validated, 'Cable thermal boundary')
        close(n*1000,b.total_terminal_current_limit_from_a,'Cable declared hardware ampere ceiling')
    composition_error=0.
    for row, val in totals.items():
        composition_error=max(composition_error,close(val,ref[row-1,2:5],f'Branch segment composition {row}'))
    line_rows=set(oh.branch_row)|set(cable.branch_row)
    terminal=mat['terminal_current_limit_A']
    check(set(np.flatnonzero(np.isfinite(terminal).all(axis=1))+1)==line_rows,'All and only physical line rows have terminal amperes')
    for row in line_rows:
        b=branch.loc[row]
        close(terminal[row-1],[b.total_terminal_current_limit_from_a,b.total_terminal_current_limit_to_a],'MAT/CSV terminal A')
        close(b.equipment_ceiling_mva,math.sqrt(3)*b.base_kv*b.total_terminal_current_limit_from_a/1000,'Nominal-kV MVA proxy',tol=1e-8)
    active_equipment=branch.loc[branch.active_in_any_selected2025_state & ~branch.branch_row.isin(line_rows)]
    outside=[]
    for b in active_equipment.itertuples():
        check(b.equipment_parallel_banks in equipment['transformer_integer_parallel_bank_counts'], 'Integer equipment banks')
        check(b.equipment_per_bank_mva in equipment['transformer_per_bank_MVA_pool'], 'Finite MVA pool')
        close(b.equipment_ceiling_mva,b.equipment_parallel_banks*b.equipment_per_bank_mva,'Equipment aggregate MVA')
        own=math.hypot(b.applied_r_pu,b.applied_x_pu)*b.equipment_ceiling_mva/100
        close(own,b.equipment_own_base_z_pu,'Equipment own-base impedance')
        if not (.04 <= own <= .25):
            outside.append(b.branch_row)
            check(b.equipment_equivalent_not_literal_nameplate,'Out-of-window equipment explicitly nonliteral')
    check(outside == [132,142,161,166], 'Known qualified own-base exceptions')
    f84=branch.loc[391]
    check(f84.source_static_rating_mva==1323 and f84.source_static_rating_kind=='conductor_design_summer_normal','F84 source rating role')
    check(f84.equipment_ceiling_mva != 1323 and f84.total_terminal_current_limit_from_a == 4000,'F84 separate hardware limit')
    check(branch.loc[[52,208,213],'classification'].eq('station_reactance_equivalent').all(),'Finite station reactances excluded from OH')
    for b in branch.loc[branch.original_R_X_preserved.eq(True)].itertuples():
        close([b.original_r_pu,b.original_x_pu],[b.applied_r_pu,b.applied_x_pu],'Exact-R/X preservation claim')
    construction=json.loads((FROZEN/'branch_engineering_receipt.json').read_text())
    for item in construction['dependencies']+construction['outputs']:
        source_path=ROOT/item['path']
        archived=FROZEN/source_path.name
        if archived.exists():source_path=archived
        check(sha(source_path)==item['sha256'],'Frozen construction file hash binding: '+item['path'])
    paths=[FROZEN/p for p in ['branch_assignments.csv','thermal_segments.csv','cable_segments.csv','engineering_overlay.mat','branch_engineering_receipt.json']]
    paths += [BASE/'engineering'/p for p in ['thermal_conductors.csv','cable_candidates.csv','geometry_defaults.csv','synthetic_equipment_defaults.json']]
    paths.append(Path(__file__))
    long_lines=branch.loc[branch.branch_row.isin(line_rows)&branch.route_length_m.gt(120*1609.344),['branch_row','branch_key','route_length_m','applied_b_pu']].to_dict('records')
    report=dict(passed=True,scope='historical frozen revision2 arithmetic and classification; current revision3 is separately checked by composite_revision_independent_review.json',
        created_utc=datetime.now(timezone.utc).isoformat(),branch_records=413,ever_active=339,inactive_provenance=74,
        overhead_branches=186,overhead_segments=187,cable_realizations=40,non_overhead_equipment=len(active_equipment),
        max_independent_formula_error_pu=maxerr,max_composition_error_pu=composition_error,
        max_three_phase_joule_identity_error_w=loss_error,equipment_own_base_exceptions=outside,
        terminal_ampere_limits_bound_to_all_226_line_rows=True,F84_source_conductor_rating_separated=True,
        current_gamma_lift=False,impedance_gamma_transform=False,full_system_buses_pre_post=[191,192],
        limitations=['Synthetic realizations are not installed-asset identification.',
            'The pi branch uses total route R/X/B; distributed-parameter or cascaded-pi correction is not validated for long corridors.',
            'Cable static current ceilings are declared study values; burial, sheath and soil thermal ratings remain unvalidated.',
            'Four equipment rows exceed the declared own-base impedance window and remain explicitly nonliteral equivalents.',
            'Conductor/reference resistance consistency does not establish coupled temperature equilibrium or AC feasibility.'],
        overhead_corridors_over_120_miles=long_lines,checked_files=[record(p) for p in paths])
    target=BASE/'engineering/revision02_branch_mapping_review.json'
    target.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['checked_files','overhead_corridors_over_120_miles']},indent=2))


if __name__=='__main__':
    main()
