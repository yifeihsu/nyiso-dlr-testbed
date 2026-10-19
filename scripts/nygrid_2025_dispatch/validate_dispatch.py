"""Independent validation of fixed-topology, P-bounded 2025 DC snapshots.

This module does not import the projection solver. It reconstructs capability
and input accounting, checks convex KKT conditions, assembles nodal equations,
and independently resolves voltage angles from the saved generation. Missing
hours remain part of the annual inventory. It adds no AC/UC/storage-SOC gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.linalg import lu_factor, lu_solve
from scipy.sparse import csr_matrix

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/nygrid_2025_dispatch"
INPUT = ROOT / "output/nygrid_2025_inputs/model/operating_inputs.mat"
TOL = 1e-7
KKT_TOL = 1e-6
PENALTIES = {"Combined Fossil": 1., "Nuclear": 100., "Hydro": 25., "Wind": 100., "Other Renewables": 100.}
NJ_NATIVE_KEYS = ({f"EIA860:2025:PLANT:56964:GEN:GT{i}" for i in range(1, 11)}
                  | {f"EIA860:2025:PLANT:50006:GEN:GTG{i}" for i in range(1, 6)}
                  | {f"EIA860:2025:PLANT:50006:GEN:STG{i}" for i in range(1, 4)})
NJ_QUARANTINE_KEYS = {"EIA860:2025:PLANT:50006:GEN:GTG6",
                      "EIA860:2025:PLANT:67086:GEN:P6132",
                      "EIA860:2025:PLANT:67087:GEN:P4256"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def flag(values):
    text = pd.Series(values).astype(str).str.lower()
    require(text.isin(["0", "1", "false", "true", "0.0", "1.0"]).all(), "Invalid boolean ledger value")
    return text.isin(["1", "true", "1.0"]).to_numpy()


class Audit:
    def __init__(self):
        self.checks = []

    def check(self, name, condition, detail=""):
        passed = bool(condition)
        self.checks.append(dict(check=name, passed=passed, max_error=None, detail=detail))
        require(passed, name + ": " + detail)

    def close(self, name, actual, expected, tol=TOL, allow_nan=False):
        a, e = np.asarray(actual, float), np.asarray(expected, float)
        require(a.shape == e.shape, f"{name}: shape mismatch {a.shape}/{e.shape}")
        mask = np.ones(e.shape, bool)
        if allow_nan:
            require(np.array_equal(np.isnan(a), np.isnan(e)), name + ": missingness differs")
            mask = ~np.isnan(e)
        require(np.isfinite(a[mask]).all() and np.isfinite(e[mask]).all(), name + ": nonfinite values")
        error = float(np.max(np.abs(a[mask] - e[mask]), initial=0))
        self.checks.append(dict(check=name, passed=error <= tol, max_error=error, detail=f"tolerance {tol:g}"))
        require(error <= tol, f"{name}: max error {error:g}")


def read_dispatch(folder):
    """Merge lossless split MAT artifacts while checking all shared identities."""
    merged = {}
    for name in ["dispatch.mat", "dispatch_bounds.mat", "dispatch_priors.mat", "dispatch_network.mat"]:
        path = folder / name
        require(path.is_file(), "Missing dispatch artifact " + str(path))
        part = loadmat(path, simplify_cells=True)
        for key, value in part.items():
            if key.startswith("__"):
                continue
            if key in merged:
                require(key in {"hour_index", "native_fleet_ids"} and np.array_equal(merged[key], value),
                        "Split-artifact identity mismatch or duplicated data: " + key)
            else:
                merged[key] = value
    return merged


def box_kkt(pg, prior, lower, upper, weights, target, saved_lambda=None, active_tol=1e-8):
    """Derive an independent KKT multiplier certificate, including all-bound cases.

    With L=J-lambda*(sum(P)-target), free gradients equal lambda, lower-bound
    gradients are at least lambda, and upper-bound gradients at most lambda.
    Fixed variables impose no restriction on the equality multiplier.
    """
    p, p0, lo, hi, w = [np.atleast_2d(np.asarray(x, float)) for x in [pg, prior, lower, upper, weights]]
    target = np.asarray(target, float).reshape(-1)
    require(p.shape == p0.shape == lo.shape == hi.shape == w.shape and len(p) == len(target), "KKT shape mismatch")
    require(all(np.isfinite(x).all() for x in [p, p0, lo, hi, w, target]), "Nonfinite KKT inputs")
    require((w > 0).all() and (hi >= lo).all(), "Invalid KKT weights/bounds")
    equality = np.abs(p.sum(axis=1) - target)
    bounds = np.maximum(np.max(lo - p, axis=1), np.max(p - hi, axis=1)).clip(min=0)
    fixed = hi - lo <= 1e-12
    at_lower = (p - lo <= active_tol) & ~fixed
    at_upper = (hi - p <= active_tol) & ~fixed
    free = ~fixed & ~at_lower & ~at_upper
    gradient = (p - p0) * w
    count = free.sum(axis=1)
    independent = np.divide(np.where(free, gradient, 0).sum(axis=1), count,
                            out=np.zeros(len(p)), where=count > 0)
    min_lambda = np.max(np.where(at_upper, gradient, -np.inf), axis=1)
    max_lambda = np.min(np.where(at_lower, gradient, np.inf), axis=1)
    nofree = count == 0
    both = nofree & np.isfinite(min_lambda) & np.isfinite(max_lambda)
    independent[both] = (min_lambda[both] + max_lambda[both]) / 2
    onlymin = nofree & np.isfinite(min_lambda) & ~np.isfinite(max_lambda)
    onlymax = nofree & ~np.isfinite(min_lambda) & np.isfinite(max_lambda)
    independent[onlymin] = min_lambda[onlymin]
    independent[onlymax] = max_lambda[onlymax]

    def certificate(lam):
        delta = gradient - lam[:, None]
        return np.maximum.reduce([
            np.max(np.where(free, np.abs(delta), 0), axis=1),
            np.max(np.where(at_lower, np.maximum(-delta, 0), 0), axis=1),
            np.max(np.where(at_upper, np.maximum(delta, 0), 0), axis=1)])

    result = dict(sum_error_mw=equality, bound_violation_mw=bounds,
                  independent_lambda=independent, kkt_gradient_residual=certificate(independent),
                  objective=.5 * np.sum(w * (p - p0) ** 2, axis=1), free_variables=count)
    if saved_lambda is not None:
        lam = np.asarray(saved_lambda, float).reshape(-1)
        require(lam.shape == independent.shape and np.isfinite(lam).all(), "Invalid saved multiplier")
        result["saved_dual_gradient_residual"] = certificate(lam)
    return result


def electrical_matrices(case):
    """Assemble nodal DC equations independently of replay_dc.network()."""
    bus, gen, branch, dc = [np.asarray(case[k], float) for k in ["bus", "gen", "branch", "dcline"]]
    dc = dc.reshape(-1, 17)
    nb, nl = len(bus), len(branch)
    ids = bus[:, 0].astype(int)
    require(len(set(ids)) == nb, "Duplicate bus IDs")
    lookup = {value: i for i, value in enumerate(ids)}
    f = np.array([lookup[int(v)] for v in branch[:, 0]])
    t = np.array([lookup[int(v)] for v in branch[:, 1]])
    tap = np.where(branch[:, 8] == 0, 1., branch[:, 8])
    on = branch[:, 10] > 0
    require((tap > 0).all() and np.all(branch[on, 3] != 0), "Invalid branch tap/reactance")
    coeff = np.zeros(nl)
    coeff[on] = float(case["baseMVA"]) / (branch[on, 3] * tap[on])
    B = np.zeros((nb, nb))
    for i in range(nl):
        B[f[i], f[i]] += coeff[i]
        B[t[i], t[i]] += coeff[i]
        B[f[i], t[i]] -= coeff[i]
        B[t[i], f[i]] -= coeff[i]
    C = np.zeros((nl, nb))
    C[np.arange(nl), f] = 1
    C[np.arange(nl), t] -= 1
    phase_flow = -coeff * np.deg2rad(branch[:, 9])
    phase_injection = C.T @ phase_flow
    G = csr_matrix((gen[:, 7], (np.arange(len(gen)), [lookup[int(v)] for v in gen[:, 0]])), shape=(len(gen), nb))
    D = np.zeros((len(dc), nb))
    require(np.all(dc[:, 15:17] == 0), "This frozen dispatch uses lossless DC links")
    for i, row in enumerate(dc):
        D[i, lookup[int(row[0])]] -= row[2]
        D[i, lookup[int(row[1])]] += row[2]
    return dict(bus=bus, gen=gen, branch=branch, dc=dc, ids=ids, lookup=lookup,
                from_index=f, to_index=t, B=B, C=C, G=G, D=D, coeff=coeff,
                phase_flow=phase_flow, phase_injection=phase_injection)


def electrical_audit(case, pd, pg, dc_pf, flows, angles_deg, references):
    e = electrical_matrices(case)
    pd, pg, dc_pf, flows, angles_deg = [np.asarray(x, float) for x in [pd, pg, dc_pf, flows, angles_deg]]
    require(all(np.isfinite(x).all() for x in [pd, pg, dc_pf, flows, angles_deg]), "Nonfinite solved state")
    specified = np.asarray(pg @ e["G"]) - pd - e["bus"][:, 4] + dc_pf @ e["D"]
    from_angles = np.deg2rad(angles_deg[:, e["from_index"]] - angles_deg[:, e["to_index"]]) * e["coeff"] + e["phase_flow"]
    residual = flows @ e["C"] - specified
    independent_angles = np.zeros_like(angles_deg)
    refs = np.asarray(references, int).reshape(-1)
    for ref in np.unique(refs):
        require(ref in e["lookup"], "Unknown reference bus")
        ix = np.flatnonzero(refs == ref)
        r = e["lookup"][ref]
        others = np.delete(np.arange(len(e["bus"])), r)
        rhs = (specified[ix] - e["phase_injection"])[:, others]
        solved = lu_solve(lu_factor(e["B"][np.ix_(others, others)]), rhs.T).T
        independent_angles[np.ix_(ix, others)] = solved
    independent_flow = (independent_angles[:, e["from_index"]] - independent_angles[:, e["to_index"]]) * e["coeff"] + e["phase_flow"]
    saved_relative = angles_deg.copy()
    saved_relative -= angles_deg[np.arange(len(refs)), [e["lookup"][r] for r in refs]][:, None]
    return dict(nodal_residual_mw=np.max(np.abs(residual), axis=1),
                global_balance_residual_mw=np.abs(specified.sum(axis=1)),
                branch_angle_identity_error_mw=np.max(np.abs(flows - from_angles), axis=1),
                independent_branch_error_mw=np.max(np.abs(independent_flow - flows), axis=1),
                independent_angle_error_deg=np.max(np.abs(np.rad2deg(independent_angles) - saved_relative), axis=1),
                matrices=e)


def verify_market_scope(audit, fleet, info):
    """Check unit market membership independently of a plant's state/BA label.

    The frozen 2025 scope includes 18 corroborated NJ units; a plant-level NYIS
    label alone does not admit Linden GTG6 or the two uncorroborated solar units.
    Full-inventory quarantine rows may have bus zero, but cannot enter dispatch.
    """
    outside = fleet.inventory_state.ne("NY").to_numpy()
    keys = fleet.device_key
    corroborated = keys.isin(NJ_NATIVE_KEYS).to_numpy()
    quarantined = keys.isin(NJ_QUARANTINE_KEYS).to_numpy()
    audit.check("outside_state_inventory_exact_frozen_cohort",
                int(outside.sum()) == 21 and set(keys[outside]) == NJ_NATIVE_KEYS | NJ_QUARANTINE_KEYS)
    audit.check("outside_state_inventory_is_NJ", fleet.loc[outside, "inventory_state"].eq("NJ").all())
    expected_scope = ~outside | corroborated
    audit.check("unit_market_scope_independent_reconstruction",
                np.array_equal(flag(fleet.unit_market_scope_eligible), expected_scope))
    bus_ids = fleet.bus_id.to_numpy(int)
    landed = (bus_ids >= 37) & (bus_ids <= 82)
    audit.check("landing_flag_matches_original_NY_bus_IDs", np.array_equal(flag(fleet.has_parent_landing), landed))
    audit.check("only_explicit_quarantine_has_no_landing", np.array_equal(~landed, quarantined)
                and np.all(bus_ids[quarantined] == 0))
    expected_zone = np.full(len(fleet), "", dtype=object)
    expected_zone[landed] = info.loc[bus_ids[landed], "zone"].to_numpy()
    audit.check("parent_landing_zone_identity", np.array_equal(fleet.parent_bus_zone, expected_zone))
    audit.check("quarantined_parent_names_empty", fleet.loc[quarantined, "parent_bus_name"].eq("").all())
    audit.check("zone_conflicts_explicit", np.array_equal(flag(fleet.source_zone_parent_bus_zone_conflict),
                landed & (fleet.zone.to_numpy() != expected_zone)))
    audit.check("corroborated_NJ_units_land_on_existing_ZoneJ_proxy",
                np.all(bus_ids[corroborated] == 82) and fleet.loc[corroborated, "zone"].eq("J").all()
                and fleet.loc[corroborated, "mapping_method"].eq("same_zone_nearest_parent_bus_geographic_proxy").all())
    audit.check("corroborated_NJ_units_have_primary_scope_evidence",
                flag(fleet.loc[corroborated, "market_scope_primary_corroborated"]).all()
                and all({"NYISO:GoldBook:2025", "NYISO:P19:20261010"}.issubset(set(value.split("|")))
                        for value in fleet.loc[corroborated, "native_market_scope_evidence"]))
    linden = fleet.plant_id.eq(50006).to_numpy()
    audit.check("Linden_unit_market_split_has_owner_evidence",
                fleet.loc[linden, "native_market_scope_evidence"].str.contains("EGCO:Linden:20251216", regex=False).all())
    audit.check("NJ_P63_membership_is_disclosed_inference",
                np.array_equal(flag(fleet.loc[outside, "native_p63_scope_inferred"]), corroborated[outside])
                and not flag(fleet.loc[outside, "native_p63_unit_output_observed"]).any())
    audit.check("Linden_GTG6_is_explicit_PJM_record",
                fleet.loc[keys.eq("EIA860:2025:PLANT:50006:GEN:GTG6"), "zone"].eq("PJM").all())
    audit.check("uncorroborated_NJ_solar_zone_is_unverified",
                fleet.loc[fleet.plant_id.isin([67086, 67087]), "zone"].eq("UNVERIFIED").all())
    return expected_scope


def verify_fleet(audit, folder, fleet, bounds, timestamps):
    n = len(fleet)
    audit.check("complete_fleet_keys_unique", fleet.device_key.is_unique and not fleet.duplicated(["plant_id", "eia_generator_id"]).any())
    audit.check("contiguous_fleet_IDs", np.array_equal(fleet.fleet_id.to_numpy(int), np.arange(1, n + 1)))
    audit.close("fleet_bound_hour_axis", bounds["hour_index"], np.arange(1, 8761), tol=0)
    audit.close("fleet_bound_unit_axis", bounds["fleet_id"], fleet.fleet_id.to_numpy(int), tol=0)
    expected_keys = [f"EIA860:2025:PLANT:{int(r.plant_id)}:GEN:{r.eia_generator_id}" for r in fleet.itertuples()]
    audit.check("EIA_identity_key_format", np.array_equal(fleet.device_key.to_numpy(), expected_keys))
    audit.check("EIA_capacity_not_duplicated_by_aliases", not flag(fleet.capacity_duplicated_by_associations).any())
    info = pd.read_csv(folder / "source_parent/npcc.csv", keep_default_na=False).set_index("idx")
    unit_market_scope = verify_market_scope(audit, fleet, info)
    receipts = json.loads((folder / "source_scope/source_receipts.json").read_text())
    audit.check("primary_market_scope_sources_present", {row["source_id"] for row in receipts} == {
        "NYISO:P19:20261010", "EGCO:Linden:20251216", "NYISO:VFT:FERC:20120524", "NYISO:GoldBook:2025"})
    for receipt in receipts:
        path = ROOT / receipt["path"]
        audit.check("market_scope_source_fingerprint:" + receipt["source_id"],
                    path.is_file() and sha(path) == receipt["sha256"] and path.stat().st_size == receipt["bytes"])
    local = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True)).tz_convert("America/New_York")
    months = local.month.to_numpy()
    physical = bounds["physical_pmax_actual_mw"]
    default_max = bounds["pmax_actual_mw"]
    audit.check("finite_nonnegative_fleet_capabilities", np.isfinite(physical).all() and (physical >= 0).all())
    active_any = np.zeros(n, bool)
    for month in range(1, 13):
        expected = np.zeros(n)
        for j, row in enumerate(fleet.itertuples()):
            start = (int(row.operating_year), int(row.operating_month))
            active = row.source_status in {"OP", "SB", "RE"} and start[0] > 0 and 1 <= start[1] <= 12 and start < (2025, month)
            if row.source_status == "RE":
                end = (int(row.retirement_year), int(row.retirement_month))
                active = active and end[0] > 0 and 1 <= end[1] <= 12 and (2025, month) < end
            if active:
                active_any[j] = True
                season = "winter_capacity_mw" if month in {11, 12, 1, 2, 3} else "summer_capacity_mw"
                expected[j] = float(getattr(row, season))
                # Explicit, source-audited missing-seasonal-capacity exception.
                if int(row.plant_id) == 2490 and row.eia_generator_id == "GT1" and expected[j] == 0:
                    require("nameplate" in row.capability_policy.lower(), "Arthur Kill capability proxy is not disclosed")
                    expected[j] = float(row.nameplate_capacity_mw)
        take = np.flatnonzero(months == month)
        audit.close(f"fleet_season_status_bounds_month_{month}", physical[take], np.broadcast_to(expected, (len(take), n)), tol=1e-10)
    expected_scope = (fleet.sector.isin(["Electric Utility", "IPP Non-CHP", "IPP CHP"]).to_numpy()
                      & fleet.synchronized_to_transmission_grid.ne("N").to_numpy()
                      & fleet.balancing_authority_code.eq("NYIS").to_numpy()
                      & fleet.plant_id.ne(52168).to_numpy() & unit_market_scope)
    audit.check("fleet_grid_scope_independent_reconstruction", np.array_equal(flag(fleet.grid_scope_eligible), expected_scope))
    audit.check("fleet_active_month_policy", np.array_equal(flag(fleet.has_active_2025_month), active_any))
    allowed_fuel = fleet.fuel_category.isin(PENALTIES).to_numpy()
    expected_default = expected_scope & active_any & allowed_fuel & ~flag(fleet.is_storage)
    expected_ps = expected_scope & active_any & allowed_fuel & flag(fleet.is_pumped_hydro)
    eligible = flag(fleet.dispatch_eligible_default)
    audit.check("fleet_default_eligibility_independent_reconstruction", np.array_equal(eligible, expected_default))
    audit.check("fleet_PS_eligibility_independent_reconstruction", np.array_equal(flag(fleet.pumped_hydro_prior_eligible), expected_ps))
    audit.close("fleet_default_bounds_respect_scope", default_max, physical * eligible, tol=0)
    audit.close("continuous_native_minimum_zero", bounds["pmin_actual_mw"], np.zeros_like(default_max), tol=0)
    battery = flag(fleet.is_storage) & ~flag(fleet.is_pumped_hydro)
    audit.check("batteries_excluded_from_default_dispatch", np.all(default_max[:, battery] == 0))
    retired_ip = ((fleet.plant_id == 2497) & (fleet.eia_generator_id == "2")) | ((fleet.plant_id == 8907) & (fleet.eia_generator_id == "3"))
    audit.check("two_Indian_Point_tombstones_zero", int(retired_ip.sum()) == 2 and np.all(physical[:, retired_ip.to_numpy()] == 0))
    return physical


def validate(source_root=OUT, dispatch_dir=None, output_dir=None):
    source_root = Path(source_root).resolve()
    folder = Path(dispatch_dir).resolve() if dispatch_dir else source_root / "dispatch"
    output = Path(output_dir).resolve() if output_dir else source_root / "validation"
    a = Audit()
    d = read_dispatch(folder)
    inputs = loadmat(INPUT, simplify_cells=True)
    parent = inputs["base_case"]
    case = d["base_case"]
    contract = json.loads((folder / "contract.json").read_text())
    summary = json.loads((folder / "summary.json").read_text())
    register = pd.read_csv(folder / "model_generator_register.csv", keep_default_na=False,
                           dtype={"eia_generator_id": str, "device_key": str})
    fleet = pd.read_csv(source_root / "fleet/fleet_register.csv", keep_default_na=False, dtype={"eia_generator_id": str})
    bounds = np.load(source_root / "fleet/fleet_bounds.npz", allow_pickle=False)
    priors = np.load(source_root / "priors/dispatch_priors.npz", allow_pickle=False)
    hours = np.arange(1, 8761)
    axis = pd.date_range("2025-01-01 05:00Z", periods=8760, freq="h")
    a.close("8760_hour_axis", d["hour_index"], hours, tol=0)
    a.check("UTC_physical_year_axis", pd.DatetimeIndex(pd.to_datetime(np.asarray(d["timestamp_utc"]).astype(str), utc=True)).equals(axis))
    a.check("input_hour_identity", np.array_equal(np.asarray(d["timestamp_utc"]).astype(str), np.asarray(inputs["timestamp_utc"]).astype(str)))
    a.close("original_bus_IDs", case["bus"][:, 0], parent["bus"][:, 0], tol=0)
    a.close("unchanged_branch_rows", case["branch"], parent["branch"], tol=0)
    a.close("unchanged_bus_voltage_and_shunts", case["bus"][:, [0, 4, 5, 9]], parent["bus"][:, [0, 4, 5, 9]], tol=0)
    a.close("unchanged_DC_topology_and_loss_model", case["dcline"][:, [0, 1, 2, 15, 16]], parent["dcline"][:, [0, 1, 2, 15, 16]], tol=0)
    a.close("lossless_DC_PT_equals_PF", case["dcline"][:, 4], case["dcline"][:, 3], tol=0)
    a.close("gross_PD_preserved_without_second_renewable_netting", d["bus_pd"], inputs["bus_gross_pd"], tol=0)
    a.close("declared_QD_preserved", d["bus_qd"], inputs["bus_gross_qd"], tol=0)
    a.close("fixed_DC_schedules", d["dc_pf"], inputs["dcline_pf"], tol=0, allow_nan=True)
    a.close("reference_MVA_base", case["baseMVA"], parent["baseMVA"], tol=0)
    a.close("inherited_operator_membership", case["if"]["map"], parent["if"]["map"], tol=0)
    for key in ["topology_changed", "internal_interface_observations_read", "interface_calibration_performed",
                "reference_is_free_balancing_generator", "load_shedding_allowed", "bounds_relaxed",
                "ac_feasibility_validated", "reactive_capabilities_available", "physical_branch_thermal_feasibility_validated",
                "unit_commitment_validated", "ramping_validated", "reserve_feasibility_validated",
                "storage_energy_feasibility_validated", "battery_dispatch_enabled"]:
        a.check("claim_scope:" + key, contract[key] is False)
    physical = verify_fleet(a, source_root / "fleet", fleet, bounds, d["timestamp_utc"])
    a.close("prior_hour_axis", priors["hour_index"], hours, tol=0)
    a.close("prior_fleet_axis", priors["fleet_id"], fleet.fleet_id.to_numpy(int), tol=0)
    a.check("prior_timestamp_axis", np.array_equal(priors["timestamp_utc"].astype(str), np.asarray(d["timestamp_utc"]).astype(str)))
    admitted = np.any(np.isfinite(priors["available_pmax_actual_mw"]) & (priors["available_pmax_actual_mw"] > 0), axis=0)
    native = fleet.loc[admitted].reset_index(drop=True)
    nn, ng = len(native), len(register)
    authority = native.balancing_authority_code.astype(str).str.strip().str.upper()
    outside_market = authority != "NYIS"
    exceptions = np.zeros(nn, bool)
    if "native_scope_exception_approved" in native and "native_scope_exception_evidence" in native:
        exceptions = flag(native.native_scope_exception_approved) & native.native_scope_exception_evidence.astype(str).str.strip().ne("").to_numpy()
    a.check("admitted_native_balancing_authority_scope", np.all(~outside_market.to_numpy() | exceptions),
            "Explicit other or unknown balancing authorities require a recorded, evidenced exception")
    a.check("admitted_native_unit_market_scope", flag(native.unit_market_scope_eligible).all())
    a.check("all_admitted_native_landings_valid", flag(native.has_parent_landing).all()
            and native.bus_id.astype(int).between(37, 82).all())
    a.check("all_18_corroborated_NJ_units_admitted", set(native.loc[native.inventory_state.ne("NY"), "device_key"]) == NJ_NATIVE_KEYS)
    a.check("quarantined_NJ_units_never_admitted", NJ_QUARANTINE_KEYS.isdisjoint(set(native.device_key)))
    quarantine = fleet.device_key.isin(NJ_QUARANTINE_KEYS).to_numpy()
    expected_quarantine_bounds = np.zeros((8760, int(quarantine.sum())))
    expected_quarantine_bounds[~np.isfinite(inputs["statewide_generation_public_mw"]).all(axis=1)] = np.nan
    for key in ["available_pmin_actual_mw", "available_pmax_actual_mw"]:
        a.close("quarantine_prior_bound_zero:" + key, priors[key][:, quarantine], expected_quarantine_bounds, tol=0, allow_nan=True)
    a.check("native_selection_exactly_ever_admitted_units", np.array_equal(d["native_fleet_ids"], native.fleet_id.to_numpy(int)))
    a.check("model_generator_count", ng == nn + 28 and np.shape(d["gen_pg"]) == (8760, ng))
    a.close("contiguous_generator_rows", register.gen_row, np.arange(1, ng + 1), tol=0)
    a.check("generator_keys_unique", register.device_key.is_unique)
    a.check("generator_roles_partition", (register.iloc[:nn].role == "native").all() and (register.iloc[nn:].role == "fixed_external").all())
    a.check("native_keys_preserved", np.array_equal(register.iloc[:nn].device_key, native.device_key))
    a.close("native_landing_ids", register.iloc[:nn].bus_id.astype(int), native.bus_id.astype(int), tol=0)
    a.close("case_generator_landing_identity", case["gen"][:, 0], register.bus_id.astype(int), tol=0)
    a.check("native_source_zone_ledger", np.array_equal(register.iloc[:nn].zone, native.zone))
    a.check("native_fuel_ledger", np.array_equal(register.iloc[:nn].fuel_category, native.fuel_category))
    gamma = float(inputs["gamma"])
    a.close("single_frozen_gamma", d["gamma"], gamma, tol=0)
    a.close("scaled_native_physical_capability", d["native_physical_pmax"], physical[:, admitted] * gamma, tol=0)
    a.close("scaled_native_admitted_upper_bounds", d["gen_pmax"][:, :nn], priors["available_pmax_actual_mw"][:, admitted] * gamma, tol=0, allow_nan=True)
    a.close("scaled_native_lower_bounds", d["gen_pmin"][:, :nn], priors["available_pmin_actual_mw"][:, admitted] * gamma, tol=0, allow_nan=True)
    a.close("source_native_priors_not_interface_fit", d["prior_pg"][:, :nn], priors["prior_actual_mw"][:, admitted] * gamma, tol=0, allow_nan=True)
    penalties = np.array([PENALTIES[value] for value in native.fuel_category])
    ps = flag(native.is_pumped_hydro)
    penalties[ps] = 100
    expected_weights = penalties / np.where(d["native_physical_pmax"] > 0, d["native_physical_pmax"], 1.)
    a.close("declared_capacity_weighted_objective", d["objective_weights"], expected_weights, tol=0)
    a.close("penalty_register", register.iloc[:nn].penalty.astype(float), penalties, tol=0)
    parent_ext = np.flatnonzero(np.asarray(parent["genfuel"]).astype(str) == "Import")
    a.close("external_parent_identity", register.iloc[nn:].parent_gen_row.astype(int), parent_ext + 1, tol=0)
    fixed = inputs["external_input_pg"][:, parent_ext]
    for key in ["gen_pmin", "gen_pmax", "prior_pg"]:
        a.close("fixed_external:" + key, d[key][:, nn:], fixed, tol=0, allow_nan=True)
    generation_ok = np.isfinite(inputs["statewide_generation_public_mw"]).all(axis=1)
    source_ok = generation_ok & np.asarray(inputs["boundary_hour_qualified"]).reshape(-1).astype(bool)
    a.check("prior_generation_coverage_from_frozen_P63", np.array_equal(priors["generation_hour_qualified"].astype(bool), generation_ok))
    a.check("prior_joint_coverage_from_frozen_P32_P63", np.array_equal(priors["source_hour_qualified"].astype(bool), source_ok))
    state_names = np.asarray(inputs["statewide_generation_fuel_names"]).astype(str).tolist()
    state_values = np.asarray(inputs["statewide_generation_public_mw"])
    for fuel in PENALTIES:
        members = ["Dual Fuel", "Natural Gas", "Other Fossil Fuels"] if fuel == "Combined Fossil" else [fuel]
        expected_fuel = state_values[:, [state_names.index(value) for value in members]].sum(axis=1)
        prior_fuel = priors["prior_actual_mw"][:, fleet.fuel_category.eq(fuel).to_numpy()].sum(axis=1)
        a.close("complete_inventory_source_fuel_conservation:" + fuel, prior_fuel[generation_ok], expected_fuel[generation_ok], tol=1e-6)
    valid = np.asarray(d["dispatch_qualified"]).reshape(-1).astype(bool)
    status = np.asarray(d["status_code"]).reshape(-1)
    a.check("source_qualification_independent_rebuild", np.array_equal(np.asarray(d["source_qualified"]).reshape(-1).astype(bool), source_ok))
    a.check("all_hours_have_a_known_status", status.shape == (8760,) and np.isin(status, [0, 1, 2]).all())
    a.check("missing_source_status_exact", np.array_equal(status == 0, ~source_ok))
    a.check("dispatch_status_exact", np.array_equal(status == 1, valid))
    for key in ["gen_pg", "branch_pf", "bus_va"]:
        a.check("unsolved_state_is_missing:" + key, np.isnan(d[key][~valid]).all())
        a.check("qualified_state_is_finite:" + key, np.isfinite(d[key][valid]).all())
    target = inputs["zonal_load_model_mw"].sum(axis=1) - inputs["boundary_model_mw"].sum(axis=1)
    a.close("native_required_balance", d["native_required_pg"], target, allow_nan=True)
    lower = d["gen_pmin"][:, :nn]
    upper = d["gen_pmax"][:, :nn]
    feasible = source_ok & (target >= lower.sum(axis=1) - TOL) & (target <= upper.sum(axis=1) + TOL)
    a.check("capacity_infeasibility_is_explicit", np.array_equal(status == 2, source_ok & ~feasible))
    a.check("all_box_feasible_hours_solved", np.array_equal(valid, feasible))
    ix = np.flatnonzero(valid)
    require(len(ix) > 0, "No bounded DC cases were produced")
    a.close("fixed_external_dispatch_exact", d["gen_pg"][valid, nn:], fixed[valid], tol=0)
    a.check("finite_positive_objective_weights", np.isfinite(d["objective_weights"][valid]).all() and (d["objective_weights"][valid] > 0).all())
    a.check("native_bounds_nonnegative_ordered", (lower[valid] >= 0).all() and (upper[valid] >= lower[valid]).all())
    a.close("declared_continuous_native_minimum_zero", lower[valid], np.zeros_like(lower[valid]), tol=0)
    a.check("admitted_capability_not_above_physical", np.max(upper[valid] - d["native_physical_pmax"][valid]) <= TOL)
    a.check("pumped_storage_no_extra_balancing_generation", np.max(upper[valid][:, ps] - d["prior_pg"][valid, :nn][:, ps], initial=0) <= TOL)
    variable = flag(native.is_variable_renewable)
    a.check("wind_solar_below_allocated_availability", np.max(upper[valid][:, variable] - d["prior_pg"][valid, :nn][:, variable], initial=0) <= TOL)
    prior_native = d["prior_pg"][:, :nn]
    for label, mask in [("wind_solar", variable), ("pumped_hydro", ps)]:
        expected_cap = np.minimum(d["native_physical_pmax"][valid][:, mask], np.maximum(prior_native[valid][:, mask], 0))
        a.close("exact_source_availability_ceiling:" + label, upper[valid][:, mask], expected_cap)
    nuclear = native.fuel_category.eq("Nuclear").to_numpy()
    conventional = ~variable & ~ps & ~nuclear
    a.close("conventional_resource_physical_ceiling", upper[valid][:, conventional], d["native_physical_pmax"][valid][:, conventional])
    reactor_path = ROOT / "output/nygrid_2025_inputs/generation_source/nuclear_plant_hourly_priors.csv.gz"
    reactors = pd.read_csv(reactor_path, dtype={"generator_id": str})
    a.check("reactor_availability_keys_unique", not reactors.duplicated(["hour_index", "plant_id", "generator_id"]).any())
    for col in np.flatnonzero(nuclear):
        row = native.iloc[col]
        source_reactor = reactors.loc[(reactors.plant_id == int(row.plant_id)) & (reactors.generator_id == row.eia_generator_id)].set_index("hour_index").reindex(hours)
        require(source_reactor.availability_weight_mw.notna().all(), "Missing independent daily reactor availability")
        expected_cap = np.minimum(d["native_physical_pmax"][:, col], source_reactor.availability_weight_mw.to_numpy(float) * gamma)
        a.close("NRC_availability_ceiling:" + row.device_key, upper[valid, col], expected_cap[valid])
    kkt_parts = []
    for start in range(0, len(ix), 256):
        take = ix[start:start + 256]
        kkt_parts.append(box_kkt(d["gen_pg"][take, :nn], d["prior_pg"][take, :nn], lower[take], upper[take],
                                 d["objective_weights"][take], target[take], d["dual_lambda"][take]))
    kkt = {key: np.concatenate([part[key] for part in kkt_parts]) for key in kkt_parts[0]}
    for name in ["sum_error_mw", "bound_violation_mw"]:
        a.close("KKT_primal:" + name, kkt[name], np.zeros(len(ix)))
    for name in ["kkt_gradient_residual", "saved_dual_gradient_residual"]:
        a.close("KKT_stationarity:" + name, kkt[name], np.zeros(len(ix)), tol=KKT_TOL)
    a.close("objective_recalculation", d["objective_value"][valid], kkt["objective"], tol=1e-5)
    refs = np.asarray(d["reference_bus"], int).reshape(-1)
    retired_keys = {"EIA860:2025:PLANT:2497:GEN:2", "EIA860:2025:PLANT:8907:GEN:3"}
    a.check("retired_IP_units_not_admitted", retired_keys.isdisjoint(set(native.device_key)))
    a.check("reference_zero_on_unsolved_hours", np.all(refs[~valid] == 0))
    native_bus_ids = register.iloc[:nn].bus_id.to_numpy(int)
    for h in ix:
        eligible_ref = (native_bus_ids == refs[h]) & (upper[h] > 0)
        require(eligible_ref.any(), "Reference bus has no admitted native generator")
        expected_ref = 50 if np.any((native_bus_ids == 50) & (upper[h] > 0)) else native_bus_ids[np.argmax(d["gen_pg"][h, :nn])]
        require(refs[h] == expected_ref, "Reference-bus policy changed")
    a.check("reference_has_admitted_native_generator", True)
    electrical = electrical_audit(case, d["bus_pd"][valid], d["gen_pg"][valid], d["dc_pf"][valid],
                                  d["branch_pf"][valid], d["bus_va"][valid], refs[valid])
    for key, values in electrical.items():
        if key == "matrices":
            continue
        a.close("independent_DC:" + key, values, np.zeros(len(ix)))
    e = electrical["matrices"]
    meta = pd.read_csv(source_root / "fleet/source_parent/npcc.csv", keep_default_na=False).set_index("idx")
    areas = meta.loc[e["ids"], "area"].to_numpy()
    region_residuals = {}
    for j, (name, numbers) in enumerate([("ISONE", [1]), ("ONTARIO", [4]), ("PJM", [5, 6])]):
        mask = np.isin(areas, numbers)
        ac_out = d["branch_pf"][valid] @ (e["C"] @ mask.astype(float))
        dc_out = -(d["dc_pf"][valid] @ e["D"][:, mask].sum(axis=1))
        expected = inputs["regional_import_model_mw"][valid, j]
        delta = ac_out + dc_out - expected
        a.close("regional_scheduled_export:" + name, delta, np.zeros(len(ix)))
        region_residuals[name] = float(np.abs(delta).max())
    a.close("recorded_slack_movement", d["dc_slack_change_mw"][valid], np.zeros(len(ix)))
    a.close("recorded_nodal_residual", d["nodal_residual_mw"][valid], np.zeros(len(ix)))
    for key, expected in [("hours", 8760), ("source_qualified_hours", int(source_ok.sum())), ("dispatched_hours", int(valid.sum())),
                          ("missing_source_hours", int((status == 0).sum())), ("capacity_infeasible_hours", int((status == 2).sum())),
                          ("native_generators", nn), ("fixed_external_generators", 28), ("generators", ng)]:
        a.check("summary:" + key, summary[key] == expected)
    status_csv = pd.read_csv(folder / "hour_status.csv")
    a.close("status_CSV_hour_axis", status_csv.hour_index, hours, tol=0)
    a.close("status_CSV_codes", status_csv.status_code, status, tol=0)
    a.check("status_CSV_qualification", np.array_equal(flag(status_csv.dispatch_qualified), valid))
    expected_artifacts = {"dispatch.mat", "dispatch_bounds.mat", "dispatch_priors.mat", "dispatch_network.mat"}
    a.check("all_state_artifacts_fingerprinted", set(summary["file_sha256"]) == expected_artifacts)
    for filename, digest in summary["file_sha256"].items():
        a.check("state_artifact_fingerprint:" + filename, sha(folder / filename) == digest)
    for receipt in contract["provenance"]:
        path = ROOT / receipt["path"]
        a.check("provenance:" + receipt["path"], path.is_file() and sha(path) == receipt["sha256"])
    hourly = pd.DataFrame(dict(hour_index=hours[ix], timestamp_utc=np.asarray(d["timestamp_utc"])[valid],
        maximum_generator_bound_violation_mw=kkt["bound_violation_mw"], native_balance_error_mw=kkt["sum_error_mw"],
        independent_KKT_gradient_residual=kkt["kkt_gradient_residual"], independent_KKT_lambda=kkt["independent_lambda"],
        nodal_residual_mw=electrical["nodal_residual_mw"], independent_branch_error_mw=electrical["independent_branch_error_mw"],
        independent_angle_error_deg=electrical["independent_angle_error_deg"]))
    result = dict(passed=True, scope="source-consistent capacity-bounded DC snapshots; no AC, commitment, ramp or storage-energy qualification",
        annual_hours=8760, source_qualified_hours=int(source_ok.sum()), qualified_dispatch_hours=int(valid.sum()),
        missing_source_hours=int((status == 0).sum()), capacity_infeasible_hours=int((status == 2).sum()),
        fleet_inventory_rows=len(fleet), native_generators=nn, fixed_external_generators=28,
        maximum_bound_violation_mw=float(kkt["bound_violation_mw"].max()),
        maximum_independent_KKT_gradient_residual=float(kkt["kkt_gradient_residual"].max()),
        maximum_nodal_residual_mw=float(electrical["nodal_residual_mw"].max()),
        maximum_independent_branch_error_mw=float(electrical["independent_branch_error_mw"].max()),
        maximum_independent_angle_error_deg=float(electrical["independent_angle_error_deg"].max()),
        regional_schedule_max_residual_mw=region_residuals, preserved_zone_landing_conflict_rows=int(flag(native.source_zone_parent_bus_zone_conflict).sum()),
        admitted_native_unknown_balancing_authority_rows=int(authority.eq("").sum()),
        admitted_native_other_balancing_authority_rows=int((authority.ne("") & authority.ne("NYIS")).sum()),
        admitted_native_outside_NY_state_rows=int(native.inventory_state.ne("NY").sum()),
        quarantined_outside_NY_inventory_rows=int(quarantine.sum()),
        scope_membership_basis="NYISO unit market membership; includes 18 corroborated NJ units and excludes Linden GTG6/PJM plus two uncorroborated NJ solar records",
        check_count=len(a.checks), checks=a.checks)
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(a.checks).to_csv(output / "validation_checks.csv", index=False, lineterminator="\n")
    hourly.to_csv(output / "independent_hourly_checks.csv", index=False, lineterminator="\n")
    receipts = [folder / name for name in ["dispatch.mat", "dispatch_bounds.mat", "dispatch_priors.mat", "dispatch_network.mat", "contract.json", "summary.json", "model_generator_register.csv", "hour_status.csv"]]
    receipts += [INPUT, source_root / "fleet/fleet_register.csv", source_root / "fleet/fleet_bounds.npz",
                 source_root / "fleet/source_parent/npcc.csv", source_root / "fleet/source_scope/source_receipts.json",
                 source_root / "fleet/outside_NY_scope_register.csv", source_root / "priors/dispatch_priors.npz", reactor_path, Path(__file__)]
    result["files"] = [dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in receipts]
    (output / "validation_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: value for key, value in result.items() if key not in {"checks", "files"}}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=OUT)
    parser.add_argument("--dispatch-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    validate(args.source_root, args.dispatch_dir, args.output_dir)
