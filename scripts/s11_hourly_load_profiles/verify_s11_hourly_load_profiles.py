"""Independently reconcile generated S11 profiles with raw NYISO CSVs.

Run with a Python environment containing NumPy and SciPy. No MATLAB process,
builder reports, serialized allocation tables, or network access is used.
The saved case's signed QD/Pd ratios describe its constant-power component;
this verifier makes no claim about measured Q demand or AC feasibility.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from scipy.io import loadmat


MONTHS = ("201901", "201904", "201907", "202501", "202504", "202507")
ZONE_NAMES = (
    "WEST", "GENESE", "CENTRL", "NORTH", "MHK VL", "CAPITL",
    "HUD VL", "MILLWD", "DUNWOD", "N.Y.C.", "LONGIL",
)
ZONE_LETTERS = tuple("ABCDEFGHIJK")
ZONE_CODES = (65, 66, 67, 68, 69, 70, 71, 73, 72, 74, 75)
SOURCE_SCHEMA = ["Time Stamp", "Time Zone", "Name", "PTID", "Integrated Load"]
TIME_COLUMNS = ["timestamp_utc", "timestamp_local", "source_time_zone"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def check_close(actual: np.ndarray, expected: np.ndarray, label: str,
                tolerance: float = 1e-8) -> float:
    require(actual.shape == expected.shape,
            f"{label}: shape {actual.shape} differs from {expected.shape}")
    require(bool(np.isfinite(actual).all()), f"{label}: nonfinite values")
    error = float(np.max(np.abs(actual - expected)))
    require(error <= tolerance, f"{label}: maximum error {error:g} > {tolerance:g}")
    return error


def vector(profile: dict, field: str, dtype: type = float) -> np.ndarray:
    return np.asarray(profile[field], dtype=dtype).reshape(-1)


def read_base_case(case_path: Path) -> np.ndarray:
    text = case_path.read_text(encoding="utf-8-sig")
    match = re.search(r"mpc\.bus\s*=\s*\[(.*?)\];", text, re.DOTALL)
    require(match is not None, "Saved S11 case is missing its explicit bus matrix")
    matrix_text = re.sub(r"%[^\n]*", "", match.group(1))
    rows = [[float(item) for item in row.split()]
            for row in matrix_text.split(";") if row.strip()]
    bus = np.asarray(rows, dtype=float)
    require(bus.shape == (49, 13), f"Unexpected saved bus matrix: {bus.shape}")
    require(len(set(bus[:, 0])) == 49, "Saved bus IDs are not unique")
    require(bool(np.isfinite(bus).all()), "Nonfinite saved bus matrix")
    return bus


def read_sources(cache: Path) -> tuple[list, np.ndarray, list, int, int]:
    """Read published observations by exact source keys, independent of row order."""
    records = {}
    metadata = {}
    coverage = []
    file_count = 0
    row_count = 0
    names_to_zone = dict(zip(ZONE_NAMES, ZONE_LETTERS))
    for month in MONTHS:
        year, month_number = int(month[:4]), int(month[4:])
        days = calendar.monthrange(year, month_number)[1]
        source_tag = "EST" if month_number == 1 else "EDT"
        local_zone = timezone(timedelta(hours=-5 if source_tag == "EST" else -4))
        start = datetime(year, month_number, 1, tzinfo=local_zone)
        expected_local = [start + timedelta(hours=n) for n in range(days * 24)]
        expected_utc = [stamp.astimezone(timezone.utc) for stamp in expected_local]
        expected_set = set(expected_utc)
        observed = set()
        folder = cache / f"{month}_palIntegrated"
        files = sorted(folder.glob("*palIntegrated.csv"))
        require(len(files) == days, f"{month}: expected {days} daily source files")
        for day, path in enumerate(files, 1):
            require(path.name == f"{month}{day:02d}palIntegrated.csv",
                    f"Unexpected source daily filename: {path}")
            file_rows = 0
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                require(reader.fieldnames == SOURCE_SCHEMA, f"Source schema changed: {path}")
                for line, row in enumerate(reader, 2):
                    label = f"{path.name}:{line}"
                    require(row["Time Zone"] == source_tag, f"Wrong source timezone: {label}")
                    wall = datetime.strptime(row["Time Stamp"], "%m/%d/%Y %H:%M:%S")
                    require(wall.strftime("%Y%m%d") == f"{month}{day:02d}",
                            f"Source date disagrees with filename: {label}")
                    local = wall.replace(tzinfo=local_zone)
                    utc = local.astimezone(timezone.utc)
                    require(utc in expected_set, f"Off-hour source timestamp: {label}")
                    name = row["Name"]
                    require(name in names_to_zone, f"Unknown source zone: {label}")
                    zone = names_to_zone[name]
                    require(int(row["PTID"]) == 61752 + ZONE_LETTERS.index(zone),
                            f"Source name/PTID disagreement: {label}")
                    value = float(row["Integrated Load"])
                    require(math.isfinite(value) and value >= 0, f"Invalid source load: {label}")
                    key = (utc, zone)
                    require(key not in records, f"Duplicate source timestamp/zone: {label}")
                    records[key] = value
                    stamp_metadata = (local.isoformat(timespec="seconds"), source_tag)
                    require(utc not in metadata or metadata[utc] == stamp_metadata,
                            f"Source time labels differ between zones: {label}")
                    metadata[utc] = stamp_metadata
                    observed.add(utc)
                    file_rows += 1
            require(file_rows == 24 * 11, f"{path.name}: incomplete daily records")
            file_count += 1
            row_count += file_rows
        require(observed == expected_set, f"{month}: missing source hours")
        total = []
        for utc in expected_utc:
            require(all((utc, zone) in records for zone in ZONE_LETTERS),
                    f"Missing source zone at {utc}")
            total.append(math.fsum(records[utc, zone] for zone in ZONE_LETTERS))
        coverage.append({"month": month, "hours": len(expected_utc),
                         "minimum_pd_mw": min(total), "maximum_pd_mw": max(total)})
    timestamps = sorted(metadata)
    labels = [(utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
               *metadata[utc]) for utc in timestamps]
    loads = np.asarray([[records[utc, zone] for utc in timestamps]
                        for zone in ZONE_LETTERS], dtype=float)
    return labels, loads, coverage, file_count, row_count


def read_wide_csv(path: Path, bus_ids: np.ndarray, labels: list) -> np.ndarray:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        require(header == TIME_COLUMNS + [f"bus_{int(bus)}" for bus in bus_ids],
                f"Wrong column identity/order in {path.name}")
        values = []
        for index, row in enumerate(reader):
            require(index < len(labels), f"Extra CSV hour in {path.name}")
            require(len(row) == 52, f"Wrong CSV row width in {path.name}:{index + 2}")
            require(tuple(row[:3]) == labels[index],
                    f"Source timestamp mismatch in {path.name}:{index + 2}")
            values.append([float(value) for value in row[3:]])
        require(len(values) == len(labels), f"Missing CSV hours in {path.name}")
    return np.asarray(values, dtype=float).T


def verify(root: Path, output: Path) -> dict:
    helper = root / "System Matpower Format" / "NY_Lite"
    bus = read_base_case(helper.parent / "npcc_ny_lite_s11_dlr_pf_base.m")
    bus_ids, base_p, base_q = bus[:, 0], bus[:, 2], bus[:, 3]
    code_to_zone = dict(zip(ZONE_CODES, ZONE_LETTERS))
    require(all(code in code_to_zone for code in bus[:, 10]), "Unknown saved case zone code")
    # H/I are deliberately not in numeric order: PERFORM 73=H and 72=I.
    zones = np.asarray([code_to_zone[code] for code in bus[:, 10]])
    labels, source_p, coverage, file_count, row_count = read_sources(helper / "nyiso_public_cache")
    require(file_count == 184 and row_count == 48576 and len(labels) == 4416,
            "Unexpected six-month source coverage")
    profile = loadmat(output / "s11_hourly_load_profiles.mat", simplify_cells=True)["profile"]
    require(np.array_equal(vector(profile, "bus_id"), bus_ids), "MAT bus order differs from case")
    require(np.array_equal(vector(profile, "zone", str), zones), "MAT zones differ from saved case")
    check_close(vector(profile, "base_pd_mw"), base_p, "Saved baseline Pd", 0)
    check_close(vector(profile, "base_qd_mvar"), base_q, "Saved baseline Qd", 0)
    for index, field in enumerate(TIME_COLUMNS):
        require(vector(profile, field, str).tolist() == [row[index] for row in labels],
                f"MAT {field} differs from raw source")
    pd = np.asarray(profile["pd_mw"], dtype=float)
    qd = np.asarray(profile["qd_mvar"], dtype=float)
    require(pd.shape == qd.shape == (49, 4416), "Wrong bus-by-hour matrix shape")
    require(bool((pd >= 0).all()), "Generated active demand is negative")
    require(bool((base_p >= 0).all()), "Saved base active demand is negative")
    require(bool((base_q[base_p == 0] == 0).all()), "Unsupported zero-P/nonzero-Q baseline")
    weights = np.zeros(49)
    expected_p = np.zeros_like(pd)
    expected_q = np.zeros_like(qd)
    zone_errors = []
    for zone_index, zone in enumerate(ZONE_LETTERS):
        selected = zones == zone
        denominator = float(np.sum(base_p[selected]))
        require(denominator > 0, f"No positive saved demand in zone {zone}")
        weights[selected] = base_p[selected] / denominator
        # Reconstruct directly by zonal scaling of the saved case, independently
        # of the builder's stored weights and per-bus Q/P vector.
        expected_p[selected] = np.outer(base_p[selected], source_p[zone_index] / denominator)
        expected_q[selected] = np.outer(base_q[selected], source_p[zone_index] / denominator)
        zone_errors.append(check_close(np.sum(pd[selected], axis=0), source_p[zone_index],
                                       f"Zone {zone} active-load conservation"))
    check_close(vector(profile, "allocation_weight"), weights, "Allocation weights", 1e-13)
    bus_p_error = check_close(pd, expected_p, "Independent per-bus active allocation")
    bus_q_error = check_close(qd, expected_q, "Baseline signed reactive scaling")
    zero = base_p == 0
    require(bool((pd[zero] == 0).all() and (qd[zero] == 0).all()),
            "Zero-load buses acquired P or Q demand")
    total_error = check_close(np.sum(pd, axis=0), np.sum(source_p, axis=0),
                              "Statewide active-load conservation")
    csv_errors = {}
    for filename, values in (("pd_mw.csv", pd), ("qd_mvar.csv", qd)):
        csv_errors[filename] = check_close(read_wide_csv(output / filename, bus_ids, labels),
                                          values, f"MAT/CSV agreement: {filename}")
    peak_index = [row[0] for row in labels].index("2025-07-29T22:00:00Z")
    peak_p_error = check_close(pd[:, peak_index], base_p, "Known saved peak Pd", 1e-4)
    peak_q_error = check_close(qd[:, peak_index], base_q, "Known saved peak Qd", 1e-6)
    return {
        "passed": True, "bus_count": 49, "hours": 4416, "source_daily_files": file_count,
        "source_zone_hour_rows": row_count, "positive_load_buses": int((~zero).sum()),
        "zero_load_bus_ids": bus_ids[zero].astype(int).tolist(),
        "maximum_zonal_pd_error_mw": max(zone_errors),
        "maximum_statewide_pd_error_mw": total_error,
        "maximum_independent_bus_pd_error_mw": bus_p_error,
        "maximum_independent_bus_qd_error_mvar": bus_q_error,
        "maximum_csv_mat_errors": csv_errors,
        "known_peak_pd_error_mw": peak_p_error, "known_peak_qd_error_mvar": peak_q_error,
        "complete_sampled_months": coverage, "full_year_coverage": False,
        "reactive_model": "saved_case_signed_constant_power_Qd_scaled_with_zonal_Pd",
        "all_hours_power_flow_validated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = args.output or args.root / "output" / "s11_hourly_load_profiles"
    try:
        result = verify(args.root, output)
    except (ValueError, KeyError, FileNotFoundError, OSError) as error:
        print(json.dumps({"passed": False, "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
