"""Fingerprint or verify the delivered source, model-input and validation files.

This does not change numeric data, fill gaps, run dispatch, or expand any
scientific qualification beyond the recorded input-accounting validations.
"""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_inputs"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_reconciliation():
    d = loadmat(OUT / "model/operating_inputs.mat", simplify_cells=True,
                variable_names=["ny_balance_residual_public_mw", "gamma", "boundary_hour_qualified",
                                "zonal_generation_prior_qualified", "timestamp_utc"])
    residual = d["ny_balance_residual_public_mw"]
    valid = np.isfinite(residual)
    prior_ok = d["zonal_generation_prior_qualified"].astype(bool).all(axis=(1, 2))
    boundary_ok = d["boundary_hour_qualified"].astype(bool)
    summary = dict(meaning="Source reconciliation: statewide reported generation + ten scheduled import channels - gross NYISO load; not a power-flow balance",
        finite_reconciliation_hours=int(valid.sum()),
        joint_prior_and_boundary_qualified_hours=int((prior_ok & boundary_ok).sum()),
        mean_public_mw=float(residual[valid].mean()), mean_absolute_public_mw=float(abs(residual[valid]).mean()),
        minimum_public_mw=float(residual[valid].min()), maximum_public_mw=float(residual[valid].max()),
        gamma=float(d["gamma"]), residual_assigned_to_generator=False,
        possible_sources=["scheduled rather than actual interchange", "system loss and reporting scope differences",
                          "declared timing/aggregation conventions"], causal_attribution_established=False)
    (OUT / "validation/source_reconciliation.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    pd.DataFrame(dict(hour_index=np.arange(1, 8761), timestamp_utc=d["timestamp_utc"],
        source_balance_residual_public_mw=residual, source_balance_residual_model_mw=residual * d["gamma"],
        source_components_qualified=valid, all_priors_and_boundaries_qualified=prior_ok & boundary_ok)).to_csv(
            OUT / "validation/source_reconciliation.csv", index=False, lineterminator="\n")


def finalize(verify=False):
    receipt = OUT / "delivery_manifest.json"
    if verify:
        manifest = json.loads(receipt.read_text())
        for row in manifest["files"]:
            path = ROOT / row["path"]
            assert path.stat().st_size == row["bytes"] and digest(path) == row["sha256"], row["path"]
        print(f"Verified {len(manifest['files'])} delivered files.")
        return
    validation = json.loads((OUT / "validation/validation_summary.json").read_text())
    matlab = json.loads((OUT / "model/matlab_accessor_validation.json").read_text())
    rebuild = json.loads((OUT / "validation/rebuild_comparison.json").read_text())
    assert validation["passed"] and matlab["passed"] and rebuild["passed"]
    assert validation["ready_for_dc_power_flow"] is False and matlab["power_flow_tested"] is False
    source_reconciliation()
    paths = [p for p in OUT.rglob("*") if p.is_file() and p != receipt]
    paths.extend(p for p in (ROOT / "scripts/nygrid_2025_inputs").iterdir() if p.is_file())
    paths.extend([ROOT / "NYGRID_2025_OPERATING_INPUTS.md",
                  ROOT / "System Matpower Format/npcc_nygrid_2025_operating_inputs.m"])
    files = [dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=digest(p))
             for p in sorted(set(paths))]
    manifest = dict(scope="2025 source and scaled operating inputs; not a completed operating case",
                    input_validation_passed=True, matlab_accessor_passed=True,
                    separate_rebuild_numeric_match=True, ready_for_dc_power_flow=False,
                    files=files)
    receipt.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Fingerprinted {len(files)} delivered files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    finalize(parser.parse_args().verify)
