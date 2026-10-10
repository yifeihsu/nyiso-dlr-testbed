"""Chronology boundary checks independent of any score or network parameter."""
import unittest
import numpy as np
from replay_refinement import state_schedule


class ChronologyTests(unittest.TestCase):
    def test_commissioning_boundary_hours(self):
        times = np.array(["2025-01-01T05:00:00Z", "2025-05-21T03:00:00Z", "2025-05-21T04:00:00Z",
            "2025-05-30T03:00:00Z", "2025-05-30T04:00:00Z", "2025-12-20T03:00:00Z", "2025-12-20T04:00:00Z"])
        expected = ["refined_2025_pre_may_case", "refined_2025_pre_may_case", "refined_2025_may21_case",
            "refined_2025_may21_case", "refined_2025_may30_case", "refined_2025_may30_case", "refined_2025_case"]
        np.testing.assert_array_equal(state_schedule(times, True), expected)

    def test_year_end_counterfactual_keeps_one_state(self):
        times = np.array(["2025-01-01T05:00:00Z", "2025-06-01T04:00:00Z", "2026-01-01T04:00:00Z"])
        np.testing.assert_array_equal(state_schedule(times, False), ["refined_2025_case"] * 3)


if __name__ == "__main__":
    unittest.main()
