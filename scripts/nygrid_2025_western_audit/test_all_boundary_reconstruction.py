"""Adversarial contracts for simultaneous external-boundary reconstruction."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import reconstruct_all_boundaries as r


class AllBoundaryContracts(unittest.TestCase):
    def test_counteracting_regional_flows_do_not_create_native_supply(self):
        # Ontario+100 and PJM-100 are circulation: native total is unchanged.
        shares = np.array([[1, 0, 0, 0], [0, .3, 0, 0], [0, .7, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1.]])
        change = r.regional_pg_change([[0, 100, -100, 0]], shares, .3)
        np.testing.assert_allclose(change, [[0, 9, 21, -30, 0]], atol=1e-12)
        self.assertAlmostEqual(float(change.sum()), 0.)

    def test_HQ_single_injection_and_sign(self):
        change = r.regional_pg_change([[0, 0, 0, -50]], np.eye(4), .3)
        np.testing.assert_array_equal(change, [[0, 0, 0, -15]])

    def test_scale_applied_once(self):
        change = r.regional_pg_change([[10, -20, 30, -40]], np.eye(4), .3)
        np.testing.assert_allclose(change, [[3, -6, 9, -12]], atol=1e-12)

    def test_invalid_regional_partition_rejected(self):
        for share in [np.eye(4) * .5, np.eye(4) * -1, np.eye(4) * np.nan]:
            with self.assertRaises(ValueError):
                r.regional_pg_change([[1, 2, 3, 4]], share, .3)

    def test_missing_region_or_nonfinite_delta_rejected(self):
        for delta in [[[1, 2, 3]], [[1, 2, np.nan, 4]], [[1, 2, np.inf, 4]]]:
            with self.assertRaises(ValueError):
                r.regional_pg_change(delta, np.eye(4), .3)

    def test_legitimate_all_four_zero_retained(self):
        for total in [0., 2.5, -2.5, np.nan]:
            q, _, _ = r.independent_region_quality([[0, 0, 0, 0]], [total])
            self.assertTrue(q.all())

    def test_zero_report_conflicting_independent_total_quarantined(self):
        for total in [2.50001, -3., 500.]:
            q, _, _ = r.independent_region_quality([[0, 0, 0, 0]], [total])
            self.assertFalse(q.any())

    def test_individual_Ontario_zero_not_inherited_as_an_exclusion(self):
        q, allzero, _ = r.independent_region_quality([[100, 0, -50, 25]], [75])
        self.assertTrue(q.all()); self.assertFalse(allzero[0])

    def test_nonfinite_region_does_not_get_filled(self):
        q, _, _ = r.independent_region_quality([[100, np.nan, -50, 25]], [75])
        np.testing.assert_array_equal(q, [[True, False, True, True]])

    def test_frozen_run_includes_first_hour_but_not_adjacent_transitions(self):
        data = np.array([[1, 2, 3, 4], [10, 20, 30, 40], [10, 20, 30, 40], [10, 20, 30, 40], [11, 21, 31, 41]])
        q, lengths, runs = r.frozen_vector_quality(data, [0, 1, 4, 8, 20], [0, 20, 25, 23, 40], [True] * 5)
        np.testing.assert_array_equal(q, [False, True, True, True, False])
        np.testing.assert_array_equal(lengths, [1, 3, 3, 3, 1]); self.assertEqual(runs, 1)

    def test_frozen_vector_requires_both_independent_witnesses(self):
        data = np.tile([10., 20., 30., 40.], (3, 1))
        for ieso, isne, iq in [([1, 4, 8], [20, 21, 22], [True] * 3),
                               ([1, 4, 8], [20, 25, 30], [True, False, True]),
                               ([1, 4, np.nan], [20, 25, 30], [True] * 3)]:
            q, _, _ = r.frozen_vector_quality(data, ieso, isne, iq)
            self.assertFalse(q.any())

    def test_three_of_four_frozen_components_do_not_define_frozen_report(self):
        data = np.array([[10, 20, 30, 40], [10, 20, 30, 41], [10, 20, 30, 42]])
        q, _, runs = r.frozen_vector_quality(data, [1, 4, 8], [20, 25, 30], [True] * 3)
        self.assertFalse(q.any()); self.assertEqual(runs, 0)

    def test_balanced_but_nonoptimal_native_dispatch_rejected(self):
        # Same total and valid boxes do not suffice: objective/KKT must hold.
        with self.assertRaises(ValueError):
            r.kkt_metrics(np.array([[6., 4.]]), np.array([[5., 5.]]), np.zeros((1, 2)),
                          np.full((1, 2), 10.), np.ones((1, 2)), np.array([10.]), np.array([0.]))

    def test_bound_optimum_KKT_accepted(self):
        distance, balance, bound = r.kkt_metrics(np.array([[10., 7.]]), np.array([[9., 5.]]), np.zeros((1, 2)),
            np.full((1, 2), 10.), np.ones((1, 2)), np.array([17.]), np.array([2.]))
        self.assertEqual(max(distance.max(), balance.max(), bound.max()), 0.)

    def test_projection_does_not_mutate_priors_weights_or_bounds(self):
        prior = np.array([[3., 7.]])
        lower = np.array([[0., 2.]])
        upper = np.array([[10., 10.]])
        weights = np.array([[1., 4.]])
        before = [a.copy() for a in [prior, lower, upper, weights]]
        pg, dual, feasible = r.bounded_projection(prior, lower, upper, [12.], weights)
        self.assertTrue(feasible.all())
        for old, current in zip(before, [prior, lower, upper, weights]):
            np.testing.assert_array_equal(old, current)
        r.kkt_metrics(pg, prior, lower, upper, weights, np.array([12.]), dual)

    def test_empty_or_incomplete_proof_manifest_rejected(self):
        with self.assertRaises(ValueError):
            r.check_records([])
        p = r.ALLOCATION
        record = dict(path=p.relative_to(r.ROOT).as_posix(), sha256=r.sha(p))
        with self.assertRaises(ValueError):
            r.check_records([record], [r.REGISTER])
        with self.assertRaises(ValueError):
            r.check_records([record, record])
        with self.assertRaises(ValueError):
            r.check_records([dict(path=record["path"], sha256="0" * 64)])


class SourceGateMutationContracts(unittest.TestCase):
    """Mutate parsed metadata/derived views in memory; source files stay intact."""
    @classmethod
    def setUpClass(cls):
        cls.audit_path = r.SOURCES / "source_audit_receipt.json"
        cls.audit = json.loads(cls.audit_path.read_text())
        cls.review = json.loads(r.REVIEW.read_text())
        cls.times = pd.read_csv(r.SOURCES / "hourly_regional_actuals.csv", usecols=["timestamp_utc"]).timestamp_utc.to_numpy(str)
        _, cls.original, _ = r.original_schedules(cls.times)
        cls.native_cache = None

    def audit_rejected(self, altered):
        real_read = Path.read_text
        def read(path, *args, **kwargs):
            return json.dumps(altered) if path.resolve() == self.audit_path.resolve() else real_read(path, *args, **kwargs)
        with patch.object(Path, "read_text", read), self.assertRaises(ValueError):
            r.verify_boundary_sources(self.times, self.original)

    def test_import_sign_metadata_reversal_rejected(self):
        value = copy.deepcopy(self.audit); value["sign_transform"] = "output_import_mw = +bulk_Interchange_MW"
        self.audit_rejected(value)

    def test_hour_start_without_HE_conversion_rejected(self):
        value = copy.deepcopy(self.audit); value["time_transform"] = "timestamp_utc_start = EIA_period_utc_hour_ending"
        self.audit_rejected(value)

    def test_reporting_perspective_and_neighbor_code_mutations_rejected(self):
        for key, altered in [("reporting_balancing_authority", "IESO"),
                             ("neighboring_BA_codes", dict(self.audit["neighboring_BA_codes"], HQ="HQ"))]:
            value = copy.deepcopy(self.audit); value[key] = altered; self.audit_rejected(value)

    def test_missing_region_records_rejected(self):
        value = copy.deepcopy(self.audit); value["source_record_count"] -= 1
        self.audit_rejected(value)

    def test_bulk_MW_and_API_MWh_cannot_be_relabelled(self):
        value = copy.deepcopy(self.audit); value["bulk_source_units"] = "megawatthours"
        self.audit_rejected(value)

    def test_missing_direction_document_proof_rejected(self):
        value = copy.deepcopy(self.audit)
        value["source_proof"] = [x for x in value["source_proof"] if x["id"] != "EIA930_FLOW_sign"]
        self.audit_rejected(value)

    def test_incomplete_independent_review_manifest_rejected(self):
        value = copy.deepcopy(self.review)
        missing = (r.SOURCES / "raw/EIA930_instructions.pdf").resolve()
        value["dependencies"] = [x for x in value["dependencies"] if r.checked_path(x["path"]) != missing]
        real_read = Path.read_text
        def read(path, *args, **kwargs):
            return json.dumps(value) if path.resolve() == r.REVIEW.resolve() else real_read(path, *args, **kwargs)
        with patch.object(Path, "read_text", read), self.assertRaises(ValueError):
            r.verify_boundary_sources(self.times, self.original)

    @classmethod
    def cached_native(cls):
        if cls.native_cache is None:
            cls.native_cache = r.bulk_native_records(cls.audit["source_receipts"], cls.audit)
        return tuple(frame.copy(deep=True) for frame in cls.native_cache)

    def parsed_csv_mutation_rejected(self, filename, mutate):
        self.cached_native()
        real_csv = pd.read_csv
        target = (r.SOURCES / filename).resolve()
        def read(path, *args, **kwargs):
            data = real_csv(path, *args, **kwargs)
            if Path(path).resolve() == target:
                mutate(data)
            return data
        with patch.object(r, "bulk_native_records", side_effect=lambda *_: self.cached_native()), \
                patch.object(pd, "read_csv", side_effect=read), self.assertRaises(ValueError):
            r.verify_boundary_sources(self.times, self.original)

    def test_frozen_quality_mask_mutation_rejected(self):
        self.parsed_csv_mutation_rejected("hourly_source_quality.csv",
            lambda d: d.__setitem__("corroborated_frozen_report", False))

    def test_derived_actual_value_sign_mutation_rejected(self):
        def mutate(d):
            d.loc[0, "ONTARIO_actual_import_mw"] *= -1
        self.parsed_csv_mutation_rejected("hourly_regional_actuals.csv", mutate)

    def test_derived_UTC_clock_mutation_rejected(self):
        def mutate(d):
            d.loc[0, "timestamp_utc"] = "2025-01-01T06:00:00Z"
        self.parsed_csv_mutation_rejected("hourly_regional_actuals.csv", mutate)

    def test_true_source_mask_and_IESO_zero_hours_remain_distinct(self):
        self.cached_native()
        with patch.object(r, "bulk_native_records", side_effect=lambda *_: self.cached_native()):
            _, q, _, _, _, _ = r.verify_boundary_sources(self.times, self.original)
        self.assertEqual(int(q.sum()), 8754)
        expected = np.array([2999, 3000, 3001, 3007, 3008, 3009])
        np.testing.assert_array_equal(np.flatnonzero(~q) + 1, expected)
        ieso = pd.read_csv(r.OUT / "ontario/hourly_exchange_quality.csv")
        old_zero = ~r.bool_values(ieso.source_quality_qualified)
        self.assertEqual(int(old_zero.sum()), 6)
        self.assertTrue(q[old_zero].all())


if __name__ == "__main__":
    receipt_path = r.OUT / "dispatch/all_boundary_dispatch_receipt.json"
    dispatch_receipt = json.loads(receipt_path.read_text())
    dependencies = [r.checked_path(x["path"]) for x in dispatch_receipt["dependencies"]]
    dependencies += [receipt_path, r.ROOT / dispatch_receipt["dispatch_file"], Path(__file__).resolve()]
    dependencies = list(dict.fromkeys(dependencies))
    before = {p: r.sha(p) for p in dependencies}
    for row in dispatch_receipt["dependencies"]:
        r.require(before[r.checked_path(row["path"])] == row["sha256"], "Dispatch dependency changed before guard tests")
    r.require(before[r.ROOT / dispatch_receipt["dispatch_file"]] == dispatch_receipt["dispatch_file_sha256"], "Dispatch output changed before guard tests")
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    unchanged = all(r.sha(p) == value for p, value in before.items())
    summary = dict(passed=result.wasSuccessful() and unchanged, created_utc=datetime.now(timezone.utc).isoformat(),
        tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
        immutable_input_hashes_unchanged=unchanged,
        failure_details=[dict(test=str(test), traceback=error) for test, error in result.failures + result.errors],
        scope="Four-region circulation accounting; native prior/bound/weight preservation; KKT; source sign,HEclock,BAcodes,units,proof coverage,derived-value and corroborated-freeze-mask mutations; no filesystem source mutations.",
        dependencies=[dict(path=p.relative_to(r.ROOT).as_posix(), sha256=value) for p, value in before.items()])
    path = r.OUT / "dispatch/all_boundary_guard_test_receipt.json"
    path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in ["passed", "tests", "failures", "errors", "skipped", "immutable_input_hashes_unchanged"]}, indent=2))
    sys.exit(0 if summary["passed"] else 1)
