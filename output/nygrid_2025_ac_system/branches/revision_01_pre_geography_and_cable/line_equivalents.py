"""Positive-sequence synthetic overhead conductor equivalents in SI units.

Circuit multiplicity and bundle multiplicity are different integers. These
equations describe transposed, uncoupled parallel circuits without earth
images or series compensation. They do not identify installed conductors.
"""
import math
import numpy as np

OMEGA = 2 * math.pi * 60
EPSILON_0 = 8.8541878128e-12


def require(value, message):
    if not value:
        raise ValueError(message)


def resistance(conductor, temperature_c):
    ts = [25., 75.]
    rs = [float(conductor['r_ac25_ohm_per_m']), float(conductor['r_ac75_ohm_per_m'])]
    hot = float(conductor.get('r_ac200_ohm_per_m', float('nan')))
    if math.isfinite(hot):
        ts.append(200.); rs.append(hot)
    require(ts[0] <= temperature_c <= ts[-1], 'AC resistance cannot be extrapolated')
    return float(np.interp(temperature_c, ts, rs))


def bundle_radius(single_radius_m, bundle_count, adjacent_spacing_m):
    require(isinstance(bundle_count, (int, np.integer)) and 1 <= bundle_count <= 8,
            'Bundle count must be an integer1..8')
    require(single_radius_m > 0 and adjacent_spacing_m > 2*single_radius_m,
            'Nonphysical conductor or bundle spacing')
    if bundle_count == 1:
        return float(single_radius_m)
    circle = adjacent_spacing_m/(2*math.sin(math.pi/bundle_count))
    return (single_radius_m*bundle_count*circle**(bundle_count-1))**(1/bundle_count)


def electrical(conductor, length_m, circuits, bundle_count, gmd_m,
               bundle_spacing_m=.4572, temperature_c=None, base_kv=345., base_mva=100.):
    require(isinstance(circuits, (int, np.integer)) and circuits >= 1,
            'Circuit count must be a positive integer')
    require(length_m > 0 and base_kv > 0 and base_mva > 0, 'Invalid line/base dimensions')
    temperature_c = float(conductor['reference_temperature_c']) if temperature_c is None else float(temperature_c)
    rsub = resistance(conductor, temperature_c)
    gm = bundle_radius(float(conductor['gmr_m']), bundle_count, bundle_spacing_m)
    capradius = bundle_radius(float(conductor['diameter_m'])/2, bundle_count, bundle_spacing_m)
    require(gmd_m > max(gm, capradius), 'Phase separation must exceed bundle radii')
    x_per_m = OMEGA*2e-7*math.log(gmd_m/gm)
    c_per_m = 2*math.pi*EPSILON_0/math.log(gmd_m/capradius)
    zbase = base_kv**2/base_mva
    r = rsub*length_m/(circuits*bundle_count)
    x = x_per_m*length_m/circuits
    b = circuits*OMEGA*c_per_m*length_m
    require(min(r,x,b) > 0, 'Passive overhead equivalent requires positive R/X/B')
    return dict(r_pu=r/zbase, x_pu=x/zbase, b_pu=b*zbase,
                r_ohm=r, x_ohm=x, b_siemens=b, zbase_ohm=zbase,
                r_ref_ohm_per_m_per_subconductor=rsub,
                reactance_ohm_per_m_per_circuit=x_per_m,
                capacitance_f_per_m_per_circuit=c_per_m,
                bundle_gmr_m=gm,bundle_capacitance_radius_m=capradius)


def geometry_for_ratio(conductor, ratio, bundle_count, bundle_spacing_m):
    require(ratio > 0, 'X/R must be positive for an inverse conductor realization')
    rsub = resistance(conductor, float(conductor['reference_temperature_c']))
    exponent = ratio*rsub/(bundle_count*OMEGA*2e-7)
    if exponent > 40:
        return float('inf')
    return bundle_radius(float(conductor['gmr_m']),bundle_count,bundle_spacing_m)*math.exp(exponent)


def segment(conductor, branch_row, branch_key, segment_id, length_m, circuits,
            bundle_count, base_kv, gmd_m, bundle_spacing_m, basis):
    e = electrical(conductor,length_m,circuits,bundle_count,gmd_m,bundle_spacing_m,base_kv=base_kv)
    result = dict(branch_row=int(branch_row),branch_key=str(branch_key),segment_id=str(segment_id),
        segment_length_m=float(length_m),circuits=int(circuits),bundle_count=int(bundle_count),
        base_kv=float(base_kv),catalog_id=str(conductor['catalog_id']),
        gmd_m=float(gmd_m),bundle_spacing_m=float(bundle_spacing_m),
        reference_temperature_c=float(conductor['reference_temperature_c']),
        temperature_min_c=float(conductor['temperature_min_c']),temperature_max_c=float(conductor['temperature_max_c']),
        diameter_m=float(conductor['diameter_m']),gmr_m=float(conductor['gmr_m']),
        r_ac25_ohm_per_m=float(conductor['r_ac25_ohm_per_m']),
        r_ac75_ohm_per_m=float(conductor['r_ac75_ohm_per_m']),
        r_ac200_ohm_per_m=float(conductor['r_ac200_ohm_per_m']),
        heat_capacity_j_m_k=float(conductor['heat_capacity_j_m_k']),
        emissivity=float(conductor['emissivity']),absorptivity=float(conductor['absorptivity']),
        reference_r_pu=e['r_pu'],reference_x_pu=e['x_pu'],reference_b_pu=e['b_pu'],
        r_ref_ohm_per_m_per_subconductor=e['r_ref_ohm_per_m_per_subconductor'],
        reactance_ohm_per_m_per_circuit=e['reactance_ohm_per_m_per_circuit'],
        capacitance_f_per_m_per_circuit=e['capacitance_f_per_m_per_circuit'],
        parameter_basis=basis,route_length_verified=False,installed_conductor_identified=False,
        current_gamma_lift=False,parallel_circuit_mutual_coupling_modeled=False,
        bare_overhead_thermal_model_applicable=True)
    return result


def inverse_candidates(r_pu, x_pu, b_pu, base_kv, catalog, geometry,
                       circuits_allowed=(1,2,3,4), max_length_m=1_000_000.):
    """Return finite exact-R/X candidates ranked without dispatch information.

    A positive legacy B helps choose integer parallel-circuit hypotheses, but
    the new AC overlay uses the candidate's geometric B. R=0 is not used to
    claim zero geographic line length or zero conductor resistivity.
    """
    if r_pu <= 0 or x_pu <= 0:
        return []
    zbase=base_kv**2/100
    bundles=[int(v) for v in str(geometry['allowed_bundle_counts']).split(';')]
    spacings=sorted(set(float(geometry[k]) for k in ['bundle_spacing_m','bundle_spacing_min_m','bundle_spacing_max_m']))
    results=[]
    for conductor in catalog:
        rsub=resistance(conductor,float(conductor['reference_temperature_c']))
        for nb in bundles:
            for spacing in spacings:
                gmd=geometry_for_ratio(conductor,x_pu/r_pu,nb,spacing)
                if not float(geometry['gmd_min_m']) <= gmd <= float(geometry['gmd_max_m']):
                    continue
                for nc in circuits_allowed:
                    length=r_pu*zbase*nc*nb/rsub
                    if not 5 <= length <= max_length_m:
                        continue
                    e=electrical(conductor,length,nc,nb,gmd,spacing,base_kv=base_kv)
                    require(abs(e['x_pu']-x_pu)<1e-10 and abs(e['r_pu']-r_pu)<1e-12,
                            'Inverse R/X reconstruction failed')
                    b_error=abs(math.log(e['b_pu']/b_pu)) if b_pu>0 else 0.
                    score=2*b_error+.15*(nc-1)+.04*abs(nb-float(geometry['default_bundle_count']))
                    score+=.03*abs(math.log(gmd/float(geometry['gmd_nominal_m'])))
                    score+=.005*abs(math.log(spacing/float(geometry['bundle_spacing_m'])))
                    results.append(dict(score=score,conductor=conductor,segment_length_m=length,circuits=nc,
                        bundle_count=nb,gmd_m=gmd,bundle_spacing_m=spacing,electrical=e,
                        parent_B_log_difference=b_error,derivation='exact_R_X_inverse_with_integer_circuit_search'))
    return sorted(results,key=lambda row:(row['score'],row['circuits'],row['conductor']['catalog_id'],row['bundle_count'],row['bundle_spacing_m']))


def fallback_candidate(r_pu,x_pu,base_kv,conductor,geometry,max_length_m):
    """Explicit synthetic redesign when no physical geometry matches legacy R/X.

    Keep X if its implied route length is inside the predeclared interval;
    otherwise use the nearest length boundary. No solver/loading input enters.
    """
    nb=int(geometry['default_bundle_count']);gmd=float(geometry['gmd_nominal_m']);spacing=float(geometry['bundle_spacing_m'])
    one=electrical(conductor,1.,1,nb,gmd,spacing,base_kv=base_kv)
    raw_length=x_pu/one['x_pu'] if x_pu>0 else 1000.
    length=float(np.clip(raw_length,5.,max_length_m))
    e=electrical(conductor,length,1,nb,gmd,spacing,base_kv=base_kv)
    return dict(score=None,conductor=conductor,segment_length_m=length,circuits=1,bundle_count=nb,
        gmd_m=gmd,bundle_spacing_m=spacing,electrical=e,parent_B_log_difference=None,
        derivation='synthetic_positive_R_X_B_redesign_from_nominal_geometry_and_X_implied_length',
        raw_X_implied_length_m=float(raw_length),length_clamped=bool(length!=raw_length))
