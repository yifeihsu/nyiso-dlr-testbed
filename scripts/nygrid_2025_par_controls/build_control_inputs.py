"""Compile source-only 2025 St. Lawrence PAR controls without internal flows.

The two measured P34 targets retain their raw values and quality masks. Their
positive direction is documented as Ontario to New York from 2024-12-03.
The 300 MVA equipment values support only a necessary |P| <= nominal S screen;
they are not a complete P/Q, thermal, tap, outage or operational-feasibility
certificate. P53A schedules retain the original G/L code and remain diagnostic
until their numeric sign convention is independently established.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import zipfile

import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_par_controls/controls"
OLD = ROOT / "output/nygrid_2025_moses_audit/exchanges"
SCHEDULES = ROOT / "output/nygrid_2025_par_controls/sources/schedules"
PTIDS = np.array([25118, 25119], dtype=np.int32)
TZ = "America/New_York"
YEAR = 2025


def require(value, message):
    if not bool(value):
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def physical_hours():
    return pd.date_range("2025-01-01", "2026-01-01", inclusive="left", freq="h", tz=TZ).tz_convert("UTC")


def equal_numeric(a, b, tolerance=1e-9):
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and np.array_equal(np.isnan(a), np.isnan(b)) and np.allclose(a, b, atol=tolerance, rtol=0, equal_nan=True)


def p_only_screen(values, limit, label, allow_missing=False):
    """Never average first, clip a violation, or call this full MVA feasibility."""
    values = np.asarray(values, dtype=float)
    require(np.isfinite(limit) and limit > 0, "Invalid nominal-S screen")
    require(not np.isinf(values).any(), label + ": infinite raw value")
    if not allow_missing:
        require(np.isfinite(values).all(), label + ": missing source value")
    finite = np.isfinite(values)
    maximum = float(np.max(np.abs(values[finite]), initial=0.))
    require(maximum <= limit + 1e-9, label + ": necessary |P| <= nominal S screen failed; no clipping allowed")
    return dict(records=int(values.size), finite_records=int(finite.sum()), missing_records=int((~finite).sum()),
                minimum_public_mw=float(values[finite].min()) if finite.any() else None,
                maximum_public_mw=float(values[finite].max()) if finite.any() else None,
                maximum_absolute_public_mw=maximum, necessary_abs_p_screen_mw=float(limit),
                violations=0, scope="necessary_abs_P_le_nominal_S_only", full_P_Q_rating_feasible=False)


def parse_schedule(payload: bytes, member: str):
    lines = [line for line in payload.decode("utf-8-sig").splitlines() if line.strip()]
    header = lines[0].split()
    require(len(header) == 5, "P53A requires five declared header fields: " + member)
    require(header[0] == "00:00", "P53A start must be local midnight: " + member)
    day = datetime.strptime(header[1], "%d-%b-%Y").date()
    require(day.year == YEAR and day.strftime("%Y%m%d") == member[:8], "P53A filename/date mismatch: " + member)
    step, periods, rows = map(int, header[2:])
    require(step == 60, "P53A interval is not hourly: " + member)
    start = pd.Timestamp(day).tz_localize(TZ)
    end = pd.Timestamp(day + timedelta(days=1)).tz_localize(TZ)
    duration_minutes = int((end.tz_convert("UTC") - start.tz_convert("UTC")).total_seconds() / 60)
    require(periods in [23, 24, 25] and periods * step == duration_minutes,
            "P53A declared period count disagrees with physical local day: " + member)
    require(len(lines) - 1 == rows, "P53A declared device-row count differs: " + member)
    times = pd.date_range(start.tz_convert("UTC"), periods=periods, freq="h")
    values = np.full((periods, 2), np.nan)
    codes = np.full((periods, 2), "", dtype="U1")
    selected = set()
    for line in lines[1:]:
        fields = line.split()
        require(len(fields) == periods + 2, "P53A data row length differs from period count: " + member)
        ptid = int(fields[0])
        if ptid not in PTIDS:
            continue
        require(ptid not in selected, "Duplicate P53A target PTID: " + member)
        selected.add(ptid)
        require(fields[1] in ["G", "L"], "Unknown P53A control code: " + member)
        j = int(np.flatnonzero(PTIDS == ptid)[0])
        values[:, j] = np.array([float(v) for v in fields[2:]], dtype=float)
        require(not np.isinf(values[:, j]).any(), "Infinite P53A value: " + member)
        codes[:, j] = fields[1]
    # Missing PTIDs remain missing, never copied from the other device or day.
    return times, values, codes, dict(source_member=member, date_local=day.isoformat(),
        header_start_local=header[0], interval_minutes=step, declared_periods=periods,
        physical_day_minutes=duration_minutes, declared_device_rows=rows,
        selected_ptids="|".join(map(str, sorted(selected))), missing_selected_ptids="|".join(map(str, sorted(set(PTIDS) - selected))),
        header=lines[0], member_sha256=hashlib.sha256(payload).hexdigest())


def focused_checks():
    # An instantaneous excursion must fail even when its arithmetic mean passes.
    failed = False
    try:
        p_only_screen([301., -299.], 300., "native spike")
    except ValueError:
        failed = True
    require(failed and abs(np.mean([301., -299.])) < 300, "Native-spike guard regressed")
    examples = [("20250309", "09-MAR-2025", 23), ("20251102", "02-NOV-2025", 25)]
    for date, date_label, count in examples:
        data = f"00:00 {date_label} 60 {count} 2\n25118 G " + " ".join(map(str, range(count))) + "\n25119 G " + " ".join(["0"] * count) + "\n"
        times, values, _, _ = parse_schedule(data.encode(), date + "parSchedule.txt")
        require(len(times) == count and times.is_unique and np.all(np.diff(times.asi8) == 3600e9), "DST physical-hour fixture failed")
        require(np.array_equal(values[:, 0], np.arange(count)), "Schedule period order changed")
        local = times.tz_convert(TZ)
        if count == 23:
            require(not np.any(local.hour == 2), "Spring nonexistent hour invented")
        else:
            require(np.sum(local.hour == 1) == 2 and local[1].utcoffset() != local[2].utcoffset(), "Fall folds merged")
        bad = data.replace(f"60 {count} 2", "60 24 2")
        rejected = False
        try:
            parse_schedule(bad.encode(), date + "parSchedule.txt")
        except ValueError:
            rejected = True
        require(rejected, "Wrong DST period declaration accepted")
    missing = b"00:00 01-JAN-2025 60 24 1\n25118 G " + b"0 " * 24 + b"\n"
    _, values, _, _ = parse_schedule(missing, "20250101parSchedule.txt")
    require(np.isnan(values[:, 1]).all(), "Missing device silently filled")
    return dict(native_resolution_spike_rejected=True, spring_23_hours_preserved=True,
                fall_25_hours_preserved=True, invalid_DST_period_count_rejected=True,
                missing_schedule_device_not_filled=True)


def build(output=OUT):
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT / "output/nygrid_2025_par_controls"), "Outputs must remain in the new PAR package")
    output.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    dependencies = {}

    def read(path):
        path = Path(path)
        dependencies[relative(path)] = sha(path)
        return path

    direction_path = read(ROOT / "output/nygrid_2025_par_controls/sources/direction/direction_verification_receipt.json")
    direction = json.loads(direction_path.read_text())
    directions_path = read(ROOT / "output/nygrid_2025_par_controls/sources/direction/verified_ptid_directions.csv")
    directions = pd.read_csv(directions_path).set_index("ptid")
    require(direction["status"] == "verified_official_direction_for_2025", "P34 direction is not verified")
    require(direction["sign_convention_effective_date"] == "2024-12-03", "Review changed direction effective date")
    require(set(directions.index) == set(PTIDS) and directions.raw_to_ontario_to_new_york_multiplier.eq(1).all(), "Unexpected physical P34 directions")
    direction_manifest = json.loads(read(ROOT / "output/nygrid_2025_par_controls/sources/direction/direction_manifest.json").read_text())
    for record in direction_manifest["files"]:
        require(sha(read(ROOT / record["path"])) == record["sha256"], "Direction source changed: " + record["path"])
    limits_path = read(ROOT / "output/nygrid_2025_par_controls/sources/limits/limits.json")
    limits = json.loads(limits_path.read_text())
    devices = {int(r["ptid"]): r for r in limits["devices"]}
    require(set(devices) == set(PTIDS), "PAR limit identities changed")
    p_limits = np.array([devices[int(i)]["necessary_abs_p_screen_mw"] for i in PTIDS], float)
    for ptid in PTIDS:
        d = devices[int(ptid)]
        require(d["scope"] == "necessary_abs_P_le_nominal_S_only" and d["nominal_mva"] == 300. and d["continuous_mva"] is None,
                "Unsupported expansion of equipment-limit scope")
        require(d["phase_bound_applies_to_reduced_equivalent_SHIFT"] is False, "Physical no-load angle applied to equivalent phase")
        p = read(ROOT / d["phase_design_pdf_path"])
        require(sha(p) == d["phase_design_pdf_sha256"], "Phase-design metadata source changed")
    require(np.array_equal(p_limits, [300., 300.]), "Review changed nominal device limit")
    dispatch_path = read(ROOT / "output/nygrid_2025_dispatch/dispatch/dispatch.mat")
    native = loadmat(dispatch_path, simplify_cells=True, variable_names=["hour_index", "timestamp_utc", "dispatch_qualified", "gamma"])
    hours = physical_hours()
    require(len(hours) == 8760 and hours.is_unique, "Invalid physical-year axis")
    require(pd.DatetimeIndex(pd.to_datetime(native["timestamp_utc"], utc=True)).equals(hours), "Dispatch physical-hour axis differs")
    require(np.array_equal(native["hour_index"], np.arange(1, 8761)), "Dispatch hour IDs differ")
    gamma = float(native["gamma"])
    native_ok = np.asarray(native["dispatch_qualified"], bool)
    require(gamma > 0 and native_ok.sum() == 8663, "Frozen dispatch scale or cohort differs")

    # Read the frozen native-resolution records and separately verify archive bytes.
    raw_path = read(OLD / "par_stlawrence_raw_2025.csv.gz")
    raw = pd.read_csv(raw_path)
    require(set(raw.point_id) == set(PTIDS), "Unexpected raw P34 channel set")
    raw["utc"] = pd.to_datetime(raw.timestamp_utc, utc=True)
    receipts = pd.read_csv(read(OLD / "par_source_receipts.csv"))
    selected = receipts.loc[(receipts.year == YEAR) | ((receipts.year == YEAR + 1) & (receipts.month == 1))]
    require(len(selected) == 13, "P34 requires twelve months and an endpoint archive")
    native_counts = {int(p): 0 for p in PTIDS}
    native_extrema = {int(p): 0. for p in PTIDS}
    members = []
    for r in selected.itertuples(index=False):
        archive_path = read(OLD / "raw" / f"{int(r.year)}{int(r.month):02d}01ParFlows_csv.zip")
        require(sha(archive_path) == r.sha256, "P34 archive hash differs: " + archive_path.name)
        with zipfile.ZipFile(archive_path) as archive:
            for member in sorted(archive.namelist()):
                if int(r.year) != YEAR and member != "20260101ParFlows.csv":
                    continue
                payload = archive.read(member)
                frame = pd.read_csv(io.BytesIO(payload))
                require(list(frame.columns) == ["Timestamp", "Point ID", "Flow (MWH)"], "P34 raw schema differs: " + member)
                for j, ptid in enumerate(PTIDS):
                    source_values = frame.loc[frame["Point ID"] == ptid, "Flow (MWH)"].to_numpy(float)
                    require(len(source_values) > 0, "Native-resolution P34 channel absent: " + member)
                    screen = p_only_screen(source_values, p_limits[j], f"P34{member} PTID{ptid}")
                    frozen = raw.loc[(raw.source_archive == archive_path.name) & (raw.source_member == member) & (raw.point_id == ptid), "original_flow_mw"].to_numpy(float)
                    require(equal_numeric(frozen, source_values, tolerance=1e-10), "Frozen raw P34 values differ from archive: " + member)
                    native_counts[int(ptid)] += len(source_values)
                    native_extrema[int(ptid)] = max(native_extrema[int(ptid)], screen["maximum_absolute_public_mw"])
                members.append(dict(source_archive=relative(archive_path), source_member=member,
                                    member_sha256=hashlib.sha256(payload).hexdigest()))
    require(len(members) == 366 and sum(native_counts.values()) == len(raw), "Raw member/record coverage differs")
    hourly_path = read(OLD / "par_stlawrence_hourly_2025.csv")
    hourly = pd.read_csv(hourly_path)
    require(pd.DatetimeIndex(pd.to_datetime(hourly.timestamp_utc, utc=True)).equals(hours), "Hourly P34 axis differs")
    observed = hourly[["PS33_raw_mw", "PS34_raw_mw"]].to_numpy(float)
    coverage = hourly[["PS33_coverage_seconds", "PS34_coverage_seconds"]].to_numpy(float)
    observed_device_ok = coverage == 3600
    require(np.array_equal(observed_device_ok, np.isfinite(observed)), "P34 finite values and coverage disagree")
    observed_ok = observed_device_ok.all(axis=1)
    require(observed_ok.sum() == 8673 and (observed_ok & native_ok).sum() == 8663, "Frozen P34 quality cohort differs")
    device_audit = []
    for j, ptid in enumerate(PTIDS):
        r = p_only_screen(raw.loc[raw.point_id == ptid, "original_flow_mw"], p_limits[j], f"P34 all raw PTID{ptid}")
        h = p_only_screen(observed[:, j], p_limits[j], f"P34 hourly PTID{ptid}", allow_missing=True)
        require(r["records"] == native_counts[int(ptid)] and r["maximum_absolute_public_mw"] == native_extrema[int(ptid)], "Native screen coverage mismatch")
        device_audit.append(dict(ptid=int(ptid), native_resolution=r, hourly=h))

    schedule_receipts_path = read(SCHEDULES / "acquisition_receipts.json")
    schedule_receipts = json.loads(schedule_receipts_path.read_text())
    require(len(schedule_receipts) == 12 and {r["month"] for r in schedule_receipts} == set(range(1, 13)), "P53A monthly coverage incomplete")
    schedules = np.full((8760, 2), np.nan)
    side_codes = np.full((8760, 2), "", dtype="U1")
    schedule_members = np.full(8760, "", dtype="U32")
    filled = np.zeros(8760, bool)
    day_receipts = []
    for receipt in schedule_receipts:
        path = read(ROOT / receipt["path"])
        require(sha(path) == receipt["sha256"], "P53A archive differs from acquisition receipt")
        with zipfile.ZipFile(path) as archive:
            for member in sorted(archive.namelist()):
                require(member.endswith("parSchedule.txt"), "Unexpected P53A archive member")
                times, values, codes, day = parse_schedule(archive.read(member), member)
                ix = hours.get_indexer(times)
                require(np.all(ix >= 0) and not filled[ix].any(), "P53A duplicate or out-of-year physical-hour keys")
                schedules[ix], side_codes[ix], schedule_members[ix], filled[ix] = values, codes, member, True
                day["archive"] = relative(path)
                day_receipts.append(day)
    require(len(day_receipts) == 365 and filled.all(), "P53A physical-year day coverage incomplete")
    schedule_device_ok = np.isfinite(schedules)
    schedule_ok = schedule_device_ok.all(axis=1)
    require(set(side_codes[schedule_device_ok]) == {"G"}, "Review changed StLawrence P53A control-side codes")
    for j, ptid in enumerate(PTIDS):
        device_audit[j]["P53A_schedule"] = p_only_screen(schedules[:, j], p_limits[j], f"P53A PTID{ptid}", allow_missing=True)
    schedule_sign_verified = False
    # Schedule numeric values are preserved; the hypothetical shared +direction
    # is explicitly diagnostic until G/L semantics are independently verified.
    arrays = dict(schema_version=np.int32(1), year=np.int32(YEAR), hour_index=np.arange(1, 8761, dtype=np.int32),
        timestamp_utc=hours.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy(dtype=str), ptids=PTIDS,
        observed_public_mw=observed, observed_model_mw=observed * gamma,
        schedule_public_mw=schedules, schedule_model_mw=schedules * gamma,
        observed_device_qualified=observed_device_ok, observed_quality=observed_device_ok,
        observed_qualified=observed_ok,
        observed_replay_qualified=observed_ok & native_ok,
        schedule_device_qualified=schedule_device_ok, schedule_qualified=schedule_ok,
        schedule_replay_qualified=schedule_ok & native_ok,
        common_replay_qualified=observed_ok & schedule_ok & native_ok,
        native_dispatch_qualified=native_ok, observed_coverage_seconds=coverage,
        schedule_control_codes=side_codes, gamma=gamma,
        observed_direction_verified=np.bool_(True), schedule_sign_verified=np.bool_(schedule_sign_verified),
        schedule_mode_diagnostic=np.bool_(True), direction_ontario_to_NY_multiplier=np.ones(2, dtype=np.int32),
        p_only_limit_public_mw=p_limits, p_only_limit_model_mw=p_limits * gamma,
        nominal_mva_public=p_limits, full_P_Q_rating_feasible=np.bool_(False),
        hardware_no_load_phase_min_deg=np.array([devices[int(p)]["phase_design_no_load_min_degree"] for p in PTIDS]),
        hardware_no_load_phase_max_deg=np.array([devices[int(p)]["phase_design_no_load_max_degree"] for p in PTIDS]),
        hardware_phase_applies_to_equivalent=np.bool_(False),
        limit_metadata_json=np.array(json.dumps(limits, sort_keys=True)),
        direction_metadata_json=np.array(json.dumps(direction, sort_keys=True)))
    np.savez_compressed(output / "inputs.npz", **arrays)
    mat_arrays = dict(arrays)
    for key in ["timestamp_utc", "schedule_control_codes"]:
        mat_arrays[key] = arrays[key].astype(object)
    savemat(output / "inputs.mat", mat_arrays, do_compression=True, oned_as="column")
    local = hours.tz_convert(TZ)
    table = pd.DataFrame(dict(hour_index=arrays["hour_index"], timestamp_utc=arrays["timestamp_utc"],
        timestamp_local=local.strftime("%Y-%m-%dT%H:%M:%S"), time_zone=local.strftime("%Z"),
        dst_fold=[t.fold for t in local], native_dispatch_qualified=native_ok,
        observed_qualified=observed_ok, schedule_qualified=schedule_ok,
        observed_replay_qualified=arrays["observed_replay_qualified"],
        schedule_replay_qualified=arrays["schedule_replay_qualified"],
        common_replay_qualified=arrays["common_replay_qualified"], schedule_source_member=schedule_members))
    for j, ptid in enumerate(PTIDS):
        for field, values in [("observed_public_mw", observed), ("observed_model_mw", observed * gamma),
                              ("schedule_raw_public_mw", schedules), ("schedule_raw_model_mw", schedules * gamma),
                              ("observed_coverage_seconds", coverage), ("observed_qualified", observed_device_ok),
                              ("schedule_qualified", schedule_device_ok), ("schedule_control_code", side_codes)]:
            table[f"ptid_{ptid}_{field}"] = values[:, j]
    table.to_csv(output / "hourly_controls.csv", index=False, lineterminator="\n")
    pd.DataFrame(day_receipts).to_csv(output / "schedule_day_receipts.csv", index=False, lineterminator="\n")
    pd.DataFrame(members).to_csv(output / "P34_native_member_receipts.csv", index=False, lineterminator="\n")
    (output / "necessary_p_only_screen.json").write_text(json.dumps(dict(
        status="passed_necessary_P_only_screen_not_full_physical_feasibility",
        native_resolution_screen_precedes_hourly_aggregation=True, devices=device_audit,
        clipping_performed=False, equivalent_phase_clipping_performed=False), indent=2) + "\n")
    with np.load(output / "inputs.npz", allow_pickle=False) as saved:
        for key in ["observed_public_mw", "schedule_public_mw", "observed_model_mw", "schedule_model_mw"]:
            require(equal_numeric(saved[key], arrays[key], tolerance=0), "NPZ roundtrip changed values: " + key)
    saved = loadmat(output / "inputs.mat", simplify_cells=True)
    for key in ["observed_public_mw", "schedule_public_mw", "observed_model_mw", "schedule_model_mw"]:
        require(equal_numeric(saved[key], arrays[key], tolerance=0), "MAT roundtrip changed values: " + key)
    helper_checks = focused_checks()
    read(Path(__file__))
    for path, value in dependencies.items():
        require(sha(ROOT / path) == value, "Input changed during compiler run: " + path)
    receipt = dict(status="complete_source_only_two_device_controls", created_utc=datetime.now(timezone.utc).isoformat(),
        started_utc=started, python=platform.python_version(), ptids=PTIDS.tolist(), physical_hours=8760,
        observed_qualified_hours=int(observed_ok.sum()), observed_replay_hours=int((observed_ok & native_ok).sum()),
        schedule_qualified_hours=int(schedule_ok.sum()), schedule_replay_hours=int((schedule_ok & native_ok).sum()),
        common_replay_hours=int(arrays["common_replay_qualified"].sum()), native_P34_records=len(raw),
        native_P34_records_by_device=native_counts, native_P34_source_days=366,
        native_P34_endpoint_scope="Includes the frozen Jan1,2026 endpoint day; all retained raw records screened, not only averaged or replay-qualified hours.",
        schedule_source_days=365, schedule_period_count_histogram=pd.Series([r["declared_periods"] for r in day_receipts]).value_counts().sort_index().to_dict(),
        gamma=gamma, input_device_direction="Ontario100_to_NewYork_Moses48_positive",
        P34_direction_verified=True, P34_direction_effective_date="2024-12-03",
        P53A_sign_verified=False, P53A_mode="diagnostic_raw_signed_G_control_code;shared_direction_not_promoted",
        P53A_time_policy="Declared midnight local date and60minute intervals; count must equal physical UTC duration to next local midnight. Preserve both fallfolds; invent no spring hour.",
        P34_time_policy="Frozen forward-held means; complete3600seconds and source gap<=600seconds; no fill or clipping.",
        missing_data_policy="Retain NaN per device and explicit masks; no interpolation, zero-fill or cross-device substitution.",
        necessary_active_power_screen_passed=True, full_P_Q_thermal_or_operational_feasibility_verified=False,
        actual_tap_trajectory_used=False, physical_no_load_phase_bound_applied_to_equivalent=False,
        internal_interface_observations_read=False, sign_or_parameters_fit_to_internal_flows=False,
        frozen_inputs_modified=False, all_input_hashes_unchanged=True, focused_checks=helper_checks,
        limitations=["The nominal300MVA screen is only necessary |P|<=S; Q,current,temperature,voltage,tap,emergency and outage capability remain unverified.",
                     "The physical +/-60degree no-load design range is metadata and is not a bound on an aggregate equivalent's phase offset.",
                     "P53A schedules are source-derived with correct physical hours, but their G/L numeric sign semantics remain explicitly diagnostic.",
                     "P34's raw Flow(MWH) column retains the existing posted-flow numeric convention; no energy/time rescaling was introduced."],
        dependencies=[dict(path=p, sha256=h) for p, h in sorted(dependencies.items())],
        outputs=[dict(path=relative(p), bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(output.iterdir())
                 if p.is_file() and p.name not in ["input_receipt.json", "compiler_failure.json"]])
    (output / "input_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ["status", "physical_hours", "observed_qualified_hours", "observed_replay_hours", "schedule_qualified_hours", "schedule_replay_hours", "native_P34_records", "P53A_sign_verified"]}), flush=True)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    try:
        build(args.output)
    except Exception as error:
        folder = Path(args.output).resolve()
        if folder.is_relative_to(ROOT / "output/nygrid_2025_par_controls"):
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "compiler_failure.json").write_text(json.dumps(dict(status="failed_closed", error=str(error),
                clipped=False, frozen_inputs_modified=False), indent=2) + "\n")
        raise
