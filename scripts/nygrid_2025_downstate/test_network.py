"""Physical and provenance checks for the controlled Downstate construction."""
import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

from build_network import DEFAULT, PARENT, SOURCE, VARIANTS, parse_source, series_split
from validate_refinement import (assert_identity, dc_matrices, exact_source_branches,
                                parent_structure, schur_signature)


class SeriesPhysics(unittest.TestCase):
    def test_nonunity_tap_and_phase_are_preserved(self):
        parent = dict(baseMVA=100., bus=np.array([[1.]+[0.]*12, [2.]+[0.]*12]),
                      branch=np.array([[1., 2., .01, .12, .03, 0, 0, 0, 1.13, 8., 1, -360, 360]]))
        candidate = copy.deepcopy(parent)
        candidate["bus"] = np.r_[parent["bus"], [[3.]+[0.]*12, [4.]+[0.]*12]]
        candidate["branch"] = series_split(parent["branch"][0], [1, 3, 4, 2], [.2, .3, .5])
        assert_identity(parent, candidate)
        # The tempting naive-X split is wrong when only one segment has tap.
        bad = copy.deepcopy(candidate)
        bad["branch"][:, 3] = parent["branch"][0, 3] * np.array([.2, .3, .5])
        with self.assertRaises(ValueError):
            assert_identity(parent, bad)

    def test_nonpositive_split_rejected(self):
        row = np.array([1., 2., .01, .1, 0, 0, 0, 0, 0, 0, 1, -360, 360])
        for weights in [[0, 1], [-1, 2]]:
            with self.assertRaises(ValueError):
                series_split(row, [1, 3, 2], weights)

    def test_modified_source_hash_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "changed.m"
            path.write_text(SOURCE.read_text() + "\n% changed\n")
            with self.assertRaises(ValueError):
                parse_source(path)


class DeliveredConstruction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = loadmat(DEFAULT / "network_cases.mat", simplify_cells=True)
        cls.parent = loadmat(PARENT, simplify_cells=True)["base_case"]
        cls.buses = pd.read_csv(DEFAULT / "bus_register.csv", keep_default_na=False)
        cls.branches = pd.read_csv(DEFAULT / "branch_register.csv", keep_default_na=False)
        cls.replacements = pd.read_csv(DEFAULT / "replacement_register.csv", keep_default_na=False)
        cls.mapping = dict(pd.read_csv(DEFAULT / "source_bus_map.csv")[["source_bus", "model_bus"]].to_numpy(int))

    def test_all_cases_preserve_parent_and_devices(self):
        for name in VARIANTS:
            case = self.data[name + "_case"]
            replaced = self.replacements.loc[self.replacements.variant.eq(name), "parent_branch_row"].tolist()
            parent_structure(self.parent, case, replaced)
            np.testing.assert_array_equal(case["gen"], self.parent["gen"])
            np.testing.assert_array_equal(case["dcline"], self.parent["dcline"])
            self.assertEqual(case["bus"].shape[0], 191)
            self.assertTrue(np.all(case["bus"][140:, 2:6] == 0))
            active = case["branch"][:, 10] == 1
            self.assertTrue(np.all(case["branch"][225:][active[225:], 2] >= 0))
            self.assertTrue(np.all(case["branch"][225:][active[225:], 3] > 0))

    def test_identity_for_arbitrary_injections_and_affine_phases(self):
        case = self.data["expanded_identity_case"]
        assert_identity(self.parent, case)
        old = dc_matrices(self.parent)
        new = schur_signature(case, self.parent["bus"][:, 0])
        random = np.random.default_rng(4381)
        injections = random.normal(size=(32, 140)) * 50
        injections -= injections.mean(axis=1)[:, None]
        theta = np.zeros_like(injections)
        theta[:, 1:] = np.linalg.solve(old["B"][1:, 1:], (injections[:, 1:] - old["phase_bus"][1:]).T).T
        lifted = theta @ new["angle_lift"].T + new["angle_offset"]
        full_residual = lifted @ new["network"]["B"].T + new["network"]["phase_bus"]
        np.testing.assert_allclose(full_residual[:, :140], injections, atol=1e-8, rtol=0)
        np.testing.assert_allclose(full_residual[:, 140:], 0, atol=1e-8, rtol=0)

    def test_source_circuits_exact_once(self):
        records = self.branches.loc[self.branches.electrical_role.eq("exact_historical_source_circuit")].to_dict("records")
        self.assertEqual(len(records), 97)
        for name in VARIANTS[1:]:
            result = exact_source_branches(self.data[name + "_case"], parse_source(), records, self.mapping,
                                           neutralized_angle_limits=True)
            self.assertEqual(result["maximum_source_parameter_error"], 0)
        bad = copy.deepcopy(self.data["refined_2025_case"])
        bad["branch"][int(records[0]["model_branch_row"])-1, 3] *= 1.001
        with self.assertRaises(ValueError):
            exact_source_branches(bad, parse_source(), records, self.mapping, neutralized_angle_limits=True)

    def test_load_and_generation_landing_contract(self):
        identity = self.data["load_allocation_identity"]
        np.testing.assert_array_equal(identity, np.eye(191, 140))
        W = self.data["load_allocation_asset"]
        np.testing.assert_allclose(W.sum(axis=0), 1, atol=1e-12, rtol=0)
        self.assertTrue(np.all(W >= 0))
        zones = self.buses.accounting_zone.to_numpy()
        self.assertTrue(np.all(W[zones[:, None] != zones[None, :140]] == 0))
        external = np.flatnonzero(zones[:140] == "NA")
        np.testing.assert_array_equal(W[:, external], identity[:, external])
        old, new = [self.data[k].astype(int) for k in ["generator_bus_identity", "generator_bus_asset"]]
        lookup = dict(zip(self.buses.model_bus, self.buses.accounting_zone))
        self.assertEqual(sum(old != new), 38)
        for a, b in zip(old, new):
            self.assertEqual(lookup[a], lookup[b])
        # Arthur Kill units and Ravenswood voltage groups must remain distinct.
        landing = pd.read_csv(DEFAULT / "generation_landing_register.csv", keep_default_na=False)
        targets = {(int(r.plant_id), str(r.eia_generator_id)): int(r.new_bus) for r in landing.itertuples()}
        self.assertEqual(targets[(2490, "2")], 20012)
        self.assertEqual(targets[(2490, "3")], 20013)
        self.assertEqual(targets[(55375, "CT1")], 11493)
        self.assertEqual(targets[(57664, "CT3")], 20005)
        self.assertEqual(targets[(65561, "SFWND")], 20006)

    def test_partial_load_coverage_uses_full_zone_denominator(self):
        W = self.data["load_allocation_asset"]
        source = parse_source()
        source_codes = {"I": 72, "J": 74, "K": 75}
        for zone, code in source_codes.items():
            full_pd = source["bus"][source["bus"][:, 10] == code, 2].sum()
            selected = self.buses.accounting_zone.eq(zone) & self.buses.source_pd_mw.gt(0)
            coverage = self.buses.loc[selected, "source_pd_mw"].sum() / full_pd
            original = np.flatnonzero(self.buses.iloc[:140].accounting_zone.eq(zone))
            for parent_row in original:
                self.assertAlmostEqual(W[parent_row, parent_row], 1-coverage)
                np.testing.assert_allclose(W[selected.to_numpy(), parent_row],
                                           self.buses.loc[selected, "source_pd_mw"].to_numpy()/full_pd,
                                           atol=1e-15, rtol=0)
            self.assertLess(coverage, 1)
        self.assertLess(coverage, .1)  # K detail cannot silently absorb all LI demand.

    def test_loaded_K_terminals_have_K_only_parent_paths(self):
        case = self.data["refined_2025_case"]
        k = set(self.buses.loc[self.buses.accounting_zone.eq("K"), "model_bus"])
        reached = {v for v in k if v <= 140}
        edges = [(int(r[0]), int(r[1])) for r in case["branch"] if r[10] and r[0] in k and r[1] in k]
        while True:
            grown = reached | {a for a,b in edges if b in reached} | {b for a,b in edges if a in reached}
            if grown == reached:
                break
            reached = grown
        loaded = set(self.buses.loc[self.buses.accounting_zone.eq("K") & self.buses.source_pd_mw.gt(0), "model_bus"])
        self.assertTrue(loaded.issubset(reached))
        self.assertTrue({10598, 10626, 11497}.issubset(reached))

    def test_core_nyes_exclusion_and_project_chronology(self):
        keys = dict(zip(self.branches.branch_key, self.branches.model_branch_row - 1))
        for name in VARIANTS[1:6]:
            case = self.data[name + "_case"]
            self.assertEqual(case["branch"][37, 10], 1)
            self.assertEqual(case["branch"][keys["NYES:2023_ADDITIONAL_345"], 10], 0)
        optional = self.data["refined_2025_nyes_case"]
        self.assertEqual(optional["branch"][37, 10], 0)
        self.assertEqual(optional["branch"][keys["NYES:2023_ADDITIONAL_345"], 10], 1)
        states = ["refined_2025_pre_may", "refined_2025_may21", "refined_2025_may30", "refined_2025"]
        for key, expected in [("RCC:CABLE:BROOKLYN", [0, 1, 1, 1]), ("RCC:CABLE:STATEN", [0, 0, 1, 1]),
                              ("CV:CV_LM_398_PROXY", [1, 1, 1, 0]), ("DOVER:CV_DOVER_Y17", [0, 0, 0, 1])]:
            self.assertEqual([int(self.data[name+"_case"]["branch"][keys[key], 10]) for name in states], expected)

    def test_template_interface_maps_never_reference_inactive_rows(self):
        zones = dict(zip(self.buses.model_bus, self.buses.accounting_zone))
        definitions = {1: (set("A"), set("B")), 2: (set("B"), set("C")),
                       3: (set("ABCDE"), set("FGHIJK")), 4: (set("D"), set("E")),
                       5: (set("E"), set("F")), 8: (set("ABCDEFG"), set("HIJK")),
                       10: (set("I"), set("J"))}
        for name in VARIANTS:
            case = self.data[name+"_case"]
            mapping = case["if"]["map"]
            self.assertEqual(set(mapping[:, 0]), set(definitions))
            for iid, (left, right) in definitions.items():
                expected = []
                for j, row in enumerate(case["branch"], 1):
                    if not row[10]:
                        continue
                    a, b = zones[int(row[0])], zones[int(row[1])]
                    if a in left and b in right:
                        expected.append(j)
                    elif a in right and b in left:
                        expected.append(-j)
                self.assertEqual(mapping[mapping[:, 0] == iid, 1].tolist(), expected)


if __name__ == "__main__":
    unittest.main()
