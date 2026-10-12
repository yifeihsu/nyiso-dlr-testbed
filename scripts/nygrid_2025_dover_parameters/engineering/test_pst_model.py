"""PST physical invariants and model-control tests; no network power-flow run."""
import hashlib
import json
import math
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

import pst_model as m


class PSTEngineeringTests(unittest.TestCase):
    def test_conditional_8_degree_reference_is_phasor_consistent(self):
        x=m.conditional_reactance()
        state=m.load_phasor(0,x)
        self.assertAlmostEqual(state['leakage_load_angle_deg'],8.,places=12)
        self.assertAlmostEqual(state['internal_voltage_magnitude_pu'],1/math.cos(math.radians(8)),places=12)
        vload=1+0j;vsource=(1+1j*x)*np.exp(-1j*math.radians(40))
        powers=m.port_powers(vsource,vload,0,x,shift_deg=-40,base_mva=750)
        self.assertAlmostEqual(np.angle(vload/vsource,deg=True),32.,places=12)
        self.assertAlmostEqual(-powers[1].real,750.,places=10)
        self.assertAlmostEqual(powers.real.sum(),0.,places=10)

    def test_general_PF_and_voltage_conditions_are_not_unique_impedance(self):
        inferred=[]
        for v,pf,sign in [(1,1,1),(.95,.95,1),(1.05,.9,-1)]:
            x=m.conditional_reactance(receiving_v_pu=v,power_factor=pf,reactive_sign=sign,r_pu=.003)
            phi=m.load_phasor(.003,x,v,1,pf,sign)['leakage_load_angle_deg']
            self.assertAlmostEqual(phi,8.,places=12);inferred.append(x)
        self.assertGreater(max(inferred)-min(inferred),.01)

    def test_sin8_corresponds_to_different_receiving_voltage_and_MVA(self):
        x=math.sin(math.radians(8));v=math.cos(math.radians(8))
        state=m.load_phasor(0,x,receiving_v_pu=v,load_mva_pu=v)
        self.assertAlmostEqual(abs(state['load_current']),1.,places=12)
        self.assertAlmostEqual(state['internal_voltage_magnitude_pu'],1.,places=12)
        self.assertAlmostEqual(state['leakage_load_angle_deg'],8.,places=12)
        self.assertNotAlmostEqual(x,m.conditional_reactance(),places=3)

    def test_base_conversion_preserves_physical_ohms(self):
        x=m.conditional_reactance()
        self.assertAlmostEqual(m.change_base(x),.01873877796031886,places=15)
        for base in [100.,1500.,750.]:
            converted=m.change_base(x,to_mva=base)
            self.assertAlmostEqual(converted*345**2/base,x*345**2/750,places=11)

    def test_two_parallel_banks_halve_X_not_double_it(self):
        x=m.change_base(m.conditional_reactance())
        eq=m.parallel_dc_equivalent([x,x],[0.,0.])
        self.assertAlmostEqual(eq['x_pu'],x/2,places=15)
        each=m.dc_power(1,0,0,x)
        self.assertAlmostEqual(2*each,m.dc_power(1,0,eq['shift_deg'],eq['x_pu']),places=11)

    def test_unequal_bank_angles_preserve_total_and_expose_circulation(self):
        x=m.change_base(m.conditional_reactance())
        eq=m.parallel_dc_equivalent([x,x],[-3.,3.])
        actual=np.array([m.dc_power(0,0,angle,x) for angle in [-3.,3.]])
        self.assertAlmostEqual(actual.sum(),m.dc_power(0,0,eq['shift_deg'],eq['x_pu']),places=11)
        self.assertGreater(abs(actual[0]),250.)
        # Aggregate transfer zero cannot hide individual-bank overload.
        self.assertFalse(m.necessary_p_screen(actual,np.array([750.,750.]),.3).any())

    def test_advancing_load_side_uses_negative_MATPOWER_shift(self):
        x=m.change_base(m.conditional_reactance())
        powers=m.port_powers(1,1,0,x,shift_deg=-2,base_mva=100)
        self.assertGreater(powers[0].real,0)
        self.assertGreater(m.dc_power(0,0,-2,x),0)
        self.assertAlmostEqual(powers.real.sum(),0,places=10)

    def test_nominal_zero_phase_is_not_zero_impedance(self):
        x=m.change_base(m.conditional_reactance())
        y=m.pst_y(0,x,0)
        self.assertAlmostEqual(abs(y[0,0]),1/x,places=9)
        self.assertGreater(m.dc_power(1,0,0,x),0)

    def test_complex_tap_passivity_and_copper_loss_identity(self):
        for r in [0.,.002]:
            for shift in [-40.,0.,40.]:
                tap=.98;y=m.pst_y(r,.02,shift,tap)
                eigen=np.linalg.eigvalsh((y+y.conj().T)/2)
                self.assertGreaterEqual(eigen.min(),-1e-10)
                v=np.array([1.02*np.exp(1j*.08),.97*np.exp(-1j*.03)])
                s=m.port_powers(*v,r,.02,shift,tap,base_mva=100)
                a=tap*np.exp(1j*math.radians(shift));series=(v[0]/a-v[1])/complex(r,.02)
                self.assertAlmostEqual(s.real.sum(),100*r*abs(series)**2,places=9)

    def test_P34_sign_and_target_phase_reconstruction(self):
        x=m.change_base(m.conditional_reactance());gamma=.30012075175285535
        raw=np.array([-323.,0.,205.]);target=-gamma*raw
        phase=m.dc_shift_for_target(2.,-.4,target,x)
        recovered=m.dc_power(2.,-.4,phase,x)
        np.testing.assert_allclose(recovered,target,rtol=0,atol=1e-12)
        self.assertTrue(m.necessary_p_screen(target,np.full(3,750.),gamma).all())

    def test_scaling_angles_and_targets_together_preserves_DC_similarity(self):
        x=m.change_base(m.conditional_reactance());gamma=.30012075175285535
        phase=m.dc_shift_for_target(2.,-.4,250.,x)
        scaled=m.dc_shift_for_target(2*gamma,-.4*gamma,250*gamma,x)
        self.assertAlmostEqual(scaled,phase*gamma,places=12)

    def test_series_line_parallel_bank_schur_affine_identity(self):
        x=m.change_base(m.conditional_reactance());xl1=.00015;xl2=.0051
        C=np.array([[1,-1,0,0],[0,1,-1,0],[0,1,-1,0],[0,0,1,-1]],float)
        weights=100/np.array([xl1,x,x,xl2]);shifts=np.deg2rad([0.,-2.,-2.,0.])
        B=C.T@(weights[:,None]*C);phase=C.T@(-weights*shifts)
        r=[0,3];i=[1,2]
        reduced=B[np.ix_(r,r)]-B[np.ix_(r,i)]@np.linalg.solve(B[np.ix_(i,i)],B[np.ix_(i,r)])
        reduced_phase=phase[r]-B[np.ix_(r,i)]@np.linalg.solve(B[np.ix_(i,i)],phase[i])
        expected_weight=100/(xl1+x/2+xl2)
        np.testing.assert_allclose(reduced,expected_weight*np.array([[1,-1],[-1,1]]),atol=1e-9,rtol=0)
        np.testing.assert_allclose(reduced_phase,-expected_weight*math.radians(-2)*np.array([1,-1]),atol=1e-9,rtol=0)

    def test_mixed_NY_CT_line_sections_are_summed_once(self):
        path=m.ROOT/'output/nygrid_2025_line_parameters/estimates/Dover_line_only_estimates_not_applied.csv'
        table=pd.read_csv(path)
        choose=table.loc[(table.temperature_c==95)&(table.adjacent_phase_spacing_ft==25.6)].set_index('section')
        composite=choose.loc['Dover_LongMountain_composite_line_only']
        for key in ['r_pu','x_pu','b_pu','length_miles']:
            self.assertAlmostEqual(composite[key],choose.loc['398_NY_line_only',key]+choose.loc['398_CT_line_only',key],places=12)
        self.assertEqual(int(choose.loc['398_NY_line_only','subconductors_per_phase']),2)
        self.assertEqual(int(choose.loc['398_CT_line_only','subconductors_per_phase']),1)

    def test_nonpassive_or_inconsistent_inputs_fail(self):
        for args in [dict(delta_deg=0),dict(power_factor=0),dict(receiving_v_pu=-1),dict(r_pu=-.001)]:
            with self.assertRaises(ValueError):m.conditional_reactance(**args)
        with self.assertRaises(ValueError):m.pst_y(-.1,.1)
        with self.assertRaises(ValueError):m.parallel_dc_equivalent([.1,0],[0,0])


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PSTEngineeringTests))
    report=dict(passed=result.wasSuccessful(),tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        scope='phasor_unit_control_passivity_parallel_and_section_composition_invariants;no_network_PF_or_measured_tap_claim',
        engineering_code_sha256=m.sha(Path(m.__file__)),test_code_sha256=m.sha(Path(__file__)))
    m.OUT.mkdir(parents=True,exist_ok=True)
    (m.OUT/'engineering_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
