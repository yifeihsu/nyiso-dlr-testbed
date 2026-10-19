"""Focused unit tests for source-to-fleet allocation and resource bounds."""
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_dispatch_priors import association_ids, capacity_split, nj_admission, normalize_weights, resource_bounds, solar_weights


class PriorTests(unittest.TestCase):
    def test_many_to_many_partition_conserves_each_reporting_unit_once(self):
        gross = np.asarray([100., 200.])
        first = capacity_split([50., 50.])
        second = capacity_split([50., 150.])
        assigned = np.zeros(3)
        assigned[[0, 1]] += gross[0] * first
        assigned[[1, 2]] += gross[1] * second
        self.assertEqual(assigned.sum(), gross.sum())
        self.assertEqual(assigned[1], 100.)

    def test_normalization_keeps_total_and_missing_masks(self):
        p, ok, factor = normalize_weights([[1., 3.], [2., 1.], [0., 0.]], [200., np.nan, 0.], [True, False, True])
        np.testing.assert_allclose(p[0], [50., 150.])
        self.assertTrue(np.isnan(p[1]).all())
        np.testing.assert_allclose(p[2], [0., 0.])
        self.assertEqual(ok.tolist(), [True, False, True])
        self.assertEqual(factor[0], 50.)

    def test_zero_weights_cannot_manufacture_positive_generation(self):
        p, ok, _ = normalize_weights([[0., 0.]], [10.], [True])
        self.assertFalse(ok[0]); self.assertTrue(np.isnan(p).all())
        with self.assertRaises(ValueError):
            capacity_split([0., 0.])

    def test_solar_daylight_is_zero_at_local_midnight(self):
        local = pd.DatetimeIndex(['2025-07-01 00:00', '2025-07-01 12:00']).tz_localize('America/New_York')
        w = solar_weights(local, [42.5], [-75.])
        self.assertEqual(w[0, 0], 0.)
        self.assertGreater(w[1, 0], .5)

    def test_resource_caps_do_not_invent_storage_or_renewable_energy(self):
        fleet = pd.DataFrame({'is_variable_renewable': [1, 0, 0, 0], 'is_pumped_hydro': [0, 1, 0, 0],
            'pumped_hydro_prior_eligible': [0, 1, 0, 0], 'is_storage': [0, 1, 1, 0],
            'fuel_category': ['Wind', 'Hydro', 'Storage', 'Nuclear']})
        physical = np.full((2, 4), 100.)
        default = np.asarray([[100., 0., 0., 100.], [100., 0., 0., 100.]])
        prior = np.asarray([[40., 20., 0., 70.], [np.nan] * 4])
        nuclear = np.asarray([[0., 0., 0., 60.], [0., 0., 0., 60.]])
        result = resource_bounds(fleet, physical, default, prior, nuclear, [True, False])
        np.testing.assert_allclose(result[0], [40., 20., 0., 60.])
        self.assertTrue(np.isnan(result[1]).all())

    def test_scope_exclusion_zeros_bounds_without_reallocating_preference(self):
        fleet = pd.DataFrame({'is_variable_renewable': [1, 1], 'is_pumped_hydro': [0, 0],
            'pumped_hydro_prior_eligible': [0, 0], 'is_storage': [0, 0], 'fuel_category': ['Wind', 'Wind']})
        prior = np.asarray([[3., 7.]])
        result = resource_bounds(fleet, np.asarray([[10., 10.]]), np.asarray([[10., 0.]]),
                                 prior, np.zeros((1, 2)), [True])
        np.testing.assert_array_equal(result, [[3., 0.]])
        np.testing.assert_array_equal(prior, [[3., 7.]])

    def test_NJ_admission_uses_associated_generator_evidence_not_reporting_labels(self):
        associated = association_ids('GTG6 (172), STG2 (95.2), STG3 (95.2), STG1 (95.2)')
        admitted, policy = nj_admission(50006, associated)
        self.assertFalse(admitted)
        self.assertIn('conservative_prior_rule', policy)
        self.assertTrue(nj_admission(50006, association_ids('GTG1 (88), STG1 (95.2), STG2 (95.2), STG3 (95.2)'))[0])
        self.assertTrue(nj_admission(56964, association_ids('GT10 (64)'))[0])

    def test_shared_steam_pool_owns_capacity_once_and_preserves_P63_total(self):
        gross_reporting_groups = np.asarray([100., 110., 120., 130., 140.])
        unique_eia_capacities = np.asarray([88.] * 5 + [95.2] * 3)
        preferred_weights = gross_reporting_groups.sum() * capacity_split(unique_eia_capacities)
        self.assertEqual(len(preferred_weights), 8)
        self.assertAlmostEqual(preferred_weights.sum(), gross_reporting_groups.sum())
        combined = np.r_[400., preferred_weights][None, :]
        p, ok, _ = normalize_weights(combined, [800.], [True])
        self.assertTrue(ok[0]); self.assertAlmostEqual(p.sum(), 800.)


if __name__ == '__main__':
    unittest.main(verbosity=2)
