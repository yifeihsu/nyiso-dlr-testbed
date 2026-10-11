"""Check the verified-direction PAR research delivery and preserve its hashes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from replay_controls import verify_control_sources

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_par_controls"
MANIFEST = OUT / "delivery_manifest.json"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def check(records):
    for record in records:
        p = Path(record["path"])
        if not p.is_absolute():
            p = ROOT / p
        require(p.is_file() and sha(p) == record["sha256"], "Stale dependency: " + str(p))


def finalize(verify=False):
    inputs = np.load(OUT / "controls/inputs.npz", allow_pickle=False)
    compiler = read("controls/input_receipt.json")
    verify_control_sources(inputs, compiler)
    check(read("sources/direction/direction_manifest.json")["files"])
    limit_manifest = read("sources/limits/manifest.json")
    require(sha(OUT / "sources/limits/limits.json") == limit_manifest["contract_sha256"], "Equipment contract changed")
    check(limit_manifest["files"])
    replay = read("replay/provenance.json")
    require(replay["passed"] and len(replay["variants"]) == 2, "Incomplete replay")
    require(not replay["internal_interface_observations_used"] and not replay["full_physical_operating_limits_verified"],
            "Replay fitting or physical qualification scope changed")
    check(replay["dependencies"])
    check([dict(path=r["file"], sha256=r["sha256"]) for r in replay["variants"]])
    annual = read("validation/independent_validation.json")
    require(annual["passed"] and annual["hourly_topology_checks"] == 17326 and annual["annual_score_rows"] == 42,
            "Independent annual validation failed or changed cohort")
    check(annual["dependencies"])
    matlab = read("validation/matlab_validation.json")
    require(matlab["passed"] and matlab["fresh_MATPOWER_snapshots"] >= 31, "MATPOWER verification incomplete")
    require(matlab["missing_source_hour_rejected"] and not matlab["full_P_Q_thermal_or_tap_feasibility_certified"],
            "Loader qualification or scope changed")
    check(matlab["dependencies"])
    gate = read("validation/source_gate_validation.json")
    require(gate["tests_run"] >= 21 and gate["failures"] == 0 and gate["errors"] == 0, "Source-gate fixtures failed")
    check(gate["inputs"])
    figures = read("figures/figure_validation.json")
    require(figures["passed"] and not figures["internal_interface_fitting"]
            and not figures["hardware_taps_and_full_PQ_feasibility_claimed"], "Figure validation or qualifications failed")
    check(figures["inputs"]); check(figures["outputs"])
    score = read("comparison/scoring_receipt.json")
    require(score["passed"] and score["internal_observations_only_posthoc"], "Scoring scope changed")
    require(score["replay_provenance_sha256"] == sha(OUT / "replay/provenance.json"), "Scoring receipt is stale")
    require(score["code_sha256"] == sha(ROOT / "scripts/nygrid_2025_par_controls/replay_controls.py"), "Scoring code changed")
    require(score["observed_internal_sha256"] == sha(ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv"),
            "Internal observations changed")
    files = [p for folder in [OUT, ROOT / "scripts/nygrid_2025_par_controls"]
             for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p != MANIFEST]
    files += [ROOT / "NYGRID_2025_VERIFIED_PAR_CONTROLS.md",
              ROOT / "System Matpower Format/npcc_nygrid_2025_par_controlled_dc.m"]
    entries = []
    for p in sorted(files):
        require(p.stat().st_size < 100 * 1024**2, "Oversized delivery file: " + str(p))
        entries.append(dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=sha(p)))
    result = dict(status="verified_direction_and_nominal_P_screen_external_flow_conditioned_DC_reconstruction",
        buses=148, original_buses=140, added_buses=8, qualified_hours_each=8663,
        source_DC_records_preserved=4, ideal_PAR_transfer_records=2, physical_HVDC_added=0,
        complete_physical_PAR_operating_envelope_verified=False, actual_tap_trajectory_reconstructed=False,
        original_artifacts_preserved=True, files=len(entries), total_bytes=sum(r["bytes"] for r in entries),
        maximum_file_bytes=max(r["bytes"] for r in entries), entries=entries)
    if verify:
        require(read("delivery_manifest.json") == result, "Delivery manifest is stale")
    else:
        MANIFEST.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "entries"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--verify", action="store_true")
    finalize(parser.parse_args().verify)
