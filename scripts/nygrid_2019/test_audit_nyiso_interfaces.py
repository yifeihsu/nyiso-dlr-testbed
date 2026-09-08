"""Small adversarial fixtures for the independent NYISO source audit."""
import tempfile
from pathlib import Path
import unittest
import json
import sys

import numpy as np
import pandas as pd

from audit_nyiso_interfaces import COLS, KEYS, METRICS, compare_published, linear_fill, reconstruct_hourly


def fixture(times, flows):
    return pd.DataFrame({"TimeStamp": pd.to_datetime(times), "InterfaceName": "TEST",
                         "PointID": "1", "FlowMWH": flows,
                         "PositiveLimitMWH": 9999., "NegativeLimitMWH": -9999.})[COLS]


class TestNyisoReproduction(unittest.TestCase):
    def test_duplicates_are_sample_weighted_and_hour_is_left_closed(self):
        raw = fixture(["2019-01-01 00:00", "2019-01-01 00:00", "2019-01-01 00:59", "2019-01-01 01:00"],
                      [0., 6., 6., 100.])
        h = reconstruct_hourly(raw)
        self.assertEqual(h.FlowMWH.tolist(), [4., 100.])
        self.assertEqual(h.sample_count.tolist(), [3, 1])
        self.assertEqual(h.distinct_timestamp_count.tolist(), [2, 1])
        self.assertEqual(h.PositiveLimitMWH.tolist(), [9999., 9999.])

    def test_spring_local_missing_hour_is_flagged_and_interpolated(self):
        raw = fixture(["2019-03-10 01:00", "2019-03-10 03:00"], [10., 30.])
        h = reconstruct_hourly(raw)
        self.assertEqual(h.FlowMWH.tolist(), [10., 20., 30.])
        self.assertTrue(h.iloc[1].spring_dst_missing_hour)
        self.assertTrue(h.iloc[1].FlowMWH_imputed)
        self.assertTrue(np.isnan(h.iloc[1].FlowMWH_unimputed))
        self.assertEqual(h.iloc[1].sample_count, 0)

    def test_fall_fold_remains_ambiguous_and_combined(self):
        raw = fixture(["2019-11-03 01:00", "2019-11-03 01:30", "2019-11-03 01:00", "2019-11-03 02:00"],
                      [10., 20., 60., 100.])
        h = reconstruct_hourly(raw)
        self.assertEqual(h.iloc[0].FlowMWH, 30.)
        self.assertTrue(h.iloc[0].fall_dst_ambiguous_hour)
        self.assertFalse(h.iloc[0].FlowMWH_imputed)

    def test_linear_fills_long_gaps_and_extrapolates_endpoints(self):
        np.testing.assert_allclose(linear_fill([np.nan, 2., np.nan, np.nan, 8., np.nan]), [0., 2., 4., 6., 8., 10.])
        self.assertTrue(np.isnan(linear_fill([np.nan, np.nan])).all())

    def test_missing_numeric_sample_omitted_from_mean_but_count_retained(self):
        raw = fixture(["2019-01-01 00:00", "2019-01-01 00:05", "2019-01-01 01:00"], [np.nan, 10., 20.])
        h = reconstruct_hourly(raw)
        self.assertEqual(h.iloc[0].FlowMWH, 10.)
        self.assertEqual(h.iloc[0].sample_count, 2)
        self.assertEqual(h.iloc[0].FlowMWH_finite_samples, 1)

    def test_comparison_detects_missing_key_numeric_change_and_duplicate(self):
        h = reconstruct_hourly(fixture(["2019-01-01 00:00", "2019-01-01 01:00"], [1., 2.]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "published.csv"
            p = h[KEYS + METRICS].copy()
            p.to_csv(path, index=False)
            self.assertTrue(compare_published(h, path)[2]["numerically_reproduced"])
            p.loc[0, "FlowMWH"] += 1e-4
            p.to_csv(path, index=False)
            self.assertEqual(compare_published(h, path)[2]["rows_above_tolerance_or_missing"], 1)
            p.iloc[1:].to_csv(path, index=False)
            self.assertEqual(compare_published(h, path)[2]["missing_published_keys"], 1)
            pd.concat([p, p]).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                compare_published(h, path)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestNyisoReproduction)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    output = Path(__file__).resolve().parents[2] / "output/nygrid_2019/nyiso_source_audit_tests.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"tests_run": result.testsRun, "failures": len(result.failures),
                                 "errors": len(result.errors), "passed": result.wasSuccessful(),
                                 "scope": "Six synthetic guards: duplicate weighting, hour boundaries, DST, linear fill, missing numeric samples, and comparison rejection"}, indent=2) + "\n")
    sys.exit(not result.wasSuccessful())
