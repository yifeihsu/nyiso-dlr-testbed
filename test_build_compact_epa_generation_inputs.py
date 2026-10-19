"""Offline source-integrity and accounting tests; no power-flow fitting."""
import base64
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import build_compact_epa_generation_inputs as ep


class EPAGenerationInputsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = ep.OUTPUT
        cls.rows = ep.read_csv(cls.output / "epa_generation_hourly.csv")
        cls.scenarios = ep.read_csv(cls.output / "epa_selected_scenarios.csv")
        cls.selected = ep.read_csv(cls.output / "selected_epa_source_rows_2025.csv")
        cls.ng = ep.read_csv(cls.output / "nygrid_2019_identity_crosswalk.csv")
        cls.eia = ep.read_csv(cls.output / "epa_eia_crosswalk_ny.csv")

    def test_01_fixed_standard_time_and_exact_interval(self):
        s = {r["scenario_id"]: r for r in self.scenarios}
        summer = s["S1_2025_SUMMER_PEAK_PUBLIC"]
        winter = s["S2_2025_WINTER_PEAK_PUBLIC"]
        self.assertEqual(summer["epa_hour"], "17")  # 18 EDT = 17 EST
        self.assertEqual(summer["interval_start_utc"], "2025-07-29T22:00:00Z")
        self.assertEqual(summer["interval_end_utc"], "2025-07-29T23:00:00Z")
        self.assertEqual(winter["epa_hour"], "18")
        self.assertEqual(len(s), 16)
        self.assertEqual(sum(k.startswith("V") for k in s), 4)

    def test_02_partial_operation_is_weighted_once(self):
        row = {"Gross Load (MW)": "100", "Operating Time": "0.25"}
        self.assertEqual(ep.convert_gross(row)[2], 25)
        hourly = ep.read_csv(self.output / "quantity_audit_hourly_source.csv")
        daily = ep.read_csv(self.output / "quantity_audit_daily_source.csv")
        out = ep.quantity_audit(hourly, daily)[0]
        self.assertEqual(out["official_daily_gross_energy_mwh"], 951.75)
        self.assertEqual(out["source_hourly_gross_sum"], 975)
        self.assertEqual(out["absolute_error_mwh"], 0)

    def test_03_blanks_are_not_observed_zero(self):
        self.assertIsNone(ep.convert_gross({"Gross Load (MW)": "", "Operating Time": "0"})[2])
        self.assertIsNone(ep.convert_gross({"Gross Load (MW)": "100", "Operating Time": ""})[2])
        self.assertEqual(ep.convert_gross({"Gross Load (MW)": "0", "Operating Time": "1"})[2], 0)
        for value in ["NaN", "inf", "-1"]:
            with self.assertRaises(ValueError):
                ep.convert_gross({"Gross Load (MW)": value, "Operating Time": "1"})
        with self.assertRaises(ValueError):
            ep.convert_gross({"Gross Load (MW)": "20", "Operating Time": "1.01"})

    def test_04_exact_source_records_detect_mutation(self):
        ep.verify_extract(self.selected)
        changed = copy.deepcopy(self.selected[:1])
        changed[0]["Gross Load (MW)"] = "999"
        with self.assertRaisesRegex(ValueError, "disagree"):
            ep.verify_extract(changed)
        changed = copy.deepcopy(self.selected[:1])
        changed[0]["source_record_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            ep.verify_extract(changed)

    def test_05_crosswalk_many_to_many_never_duplicates_MW(self):
        idx = ep.mapping_indices(self.ng, self.eia)
        mapped = ep.map_unit("2682", "20", idx)
        self.assertEqual(mapped["zone"], "A")
        self.assertEqual(len(mapped["nygrid_crosswalk_rows"].split("|")), 3)
        keys = [(r["scenario_id"], r["facility_id"], r["unit_id"]) for r in self.rows]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(self.rows), 4103)

    def test_06_crosswalk_conflict_rejected_and_leading_zero_kept(self):
        a = dict(self.ng[0], facility_id="1", unit_id="01", zone="A")
        with self.assertRaisesRegex(ValueError, "contradictory"):
            ep.mapping_indices([a, dict(a, zone="B")], [])
        idx = ep.mapping_indices([a], [])
        self.assertEqual(ep.map_unit("1", "01", idx)["zone_mapping_kind"], "nygrid_2019_exact_facility_unit_crosswalk")
        self.assertEqual(ep.map_unit("1", "1", idx)["zone_mapping_kind"], "assumed_same_facility_zone_from_2019_ORIS_identity")

    def test_07_unmatched_generation_is_retained(self):
        idx = ep.mapping_indices([], [])
        mapped = ep.map_unit("999", "U1", idx)
        self.assertEqual(mapped["zone"], "")
        self.assertEqual(mapped["zone_mapping_kind"], "unmatched_zone_explicitly_retained")
        unmatched = ep.read_csv(self.output / "epa_unmatched_generation.csv")
        self.assertGreater(len(unmatched), 0)
        self.assertTrue(all(not r["zone"] for r in unmatched))
        # This is coverage of reported positive source values, not all NY output.
        coverage = ep.read_csv(self.output / "epa_snapshot_coverage.csv")
        self.assertTrue(all(float(r["gross_zone_unmatched_mwh"]) == 0 for r in coverage))
        self.assertTrue(all(r["complete_NYISO_generation_coverage"] == "False" for r in coverage))

    def test_08_primary_2025_identity_and_CHP_exclusion(self):
        cricket = [r for r in self.rows if r["scenario_id"] == "S1_2025_SUMMER_PEAK_PUBLIC" and r["facility_id"] == "57185"]
        self.assertEqual({r["unit_id"] for r in cricket}, {"U001", "U002", "U003"})
        self.assertTrue(all(r["zone"] == "G" and r["epa_county"] == "Dutchess County" for r in cricket))
        self.assertTrue(all("ST" in r["epa_associated_generators_nameplate"] for r in cricket))
        riverbay = [r for r in self.rows if r["facility_id"] == "52168"]
        self.assertTrue(all(r["grid_fossil_share_eligible"] == "False" for r in riverbay))
        self.assertGreater(sum(float(r["gross_generation_mwh"] or 0) for r in riverbay), 0)

    def test_09_zonal_partition_conserves_all_present_gross(self):
        zones = ep.read_csv(self.output / "epa_zonal_gross_generation.csv")
        for s in self.scenarios:
            sid = s["scenario_id"]
            unit = [r for r in self.rows if r["scenario_id"] == sid]
            zone = [r for r in zones if r["scenario_id"] == sid]
            self.assertEqual({r["zone"] for r in zone}, set("ABCDEFGHIJK") | {"UNMAPPED"})
            self.assertAlmostEqual(sum(float(r["gross_generation_mwh"] or 0) for r in unit),
                                   sum(float(r["all_reported_gross_clock_hour_mw"]) for r in zone), places=8)
            self.assertAlmostEqual(sum(float(r["gross_generation_mwh"] or 0) for r in unit if r["grid_fossil_share_eligible"] == "True"),
                                   sum(float(r["grid_eligible_gross_clock_hour_mw"]) for r in zone), places=8)

    def test_10_selector_rejects_duplicate_and_wrong_state(self):
        row = self.selected[0]
        raw = base64.b64decode(row["source_record_base64"])
        original_fields = [k for k in row if not k.startswith("source_")]
        header = io.StringIO()
        csv.writer(header, lineterminator="\n").writerow(original_fields)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.csv"
            path.write_bytes(header.getvalue().encode() + raw + raw)
            s = [{"epa_date": row["Date"], "epa_hour": row["Hour"]}]
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                ep.select_records(path, s)
            path.write_bytes(header.getvalue().encode() + raw.replace(b'"NY"', b'"NJ"', 1))
            with self.assertRaisesRegex(ValueError, "Non-NY"):
                ep.select_records(path, s)

    def test_11_source_manifest_pins_and_independence(self):
        manifest = json.loads((self.output / "epa_source_manifest.json").read_text())
        self.assertFalse(manifest["internal_interface_observations_read"])
        self.assertFalse(manifest["unit_row_expansion"])
        self.assertFalse(manifest["source_gross_is_net"])
        for item in manifest["extracts"]:
            self.assertEqual(ep.sha256(self.output/item["filename"]), item["sha256"])
        # Raw caches are optional in CI; if present, also verify original bytes.
        for name, spec in ep.SPECS.items():
            path = ep.CACHE/name
            if path.exists():
                self.assertEqual(ep.sha256(path), spec[1])
        self.assertTrue(all(not r["net_generation_mw"] for r in self.rows))

    def test_12_independent_offline_replay_and_artifact_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/"epa"
            shutil.copytree(self.output, folder)
            before = ep.sha256(folder/"epa_generation_hourly.csv")
            ep.build(output=folder, replay=True)
            self.assertEqual(ep.sha256(folder/"epa_generation_hourly.csv"), before)
            with (folder/"selected_epa_source_rows_2025.csv").open("a") as f:
                f.write("\n")
            with self.assertRaisesRegex(ValueError, "Pinned extract changed"):
                ep.build(output=folder, replay=True)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EPAGenerationInputsTests))
    report = dict(test_groups_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  passed=result.wasSuccessful(), code_sha256=ep.sha256(ep.ROOT / "build_compact_epa_generation_inputs.py"),
                  test_code_sha256=ep.sha256(Path(__file__)))
    (ep.OUTPUT / "epa_generation_input_tests.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
