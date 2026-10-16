"""Inventory committed research, runtime data and referenced historical source captures.

This reads prior research without modifying it. The package builder owns archive
creation and must add the new handbook, runtime adapter and vendor manifests.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_dlr_handoff"
HEAD = "8188cbec1172219a0414881121ad042b405a4044"
EXCLUDED_COMPONENTS = {"node_modules", ".git", "__pycache__"}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == HEAD
    assert subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip() == "codex/s13-phase1b-upny-coned"
    entries = {}
    raw = subprocess.check_output(["git", "ls-tree", "-r", "-l", "-z", HEAD], cwd=ROOT)
    for item in raw.split(b"\0"):
        if not item: continue
        header, encoded_path = item.split(b"\t", 1)
        _, kind, blob, size = header.decode().split()
        if kind == "blob": entries[encoded_path.decode("utf-8")] = dict(git_blob=blob, bytes=int(size))

    def research(path):
        # The requested full history includes the earlier S7/S13/PackageA/B and
        # compact51/66/71 families, not only the latest NYgrid namespaces.
        if path.startswith("output/pdf/") and Path(path).suffix in {".aux", ".fdb_latexmk", ".fls", ".log", ".nav", ".out", ".snm", ".toc"}:
            return False
        return path.startswith(("output/", "scripts/", "System Matpower Format/", "PERFORM/", "ENLITEN-Grid-Econ-Data-main/")) or "/" not in path

    selected = {p for p in entries if research(p) and not (set(Path(p).parts) & EXCLUDED_COMPONENTS)}
    selected.update(p for p in entries if p.startswith("System Matpower Format/") and p.endswith(".m"))
    selected.update(p for p in ["PROJECT_HANDOFF.md", ".gitattributes", ".gitignore"] if p in entries)
    dependency_refs = defaultdict(set)
    external_refs = defaultdict(set)
    prefix = ROOT.as_posix() + "/"
    reference_keys = {"path", "file", "source_file", "source_path", "input_file", "archive", "original_path", "file_path", "absolute_path", "mat_file", "parent_path"}

    def walk(value, source):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in reference_keys and isinstance(item, str):
                    rel = item.replace("\\", "/")
                    if rel.startswith(prefix): rel = rel[len(prefix):]
                    if not rel.startswith(("http:", "https:", "data:")):
                        candidate = ROOT / rel
                        if candidate.is_file():
                            if candidate.resolve().is_relative_to(ROOT):
                                rel = candidate.resolve().relative_to(ROOT).as_posix()
                                if rel not in selected: dependency_refs[rel].add(source)
                            else: external_refs[candidate.as_posix()].add(source)
                walk(item, source)
        elif isinstance(value, list):
            for item in value: walk(item, source)

    for rel in sorted(selected):
        if rel.endswith(".json") and research(rel):
            try: walk(json.loads((ROOT / rel).read_text(encoding="utf-8-sig")), rel)
            except (ValueError, UnicodeError): pass
    # Preserve the complete, specifically identified original-author working
    # source tree (including README and prepared Data files), not arbitrary tmp.
    # This enables a source-level historical rebuild without silently relying
    # on unshipped files in the original author's local cache.
    historical_trees = ["tmp/nygrid_2019_reproduction/upstream", "tmp/nygrid_2019_reproduction/cached_upstream",
                        "tmp/nygrid_2019_reproduction/reduction_toolbox"]
    for folder in historical_trees:
        upstream = ROOT / folder
        for path in upstream.rglob("*"):
            if path.is_file() and not (set(path.relative_to(upstream).parts) & EXCLUDED_COMPONENTS):
                dependency_refs[path.relative_to(ROOT).as_posix()].add("scripts/nygrid_2019_full/prepare_capture.py")
    # Every included supplemental path was found in a concrete existing receipt.
    # No recursive tmp capture, personal download folder, or unrelated workspace
    # tree is selected by this inventory.
    supplement = {p for p in dependency_refs if not (set(Path(p).parts) & EXCLUDED_COMPONENTS)}
    selected.update(p for p in supplement if p in entries)
    files = []
    hash_to_paths = defaultdict(list)
    differences = []
    for rel in sorted(selected):
        path = ROOT / rel
        expected = entries[rel]
        data_size = path.stat().st_size
        h = hashlib.sha256(); git = hashlib.sha1()
        git.update(f"blob {data_size}\0".encode())
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024): h.update(block); git.update(block)
        exact = git.hexdigest() == expected["git_blob"]
        if exact:
            digest = h.hexdigest()
        else:
            committed = subprocess.check_output(["git", "cat-file", "blob", expected["git_blob"]], cwd=ROOT)
            assert len(committed) == expected["bytes"]
            digest = hashlib.sha256(committed).hexdigest()
            differences.append(dict(path=rel, working_bytes=data_size, baseline_bytes=expected["bytes"],
                                    working_sha256=h.hexdigest(), baseline_sha256=digest,
                                    difference_kind="line_endings_only" if path.read_bytes().replace(b"\r\n", b"\n") == committed.replace(b"\r\n", b"\n") else "content_difference",
                                    action="Use committed8188cbe bytes in package; preserve working file unchanged"))
        if rel.startswith("output/"):
            group = "/".join(rel.split("/")[:2])
        elif rel.startswith("scripts/"): group = "research_code"
        elif rel.startswith("System Matpower Format/"): group = "shared_MATLAB_code_and_historical_models"
        elif rel.startswith("ENLITEN-Grid-Econ-Data-main/"): group = "ENLITEN_original_source_with_GPL_notice"
        elif rel.startswith("PERFORM/"): group = "PERFORM_historical_reference_source"
        elif "/" not in rel: group = "root_reports_and_configuration"
        else: group = "referenced_tracked_source_support"
        record = dict(path=rel, group=group, bytes=expected["bytes"], sha256=digest, git_blob=expected["git_blob"],
                      copy_from_worktree_safe=exact, materialization="working_or_git_blob" if exact else "git_blob_required")
        files.append(record); hash_to_paths[digest].append(rel)

    historical_sources = []
    for rel in sorted(supplement - set(entries)):
        p = ROOT / rel; digest = sha(p)
        historical_sources.append(dict(path=rel, bytes=p.stat().st_size, sha256=digest,
            already_in_research_at_same_content=hash_to_paths.get(digest, []),
            recommended_target="source_archive/" + rel,
            role="curated_referenced_source_or_historical_capture; no unrelated tmp files",
            referenced_by=sorted(dependency_refs[rel]),
            baseline_git_tracked=False,
            needed_for_latest_default_runtime=False))
    external = []
    for path, sources in sorted(external_refs.items()):
        p = Path(path); digest = sha(p)
        external.append(dict(original_path=path, bytes=p.stat().st_size, sha256=digest,
            same_content_in_research=hash_to_paths.get(digest, []), referenced_by=sorted(sources),
            role="vendor_dependency" if "/matpower/" in path.lower() else "external_original_source_reference",
            automatic_external_copy_authorized_by_inventory=False))

    group_rows = []
    for name in sorted({f["group"] for f in files}):
        use = [f for f in files if f["group"] == name]
        group_rows.append(dict(group=name, count=len(use), bytes=sum(f["bytes"] for f in use)))
    data_closure_path = OUT / "runtime_data_closure.json"
    closure = json.loads(data_closure_path.read_text())
    assert len(closure["entries"]) == 30
    for item in closure["entries"]:
        assert sha(ROOT / item["path"]) == item["sha256"]
    history_unique = {x["sha256"]: x["bytes"] for x in historical_sources if not x["already_in_research_at_same_content"]}
    scan_paths = [p for p in selected if Path(p).suffix in {".m", ".py", ".js", ".mjs", ".ps1"}]
    credential_findings = []
    for rel in scan_paths:
        p = ROOT / rel
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        for num, line in enumerate(text.splitlines(), 1):
            if re.search(r"(?i)(api[_-]?key|authorization|bearer|access[_-]?token)", line):
                if "DEMO_KEY" in line:
                    kind = "public_DEMO_KEY_or_description; not a private credential"
                elif re.search(r"getenv|environ|process\.env|\$env:", line):
                    kind = "environment_variable_lookup; no credential value stored"
                elif line.lstrip().startswith(("#", "%", "//")):
                    kind = "comment_reference; no credential value stored"
                else:
                    kind = "requires_manual_classification; value not exported"
                credential_findings.append(dict(path=rel, line=num, classification=kind, value_exported=False))

    weather_files = [f["path"] for f in files if "weather" in Path(f["path"]).name.lower()]
    result = dict(
        schema_version=1, created_utc=datetime.now(timezone.utc).isoformat(), source_head=HEAD,
        checkout_branch="codex/s13-phase1b-upny-coned", prior_files_modified=False,
        scope="All committed NYgrid2019/2025, Marcy, S7/S13/S14 scaffolding, S8/S11, PackageA/B, compact51/66/71 source/results, relevant root reports, SystemMatpowerFormat source/evidence, PERFORM and ENLITEN parents; excludes unrelated package-manager caches and transient slide build products. New handoff/vendor files are appended by package builder.",
        selected_prior_file_count=len(files), selected_prior_bytes=sum(f["bytes"] for f in files),
        include_groups=group_rows, files=files,
        default_runtime_data=closure,
        existing_worktree_differences=differences,
        curated_untracked_historical_sources=historical_sources,
        curated_untracked_raw_bytes=sum(x["bytes"] for x in historical_sources),
        unique_historical_source_bytes_not_already_in_research=sum(history_unique.values()),
        explicit_curated_source_trees=historical_trees,
        external_references=external,
        excluded_unrelated_namespaces=[".git", "**/node_modules/**", "**/__pycache__/**", "output/pdf compiler scratch products", "unreferenced tmp/**", "unrelated user working changes", "personal credentials or runtime environment folders"],
        recommended_layout={
            "archive_root": "Preserve checkout-relative System Matpower Format/, scripts/, output/ and report paths",
            "runtime_archive": "Default30data files plus required MATLAB/API closure, thermal metadata, new portable helpers, START_HERE, handbook, selected current receipts, vendor/matpower8.1 with notices",
            "full_research_archive": "Runtime archive plus all inventory.files and curated source captures or verified same-content aliases; retains failed experiments and historical evidence under declared roles",
            "source_capture_policy": "Use source_archive/<original-relative-path> for curated temporary captures and publish an explicit path/hash alias map; do not silently rewrite original receipts",
            "ZIP64": True,
            "archive_digest_and_manifest": "Hash archive bytes and every extracted member; verify archive and expanded manifest together",
            "new_files_not_counted_yet": ["START_HERE.txt", "NYGRID_2025_DLR_HANDOFF.docx", "NYGRID_2025_DLR_HANDOFF.md", "scripts/nygrid_2025_dlr_handoff/**", "output/nygrid_2025_dlr_handoff/**", "vendor/matpower8.1/**"],
        },
        rerun_levels={
            "latest_single_hour_PF": "30defaultdata closure plus MATLAB code closure; MATLAB and MATPOWER required; route weather not required",
            "new_full_year_PF": "Same frozen annual data and cache; write a new run label; preserve8651eligibility andall8760clockpositions",
            "rescore_saved_2025_comparison": "Full package must include old12monthlyprofile MATs, new12monthly MATs, annualreceipts, frozencomparisoncohort, observations/operator source cases, correctedgenlanding vector and policy inputs",
            "portable_scoring_gap": "Original scorer invokes git show6dcc77f for two source bindings; provide a separate package-SHA-based adapter, not a false claim that it works unchanged without.git",
            "historical_finalizers": "Some enforce oldGit roots or the unrelated annotatedWESTERNreport hash; retain as historical methods, use package-specific verification for relocated archives",
            "original_source_rebuild": "Also needs curated rawupstream/federal/NYISO source captures, documented downloads and external dependency versions; not equivalent to loading saved cases",
        },
        DLR_data_and_guard_notes={
            "weather_named_files": weather_files,
            "observed_route_bound_2025_weather_available": False,
            "weather_schema": ["ambient_c", "wind_m_s", "wind_angle_deg", "solar_w_m2", "pressure_pa"],
            "provided_weather": "Synthetic constant catalog_reference and breezy scenarios; not historical measurements",
            "thermal_method": "Steady conductor heat balance with manufacturer AC R(T) interpolation and declared temperature/surface/heat-capacity assumptions; inherited reference temperature is not solved equilibrium",
            "current_scale": "Use recovered original branch/section amperes; never divide amperes by gamma",
            "strict_asset_exclusions": [224, 300, 309, 310, 386],
            "generic_OH_class_is_not_physical_asset_verification": True,
            "other_rejections": ["cables", "transformers and voltage-changing branches", "PAR equipment", "nonphysical equivalents", "unqualified conductor/route/equipment identities"],
            "state_and_units": "PreserveUTC/calendar pairing, original parent/section IDs, circuit/bundle multiplicity, limitingheterogeneous section, terminal equipment ceilings and positive thermal margin",
            "latest_loss_revision": "PF-only148retained-bus accounting model;8170/8651qualified,0physicalVQ; parent224removedfromDLR",
            "older_thermal_api": "run_nygrid_2025_ac_dlr constructs older npcc_nygrid_2025_ac; its4/8historical syntheticthermal qualification does not transfer to latestlossrevision",
        },
        sharing_and_license_observations=[
            dict(component="Local research repository", observation="No root license file found in baseline checkout; do not label the whole mixed package MIT.", action="Preserve provenance and creator/source notices; no new license is granted by this inventory."),
            dict(component="CornellNYgrid pinned upstream", observation="Pinned README declares MIT and refers to LICENSE, but the local pinned upstream snapshot has no LICENSE file.", action="Preserve pinned README/sourcecommit and record this notice gap; verify original grant before redistribution."),
            dict(component="ENLITEN source repository", observation="ENLITEN-Grid-Econ-Data-main/LICENSE contains GPLversion3; this is a separate source repository, not a blanket license for all package data.", action="If its files are included, retain its license and attribution and assess the relevant reuse terms."),
            dict(component="MATLAB/MATPOWER", observation="MATLAB installation is a recipient prerequisite; MATPOWERvendor license audit handled by runtime workstream.", action="Do not copy the licensed MATLAB runtime installation; include only explicitly permitted vendor payload with notices."),
            dict(component="NYISO/IEEE/manufacturer/utility PDFs", observation="Publicly readable provenance is not an established blanket redistribution grant; originals retain publisher notices.", action="Classify as source evidence; preserve URLs/capture dates/hashes and seek appropriate terms review before external redistribution."),
            dict(component="EIA/EPA and other public datasets", observation="Frozen data lineage and reporting scope are documented; source availability does not make all linked third-party attachments one license.", action="Preserve each source's receipts and attribution; do not include personal APIcredentials."),
        ],
        credential_reference_locations_for_builder_review=credential_findings,
        unresolved_credential_reference_count=sum(x["classification"].startswith("requires_manual") for x in credential_findings),
        upload_or_message_to_colleague_performed=False,
        source_code=dict(path=Path(__file__).relative_to(ROOT).as_posix(), sha256=sha(Path(__file__))),
    )
    target = OUT / "package_inventory.json"
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ["selected_prior_file_count", "selected_prior_bytes", "curated_untracked_raw_bytes", "unique_historical_source_bytes_not_already_in_research"]}))


if __name__ == "__main__":
    main()
