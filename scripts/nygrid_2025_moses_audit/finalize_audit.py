"""Check the source-backed correction and fingerprint its separate delivery."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_moses_audit"
MANIFEST = OUT / "delivery_manifest.json"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def check_records(records):
    for item in records:
        path = Path(item["path"])
        path = path if path.is_absolute() else ROOT / path
        require(path.is_file() and sha(path) == item["sha256"], "Stale evidence: " + str(path))


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def finalize(verify=False):
    repair = read("corrected/fleet/repair_receipt.json")
    require(repair["corrected_plants"] == 26 and repair["corrected_admitted_dispatch_rows"] == 46,
            "Confirmed repair scope changed")
    require(repair["original_outputs_unchanged"] and not repair["hourly_PG_prior_bounds_modified"],
            "Repair no longer preserves frozen dispatch")
    check_records([dict(path=k, sha256=v) for k, v in repair["source_hashes"].items()])
    require(sha(OUT / "corrected/fleet/fleet_register.csv") == repair["fleet_register_sha256"], "Corrected fleet changed")
    for name in ["generation/source_manifest.csv", "corrected/fleet/source_manifest.csv"]:
        check_records(pd.read_csv(OUT / name).to_dict("records"))
    mapping = read("mapping/summary.json")
    require(mapping["failed_checks"] == 0 and mapping["confirmed_numerical_mapping_or_channel_bugs"] == [],
            "Mapping audit failed")
    check_records(read("mapping/manifest.json")["inputs"])
    source_review = read("mapping/generation_and_dc_control_review.json")
    require(source_review["failed_checks"] == 0, "Independent source/control review failed")
    check_records(source_review["inputs"])
    exchange = read("exchanges/exchange_audit_summary.json")
    require(exchange["signed_HQ_injection_preserved"] and exchange["signed_four_DC_schedules_preserved"],
            "External accounting failed")
    check_records(exchange["frozen_inputs"])
    require(sha(ROOT / "scripts/nygrid_2025_moses_audit/exchange_audit.py") == exchange["audit_script_sha256"],
            "Exchange code differs from audited version")
    replay = read("replay/provenance.json")
    require(replay["passed"] and replay["common_qualified_hours"] == 8663 and len(replay["variants"]) == 8,
            "Annual replay scope changed")
    check_records(replay["dependencies"])
    check_records([dict(path=r["file"], sha256=r["sha256"]) for r in replay["variants"]])
    require(not any(r["par_orientation_is_promoted"] for r in replay["variants"]), "Unverified PAR orientation was promoted")
    annual = read("validation/annual_validation.json")
    require(annual["failed_checks"] == 0 and annual["all_inputs_unchanged"] and annual["annual_variants"] == 8,
            "Independent annual validation failed")
    check_records(annual["inputs"])
    matlab = read("validation/matlab_validation.json")
    require(matlab.get("passed", False), "MATPOWER validation did not pass")
    if "dependencies" in matlab:
        check_records(matlab["dependencies"])
    score = read("comparison/scoring_receipt.json")
    require(score["passed"] and score["observations_used_only_posthoc"], "Scoring is not qualified")
    require(score["replay_provenance_sha256"] == sha(OUT / "replay/provenance.json"), "Stale scoring receipt")
    require(score["code_sha256"] == sha(ROOT / "scripts/nygrid_2025_moses_audit/replay_corrections.py"), "Scoring code changed")
    require(score["observation_source_sha256"] == sha(ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv"),
            "Observed interfaces changed")
    figures = read("figures/figure_validation.json")
    require(figures["passed"] and not figures["diagnostic_orientation_selected"], "Figure scope or verification failed")
    check_records(figures["inputs"])
    check_records(figures["outputs"])
    files = [p for folder in [OUT, ROOT / "scripts/nygrid_2025_moses_audit"]
             for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p != MANIFEST]
    files += [ROOT / "NYGRID_2025_MOSES_SOUTH_DIAGNOSIS.md",
              ROOT / "System Matpower Format/npcc_nygrid_2025_moses_corrected_dc.m"]
    entries = []
    for path in sorted(files):
        require(path.stat().st_size < 100 * 1024**2, "Oversized artifact: " + str(path))
        entries.append(dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
    result = dict(status="verified_source_backed_hydro_zone_repair_with_unpromoted_PAR_diagnostics",
                  qualified_hours=8663, buses=148, original_buses=140, added_buses=8,
                  confirmed_plants=26, admitted_generator_rows_moved=46,
                  frozen_inputs_builders_and_numerical_outputs_preserved=True,
                  PAR_direction_or_physical_tap_qualification=False,
                  files=len(entries), total_bytes=sum(r["bytes"] for r in entries),
                  maximum_file_bytes=max(r["bytes"] for r in entries), entries=entries)
    if verify:
        require(read("delivery_manifest.json") == result, "Delivery manifest is stale")
    else:
        MANIFEST.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "entries"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    finalize(parser.parse_args().verify)
