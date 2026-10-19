"""Create/verify final file fingerprints without rerunning reconstruction."""
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_dispatch"


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def finalize(verify=False):
    path = OUT / "delivery_manifest.json"
    if verify:
        data = json.loads(path.read_text())
        for row in data["files"]:
            p = ROOT / row["path"]
            assert p.stat().st_size == row["bytes"] and sha(p) == row["sha256"], row["path"]
        print(f"Verified {len(data['files'])} delivered files.")
        return
    independent = json.loads((OUT / "validation/validation_summary.json").read_text())
    matlab = json.loads((OUT / "dispatch/matlab_validation.json").read_text())
    rebuild = json.loads((OUT / "validation/rebuild_comparison.json").read_text())
    dispatch = json.loads((OUT / "dispatch/summary.json").read_text())
    assert independent["passed"] and matlab["passed"] and rebuild["passed"]
    assert dispatch["all_source_qualified_hours_solved"] and dispatch["capacity_infeasible_hours"] == 0
    assert dispatch["ac_feasibility_validated"] is False and dispatch["topology_changed"] is False
    contract = json.loads((OUT / "dispatch/contract.json").read_text())
    for row in independent["files"] + contract["provenance"]:
        assert sha(ROOT / row["path"]) == row["sha256"], "Changed validated input: " + row["path"]
    for name, digest in dispatch["file_sha256"].items():
        assert sha(OUT / "dispatch" / name) == digest, name
    for row in matlab["input_files"]:
        assert sha(OUT / "dispatch" / row["name"]) == row["sha256"], row["name"]
    assert sha(ROOT / "System Matpower Format/npcc_nygrid_2025_full_dc.m") == matlab["loader_sha256"]
    assert sha(ROOT / "scripts/nygrid_2025_dispatch/validate_matlab_dispatch.m") == matlab["validation_code_sha256"]
    excluded = {"initial_pre_ba_filter", "initial_pre_nj_native_extension", "archive_ny_state_only_20261010"}
    files = [p for p in OUT.rglob("*") if p.is_file() and p != path and not excluded.intersection(p.parts)]
    files += [p for p in (ROOT / "scripts/nygrid_2025_dispatch").iterdir() if p.is_file()]
    files += [ROOT / "System Matpower Format/npcc_nygrid_2025_full_dc.m", ROOT / "NYGRID_2025_BOUNDED_DISPATCH.md"]
    records = [dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(set(files))]
    assert all(r["bytes"] < 100 * 1024**2 for r in records), "Split an oversized artifact before delivery"
    result = dict(scope="capacity-bounded independent hourly DC reconstruction; unchanged2019 full NPCC network",
        qualified_hours=dispatch["dispatched_hours"], source_gap_hours=dispatch["missing_source_hours"],
        independent_validation_passed=True, fresh_matpower_replay_passed=True, separate_rebuild_exact=True,
        topology_changed=False, ac_feasibility_validated=False, internal_interface_targets_used_for_dispatch=False,
        local_history_excluded="initial_pre_ba_filter, initial_pre_nj_native_extension and archive_ny_state_only_20261010 are optional intermediate history, not delivered/reproduction inputs",
        files=records)
    path.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(f"Fingerprinted {len(records)} delivered files.")


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--verify", action="store_true")
    finalize(p.parse_args().verify)
