"""Independent unit, multiplicity, and passivity checks for engineering maps."""
from pathlib import Path
import math
import unittest
import numpy as np
import pandas as pd
from scipy.io import loadmat
import line_equivalents as le

ROOT=Path(__file__).resolve().parents[3]


class EngineeringEquivalents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=pd.read_csv(ROOT/'output/nygrid_2025_ac_system/engineering/thermal_conductors.csv')
        cls.conductor=cls.catalog.loc[(cls.catalog.family=='ACSS')&(cls.catalog.code_word=='Mallard')].iloc[0].to_dict()

    def test_regular_bundle_geometry_against_explicit_distances(self):
        gmr=self.conductor['gmr_m'];spacing=.4572
        for n in [2,3,4,5,6]:
            radius=spacing/(2*np.sin(np.pi/n))
            points=radius*np.exp(2j*np.pi*np.arange(n)/n)
            expected=(gmr*np.prod(abs(points[0]-points[1:])))**(1/n)
            self.assertAlmostEqual(le.bundle_radius(gmr,n,spacing),expected,places=14)

    def test_parallel_circuits_at_fixed_route_length(self):
        one=le.electrical(self.conductor,50000.,1,2,10.)
        three=le.electrical(self.conductor,50000.,3,2,10.)
        self.assertAlmostEqual(three['r_pu'],one['r_pu']/3)
        self.assertAlmostEqual(three['x_pu'],one['x_pu']/3)
        self.assertAlmostEqual(three['b_pu'],one['b_pu']*3)

    def test_multiplicity_cannot_repair_X_R(self):
        one=le.electrical(self.conductor,20000.,1,2,10.)
        four=le.electrical(self.conductor,80000.,4,2,10.)
        self.assertAlmostEqual(four['r_pu'],one['r_pu'])
        self.assertAlmostEqual(four['x_pu'],one['x_pu'])
        self.assertAlmostEqual(four['b_pu'],one['b_pu']*16)

    def test_phase_bundle_and_parallel_circuit_Joule_identity(self):
        length=81234.;circuits=3;bundle=4;phase_current=1723.
        e=le.electrical(self.conductor,length,circuits,bundle,12.)
        branch_loss=3*phase_current**2*e['r_ohm']
        subconductor=phase_current/(circuits*bundle)
        conductor_loss=3*circuits*bundle*subconductor**2*le.resistance(self.conductor,95.)*length
        self.assertAlmostEqual(branch_loss,conductor_loss,places=8)

    def test_manufacturer_R_interpolation_without_extrapolation(self):
        expected=(self.conductor['r_ac75_ohm_per_m']+(self.conductor['r_ac200_ohm_per_m']-self.conductor['r_ac75_ohm_per_m'])*20/125)
        self.assertAlmostEqual(le.resistance(self.conductor,95.),expected,places=16)
        acsr=self.catalog.loc[self.catalog.family=='ACSR'].iloc[0].to_dict()
        for temp in [24.,76.]:
            with self.assertRaises(ValueError):le.resistance(acsr,temp)

    def test_reject_nonphysical_multiplicity_geometry(self):
        for n in [0,1.5]:
            with self.assertRaises(ValueError):le.electrical(self.conductor,10000.,n,2,10.)
        with self.assertRaises(ValueError):le.electrical(self.conductor,10000.,1,2,.001)

    def test_no_gamma_in_physical_study_current_or_impedance(self):
        e=le.electrical(self.conductor,23496.4224,1,2,10.182226556367471)
        self.assertAlmostEqual(e['r_pu'],.0008742145129174543,places=14)
        volts=345.;p_mw=100.
        phase_current=p_mw*1000/(math.sqrt(3)*volts)
        self.assertAlmostEqual(phase_current,167.34790411293404,places=9)

    def test_heterogeneous_Dover_series_composition(self):
        s=pd.read_csv(ROOT/'output/nygrid_2025_ac_system/branches/thermal_segments.csv')
        d=s.loc[s.branch_row==413]
        self.assertEqual(len(d),2);self.assertEqual(set(d.bundle_count),{1,2})
        m=loadmat(ROOT/'output/nygrid_2025_ac_system/branches/engineering_overlay.mat',simplify_cells=True)['branch_reference']
        np.testing.assert_allclose(d[['reference_r_pu','reference_x_pu','reference_b_pu']].sum(),m[412,2:5],rtol=0,atol=1e-12)
        phase=1000.;loss=sum(3*int(x.circuits)*int(x.bundle_count)*(phase/(int(x.circuits)*int(x.bundle_count)))**2*x.r_ref_ohm_per_m_per_subconductor*x.segment_length_m for x in d.itertuples())
        self.assertAlmostEqual(loss,3*phase**2*m[412,2]*345**2/100,places=8)

    def test_cable_parallel_units_and_charging(self):
        c=pd.read_csv(ROOT/'output/nygrid_2025_ac_system/engineering/cable_candidates.csv').iloc[0].to_dict()
        one=le.cable_electrical(c,5000.,1,c['phase_gmd_reference_m'],c['nominal_kv'])
        two=le.cable_electrical(c,5000.,2,c['phase_gmd_reference_m'],c['nominal_kv'])
        self.assertAlmostEqual(two['r_pu'],one['r_pu']/2)
        self.assertAlmostEqual(two['x_pu'],one['x_pu']/2)
        self.assertAlmostEqual(two['b_pu'],2*one['b_pu'])
        expected_b=2*math.pi*60*c['capacitance_f_per_m']*5000*c['nominal_kv']**2/100
        self.assertAlmostEqual(one['b_pu'],expected_b)

    def test_complete_energized_mapping_and_true_terminal_ampere_ledger(self):
        d=pd.read_csv(ROOT/'output/nygrid_2025_ac_system/branches/branch_assignments.csv')
        active=d.loc[d.active_in_any_selected2025_state]
        self.assertTrue((active[['applied_r_pu','applied_x_pu','applied_rate_a_mva']]>0).all().all())
        self.assertTrue((active.applied_b_pu>=0).all())
        self.assertEqual(active.total_terminal_current_limit_from_a.notna().sum(),291)
        f=d.loc[d.branch_row==391].iloc[0]
        self.assertEqual(f.source_static_rating_mva,1323.)
        self.assertEqual(f.total_terminal_current_limit_from_a,4000.)
        self.assertAlmostEqual(f.equipment_ceiling_mva,math.sqrt(3)*345*4000/1000)
        self.assertFalse(d.current_gamma_lift.any())

    def test_composite_capacity_is_independent_of_total_path_X(self):
        d=pd.read_csv(ROOT/'output/nygrid_2025_ac_system/branches/branch_assignments.csv')
        review=pd.read_csv(ROOT/'output/nygrid_2025_ac_system/engineering/voltage_changing_classification_review.csv').set_index('branch_row')
        selected=d[d.classification=='composite_voltage_changing_equivalent']
        self.assertEqual(len(selected),65)
        for row in selected.itertuples():
            expected=review.loc[row.branch_row]
            self.assertAlmostEqual(row.equipment_ceiling_mva,expected.recommended_composite_nominal_mva_proxy)
            self.assertAlmostEqual(row.total_terminal_current_limit_from_a,expected.recommended_composite_from_A)
            self.assertAlmostEqual(row.total_terminal_current_limit_to_a,expected.recommended_composite_to_A)
        old=loadmat(ROOT/'output/nygrid_2025_ac_system/branches/revision_02_complete_mapping/engineering_overlay.mat',simplify_cells=True)['branch_reference']
        new=loadmat(ROOT/'output/nygrid_2025_ac_system/branches/engineering_overlay.mat',simplify_cells=True)['branch_reference']
        np.testing.assert_array_equal(new[:,2:5],old[:,2:5])


if __name__=='__main__':unittest.main()
