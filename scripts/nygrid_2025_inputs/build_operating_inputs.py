"""Compile scaled 2025 operating inputs for the unreduced NYgrid NPCC parent.

This stage is an input package, not an executable generation dispatch. Gross
load remains separate from renewable generation and external exchanges. The
one annual gamma converts every public MW series to the same benchmark scale.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tmp/nygrid_2019_reproduction/upstream/Data"
OUT = ROOT / "output/nygrid_2025_inputs"
ZONES = list("ABCDEFGHIJK")
CHANNELS = ["SCH - HQ - NY", "SCH - HQ_CEDARS", "SCH - OH - NY",
            "SCH - NE - NY", "SCH - NPX_1385", "SCH - NPX_CSC",
            "SCH - PJ - NY", "SCH - PJM_HTP", "SCH - PJM_NEPTUNE", "SCH - PJM_VFT"]
REGIONS = {"ISONE": ["SCH - NE - NY", "SCH - NPX_1385", "SCH - NPX_CSC"],
           "ONTARIO": ["SCH - OH - NY"],
           "PJM": ["SCH - PJ - NY", "SCH - PJM_HTP", "SCH - PJM_NEPTUNE", "SCH - PJM_VFT"],
           "HQ": ["SCH - HQ - NY", "SCH - HQ_CEDARS"]}
AREA_REGION = {1: "ISONE", 4: "ONTARIO", 5: "PJM", 6: "PJM"}
GENERATION_FUELS = ["Combined Fossil", "Nuclear", "Hydro", "Wind", "Other Renewables"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_table(folder, name):
    path = folder / name
    if not path.exists():
        path = path.with_suffix(path.suffix + ".gz")
    require(path.is_file(), f"Missing source table: {name}")
    return path


def allocation(metadata):
    """Frozen paper bus weights, with explicit uniform fallback in zero-load J."""
    info = metadata.copy().sort_values("idx")
    require(info.idx.is_unique, "Duplicate bus identity")
    rows = []
    for z in ZONES:
        group = info.loc[info.zone == z]
        require(len(group) > 0, f"Missing zone {z}")
        positive = group.sumLoadP0.clip(lower=0).to_numpy(float)
        if positive.sum() > 0:
            weights = positive / positive.sum()
            policy = "paper_npcc_new_positive_load_share"
        else:
            weights = np.ones(len(group)) / len(group)
            policy = "paper_uniform_zero_load_zone_fallback"
        for record, weight in zip(group.to_dict("records"), weights):
            rows.append(dict(bus_id=int(record["idx"]), bus_name=record["name"], zone=z,
                             weight=float(weight), allocation_policy=policy))
    return pd.DataFrame(rows).sort_values("bus_id").reset_index(drop=True)


def load_arrays(public_load, raw_bus, weights, metadata, ny_pf=0.98):
    require(public_load.ndim == 2 and public_load.shape[1] == 11, "Expected eleven load zones")
    require(np.isfinite(public_load).all() and (public_load >= 0).all(), "Invalid public load")
    require(np.array_equal(raw_bus[:, 0], np.arange(1, 141)), "Unexpected raw NPCC bus order")
    require(0 < ny_pf <= 1, "Invalid assumed power factor")
    ny_idx = weights.bus_id.to_numpy(int) - 1
    require(len(ny_idx) == 46 and len(set(ny_idx)) == 46, "Expected 46 unique NY buses")
    reference = float(np.abs(raw_bus[ny_idx, 2]).sum())
    peak = float(public_load.sum(axis=1).max())
    require(reference > 0 and peak > 0, "Nonpositive scale anchor")
    gamma = reference / peak
    model = public_load * gamma
    # This is the source paper's regional load-shape proxy, now at NPCC scale.
    ratio = model.sum(axis=1) / reference
    pd_gross = ratio[:, None] * np.abs(raw_bus[:, 2])[None, :]
    qd_gross = ratio[:, None] * raw_bus[:, 3][None, :]
    for r in weights.itertuples(index=False):
        pd_gross[:, r.bus_id - 1] = model[:, ZONES.index(r.zone)] * r.weight
    qd_gross[:, ny_idx] = pd_gross[:, ny_idx] * np.tan(np.arccos(ny_pf))
    return dict(zonal_load_public_mw=public_load, zonal_load_model_mw=model,
                bus_gross_pd=pd_gross, bus_gross_qd=qd_gross, gamma=gamma,
                reference_ny_load_mw=reference, annual_peak_public_mw=peak,
                external_load_ratio=ratio)


def boundary_arrays(wide, gamma, base_case, raw_case, metadata, load_ratio):
    """Full-region exchange accounting; channels are counted exactly once.

    External generator shares are inherited NPCC equivalents, not observations
    of neighboring generators. Missing P32 coverage propagates as NaN.
    """
    require(all(c in wide for c in CHANNELS), "Missing required external schedule channel")
    public = wide[CHANNELS].to_numpy(float)
    model = public * gamma
    reg = np.column_stack([wide[names].sum(axis=1, min_count=len(names)).to_numpy(float)
                           for names in REGIONS.values()]) * gamma
    reg_idx = {name: j for j, name in enumerate(REGIONS)}
    # The four source DC links draw from the same external regional injection.
    dc = np.column_stack([wide[["SCH - NPX_1385", "SCH - NPX_CSC"]].sum(axis=1, min_count=2),
                          wide["SCH - PJM_NEPTUNE"], wide["SCH - PJM_HTP"],
                          wide["SCH - PJM_VFT"]]) * gamma
    info = metadata.set_index("idx")
    gen = np.asarray(base_case["gen"], float)
    fuel = np.asarray(base_case["genfuel"])
    output = np.full((len(wide), len(gen)), np.nan)
    specs = []
    for region in ["ISONE", "ONTARIO", "PJM"]:
        bus_ids = info.index[info.area.map(AREA_REGION) == region].to_numpy(int)
        rows = np.flatnonzero((fuel == "Import") & np.isin(gen[:, 0], bus_ids))
        raw = np.asarray(raw_case["gen"], float)
        raw_rows = raw[np.isin(raw[:, 0], bus_ids)]
        # Preserve parallel generator identities through the ordered region subset.
        require(np.array_equal(raw_rows[:, 0], gen[rows, 0]), f"External generator ordering changed: {region}")
        shares = raw_rows[:, 1] / raw_rows[:, 1].sum()
        require(np.isfinite(shares).all() and (shares >= 0).all(), "Invalid external generation shares")
        region_pd = np.abs(raw_case["bus"][bus_ids - 1, 2]).sum() * load_ratio
        total = region_pd + reg[:, reg_idx[region]]
        output[:, rows] = total[:, None] * shares
        for row, weight in zip(rows, shares):
            specs.append(dict(generator_row=int(row + 1), bus_id=int(gen[row, 0]),
                              region=region, generation_share=float(weight),
                              policy="original_NPCC_PG_share_of_regional_load_plus_exchange"))
    hq = np.flatnonzero((fuel == "Import") & (gen[:, 0] == 48))
    require(len(hq) == 1, "HQ injection identity changed")
    output[:, hq[0]] = reg[:, reg_idx["HQ"]]
    specs.append(dict(generator_row=int(hq[0] + 1), bus_id=48, region="HQ", generation_share=1.0,
                      policy="HQ_schedule_plus_Cedars_single_injection"))
    return dict(boundary_public_mw=public, boundary_model_mw=model,
                regional_import_model_mw=reg, dcline_pf=dc, external_input_pg=output), pd.DataFrame(specs)


def load_sources(folder):
    """Source adapter; the source extractor retains all original quality flags."""
    hours = pd.read_csv(folder / "hour_catalog.csv")
    wide = pd.read_csv(folder / "load_wide.csv")
    interface = pd.read_csv(folder / "interface_wide.csv")
    require("timestamp_utc" in hours, "Missing canonical UTC hour key")
    axis = pd.DatetimeIndex(pd.to_datetime(hours.timestamp_utc, utc=True))
    expected = pd.date_range("2025-01-01 05:00Z", periods=8760, freq="h")
    require(axis.equals(expected), "Incomplete or shifted 2025 physical-hour axis")
    for frame in [wide, interface]:
        require(pd.DatetimeIndex(pd.to_datetime(frame.timestamp_utc, utc=True)).equals(axis),
                "Source tables do not share exact UTC hour order")
    return hours, wide, interface


def generation_arrays(folder, hours, gamma):
    """Preserve priors and qualification separately; do not manufacture dispatch."""
    axis = pd.DatetimeIndex(pd.to_datetime(hours.timestamp_utc, utc=True))
    zone = pd.read_csv(source_table(folder, "zonal_generation_priors.csv"))
    zone["utc"] = pd.to_datetime(zone.timestamp_utc, utc=True)
    require(not zone.duplicated(["utc", "zone", "fuel_category"]).any(), "Duplicated generation prior key")
    require(set(zone.zone) == set(ZONES), "Unexpected generation prior zones")
    require(set(zone.fuel_category) == set(GENERATION_FUELS), "Unexpected generation prior fuels")
    prior = np.full((8760, 11, len(GENERATION_FUELS)), np.nan)
    qualified = np.zeros(prior.shape, dtype=bool)
    for f, fuel in enumerate(GENERATION_FUELS):
        block = zone.loc[zone.fuel_category == fuel]
        pivot = block.pivot(index="utc", columns="zone", values="prior_actual_mw")
        require(pivot.index.equals(axis), f"Incomplete generation prior hours: {fuel}")
        prior[:, :, f] = pivot[ZONES].to_numpy(float)
        valid = block.copy()
        for key in ["allocation_qualified", "source_coverage_qualified"]:
            valid[key] = valid[key].astype(str).str.lower().isin(["true", "1"])
        valid["qualified"] = valid.allocation_qualified & valid.source_coverage_qualified
        qualified[:, :, f] = valid.pivot(index="utc", columns="zone", values="qualified")[ZONES].to_numpy(bool)
    fuel = pd.read_csv(source_table(folder, "statewide_fuelmix_hourly.csv"))
    fuel["utc"] = pd.to_datetime(fuel.timestamp_utc, utc=True)
    require(not fuel.duplicated(["utc", "fuel_category"]).any(), "Duplicated fuel mix key")
    state = fuel.pivot(index="utc", columns="fuel_category", values="generation_mw")
    require(state.index.equals(axis), "Incomplete statewide generation hours")
    values = state.to_numpy(float)
    return dict(zonal_generation_prior_public_mw=prior,
                zonal_generation_prior_model_mw=prior * gamma,
                zonal_generation_prior_qualified=qualified,
                generation_prior_fuel_names=np.array(GENERATION_FUELS, dtype=object),
                statewide_generation_public_mw=values,
                statewide_generation_model_mw=values * gamma,
                statewide_generation_fuel_names=state.columns.to_numpy(dtype=object))


def build(source_root=OUT, output=None):
    source_root = Path(source_root).resolve()
    output = Path(output).resolve() if output is not None else source_root / "model"
    require(not (output / "operating_inputs.mat").exists(), "Choose a new output folder; frozen inputs already exist")
    hours, wide, interface = load_sources(source_root / "load_source")
    upstream = json.loads((ROOT / "output/nygrid_2019/upstream_manifest.json").read_text())
    for filename in ["npcc.mat", "npcc_new.csv"]:
        expected = next(f["sha256"] for f in upstream["files"] if f["path"] == f"Data/{filename}")
        require(sha(SOURCE / filename) == expected, f"Pinned source changed: {filename}")
    raw = loadmat(SOURCE / "npcc.mat", simplify_cells=True)["mpc"]
    parent_path = ROOT / "output/nygrid_2019_full_stage1/full_year.mat"
    parent = loadmat(parent_path, simplify_cells=True, variable_names=["base_case"])["base_case"]
    info = pd.read_csv(SOURCE / "npcc_new.csv", keep_default_na=False)
    weights = allocation(info)
    arrays = load_arrays(wide[ZONES].to_numpy(float), np.asarray(raw["bus"]), weights, info)
    boundary, external_shares = boundary_arrays(interface, arrays["gamma"], parent, raw, info,
                                                 arrays["external_load_ratio"])
    arrays.update(boundary)
    arrays.update(generation_arrays(source_root / "generation_source", hours, arrays["gamma"]))
    # Source reconciliation only: schedules, telemetry and losses need not agree.
    # NaNs propagate when even one component lacks qualified source coverage.
    arrays["ny_balance_residual_public_mw"] = (arrays["statewide_generation_public_mw"].sum(axis=1)
        + arrays["boundary_public_mw"].sum(axis=1) - arrays["zonal_load_public_mw"].sum(axis=1))
    arrays["ny_balance_residual_model_mw"] = arrays["ny_balance_residual_public_mw"] * arrays["gamma"]
    output.mkdir(parents=True, exist_ok=True)
    weights.to_csv(output / "bus_allocation.csv", index=False, lineterminator="\n")
    external_shares.to_csv(output / "external_generator_allocation.csv", index=False, lineterminator="\n")
    hours.to_csv(output / "hour_catalog.csv", index=False, lineterminator="\n")
    gamma = arrays["gamma"]
    for filename in ["load_hourly.csv", "interface_hourly.csv"]:
        frame = pd.read_csv(source_root / "load_source" / filename)
        # Numeric MW conversions are explicit; timestamps, quality and source IDs survive.
        for column in list(frame.columns):
            if column.endswith("_mw") and not column.endswith("_model_mw"):
                frame[column.removesuffix("_mw") + "_model_mw"] = frame[column] * gamma
        if filename == "interface_hourly.csv":
            for sign in ["positive", "negative"]:
                flag = f"{sign}_limit_contains_sentinel"
                require(flag in frame, "Source limits need contributing-sample sentinel flags")
                sentinel = frame[flag].astype(str).str.lower().isin(["true", "1"])
                source_hour_ok = frame.coverage_qualified.astype(str).str.lower().isin(["true", "1"])
                frame.loc[sentinel | ~source_hour_ok, f"{sign}_limit_model_mw"] = np.nan
                frame[f"{sign}_limit_model_usable"] = (~sentinel
                    & np.isfinite(frame[f"{sign}_limit_model_mw"])
                    & frame[f"{sign}_limit_usable"].astype(str).str.lower().isin(["true", "1"]))
        frame["scale_factor_gamma"] = gamma
        frame.to_csv(output / filename, index=False, lineterminator="\n")
    generation_files = []
    gen_folder = source_root / "generation_source"
    for name in ["statewide_fuelmix_hourly.csv", "zonal_generation_priors.csv", "epa_zonal_hourly.csv"]:
        path = source_table(gen_folder, name)
        frame = pd.read_csv(path)
        for column in list(frame.columns):
            if column.endswith("_mw") and not column.endswith("_model_mw"):
                frame[column.removesuffix("_mw") + "_model_mw"] = frame[column] * gamma
        frame["scale_factor_gamma"] = gamma
        destination = output / path.name
        compression = {"method": "gzip", "mtime": 0} if destination.suffix == ".gz" else None
        frame.to_csv(destination, index=False, lineterminator="\n", compression=compression)
        generation_files.append(destination.name)
    require(generation_files, "Generation source priors must be assembled before compilation")
    arrays.update(hour_index=np.arange(1, 8761), bus_id=np.arange(1, 141),
                  base_case=parent, zone_names=np.array(ZONES, dtype=object),
                  boundary_channel_names=np.array(CHANNELS, dtype=object),
                  regional_import_names=np.array(list(REGIONS), dtype=object),
                  timestamp_utc=hours.timestamp_utc.to_numpy(dtype=object),
                  boundary_hour_qualified=np.isfinite(arrays["boundary_public_mw"]).all(axis=1),
                  ny_generation_dispatch_available=False, ready_for_dc_power_flow=False)
    savemat(output / "operating_inputs.mat", arrays, do_compression=True, oned_as="column")
    manifest = dict(model_year=2025, hours=8760, buses=140, topology_modified=False,
                    gamma=gamma, reference_ny_load_mw=arrays["reference_ny_load_mw"],
                    annual_peak_public_mw=arrays["annual_peak_public_mw"],
                    annual_peak_timestamp_utc=hours.iloc[int(np.argmax(wide[ZONES].sum(axis=1)))].timestamp_utc,
                    scaling_policy="single fixed annual gamma: original source NY snapshot / 2025 observed annual peak",
                    reference_is_measured_peak=False,
                    load_interval_assumption="P58C labels treated as hour beginnings following prior empirical repository timing audit; not a provider integration specification",
                    within_zone_policy="pinned npcc_new positive shares; zero-load zone J uniform fallback",
                    ny_q_policy="gross load at assumed 0.98 lagging power factor; not observed",
                    external_q_policy="original signed QD times external load ratio; preserves snapshot Q/P",
                    external_load_policy="original abs(PD) times scaled NY gross total / 9561; regional proxy, not 2025 observations",
                    generation_files=generation_files,
                    boundary_qualified_hours=int(arrays["boundary_hour_qualified"].sum()),
                    missing_boundary_policy="NaN retained; no interpolation or fill at compiler stage",
                    generation_policy="source priors only; 2025 fleet landing and bounded balanced dispatch pending",
                    renewable_policy="gross loads retained; no renewable subtraction until mapped exactly once",
                    boundary_policy="ten disjoint paper schedule channels; full external networks retained; DC transfers draw on same regional totals",
                    reference_case_role="frozen 2019 topology and generator row identities only, not a 2025 operating case",
                    ny_generation_dispatch_available=False, ready_for_dc_power_flow=False,
                    ac_feasibility_validated=False, interface_calibration_performed=False,
                    provenance=[dict(path=str(p.relative_to(ROOT)).replace('\\','/'), sha256=sha(p))
                                for p in [SOURCE / "npcc.mat", SOURCE / "npcc_new.csv", parent_path,
                                          *sorted((source_root / "load_source").glob("*.csv")),
                                          *[gen_folder / n for n in generation_files]]],
                    operating_inputs_sha256=sha(output / "operating_inputs.mat"))
    (output / "scaling_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "provenance"}, indent=2))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=OUT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    build(args.source_root, args.output)
