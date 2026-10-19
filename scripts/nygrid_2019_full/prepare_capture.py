"""Prepare an isolated, instrumented copy of the pinned NYgrid constructor.

Only the function name/outputs and two stage snapshots are added. Data files
are linked read-only by convention into a separate runtime directory; all
released writes therefore land in that runtime's Result directory.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tmp/nygrid_2019_reproduction/upstream"
CACHED = ROOT / "tmp/nygrid_2019_reproduction/cached_upstream"
OUT = ROOT / "output/nygrid_2019_full_stage1"
PIN = "47698b6c7823ae7b1bc6935e5601d5b64b8f918e"
REDUCTION_PIN = "cbd61ad03308c31faecffa3d8d3259121bdc1aa4"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_output(output: Path) -> Path:
    """Keep alternate builds inside this repository and away from inputs."""
    output = (ROOT / output if not output.is_absolute() else output).resolve()
    if output == ROOT or not output.is_relative_to(ROOT):
        raise ValueError("Output must be a directory inside the repository")
    protected = [SOURCE, CACHED, ROOT / "tmp/nygrid_2019_reproduction/reduction_toolbox",
                 ROOT / "output/nygrid_2019", ROOT / "scripts", ROOT / "System Matpower Format"]
    for path in protected:
        path = path.resolve()
        if output.is_relative_to(path) or path.is_relative_to(output):
            raise ValueError(f"Output overlaps a source or input directory: {path}")
    return output


def prepare(output: Path = OUT) -> dict:
    output = resolve_output(output)
    runtime = (output / "capture_runtime").resolve()
    if not runtime.is_relative_to(output):
        raise ValueError("Capture runtime must remain inside the selected output directory")
    upstream = json.loads((ROOT / "output/nygrid_2019/upstream_manifest.json").read_text())
    assert upstream["commit"] == PIN
    for record in upstream["files"]:
        data = (SOURCE / record["path"]).read_bytes()
        assert sha(data) == record["sha256"], record["path"]
        assert hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() == record["git_blob_sha1"]
    cached = json.loads((ROOT / "output/nygrid_2019/cached_upstream_manifest.json").read_text())
    for record in cached["files"]:
        assert sha((CACHED / record["relative_path"]).read_bytes()) == record["generated_sha256"], record["relative_path"]
    for record in cached["added_helpers"]:
        assert sha((CACHED / record["generated_path"]).read_bytes()) == record["sha256"]
    reduction = json.loads((ROOT / "output/nygrid_2019/toolbox_manifest.json").read_text())
    assert reduction["selected_commit"] == REDUCTION_PIN
    assert reduction["selected_path"] == "tmp/nygrid_2019_reproduction/reduction_toolbox/mirror"
    for record in reduction["mirror"]["files"]:
        data = (ROOT / reduction["selected_path"] / record["relative_path"]).read_bytes()
        assert sha(data) == record["sha256"], record["relative_path"]
        assert hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() == record["git_blob_sha1"]

    original = (CACHED / "updateOpCond.m").read_bytes()
    text = original.decode("utf-8")
    header = "function mpcreduced = updateOpCond(mpc,timeStamp,savedata,verbose,usemat)"
    replacement = "function [mpcreduced,full_mpc,reduced_pre_hvdc] = nygrid_full_updateOpCond(mpc,timeStamp,savedata,verbose,usemat)"
    reduction_call = "[mpcreduced,~,~] = MPReduction(mpc,Exbus,pf_flag);"
    newline = "\r\n" if "\r\n" in text else "\n"
    instrumented = "full_mpc = mpc; % capture only; released calculation is unchanged" + newline + reduction_call + newline + "reduced_pre_hvdc = mpcreduced; % capture only"
    assert text.count(header) == 1 and text.count(reduction_call) == 1
    generated = text.replace(header, replacement).replace(reduction_call, instrumented)
    # A reversible exact-text check guards against accidental model changes.
    assert generated.replace(replacement, header).replace(instrumented, reduction_call) == text
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "nygrid_full_updateOpCond.m").write_bytes(generated.encode("utf-8"))
    data_records = []
    for source in sorted((CACHED / "Data").rglob("*")):
        if not source.is_file():
            continue
        destination = runtime / "Data" / source.relative_to(CACHED / "Data")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            os.link(source, destination)
        assert sha(destination.read_bytes()) == sha(source.read_bytes())
        data_records.append({"path": destination.relative_to(ROOT).as_posix(), "source_path": source.relative_to(ROOT).as_posix(), "sha256": sha(source.read_bytes()), "hardlink": os.path.samefile(source, destination)})
    patch = "\n".join(difflib.unified_diff(text.splitlines(), generated.splitlines(), fromfile="cached_upstream/updateOpCond.m", tofile="capture_runtime/nygrid_full_updateOpCond.m", lineterm="")) + "\n"
    (output / "capture_instrumentation.patch").write_text(patch, encoding="utf-8")
    manifest = {
        "source_commit": PIN,
        "verified_upstream_files": len(upstream["files"]),
        "verified_cached_files": len(cached["files"]),
        "reduction_commit": REDUCTION_PIN,
        "verified_reduction_files": len(reduction["mirror"]["files"]),
        "cached_function_sha256": sha(original),
        "instrumented_function_sha256": sha(generated.encode("utf-8")),
        "transformation_reverses_to_exact_cached_source": True,
        "transformation": ["rename function and add two outputs", "copy full mpc immediately before MPReduction", "copy reduced mpc immediately after MPReduction"],
        "model_arithmetic_changed": False,
        "source_or_existing_results_written": False,
        "runtime": runtime.relative_to(ROOT).as_posix(),
        "data_link_policy": "Only read by released import/load calls; never edit the linked files. Result writes remain in capture_runtime.",
        "data_files": data_records,
        "prepare_script_sha256": sha(Path(__file__).read_bytes()),
    }
    (output / "capture_preparation_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT,
                        help="Build directory inside the repository; relative paths resolve from repository root")
    args = parser.parse_args()
    result = prepare(args.output)
    print(json.dumps({key: result[key] for key in ["source_commit", "verified_upstream_files", "verified_cached_files", "transformation_reverses_to_exact_cached_source", "runtime"]}, indent=2))
