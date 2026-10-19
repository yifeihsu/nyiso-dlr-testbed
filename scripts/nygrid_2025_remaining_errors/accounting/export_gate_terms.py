"""Expose current qualified cut terminal terms without re-solving any case."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output/nygrid_2025_remaining_errors/accounting"
SOURCE = ROOT / "output/nygrid_2025_ac_loss_revision/comparison/combined/comparison_arrays.npz"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = np.load(SOURCE, allow_pickle=False); q = data["revised_qualified"]
    assert q.sum() == 8170 and np.isfinite(data["observed"][q]).all()
    gamma = float(data["gamma"]); rows = []
    regions = ["A", "A+B", "A+B+C+D+E", "D", "A+B+C+D+E", "A+B+C+D+E+F+G", "I"]
    for j, name in enumerate(data["interface_names"]):
        primary = data["revised_legacy_signed_literal_from"][q, j]
        source = data["revised_oriented_source_side"][q, j]
        target = data["revised_oriented_target_side"][q, j]
        midpoint = (source + target) / 2; correction = primary - midpoint
        observed = data["observed"][q, j]
        rows.append(pd.DataFrame({"hour_index": data["hour_index"][q], "timestamp_utc": data["timestamp_utc"][q],
            "interface": str(name), "analysis_zone_set": regions[j], "complete_NY_cut": j in [0,1,2,3,5],
            "primary_public_MW": primary, "midpoint_public_MW": midpoint,
            "source_side_public_MW": source, "target_side_public_MW": target,
            "signed_half_loss_correction_public_MW": correction, "included_corridor_loss_public_MW": source-target,
            "observed_public_numeric_MW": observed, "primary_minus_observed_public_MW": primary-observed,
            "observed_minus_midpoint_public_MW": observed-midpoint,
            "required_net_correction_if_primary_terminal_effect_held_MW": observed-midpoint-correction,
            "primary_model_MW": primary*gamma, "midpoint_model_MW": midpoint*gamma,
            "gamma": gamma}))
    frame = pd.concat(rows, ignore_index=True)
    path = OUT / "current_gate_terms.csv"; frame.to_csv(path, index=False)
    receipt = {"passed": True, "qualified_hours": 8170, "rows": len(frame), "scope": "Current saved gate terminal conventions and conditional oracle terms",
        "important_interpretation": "Observed-minus-midpoint assumes a midpoint measurement convention. If the frozen primary terminal correction is held, the required net-input correction is observed-minus-primary. Neither is a causal attribution or verified physical meter mapping.",
        "source": {"path": SOURCE.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest()},
        "output": {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
        "new_PF_or_annual_run": False, "raw_monthly_zonal_balance_validation": "separate accounting analysis"}
    (OUT / "gate_terms_receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
    print(json.dumps({"passed": True, "rows": len(frame), "path": str(path)}))


if __name__ == "__main__": main()
