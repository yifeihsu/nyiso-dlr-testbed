"""Read-only HQ/PAR source audit on the frozen physical-repair cohort.

Rebuilds EIA930 hours and P34 native timestamps/aggregations independently.
Alternative PAR aggregations and historical schedules are diagnostics only.
Internal-interface observations score predetermined algebraic probes; they never
select source signs, timestamps, source-quality flags or a promoted replacement.
"""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output/nygrid_2025_moses_source_diagnosis/boundary"
WEST = ROOT / "output/nygrid_2025_western_audit/boundary_actuals"
PAR = ROOT / "output/nygrid_2025_par_controls"
OLD = ROOT / "output/nygrid_2025_moses_audit/exchanges"
PTIDS = [25118, 25119]
DEPENDENCIES = {}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    path = Path(path)
    DEPENDENCIES[str(path.relative_to(ROOT)).replace("\\", "/")] = sha(path)
    return path


def require(test, message):
    if not bool(test):
        raise ValueError(message)


def equal(a, b, label, tol=1e-8):
    a, b = np.asarray(a), np.asarray(b)
    require(a.shape == b.shape and np.allclose(a, b, atol=tol, rtol=0, equal_nan=True), label)
    finite = np.isfinite(a) & np.isfinite(b)
    return float(np.max(abs(a[finite] - b[finite]), initial=0))


def summary(values):
    values = np.asarray(values, float)
    values = values[np.isfinite(values)]
    require(len(values) > 0, "Empty summary cohort")
    return dict(hours=len(values), mean_MW=float(values.mean()), mean_absolute_MW=float(abs(values).mean()),
                standard_deviation_MW=float(values.std()), minimum_MW=float(values.min()),
                maximum_MW=float(values.max()), p95_absolute_MW=float(np.quantile(abs(values), .95)),
                max_absolute_MW=float(abs(values).max()))


def performance(modeled, observed, mask):
    error = np.asarray(modeled, float)[mask] - np.asarray(observed, float)[mask]
    target = np.asarray(observed, float)[mask]
    require(np.isfinite(error).all() and len(error) > 0, "Incomplete diagnostic comparison")
    return dict(hours=int(mask.sum()), MAE_MW=float(abs(error).mean()), RMSE_MW=float(np.sqrt(np.mean(error**2))),
        WAPE_percent=float(100*abs(error).sum()/abs(target).sum()), mean_residual_MW=float(error.mean()),
        p95_absolute_error_MW=float(np.quantile(abs(error), .95)), total_absolute_error_MWh=float(abs(error).sum()))


def write_csv(table, name):
    table.to_csv(OUT / name, index=False, lineterminator="\n")


def eia_native(axis):
    parts, counts = [], []
    for half in ["Jan_Jun", "Jul_Dec"]:
        path = read(WEST / "raw" / f"EIA930_INTERCHANGE_2025_{half}.csv.gz")
        receipt = json.loads(read(path.with_suffix(path.suffix + ".receipt.json")).read_text())
        require(sha(path) == receipt["sha256"], "EIA archived bytes differ")
        with gzip.open(path, "rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        require(digest == receipt["original_csv_sha256"], "EIA decoded original CSV differs")
        columns = ["Balancing Authority", "Directly Interconnected Balancing Authority", "UTC Time at End of Hour", "Interchange (MW)"]
        for block in pd.read_csv(path, usecols=columns, chunksize=100000):
            connected = block[block[columns[1]].eq("NYIS")]
            counts.extend(connected[columns[0]].tolist())
            selected = block[block[columns[0]].eq("NYIS")].copy()
            if selected.empty:
                continue
            selected["timestamp_utc"] = pd.to_datetime(selected[columns[2]], format="%m/%d/%Y %I:%M:%S %p", utc=True) - pd.Timedelta(hours=1)
            selected["neighbor"] = selected[columns[1]]
            selected["import_to_NY_MW"] = -pd.to_numeric(selected[columns[3]], errors="raise")
            parts.append(selected[["timestamp_utc", "neighbor", "import_to_NY_MW"]])
    data = pd.concat(parts, ignore_index=True)
    require(not data.duplicated(["timestamp_utc", "neighbor"]).any(), "Duplicate EIA NYIS native hours")
    data = data.pivot(index="timestamp_utc", columns="neighbor", values="import_to_NY_MW").reindex(axis)
    require(set(data.columns) == {"HQT", "IESO", "ISNE", "PJM"} and np.isfinite(data.to_numpy()).all(), "EIA native source incomplete")
    return data, pd.Series(counts).value_counts().rename_axis("reporter").reset_index(name="records_to_NYIS_in_both_bulk_files")


def native_par():
    """Resolve DST from the recorded local-clock rewind, preserving row order."""
    tables, timing = [], []
    for year, month in [(2025, m) for m in range(1, 13)] + [(2026, 1)]:
        path = read(OLD / "raw" / f"{year}{month:02d}01ParFlows_csv.zip")
        receipt = json.loads(read(path.with_suffix(path.suffix + ".receipt.json")).read_text())
        require(sha(path) == receipt["sha256"], "P34 archive bytes differ")
        with zipfile.ZipFile(path) as archive:
            for member in sorted(archive.namelist()):
                if year == 2026 and member != "20260101ParFlows.csv":
                    continue
                payload = archive.read(member)
                data = pd.read_csv(io.BytesIO(payload))
                require(data.columns.tolist() == ["Timestamp", "Point ID", "Flow (MWH)"], "P34 schema changed")
                for ptid in PTIDS:
                    group = data[data["Point ID"].eq(ptid)]
                    local = pd.DatetimeIndex(pd.to_datetime(group.Timestamp, format="mixed"))
                    require(len(local) > 0 and (local.normalize() == pd.Timestamp(member[:8])).all(), "P34 source day differs")
                    ambiguous = local.tz_localize("America/New_York", ambiguous="NaT", nonexistent="raise").isna()
                    daylight = np.zeros(len(local), bool)
                    if ambiguous.any():
                        rewinds = np.flatnonzero(np.diff(local.asi8) < -1800 * 10**9) + 1
                        require(len(rewinds) == 1 and ambiguous[rewinds[0]] and ambiguous[rewinds[0] - 1], "Unresolved P34 DST fold")
                        daylight[:rewinds[0]] = True
                    utc = local.tz_localize("America/New_York", ambiguous=daylight, nonexistent="raise").tz_convert("UTC")
                    require((np.diff(utc.asi8) >= 0).all(), "P34 source order is not monotone in UTC")
                    tables.append(pd.DataFrame(dict(timestamp_utc=utc, point_id=ptid,
                        original_flow_mw=group["Flow (MWH)"].to_numpy(float), source_member=member, source_archive=path.name)))
                    timing.append(dict(source_member=member, point_id=ptid, records=len(local),
                        ambiguous_records=int(ambiguous.sum()), member_sha256=hashlib.sha256(payload).hexdigest()))
    return pd.concat(tables, ignore_index=True), pd.DataFrame(timing)


def aggregate_par(raw, axis):
    """Integrate each native segment over its exact hourly overlap.

    Forward hold is the frozen convention. Backward hold and linear interpolation
    probe the timestamp/interval convention only; no source asserts they are better.
    Arithmetic average uses samples stamped within [start,end), including irregular
    samples, and is retained only as an explicit comparison with time weighting.
    """
    result = pd.DataFrame(index=axis)
    metadata = []
    for ptid in PTIDS:
        group = raw.loc[raw.point_id.eq(ptid)].groupby("timestamp_utc").original_flow_mw.agg(["mean", "count", "min", "max"])
        seconds = group.index.asi8 // 10**9
        values = group["mean"].to_numpy(float)
        duplicates = group["max"] - group["min"]
        require(duplicates.max() == 0, "P34 duplicate timestamp has conflicting values")
        metadata.append(dict(ptid=ptid, native_records=int(group["count"].sum()), unique_timestamps=len(group),
            repeated_timestamp_records=int((group["count"]-1).sum()), max_duplicate_spread_MW=float(duplicates.max()),
            min_native_MW=float(values.min()), max_native_MW=float(values.max()),
            intervals_longer_than_600_seconds=int((np.diff(seconds) > 600).sum())))
        outputs = []
        for left in axis.asi8 // 10**9:
            right = left + 3600
            lo = max(0, np.searchsorted(seconds, left, side="right") - 1)
            hi = min(len(seconds)-1, np.searchsorted(seconds, right, side="left"))
            areas = np.zeros(3)
            coverage = 0
            maximum_gap = 0
            for j in range(lo, hi):
                start, end = max(left, seconds[j]), min(right, seconds[j+1])
                overlap = end-start
                if overlap <= 0:
                    continue
                gap = seconds[j+1]-seconds[j]
                maximum_gap = max(maximum_gap, gap)
                if gap > 600 or not np.isfinite(values[j:j+2]).all():
                    continue
                coverage += overlap
                lval, rval = values[j:j+2]
                frac = ((start-seconds[j]) + (end-seconds[j])) / (2*gap)
                areas += overlap * np.array([lval, rval, lval+(rval-lval)*frac])
            samples = values[(seconds >= left) & (seconds < right)]
            means = areas/3600 if coverage == 3600 else np.full(3, np.nan)
            outputs.append([*means, float(np.mean(samples)) if len(samples) else np.nan, coverage, maximum_gap, len(samples)])
        for j, name in enumerate(["forward_hold_MW", "backward_hold_MW", "linear_MW", "arithmetic_mean_MW", "coverage_seconds", "max_gap_seconds", "native_count"]):
            result[f"PAR_{ptid}_{name}"] = np.asarray(outputs)[:, j]
    for method in ["forward_hold_MW", "backward_hold_MW", "linear_MW", "arithmetic_mean_MW"]:
        result[f"PAR_total_{method}"] = result[[f"PAR_{p}_{method}" for p in PTIDS]].sum(axis=1, min_count=2)
    return result, metadata


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    baseline = pd.read_csv(read(OUT.parent / "balance_hourly.csv"))
    axis = pd.DatetimeIndex(pd.to_datetime(baseline.timestamp_utc, utc=True))
    expected = pd.date_range("2025-01-01", "2026-01-01", freq="h", inclusive="left", tz="America/New_York").tz_convert("UTC")
    require(axis.equals(expected), "Canonical physical-hour axis changed")
    qualified = baseline.qualified.to_numpy(bool)
    require(len(axis) == 8760 and qualified.sum() == 8651, "Expected fixed physical-repair cohort")
    direction = json.loads(read(PAR / "sources/direction/direction_verification_receipt.json").read_text())
    require(direction["status"] == "verified_official_direction_for_2025" and direction["sign_convention_effective_date"] == "2024-12-03", "P34 direction basis changed")
    require(all(r["raw_to_ontario_to_new_york_multiplier"] == 1 for r in direction["ptid_directions"]), "Unexpected current P34 positive convention")
    controls = pd.read_csv(read(PAR / "controls/hourly_controls.csv"))
    existing = pd.read_csv(read(WEST / "hourly_regional_actuals.csv"))
    source_quality = pd.read_csv(read(WEST / "hourly_source_quality.csv"))
    totals = pd.read_csv(read(WEST / "reported_total_sum_check.csv"))
    schedules = pd.read_csv(read(ROOT / "output/nygrid_2025_inputs/load_source/interface_wide.csv"),
        usecols=["timestamp_utc", "SCH - HQ - NY", "SCH - HQ_CEDARS", "SCH - HQ_IMPORT_EXPORT"])
    for label, table in [("PAR controls", controls), ("EIA compiled", existing), ("EIA quality", source_quality), ("EIA total", totals), ("HQ schedules", schedules)]:
        require(np.array_equal(table.timestamp_utc, baseline.timestamp_utc), label + " axis differs")
    for path in ["latest_model.mat", "profiles_h0001_4380.mat", "profiles_h4381_8760.mat"]:
        read(ROOT / "output/nygrid_2025_physical_repair/model" / path)
    eia, counterpart_counts = eia_native(axis)
    raw, timing = native_par()
    cached = pd.read_csv(read(OLD / "par_stlawrence_raw_2025.csv.gz"))
    cached.timestamp_utc = pd.to_datetime(cached.timestamp_utc, utc=True)
    sort = ["timestamp_utc", "point_id", "source_member", "source_archive", "original_flow_mw"]
    pd.testing.assert_frame_equal(raw.sort_values(sort).reset_index(drop=True), cached.sort_values(sort).reset_index(drop=True), check_dtype=False)
    par, par_metadata = aggregate_par(raw, axis)
    require(np.isfinite(par.PAR_total_forward_hold_MW[qualified]).all(), "Fixed cohort lacks PAR source coverage")
    checks = dict(native_P34_rows_match_frozen_raw=len(raw))
    for ptid, current in zip(PTIDS, ["PAR1_MW", "PAR2_MW"]):
        values = par[f"PAR_{ptid}_forward_hold_MW"].to_numpy()
        checks[f"PAR_{ptid}_native_vs_compiled_max_absolute_MW"] = equal(values, controls[f"ptid_{ptid}_observed_public_mw"], "P34 native/compiled mismatch")
        checks[f"PAR_{ptid}_native_vs_current_model_max_absolute_MW"] = equal(values[qualified], baseline[current][qualified], "P34 model mismatch")
    checks["HQ_native_vs_compiled_max_absolute_MW"] = equal(eia.HQT, existing.HQ_actual_import_mw, "HQ native/compiled mismatch")
    checks["HQ_native_vs_current_model_max_absolute_MW"] = equal(eia.HQT[qualified], baseline.HQ_MW[qualified], "HQ current model mismatch")
    hourly = baseline[["hour_index", "timestamp_utc", "state_index", "qualified"]].copy()
    hourly["HQ_native_actual_import_MW"] = eia.HQT.to_numpy()
    hourly["HQ_original_schedule_with_Cedars_MW"] = schedules["SCH - HQ - NY"] + schedules["SCH - HQ_CEDARS"]
    hourly["HQ_original_Cedars_schedule_MW"] = schedules["SCH - HQ_CEDARS"]
    hourly["HQ_NY_minus_import_export_schedule_MW"] = schedules["SCH - HQ - NY"]-schedules["SCH - HQ_IMPORT_EXPORT"]
    hourly["HQ_actual_minus_original_schedule_MW"] = hourly.HQ_native_actual_import_MW - hourly.HQ_original_schedule_with_Cedars_MW
    hourly["NYIS_bilateral_sum_minus_reported_total_MW"] = totals.bilateral_sum_minus_reported_total_mw
    hourly["EIA_source_quality_qualified"] = existing.HQ_source_qualified
    hourly["EIA_source_quality_reason"] = source_quality.quality_reason
    for col in par:
        hourly[col] = par[col].to_numpy()
    for method in ["backward_hold", "linear", "arithmetic_mean"]:
        hourly[f"PAR_{method}_minus_frozen_MW"] = hourly[f"PAR_total_{method}_MW"] - hourly.PAR_total_forward_hold_MW
    aggregation_common = qualified & np.isfinite(hourly[[f"PAR_total_{m}_MW" for m in ["forward_hold", "backward_hold", "linear", "arithmetic_mean"]]].to_numpy()).all(axis=1)
    require(np.array_equal(aggregation_common, qualified), "Alternative aggregations must use all fixed8651hours")
    hourly["PAR_aggregation_common_cohort"] = aggregation_common
    stats = []
    for name in ["HQ_native_actual_import_MW", "HQ_original_schedule_with_Cedars_MW", "HQ_original_Cedars_schedule_MW", "HQ_NY_minus_import_export_schedule_MW", "HQ_actual_minus_original_schedule_MW", "PAR_total_forward_hold_MW", "PAR_backward_hold_minus_frozen_MW", "PAR_linear_minus_frozen_MW", "PAR_arithmetic_mean_minus_frozen_MW", "NYIS_bilateral_sum_minus_reported_total_MW"]:
        stats.append(dict(quantity=name, cohort="fixed8651", **summary(hourly.loc[qualified, name])))
    monthly = []
    for month in range(1, 13):
        mask = qualified & (axis.tz_convert("America/New_York").month == month)
        for name in ["HQ_actual_minus_original_schedule_MW", "PAR_backward_hold_minus_frozen_MW", "PAR_linear_minus_frozen_MW", "PAR_arithmetic_mean_minus_frozen_MW"]:
            monthly.append(dict(month=month, quantity=name, **summary(hourly.loc[mask, name])))
    # Predetermined diagnostic probes: hold native PG, demand, and terminal-loss
    # correction fixed. This is an algebraic sensitivity, never a fresh AC run.
    probe_changes = {
        "current_frozen_inputs": np.zeros(len(axis)),
        "PAR_backward_hold_only": hourly.PAR_backward_hold_minus_frozen_MW.to_numpy(),
        "PAR_linear_interpolation_only": hourly.PAR_linear_minus_frozen_MW.to_numpy(),
        "PAR_unweighted_sample_mean_only": hourly.PAR_arithmetic_mean_minus_frozen_MW.to_numpy(),
        "HQ_original_schedule_including_Cedars_only": -hourly.HQ_actual_minus_original_schedule_MW.to_numpy(),
    }
    probe_rows = []
    for name, change in probe_changes.items():
        probe_rows.append(dict(probe=name, **performance(baseline.primary_Moses_MW + change, baseline.observed_Moses_MW, qualified),
            mean_absolute_input_change_MW=float(abs(change[qualified]).mean()),
            fresh_AC_replay_run=False, source_replacement_promoted=False))
    suspicious = qualified & hourly.NYIS_bilateral_sum_minus_reported_total_MW.abs().gt(2.5).to_numpy()
    source_discrepancy_rows = []
    for label, mask in [("all_fixed8651", qualified), ("bilateral_total_discrepancy_above_2_5MW", suspicious),
                        ("remaining_fixed_cohort", qualified & ~suspicious)]:
        source_discrepancy_rows.append(dict(cohort=label, **performance(baseline.primary_Moses_MW, baseline.observed_Moses_MW, mask),
            absolute_error_share_of_fixed_cohort_percent=float(100*abs(baseline.residual_primary_MW[mask]).sum()/abs(baseline.residual_primary_MW[qualified]).sum()),
            HQ_actual_schedule_difference_MAE_MW=float(abs(hourly.HQ_actual_minus_original_schedule_MW[mask]).mean()),
            reported_total_exactly_zero_hours=int(totals.NYIS_reported_total_actual_import_mw[mask].eq(0).sum())))
    counterpart = pd.read_csv(read(WEST / "counterparty_actual_comparison.csv"))
    require(np.array_equal(counterpart.timestamp_utc, baseline.timestamp_utc), "Counterparty time axis changed")
    detail = hourly.loc[suspicious, ["hour_index", "timestamp_utc", "state_index", "HQ_native_actual_import_MW", "HQ_actual_minus_original_schedule_MW", "NYIS_bilateral_sum_minus_reported_total_MW"]].copy()
    detail["reported_total_import_MW"] = totals.NYIS_reported_total_actual_import_mw[suspicious]
    detail["sum_bilateral_import_MW"] = totals.sum_all_four_actual_import_mw[suspicious]
    detail["Moses_residual_MW"] = baseline.residual_primary_MW[suspicious]
    for name in ["NYIS_minus_ISNE_reported_import_mw", "NYIS_minus_PJM_reported_import_mw", "NYIS_minus_IESO_reported_import_mw"]:
        detail[name] = counterpart[name][suspicious]
    scope_path = Path(__file__).with_name("source_scope.json")
    scope = json.loads(read(scope_path).read_text())
    for source in scope["sources"]:
        if source.get("local_path"):
            read(ROOT / source["local_path"])
    write_csv(hourly, "hourly_boundary_diagnostics.csv")
    write_csv(pd.DataFrame(stats), "boundary_difference_statistics.csv")
    write_csv(pd.DataFrame(monthly), "monthly_boundary_difference_statistics.csv")
    write_csv(counterpart_counts, "eia_native_counterpart_availability.csv")
    write_csv(timing, "P34_native_timing_reconstruction.csv")
    write_csv(pd.DataFrame(probe_rows), "algebraic_probe_metrics.csv")
    write_csv(pd.DataFrame(source_discrepancy_rows), "total_sum_discrepancy_residual_contribution.csv")
    write_csv(detail, "total_sum_discrepancy_qualified_hours.csv")
    limitations = [
        "NYIS HQT is one physical BA-to-BA net aggregate; it does not independently resolve Chateauguay, Cedars or through wheeling.",
        "No HQT-to-NYIS or IESO-to-NYIS reporter is present in the two archived EIA bulk files; ISNE and PJM are present. The separate IESO yearly report supplies its comparison. Absence is not proof of inaccurate NYIS HQT telemetry.",
        "Native P34 CSV header says Flow (MWH); treatment as a power-flow snapshot follows the existing P34 contract and published PAR flow identity. The inspected public source does not specify whether a timestamp labels an instantaneous point or preceding/following averaging interval.",
        "Backward hold and linear interpolation are explicit interval-convention sensitivity probes, not source-validated replacements or evidence that the frozen forward hold is wrong.",
        "HQ P32 schedules are distinct from actual metered flow. HQ_IMPORT_EXPORT overlaps HQ-NY; it must not be added to HQ-NY plus Cedars.",
        "A public regional actual series and a source-verified PAR sign do not certify the reduced model's geographical cut or the public Moses South meter membership.",
        "All source-quality defects already excluded by the frozen mask remain excluded. Internal observations only score predetermined algebraic alternatives; they do not select source interpretations or promote replacements.",
        "Bilateral-versus-total reporting discrepancies are real source inconsistencies, but their allocation to HQ or any other individual neighbor is not identifiable from the sum. No source-quality mask is changed here.",
    ]
    manifest = [{"path": p, "sha256": h, "bytes": (ROOT/p).stat().st_size} for p,h in DEPENDENCIES.items()]
    unchanged = all(sha(ROOT/p) == h for p,h in DEPENDENCIES.items())
    require(unchanged, "A frozen input changed while the source audit was running")
    report = dict(status="completed_native_source_reconstruction_and_explicit_aggregation_diagnostics", created_utc=datetime.now(timezone.utc).isoformat(),
        physical_hours=8760, qualified_hours=int(qualified.sum()), new_AC_power_flows_run=0, defaults_changed=False,
        source_sign_fitted_to_internal_observations=False, source_replacement_promoted=False, checks=checks,
        HQ_clock="native UTC Time at End of Hour minus one hour; numeric interchange negated to make NY imports positive",
        PAR_clock="native America/New_York timestamps with explicit fall fold from observed clock rewind; all8760UTCslots retained",
        PAR_positive_direction="Ontario to New York; official diagram effective2024-12-03", PAR_native_metadata=par_metadata,
        HQT_counterpart_reported_in_archived_bulk=bool(counterpart_counts.reporter.eq("HQT").any()),
        EIA_quality_rejected_hours=int((~existing.HQ_source_qualified).sum()),
        EIA_rejected_hours_in_fixed_cohort=int((qualified & ~existing.HQ_source_qualified).sum()),
        P34_incomplete_coverage_hours=int((~np.isfinite(hourly.PAR_total_forward_hold_MW)).sum()),
        fixed_cohort_P34_non12_sample_hours=int(((hourly.PAR_25118_native_count != 12) | (hourly.PAR_25119_native_count != 12))[qualified].sum()),
        fixed_cohort_bilateral_total_discrepancies_above_2_5MW=int((abs(hourly.NYIS_bilateral_sum_minus_reported_total_MW[qualified]) > 2.5).sum()),
        source_scope=scope, algebraic_probe_policy="All predetermined alternatives retained; hold native PG, gross demand and terminal correction fixed; no AC rerun or source promotion",
        limitations=limitations, frozen_sources_preserved=unchanged, source_manifest=manifest,
        audit_script_sha256=sha(Path(__file__)))
    (OUT/"boundary_audit_receipt.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:report[k] for k in ["status", "qualified_hours", "checks", "PAR_native_metadata", "fixed_cohort_P34_non12_sample_hours", "fixed_cohort_bilateral_total_discrepancies_above_2_5MW"]}, indent=2))
    print(pd.DataFrame(stats).to_string(index=False))


if __name__ == "__main__":
    main()
