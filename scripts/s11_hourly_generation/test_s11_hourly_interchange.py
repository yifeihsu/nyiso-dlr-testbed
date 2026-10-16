"""Physical accounting and temporal guards for the S11 interchange handoff."""
import unittest

import numpy as np
import pandas as pd

from extract_s11_hourly_interchange import CHANNELS, MAPPING, PRIMARY, channel_identity, hourly_channel


class InterchangeTests(unittest.TestCase):
    def samples(self):
        times = pd.date_range("2025-07-15T22:00Z", periods=13, freq="5min")
        return pd.DataFrame({"utc": times, "Flow (MWH)": np.arange(13, dtype=float),
                             "Interface Name": "SCH - HQ - NY", "Point ID": 23324})

    def test_ramp_and_gap_completion_have_distinct_quality(self):
        b = self.samples()
        normal = hourly_channel(b, [b.utc.iloc[0]]).iloc[0]
        self.assertEqual(normal.schedule_mw, 5.5)
        self.assertEqual(normal.applied_schedule_mw, normal.schedule_mw)
        self.assertFalse(normal.schedule_imputed)
        gap = hourly_channel(b.drop(index=[3, 4]), [b.utc.iloc[0]]).iloc[0]
        self.assertTrue(np.isnan(gap.schedule_mw))
        self.assertFalse(gap.coverage_qualified)
        self.assertTrue(gap.schedule_imputed)
        self.assertEqual(gap.uncovered_seconds, 900)
        # The values 3 and 4 are replaced by last available value 2.
        self.assertEqual(gap.applied_schedule_mw, (sum(range(12)) - 3 - 4 + 2 + 2) / 12)

    def test_edges_never_extrapolate(self):
        b = self.samples()
        for edge in [b.iloc[1:], b.iloc[:-1]]:
            result = hourly_channel(edge, [b.utc.iloc[0]]).iloc[0]
            self.assertFalse(result.applied_schedule_available)
            self.assertTrue(np.isnan(result.schedule_mw))
            self.assertTrue(np.isnan(result.applied_schedule_mw))
            self.assertFalse(result.schedule_imputed)

    def test_gap_over_one_hour_is_not_completed(self):
        b = self.samples().iloc[[0, -1]].copy()
        b.loc[b.index[-1], "utc"] += pd.Timedelta(minutes=1)
        result = hourly_channel(b, [b.utc.iloc[0]]).iloc[0]
        self.assertFalse(result.applied_schedule_available)
        self.assertTrue(np.isnan(result.applied_schedule_mw))

    def test_primary_allocation_conserves_each_region_and_excludes_extra_ties(self):
        self.assertEqual(len(CHANNELS), 11)
        self.assertEqual(len(MAPPING), 8)
        self.assertEqual({row[1] for row in MAPPING}, set(PRIMARY))
        for channel in PRIMARY:
            self.assertAlmostEqual(sum(row[3] for row in MAPPING if row[1] == channel), 1.0)
        regional = {channel: (-1) ** i * (i + 1) * 123.45 for i, channel in enumerate(PRIMARY)}
        self.assertAlmostEqual(sum(regional[channel] * weight for _, channel, _, weight in MAPPING),
                               sum(regional.values()))

    def test_conflicting_point_id_and_wrong_channel_are_rejected(self):
        b = self.samples()
        self.assertEqual(channel_identity(b, "SCH - HQ - NY"), 23324)
        b.loc[0, "Point ID"] = 999999
        with self.assertRaises(ValueError):
            channel_identity(b, "SCH - HQ - NY")
        with self.assertRaises(ValueError):
            channel_identity(self.samples(), "SCH - PJ - NY")


if __name__ == "__main__":
    unittest.main()
