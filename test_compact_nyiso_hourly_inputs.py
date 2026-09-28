"""Numerical, temporal and blind-target guards for public input assembly."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from build_compact_nyiso_hourly_inputs import hourly_point_mean, local_utc, build, verify_freeze


class HourlyInputsTest(unittest.TestCase):
    def fixture(self, values=None):
        t = pd.date_range('2025-07-15T22:00:00Z', periods=13, freq='5min')
        return pd.DataFrame({'utc': t, 'Flow (MWH)': np.arange(13) if values is None else values,
                             'source_csv_line': np.arange(13) + 2})

    def test_linear_ramp_independent_closed_form(self):
        b = self.fixture()
        a = hourly_point_mean(b, b.utc.iloc[0])
        self.assertEqual(a['actual_hour_mean_mw'], 5.5)
        self.assertEqual(a['backward_hold_mean_mw'], 6.5)
        self.assertEqual(a['linear_mean_mw'], 6.0)

    def test_duplicate_labels_have_one_time_weight(self):
        b = self.fixture(np.full(13, 20.0))
        extra = b.iloc[[0]].copy()
        extra['Flow (MWH)'] = 40
        extra['source_csv_line'] = 99
        a = hourly_point_mean(pd.concat([b, extra]), b.utc.iloc[0])
        self.assertAlmostEqual(a['actual_hour_mean_mw'], 20 + 10/12)
        self.assertEqual(a['duplicate_timestamp_count'], 1)
        self.assertEqual(a['max_duplicate_spread_mw'], 20)
        self.assertAlmostEqual(a['duplicate_lower_hour_mean_mw'], 20)
        self.assertAlmostEqual(a['duplicate_upper_hour_mean_mw'], 20 + 20/12)
        self.assertIn('99', a['source_csv_lines'].split(';'))

    def test_incomplete_and_gapped_hours_rejected(self):
        b = self.fixture()
        for bad in [b.iloc[1:], b.iloc[:-1], b.drop(index=[3, 4])]:
            with self.assertRaises(AssertionError):
                hourly_point_mean(bad, b.utc.iloc[0])

    def test_nonfinite_rejected(self):
        b = self.fixture()
        b.loc[2, 'Flow (MWH)'] = np.nan
        with self.assertRaises(AssertionError):
            hourly_point_mean(b, b.utc.iloc[0])

    def test_timezone_and_dst(self):
        self.assertEqual(local_utc(['2025-07-15 18:00'], 'EDT')[0], pd.Timestamp('2025-07-15T22:00Z'))
        self.assertEqual(local_utc(['2025-01-15 18:00'], 'EST')[0], pd.Timestamp('2025-01-15T23:00Z'))
        with self.assertRaises(AssertionError):
            local_utc(['2025-07-15 18:00'], 'EST')
        for t in ['2025-11-02 01:30', '2025-03-09 02:30']:
            with self.assertRaises(Exception):
                local_utc([t], 'EST')

    def test_internal_targets_require_freeze(self):
        with self.assertRaises(AssertionError):
            build(include_targets=True)
        with tempfile.TemporaryDirectory() as p:
            f = Path(p) / 'bad.json'
            f.write_text('{"internal_targets_used_to_form_prior":true}')
            with self.assertRaises(AssertionError):
                verify_freeze(f)


if __name__ == '__main__':
    unittest.main()
