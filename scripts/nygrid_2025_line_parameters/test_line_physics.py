"""Independent physics invariants for engineering estimates, not an as-built gate.

References: PowerWorld TransLineCalc printed13-17, and EPRI OpenDSS-C's
potential-coefficient earth-image calculation. No interface-flow observations.
"""
from __future__ import annotations
import hashlib
import itertools
import json
import math
from pathlib import Path
import unittest

import numpy as np

import line_physics as physics

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/nygrid_2025_line_parameters/validation/physics_validation.json"


def fixture(**changes):
    values = dict(length_m=14.6*1609.344, conductor_diameter_m=1.140*.0254,
        conductor_gmr_m=.0389*.3048, ac_resistance_ohm_per_m=.026996/304.8,
        bundle_spacing_m=.4572, bundle_count=2,
        phase_xy_m=np.array([[-8.,24.],[3.,34.],[12.,19.]]),frequency_hz=60.,base_kv=345.,base_mva=100.)
    values.update(changes); return values


def independent_transposed_capacitance(phase_xy_m, capacitance_radius_m):
    """Build three conductor image potentials, transpose, then excite a mode.

    This matrix construction is independent of the implementation's averaged
    scalar logarithms. It validates the declared mean-potential approximation,
    not detailed untransposed multi-circuit or grounded-shield behavior.
    """
    points = np.asarray(phase_xy_m, float)
    potential = np.zeros((3,3))
    for i in range(3):
        for j in range(3):
            image = points[j] * [1.,-1.]
            distance_image = float(np.linalg.norm(points[i]-image))
            direct = capacitance_radius_m if i==j else float(np.linalg.norm(points[i]-points[j]))
            potential[i,j] = math.log(distance_image/direct)/(2*math.pi*8.8541878128e-12)
    transpositions = [np.roll(np.eye(3), shift, axis=0) for shift in range(3)]
    mean = sum(p @ potential @ p.T for p in transpositions)/3
    sequence_voltage = np.exp(-2j*math.pi*np.arange(3)/3)
    charge = np.linalg.solve(mean,sequence_voltage)
    return float(np.real(np.vdot(sequence_voltage,charge)/3))


class LinePhysicsTests(unittest.TestCase):
    def test_catalog_interpolation_95_and_180_without_DC_alpha(self):
        self.assertAlmostEqual(physics.interpolate_resistance(95,[25,75,200],[.0212,.0253,.0359]),.026996/304.8,places=16)
        self.assertAlmostEqual(physics.interpolate_resistance(180,[25,75,200],[.0212,.0253,.0359]),.034204/304.8,places=16)
        with self.assertRaises(ValueError):
            physics.interpolate_resistance(95,[25,75],[.0219,.0262])

    def test_twin_resistance_is_two_parallel_subconductors_once(self):
        value=physics.overhead_transposed(**fixture())
        self.assertAlmostEqual(value['r_ohm'],1.040533824,places=12)
        self.assertAlmostEqual(value['r_pu'],.0008742145129174543,places=15)

    def test_phase_current_rating_not_multiplied_by_bundle_count(self):
        self.assertAlmostEqual(physics.design_mva_from_phase_current(2214,345),1323.,delta=.1)
        self.assertAlmostEqual(physics.design_mva_from_phase_current(3979,345),2377.68,delta=.01)

    def test_single_Bluebird_uses_full_resistance_and_own_GMR(self):
        args=fixture(bundle_count=1,bundle_spacing_m=None,conductor_diameter_m=1.762*.0254,
                     conductor_gmr_m=.0585*.3048,ac_resistance_ohm_per_m=.010908/304.8,length_m=5.3*1609.344)
        value=physics.overhead_transposed(**args)
        self.assertAlmostEqual(value['r_ohm'],.010908*5.28*5.3,places=12)
        self.assertAlmostEqual(value['bundle_gmr_m'],.0585*.3048,places=15)
        self.assertAlmostEqual(value['bundle_capacitance_radius_m'],1.762*.0254/2,places=15)

    def test_asymmetric_image_capacitance_matches_independent_matrix_mode(self):
        args=fixture();value=physics.overhead_transposed(**args)
        expected=independent_transposed_capacitance(args['phase_xy_m'],math.sqrt(args['conductor_diameter_m']/2*args['bundle_spacing_m']))
        self.assertAlmostEqual(value['capacitance_f_per_m']/expected,1.,places=12)

    def test_phase_permutations_and_horizontal_mirror_are_invariant(self):
        args=fixture();base=physics.overhead_transposed(**args)
        for order in itertools.permutations(range(3)):
            changed=physics.overhead_transposed(**fixture(phase_xy_m=args['phase_xy_m'][list(order)]))
            for field in ['r_ohm','x_ohm','b_siemens']:
                self.assertAlmostEqual(changed[field]/base[field],1.,places=12)
        mirrored=physics.overhead_transposed(**fixture(phase_xy_m=args['phase_xy_m']*[-1,1]))
        self.assertAlmostEqual(mirrored['b_siemens']/base['b_siemens'],1.,places=12)

    def test_height_to_infinity_matches_no_ground_formula(self):
        points=np.array([[-10.,1e8],[0.,1e8],[10.,1e8]])
        with_images=physics.overhead_transposed(**fixture(phase_xy_m=points))
        no_images=physics.overhead_transposed(**fixture(phase_xy_m=points,include_ground_images=False))
        self.assertAlmostEqual(with_images['capacitance_f_per_m']/no_images['capacitance_f_per_m'],1.,places=10)
        # Without image correction only relative phase coordinates matter.
        relative=physics.overhead_transposed(**fixture(phase_xy_m=points-[0,1e8],include_ground_images=False))
        self.assertAlmostEqual(relative['b_siemens']/no_images['b_siemens'],1.,places=12)

    def test_no_ground_capacitance_uses_physical_radius_not_GMR(self):
        args=fixture(include_ground_images=False);value=physics.overhead_transposed(**args)
        expected=2*math.pi*8.8541878128e-12/math.log(value['gmd_m']/math.sqrt(args['conductor_diameter_m']/2*args['bundle_spacing_m']))
        wrong=2*math.pi*8.8541878128e-12/math.log(value['gmd_m']/value['bundle_gmr_m'])
        self.assertAlmostEqual(value['capacitance_f_per_m']/expected,1.,places=13)
        self.assertGreater(abs(value['capacitance_f_per_m']/wrong-1),.005)

    def test_scale_all_geometry_preserves_dimensionless_ratios(self):
        args=fixture();a=physics.overhead_transposed(**args)
        for key in ['conductor_diameter_m','conductor_gmr_m','bundle_spacing_m','phase_xy_m']:args[key]*=3.5
        b=physics.overhead_transposed(**args)
        self.assertAlmostEqual(a['inductance_h_per_m']/b['inductance_h_per_m'],1.,places=12)
        self.assertAlmostEqual(a['capacitance_f_per_m']/b['capacitance_f_per_m'],1.,places=12)

    def test_length_frequency_and_base_scaling(self):
        base=physics.overhead_transposed(**fixture())
        twice=physics.overhead_transposed(**fixture(length_m=2*fixture()['length_m']))
        freq=physics.overhead_transposed(**fixture(frequency_hz=50))
        power=physics.overhead_transposed(**fixture(base_mva=200))
        for field in ['r_ohm','x_ohm','b_siemens']:self.assertAlmostEqual(twice[field]/base[field],2.,places=12)
        self.assertAlmostEqual(freq['x_ohm']/base['x_ohm'],50/60,places=12)
        self.assertAlmostEqual(freq['b_siemens']/base['b_siemens'],50/60,places=12)
        self.assertAlmostEqual(power['r_pu']/base['r_pu'],2.,places=12)
        self.assertAlmostEqual(power['x_pu']/base['x_pu'],2.,places=12)
        self.assertAlmostEqual(power['b_pu']/base['b_pu'],.5,places=12)

    def test_nominal_pi_charging_is_total_B_split_once(self):
        p=physics.overhead_transposed(**fixture());s=physics.nominal_pi_terminal_powers(p['r_pu'],p['x_pu'],p['b_pu'],1,1)
        expected=p['charging_mvar_at_nominal_kv']
        self.assertAlmostEqual(s['s_from'].real+s['s_to'].real,0.,places=12)
        self.assertAlmostEqual(-(s['s_from'].imag+s['s_to'].imag),expected,places=11)
        self.assertAlmostEqual(-s['s_from'].imag,expected/2,places=11)

    def test_two_terminal_real_power_loss_closes(self):
        p=physics.overhead_transposed(**fixture());vf=1.03*np.exp(1j*.06);vt=.99*np.exp(-1j*.03)
        s=physics.nominal_pi_terminal_powers(p['r_pu'],p['x_pu'],p['b_pu'],vf,vt)
        self.assertAlmostEqual(s['s_from'].real+s['s_to'].real,s['series_loss_mw'],places=9)

    def test_geometry_and_bundle_fail_closed(self):
        for edits in [dict(bundle_count=True),dict(bundle_count=3),dict(bundle_spacing_m=.001),
                      dict(phase_xy_m=[[0,0],[5,10],[10,10]]),dict(conductor_gmr_m=.1)]:
            with self.assertRaises(ValueError):physics.overhead_transposed(**fixture(**edits))


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(LinePhysicsTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    digest=lambda path:hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
    receipt=dict(passed=result.wasSuccessful(),tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        scope='independent physics invariants;no installed-line or network power-flow qualification',
        methods=['asymmetric_earth_image_potential_matrix_positive_sequence','height_to_infinity_limit',
                 'phase_permutation_and_geometry_scale_invariance','manufacturer_temperature_interpolation',
                 'single_vs_twin_parallel_resistance','per_unit_base_scaling','nominal_pi_total_charging_and_real_loss'],
        physics_code_sha256=digest(Path(physics.__file__)),test_code_sha256=digest(Path(__file__)),
        references=[{'path':'output/nygrid_2025_line_parameters/conductors/sources/powerworld_translinecalc_v2.pdf','printed_pages':'13-17'},
                    {'path':'output/nygrid_2025_line_parameters/conductors/sources/epri_LineConstants.cpp','lines':'107-127'}])
    OUTPUT.parent.mkdir(parents=True,exist_ok=True);OUTPUT.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
