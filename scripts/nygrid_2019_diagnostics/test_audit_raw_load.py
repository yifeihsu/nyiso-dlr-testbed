"""Focused guards for load-source reconstruction risks, not output snapshots."""
import sys
import unittest
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_raw_load import compare, linear_fill, reconstruct_hourly


def fixture(times, loads, tz=None):
    return pd.DataFrame({"TimeStamp": pd.to_datetime(times), "TimeZone": tz or ["EST"] * len(times),
                         "ZoneName": "WEST", "Load": loads})


class TestRawLoadAudit(unittest.TestCase):
    def test_fall_fold_keeps_both_timezone_samples_and_averages_without_dedup(self):
        raw = fixture(["2019-11-03 01:00", "2019-11-03 01:00", "2019-11-03 02:00"],
                      [10., 30., 50.], ["EDT", "EST", "EST"])
        out = reconstruct_hourly(raw)
        self.assertEqual(out.Load.tolist(), [20., 50.])
        self.assertEqual(out.raw_timezone_labels.tolist(), ["EDT|EST", "EST"])
        self.assertEqual(out.raw_rows.tolist(), [2, 1])
        self.assertTrue(out.iloc[0].fall_dst_ambiguous_hour)
        self.assertEqual(out.iloc[0].duplicate_raw_timestamp_rows, 1)

    def test_sample_weighting_and_hour_boundaries_are_literal(self):
        raw = fixture(["2019-01-01 00:00", "2019-01-01 00:00", "2019-01-01 00:59", "2019-01-01 01:00"],
                      [0., 6., 6., 100.])
        out = reconstruct_hourly(raw)
        self.assertEqual(out.Load.tolist(), [4., 100.])
        self.assertEqual(out.raw_rows.tolist(), [3, 1])

    def test_spring_gap_is_visible_and_linearly_filled(self):
        raw = fixture(["2019-03-10 01:00", "2019-03-10 03:00"], [10., 30.], ["EST", "EDT"])
        out = reconstruct_hourly(raw)
        self.assertEqual(out.Load.tolist(), [10., 20., 30.])
        self.assertTrue(out.iloc[1].Load_imputed)
        self.assertTrue(out.iloc[1].spring_dst_hour)
        self.assertEqual(out.iloc[1].raw_rows, 0)
        self.assertEqual(out.iloc[1].raw_timezone_labels, "")

    def test_linear_fill_extrapolates_endpoints_and_rejects_underdetermined_slope(self):
        np.testing.assert_allclose(linear_fill([np.nan, 2., np.nan, np.nan, 8., np.nan]), [0, 2, 4, 6, 8, 10])
        with self.assertRaisesRegex(ValueError, "one finite"):
            linear_fill([np.nan, 2., np.nan])

    def test_missing_numeric_samples_have_distinct_counts(self):
        out = reconstruct_hourly(fixture(["2019-01-01 00:00", "2019-01-01 00:00", "2019-01-01 01:00"],
                                        [np.nan, 10., 20.]))
        self.assertEqual(out.iloc[0].Load, 10)
        self.assertEqual(out.iloc[0].raw_rows, 2)
        self.assertEqual(out.iloc[0].finite_load_samples, 1)

    def test_comparison_detects_value_changes_missing_keys_and_duplicates(self):
        h = reconstruct_hourly(fixture(["2019-01-01 00:00", "2019-01-01 01:00"], [1., 2.]))
        p = h[["TimeStamp", "ZoneName", "Load"]].copy()
        self.assertTrue(compare(h, p, "published")[1]["reproduced_within_tolerance"])
        p.loc[0, "Load"] += 1e-4
        self.assertEqual(compare(h, p, "published")[1]["rows_above_tolerance_or_missing"], 1)
        self.assertEqual(compare(h, p.iloc[:1], "published")[1]["missing_published_keys"], 1)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            compare(h, pd.concat([p, p]), "published")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestRawLoadAudit)
    names = [case.id() for case in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    target = Path(__file__).resolve().parents[2] / "output/nygrid_2019_diagnostics/load_audit_tests.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"completed_utc": datetime.now(timezone.utc).isoformat(),
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "passed": result.wasSuccessful(), "test_cases": names,
        "test_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    sys.exit(not result.wasSuccessful())
