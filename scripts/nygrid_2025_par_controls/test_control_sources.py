"""Adversarial source gates and per-device controlled-transfer invariants.

Tests mutate only in-memory copies. Frozen source files and replay artifacts
are read-only. No annual replay or internal-interface scoring is performed.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from scipy.io import loadmat

from controlled_equivalent import make_controlled_case, qualify_targets
from replay_controls import verify_control_sources
from build_control_inputs import parse_schedule, p_only_screen

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_par_controls"


class SourceGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with np.load(OUT / "controls/inputs.npz", allow_pickle=False) as values:
            cls.original_controls = {key: values[key].copy() for key in values.files}
        cls.original_receipt = json.loads((OUT / "controls/input_receipt.json").read_text())

    def setUp(self):
        self.controls = {key: value.copy() for key, value in self.original_controls.items()}
        self.receipt = copy.deepcopy(self.original_receipt)

    def reject(self):
        with self.assertRaises((ValueError, KeyError)):
            verify_control_sources(self.controls, self.receipt)

    def test_accepts_complete_frozen_source_proof(self):
        verify_control_sources(self.controls, self.receipt)

    def test_rejects_unqualified_status(self):
        self.receipt["status"] = "partial_source_capture"
        self.reject()

    def test_rejects_unverified_direction(self):
        self.receipt["P34_direction_verified"] = False
        self.reject()

    def test_rejects_wrong_effective_date(self):
        self.receipt["P34_direction_effective_date"] = "2026-01-01"
        self.reject()

    def test_rejects_internal_observations_in_source_build(self):
        self.receipt["internal_interface_observations_read"] = True
        self.reject()

    def test_rejects_unpassed_native_P_screen(self):
        self.receipt["necessary_active_power_screen_passed"] = False
        self.reject()

    def test_rejects_unverified_NPZ_direction(self):
        self.controls["observed_direction_verified"] = np.bool_(False)
        self.reject()

    def test_rejects_reversed_numeric_orientation(self):
        self.controls["direction_ontario_to_NY_multiplier"] = np.array([-1, -1])
        self.reject()

    def test_rejects_wrong_recorded_source_hash(self):
        self.receipt["dependencies"][0]["sha256"] = "0" * 64
        self.reject()

    def test_rejects_absent_dependency_proof(self):
        self.receipt["dependencies"] = []
        self.reject()

    def test_rejects_absent_NPZ_output_proof(self):
        self.receipt["outputs"] = []
        self.reject()

    def test_rejects_changed_equipment_metadata(self):
        data = json.loads(str(self.controls["limit_metadata_json"]))
        data["devices"][0]["nominal_mva"] = 500.
        self.controls["limit_metadata_json"] = np.array(json.dumps(data))
        self.reject()

    def test_rejects_changed_direction_metadata(self):
        data = json.loads(str(self.controls["direction_metadata_json"]))
        data["sign_convention_effective_date"] = "2026-01-01"
        self.controls["direction_metadata_json"] = np.array(json.dumps(data))
        self.reject()

    def test_rejects_numerical_envelope_source_disagreement(self):
        self.controls["p_only_limit_public_mw"] = np.array([301., 300.])
        self.reject()

    def test_rejects_hardware_phase_bound_on_equivalent(self):
        self.controls["hardware_phase_applies_to_equivalent"] = np.bool_(True)
        self.reject()


class TransferAndClockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = loadmat(ROOT / "output/nygrid_2025_slim/network/network_cases.mat", simplify_cells=True,
                           variable_names=["refined_2025_pre_may_case"])["refined_2025_pre_may_case"]
        cls.buses = pd.read_csv(ROOT / "output/nygrid_2025_moses_audit/corrected/model_generator_register.csv").bus_id.to_numpy(int)

    def test_invalid_targets_are_rejected_per_device(self):
        for value in [[301., -299.], [-301., 299.], [301., -301.], [np.nan, 0.], [np.inf, 0.], [0.], [0., 0., 0.]]:
            with self.subTest(target=value), self.assertRaises(ValueError):
                make_controlled_case(self.case, self.buses, value, [300., 300.])

    def test_invalid_limits_are_rejected_by_construction_and_qualification(self):
        for value in [[np.nan, 300.], [np.inf, 300.], [0., 300.], [-1., 300.]]:
            with self.subTest(limit=value), self.assertRaises(ValueError):
                make_controlled_case(self.case, self.buses, [0., 0.], value)
            with self.subTest(qualification_limit=value), self.assertRaises(ValueError):
                qualify_targets(np.array([[0., 0.]]), value)

    def test_boundary_values_preserve_two_signed_ports_and_original_devices(self):
        original = copy.deepcopy(self.case)
        for targets in [[300., -300.], [-300., 300.], [0., 0.]]:
            got = make_controlled_case(self.case, self.buses, targets, [300., 300.])
            np.testing.assert_array_equal(got["dcline"][:4], original["dcline"])
            np.testing.assert_array_equal(got["dcline"][4:, :3], [[100, 48, 1], [100, 48, 1]])
            for column in [3, 4, 9, 10]:
                np.testing.assert_array_equal(got["dcline"][4:, column], targets)
            expected = original["branch"].copy()
            expected[210, 10] = 0
            np.testing.assert_array_equal(got["branch"], expected)
            np.testing.assert_array_equal(got["branch"][:, 9], original["branch"][:, 9])
            for key in ["bus", "branch", "gen", "dcline"]:
                np.testing.assert_array_equal(self.case[key], original[key])

    def test_raw_excursion_cannot_hide_in_an_hourly_mean(self):
        values = [301., -299.]
        self.assertLess(abs(np.mean(values)), 300.)
        with self.assertRaises(ValueError):
            p_only_screen(values, 300., "raw spike")

    def test_DST_day_headers_preserve_physical_hours(self):
        for member, label, count in [("20250309parSchedule.txt", "09-MAR-2025", 23),
                                     ("20251102parSchedule.txt", "02-NOV-2025", 25)]:
            payload = f"00:00 {label} 60 {count} 2\n25118 G " + " ".join(map(str, range(count))) + "\n25119 G " + " ".join(["0"] * count)
            times, values, _, _ = parse_schedule(payload.encode(), member)
            self.assertEqual(len(times), count)
            self.assertTrue(times.is_unique)
            np.testing.assert_array_equal(np.diff(times.asi8), np.full(count - 1, 3600e9))
            np.testing.assert_array_equal(values[:, 0], np.arange(count))
            local = times.tz_convert("America/New_York")
            self.assertEqual(int(np.sum(local.hour == 1)), 1 if count == 23 else 2)
            self.assertEqual(int(np.sum(local.hour == 2)), 0 if count == 23 else 1)
            with self.assertRaises(ValueError):
                parse_schedule(payload.replace(f"60 {count} 2", "60 24 2").encode(), member)

    def test_missing_schedule_channel_remains_missing(self):
        payload = b"00:00 01-JAN-2025 60 24 1\n25118 G " + b"0 " * 24
        _, values, _, _ = parse_schedule(payload, "20250101parSchedule.txt")
        self.assertTrue(np.isnan(values[:, 1]).all())


if __name__ == "__main__":
    unittest.main()
