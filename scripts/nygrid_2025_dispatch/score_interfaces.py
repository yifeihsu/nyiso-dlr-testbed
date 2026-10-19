"""Post-hoc 2025 interface baseline; observations never enter reconstruction.

These are the inherited2019 interface operators, not certified physical2025
flowgate definitions. Scores diagnose a fixed-topology starting point only.
"""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "output/nygrid_2025_dispatch/dispatch"
NAMES = ["DYSINGER EAST", "WEST CENTRAL", "TOTAL EAST", "MOSES SOUTH", "CENTRAL EAST - VC", "UPNY CONED", "SPR/DUN-SOUTH"]


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def score(folder):
    folder = Path(folder).resolve()
    contract = json.loads((folder / "contract.json").read_text())
    assert contract["internal_interface_observations_read"] is False
    path = folder / "dispatch.mat"
    d = loadmat(path, simplify_cells=True, variable_names=["hour_index", "timestamp_utc", "gamma", "dispatch_qualified"])
    network_path = folder / "dispatch_network.mat"
    network = loadmat(network_path, simplify_cells=True, variable_names=["hour_index", "inherited_interface_pf"])
    assert np.array_equal(d["hour_index"], network["hour_index"])
    source_path = ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv"
    observed = pd.read_csv(source_path)
    assert np.array_equal(np.asarray(d["timestamp_utc"]).astype(str), observed.timestamp_utc.astype(str))
    predicted = network["inherited_interface_pf"]
    actual = observed[NAMES].to_numpy(float)
    gamma = float(d["gamma"])
    valid = np.asarray(d["dispatch_qualified"], bool) & np.isfinite(actual).all(axis=1)
    assert valid.any()
    rows, summaries = [], []
    for j, name in enumerate(NAMES):
        p = predicted[valid, j] / gamma
        y = actual[valid, j]
        e = p-y
        summaries.append(dict(interface=name, hours=int(valid.sum()), public_equivalent_mae_mw=float(abs(e).mean()),
            public_equivalent_rmse_mw=float(np.sqrt(np.mean(e**2))), public_equivalent_bias_mw=float(e.mean()),
            wape_percent=float(100*abs(e).sum()/abs(y).sum()), actual_mean_absolute_mw=float(abs(y).mean()),
            observation_used_for_dispatch=False, physical_2025_interface_mapping_verified=False))
        f = pd.DataFrame(dict(hour_index=np.asarray(d["hour_index"]), timestamp_utc=observed.timestamp_utc,
            interface=name, scored=valid, observed_public_mw=actual[:, j],
            predicted_public_equivalent_mw=predicted[:, j]/gamma, predicted_model_mw=predicted[:, j]))
        rows.append(f)
    pd.DataFrame(summaries).to_csv(folder / "posthoc_interface_summary.csv", index=False, lineterminator="\n")
    pd.concat(rows, ignore_index=True).to_csv(folder / "posthoc_interface_hourly.csv.gz", index=False,
        lineterminator="\n", compression={"method":"gzip", "mtime":0})
    receipt = dict(scope="posthoc_inherited2019_interface_proxy_diagnostic", hours=int(valid.sum()),
        model_parameters_fitted_to_observations=False, predictions_sha256=digest(path),
        network_predictions_sha256=digest(network_path),
        reconstruction_contract_sha256=digest(folder / "contract.json"), observations_sha256=digest(source_path),
        scoring_code_sha256=digest(Path(__file__)), model_topology_year=2019, operating_source_year=2025,
        physical_2025_flowgate_membership_verified=False)
    (folder / "posthoc_scoring_receipt.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(pd.DataFrame(summaries).to_string(index=False))


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--folder", type=Path, default=DEFAULT)
    score(p.parse_args().folder)
