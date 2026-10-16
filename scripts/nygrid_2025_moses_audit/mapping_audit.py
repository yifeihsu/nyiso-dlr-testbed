"""Read-only Moses South mapping and observed-channel audit.

This script reads frozen 2019/2025 artifacts and official cached P32 archives.
It writes only output/nygrid_2025_moses_audit/mapping. It neither changes a
builder nor fits an operator, impedance, scale, dispatch, or time shift to flow.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_moses_audit/mapping"
CHANNEL = "MOSES SOUTH"
POINT_ID = 23319
FLOW_HEADERS = ["Timestamp", "Interface Name", "Point ID", "Flow (MWH)",
                "Positive Limit (MWH)", "Negative Limit (MWH)"]
DEPENDENCIES: dict[str, str] = {}
CHECKS: list[dict] = []


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def use(relative: str) -> Path:
    path = ROOT / relative
    DEPENDENCIES[relative] = sha(path)
    return path


def check(name: str, value: bool, detail: str = "", maximum_error: float = 0.) -> None:
    CHECKS.append(dict(check=name, passed=bool(value), detail=detail,
                       maximum_absolute_error=float(maximum_error)))
    if not value:
        raise AssertionError(name + ": " + detail)


def close(name: str, actual, expected, tol=1e-8) -> None:
    a, b = np.asarray(actual), np.asarray(expected)
    same = a.shape == b.shape and np.array_equal(np.isnan(a), np.isnan(b))
    error = float(np.max(np.abs(a[np.isfinite(a)] - b[np.isfinite(b)]), initial=0)) if same else float("inf")
    check(name, same and error < tol, f"absolute tolerance {tol:g}", error)


def csv(relative: str, **kwargs) -> pd.DataFrame:
    return pd.read_csv(use(relative), **kwargs)


def mat(relative: str, variables=None) -> dict:
    return loadmat(use(relative), simplify_cells=True, variable_names=variables)


def save_csv(name: str, frame: pd.DataFrame) -> None:
    frame.to_csv(OUT / name, index=False, lineterminator="\n")


def map_operator(case: dict) -> np.ndarray:
    members = np.atleast_2d(case["if"]["map"])
    signed = members[members[:, 0] == 4, 1].astype(int)
    check("map_members_valid_" + str(len(case["branch"])), len(signed) == 3 and len(set(abs(signed))) == 3)
    op = np.zeros(len(case["branch"]))
    op[abs(signed) - 1] = np.sign(signed)
    return op


def cut_operator(case: dict, zones: dict[int, str]) -> np.ndarray:
    return np.array([r[10] * (int(zones[int(r[0])] == "D" and zones[int(r[1])] == "E")
                    - int(zones[int(r[1])] == "D" and zones[int(r[0])] == "E"))
                    for r in case["branch"]], dtype=float)


def branch_ledger(case: dict, op: np.ndarray, label: str, info: pd.DataFrame) -> list[dict]:
    lookup = info.set_index("idx")
    rows = []
    for i in np.flatnonzero(op):
        r = case["branch"][i]
        a, b = int(r[0]), int(r[1])
        rows.append(dict(case=label, branch_row_1based=int(i + 1), coefficient=float(op[i]),
                         from_bus=a, to_bus=b, from_name=lookup.loc[a, "name"],
                         to_name=lookup.loc[b, "name"], from_zone=lookup.loc[a, "zone"],
                         to_zone=lookup.loc[b, "zone"], from_kv=float(lookup.loc[a, "Vn"]),
                         to_kv=float(lookup.loc[b, "Vn"]), r_pu=r[2], x_pu=r[3],
                         b_pu=r[4], tap=r[8], phase_degree=r[9], status=r[10]))
    return rows


def resolve_utc(local: pd.DatetimeIndex) -> tuple[pd.DatetimeIndex, int]:
    """Use the raw per-channel clock rewind, with no fitted time shift."""
    ambiguous = local.tz_localize("America/New_York", ambiguous="NaT", nonexistent="raise").isna()
    summer = np.zeros(len(local), dtype=bool)
    if ambiguous.any():
        rewind = [i for i in range(1, len(local)) if ambiguous[i] and ambiguous[i - 1]
                  and (local[i - 1] - local[i]).total_seconds() > 1800]
        if len(rewind) != 1:
            raise ValueError("Ambiguous raw fall-clock sequence")
        summer[:rewind[0]] = True
    return local.tz_localize("America/New_York", ambiguous=summer,
                            nonexistent="raise").tz_convert("UTC"), int(ambiguous.sum())


def read_raw(year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    relative = ("output/nygrid_2019/nyiso_source_audit_archives.csv" if year == 2019 else
                "output/nygrid_2025_inputs/load_source/source_receipts.csv")
    records = csv(relative)
    if year == 2025:
        records = records.loc[records.family == "ExternalLimitsFlows"]
    frames, identities = [], []
    for receipt in records.to_dict("records"):
        path = use(receipt["archive"])
        check(f"archive_hash_{year}_{receipt['month']}", sha(path) == receipt["sha256"])
        with zipfile.ZipFile(path) as archive:
            for member in sorted(archive.namelist()):
                if receipt["month"] == "2026-01" and member != "20260101ExternalLimitsFlows.csv":
                    continue
                raw = pd.read_csv(io.BytesIO(archive.read(member)))
                if list(raw.columns) != FLOW_HEADERS:
                    raise ValueError("Unexpected P32 schema: " + member)
                f = raw.loc[raw["Interface Name"] == CHANNEL].copy()
                if not len(f) or set(f["Point ID"]) != {POINT_ID}:
                    raise ValueError("Missing or changed Moses channel: " + member)
                local = pd.DatetimeIndex(pd.to_datetime(f.Timestamp, format="mixed"))
                f["local_timestamp"] = local
                f["source_member"] = member
                ambiguous = 0
                if year == 2025:
                    f["timestamp_utc"], ambiguous = resolve_utc(local)
                frames.append(f)
                identities.append(dict(year=year, source_member=member, channel=CHANNEL,
                                       point_id=POINT_ID, raw_rows=len(f),
                                       ambiguous_rows=ambiguous,
                                       published_flow_column="Flow (MWH)",
                                       source_url=receipt["source_url"]))
    return pd.concat(frames, ignore_index=True), pd.DataFrame(identities)


def held_means(raw: pd.DataFrame, hours: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """Independent per-hour interval intersection; no production aggregator import."""
    grouped = raw.groupby("timestamp_utc", sort=True)["Flow (MWH)"].mean()
    t = grouped.index.asi8 / 1e9
    y = grouped.to_numpy(float)
    means = np.full(len(hours), np.nan)
    covered = np.zeros(len(hours))
    for h, start in enumerate(hours.asi8 / 1e9):
        end = start + 3600
        first = max(0, int(np.searchsorted(t, start, side="right")) - 1)
        last = min(len(t) - 1, int(np.searchsorted(t, end, side="left")))
        indices = np.arange(first, last)
        seconds = np.maximum(0, np.minimum(t[indices + 1], end) - np.maximum(t[indices], start))
        keep = (t[indices + 1] - t[indices] <= 600) & np.isfinite(y[indices])
        covered[h] = seconds[keep].sum()
        if abs(covered[h] - 3600) < 1e-7:
            means[h] = (seconds[keep] * y[indices[keep]]).sum() / 3600
    return means, covered


def score(prediction, actual) -> dict:
    error = np.asarray(prediction) - np.asarray(actual)
    return dict(hours=len(error), predicted_mean_mw=float(np.mean(prediction)),
                observed_mean_mw=float(np.mean(actual)),
                observed_mean_absolute_mw=float(np.mean(abs(np.asarray(actual)))),
                mae_mw=float(abs(error).mean()), bias_mw=float(error.mean()),
                wape_percent=float(100 * abs(error).sum() / abs(np.asarray(actual)).sum()))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    info = csv("tmp/nygrid_2019_reproduction/upstream/Data/npcc_new.csv", keep_default_na=False)
    zones = dict(zip(info.idx.astype(int), info.zone))
    d19 = mat("output/nygrid_2019_full_stage1/full_year.mat",
              ["base_case", "reduced_final_case", "branch_pf", "interface_mw", "observed_interface_mw", "timestamp_iso"])
    d25 = mat("output/nygrid_2025_dispatch/dispatch/dispatch.mat",
              ["base_case", "timestamp_utc", "dispatch_qualified", "gamma"])
    n25 = mat("output/nygrid_2025_dispatch/dispatch/dispatch_network.mat",
              ["branch_pf", "inherited_interface_pf"])
    slim = mat("output/nygrid_2025_slim/network/network_cases.mat")
    full = mat("output/nygrid_2025_downstate/network/network_cases.mat")
    rec25 = mat("output/nygrid_2025_slim/replay/topology_dated.mat",
                ["timestamp_utc", "qualified", "network_state_ids", "bus_va", "interface_pf"])
    full25 = mat("output/nygrid_2025_downstate/replay/upgrades_dated.mat",
                 ["timestamp_utc", "qualified", "branch_pf", "interface_pf"])
    all_zones = dict(zip(np.asarray(full["bus_ids"], int), np.asarray(full["bus_zones"]).astype(str)))
    op19, op25 = map_operator(d19["base_case"]), map_operator(d25["base_case"])
    reduced_op = map_operator(d19["reduced_final_case"])
    close("full2019_map_matches_D_to_E_cut", op19, cut_operator(d19["base_case"], zones))
    close("original140_map_matches_D_to_E_cut", op25, cut_operator(d25["base_case"], zones))
    close("full2019_vs_original140_operator", op19, op25)
    close("moses_member_electrical_rows_2019_vs_2025", d19["base_case"]["branch"][op19 != 0],
          d25["base_case"]["branch"][op25 != 0])
    close("full2019_saved_prediction_from_branch_PF", d19["branch_pf"] @ op19, d19["interface_mw"][:, 3])
    q = np.asarray(d25["dispatch_qualified"], bool)
    close("original140_saved_prediction_from_branch_PF", n25["branch_pf"][q] @ op25,
          n25["inherited_interface_pf"][q, 3])
    check("cohort_8663", int(q.sum()) == 8663)
    check("dated148_same_cohort", np.array_equal(q, np.asarray(rec25["qualified"], bool)))
    check("dated191_same_cohort", np.array_equal(q, np.asarray(full25["qualified"], bool)))
    for label, data in [("dated148", rec25), ("dated191", full25)]:
        check(label + "_same_UTC_timestamps", np.array_equal(np.asarray(data["timestamp_utc"]).astype(str),
              np.asarray(d25["timestamp_utc"]).astype(str)))
    ledger = branch_ledger(d19["reduced_final_case"], reduced_op, "2019_corrected_reduced", info)
    ledger += branch_ledger(d19["base_case"], op19, "2019_full140", info)
    ledger += branch_ledger(d25["base_case"], op25, "2025_original140", info)
    recovered = np.full(8760, np.nan)
    for state in sorted(set(np.asarray(rec25["network_state_ids"]).astype(str))):
        mask = q & (rec25["network_state_ids"] == state)
        op = cut_operator(full[state], all_zones)
        close(state + "_same_moses_members", op[:225], op25)
        check(state + "_no_added_moses_members", bool(np.all(op[225:] == 0)))
        ledger += branch_ledger(full[state], op, "2025_191_" + state, info)
        close(state + "_191_direct_branch_sum", full25["branch_pf"][mask] @ op,
              full25["interface_pf"][mask, 3])
        rec = slim["recovery"][state.removesuffix("_case")]
        recovered[mask] = np.deg2rad(rec25["bus_va"][mask]) @ np.asarray(rec["interface_angle_matrix"])[3] + np.asarray(rec["interface_flow_offset"])[3]
        close(state + "_148_recovery_saved", recovered[mask], rec25["interface_pf"][mask, 3])
        close(state + "_148_to191_moses", recovered[mask], full25["branch_pf"][mask] @ op)
    save_csv("mapping_terms.csv", pd.DataFrame(ledger))

    raw19, identity19 = read_raw(2019)
    raw25, identity25 = read_raw(2025)
    save_csv("raw_channel_identity.csv", pd.concat([identity19, identity25], ignore_index=True))
    check("2019_source_daily_files_365", len(identity19) == 365)
    check("2025_source_daily_files_365_plus_endpoint", len(identity25) == 366)
    naive_hours = pd.date_range("2019-01-01", periods=8760, freq="h")
    mean19 = raw19.groupby(raw19.local_timestamp.dt.floor("h"))["Flow (MWH)"].mean().reindex(naive_hours)
    filled19 = mean19.interpolate(method="linear").to_numpy()
    check("2019_no_edge_extrapolation_needed", bool(mean19.iloc[[0, -1]].notna().all()))
    close("2019_observation_rebuilt_from_raw_Flow_column", filled19, d19["observed_interface_mw"][:, 3])
    catalog = csv("output/nygrid_2025_inputs/load_source/hour_catalog.csv")
    hours = pd.DatetimeIndex(pd.to_datetime(catalog.timestamp_utc, utc=True))
    check("2025_physical_hours_consecutive", len(hours) == 8760 and bool(np.all(np.diff(hours.asi8) == 3600e9)))
    mean25, coverage = held_means(raw25, hours)
    wide = csv("output/nygrid_2025_inputs/load_source/interface_wide.csv")
    close("2025_observation_rebuilt_from_raw_Flow_column", mean25, wide[CHANNEL].to_numpy(float))
    check("2025_observations_align_with_dispatch_UTC", np.array_equal(wide.timestamp_utc.astype(str),
          np.asarray(d25["timestamp_utc"]).astype(str)))
    check("2025_qualified_cohort_has_complete_Moses_data", bool(np.isfinite(mean25[q]).all()))
    flow_long = csv("output/nygrid_2025_inputs/load_source/interface_hourly.csv")
    ml = flow_long.loc[flow_long.channel == CHANNEL].sort_values("hour_index")
    close("2025_Moses_hourly_coverage_rebuilt", coverage, ml.coverage_seconds.to_numpy())
    close("2025_Moses_long_wide_identity", mean25, ml.flow_mw.to_numpy())
    check("2025_Moses_hourly_point_id", set(ml.point_id) == {POINT_ID})
    observed_2025 = mean25[q]
    gamma = float(d25["gamma"])
    check("gamma_positive_and_consistent", gamma > 0 and gamma == float(slim["gamma"]) == float(full["gamma"]))
    original_public = n25["inherited_interface_pf"][q, 3] / gamma
    updated_public = recovered[q] / gamma
    close("WAPE_common_scale_invariance", [score(original_public, observed_2025)["wape_percent"]],
          [score(original_public * gamma, observed_2025 * gamma)["wape_percent"]])
    summaries = [dict(case="2019_full140", **score(d19["interface_mw"][:, 3], filled19)),
                 dict(case="2025_original140", **score(original_public, observed_2025)),
                 dict(case="2025_dated148", **score(updated_public, observed_2025))]
    saved = csv("output/nygrid_2025_slim/comparison/interface_summary.csv")
    for label, name in [("original140", "2025_original140"), ("topology_dated_148bus", "2025_dated148")]:
        record = saved.loc[(saved.variant == label) & (saved.interface == CHANNEL)].iloc[0]
        rebuilt = next(row for row in summaries if row["case"] == name)
        close(label + "_published_WAPE_rebuilt", [rebuilt["wape_percent"]], [record.wape_percent])
    save_csv("score_reconstruction.csv", pd.DataFrame(summaries))
    alt = raw25.loc[raw25.timestamp_utc.ge(hours[0]) & raw25.timestamp_utc.lt(hours[-1] + pd.Timedelta(hours=1))]
    arithmetic = alt.groupby(alt.timestamp_utc.dt.floor("h"))["Flow (MWH)"].mean().reindex(hours).to_numpy()
    save_csv("2025_observation_hourly_reconstruction.csv", pd.DataFrame(dict(
        hour_index=np.arange(1, 8761), timestamp_utc=catalog.timestamp_utc,
        dispatch_qualified=q, raw_rebuilt_forward_hold_mw=mean25, saved_observation_mw=wide[CHANNEL],
        covered_seconds=coverage, alternative_raw_arithmetic_mean_mw=arithmetic,
        original_prediction_public_mw=n25["inherited_interface_pf"][:, 3] / gamma,
        dated148_prediction_public_mw=recovered / gamma)))
    alt_score = score(original_public, arithmetic[q])
    methods = dict(canonical_forward_hold_WAPE=summaries[1]["wape_percent"],
                   alternate_raw_arithmetic_WAPE=alt_score["wape_percent"],
                   arithmetic_minus_hold_mean_mw=float(np.mean(arithmetic[q] - mean25[q])),
                   arithmetic_minus_hold_mae_mw=float(np.mean(abs(arithmetic[q] - mean25[q]))),
                   selected_method="frozen_source_contract_forward_hold", method_fitted_to_observations=False)

    source_docs = [
        dict(title="NYISO Summer 2025 Operating Study", page=22,
             url="https://www.nyiso.com/documents/20142/3691300/Summer2025-OperatingStudy-APPROVED.pdf/3aaa5eb6-9fa4-53b5-181a-189e3ac52fcb",
             access="official-domain indexed search excerpt; direct web open returned JavaScript verification page",
             finding="Moses South transfer limits still reference Moses-Adirondack MA2, Massena-Marcy MSU1 and Marcy transformers. This table gives limiting facilities and contingencies, not the complete metered flowgate membership.",
             complete_2025_membership_established=False),
        dict(title="New York STARS Phase 2 Final Report, April 30 2012", page=34,
             url="https://www.nyiso.com/documents/20142/1398242/Phase_2_Final_Report_4_30_2012.pdf",
             access="official-domain indexed search excerpt; direct web open returned JavaScript verification page",
             finding="Figure6-6 historically lists nine Moses South circuits: Massena-Marcy765, two Moses West-Adirondack230 circuits, Jay-Norton46, Alcoa-Brady115, AllensFalls-Colton115, two Dennison115 ties, and a Gilpin46 tie. The three-row NPCC zone functional is a coarse proxy, not this literal nine-circuit list.",
             complete_2025_membership_established=False),
        dict(title="NYISO 2023 Q1 STAR Report", page=39,
             url="https://www.nyiso.com/documents/20142/16004172/2023-Q1-STAR-Report-Final.pdf",
             access="official-domain indexed search excerpt",
             finding="Earlier planning tables describe future Haverstock-Adirondack and Haverstock-Willis345 connections for project1125. A proposed 2025 date does not establish actual energization or a new 2025 meter definition.",
             complete_2025_membership_established=False),
    ]
    (OUT / "primary_source_search_receipt.json").write_text(json.dumps(dict(
        searched_utc=started, purpose="Moses South physical membership and 2025 changes",
        sources=source_docs, inference="No current complete physical meter list was accessible; do not change the operator to fit observed flows."), indent=2) + "\n")
    save_csv("checks.csv", pd.DataFrame(CHECKS))
    summary = dict(status="passed_numerical_mapping_and_raw_channel_audit_physical_membership_unverified",
                   started_utc=started, completed_utc=datetime.now(timezone.utc).isoformat(),
                   branch=subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
                   head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                   checks=len(CHECKS), failed_checks=0, confirmed_numerical_mapping_or_channel_bugs=[],
                   model_scope="D-to-E accounting-zone crossing; inherited proxy with signed full rows -46,-51,-52",
                   point_id_2019=POINT_ID, point_id_2025=POINT_ID,
                   raw_rows_2019=len(raw19), raw_rows_2025_including_endpoint=len(raw25),
                   imputed_2019_hours=int(mean19.isna().sum()),
                   qualified_2025_Moses_hours=int(np.isfinite(mean25).sum()), paired_scoring_hours=int(q.sum()),
                   gamma=gamma, published_units="Flow (MWH) in both raw schemas; preserved numeric convention treated as power MW in existing models",
                   unit_scope="No year-specific unit or source-column change found; no factor-of12 or factor-of60 conversion was introduced.",
                   aggregation_diagnostic=methods, scores=summaries,
                   physical_2025_membership_verified=False,
                   limitations=["Physical flowgate membership is not established by matching a zone-cut operator.",
                                "2019 nominal-local-hour reconstruction and2025 qualified physical-hour reconstruction are different cohorts and methods.",
                                "Public operating-study limiting elements are not a complete flow-measurement operator.",
                                "This audit does not independently certify the public header's MWH label as a metering-unit specification."],
                   recommended_builder_fix="None supported by this mapping/observation audit. Preserve the current operator pending source-backed physical membership.",
                   writes_scope="new audit folder only; all frozen files preserved")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    use("scripts/nygrid_2025_moses_audit/mapping_audit.py")
    for relative, digest in DEPENDENCIES.items():
        if sha(ROOT / relative) != digest:
            raise AssertionError("Frozen dependency changed during audit: " + relative)
    (OUT / "manifest.json").write_text(json.dumps(dict(
        inputs=[dict(path=k, sha256=v) for k, v in sorted(DEPENDENCIES.items())],
        outputs=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p))
                 for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "manifest.json"],
        all_inputs_unchanged_at_completion=True), indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
