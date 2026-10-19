"""Independently validate the 2025 scaled-input package, without power flow.

Checks source/model units, the raw NYgrid NPCC load anchor, zonal allocation,
external regional accounting, generation-prior conservation, UTC/DST identity,
and explicit incompleteness. It never fills missing data, fits observations,
or treats the frozen 2019 base case as a balanced 2025 operating point.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "output/nygrid_2025_inputs"
UPSTREAM = ROOT / "tmp/nygrid_2019_reproduction/upstream/Data"
ZONES = list("ABCDEFGHIJK")
CHANNELS = ["SCH - HQ - NY", "SCH - HQ_CEDARS", "SCH - OH - NY",
            "SCH - NE - NY", "SCH - NPX_1385", "SCH - NPX_CSC",
            "SCH - PJ - NY", "SCH - PJM_HTP", "SCH - PJM_NEPTUNE", "SCH - PJM_VFT"]
REGIONS = {"ISONE": ["SCH - NE - NY", "SCH - NPX_1385", "SCH - NPX_CSC"],
           "ONTARIO": ["SCH - OH - NY"],
           "PJM": ["SCH - PJ - NY", "SCH - PJM_HTP", "SCH - PJM_NEPTUNE", "SCH - PJM_VFT"],
           "HQ": ["SCH - HQ - NY", "SCH - HQ_CEDARS"]}
FUEL_CATEGORIES = ["Dual Fuel", "Natural Gas", "Other Fossil Fuels", "Nuclear", "Hydro", "Wind", "Other Renewables"]
PRIOR_CATEGORIES = ["Combined Fossil", "Nuclear", "Hydro", "Wind", "Other Renewables"]
TOL = 1e-6


def require(condition, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def boolean(series) -> np.ndarray:
    values = pd.Series(series).astype(str).str.lower()
    require(values.isin(["true", "false", "1", "0", "1.0", "0.0"]).all(), "Unrecognized or missing qualification boolean")
    return values.isin(["true", "1", "1.0"]).to_numpy()


def find_csv(folder: Path, stem: str) -> Path:
    candidates = [p for p in [folder / f"{stem}.csv", folder / f"{stem}.csv.gz"] if p.is_file()]
    require(len(candidates) == 1, f"Expected exactly one plain/compressed CSV for {folder / stem}")
    return candidates[0]


class Audit:
    def __init__(self):
        self.checks = []
        self.files = {}

    def record_file(self, path: Path, role: str):
        key = str(path.resolve().relative_to(ROOT))
        self.files[key] = {"path": key.replace("\\", "/"), "sha256": sha(path), "role": role}

    def check(self, name: str, condition, detail: str = ""):
        passed = bool(condition)
        self.checks.append(dict(check=name, passed=passed, maximum_absolute_error=None, detail=detail))
        require(passed, f"{name}: {detail}")

    def close(self, name: str, actual, expected, tol=TOL, allow_nan=False):
        a, e = np.asarray(actual, float), np.asarray(expected, float)
        require(a.shape == e.shape, f"{name}: shape mismatch {a.shape} != {e.shape}")
        if allow_nan:
            require(np.array_equal(np.isnan(a), np.isnan(e)), f"{name}: missing-data mask changed")
            finite = ~np.isnan(e)
        else:
            finite = np.ones(e.shape, bool)
        require(np.isfinite(a[finite]).all() and np.isfinite(e[finite]).all(), f"{name}: invalid finite values")
        error = float(np.max(np.abs(a[finite] - e[finite]), initial=0))
        self.checks.append(dict(check=name, passed=error <= tol, maximum_absolute_error=error, detail=f"tolerance {tol:g}"))
        require(error <= tol, f"{name}: {error:g} exceeds {tol:g}")


def check_time_keys(audit: Audit, frame: pd.DataFrame, axis: pd.DatetimeIndex, name: str):
    require("timestamp_utc" in frame, f"{name} lacks canonical UTC key")
    stamps = pd.DatetimeIndex(pd.to_datetime(frame.timestamp_utc, utc=True))
    if "hour_index" in frame:
        raw = frame.hour_index.to_numpy(float)
        require(np.isfinite(raw).all() and np.equal(raw, np.floor(raw)).all(), f"{name}: invalid hour indices")
        indices = raw.astype(int) - 1
        require(((indices >= 0) & (indices < 8760)).all(), f"{name}: index outside year")
        audit.check(name + "_UTC_indices", np.array_equal(stamps.asi8, axis.asi8[indices]))
    else:
        audit.check(name + "_UTC_keys", stamps.isin(axis).all())


def sentinel_mask(frame: pd.DataFrame, direction: str) -> np.ndarray:
    names = [c for c in frame if c.startswith(direction + "_limit") and ("sentinel" in c or "9999" in c)]
    require(bool(names), f"Missing per-sign sentinel provenance for {direction} limits")
    mask = np.zeros(len(frame), bool)
    for name in names:
        col = frame[name]
        if pd.api.types.is_numeric_dtype(col) and not pd.api.types.is_bool_dtype(col):
            require(np.isfinite(col).all() and (col >= 0).all(), f"Invalid sentinel count/flag {name}")
            mask |= col.to_numpy() > 0
        else:
            mask |= boolean(col)
    return mask


def validate_csv_conversion(audit: Audit, source_path: Path, model_path: Path, gamma: float, axis):
    source, model = pd.read_csv(source_path), pd.read_csv(model_path)
    label = source_path.name.removesuffix(".gz").removesuffix(".csv")
    audit.check(label + "_row_count_preserved", len(source) == len(model))
    audit.check(label + "_source_columns_preserved", set(source).issubset(model.columns))
    check_time_keys(audit, source, axis, label + "_source")
    check_time_keys(audit, model, axis, label + "_model")
    for column in source:
        if pd.api.types.is_numeric_dtype(source[column]) and not pd.api.types.is_bool_dtype(source[column]):
            audit.close(label + ":source:" + column, model[column], source[column], allow_nan=True)
        else:
            audit.check(label + ":source:" + column,
                        source[column].fillna("<NULL>").astype(str).equals(model[column].fillna("<NULL>").astype(str)))
        if column.endswith("_mw") and not column.endswith("_model_mw"):
            converted = column.removesuffix("_mw") + "_model_mw"
            require(converted in model, f"Missing common-scale conversion {label}:{converted}")
            expected = source[column].to_numpy(float) * gamma
            if column in ["positive_limit_mw", "negative_limit_mw"]:
                direction = column.split("_")[0]
                sentinel = sentinel_mask(source, direction)
                expected[sentinel] = np.nan
                # Invalid source hours must not produce usable model constraints.
                if "coverage_qualified" in source:
                    expected[~boolean(source.coverage_qualified)] = np.nan
                qualified_columns = [c for c in model if c.startswith(direction + "_limit") and
                                     ("constraint_qualified" in c or c == direction + "_limit_model_usable")]
                require(bool(qualified_columns), f"Missing explicit model constraint qualification for {direction}")
                qualified_expected = np.isfinite(expected)
                if direction + "_limit_usable" in source:
                    qualified_expected &= boolean(source[direction + "_limit_usable"])
                for flag in qualified_columns:
                    audit.check(label + ":" + flag, np.array_equal(boolean(model[flag]), qualified_expected))
            audit.close(label + ":scaled:" + column, model[converted], expected, allow_nan=True)
    audit.close(label + "_gamma", model.scale_factor_gamma.to_numpy(float), np.full(len(model), gamma), tol=1e-14)
    audit.record_file(source_path, "source_table")
    audit.record_file(model_path, "scaled_table")
    return source, model


def validate_generation(audit: Audit, source_root: Path, model_dir: Path, gamma, axis, mat: dict) -> dict:
    loaded = {}
    for stem in ["statewide_fuelmix_hourly", "zonal_generation_priors", "epa_zonal_hourly"]:
        source = find_csv(source_root / "generation_source", stem)
        model = find_csv(model_dir, stem)
        loaded[stem] = validate_csv_conversion(audit, source, model, gamma, axis)[0]
    fuel = loaded["statewide_fuelmix_hourly"]
    priors = loaded["zonal_generation_priors"]
    epa = loaded["epa_zonal_hourly"]
    audit.check("fuelmix_category_inventory", set(fuel.fuel_category) == set(FUEL_CATEGORIES))
    audit.check("fuelmix_complete_hour_category_grid", len(fuel) == 8760 * 7 and not fuel.duplicated(["hour_index", "fuel_category"]).any())
    fuel_valid = boolean(fuel.coverage_qualified)
    audit.check("fuelmix_primary_missingness_follows_coverage", np.array_equal(np.isfinite(fuel.generation_mw.to_numpy(float)), fuel_valid))
    audit.close("fuelmix_qualified_coverage_seconds", fuel.coverage_seconds.to_numpy(float)[fuel_valid], np.full(int(fuel_valid.sum()), 3600.0))
    audit.check("prior_zone_category_inventory", set(priors.zone) == set(ZONES) and set(priors.fuel_category) == set(PRIOR_CATEGORIES))
    audit.check("prior_complete_hour_zone_category_grid", len(priors) == 8760 * 11 * 5 and
                not priors.duplicated(["hour_index", "zone", "fuel_category"]).any())
    audit.check("no_observed_zonal_generation_claim", not boolean(priors.observed_zonal_generation).any())
    valid = boolean(priors.allocation_qualified) & boolean(priors.source_coverage_qualified)
    audit.check("unqualified_priors_remain_missing", np.isnan(priors.prior_actual_mw.to_numpy(float)[~valid]).all())
    audit.check("qualified_priors_finite", np.isfinite(priors.prior_actual_mw.to_numpy(float)[valid]).all())
    fuel_wide = fuel.pivot(index="hour_index", columns="fuel_category", values="generation_mw").reindex(range(1, 8761))
    coverage = fuel.assign(valid=boolean(fuel.coverage_qualified)).pivot(index="hour_index", columns="fuel_category", values="valid").reindex(range(1, 8761))
    prior_order = np.asarray(mat["generation_prior_fuel_names"]).astype(str).reshape(-1).tolist()
    state_order = np.asarray(mat["statewide_generation_fuel_names"]).astype(str).reshape(-1).tolist()
    audit.check("MAT_prior_fuel_order", prior_order == PRIOR_CATEGORIES)
    audit.check("MAT_statewide_fuel_inventory", len(state_order) == 7 and set(state_order) == set(FUEL_CATEGORIES))
    expected_priors = np.full((8760, 11, 5), np.nan)
    expected_qualified = np.zeros((8760, 11, 5), bool)
    for j, category in enumerate(PRIOR_CATEGORIES):
        block = priors.loc[priors.fuel_category == category].copy()
        expected_priors[:, :, j] = block.pivot(index="hour_index", columns="zone", values="prior_actual_mw").reindex(range(1, 8761))[ZONES].to_numpy(float)
        block["valid"] = boolean(block.allocation_qualified) & boolean(block.source_coverage_qualified)
        expected_qualified[:, :, j] = block.pivot(index="hour_index", columns="zone", values="valid").reindex(range(1, 8761))[ZONES].to_numpy(bool)
    audit.close("MAT_source_zonal_generation_priors", mat["zonal_generation_prior_public_mw"], expected_priors, allow_nan=True)
    audit.close("MAT_scaled_zonal_generation_priors", mat["zonal_generation_prior_model_mw"], expected_priors * gamma, allow_nan=True)
    audit.check("MAT_generation_qualification_masks", np.array_equal(np.asarray(mat["zonal_generation_prior_qualified"]).astype(bool), expected_qualified))
    audit.close("MAT_source_statewide_generation", mat["statewide_generation_public_mw"], fuel_wide[state_order].to_numpy(float), allow_nan=True)
    audit.close("MAT_scaled_statewide_generation", mat["statewide_generation_model_mw"], fuel_wide[state_order].to_numpy(float) * gamma, allow_nan=True)
    expected = fuel_wide[["Nuclear", "Hydro", "Wind", "Other Renewables"]].copy()
    expected["Combined Fossil"] = fuel_wide[["Dual Fuel", "Natural Gas", "Other Fossil Fuels"]].sum(axis=1, min_count=3)
    expected_coverage = coverage[["Nuclear", "Hydro", "Wind", "Other Renewables"]].copy()
    expected_coverage["Combined Fossil"] = coverage[["Dual Fuel", "Natural Gas", "Other Fossil Fuels"]].all(axis=1)
    by_key = priors.groupby(["hour_index", "fuel_category"], sort=True)
    first_state = by_key.statewide_actual_mw.first()
    for category in PRIOR_CATEGORIES:
        group = priors.loc[priors.fuel_category == category]
        h = group.hour_index.to_numpy(int) - 1
        audit.close("prior_statewide_source_identity:" + category, group.statewide_actual_mw,
                    expected[category].to_numpy()[h], allow_nan=True)
        audit.check("prior_coverage_identity:" + category,
                    np.array_equal(boolean(group.source_coverage_qualified), expected_coverage[category].to_numpy(bool)[h]))
    allocation_ok = priors.assign(valid=boolean(priors.allocation_qualified)).groupby(["hour_index", "fuel_category"]).valid.all()
    complete = priors.assign(valid=valid).groupby(["hour_index", "fuel_category"]).valid.all()
    summed = by_key.prior_actual_mw.sum(min_count=11)
    shares = by_key.allocation_share.sum(min_count=11)
    audit.close("qualified_prior_sums_match_statewide_source", summed[complete], first_state[complete])
    audit.close("qualified_allocation_shares_sum_to_one", shares[allocation_ok], np.ones(int(allocation_ok.sum())), tol=1e-10)
    audit.check("allocation_shares_nonnegative", (priors.allocation_share.dropna() >= -1e-12).all())
    audit.check("allocation_shares_at_most_one", (priors.allocation_share.dropna() <= 1 + 1e-12).all())
    audit.check("EPA_hour_zone_rows_unique", not epa.duplicated(["hour_index", "zone"]).any())
    audit.check("EPA_zone_inventory", set(epa.zone).issubset(set(ZONES) | {"UNMAPPED"}))
    audit.check("EPA_gross_not_claimed_as_observed_net", not boolean(epa.observed_net_generation).any())
    audit.check("EPA_panel_not_claimed_as_complete_grid_generation", not boolean(epa.complete_grid_generation_coverage).any())
    for column in ["source_unit_rows", "gross_present_rows", "gross_missing_rows", "reported_offline_gross_blank_rows", "active_unknown_gross_rows"]:
        require(column in epa, f"EPA coverage accounting missing {column}")
        audit.check("EPA_nonnegative_counts:" + column, (epa[column] >= 0).all())
    audit.close("EPA_present_missing_count_identity", epa.gross_present_rows + epa.gross_missing_rows, epa.source_unit_rows, tol=0)
    return {"statewide_fuel_hour_rows": len(fuel), "zonal_prior_rows": len(priors), "qualified_zonal_prior_rows": int(valid.sum()),
            "qualified_hour_category_groups": int(complete.sum()), "unqualified_hour_category_groups": int((~complete).sum()),
            "EPA_hour_zone_rows": len(epa), "EPA_gross_is_not_reconciled_to_net_generation": True,
            "observed_zonal_generation": False, "complete_native_dispatch_available": False}


def validate(source_root: Path, model_dir: Path, output_dir: Path) -> dict:
    a = Audit()
    raw_path = UPSTREAM / "npcc.mat"
    metadata_path = UPSTREAM / "npcc_new.csv"
    manifest = json.loads((model_dir / "scaling_manifest.json").read_text())
    upstream = json.loads((ROOT / "output/nygrid_2019/upstream_manifest.json").read_text())
    for path in [raw_path, metadata_path, UPSTREAM / "npcc.csv"]:
        original = next(r for r in upstream["files"] if r["path"] == "Data/" + path.name)
        a.check("pinned_source:" + path.name, sha(path) == original["sha256"])
        a.record_file(path, "pinned_source")
    mat_path = model_dir / "operating_inputs.mat"
    a.check("operating_artifact_fingerprint", sha(mat_path) == manifest["operating_inputs_sha256"])
    data = loadmat(mat_path, simplify_cells=True)
    raw = loadmat(raw_path, simplify_cells=True)["mpc"]
    parent_path = ROOT / "output/nygrid_2019_full_stage1/full_year.mat"
    parent = loadmat(parent_path, simplify_cells=True, variable_names=["base_case"])["base_case"]
    base = data["base_case"]
    for name in ["bus", "gen", "branch", "dcline"]:
        a.close("frozen_parent:" + name, base[name], parent[name], tol=0)
    a.close("frozen_parent_baseMVA", base["baseMVA"], parent["baseMVA"], tol=0)
    a.check("frozen_generator_categories", np.array_equal(base["genfuel"], parent["genfuel"]))
    a.check("original_140_bus_IDs", np.array_equal(np.asarray(data["bus_id"]).reshape(-1), np.arange(1, 141)))
    a.check("annual_hour_indices", np.array_equal(np.asarray(data["hour_index"]).reshape(-1), np.arange(1, 8761)))
    a.check("preserved_model_inventory", np.shape(base["bus"]) == (140, 13) and np.shape(base["branch"]) == (225, 13)
            and np.shape(base["gen"])[0] == 271 and np.shape(base["dcline"]) == (4, 17))
    for flag in ["ny_generation_dispatch_available", "ready_for_dc_power_flow"]:
        a.check("MAT_unqualified:" + flag, not bool(data[flag]))
    for flag in ["topology_modified", "reference_is_measured_peak", "ny_generation_dispatch_available", "ready_for_dc_power_flow",
                 "ac_feasibility_validated", "interface_calibration_performed"]:
        a.check("manifest_unqualified:" + flag, manifest[flag] is False)

    axis = pd.date_range("2025-01-01 05:00Z", periods=8760, freq="h")
    local = axis.tz_convert("America/New_York")
    hours = pd.read_csv(source_root / "load_source/hour_catalog.csv")
    a.check("source_exact_physical_year_axis", pd.DatetimeIndex(pd.to_datetime(hours.timestamp_utc, utc=True)).equals(axis))
    a.check("MAT_exact_UTC_axis", pd.DatetimeIndex(pd.to_datetime(np.asarray(data["timestamp_utc"]).reshape(-1), utc=True)).equals(axis))
    a.check("hour_catalog_preserved", hours.equals(pd.read_csv(model_dir / "hour_catalog.csv")))
    a.check("source_local_labels", np.array_equal(pd.to_datetime(hours.local_timestamp).to_numpy(), local.tz_localize(None).to_numpy()))
    a.check("source_time_zones", np.array_equal(hours.time_zone.to_numpy(), np.asarray([t.tzname() for t in local])))
    a.close("source_UTC_offsets_minutes", hours.utc_offset_minutes, [t.utcoffset().total_seconds() / 60 for t in local], tol=0)
    folds = np.asarray([t.to_pydatetime().fold for t in local])
    a.close("source_DST_folds", hours.dst_fold, folds, tol=0)
    a.check("one_repeated_fall_label", int(local.tz_localize(None).duplicated().sum()) == 1)
    a.check("no_nonexistent_spring_label", not any((t.month == 3 and t.day == 9 and t.hour == 2) for t in local))
    wide = pd.read_csv(source_root / "load_source/load_wide.csv")
    interfaces = pd.read_csv(source_root / "load_source/interface_wide.csv")
    for name, frame in [("load", wide), ("interfaces", interfaces)]:
        a.check(name + "_wide_UTC_order", pd.DatetimeIndex(pd.to_datetime(frame.timestamp_utc, utc=True)).equals(axis))
    public = wide[ZONES].to_numpy(float)
    a.check("complete_finite_positive_load_source", public.shape == (8760, 11) and np.isfinite(public).all() and (public >= 0).all())
    info = pd.read_csv(metadata_path, keep_default_na=False).set_index("idx")
    source_info = pd.read_csv(UPSTREAM / "npcc.csv", keep_default_na=False).set_index("idx")
    ny_ids = source_info.index[source_info.zone.isin(ZONES)].to_numpy(int)
    ny_mask = np.isin(np.arange(1, 141), ny_ids)
    a.check("NY_original_identity_count", len(ny_ids) == 46 and len(set(ny_ids)) == 46)
    anchor = float(raw["bus"][ny_mask, 2].sum())
    a.close("source_mat_snapshot_anchor_9561", anchor, 9561.0, tol=0)
    peak = float(public.sum(axis=1).max())
    gamma = anchor / peak
    a.close("one_annual_scale_factor", data["gamma"], gamma, tol=1e-14)
    a.close("manifest_scale_factor", manifest["gamma"], gamma, tol=1e-14)
    a.close("manifest_reference_anchor", manifest["reference_ny_load_mw"], anchor, tol=0)
    a.close("manifest_annual_peak", manifest["annual_peak_public_mw"], peak)
    a.close("public_load_preserved", data["zonal_load_public_mw"], public)
    a.close("model_zonal_load_common_gamma", data["zonal_load_model_mw"], public * gamma)
    a.close("model_peak_equals_snapshot_anchor", np.asarray(data["zonal_load_model_mw"]).sum(axis=1).max(), anchor)
    weights = pd.read_csv(model_dir / "bus_allocation.csv").set_index("bus_id")
    a.check("all_NY_allocation_records_once", set(weights.index) == set(ny_ids) and weights.index.is_unique)
    ny_pf_ratio = np.tan(np.arccos(.98))
    fallback = []
    for j, z in enumerate(ZONES):
        ids = info.index[info.zone == z].to_numpy(int)
        values = np.maximum(info.loc[ids, "sumLoadP0"].to_numpy(float), 0)
        if values.sum() == 0:
            expected_weights = np.full(len(ids), 1 / len(ids))
            fallback.append(z)
            expected_policy = "paper_uniform_zero_load_zone_fallback"
        else:
            expected_weights = values / values.sum()
            expected_policy = "paper_npcc_new_positive_load_share"
        a.close("allocation_weights:" + z, weights.loc[ids, "weight"], expected_weights, tol=1e-12)
        a.check("allocation_policy:" + z, (weights.loc[ids, "allocation_policy"] == expected_policy).all())
        expected_bus = public[:, j, None] * gamma * expected_weights
        a.close("bus_gross_allocation:" + z, data["bus_gross_pd"][:, ids - 1], expected_bus)
        a.close("zone_gross_conservation:" + z, data["bus_gross_pd"][:, ids - 1].sum(axis=1), public[:, j] * gamma)
    a.check("only_J_uniform_fallback", fallback == ["J"])
    a.close("NY_reactive_assumption", data["bus_gross_qd"][:, ny_mask], data["bus_gross_pd"][:, ny_mask] * ny_pf_ratio)
    ratio = public.sum(axis=1) / peak
    a.close("external_shape_ratio", data["external_load_ratio"], ratio)
    a.close("external_gross_PD", data["bus_gross_pd"][:, ~ny_mask], ratio[:, None] * np.abs(raw["bus"][~ny_mask, 2]))
    a.close("external_QD_constant_snapshot_power_factor", data["bus_gross_qd"][:, ~ny_mask], ratio[:, None] * raw["bus"][~ny_mask, 3])
    a.close("full_gross_peak_at_modified_NPCC_snapshot", data["bus_gross_pd"].sum(axis=1).max(), 27969.0)
    a.check("nonnegative_gross_PD", np.isfinite(data["bus_gross_pd"]).all() and (data["bus_gross_pd"] >= 0).all())

    schedule = interfaces[CHANNELS].to_numpy(float)
    a.close("boundary_public_preserved", data["boundary_public_mw"], schedule, allow_nan=True)
    a.close("boundary_common_gamma", data["boundary_model_mw"], schedule * gamma, allow_nan=True)
    regions = np.column_stack([interfaces[channels].sum(axis=1, min_count=len(channels)) for channels in REGIONS.values()]) * gamma
    a.close("regional_schedule_accounting", data["regional_import_model_mw"], regions, allow_nan=True)
    expected_dc = np.column_stack([
        interfaces[["SCH - NPX_1385", "SCH - NPX_CSC"]].sum(axis=1, min_count=2),
        interfaces["SCH - PJM_NEPTUNE"], interfaces["SCH - PJM_HTP"], interfaces["SCH - PJM_VFT"]]) * gamma
    a.close("four_DC_schedules_order_and_scale", data["dcline_pf"], expected_dc, allow_nan=True)
    a.close("four_DC_endpoint_identity", base["dcline"][:, :2], [[21, 80], [124, 79], [125, 81], [125, 81]], tol=0)
    boundary_valid = np.isfinite(schedule).all(axis=1)
    a.check("boundary_validity_mask", np.array_equal(np.asarray(data["boundary_hour_qualified"]).reshape(-1).astype(bool), boundary_valid))
    a.check("boundary_validity_count", manifest["boundary_qualified_hours"] == int(boundary_valid.sum()))
    fuel = np.asarray(base["genfuel"]).astype(str)
    gen = np.asarray(base["gen"])
    native = (fuel != "Import") & np.isin(gen[:, 0], ny_ids)
    a.check("243_NY_native_generation_rows_pending", int(native.sum()) == 243 and np.isnan(data["external_input_pg"][:, native]).all())
    external_specs = pd.read_csv(model_dir / "external_generator_allocation.csv").set_index("generator_row")
    identified = []
    for j, (region, areas) in enumerate([("ISONE", [1]), ("ONTARIO", [4]), ("PJM", [5, 6])]):
        buses = source_info.index[source_info.area.isin(areas)].to_numpy(int)
        gr = np.flatnonzero((fuel == "Import") & np.isin(gen[:, 0], buses))
        raw_gen = raw["gen"][np.isin(raw["gen"][:, 0], buses)]
        a.close("external_generator_bus_lineage:" + region, gen[gr, 0], raw_gen[:, 0], tol=0)
        shares = raw_gen[:, 1] / raw_gen[:, 1].sum()
        demand = data["bus_gross_pd"][:, buses - 1].sum(axis=1)
        expected_pg = (demand + regions[:, j])[:, None] * shares
        a.close("external_generator_allocation:" + region, data["external_input_pg"][:, gr], expected_pg, allow_nan=True)
        a.close("external_region_net_export:" + region, data["external_input_pg"][:, gr].sum(axis=1) - demand, regions[:, j], allow_nan=True)
        a.close("external_generator_share_register:" + region, external_specs.loc[gr + 1, "generation_share"], shares, tol=1e-12)
        identified.extend(gr.tolist())
    hq = np.flatnonzero((fuel == "Import") & (gen[:, 0] == 48))
    a.check("single_HQ_proxy", len(hq) == 1)
    a.close("HQ_Cedars_not_double_counted", data["external_input_pg"][:, hq[0]], regions[:, 3], allow_nan=True)
    identified.extend(hq.tolist())
    a.check("28_external_and_HQ_rows_once", len(set(identified)) == 28 and set(identified) == set(np.flatnonzero(~native)))
    a.check("external_generator_register_coverage", set(external_specs.index) == set(np.asarray(identified) + 1))
    load_long, _ = validate_csv_conversion(a, find_csv(source_root / "load_source", "load_hourly"),
                                         find_csv(model_dir, "load_hourly"), gamma, axis)
    a.check("load_long_complete_hour_zone_grid", len(load_long) == 8760 * 11 and
            not load_long.duplicated(["hour_index", "zone"]).any() and set(load_long.zone) == set(ZONES))
    a.check("all_load_hours_source_qualified", boolean(load_long.coverage_qualified).all())
    load_pivot = load_long.pivot(index="hour_index", columns="zone", values="load_mw").reindex(range(1, 8761))[ZONES]
    a.close("source_long_wide_load_agreement", load_pivot.to_numpy(float), public)
    flow_long, _ = validate_csv_conversion(a, find_csv(source_root / "load_source", "interface_hourly"),
                                         find_csv(model_dir, "interface_hourly"), gamma, axis)
    a.check("P32_long_hour_channel_keys_unique", not flow_long.duplicated(["hour_index", "channel"]).any())
    flow_pivot = flow_long.pivot(index="hour_index", columns="channel", values="flow_mw").reindex(range(1, 8761))
    a.check("P32_long_complete_hour_channel_grid", len(flow_long) == 8760 * len(flow_pivot.columns))
    a.close("source_long_wide_P32_agreement", flow_pivot.to_numpy(float), interfaces[flow_pivot.columns].to_numpy(float), allow_nan=True)
    a.check("P32_primary_missingness_follows_coverage", np.array_equal(np.isfinite(flow_long.flow_mw.to_numpy(float)), boolean(flow_long.coverage_qualified)))
    generation = validate_generation(a, source_root, model_dir, gamma, axis, data)
    generation_hour_valid = np.asarray(data["zonal_generation_prior_qualified"]).astype(bool).all(axis=(1, 2))
    for path in [mat_path, model_dir / "scaling_manifest.json", model_dir / "bus_allocation.csv",
                 model_dir / "external_generator_allocation.csv", source_root / "load_source/hour_catalog.csv",
                 source_root / "load_source/load_wide.csv", source_root / "load_source/interface_wide.csv", parent_path, Path(__file__)]:
        a.record_file(path, "input_or_validation_code")
    result = {"passed": True, "scope": "independent_input_accounting_validation_not_operating_case_qualification",
              "hours": 8760, "buses": 140, "NY_buses": 46, "external_buses": 94,
              "reference_NY_snapshot_mw": anchor, "actual_2025_NY_peak_mw": peak, "gamma": gamma,
              "fallback_zones": fallback, "boundary_complete_hours": int(boundary_valid.sum()),
              "boundary_incomplete_hours": int((~boundary_valid).sum()), "generation": generation,
              "all_generation_priors_qualified_hours": int(generation_hour_valid.sum()),
              "boundary_and_generation_priors_qualified_hours": int((boundary_valid & generation_hour_valid).sum()),
              "ready_for_dc_power_flow": False, "ac_feasibility_validated": False,
              "check_count": len(a.checks), "checks": a.checks, "files": list(a.files.values())}
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(a.checks).to_csv(output_dir / "validation_checks.csv", index=False, lineterminator="\n")
    (output_dir / "validation_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"checks", "files", "generation"}}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    validate(args.source_root, args.model_dir or args.source_root / "model", args.output_dir or args.source_root / "validation")
