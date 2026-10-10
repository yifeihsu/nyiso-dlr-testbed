"""Focused checks for unit/hour grain, reporting semantics, and allocation."""
import datetime as dt
import json
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generation_priors as g


class GenerationSourceTests(unittest.TestCase):
    def test_physical_hour_axis_and_dst(self):
        a = g.hour_axis()
        self.assertEqual(len(a), 8760)
        self.assertEqual(a.iloc[0].timestamp_utc, "2025-01-01T05:00:00Z")
        self.assertEqual(a.iloc[-1].timestamp_utc, "2026-01-01T04:00:00Z")
        fall = a[a.timestamp_local == "2025-11-02 01:00:00"]
        self.assertEqual(set(fall.time_zone), {"EDT", "EST"})
        self.assertEqual(len(a[a.timestamp_local == "2025-03-09 02:00:00"]), 0)

    def test_metered_interval_integration_and_gap(self):
        samples = [(0, 0)] + [(t, 100 if t <= 1800 else 200) for t in range(300, 3601, 300)]
        p, c, q, *_ = g.integrate_hourly(samples, 0, 1)
        self.assertAlmostEqual(p[0], 150); self.assertEqual(c[0], 3600); self.assertTrue(q[0])
        p, c, q, *_ = g.integrate_hourly([(0, 1), (900, 2), (1200, 3)], 0, 1)
        self.assertTrue(np.isnan(p[0])); self.assertEqual(c[0], 300); self.assertFalse(q[0])

    def test_utc_clock_disambiguates_repeated_civil_hour(self):
        early = g.utc_seconds("11/02/2025 01:00:00", "EDT")
        late = g.utc_seconds("11/02/2025 01:00:00", "EST")
        self.assertEqual(late - early, 3600)

    def test_conflicting_samples_fail(self):
        with self.assertRaises(ValueError):
            g.integrate_hourly([(0, 1), (0, 2)], 0, 1)

    def test_duplicate_equal_sample_does_not_double_energy(self):
        s = [(t, 5) for t in range(0, 3601, 300)]
        result = g.integrate_hourly(s + [(300, 5)], 0, 1)
        self.assertEqual(result[0][0], 5); self.assertEqual(result[-1], 1)

    def test_epa_partial_operation_and_blank(self):
        self.assertEqual(g.epa.convert_gross({"Gross Load (MW)": "100", "Operating Time": "0.25"})[2], 25)
        value = g.epa.convert_gross({"Gross Load (MW)": "", "Operating Time": "0"})
        self.assertIsNone(value[2]); self.assertEqual(value[3], "reported_offline_gross_blank")

    def test_crosswalk_many_to_many_does_not_create_output_rows(self):
        rows = [dict(facility_id="2682", unit_id="20", zone="A", source_excel_row=i,
                     nyiso_ptid=str(1658 + i % 2)) for i in [61, 62, 63]]
        value = g.epa.map_unit("2682", "20", g.epa.mapping_indices(rows, []))
        self.assertEqual(value["zone"], "A")
        self.assertEqual(value["nygrid_crosswalk_rows"], "61|62|63")

    def test_unqualified_prior_not_zero(self):
        p, s, ok = g.normalise_weights([1, 3], 100, False)
        self.assertFalse(ok); self.assertTrue(np.isnan(p).all())
        self.assertAlmostEqual(s.sum(), 1)

    def test_qualified_prior_conserves_independent_total(self):
        p, s, ok = g.normalise_weights([2, 3, 5], 370, True)
        self.assertTrue(ok); self.assertTrue(np.allclose(p, [74, 111, 185])); self.assertEqual(p.sum(), 370)

    def test_nrc_daily_parser_and_conflict(self):
        text = b"ReportDt|Unit|Power\n01/01/2025 12:00:00 AM|Ginna|90\n"
        values = g.parse_nrc_year(text)
        self.assertEqual(values[(dt.date(2025, 1, 1), "Ginna")], 90)
        self.assertEqual(g.parse_nrc_year(b"ReportDt|Unit|Power\n1/9/2025 12:00:00 AM|Ginna|95\n")[(dt.date(2025, 1, 9), "Ginna")], 95)
        with self.assertRaises(ValueError):
            g.parse_nrc_year(text + b"01/01/2025|Ginna|80\n")

    def test_retirement_month_is_not_reactivated(self):
        r = dict(operating_year=1974, operating_month=8, source_status="RE", retirement_year=2020, retirement_month=4)
        self.assertFalse(g.nf.is_active(r, dt.datetime(2025, 1, 1)))

    def test_hydro_negative_net_pumping_not_used_as_generation(self):
        p, ok = g.nf.bounded_hydro_projection([80, 0], [100, 50], 120)
        self.assertTrue(ok); self.assertAlmostEqual(sum(p), 120)
        self.assertGreater(p[1], 0)
        p, ok = g.nf.bounded_hydro_projection([80, 0], [100, 50], 160)
        self.assertFalse(ok); self.assertTrue(np.isnan(p).all())

    def test_independent_epa_daily_quantity_fixture(self):
        folder = g.ROOT / "output/compact_ny_2025/generation_sources/epa"
        result = g.epa.quantity_audit(g.epa.read_csv(folder / "quantity_audit_hourly_source.csv"),
                                    g.epa.read_csv(folder / "quantity_audit_daily_source.csv"))
        self.assertAlmostEqual(result[0]["weighted_clock_hour_energy_mwh"], 951.75)
        self.assertAlmostEqual(result[0]["unweighted_error_mwh"], 23.25)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(GenerationSourceTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    g.OUT.mkdir(parents=True, exist_ok=True)
    (g.OUT / "generation_tests.json").write_text(json.dumps(dict(
        tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        passed=result.wasSuccessful(), generation_script_sha256=g.sha(Path(g.__file__)),
        test_script_sha256=g.sha(Path(__file__))), indent=2) + "\n")
    sys.exit(0 if result.wasSuccessful() else 1)
