"""Tests for accounting failures that can silently corrupt scaled studies."""
import unittest

import numpy as np
import pandas as pd

from build_operating_inputs import allocation, load_arrays, boundary_arrays, CHANNELS


class ScalingTests(unittest.TestCase):
    def setUp(self):
        self.info = pd.DataFrame(dict(idx=np.arange(1, 141), name=[f"B{i}" for i in range(140)],
                                     zone=["NA"] * 140, area=[1] * 140, sumLoadP0=np.ones(140)))
        self.info.loc[36:81, "zone"] = ["ABCDEFGHIJK"[min(i // 4, 10)] for i in range(46)]
        self.info.loc[self.info.zone == "J", "sumLoadP0"] = 0
        self.raw = np.zeros((140, 13))
        self.raw[:, 0] = np.arange(1, 141)
        self.raw[:, 2] = 10
        self.raw[:, 3] = 3
        self.weights = allocation(self.info)

    def test_peak_anchor_shapes_and_zonal_conservation(self):
        load = np.arange(1, 34, dtype=float).reshape(3, 11)
        a = load_arrays(load, self.raw, self.weights, self.info)
        self.assertAlmostEqual(a["zonal_load_model_mw"].sum(axis=1).max(), 460)
        for j, z in enumerate("ABCDEFGHIJK"):
            ids = self.weights.loc[self.weights.zone == z, "bus_id"].to_numpy() - 1
            np.testing.assert_allclose(a["bus_gross_pd"][:, ids].sum(axis=1), load[:, j] * a["gamma"])
        np.testing.assert_allclose(a["bus_gross_pd"][:, 0], 10 * a["external_load_ratio"])
        np.testing.assert_allclose(a["bus_gross_qd"][:, 0], 3 * a["external_load_ratio"])
        np.testing.assert_allclose(a["zonal_load_model_mw"] / load, a["gamma"])

    def test_zero_load_zone_fallback_is_explicit_and_conserves(self):
        j = self.weights.loc[self.weights.zone == "J"]
        np.testing.assert_allclose(j.weight, 1 / len(j))
        self.assertTrue(j.allocation_policy.str.contains("fallback").all())

    def test_invalid_load_is_rejected(self):
        for value in [np.nan, -1]:
            a = np.ones((2, 11)); a[0, 0] = value
            with self.assertRaisesRegex(ValueError, "Invalid public load"):
                load_arrays(a, self.raw, self.weights, self.info)

    def test_missing_one_exchange_is_not_silently_counted_as_zero(self):
        info = pd.DataFrame(dict(idx=np.arange(1, 141), area=[1] * 40 + [4] * 40 + [5] * 60))
        info.loc[info.idx == 48, "area"] = 2
        raw_gen = np.zeros((3, 21)); raw_gen[:, 0] = [21, 60, 100]; raw_gen[:, 1] = [100, 100, 100]
        base_gen = np.vstack([raw_gen, np.zeros((1, 21))]); base_gen[-1, 0] = 48
        case = dict(gen=base_gen, genfuel=np.array(["Import"] * 4))
        raw = dict(gen=raw_gen, bus=self.raw)
        wide = pd.DataFrame({c: [10., 20.] for c in CHANNELS})
        wide.loc[1, "SCH - PJM_HTP"] = np.nan
        a, _ = boundary_arrays(wide, .5, case, raw, info, np.ones(2))
        self.assertTrue(np.isnan(a["regional_import_model_mw"][1, 2]))
        self.assertTrue(np.isnan(a["external_input_pg"][1, 2]))
        self.assertAlmostEqual(a["dcline_pf"][0, 0], 10.)
        self.assertAlmostEqual(a["regional_import_model_mw"][0, 2], 20.)


if __name__ == "__main__":
    unittest.main()
