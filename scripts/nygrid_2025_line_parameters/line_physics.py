"""Positive-sequence engineering estimates with explicit SI inputs.

These functions calculate line parameters from conductor/geometry assumptions;
they do not infer installed equipment from interface observations. The overhead
model is a transposed, single-conductor or twin-bundle approximation. It omits earth-return
loss, mutual coupling to adjacent circuits and detailed untransposed effects.
"""
from __future__ import annotations
import math
import numpy as np

EPS0 = 8.8541878128e-12
M_PER_MILE = 1609.344
M_PER_KFT = 304.8


def positive(name, value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(name+' must be finite and positive')
    return value


def base_impedance(kv, mva):
    """Three-phase base: line-to-line kV squared / three-phase MVA."""
    return positive('kV',kv)**2/positive('MVA',mva)


def interpolate_resistance(temperature_c, temperatures_c, ac_ohm_per_kft):
    temp = np.asarray(temperatures_c, float)
    resistance = np.asarray(ac_ohm_per_kft, float)
    if (temp.ndim != 1 or len(temp)<2 or temp.shape != resistance.shape
            or not np.isfinite(temp).all() or not np.isfinite(resistance).all()
            or np.any(np.diff(temp)<=0) or np.any(resistance<=0)
            or np.any(np.diff(resistance)<0)):
        raise ValueError('Invalid manufacturer resistance table')
    t = float(temperature_c)
    if not math.isfinite(t) or t < temp[0] or t > temp[-1]:
        raise ValueError('Resistance interpolation requires a temperature within the source table')
    return float(np.interp(t,temp,resistance))/M_PER_KFT


def overhead_transposed(*, length_m, conductor_diameter_m, conductor_gmr_m,
                        ac_resistance_ohm_per_m, phase_xy_m, bundle_count=2,
                        bundle_spacing_m=None, include_ground_images=True,
                        frequency_hz=60., base_kv=345., base_mva=100.):
    """Return total positive-sequence nominal-pi R/X/B and their SI basis.

    phase_xy_m gives three phase-bundle centers (horizontal position,height).
    The electrostatic earth-image correction uses transposed mean potential
    coefficients. R is per-phase series resistance; B is TOTAL line charging
    susceptance, to be split equally at the two nominal-pi terminals.
    """
    length=positive('length',length_m)
    diameter=positive('diameter',conductor_diameter_m)
    gmr=positive('GMR',conductor_gmr_m)
    rac=positive('AC resistance',ac_resistance_ohm_per_m)
    if bundle_count not in (1,2) or isinstance(bundle_count,bool):
        raise ValueError('Only explicit single or twin phase arrangements are supported')
    spacing=positive('bundle spacing',bundle_spacing_m) if bundle_count==2 else 0.
    freq=positive('frequency',frequency_hz)
    zbase=base_impedance(base_kv,base_mva)
    points=np.asarray(phase_xy_m,float)
    if (points.shape!=(3,2) or not np.isfinite(points).all()
            or (include_ground_images and np.any(points[:,1]<=0))):
        raise ValueError('Three finite phase centers, above ground for image corrections, are required')
    if (bundle_count==2 and spacing<=diameter) or gmr>=diameter/2:
        raise ValueError('Invalid sub-conductor geometry')
    distances=[float(np.linalg.norm(points[a]-points[b])) for a,b in [(0,1),(1,2),(2,0)]]
    if min(distances)<=max(spacing,diameter):
        raise ValueError('Phase bundles overlap or phase separation is unresolved')
    dm=float(np.prod(distances)**(1/3))
    ds=math.sqrt(gmr*spacing) if bundle_count==2 else gmr
    req=math.sqrt(diameter/2*spacing) if bundle_count==2 else diameter/2
    inductance_per_m=2e-7*math.log(dm/ds)
    if include_ground_images:
        self_mean=float(np.mean(np.log(2*points[:,1]/req)))
        mutual=[]
        for (a,b),d in zip([(0,1),(1,2),(2,0)],distances):
            image_distance=math.hypot(points[a,0]-points[b,0],points[a,1]+points[b,1])
            mutual.append(math.log(image_distance/d))
        potential_factor=self_mean-float(np.mean(mutual))
    else:
        potential_factor=math.log(dm/req)
    if inductance_per_m<=0 or potential_factor<=0:
        raise ValueError('Nonphysical sequence impedance/capacitance')
    capacitance_per_m=2*math.pi*EPS0/potential_factor
    omega=2*math.pi*freq
    r_ohm=rac*length/bundle_count
    x_ohm=omega*inductance_per_m*length
    b_siemens=omega*capacitance_per_m*length
    return dict(r_pu=r_ohm/zbase,x_pu=x_ohm/zbase,b_pu=b_siemens*zbase,
        r_ohm=r_ohm,x_ohm=x_ohm,b_siemens=b_siemens,zbase_ohm=zbase,
        length_m=length,frequency_hz=freq,parallel_subconductors_per_phase=bundle_count,
        gmd_m=dm,bundle_gmr_m=ds,bundle_capacitance_radius_m=req,
        inductance_h_per_m=inductance_per_m,capacitance_f_per_m=capacitance_per_m,
        r_ac_ohm_per_m_per_subconductor=rac,
        charging_mvar_at_nominal_kv=b_siemens*base_kv**2,
        capacitance_ground_image_correction=bool(include_ground_images),
        scope='transposed_overhead_engineering_estimate_not_asbuilt_test')


def overhead_twin_bundle(**kwargs):
    """Convenience wrapper fixing exactly two parallel sub-conductors."""
    if 'bundle_count' in kwargs:
        raise ValueError('Twin-bundle entrypoint fixes bundle_count=2')
    return overhead_transposed(bundle_count=2,**kwargs)


def design_mva_from_phase_current(phase_current_a, kv):
    # phase_current is the total current in the phase bundle, not the current
    # in one sub-conductor. Do not multiply the result by bundle count again.
    return math.sqrt(3)*positive('kV',kv)*positive('phase current',phase_current_a)/1000


def nominal_pi_terminal_powers(r_pu, x_pu, total_b_pu, vf, vt, base_mva=100.):
    """Independent two-terminal AC diagnostic using positive-into-line signs."""
    r=float(r_pu);x=positive('X',x_pu);b=float(total_b_pu)
    if not math.isfinite(r) or r<0 or not math.isfinite(b) or b<0:
        raise ValueError('Nonpassive line parameters')
    vf,vt=complex(vf),complex(vt)
    if not all(math.isfinite(v) for v in [vf.real,vf.imag,vt.real,vt.imag]):
        raise ValueError('Nonfinite terminal voltage')
    ys=1/complex(r,x)
    series=ys*(vf-vt)
    i_from=series+complex(0,b/2)*vf
    i_to=-series+complex(0,b/2)*vt
    return dict(s_from=base_mva*vf*np.conj(i_from),s_to=base_mva*vt*np.conj(i_to),
                series_loss_mw=base_mva*r*abs(series)**2)
