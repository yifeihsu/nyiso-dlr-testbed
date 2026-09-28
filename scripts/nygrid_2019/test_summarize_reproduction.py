"""Independent synthetic metric, calendar and quality-join guards."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("summarize_reproduction", Path(__file__).with_name("summarize_reproduction.py"))
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


class ReproductionMetricTests(unittest.TestCase):
    def test_zeros_do_not_disappear_from_weighted_absolute_error(self):
        r = summary.metrics([10, 120, 50], [0, 100, -100], [100, 200, 200])
        self.assertEqual(r["actual_flow_wape_pct"], 90)
        self.assertEqual(r["mae_mw"], 60)
        self.assertAlmostEqual(r["rmse_mw"], np.sqrt(23000 / 3))
        self.assertEqual(r["mape_nonzero_actual_pct"], 85)
        self.assertEqual(r["mape_defined_observations"], 2)
        self.assertEqual(r["zero_actual_flow_count"], 1)
        self.assertEqual(r["opposite_direction_count"], 1)

    def test_tiny_nonzero_actual_is_not_floored(self):
        r = summary.metrics([1], [.001], [9999])
        self.assertAlmostEqual(r["actual_flow_wape_pct"], 99900)
        self.assertAlmostEqual(r["mape_nonzero_actual_pct"], 99900)
        self.assertLess(abs(r["paper_error_median_pct"]), .01)

    def test_all_zero_actual_makes_relative_metrics_undefined(self):
        r = summary.metrics([0, 10], [0, 0], [100, 100])
        self.assertIsNone(r["actual_flow_wape_pct"])
        self.assertIsNone(r["mape_nonzero_actual_pct"])
        self.assertIsNone(r["max_nonzero_actual_error_pct"])
        self.assertEqual(r["mae_mw"], 5)

    def test_paper_sign_positive_denominator_and_quantiles(self):
        r = summary.metrics([110, -80, 0, 50], [100, -100, 0, 100], [100] * 4)
        values = np.array([-10, -20, 0, 50])
        self.assertAlmostEqual(r["paper_error_median_pct"], -5)
        self.assertAlmostEqual(r["paper_error_q025_pct"], np.quantile(values, .025))
        self.assertAlmostEqual(r["paper_error_q975_pct"], np.quantile(values, .975))
        self.assertEqual(r["fraction_absolute_paper_error_le_10pct"], .5)
        self.assertEqual(r["fraction_absolute_paper_error_le_15pct"], .5)
        self.assertEqual(r["zero_prediction_nonzero_actual_count"], 0)

    def test_scaling_flows_and_limits_preserves_all_percentages(self):
        a = summary.metrics([12, -7, 2], [10, -5, 0], [20, 25, 30])
        b = summary.metrics(np.array([12, -7, 2]) * .355, np.array([10, -5, 0]) * .355, np.array([20, 25, 30]) * .355)
        for key in a:
            if "pct" in key and a[key] is not None:
                self.assertAlmostEqual(a[key], b[key])

    def test_invalid_inputs_rejected(self):
        for sim, obs, limit in [([1], [0], [0]), ([np.nan], [1], [100]), ([1], [1], [-100]), ([], [], []), ([1, 2], [1], [1])]:
            with self.subTest(sim=sim, obs=obs, limit=limit), self.assertRaises(ValueError):
                summary.metrics(sim, obs, limit)

    @staticmethod
    def hourly_fixture():
        return pd.DataFrame({
            "timestamp": ["01-Jan-2019 00:00:00"] * 7,
            "interface": list(summary.INTERFACES), "released_plot_mw": [110.] * 7,
            "corrected_operator_mw": [105.] * 7, "observed_mw": [100.] * 7,
            "positive_limit_mw": [1000.] * 7, "released_paper_error_pct": [-1.] * 7, "pf_success": [1] * 7,
        })

    def test_duplicate_worker_rows_cannot_inflate_annual_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "one.csv"
            pd.concat([self.hourly_fixture()] * 2).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                summary.load_campaign([path], pilot=True)

    def test_partial_grid_cannot_be_called_annual(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for k in range(4):
                frame = self.hourly_fixture()
                frame["timestamp"] = f"01-Jan-2019 0{k}:00:00"
                path = Path(folder) / f"part{k}.csv"
                frame.to_csv(path, index=False)
                paths.append(path)
            with self.assertRaisesRegex(ValueError, "8760"):
                summary.load_campaign(paths, pilot=False)

    def test_failed_pf_cannot_be_silently_dropped(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "one.csv"
            frame = self.hourly_fixture()
            frame.loc[0, "pf_success"] = 0
            frame.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "failed"):
                summary.load_campaign([path], pilot=True)

    def test_quality_must_match_flow_and_filter_meaning(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.csv"
            rows = self.hourly_fixture()
            rows.timestamp = pd.to_datetime(rows.timestamp, format="%d-%b-%Y %H:%M:%S")
            rows["InterfaceName"] = rows.interface.map(summary.INTERFACES)
            quality = pd.DataFrame({"TimeStamp": ["2019-01-01 00:00:00"] * 7, "InterfaceName": list(summary.INTERFACES.values()),
                                    "FlowMWH": [100.] * 7, "PositiveLimitMWH": [1000.] * 7, "sample_count": [12] * 7,
                                    "distinct_timestamp_count": [12] * 7, "FlowMWH_imputed": [False] * 7,
                                    "PositiveLimitMWH_imputed": [False] * 7, "spring_dst_missing_hour": [False] * 7,
                                    "fall_dst_ambiguous_hour": [False] * 7, "filter_unimputed_unambiguous_hour": [True] * 7})
            quality.to_csv(source, index=False)
            joined = summary.join_quality(rows, source)
            self.assertEqual(len(joined), 7)
            quality.loc[0, "FlowMWH"] = 101
            quality.to_csv(source, index=False)
            with self.assertRaisesRegex(ValueError, "flow"):
                summary.join_quality(rows, source)
            quality.loc[0, "FlowMWH"] = 100
            quality.loc[0, "filter_unimputed_unambiguous_hour"] = False
            quality.to_csv(source, index=False)
            with self.assertRaisesRegex(ValueError, "filter"):
                summary.join_quality(rows, source)


if __name__ == "__main__":
    unittest.main()
