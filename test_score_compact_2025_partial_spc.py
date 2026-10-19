"""Protect diagnostic scoring from target leakage and identity mistakes."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import score_compact_2025_partial_spc as scorer


class DiagnosticScoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "variant"
        self.folder.mkdir()
        (self.folder / "campaign.mat").write_bytes(b"saved numerical evidence fixture")
        pd.DataFrame([{"artifact": "campaign.mat", "sha256": scorer.digest(self.folder / "campaign.mat")}]).to_csv(
            self.folder / "campaign_manifest.csv", index=False)
        self.flows = pd.DataFrame([{"variant_id": "nominal", "scenario_id": "S", "interface_name": "I",
                                   "model_flow_mw": 130, "target_flow_mw": float("nan"), "used_in_optimizer": False,
                                   "residual_mw": float("nan"), "absolute_residual_mw": float("nan"),
                                   "electrically_qualified": True}])
        self.target_folder = self.root / "output/compact_ny_2025/generation_reconstruction"
        self.target_folder.mkdir(parents=True)
        self.targets = pd.DataFrame([{"scenario_id": "S", "interface_name": "I", "model_flow_mw": 160,
                                     "target_flow_mw": 100, "actual_flow_mw": 200, "scale_factor_gamma": .5,
                                     "target_coverage_qualified": True, "absolute_residual_mw": 60}])

    def run_score(self):
        self.flows.to_csv(self.folder / "target_free_interface_flows.csv", index=False)
        self.targets.to_csv(self.target_folder / "scored_interface_comparison.csv", index=False)
        with patch.object(scorer, "ROOT", self.root):
            return scorer.score(self.folder)

    def test_signed_error_and_no_fresh_claim(self):
        report = self.run_score()
        result = pd.read_csv(self.folder / "revisited_interface_comparison.csv")
        self.assertEqual(result.iloc[0].residual_mw, 30)
        self.assertFalse(report["fresh_holdout_validation"])
        self.assertFalse(report["historical_as_operated_reconstruction"])

    def test_changed_campaign_rejected(self):
        (self.folder / "campaign.mat").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            self.run_score()

    def test_duplicate_identity_rejected(self):
        self.flows = pd.concat([self.flows, self.flows], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.run_score()

    def test_target_leakage_rejected(self):
        self.flows.loc[0, "target_flow_mw"] = 100
        with self.assertRaisesRegex(ValueError, "target-free"):
            self.run_score()

    def test_unqualified_prediction_not_scored(self):
        self.flows.loc[0, "electrically_qualified"] = False
        report = self.run_score()
        result = pd.read_csv(self.folder / "revisited_interface_comparison.csv")
        self.assertEqual(report["scored_prediction_rows"], 0)
        self.assertTrue(pd.isna(result.iloc[0].residual_mw))

    def test_missing_comparison_hour_rejected(self):
        self.flows.loc[0, "scenario_id"] = "unknown"
        with self.assertRaisesRegex(ValueError, "registered comparison"):
            self.run_score()


if __name__ == "__main__":
    unittest.main()
