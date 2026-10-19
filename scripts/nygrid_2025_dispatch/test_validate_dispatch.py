"""Adversarial checks for the independent dispatch audit, not the optimizer."""
import unittest

import numpy as np
import pandas as pd

from validate_dispatch import Audit, NJ_NATIVE_KEYS, NJ_QUARANTINE_KEYS, box_kkt, electrical_audit, verify_market_scope


class IndependentAuditTests(unittest.TestCase):
    @staticmethod
    def market_fixture():
        rows = []
        for key in sorted(NJ_NATIVE_KEYS | NJ_QUARANTINE_KEYS):
            native = key in NJ_NATIVE_KEYS
            plant = int(key.split(":")[3])
            evidence = "NYISO:GoldBook:2025|NYISO:P19:20261010"
            if plant == 50006:
                evidence += "|EGCO:Linden:20251216"
            rows.append(dict(device_key=key, inventory_state="NJ", plant_id=plant,
                unit_market_scope_eligible=int(native), bus_id=82 if native else 0,
                has_parent_landing=int(native), parent_bus_zone="J" if native else "",
                parent_bus_name="Existing bus" if native else "", source_zone_parent_bus_zone_conflict=0,
                zone="J" if native else ("PJM" if plant == 50006 else "UNVERIFIED"),
                mapping_method="same_zone_nearest_parent_bus_geographic_proxy" if native else "quarantined",
                market_scope_primary_corroborated=int(native), native_market_scope_evidence=evidence,
                native_p63_scope_inferred=int(native), native_p63_unit_output_observed=0))
        return pd.DataFrame(rows), pd.DataFrame({"zone": ["J"]}, index=[82])

    def test_NJ_market_native_units_and_explicit_quarantine_pass(self):
        fleet, info = self.market_fixture()
        scope = verify_market_scope(Audit(), fleet, info)
        self.assertEqual(int(scope.sum()), 18)

    def test_plant_BA_label_cannot_admit_Linden_GTG6(self):
        fleet, info = self.market_fixture()
        fleet.loc[fleet.device_key.eq("EIA860:2025:PLANT:50006:GEN:GTG6"), "unit_market_scope_eligible"] = 1
        with self.assertRaisesRegex(ValueError, "unit_market_scope_independent_reconstruction"):
            verify_market_scope(Audit(), fleet, info)

    def test_missing_corroborated_NJ_unit_is_detected(self):
        fleet, info = self.market_fixture()
        fleet = fleet.loc[fleet.device_key.ne("EIA860:2025:PLANT:56964:GEN:GT10")]
        with self.assertRaisesRegex(ValueError, "outside_state_inventory_exact_frozen_cohort"):
            verify_market_scope(Audit(), fleet, info)

    def test_quarantined_solar_cannot_gain_native_landing(self):
        fleet, info = self.market_fixture()
        mask = fleet.device_key.eq("EIA860:2025:PLANT:67086:GEN:P6132")
        fleet.loc[mask, ["bus_id", "has_parent_landing"]] = [82, 1]
        with self.assertRaisesRegex(ValueError, "only_explicit_quarantine_has_no_landing"):
            verify_market_scope(Audit(), fleet, info)

    def test_balanced_but_nonoptimal_dispatch_fails_stationarity(self):
        lo = np.zeros((1, 2)); hi = np.full((1, 2), 10.)
        prior = np.zeros((1, 2)); w = np.array([[1., 4.]])
        good = box_kkt([[4., 1.]], prior, lo, hi, w, [5.], [4.])
        bad = box_kkt([[3., 2.]], prior, lo, hi, w, [5.])
        self.assertLess(good["kkt_gradient_residual"][0], 1e-12)
        self.assertEqual(bad["sum_error_mw"][0], 0)
        self.assertGreater(bad["kkt_gradient_residual"][0], 1)

    def test_active_bound_inequalities_and_fixed_variables(self):
        upper = box_kkt([[4., 1.]], [[10., 0.]], [[0., 0.]], [[4., 10.]], [[1., 1.]], [5.], [1.])
        lower = box_kkt([[0., 2.]], [[-10., 3.]], [[0., 0.]], [[10., 10.]], [[1., 1.]], [2.], [-1.])
        fixed = box_kkt([[2., 3.]], [[100., -20.]], [[2., 3.]], [[2., 3.]], [[3., 7.]], [5.], [999.])
        for result in [upper, lower, fixed]:
            self.assertLess(result["kkt_gradient_residual"][0], 1e-12)
            self.assertLess(result["saved_dual_gradient_residual"][0], 1e-12)

    def test_bad_saved_dual_is_detected(self):
        result = box_kkt([[4., 1.]], [[0., 0.]], [[0., 0.]], [[10., 10.]], [[1., 4.]], [5.], [5.])
        self.assertLess(result["kkt_gradient_residual"][0], 1e-12)
        self.assertGreater(result["saved_dual_gradient_residual"][0], .9)

    def test_no_generator_can_hide_nodal_or_global_imbalance(self):
        bus = np.zeros((3, 13)); bus[:, 0] = [1, 2, 3]
        gen = np.zeros((1, 21)); gen[0, 0] = 1; gen[0, 7] = 1
        branch = np.zeros((2, 13)); branch[:, :2] = [[1, 2], [2, 3]]
        branch[:, 3] = .1; branch[:, 10] = 1
        case = dict(baseMVA=100., bus=bus, gen=gen, branch=branch, dcline=np.zeros((0, 17)))
        angle = np.rad2deg([[0., -.04, -.08]])
        good = electrical_audit(case, [[0., 0., 40.]], [[40.]], np.zeros((1, 0)), [[40., 40.]], angle, [1])
        bad = electrical_audit(case, [[0., 0., 40.]], [[39.]], np.zeros((1, 0)), [[40., 40.]], angle, [1])
        self.assertLess(good["independent_branch_error_mw"][0], 1e-12)
        self.assertLess(good["nodal_residual_mw"][0], 1e-12)
        self.assertAlmostEqual(bad["global_balance_residual_mw"][0], 1.)
        self.assertAlmostEqual(bad["nodal_residual_mw"][0], 1.)


if __name__ == "__main__":
    unittest.main()
