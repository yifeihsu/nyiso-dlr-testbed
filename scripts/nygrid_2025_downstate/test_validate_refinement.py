"""Adversarial tests for refinement identity and injection accounting."""
import copy
import unittest

import numpy as np
import pandas as pd

from validate_refinement import (assert_identity, coverage_preserving_load_allocation, dc_channel_identity, exact_source_branches, identity_metrics,
    load_relocation, operator_identity, passive_residual_metrics, physical_cut_identity,
    paired_interface_scores, parent_structure, schur_signature, unit_generation_identity, zone_backbone_reachability, zone_interface_operators)


def case(ids, lines):
    bus = np.zeros((len(ids), 13)); bus[:, 0] = ids; bus[:, 1] = 1
    branch = np.zeros((len(lines), 13))
    for i, (f, t, x, shift) in enumerate(lines):
        branch[i, [0, 1, 3, 9, 10]] = [f, t, x, shift, 1]
    return dict(baseMVA=100., bus=bus, branch=branch)


class RefinementAuditTests(unittest.TestCase):
    def setUp(self):
        self.parent = case([1, 2], [(1, 2, .1, 0)])
        self.expanded = case([1, 2, 3], [(1, 3, .04, 0), (3, 2, .06, 0)])

    def test_series_detail_has_full_Schur_identity(self):
        result = assert_identity(self.parent, self.expanded)
        self.assertLess(result["maximum_schur_matrix_error_mw_per_rad"], 1e-10)

    def test_aggregate_plus_duplicate_detail_fails_identity(self):
        doubled = copy.deepcopy(self.expanded)
        doubled["branch"] = np.vstack([doubled["branch"], self.parent["branch"]])
        with self.assertRaisesRegex(ValueError, "Schur admittance"):
            assert_identity(self.parent, doubled)

    def test_phase_shifter_change_not_hidden_by_admittance_identity(self):
        shifted = copy.deepcopy(self.expanded); shifted["branch"][0, 9] = 10
        self.assertLess(identity_metrics(self.parent, shifted)["maximum_schur_matrix_error_mw_per_rad"], 1e-10)
        with self.assertRaisesRegex(ValueError, "phase-source"):
            assert_identity(self.parent, shifted)

    def test_interior_injection_relocation_changes_retained_injections(self):
        projection = schur_signature(self.expanded, [1, 2])["injection_projection"]
        relocated = projection @ np.array([0., -10., 10.])
        self.assertAlmostEqual(relocated.sum(), 0.)
        self.assertGreater(np.max(np.abs(relocated - [10., -10.])), 1.)

    def test_nonpassive_residual_is_rejected(self):
        passive_residual_metrics(np.array([[2., -2.], [-2., 2.]]))
        with self.assertRaisesRegex(ValueError, "Nonpassive"):
            passive_residual_metrics(np.array([[-2., 2.], [2., -2.]]))

    def test_operator_uses_one_series_cut_not_both_legs(self):
        good = operator_identity(self.parent, self.expanded, [[1.]], [[1., 0.]])
        bad = operator_identity(self.parent, self.expanded, [[1.]], [[1., 1.]])
        self.assertLess(good["maximum_operator_response_error_mw_per_rad"], 1e-10)
        self.assertGreater(bad["maximum_operator_response_error_mw_per_rad"], 100.)
        physical_cut_identity(self.expanded, [1., 0.], [1])
        with self.assertRaisesRegex(ValueError, "Physical cut membership"):
            physical_cut_identity(self.expanded, [1., 1.], [1])

    def test_source_parameter_or_duplicated_source_row_is_rejected(self):
        original = case([10, 20], [(10, 20, .1, 0)])
        rows = [dict(model_branch_row=1, source_branch_row=1)]
        exact_source_branches(self.parent, original, rows, {10: 1, 20: 2})
        changed = copy.deepcopy(self.parent); changed["branch"][0, 3] = .11
        with self.assertRaisesRegex(ValueError, "Exact source branch"):
            exact_source_branches(changed, original, rows, {10: 1, 20: 2})
        with self.assertRaisesRegex(ValueError, "Source circuit copied"):
            exact_source_branches(self.expanded, original,
                [dict(model_branch_row=1, source_branch_row=1), dict(model_branch_row=2, source_branch_row=1)], {10: 1, 20: 2})

    def test_only_registered_parent_branch_deactivation_is_allowed(self):
        expanded = copy.deepcopy(self.expanded)
        old = self.parent["branch"].copy(); old[0, 10] = 0
        expanded["branch"] = np.vstack([old, expanded["branch"]])
        parent_structure(self.parent, expanded, [1])
        with self.assertRaisesRegex(ValueError, "registered status"):
            parent_structure(self.parent, expanded, [])
        expanded["branch"][0, 3] = .11
        with self.assertRaisesRegex(ValueError, "Original branch identity"):
            parent_structure(self.parent, expanded, [1])

    def test_load_cannot_cross_zone_or_duplicate_parent_allocation(self):
        load_relocation([[10., 20.]], [[6., 20., 4.]], [[.6, 0], [0, 1], [.4, 0]], ["A", "B"], ["A", "B", "A"])
        with self.assertRaisesRegex(ValueError, "crosses a zone"):
            load_relocation([[10., 20.]], [[6., 20., 4.]], [[.6, 0], [0, 1], [.4, 0]], ["A", "B"], ["A", "B", "B"])
        with self.assertRaisesRegex(ValueError, "allocated once"):
            load_relocation([[10., 20.]], [[10., 20., 4.]], [[1, 0], [0, 1], [.4, 0]], ["A", "B"], ["A", "B", "A"])

    def test_compensating_redispatch_cannot_hide_in_zonal_totals(self):
        register = pd.DataFrame(dict(device_key=["a", "b"], zone=["J", "J"], role=["native", "native"],
                                     fuel_category=["fossil", "fossil"], bus_id=[1, 2]))
        unit_generation_identity([[10., 20.]], [[10., 20.]], register, register)
        with self.assertRaisesRegex(ValueError, "Per-device PG preserved"):
            unit_generation_identity([[10., 20.]], [[11., 19.]], register, register)

    def test_score_cannot_drop_bad_hours_and_reports_regression(self):
        result = paired_interface_scores([[10.], [20.]], [[10.], [10.]], [[10.], [20.]],
                                         [True, True], [True, True], 1., ["guardrail"])
        self.assertGreater(result[0]["wape_change_percentage_points"], 30.)
        with self.assertRaisesRegex(ValueError, "qualification cohort"):
            paired_interface_scores([[10.], [20.]], [[10.], [np.nan]], [[10.], [20.]],
                                    [True, True], [True, False], 1., ["guardrail"])

    def test_DC_endpoint_move_requires_ledger_and_signed_schedule(self):
        old = np.zeros((1, 17)); old[0, :3] = [1, 2, 1]
        new = old.copy(); new[0, 1] = 3
        register = [dict(dc_row=1, endpoint="to", old_bus_id=2, new_bus_id=3)]
        dc_channel_identity({"dcline": old}, {"dcline": new}, [[10.]], [[10.]], register)
        with self.assertRaisesRegex(ValueError, "DC channel endpoints"):
            dc_channel_identity({"dcline": old}, {"dcline": new}, [[10.]], [[10.]])
        with self.assertRaisesRegex(ValueError, "signed DC schedule"):
            dc_channel_identity({"dcline": old}, {"dcline": new}, [[10.]], [[-10.]], register)

    def test_zone_operator_counts_new_crossing_not_inactive_aggregate_or_external_tie(self):
        model = case([1, 2, 3, 4], [(1, 2, .1, 0), (1, 3, .04, 0), (3, 2, .06, 0), (2, 4, .1, 0)])
        model["branch"][0, 10] = 0
        operators = zone_interface_operators(model, {1: "I", 2: "J", 3: "I", 4: "NA"})
        np.testing.assert_array_equal(operators[6], [0., 0., 1., 0.])

    def test_partial_source_coverage_retains_unrepresented_load_at_parent(self):
        parent = case([1, 2, 3], [(1, 2, .1, 0), (2, 3, .1, 0)])
        source = case([10, 20, 30, 31], [(10, 20, .1, 0), (20, 30, .1, 0), (30, 31, .1, 0)])
        source["bus"][:, 10] = [72, 74, 75, 75]
        source["bus"][:, 2] = [100, 100, 2, 98]
        register = pd.DataFrame(dict(model_bus=[1, 2, 3, 4], accounting_zone=["I", "J", "K", "K"],
                                     source_bus=[0, 0, 0, 30], source_pd_mw=[0, 0, 0, 2]))
        good = np.eye(4, 3); good[2, 2] = .98; good[3, 2] = .02
        rows = coverage_preserving_load_allocation(parent, source, register, good)
        self.assertAlmostEqual(rows[2]["residual_fraction_retained_at_original_buses"], .98)
        bad = good.copy(); bad[2, 2] = 0.; bad[3, 2] = 1.
        with self.assertRaisesRegex(ValueError, "Source coverage allocation"):
            coverage_preserving_load_allocation(parent, source, register, bad)

    def test_loaded_K_leaf_requires_within_zone_backbone(self):
        broken = case([1, 2, 3], [(1, 2, .1, 0), (2, 3, .1, 0)])
        zones = {1: "K", 2: "J", 3: "K"}
        with self.assertRaisesRegex(ValueError, "source backbone is incomplete"):
            zone_backbone_reachability(broken, zones, "K", [1], [3])
        repaired = case([1, 2, 3], [(1, 2, .1, 0), (2, 3, .1, 0), (1, 3, .2, 0)])
        result = zone_backbone_reachability(repaired, zones, "K", [1], [3])
        self.assertEqual(result["loaded_buses_unreachable_within_zone"], 0)


if __name__ == "__main__":
    unittest.main()
