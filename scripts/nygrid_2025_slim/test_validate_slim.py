"""Adversarial checks for the zero-injection slim DC equivalent."""
import copy
import unittest

import numpy as np
import pandas as pd

from validate_slim import (assert_dc_equivalence, assert_generic_operator, component_provenance, expected_generic_operator,
                           equivalent_placeholder_contract, passive_residual, zero_interior_injection_contract)


def case(ids, edges):
    bus = np.zeros((len(ids), 13)); bus[:, 0] = ids
    branch = np.zeros((len(edges), 13))
    for i, (a, b, x, shift) in enumerate(edges):
        branch[i, [0, 1, 3, 9, 10]] = [a, b, x, shift, 1]
    gen = np.zeros((1, 21)); gen[0, 0] = ids[0]; gen[0, 7] = 1
    return dict(baseMVA=100., bus=bus, branch=branch, gen=gen, dcline=np.zeros((0, 17)))


class SlimAuditTests(unittest.TestCase):
    def setUp(self):
        self.full = case([1, 2, 3], [(1, 3, .04, 4.), (3, 2, .06, 6.)])
        self.slim = case([1, 2], [(1, 2, .1, 10.)])

    def test_affine_series_reduction_is_exact(self):
        result = assert_dc_equivalence(self.full, self.slim)
        self.assertLess(result["maximum_B_error_mw_per_rad"], 1e-10)

    def test_dropping_phase_offset_fails_even_when_B_matches(self):
        changed = copy.deepcopy(self.slim); changed["branch"][0, 9] = 0
        with self.assertRaisesRegex(ValueError, "affine phase"):
            assert_dc_equivalence(self.full, changed)

    def test_interior_load_or_asset_landing_is_rejected(self):
        zero_interior_injection_contract(self.full, [1, 2])
        with self.assertRaisesRegex(ValueError, "generator landing"):
            zero_interior_injection_contract(self.full, [1, 2], generator_bus_ids=[3])
        with self.assertRaisesRegex(ValueError, "Hourly interior PD"):
            zero_interior_injection_contract(self.full, [1, 2], pd=[[0., 0., 1.]])

    def test_generic_operator_preserves_internal_source_flow(self):
        matrix, offset = expected_generic_operator(self.full, [1, 2], [[1., 0.]])
        assert_generic_operator(self.full, [1, 2], [[1., 0.]], matrix, offset)
        with self.assertRaisesRegex(ValueError, "Generic operator"):
            assert_generic_operator(self.full, [1, 2], [[1., 0.]], matrix, np.zeros(1))

    def test_parallel_retained_direct_circuit_must_be_subtracted_once(self):
        full = case([1, 2, 3], [(1, 2, .2, 0.), (1, 3, .04, 0.), (3, 2, .06, 0.)])
        slim = case([1, 2], [(1, 2, .2, 0.), (1, 2, .1, 0.)])
        result = passive_residual(full, slim, [1])
        self.assertEqual(result["required_positive_residual_pairs"], 1)
        with self.assertRaisesRegex(ValueError, "counted more than once"):
            passive_residual(full, slim, [1, 1])
        double_count = case([1, 2], [(1, 2, .04, 0.)])
        with self.assertRaisesRegex(ValueError, "Nonpassive residual"):
            passive_residual(full, double_count, [1])

    def test_equivalent_cannot_claim_resistance_or_thermal_rating(self):
        equivalent_placeholder_contract(self.slim, [1])
        changed = copy.deepcopy(self.slim); changed["branch"][0, 5] = 500
        with self.assertRaisesRegex(ValueError, "thermal rating"):
            equivalent_placeholder_contract(changed, [1])
        changed["branch"][0, 5] = 0; changed["branch"][0, 2] = .01
        with self.assertRaisesRegex(ValueError, "resistance"):
            equivalent_placeholder_contract(changed, [1])

    def test_naive_zone_operator_loses_eliminated_boundary(self):
        full = case([1, 2, 3], [(1, 3, .04, 0.), (3, 2, .06, 0.)])
        # Internal bus3 is zone I, endpoints1/2 are H/J. Its I-to-J cut
        # cannot be recreated by looking only for I/J endpoint labels.
        with self.assertRaisesRegex(ValueError, "Generic operator"):
            assert_generic_operator(full, [1, 2], [[0., 1.]], np.zeros((1, 2)), np.zeros(1))

    def test_redundant_parallel_equivalents_do_not_hide_line_expansion(self):
        redundant = case([1, 2], [(1, 2, .2, 0.), (2, 1, .2, 0.)])
        with self.assertRaisesRegex(ValueError, "unnecessary line expansion"):
            equivalent_placeholder_contract(redundant, [1, 2])

    def test_equivalent_documentation_cannot_omit_a_source_circuit(self):
        components = pd.DataFrame([dict(component_id=1, interior_bus_ids="3", retained_port_ids="1;2",
            source_branch_rows="1;2", interior_count=1, port_count=2, structural_pair_count=1)])
        contributions = pd.DataFrame([dict(from_bus=1, to_bus=2, component_ids="1", full191_source_branch_rows="1;2",
            full191_source_branch_keys="source_a;source_b", direct_retained_rows_excluded=True,
            pruned_by_magnitude_threshold=False, model_branch_row=1, weight_MW_per_rad=1000., x_pu=.1)])
        source_rows = pd.DataFrame(dict(branch_key=["source_a", "source_b"]))
        component_provenance(self.full, self.slim, components, contributions, source_rows, [])
        contributions.loc[0, "full191_source_branch_rows"] = "1"
        with self.assertRaisesRegex(ValueError, "lineage is incomplete"):
            component_provenance(self.full, self.slim, components, contributions, source_rows, [])


if __name__ == "__main__":
    unittest.main()
