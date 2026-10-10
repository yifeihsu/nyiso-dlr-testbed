"""Adversarial checks for physical-hour load and P32 aggregation semantics."""
from pathlib import Path
import sys
import unittest
import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_sources import FLOW_VALUES, canonical_load, forward_hourly, hour_catalog, load_utc, p32_utc


def flow(times, values):
    return pd.DataFrame({"timestamp_utc": pd.to_datetime(times, utc=True),
                         "flow_mw": values, "positive_limit_mw": 9999., "negative_limit_mw": -9999.})


class TestPhysicalSources(unittest.TestCase):
    def test_catalog_has_8760_physical_hours_and_both_fall_folds(self):
        c = hour_catalog()
        self.assertEqual(len(c), 8760)
        self.assertTrue(c.timestamp_utc.is_unique)
        fall = c[c.local_timestamp.eq('2025-11-02T01:00:00')]
        self.assertEqual(fall.time_zone.tolist(), ['EDT', 'EST'])
        self.assertEqual(fall.dst_fold.tolist(), [0, 1])
        self.assertFalse(c.local_timestamp.eq('2025-03-09T02:00:00').any())

    def test_explicit_load_timezone_keeps_folds_and_rejects_wrong_season(self):
        times = pd.DatetimeIndex(['2025-11-02 01:00', '2025-11-02 01:00'])
        actual = load_utc(times, np.array(['EDT', 'EST']))
        self.assertEqual(actual.strftime('%H:%M').tolist(), ['05:00', '06:00'])
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            load_utc(pd.DatetimeIndex(['2025-07-01 01:00']), np.array(['EST']))

    def test_p32_fold_uses_raw_clock_rewind_and_does_not_merge_two_hours(self):
        local = pd.DatetimeIndex(['2025-11-02 00:55', '2025-11-02 01:00', '2025-11-02 01:55',
                                  '2025-11-02 01:00', '2025-11-02 01:55', '2025-11-02 02:00'])
        utc, checks = p32_utc(local)
        self.assertTrue(utc.is_monotonic_increasing)
        self.assertEqual(utc[3] - utc[1], pd.Timedelta(hours=1))
        self.assertTrue(checks['fall_fold_resolved_from_raw_order'])
        with self.assertRaisesRegex(ValueError, 'explicit source clock rewind'):
            p32_utc(pd.DatetimeIndex(['2025-11-02 01:00', '2025-11-02 01:05']))

    def test_p32_spring_nonexistent_hour_is_not_imputed(self):
        local = pd.DatetimeIndex(['2025-03-09 01:55', '2025-03-09 03:00'])
        utc, _ = p32_utc(local)
        self.assertEqual(utc[1] - utc[0], pd.Timedelta(minutes=5))
        with self.assertRaises(Exception):
            p32_utc(pd.DatetimeIndex(['2025-03-09 02:00']))

    def test_forward_mean_uses_durations_and_duplicate_timestamp_mean(self):
        times = pd.date_range('2025-01-01T05:00Z', periods=7, freq='10min')
        g = flow(times, [0., 10., 20., 30., 40., 50., 900.])
        g = pd.concat([g, flow([times[0]], [10.])], ignore_index=True)
        result = forward_hourly(g, pd.DatetimeIndex([times[0]]))
        self.assertTrue(result.iloc[0].coverage_qualified)
        self.assertAlmostEqual(result.iloc[0].flow_mw, (5 + 10 + 20 + 30 + 40 + 50) / 6)
        self.assertNotEqual(result.iloc[0].flow_mw, result.iloc[0].paper_arithmetic_mean_flow_mw)
        self.assertEqual(result.iloc[0].maximum_duplicate_spread_mw, 10)

    def test_long_gap_remains_nan_and_full_interval_is_disqualified(self):
        times = pd.date_range('2025-01-01T05:00Z', periods=13, freq='5min').delete([3, 4])
        result = forward_hourly(flow(times, np.ones(len(times))), pd.DatetimeIndex([times[0]]))
        self.assertFalse(result.iloc[0].coverage_qualified)
        self.assertTrue(np.isnan(result.iloc[0].flow_mw))
        self.assertEqual(result.iloc[0].maximum_bracketing_gap_seconds, 900)
        self.assertEqual(result.iloc[0].coverage_seconds, 2700)
        self.assertEqual(result.iloc[0].coverage_failure, 'source_gap_over_600s')

    def test_end_of_hour_requires_future_bracket_not_extrapolation(self):
        times = pd.date_range('2025-01-01T05:00Z', periods=12, freq='5min')
        result = forward_hourly(flow(times, np.ones(len(times))), pd.DatetimeIndex([times[0]]))
        self.assertFalse(result.iloc[0].coverage_qualified)
        self.assertEqual(result.iloc[0].coverage_seconds, 3300)
        self.assertEqual(result.iloc[0].coverage_failure, 'missing_bracket')

    def test_mixed_sentinel_duplicate_is_flagged_before_averaging(self):
        times = pd.date_range('2025-01-01T05:00Z', periods=7, freq='10min')
        g = flow(times, np.ones(len(times)))
        g['positive_limit_mw'] = 1000.
        g['negative_limit_mw'] = -1000.
        extra = g.iloc[[2]].copy()
        extra['positive_limit_mw'] = 9999.
        result = forward_hourly(pd.concat([g, extra]), pd.DatetimeIndex([times[0]]))
        self.assertTrue(result.iloc[0].coverage_qualified)
        self.assertTrue(result.iloc[0].positive_limit_contains_sentinel)
        self.assertFalse(result.iloc[0].positive_limit_usable)
        self.assertFalse(result.iloc[0].negative_limit_contains_sentinel)
        self.assertTrue(result.iloc[0].negative_limit_usable)
        self.assertNotEqual(result.iloc[0].positive_limit_mw, 9999.)
        # A sentinel at the next hour's exact boundary does not contribute to
        # this forward-held average and must not invalidate the preceding hour.
        g.loc[g.index[-1], 'negative_limit_mw'] = -9999.
        previous = forward_hourly(g, pd.DatetimeIndex([times[0]]))
        self.assertFalse(previous.iloc[0].negative_limit_contains_sentinel)

    def test_conflicting_or_missing_load_keys_stay_unqualified(self):
        c = hour_catalog().iloc[:1]
        raw = pd.DataFrame({'timestamp_utc': [c.timestamp_utc.iloc[0]] * 2,
                            'zone': ['A', 'A'], 'load_mw': [100., 120.]})
        result = canonical_load(raw, c)
        self.assertEqual(len(result), 11)
        self.assertFalse(result.coverage_qualified.any())
        self.assertTrue(result.load_mw.isna().all())
        self.assertEqual(result.loc[result.zone.eq('A'), 'source_rows'].iloc[0], 2)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestPhysicalSources)
    names = [case.id() for case in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    target = Path(__file__).resolve().parents[2] / 'output/nygrid_2025_inputs/load_source/source_tests.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'completed_utc': datetime.now(timezone.utc).isoformat(),
        'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'passed': result.wasSuccessful(), 'test_cases': names,
        'test_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, indent=2) + '\n',
        encoding='utf-8', newline='\n')
    sys.exit(not result.wasSuccessful())
