"""Synthetic integration guards; no observed or heldout interface data."""
import numpy as np
import unittest
from audit_compact_nyiso_time_alignment import integrate_hourly_samples


class TimeIntegrationTests(unittest.TestCase):
    def test_constant_signal_exact_all_conventions(self):
        r = integrate_hourly_samples(np.arange(0, 3601, 300), np.full(13, 17.5)).iloc[0]
        assert r.complete_coverage and r.coverage_seconds == 3600
        assert r.forward_sample_hold == r.backward_sample_hold == r.linear_between_samples == 17.5


    def test_ramp_independent_analytic_integrals(self):
        t = np.arange(0, 3601, 300)
        r = integrate_hourly_samples(t, t / 3600).iloc[0]
        self.assertAlmostEqual(r.forward_sample_hold, 11 / 24)
        self.assertAlmostEqual(r.backward_sample_hold, 13 / 24)
        self.assertAlmostEqual(r.linear_between_samples, .5)


    def test_hour_end_sample_does_not_enter_forward_hold(self):
        t = np.arange(0, 3601, 300)
        r = integrate_hourly_samples(t, np.r_[np.zeros(12), 120]).iloc[0]
        assert r.forward_sample_hold == 0
        assert r.backward_sample_hold == 10
        assert r.linear_between_samples == 5


    def test_irregular_cadence_uses_duration_not_sample_average(self):
        t = np.r_[0, 60, np.arange(600, 3601, 600)]
        v = np.r_[60, np.zeros(len(t) - 1)]
        r = integrate_hourly_samples(t, v).iloc[0]
        assert r.forward_sample_hold == 1
        assert r.backward_sample_hold == 0
        assert r.linear_between_samples == .5


    def test_long_gap_cannot_be_counted_as_coverage(self):
        t = np.array([0, 300, 1500, 1800, 2100, 2400, 2700, 3000, 3300, 3600])
        r = integrate_hourly_samples(t, np.ones(len(t))).iloc[0]
        assert not r.complete_coverage and r.coverage_seconds == 2400 and r.rejected_gap_seconds == 1200
        assert np.isnan(r.forward_sample_hold) and np.isnan(r.linear_between_samples)


    def test_gap_crossing_hour_boundary_rejects_both_parts(self):
        t = np.r_[np.arange(0, 3301, 300), np.arange(4200, 7201, 300)]
        r = integrate_hourly_samples(t, np.ones(len(t)))
        assert r.coverage_seconds.tolist() == [3300, 3000]
        assert r.rejected_gap_seconds.tolist() == [300, 600]
        assert not r.complete_coverage.any()


    def test_partial_edges_never_extrapolated(self):
        t = np.arange(60, 7141, 300)
        r = integrate_hourly_samples(t, np.ones(len(t)))
        assert not r.complete_coverage.any()
        assert (r.source_span_seconds < 3600).all()
        assert r.forward_sample_hold.isna().all()


    def test_exact_ten_minute_gap_allowed(self):
        t = np.arange(0, 3601, 600)
        r = integrate_hourly_samples(t, np.ones(len(t))).iloc[0]
        assert r.complete_coverage and r.maximum_bracketing_gap_seconds == 600


    def test_invalid_samples_rejected(self):
        cases=[([0],[1]),([0,0],[1,2]),([1,0],[1,2]),([0,300],[1]),([0,float('nan')],[1,2]),([0,300],[1,float('inf')])]
        for t,v in cases:
            with self.subTest(t=t,v=v), self.assertRaises(ValueError):
                integrate_hourly_samples(t,v)

    def test_invalid_gap_policy_rejected(self):
        for gap in [0,-1,float('inf'),float('nan')]:
            with self.subTest(gap=gap), self.assertRaises(ValueError):
                integrate_hourly_samples([0,300],[1,2],max_gap_seconds=gap)


if __name__=='__main__':unittest.main()
