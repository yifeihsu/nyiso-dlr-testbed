"""Named estimates must remain subsets of the independent zone totals."""
import unittest
import numpy as np
import pandas as pd
from build_compact_named_generation_priors import named_subsets, SOURCES, OUT


class NamedPriorTests(unittest.TestCase):
    def frames(self):
        paths=[SOURCES/'epa/epa_generation_hourly.csv',SOURCES/'nonfossil/named_renewable_priors.csv',
               OUT/'zonal_generation_priors.csv',OUT/'statewide_reconciliation.csv']
        return [pd.read_csv(p,dtype={'unit_id':str}) for p in paths]

    def test_real_source_subsets_and_no_historical_new_units(self):
        e,w,z,s=self.frames();d=named_subsets(e,w,z,s)
        self.assertEqual(len(d),20)
        self.assertTrue(d.coverage_qualified.all())
        self.assertTrue(d.subset_of_zone_prior.all())
        self.assertFalse(d.observed_plant_net_generation.any())
        merged=d.merge(z[['scenario_id','zone','prior_benchmark_mw']],on=['scenario_id','zone'],suffixes=('_named','_zone'))
        self.assertTrue((merged.prior_benchmark_mw_named<=merged.prior_benchmark_mw_zone+1e-7).all())

    def test_online_missing_gross_is_unqualified(self):
        e,w,z,s=self.frames();ix=e.index[(e.facility_id==57185)&(e.vintage==2025)][0]
        sid=e.loc[ix,'scenario_id'];e.loc[ix,'gross_clock_hour_average_mw']=np.nan;e.loc[ix,'operating_time_hours']=1
        d=named_subsets(e,w,z,s);c=d[(d.scenario_id==sid)&(d.zone=='G')].iloc[0]
        self.assertFalse(c.coverage_qualified);self.assertTrue(np.isnan(c.prior_benchmark_mw))

    def test_offline_blank_is_explicit_estimate(self):
        e,w,z,s=self.frames();ix=e.index[(e.facility_id==57185)&(e.vintage==2025)][0]
        sid=e.loc[ix,'scenario_id'];e.loc[ix,'gross_clock_hour_average_mw']=np.nan;e.loc[ix,'operating_time_hours']=0
        d=named_subsets(e,w,z,s);c=d[(d.scenario_id==sid)&(d.zone=='G')].iloc[0]
        self.assertTrue(c.coverage_qualified);self.assertGreaterEqual(c.inferred_offline_zero_prior_units,1)
        self.assertFalse(c.observed_plant_net_generation)

    def test_duplicate_cricket_unit_rejected(self):
        e,w,z,s=self.frames();extra=e[(e.facility_id==57185)&(e.vintage==2025)].iloc[[0]]
        with self.assertRaises(AssertionError):named_subsets(pd.concat([e,extra]),w,z,s)

    def test_named_wind_not_larger_than_parent_or_double_scaled(self):
        e,w,z,s=self.frames();at=w.index[w.vintage==2025][0]
        wrong=w.copy();wrong.loc[at,'prior_public_mw']=1e6
        with self.assertRaises(AssertionError):named_subsets(e,wrong,z,s)
        wrong=w.copy();wrong.loc[at,'prior_benchmark_mw']*=2
        with self.assertRaises(AssertionError):named_subsets(e,wrong,z,s)


if __name__=='__main__':unittest.main()
