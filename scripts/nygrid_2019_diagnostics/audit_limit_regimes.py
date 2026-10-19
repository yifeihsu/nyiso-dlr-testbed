"""Check whether western error is confined to changed published limit levels.

Published limit levels are not an outage-status or control-state inventory.
This is a descriptive comparison, not causal attribution or a model change.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2019_diagnostics"


def run():
    data = pd.concat([pd.read_csv(ROOT / f"output/nygrid_2019/annual_{q}_interfaces.csv")
                      for q in range(1, 5)], ignore_index=True)
    west = data[data.interface == "Dysinger East"].copy()
    assert len(west) == 8760 and west.timestamp.nunique() == 8760
    west["error_mw"] = west.corrected_operator_mw - west.observed_mw
    grouped = west.groupby("positive_limit_mw").agg(
        hours=("error_mw", "size"), mae_mw=("error_mw", lambda s: s.abs().mean()),
        bias_sim_minus_observed_mw=("error_mw", "mean"), observed_mean_mw=("observed_mw", "mean"))
    assert grouped.hours.sum() == 8760
    grouped.to_csv(OUT / "western_limit_regimes.csv", lineterminator="\n")
    print(grouped.loc[[3150.0]].to_string())


if __name__ == "__main__":
    run()
