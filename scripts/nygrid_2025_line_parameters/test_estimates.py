"""Independent guards for source interpretation and applied estimate scope.

These tests use source values, CSV outputs and the frozen MAT case directly.
They do not call build_estimates or its line_physics calculation functions.
Passing verifies arithmetic/provenance, not the installed equipment or 2025
physical accuracy of an assumed operating model.
"""
from pathlib import Path
import csv
import hashlib
import json
import math
import unittest
import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'output/nygrid_2025_line_parameters'
EST = OUT/'estimates'
F84 = 'CV:PV_CV_F84'
Y17 = 'DOVER:CV_DOVER_Y17'
LM = 'DOVER:DOVER_LM_398'
FIELDS = ['r_pu','x_pu','b_pu','rate_a_mva','rate_b_mva','rate_c_mva']

def csvrows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as file:
        return list(csv.DictReader(file))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class ParameterEstimateReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.basis = json.loads((EST/'engineering_basis.json').read_text())
        cls.applied = csvrows(EST/'parameter_estimates.csv')
        cls.project = {(r['asset_key'],r['field']):r for r in csvrows(OUT/'project_source_register.csv')}
        cls.dover = csvrows(EST/'Dover_line_only_estimates_not_applied.csv')
        cls.oldreg = {r['branch_key']:r for r in csvrows(ROOT/'output/nygrid_2025_downstate/network/branch_register.csv')}
        cls.frozen = loadmat(ROOT/'output/nygrid_2025_downstate/network/network_cases.mat',simplify_cells=True)['refined_2025_case']['branch']

    def close(self, actual, expected, label='', rel=2e-12, absolute=1e-14):
        self.assertTrue(math.isclose(float(actual),float(expected),rel_tol=rel,abs_tol=absolute),f'{label}: {actual} != {expected}')

    def test_source_bindings_year_and_rating_units(self):
        p=self.project
        self.assertEqual(p[F84,'energized_date']['value'],'2019-07-28')
        self.assertEqual(self.basis['F84_energized_date'],'2019-07-28')
        self.assertIn('relative_to_frozen2019_model',self.basis['scope'])
        self.assertEqual(p[F84,'conductor']['value'],'Mallard 795 ACSS')
        self.assertEqual(p[F84,'subconductors_per_phase']['value'],'2')
        self.close(p[F84,'bundle_spacing']['value'],18)
        self.close(p[F84,'length']['value'],14.6)
        for key in [Y17,LM]:
            self.assertEqual(p[key,'summer_thermal_rating_table']['unit'],'A')
            self.close(p[key,'summer_thermal_rating_table']['value'],2220)
        self.close(p[LM,'length_CT']['value'],5.3)
        self.assertEqual(p[LM,'subconductors_per_phase_CT']['value'],'1')
        self.assertEqual(p['DOVER:PAR','series_impedance']['value'],'unresolved')

    def test_artifact_hashes_current_and_no_observations_in_dependencies(self):
        for row in self.basis['dependencies']+self.basis['outputs']:
            self.assertEqual(sha(ROOT/row['path']),row['sha256'],row['path'])
            self.assertFalse(any(s in row['path'].lower() for s in ['interface_observ','observed_interface','flowgate_score','hourly_actual']),row['path'])
        self.assertFalse(self.basis['internal_interface_observations_used'])

    def test_f84_independent_imperial_units_and_nominal_pi(self):
        # Public manufacturer Mallard/ACSS entries are 0.0253 and 0.0359
        # ohm/kft at75/200C, GMR0.0389ft, diameter1.140in. Work in source
        # imperial units before converting, independent of the SI helper.
        r95_per_kft = 0.0253+(95-75)/(200-75)*(0.0359-0.0253)
        r_ohm = r95_per_kft*(14.6*5.28)/2
        pair_feet = [31,math.hypot(31,17),math.hypot(31,14)]
        gmd_ft = math.prod(pair_feet)**(1/3)
        ds_ft = math.sqrt(.0389*1.5)
        cap_radius_ft = math.sqrt((1.140/24)*1.5)
        length_m = 14.6*5280*.3048
        x_ohm = 2*math.pi*60*(2e-7)*math.log(gmd_ft/ds_ft)*length_m
        capacitance = 2*math.pi*8.8541878128e-12/math.log(gmd_ft/cap_radius_ft)*length_m
        b_siemens = 2*math.pi*60*capacitance
        zbase = 345**2/100
        nominal = next(r for r in self.applied if r['full191_branch_key']==F84 and r['scenario_name']=='engineering_nominal')
        for name,value in [('r_pu',r_ohm/zbase),('x_pu',x_ohm/zbase),('b_pu',b_siemens*zbase)]:
            self.close(nominal[name],value,name)
        self.close(self.basis['F84_estimates'][0]['r_ohm'],1.040533824)
        self.close(self.basis['F84_estimates'][0]['charging_mvar_at_nominal_kv'],100*float(nominal['b_pu']))
        # B is total nominal-pi charging, not charging per endpoint.
        self.close(0.5*100*float(nominal['b_pu']),6.072470009611746)
        self.close(float(nominal['rate_a_mva']),1323)
        self.close(math.sqrt(3)*345*2214/1000,self.basis['F84_rating_from_current_mva'])
        self.assertEqual(float(nominal['rate_b_mva']),0)
        self.assertEqual(float(nominal['rate_c_mva']),0)

    def test_sensitivity_geometry_source_and_expected_directions(self):
        rows={r['scenario_name']:r for r in self.basis['F84_estimates']}
        n=rows['engineering_nominal'];low=rows['geometry_spacing_80pct'];high=rows['geometry_spacing_120pct']
        self.assertLess(low['x_pu'],n['x_pu']);self.assertLess(n['x_pu'],high['x_pu'])
        self.assertGreater(low['b_pu'],n['b_pu']);self.assertGreater(n['b_pu'],high['b_pu'])
        ground=rows['ground_image_30ft']
        self.close(min(p[1] for p in ground['geometry_m']),30*.3048)
        self.assertIn('not_route_average_sag',ground['geometry_basis'])
        self.assertGreater(ground['b_pu'],n['b_pu'])
        for item in rows.values():
            self.close(item['r_pu'],n['r_pu'])
            self.assertEqual(item['conductor_temperature_c'],95)
        self.assertIn('not_confidence_intervals',self.basis['uncertainty_policy'])

    def test_only_f84_and_staten_are_changed_from_frozen_model(self):
        keys={F84,Y17,LM,'RCC:CABLE:QUEENS','RCC:CABLE:BROOKLYN','RCC:CABLE:STATEN'}
        self.assertEqual(len(self.applied),24)
        self.assertEqual({r['full191_branch_key'] for r in self.applied},keys)
        for row in self.applied:
            key=row['full191_branch_key'];index=int(self.oldreg[key]['model_branch_row'])-1
            original=self.frozen[index,2:8]
            values=np.array([float(row[k]) for k in FIELDS])
            if key==F84:
                self.assertIn('not_verified_terminal_limited_facility_rating',row['rating_scope'])
            elif key=='RCC:CABLE:STATEN':
                np.testing.assert_array_equal(values[2:],original[2:])
                self.close(values[0],original[0]*9.4/9.2)
                self.close(values[1],original[1]*9.4/9.2)
            else:
                np.testing.assert_array_equal(values,original)

    def test_dover_segments_and_parallel_conductor_metadata(self):
        self.assertEqual(len(self.dover),36)
        groups={}
        for row in self.dover:
            self.assertEqual(row['applied_to_network'],'False')
            self.assertEqual(row['includes_PAR_series_impedance'],'False')
            self.assertIn('not_asbuilt',row['geometry_status'])
            group=(float(row['temperature_c']),float(row['adjacent_phase_spacing_ft']))
            groups.setdefault(group,{})[row['section']]=row
        self.assertEqual(len(groups),9)
        for group,rows in groups.items():
            y,ny,ct,combined=[rows[k] for k in ['Y17_NY_line_only','398_NY_line_only','398_CT_line_only','Dover_LongMountain_composite_line_only']]
            for row,length,count in [(y,.30,2),(ny,3.13,2),(ct,5.3,1)]:
                self.close(row['length_miles'],length)
                self.assertEqual(int(row['subconductors_per_phase']),count)
            self.close(combined['length_miles'],8.43)
            for field in ['r_pu','x_pu','b_pu','r_ohm','x_ohm','b_siemens','length_m']:
                self.close(combined[field],float(ny[field])+float(ct[field]),field)
            self.assertEqual(combined['parallel_subconductors_per_phase'],'section_specific_see_component_rows')
            self.assertEqual(combined['subconductors_per_phase'],'2_NY;1_CT')

    def test_dover_resistance_temperature_and_bundle_are_independently_correct(self):
        for row in self.dover:
            if row['section']=='Dover_LongMountain_composite_line_only':continue
            temp=float(row['temperature_c'])
            is_ct=row['section']=='398_CT_line_only'
            r75,r200=(.0103,.0141) if is_ct else (.0253,.0359)
            rac=r75+(temp-75)/125*(r200-r75)
            resistance=rac*float(row['length_miles'])*5.28/(1 if is_ct else 2)
            self.close(row['r_ohm'],resistance,row['section'])

    def test_cable_and_operating_rating_claims_remain_qualified(self):
        matches=csvrows(EST/'circuit_conductor_matches.csv')
        for row in matches:
            if row['branch_key'].startswith('RCC:'):
                self.assertEqual(row['catalog_match'],'no_unique_installed_conductor_match')
        self.assertFalse(self.basis['rating_is_current_operational_facility_rating'])
        self.assertIn('not_applied_until_PAR_series_impedance',self.basis['Dover_policy'])
        self.assertIn('qualified_historical_analog',self.basis['cable_policy'])


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ParameterEstimateReview)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    checked=[EST/'engineering_basis.json',EST/'parameter_estimates.csv',EST/'Dover_line_only_estimates_not_applied.csv',EST/'circuit_conductor_matches.csv',OUT/'project_source_register.csv',Path(__file__),Path(__file__).with_name('build_estimates.py'),Path(__file__).with_name('line_physics.py')]
    review=dict(passed=result.wasSuccessful(),reviewer='independent_project_source_review',tests_run=result.testsRun,
        failures=[str(x[0]) for x in result.failures],errors=[str(x[0]) for x in result.errors],
        scope='source interpretation, unit conversions, bundle arithmetic, frozen-model change boundary, declared uncertainty and commissioning year',
        physical_validation_of_installed_equipment=False,
        actual_2025_operating_temperature_or_PAR_state_established=False,
        independent_observations_used=False,
        resolved_findings=['Ground-image height changed from unsupported38ft source label to sourced30ft minimum-clearance sensitivity.','Dover composite bundle metadata made section-specific instead of inheriting CT single-conductor count.'],
        remaining_limitations=['F84 uses95C design-temperature resistance, not an observed annual operating temperature.','F84 route-average geometry, installed manufacturer/core grade and terminal facility rating remain unverified.','Dover line-only estimates exclude unresolved PAR series impedances and operating taps and are not applied.','RCC electrical parameters remain historical analogs; Staten length update does not certify its conductor.'],
        checked_files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in checked])
    validation=OUT/'validation';validation.mkdir(exist_ok=True)
    (validation/'parameter_source_review.json').write_text(json.dumps(review,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
