"""Independently verify serialized S11 hourly operating profiles and AC physics.

Uses NumPy/SciPy and literal MATPOWER case data; it does not call MATLAB,
MATPOWER, or the dispatch implementation. JSON goes to stdout. A partial
campaign may pass consistency checks, but is explicitly reported as partial.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import numpy as np
from scipy.io import loadmat


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "output/s11_hourly_generation"
CASE = ROOT / "System Matpower Format/npcc_ny_lite_s11_dlr_pf_base.m"
TIME_FIELDS = ("timestamp_utc", "timestamp_local", "source_time_zone")
CSV_METADATA = TIME_FIELDS + (
    "generation_valid", "interchange_source_qualified", "interchange_gap_completed"
)
BOUNDARY_NAMES = (
    "HQ_NY_MOSES", "NE_NY_NORTHFIELD", "NE_NY_PV", "OH_NY_NIAGARA",
    "PJM_NY_WATERCURE", "PJM_NY_WRHL", "PJM_NY_RAMAPO", "PJM_NY_GOETHALS",
)
TRUSTED_ROWS = np.array([69, 70, 71, 82, 83]) - 1
ARRAY_CSV = {
    "pg_mw": "gen_pg_mw.csv", "qg_mvar": "gen_qg_mvar.csv",
    "vg_pu": "gen_vg_pu.csv", "gen_status": "gen_status.csv",
}


def require(condition, message):
    if not bool(condition):
        raise AssertionError(message)


def maximum(values):
    values = np.asarray(values)
    return float(np.max(values)) if values.size else 0.0


def text(values):
    return np.asarray(values, dtype=str).reshape(-1)


def boolean(values):
    values = text(values)
    lower = np.char.lower(values)
    require(np.isin(lower, ["true", "false", "1", "0"]).all(), "Invalid boolean encoding")
    return np.isin(lower, ["true", "1"])


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def literal_case(path):
    """Read only literal numeric matrices and quoted metadata, never execute code."""
    source = path.read_text(encoding="utf-8-sig")
    result = {}
    for field in ("bus", "gen", "branch"):
        block = re.search(r"mpc\." + field + r"\s*=\s*\[(.*?)\];", source, re.S)
        require(block is not None, f"Missing literal {field} in {path}")
        body = re.sub(r"%[^\n]*", "", block[1])
        result[field] = np.array([
            [float(value) for value in row.split()]
            for row in body.split(";") if row.strip()
        ])
    base = re.search(r"mpc\.baseMVA\s*=\s*([\d.eE+-]+)\s*;", source)
    require(base is not None, "Missing literal baseMVA")
    result["baseMVA"] = float(base[1])
    for field in ("genfuel", "gentype"):
        block = re.search(r"mpc\." + field + r"\s*=\s*\{(.*?)\};", source, re.S)
        require(block is not None, f"Missing literal {field}")
        result[field] = np.asarray(re.findall(r"'([^']*)'", block[1]))
    return result


def admittance(case):
    """Construct nodal and terminal admittance from PI branches and complex taps."""
    bus, branch, base = case["bus"], case["branch"], case["baseMVA"]
    index = {int(bus_id): row for row, bus_id in enumerate(bus[:, 0])}
    require(len(index) == len(bus), "Duplicate bus identity")
    ybus = np.diag((bus[:, 4] + 1j * bus[:, 5]) / base)
    yf = np.zeros((len(branch), len(bus)), dtype=complex)
    yt = np.zeros_like(yf)
    f = np.array([index[int(value)] for value in branch[:, 0]])
    t = np.array([index[int(value)] for value in branch[:, 1]])
    for k, row in enumerate(branch):
        require(row[10] in (0, 1), "Branch status must be binary")
        if row[10] == 0:
            continue
        impedance = complex(row[2], row[3])
        require(abs(impedance) > 0, "Online zero-impedance branch cannot be evaluated")
        series = 1 / impedance
        charging = 1j * row[4] / 2
        tap = (row[8] if row[8] != 0 else 1) * np.exp(1j * np.deg2rad(row[9]))
        ff = (series + charging) / abs(tap) ** 2
        ft = -series / np.conj(tap)
        tf = -series / tap
        tt = series + charging
        yf[k, f[k]], yf[k, t[k]] = ff, ft
        yt[k, f[k]], yt[k, t[k]] = tf, tt
        ybus[f[k], f[k]] += ff
        ybus[f[k], t[k]] += ft
        ybus[t[k], f[k]] += tf
        ybus[t[k], t[k]] += tt
    return ybus, yf, yt, f, t, index


def ac_quantities(case, vm, va, pg, qg, status, pd, qd):
    ybus, yf, yt, f, t, index = admittance(case)
    voltage = vm * np.exp(1j * np.deg2rad(va))
    injection = np.zeros_like(voltage, dtype=complex)
    for row, generator in enumerate(case["gen"]):
        injection[index[int(generator[0])]] += status[row] * (pg[row] + 1j * qg[row])
    nodal = case["baseMVA"] * voltage * np.conj(ybus @ voltage)
    mismatch = injection - pd - 1j * qd - nodal
    sf = case["baseMVA"] * voltage[f] * np.conj(yf @ voltage)
    st = case["baseMVA"] * voltage[t] * np.conj(yt @ voltage)
    shunt = ((case["bus"][:, 4] - 1j * case["bus"][:, 5])[:, None] * vm**2).sum(axis=0)
    loss_identity = nodal.sum(axis=0) - (sf + st).sum(axis=0) - shunt
    return mismatch, sf, st, loss_identity


def saved_peak_check(path, power_tolerance):
    case = literal_case(path)
    bus, gen = case["bus"], case["gen"]
    mismatch, _, _, loss_identity = ac_quantities(
        case, bus[:, 7:8], bus[:, 8:9], gen[:, 1:2], gen[:, 2:3],
        gen[:, 7:8], bus[:, 2:3], bus[:, 3:4],
    )
    residual = maximum(abs(mismatch))
    require(residual <= power_tolerance, "Independent Ybus does not reproduce the saved peak solution")
    require(maximum(abs(loss_identity)) < 1e-7, "Branch/nodal/shunt admittance identity failed")
    return {"case": path.name, "maximum_nodal_residual_mva": residual,
            "maximum_branch_shunt_identity_error_mva": maximum(abs(loss_identity)),
            "passed": True}


def aligned_csv(path, operating, count):
    header, rows = read_csv(path)
    require(len(rows) == count, f"Wrong row count: {path.name}")
    for field in TIME_FIELDS:
        require(np.array_equal([row[field] for row in rows], text(operating[field])),
                f"Timestamp alignment failed: {path.name}/{field}")
    return header, rows


def verify(output, load_path, case_path, power_tolerance=1e-3, voltage_tolerance=1e-6):
    case = literal_case(case_path)
    saved = loadmat(output / "s11_hourly_operating_profiles.mat", simplify_cells=True)
    operating = saved["operating"]
    loads = loadmat(load_path, simplify_cells=True)["profile"]
    bus, gen, branch = case["bus"], case["gen"], case["branch"]
    count = len(text(loads["timestamp_utc"]))
    require(count == 4416 and len(bus) == 49 and len(gen) == 49 and len(branch) == 83,
            "Expected the 49-bus / 49-row / 83-branch, 4416-hour S11 delivery")
    for field in ("bus", "gen", "branch"):
        require(np.array_equal(operating[f"base_{field}"], case[field]),
                f"Serialized base_{field} differs from the literal saved S11 case")
    require(np.array_equal(operating["bus_id"], bus[:, 0]), "Operating bus order differs from baseline")
    require(np.array_equal(loads["bus_id"], bus[:, 0]), "Load bus order differs from baseline")
    require(np.array_equal(operating["gen_bus_id"], gen[:, 0]), "Generator bus identity mismatch")
    for field in ("genfuel", "gentype"):
        require(np.array_equal(text(operating[field]), case[field]), f"Generator {field} mismatch")
    require(len(set(text(operating["gen_id"]))) == 49, "Generator IDs are not unique")
    ext = np.flatnonzero(case["genfuel"] == "external_schedule")
    require(np.array_equal(ext, np.arange(41, 49)), "Unexpected external row identities")
    require(np.array_equal(np.asarray(operating["external_gen_indices"]).reshape(-1) - 1, ext),
            "External indices mismatch")
    require(np.array_equal(np.asarray(operating["trusted_branch_indices"]).reshape(-1) - 1, TRUSTED_ROWS),
            "Trusted physical branch identities mismatch")
    for field in TIME_FIELDS:
        require(np.array_equal(text(loads[field]), text(operating[field])), f"Load time mismatch: {field}")
    require(len(set(text(operating["timestamp_utc"]))) == count, "Duplicate operating timestamps")
    valid_raw = np.asarray(operating["valid"]).reshape(-1)
    require(len(valid_raw) == count and np.isin(valid_raw, [0, 1]).all(), "Malformed validity flags")
    valid = valid_raw.astype(bool)
    qualified = np.asarray(operating["source_coverage_qualified"]).reshape(-1).astype(bool)
    imputed = np.asarray(operating["schedule_imputed"]).reshape(-1).astype(bool)
    require(qualified.shape == valid.shape and imputed.shape == valid.shape and np.logical_xor(qualified, imputed).all(),
            "Every schedule requires exactly one source-quality class")
    require(not bool(operating["dispatch_is_observed"]), "Modeled dispatch cannot be labeled observed")
    require(not bool(operating["chronological_ramps_enforced"]), "Snapshot profiles cannot imply chronological ramp validation")
    fields = tuple(ARRAY_CSV) + ("bus_vm_pu", "bus_va_deg", "bus_type")
    for field in fields:
        values = np.asarray(operating[field])
        require(values.shape == (49, count), f"Wrong shape: {field}")
        require(np.isfinite(values[:, valid]).all(), f"Valid-hour nonfinite values: {field}")
        require(np.isnan(values[:, ~valid]).all(), f"Invalid hours must not contain apparent operating results: {field}")
    for field in ("pd_mw", "qd_mvar"):
        require(np.asarray(loads[field]).shape == (49, count) and np.isfinite(loads[field]).all(),
                f"Load shape or values invalid: {field}")

    _, boundary = aligned_csv(output / "interchange_boundary_applied_mw.csv", operating, count)
    applied = np.array([[float(row[name]) for name in BOUNDARY_NAMES] for row in boundary]).T
    require(np.isfinite(applied).all(), "Applied boundary schedules incomplete")
    require(np.allclose(applied, operating["external_pg_mw"], rtol=0, atol=1e-9),
            "Stored interchange differs from applied source CSV")
    require(np.array_equal(boolean([row["all_primary_coverage_qualified"] for row in boundary]), qualified),
            "Interchange source qualification mismatch")
    require(np.array_equal(boolean([row["schedule_imputed"] for row in boundary]), imputed),
            "Interchange gap-completion flags mismatch")

    roundtrip = {}
    metadata_flags = {"generation_valid": valid, "interchange_source_qualified": qualified,
                      "interchange_gap_completed": imputed}
    for field, name in ARRAY_CSV.items():
        header, rows = aligned_csv(output / name, operating, count)
        expected_header = list(CSV_METADATA) + [f"gen_{k:03d}" for k in range(1, 50)]
        require(header == expected_header, f"Generator CSV column identity mismatch: {name}")
        for label, flags in metadata_flags.items():
            require(np.array_equal(boolean([row[label] for row in rows]), flags), f"CSV flags mismatch: {name}/{label}")
        values = np.array([[float(row[key]) if row[key] else np.nan for key in header[6:]] for row in rows]).T
        reference = np.asarray(operating[field])
        require(np.allclose(values, reference, rtol=1e-12, atol=1e-8, equal_nan=True), f"MAT/CSV round-trip failure: {name}")
        roundtrip[name] = maximum(abs(values[:, valid] - reference[:, valid]))

    _, ledger = aligned_csv(output / "hourly_validation.csv", operating, count)
    for label, flags in metadata_flags.items():
        require(np.array_equal(boolean([row[label] for row in ledger]), flags), f"Ledger flags mismatch: {label}")
    not_run = 0
    for hour, row in enumerate(ledger):
        if valid[hour]:
            require(row["status"] == "ac_verified" and bool(row["reason"].strip()), "Valid hour lacks explicit validation ledger")
        else:
            require(bool(row["status"].strip()) and row["status"] != "ac_verified", "Invalid hour lacks explicit status")
            require(bool(row["reason"].strip()) or row["status"] == "not_run", "Failed hour lacks a reason")
            not_run += row["status"] == "not_run"
    _, mapping = read_csv(output / "generator_mapping.csv")
    require(len(mapping) == 49, "Generator mapping row count mismatch")
    for k, row in enumerate(mapping):
        require(int(row["original_gen_row"]) == k + 1 and int(row["bus_id"]) == gen[k, 0]
                and row["gen_id"] == text(operating["gen_id"])[k]
                and row["genfuel"] == case["genfuel"][k] and row["gentype"] == case["gentype"][k],
                "Generator mapping identity mismatch")

    report = {"passed": True, "total_aligned_hours": count, "valid_hours_checked": int(valid.sum()),
              "invalid_hours": int((~valid).sum()), "not_run_hours": int(not_run),
              "complete_all_hours_ac_valid": bool(valid.all()),
              "power_tolerance_mva": power_tolerance, "voltage_tolerance_pu": voltage_tolerance,
              "network_matches_saved_case": True, "all_timestamps_aligned": True,
              "invalid_hour_ledger_explicit": True, "generator_csv_roundtrip_maximum_errors": roundtrip,
              "source_qualified_interchange_hours": int(qualified.sum()),
              "gap_completed_interchange_hours": int(imputed.sum()),
              "dispatch_is_observed": False, "chronological_ramps_checked": False,
              "saved_peak_admittance_check": saved_peak_check(
                  case_path.with_name("npcc_ny_lite_s11_dlr_pf_solution.m"), power_tolerance)}
    if not valid.any():
        report["physics_status"] = "no_valid_hours_to_check"
        return report

    pg, qg, status = (np.asarray(operating[key])[:, valid] for key in ("pg_mw", "qg_mvar", "gen_status"))
    vm, va, types = (np.asarray(operating[key])[:, valid] for key in ("bus_vm_pu", "bus_va_deg", "bus_type"))
    require(np.isin(status, [0, 1]).all(), "Non-binary generator status")
    require((status[ext] == 1).all(), "External schedule rows must remain online")
    on, off = status == 1, status == 0
    internal = np.ones(49, dtype=bool)
    internal[ext] = False
    pmin, pmax = np.repeat(gen[:, 9:10], valid.sum(), axis=1), np.repeat(gen[:, 8:9], valid.sum(), axis=1)
    pmin[ext], pmax[ext] = applied[:, valid], applied[:, valid]
    p_violation = max(0.0, maximum((pg - pmax)[on]), maximum((pmin - pg)[on]), maximum(abs(pg[off])))
    q_violation = max(0.0, maximum((qg - gen[:, 3:4])[on]), maximum((gen[:, 4:5] - qg)[on]), maximum(abs(qg[off])))
    voltage_violation = max(0.0, maximum(vm - bus[:, 11:12]), maximum(bus[:, 12:13] - vm))
    require(p_violation <= power_tolerance, "Online P capability or offline zero-P failure")
    require(q_violation <= power_tolerance, "Online Q capability or offline zero-Q failure")
    require(voltage_violation <= voltage_tolerance, "Bus voltage limit violation")
    require(np.isin(types, [1, 2, 3]).all() and (np.sum(types == 3, axis=0) == 1).all(), "Invalid bus control types")
    require((types[bus[:, 0] == 73] == 3).all(), "Operational reference is not bus 73")
    require((types[~np.isin(bus[:, 0], [37, 38, 39, 41, 73, 76, 81])] == 1).all(), "Unauthorized regulating bus")
    require((np.asarray(operating["vg_pu"])[:, valid] > 0).all(), "Nonpositive generator voltage targets")
    mismatch, sf, st, loss_identity = ac_quantities(
        case, vm, va, pg, qg, status, loads["pd_mw"][:, valid], loads["qd_mvar"][:, valid])
    ac_error = maximum(abs(mismatch))
    require(ac_error <= power_tolerance, f"Independent AC nodal mismatch exceeds tolerance: {ac_error}")
    require(maximum(abs(loss_identity)) < 1e-7, "Independent nodal/terminal/shunt identity failed")
    smax = np.maximum(abs(sf), abs(st))
    trusted_violation = max(0.0, maximum(smax[TRUSTED_ROWS] - branch[TRUSTED_ROWS, 5:6]))
    require(trusted_violation <= power_tolerance, "Trusted physical branch apparent-power limit violation")
    external_error = maximum(abs(pg[ext] - applied[:, valid]))
    require(external_error <= power_tolerance, "Delivered external injections do not match applied schedules")
    legacy = np.ones(len(branch), dtype=bool)
    legacy[TRUSTED_ROWS] = False
    legacy &= (branch[:, 10] == 1) & (branch[:, 5] > 0)
    expected_net = pg.sum(axis=0) - loads["pd_mw"][:, valid].sum(axis=0)
    ledger_net = np.array([float(row["network_loss_and_shunt_consumption_mw"]) for row in ledger])[valid]
    require(np.allclose(expected_net, ledger_net, rtol=0, atol=2e-3), "Ledger network power accounting differs from delivered dispatch")
    report.update(physics_status="independently_verified_on_valid_hours",
                  maximum_ac_nodal_mismatch_mva=ac_error,
                  maximum_p_capability_or_offline_violation_mw=p_violation,
                  maximum_q_capability_or_offline_violation_mvar=q_violation,
                  maximum_voltage_violation_pu=voltage_violation,
                  maximum_trusted_branch_violation_mva=trusted_violation,
                  maximum_external_schedule_error_mw=external_error,
                  maximum_branch_shunt_identity_error_mva=maximum(abs(loss_identity)),
                  minimum_bus_voltage_pu=float(vm.min()), maximum_bus_voltage_pu=float(vm.max()),
                  maximum_untrusted_branch_loading_ratio=maximum(smax[legacy] / branch[legacy, 5:6]),
                  untrusted_branch_limits_are_diagnostic=True,
                  hours_with_modeled_internal_shutdown=int(np.any(status[internal] == 0, axis=0).sum()))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--load-profile", type=Path,
                        default=ROOT / "output/s11_hourly_load_profiles/s11_hourly_load_profiles.mat")
    parser.add_argument("--case", type=Path, default=CASE)
    parser.add_argument("--power-tolerance", type=float, default=1e-3)
    parser.add_argument("--voltage-tolerance", type=float, default=1e-6)
    parser.add_argument("--peak-check-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.peak_check_only:
            result = saved_peak_check(args.case.with_name("npcc_ny_lite_s11_dlr_pf_solution.m"), args.power_tolerance)
        else:
            result = verify(args.output, args.load_profile, args.case, args.power_tolerance, args.voltage_tolerance)
        print(json.dumps(result, indent=2, allow_nan=False))
    except Exception as error:
        print(json.dumps({"passed": False, "error_type": type(error).__name__, "error": str(error)}, indent=2))
        raise SystemExit(1) from error
