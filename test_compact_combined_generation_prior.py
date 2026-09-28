"""Independent/adversarial accounting tests for public generation priors."""
import copy
import unittest

import numpy as np
import pandas as pd

from build_compact_combined_generation_prior import combine


def fixture():
    meta=dict(scenario_id='TEST',vintage=2025,timestamp_local_requested='2025-07-15 18:00',
              timestamp_utc_requested='2025-07-15T22:00:00Z',scale_factor_gamma=.25)
    ep=[]
    for facility,unit,zone,gross,eligible in [(1,'01','A',100,True),(2,'GT1','K',300,True),
                                            (3,'1','J',1000,False),(4,'1','C',np.nan,True),
                                            (5,'1','UNMAPPED',0,True)]:
        ep.append(dict(**meta,facility_id=facility,unit_id=unit,zone=zone,gross_clock_hour_average_mw=gross,
                       grid_fossil_share_eligible=eligible,interval_start_utc='2025-07-15T22:00:00Z',
                       interval_end_utc='2025-07-15T23:00:00Z'))
    nf=[];sf=[]
    totals={'Nuclear':40,'Hydro':20,'Wind':30,'Other Renewables':10,
            'Dual Fuel':80,'Natural Gas':120,'Other Fossil Fuels':0}
    for fuel,total in totals.items():
        sf.append(dict(**meta,fuel_category=fuel,window_policy='hour_beginning',coverage_qualified=True,
                       duration_weighted_generation_mw=total,window_start_local='2025-07-15 18:00:00',
                       window_end_local='2025-07-15 19:00:00'))
        if fuel in ['Nuclear','Hydro','Wind','Other Renewables']:
            for z in 'ABCDEFGHIJK':
                public=total if z=='B' else 0
                nf.append(dict(**meta,zone=z,fuel_category=fuel,window_policy='hour_beginning',coverage_qualified=True,
                               prior_public_mw=public,prior_benchmark_mw=public*.25))
    return pd.DataFrame(ep),pd.DataFrame(nf),pd.DataFrame(sf)


class CombinedPriorTests(unittest.TestCase):
    def test_known_mass_balance_and_exactly_one_gamma(self):
        z,s=combine(*fixture());z=z.set_index('zone')
        self.assertAlmostEqual(z.prior_public_mw.sum(),300)
        self.assertAlmostEqual(z.prior_benchmark_mw.sum(),75)
        self.assertEqual(z.loc['A','prior_public_mw'],50)
        self.assertEqual(z.loc['B','prior_public_mw'],100)
        self.assertEqual(z.loc['K','prior_public_mw'],150)
        self.assertAlmostEqual(s.iloc[0].statewide_total_reconciliation_factor,.5)
        self.assertFalse(z.zonal_generation_observed.any());self.assertFalse(z.internal_interfaces_used_in_prior.any())

    def test_combined_fossil_labels_do_not_assume_unit_fuel_split(self):
        e,n,s=fixture();expected=combine(e,n,s)[0]
        s.loc[s.fuel_category=='Dual Fuel','duration_weighted_generation_mw']=0
        s.loc[s.fuel_category=='Natural Gas','duration_weighted_generation_mw']=10
        s.loc[s.fuel_category=='Other Fossil Fuels','duration_weighted_generation_mw']=190
        pd.testing.assert_frame_equal(combine(e,n,s)[0],expected)

    def test_missing_gross_is_recorded_not_measured_zero(self):
        z,s=combine(*fixture())
        self.assertEqual(s.iloc[0].eligible_missing_gross_rows,1)
        self.assertTrue(s.iloc[0].coverage_qualified)
        self.assertFalse(s.iloc[0].geographic_coverage_complete)
        self.assertFalse(z.source_net_generation_complete.any())

    def test_unmapped_positive_prevents_qualification(self):
        e,n,s=fixture();e.loc[e.facility_id==5,'gross_clock_hour_average_mw']=17
        z,t=combine(e,n,s)
        self.assertFalse(t.iloc[0].coverage_qualified)
        self.assertEqual(t.iloc[0].eligible_unmapped_present_gross_mw,17)
        self.assertTrue(z.prior_public_mw.isna().all())

    def test_explicitly_excluded_chp_does_not_become_grid_fossil_share(self):
        e,n,s=fixture();e.loc[e.facility_id==3,'zone']='UNMAPPED'
        z,t=combine(e,n,s)
        self.assertTrue(t.iloc[0].coverage_qualified)
        self.assertEqual(t.iloc[0].excluded_reported_gross_mw,1000)
        self.assertEqual(z.loc[z.zone=='J','fossil_prior_public_mw'].iloc[0],0)

    def test_duplicate_epa_unit_hour_rejected_after_facility_normalization(self):
        e,n,s=fixture();d=e.iloc[[0]].copy();d['facility_id']='1'
        with self.assertRaisesRegex(AssertionError,'Duplicate EPA'):combine(pd.concat([e,d]),n,s)

    def test_epa_unit_identifier_cannot_be_blank_or_whitespace_aliased(self):
        for bad in ['',None,' 01']:
            e,n,s=fixture();e.loc[0,'unit_id']=bad
            with self.assertRaisesRegex(AssertionError,'unit identity'):combine(e,n,s)

    def test_offsetting_nonfossil_errors_do_not_evade_conservation(self):
        e,n,s=fixture()
        for fuel,delta in [('Nuclear',10),('Hydro',-10)]:
            mask=(n.zone=='B')&(n.fuel_category==fuel)
            n.loc[mask,'prior_public_mw']+=delta;n.loc[mask,'prior_benchmark_mw']+=delta*.25
        with self.assertRaisesRegex(AssertionError,'fuel total'):combine(e,n,s)

    def test_double_applied_benchmark_scale_rejected(self):
        e,n,s=fixture();n['prior_benchmark_mw']*=.25
        with self.assertRaisesRegex(AssertionError,'gamma incorrectly'):combine(e,n,s)

    def test_negative_gamma_rejected_even_when_sources_agree(self):
        data=fixture()
        for d in data:d['scale_factor_gamma']=-1
        with self.assertRaisesRegex(AssertionError,'scale gamma'):combine(*data)

    def test_timestamp_alias_cannot_mix_different_hours(self):
        e,n,s=fixture();e.loc[0,'timestamp_utc_requested']='2025-07-15T21:00:00Z'
        with self.assertRaisesRegex(AssertionError,'timestamp/vintage'):combine(e,n,s)
        e,n,s=fixture();e['interval_start_utc']='2025-07-15T21:00:00Z'
        with self.assertRaisesRegex(AssertionError,'interval'):combine(e,n,s)

    def test_wrong_p63_bin_rejected(self):
        e,n,s=fixture();s['window_start_local']='2025-07-15 17:00:00'
        with self.assertRaisesRegex(AssertionError,'P63 interval'):combine(e,n,s)

    def test_invalid_or_stale_eligibility_flags_fail_closed(self):
        e,n,s=fixture();e['grid_fossil_share_eligible']=e.grid_fossil_share_eligible.astype(object)
        e.loc[0,'grid_fossil_share_eligible']='unknown'
        with self.assertRaisesRegex(AssertionError,'qualification flag'):combine(e,n,s)
        e,n,s=fixture();s.loc[0,'coverage_qualified']=False
        z,t=combine(e,n,s);self.assertFalse(t.iloc[0].coverage_qualified);self.assertTrue(z.prior_public_mw.isna().all())

    def test_duplicate_nonfossil_zone_identity_rejected(self):
        e,n,s=fixture();n.loc[0,'zone']='C'
        with self.assertRaises(AssertionError):combine(e,n,s)


if __name__=='__main__':unittest.main(verbosity=2)
